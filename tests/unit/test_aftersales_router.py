"""售后前台 (chat side): after-sales turns go to the pool's 售后 agents and one
agent owns a customer's case until it closes."""
import time
from types import SimpleNamespace

import pytest

from agent.ec_agents import aftersales_router as asr

AGENTS = {
    "qa1": SimpleNamespace(tasks=[SimpleNamespace(name="飞鸽客服应答001")]),
    "qa2": SimpleNamespace(tasks=[SimpleNamespace(name="飞鸽客服应答002")]),
    "as1": SimpleNamespace(tasks=[SimpleNamespace(name="售后应答001")]),
    "as2": SimpleNamespace(tasks=[SimpleNamespace(name="售后应答002")]),
}
POOL = ["qa1", "qa2", "as1", "as2"]


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "_path", lambda: str(tmp_path / "cases.json"))
    asr._cases.clear()
    asr._loaded[0] = False
    yield
    asr._cases.clear()


def route(text, customer="买家A", pool=POOL):
    return asr.route("fd", customer, text, pool, lookup=AGENTS.get)


def test_presales_turns_stay_with_the_presales_agents():
    assert route("这件衣服面料舒服吗") == (["qa1", "qa2"], "presales")
    assert route("可以退货吗") == (["qa1", "qa2"], "presales")       # a policy question opens no case


def test_an_after_sales_turn_goes_to_the_after_sales_agents_and_opens_a_case():
    ids, why = route("收到的杯子破了")
    assert ids == ["as1", "as2"] and why == "aftersales:new"
    asr.claim("fd", "买家A", "as2", "收到的杯子破了")
    # every later message of that buyer -> the case owner, even a plain one
    assert route("好的") == (["as2"], "aftersales:case")
    assert route("这个还有别的颜色吗") == (["as2"], "aftersales:case")
    # another buyer is unaffected
    assert route("有货吗", customer="买家B") == (["qa1", "qa2"], "presales")


def test_the_case_survives_a_restart_and_closes_when_idle(monkeypatch):
    asr.claim("fd", "买家A", "as1", "发错颜色了")
    asr._cases.clear()
    asr._loaded[0] = False                                 # "restart": reload from disk
    assert route("什么时候补发") == (["as1"], "aftersales:case")
    monkeypatch.setenv("ECAN_AFTERSALES_CASE_IDLE_H", "1")
    asr._cases["fd|买家A"]["last"] = time.time() - 2 * 3600
    assert route("在吗") == (["qa1", "qa2"], "presales")      # closed after 1 h idle
    assert asr.cases() == {}


def test_dormant_without_after_sales_agents():
    assert route("收到的杯子破了", pool=["qa1", "qa2"]) == (["qa1", "qa2"], "")


def test_an_owner_that_left_the_pool_hands_the_case_to_another_after_sales_agent():
    asr.claim("fd", "买家A", "as9", "坏了")
    assert route("怎么处理") == (["as1", "as2"], "aftersales:new")


@pytest.mark.parametrize("text", ["衣服收到了，袖子开线了", "发错颜色了", "少了一件", "我要退货", "申请退款",
                                  "耳机用不了，没反应", "快递显示签收但我没收到", "和图片色差太大"])
def test_after_sales_phrases(text):
    assert asr.is_aftersales(text)


@pytest.mark.parametrize("text", ["可以退货吗", "支持七天无理由吗", "包运费险吗", "有货吗", "穿久了会不会掉色褪色",
                                  "尺码偏大还是偏小", "会不会起球", "有人吗？"])
def test_presales_phrases(text):
    assert not asr.is_aftersales(text)


# --- the 售后 agent's case-note tools ------------------------------------------------

def _call(fn, **inp):
    import asyncio
    import json
    return json.loads(asyncio.run(fn(None, {"input": inp}))[0].text)


def test_case_tools_note_read_and_close():
    from agent.mcp.server.aftersales import case_tools as ct
    assert _call(ct.aftersales_case_note, customer_id="买家A", kind="evidence", text="x")["ok"] is False
    asr.claim("fd", "买家A", "as1", "收到的杯子破了")
    assert _call(ct.aftersales_case_note, customer_id="买家A", kind="evidence",
                 text="照片：杯口有裂纹，外箱完好", order_id="261021-1")["ok"]
    assert _call(ct.aftersales_case_note, customer_id="买家A", kind="pending_approval",
                 text="补发一个同款，待商家确认")["ok"]
    assert _call(ct.aftersales_case_note, customer_id="买家A", kind="bogus", text="x")["ok"] is False
    got = _call(ct.aftersales_case_get, customer_id="买家A")
    assert got["found"] and got["case"]["order_id"] == "261021-1"
    assert [n["kind"] for n in got["case"]["notes"]] == ["evidence", "pending_approval"]
    assert got["case"]["owner_agent_id"] == "as1"
    assert _call(ct.aftersales_case_close, customer_id="买家A", resolution="已补发")["ok"]
    assert _call(ct.aftersales_case_get, customer_id="买家A")["found"] is False
    assert route("还有别的问题吗") == (["qa1", "qa2"], "presales")      # back to pre-sales


def test_case_tools_are_registered():
    from agent.mcp.server.aftersales.case_tools import add_aftersales_case_tool_schemas
    schemas = []
    add_aftersales_case_tool_schemas(schemas)
    assert [t.name for t in schemas] == ["aftersales_case_get", "aftersales_case_note", "aftersales_case_close"]
