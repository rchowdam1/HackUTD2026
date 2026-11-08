# CallSafe: talk tracks

Every number here comes from one of two sources, named each time: the dev set (`results/latest.md`, 40 scripted calls the rules were tuned on) or the blind H4 set (6228 scripted calls, see `slides.md`). Don't quote any other number. Don't quote a latency number: the console shows the measured one.

## 30-second version
"A scam call can get past every caller-ID filter and then simply ask for your code or your money. CallSafe listens only on calls you've opted into, and when the caller asks for a code, money or access to your device, it texts you one line during the call: what they're asking for and one safe step, which is to hang up and call back on a number you know. After the call, a second text teaches you the trick. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

## What is real in the demo (say it if asked, never overstate it)
- **The call is real.** The judge dials a Twilio number we own. Twilio forwards the call to the subscriber's phone (Arnav's, `DEMO_PHONE`) and sends both sides' audio to the laptop. It is not a carrier integration.
- **Speech-to-text is real and local.** faster-whisper runs on the laptop.
- **The AI is real and leaves the laptop.** The demo runs arm C: each caller turn, plus up to three turns before it, goes to OpenRouter (Perplexity Decider). The laptop stores no audio and no transcripts.
- **The alert text is sent through Twilio for real, but it doesn't arrive.** US carriers currently block it: Twilio error 30034, because our number's 10DLC registration isn't done, and that takes days. The console's phone frame mirrors exactly what was sent and shows the real "not delivered" status. Never say a text arrived on a phone.
- **Speed:** the target is the alert text sent within 2 seconds of the end of the caller's flagged sentence. The console shows how long it took on each turn. Say "the console shows how long it took", never a number.

## 3-minute version: the live call

**Before the judge arrives:** console open, arm badge reads "rules + AI (Perplexity Decider)", consent active, Arnav's phone unlocked with the ringer on, the printed caller script on the table.

**0:00-0:20 Problem (slide 1)**
"This call got past Scam Shield. The number looks fine. Thirty seconds in, the caller asks for money or for the code we just texted you. That's the moment the money goes, and nothing on your phone says a word. Let's do it live. You're the scammer."

**0:20-0:35 Set up the call**
Hand the judge the grandson script and the number card. "Call this number and read the caller lines. Arnav plays your grandma." (If the judge would rather not use their own phone, hand them the spare.) Arnav's phone rings and he answers on speaker. "That number is ours on Twilio. It forwards the call to Arnav's phone and sends the audio to this laptop."

**0:35-1:35 The grandson call (console)**
The judge reads the lines and Arnav answers. Point at the transcript as both sides appear. "Both sides, transcribed live on this laptop." After the judge's car-accident line: "Nothing yet. There's no code and no dollar amount, and our rules alone stay silent on this whole call." On the bank-and-cash line, the alert fires mid-call: "There. Perplexity Decider is" (read the percentage the console shows) "sure the caller wants money. That's the AI moment: rules alone miss this call." Point at the phone frame: "That's the text we sent: 'caller is asking for money. Don't pay. Hang up, call them back on a number you know.' It went out through Twilio for real. US carriers are blocking it today because our number's registration isn't done, so this frame shows exactly what we sent and the real status, not delivered." Point at the turn row: "The console shows how long it took."

**1:35-2:00 Hang up, follow-up, Why panel (console)**
Arnav hangs up. The follow-up appears in the phone frame. "After the call, the follow-up explains the trick: scammers rush you, real people let you call back." Point at "Why this alert": "Every alert quotes the line that set it off and says why it matters. Here it says the model caught it, not the rules."

**2:00-2:35 The numbers (slide 3)**
"The obvious way to build this is keyword matching. On our dev set, 40 scripted calls we tuned the rules on, keywords false-alert on 11 of 13 tricky harmless calls; our rules and rules plus AI on 0 of 13; all three catch all 20 scams. Dev shows no AI gain because we tuned the rules on it. On 6,228 scripted calls written blind by AI agents that never saw our code, keywords alerted on 64.4% of harmless calls. Our rules alerted on 0.9% and caught 65.9% of scams. With AI, 99.2% caught and 0.3% false alerts, but that was measured before our last merge with the previous model, TypeSafe Jev, not the Perplexity Decider you just saw. They're scripts, not real calls, so no production claim." (Point to "Where we fail".) "The rules miss about a third of the blind scams. The grandson call is that kind of miss, and that's what the AI is for."

**2:35-3:00 Stack and next steps (slide 4)**
"A Twilio number, whisper on the laptop, Python rules, and Perplexity Decider through OpenRouter. We store counts, not audio or transcripts. T-Mobile already runs AI inside calls on any phone with Live Translation. Next we route on that path, add an in-call audio prompt, gate it on consent, and finish sender registration so the text arrives. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

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

1. **Phone network fails** (the call doesn't connect, drops, or no transcript shows within a few seconds): "The phone network isn't cooperating, so we'll use the laptop mic. Same pipeline, same AI." Press **Live (mic)** in the console and have the judge read the same script into the laptop, push-to-talk, Arnav answering.
2. **Mic fails too:** "Here's a recording of the same call." Press **Run grandson**. It replays a recorded call through the same pipeline. Say it's a recording.
3. **The AI is down** (the turn shows the "AI unavailable, rules only" badge): say so. The rules still alert on code, money and access requests they recognise, so switch to the bank script, which the rules catch. Don't claim the grandson catch on that run.

Never pretend a lower rung is a live phone call. The console's session source says which one is running: phone, mic or replay.

## Reset between judges
- Hang up both phones.
- Press the console **Reset** button. It cancels the call session and pending sends and clears the transcript. It never changes consent.
- Check the consent state is active. If a phone was STOPped, switch SMS mode to simulated and press YES in the phone frame, or swap to the spare phone.
- Check the arm badge still reads "rules + AI (Perplexity Decider)". If it doesn't, say the demo is running on rules only and use the bank script.
- Put the printed scripts back face up for the next judge.
