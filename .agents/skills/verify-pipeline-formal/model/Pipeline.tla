---------------------------- MODULE Pipeline ----------------------------
(***************************************************************************)
(* Session lifecycle of backend/app/pipeline.py, the demo replay in        *)
(* backend/app/ingest/__init__.py and the operator routes in               *)
(* backend/app/api/demo.py.                                                *)
(*                                                                         *)
(* Atomicity follows the code: the asyncio event loop runs one coroutine   *)
(* between awaits, so each action below is the code between two awaits.   *)
(* SMS sends run `send_if_live` in a worker thread (asyncio.to_thread),    *)
(* so the thread's generation check (TCheck) and the gateway call (TSend)  *)
(* are separate steps that interleave with the event loop. Cancelling a    *)
(* task that awaits a thread does not stop the thread.                     *)
(*                                                                         *)
(* Abstractions: one alert category (a session queues at most one ALERT,   *)
(* as with the bank call); consent is always active; the gateway never     *)
(* raises; rule outcomes are nondeterministic per segment.                 *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
    Arm,            \* "B" (demo arm: rules on the loop) or "C" (rules in a thread)
    MaxSegs,        \* segments per replay
    MaxRuns,        \* replays started (the first + operator Run clicks)
    MaxOps,         \* operator actions (Run / End call / Reset)
    \* Guards present in the code. Set one to FALSE to model a broken variant.
    FinishGuard,    \* finish(): `if s.finish_task is None` (one shared finish task)
    EmitGuard,      \* _emit(): `if _live(s.generation)`
    ThreadRecheck,  \* _send.send_if_live(): `if not _live(s.generation): return None`
    FinishLock      \* _finish(): `async with s.lock` before draining

Runs == 1..MaxRuns
States == {"idle", "start", "start_wait", "next", "eval", "fin_wait", "end"}

VARIABLES
    gen,        \* pipeline._generation
    cur,        \* pipeline._session (0 = None); session id = id of the replay that created it
    nruns,      \* replays started; replay nruns is demo._replay
    rp,         \* replay coroutine pc (ingest.run -> pipeline.start/process/finish)
    rw,         \* finish task a coroutine awaits: [s, i]
    rsegs,      \* segments left in each replay
    sgen,       \* session.generation (0 = not created)
    fin,        \* session.finished
    alerted,    \* session.alerts non-empty
    lock,       \* session.lock held by process() (arm C)
    ftasks,     \* session.finish_task(s): Seq of [pc, snap, fu]
    tasks,      \* SMS send tasks: Seq of [s, tmpl, pc, th, checked]
    op,         \* operator request in flight: [kind, pc, s, i]
    ops,        \* operator requests used
    log,        \* events published by emit(): [type, s, live]
    delivered   \* gateway.send() calls that reached the gateway: [s, tmpl, sgen, gen, checked]

vars == <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, ftasks, tasks, op, ops, log, delivered>>

Init ==
    /\ gen = 0 /\ cur = 0 /\ nruns = 1
    /\ rp = [r \in Runs |-> IF r = 1 THEN "start" ELSE "idle"]
    /\ rw = [r \in Runs |-> [s |-> 0, i |-> 0]]
    /\ rsegs = [r \in Runs |-> MaxSegs]
    /\ sgen = [r \in Runs |-> 0]
    /\ fin = [r \in Runs |-> FALSE]
    /\ alerted = [r \in Runs |-> FALSE]
    /\ lock = [r \in Runs |-> FALSE]
    /\ ftasks = [r \in Runs |-> <<>>]
    /\ tasks = <<>>
    /\ op = [kind |-> "none", pc |-> "idle", s |-> 0, i |-> 0]
    /\ ops = 0
    /\ log = <<>>
    /\ delivered = <<>>

\* --- helpers ------------------------------------------------------------------

Live(s) == sgen[s] = gen                                          \* pipeline._live
Emit(l, type, s) == IF ~EmitGuard \/ Live(s)                      \* pipeline._emit
                    THEN Append(l, [type |-> type, s |-> s, live |-> Live(s)]) ELSE l
NewTask(s, tmpl) == [s |-> s, tmpl |-> tmpl, pc |-> "queued", th |-> "idle", checked |-> 0]

\* pipeline.finish(s): the finish task index the caller will await (0 = returned at once)
Creates(s) == cur = s /\ ~(FinishGuard /\ Len(ftasks[s]) > 0)
FinIdx(s) == IF cur # s THEN 0 ELSE IF Creates(s) THEN Len(ftasks[s]) + 1 ELSE 1
FinFtasks(s) == IF Creates(s) THEN [ftasks EXCEPT ![s] = Append(@, [pc |-> "lock", snap |-> {}, fu |-> 0])] ELSE ftasks
FinFin(s) == IF Creates(s) THEN [fin EXCEPT ![s] = TRUE] ELSE fin
FinDone(w) == w.i = 0 \/ ftasks[w.s][w.i].pc = "done"

\* demo._cancel_replay(): cancel the latest replay task wherever it awaits
Cancelled(r) == rp[r] \in {"start", "start_wait", "next", "eval", "fin_wait"}
CancelRp == IF Cancelled(nruns) THEN [rp EXCEPT ![nruns] = "end"] ELSE rp
CancelLock == IF rp[nruns] = "eval" THEN [lock EXCEPT ![nruns] = FALSE] ELSE lock   \* `async with` exits

\* --- replay coroutine (ingest.run) ----------------------------------------------

\* pipeline.start: an active session is finished first (awaited, shielded)
RStartFinish(r) ==
    /\ rp[r] = "start" /\ cur # 0
    /\ rp' = [rp EXCEPT ![r] = "start_wait"]
    /\ rw' = [rw EXCEPT ![r] = [s |-> cur, i |-> FinIdx(cur)]]
    /\ ftasks' = FinFtasks(cur) /\ fin' = FinFin(cur)
    /\ UNCHANGED <<gen, cur, nruns, rsegs, sgen, alerted, lock, tasks, op, ops, log, delivered>>

RStartCreate(r) ==
    /\ \/ rp[r] = "start" /\ cur = 0
       \/ rp[r] = "start_wait" /\ FinDone(rw[r])
    /\ gen' = gen + 1 /\ cur' = r
    /\ sgen' = [sgen EXCEPT ![r] = gen + 1]
    /\ rp' = [rp EXCEPT ![r] = "next"]
    /\ log' = Append(log, [type |-> "running", s |-> r, live |-> TRUE])
    /\ UNCHANGED <<nruns, rw, rsegs, fin, alerted, lock, ftasks, tasks, op, ops, delivered>>

\* ingest: `if not _alive(ref): return`
RStop(r) ==
    /\ rp[r] = "next" /\ cur # r
    /\ rp' = [rp EXCEPT ![r] = "end"]
    /\ UNCHANGED <<gen, cur, nruns, rw, rsegs, sgen, fin, alerted, lock, ftasks, tasks, op, ops, log, delivered>>

\* ingest: after the last segment, `await pipeline.finish(ref)`
RFinish(r) ==
    /\ rp[r] = "next" /\ cur = r /\ rsegs[r] = 0
    /\ rp' = [rp EXCEPT ![r] = "fin_wait"]
    /\ rw' = [rw EXCEPT ![r] = [s |-> r, i |-> FinIdx(r)]]
    /\ ftasks' = FinFtasks(r) /\ fin' = FinFin(r)
    /\ UNCHANGED <<gen, cur, nruns, rsegs, sgen, alerted, lock, tasks, op, ops, log, delivered>>

\* pipeline.process: dropped when finished
RDrop(r) ==
    /\ rp[r] = "next" /\ cur = r /\ rsegs[r] > 0 /\ fin[r]
    /\ rsegs' = [rsegs EXCEPT ![r] = @ - 1]
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, sgen, fin, alerted, lock, ftasks, tasks, op, ops, log, delivered>>

\* The rules may or may not decide the (single) alert on this segment.
Decide(r, l) ==
    \E a \in BOOLEAN :
        IF a /\ ~alerted[r]
        THEN /\ alerted' = [alerted EXCEPT ![r] = TRUE]
             /\ log' = Emit(l, "decision", r)
             /\ tasks' = Append(tasks, NewTask(r, "A"))                    \* _queue_send
        ELSE /\ UNCHANGED <<alerted, tasks>> /\ log' = l

\* arm B: process() runs start to finish without awaiting
RProcessB(r) ==
    /\ Arm = "B" /\ rp[r] = "next" /\ cur = r /\ rsegs[r] > 0 /\ ~fin[r]
    /\ rsegs' = [rsegs EXCEPT ![r] = @ - 1]
    /\ Decide(r, Emit(log, "segment", r))
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, sgen, fin, lock, ftasks, op, ops, delivered>>

\* arm C: emit the segment, take the lock, evaluate in a thread
RProcessC(r) ==
    /\ Arm = "C" /\ rp[r] = "next" /\ cur = r /\ rsegs[r] > 0 /\ ~fin[r] /\ ~lock[r]
    /\ lock' = [lock EXCEPT ![r] = TRUE]
    /\ rp' = [rp EXCEPT ![r] = "eval"]
    /\ log' = Emit(log, "segment", r)
    /\ UNCHANGED <<gen, cur, nruns, rw, rsegs, sgen, fin, alerted, ftasks, tasks, op, ops, delivered>>

\* arm C: back on the loop after the thread; `if not _live(...): return []`
REvalDone(r) ==
    /\ rp[r] = "eval"
    /\ lock' = [lock EXCEPT ![r] = FALSE]
    /\ rp' = [rp EXCEPT ![r] = "next"]
    /\ rsegs' = [rsegs EXCEPT ![r] = @ - 1]
    /\ IF Live(r) THEN Decide(r, log) ELSE UNCHANGED <<alerted, tasks, log>>
    /\ UNCHANGED <<gen, cur, nruns, rw, sgen, fin, ftasks, op, ops, delivered>>

RFinWaitDone(r) ==
    /\ rp[r] = "fin_wait" /\ FinDone(rw[r])
    /\ rp' = [rp EXCEPT ![r] = "end"]
    /\ UNCHANGED <<gen, cur, nruns, rw, rsegs, sgen, fin, alerted, lock, ftasks, tasks, op, ops, log, delivered>>

\* --- finish task (pipeline._finish) -------------------------------------------------

FSet(s, i, f) == ftasks' = [ftasks EXCEPT ![s][i] = f]

FLock(s, i) ==
    /\ ftasks[s][i].pc = "lock"
    /\ FinishLock => ~lock[s]
    /\ FSet(s, i, [pc |-> "drain", fu |-> 0,
                   snap |-> {t \in DOMAIN tasks : tasks[t].s = s /\ tasks[t].pc # "done"}])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, tasks, op, ops, log, delivered>>

FDrain(s, i) ==                                                   \* asyncio.gather(*s.tasks)
    /\ ftasks[s][i].pc = "drain"
    /\ \A t \in ftasks[s][i].snap : tasks[t].pc = "done"
    /\ FSet(s, i, [ftasks[s][i] EXCEPT !.pc = "check"])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, tasks, op, ops, log, delivered>>

FCheck(s, i) ==
    /\ ftasks[s][i].pc = "check"
    /\ IF ~Live(s)
       THEN FSet(s, i, [ftasks[s][i] EXCEPT !.pc = "done"]) /\ UNCHANGED <<tasks, log>>
       ELSE IF alerted[s]
            THEN /\ tasks' = Append(tasks, NewTask(s, "F"))          \* follow-up
                 /\ FSet(s, i, [ftasks[s][i] EXCEPT !.pc = "fu", !.fu = Len(tasks) + 1])
                 /\ UNCHANGED log
            ELSE /\ log' = Emit(log, "finished", s)
                 /\ FSet(s, i, [ftasks[s][i] EXCEPT !.pc = "done"])
                 /\ UNCHANGED tasks
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, op, ops, delivered>>

FFollowupDone(s, i) ==
    /\ ftasks[s][i].pc = "fu" /\ tasks[ftasks[s][i].fu].pc = "done"
    /\ log' = Emit(log, "finished", s)
    /\ FSet(s, i, [ftasks[s][i] EXCEPT !.pc = "done"])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, tasks, op, ops, delivered>>

\* --- SMS send task (pipeline._send) -----------------------------------------------

TSet(t, f) == tasks' = [tasks EXCEPT ![t] = f]

TStart(t) ==                                                      \* await asyncio.to_thread(send_if_live)
    /\ tasks[t].pc = "queued"
    /\ TSet(t, [tasks[t] EXCEPT !.pc = "thread", !.th = "check"])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, ftasks, op, ops, log, delivered>>

TCheck(t) ==                                                      \* worker thread: `if not _live(...)`
    /\ tasks[t].th = "check"
    /\ TSet(t, [tasks[t] EXCEPT !.checked = gen,
                                !.th = IF ThreadRecheck /\ ~Live(tasks[t].s) THEN "none" ELSE "send"])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, ftasks, op, ops, log, delivered>>

TSend(t) ==                                                       \* worker thread: gateway.send(...)
    /\ tasks[t].th = "send"
    /\ delivered' = Append(delivered, [s |-> tasks[t].s, tmpl |-> tasks[t].tmpl, sgen |-> sgen[tasks[t].s],
                                       gen |-> gen, checked |-> tasks[t].checked])
    /\ TSet(t, [tasks[t] EXCEPT !.th = "id"])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, ftasks, op, ops, log>>

TResume(t) ==                                                     \* back on the loop
    /\ tasks[t].pc = "thread" /\ tasks[t].th \in {"none", "id"}
    /\ log' = IF tasks[t].th = "id" THEN Emit(log, "sms", tasks[t].s) ELSE log
    /\ TSet(t, [tasks[t] EXCEPT !.pc = "done"])
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, ftasks, op, ops, delivered>>

\* --- operator routes (api/demo.py), one request in flight -----------------------

OpRun ==                                                          \* POST /demo/run/{id}
    /\ op.pc = "idle" /\ ops < MaxOps /\ nruns < MaxRuns
    /\ ops' = ops + 1 /\ nruns' = nruns + 1
    /\ rp' = [CancelRp EXCEPT ![nruns + 1] = "start"]
    /\ lock' = CancelLock
    /\ UNCHANGED <<gen, cur, rw, rsegs, sgen, fin, alerted, ftasks, tasks, op, log, delivered>>

OpEnd ==                                                          \* POST /demo/end-call
    /\ op.pc = "idle" /\ ops < MaxOps
    /\ ops' = ops + 1
    /\ rp' = CancelRp /\ lock' = CancelLock
    /\ op' = [kind |-> "end", pc |-> IF cur # 0 THEN "wait" ELSE "idle", s |-> cur, i |-> IF cur # 0 THEN FinIdx(cur) ELSE 0]
    /\ ftasks' = IF cur # 0 THEN FinFtasks(cur) ELSE ftasks
    /\ fin' = IF cur # 0 THEN FinFin(cur) ELSE fin
    /\ UNCHANGED <<gen, cur, nruns, rw, rsegs, sgen, alerted, tasks, log, delivered>>

OpEndDone ==
    /\ op.pc = "wait" /\ FinDone(op)
    /\ op' = [op EXCEPT !.pc = "idle"]
    /\ UNCHANGED <<gen, cur, nruns, rp, rw, rsegs, sgen, fin, alerted, lock, ftasks, tasks, ops, log, delivered>>

OpReset ==                                                        \* POST /demo/reset (atomic: no await inside)
    /\ op.pc = "idle" /\ ops < MaxOps
    /\ ops' = ops + 1
    /\ rp' = CancelRp /\ lock' = CancelLock
    /\ gen' = gen + 1 /\ cur' = 0
    /\ tasks' = [t \in DOMAIN tasks |->                           \* task.cancel(); threads keep running
                   IF tasks[t].s = cur /\ tasks[t].pc \in {"queued", "thread"}
                   THEN [tasks[t] EXCEPT !.pc = "done"] ELSE tasks[t]]
    /\ UNCHANGED <<nruns, rw, rsegs, sgen, fin, alerted, ftasks, op, log, delivered>>

Terminated ==
    /\ \A r \in Runs : rp[r] \in {"idle", "end"}
    /\ \A s \in Runs : \A i \in DOMAIN ftasks[s] : ftasks[s][i].pc = "done"
    /\ \A t \in DOMAIN tasks : tasks[t].pc = "done" /\ tasks[t].th \in {"idle", "none", "id"}
    /\ op.pc = "idle"

Next ==
    \/ \E r \in Runs : \/ RStartFinish(r) \/ RStartCreate(r) \/ RStop(r) \/ RFinish(r) \/ RDrop(r)
                       \/ RProcessB(r) \/ RProcessC(r) \/ REvalDone(r) \/ RFinWaitDone(r)
    \/ \E s \in Runs : \E i \in DOMAIN ftasks[s] :
           FLock(s, i) \/ FDrain(s, i) \/ FCheck(s, i) \/ FFollowupDone(s, i)
    \/ \E t \in DOMAIN tasks : TStart(t) \/ TCheck(t) \/ TSend(t) \/ TResume(t)
    \/ OpRun \/ OpEnd \/ OpEndDone \/ OpReset
    \/ Terminated /\ UNCHANGED vars

Spec == Init /\ [][Next]_vars

\* --- properties ------------------------------------------------------------------

\* PRD 19.10: "anything from an old generation is dropped and never sends SMS".
NoStaleSend == \A k \in DOMAIN delivered : delivered[k].sgen = delivered[k].gen

\* What the thread re-check does guarantee: a send only reaches the gateway if its
\* session was live when the worker thread checked.
SendStartsLive == \A k \in DOMAIN delivered : delivered[k].checked = delivered[k].sgen

\* pipeline.finish docstring: "at most one follow-up".
AtMostOneFollowup == \A s \in Runs :
    Cardinality({t \in DOMAIN tasks : tasks[t].s = s /\ tasks[t].tmpl = "F"}) <= 1

\* One "finished" per session; nothing published for a session after it went stale.
FinishedOnce == \A s \in Runs : Cardinality({k \in DOMAIN log : log[k].s = s /\ log[k].type = "finished"}) <= 1
NoStaleEvent == \A k \in DOMAIN log : log[k].live

\* The follow-up goes out after the alert, and no alert is decided after "finished".
FollowupAfterAlert == \A j, k \in DOMAIN delivered :
    (delivered[j].s = delivered[k].s /\ delivered[j].tmpl = "F" /\ delivered[k].tmpl = "A") => k < j
NoAlertAfterFinished == \A j, k \in DOMAIN log :
    (log[j].s = log[k].s /\ log[j].type = "finished" /\ log[k].type = "decision") => k < j
=============================================================================
