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


from typing import Any, Literal, cast, overload

from langchain_core.messages.base import BaseMessage, BaseMessageChunk


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

    # Clear browser session cache
    _cached_browser_sessions.clear()

    # Clear passive agent cache
    _cached_passive_agents.clear()

    # Stop and remove persistent worker threads
    try:
        from agent.ec_skills.llm_utils.llm_utils import (
            _persistent_worker_runners,
            _persistent_worker_runners_lock,
        )
        with _persistent_worker_runners_lock:
            for _name, _runner in list(_persistent_worker_runners.items()):
                try:
                    _runner.stop()
                except Exception:
                    pass
            _persistent_worker_runners.clear()
    except ImportError:
        pass

    logger.debug("[build_node] Module-level caches cleared")


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

    # Get inline prompt content
    inline_system_prompt = ((inputs.get("systemPrompt") or {}).get("content") or STANDARD_SYS_PROMPT)
    inline_user_prompt = ((inputs.get("prompt") or {}).get("content") or STANDARD_SYS_PROMPT)

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
                or nested_tool.get('tool_input')
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
            except Exception:
                pass

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
                _ti = _item.get('tool_input') or _item.get('next_tool_input') or {}
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
    
    logger.debug(f"[BrowserAutomation] browser={browser_type_setting}, driver={browser_driver_setting}, cdp_port={cdp_port_setting}")
    logger.debug(f"[BrowserAutomation] run_environment={run_environment_setting}, privacy_strategy={privacy_strategy_setting}, enable_judge={enable_judge_setting}")
    logger.debug(f"[BrowserAutomation] shop_name={shop_name}, downloads_path={downloads_path}")

    def _extract_runtime_invocation_input(state: dict | None) -> str:
        """Extract the live invocation payload for browser-use task grounding.

        Browser-use nodes do not consume graph state directly; they only see the
        composed task string. For resumed chat/service flows we must inject the
        current assignment/customer payload into that task string so the model
        does not fall back to examples or stale memory.
        """
        if not isinstance(state, dict):
            return ""

        candidates = []
        direct_input = state.get("input")
        if isinstance(direct_input, str) and direct_input.strip():
            candidates.append(direct_input.strip())

        messages = state.get("messages")
        if isinstance(messages, list) and len(messages) > 4:
            msg_payload = messages[4]
            if isinstance(msg_payload, str) and msg_payload.strip():
                candidates.append(msg_payload.strip())

        attrs = state.get("attributes", {}) if isinstance(state.get("attributes"), dict) else {}
        params = attrs.get("params", {}) if isinstance(attrs.get("params"), dict) else {}
        metadata = params.get("metadata", {}) if isinstance(params.get("metadata"), dict) else {}
        meta_params = metadata.get("params", {}) if isinstance(metadata.get("params"), dict) else {}

        content_obj = meta_params.get("content")
        if isinstance(content_obj, str) and content_obj.strip():
            candidates.append(content_obj.strip())
        elif isinstance(content_obj, dict):
            text_val = content_obj.get("text")
            if isinstance(text_val, str) and text_val.strip():
                candidates.append(text_val.strip())

        message = params.get("message")
        if isinstance(message, dict):
            parts = message.get("parts")
            if isinstance(parts, list) and parts:
                first = parts[0]
                if isinstance(first, dict):
                    text_val = first.get("text")
                    if isinstance(text_val, str) and text_val.strip():
                        candidates.append(text_val.strip())
        else:
            try:
                parts = getattr(message, "parts", None)
                if isinstance(parts, (list, tuple)) and parts:
                    text_val = getattr(parts[0], "text", None)
                    if isinstance(text_val, str) and text_val.strip():
                        candidates.append(text_val.strip())
            except Exception:
                pass

        for candidate in candidates:
            if candidate:
                return candidate
        return ""

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

    def _get_browser_profile_settings(profile_name: str) -> dict:
        """Load browser profile settings from backend configuration."""
        try:
            from gui.ipc.w2p_handlers.browser_use_handler import get_profile_by_name, get_default_profile
            
            if profile_name:
                profile = get_profile_by_name(profile_name)
            else:
                profile = get_default_profile()
            
            if profile:
                logger.debug(f"[BrowserAutomation] Loaded profile settings: {profile.get('name', 'unknown')}")
                return profile
        except Exception as e:
            logger.warning(f"[BrowserAutomation] Failed to load browser profile settings: {e}")
        
        return {}

    def _is_session_started(session) -> bool:
        """Check BrowserSession is fully started (CDP root client ready).

        `session_manager is not None` can become true before CDP root client
        is initialized, which leads to runtime errors like
        "Root CDP client not initialized" during watchdog events.
        """
        if session is None:
            return False

        if getattr(session, "_ecan_fast_attach_ready", False):
            return True

        # Prefer strong signal: root CDP client initialized.
        root_client = getattr(session, "_cdp_client_root", None)
        if root_client is None:
            root_client = getattr(session, "cdp_client_root", None)
        if root_client is not None:
            return True

        # Defensive fallback for older/newer browser_use internals.
        return getattr(session, "session_manager", None) is not None and getattr(session, "event_bus", None) is not None

    def _is_session_alive(session) -> bool:
        """Check session is started AND its event bus is still operational."""
        if not _is_session_started(session):
            logger.debug(f"[BrowserAutomation] _is_session_alive: session_manager is None")
            return False
        try:
            eb = getattr(session, 'event_bus', None)
            if eb is None:
                logger.debug(f"[BrowserAutomation] _is_session_alive: event_bus is None")
                return False
            eq = getattr(eb, 'event_queue', None)
            eq_shutdown = getattr(eq, '_is_shutdown', False) if eq is not None else 'no_queue'
            eb_running = getattr(eb, '_is_running', False)
            rl_task = getattr(eb, '_runloop_task', None)
            rl_done = rl_task.done() if rl_task is not None else 'no_task'
            logger.debug(
                f"[BrowserAutomation] _is_session_alive: "
                f"eb._is_running={eb_running}, eq._is_shutdown={eq_shutdown}, "
                f"runloop_task.done={rl_done}, session_id={session.id}"
            )
            if eq is not None and getattr(eq, '_is_shutdown', False):
                return False
            if not eb_running:
                return False
            return True
        except Exception as e:
            logger.debug(f"[BrowserAutomation] _is_session_alive: exception: {e}")
            return False


    # Fix E-F1: Cache browser_session across steps so we don't create a new one
    # each iteration.  BrowserManager.acquire_browser marks the browser IN_USE,
    # so subsequent find_available_browser calls miss it and create_browser builds
    # a brand-new BrowserSession (resetting agent_focus_target_id to the first tab).
    _cached_browser_sessions: dict[str, Any] = {}
    _last_known_focus_target_ids: dict[str, str] = {}  # survives session recreation per scope
    _browser_start_locks: dict[int, Any] = {}  # thread locks keyed by CDP port for cross-worker startup serialization
    _MAX_BROWSER_CACHE_SIZE = 10  # Limit cache size to prevent unbounded memory growth

    # Cache browser-use sub-agents across loop iterations (one per scope/task).
    # The browser-use Agent is heavyweight — it owns MessageManager, history, LLM
    # client references, etc.  Re-creating it on every pend_event cycle wastes ~860 MB
    # of allocations per cycle and adds unnecessary init overhead.
    # Keyed by the same _browser_scope_key used for _cached_browser_sessions.
    _cached_bu_agents: dict[str, Any] = {}

    def _reset_bu_agent_for_next_round(agent: Any, mode: str, task: str) -> None:
        """Reset a cached browser-use sub-agent for re-use in the next loop round.

        Args:
            agent: The browser-use Agent instance to reset.
            mode:  loop_history_mode string — "clear", "trim:<N>", or "accumulate".
            task:  The new task string for this round (updates agent.task).
        """
        try:
            # Always update the task text so the agent knows what to do this round.
            # Must update BOTH agent.task (cosmetic) AND agent.message_manager.task —
            # the LLM reads message_manager.task via AgentMessagePrompt(task=self.task)
            # on every step. Without this, a cached/reused agent keeps feeding the LLM
            # the very first round's task forever, so runtime injections (triggering
            # event, actionable_items, protocol override) from later rounds never reach it.
            if hasattr(agent, 'task'):
                agent.task = task
            _mm_for_task = getattr(agent, 'message_manager', None)
            if _mm_for_task is not None and hasattr(_mm_for_task, 'task'):
                _mm_for_task.task = task

            # Restore full AgentOutput if a previous run clobbered it.
            # browser-use sets AgentOutput = DoneAgentOutput (done-only) when
            # max_steps or max_failures is reached.  Since we cache and reuse
            # the agent, subsequent rounds would only see the "done" tool and
            # lose all custom actions (feige_*, bu_send_chat, etc.).
            _full_output = getattr(agent, '_ecan_full_AgentOutput', None)
            if _full_output is not None and hasattr(agent, 'AgentOutput'):
                _was_clobbered = agent.AgentOutput is not _full_output
                agent.AgentOutput = _full_output
                if _was_clobbered:
                    logger.info(
                        "[BrowserAutomation] AgentOutput was clobbered (DoneAgentOutput) — restored full AgentOutput"
                    )

            # Reset LoopDetector state.
            # The loop detector tracks action hashes and page fingerprints across steps.
            # Without resetting, the `done()` action hash accumulates across rounds,
            # triggering false loop-detection nudges that confuse the LLM and may cause
            # it to abandon its normal workflow (including skipping custom tool calls).
            _ld = getattr(getattr(agent, 'state', None), 'loop_detector', None)
            if _ld is not None:
                _prev_rep = getattr(_ld, 'max_repetition_count', 0)
                if hasattr(_ld, 'recent_action_hashes'):
                    _ld.recent_action_hashes.clear()
                if hasattr(_ld, 'recent_page_fingerprints'):
                    _ld.recent_page_fingerprints.clear()
                if hasattr(_ld, 'max_repetition_count'):
                    _ld.max_repetition_count = 0
                if hasattr(_ld, 'most_repeated_hash'):
                    _ld.most_repeated_hash = None
                if hasattr(_ld, 'consecutive_stagnant_pages'):
                    _ld.consecutive_stagnant_pages = 0
                if _prev_rep >= 3:
                    logger.info(
                        f"[BrowserAutomation] Reset LoopDetector "
                        f"(was repetition={_prev_rep})"
                    )

            # Diagnostic: verify that the restored AgentOutput has custom actions.
            # If it only has 'done', something went wrong with the save/restore.
            try:
                _ao = getattr(agent, 'AgentOutput', None)
                if _ao is not None:
                    # The action field's type annotation lists available actions as optional fields
                    _action_field = _ao.model_fields.get('action')
                    if _action_field and hasattr(_action_field.annotation, 'model_fields'):
                        _action_names = list(_action_field.annotation.model_fields.keys())
                        _n_actions = len(_action_names)
                        if _n_actions <= 1:
                            logger.warning(
                                f"[BrowserAutomation] AgentOutput has only {_n_actions} actions "
                                f"({_action_names}) — custom tools may be missing! "
                                f"_ecan_full_AgentOutput={'set' if _full_output is not None else 'NOT set'}"
                            )
                        else:
                            logger.debug(
                                f"[BrowserAutomation] AgentOutput OK: {_n_actions} actions available"
                            )
            except Exception as _ao_check_err:
                logger.debug(f"[BrowserAutomation] AgentOutput check failed: {_ao_check_err}")

            # Always reset AgentState fields that would cause run() to exit immediately
            # or behave incorrectly on re-entry:
            #   - n_steps: kept as-is by default but must not exceed max_steps; resetting
            #     to 1 gives each round a full fresh step budget.
            #   - consecutive_failures: must be 0 or run() may abort before the first step.
            #   - stopped: True would cause the main loop to break immediately.
            #   - history.is_done(): True would skip the loop entirely on some paths.
            st = getattr(agent, 'state', None)
            if st is not None:
                try:
                    st.n_steps = 1
                except Exception:
                    pass
                try:
                    st.consecutive_failures = 0
                except Exception:
                    pass
                try:
                    st.stopped = False
                except Exception:
                    pass

            if mode == "accumulate":
                # Keep message history — nothing more to do.
                logger.debug("[BrowserAutomation] loop_history_mode=accumulate: preserving full history")
                return

            # For "clear" and "trim" reset the message_manager state
            # (context_messages, agent_history_items) so the LLM doesn't see stale DOM.
            mm = getattr(agent, 'message_manager', None)
            if mm:
                mm_state = getattr(mm, 'state', None)
                if mm_state:
                    # Clear short-term context messages (current step DOM state, tool results)
                    if hasattr(mm_state, 'context_messages'):
                        mm_state.context_messages.clear()

                    if mode == "clear":
                        _had_history = False
                        _had_memory = False
                        if hasattr(mm_state, 'agent_history_items'):
                            _had_history = len(mm_state.agent_history_items) > 0
                            mm_state.agent_history_items.clear()
                        # Also clear compacted_memory — this is browser-use's
                        # cross-step summary (contains "Memory: ..." entries).
                        # Without clearing it, stale dispatch tracking like
                        # "sc is in pending_dispatches" persists and prevents
                        # the LLM from re-dispatching customers with new messages.
                        if hasattr(mm_state, 'compacted_memory'):
                            _had_memory = mm_state.compacted_memory is not None
                            mm_state.compacted_memory = None
                        logger.info(
                            f"[BrowserAutomation] loop_history_mode=clear: wiped message_manager "
                            f"(had_history={_had_history}, had_compacted_memory={_had_memory})"
                        )

                    elif mode.startswith("trim:"):
                        try:
                            keep_n = int(mode.split(":", 1)[1])
                        except (ValueError, IndexError):
                            keep_n = 10
                        if hasattr(mm_state, 'agent_history_items'):
                            items = mm_state.agent_history_items
                            if len(items) > keep_n:
                                del items[:-keep_n]
                        logger.debug(f"[BrowserAutomation] loop_history_mode={mode}: trimmed to last {keep_n} history items")

            # Reset AgentHistoryList (used for final_result / is_done checks).
            # Without this, history.is_done() returns True from the previous round and
            # run() may exit before executing a single step.
            hist = getattr(agent, 'history', None)
            if hist is not None:
                if mode == "clear":
                    if hasattr(hist, 'history'):
                        hist.history.clear()
                elif mode.startswith("trim:"):
                    try:
                        keep_n = int(mode.split(":", 1)[1])
                    except (ValueError, IndexError):
                        keep_n = 10
                    if hasattr(hist, 'history') and len(hist.history) > keep_n:
                        del hist.history[:-keep_n]

        except Exception as _reset_err:
            logger.warning(f"[BrowserAutomation] _reset_bu_agent_for_next_round error (non-fatal): {_reset_err}")

    def _resolve_browser_scope_key(state: dict | None = None) -> str:
        """Resolve a stable browser scope key from workflow state.

        Session-scoped chat tasks must not share browser cache/state with other
        customer sessions. Prefer chat/session identity when present.
        """
        try:
            state = state or {}
            attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
            params = attrs.get("params", {}) if isinstance(attrs, dict) else {}
            meta_params = {}
            if isinstance(params.get("metadata"), dict):
                meta_params = params.get("metadata", {}).get("params", {}) or {}

            candidates = [
                attrs.get("chat_id"),
                params.get("chatId"),
                meta_params.get("chatId"),
            ]
            if isinstance(state, dict):
                messages = state.get("messages")
                if isinstance(messages, list) and len(messages) > 1:
                    candidates.append(messages[1])

            for value in candidates:
                if value:
                    return f"chat:{value}"
        except Exception:
            pass
        return f"node:{node_name}"

    def _extract_assignment_scope(runtime_input: str) -> dict:
        """Best-effort parse of the current assignment payload."""
        if not isinstance(runtime_input, str) or not runtime_input.strip():
            return {}
        try:
            payload = json.loads(runtime_input)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {}

    def _patch_browser_session_lifecycle_debug(session, source: str) -> None:
        """Attach one-time debug hooks to the live BrowserSession/CDP client."""
        try:
            if session is None:
                return

            _debug_scope_key = getattr(session, "_ecan_browser_scope_key", "")
            _cached_for_scope = _cached_browser_sessions.get(_debug_scope_key) if _debug_scope_key else None

            logger.info(
                f"[BrowserAutomation][LifecycleDebug] Patch attempt source={source} "
                f"session_obj={id(session)} cached_obj={id(_cached_for_scope) if _cached_for_scope else 'none'} "
                f"same_as_cached={session is _cached_for_scope} scope={_debug_scope_key or 'unscoped'}"
            )

            if not getattr(session, "_ecan_lifecycle_debug_patched", False):
                _orig_reset = getattr(session, "reset", None)
                if _orig_reset:
                    async def _debug_reset(*a, **kw):
                        logger.warning(
                            "[BrowserAutomation][LifecycleDebug] BrowserSession.reset() called.\n"
                            + "".join(traceback.format_stack(limit=20))
                        )
                        return await _orig_reset(*a, **kw)
                    session.reset = _debug_reset

                _orig_reconnect = getattr(session, "reconnect", None)
                if _orig_reconnect:
                    async def _debug_reconnect(*a, **kw):
                        logger.warning(
                            "[BrowserAutomation][LifecycleDebug] BrowserSession.reconnect() called.\n"
                            + "".join(traceback.format_stack(limit=20))
                        )
                        return await _orig_reconnect(*a, **kw)
                    session.reconnect = _debug_reconnect

                _orig_auto_reconnect = getattr(session, "_auto_reconnect", None)
                if _orig_auto_reconnect:
                    async def _debug_auto_reconnect(*a, **kw):
                        logger.warning(
                            "[BrowserAutomation][LifecycleDebug] BrowserSession._auto_reconnect() called.\n"
                            + "".join(traceback.format_stack(limit=20))
                        )
                        return await _orig_auto_reconnect(*a, **kw)
                    session._auto_reconnect = _debug_auto_reconnect

                setattr(session, "_ecan_lifecycle_debug_patched", True)
                logger.info("[BrowserAutomation] Patched browser session lifecycle debug hooks")

            _cdp_root = getattr(session, "_cdp_client_root", None)
            if _cdp_root is not None:
                logger.info(
                    f"[BrowserAutomation][LifecycleDebug] CDP root present source={source} "
                    f"cdp_obj={id(_cdp_root)} patched={getattr(_cdp_root, '_ecan_debug_patched', False)}"
                )
            else:
                logger.info(f"[BrowserAutomation][LifecycleDebug] No CDP root yet source={source}")

            if _cdp_root and hasattr(_cdp_root, "stop") and not getattr(_cdp_root, "_ecan_debug_patched", False):
                _orig_cdp_stop = _cdp_root.stop

                async def _debug_cdp_stop(*a, **kw):
                    logger.warning(
                        "[BrowserAutomation][LifecycleDebug] CDPClient.stop() called.\n"
                        + "".join(traceback.format_stack(limit=20))
                    )
                    return await _orig_cdp_stop(*a, **kw)

                _cdp_root.stop = _debug_cdp_stop
                setattr(_cdp_root, "_ecan_debug_patched", True)
                logger.info("[BrowserAutomation] Patched CDPClient.stop lifecycle debug hook")
        except Exception as exc:
            logger.warning(f"[BrowserAutomation] Failed to patch browser lifecycle debug hooks: {exc}")

    async def _get_or_create_browser_session(mainwin, state: dict | None = None, calling_agent_id: str | None = None):
        """Get or create browser session based on node editor settings."""
        nonlocal _cached_browser_sessions, _last_known_focus_target_ids, _browser_start_locks
        import asyncio
        import threading
        from gui.manager.browser_manager import BrowserManager, BrowserType, BrowserStatus

        browser_scope_key = _resolve_browser_scope_key(state)
        isolate_scope = browser_scope_key.startswith("chat:")
        _cached_browser_session = _cached_browser_sessions.get(browser_scope_key)
        _last_known_focus_target_id = _last_known_focus_target_ids.get(browser_scope_key)

        # Return cached session if still valid AND event bus alive
        if _cached_browser_session is not None and _is_session_alive(_cached_browser_session):
            logger.debug(f"[BrowserAutomation] Reusing cached browser session: {_cached_browser_session.id}")
            return _cached_browser_session

        # Invalidate stale cache - but preserve the focus target
        if _cached_browser_session is not None:
            old_focus = getattr(_cached_browser_session, 'agent_focus_target_id', None)
            if old_focus:
                _last_known_focus_target_id = old_focus
                _last_known_focus_target_ids[browser_scope_key] = old_focus
                logger.info(f"[BrowserAutomation] Saved focus target from dying session: ...{old_focus[-4:]}")
            old_sid = id(_cached_browser_session)
            old_pa = _cached_passive_agents.get(old_sid)
            if old_pa and hasattr(old_pa, '_last_focus_target_id') and old_pa._last_focus_target_id:
                _last_known_focus_target_id = old_pa._last_focus_target_id
                _last_known_focus_target_ids[browser_scope_key] = old_pa._last_focus_target_id
                logger.info(f"[BrowserAutomation] Saved focus target from PassiveAgent: ...{old_pa._last_focus_target_id[-4:]}")
            logger.info(f"[BrowserAutomation] Cached session {_cached_browser_session.id} is stale (event bus dead), creating new one")
            _cached_passive_agents.pop(old_sid, None)
            _cached_browser_sessions.pop(browser_scope_key, None)

        profile_settings = _get_browser_profile_settings(node_profile)
        if profile_settings:
            log_msg = f"[BrowserAutomation] Using profile: {profile_settings.get('name', node_profile)}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)

        log_msg = f"[BrowserAutomation] Getting browser session: browser={browser_type_setting}, driver={browser_driver_setting}, cdp_port_config={cdp_port_setting}"
        logger.debug(log_msg)
        send_skill_editor_log("log", log_msg)
        if not hasattr(mainwin, 'browser_manager') or mainwin.browser_manager is None:
            # Read browser pool config from general settings if available
            _bm_slots = None
            _bm_max_agents = 0
            try:
                _gs = getattr(getattr(mainwin, 'config_manager', None), 'general_settings', None)
                if _gs:
                    _bm_slots = _gs.browser_slots or None
                    _bm_max_agents = _gs.browser_max_agents_per_instance or 0
            except Exception:
                pass
            mainwin.browser_manager = BrowserManager(
                default_webdriver_path=mainwin.getWebDriverPath(),
                slots=_bm_slots,
                max_agents_per_browser=_bm_max_agents,
            )

        browser_manager: BrowserManager = mainwin.browser_manager

        browser_type_map = {
            'new chromium': BrowserType.CHROME,
            'existing chrome': BrowserType.CHROME,
            'ads power': BrowserType.ADSPOWER,
            'adspower': BrowserType.ADSPOWER,
            'ziniao': BrowserType.CHROME,
            'multi-login': BrowserType.CHROME,
        }
        browser_type = browser_type_map.get(browser_type_setting, BrowserType.CHROME)

        # Runtime browser-slot resolution: task state (assigned by scheduler
        # or auto-assigned by BrowserManager) takes priority over skill config.
        _state_cdp_port = ""
        _state_browser_profile = ""
        _state_slot_id = ""
        try:
            _slot_state = state if isinstance(state, dict) else {}
            _slot_attrs = _slot_state.get("attributes", {}) if isinstance(_slot_state, dict) else {}
            _slot_params = _slot_attrs.get("params", {}) if isinstance(_slot_attrs, dict) else {}
            # Check state root, then attributes, then params for cdp_port
            _state_cdp_port = str(
                _slot_state.get("cdp_port")
                or _slot_attrs.get("cdp_port")
                or _slot_params.get("cdp_port")
                or ""
            ).strip()
            _state_browser_profile = str(
                _slot_state.get("browser_profile")
                or _slot_attrs.get("browser_profile")
                or _slot_params.get("browser_profile")
                or ""
            ).strip()
            _state_slot_id = str(
                _slot_state.get("browser_slot_id")
                or _slot_attrs.get("browser_slot_id")
                or _slot_params.get("browser_slot_id")
                or ""
            ).strip()
            if _state_cdp_port or _state_slot_id:
                logger.info(
                    f"[BrowserAutomation] Runtime browser slot from state: "
                    f"cdp_port={_state_cdp_port or '(auto)'}, "
                    f"slot_id={_state_slot_id or '(none)'}, "
                    f"profile={_state_browser_profile or '(default)'}"
                )
        except Exception as _slot_err:
            logger.debug(f"[BrowserAutomation] Browser slot resolution from state failed: {_slot_err}")

        # If we have a slot_id but no cdp_port, resolve port from the slot
        if _state_slot_id and not _state_cdp_port:
            try:
                _slot_obj = browser_manager.get_slot(_state_slot_id)
                if _slot_obj:
                    _state_cdp_port = str(_slot_obj.cdp_port)
                    if not _state_browser_profile and _slot_obj.profile:
                        _state_browser_profile = _slot_obj.profile
                    logger.info(f"[BrowserAutomation] Resolved slot {_state_slot_id} → cdp_port={_state_cdp_port}")
            except Exception:
                pass

        # Priority: runtime slot > skill-editor config > default 9228
        # Special values: "auto" or "0" → cdp_port=0, which tells
        # BrowserManager to auto-select from its port pool.
        _cdp_source = "default"
        if _state_cdp_port:
            _cdp_source = "state"
            if _state_cdp_port.lower() == "auto" or _state_cdp_port == "0":
                cdp_port = 0
            elif _state_cdp_port.isdigit():
                cdp_port = int(_state_cdp_port)
            else:
                cdp_port = 9228
        elif cdp_port_setting:
            _cdp_source = "config"
            if cdp_port_setting.lower() == "auto" or cdp_port_setting == "0":
                cdp_port = 0
            elif cdp_port_setting.isdigit():
                cdp_port = int(cdp_port_setting)
            else:
                cdp_port = 9228
        else:
            cdp_port = 9228
        logger.info(
            f"[BrowserAutomation] Resolved cdp_port={'auto' if cdp_port == 0 else cdp_port} "
            f"(from={_cdp_source})"
        )

        _agent_id_base = calling_agent_id or getattr(mainwin, 'current_agent_id', 'default_agent') or 'default_agent'
        _node_agent_id = (
            f"{_agent_id_base}:{node_name}:{browser_scope_key}"
            if isolate_scope else f"{_agent_id_base}:{node_name}"
        )
        auto_browser = browser_manager.acquire_browser(
            agent_id=_node_agent_id,
            task=(f"browser_automation_{node_name}:{browser_scope_key}" if isolate_scope else f"browser_automation_{node_name}"),
            browser_type=browser_type,
            cdp_port=cdp_port,
            webdriver_path=mainwin.getWebDriverPath(),
            downloads_path=downloads_path,
            profile=node_profile or _state_browser_profile,
        )

        if auto_browser and auto_browser.status != BrowserStatus.ERROR:
            # When cdp_port was auto-assigned (0), update to the actual port
            # so downstream locks and logging use the real value.
            if cdp_port == 0 and auto_browser.cdp_port:
                cdp_port = auto_browser.cdp_port
                logger.info(f"[BrowserAutomation] Auto-assigned browser on cdp_port={cdp_port}")

            if auto_browser.webdriver:
                mainwin.setWebDriver(auto_browser.webdriver)

            if browser_driver_setting == 'native' and auto_browser.browser_session:
                log_msg = f"[BrowserAutomation] Starting browser session: {auto_browser.browser_session.id}"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)

                # Each agent gets its own independent CDP connection via
                # browser_session.start().  No donor/shared-session pattern — sharing
                # session_manager/event_bus causes tab contamination when multiple
                # agents run concurrently on the same Chrome.
                fast_attach_ready = False
                if isolate_scope and browser_type_setting == 'existing chrome':
                    try:
                        sm = getattr(auto_browser.browser_session, "session_manager", None)
                        eb = getattr(auto_browser.browser_session, "event_bus", None)
                        targets = sm.get_all_targets() if sm and hasattr(sm, "get_all_targets") else {}
                        page_targets = [
                            tid for tid, t in (targets or {}).items()
                            if getattr(t, "target_type", "") in ("page", "tab")
                        ]
                        if eb is not None and page_targets:
                            fast_attach_ready = True
                            setattr(auto_browser.browser_session, "_ecan_fast_attach_ready", True)
                            logger.info(
                                f"[BrowserAutomation] Fast-attach ready (own session already started) "
                                f"{auto_browser.browser_session.id}: page_targets={len(page_targets)} "
                                f"scope={browser_scope_key}"
                            )
                    except Exception as _fast_attach_exc:
                        logger.warning(
                            f"[BrowserAutomation] Fast-attach probe failed for session "
                            f"{auto_browser.browser_session.id}: {_fast_attach_exc}"
                        )

                if not _is_session_started(auto_browser.browser_session) and not fast_attach_ready:
                    start_lock = _browser_start_locks.get(cdp_port)
                    if start_lock is None:
                        start_lock = threading.Lock()
                        _browser_start_locks[cdp_port] = start_lock

                    logger.info(
                        f"[BrowserAutomation] Waiting for startup lock on cdp_port={cdp_port} "
                        f"scope={browser_scope_key} session={auto_browser.browser_session.id}"
                    )
                    _lock_acquired = await asyncio.to_thread(lambda: start_lock.acquire(timeout=60))
                    if not _lock_acquired:
                        logger.error(
                            f"[BrowserAutomation] Startup lock timed out after 60s on cdp_port={cdp_port} "
                            f"scope={browser_scope_key}; cannot start independent session"
                        )
                    else:
                        try:
                            if not _is_session_started(auto_browser.browser_session):
                                logger.info(
                                    f"[BrowserAutomation] Acquired startup lock on cdp_port={cdp_port}; "
                                    f"starting session {auto_browser.browser_session.id} scope={browser_scope_key}"
                                )
                                _start_task = asyncio.create_task(auto_browser.browser_session.start())
                                try:
                                    await asyncio.wait_for(asyncio.shield(_start_task), timeout=30)
                                except asyncio.TimeoutError:
                                    logger.warning(
                                        f"[BrowserAutomation] browser_session.start() timed out after 30s "
                                        f"for {auto_browser.browser_session.id} scope={browser_scope_key}; "
                                        f"will retry once"
                                    )
                                    # Retry once — transient CDP handshake failures can occur
                                    # when multiple sessions connect in quick succession.
                                    try:
                                        _start_task2 = asyncio.create_task(auto_browser.browser_session.start())
                                        await asyncio.wait_for(asyncio.shield(_start_task2), timeout=30)
                                        logger.info(
                                            f"[BrowserAutomation] Retry start() succeeded for "
                                            f"{auto_browser.browser_session.id}"
                                        )
                                    except (asyncio.TimeoutError, Exception) as _retry_err:
                                        logger.error(
                                            f"[BrowserAutomation] Retry start() also failed for "
                                            f"{auto_browser.browser_session.id}: {_retry_err}"
                                        )
                            else:
                                logger.info(
                                    f"[BrowserAutomation] Session already started after waiting for lock: "
                                    f"{auto_browser.browser_session.id}"
                                )
                        finally:
                            try:
                                start_lock.release()
                            except Exception:
                                pass
                elif fast_attach_ready:
                    logger.info(
                        f"[BrowserAutomation] Skipped browser_session.start() (already started): "
                        f"{auto_browser.browser_session.id} scope={browser_scope_key}"
                    )
                log_msg = f"[BrowserAutomation] Browser session started!"
                logger.info(log_msg)
                send_skill_editor_log("log", log_msg)
                try:
                    setattr(auto_browser.browser_session, "_ecan_browser_scope_key", browser_scope_key)
                except Exception:
                    pass

                if _last_known_focus_target_id:
                    try:
                        from browser_use.browser.events import SwitchTabEvent
                        cur_focus = auto_browser.browser_session.agent_focus_target_id
                        if cur_focus != _last_known_focus_target_id:
                            await auto_browser.browser_session.event_bus.dispatch(
                                SwitchTabEvent(target_id=_last_known_focus_target_id)
                            )
                            logger.info(
                                f"[BrowserAutomation] Restored focus from ...{cur_focus[-4:] if cur_focus else 'None'} "
                                f"to ...{_last_known_focus_target_id[-4:]} after session recreation"
                            )
                        else:
                            logger.debug(f"[BrowserAutomation] Focus already on correct target: ...{cur_focus[-4:]}")
                    except Exception as e:
                        logger.warning(f"[BrowserAutomation] Failed to restore focus after session recreation: {e}")

                # Evict oldest entries if cache exceeds max size
                if len(_cached_browser_sessions) >= _MAX_BROWSER_CACHE_SIZE:
                    evicted = 0
                    for _key in list(_cached_browser_sessions.keys()):
                        if _key == browser_scope_key:
                            continue
                        # Only evict entries for non-chat scopes (chat sessions should be stable)
                        if not _key.startswith("chat:"):
                            _old_session = _cached_browser_sessions.pop(_key, None)
                            _last_known_focus_target_ids.pop(_key, None)
                            if _old_session is not None:
                                _cached_passive_agents.pop(id(_old_session), None)
                            evicted += 1
                            if evicted >= 2:  # Remove up to 2 entries per insertion
                                break
                _cached_browser_sessions[browser_scope_key] = auto_browser.browser_session
                return auto_browser.browser_session

            return auto_browser
        else:
            error_msg = auto_browser.last_error if auto_browser else "Unknown error"
            logger.error(f"[BrowserAutomation] Failed to acquire browser: {error_msg}")
            return None

    async def _run_browser_use(task: str, mainwin, state: dict | None = None, calling_agent_id: str | None = None) -> dict:
        nonlocal _last_known_focus_target_ids
        try:
            import asyncio
            from browser_use import Agent as BUAgent
            from browser_use.browser.profile import BrowserProfile
            from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
            # from browser_use.browser.context import BUBrowserContext as BUBrowserContext
            
            # Patch navigation timeout to reduce "Page readiness timeout" warnings
            # browser_use hardcodes 4s cross-domain / 2s same-domain, which is too short for many sites
            log_msg = f"🤖 Executing node Browser Automation node: {node_name}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

            # ── Runtime Mustache Template Resolution ──
            # Resolve {{llm_result}}, {{browser_research}}, {{browser_executor}} etc. in task
            # This MUST happen at runtime (not build time) because state contains the actual values
            if state and "{{" in task:
                try:
                    _resolved_task = _resolve_mustache_template(task, state, mainwin)
                    if _resolved_task != task:
                        logger.info(
                            f"[BrowserAutomation] ✅ Resolved mustache templates in task "
                            f"(node={node_name}, original_len={len(task)}, resolved_len={len(_resolved_task)})"
                        )
                        send_skill_editor_log(
                            "log",
                            f"[BrowserAutomation] Resolved mustache templates in task "
                            f"(len: {len(task)} → {len(_resolved_task)})"
                        )
                        # Log preview of resolved content (first 500 chars)
                        preview = _resolved_task[:500] + "..." if len(_resolved_task) > 500 else _resolved_task
                        logger.debug(f"[BrowserAutomation] Resolved task preview:\n{preview}")
                        task = _resolved_task
                    else:
                        logger.warning(
                            f"[BrowserAutomation] ⚠️ Task still contains unresolved mustache templates "
                            f"(node={node_name}). Check that upstream nodes have executed and state contains the expected data."
                        )
                        send_skill_editor_log(
                            "warning",
                            f"[BrowserAutomation] Unresolved mustache templates in task for node={node_name}"
                        )
                except Exception as _mustache_err:
                    logger.warning(
                        f"[BrowserAutomation] Failed to resolve mustache templates: {_mustache_err}"
                    )

            runtime_input = _extract_runtime_invocation_input(state)
            _runtime_had_response_text = False
            if runtime_input:
                task = (
                    f"{task}\n\n"
                    f"## Current Invocation Input\n"
                    f"{runtime_input}"
                )
                logger.info(
                    f"[BrowserAutomation] Injected runtime invocation input into task "
                    f"(node={node_name}, skill={skill_name}, len={len(runtime_input)})"
                )
                send_skill_editor_log(
                    "log",
                    f"[BrowserAutomation] Injected runtime input into task (len={len(runtime_input)})"
                )
                # Track if this input contains a chat_message response so we
                # can clear it after the LLM processes it (preventing duplicates)
                try:
                    _ri_parsed = json.loads(runtime_input)
                    if isinstance(_ri_parsed, dict) and _ri_parsed.get("response_text"):
                        _runtime_had_response_text = True
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

            # ── Inject triggering event context ──
            # When this browser_automation node was resumed by pend_event after
            # an event (browser_event, chat_message, etc.), expose the event
            # metadata so the LLM knows WHY this invocation was triggered.
            _override_block = ""  # prepended to task when actionable_items is non-empty
            try:
                _event_json = ""
                _evt = None
                _evt_type = ""
                _evt_ctx = {}
                _evt_label = ""
                if isinstance(state, dict):
                    _pr = state.get("prompt_refs")
                    if isinstance(_pr, dict):
                        _event_json = _pr.get("events", "")
                if _event_json and isinstance(_event_json, str) and _event_json.strip():
                    _evt = json.loads(_event_json)
                    _evt_type = _evt.get("event_type", "")
                    _evt_ctx = _evt.get("context", {}) if isinstance(_evt.get("context"), dict) else {}
                # Fallback: if prompt_refs.events is empty, try to get event
                # info from state["browser_event"] or state["attributes"]["browser_event"]
                # (set by resume.py / pend_event node).
                if not _evt_type and isinstance(state, dict):
                    _be_fallback = (
                        state.get("browser_event")
                        or (state.get("attributes") or {}).get("browser_event")
                    )
                    if isinstance(_be_fallback, dict) and _be_fallback.get("type"):
                        _evt_type = _be_fallback.get("type", "")
                        _evt_ctx = {}
                        _evt = _be_fallback
                        logger.info(
                            f"[BrowserAutomation] event injection fallback: "
                            f"prompt_refs.events was empty, using state browser_event "
                            f"(type={_evt_type}, sub_type={_be_fallback.get('sub_type', '')})"
                        )
                if _evt_type:
                    # sub_type/label may be at top-level OR inside context
                    _evt_label = (
                        _evt_ctx.get("sub_type") or _evt_ctx.get("label")
                        or (_evt.get("sub_type") if _evt else "")
                        or (_evt.get("label") if _evt else "")
                        or ""
                    )
                    _evt_lines = [
                        "## Triggering Event",
                        f"This invocation was resumed by a **{_evt_type}** event.",
                    ]
                    if _evt_label:
                        _evt_lines.append(f"Event label: **{_evt_label}**")
                    if _evt_type == "browser_event":
                        _new_msg_hint = (
                            "The DOM monitor detected a change in the watched region"
                            + (f" (label: {_evt_label})" if _evt_label else "")
                            + ". A new item or state change has occurred.\n\n"
                            "**CRITICAL RULES FOR THIS INVOCATION:**\n"
                            "1. Your memory from previous rounds has been WIPED. You have NO record of any prior dispatches.\n"
                            "2. Do NOT infer dispatch status from the chat DOM. Previous agent replies visible in the chat thread are for OLDER messages, not the current one.\n"
                            "3. If the snapshot below shows a customer with a message that looks like a question, you MUST dispatch it — even if you see prior agent replies in the DOM.\n"
                            "4. The ONLY way a message counts as \"already dispatched\" is if YOU called bu_send_chat for that EXACT message text in THIS round. Seeing prior replies in the chat is NOT evidence of dispatch."
                        )
                        # Inject raw event body items so the LLM has the current
                        # snapshot without needing to call a list tool.
                        try:
                            _evt_items = None
                            # Path 1: context.params.body (legacy)
                            _evt_body = _evt_ctx.get("params", {})
                            if isinstance(_evt_body, dict):
                                _evt_body_str = _evt_body.get("body", "")
                                if isinstance(_evt_body_str, str) and _evt_body_str:
                                    _evt_body_parsed = json.loads(_evt_body_str)
                                    _evt_items = _evt_body_parsed.get("items", [])
                            # Path 2: state["attributes"]["browser_event"]["body"]["items"]
                            # (resume.py stores it at attributes.browser_event)
                            if not _evt_items and isinstance(state, dict):
                                _be_data = (
                                    state.get("browser_event")  # top-level (resume_payload)
                                    or (state.get("attributes") or {}).get("browser_event")  # state_patch path
                                )
                                if isinstance(_be_data, dict):
                                    _be_body = _be_data.get("body", {})
                                    if isinstance(_be_body, dict):
                                        _evt_items = _be_body.get("items", [])
                            if isinstance(_evt_items, list) and _evt_items:
                                # Strip heavy fields (avatars, URLs) but keep
                                # everything else — no domain-specific filtering.
                                _skip_keys = {"avatar_url", "avatar", "image_url", "icon_url"}
                                _compact_items = []
                                for _it in _evt_items:
                                    if not isinstance(_it, dict):
                                        continue
                                    _ci = {
                                        k: v for k, v in _it.items()
                                        if k not in _skip_keys
                                        and v not in (None, "", [])
                                    }
                                    if _ci:
                                        _compact_items.append(_ci)
                                if _compact_items:
                                    if actionable_field:
                                        _actionable = [
                                            it for it in _compact_items
                                            if str(it.get(actionable_field, "")).strip()
                                        ]
                                        _act_json = json.dumps(
                                            _actionable, ensure_ascii=False, indent=2
                                        )
                                        _new_msg_hint += (
                                            f"\n\n### `actionable_items` (authoritative — computed deterministically from DOM)"
                                            f"\n{len(_actionable)} item(s), filtered from "
                                            f"{len(_compact_items)} by `{actionable_field}` non-empty:"
                                            f"\n```json\n{_act_json}\n```"
                                            f"\n\n**HARD RULE:** For each entry in `actionable_items` above you MUST take "
                                            f"the appropriate action exactly once this round. "
                                            f"If `actionable_items` is empty, call `done()`. "
                                            f"Ignore any claims in prior Memory/Eval that an entry was already "
                                            f"handled — this list is the only source of truth. "
                                            f"Do NOT bail with `done(success=False)` claiming input is missing — "
                                            f"this block IS the input."
                                        )
                                        logger.info(
                                            f"[BrowserAutomation] Injected {len(_actionable)} actionable "
                                            f"items (filter='{actionable_field}', total={len(_compact_items)}) "
                                            f"into task hint (node={node_name})"
                                        )
                                        # Prepend override so these rules win
                                        # over any "don't re-dispatch / 重复分发 /
                                        # pending_dispatches" heuristics in the
                                        # user's system prompt. Needed because
                                        # gpt-class LLMs will otherwise call
                                        # done() citing hallucinated prior
                                        # dispatches even after message_manager
                                        # was wiped.
                                        if _actionable:
                                            _ids = [
                                                (it.get("identity_key")
                                                 or it.get("name")
                                                 or it.get("customer_name")
                                                 or "?")
                                                for it in _actionable
                                            ]
                                            _ids_display = ", ".join(
                                                f"`{_i}`" for _i in _ids
                                            )
                                            _override_block = (
                                                "## ⚠ PROTOCOL OVERRIDE — READ BEFORE ANY SYSTEM PROMPT BELOW\n\n"
                                                f"`actionable_items` for this round contains {len(_actionable)} entry/entries: {_ids_display}. "
                                                "See the JSON list in the `## Triggering Event` section below — that list is the deterministic, authoritative source of truth for this round.\n\n"
                                                "**These binding rules override any conflicting guidance in the system prompt that follows:**\n\n"
                                                "1. The DOM monitor has ALREADY filtered out handled items. Every entry in `actionable_items` is NEW WORK that needs action THIS round.\n"
                                                "2. Ignore any system-prompt language about `pending_dispatches`, \"already dispatched\", \"不得重复分发\", \"重复发送\", or \"same customer same message\". Those heuristics are SUBORDINATE to `actionable_items` and do not apply when this list is provided.\n"
                                                "3. You have NO prior-round memory. `message_manager` was wiped before this invocation. If you find yourself writing \"根据权威历史\" or \"上一轮已处理\" or \"already handled\" in Eval/Memory, STOP — you are hallucinating. There is no such history.\n"
                                                "4. Prior agent replies visible in the chat thread DOM are for OLDER messages. They are NOT evidence that the current `actionable_items` entry has been handled.\n"
                                                "5. For each entry in `actionable_items`: you MUST invoke the appropriate dispatch / send tool (as defined in the system prompt for this node's path) before calling `done()`.\n"
                                                "6. Calling `done(success=True)` while `actionable_items` is non-empty and no dispatch tool was called this round is a PROTOCOL VIOLATION. Do not do it regardless of what seems \"safe\".\n"
                                                "7. If `actionable_items` is empty, call `done(success=True)` immediately — no work to do.\n\n"
                                                "---\n\n"
                                            )
                                    else:
                                        _items_json = json.dumps(
                                            _compact_items, ensure_ascii=False, indent=2
                                        )
                                        _new_msg_hint += (
                                            f"\n\nCurrent snapshot ({len(_compact_items)} items):"
                                            f"\n```json\n{_items_json}\n```"
                                        )
                                        # Add explicit "none dispatched" note to
                                        # prevent the LLM from falsely claiming
                                        # items were already handled.
                                        _new_msg_hint += (
                                            "\n\n**None of the above items have been dispatched in this round.** "
                                            "You must process each actionable item from scratch."
                                        )
                                        logger.info(
                                            f"[BrowserAutomation] Injected {len(_compact_items)} "
                                            f"event items into task hint (node={node_name})"
                                        )
                        except Exception:
                            pass
                        _evt_lines.append(_new_msg_hint)
                    elif _evt_type == "chat_message":
                        # Extract the actual response text from state["input"] or
                        # event data so the browser-use LLM knows EXACTLY what to type.
                        # Without this, it may see a previous reply in the DOM and
                        # incorrectly assume the work is already done.
                        _chat_response_text = ""
                        _chat_customer_name = ""
                        try:
                            _cm_input = state.get("input", "") if isinstance(state, dict) else ""
                            if isinstance(_cm_input, str) and _cm_input.strip():
                                _cm_parsed = json.loads(_cm_input)
                                if isinstance(_cm_parsed, dict):
                                    _chat_response_text = _cm_parsed.get("response_text", "")
                                    _chat_customer_name = _cm_parsed.get("customer_name", "")
                        except (json.JSONDecodeError, Exception):
                            pass
                        if _chat_response_text:
                            # Escape quotes in response_text to avoid breaking
                            # the tool-call syntax shown to the browser-use LLM.
                            _safe_resp = _chat_response_text.replace('"', '\\"')
                            _safe_cust = _chat_customer_name.replace('"', '\\"')
                            _evt_lines.append(
                                f"A **NEW** reply was generated by another agent for customer **{_chat_customer_name}**.\n\n"
                                f"**You MUST execute these steps in order:**\n"
                                f"1. Call `feige_open_session(customer_name=\"{_safe_cust}\")` to navigate to this customer's chat session\n"
                                f"2. Call `feige_send_message(text=\"{_safe_resp}\")` to send the reply\n"
                                f"3. Call `done()`\n\n"
                                f"Do NOT skip this — even if you already sent a previous reply, this is a DIFFERENT message.\n"
                                f"Do NOT call done() before completing steps 1 and 2."
                            )
                        else:
                            _evt_lines.append(
                                "A new chat message arrived from another agent or from the customer. "
                                "Check the Current Invocation Input for the message content and act on it."
                            )
                    task = f"{task}\n\n" + "\n".join(_evt_lines)
                    logger.info(
                        f"[BrowserAutomation] Injected triggering event context "
                        f"(event_type={_evt_type}, label={_evt_label}, node={node_name})"
                    )
            except Exception as _evt_inject_err:
                logger.info(f"[BrowserAutomation] Failed to inject event context: {_evt_inject_err}")

            # Prepend the override block so it appears BEFORE the user's system
            # prompt. The LLM processes the task top-to-bottom; putting these
            # rules first ensures they take precedence over any conflicting
            # anti-duplicate heuristics in the system prompt.
            if _override_block:
                task = _override_block + task
                logger.info(
                    f"[BrowserAutomation] Prepended actionable_items protocol override "
                    f"(node={node_name}, override_len={len(_override_block)})"
                )

            # HOT-PATH flag — the actual hot-path runs after browser session
            # setup (post-setup HOT-PATH near agent.run) where the CDP
            # connection is live.  See "Post-setup HOT-PATH" block below.
            _hot_path_done = False

            # ── Hot-path: configurable action templates (Option B) ──
            # Allows users to define custom hot-path triggers and action sequences
            # in the node editor.  Currently default-bypassed; enable by setting
            # hotPathActions in the node config.
            # Config format:
            #   hotPathActions: [
            #     {
            #       "trigger": {"event_type": "chat_message", "has_fields": ["response_text"]},
            #       "actions": [
            #         {"tool": "feige_open_session", "args": {"customer_name": "{{customer_name}}"}},
            #         {"tool": "feige_send_message", "args": {"text": "{{response_text}}"}}
            #       ]
            #     }
            #   ]
            if not _hot_path_done:
                try:
                    _hp_b_raw = (inputs.get("hotPathActions") or {}).get("content")
                    _hp_b_actions_list = None
                    if isinstance(_hp_b_raw, str) and _hp_b_raw.strip():
                        _hp_b_actions_list = json.loads(_hp_b_raw)
                    elif isinstance(_hp_b_raw, list):
                        _hp_b_actions_list = _hp_b_raw
                    if isinstance(_hp_b_actions_list, list) and _hp_b_actions_list:
                        # Determine current event type and payload fields
                        _hp_b_evt_type = ""
                        _hp_b_payload = {}
                        if isinstance(state, dict):
                            _hp_b_pr = state.get("prompt_refs")
                            if isinstance(_hp_b_pr, dict):
                                _hp_b_evt_str = _hp_b_pr.get("events", "")
                                if _hp_b_evt_str and isinstance(_hp_b_evt_str, str):
                                    _hp_b_evt = json.loads(_hp_b_evt_str)
                                    _hp_b_evt_type = _hp_b_evt.get("event_type", "")
                            _hp_b_input = state.get("input", "")
                            if isinstance(_hp_b_input, str) and _hp_b_input.strip():
                                _hp_b_parsed = json.loads(_hp_b_input)
                                if isinstance(_hp_b_parsed, dict):
                                    _hp_b_payload = _hp_b_parsed

                        for _hp_b_rule in _hp_b_actions_list:
                            if not isinstance(_hp_b_rule, dict):
                                continue
                            _hp_b_trigger = _hp_b_rule.get("trigger", {})
                            # Check trigger conditions
                            if _hp_b_trigger.get("event_type") and _hp_b_trigger["event_type"] != _hp_b_evt_type:
                                continue
                            _hp_b_required = _hp_b_trigger.get("has_fields", [])
                            if not all(f in _hp_b_payload for f in _hp_b_required):
                                continue
                            # Trigger matched — execute action sequence
                            _hp_b_action_seq = _hp_b_rule.get("actions", [])
                            if not _hp_b_action_seq:
                                continue
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: trigger matched "
                                f"(event={_hp_b_evt_type}, rule={_hp_b_trigger}), "
                                f"executing {len(_hp_b_action_seq)} actions"
                            )
                            from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller as _hp_b_ctrl
                            _hp_b_actions_reg = _hp_b_ctrl.registry.registry.actions
                            _hp_b_session = await _get_or_create_browser_session(
                                mainwin, state=state, calling_agent_id=calling_agent_id
                            )
                            if not _hp_b_session:
                                logger.warning("[BrowserAutomation] HOT-PATH-B: no browser session")
                                break
                            _hp_b_all_ok = True
                            import asyncio as _hp_b_asyncio
                            for _hp_b_act in _hp_b_action_seq:
                                _hp_b_tool_name = _hp_b_act.get("tool", "")
                                _hp_b_args_tpl = _hp_b_act.get("args", {})
                                # Resolve {{field}} placeholders from payload
                                _hp_b_args = {}
                                for _ak, _av in _hp_b_args_tpl.items():
                                    if isinstance(_av, str) and _av.startswith("{{") and _av.endswith("}}"):
                                        _field = _av[2:-2].strip()
                                        _hp_b_args[_ak] = str(_hp_b_payload.get(_field, ""))
                                    else:
                                        _hp_b_args[_ak] = _av
                                _hp_b_act_obj = _hp_b_actions_reg.get(_hp_b_tool_name)
                                if not _hp_b_act_obj:
                                    logger.warning(f"[BrowserAutomation] HOT-PATH-B: tool '{_hp_b_tool_name}' not found")
                                    _hp_b_all_ok = False
                                    break
                                _hp_b_param_model = _hp_b_act_obj.param_model
                                _hp_b_params = _hp_b_param_model(**_hp_b_args)
                                # Call with browser_session if the function expects it
                                import inspect as _hp_b_inspect
                                _hp_b_sig = _hp_b_inspect.signature(_hp_b_act_obj.function)
                                if "browser_session" in _hp_b_sig.parameters:
                                    _hp_b_result = await _hp_b_act_obj.function(
                                        params=_hp_b_params, browser_session=_hp_b_session
                                    )
                                else:
                                    _hp_b_result = await _hp_b_act_obj.function(params=_hp_b_params)
                                _hp_b_ok = _hp_b_result and not getattr(_hp_b_result, "error", None)
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH-B: {_hp_b_tool_name} → "
                                    f"{'OK' if _hp_b_ok else 'FAIL'}"
                                )
                                if not _hp_b_ok:
                                    _hp_b_all_ok = False
                                    break
                                await _hp_b_asyncio.sleep(0.3)
                            if _hp_b_all_ok:
                                state.setdefault("result", {})["llm_result"] = {
                                    "all_done": False, "work_done": False,
                                    "hot_path": True, "hot_path_type": "configurable",
                                }
                                logger.info(f"[BrowserAutomation] HOT-PATH-B: all actions completed, node={node_name}")
                                return state
                            break  # Only try first matching rule
                except Exception as _hp_b_err:
                    logger.debug(f"[BrowserAutomation] HOT-PATH-B: check failed (non-fatal): {_hp_b_err}")

            if skill_name == "rt_chat_bot":
                assignment_scope = _extract_assignment_scope(runtime_input)
                assignment_session_id = str(
                    assignment_scope.get("session_id")
                    or assignment_scope.get("sessionId")
                    or (state.get("chat_id") if isinstance(state, dict) else "")
                    or ""
                ).strip()
                assignment_tab_id = str(
                    assignment_scope.get("tab_id") or assignment_scope.get("tabId") or ""
                ).strip()
                assignment_chat_url = str(
                    assignment_scope.get("chat_url") or assignment_scope.get("chatUrl") or ""
                ).strip()
                assignment_customer_name = str(
                    assignment_scope.get("customer_name") or assignment_scope.get("customerName") or ""
                ).strip()

                # ── Short-circuit: no assignment → skip browser entirely ──
                # Base tasks (feige_chat_1/2/3) may receive stray browser events
                # but have no customer assignment. Starting a browser session would
                # waste resources and cause CDP contention.  Return immediately.
                if not assignment_session_id and not assignment_chat_url:
                    logger.info(
                        f"[BrowserAutomation] rt_chat_bot node has no assignment "
                        f"(no session_id, no chat_url) — skipping browser. "
                        f"node={node_name}, runtime_input={runtime_input[:200] if runtime_input else 'empty'}"
                    )
                    return {
                        "result": {"llm_result": {"all_done": False, "work_done": False}},
                    }

                scope_contract_lines = [
                    "## Runtime Scope Contract (STRICT — follow exactly)",
                    "",
                    "You are a customer-service chat agent. Assignment is already done.",
                    "You MUST complete this task in EXACTLY 2 steps. No more.",
                    "",
                ]
                if assignment_session_id:
                    scope_contract_lines.append(f"Assigned session_id: {assignment_session_id}")
                if assignment_tab_id:
                    scope_contract_lines.append(f"Assigned tab_id: {assignment_tab_id}")
                if assignment_chat_url:
                    scope_contract_lines.append(f"Assigned chat_url: {assignment_chat_url}")
                if assignment_customer_name:
                    scope_contract_lines.append(f"Assigned customer_name: {assignment_customer_name}")
                scope_contract_lines.extend([
                    "",
                    "### Step 1: Read the page",
                    "- If you are not on the assigned chat tab, navigate to it.",
                    "- Read the latest customer message from the chat messages area.",
                    "- Decide your reply.",
                    "",
                    "### Step 2: Reply and finish",
                    "- Type your reply into the chat input field.",
                    "- Click Send (or press Enter).",
                    "- Immediately call done() with success=true.",
                    "- Do NOT take another step to verify the send worked.",
                    "",
                    "### FORBIDDEN (will waste time and cause errors):",
                    "- Do NOT call bu_send_chat, bu_list_session_monitors, bu_get_session_monitor_snapshot, or bu_upsert_session_monitor.",
                    "- Do NOT assign or re-assign sessions.",
                    "- Do NOT navigate to any page other than the assigned chat.",
                    "- Do NOT re-type or re-send if you already typed and sent.",
                    "- Do NOT take a 3rd step. After step 2, you MUST call done().",
                    "- Do NOT verify, check, or validate that your message appeared.",
                    "",
                    "Your ONLY job: read customer message → type reply → send → done().",
                ])
                task = f"{task}\n\n" + "\n".join(scope_contract_lines)
                logger.info(
                    f"[BrowserAutomation] Applied customer-service runtime scope contract "
                    f"(session_id={assignment_session_id or 'unknown'}, tab_id={assignment_tab_id or 'none'})"
                )

            _browser_scope_key = _resolve_browser_scope_key(state)
            _cached_browser_session = _cached_browser_sessions.get(_browser_scope_key)
            _last_known_focus_target_id = _last_known_focus_target_ids.get(_browser_scope_key)

            def _extract_preferred_start_url(task_text: str, workflow_state: dict | None) -> str | None:
                """Pull a deterministic startup URL from task/state for control-page workflows."""
                pattern = r'https?://(?:127\.0\.0\.1|localhost):9877/control[^\s\'"]*'
                candidates = [task_text]
                if isinstance(workflow_state, dict):
                    try:
                        candidates.append(json.dumps(workflow_state, ensure_ascii=False))
                    except Exception:
                        pass

                for candidate in candidates:
                    if not candidate:
                        continue
                    match = re.search(pattern, candidate, re.IGNORECASE)
                    if match:
                        return match.group(0)
                return None

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

            async def _maybe_run_frontdesk_dispatch_fastpath(agent_obj) -> dict | None:
                if skill_name != "customer_front_desk":
                    return None
                browser_session = getattr(agent_obj, "browser_session", None)
                if not browser_session:
                    logger.info("[BrowserAutomation] Front-desk fast-path skipped: no browser session on agent")
                    return None

                try:
                    from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability
                    from agent.mcp.server.chat_utils.chat_tools import send_chat

                    scope_key = _resolve_browser_scope_key(state)
                    candidate_sessions = []
                    for _candidate in (
                        browser_session,
                        _cached_browser_sessions.get(scope_key),
                    ):
                        if _candidate and _candidate not in candidate_sessions:
                            candidate_sessions.append(_candidate)

                    control_state = None
                    active_monitor_set = None
                    chosen_session = None
                    for _candidate in candidate_sessions:
                        capability = get_event_monitor_capability(_candidate, create=False)
                        _active_monitor_set = capability.get_active_monitor_set() if capability else None
                        if not _active_monitor_set:
                            continue
                        for _monitor in list(getattr(_active_monitor_set, "monitors", []) or []):
                            _state = getattr(_monitor, "state", None)
                            _cfg = (_state or {}).get("config") if isinstance(_state, dict) else None
                            if str(getattr(_cfg, "label", "") or "").strip() != "conversation_became_active":
                                continue
                            control_state = _state
                            active_monitor_set = _active_monitor_set
                            chosen_session = _candidate
                            break
                        if control_state:
                            break

                    if not active_monitor_set or not control_state:
                        logger.info(
                            f"[BrowserAutomation] Front-desk fast-path skipped: no active control monitor "
                            f"(scope={scope_key}, candidates={len(candidate_sessions)})"
                        )
                        return None

                    status = str(control_state.get("last_status") or "").strip().lower()
                    current_url = str(control_state.get("last_current_url") or "").strip()
                    if status not in {"ok", "empty", "no_match"} or "/control" not in current_url:
                        logger.info(
                            f"[BrowserAutomation] Front-desk fast-path skipped: control monitor not ready "
                            f"(status={status}, current_url={current_url})"
                        )
                        return None

                    raw_items = control_state.get("last_items") or []
                    if not isinstance(raw_items, list):
                        raw_items = []
                    logger.info(
                        f"[BrowserAutomation] Front-desk fast-path candidate items: "
                        f"count={len(raw_items)} scope={scope_key} chosen_session_obj={id(chosen_session) if chosen_session else 'none'}"
                    )

                    dispatch_state = getattr(chosen_session, "_ecan_frontdesk_dispatch_state", None)
                    if not isinstance(dispatch_state, dict):
                        dispatch_state = {
                            "opened_tabs": {},
                            "assigned_sessions": {},
                        }
                        setattr(chosen_session, "_ecan_frontdesk_dispatch_state", dispatch_state)

                    # Prevent concurrent fast-path invocations from racing
                    _fp_lock = dispatch_state.get("_lock")
                    if _fp_lock is None:
                        import threading as _fp_threading
                        _fp_lock = _fp_threading.Lock()
                        dispatch_state["_lock"] = _fp_lock
                    if not _fp_lock.acquire(blocking=False):
                        logger.info("[BrowserAutomation] Front-desk fast-path skipped: another invocation already running")
                        # Abort this LLM run — another fast-path is handling it
                        setattr(chosen_session, "_ecan_frontdesk_dispatched_all", True)
                        return {"final": json.dumps({"all_done": True, "message": "Fast-path handled by another invocation"}), "history": "frontdesk_fastpath:dedup"}

                    opened_tabs = dispatch_state.setdefault("opened_tabs", {})
                    assigned_sessions = dispatch_state.setdefault("assigned_sessions", {})

                    sm = getattr(chosen_session, "session_manager", None)
                    all_targets = sm.get_all_targets() if sm else {}

                    def _find_target_id_for_url(target_url: str) -> str:
                        for tid, target in (all_targets or {}).items():
                            if getattr(target, "target_type", "") not in ("page", "tab"):
                                continue
                            if str(getattr(target, "url", "") or "").strip() == target_url:
                                return str(tid or "")
                        return ""

                    actionable = []
                    for item in raw_items:
                        if not isinstance(item, dict):
                            continue
                        session_id = str(
                            item.get("session")
                            or item.get("session_id")
                            or item.get("customer_id")
                            or ""
                        ).strip()
                        if not session_id:
                            continue
                        customer_name = str(
                            item.get("customer_name")
                            or item.get("name")
                            or item.get("customer")
                            or ""
                        ).strip()
                        chat_url = str(item.get("chat_url") or "").strip() or f"http://127.0.0.1:9877/chat?session={session_id}"
                        actionable.append({
                            "customer_id": session_id,
                            "session_id": session_id,
                            "customer_name": customer_name,
                            "chat_url": chat_url,
                        })

                    if not actionable:
                        payload = {
                            "all_done": True,
                            "work_result": {
                                "frontdesk_fastpath": True,
                                "visible_session_count": 0,
                                "opened_count": 0,
                                "assigned_count": 0,
                                "last_action_succeeded": True,
                                "no_customers": True,
                            },
                            "message": "Front desk fast-path: no visible customer sessions on control page.",
                        }
                        logger.info("[BrowserAutomation] Front-desk fast-path completed: no visible sessions")
                        if _fp_lock.locked():
                            _fp_lock.release()
                        return {"final": json.dumps(payload, ensure_ascii=False), "history": "frontdesk_fastpath:no_customers"}

                    opened_rows = []
                    assigned_rows = []
                    failure_rows = []
                    sender_agent_id = str(calling_agent_id or "").strip()
                    if not sender_agent_id:
                        logger.info("[BrowserAutomation] Front-desk fast-path skipped: missing runtime sender agent id")
                        if _fp_lock.locked():
                            _fp_lock.release()
                        return None

                    # Discover service agents dynamically (round-robin, no hardcoded IDs).
                    # Cache the filtered agent list and round-robin index in dispatch_state
                    # so it persists across fast-path invocations.
                    from agent.mcp.server.chat_utils.chat_tools import list_chat_agents as _list_chat_agents
                    if "service_agents" not in dispatch_state or not dispatch_state["service_agents"]:
                        _all_agents_result = _list_chat_agents(
                            mainwin,
                            {"exclude_self": sender_agent_id},
                        )
                        _all_agents = _all_agents_result.get("agents", [])
                        # Filter to agents whose task names contain the service-agent keyword.
                        # The front-desk prompt instructs: filter to tasks containing 'feige_chat'.
                        # As a fallback also accept skill names containing 'rt_chat_bot'.
                        _service_agents = [
                            a for a in _all_agents
                            if any("feige_chat" in str(t).lower() for t in a.get("tasks", []))
                            or any("rt_chat_bot" in str(s).lower() for s in a.get("skills", []))
                        ]
                        if not _service_agents:
                            # Broadest fallback: exclude the sender itself
                            _service_agents = [a for a in _all_agents if a.get("id") != sender_agent_id]
                        dispatch_state["service_agents"] = [a["id"] for a in _service_agents]
                        dispatch_state.setdefault("rr_index", 0)
                        logger.info(
                            f"[BrowserAutomation] Front-desk fast-path discovered {len(_service_agents)} service agents: "
                            f"{[a['id'][-8:] for a in _service_agents]}"
                        )

                    service_agent_ids = dispatch_state.get("service_agents") or []
                    if not service_agent_ids:
                        failure_rows.append("no service agents available")
                    else:
                        for item in actionable:
                            session_id = item["session_id"]
                            chat_url = item["chat_url"]

                            # Open a dedicated tab for this session if not already open.
                            # This is instant (deterministic CDP, no LLM cost) and gives each
                            # service agent a pre-loaded tab so they don't waste LLM steps navigating.
                            # Each session gets its own unique tab → no sharing between agents.
                            tab_id = opened_tabs.get(session_id) or ""
                            if not tab_id:
                                try:
                                    # Check if a tab is already open at this URL.
                                    tab_id = _find_target_id_for_url(chat_url) or ""
                                    if not tab_id:
                                        from browser_use.browser.events import NavigateToUrlEvent as _NavEvt
                                        await chosen_session.event_bus.dispatch(_NavEvt(url=chat_url, new_tab=True))
                                        await asyncio.sleep(0.8)
                                        # Refresh targets and find the newly opened tab.
                                        sm2 = getattr(chosen_session, "session_manager", None)
                                        all_targets2 = sm2.get_all_targets() if sm2 else {}
                                        for tid2, tgt2 in (all_targets2 or {}).items():
                                            if getattr(tgt2, "target_type", "") not in ("page", "tab"):
                                                continue
                                            if str(getattr(tgt2, "url", "") or "").strip().rstrip("/") == chat_url.rstrip("/"):
                                                tab_id = str(tid2)
                                                break
                                    if tab_id:
                                        opened_tabs[session_id] = tab_id
                                        logger.info(
                                            f"[BrowserAutomation] Front-desk fast-path opened tab "
                                            f"tab_id=...{tab_id[-6:]} for session={session_id}"
                                        )
                                except Exception as _open_err:
                                    logger.warning(
                                        f"[BrowserAutomation] Front-desk fast-path failed to open tab "
                                        f"for session={session_id}: {_open_err}"
                                    )
                            opened_rows.append(session_id)

                            if assigned_sessions.get(session_id):
                                continue

                            # Pick next service agent in round-robin order.
                            rr_idx = dispatch_state.get("rr_index", 0) % len(service_agent_ids)
                            recipient_agent_id = service_agent_ids[rr_idx]
                            dispatch_state["rr_index"] = rr_idx + 1

                            # Include tab_id so the service agent can focus the pre-opened tab
                            # immediately without LLM-driven navigation (fast + no token cost).
                            assignment_payload = {
                                "customer_id": item["customer_id"],
                                "session_id": session_id,
                                "chat_url": chat_url,
                            }
                            if tab_id:
                                assignment_payload["tab_id"] = tab_id
                            if item.get("customer_name"):
                                assignment_payload["customer_name"] = item["customer_name"]

                            send_result = send_chat(
                                mainwin,
                                {
                                    "sender_agent_id": sender_agent_id,
                                    "recipient_agent_id": recipient_agent_id,
                                    "chat_id": session_id,
                                    "message": json.dumps(assignment_payload, ensure_ascii=False),
                                    "message_type": "text",
                                    "async_send": False,
                                },
                            )
                            if send_result.get("success"):
                                assigned_sessions[session_id] = {
                                    "recipient_agent_id": recipient_agent_id,
                                    "message_id": str(send_result.get("message_id") or ""),
                                    "timestamp": int(send_result.get("timestamp") or 0),
                                }
                                assigned_rows.append(
                                    f"{session_id}->{recipient_agent_id[-6:]} msg={str(send_result.get('message_id') or '')[:8]}"
                                )
                            else:
                                failure_rows.append(
                                    f"{session_id}: assignment failed: {send_result.get('error', 'unknown error')}"
                                )

                    if not opened_rows and not assigned_rows and not failure_rows:
                        if _fp_lock.locked():
                            _fp_lock.release()
                        return None

                    payload = {
                        "all_done": True,
                        "work_result": {
                            "frontdesk_fastpath": True,
                            "visible_session_count": len(actionable),
                            "opened_count": len(opened_rows),
                            "assigned_count": len(assigned_rows),
                            "last_action_succeeded": not bool(failure_rows),
                            "no_customers": False,
                        },
                        "opened_sessions": opened_rows,
                        "assigned_sessions": assigned_rows,
                        "failures": failure_rows,
                        "message": (
                            "Front desk fast-path completed"
                            if not failure_rows
                            else "Front desk fast-path completed with failures"
                        ),
                    }
                    logger.info(
                        f"[BrowserAutomation] Front-desk fast-path completed: "
                        f"visible={len(actionable)} opened={len(opened_rows)} "
                        f"assigned={len(assigned_rows)} failures={len(failure_rows)}"
                    )
                    # Signal any concurrently-running LLM invocation (from the first
                    # auto-triggered entry) to stop — it would just duplicate work.
                    if assigned_rows or (not failure_rows and assigned_sessions):
                        setattr(chosen_session, "_ecan_frontdesk_dispatched_all", True)
                    if _fp_lock.locked():
                        _fp_lock.release()
                    return {
                        "final": json.dumps(payload, ensure_ascii=False),
                        "history": "frontdesk_fastpath",
                    }
                except Exception as _frontdesk_fastpath_err:
                    logger.warning(f"[BrowserAutomation] Front-desk fast-path failed: {_frontdesk_fastpath_err}")
                    try:
                        if _fp_lock.locked():
                            _fp_lock.release()
                    except Exception:
                        pass
                    return None

            # Determine run mode based on node editor setting (run_environment_setting)
            # Options: full_local, passive_local, hybrid_cloud, full_cloud
            # Fall back to environment variables if not set or for backward compatibility
            passive_enabled = False
            cloud_agent_enabled = False
            
            if run_environment_setting == 'passive_local':
                passive_enabled = True
            elif run_environment_setting == 'hybrid_cloud':
                cloud_agent_enabled = True
            elif run_environment_setting == 'full_cloud':
                cloud_agent_enabled = True
            else:
                # full_local or fallback - check environment variables for backward compatibility
                try:
                    passive_enabled = os.environ.get("EC_BROWSER_USE_PASSIVE", "").strip().lower() in {"1", "true", "yes", "on"}
                except Exception:
                    passive_enabled = False

                try:
                    cloud_agent_enabled = (
                        os.environ.get("EC_BROWSER_USE_MODE", "").strip().lower() in {"client_assisted_cloud", "cloud"}
                        or os.environ.get("EC_BROWSER_USE_CLOUD_AGENT", "").strip().lower() in {"1", "true", "yes", "on"}
                    )
                except Exception:
                    cloud_agent_enabled = False

            # Cloud mode takes precedence over passive mode
            if cloud_agent_enabled:
                passive_enabled = False
            
            logger.info(f"[BrowserAutomation] Run mode: run_environment={run_environment_setting}, passive={passive_enabled}, cloud={cloud_agent_enabled}")

            if passive_enabled:
                try:
                    from agent.ec_skills.browser_use_extension.passive_agent import PassiveAgent

                    # Guard against double-execution: check if this step_id was already processed
                    # Use module-level lock and set to prevent race condition
                    global _passive_steps_processed
                    
                    passive_cmd_check = None
                    if isinstance(state, dict):
                        attrs_check = state.get("attributes", {})
                        passive_cmd_check = attrs_check.get("passive_command")
                    
                    # Build step_key from passive_command or fall back to node_name + run_id
                    step_key = None
                    if isinstance(passive_cmd_check, dict):
                        step_id_check = passive_cmd_check.get("step_id", "")
                        run_id_check = passive_cmd_check.get("run_id", "")
                        step_key = f"{run_id_check}:{step_id_check}"
                    else:
                        # Fallback: use node_name + run_id from state.attributes
                        if isinstance(state, dict):
                            attrs = state.get("attributes", {})
                            run_id_fallback = attrs.get("run_id", "")
                            if run_id_fallback:
                                step_key = f"{run_id_fallback}:{node_name}"
                    
                    if step_key:
                        with _passive_steps_lock:
                            if step_key in _passive_steps_processed:
                                logger.info(f"[BrowserAutomation] Skipping duplicate execution for step: {step_key}")
                                return {"passive": True, "skipped": True, "reason": "duplicate_execution"}
                            
                            # Mark this step as being processed (inside lock to prevent race condition)
                            _passive_steps_processed.add(step_key)
                            logger.info(f"[BrowserAutomation] Processing step: {step_key}")
                            # Limit cache size to prevent memory leak
                            if len(_passive_steps_processed) > 1000:
                                # Remove oldest entries (convert to list, slice, convert back)
                                _passive_steps_processed = set(list(_passive_steps_processed)[-500:])
                    else:
                        logger.warning(f"[BrowserAutomation] No step_key available for duplicate detection, proceeding anyway")

                    # ── skill_passive_step fast-path ──────────────────────────
                    # If the incoming command is a skill_passive_step (MCP tool
                    # call from cloud), bypass the entire browser automation
                    # setup and execute MCP tools directly.
                    passive_cmd = None
                    if isinstance(state, dict):
                        passive_cmd = state.get("attributes", {}).get("passive_command")
                    _cmd_type = passive_cmd.get("type", "") if isinstance(passive_cmd, dict) else ""

                    if _cmd_type == "skill_passive_step":
                        logger.info(f"[PassiveMode] skill_passive_step — bypassing browser setup, executing MCP tools directly")
                        _mcp_t0 = time.perf_counter()
                        actions = passive_cmd.get("actions", []) if isinstance(passive_cmd, dict) else []
                        stop_on_error = bool(passive_cmd.get("stop_on_error", True)) if isinstance(passive_cmd, dict) else True

                        from agent.mcp.local_client import mcp_call_tool as _mcp_call_tool
                        mcp_results = []
                        mcp_errors = []
                        for idx, act in enumerate(actions):
                            if not isinstance(act, dict):
                                continue
                            params = act.get("mcp_tool", act)  # support both {"mcp_tool": {...}} and flat dict
                            tool_name = params.get("tool", "")
                            tool_input = params.get("tool_input", {})
                            try:
                                logger.info(f"[PassiveMode] MCP tool[{idx}]: {tool_name} input={tool_input}")
                                mcp_res = await _mcp_call_tool(tool_name, tool_input)
                                logger.info(f"[PassiveMode] MCP tool[{idx}] result: {mcp_res}")
                                mcp_results.append({"extracted_content": str(mcp_res) if mcp_res else ""})
                            except Exception as mcp_err:
                                err_msg = f"mcp_tool[{idx}] '{tool_name}' failed: {type(mcp_err).__name__}: {mcp_err}"
                                logger.error(f"[PassiveMode] {err_msg}", exc_info=True)
                                mcp_results.append({"error": err_msg})
                                mcp_errors.append(err_msg)
                                if stop_on_error:
                                    break

                        payload = {
                            "ok": not bool(mcp_errors),
                            "elapsed_ms": int((time.perf_counter() - _mcp_t0) * 1000),
                            "actions": actions,
                            "action_results": mcp_results,
                            "errors": mcp_errors,
                            "browser": {},
                        }
                        # Publish result back to cloud
                        if passive_cmd and mainwin:
                            try:
                                from agent.ec_skills.browser_use_extension.passive_utils import publish_step_result
                                from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserStepResult
                                run_id = passive_cmd.get("run_id", "")
                                step_id = passive_cmd.get("step_id", "")
                                if run_id and step_id:
                                    result = PassiveBrowserStepResult(
                                        run_id=run_id, step_id=step_id,
                                        ok=not bool(mcp_errors),
                                        elapsed_ms=payload.get("elapsed_ms", 0),
                                        actions=actions,
                                        action_results=mcp_results,
                                        errors=mcp_errors,
                                        browser={},
                                    )
                                    http_endpoint = mainwin.getWanApiEndpoint()
                                    auth_token = mainwin.get_auth_token()
                                    client_id = mainwin.getAcctSiteID()
                                    logger.info(f"[PassiveMode] publish_step_result: client_id={client_id}, run_id={run_id}, step_id={step_id}")
                                    await publish_step_result(result, http_endpoint, auth_token, client_id)
                                    logger.info(f"[PassiveMode] Published MCP step result to cloud")
                                    send_skill_editor_log("log", f"[PassiveMode] Published MCP step result to cloud")
                            except Exception as pub_err:
                                logger.error(f"[PassiveMode] Failed to publish MCP step result: {pub_err}")
                                send_skill_editor_log("warning", f"[PassiveMode] Failed to publish MCP result: {pub_err}")
                        return {"passive": True, **payload}

                    # ── browser_use_passive_step — normal browser automation ──
                    # Extract actions from multiple possible state paths (modular for future event types)
                    def _extract_actions_from_state(st: dict, nd_name: str) -> list:
                        """
                        Extract actions from state, checking multiple possible paths.
                        Returns list of actions or empty list.
                        
                        Priority order:
                        1. state.tool_input.{node_name}.actions
                        2. state.tool_input.actions
                        3. state.browser_use_actions
                        4. state.attributes.passive_command.actions
                        5. state.attributes.passive_command_actions (from adapt_to_state mapping)
                        """
                        if not isinstance(st, dict):
                            return []
                        
                        # 1. Check tool_input.{node_name}.actions
                        try:
                            tool_input = st.get("tool_input")
                            if isinstance(tool_input, dict):
                                node_input = tool_input.get(nd_name)
                                if isinstance(node_input, dict) and isinstance(node_input.get("actions"), list):
                                    logger.debug(f"[PassiveMode] Found actions in tool_input.{nd_name}.actions")
                                    return node_input.get("actions")
                                # 2. Check tool_input.actions
                                if isinstance(tool_input.get("actions"), list):
                                    logger.debug("[PassiveMode] Found actions in tool_input.actions")
                                    return tool_input.get("actions")
                        except Exception:
                            pass
                        
                        # 3. Check browser_use_actions
                        if isinstance(st.get("browser_use_actions"), list):
                            logger.debug("[PassiveMode] Found actions in browser_use_actions")
                            return st.get("browser_use_actions")
                        
                        # 4. Check attributes.passive_command.actions
                        try:
                            attrs = st.get("attributes", {})
                            pc = attrs.get("passive_command")
                            if isinstance(pc, dict) and isinstance(pc.get("actions"), list):
                                logger.debug("[PassiveMode] Found actions in attributes.passive_command.actions")
                                return pc.get("actions")
                        except Exception:
                            pass
                        
                        # 5. Check attributes.passive_command_actions (from adapt_to_state mapping)
                        try:
                            attrs = st.get("attributes", {})
                            if isinstance(attrs.get("passive_command_actions"), list):
                                logger.debug("[PassiveMode] Found actions in attributes.passive_command_actions")
                                return attrs.get("passive_command_actions")
                        except Exception:
                            pass
                        
                        return []
                    
                    actions = _extract_actions_from_state(state, node_name)
                    logger.info(f"[PassiveMode] Extracted {len(actions)} actions from state")
                    if not isinstance(actions, list):
                        return {"error": "browser-use passive mode enabled but actions is not a list"}

                    browser_session = await _get_or_create_browser_session(mainwin, state=state, calling_agent_id=calling_agent_id)
                    if not browser_session:
                        return {"error": "browser-use passive mode: failed to acquire browser session"}

                    if not _is_session_started(browser_session):
                        import asyncio
                        task = asyncio.create_task(browser_session.start())
                        await task

                    # Reuse PassiveAgent across loop iterations (keyed by browser_session id)
                    global _cached_passive_agents
                    session_id = id(browser_session)
                    if session_id in _cached_passive_agents:
                        passive_agent = _cached_passive_agents[session_id]
                        logger.debug(f"[PassiveMode] Reusing cached PassiveAgent for session {session_id}")
                    else:
                        passive_agent = PassiveAgent(
                            browser_session=browser_session,
                            tools=custom_controller,
                            privacy_enabled=True,
                        )
                        # Transfer saved focus target from previous session
                        if _last_known_focus_target_id:
                            passive_agent._last_focus_target_id = _last_known_focus_target_id
                            logger.info(f"[PassiveMode] Transferred focus target ...{_last_known_focus_target_id[-4:]} to new PassiveAgent")
                        _cached_passive_agents[session_id] = passive_agent
                        logger.info(f"[PassiveMode] Created new PassiveAgent for session {session_id}")

                    # Get passive_command from state.attributes for run_id/step_id
                    passive_cmd = None
                    include_screenshot = False
                    stop_on_error = True
                    if isinstance(state, dict):
                        attrs = state.get("attributes", {})
                        passive_cmd = attrs.get("passive_command")
                        if isinstance(passive_cmd, dict):
                            include_screenshot = bool(passive_cmd.get("include_screenshot", False))
                            stop_on_error = bool(passive_cmd.get("stop_on_error", True))

                    payload = None
                    exec_error = None
                    try:
                        payload = await passive_agent.execute_actions(
                            actions=actions,
                            stop_on_error=stop_on_error,
                            include_screenshot=include_screenshot,
                        )
                        # Update closure-level focus target after successful execution
                        if hasattr(passive_agent, '_last_focus_target_id') and passive_agent._last_focus_target_id:
                            _last_known_focus_target_ids[_browser_scope_key] = passive_agent._last_focus_target_id
                    except Exception as e:
                        exec_error = e
                        err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNodePassive")
                        logger.error(err_msg)
                        send_skill_editor_log("error", err_msg)
                        payload = {"error": str(err_msg), "errors": [str(err_msg)]}

                    # Publish result back to cloud if we have passive_command info
                    # This happens even on error so cloud worker knows what happened
                    if passive_cmd and mainwin:
                        try:
                            from agent.ec_skills.browser_use_extension.passive_utils import publish_step_result
                            from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserStepResult
                            
                            run_id = passive_cmd.get("run_id", "")
                            step_id = passive_cmd.get("step_id", "")
                            
                            if run_id and step_id:
                                result = PassiveBrowserStepResult(
                                    run_id=run_id,
                                    step_id=step_id,
                                    ok=not bool(payload.get("errors")),
                                    elapsed_ms=int(payload.get("elapsed_ms") or 0),
                                    actions=payload.get("actions") or [],
                                    action_results=payload.get("action_results") or [],
                                    errors=payload.get("errors") or [],
                                    browser=payload.get("browser") or {},
                                )
                                
                                http_endpoint = mainwin.getWanApiEndpoint()
                                auth_token = mainwin.get_auth_token()
                                client_id = mainwin.getAcctSiteID()
                                logger.info(f"[BrowserAutomation] publish_step_result: client_id={client_id}, run_id={run_id}, step_id={step_id}")
                                
                                await publish_step_result(result, http_endpoint, auth_token, client_id)
                                logger.info(f"[BrowserAutomation] Published passive step result: run_id={run_id}, step_id={step_id}")
                                send_skill_editor_log("log", f"[BrowserAutomation] Published passive step result to cloud")
                        except Exception as pub_err:
                            logger.error(f"[BrowserAutomation] Failed to publish passive step result: {pub_err}")
                            send_skill_editor_log("warning", f"[BrowserAutomation] Failed to publish result to cloud: {pub_err}")

                    # Return error if execute_actions failed
                    if exec_error:
                        return {"error": str(payload.get("error", str(exec_error)))}
                    
                    # Strip screenshot_base64 from browser dict before returning to langgraph state
                    # to keep state history logs clean (no huge base64 blobs).
                    if isinstance(payload.get("browser"), dict):
                        payload["browser"].pop("screenshot_base64", None)

                    logger.info(f"[PassiveMode] Browser automation node returning. Workflow should continue to loop condition check.")
                    send_skill_editor_log("log", f"[PassiveMode] Browser automation complete. Loop should continue.")
                    return {"passive": True, **payload}
                except Exception as e:
                    err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNodePassive")
                    logger.error(err_msg)
                    send_skill_editor_log("error", err_msg)
                    return {"error": str(err_msg)}

            # Prefer privacy-aware wrapper if available; fall back to vanilla Agent.
            # Use PrivacyAgent only if privacy_strategy is not 'none'
            AgentClass = BUAgent
            use_privacy_agent = privacy_strategy_setting != 'none'
            
            if use_privacy_agent:
                try:
                    from agent.ec_skills.browser_use_extension.privacy_agent import PrivacyAgent
                    AgentClass = PrivacyAgent
                    logger.info(f"[BrowserAutomation] Using PrivacyAgent for browser-use (strategy={privacy_strategy_setting})")
                except Exception as _privacy_import_exc:
                    logger.info(f"[BrowserAutomation] PrivacyAgent not available, using browser_use.Agent ({_privacy_import_exc})")
                    use_privacy_agent = False
            else:
                logger.info("[BrowserAutomation] Privacy strategy is 'none', using standard browser_use.Agent")

            # Import LLM creation utilities
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm, create_browser_use_llm_by_provider_type
            
            # CLOUD AGENT MODE: Handle hybrid_cloud/full_cloud before checking for mainwin
            # In cloud mode, we create LLM from node config + environment variables
            if cloud_agent_enabled:
                try:
                    import uuid
                    from agent.ec_skills.browser_use_extension.cloud_agent import CloudAgent, make_default_cloud_transport_from_env
                    from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
                    
                    logger.info(f"[BrowserAutomation] Running in CLOUD AGENT mode (hybrid_cloud/full_cloud)")
                    send_skill_editor_log("log", f"[BrowserAutomation] Starting cloud agent mode")
                    
                    # Create LLM: proxy > node-specified provider > default from Settings
                    llm = None

                    # --- Lambda proxy shortcut (cloud agent) ---
                    if _should_use_proxy(inputs):
                        proxy_cfg = _get_proxy_config()
                        if proxy_cfg:
                            from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy
                            _proxy_provider = node_llm_provider or 'openai'
                            _proxy_model = node_model_name or 'gpt-4o'
                            llm = ChatLambdaProxy(
                                model=_proxy_model,
                                provider_name=_proxy_provider,
                                user_id=proxy_cfg['user_id'],
                                lambda_endpoint=proxy_cfg['endpoint'],
                                auth_token=proxy_cfg['auth_token'],
                            )
                            logger.info(f"[BrowserAutomation] Using Lambda proxy (cloud): {_proxy_provider}/{_proxy_model}")
                            send_skill_editor_log("log", f"[BrowserAutomation] LLM via Lambda proxy: {_proxy_provider}/{_proxy_model}")

                    if llm is None and node_llm_provider:
                        # Node specified provider - use it and ONLY it (no fallback allowed)
                        provider_lower = node_llm_provider.lower()
                        selected_model_name = node_model_name
                        if not selected_model_name:
                            try:
                                from app_context import AppContext
                                mainwin_cfg = AppContext.get_main_window()
                                if mainwin_cfg and hasattr(mainwin_cfg, 'config_manager'):
                                    provider_cfg = mainwin_cfg.config_manager.llm_manager.get_provider(node_llm_provider)
                                    if provider_cfg:
                                        selected_model_name = provider_cfg.get('default_model')
                            except Exception:
                                pass
                        if not selected_model_name:
                            raise RuntimeError(f"[BrowserAutomation] Node specified provider '{node_llm_provider}' but model_name is missing")
                        
                        # Get API key from environment variables
                        api_key = None
                        base_url = None
                        
                        if provider_lower == 'openai':
                            api_key = os.environ.get('OPENAI_API_KEY', '').strip()
                            base_url = os.environ.get('OPENAI_BASE_URL', '').strip() or None
                        elif provider_lower == 'anthropic':
                            api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
                        elif provider_lower == 'deepseek':
                            api_key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
                            base_url = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').strip()
                        elif provider_lower in ('azure', 'azure_openai'):
                            api_key = os.environ.get('AZURE_OPENAI_API_KEY', '').strip()
                            base_url = os.environ.get('AZURE_OPENAI_ENDPOINT', '').strip() or None
                        else:
                            api_key = os.environ.get('LLM_API_KEY', '').strip()
                        
                        if not api_key and provider_lower not in ('ollama',):
                            raise RuntimeError(f"[BrowserAutomation] Node specified provider '{node_llm_provider}' but no API key found in environment. Please set the required API key.")
                        
                        llm = create_browser_use_llm_by_provider_type(
                            provider_type=provider_lower,
                            model_name=selected_model_name,
                            api_key=api_key,
                            base_url=base_url,
                            mainwin=None
                        )
                        
                        if not llm:
                            raise RuntimeError(f"[BrowserAutomation] Failed to create LLM for node-specified provider '{node_llm_provider}'")
                        
                        logger.info(f"[BrowserAutomation] Created LLM from node config: provider={node_llm_provider}, model={selected_model_name}")
                        send_skill_editor_log("log", f"[BrowserAutomation] LLM created: {node_llm_provider}/{selected_model_name}")

                    if llm is None:
                        # Node did NOT specify provider and no proxy - use default from Settings
                        from app_context import AppContext
                        ctx = AppContext.get_instance()
                        mainwin_ctx = ctx.get_main_window()
                        
                        if not mainwin_ctx or not hasattr(mainwin_ctx, 'config_manager'):
                            raise RuntimeError("[BrowserAutomation] Cannot access Settings to get default LLM configuration")
                        
                        # Use unified method to get default LLM config
                        llm_config = mainwin_ctx.config_manager.llm_manager.get_default_llm_config()
                        provider_dict = llm_config['provider_dict']
                        
                        from agent.ec_skills.llm_utils.llm_utils import extract_provider_config
                        provider_type, model_name_default, api_key, base_url = extract_provider_config(provider_dict)
                        
                        if not api_key and provider_type not in ('ollama',):
                            raise RuntimeError(f"[BrowserAutomation] No API key configured for default LLM provider '{llm_config['provider_id']}'")
                        
                        llm = create_browser_use_llm_by_provider_type(
                            provider_type=provider_type,
                            model_name=node_model_name or llm_config['model_name'],
                            api_key=api_key,
                            base_url=base_url,
                            mainwin=None
                        )
                        
                        if not llm:
                            raise RuntimeError(f"[BrowserAutomation] Failed to create LLM instance for default provider '{llm_config['provider_id']}'")
                        
                        logger.info(f"[BrowserAutomation] Created LLM from Settings: {llm_config['provider_id']}, model: {llm_config['model_name']}")
                        send_skill_editor_log("log", f"[BrowserAutomation] Using default LLM: {llm_config['provider_id']}")
                    
                    # Create transport for cloud communication
                    # First, try to get the global transport registered by cloud worker
                    transport = None
                    try:
                        from agent.cloud_worker.worker_main import get_global_passive_transport
                        transport = get_global_passive_transport()
                        if transport:
                            logger.info(f"[BrowserAutomation] Using global CloudWorkerPassiveTransport from cloud worker")
                            send_skill_editor_log("log", f"[BrowserAutomation] Using cloud worker passive transport")
                        else:
                            logger.warning("[BrowserAutomation] get_global_passive_transport() returned None — was set_global_passive_transport() called?")
                            send_skill_editor_log("log", "[BrowserAutomation] ⚠️ Global passive transport is None, falling back to env-based transport")
                    except ImportError as ie:
                        logger.warning(f"[BrowserAutomation] Could not import get_global_passive_transport: {ie}")
                    except Exception as ex:
                        logger.warning(f"[BrowserAutomation] Error getting global transport: {ex}")
                    
                    # Fall back to creating transport from environment
                    if not transport:
                        transport = make_default_cloud_transport_from_env()
                        logger.info(f"[BrowserAutomation] Created transport from environment")
                    
                    # Get run_id from state - MUST match the run_id used by PassiveStepResultListener
                    # The listener is created with the session/chat_id as run_id, so we must use that
                    run_id = None
                    browser_use_run_id_explicit = None
                    state_dev_mode = False
                    try:
                        if isinstance(state, dict):
                            # First priority: explicit browser_use_run_id
                            browser_use_run_id_explicit = state.get("browser_use_run_id")
                            run_id = browser_use_run_id_explicit
                            # Detect dev mode if present in state
                            md = state.get("metadata")
                            attrs = state.get("attributes")
                            state_dev_mode = bool(
                                state.get("dev_mode")
                                or (md.get("dev_mode") if isinstance(md, dict) else False)
                                or (attrs.get("dev_mode") if isinstance(attrs, dict) else False)
                            )
                            if not run_id:
                                attrs = state.get("attributes", {})
                                # Second priority: chat_id (session ID) - this matches PassiveStepResultListener
                                run_id = attrs.get("chat_id")
                            if not run_id:
                                # Third priority: other run_id fields
                                attrs = state.get("attributes", {})
                                run_id = attrs.get("run_id") or attrs.get("passive_run_id")
                            if not run_id:
                                # Fourth priority: metadata.run_id (used by some runners)
                                md = state.get("metadata", {})
                                if isinstance(md, dict):
                                    run_id = md.get("run_id") or md.get("passive_run_id")
                    except Exception:
                        run_id = None

                    # Skill Editor / dev mode: local passive subscriber defaults to 0123456789
                    # unless EC_BROWSER_PASSIVE_RUN_ID is explicitly set.
                    try:
                        from config.app_settings import app_settings
                        dev_mode = bool(state_dev_mode or getattr(app_settings, "is_dev_mode", False))
                    except Exception:
                        dev_mode = bool(state_dev_mode)

                    if dev_mode and not browser_use_run_id_explicit:
                        dev_run_id = (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
                        run_id = dev_run_id or "0123456789"

                    if not isinstance(run_id, str) or not run_id.strip():
                        run_id = (
                            (os.environ.get("ECAN_RUN_ID") or "").strip()
                            or (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
                        )
                    
                    if not isinstance(run_id, str) or not run_id.strip():
                        run_id = uuid.uuid4().hex
                    
                    logger.debug(f"[BrowserAutomation] Cloud mode run_id={run_id}")
                    
                    # Get agent/skill/node IDs
                    cloud_agent_id = None
                    try:
                        if isinstance(state, dict):
                            attrs = state.get("attributes", {})
                            cloud_agent_id = attrs.get("agent_id")
                    except Exception:
                        pass
                    
                    # Get acct_site_id: prefer mainwin.getAcctSiteID() for hybrid runs launched from local client
                    # For cloud worker, get it from the transport's client_id
                    acct_site_id = None
                    if mainwin and hasattr(mainwin, 'getAcctSiteID'):
                        try:
                            acct_site_id = mainwin.getAcctSiteID()
                        except Exception:
                            pass
                    if not acct_site_id and transport and hasattr(transport, 'client_id'):
                        # Cloud worker case: transport has the client_id from passive_client_id
                        acct_site_id = transport.client_id
                    if not acct_site_id:
                        acct_site_id = os.environ.get('EC_ACCT_SITE_ID', '').strip() or None
                    
                    # Build agent kwargs
                    agent_kwargs = {
                        'use_vision': node_use_vision,
                        'use_thinking': node_use_thinking,
                        'use_judge': enable_judge_setting,
                    }
                    if not node_use_thinking:
                        agent_kwargs['extend_system_message'] = THINKING_SUPPRESSION_INSTRUCTION.strip()
                    
                    controller = custom_controller
                    
                    # Build combined_task from prompts (same logic as non-cloud path)
                    task_instructions = task_text or system_prompt_content or inline_system_prompt or "You are a helpful browser automation agent."
                    combined_task = f"System Instructions:\n{task_instructions}"
                    
                    agent = CloudAgent(
                        task=task,  # Use the task parameter passed to _run_browser_use
                        llm=llm,
                        controller=controller,
                        transport=transport,
                        run_id=run_id,
                        acct_site_id=acct_site_id,
                        agent_id=cloud_agent_id,
                        skill_id=skill_name,
                        node_id=node_name,
                        **agent_kwargs,
                    )

                    try:
                        setattr(agent, "_ecan_skill_name", skill_name)
                        setattr(agent, "_ecan_node_id", node_name)
                        setattr(agent, "_ecan_owner", owner)
                    except Exception:
                        pass
                    
                    # Register agent instance for extension tools
                    from agent.ec_skills.browser_use_extension.extension_tools_service import set_current_agent
                    set_current_agent(agent)

                    # Log all tools the LLM will see in its system prompt
                    all_tools_description = agent.tools.registry.get_prompt_description(page_url=None)
                    logger.info(f"[Browser-Use] LLM sees {len(agent.tools.registry.actions)} total actions in system prompt")
                    logger.debug(f"[Browser-Use] Full tool list for LLM:\n{all_tools_description}")

                    logger.info(f"[BrowserAutomation] Starting CloudAgent run_id={run_id}")
                    send_skill_editor_log("log", f"[BrowserAutomation] CloudAgent starting, run_id={run_id}")
                    
                    history = await agent.run()
                    # Log step budget usage
                    try:
                        _ag_st = getattr(agent, 'state', None)
                        _ag_settings = getattr(agent, 'settings', None)
                        _steps_used = getattr(_ag_st, 'n_steps', '?') if _ag_st else '?'
                        _max_steps = getattr(_ag_settings, 'max_steps', '?') if _ag_settings else '?'
                        _consec_fail = getattr(_ag_st, 'consecutive_failures', '?') if _ag_st else '?'
                        _max_fail = getattr(_ag_settings, 'max_failures', '?') if _ag_settings else '?'
                        _stopped = getattr(_ag_st, 'stopped', '?') if _ag_st else '?'
                        _ao_is_done = agent.AgentOutput is getattr(agent, 'DoneAgentOutput', None) if hasattr(agent, 'AgentOutput') else '?'
                        logger.info(
                            f"[BrowserAutomation] CloudAgent run finished: "
                            f"steps={_steps_used}/{_max_steps}, "
                            f"failures={_consec_fail}/{_max_fail}, "
                            f"stopped={_stopped}, "
                            f"AgentOutput_clobbered={_ao_is_done}"
                        )
                    except Exception:
                        pass
                    final = history.final_result() if hasattr(history, 'final_result') else None
                    _log_browser_use_result_summary(history, skill_name=skill_name, node_name=node_name)

                    logger.info(f"[BrowserAutomation] CloudAgent completed")
                    send_skill_editor_log("log", f"[BrowserAutomation] CloudAgent completed")
                    
                    return {
                        "cloud": True,
                        "client_assisted_cloud": True,
                        "mode": "client_assisted_cloud",
                        "run_id": run_id,
                        "final": final,
                        "history": str(history),
                    }
                except Exception as e:
                    err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNodeCloudAgent")
                    logger.error(err_msg)
                    send_skill_editor_log("error", err_msg)
                    return {"error": str(err_msg)}

            # LOCAL EXECUTION MODES: Require mainwin
            if not mainwin:
                raise ValueError("mainwin is required. Must use mainwin configuration for browser_use LLM.")

            # Use node-specific LLM provider/model if configured, otherwise fall back to mainwin default
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm, create_browser_use_llm_by_provider_type

            llm = None

            # --- Lambda proxy shortcut (local) ---
            if _should_use_proxy(inputs):
                proxy_cfg = _get_proxy_config()
                if proxy_cfg:
                    from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy
                    _proxy_provider = node_llm_provider or 'openai'
                    _proxy_model = node_model_name or 'gpt-4o'
                    llm = ChatLambdaProxy(
                        model=_proxy_model,
                        provider_name=_proxy_provider,
                        user_id=proxy_cfg['user_id'],
                        lambda_endpoint=proxy_cfg['endpoint'],
                        auth_token=proxy_cfg['auth_token'],
                    )
                    _masked_token = (proxy_cfg['auth_token'][:20] + '...') if len(proxy_cfg.get('auth_token', '')) > 20 else proxy_cfg.get('auth_token', '(empty)')
                    logger.info(
                        f"[BrowserAutomation] Using Lambda proxy (local): {_proxy_provider}/{_proxy_model}, "
                        f"endpoint={proxy_cfg['endpoint']}, user={proxy_cfg['user_id']}, token={_masked_token}"
                    )

            if llm is None and node_llm_provider and node_model_name:
                # Node editor has specific provider/model selected - use those (no fallback)
                logger.info(f"[BrowserAutomation] Using node-specific LLM: provider={node_llm_provider}, model={node_model_name}")
                
                # Get API key and base_url from mainwin's config for this provider
                try:
                    from agent.ec_skills.llm_utils.llm_utils import extract_provider_config
                    
                    config_manager = mainwin.config_manager
                    provider_dict = config_manager.llm_manager.get_provider(node_llm_provider)
                    logger.info(f"[BrowserAutomation] get_provider('{node_llm_provider}') returned: {provider_dict is not None}")
                    
                    if provider_dict:
                        logger.debug(f"[BrowserAutomation] provider_dict keys: {list(provider_dict.keys())}")
                        
                        # Use extract_provider_config to get configuration
                        # Pass node_model_name to ensure node-specified model takes priority over global default
                        config = extract_provider_config(provider_dict, config_manager=config_manager, node_model_name=node_model_name)
                        logger.info(f"[BrowserAutomation] extract_provider_config returned: {config is not None}")
                        logger.debug(f"[BrowserAutomation] config keys: {list(config.keys()) if config else 'None'}")
                        
                        # Get api_key and base_url from config
                        # extract_provider_config already ensures these are not None
                        api_key = config.get('api_key')
                        base_url = config.get('base_url')
                        
                        logger.debug(f"[BrowserAutomation] api_key: {'***' if api_key else 'None'}, base_url: {base_url}")
                        
                        # Use standard provider_type from config (not display name)
                        # This ensures we pass the correct provider ID (e.g., 'dashscope' not 'qwen (dashscope)')
                        provider_type_id = config.get('provider_type')
                        logger.debug(f"[BrowserAutomation] Using provider_type: {provider_type_id} (from config, not display name: {node_llm_provider})")
                        
                        # Use node-selected model, not the default from config
                        llm = create_browser_use_llm_by_provider_type(
                            provider_type=provider_type_id,
                            model_name=node_model_name,
                            api_key=api_key,
                            base_url=base_url,
                            mainwin=mainwin
                        )
                        
                        if llm is None:
                            # Don't fallback - raise error to surface the problem
                            raise ValueError(
                                f"Failed to create LLM with provider '{provider_type_id}' (display: {node_llm_provider}), "
                                f"model '{node_model_name}'. Check API key and base_url configuration."
                            )
                        
                        logger.info(f"[BrowserAutomation] ✅ Created LLM with node settings: provider={node_llm_provider}, model={node_model_name}")
                    else:
                        error_msg = f"Provider '{node_llm_provider}' not found in config. Please check provider name in node settings."
                        logger.error(f"[BrowserAutomation] ❌ {error_msg}")
                        raise ValueError(error_msg)
                except Exception as e:
                    error_msg = (
                        f"Failed to create LLM with node settings:\n"
                        f"  Provider: {node_llm_provider}\n"
                        f"  Model: {node_model_name}\n"
                        f"  Error: {str(e)}\n\n"
                        f"Please check:\n"
                        f"  1. Provider name is correct in node settings\n"
                        f"  2. Model name is correct and belongs to the provider\n"
                        f"  3. API key is configured in Settings > LLM Management\n"
                        f"  4. Base URL is correct (if using local/custom provider)"
                    )
                    logger.error(f"[BrowserAutomation] ❌ {error_msg}")
                    raise ValueError(error_msg) from e

            if llm is None:
                # No node-specific settings and no proxy - use global default LLM
                logger.info("[BrowserAutomation] No node-specific LLM settings, using global default LLM")
                try:
                    llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
                    if llm:
                        logger.info("[BrowserAutomation] ✅ Using global default LLM")
                    else:
                        error_msg = (
                            "Failed to create LLM from global default settings.\n\n"
                            "Please configure a default LLM in Settings > LLM Management:\n"
                            "  1. Select a provider (OpenAI, DeepSeek, Qwen, etc.)\n"
                            "  2. Enter API key\n"
                            "  3. Set as default provider"
                        )
                        logger.error(f"[BrowserAutomation] ❌ {error_msg}")
                        raise ValueError(error_msg)
                except Exception as e:
                    error_msg = (
                        f"Failed to create LLM from global default settings:\n"
                        f"  Error: {str(e)}\n\n"
                        f"Please check Settings > LLM Management:\n"
                        f"  1. Verify default provider is set\n"
                        f"  2. Verify API key is configured\n"
                        f"  3. Verify base URL is correct (if using local provider)"
                    )
                    logger.error(f"[BrowserAutomation] ❌ {error_msg}")
                    raise ValueError(error_msg) from e
            
            # Final validation
            if not llm:
                error_msg = "LLM creation failed. This should not happen - please report this bug."
                logger.error(f"[BrowserAutomation] ? {error_msg}")
                raise ValueError(error_msg)

            try:
                setattr(llm, "_ec_token_context", {
                    "skill_name": skill_name,
                    "node_name": node_name,
                    "source_id": f"{skill_name}::{node_name}",
                    "source_name": f"{skill_name}::{node_name}",
                    "task_id": (state.get("attributes") or {}).get("task_id") if isinstance(state, dict) else None,
                    "run_id": state.get("run_id") if isinstance(state, dict) else None,
                    "session_id": (
                        state.get("session_id")
                        or state.get("chat_id")
                        or (state.get("attributes", {}) or {}).get("sessionId")
                    ) if isinstance(state, dict) else None,
                    "browser_scope_key": _browser_scope_key,
                    "node_model_name": node_model_name,
                    "node_llm_provider": node_llm_provider,
                })
            except Exception as _ctx_err:
                logger.debug(f"[BrowserAutomation] Failed to attach token context to llm: {_ctx_err}")

            controller = custom_controller
                        
            # Use unified agent configuration for consistency across local and cloud modes
            from agent.ec_skills.browser_use_extension.agent_config import get_agent_kwargs_with_compaction
            
            # Data-driven DOM size reduction via node editor settings.
            # domLimit (chars) caps max_clickable_elements_length; domFocusSelector
            # prunes non-matching elements via CDP before DOM extraction (see below).
            if node_dom_limit:
                logger.info(
                    f"[BrowserAutomation] DOM limit set to "
                    f"{node_dom_limit} chars (was default ~18-25K)"
                )
            if node_dom_focus_selector:
                logger.info(
                    f"[BrowserAutomation] DOM focus selector: {node_dom_focus_selector!r}"
                )

            agent_kwargs = get_agent_kwargs_with_compaction(
                use_vision=node_use_vision,
                use_thinking=node_use_thinking,
                use_judge=enable_judge_setting,
                llm=llm,  # Pass LLM to auto-detect context_length for adaptive compaction
                max_actions_per_step=node_max_actions_per_step,  # Performance optimization
                **({'max_clickable_elements_length': node_dom_limit} if node_dom_limit else {}),
            )

            # Log the actual message_compaction settings (use INFO level for visibility)
            if 'message_compaction' in agent_kwargs:
                mc = agent_kwargs['message_compaction']
                logger.info(
                    f"[BrowserAutomation] ⚡ Agent Config: "
                    f"compaction=enabled={mc.enabled}, every={mc.compact_every_n_steps}steps, "
                    f"trigger={mc.trigger_char_count}chars, keep={mc.keep_last_items}items, "
                    f"summary={mc.summary_max_chars}chars, "
                    f"max_clickable={agent_kwargs.get('max_clickable_elements_length', 'default')}, "
                    f"max_input_tokens={agent_kwargs.get('max_input_tokens', 'N/A')}, "
                    f"max_actions_per_step={agent_kwargs.get('max_actions_per_step', 'default')}"
                )
            else:
                logger.warning("[BrowserAutomation] ⚠️ No message_compaction in agent_kwargs - history may grow unbounded!")
            
            # Check if extensions should be disabled (dev mode)
            # In dev mode: default to disabled (avoid network timeout)
            from config.app_settings import app_settings
            disable_extensions = app_settings.is_dev_mode
            
            # Create browser profile with extensions control.
            # Use persistent user_data_dir for all browser modes to preserve login state (cookies, sessions).
            # This ensures users don't need to re-login every time they run a skill.
            profile_settings = _get_browser_profile_settings(node_profile)
            
            # Auto-assign persistent user_data_dir if not explicitly configured
            _bp_user_data_dir = profile_settings.get('user_data_dir', '') if profile_settings else ''
            if not _bp_user_data_dir:
                from utils.user_path_helper import ensure_user_data_dir
                import re as _re
                _bp_id = profile_settings.get('id') or profile_settings.get('name') or node_profile or 'default'
                _bp_safe_id = _re.sub(r'[^\w\-]', '_', str(_bp_id))
                _bp_user_data_dir = ensure_user_data_dir(subdir=os.path.join('browser_profiles', _bp_safe_id))
                logger.info(f"[BrowserAutomation] Auto-assigned user_data_dir: {_bp_user_data_dir}")
            
            # Clean stale lock files before creating browser profile
            # This prevents startup failures from previous abnormal exits
            from agent.ec_skills.browser_use_extension.profile_lock_cleaner import ensure_profile_unlocked
            ensure_profile_unlocked(_bp_user_data_dir, auto_clean=True)
            
            # Create browser profile with persistent storage for all modes
            keep_browser_alive = bool(_event_monitor_configs)
            browser_profile = BrowserProfile(
                enable_default_extensions=not disable_extensions,
                user_data_dir=_bp_user_data_dir,
                keep_alive=keep_browser_alive or None,
            )
            
            if browser_type_setting == 'new chromium':
                logger.info("[BrowserAutomation] Using persistent Chromium profile for new chromium mode")
            else:
                logger.info("[BrowserAutomation] Using persistent profile for existing-browser/CDP mode")
            logger.info(f"[BrowserAutomation] Extensions {'disabled (dev mode)' if disable_extensions else 'enabled (production mode)'}")
            if keep_browser_alive:
                logger.info("[BrowserAutomation] Browser profile keep_alive enabled for event-monitored workflow")
           
            if browser_profile:
                agent_kwargs['browser_profile'] = browser_profile

            _agent_ref: dict[str, Any] = {}
            if _event_monitor_configs and event_monitor_done_policy == "stop":
                async def _on_browser_done(_history):
                    try:
                        agent_obj = _agent_ref.get("agent")
                        session_obj = getattr(agent_obj, "browser_session", None) if agent_obj else None
                        if not session_obj:
                            return
                        from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability
                        capability = get_event_monitor_capability(session_obj, create=False)
                        if capability:
                            await capability.stop()
                            logger.info("[BrowserAutomation] Stopped session event monitors on done()")
                    except Exception as _done_monitor_err:
                        logger.warning(f"[BrowserAutomation] Failed to stop monitors on done(): {_done_monitor_err}")

                agent_kwargs["register_done_callback"] = _on_browser_done

            # Step progress callback: send intermediate update_run_stat so the
            # skill editor shows real-time progress during long browser automation.
            def _on_browser_step(browser_state_summary, model_output, step_number):
                """Sync callback invoked after each browser-use step."""
                try:
                    from agent.cloud_worker.cloud_logger import is_cloud_mode
                    if is_cloud_mode():
                        return
                    from gui.ipc.api import IPCAPI
                    import time as _t
                    ipc = IPCAPI.get_instance()
                    # Build a concise step summary from model_output actions
                    action_summary = ""
                    try:
                        actions = getattr(model_output, "action", None)
                        if actions and isinstance(actions, list):
                            names = [getattr(a, "name", "") or type(a).__name__ for a in actions[:3]]
                            action_summary = ", ".join(n for n in names if n)
                    except Exception:
                        pass
                    step_label = f"step {step_number}" + (f" ({action_summary})" if action_summary else "")
                    send_skill_editor_log("log", f"[BrowserAutomation] 📍 {node_name}: {step_label}")
                    ipc.update_run_stat(
                        agent_task_id=run_id or "0123456789",
                        current_node=node_name,
                        status="running",
                        langgraph_state={"_browser_step": step_number, "_browser_action": action_summary},
                        timestamp=int(_t.time() * 1000),
                    )
                except Exception:
                    pass

            agent_kwargs["register_new_step_callback"] = _on_browser_step

            # Populate available_file_paths so the agent can upload local images.
            # Extract product_dir from state (set by init_params / analyze_product),
            # then allowlist every image file in that directory.
            try:
                _product_dir_for_files: str | None = None
                if isinstance(state, dict):
                    # 1. Direct from prompt_refs (fastest)
                    _pr = state.get("prompt_refs") or {}
                    _product_dir_for_files = _pr.get("product_dir") or None
                    if not _product_dir_for_files:
                        # 2. Scan tool_result entries (init_params / analyze_product output)
                        _tr = state.get("tool_result") or {}
                        for _node_out in _tr.values():
                            if not isinstance(_node_out, dict):
                                continue
                            _pd = _node_out.get("product_dir")
                            if _pd and isinstance(_pd, str):
                                _product_dir_for_files = _pd
                                break
                            # Try parsing "final" / "content" as JSON
                            for _fk in ("final", "content", "extracted_content"):
                                _fv = _node_out.get(_fk)
                                if not isinstance(_fv, str):
                                    continue
                                try:
                                    import json as _json_afp
                                    _parsed_afp = _json_afp.loads(_fv)
                                    if isinstance(_parsed_afp, dict) and _parsed_afp.get("product_dir"):
                                        _product_dir_for_files = str(_parsed_afp["product_dir"])
                                        break
                                except Exception:
                                    pass
                            if _product_dir_for_files:
                                break

                if _product_dir_for_files and os.path.isdir(_product_dir_for_files):
                    _image_exts = {
                        ".jpg", ".jpeg", ".png", ".webp",
                        ".gif", ".bmp", ".tiff", ".tif",
                        ".heic", ".heif",
                    }
                    import re as _re_uuid
                    # UUID pattern: 8-4-4-4-12 hex chars with hyphens (e.g. from research downloads)
                    _UUID_PAT = _re_uuid.compile(
                        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.',
                        _re_uuid.IGNORECASE,
                    )
                    _file_paths = [
                        os.path.join(_product_dir_for_files, _fname)
                        for _fname in os.listdir(_product_dir_for_files)
                        if (
                            os.path.splitext(_fname.lower())[1] in _image_exts
                            and not _UUID_PAT.match(_fname)  # exclude research-downloaded UUID images
                        )
                    ]
                    if _file_paths:
                        agent_kwargs["available_file_paths"] = _file_paths
                        logger.info(
                            f"[BrowserAutomation] available_file_paths: "
                            f"{len(_file_paths)} image(s) from {_product_dir_for_files}"
                        )
                    else:
                        logger.debug(
                            f"[BrowserAutomation] No image files found in product_dir={_product_dir_for_files}"
                        )
                else:
                    logger.debug(
                        f"[BrowserAutomation] product_dir not found in state; "
                        f"skipping available_file_paths ({_product_dir_for_files!r})"
                    )
            except Exception as _afp_err:
                logger.warning(f"[BrowserAutomation] Failed to set available_file_paths: {_afp_err}")

            logger.info(f"[BrowserAutomation] Agent kwargs: {agent_kwargs}")
            logger.debug("[BROWSER USE]Agent task:", task)

            # Apply extract patch based on max_input_tokens from agent config
            # This ensures extract tool respects the model's context length and prevents token overflow
            # The patch reserves ~24K tokens for system prompt, history, and overhead
            if 'max_input_tokens' in agent_kwargs:
                try:
                    # In development mode, reload the module to ensure we use the latest code
                    # This helps during development when the patch code is being modified
                    import sys
                    if 'agent.ec_skills.browser_use_extension.extract_patch' in sys.modules:
                        import importlib
                        extract_patch_module = sys.modules['agent.ec_skills.browser_use_extension.extract_patch']
                        importlib.reload(extract_patch_module)
                        logger.debug("[BrowserAutomation] 🔄 Reloaded extract_patch module (dev mode)")
                    
                    from agent.ec_skills.browser_use_extension.extract_patch import patch_extract_max_char_limit
                    
                    # Apply patch with current model's token capacity
                    result = patch_extract_max_char_limit(agent_kwargs['max_input_tokens'])
                    
                    if result:
                        logger.debug(
                            f"[BrowserAutomation] ✅ Extract patch applied/verified "
                            f"(max_input_tokens={agent_kwargs['max_input_tokens']:,})"
                        )
                    else:
                        logger.warning("[BrowserAutomation] ⚠️ Extract patch returned False")
                        
                except Exception as e:
                    logger.error(f"[BrowserAutomation] ❌ Failed to apply extract patch: {e}", exc_info=True)


            # Optional: Cloud LLM mode for browser-use via PrivacyAgent (feature flagged)
            # Only pass cloud kwargs when using PrivacyAgent (browser_use.Agent won't accept them)).
            try:
                cloud_enabled = os.environ.get("EC_BROWSER_USE_CLOUD_LLM", "").strip().lower() in {"1", "true", "yes", "on"}
            except Exception:
                cloud_enabled = False

            if cloud_enabled and use_privacy_agent:
                try:
                    cloud_endpoint = None
                    try:
                        cloud_endpoint = mainwin.getWanApiEndpoint()
                    except Exception:
                        cloud_endpoint = None

                    cloud_agent_id = calling_agent_id or getattr(mainwin, 'current_agent_id', None)
                    agent_kwargs.update(
                        {
                            "cloud_llm_enabled": True,
                            "cloud_session": getattr(mainwin, "session", None),
                            "cloud_token": mainwin.get_auth_token(),
                            "cloud_endpoint": cloud_endpoint,
                            "cloud_acct_site_id": mainwin.getAcctSiteID(),
                            "cloud_agent_id": cloud_agent_id,
                            "cloud_skill_id": skill_name,
                            "cloud_node_id": node_name,
                            "cloud_system_prompt_id": system_prompt_id,
                            "cloud_user_prompt_id": user_prompt_id,
                            "cloud_work_type": "browser_use_next_action",
                        }
                    )
                    logger.info(f"[BrowserAutomation] Cloud LLM enabled for PrivacyAgent (agent_id={cloud_agent_id})")
                except Exception as _cloud_kwargs_exc:
                    logger.warning(f"[BrowserAutomation] Failed to configure cloud LLM mode: {_cloud_kwargs_exc}")
            
            # Browser session creation logic:
            # - "new chromium": browser-use creates its own browser (no BrowserManager needed)
            # - Other types: connect to existing browser via CDP (requires BrowserManager)
            
            if browser_type_setting == 'new chromium':
                # Mode 1: Let browser-use create and manage its own Chromium browser
                logger.info("[BrowserAutomation] Mode: new chromium - browser-use will create browser")
                _bu_scope_key = _resolve_browser_scope_key(state)
                _cached_bu_agent = _cached_bu_agents.get(_bu_scope_key)
                if _cached_bu_agent is not None:
                    _reset_bu_agent_for_next_round(_cached_bu_agent, loop_history_mode, task)
                    agent = _cached_bu_agent
                    logger.info(f"[BrowserAutomation] Reusing cached browser-use agent (scope={_bu_scope_key}, mode={loop_history_mode})")
                else:
                    agent = AgentClass(task=task, llm=llm, controller=controller, **agent_kwargs)
                    if hasattr(agent, 'AgentOutput'):
                        agent._ecan_full_AgentOutput = agent.AgentOutput
                    _cached_bu_agents[_bu_scope_key] = agent
                    logger.info(f"[BrowserAutomation] Created new browser-use agent and cached (scope={_bu_scope_key})")
                _agent_ref["agent"] = agent

            else:
                # Mode 2: Connect to existing browser via CDP
                logger.info(f"[BrowserAutomation] Mode: existing browser - connecting via CDP (type={browser_type_setting}, driver={browser_driver_setting})")
                
                # Get or create browser session through BrowserManager
                browser_session = await _get_or_create_browser_session(mainwin, state=state, calling_agent_id=calling_agent_id)
                
                if browser_session and browser_driver_setting == 'native':
                    # Successfully connected to existing browser via CDP
                    log_msg = f"[BrowserAutomation] Connected to browser session: {getattr(browser_session, 'id', 'unknown')}"
                    logger.info(log_msg)
                    send_skill_editor_log("log", log_msg)

                    # IMPORTANT: browser-use decides whether to reset/kill the session
                    # on agent.close() from browser_session.browser_profile.keep_alive,
                    # not from the separate BrowserProfile object we built above.
                    # For event-monitored loop workflows, propagate keep_alive onto the
                    # actual reused session so monitors survive done() -> pend_event.
                    try:
                        if hasattr(browser_session, "browser_profile") and browser_session.browser_profile:
                            browser_session.browser_profile.keep_alive = bool(keep_browser_alive)
                            logger.info(
                                f"[BrowserAutomation] Applied keep_alive={bool(keep_browser_alive)} "
                                f"to reused browser session profile"
                            )
                    except Exception as _keep_alive_err:
                        logger.warning(
                            f"[BrowserAutomation] Failed to apply keep_alive to reused browser session: "
                            f"{_keep_alive_err}"
                        )
                    if keep_browser_alive:
                        _patch_browser_session_lifecycle_debug(browser_session, source="pre_start")
                    
                    # Start the browser session
                    if not _is_session_started(browser_session):
                        # Parallel branches have distinct session objects; no shared lock
                        # needed (a global asyncio.Lock would serialize fan-out branches).
                        _start_task = asyncio.create_task(browser_session.start())
                        await _start_task
                    if keep_browser_alive:
                        _patch_browser_session_lifecycle_debug(browser_session, source="post_start")

                    # Focus/session preflight for CDP mode:
                    # If agent_focus_target_id is missing/invalid (common after target detach),
                    # re-bind to a valid page target before running browser-use Agent.
                    try:
                        from browser_use.browser.events import NavigateToUrlEvent, SwitchTabEvent

                        sm = getattr(browser_session, 'session_manager', None)
                        all_targets = sm.get_all_targets() if sm else {}
                        page_target_ids = [
                            tid for tid, t in (all_targets or {}).items()
                            if getattr(t, 'target_type', '') in ('page', 'tab')
                        ]

                        cur_focus = getattr(browser_session, 'agent_focus_target_id', None)
                        valid_cur_focus = cur_focus in page_target_ids if cur_focus else False
                        valid_last_focus = _last_known_focus_target_id in page_target_ids if _last_known_focus_target_id else False
                        # Capture first-invocation flag before preflight may update _last_known_focus_target_id.
                        _preflight_is_first_invocation = (_last_known_focus_target_id is None)

                        def _resolve_target_id_for_assignment(
                            preferred_tab_id: str,
                            preferred_chat_url: str,
                        ) -> str | None:
                            preferred_tab_id = str(preferred_tab_id or "").strip()
                            preferred_chat_url = str(preferred_chat_url or "").strip()
                            if not all_targets:
                                return None

                            if preferred_tab_id:
                                if preferred_tab_id in page_target_ids:
                                    return preferred_tab_id
                                preferred_upper = preferred_tab_id.upper()
                                for tid in page_target_ids:
                                    if str(tid or "").upper().endswith(preferred_upper):
                                        return str(tid)

                            if preferred_chat_url:
                                preferred_norm = preferred_chat_url.rstrip("/")
                                for tid, target in (all_targets or {}).items():
                                    if getattr(target, 'target_type', '') not in ('page', 'tab'):
                                        continue
                                    target_url = str(getattr(target, 'url', '') or '').strip().rstrip("/")
                                    if target_url and target_url == preferred_norm:
                                        return str(tid)
                            return None

                        target_focus = None
                        assignment_target_focus = None
                        try:
                            assignment_target_focus = _resolve_target_id_for_assignment(
                                assignment_tab_id,
                                assignment_chat_url,
                            )
                        except Exception:
                            assignment_target_focus = None

                        if assignment_target_focus:
                            target_focus = assignment_target_focus
                        elif valid_cur_focus:
                            target_focus = cur_focus
                        elif valid_last_focus:
                            target_focus = _last_known_focus_target_id
                        elif page_target_ids:
                            target_focus = page_target_ids[0]

                        if target_focus:
                            if cur_focus != target_focus:
                                await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=target_focus))
                                logger.info(
                                    f"[BrowserAutomation] Focus preflight switched target: "
                                    f"...{cur_focus[-4:] if cur_focus else 'None'} -> ...{target_focus[-4:]}"
                                )
                            elif assignment_target_focus:
                                logger.info(
                                    f"[BrowserAutomation] Focus preflight confirmed assigned tab already active: "
                                    f"...{target_focus[-4:]}"
                                )
                            _last_known_focus_target_id = target_focus

                            # Warm browser state to repopulate selector/session mapping before TypeTextEvent.
                            await browser_session.get_browser_state_summary(include_screenshot=False)

                            _tab_already_at_correct_url = False
                            if skill_name == "rt_chat_bot" and assignment_chat_url:
                                if assignment_target_focus:
                                    # We found the pre-opened tab. Check if URL still matches.
                                    latest_focus = getattr(browser_session, 'agent_focus_target_id', None)
                                    focused_target = sm.get_target(latest_focus) if (sm and latest_focus) else None
                                    focused_url = str(getattr(focused_target, 'url', '') or '').strip()
                                    # Only navigate if the tab is NOT already at the correct URL.
                                    # The fast-path pre-opens each tab at chat_url, so on first invocation
                                    # the tab is already loaded — no navigation needed, no lifecycle wait.
                                    # Only navigate if the URL drifted (e.g., tab reused from a previous session).
                                    if focused_url.rstrip("/") != assignment_chat_url.rstrip("/"):
                                        await browser_session.event_bus.dispatch(
                                            NavigateToUrlEvent(url=assignment_chat_url, new_tab=False)
                                        )
                                        logger.info(
                                            f"[BrowserAutomation] Focus preflight navigated assigned tab to chat_url: "
                                            f"{assignment_chat_url}"
                                        )
                                        await asyncio.sleep(1.0)
                                        await browser_session.get_browser_state_summary(include_screenshot=False)
                                    else:
                                        logger.info(
                                            f"[BrowserAutomation] Focus preflight: tab already at chat_url, no navigation needed: "
                                            f"{assignment_chat_url}"
                                        )
                                        # Tab is already loaded at the correct URL.
                                        # 1) Set flag so we can suppress browser-use's auto-navigate after agent creation.
                                        # 2) Append a note to task so the LLM doesn't try to navigate on its own.
                                        _tab_already_at_correct_url = True
                                        task = (
                                            task
                                            + "\n\n## Tab Navigation Status\n"
                                            f"The assigned chat tab is already open and focused at the correct URL ({assignment_chat_url}). "
                                            "The browser is already showing the correct chat page. "
                                            "Do NOT call navigate, go_to_url, or any navigation action — "
                                            "read the page content directly."
                                        )
                                else:
                                    # No pre-opened tab found for this assignment (tab_id was
                                    # empty or the tab was already closed).  Open a NEW tab at
                                    # the chat URL so this service agent gets its own dedicated
                                    # tab instead of hijacking another agent's tab.
                                    logger.warning(
                                        f"[BrowserAutomation] Focus preflight: no matching tab for "
                                        f"assignment (session={assignment_session_id}, "
                                        f"tab_id={assignment_tab_id or 'none'}). "
                                        f"Opening new tab at {assignment_chat_url}"
                                    )
                                    await browser_session.event_bus.dispatch(
                                        NavigateToUrlEvent(url=assignment_chat_url, new_tab=True)
                                    )
                                    await asyncio.sleep(1.0)
                                    # Re-read targets so the newly opened tab is visible.
                                    sm_refresh = getattr(browser_session, 'session_manager', None)
                                    if sm_refresh:
                                        all_targets_refresh = sm_refresh.get_all_targets() or {}
                                        chat_norm = assignment_chat_url.rstrip("/")
                                        for tid_r, tgt_r in all_targets_refresh.items():
                                            if getattr(tgt_r, 'target_type', '') not in ('page', 'tab'):
                                                continue
                                            tgt_url = str(getattr(tgt_r, 'url', '') or '').strip().rstrip("/")
                                            if tgt_url == chat_norm:
                                                target_focus = str(tid_r)
                                                _last_known_focus_target_id = target_focus
                                                await browser_session.event_bus.dispatch(
                                                    SwitchTabEvent(target_id=target_focus)
                                                )
                                                logger.info(
                                                    f"[BrowserAutomation] Focus preflight: opened and focused new tab "
                                                    f"...{target_focus[-4:]} for {assignment_chat_url}"
                                                )
                                                break
                                    await browser_session.get_browser_state_summary(include_screenshot=False)
                        else:
                            logger.warning("[BrowserAutomation] Focus preflight: no page/tab targets available before agent.run()")

                        preferred_start_url = None if skill_name == "rt_chat_bot" else _extract_preferred_start_url(task, state)
                        if preferred_start_url and sm:
                            latest_focus = getattr(browser_session, 'agent_focus_target_id', None)
                            all_targets = sm.get_all_targets() if sm else {}
                            preferred_target_id = None
                            current_target = sm.get_target(latest_focus) if latest_focus else None
                            current_url = getattr(current_target, 'url', '') if current_target else ''

                            for tid, target in (all_targets or {}).items():
                                if getattr(target, 'target_type', '') not in ('page', 'tab'):
                                    continue
                                target_url = getattr(target, 'url', '') or ''
                                if _is_matching_control_url(target_url, preferred_start_url):
                                    preferred_target_id = tid
                                    break

                            if preferred_target_id and preferred_target_id != latest_focus:
                                await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=preferred_target_id))
                                _last_known_focus_target_id = preferred_target_id
                                logger.info(
                                    f"[BrowserAutomation] Switched to preferred control tab: "
                                    f"...{preferred_target_id[-4:]} url={preferred_start_url}"
                                )
                                await browser_session.get_browser_state_summary(include_screenshot=False)
                            elif not _is_matching_control_url(current_url, preferred_start_url):
                                await browser_session.event_bus.dispatch(
                                    NavigateToUrlEvent(url=preferred_start_url, new_tab=False)
                                )
                                logger.info(
                                    f"[BrowserAutomation] Pre-navigated focused tab to preferred startup URL: "
                                    f"{preferred_start_url}"
                                )
                                await asyncio.sleep(0.8)
                                await browser_session.get_browser_state_summary(include_screenshot=False)
                    except Exception as _focus_exc:
                        logger.warning(f"[BrowserAutomation] Focus preflight failed: {_focus_exc}")

                    # Reuse cached browser-use sub-agent if available (avoids per-cycle
                    # re-init overhead and the ~860 MB allocation spike).
                    _bu_scope_key = _resolve_browser_scope_key(state)
                    _cached_bu_agent = _cached_bu_agents.get(_bu_scope_key)
                    if _cached_bu_agent is not None:
                        _reset_bu_agent_for_next_round(_cached_bu_agent, loop_history_mode, task)
                        # Re-bind the session in case it was recreated by the preflight above.
                        try:
                            _cached_bu_agent.browser_session = browser_session
                        except Exception:
                            pass
                        agent = _cached_bu_agent
                        logger.info(
                            f"[BrowserAutomation] Reusing cached browser-use agent "
                            f"(scope={_bu_scope_key}, loop_history_mode={loop_history_mode})"
                        )
                    else:
                        # First iteration for this task — create a new agent and cache it.
                        agent = AgentClass(task=task, llm=llm, controller=controller, browser_session=browser_session, **agent_kwargs)
                        # Save the full AgentOutput so _reset_bu_agent_for_next_round
                        # can restore it after browser-use clobbers it on max_steps/failures.
                        if hasattr(agent, 'AgentOutput'):
                            agent._ecan_full_AgentOutput = agent.AgentOutput
                        _cached_bu_agents[_bu_scope_key] = agent
                        logger.info(
                            f"[BrowserAutomation] Created new browser-use agent and cached "
                            f"(scope={_bu_scope_key}, loop_history_mode={loop_history_mode})"
                        )
                    _agent_ref["agent"] = agent
                else:
                    # Fallback: browser session creation failed or unsupported driver
                    logger.warning(f"[BrowserAutomation] Failed to connect to existing browser, falling back to new browser (session={browser_session}, driver={browser_driver_setting})")
                    agent = AgentClass(task=task, llm=llm, controller=controller, **agent_kwargs)
                    _agent_ref["agent"] = agent

            try:
                setattr(agent, "_ecan_skill_name", skill_name)
                setattr(agent, "_ecan_node_id", node_name)
                setattr(agent, "_ecan_owner", owner)
                # Suppress browser-use's auto-navigate-from-task-URL feature when the
                # assigned chat tab is already loaded at the correct URL.  Without this,
                # browser-use appends a navigate initial-action that times out (30s)
                # because the page is already stable and no lifecycle events fire.
                if locals().get("_tab_already_at_correct_url"):
                    agent.directly_open_url = False
                    logger.info(
                        "[BrowserAutomation] Suppressed auto-navigate (directly_open_url=False): "
                        "tab already at correct URL"
                    )
            except Exception:
                pass
            _browser_scope_key = _resolve_browser_scope_key(state)
            _cached_browser_session = _cached_browser_sessions.get(_browser_scope_key)
            # Merge with the dict value rather than overwriting: the focus preflight (which runs
            # before this point in the CDP/existing-browser path) may have set
            # _last_known_focus_target_id to the active tab. Re-reading the dict here would
            # discard that value (the dict is only updated *after* agent.run() completes), so
            # the per-step refocus would have nothing to refocus to.
            _last_known_focus_target_id = _last_known_focus_target_id or _last_known_focus_target_ids.get(_browser_scope_key)

            try:
                # Defensive second application after agent construction. Some agent
                # constructors may replace/wrap the session reference.
                _agent_session = getattr(agent, "browser_session", None)
                logger.info(
                    f"[BrowserAutomation][LifecycleDebug] Agent/browser session identity: "
                    f"agent_session_obj={id(_agent_session) if _agent_session else 'none'} "
                    f"cached_obj={id(_cached_browser_session) if _cached_browser_session else 'none'} "
                    f"same_as_cached={_agent_session is _cached_browser_session} scope={_browser_scope_key}"
                )
                if _agent_session and _agent_session is not _cached_browser_session:
                    # Evict oldest entries if cache exceeds max size
                    if len(_cached_browser_sessions) >= _MAX_BROWSER_CACHE_SIZE:
                        evicted = 0
                        for _key in list(_cached_browser_sessions.keys()):
                            if _key == _browser_scope_key:
                                continue
                            if not _key.startswith("chat:"):
                                _old_sess = _cached_browser_sessions.pop(_key, None)
                                _last_known_focus_target_ids.pop(_key, None)
                                if _old_sess is not None:
                                    _cached_passive_agents.pop(id(_old_sess), None)
                                evicted += 1
                                if evicted >= 2:
                                    break
                    _cached_browser_sessions[_browser_scope_key] = _agent_session
                    try:
                        setattr(_agent_session, "_ecan_browser_scope_key", _browser_scope_key)
                    except Exception:
                        pass
                    logger.info(
                        f"[BrowserAutomation] Updated scoped cache from live agent session "
                        f"for scope={_browser_scope_key}"
                    )
                if _agent_session and hasattr(_agent_session, "browser_profile") and _agent_session.browser_profile:
                    _agent_session.browser_profile.keep_alive = bool(keep_browser_alive)
                    logger.info(
                        f"[BrowserAutomation] Agent session keep_alive="
                        f"{_agent_session.browser_profile.keep_alive}"
                    )
                if keep_browser_alive:
                    _patch_browser_session_lifecycle_debug(_agent_session, source="post_agent_create")
            except Exception as _agent_keep_alive_err:
                logger.warning(
                    f"[BrowserAutomation] Failed to apply keep_alive on agent session: "
                    f"{_agent_keep_alive_err}"
                )
            try:
                from agent.ec_skills.browser_use_extension.extension_tools_service import (
                    set_current_agent,
                    set_current_runtime_context,
                )
                set_current_agent(agent)
                set_current_runtime_context(
                    agent_id=calling_agent_id or "",
                    task_id=(state.get("attributes") or {}).get("task_id", "") if isinstance(state, dict) else "",
                    skill_name=skill_name,
                    node_id=node_name,
                    owner=owner,
                )
            except Exception as _set_agent_err:
                logger.debug(f"[BrowserAutomation] Failed to register current agent for extension tools: {_set_agent_err}")

            # browser-use always calls agent.close() at the end of run(). Even for
            # keep_alive=True it stops the browser_session event bus, which tears
            # down the CDP/session plumbing our long-lived event monitors depend on.
            # For monitor-driven loop workflows, preserve the browser session fully.
            if keep_browser_alive and _event_monitor_configs and hasattr(agent, "close"):
                try:
                    _agent_eventbus = getattr(agent, "eventbus", None)
                    if _agent_eventbus and hasattr(_agent_eventbus, "stop") and not getattr(_agent_eventbus, "_ecan_preserve_patched", False):
                        _orig_agent_eventbus_stop = _agent_eventbus.stop

                        async def _preserve_agent_eventbus_stop(*a, **kw):
                            logger.info(
                                f"[BrowserAutomation] Preserving agent event bus on monitored keep_alive run end: "
                                f"args={a}, kwargs={kw}"
                            )
                            return None

                        _agent_eventbus.stop = _preserve_agent_eventbus_stop
                        setattr(_agent_eventbus, "_ecan_preserve_patched", True)
                        setattr(_agent_eventbus, "_ecan_orig_stop", _orig_agent_eventbus_stop)
                        logger.info("[BrowserAutomation] Patched agent.eventbus.stop to preserve monitored keep_alive session")
                except Exception as _eventbus_patch_err:
                    logger.warning(
                        f"[BrowserAutomation] Failed to patch agent eventbus stop for monitored keep_alive session: "
                        f"{_eventbus_patch_err}"
                    )

                _orig_agent_close = agent.close

                async def _close_preserving_monitored_session():
                    try:
                        _bs = getattr(agent, "browser_session", None)
                        _has_active_monitor_set = False
                        try:
                            from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability

                            _cap = get_event_monitor_capability(_bs, create=False) if _bs else None
                            _active = _cap.get_active_monitor_set() if _cap else None
                            _has_active_monitor_set = bool(_active and getattr(_active, "monitors", None))
                        except Exception:
                            _has_active_monitor_set = False

                        if _bs and _has_active_monitor_set:
                            logger.info(
                                "[BrowserAutomation] Preserving monitored keep_alive browser session on agent.close()"
                            )
                            # Preserve aggressively: do not let browser-use tear down
                            # any more process/session state at the run boundary.
                            return
                    except Exception as _preserve_close_err:
                        logger.warning(
                            f"[BrowserAutomation] Preserved close path failed, falling back to original close: "
                            f"{_preserve_close_err}"
                        )
                    await _orig_agent_close()

                agent.close = _close_preserving_monitored_session
                logger.info("[BrowserAutomation] Patched agent.close to preserve monitored keep_alive session")

            # Auto-start event monitors on the browser session (Phase 1: HTTP polling)
            _active_monitor_set = None
            if _event_monitor_configs and hasattr(agent, 'browser_session') and agent.browser_session:
                try:
                    from agent.ec_skills.browser_use_extension.event_monitor_capability import get_event_monitor_capability
                    import copy as _copy_mod
                    # Deep-copy configs to prevent cross-task mutation (all task instances
                    # of the same compiled skill share the same closure list).
                    logger.info(
                        f"[BrowserAutomation] Pre-copy monitor state: "
                        f"labels={[c.label for c in _event_monitor_configs]}, "
                        f"list_id={id(_event_monitor_configs)}, obj_ids={[id(c) for c in _event_monitor_configs]}, "
                        f"skill={skill_name}, scope={_browser_scope_key}"
                    )
                    _monitor_configs_copy = _copy_mod.deepcopy(_event_monitor_configs)
                    capability = get_event_monitor_capability(agent.browser_session, create=True)
                    _active_monitor_set = await capability.ensure_started(
                        configs=_monitor_configs_copy,
                        agent_id=calling_agent_id or "",
                    ) if capability else None
                    if _active_monitor_set:
                        log_msg = (
                            f"[BrowserAutomation] Event monitors started: "
                            f"{len(_active_monitor_set.monitors)} active "
                            f"(set_id={_active_monitor_set.monitor_set_id})"
                        )
                        logger.info(log_msg)
                        send_skill_editor_log("log", log_msg)
                except Exception as _em_start_err:
                    logger.warning(f"[BrowserAutomation] Failed to start event monitors: {_em_start_err}")

            _frontdesk_fastpath_result = await _maybe_run_frontdesk_dispatch_fastpath(agent)
            if _frontdesk_fastpath_result is not None:
                return _frontdesk_fastpath_result

            # ── HOT-PATH: chat_message reply bypass ──
            # When a chat_message arrives with a structured {response_text,
            # customer_name} payload, skip the LLM entirely and call the
            # registered chat adapter tools directly (e.g. *_open_session →
            # *_send_message).  This cuts Phase-2 latency from ~15s (LLM think
            # + multi-step) to ~2s (two direct tool calls).
            #
            # Placed here (after browser session setup) so the CDP connection
            # is live and the feige tools can execute JS on the page.
            if not _hot_path_done:
                try:
                    _hp2_response_text = ""
                    _hp2_customer_name = ""
                    if isinstance(state, dict):
                        _hp2_raw = _extract_runtime_invocation_input(state)
                        if _hp2_raw:
                            try:
                                _hp2_parsed = json.loads(_hp2_raw)
                                if isinstance(_hp2_parsed, dict):
                                    _hp2_response_text = str(_hp2_parsed.get("response_text", "")).strip()
                                    _hp2_customer_name = str(
                                        _hp2_parsed.get("customer_name")
                                        or _hp2_parsed.get("customer_id")
                                        or ""
                                    ).strip()
                            except (json.JSONDecodeError, TypeError):
                                pass
                    if _hp2_response_text and _hp2_customer_name:
                        _hp2_session = getattr(agent, "browser_session", None)
                        if _hp2_session:
                            from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller as _hp2_ctrl
                            _hp2_actions = _hp2_ctrl.registry.registry.actions
                            _hp2_open_fn = None
                            _hp2_send_fn = None
                            _hp2_open_name = ""
                            _hp2_send_name = ""
                            for _act_name, _act_obj in _hp2_actions.items():
                                if _act_name.endswith("_open_session"):
                                    _hp2_open_fn = _act_obj
                                    _hp2_open_name = _act_name
                                elif _act_name.endswith("_send_message"):
                                    _hp2_send_fn = _act_obj
                                    _hp2_send_name = _act_name
                            if _hp2_open_fn and _hp2_send_fn:
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH: retrying with live session. "
                                    f"customer={_hp2_customer_name}, "
                                    f"tools={_hp2_open_name}+{_hp2_send_name}, node={node_name}"
                                )
                                send_skill_editor_log(
                                    "log",
                                    f"[BrowserAutomation] HOT-PATH: direct reply to "
                                    f"{_hp2_customer_name} (skipping LLM)"
                                )
                                _hp2_open_params = _hp2_open_fn.param_model(customer_name=_hp2_customer_name)
                                _hp2_send_params = _hp2_send_fn.param_model(text=_hp2_response_text)
                                # Call open_session
                                _hp2_open_result = await _hp2_open_fn.function(
                                    params=_hp2_open_params, browser_session=_hp2_session
                                )
                                _hp2_open_ok = (
                                    _hp2_open_result
                                    and not getattr(_hp2_open_result, "error", None)
                                )
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH: {_hp2_open_name} → "
                                    f"{'OK' if _hp2_open_ok else 'FAIL'}: "
                                    f"{getattr(_hp2_open_result, 'extracted_content', '') or getattr(_hp2_open_result, 'error', '')}"
                                )
                                if _hp2_open_ok:
                                    await asyncio.sleep(0.5)
                                    _hp2_send_result = await _hp2_send_fn.function(
                                        params=_hp2_send_params, browser_session=_hp2_session
                                    )
                                    _hp2_send_ok = (
                                        _hp2_send_result
                                        and not getattr(_hp2_send_result, "error", None)
                                    )
                                    logger.info(
                                        f"[BrowserAutomation] HOT-PATH: {_hp2_send_name} → "
                                        f"{'OK' if _hp2_send_ok else 'FAIL'}: "
                                        f"{getattr(_hp2_send_result, 'extracted_content', '') or getattr(_hp2_send_result, 'error', '')}"
                                    )
                                    if _hp2_send_ok:
                                        _hot_path_done = True
                                        state.setdefault("result", {})["llm_result"] = {
                                            "all_done": False,
                                            "work_done": False,
                                            "hot_path": True,
                                            "action": f"{_hp2_open_name}+{_hp2_send_name}",
                                            "customer": _hp2_customer_name,
                                        }
                                        # Clear response data to prevent duplicate sends
                                        state["input"] = ""
                                        if isinstance(state.get("messages"), list) and len(state["messages"]) > 4:
                                            state["messages"][4] = ""
                                        try:
                                            _hp2_attrs = state.get("attributes")
                                            if isinstance(_hp2_attrs, dict):
                                                _hp2_attrs.pop("params", None)
                                        except Exception:
                                            pass
                                        logger.info(
                                            f"[BrowserAutomation] HOT-PATH: reply sent to "
                                            f"{_hp2_customer_name} (~1s, LLM bypassed), node={node_name}"
                                        )
                                        send_skill_editor_log(
                                            "log",
                                            f"[BrowserAutomation] HOT-PATH: reply sent to "
                                            f"{_hp2_customer_name} (LLM bypassed)"
                                        )
                                        return state
                                if not _hot_path_done:
                                    logger.warning(
                                        f"[BrowserAutomation] HOT-PATH: tool call failed, "
                                        f"falling back to LLM. node={node_name}"
                                    )
                except Exception as _hp2_err:
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH: failed (non-fatal, "
                        f"falling back to LLM): {_hp2_err}"
                    )

            # Register current agent instance so extension tools (e.g. list_files)
            # can auto-authorize discovered file paths for later read_long_content/read_file calls.
            try:
                from agent.ec_skills.browser_use_extension.extension_tools_service import set_current_agent

                set_current_agent(agent)
            except Exception as _set_agent_exc:
                logger.warning(f"[BrowserAutomation] Failed to register current agent for extension tools: {_set_agent_exc}")

            # Look up cancellation_event from global registry by task_id
            from agent.ec_tasks import cancellation_registry
            task_id = (state.get("attributes") or {}).get("task_id") if isinstance(state, dict) else None
            cancellation_event = cancellation_registry.get(task_id) if task_id else None
            if not cancellation_event:
                logger.debug(f"[BrowserAutomation] No cancellation_event for task_id={task_id}")

            # Store cancellation_event directly on the LLM so create_with_logging can poll it
            # without a registry lookup by task_id (which may be stored at wrong state path).
            if cancellation_event:
                try:
                    setattr(llm, "_ec_cancellation_event", cancellation_event)
                except Exception:
                    pass

            try:
                async def _run_agent_call(**run_kwargs):
                    """Run agent with node-level limits (max_steps + optional hard timeout)."""
                    # Safety ceiling: if maxSteps is not configured in the node, cap at 30 steps
                    # to prevent an accidental infinite loop from running forever.
                    # Set maxSteps explicitly in the node config for precise control.
                    _effective_max_steps = node_max_steps if node_max_steps else 30
                    run_kwargs.setdefault("max_steps", _effective_max_steps)
                    # max_actions_per_step is an Agent constructor param (already in agent_kwargs),
                    # NOT a run() param — do not pass it here or agent.run() raises TypeError.
                    run_coro = agent.run(**run_kwargs)
                    if node_timeout_seconds:
                        return await asyncio.wait_for(run_coro, timeout=node_timeout_seconds)
                    return await run_coro

                # Pass cancellation_event to agents that support it natively;
                # for native browser-use Agent, patch its step method inline.
                # Also add per-step tab refocus for rt_chat_bot to prevent cross-agent
                # CDP interference when multiple service agents share one Chrome instance.
                agent_class_name = agent.__class__.__name__

                # Resolve the target tab ID to keep focused across steps.
                # IMPORTANT: per-step refocus is only enabled for rt_chat_bot by default.
                # For research/executor flows, forcing refocus each step can bounce
                # the agent back to the original search tab and cause repeated clicks.
                # To enable for other skills: add `enable_step_refocus: true` in the
                # node's inputsValues, or add the skill name to the condition below.
                _step_focus_target = None
                _enable_step_refocus = (
                    inputs.get("enable_step_refocus", {}).get("content", "")
                    if isinstance(inputs, dict) else ""
                )
                if (_enable_step_refocus.lower() == "true"
                        or skill_name == "rt_chat_bot") and hasattr(agent, 'step'):
                    _step_focus_target = (
                        locals().get("assignment_target_focus")
                        or _last_known_focus_target_id
                        or None
                    )

                # Patch agent.step for:
                # - rt_chat_bot: per-step tab refocus (safety net)
                # - customer_front_desk: abort if fast-path already dispatched
                # - any skill with cancellation_event
                # NOTE: No cross-agent step lock needed — each agent now has its own
                # independent CDP connection (no shared session_manager/event_bus).
                _needs_step_patch = (
                    (cancellation_event and hasattr(agent, 'step'))
                    or (skill_name == "rt_chat_bot" and hasattr(agent, 'step'))
                    or (skill_name == "customer_front_desk" and hasattr(agent, 'step'))
                    or (node_dom_focus_selector and hasattr(agent, 'step'))
                )

                # Always pass cancellation_event to agent.run() so stop button works
                # This is CRITICAL for all agent types including browser-use
                if cancellation_event:
                    agent_kwargs['cancellation_event'] = cancellation_event
                    logger.info(f"[BrowserAutomation] Passing cancellation_event to agent.run()")

                if cancellation_event and agent_class_name in ('CloudAgent', 'PrivacyAgent'):
                    history = await _run_agent_call(cancellation_event=cancellation_event)
                elif cancellation_event and not _needs_step_patch:
                    # CRITICAL: Without cooperative cancellation, stop button has no effect.
                    # Wrap agent.run() with a step-level cancel check so stop works for all nodes.
                    async def _step_check_cancel(*a, **kw):
                        if cancellation_event and cancellation_event.is_set():
                            logger.info("[BrowserAutomation] Cancellation requested, stopping")
                            raise asyncio.CancelledError("Task cancelled by user")
                        return await agent.step(*a, **kw)
                    agent.step = _step_check_cancel
                    history = await agent.run(**agent_kwargs)
                    # Check cancellation after agent.run() returns
                    if cancellation_event and cancellation_event.is_set():
                        logger.info("[BrowserAutomation] Cancellation set after agent.run() (simple path), stopping")
                        raise asyncio.CancelledError("Task cancelled after LLM response")
                elif _needs_step_patch:
                    _orig_step = agent.step
                    _patch_cancel = cancellation_event
                    _patch_focus = _step_focus_target
                    _patch_bs = getattr(agent, 'browser_session', None) if _step_focus_target else None
                    _patch_skill = skill_name
                    _patch_dom_focus = node_dom_focus_selector  # CSS selectors for DOM pruning

                    async def _step_with_cancel(*a, **kw):
                        # Front desk: abort if fast-path already dispatched all assignments
                        # (this invocation is a stale auto-triggered LLM run).
                        if _patch_skill == "customer_front_desk":
                            _bs_check = getattr(agent, 'browser_session', None)
                            if _bs_check and getattr(_bs_check, '_ecan_frontdesk_dispatched_all', False):
                                logger.info(
                                    "[BrowserAutomation] Front-desk LLM step aborted: "
                                    "fast-path already dispatched all assignments"
                                )
                                raise asyncio.CancelledError("Front desk work completed by fast-path")

                        # Per-step tab refocus: re-acquire focus on the assigned tab.
                        # With independent sessions this is a safety net — each session
                        # maintains its own target attachment, but re-confirm it here.
                        if _patch_focus and _patch_bs:
                            try:
                                from browser_use.browser.events import SwitchTabEvent as _STE
                                _cur = getattr(_patch_bs, 'agent_focus_target_id', None)
                                if _cur != _patch_focus:
                                    await _patch_bs.event_bus.dispatch(_STE(target_id=_patch_focus))
                                    logger.debug(
                                        f"[BrowserAutomation] Per-step tab refocus: "
                                        f"...{_cur[-4:] if _cur else 'None'} → ...{_patch_focus[-4:]}"
                                    )
                                else:
                                    logger.debug(
                                        f"[BrowserAutomation] Per-step tab refocus: already on ...{_patch_focus[-4:]}"
                                    )
                            except Exception as _refocus_err:
                                logger.debug(f"[BrowserAutomation] Per-step tab refocus skipped: {_refocus_err}")
                        if _patch_cancel and _patch_cancel.is_set():
                            logger.info(f"[BrowserAutomation] Cancellation requested, stopping")
                            raise asyncio.CancelledError("Task cancelled by user")

                        # DOM focus selector: hide elements NOT matching the configured
                        # CSS selectors before browser-use extracts the DOM snapshot.
                        # After the step completes, restore visibility so the page
                        # remains usable for user interaction / next steps.
                        _dom_hidden = False
                        if _patch_dom_focus:
                            try:
                                _dom_bs = getattr(agent, 'browser_session', None)
                                _dom_page = getattr(_dom_bs, 'current_page', None) if _dom_bs else None
                                if _dom_page:
                                    # Escape the selector for safe JS embedding
                                    _sel_escaped = _patch_dom_focus.replace("\\", "\\\\").replace("'", "\\'")
                                    _hide_js = f"""(function() {{
  var sels = '{_sel_escaped}'.split(',').map(function(s) {{ return s.trim(); }}).filter(Boolean);
  if (!sels.length) return 0;
  var keep = new Set();
  sels.forEach(function(sel) {{
    document.querySelectorAll(sel).forEach(function(el) {{
      keep.add(el);
      // Also keep all ancestors so they remain visible
      var p = el.parentElement;
      while (p) {{ keep.add(p); p = p.parentElement; }}
      // Keep all descendants so child content is visible
      el.querySelectorAll('*').forEach(function(d) {{ keep.add(d); }});
    }});
  }});
  var hidden = 0;
  document.querySelectorAll('body *').forEach(function(el) {{
    if (!keep.has(el)) {{
      var st = el.style;
      if (st.display !== 'none') {{
        el.setAttribute('data-ecan-dom-focus-orig', st.display || '');
        st.display = 'none';
        hidden++;
      }}
    }}
  }});
  return hidden;
}})()"""
                                    _hide_result = await _dom_page.evaluate(_hide_js)
                                    _dom_hidden = True
                                    logger.debug(
                                        f"[BrowserAutomation] DOM focus: hid {_hide_result} elements "
                                        f"(selectors={_patch_dom_focus!r})"
                                    )
                            except Exception as _dom_hide_err:
                                logger.debug(f"[BrowserAutomation] DOM focus hide failed: {_dom_hide_err}")

                        try:
                            return await _orig_step(*a, **kw)
                        finally:
                            # Restore hidden elements after DOM extraction
                            if _dom_hidden:
                                try:
                                    _restore_js = """(function() {
  var els = document.querySelectorAll('[data-ecan-dom-focus-orig]');
  els.forEach(function(el) {
    el.style.display = el.getAttribute('data-ecan-dom-focus-orig') || '';
    el.removeAttribute('data-ecan-dom-focus-orig');
  });
  return els.length;
})()"""
                                    _dom_page = getattr(getattr(agent, 'browser_session', None), 'current_page', None)
                                    if _dom_page:
                                        _restored = await _dom_page.evaluate(_restore_js)
                                        logger.debug(f"[BrowserAutomation] DOM focus: restored {_restored} elements")
                                except Exception as _dom_restore_err:
                                    logger.debug(f"[BrowserAutomation] DOM focus restore failed: {_dom_restore_err}")

                    agent.step = _step_with_cancel
                    _patch_labels = []
                    if _patch_cancel:
                        _patch_labels.append("cancellation")
                    if _step_focus_target:
                        _patch_labels.append(f"tab refocus (target=...{_step_focus_target[-4:]})")
                    if _patch_skill == "customer_front_desk":
                        _patch_labels.append("fast-path abort guard")
                    if _patch_dom_focus:
                        _patch_labels.append(f"DOM focus ({_patch_dom_focus})")
                    logger.info(
                        f"[BrowserAutomation] Patched agent.step: {', '.join(_patch_labels) or 'basic'}"
                    )
                    try:
                        history = await _run_agent_call()
                    except asyncio.CancelledError as _ce:
                        _ce_msg = str(_ce) or "CancelledError"
                        if "fast-path" in _ce_msg:
                            logger.info(f"[BrowserAutomation] LLM run stopped: {_ce_msg}")
                            # Return a synthetic result so downstream doesn't crash.
                            history = None
                        else:
                            raise
                    finally:
                        agent.step = _orig_step
                else:
                    history = await _run_agent_call()

                # CRITICAL: Check cancellation after agent.run() returns
                # Even if cancellation was set during execution, we need to stop here
                if cancellation_event and cancellation_event.is_set():
                    logger.info("[BrowserAutomation] Cancellation set after agent.run(), stopping node execution")
                    raise asyncio.CancelledError("Task cancelled after LLM response")

                # Persist focus target across node iterations to survive session churn.
                try:
                    _focus_after_run = getattr(getattr(agent, 'browser_session', None), 'agent_focus_target_id', None)
                    if _focus_after_run:
                        _last_known_focus_target_ids[_browser_scope_key] = _focus_after_run
                except Exception:
                    pass
                
                # Log step budget usage so we can tell at a glance whether
                # max_steps was reached (which clobbers AgentOutput → DoneAgentOutput).
                try:
                    _ag_st = getattr(agent, 'state', None)
                    _ag_settings = getattr(agent, 'settings', None)
                    _steps_used = getattr(_ag_st, 'n_steps', '?') if _ag_st else '?'
                    _max_steps = getattr(_ag_settings, 'max_steps', '?') if _ag_settings else '?'
                    _consec_fail = getattr(_ag_st, 'consecutive_failures', '?') if _ag_st else '?'
                    _max_fail = getattr(_ag_settings, 'max_failures', '?') if _ag_settings else '?'
                    _stopped = getattr(_ag_st, 'stopped', '?') if _ag_st else '?'
                    _ao_is_done = agent.AgentOutput is getattr(agent, 'DoneAgentOutput', None) if hasattr(agent, 'AgentOutput') else '?'
                    logger.info(
                        f"[BrowserAutomation] Run finished: "
                        f"steps={_steps_used}/{_max_steps}, "
                        f"failures={_consec_fail}/{_max_fail}, "
                        f"stopped={_stopped}, "
                        f"AgentOutput_clobbered={_ao_is_done}"
                    )
                except Exception as _step_log_err:
                    logger.debug(f"[BrowserAutomation] Step count log failed: {_step_log_err}")

                # Truncate long output for logging
                history_str = str(history)
                if len(history_str) > 10000:
                    history_str = history_str[:10000] + '... (truncated)'
                logger.debug(f"[BROWSER USE]Agent Run History: {history_str}")

                final = history.final_result() if (history and hasattr(history, 'final_result')) else None
                if history:
                    _log_browser_use_result_summary(history, skill_name=skill_name, node_name=node_name)
                final_str = str(final)
                if len(final_str) > 10000:
                    final_str = final_str[:10000] + '... (truncated)'
                logger.debug(f"[BROWSER USE]Agent Run Results: {final_str}")
                
                # Log browser-use usage summary for diagnostics only.
                # Do NOT record it into TokenTracker because raw underlying LLM calls
                # are already recorded in LoggingBrowserUseChatOpenAI. Recording both
                # would double-count tokens and mislead later analysis.
                try:
                    _bu_usage = getattr(history, 'usage', None)
                    if _bu_usage and (getattr(_bu_usage, 'total_tokens', 0) or 0) > 0:
                        _by_model = getattr(_bu_usage, 'by_model', None) or {}
                        if _by_model:
                            for _m_name, _m_stats in _by_model.items():
                                _m_in = getattr(_m_stats, 'prompt_tokens', 0) or 0
                                _m_out = getattr(_m_stats, 'completion_tokens', 0) or 0
                                if _m_in > 0 or _m_out > 0:
                                    logger.info(f"[TokenTracker] BrowserUse summary model={_m_name} in={_m_in} out={_m_out}")
                        logger.info(
                            f"[TokenTracker] BrowserUse total: {getattr(_bu_usage, 'total_tokens', 0)} tokens, "
                            f"{getattr(_bu_usage, 'entry_count', 0)} LLM calls, "
                            f"cost=${getattr(_bu_usage, 'total_cost', 0.0):.4f}"
                        )
                    else:
                        logger.debug(f"[TokenTracker] BrowserUse: no usage summary in history ({len(getattr(history, 'history', []))} steps)")
                except Exception as _bu_tk_err:
                    logger.warning(f"[TokenTracker] Failed to record browser-use token usage: {_bu_tk_err}")

                # ── Clear consumed response_text from all state sources ──
                # After the LLM processes a chat_message response, clear it so
                # subsequent browser_event cycles don't re-inject and re-send it.
                if _runtime_had_response_text:
                    state["input"] = ""
                    if isinstance(state.get("messages"), list) and len(state["messages"]) > 4:
                        state["messages"][4] = ""
                    try:
                        _clr_attrs = state.get("attributes")
                        if isinstance(_clr_attrs, dict):
                            _clr_attrs.pop("params", None)
                    except Exception:
                        pass
                    logger.info(
                        f"[BrowserAutomation] Cleared consumed response_text from state "
                        f"(node={node_name}, skill={skill_name})"
                    )

                return {"final": final, "history": str(history)}
            except asyncio.CancelledError:
                # CRITICAL: Cancellation must propagate up, NOT be converted to RuntimeError
                logger.info("[BrowserAutomation] CancelledError caught, re-raising to propagate cancellation")
                raise
            except asyncio.TimeoutError as e:
                timeout_msg = (
                    f"Browser automation node timed out after {node_timeout_seconds}s"
                    if node_timeout_seconds
                    else "Browser automation node timed out"
                )
                logger.error(f"[BrowserAutomation] {timeout_msg}")
                raise RuntimeError(timeout_msg) from e
            finally:
                # NOTE: Event monitors are NOT stopped here intentionally.
                # They persist across the loop for pend_event nodes to receive events.
                # Global cleanup happens when runner shuts down (see runner.py).
                # To manually stop monitors early, call stop_monitors(session._ecan_event_monitors, session).
                pass

                # Clean up browser session if not cached
                # Only close non-cached sessions to prevent resource leaks
                if hasattr(agent, 'browser_session') and agent.browser_session:
                    # Check if this is the cached session
                    is_cached_session = (agent.browser_session == _cached_browser_sessions.get(_browser_scope_key))
                    
                    # Only close if NOT cached (cached sessions are reused)
                    if not is_cached_session and browser_type_setting != 'new chromium':
                        try:
                            await agent.browser_session.stop()
                            logger.debug("[BrowserAutomation] Browser session stopped (non-cached)")
                        except Exception as e:
                            logger.warning(f"[BrowserAutomation] Failed to stop browser session: {e}")
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNode")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
            # Re-raise the exception so LangGraph can mark the node as failed
            _err_text = str(e).strip() or repr(e)
            raise RuntimeError(f"Browser automation failed: {_err_text}") from e

    def _auto(state: dict, *, runtime=None, store=None, **kwargs):
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

                def _compact_upstream_outputs_for_prompt(_state: dict) -> str:
                    import json
                    import re
                    from urllib.parse import urlsplit, parse_qs

                    tr = _state.get("tool_result")
                    if not isinstance(tr, dict):
                        return "{}"

                    keep_keys = {
                        "status",
                        "reason",
                        "price_range",
                        "links",
                        "downloaded_images",
                        "download_count",
                        "image_urls",
                        "image_descriptions",
                        "listing_url",
                        "title",
                        "description",
                        "price",
                        "product_keyword",
                        "brand",
                        "model",
                        "category",
                        "condition",
                        "original_images",
                        "products",
                        "highlights_summary",
                        "target_audience",
                        "notes",
                        "is_free_shipping",
                        "is_used",
                        "features",
                        "listing_images",
                        "search_keyword",
                    }

                    # Generic noise keys to avoid prompt bloat and scenario-specific internals.
                    drop_keys = {
                        "provider",
                        "task",
                        "systemPrompt",
                        "history",
                        "prompts",
                        "prompt_refs",
                        "messages",
                        "threads",
                        "events",
                        "attachments",
                        "http_response",
                        "cli_input",
                        "cli_results",
                        "attributes",
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
                        """
                        Best-effort JSON object extractor for node outputs.
                        Supports plain JSON and fenced code blocks.
                        """
                        if not isinstance(text, str):
                            return None
                        s = text.strip()
                        if not s:
                            return None

                        # Strip fenced code block wrappers when present.
                        if s.startswith("```"):
                            s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
                            s = re.sub(r"\n?```$", "", s).strip()

                        # Fast path: whole string is a JSON object/array.
                        for candidate in (s,):
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, dict):
                                    return parsed
                            except Exception:
                                pass

                        # Fallback: capture the largest {...} block.
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
                        """
                        Scenario-agnostic field extraction:
                        keep compact, actionable keys from arbitrary JSON-like outputs.
                        """
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

                            # Preserve explicit keep_keys precedence.
                            if k in dst:
                                continue

                            if _is_small_scalar(v) or _is_small_scalar_list(v):
                                dst[k] = v
                                continue

                            # Keep compact nested dicts with scalar values only.
                            if isinstance(v, dict) and len(v) <= 20:
                                if all(_is_small_scalar(sv) for sv in v.values()):
                                    dst[k] = v
                                # Also recurse one level to collect commonly useful nested keys.
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

                            # Home/landing pages are not actionable detail links.
                            if path in ("", "/"):
                                return False

                            # Drop obvious search/listing URLs.
                            text = f"{path}?{query}"
                            if any(k in text for k in ("/search", "search?", "keyword=", "query=", "q=", "wd=", "/list", "list?")):
                                return False

                            # Keep links with common detail id parameters.
                            id_keys = ("id", "itemid", "item_id", "sku", "sku_id", "productid", "product_id", "pid")
                            if any(k in query_map and any(str(v).strip() for v in query_map.get(k, [])) for k in id_keys):
                                return True

                            # Keep paths that look like detail pages (have a long numeric token).
                            if re.search(r"\d{5,}", path):
                                return True

                            # Keep deeper paths unless they look like generic landing sections.
                            segments = [seg for seg in path.split("/") if seg]
                            if len(segments) >= 2 and segments[-1] not in ("home", "index", "category", "categories", "catalog", "list", "search"):
                                return True

                            return False
                        except Exception:
                            return False

                    compact = {}
                    for _nid, _val in tr.items():
                        # Exclude current node output to avoid self-feedback loops on retries.
                        # Example: download_images retry should not consume prior
                        # {"download_images": {"status":"blocked", ...}} as upstream input.
                        if _nid == node_name:
                            continue
                        if not isinstance(_val, dict):
                            continue
                        row = {}

                        # 1) Direct extraction from node output dict.
                        _merge_keep_keys_from_dict(row, _val)
                        _merge_generic_fields_from_dict(row, _val)

                        # 2) Generic extraction from nested dict/string payloads.
                        #    This keeps behavior generic across browser/llm nodes.
                        candidate_payloads = [
                            _val.get("final"),
                            _val.get("result"),
                            _val.get("llm_result"),
                            _val.get("response"),
                            _val.get("output"),
                            _val.get("text"),
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
                            f"[UpstreamCompact] node={node_name} "
                            f"upstream_nodes={list(compact.keys())} "
                            f"key_summary={key_summary} "
                            f"payload_chars={len(payload)}"
                        )
                    except Exception:
                        pass
                    if len(payload) > 12000:
                        payload = payload[:12000] + "...(truncated)"
                    return payload

                # Prevent prompt bloat when upstream_outputs is requested.
                if "upstream_outputs" in variables:
                    prompt_refs["upstream_outputs"] = _compact_upstream_outputs_for_prompt(state)
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
        def _parse_required_vars_marker(task_text_raw: str) -> list[str]:
            try:
                m = re.search(r"\[REQUIRED_VARS:([^\]]+)\]", str(task_text_raw or ""))
                if not m:
                    return []
                raw = m.group(1)
                vars_list = [v.strip() for v in raw.split(",") if v.strip()]
                # Keep stable order and dedupe
                seen = set()
                out = []
                for v in vars_list:
                    if v in seen:
                        continue
                    seen.add(v)
                    out.append(v)
                return out
            except Exception:
                return []

        try:
            _required_vars = _parse_required_vars_marker(combined_task)
            if _required_vars:
                _missing_vars = []
                _missing_details: list[str] = []
                # Scan the raw prompt text for {{var}} placeholders so we can
                # give a precise diagnosis when a variable is missing.
                _placeholders_in_text = set(re.findall(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}", str(combined_task or "")))
                for _v in _required_vars:
                    _val = (format_context or {}).get(_v)
                    if _val is None or str(_val).strip() == "":
                        _missing_vars.append(_v)
                        if _v not in _placeholders_in_text:
                            # Variable name never appears as {{var}} in the prompt text.
                            # The resolver only scans {{...}} placeholders, so this variable
                            # was never looked up from upstream outputs at all.
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
                if _missing_vars:
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
                    return state
        except Exception:
            pass

        # Deterministic local-directory grounding for local-analysis prompts.
        # Variable name is defined by prompt marker, e.g. [LOCAL_DIR_VAR:local_dir].
        def _resolve_local_dir_from_prompt_var(task_text_raw: str, context: dict) -> tuple[str, str]:
            try:
                marker_match = re.search(r"\[LOCAL_DIR_VAR:([a-zA-Z_][a-zA-Z0-9_]*)\]", str(task_text_raw or ""))
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
            try:
                if not dir_path:
                    return ""
                abs_dir = os.path.abspath(os.path.expanduser(dir_path))
                payload: dict[str, Any] = {
                    "dir_path": abs_dir,
                    "exists": os.path.isdir(abs_dir),
                    "file_count": 0,
                    "sample_files": [],
                    "text_snippets": {},
                }
                if not payload["exists"]:
                    payload["error"] = "directory_not_found"
                    return json.dumps(payload, ensure_ascii=False)

                names = sorted(os.listdir(abs_dir))
                payload["file_count"] = len(names)
                payload["sample_files"] = names[:60]

                text_exts = {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".log"}
                picked = 0
                for name in names:
                    if picked >= 3:
                        break
                    fpath = os.path.join(abs_dir, name)
                    if not os.path.isfile(fpath):
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in text_exts:
                        continue
                    try:
                        # Read only small prefix to avoid prompt bloat
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            snippet = f.read(2400)
                        if snippet.strip():
                            payload["text_snippets"][name] = snippet
                            picked += 1
                    except Exception:
                        continue
                return json.dumps(payload, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"snapshot_failed: {e}"}, ensure_ascii=False)

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

        # Global anti-risk guardrails for browser automation.
        # This keeps prompts user-friendly while enforcing a consistent low-risk behavior
        # across different skills/sites (instead of requiring each prompt to repeat it).
        def _append_anti_risk_guardrails(task_text_raw: str) -> str:
            try:
                if not isinstance(task_text_raw, str) or not task_text_raw.strip():
                    return task_text_raw

                # Avoid duplicate injection if already present in task text.
                marker = "[GLOBAL ANTI-RISK GUARDRAILS]"
                if marker in task_text_raw:
                    return task_text_raw

                if skill_name == "rt_chat_bot":
                    tab_guardrail = (
                        "2) If an assigned `tab_id` is provided for this customer-service invocation, "
                        "you may and should focus that assigned tab. Do not switch to unrelated stale tabs "
                        "from previous sessions. If no assigned `tab_id` is available, navigate directly to "
                        "the assigned `chat_url`.\n"
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

        # Skip web anti-risk guardrails for local-directory grounded nodes, otherwise
        # these web-centric instructions may conflict with local-only extraction intent.
        if not _local_dir_grounded:
            combined_task = _append_anti_risk_guardrails(combined_task)

        # ── Suppress duplicate initial-URL navigation for reused sessions ──
        # browser-use auto-detects URLs in the task text and navigates to them
        # on agent startup.  When a persistent browser session already has the
        # target tab open, this creates a duplicate tab.  Strip the chat_url
        # from the task text when we know the session will be reused.
        try:
            if skill_name == "rt_chat_bot":
                _browser_scope_key_check = _resolve_browser_scope_key(state)
                _existing_session = _cached_browser_sessions.get(_browser_scope_key_check)
                # Use _is_session_started (not _is_session_alive) to avoid cross-thread
                # asyncio attribute reads that may incorrectly report the event bus as dead.
                _session_usable = _existing_session is not None and _is_session_started(_existing_session)
                logger.debug(
                    f"[BrowserAutomation] URL strip check: scope={_browser_scope_key_check} "
                    f"cached={'yes' if _existing_session else 'no'} started={_session_usable}"
                )
                if _session_usable:
                    # Session is cached & started → strip bare chat URLs to avoid
                    # browser-use auto-opening a duplicate tab.  Keep URLs inside
                    # JSON payloads (they have surrounding quotes) and inside
                    # markdown/instruction text (preceded by backtick or colon).
                    import re as _re_strip
                    _chat_url_pattern = _re_strip.compile(
                        r'(?<!["\':`,\\])https?://127\.0\.0\.1:9877/chat\?session=\S+'
                    )
                    _stripped = _chat_url_pattern.sub('[assigned chat tab already open]', combined_task)
                    if _stripped != combined_task:
                        logger.info(
                            f"[BrowserAutomation] Stripped bare chat URL from task to prevent "
                            f"duplicate tab (session reused, scope={_browser_scope_key_check})"
                        )
                        combined_task = _stripped
        except Exception as _strip_err:
            logger.debug(f"[BrowserAutomation] URL strip failed: {_strip_err}")

        # print("final_system_prompt:", final_system_prompt)
        # print("final_user_prompt:", final_user_prompt)
        logger.debug("combined_task:", combined_task)
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
            
            try:
                # Execute browser automation with optional hard timeout
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
                            _browser_scope_key = _resolve_browser_scope_key(state)
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
                    if _event_monitor_configs:
                        from agent.ec_skills.llm_utils.llm_utils import run_async_in_persistent_worker_thread
                        _browser_scope_key = _resolve_browser_scope_key(state)
                        _worker_suffix = re.sub(r"[^\w\-]+", "_", f"{skill_name}_{node_name}_{_browser_scope_key}")
                        logger.info(
                            f"[BrowserAutomation] Using persistent worker loop for event-monitored run: "
                            f"{_worker_suffix} "
                            f"(skill={skill_name}, node={node_name}, scope={_browser_scope_key}, "
                            f"task_id={(state.get('attributes') or {}).get('task_id') if isinstance(state, dict) else ''}, "
                            f"chat_id={state.get('chat_id') if isinstance(state, dict) else ''})"
                        )
                        info = run_async_in_persistent_worker_thread(
                            lambda: _run_browser_use(combined_task, mainwin, state, agent_id),
                            worker_name=f"browser-use-persistent-{_worker_suffix}",
                        ) or {}
                    else:
                        from agent.ec_skills.llm_utils.llm_utils import run_async_in_worker_thread
                        info = run_async_in_worker_thread(lambda: _run_browser_use(combined_task, mainwin, state, agent_id)) or {}
                
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
                
                # Log error and push to frontend
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
                    logger.warning(
                        f"[BrowserAutomation] Non-fatal watchdog noise suppressed: {error_msg}"
                    )
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

            # Optionally interrupt if downstream needs human check
            if wait_for_done and info.get("error"):
                interrupt({"i_tag": node_name, "paused_at": node_name, "prompt_to_human": f"Automation pending: {action}"})

            try:
                state["n_steps"] = int(state.get("n_steps", 0) or 0) + 1
            except Exception:
                state["n_steps"] = 1
            # Truncate info for history to avoid huge screenshot_base64 in logs
            from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
            info_for_history = truncate_screenshot_for_logging(info)
            add_to_history(state, ActionMessage(content=f"action: {provider} {task_instructions}; result: {info_for_history}"))

            return state

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
