"""Unit tests for the get_weather MCP tool (agent/mcp/server/weather)."""

import asyncio

import pytest

from agent.mcp.server.weather import weather_tools as wt


def _call(input_dict):
    """Run the async handler and return its meta dict."""
    res = asyncio.run(wt.get_weather(None, {"input": input_dict}))
    return getattr(res[0], "meta", {})


# --- pure severity classifier -------------------------------------------------

@pytest.mark.parametrize("text,severe,days", [
    ("多云", False, 0),
    ("晴", False, 0),
    ("小雨", False, 0),           # light rain does NOT delay shipping
    ("暴雨", True, 2),
    ("大雪", True, 2),
    ("台风", True, 3),
    ("Thunderstorm heavy rain", True, 2),
    ("Tornado", True, 3),
    ("Clear sky", False, 0),
    ("", False, 0),
])
def test_assess_condition(text, severe, days):
    s, _sev, d = wt.assess_condition(text)
    assert s is severe
    assert d == days


# --- mock vendor end-to-end ---------------------------------------------------

def test_mock_clear(monkeypatch):
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "mock")
    m = _call({"location": "杭州"})
    assert m["status"] == "success"
    assert m["vendor"] == "mock"
    assert m["severe"] is False
    assert m["suggested_delay_days"] == 0
    assert m["advisory"] == ""


def test_mock_severe_keyword_drives_branch(monkeypatch):
    # The mock vendor reports severe weather when the location name carries a
    # severe keyword — lets the severe path be exercised with no API key.
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "mock")
    m = _call({"location": "台风测试城"})
    assert m["severe"] is True
    assert m["suggested_delay_days"] == 3
    assert m["advisory"]


def test_multi_location_takes_max_delay(monkeypatch):
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "mock")
    m = _call({"locations": ["深圳", "暴雨城"]})
    assert m["checked"] == ["深圳", "暴雨城"]
    assert len(m["results"]) == 2
    assert m["severe"] is True
    assert m["suggested_delay_days"] == 2   # 暴雨 -> heavy -> 2


def test_missing_location_is_error(monkeypatch):
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "mock")
    m = _call({})
    assert m["status"] == "error"


# --- vendor selection + no-key fallback --------------------------------------

def test_select_vendor_env_override(monkeypatch):
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "cn")
    assert wt._select_vendor() == "cn"
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "us")
    assert wt._select_vendor() == "us"


def test_select_vendor_by_region(monkeypatch):
    monkeypatch.delenv("ECAN_WEATHER_VENDOR", raising=False)

    class _Cfg:
        def __init__(self, cn): self._cn = cn
        def is_cn(self): return self._cn

    import utils.app_config_loader as acl
    monkeypatch.setattr(acl, "get_app_config", lambda *a, **k: _Cfg(True))
    assert wt._select_vendor() == "cn"
    monkeypatch.setattr(acl, "get_app_config", lambda *a, **k: _Cfg(False))
    assert wt._select_vendor() == "us"


def test_real_vendor_without_key_falls_back_to_mock(monkeypatch):
    # Pick the CN vendor but provide no key -> must not raise, must use mock.
    monkeypatch.setenv("ECAN_WEATHER_VENDOR", "cn")
    monkeypatch.delenv("ECAN_WEATHER_CN_KEY", raising=False)
    m = _call({"location": "暴雨城"})
    assert m["status"] == "success"
    # fell back to mock; the result row's source says so
    assert m["results"][0]["source"] == "mock"
    assert m["severe"] is True


# --- schema shape -------------------------------------------------------------

def test_schema_registration():
    schemas = []
    wt.add_get_weather_tool_schema(schemas)
    assert len(schemas) == 1
    tool = schemas[0]
    assert tool.name == "get_weather"
    assert tool.inputSchema["required"] == ["input"]
    props = tool.inputSchema["properties"]["input"]["properties"]
    assert "locations" in props and "location" in props
