# CallSafe: talk tracks

## 30-second version
"A scam call can get past every caller-ID filter and then simply ask for your code. CallSafe listens only on calls you've opted into, and when the caller asks for a code, money or access to your device, it texts you one line: what they're asking for and one safe step, which is to hang up and call back on a number you know. After the call, a second text teaches you the trick. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

## 3-minute version (timed to PRD §19.1)

The demo runs arm B with simulated SMS: texts appear in the console's phone frame and judges reply with its on-screen buttons. The Twilio trial account can't send our texts. Real SMS works through Twilio once the account is upgraded and registered; the code is ready (signed webhooks, fails closed). If asked, say so plainly.

**0:00-0:20 Problem (slide 1)**
"This call got past Scam Shield. The number looks fine. Thirty seconds in, the caller says: read me the code we just sent you. That's the moment the money goes, and nothing on your phone says a word."

**0:20-0:40 Replay 1, clinic (console)**
"Here's a clinic call. It mentions a code, but it tells you not to share it." (The phone frame stays empty.) "No alert. The console says 'no alert, not a safety verdict'. Silence never means a call is safe."

**0:40-1:50 Replay 2, bank (console phone frame)**
"Now a bank fraud call. It starts out normal..." (The caller asks for the code and the alert lands in the phone frame.) "That's the alert: 'caller is asking for a code. Don't share it. Hang up, call your bank's number yourself.' It names the request and gives one safe step." (The replay ends, the call ends automatically, and the follow-up arrives.) "After the call, the follow-up explains the trick: banks never ask for codes." (Point the judge to the reply buttons under the phone frame.) "Say we got it wrong. Press WRONG." (The console counter ticks.) "That goes to a person, and any change is tested before it goes live."

**1:50-2:25 Why panel and one number (console, then slide 3)**
"Every alert shows the exact sentence that set it off, highlights the words, and says why it's dangerous, here in the 'Why this alert' panel. The obvious way to build this is keyword matching. We tested both on 6,228 scripted calls written blind by AI agents that never saw our code. Keywords alerted on 64% of harmless calls. Our rules alerted on 0.9%, and caught 66% of the scams. They're scripts, not real calls, so no production claim." (Point to the "Where we fail" card.) "Here's what we still miss: about a third of scams, asked in words our rules weren't written for. An opt-in model from TypeSafe caught 99%, but it sends call text off the laptop, and its API is out of credit today."

**2:25-3:00 Stack and next steps (slide 4)**
"It's whisper speech-to-text and pure-Python rules, with Twilio texts, simulated here. We store counts, not audio, transcripts or numbers. T-Mobile already runs AI inside calls on any phone with Live Translation. Next we route on that path, add an in-call audio prompt, gate it on consent, and verify the sender. We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone."

**Reset between judges:** press the console Reset button. It never changes consent. If someone pressed STOP in the phone frame, press YES to re-enroll. (With real SMS, a STOPped phone texts START, or switch to the spare phone.) Only ever ask judges to press WRONG.
