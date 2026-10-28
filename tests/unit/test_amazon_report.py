"""The Amazon after-sales run report is built from the browser step's final JSON."""
import json
from pathlib import Path

import pytest

from agent.ec_skills.reports import amazon_report as ar
from agent.ec_skills.reports import report_store as rs

REPORT = {
    "store": "sc_amazon_0", "marketplace": "US", "checked_at": "2026-10-26T18:00:00", "login_required": False,
    "fbm_orders": [{"order_id": "113-1", "ship_by": "2026-10-27", "late": True,
                    "items": [{"sku": "SKU1", "qty": 2}], "action_needed": "ship", "draft_action": "buy label"}],
    "buyer_messages": [{"order_id": "113-2", "buyer": "Ann", "respond_by": "10/27 09:00", "urgency": "high",
                        "request": "where is | my order", "draft_reply": "Hi Ann,\nit ships today."}],
    "account_health": {"status": "Healthy", "ahr_score": 250, "metrics": [{"name": "ODR", "value": "0.4%"}]},
    "red_flags": [{"severity": "low", "type": "feedback"}, {"severity": "high", "type": "A-to-z claim"}],
}


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "reports_root", lambda: tmp_path)
    monkeypatch.setattr(rs, "_request_upload_url", lambda *a: {"error": "not deployed"})
    return tmp_path


def _state(final):
    return {"tool_result": {"Amazon_Triage": {"final": final}}}


def test_the_final_json_becomes_a_report_and_markdown(saved):
    out = ar.save_amazon_run_report(_state("Done.\n" + json.dumps(REPORT)), date="2026-10-26")
    folder = Path(out["folder"])
    assert folder == saved / "amazon" / "sc_amazon_0" / "2026-10-26" and out["parsed"]
    md = (folder / "report.md").read_text(encoding="utf-8")
    assert md.index("A-to-z claim") < md.index("feedback")          # high before low
    assert "1 late" in md and "where is / my order" in md and "> it ships today." in md
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["store"] == "sc_amazon_0"
    assert out["upload"]["status"] == "pending"


def test_an_unparsable_answer_is_kept_raw(saved):
    out = ar.save_amazon_run_report(_state("I could not finish."), store_name="sc_amazon_0", date="2026-10-26")
    assert not out["parsed"]
    assert json.loads((Path(out["folder"]) / "raw_result.json").read_text(encoding="utf-8")) == {"final": "I could not finish."}
    assert "DID NOT COMPLETE" in (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")


def test_a_failed_browser_step_is_not_an_all_clear(saved):
    """2026-10-26: {"status": "failed"} rendered as "0 red flags, 0 orders"."""
    failed = {"status": "failed", "error": "browser-use run ended with consecutive failures"}
    out = ar.save_amazon_run_report(_state(failed), store_name="sc_amazon_0", date="2026-10-26")
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert not out["parsed"] and "DID NOT COMPLETE" in md and "consecutive failures" in md
    assert "Red flags: 0" not in md


def test_a_sign_in_page_is_flagged(saved):
    out = ar.save_amazon_run_report(_state(json.dumps({"store": "s", "login_required": True})), date="2026-10-26")
    assert out["login_required"]
    assert "needs a sign-in" in (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")


def test_red_flag_details_are_rendered(saved):
    rep = dict(REPORT, red_flag_details=[{"title": "Listing policy violation", "source": "account_health",
                                          "asins": ["B0ABC"], "reason": "Restricted product", "deadline": "2026-11-01",
                                          "appeal_available": True, "excerpt": "Your listing was removed."}])
    out = ar.save_amazon_run_report(_state(json.dumps(rep)), date="2026-10-26")
    md = (Path(out["folder"]) / "report.md").read_text(encoding="utf-8")
    assert "## Red flag details" in md and "B0ABC" in md and "appeal available: True" in md
    assert "> Your listing was removed." in md
