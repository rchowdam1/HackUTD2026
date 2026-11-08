import { type ReactNode, useCallback, useEffect, useReducer, useRef, useState } from "react";
import * as api from "./api";
import OptInPrompt from "./OptInPrompt";
import { initial, reduce, type Action, type Bubble, type State } from "./state";
import type { Event, RiskEvent, Segment, SmsPayload } from "./types";

const FIXTURES = new URLSearchParams(location.search).has("fixtures");
// Live transcript typing speed. Must match WORD_MS in backend/app/ingest/__init__.py (cached replay pacing).
const WORD_MS = 100;
const words = (text: string) => text.split(/\s+/).filter(Boolean);
const segKey = (s: Segment) => `${s.session_ref}:${s.seq}`;

const CATEGORY_WORDS: Record<RiskEvent["category"], string> = {
  otp: "Caller asked for a code",
  payment: "Caller asked for money",
  remote: "Caller asked for access to your device",
};
const REQUEST_TAG: Record<RiskEvent["category"], string> = { otp: "Code request", payment: "Money request", remote: "Access request" };
const DANGER_WORDS: Record<RiskEvent["category"], string> = {
  otp: "Whoever has the code can get into your account. Your bank never asks you to read one back.",
  payment: "Money sent this way is almost never recovered. Real organisations let you hang up and call back.",
  remote: "Remote access lets a stranger control your device, including your banking apps.",
};
const STATUS_WORDS: Record<SmsPayload["status"], string> = { queued: "Queued", sent: "Sent", delivered: "Delivered", failed: "Not sent" };
// 30034: carriers block texts from a number not yet registered for US A2P 10DLC (our number today).
const CARRIER_BLOCKED = "30034";
function statusWords(sms: SmsPayload): string {
  if (sms.status !== "failed" || !sms.error_code) return STATUS_WORDS[sms.status];
  if (sms.error_code === CARRIER_BLOCKED) return "Not delivered: carrier blocked (Twilio 30034, number not registered yet)";
  return `Not delivered (Twilio ${sms.error_code})`;
}
// The transcript note under the line an alert / follow-up text went out after.
const MARKER_WORDS: [string, string][] = [
  ["ALERT-", "Alert text"],
  ["FU-", "Follow-up text"],
];
const MARKER_STATUS: Record<SmsPayload["status"], string> = { queued: "sent", sent: "sent", delivered: "delivered", failed: "not delivered" };
// The intent model behind arm C: app.intent.MODEL (perplexity/pplx-decider-v1.2-20261016).
const MODEL_NAME = "Perplexity Decider";
const ARM_WORDS: Record<string, string> = { K: "keywords only", B: "rules only", C: `rules + AI (${MODEL_NAME})` };
const DETECTOR_WORDS: Record<string, string> = { K: "Keywords only", B: "CallSafe rules", C: `Rules + ${MODEL_NAME}` };
const SCENARIO_WORDS: Record<string, string> = { bank: "Bank", clinic: "Clinic", family: "Grandson" };

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
  const optInDone = useCallback(() => setAskOptIn(false), []);
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
  return <Console onLoggedOut={loggedOut} askOptIn={askOptIn} onOptInDone={optInDone} />;
}

function Login({ note, onLogin }: { note: string | null; onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <main className="login-page">
      <form
        className="login"
        onSubmit={async (e) => {
          e.preventDefault();
          const err = await api.login(password);
          err === null ? onLogin() : setError(err);
        }}
      >
        <p className="wordmark">CallSafe</p>
        <h1 className="headline">Operator console</h1>
        <label className="label" htmlFor="password">
          Password
        </label>
        <div className="field">
          <input
            id="password"
            type={show ? "text" : "password"}
            placeholder="Operator password"
            autoComplete="current-password"
            aria-describedby="password-help"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
          <button type="button" className="text-button" aria-pressed={show} onClick={() => setShow(!show)}>
            Show
          </button>
        </div>
        <p id="password-help" className={error ? "help error" : "help"} role={error ? "alert" : undefined}>
          {error ?? note ?? "The demo team's shared password."}
        </p>
        <button type="submit" className="primary">
          Log in
        </button>
      </form>
    </main>
  );
}

function Console({ onLoggedOut, askOptIn, onOptInDone }: { onLoggedOut: (why: string | null) => void; askOptIn: boolean; onOptInDone: () => void }) {
  const [state, dispatch] = useReducer(reduce, initial);
  const [stream, setStream] = useState<"connecting" | "live" | "stale">(FIXTURES ? "live" : "connecting");
  const [error, setError] = useState<string | null>(null);
  const live = useRef(new Set<string>()); // segments that arrived over the stream type out; hydrated ones don't
  const arrived = useRef(new Map<string, number>()); // receive time per segment / sms, before the typing hold

  // Ask once per login, and only when the snapshot says the demo phone isn't opted in yet.
  const hydrated = stream === "live";
  useEffect(() => {
    if (askOptIn && hydrated && state.consent === "active") onOptInDone();
  }, [askOptIn, hydrated, state.consent, onOptInDone]);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 8000);
    return () => clearTimeout(t);
  }, [error]);

  useEffect(() => {
    if (FIXTURES) return api.replayFixtures(dispatch);
    api.onFailure({ unauthorized: () => onLoggedOut("Session expired, log in again"), error: setError });
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
      event: (e) => {
        const key = e.type === "segment" ? segKey(e.payload) : e.type === "sms" ? e.payload.message_id : null;
        if (key && !arrived.current.has(key)) arrived.current.set(key, Date.now());
        return buffer ? buffer.push(e) : paced(e);
      },
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
      unsubscribe();
    };
  }, [onLoggedOut]);

  return (
    <div className="console">
      <header className="topbar">
        <p className="wordmark">CallSafe</p>
        <span className="status" aria-live="polite">
          {sessionLabel(state)}
        </span>
        {FIXTURES && <span className="tag warn">fixture replay</span>}
        {stream === "connecting" && <span className="tag">connecting…</span>}
        {stream === "stale" && <span className="tag stale">disconnected / reconnecting — view may be stale</span>}
        <span className="spacer" />
        {!FIXTURES && <Monitoring consent={state.consent} />}
        {!FIXTURES && (
          <button className="secondary" onClick={async () => (await api.logout()) && onLoggedOut(null)}>
            Log out
          </button>
        )}
      </header>
      {error && (
        <p className="action-error" role="alert">
          {error} <button className="text-button" onClick={() => setError(null)}>Dismiss</button>
        </p>
      )}
      <main className="band">
        <div className="col left">
          <CallClock state={state} />
          <Controls state={state} dispatch={dispatch} />
        </div>
        <div className="col centre">
          <Verdict state={state} />
          <Transcript state={state} live={live.current} />
        </div>
        <div className="col right">
          <WhyPanel state={state} arrived={arrived.current} />
          <Phone bubbles={state.bubbles} simulated={state.smsMode === "simulated"} off={monitoringOff(state)} />
        </div>
      </main>
      {askOptIn && hydrated && state.consent !== "active" && <OptInPrompt onDone={onOptInDone} />}
    </div>
  );
}

// Always visible, so monitoring can be switched on in one click whatever was answered at login.
function Monitoring({ consent }: { consent: State["consent"] }) {
  if (consent === null) return null;
  if (consent === "active") {
    return (
      <span className="monitoring on">
        <span className="dot" aria-hidden="true" />
        Monitoring on
      </span>
    );
  }
  return (
    <span className="monitoring">
      <span className="dot hollow" aria-hidden="true" />
      Monitoring off · <button className="text-button" onClick={() => api.setOptIn(true)}>Turn on</button>
    </span>
  );
}

function sessionLabel(s: State): string {
  if (!s.session) return "idle";
  if (s.session.state === "running") return `call running · ${ARM_WORDS[s.session.arm ?? ""] ?? s.session.arm}`;
  return s.session.state === "finished" ? "call ended" : "reset";
}

function sourceWords(source: string | null | undefined): string {
  if (!source) return "Call";
  if (source.startsWith("replay:")) {
    const id = source.slice("replay:".length);
    return `${SCENARIO_WORDS[id] ?? id} call replay`;
  }
  return source === "phone" ? "Phone call" : source === "mic" ? "Live mic call" : source;
}

const clockText = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

// Counts up while a call runs and holds its length once it ends. A call already running when the page
// loaded starts from its last line's end time, the best the snapshot can tell.
function CallClock({ state }: { state: State }) {
  const [clock, setClock] = useState<{ ref: string | null; start: number; end: number | null } | null>(null);
  const [, tick] = useState(0);
  const session = state.session;
  useEffect(() => {
    if (!session || session.state === "reset") return setClock(null);
    const now = Date.now();
    setClock((c) => {
      if (c && c.ref === state.sessionRef) return session.state === "finished" && c.end === null ? { ...c, end: now } : c;
      const last = state.segments[state.segments.length - 1];
      return { ref: state.sessionRef, start: now - (last?.t_end_ms ?? 0), end: session.state === "finished" ? now : null };
    });
  }, [session, state.sessionRef]); // segments only matter when a new session is first seen
  const running = clock !== null && clock.end === null;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => tick((n) => n + 1), 250);
    return () => clearInterval(t);
  }, [running]);
  const ms = clock ? (clock.end ?? Date.now()) - clock.start : 0;
  const status = !session || session.state === "reset" ? "Ready" : session.state === "running" ? "Live" : "Ended";
  return (
    <section className="card clock" aria-labelledby="clock-label">
      <h2 className="label" id="clock-label">
        <span>Call time</span>
        <span className="meta">
          <span className={`dot ${running ? "live" : "hollow"}`} aria-hidden="true" />
          {status}
        </span>
      </h2>
      <p className="hero" aria-label={`Call time ${clockText(ms)}`}>
        {clockText(ms)}
      </p>
      <p className="source">{session && session.state !== "reset" ? sourceWords(session.source) : "No call running"}</p>
      {session?.arm && session.state !== "reset" && <p className="arm">{DETECTOR_WORDS[session.arm] ?? session.arm}</p>}
    </section>
  );
}

function ControlRow({ label, hint, icon, className, onClick }: { label: string; hint: string; icon: string; className?: string; onClick: () => void }) {
  const id = `hint-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <li>
      <button className={`row ${className ?? ""}`} disabled={FIXTURES} aria-describedby={id} onClick={onClick}>
        <span className="icon" aria-hidden="true">
          {icon}
        </span>
        <span className="row-label">{label}</span>
        {/* hidden from the name (checks and screen readers find "Run bank"), still read as the description */}
        <span className="hint" id={id} aria-hidden="true">
          {hint}
        </span>
      </button>
    </li>
  );
}

function Controls({ state, dispatch }: { state: State; dispatch: (a: Action) => void }) {
  const mode = state.smsMode;
  return (
    <section className="card controls" aria-labelledby="controls-label">
      <h2 className="label" id="controls-label">
        <span>Controls</span>
      </h2>
      <ul className="rows">
        <ControlRow label="Run clinic" hint="harmless" icon="▶" onClick={() => api.runScenario("clinic")} />
        <ControlRow label="Run bank" hint="asks for a code" icon="▶" className="primary-row" onClick={() => api.runScenario("bank")} />
        <ControlRow label="Run grandson" hint="asks for money" icon="▶" onClick={() => api.runScenario("family")} />
        <ControlRow label="End call" hint="hang up" icon="■" onClick={() => api.endCall()} />
        <ControlRow label="Reset" hint="clear screen" icon="↺" className="danger" onClick={() => api.reset()} />
      </ul>
      <div className="toggle" role="group" aria-labelledby="sms-mode-label">
        <span className="label-text" id="sms-mode-label">
          SMS mode
        </span>
        {(["real", "simulated"] as const).map((m) => (
          <button
            key={m}
            disabled={FIXTURES}
            className={`pill ${mode === m ? "on" : ""}`}
            aria-pressed={mode === m}
            onClick={async () => {
              if (await api.setSmsMode(m)) dispatch({ type: "sms_mode", mode: m });
            }}
          >
            {m}
          </button>
        ))}
      </div>
    </section>
  );
}

// The risk event behind the first alert (its rule id is in the decision's basis), or null.
function alertRisk(state: State): RiskEvent | null {
  const alert = state.decisions.find((d) => d.level === "action_warning");
  return (alert && state.risks.find((r) => r.rule_id && alert.basis.includes(r.rule_id))) || null;
}

function Verdict({ state }: { state: State }) {
  const alerted = state.decisions.some((d) => d.level === "action_warning");
  const risk = alertRisk(state);
  const finished = state.session?.state === "finished";
  return (
    <section className="card verdict" aria-labelledby="verdict-label">
      <h2 className="label" id="verdict-label">
        <span>Verdict</span>
      </h2>
      <p className={`headline ${alerted ? "alerted" : ""}`} aria-live="polite">
        {alerted ? (risk ? CATEGORY_WORDS[risk.category] : "Alert") : finished ? "No alert" : "No alert yet"}
      </p>
      {!alerted && <p className="aside">not a safety verdict</p>}
    </section>
  );
}

function Transcript({ state, live }: { state: State; live: Set<string> }) {
  // The line that carried the request (the Why panel quotes the same one).
  const flaggedAt = new Map(state.risks.map((r) => [r.span_seq[r.span_seq.length - 1], r.category] as const));
  const cached = state.segments.some((s) => s.source === "cached");
  // A note for each alert / follow-up text, right after the line that was last when it was sent.
  const markers = state.bubbles.flatMap((b) => {
    const kind = b.kind === "out" && MARKER_WORDS.find(([p]) => b.sms.template_id.startsWith(p));
    return b.kind === "out" && kind ? [{ afterSeq: b.afterSeq, id: b.sms.message_id || b.sms.template_id, text: `→ ${kind[1]} ${MARKER_STATUS[b.sms.status]}` }] : [];
  });
  const end = useRef<HTMLOListElement>(null);
  const last = state.segments[state.segments.length - 1];
  useEffect(() => {
    end.current?.lastElementChild?.scrollIntoView({ block: "end" });
  }, [state.segments.length, markers.length, last?.text]);
  return (
    <section className="card transcript" aria-labelledby="transcript-label">
      <h2 className="label" id="transcript-label">
        <span>Live transcript</span>
        {cached && <span className="meta">cached transcript</span>}
      </h2>
      {state.segments.length === 0 && <p className="empty">No call yet.</p>}
      <ol ref={end}>
        {state.segments.map((s) => {
          const category = flaggedAt.get(s.seq);
          const flagged = category !== undefined;
          return (
            <li key={segKey(s)}>
              <p className={`line ${s.speaker} ${flagged ? "flagged" : ""}`}>
                <span className="time">{clockText(s.t_start_ms)}</span>
                <span className="dot" aria-hidden="true" />
                <span className="who">{s.speaker === "caller" ? "Caller" : "You"}</span>
                <span className="text">
                  <TypedText text={s.text} animate={live.has(segKey(s))} />
                </span>
                {category && <span className="rel">{REQUEST_TAG[category]}</span>}
              </p>
              {markers
                .filter((m) => m.afterSeq === s.seq)
                .map((m) => (
                  <p key={m.id} className="marker">
                    {m.text}
                  </p>
                ))}
            </li>
          );
        })}
      </ol>
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

function WhyPanel({ state, arrived }: { state: State; arrived: Map<string, number> }) {
  const alert = state.decisions.find((d) => d.level === "action_warning");
  const sms = alert && state.bubbles.find((b) => b.kind === "out" && b.sms.template_id === alert.template_id);
  const told = useTemplateText(sms && alert ? alert.template_id : null);
  if (!alert) {
    return (
      <section className="card why" aria-labelledby="why-label">
        <h2 className="label" id="why-label">
          <span>Why this alert</span>
        </h2>
        <p className="quiet">{state.session?.state === "finished" ? "No alert - not a safety verdict" : "No alert yet"}</p>
        <p className="quiet">CallSafe texts only when a caller asks for a code, money or access to your device.</p>
      </section>
    );
  }
  const risk = alertRisk(state);
  const out = sms?.kind === "out" ? sms.sms : null;
  const optedOut = !out && state.alertSkipped;
  const line = risk && state.segments.find((s) => s.seq === risk.span_seq[risk.span_seq.length - 1]);
  const lineAt = line && arrived.get(segKey(line));
  const smsAt = out ? arrived.get(out.message_id) : undefined;
  return (
    <section className="card why alert" aria-labelledby="why-label">
      <h2 className="label" id="why-label">
        <span>Why this alert</span>
      </h2>
      <dl>
        <dt>Request</dt>
        <dd className="request">{risk ? CATEGORY_WORDS[risk.category] : alert.template_id}</dd>
        {line && (
          <>
            <dt>{line.speaker === "caller" ? "Caller said" : "You said"}</dt>
            <dd className="quote">
              &ldquo;<Highlighted text={line.text} spans={risk.match_spans} />&rdquo;
            </dd>
          </>
        )}
        <dt>Caught by</dt>
        <dd>{risk ? caughtBy(risk) : "-"}</dd>
        {lineAt && smsAt && (
          <>
            <dt>Speed</dt>
            <dd>Alert went out {Math.max(0, smsAt - lineAt)} ms after the line came in</dd>
          </>
        )}
        {risk && (
          <>
            <dt>Why it matters</dt>
            <dd>{DANGER_WORDS[risk.category]}</dd>
          </>
        )}
        {told && (
          <>
            <dt>We texted</dt>
            <dd>{told.replace(/^CallSafe:\s*(\w)/, (_, c: string) => c.toUpperCase())}</dd>
          </>
        )}
      </dl>
      <p className={`dispatch ${out?.status ?? ""}`}>
        {optedOut ? "Monitoring opt-in: No. No text sent" : out ? `Alert text: ${statusWords(out)}` : "Alert text not dispatched yet"}
      </p>
    </section>
  );
}

// The words the rule matched (RiskEvent.match_spans: sorted [start, end) offsets into the line).
function Highlighted({ text, spans }: { text: string; spans: [number, number][] }) {
  const parts: ReactNode[] = [];
  let at = 0;
  for (const [a, b] of spans) {
    if (a < at) continue;
    parts.push(text.slice(at, a), <mark key={a}>{text.slice(a, b)}</mark>);
    at = b;
  }
  parts.push(text.slice(at));
  return <>{parts}</>;
}

function caughtBy(r: RiskEvent): string {
  if (r.source === "rule") return "CallSafe rules";
  const sure = r.score === null ? "" : `: ${(Math.floor(r.score * 1000) / 10).toFixed(1)}% sure`;
  return `${MODEL_NAME} (AI)${sure}`;
}

// Consent known and not active: alerts are skipped, not failed. null = not loaded yet (or fixture replay).
const monitoringOff = (s: State) => s.consent !== null && s.consent !== "active";

// The phone frame in both modes: simulated shows the demo phone; real mirrors every text Twilio was asked to send.
function Phone({ bubbles, simulated, off }: { bubbles: Bubble[]; simulated: boolean; off: boolean }) {
  const blocked = bubbles.some((b) => b.kind === "out" && b.sms.error_code === CARRIER_BLOCKED);
  const thread = useRef<HTMLOListElement>(null);
  useEffect(() => {
    thread.current?.lastElementChild?.scrollIntoView({ block: "end" });
  }, [bubbles]);
  return (
    <section className="card phone" aria-labelledby="phone-label">
      <h2 className="label" id="phone-label">
        <span>Phone</span>
        <span className="meta">
          <span className={`dot ${simulated ? "warn" : "info"}`} aria-hidden="true" />
          {simulated ? "simulated SMS" : "real SMS"}
        </span>
      </h2>
      {blocked && <p className="note">Real texts are blocked by carriers until our number's registration clears; this frame shows what was sent.</p>}
      <div className="frame">
        <div className="screen">
          {off ? <p className="empty">Call monitoring is off.</p> : bubbles.length === 0 && <p className="empty">No texts yet.</p>}
          <ol className="thread" ref={thread}>
            {bubbles.map((b) =>
              b.kind === "out" ? (
                <OutBubble key={b.sms.message_id || b.sms.template_id} b={b} />
              ) : (
                <li key={b.id} className="msg in">
                  <div className="bubble in">{b.keyword}</div>
                </li>
              ),
            )}
          </ol>
        </div>
      </div>
      <div className="keys" role="group" aria-label="Reply from the phone">
        {["YES", "WRONG", "SHARED", "STOP"].map((k) => (
          <button key={k} className={`pill ${k === "WRONG" ? "wrong" : ""}`} disabled={FIXTURES} onClick={() => api.simulateReply(k)}>
            {k}
          </button>
        ))}
      </div>
    </section>
  );
}

function useTemplateText(id: string | null): string | null {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (id && !FIXTURES) api.templateText(id).then(setText);
  }, [id]);
  return id ? text : null;
}

function OutBubble({ b }: { b: Extract<Bubble, { kind: "out" }> }) {
  const text = useTemplateText(b.sms.template_id);
  return (
    <li className={`msg out ${b.sms.status}`}>
      <div className="bubble out">{text ?? b.sms.template_id}</div>
      <small className={`status ${b.sms.status}`}>{statusWords(b.sms)}</small>
    </li>
  );
}
