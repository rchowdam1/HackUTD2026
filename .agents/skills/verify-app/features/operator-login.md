# Operator login

The console is locked behind one operator password. A correct password sets an HttpOnly, SameSite=Strict signed session cookie backed by a server-side session (12 h expiry, revoked by `POST /logout`); every operator route answers 401 without it, and `/health` stays public.

## Sub-features

- `login.api-guard` rejects every operator route without a valid cookie (including a forged one) and keeps `/health` public.
- `login.ui-wrong-password` shows "Wrong password" and stores no cookie.
- `login.ui-success` renders the console, shows the opt-in prompt only if the demo phone is not opted in (else the header reads "Monitoring on"), and stores a cookie that authenticates API calls through the Vite proxy.
- `login.opt-in-every-login` asks "Opt in to call monitoring?" on every login while the demo phone is not opted in: Not now keeps consent `stopped`, Yes stores `active`, neither sends a text; once active, the next login and a reload do not ask.

## How to get to it (user POV)

- Open the console URL; the login form appears when `GET /aggregates` returns 401.
- `POST /login {"password": ...}` from any HTTP client.

## Driving it with verify.py

Preconditions:

- `make verify ARGS="--features operator-login"` launched a healthy instance (doctor `auth=ok`).

- **Unauthenticated wall.** Request each route in `PROTECTED` (`checks.py`) with no cookie. Each returns 401; an unauthenticated `POST /demo/run/bank` produces no `session` event on the SSE observer.
- **Forged cookie.** `GET /aggregates` with `safesignal_session=forged.deadbeef`. Returns 401.
- **Wrong password (UI).** Fresh browser context: fill placeholder `Operator password` with a wrong value, click button `Log in`. Text `Wrong password` is visible, button `Run bank` is absent, the context holds no cookies.
- **Correct password (UI).** Fill the sandbox password, click `Log in`. Button `Run bank` is visible; cookie `safesignal_session` has `httpOnly` and `sameSite=Strict`; `page.request.get(<console>/aggregates)` returns 200. If SQLite consent is active: header `Monitoring on`, no dialog. Otherwise dialog `Opt in to call monitoring?` is visible and the check answers `Not now` so consent stays as it was.
- **Opt-in on every login.** Opt out via `POST /sms/consent {opt_in: false}`, then twice in a fresh context: clear cookies, log in, dialog visible, click `Not now` (then `Yes` on the second login). Each answer: `POST /sms/consent` 200, SQLite `stopped` (then `active`, with an SSE `consent` event), outbox unchanged. A third login shows `Monitoring on` and no dialog; `page.reload()`: no dialog.
- **Proof.** `screenshots/login.ui-success--logged-in.png` + `.aria.txt`, `screenshots/login.ui-wrong-password--wrong-password.png`, `screenshots/login.opt-in-every-login--prompt-{no,yes}.png` (the dialog on each login).

## Gotchas

- The opt-in dialog (`role=dialog`, name `Opt in to call monitoring?`) appears only after the login form and only while consent is not `active`, never on a reload, and blocks the console until answered. The header's `Monitoring off · Turn on` opts in with one click. `open_console` answers `Not now` when SQLite consent is not active (which turns `invited` into `stopped`), so checks keep the consent they set up.
- The password input has no label or role; Playwright cannot find it by role `textbox`. Use the placeholder.
- The console decides "logged in" by probing `/aggregates`, so a backend that is down also shows the login form. Run doctor before blaming auth.
- `SESSION_SECRET` must be set or `/login` returns 500; the sandbox always sets it. A 500 here means the launch env drifted.
- Sessions are server-side (hashed id) and expire after 12 h; `POST /logout` (the console's `Log out` button) revokes one, and 5 failed logins from one client within 5 min get 429. No check here covers expiry, logout or the throttle (`tests/api` does); repeated wrong-password runs against one instance can hit the 429.
