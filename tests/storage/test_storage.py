"""SQLite storage (issue #18): tables and reply counts."""
from app import storage


def test_reply_total_runs_across_templates_per_keyword():
    assert storage.reply_total("WRONG") == 0
    storage.incr_reply("WRONG", "FU-OTP-01")
    storage.incr_reply("WRONG", "FU-OTP-01")
    storage.incr_reply("WRONG", "ALERT-OTP-01")
    storage.incr_reply("SHARED", "FU-OTP-01")
    assert (storage.reply_total("WRONG"), storage.reply_total("SHARED")) == (3, 1)
    assert storage.aggregates()["replies"] == [
        {"keyword": "SHARED", "template_id": "FU-OTP-01", "count": 1},
        {"keyword": "WRONG", "template_id": "ALERT-OTP-01", "count": 1},
        {"keyword": "WRONG", "template_id": "FU-OTP-01", "count": 2},
    ]
