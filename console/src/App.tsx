import { Fragment, useCallback, useEffect, useReducer, useRef, useState } from "react";
import * as api from "./api";
import OptInPrompt from "./OptInPrompt";
import { initial, reduce, type Action, type Bubble, type State } from "./state";
import type { ArmCounts, Event, Results, RiskEvent, Segment, SmsPayload } from "./types";

const FIXTURES = new URLSearchParams(location.search).has("fixtures");
// Live transcript typing speed. Must match WORD_MS in backend/app/ingest/__init__.py (cached replay pacing).
const WORD_MS = 100;
const words = (text: string) => text.split(/\s+/).filter(Boolean);
const segKey = (s: Segment) => `${s.session_ref}:${s.seq}`;

const CATEGORY_WORDS: Record<RiskEvent["category"], string> = {
  otp: "Caller asked for a code",
  payment: "Caller asked for money",
  remote: "Caller asked for access to the device",
};
const DISPATCH_WORDS: Record<SmsPayload["status"], string> = {
  queued: "Alert text queued",
  sent: "Alert text sent",
  delivered: "Alert text delivered",
  failed: "Warning detected but the alert text was NOT sent (failed)",
};
const ARM_NAMES: Record<string, string> = { K: "Keyword only (K)", B: "CallSafe rules (B)", C: "Rules + intent model (C)" };
const MARKER_WORDS: [string, string][] = [
  ["ALERT-", "Alert message sent to user"],
  ["FU-", "Follow-up message sent to user"],
];
const CONFIDENCE_WORDS: Record<RiskEvent["confidence_class"], string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(FIXTURES ? true : null);
  const [note, setNote] = useState<string | null>(null);
  const [askOptIn, setAskOptIn] = useState(false); // set on every login, never stored
  useEffect(() => {
    if (!FIXTURES) api.loggedIn().then(setAuthed, () => setAuthed(false));
  }, []);
  const loggedOut = useCallback((why: string | null) => {
    setNote(why);
    setAuthed(false);
  }, []);
  if (authed === null) return null;
  if (!authed) {
    return (
      <Login
        note={note}
        onLogin={() => {
          setAskOptIn(true);
          setAuthed(true);
        }}
      />
    );
  }
  return (
    <>
      <Console onLoggedOut={loggedOut} />
      {askOptIn && <OptInPrompt onDone={() => setAskOptIn(false)} />}
    </>
  );
}

function Login({ note, onLogin }: { note: string | null; onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="login"
      onSubmit={async (e) => {
        e.preventDefault();
        const err = await api.login(password);
        err === null ? onLogin() : setError(err);
      }}
    >
      <h1>CallSafe</h1>
      <input type="password" placeholder="Operator password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
      <button type="submit">Log in</button>
      {error ? <p className="error">{error}</p> : note && <p className="muted">{note}</p>}
    </form>
  );
}

function Console({ onLoggedOut }: { onLoggedOut: (why: string | null) => void }) {
  const [state, dispatch] = useReducer(reduce, initial);
  const [results, setResults] = useState<Results>({ status: "pending" });
  const [stream, setStream] = useState<"connecting" | "live" | "stale">(FIXTURES ? "live" : "connecting");
  const [error, setError] = useState<string | null>(null);
  const live = useRef(new Set<string>()); // segments that arrived over the stream type out; hydrated ones don't

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 8000);
    return () => clearTimeout(t);
  }, [error]);

  useEffect(() => {
    if (FIXTURES) return api.replayFixtures(dispatch);
    api.onFailure({ unauthorized: () => onLoggedOut("Session expired, log in again"), error: setError });
    api.results().then(setResults);
    const timer = setInterval(() => api.results().then(setResults), 30_000);
    // On every (re)open: buffer live events, rebuild from GET /state, then replay the buffer (deduped).
    let buffer: Event[] | null = null;
    let generation = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    // Hold each live event until the line before it has finished typing, so an alert never shows before its words.
    let gate = 0;
    const held = new Set<ReturnType<typeof setTimeout>>();
    const paced = (e: Event) => {
      const wait = gate - Date.now();
      if (e.type === "segment") gate = Math.max(gate, Date.now()) + words(e.payload.text).length * WORD_MS;
      const run = () => {
        if (e.type === "segment") live.current.add(segKey(e.payload));
        dispatch(e);
      };
      if (wait <= 0) return run();
      const t = setTimeout(() => {
        held.delete(t);
        run();
      }, wait);
      held.add(t);
    };
    const sync = async (gen: number) => {
      const snap = await api.snapshot();
      if (gen !== generation) return;
      if (!snap) {
        retry = setTimeout(() => sync(gen), 3000);
        return;
      }
      dispatch({ type: "hydrate", snapshot: snap, after: buffer ?? [] });
      buffer = null;
      setStream("live");
    };
    const unsubscribe = api.subscribe({
      event: (e) => (buffer ? buffer.push(e) : paced(e)),
      open: () => {
        buffer = [];
        clearTimeout(retry);
        sync(++generation);
      },
      error: (closed) => {
        generation++;
        clearTimeout(retry);
        setStream("stale");
        if (closed) api.snapshot(); // EventSource gave up on an HTTP error; a 401 here returns to login
      },
    });
    return () => {
      generation++;
      clearTimeout(retry);
      held.forEach(clearTimeout);
      clearInterval(timer);
      unsubscribe();
    };
  }, [onLoggedOut]);

  return (
    <div className="console">
      <header>
        <h1>CallSafe</h1>
        <span className="tag">replayed call through the live ingestion path</span>
        {FIXTURES && <span className="tag warn">fixture replay</span>}
        {stream === "connecting" && <span className="tag">connecting…</span>}
        {stream === "stale" && <span className="tag stale">disconnected / reconnecting — view may be stale</span>}
        <span className="status">{sessionLabel(state)}</span>
        {!FIXTURES && (
          <button onClick={async () => (await api.logout()) && onLoggedOut(null)}>Log out</button>
        )}
      </header>
      {error && (
        <p className="action-error" role="alert">
          {error} <button onClick={() => setError(null)}>Dismiss</button>
        </p>
      )}
      <Controls state={state} dispatch={dispatch} />
      <main>
        <Transcript state={state} live={live.current} />
        <aside>
          <WhyPanel state={state} />
          <div className="card counter">
            <h2>WRONG replies</h2>
            <div className="big">{state.wrongCount}</div>
          </div>
          <Phone bubbles={state.bubbles} simulated={state.smsMode === "simulated"} off={monitoringOff(state)} />
        </aside>
      </main>
      <footer>
        <ResultsCard results={results} />
        <WhereWeFail results={results} />
      </footer>
    </div>
  );
}

function sessionLabel(s: State): string {
  if (!s.session) return "idle";
  if (s.session.state === "running") return `call running · arm ${s.session.arm}`;
  return s.session.state === "finished" ? "call ended" : "reset";
}

function Controls({ state, dispatch }: { state: State; dispatch: (a: Action) => void }) {
  const mode = state.smsMode;
  return (
    <nav className="controls">
      <button disabled={FIXTURES} onClick={() => api.runScenario("clinic")}>Run clinic</button>
      <button disabled={FIXTURES} onClick={() => api.runScenario("bank")}>Run bank</button>
      <button disabled={FIXTURES} onClick={() => api.endCall()}>End call</button>
      <button disabled={FIXTURES} className="danger" onClick={() => api.reset()}>Reset</button>
      <span className="spacer" />
      <span>SMS mode</span>
      {(["real", "simulated"] as const).map((m) => (
        <button
          key={m}
          disabled={FIXTURES}
          className={mode === m ? "on" : ""}
          onClick={async () => {
            if (await api.setSmsMode(m)) dispatch({ type: "sms_mode", mode: m });
          }}
        >
          {m}
        </button>
      ))}
    </nav>
  );
}

function Transcript({ state, live }: { state: State; live: Set<string> }) {
  const flagged = new Set(state.risks.flatMap((r) => r.span_seq));
  const cached = state.segments.some((s) => s.source === "cached");
  // A marker for each alert / follow-up text, right after the line that was last when it was sent.
  const markers = state.bubbles.flatMap((b) => {
    const words = b.kind === "out" && b.sms.status !== "failed" && MARKER_WORDS.find(([p]) => b.sms.template_id.startsWith(p));
    return b.kind === "out" && words ? [{ afterSeq: b.afterSeq, id: b.sms.message_id, text: words[1] }] : [];
  });
  return (
    <section className="card transcript">
      <h2>
        Live transcript {cached && <span className="tag">cached transcript</span>}
      </h2>
      {state.segments.length === 0 && <p className="muted">No call yet.</p>}
      {state.segments.map((s) => (
        <Fragment key={segKey(s)}>
          <p className={`line ${s.speaker} ${flagged.has(s.seq) ? "flagged" : ""}`}>
            <span className="who">{s.speaker === "caller" ? "Caller" : "You"}</span>
            <TypedText text={s.text} animate={live.has(segKey(s))} />
          </p>
          {markers
            .filter((m) => m.afterSeq === s.seq)
            .map((m) => (
              <p key={m.id} className="line marker">
                * {m.text}
              </p>
            ))}
        </Fragment>
      ))}
    </section>
  );
}

// Reveals a line one word per WORD_MS, like a streamed chat reply. Words shown are computed from the
// clock, not counted ticks, so throttled timers can't fall behind the event hold in Console.
function TypedText({ text, animate }: { text: string; animate: boolean }) {
  const all = words(text);
  const [start] = useState(() => Date.now());
  const [, tick] = useState(0);
  const shown = animate ? Math.min(all.length, Math.floor((Date.now() - start) / WORD_MS)) : all.length;
  useEffect(() => {
    if (shown >= all.length) return;
    const t = setTimeout(() => tick((n) => n + 1), WORD_MS);
    return () => clearTimeout(t);
  });
  if (shown >= all.length) return <>{text}</>;
  return <span className="typing">{all.slice(0, shown).join(" ")}</span>;
}

function WhyPanel({ state }: { state: State }) {
  const alert = state.decisions.find((d) => d.level === "action_warning");
  if (!alert) {
    return (
      <section className="card why">
        <h2>Why this alert</h2>
        <p className="big-text">{state.session?.state === "finished" ? "No alert - not a safety verdict" : "No alert yet"}</p>
      </section>
    );
  }
  const risk = state.risks.find((r) => r.rule_id && alert.basis.includes(r.rule_id));
  const sms = state.bubbles.find((b) => b.kind === "out" && b.sms.template_id === alert.template_id);
  const status = sms?.kind === "out" ? sms.sms.status : null;
  const optedOut = !sms && monitoringOff(state);
  return (
    <section className="card why alert">
      <h2>Why this alert</h2>
      <p className="big-text">{risk ? CATEGORY_WORDS[risk.category] : alert.template_id}</p>
      <dl>
        <dt>Rule</dt>
        <dd>{alert.basis.join(", ") || "-"}</dd>
        <dt>Confidence</dt>
        <dd>{risk ? CONFIDENCE_WORDS[risk.confidence_class] : "-"}</dd>
        <dt>Keyword-only would have fired</dt>
        <dd>{alert.keyword_arm_would_fire ? "Yes" : "No"}</dd>
        <dt>Policy</dt>
        <dd>{alert.policy_version}</dd>
      </dl>
      <p className={`dispatch ${status ?? ""}`}>
        {optedOut ? "Monitoring opt-in: No. No text sent" : status ? DISPATCH_WORDS[status] : "Alert text not dispatched yet"}
      </p>
    </section>
  );
}

// Consent known and not active: alerts are skipped, not failed. null = not loaded yet (or fixture replay).
const monitoringOff = (s: State) => s.consent !== null && s.consent !== "active";

// Simulated mode: the phone frame with reply keys. Real mode: a compact list of outgoing texts and replies.
function Phone({ bubbles, simulated, off }: { bubbles: Bubble[]; simulated: boolean; off: boolean }) {
  return (
    <section className={`card phone ${simulated ? "" : "compact"}`}>
      <h2>
        {simulated ? "Phone" : "Outgoing texts"} <span className="tag">{simulated ? "simulated SMS" : "real SMS"}</span>
      </h2>
      <div className="thread">
        {off ? <p className="muted">Call monitoring is off.</p> : bubbles.length === 0 && <p className="muted">No texts yet.</p>}
        {bubbles.map((b) =>
          b.kind === "out" ? <OutBubble key={b.sms.message_id || b.sms.template_id} b={b} /> : <div key={b.id} className="bubble in">{b.keyword}</div>,
        )}
      </div>
      {simulated && (
        <div className="keys">
          {["YES", "WRONG", "SHARED", "STOP"].map((k) => (
            <button key={k} disabled={FIXTURES} onClick={() => api.simulateReply(k)}>
              {k}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function OutBubble({ b }: { b: Extract<Bubble, { kind: "out" }> }) {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (!FIXTURES) api.templateText(b.sms.template_id).then(setText);
  }, [b.sms.template_id]);
  return (
    <div className={`bubble out ${b.sms.status}`}>
      {text ?? b.sms.template_id}
      <small>{b.sms.status}</small>
    </div>
  );
}

function ResultsCard({ results }: { results: Results }) {
  if ("status" in results) {
    return (
      <section className="card results">
        <h2>Held-out results</h2>
        <p className="muted">Results pending</p>
      </section>
    );
  }
  const arm = (name: string, c?: ArmCounts) =>
    c && (
      <div className="arm" key={name}>
        <h3>{ARM_NAMES[name] ?? name}</h3>
        <p>
          Hard-benign false alerts: <b>{c.hard_benign_fp} of {c.hard_benign_n}</b>
        </p>
        <p>
          Scam calls caught: <b>{c.TP} of {c.TP + c.FN}</b>
        </p>
      </div>
    );
  return (
    <section className="card results">
      <h2>Held-out results · {results.batch}</h2>
      <div className="arms">{Object.entries(results.arms).map(([n, c]) => arm(n, c))}</div>
      {results.discordant && (
        <p>
          Correct only under K: {results.discordant.K_only} · correct only under B: {results.discordant.B_only}
        </p>
      )}
      <p className="muted">Scripted transcripts, not ASR.</p>
    </section>
  );
}

function WhereWeFail({ results }: { results: Results }) {
  const b = "status" in results ? undefined : results.arms.B;
  return (
    <section className="card fail">
      <h2>Where we fail</h2>
      <ul>
        {b && <li>Missed {b.FN} of {b.TP + b.FN} scam calls on the held-out set.</li>}
        {b && <li>False alerts on {b.FP} of {b.FP + b.TN} benign calls.</li>}
        <li>A request paraphrased with no trigger phrase can slip past the rules.</li>
        <li>Held-out calls are scripted text; speech recognition is only checked on the demo clips.</li>
        <li>Too few calls for a production accuracy claim.</li>
      </ul>
    </section>
  );
}
