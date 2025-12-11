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

    structured_sections = normalized.get("sections") or []
    if structured_sections:
        for section in structured_sections:
            if not isinstance(section, dict):
                continue
            items = section.get("items") if isinstance(section.get("items"), list) else []
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
            label = str(section.get("type") or "").strip()
            items = section.get("items") if isinstance(section.get("items"), list) else []
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

    human_inputs = normalized.get("humanInputs") or []
    human_inputs_joined = _join_list(human_inputs if isinstance(human_inputs, list) else [])
    if human_inputs_joined:
        _add_section(user_parts, "Provide", human_inputs_joined)

    user_sections = normalized.get("userSections") or []
    for section in user_sections:
        if not isinstance(section, dict):
            continue
        items = section.get("items") if isinstance(section.get("items"), list) else []
        joined = _join_list(items)
        if not joined:
            continue
        label = _section_label(section)
        _add_section(user_parts, label or None, joined)

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

    Returns:
        A callable function that takes a state dictionary and returns the updated state.
    """
    # Extract configuration from metadata with sensible defaults (tolerant to missing keys)
    logger.debug("building llm node:", config_metadata)
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
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


        active_system_prompt, active_user_prompt = _resolve_prompt_templates(
            prompt_selection,
            system_prompt_template,
            user_prompt_template,
        )

        # Find all variable placeholders (e.g., {var_name}) in the prompts
        variables = re.findall(r'\{(\w+)\}', active_system_prompt + active_user_prompt)

        # Get attributes from state, default to an empty dict if not present
        prompt_refs = state.get("prompt_refs", {})

        # Prepare the context for formatting the prompts by pulling values from the state
        format_context = {}
        for var in variables:
            if var in prompt_refs:
                format_context[var] = prompt_refs[var]
            else:
                logger.warning(f"Warning: Variable '{{{var}}}' not found in state prompt_refs. Using empty string.")
                format_context[var] = ""

        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        safe_context = _SafeDict(format_context)

        # Format the final prompts with values from the state, preserving unknown placeholders
        try:
            final_system_prompt = _escape_positional_placeholders(active_system_prompt).format_map(safe_context)
            final_user_prompt = _escape_positional_placeholders(active_user_prompt).format_map(safe_context)

            logger.debug("final_system_prompt:", final_system_prompt)
            logger.debug("final_user_prompt:", final_user_prompt)
        except KeyError as e:
            err_msg = f"Error formatting prompt: Missing key {e} in state prompt_refs."
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
            run_pre_llm_hook(full_node_name, agent, state, prompt_src="local", prompt_data=messages)

            # Adjust context window based on provider limitations
            # Fetch max_tokens from LLM config (gui/config/llm_providers.json)
            from gui.config.llm_config import llm_config
            context_limit = llm_config.get_max_tokens(llm_provider, model_name)
            logger.debug(f"Using max_tokens={context_limit} from config for {llm_provider}/{model_name}")
            
            logger.debug(f"Forming context (limit={context_limit})......")
            recent_context = get_recent_context(state.get("history", []), max_tokens=context_limit)

            log_msg = f"recent_context: [{len(recent_context)} messages] {recent_context}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Build LLM from node config (do NOT depend on mainwin.llm)
            llm = None
            try:
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

                def _invoke_with_thread(llm_to_use, timeout_sec: float):
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

                # Single attempt (node-configured llm, no fallback)
                response = _invoke_with_thread(llm, 150.0)

                log_msg = f"✅ LLM response received from {llm_provider}"
                logger.info(log_msg)
                web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

                # It's good practice to put results in specific keys
                run_post_llm_hook(full_node_name, agent, state, response)
                logger.debug(f"llm_node finished..... {state}")

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

    Returns:
        A callable function that takes a state dictionary.
    """
    # Accept multiple shapes from GUI/legacy formats
    log_msg = f"building mcp tool node: {config_metadata}"
    logger.debug(log_msg)
    web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

    tool_name = None
    try:
        tool_name = (config_metadata.get('tool_name')
                     or config_metadata.get('toolName')
                     or ((config_metadata.get('inputsValues') or {}).get('tool_name') or {}).get('content')
                     or ((config_metadata.get('inputsValues') or {}).get('toolName') or {}).get('content')
                     or (config_metadata.get('inputs') or {}).get('tool_name')
                     or (config_metadata.get('inputs') or {}).get('toolName'))

    except Exception:
        tool_name = None

    # If tool_name is not specified, return an error node
    if not tool_name:
        err_msg = f"'tool_name' is missing in config_metadata for mcp_tool_calling_node. node_name={node_name}, skill_name={skill_name}"
        logger.error(err_msg)
        logger.debug(f"[MCP] config_metadata keys: {list(config_metadata.keys()) if config_metadata else 'None'}")
        web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)
        return lambda state, **kwargs: {**state, 'error': f'MCP tool_name not configured for node {node_name}'}

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
        log_msg = f"🤖 Executing node MCP tool node for tool: {tool_name}"
        logger.info(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        # By convention, the input for the tool is expected in state['tool_input']
        tool_input = state.get('tool_input', {})

        # Schema-aware compile-time fallback from node editor config
        try:
            _schema = _get_tool_schema_by_name(tool_name)
            _root = _normalize_schema_root(_schema) if _schema else {}
            if _root and not _validate_tool_input_against_schema(tool_input, _root):
                compiled_input = _build_input_from_config(config_metadata, _root)
                tool_input = _merge_inputs(tool_input if isinstance(tool_input, dict) else {}, compiled_input)
            
            # Always coerce all inputs to match schema types (handles empty strings, wrong types)
            if _root:
                tool_input = _coerce_all_inputs(tool_input, _root)
            
            state['tool_input'] = tool_input

            log_msg = f"tool_input backfilled for {tool_name}: {state['tool_input']}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, "ErrorMCPToolCallable")
            logger.debug(err_msg)
            web_gui.get_ipc_api().send_skill_editor_log("error", err_msg)


        async def run_tool_call():
            """A local async function to perform the actual tool call."""
            log_msg = f"Calling MCP tool '{tool_name}' with input: {tool_input}"
            logger.info(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)
            from config.constants import DEFAULT_API_TIMEOUT
            timeout = config_metadata.get('timeout', DEFAULT_API_TIMEOUT)
            return await mcp_call_tool(tool_name, tool_input, timeout=timeout)

        try:
            # Use the utility to run the async function from a sync context
            tool_result = run_async_in_sync(run_tool_call())

            log_msg = f"mcp tool call results: {tool_result}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            # Add the result to the state (result is a dict, not a list)
            state['tool_result'] = tool_result
            state['n_steps'] += 1

            tool_call_summary = ActionMessage(content=f"action: mcp call to {tool_name}; result: {tool_result}")
            add_to_history(state, tool_call_summary)

            # Also update attributes for easier access by subsequent nodes
            log_msg = f"state tool_result: {state['tool_result']}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, f"ErrorMCPToolCallable({tool_name})")
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
    """
    log_msg = f"building browser automation node : {config_metadata}"
    logger.debug(log_msg)
    provider = ((config_metadata or {}).get("provider") or "browser-use").lower()
    action = (config_metadata or {}).get("action") or "open_page"
    params = (config_metadata or {}).get("params") or {}
    wait_for_done = bool((config_metadata or {}).get("wait_for_done", False))
    task_text = (config_metadata or {}).get("task") or f"{action} {params}".strip()

    inputs = (config_metadata or {}).get("inputsValues", {}) or {}

    prompt_selection = ((inputs.get("promptSelection") or {}).get("content") or "inline").strip()
    logger.debug("[LLMNode]prompt_selection:", prompt_selection)

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

    async def _run_browser_use(task: str, mainwin) -> dict:
        try:
            from browser_use import Agent as BUAgent, Controller as BUController
            from browser_use.browser.profile import BrowserProfile as BUBrowserProfile
            log_msg = f"🤖 Executing node Browser Automation node: {node_name}"
            logger.debug(log_msg)
            web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

            if not mainwin:
                raise ValueError("mainwin is required. Must use mainwin configuration for browser_use LLM.")

            # Use mainwin's LLM configuration (no fallback)
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
            llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
            if not llm:
                raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")

            controller = BUController()
            profile = BUBrowserProfile()
            print("[BROWSER USE]Agent task:", task)
            # Auto-detect model vision support and set use_vision accordingly to avoid warnings
            from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
            agent_kwargs = {'use_vision': get_use_vision_from_llm(llm, context="build_browser_automation_node")}
            agent = BUAgent(task=task, llm=llm, controller=controller, browser_profile=profile, **agent_kwargs)
            history = await agent.run()
            print("[BROWSER USE]Agent Run Results:", history)
            final = history.final_result() if hasattr(history, 'final_result') else None
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

        variables = re.findall(r'\{(\w+)\}', active_system_prompt + active_user_prompt)
        prompt_refs = state.get("prompt_refs", {}) if isinstance(state, dict) else {}
        format_context = {}
        for var in variables:
            if var in prompt_refs:
                format_context[var] = prompt_refs[var]
            else:
                logger.warning(f"[build_browser_automation_node] Variable '{{{var}}}' missing in prompt_refs; using empty string.")
                format_context[var] = ""

        try:
            final_system_prompt = active_system_prompt.format(**format_context)
            final_user_prompt = active_user_prompt.format(**format_context)
        except KeyError as exc:
            err_msg = f"Error formatting browser automation prompt, missing key {exc}"
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
            try:
                info = run_async_in_sync(_run_browser_use(combined_task, mainwin)) or {}
            except Exception as e:
                info = {"error": f"browser-use run failed: {e}"}
            state.setdefault("tool_result", {})
            state["tool_result"][node_name] = {
                "provider": provider,
                "task": task_instructions,
                "systemPrompt": final_system_prompt,
                **info,
            }
            # Optionally interrupt if downstream needs human check
            if wait_for_done and info.get("error"):
                interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Automation pending: {action}"})

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
