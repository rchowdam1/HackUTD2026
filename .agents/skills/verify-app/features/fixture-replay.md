# Fixture replay

Opening the console with `?fixtures` replays Track A's example events from `tests/fixtures/events/` without a backend or login. It exists so the console can be rehearsed and developed when the backend is down; it is labelled "fixture replay" and the controls are disabled.

## Sub-features

- `fixtures.console-replay` renders the fixture transcript under a "fixture replay" tag, with controls disabled and no backend calls.

## How to get to it (user POV)

- Open `<console>/?fixtures`.

## Driving it with verify.py

Preconditions:

- The Vite console is running (any profile with UI). No login.

- **Open.** Fresh browser context (no cookie), go to `<console>/?fixtures`. Text `fixture replay` is visible; button `Run bank` is disabled.
- **Replay.** Within 15 s the `Live transcript` card contains the `payload.text` of `tests/fixtures/events/segment.json`.
- **No backend.** No request to `/events`, `/aggregates`, `/results` or `/demo` was made by the page.
- **Proof.** `screenshots/fixtures.console-replay--fixtures.png`.

## Gotchas

- Fixtures are bundled by Vite's `import.meta.glob`; a fixture added while Vite runs may need a reload.
- Events replay in `event_id` order every 700 ms; the reset fixture is skipped on purpose.
