import importlib.util
import sys
from pathlib import Path

import pytest

from app import pipeline, sms, storage
from app.api import auth
from app.events import hub

FIXTURES = Path(__file__).parent / "fixtures"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str):
    """scripts/<name>.py as module `name`, loaded once (demo_up imports preflight_checks by that name)."""
    if name not in sys.modules:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        sys.modules[name] = importlib.util.module_from_spec(spec)  # registered first: dataclasses look it up
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    """Module-level state every test starts without: session, SMS mode and records, event history, login throttle."""
    monkeypatch.setattr(pipeline, "_session", None)
    monkeypatch.setattr(pipeline, "_generation", 0)
    monkeypatch.setattr(sms, "_mode", "simulated")
    monkeypatch.setattr(sms, "_last_alerts", {})
    monkeypatch.setattr(sms, "_sent", {})
    monkeypatch.setattr(sms, "simulated", sms.SimulatedGateway())
    monkeypatch.setattr(sms, "_twilio", None)
    monkeypatch.setattr(hub, "history", [])
    monkeypatch.setattr(auth, "_failures", {})


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch) -> Path:
    """Every test gets its own SQLite file; nothing touches data/safesignal.db."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "safesignal.db")
    return storage.DB_PATH


@pytest.fixture
def published(monkeypatch) -> list:
    """Every event published to the hub, as (type, parsed payload, session_ref)."""
    seen = []
    monkeypatch.setattr(hub, "publish", lambda e: seen.append((e.type, e.parsed_payload(), e.session_ref)))
    return seen
