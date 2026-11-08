import { useState } from "react";
import * as api from "./api";

// Shown after a login while the demo phone isn't opted in; the answer is never stored in the browser.
export default function OptInPrompt({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const choose = async (optIn: boolean) => {
    setBusy(true);
    if (await api.setOptIn(optIn)) onDone();
    else setBusy(false); // the console shows the error banner
  };
  return (
    <div className="modal-backdrop">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="optin-title" aria-describedby="optin-choices">
        <h2 id="optin-title">Opt in to call monitoring?</h2>
        <ul className="choices" id="optin-choices">
          <li>
            <span className="label-text">Yes</span>
            <span>CallSafe texts you when a caller asks for a code, money or access to your device.</span>
          </li>
          <li>
            <span className="label-text">Not now</span>
            <span>CallSafe still explains what it would flag, but sends no texts. You can turn it on later from the top bar.</span>
          </li>
        </ul>
        <div className="modal-actions">
          <button className="secondary" disabled={busy} onClick={() => choose(false)}>
            Not now
          </button>
          <button className="primary" disabled={busy} onClick={() => choose(true)} autoFocus>
            Yes
          </button>
        </div>
      </section>
    </div>
  );
}
