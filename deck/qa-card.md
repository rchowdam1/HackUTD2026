# Q&A card (one sentence each, PRD §19.8)

- **Live Translation?** It proves T-Mobile can run AI inside calls on any phone; we point that same path at scam requests.
- **Pixel already does this?** Pixel says "Likely scam" on some Android phones; we name the request, give a safe step, teach the trick, and reach any phone, including iPhones.
- **Who reads a text mid-call?** The buzz is the interrupt and the text is one line; the follow-up exists because many won't read it until after; an in-call audio prompt on the Live Translation path is next.
- **Is the text real?** Simulated in the console today because Twilio's trial account can't send our texts; real SMS through Twilio is built (signed webhooks, fails closed) and works once the account is upgraded.
- **So you transcribe all my calls?** Only for opted-in subscribers, processed in memory and dropped when the call ends; we store no audio, transcripts or numbers, only counts; the opt-in arm C sends call text to OpenRouter, and the demo doesn't use it.
- **Can scammers fake your text?** Yes, which is why our texts only ever say stop and check; a fake that copies us gives safe advice, and one that says "go ahead" breaks our one rule.
- **Is listening legal?** Subscriber opt-in is necessary but not sufficient; caller notice in all-party-consent states is a gate before any real customer.
- **How good is it?** On 6228 scripted calls written blind by AI agents with no repo access, keywords caught 84.3% of scams but alerted on 64.4% of harmless calls, our rules (the demo) caught 65.9% with 0.9% false alerts, and the opt-in model arm caught 99.2% with 0.3% (measured on the pre-merge branch, measured with TypeSafe Jev 1.14, the previous arm C model; not yet re-measured with Decider V1.2); scripts, not real calls or ASR, so no production claim.
- **What if the AI is wrong?** A false alarm costs one callback; silence is never a safety verdict; WRONG replies go to a human-approved, tested policy change.
- **Why trust AI at all?** In the demo pure-Python rules decide; the opt-in arm C model can alert on its own, but every alert cites a rule ID and the advice is safe even if we're wrong.

Q&A-only material: family-impersonation paraphrase (model path, arm C), gate board, full K/B/C table.
