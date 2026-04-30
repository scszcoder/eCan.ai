import re
import os
import json
import time
import threading
import traceback
import string
import importlib.util
import httpx
from urllib.parse import urlparse, parse_qsl, urlunparse

# Process-level guard to prevent duplicate messages from parallel pend_event_node executions.
# Key: (skill_name, node_name, chat_id) → True once sent.
_PEND_GLOBAL_SENT = {}
_PEND_GLOBAL_LOCK = threading.Lock()
from agent.mcp.local_client import mcp_call_tool
# REMOVED: from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync  # Moved to lazy import to avoid circular dependency
from agent.ec_skills.dev_defs import BreakpointManager
from agent.ec_tasks.pending_events import register_async_operation, resolve_async_operation
from langchain_core.messages import HumanMessage, SystemMessage
from agent.ec_skill import node_builder
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from langgraph.types import interrupt
from utils.env.secure_store import secure_store, get_current_username
# REMOVED: from agent.ec_skills.llm_utils.llm_utils import _create_no_proxy_http_client  # Moved to lazy import to avoid circular dependency
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_community.chat_models import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_deepseek import ChatDeepSeek
# NOTE: prompt_handler is imported lazily to avoid PySide6 dependency in cloud worker
# from gui.ipc.w2p_handlers import prompt_handler
from agent.cloud_worker.cloud_logger import send_skill_editor_log

from typing import Any, Awaitable, Callable, Literal, cast, overload
from dataclasses import dataclass

from langchain_core.messages.base import BaseMessage, BaseMessageChunk


# ==================== Browser-Use Node Lifecycle Hooks ====================
#
# Site-specific business-case patterns (e.g. Feige's front-desk +
# Q&A-worker-team fan-out) that wrap ``browser_automation`` register
# themselves here as async callables invoked before the browser-use
# agent runs.  If any hook returns a non-None state dict, the LLM
# invocation is skipped and that state dict is returned from the node.
# Hooks are invoked in registration order.
#
# Site bundles (e.g. ``hooks/external/feige_chat``) register their
# hook at import time; this module imports the bundle near the end of
# the file so the registry is populated before any node executes.
# ``build_node`` itself has no knowledge of what any hook does — it
# only invokes them.

# Early-phase hooks run BEFORE the browser-use agent is constructed.
# Used for fast-paths that can decide to short-circuit the whole node
# based on the incoming event alone (e.g. Feige's HOT-PATH-B typing a
# pre-computed reply into Feige without invoking the LLM or the full
# browser-use agent lifecycle).  ``agent`` is always None at this phase.
_before_browser_session_setup_hooks: list[
    Callable[[Any, dict, dict, "BrowserUseHookContext"], Awaitable[dict | None]]
] = []


def register_before_browser_session_setup_hook(
    hook: Callable[[Any, dict, dict, "BrowserUseHookContext"], Awaitable[dict | None]],
) -> None:
    """Register *hook* to be invoked BEFORE the browser-use agent is
    constructed (early phase).  Use this for fast-paths that can decide
    on the incoming event alone without needing the LLM or a fully
    set-up browser-use agent.

    Hook signature: ``hook(agent, state, inputs, hook_ctx)``.  ``agent``
    is always ``None`` at this phase — acquire a browser session via
    ``hook_ctx.get_or_create_browser_session`` if needed.  Returning a
    non-None state dict short-circuits the whole node; returning
    ``None`` lets the next early hook run (or the late phase, if no
    more early hooks).  Registration is idempotent.
    """
    if hook not in _before_browser_session_setup_hooks:
        _before_browser_session_setup_hooks.append(hook)


# Prompt-build-phase hooks run AFTER DOM event items have been
# extracted + compacted but BEFORE the task prompt / override block
# are finalised and the browser-use agent is constructed.  Site
# plugins use this to enrich the task prompt with business-case-
# specific rules (e.g. Feige's front-desk actionable-items filter,
# protocol-override block, and deterministic auto-dispatch short-
# circuit).  ``build_node`` itself only performs a generic snapshot
# injection when no prompt-build hook handles the round.
_before_prompt_build_hooks: list[
    Callable[[dict, dict, "BrowserUseHookContext", "PromptBuildContext"], Awaitable["PromptBuildResult | None"]]
] = []


def register_before_prompt_build_hook(
    hook: Callable[[dict, dict, "BrowserUseHookContext", "PromptBuildContext"], Awaitable["PromptBuildResult | None"]],
) -> None:
    """Register *hook* to be invoked during task-prompt assembly
    (prompt-build phase), after DOM event items have been extracted
    and compacted.

    Hook signature:
        ``hook(state, inputs, hook_ctx, prompt_ctx) -> PromptBuildResult | None``

    Returning ``None`` leaves the task / override text unchanged.
    Returning a ``PromptBuildResult`` with ``short_circuit_state`` set
    short-circuits the whole node (skips the LLM).  Otherwise the
    result's ``task_hint_append`` is appended to the task hint and
    ``override_prepend`` is prepended to the protocol override block.
    If any hook appends non-empty text (or short-circuits), the
    generic "compact_items snapshot" fallback injection is skipped.
    Registration is idempotent.
    """
    if hook not in _before_prompt_build_hooks:
        _before_prompt_build_hooks.append(hook)


# Late-phase hooks run AFTER the browser-use agent is constructed and
# its browser session is ready.  Use this for patterns that need the
# live agent / browser session (e.g. Feige's PreDispatch customer-
# message fan-out that reads the sidebar DOM via agent.browser_session).
_before_browser_use_run_hooks: list[
    Callable[[Any, dict, dict, "BrowserUseHookContext"], Awaitable[dict | None]]
] = []


def register_before_browser_use_run_hook(
    hook: Callable[[Any, dict, dict, "BrowserUseHookContext"], Awaitable[dict | None]],
) -> None:
    """Register *hook* to be invoked before the browser-use agent runs
    (late phase).

    Hook signature: ``hook(agent, state, inputs, hook_ctx)``.  Returning
    a non-None state dict short-circuits the LLM; returning ``None``
    lets the next hook run (or the LLM, if no more hooks).  Registration
    is idempotent: adding the same callable twice is a no-op.
    """
    if hook not in _before_browser_use_run_hooks:
        _before_browser_use_run_hooks.append(hook)


# ─── Phase 6.5: context dataclasses moved to browser_node.contexts ───
# Lifted 2026-04-24 to break the runner→build_node import cycle.  The
# four classes below are re-exported here for back-compat so external
# hook bundles (e.g. browser_use_extension/hooks/external/feige_chat)
# can continue to import them from their historical location.
from agent.ec_skills.browser_node.contexts import (
    BrowserUseHookContext,
    PromptBuildContext,
    PromptBuildResult,
    _AssignmentContext,
)


# ==================== Node Input Helpers ====================

class _SafeFormatDict(dict):
    """dict subclass for str.format_map() that returns "" for missing keys.

    Used when rendering user-authored templates where a referenced field
    may legitimately be empty or undefined.
    """
    def __missing__(self, key):
        return ""


def _parse_json_input(inputs: dict, key: str):
    """Read inputs[key].content and decode it as JSON.

    Accepts either a JSON string (the common Flowgram shape for textarea
    inputs) or a pre-parsed dict/list.  Returns ``None`` when absent or
    invalid so callers can use ``isinstance()`` checks without try/except.
    """
    raw = (inputs.get(key) or {}).get("content") if isinstance(inputs, dict) else None
    if raw is None or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception as err:
            logger.warning(f"[NodeInputs] Failed to parse '{key}' as JSON (non-fatal): {err}")
            return None
    return None


# ==================== Hot-Path Template Resolution ====================

def _resolve_template(template: str, payload: dict) -> str:
    """Resolve ``{{field}}`` or ``{{field1 || field2}}`` placeholders from *payload*.

    - ``{{customer_name}}`` → ``payload["customer_name"]``
    - ``{{customer_id || identity_key || customer_name}}`` → first non-empty value
    - Non-template strings (no ``{{``/``}}``) are returned as-is.
    """
    if not isinstance(template, str):
        return str(template) if template is not None else ""
    if not (template.startswith("{{") and template.endswith("}}")):
        return template
    inner = template[2:-2].strip()
    candidates = [c.strip() for c in inner.split("||")]
    for field_name in candidates:
        val = payload.get(field_name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


# ==================== Customer ID Normalization ====================

def _normalize_dispatch_identity_key(raw_id: str) -> str:
    """Normalize a customer ID by stripping the message-preview suffix.

    DOM extractor identity keys often look like ``"sc|有紫色款吗？"`` where
    the part after ``|`` is the latest message preview.  This changes every
    time a new message arrives, which breaks dedup and affinity caches.

    This function returns just the stable portion (everything before the
    first ``|``).  If there is no ``|`` or the result would be empty, the
    original string is returned stripped.
    """
    if not raw_id:
        return ""
    s = str(raw_id).strip()
    if "|" in s:
        prefix = s.split("|", 1)[0].strip()
        if prefix:
            return prefix
    return s


def _stale_input_has_undelivered_response_text(
    stale_input: Any,
    new_event_type: str,
) -> tuple[bool, str, str]:
    """Detect if a soon-to-be-cleared ``state["input"]`` carries a Q&A
    worker reply that HOT-PATH-B has not yet typed into Feige.

    Used by :func:`build_pend_for_event_node` to defend against an
    event-bus race where a chat_message resume populates
    ``state["input"]`` with ``response_text`` but the langgraph loops
    back to ``pend_event`` via condition nodes WITHOUT entering
    ``browser_automation_janWe`` (so HOT-PATH-B never fires).  The next
    non-chat_message resume would then permanently drop the reply via
    ``state.pop("input", None)``.

    Liveness incident 2026-04-28 (eCan.log around 12:19:50): customer
    ``cejs``'s "退货包邮吗" went silent for ~2 minutes this way.

    Returns ``(should_preserve, customer, response_text)``.  Caller is
    expected to put ``stale_input`` back into ``state["input"]`` iff
    ``should_preserve`` is ``True``.

    Heuristic: preserve iff
      * ``new_event_type`` is NOT ``chat_message`` (chat_message
        resumes re-populate ``state["input"]`` themselves),
      * ``stale_input`` parses as a JSON object with non-empty
        ``response_text`` and ``customer_name``/``customer_id``,
      * ``dispatch_state.was_recently_sent(...)`` is 0.0 (15 s TTL,
        i.e. HOT-PATH-B has NOT typed this reply recently).

    HOT-PATH-B has its own dedup guards downstream, so a false-positive
    (reply already typed but TTL not yet recorded) just becomes a
    ``dedup-skip`` — no duplicate sends.
    """
    if new_event_type == "chat_message":
        return False, "", ""
    if not stale_input:
        return False, "", ""
    try:
        import json as _json
        parsed = (
            _json.loads(stale_input)
            if isinstance(stale_input, str)
            else stale_input
        )
    except Exception:
        return False, "", ""
    if not isinstance(parsed, dict):
        return False, "", ""
    response_text = parsed.get("response_text")
    customer = parsed.get("customer_name") or parsed.get("customer_id")
    if not (
        isinstance(response_text, str) and response_text.strip()
        and isinstance(customer, str) and customer.strip()
    ):
        return False, "", ""
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dispatch_state as _ds,
        )
        recent_age = _ds.was_recently_sent(customer, response_text)
    except Exception:
        recent_age = 0.0
    if recent_age > 0.0:
        # HOT-PATH-B already typed this reply within the dedup TTL —
        # really stale, safe to drop.
        return False, customer, response_text
    return True, customer, response_text


# ==================== Lambda Proxy Helpers ====================

def _should_use_proxy(node_inputs: dict | None = None) -> bool:
    """Check if LLM calls should be routed through the Lambda proxy.

    Priority: node-level useProxy override > global use_lambda_proxy setting.
    """
    # 1. Check node-level override
    if node_inputs:
        use_proxy_val = (node_inputs.get("useProxy") or {}).get("content")
        if use_proxy_val is not None:
            return str(use_proxy_val).lower() in ('true', '1', 'yes', 'on')

    # 2. Fall back to global setting
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin and hasattr(mainwin, 'config_manager'):
            return mainwin.config_manager.general_settings.use_lambda_proxy
    except Exception:
        pass
    return False


def _get_proxy_config() -> dict:
    """Get Lambda proxy configuration from settings.

    Returns dict with: endpoint, auth_token, user_id (or empty dict if unavailable).
    """
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if not mainwin or not hasattr(mainwin, 'config_manager'):
            return {}
        endpoint = mainwin.config_manager.general_settings.lambda_proxy_endpoint
        if not endpoint:
            logger.warning("[build_node] Lambda proxy enabled but no endpoint configured")
            return {}
        auth_token = ''
        if hasattr(mainwin, 'get_auth_token'):
            auth_token = mainwin.get_auth_token() or ''
        user_id = getattr(mainwin, 'user', '') or ''
        return {
            'endpoint': endpoint,
            'auth_token': auth_token,
            'user_id': user_id,
        }
    except Exception as e:
        logger.warning(f"[build_node] Failed to get proxy config: {e}")
        return {}


# ==================== Module-level Constants ====================

# When a node has useThinking disabled, we still need a well-defined instruction
# to prevent providers/models that default to verbose reasoning from emitting it.
# This is appended to the system message via browser-use's `extend_system_message`.
THINKING_SUPPRESSION_INSTRUCTION = """
Answer concisely.

- Do not reveal hidden reasoning or chain-of-thought.
- If you need to think, do it silently and only provide the final answer.
"""

# ==================== Cloud-Direct Tool Registry ====================
# Maps MCP tool names -> (module_path, function_name) for tools that can be
# imported without triggering GUI dependencies (pyautogui, pynput, PyGetWindow)
# which are present in server.py but fail on headless Linux cloud workers.
_CLOUD_TOOL_REGISTRY: dict[str, tuple[str, str]] = {
    # AWS cost monitoring & shutdown
    "aws_read_billing": ("agent.mcp.server.aws_utils.aws_tools", "aws_read_billing"),
    "aws_shutdown": ("agent.mcp.server.aws_utils.aws_tools", "aws_shutdown"),
    # Azure cost monitoring & shutdown
    "azure_read_billing": ("agent.mcp.server.azure_utils.azure_tools", "azure_read_billing"),
    "azure_shutdown": ("agent.mcp.server.azure_utils.azure_tools", "azure_shutdown"),
    # GCP cost monitoring & shutdown
    "gcloud_read_billing": ("agent.mcp.server.gcloud_utils.gcloud_tools", "gcloud_read_billing"),
    "gcloud_shutdown": ("agent.mcp.server.gcloud_utils.gcloud_tools", "gcloud_shutdown"),
    # Code execution
    "run_code": ("agent.mcp.server.code_utils.code_tools", "async_run_code"),
    "run_shell_script": ("agent.mcp.server.code_utils.code_tools", "async_run_shell_script"),
    "grep_search": ("agent.mcp.server.code_utils.code_tools", "async_grep_search"),
    "find_files": ("agent.mcp.server.code_utils.code_tools", "async_find_files"),
    # RAG
    "ragify": ("agent.ec_skills.rag.local_rag_mcp", "ragify"),
    "rag_query": ("agent.ec_skills.rag.local_rag_mcp", "rag_query"),
    "wait_for_rag_completion": ("agent.ec_skills.rag.local_rag_mcp", "wait_for_rag_completion"),
    "ragify_async": ("agent.ec_skills.rag.local_rag_mcp", "ragify_async"),
    # Chat / communication
    "send_chat": ("agent.mcp.server.chat_utils.chat_tools", "async_send_chat"),
    "list_chat_agents": ("agent.mcp.server.chat_utils.chat_tools", "async_list_chat_agents"),
    "get_chat_history": ("agent.mcp.server.chat_utils.chat_tools", "async_get_chat_history"),
    # Self-introspection
    "describe_self": ("agent.mcp.server.self_utils.self_tools", "async_describe_self"),
    # Task management
    "launch_agent_task": ("agent.ec_tasks.task_mcp_tools", "async_launch_agent_task"),
    "create_agent_task_with_skill": ("agent.ec_tasks.task_mcp_tools", "async_create_agent_task_with_skill"),
    "schedule_agent_task": ("agent.ec_tasks.task_mcp_tools", "async_schedule_agent_task"),
    "delete_agent_task": ("agent.ec_tasks.task_mcp_tools", "async_delete_agent_task"),
    "stop_agent_task": ("agent.ec_tasks.task_mcp_tools", "async_stop_agent_task"),
    # Privacy
    "privacy_reserve": ("agent.mcp.server.Privacy.privacy_reserve", "privacy_reserve"),
}

# ==================== Module-level LLM + API Key Caches ====================
# Cache LLM instances per (provider, model, host, api_key_preview) so repeated
# invocations of the same LLM node don't pay the constructor + HTTP client setup
# cost every step.  Cache is invalidated when the skill graph re-compiles.
_LLM_INSTANCE_CACHE: dict[str, Any] = {}
_LLM_CACHE_TTL_SECONDS = 300.0  # Invalidate after 5 min to avoid stale credentials

# Cache resolved API keys per provider so we don't hit the LLM Manager / secure
# store on every tool call or LLM invocation.  Key = provider string.
_API_KEY_CACHE: dict[str, str] = {}
_API_KEY_CACHE_TTL_SECONDS = 120.0  # Re-resolve after 2 min

# Cache the LLM manager singleton so we don't call get_llm_manager() on every
# LLM invocation (each call parses settings.json and builds provider maps).
_LLM_MANAGER_CACHE: dict[str, Any] = {}  # key is always "" for the singleton slot

# Track the current skill execution ID so we can scope cache entries per execution
_CURRENT_SKILL_EXECUTION_ID: str | None = None


def _clear_module_caches():
    """Clear all module-level caches to prevent memory accumulation.

    Call this at the end of every skill execution.  Clears:
    - LLM instance cache
    - LLM manager cache
    - API key cache
    - Browser session cache
    - Passive agent cache
    - Persistent worker threads (stops them and removes references)

    Also resets the current skill execution ID so stale references can't
    accidentally leak into the next execution.
    """
    global _CURRENT_SKILL_EXECUTION_ID
    _CURRENT_SKILL_EXECUTION_ID = None

    # Clear LLM instance cache
    _LLM_INSTANCE_CACHE.clear()

    # Clear LLM manager cache
    _LLM_MANAGER_CACHE.clear()

    # Clear API key cache
    _API_KEY_CACHE.clear()

    # NOTE (Phase 6.7 hotfix, 2026-04-24): the previous block here cleared
    # browser-session caches AND stopped persistent worker threads.  It
    # had a latent NameError on ``_cached_browser_sessions`` (build-scope
    # local) that silently aborted the function before the worker-stop
    # ran, so in practice neither cache-clear nor worker-stop ever
    # executed.  Phase 6.7 fixed the NameError, which inadvertently
    # activated the worker-stop loop — every task completion now killed
    # ALL persistent worker threads, including ones executing concurrent
    # browser-automation tasks (CancelledError mid-await).
    #
    # The browser-session caches are intentionally long-lived (chat
    # sessions reused across customer interactions, ~860MB browser-use
    # agents kept hot).  The persistent workers are likewise designed to
    # outlive individual tasks.  Neither should be torn down per-task.
    # Leave them alone — module unload / process exit handles teardown.

    logger.debug("[build_node] Module-level LLM caches cleared")


def _resolve_cloud_tool_func(tool_name: str):
    """Resolve a tool handler function for cloud-direct invocation.

    Instead of importing ``tool_function_mapping`` from ``server.py`` (which
    pulls in GUI dependencies like *pynput*, *pyautogui*, and *PyGetWindow*
    that fail on headless Linux), this function lazily imports **only** the
    lightweight source module that defines the requested tool.

    Returns the callable tool handler, or ``None`` if the tool is not in the
    cloud-safe registry.
    """
    import importlib

    entry = _CLOUD_TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return None
    module_path, func_name = entry
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


# ==================== Helper Functions ====================
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
except ImportError:
    ChatGoogleGenerativeAI = None
try:
    from langchain_qwq import ChatQwQ
except ImportError:
    ChatQwQ = None
try:
    from langchain_community.chat_models import ChatZhipuAI
except ImportError:
    ChatZhipuAI = None
try:
    from langchain_aws import ChatBedrockConverse
except ImportError:
    ChatBedrockConverse = None

def get_default_node_schemas():
    schemas = {
        "llm" : {

        }
    }
    return schemas


def add_to_history(state, messages, max_entries: int = 200):
    """Append messages to state["history"] with automatic pruning.

    To prevent unbounded memory growth during long-running skill executions,
    the history is trimmed to the most recent ``max_entries`` items whenever
    it exceeds that threshold.
    """
    if not isinstance(state.get("history"), list):
        state["history"] = []

    if isinstance(messages, list):
        state["history"].extend(messages)
    else:
        state["history"].append(messages)

    # Prune to keep only the most recent entries
    if len(state["history"]) > max_entries:
        state["history"] = state["history"][-max_entries:]


def _is_qa_inbound_payload(payload) -> bool:
    """Return ``True`` when *payload* is a Q&A-worker inbound dispatch.

    Mirrors ``extension_tools_service._is_qa_dispatch`` so the inbound
    detection (Q&A worker side) and outbound rejection (front-desk side)
    use the same rule.  A Q&A *inbound* dispatch payload has BOTH
    ``customer_id`` and ``latest_message`` and lacks ``response_text``
    (which would mark it as a Q&A *reply* flowing back to front-desk).
    Returns ``False`` for non-dict payloads so callers can pass any
    parsed JSON value defensively.
    """
    if not isinstance(payload, dict):
        return False
    cust = str(payload.get("customer_id") or payload.get("customerId") or "").strip()
    latest = str(payload.get("latest_message") or "").strip()
    response = str(payload.get("response_text") or "").strip()
    return bool(cust and latest and not response)


def _parse_jsonish_dict(value) -> dict:
    """Best-effort parse for JSON dict payloads carried in state fields."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _state_current_event_human_payload(state: dict) -> dict:
    """Return the current turn's human payload from prompt_refs/events/input.

    Q&A replies are generated from a front-desk assignment payload.  That
    payload may carry Feige's source customer-bubble msg_id; we need to
    propagate it into the response envelope so the front desk can reject a
    stale answer if the customer sends a newer bubble before the LLM returns.
    """
    if not isinstance(state, dict):
        return {}

    candidates: list[object] = []

    pr_events = (state.get("prompt_refs") or {}).get("events", "")
    if isinstance(pr_events, str) and pr_events.strip():
        evt = _parse_jsonish_dict(pr_events)
        if evt:
            candidates.append(evt.get("human_text"))

    for evt in reversed(state.get("events") or []):
        if not isinstance(evt, dict):
            continue
        data = evt.get("data") or {}
        if isinstance(data, dict):
            candidates.append(data.get("human_text"))

    candidates.append(state.get("input", ""))

    for msg in reversed(state.get("history") or []):
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            candidates.append(content)

    for candidate in candidates:
        parsed = _parse_jsonish_dict(candidate)
        if parsed:
            return parsed
    return {}


def _augment_send_chat_reply_with_source_turn(actual_tool_input, state: dict):
    """Attach source customer-bubble metadata to Q&A send_chat replies.

    The Q&A prompt intentionally keeps the visible `message` JSON small.
    This hidden runtime enrichment preserves turn correlation without asking
    the LLM to remember or emit extra fields.
    """
    if not isinstance(actual_tool_input, dict):
        return actual_tool_input

    target = actual_tool_input.get("input")
    if not isinstance(target, dict) or "message" not in target:
        target = actual_tool_input
    if not isinstance(target, dict):
        return actual_tool_input

    msg_text = target.get("message")
    msg_obj = _parse_jsonish_dict(msg_text)
    if not msg_obj or not str(msg_obj.get("response_text") or "").strip():
        return actual_tool_input

    inbound = _state_current_event_human_payload(state)
    if not _is_qa_inbound_payload(inbound):
        return actual_tool_input

    source_msg_id = str(
        inbound.get("source_customer_msg_id")
        or inbound.get("latest_message_msg_id")
        or inbound.get("reply_to_msg_id")
        or ""
    ).strip()
    if not source_msg_id:
        return actual_tool_input

    out_cust = str(
        msg_obj.get("customer_id")
        or msg_obj.get("customer_name")
        or ""
    ).strip()
    in_cust = str(
        inbound.get("customer_id")
        or inbound.get("customer_name")
        or ""
    ).strip()
    try:
        if out_cust and in_cust:
            if _normalize_dispatch_identity_key(out_cust) != _normalize_dispatch_identity_key(in_cust):
                logger.warning(
                    "[MCP Auto-Select] Not attaching source_customer_msg_id: "
                    f"response customer {out_cust!r} != inbound customer {in_cust!r}"
                )
                return actual_tool_input
    except Exception:
        if out_cust and in_cust and out_cust != in_cust:
            return actual_tool_input

    if not msg_obj.get("source_customer_msg_id"):
        msg_obj["source_customer_msg_id"] = source_msg_id
    latest_text = str(inbound.get("latest_message") or "").strip()
    if latest_text and not msg_obj.get("source_latest_message"):
        msg_obj["source_latest_message"] = latest_text

    target["message"] = json.dumps(msg_obj, ensure_ascii=False, separators=(",", ":"))
    logger.info(
        "[MCP Auto-Select] Attached source_customer_msg_id to send_chat "
        f"reply for customer={out_cust or in_cust!r} msg_id=...{source_msg_id[-8:]}"
    )
    return actual_tool_input


def _reset_qa_history_on_customer_change(
    state: dict,
    payload,
    *,
    node_name: str = "",
    logger_=None,
) -> bool:
    """Per-customer ``state["history"]`` isolation for Q&A workers.

    Production incident 2026-04-27: a Q&A worker (e.g. ``飞鸽客户应答``)
    handling multiple customers via round-robin dispatch echoed one
    customer's answer onto another customer's chat tab.  Symptom:
    customer B asked "转人工", but the bot typed
    "您好，红色款是否有货需要帮您核实一下…" into B's tab — that answer
    belonged to customer A who had asked "有红色的吗？".

    Root cause: ``state["history"]`` is shared across all dispatches to
    the same agent (the LangGraph state is per chatter-task, and the
    chatter task is per-agent, not per-customer).  When customer A's
    ``(HumanMessage, AIMessage)`` pair was still in history at the
    moment customer B's HumanMessage arrived, the LLM weighted the
    prior turn heavily and produced an answer shaped by A's turn.
    The Q&A worker's prompt explicitly instructs "忽略历史，只看本轮的
    ``{{input}}``" but the model didn't fully comply.

    This helper detects an inbound Q&A dispatch payload (via
    :func:`_is_qa_inbound_payload`) and, when the ``customer_id`` has
    changed since the last call, clears ``state["history"]`` so the LLM
    can't reach across customer boundaries.  The new ``customer_id`` is
    recorded in ``state["attributes"]["_last_qa_customer_id"]``.

    Returns ``True`` when a reset was performed (so callers / tests
    can assert), ``False`` otherwise.

    NOTE: deliberately does NOT touch front-desk inbound traffic —
    front-desk receives Q&A *replies* (which carry ``response_text``)
    and browser events (which never look like a dispatch), neither of
    which trip :func:`_is_qa_inbound_payload`.  Front-desk legitimately
    tracks multi-customer state in its history.
    """
    try:
        if not _is_qa_inbound_payload(payload):
            return False
        cust = str(
            payload.get("customer_id") or payload.get("customerId") or ""
        ).strip()
        attrs = state.setdefault("attributes", {}) if isinstance(state, dict) else {}
        if not isinstance(attrs, dict):
            # Should never happen — defensive against malformed state.
            return False
        last_cust = str(attrs.get("_last_qa_customer_id") or "").strip()
        did_reset = False
        if last_cust and last_cust != cust:
            hist_len = (
                len(state["history"])
                if isinstance(state.get("history"), list)
                else 0
            )
            state["history"] = []
            # Drop the per-turn ``prompts`` accumulator too —
            # ``standard_post_llm_hook`` extends it with the AIMessage of
            # each turn; clearing keeps state tidy and prevents
            # memory-monitor false alarms.
            if isinstance(state.get("prompts"), list):
                state["prompts"] = []
            did_reset = True
            if logger_ is not None:
                logger_.info(
                    f"[{node_name}] Q&A history reset on customer change: "
                    f"prev={last_cust!r} -> new={cust!r} "
                    f"(cleared {hist_len} prior history entries)"
                )
        attrs["_last_qa_customer_id"] = cust
        return did_reset
    except Exception as exc:
        if logger_ is not None:
            logger_.debug(
                f"[{node_name}] Q&A history isolation skipped: {exc}"
            )
        return False


STANDARD_SYS_PROMPT = "You are a helpful AI assistant."
BROWSER_AUTOMATION_SYS_PROMPT = "You are a helpful browser automation agent."


def _load_prompt_data(selection: str, skill_owner: str = "") -> tuple[dict | None, Any]:
    """
    Load prompt data either from cloud (DynamoDB) or local (GUI prompt_handler).

    Args:
        selection: prompt ID to load
        skill_owner: email of the skill's original author.  When running
            someone else's skill the prompt lives under *their* DynamoDB
            partition, not the runner's.  If empty, falls back to the
            current cloud context owner or local prompts.

    Returns:
        (prompt_data, normalizer_module) - prompt_data is the raw prompt dict,
        normalizer_module has _normalize_prompt function
    """
    # First, check if we're in cloud context
    try:
        from agent.cloud.cloud_prompt_loader import (
            get_cloud_prompt_context,
            get_cloud_prompt_loader,
            _normalize_prompt as cloud_normalize_prompt,
        )
        
        cloud_ctx = get_cloud_prompt_context()
        if cloud_ctx is not None:
            # Determine which owner to query — prefer explicit skill_owner
            effective_owner = skill_owner or cloud_ctx.owner_id
            logger.warning(f"[prompts] ⚠️ CLOUD PROMPT LOADING ACTIVE - Using cloud prompt loader for selection '{selection}' owner='{effective_owner}'")
            send_skill_editor_log("warning", f"[prompts] Loading prompt '{selection}' from CLOUD (may be stale)")
            loader = get_cloud_prompt_loader(
                owner_id=effective_owner,
                region=cloud_ctx.region,
                table_name=cloud_ctx.table_name,
            )
            prompt_data = loader.get_prompt_by_id(selection)
            if prompt_data:
                logger.warning(f"[prompts] ⚠️ Loaded prompt '{selection}' from CLOUD - this may override your local version")
                send_skill_editor_log("warning", f"[prompts] Loaded prompt from CLOUD (not local file)")
            
            # Create a simple normalizer wrapper
            class CloudNormalizer:
                @staticmethod
                def _normalize_prompt(data, *, source, read_only, last_modified_ts):
                    return cloud_normalize_prompt(data, source=source, read_only=read_only, last_modified_ts=last_modified_ts)
            
            return prompt_data, CloudNormalizer
    except ImportError:
        pass  # Cloud loader not available
    except Exception as e:
        logger.warning(f"[prompts] Cloud prompt loading failed: {e}")
    
    # Fall back to local GUI prompt_handler
    try:
        from gui.ipc.w2p_handlers import prompt_handler
        prompts = prompt_handler._load_all_prompts()
        prompt_data = next((p for p in prompts if p.get("id") == selection), None)

        # If not found locally and we have a skill_owner, try fetching from
        # cloud under the skill owner's partition (free-skill auto-download).
        if prompt_data is None and skill_owner:
            try:
                from gui.ipc.w2p_handlers.prompt_cloud_sync import _get_cloud_context, _appsync_request
                import json as _json
                ctx = _get_cloud_context()
                if ctx:
                    query = """
                        query QueryPrompts($input: PromptQueryInput) {
                            queryPrompts(input: $input) { id owner prompt version }
                        }
                    """
                    resp = _appsync_request(query, ctx, variables={"input": {"id": selection, "owner": skill_owner}})
                    items = (resp.get("data") or {}).get("queryPrompts") or []
                    if items:
                        raw = items[0].get("prompt", "{}")
                        pdata = _json.loads(raw) if isinstance(raw, str) else raw
                        if isinstance(pdata, dict):
                            pdata["id"] = selection
                        prompt_data = pdata
                        logger.info(f"[prompts] Fetched prompt '{selection}' from cloud (skill_owner={skill_owner})")
            except Exception as fetch_exc:
                logger.debug(f"[prompts] Cloud fallback for skill_owner prompt failed: {fetch_exc}")

        return prompt_data, prompt_handler
    except ImportError:
        # PySide6 not available
        logger.warning(f"[prompts] Neither cloud context nor GUI prompt_handler available")
        return None, None
    except Exception as e:
        logger.warning(f"[prompts] Failed to load prompts: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Prompt template helpers (used by _resolve_prompt_templates and other nodes)
# ---------------------------------------------------------------------------

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


def _schema_to_dict(schema: Any) -> dict:
    if hasattr(schema, 'model_dump'):
        return schema.model_dump()
    if isinstance(schema, dict):
        return schema
    return {
        'name': getattr(schema, 'name', ''),
        'description': getattr(schema, 'description', ''),
        'inputSchema': getattr(schema, 'inputSchema', {}),
    }


def _get_all_tool_schemas() -> list:
    """Fetch all tool schemas, working in both GUI and cloud-worker contexts."""
    all_schemas = []

    # 1) GUI context (main window registry)
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        all_schemas = getattr(mainwin, 'mcp_tools_schemas', None) or []
    except Exception:
        all_schemas = []

    # 2) Cloud/no-GUI context fallback (server-side registry)
    if not all_schemas:
        try:
            from agent.mcp.server.tool_schemas import get_tool_schemas
            all_schemas = get_tool_schemas() or []
            logger.debug(f"[_get_all_tool_schemas] Loaded {len(all_schemas)} schemas from MCP server registry")
        except Exception as e:
            logger.warning(f"[_get_all_tool_schemas] Failed to load schemas from MCP server registry: {e}")
            all_schemas = []

    return all_schemas


def _get_tool_schemas_for_names(tool_names: list[str]) -> list[dict]:
    """Fetch full tool schemas for the given tool names from MCP registry."""
    try:
        all_schemas = _get_all_tool_schemas()
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
                    result.append(_schema_to_dict(schema))
                    break
        return result
    except Exception as e:
        logger.warning(f"Failed to get tool schemas: {e}")
        return []


def _is_tools_schema_placeholder(raw: str) -> bool:
    txt = str(raw or '').strip()
    if not txt:
        return False
    return bool(re.fullmatch(r'\{\{\s*tools_schema\s*\}\}', txt, re.IGNORECASE))


def _format_tools_to_use_section(items: list[str]) -> str:
    """Format tools_to_use section with full tool schemas instead of just names."""
    include_all_schemas = False

    # Collect all tool names from items
    all_tool_names = []
    seen = set()
    for item in items:
        if _is_tools_schema_placeholder(item):
            include_all_schemas = True
            continue
        for name in _parse_tools_to_use_item(item):
            if name not in seen:
                seen.add(name)
                all_tool_names.append(name)

    logger.debug(f"[_format_tools_to_use_section] Parsed tool names: {all_tool_names}")

    if not all_tool_names and not include_all_schemas:
        logger.debug("[_format_tools_to_use_section] No tool names found, returning empty")
        return ""

    # Get full schemas
    if include_all_schemas:
        all_schemas = _get_all_tool_schemas()
        schemas = [_schema_to_dict(s) for s in all_schemas]
        logger.debug(f"[_format_tools_to_use_section] Expanded {{tools_schema}} to {len(schemas)} schemas")
    else:
        schemas = _get_tool_schemas_for_names(all_tool_names)
        logger.debug(f"[_format_tools_to_use_section] Got {len(schemas)} schemas for {len(all_tool_names)} tool names")

    if not schemas:
        if include_all_schemas:
            logger.warning("[_format_tools_to_use_section] {{tools_schema}} requested but no schemas found")
            return ""
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


# ─────────────────────────────────────────────────────────────────────────────
# Native function-calling support (Step 1 pilot — opt-in QA worker migration)
#
# Background: until 2026-04, MCP auto-select nodes relied entirely on parsing
# the LLM's free-text JSON output to extract ``tool_name``/``tool_input``.  This
# proved fragile — gpt-5/o-series models occasionally slip into the OpenAI
# Harmony channel format (``to=send_chat ... =json\n{...}``), causing the
# strict parser to silently drop tool calls.  Liveness incident 2026-04-29 lost
# customer ``陆地飞鱼``'s reply this way.
#
# The structurally-correct fix is to use the LLM provider's native tool/function
# calling API — i.e. pass the MCP tool schemas via ``bind_tools`` and read the
# typed ``response.tool_calls`` field instead of re-parsing free-text content.
# Format slips in a structured channel are impossible.
#
# This helper set is the OPT-IN bridge for the pilot rollout:
#   * gate by env ``ECAN_NATIVE_TOOL_CALLS=1`` or skill mapping_rules
#     ``use_native_tool_calls=true``
#   * applies only when the LLM node has a non-empty ``tools_to_use`` section
#   * falls back transparently to the legacy text-parse path (incl. the
#     Harmony fallback added in the same incident response) when:
#       - the gate is off
#       - the provider does not expose ``bind_tools``
#       - the LLM responds without a ``tool_calls`` field
# ─────────────────────────────────────────────────────────────────────────────

# Observability counters (Step 2): in-memory metric for how often the native
# path is exercised vs the legacy text-parse path.  Persistent stats are out
# of scope for the pilot — these counters are read by tests and surfaced via
# the ``[NativeToolCalls]`` log lines below.
_NATIVE_TOOL_CALL_METRICS: dict[str, int] = {
    "bind_attempted": 0,        # native binding decision was reached
    "bind_succeeded": 0,        # bind_tools call returned without raising
    "bind_skipped_gate": 0,     # gate was off
    "bind_skipped_no_tools": 0, # no tools_to_use names resolved
    "bind_skipped_proxy": 0,    # Lambda proxy LLM (no native binding)
    "bind_skipped_unsupported": 0,  # LLM lacked bind_tools attr
    "bind_failed": 0,           # bind_tools raised
    "response_native": 0,       # LLM returned typed tool_calls
    "response_text_fallback": 0, # bound LLM returned no tool_calls (fell back)
}


def _native_tool_call_metric_inc(key: str, n: int = 1) -> None:
    """Increment a native-tool-calls metric; never raises."""
    try:
        _NATIVE_TOOL_CALL_METRICS[key] = _NATIVE_TOOL_CALL_METRICS.get(key, 0) + n
    except Exception:
        pass


def get_native_tool_call_metrics() -> dict:
    """Return a snapshot of the native-tool-calls observability counters."""
    try:
        return dict(_NATIVE_TOOL_CALL_METRICS)
    except Exception:
        return {}


def _extract_tools_to_use_names(
    prompt_selection: str,
    inline_system: str,
    *,
    skill_owner: str = "",
) -> list[str]:
    """Return the flat list of MCP tool names declared in ``tools_to_use``
    sections of the resolved prompt.

    Used by the native function-calling bridge to know which tools to pass to
    ``llm.bind_tools(...)``.  When the prompt uses the ``{{tools_schema}}``
    placeholder, returns the names of ALL registered MCP tools.

    Returns an empty list when the prompt has no structured ``tools_to_use``
    section (e.g. inline-only prompts that embed tool docs in free text).  The
    caller treats empty-list as "skip native binding, use legacy text parse".
    """
    selection = (prompt_selection or "inline").strip()
    if selection in ("", "inline"):
        # Inline prompts don't expose a structured tools_to_use list.  Native
        # binding is opt-in only for promptId-based flows during the pilot.
        return []

    try:
        prompt_data, normalizer = _load_prompt_data(selection, skill_owner=skill_owner)
    except Exception:
        return []
    if not prompt_data:
        return []

    normalized = prompt_data
    # Accept any of the three section-bearing keys without requiring
    # normalization.  Fall back to the normalizer (if available) only when
    # none of them is present.
    _has_any_sections = isinstance(normalized, dict) and any(
        normalized.get(k) for k in ("sections", "systemSections", "userSections")
    )
    if not _has_any_sections:
        if normalizer is None:
            return []
        try:
            normalized = normalizer._normalize_prompt(
                prompt_data,
                source=str(prompt_data.get("source") or "inline"),
                read_only=bool(prompt_data.get("readOnly")),
                last_modified_ts=None,
            )
        except Exception:
            return []

    names: list[str] = []
    seen: set[str] = set()

    def _consume_section(sec: dict) -> bool:
        """Return True if a {{tools_schema}} placeholder was hit (=> bind ALL)."""
        items = sec.get("items") if isinstance(sec.get("items"), list) else []
        for item in items:
            if _is_tools_schema_placeholder(item):
                return True
            for n in _parse_tools_to_use_item(item):
                if n and n not in seen:
                    seen.add(n)
                    names.append(n)
        return False

    bind_all = False
    for section_key in ("sections", "systemSections", "userSections"):
        for sec in (normalized.get(section_key) or []):
            if not isinstance(sec, dict):
                continue
            if str(sec.get("type") or "").strip().lower() != "tools_to_use":
                continue
            if _consume_section(sec):
                bind_all = True

    if bind_all:
        all_names: list[str] = []
        seen_all: set[str] = set()
        for s in (_get_all_tool_schemas() or []):
            sn = getattr(s, "name", None) or (s.get("name") if isinstance(s, dict) else None)
            if sn and sn not in seen_all:
                seen_all.add(sn)
                all_names.append(sn)
        # Merge any explicitly-listed names too (defensive).
        for n in names:
            if n not in seen_all:
                seen_all.add(n)
                all_names.append(n)
        return all_names

    return names


def _schemas_to_function_tools(schemas: list[dict]) -> list[dict]:
    """Convert MCP tool schemas (``{name, description, inputSchema}``) into the
    OpenAI/LangChain function-tool dict shape expected by ``bind_tools``:

        {"type": "function",
         "function": {"name": ..., "description": ..., "parameters": <JSONSchema>}}

    LangChain ``BaseChatModel.bind_tools`` accepts this dict shape directly and
    translates it into each provider's native tool-call protocol (OpenAI tools
    parameter, Anthropic tool_use blocks, Bedrock Converse toolConfig, etc.).
    """
    out: list[dict] = []
    for s in schemas or []:
        if not isinstance(s, dict):
            continue
        name = s.get("name")
        if not name:
            continue
        params = s.get("inputSchema") or {"type": "object", "properties": {}}
        # Normalize: providers expect a JSONSchema object with a top-level
        # ``type`` key.  MCP schemas already comply, but defensively coerce.
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        if "type" not in params:
            params = {"type": "object", **params}
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": s.get("description") or "",
                "parameters": params,
            },
        })
    return out


def _should_use_native_tool_calls(
    skill_name: str,
    mainwin: Any,
    inputs: dict | None = None,
) -> bool:
    """Decide whether the native function-calling path is enabled for this
    skill/node invocation.

    Order of precedence (first match wins):
      1. Node-level inputs flag ``useNativeToolCalls`` (truthy)
      2. Env override ``ECAN_NATIVE_TOOL_CALLS`` set to a truthy value
      3. Skill-level ``mapping_rules.use_native_tool_calls`` truthy
      4. Default: False
    """
    # 1. Node config
    try:
        if isinstance(inputs, dict):
            v = inputs.get("useNativeToolCalls")
            if isinstance(v, bool) and v:
                return True
            if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "on"):
                return True
    except Exception:
        pass

    # 2. Env override
    try:
        env_val = os.getenv("ECAN_NATIVE_TOOL_CALLS", "").strip().lower()
        if env_val in ("1", "true", "yes", "on"):
            return True
        if env_val in ("0", "false", "no", "off"):
            return False  # explicit disable beats skill-level enable
    except Exception:
        pass

    # 3. Skill mapping_rules
    try:
        if mainwin and skill_name:
            for sk in (getattr(mainwin, "agent_skills", None) or []):
                if getattr(sk, "name", "") != skill_name:
                    continue
                mr = getattr(sk, "mapping_rules", None) or {}
                if isinstance(mr, dict):
                    flag = mr.get("use_native_tool_calls")
                    if isinstance(flag, bool):
                        return flag
                    if isinstance(flag, str) and flag.strip().lower() in ("1", "true", "yes", "on"):
                        return True
                break
    except Exception:
        pass

    return False


def _resolve_prompt_templates(prompt_selection: str, inline_system: str, inline_user: str, *, skill_owner: str = "") -> tuple[str, str, dict]:
    """Resolve system/user prompt templates based on selection.

    Args:
        skill_owner: original author email — passed to _load_prompt_data so
            prompts belonging to another user's skill can be resolved.

    Returns:
        (system_text, user_text, prompt_variables) where prompt_variables is
        a dict of variable declarations from the prompt JSON's "variables" field.
    """
    selection = (prompt_selection or "inline").strip()
    logger.info(f"[_resolve_prompt_templates] 🔍 selection='{selection}', inline_system={len(inline_system)} chars, inline_user={len(inline_user)} chars")
    
    if selection in ("", "inline"):
        logger.info(f"[_resolve_prompt_templates] ↩️ Using inline prompts (selection is empty or 'inline')")
        return inline_system, inline_user, {}

    # Load prompt data from cloud or local
    logger.info(f"[_resolve_prompt_templates] 📂 Loading prompt data for '{selection}', skill_owner='{skill_owner}'")
    prompt_data, normalizer = _load_prompt_data(selection, skill_owner=skill_owner)
    
    if not prompt_data:
        logger.warning(f"[_resolve_prompt_templates] ❌ Prompt selection '{selection}' not found. Falling back to inline prompts.")
        send_skill_editor_log("warning", f"Prompt '{selection}' not found, using inline prompts")
        return inline_system, inline_user, {}
    
    logger.info(f"[_resolve_prompt_templates] ✅ Loaded prompt data for '{selection}'")

    normalized = prompt_data
    if not isinstance(normalized, dict) or "sections" not in normalized:
        if normalizer is None:
            logger.warning(f"No normalizer available for prompt '{selection}'. Falling back to inline prompts.")
            return inline_system, inline_user, {}
        try:
            normalized = normalizer._normalize_prompt(
                prompt_data,
                source=str(prompt_data.get("source") or "inline"),
                read_only=bool(prompt_data.get("readOnly")),
                last_modified_ts=None,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(f"Failed to normalize prompt '{selection}': {exc}")
            return inline_system, inline_user, {}

    sys_parts: list[str] = []

    def _add_section(parts: list[str], title: str | None, content: str) -> None:
        clean = content.strip()
        if not clean:
            return
        if title:
            parts.append(f"[{title}]\n{clean}")
        else:
            parts.append(clean)

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

    # When tools are provided, append structured output format instructions so the LLM
    # returns JSON with tool_name instead of hallucinating tool calls as free-form text.
    if tools_to_use_added:
        _tool_output_format = (
            "[Output Format]\n"
            "You MUST always respond with valid JSON (no markdown fences, no extra text outside the JSON).\n"
            "When you want to call a tool, return:\n"
            '{"message": "<brief explanation to the user>", "tool_name": "<exact tool name from the list above>", '
            '"tool_input": {"input": {<tool parameters>}}}\n'
            "When you are just chatting (no tool call), return:\n"
            '{"message": "<your response to the user>"}\n'
            "CRITICAL RULES:\n"
            "- NEVER fabricate or imagine tool results. You MUST return the tool_name and tool_input and WAIT for the system to execute the tool.\n"
            "- NEVER include fake tool output in your message. The system will run the tool and provide the real result.\n"
            "- If the user confirms an action (e.g. says 'proceed', 'yes', 'go ahead'), call the tool immediately — do NOT describe what you would do."
        )
        sys_parts.append(_tool_output_format)

    system_text = "\n\n".join(part for part in sys_parts if part) or inline_system

    # Check if mdContent exists (markdown mode) - if so, use it directly and skip structured sections
    md_content = str(normalized.get("mdContent") or "").strip()
    if md_content:
        logger.warning(f"[_resolve_prompt_templates] ✅ Using mdContent for user prompt (markdown mode, {len(md_content)} chars)")
        logger.warning(f"[_resolve_prompt_templates] mdContent preview: {md_content[:200]}...")
        send_skill_editor_log("log", f"[_resolve_prompt_templates] Using mdContent ({len(md_content)} chars)")
        user_text = md_content
    else:
        # Structured sections mode (JSON format)
        logger.warning(f"[_resolve_prompt_templates] ⚠️ No mdContent, using structured sections")
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
            # Fallback to humanInputs if userSections is empty (DEPRECATED - should use mdContent instead)
            logger.warning(f"[_resolve_prompt_templates] ⚠️ Falling back to humanInputs (deprecated)")
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

    # Extract prompt-level variable declarations for cascading resolution
    prompt_variables = {}
    raw_vars = normalized.get("variables") or prompt_data.get("variables") or []
    if isinstance(raw_vars, list):
        for v in raw_vars:
            if isinstance(v, dict) and v.get("name"):
                prompt_variables[v["name"]] = v
    elif isinstance(raw_vars, dict):
        prompt_variables = raw_vars
    if prompt_variables:
        logger.debug(f"[_resolve_prompt_templates] Extracted {len(prompt_variables)} prompt-level variables: {list(prompt_variables.keys())}")

    return system_text, user_text, prompt_variables


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
def _mustache_escape(s: str) -> str:
    """Mustache HTML-escape: & < > " ' / ="""
    return (s
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
        .replace('/', '&#x2F;')
        .replace('=', '&#x3D;'))


def _render_mustache_section(section_text: str, data: Any, state: dict, mainwin) -> str:
    """
    Recursively render a Mustache section block.
    
    Handles:
    - {{#name}}...{{/name}}  : block section (truthy → render body, falsy → empty)
    - {{#name}}...{{.}}{{/name}} : iterate over list, {{.}} = current item
    - {{#name}}{{field}}{{/name}} : nested field extraction
    - {{.}}                 : current value (when iterating)
    - {{name}}               : variable substitution (pre-resolved via state)
    
    IMPORTANT: Even when data is falsy, we must render the body to handle nested sections.
    Nested sections will be processed and removed by _resolve_sections_recursive later.
    """
    # --- List iteration (Mustache spec) ---
    if isinstance(data, (list, tuple)):
        out = []
        for item in data:
            out.append(_render_mustache_section(section_text, item, state, mainwin))
        return "".join(out)

    # --- Falsy section data: render body anyway to handle nested sections, then return empty ---
    # This ensures nested {{#section}}{{/section}} tags are properly processed and removed
    if not data:
        # Render the body to process any nested sections
        rendered = _resolve_sections_recursive(section_text, {}, state, mainwin)
        # Return empty string per Mustache spec for falsy section data
        return ""

    # --- Dict section body ---
    return _render_mustache_block(section_text, data, state, mainwin)


def _render_mustache_block(block: str, ctx: Any, state: dict, mainwin) -> str:
    """
    Render a Mustache block (section body) against `ctx` (a dict or scalar).
    
    Scans the block for:
      {{#name}}...{{/name}}   — nested section
      {{^name}}...{{/name}}   — inverted section
      {{.}}"                   — current value reference
      {{name}} or {{name.path}} — variable
      {{{unescaped}}}          — unescaped HTML
    """
    import re as _re2

    result = []
    i = 0
    n = len(block)
    _max_iterations = 10000  # Safety limit to prevent infinite loops

    for _iter in range(_max_iterations):
        # Find next mustache tag opening {{
        m = _re2.search(r'\{\{', block[i:])
        if not m:
            result.append(block[i:])
            break

        result.append(block[i:i + m.start()])
        tag_start = i + m.start()
        tag_end = tag_start + 2  # skip {{

        # Determine opening sequence: {{ or {{{
        if block[tag_end:tag_end + 2] == '{{':
            raw_tag_start = tag_end + 2
            raw_tag_end = block.find('}}}', raw_tag_start)
            if raw_tag_end != -1:
                raw_tag = block[raw_tag_start:raw_tag_end].strip()
                is_unescaped = False
                i = raw_tag_end + 3
            else:
                # Fallback: treat as single brace
                raw_tag_start = tag_end
                raw_tag_end = block.find('}}', raw_tag_start)
                if raw_tag_end != -1:
                    raw_tag = block[raw_tag_start:raw_tag_end].strip()
                    is_unescaped = False
                    i = raw_tag_end + 2
                else:
                    result.append(block[tag_start])
                    i = tag_start + 1
                    continue
        elif block[tag_end:tag_end + 1] == '{':
            # {{{unescaped}}} detected by triple brace
            raw_tag_start = tag_end + 1
            raw_tag_end = block.find('}}}', raw_tag_start)
            if raw_tag_end != -1:
                raw_tag = block[raw_tag_start:raw_tag_end].strip()
                is_unescaped = True
                i = raw_tag_end + 3
            else:
                result.append(block[tag_start])
                i = tag_start + 1
                continue
        else:
            # Normal {{...}}
            raw_tag_start = tag_end
            raw_tag_end = block.find('}}', raw_tag_start)
            if raw_tag_end != -1:
                raw_tag = block[raw_tag_start:raw_tag_end].strip()
                is_unescaped = False
                i = raw_tag_end + 2
            else:
                result.append(block[tag_start])
                i = tag_start + 1
                continue

        # Parse the raw tag
        raw_tag = raw_tag.strip()
        is_inverted = False
        if raw_tag.startswith('#'):
            seg = raw_tag[1:].strip()
            is_inverted = False
        elif raw_tag.startswith('^'):
            seg = raw_tag[1:].strip()
            is_inverted = True
        elif raw_tag.startswith('/'):
            # Closing tag — skip (handled by section-level recursion)
            continue
        elif raw_tag == '.':
            # {{.}} — current value
            val = _mustache_get(ctx, None)
            rendered = _mustache_escape(str(val)) if not is_unescaped else str(val)
            result.append(rendered)
            continue
        else:
            seg = raw_tag

        # Determine section name and trailing path
        seg = seg.strip()
        if '.' in seg:
            section_name, field_path = seg.split('.', 1)
            section_name = section_name.strip()
            field_path = field_path.strip()
        else:
            section_name = seg
            field_path = None

        # Collect section body
        depth = 1
        search_start = i
        section_body = ""
        while depth > 0 and search_start < n:
            # Find next opening or closing tag for this section
            next_open = _re2.search(r'\{\{#' + _re2.escape(section_name) + r'\b|\{\{\^' + _re2.escape(section_name) + r'\b|\{\{/' + _re2.escape(section_name) + r'\b', block[search_start:])
            if not next_open:
                section_body += block[search_start:]
                break
            body_end = search_start + next_open.start()
            tag_content = next_open.group()[2:-2]  # strip {{ and }} from {{tag}} or {{{tag}}}
            section_body += block[search_start:body_end]
            if tag_content.startswith('/'):
                depth -= 1
                if depth == 0:
                    i = body_end + len(next_open.group())
                    break
            else:
                depth += 1
            search_start = body_end + len(next_open.group())
        else:
            # depth > 0 but search exhausted — unmatched opener, advance past it to prevent loop
            if depth > 0:
                # Find the opening tag for this section
                opener_match = _re2.search(r'\{\{#' + _re2.escape(section_name) + r'\b|\{\{\^' + _re2.escape(section_name) + r'\b', block[i:])
                if opener_match:
                    opener_end = i + opener_match.start() + opener_match.end() - opener_match.start()
                    result.append(block[i:opener_end])
                    i = opener_end

        # Get section data
        if field_path:
            section_data = _mustache_get(ctx, field_path)
        else:
            section_data = _mustache_get(ctx, section_name)

        # Render
        if is_inverted:
            if not section_data or (isinstance(section_data, (list, tuple)) and len(section_data) == 0):
                result.append(_render_mustache_section(section_body, True, state, mainwin))
        else:
            rendered = _render_mustache_section(section_body, section_data, state, mainwin)
            result.append(rendered)
    else:
        # Safety: max iterations reached, append remaining text
        result.append(block[i:])

    return "".join(result)


def _mustache_get(data: Any, path: str | None) -> Any:
    """Get value from data by dot-separated path. None if not found."""
    if path is None:
        return data
    if data is None:
        return None
    if not isinstance(data, dict):
        return None
    parts = path.split('.')
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _resolve_mustache_template(template: str, state: dict, mainwin=None) -> str:
    """Resolve Mustache-style templates including deeply-nested {{#section}}{{.}}{{/section}} patterns.

    Supports:
    - Simple:      {{query}}                       → tool_result resolution
    - Section:     {{#node}}{{field}}{{/node}}     → nested field
    - Iterate:     {{#list}}{{.}}{{/list}}         → list iteration with current item
    - Deep nested: {{#a}}{{#b}}{{c}}{{/b}}{{/a}}   → multi-level nesting
    - Dot path:    {{product_profile.product_name}} → nested field shortcut
    """
    if not template or "{{" not in template:
        return template
    # Safety: skip templates larger than 1MB to prevent regex/stack overflow
    if len(template) > 1_000_000:
        logger.warning(f"[Mustache] Template too large ({len(template)} chars), skipping resolution")
        return template

    # Normalize escape sequences: JSON stores \\n as literal backslash-n.
    # We need actual newlines for the regex to match across lines.
    _normalized = template.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')

    from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables
    import re as _re

    # Extract all unique variable names used in the template
    # IMPORTANT: Exclude closing tags like {{/llm_planner}} which should NOT be replaced
    _simple_vars = _re.findall(r'\{\{(\w+)\}\}', _normalized)
    # Filter out closing section tags (they start with / like {{/llm_planner}})
    _simple_vars = [v for v in _simple_vars if not v.startswith('/')]

    # Handle simple dot notation: {{node.field}}
    _dot_vars = _re.findall(r'\{\{(\w+(?:\.\w+)*)\}\}', _normalized)
    _dot_only_vars = [v for v in _dot_vars if v not in _simple_vars and '.' in v]

    # Collect all unique top-level variable names needed
    all_vars = set(_simple_vars)
    for dv in _dot_only_vars:
        top = dv.split('.')[0]
        all_vars.add(top)

    if not all_vars:
        return _normalized

    # Resolve using the same cascading provider as LLM nodes
    fmt_ctx = resolve_prompt_variables(
        variable_names=list(all_vars),
        state=state,
        mainwin=mainwin,
    )

    logger.info(f"[Mustache] simple_vars={_simple_vars}, dot={_dot_only_vars}")
    logger.info(f"[Mustache] fmt_ctx keys={list(fmt_ctx.keys())}")
    for k, v in fmt_ctx.items():
        sv = repr(str(v)[:200]) if v else '(empty)'
        logger.info(f"[Mustache]   {k} = {sv}")

    result = _normalized

    # --- 1. Replace top-level {{var}} (but NOT those inside section delimiters) ---
    # Strategy: protect section-delimited areas, replace simple vars outside them.
    # Simple and safe: use a placeholder approach.

    # Collect all section ranges (start, end) to protect
    protected_ranges = []  # list of (start, end)

    # Match all section tags (opening, closing, inverted)
    for _m in _re.finditer(r'\{\{[#^/]?\s*(\w+(?:\.\w+)*)\s*\}\}', _normalized):
        tag_start = _m.start()
        tag_end = _m.end()
        # Extend range to include the full tag
        protected_ranges.append((tag_start, tag_end))

    def _is_protected(pos: int) -> bool:
        for s, e in protected_ranges:
            if s <= pos < e:
                return True
        return False

    # Replace simple vars that are not inside a tag
    for var in sorted(_simple_vars, key=len, reverse=True):
        # Find all occurrences of {{var}}
        for _m in _re.finditer(r'\{\{' + _re.escape(var) + r'\}\}', result):
            span = (_m.start(), _m.end())
            if not any(s <= span[0] < e or s < span[1] <= e for s, e in protected_ranges):
                val = fmt_ctx.get(var, '')
                if val is None:
                    val = ''
                result = result[:_m.start()] + str(val) + result[_m.end():]
                # Recompute protected ranges after string change (simple approach: break and restart)
                break

    # --- 2. Replace dot-path vars {{a.b}} ---
    for dv in sorted(_dot_only_vars, key=len, reverse=True):
        parts = dv.split('.')
        val = None
        top_var = parts[0]
        ctx_val = fmt_ctx.get(top_var)
        if isinstance(ctx_val, dict):
            val = _mustache_get(ctx_val, dv[len(top_var) + 1:])
        if val is None:
            val = ''
        # Protect tag spans before replacing
        protected_dot = []
        for _m2 in _re.finditer(r'\{\{' + _re.escape(dv) + r'\}\}', result):
            if not any(s <= _m2.start() < e for s, e in protected_ranges):
                result = result[:_m2.start()] + str(val) + result[_m2.end():]
                break

    # --- 3. Recursively resolve all section blocks ---
    result = _resolve_sections_recursive(result, fmt_ctx, state, mainwin)

    return result


def _resolve_sections_recursive(text: str, fmt_ctx: dict, state: dict, mainwin) -> str:
    """
    Recursively find and resolve Mustache section blocks in text.
    
    Handles nested sections correctly using a stack-based approach:
      {{#a}}{{#b}}{{c}}{{/b}}{{/a}}
      {{#a}}{{#b}}{{#list}}{{.}}{{/list}}{{/b}}{{/a}}
    
    Algorithm:
    1. Use a stack to track open section tags
    2. When we find an opening tag, push it onto the stack
    3. When we find a closing tag, pop from stack until we find a matching opener
    4. When we find a matching opener/opener pair at top of stack, extract body and render
    """
    import re as _re
    
    # Pattern to find ALL section tags (opening, closing, inverted)
    # Matches: {{#name}}, {{^name}}, {{/name}}
    tag_pattern = _re.compile(r'\{\{(#|\^|/)\s*(\w+)\s*\}\}')
    
    result = []
    i = 0
    _max_iterations = 10000  # Safety limit to prevent infinite loops
    
    for _iter in range(_max_iterations):
        # Look for next section tag
        match = tag_pattern.search(text, i)
        if not match:
            result.append(text[i:])
            break
        
        # Add any text before this tag
        result.append(text[i:match.start()])
        
        tag_type = match.group(1)  # '#', '^', or '/'
        tag_name = match.group(2)
        
        if tag_type in ('#', '^'):
            # Opening or inverted section tag
            # Push a marker for this section onto a conceptual stack
            # We'll process it when we find the matching closer
            opener_pos = match.start()
            opener_end = match.end()
            
            # Find the matching closing tag
            depth = 1
            search_pos = opener_end
            
            while search_pos < len(text):
                next_match = tag_pattern.search(text, search_pos)
                if not next_match:
                    # No more tags
                    break
                
                next_type = next_match.group(1)
                next_name = next_match.group(2)
                
                if next_type == '/':
                    # Closing tag
                    if next_name == tag_name:
                        depth -= 1
                        if depth == 0:
                            # Found matching closer
                            body = text[opener_end:next_match.start()]
                            closer_end = next_match.end()
                            
                            # Get section data from context
                            section_data = fmt_ctx.get(tag_name)
                            
                            # Render the body (this recursively handles nested sections)
                            rendered_body = _render_mustache_section(body, section_data, state, mainwin)
                            
                            # Handle inverted sections
                            if tag_type == '^':
                                if not section_data or (isinstance(section_data, (list, tuple)) and len(section_data) == 0):
                                    result.append(rendered_body)
                            else:
                                result.append(rendered_body)
                            
                            # Continue after the closer
                            i = closer_end
                            break
                    else:
                        # Closing tag for a different section - skip it, don't decrement
                        # It belongs to a nested section that will be processed separately
                        pass
                elif next_type in ('#', '^'):
                    # Opening or inverted tag for another section
                    if next_name == tag_name:
                        # Nested section with same name
                        depth += 1
                
                search_pos = next_match.end()
            else:
                # Depth never reached 0 - unmatched opener, keep as-is and advance past it
                # to prevent infinite loop. Append the opener text and move i past it.
                result.append(text[match.start():opener_end])
                i = opener_end
        elif tag_type == '/':
            # Closing tag {{/name}} - this shouldn't happen at top level without opener
            # Keep it as-is (it will be handled when processing the parent section)
            result.append(match.group(0))
            i = match.end()
    else:
        # Safety: max iterations reached, append remaining text
        result.append(text[i:])
    
    return ''.join(result)


def _get_nested_field(data: dict, path: str) -> Any:
    """Get nested field from dict using dot-separated path."""
    if not isinstance(data, dict):
        return None
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current



def _compact_upstream_for_prompt(state: dict, max_chars: int = 10000) -> str:
    """Compact state["tool_result"] into a trimmed JSON string for LLM prompt injection.

    Design principle: **blacklist noise, keep everything else**.

    Instead of whitelisting specific business field names (which would be
    skill-specific and require maintenance), we drop known *structural noise*
    produced by browser-use / LLM framework internals and keep all remaining
    fields that are small enough to include in a prompt.

    Noise sources to drop:
    - Large text blobs: DOM content, HTML, screenshots, raw markdown
    - Framework internals: messages, history, prompt text, threads, events
    - Redundant scaffolding: provider, task description, system prompt

    Everything else (business fields of any name, from any skill) passes through
    as long as individual values stay under the per-value size cap.
    """
    import json as _json
    import re as _re

    tr = state.get("tool_result")
    if not isinstance(tr, dict) or not tr:
        return "{}"

    # Keys always dropped — framework/infrastructure noise with no business value.
    _NOISE_KEYS = frozenset({
        "provider", "task", "systemPrompt", "system_prompt",
        "history", "prompts", "prompt_refs", "prompt",
        "messages", "threads", "events",
        "attachments", "http_response",
        "cli_input", "cli_results",
        "attributes", "metadata",
    })

    # Key-name substrings that signal large, noisy content regardless of key name.
    _NOISE_SUBSTR = (
        "screenshot", "base64", "dom_content", "html_content",
        "raw_html", "markdown_content", "page_content", "dom_tree",
        "page_source", "inner_html", "outer_html",
    )

    # Maximum character length for any single scalar value kept in the output.
    _MAX_VAL_CHARS = 500
    # Maximum items kept from a list value.
    _MAX_LIST_ITEMS = 30

    def _is_noisy_key(k: str) -> bool:
        kl = k.lower()
        return k in _NOISE_KEYS or any(s in kl for s in _NOISE_SUBSTR)

    def _extract_json_from_text(text: str):
        """Best-effort: parse a JSON object out of a fenced or plain string."""
        s = text.strip()
        if not s:
            return None
        if s.startswith("```"):
            s = _re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
            s = _re.sub(r"\n?```$", "", s).strip()
        try:
            parsed = _json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        m = _re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                parsed = _json.loads(m.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    def _compact_value(v, depth: int = 0):
        """Recursively compact a value, dropping noise and over-sized content."""
        if v is None or v == "" or v == [] or v == {}:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            if len(v) > _MAX_VAL_CHARS:
                # Try to parse as JSON — the string might be an encoded business payload.
                parsed = _extract_json_from_text(v)
                if parsed:
                    return _compact_dict(parsed, depth + 1)
                return None  # Too long and not parseable — drop it.
            return v
        if isinstance(v, list):
            result = []
            for item in v[:_MAX_LIST_ITEMS]:
                cv = _compact_value(item, depth + 1)
                if cv is not None:
                    result.append(cv)
            return result or None
        if isinstance(v, dict):
            return _compact_dict(v, depth + 1) or None
        return None

    def _compact_dict(d: dict, depth: int = 0) -> dict:
        """Return a compacted copy of d, dropping noise and oversized values."""
        if depth > 5:
            return {}
        out = {}
        for k, v in d.items():
            if not isinstance(k, str):
                continue
            if _is_noisy_key(k):
                continue
            cv = _compact_value(v, depth)
            if cv is not None:
                out[k] = cv
        return out

    def _unwrap_payload(node_val: dict) -> dict:
        """
        Merge business data from both the top-level dict and common wrapper keys
        (final, result, llm_result, response, output) into a single flat dict.
        Wrapper keys are resolved first so that top-level scaffolding fields
        (provider, task, …) don't shadow the actual business payload.
        """
        merged: dict = {}

        # 1. Check candidate wrapper keys for a JSON business payload.
        for wrapper in ("final", "result", "llm_result", "response", "output", "text"):
            payload = node_val.get(wrapper)
            if isinstance(payload, dict):
                for k, v in payload.items():
                    if k not in merged and not _is_noisy_key(k):
                        merged[k] = v
            elif isinstance(payload, str):
                parsed = _extract_json_from_text(payload)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if k not in merged and not _is_noisy_key(k):
                            merged[k] = v

        # 2. Top-level non-noise keys (don't overwrite payload fields).
        for k, v in node_val.items():
            if k not in merged and not _is_noisy_key(k) and k not in ("final", "result", "llm_result", "response", "output", "text"):
                merged[k] = v

        return merged

    compact = {}
    for node_id, node_val in tr.items():
        if not isinstance(node_val, dict):
            continue
        unwrapped = _unwrap_payload(node_val)
        row = _compact_dict(unwrapped)
        if row:
            compact[node_id] = row

    try:
        payload = _json.dumps(compact, ensure_ascii=False, indent=2)
    except Exception:
        payload = str(compact)

    if len(payload) > max_chars:
        payload = payload[:max_chars] + "...(truncated)"
    return payload


_MAX_TOOL_RESULT_ENTRIES = 50  # Keep only the most recent 50 tool results to limit memory


def _trim_tool_result(state: dict) -> None:
    """Prune state["tool_result"] to the most recent entries to limit memory.

    Each node execution appends to tool_result (keyed by node name).  After
    MAX_TOOL_RESULT_ENTRIES, older entries are dropped.
    """
    tr = state.get("tool_result")
    if not isinstance(tr, dict) or len(tr) <= _MAX_TOOL_RESULT_ENTRIES:
        return
    try:
        # Keep only the last MAX_TOOL_RESULT_ENTRIES entries by insertion order
        items = list(tr.items())
        state["tool_result"] = dict(items[-_MAX_TOOL_RESULT_ENTRIES:])
        logger.debug(f"[build_node] Trimmed tool_result from {len(items)} to {_MAX_TOOL_RESULT_ENTRIES} entries")
    except Exception:
        pass


def build_llm_node(config_metadata: dict, node_name, skill_name, owner, bp_manager):
    """
    Builds a callable function for a LangGraph node that interacts with an LLM.

    Args:
        config_metadata (dict): The node configuration from the skill JSON
        node_name (str): The name of the node
        skill_name (str): The name of the skill
        owner (str): The owner of the skill
        bp_manager: The breakpoint manager

    Returns:
        A callable function that can be used as a LangGraph node
    """
    # Extract configuration from metadata with sensible defaults (tolerant to missing keys)
    logger.debug("building llm node:", config_metadata)
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
    
    # Guardrail timer configuration
    enable_guardrail_timer = False
    llm_timeout_seconds = float(os.getenv("ECAN_LLM_TIMEOUT_SEC", "150"))
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
    
    # CRITICAL: Get inputsValues FIRST before accessing any input fields
    inputs = (config_metadata or {}).get("inputsValues", {}) or {}
    
    # Get explicit provider from frontend (guaranteed by form-meta.tsx)
    raw_provider = None
    try:
        raw_provider = ((inputs.get("modelProvider") or {}).get("content")
                        or (inputs.get("provider") or {}).get("content"))
    except Exception:
        raw_provider = None
    
    model_name = ((inputs.get("modelName") or {}).get("content")
                  or (inputs.get("model") or {}).get("content"))
    api_key = ((inputs.get("apiKey") or {}).get("content") or "")
    api_host = ((inputs.get("apiHost") or {}).get("content") or "")
    try:
        temperature = float(((inputs.get("temperature") or {}).get("content") or 0.5))
    except Exception:
        temperature = 0.5
    
    # Extract useThinking setting from node editor (for Qwen/reasoning models)
    node_use_thinking = False
    try:
        use_thinking_val = (inputs.get("useThinking") or {}).get("content")
        node_use_thinking = str(use_thinking_val).lower() in ('true', '1', 'yes', 'on') if use_thinking_val is not None else False
    except Exception:
        node_use_thinking = False

    prompt_selection = ((inputs.get("promptSelection") or {}).get("content") or "inline").strip()
    logger.debug("[LLMNode]prompt_selection:", prompt_selection)

    system_prompt_id = ((inputs.get("systemPromptId") or {}).get("content") or None)
    user_prompt_id = ((inputs.get("promptId") or {}).get("content") or None)
    logger.debug("[LLMNode]system_prompt_id:", system_prompt_id)
    logger.debug("[LLMNode]user_prompt_id:", user_prompt_id)

    # ── Skill-author footgun guard: duplicate prompt ids ─────────────
    # If a skill author accidentally points both ``systemPromptId`` and
    # ``promptId`` at the same prompt, the prompt body gets loaded as
    # BOTH the system and user templates, so every ``{{input}}`` slot
    # and every token of the body is sent to the model twice, and any
    # inlined attachment ``data_uri`` in ``{{input}}`` blows the system
    # message up to tens of megabytes.  This caused the Feige Q&A
    # worker "我看不到图片" regression; keep a loud warning here so the
    # next misconfiguration is obvious in logs and the skill editor
    # timeline.
    if (
        system_prompt_id
        and user_prompt_id
        and system_prompt_id == user_prompt_id
    ):
        _dup_msg = (
            f"[build_llm_node] ⚠️ node={node_name}: systemPromptId and "
            f"promptId are both set to '{system_prompt_id}'. The prompt "
            f"body will be used as BOTH system and user prompt, which "
            f"doubles token cost and inlines attachment data_uri blobs "
            f"into the system message. Set promptId to a separate "
            f"user-input template (e.g. one containing just "
            f"'{{{{input}}}}'), or clear one of the two fields."
        )
        logger.warning(_dup_msg)
        try:
            send_skill_editor_log("warning", _dup_msg)
        except Exception:
            pass

    # Get inline prompt content.
    # Note: ``inline_user_prompt`` defaults to ``{{input}}`` (NOT
    # ``STANDARD_SYS_PROMPT``) because this field is the *user-turn*
    # template — the natural default is to pass the invocation payload
    # straight through as the human message.  Using the system-prompt
    # string here was a historical copy-paste; it caused the user turn
    # to literally read "You are a helpful AI assistant." when the
    # skill author left the field blank.
    inline_system_prompt = ((inputs.get("systemPrompt") or {}).get("content") or STANDARD_SYS_PROMPT)
    inline_user_prompt = ((inputs.get("prompt") or {}).get("content") or "{{input}}")

    logger.debug("[LLMNode]inline_system_prompt:", inline_system_prompt)
    logger.debug("[LLMNode]inline_user_prompt:", inline_user_prompt)

    # Resolve prompt templates based on the selected prompt id first for initial config preview
    resolved_system_prompt, resolved_user_prompt, prompt_level_variables = _resolve_prompt_templates(
        prompt_selection,
        inline_system_prompt,
        inline_user_prompt,
        skill_owner=owner or "",
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
    # Normalize provider names dynamically from llm_manager
    # This automatically syncs with gui/config/llm_providers.json
    # NOTE: _get_llm_manager_singleton must be defined BEFORE _get_provider_mapping
    # since _get_provider_mapping() calls it. These are nested functions but Python
    # resolves names at call time, not definition time.
    _LLM_MANAGER_CACHE: dict = {}  # Module-level cache for LLM manager singleton

    def _get_llm_manager_singleton():
        """Return the cached LLM manager singleton, avoiding repeated JSON parsing."""
        if "singleton" in _LLM_MANAGER_CACHE:
            return _LLM_MANAGER_CACHE["singleton"]
        try:
            from gui.ipc.w2p_handlers.llm_handler import get_llm_manager
            mgr = get_llm_manager()
            _LLM_MANAGER_CACHE["singleton"] = mgr
            return mgr
        except Exception as e:
            logger.debug(f"[build_llm_node] get_llm_manager() failed: {e}")
            return None

    def _get_provider_mapping() -> dict:
        """
        Dynamically build provider mapping from llm_manager.
        Maps all known name variants (name, display_name, class_name, provider_id)
        to the canonical provider_id. No hardcoded provider list needed.
        
        Returns:
            Dictionary mapping various provider name formats to canonical provider identifiers
        """
        try:
            llm_manager = _get_llm_manager_singleton()

            if not llm_manager:
                logger.warning("[build_llm_node] LLM manager not available, using fallback mapping")
                return {}
            
            providers = llm_manager.get_all_providers()
            mapping = {}
            
            for provider in providers:
                # Get canonical provider identifier (e.g., "openai", "deepseek")
                provider_id = (provider.get("provider") or "").lower()
                if not provider_id:
                    continue
                
                # Map provider identifier to itself
                mapping[provider_id] = provider_id
                
                # Map display name to provider identifier (e.g., "OpenAI" -> "openai")
                name = (provider.get("name") or "").lower()
                if name:
                    mapping[name] = provider_id
                
                # Map display_name if different from name
                display_name = (provider.get("display_name") or "").lower()
                if display_name and display_name != name:
                    mapping[display_name] = provider_id
                
                # Map class_name for backward compatibility (e.g., "ChatOpenAI" -> "openai")
                class_name = (provider.get("class_name") or "").lower()
                if class_name:
                    mapping[class_name] = provider_id
            
            logger.debug(f"[build_llm_node] Built provider mapping with {len(mapping)} entries from llm_manager")
            return mapping
            
        except Exception as e:
            logger.warning(f"[build_llm_node] Failed to build provider mapping from llm_manager: {e}")
            return {}
    
    # Get dynamic provider mapping from llm_manager
    # Resolves any name variant (name/display_name/class_name/provider_id) → canonical provider_id
    provider_mapping = _get_provider_mapping()

    # Determine provider: node-specified OR default from Settings
    # CRITICAL: If node specifies a provider, we MUST use it (no fallback)
    if raw_provider:
        # Node specified a provider - use it and ONLY it (no fallback allowed)
        model_provider = provider_mapping.get(raw_provider.lower(), raw_provider)
        llm_provider = model_provider.lower()
        try:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
            if mainwin and hasattr(mainwin, 'config_manager'):
                provider_exists = mainwin.config_manager.llm_manager.get_provider(model_provider)
                if not provider_exists:
                    raise RuntimeError(f"[build_llm_node] Node specified unknown provider '{raw_provider}'")
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.warning(f"[build_llm_node] Could not validate node provider '{raw_provider}': {e}")
        if not model_name:
            try:
                from app_context import AppContext
                mainwin = AppContext.get_main_window()
                if mainwin and hasattr(mainwin, 'config_manager'):
                    provider_dict = mainwin.config_manager.llm_manager.get_provider(model_provider)
                    if provider_dict:
                        model_name = provider_dict.get('default_model')
            except Exception:
                pass
        if not model_name:
            raise RuntimeError(f"[build_llm_node] Node specified provider '{raw_provider}' but model_name is missing")
        logger.info(f"[build_llm_node] Node specified provider: {raw_provider} -> {llm_provider}")
    else:
        # Node did NOT specify provider - use default from Settings
        try:
            from app_context import AppContext
            ctx = AppContext.get_instance()
            mainwin = ctx.get_main_window()
            
            if not mainwin or not hasattr(mainwin, 'config_manager'):
                raise RuntimeError("[build_llm_node] Cannot access Settings to get default LLM")
            
            # Use unified method to get default LLM config
            llm_config = mainwin.config_manager.llm_manager.get_default_llm_config()
            model_provider = llm_config['provider_id']
            llm_provider = model_provider.lower()
            
            # If node didn't specify model, use default model from Settings
            if not model_name:
                model_name = llm_config['model_name']
            
            logger.info(f"[build_llm_node] Using default LLM from Settings: {model_provider}, model: {model_name}")
            
        except Exception as e:
            logger.error(f"[build_llm_node] Failed to get default LLM from Settings: {e}")
            raise RuntimeError(f"No provider specified in node and failed to get default LLM from Settings: {e}")
    
    logger.info(f"llm config: system_prompt_template='{system_prompt_template}' user_prompt_template='{user_prompt_template}' ")
    logger.info(f"llm config: model_name={model_name} api_host={api_host} api_key={api_key} model_provider={model_provider} llm_provider={llm_provider}")

    # ── Per-provider-info cache: LLM manager lookups are slow (JSON parsing, regex) ──
    _PROVIDER_INFO_CACHE: dict[str, dict] = {}
    _PROVIDER_SPEC_CACHE: dict[str, dict] = {}

    def _get_runtime_provider_info(provider_name: str) -> dict:
        provider_name_l = (provider_name or "").lower()
        # Fast path: already cached
        if provider_name_l in _PROVIDER_INFO_CACHE:
            return _PROVIDER_INFO_CACHE[provider_name_l]
        llm_manager = _get_llm_manager_singleton()
        if llm_manager:
            provider_info = llm_manager.get_provider(provider_name_l)
            if isinstance(provider_info, dict):
                _PROVIDER_INFO_CACHE[provider_name_l] = provider_info
                return provider_info
            for item in llm_manager.get_all_providers() or []:
                if not isinstance(item, dict):
                    continue
                pid = (item.get("provider") or "").lower()
                name = (item.get("name") or "").lower()
                display_name = (item.get("display_name") or "").lower()
                if provider_name_l in {pid, name, display_name}:
                    _PROVIDER_INFO_CACHE[provider_name_l] = item
                    return item
        return {}

    def _normalize_provider_runtime_spec(provider_name: str, provider_info: dict) -> dict:
        # Cache the normalized spec — it's a pure function of the provider_info dict
        # which itself is cached by _get_runtime_provider_info.
        cache_key = str(id(provider_info))
        if cache_key in _PROVIDER_SPEC_CACHE:
            return _PROVIDER_SPEC_CACHE[cache_key]
        spec = {
            "provider_key": (provider_info.get("provider") or provider_name or "").strip().lower(),
            "runtime_kind": (provider_info.get("runtime_kind") or "").strip(),
            "param_mapping": provider_info.get("param_mapping") or {},
            "api_key_env_vars": provider_info.get("api_key_env_vars") or [],
            "default_model": provider_info.get("default_model") or "",
            "base_url": provider_info.get("base_url") or "",
            "default_params": provider_info.get("default_params") or {},
            "special_features": provider_info.get("special_features") or {},
        }
        _PROVIDER_SPEC_CACHE[cache_key] = spec
        return spec

    def _prepare_llm_extra_params(runtime_spec: dict, use_thinking: bool) -> dict:
        extra_params = {}
        special_features = runtime_spec.get("special_features") or {}
        thinking_toggle_mode = special_features.get("thinking_toggle_mode")
        if thinking_toggle_mode == "extra_body.enable_thinking":
            if not use_thinking:
                extra_params["extra_body"] = {"enable_thinking": False}
                logger.info(f"[LLM] Qwen enable_thinking=False via extra_body")
            else:
                logger.info(f"[LLM] Qwen enable_thinking=True (default)")
        return extra_params

    def _get_runtime_constructor(runtime_kind: str):
        """
        Get the LLM constructor class for a given runtime_kind.
        
        When adding a new runtime_kind:
        1. Add the mapping here: "runtime_kind": ConstructorClass
        2. Ensure the constructor class is imported at the top of this file
        3. Update llm_providers.json with the new runtime_kind and validation rules
        """
        runtime_registry = {
            "openai_compatible": ChatOpenAI,
            "anthropic": ChatAnthropic,
            "google_genai": ChatGoogleGenerativeAI,
            "deepseek": ChatDeepSeek,
            "qwq_compatible": ChatQwQ,
            "ollama_native": ChatOllama,
            "zhipuai": ChatZhipuAI,
            "bedrock_converse": ChatBedrockConverse,
            "azure_openai": AzureChatOpenAI,
        }
        return runtime_registry.get((runtime_kind or "").strip())

    def _validate_runtime_registry():
        """
        Self-check: Validate that all runtime_kinds in llm_providers.json
        have corresponding constructors in the runtime registry.
        This runs once at module load time.
        """
        try:
            llm_manager = _get_llm_manager_singleton()
            if not llm_manager:
                return
            all_providers = llm_manager.get_all_providers() or []
            runtime_registry_keys = {
                "openai_compatible", "anthropic", "google_genai", "deepseek",
                "qwq_compatible", "ollama_native", "zhipuai", "bedrock_converse", "azure_openai"
            }
            missing_constructors = []
            for provider in all_providers:
                if not isinstance(provider, dict):
                    continue
                runtime_kind = (provider.get("runtime_kind") or "").strip()
                if runtime_kind and runtime_kind not in runtime_registry_keys:
                    provider_name = provider.get("name") or provider.get("provider") or "Unknown"
                    missing_constructors.append(f"{provider_name} (runtime_kind: {runtime_kind})")
            if missing_constructors:
                logger.warning(
                    f"[build_llm_node] Runtime registry missing constructors for: {', '.join(missing_constructors)}. "
                    "Please add them to _get_runtime_constructor() in build_node.py"
                )
        except Exception as e:
            logger.debug(f"[build_llm_node] Runtime registry validation skipped: {e}")

    def _build_llm_kwargs_from_runtime_spec(
        runtime_spec: dict,
        *,
        model_name_value: str,
        api_key_value: str,
        host_value: str,
        temperature_value: float,
        use_thinking: bool,
    ) -> dict:
        kwargs = dict(runtime_spec.get("default_params") or {})
        param_mapping = runtime_spec.get("param_mapping") or {}
        default_model = runtime_spec.get("default_model") or ""
        default_base_url = runtime_spec.get("base_url") or ""
        special_features = runtime_spec.get("special_features") or {}

        value_map = {
            "model": model_name_value or default_model,
            "api_key": api_key_value,
            "base_url": host_value or default_base_url,
            "temperature": temperature_value,
        }

        for source_key, target_key in param_mapping.items():
            value = value_map.get(source_key)
            if value not in (None, ""):
                kwargs[target_key] = value

        extra_params = _prepare_llm_extra_params(runtime_spec, use_thinking)
        kwargs.update(extra_params)

        if special_features.get("requires_http_client"):
            from agent.ec_skills.llm_utils.llm_utils import _create_no_proxy_http_client
            sync_client, async_client = _create_no_proxy_http_client()
            if sync_client and "http_client" not in kwargs:
                kwargs["http_client"] = sync_client
            if async_client and "http_async_client" not in kwargs:
                kwargs["http_async_client"] = async_client

        return kwargs

    def _get_runtime_provider_env_vars(provider_name: str) -> list[str]:
        provider_info = _get_runtime_provider_info(provider_name)
        env_vars = provider_info.get("api_key_env_vars") or []
        return [str(v).strip() for v in env_vars if isinstance(v, str) and str(v).strip()]

    def _resolve_api_key_from_provider_env_vars(provider_name: str, username: str | None = None) -> str | None:
        # ── API key cache: avoid hitting secure_store on every LLM invocation ──
        # Cache keyed by (provider, username) with a 2-min TTL so credential
        # rotation is picked up without a process restart.
        _now = time.time()
        _ak_cache_key = f"{provider_name}|{username or ''}"
        _ak_cached = _API_KEY_CACHE.get(_ak_cache_key)
        if _ak_cached is not None:
            _ak_cached_at, _ak_cached_val = _ak_cached
            if _now - _ak_cached_at < _API_KEY_CACHE_TTL_SECONDS and _ak_cached_val is not None:
                return _ak_cached_val

        env_vars = _get_runtime_provider_env_vars(provider_name)
        resolved = None
        for env_var in env_vars:
            if "ENDPOINT" in env_var.upper():
                continue
            env_value = (os.getenv(env_var) or "").strip()
            if env_value:
                resolved = env_value
                break
            try:
                secure_value = secure_store.get(env_var, username=username)
                if secure_value and str(secure_value).strip():
                    resolved = str(secure_value).strip()
                    break
            except Exception:
                pass

        _API_KEY_CACHE[_ak_cache_key] = (_now, resolved)
        return resolved

    def _build_runtime_llm(
        *,
        provider_name: str,
        model_name_value: str,
        api_key_value: str,
        host_value: str,
        temperature_value: float,
        use_thinking: bool,
        raw_provider_name: str | None,
        allow_default_openai: bool,
    ):
        # --- Lambda proxy shortcut ---
        if _should_use_proxy(inputs):
            proxy_cfg = _get_proxy_config()
            if proxy_cfg:
                from agent.ec_skills.lambda_proxy_langchain import create_lambda_proxy_langchain
                logger.info(f"[LLM Node] Using Lambda proxy for {provider_name}/{model_name_value}")
                return create_lambda_proxy_langchain(
                    provider=provider_name or 'openai',
                    model=model_name_value or 'gpt-4o',
                    user_id=proxy_cfg['user_id'],
                    lambda_endpoint=proxy_cfg['endpoint'],
                    auth_token=proxy_cfg['auth_token'],
                    temperature=temperature_value,
                )

        # ── LLM instance cache: skip re-construction for repeated invocations ──
        # Build a stable cache key from the parameters that define the LLM identity.
        # API key is deliberately excluded from the key: the cached instance still
        # calls the same endpoint with the same model; if credentials rotate the
        # TTL (5 min) handles stale-key cleanup.
        _now = time.time()
        _raw_key = (
            f"{provider_name}|{model_name_value or ''}|"
            f"{(host_value or '').rstrip('/')}|"
            f"{temperature_value}|{use_thinking}"
        )
        _cached = _LLM_INSTANCE_CACHE.get(_raw_key)
        if _cached is not None:
            _cached_at, _cached_llm = _cached
            if _now - _cached_at < _LLM_CACHE_TTL_SECONDS:
                return _cached_llm

        # ── Full construction (cache miss) ─────────────────────────────────────
        provider_info = _get_runtime_provider_info(provider_name)
        runtime_spec = _normalize_provider_runtime_spec(provider_name, provider_info)
        runtime_kind = runtime_spec.get("runtime_kind") or ""
        constructor = _get_runtime_constructor(runtime_kind)

        if not runtime_kind or constructor is None:
            if raw_provider_name and not allow_default_openai:
                raise ValueError(
                    f"Unsupported node-specified provider '{raw_provider_name}' (resolved: '{provider_name}'). "
                    "Please select a configured provider from Settings."
                )
            runtime_kind = "openai_compatible"
            runtime_spec = {
                "runtime_kind": "openai_compatible",
                "param_mapping": {
                    "model": "model",
                    "api_key": "api_key",
                    "base_url": "base_url",
                    "temperature": "temperature",
                },
                "default_params": {},
                "default_model": "",
                "base_url": "",
                "special_features": {},
            }
            constructor = ChatOpenAI

        special_features = runtime_spec.get("special_features") or {}

        if special_features.get("check_import"):
            import_name = special_features["check_import"]
            if globals().get(import_name) is None:
                raise ImportError(f"{import_name} is not available. Please install the required package.")

        if special_features.get("requires_api_key") and not api_key_value:
            raise ValueError(f"{provider_name} requires an API key")

        if special_features.get("requires_model") and not model_name_value:
            raise ValueError(f"{provider_name} requires a model/deployment name")

        if special_features.get("requires_azure_endpoint"):
            azure_endpoint = host_value or (secure_store.get("AZURE_ENDPOINT", username=get_current_username()) if api_key_value else None)
            if not azure_endpoint:
                raise ValueError(f"{provider_name} requires AZURE_ENDPOINT")
            if not runtime_spec.get("base_url"):
                runtime_spec["base_url"] = azure_endpoint
            host_value = azure_endpoint

        kwargs = _build_llm_kwargs_from_runtime_spec(
            runtime_spec,
            model_name_value=model_name_value,
            api_key_value=api_key_value,
            host_value=host_value,
            temperature_value=temperature_value,
            use_thinking=use_thinking,
        )
        llm = constructor(**kwargs)

        # Store in cache with timestamp for TTL enforcement
        _LLM_INSTANCE_CACHE[_raw_key] = (_now, llm)
        return llm

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
        send_skill_editor_log("log", log_msg)

        log_msg = f"State: {state}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)

        # obtain code from code based workflow.
        current_node_name = runtime.context["this_node"].get("name")
        skill_name = runtime.context["this_node"].get("skill_name")
        owner = runtime.context["this_node"].get("owner")
        full_node_name = f"{owner}:{skill_name}:{current_node_name}"
        logger.debug(f"[LLM] llm_node_callable: node={node_name}, skill={skill_name}")

        log_msg = f"full_node_name: {full_node_name}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)


        # Use the already-resolved templates from build time (which include full tool schemas)
        # instead of calling _resolve_prompt_templates again at runtime
        # The build-time resolution (lines 475-492) already processed prompt_selection and
        # fetched tool schemas - calling it again at runtime may lose that context
        active_system_prompt = system_prompt_template
        active_user_prompt = user_prompt_template
        logger.debug(f"[LLM] Using pre-resolved prompts: system_len={len(active_system_prompt)}, user_len={len(active_user_prompt)}")

        # Find all variable placeholders (e.g., {{var_name}}) in the prompts
        variables = re.findall(r'\{\{(\w+)\}\}', active_system_prompt + active_user_prompt)
        logger.debug(f"[LLM] node={node_name} template_vars={variables}")

        # Compact upstream_outputs before variable resolution to prevent context bloat.
        # Browser-automation nodes do this inline; LLM nodes must do the same here.
        if "upstream_outputs" in variables:
            try:
                _pr = state.setdefault("prompt_refs", {})
                if isinstance(_pr, dict) and "upstream_outputs" not in _pr:
                    _pr["upstream_outputs"] = _compact_upstream_for_prompt(state)
                    logger.info(
                        f"[LLM] node={node_name} injected compact upstream_outputs "
                        f"({len(_pr['upstream_outputs'])} chars) into prompt_refs"
                    )
            except Exception as _cmp_err:
                logger.debug(f"[LLM] Failed to compact upstream_outputs: {_cmp_err}")

        # --- Cascading variable resolution ---
        # Priority: prompt_refs → prompt-level vars → skill-level vars → built-in providers → ""
        _mainwin = None
        try:
            from app_context import AppContext
            _mainwin = AppContext.get_main_window()
        except Exception:
            pass

        # Extract skill-level prompt_variables from the running skill's mapping_rules
        skill_prompt_variables = {}
        try:
            agent_id = state.get("messages", [""])[0] if state.get("messages") else ""
            if agent_id and _mainwin:
                from agent.agent_service import get_agent_by_id
                _agent = get_agent_by_id(agent_id)
                if _agent:
                    _skill = next(
                        (sk for sk in getattr(_agent, "skills", []) or []
                         if getattr(sk, "name", "") == skill_name),
                        None,
                    )
                    if _skill and getattr(_skill, "mapping_rules", None):
                        skill_prompt_variables = _skill.mapping_rules.get("prompt_variables", {}) or {}
        except Exception as _spv_err:
            logger.debug(f"[LLM] Could not load skill prompt_variables: {_spv_err}")

        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables
        format_context = resolve_prompt_variables(
            variable_names=variables,
            state=state,
            mainwin=_mainwin,
            prompt_variables=prompt_level_variables,
            skill_prompt_variables=skill_prompt_variables,
        )
        logger.debug(f"[LLM] node={node_name} resolved {len(format_context)} variables")
        
        # DEBUG: Log format_context for key variables to help debug template resolution
        if any(v in ["input", "attachments", "llm_result", "query", "human_text"] for v in format_context):
            try:
                for _key in ["input", "attachments", "llm_result", "query", "human_text"]:
                    if _key in format_context:
                        _val = format_context[_key]
                        _preview = str(_val)[:200] if _val else "(empty/None)"
                        logger.info(f"[LLM_DEBUG] node={node_name} format_context[{_key}] = '{_preview}...'")
            except Exception as _fmt_err:
                logger.debug(f"[LLM] Failed to log format_context: {_fmt_err}")

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
            # Check if any {{variables}} remain unresolved after substitution
            _remaining_sys = re.findall(r'\{\{(\w+)\}\}', final_system_prompt)
            _remaining_usr = re.findall(r'\{\{(\w+)\}\}', final_user_prompt)
            if _remaining_sys or _remaining_usr:
                logger.warning(
                    f"[LLM] UNRESOLVED variables remain: system={_remaining_sys} user={_remaining_usr}"
                )
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
            send_skill_editor_log("error", err_msg)
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
                    send_skill_editor_log("log", log_msg)
                    
                except Exception as e:
                    err_msg = f"[ContextBuilder] Failed to build context: {e}"
                    logger.warning(err_msg)
                    send_skill_editor_log("warning", err_msg)
            # =================================================================
            # End Context Engineering
            # =================================================================
            
            # ── Multimodal upgrade (pre-hook stage) ───────────────────────────
            # If the inbound payload (state["input"] JSON) carries
            # ``latest_message_attachments`` with ``data_uri`` blobs
            # (eager-fetched by the front-desk's pre-dispatch hook), replace
            # the current-turn HumanMessage at ``messages[-1]`` with a proper
            # multimodal content list ([text_part, image_url_part, ...]) and
            # strip the base64 blob out of the text part.
            #
            # Why here (before run_pre_llm_hook) and NOT after recent_context is
            # built: with a raw ~6 MB data-URI-bearing HumanMessage,
            # ``get_recent_context`` sees it as ~2.6 M tokens and silently drops
            # it via its token-budget filter, leaving recent_context with only
            # the SystemMessage.  Upgrading here keeps the text part tiny (~7 KB)
            # and lets the multimodal HumanMessage flow through the pre-hook
            # into ``state["history"]`` and then through get_recent_context.
            #
            # Fully try/except'd — a failure MUST NOT break the text-only path.
            try:
                if (
                    messages
                    and isinstance(messages[-1], HumanMessage)
                    and isinstance(messages[-1].content, str)
                ):
                    from agent.ec_skills.llm_utils.llm_utils import (
                        prep_multi_modal_content,
                        _strip_data_uri_noise,
                    )
                    _mm_content = prep_multi_modal_content(
                        state,
                        runtime,
                        llm=None,  # vision-capability check deferred to build_llm
                        base_text=messages[-1].content,
                    )
                    if _mm_content:
                        _img_n = sum(
                            1 for p in _mm_content
                            if isinstance(p, dict) and p.get("type") == "image_url"
                        )
                        messages[-1] = HumanMessage(content=_mm_content)

                        # ── Critical: strip inlined data URIs from the text
                        # streams now that the image is properly delivered as
                        # an ``image_url`` content part on the HumanMessage.
                        #
                        # Why this matters: ``{{input}}`` inside the prompt
                        # template gets substituted with the raw JSON payload
                        # which carries ``"data_uri": "data:image/...;base64,
                        # <up-to-7MB>"`` for each customer attachment.  When
                        # the same prompt body is used for BOTH the system
                        # and user templates (e.g. when ``systemPromptId`` and
                        # ``promptId`` point at the same prompt id, or when
                        # the prompt body has multiple ``{{input}}`` slots —
                        # both common in Feige-style Q&A workers), the
                        # ``final_system_prompt`` and ``final_user_prompt``
                        # each balloon to tens of megabytes of inline base64.
                        #
                        # The model then sees the (real, viewable) image
                        # AND six garbled base64 strings in the system text
                        # — and reports back "I can't see a clear image"
                        # which is exactly its prompted fallback for
                        # unrecognizable content.  Stripping the data URIs
                        # from the text streams here keeps the model focused
                        # on the one canonical ``image_url`` part.
                        try:
                            _orig_sys_len = len(final_system_prompt) if final_system_prompt else 0
                            _orig_usr_len = len(final_user_prompt) if final_user_prompt else 0
                            if final_system_prompt:
                                final_system_prompt = _strip_data_uri_noise(final_system_prompt)
                            if final_user_prompt:
                                final_user_prompt = _strip_data_uri_noise(final_user_prompt)
                            # Mirror the strip into messages[0] (SystemMessage)
                            # since downstream code reads from that as well.
                            if (
                                messages
                                and isinstance(messages[0], SystemMessage)
                                and isinstance(messages[0].content, str)
                            ):
                                messages[0] = SystemMessage(
                                    content=_strip_data_uri_noise(messages[0].content)
                                )
                            _new_sys_len = len(final_system_prompt) if final_system_prompt else 0
                            _new_usr_len = len(final_user_prompt) if final_user_prompt else 0
                            logger.info(
                                f"[multimodal-llm-node] stripped data_uri noise "
                                f"from prompt text streams: "
                                f"system {_orig_sys_len:,} -> {_new_sys_len:,} chars, "
                                f"user {_orig_usr_len:,} -> {_new_usr_len:,} chars "
                                f"(image now delivered as image_url part)"
                            )
                        except Exception as _strip_exc:
                            logger.warning(
                                f"[multimodal-llm-node] data_uri strip failed "
                                f"(non-fatal, continuing): "
                                f"{type(_strip_exc).__name__}: {_strip_exc}"
                            )

                        logger.info(
                            f"[multimodal-llm-node] node={node_name} "
                            f"upgraded messages[-1] HumanMessage to multimodal "
                            f"({_img_n} image part(s))"
                        )
            except Exception as _mm_exc:
                logger.warning(
                    f"[multimodal-llm-node] non-fatal upgrade failure "
                    f"(continuing text-only): "
                    f"{type(_mm_exc).__name__}: {_mm_exc}"
                )

            _t_stage = _time.perf_counter()
            run_pre_llm_hook(full_node_name, agent, state, prompt_src="local", prompt_data=messages)
            _perf_llm("pre_hook", _t_stage)

            # Adjust context window based on provider limitations
            # Fetch max_tokens from LLM config (gui/config/llm_providers.json)
            from gui.config.llm_config import llm_config
            model_max_tokens = llm_config.get_max_tokens(llm_provider, model_name)
            
            # Reserve tokens ONLY for LLM response output
            # System prompt and current user input are added separately and counted by LLM provider
            # History is what get_recent_context() controls
            # Total input = system_prompt + history + current_input (all auto-calculated)
            # We only need to ensure: total_input + response_output <= model_max_tokens
            RESPONSE_RESERVE = 4000  # Reserve for LLM response generation
            context_limit = max(8000, model_max_tokens - RESPONSE_RESERVE)  # More room for history
            
            logger.debug(
                f"Token allocation: model_max={model_max_tokens}, "
                f"history_limit={context_limit}, response_reserve={RESPONSE_RESERVE}"
            )
            
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
            send_skill_editor_log("log", log_msg)

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
                        llm_manager = _get_llm_manager_singleton()
                        if llm_manager:
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

                    return _resolve_api_key_from_provider_env_vars(provider_l, username=username)

                key = _resolve_api_key(llm_provider, api_key)
                host = (api_host or "").strip()
                prov = llm_provider

                if key:
                    key_preview = f"{key[:8]}......{key[-8:]}"
                else:
                    key_preview = ""
                logger.debug(f"real llm settings: api_key={key_preview} host={host} llm_provider={prov}")
                
                llm = _build_runtime_llm(
                    provider_name=prov,
                    model_name_value=model_name,
                    api_key_value=key,
                    host_value=host,
                    temperature_value=temperature,
                    use_thinking=node_use_thinking,
                    raw_provider_name=raw_provider,
                    allow_default_openai=not bool(raw_provider),
                )

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
                send_skill_editor_log("error", f"[build_llm_node] {err}")
                state['error'] = err
                return state

            # ── Native function-calling pilot: bind MCP tool schemas ──
            # Step 1 of the migration away from text-JSON-as-tool-call.  When
            # the gate is on AND we can resolve the node's ``tools_to_use``
            # list, attach those schemas to the LLM via LangChain
            # ``bind_tools``.  The provider then uses its native tool-call
            # protocol (OpenAI tools=[...], Anthropic tool_use, ...) and the
            # response will carry a typed ``tool_calls`` field instead of
            # relying on the model serializing JSON correctly into ``content``.
            #
            # Track for the bridge below — set on the *outer* function scope so
            # the post-invoke overlay knows whether to look at tool_calls.
            _native_tc_active = False
            try:
                _gate = _should_use_native_tool_calls(skill_name, _mainwin, inputs)
                if not _gate:
                    _native_tool_call_metric_inc("bind_skipped_gate")
                else:
                    _native_tool_call_metric_inc("bind_attempted")
                    if _should_use_proxy(inputs):
                        # Lambda proxy LLM doesn't expose a langchain bind_tools;
                        # leave it on the legacy path.
                        _native_tool_call_metric_inc("bind_skipped_proxy")
                        logger.info(
                            "[NativeToolCalls] gate=on but Lambda proxy LLM in use; "
                            f"skipping bind_tools for node={full_node_name}"
                        )
                    elif not hasattr(llm, "bind_tools"):
                        _native_tool_call_metric_inc("bind_skipped_unsupported")
                        logger.warning(
                            f"[NativeToolCalls] gate=on but LLM type={type(llm).__name__} "
                            f"has no bind_tools attribute; falling back to text parse "
                            f"for node={full_node_name}"
                        )
                    else:
                        _tool_names = _extract_tools_to_use_names(
                            prompt_selection,
                            inline_system_prompt,
                            skill_owner=owner or "",
                        )
                        if not _tool_names:
                            _native_tool_call_metric_inc("bind_skipped_no_tools")
                            logger.info(
                                f"[NativeToolCalls] gate=on but no tools_to_use names "
                                f"resolved for node={full_node_name} "
                                f"(prompt_selection={prompt_selection!r}); "
                                "falling back to text parse"
                            )
                        else:
                            _tool_schemas = _get_tool_schemas_for_names(_tool_names)
                            _function_tools = _schemas_to_function_tools(_tool_schemas)
                            if not _function_tools:
                                _native_tool_call_metric_inc("bind_skipped_no_tools")
                                logger.warning(
                                    f"[NativeToolCalls] gate=on but tool schemas could "
                                    f"not be loaded for names={_tool_names} "
                                    f"(node={full_node_name}); falling back to text parse"
                                )
                            else:
                                try:
                                    llm = llm.bind_tools(_function_tools, tool_choice="auto")
                                    _native_tc_active = True
                                    _native_tool_call_metric_inc("bind_succeeded")
                                    logger.info(
                                        f"[NativeToolCalls] bound {len(_function_tools)} "
                                        f"tools to LLM for node={full_node_name} "
                                        f"(provider={llm_provider}, model={model_name}, "
                                        f"names={[t['function']['name'] for t in _function_tools]})"
                                    )
                                    send_skill_editor_log(
                                        "log",
                                        f"[NativeToolCalls] bound {len(_function_tools)} tools "
                                        f"({', '.join(t['function']['name'] for t in _function_tools)})"
                                    )
                                except Exception as _bind_err:
                                    _native_tool_call_metric_inc("bind_failed")
                                    logger.warning(
                                        f"[NativeToolCalls] bind_tools failed for "
                                        f"node={full_node_name} "
                                        f"(provider={llm_provider}): {_bind_err}; "
                                        "falling back to text parse"
                                    )
            except Exception as _ntc_err:
                # Never let the native-tools path crash the LLM node — always
                # fall through to legacy text parsing on any unexpected error.
                logger.warning(
                    f"[NativeToolCalls] gating logic raised "
                    f"(non-fatal, falling back to text parse): {_ntc_err}"
                )
                _native_tc_active = False

            # so far we have get API key, LLM model setup among difference possible choices.

            # Log LLM configuration for debugging
            log_msg = f"🔧 LLM Config (node_config): provider={llm_provider}, model={model_name}, temperature={temperature}, use_thinking={node_use_thinking}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)

            log_msg = f"📝 Prompt length: system={len(final_system_prompt)}, user={len(final_user_prompt)}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

            # Invoke the LLM and update the state
            try:
                import time
                import threading
                import queue
                import asyncio

                def _invoke_with_thread(llm_to_use, timeout_sec: float):
                    """LLM sync invocation via persistent worker thread (no thread-per-call)."""
                    from agent.ec_skills.llm_utils.llm_utils import (
                        _PersistentAsyncWorkerThread,
                        _persistent_worker_runners,
                        _persistent_worker_runners_lock,
                    )

                    worker_name = f"llm-sync-{id(llm_to_use)}"
                    with _persistent_worker_runners_lock:
                        runner = _persistent_worker_runners.get(worker_name)
                        if runner is None or runner._closed:
                            runner = _PersistentAsyncWorkerThread(name=worker_name)
                            _persistent_worker_runners[worker_name] = runner

                    async def _call_llm():
                        return llm_to_use.invoke(recent_context)

                    start_time = time.time()
                    try:
                        # Ensure the worker loop is running
                        runner.start()
                        loop = runner._loop
                        if loop is None:
                            raise RuntimeError(f"Persistent worker loop is unavailable: {worker_name}")

                        import asyncio as _aio

                        async def _invoke_inner():
                            if callable(_call_llm):
                                return await _call_llm()
                            return await _call_llm

                        future = _aio.run_coroutine_threadsafe(_invoke_inner(), loop)
                        # ── Timeout guard: prevent indefinite blocking ──
                        resp = future.result(timeout=timeout_sec)
                        elapsed = time.time() - start_time
                        log_msg = f"⏱️ Request completed in {elapsed:.2f}s"
                        logger.debug(log_msg)
                        send_skill_editor_log("log", log_msg)
                        return resp

                    except TimeoutError:
                        # future.result(timeout=...) raises concurrent.futures.TimeoutError
                        elapsed = time.time() - start_time
                        llm_info = f"{llm_provider}/{model_name}"
                        base_url_info = f" (base_url: {api_host})" if api_host else ""
                        timeout_msg = (
                            f"⏱️ LLM request timed out after {elapsed:.1f}s "
                            f"(limit {timeout_sec}s): {llm_info}{base_url_info} - worker thread still running"
                        )
                        logger.error(timeout_msg)
                        send_skill_editor_log("error", timeout_msg)
                        raise TimeoutError(timeout_msg)

                    except Exception as exc:
                        elapsed = time.time() - start_time
                        error_type = type(exc).__name__
                        error_msg = str(exc)
                        logger.error(
                            f"❌ LLM Invocation Failed\n"
                            f"   Provider: {llm_provider}\n"
                            f"   Model: {model_name}\n"
                            f"   Base URL: {api_host or 'default'}\n"
                            f"   Error Type: {error_type}\n"
                            f"   Error Message: {error_msg}\n"
                            f"   Elapsed: {elapsed:.2f}s"
                        )
                        import traceback
                        logger.debug(f"LLM invocation traceback: {traceback.format_exc()}")
                        send_skill_editor_log("error", f"LLM error: {error_type}: {error_msg}")

                        # Runner failed (loop died) — clear it so next call creates a fresh one
                        with _persistent_worker_runners_lock:
                            if _persistent_worker_runners.get(worker_name) is runner:
                                runner._closed = True
                                del _persistent_worker_runners[worker_name]
                        raise

                async def _invoke_async(llm_to_use, timeout_sec: float):
                    """Async LLM invocation using ainvoke with timeout."""
                    log_msg = "LLM async invocation started"
                    logger.debug(f"🔄{log_msg}")
                    send_skill_editor_log("log", log_msg)
                    
                    start_time = time.time()
                    try:
                        # Use ainvoke with asyncio timeout
                        result = await asyncio.wait_for(
                            llm_to_use.ainvoke(recent_context),
                            timeout=timeout_sec
                        )
                        elapsed = time.time() - start_time
                        
                        log_msg = f"✅ LLM async invocation completed in {elapsed:.2f}s {result}"
                        logger.debug(log_msg)
                        send_skill_editor_log("log", log_msg)
                        return result
                        
                    except asyncio.TimeoutError:
                        # Get LLM info for detailed error message
                        llm_info = f"{llm_provider}/{model_name}"
                        base_url_info = f" (base_url: {api_host})" if api_host else ""
                        timeout_msg = f"⏱️ LLM async request timed out after {timeout_sec}s: {llm_info}{base_url_info}"
                        logger.error(timeout_msg)
                        send_skill_editor_log("error", timeout_msg)
                        raise TimeoutError(timeout_msg)

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
                        import concurrent.futures as _cf
                        _poll_interval = 0.5
                        _deadline = time.time() + timeout_sec + 5
                        while time.time() < _deadline:
                            try:
                                return future.result(timeout=_poll_interval)
                            except _cf.TimeoutError:
                                _tid = (state.get("attributes") or {}).get("task_id") if isinstance(state.get("attributes"), dict) else None
                                if _tid:
                                    try:
                                        from agent.ec_tasks import cancellation_registry as _cr
                                        _evt = _cr.get(_tid)
                                        if _evt and _evt.is_set():
                                            future.cancel()
                                            raise InterruptedError("Task cancelled during LLM call")
                                    except InterruptedError:
                                        raise
                                    except Exception:
                                        pass
                        future.cancel()
                        raise TimeoutError(f"LLM call timed out after {timeout_sec + 5}s")
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

                # ── Cancellation check: abort if task was cancelled before LLM call ──
                task_id_for_cancel = (state.get("attributes") or {}).get("task_id") if isinstance(state.get("attributes"), dict) else None
                if task_id_for_cancel:
                    try:
                        from agent.ec_tasks import cancellation_registry
                        cancel_evt = cancellation_registry.get(task_id_for_cancel)
                        if cancel_evt and cancel_evt.is_set():
                            logger.warning(f"[build_llm_node] Task cancelled before LLM call, aborting node={full_node_name}")
                            send_skill_editor_log("error", "LLM call cancelled by user")
                            raise InterruptedError(f"Task cancelled before LLM call")
                    except Exception:
                        pass

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
                    default_timeout=150.0  # hardcoded final fallback (config_timeout already carries env var)
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
                            send_skill_editor_log("log", log_msg)
                    except Exception as e:
                        logger.warning(f"[LLM_GUARDRAIL] Failed to start timer: {e}")
                
                # Execute LLM call with optional hard timeout
                if use_hard_timeout:
                    import asyncio
                    log_msg = f"[LLM_HARD_TIMEOUT] Using hard timeout ({effective_timeout}s) - will cancel on timeout"
                    logger.info(log_msg)
                    send_skill_editor_log("log", log_msg)
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
                                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
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
                        send_skill_editor_log("error", error_msg)
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

                log_msg = f"✅ LLM response received from {llm_provider} {response}"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)

                # Record token usage to database for the top-panel display
                try:
                    from agent.ec_skills.token_tracker import token_tracker
                    _task_id = (state.get("attributes") or {}).get("task_id") if isinstance(state, dict) else None
                    _run_id = state.get("run_id") if isinstance(state, dict) else None
                    _session_id = (
                        state.get("session_id")
                        or state.get("chat_id")
                        or (state.get("attributes", {}) or {}).get("sessionId")
                    ) if isinstance(state, dict) else None
                    token_tracker.record_llm_usage(
                        response,
                        source_type="skill_llm_node",
                        source_id=full_node_name,
                        source_name=f"{skill_name}::{node_name}",
                        session_id=_session_id,
                        node_type="llm",
                        metadata={
                            "skill_name": skill_name,
                            "node_name": node_name,
                            "task_id": _task_id,
                            "run_id": _run_id,
                            "full_node_name": full_node_name,
                            "llm_provider": llm_provider,
                            "path": "llm_node",
                        },
                    )
                except Exception as _tk_err:
                    logger.debug(f"[TokenTracker] Failed to record LLM usage: {_tk_err}")

                # It's good practice to put results in specific keys
                _t_stage = _time.perf_counter()
                run_post_llm_hook(full_node_name, agent, state, response)
                _perf_llm("post_hook", _t_stage)

                # ── Native function-calling bridge ────────────────────────
                # When tools were bound above, the provider may have returned
                # a typed ``tool_calls`` list on the response.  Overlay it
                # onto ``state['result']['llm_result']`` in the same shape
                # the legacy text-parser would have produced (tool_name,
                # tool_input, OR multi-tool ``tool`` list).  Drop ``message``
                # so the MCP auto-select parser at ``_run_use_mcp_node``
                # short-circuits the JSON-walk and uses the structured
                # fields directly — eliminating the class of bugs where the
                # LLM serialized its tool call into a non-canonical text
                # format (e.g. OpenAI Harmony ``to=send_chat`` headers).
                #
                # If the bound LLM returned NO tool_calls (e.g. it answered
                # in plain content), leave ``llm_result`` as the standard
                # post-hook produced it; the legacy parser still runs and
                # picks up any ``message``/``all_done`` JSON in content.
                try:
                    if _native_tc_active:
                        _resp_tcs = getattr(response, "tool_calls", None) or []
                        if _resp_tcs:
                            _native_tool_call_metric_inc("response_native")
                            _llm_res = (state.get("result") or {}).get("llm_result")
                            if not isinstance(_llm_res, dict):
                                _llm_res = {}
                            if len(_resp_tcs) == 1:
                                _tc = _resp_tcs[0] or {}
                                _llm_res["tool_name"] = _tc.get("name") or ""
                                _llm_res["tool_input"] = _tc.get("args") or {}
                                logger.info(
                                    f"[NativeToolCalls] bridged single tool_call "
                                    f"name={_tc.get('name')!r} "
                                    f"args_keys={list((_tc.get('args') or {}).keys())} "
                                    f"node={full_node_name}"
                                )
                            else:
                                _llm_res["tool"] = [
                                    {"tool_name": (tc or {}).get("name") or "",
                                     "tool_input": (tc or {}).get("args") or {}}
                                    for tc in _resp_tcs
                                ]
                                _llm_res["multi_tool_calls"] = "serial"
                                logger.info(
                                    f"[NativeToolCalls] bridged {len(_resp_tcs)} "
                                    f"serial tool_calls "
                                    f"names={[(tc or {}).get('name') for tc in _resp_tcs]} "
                                    f"node={full_node_name}"
                                )
                            # Drop ``message`` so the legacy text parser at
                            # ``_run_use_mcp_node`` line ~4708 sees structured
                            # fields and skips the JSON-walk path entirely.
                            _llm_res.pop("message", None)

                            if isinstance(state.get("result"), dict):
                                state["result"]["llm_result"] = _llm_res
                                # Promote tool_name/tool_input to the top of
                                # state['result'] for condition-edge readers
                                # (mirrors what standard_post_llm_hook does).
                                if _llm_res.get("tool_name"):
                                    state["result"]["tool_name"] = _llm_res["tool_name"]
                                    if _llm_res.get("tool_input") is not None:
                                        state["result"]["tool_input"] = _llm_res["tool_input"]
                        else:
                            _native_tool_call_metric_inc("response_text_fallback")
                            logger.info(
                                f"[NativeToolCalls] bound LLM returned no tool_calls "
                                f"(falling through to text parse) node={full_node_name} "
                                f"content_len={len(getattr(response, 'content', '') or '')}"
                            )
                except Exception as _bridge_err:
                    # Bridge failure must not break the LLM node.  Log and
                    # leave ``state['result']['llm_result']`` exactly as the
                    # standard post-hook produced it; the legacy parser will
                    # take over from there (incl. the Harmony fallback).
                    logger.warning(
                        f"[NativeToolCalls] bridge raised "
                        f"(non-fatal, leaving legacy llm_result): {_bridge_err}"
                    )

                logger.debug(f"llm_node finished..... {state}")

                # Total time for llm_node_callable (best-effort)
                _perf_llm("total", _t0)

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)

                # Log complete error context at ERROR level for quick problem identification
                import traceback
                logger.error(
                    f"❌ LLM Node Callable Failed\n"
                    f"   Provider: {llm_provider}\n"
                    f"   Model: {model_name}\n"
                    f"   Base URL: {api_host or 'default'}\n"
                    f"   Error Type: {error_type}\n"
                    f"   Error Message: {error_msg}"
                )
                logger.debug(f"Traceback: {traceback.format_exc()}")

                # Detect specific error types and provide helpful messages
                if "AuthenticationError" in error_type or "authentication" in error_msg.lower():
                    user_msg = (
                        f"🔑 LLM Authentication Failed: Invalid API key for {llm_provider}\n"
                        f"   Provider: {llm_provider}\n"
                        f"   Model: {model_name}\n"
                        f"   Base URL: {api_host or 'default'}\n"
                        f"   Error: {error_type}: {error_msg}\n"
                        f"   💡 Action: Check your API key configuration in settings"
                    )
                    logger.error(user_msg)
                    send_skill_editor_log("error", user_msg)
                elif "Error code: 402" in error_msg or "Insufficient Balance" in error_msg or "insufficient balance" in error_msg.lower():
                    user_msg = (
                        f"💰 {llm_provider} 余额不足 (Insufficient Balance)\n"
                        f"   Provider: {llm_provider}\n"
                        f"   Model: {model_name}\n"
                        f"   Base URL: {api_host or 'default'}\n"
                        f"   Error: {error_type}: {error_msg}\n"
                        f"   💡 说明: 您的 {llm_provider} API 账户余额已用尽，无法继续调用\n"
                        f"   💡 Action: 请前往 {llm_provider} 平台充值后再试"
                    )
                    logger.error(user_msg)
                    send_skill_editor_log("error", user_msg)
                elif "RateLimitError" in error_type or "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                    user_msg = (
                        f"🚫 LLM Rate Limit: {llm_provider} quota exceeded\n"
                        f"   Provider: {llm_provider}\n"
                        f"   Model: {model_name}\n"
                        f"   Base URL: {api_host or 'default'}\n"
                        f"   Error: {error_type}: {error_msg}\n"
                        f"   💡 Action: Wait a few minutes and retry, or upgrade your API plan"
                    )
                    logger.error(user_msg)
                    send_skill_editor_log("error", user_msg)
                elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    user_msg = (
                        f"⏱️ LLM Request Timeout: {llm_provider} connection timed out\n"
                        f"   Provider: {llm_provider}\n"
                        f"   Model: {model_name}\n"
                        f"   Base URL: {api_host or 'default'}\n"
                        f"   Error: {error_type}: {error_msg}\n"
                        f"   💡 Troubleshooting:\n"
                        f"      - Check your network connection\n"
                        f"      - Verify the service is responding\n"
                        f"      - Try increasing the timeout setting"
                    )
                    logger.error(user_msg)
                    send_skill_editor_log("error", user_msg)
                elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                    # Check if it's a model not found error
                    if "model" in error_msg.lower() and ("not found" in error_msg.lower() or "does not exist" in error_msg.lower()):
                        user_msg = f"💡 Hint: Model '{model_name}' does not exist. Common OpenAI models: gpt-5.2, gpt-5-mini, gpt-4o, gpt-4o-mini"
                    else:
                        # Detailed connection error with all diagnostic information
                        base_url_info = f" at {api_host}" if api_host else " (using default URL)"
                        user_msg = (
                            f"🔌 Connection Error: Cannot connect to {llm_provider}{base_url_info}\n"
                            f"   Provider: {llm_provider}\n"
                            f"   Model: {model_name}\n"
                            f"   Base URL: {api_host or 'default'}\n"
                            f"   Error Type: {error_type}\n"
                            f"   Error Message: {error_msg}\n"
                            f"   💡 Troubleshooting:\n"
                            f"      - Check if {llm_provider} service is running\n"
                            f"      - Verify the base URL is correct\n"
                            f"      - Ensure network connectivity"
                        )
                    logger.error(user_msg)
                    send_skill_editor_log("error", user_msg)
                else:
                    # Generic error with full details
                    user_msg = (
                        f"❌ LLM Invocation Failed\n"
                        f"   Provider: {llm_provider}\n"
                        f"   Model: {model_name}\n"
                        f"   Base URL: {api_host or 'default'}\n"
                        f"   Error Type: {error_type}\n"
                        f"   Error Message: {error_msg}\n"
                        f"   💡 Check the error message above for specific details"
                    )
                    logger.error(user_msg)
                    send_skill_editor_log("error", user_msg)
                
                state['error'] = user_msg

                # Add detailed error info for debugging
                state['error_details'] = {
                    'error_type': error_type,
                    'provider': llm_provider,
                    'model': model_name,
                    'error_message': error_msg
                }
        else:
            # Cloud worker / no-agent mode: state["messages"] is empty (no GUI agent_id).
            # Still invoke the LLM with the already-formatted base prompts so the graph
            # can progress and conditionals like all_done can become True.
            logger.warning(
                f"LLM NODE [{node_name}]: messages empty - running in cloud worker mode without agent context"
            )
            try:
                # Resolve API key – prefer node config, fall back to env vars
                _raw_key = (api_key or "").strip()

                def _looks_masked_simple(v: str) -> bool:
                    v = (v or "").strip()
                    return not v or any(c in v for c in ("*", "•", "·")) or v.lower().startswith("sk-xxxxx")

                if _looks_masked_simple(_raw_key):
                    _key = _resolve_api_key_from_provider_env_vars(llm_provider)
                else:
                    _key = _raw_key

                _host = (api_host or "").strip()
                _prov = llm_provider

                _llm = _build_runtime_llm(
                    provider_name=_prov,
                    model_name_value=model_name,
                    api_key_value=_key,
                    host_value=_host,
                    temperature_value=temperature,
                    use_thinking=node_use_thinking,
                    raw_provider_name=None,
                    allow_default_openai=True,
                )

                log_msg = f"[LLM_NO_AGENT] Invoking {_prov}/{model_name} with {len(messages)} base messages"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)

                _t_stage = _time.perf_counter()
                _response = _llm.invoke(messages)
                _perf_llm("invoke_no_agent", _t_stage)

                log_msg = f"✅ LLM (no-agent) response from {_prov}: {_response}"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)

                # Record token usage to database for the top-panel display
                try:
                    from agent.ec_skills.token_tracker import token_tracker
                    _task_id = (state.get("attributes") or {}).get("task_id") if isinstance(state, dict) else None
                    _run_id = state.get("run_id") if isinstance(state, dict) else None
                    _session_id = (
                        state.get("session_id")
                        or state.get("chat_id")
                        or (state.get("attributes", {}) or {}).get("sessionId")
                    ) if isinstance(state, dict) else None
                    token_tracker.record_llm_usage(
                        _response,
                        source_type="skill_llm_node",
                        source_id=full_node_name,
                        source_name=f"{skill_name}::{node_name}",
                        session_id=_session_id,
                        node_type="llm",
                        metadata={
                            "skill_name": skill_name,
                            "node_name": node_name,
                            "task_id": _task_id,
                            "run_id": _run_id,
                            "full_node_name": full_node_name,
                            "llm_provider": llm_provider,
                            "path": "llm_node_no_agent",
                        },
                    )
                except Exception as _tk_err:
                    logger.debug(f"[TokenTracker] Failed to record LLM usage (no-agent): {_tk_err}")

                # Parse the response and update state["result"] so loop conditions can evaluate
                from agent.ec_skills.llm_hooks.llm_hooks import standard_post_llm_func
                _parsed = standard_post_llm_func("skid0", full_node_name, state, _response)
                state["result"] = _parsed

                # ── Promote LLM result under node name for condition/template access ──
                # Standard condition exprs use state["result"]["llm_planner"]["execution_plan"]["next_action"]
                # but tool_result uses state["result"]["llm_planner"]. Ensure BOTH paths work.
                inner = _parsed.get("llm_result", {})
                if isinstance(inner, dict) and inner.get("llm_result"):
                    # Double-wrapped: state["result"]["llm_result"]["llm_result"] → promote
                    state["result"][node_name] = inner.get("llm_result")
                elif isinstance(inner, dict):
                    # Single-wrapped: state["result"]["llm_result"] → promote under node_name
                    state["result"][node_name] = inner

                _perf_llm("total", _t0)

            except Exception as _no_agent_err:
                _err_msg = f"LLM error (no-agent mode, provider={llm_provider}, model={model_name}): {type(_no_agent_err).__name__}: {_no_agent_err}"
                logger.error(f"[LLM_NODE] {_err_msg}")
                send_skill_editor_log("error", _err_msg)
                state["error"] = _err_msg

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
    send_skill_editor_log("log", log_msg)

    # Safely extract inline script content; tolerate missing keys and fall back to no-op
    try:
        code_source = (config_metadata or {}).get('script', {}).get('content')
    except Exception:
        code_source = None

    log_msg = f"code_source: {code_source}"
    logger.debug(log_msg)
    send_skill_editor_log("log", log_msg)

    if not code_source or not isinstance(code_source, str):
        err_msg = "Error: 'code' key is missing or invalid in config_metadata for basic_node."
        logger.warning(err_msg)
        send_skill_editor_log("warning", err_msg)
        # Return a no-op function that just passes the state through
        return lambda state, runtime=None, store=None, **kwargs: state

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
                send_skill_editor_log("warning", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, f"ErrorBuildBasicNode {code_source}")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)

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
                send_skill_editor_log("debug", log_msg)
            else:
                log_msg = "No function definition found in inline code for basic node."
                logger.warning(log_msg)
                send_skill_editor_log("warning", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, "ErrorExecutingInlineCodeForBasicNode")
            logger.warning(err_msg)
            send_skill_editor_log("warning", err_msg)
            node_callable = None

    # If callable creation failed, return a no-op function
    if node_callable is None:
        return lambda state, runtime=None, store=None, **kwargs: state

    log_msg = f"done building basic node {node_name}"
    logger.debug(log_msg)
    send_skill_editor_log("debug", log_msg)
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
    send_skill_editor_log("log", log_msg)
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
        logger.warning(err_msg)
        send_skill_editor_log("warning", err_msg)
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
            send_skill_editor_log("error", err_msg)

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
            send_skill_editor_log("error", err_msg)

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
                send_skill_editor_log("log", log_msg)
        except httpx.HTTPStatusError as e:
            err_msg = f"API call failed with status {e.response.status_code}: {e.response.text}"
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
        except Exception as e:
            err_msg = get_traceback(e, "ErrorSyncAPICallable")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
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
            send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
        except Exception as e:
            err_msg = get_traceback(e, "ErrorASyncAPICallable")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
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
    send_skill_editor_log("log", log_msg)

    tool_name = None
    use_llm_auto_select = False
    
    # Run local flag: if True, send passive command to local side instead of calling MCP tool directly
    # The GUI stores the actual setting in data.run_local (top-level run_local may be stale/False)
    run_local = False
    try:
        run_local_val = config_metadata.get('run_local')
        if run_local_val is None or run_local_val is False:
            # Check data.run_local (GUI stores actual config here)
            data_section = config_metadata.get('data') or {}
            run_local_val = data_section.get('run_local') if data_section.get('run_local') is not None else run_local_val
        if run_local_val is None:
            # Also check inputsValues.run_local.content
            run_local_val = ((config_metadata.get('inputsValues') or {}).get('run_local') or {}).get('content')
        run_local = str(run_local_val).lower() in ('true', '1', 'yes', 'on') if run_local_val is not None else False
    except Exception:
        run_local = False
    
    if run_local:
        log_msg = f"[MCP] Node '{node_name}' has run_local=True - will use passive command to execute on local machine"
        logger.info(log_msg)
        send_skill_editor_log("info", log_msg)
    
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
        # Prefer data.callable (actual tool config) over top-level callable (may be placeholder)
        data_section = config_metadata.get('data') or {}
        callable_info = data_section.get('callable') or config_metadata.get('callable') or {}
        callable_id = callable_info.get('id', '') if isinstance(callable_info, dict) else ''
        callable_name = callable_info.get('name', '') if isinstance(callable_info, dict) else ''

    except Exception:
        tool_name = None
        callable_id = ''
        callable_name = ''

    # Check if "llm auto select" mode is enabled
    # Only use auto-select when tool_name is NOT a specific tool
    _tool_is_specific = (tool_name and tool_name not in ('llm-auto-select', 'llm auto select'))
    if not _tool_is_specific and (
        not tool_name 
        or tool_name in ('llm-auto-select', 'llm auto select')
        or callable_id in ('llm-auto-select',)
        or callable_name in ('llm auto select',)
    ):
        use_llm_auto_select = True
        log_msg = f"[MCP] Node '{node_name}' using LLM auto-select mode - tool will be determined at runtime from state['result']['llm_result']"
        logger.info(log_msg)
        send_skill_editor_log("info", log_msg)

    def _get_llm_manager_singleton():
        """Return the cached LLM manager singleton, avoiding repeated JSON parsing."""
        if "singleton" in _LLM_MANAGER_CACHE:
            return _LLM_MANAGER_CACHE["singleton"]
        try:
            from gui.ipc.w2p_handlers.llm_handler import get_llm_manager
            mgr = get_llm_manager()
            _LLM_MANAGER_CACHE["singleton"] = mgr
            return mgr
        except Exception as e:
            logger.debug(f"[build_llm_node] get_llm_manager() failed: {e}")
            return None

    # --- MCP tool input helpers (schema-aware) ---

    def _get_tool_schema_by_name(tool_name: str):
        schemas = None
        try:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
            schemas = getattr(mainwin, 'mcp_tools_schemas', None)
        except Exception:
            pass

        # Cloud fallback: mainwin is None in cloud worker, load from server registry
        if not schemas:
            try:
                from agent.mcp.server.tool_schemas import get_tool_schemas
                schemas = get_tool_schemas() or []
            except Exception:
                schemas = []

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

            # 1b) nested tool_input / input objects (common for tool nodes)
            tool_input = cfg.get('tool_input')
            if isinstance(tool_input, dict):
                if key in tool_input:
                    return tool_input.get(key)
                nested_input = tool_input.get('input')
                if isinstance(nested_input, dict) and key in nested_input:
                    return nested_input.get(key)

            nested_cfg_input = cfg.get('input')
            if isinstance(nested_cfg_input, dict) and key in nested_cfg_input:
                return nested_cfg_input.get(key)

            # 2) inputsValues.<key>.content
            inputs_values = cfg.get('inputsValues')
            if isinstance(inputs_values, dict) and key in inputs_values:
                v = inputs_values.get(key)
                if isinstance(v, dict) and 'content' in v:
                    return v.get('content')
                return v

            # 2b) inputsValues.input.content.<key>
            if isinstance(inputs_values, dict) and isinstance(inputs_values.get('input'), dict):
                v = inputs_values.get('input')
                if isinstance(v, dict) and 'content' in v:
                    content = v.get('content')
                    if isinstance(content, dict) and key in content:
                        return content.get(key)

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
        def _safe_inc_steps(st: dict) -> None:
            if not isinstance(st, dict):
                return
            cur = st.get('n_steps', 0)
            try:
                cur_int = int(cur) if cur is not None else 0
            except Exception:
                cur_int = 0
            st['n_steps'] = cur_int + 1

        # Determine actual tool name and input at runtime
        actual_tool_name = tool_name
        # Tool input can be stored either at state.tool_input (legacy) or
        # nested under state.tool_input[node_name] (per-node).
        actual_tool_input: dict[str, Any] = {}
        try:
            ti = state.get('tool_input', {}) if isinstance(state, dict) else {}
            if isinstance(ti, dict) and isinstance(ti.get(node_name), dict):
                actual_tool_input = ti.get(node_name) or {}
            elif isinstance(ti, dict):
                actual_tool_input = ti
        except Exception:
            actual_tool_input = {}

        def _normalize_run_code_tool_input(inp: Any) -> dict[str, Any]:
            if not isinstance(inp, dict):
                inp = {}

            # Some call sites may wrap tool_input one level deeper.
            if not isinstance(inp.get('input'), dict) and isinstance(inp.get('tool_input'), dict):
                wrapped = inp.get('tool_input')
                if isinstance(wrapped, dict):
                    inp = wrapped

            # Prefer nested input schema: {"input": {...}}
            if isinstance(inp.get('input'), dict):
                normalized: dict[str, Any] = {**inp}
                normalized_input: dict[str, Any] = {**(normalized.get('input') or {})}
            else:
                normalized = {}
                normalized_input = {}

            # Promote common flat keys into input
            for k in ('code', 'args', 'timeout', 'allowed_imports', 'language'):
                if k in inp and k not in normalized_input:
                    normalized_input[k] = inp.get(k)

            # Also accept node-editor naming when passed at runtime
            if 'run_code_source' in inp and 'code' not in normalized_input:
                normalized_input['code'] = inp.get('run_code_source')
            if 'run_code_language' in inp and 'language' not in normalized_input:
                normalized_input['language'] = inp.get('run_code_language')

            # Backfill from node config if missing
            for k in ('code', 'args', 'timeout', 'allowed_imports', 'language'):
                if normalized_input.get(k) is not None:
                    continue
                try:
                    v = _gather_config_value(config_metadata, k)
                    if v is not None:
                        normalized_input[k] = v
                except Exception:
                    pass

            # Node editor stores run_code fields as run_code_source/run_code_language
            # (often either at config_metadata.<key> or config_metadata.data.<key>).
            if not normalized_input.get('code'):
                try:
                    v = (
                        _gather_config_value(config_metadata, 'run_code_source')
                        or (config_metadata.get('run_code_source') if isinstance(config_metadata, dict) else None)
                        or ((config_metadata.get('data') or {}).get('run_code_source') if isinstance(config_metadata, dict) else None)
                    )
                    if isinstance(v, str) and v.strip():
                        normalized_input['code'] = v
                except Exception:
                    pass

            if not normalized_input.get('language'):
                try:
                    v = (
                        _gather_config_value(config_metadata, 'run_code_language')
                        or (config_metadata.get('run_code_language') if isinstance(config_metadata, dict) else None)
                        or ((config_metadata.get('data') or {}).get('run_code_language') if isinstance(config_metadata, dict) else None)
                    )
                    if isinstance(v, str) and v.strip():
                        normalized_input['language'] = v
                except Exception:
                    pass

            # Backfill from state metadata/attributes when config isn't populated
            if not normalized_input.get('code'):
                try:
                    if isinstance(state, dict):
                        attrs = state.get('attributes')
                        meta = state.get('metadata')
                        for container in (attrs, meta):
                            if isinstance(container, dict):
                                v = container.get('code') or container.get('source_code') or container.get('script')
                                if isinstance(v, str) and v.strip():
                                    normalized_input['code'] = v
                                    break
                except Exception:
                    pass

            # Best-effort: alternate code keys
            if not normalized_input.get('code'):
                for alt in ('source_code', 'source', 'script', 'run_code_source'):
                    v = inp.get(alt)
                    if isinstance(v, str) and v.strip():
                        normalized_input['code'] = v
                        break

            # Coerce args: allow empty string in UI, but MCP run_code expects an object
            args_val = normalized_input.get('args')
            if isinstance(args_val, str):
                if not args_val.strip():
                    normalized_input['args'] = {}
                else:
                    try:
                        parsed_args = json.loads(args_val)
                        normalized_input['args'] = parsed_args if isinstance(parsed_args, dict) else {"_raw": args_val}
                    except Exception:
                        normalized_input['args'] = {"_raw": args_val}
            elif args_val is None:
                normalized_input['args'] = {}
            elif not isinstance(args_val, dict):
                normalized_input['args'] = {}

            # Coerce timeout to int when possible
            timeout_val = normalized_input.get('timeout')
            if isinstance(timeout_val, str):
                try:
                    normalized_input['timeout'] = int(float(timeout_val.strip()))
                except Exception:
                    pass

            # Coerce allowed_imports to list[str]
            allowed_imports_val = normalized_input.get('allowed_imports')
            if allowed_imports_val is None:
                normalized_input['allowed_imports'] = []
            elif isinstance(allowed_imports_val, str):
                s = allowed_imports_val.strip()
                if not s:
                    normalized_input['allowed_imports'] = []
                else:
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, list):
                            normalized_input['allowed_imports'] = [str(x) for x in parsed]
                        else:
                            normalized_input['allowed_imports'] = [s]
                    except Exception:
                        normalized_input['allowed_imports'] = [s]
            elif isinstance(allowed_imports_val, list):
                normalized_input['allowed_imports'] = [str(x) for x in allowed_imports_val]
            else:
                normalized_input['allowed_imports'] = []
 
            # Always return nested form.
            # MCP server `run_code` will ignore unknown keys like language, but
            # our passive protocol expects language+code for consistent tooling.
            return {'input': normalized_input}
        
        # Multi-tool state (set inside use_llm_auto_select block when tool is a list)
        _multi_tool_list = None
        _multi_tool_mode = 'serial'

        # --- LLM Auto-Select Mode ---
        if use_llm_auto_select:
            log_msg = f"🤖 Executing MCP node '{node_name}' in LLM auto-select mode"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)

            llm_result = (state.get('result') or {}).get('llm_result') or {}

            # Snapshot propagated work_result so the LLM response cannot blank it
            _propagated_work_result = dict(llm_result.get('work_result') or {}) if isinstance(llm_result, dict) else {}

            if 'message' in llm_result and isinstance(llm_result.get('message'), str):
                message_content = llm_result['message']
                logger.debug(f"[MCP Auto-Select] Found 'message' wrapper, attempting to parse: {message_content[:300]}...")

                parsed_objects = []
                idx = 0
                while idx < len(message_content):
                    start_idx = message_content.find('{', idx)
                    if start_idx < 0:
                        break

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

                # Collect ALL tool-call objects from the LLM output (not just the first)
                _all_tool_objs = []
                for obj in parsed_objects:
                    nested_tool_obj = {}
                    if isinstance(obj, dict):
                        for _tool_key in ('tool', 'tool_use', 'next_tool_use', 'next_tool'):
                            _candidate = obj.get(_tool_key)
                            if isinstance(_candidate, dict):
                                nested_tool_obj = _candidate
                                break
                    if isinstance(obj, dict) and (
                        'next_tool_name' in obj
                        or 'tool_name' in obj
                        or 'tool_name' in nested_tool_obj
                    ):
                        _all_tool_objs.append(obj)

                # ── Harmony-channel fallback ─────────────────────────────
                # GPT-5 / o-series models occasionally slip into the OpenAI
                # Harmony tool-call dialect, putting the tool name in a
                # free-text routing header instead of a JSON ``tool_name``
                # key, e.g.:
                #
                #   to=send_chat <hallucinated tokens> =json
                #   {"input": {...}}
                #   {"all_done": true, "work_done": true}
                #   done()
                #
                # The body JSON is still valid input but our strict
                # parser above sees ``{"input": ...}`` with no
                # ``tool_name`` and silently drops the tool call, while
                # still capturing the trailing ``{"all_done": true}``
                # below.  Net effect: the worker reports "all_done"
                # without ever invoking the tool.
                #
                # Liveness incident 2026-04-29 09:08:17.176 (eCan.log.1
                # line 10286): customer ``陆地飞鱼``'s reply to
                # ``我要买衣服`` was lost this way and stayed
                # ``already_dispatched`` in the front-desk dedup map for
                # the rest of the run.
                #
                # Adopt the first ``input``-bearing JSON as the tool
                # call when (a) no proper tool object was found AND
                # (b) the message contains a Harmony-style ``to=<name>``
                # header.  This keeps well-formed outputs untouched
                # while recovering the malformed-but-intent-clear case.
                if not _all_tool_objs:
                    _harmony_match = re.search(
                        r'\bto\s*=\s*([A-Za-z_][A-Za-z0-9_\-]*)',
                        message_content,
                    )
                    if _harmony_match:
                        _harmony_tool_name = _harmony_match.group(1)
                        _adopted = None
                        for obj in parsed_objects:
                            if not isinstance(obj, dict):
                                continue
                            # Skip pure completion-flag objects — those
                            # belong to the flags collector below.
                            if set(obj.keys()) <= {'all_done', 'work_done'}:
                                continue
                            if 'input' in obj or 'tool_input' in obj:
                                _adopted = dict(obj)
                                _adopted['tool_name'] = _harmony_tool_name
                                _all_tool_objs.append(_adopted)
                                logger.warning(
                                    "[MCP Auto-Select] Harmony-style tool call "
                                    f"recovered: tool_name='{_harmony_tool_name}' "
                                    f"from `to=` header, body keys={list(obj.keys())}. "
                                    "LLM emitted non-standard format; treating as "
                                    "if `tool_name` was present in the JSON."
                                )
                                break
                        if _adopted is None:
                            logger.warning(
                                f"[MCP Auto-Select] Detected Harmony header "
                                f"`to={_harmony_tool_name}` but no input-bearing "
                                "JSON body found; cannot recover tool call. "
                                f"Parsed objects: {[list(o.keys()) if isinstance(o, dict) else type(o).__name__ for o in parsed_objects]}"
                            )

                # Collect completion flags (all_done, work_done) from non-tool
                # JSON objects.  The LLM often emits these as a separate object
                # after the tool-call JSON, e.g.:
                #   {"tool_name":"send_chat", ...}
                #   {"all_done": true, "work_done": true}
                # Without merging, the condition node never sees all_done and
                # the skill loop never exits.
                _completion_flags: dict[str, Any] = {}
                for obj in parsed_objects:
                    if not isinstance(obj, dict):
                        continue
                    # Skip objects that are tool calls (already in _all_tool_objs)
                    if obj in _all_tool_objs:
                        continue
                    for _flag_key in ('all_done', 'work_done'):
                        if _flag_key in obj:
                            _completion_flags[_flag_key] = obj[_flag_key]
                if _completion_flags:
                    logger.info(f"[MCP Auto-Select] Captured completion flags from non-tool objects: {_completion_flags}")

                if len(_all_tool_objs) > 1:
                    # Multiple tool calls found — bundle as a multi-tool list so the
                    # multi-tool executor (serial mode) runs them all sequentially.
                    llm_result = {'tool': _all_tool_objs, 'multi_tool_calls': 'serial'}
                    llm_result.update(_completion_flags)
                    logger.info(f"[MCP Auto-Select] Found {len(_all_tool_objs)} tool calls, bundling as serial multi-tool")
                    if 'result' in state and isinstance(state['result'], dict):
                        state['result']['llm_result'] = llm_result
                elif len(_all_tool_objs) == 1:
                    llm_result = _all_tool_objs[0]
                    llm_result.update(_completion_flags)
                    logger.debug(f"[MCP Auto-Select] Found target JSON with next tool selection: {_all_tool_objs[0]}")
                    if 'result' in state and isinstance(state['result'], dict):
                        state['result']['llm_result'] = _all_tool_objs[0]
                        logger.debug(f"[MCP Auto-Select] Updated state['result']['llm_result'] with parsed object")
                elif _completion_flags:
                    # No tool calls but we have completion flags (e.g. LLM just
                    # said {"all_done": true} without any tool call).
                    llm_result = _completion_flags
                    if 'result' in state and isinstance(state['result'], dict):
                        state['result']['llm_result'] = llm_result
                    logger.info(f"[MCP Auto-Select] No tool calls, but found completion flags: {_completion_flags}")

            # Merge propagated work_result back: LLM may have overwritten with empty values
            if _propagated_work_result and isinstance(llm_result, dict):
                llm_wr = llm_result.get('work_result')
                if isinstance(llm_wr, dict):
                    for _pk, _pv in _propagated_work_result.items():
                        if _pv and not llm_wr.get(_pk):
                            llm_wr[_pk] = _pv
                else:
                    llm_result['work_result'] = dict(_propagated_work_result)
                # Also update state in case llm_result is a copy
                if 'result' in state and isinstance(state.get('result'), dict):
                    sr = state['result'].get('llm_result')
                    if isinstance(sr, dict):
                        sr_wr = sr.setdefault('work_result', {})
                        if isinstance(sr_wr, dict):
                            for _pk, _pv in _propagated_work_result.items():
                                if _pv and not sr_wr.get(_pk):
                                    sr_wr[_pk] = _pv
                logger.debug(f"[MCP Auto-Select] Preserved propagated work_result: {_propagated_work_result}")

            work_done = llm_result.get('work_done', False)

            # --- Multi-tool detection: llm_result['tool'] may be a list of {tool_name, tool_input} ---
            for _mtk in ('tool', 'tool_use', 'next_tool_use', 'next_tool'):
                _mtv = llm_result.get(_mtk) if isinstance(llm_result, dict) else None
                if isinstance(_mtv, list) and _mtv:
                    _multi_tool_list = _mtv
                    _multi_tool_mode = (llm_result.get('multi_tool_calls') or 'serial').lower().strip()
                    break

            nested_tool = {}
            for _tool_key in ('tool', 'tool_use', 'next_tool_use', 'next_tool'):
                _candidate = llm_result.get(_tool_key) if isinstance(llm_result, dict) else None
                if isinstance(_candidate, dict):
                    nested_tool = _candidate
                    break

            next_tool_name = (
                llm_result.get('next_tool_name', '')
                or llm_result.get('tool_name', '')
                or nested_tool.get('tool_name', '')
            )
            next_tool_input = (
                llm_result.get('next_tool_input')
                or llm_result.get('tool_input')
                or llm_result.get('input')
                or nested_tool.get('tool_input')
                or nested_tool.get('input')
                or {}
            )

            log_msg = f"[MCP Auto-Select] work_done={work_done}, next_tool_name='{next_tool_name}', next_tool_input={next_tool_input}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

            def _sync_completion_flags(st: dict[str, Any]) -> None:
                try:
                    if not isinstance(st, dict):
                        return
                    result_obj = st.setdefault('result', {})
                    if not isinstance(result_obj, dict):
                        return
                    llm_obj = result_obj.setdefault('llm_result', {})
                    if not isinstance(llm_obj, dict):
                        return
                    if 'all_done' not in llm_obj:
                        llm_obj['all_done'] = False
                except Exception:
                    return

            if work_done:
                # If there's still a pending tool call (e.g. send_chat), execute it
                # before honoring work_done — the LLM intended the tool to run first.
                _has_pending_tool = (
                    (next_tool_name and isinstance(next_tool_name, str) and next_tool_name.strip())
                    or _multi_tool_list is not None
                )
                if not _has_pending_tool:
                    _sync_completion_flags(state)
                    log_msg = f"[MCP Auto-Select] work_done=True, no pending tool call, skipping for node '{node_name}'"
                    logger.info(log_msg)
                    send_skill_editor_log("info", log_msg)
                    # ── Silent-drop visibility (Fix B observability) ──
                    # If the LLM explicitly emitted `done(success=False, ...)`
                    # alongside work_done=True, the loop exits without sending
                    # any reply.  That used to log only at INFO and was easy
                    # to miss when a customer's message went unanswered.  Re-
                    # log at WARNING so an operator can find these in eCan.log.
                    try:
                        _raw_msg = ""
                        if isinstance(llm_result, dict):
                            _raw_msg = str(llm_result.get('message', '') or '')
                        if not _raw_msg:
                            _raw_msg = str(state.get('result', {}).get('llm_result', {}).get('message', '') or '')
                        if 'done(success=false' in _raw_msg.lower():
                            _drop_msg = (
                                f"[Silent Drop] node='{node_name}' emitted "
                                f"done(success=False) with no tool call — NO REPLY "
                                f"WAS SENT. Raw LLM output: {_raw_msg!r}"
                            )
                            logger.warning(_drop_msg)
                            send_skill_editor_log("warning", _drop_msg)
                    except Exception:
                        pass
                    return state
                else:
                    log_msg = f"[MCP Auto-Select] work_done=True but has pending tool '{next_tool_name}' — executing tool first, then marking done"
                    logger.info(log_msg)
                    send_skill_editor_log("info", log_msg)
                    # Fall through to tool execution below; completion flags
                    # will be applied after the tool call completes.

            if (not next_tool_name or not isinstance(next_tool_name, str) or not next_tool_name.strip()) and _multi_tool_list is None:
                if 'message' in llm_result and not llm_result.get('message', '').strip():
                    log_msg = f"[MCP Auto-Select] WARNING: LLM returned empty message with no next_tool_name. Setting work_done=True to exit loop gracefully."
                    logger.warning(log_msg)
                    send_skill_editor_log("warning", log_msg)
                elif 'input' in llm_result and 'next_tool_name' not in llm_result:
                    log_msg = f"[MCP Auto-Select] WARNING: LLM returned invalid format (just 'input' without 'next_tool_name'). Expected format: {{work_done, next_tool_name, next_tool_input}}. Got: {list(llm_result.keys())}. Setting work_done=True."
                    logger.warning(log_msg)
                    send_skill_editor_log("warning", log_msg)
                else:
                    log_msg = f"[MCP Auto-Select] next_tool_name is empty or not provided. LLM result keys: {list(llm_result.keys())}. Skipping tool call for node '{node_name}'"
                    logger.info(log_msg)
                    send_skill_editor_log("info", log_msg)

                if 'result' in state and isinstance(state['result'], dict):
                    if 'llm_result' not in state['result']:
                        state['result']['llm_result'] = {}
                    state['result']['llm_result']['work_done'] = True
                    state['result']['llm_result']['all_done'] = True
                _sync_completion_flags(state)
                return state

            actual_tool_name = next_tool_name.strip()

            tool_schema = _get_tool_schema_by_name(actual_tool_name)
            if not tool_schema:
                log_msg = f"[MCP Auto-Select] Tool '{actual_tool_name}' not found in MCP tool registry, skipping tool call for node '{node_name}'"
                logger.warning(log_msg)
                send_skill_editor_log("warning", log_msg)
                return state

            if isinstance(next_tool_input, dict) and next_tool_input:
                actual_tool_input = next_tool_input

            log_msg = f"[MCP Auto-Select] Resolved tool: '{actual_tool_name}' with input: {actual_tool_input}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)
        else:
            log_msg = f"🤖 Executing node MCP tool node for tool: {actual_tool_name}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)

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

            # Auto-inject agent_id from state context when tool expects it but LLM left it blank.
            # The LLM has no way to know the current agent_id; it lives in state['attributes'].
            try:
                _ctx_agent_id = (state.get('attributes') or {}).get('agent_id', '')
                if _ctx_agent_id:
                    for _target in (actual_tool_input, actual_tool_input.get('input')):
                        if isinstance(_target, dict) and 'agent_id' in _target and not _target.get('agent_id'):
                            _target['agent_id'] = _ctx_agent_id
                        # Also auto-inject sender_agent_id for send_chat (same runtime agent_id).
                        if isinstance(_target, dict) and 'sender_agent_id' in _target and not _target.get('sender_agent_id'):
                            _target['sender_agent_id'] = _ctx_agent_id
                        # Auto-inject recipient_agent_id for send_chat replies:
                        # when the LLM leaves it blank (or omits it entirely), fill from
                        # the last chat_message event's senderId so reply-to routing works.
                        if isinstance(_target, dict) and 'sender_agent_id' in _target and not _target.get('recipient_agent_id'):
                            if not _target.get('recipient_agent_name'):
                                _evt_sender = ''
                                for _evt in reversed(state.get('events') or []):
                                    _ec = _evt.get('context') if isinstance(_evt, dict) else None
                                    if isinstance(_ec, dict) and _ec.get('senderId'):
                                        _evt_sender = str(_ec['senderId'])
                                        break
                                if not _evt_sender:
                                    # Fallback: check prompt_refs["events"] compact form
                                    _pr_events = (state.get('prompt_refs') or {}).get('events', '')
                                    if isinstance(_pr_events, str) and 'senderId' in _pr_events:
                                        try:
                                            _evt_sender = json.loads(_pr_events).get('senderId', '')
                                        except Exception:
                                            pass
                                if _evt_sender and _evt_sender != _ctx_agent_id:
                                    _target['recipient_agent_id'] = _evt_sender
                                    logger.info(f"[MCP Auto-Fill] recipient_agent_id backfilled from event senderId={_evt_sender}")
            except Exception:
                pass

            if actual_tool_name == 'send_chat':
                actual_tool_input = _augment_send_chat_reply_with_source_turn(
                    actual_tool_input, state
                )

            # Preserve both legacy (dict with 'input') and per-node tool_input maps.
            try:
                existing_ti = state.get('tool_input') if isinstance(state, dict) else None
                if isinstance(existing_ti, dict) and node_name in existing_ti and isinstance(existing_ti.get(node_name), dict):
                    existing_ti[node_name] = actual_tool_input
                    state['tool_input'] = existing_ti
                elif isinstance(existing_ti, dict) and ('input' not in existing_ti):
                    existing_ti[node_name] = actual_tool_input
                    state['tool_input'] = existing_ti
                else:
                    state['tool_input'] = actual_tool_input
            except Exception:
                state['tool_input'] = actual_tool_input

            log_msg = f"tool_input backfilled for {actual_tool_name}: {state['tool_input']}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

        except Exception as e:
            err_msg = get_traceback(e, "ErrorMCPToolCallable")
            logger.debug(err_msg)
            send_skill_editor_log("error", err_msg)

        # Capture for closure.
        # If the tool input has a nested 'input' sub-object alongside top-level fields
        # (produced by backfill), merge them: nested defaults first, top-level values win.
        # This ensures the LLM's runtime values (at top level) are not shadowed by the
        # empty defaults inside the nested 'input' wrapper.
        _actual_tool_name = actual_tool_name
        if (isinstance(actual_tool_input, dict)
                and 'input' in actual_tool_input
                and isinstance(actual_tool_input.get('input'), dict)):
            # Backfill produces: {'input': {empty_defaults}, 'field': runtime_value, ...}
            # Merge: nested defaults first, then top-level non-empty values override.
            # Keep the 'input' wrapper since MCP schema requires it as root property.
            _nested = actual_tool_input['input']
            _top = {k: v for k, v in actual_tool_input.items()
                    if k != 'input' and v not in ('', None, [], {})}
            _merged_inner = {**_nested, **_top}
            _actual_tool_input = {'input': _merged_inner}
            logger.info(f"[MCP] Merged nested+top-level input for '{_actual_tool_name}': {_actual_tool_input}")
        else:
            _actual_tool_input = actual_tool_input

        def _extract_tool_result_text(result) -> str:
            """Extract readable text from MCP CallToolResult object.

            MCP CallToolResult has .content = [TextContent(text=...), ...]
            Stringifying the object via f-string only shows the repr, which
            truncates the actual text.  This helper pulls out the real text
            so the LLM can see the full tool output in its conversation history.
            """
            try:
                if hasattr(result, 'content') and isinstance(result.content, list):
                    text_parts = []
                    for c in result.content:
                        if hasattr(c, 'text'):
                            text_parts.append(c.text)
                    if text_parts:
                        return "\n".join(text_parts)
            except Exception:
                pass
            return str(result)

        def _extract_tool_result_payload(result):
            try:
                structured = getattr(result, 'structuredContent', None)
                if isinstance(structured, dict):
                    return structured
            except Exception:
                pass
            try:
                meta = getattr(result, 'meta', None)
                if isinstance(meta, dict):
                    if isinstance(meta.get('task_result'), dict):
                        return meta.get('task_result')
                    # Check for tool-specific result keys (e.g. send_chat_result)
                    for mk, mv in meta.items():
                        if mk.endswith('_result') and isinstance(mv, dict) and 'success' in mv:
                            return mv
                    # Check if meta itself has 'success' (flat meta payload)
                    if 'success' in meta:
                        return meta
            except Exception:
                pass
            try:
                if hasattr(result, 'content') and isinstance(result.content, list):
                    for c in result.content:
                        c_meta = getattr(c, 'meta', None)
                        if isinstance(c_meta, dict):
                            if isinstance(c_meta.get('task_result'), dict):
                                return c_meta.get('task_result')
                            # Check for tool-specific result keys
                            for mk, mv in c_meta.items():
                                if mk.endswith('_result') and isinstance(mv, dict) and 'success' in mv:
                                    return mv
                            # Flat meta with success
                            if 'success' in c_meta:
                                return c_meta
            except Exception:
                pass
            # Last resort: parse the text content for JSON with success field
            try:
                if hasattr(result, 'content') and isinstance(result.content, list):
                    for c in result.content:
                        txt = getattr(c, 'text', None)
                        if isinstance(txt, str) and '"success"' in txt:
                            import json as _json
                            parsed = _json.loads(txt)
                            if isinstance(parsed, dict) and 'success' in parsed:
                                return parsed
            except Exception:
                pass
            # Also check isError flag on the result itself — if isError is explicitly
            # False and we found no payload, synthesize a success indicator so callers
            # don't wrongly treat the tool as failed.
            try:
                is_error = getattr(result, 'isError', None)
                if is_error is False:
                    return {"success": True, "_inferred_from_isError": True}
            except Exception:
                pass
            return {}

        def _apply_mcp_result_to_llm_state(st: dict, tool_name: str, result) -> None:
            try:
                if not isinstance(st, dict):
                    return
                result_obj = st.setdefault('result', {})
                if not isinstance(result_obj, dict):
                    return
                llm_obj = result_obj.setdefault('llm_result', {})
                if not isinstance(llm_obj, dict):
                    return
                work_result = llm_obj.setdefault('work_result', {})
                if not isinstance(work_result, dict):
                    llm_obj['work_result'] = {}
                    work_result = llm_obj['work_result']

                payload = _extract_tool_result_payload(result)
                success = bool(isinstance(payload, dict) and payload.get('success'))
                if success:
                    work_result['last_action_succeeded'] = True

                if tool_name == 'create_agent_task_with_skill' and success:
                    task_id = str(payload.get('task_id') or '')
                    work_result['skill_task_created'] = True
                    if task_id:
                        work_result['created_task_id'] = task_id
                    llm_obj['all_done'] = False
                elif tool_name == 'launch_agent_task' and success:
                    work_result['skill_task_launched'] = True
                    task_id = str(payload.get('task_id') or payload.get('run_id') or '')
                    if task_id:
                        work_result['created_task_id'] = task_id
                    llm_obj['all_done'] = False
                elif tool_name == 'os_screen_capture' and success:
                    work_result['screen_capture_done'] = True
                    llm_obj['all_done'] = False
                elif tool_name == 'send_chat' and success:
                    work_result['chat_sent'] = True
                    work_result['last_action_succeeded'] = True
                    # Extract recipient info if available
                    recipient = payload.get('recipient_name') or payload.get('recipient') or ''
                    if recipient:
                        work_result['chat_sent_to'] = recipient
                logger.info(
                    f"[MCP Result Propagation] tool={tool_name} success={success} "
                    f"work_result={work_result}"
                )
            except Exception:
                return

        async def run_tool_call():
            """A local async function to perform the actual tool call.

            Execution strategy:
            - On the desktop (local/cloud skill with GUI): call via MCP HTTP
              server at 127.0.0.1:4668 as before.
            - In the cloud worker container (no local MCP server): call the
              tool handler function **directly in-process** from
              ``tool_function_mapping`` so that no HTTP round-trip is needed.
              This is the correct behaviour for cloud skills and local skills
              where "local" means the current host.  Hybrid-cloud skills that
              need to reach the remote client's machine use the *run_local*
              path (passive transport) instead, which is handled separately.
            """
            log_msg = f"Calling MCP tool '{_actual_tool_name}' with input: {_actual_tool_input}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)
            from config.constants import DEFAULT_API_TIMEOUT
            timeout = config_metadata.get('timeout', DEFAULT_API_TIMEOUT)

            try:
                llm_manager = _get_llm_manager_singleton()
                all_providers = (llm_manager.get_all_providers() or []) if llm_manager else []
            except Exception:
                pass

            # --- Cloud-worker direct invocation (no local MCP HTTP server) ---
            _is_cloud = os.environ.get("ECAN_MODE") == "worker"
            if not _is_cloud:
                try:
                    from app_context import AppContext
                    _is_cloud = AppContext.get_main_window() is None
                except Exception:
                    pass

            if _is_cloud:
                try:
                    # Import tool handler directly from its source module,
                    # bypassing server.py which has GUI dependencies
                    # (pynput/pyautogui/PyGetWindow) that fail on headless Linux.
                    tool_func = _resolve_cloud_tool_func(_actual_tool_name)
                    if tool_func is not None:
                        log_msg = (
                            f"[CLOUD_DIRECT] Invoking tool '{_actual_tool_name}' "
                            f"directly in-process (no MCP HTTP server in cloud)"
                        )
                        logger.info(log_msg)
                        send_skill_editor_log("log", log_msg)

                        # Tool handlers have signature (mainwin, args).
                        # In the cloud worker there is no GUI mainwin; pass None.
                        content_blocks = await tool_func(None, _actual_tool_input)

                        # Wrap the raw content blocks into a CallToolResult so
                        # the downstream code sees the same shape as a real MCP
                        # response.
                        from mcp.types import CallToolResult
                        return CallToolResult(content=content_blocks, isError=False)
                    else:
                        log_msg = (
                            f"[CLOUD_DIRECT] Tool '{_actual_tool_name}' not in "
                            f"cloud tool registry — falling back to MCP HTTP call"
                        )
                        logger.warning(log_msg)
                        send_skill_editor_log("warning", log_msg)
                except Exception as _cd_err:
                    log_msg = (
                        f"[CLOUD_DIRECT] Direct invocation failed for "
                        f"'{_actual_tool_name}': {_cd_err} — falling back to MCP HTTP call"
                    )
                    logger.warning(log_msg)
                    send_skill_editor_log("warning", log_msg)

            return await mcp_call_tool(_actual_tool_name, _actual_tool_input, timeout=timeout)

        # ============================================================
        # Multi-Tool Mode: execute list of tools from llm_result['tool']
        # Triggered when llm_result['tool'] is a list instead of a dict.
        # llm_result['multi_tool_calls'] controls execution order:
        #   "parallel" → asyncio.gather (concurrent)
        #   "serial"   → sequential in list order (default)
        # ============================================================
        if _multi_tool_list is not None:
            log_msg = f"[MCP Multi-Tool] Node '{node_name}' executing {len(_multi_tool_list)} tools in '{_multi_tool_mode}' mode"
            logger.info(log_msg)
            send_skill_editor_log("info", log_msg)

            # Persist mode in state for downstream inspection
            if 'result' in state and isinstance(state['result'], dict):
                _lr = state['result'].setdefault('llm_result', {})
                if isinstance(_lr, dict):
                    _lr['multi_tool_calls'] = _multi_tool_mode

            async def _run_single_mcp_tool(t_name: str, t_input: dict):
                """Call one MCP tool, honouring cloud-direct vs HTTP path."""
                from config.constants import DEFAULT_API_TIMEOUT
                _mt_timeout = config_metadata.get('timeout', DEFAULT_API_TIMEOUT)
                _is_cloud_mt = os.environ.get("ECAN_MODE") == "worker"
                if not _is_cloud_mt:
                    try:
                        from app_context import AppContext
                        _is_cloud_mt = AppContext.get_main_window() is None
                    except Exception:
                        pass
                if _is_cloud_mt:
                    try:
                        _tf = _resolve_cloud_tool_func(t_name)
                        if _tf is not None:
                            _content = await _tf(None, t_input)
                            from mcp.types import CallToolResult as _MTR
                            return _MTR(content=_content, isError=False)
                    except Exception as _mte:
                        logger.warning(f"[MCP Multi-Tool] Cloud-direct failed for '{t_name}': {_mte}, falling back to HTTP")
                return await mcp_call_tool(t_name, t_input, timeout=_mt_timeout)

            # --- Inter-tool data wiring helpers ---

            def _resolve_placeholders(obj, ctx: dict):
                """Recursively replace {{key}} placeholders in tool_input with results
                from previously executed tools.

                ctx keys:
                  - str tool name  → text result of that tool (last call wins)
                  - int index      → text result at that 0-based position in the list
                  - str alias      → text result for a tool declared with "alias"

                Supported syntax in any string value:
                  {{rag_query}}        — result of the tool named rag_query
                  {{tool_result[2]}}   — result of tool at index 2
                  {{my_alias}}         — result of tool with alias "my_alias"

                A placeholder that has no match is left as-is so the LLM can
                detect the gap rather than silently receiving an empty string.
                """
                import re as _re
                if isinstance(obj, dict):
                    return {k: _resolve_placeholders(v, ctx) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_resolve_placeholders(v, ctx) for v in obj]
                if isinstance(obj, str):
                    def _replace(m):
                        key = m.group(1).strip()
                        # {{tool_result[N]}} — index form
                        _idx_m = _re.fullmatch(r'tool_result\[(\d+)\]', key)
                        if _idx_m:
                            idx = int(_idx_m.group(1))
                            if idx in ctx:
                                return ctx[idx]
                        # bare name / alias form
                        if key in ctx:
                            return ctx[key]
                        return m.group(0)  # unresolved: leave as-is
                    return _re.sub(r'\{\{(.+?)\}\}', _replace, obj)
                return obj

            # Resolve, backfill, and coerce each tool call.
            # Each entry: (tool_name, tool_input, pipe_output_to, alias)
            _tool_calls_to_run = []
            for _item in _multi_tool_list:
                if not isinstance(_item, dict):
                    continue
                _tn = (_item.get('tool_name') or _item.get('next_tool_name') or '').strip()
                _ti = (
                    _item.get('tool_input')
                    or _item.get('next_tool_input')
                    or _item.get('input')
                    or {}
                )
                if not isinstance(_ti, dict):
                    _ti = {}
                _pipe_to = _item.get('pipe_output_to')   # Option B: field name string or None
                _alias   = (_item.get('alias') or '').strip()  # Option A: named alias
                if not _tn:
                    logger.warning(f"[MCP Multi-Tool] Skipping item with no tool_name: {_item}")
                    continue
                _ts = _get_tool_schema_by_name(_tn)
                _tr_root = _normalize_schema_root(_ts) if _ts else {}
                if _tr_root and not _validate_tool_input_against_schema(_ti, _tr_root):
                    _ci = _build_input_from_config(config_metadata, _tr_root)
                    _ti = _merge_inputs(_ti, _ci)
                if _tr_root:
                    _ti = _coerce_all_inputs(_ti, _tr_root)
                # Auto-inject agent_id / sender_agent_id / recipient_agent_id
                # (mirrors the single-tool auto-inject at line ~4423)
                try:
                    _ctx_agent_id_mt = (state.get('attributes') or {}).get('agent_id', '')
                    if _ctx_agent_id_mt:
                        for _tgt_mt in (_ti, _ti.get('input') if isinstance(_ti, dict) else None):
                            if not isinstance(_tgt_mt, dict):
                                continue
                            if 'agent_id' in _tgt_mt and not _tgt_mt.get('agent_id'):
                                _tgt_mt['agent_id'] = _ctx_agent_id_mt
                            if 'sender_agent_id' in _tgt_mt and not _tgt_mt.get('sender_agent_id'):
                                _tgt_mt['sender_agent_id'] = _ctx_agent_id_mt
                            if 'sender_agent_id' in _tgt_mt and not _tgt_mt.get('recipient_agent_id'):
                                if not _tgt_mt.get('recipient_agent_name'):
                                    _evt_sender_mt = ''
                                    for _evt_mt in reversed(state.get('events') or []):
                                        _ec_mt = _evt_mt.get('context') if isinstance(_evt_mt, dict) else None
                                        if isinstance(_ec_mt, dict) and _ec_mt.get('senderId'):
                                            _evt_sender_mt = str(_ec_mt['senderId'])
                                            break
                                    if not _evt_sender_mt:
                                        _pr_events_mt = (state.get('prompt_refs') or {}).get('events', '')
                                        if isinstance(_pr_events_mt, str) and 'senderId' in _pr_events_mt:
                                            try:
                                                _evt_sender_mt = json.loads(_pr_events_mt).get('senderId', '')
                                            except Exception:
                                                pass
                                    if _evt_sender_mt and _evt_sender_mt != _ctx_agent_id_mt:
                                        _tgt_mt['recipient_agent_id'] = _evt_sender_mt
                                        logger.info(f"[MCP Multi-Tool Auto-Fill] recipient_agent_id backfilled from event senderId={_evt_sender_mt} for tool={_tn}")
                except Exception:
                    pass
                if _tn == 'send_chat':
                    _ti = _augment_send_chat_reply_with_source_turn(_ti, state)
                _tool_calls_to_run.append((_tn, _ti, _pipe_to, _alias))

            if not _tool_calls_to_run:
                log_msg = f"[MCP Multi-Tool] No valid tool calls in list, skipping"
                logger.warning(log_msg)
                send_skill_editor_log("warning", log_msg)
                return state

            from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
            import asyncio as _asyncio_mt

            if _multi_tool_mode == 'parallel':
                # Parallel: no inter-tool wiring (results not available at dispatch time)
                async def _run_all_parallel_mt():
                    return await _asyncio_mt.gather(
                        *[_run_single_mcp_tool(tn, ti) for tn, ti, _, __ in _tool_calls_to_run],
                        return_exceptions=True,
                    )
                _multi_results = run_async_in_sync(_run_all_parallel_mt())
            else:
                # Serial: resolve placeholders and pipe_output_to before each call
                async def _run_all_serial_mt():
                    _out = []
                    # results_ctx: keyed by index (int), tool_name (str), and alias (str)
                    _rctx: dict = {}
                    _pending_pipe: dict | None = None  # {field: text} to inject into next call
                    for _idx, (_tn_s, _ti_s, _pipe_s, _alias_s) in enumerate(_tool_calls_to_run):
                        # Option B: inject piped value from previous tool
                        if _pending_pipe and isinstance(_ti_s, dict):
                            _ti_s = dict(_ti_s)
                            _ti_s.update(_pending_pipe)
                            _pending_pipe = None
                        # Option A: resolve {{placeholders}} using accumulated results
                        _ti_s = _resolve_placeholders(_ti_s, _rctx)
                        logger.debug(f"[MCP Multi-Tool Serial] [{_idx}] {_tn_s} input after resolution: {_ti_s}")
                        try:
                            _r = await _run_single_mcp_tool(_tn_s, _ti_s)
                            _out.append(_r)
                            # Update resolved inputs in-place so result reporting is accurate
                            _tool_calls_to_run[_idx] = (_tn_s, _ti_s, _pipe_s, _alias_s)
                            # Accumulate result in context for downstream placeholders
                            _result_text = _extract_tool_result_text(_r)
                            _rctx[_idx] = _result_text
                            _rctx[_tn_s] = _result_text          # by tool name
                            if _alias_s:
                                _rctx[_alias_s] = _result_text   # by alias
                            # Option B: prepare pipe for next tool
                            if _pipe_s and isinstance(_pipe_s, str):
                                _pending_pipe = {_pipe_s: _result_text}
                        except Exception as _se:
                            _out.append(_se)
                            _pending_pipe = None  # don't pipe from a failed call
                    return _out
                _multi_results = run_async_in_sync(_run_all_serial_mt())

            _mt_succeeded = []
            for (_tn_i, _ti_i, _pipe_i, _alias_i), _tr_i in zip(_tool_calls_to_run, _multi_results):
                if isinstance(_tr_i, Exception):
                    _em = f"[MCP Multi-Tool] Tool '{_tn_i}' raised: {_tr_i}"
                    logger.error(_em)
                    send_skill_editor_log("error", _em)
                    state.setdefault('error', _em)
                    add_to_history(state, ActionMessage(content=f"action: mcp call to {_tn_i}; status: FAILED; error: {_tr_i}"))
                    continue
                _t_failed = hasattr(_tr_i, 'isError') and _tr_i.isError
                if _t_failed:
                    _et = ''
                    if hasattr(_tr_i, 'content') and isinstance(_tr_i.content, list) and _tr_i.content:
                        _et = str(getattr(_tr_i.content[0], 'text', ''))
                    _em = f"[MCP Multi-Tool] Tool '{_tn_i}' returned error: {_et}"
                    logger.error(_em)
                    send_skill_editor_log("error", _em)
                    state.setdefault('error', _em)
                    add_to_history(state, ActionMessage(content=f"action: mcp call to {_tn_i}; status: FAILED; error: {_et}"))
                else:
                    _safe_inc_steps(state)
                    _rt = _extract_tool_result_text(_tr_i)
                    add_to_history(state, ActionMessage(content=f"action: mcp call to {_tn_i}; result: {_rt}"))
                    _apply_mcp_result_to_llm_state(state, _tn_i, _tr_i)
                    _entry = {'tool_name': _tn_i, 'result': _rt}
                    if _alias_i:
                        _entry['alias'] = _alias_i
                    _mt_succeeded.append(_entry)

            if _mt_succeeded:
                state['tool_result'] = _mt_succeeded

            log_msg = f"[MCP Multi-Tool] Completed {len(_tool_calls_to_run)} tool(s) ({len(_mt_succeeded)} succeeded)"
            logger.info(log_msg)
            send_skill_editor_log("info", log_msg)
            _trim_tool_result(state)
            return state

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
                    send_skill_editor_log("warning", log_msg)
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
                    send_skill_editor_log("log", log_msg)
                    
                    # Make the tool call (fire-and-forget - we don't wait for full completion)
                    from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                    tool_result = run_async_in_sync(run_tool_call())
                    
                    # Store initial result and correlation_id
                    state["tool_result"] = tool_result
                    
                    # Check if MCP tool execution failed using MCP standard isError field
                    tool_failed = False
                    error_message = None
                    
                    # MCP standard: Check CallToolResult.isError
                    if hasattr(tool_result, 'isError') and tool_result.isError:
                        tool_failed = True
                        # Extract error message from content
                        if hasattr(tool_result, 'content') and isinstance(tool_result.content, list) and len(tool_result.content) > 0:
                            first_content = tool_result.content[0]
                            error_message = str(getattr(first_content, 'text', 'MCP tool execution failed'))
                        else:
                            error_message = 'MCP tool execution failed'
                    
                    if tool_failed:
                        err_msg = f"[ASYNC_MODE] MCP tool '{_actual_tool_name}' execution failed: {error_message}"
                        logger.error(err_msg)
                        send_skill_editor_log("error", err_msg)
                        state['error'] = err_msg
                        
                        tool_call_summary = ActionMessage(content=f"action: async mcp call to {_actual_tool_name}; correlation_id: {correlation_id}; status: FAILED; error: {error_message}")
                        add_to_history(state, tool_call_summary)
                        
                        return state
                    
                    _safe_inc_steps(state)
                    
                    # Track pending operation in state
                    pending_ops = state.setdefault("_pending_async_operations", [])
                    pending_ops.append({
                        "correlation_id": correlation_id,
                        "tool_name": _actual_tool_name,
                        "node_name": full_node_name,
                        "initial_result": tool_result,
                    })
                    
                    tool_call_summary = ActionMessage(
                        content=f"action: async mcp call to {_actual_tool_name}; correlation_id: {correlation_id}; initial_result: {_extract_tool_result_text(tool_result)}"
                    )
                    add_to_history(state, tool_call_summary)
                    
                    log_msg = f"[ASYNC_MODE] Tool call initiated, workflow continues. Completion will be tracked via correlation_id={correlation_id}"
                    logger.info(log_msg)
                    send_skill_editor_log("log", log_msg)
                    
                    return state
                    
            except Exception as e:
                err_msg = get_traceback(e, f"ErrorAsyncMCPToolCallable({_actual_tool_name})")
                logger.error(err_msg)
                send_skill_editor_log("error", err_msg)
                # Fall through to sync mode on error
        
        # ============================================================
        # Run Local Mode: Send passive command to local machine
        # ============================================================
        if run_local:
            try:
                import uuid as _uuid
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                
                log_msg = f"[RUN_LOCAL] Sending passive MCP tool command to local machine: tool={_actual_tool_name}"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)
                
                # Get the passive transport (same as browser_use cloud agent pattern)
                transport = None
                try:
                    from agent.cloud_worker.worker_main import get_global_passive_transport
                    transport = get_global_passive_transport()
                    logger.info(f"[RUN_LOCAL] get_global_passive_transport returned: {type(transport).__name__ if transport else 'None'}")
                except ImportError as _ie:
                    logger.warning(f"[RUN_LOCAL] ImportError getting passive transport (not running in cloud worker?): {_ie}")
                except Exception as _tex:
                    logger.warning(f"[RUN_LOCAL] Error getting global transport: {_tex}")
                
                # Fallback: create transport from env vars if global transport not set
                # (same env vars that skill_editor_lambda sets on the ECS container)
                if not transport:
                    try:
                        import os as _os
                        _appsync_url = _os.environ.get("EC_APPSYNC_HTTP_ENDPOINT") or _os.environ.get("APPSYNC_API_URL", "")
                        _appsync_key = _os.environ.get("APPSYNC_API_KEY") or _os.environ.get("EC_APPSYNC_TOKEN", "")
                        _client_id = _os.environ.get("EC_BROWSER_PASSIVE_CLIENT_ID", "")
                        if _appsync_url and _appsync_key and _client_id:
                            from agent.ec_skills.browser_use_extension.cloud_agent import CloudWorkerPassiveTransport
                            transport = CloudWorkerPassiveTransport(
                                appsync_url=_appsync_url,
                                appsync_api_key=_appsync_key,
                                client_id=_client_id,
                            )
                            logger.info(f"[RUN_LOCAL] Created fallback transport from env vars: client_id={_client_id}")
                            # Also register globally for future calls
                            try:
                                from agent.cloud_worker.worker_main import set_global_passive_transport
                                set_global_passive_transport(transport)
                            except Exception:
                                pass
                        else:
                            logger.warning(f"[RUN_LOCAL] Cannot create fallback transport: url={bool(_appsync_url)}, key={bool(_appsync_key)}, client={bool(_client_id)}")
                    except Exception as _ftex:
                        logger.warning(f"[RUN_LOCAL] Fallback transport creation failed: {_ftex}")
                
                if not transport:
                    raise RuntimeError(
                        "[RUN_LOCAL] No passive transport available. "
                        "run_local requires running from cloud worker with passive transport configured."
                    )
                
                # Get canonical run_id from state/runtime context
                run_id = None
                try:
                    if isinstance(state, dict):
                        run_id = state.get("browser_use_run_id")
                        if not run_id:
                            attrs = state.get("attributes", {})
                            run_id = attrs.get("chat_id") or attrs.get("run_id") or attrs.get("passive_run_id")
                        if not run_id:
                            meta = state.get("metadata", {})
                            run_id = (
                                (meta.get("run_id") or meta.get("passive_run_id"))
                                if isinstance(meta, dict)
                                else None
                            )
                except Exception:
                    pass
                if not isinstance(run_id, str) or not run_id.strip():
                    run_id = (
                        (os.environ.get("ECAN_RUN_ID") or "").strip()
                        or (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
                    )
                if not isinstance(run_id, str) or not run_id.strip():
                    run_id = _uuid.uuid4().hex
                logger.debug(f"[RUN_LOCAL] resolved run_id={run_id}")
                
                step_id = f"mcp_{_actual_tool_name}_{_uuid.uuid4().hex[:8]}"
                
                # Build the passive command with mcp_tool schema
                from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserCommand

                tool_input_for_passive: dict[str, Any] = _actual_tool_input if isinstance(_actual_tool_input, dict) else {}
                if _actual_tool_name == 'run_code':
                    tool_input_for_passive = _normalize_run_code_tool_input(tool_input_for_passive)
                    if not (tool_input_for_passive.get('input') or {}).get('code'):
                        logger.warning(f"[RUN_LOCAL] run_code tool_input missing code after normalization; tool_input={tool_input_for_passive}")

                mcp_action = {
                    'mcp_tool': {
                        'command': 'mcp_tool',
                        'tool': _actual_tool_name,
                        'tool_input': tool_input_for_passive,
                    }
                }
                
                # Get IDs from state attributes
                acct_site_id = None
                agent_id = None
                skill_id = None
                try:
                    attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
                    acct_site_id = attrs.get("acct_site_id")
                    agent_id = attrs.get("agent_id")
                    skill_id = attrs.get("skill_id") or skill_name
                    if not acct_site_id and transport and hasattr(transport, 'client_id'):
                        acct_site_id = transport.client_id
                except Exception:
                    pass
                
                cmd = PassiveBrowserCommand(
                    type="skill_passive_step",
                    run_id=run_id,
                    step_id=step_id,
                    acct_site_id=acct_site_id,
                    agent_id=agent_id,
                    skill_id=skill_id,
                    node_id=node_name,
                    actions=[mcp_action],
                    include_screenshot=False,
                    stop_on_error=True,
                )
                
                logger.info(
                    f"[RUN_LOCAL] PassiveBrowserCommand built: "
                    f"type={cmd.type}, run_id={run_id}, step_id={step_id}, "
                    f"node_id={node_name}, acct_site_id={acct_site_id}, "
                    f"agent_id={agent_id}, skill_id={skill_id}, "
                    f"actions={mcp_action}"
                )
                logger.info(
                    f"[RUN_LOCAL] Transport info: type={type(transport).__name__}, "
                    f"client_id={getattr(transport, 'client_id', 'N/A')}, "
                    f"url={getattr(transport, 'appsync_url', 'N/A')[:60] if hasattr(transport, 'appsync_url') else 'N/A'}"
                )
                
                timeout_s = float(config_metadata.get('timeout', 180) or 180)
                task_id = (state.get("attributes") or {}).get("task_id") if isinstance(state, dict) else None
                cancellation_event = None
                if task_id:
                    try:
                        from agent.ec_tasks import cancellation_registry
                        cancellation_event = cancellation_registry.get(task_id)
                    except Exception:
                        cancellation_event = None

                async def _run_local_mcp():
                    import time as _time
                    _t0 = _time.time()
                    # Prepare to receive result before publishing command
                    logger.info(f"[RUN_LOCAL] Calling prepare_for_result(run_id={run_id}, step_id={step_id})...")
                    await transport.prepare_for_result(
                        run_id=run_id,
                        step_id=step_id,
                        cancellation_event=cancellation_event,
                    )
                    logger.info(f"[RUN_LOCAL] prepare_for_result done, elapsed={_time.time()-_t0:.2f}s")
                    # Publish command to local machine
                    logger.info(f"[RUN_LOCAL] Publishing command to local machine via transport...")
                    await transport.publish_command(cmd)
                    _pub_elapsed = _time.time() - _t0
                    log_msg = f"[RUN_LOCAL] ⏳ Command published ({_pub_elapsed:.2f}s). Waiting for local response (stepId={step_id}, timeout={timeout_s}s)..."
                    logger.info(log_msg)
                    send_skill_editor_log("log", log_msg)
                    # Wait for result
                    result = await transport.wait_for_result(
                        run_id=run_id,
                        step_id=step_id,
                        timeout_s=timeout_s,
                        cancellation_event=cancellation_event,
                    )
                    _total_elapsed = _time.time() - _t0
                    logger.info(f"[RUN_LOCAL] wait_for_result returned after {_total_elapsed:.2f}s, result type={type(result).__name__}, result is None={result is None}")
                    if result:
                        logger.info(f"[RUN_LOCAL] Result keys: {list(result.keys()) if isinstance(result, dict) else dir(result)[:10]}")
                    return result
                
                if cancellation_event and hasattr(transport, 'cancel_wait'):
                    try:
                        state_task = state.get("task") if isinstance(state, dict) else None
                        if state_task and hasattr(state_task, "register_force_stop_callback"):
                            state_task.register_force_stop_callback(
                                lambda: transport.cancel_wait(
                                    run_id=run_id,
                                    step_id=step_id,
                                    reason=f"Task cancelled during run_local wait: run_id={run_id} step_id={step_id}",
                                ),
                                source=f"run_local_wait_{step_id}",
                            )
                    except Exception:
                        pass

                passive_result = run_async_in_sync(_run_local_mcp())
                
                # Extract tool result from passive response
                tool_result = {}
                if passive_result:
                    logger.info(f"[RUN_LOCAL] Parsing passive_result: type={type(passive_result).__name__}")
                    if hasattr(passive_result, 'action_results'):
                        action_results = passive_result.action_results
                        logger.info(f"[RUN_LOCAL] action_results (attr): count={len(action_results) if action_results else 0}, values={action_results}")
                        if action_results and len(action_results) > 0:
                            tool_result = action_results[0]
                    elif isinstance(passive_result, dict):
                        action_results = passive_result.get('action_results', [])
                        logger.info(f"[RUN_LOCAL] action_results (dict): count={len(action_results) if action_results else 0}, values={action_results}")
                        tool_result = action_results[0] if action_results else passive_result
                    
                    # Check if there were errors
                    errors = getattr(passive_result, 'errors', None) or (passive_result.get('errors') if isinstance(passive_result, dict) else None)
                    if errors:
                        log_msg = f"[RUN_LOCAL] ⚠️ Local execution had errors: {errors}"
                        logger.warning(log_msg)
                        send_skill_editor_log("warning", log_msg)
                else:
                    log_msg = "[RUN_LOCAL] ⚠️ passive_result is None/empty — local machine may not have responded"
                    logger.warning(log_msg)
                    send_skill_editor_log("warning", log_msg)
                
                log_msg = f"[RUN_LOCAL] ✅ Local MCP tool result: {tool_result}"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)
                
                state["tool_result"] = tool_result
                
                # Check if MCP tool execution failed using MCP standard isError field
                tool_failed = False
                error_message = None
                
                # MCP standard: Check CallToolResult.isError
                if hasattr(tool_result, 'isError') and tool_result.isError:
                    tool_failed = True
                    # Extract error message from content
                    if hasattr(tool_result, 'content') and isinstance(tool_result.content, list) and len(tool_result.content) > 0:
                        first_content = tool_result.content[0]
                        error_message = str(getattr(first_content, 'text', 'MCP tool execution failed'))
                    else:
                        error_message = 'MCP tool execution failed'
                
                if tool_failed:
                    err_msg = f"[RUN_LOCAL] MCP tool '{_actual_tool_name}' execution failed: {error_message}"
                    logger.error(err_msg)
                    send_skill_editor_log("error", err_msg)
                    state['error'] = err_msg
                    
                    tool_call_summary = ActionMessage(content=f"action: run_local mcp call to {_actual_tool_name}; status: FAILED; error: {error_message}")
                    add_to_history(state, tool_call_summary)
                else:
                    _safe_inc_steps(state)
                    tool_call_summary = ActionMessage(content=f"action: run_local mcp call to {_actual_tool_name}; result: {_extract_tool_result_text(tool_result)}")
                    add_to_history(state, tool_call_summary)
                    _apply_mcp_result_to_llm_state(state, _actual_tool_name, tool_result)

                return state
                
            except Exception as e:
                err_msg = get_traceback(e, f"ErrorRunLocalMCPTool({_actual_tool_name})")
                logger.error(err_msg)
                send_skill_editor_log("error", err_msg)
                state['error'] = err_msg
                return state
        
        # ============================================================
        # Sync Mode: Standard blocking tool call
        # ============================================================
        try:
            # Use the utility to run the async function from a sync context
            from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
            tool_result = run_async_in_sync(run_tool_call())

            log_msg = f"mcp tool call results: {tool_result}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

            # Add the result to the state (result is a dict, not a list)
            state["tool_result"] = tool_result
            
            # Check if MCP tool execution failed using MCP standard isError field
            tool_failed = False
            error_message = None
            
            # MCP standard: Check CallToolResult.isError
            if hasattr(tool_result, 'isError') and tool_result.isError:
                tool_failed = True
                # Extract error message from content
                if hasattr(tool_result, 'content') and isinstance(tool_result.content, list) and len(tool_result.content) > 0:
                    first_content = tool_result.content[0]
                    error_message = str(getattr(first_content, 'text', 'MCP tool execution failed'))
                else:
                    error_message = 'MCP tool execution failed'
            
            if tool_failed:
                err_msg = f"MCP tool '{_actual_tool_name}' execution failed: {error_message}"
                logger.error(err_msg)
                send_skill_editor_log("error", err_msg)
                state['error'] = err_msg
                
                tool_call_summary = ActionMessage(content=f"action: mcp call to {_actual_tool_name}; status: FAILED; error: {error_message}")
                add_to_history(state, tool_call_summary)
            else:
                _safe_inc_steps(state)
                tool_call_summary = ActionMessage(content=f"action: mcp call to {_actual_tool_name}; result: {_extract_tool_result_text(tool_result)}")
                add_to_history(state, tool_call_summary)
                _apply_mcp_result_to_llm_state(state, _actual_tool_name, tool_result)

                # Also update attributes for easier access by subsequent nodes
                log_msg = f"state tool_result: meta={getattr(tool_result, 'meta', None)} content={[c.text[:200] + '...' if hasattr(c, 'text') and len(getattr(c, 'text', '')) > 200 else c for c in getattr(tool_result, 'content', [])]!r} structuredContent={getattr(tool_result, 'structuredContent', None)} isError={getattr(tool_result, 'isError', None)}"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)

                # Trim large tool_result to reduce state serialization overhead.
                # Full data is already in history (via add_to_history above).
                try:
                    _tr = state.get("tool_result")
                    if _tr and hasattr(_tr, "content") and isinstance(_tr.content, list):
                        _total_len = sum(len(getattr(c, "text", "") or "") for c in _tr.content)
                        if _total_len > 2000:
                            from mcp.types import TextContent as _TC
                            _tr.content = [_TC(type="text", text=f"[trimmed {_total_len} chars, see history]")]
                            if hasattr(_tr, "meta"):
                                _tr.meta = None
                            logger.debug(f"Trimmed tool_result from {_total_len} chars to save state serialization")
                except Exception:
                    pass

                # Enforce overall tool_result dict size limit
                _trim_tool_result(state)

        except Exception as e:
            err_msg = get_traceback(e, f"ErrorMCPToolCallable({_actual_tool_name})")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
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
    send_skill_editor_log("log", log_msg)

    def _noop(state: dict, *, runtime=None, store=None, **kwargs):
        return state
    # Wrap to inherit common context/retry behavior
    return node_builder(_noop, node_name, skill_name, owner, bp_manager)


def build_loop_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Loops are translated structurally by the compiler; runtime callable is a no-op."""
    log_msg = f"building loop node : {config_metadata}"
    logger.debug(log_msg)
    send_skill_editor_log("log", log_msg)

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
    send_skill_editor_log("log", log_msg)

    prompt = (config_metadata or {}).get("prompt") or "Action required to continue."
    tag = (config_metadata or {}).get("tag") or node_name

    # Resolve Mustache-style templates in the prompt before passing to interrupt.
    # This allows pend_event prompts to use upstream node data like {{llm_planner.question_to_user}}
    _mainwin_for_pend = None
    try:
        from app_context import AppContext
        _mainwin_for_pend = AppContext.get_main_window()
    except Exception:
        pass

    # Validate inputsValues exists - this is required for pend_event node
    if "inputsValues" not in config_metadata:
        raise KeyError(
            f"pend_event node '{node_name}' is missing required 'inputsValues' in config_metadata. "
            f"Available keys: {list(config_metadata.keys())}"
        )
    
    main_event = config_metadata["inputsValues"]["eventType"]["content"]
    additional_events = config_metadata["inputsValues"].get("pendingSources", {}).get("content", [])
    timer_name = (config_metadata["inputsValues"].get("timerName") or {}).get("content", "") or ""
    browser_event_label = (config_metadata["inputsValues"].get("browserEventLabel") or {}).get("content", "") or ""

    # Also extract timer_name from pendingSources items (dicts with type + timerName)
    if not timer_name and isinstance(additional_events, list):
        for src in additional_events:
            if isinstance(src, dict) and src.get("type") == "timer":
                timer_name = (src.get("timerName") or "").strip()
                if timer_name:
                    break

    # Also extract browser_event_label from pendingSources items
    if not browser_event_label and isinstance(additional_events, list):
        for src in additional_events:
            if isinstance(src, dict) and src.get("type") == "browser_event":
                browser_event_label = (src.get("browserEventLabel") or "").strip()
                if browser_event_label:
                    break

    # Build a flat set of event type strings for easy membership checks
    _additional_event_types = set()
    if isinstance(additional_events, list):
        for src in additional_events:
            if isinstance(src, str):
                _additional_event_types.add(src.strip())
            elif isinstance(src, dict):
                _additional_event_types.add((src.get("type") or "").strip())

    _listens_for_timer = main_event == "timer" or "timer" in _additional_event_types

    def _pend(state: dict, *, runtime=None, store=None, **kwargs):
        log_msg = f"🤖 Executing node pending event node: {node_name}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)

        # Safety net: auto-resume any paused timers when we reach a pend_event
        # node that listens for timer events. This handles the case where the
        # LLM called pause_timer but forgot to call resume_timer.
        if _listens_for_timer:
            try:
                agent_id = (state.get("attributes") or {}).get("agent_id", "")
                if agent_id:
                    from agent.ec_tasks.timer_service import get_timer_service
                    get_timer_service().resume_all_paused_for_agent(agent_id)
            except Exception as _auto_resume_err:
                logger.debug(f"[pend_event] auto-resume timers skipped: {_auto_resume_err}")

        current_node_name = runtime.context["this_node"].get("name")
        # Truncate screenshot data for logging
        try:
            from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
            log_state = truncate_screenshot_for_logging(state)
        except Exception:
            log_state = str(state)[:500] + "..."
        log_msg = f"[Pending For Event Node] pend_for_event_node: {current_node_name}, {log_state}"
        logger.debug(log_msg)
        send_skill_editor_log("log", str(log_msg)[:500])
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
            "event_type": main_event,
            "timer_name": timer_name,
            "browser_event_label": browser_event_label,
        }
        # Resolve Mustache templates in prompt before interrupt so upstream data appears in the prompt
        resolved_prompt = _resolve_mustache_template(prompt, state, _mainwin_for_pend)
        if resolved_prompt != prompt:
            logger.info(f"[pend_event] Mustache resolved prompt: {resolved_prompt[:300]}...")
            info["prompt_to_human"] = resolved_prompt

        # Send the question to the chat window so the user sees it before the skill pauses
        _msg_to_send = resolved_prompt if (resolved_prompt and str(resolved_prompt).strip()) else "请输入您的回复..."
        _chat_id = None
        try:
            attrs = (state.get("attributes") or {}) if isinstance(state, dict) else {}
            _chat_id = attrs.get("chat_id") or None
            if not _chat_id:
                params = attrs.get("params", {})
                if isinstance(params, dict):
                    _chat_id = params.get("chatId")
                    if not _chat_id:
                        _chat_id = (params.get("metadata") or {}).get("params", {}).get("chatId")
            if not _chat_id and isinstance(state.get("messages"), list) and len(state["messages"]) > 1:
                _chat_id = state["messages"][1]
        except Exception:
            pass

        if _chat_id and str(_msg_to_send).strip():
            # Guard: prevent duplicate sends across parallel task executions.
            # Use a process-level key (skill + node + chat_id) so the flag survives
            # even when state["attributes"] is reinitialized by _node_state_baseline.
            _pend_sent_key = f"_pend_sent_{node_name}"
            _global_key = (skill_name, node_name, _chat_id)
            _attrs_for_guard = state.get("attributes", {})
            _prompt_already_sent = bool(str(_attrs_for_guard.get("prompt_to_human", "")).strip())
            _flag_already_sent = _attrs_for_guard.get(_pend_sent_key, False)
            with _PEND_GLOBAL_LOCK:
                _global_already_sent = _PEND_GLOBAL_SENT.get(_global_key, False)
            _already_sent = _global_already_sent or _prompt_already_sent or _flag_already_sent
            if not _already_sent:
                _sent = False
                try:
                    from app_context import AppContext
                    _mw = AppContext.get_main_window()
                    _bridge = getattr(_mw, "channel_bridge", None)
                    if _bridge:
                        _ch_result = _bridge.route_reply(state, _msg_to_send)
                        if _ch_result is not None:
                            _sent = True
                            logger.info(f"[pend_event] Sent prompt via channel bridge, len={len(_msg_to_send)}")
                except Exception as _ch_err:
                    logger.debug(f"[pend_event] Channel bridge unavailable: {_ch_err}")

                if not _sent:
                    try:
                        from agent.ec_tasks.message_sender import ChatMessageSender
                        agent_id = state.get("messages", [""])[0] if isinstance(state.get("messages"), list) else ""
                        agent_obj = None
                        if agent_id:
                            try:
                                from agent.agent_service import get_agent_by_id
                                agent_obj = get_agent_by_id(agent_id)
                            except Exception:
                                pass
                        sender = ChatMessageSender(agent_obj)
                        sender.send_text(_chat_id, _msg_to_send)
                        logger.info(f"[pend_event] Sent prompt to GUI chat={_chat_id}, len={len(_msg_to_send)}")
                    except Exception as _send_err:
                        logger.info(f"[pend_event] Failed to send prompt: {_send_err}")

                # Mark as sent in all three places.
                with _PEND_GLOBAL_LOCK:
                    _PEND_GLOBAL_SENT[_global_key] = True
                if isinstance(state.get("attributes"), dict):
                    state["attributes"][_pend_sent_key] = True
            else:
                logger.info(f"[pend_event] Guard BLOCKED send (global={_global_already_sent}, prompt={_prompt_already_sent}, flag={_flag_already_sent}), skipping")

        log_msg = f"[pend_event_node] Waiting for event: type={main_event}, browser_label={browser_event_label}, timer={timer_name}, node={node_name}"
        logger.debug(f"[DEBUG PEND] 1 log_msg ready, node={node_name}")
        logger.info(log_msg)
        logger.debug(f"[DEBUG PEND] 2 logger.info done, node={node_name}")
        send_skill_editor_log("log", log_msg)
        logger.debug(f"[DEBUG PEND] 3 send_skill_editor_log done, node={node_name}")
        logger.debug(f"[DEBUG PEND] 4 about to call interrupt, node={node_name}")
        resume_payload = interrupt(info)
        logger.debug(f"[DEBUG PEND] 5 interrupt() RETURNED, node={node_name}")

        from agent.ec_skills.llm_utils.llm_utils import try_parse_json
        # If resumer supplied a state patch (e.g., via Command(resume={... "_state_patch": {...}})), merge it
        _rp_event_type = resume_payload.get("event_type", "") if isinstance(resume_payload, dict) else ""
        log_msg = f"[pend_event_node] RESUMED: event_type={_rp_event_type}, node={node_name}, payload_keys={list(resume_payload.keys()) if isinstance(resume_payload, dict) else '?'}"
        logger.info(log_msg)
        send_skill_editor_log("log", log_msg)
        # send_skill_editor_log("log", log_msg)

        try:
            _env = resume_payload.get("_event_envelope") if isinstance(resume_payload, dict) else {}
            _env_ctx = _env.get("context", {}) if isinstance(_env, dict) else {}
            _env_data = _env.get("data", {}) if isinstance(_env, dict) else {}
            _browser_label = ""
            if isinstance(_env_ctx, dict):
                _browser_label = str(_env_ctx.get("label") or _env_ctx.get("browserEventLabel") or "").strip()
            if not _browser_label and isinstance(_env_data, dict):
                _browser_label = str(_env_data.get("label") or "").strip()
            if _rp_event_type == "browser_event" and _browser_label == "chat_message_added":
                _chat_id = ""
                if isinstance(state, dict):
                    _attrs = state.get("attributes", {}) if isinstance(state.get("attributes"), dict) else {}
                    _chat_id = str(_attrs.get("chat_id") or "").strip()
                if not _chat_id and isinstance(_env_ctx, dict):
                    _chat_id = str(_env_ctx.get("chatId") or "").strip()
                logger.info(
                    f"[LatencyMarker] service_resume browser_event=chat_message_added "
                    f"chat_id={_chat_id or 'unknown'} resumed_at_ms={int(time.time() * 1000)} node={node_name}"
                )
        except Exception as _latency_log_err:
            logger.debug(f"[LatencyMarker] failed to log browser_event resume marker: {_latency_log_err}")

        # --- Append full event envelope to state["events"] ---
        try:
            envelope = resume_payload.get("_event_envelope") if isinstance(resume_payload, dict) else None
            event_record = {
                "event_type": (resume_payload.get("event_type") if isinstance(resume_payload, dict) else None)
                             or (envelope.get("type") if isinstance(envelope, dict) else None)
                             or main_event
                             or "",
                "source": (envelope.get("source", "") if isinstance(envelope, dict) else ""),
                "timestamp": (envelope.get("timestamp", "") if isinstance(envelope, dict) else ""),
                "context": (envelope.get("context", {}) if isinstance(envelope, dict) else {}),
                "tag": (envelope.get("tag", "") if isinstance(envelope, dict) else ""),
                "node": node_name,
            }
            # Include event data (human_text, metadata, etc.) if present
            if isinstance(envelope, dict) and envelope.get("data"):
                event_record["data"] = envelope["data"]
            state.setdefault("events", []).append(event_record)
            # Prune events list to prevent unbounded growth
            if len(state["events"]) > 100:
                state["events"] = state["events"][-100:]
            # Store a COMPACT reference in prompt_refs — avoid storing large data payloads
            # (envelope["data"] may contain human_text, screenshots, etc.) to prevent memory leak.
            compact_event = {
                "event_type": event_record.get("event_type", ""),
                "source": event_record.get("source", ""),
                "tag": event_record.get("tag", ""),
                "node": event_record.get("node", ""),
                "timestamp": event_record.get("timestamp", ""),
            }
            # Include small scalar fields from context (e.g. senderId, chatId)
            # so downstream LLM nodes can reference the sender for replies.
            _ctx = event_record.get("context")
            if isinstance(_ctx, dict):
                for _ck, _cv in _ctx.items():
                    if isinstance(_cv, (str, int, float, bool)) and len(str(_cv)) < 500:
                        compact_event[_ck] = _cv
            # Only include small scalar fields from data, skip large blobs
            if isinstance(event_record.get("data"), dict):
                for _ek, _ev in event_record["data"].items():
                    if isinstance(_ev, (str, int, float, bool)) and len(str(_ev)) < 5000:
                        compact_event[_ek] = _ev
            state.setdefault("prompt_refs", {})["events"] = json.dumps(
                compact_event, ensure_ascii=False, default=str
            )
            logger.debug(f"[pend_event_node] Appended event to state['events']: type={event_record['event_type']}, source={event_record['source']}")
            
            # DEBUG: Log event data after appending to help debug input accumulation issues
            try:
                _event_data_keys = list(event_record.get("data", {}).keys()) if isinstance(event_record.get("data"), dict) else []
                _human_text = event_record.get("data", {}).get("human_text") if isinstance(event_record.get("data"), dict) else None
                _text = event_record.get("data", {}).get("text") if isinstance(event_record.get("data"), dict) else None
                _content = event_record.get("data", {}).get("content") if isinstance(event_record.get("data"), dict) else None
                _message = event_record.get("data", {}).get("message") if isinstance(event_record.get("data"), dict) else None
                logger.info(
                    f"[PEND_EVENT_DEBUG] node={node_name} event appended: "
                    f"data_keys={_event_data_keys} "
                    f"has_human_text={bool(_human_text)} "
                    f"has_text={bool(_text)} "
                    f"has_content={bool(_content)} "
                    f"has_message={bool(_message)} "
                    f"human_text_preview='{str(_human_text)[:80] if _human_text else ''}...'"
                )
            except Exception as _ev_debug_err:
                logger.debug(f"[pend_event_node] Failed to log event debug info: {_ev_debug_err}")
        except Exception as ev_err:
            logger.debug(f"[pend_event_node] Failed to append event record: {ev_err}")

        # --- Deep-merge _state_patch into state ---
        try:
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

                    if isinstance(state, dict):
                        merged = _deep_merge(state, patch)
                        state.clear()
                        state.update(merged)
        except Exception:
            pass

        log_msg = f"[pend_event_node] resume payload after deep merge: {resume_payload}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)

        # ── Clear stale input from previous event cycle ──
        # Without this, state["input"] from a previous chat_message cycle
        # leaks into the next browser_event cycle.  The browser-use node
        # injects state["input"] as "Current Invocation Input", so stale
        # response_text causes the LLM to re-send old replies instead of
        # running Phase-1 detection.  Clearing here ensures each cycle
        # starts fresh; the new event's data (if any) will be set below
        # by chat_attributes enrichment or human_text extraction.
        _stale_input = state.pop("input", None)

        # ── Preserve UNDELIVERED response_text across event-bus race ──
        # See ``_stale_input_has_undelivered_response_text`` docstring
        # for the full incident write-up.  TL;DR: when a chat_message
        # resume populates ``state["input"]`` with a Q&A worker's reply
        # but the langgraph loops back to pend_event via condition nodes
        # without entering ``browser_automation_janWe``, the very next
        # non-chat_message resume here would silently drop the reply.
        # Restore it so HOT-PATH-B's ``state["input"]`` payload-source
        # fallback can pick it up on the next BA invocation.
        try:
            _preserve, _undeliv_cust, _undeliv_resp = (
                _stale_input_has_undelivered_response_text(
                    _stale_input, _rp_event_type
                )
            )
            if _preserve:
                state["input"] = _stale_input
                _stale_input = None  # don't log as cleared
                logger.warning(
                    f"[pend_event] Preserved undelivered response_text "
                    f"(cust={_undeliv_cust!r}, len={len(_undeliv_resp)}) "
                    f"in state.input — would have been dropped by "
                    f"{_rp_event_type} resume; HOT-PATH-B will retry "
                    f"via state.input fallback, node={node_name}"
                )
        except Exception as _undeliv_err:
            logger.debug(
                f"[pend_event] Undelivered-reply preservation check failed "
                f"(non-fatal): {_undeliv_err}"
            )
        _stale_msg4 = None
        if isinstance(state.get("messages"), list) and len(state["messages"]) > 4:
            _stale_msg4 = state["messages"][4]
            state["messages"][4] = ""
        # Also clear state["attributes"]["params"] — _extract_runtime_invocation_input()
        # reads response_text from attrs.params.metadata.params.content, which leaks
        # across event cycles and causes the HOT-PATH to fire for stale chat_message
        # replies when the actual triggering event is a browser_event (new customer
        # message).  Only clear for non-chat_message events; chat_message events
        # re-populate params via chat_attributes enrichment below.
        _stale_attrs_params = None
        if _rp_event_type != "chat_message":
            _attrs = state.get("attributes")
            if isinstance(_attrs, dict) and _attrs.get("params"):
                _stale_attrs_params = _attrs.pop("params", None)
        if _stale_input or _stale_msg4 or _stale_attrs_params:
            logger.info(
                f"[pend_event] Cleared stale input from previous cycle "
                f"(had_input={bool(_stale_input)}, had_msg4={bool(_stale_msg4)}, "
                f"had_attrs_params={bool(_stale_attrs_params)}, "
                f"new_event={_rp_event_type}, node={node_name})"
            )

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
                        if val and (msg_list[idx] in (None, "") or idx == 4):
                            # idx 4 = content: always overwrite so subsequent
                            # chat_message events carry the latest message text,
                            # not the stale value from a previous event.
                            msg_list[idx] = val
        except Exception:
            pass

        log_msg = f"[pend_event_node] resumed, state: {state}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)

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

        # Add human message to history for LLM context
        # Extract the actual text content from human_text
        human_text_content = None
        if isinstance(raw_ht, str) and raw_ht.strip():
            human_text_content = raw_ht.strip()
        elif isinstance(data, dict) and data.get("content"):
            human_text_content = data.get("content")

        if human_text_content:
            # ── Per-customer history isolation for Q&A workers ──────────
            # See ``_reset_qa_history_on_customer_change`` for the full
            # incident write-up (2026-04-27 crosstalk).  Short version:
            # ``state["history"]`` is shared across all dispatches to
            # the same agent, so without this reset a Q&A worker can
            # bleed customer A's prior turn into customer B's reply.
            _qa_payload = data if isinstance(data, dict) else None
            if _qa_payload is None and isinstance(human_text_content, str):
                _qa_payload = try_parse_json(human_text_content)
            _reset_qa_history_on_customer_change(
                state, _qa_payload, node_name=node_name, logger_=logger,
            )

            # Set state["input"] so _get_human_input() in pre_llm_hook can find it
            state["input"] = human_text_content
            state.setdefault("history", [])
            state["history"].append(HumanMessage(content=human_text_content))
            logger.debug(f"[{node_name}] added human message to history and input: {human_text_content[:100]}...")

        logger.debug(f"[{node_name}] exit state: {state}")
        return state

    return node_builder(_pend, node_name, skill_name, owner, bp_manager)


def build_chat_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """Chat node sends messages via TaskRunner GUI methods."""
    log_msg = f"building chat node : {config_metadata}"
    logger.debug(log_msg)
    send_skill_editor_log("log", log_msg)

    role = ((config_metadata or {}).get("role") or "assistant").lower()
    msg_tpl = (config_metadata or {}).get("message") or ""
    wait_for_reply_tpl = (config_metadata or {}).get("wait_for_reply") or False
    def _chat(state: dict, *, runtime=None, store=None, **kwargs):
        from agent.ec_tasks.message_sender import ChatMessageSender
        attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
        log_msg = f"🤖 Executing node Chat node: {node_name}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)

        logger.debug("in chat node....", state)

        # Resolve Mustache-style template in the message using tool_result data.
        # Supports: {{query}}, {{#llm_planner}}{{product_name}}{{/llm_planner}},
        # and {{product_profile.product_name}} dot-path notation.
        # Get mainwin from AppContext for proper variable resolution
        _chat_mainwin = None
        try:
            from app_context import AppContext
            _chat_mainwin = AppContext.get_main_window()
        except Exception:
            pass
        resolved_response = _resolve_mustache_template(msg_tpl, state, mainwin=_chat_mainwin)

        # Try to deliver to GUI via ChatMessageSender (direct to GUI, no twin agent needed)
        try:
            llm_output = state["result"].get("llm_result", {})
            # Extract displayable text from llm_result
            if isinstance(llm_output, dict):
                response = (
                    llm_output.get("message") or
                    llm_output.get("next_prompt") or
                    llm_output.get("content") or
                    llm_output.get("text") or
                    ""
                )
            else:
                response = str(llm_output) if llm_output else ""

            state["job_related"] = state["result"].get("job_related", False)

            # DO NOT overwrite llm_result - downstream condition nodes need the full dict
            # state["result"]["llm_result"] = response  # REMOVED: this was destroying condition data

            # Send response directly to GUI via ChatMessageSender
            chat_id = None
            try:
                # 1) attributes.chat_id (set by _node_state_baseline)
                chat_id = attrs.get("chat_id") or None
                # 2) attributes.params.chatId (legacy direct param)
                if not chat_id:
                    params = attrs.get("params", {})
                    if isinstance(params, dict):
                        chat_id = params.get("chatId")
                        # 3) attributes.params.metadata.params.chatId (new A2A SDK)
                        if not chat_id:
                            meta_params = (params.get("metadata") or {}).get("params", {})
                            if isinstance(meta_params, dict):
                                chat_id = meta_params.get("chatId")
                # 4) messages[1] (baseline stores chat_id there)
                if not chat_id and isinstance(state.get("messages"), list) and len(state["messages"]) > 1:
                    chat_id = state["messages"][1]
            except Exception:
                if isinstance(state.get("messages"), list) and len(state["messages"]) > 1:
                    chat_id = state["messages"][1]

            if chat_id:
                # Use template-resolved message if available, otherwise fall back to LLM output
                _msg_to_send = resolved_response if (resolved_response and str(resolved_response).strip()) else (response or "")
                if _msg_to_send and str(_msg_to_send).strip():
                    _sent_via_channel = False
                    try:
                        from app_context import AppContext
                        _mw = AppContext.get_main_window()
                        _bridge = getattr(_mw, "channel_bridge", None)
                        if _bridge:
                            _ch_result = _bridge.route_reply(state, _msg_to_send)
                            if _ch_result is not None:
                                _sent_via_channel = True
                                logger.info(f"[chat_node] Sent response via channel, len={len(_msg_to_send)}")
                    except Exception as _ch_err:
                        logger.debug(f"[chat_node] Channel bridge check failed: {_ch_err}")

                    if not _sent_via_channel:
                        agent_id = state.get("messages", [""])[0] if isinstance(state.get("messages"), list) else ""
                        agent_obj = None
                        if agent_id:
                            try:
                                from agent.agent_service import get_agent_by_id
                                agent_obj = get_agent_by_id(agent_id)
                            except Exception:
                                pass
                        sender = ChatMessageSender(agent_obj)
                        sender.send_text(chat_id, _msg_to_send)
                        logger.info(f"[chat_node] Sent response to GUI chat={chat_id}, len={len(_msg_to_send)}")
                        send_skill_editor_log("log", f"[chat_node] Sent response to GUI chat={chat_id}")

                    # Mark that chat node already delivered the response (prevents duplicate in _on_skill_complete)
                    if isinstance(state.get("attributes"), dict):
                        state["attributes"]["chat_response_sent"] = True

                    # Wait for user reply if configured
                    if wait_for_reply_tpl:
                        info = {
                            "i_tag": node_name,
                            "paused_at": node_name,
                            "prompt_to_human": _msg_to_send,
                            "event_type": "human_input",
                        }
                        resume_payload = interrupt(info)
                        # Merge reply data into state
                        if isinstance(resume_payload, dict):
                            human_text = resume_payload.get("human_text")
                            if human_text:
                                state["input"] = human_text
                            if "_state_patch" in resume_payload:
                                patch = resume_payload.get("_state_patch", {})
                                if isinstance(patch, dict):
                                    for k, v in patch.items():
                                        if isinstance(state, dict):
                                            state[k] = v
            else:
                logger.warning(f"[chat_node] No chatId found, cannot send response to GUI")

        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildChatNode")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)

        return state

    return node_builder(_chat, node_name, skill_name, owner, bp_manager)


def build_rag_node(config_metadata: dict, node_name: str, skill_name: str, owner: str, bp_manager: BreakpointManager):
    """RAG node with optional LIGHTRAG API."""
    log_msg = f"building rag node : {config_metadata}"
    logger.debug(log_msg)
    send_skill_editor_log("log", log_msg)

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
            send_skill_editor_log("error", err_msg)
        # Ensure tool_result is a dict; previous nodes may set non-dict objects here
        try:
            tr = state.get("tool_result") if isinstance(state, dict) else None
            if not isinstance(tr, dict):
                tr = {}
                state["tool_result"] = tr
            tr[node_name] = {"query": query, "documents": results}
            _trim_tool_result(state)
        except Exception as _e:
            # Best-effort: record error without raising to keep the workflow moving
            try:
                from utils.logger_helper import get_traceback as _gt
                err_msg = _gt(_e, "ErrorRAGNodeToolResult")
                logger.error(err_msg)
                send_skill_editor_log("error", err_msg)
            except Exception as _e_:
                err_msg = get_traceback(_e_, "ErrorRAGNodeToolResult")
                logger.debug(f"RAG node tool_result set failed: {err_msg}")
                send_skill_editor_log("error", f"RAG node tool_result set failed: {err_msg}")
            state["error"] = f"rag node failed to set tool_result: {err_msg}"

        add_to_history(state, ActionMessage(content=f"action: rag {str(query)}; result: {results}; {err_msg}"))
        return state

    return node_builder(_rag, node_name, skill_name, owner, bp_manager)


# Module-level lock and cache for preventing duplicate passive command execution
import asyncio as _asyncio_module
import threading as _threading_module
_passive_steps_lock = _threading_module.Lock()  # threading.Lock — safe across event loops
_passive_steps_processed: set[str] = set()

# Module-level cache for PassiveAgent - reuse across loop iterations
# Key: browser_session id, Value: PassiveAgent instance
_cached_passive_agents: dict[int, "PassiveAgent"] = {}

# Module-level guard: scopes that have already done the first-invocation skip.
# Must be module-level (not closure-level) so it persists across skill rebuilds
# when the runner re-submits after a failure.
_first_invocation_done: set[str] = set()

# Module-level PreDispatch state, shared across all BrowserSession instances
# (and their "scopes" like node:... / chat:<customer>). Keyed by
# (calling_agent_id, node_name, dispatch_state_attr). Without this, the per-
# BrowserSession dispatch_state caused duplicate assignments whenever Mary
# resumed under a different scope (empty state, so the assigned_sessions dedup
# was bypassed).
_dispatch_state_by_agent: dict[tuple[str, str, str], dict] = {}

# Cross-scope, cross-agent dispatch-inflight lock keyed by normalised
# customer_id.  PreDispatch can run in either scope=node:<node> (front-desk)
# or scope=chat:<customer> (a QA worker whose EventMonitor happens to fire
# first after the front-desk's runner drops off between rounds).  Without a
# shared lock, both would dispatch the *same* customer turn to different
# QA workers in parallel.  First PreDispatch to dispatch acquires the lock;
# subsequent PreDispatches skip that customer until:
#   * HOT-PATH-B finishes typing the reply and calls the clear helper, OR
#   * the TTL elapses (safety net if the responder crashes).
# The lock is per-customer, so multi-customer simultaneity is unaffected —
# customer A's lock never blocks dispatching customer B.
_dispatch_inflight: dict[str, float] = {}
_DISPATCH_INFLIGHT_TTL_S = 30.0


def _is_dispatch_inflight(customer_key: str) -> float:
    """Return age (s) of an active inflight lock, or 0.0 if none/expired."""
    if not customer_key:
        return 0.0
    import time as _cdi_time
    ts = _dispatch_inflight.get(customer_key)
    if ts is None:
        return 0.0
    age = _cdi_time.time() - ts
    if age > _DISPATCH_INFLIGHT_TTL_S:
        _dispatch_inflight.pop(customer_key, None)
        return 0.0
    return age if age > 0.0 else 0.000001


def _mark_dispatch_inflight(customer_key: str) -> None:
    if not customer_key:
        return
    import time as _cdi_time
    _dispatch_inflight[customer_key] = _cdi_time.time()


def _clear_dispatch_inflight(customer_key: str) -> None:
    if not customer_key:
        return
    _dispatch_inflight.pop(customer_key, None)


# ── External lifecycle-hook bundle auto-discovery ───────────────────────────
# Every bundle is imported once at module-load time so its
# ``__init__.py`` has a chance to call the ``register_before_*_hook``
# APIs above and wire itself into the three lifecycle-hook registries.
#
# Three search locations (in order, first-wins on name collisions):
#   1. In-tree:  ``agent/ec_skills/browser_use_extension/hooks/external/*/``
#                (shipped with the app)
#   2. User data home:  ``<app_info.appdata_path>/hooks/external/*/``
#                (field-deployed users drop bundles here — no app edits)
#   3. Extra:    paths listed in ``ECAN_EXTRA_HOOK_DIRS`` env var
#                (OS-path-sep separated)
#
# Third-party contract: drop a directory under any of the three roots
# containing an ``__init__.py`` that performs the ``register_*`` calls.
# No edits to ``build_node.py`` required — the directory is discovered
# on next process start.  A bundle whose import raises is logged and
# skipped; other bundles still load.  Set
# ``ECAN_DISABLE_EXTERNAL_HOOK_DISCOVERY=1`` to turn discovery off
# entirely (useful for isolated tests or locked-down deployments).
#
# Reference implementation: ``feige_chat/`` (in-tree) — registers
# HOT-PATH-B (early phase), the actionable-items prompt-build filter,
# and PreDispatch (late phase).
def _discover_external_hook_bundles() -> None:
    """Discover + import every external lifecycle-hook bundle.

    Three search locations (in order):

    1. **In-tree** ``agent/ec_skills/browser_use_extension/hooks/external/*/``
       — shipped with the app, imported as a regular Python subpackage.
    2. **User data home** ``<app_info.appdata_path>/hooks/external/*/``
       — field-deployed users drop bundles here without touching the
       installed app.  Loaded via importlib under a synthesized
       top-level package name ``ecan_user_hook__<bundle>`` so relative
       imports inside the bundle still work.
    3. **Extra dirs** listed in ``ECAN_EXTRA_HOOK_DIRS`` (OS-path-sep
       separated: ``;`` on Windows, ``:`` elsewhere).  Same loading
       mechanism as (2).

    Ordering: in-tree → user home → extra dirs.  First-wins on name
    collisions (a user bundle cannot shadow an in-tree bundle of the
    same name — that case logs a warning and skips the shadowing copy).

    Failure isolation: a broken bundle is logged at WARNING and
    skipped; other bundles still load.

    Disable entirely via ``ECAN_DISABLE_EXTERNAL_HOOK_DISCOVERY=1``.
    """
    import os as _eh_os
    if _eh_os.environ.get("ECAN_DISABLE_EXTERNAL_HOOK_DISCOVERY", "").strip().lower() in ("1", "true", "yes", "on"):
        logger.info("[build_node] External hook bundle discovery disabled via ECAN_DISABLE_EXTERNAL_HOOK_DISCOVERY")
        return

    _loaded: list[str] = []
    _failed: list[tuple[str, str]] = []
    _seen_names: set[str] = set()

    # (1) In-tree subpackage discovery (regular import path).
    import importlib
    import pkgutil
    try:
        external_pkg = importlib.import_module(
            "agent.ec_skills.browser_use_extension.hooks.external"
        )
        for _mod_info in pkgutil.iter_modules(
            external_pkg.__path__, prefix=external_pkg.__name__ + "."
        ):
            if not _mod_info.ispkg:
                continue
            _short = _mod_info.name.rsplit(".", 1)[-1]
            if _short.startswith("_") or _short in _seen_names:
                continue
            try:
                importlib.import_module(_mod_info.name)
                _seen_names.add(_short)
                _loaded.append(f"{_short} (in-tree)")
            except Exception as _bundle_err:
                _failed.append((_short, str(_bundle_err)))
                logger.warning(
                    f"[build_node] External hook bundle '{_short}' (in-tree) failed to load "
                    f"(skipped, other bundles continue): {_bundle_err}"
                )
    except Exception as _imp_err:
        logger.warning(
            f"[build_node] In-tree external hook package failed to import "
            f"(continuing to user-home discovery): {_imp_err}"
        )

    # (2) + (3) Filesystem discovery under the user data home + extra dirs.
    _extra_dirs: list[tuple[str, str]] = []  # (origin_label, abs_path)
    try:
        from config.app_info import app_info as _app_info
        _appdata = getattr(_app_info, "appdata_path", "") or ""
        if _appdata:
            _extra_dirs.append(("user_home", _eh_os.path.join(_appdata, "hooks", "external")))
    except Exception as _ai_err:
        logger.debug(f"[build_node] Cannot resolve appdata_path for user hook discovery: {_ai_err}")

    _env_extra = _eh_os.environ.get("ECAN_EXTRA_HOOK_DIRS", "").strip()
    if _env_extra:
        for _p in _env_extra.split(_eh_os.pathsep):
            _p = _p.strip()
            if _p:
                _extra_dirs.append(("env", _eh_os.path.abspath(_p)))

    for _origin, _root in _extra_dirs:
        if not _eh_os.path.isdir(_root):
            logger.debug(f"[build_node] Hook discovery: {_origin} path not found, skipping: {_root}")
            continue
        try:
            _entries = sorted(_eh_os.listdir(_root))
        except Exception as _ls_err:
            logger.warning(f"[build_node] Cannot list {_origin} hook dir {_root!r}: {_ls_err}")
            continue
        for _name in _entries:
            if _name.startswith("_") or _name.startswith("."):
                continue
            _bundle_dir = _eh_os.path.join(_root, _name)
            if not _eh_os.path.isdir(_bundle_dir):
                continue
            _init_py = _eh_os.path.join(_bundle_dir, "__init__.py")
            if not _eh_os.path.isfile(_init_py):
                continue
            if _name in _seen_names:
                logger.warning(
                    f"[build_node] External hook bundle '{_name}' ({_origin}) shadows "
                    f"an already-loaded bundle at {_bundle_dir!r} — skipping "
                    f"(first-wins policy, in-tree bundles always win)"
                )
                continue
            try:
                _pkg_name = f"ecan_user_hook__{_name}"
                import importlib.util as _iu
                import sys as _sys
                _spec = _iu.spec_from_file_location(
                    _pkg_name,
                    _init_py,
                    submodule_search_locations=[_bundle_dir],
                )
                if _spec is None or _spec.loader is None:
                    raise ImportError(f"could not build import spec for {_init_py}")
                _mod = _iu.module_from_spec(_spec)
                _sys.modules[_pkg_name] = _mod
                _spec.loader.exec_module(_mod)
                _seen_names.add(_name)
                _loaded.append(f"{_name} ({_origin}:{_bundle_dir})")
            except Exception as _bundle_err:
                _failed.append((_name, str(_bundle_err)))
                logger.warning(
                    f"[build_node] External hook bundle '{_name}' ({_origin}) at "
                    f"{_bundle_dir!r} failed to load (skipped, other bundles continue): {_bundle_err}"
                )

    if _loaded:
        logger.info(
            f"[build_node] Loaded {len(_loaded)} external hook bundle(s): "
            f"{', '.join(_loaded)}"
        )
    if _failed:
        logger.warning(
            f"[build_node] {len(_failed)} external hook bundle(s) skipped: "
            f"{', '.join(n for n, _ in _failed)}"
        )


_discover_external_hook_bundles()


# ── Upstream-output compaction ────────────────────────────────────────────
# Walk `state["tool_result"]` and build a compact JSON summary for injection
# into the browser-automation task prompt.  Drops noise keys, truncates
# oversized payloads, and applies generic detail-page heuristics to avoid
# feeding the LLM a bloated blob.
#
# Extracted from `_auto` on 2026-04-22 (was ~327 lines of nested helpers
# inside the build function).  Pure: reads state, returns a string.
# `current_node_name` is excluded from the output to prevent self-feedback
# loops on retries.
def _compact_tool_result_for_prompt(state: dict, current_node_name: str) -> str:
    import json
    import re
    from urllib.parse import urlsplit, parse_qs

    tr = state.get("tool_result") if isinstance(state, dict) else None
    if not isinstance(tr, dict):
        return "{}"

    # Keys we want to preserve verbatim when present in any node output.
    keep_keys = {
        "status", "reason", "price_range", "links",
        "downloaded_images", "download_count", "image_urls", "image_descriptions",
        "listing_url", "title", "description", "price",
        "product_keyword", "brand", "model", "category", "condition",
        "original_images", "products", "highlights_summary", "target_audience",
        "notes", "is_free_shipping", "is_used", "features", "listing_images",
        "search_keyword",
    }

    # Generic noise keys to avoid prompt bloat and scenario-specific internals.
    drop_keys = {
        "provider", "task", "systemPrompt", "history", "prompts", "prompt_refs",
        "messages", "threads", "events", "attachments", "http_response",
        "cli_input", "cli_results", "attributes",
    }

    def _extract_links(*texts):
        links = []
        for txt in texts:
            if not txt:
                continue
            s = str(txt)
            links.extend(re.findall(r'https?://[^\s\]\"\'\)]+', s))
            for m in re.findall(r'//[^\s\]\"\'\)]+', s):
                links.append(f"https:{m}")
        dedup = []
        seen = set()
        for u in links:
            if u in seen:
                continue
            seen.add(u)
            dedup.append(u)
        return dedup

    def _extract_json_object_from_text(text):
        """Best-effort JSON object extractor for node outputs.
        Supports plain JSON and fenced code blocks."""
        if not isinstance(text, str):
            return None
        s = text.strip()
        if not s:
            return None
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
            s = re.sub(r"\n?```$", "", s).strip()
        for candidate in (s,):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            block = m.group(0)
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None
        return None

    def _merge_keep_keys_from_dict(dst: dict, src: dict):
        if not isinstance(src, dict):
            return
        for k in keep_keys:
            v = src.get(k)
            if v in (None, "", [], {}):
                continue
            dst[k] = v

    def _is_small_scalar(v):
        return isinstance(v, (str, int, float, bool)) and len(str(v)) <= 200

    def _is_small_scalar_list(v):
        return (
            isinstance(v, list)
            and len(v) <= 20
            and all(_is_small_scalar(i) for i in v)
        )

    def _merge_generic_fields_from_dict(dst: dict, src: dict, depth: int = 0):
        """Scenario-agnostic field extraction: keep compact, actionable keys
        from arbitrary JSON-like outputs."""
        if not isinstance(src, dict) or depth > 1:
            return
        for k, v in src.items():
            if not isinstance(k, str):
                continue
            kl = k.lower()
            if (
                k in drop_keys
                or kl.startswith("_")
                or any(tok in kl for tok in ("prompt", "history", "message", "thread", "event", "attachment", "screenshot", "dom", "html", "markdown"))
            ):
                continue
            if v in (None, "", [], {}):
                continue
            if k in dst:
                continue
            if _is_small_scalar(v) or _is_small_scalar_list(v):
                dst[k] = v
                continue
            if isinstance(v, dict) and len(v) <= 20:
                if all(_is_small_scalar(sv) for sv in v.values()):
                    dst[k] = v
                _merge_generic_fields_from_dict(dst, v, depth + 1)

    def _is_actionable_detail_link(url: str) -> bool:
        """Generic heuristic to keep likely detail pages, drop home/search/list pages."""
        try:
            s = str(url or "").strip()
            if not s.startswith(("http://", "https://")):
                return False
            p = urlsplit(s)
            if not p.netloc:
                return False
            path = (p.path or "").strip().lower()
            query = (p.query or "").lower()
            query_map = parse_qs(p.query or "", keep_blank_values=True)
            if path in ("", "/"):
                return False
            text = f"{path}?{query}"
            if any(k in text for k in ("/search", "search?", "keyword=", "query=", "q=", "wd=", "/list", "list?")):
                return False
            id_keys = ("id", "itemid", "item_id", "sku", "sku_id", "productid", "product_id", "pid")
            if any(k in query_map and any(str(v).strip() for v in query_map.get(k, [])) for k in id_keys):
                return True
            if re.search(r"\d{5,}", path):
                return True
            segments = [seg for seg in path.split("/") if seg]
            if len(segments) >= 2 and segments[-1] not in ("home", "index", "category", "categories", "catalog", "list", "search"):
                return True
            return False
        except Exception:
            return False

    compact = {}
    for _nid, _val in tr.items():
        # Exclude current node output to avoid self-feedback loops on retries.
        if _nid == current_node_name:
            continue
        if not isinstance(_val, dict):
            continue
        row = {}

        # 1) Direct extraction from node output dict.
        _merge_keep_keys_from_dict(row, _val)
        _merge_generic_fields_from_dict(row, _val)

        # 2) Generic extraction from nested dict/string payloads.
        candidate_payloads = [
            _val.get("final"), _val.get("result"), _val.get("llm_result"),
            _val.get("response"), _val.get("output"), _val.get("text"),
            _val.get("history"),
        ]
        for payload in candidate_payloads:
            if isinstance(payload, dict):
                _merge_keep_keys_from_dict(row, payload)
                _merge_generic_fields_from_dict(row, payload)
                nested = payload.get("result")
                if isinstance(nested, dict):
                    _merge_keep_keys_from_dict(row, nested)
                    _merge_generic_fields_from_dict(row, nested)
            elif isinstance(payload, str):
                parsed = _extract_json_object_from_text(payload)
                if isinstance(parsed, dict):
                    _merge_keep_keys_from_dict(row, parsed)
                    _merge_generic_fields_from_dict(row, parsed)
                    nested = parsed.get("result")
                    if isinstance(nested, dict):
                        _merge_keep_keys_from_dict(row, nested)
                        _merge_generic_fields_from_dict(row, nested)

        # Extract links from products array for backward compat.
        if "products" in row and "links" not in row:
            prods = row.get("products")
            if isinstance(prods, list):
                prod_links = [p.get("link") for p in prods if isinstance(p, dict) and p.get("link")]
                if prod_links:
                    row["links"] = prod_links

        # Normalize and filter links with generic detail-page heuristics.
        if "links" in row:
            raw_links = row.get("links")
            if isinstance(raw_links, str):
                raw_links = [raw_links]
            if isinstance(raw_links, list):
                filtered_links = []
                seen_links = set()
                for u in raw_links:
                    su = str(u or "").strip()
                    if not su or su in seen_links:
                        continue
                    seen_links.add(su)
                    if _is_actionable_detail_link(su):
                        filtered_links.append(su)
                if filtered_links:
                    row["links"] = filtered_links
                else:
                    row.pop("links", None)

        if "links" not in row:
            links = _extract_links(_val.get("final"), _val.get("error"), _val.get("task"))
            if links:
                links = [u for u in links if _is_actionable_detail_link(u)]
                if links:
                    row["links"] = links[:8]

        # Skip rows that only contain status/reason with no actionable payload.
        actionable_keys = set(row.keys()) - {"status", "reason"}
        if not actionable_keys:
            continue

        if row:
            compact[_nid] = row

    payload = json.dumps(compact, ensure_ascii=False)
    try:
        key_summary = {
            nid: sorted(list(val.keys()))[:15]
            for nid, val in compact.items()
            if isinstance(val, dict)
        }
        logger.info(
            f"[UpstreamCompact] node={current_node_name} "
            f"upstream_nodes={list(compact.keys())} "
            f"key_summary={key_summary} "
            f"payload_chars={len(payload)}"
        )
    except Exception:
        pass
    if len(payload) > 12000:
        payload = payload[:12000] + "...(truncated)"
    return payload


# ── Pure helpers extracted from _auto (commit 2, 2026-04-22) ─────────────
# Keeping them module-level makes the prompt-mutation pipeline readable at
# a glance and enables unit testing without building a full browser node.

def _parse_required_vars_marker(task_text_raw: str) -> list[str]:
    """Extract variable names from a `[REQUIRED_VARS:v1,v2,...]` marker.

    Returns a de-duplicated list preserving declaration order, or an empty
    list when the marker is absent or unparsable.
    """
    import re as _re
    try:
        m = _re.search(r"\[REQUIRED_VARS:([^\]]+)\]", str(task_text_raw or ""))
        if not m:
            return []
        raw = m.group(1)
        vars_list = [v.strip() for v in raw.split(",") if v.strip()]
        seen: set[str] = set()
        out: list[str] = []
        for v in vars_list:
            if v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out
    except Exception:
        return []


def _resolve_local_dir_from_prompt_var(task_text_raw: str, context: dict) -> tuple[str, str]:
    """Resolve the `[LOCAL_DIR_VAR:name]` marker against the format context.

    Returns `(var_name, resolved_path)`.  When the marker is present but
    the variable is missing/empty, returns `(var_name, "")` so callers can
    distinguish "no marker" from "marker but no value".
    """
    import re as _re
    try:
        marker_match = _re.search(r"\[LOCAL_DIR_VAR:([a-zA-Z_][a-zA-Z0-9_]*)\]", str(task_text_raw or ""))
        if not marker_match:
            return "", ""
        var_name = marker_match.group(1).strip()
        if not var_name:
            return "", ""
        value = (context or {}).get(var_name)
        if isinstance(value, str) and value.strip():
            return var_name, value.strip()
        return var_name, ""
    except Exception:
        return "", ""


def _build_local_dir_snapshot(dir_path: str) -> str:
    """Return a compact JSON snapshot of a local directory.

    The snapshot contains:
      - absolute path, existence flag, file count
      - first 60 filenames (sorted)
      - first 2400-byte prefix of up to 3 small text files
    Intended for injection into an LLM prompt so the browser-automation
    agent can ground extraction on local files without navigating the web.
    """
    import json as _json
    import os as _os
    try:
        if not dir_path:
            return ""
        abs_dir = _os.path.abspath(_os.path.expanduser(dir_path))
        payload: dict = {
            "dir_path": abs_dir,
            "exists": _os.path.isdir(abs_dir),
            "file_count": 0,
            "sample_files": [],
            "text_snippets": {},
        }
        if not payload["exists"]:
            payload["error"] = "directory_not_found"
            return _json.dumps(payload, ensure_ascii=False)

        names = sorted(_os.listdir(abs_dir))
        payload["file_count"] = len(names)
        payload["sample_files"] = names[:60]

        text_exts = {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".log"}
        picked = 0
        for name in names:
            if picked >= 3:
                break
            fpath = _os.path.join(abs_dir, name)
            if not _os.path.isfile(fpath):
                continue
            ext = _os.path.splitext(name)[1].lower()
            if ext not in text_exts:
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    snippet = f.read(2400)
                if snippet.strip():
                    payload["text_snippets"][name] = snippet
                    picked += 1
            except Exception:
                continue
        return _json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return _json.dumps({"error": f"snapshot_failed: {e}"}, ensure_ascii=False)


def _append_anti_risk_guardrails(task_text_raw: str, inputs: dict | None = None) -> str:
    """Append a shared anti-risk guardrail block to a browser task prompt.

    Idempotent: returns `task_text_raw` unchanged when the marker
    `[GLOBAL ANTI-RISK GUARDRAILS]` is already present.  The `inputs` dict
    (the node's `inputsValues`) is consulted for a `tabPolicy` override.
    """
    try:
        if not isinstance(task_text_raw, str) or not task_text_raw.strip():
            return task_text_raw

        marker = "[GLOBAL ANTI-RISK GUARDRAILS]"
        if marker in task_text_raw:
            return task_text_raw

        _tab_policy = ""
        if isinstance(inputs, dict):
            _tab_policy = str(
                (inputs.get("tabPolicy") or {}).get("content", "") or ""
            ).strip().lower()
        if _tab_policy == "allow_assigned_tab":
            tab_guardrail = (
                "2) If an assigned `tab_id` is provided for this invocation, "
                "you may and should focus that assigned tab. Do not switch to unrelated stale tabs "
                "from previous sessions. If no assigned `tab_id` is available, navigate directly to "
                "the assigned URL.\n"
            )
        else:
            tab_guardrail = (
                "2) Never use switch_tab. Always stay in the current active tab and use navigate "
                "to load any new URL. Do not switch to any stale tab from a previous run.\n"
            )

        guardrail_text = (
            "\n\n[GLOBAL ANTI-RISK GUARDRAILS]\n"
            "1) Anti-bot handling: if the page shows any rate-limit, captcha, "
            "human-verification, access-denied, or unusual-traffic warning (in any language), "
            "perform at most one low-risk recovery attempt (for example: refresh once or navigate "
            "to site home then continue with the same intent). If still blocked, return "
            "blocked(reason=risk_control).\n"
            f"{tab_guardrail}"
            "3) Low-frequency behavior: avoid repeated clicks on the same element and "
            "unnecessary refresh loops. Retry the same failed action at most once.\n"
            "4) Fast convergence: if 2-3 consecutive actions produce no meaningful state change, "
            "stop and return blocked(reason=navigation_deadlock).\n"
            "5) Minimum-necessary actions: prefer direct navigation to target pages and extract "
            "required data with the shortest path. End as soon as success criteria are met.\n"
            "6) Cooldown policy: after blocked(reason=risk_control), treat the site as cooling down "
            "for this run and continue with alternative paths or downstream steps."
        )
        return f"{task_text_raw}{guardrail_text}"
    except Exception:
        return task_text_raw


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
    # GUI stores automation backend under inputsValues.tool.content (browser-use | crawl4ai | browsebase)
    _tool_sel = ((inputs.get("tool") or {}).get("content") or "").strip().lower()
    if _tool_sel in ("browser-use", "crawl4ai", "browsebase"):
        provider = _tool_sel

    action = (config_metadata or {}).get("action") or "open_page"
    params = (config_metadata or {}).get("params") or {}
    wait_for_done = bool((config_metadata or {}).get("wait_for_done", False))
    task_text = (config_metadata or {}).get("task") or f"{action} {params}".strip()

    inputs = (config_metadata or {}).get("inputsValues", {}) or {}

    # Parse event monitor configs from node editor (Phase 1: HTTP polling)
    _event_monitor_configs = []
    event_monitor_done_policy = "keep"
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import parse_monitor_configs
        _event_monitor_configs = parse_monitor_configs(inputs)
        event_monitor_done_policy = (
            ((inputs.get("eventMonitorDonePolicy") or {}).get("content") or "keep").strip().lower() or "keep"
        )
        if event_monitor_done_policy == "teardown":
            event_monitor_done_policy = "stop"
        if _event_monitor_configs:
            logger.info(
                f"[BrowserAutomation] Parsed {len(_event_monitor_configs)} event monitor config(s): "
                f"{[c.label for c in _event_monitor_configs]}, "
                f"list_id={id(_event_monitor_configs)}, obj_ids={[id(c) for c in _event_monitor_configs]}, "
                f"skill={skill_name}"
            )
            send_skill_editor_log("log", f"[BrowserAutomation] {len(_event_monitor_configs)} event monitor(s) configured")
    except Exception as _em_parse_err:
        logger.warning(f"[BrowserAutomation] Failed to parse event monitor configs: {_em_parse_err}")

    # Extract browser settings from node editor
    browser_type_setting = ((inputs.get("browser") or {}).get("content") or "new chromium").lower().strip()
    browser_driver_setting = ((inputs.get("browserDriver") or {}).get("content") or "native").lower().strip()
    cdp_port_setting = ((inputs.get("cdpPort") or {}).get("content") or "").strip()
    # cdpPortAuto checkbox overrides cdpPort to "auto" when checked
    _cdp_port_auto_val = (inputs.get("cdpPortAuto") or {}).get("content")
    if str(_cdp_port_auto_val).lower() in ("true", "1", "yes", "on"):
        cdp_port_setting = "auto"
    
    # Extract headless mode setting from node editor
    node_headless = False
    try:
        headless_val = (inputs.get("headless") or {}).get("content")
        node_headless = str(headless_val).lower() in ('true', '1', 'yes', 'on') if headless_val is not None else False
    except Exception:
        node_headless = False

    # Extract new browser automation options from node editor
    run_environment_setting = ((inputs.get("runEnvironment") or {}).get("content") or "full_local").lower().strip()
    privacy_strategy_setting = ((inputs.get("privacyStrategy") or {}).get("content") or "none").lower().strip()
    enable_judge_setting = False
    try:
        enable_judge_val = (inputs.get("enableJudge") or {}).get("content")
        enable_judge_setting = str(enable_judge_val).lower() in ('true', '1', 'yes', 'on') if enable_judge_val is not None else False
    except Exception:
        enable_judge_setting = False
    
    # Extract LLM provider/model settings from node editor (like build_llm_node)
    node_llm_provider = None
    try:
        node_llm_provider = ((inputs.get("modelProvider") or {}).get("content")
                             or (inputs.get("provider") or {}).get("content"))
    except Exception:
        node_llm_provider = None
    node_model_name = ((inputs.get("modelName") or {}).get("content")
                       or (inputs.get("model") or {}).get("content")
                       or None)
    
    # Extract useThinking setting from node editor (for browser_use Agent)
    node_use_thinking = False
    try:
        use_thinking_val = (inputs.get("useThinking") or {}).get("content")
        node_use_thinking = str(use_thinking_val).lower() in ('true', '1', 'yes', 'on') if use_thinking_val is not None else False
    except Exception:
        node_use_thinking = False
    
    # Extract useVision setting from node editor (for browser_use Agent)
    node_use_vision = False
    try:
        use_vision_val = (inputs.get("useVision") or {}).get("content")
        node_use_vision = str(use_vision_val).lower() in ('true', '1', 'yes', 'on') if use_vision_val is not None else False
    except Exception:
        node_use_vision = False
    
    # Extract browser profile setting from node editor
    node_profile = ((inputs.get("profile") or {}).get("content") or "").strip()
    
    # Extract performance settings from node editor (for multi-customer chat scenarios)
    node_flash_mode = False
    try:
        flash_mode_val = (inputs.get("flashMode") or {}).get("content")
        node_flash_mode = str(flash_mode_val).lower() in ('true', '1', 'yes', 'on') if flash_mode_val is not None else False
    except Exception:
        node_flash_mode = False
    
    node_max_steps = None
    try:
        max_steps_val = (inputs.get("maxSteps") or {}).get("content")
        if max_steps_val:
            node_max_steps = int(max_steps_val)
    except Exception:
        node_max_steps = None
    
    node_max_actions_per_step = None
    try:
        max_actions_val = (inputs.get("maxActionsPerStep") or {}).get("content")
        if max_actions_val:
            node_max_actions_per_step = int(max_actions_val)
    except Exception:
        node_max_actions_per_step = None


    # Optional node-level hard timeout for browser automation runtime (seconds).
    # Keep this separate from LLM request timeout so we can cap the whole node duration.
    # Minimum floor: browser automation involves multiple LLM calls + page navigations,
    # so timeouts below 300s typically cause premature failures.
    _BROWSER_MIN_TIMEOUT_SEC = 300
    node_timeout_seconds = None
    try:
        timeout_val = ((inputs.get("nodeTimeoutSeconds") or {}).get("content")
                       or (inputs.get("timeoutSeconds") or {}).get("content"))
        if timeout_val not in (None, ""):
            _timeout = float(timeout_val)
            node_timeout_seconds = _timeout if _timeout > 0 else None
            if node_timeout_seconds and node_timeout_seconds < _BROWSER_MIN_TIMEOUT_SEC:
                logger.warning(
                    f"[BrowserAutomation] node_timeout_seconds={node_timeout_seconds}s is below "
                    f"minimum {_BROWSER_MIN_TIMEOUT_SEC}s for browser automation. "
                    f"Bumping to {_BROWSER_MIN_TIMEOUT_SEC}s to prevent premature timeout."
                )
                send_skill_editor_log(
                    "warning",
                    f"[BrowserAutomation] Timeout {node_timeout_seconds}s too short, "
                    f"raised to {_BROWSER_MIN_TIMEOUT_SEC}s minimum"
                )
                node_timeout_seconds = _BROWSER_MIN_TIMEOUT_SEC
    except Exception:
        node_timeout_seconds = None
    
    # DOM reduction settings (data-driven, replaces hardcoded skill-specific limits)
    node_dom_focus_selector = ""
    try:
        node_dom_focus_selector = ((inputs.get("domFocusSelector") or {}).get("content") or "").strip()
    except Exception:
        node_dom_focus_selector = ""

    node_dom_limit = None
    try:
        dom_limit_val = str((inputs.get("domLimit") or {}).get("content") or "").strip()
        if dom_limit_val and dom_limit_val.isdigit():
            node_dom_limit = int(dom_limit_val)
    except Exception:
        node_dom_limit = None

    # loopHistoryMode — controls how the browser-use sub-agent's history is handled
    # when the agent is reused across pend_event loop iterations (within the same task).
    # Values:
    #   "clear"      (default) — wipe history + message_manager on each round; agent
    #                            starts every iteration with a clean slate.  Best for
    #                            stateless workflows (e.g. front-desk dispatch loop).
    #   "trim:<N>"             — keep only the last N history items (rolling window).
    #                            Useful when some recent context helps but full history bloats.
    #   "accumulate"           — keep all history across rounds.  Use only for short-lived
    #                            loops where cross-round memory is intentional.
    _loop_history_mode_raw = (
        ((inputs.get("loopHistoryMode") or {}).get("content") or "clear").strip().lower() or "clear"
    )
    # Normalise: "trim" without N defaults to trim:10
    if _loop_history_mode_raw == "trim":
        _loop_history_mode_raw = "trim:10"
    loop_history_mode = _loop_history_mode_raw  # e.g. "clear", "trim:10", "accumulate"

    # actionableField — name of the per-item field whose non-empty value
    # marks that item as actionable (needs work this round). When set, the
    # browser-event task hint emits a deterministic `actionable_items` list
    # (filtered from raw event items) instead of dumping every raw item, plus
    # a hard rule that the LLM MUST process each entry. Defeats LLM
    # hallucination of "already handled" claims since the list is ground
    # truth, not LLM interpretation. Domain-agnostic: works for customer
    # support (pending reply), inbox triage (unread), queue processing,
    # form-filling checklists, etc. — any extractor that populates this
    # field works. Leave empty to preserve legacy raw-items behavior.
    actionable_field = (
        ((inputs.get("actionableField") or {}).get("content") or "").strip()
    )

    logger.info(f"[BrowserAutomation] Extracted from node editor: provider={node_llm_provider}, model={node_model_name}, use_thinking={node_use_thinking}, use_vision={node_use_vision}, profile={node_profile}")
    logger.info(
        f"[BrowserAutomation] Performance settings: flash_mode={node_flash_mode}, "
        f"max_steps={node_max_steps}, max_actions_per_step={node_max_actions_per_step}, "
        f"node_timeout_seconds={node_timeout_seconds}, "
        f"dom_focus_selector={node_dom_focus_selector!r}, dom_limit={node_dom_limit}"
    )
    send_skill_editor_log("log", f"[BrowserAutomation] Node LLM settings: provider={node_llm_provider}, model={node_model_name}")
    
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
    
    logger.debug(f"[BrowserAutomation] browser={browser_type_setting}, driver={browser_driver_setting}, cdp_port={cdp_port_setting}, headless={node_headless}")
    logger.debug(f"[BrowserAutomation] run_environment={run_environment_setting}, privacy_strategy={privacy_strategy_setting}, enable_judge={enable_judge_setting}")
    logger.debug(f"[BrowserAutomation] shop_name={shop_name}, downloads_path={downloads_path}")


    prompt_selection = ((inputs.get("promptSelection") or {}).get("content") or "inline").strip()
    logger.info(f"[BrowserAutomation] 🔍 prompt_selection='{prompt_selection}'")
    send_skill_editor_log("log", f"[BrowserAutomation] Prompt selection: '{prompt_selection}'")

    system_prompt_id = ((inputs.get("systemPromptId") or {}).get("content") or None)
    user_prompt_id = ((inputs.get("promptId") or {}).get("content") or None)

    # Get inline prompt content
    inline_system_prompt = ((inputs.get("systemPrompt") or {}).get("content") or "")
    inline_user_prompt = ((inputs.get("prompt") or {}).get("content") or "")
    
    logger.info(f"[BrowserAutomation] 📝 Raw inline prompts - system: {len(inline_system_prompt)} chars, user: {len(inline_user_prompt)} chars")

    # Clear inline prompts when a saved prompt is selected to prevent stale inline content from overriding
    if prompt_selection and prompt_selection not in ("", "inline"):
        logger.info(f"[BrowserAutomation] ✂️ Using saved prompt '{prompt_selection}', clearing inline prompts to prevent override")
        send_skill_editor_log("log", f"[BrowserAutomation] Using saved prompt '{prompt_selection}', clearing inline prompts")
        inline_system_prompt = ""
        inline_user_prompt = ""
    else:
        logger.info(f"[BrowserAutomation] 📄 Using inline prompts (selection='{prompt_selection}')")

    logger.debug("[BrowserAutomation]inline_system_prompt:", inline_system_prompt)
    logger.debug("[BrowserAutomation]inline_user_prompt:", inline_user_prompt)
    # Load prompts using prompt loader (handles both inline and saved prompts)
    # Resolve prompt templates based on the selected prompt id first for initial config preview
    logger.info(f"[BrowserAutomation] 🔄 Calling _resolve_prompt_templates with selection='{prompt_selection}', skill_owner='{owner}'")
    resolved_system_prompt, resolved_user_prompt, _browser_prompt_vars = _resolve_prompt_templates(
        prompt_selection,
        inline_system_prompt,
        inline_user_prompt,
        skill_owner=owner or "",
    )
    
    logger.info(f"[BrowserAutomation] ✅ Resolved prompts - system: {len(resolved_system_prompt)} chars, user: {len(resolved_user_prompt)} chars")
    send_skill_editor_log("log", f"[BrowserAutomation] Resolved prompt lengths - system: {len(resolved_system_prompt)}, user: {len(resolved_user_prompt)}")
    
    # Log first 200 chars of resolved prompts for debugging
    if resolved_user_prompt:
        preview = resolved_user_prompt[:200] + "..." if len(resolved_user_prompt) > 200 else resolved_user_prompt
        logger.info(f"[BrowserAutomation] 📋 User prompt preview: {preview}")
        send_skill_editor_log("log", f"[BrowserAutomation] User prompt preview: {preview}")

    # Use the already-resolved prompts directly (no need to call get_prompt_content again)
    # _resolve_prompt_templates already loaded and processed the prompt
    system_prompt_content = resolved_system_prompt if resolved_system_prompt else None
    user_prompt_content = resolved_user_prompt if resolved_user_prompt else None

    # Inject tools_to_use from skill node inputsValues when present.
    # This is critical for skills that define tools_to_use in the node config
    # (e.g. {{tools_schema}}) rather than inside the saved prompt record.
    _inputs_tools = inputs.get("tools_to_use") or {}
    _inputs_tools_content = _inputs_tools.get("content", "") if isinstance(_inputs_tools, dict) else str(_inputs_tools or "")
    if _inputs_tools_content.strip():
        logger.info(f"[BrowserAutomation] 📦 Found tools_to_use in inputsValues: {len(_inputs_tools_content)} chars")
        try:
            _tools_section = _format_tools_to_use_section([_inputs_tools_content])
            if _tools_section:
                _tools_label = "[Available Tools]\nAll MCP tool schemas (use exact names when calling):\n"
                if system_prompt_content:
                    system_prompt_content = system_prompt_content.rstrip() + "\n\n" + _tools_label + _tools_section
                    logger.info(f"[BrowserAutomation] ✅ Appended tools_to_use to system prompt (+{len(_tools_section)} chars)")
                else:
                    system_prompt_content = _tools_label + _tools_section
                    logger.info(f"[BrowserAutomation] ✅ Created system prompt from tools_to_use only (+{len(_tools_section)} chars)")
        except Exception as _t_err:
            logger.warning(f"[BrowserAutomation] Failed to resolve tools_to_use: {_t_err}")

    # If prompts are configured, use them to enhance the task text
    logger.info(f"[BrowserAutomation] 🔧 Before prompt override - task_text length: {len(task_text)} chars")
    if system_prompt_content or user_prompt_content:
        prompt_parts = []
        if system_prompt_content:
            prompt_parts.append(f"System Instructions:\n{system_prompt_content}")
        if user_prompt_content:
            prompt_parts.append(f"Task:\n{user_prompt_content}")
        if prompt_parts:
            task_text = "\n\n".join(prompt_parts)
            logger.info(f"[BrowserAutomation] ✅ Overrode task_text with prompt content - new length: {len(task_text)} chars")
            send_skill_editor_log("log", f"[BrowserAutomation] Using prompt content as task (length: {len(task_text)})")
    else:
        logger.warning(f"[BrowserAutomation] ⚠️ No prompt content resolved, keeping original task_text")
        send_skill_editor_log("warning", f"[BrowserAutomation] No prompt content found, using original task field")





    # Fix E-F1: Cache browser_session across steps so we don't create a new one
    # each iteration.  BrowserManager.acquire_browser marks the browser IN_USE,
    # so subsequent find_available_browser calls miss it and create_browser builds
    # a brand-new BrowserSession (resetting agent_focus_target_id to the first tab).

    # Cache browser-use sub-agents across loop iterations (one per scope/task).
    # The browser-use Agent is heavyweight — it owns MessageManager, history, LLM
    # client references, etc.  Re-creating it on every pend_event cycle wastes ~860 MB
    # of allocations per cycle and adds unnecessary init overhead.
    # Keyed by the same _browser_scope_key used for _cached_browser_sessions.


    def _is_matching_control_url(actual_url: str, preferred_url: str) -> bool:
        """Treat localhost and 127.0.0.1 control-panel URLs as equivalent."""
        if not actual_url or not preferred_url:
            return False
        try:
            actual = urlparse(actual_url)
            preferred = urlparse(preferred_url)
            actual_host = (actual.hostname or "").lower()
            preferred_host = (preferred.hostname or "").lower()
            local_hosts = {"127.0.0.1", "localhost"}
            if actual_host not in local_hosts or preferred_host not in local_hosts:
                return actual_url.rstrip("/") == preferred_url.rstrip("/")
            return (
                (actual.port or 80) == (preferred.port or 80)
                and actual.path.rstrip("/").startswith("/control")
                and preferred.path.rstrip("/").startswith("/control")
            )
        except Exception:
            return actual_url.rstrip("/") == preferred_url.rstrip("/")

    def _reset_bu_agent_for_next_round(agent: Any, mode: str, task: str) -> None:
        """Delegator → :func:`browser_node.agent.reset_bu_agent_for_next_round`.

        The closure form is preserved so existing call sites inside
        ``build_browser_automation_node`` keep working.  All real logic
        (history clamp, AgentOutput restore, LoopDetector reset, state
        reset) now lives in the dedicated module.
        """
        from agent.ec_skills.browser_node.agent import (
            reset_bu_agent_for_next_round as _impl,
        )
        _impl(agent, mode, task)






    # ─── Phase 6 RunContext construction (2026-04-24) ────────────────
    # Captures every build-scope closure ref needed by
    # ``_BrowserRunSession``.  Built once, shared across every
    # ``_run_browser_use`` invocation for this compiled node.  Field
    # naming preserves the original closure-name underscores so the
    # mass-rewrite from ``X`` to ``self.ctx.X`` could be a pure
    # symbol-substitution.  Mutable dict / list fields are passed by
    # reference (not copied), so cache mutations performed by helpers
    # persist across runs.
    from agent.ec_skills.browser_node.runner import RunContext as _RunContext
    _run_ctx = _RunContext(
        # identity
        node_name=node_name, skill_name=skill_name, owner=owner, inputs=inputs,
        # settings
        node_llm_provider=node_llm_provider, node_model_name=node_model_name,
        node_use_vision=node_use_vision, node_use_thinking=node_use_thinking,
        node_max_actions_per_step=node_max_actions_per_step,
        node_dom_limit=node_dom_limit, node_dom_focus_selector=node_dom_focus_selector,
        node_profile=node_profile, node_headless=node_headless,
        node_max_steps=node_max_steps, node_timeout_seconds=node_timeout_seconds,
        enable_judge_setting=enable_judge_setting,
        system_prompt_id=system_prompt_id, user_prompt_id=user_prompt_id,
        loop_history_mode=loop_history_mode,
        privacy_strategy_setting=privacy_strategy_setting,
        run_environment_setting=run_environment_setting,
        event_monitor_done_policy=event_monitor_done_policy,
        browser_type_setting=browser_type_setting,
        browser_driver_setting=browser_driver_setting,
        cdp_port_setting=cdp_port_setting,
        downloads_path=downloads_path,
        actionable_field=actionable_field,
        # hook lists
        before_browser_session_setup_hooks=_before_browser_session_setup_hooks,
        before_prompt_build_hooks=_before_prompt_build_hooks,
        before_browser_use_run_hooks=_before_browser_use_run_hooks,
        # event monitors
        event_monitor_configs=_event_monitor_configs,
    )

    async def _run_browser_use(task: str, mainwin, state: dict | None = None, calling_agent_id: str | None = None) -> dict:
        """Thin delegator — orchestrates a single browser-use run.

        Body lives in :class:`_BrowserRunSession` (defined just below)
        so phases can be split into methods incrementally without
        further perturbing this delegator.  See class docstring.
        """
        return await _BrowserRunSession(
            ctx=_run_ctx,
            task=task,
            mainwin=mainwin,
            state=state,
            calling_agent_id=calling_agent_id,
        ).run()

    # ─── Phase 6.3: BrowserRunSession lifted to browser_node/runner.py ──
    # The class body (formerly ~1649 lines here) now lives in
    # ``agent.ec_skills.browser_node.runner.BrowserRunSession``.  This module
    # keeps a local alias for the historical ``_BrowserRunSession`` name so
    # docstring references / debugger hits still resolve.
    from agent.ec_skills.browser_node.runner import BrowserRunSession as _BrowserRunSession

    # ── Inner helpers for _auto (commit 3, 2026-04-22) ────────────────────
    # Declared here so they close over `_run_browser_use`,
    # `_resolve_browser_scope_key`, `_event_monitor_configs`, `skill_name`,
    # `node_name`, `owner`, and the other build-scope closures.  Keeps
    # `_auto`'s linear flow compact without plumbing 10+ params into
    # module-level helpers.

    def _execute_browser_use_run(
        *,
        state: dict,
        runtime,
        combined_task: str,
        mainwin,
        agent_id: str | None,
        use_hard_timeout: bool,
        effective_timeout: float,
        correlation_id,
    ) -> dict:
        """Run `_run_browser_use` in the appropriate worker loop.

        Handles hard/soft timeout, persistent vs per-call worker selection,
        guardrail-timer cancellation on success, and exception-to-info
        conversion (including suppression of non-fatal watchdog teardown
        noise).  Always returns an `info` dict — never raises.
        """
        import time as _exbu_time
        info: dict = {}
        try:
            if use_hard_timeout:
                import asyncio
                log_msg = f"[BROWSER_HARD_TIMEOUT] Using hard timeout ({effective_timeout}s) - will cancel on timeout"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)
                try:
                    async def _run_with_hard_timeout():
                        return await asyncio.wait_for(
                            _run_browser_use(combined_task, mainwin, state, agent_id),
                            timeout=effective_timeout
                        )
                    if _event_monitor_configs:
                        from agent.ec_skills.llm_utils.llm_utils import run_async_in_persistent_worker_thread
                        from agent.ec_skills.browser_node import build_helpers as _bh
                        _browser_scope_key = _bh.resolve_browser_scope_key(state, node_name=node_name)
                        _worker_suffix = re.sub(r"[^\w\-]+", "_", f"{skill_name}_{node_name}_{_browser_scope_key}")
                        logger.info(
                            f"[BrowserAutomation] Using persistent worker loop for event-monitored run: "
                            f"{_worker_suffix} "
                            f"(skill={skill_name}, node={node_name}, scope={_browser_scope_key}, "
                            f"task_id={(state.get('attributes') or {}).get('task_id') if isinstance(state, dict) else ''}, "
                            f"chat_id={state.get('chat_id') if isinstance(state, dict) else ''})"
                        )
                        info = run_async_in_persistent_worker_thread(
                            _run_with_hard_timeout,
                            worker_name=f"browser-use-persistent-{_worker_suffix}",
                        ) or {}
                    else:
                        from agent.ec_skills.llm_utils.llm_utils import run_async_in_worker_thread
                        info = run_async_in_worker_thread(_run_with_hard_timeout) or {}
                except asyncio.TimeoutError:
                    error_msg = f"Browser automation timed out after {effective_timeout}s (hard timeout)"
                    logger.error(f"[BROWSER_HARD_TIMEOUT] {error_msg}")
                    send_skill_editor_log("error", error_msg)
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
                if _event_monitor_configs:
                    from agent.ec_skills.llm_utils.llm_utils import run_async_in_persistent_worker_thread
                    from agent.ec_skills.browser_node import build_helpers as _bh
                    _browser_scope_key = _bh.resolve_browser_scope_key(state, node_name=node_name)
                    _worker_suffix = re.sub(r"[^\w\-]+", "_", f"{skill_name}_{node_name}_{_browser_scope_key}")
                    logger.info(
                        f"[BrowserAutomation] Using persistent worker loop for event-monitored run: "
                        f"{_worker_suffix} "
                        f"(skill={skill_name}, node={node_name}, scope={_browser_scope_key}, "
                        f"task_id={(state.get('attributes') or {}).get('task_id') if isinstance(state, dict) else ''}, "
                        f"chat_id={state.get('chat_id') if isinstance(state, dict) else ''})"
                    )
                    _worker_t0 = _exbu_time.perf_counter()
                    logger.info(
                        f"[BA._auto] worker_call start node={node_name} kind=persistent worker={_worker_suffix}"
                    )
                    info = run_async_in_persistent_worker_thread(
                        lambda: _run_browser_use(combined_task, mainwin, state, agent_id),
                        worker_name=f"browser-use-persistent-{_worker_suffix}",
                    ) or {}
                    logger.info(
                        f"[BA._auto] worker_call done node={node_name} kind=persistent "
                        f"elapsed_ms={(_exbu_time.perf_counter()-_worker_t0)*1000:.0f} "
                        f"info_keys={list(info.keys()) if isinstance(info, dict) else type(info).__name__}"
                    )
                else:
                    from agent.ec_skills.llm_utils.llm_utils import run_async_in_worker_thread
                    _worker_t0 = _exbu_time.perf_counter()
                    logger.info(f"[BA._auto] worker_call start node={node_name} kind=per_call")
                    info = run_async_in_worker_thread(lambda: _run_browser_use(combined_task, mainwin, state, agent_id)) or {}
                    logger.info(
                        f"[BA._auto] worker_call done node={node_name} kind=per_call "
                        f"elapsed_ms={(_exbu_time.perf_counter()-_worker_t0)*1000:.0f} "
                        f"info_keys={list(info.keys()) if isinstance(info, dict) else type(info).__name__}"
                    )

            # Cancel guardrail timer on success
            if correlation_id:
                try:
                    task = state.get('_managed_task')
                    if task is None and runtime and hasattr(runtime, 'context'):
                        task = runtime.context.get('task') or runtime.context.get('managed_task')
                    if task:
                        resolve_async_operation(task, correlation_id, result={"status": "completed"})
                        logger.info(f"[BROWSER_GUARDRAIL] Cancelled timer {correlation_id} (browser automation completed)")
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

            import traceback as _traceback
            _err_text = str(e).strip() or repr(e)
            _err_type = type(e).__name__
            _tb = _traceback.format_exc()
            error_msg = f"browser-use run failed: {_err_text}"
            _err_text_l = _err_text.lower()
            _tb_l = (_tb or "").lower()
            _is_nonfatal_watchdog_noise = (
                "root cdp client not initialized" in _err_text_l
                and ("watchdog" in _err_text_l or "watchdog" in _tb_l)
            )
            if _is_nonfatal_watchdog_noise:
                logger.warning(f"[BrowserAutomation] Non-fatal watchdog noise suppressed: {error_msg}")
                logger.debug(f"[BrowserAutomation] suppressed traceback:\n{_tb}")
                send_skill_editor_log(
                    "warning",
                    "⚠️ [BrowserAutomation] Suppressed non-fatal watchdog teardown noise",
                )
                info = {
                    "status": "warning",
                    "warning_type": "non_fatal_watchdog_noise",
                    "warning": error_msg,
                }
            else:
                logger.error(f"[BrowserAutomation] {error_msg}")
                logger.error(f"[BrowserAutomation] exception_type={_err_type}, exception_repr={repr(e)}")
                logger.debug(f"[BrowserAutomation] traceback:\n{_tb}")
                send_skill_editor_log("error", f"❌ [BrowserAutomation] {error_msg}")
                info = {
                    "error": error_msg,
                    "error_type": _err_type,
                    "error_repr": repr(e),
                    "traceback": _tb,
                }
        return info

    def _apply_required_vars_preflight(state: dict, combined_task: str, format_context: dict) -> bool:
        """Fail-fast check for missing `[REQUIRED_VARS:...]` placeholders.

        When one or more declared variables are missing or empty in
        `format_context`, this writes a blocked payload into
        `state["tool_result"][node_name]`, appends a history entry and
        returns ``True``.  Otherwise returns ``False`` and leaves state
        unchanged.  Swallows unexpected errors (treated as non-blocking).
        """
        try:
            _required_vars = _parse_required_vars_marker(combined_task)
            if not _required_vars:
                return False

            _missing_vars: list[str] = []
            _missing_details: list[str] = []
            _placeholders_in_text = set(re.findall(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}", str(combined_task or "")))
            for _v in _required_vars:
                _val = (format_context or {}).get(_v)
                if _val is None or str(_val).strip() == "":
                    _missing_vars.append(_v)
                    if _v not in _placeholders_in_text:
                        _missing_details.append(
                            f"  - '{_v}': placeholder {{{{{_v}}}}} not found in prompt text. "
                            f"The resolver only processes variables that appear as {{{{name}}}} "
                            f"in the prompt body. Fix: add '| {_v} | {{{{{_v}}}}} |' to the "
                            f"input parameters table in the prompt."
                        )
                    else:
                        _missing_details.append(
                            f"  - '{_v}': placeholder {{{{{_v}}}}} exists in prompt but resolved "
                            f"to empty. Check that an upstream node outputs a field named '{_v}' "
                            f"in its JSON result, or that init_params defines it."
                        )

            if not _missing_vars:
                return False

            _diag_lines = "\n".join(_missing_details)
            _blocked_payload = {
                "status": "blocked",
                "reason": "missing_required_inputs",
                "missing_fields": _missing_vars,
                "node": node_name,
                "notes": f"Missing required variables: {', '.join(_missing_vars)}",
                "diagnosis": _diag_lines.strip(),
            }
            state.setdefault("tool_result", {})
            if isinstance(state.get("tool_result"), dict):
                state["tool_result"][node_name] = _blocked_payload
            state["result"] = _blocked_payload
            add_to_history(
                state,
                ActionMessage(
                    content=(
                        f"action: browser-use preflight; "
                        f"result: blocked(reason=missing_required_inputs, "
                        f"missing={_missing_vars})"
                    )
                ),
            )
            send_skill_editor_log(
                "warning",
                f"[BrowserAutomation] Preflight BLOCKED — node='{node_name}' "
                f"missing vars: {_missing_vars}\n"
                f"Diagnosis per variable:\n{_diag_lines}\n"
                f"Placeholders found in prompt text: {sorted(_placeholders_in_text)}",
            )
            return True
        except Exception:
            return False

    def _finalize_automation_result(
        *,
        state: dict,
        info: dict,
        provider: str,
        task_instructions: str,
        final_system_prompt: str,
        action: str,
        wait_for_done: bool,
    ) -> dict:
        """Persist the browser-automation run result into state.

        Writes `tool_result[node_name]`, increments `n_steps`, optionally
        raises an interrupt for human check, and appends a truncated
        history entry.  Returns the (mutated) state.
        """
        state.setdefault("tool_result", {})
        tr = state.get("tool_result")
        if not isinstance(tr, dict):
            tr = {}
            state["tool_result"] = tr
        tr[node_name] = {
            "provider": provider,
            "task": task_instructions,
            "systemPrompt": final_system_prompt,
            **info,
        }

        if wait_for_done and info.get("error"):
            interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Automation pending: {action}"})

        try:
            state["n_steps"] = int(state.get("n_steps", 0) or 0) + 1
        except Exception:
            state["n_steps"] = 1

        from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
        info_for_history = truncate_screenshot_for_logging(info)
        add_to_history(state, ActionMessage(content=f"action: {provider} {task_instructions}; result: {info_for_history}"))

        return state

    def _auto(state: dict, *, runtime=None, store=None, **kwargs):
        # ── Entry trace (diagnostic) ──
        # Added 2026-04-22 after repeated hangs observed between the node
        # entry wrapper log and the first HOT-PATH-B / PreDispatch log.
        # These info-level checkpoints make the hang location visible
        # without requiring a debugger attach.
        import time as _ba_auto_time
        _ba_auto_t0 = _ba_auto_time.perf_counter()
        try:
            _ba_auto_thread_name = threading.current_thread().name
        except Exception:
            _ba_auto_thread_name = "?"
        logger.info(
            f"[BA._auto] enter node={node_name} thread={_ba_auto_thread_name} "
            f"state_keys={list(state.keys()) if isinstance(state, dict) else type(state).__name__}"
        )

        # Use the pre-resolved prompts from build time (when cloud context was available)
        # instead of calling _resolve_prompt_templates again at runtime
        active_system_prompt = resolved_system_prompt
        active_user_prompt = resolved_user_prompt

        # Find all variable placeholders (e.g., {{var_name}}) in the prompts
        variables = re.findall(r'\{\{(\w+)\}\}', active_system_prompt + active_user_prompt)

        # Use cascading variable resolution
        _ba_mainwin = None
        try:
            from app_context import AppContext
            _ba_mainwin = AppContext.get_main_window()
        except Exception:
            pass

        # Copy scalar browser node inputsValues into state["prompt_refs"].
        # Empty strings are skipped: an empty inputsValue means "not configured here",
        # so the upstream implicit resolver (priority 1.5 in resolve_prompt_variables)
        # can supply the value from a previous node's tool_result output instead.
        prompt_refs = {}
        try:
            if isinstance(state, dict):
                prompt_refs = state.setdefault("prompt_refs", {})
                if not isinstance(prompt_refs, dict):
                    prompt_refs = {}
                    state["prompt_refs"] = prompt_refs

                for _key, _raw in (inputs or {}).items():
                    if not isinstance(_raw, dict) or "content" not in _raw:
                        continue
                    _val = _raw.get("content")
                    if isinstance(_val, (str, int, float, bool)):
                        if isinstance(_val, str) and not _val.strip():
                            continue
                        prompt_refs[_key] = _val

                # Prevent prompt bloat when upstream_outputs is requested.
                # Logic extracted to module-level `_compact_tool_result_for_prompt`.
                if "upstream_outputs" in variables:
                    prompt_refs["upstream_outputs"] = _compact_tool_result_for_prompt(state, node_name)
        except Exception as _inject_prompt_ref_err:
            logger.debug(f"[BrowserAutomation] Failed injecting node inputsValues into prompt_refs: {_inject_prompt_ref_err}")

        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables
        format_context = resolve_prompt_variables(
            variable_names=variables,
            state=state if isinstance(state, dict) else {},
            mainwin=_ba_mainwin,
            prompt_variables=_browser_prompt_vars,
        )

        # Diagnostic: template placeholder resolution (generic — no assumption about key names).
        try:
            if variables:
                _lens = {v: len(str(format_context.get(v) or "")) for v in variables}
                logger.info(
                    f"[BrowserAutomation][PromptTemplateCheck] node={node_name} "
                    f"placeholders={variables} value_lens={_lens}"
                )
        except Exception:
            pass

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
            send_skill_editor_log("error", err_msg)
            state['error'] = err_msg
            final_system_prompt = active_system_prompt
            final_user_prompt = active_user_prompt

        # --- Data Availability Summary ---
        # After resolving template variables, check which ones are empty and inject
        # a summary so the browser agent knows what upstream data is missing and can
        # skip impossible steps (e.g. image upload when no images were downloaded).
        try:
            if variables and format_context:
                # Deduplicate variable names while preserving order
                unique_vars = list(dict.fromkeys(variables))
                _empty_vars = [
                    v for v in unique_vars
                    if not str(format_context.get(v) or "").strip()
                ]
                _present_vars = [
                    v for v in unique_vars
                    if str(format_context.get(v) or "").strip()
                ]
                if _empty_vars:
                    _availability_lines = []
                    if _present_vars:
                        _availability_lines.append(f"✅ Available: {', '.join(_present_vars)}")
                    _availability_lines.append(f"❌ Missing/empty: {', '.join(_empty_vars)}")
                    _availability_lines.append(
                        "IMPORTANT: Do NOT attempt to use or search for missing data. "
                        "Skip any steps that depend on missing variables. "
                        "For example, if original_images or product_dir is missing, "
                        "skip the image upload phase entirely and proceed to the next phase."
                    )
                    _data_avail_section = "\n[DATA AVAILABILITY]\n" + "\n".join(_availability_lines) + "\n"
                    # Append to user prompt so it's visible in the task
                    final_user_prompt = (final_user_prompt or "") + _data_avail_section
                    logger.info(
                        f"[BrowserAutomation] Injected data availability summary for node={node_name}: "
                        f"empty={_empty_vars}, present={_present_vars}"
                    )
                    send_skill_editor_log(
                        "warning",
                        f"[BrowserAutomation] {node_name}: missing upstream data: {', '.join(_empty_vars)}"
                    )
        except Exception as _data_avail_err:
            logger.debug(f"[BrowserAutomation] Data availability check failed: {_data_avail_err}")

        # Combine prompts into task instructions for browser_use agent
        task_instructions = final_user_prompt.strip() or task_text or final_system_prompt.strip()
        
        # Validate that we have a task (P0 Fix: prevent empty task)
        if not task_instructions:
            default_task = "Browse the current webpage and report what you find."
            logger.warning(
                f"[BrowserAutomation] ⚠️ No task provided (system_prompt, user_prompt, and task_text are all empty). "
                f"Using default task: {default_task}"
            )
            send_skill_editor_log("warning", f"[BrowserAutomation] No task specified, using default task")
            task_instructions = default_task
        
        if final_system_prompt.strip():
            combined_task = f"{final_system_prompt.strip()}\n\n{task_instructions}"
        else:
            combined_task = task_instructions

        # Fast preflight: fail early on missing required prompt variables
        # (marker-driven, avoids an expensive LLM/browser round-trip).
        # Extracted to _apply_required_vars_preflight (commit 3 cleanup).
        _preflight_blocked = _apply_required_vars_preflight(state, combined_task, format_context)
        if _preflight_blocked:
            return state

        # Deterministic local-directory grounding for local-analysis prompts.
        # Variable name is defined by prompt marker, e.g. [LOCAL_DIR_VAR:local_dir].
        # _resolve_local_dir_from_prompt_var and _build_local_dir_snapshot
        # extracted to module level (commit 2).
        _local_dir_grounded = False
        try:
            _enable_local_dir_grounding = "[LOCAL_DIR_GROUNDING:ON]" in str(combined_task or "")

            if _enable_local_dir_grounding:
                _local_dir_var_name, configured_dir = _resolve_local_dir_from_prompt_var(combined_task, format_context)
                local_snapshot = _build_local_dir_snapshot(configured_dir)
                if local_snapshot:
                    _local_dir_grounded = True
                    combined_task = (
                        f"{combined_task}\n\n"
                        "[LOCAL PRODUCT DIRECTORY SNAPSHOT]\n"
                        f"{local_snapshot}\n\n"
                        "[STRICT EXECUTION RULES FOR THIS NODE]\n"
                        "1) This node must use the local directory snapshot above as primary evidence.\n"
                        "2) Do NOT navigate websites, do NOT search web, do NOT switch tabs.\n"
                        "3) If fields are missing, infer conservatively from filenames/snippets only.\n"
                        "4) Output final JSON directly once extracted."
                    )
                elif configured_dir == "":
                    combined_task = (
                        f"{combined_task}\n\n"
                        "[LOCAL PRODUCT DIRECTORY SNAPSHOT]\n"
                        f"{{\"error\":\"missing_local_dir_variable\",\"variable\":\"{_local_dir_var_name or 'LOCAL_DIR_VAR_NOT_SET'}\"}}\n\n"
                        "[STRICT EXECUTION RULES FOR THIS NODE]\n"
                        "Required local directory variable is missing. "
                        "Return blocked(reason=missing_local_dir_variable) immediately."
                    )
        except Exception:
            pass

        # Global anti-risk guardrails extracted to module level (commit 2).
        # Skip for local-directory grounded nodes, otherwise these web-centric
        # instructions may conflict with local-only extraction intent.
        if not _local_dir_grounded:
            combined_task = _append_anti_risk_guardrails(combined_task, inputs)

        # ── Suppress duplicate initial-URL navigation for reused sessions ──
        # browser-use auto-detects URLs in the task text and navigates to them
        # on agent startup.  When a persistent browser session already has the
        # target tab open, this creates a duplicate tab.  If the node's
        # `assignment.strip_url_regex` is set, strip matching bare URLs from the
        # task text so browser-use doesn't reopen them.
        try:
            _strip_regex_src = ""
            _strip_replacement = "[assigned chat tab already open]"
            # Re-parse assignment config locally — this block lives in `_auto`,
            # while the upstream `_asg_cfg` is bound in the sibling closure
            # `_run_browser_use` and is not visible here.
            _asg_cfg_local = _parse_json_input(inputs, "assignment")
            if isinstance(_asg_cfg_local, dict):
                _strip_regex_src = str(_asg_cfg_local.get("strip_url_regex") or "").strip()
                _strip_replacement = str(
                    _asg_cfg_local.get("strip_url_replacement") or _strip_replacement
                )
            if _strip_regex_src:
                from agent.ec_skills.browser_node import build_helpers as _bh
                _browser_scope_key_check = _bh.resolve_browser_scope_key(state, node_name=node_name)
                _existing_session = _bh.cached_browser_sessions.get(_browser_scope_key_check)
                _session_usable = _existing_session is not None and _bh.is_session_started(_existing_session)
                logger.debug(
                    f"[BrowserAutomation] URL strip check: scope={_browser_scope_key_check} "
                    f"cached={'yes' if _existing_session else 'no'} started={_session_usable}"
                )
                if _session_usable:
                    import re as _re_strip
                    _chat_url_pattern = _re_strip.compile(_strip_regex_src)
                    _stripped = _chat_url_pattern.sub(_strip_replacement, combined_task)
                    if _stripped != combined_task:
                        logger.info(
                            f"[BrowserAutomation] Stripped matching URL(s) from task to prevent "
                            f"duplicate tab (session reused, scope={_browser_scope_key_check})"
                        )
                        combined_task = _stripped
        except Exception as _strip_err:
            logger.debug(f"[BrowserAutomation] URL strip failed: {_strip_err}")

        # print("final_system_prompt:", final_system_prompt)
        # print("final_user_prompt:", final_user_prompt)
        logger.debug("combined_task:", combined_task)
        logger.info(
            f"[BA._auto] preflight_done node={node_name} "
            f"elapsed_ms={(_ba_auto_time.perf_counter()-_ba_auto_t0)*1000:.0f} "
            f"provider={provider} task_len={len(task_instructions or '')}"
        )
        if provider in ("browser-use", "crawl4ai"):
            # Check if we're in cloud mode (hybrid_cloud or full_cloud)
            # In cloud mode, mainwin is not required
            is_cloud_mode = run_environment_setting in ('hybrid_cloud', 'full_cloud')
            
            # Get mainwin from agent via state (only needed for local modes)
            mainwin = None
            agent_id = None  # Initialize agent_id for use in _run_browser_use
            
            # Try to get agent_id from state (works in both local and cloud mode)
            # P0 Fix: Prioritize attributes.agent_id and validate messages[0] type
            try:
                # First priority: attributes.agent_id (most reliable)
                agent_id = state.get("attributes", {}).get("agent_id")
                
                # Fallback: messages[0] if it's a string
                if not agent_id and state.get("messages"):
                    first_msg = state["messages"][0]
                    if isinstance(first_msg, str):
                        agent_id = first_msg
                    else:
                        logger.debug(
                            f"[BrowserAutomation] messages[0] is not a string (type: {type(first_msg).__name__}), "
                            f"cannot use as agent_id"
                        )
            except Exception as e:
                logger.warning(f"[BrowserAutomation] Failed to extract agent_id: {e}")
            
            if not is_cloud_mode:
                try:
                    from agent.agent_service import get_agent_by_id
                    if agent_id:
                        agent = get_agent_by_id(agent_id)
                        if agent and hasattr(agent, 'mainwin'):
                            mainwin = agent.mainwin
                except Exception as e:
                    err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNode brower-use")
                    logger.warning(err_msg)
                    send_skill_editor_log("warning", err_msg)

            # ── Fallback: AppContext singleton (2026-04-24 hotfix) ──
            # When the loop scaffolding (`update_loop_*_condition`) re-enters
            # the node on auto-resume, the propagated state has been observed
            # to carry only ``{attributes, result, tool_result}`` keys, often
            # without ``attributes.agent_id`` populated.  The agent-based
            # lookup above then returns ``None`` and the node aborts with
            # "mainwin not available".  AppContext.get_main_window() is the
            # process-wide singleton populated at startup; using it as a
            # last-resort fallback restores execution without changing the
            # primary lookup path.
            if not mainwin and not is_cloud_mode:
                try:
                    from app_context import AppContext
                    _ctx_mw = AppContext.get_main_window()
                    if _ctx_mw is not None:
                        mainwin = _ctx_mw
                        logger.warning(
                            f"[build_browser_automation_node] Recovered mainwin from "
                            f"AppContext singleton (agent_id={agent_id!r}, state_keys="
                            f"{sorted(state.keys()) if isinstance(state, dict) else '?'}"
                            f", attrs_keys="
                            f"{sorted((state.get('attributes') or {}).keys()) if isinstance(state, dict) else '?'})"
                        )
                except Exception as _ctx_err:
                    logger.debug(
                        f"[build_browser_automation_node] AppContext fallback failed: {_ctx_err}"
                    )

            if not mainwin and not is_cloud_mode:
                err_msg = "Cannot create browser_use LLM: mainwin not available. Please ensure agent is properly initialized."
                logger.error(f"[build_browser_automation_node] {err_msg}")
                send_skill_editor_log("error", f"[build_browser_automation_node] {err_msg}")
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
                        send_skill_editor_log("log", log_msg)
                except Exception as e:
                    logger.warning(f"[BROWSER_GUARDRAIL] Failed to start timer: {e}")
            
            logger.info(
                f"[BA._auto] dispatch node={node_name} "
                f"elapsed_ms={(_ba_auto_time.perf_counter()-_ba_auto_t0)*1000:.0f} "
                f"cloud={is_cloud_mode} hard_timeout={use_hard_timeout} "
                f"effective_timeout={effective_timeout} "
                f"has_monitors={bool(_event_monitor_configs)} agent_id={agent_id!r}"
            )
            info = _execute_browser_use_run(
                state=state,
                runtime=runtime,
                combined_task=combined_task,
                mainwin=mainwin,
                agent_id=agent_id,
                use_hard_timeout=use_hard_timeout,
                effective_timeout=effective_timeout,
                correlation_id=correlation_id,
            )
            return _finalize_automation_result(
                state=state,
                info=info,
                provider=provider,
                task_instructions=task_instructions,
                final_system_prompt=final_system_prompt,
                action=action,
                wait_for_done=wait_for_done,
            )

        # Fallback: record intent for other providers
        intents = state.setdefault("metadata", {}).setdefault("automation_intents", [])
        intents.append({"node": node_name, "provider": provider, "action": action, "params": params, "task": combined_task})
        info = {"recorded": True, "provider": provider, "action": action}
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
    send_skill_editor_log("log", log_msg)
    
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
            send_skill_editor_log("debug", log_msg)
            
        except Exception as e:
            err_msg = get_traceback(e, f"ErrorInTaskNode_{node_name}")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
        
        return state
    
    return node_builder(_task, node_name, skill_name, owner, bp_manager)


def _log_browser_use_result_summary(history: Any, *, skill_name: str, node_name: str) -> None:
    """Log compact per-step browser-use results so blank retry counters are diagnosable."""
    try:
        all_results = list(getattr(history, "all_results", []) or [])
    except Exception:
        all_results = []
    if not all_results:
        return

    lines = []
    for idx, result in enumerate(all_results, start=1):
        if result is None:
            lines.append(f"[{idx}] <none>")
            continue
        try:
            is_done = getattr(result, "is_done", None)
            success = getattr(result, "success", None)
            error = str(getattr(result, "error", "") or "").strip()
            extracted = str(getattr(result, "extracted_content", "") or "").strip().replace("\r", " ").replace("\n", " ")
            if len(extracted) > 180:
                extracted = extracted[:177] + "..."
            line = f"[{idx}] done={is_done} success={success}"
            if error:
                line += f" error={error}"
            if extracted:
                line += f" extracted={extracted}"
            lines.append(line)
        except Exception as exc:
            lines.append(f"[{idx}] <summary_failed> {exc}")
    logger.info(
        f"[BrowserAutomation] browser-use result summary for {skill_name}:{node_name}\n" + "\n".join(lines)
    )


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
    send_skill_editor_log("log", log_msg)
    
    # Get LLM config from node metadata or use defaults from Settings
    def _get_default_model():
        """Get default model from Settings using unified method"""
        try:
            from app_context import AppContext
            ctx = AppContext.get_instance()
            mainwin = ctx.get_main_window()
            if mainwin and hasattr(mainwin, 'config_manager'):
                # Use unified method to get default LLM config
                llm_config = mainwin.config_manager.llm_manager.get_default_llm_config()
                return llm_config['model_name']
            raise RuntimeError("MainWindow or config_manager not available")
        except Exception as e:
            logger.warning(f"[build_tool_picker_node] Failed to get default model from Settings: {e}")
            raise RuntimeError("Failed to get default model from Settings. Please configure a default LLM in Settings.")
    
    model_name = (config_metadata or {}).get('model') or _get_default_model()
    temperature = (config_metadata or {}).get('temperature', 0.0)
    
    def _tool_picker(state: dict, **kwargs):
        """Tool picker node implementation using LLM to select tools."""
        try:
            log_msg = f"🤖 Executing node LLM assisted tool picker node: {node_name}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

            # Step 1: Extract next_actions from previous LLM result
            logger.debug("[ToolPickerNode] Extracting next_actions from state")
            result = state.get('result', {})
            llm_result = result.get('llm_result', {})
            next_actions = llm_result.get('next_actions', [])
            logger.debug("[ToolPickerNode] found next_actions:", next_actions)

            if not next_actions:
                log_msg = f"[{node_name}] No next_actions found in state['result']['llm_result']"
                logger.warning(log_msg)
                send_skill_editor_log("warning", log_msg)
                state.setdefault('tool_calls', [])
                return state
            
            log_msg = f"[{node_name}] Processing {len(next_actions)} action(s)"
            logger.debug(log_msg)
            send_skill_editor_log("debug", log_msg)
            
            # Step 2: Get all available tool schemas from MCP
            try:
                from agent.mcp.server.tool_schemas import tool_schemas
                all_tools = tool_schemas or []
            except Exception as e:
                err_msg = get_traceback(e, f"ErrorLoadingToolSchemas_{node_name}")
                logger.error(err_msg)
                send_skill_editor_log("error", err_msg)
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
                send_skill_editor_log("debug", log_msg)
                
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
                send_skill_editor_log("debug", log_msg)
                
                if not filtered_tools:
                    log_msg = f"[{node_name}] No tools found for category={category}, sub_category={sub_category}"
                    logger.warning(log_msg)
                    send_skill_editor_log("warning", log_msg)
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
                    send_skill_editor_log("debug", log_msg)
                    
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
                    send_skill_editor_log("error", err_msg)
                    continue
            
            # Step 7: Store tool_calls in state
            state['tool_calls'] = tool_calls
            
            log_msg = f"[{node_name}] Generated {len(tool_calls)} tool call(s)"
            logger.info(log_msg)
            send_skill_editor_log("info", log_msg)
            
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
            send_skill_editor_log("error", err_msg)
            state.setdefault('tool_calls', [])
        
        return state
    
    return node_builder(_tool_picker, node_name, skill_name, owner, bp_manager)
