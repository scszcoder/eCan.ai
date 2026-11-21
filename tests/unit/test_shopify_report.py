"""Shopify end-of-day reports use the same store report as Amazon, with Shopify's names."""
import json
from pathlib import Path

import pytest

from agent.ec_skills.reports import report_store as rs
from agent.ec_skills.reports import store_report as sr

REPORT = {"store": "ushooa", "store_url": "https://admin.shopify.com/store/ushooa", "checked_at": "2026-10-28T18:00",
          "orders": [{"order_id": "#1001", "action_needed": "fulfil today", "items": [{"title": "Lamp", "qty": 1}]},
                     {"order_id": "#1000", "action_needed": ""}],
          "customer_messages": [{"order_id": "#1001", "buyer": "Kim", "request": "tracking?", "draft_reply": "Hi Kim"}],
          "red_flags": [{"severity": "high", "type": "Payouts on hold"}]}


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "reports_root", lambda: tmp_path)
    monkeypatch.setattr(rs, "_request_upload_url", lambda *a: {"error": "not deployed"})
    return tmp_path


def test_each_store_gets_its_own_report_from_its_own_step(saved):
    state = {"tool_result": {"Shopify_Triage_ushooa": {"final": json.dumps(REPORT)},
                             "Shopify_Triage_ryoais": {"final": json.dumps(dict(REPORT, store="ryoais", orders=[]))}}}
    out = sr.save_store_run_report(state, "shopify", "ushooa", node="Shopify_Triage_ushooa", date="2026-10-28")
    folder = Path(out["folder"])
    assert folder == saved / "shopify" / "ushooa" / "2026-10-28"
    md = (folder / "report.md").read_text(encoding="utf-8")
    assert md.splitlines()[0] == "# 2 orders, 1 processed, 2 todos, 1 redflags" == "# " + out["title"]
    assert "## Unfulfilled orders" in md and "## Customer messages" in md and "Account Health" not in md
    other = sr.save_store_run_report(state, "shopify", "ryoais", node="Shopify_Triage_ryoais", date="2026-10-28")
    assert other["title"].startswith("0 orders")


def test_a_failed_shopify_check_says_so(saved):
    out = sr.save_store_run_report({"tool_result": {"x": {"final": {"status": "failed", "error": "boom"}}}},
                                   "shopify", "ryoais", date="2026-10-28")
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert out["title"] == "CHECK DID NOT COMPLETE" and "Shopify admin" in md and "boom" in md


def test_a_report_about_another_store_is_not_filed_as_this_one(saved):
    state = {"tool_result": {"Shopify_Triage_ryoais": {"final": json.dumps(REPORT)}}}
    out = sr.save_store_run_report(state, "shopify", "ryoais", node="Shopify_Triage_ryoais", date="2026-10-28")
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert out["title"] == "CHECK DID NOT COMPLETE" and "'ushooa', not 'ryoais'" in md
    assert not (Path(out["folder"]) / "report.json").exists()

def test_labels_bought_earlier_in_the_run_are_in_the_report(saved):
    # The check runs after the label step and sees those orders already fulfilled.
    folder = saved / "shopify" / "ushooa" / "2026-11-20"
    folder.mkdir(parents=True)
    (folder / "labels.json").write_text(json.dumps({"labels": [
        {"order_id": "#1091", "status": "purchased", "service": "USPS Ground Advantage", "total": "$8.88"},
        {"order_id": "#1090", "status": "purchased", "total": "$6.63"},
        {"order_id": "#1089", "status": "skipped"}]}), encoding="utf-8")
    state = {"tool_result": {"t": {"final": json.dumps(dict(REPORT, orders=[], customer_messages=[]))}}}
    out = sr.save_store_run_report(state, "shopify", "ushooa", node="t", date="2026-11-20")
    md = (folder / "report.md").read_text(encoding="utf-8")
    assert out["title"] == "2 orders, 2 processed, 0 todos, 1 redflags" and md.startswith("# " + out["title"])
    assert "Bought 2 shipping labels on Shopify (#1091, #1090)" in md and "Read-only" not in md
    assert "## Shipping labels bought" in md and "$8.88" in md and "#1089" not in md
