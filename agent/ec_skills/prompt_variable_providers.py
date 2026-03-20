"""
Prompt Variable Providers — Data-driven variable resolution for prompt templates.

This module implements a cascading resolution chain for {{var_name}} placeholders
in prompt templates. Variables are resolved in priority order:

  1. state["prompt_refs"][var]              — explicit (code node set it)
  2. prompt["variables"][var]               — prompt-level declaration
  3. skill.mapping_rules["prompt_variables"][var] — skill-level mapping
  4. BUILTIN_PROVIDERS[var]                 — built-in providers
  5. ""                                     — fallback empty string

Prompt-level variable declarations support multiple source types:
  - "builtin"    : delegates to a named built-in provider
  - "static"     : literal string value
  - "state_path" : dot-path into the node state dict
  - "code"       : Python expression evaluated with state in scope
  - "api"        : HTTP GET/POST to a URL (result is the response body)

Customers can extend the system by:
  - Adding "variables" to their prompt JSON (no code needed)
  - Adding "prompt_variables" to their skill's mapping_rules
  - Setting state["prompt_refs"] from a preceding code node
  - Registering custom providers via register_provider()
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# ---------------------------------------------------------------------------
# Type alias for a provider function
# Signature: (state: dict, mainwin: Any) -> str
# ---------------------------------------------------------------------------
ProviderFn = Callable[[dict, Any], str]

# ---------------------------------------------------------------------------
# Built-in provider registry
# ---------------------------------------------------------------------------
_BUILTIN_PROVIDERS: Dict[str, ProviderFn] = {}


def register_provider(name: str, fn: ProviderFn) -> None:
    """Register a named variable provider function.

    Args:
        name: Variable name this provider handles (e.g. "skills_schema").
        fn:   Callable(state, mainwin) -> str
    """
    _BUILTIN_PROVIDERS[name] = fn
    logger.debug(f"[prompt_var] Registered provider: {name}")


def get_provider(name: str) -> Optional[ProviderFn]:
    """Look up a registered provider by name."""
    return _BUILTIN_PROVIDERS.get(name)


def list_providers() -> List[str]:
    """Return names of all registered providers."""
    return list(_BUILTIN_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# Built-in providers
# ---------------------------------------------------------------------------

def _provide_skills_schema(state: dict, mainwin: Any) -> str:
    """Return JSON summary of all agent skills."""
    try:
        from agent.mcp.server.skill_schemas import get_skill_schemas_summary
        summaries = get_skill_schemas_summary(mainwin)
        if summaries:
            result = json.dumps(summaries, indent=2, ensure_ascii=False)
            logger.debug(f"[prompt_var] skills_schema: {len(summaries)} summaries, {len(result)} chars")
            return result
        return "No skills available."
    except Exception as e:
        logger.warning(f"[prompt_var] skills_schema provider failed: {e}")
        return "Skills schema unavailable."


def _provide_tools_schema(state: dict, mainwin: Any) -> str:
    """Return compact JSON summary of all MCP tool schemas for LLM decision-making.

    Outputs only name, description (XML tags stripped), and parameter names.
    Full inputSchema is NOT included — it is fetched separately at tool-call time.
    This reduces prompt size from ~172K to ~38K chars (~78% reduction).
    """
    try:
        # 1) GUI context — main-window registry
        all_schemas = getattr(mainwin, "mcp_tools_schemas", None) or []

        # 2) Cloud / no-GUI fallback — server-side tool_schemas registry
        if not all_schemas:
            try:
                from agent.mcp.server.tool_schemas import get_tool_schemas
                all_schemas = get_tool_schemas() or []
            except Exception as fallback_err:
                logger.warning(f"[prompt_var] tools_schema cloud fallback failed: {fallback_err}")

        if not all_schemas:
            return "No tools available."

        logger.debug(f"[prompt_var] tools_schema: building compact summary for {len(all_schemas)} tools")

        result = []
        for schema in all_schemas:
            name = getattr(schema, "name", "") if not isinstance(schema, dict) else schema.get("name", "")
            desc = getattr(schema, "description", "") if not isinstance(schema, dict) else schema.get("description", "")
            inp_schema = getattr(schema, "inputSchema", {}) if not isinstance(schema, dict) else schema.get("inputSchema", {})

            # Strip XML category/sub-category tags, keep human-readable text
            clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()
            clean_desc = re.sub(r"\s{2,}", " ", clean_desc)

            # Extract parameter names from inputSchema
            props = (inp_schema or {}).get("properties", {})
            inner = props.get("input", {})
            if isinstance(inner, dict) and inner.get("properties"):
                params = list(inner["properties"].keys())
            else:
                params = [p for p in props if p != "input"]

            entry = {"name": name, "description": clean_desc}
            if params:
                entry["params"] = params
            result.append(entry)

        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[prompt_var] tools_schema provider failed: {e}")
        return "Tools schema unavailable."


def _provide_current_time(state: dict, mainwin: Any) -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _provide_current_time_local(state: dict, mainwin: Any) -> str:
    """Return current local time in ISO format."""
    return datetime.now().isoformat()


def _provide_agent_name(state: dict, mainwin: Any) -> str:
    """Return the current agent's name."""
    try:
        from agent.agent_service import get_agent_by_id
        agent_id = ""
        messages = state.get("messages", [])
        if messages and isinstance(messages[0], str):
            agent_id = messages[0]
        if agent_id:
            agent = get_agent_by_id(agent_id)
            if agent and hasattr(agent, "card"):
                return getattr(agent.card, "name", "Agent")
        return "Agent"
    except Exception:
        return "Agent"


def _provide_agent_id(state: dict, mainwin: Any) -> str:
    """Return the current agent's ID."""
    messages = state.get("messages", [])
    if messages and isinstance(messages[0], str):
        return messages[0]
    return ""


def _provide_chat_id(state: dict, mainwin: Any) -> str:
    """Return the current chat ID."""
    attrs = state.get("attributes", {})
    if isinstance(attrs, dict):
        return str(attrs.get("chat_id", ""))
    return ""


def _provide_task_id(state: dict, mainwin: Any) -> str:
    """Return the current task ID."""
    attrs = state.get("attributes", {})
    if isinstance(attrs, dict):
        return str(attrs.get("task_id", ""))
    return ""


def _provide_human_input(state: dict, mainwin: Any) -> str:
    """Return the latest human input text."""
    # Direct input field
    inp = state.get("input", "")
    if isinstance(inp, str) and inp.strip():
        return inp.strip()

    # From messages (last item in messages list that's a plain string)
    messages = state.get("messages", [])
    if len(messages) >= 5:
        msg_txt = messages[4]
        if isinstance(msg_txt, str) and msg_txt.strip():
            return msg_txt.strip()

    return ""


def _provide_step_count(state: dict, mainwin: Any) -> str:
    """Return the current step count."""
    return str(state.get("n_steps", 0))


def _provide_max_steps(state: dict, mainwin: Any) -> str:
    """Return the max steps limit."""
    return str(state.get("max_steps", 300))


# Register all built-in providers
register_provider("skills_schema", _provide_skills_schema)
register_provider("tools_schema", _provide_tools_schema)
register_provider("current_time", _provide_current_time)
register_provider("current_time_local", _provide_current_time_local)
register_provider("agent_name", _provide_agent_name)
register_provider("agent_id", _provide_agent_id)
register_provider("chat_id", _provide_chat_id)
register_provider("task_id", _provide_task_id)
register_provider("human_input", _provide_human_input)
register_provider("step_count", _provide_step_count)
register_provider("max_steps", _provide_max_steps)


# ---------------------------------------------------------------------------
# Variable declaration resolver (for prompt-level and skill-level declarations)
# ---------------------------------------------------------------------------

def _resolve_state_path(state: dict, path: str) -> str:
    """Resolve a dot-separated path into the state dict.

    Example: "attributes.customer_name" → state["attributes"]["customer_name"]
    """
    current = state
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return ""
        if current is None:
            return ""
    if isinstance(current, (dict, list)):
        return json.dumps(current, indent=2, ensure_ascii=False)
    return str(current)


def _resolve_variable_declaration(
    decl: dict, state: dict, mainwin: Any
) -> Optional[str]:
    """Resolve a single variable declaration to its string value.

    Declaration format:
        {"source": "builtin",    "key": "skills_schema"}
        {"source": "static",     "value": "My eBay Store"}
        {"source": "state_path", "path": "result.llm_result.order_count"}
        {"source": "code",       "code": "len(state.get('history', []))"}
        {"source": "api",        "url": "https://...", "method": "GET"}

    Returns:
        Resolved string value, or None if resolution fails.
    """
    if not isinstance(decl, dict):
        # Simple string value — treat as static
        return str(decl) if decl is not None else None

    source = str(decl.get("source", "")).strip().lower()

    if source == "builtin":
        key = decl.get("key") or decl.get("builtin_key") or ""
        provider = get_provider(key)
        if provider:
            try:
                return provider(state, mainwin)
            except Exception as e:
                logger.warning(f"[prompt_var] builtin provider '{key}' failed: {e}")
                return None
        else:
            logger.warning(f"[prompt_var] Unknown builtin provider: '{key}'")
            return None

    elif source == "static":
        val = decl.get("value", "")
        return str(val) if val is not None else ""

    elif source == "state_path":
        path = decl.get("path", "")
        if path:
            return _resolve_state_path(state, path)
        return None

    elif source == "code":
        code_str = decl.get("code", "")
        if code_str:
            try:
                # Provide state and mainwin in the eval scope
                result = eval(code_str, {"__builtins__": {}}, {
                    "state": state,
                    "mainwin": mainwin,
                    "json": json,
                    "time": time,
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "list": list,
                    "dict": dict,
                    "bool": bool,
                    "isinstance": isinstance,
                    "getattr": getattr,
                    "hasattr": hasattr,
                })
                if isinstance(result, (dict, list)):
                    return json.dumps(result, indent=2, ensure_ascii=False)
                return str(result)
            except Exception as e:
                logger.warning(f"[prompt_var] code eval failed: {e}")
                return None
        return None

    elif source == "api":
        url = decl.get("url", "")
        method = str(decl.get("method", "GET")).upper()
        if url:
            try:
                import httpx
                with httpx.Client(timeout=10.0) as client:
                    if method == "POST":
                        body = decl.get("body", {})
                        headers = decl.get("headers", {})
                        resp = client.post(url, json=body, headers=headers)
                    else:
                        headers = decl.get("headers", {})
                        resp = client.get(url, headers=headers)
                    resp.raise_for_status()
                    return resp.text
            except Exception as e:
                logger.warning(f"[prompt_var] API call to '{url}' failed: {e}")
                return None
        return None

    else:
        # Unknown source type — treat value as static if present
        val = decl.get("value")
        if val is not None:
            return str(val)
        logger.warning(f"[prompt_var] Unknown variable source type: '{source}'")
        return None


# ---------------------------------------------------------------------------
# Cascading resolution chain
# ---------------------------------------------------------------------------

def resolve_prompt_variables(
    variable_names: List[str],
    state: dict,
    mainwin: Any,
    prompt_variables: Optional[Dict[str, Any]] = None,
    skill_prompt_variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Resolve a list of variable names using the cascading resolution chain.

    Resolution priority (first match wins):
      1. state["prompt_refs"][var]                — explicit from code node
      2. prompt_variables[var]                    — prompt-level declaration
      3. skill_prompt_variables[var]              — skill-level mapping
      4. BUILTIN_PROVIDERS[var]                   — built-in provider
      5. ""                                       — fallback empty

    Args:
        variable_names:         List of variable names found in the prompt template.
        state:                  Current node state dict.
        mainwin:                Main window / app context object.
        prompt_variables:       Variable declarations from the prompt JSON's "variables" field.
        skill_prompt_variables: Variable declarations from skill.mapping_rules["prompt_variables"].

    Returns:
        Dict mapping variable name → resolved string value.
    """
    prompt_refs = state.get("prompt_refs", {}) or {}
    prompt_variables = prompt_variables or {}
    skill_prompt_variables = skill_prompt_variables or {}

    resolved = {}
    for var in variable_names:
        # 1. Explicit from state["prompt_refs"]
        if var in prompt_refs:
            resolved[var] = str(prompt_refs[var])
            continue

        # 2. Prompt-level variable declaration
        if var in prompt_variables:
            val = _resolve_variable_declaration(prompt_variables[var], state, mainwin)
            if val is not None:
                resolved[var] = val
                continue

        # 3. Skill-level variable declaration
        if var in skill_prompt_variables:
            val = _resolve_variable_declaration(skill_prompt_variables[var], state, mainwin)
            if val is not None:
                resolved[var] = val
                continue

        # 4. Built-in provider
        provider = get_provider(var)
        if provider:
            try:
                val = provider(state, mainwin)
                if val is not None:
                    resolved[var] = val
                    continue
            except Exception as e:
                logger.warning(f"[prompt_var] builtin provider '{var}' failed: {e}")

        # 5. Fallback
        resolved[var] = ""

    logger.debug(f"[prompt_var] Resolved {len(resolved)} variables: {list(resolved.keys())}")
    return resolved
