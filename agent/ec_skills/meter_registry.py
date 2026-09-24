"""What each business-outcome meter means: name, unit, definition.

``metering.emit`` records an outcome by code -- ``(scenario_code, meter_code)``
-- and deliberately knows nothing about any site. The human-facing meaning
lives with whoever emits it, today the ``meters:`` block of a hook bundle's
``hook.yaml`` (e.g. feige_chat's ``cs_chat.message_replied`` = 客服回复). This
module collects those declarations so a screen can show "客服回复 128 条"
instead of a code, without the platform learning what any one site's outcome
is. A meter nobody declared still shows, under its code.
"""

from __future__ import annotations

import threading
from typing import Dict, Tuple

from utils.logger_helper import logger_helper as logger

MeterKey = Tuple[str, str]

_lock = threading.Lock()
_cache: Dict[MeterKey, dict] = {}
_loaded = False


def _from_bundles() -> Dict[MeterKey, dict]:
    from agent.ec_skills.browser_use_extension.hook_loader import list_available_bundles
    out: Dict[MeterKey, dict] = {}
    for bundle in list_available_bundles():
        for m in bundle.get("meters") or []:
            key = (str(m.get("scenario_code") or "").strip(), str(m.get("meter_code") or "").strip())
            if not all(key):
                continue
            out[key] = {
                "scenario_code": key[0],
                "meter_code": key[1],
                "display_name_zh": str(m.get("display_name_zh") or ""),
                "display_name_en": str(m.get("display_name_en") or ""),
                "unit": str(m.get("unit") or ""),
                "definition": str(m.get("billable_definition") or "").strip(),
                "source": f"bundle:{bundle.get('name')}",
            }
    return out


def declared_meters(refresh: bool = False) -> Dict[MeterKey, dict]:
    """Every declared meter, keyed by ``(scenario_code, meter_code)``."""
    global _loaded
    with _lock:
        if refresh or not _loaded:
            try:
                _cache.clear()
                _cache.update(_from_bundles())
            except Exception as e:
                logger.warning(f"[MeterRegistry] could not read meter declarations: {e}")
            _loaded = True
        return dict(_cache)


def describe(scenario_code: str, meter_code: str) -> dict:
    """The declaration for one meter, or a code-only stand-in."""
    known = declared_meters().get((scenario_code, meter_code))
    if known:
        return known
    return {"scenario_code": scenario_code, "meter_code": meter_code,
            "display_name_zh": "", "display_name_en": "", "unit": "",
            "definition": "", "source": "undeclared"}
