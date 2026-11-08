import { useState } from "react";
import * as api from "./api";

// Shown after every login; the answer is never stored in the browser. Can't be dismissed without choosing.
export default function OptInPrompt({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const choose = async (optIn: boolean) => {
    setBusy(true);
    if (await api.setOptIn(optIn)) onDone();
    else setBusy(false); // the console shows the error banner
  };
  return (
    <div className="modal-backdrop">
      <section className="modal card" role="dialog" aria-modal="true" aria-labelledby="optin-title">
        <h2 id="optin-title">Opt in to call monitoring?</h2>
        <p>Yes: CallSafe texts you when a caller asks for a code, money or access to your device.</p>
        <p>No: CallSafe still explains what it would flag, but sends no texts.</p>
        <div className="modal-actions">
          <button className="on" disabled={busy} onClick={() => choose(true)} autoFocus>
            Yes
          </button>
          <button disabled={busy} onClick={() => choose(false)}>
            No
          </button>
        </div>
      </section>
    </div>
  );
}
