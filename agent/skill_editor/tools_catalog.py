"""
Tools Catalog — builds a compact, prompt-injectable tool reference.

Sources (merged, de-duplicated by name):
    1. S3  public/mcp_tools/cloud_mcp_tools_schema.json   (built-in tools)
    2. S3  {owner}/tools/*.json                            (user custom tools)

The catalog is formatted as a concise one-line-per-tool reference grouped by
category, small enough to inject into LLM prompts (~200–400 lines).
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# ---------------------------------------------------------------------------
# S3 config
# ---------------------------------------------------------------------------
_BUCKET = "ecan-skills"
_PUBLIC_TOOLS_KEY = "public/mcp_tools/cloud_mcp_tools_schema.json"

# Module-level cache (survives across warm Lambda invocations)
_cached_public_tools: Optional[List[Dict]] = None
_cached_user_tools: Dict[str, List[Dict]] = {}  # owner → tools


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _s3_get_json(bucket: str, key: str) -> Any:
    """Read a JSON object from S3.  Returns None on missing key."""
    import boto3
    try:
        s3 = boto3.client("s3")
        resp = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception as exc:
        # NoSuchKey or any S3 error — treat as empty
        logger.debug("[ToolsCatalog] S3 read failed for %s/%s: %s", bucket, key, exc)
        return None


def _s3_list_json_keys(bucket: str, prefix: str) -> List[str]:
    """List all .json keys under *prefix* in S3."""
    import boto3
    s3 = boto3.client("s3")
    keys: List[str] = []
    continuation = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            if obj["Key"].endswith(".json"):
                keys.append(obj["Key"])
        continuation = resp.get("NextContinuationToken")
        if not continuation:
            break
    return keys


# ---------------------------------------------------------------------------
# Load raw tool schemas
# ---------------------------------------------------------------------------

def _load_public_tools() -> List[Dict]:
    """Load the built-in (public) MCP tools schema from S3 (cached)."""
    global _cached_public_tools
    if _cached_public_tools is not None:
        return _cached_public_tools

    data = _s3_get_json(_BUCKET, _PUBLIC_TOOLS_KEY)
    if data is None:
        _cached_public_tools = []
        return _cached_public_tools

    # Accept both array and {tools: [...]} wrapper
    if isinstance(data, list):
        tools = data
    elif isinstance(data, dict):
        tools = data.get("tools") or data.get("mcpTools") or []
    else:
        tools = []

    _cached_public_tools = [t for t in tools if isinstance(t, dict) and t.get("name")]
    logger.info("[ToolsCatalog] Loaded %d public tools from S3", len(_cached_public_tools))
    return _cached_public_tools


def _load_user_tools(owner: str) -> List[Dict]:
    """Load custom tools for *owner* from S3 (cached per owner)."""
    if owner in _cached_user_tools:
        return _cached_user_tools[owner]

    safe_owner = (owner or "unknown").replace("@", "_").replace(".", "_")
    prefix = f"{safe_owner}/tools/"

    user_tools: List[Dict] = []
    try:
        keys = _s3_list_json_keys(_BUCKET, prefix)
        for key in keys:
            data = _s3_get_json(_BUCKET, key)
            if isinstance(data, dict) and data.get("name"):
                user_tools.append(data)
            elif isinstance(data, list):
                user_tools.extend(t for t in data if isinstance(t, dict) and t.get("name"))
    except Exception as exc:
        logger.warning("[ToolsCatalog] Failed to load user tools for %s: %s", owner, exc)

    _cached_user_tools[owner] = user_tools
    if user_tools:
        logger.info("[ToolsCatalog] Loaded %d custom tools for %s", len(user_tools), safe_owner)
    return user_tools


# ---------------------------------------------------------------------------
# Condensation helpers
# ---------------------------------------------------------------------------

_CAT_RE = re.compile(r"<category>(.*?)</category>", re.IGNORECASE)
_SUBCAT_RE = re.compile(r"<sub-category>(.*?)</sub-category>", re.IGNORECASE)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _extract_category(desc: str) -> str:
    m = _CAT_RE.search(desc)
    return m.group(1).strip() if m else "Other"


def _extract_subcategory(desc: str) -> str:
    m = _SUBCAT_RE.search(desc)
    return m.group(1).strip() if m else ""


def _clean_description(desc: str) -> str:
    """Strip XML tags and truncate to first sentence."""
    text = _TAG_STRIP_RE.sub("", desc).strip()
    # Take first sentence (up to ~120 chars)
    for sep in (". ", ".\n", "\n"):
        idx = text.find(sep)
        if 0 < idx <= 120:
            return text[:idx + 1].strip()
    return text[:120].strip()


def _format_params(input_schema: Optional[Dict]) -> str:
    """Build compact param signature: 'param1:type, param2:type=default'."""
    if not input_schema or not isinstance(input_schema, dict):
        return ""
    props = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    if not props:
        return ""

    parts: List[str] = []
    for name, spec in props.items():
        if not isinstance(spec, dict):
            continue
        ptype = spec.get("type", "any")
        # Shorten types
        ptype = {"string": "str", "integer": "int", "number": "num",
                 "boolean": "bool", "array": "list", "object": "obj"}.get(ptype, ptype)
        if name in required:
            parts.append(f"{name}:{ptype}")
        else:
            default = spec.get("default")
            if default is not None:
                parts.append(f"{name}:{ptype}={json.dumps(default)}")
            else:
                parts.append(f"{name}:{ptype}?")
    return ", ".join(parts)


def _condense_tool(tool: Dict) -> Optional[Dict]:
    """Extract a compact representation of a single tool."""
    name = tool.get("name", "")
    if not name:
        return None
    desc = tool.get("description", "")
    category = _extract_category(desc)
    subcategory = _extract_subcategory(desc)
    clean_desc = _clean_description(desc)
    params = _format_params(tool.get("inputSchema"))
    is_custom = tool.get("source") == "user" or tool.get("_custom", False)
    return {
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "description": clean_desc,
        "params": params,
        "custom": is_custom,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_tools_catalog(owner: Optional[str] = None) -> str:
    """Build a compact, prompt-injectable tools catalog string.

    Returns Markdown-formatted text grouped by category, one line per tool:
        ## Timer & Events
        - add_timer(timer_name:str, period_ms:int, repeat_count:int=-1) — Start a recurring timer
        - remove_timer(timer_id:str) — Stop and remove a timer

    Custom user tools (if any) appear in a separate section at the end.
    """
    # Load tools
    public = _load_public_tools()
    user = _load_user_tools(owner) if owner else []

    # Merge, de-duplicate by name (user tools override built-in)
    seen: Dict[str, Dict] = {}
    for t in public:
        name = t.get("name", "")
        if name:
            condensed = _condense_tool(t)
            if condensed:
                seen[name] = condensed

    custom_tools: List[Dict] = []
    for t in user:
        name = t.get("name", "")
        if not name:
            continue
        t["_custom"] = True
        condensed = _condense_tool(t)
        if condensed:
            condensed["custom"] = True
            seen[name] = condensed
            custom_tools.append(condensed)

    if not seen:
        return "(No tools available)"

    # Group by category
    by_category: Dict[str, List[Dict]] = defaultdict(list)
    for tool_info in seen.values():
        by_category[tool_info["category"]].append(tool_info)

    # Build formatted output
    lines: List[str] = ["# Available MCP Tools"]
    lines.append(f"Total: {len(seen)} tools. When a tool below matches the task, use its exact name as callable.id and its exact parameter names.\n")

    # Sort categories, but put "Other" last
    sorted_cats = sorted(by_category.keys(), key=lambda c: (c == "Other", c))

    for cat in sorted_cats:
        tools_in_cat = sorted(by_category[cat], key=lambda t: t["name"])
        lines.append(f"## {cat}")
        for t in tools_in_cat:
            sig = f"{t['name']}({t['params']})" if t["params"] else t["name"]
            marker = " [CUSTOM]" if t.get("custom") else ""
            lines.append(f"- {sig} — {t['description']}{marker}")
        lines.append("")

    # Summary note for custom tools
    if custom_tools:
        lines.append(f"*{len(custom_tools)} custom tool(s) from this user are marked [CUSTOM] above.*")

    return "\n".join(lines)


def invalidate_cache(owner: Optional[str] = None) -> None:
    """Clear cached tool schemas.  Call when tools change at runtime."""
    global _cached_public_tools
    if owner:
        _cached_user_tools.pop(owner, None)
    else:
        _cached_public_tools = None
        _cached_user_tools.clear()
