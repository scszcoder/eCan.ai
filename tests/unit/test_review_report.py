"""A review-mining run becomes a report of complaints and ideas; an empty run says it failed."""
import json
from pathlib import Path

import pytest

from agent.ec_skills.reports import report_store as rs
from agent.ec_skills.reports import review_report as rr

MINED = {"niche": "magsafe case", "checked_at": "2026-11-06T10:00",
         "listings": [{"asin": "B000TEST01", "title": "Clear case", "price": "$15.99", "rating": 4.3,
                       "ratings_count": 5200, "top_complaints": ["yellows", "weak magnet"], "reviews_read": 8}],
         "themes": [{"theme": "turns yellow", "kind": "complaint", "products": 4, "mentions": 11,
                     "quotes": ["yellow after a month"]},
                    {"theme": "slim", "kind": "praise", "products": 3, "mentions": 6}],
         "improvement_ideas": [{"idea": "anti-yellow TPU", "fixes_theme": "turns yellow", "why": "top complaint",
                                "effort": "low"}],
         "market": {"price_low": "$9.99", "price_median": "$15.99", "price_high": "$39.99", "competition": "high"}}


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "reports_root", lambda: tmp_path)
    monkeypatch.setattr(rs, "_request_upload_url", lambda *a: {"error": "not deployed"})
    return tmp_path


def test_a_mining_run_lists_complaints_ideas_and_competitors(saved):
    state = {"tool_result": {"mine": {"final": json.dumps(MINED)}}}
    out = rr.save_review_mining_report(state, "magsafe case", node="mine", date="2026-11-06")
    assert Path(out["folder"]) == saved / "review_mining" / "magsafe case" / "2026-11-06"
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert md.splitlines()[0] == "# magsafe case: 1 competitors, 1 recurring complaints, 1 improvement ideas"
    assert '**turns yellow**' in md and '"yellow after a month"' in md and "anti-yellow TPU" in md
    assert "B000TEST01" in md and "What buyers like" in md
    assert "8 reviews read." in md and "password again" not in md
    assert out["parsed"] and out["report"]["niche"] == "magsafe case"


def test_a_run_that_read_nothing_says_so(saved):
    state = {"tool_result": {"mine": {"final": {"status": "failed", "error": "robot check"}}}}
    out = rr.save_review_mining_report(state, "magsafe case", node="mine", date="2026-11-06")
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert "MINING DID NOT COMPLETE" in md and "robot check" in md and not out["parsed"]
