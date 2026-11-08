import { type ReactNode, useCallback, useEffect, useReducer, useRef, useState } from "react";
import * as api from "./api";
import Home from "./Home";
import Numbers from "./Numbers";
import OptInPrompt from "./OptInPrompt";
import { initial, reduce, type Action, type Bubble, type State } from "./state";
import type { Event, RiskEvent, Segment, SmsPayload, TurnPayload, Speaker } from "./types";

const FIXTURES = new URLSearchParams(location.search).has("fixtures");
// Live transcript typing speed. Must match WORD_MS in backend/app/ingest/__init__.py (cached replay pacing).
const WORD_MS = 100;
const words = (text: string) => text.split(/\s+/).filter(Boolean);
const segKey = (s: Segment) => `${s.session_ref}:${s.seq}`;
// How long a live line takes to type out: over its turn's audio when the replay has some, else WORD_MS a word.
const lineMs = (s: Segment) => (s.audio && s.t_end_ms > s.t_start_ms ? s.t_end_ms - s.t_start_ms : words(s.text).length * WORD_MS);

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
  // The simulated gateway's texts ("SIM…" ids) land in this frame at once but are never status-updated past queued.
  if (sms.status === "queued" && sms.message_id.startsWith("SIM")) return "Sent (simulated)";
  if (sms.status !== "failed" || !sms.error_code) return STATUS_WORDS[sms.status];
  if (sms.error_code === CARRIER_BLOCKED) return "Blocked by carrier (30034)";
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
const DETECTOR_WORDS: Record<string, string> = { K: "Keywords only", B: "Rules only (AI off)", C: `Rules + ${MODEL_NAME}` };
// What the caller wanted, as the AI's sentence ends: "99.9% sure the caller wants money".
const WANTS_WORDS: Record<RiskEvent["category"], string> = { otp: "a code", payment: "money", remote: "access to your device" };
const percent = (score: number) => `${(Math.floor(score * 1000) / 10).toFixed(1)}%`;
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
  const [home, setHome] = useState(() => location.hash === "#home");
  useEffect(() => {
    const onHash = () => setHome(location.hash === "#home");
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  if (home) return <Home />;
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
        <a className="wordmark home-link" href="#home" aria-label="CallSafe home"><span className="mark" aria-hidden="true" />CallSafe</a>
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
  const live = useRef(new Map<string, number>()); // ms per word for segments that arrived over the stream; hydrated ones don't type
  const player = useRef<Player>({ interrupt: () => {}, flush: () => {}, resume: () => {} }); // set by the stream effect; the controls call it
  const [page, setPage] = useState(() => location.hash);
  useEffect(() => {
    const onHash = () => setPage(location.hash);
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  const numbers = page === "#numbers";
  const [hardStop, setHardStop] = useState<string | null>(null); // the alert template the caller is on hold for
  const monitoring = useRef(false); // read by the stream effect: no hold for a subscriber who opted out
  monitoring.current = state.consent === "active";
  const arrived = useRef(new Map<string, number>()); // receive time per segment / sms, before the typing hold
  // Live mic conversation (#100): the session this tab started, the open mic, and turns still being transcribed.
  const [liveRef, setLiveRef] = useState<string | null>(null);
  const mic = useRef<MediaStream | null>(null);
  const [transcribing, setTranscribing] = useState(0);
  const liveOn = liveRef !== null && state.sessionRef === liveRef && state.session?.state === "running";
  const wasOn = useRef(false);
  const stopMic = () => {
    mic.current?.getTracks().forEach((t) => t.stop());
    mic.current = null;
  };
  useEffect(() => {
    if (wasOn.current && !liveOn) stopMic(); // End call, Reset or another run: release the mic
    wasOn.current = liveOn;
  }, [liveOn]);
  const startLive = async () => {
    player.current.interrupt();
    try {
      stopMic();
      mic.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setError("Microphone unavailable (permission denied or no mic found)");
      return;
    }
    const r = await api.liveStart();
    if (r) setLiveRef((await r.json()).session_ref);
    else stopMic();
  };

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
    // Live events wait, in order, until the line before them has finished typing (and its audio has played),
    // so an alert never shows before its words.
    let queue: Event[] = [];
    let gate = 0;
    let held: ReturnType<typeof setTimeout> | undefined;
    let audio: HTMLAudioElement | null = null;
    // Hard stop (demo): on an alert the caller is put on hold; their next lines wait until the warning has played.
    let onHold = false;
    let source: string | null | undefined;
    const stopAudio = () => {
      audio?.pause();
      audio = null;
    };
    const run = (e: Event) => {
      if (e.type === "segment") {
        const ms = lineMs(e.payload);
        live.current.set(segKey(e.payload), ms / Math.max(1, words(e.payload.text).length));
        gate = Date.now() + ms;
        if (e.payload.audio) {
          stopAudio();
          audio = new Audio(`/demo/audio/${e.payload.audio}`);
          audio.play().catch(() => {}); // muted tab or autoplay block: the line still types out on time
        }
      }
      if (e.type === "session" && e.payload.state === "running") source = e.payload.source;
      dispatch(e);
      // A real phone call can't be held from the console yet (that needs the Twilio conference bridge).
      if (e.type === "decision" && e.payload.level === "action_warning" && e.payload.template_id && source !== "phone" && monitoring.current) {
        onHold = true;
        stopAudio();
        setHardStop(e.payload.template_id);
      }
    };
    const pump = () => {
      clearTimeout(held);
      // On hold only the conversation waits; the alert text still lands on the phone.
      while (queue.length && !(onHold && queue[0].type === "segment")) {
        const wait = gate - Date.now();
        if (wait > 0) {
          held = setTimeout(pump, wait);
          return;
        }
        run(queue.shift()!);
      }
    };
    // Reset / a new call: drop what is still held for the old one and go silent at once.
    const release = () => {
      onHold = false;
      setHardStop(null);
    };
    const interrupt = () => {
      release();
      queue = [];
      gate = 0;
      clearTimeout(held);
      stopAudio();
    };
    // End call: go silent and show everything already received now.
    const flush = () => {
      release();
      stopAudio();
      gate = 0;
      pump();
    };
    // Back to the call: the rest of the conversation plays on from where it was held.
    const resume = () => {
      release();
      gate = Date.now();
      pump();
    };
    player.current = { interrupt, flush, resume };
    const paced = (e: Event) => {
      if (e.type === "session" && e.payload.state !== "finished") interrupt();
      queue.push(e);
      pump();
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
      interrupt();
      unsubscribe();
    };
  }, [onLoggedOut]);

  return (
    <div className="console">
      <header className="topbar">
        <a className="wordmark home-link" href="#home" aria-label="CallSafe home"><span className="mark" aria-hidden="true" />CallSafe</a>
        <span className="status" aria-live="polite">
          {sessionLabel(state)}
        </span>
        {FIXTURES && <span className="tag warn">fixture replay</span>}
        {stream === "connecting" && <span className="tag">connecting…</span>}
        {stream === "stale" && <span className="tag stale">disconnected / reconnecting — view may be stale</span>}
        <span className="spacer" />
        <a className="nav" href={numbers ? "#" : "#numbers"}>
          {numbers ? "Back to the call" : "The numbers"}
        </a>
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
      <main className="page-main">
        {numbers && <Numbers />}
        {/* Hidden, not unmounted: the call keeps running (and the mic keeps its stream) on the numbers page. */}
        <div className="band" hidden={numbers}>
        <div className="col left">
          <CallClock state={state} />
          <Controls state={state} dispatch={dispatch} player={player} onStartLive={liveOn ? null : startLive}>
            {liveOn && mic.current && <LiveMic stream={mic.current} onTranscribing={(n) => setTranscribing((t) => t + n)} />}
          </Controls>
        </div>
        <div className="col centre">
          <Verdict state={state} />
          <Transcript state={state} live={live.current} transcribing={transcribing > 0} />
        </div>
        <div className="col right">
          <WhyPanel state={state} arrived={arrived.current} />
          <Phone bubbles={state.bubbles} simulated={state.smsMode === "simulated"} off={monitoringOff(state)} wrongCount={state.wrongCount} />
        </div>
        </div>
      </main>
      {!numbers && <Ticker state={state} />}
      {askOptIn && hydrated && state.consent !== "active" && <OptInPrompt onDone={onOptInDone} />}
      {hardStop && (
        <HardStop
          templateId={hardStop}
          onResume={() => player.current.resume()}
          onHangUp={() => {
            player.current.flush();
            api.endCall();
          }}
        />
      )}
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
  if (s.session.state === "running") return "call running";
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
      {state.turns.some((t) => t.ai === "unavailable") && (
        <p className="badge warn" role="status">
          <span className="dot warn" aria-hidden="true" />
          AI unavailable, rules only
        </p>
      )}
    </section>
  );
}

function ControlRow({ label, icon, className, onClick }: { label: string; icon: string; className?: string; onClick: (() => void) | null }) {
  return (
    <li>
      <button className={`row ${className ?? ""}`} disabled={FIXTURES || !onClick} onClick={onClick ?? undefined}>
        <span className="icon" aria-hidden="true">
          {icon}
        </span>
        <span className="row-label">{label}</span>
      </button>
    </li>
  );
}

type Player = { interrupt: () => void; flush: () => void; resume: () => void };

function Controls({ state, dispatch, player, onStartLive, children }: {
  state: State;
  dispatch: (a: Action) => void;
  player: { current: Player };
  onStartLive: (() => void) | null; // null while this tab's live conversation runs
  children: ReactNode;
}) {
  const mode = state.smsMode;
  const run = (id: "clinic" | "bank" | "family") => {
    player.current.interrupt();
    api.runScenario(id);
  };
  return (
    <section className="card controls" aria-labelledby="controls-label">
      <h2 className="visually-hidden" id="controls-label">
        Controls
      </h2>
      <ul className="rows">
        <ControlRow label="Run clinic" icon="▶" onClick={() => run("clinic")} />
        <ControlRow label="Run bank" icon="▶" className="primary-row" onClick={() => run("bank")} />
        <ControlRow label="Run grandson" icon="▶" onClick={() => run("family")} />
        <ControlRow label="Start live conversation" icon="●" onClick={onStartLive} />
        {children}
        <ControlRow
          label="End call"
          icon="■"
          onClick={() => {
            player.current.flush();
            api.endCall();
          }}
        />
        <ControlRow
          label="Reset"
          icon="↺"
          className="danger"
          onClick={() => {
            player.current.interrupt();
            api.reset();
          }}
        />
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
        {alerted ? (risk ? CATEGORY_WORDS[risk.category] : "Alert") : finished ? "No alert detected" : "No alert yet"}
      </p>
    </section>
  );
}

// Tap a speaker to record a turn, tap again to send it. One mic, so one speaker at a time; either may go twice in a row.
function LiveMic({ stream, onTranscribing }: { stream: MediaStream; onTranscribing: (delta: number) => void }) {
  const [speaker, setSpeaker] = useState<Speaker | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  useEffect(
    () => () => {
      if (rec.current?.state !== "recording") return;
      rec.current.onstop = null; // the call ended mid-turn: drop the clip
      rec.current.stop();
    },
    [],
  );
  const toggle = (who: Speaker) => {
    if (speaker === who) {
      rec.current?.stop();
      setSpeaker(null);
      return;
    }
    const r = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    r.ondataavailable = (e) => chunks.push(e.data);
    r.onstop = () => {
      onTranscribing(1);
      api.liveTurn(who, new Blob(chunks, { type: r.mimeType })).finally(() => onTranscribing(-1));
    };
    r.start();
    rec.current = r;
    setSpeaker(who);
  };
  return (
    <li className="live-mic" role="group" aria-label="Live mic: tap a speaker to record, tap again to send">
      {(["caller", "subscriber"] as const).map((who) => (
        <button
          key={who}
          className={`pill ${speaker === who ? "on" : ""}`}
          aria-pressed={speaker === who}
          disabled={speaker !== null && speaker !== who}
          onClick={() => toggle(who)}
        >
          {SPEAKER_WORDS[who]}
          {speaker === who && " - tap to stop"}
        </button>
      ))}
    </li>
  );
}

const SPEAKER_WORDS: Record<Speaker, string> = { caller: "Caller", subscriber: "You" };

function Transcript({ state, live, transcribing }: { state: State; live: Map<string, number>; transcribing: boolean }) {
  // The line that carried the request (the Why panel quotes the same one).
  const flaggedAt = new Map(state.risks.map((r) => [r.span_seq[r.span_seq.length - 1], r.category] as const));
  // A rule hit underlines the words it matched, once the line has finished typing.
  const spansAt = new Map(state.risks.filter((r) => r.source === "rule").map((r) => [r.span_seq[r.span_seq.length - 1], r.match_spans] as const));
  const cached = state.segments.some((s) => s.source === "cached");
  // A note for each alert / follow-up text, right after the line that was last when it was sent.
  const markers = state.bubbles.flatMap((b) => {
    const kind = b.kind === "out" && MARKER_WORDS.find(([p]) => b.sms.template_id.startsWith(p));
    return b.kind === "out" && kind ? [{ afterSeq: b.afterSeq, id: b.sms.message_id || b.sms.template_id, text: `→ ${kind[1]} ${MARKER_STATUS[b.sms.status]}` }] : [];
  });
  const end = useRef<HTMLOListElement>(null);
  const last = state.segments[state.segments.length - 1];
  useEffect(() => {
    const ol = end.current;
    if (!ol) return;
    const scroll = () => ol.lastElementChild?.scrollIntoView({ block: "end" });
    scroll();
    // Lines grow after they arrive (typing, the alert marker, underlines), so keep the newest in view.
    const grown = new ResizeObserver(scroll);
    grown.observe(ol);
    return () => grown.disconnect();
  }, [state.segments.length, markers.length, last?.text]);
  return (
    <section className="card transcript" aria-labelledby="transcript-label">
      <h2 className="label" id="transcript-label">
        <span>Live transcript</span>
        {cached && <span className="meta">cached transcript</span>}
        {state.session?.source === "mic" && <span className="meta">Live mic</span>}
        {state.session?.source === "phone" && <span className="meta">Phone call</span>}
      </h2>
      {state.segments.length === 0 && <p className="empty">No call yet.</p>}
      <ol ref={end} tabIndex={0} aria-label="Transcript lines">
        {state.segments.map((s) => {
          const category = flaggedAt.get(s.seq);
          const flagged = category !== undefined;
          return (
            <li key={segKey(s)}>
              <p className={`line ${s.speaker} ${flagged ? "flagged" : ""}`}>
                <span className="time">{clockText(s.t_start_ms)}</span>
                <span className="dot" aria-hidden="true" />
                <span className="who">{SPEAKER_WORDS[s.speaker]}</span>
                <span className="text">
                  <TypedText text={s.text} wordMs={live.get(segKey(s))}>
                    {spansAt.has(s.seq) ? <Highlighted text={s.text} spans={spansAt.get(s.seq)!} /> : undefined}
                  </TypedText>
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
      {transcribing && <p className="empty">Transcribing...</p>}
    </section>
  );
}

// Reveals a line one word per `wordMs` (undefined: all at once), like a streamed chat reply. Words shown are
// computed from the clock, not counted ticks, so throttled timers can't fall behind the event hold in Console.
function TypedText({ text, wordMs, children }: { text: string; wordMs: number | undefined; children?: ReactNode }) {
  const all = words(text);
  const [start] = useState(() => Date.now());
  const [, tick] = useState(0);
  const shown = wordMs ? Math.min(all.length, Math.floor((Date.now() - start) / wordMs)) : all.length;
  useEffect(() => {
    if (!wordMs || shown >= all.length) return;
    const t = setTimeout(() => tick((n) => n + 1), Math.max(0, (shown + 1) * wordMs - (Date.now() - start))); // next word boundary
    return () => clearTimeout(t);
  });
  if (shown >= all.length) return <>{children ?? text}</>;
  return <span className="typing">{all.slice(0, shown).join(" ")}</span>;
}

function WhyPanel({ state, arrived }: { state: State; arrived: Map<string, number> }) {
  const alert = state.decisions.find((d) => d.level === "action_warning");
  const sms = alert && state.bubbles.find((b) => b.kind === "out" && b.sms.template_id === alert.template_id);
  if (!alert) {
    return (
      <section className="card why" aria-labelledby="why-label" tabIndex={0}>
        <h2 className="label" id="why-label">
          <span>Why this alert</span>
        </h2>
        <p className="quiet">{state.session?.state === "finished" ? "No alert detected" : "No alert yet"}</p>
        <p className="quiet">Texts you only when a caller asks for a code, money or device access.</p>
      </section>
    );
  }
  const risk = alertRisk(state);
  const out = sms?.kind === "out" ? sms.sms : null;
  const optedOut = !out && state.alertSkipped;
  const line = risk && state.segments.find((s) => s.seq === risk.span_seq[risk.span_seq.length - 1]);
  const lineAt = line && arrived.get(segKey(line));
  const smsAt = out ? arrived.get(out.message_id) : undefined;
  // The backend's measure (end of the turn's speech -> gateway accepted), else this console's clock.
  const speedMs = out?.latency_ms ?? (lineAt && smsAt ? Math.max(0, smsAt - lineAt) : null);
  const replay = state.session?.source?.startsWith("replay:") ?? true;
  return (
    <section className="card why alert" aria-labelledby="why-label" tabIndex={0}>
      <h2 className="label" id="why-label">
        <span>Why this alert</span>
      </h2>
      <dl>
        <dt>Caught by</dt>
        <dd>{risk ? caughtBy(risk) : "-"}</dd>
        {speedMs !== null && (
          <>
            <dt>Speed</dt>
            <dd>
              Text sent {(speedMs / 1000).toFixed(2)} s after {replay ? "the line came in" : "the caller stopped talking"}
            </dd>
          </>
        )}
        {risk && (
          <>
            <dt>Why it matters</dt>
            <dd>{DANGER_WORDS[risk.category]}</dd>
          </>
        )}
      </dl>
      {/* The phone shows the text and its status; only say why there is none. */}
      {optedOut && <p className="dispatch">Monitoring opt-in: No. No text sent</p>}
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
  const sure = r.score === null ? "sure" : `${percent(r.score)} sure`;
  return `${MODEL_NAME}: ${sure} the caller wants ${WANTS_WORDS[r.category]}`;
}

// Consent known and not active: alerts are skipped, not failed. null = not loaded yet (or fixture replay).
const monitoringOff = (s: State) => s.consent !== null && s.consent !== "active";

// The phone frame in both modes: simulated shows the demo phone; real mirrors every text Twilio was asked to send.
function Phone({ bubbles, simulated, off, wrongCount }: { bubbles: Bubble[]; simulated: boolean; off: boolean; wrongCount: number | null }) {
  const blocked = bubbles.some((b) => b.kind === "out" && b.sms.error_code === CARRIER_BLOCKED);
  const thread = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const ol = thread.current;
    if (!ol) return;
    // Newest first, except the follow-up that lands right after the alert must not scroll the alert away.
    const scroll = () => {
      const shown = [...ol.children].filter((_, i) => {
        const b = bubbles[i];
        return !(b?.kind === "out" && b.sms.template_id.startsWith("FU-"));
      });
      (shown.pop() ?? ol.lastElementChild)?.scrollIntoView({ block: "end" });
    };
    scroll();
    // A bubble grows when its template text arrives after it was first drawn.
    const grown = new ResizeObserver(scroll);
    grown.observe(ol);
    return () => grown.disconnect();
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
      {blocked && <p className="note">Carriers block our texts until the number is registered.</p>}
      <div className="frame">
        <div className="screen" tabIndex={0} role="log" aria-label="Texts on the phone">
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
      <p className="wrong-count" role="status" aria-atomic="true">
        <span className="n">{wrongCount ?? 0}</span> WRONG replies
      </p>
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

// Eval rows, best last; an arm missing from the file is left out.


const AI_CATEGORY: Record<RiskEvent["category"], string> = { otp: "code", payment: "money", remote: "access" };
function aiWords(t: TurnPayload): string {
  if (t.ai === "off") return "rules only";
  if (t.ai === "unavailable") return "AI unavailable";
  const pct = t.score === null ? "" : ` ${percent(t.score)}`;
  return t.ai === "request" && t.category ? `AI ${AI_CATEGORY[t.category]}${pct}` : `AI no request${pct}`;
}
function templateWords(id: string): string {
  if (id.startsWith("ALERT-")) return "Alert text";
  if (id.startsWith("FU-")) return "Follow-up text";
  if (id === "ENROLL") return "Opt-in invite";
  return id.startsWith("R-") ? `Reply to ${id.slice(2).split("-")[0]}` : id;
}

type TickerItem = { key: string; tag: "turn" | "alert" | "sms"; text: string };
// One entry per judged turn, each text after the turn it followed.
function tickerItems(s: State): TickerItem[] {
  const sms = (afterSeq: number) =>
    s.bubbles.flatMap((b): TickerItem[] => {
      if (b.kind !== "out" || b.afterSeq !== afterSeq) return [];
      // The Why panel's Speed row says what the seconds are measured from.
      const latency = b.sms.latency_ms == null ? "" : ` · ${(b.sms.latency_ms / 1000).toFixed(2)} s`;
      const tag = b.sms.template_id.startsWith("ALERT-") ? "alert" : "sms";
      return [{ key: `sms-${b.sms.message_id || b.sms.template_id}`, tag, text: `${templateWords(b.sms.template_id)} · ${statusWords(b.sms)}${latency}` }];
    });
  const turns = s.turns.flatMap((t): TickerItem[] => [
    { key: `turn-${t.seq}`, tag: "turn", text: `${SPEAKER_WORDS[t.speaker]} · ${aiWords(t)} · ${t.decided_ms} ms` },
    ...sms(t.seq),
  ]);
  return [...sms(0), ...turns];
}

// The pipeline's per-turn verdicts as a slow ticker (70 s a loop, paused on hover, still under reduced motion).
function Ticker({ state }: { state: State }) {
  const items = tickerItems(state);
  const list = (copy: boolean) => (
    <ul className="ticker-list" aria-hidden={copy || undefined}>
      {items.map((i) => (
        <li key={i.key}>
          <span className={`ttag ${i.tag}`}>{i.tag}</span>
          {i.text}
        </li>
      ))}
    </ul>
  );
  return (
    <section className="ticker" aria-label="Pipeline log" tabIndex={0}>
      {items.length === 0 ? (
        <p className="ticker-empty">Each turn's verdict and every text appear here during a call.</p>
      ) : (
        <div className="ticker-track">
          {list(false)}
          {list(true)}
        </div>
      )}
    </section>
  );
}

// What CallSafe says to the subscriber while the caller is on hold, per alert template family.
const HOLD_SCRIPT: [string, string][] = [
  ["ALERT-OTP", "This is CallSafe. We've put your caller on hold. They asked for a security code, and your bank never asks for that. Don't share it. Hang up and call your bank yourself."],
  ["ALERT-PAY", "This is CallSafe. We've put your caller on hold. They asked you to send money, which is a common scam. Don't pay anyone. Hang up and call your family on a number you know."],
  ["ALERT-REMOTE", "This is CallSafe. We've put your caller on hold. They want access to your device. Don't install anything. Hang up and call the company on a number you know."],
];
const SPEAK_MS_PER_WORD = 400; // if speech never ends (no voice, headless), resume after about the time it would take

// The hard stop (demo): the caller is held, the subscriber hears a spoken warning, then decides.
function HardStop({ templateId, onResume, onHangUp }: { templateId: string; onResume: () => void; onHangUp: () => void }) {
  const script = (HOLD_SCRIPT.find(([p]) => templateId.startsWith(p)) ?? HOLD_SCRIPT[0])[1];
  const resume = useRef(onResume);
  resume.current = onResume;
  useEffect(() => {
    const done = () => resume.current();
    const say = new SpeechSynthesisUtterance(script);
    say.rate = 1.05;
    say.onend = done;
    say.onerror = done; // no voice to play: nothing to hold the call for
    speechSynthesis.cancel();
    speechSynthesis.speak(say);
    const fallback = setTimeout(done, 1500 + words(script).length * SPEAK_MS_PER_WORD);
    return () => {
      say.onend = say.onerror = null;
      speechSynthesis.cancel();
      clearTimeout(fallback);
    };
  }, [script]);
  return (
    <div className="modal-backdrop hold-backdrop">
      <section className="modal hold" role="alertdialog" aria-modal="true" aria-labelledby="hold-title" aria-describedby="hold-script">
        <p className="label-text">
          <span className="dot live-alert" aria-hidden="true" /> Caller on hold
        </p>
        <h2 id="hold-title">Possible scam. Listen.</h2>
        <p id="hold-script" className="script">
          &ldquo;{script}&rdquo;
        </p>
        <div className="modal-actions">
          <button className="secondary" onClick={onHangUp}>
            Hang up
          </button>
          <button className="primary" onClick={onResume} autoFocus>
            Return to call
          </button>
        </div>
      </section>
    </div>
  );
}
