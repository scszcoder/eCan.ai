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
