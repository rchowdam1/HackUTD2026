from fastapi.testclient import TestClient

from app.main import create_app
from app.models import PAYLOAD_MODELS, Event, Scenario, SmsGateway
from app.sms import SimulatedGateway
from app.asr import load_transcript


def test_every_event_type_has_a_valid_fixture(fixtures_dir):
    seen = set()
    for path in sorted((fixtures_dir / "events").glob("*.json")):
        event = Event.model_validate_json(path.read_text())
        event.parsed_payload()
        seen.add(event.type)
    assert seen == set(PAYLOAD_MODELS)


def test_otp_fixture_scenario_and_transcript(fixtures_dir):
    scenario = Scenario.model_validate_json((fixtures_dir / "scenario_otp.json").read_text())
    lines = load_transcript(fixtures_dir / "scenario_otp" / "transcript.json")
    assert [l.text for l in lines] == [t.text for t in scenario.turns]
    assert [l.seq for l in lines] == list(range(1, len(lines) + 1))


def test_simulated_gateway_satisfies_protocol():
    gw = SimulatedGateway()
    assert isinstance(gw, SmsGateway)
    assert gw.send("ALERT-OTP-01", "ref")


def test_health_route_auto_discovered():
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
