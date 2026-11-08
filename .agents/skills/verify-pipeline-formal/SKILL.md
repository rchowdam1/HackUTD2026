---
name: verify-pipeline-formal
description: "Model-check Safe Signal's call-session lifecycle (backend/app/pipeline.py with ingest replay and the /demo routes) in TLA+/TLC: stale-generation SMS sends, one follow-up per call, no events after reset, alert/follow-up ordering. Use when a change touches pipeline.py, ingest/__init__.py or api/demo.py, or when asked whether Reset / End call / Run races are safe."
---

# Verify the pipeline's ordering guarantees

Reset, End call, Run and the replay's own auto-finish can interleave with SMS sends that run in worker threads. Tests hit a few orders; this check explores every order in a bounded model. One command, ~5 s:

```bash
make verify-formal                                   # all configs
.agents/skills/verify-pipeline-formal/scripts/check.sh arm-b prd-no-stale-send   # some
```

It downloads `tla2tools.jar` v1.8.0 once into `.verify/tools/` (sha256-pinned), needs Java 11+, and writes TLC logs (with counterexample traces) to `.verify/formal/<timestamp>/`. Exit 0 only if every config produced the outcome in `checks/expectations.tsv`; missing Java or a failed download prints `BLOCKED` and exits 2.

## What is checked

The model is `model/Pipeline.tla`. Each action is the code between two `await`s, because the asyncio loop runs one coroutine at a time; the worker thread's live check (`TCheck`) and the gateway call (`TSend`) are separate steps because they run off the loop.

| Property | Plain statement | Harm if broken |
|---|---|---|
| `NoStaleSend` | No SMS reaches the gateway for a call that was reset (PRD §19.10). | The phone buzzes after the operator pressed Reset. |
| `SendStartsLive` | A send only reaches the gateway if its call was live when the worker thread checked. | Reset would not stop queued alerts at all. |
| `AtMostOneFollowup` | A call gets at most one follow-up, however many finish() calls race. | Duplicate follow-up texts. |
| `FinishedOnce` | One "finished" event per call. | Console flips state twice. |
| `NoStaleEvent` | Nothing is published for a call after it went stale. | Old transcript/alerts appear after Reset. |
| `FollowupAfterAlert` | The follow-up goes out after the alert. | Out-of-order texts. |
| `NoAlertAfterFinished` | No alert is decided after the call's "finished" event. | An alert with no follow-up after the call ended. |

Bounds and assumptions: 2 segments per replay, 2 replays, 2 operator requests (one in flight), arm B or C, one alert category, consent always active, the gateway never raises, rule outcomes nondeterministic per segment. A pass covers these bounds only.

| Config | Checks | Expected |
|---|---|---|
| `arm-b`, `arm-c` | all properties except `NoStaleSend`, real code | pass |
| `prd-no-stale-send` | `NoStaleSend`, real code | **violation** (finding below) |
| `broken-finish-guard` | `finish()` without the `finish_task is None` guard | violation of `AtMostOneFollowup` |
| `broken-emit-guard` | `_emit()` without `_live()` | violation of `NoStaleEvent` |
| `broken-thread-recheck` | `send_if_live()` without its re-check | violation of `SendStartsLive` |
| `broken-finish-lock` | `_finish()` without `async with s.lock`, arm C | pass (see below) |

The `broken-*` configs prove each property can fail: each flips one guard constant that mirrors one line of code.

## Findings at the sync commit

- **Reset can't stop an SMS that is already being sent (`NoStaleSend` violated).** Counterexample: the bank alert is queued; its worker thread runs `send_if_live`, sees the call live; the operator presses Reset (generation 1 → 2, task cancelled, but cancelling doesn't stop the thread); the thread calls `gateway.send(...)` and the alert goes out for a reset call. The window is from the thread's `_live` check through the consent lookup and the Twilio HTTP request (milliseconds to a few hundred ms). PRD §19.10's "never sends SMS" is stronger than the code can promise; what holds is `SendStartsLive`. Either the PRD wording or the design (e.g. a cancellable send) should change; this is a product decision, not a verification fix.
- **The arm C lock in `_finish` is not load-bearing today.** With the lock removed, `NoAlertAfterFinished` still holds, because every route that finishes a call (`/demo/end-call`, `/demo/run`, `/demo/reset`) cancels the replay first, which drops an in-flight arm C evaluation. The lock would matter for a caller that runs `pipeline.finish` while `process` is evaluating without cancelling; keep it, but don't rely on it as the guard.

## Coverage record

- `backend/app/pipeline.py`: `_live`, `_emit`, `start`, `process`, `_evaluate`, `_queue_send`, `_send` (`send_if_live`), `finish`, `_finish`, `reset`.
- `backend/app/ingest/__init__.py`: `replay_transcript` loop (`_alive` checks, final `finish`), `run` (cached path).
- `backend/app/api/demo.py`: `run`, `end_call`, `reset`, `_cancel_replay`.
- Not covered: `sms` gateway internals and consent, ASR replay timing, `events.Hub` back-pressure, rule correctness (tests/rules, verify-app).
- **Sync commit: `fefb2d3`** (origin/main, 2026-11-07). The model describes the covered code at this commit.

## When code changes

1. `git diff fefb2d3..HEAD -- backend/app/pipeline.py backend/app/ingest/__init__.py backend/app/api/demo.py`. Empty → run `make verify-formal`; done. Also look for new code that writes `_generation`, `_session`, `s.tasks`, `s.finish_task` or calls `pipeline.finish/reset` from a new route.
2. For each change decide: no effect on the model; the model no longer describes the code (an `await` added or removed splits or merges an action; a new caller; a new guard); or the promise changed on purpose (cite the commit message, docstring or test).
3. Update `model/Pipeline.tla` from the code first, keeping one action per await-free stretch, then rerun. Don't shape the model to make a check pass, and don't drop a property or shrink a bound without saying so.
4. Judge each result. Pass → re-run the `broken-*` config that guards the changed code to show the check can still fail. Violation → replay the TLC trace (`.verify/formal/<ts>/<cfg>.log`, "State 1..n") against the code step by step. A step the code can't take = model bug (fix the model, say what was wrong). Every step possible = code bug (report the steps in code terms and the commit that introduced it; don't fix product code unless asked).
5. Update the findings, coverage record and expectations, then move the sync commit to the commit you checked. Never move it for a check you couldn't run.

The `maintain-verification` skill runs this procedure as part of its pass. If the pstack `statechart` skill is available in your harness, use it to read TLC traces as plain-language state paths.
