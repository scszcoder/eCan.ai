"""The ec_* MCP tools end to end: ingest a Google Ads download, run gads_v1, approve in chat,
build the upload file. Data goes to a temporary ECAN_ECOM_HOME."""
import asyncio
import json

import pytest

from agent.mcp.server.ecom import ec_tools

ST = """Search terms report
"November 1, 2026 - November 9, 2026"
Search term,Match type,Campaign,Ad group,Day,Impr.,Clicks,Cost,Conversions,Conv. value
blue widget large,Phrase match,C1,All,2026-11-06,900,40,102.00,0.00,0.00
"""


def call(name, **inp):
    out = asyncio.run(ec_tools.EC_TOOL_HANDLERS[name](None, {"input": inp}))
    return json.loads(out[0].text)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_ECOM_HOME", str(tmp_path / "ecom"))
    monkeypatch.setattr("agent.ec_skills.reports.report_store.reports_root", lambda: tmp_path / "reports")
    return tmp_path


def test_schemas_register():
    schemas = []
    ec_tools.add_ec_tool_schemas(schemas)
    assert {s.name for s in schemas} == set(ec_tools.EC_TOOL_HANDLERS)


def test_ingest_rules_approve_and_upload_file(home):
    f = home / "search_terms.csv"
    f.write_text(ST, encoding="utf-8")
    ing = call("ec_report_ingest", file_path=str(f), store_id="s1")
    assert (ing["status"], ing["table"], ing["rows"]) == ("ingested", "gads_search_term_rows", 1)
    assert call("ec_table_query", sql="SELECT SUM(cost) FROM gads_search_term_rows")["rows"] == [[102.0]]
    assert call("ec_rules_eval", ruleset_id="gads_v1", store_id="s1", today="2026-11-09")["status"] == "needs_input"
    run = call("ec_rules_eval", ruleset_id="gads_v1", store_id="s1", today="2026-11-09", breakeven_roas=2.5, aov=50)
    (act,) = [a for a in run["actions"] if a["type"] == "negate_keyword"]
    assert act["status"] == "proposed"
    assert "error" in call("ec_actions", store_id="s1", op="decide", decision="approved", action_ids=[act["action_id"]])
    dec = call("ec_actions", store_id="s1", op="decide", decision="approved", action_ids=[act["action_id"]],
               owner_words="yes, negate that one")
    assert dec["changed"] == [act["action_id"]]
    rerun = call("ec_rules_eval", ruleset_id="gads_v1", store_id="s1", today="2026-11-09", breakeven_roas=2.5, aov=50)
    assert next(a for a in rerun["actions"] if a["action_id"] == act["action_id"])["status"] == "approved"
    out = call("ec_bulk_file_build", platform="google_ads", store_id="s1")
    text = open(out["path"], encoding="utf-8").read()
    assert out["rows"] == 1 and "blue widget large" in text and "Campaign negative exact" in text


def test_core_is_not_writable_and_query_is_read_only():
    assert "PermissionError" in call("ec_kb", op="put", collection="core", key="x", value={})["error"]
    assert "error" in call("ec_table_query", sql="DELETE FROM kb")


def test_unit_economics_needs_the_owners_cost():
    out = call("ec_unit_economics", items=[{"id": "a", "price": 40, "cogs": 12, "shipping": 6}, {"id": "b", "price": 9}])
    assert out["items"][0]["breakeven_roas"] > 1 and "cogs" in out["items"][1]["error"]
