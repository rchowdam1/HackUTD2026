import re
from pathlib import Path

import pytest

from app import policy
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


def test_every_alert_has_an_existing_followup_and_shared_reply():
    alerts = [tid for tid in IDS if tid.startswith("ALERT-")]
    assert [tid for tid in IDS if templates.is_alert(tid)] == alerts
    for alert in alerts:
        templates.get(templates.followup_for(alert))
        templates.get(templates.shared_for(alert))


def test_every_rules_category_alerts_with_an_alert_template():
    for cat in policy.load("rules")["categories"].values():
        assert templates.is_alert(cat["alert"])
