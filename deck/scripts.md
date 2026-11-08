# CallSafe: talk tracks

Every number here comes from one of two sources, named each time: the dev set (`results/latest.md`, 40 scripted calls the rules were tuned on) or the blind H4 set (6228 scripted calls, see `slides.md`). Don't quote any other number. Don't quote a latency number: the console shows the measured one.

## 30-second version
"A scam call can get past every caller-ID filter and then simply ask for your code or your money. CallSafe listens only on calls you've opted into, and when the caller asks for a code, money or access to your device, it texts you one line during the call: what they're asking for and one safe step, which is to hang up and call back on a number you know. After the call, a second text teaches you the trick. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

## What is real in the demo (say it if asked, never overstate it)
- **The call is real.** The judge dials a Twilio number we own. Twilio forwards the call to the subscriber's phone (Arnav's, `DEMO_PHONE`) and sends both sides' audio to the laptop. It is not a carrier integration.
- **Speech-to-text is real and local.** faster-whisper runs on the laptop.
- **The AI is real and leaves the laptop.** The demo runs arm C: each caller turn, plus up to three turns before it, goes to OpenRouter (Perplexity Decider). The laptop stores no audio and no transcripts.
- **The alert text is sent to Twilio for real, but it doesn't arrive.** Twilio accepts it, then US carriers block it: Twilio error 30034, because our number's 10DLC registration isn't done, and that takes days. The console's Phone panel (tagged "real SMS") mirrors every text we sent, and once Twilio reports back the bubble reads "Blocked by carrier (30034)". Say it plainly: Twilio took it, the carrier refused it. Never say a text arrived on a phone.
- **Speed:** the target is the alert text sent within 2 seconds of the end of the caller's flagged sentence. The Why panel's "Speed" line shows how long it took. Say "the console shows how long it took", never a number.

## 3-minute version: the live call

**Before the judge arrives:**
- Console open and logged in; the opt-in prompt answered **Yes** (consent active).
- **SMS mode: real** (the "real" button is lit and the Phone panel reads "real SMS"). If it says simulated, the Twilio and 30034 lines below are false: switch it or don't say them.
- Arm C on (`INTENT_MODEL=on`, OpenRouter key set). Once the call starts, the call clock reads "Rules + Perplexity Decider".
- Arnav's phone unlocked, ringer on, **not on speaker**. The spare phone and the printed scripts on the table.

Timings below are `say -r 150` machine reads of the spoken lines (150 words per minute) plus the call itself; pointing and pauses aren't in them. Rehearse once with a stopwatch and write the real times next to these.

**0:00-0:15 Problem (slide 1)** (38 words, 13 s)
"This call got past Scam Shield. The number looks fine. Thirty seconds in, the caller asks for money or a code. That's when the money goes, and your phone says nothing. Let's do it live. You're the scammer."

**0:15-0:30 Set up the call** (29 words, 11 s, said while the judge dials)
Hand the judge the grandson script and the number card (or the spare phone). "Call this number and read the caller lines. Arnav plays Grandma. The number is ours on Twilio. It forwards to Arnav's phone and streams the audio to this laptop."

**0:30-1:15 The grandson call (console)** (presenter silent; the recorded call is 28.6 s of speech, plus ring, answer and the model's verdict)
Arnav answers with the phone at his ear, not on speaker. **The presenter says nothing while the call is live**: the judge's phone and Arnav's phone both hear the room, and anything they pick up becomes a transcript turn that goes to OpenRouter. Point instead:
- Point at the transcript (tagged "Phone call") as both sides appear.
- After the car-accident line, point at the empty Why panel. No words.
- On the bank-and-cash line the alert fires. Point at "Caught by" and the outgoing text.
- Arnav says his last line and hangs up.

**1:15-1:40 What just happened (console)** (56 words, 25 s)
"Both sides, transcribed live on this laptop. Our rules stayed silent: no code, no dollar amount. Perplexity Decider caught it." (Read the percentage after "Caught by" as it shows: "N percent sure". Never promise a number.) "Here's the text we sent. Twilio accepted it; US carriers block it until our number's registration is done, so it reads carrier blocked. Speed shows how long it took. And the follow-up explains the trick."

**1:40-2:25 The numbers (slide 3)** (80 words, 43 s: spoken numbers are slow)
"Keyword matching is the obvious build. On 40 dev calls we tuned on, keywords false-alert on 11 of 13 tricky harmless calls; our rules, with or without AI, on none. All three catch all 20 scams, so dev shows no AI gain. On 6,228 blind scripted calls, keywords caught 84.3% of scams but alerted on 64.4% of harmless calls. Our rules: 65.9% caught, 0.9% false alerts. With AI, 99.2% caught, 0.3% false, measured with our previous model, not this one."

**2:25-3:00 Stack and close (slide 4)** (79 words, 31 s)
"A Twilio number, whisper on the laptop, Python rules, and Perplexity Decider through OpenRouter. We store counts, not audio or transcripts. Next: the Live Translation path for any phone, an in-call voice prompt, and finished registration so the text arrives. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

Spoken total: 282 words, 2:02 by machine read, plus about 45 s for ringing, the call and the model's verdict: about 2:47. If the rehearsal runs long, cut "Keyword matching is the obvious build." and "We store counts, not audio or transcripts." (the slide and the Q&A card carry both).

## Printed caller script: the grandson call (hand this to the judge)

You are the caller. Read your lines; Arnav answers as Grandma. Wait for Arnav to finish before your next line.

> **CALLER (you):** Grandma? It's me, Danny. I'm in trouble and I don't know who else to call.
>
> **GRANDMA (Arnav):** Danny? Oh my goodness, what happened?
>
> **CALLER (you):** I hit another car and the police are holding me. The lawyer says I can go home today if we sort it out.
>
> **CALLER (you):** Could you go to the bank, take out whatever you can spare, and hand it to the man he sends to your house? Please don't tell Mom.
>
> **GRANDMA (Arnav):** Oh, sweetheart. Okay, let me find my purse.

(Lines are verbatim from `scenarios/demo/family/transcript.json`. The two caller lines in a row are on purpose: read them as one turn each, with a short pause between.)

## Backup caller script: the bank call

Use it for a second judge at the table, or when the AI is down: rules catch this one on their own.

> **CALLER (you):** Hi, this is the fraud team at your bank. We stopped a suspicious charge on your debit card.
>
> **YOU (Arnav):** Oh no. What was it?
>
> **CALLER (you):** An online purchase we put on hold. To cancel it, I need to verify it's really you.
>
> **CALLER (you):** I just sent a code to your phone. Can you read it back to me?
>
> **YOU (Arnav):** Um, okay, hold on.

(Verbatim from `scenarios/demo/bank/transcript.json`.) The alert is "caller is asking for a code. Don't share it. Hang up, call your bank's number yourself."

## Fallback ladder (say which rung you're on, out loud)

1. **Phone network fails** (the call doesn't connect, drops, or no transcript shows within a few seconds): "The phone network isn't cooperating, so we'll use the laptop mic. Same pipeline, same AI." Press **Start live conversation**. The judge taps **Caller**, reads a line and taps it again to send it; Arnav does the same with **You**. The transcript is tagged "Live mic". Press **End call** when done (that sends the follow-up).
2. **Mic fails too:** "Here's a recording of the same call." Press **Run grandson**. It replays a recorded call through the same pipeline. Say it's a recording.
3. **The AI is down** (an "AI unavailable, rules only" badge on the turn, or "Caught by" reads "CallSafe rules" on a call the AI should have caught): say so. The rules still alert on code, money and access requests they recognise, so switch to the bank script, which the rules catch. Don't claim the grandson catch on that run.

Never pretend a lower rung is a live phone call.

## Console labels this script quotes
Checked against this branch's console: "Run grandson", "Start live conversation", "Caller" / "You", "End call", "Reset", "Log out", "SMS mode" real/simulated, the header "call running" and "Monitoring off · Turn on", the call clock "Rules + Perplexity Decider", the transcript tags "Phone call" / "Live mic" / "cached transcript", the Why panel's "Caught by", "Speed", the Phone panel's "real SMS" tag, "AI unavailable, rules only", and the 30034 wording above.

## Reset between judges
- Hang up both phones.
- Press the console **Reset** button. It cancels the call session and pending sends and clears the transcript. It never changes consent.
- If the header says "Monitoring off" (someone said STOP or No), press **Turn on** next to it. If a phone texted STOP for real, Twilio blocks texts to it until it texts START, so use the spare phone instead.
- Check **SMS mode** is still **real**.
- Check the arm: on the next call the call clock must read "Rules + Perplexity Decider". If it doesn't, say the demo is running on rules only and use the bank script.
- Put the printed scripts back face up for the next judge.
