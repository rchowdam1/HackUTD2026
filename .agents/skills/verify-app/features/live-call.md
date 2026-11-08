# Live call

A real phone call to the Twilio number is monitored like a replay (#94). Twilio calls `POST /voice/incoming`, which answers with TwiML `<Start><Stream url="{ws(s) PUBLIC_BASE_URL}/voice/stream" track="both_tracks"/>` and then `<Dial>DEMO_PHONE</Dial>`, so the two phones talk normally while Twilio streams 20 ms frames of 8 kHz mu-law for both sides. The socket cuts each side into utterances at a 0.7 s pause (8 s max), transcribes them with whisper in memory, and feeds them through the replay driver (`ingest._replay`), so the session gets the same arm as a replay: inbound track = caller, outbound = subscriber. The session finishes on the stream's `stop` or when the socket closes. Both endpoints check `X-Twilio-Signature` (the socket over the stream URL with no params) and fail closed when `TWILIO_AUTH_TOKEN` or `PUBLIC_BASE_URL` is unset.

## Sub-features

- `voice.signature-required` rejects unsigned and mis-signed `POST /voice/incoming` (403) and `/voice/stream` handshakes (403), and starts no session.
- `voice.incoming-twiml` answers a signed call webhook with a both-track stream to `/voice/stream`, then a dial to `DEMO_PHONE`.
- `voice.bank-live-stream` streams the bank call's WAVs as a signed Twilio Media Stream in real time: every segment is `source: asr`, both speakers appear, ALERT-OTP-01 fires, the session finishes, and the console shows the transcript.

## How to get to it (user POV)

- `scripts/demo_up` points the `TWILIO_FROM` number's "A call comes in" webhook at `POST {PUBLIC_BASE_URL}/voice/incoming`.
- Call the Twilio number from any phone; `DEMO_PHONE` rings; talk. The console shows the call live (no Run button).

## Driving it with verify.py

Preconditions:

- `voice.signature-required` and `voice.incoming-twiml`: profile `cached`; the sandbox sets `TWILIO_AUTH_TOKEN` and `PUBLIC_BASE_URL=http://127.0.0.1:<port>`, so the stream URL is `ws://127.0.0.1:<port>/voice/stream`. The harness signs with its own implementation (`twilio_signature`).
- `voice.bank-live-stream`: profile `asr` (whisper `small.en` cached, else BLOCKED) and the console.

- **Signature.** POST `/voice/incoming` unsigned and with one corrupted character: 403. Open `/voice/stream` without `x-twilio-signature` and with a corrupted one: the handshake gets 403. No `session` event within 1 s.
- **TwiML.** Signed POST: 200 `text/xml`; `Response` children are exactly `Start`, `Dial`; `Start/Stream` url = stream URL, `track="both_tracks"`; `Dial` = `DEMO_PHONE`.
- **Stream.** Reset, opt in, open the console. Encode `audio/demo/bank/tNN.wav` to mu-law with the stdlib (`audioop.lin2ulaw`, not the app's decoder), send `connected`, `start`, then `media` frames paced at 20 ms (the speaking side carries the audio, the other side silence, 0.8 s of silence after each turn), then `stop`. Within 60 s: `session finished`; every segment `source: asr`; speakers include caller and subscriber; seq 1..n; decisions exactly `[ALERT-OTP-01]`; `Live transcript` contains the first segment's text, no `cached transcript` tag.
- **Proof.** `report.json`, `artifacts/voice.bank-live-stream--live-segments.json`, `screenshots/voice.bank-live-stream--live-finished.png`.

## Gotchas

- `app.main`'s tunnel filter is HTTP middleware and never sees WebSocket handshakes, so `/voice/stream` is reachable through the tunnel and its signature check is the only gate. Keep `voice.signature-required` passing.
- The signed URL is exactly the `url` in the TwiML (`wss://<tunnel host>/voice/stream` live). A `PUBLIC_BASE_URL` that doesn't match the tunnel shows up as a refused stream while the call itself still connects (unmonitored).
- Which party is on which track is Twilio's: inbound = the party who called the Twilio number. Confirmed only by a real call (external, see `coverage.json`).
- Whisper text is not byte-stable; assert source, speakers, decision, not exact words.
