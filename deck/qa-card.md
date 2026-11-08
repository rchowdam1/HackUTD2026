# Q&A card (one sentence each, PRD §19.8)

- **Is the text real?** It's sent through Twilio for real, but US carriers block it today (Twilio error 30034: our number's 10DLC registration isn't done, which takes days), so the phone frame shows exactly what we sent and the real "not delivered" status; no text reached a phone.
- **Is this a real call?** Yes: you called a Twilio number we own, which forwards to Arnav's phone and streams the audio to this laptop; it's not a carrier integration, and if the phone network fails we say so and switch to the laptop mic or a recorded replay.
- **What leaves the laptop?** The live demo runs rules + AI, so each caller turn plus up to three turns before it goes to OpenRouter (Perplexity Decider), the alert text goes to Twilio, and the call itself runs through Twilio; speech-to-text runs on the laptop, which stores no audio or transcripts, only counts and hashed numbers.
- **How fast?** The target is the alert text sent within 2 seconds of the end of the caller's flagged sentence, and the console shows how long it took on every turn.
- **What if the AI is down?** The turn shows an "AI unavailable, rules only" badge, and the rules still alert on the code, money and access requests they recognise; they'd miss the grandson call, so we'd show the bank call instead.
- **Live Translation?** It proves T-Mobile can run AI inside calls on any phone; we point that same path at scam requests.
- **Pixel already does this?** Pixel says "Likely scam" on some Android phones; we name the request, give a safe step, teach the trick, and reach any phone, including iPhones.
- **Who reads a text mid-call?** The buzz is the interrupt and the text is one line; the follow-up exists because many won't read it until after; an in-call audio prompt on the Live Translation path is next.
- **So you transcribe all my calls?** Only for opted-in subscribers, processed in memory and dropped when the call ends; we store no audio, transcripts or raw numbers, only counts, and with the AI on, call text goes to OpenRouter as above.
- **Can scammers fake your text?** Yes, which is why our texts only ever say stop and check; a fake that copies us gives safe advice, and one that says "go ahead" breaks our one rule.
- **Is listening legal?** Subscriber opt-in is necessary but not sufficient; caller notice in all-party-consent states is a gate before any real customer.
- **How good is it?** On the blind H4 set (6228 scripted calls written by AI agents that never saw our code), keywords alerted on 64.4% of harmless calls and our rules on 0.9%, catching 65.9% of scams; rules + AI caught 99.2% with 0.3% false alerts, measured on the pre-merge branch with TypeSafe Jev 1.14, the previous model, not re-measured with Perplexity Decider V1.2; scripts, not real calls, so no production claim.
- **Does the AI help?** On the dev set (40 scripted calls the rules were tuned on) keywords false-alert on 11 of 13 hard-benign calls, rules and rules + AI on 0 of 13, and all three catch 20 of 20 scams, so dev shows no AI gain because the rules were tuned on it; the gain shows on calls like the grandson one, which the rules alone miss.
- **What if the AI is wrong?** A false alarm costs one callback; silence is never a safety verdict; WRONG replies go to a human-approved, tested policy change.
- **Why trust AI at all?** Every alert shows the line that set it off and who caught it, rules or model, and the advice is the same safe step even if we're wrong.

Q&A-only material: gate board, full K/B/C table.
