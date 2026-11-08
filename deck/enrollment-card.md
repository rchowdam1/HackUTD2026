# Enrollment card (printed at the table, PRD §19.5)

CallSafe analyses audio of your own calls only after you reply YES; texts are sent only when a call asks for codes, money or access; msg and data rates may apply; reply STOP to end, HELP for help.

If the intent model (arm C) is switched on: each caller turn and up to three turns before it are sent through OpenRouter (openrouter.ai) to an AI decision model for analysis; CallSafe doesn't store them. It is off unless this line is shown.

**CallSafe only ever says stop and check. Any text saying a caller is fine, or asking for codes, money or info, is not us.**

Printing note (not on the card): the demo runs arm B, so print without the arm C line. With real SMS, Twilio handles STOP itself and blocks further texts to that phone.
