"""Pipeline lifecycle (§19.4) against fake rules, gateway and consent."""
import asyncio
import json
import threading

import pytest

from app import consent, ingest, intent, pipeline, rules, sms
from app.events import hub
from app.models import Decision, RiskEvent, Segment


class FakeGateway:
    def __init__(self, block: threading.Event | None = None):
        self.sent: list[str] = []
        self.block = block

    def send(self, template_id, session_ref):
        if self.block:
            self.block.wait(5)
        self.sent.append(template_id)
        return f"SIM{len(self.sent)}"


def fake_detect(segments, arm, policy_version):
    return [RiskEvent(session_ref=s.session_ref, event_type="code_request", source="rule", rule_id="B-OTP-REQ-01", category="otp",
                      span_seq=[s.seq], confidence_class="high", policy_version=policy_version)
            for s in segments if s.speaker == "caller" and "code" in s.text]


def fake_evaluate(segments, arm, policy_version):
    events = fake_detect(segments, arm, policy_version)
    if not events:
        return events, [Decision(level="none", policy_version=policy_version)]
    return events, [Decision(session_ref=events[0].session_ref, level="action_warning", template_id="ALERT-OTP-01",
                             followup_template_id="FU-OTP-01", basis=["B-OTP-REQ-01"], policy_version=policy_version)]


@pytest.fixture
def gw(monkeypatch):
    gateway = FakeGateway()
    monkeypatch.setattr(sms, "get_gateway", lambda: gateway)
    monkeypatch.setattr(rules, "evaluate", fake_evaluate)
    monkeypatch.setattr(consent, "is_active", lambda: True)
    return gateway


def seg(ref, seq, text, speaker="caller"):
    return Segment(session_ref=ref, seq=seq, speaker=speaker, text=text, source="script")


def drain(q):
    return [q.get_nowait() for _ in range(q.qsize())]


def summary(events):
    """(type, key detail) per event, for compact assertions."""
    out = []
    for e in events:
        p = e.payload
        detail = {"session": p.get("state"), "segment": p.get("seq"), "risk_event": tuple(p.get("span_seq", ())),
                  "decision": p.get("template_id"), "sms": p.get("template_id")}[e.type]
        out.append((e.type, detail))
    return out


def run(coro_fn):
    async def wrapper():
        async with hub.subscribe() as q:
            result = await coro_fn()
            await asyncio.sleep(0)
            return result, drain(q)
    return asyncio.run(wrapper())


def test_alert_then_exactly_one_followup_on_double_finish(gw):
    async def scenario():
        ref = await pipeline.start("B", "v1.0", "simulated")
        await pipeline.process(seg(ref, 1, "Hi, this is your bank."))
        new = await pipeline.process(seg(ref, 2, "I sent a code to your phone."))
        again = await pipeline.process(seg(ref, 3, "Read me the code."))
        await asyncio.gather(pipeline.finish(ref), pipeline.finish(ref))
        await pipeline.finish(ref)
        late = await pipeline.process(seg(ref, 4, "Hello?"))
        return ref, new, again, late

    (ref, new, again, late), events = run(scenario)
    assert [d.template_id for d in new] == ["ALERT-OTP-01"] and new[0].session_ref == ref
    assert again == [] and late == []
    assert gw.sent == ["ALERT-OTP-01", "FU-OTP-01"]
    assert summary(events) == [
        ("session", "running"),
        ("segment", 1),
        ("segment", 2), ("risk_event", (2,)), ("decision", "ALERT-OTP-01"),
        ("segment", 3), ("risk_event", (3,)),
        ("sms", "ALERT-OTP-01"),
        ("sms", "FU-OTP-01"),
        ("session", "finished"),
    ]
    assert all(e.session_ref == ref and e.generation == 1 for e in events)
    assert next(e for e in events if e.type == "sms").payload["status"] == "queued"


def test_no_followup_without_alert_or_consent(gw, monkeypatch):
    async def silent():
        ref = await pipeline.start("B", "v1.0", "simulated")
        await pipeline.process(seg(ref, 1, "Your appointment is tomorrow."))
        await pipeline.finish(ref)

    _, events = run(silent)
    assert gw.sent == []
    assert [e.type for e in events] == ["session", "segment", "session"]

    monkeypatch.setattr(consent, "is_active", lambda: False)

    async def opted_out():
        ref = await pipeline.start("B", "v1.0", "simulated")
        await pipeline.process(seg(ref, 1, "Read me the code."))
        await pipeline.finish(ref)

    run(opted_out)
    assert gw.sent == ["ALERT-OTP-01"]  # no follow-up; the fake gateway doesn't check consent itself


def test_start_while_active_finishes_old_session(gw):
    async def scenario():
        old = await pipeline.start("B", "v1.0", "simulated")
        await pipeline.process(seg(old, 1, "Read me the code."))
        new = await pipeline.start("B", "v1.0", "simulated")
        dropped = await pipeline.process(seg(old, 2, "Read me the code."))
        return old, new, dropped

    (old, new, dropped), events = run(scenario)
    assert dropped == [] and pipeline.current().ref == new and pipeline.current().generation == 2
    assert gw.sent == ["ALERT-OTP-01", "FU-OTP-01"]
    sessions = [(e.session_ref, e.payload["state"], e.generation) for e in events if e.type == "session"]
    assert sessions == [(old, "running", 1), (old, "finished", 1), (new, "running", 2)]


def test_process_with_stale_or_unknown_ref_is_dropped(gw):
    async def scenario():
        ref = await pipeline.start("B", "v1.0", "simulated")
        out = await pipeline.process(seg("not-" + ref, 1, "Read me the code."))
        await pipeline.reset()
        out += await pipeline.process(seg(ref, 2, "Read me the code."))
        await pipeline.finish(ref)  # no-op after reset
        return out

    out, events = run(scenario)
    assert out == [] and gw.sent == []
    assert [(e.type, e.payload.get("state")) for e in events] == [("session", "running"), ("session", "reset")]


def test_reset_mid_replay(gw, tmp_path):
    lines = [(1, "caller", 20, "Hi, this is your bank."),
             (2, "caller", 40, "Can you read me the code?"),
             (3, "subscriber", 400, "Okay."),
             (4, "caller", 420, "Now read me the other code.")]
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps([{"seq": s, "speaker": sp, "t_start_ms": t - 10, "t_end_ms": t, "text": x}
                                for s, sp, t, x in lines]))

    async def scenario():
        replay = asyncio.create_task(ingest.replay_transcript(path, realtime=True))
        await asyncio.sleep(0.2)  # segments 1-2 processed, alert sent
        ref = pipeline.current().ref
        await pipeline.reset()
        await replay  # ingest may stop early or keep feeding stale segments; either way they're dropped
        await asyncio.sleep(0.05)
        return ref

    ref, events = run(scenario)
    assert gw.sent == ["ALERT-OTP-01"]  # no follow-up after reset
    assert pipeline.current() is None
    reset_at = next(i for i, e in enumerate(events) if e.payload.get("state") == "reset")
    assert reset_at == len(events) - 1  # nothing for the old session after reset
    assert [e.payload["seq"] for e in events if e.type == "segment"] == [1, 2]
    assert events[reset_at].session_ref == ref and events[reset_at].generation == 2


def test_send_scheduled_before_reset_never_calls_gateway(gw):
    async def scenario():
        ref = await pipeline.start("B", "v1.0", "simulated")
        new = await pipeline.process(seg(ref, 1, "Read me the code."))  # send queued, not yet run
        await pipeline.reset()
        await asyncio.sleep(0.1)
        return new

    new, events = run(scenario)
    assert len(new) == 1 and gw.sent == []
    assert "sms" not in [e.type for e in events]


def test_inflight_send_result_dropped_after_reset(gw):
    gw.block = threading.Event()

    async def scenario():
        ref = await pipeline.start("B", "v1.0", "simulated")
        await pipeline.process(seg(ref, 1, "Read me the code."))
        await asyncio.sleep(0.05)  # worker thread is now inside gateway.send
        await pipeline.reset()
        gw.block.set()
        await asyncio.sleep(0.1)
        await pipeline.finish(ref)

    _, events = run(scenario)
    assert gw.sent == ["ALERT-OTP-01"]  # already in Twilio's hands; no event, no follow-up
    assert "sms" not in [e.type for e in events]


def test_failed_send_emits_failed_status(gw, monkeypatch):
    class Refusing:
        def send(self, template_id, session_ref):
            raise RuntimeError("consent not active")

    monkeypatch.setattr(sms, "get_gateway", lambda: Refusing())

    async def scenario():
        ref = await pipeline.start("B", "v1.0", "simulated")
        await pipeline.process(seg(ref, 1, "Read me the code."))
        await pipeline.finish(ref)

    _, events = run(scenario)
    statuses = [(e.payload["template_id"], e.payload["status"]) for e in events if e.type == "sms"]
    assert statuses == [("ALERT-OTP-01", "failed"), ("FU-OTP-01", "failed")]
    assert events[-1].payload["state"] == "finished"


class SlowRules:
    """Arm C rules whose evaluation blocks (like model inference) until released."""
    def __init__(self):
        self.entered, self.go = threading.Event(), threading.Event()

    def evaluate(self, segments, arm, policy_version):
        self.entered.set()
        self.go.wait(2)
        return fake_evaluate(segments, arm, policy_version)


@pytest.fixture
def slow(gw, monkeypatch):
    r = SlowRules()
    monkeypatch.setattr(rules, "evaluate", r.evaluate)
    return r


def test_arm_c_inference_does_not_block_the_loop(slow):
    async def scenario():
        ref = await pipeline.start("C", "v1.0", "simulated")
        task = asyncio.create_task(pipeline.process(seg(ref, 1, "Read me the code.")))
        ticked = asyncio.Event()
        asyncio.get_running_loop().call_soon(ticked.set)
        await asyncio.wait_for(ticked.wait(), 1)
        blocked_done = task.done()
        slow.go.set()
        return blocked_done, await task

    (blocked_done, new), _ = run(scenario)
    assert not blocked_done and [d.template_id for d in new] == ["ALERT-OTP-01"]


def test_reset_during_arm_c_inference_drops_result(slow):
    async def scenario():
        ref = await pipeline.start("C", "v1.0", "simulated")
        task = asyncio.create_task(pipeline.process(seg(ref, 1, "Read me the code.")))
        await asyncio.to_thread(slow.entered.wait, 1)
        await pipeline.reset()
        slow.go.set()
        new = await task
        await asyncio.sleep(0.05)
        return new

    new, events = run(scenario)
    assert new == [] and sms.get_gateway().sent == []
    assert [e.type for e in events] == ["session", "segment", "session"]


def test_finish_during_arm_c_inference_sends_alert_before_followup(slow):
    async def scenario():
        ref = await pipeline.start("C", "v1.0", "simulated")
        task = asyncio.create_task(pipeline.process(seg(ref, 1, "Read me the code.")))
        await asyncio.to_thread(slow.entered.wait, 1)
        finishing = asyncio.create_task(pipeline.finish(ref))
        await asyncio.sleep(0.05)
        slow.go.set()
        await task
        await finishing

    run(scenario)
    assert sms.get_gateway().sent == ["ALERT-OTP-01", "FU-OTP-01"]


@pytest.mark.parametrize("end", ["finish", "reset"])
def test_intent_cache_cleared_when_session_ends(gw, monkeypatch, end):
    monkeypatch.setenv("INTENT_MODEL", "on")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(intent, "_post", lambda body: {"answers": {q: {"noul": 0.0} for q in intent.QUESTIONS}})

    def evaluate(segments, arm, policy_version):
        intent.answers(segments)
        return fake_evaluate(segments, arm, policy_version)

    monkeypatch.setattr(rules, "evaluate", evaluate)

    async def scenario():
        ref = await pipeline.start("C", "v1.0", "simulated")
        await pipeline.process(seg(ref, 1, "Read me the code."))
        cached = len(intent._cache)
        await (pipeline.finish(ref) if end == "finish" else pipeline.reset())
        return cached

    cached, _ = run(scenario)
    assert cached > 0 and len(intent._cache) == 0


@pytest.mark.parametrize("end", ["finish", "reset"])
def test_transcript_dropped_when_session_ends(gw, end):
    """No call text stays in memory once the call ends (PRD §12 transient content)."""
    async def scenario():
        ref = await pipeline.start("B", "v1.0", "simulated")
        s = pipeline.current()
        await pipeline.process(seg(ref, 1, "Read me the code."))
        held = len(s.segments)
        await (pipeline.finish(ref) if end == "finish" else pipeline.reset())
        return held, s

    (held, s), _ = run(scenario)
    assert held == 1 and s.segments == []
