import { useState } from "react";

// The intro screen for the demo video (#home). The T-Mobile logo is console/public/t-mobile-logo.png when present.
export default function Home() {
  const [logo, setLogo] = useState(true);
  return (
    <main className="home">
      <p className="lockup">
        <span className="wordmark">CallSafe</span>
        <span className="times" aria-hidden="true">×</span>
        {logo ? (
          <img src="/t-mobile-logo.png" alt="T-Mobile" onError={() => setLogo(false)} />
        ) : (
          <span className="partner">T-Mobile</span>
        )}
      </p>
      <h1 className="home-title">Every scam call asks for something. CallSafe speaks up the moment it does.</h1>
      <p className="home-sub">It listens for a request for a code, money or access to your phone, puts the caller on hold and tells you, during the call.</p>
      <p className="home-actions">
        <a className="primary" href="#">
          Open CallSafe
        </a>
        <a className="nav" href="#numbers">
          The numbers
        </a>
      </p>
    </main>
  );
}
