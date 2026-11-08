import { useEffect, useState } from "react";
import * as api from "./api";
import type { ArmCounts, Results } from "./types";

// Blind H4 (PRD §19.6): 6228 scripted calls written blind by isolated AI agents with no repo access,
// sealed by sha256 before scoring. K and B on main bfc510b; C on the PR #79 branch (79b6b8d) with the
// previous model (TypeSafe Jev 1.14), not re-measured with Perplexity Decider V1.2.
const H4 = {
  scams: 3117,
  harmless: 3111,
  arms: [
    // Percentages exactly as published in PRD §19.6 and the deck, so every surface quotes the same figure.
    { name: "Keywords only", caught: 2629, caughtPct: "84.3%", caughtCi: "83.0–85.6", falseAlerts: 2001, falsePct: "64.4%", falseCi: "62.6–66.0" },
    { name: "CallSafe rules", caught: 2056, caughtPct: "65.9%", caughtCi: "64.2–67.7", falseAlerts: 27, falsePct: "0.9%", falseCi: "0.5–1.3" },
    { name: "Rules + AI*", caught: 3094, caughtPct: "99.2%", caughtCi: "98.8–99.6", falseAlerts: 9, falsePct: "0.3%", falseCi: "0.1–0.6" },
  ],
};
// Real calls to the demo number on 2026-11-08 (grandson script, arm C, real Twilio send): end of the money
// request -> Twilio accepted the alert text. Breakdown from the call before the whisper-draft change.
const LIVE_ALERT_S = 1.74;
const LIVE_PARTS: [string, string][] = [
  ["Pause that ends the turn", "0.6 s"],
  ["Speech to text (on the laptop)", "~0.5 s"],
  ["Rules + Perplexity Decider", "~0.5 s"],
  ["Twilio accepts the text", "~0.3 s"],
];
const DEV_ARMS: [string, string][] = [
  ["K", "Keywords only"],
  ["B", "CallSafe rules"],
  ["C", "Rules + AI"],
];

export default function Numbers() {
  const [dev, setDev] = useState<Results | "pending" | null>(null);
  useEffect(() => {
    api.results().then((r) => setDev(r && "arms" in r ? r : "pending"));
  }, []);
  const keywords = H4.arms[0];
  const rules = H4.arms[1];
  const ai = H4.arms[2];
  return (
    <div className="numbers">
      <section className="hero-stats" aria-label="Headline numbers">
        <Stat label="Harmless calls flagged" before={keywords.falsePct} after={rules.falsePct} note="keywords → CallSafe rules" />
        <Stat label="Scams caught" before={rules.caughtPct} after={ai.caughtPct} note="rules → rules + AI*" />
        <Stat label="Alert on a real call" after={`${LIVE_ALERT_S.toFixed(2)} s`} note="target: under 2 s" />
      </section>

      <section aria-labelledby="h4-label">
        <h2 className="label" id="h4-label">
          <span>Blind test · {(H4.scams + H4.harmless).toLocaleString()} scripted calls</span>
        </h2>
        <table className="stats">
          <thead>
            <tr>
              <td />
              <th scope="col">Scams caught</th>
              <th scope="col">Harmless calls flagged</th>
            </tr>
          </thead>
          <tbody>
            {H4.arms.map((a) => (
              <tr key={a.name}>
                <th scope="row">{a.name}</th>
                <td>
                  {a.caughtPct} <small>{a.caught.toLocaleString()} of {H4.scams.toLocaleString()} · CI {a.caughtCi}</small>
                </td>
                <td>
                  {a.falsePct} <small>{a.falseAlerts.toLocaleString()} of {H4.harmless.toLocaleString()} · CI {a.falseCi}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="fine">
          Written by AI agents that never saw our code, sealed before scoring. *Measured with our previous model, not yet with Perplexity Decider.
        </p>
      </section>

      <section aria-labelledby="dev-label">
        <h2 className="label" id="dev-label">
          <span>Dev set · the calls the rules were tuned on</span>
        </h2>
        {dev === null ? (
          <p className="quiet">Loading…</p>
        ) : dev === "pending" ? (
          <p className="quiet">Results pending</p>
        ) : (
          <DevTable results={dev} />
        )}
      </section>

      <section aria-labelledby="speed-label">
        <h2 className="label" id="speed-label">
          <span>Where the time goes on a live call</span>
        </h2>
        <dl className="parts">
          {LIVE_PARTS.map(([what, t]) => (
            <div key={what}>
              <dt>{what}</dt>
              <dd>{t}</dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="fine">Scripted transcripts, not real customer calls. No production claim.</p>
    </div>
  );
}

function Stat({ label, before, after, note }: { label: string; before?: string; after: string; note: string }) {
  return (
    <div className="stat">
      <p className="label-text">{label}</p>
      <p className="big">
        {before && <span className="before">{before} → </span>}
        {after}
      </p>
      <p className="note">{note}</p>
    </div>
  );
}

function DevTable({ results }: { results: Results }) {
  const rows = DEV_ARMS.flatMap(([id, name]) => (results.arms[id] ? [[name, results.arms[id]] as [string, ArmCounts]] : []));
  const calls = rows.length ? rows[0][1].TP + rows[0][1].FP + rows[0][1].FN + rows[0][1].TN : 0;
  return (
    <>
      <table className="stats">
        <thead>
          <tr>
            <td />
            <th scope="col">Scams caught</th>
            <th scope="col">Hard harmless calls flagged</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, c]) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              <td>
                {c.TP} of {c.TP + c.FN}
              </td>
              <td>
                {c.hard_benign_fp} of {c.hard_benign_n}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fine">{calls} scripted calls the rules were tuned on, so it shows no AI gain; the blind test above is the fair one.</p>
    </>
  );
}
