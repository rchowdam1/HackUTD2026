# CallSafe: talk tracks

## 30-second version
"A scam call can get past every caller-ID filter and then simply ask for your code. CallSafe listens only on calls you've opted into, and when the caller asks for a code, money or access to your device, it texts you one line: what they're asking for and one safe step, which is to hang up and call back on a number you know. After the call, a second text teaches you the trick. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

## 3-minute version (timed to PRD §19.1)

**0:00-0:20 Problem (slide 1)**
"This call got past Scam Shield. The number looks fine. Thirty seconds in, the caller says: read me the code we just sent you. That's the moment the money goes, and nothing on your phone says a word."

**0:20-0:40 Replay 1, clinic (console)**
"Here's a clinic call. It mentions a code, but it tells you not to share it." (Phone stays silent.) "No alert. The console says 'no alert, not a safety verdict'. Silence never means a call is safe."

**0:40-1:50 Replay 2, bank (console plus phone)**
"Now a bank fraud call. It starts out normal..." (The caller asks for the code and the phone buzzes.) "That buzz is the alert: 'caller is asking for a code. Don't share it. Hang up, call your bank's number yourself.' It names the request and gives one safe step." (The replay ends, the call ends automatically, and the follow-up arrives.) "After the call, the follow-up explains the trick: banks never ask for codes." (Hand over the phone with the thread open.) "Say we got it wrong. Type WRONG." (The console counter ticks.) "That goes to a person, and any change is tested before it goes live."
- If a text hasn't arrived 10 s after it was sent: flip the SMS mode toggle to simulated and say "switching to simulated SMS for the hall".

**1:50-2:25 Why panel and one number (console, then slide 3)**
"Every alert cites the rule that fired, here in the 'Why this alert' panel. The obvious way to build this is keyword matching. On calls that only mention codes or money, keywords alerted on 6 of 22; we alerted on none of 22. But we caught only 5 of 30 of the scams. That's 60 held-out scripted calls written blind by an AI agent that never saw the rules. It's small, and we say so." (Point to the "Where we fail" card.) "Here's what we still miss: scams that ask in words our rules weren't written for. We catch 19 of 20 on the calls we tuned on and 5 of 30 on calls we never saw. That gap is our next job, and it's why a person reviews every change."

**2:25-3:00 Stack and next steps (slide 4)**
"It's whisper speech-to-text and pure-Python rules, with Twilio for the texts. We store counts, not audio, transcripts or numbers. T-Mobile already runs AI inside calls on any phone with Live Translation. Next we route on that path, add an in-call audio prompt, gate it on consent, and verify the sender. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

**Reset between judges:** press the console Reset button. It never changes consent. If the phone was STOPped, text START from it or switch to the spare phone. Only ever ask judges to type WRONG.
