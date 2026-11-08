"""Minimal pairs for app.rules (written for these tests, not taken from any scenario file)."""
import pytest

from app import intent
from app.models import RiskEvent, Scenario, Segment
from app.rules import decide, detect

V = "v1.0"


@pytest.fixture(autouse=True)
def model_off(monkeypatch):
    """Arm C here is B plus a stubbed (or absent) model: never call the live API, even under INTENT_MODEL=on."""
    monkeypatch.delenv("INTENT_MODEL", raising=False)


def call(*turns, ref=None):
    """turns: plain strings are the caller; ("subscriber", text) tuples are the subscriber."""
    out = []
    for i, t in enumerate(turns, 1):
        speaker, text = t if isinstance(t, tuple) else ("caller", t)
        out.append(Segment(session_ref=ref, seq=i, speaker=speaker, text=text, source="script"))
    return out


def alerts(segments, arm):
    return [d.template_id for d in decide(segments, arm, V) if d.level == "action_warning"]


# (category alert, risky request, benign twin) pairs: K fires on both, B only on the request.
PAIRS = {
    "otp negation": ("ALERT-OTP-01",
                     "Please read the verification code to me.",
                     "Please don't read the verification code to anyone."),
    "otp never ask": ("ALERT-OTP-01",
                      "I need you to tell me your PIN now.",
                      "We will never ask you to tell us your PIN."),
    "otp direction": ("ALERT-OTP-01",
                      "Can you give me the password you set up?",
                      "I'll give you a temporary password at the end of the call."),
    "otp speaker": ("ALERT-OTP-01",
                    "What's the six digit code on your screen?",
                    ("subscriber", "What's the six digit code they mentioned?")),
    "otp hedge": ("ALERT-OTP-01",
                  "Just text me the passcode.",
                  "If anyone asks you to text them a passcode, hang up."),
    "pay negation": ("ALERT-PAY-01",
                     "You need to buy two gift cards at the pharmacy.",
                     "You should never buy gift cards to pay a bill."),
    "pay direction": ("ALERT-PAY-01",
                      "Send the bail money by Western Union to me today.",
                      "Western Union will send you a receipt by mail."),
    "pay speaker": ("ALERT-PAY-01",
                    "Can you wire the funds to our safe account this afternoon?",
                    ("subscriber", "Can you wire the funds to my safe account this afternoon?")),
    "pay hedge": ("ALERT-PAY-01",
                  "Go ahead and pay with Zelle.",
                  "Scammers often ask you to pay with Zelle."),
    "remote negation": ("ALERT-REMOTE-01",
                        "Please install TeamViewer so we can fix it.",
                        "Please do not install TeamViewer from a pop-up."),
    "remote direction": ("ALERT-REMOTE-01",
                         "Let me connect to your computer through remote support.",
                         "Our store offers remote support if you book a visit."),
    "remote speaker": ("ALERT-REMOTE-01",
                       "Could you download AnyDesk for me?",
                       ("subscriber", "Could you download AnyDesk for me?")),
    "remote hedge": ("ALERT-REMOTE-01",
                     "Open quick assist and click allow.",
                     "If someone tells you to open quick assist, hang up."),
    # Added with the dev-set tuning (#12).
    "otp negation aside": ("ALERT-OTP-01",
                           "Right now, give me your PIN.",
                           "Please do not, for any reason, give your PIN to us."),
    "otp comma ends negation": ("ALERT-OTP-01",
                                "Don't panic, tell me the PIN on the card.",
                                "Don't tell me the PIN on the card."),
    "otp negated recipient": ("ALERT-OTP-01",
                              "Share the passcode with me.",
                              "Share the passcode with nobody."),
    "otp won't you": ("ALERT-OTP-01",
                      "Won't you read me the code?",
                      "I won't read you the code."),
    "otp intro phrase": ("ALERT-OTP-01",
                         "To finish the upgrade, read out the code we texted.",
                         "To finish the upgrade, type the code we texted into the app."),
    "otp confirm": ("ALERT-OTP-01",
                    "Before we continue, confirm the PIN you got by mail.",
                    "Before we continue, we confirmed the PIN you got by mail."),
    "otp i need": ("ALERT-OTP-01",
                   "I just need the one-time PIN from the letter.",
                   "You just need the one-time PIN from the letter."),
    "otp what does it say": ("ALERT-OTP-01",
                             "I texted you a four digit number. What does it say?",
                             "I texted you a four digit number. Did it arrive?"),
    "pay you can": ("ALERT-PAY-01",
                    "You can settle the fine with gift cards.",
                    "You can't settle a fine with gift cards."),
    "pay yes filler": ("ALERT-PAY-01",
                       "Yes, then wire it to the holding account.",
                       "Yes, the bank will wire it to the holding account."),
    "remote lets me see": ("ALERT-REMOTE-01",
                           "This lets me see your screen.",
                           "This lets you see your screen."),
    "remote hedge someone may": ("ALERT-REMOTE-01",
                                 "You need to install AnyDesk.",
                                 "Someone may call and say you need to install AnyDesk."),
    # Semantic-class broadening (#67): objects without the classic keywords, indirect forms.
    "otp what is it": ("ALERT-OTP-01",
                       "Is your account PIN still the same? What is it?",
                       "Is your account PIN still the same? Good."),
    "otp what it says": ("ALERT-OTP-01",
                         "The app will text you a code. Just shoot me back what it says.",
                         "The app will text you a code. Just type in what it says."),
    "otp policy statement": ("ALERT-OTP-01",
                             "I need you to read me your PIN.",
                             "Nobody here will ever ask you to read us your PIN."),
    "pay you'll send": ("ALERT-PAY-01",
                        "You'll send two thousand dollars to the holding account.",
                        "You'll get a text when the two thousand dollars arrive."),
    "pay amount in words": ("ALERT-PAY-01",
                            "I need eleven hundred for the flight.",
                            "I needed eleven hundred for the flight, but I sorted it out."),
    "pay how will you pay": ("ALERT-PAY-01",
                             "The fee is three hundred. How will you be paying?",
                             "The fee is waived. You won't be paying anything."),
    "pay reported wish": ("ALERT-PAY-01",
                          "Send me the money by Zelle.",
                          "Mom said you wanted to send me money, but please don't."),
    "pay wire fraud": ("ALERT-PAY-01",
                       "Wire the money to the escrow account today.",
                       "Wire fraud is common at closings, so call your title company."),
    "remote hop on": ("ALERT-REMOTE-01",
                      "Let my technician hop on your computer for a minute.",
                      "My technician can't hop on your computer, so bring it in."),
    "remote sideload": ("ALERT-REMOTE-01",
                        "Install our app and allow unknown sources.",
                        "Never install apps from unknown sources."),
    "remote negated object": ("ALERT-REMOTE-01",
                              "Click the link and share your screen with me.",
                              "Click the link in your email. You don't need to share your screen."),
}


@pytest.mark.parametrize("name", PAIRS)
def test_minimal_pair(name):
    template, risky, benign = PAIRS[name]
    assert alerts(call(risky), "B") == [template]
    assert alerts(call(benign), "B") == []
    assert alerts(call(risky), "K") == [template]
    assert alerts(call(benign), "K") == [template]


def test_clinic_silent_under_b_fires_under_k():
    clinic = call("Hello, this is Riverside Clinic about tomorrow's appointment.",
                  "We texted you a check-in code. Don't share your code with anyone, just show it at the desk.",
                  ("subscriber", "Okay, thanks."))
    assert alerts(clinic, "B") == []
    assert alerts(clinic, "C") == []
    assert alerts(clinic, "K") == ["ALERT-OTP-01"]


def test_bank_fires_otp_under_both_arms():
    bank = call("This is the fraud team at your bank. We blocked a charge.",
                "I just sent a security code to your phone.",
                ("subscriber", "Okay, I see it."),
                "Read me the code so I can confirm it's you.")
    for arm in "KB":
        assert alerts(bank, arm) == ["ALERT-OTP-01"]


def test_otp_fixture_scenario(fixtures_dir):
    scenario = Scenario.model_validate_json((fixtures_dir / "scenario_otp.json").read_text())
    segs = call(*[(t.speaker, t.text) for t in scenario.turns])
    for arm in "KB":
        assert alerts(segs, arm) == ["ALERT-OTP-01"]


def test_dialogue_state_resolves_pronoun_from_earlier_turn():
    segs = call("I sent a code to your phone.", ("subscriber", "Got it."), "Great, read it to me.")
    (event,) = detect(segs, "B", V)
    assert (event.rule_id, event.confidence_class, event.span_seq) == ("B-OTP-CTX-01", "medium", [1, 3])
    # Out of the context window: the pronoun no longer resolves.
    far = call("I sent a code to your phone.", ("subscriber", "One sec."), "Hold on.", "Still there?",
               ("subscriber", "Yes."), "Great, read it to me.")
    assert detect(far, "B", V) == []


def test_negation_scope_ends_at_a_new_clause():
    assert alerts(call("Don't hang up, just read me the code."), "B") == ["ALERT-OTP-01"]
    assert alerts(call("Never share your code with anyone, but you can read it to me."), "B") == ["ALERT-OTP-01"]
    assert alerts(call("Never, ever share your code."), "B") == []
    assert alerts(call("Please do not, under any circumstances, share your code with me."), "B") == []
    assert alerts(call("Never, just read me the code."), "B") == ["ALERT-OTP-01"]


def test_negated_recipient_scopes_to_the_matched_request():
    # A secrecy instruction after "and" doesn't negate the request before it.
    for template, text in (("ALERT-OTP-01", "Read me the code and share it with nobody else."),
                           ("ALERT-REMOTE-01", "Download AnyDesk and talk to nobody about this."),
                           ("ALERT-OTP-01", "Tell me the PIN, then share it with no one.")):
        for arm in "KB":
            assert alerts(call(text), arm) == [template], (arm, text)
    # The negated recipient of the request itself still negates it.
    for text in ("Share it with no one.", "Share the code with no one and hang up.",
                 "Please send your PIN to nobody, ever."):
        assert alerts(call(text), "B") == [], text


def test_not_a_request():
    for text in ("We sent a code, tell me when you get it.",
                 "Give me a second while I pull up the code.",
                 "What's your zip code?"):
        assert alerts(call(text), "B") == [], text


def test_one_warning_per_category_with_templates_and_basis():
    segs = call("Read me the code.", "Now tell me the PIN too.", "Then buy gift cards and send me the numbers.",
                "Download AnyDesk.", ref="s1")
    ds = decide(segs, "B", V)
    assert [(d.template_id, d.followup_template_id) for d in ds] == [
        ("ALERT-OTP-01", "FU-OTP-01"), ("ALERT-PAY-01", "FU-PAY-01"), ("ALERT-REMOTE-01", "FU-REMOTE-01")]
    assert all(d.session_ref == "s1" and d.policy_version == V and d.keyword_arm_would_fire for d in ds)
    # "send me the numbers" resolves to the gift cards in the same turn, not the earlier code.
    assert ds[0].basis == ["B-OTP-REQ-01"]
    assert [d.basis for d in decide(segs, "K", V)] == [["K-OTP-01"], ["K-PAY-01"], ["K-REMOTE-01"]]


def test_keyword_arm_would_fire_reports_k():
    (d,) = decide(call("I sent a code to your phone.", "Read it to me."), "B", V)
    assert d.keyword_arm_would_fire
    assert decide(call("Read it to me."), "B", V) == []  # no object anywhere: no alert, K silent too


def test_cumulative_and_prefix_stable():
    segs = call("Hi, it's your bank.", "Read me the code.", "Read me the code again.", "Download AnyDesk.")
    for arm in "KB":
        prev: list[RiskEvent] = []
        for n in range(1, len(segs) + 1):
            events = detect(segs[:n], arm, V)
            assert events[:len(prev)] == prev
            prev = events
    assert [e.rule_id for e in detect(segs, "B", V)] == ["B-OTP-REQ-01", "B-REMOTE-REQ-01"]


def test_events_carry_category_words_not_call_text():
    segs = call("Read me the code: four seven two nine.", ref="s2")
    for arm in "KB":
        for e in detect(segs, arm, V):
            dumped = e.model_dump_json().lower()
            assert "four" not in dumped and "read me" not in dumped
            assert e.session_ref == "s2" and e.source == "rule" and e.policy_version == V
    (b,) = detect(segs, "B", V)
    assert (b.event_type, b.category, b.span_seq, b.confidence_class) == ("code_request", "otp", [1], "high")


def test_arm_c_equals_b_with_abstaining_stub():
    segs = call("We will never ask for your code.", "Read me the code.")
    assert decide(segs, "C", V) == decide(segs, "B", V)


def test_arm_c_confirm_needs_lexicon_solo_has_its_own_id(monkeypatch):
    windows = []

    def fake_answers(window):
        windows.append([s.seq for s in window])
        return {**dict.fromkeys(intent.QUESTIONS, 0.0), "payment": 0.8}  # confident enough to confirm, not to act alone

    monkeypatch.setattr(intent, "answers", fake_answers)
    monkeypatch.setattr(intent, "judge", lambda ans, cat, seen: ("confirm" if seen else None)
                        if ans.get(cat, 0) >= 0.7 else None)
    segs = call("Hello there.", "Grandma, the lawyer said bail is fifteen hundred, okay?")
    assert decide(segs, "B", V) == []
    (d,) = decide(segs, "C", V)
    assert (d.template_id, d.basis) == ("ALERT-PAY-01", ["C-INTENT-PAY-01"])
    assert windows[:2] == [[1], [1, 2]]  # every caller turn, with its context window
    # The same judgment without the lexicon in the window does nothing.
    assert decide(call("Grandma, the lawyer said it's a lot, okay?"), "C", V) == []
    # A solo judgment maps to the model-only rule id.
    monkeypatch.setattr(intent, "judge", lambda ans, cat, seen: "solo" if cat == "payment" else None)
    (d,) = decide(call("Can you help me out, quick?"), "C", V)
    assert d.basis == ["C-INTENT-PAY-SOLO"]


def test_empty_session():
    for arm in "KBC":
        assert decide([], arm, V) == [] and detect([], arm, V) == []


def test_symbol_amount_is_a_payment_term_like_the_word():
    # F04: "$100" is the same payment object as "100 dollars", under both arms.
    for text in ("Please send $100.", "Please send 100 dollars.", "Please send $ 2,500 today."):
        for arm in "KB":
            assert alerts(call(text), arm) == ["ALERT-PAY-01"], (arm, text)
    assert alerts(call("Please don't send $100 to anyone."), "B") == []
    assert alerts(call("Item A100 is back in stock."), "K") == []  # a digit inside a word is no amount


def test_anyone_is_a_recipient_unless_negated():
    # F07: "to anyone" without a negation is a request, like "to someone".
    for text in ("Read the code to anyone on my team.", "Read the code to someone on my team."):
        assert [e.rule_id for e in detect(call(text), "B", V)] == ["B-OTP-REQ-01"], text
    assert alerts(call("Don't hang up, just read the code to anyone here."), "B") == ["ALERT-OTP-01"]
    for text in ("Share it with nobody.", "Don't give it to anyone.", "Do not read the code to anybody.",
                 "Share the code with no one.", "Never, ever share the code with anyone."):
        assert alerts(call(text), "B") == [], text


def test_request_object_is_bound_to_its_own_sentence():
    # F08: a lexicon term in another sentence is not the object of this request.
    assert detect(call("Tell me your name. A security code will arrive later."), "B", V) == []
    assert detect(call("Tell me your name."), "B", V) == []
    assert [e.rule_id for e in detect(call("Tell me the security code that arrived."), "B", V)] == ["B-OTP-REQ-01"]
    # An object already mentioned earlier in the turn still counts.
    assert [e.rule_id for e in detect(call("A security code will arrive. Read it to me."), "B", V)] \
        == ["B-OTP-REQ-01"]


def test_pronoun_resolves_to_the_latest_mention_across_categories():
    # F09: the most recent mention wins, whatever the category order in the policy.
    segs = call("I mentioned a code. Now you have AnyDesk ready.", "Open it now.")
    assert [e.rule_id for e in detect(segs, "B", V)] == ["B-REMOTE-CTX-01"]
    assert [e.rule_id for e in detect(call("Now you have AnyDesk ready.", "Open it now."), "B", V)] \
        == ["B-REMOTE-CTX-01"]
    # Within one turn too: the later mention is the referent.
    segs = call("You have AnyDesk. I just sent a code to your phone.", "Read it to me.")
    assert [e.rule_id for e in detect(segs, "B", V)] == ["B-OTP-CTX-01"]
