import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for `eval`

from app.models import Decision, Results
from eval import run as ev


def fake_decide(segments, arm, policy_version):
    """Fires on 'code' anywhere for K; only on caller lines without "don't" for B."""
    hit = any("code" in s.text and (arm == "K" or (s.speaker == "caller" and "don't" not in s.text))
              for s in segments)
    return [Decision(level="action_warning" if hit else "none", policy_version=policy_version)]


def scenario(sid, batch, label, hard, *lines):
    return {"id": sid, "set": batch, "label": label, "hard_benign": hard,
            "category": "otp" if label == "scam" else "none",
            "turns": [{"speaker": sp, "text": t, "audio": None} for sp, t in lines]}


@pytest.fixture
def scen_dir(tmp_path):
    rows = [
        scenario("s1", "dev", "scam", False, ("caller", "Read me the code.")),
        scenario("s2", "dev", "scam", False, ("caller", "Send money now.")),
        scenario("b1", "dev", "benign", True, ("caller", "We sent a code, don't share it.")),
        scenario("b2", "dev", "benign", True, ("subscriber", "I got a code.")),
        scenario("b3", "dev", "benign", False, ("caller", "Dinner at seven?")),
    ]
    (tmp_path / "dev").mkdir()
    for r in rows:
        (tmp_path / "dev" / f"{r['id']}.json").write_text(json.dumps(r))
    return tmp_path


def test_counts_and_discordant(scen_dir, tmp_path):
    res = ev.run(["K", "B"], "dev", "v1.0", fake_decide, scen_dir, tmp_path / "out")
    assert res.arms["K"].model_dump() == dict(TP=1, FN=1, FP=2, TN=1, hard_benign_fp=2, hard_benign_n=2)
    assert res.arms["B"].model_dump() == dict(TP=1, FN=1, FP=0, TN=3, hard_benign_fp=0, hard_benign_n=2)
    assert (res.discordant.K_only, res.discordant.B_only) == (0, 2)
    md = (tmp_path / "out" / "latest.md").read_text()
    assert "Scripted transcripts, not ASR" in md and "No win called" in md
    assert "2 of 2 (upper bound" in md


def test_results_json_matches_schema(scen_dir, tmp_path):
    ev.run(["K", "B"], "dev", "v1.0", fake_decide, scen_dir, tmp_path / "out")
    data = json.loads((tmp_path / "out" / "latest.json").read_text())
    Results.model_validate(data)
    assert set(data) == {"batch", "source", "arms", "discordant"} and data["source"] == "script"
    assert set(data["arms"]["K"]) == {"TP", "FP", "FN", "TN", "hard_benign_fp", "hard_benign_n"}


def test_wilson_known_values():
    lo, hi = ev.wilson(8, 10)
    assert round(lo, 4) == 0.4902 and round(hi, 4) == 0.9433
    assert ev.wilson(0, 20)[0] == 0.0 and round(ev.wilson(0, 20)[1], 4) == 0.1611
    assert ev.pct_down(0.49019) == "49.0%" and ev.pct_up(0.94331) == "94.4%"


def test_verdict_needs_five_one_directional():
    assert ev.verdict(0, 5).startswith("B wins")
    assert ev.verdict(1, 6).startswith("No win")
    assert ev.verdict(0, 4).startswith("No win")


def test_h1_hash_refusal(tmp_path):
    (tmp_path / "H1").mkdir()
    (tmp_path / "H1" / "h.json").write_text(json.dumps(
        scenario("h", "H1", "scam", False, ("caller", "Read me the code."))))
    with pytest.raises(SystemExit):
        ev.load_batch("H1", tmp_path)  # no seal
    (tmp_path / "H1.sha256").write_text("0" * 64)
    with pytest.raises(SystemExit):
        ev.load_batch("H1", tmp_path)  # wrong seal
    (tmp_path / "H1.sha256").write_text(ev.h1_digest(tmp_path) + "\n")
    assert [s.id for s in ev.load_batch("H1", tmp_path)] == ["h"]
