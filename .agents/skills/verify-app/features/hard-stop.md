# Hard stop (demo)

When CallSafe alerts on a replay or a live-mic conversation, the console puts the caller on hold: the caller's next lines (and the replay audio) wait, a "Caller on hold" card reads `Possible scam. Listen.`, and the browser speaks a short warning to the subscriber. The alert text still lands on the phone during the hold. The call resumes when the warning ends, or at once with `Return to call`; `Hang up` ends the call (the follow-up goes out). No hold for a real phone call (that needs the Twilio conference bridge) or when monitoring is off.

## Sub-features

- `hardstop.hold-and-resume` runs the bank replay: the hold card appears at the alert with the code warning; the alert bubble shows on the phone; the transcript does not grow for 3 s; `Return to call` closes the card and the call plays to its last line.

## How to get to it (user POV)

- Log in, opt in, click `Run bank` or `Run grandson`; wait for the alert.

## Driving it with verify.py

Preconditions: profile `cached`, demo phone opted in (`ctx.ensure_opted_in()`).

- Other UI checks that run an alerting replay answer the hold with `return_to_call()` the way an operator would.
- **Proof.** `screenshots/hardstop.hold-and-resume--on-hold.png`, `...--resumed.png`.

## Gotchas

- Playwright's Chromium has no speech voices, so the warning never "ends"; the card closes on its reading-time fallback (about 15 s) unless the check clicks `Return to call`.
