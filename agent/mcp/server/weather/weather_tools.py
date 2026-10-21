"""Weather MCP tool: ``get_weather``.

A thin, general tool the customer-service chatbot calls to set realistic
delivery expectations. When a buyer asks about shipping time, the agent
checks the weather at the ship-from location (from the product / warehouse
page) and, if the buyer volunteered a destination, at the destination too.
If severe weather (storm / typhoon / heavy snow / heavy rain, 暴雨 / 台风 /
暴雪 …) is hitting either end, the tool returns ``severe=true`` plus a
``suggested_delay_days`` the agent can relay ("delivery may take a few extra
days because of the storm").

Vendor selection
----------------
* ``ECAN_WEATHER_VENDOR`` env var, if set, wins (``mock`` / ``cn`` / ``us``).
* otherwise the CN app uses the CN vendor (和风天气 / QWeather) and the intl
  app uses the US vendor (OpenWeatherMap), decided by
  ``AppConfigLoader.is_cn()``.

A real vendor needs an API key (``ECAN_WEATHER_CN_KEY`` / ``ECAN_WEATHER_US_KEY``).
If the key is missing or a call fails, the tool falls back to the built-in
``mock`` vendor and logs a warning — a weather check must never break a
customer reply. The ``mock`` vendor is deterministic: a location whose name
contains a severe-weather keyword reports that condition, everything else is
reported clear. This lets the shipping flow be exercised end-to-end with no
key, and drives both the severe and clear branches in tests/demos.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from mcp.types import TextContent

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Severity classification (pure, testable)
# ---------------------------------------------------------------------------

# Keyword -> (severity label, suggested extra shipping days). Matched against
# the vendor's condition text (Chinese for the CN vendor, English for the US
# vendor; the mock vendor accepts either). Only conditions that would
# realistically delay a parcel count as "severe" — light rain / cloud do not.
# Ordered most-disruptive first so the first hit wins.
_SEVERE_RULES: Tuple[Tuple[Tuple[str, ...], str, int], ...] = (
    # extreme: ~3 extra days
    (("台风", "飓风", "龙卷", "特大暴雨", "暴雪", "寒潮", "沙尘暴",
      "typhoon", "hurricane", "tornado", "blizzard", "cyclone"), "extreme", 3),
    # heavy: ~2 extra days
    (("暴雨", "大暴雨", "大雪", "冰雹", "雷暴", "大雾", "沙尘",
      "thunderstorm", "heavy rain", "heavy snow", "snowstorm", "squall",
      "sandstorm", "freezing rain", "hail"), "heavy", 2),
)


def assess_condition(condition: str) -> Tuple[bool, str, int]:
    """Classify a condition string. Returns ``(severe, severity, delay_days)``.

    ``severity`` is ``""`` and ``delay_days`` ``0`` when not severe.
    """
    text = (condition or "").strip().lower()
    if not text:
        return (False, "", 0)
    for keywords, severity, days in _SEVERE_RULES:
        for kw in keywords:
            if kw.lower() in text:
                return (True, severity, days)
    return (False, "", 0)


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

class _NoApiKey(Exception):
    """Raised by a real vendor when its API key is not configured."""


def _severe_keyword_in(text: str) -> str:
    """First severe keyword present in ``text`` (case-insensitive), else ""."""
    low = (text or "").lower()
    for keywords, _severity, _days in _SEVERE_RULES:
        for kw in keywords:
            if kw.lower() in low:
                return kw
    return ""


def _mock_fetch(location: str, days: int) -> Dict[str, Any]:
    """Deterministic stub. If the name carries a severe keyword, report THAT
    condition (so every severity tier is exercised); otherwise report clear."""
    kw = _severe_keyword_in(location)
    condition = kw or "多云"
    return {"location": location, "condition": condition, "source": "mock"}


def _cn_fetch(location: str, days: int) -> Dict[str, Any]:
    """和风天气 (QWeather): city lookup -> now conditions.

    Needs ``ECAN_WEATHER_CN_KEY``. API host is per-account on QWeather's
    current plans, so it is configurable via ``ECAN_WEATHER_CN_HOST`` /
    ``ECAN_WEATHER_CN_GEO_HOST`` (legacy hosts are the defaults).
    """
    key = (os.environ.get("ECAN_WEATHER_CN_KEY") or "").strip()
    if not key:
        raise _NoApiKey("ECAN_WEATHER_CN_KEY not set")
    import requests

    geo_host = (os.environ.get("ECAN_WEATHER_CN_GEO_HOST")
                or "https://geoapi.qweather.com").rstrip("/")
    api_host = (os.environ.get("ECAN_WEATHER_CN_HOST")
                or "https://devapi.qweather.com").rstrip("/")

    geo = requests.get(f"{geo_host}/v2/city/lookup",
                       params={"location": location, "key": key}, timeout=6).json()
    locs = geo.get("location") or []
    if not locs:
        return {"location": location, "condition": "", "found": False, "source": "cn"}
    loc_id = locs[0].get("id")
    city = locs[0].get("name") or location
    now = requests.get(f"{api_host}/v7/weather/now",
                       params={"location": loc_id, "key": key}, timeout=6).json()
    cur = now.get("now") or {}
    return {
        "location": city,
        "condition": cur.get("text") or "",
        "temp_c": cur.get("temp"),
        "found": True,
        "source": "cn",
    }


def _us_fetch(location: str, days: int) -> Dict[str, Any]:
    """OpenWeatherMap current weather. Needs ``ECAN_WEATHER_US_KEY``."""
    key = (os.environ.get("ECAN_WEATHER_US_KEY") or "").strip()
    if not key:
        raise _NoApiKey("ECAN_WEATHER_US_KEY not set")
    import requests

    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": location, "appid": key, "units": "metric", "lang": "en"},
        timeout=6,
    ).json()
    if str(r.get("cod")) != "200":
        return {"location": location, "condition": "", "found": False, "source": "us"}
    w = (r.get("weather") or [{}])[0]
    # "main" (e.g. Thunderstorm/Snow) + "description" (e.g. "heavy snow")
    condition = " ".join(x for x in (w.get("main"), w.get("description")) if x)
    return {
        "location": r.get("name") or location,
        "condition": condition,
        "temp_c": (r.get("main") or {}).get("temp"),
        "found": True,
        "source": "us",
    }


_VENDORS = {"mock": _mock_fetch, "cn": _cn_fetch, "us": _us_fetch}


def _select_vendor() -> str:
    override = (os.environ.get("ECAN_WEATHER_VENDOR") or "").strip().lower()
    if override in _VENDORS:
        return override
    try:
        from utils.app_config_loader import get_app_config
        return "cn" if get_app_config().is_cn() else "us"
    except Exception:
        return "us"


def _fetch_one(vendor: str, location: str, days: int) -> Dict[str, Any]:
    """Fetch for one location; fall back to mock on missing key / error."""
    fn = _VENDORS.get(vendor, _mock_fetch)
    try:
        row = fn(location, days)
    except _NoApiKey as e:
        logger.warning(f"[weather] vendor={vendor!r} not configured ({e}); using mock")
        row = _mock_fetch(location, days)
        vendor = "mock"
    except Exception as e:
        logger.warning(f"[weather] vendor={vendor!r} lookup for {location!r} failed: {e}; using mock")
        row = _mock_fetch(location, days)
        vendor = "mock"
    severe, severity, delay = assess_condition(row.get("condition", ""))
    row["severe"] = severe
    row["severity"] = severity
    row["delay_days"] = delay
    row["source"] = row.get("source") or vendor
    return row


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------

def _normalize_locations(input_data: Dict[str, Any]) -> List[str]:
    raw = input_data.get("locations")
    if isinstance(raw, str):
        raw = [raw]
    if not raw:
        one = input_data.get("location")
        raw = [one] if one else []
    out: List[str] = []
    for x in raw:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _advisory(results: List[Dict[str, Any]], delay: int, cn: bool) -> str:
    bad = [r for r in results if r.get("severe")]
    if not bad:
        return ""
    names = "、".join(r["location"] for r in bad) if cn else ", ".join(r["location"] for r in bad)
    conds = bad[0].get("condition", "")
    if cn:
        return f"发货地/目的地 {names} 当前有{conds}等恶劣天气，物流可能延迟约 {delay} 天，请向顾客说明。"
    return (f"Severe weather ({conds}) at {names}; delivery may take about "
            f"{delay} extra day(s). Set the customer's expectation accordingly.")


async def get_weather(mainwin, args):
    """MCP handler. ``args == {"input": {...}}``. Never raises."""
    try:
        input_data = (args or {}).get("input", {}) or {}
        if not isinstance(input_data, dict):
            return [TextContent(type="text", text="Error: input must be an object")]

        locations = _normalize_locations(input_data)
        if not locations:
            msg = "Missing required field: 'locations' (or 'location')"
            result = TextContent(type="text", text=f"Error: {msg}")
            result.meta = {"status": "error", "message": msg}
            return [result]

        try:
            days = int(input_data.get("days") or 2)
        except (TypeError, ValueError):
            days = 2

        vendor = _select_vendor()
        logger.info(f"[weather] vendor={vendor!r} locations={locations} days={days}")

        results = await asyncio.gather(
            *[asyncio.to_thread(_fetch_one, vendor, loc, days) for loc in locations]
        )
        results = list(results)

        severe = any(r.get("severe") for r in results)
        suggested = max((r.get("delay_days") or 0) for r in results) if results else 0
        cn = vendor == "cn" or (vendor == "mock" and _select_vendor() == "cn")

        payload = {
            "vendor": vendor,
            "checked": locations,
            "results": results,
            "severe": severe,
            "suggested_delay_days": suggested,
            "advisory": _advisory(results, suggested, cn),
        }
        result = TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))
        result.meta = {"status": "success", **payload}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetWeather")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ---------------------------------------------------------------------------
# Schema registration
# ---------------------------------------------------------------------------

def add_get_weather_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="get_weather",
        description=(
            "<category>Customer Service</category><sub-category>Shipping</sub-category>"
            "Check current weather for one or more places to set realistic "
            "delivery expectations. Call this when a customer asks about "
            "shipping / delivery time ('多久能到', '什么时候发货', 'when will it "
            "arrive') AND you know the ship-from location (from the product / "
            "warehouse). Include the customer's destination ONLY if they "
            "volunteered it — do not guess a destination. If severe weather "
            "(storm / typhoon / heavy snow / heavy rain, 暴雨 / 台风 / 暴雪 …) "
            "hits the ship-from or destination, the result has severe=true and "
            "suggested_delay_days so you can tell the customer delivery may take "
            "a few extra days. Returns JSON: {vendor, results:[{location, "
            "condition, severe, severity, delay_days}], severe, "
            "suggested_delay_days, advisory}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "locations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "City / place names to check, e.g. ['杭州'] or "
                                "['Shenzhen', 'Los Angeles']. Put the ship-from "
                                "location first; add the destination only if the "
                                "customer gave one."
                            ),
                        },
                        "location": {
                            "type": "string",
                            "description": "A single place name (alternative to 'locations').",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Forecast horizon in days (default 2).",
                        },
                    },
                }
            },
        },
    ))
