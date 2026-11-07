import re
from pathlib import Path

import pytest

from app.policy import templates

ROOT = Path(__file__).resolve().parents[2]

IDS = [
    "ENROLL", "R-YES", "R-HELP",
    "ALERT-OTP-01", "ALERT-PAY-01", "ALERT-REMOTE-01",
    "FU-OTP-01", "FU-PAY-01", "FU-REMOTE-01",
    "R-SHARED-OTP", "R-SHARED-PAY", "R-SHARED-REMOTE",
    "R-WRONG", "R-STOP",
]

# ASCII characters in the GSM 03.38 basic set (no extension table: [ ] { } \ ^ ~ | ` excluded).
GSM7_ASCII = set(
    "@$\n\r_ !\"#%&'()*+,-./0123456789:;<=>?"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)
LINK = re.compile(r"https?://|www\.|[a-z0-9-]+\.[a-z]{2,}", re.I)


def prd_table() -> dict[str, str]:
    prd = (ROOT / "PRD.md").read_text(encoding="utf-8")
    section = prd.split("### 19.5")[1].split("### 19.6")[0]
    return dict(re.findall(r"^\| ([A-Z][A-Z0-9-]+) \| (.+) \|$", section, re.M))


def test_yaml_matches_prd_exactly():
    assert prd_table() == templates.TEMPLATES
    assert list(templates.TEMPLATES) == IDS


def lint(tid: str, text: str) -> list[str]:
    problems = []
    if not text.isascii() or not set(text) <= GSM7_ASCII:
        problems.append("non GSM-7/ASCII")
    if len(text) > 160:
        problems.append(f"{len(text)} chars")
    if re.search(r"\d", text):
        problems.append("digit")
    if '"' in text:
        problems.append("double quote")
    if LINK.search(text):
        problems.append("link")
    if tid.startswith("ALERT-") and len(text.split()) > 20:
        problems.append("ALERT over 20 words")
    return problems


@pytest.mark.parametrize("tid", IDS)
def test_lint(tid):
    assert lint(tid, templates.get(tid)) == []


@pytest.mark.parametrize("bad", [
    "call 555", "see www.x", "go to example.com", "http://x", 'say "hi"',
    "caf\u00e9", "a [b]", "x" * 161,
])
def test_lint_catches(bad):
    assert lint("R-X", bad)


def test_lint_catches_long_alert():
    assert lint("ALERT-X", " ".join(["word"] * 21))


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        templates.get("NOPE")


@pytest.mark.parametrize("cat", ["OTP", "PAY", "REMOTE"])
def test_alert_mappings(cat):
    alert = f"ALERT-{cat}-01"
    assert templates.followup_for(alert) == f"FU-{cat}-01"
    assert templates.shared_for(alert) == f"R-SHARED-{cat}"
    templates.get(templates.followup_for(alert))
    templates.get(templates.shared_for(alert))


def test_mapping_unknown_alert_raises():
    with pytest.raises(KeyError):
        templates.followup_for("FU-OTP-01")
    with pytest.raises(KeyError):
        templates.shared_for("NOPE")
