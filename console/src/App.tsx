import { useEffect, useReducer, useState } from "react";
import * as api from "./api";
import { initial, reduce, type Bubble, type State } from "./state";
import type { ArmCounts, Results, RiskEvent } from "./types";

const FIXTURES = new URLSearchParams(location.search).has("fixtures");

const CATEGORY_WORDS: Record<RiskEvent["category"], string> = {
  otp: "Caller asked for a code",
  payment: "Caller asked for money",
  remote: "Caller asked for access to the device",
};
const CONFIDENCE_WORDS: Record<RiskEvent["confidence_class"], string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(FIXTURES ? true : null);
  useEffect(() => {
    if (!FIXTURES) api.loggedIn().then(setAuthed);
  }, []);
  if (authed === null) return null;
  return authed ? <Console /> : <Login onLogin={() => setAuthed(true)} />;
}

function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  return (
    <form
      className="login"
      onSubmit={async (e) => {
        e.preventDefault();
        (await api.login(password)) ? onLogin() : setError(true);
      }}
    >
      <h1>Safe Signal</h1>
      <input type="password" placeholder="Operator password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
      <button type="submit">Log in</button>
      {error && <p className="error">Wrong password</p>}
    </form>
  );
}

function Console() {
  const [state, dispatch] = useReducer(reduce, initial);
  const [results, setResults] = useState<Results>({ status: "pending" });

  useEffect(() => {
    if (FIXTURES) return api.replayFixtures(dispatch);
    api.wrongCount().then((count) => dispatch({ type: "wrong_count", count }));
    api.results().then(setResults);
    const timer = setInterval(() => api.results().then(setResults), 30_000);
    const unsubscribe = api.subscribe(dispatch);
    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, []);

  return (
    <div className="console">
      <header>
        <h1>Safe Signal</h1>
        <span className="tag">replayed call through the live ingestion path</span>
        {FIXTURES && <span className="tag warn">fixture replay</span>}
        <span className="status">{sessionLabel(state)}</span>
      </header>
      <Controls state={state} dispatch={dispatch} />
      <main>
        <Transcript state={state} />
        <aside>
          <WhyPanel state={state} />
          <div className="card counter">
            <h2>WRONG replies</h2>
            <div className="big">{state.wrongCount}</div>
          </div>
          {state.smsMode === "simulated" && <Phone bubbles={state.bubbles} />}
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

function Controls({ state, dispatch }: { state: State; dispatch: (a: { type: "sms_mode"; mode: "real" | "simulated" }) => void }) {
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
            if ((await api.setSmsMode(m)).ok) dispatch({ type: "sms_mode", mode: m });
          }}
        >
          {m}
        </button>
      ))}
    </nav>
  );
}

function Transcript({ state }: { state: State }) {
  const flagged = new Set(state.risks.flatMap((r) => r.span_seq));
  const cached = state.segments.some((s) => s.source === "cached");
  return (
    <section className="card transcript">
      <h2>
        Live transcript {cached && <span className="tag">cached transcript</span>}
      </h2>
      {state.segments.length === 0 && <p className="muted">No call yet.</p>}
      {state.segments.map((s) => (
        <p key={s.seq} className={`line ${s.speaker} ${flagged.has(s.seq) ? "flagged" : ""}`}>
          <span className="who">{s.speaker === "caller" ? "Caller" : "You"}</span>
          {s.text}
        </p>
      ))}
    </section>
  );
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
  const risk = state.risks.find((r) => r.rule_id && alert.basis.includes(r.rule_id)) ?? state.risks[0];
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
    </section>
  );
}

function Phone({ bubbles }: { bubbles: Bubble[] }) {
  return (
    <section className="card phone">
      <h2>
        Phone <span className="tag">simulated SMS</span>
      </h2>
      <div className="thread">
        {bubbles.length === 0 && <p className="muted">No texts yet.</p>}
        {bubbles.map((b) =>
          b.kind === "out" ? <OutBubble key={b.sms.message_id || b.sms.template_id} b={b} /> : <div key={b.id} className="bubble in">{b.keyword}</div>,
        )}
      </div>
      <div className="keys">
        {["YES", "WRONG", "SHARED", "STOP"].map((k) => (
          <button key={k} disabled={FIXTURES} onClick={() => api.simulateReply(k)}>
            {k}
          </button>
        ))}
      </div>
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
        <h3>{name === "K" ? "Keyword only (K)" : name === "B" ? "Safe Signal rules (B)" : name}</h3>
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
          Calls only K flagged: {results.discordant.K_only} · only B flagged: {results.discordant.B_only}
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
