import re
import os
import json
import string
import importlib.util
import httpx
from urllib.parse import urlparse, parse_qsl, urlunparse
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
from agent.ec_skills.dev_defs import BreakpointManager
from agent.ec_tasks.pending_events import register_async_operation, resolve_async_operation
from langchain_core.messages import HumanMessage, SystemMessage
from agent.ec_skill import node_builder
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from langgraph.types import interrupt
from app_context import AppContext
from utils.env.secure_store import secure_store, get_current_username
from agent.ec_skills.llm_utils.llm_utils import _create_no_proxy_http_client
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_community.chat_models import ChatAnthropic
from langchain_community.chat_models import ChatOllama
from langchain_deepseek import ChatDeepSeek
from gui.ipc.w2p_handlers import prompt_handler
web_gui = AppContext.get_web_gui()


from typing import Any, Literal, cast, overload

from langchain_core.messages.base import BaseMessage, BaseMessageChunk


def resolve_timeout(
    node_name: str,
    state: dict,
    tool_input: dict = None,
    config_timeout: float = None,
    default_timeout: float = 60.0
) -> float:
    """
    Resolve timeout with precedence: tool_input > state override > config > default.
    
    Args:
        node_name: Name of the current node
        state: Current workflow state
        tool_input: Tool input dict (for MCP tools)
        config_timeout: Timeout from node config (design-time)
        default_timeout: Final fallback default
        
    Returns:
        Resolved timeout in seconds
        
    Precedence (highest to lowest):
        1. tool_input["_timeout"] - per-call override
        2. state["_timeout_overrides"][node_name] - per-node runtime override
        3. state["_timeout_overrides"]["*"] - global runtime override
        4. config_timeout - design-time config
        5. default_timeout - hardcoded default
    """
    # 1. Check tool_input override (Option B)
    if tool_input and isinstance(tool_input, dict):
        if "_timeout" in tool_input:
            try:
                return float(tool_input["_timeout"])
            except (ValueError, TypeError):
                pass
    
    # 2. Check state overrides (Option A)
    if state and isinstance(state, dict):
        overrides = state.get("_timeout_overrides")
        if isinstance(overrides, dict):
            # Per-node override
            if node_name in overrides:
                try:
                    return float(overrides[node_name])
                except (ValueError, TypeError):
                    pass
            # Global override
            if "*" in overrides:
                try:
                    return float(overrides["*"])
                except (ValueError, TypeError):
                    pass
    
    # 3. Config timeout (design-time)
    if config_timeout is not None:
        try:
            return float(config_timeout)
        except (ValueError, TypeError):
            pass
    
    # 4. Default
    return default_timeout


def resolve_hard_timeout(
    node_name: str,
    state: dict,
    tool_input: dict = None,
    config_hard_timeout: bool = False
) -> bool:
    """
    Resolve whether to use hard timeout (cancel on timeout) vs soft timeout (guardrail only).
    
    Args:
        node_name: Name of the current node
        state: Current workflow state
        tool_input: Tool input dict (for MCP tools)
        config_hard_timeout: Hard timeout setting from node config
        
    Returns:
        True if hard timeout should be used (cancel operation on timeout)
        
    Precedence (highest to lowest):
        1. tool_input["_hard_timeout"] - per-call override
        2. state["_hard_timeout_overrides"][node_name] - per-node runtime override
        3. state["_hard_timeout_overrides"]["*"] - global runtime override
        4. config_hard_timeout - design-time config
        5. False (default: soft timeout)
    """
    # 1. Check tool_input override
    if tool_input and isinstance(tool_input, dict):
        if "_hard_timeout" in tool_input:
            val = tool_input["_hard_timeout"]
            if isinstance(val, bool):
                return val
            return str(val).lower() in ('true', '1', 'yes', 'on')
    
    # 2. Check state overrides
    if state and isinstance(state, dict):
        overrides = state.get("_hard_timeout_overrides")
        if isinstance(overrides, dict):
            # Per-node override
            if node_name in overrides:
                val = overrides[node_name]
                if isinstance(val, bool):
                    return val
                return str(val).lower() in ('true', '1', 'yes', 'on')
            # Global override
            if "*" in overrides:
                val = overrides["*"]
                if isinstance(val, bool):
                    return val
                return str(val).lower() in ('true', '1', 'yes', 'on')
    
    # 3. Config setting
    if config_hard_timeout:
        return True
    
    # 4. Default: soft timeout
    return False


class ActionMessage(BaseMessage):
    """Message for capture action and action result.

    The action message is use for recording action in history

    Example:
        ```python
        from build_node import ActionMessage

        messages = [
            SystemMessage(content="You are a helpful assistant! Your name is Bob."),
            HumanMessage(content="What is your name?"),
            ActionMessage(content="action: search; result: found 10 results")
        ]

        # Define a chat model and invoke it with the messages
        print(model.invoke(messages))
        ```
    """

    type: Literal["action"] = "action"
    """The type of the message (used for serialization)."""

    @overload
    def __init__(
        self,
        content: str | list[str | dict],
        **kwargs: Any,
    ) -> None: ...

    @overload
    def __init__(
        self,
        content: str | list[str | dict] | None = None,
        content_blocks: list[dict | str] | None = None,
        **kwargs: Any,
    ) -> None: ...

    def __init__(
        self,
        content: str | list[str | dict] | None = None,
        content_blocks: list[dict | str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Specify `content` as positional arg or `content_blocks` for typing."""
        if content_blocks is not None:
            super().__init__(
                content=cast("str | list[str | dict]", content_blocks),
                **kwargs,
            )
        else:
            super().__init__(content=content, **kwargs)


try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:
    ChatGoogleGenerativeAI = None
try:
    from langchain_qwq import ChatQwQ
except Exception:
    ChatQwQ = None

def get_default_node_schemas():
    schemas = {
        "llm" : {

        }
    }
    return schemas


def add_to_history(state, messages):
    if not isinstance(state.get("history"), list):
        state["history"] = []

    if isinstance(messages, list):
        state["history"].extend(messages)
    else:
        state["history"].append(messages)


STANDARD_SYS_PROMPT = "You are a helpful AI assistant."
BROWSER_AUTOMATION_SYS_PROMPT = "You are a helpful browser automation agent."


def _resolve_prompt_templates(prompt_selection: str, inline_system: str, inline_user: str) -> tuple[str, str]:
    """Resolve system/user prompt templates based on selection."""
    selection = (prompt_selection or "inline").strip()
    if selection in ("", "inline"):
        return inline_system, inline_user

    try:
        prompts = prompt_handler._load_all_prompts()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning(f"Failed to load prompts from disk for selection '{selection}': {exc}")
        prompts = []

    prompt_data = next((p for p in prompts if p.get("id") == selection), None)
    if not prompt_data:
        logger.warning(f"Prompt selection '{selection}' not found. Falling back to inline prompts.")
        return inline_system, inline_user

    normalized = prompt_data
    if not isinstance(normalized, dict) or "sections" not in normalized:
        try:
            normalized = prompt_handler._normalize_prompt(
                prompt_data,
                source=str(prompt_data.get("source") or "inline"),
                read_only=bool(prompt_data.get("readOnly")),
                last_modified_ts=None,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(f"Failed to normalize prompt '{selection}': {exc}")
            return inline_system, inline_user

    def _join_list(items: list[str]) -> str:
        lines = []
        for idx, item in enumerate(items or [], 1):
            text = str(item).strip()
            if text:
                lines.append(f"{idx}. {text}")
        return "\n".join(lines)

    def _parse_tools_to_use_item(raw: str) -> list[str]:
        """Parse a tools_to_use item which can be JSON array or comma-separated string."""
        s = str(raw or "").strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if v]
        except Exception:
            pass
        return [v.strip() for v in s.split(',') if v.strip()]

    def _get_tool_schemas_for_names(tool_names: list[str]) -> list[dict]:
        """Fetch full tool schemas for the given tool names from MCP registry."""
        try:
            mainwin = AppContext.get_main_window()
            all_schemas = getattr(mainwin, 'mcp_tools_schemas', None) or []
            logger.debug(f"[_get_tool_schemas_for_names] Looking for {len(tool_names)} tools in registry with {len(all_schemas)} schemas")
            result = []
            seen = set()
            for name in tool_names:
                if name in seen:
                    continue
                seen.add(name)
                for schema in all_schemas:
                    schema_name = getattr(schema, 'name', None) or (schema.get('name') if isinstance(schema, dict) else None)
                    schema_id = getattr(schema, 'id', None) or (schema.get('id') if isinstance(schema, dict) else None)
                    if schema_name == name or schema_id == name:
                        # Convert to dict if it's a pydantic model
                        if hasattr(schema, 'model_dump'):
                            schema_dict = schema.model_dump()
                        elif isinstance(schema, dict):
                            schema_dict = schema
                        else:
                            schema_dict = {
                                'name': getattr(schema, 'name', ''),
                                'description': getattr(schema, 'description', ''),
                                'inputSchema': getattr(schema, 'inputSchema', {}),
                            }
                        result.append(schema_dict)
                        break
            return result
        except Exception as e:
            logger.warning(f"Failed to get tool schemas: {e}")
            return []

    def _format_tools_to_use_section(items: list[str]) -> str:
        """Format tools_to_use section with full tool schemas instead of just names."""
        # Collect all tool names from items
        all_tool_names = []
        seen = set()
        for item in items:
            for name in _parse_tools_to_use_item(item):
                if name not in seen:
                    seen.add(name)
                    all_tool_names.append(name)
        
        logger.debug(f"[_format_tools_to_use_section] Parsed tool names: {all_tool_names}")
        
        if not all_tool_names:
            logger.debug("[_format_tools_to_use_section] No tool names found, returning empty")
            return ""
        
        # Get full schemas
        schemas = _get_tool_schemas_for_names(all_tool_names)
        logger.debug(f"[_format_tools_to_use_section] Got {len(schemas)} schemas for {len(all_tool_names)} tool names")
        
        if not schemas:
            # Fallback to just listing names if schemas not available
            logger.debug("[_format_tools_to_use_section] No schemas found, falling back to name list")
            return _join_list(all_tool_names)
        
        # Format schemas as JSON for LLM to understand
        lines = []
        for idx, schema in enumerate(schemas, 1):
            schema_json = json.dumps(schema, indent=2, ensure_ascii=False)
            lines.append(f"{idx}. {schema_json}")
        result = "\n".join(lines)
        logger.debug(f"[_format_tools_to_use_section] Formatted {len(schemas)} tool schemas, total length: {len(result)}")
        return result

    def _section_label(section: dict) -> str:
        sec_type = str((section or {}).get("type") or "").strip()
        if not sec_type:
            return ""
        if sec_type == "custom" and section.get("customLabel"):
            return str(section.get("customLabel")).strip()
        return sec_type.replace("_", " ").title()

    def _add_section(parts: list[str], title: str | None, content: str) -> None:
        clean = content.strip()
        if not clean:
            return
        if title:
            parts.append(f"[{title}]\n{clean}")
        else:
            parts.append(clean)

    sys_parts: list[str] = []
    role_context = str(normalized.get("roleToneContext") or "").strip()
    if role_context:
        sys_parts.append(role_context)

    # Track if tools_to_use section has been added to avoid duplication
    tools_to_use_added = False
    
    # Check if inline system prompt already contains an actual tools_to_use SECTION header
    # We look for section headers at the start of a line, not just mentions in text
    # e.g. "[Tools To Use]\n" or "<tools_to_use>\n...content...\n</tools_to_use>"
    import re
    inline_lower = inline_system.lower()
    # Match actual section headers: [Tools To Use] at line start, or XML-style <tools_to_use>...</tools_to_use>
    has_tools_section = bool(
        re.search(r'^\s*\[tools[_ ]to[_ ]use\]', inline_lower, re.MULTILINE) or
        re.search(r'<tools_to_use>\s*\n.*?</tools_to_use>', inline_lower, re.DOTALL)
    )
    if has_tools_section:
        tools_to_use_added = True
        logger.debug("[_resolve_prompt_templates] tools_to_use section header found in inline system prompt, skipping structured section")

    structured_sections = normalized.get("sections") or []
    if structured_sections:
        for section in structured_sections:
            if not isinstance(section, dict):
                continue
            sec_type = str(section.get("type") or "").strip().lower()
            items = section.get("items") if isinstance(section.get("items"), list) else []
            # Handle tools_to_use specially - fetch full schemas, skip if already added
            if sec_type == "tools_to_use":
                if tools_to_use_added:
                    logger.debug("[_resolve_prompt_templates] Skipping duplicate tools_to_use section")
                    continue
                joined = _format_tools_to_use_section(items)
                if joined:
                    tools_to_use_added = True
            else:
                joined = _join_list(items)
            if not joined:
                continue
            label = _section_label(section)
            _add_section(sys_parts, label or None, joined)
    else:
        system_sections = normalized.get("systemSections") or []
        for section in system_sections:
            if not isinstance(section, dict):
                continue
            sec_type = str(section.get("type") or "").strip().lower()
            label = sec_type.replace("_", " ").title() if sec_type else ""
            items = section.get("items") if isinstance(section.get("items"), list) else []
            # Handle tools_to_use specially - fetch full schemas, skip if already added
            if sec_type == "tools_to_use":
                if tools_to_use_added:
                    logger.debug("[_resolve_prompt_templates] Skipping duplicate tools_to_use section")
                    continue
                joined = _format_tools_to_use_section(items)
                if joined:
                    tools_to_use_added = True
            else:
                joined = _join_list(items)
            _add_section(sys_parts, label or None, joined if joined else "")

        for label, field_name in (
            ("Goals", "goals"),
            ("Guidelines", "guidelines"),
            ("Rules", "rules"),
        ):
            values = normalized.get(field_name) or []
            joined = _join_list(values if isinstance(values, list) else [])
            if joined:
                _add_section(sys_parts, label, joined)

    system_text = "\n\n".join(part for part in sys_parts if part) or inline_system

    user_parts: list[str] = []
    title = str(normalized.get("title") or "").strip()
    topic = str(normalized.get("topic") or "").strip()
    if title and title != selection:
        user_parts.append(title)
    if topic and topic.lower() not in {"", "new prompt"} and topic.lower() != title.lower():
        user_parts.append(topic)

    # normalized is guaranteed to be dict from _normalize_prompt
    instructions = normalized.get("instructions") or []
    instructions_joined = _join_list(instructions if isinstance(instructions, list) else [])
    if instructions_joined:
        _add_section(user_parts, "Instructions", instructions_joined)

    # Prioritize userSections over humanInputs - only use humanInputs if userSections is empty
    user_sections = normalized.get("userSections") or []
    user_sections_has_content = any(
        isinstance(s, dict) and s.get("items") and any(str(i).strip() for i in (s.get("items") if isinstance(s.get("items"), list) else []))
        for s in user_sections
    )
    
    if user_sections_has_content:
        # Use userSections
        for section in user_sections:
            if not isinstance(section, dict):
                continue
            sec_type = str(section.get("type") or "").strip().lower()
            items = section.get("items") if isinstance(section.get("items"), list) else []
            # Handle tools_to_use specially - fetch full schemas
            if sec_type == "tools_to_use":
                joined = _format_tools_to_use_section(items)
            else:
                joined = _join_list(items)
            if not joined:
                continue
            label = _section_label(section)
            _add_section(user_parts, label or None, joined)
    else:
        # Fallback to humanInputs if userSections is empty
        human_inputs = normalized.get("humanInputs") or []
        human_inputs_joined = _join_list(human_inputs if isinstance(human_inputs, list) else [])
        if human_inputs_joined:
            _add_section(user_parts, "Provide", human_inputs_joined)

    sys_inputs = normalized.get("sysInputs") or []
    sys_inputs_joined = _join_list(sys_inputs if isinstance(sys_inputs, list) else [])
    if sys_inputs_joined:
        _add_section(user_parts, "System Inputs", sys_inputs_joined)

    additional_prompt = str(normalized.get("prompt") or "").strip()
    if additional_prompt:
        user_parts.append(additional_prompt)

    user_text = "\n\n".join(part for part in user_parts if part) or inline_user

    return system_text, user_text


def _escape_positional_placeholders(template: str) -> str:
    """Turn positional format fields like ``{}`` or ``{0}`` into literal braces."""
    if not template:
        return template

    formatter = string.Formatter()
    rebuilt: list[str] = []

    for literal_text, field_name, format_spec, conversion in formatter.parse(template):
        if literal_text:
            rebuilt.append(literal_text.replace("{", "{{").replace("}", "}}"))

        if field_name is None:
            continue

        conv_fragment = f"!{conversion}" if conversion else ""
        spec_fragment = f":{format_spec}" if format_spec else ""

        is_identifier = bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field_name or ""))
        needs_escape = (
            not field_name
            or field_name.isdigit()
            or not is_identifier
            or format_spec not in (None, "")
            or conversion not in (None, "")
        )

        if needs_escape:
            # Render literally by doubling braces
            inner = f"{field_name or ''}{conv_fragment}{spec_fragment}"
            rebuilt.append("{{" + inner + "}}")
        else:
            rebuilt.append("{")
            rebuilt.append(field_name)
            rebuilt.append(conv_fragment)
            rebuilt.append(spec_fragment)
            rebuilt.append("}")

    return "".join(rebuilt)
def build_llm_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    """
    Builds a callable function for a LangGraph node that interacts with an LLM.

    Args:
        config_metadata: A dictionary containing the configuration for the LLM node,
                         including provider, model, temperature, and prompt templates.
                         - timeout_seconds: Max time for LLM call (default 150)
                         - enable_guardrail_timer: If True, register pending event for timeout tracking

    Returns:
        A callable function that takes a state dictionary and returns the updated state.
    """
    # Extract configuration from metadata with sensible defaults (tolerant to missing keys)
    logger.debug("building llm node:", config_metadata)
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
    
    # Guardrail timer configuration
    enable_guardrail_timer = False
    llm_timeout_seconds = 150.0
    hard_timeout_config = False  # If True, cancel operation on timeout (like browser-use)
    try:
        enable_guardrail_timer = (config_metadata.get('enable_guardrail_timer')
                                  or ((inputs.get('enable_guardrail_timer') or {}).get('content'))
                                  or (config_metadata.get('inputs') or {}).get('enable_guardrail_timer'))
        enable_guardrail_timer = str(enable_guardrail_timer).lower() in ('true', '1', 'yes', 'on') if enable_guardrail_timer else False
        
        timeout_val = (config_metadata.get('timeout_seconds')
                       or ((inputs.get('timeout_seconds') or {}).get('content'))
                       or (config_metadata.get('inputs') or {}).get('timeout_seconds'))
        if timeout_val:
            llm_timeout_seconds = float(timeout_val)
        
        hard_timeout_val = (config_metadata.get('hard_timeout')
                            or ((inputs.get('hard_timeout') or {}).get('content'))
                            or (config_metadata.get('inputs') or {}).get('hard_timeout'))
        hard_timeout_config = str(hard_timeout_val).lower() in ('true', '1', 'yes', 'on') if hard_timeout_val else False
    except Exception:
        pass
    # Prefer explicit provider; infer from apiHost if absent
    raw_provider = None
    try:
        raw_provider = ((inputs.get("modelProvider") or {}).get("content")
                        or (inputs.get("provider") or {}).get("content"))
    except Exception:
        raw_provider = None
    model_name = ((inputs.get("modelName") or {}).get("content")
                  or (inputs.get("model") or {}).get("content")
                  or "gpt-3.5-turbo")
    api_key = ((inputs.get("apiKey") or {}).get("content") or "")
    api_host = ((inputs.get("apiHost") or {}).get("content") or "")
    try:
        temperature = float(((inputs.get("temperature") or {}).get("content") or 0.5))
    except Exception:
        temperature = 0.5
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}

    prompt_selection = ((inputs.get("promptSelection") or {}).get("content") or "inline").strip()
    logger.debug("[LLMNode]prompt_selection:", prompt_selection)

    system_prompt_id = ((inputs.get("systemPromptId") or {}).get("content") or None)
    user_prompt_id = ((inputs.get("promptId") or {}).get("content") or None)
    logger.debug("[LLMNode]system_prompt_id:", system_prompt_id)
    logger.debug("[LLMNode]user_prompt_id:", user_prompt_id)

    # Get inline prompt content
    inline_system_prompt = ((inputs.get("systemPrompt") or {}).get("content") or STANDARD_SYS_PROMPT)
    inline_user_prompt = ((inputs.get("prompt") or {}).get("content") or STANDARD_SYS_PROMPT)

    logger.debug("[LLMNode]inline_system_prompt:", inline_system_prompt)
    logger.debug("[LLMNode]inline_user_prompt:", inline_user_prompt)

    # Resolve prompt templates based on the selected prompt id first for initial config preview
    resolved_system_prompt, resolved_user_prompt = _resolve_prompt_templates(
        prompt_selection,
        inline_system_prompt,
        inline_user_prompt,
    )

    # Load prompts using legacy prompt ids if provided for backwards compatibility
    from agent.ec_skills.prompt_loader import get_prompt_content

    if system_prompt_id:
        system_prompt_template = get_prompt_content(system_prompt_id, resolved_system_prompt)
    else:
        system_prompt_template = resolved_system_prompt

    if user_prompt_id:
        user_prompt_template = get_prompt_content(user_prompt_id, resolved_user_prompt)
    else:
        user_prompt_template = resolved_user_prompt
    # Infer provider when not explicitly set
    def _infer_provider(host: str, model: str) -> str:
        try:
            h = (host or "").lower()
            m = (model or "").lower()
            if "anthropic" in h or m.startswith("claude"):
                return "anthropic"
            if "google" in h or "generativeai" in h or m.startswith("gemini"):
                return "google"
            return "openai"
        except Exception:
            return "openai"

    model_provider = raw_provider or _infer_provider(api_host, model_name)
    llm_provider = (model_provider or "openai").lower()

    # Normalize provider names (handle spaces in provider names)
    # Map frontend provider names to backend identifiers
    provider_mapping = {
        'azure openai': 'azure',
        'anthropic claude': 'anthropic',
        'aws bedrock': 'bedrock',
        'google gemini': 'google',
        'qwen (dashscope)': 'qwen',
        'ollama (local)': 'ollama',
        'bytedance doubao': 'bytedance',
        'dashscope/qwen': 'dashscope',
        'baidu qianfan': 'baidu_qianfan',
        '百度千帆': 'baidu_qianfan',
    }
    logger.info(f"llm config: system_prompt_template='{system_prompt_template}' user_prompt_template='{user_prompt_template}' ")
    logger.info(f"llm config: model_name={model_name} api_host={api_host} api_key={api_key} model_provider={model_provider} llm_provider={llm_provider}")

    llm_provider = provider_mapping.get(llm_provider, llm_provider)

    # This is the actual function that will be executed as the node in the graph
    def llm_node_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        """
        The runtime callable for the LLM node. It formats prompts, invokes the LLM,
        and updates the state with the response.
        """
        from agent.ec_skills.llm_hooks.llm_hooks import run_pre_llm_hook, run_post_llm_hook
        from agent.agent_service import get_agent_by_id
        from agent.ec_skills.llm_utils.llm_utils import get_recent_context

        import time as _time
        _t0 = _time.perf_counter()

        def _perf_llm(stage: str, t_start: float, extra: dict | None = None):
            try:
                dt_ms = int(max((_time.perf_counter() - t_start), 0.0) * 1000)
                logger.info(
                    f"[PERF][LLM] node={node_name} skill={skill_name} stage={stage} duration_ms={dt_ms}"
                )
                if isinstance(state, dict):
                    attrs = state.get("attributes")
                    if not isinstance(attrs, dict):
                        attrs = {}
                        state["attributes"] = attrs
                    lst = attrs.get("__llm_timings__")
                    if not isinstance(lst, list):
                        lst = []
                        attrs["__llm_timings__"] = lst
                    item = {
                        "node": str(node_name),
                        "skill": str(skill_name),
                        "stage": str(stage),
                        "duration_ms": dt_ms,
                        "ts_ms": int(_time.time() * 1000),
                    }
                    if isinstance(extra, dict) and extra:
                        item.update(extra)
                    lst.append(item)
            except Exception:
                pass

        log_msg = f"🤖 Executing node LLM node: {node_name}"
        logger.info(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        log_msg = f"State: {state}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        # obtain code from code based workflow.
        current_node_name = runtime.context["this_node"].get("name")
        skill_name = runtime.context["this_node"].get("skill_name")
        owner = runtime.context["this_node"].get("owner")
        full_node_name = f"{owner}:{skill_name}:{current_node_name}"

        log_msg = f"full_node_name: {full_node_name}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)


        # Use the already-resolved templates from build time (which include full tool schemas)
        # instead of calling _resolve_prompt_templates again at runtime
        # The build-time resolution (lines 475-492) already processed prompt_selection and
        # fetched tool schemas - calling it again at runtime may lose that context
        active_system_prompt = system_prompt_template
        active_user_prompt = user_prompt_template
        logger.debug(f"[LLM] Using pre-resolved prompts: system_len={len(active_system_prompt)}, user_len={len(active_user_prompt)}")

        # Find all variable placeholders (e.g., {{var_name}}) in the prompts
        variables = re.findall(r'\{\{(\w+)\}\}', active_system_prompt + active_user_prompt)

        # Get attributes from state, default to an empty dict if not present
        prompt_refs = state.get("prompt_refs", {})

        # Prepare the context for formatting the prompts by pulling values from the state
        format_context = {}
        for var in variables:
            if var in prompt_refs:
                format_context[var] = prompt_refs[var]
            else:
                logger.warning(f"Warning: Variable '{{{{{{var}}}}}}' not found in state prompt_refs. Using empty string.")
                format_context[var] = ""

        # Substitute {{var_name}} with values from format_context
        try:
            _t_stage = _time.perf_counter()
            final_system_prompt = active_system_prompt
            final_user_prompt = active_user_prompt
            for var, val in format_context.items():
                final_system_prompt = final_system_prompt.replace(f'{{{{{var}}}}}', str(val))
                final_user_prompt = final_user_prompt.replace(f'{{{{{var}}}}}', str(val))

            logger.debug("final_system_prompt:", final_system_prompt)
            logger.debug("final_user_prompt:", final_user_prompt)
            _perf_llm(
                "prompt_format",
                _t_stage,
                extra={
                    "system_len": len(final_system_prompt or ""),
                    "user_len": len(final_user_prompt or ""),
                    "vars": len(variables or []),
                },
            )
        except Exception as e:
            err_msg = f"Error formatting prompt: {e}"
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
            return state

        # Build the message list for the LLM
        messages = []
        if final_system_prompt:
            messages.append(SystemMessage(content=final_system_prompt))
        messages.append(HumanMessage(content=final_user_prompt))

        logger.debug("llm node state messages:", state["messages"])
        if state["messages"]:
            agent_id = state["messages"][0]
            agent = get_agent_by_id(agent_id)
            
            # =================================================================
            # Context Engineering: Build structured context from providers
            # =================================================================
            # Check if context builder is enabled via state attributes
            context_builder_enabled = state.get("attributes", {}).get("context_builder_enabled", False)
            if context_builder_enabled:
                try:
                    _t_stage = _time.perf_counter()
                    from agent.ec_skills.context_utils.context_utils import (
                        ContextBuilder,
                        ContextBuilderConfig,
                    )
                    
                    # Get config from state or use default
                    context_config = state.get("attributes", {}).get("context_builder_config")
                    if context_config and isinstance(context_config, dict):
                        # Convert dict to ContextBuilderConfig
                        builder_config = ContextBuilderConfig(**context_config)
                    elif isinstance(context_config, ContextBuilderConfig):
                        builder_config = context_config
                    else:
                        builder_config = ContextBuilderConfig()
                    
                    # Build structured context
                    context_builder = ContextBuilder(builder_config)
                    structured_context = context_builder.build_context(state)
                    
                    # Store in state for use by hooks and prompts
                    if "attributes" not in state:
                        state["attributes"] = {}
                    state["attributes"]["structured_context"] = structured_context
                    
                    _perf_llm("context_builder", _t_stage, extra={
                        "context_len": len(structured_context or ""),
                        "providers": len(builder_config.enabled_providers),
                    })
                    
                    log_msg = f"📦 ContextBuilder: built {len(structured_context)} chars from {len(builder_config.enabled_providers)} providers"
                    logger.debug(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    
                except Exception as e:
                    err_msg = f"[ContextBuilder] Failed to build context: {e}"
                    logger.warning(err_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("warning", err_msg)
            # =================================================================
            # End Context Engineering
            # =================================================================
            
            _t_stage = _time.perf_counter()
            run_pre_llm_hook(full_node_name, agent, state, prompt_src="local", prompt_data=messages)
            _perf_llm("pre_hook", _t_stage)

            # Adjust context window based on provider limitations
            # Fetch max_tokens from LLM config (gui/config/llm_providers.json)
            from gui.config.llm_config import llm_config
            context_limit = llm_config.get_max_tokens(llm_provider, model_name)
            logger.debug(f"Using max_tokens={context_limit} from config for {llm_provider}/{model_name}")
            
            logger.debug(f"Forming context (limit={context_limit})......")
            _t_stage = _time.perf_counter()
            recent_context = get_recent_context(state.get("history", []), max_tokens=context_limit)
            _perf_llm(
                "build_recent_context",
                _t_stage,
                extra={"context_limit": int(context_limit or 0), "context_msgs": len(recent_context or [])},
            )
            
            # Intelligent system prompt precedence:
            # If the node has explicit prompts configured (prompt_selection or non-default inline),
            # those take higher precedence over what's in history. This ensures tool schemas and
            # other dynamically resolved content are properly sent to the LLM.
            # Otherwise, preserve history system message for continuity.
            node_has_explicit_prompt = bool(prompt_selection) or (
                system_prompt_template and 
                system_prompt_template.strip() != STANDARD_SYS_PROMPT.strip() and
                len(system_prompt_template) > len(STANDARD_SYS_PROMPT)
            )
            
            if node_has_explicit_prompt and final_system_prompt and recent_context:
                # Node has explicit prompt config - use the freshly resolved system prompt
                # (which includes full tool schemas from tools_to_use section)
                if recent_context and isinstance(recent_context[0], SystemMessage):
                    old_len = len(recent_context[0].content)
                    new_len = len(final_system_prompt)
                    logger.debug(f"[LLM] Node has explicit prompt - replacing system message (len={old_len}) with resolved one (len={new_len})")
                    recent_context[0] = SystemMessage(content=final_system_prompt)
                else:
                    # Prepend the new system message if none exists
                    logger.debug(f"[LLM] Node has explicit prompt - prepending system message (len={len(final_system_prompt)})")
                    recent_context.insert(0, SystemMessage(content=final_system_prompt))
            else:
                logger.debug(f"[LLM] No explicit prompt on node - preserving history system message for continuity")

            log_msg = f"recent_context: [{len(recent_context)} messages] {recent_context}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Build LLM from node config (do NOT depend on mainwin.llm)
            llm = None
            try:
                _t_stage = _time.perf_counter()
                # Helper: resolve API key (prefer node config; fallback to settings/secure store)
                def _resolve_api_key(provider: str, provided_key: str | None) -> str | None:
                    def _looks_masked(value: str) -> bool:
                        trimmed = (value or "").strip()
                        if not trimmed:
                            return False
                        if any(ch in trimmed for ch in ("*", "•", "·")):
                            return True
                        sample = "".join(ch for ch in trimmed if ch not in "-_")
                        if not sample:
                            return False
                        mask_chars = {"x", "X"}
                        masked_count = sum(ch in mask_chars for ch in sample)
                        if masked_count >= max(4, int(len(sample) * 0.6)):
                            return True
                        return trimmed.lower().startswith("sk-xxxxx")

                    trimmed_key = (provided_key or "").strip()
                    if trimmed_key and not _looks_masked(trimmed_key):
                        return trimmed_key

                    provider_l = (provider or "").lower()
                    logger.debug(f"provider_l: {provider_l}, {provider}, {provided_key}")
                    try:
                        username = get_current_username()
                    except Exception:
                        username = None

                    logger.debug(f"username: {username}")

                    # Try provider settings (LLM Manager stores full key)
                    resolved_key = None
                    try:
                        from gui.ipc.w2p_handlers.llm_handler import get_llm_manager
                        llm_manager = get_llm_manager()
                        provider_info = llm_manager.get_provider(provider_l)
                        if provider_info:
                            env_vars = provider_info.get("api_key_env_vars", [])
                            for env_var in env_vars:
                                candidate = llm_manager.retrieve_api_key(env_var)
                                if candidate and candidate.strip():
                                    resolved_key = candidate.strip()
                                    break
                    except Exception as settings_err:
                        logger.debug(f"Failed to load API key from provider settings: {settings_err}")

                    if resolved_key:
                        return resolved_key

                    def gs(name: str) -> str | None:
                        try:
                            return secure_store.get(name, username=username)
                        except Exception:
                            return None
                    if provider_l in ("openai",):
                        return gs("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
                    if provider_l in ("anthropic", "claude"):
                        return gs("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
                    if provider_l in ("google", "gemini"):
                        return gs("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
                    if provider_l in ("deepseek",):
                        return gs("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
                    if provider_l in ("dashscope", "qwen", "qwq"):
                        return gs("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
                    if provider_l in ("bytedance", "doubao"):
                        return gs("ARK_API_KEY") or os.getenv("ARK_API_KEY")
                    if provider_l in ("baidu", "qianfan", "baidu_qianfan"):
                        return gs("BAIDU_API_KEY") or os.getenv("BAIDU_API_KEY")
                    if provider_l in ("azure", "azure_openai"):
                        # Azure uses a different key name
                        return gs("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
                    return None

                key = _resolve_api_key(llm_provider, api_key)
                host = (api_host or "").strip()
                prov = llm_provider

                key_preview = "" if not key else f"{key[:4]}..."
                logger.debug(f"real llm settings: api_key={key_preview} host={host} llm_provider={prov}")
                # Provider-specific construction
                if prov in ("azure", "azure_openai"):
                    azure_endpoint = host or (secure_store.get("AZURE_ENDPOINT", username=get_current_username()) if key else None)
                    if not azure_endpoint or not key:
                        raise ValueError("Azure OpenAI requires AZURE_ENDPOINT and API key")
                    llm = AzureChatOpenAI(
                        azure_endpoint=azure_endpoint,
                        api_key=key,
                        azure_deployment=model_name,
                        api_version="2024-02-15-preview",
                        temperature=temperature
                    )
                elif prov in ("openai",):
                    logger.debug("setting up for openai......")
                    kwargs = {"model": model_name, "api_key": key, "temperature": temperature}
                    if host:
                        kwargs["base_url"] = host
                    llm = ChatOpenAI(**kwargs)
                elif prov in ("anthropic", "claude"):
                    if not key:
                        raise ValueError("Anthropic API key missing")
                    llm = ChatAnthropic(model=model_name, api_key=key, temperature=temperature)
                elif prov in ("google", "gemini"):
                    if ChatGoogleGenerativeAI is None:
                        raise ImportError("langchain-google-genai not installed")
                    if not key:
                        raise ValueError("Gemini API key missing")
                    llm = ChatGoogleGenerativeAI(model=model_name or "gemini-pro", google_api_key=key, temperature=temperature)
                elif prov in ("deepseek",):
                    if not key:
                        raise ValueError("DeepSeek API key missing")
                    base_url = host or "https://api.deepseek.com"
                    sync_client, async_client = _create_no_proxy_http_client()
                    llm = ChatDeepSeek(
                        model=model_name or "deepseek-chat",
                        api_key=key,
                        base_url=base_url,
                        temperature=temperature,
                        http_client=sync_client,
                        http_async_client=async_client
                    )
                elif prov in ("dashscope", "qwen", "qwq"):
                    if ChatQwQ is None:
                        raise ImportError("langchain-qwq not installed")
                    if not key:
                        raise ValueError("DashScope (Qwen/QwQ) API key missing")
                    base_url = host or "https://dashscope.aliyuncs.com/compatible-mode/v1"
                    sync_client, async_client = _create_no_proxy_http_client()
                    kw = {
                        "model": model_name or "qwq-plus",
                        "api_key": key,
                        "base_url": base_url,
                        "temperature": temperature
                    }
                    if sync_client:
                        kw["http_client"] = sync_client
                    if async_client:
                        kw["http_async_client"] = async_client
                    llm = ChatQwQ(**kw)
                elif prov in ("bytedance", "doubao"):
                    if not key:
                        raise ValueError("Bytedance (Doubao/ARK) API key missing")
                    base_url = host or "https://ark.cn-beijing.volces.com/api/v3"
                    sync_client, async_client = _create_no_proxy_http_client()
                    kwargs = {
                        "model": model_name or "doubao-pro-256k",
                        "api_key": key,
                        "base_url": base_url,
                        "temperature": temperature
                    }
                    if sync_client:
                        kwargs["http_client"] = sync_client
                    if async_client:
                        kwargs["http_async_client"] = async_client
                    llm = ChatOpenAI(**kwargs)
                elif prov in ("baidu", "qianfan", "baidu_qianfan"):
                    if not key:
                        raise ValueError("Baidu Qianfan API key missing")
                    base_url = host or "https://qianfan.baidubce.com/v2"
                    sync_client, async_client = _create_no_proxy_http_client()
                    kwargs = {
                        "model": model_name or "ernie-4.0-8k",
                        "api_key": key,
                        "base_url": base_url,
                        "temperature": temperature
                    }
                    if sync_client:
                        kwargs["http_client"] = sync_client
                    if async_client:
                        kwargs["http_async_client"] = async_client
                    llm = ChatOpenAI(**kwargs)
                elif prov in ("ollama",):
                    base_url = host or "http://localhost:11434"
                    llm = ChatOllama(model=model_name or "llama3.2", base_url=base_url, temperature=temperature)
                else:
                    # Default to OpenAI-compatible
                    kwargs = {"model": model_name, "api_key": key, "temperature": temperature}
                    if host:
                        kwargs["base_url"] = host
                    llm = ChatOpenAI(**kwargs)

                _perf_llm(
                    "build_llm",
                    _t_stage,
                    extra={
                        "provider": str(llm_provider),
                        "model": str(model_name),
                    },
                )

            except Exception as e:
                err = f"Failed to create LLM from node config (provider={llm_provider}, model={model_name}): {e}"
                logger.error(f"[build_llm_node] {err}")
                web_gui.get_ipc_api().send_skill_editor_log("error", f"[build_llm_node] {err}")
                state['error'] = err
                return state

            # so far we have get API key, LLM model setup among difference possible choices.

            # Log LLM configuration for debugging
            log_msg = f"🔧 LLM Config (node_config): provider={llm_provider}, model={model_name}, temperature={temperature}"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            log_msg = f"📝 Prompt length: system={len(final_system_prompt)}, user={len(final_user_prompt)}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Invoke the LLM and update the state
            try:
                import time
                import threading
                import queue
                import asyncio

                def _invoke_with_thread(llm_to_use, timeout_sec: float):
                    """Sync LLM invocation with thread-based timeout (legacy)."""
                    result_queue = queue.Queue()
                    exception_queue = queue.Queue()

                    def invoke_llm():
                        try:
                            log_msg = "🔄 LLM invocation thread started"
                            logger.debug(log_msg)
                            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

                            logger.debug(f"llm_to_use: {llm_to_use}")
                            result = llm_to_use.invoke(recent_context)
                            result_queue.put(result)

                            log_msg = f"✅ LLM invocation thread completed {result}"
                            logger.debug(log_msg)
                            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                        except Exception as e:
                            err_msg = get_traceback(e, "ErrorInvokeWithThread❌")
                            logger.error(err_msg)
                            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                            exception_queue.put(e)

                    start_time = time.time()
                    th = threading.Thread(target=invoke_llm, daemon=True)
                    th.start()
                    th.join(timeout=timeout_sec)
                    elapsed = time.time() - start_time

                    if th.is_alive():
                        err_msg = f"⏱️ LLM request timed out after {timeout_sec}s (thread still running)"
                        logger.error(err_msg)
                        web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                        raise TimeoutError(err_msg)
                    if not exception_queue.empty():
                        raise exception_queue.get()
                    if result_queue.empty():
                        raise RuntimeError("❌ LLM thread completed but no result available")
                    resp = result_queue.get()
                    log_msg = f"⏱️ Request completed in {elapsed:.2f}s"
                    logger.debug(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    return resp

                async def _invoke_async(llm_to_use, timeout_sec: float):
                    """Async LLM invocation using ainvoke with timeout."""
                    log_msg = "🔄 LLM async invocation started"
                    logger.debug(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    
                    start_time = time.time()
                    try:
                        # Use ainvoke with asyncio timeout
                        result = await asyncio.wait_for(
                            llm_to_use.ainvoke(recent_context),
                            timeout=timeout_sec
                        )
                        elapsed = time.time() - start_time
                        
                        log_msg = f"✅ LLM async invocation completed in {elapsed:.2f}s"
                        logger.debug(log_msg)
                        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                        return result
                        
                    except asyncio.TimeoutError:
                        err_msg = f"⏱️ LLM async request timed out after {timeout_sec}s"
                        logger.error(err_msg)
                        web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                        raise TimeoutError(err_msg)

                def _invoke_hybrid(llm_to_use, timeout_sec: float):
                    """
                    Hybrid LLM invocation: uses async if in event loop, else sync.
                    
                    This allows the same node to work in both sync and async contexts.
                    Controlled by env var ECAN_ASYNC_LLM (default: true).
                    """
                    # Check if async LLM is enabled
                    use_async_llm = os.getenv("ECAN_ASYNC_LLM", "true").lower() in ("1", "true", "yes", "on")
                    
                    if not use_async_llm:
                        logger.debug("[HYBRID_LLM] Async disabled, using sync invocation")
                        return _invoke_with_thread(llm_to_use, timeout_sec)
                    
                    # Check if LLM supports ainvoke
                    if not hasattr(llm_to_use, 'ainvoke'):
                        logger.debug("[HYBRID_LLM] LLM doesn't support ainvoke, using sync")
                        return _invoke_with_thread(llm_to_use, timeout_sec)
                    
                    # Try to detect if we're in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in an async context - use run_coroutine_threadsafe
                        # to avoid blocking the event loop
                        logger.debug("[HYBRID_LLM] Running in async context, using ainvoke")
                        future = asyncio.run_coroutine_threadsafe(
                            _invoke_async(llm_to_use, timeout_sec),
                            loop
                        )
                        return future.result(timeout=timeout_sec + 5)
                    except RuntimeError:
                        # No running event loop - we're in sync context
                        # Try to run async in a new loop (best effort)
                        try:
                            logger.debug("[HYBRID_LLM] No event loop, trying new loop for ainvoke")
                            new_loop = asyncio.new_event_loop()
                            try:
                                return new_loop.run_until_complete(
                                    _invoke_async(llm_to_use, timeout_sec)
                                )
                            finally:
                                new_loop.close()
                        except Exception as e:
                            # Fallback to sync
                            logger.debug(f"[HYBRID_LLM] Async failed ({e}), falling back to sync")
                            return _invoke_with_thread(llm_to_use, timeout_sec)

                # Single attempt (node-configured llm, no fallback)
                # Use hybrid invocation for async/sync compatibility
                _t_stage = _time.perf_counter()
                
                # Resolve timeout with hybrid precedence (runtime > config > default)
                full_node_name = f"{owner}:{skill_name}:{node_name}"
                effective_timeout = resolve_timeout(
                    node_name=full_node_name,
                    state=state,
                    tool_input=None,  # LLM nodes don't have tool_input
                    config_timeout=llm_timeout_seconds,
                    default_timeout=150.0
                )
                
                # Resolve hard timeout mode
                use_hard_timeout = resolve_hard_timeout(
                    node_name=full_node_name,
                    state=state,
                    tool_input=None,
                    config_hard_timeout=hard_timeout_config
                )
                
                # Guardrail timer for long-running LLM calls (soft timeout)
                correlation_id = None
                if enable_guardrail_timer and not use_hard_timeout:
                    try:
                        task = None
                        try:
                            if runtime and hasattr(runtime, 'context'):
                                task = runtime.context.get('task') or runtime.context.get('managed_task')
                        except Exception:
                            pass
                        if task is None:
                            task = state.get('_managed_task')
                        
                        if task:
                            correlation_id = register_async_operation(
                                task=task,
                                source_node=f"llm:{full_node_name}",
                                timeout_seconds=effective_timeout
                            )
                            log_msg = f"[LLM_GUARDRAIL] Started timer {correlation_id} ({effective_timeout}s)"
                            logger.info(log_msg)
                            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    except Exception as e:
                        logger.warning(f"[LLM_GUARDRAIL] Failed to start timer: {e}")
                
                # Execute LLM call with optional hard timeout
                if use_hard_timeout:
                    import asyncio
                    log_msg = f"[LLM_HARD_TIMEOUT] Using hard timeout ({effective_timeout}s) - will cancel on timeout"
                    logger.info(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    try:
                        # Hard timeout: cancel operation if it exceeds timeout
                        async def _invoke_with_hard_timeout():
                            return await asyncio.wait_for(
                                _invoke_async(llm, effective_timeout),
                                timeout=effective_timeout
                            )
                        
                        # Run in event loop (sync context)
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Use run_async_in_sync for nested event loop
                                response = run_async_in_sync(_invoke_with_hard_timeout())
                            else:
                                response = loop.run_until_complete(_invoke_with_hard_timeout())
                        except RuntimeError:
                            new_loop = asyncio.new_event_loop()
                            try:
                                response = new_loop.run_until_complete(_invoke_with_hard_timeout())
                            finally:
                                new_loop.close()
                    except asyncio.TimeoutError:
                        error_msg = f"LLM call timed out after {effective_timeout}s (hard timeout)"
                        logger.error(f"[LLM_HARD_TIMEOUT] {error_msg}")
                        web_gui.get_ipc_api().send_skill_editor_log("error", error_msg)
                        # Record failure if task available
                        try:
                            task = state.get('_managed_task')
                            if task is None and runtime and hasattr(runtime, 'context'):
                                task = runtime.context.get('task') or runtime.context.get('managed_task')
                            if task and hasattr(task, 'record_failure'):
                                task.record_failure()
                        except Exception:
                            pass
                        raise TimeoutError(error_msg)
                else:
                    response = _invoke_hybrid(llm, effective_timeout)
                
                # Cancel guardrail timer on success
                if correlation_id:
                    try:
                        task = state.get('_managed_task')
                        if task is None and runtime and hasattr(runtime, 'context'):
                            task = runtime.context.get('task') or runtime.context.get('managed_task')
                        if task:
                            resolve_async_operation(task, correlation_id, result={"status": "completed"})
                            log_msg = f"[LLM_GUARDRAIL] Cancelled timer {correlation_id} (LLM completed)"
                            logger.info(log_msg)
                    except Exception as e:
                        logger.warning(f"[LLM_GUARDRAIL] Failed to cancel timer: {e}")
                
                _perf_llm("invoke", _t_stage)

                log_msg = f"✅ LLM response received from {llm_provider}"
                logger.info(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

                # It's good practice to put results in specific keys
                _t_stage = _time.perf_counter()
                run_post_llm_hook(full_node_name, agent, state, response)
                _perf_llm("post_hook", _t_stage)
                logger.debug(f"llm_node finished..... {state}")

                # Total time for llm_node_callable (best-effort)
                _perf_llm("total", _t0)

            except Exception as e:
                error_type = type(e).__name__
                error_str = get_traceback(e, "ErrorLLMNodeCallable")

                # Detect specific error types and provide helpful messages
                if "AuthenticationError" in error_type or "authentication" in error_str.lower():
                    err_msg = (f"❌ LLM Authentication Failed: Invalid API key for {llm_provider}. "
                                     "Please check your API key configuration.")
                    logger.error(f"{err_msg} | Original error: {error_str}")
                    web_gui.get_ipc_api().send_skill_editor_log("error", f"{err_msg} | Original error: {error_str}")
                elif "RateLimitError" in error_type or "rate limit" in error_str.lower() or "quota" in error_str.lower():
                    err_msg = (f"❌ LLM Rate Limit Exceeded: {llm_provider} quota exhausted or rate limit reached. "
                                     "Please check your usage limits.")
                    logger.error(f"{err_msg} | Original error: {error_str}")
                    web_gui.get_ipc_api().send_skill_editor_log("error", f"{err_msg} | Original error: {error_str}")
                elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                    err_msg = (f"⏱️ LLM Request Timeout: Connection to {llm_provider} timed out. "
                                     "This may be due to network issues or API endpoint unreachable.")
                    logger.error(f"{err_msg} | Original error: {error_str}")
                    web_gui.get_ipc_api().send_skill_editor_log("error", f"{err_msg} | Original error: {error_str}")
                elif "connection" in error_str.lower() or "network" in error_str.lower():
                    err_msg = (f"🌐 LLM Connection Error: Cannot connect to {llm_provider} API. "
                                     "Please check your network connection and API endpoint configuration.")
                    logger.error(f"{err_msg} | Original error: {error_str}")
                    web_gui.get_ipc_api().send_skill_editor_log("error", f"{err_msg} | Original error: {error_str}")
                elif "InvalidRequestError" in error_type or "invalid" in error_str.lower() or "model" in error_str.lower():
                    err_msg = (f"⚠️ LLM Invalid Request: The request to {llm_provider} was invalid. "
                                     f"Model: '{model_name}'. Error: {error_str}")
                    logger.error(f"{err_msg}")
                    web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                    # Check if it's a model not found error
                    if "model" in error_str.lower() and ("not found" in error_str.lower() or "does not exist" in error_str.lower()):
                        err_msg = f"💡 Hint: Model '{model_name}' does not exist. Common OpenAI models: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo"
                        logger.error(err_msg)
                        web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                else:
                    # Generic error with full details
                    err_msg = f"❌ LLM Invocation Failed  for {llm_provider}/{model_name}: ({error_type}): {error_str}"
                    logger.error(err_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                state['error'] = err_msg

                # Add detailed error info for debugging
                state['error_details'] = {
                    'error_type': error_type,
                    'provider': llm_provider,
                    'model': model_name,
                    'original_error': error_str
                }
        else:
            logger.error("ERROR LLM NODE: messages empty ")
        return state

    full_node_callable = node_builder(llm_node_callable, node_name, skill_name, owner, bp_manager)

    return full_node_callable


def build_basic_node(config_metadata: dict, node_id: str, skill_name: str, owner: str, bp_manager) -> callable:
    """
    Builds a basic node from a code source, which can be either a file path or an inline string.
    This function is responsible for dynamically loading or executing the code and returning
    a callable that can be used as a node in the graph.
    """
    log_msg = f"building basic node: {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    # Safely extract inline script content; tolerate missing keys and fall back to no-op
    try:
        code_source = (config_metadata or {}).get('script', {}).get('content')
    except Exception:
        code_source = None

    log_msg = f"code_source: {code_source}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    if not code_source or not isinstance(code_source, str):
        err_msg = "Error: 'code' key is missing or invalid in config_metadata for basic_node."
        logger.error(err_msg)
        web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
        # Return a no-op function that just passes the state through
        return lambda state: state

    node_callable = None
    node_name = node_id

    # Scenario 1: Code is a file path
    if False and (code_source.endswith('.py') and os.path.exists(code_source)):
        try:
            # Use a unique module name to avoid conflicts
            module_name = f"dynamic_basic_node_{os.path.basename(code_source)[:-3]}"
            spec = importlib.util.spec_from_file_location(module_name, code_source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Convention: the file must have a 'run' function
            if hasattr(module, 'run'):
                node_callable = getattr(module, 'run')
            else:
                log_msg = f"Basic node file {code_source} is missing a 'run(state)' function."
                logger.warning(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, f"ErrorBuildBasicNode {code_source}")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)

    # Scenario 2: Code is an inline script
    else:
        try:
            # Define a scope for the exec to run in, so imports are captured
            local_scope = {}
            exec(code_source, local_scope, local_scope)

            # Find the 'main' function within the executed code's scope
            main_func = local_scope.get('main')
            if callable(main_func):
                node_callable = main_func
                log_msg = "Callable obtained from inline basic node code"
                logger.debug(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
            else:
                log_msg = "No function definition found in inline code for basic node."
                logger.warning(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, "ErrorExecutingInlineCodeForBasicNode")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            node_callable = None

    # If callable creation failed, return a no-op function
    if node_callable is None:
        return lambda state: state

    log_msg = f"done building basic node {node_name}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
    full_node_callable = node_builder(node_callable, node_name, skill_name, owner, bp_manager)

    return full_node_callable


def build_api_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    """
    Builds a callable function for a node that makes an API call.

    Args:
        config_metadata: A dictionary containing the API call configuration:
                         - api_endpoint: URL for the request.
                         - method: HTTP method (GET, POST, etc.).
                         - headers: Request headers.
                         - params: Request parameters (for query string or body).
                         - sync: Boolean indicating if the call is synchronous.

    Returns:
        A sync or async callable function that takes a state dictionary.
    """
    # Extract configuration (support legacy `{http: {...}}` and new flowgram schema)
    log_msg = f"building api node... {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
    cfg_http = config_metadata.get("http") if isinstance(config_metadata, dict) else None
    if isinstance(cfg_http, dict):
        api_endpoint = cfg_http.get('apiUrl') or cfg_http.get('url') or ""
        method = (cfg_http.get('apiMethod') or cfg_http.get('method') or "GET").upper()
        timeout = int(cfg_http.get('timeout', 30))
        retries = int(cfg_http.get('retry', 3))
        headers_template = cfg_http.get('requestHeadersValues', {'Content-Type': {'type': 'constant', 'content': 'application/json'}})
        params_template = cfg_http.get('requestParams', {})
        api_key = cfg_http.get('apiKey', "")
        attachments = cfg_http.get('attachments', [])
    else:
        api = (config_metadata.get('api') or {}) if isinstance(config_metadata, dict) else {}
        url_field = api.get('url')
        if isinstance(url_field, dict):
            api_endpoint = url_field.get('content') or ""
        else:
            api_endpoint = str(url_field or "")
        method = (api.get('method') or "GET").upper()
        to = (config_metadata.get('timeout') or {}) if isinstance(config_metadata, dict) else {}
        # incoming timeout in ms; convert to seconds, fallback 10s
        timeout = int(max(1, int((to.get('timeout') or 10000) / 1000)))
        retries = int((to.get('retryTimes') or 1))
        headers_template = (config_metadata.get('headers') or {})
        params_template = (config_metadata.get('params') or {})
        body_cfg = (config_metadata.get('body') or {})
        attachments = body_cfg.get('attachments', []) if isinstance(body_cfg, dict) else []
        api_key = (config_metadata.get('apiKey') or "")

    is_sync = bool((config_metadata or {}).get('sync', True))

    if not api_endpoint:
        err_msg = "'api_endpoint' is missing in config_metadata for api_node."
        logger.error(err_msg)
        web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
        return lambda state, runtime=None, store=None, **kwargs: {**state, 'error': 'API endpoint not configured'}

    def _format_from_state(template, attributes):
        """Recursively format strings in a template dict/list with state attributes."""
        if isinstance(template, str):
            return template.format(**attributes)
        if isinstance(template, dict):
            out = {}
            for k, v in template.items():
                if isinstance(v, dict):
                    # Prefer 'content' if present
                    val = v.get('content', None)
                    if val is None:
                        # If no 'content', try formatting the entire dict recursively
                        val = _format_from_state(v, attributes)
                    out[k] = val
                else:
                    out[k] = _format_from_state(v, attributes)
            return out
        if isinstance(template, list):
            return [_format_from_state(i, attributes) for i in template]
        return template

    def _flatten_kv(template):
        """Recursively flatten {key: {type, content}} -> {key: formatted_content}"""
        out = {}
        if not isinstance(template, dict):
            return out
        for k, v in template.items():
            if isinstance(v, dict):
                # Prefer 'content' if present
                content = v.get('content')
                if content is None:
                    # If no 'content', try formatting the entire dict recursively
                    content = _format_from_state(v, {})
                if isinstance(content, str):
                    try:
                        content = content.format(**{})
                    except Exception:
                        pass
                out[k] = content
            elif isinstance(v, str):
                try:
                    out[k] = v.format(**{})
                except Exception:
                    out[k] = v
            else:
                out[k] = v
        return out

    def _prepare_request_args(state):
        """Prepare final request arguments by formatting templates with state.

        - headers_template follows requestHeadersValues shape: {name: {type, content, ...}}
        - params_template may be {values: {name: {type, content}}} or a flat dict.
        """
        attributes = state.get("attributes", {})
        try:
            final_url = (api_endpoint or "").format(**attributes)
        except Exception:
            final_url = api_endpoint or ""

        # Helper to flatten {key: {type, content}} -> {key: formatted_content}
        def _flatten_kv(template):
            out = {}
            if not isinstance(template, dict):
                return out
            for k, v in template.items():
                if isinstance(v, dict):
                    # Prefer 'content' if present
                    content = v.get('content')
                    if content is None:
                        # If no 'content', try formatting the entire dict recursively
                        content = _format_from_state(v, attributes)
                    out[k] = content
                elif isinstance(v, str):
                    try:
                        out[k] = v.format(**attributes)
                    except Exception:
                        out[k] = v
                else:
                    out[k] = v
            return out

        # Build headers from requestHeadersValues
        final_headers = {}
        if isinstance(headers_template, dict):
            final_headers.update(_flatten_kv(headers_template))

        # Build params from requestParams (support both flat and values-schema form)
        if isinstance(params_template, dict):
            values = params_template.get('values') if 'values' in params_template else params_template
            final_params = _flatten_kv(values if isinstance(values, dict) else {})
        else:
            final_params = {}

        logger.debug(f"final_params: {final_params}")
        # Convenience: if GET/DELETE and no explicit params provided, promote non-standard headers to query params
        # This supports simple GUI inputs where users add foo1/bar1 in headers area.
        if method in ['GET', 'DELETE'] and not final_params and isinstance(headers_template, dict):
            common_headers = {
                'content-type','authorization','accept','user-agent','cache-control','connection','pragma',
                'referer','origin','host','accept-encoding','accept-language'
            }
            promoted = {}
            for k, v in headers_template.items():
                key_l = k.lower()
                if key_l in common_headers:
                    continue
                if isinstance(v, dict):
                    content = v.get('content')
                    if content is None:
                        continue
                    if isinstance(content, str):
                        try:
                            content = content.format(**attributes)
                        except Exception:
                            pass
                    promoted[k] = content
                elif isinstance(v, str):
                    promoted[k] = v
            if promoted:
                final_params.update(promoted)

        # Always merge primitive attributes into params/body (explicit params override attributes)
        if isinstance(attributes, dict):
            reserved_keys = {"__this_node__"}
            attr_params = {}
            for k, v in attributes.items():
                if k in reserved_keys:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    attr_params[k] = v
            if attr_params:
                # attributes first, then explicit params so explicit wins on key conflicts
                final_params = {**attr_params, **final_params}

        # Merge any query string already present in apiUrl with final_params
        request_args = {'method': method, 'headers': final_headers}
        if method in ['GET', 'DELETE']:
            try:
                parsed = urlparse(final_url)
                existing_qs = dict(parse_qsl(parsed.query))
                # final_params take precedence
                merged_params = {**existing_qs, **final_params}
                # rebuild URL without query; pass params separately
                cleaned_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, '', parsed.fragment))
                request_args['url'] = cleaned_url
                request_args['params'] = merged_params
            except Exception:
                request_args['url'] = final_url
                request_args['params'] = final_params
        else: # POST, PUT, PATCH
            request_args['url'] = final_url
            request_args['json'] = final_params
        
        # Inject API key if configured
        try:
            if api_key:
                # Case 1: simple string -> default to Authorization: Bearer <token>
                if isinstance(api_key, str):
                    token = api_key.format(**attributes)
                    request_args['headers'] = request_args.get('headers', {})
                    # Do not overwrite if already provided
                    request_args['headers'].setdefault('Authorization', f"Bearer {token}")
                # Case 2: dict configuration
                elif isinstance(api_key, dict):
                    # Support nested style: {'header': {...}} or {'query': {...}}
                    if 'header' in api_key or 'query' in api_key:
                        for place in ['header', 'query']:
                            if place in api_key and isinstance(api_key[place], dict):
                                spec = api_key[place]
                                name = spec.get('name', 'Authorization' if place == 'header' else 'api_key')
                                value = spec.get('value')
                                if value is None and spec.get('env_var'):
                                    value = os.getenv(spec.get('env_var'), '')
                                if isinstance(value, str):
                                    value = value.format(**attributes)
                                prefix = spec.get('prefix', '')
                                full_value = f"{prefix}{value}" if prefix else value
                                if place == 'header':
                                    request_args['headers'] = request_args.get('headers', {})
                                    request_args['headers'][name] = full_value
                                else:  # query
                                    if method in ['GET', 'DELETE']:
                                        params = request_args.get('params') or {}
                                        if not isinstance(params, dict):
                                            params = {}
                                        params[name] = full_value
                                        request_args['params'] = params
                                    else:
                                        body = request_args.get('json') or {}
                                        if not isinstance(body, dict):
                                            body = {}
                                        body[name] = full_value
                                        request_args['json'] = body
                    else:
                        # Flat dict: {'in': 'header'|'query', 'name': 'Authorization', 'value': '...', 'env_var': '...', 'prefix': 'Bearer '}
                        place = api_key.get('in', 'header')
                        name = api_key.get('name', 'Authorization' if place == 'header' else 'api_key')
                        value = api_key.get('value')
                        if value is None and api_key.get('env_var'):
                            value = os.getenv(api_key.get('env_var'), '')
                        if isinstance(value, str):
                            value = value.format(**attributes)
                        prefix = api_key.get('prefix', '')
                        full_value = f"{prefix}{value}" if prefix else value
                        if place == 'header':
                            request_args['headers'] = request_args.get('headers', {})
                            request_args['headers'][name] = full_value
                        else:
                            if method in ['GET', 'DELETE']:
                                params = request_args.get('params') or {}
                                if not isinstance(params, dict):
                                    params = {}
                                params[name] = full_value
                                request_args['params'] = params
                            else:
                                body = request_args.get('json') or {}
                                if not isinstance(body, dict):
                                    body = {}
                                body[name] = full_value
                                request_args['json'] = body
        except Exception as e:
            err_msg = get_traceback(e, "ErrorPrepareRequestArgs build_api_node api_key injection skipped")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)

        # Handle file attachments for multipart/form-data
        opened_files = []
        try:
            files_arg = []
            if attachments:
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    field = att.get('field', 'file')
                    path_tmpl = att.get('path') or att.get('filepath')
                    if not path_tmpl:
                        continue
                    # Format path with attributes if templated
                    path = path_tmpl.format(**attributes)
                    filename = att.get('filename') or os.path.basename(path)
                    content_type = att.get('content_type', 'application/octet-stream')
                    f = open(path, 'rb')
                    opened_files.append(f)
                    files_arg.append((field, (filename, f, content_type)))

            if files_arg:
                request_args['files'] = files_arg
                # When sending files, use form fields for params instead of JSON body
                if 'json' in request_args:
                    body = request_args.pop('json')
                    request_args['data'] = body
        except Exception as e:
            # If attachments setup fails, close any opened files and continue without files
            err_msg = get_traceback(e, "ErrorPrepareRequestArgs build_api_node attachments setup")
            logger.debug(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)

            for fh in opened_files:
                try:
                    fh.close()
                except Exception:
                    pass
            opened_files = []

        return request_args, opened_files

    # Define the synchronous version of the callable
    def sync_api_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        logger.info(f"Executing sync API node for endpoint: {api_endpoint}, current state is: {state}")
        request_args, file_handles = _prepare_request_args(state)
        logger.debug(f"prepared request args: {request_args}")

        try:
            # Configure timeout for proxy compatibility (especially Clash)
            # Increased read timeout to handle slow proxy responses
            timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)
            with httpx.Client(timeout=timeout) as client:
                # follow redirects to avoid 302 on some endpoints
                response = client.request(**request_args, follow_redirects=True)
                logger.debug(f"HTTP API response received: {response}")
                response.raise_for_status() # Raise an exception for bad status codes
                # Prefer JSON; fall back to text for non-JSON endpoints
                payload = None
                ct = (response.headers.get('content-type') or '').lower()
                if 'application/json' in ct:
                    payload = response.json()
                else:
                    try:
                        payload = response.json()
                    except Exception:
                        payload = response.text
                state.setdefault('results', []).append({
                    'status': response.status_code,
                    'url': str(response.url),
                    'headers': dict(response.headers),
                    'body': payload,
                })
                log_msg = f"received response payload: {payload}"
                logger.debug(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
        except httpx.HTTPStatusError as e:
            err_msg = f"API call failed with status {e.response.status_code}: {e.response.text}"
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
        except Exception as e:
            err_msg = get_traceback(e, "ErrorSyncAPICallable")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

            add_to_history(state, ActionMessage(content=f"action: api call to {api_endpoint}; result: {response}"))
        return state

    # Define the asynchronous version of the callable
    async def async_api_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        logger.info(f"Executing async API node for endpoint: {api_endpoint}")
        request_args, file_handles = _prepare_request_args(state)
        try:
            # Configure timeout for proxy compatibility (especially Clash)
            # Increased read timeout to handle slow proxy responses
            timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(**request_args)
                response.raise_for_status()
                state.setdefault('results', []).append(response.json())
        except httpx.HTTPStatusError as e:
            err_msg = f"API call failed with status {e.response.status_code}: {e.response.text}"
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
        except Exception as e:
            err_msg = get_traceback(e, "ErrorASyncAPICallable")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

            add_to_history(state, ActionMessage(content=f"action: api call to {api_endpoint}; result: {response}"))

        return state

    # return sync_api_callable if is_sync else async_api_callable

    # Return the correct function based on the 'sync' flag
    full_node_callable = node_builder(sync_api_callable, node_name, skill_name, owner, bp_manager)

    return full_node_callable




# pre-requisite: tool_name is in config_metadata, tool_input is in state and conform the tool input schema (strictly, it will be type checked)
def build_mcp_tool_calling_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """
    Builds a callable function for a node that calls an MCP tool.

    Args:
        config_metadata: A dictionary containing the tool configuration:
                         - tool_name: The name of the MCP tool to call.
                         - async_mode: If True, use fire-and-forget pattern with pending events.
                         - async_timeout: Timeout in seconds for async operations (default 60).

    Returns:
        A callable function that takes a state dictionary.
    """
    # Accept multiple shapes from GUI/legacy formats
    log_msg = f"building mcp tool node: {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    tool_name = None
    use_llm_auto_select = False
    
    # Async mode configuration for fire-and-forget pattern
    async_mode = False
    async_timeout = 60.0
    try:
        async_mode = (config_metadata.get('async_mode')
                      or ((config_metadata.get('inputsValues') or {}).get('async_mode') or {}).get('content')
                      or (config_metadata.get('inputs') or {}).get('async_mode'))
        async_mode = str(async_mode).lower() in ('true', '1', 'yes', 'on') if async_mode else False
        
        async_timeout_val = (config_metadata.get('async_timeout')
                             or ((config_metadata.get('inputsValues') or {}).get('async_timeout') or {}).get('content')
                             or (config_metadata.get('inputs') or {}).get('async_timeout'))
        if async_timeout_val:
            async_timeout = float(async_timeout_val)
    except Exception:
        pass
    
    try:
        tool_name = (config_metadata.get('tool_name')
                     or config_metadata.get('toolName')
                     or ((config_metadata.get('inputsValues') or {}).get('tool_name') or {}).get('content')
                     or ((config_metadata.get('inputsValues') or {}).get('toolName') or {}).get('content')
                     or (config_metadata.get('inputs') or {}).get('tool_name')
                     or (config_metadata.get('inputs') or {}).get('toolName'))
        
        # Also check callable.id or callable.name for "llm-auto-select"
        callable_info = config_metadata.get('callable') or {}
        callable_id = callable_info.get('id', '') if isinstance(callable_info, dict) else ''
        callable_name = callable_info.get('name', '') if isinstance(callable_info, dict) else ''

    except Exception:
        tool_name = None
        callable_id = ''
        callable_name = ''

    # Check if "llm auto select" mode is enabled
    if (not tool_name 
        or tool_name in ('llm-auto-select', 'llm auto select')
        or callable_id in ('llm-auto-select',)
        or callable_name in ('llm auto select',)):
        use_llm_auto_select = True
        log_msg = f"[MCP] Node '{node_name}' using LLM auto-select mode - tool will be determined at runtime from state['result']['llm_result']"
        logger.info(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("info", log_msg)

    # --- MCP tool input helpers (schema-aware) ---

    def _get_tool_schema_by_name(tool_name: str):
        try:
            mainwin = AppContext.get_main_window()
            schemas = getattr(mainwin, 'mcp_tools_schemas', None)
            if not schemas:
                return None
            for s in schemas:
                try:
                    s_name = getattr(s, 'name', None) or (s.get('name') if isinstance(s, dict) else None)
                    if s_name == tool_name:
                        # normalize to a dict
                        return s if isinstance(s, dict) else {
                            'name': s.name,
                            'description': getattr(s, 'description', ''),
                            'inputSchema': getattr(s, 'inputSchema', {})
                        }
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def _normalize_schema_root(schema: dict) -> dict:
        if not isinstance(schema, dict):
            return {}
        return schema.get('inputSchema') if 'inputSchema' in schema else schema

    def _empty_for_type(t):
        try:
            if not t:
                return ''
            t = str(t).lower()
            if t == 'string':
                return ''
            if t in ('integer', 'number'):
                return 0
            if t == 'float':
                return 0.0
            if t == 'boolean':
                return False
            if t.startswith('['):  # e.g. "[string]" in some of our schemas
                return []
            if t == 'object':
                if t in ('object', 'dict'):
                    return {}
                if t in ('array',) or t.startswith('['):
                    return []
            return ''
        except Exception:
            return ''

    # Tool-specific default values for required fields
    TOOL_FIELD_DEFAULTS = {
        'gmail_read_titles': {'recent': 72},
        'gmail_read_full_email': {'recent': 72},
    }

    def _coerce_value_to_type(val, expected_type: str, tool_name: str = None, field_name: str = None):
        """
        Coerce a value to match the expected schema type.
        Falls back to tool-specific defaults or type-based defaults.
        """
        try:
            if expected_type is None:
                return val
            
            expected_type = str(expected_type).lower()
            
            # Check for tool-specific defaults first
            if tool_name and field_name:
                tool_defaults = TOOL_FIELD_DEFAULTS.get(tool_name, {})
                default_val = tool_defaults.get(field_name)
            else:
                default_val = None
            
            # Handle integer type
            if expected_type == 'integer':
                if val is None or val == '':
                    return default_val if default_val is not None else 0
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return default_val if default_val is not None else 0
            
            # Handle number type (float)
            if expected_type in ('number', 'float'):
                if val is None or val == '':
                    return default_val if default_val is not None else 0.0
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default_val if default_val is not None else 0.0
            
            # Handle boolean type
            if expected_type == 'boolean':
                if val is None or val == '':
                    return default_val if default_val is not None else False
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.lower() in ('true', '1', 'yes')
                return bool(val)
            
            # Handle string type
            if expected_type == 'string':
                if val is None:
                    return default_val if default_val is not None else ''
                return str(val)
            
            # Handle object type
            if expected_type in ('object', 'dict'):
                if val is None or val == '':
                    return default_val if default_val is not None else {}
                if isinstance(val, dict):
                    return val
                if isinstance(val, str):
                    try:
                        import json
                        return json.loads(val)
                    except:
                        return {}
                return {}
            
            # Handle array type
            if expected_type in ('array',) or expected_type.startswith('['):
                if val is None or val == '':
                    return default_val if default_val is not None else []
                if isinstance(val, list):
                    return val
                return []
            
            return val
        except Exception:
            return val

    def _gather_config_value(cfg: dict, key: str):
        # Read from config_metadata across several shapes:
        if not isinstance(cfg, dict):
            return None
        try:
            # 1) flat
            if key in cfg:
                return cfg.get(key)

            # 2) inputsValues.<key>.content
            inputs_values = cfg.get('inputsValues')
            if isinstance(inputs_values, dict) and key in inputs_values:
                v = inputs_values.get(key)
                if isinstance(v, dict) and 'content' in v:
                    return v.get('content')
                return v

            # 3) inputs.<key>
            inputs = cfg.get('inputs')
            if isinstance(inputs, dict) and key in inputs:
                return inputs.get(key)
        except Exception:
            return None
        return None

    def _validate_tool_input_against_schema(inp: dict, root: dict) -> bool:
        # Minimal structural validation to ensure required keys are present
        try:
            if not isinstance(root, dict):
                return True
            required_root = root.get('required') or []
            if not isinstance(inp, dict):
                return False if required_root else True

            # root-level required fields
            for k in required_root:
                if k not in inp:
                    return False

            # nested input object
            props = root.get('properties') or {}
            input_prop = props.get('input') if isinstance(props, dict) else None
            if 'input' in required_root and isinstance(input_prop, dict):
                input_required = input_prop.get('required') or []
                input_obj = inp.get('input', {}) if isinstance(inp.get('input'), dict) else {}
                for k in input_required:
                    if k not in input_obj:
                        return False
            return True
        except Exception:
            return False

    def _build_input_from_config(config_metadata: dict, root: dict) -> dict:
        # Build a correct-shaped input dict; fill missing with type-based empty defaults
        # Also coerce values to match expected schema types
        result = {}
        try:
            if not isinstance(root, dict):
                return result
            required_root = root.get('required') or []
            props = root.get('properties') or {}

            # Handle nested 'input' object
            if 'input' in required_root and isinstance(props, dict):
                input_spec = props.get('input') if isinstance(props.get('input'), dict) else None
                input_obj = {}
                if isinstance(input_spec, dict):
                    input_required = input_spec.get('required') or []
                    input_props = input_spec.get('properties') or {}
                    for rk in input_required:
                        val = _gather_config_value(config_metadata, rk)
                        t = (input_props.get(rk) or {}).get('type') if isinstance(input_props, dict) else None
                        # Always coerce value to expected type (handles empty strings, None, wrong types)
                        val = _coerce_value_to_type(val, t, tool_name, rk)
                        input_obj[rk] = val
                result['input'] = input_obj

            # Handle other root-level required keys
            for rk in required_root:
                if rk == 'input':
                    continue
                if rk not in result:
                    val = _gather_config_value(config_metadata, rk)
                    t = ((props.get(rk) or {}).get('type') if isinstance(props, dict) else None)
                    # Always coerce value to expected type
                    val = _coerce_value_to_type(val, t, tool_name, rk)
                    result[rk] = val
        except Exception:
            pass
        return result

    def _merge_inputs(runtime_input: dict, compiled_input: dict) -> dict:
        # Prefer runtime-provided, fill missing from compiled
        out = compiled_input.copy() if isinstance(compiled_input, dict) else {}
        if isinstance(runtime_input, dict):
            for k, v in runtime_input.items():
                if k == 'input' and isinstance(v, dict):
                    out.setdefault('input', {})
                    for ik, iv in v.items():
                        out['input'][ik] = iv
                else:
                    out[k] = v
        return out

    def _coerce_all_inputs(inp: dict, root: dict) -> dict:
        """
        Coerce all values in the input dict to match schema types.
        This is a final pass to ensure type correctness after merging.
        """
        try:
            if not isinstance(inp, dict) or not isinstance(root, dict):
                return inp
            
            props = root.get('properties') or {}
            
            # Handle nested 'input' object
            if 'input' in inp and isinstance(inp['input'], dict):
                input_spec = props.get('input') if isinstance(props, dict) else None
                if isinstance(input_spec, dict):
                    input_props = input_spec.get('properties') or {}
                    for field_name, field_val in inp['input'].items():
                        field_spec = input_props.get(field_name) or {}
                        expected_type = field_spec.get('type')
                        if expected_type:
                            inp['input'][field_name] = _coerce_value_to_type(
                                field_val, expected_type, tool_name, field_name
                            )
            
            return inp
        except Exception:
            return inp

    def mcp_tool_callable(state: dict, runtime=None, store=None, **kwargs) -> dict:
        # Determine actual tool name and input at runtime
        actual_tool_name = tool_name
        actual_tool_input = state.get('tool_input', {})
        
        # --- LLM Auto-Select Mode ---
        if use_llm_auto_select:
            log_msg = f"🤖 Executing MCP node '{node_name}' in LLM auto-select mode"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
            
            # Extract LLM result from state
            llm_result = (state.get('result') or {}).get('llm_result') or {}
            
            # Handle case where LLM response is wrapped in 'message' field (multi-line JSON parsing fallback)
            # Try to extract the JSON object containing next_tool_name
            if 'message' in llm_result and isinstance(llm_result.get('message'), str):
                message_content = llm_result['message']
                logger.debug(f"[MCP Auto-Select] Found 'message' wrapper, attempting to parse: {message_content[:300]}...")
                
                # Parse all complete JSON objects from the message and find the one with next_tool_name
                parsed_objects = []
                idx = 0
                while idx < len(message_content):
                    # Find next '{'
                    start_idx = message_content.find('{', idx)
                    if start_idx < 0:
                        break
                    
                    # Find matching closing brace using depth tracking
                    depth = 0
                    end_idx = -1
                    for i, c in enumerate(message_content[start_idx:]):
                        if c == '{':
                            depth += 1
                        elif c == '}':
                            depth -= 1
                            if depth == 0:
                                end_idx = start_idx + i
                                break
                    
                    if end_idx > start_idx:
                        json_str = message_content[start_idx:end_idx + 1]
                        try:
                            parsed = json.loads(json_str)
                            parsed_objects.append(parsed)
                            logger.debug(f"[MCP Auto-Select] Parsed JSON object: {list(parsed.keys())}")
                        except json.JSONDecodeError as e:
                            logger.debug(f"[MCP Auto-Select] Skipping invalid JSON: {e}")
                        idx = end_idx + 1
                    else:
                        idx = start_idx + 1
                
                # Find the object with next_tool_name
                for obj in parsed_objects:
                    if isinstance(obj, dict) and 'next_tool_name' in obj:
                        llm_result = obj
                        logger.debug(f"[MCP Auto-Select] Found target JSON with next_tool_name: {obj}")
                        # Update state so loop condition can properly check work_done
                        if 'result' in state and isinstance(state['result'], dict):
                            state['result']['llm_result'] = obj
                            logger.debug(f"[MCP Auto-Select] Updated state['result']['llm_result'] with parsed object")
                        break
            
            work_done = llm_result.get('work_done', False)
            next_tool_name = llm_result.get('next_tool_name', '')
            next_tool_input = llm_result.get('next_tool_input', {})
            
            log_msg = f"[MCP Auto-Select] work_done={work_done}, next_tool_name='{next_tool_name}', next_tool_input={next_tool_input}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
            
            # Check if work is done - skip tool call
            if work_done:
                log_msg = f"[MCP Auto-Select] work_done=True, skipping tool call for node '{node_name}'"
                logger.info(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("info", log_msg)
                return state
            
            # Check if next_tool_name is empty or not provided
            if not next_tool_name or not isinstance(next_tool_name, str) or not next_tool_name.strip():
                # Check if this is an invalid LLM response format
                # The LLM should return: {"work_done": bool, "next_tool_name": str, "next_tool_input": dict}
                # But sometimes it returns just {"input": {...}} or {"message": ""}
                
                # Case 1: Empty message wrapper
                if 'message' in llm_result and not llm_result.get('message', '').strip():
                    log_msg = f"[MCP Auto-Select] WARNING: LLM returned empty message with no next_tool_name. Setting work_done=True to exit loop gracefully."
                    logger.warning(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)
                # Case 2: LLM returned just the input schema without required fields
                elif 'input' in llm_result and 'next_tool_name' not in llm_result:
                    log_msg = f"[MCP Auto-Select] WARNING: LLM returned invalid format (just 'input' without 'next_tool_name'). Expected format: {{work_done, next_tool_name, next_tool_input}}. Got: {list(llm_result.keys())}. Setting work_done=True."
                    logger.warning(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)
                else:
                    log_msg = f"[MCP Auto-Select] next_tool_name is empty or not provided. LLM result keys: {list(llm_result.keys())}. Skipping tool call for node '{node_name}'"
                    logger.info(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("info", log_msg)
                
                # Set work_done to True so the loop condition exits gracefully
                if 'result' in state and isinstance(state['result'], dict):
                    if 'llm_result' not in state['result']:
                        state['result']['llm_result'] = {}
                    state['result']['llm_result']['work_done'] = True
                return state
            
            actual_tool_name = next_tool_name.strip()
            
            # Validate tool name against MCP tool registry
            tool_schema = _get_tool_schema_by_name(actual_tool_name)
            if not tool_schema:
                log_msg = f"[MCP Auto-Select] Tool '{actual_tool_name}' not found in MCP tool registry, skipping tool call for node '{node_name}'"
                logger.warning(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)
                return state
            
            # Use next_tool_input from LLM result
            if isinstance(next_tool_input, dict) and next_tool_input:
                actual_tool_input = next_tool_input
            
            log_msg = f"[MCP Auto-Select] Resolved tool: '{actual_tool_name}' with input: {actual_tool_input}"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
        else:
            log_msg = f"🤖 Executing node MCP tool node for tool: {actual_tool_name}"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        # Schema-aware compile-time fallback from node editor config
        try:
            _schema = _get_tool_schema_by_name(actual_tool_name)
            _root = _normalize_schema_root(_schema) if _schema else {}
            if _root and not _validate_tool_input_against_schema(actual_tool_input, _root):
                compiled_input = _build_input_from_config(config_metadata, _root)
                actual_tool_input = _merge_inputs(actual_tool_input if isinstance(actual_tool_input, dict) else {}, compiled_input)
            
            # Always coerce all inputs to match schema types (handles empty strings, wrong types)
            if _root:
                actual_tool_input = _coerce_all_inputs(actual_tool_input, _root)
            
            state['tool_input'] = actual_tool_input

            log_msg = f"tool_input backfilled for {actual_tool_name}: {state['tool_input']}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, "ErrorMCPToolCallable")
            logger.debug(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)

        # Capture for closure
        _actual_tool_name = actual_tool_name
        _actual_tool_input = actual_tool_input

        async def run_tool_call():
            """A local async function to perform the actual tool call."""
            log_msg = f"Calling MCP tool '{_actual_tool_name}' with input: {_actual_tool_input}"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
            from config.constants import DEFAULT_API_TIMEOUT
            timeout = config_metadata.get('timeout', DEFAULT_API_TIMEOUT)
            return await mcp_call_tool(_actual_tool_name, _actual_tool_input, timeout=timeout)

        # ============================================================
        # Async Mode: Fire-and-forget with pending event tracking
        # ============================================================
        if async_mode:
            try:
                # Get task from runtime context for pending event registration
                task = None
                try:
                    if runtime and hasattr(runtime, 'context'):
                        task = runtime.context.get('task') or runtime.context.get('managed_task')
                except Exception:
                    pass
                
                if task is None:
                    # Fallback: try to get from state
                    task = state.get('_managed_task')
                
                if task is None:
                    log_msg = f"[ASYNC_MODE] No task context available for async tracking, falling back to sync mode"
                    logger.warning(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)
                else:
                    # Register pending event and get correlation ID
                    full_node_name = f"{owner}:{skill_name}:{node_name}"
                    
                    # Resolve timeout with hybrid precedence (tool_input > state > config > default)
                    effective_timeout = resolve_timeout(
                        node_name=full_node_name,
                        state=state,
                        tool_input=_actual_tool_input,
                        config_timeout=async_timeout,
                        default_timeout=60.0
                    )
                    
                    correlation_id = register_async_operation(
                        task=task,
                        source_node=full_node_name,
                        timeout_seconds=effective_timeout
                    )
                    
                    # Inject correlation_id into tool input for webhook callback
                    if isinstance(_actual_tool_input, dict):
                        _actual_tool_input['_correlation_id'] = correlation_id
                    
                    log_msg = f"[ASYNC_MODE] Registered pending event {correlation_id} for {_actual_tool_name} (timeout={effective_timeout}s)"
                    logger.info(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    
                    # Make the tool call (fire-and-forget - we don't wait for full completion)
                    tool_result = run_async_in_sync(run_tool_call())
                    
                    # Store initial result and correlation_id
                    state["tool_result"] = tool_result
                    state["n_steps"] += 1
                    
                    # Track pending operation in state
                    pending_ops = state.setdefault("_pending_async_operations", [])
                    pending_ops.append({
                        "correlation_id": correlation_id,
                        "tool_name": _actual_tool_name,
                        "node_name": full_node_name,
                        "initial_result": tool_result,
                    })
                    
                    tool_call_summary = ActionMessage(
                        content=f"action: async mcp call to {_actual_tool_name}; correlation_id: {correlation_id}; initial_result: {tool_result}"
                    )
                    add_to_history(state, tool_call_summary)
                    
                    log_msg = f"[ASYNC_MODE] Tool call initiated, workflow continues. Completion will be tracked via correlation_id={correlation_id}"
                    logger.info(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    
                    return state
                    
            except Exception as e:
                err_msg = get_traceback(e, f"ErrorAsyncMCPToolCallable({_actual_tool_name})")
                logger.error(err_msg)
                web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                # Fall through to sync mode on error
        
        # ============================================================
        # Sync Mode: Standard blocking tool call
        # ============================================================
        try:
            # Use the utility to run the async function from a sync context
            tool_result = run_async_in_sync(run_tool_call())

            log_msg = f"mcp tool call results: {tool_result}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Add the result to the state (result is a dict, not a list)
            state["tool_result"] = tool_result
            state["n_steps"] += 1

            tool_call_summary = ActionMessage(content=f"action: mcp call to {_actual_tool_name}; result: {tool_result}")
            add_to_history(state, tool_call_summary)

            # Also update attributes for easier access by subsequent nodes
            log_msg = f"state tool_result: {state['tool_result']}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, f"ErrorMCPToolCallable({_actual_tool_name})")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg

        return state

    # graph.add_node("step1", breakpoint_wrapper(step1, "step1", bp_manager))

    node_callable = node_builder(mcp_tool_callable, node_name, skill_name, owner, bp_manager)
    return node_callable


def build_condition_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Conditions are handled by graph's conditional edges.
    Return a no-op callable to keep the graph executable when visited.
    """
    log_msg = f"building condition node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    def _noop(state: dict, *, runtime=None, store=None, **kwargs):
        return state
    # Wrap to inherit common context/retry behavior
    return node_builder(_noop, node_name, skill_name, owner, bp_manager)


def build_loop_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Loops are translated structurally by the compiler; runtime callable is a no-op."""
    log_msg = f"building loop node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    def _noop(state: dict, *, runtime=None, store=None, **kwargs):
        return state
    return node_builder(_noop, node_name, skill_name, owner, bp_manager)


def build_pend_event_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Interrupt the graph and wait for an external event or human input.

    Config (best-effort):
      - prompt: optional string to present to human/agent
      - tag: optional business tag; defaults to node_name
    """
    log_msg = f"building pend event node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    prompt = (config_metadata or {}).get("prompt") or "Action required to continue."
    tag = (config_metadata or {}).get("tag") or node_name

    main_event = config_metadata["inputsValues"]["eventType"]["content"]
    additional_events = config_metadata["inputsValues"].get("pendingSources", {}).get("content", [])


    def _pend(state: dict, *, runtime=None, store=None, **kwargs):
        log_msg = f"🤖 Executing node pending event node: {node_name}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        current_node_name = runtime.context["this_node"].get("name")
        log_msg = f"[Pending For Event Node] pend_for_event_node: {current_node_name}, {state}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
        if state.get("metadata"):
            qa_form = state.get("metadata").get("qa_form", None)
            notification = state.get("metadata").get("notification", None)
        else:
            qa_form = None
            notification = None

        info = {
            "i_tag": tag,
            "paused_at": node_name,
            "prompt_to_human": prompt,
            "qa_form_to_human": qa_form,
            "notification_to_human": notification,
        }
        resume_payload = interrupt(info)

        from agent.ec_skills.llm_utils.llm_utils import try_parse_json
        # If resumer supplied a state patch (e.g., via Command(resume={... "_state_patch": {...}})), merge it
        log_msg = f"[pend_event_node] resume payload immediately after resuming: {resume_payload}"
        logger.debug(log_msg)
        # web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        try:
            state["events"].append({"event_type": resume_payload["event_type"]})
            if isinstance(resume_payload, dict) and "_state_patch" in resume_payload:
                patch = resume_payload.get("_state_patch")
                if isinstance(patch, dict):
                    def _deep_merge(a: dict, b: dict) -> dict:
                        out = dict(a)
                        for k, v in b.items():
                            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                                out[k] = _deep_merge(out[k], v)
                            else:
                                out[k] = v
                        return out

                    # merge patch into state in place
                    try:
                        if isinstance(state, dict):
                            merged = _deep_merge(state, patch)
                            state.clear()
                            state.update(merged)
                    except Exception:
                        pass
        except Exception:
            pass

        log_msg = f"[pend_event_node] resume payload after deep merge: {resume_payload}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        # Enrich state with chat metadata, if available
        try:
            chat_attrs = resume_payload.get("chat_attributes") if isinstance(resume_payload, dict) else None
            if isinstance(chat_attrs, dict) and chat_attrs:
                attrs = state.setdefault("attributes", {}) if isinstance(state, dict) else {}
                attrs.setdefault("chat_attributes", {}).update(chat_attrs)

                for key, value in chat_attrs.items():
                    if value not in (None, "", [], {}):
                        existing = attrs.get(key)
                        if existing in (None, "", [], {}):
                            attrs[key] = value

                msg_list = state.setdefault("messages", []) if isinstance(state, dict) else []
                if isinstance(msg_list, list):
                    while len(msg_list) < 5:
                        msg_list.append("")

                    fill_map = {
                        0: chat_attrs.get("receiverId"),
                        1: chat_attrs.get("chatId"),
                        4: chat_attrs.get("content"),
                    }

                    metadata = resume_payload.get("_state_patch", {}).get("attributes", {}).get("debug", {}).get("last_event_metadata", {}) if isinstance(resume_payload, dict) else {}
                    if isinstance(metadata, dict):
                        params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
                        if params:
                            fill_map.setdefault(0, params.get("receiverId"))
                            if params.get("chatId"):
                                fill_map[1] = fill_map.get(1) or params.get("chatId")
                            if params.get("msgId"):
                                fill_map[2] = params.get("msgId")
                            if params.get("taskId"):
                                fill_map[3] = params.get("taskId")
                            if params.get("content"):
                                fill_map[4] = fill_map.get(4) or params.get("content")

                    for idx, val in fill_map.items():
                        if val and msg_list[idx] in (None, ""):
                            msg_list[idx] = val
        except Exception:
            pass

        log_msg = f"[pend_event_node] resumed, state: {state}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        # Normalize human_text and parse
        raw_ht = resume_payload.get("human_text")
        if isinstance(raw_ht, list):
            raw_ht = raw_ht[0] if raw_ht else None
        if isinstance(raw_ht, dict):
            data = raw_ht
        else:
            data = try_parse_json(raw_ht)
        state.setdefault("metadata", {})
        if isinstance(data, dict):
            if data.get("type", "") == "normal":
                state["metadata"]["filled_parametric_filter"] = data
                logger.debug(f"[{node_name}] saving filled parametric filter form......",
                             state["metadata"]["filled_parametric_filter"])
            elif data.get("type", "") == "score":
                state["metadata"]["filled_fom_form"] = data
                logger.debug(f"[{node_name}] saving filled fom form......",
                             state["metadata"]["filled_fom_form"])

        logger.debug(f"[{node_name}] exit state: {state}")
        return state

    return node_builder(_pend, node_name, skill_name, owner, bp_manager)


def build_chat_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Chat node sends messages via TaskRunner GUI methods."""
    log_msg = f"building chat node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    role = ((config_metadata or {}).get("role") or "assistant").lower()
    msg_tpl = (config_metadata or {}).get("message") or ""
    wait_for_reply = bool((config_metadata or {}).get("wait_for_reply", False))
    def _chat(state: dict, *, runtime=None, store=None, **kwargs):
        from agent.ec_skills.llm_utils.llm_utils import send_response_back
        attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
        log_msg = f"🤖 Executing node Chat node: {node_name}"
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        logger.debug("in chat node....", state)


        # Try to deliver to GUI via TaskRunner helpers
        try:
            llm_output = state["result"].get("llm_result", {})
            # Extract next_prompt for display but preserve full llm_result for downstream conditions
            if isinstance(llm_output, dict):
                response = llm_output.get("next_prompt", "some is not right....")
            else:
                response = str(llm_output) if llm_output else "some is not right...."

            state["job_related"] = state["result"].get("job_related", False)
            # DO NOT overwrite llm_result - downstream condition nodes need the full dict
            # state["result"]["llm_result"] = response  # REMOVED: this was destroying condition data

            # Clean up the response
            # send_result = send_response_back(state)
            logger.debug("just sent response back to GUI....")

        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildChatNode")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)

        return state

    return node_builder(_chat, node_name, skill_name, owner, bp_manager)


def build_rag_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """RAG node with optional LIGHTRAG API."""
    log_msg = f"building rag node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    query_path = (config_metadata or {}).get("query_path") or "attributes.query"
    def _rag(state: dict, *, runtime=None, store=None, **kwargs):
        # Resolve dotted path from state
        err_msg = ""
        resp = None
        cur = state
        for part in query_path.split("."):
            try:
                cur = cur.get(part)
            except Exception:
                cur = None
                break
        query = cur if isinstance(cur, (str, int, float)) else None
        # Try LIGHTRAG backend if configured, otherwise fallback to empty
        results = []
        try:
            rag_url = os.getenv('LIGHTRAG_API_URL') or os.getenv('LIGHTRAG_URL')
            if rag_url and query:
                url = rag_url.rstrip('/') + '/query'
                payload = {"query": str(query)}
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        # best-effort normalize
                        results = data.get('documents') or data.get('results') or data.get('hits') or []
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildRagNode")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
        # Ensure tool_result is a dict; previous nodes may set non-dict objects here
        try:
            tr = state.get("tool_result") if isinstance(state, dict) else None
            if not isinstance(tr, dict):
                tr = {}
                state["tool_result"] = tr
            tr[node_name] = {"query": query, "documents": results}
        except Exception as _e:
            # Best-effort: record error without raising to keep the workflow moving
            try:
                from utils.logger_helper import get_traceback as _gt
                err_msg = _gt(_e, "ErrorRAGNodeToolResult")
                logger.error(err_msg)
                web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            except Exception as _e_:
                err_msg = get_traceback(_e_, "ErrorRAGNodeToolResult")
                logger.debug(f"RAG node tool_result set failed: {err_msg}")
                web_gui.get_ipc_api().send_skill_editor_log("error", f"RAG node tool_result set failed: {err_msg}")
            state["error"] = f"rag node failed to set tool_result: {err_msg}"

        add_to_history(state, ActionMessage(content=f"action: rag {str(query)}; result: {results}; {err_msg}"))
        return state

    return node_builder(_rag, node_name, skill_name, owner, bp_manager)


def build_browser_automation_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Browser automation scaffold.

    Config keys (best-effort):
      - provider: 'browser-use' | 'browsebase' | 'crawl4ai' (default 'browser-use')
      - task: high-level instruction text for the agent
      - action/params: legacy fields folded into task when present
      - wait_for_done: whether to interrupt when external completion is needed
      - model: optional LLM model for browser-use (env fallback supported)
      - enable_guardrail_timer: If True, register pending event for timeout tracking
      - timeout_seconds: Max time for browser automation (default 300)
    """
    log_msg = f"building browser automation node : {config_metadata}"
    logger.debug(log_msg)
    
    # Guardrail timer configuration
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
    enable_guardrail_timer = False
    browser_timeout_seconds = 300.0  # 5 minutes default for browser automation
    hard_timeout_config = False  # If True, cancel operation on timeout (like browser-use native)
    try:
        enable_guardrail_timer = (config_metadata.get('enable_guardrail_timer')
                                  or ((inputs.get('enable_guardrail_timer') or {}).get('content'))
                                  or (config_metadata.get('inputs') or {}).get('enable_guardrail_timer'))
        enable_guardrail_timer = str(enable_guardrail_timer).lower() in ('true', '1', 'yes', 'on') if enable_guardrail_timer else False
        
        timeout_val = (config_metadata.get('timeout_seconds')
                       or ((inputs.get('timeout_seconds') or {}).get('content'))
                       or (config_metadata.get('inputs') or {}).get('timeout_seconds'))
        if timeout_val:
            browser_timeout_seconds = float(timeout_val)
        
        hard_timeout_val = (config_metadata.get('hard_timeout')
                            or ((inputs.get('hard_timeout') or {}).get('content'))
                            or (config_metadata.get('inputs') or {}).get('hard_timeout'))
        hard_timeout_config = str(hard_timeout_val).lower() in ('true', '1', 'yes', 'on') if hard_timeout_val else False
    except Exception:
        pass
    
    provider = ((config_metadata or {}).get("provider") or "browser-use").lower()
    action = (config_metadata or {}).get("action") or "open_page"
    params = (config_metadata or {}).get("params") or {}
    wait_for_done = bool((config_metadata or {}).get("wait_for_done", False))
    task_text = (config_metadata or {}).get("task") or f"{action} {params}".strip()

    inputs = (config_metadata or {}).get("inputsValues", {}) or {}

    # Extract browser settings from node editor
    browser_type_setting = ((inputs.get("browser") or {}).get("content") or "new chromium").lower().strip()
    browser_driver_setting = ((inputs.get("browserDriver") or {}).get("content") or "native").lower().strip()
    cdp_port_setting = ((inputs.get("cdpPort") or {}).get("content") or "").strip()
    
    # Extract shop_name and build downloads_path
    from pathlib import Path
    from datetime import datetime
    from config.app_info import app_info
    
    shop_name_selection = ((inputs.get("shopName") or {}).get("content") or "").strip()
    custom_shop_name = ((inputs.get("customShopName") or {}).get("content") or "").strip()
    # Use custom shop name if 'custom' is selected, otherwise use the selected shop
    shop_name = custom_shop_name if shop_name_selection == "custom" else shop_name_selection
    
    appdata_path = Path(app_info.appdata_path)
    date_str = datetime.now().strftime("%Y%m%d")
    downloads_path = str(appdata_path / "daily_work" / f"D{date_str}" / shop_name) if shop_name else None
    
    logger.debug(f"[BrowserAutomation] browser={browser_type_setting}, driver={browser_driver_setting}, cdp_port={cdp_port_setting}")
    logger.debug(f"[BrowserAutomation] shop_name={shop_name}, downloads_path={downloads_path}")

    prompt_selection = ((inputs.get("promptSelection") or {}).get("content") or "inline").strip()
    logger.debug("[BrowserAutomation]prompt_selection:", prompt_selection)

    system_prompt_id = ((inputs.get("systemPromptId") or {}).get("content") or None)
    user_prompt_id = ((inputs.get("promptId") or {}).get("content") or None)

    # Get inline prompt content
    inline_system_prompt = ((inputs.get("systemPrompt") or {}).get("content") or "")
    inline_user_prompt = ((inputs.get("prompt") or {}).get("content") or "")

    logger.debug("[BrowserAutomation]inline_system_prompt:", inline_system_prompt)
    logger.debug("[BrowserAutomation]inline_user_prompt:", inline_user_prompt)
    # Load prompts using prompt loader (handles both inline and saved prompts)
    # Resolve prompt templates based on the selected prompt id first for initial config preview
    resolved_system_prompt, resolved_user_prompt = _resolve_prompt_templates(
        prompt_selection,
        inline_system_prompt,
        inline_user_prompt,
    )

    from agent.ec_skills.prompt_loader import get_prompt_content
    system_prompt_content = get_prompt_content(system_prompt_id, inline_system_prompt) if (system_prompt_id or inline_system_prompt) else None
    user_prompt_content = get_prompt_content(user_prompt_id, inline_user_prompt) if (user_prompt_id or inline_user_prompt) else None

    # If prompts are configured, use them to enhance the task text
    if system_prompt_content or user_prompt_content:
        prompt_parts = []
        if system_prompt_content:
            prompt_parts.append(f"System Instructions:\n{system_prompt_content}")
        if user_prompt_content:
            prompt_parts.append(f"Task:\n{user_prompt_content}")
        if prompt_parts:
            task_text = "\n\n".join(prompt_parts)

    async def _get_or_create_browser_session(mainwin):
        """Get or create browser session based on node editor settings."""
        from gui.manager.browser_manager import BrowserManager, BrowserType, BrowserStatus
        
        logger.debug(f"[BrowserAutomation] Getting browser session: browser={browser_type_setting}, driver={browser_driver_setting}, cdp_port={cdp_port_setting}")
        
        # Get or create BrowserManager
        if not hasattr(mainwin, 'browser_manager') or mainwin.browser_manager is None:
            mainwin.browser_manager = BrowserManager(default_webdriver_path=mainwin.getWebDriverPath())
        
        browser_manager: BrowserManager = mainwin.browser_manager
        
        # Map browser setting to BrowserType
        browser_type_map = {
            'new chromium': BrowserType.CHROME,
            'existing chrome': BrowserType.CHROME,
            'ads power': BrowserType.ADSPOWER,
            'adspower': BrowserType.ADSPOWER,
            'ziniao': BrowserType.CHROME,  # Treat as Chrome for now
            'multi-login': BrowserType.CHROME,  # Treat as Chrome for now
        }
        browser_type = browser_type_map.get(browser_type_setting, BrowserType.CHROME)
        
        # Determine CDP port
        cdp_port = int(cdp_port_setting) if cdp_port_setting and cdp_port_setting.isdigit() else 9228
        
        # Acquire browser based on settings
        auto_browser = browser_manager.acquire_browser(
            agent_id=getattr(mainwin, 'current_agent_id', 'default_agent'),
            task=f"browser_automation_{node_name}",
            browser_type=browser_type,
            cdp_port=cdp_port,
            webdriver_path=mainwin.getWebDriverPath(),
            downloads_path=downloads_path,
        )
        
        if auto_browser and auto_browser.status != BrowserStatus.ERROR:
            # Set webdriver on mainwin for backward compatibility
            if auto_browser.webdriver:
                mainwin.setWebDriver(auto_browser.webdriver)
            
            # Start browser session if not already started (for CDP/native mode)
            if browser_driver_setting == 'native' and auto_browser.browser_session:
                logger.info(f"[BrowserAutomation] Starting browser session: {auto_browser.browser_session.id}")
                await auto_browser.browser_session.start()
                logger.info(f"[BrowserAutomation] Browser session started!")
                return auto_browser.browser_session
            
            return auto_browser
        else:
            error_msg = auto_browser.last_error if auto_browser else "Unknown error"
            logger.error(f"[BrowserAutomation] Failed to acquire browser: {error_msg}")
            return None

    async def _run_browser_use(task: str, mainwin) -> dict:
        try:
            from browser_use import Agent as BUAgent
            from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
            # from browser_use.browser.context import BrowserContext as BUBrowserContext
            log_msg = f"🤖 Executing node Browser Automation node: {node_name}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Prefer privacy-aware wrapper if available; fall back to vanilla Agent.
            AgentClass = BUAgent
            try:
                from agent.ec_skills.browser_use_extension.privacy_agent import PrivacyAgent
                AgentClass = PrivacyAgent
                logger.info("[BrowserAutomation] Using PrivacyAgent for browser-use")
            except Exception as _privacy_import_exc:
                logger.info(f"[BrowserAutomation] PrivacyAgent not available, using browser_use.Agent ({_privacy_import_exc})")

            if not mainwin:
                raise ValueError("mainwin is required. Must use mainwin configuration for browser_use LLM.")

            # Use mainwin's LLM configuration (no fallback)
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
            llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
            if not llm:
                raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")

            controller = custom_controller
            print("[BROWSER USE]Agent task:", task)
            
            # Auto-detect model vision support and set use_vision accordingly to avoid warnings
            from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
            agent_kwargs = {'use_vision': get_use_vision_from_llm(llm, context="build_browser_automation_node")}
            
            # Get or create browser session based on node editor settings
            browser_session = await _get_or_create_browser_session(mainwin)
            
            if browser_type_setting == 'new chromium':
                # For new chromium, let browser_use create its own browser
                logger.info("[BrowserAutomation] Using new chromium - browser_use will create browser")
                agent = AgentClass(task=task, llm=llm, controller=controller, **agent_kwargs)
            elif browser_driver_setting == 'native' and browser_session:
                # For native (CDP) mode with existing browser session
                logger.info(f"[BrowserAutomation] Using existing browser session via CDP: {browser_type_setting}")
                # Create browser_use Browser with CDP connection
                cdp_port = int(cdp_port_setting) if cdp_port_setting and cdp_port_setting.isdigit() else 9228
                cdp_url = f"http://127.0.0.1:{cdp_port}"
                
                # browser_use expects a Browser instance for existing browsers
                # browser = BUBrowser(config={"cdp_url": cdp_url})
                await browser_session.start()
                # browser_context = BUBrowserContext(browser=browser)
                agent = AgentClass(task=task, llm=llm, controller=controller, browser_session=browser_session, **agent_kwargs)
            else:
                # Fallback: let browser_use create its own browser
                logger.info(f"[BrowserAutomation] Fallback - browser_use will create browser (driver={browser_driver_setting})")
                agent = AgentClass(task=task, llm=llm, controller=controller, **agent_kwargs)
            
            history = await agent.run()
            print("[BROWSER USE]Agent Run History:", history)
            final = history.final_result() if hasattr(history, 'final_result') else None
            print("[BROWSER USE]Agent Run Results:", final)
            return {"final": final, "history": str(history)}
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNode")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            return {"error": str(err_msg)}

    def _auto(state: dict, *, runtime=None, store=None, **kwargs):
        active_system_prompt, active_user_prompt = _resolve_prompt_templates(
            prompt_selection,
            inline_system_prompt,
            inline_user_prompt,
        )

        # Find all variable placeholders (e.g., {{var_name}}) in the prompts
        variables = re.findall(r'\{\{(\w+)\}\}', active_system_prompt + active_user_prompt)
        prompt_refs = state.get("prompt_refs", {}) if isinstance(state, dict) else {}
        format_context = {}
        for var in variables:
            if var in prompt_refs:
                format_context[var] = prompt_refs[var]
            else:
                logger.warning(f"[build_browser_automation_node] Variable '{{{{{{var}}}}}}' missing in prompt_refs; using empty string.")
                format_context[var] = ""

        # Substitute {{var_name}} with values from format_context
        try:
            final_system_prompt = active_system_prompt
            final_user_prompt = active_user_prompt
            for var, val in format_context.items():
                final_system_prompt = final_system_prompt.replace(f'{{{{{var}}}}}', str(val))
                final_user_prompt = final_user_prompt.replace(f'{{{{{var}}}}}', str(val))
        except Exception as exc:
            err_msg = f"Error formatting browser automation prompt: {exc}"
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
            final_system_prompt = active_system_prompt
            final_user_prompt = active_user_prompt

        # Combine prompts into task instructions for browser_use agent
        task_instructions = final_user_prompt.strip() or base_task_text or final_system_prompt.strip()
        if final_system_prompt.strip():
            combined_task = f"{final_system_prompt.strip()}\n\n{task_instructions}"
        else:
            combined_task = task_instructions

        # print("final_system_prompt:", final_system_prompt)
        # print("final_user_prompt:", final_user_prompt)
        print("combined_task:", combined_task)
        if provider == 'browser-use':
            # Get mainwin from agent via state
            mainwin = None
            try:
                from agent.agent_service import get_agent_by_id
                if state.get("messages") and len(state["messages"]) > 0:
                    agent_id = state["messages"][0]
                    agent = get_agent_by_id(agent_id)
                    if agent and hasattr(agent, 'mainwin'):
                        mainwin = agent.mainwin
            except Exception as e:
                err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNode brower-use")
                logger.warning(err_msg)
                web_gui.get_ipc_api().send_skill_editor_log("warning", err_msg)

            if not mainwin:
                err_msg = "Cannot create browser_use LLM: mainwin not available. Please ensure agent is properly initialized."
                logger.error(f"[build_browser_automation_node] {err_msg}")
                web_gui.get_ipc_api().send_skill_editor_log("error", f"[build_browser_automation_node] {err_msg}")
                state.setdefault("tool_result", {})
                state["tool_result"][node_name] = {"provider": provider, "task": task_instructions, "error": err_msg}

                add_to_history(state, ActionMessage(content=f"action: browser-use {task_text}; result: {err_msg}"))

                return state
            
            info = {}
            correlation_id = None
            full_node_name = f"{owner}:{skill_name}:{node_name}"
            
            # Resolve timeout with hybrid precedence (runtime > config > default)
            effective_timeout = resolve_timeout(
                node_name=full_node_name,
                state=state,
                tool_input=None,  # Browser nodes don't have tool_input
                config_timeout=browser_timeout_seconds,
                default_timeout=300.0
            )
            
            # Resolve hard timeout mode
            use_hard_timeout = resolve_hard_timeout(
                node_name=full_node_name,
                state=state,
                tool_input=None,
                config_hard_timeout=hard_timeout_config
            )
            
            # Start guardrail timer for long-running browser automation (soft timeout only)
            if enable_guardrail_timer and not use_hard_timeout:
                try:
                    task = None
                    try:
                        if runtime and hasattr(runtime, 'context'):
                            task = runtime.context.get('task') or runtime.context.get('managed_task')
                    except Exception:
                        pass
                    if task is None:
                        task = state.get('_managed_task')
                    
                    if task:
                        correlation_id = register_async_operation(
                            task=task,
                            source_node=f"browser:{full_node_name}",
                            timeout_seconds=effective_timeout
                        )
                        log_msg = f"[BROWSER_GUARDRAIL] Started timer {correlation_id} ({effective_timeout}s)"
                        logger.info(log_msg)
                        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                except Exception as e:
                    logger.warning(f"[BROWSER_GUARDRAIL] Failed to start timer: {e}")
            
            try:
                # Execute browser automation with optional hard timeout
                if use_hard_timeout:
                    import asyncio
                    log_msg = f"[BROWSER_HARD_TIMEOUT] Using hard timeout ({effective_timeout}s) - will cancel on timeout"
                    logger.info(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
                    try:
                        async def _run_with_hard_timeout():
                            return await asyncio.wait_for(
                                _run_browser_use(combined_task, mainwin),
                                timeout=effective_timeout
                            )
                        info = run_async_in_sync(_run_with_hard_timeout()) or {}
                    except asyncio.TimeoutError:
                        error_msg = f"Browser automation timed out after {effective_timeout}s (hard timeout)"
                        logger.error(f"[BROWSER_HARD_TIMEOUT] {error_msg}")
                        web_gui.get_ipc_api().send_skill_editor_log("error", error_msg)
                        # Record failure if task available
                        try:
                            task = state.get('_managed_task')
                            if task is None and runtime and hasattr(runtime, 'context'):
                                task = runtime.context.get('task') or runtime.context.get('managed_task')
                            if task and hasattr(task, 'record_failure'):
                                task.record_failure()
                        except Exception:
                            pass
                        info = {"error": error_msg, "timed_out": True}
                else:
                    info = run_async_in_sync(_run_browser_use(combined_task, mainwin)) or {}
                
                # Cancel guardrail timer on success
                if correlation_id:
                    try:
                        task = state.get('_managed_task')
                        if task is None and runtime and hasattr(runtime, 'context'):
                            task = runtime.context.get('task') or runtime.context.get('managed_task')
                        if task:
                            resolve_async_operation(task, correlation_id, result={"status": "completed"})
                            log_msg = f"[BROWSER_GUARDRAIL] Cancelled timer {correlation_id} (browser automation completed)"
                            logger.info(log_msg)
                    except Exception as e:
                        logger.warning(f"[BROWSER_GUARDRAIL] Failed to cancel timer: {e}")
                        
            except Exception as e:
                # Cancel guardrail timer on error too
                if correlation_id:
                    try:
                        task = state.get('_managed_task')
                        if task is None and runtime and hasattr(runtime, 'context'):
                            task = runtime.context.get('task') or runtime.context.get('managed_task')
                        if task:
                            resolve_async_operation(task, correlation_id, error=str(e))
                    except Exception:
                        pass
                info = {"error": f"browser-use run failed: {e}"}
            state.setdefault("tool_result", {})
            # state["tool_result"][node_name] = {
            state["tool_result"] = {
                "provider": provider,
                "task": task_instructions,
                "systemPrompt": final_system_prompt,
                **info,
            }
            # Optionally interrupt if downstream needs human check
            if wait_for_done and info.get("error"):
                interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Automation pending: {action}"})

            state["n_steps"] += 1
            add_to_history(state, ActionMessage(content=f"action: browser-use {task_instructions}; result: {info}"))

            return state
        # Fallback: record intent for other providers
        intents = state.setdefault("metadata", {}).setdefault("automation_intents", [])
        intents.append({"node": node_name, "provider": provider, "action": action, "params": params, "task": combined_task})
        if wait_for_done:
            interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Please perform automation: {action}"})

        add_to_history(state, ActionMessage(content=f"action: non browser-use {task_instructions}; result: {info}"))

        return state

    return node_builder(_auto, node_name, skill_name, owner, bp_manager)


def build_task_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """
    Builds a task node for organizing workflow steps.
    Currently a pass-through node that can be extended with task-specific logic.
    
    Config keys (best-effort):
        - description: Optional task description
        - metadata: Optional task metadata
    """
    log_msg = f"building task node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
    
    description = (config_metadata or {}).get('description', '')
    
    def _task(state: dict, **kwargs):
        """Task node implementation - currently a pass-through."""
        try:
            # Add task execution marker to metadata
            metadata = state.setdefault('metadata', {})
            tasks = metadata.setdefault('executed_tasks', [])
            tasks.append({
                'node': node_name,
                'description': description,
                'skill': skill_name
            })
            
            log_msg = f"Task node '{node_name}' executed: {description}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
            
        except Exception as e:
            err_msg = get_traceback(e, f"ErrorInTaskNode_{node_name}")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
        
        return state
    
    return node_builder(_task, node_name, skill_name, owner, bp_manager)


def _get_chat_llm(model_name: str, temperature: float = 0.0):
    """
    Helper function to create a chat LLM instance for tool picker.
    Defaults to OpenAI with credentials from secure_store.
    """
    try:
        # Get API key from secure store
        username = get_current_username()
        api_key = secure_store.get("OPENAI_API_KEY", username=username) or ""
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in secure store")
        
        # Create OpenAI LLM instance
        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature
        )
        return llm
    except Exception as e:
        err_msg = get_traceback(e, "ErrorCreatingLLM")
        logger.error(f"Failed to create LLM for tool picker: {err_msg}")
        raise


def build_tool_picker_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """
    Builds a tool picker node that uses LLM to select appropriate tools based on action plans.
    
    Workflow:
    1. Reads next_actions from state['result']['llm_result']['next_actions']
    2. Filters available tool schemas by category and sub_category
    3. Uses LLM to map action_name and action_input to specific tool_name and tool_input
    4. Outputs to state['tool_calls'] for downstream MCP tool node execution
    
    Config keys (best-effort):
        - model: LLM model name (default: gpt-4o-mini)
        - temperature: LLM temperature (default: 0.0 for deterministic selection)
    """
    log_msg = f"building tool-picker node : {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
    
    # Get LLM config from node metadata or use defaults
    model_name = (config_metadata or {}).get('model', 'gpt-4o-mini')
    temperature = (config_metadata or {}).get('temperature', 0.0)
    
    def _tool_picker(state: dict, **kwargs):
        """Tool picker node implementation using LLM to select tools."""
        try:
            log_msg = f"🤖 Executing node LLM assisted tool picker node: {node_name}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Step 1: Extract next_actions from previous LLM result
            logger.debug("[ToolPickerNode] Extracting next_actions from state")
            result = state.get('result', {})
            llm_result = result.get('llm_result', {})
            next_actions = llm_result.get('next_actions', [])
            logger.debug("[ToolPickerNode] found next_actions:", next_actions)

            if not next_actions:
                log_msg = f"[{node_name}] No next_actions found in state['result']['llm_result']"
                logger.warning(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)
                state.setdefault('tool_calls', [])
                return state
            
            log_msg = f"[{node_name}] Processing {len(next_actions)} action(s)"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
            
            # Step 2: Get all available tool schemas from MCP
            try:
                from agent.mcp.server.tool_schemas import tool_schemas
                all_tools = tool_schemas or []
            except Exception as e:
                err_msg = get_traceback(e, f"ErrorLoadingToolSchemas_{node_name}")
                logger.error(err_msg)
                web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                all_tools = []
            
            # Step 3: Process each action
            tool_calls = []
            for action in next_actions:
                category = action.get('category', '')
                sub_category = action.get('sub_category', '')
                action_name = action.get('action_name', '')
                action_input = action.get('action_input', {})
                
                log_msg = f"[{node_name}] Selecting tool for category={category}, sub_category={sub_category}, action={action_name}"
                logger.debug(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
                
                # Step 4: Filter tools by category and sub_category
                filtered_tools = []
                for tool in all_tools:
                    description = tool.get('description', '')
                    # Parse category and sub_category from description
                    import re
                    cat_match = re.search(r'<category>([^<]+)</category>', description)
                    subcat_match = re.search(r'<sub-category>([^<]+)</sub-category>', description)
                    
                    tool_category = cat_match.group(1).strip() if cat_match else ''
                    tool_subcategory = subcat_match.group(1).strip() if subcat_match else ''
                    
                    # Match both category and sub_category
                    if category.lower() in tool_category.lower() and sub_category.lower() in tool_subcategory.lower():
                        filtered_tools.append(tool)
                
                log_msg = f"[{node_name}] Filtered {len(filtered_tools)} tools from {len(all_tools)} total"
                logger.debug(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
                
                if not filtered_tools:
                    log_msg = f"[{node_name}] No tools found for category={category}, sub_category={sub_category}"
                    logger.warning(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("warning", log_msg)
                    continue
                
                # Step 5: Build prompt for LLM to select exact tool
                tools_schema_text = json.dumps(filtered_tools, indent=2, ensure_ascii=False)
                
                selection_prompt = f"""You are a tool selection expert. Given the available tools and the requested action, select the most appropriate tool and prepare its input parameters.
Available Tools:
{tools_schema_text}

Requested Action:
- Action Name: {action_name}
- Action Input: {json.dumps(action_input, indent=2, ensure_ascii=False)}

Task: Select the exact tool function name and prepare the complete tool input parameters.

Output Format (JSON):
{{
    "tool_name": "<exact_function_name_from_tools>",
    "tool_input": {{<complete_input_parameters_dict>}}
}}

Requirements:
1. tool_name must exactly match one of the function names in available tools
2. tool_input must conform to the selected tool's input schema
3. Map action_input fields to the correct tool parameter names
4. Output ONLY the JSON, no additional text"""

                # Step 6: Call LLM to select tool
                try:
                    # Get LLM instance
                    llm = _get_chat_llm(model_name, temperature)
                    
                    # Invoke LLM
                    llm_response = llm.invoke([{"role": "user", "content": selection_prompt}])
                    response_text = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                    
                    # Parse JSON response
                    # Extract JSON from markdown code blocks if present
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(1)
                    
                    tool_selection = json.loads(response_text.strip())
                    tool_name = tool_selection.get('tool_name', '')
                    tool_input = tool_selection.get('tool_input', {})
                    
                    log_msg = f"[{node_name}] LLM selected tool: {tool_name}"
                    logger.debug(log_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("debug", log_msg)
                    
                    # Add to tool_calls list
                    tool_calls.append({
                        'tool_name': tool_name,
                        'tool_input': tool_input,
                        'source_action': {
                            'category': category,
                            'sub_category': sub_category,
                            'action_name': action_name
                        }
                    })
                    
                except Exception as e:
                    err_msg = get_traceback(e, f"ErrorLLMToolSelection_{node_name}")
                    logger.error(err_msg)
                    web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
                    continue
            
            # Step 7: Store tool_calls in state
            state['tool_calls'] = tool_calls
            
            log_msg = f"[{node_name}] Generated {len(tool_calls)} tool call(s)"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("info", log_msg)
            
            # Store in metadata for debugging
            metadata = state.setdefault('metadata', {})
            metadata['last_tool_picker_output'] = {
                'node': node_name,
                'tool_calls': tool_calls,
                'actions_processed': len(next_actions)
            }
            
        except Exception as e:
            err_msg = get_traceback(e, f"ErrorInToolPickerNode_{node_name}")
            logger.error(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
            state.setdefault('tool_calls', [])
        
        return state
    
    return node_builder(_tool_picker, node_name, skill_name, owner, bp_manager)
