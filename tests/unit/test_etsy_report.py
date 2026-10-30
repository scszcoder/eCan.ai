"""Etsy end-of-day reports use the same store report, with Etsy's names."""
import json
from pathlib import Path

import pytest

from agent.ec_skills.reports import report_store as rs
from agent.ec_skills.reports import store_report as sr

REPORT = {"store": "shop", "store_url": "https://www.etsy.com/your/shops/me/dashboard", "checked_at": "2026-10-29T18:00",
          "orders": [{"order_id": "3001", "action_needed": "ship today", "items": [{"title": "Lamp", "qty": 1}]}],
          "buyer_messages": [{"order_id": "3001", "buyer": "Kim", "request": "tracking?", "draft_reply": "Hi Kim"}],
          "red_flags": [{"severity": "medium", "type": "Listing removed"}],
          "red_flag_details": [{"title": "Listing removed", "listings": ["Neon sign"], "platform_action": "removed"}]}


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "reports_root", lambda: tmp_path)
    monkeypatch.setattr(rs, "_request_upload_url", lambda *a: {"error": "not deployed"})
    return tmp_path


def test_an_etsy_shop_gets_its_report_with_etsy_names(saved):
    state = {"tool_result": {"etsy_triage_shop": {"final": json.dumps(REPORT)}}}
    out = sr.save_store_run_report(state, "etsy", "shop", node="etsy_triage_shop", date="2026-10-29")
    assert Path(out["folder"]) == saved / "etsy" / "shop" / "2026-10-29"
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert md.splitlines()[0] == "# 1 orders, 0 processed, 2 todos, 1 redflags"
    assert "## Orders to ship" in md and "## Buyer messages" in md and "Etsy's action: removed" in md
    assert "Listings: Neon sign" in md


def test_a_failed_etsy_check_says_so(saved):
    out = sr.save_store_run_report({"tool_result": {"x": {"final": {"status": "failed", "error": "boom"}}}},
                                   "etsy", "shop", date="2026-10-29")
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert out["title"] == "CHECK DID NOT COMPLETE" and "Etsy Shop Manager" in md
