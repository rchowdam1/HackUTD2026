from pathlib import Path

import pytest

from app import pipeline

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def _fresh_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline, "_session", None)
    monkeypatch.setattr(pipeline, "_generation", 0)
