"""gads_review: downloaded Google Ads files + the browser step's answer -> one report."""
import time

import pytest

from agent.ec_skills.ecom import gads_review

CAMPAIGNS = """Campaign report
"October 10, 2026 - November 8, 2026"
Campaign,Campaign type,Campaign status,Budget,Bid strategy type,Impr.,Clicks,Cost,Conversions,Conv. value
Search A,Search,Enabled,5.00,Maximize clicks,1200,200,120.00,3.00,250.00
PMax B,Performance Max,Enabled,5.00,Maximize conversions,900,30,25.00,0.00,0.00
Total: Account,--,--,--,--,2100,230,145.00,3.00,250.00
"""
TERMS = """Search terms report
"October 10, 2026 - November 8, 2026"
Search term,Match type,Campaign,Ad group,Impr.,Clicks,Cost,Conversions,Conv. value
led signs for room,Phrase match,Search A,Ad group 1,400,90,60.00,0.00,0.00
custom neon sign,Exact match,Search A,Ad group 1,300,50,30.00,3.00,250.00
"""
ANSWER = {
    "account": "Test account", "date_range": "Oct 10 - Nov 8, 2026", "downloads": ["campaigns", "search_terms"],
    "not_downloaded": ["products: no Shopping data"],
    "conversion_actions": [
        {"name": "Shop App Purchase", "category": "Purchase", "status": "Needs attention", "optimization": "Primary"},
        {"name": "Old page-load purchase", "category": "Purchase", "status": "Removed", "optimization": "Primary"},
        {"name": "Shop App Add To Cart", "category": "Add to cart", "status": "Active", "optimization": "Primary"},
    ],
}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_ECOM_HOME", str(tmp_path / "ecom"))
    return tmp_path


def test_review_adds_up_files_and_flags_tracking(home):
    dl = home / "dl"
    dl.mkdir()
    since = time.time()
    (dl / "Campaign report.csv").write_text(CAMPAIGNS, encoding="utf-8")
    (dl / "Search terms report.csv").write_text(TERMS, encoding="utf-8")
    r = gads_review.review(ANSWER, "s1", str(dl), since)
    assert r["completed"] and r["totals"]["cost"] == 145.0 and r["totals"]["clicks"] == 230
    assert [c["campaign"] for c in r["campaigns"]] == ["Search A", "PMax B"]
    rules_hit = {f["rule_id"] for f in r["tracking"]["findings"]}
    assert {"trk.needs_attention", "trk.primary_non_purchase"} <= rules_hit and "trk.double_primary" not in rules_hit
    md = gads_review.render_markdown(r)
    assert "Shop App Add To Cart" in md and "not sales" in md and "1 search terms cost $60.00" in md
    assert "spent" in gads_review.chat_summary(r, "x")


def test_nothing_downloaded_is_not_an_all_clear(home):
    r = gads_review.review({"downloads": [], "notes": ["sign-in page"]}, "s1", str(home / "none"), time.time())
    assert not r["completed"]
    assert "DID NOT COMPLETE" in gads_review.render_markdown(r)
    assert "DID NOT COMPLETE" in gads_review.chat_summary(r, "x")


def test_a_sign_in_is_named_in_the_report_and_the_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_ECOM_HOME", str(tmp_path / "ecom"))
    from agent.ec_skills.ecom import gads_review as G
    r = G.review({"signin_required": True, "notes": ["sign-in page"]}, "s1", str(tmp_path), 0)
    assert not r["completed"] and r["signin_required"]
    assert "sign in again" in G.render_markdown(r) and "DID NOT COMPLETE" in G.render_markdown(r)
    assert "sign in to Google Ads" in G.chat_summary(r, "f")
