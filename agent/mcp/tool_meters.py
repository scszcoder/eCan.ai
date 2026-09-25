"""Business outcomes produced by MCP tools: declared by the tool, emitted by the platform.

A tool that DOES something a seller would pay for -- creates a listing,
optimises an ad, handles a return -- declares a meter here. The platform, not
the tool, records the outcome, and only when:

* the call succeeded (an error result is never an outcome);
* the result names the outcome (``outcome_id_field``: the listing id, the
  campaign id). That id is the idempotency key, so a retried call that returns
  the same listing is counted once. No id, no event -- never a made-up key.

Emission rule 2 of agent/ec_skills/metering.py holds: a tool never calls
``metering.emit``; ``record_tool_outcome`` is invoked only by the two platform
call paths (the MCP server's handler and build_node's cloud-direct path).

Attribution (store / agent / task) comes from the caller's run scope. Over the
HTTP hop that scope travels as MCP request ``meta`` (``scope_meta`` on the
client, ``scope_from_meta`` on the server); in-process it is simply present.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

META_KEY = "ecan_scope"
# Only attribution crosses the hop; nothing else of the scope is sent.
_SCOPE_FIELDS = ("store_id", "agent_id", "task_id", "skill_id", "vehicle_id", "owner")

_TOOL_METERS: Dict[str, Dict[str, str]] = {}


def declare_tool_meter(tool_name: str, *, scenario_code: str, meter_code: str,
                       outcome_id_field: str, display_name_zh: str = "",
                       display_name_en: str = "", unit: str = "", definition: str = "") -> None:
    """Declare that ``tool_name`` produces one countable outcome per successful call."""
    if not (tool_name and scenario_code and meter_code and outcome_id_field):
        raise ValueError("tool_name, scenario_code, meter_code and outcome_id_field are required")
    _TOOL_METERS[tool_name] = {
        "scenario_code": scenario_code, "meter_code": meter_code,
        "outcome_id_field": outcome_id_field, "display_name_zh": display_name_zh,
        "display_name_en": display_name_en, "unit": unit, "definition": definition,
    }


def declared_tool_meters() -> Dict[str, Dict[str, str]]:
    return dict(_TOOL_METERS)


# ── scope across the HTTP hop ────────────────────────────────────────

def scope_meta() -> Optional[Dict[str, Any]]:
    """The caller's attribution as MCP request meta, or None when there is none."""
    try:
        from utils.log_scope import get_scope
        sc = get_scope() or {}
    except Exception:
        return None
    fields = {k: str(sc[k]) for k in _SCOPE_FIELDS if sc.get(k)}
    return {META_KEY: fields} if fields else None


def scope_from_meta(meta: Any) -> Dict[str, str]:
    """Attribution fields from a request's meta (pydantic model or dict), or {}."""
    raw = getattr(meta, META_KEY, None) if meta is not None and not isinstance(meta, dict) else (meta or {}).get(META_KEY)
    if not isinstance(raw, dict):
        return {}
    return {k: str(v) for k, v in raw.items() if k in _SCOPE_FIELDS and v}


# ── recording ────────────────────────────────────────────────────────

def _is_error(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("isError"))
    return bool(getattr(result, "isError", False))


def _payloads(result: Any):
    """Every dict a tool result may carry its outcome in."""
    if isinstance(result, dict):
        yield result
        result = result.get("content")
    content = getattr(result, "content", result)
    for block in content if isinstance(content, (list, tuple)) else []:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if isinstance(text, str) and text.strip().startswith("{"):
            try:
                data = json.loads(text)
            except ValueError:
                continue
            if isinstance(data, dict):
                yield data


def outcome_id(result: Any, field: str) -> str:
    for data in _payloads(result):
        value = data.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def record_tool_outcome(tool_name: str, result: Any) -> bool:
    """Emit the tool's declared meter if the call produced an outcome. Never raises."""
    spec = _TOOL_METERS.get(tool_name)
    if spec is None or _is_error(result):
        return False
    try:
        oid = outcome_id(result, spec["outcome_id_field"])
        if not oid:
            logger.warning(f"[ToolMeter] {tool_name} succeeded but returned no "
                           f"{spec['outcome_id_field']!r}; outcome not recorded")
            return False
        from agent.ec_skills import metering
        return metering.emit(spec["scenario_code"], spec["meter_code"],
                             idempotency_key=f"tool:{tool_name}:{oid}",
                             evidence={"tool": tool_name, "outcome_id": oid})
    except Exception as e:
        logger.warning(f"[ToolMeter] recording {tool_name} outcome failed: {e}")
        return False
