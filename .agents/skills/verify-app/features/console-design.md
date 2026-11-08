# Console design

The console follows `DESIGN.md` (Light Mirror): three columns (controls, the live transcript, the Why panel over the phone), a separate `The numbers` page (blind test, dev set from `results/latest.json`, live-call speed), and a ticker with one entry per turn. Magenta marks only the request CallSafe acted on, the alert, the WRONG key and the primary action.

## Sub-features

- `design.fit-and-accent` runs the bank replay to its end, then at 1440x900 and 1920x1080: no page scroll, three columns, the alert bubble fully inside the phone screen, no magenta outside the allowed elements and no `--magenta` text under 24px. The call screen has no results band.
- `numbers.page` opens `The numbers` from the top bar: the blind-test table, the dev table with every arm's hard-benign false alerts from `GET /results/latest` (labelled as the set the rules were tuned on), the no-production-claim line, no sideways scroll at 1440x900 / 1280x720 / 390x844, and `Back to the call`.
- `ticker.turns` runs the bank replay to its end: one `turn` SSE event per transcript line; the ticker lists one entry per turn (speaker, AI verdict, `N ms` to decide) plus one per text, with an ALERT entry for the alert text; it scrolls by default and stops under `prefers-reduced-motion`.

## How to get to it (user POV)

- Log in, click `Run bank`, wait for `call ended`. Resize the window; look at the ticker at the bottom; open `The numbers` from the top bar.

## Driving it with verify.py

Preconditions: profile `cached`, demo phone opted in (`ctx.ensure_opted_in()`).

- **Fit.** `document.documentElement.scrollHeight <= innerHeight` and `scrollWidth <= innerWidth` at both sizes, after the alert (the phone and Why panel are fullest then).
- **Accent.** The audit (`MAGENTA_AUDIT` in `checks.py`) walks every visible element whose own text, background or border is `#E20074` / `#C8006A` and requires an ancestor in `MAGENTA_ALLOWED`. Focus rings are outlines and aren't audited.
- **Ticker.** Read the first `.ticker-list` (the second is an `aria-hidden` copy for the loop). Turn events are emitted for every line, so counts match the transcript.
- **Proof.** `screenshots/design.fit-and-accent--bank-alert-1440.png`, `...-1920.png`, `artifacts/design.fit-and-accent--magenta-*.json`, `artifacts/ticker.turns--ticker.json`, `screenshots/ticker.turns--ticker.png`.

## Gotchas

- Wait for `call ended` before measuring: the console types the last line over its audio, after `session finished`.
- `MAGENTA_ALLOWED` is the DESIGN.md rule written as selectors; a new magenta element needs a DESIGN.md reason first, then a selector here.
