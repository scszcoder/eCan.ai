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

def _extract_inner_json(text: str) -> dict:
    """Extract and parse JSON from text that may be wrapped in markdown code blocks.
    
    Handles formats like:
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - Just raw JSON string
    - JSON-escaped text like "```json\n{\"key\": ...}\n```" (double-encoded)
    """
    if not text:
        return None
    
    # Step 1: If text looks like a JSON string with escaped content (double-encoded),
    # unescape it first by parsing as JSON
    if text.startswith('"') and text.endswith('"'):
        try:
            unescaped = json.loads(text)
            if isinstance(unescaped, str):
                text = unescaped
        except (json.JSONDecodeError, Exception):
            pass
    
    # Step 2: Try to find JSON inside markdown code blocks
    patterns = [
        r'```json\s*\n(.*?)\n```',  # ```json\n{...}\n```
        r'```\s*\n(.*?)\n```',      # ```\n{...}\n```
        r'```(.*?)```',                 # ```{...}```
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
    
    # Step 3: Try parsing the whole text as JSON (in case it's already clean)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _search_nested(data: Any, target_key: str, max_depth: int = 4) -> Any:
    """Search for `target_key` in a nested dict up to max_depth levels.

    Used when a prompt variable {{product_name}} needs to resolve from a deeply
    nested payload like {"product_profile": {"platforms": [...], "product_name": "foo"}}.
    Only descends into dict-valued keys to avoid iterating over long lists.
    """
    if max_depth <= 0 or not isinstance(data, dict):
        return None
    if target_key in data:
        return data.get(target_key)
    for k, v in data.items():
        if isinstance(v, dict):
            result = _search_nested(v, target_key, max_depth - 1)
            if result is not None:
                return result
    return None


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
        logger.debug(f"[human_input provider] found in state['input']: '{inp[:100]}...'")
        return inp.strip()

    # From messages (last item in messages list that's a plain string)
    messages = state.get("messages", [])
    if len(messages) >= 5:
        msg_txt = messages[4]
        if isinstance(msg_txt, str) and msg_txt.strip():
            logger.debug(f"[human_input provider] found in messages[4]: '{msg_txt[:100]}...'")
            return msg_txt.strip()
    
    logger.debug(f"[human_input provider] NOT FOUND: input='{inp}', messages_len={len(messages)}, messages[4]={messages[4] if len(messages) >= 5 else 'N/A'}")

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
# Reserved variable names — toolset/skillset names must not clash with these
# ---------------------------------------------------------------------------
# Includes built-in providers AND zero-config implicit variable names.
RESERVED_VARIABLE_NAMES: frozenset = frozenset({
    # Built-in providers
    "skills_schema", "tools_schema", "current_time", "current_time_local",
    "agent_name", "agent_id", "chat_id", "task_id", "human_input",
    "step_count", "max_steps",
    # Implicit zero-config variables from upstream node outputs
    "previous_node_output", "latest_output", "previous_node_id",
    "upstream_outputs", "upstream_node_ids", "search_keyword",
})


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
      1. state["prompt_refs"][var]                — explicit inputsValues written by build_node
      1.5 implicit from previous node tool_result — zero-config upstream variable passing
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

    def _ordered_tool_result_items(st: dict) -> List[tuple[str, Any]]:
        """Return tool_result items in a stable recency-aware order."""
        tr = st.get("tool_result", {}) if isinstance(st, dict) else {}
        if not isinstance(tr, dict) or not tr:
            return []

        # Start with insertion order from dict (Py3.7+).
        ordered_keys = list(tr.keys())

        # If node timings exist, reorder by completion recency.
        try:
            attrs = st.get("attributes", {}) if isinstance(st, dict) else {}
            timings = attrs.get("__node_timings__", []) if isinstance(attrs, dict) else []
            if isinstance(timings, list) and timings:
                seen = set()
                timeline = []
                for rec in timings:
                    if not isinstance(rec, dict):
                        continue
                    if rec.get("status") != "completed":
                        continue
                    node = rec.get("node")
                    if isinstance(node, str) and node in tr:
                        timeline.append(node)
                # Keep latest occurrence of each node, preserving recency.
                recency_desc = []
                for node in reversed(timeline):
                    if node in seen:
                        continue
                    seen.add(node)
                    recency_desc.append(node)
                if recency_desc:
                    ordered_keys = list(reversed(recency_desc))
                    # Append any keys that did not appear in timings.
                    for k in tr.keys():
                        if k not in seen:
                            ordered_keys.append(k)
        except Exception:
            pass

        return [(k, tr.get(k)) for k in ordered_keys]

    def _implicit_var_from_tool_result(var: str, st: dict) -> Any:
        """Zero-config variable resolution from previous node outputs.

        Supports:
        - previous_node_output / latest_output: latest completed node output
        - upstream_outputs: all previous outputs keyed by node id
        - upstream_node_ids: ordered node id list
        - arbitrary business fields (e.g. product_keyword, brand, model):
          first checks latest output top-level key, then falls back to other
          previous outputs by recency.
        - node_id variables: when var matches an upstream node id, return
          the entire node output (enabling {{node_name}} as a full-context alias).
        """
        items = _ordered_tool_result_items(st)
        if not items:
            return None

        def _try_parse_json_text(text: Any) -> Any:
            if not isinstance(text, str):
                return None
            s = text.strip()
            if not s:
                return None
            if not (s.startswith("{") or s.startswith("[")):
                return None
            try:
                return json.loads(s)
            except Exception:
                return None

        def _candidate_dicts(output: Any) -> List[dict]:
            """Collect possible business-payload dicts from a node output.

            Handles the double-nested llm_result structure produced by standard_post_llm_func:
                {"llm_result": {"llm_result": {...business JSON...}}}
            by iteratively unwrapping llm_result wrappers.

            Returns an ordered list of candidate dicts (outermost first), so callers
            can check top-level keys before falling back to nested ones.
            """
            out: List[dict] = []
            if not isinstance(output, dict):
                parsed = _try_parse_json_text(output)
                if isinstance(parsed, dict):
                    out.append(parsed)
                return out

            # Always include the raw output as the first candidate.
            out.append(output)

            # Iteratively unwrap nested llm_result wrappers.
            # Example chain: {"llm_result": {"llm_result": {"product_name": "foo"}}}
            # Step 1: inner = {"llm_result": {"product_name": "foo"}}  → append
            # Step 2: inner = {"product_name": "foo"}                  → append, no more unwrap
            current = output
            _llm_key = "llm_result"
            while True:
                if not isinstance(current, dict):
                    break
                inner = current.get(_llm_key)
                if not isinstance(inner, dict):
                    break
                # Avoid infinite loop on pathological {"llm_result": {"llm_result": ...}}
                # Only continue if the inner value is itself wrapped.
                if inner is current:
                    break
                if inner not in out:
                    out.append(inner)
                # Keep unwrapping only if the inner dict itself has an llm_result key.
                if _llm_key not in inner:
                    break
                current = inner

            # Common wrappers that may carry JSON-encoded business payload.
            # These are checked against the innermost unwrapped dict (current).
            for key in ("final", "result", "extracted_content", "content", "data"):
                val = current.get(key)
                if val is None:
                    continue
                parsed = _try_parse_json_text(val)
                if isinstance(parsed, dict) and parsed not in out:
                    out.append(parsed)

            return out

        def _extract_done_result_from_browser_use(output: Any) -> Optional[dict]:
            """Extract the done() JSON result from browser-use node output.
            
            Browser-use nodes store the done() action result differently from LLM nodes.
            The done() JSON is usually in nlp_annotation field or as part of result field.
            We need to extract just this clean JSON, not the full history with all actions.
            """
            if not isinstance(output, dict):
                return None
            
            # Check for nlp_annotation which often contains the done() result
            nlp = output.get("nlp_annotation")
            if isinstance(nlp, dict):
                result_data = nlp.get("result_data") or nlp.get("result") or nlp.get("content")
                if isinstance(result_data, dict):
                    # Check if this looks like a business JSON (has stage, platform, etc.)
                    if "stage" in result_data or "result" in result_data:
                        return result_data
            
            # Check for result field at top level
            result = output.get("result")
            if isinstance(result, dict):
                if "stage" in result or "success" in result:
                    return result
            
            # Check for message field containing clean JSON (not the full history)
            msg = output.get("message")
            if isinstance(msg, str) and msg.strip():
                # Only extract if message doesn't look like full history
                # Full history contains "actions", "all_model_outputs", "find_elements"
                if "all_model_outputs" not in msg and "find_elements" not in msg:
                    inner = _extract_inner_json(msg)
                    if inner and isinstance(inner, dict):
                        if "stage" in inner or "result" in inner:
                            return inner
            
            return None

        def _compose_search_keyword(payload: dict) -> str:
            """Resolve explicit search keyword from upstream output only."""
            if not isinstance(payload, dict):
                return ""
            direct = payload.get("search_keyword") or payload.get("product_keyword")
            if isinstance(direct, str) and direct.strip():
                return direct.strip()
            return ""

        upstream_map = {k: v for k, v in items}
        upstream_ids = [k for k, _ in items]

        # Also check state["result"] for LLM nodes directly.
        # LLM nodes store output in state["result"] (not state["tool_result"]).
        # state["result"] is a flat dict where keys are node IDs.
        direct_result = st.get("result") if isinstance(st, dict) else None
        if isinstance(direct_result, dict):
            for _k, _v in direct_result.items():
                # Skip non-node keys like "llm_result" (which is a wrapper key)
                if isinstance(_k, str) and _k not in ("llm_result",) and _k not in upstream_map:
                    upstream_map[_k] = _v
            # Also handle the common pattern: state["result"]["llm_result"] contains
            # the business output from the most recent LLM node.
            llm_wrapper = direct_result.get("llm_result")
            if isinstance(llm_wrapper, dict) and "llm_result" not in upstream_map:
                upstream_map["llm_result"] = llm_wrapper

        if var in ("previous_node_output", "latest_output"):
            return items[-1][1] if items else None
        if var == "previous_node_id":
            return items[-1][0] if items else None
        if var == "upstream_outputs":
            return upstream_map
        if var == "upstream_node_ids":
            return upstream_ids
        if var == "search_keyword":
            # Prefer latest upstream payload; then fallback by recency.
            for d in _candidate_dicts(items[-1][1] if items else None):
                kw = _compose_search_keyword(d)
                if kw:
                    return kw
            for _, output in reversed(items):
                for d in _candidate_dicts(output):
                    kw = _compose_search_keyword(d)
                    if kw:
                        return kw

        # --- Node-ID variable resolution (NEW) ---
        # When var matches an upstream node id, return the entire node output.
        # This enables {{node_name}} to inject the full node context into prompts.
        # e.g. {{llm_planner}} returns the complete planner node output.
        # Check both tool_result (MCP/code nodes) and state["result"] (LLM nodes).
        # IMPORTANT: If the output has a "message" key with backtick-wrapped JSON,
        # extract the inner JSON first so that nested {{#section}}{{key}}{{/section}}
        # accessors work correctly.
        if var in upstream_map:
            node_output = upstream_map[var]
            if isinstance(node_output, dict):
                # Check if this is a browser-use node output (has full action history)
                msg = node_output.get("message")
                if isinstance(msg, str) and msg.strip():
                    # For browser-use nodes with full history, extract only done() result
                    if "all_model_outputs" in msg or "find_elements" in msg:
                        done_result = _extract_done_result_from_browser_use(node_output)
                        if done_result:
                            logger.info(f"[prompt_var] Extracted done() result from browser-use node '{var}'")
                            return done_result
                    elif "```json" in msg or "```" in msg:
                        inner = _try_parse_json_text(msg)
                        if inner:
                            logger.info(f"[prompt_var] Extracted inner JSON from node output '{var}'")
                            return inner
                return node_output
            return str(node_output) if node_output is not None else None
        
        # Also try state["result"] directly for LLM nodes (where node ID is the key).
        if isinstance(direct_result, dict) and var in direct_result:
            node_output = direct_result[var]
            if isinstance(node_output, dict):
                msg = node_output.get("message")
                if isinstance(msg, str) and msg.strip():
                    if "```json" in msg or "```" in msg:
                        inner = _try_parse_json_text(msg)
                        if inner:
                            logger.info(f"[prompt_var] Extracted inner JSON from direct_result '{var}'")
                            return inner
                return node_output
            return str(node_output) if node_output is not None else None
        
        # Special case: check if state["result"]["llm_result"] is the upstream output
        # (happens when LLM node wrote to state["result"] without a named key).
        if var not in upstream_map and "llm_result" in (direct_result or {}):
            llm_out = direct_result.get("llm_result")
            if isinstance(llm_out, dict):
                # Return the raw llm_result dict for templates like {{llm_planner}}
                return llm_out
        
        # Special case: Handle LLM output wrapped in {"message": "```json\n{...}\n```"}
        # This format wraps the actual JSON in backticks and escapes newlines
        # e.g. {"message": "```json\n{\"stage\": \"planning\",...}\n```"}
        # We need to extract and parse the inner JSON for proper template variable access
        for candidate in [upstream_map.get(var), 
                         (direct_result.get(var) if direct_result else None),
                         direct_result.get("llm_result") if direct_result else None]:
            if isinstance(candidate, dict):
                msg = candidate.get("message")
                if isinstance(msg, str) and msg.strip():
                    # Check if message contains backtick-wrapped JSON
                    if "```json" in msg or "```" in msg:
                        inner = _extract_inner_json(msg)
                        if inner:
                            logger.info(f"[prompt_var] Extracted inner JSON for '{var}'")
                            return inner

        # Also check for nested paths like product_profile.platforms.
        # This handles the common pattern where LLM output has nested structure:
        # {"product_profile": {"platforms": [...], "product_name": ...}}
        # NOTE: _search_nested is now defined at module level for clarity.

        # Prefer direct top-level business keys from latest node output.
        for d in _candidate_dicts(items[-1][1] if items else None):
            # First try top-level key
            if var in d:
                val = d.get(var)
                if val is not None:
                    # Only return top-level value if it's a scalar or deliberate full-object
                    if not isinstance(val, dict):
                        return val
                    # If top-level value is a dict, search nested
                    nested_val = _search_nested(val, var)
                    if nested_val is not None:
                        return nested_val
                    # Return the dict as-is (it's a deliberate object reference)
                    return val

        # Fallback: search older outputs by recency (latest -> oldest).
        for _, output in reversed(items):
            for d in _candidate_dicts(output):
                if var in d:
                    val = d.get(var)
                    if val is not None:
                        if not isinstance(val, dict):
                            return val
                        nested_val = _search_nested(val, var)
                        if nested_val is not None:
                            return nested_val
                        return val
        return None

    def _ref_val_to_str(val: Any) -> str:
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2, ensure_ascii=False)
        if val is None:
            return ""
        return str(val)

    resolved = {}
    for var in variable_names:
        # DEBUG: Special logging for 'input' variable to help debug accumulation issues
        if var == "input":
            logger.debug(
                f"[prompt_var] resolving 'input': "
                f"state.input='{str(state.get('input', ''))[:100]}...' "
                f"state.messages[4]='{str(state.get('messages', ['N/A'])[4] if len(state.get('messages', [])) > 4 else 'N/A')[:100]}...' "
                f"state.events_count={len(state.get('events', []))}"
            )
        
        # 1. Explicit from state["prompt_refs"] (written by build_node from inputsValues)
        if var in prompt_refs:
            resolved[var] = _ref_val_to_str(prompt_refs[var])
            if var == "input":
                logger.debug(f"[prompt_var] 'input' resolved from prompt_refs: '{str(prompt_refs[var])[:100]}...'")
            continue

        # 1.5 Implicit zero-config variables from previous node outputs.
        # This lowers prompt authoring cost:
        # - {{product_keyword}} can come directly from upstream JSON output.
        # - {{upstream_outputs}} is available for multi-incoming-edge scenarios.
        implicit_val = _implicit_var_from_tool_result(var, state)
        if implicit_val is not None:
            resolved[var] = _ref_val_to_str(implicit_val)
            if var == "input":
                logger.debug(f"[prompt_var] 'input' resolved from implicit: '{str(implicit_val)[:100]}...'")
            continue

        # 2. Prompt-level variable declaration
        if var in prompt_variables:
            val = _resolve_variable_declaration(prompt_variables[var], state, mainwin)
            if val is not None:
                resolved[var] = val
                if var == "input":
                    logger.debug(f"[prompt_var] 'input' resolved from prompt_variables: '{str(val)[:100]}...'")
                continue

        # 3. Skill-level variable declaration
        if var in skill_prompt_variables:
            val = _resolve_variable_declaration(skill_prompt_variables[var], state, mainwin)
            if val is not None:
                resolved[var] = val
                if var == "input":
                    logger.debug(f"[prompt_var] 'input' resolved from skill_prompt_variables: '{str(val)[:100]}...'")
                continue

        # 4. Built-in provider
        provider = get_provider(var)
        if provider:
            try:
                val = provider(state, mainwin)
                if val is not None:
                    resolved[var] = val
                    if var == "input":
                        logger.debug(f"[prompt_var] 'input' resolved from builtin provider: '{str(val)[:100]}...'")
                    continue
            except Exception as e:
                logger.warning(f"[prompt_var] builtin provider '{var}' failed: {e}")

        # 5. Fallback
        resolved[var] = ""
        if var == "input":
            logger.debug("[prompt_var] 'input' fell back to empty string")

    logger.debug(f"[prompt_var] Resolved {len(resolved)} variables: {list(resolved.keys())}")
    return resolved
