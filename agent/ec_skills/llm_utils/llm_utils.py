# Standard library imports
import asyncio
import base64
import json
import os
import re
import sys
import time
import uuid
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from threading import Thread
from typing import Any, Dict, Tuple, TYPE_CHECKING

# Third-party library imports
import requests
import httpx
from langchain_community.chat_models import ChatAnthropic
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.types import Interrupt

# Optional third-party imports
try:
    from langchain_aws import ChatBedrock  # type: ignore
except ImportError:
    ChatBedrock = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

# Local application imports
from agent.agent_service import get_agent_by_id
from agent.ec_skills.dev_defs import BreakpointManager
from agent.memory.models import MemoryItem
from utils.env.secure_store import secure_store, get_current_username
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from agent.cloud_worker.cloud_logger import send_skill_editor_log

# Type-only imports to avoid circular dependency
if TYPE_CHECKING:
    from agent.ec_skill import NodeState

def build_a2a_response_message(
    agent_id: str,
    chat_id: str,
    msg_id: str,
    task_id: str,
    msg_text: str,
    sender_name: str,
    msg_type: str = "text",
    i_tag: str = "",
    attachments: list = None,
    card: dict = None,
    code: dict = None,
    form: list = None,
    notification: dict = None,
) -> dict:
    """
    Build a standardized A2A response message structure.
    
    This is the SINGLE SOURCE OF TRUTH for message format used by:
    - a2a_send_chat_message_sync() in ec_agent.py
    - All skill response functions (send_response_back, etc.)
    
    Message structure:
    {
        "id": str,                    # unique message id
        "messages": [                 # REQUIRED by a2a_send_chat_message
            agent_id,                 # [0] sender agent id
            chat_id,                  # [1] chat/session id
            msg_id,                   # [2] message id
            task_id,                  # [3] task id for tracing
            msg_text                  # [4] message text content
        ],
        "attributes": {
            "params": {
                "content": {...},     # message content details
                "attachments": [...], # file attachments
                "chatId": str,        # chat id (redundant but needed by some handlers)
                "senderId": str,      # sender agent id
                "senderName": str,    # sender display name
                ...
            }
        }
    }
    
    Args:
        agent_id: The sending agent's ID
        chat_id: The chat/session ID
        msg_id: Unique message ID (will be generated if empty)
        task_id: Task ID for tracing (can be empty)
        msg_text: The message text content
        sender_name: Display name of the sender
        msg_type: Message type - "text", "form", "notification", "card", "code"
        i_tag: Interaction tag for UI state management
        attachments: List of file attachments
        card: Card data (for card type messages)
        code: Code data (for code type messages)
        form: Form data (for form type messages)
        notification: Notification data (for notification type messages)
    
    Returns:
        dict: Standardized message structure
    """
    if not msg_id:
        msg_id = str(uuid.uuid4())
    
    return {
        "id": str(uuid.uuid4()),
        # Top-level 'messages' array - REQUIRED by ec_agent.a2a_send_chat_message
        # Format: [agent_id, chat_id, msg_id, task_id, msg_txt]
        "messages": [agent_id, chat_id, msg_id, task_id or "", msg_text],
        "attributes": {
            "params": {
                "content": {
                    "type": msg_type,
                    "text": msg_text,
                    "i_tag": i_tag,
                    "dtype": msg_type,
                    "card": card or {},
                    "code": code or {},
                    "form": form or [],
                    "notification": notification or {},
                },
                "attachments": attachments or [],
                "chatId": chat_id,
                "senderId": agent_id,
                "i_tag": i_tag,
                "createAt": int(time.time() * 1000),
                "senderName": sender_name,
                "status": "success",
                "role": "",
                "ext": "",
                "human": False,
            }
        }
    }


def parse_a2a_message_params(params) -> dict:
    """
    Parse A2A message params to extract standardized fields.
    
    This is the SINGLE SOURCE OF TRUTH for reading message params.
    Handles both TaskSendParams objects and dict structures.
    
    Args:
        params: Either a TaskSendParams object or a dict from state["attributes"]["params"]
    
    Returns:
        dict with standardized fields:
        {
            "dtype": str,           # message type: "text", "form", "notification", etc.
            "text": str,            # message text content
            "card": dict,           # card data
            "code": dict,           # code data  
            "form": list,           # form data
            "notification": dict,   # notification data
            "i_tag": str,           # interaction tag
            "role": str,            # sender role
            "senderId": str,        # sender agent id
            "senderName": str,      # sender display name
            "createAt": int,        # timestamp
            "chatId": str,          # chat id
            "status": str,          # message status
            "ext": str,             # extension data
            "attachments": list,    # file attachments
        }
    """
    from agent.a2a.langgraph_agent.utils import TaskSendParams
    
    result = {
        "dtype": "text",
        "text": "",
        "card": {},
        "code": {},
        "form": [],
        "notification": {},
        "i_tag": "",
        "role": "",
        "senderId": "",
        "senderName": "",
        "createAt": None,
        "chatId": "",
        "status": "",
        "ext": "",
        "attachments": [],
    }
    
    try:
        if isinstance(params, TaskSendParams):
            # TaskSendParams object - extract from metadata.params.content
            payload_params = params.metadata.get("params", {}) if params.metadata else {}
            content_meta = payload_params.get("content", {}) if isinstance(payload_params, dict) else {}
            
            if isinstance(content_meta, str):
                try:
                    content_meta = json.loads(content_meta)
                except:
                    content_meta = {}
            
            if isinstance(content_meta, dict):
                result["dtype"] = content_meta.get("dtype", "text")
                result["text"] = content_meta.get("text", "")
                result["card"] = content_meta.get("card", {})
                result["code"] = content_meta.get("code", {})
                result["form"] = content_meta.get("form", [])
                result["notification"] = content_meta.get("notification", {})
                result["i_tag"] = content_meta.get("i_tag", "")
            
            if isinstance(payload_params, dict):
                result["role"] = payload_params.get("role", "")
                result["senderId"] = payload_params.get("senderId", "")
                result["senderName"] = payload_params.get("senderName", "")
                result["createAt"] = payload_params.get("createAt")
                result["chatId"] = payload_params.get("chatId", "")
                result["status"] = payload_params.get("status", "")
                result["ext"] = payload_params.get("ext", "")
                result["attachments"] = payload_params.get("attachments", [])
                if not result["i_tag"]:
                    result["i_tag"] = payload_params.get("i_tag", "")
            
            # Fallback to message role if not in payload_params
            if not result["role"] and params.message:
                result["role"] = params.message.role
                
        elif isinstance(params, dict):
            # Dict structure - could be direct params or nested metadata.params.content
            # Try nested structure first (from A2A response)
            metadata = params.get("metadata", {})
            if isinstance(metadata, dict) and "params" in metadata:
                # Nested structure: params["metadata"]["params"]["content"]
                payload_params = metadata.get("params", {})
                content_meta = payload_params.get("content", {}) if isinstance(payload_params, dict) else {}
            else:
                # Direct structure: params["content"] or params itself
                payload_params = params
                content_meta = params.get("content", {})
            
            if isinstance(content_meta, str):
                try:
                    content_meta = json.loads(content_meta)
                except:
                    content_meta = {}
            
            if isinstance(content_meta, dict):
                result["dtype"] = content_meta.get("dtype", content_meta.get("type", "text"))
                result["text"] = content_meta.get("text", "")
                result["card"] = content_meta.get("card", {})
                result["code"] = content_meta.get("code", {})
                result["form"] = content_meta.get("form", [])
                result["notification"] = content_meta.get("notification", {})
                result["i_tag"] = content_meta.get("i_tag", "")
            
            if isinstance(payload_params, dict):
                result["role"] = payload_params.get("role", "")
                result["senderId"] = payload_params.get("senderId", "")
                result["senderName"] = payload_params.get("senderName", "")
                result["createAt"] = payload_params.get("createAt")
                result["chatId"] = payload_params.get("chatId", "")
                result["status"] = payload_params.get("status", "")
                result["ext"] = payload_params.get("ext", "")
                result["attachments"] = payload_params.get("attachments", [])
                if not result["i_tag"]:
                    result["i_tag"] = payload_params.get("i_tag", "")
    except Exception as e:
        logger.error(f"[parse_a2a_message_params] Error parsing params: {e}")
    
    return result


def rough_token_count(text: str) -> int:
    # Split on whitespace and common punctuations (roughly approximates token count)
    tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return len(tokens)


def parse_json_from_response(response_text):
    # Find JSON content between ```json and ``` or [ and ]
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Fallback: look for array pattern
        json_match = re.search(r'(\[[\s\S]*?\])', response_text)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            return []

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return []


_DATA_URI_STRIP_RE = re.compile(
    r'"data_uri"\s*:\s*"data:image/[^"\\]*(?:\\.[^"\\]*)*"\s*,?\s*'
)


def _resolve_attachment_data_uri(entry: dict) -> str:
    data_uri = entry.get("data_uri")
    if isinstance(data_uri, str) and data_uri.startswith("data:image/"):
        return data_uri
    image_ref = entry.get("image_ref")
    if image_ref:
        try:
            from agent.ec_skills import live_chat_dispatch as _lcd
            # Bridge None -> AttributeError -> same fallback as the old
            # failed lazy import (no image this turn).
            resolved = _lcd.runner_bridge().image_store.get_data_uri(str(image_ref))
            if isinstance(resolved, str) and resolved.startswith("data:image/"):
                return resolved
        except Exception:
            pass
    return ""


def _strip_data_uri_noise(text: str) -> str:
    """Remove ``"data_uri": "data:image/...;base64,..."`` blobs from a JSON-ish
    text string.

    The Q&A worker's user-prompt has the entire dispatch payload (including
    attachment ``data_uri`` fields) inlined as a JSON string.  When we
    promote those attachments to ``image_url`` content parts, leaving the
    base64 blob in the text wastes 2-3 KB of tokens per image and can
    confuse the model with apparent random noise.  This regex-strip removes
    just the ``"data_uri": "..."`` key/value pair (and the trailing comma if
    present) while leaving the surrounding JSON structure intact and human-
    readable.  Best-effort: returns the input unchanged on any error.
    """
    try:
        return _DATA_URI_STRIP_RE.sub("", text)
    except Exception:
        return text


def prep_multi_modal_content(
    state,
    runtime=None,
    *,
    llm=None,
    base_text: str | None = None,
):
    """Build a multimodal HumanMessage ``content`` list from ``state``.

    Two attachment sources are supported (in priority order):

    1. ``state["input"]`` — JSON string (the standard Q&A worker payload)
       carrying ``latest_message_attachments`` per the front-desk → Q&A
       worker contract.  Each entry is a dict with ``kind="image"`` and
       either ``data_uri`` (success) or ``url`` + ``fetch_error`` (URL-
       fallback).  Only ``data_uri`` entries are promoted to ``image_url``
       parts; URL-fallback entries are dropped at debug level.
    2. ``state["attachments"]`` — legacy schema with ``filename`` /
       ``mime_type`` / ``file_data``.  Kept for backward compatibility
       with any caller that pre-populates this field directly.

    Vision capability is gated by ``llm.supports_vision`` when ``llm`` is
    provided — returning ``None`` short-circuits the caller's upgrade path
    so a non-vision model is never sent ``image_url`` parts (which would
    error or be silently dropped).

    Args:
        state:     Node state dict.  ``state["input"]`` may be a JSON
                   string, ``state["attachments"]`` may be a list.
        runtime:   LangGraph runtime (unused; kept for legacy signature).
        llm:       Optional LLM instance for vision-capability gating.
        base_text: Optional override for the leading ``text`` content part.
                   When provided, the ``data_uri`` blobs are stripped from
                   it before use (saves 2-3 KB tokens per image and avoids
                   confusing the model with raw base64).  When omitted, the
                   raw ``state["input"]`` is used (legacy behaviour).

    Returns:
        ``list[dict]`` ready for ``HumanMessage(content=...)`` when at
        least one image part was added; ``None`` otherwise (no images
        found, vision disabled, or any internal failure).  Callers should
        treat ``None`` as "skip the upgrade — keep the original text-only
        HumanMessage".
    """
    try:
        # ── Vision capability gate ─────────────────────────────────────
        if llm is not None:
            try:
                if getattr(llm, "supports_vision", True) is False:
                    logger.info(
                        "[multimodal] prep: skipping — LLM does not support "
                        "vision (set supports_vision=True on the model "
                        "config to enable)"
                    )
                    return None
            except Exception:
                pass  # be permissive — let the call through

        # ── Resolve the leading text part ──────────────────────────────
        # Prefer the caller-supplied base_text (already-rendered prompt);
        # fall back to raw state["input"] for legacy callers.
        if base_text is None:
            base_text = state.get("input", "") if isinstance(state, dict) else ""
        if not isinstance(base_text, str):
            base_text = str(base_text)

        user_content: list[dict] = []
        image_part_count = 0
        lma_count = 0
        image_ref_input_count = 0
        direct_data_uri_count = 0
        resolved_image_ref_count = 0
        fetch_error_count = 0

        # ── Source 1: latest_message_attachments parsed from state["input"] ──
        text_size_before = len(base_text)
        text_size_after = text_size_before
        raw_input = state.get("input") if isinstance(state, dict) else None
        if isinstance(raw_input, str) and raw_input.strip():
            try:
                payload = json.loads(raw_input)
            except (json.JSONDecodeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                lma = payload.get("latest_message_attachments")
                if isinstance(lma, list) and lma:
                    lma_count = len(lma)
                    pending_image_parts: list[dict] = []
                    for entry in lma:
                        if not isinstance(entry, dict):
                            continue
                        kind = entry.get("kind")
                        if kind and kind != "image":
                            continue
                        if entry.get("image_ref"):
                            image_ref_input_count += 1
                        if isinstance(entry.get("data_uri"), str) and entry.get("data_uri", "").startswith("data:image/"):
                            direct_data_uri_count += 1
                        data_uri = _resolve_attachment_data_uri(entry)
                        if not data_uri:
                            err = entry.get("fetch_error")
                            if err:
                                fetch_error_count += 1
                                logger.debug(
                                    f"[multimodal] prep: dropping attachment "
                                    f"with fetch_error={err!r} url={entry.get('url')!r}"
                                )
                            continue
                        if entry.get("image_ref") and not entry.get("data_uri"):
                            resolved_image_ref_count += 1
                        pending_image_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": data_uri,
                                "detail": "auto",
                            },
                        })
                    if pending_image_parts:
                        # Strip the (now redundant) base64 blobs from the
                        # text part — they're fully represented as
                        # image_url content parts.
                        base_text = _strip_data_uri_noise(base_text)
                        text_size_after = len(base_text)
                        # Append text first, then images (OpenAI / Anthropic
                        # both accept either order; text-first is the
                        # convention used by browser-use and most examples).
                        user_content.append({"type": "text", "text": base_text})
                        user_content.extend(pending_image_parts)
                        image_part_count += len(pending_image_parts)

        # ── Source 2: legacy state["attachments"] schema ───────────────
        if image_part_count == 0:
            attachments = state.get("attachments", []) if isinstance(state, dict) else []
            if isinstance(attachments, list) and attachments:
                # Only seed the text part now (we deferred above for the
                # data_uri-strip case).
                user_content.append({"type": "text", "text": base_text})
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    fname = (att.get("filename") or "").lower()
                    mime_type = (att.get("mime_type") or "").lower()
                    if not att.get("file_data"):
                        logger.debug(f"[multimodal] prep: skipping empty file: {fname}")
                        continue
                    data = att["file_data"]
                    if mime_type.startswith("image/"):
                        file_data = (
                            data if isinstance(data, str)
                            else base64.b64encode(data).decode("utf-8")
                        )
                        user_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{file_data}",
                            },
                        })
                        image_part_count += 1
                    elif mime_type == "application/pdf":
                        user_content.append({
                            "type": "text",
                            "text": f"[PDF file: {fname} - PDF content cannot be processed directly]",
                        })
                    elif mime_type.startswith("audio/"):
                        user_content.append({
                            "type": "text",
                            "text": f"[Audio file: {fname} - Audio content cannot be processed directly]",
                        })
                    else:
                        logger.warning(
                            f"[multimodal] prep: unsupported file type "
                            f"{fname} ({mime_type})"
                        )

        if image_part_count == 0:
            # No images materialised — caller should skip the upgrade and
            # keep the existing text-only HumanMessage as-is.
            return None

        logger.info(
            f"[multimodal] prep: built {image_part_count} image part(s) "
            f"(text size {text_size_before}->{text_size_after} chars)"
        )
        if lma_count:
            logger.info(
                "[data-uri-mitigation] llm_multimodal_resolution "
                "attachments=%d image_refs=%d resolved_refs=%d direct_data_uri=%d "
                "fetch_errors=%d image_parts=%d text_chars=%d->%d",
                lma_count,
                image_ref_input_count,
                resolved_image_ref_count,
                direct_data_uri_count,
                fetch_error_count,
                image_part_count,
                text_size_before,
                text_size_after,
            )
        return user_content

    except Exception as e:
        err_trace = get_traceback(e, "ErrorPrepMultiModalContent")
        logger.warning(f"[multimodal] prep failed (non-fatal): {err_trace}")
        return None


def get_country_by_ip() -> str | None:
    """Return country code of current public IP, e.g., 'CN' for China."""
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            logger.debug(f"This host IP lookup result: {resp.json()}")
            return resp.json().get("country")
    except Exception as e:
        logger.warning(f"IP lookup failed: {e}")
    return None


def needs_onboarding(llm_instance) -> bool:
    """
    Check if an LLM instance needs onboarding (API key configuration).
    
    Args:
        llm_instance: LLM instance to check
    
    Returns:
        bool: True if onboarding is needed, False otherwise
    """
    return hasattr(llm_instance, '_needs_onboarding') and llm_instance._needs_onboarding


def get_onboarding_info(llm_instance) -> dict:
    """
    Get onboarding information from an LLM instance.
    
    Args:
        llm_instance: LLM instance
    
    Returns:
        dict: Onboarding information with provider, display_name, and model
    """
    if hasattr(llm_instance, '_onboarding_info'):
        return llm_instance._onboarding_info
    return {}


def pick_llm(default_llm, llm_providers, config_manager=None, allow_fallback=True):
    """
    Return appropriate LLM instance with intelligent provider selection.

    Logic:
    1. First use (default_llm is None):
       - Detect region: US -> OpenAI, CN -> Qwen
       - Create LLM instance (API key can be None)
       - Save selected provider as default_llm
    
    2. Subsequent uses (default_llm has value):
       - Use the default_llm provider
       - Check API key status:
         * If not configured -> Return special marker to show onboarding guide
         * If configured -> Create LLM instance normally

    Args:
        default_llm: Current default LLM provider name (None on first use)
        llm_providers: List of available LLM providers with configuration
        config_manager: Configuration manager instance (optional)
        allow_fallback: If False, only try the specified default_llm without auto-fallback (default: True)

    Returns:
        LLM instance, or dict with {'needs_onboarding': True, 'provider': provider_name} if API key not configured
    """
    from app_context import AppContext
    
    logger.info(f"Starting LLM selection process. Default LLM: {default_llm}, Allow fallback: {allow_fallback}")
    logger.debug(f"Available providers: {[p.get('name') for p in llm_providers]}")
    
    # Case 1: First use - no default_llm specified
    if not default_llm:
        logger.info("First use detected (no default_llm), selecting provider by region")
        country = get_country_by_ip()
        logger.info(f"Detected country: {country}")
        
        # Select regional default provider
        selected_provider = _select_regional_default_provider(country, llm_providers)
        
        if not selected_provider:
            logger.error("Failed to select regional provider")
            return None
        
        logger.info(f"Selected regional provider: {selected_provider['name']} (Model: {selected_provider.get('default_model', 'N/A')})")
        
        # Create LLM instance (allow without API key on first use)
        llm_instance = _create_llm_instance(selected_provider, config_manager=config_manager, allow_no_api_key=True)
        
        if llm_instance:
            # Save this provider as default_llm for future use
            _update_default_llm_via_config_manager(selected_provider['name'], config_manager)
            provider_display = selected_provider.get('display_name', selected_provider['name'])
            model_name = selected_provider.get('default_model', 'default')
            
            # Mark for onboarding since this is first use (no API key configured)
            logger.info(f"⚠️ First use: API key not configured, marking for onboarding")
            llm_instance._needs_onboarding = True
            llm_instance._onboarding_info = {
                'provider': selected_provider.get('name'),
                'display_name': selected_provider.get('display_name', selected_provider.get('name')),
                'model': selected_provider.get('default_model', 'N/A')
            }
            
            logger.info(f"✅ First use: Created LLM instance and saved as default - Provider: {provider_display}, Model: {model_name}")
            return llm_instance
        else:
            logger.error(f"Failed to create LLM instance for {selected_provider['name']}")
            return None
    
    # Case 2: Subsequent uses - default_llm has value
    logger.info(f"Subsequent use detected (default_llm={default_llm})")
    default_provider = _find_provider_by_name(default_llm, llm_providers)
    
    if not default_provider:
        logger.error(f"Default LLM provider '{default_llm}' not found in available providers")
        return None
    
    logger.info(f"Found default provider: {default_provider.get('name')}")
    
    # Check if API key is configured
    is_configured = False
    if default_provider.get('is_local', False):
        # For local providers like Ollama, check base_url
        base_url = default_provider.get('base_url', '')
        if base_url and base_url.strip() and (base_url.strip().startswith('http://') or base_url.strip().startswith('https://')):
            is_configured = True
            logger.info(f"Local provider {default_llm} has valid base_url: {base_url}")
        else:
            logger.warning(f"Local provider {default_llm} has no valid base_url configured")
    else:
        # For cloud providers, check API key
        if default_provider.get('api_key_configured', False):
            is_configured = True
            logger.info(f"Cloud provider {default_llm} has API key configured")
        else:
            logger.warning(f"Cloud provider {default_llm} has NO API key configured")
    
    # Always create LLM instance (use placeholder if API key not configured)
    allow_no_key = not is_configured
    llm_instance = _create_llm_instance(default_provider, config_manager=config_manager, allow_no_api_key=allow_no_key)
    
    if llm_instance:
        provider_display = default_provider.get('display_name', default_llm)
        model_name = default_provider.get('default_model', 'default')
        
        # Mark the instance if onboarding is needed
        if not is_configured:
            logger.warning(f"⚠️ API key not configured for '{default_llm}', marking for onboarding")
            # Add metadata to the instance to indicate onboarding is needed
            llm_instance._needs_onboarding = True
            llm_instance._onboarding_info = {
                'provider': default_provider.get('name'),
                'display_name': default_provider.get('display_name', default_provider.get('name')),
                'model': default_provider.get('default_model', 'N/A')
            }
        
        logger.info(f"✅ Created LLM instance - Provider: {provider_display}, Model: {model_name}, Needs onboarding: {not is_configured}")
        return llm_instance
    else:
        logger.error(f"Failed to create LLM instance for {default_llm}")
        return None


def _find_provider_by_name(provider_name, llm_providers):
    """Find provider by name in the providers list
    
    Supports matching by:
    - provider identifier (canonical, e.g., 'baidu_qianfan')
    - name (display name, e.g., '百度千帆')
    - display_name
    """
    if not provider_name:
        return None
        
    provider_name_lower = provider_name.lower()
    
    # First try exact match on provider identifier (canonical)
    for provider in llm_providers:
        provider_identifier = provider.get('provider', '').lower()
        if provider_identifier == provider_name_lower:
            logger.debug(f"Found provider by identifier match: '{provider_name}' -> '{provider.get('name')}'")
            return provider
    
    # Then try exact match on name (display name)
    for provider in llm_providers:
        if provider.get('name', '').lower() == provider_name_lower:
            return provider
    
    # Then try partial match (for cases like "ChatOpenAI" -> "OpenAI")
    for provider in llm_providers:
        provider_name_in_list = provider.get('name', '').lower()
        if (provider_name_lower in provider_name_in_list or 
            provider_name_in_list in provider_name_lower):
            logger.info(f"Found provider by partial match: '{provider_name}' -> '{provider.get('name')}'")
            return provider
    
    return None


def _select_regional_default_provider(country, llm_providers):
    """Select default provider based on region for first-time use.
    
    This function simply returns the regional default provider without checking API key.
    Used only on first use when no default_llm is set.
    
    Args:
        country: Country code (e.g., 'US', 'CN')
        llm_providers: List of available LLM providers
    
    Returns:
        Selected provider dict or None
    """
    # Define regional defaults (first-time use)
    regional_defaults = {
        'CN': 'qwen',      # China: Qwen (阿里云通义千问)
        'US': 'openai',    # United States: OpenAI
        'default': 'openai'  # Default: OpenAI
    }
    
    default_provider_name = regional_defaults.get(country, regional_defaults['default'])
    logger.info(f"Regional default for {country}: {default_provider_name}")
    
    # Find the provider in the list
    for provider in llm_providers:
        provider_name = provider.get('name', '').lower()
        if default_provider_name.lower() in provider_name:
            logger.info(f"Found regional default provider: {provider.get('name')}")
            return provider
    
    logger.warning(f"Regional default provider '{default_provider_name}' not found, falling back to first available")
    # Fallback: return first available provider
    if llm_providers:
        return llm_providers[0]
    
    return None


def _select_regional_provider(country, llm_providers, exclude_local=False):
    """Select best available provider based on region
    
    Args:
        country: Country code (e.g., 'US', 'CN')
        llm_providers: List of available LLM providers
        exclude_local: If True, exclude local providers (like Ollama) from selection
    
    Returns:
        Selected provider dict or None
    """
    # Define regional preferences
    # Note: CN region excludes providers that are not accessible in China (OpenAI, Claude, Google)
    us_preferences = [
        'openai',        # US provider, preferred in US
        'claude',        # US provider (Anthropic), preferred in US
        'anthropic',     # US provider (Anthropic), preferred in US
        'google',        # US provider (Google), preferred in US
        'gemini',        # US provider (Google), preferred in US
        'deepseek',      # Available globally
        'qwen',          # Available globally
        'qwq',           # Available globally
        'azure',         # Available globally
        'bedrock',       # AWS service, preferred in US
    ]
    
    # Only add local providers if not excluded
    if not exclude_local:
        us_preferences.append('ollama')  # Local deployment
    
    cn_preferences = [
        'deepseek',      # Chinese provider, accessible in CN
        'qwen',          # Chinese provider (Alibaba), accessible in CN
        'qwq',           # Chinese provider (Alibaba DashScope), accessible in CN
        'azure',         # Azure OpenAI (if configured), may be accessible depending on region
        'bedrock',       # AWS Bedrock (if configured), may be accessible depending on region
    ]
    
    # Only add local providers if not excluded
    if not exclude_local:
        cn_preferences.append('ollama')  # Local deployment, accessible anywhere
    
    regional_preferences = {
        'CN': cn_preferences,
        'US': us_preferences,
        'default': us_preferences  # Same as US
    }
    
    preferences = regional_preferences.get(country, regional_preferences['default'])
    logger.debug(f"Regional preferences for {country} (exclude_local={exclude_local}): {preferences}")
    
    # Find first available provider with API key
    for preferred_name in preferences:
        # logger.debug(f"Looking for provider matching: {preferred_name}")
        for provider in llm_providers:
            provider_name = provider.get('name', '').lower()
            api_key_configured = provider.get('api_key_configured', False)
            # logger.debug(f"Checking provider: {provider.get('name')}, API key configured: {api_key_configured}")
            
            if preferred_name.lower() in provider_name:
                # For local providers like Ollama, check if base_url is configured
                if provider.get('is_local', False):
                    base_url = provider.get('base_url', '')
                    if not base_url or not base_url.strip():
                        logger.debug(f"Local provider {provider.get('name')} found but base_url not configured, skipping")
                        continue
                    # Check if base_url is valid
                    base_url = base_url.strip()
                    if not (base_url.startswith('http://') or base_url.startswith('https://')):
                        logger.debug(f"Local provider {provider.get('name')} has invalid base_url: {base_url}, skipping")
                        continue
                    # Local provider with valid base_url
                    logger.info(f"Found matching local provider: {provider.get('name')} for preference: {preferred_name}")
                    return provider
                elif api_key_configured:
                    # Non-local provider with API key configured
                    logger.info(f"Found matching provider: {provider.get('name')} for preference: {preferred_name}")
                    return provider
    
    # If no preferred providers found, try any available provider with API key or valid base_url
    if exclude_local:
        logger.debug("No preferred providers found, trying any available cloud provider with API key")
        for provider in llm_providers:
            # Skip local providers when exclude_local is True
            if provider.get('is_local', False):
                continue
            if provider.get('api_key_configured', False):
                logger.info(f"Found available cloud provider with API key: {provider.get('name')}")
                return provider
    else:
        logger.debug("No preferred providers found, trying any available provider with API key or valid base_url")
        for provider in llm_providers:
            # For local providers, check base_url
            if provider.get('is_local', False):
                base_url = provider.get('base_url', '')
                if base_url and base_url.strip() and (base_url.strip().startswith('http://') or base_url.strip().startswith('https://')):
                    logger.info(f"Found available local provider with valid base_url: {provider.get('name')}")
                    return provider
            elif provider.get('api_key_configured', False):
                # Non-local provider with API key
                logger.info(f"Found available provider with API key: {provider.get('name')}")
                return provider
    
    logger.warning(f"No providers found with configured API keys (exclude_local={exclude_local})")
    return None


def _has_proxy_configured():
    """
    Check if proxy environment variables are configured.
    
    Returns:
        bool: True if any proxy environment variable is set, False otherwise
    """
    import os
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']
    return any(os.environ.get(var) for var in proxy_vars)


def _create_no_proxy_http_client():
    """
    Create httpx Client (sync) and AsyncClient that bypass proxy for domestic APIs.
    
    This is thread-safe and doesn't modify global environment variables.
    
    Optimization: Only creates clients if proxy is actually configured.
    If no proxy, returns (None, None) to use default clients (more efficient).
    
    Why this is needed:
    - Some domestic APIs (DashScope, DeepSeek) may have issues with proxy IPs
    - Alibaba Cloud DashScope: Security policies block proxy IP TLS handshakes
    - DeepSeek: May have similar restrictions for domestic traffic
    
    Why both sync and async?
    - ChatOpenAI uses SYNC http_client for synchronous calls (llm.invoke())
    - Uses ASYNC http_async_client for async calls (llm.ainvoke())
    - Most skill nodes use synchronous calls, so sync client is critical!
    
    Returns:
        Tuple[httpx.Client, httpx.AsyncClient] configured to not use proxy, or (None, None) if:
        - No proxy is configured (optimization: use default clients)
        - httpx is not available
    """
    import os
    
    # Optimization: Only create no-proxy clients if proxy is actually configured
    if not _has_proxy_configured():
        logger.debug(f"[ProxyBypass] No proxy configured, skipping no-proxy client creation")
        return None, None
    
    try:
        import httpx
        
        # Create SYNC client (for llm.invoke() - most common in skills)
        # Use mounts to explicitly bypass proxy by using direct HTTPTransport
        # This is thread-safe and doesn't affect other concurrent LLM creations
        # mounts overrides any proxy settings from environment variables
        sync_client = httpx.Client(
            mounts={
                "http://": httpx.HTTPTransport(),
                "https://": httpx.HTTPTransport(),
            },
            timeout=httpx.Timeout(120.0, connect=30.0),  # 120s total, 30s connect
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        
        # Create ASYNC client (for llm.ainvoke() - less common but needed)
        # Use mounts to explicitly bypass proxy by using direct AsyncHTTPTransport
        async_client = httpx.AsyncClient(
            mounts={
                "http://": httpx.AsyncHTTPTransport(),
                "https://": httpx.AsyncHTTPTransport(),
            },
            timeout=httpx.Timeout(120.0, connect=30.0),  # 120s total, 30s connect
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']
        active_proxies = {var: os.environ.get(var) for var in proxy_vars if os.environ.get(var)}
        logger.info(
            f"[ProxyBypass] Created no-proxy httpx clients (sync + async) "
            f"(bypassing: {', '.join(active_proxies.keys())})"
        )
        return sync_client, async_client
        
    except ImportError:
        logger.warning(f"[ProxyBypass] httpx not available, cannot create no-proxy clients")
        return None, None
    except Exception as e:
        logger.error(f"[ProxyBypass] Error creating no-proxy httpx clients: {e}")
        return None, None


def _select_model_with_priority(
    supported_models,
    original_provider_model,
    provider_name,
    node_model_name=None,
    config_manager=None,
    is_pydantic=False
):
    """
    Helper function to select model with priority: node_model_name > user_selected_model > provider default.
    
    Args:
        supported_models: List of supported models (Pydantic objects or dicts)
        original_provider_model: Provider's default model
        provider_name: Provider name for logging
        node_model_name: Optional model from node configuration (highest priority)
        config_manager: Optional ConfigManager for user-selected model
        is_pydantic: True if supported_models are Pydantic objects, False if dicts
    
    Returns:
        Tuple of (model_name, selected_model_config)
    """
    model_name = original_provider_model
    selected_model_config = None
    
    def matches_model(model, target_name):
        """Check if model matches target name (works for both Pydantic and dict)"""
        if is_pydantic:
            return (target_name == model.model_id or 
                    target_name == model.name or
                    target_name == model.display_name)
        else:
            model_id = model.get('model_id', '')
            model_name_key = model.get('name', '')
            display_name = model.get('display_name', '')
            return (target_name == model_id or 
                    target_name == model_name_key or
                    target_name == display_name)
    
    # Priority 1: node_model_name (highest priority)
    if node_model_name:
        is_valid_model = False
        if supported_models:
            for model in supported_models:
                if matches_model(model, node_model_name):
                    is_valid_model = True
                    selected_model_config = model
                    break
        
        if is_valid_model:
            logger.debug(f"[extract_provider_config] Using node-specified model: {node_model_name}")
            model_name = node_model_name
        else:
            model_name = original_provider_model
            logger.warning(
                f"[extract_provider_config] Node-specified model '{node_model_name}' "
                f"does not belong to provider '{provider_name}'. Using provider's default model '{model_name}' instead."
            )
    
    # Priority 2: user_selected_model (if no node model)
    elif config_manager and hasattr(config_manager, 'general_settings'):
        user_selected_model = config_manager.general_settings.default_llm_model
        if user_selected_model:
            is_valid_model = False
            if supported_models:
                for model in supported_models:
                    if matches_model(model, user_selected_model):
                        is_valid_model = True
                        selected_model_config = model
                        break
            
            if is_valid_model:
                logger.debug(f"[extract_provider_config] Using user-selected model: {user_selected_model} (instead of {model_name})")
                model_name = user_selected_model
            else:
                model_name = original_provider_model
                logger.warning(
                    f"[extract_provider_config] User-selected model '{user_selected_model}' "
                    f"does not belong to provider '{provider_name}'. Using provider's default model '{model_name}' instead."
                )
    
    return model_name, selected_model_config


def extract_provider_config(provider, config_manager=None, node_model_name=None):
    """
    Extract common configuration from provider (dict or LLMProvider object).
    
    This function provides backward compatibility by accepting both:
    - Legacy dict-based provider configurations
    - New LLMProvider class instances
    
    Args:
        provider: Either a dict or LLMProvider instance
        config_manager: Optional ConfigManager to get user-selected model (overrides provider's default)
        node_model_name: Optional model name from node configuration (highest priority)
    
    Returns:
        Dict with:
            - model_name: The model to use (node-specified > user-selected > provider default)
            - api_key: The API key
            - base_url: The base URL (if applicable)
            - provider_type: The provider type (openai, deepseek, etc.)
            - class_name: The class name
            - provider_name: The provider name
            - ... (other metadata)
    """
    import os
    from agent.ec_skills.llm_utils.llm_provider import LLMProvider
    
    # Check if provider is an LLMProvider instance
    if isinstance(provider, LLMProvider):
        # Use the class methods for cleaner code
        # Store the original provider default model for fallback (directly from default_model, not preferred_model)
        # This ensures we get the true provider default, not a user-selected model from another provider
        if provider.default_model:
            original_provider_model = provider.default_model
        elif provider.supported_models:
            original_provider_model = provider.supported_models[0].model_id
        else:
            original_provider_model = None
        
        # Get current model name (may include preferred_model from user settings)
        model_name = provider.get_model_name()
        
        # Select model with priority: node_model_name > user_selected_model > provider default
        model_name, selected_model_config = _select_model_with_priority(
            supported_models=provider.supported_models,
            original_provider_model=original_provider_model,
            provider_name=provider.name,
            node_model_name=node_model_name,
            config_manager=config_manager,
            is_pydantic=True
        )
        
        # Get supports_vision from selected model config
        supports_vision = True  # Default to True
        if selected_model_config:
            supports_vision = getattr(selected_model_config, 'supports_vision', True)
        elif provider.supported_models:
            # Find current model in supported_models
            for model in provider.supported_models:
                if (model.model_id == model_name or 
                    model.name == model_name or
                    model.display_name == model_name):
                    supports_vision = getattr(model, 'supports_vision', True)
                    break
        
        return {
            'model_name': model_name,
            'api_key': provider.get_api_key(),
            'base_url': provider.base_url,
            'provider_type': provider.provider_type.value,
            'class_name': provider.class_name.lower(),
            'provider_name': provider.name.lower(),
            'provider_name_actual': provider.name,
            'provider_display': provider.display_name,
            'api_key_env_vars': provider.api_key_env_vars,
            'is_openai_compatible': provider.is_openai_compatible(),
            'is_browser_use_compatible': provider.is_browser_use_compatible(),
            'temperature': provider.temperature,
            'supports_vision': supports_vision
        }
    
    # Legacy dict-based provider (backward compatibility)
    provider_name = provider.get('name', '').lower()
    supported_models = provider.get('supported_models', [])
    preferred_model = provider.get('preferred_model')
    default_model_name = provider.get('default_model')
    api_key_env_vars = provider.get('api_key_env_vars', [])
    
    # Store the original provider default model for fallback
    original_provider_model = default_model_name
    if not original_provider_model and supported_models:
        # Use the first supported model's model_id as fallback
        first_model = supported_models[0]
        original_provider_model = first_model.get('model_id', first_model.get('name'))
    
    # Determine which model to use (preferred_model may come from user settings)
    model_name = None
    if preferred_model:
        model_name = preferred_model
    elif default_model_name:
        model_name = default_model_name
    elif supported_models:
        # Use the first supported model's model_id
        first_model = supported_models[0]
        model_name = first_model.get('model_id', first_model.get('name'))
    
    # Get supports_vision from model config (default True if not found)
    supports_vision = True  # Default to True
    # Select model with priority: node_model_name > user_selected_model > provider default
    model_name, selected_model_config = _select_model_with_priority(
        supported_models=supported_models,
        original_provider_model=original_provider_model,
        provider_name=provider_name,
        node_model_name=node_model_name,
        config_manager=config_manager,
        is_pydantic=False
    )
    
    # Get supports_vision from the selected/current model config
    if selected_model_config:
        supports_vision = selected_model_config.get('supports_vision', True)
    elif supported_models:
        # Find the current model in supported_models
        for model in supported_models:
            model_id = model.get('model_id', '')
            model_name_key = model.get('name', '')
            display_name = model.get('display_name', '')
            if (model_name == model_id or 
                model_name == model_name_key or
                model_name == display_name):
                supports_vision = model.get('supports_vision', True)
                break
    
    # Get API key from secure store (with user isolation, same as LLMProvider.get_api_key())
    api_key = None
    try:
        from utils.env.secure_store import get_current_username, secure_store
        username = get_current_username()
        for env_var in api_key_env_vars:
            api_key = secure_store.get(env_var, username=username)
            if api_key and api_key.strip():
                break
        
        # Log debug message if no API key found (this is expected on first use)
        if not api_key and api_key_env_vars:
            logger.debug(
                f"[extract_provider_config] No API key found for provider '{provider_name}' "
                f"in secure store. Required env vars: {api_key_env_vars} (this is expected on first use)"
            )
    except Exception as e:
        logger.error(
            f"[extract_provider_config] Failed to get API key for provider '{provider_name}': {e}"
        )
    
    # Extract other configs
    base_url = provider.get('base_url')
    provider_type = provider.get('provider', '').lower()
    class_name = provider.get('class_name', '').lower()
    
    # Fallback: if provider_type is empty, try to infer from provider_name or class_name
    if not provider_type:
        if 'deepseek' in provider_name or 'chatdeepseek' == class_name:
            provider_type = 'deepseek'
        elif 'qwen' in provider_name or 'qwq' in provider_name or 'chatqwq' == class_name:
            provider_type = 'dashscope'  # QwQ uses DashScope
        elif 'openai' in provider_name or 'chatopenai' == class_name:
            provider_type = 'openai'
        elif 'ollama' in provider_name or 'chatollama' == class_name:
            provider_type = 'ollama'
        elif 'ryoais' in provider_name:
            provider_type = 'ryoais'
        elif 'ecanai' in provider_name:
            provider_type = 'ecanai'
        elif 'kimi' in provider_name or 'moonshot' in provider_name:
            provider_type = 'moonshot'
        elif 'minimax' in provider_name:
            provider_type = 'minimax'
        elif 'anthropic' in provider_name or 'claude' in provider_name or 'chatanthropic' == class_name:
            provider_type = 'anthropic'
        elif 'azure' in provider_name or 'azureopenai' == class_name:
            provider_type = 'azure_openai'
        else:
            # Default to provider_name if still empty
            provider_type = provider_name
    
    # Ensure api_key and base_url are not None (use empty string or placeholder)
    # This prevents 'NoneType' object is not subscriptable errors in downstream code
    if api_key is None:
        # Providers that allow unauthenticated access still need a non-empty
        # value because the OpenAI client validates this constructor argument.
        if provider_type in ['ollama', 'ryoais']:
            api_key = 'sk-placeholder-key-for-local-llm'
        else:
            api_key = ''
    
    return {
        'model_name': model_name,
        'api_key': api_key,
        'base_url': base_url,
        'provider_type': provider_type,
        'class_name': class_name,
        'provider_name': provider_name,
        'provider_name_actual': provider.get('name', provider_name),
        'provider_display': provider.get('display_name', provider.get('name', provider_name)),
        'api_key_env_vars': api_key_env_vars,
        'temperature': provider.get('temperature', 0.7),
        'supports_vision': supports_vision
    }


def _create_llm_instance(provider, config_manager=None, allow_no_api_key=False):
    """
    Create LLM instance based on provider configuration.
    
    Args:
        provider: Provider configuration (dict or LLMProvider object)
        config_manager: Optional ConfigManager to get user-selected model
        allow_no_api_key: If True, create instance with placeholder API key when no API key is configured (for first-time use)
    """
    import os
    
    try:
        # Extract common configuration (with user-selected model if available)
        config = extract_provider_config(provider, config_manager=config_manager)
        
        model_name = config['model_name']
        api_key = config['api_key']
        base_url = config.get('base_url')  # Extract base_url from config
        provider_name = config['provider_name']
        provider_type = config['provider_type']
        class_name = config['class_name']
        provider_display = config['provider_display']
        provider_name_actual = config['provider_name_actual']
        
        logger.info(f"Creating LLM instance - Provider: {provider_display} ({provider_name_actual}), Model: {model_name}")
        logger.info(f"[DEBUG] provider_name={provider_name}, class_name={class_name}, provider_type={provider_type}, base_url={base_url}")
        
        # Helper to get API key from secure store with user isolation (no env fallback)
        def get_api_key(env_var):
            try:
                # Get current username for user isolation
                username = get_current_username()
                return secure_store.get(env_var, username=username)
            except Exception:
                return None
        
        # ============================================================
        # PRIORITY 1: Special provider_name checks (highest priority)
        # These must be checked FIRST to avoid misidentification
        # ============================================================
        
        # eCanAI is an OpenAI-compatible managed proxy.
        if 'ecanai' in provider_name.lower():
            if not api_key:
                logger.error("eCanAI requires ECANAI_LLM_API_KEY in secure_store")
                return None
            base_url = (base_url or 'https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1').rstrip('/')
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=0,
            )

        # Check for RyoAIS (uses class_name=chatopenai, must check before OpenAI)
        if 'ryoais' in provider_name.lower():
            model_name = model_name or 'qwen2.5-72b-instruct'
            
            logger.info(f"[RyoAIS] Starting RyoAIS LLM creation - base_url from config: {base_url}")
            
            # RyoAIS already uses /v1 endpoint format
            base_url = base_url.rstrip('/') if base_url else 'http://localhost/v1'
            
            logger.info(f"[RyoAIS] Creating ChatOpenAI with model={model_name}, base_url={base_url}")
            
            # Get API key from secure store (uses RYOAIS_LLM_API_KEY)
            from gui.manager.provider_settings_helper import get_ollama_api_key
            ryoais_api_key = get_ollama_api_key('llm', provider_identifier='ryoais')
            
            # NOTE: RyoAIS 服务端控制 thinking 模式，客户端不需要设置
            llm_instance = ChatOpenAI(
                model=model_name,
                api_key=ryoais_api_key,
                base_url=base_url,
                temperature=0,
                # RyoAIS may be deployed on a LAN/private endpoint with a
                # self-signed certificate. This matches its model discovery,
                # provider probe and LightRAG runtime behaviour.
                http_client=httpx.Client(verify=False),
                http_async_client=httpx.AsyncClient(verify=False),
            )
            
            logger.info(f"[RyoAIS] Successfully created RyoAIS LLM instance")
            logger.info(f"[RyoAIS] Instance details - model: {llm_instance.model_name}, base_url: {llm_instance.openai_api_base if hasattr(llm_instance, 'openai_api_base') else 'N/A'}")
            
            return llm_instance
        
        # Check for Ollama (uses class_name=chatopenai, must check before OpenAI)
        elif 'ollama' in provider_name.lower():
            model_name = model_name or 'llama3.2'
            
            logger.info(f"[Ollama] Starting Ollama LLM creation - base_url from config: {base_url}")
            
            # Convert native Ollama URL to OpenAI-compatible endpoint
            original_base_url = base_url
            base_url = base_url.rstrip('/') if base_url else ''
            if base_url and not base_url.endswith('/v1'):
                base_url = f"{base_url}/v1"
            
            logger.info(f"[Ollama] Converted base_url: {original_base_url} -> {base_url}")
            logger.info(f"[Ollama] Creating ChatOpenAI with model={model_name}, base_url={base_url}")
            
            # Get API key from secure store (same as other providers)
            from gui.manager.provider_settings_helper import get_ollama_api_key
            ollama_api_key = get_ollama_api_key('llm')
            
            llm_instance = ChatOpenAI(
                model=model_name,
                api_key=ollama_api_key,
                base_url=base_url,
                temperature=0
            )
            
            logger.info(f"[Ollama] Successfully created Ollama LLM instance")
            logger.info(f"[Ollama] Instance details - model: {llm_instance.model_name}, base_url: {llm_instance.openai_api_base if hasattr(llm_instance, 'openai_api_base') else 'N/A'}")
            
            return llm_instance
        
        # Check for DeepSeek
        elif 'deepseek' in provider_name.lower():
            model_name = model_name or 'deepseek-chat'
            # DeepSeek requires DEEPSEEK_API_KEY in secure_store
            deepseek_api_key = get_api_key('DEEPSEEK_API_KEY')
            if not deepseek_api_key:
                logger.error("DeepSeek requires DEEPSEEK_API_KEY in secure_store")
                return None
            
            # DeepSeek API endpoint (China-based service)
            base_url = base_url or 'https://api.deepseek.com'
            
            # DeepSeek is a China-based service that may have proxy restrictions
            # Use the same thread-safe no-proxy approach as DashScope
            # Optimization: Only creates no-proxy clients if proxy is configured
            logger.debug(f"[DeepSeek] Creating ChatDeepSeek with base_url={base_url}")
            
            sync_client, async_client = _create_no_proxy_http_client()
            
            if sync_client or async_client:
                logger.debug(f"[DeepSeek] Using no-proxy httpx clients (domestic API)")
                
                llm_instance = ChatDeepSeek(
                    model=model_name,
                    api_key=deepseek_api_key,
                    base_url=base_url,
                    temperature=0,
                    timeout=120.0,
                    http_client=sync_client,  # Use custom SYNC client that bypasses proxy
                    http_async_client=async_client  # Use custom ASYNC client that bypasses proxy
                )
                
                return llm_instance
            else:
                # No proxy configured - use default clients (more efficient)
                logger.debug(f"[DeepSeek] Using default httpx clients (no proxy configured)")
                return ChatDeepSeek(
                    model=model_name,
                    api_key=deepseek_api_key,
                    base_url=base_url,
                    temperature=0,
                    timeout=120.0
                )
        
        # Check for Qwen/QwQ
        elif 'qwen' in provider_name.lower() or 'qwq' in provider_name.lower():
            model_name = model_name or 'qwq-plus'
            # QwQ/DashScope requires DASHSCOPE_API_KEY in secure_store
            dashscope_api_key = get_api_key('DASHSCOPE_API_KEY')
            if not dashscope_api_key:
                if allow_no_api_key:
                    logger.info("Qwen/DashScope API key not configured, using placeholder for first-time setup")
                    dashscope_api_key = "sk-placeholder-key-for-first-time-setup"
                else:
                    logger.error("QwQ requires DASHSCOPE_API_KEY in secure_store")
                    return None
            
            # DashScope OpenAI-compatible endpoint (Alibaba Cloud - China-based)
            base_url = base_url or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
            
            # IMPORTANT: Alibaba Cloud DashScope doesn't respond to TLS handshakes from proxy IPs
            # due to security policies (DDoS protection, proxy IP blacklist, or SNI detection).
            # 
            # Solution: Create custom httpx clients (sync + async) that don't use proxy.
            # This is THREAD-SAFE and doesn't affect other concurrent LLM creations (unlike modifying env vars).
            logger.debug(f"[DashScope] Creating ChatOpenAI with base_url={base_url}")
            
            # Create no-proxy httpx clients (thread-safe, doesn't modify global env vars)
            # Optimization: Only creates if proxy is configured
            sync_client, async_client = _create_no_proxy_http_client()
            
            if sync_client or async_client:
                logger.debug(f"[DashScope] Using no-proxy httpx clients (Alibaba Cloud security policy)")
                
                llm_instance = ChatOpenAI(
                    model=model_name,
                    api_key=dashscope_api_key,
                    base_url=base_url,
                    temperature=0,
                    http_client=sync_client,
                    http_async_client=async_client
                )
                
                return llm_instance
            else:
                # No proxy configured - use default clients (more efficient)
                logger.debug(f"[DashScope] Using default httpx clients (no proxy configured)")
                return ChatOpenAI(
                    model=model_name,
                    api_key=dashscope_api_key,
                    base_url=base_url,
                    temperature=0
                )
        
        # Check for Baidu Qianfan - use OpenAI-compatible V2 API
        elif 'baidu' in provider_name.lower() or 'qianfan' in provider_name.lower():
            model_name = model_name or 'ernie-4.0-8k'
            # Baidu Qianfan V2 API uses OpenAI-compatible format with Bearer token
            baidu_api_key = get_api_key('BAIDU_API_KEY')
            if not baidu_api_key:
                logger.error("Baidu Qianfan requires BAIDU_API_KEY in secure_store")
                return None
            
            # Baidu Qianfan OpenAI-compatible V2 API endpoint
            base_url = base_url or 'https://qianfan.baidubce.com/v2'
            
            try:
                # Create no-proxy httpx clients for Baidu Qianfan (domestic API, bypass proxy)
                sync_client, async_client = _create_no_proxy_http_client()
                
                if sync_client or async_client:
                    logger.debug(f"[Baidu Qianfan] Using no-proxy httpx clients (domestic API, bypassing proxy)")
                    
                    # ChatOpenAI supports both http_client and http_async_client
                    llm_instance = ChatOpenAI(
                        model=model_name,
                        api_key=baidu_api_key,
                        base_url=base_url,
                        temperature=0,
                        http_client=sync_client,  # Use custom SYNC client that bypasses proxy
                        http_async_client=async_client  # Use custom ASYNC client that bypasses proxy
                    )
                    
                    return llm_instance
                else:
                    # No proxy configured - use default clients (more efficient, direct connection)
                    logger.debug(f"[Baidu Qianfan] Using default httpx clients (no proxy configured)")
                    return ChatOpenAI(
                        model=model_name,
                        api_key=baidu_api_key,
                        base_url=base_url,
                        temperature=0
                    )
            except Exception as e:
                logger.error(f"Failed to create Baidu Qianfan ChatOpenAI instance: {e}")
                return None
        
        # Check for Bytedance Doubao - use OpenAI-compatible API (Volcano Engine)
        elif 'bytedance' in provider_name.lower() or 'doubao' in provider_name.lower():
            model_name = model_name or 'doubao-pro-256k'
            # Bytedance Doubao (Volcano Engine) uses OpenAI-compatible format
            ark_api_key = get_api_key('ARK_API_KEY')
            if not ark_api_key:
                logger.error("Bytedance Doubao requires ARK_API_KEY in secure_store")
                return None
            
            # Bytedance Doubao OpenAI-compatible API endpoint (Volcano Engine)
            base_url = base_url or 'https://ark.cn-beijing.volces.com/api/v3'
            
            try:
                # Create no-proxy httpx clients for Bytedance (domestic API, bypass proxy)
                sync_client, async_client = _create_no_proxy_http_client()
                
                if sync_client or async_client:
                    logger.debug(f"[Bytedance Doubao] Using no-proxy httpx clients (domestic API, bypassing proxy)")
                    
                    # ChatOpenAI supports both http_client and http_async_client
                    llm_instance = ChatOpenAI(
                        model=model_name,
                        api_key=ark_api_key,
                        base_url=base_url,
                        temperature=0,
                        http_client=sync_client,  # Use custom SYNC client that bypasses proxy
                        http_async_client=async_client  # Use custom ASYNC client that bypasses proxy
                    )
                    
                    return llm_instance
                else:
                    # No proxy configured - use default clients (more efficient, direct connection)
                    logger.debug(f"[Bytedance Doubao] Using default httpx clients (no proxy configured)")
                    return ChatOpenAI(
                        model=model_name,
                        api_key=ark_api_key,
                        base_url=base_url,
                        temperature=0
                    )
            except Exception as e:
                logger.error(f"Failed to create Bytedance Doubao ChatOpenAI instance: {e}")
                return None
        
        # ============================================================
        # PRIORITY 2: class_name exact matches (medium priority)
        # These are specific LLM classes that need special handling
        # ============================================================
        
        # Check for Azure OpenAI (specific class_name match - must be before OpenAI check)
        elif class_name == 'azureopenai' or ('azure' in provider_name.lower() and 'openai' in provider_name.lower()):
            model_name = model_name or 'gpt-4'
            # Azure OpenAI requires AZURE_ENDPOINT and AZURE_OPENAI_API_KEY from secure_store
            azure_endpoint = get_api_key('AZURE_ENDPOINT')
            api_key = get_api_key('AZURE_OPENAI_API_KEY')
            if azure_endpoint and api_key:
                # Extract deployment name from model_name if needed
                deployment_name = model_name
                return AzureChatOpenAI(
                    azure_endpoint=azure_endpoint,
                    api_key=api_key,
                    azure_deployment=deployment_name,
                    api_version="2024-02-15-preview",
                    temperature=0
                )
            else:
                logger.error(f"Azure OpenAI requires AZURE_ENDPOINT and AZURE_OPENAI_API_KEY in secure_store")
                return None
        
        # Check for AWS Bedrock (specific class_name match)
        elif 'chatbedrockconverse' == class_name or 'bedrock' in provider_name.lower():
            if ChatBedrock is None:
                logger.error("ChatBedrock is not available. Install with: pip install langchain-aws")
                return None
            model_name = model_name or 'anthropic.claude-3-sonnet-20240229-v1:0'
            # AWS Bedrock requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in secure_store
            aws_access_key_id = get_api_key('AWS_ACCESS_KEY_ID')
            aws_secret_access_key = get_api_key('AWS_SECRET_ACCESS_KEY')
            if not aws_access_key_id or not aws_secret_access_key:
                logger.error("AWS Bedrock requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in secure_store")
                return None
            try:
                # ChatBedrock will use credentials available to boto3; ensure credentials are provided via secure_store
                return ChatBedrock(
                    model_id=model_name,
                    model_kwargs={'temperature': 0}
                )
            except Exception as e:
                logger.error(f"Failed to create ChatBedrock instance: {e}")
                return None
        
        # Check for Google Gemini (specific class_name match)
        elif 'chatgooglegenerativeai' == class_name or 'google' in provider_name.lower() or 'gemini' in provider_name.lower():
            if ChatGoogleGenerativeAI is None:
                logger.error("ChatGoogleGenerativeAI is not available. Install with: pip install langchain-google-genai")
                return None
            model_name = model_name or 'gemini-pro'
            # Google Gemini requires GEMINI_API_KEY in secure_store
            gemini_api_key = get_api_key('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.error("Google Gemini requires GEMINI_API_KEY in secure_store")
                return None
            try:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=gemini_api_key,
                    temperature=0
                )
            except Exception as e:
                logger.error(f"Failed to create ChatGoogleGenerativeAI instance: {e}")
                return None
        
        # Check for Anthropic Claude
        elif 'chatanthropic' == class_name or 'claude' in provider_name.lower() or 'anthropic' in provider_name.lower():
            model_name = model_name or 'claude-3-5-sonnet-20241022'
            # Anthropic requires ANTHROPIC_API_KEY in secure_store
            anthropic_api_key = get_api_key('ANTHROPIC_API_KEY')
            if not anthropic_api_key:
                logger.error("Anthropic requires ANTHROPIC_API_KEY in secure_store")
                return None
            return ChatAnthropic(
                model=model_name,
                api_key=anthropic_api_key,
                temperature=0
            )
        
        # ============================================================
        # PRIORITY 3: Generic OpenAI fallback (lowest priority)
        # This catches any remaining chatopenai class_name or openai provider_name
        # ============================================================
        
        # Check for generic OpenAI (fallback for any OpenAI-compatible provider)
        elif class_name == 'chatopenai' or 'openai' in provider_name.lower():
            model_name = model_name or 'gpt-4o'
            # OpenAI requires OPENAI_API_KEY in secure_store
            openai_api_key = get_api_key('OPENAI_API_KEY')
            if not openai_api_key:
                if allow_no_api_key:
                    logger.info("OpenAI API key not configured, using placeholder for first-time setup")
                    openai_api_key = "sk-placeholder-key-for-first-time-setup"
                else:
                    logger.error("OpenAI requires OPENAI_API_KEY in secure_store")
                    return None
            return ChatOpenAI(
                model=model_name,
                api_key=openai_api_key,
                temperature=0
            )
        
        # Unknown provider
        else:
            logger.warning(f"Unknown provider type: {provider_name} (class_name: {class_name}, provider: {provider_type})")
            return None
            
    except Exception as e:
        provider_name = getattr(provider, 'name', None) or (provider.get('name') if isinstance(provider, dict) else 'unknown')
        logger.error(f"Error creating LLM instance for {provider_name}: {e}")
        return None


def is_provider_browser_use_compatible(provider_type: str) -> bool:
    """
    Check if a provider type is compatible with browser_use.
    
    Args:
        provider_type: Provider type string (e.g., 'openai', 'anthropic')
        
    Returns:
        True if provider is browser_use compatible
        
    Examples:
        >>> is_provider_browser_use_compatible('openai')
        True
        >>> is_provider_browser_use_compatible('anthropic')
        False
    """
    openai_compatible_providers = [
        'openai',
        'azure_openai',
        'deepseek',
        'dashscope',
        'ollama',
        'ryoais',
        'ecanai',
        'qwen',
        'qwq',
        'zhipuai',
        'bytedance',
        'baidu_qianfan',
        'moonshot',
        'minimax'
    ]
    return provider_type.lower() in openai_compatible_providers


def get_browser_use_supported_providers() -> list:
    """
    Get list of provider types that are supported by browser_use.
    
    Returns:
        List of supported provider type strings
        
    Examples:
        >>> providers = get_browser_use_supported_providers()
        >>> 'openai' in providers
        True
    """
    return [
        'openai',
        'azure_openai',
        'deepseek',
        'dashscope',
        'ollama',
        'ryoais',
        'ecanai',
        'qwen',
        'qwq',
        'zhipuai',
        'bytedance',
        'baidu_qianfan',
        'moonshot',
        'minimax'
    ]


def _get_logging_browser_use_class():
    """
    Get a LoggingBrowserUseChatOpenAI class that wraps BrowserUseChatOpenAI with custom logging.
    
    This class intercepts all LLM chat completion responses and logs them using logger_helper.
    
    Returns:
        LoggingBrowserUseChatOpenAI class or None if browser_use is not available
    """
    try:
        from functools import wraps
        from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
        from agent.ec_skills.llm_utils.output_cleaner import clean_llm_output
        
        class LoggingBrowserUseChatOpenAI(BrowserUseChatOpenAI):
            """BrowserUseChatOpenAI with custom logging and generic output cleaning for all LLM responses."""
            
            def __init__(self, *args, **kwargs):
                """Initialize with all parent class parameters."""
                super().__init__(*args, **kwargs)
            
            def get_client(self):
                client = super().get_client()
                original_create = client.chat.completions.create
                
                @wraps(original_create)
                async def create_with_logging(*args, **kwargs):
                    # Step 1: Log request details and call LLM with detailed error handling
                    import time
                    start_time = time.time()
                    
                    # Extract request info for logging
                    model = kwargs.get('model', 'unknown')
                    base_url = getattr(client, 'base_url', 'unknown')
                    timeout = kwargs.get('timeout')
                    if timeout is None:
                        timeout = (
                            getattr(self, 'timeout', None)
                            or getattr(self, 'request_timeout', None)
                            or getattr(self, 'default_timeout', None)
                            or 'default'
                        )
                    
                    # Calculate request data size
                    messages = kwargs.get('messages', [])
                    total_chars = 0
                    message_count = len(messages)
                    
                    for msg in messages:
                        if isinstance(msg, dict):
                            content = msg.get('content', '')
                            if isinstance(content, str):
                                total_chars += len(content)
                            elif isinstance(content, list):
                                # Handle multi-part content (text + images)
                                for part in content:
                                    if isinstance(part, dict) and part.get('type') == 'text':
                                        total_chars += len(part.get('text', ''))
                    
                    # Estimate tokens (conservative: 2.5 chars/token for mixed content)
                    est_tokens = int(total_chars / 2.5) if total_chars > 0 else 0
                    
                    logger.info(
                        f"[BrowserUse] 🚀 Calling LLM: model={model}, messages={message_count}, "
                        f"chars={total_chars:,}, est_tokens={est_tokens:,}, "
                        f"base_url={base_url}, timeout={timeout}"
                    )
                    # Check cancellation before starting the LLM call.
                    # _ec_cancellation_event is set directly on the instance by build_node.py
                    # after the registry lookup, which is more reliable than re-deriving task_id.
                    _cancel_evt = getattr(self, "_ec_cancellation_event", None)
                    if _cancel_evt and _cancel_evt.is_set():
                        raise asyncio.CancelledError("Task cancelled before browser LLM call")

                    try:
                        # Wrap in a Task so we can cancel mid-flight when stop is pressed.
                        # Poll every 0.5s for the cancellation event, same as _invoke_hybrid.
                        _llm_fut = asyncio.ensure_future(original_create(*args, **kwargs))
                        try:
                            while not _llm_fut.done():
                                _cancel_evt_poll = getattr(self, "_ec_cancellation_event", None)
                                if _cancel_evt_poll and _cancel_evt_poll.is_set():
                                    _llm_fut.cancel()
                                    logger.info("[BrowserUse] Task cancelled during LLM call")
                                    raise asyncio.CancelledError("Task cancelled during browser LLM call")
                                await asyncio.sleep(0.5)
                            response = _llm_fut.result()
                        except asyncio.CancelledError:
                            if not _llm_fut.done():
                                _llm_fut.cancel()
                            raise
                        elapsed = time.time() - start_time
                        logger.info(f"[BrowserUse] ? LLM responded in {elapsed:.2f}s")
                        try:
                            from agent.ec_skills.token_tracker import token_tracker as _token_tracker
                            _ctx = getattr(self, "_ec_token_context", {}) or {}
                            _token_tracker.record_llm_usage(
                                response,
                                source_type="skill_browser_llm_call",
                                source_id=_ctx.get("source_id"),
                                source_name=_ctx.get("source_name"),
                                session_id=_ctx.get("session_id"),
                                node_type="browser_automation",
                                metadata={
                                    "skill_name": _ctx.get("skill_name"),
                                    "node_name": _ctx.get("node_name"),
                                    "task_id": _ctx.get("task_id"),
                                    "run_id": _ctx.get("run_id"),
                                    "browser_scope_key": _ctx.get("browser_scope_key"),
                                    "model_requested": model,
                                    "base_url": str(base_url),
                                    "message_count": message_count,
                                    "request_chars": total_chars,
                                    "request_est_tokens": est_tokens,
                                    "elapsed_seconds": round(elapsed, 4),
                                    "path": "browser_use_raw_call",
                                },
                            )
                        except Exception as _tk_err:
                            logger.debug(f"[BrowserUse] TokenTracker raw-call record failed: {_tk_err}")
                        
                    except TimeoutError as e:
                        elapsed = time.time() - start_time
                        logger.error(f"[BrowserUse] ⏱️ TIMEOUT after {elapsed:.2f}s: {e}")
                        logger.error(f"[BrowserUse] Model: {model}, Base URL: {base_url}")
                        logger.error(f"[BrowserUse] 💡 Hint: Service is too slow or not responding")
                        raise
                        
                    except ConnectionError as e:
                        elapsed = time.time() - start_time
                        logger.error(f"[BrowserUse] 🔌 CONNECTION ERROR after {elapsed:.2f}s: {e}")
                        logger.error(f"[BrowserUse] Base URL: {base_url}")
                        logger.error(f"[BrowserUse] Error type: {type(e).__name__}")
                        
                        # Provide specific hints based on error
                        error_str = str(e).lower()
                        if 'connection refused' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Service may not be running at {base_url}")
                        elif 'connection reset' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Connection was reset by the server")
                        
                        raise
                        
                    except Exception as e:
                        elapsed = time.time() - start_time
                        error_type = type(e).__name__
                        logger.error(f"[BrowserUse] ❌ LLM CALL FAILED after {elapsed:.2f}s: {error_type}: {e}")
                        logger.error(f"[BrowserUse] Model: {model}, Base URL: {base_url}")
                        
                        # Log detailed exception info
                        import traceback
                        logger.error(f"[BrowserUse] Exception details:\n{traceback.format_exc()}")
                        
                        # Provide hints based on error message
                        error_str = str(e).lower()
                        if 'connection refused' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Service may not be running at {base_url}")
                        elif 'timeout' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Service is too slow or not responding")
                        elif 'name or service not known' in error_str or 'nodename nor servname provided' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Cannot resolve hostname {base_url}")
                        elif 'connection reset' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Connection was reset by the server")
                        elif '401' in error_str or 'unauthorized' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Invalid API key or authentication failed")
                        elif '404' in error_str or 'not found' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Model or endpoint not found")
                        elif '500' in error_str or 'internal server error' in error_str:
                            logger.error(f"[BrowserUse] 💡 Hint: Server internal error, check service logs")
                        
                        raise
                    
                    # Step 2: Log organization header
                    try:
                        org = response.response.headers.get("openai-organization")
                        if org:
                            logger.info(f"[BrowserUse] OpenAI organization: {org}")
                    except AttributeError:
                        pass
                    
                    # Step 3: Log and apply generic output cleaning for ALL providers
                    try:
                        if hasattr(response, 'choices') and response.choices and len(response.choices) > 0:
                            message = response.choices[0].message
                            if hasattr(message, 'content') and message.content:
                                content = message.content
                                logger.debug(f"[BrowserUse] Received LLM response, length: {len(content)}")
                                logger.debug(f"[BrowserUse] LLM Response preview: {content[:200]}...")
                                
                                # Apply generic cleaning (markdown blocks, think tags, JSON extraction)
                                # Safe for all providers - only removes formatting artifacts
                                cleaned = clean_llm_output(content)
                                if cleaned != content:
                                    logger.info(f"[BrowserUse] 🧹 Applied generic output cleaning (original: {len(content)}, cleaned: {len(cleaned)})")
                                    logger.debug(f"[BrowserUse] Cleaned preview: {cleaned[:200]}...")
                                    message.content = cleaned
                            else:
                                logger.debug(f"[BrowserUse] LLM response has no content")
                    except Exception as e:
                        logger.error(f"[BrowserUse] ❌ Failed to log/clean response: {e}", exc_info=True)
                    
                    return response
                
                client.chat.completions.create = create_with_logging
                return client
        
        return LoggingBrowserUseChatOpenAI
    except ImportError:
        logger.error("[_get_logging_browser_use_class] Failed to import browser_use.llm.ChatOpenAI")
        return None


def _create_and_validate_browser_use_llm(bu_config: dict):
    """
    Create and validate a BrowserUseChatOpenAI instance with custom logging.
    
    This helper function ensures that only BrowserUseChatOpenAI instances are returned,
    preventing incompatible LLM types from being passed to browser_use.
    The returned instance includes custom logging for all LLM responses.
    
    Args:
        bu_config: Configuration dict for BrowserUseChatOpenAI (model, api_key, base_url, etc.)
                   Special keys:
                   - adapt_deepseek_output: bool - Apply DeepSeek output format adapter
        
    Returns:
        LoggingBrowserUseChatOpenAI instance or None if creation/validation fails
    """
    try:
        from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
        
        # Extract special config flags
        adapt_deepseek_output = bu_config.pop('adapt_deepseek_output', False)
        adapt_qwen_output = bu_config.pop('adapt_qwen_output', False)
        # Save provider_type_id before removing it (needed for guided_json detection)
        provider_type_id = bu_config.get('provider_type_id', '')
        # Remove provider_type_id (not a valid LLM param)
        bu_config.pop('provider_type_id', None)
        
        # Remove extra_body parameter - BrowserUseChatOpenAI doesn't support it
        # This parameter is used for standard LangChain ChatOpenAI (e.g., Qwen thinking control)
        # but browser_use's ChatOpenAI wrapper doesn't accept it
        if 'extra_body' in bu_config:
            extra_body_value = bu_config.pop('extra_body')
            logger.debug(
                f"[_create_and_validate_browser_use_llm] Removed unsupported 'extra_body' parameter: {extra_body_value}"
            )
        
        # Get the logging wrapper class
        LoggingBrowserUseChatOpenAI = _get_logging_browser_use_class()
        
        if LoggingBrowserUseChatOpenAI is None:
            logger.warning("[_create_and_validate_browser_use_llm] Logging wrapper not available, using base class")
            llm_instance = BrowserUseChatOpenAI(**bu_config)
        else:
            # Create the logging-enabled instance
            llm_instance = LoggingBrowserUseChatOpenAI(**bu_config)
            logger.debug("[_create_and_validate_browser_use_llm] Created LLM with custom logging enabled")
        
        # Apply DeepSeek output format adapter if enabled
        if adapt_deepseek_output:
            try:
                from agent.ec_skills.browser_use_extension.deepseek_adapter import wrap_llm_with_compatible_output
                llm_instance = wrap_llm_with_compatible_output(llm_instance)
                logger.info("[_create_and_validate_browser_use_llm] ✅ Applied DeepSeek output format adapter")
            except Exception as e:
                logger.warning(f"[_create_and_validate_browser_use_llm] Failed to apply DeepSeek output adapter: {e}")
        
        # Apply Qwen/Ollama output format adapter if enabled
        if adapt_qwen_output:
            try:
                from agent.ec_skills.browser_use_extension.qwen_adapter import wrap_qwen_llm
                
                # Check if this is RyoAIS (vLLM) - enable guided_json for strict JSON output
                # Note: provider_type_id was saved earlier before being removed from bu_config
                enable_guided_json = (provider_type_id == 'ryoais')
                
                if enable_guided_json:
                    logger.info("[_create_and_validate_browser_use_llm] Detected RyoAIS/vLLM - enabling guided_json")
                    llm_instance = wrap_qwen_llm(llm_instance, enable_guided_json=True)
                    logger.info("[_create_and_validate_browser_use_llm] ✅ Applied Qwen adapter with vLLM guided_json")
                else:
                    llm_instance = wrap_qwen_llm(llm_instance, enable_guided_json=False)
                    logger.info("[_create_and_validate_browser_use_llm] ✅ Applied Qwen/Ollama output format adapter")
            except Exception as e:
                logger.warning(f"[_create_and_validate_browser_use_llm] Failed to apply Qwen output adapter: {e}")
        
        # Add context_length attribute to LLM instance for content limiting in browser_use
        # This prevents input prompts from exceeding the model's context window
        # All defaults and error handling are in LLMConfig.get_max_tokens()
        # Use singleton pattern to avoid repeated file I/O and provider initialization
        from gui.config.llm_config import LLMConfig
        llm_config = LLMConfig.get_instance()
        model_name = bu_config.get('model', '')
        context_length = llm_config.get_max_tokens(provider_type_id or '', model_name)
        llm_instance.context_length = context_length
        logger.info(
            f"[_create_and_validate_browser_use_llm] ✅ Set context_length={context_length} "
            f"for {provider_type_id}/{model_name}"
        )

        # CRITICAL: Set max_completion_tokens for OUTPUT limiting
        # browser-use ChatOpenAI defaults to 4096, which is too small for two scenarios:
        #
        # 1. Main agent: When LLM generates complex JSON responses (like done actions with data),
        #    it gets truncated at 4096 tokens, causing "Invalid JSON: EOF while parsing" errors
        #
        # 2. Compression: When compacting long history, the compression LLM also uses this same
        #    instance. With 4096 limit, it cannot generate good summaries for long history,
        #    causing compression to fail and history to keep growing
        #
        # Solution: Set a reasonable max for output. 8192 tokens is sufficient for:
        # - AgentOutput JSON (typical: 2-4K tokens, max: ~6K tokens)
        # - Compression summaries (typical: 1-2K tokens)
        # Can be overridden via ECAN_MAX_COMPLETION_TOKENS env var
        max_output_tokens = int(os.getenv("ECAN_MAX_COMPLETION_TOKENS", "8192"))

        # Check if the instance has max_completion_tokens attribute (BrowserUseChatOpenAI)
        if hasattr(llm_instance, 'max_completion_tokens'):
            original_max_tokens = llm_instance.max_completion_tokens
            llm_instance.max_completion_tokens = max_output_tokens
            logger.info(
                f"[_create_and_validate_browser_use_llm] ✅ Set max_completion_tokens "
                f"from {original_max_tokens} to {max_output_tokens} to prevent:"
                f"\n   - JSON truncation in agent output"
                f"\n   - Compression failures for long history"
            )
        else:
            logger.warning(
                f"[_create_and_validate_browser_use_llm] ⚠️ LLM instance doesn't have "
                f"max_completion_tokens attribute, output may be truncated"
            )

        # Validate it's BrowserUseChatOpenAI or an adapter-wrapped instance
        # Adapters (DeepSeekCompatibleLLM, QwenCompatibleLLM) wrap BrowserUseChatOpenAI
        # and are fully compatible with browser-use
        if isinstance(llm_instance, BrowserUseChatOpenAI):
            return llm_instance
        elif adapt_deepseek_output or adapt_qwen_output:
            # If adapter was applied, accept the wrapped instance
            logger.info(
                f"[_create_and_validate_browser_use_llm] ✅ Returning adapter-wrapped LLM "
                f"({type(llm_instance).__name__})"
            )
            return llm_instance
        else:
            logger.warning(
                f"[_create_and_validate_browser_use_llm] Created LLM is not BrowserUseChatOpenAI "
                f"(got {type(llm_instance).__name__}), returning None"
            )
            return None
    except ImportError:
        logger.error("[_create_and_validate_browser_use_llm] Failed to import browser_use.llm.ChatOpenAI")
        return None
    except Exception as e:
        logger.error(f"[_create_and_validate_browser_use_llm] Failed to create BrowserUseChatOpenAI: {e}")
        return None


def create_browser_use_llm_by_provider_type(
    provider_type: str,
    model_name: str = None,
    api_key: str = None,
    base_url: str = None,
    class_name: str = "",
    default_config: dict = None,
    fallback_llm = None,
    mainwin = None
):
    """
    Create browser_use-compatible LLM based on provider type.
    
    This function creates a browser_use LLM instance based on the provider type,
    handling different provider configurations appropriately.
    
    Args:
        provider_type: Type of provider (openai, deepseek, anthropic, etc.)
        model_name: Model name to use
        api_key: API key for the provider
        base_url: Base URL for API (for custom endpoints)
        class_name: LangChain class name
        default_config: Default configuration dict (fallback)
        fallback_llm: Fallback LLM instance if browser_use not supported
        mainwin: MainWindow instance (for additional fallback)
        
    Returns:
        BrowserUse-compatible LLM object or fallback
        
    Examples:
        >>> llm = create_browser_use_llm_by_provider_type(
        ...     provider_type='openai',
        ...     model_name='gpt-4',
        ...     api_key='sk-...'
        ... )
        
        >>> llm = create_browser_use_llm_by_provider_type(
        ...     provider_type='deepseek',
        ...     model_name='deepseek-chat',
        ...     api_key='...',
        ...     base_url='https://api.deepseek.com'
        ... )
    """
    import os
    from urllib.parse import urlparse

    def _is_local_base_url(url: str | None) -> bool:
        """Best-effort detection for localhost/LAN/self-hosted endpoints."""
        if not url:
            return False
        try:
            parsed = urlparse(str(url).strip())
            host = (parsed.hostname or "").lower()
            if not host:
                return False

            if host in {"localhost", "127.0.0.1", "::1"}:
                return True
            if host.endswith(".local"):
                return True
            if host.startswith("10.") or host.startswith("192.168."):
                return True
            # 172.16.0.0 - 172.31.255.255
            if host.startswith("172."):
                parts = host.split(".")
                if len(parts) >= 2 and parts[1].isdigit():
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        return True
            return False
        except Exception:
            return False

    def _resolve_browser_use_timeout_seconds(
        provider_type_id_val: str,
        model_name_val: str | None,
        base_url_val: str | None,
    ) -> tuple[float, bool]:
        """
        Resolve timeout with sensible defaults:
        - Cloud API: shorter timeout for quick convergence
        - Local/LAN model: longer timeout to tolerate slower inference
        Supports env override: EC_BROWSER_USE_LLM_TIMEOUT_SECONDS
        """
        env_override = os.getenv("EC_BROWSER_USE_LLM_TIMEOUT_SECONDS", "").strip()
        if env_override:
            try:
                val = float(env_override)
                if val > 0:
                    return val, _is_local_base_url(base_url_val)
            except Exception:
                logger.warning(
                    f"[create_browser_use_llm_by_provider_type] Invalid EC_BROWSER_USE_LLM_TIMEOUT_SECONDS={env_override}, "
                    f"falling back to auto timeout"
                )

        is_local_endpoint = provider_type_id_val in {"ollama", "ryoais"} or _is_local_base_url(base_url_val)
        timeout_seconds = 300.0 if is_local_endpoint else 150.0

        # Slow/large/reasoning models often need more wall-clock time.
        model_lower = (model_name_val or "").lower()
        slow_markers = ("32b", "70b", "72b", "110b", "405b", "671b", "reason", "thinking", "r1")
        if any(marker in model_lower for marker in slow_markers):
            timeout_seconds += 90.0

        # Safety bounds: avoid too small or unboundedly large values.
        timeout_seconds = max(60.0, min(timeout_seconds, 480.0))
        return timeout_seconds, is_local_endpoint
    
    # Try to import BrowserUseChatOpenAI
    try:
        from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
    except ImportError:
        logger.error(f"[create_browser_use_llm_by_provider_type] Failed to import browser_use.llm.ChatOpenAI")
        return None
    
    # Set default config if not provided
    if default_config is None:
        default_config = {
            'model': 'gpt-4-turbo-preview',
            'api_key': os.getenv("OPENAI_API_KEY"),
            'base_url': None
        }
    
    # Validate provider_type is a standard ID (lowercase, no spaces, no special chars except underscore)
    # Standard IDs: openai, dashscope, deepseek, ollama, etc.
    # NOT display names like "Qwen" or "ChatGLM"
    import re
    provider_type_clean = provider_type.lower().strip()
    
    if not re.match(r'^[a-z0-9_]+$', provider_type_clean):
        logger.error(
            f"[create_browser_use_llm_by_provider_type] Invalid provider_type '{provider_type}'. "
            f"Must be a standard provider ID (lowercase, no spaces, no special chars). "
            f"Examples: 'openai', 'dashscope', 'deepseek', 'ollama'. "
            f"NOT display names like ''Qwen. "
            f"Please ensure extract_provider_config() returns the 'provider_type' field (standard ID)."
        )
        return None
    
    # Use the clean provider_type directly (no complex normalization needed)
    provider_type_id = provider_type_clean
    
    # Check compatibility
    is_compatible = is_provider_browser_use_compatible(provider_type_id)
    logger.debug(
        f"[create_browser_use_llm_by_provider_type] Provider ID: {provider_type_id}, "
        f"Model: {model_name}, Compatible: {is_compatible}"
    )
    
    # OpenAI or Azure OpenAI
    if provider_type_id in ['openai', 'azure_openai'] or 'openai' in class_name:
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key'],
            'provider_type_id': provider_type_id,
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        logger.info(
            f"[create_browser_use_llm_by_provider_type] Creating BrowserUseChatOpenAI "
            f"for {provider_type_id}, model: {bu_config['model']}"
        )
        return _create_and_validate_browser_use_llm(bu_config)
    
    # OpenAI-compatible providers (DeepSeek, DashScope, Ollama, RyoAIS, Qwen, Baidu Qianfan, Bytedance, Zhipu AI, etc.)
    elif provider_type_id in ['deepseek', 'dashscope', 'ollama', 'ryoais', 'ecanai', 'qwen', 'qwq', 'baidu_qianfan', 'bytedance', 'zhipuai', 'moonshot', 'minimax']:
        resolved_timeout_s, is_local_endpoint = _resolve_browser_use_timeout_seconds(
            provider_type_id_val=provider_type_id,
            model_name_val=model_name,
            base_url_val=base_url,
        )
        # Local slow models should avoid long double-waits on retries.
        resolved_retries = 0 if is_local_endpoint else 1

        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key'] or 'dummy-key',
            'timeout': resolved_timeout_s,
            'max_retries': resolved_retries,
            'provider_type_id': provider_type_id,
        }
        
        # All major providers support response_format (JSON mode)
        # Based on official documentation verification (2026-02-06):
        # ✅ DeepSeek: https://api-docs.deepseek.com/guides/json_mode
        # ✅ Qwen/DashScope: https://help.aliyun.com/zh/model-studio/qwen-structured-output
        # ✅ Ollama: https://docs.ollama.com/capabilities/structured-outputs
        # ✅ Zhipu AI: https://docs.z.ai/guides/capabilities/struct-output
        # ✅ Baidu Qianfan: https://ai.baidu.com/ai-doc/AISTUDIO/rm344erns
        # 
        # JSON mode ensures valid JSON format, but adapters are still needed to:
        # 1. Filter invalid actions (replace_file, etc.)
        # 2. Remove extra fields (thinking, thought, etc.)
        # 
        # Some providers' JSON schema support is not compatible with browser-use
        # Use browser-use's standard compatibility mode (official approach)
        providers_need_compatibility_mode = ['deepseek', 'ollama', 'ryoais', 'qwen', 'qwq', 'dashscope', 'moonshot']
        
        if provider_type_id in providers_need_compatibility_mode:
            # Standard compatibility flags from browser-use
            bu_config['add_schema_to_system_prompt'] = True  # Add schema to prompt instead of response_format
            bu_config['dont_force_structured_output'] = True  # Don't force structured output
            bu_config['remove_min_items_from_schema'] = True  # Remove minItems constraint
            bu_config['remove_defaults_from_schema'] = True   # Remove default values
            logger.info(f"[create_browser_use_llm_by_provider_type] Using browser-use standard compatibility mode for {provider_type_id}")
        else:
            # Standard mode: use response_format (JSON schema)
            logger.info(f"[create_browser_use_llm_by_provider_type] Using structured output (response_format) for {provider_type_id}")
        
        # Enable output format adapters for specific providers
        # Adapters perform post-processing after LLM generates output
        if provider_type_id == 'deepseek':
            bu_config['adapt_deepseek_output'] = True
            logger.info(f"[create_browser_use_llm_by_provider_type] Enabled DeepSeek adapter (post-process to filter invalid actions)")
        elif provider_type_id in ['ollama', 'ryoais', 'qwen', 'qwq', 'dashscope']:
            bu_config['adapt_qwen_output'] = True
            # Store provider_type_id for guided_json detection
            bu_config['provider_type_id'] = provider_type_id
            logger.info(f"[create_browser_use_llm_by_provider_type] Enabled Qwen/Ollama adapter (post-process to filter invalid actions)")
            logger.info(
                f"[create_browser_use_llm_by_provider_type] Timeout strategy for {provider_type_id}: "
                f"timeout={resolved_timeout_s:.1f}s, max_retries={resolved_retries}, "
                f"endpoint={'local' if is_local_endpoint else 'cloud'}"
            )
                
        if base_url:
            logger.debug(f"[create_browser_use_llm_by_provider_type] Before conversion: provider_type_id={provider_type_id}, base_url={base_url}")
            # Special handling for Ollama and RyoAIS: convert native URL to OpenAI-compatible endpoint
            if provider_type_id in ['ollama', 'ryoais']:
                base_url = base_url.rstrip('/')
                if not base_url.endswith('/v1'):
                    base_url = f"{base_url}/v1"
                    logger.info(f"[create_browser_use_llm_by_provider_type] Converted {provider_type_id} URL to OpenAI-compatible: {base_url}")
                else:
                    logger.debug(f"[create_browser_use_llm_by_provider_type] {provider_type_id} URL already has /v1 suffix: {base_url}")
            bu_config['base_url'] = base_url
            logger.debug(f"[create_browser_use_llm_by_provider_type] After conversion: base_url={base_url}")
        
        logger.info(
            f"[create_browser_use_llm_by_provider_type] Creating BrowserUseChatOpenAI "
            f"for {provider_type_id} (OpenAI-compatible), model: {bu_config['model']}"
        )
        
        # Log compatibility flags for debugging
        compat_flags = {
            'add_schema_to_system_prompt': bu_config.get('add_schema_to_system_prompt'),
            'dont_force_structured_output': bu_config.get('dont_force_structured_output'),
            'remove_min_items_from_schema': bu_config.get('remove_min_items_from_schema'),
            'remove_defaults_from_schema': bu_config.get('remove_defaults_from_schema'),
        }
        logger.info(f"[create_browser_use_llm_by_provider_type] Compatibility flags: {compat_flags}")
        
        # Check if this is a domestic API that needs proxy bypass
        # Domestic APIs (DashScope, DeepSeek, Baidu Qianfan, Bytedance) may have proxy restrictions
        # Optimization: Only creates no-proxy clients if proxy is actually configured
        domestic_apis_need_direct = ['dashscope', 'qwen', 'qwq', 'deepseek', 'baidu_qianfan', 'bytedance', 'moonshot']
        
        if provider_type_id in domestic_apis_need_direct:
            # Create no-proxy httpx clients (sync + async, thread-safe, doesn't modify global env vars)
            # Optimization: Only creates if proxy is configured
            # Note: browser-use requires AsyncClient for http_client parameter (despite the name)
            # This is because browser-use operates in async context
            sync_client, async_client = _create_no_proxy_http_client()
            
            if async_client:
                # Proxy is configured - use no-proxy ASYNC client (bypass proxy for domestic APIs)
                logger.debug(
                    f"[create_browser_use_llm_by_provider_type] Using no-proxy async client for {provider_type_id} "
                    f"(proxy detected, bypassing for domestic API)"
                )
                # browser-use requires AsyncClient (operates in async context)
                bu_config['http_client'] = async_client
                return _create_and_validate_browser_use_llm(bu_config)
            else:
                # No proxy configured - use default clients (more efficient, direct connection)
                logger.debug(
                    f"[create_browser_use_llm_by_provider_type] No proxy configured for {provider_type_id}, "
                    f"using default clients (direct connection)"
                )
                return _create_and_validate_browser_use_llm(bu_config)
        else:
            # Ollama, etc. - use default clients (respects system proxy if configured)
            return _create_and_validate_browser_use_llm(bu_config)
    
    # Non-OpenAI-compatible providers (Anthropic, Google, Bedrock)
    # Try to create BrowserUseChatOpenAI with provider's data, fallback if fails
    elif provider_type_id in ['anthropic', 'google', 'bedrock']:
        logger.warning(
            f"[create_browser_use_llm_by_provider_type] Provider '{provider_type_id}' is not natively "
            f"supported by browser_use, attempting workaround"
        )
        
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key'],
            'provider_type_id': provider_type_id,
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        llm_instance = _create_and_validate_browser_use_llm(bu_config)
        if llm_instance is not None:
            logger.info(
                f"[create_browser_use_llm_by_provider_type] Successfully created BrowserUseChatOpenAI "
                f"for {provider_type_id} using workaround, model: {bu_config['model']}"
            )
            return llm_instance
        else:
            logger.error(
                f"[create_browser_use_llm_by_provider_type] Failed to create BrowserUseChatOpenAI "
                f"for {provider_type_id}"
            )
            return None
    
    # Unknown provider - try OpenAI-compatible mode
    else:
        logger.warning(
            f"[create_browser_use_llm_by_provider_type] Unknown provider '{provider_type_id}', "
            f"attempting OpenAI-compatible mode"
        )
        
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key'],
            'provider_type_id': provider_type_id,
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        llm_instance = _create_and_validate_browser_use_llm(bu_config)
        if llm_instance is not None:
            logger.info(
                f"[create_browser_use_llm_by_provider_type] Successfully created BrowserUseChatOpenAI "
                f"for {provider_type_id} (OpenAI-compatible mode), model: {bu_config['model']}"
            )
            return llm_instance
        else:
            logger.error(
                f"[create_browser_use_llm_by_provider_type] Failed to create BrowserUseChatOpenAI "
                f"for {provider_type_id}"
            )
            return None


def get_use_vision_from_llm(llm, context="") -> bool:
    """
    Get use_vision value from LLM object, defaulting to False if not found.
    
    Vision is disabled by default to avoid compatibility issues with models that don't support it.
    Only models with explicit supports_vision=True will enable vision.
    
    Args:
        llm: LLM instance that may have supports_vision attribute
        context: Optional context string for logging (e.g., "EC_Agent", "build_node")
    
    Returns:
        bool: use_vision value (False by default for safety)
    """
    if llm and hasattr(llm, 'supports_vision'):
        use_vision = llm.supports_vision
        if context:
            logger.debug(f"[{context}] Auto-set use_vision={use_vision} from LLM config")
        return use_vision
    else:
        # Default to False if not found (safer default, avoids API compatibility issues)
        if context:
            logger.debug(f"[{context}] Auto-set use_vision=False (default, no config found)")
        return False


def create_browser_use_llm(mainwin=None, fallback_llm=None, skip_playwright_check=False, preferred_provider=None, preferred_model_name=None):
    """
    Create BrowserUse-compatible LLM based on mainwin's current LLM provider configuration.
    
    This is the high-level function that integrates with mainwin configuration
    and creates an appropriate browser_use LLM instance.
    
    Args:
        mainwin: MainWindow instance to get LLM configuration from
        fallback_llm: Fallback LLM to use when browser_use LLM creation fails (DEPRECATED: not used)
        skip_playwright_check: Skip Playwright initialization check (default: False)
        
    Returns:
        BrowserUseChatOpenAI instance or None (never returns incompatible LLM types)
        
    Examples:
        >>> # Create with mainwin configuration
        >>> llm = create_browser_use_llm(mainwin=main_window)
        
        >>> # Skip playwright check for standalone use
        >>> llm = create_browser_use_llm(mainwin=main_window, skip_playwright_check=True)
    """
    import os
    
    # Validate return type at the end to ensure we never return incompatible types
    try:
        from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
    except ImportError:
        logger.error("[create_browser_use_llm] Failed to import browser_use.llm.ChatOpenAI")
        return None
    
    try:
        # Optional: Check Playwright initialization if not skipped
        if not skip_playwright_check:
            try:
                from agent.playwright.utils import check_and_init_playwright
                if not check_and_init_playwright():
                    logger.warning("[create_browser_use_llm] Playwright initialization failed, returning None")
                    return None
            except ImportError:
                logger.debug("[create_browser_use_llm] Playwright not available, skipping initialization check")
        
        # Try to get configuration from mainwin (required, no fallback)
        if mainwin and hasattr(mainwin, 'config_manager'):
            try:
                config_manager = mainwin.config_manager
                default_llm_name = preferred_provider or config_manager.general_settings.default_llm
                
                if not default_llm_name:
                    logger.error("[create_browser_use_llm] default_llm is empty - this should not happen")
                    return None
                
                # Use get_provider() to get the specific provider dict
                provider_dict = config_manager.llm_manager.get_provider(default_llm_name)
                
                if not provider_dict:
                    logger.error(f"[create_browser_use_llm] Default LLM '{default_llm_name}' not found in providers")
                    return None
                
                # Use shared extract_provider_config to get configuration.
                # If a preferred model is provided, honor it over the global default.
                config = extract_provider_config(
                    provider_dict,
                    config_manager=config_manager,
                    node_model_name=preferred_model_name,
                )
                
                provider_type = config['provider_type']
                model_name = config['model_name']  # Already includes user-selected model from extract_provider_config
                api_key = config.get('api_key')  # May be None if not configured
                base_url = config.get('base_url')
                class_name = config.get('class_name', '')
                
                if not api_key:
                    logger.error(
                        f"[create_browser_use_llm] No API key configured for provider "
                        f"'{default_llm_name}'"
                    )
                    return None
                
                logger.info(
                    f"[create_browser_use_llm] Using default LLM: "
                    f"provider={config.get('provider_display', default_llm_name)}, model={model_name}"
                )
                
                # Get supports_vision from config (default True if not found)
                supports_vision = config.get('supports_vision', True)
                
                masked_key = (api_key[:8] + '...' + api_key[-4:]) if api_key and len(api_key) > 12 else '***'
                log_msg = f"[create_browser_use_llm] provider_type:{provider_type}, model_name:{model_name}, api_key:{masked_key}, base_url:{base_url}, class_name:{class_name}, supports_vision:{supports_vision}"
                logger.debug(log_msg)
                send_skill_editor_log("log", log_msg)

                # Use centralized function (already validates BrowserUseChatOpenAI type)
                # Note: thinking control is handled via task prompt in build_node.py
                llm_instance = create_browser_use_llm_by_provider_type(
                    provider_type=provider_type,
                    model_name=model_name,
                    api_key=api_key,
                    base_url=base_url,
                    class_name=class_name,
                    default_config=None,  # No fallback config needed when using mainwin
                    fallback_llm=None,  # Don't pass fallback_llm as it may be incompatible
                    mainwin=mainwin
                )
                # Final type check before returning
                if llm_instance is not None and not isinstance(llm_instance, BrowserUseChatOpenAI):
                    log_msg = f"[create_browser_use_llm] Type check failed: expected BrowserUseChatOpenAI, got {type(llm_instance).__name__}, returning None"
                    logger.error(log_msg)
                    send_skill_editor_log("error", log_msg)
                    return None
                
                # Attach supports_vision to LLM instance for later use
                # Note: context_length is already set by _create_and_validate_browser_use_llm()
                if llm_instance is not None:
                    llm_instance.supports_vision = supports_vision
                    log_msg = f"🤖 [create_browser_use_llm] Model {model_name} supports_vision: {supports_vision}"
                    logger.debug(log_msg)
                    send_skill_editor_log("log", log_msg)
                
                return llm_instance
                        
            except Exception as e:
                logger.error(
                    f"[create_browser_use_llm] Exception getting LLM config from mainwin: {e}"
                )
                import traceback
                log_msg = f"[create_browser_use_llm] Exception details: {traceback.format_exc()}"
                logger.error(log_msg)
                send_skill_editor_log("error", log_msg)
                return None
        else:
            if not mainwin:
                log_msg = "[create_browser_use_llm] No mainwin provided - cannot create LLM without mainwin configuration"
            else:
                log_msg = "[create_browser_use_llm] mainwin has no config_manager - cannot create LLM"
            logger.error(log_msg)
            send_skill_editor_log("error", log_msg)
            return None
        
    except Exception as e:
        logger.error(f"[create_browser_use_llm] Failed to create BrowserUseChatOpenAI: {e}")
        import traceback
        logger.debug(f"[create_browser_use_llm] Exception details: {traceback.format_exc()}")
        return None


def pick_browser_use_llm(mainwin=None, skip_playwright_check=False):
    """
    Create browser_use LLM instance based on mainwin's configuration.
    
    This is a companion function to pick_llm() that creates a browser_use-compatible
    LLM instance. It should be called alongside pick_llm() during initialization
    and when switching LLM providers.
    
    Args:
        mainwin: MainWindow instance to get LLM configuration from
        skip_playwright_check: Skip Playwright initialization check (default: False)
        
    Returns:
        BrowserUseChatOpenAI instance or None
        
    Examples:
        >>> # Initialize both LLMs together
        >>> mainwin.llm = pick_llm(default_llm, providers, config_manager)
        >>> mainwin.browser_use_llm = pick_browser_use_llm(mainwin=mainwin)
        
        >>> # Update both when switching providers
        >>> mainwin.llm = pick_llm(new_provider, providers, config_manager, allow_fallback=False)
        >>> mainwin.browser_use_llm = pick_browser_use_llm(mainwin=mainwin)
    """
    logger.info("[pick_browser_use_llm] Creating browser_use LLM instance")
    
    # Delegate to create_browser_use_llm which has all the logic
    browser_use_llm = create_browser_use_llm(
        mainwin=mainwin,
        fallback_llm=None,
        skip_playwright_check=skip_playwright_check
    )
    
    if browser_use_llm:
        # Get detailed info for logging
        llm_type = type(browser_use_llm).__name__
        details = []
        
        if hasattr(browser_use_llm, 'model_name'):
            details.append(f"model={browser_use_llm.model_name}")
        elif hasattr(browser_use_llm, 'model'):
            details.append(f"model={browser_use_llm.model}")
        
        if mainwin and hasattr(mainwin, 'config_manager'):
            default_llm = mainwin.config_manager.general_settings.default_llm
            if default_llm:
                provider = mainwin.config_manager.llm_manager.get_provider(default_llm)
                if provider:
                    provider_display = provider.get('display_name', default_llm)
                    details.append(f"provider={provider_display}")
        
        detail_str = f" ({', '.join(details)})" if details else ""
        logger.info(f"[pick_browser_use_llm] Successfully created browser_use LLM: {llm_type}{detail_str}")
    else:
        logger.warning("[pick_browser_use_llm] Failed to create browser_use LLM")
    
    return browser_use_llm


def _update_default_llm_via_config_manager(provider_name, config_manager=None):
    """Update default_llm setting via config manager"""
    try:
        if config_manager is None:
            logger.warning(f"No config_manager provided, skipping default_llm update for {provider_name}")
            return

        # 检查 llm_manager 是否存在
        if not hasattr(config_manager, 'llm_manager') or config_manager.llm_manager is None:
            logger.warning(f"LLMManager not available in config_manager, skipping default_llm update for {provider_name}")
            return

        # Use LLM manager's method to update default LLM
        success = config_manager.llm_manager.update_default_llm(provider_name)
        if not success:
            logger.warning(f"Failed to update default_llm setting via LLM manager")
        else:
            logger.info(f"Successfully updated default_llm to {provider_name} via LLM manager")

    except Exception as e:
        logger.error(f"Error updating default_llm setting via config manager: {e}")


# def _fallback_llm_selection(country):
#     """Fallback LLM selection when no configured providers are available"""
#     logger.warning("[_fallback_llm_selection] Using fallback LLM selection - API keys may not be configured")
    
#     try:
#         # Helper to get API key from secure store
#         from utils.env.secure_store import secure_store
#         def get_api_key(env_var):
#             try:
#                 return secure_store.get(env_var)
#             except Exception:
#                 return None
        
#         if country == "CN":
#             logger.info("[_fallback_llm_selection] Using DeepSeek for China")
#             deepseek_api_key = get_api_key('DEEPSEEK_API_KEY')
#             if deepseek_api_key:
#                 llm = ChatDeepSeek(model="deepseek-chat", api_key=deepseek_api_key, temperature=0)
#                 logger.info(f"[_fallback_llm_selection] Created DeepSeek LLM, model: deepseek-chat")
#                 return llm
#             else:
#                 logger.warning("[_fallback_llm_selection] DEEPSEEK_API_KEY not found in secure_store")
        
#         # Try OpenAI for US or default
#         logger.info("[_fallback_llm_selection] Attempting to use OpenAI")
#         openai_api_key = get_api_key('OPENAI_API_KEY')
#         if openai_api_key:
#             llm = ChatOpenAI(model="gpt-4o", api_key=openai_api_key, temperature=0)
#             logger.info(f"[_fallback_llm_selection] Created OpenAI LLM, model: gpt-4o")
#             return llm
#         else:
#             logger.error("[_fallback_llm_selection] OPENAI_API_KEY not found in secure_store - cannot create fallback LLM")
#             return None
#     except Exception as e:
#         logger.error(f"[_fallback_llm_selection] Fallback LLM creation failed: {e}")
#         return None

def msg_role(msg: BaseMessage) -> str:
    if isinstance(msg, SystemMessage):
        return "system"
    if isinstance(msg, HumanMessage):
        c = getattr(msg, "content", "")
        if isinstance(c, str) and c.startswith("[agent_"):
            return "agent"
        return "human"
    if isinstance(msg, AIMessage):
        return "ai"
    return "unknown"

def msg_text_extract(msg: BaseMessage) -> str:
    # Content can be str or list of blocks (text/image/file)
    c = getattr(msg, "content", "")
    if isinstance(c, str):
        return c
    # If list of blocks, extract text-like parts
    parts = []
    for b in c if isinstance(c, list) else []:
        t = b.get("type")
        if t in ("text",):
            parts.append(b.get("text", ""))
        elif t == "image_url":
            parts.append("[image]")
        elif t in ("file", "audio", "input_audio"):
            parts.append(f"[{t}]")
    return " ".join(p for p in parts if p)

def to_memory_item(
    msg: BaseMessage,
    namespace: Tuple[str, ...],
    id: str,         # e.g. {"agent_id": ..., "chat_id": ..., "task_id": ..., "msg_id": ...}
    extra_meta: Dict[str, Any] = None
) -> MemoryItem:
    text = msg_text_extract(msg)
    meta = {
        "role": msg_role(msg),
        "msg_type": msg.__class__.__name__,
        "content_raw": getattr(msg, "content", None),
        **(extra_meta or {}),
    }
    return MemoryItem(
        namespace=namespace,
        id=id,
        text=text,
        metadata=meta
    )

def get_standard_prompt(state: "NodeState") -> "NodeState":
    logger.debug("get_standard_prompt===>", state)
    boss = "Guest User"
    standard_prompt_template = [
                ("system", """
                    You're a e-commerce business expert helping your human boss {boss_name} to run best performance e-commerce business. 
                    Given the latest human boss message,  try your best to understand it and respond to it.
                """),
                ("human", "{input}")
            ]
    langchain_prompt = ChatPromptTemplate.from_messages(standard_prompt_template)
    formatted_prompt = langchain_prompt.format_messages(boss_name=boss, input=state["input"])
    return formatted_prompt

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dict b into dict a and return a new dict."""
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def find_opposite_agent(self_agent, chat_id):
    mainwin = self_agent.mainwin
    this_chat = mainwin.db_chat_service.get_chat_by_id(chat_id, True)

    # Check if chat exists and has data
    if not this_chat or not this_chat.get("success") or this_chat.get("data") is None:
        logger.error(f"Chat not found or has no data: {chat_id}, result: {this_chat}")
        return None
    
    logger.debug(f"found chat: {this_chat['data']['id']}")

    members = this_chat["data"].get("members", [])
    logger.debug(f"chat members: {members}")
    logger.debug(f"me id: {self_agent.card.id}")
    # for now, let's just assume 1-1 chat, find first chat member not myself.
    oppsite_member = next((ag for ag in members if ag["userId"] != self_agent.card.id), None)
    if oppsite_member:
        opposite_side = get_agent_by_id(oppsite_member["userId"])
        if opposite_side:
            logger.debug(f"found opposite side agent: {opposite_side.card.name}")
        else:
            logger.warning(f"Agent not found for userId: {oppsite_member['userId']} (name: {oppsite_member.get('name', 'unknown')})")
    else:
        logger.error("No chat mate found for chat:", chat_id)
        opposite_side = None
    return opposite_side

def send_response_back(state: "NodeState", force_send: bool = False) -> "NodeState":
    """
    Send response back to the opposite agent (typically Twin Agent).
    
    This function is used for async communication where the response is sent
    as a new A2A request rather than returned via the original HTTP response.
    
    The decision to send or skip is controlled by:
    1. force_send=True: Always send
    2. state["attributes"]["async_response"]=True: Send via A2A (async mode)
    3. state["attributes"]["async_response"]=False: Skip, result via waiter (sync mode)
    4. Default: Send via A2A (backward compatible)
    
    Node designers can set async_response in their node config or state to control this.
    
    Args:
        state: The current node state containing the response
        force_send: If True, always send regardless of async_response setting
    
    Returns:
        The send result or state
    """
    try:
        agent_id = state["messages"][0]
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin

        # ── HOT-PATH-B failure feedback-loop guard ────────────────────────
        # Background (incident 2026-05-13 flood test, 6-min window):
        #   - 7 actual site send-tool attempts, 4 successes
        #   - 147 HOT-PATH-B "action_failed" outcomes (timeouts under load)
        #   - **127 of the 172 Q&A-bot LLM rounds (74%) were triggered by
        #     a hot_path failure echo, not a real customer question**
        # The flow: front-desk's browser_node hits HOT-PATH-B → fails →
        # llm_result = {hot_path:true, hot_path_type:'action_failed', ...} →
        # send_response_back sends THAT JSON back as a chat_message to the
        # Q&A bot that originally dispatched the send_chat → Q&A bot's
        # pend_event resumes with the failure-JSON in state["input"] →
        # spurious Q&A LLM round → LLM has no idea what to do with a
        # delivery-failure notification, echoes {all_done:true} → no useful
        # output but consumes ~3s of LLM time, ~22s of front-desk-task slot,
        # and ANOTHER chat_message back to front-desk... death spiral.
        #
        # Pre-merge behavior: front-desk failures stayed internal — Q&A bots
        # never saw them.  The dev merge added this propagation path; under
        # any flood load the feedback loop saturates everything.
        #
        # Fix: at entry, detect HOT-PATH-B failure outcomes and short-circuit
        # before constructing the A2A response.  The failure is local to the
        # front-desk's delivery layer; the Q&A bot's job already completed
        # when it emitted the send_chat.  Skipping the propagation:
        #   1. Frees the Q&A bot's LLM budget for real customer questions.
        #   2. Removes the chat_message echoes that re-saturate the
        #      front-desk task queue with no payload to deliver.
        #   3. Matches pre-merge throughput observability — operators still
        #      see the failure in HOT-PATH-B's ledger; they just don't see
        #      it amplified through 3-4 redundant agent hops.
        # Belt-and-suspenders: also short-circuit ``hot_path_type`` markers
        # that mean "front-desk handled internally" (stale_reply_drop,
        # dedup_skip, action_failed_terminal) so none of them propagate.
        try:
            _llm_result = (state.get("result") or {}).get("llm_result")
            if isinstance(_llm_result, dict):
                _hot_path = bool(_llm_result.get("hot_path"))
                _hp_type = str(_llm_result.get("hot_path_type") or "")
                _HP_INTERNAL_TYPES = {
                    "action_failed",
                    "action_failed_terminal",
                    "stale_reply_drop",
                    "dedup_skip",
                    # Fix 10 (2026-05-13): also suppress SUCCESS echoes.
                    # Background: end-of-test queue inspection found Q&A
                    # bot tasks (the three live-chat workers) still holding 3-deep
                    # queues of ``{all_done:true, work_done:false,
                    # hot_path:true, hot_path_type:configurable}`` events
                    # arriving from the front-desk.  These are HOT-PATH-B
                    # SUCCESS notifications — the front-desk typed the
                    # reply into the live-chat site, no further action needed — but
                    # they were being delivered back to the Q&A bot as
                    # chat_message events.  The Q&A bot's LLM then
                    # processes each one as if it were a real customer
                    # query, generating a useless ``{all_done:true}``
                    # echo that *also* gets queued, and the cycle
                    # repeats.  Each echo burns ~2-3s of Q&A LLM time
                    # and clogs the front-desk's downstream queue.  Pre-
                    # merge had no propagation path for these — they
                    # stayed local to the front-desk.  The dev merge
                    # added the A2A response-routing that propagates
                    # ALL outcomes (success + failure).  Fix 6 caught
                    # the failure half; this Fix 10 extension catches
                    # the success half.
                    "configurable",
                    "first_invocation_skip",
                }
                if _hot_path and _hp_type in _HP_INTERNAL_TYPES and not force_send:
                    logger.info(
                        f"[send_response_back] short-circuit: HOT-PATH-B "
                        f"outcome (hot_path_type={_hp_type!r}); NOT "
                        f"propagating to opposite agent — outcome is "
                        f"local to front-desk delivery and the Q&A bot "
                        f"already completed its turn.  Skipping A2A send "
                        f"to avoid the feedback-loop amplification."
                    )
                    return state

                # ── Wrapper-duplication guard ────────────────────────────
                # Background (incident 2026-05-13 flood test, 12:52 window):
                # the front-desk's chat_message queue was filled with
                # alternating event pairs:
                #
                #   #0: {"tool_name": "send_chat", "tool_input": {...}, "work_result": {...}}
                #   #1: {"customer_id": "客户XX", "customer_name": "...", "response_text": "..."}
                #
                # i.e. every Q&A response was generating TWO chat_messages
                # into the front-desk's queue:
                #   (a) The Q&A bot's MCP ``send_chat`` tool execution
                #       fires an A2A message with the customer payload as
                #       content → arrives as event #1.
                #   (b) The Q&A bot's task-termination path then ALSO
                #       calls ``send_response_back`` with the LLM output
                #       wrapper ``{tool_name: send_chat, tool_input, work_result}``
                #       as the body → arrives as event #2.
                #
                # Event (b) is redundant: the customer payload was already
                # delivered via (a), and event (b)'s ``tool_name=send_chat``
                # wrapper carries no destination ``customer_id`` at the
                # outer level (it's nested under ``tool_input.input.message``),
                # so HOT-PATH-B can't match a rule on it and the front-desk
                # task just burns a dequeue slot + ~7-15s of processing
                # time on a no-op.  At flood load (32-deep queue) this
                # halves the effective delivery throughput.
                #
                # Fix: if the LLM result IS a successful tool dispatch via
                # a known A2A-sending tool, the tool already sent its own
                # A2A message — skip the wrapper.  The `chat_sent: True` /
                # `last_action_succeeded: True` work_result fields are the
                # signal that the MCP tool execution succeeded.
                _A2A_SENDING_TOOLS = {"send_chat", "bu_send_chat"}
                _tool_name = str(_llm_result.get("tool_name") or "")
                _work_result = _llm_result.get("work_result")
                if (
                    _tool_name in _A2A_SENDING_TOOLS
                    and isinstance(_work_result, dict)
                    and bool(
                        _work_result.get("chat_sent")
                        or _work_result.get("last_action_succeeded")
                    )
                    and not force_send
                ):
                    logger.info(
                        f"[send_response_back] short-circuit: LLM output "
                        f"was a successful {_tool_name!r} tool dispatch "
                        f"(chat_sent={_work_result.get('chat_sent')!r}, "
                        f"last_action_succeeded={_work_result.get('last_action_succeeded')!r}); "
                        f"the MCP tool already delivered the A2A message — "
                        f"skipping wrapper propagation to avoid the "
                        f"duplicate-enqueue feedback loop."
                    )
                    return state
        except Exception as _hp_guard_err:
            logger.debug(
                f"[send_response_back] hot-path guard check failed "
                f"(non-fatal): {_hp_guard_err}"
            )

        # Check if async_response is explicitly set in state
        # This allows node/skill designers to control the response mode
        async_response = state.get("attributes", {}).get("async_response")

        # If async_response is explicitly False, skip sending (sync mode - result via waiter)
        if not force_send and async_response is False:
            logger.debug("[send_response_back] async_response=False, skipping A2A send (sync mode)")
            return state
        
        # Default behavior: send via A2A (async mode)
        # This maintains backward compatibility
        logger.debug(f"[send_response_back] async_response={async_response}, sending via A2A")
        
        # Resolve chatId by trying every known source against the chat DB
        # and picking the first one that actually resolves to a real chat.
        #
        # Historical context: the original code preferred
        # `attributes.params.metadata.params.chatId` over `messages[1]` to
        # handle the "chat deleted and recreated" case where messages[1]
        # still held a stale (deleted) id.  But front-desk skills now
        # synthesize `params.chatId = customer_name` (e.g. '客户A') when
        # dispatching browser-driven tasks — that string is NOT a DB chat
        # row id, so the lookup at `find_opposite_agent(chat_id)` below
        # failed with `Chat not found or has no data: 客户A` on every
        # cycle (observed 2026-04-22 12:31–12:32 run).  When that error
        # fires the QA worker silently has no reply target, so no
        # `chat_message` is emitted back and the front-desk's pend_event
        # node waits forever — which is exactly the stuck-after-one-round
        # behaviour we saw.
        #
        # Fix: try each candidate in order, probe the chat DB, and use
        # the first that resolves.  messages[1] is kept as a candidate
        # (not pre-empted) so the "chat recreated" scenario still works
        # when params.chatId IS a valid id.
        chat_id = None
        chat_id_source = None
        _chat_id_candidates: list[tuple[str, str]] = []  # (source_label, chat_id)
        try:
            _attrs = state.get("attributes", {})
            _sr_params = _attrs.get("params", {})
            
            # Log the actual attributes for diagnosis (elevated to INFO for debugging)
            logger.info(f"[send_response_back] === chat_id diagnostic start ===")
            logger.info(f"[send_response_back] state.attributes keys: {list(_attrs.keys())}")
            logger.info(f"[send_response_back] attributes.chat_id={_attrs.get('chat_id')!r}")
            logger.info(f"[send_response_back] attributes.params.chatId={_sr_params.get('chatId')!r}")
            logger.info(f"[send_response_back] attributes.params.sessionId={_sr_params.get('sessionId')!r}")
            _msgs = state.get('messages')
            _msg1 = _msgs[1] if isinstance(_msgs, list) and len(_msgs) > 1 else None
            logger.info(f"[send_response_back] messages[0]={_msgs[0] if isinstance(_msgs, list) and len(_msgs) > 0 else None!r}")
            logger.info(f"[send_response_back] messages[1]={_msg1!r}")
            logger.info(f"[send_response_back] state.metadata keys: {list((state.get('metadata') or {}).keys()) if isinstance(state.get('metadata'), dict) else []}")
            
            # Check if there's a sessionId that should be used as chatId
            if not _attrs.get('chat_id') and _sr_params.get('sessionId'):
                logger.info(f"[send_response_back] Using sessionId as chatId: {_sr_params.get('sessionId')}")
                _chat_id_candidates.append(("params.sessionId (fallback)", str(_sr_params.get('sessionId'))))
            
            # attributes.params.metadata.params.chatId (A2A TaskSendParams)
            if hasattr(_sr_params, "metadata") and isinstance(_sr_params.metadata, dict):
                _meta_params = _sr_params.metadata.get("params", {})
                if isinstance(_meta_params, dict):
                    _cid = _meta_params.get("chatId")
                    if _cid:
                        _chat_id_candidates.append(("params.metadata.params", str(_cid)))
            # attributes.params.chatId (plain dict-shaped params)
            if isinstance(_sr_params, dict):
                _cid = _sr_params.get("chatId")
                if _cid:
                    _chat_id_candidates.append(("params", str(_cid)))
            # attributes.chat_id (directly in attributes)
            _cid = _attrs.get("chat_id")
            if _cid:
                _chat_id_candidates.append(("attributes.chat_id", str(_cid)))
            # messages[1] — original A2A chat row id
            _msgs = state.get("messages")
            if isinstance(_msgs, list) and len(_msgs) > 1 and _msgs[1]:
                _chat_id_candidates.append(("messages[1]", str(_msgs[1])))
            # events[-1].context.chatId
            _events = state.get("events", [])
            if isinstance(_events, list) and _events:
                _last_evt = _events[-1]
                if isinstance(_last_evt, dict):
                    _ctx = _last_evt.get("context", {})
                    if isinstance(_ctx, dict):
                        _cid = _ctx.get("chatId")
                        if _cid:
                            _chat_id_candidates.append(("events.context.chatId", str(_cid)))
            
            # metadata.notification.chatId (set by skill nodes like send_a2a_response)
            _metadata = state.get("metadata", {})
            if isinstance(_metadata, dict):
                _notif = _metadata.get("notification")
                if isinstance(_notif, dict):
                    _cid = _notif.get("chatId")
                    if _cid:
                        _chat_id_candidates.append(("metadata.notification.chatId", str(_cid)))
        except Exception as e:
            logger.error(f"[send_response_back] Error collecting chatId candidates: {e}")

        # Probe candidates against the chat DB.  De-dup while preserving order.
        _seen_cids: set[str] = set()
        _ordered_candidates: list[tuple[str, str]] = []
        for _src, _cid in _chat_id_candidates:
            if _cid in _seen_cids:
                continue
            _seen_cids.add(_cid)
            _ordered_candidates.append((_src, _cid))

        _probe_mainwin = getattr(self_agent, "mainwin", None)
        _probe_service = getattr(_probe_mainwin, "db_chat_service", None) if _probe_mainwin else None
        _probe_ran = False  # Track if probe service was actually used
        _probe_succeeded = False  # Track if any probe actually found a valid chat
        if _probe_service and _ordered_candidates:
            _probe_ran = True
            for _src, _cid in _ordered_candidates:
                try:
                    _probe = _probe_service.get_chat_by_id(_cid, True)
                except Exception as _pe:
                    logger.debug(f"[send_response_back] chatId probe errored for {_cid!r} (src={_src}): {_pe}")
                    continue
                if _probe and _probe.get("success") and _probe.get("data") is not None:
                    chat_id = _cid
                    chat_id_source = _src
                    _probe_succeeded = True
                    break
                else:
                    logger.debug(
                        f"[send_response_back] chatId candidate {_cid!r} from {_src} "
                        f"did not resolve to a real chat — trying next"
                    )

        # If chat_id still not found but we have candidates, try format validation.
        # For A2A-based chat_ids (e.g., 'chat-xxx'), even if DB lookup fails due to
        # session issues or cloud storage, we can still use the chat_id directly.
        if not chat_id and _ordered_candidates:
            # Check if we have a valid A2A-style chat_id format
            _cid_for_fallback = _ordered_candidates[0][1] if _ordered_candidates else None
            _is_chat_format = _cid_for_fallback and (
                _cid_for_fallback.startswith("chat-") or
                _cid_for_fallback.startswith("session-") or
                len(_cid_for_fallback) >= 20  # UUID-like format
            )
            # Detailed logging for diagnosis
            logger.info(f"[send_response_back] === DB probe result ===")
            logger.info(f"[send_response_back] _ordered_candidates: {_ordered_candidates}")
            logger.info(f"[send_response_back] _probe_succeeded: {_probe_succeeded}")
            logger.info(f"[send_response_back] _cid_for_fallback: {_cid_for_fallback!r}")
            logger.info(f"[send_response_back] _is_chat_format: {_is_chat_format}")
            if _cid_for_fallback:
                logger.info(f"[send_response_back] startswith('chat-'): {_cid_for_fallback.startswith('chat-')}")
                logger.info(f"[send_response_back] len >= 20: {len(_cid_for_fallback) >= 20 if _cid_for_fallback else 'N/A'}")
            
            if _is_chat_format:
                chat_id = _cid_for_fallback
                chat_id_source = f"{_ordered_candidates[0][0]} (format-validated)"
                logger.warning(
                    f"[send_response_back] Using chatId WITHOUT DB validation: {chat_id} "
                    f"(format validated, DB probe failed for all candidates)"
                )
                # Log why DB probe failed - this is critical for debugging
                if _probe_service:
                    logger.warning(f"[send_response_back] DB service available: yes")
                    for _src, _cid in _ordered_candidates:
                        try:
                            _probe = _probe_service.get_chat_by_id(_cid, False)
                            logger.warning(f"[send_response_back] Probe result for {_cid!r} (src={_src}): success={_probe.get('success')}, error={_probe.get('error')}")
                        except Exception as _pe:
                            logger.warning(f"[send_response_back] Probe EXCEPTION for {_cid!r}: {_pe}")
                else:
                    logger.warning(f"[send_response_back] DB service NOT available, cannot probe")

        if chat_id:
            logger.info(
                f"[send_response_back] Using chatId: {chat_id} (from {chat_id_source}, "
                f"candidates_tried={[s for s,_ in _ordered_candidates]})"
            )
        else:
            logger.error(
                f"[send_response_back] No chatId found in any location "
                f"(candidates_tried={[s for s,_ in _ordered_candidates]})"
            )
        
        inbound_chat_attrs = {}
        try:
            # resume.py writes chat_attributes at state.attributes.chat_attributes
            # (see resume.py:1128 + build_node.py:6339). The old debug.chat_attributes
            # path is never populated, which silently broke A2A-sender routing and
            # forced this code to fall through to find_opposite_agent(chat_id) —
            # where chat_id is a synthesized customer_id like "sc", not a real DB
            # chat row id, so the lookup always failed.
            _attrs = state.get("attributes", {}) or {}
            inbound_chat_attrs = (
                _attrs.get("chat_attributes")
                or (_attrs.get("debug", {}) or {}).get("chat_attributes")
                or {}
            )
        except Exception:
            inbound_chat_attrs = {}

        # First priority: check attributes set by _node_state_baseline (from prep_skills_run)
        # These are set when an A2A message is received
        _attrs = state.get("attributes", {}) or {}
        inbound_sender_id = str(_attrs.get("inbound_sender_id") or "").strip()
        inbound_transport = str(_attrs.get("inbound_transport") or "a2a").strip()
        inbound_sender_type = str(_attrs.get("inbound_sender_type") or "").strip()

        # Second priority: check chat_attributes (set by resume.py during event handling)
        if not inbound_sender_id:
            inbound_chat_attrs = (
                _attrs.get("chat_attributes")
                or (_attrs.get("debug", {}) or {}).get("chat_attributes")
                or {}
            )
            if isinstance(inbound_chat_attrs, dict):
                inbound_sender_id = str(inbound_chat_attrs.get("senderId") or "").strip()
                inbound_transport = str(inbound_chat_attrs.get("transport") or "a2a").strip()
                inbound_sender_type = str(inbound_chat_attrs.get("senderType") or "").strip()

        # Third priority: extract from last event's context
        if not inbound_sender_id:
            try:
                last_evt = ((state.get("events") or [])[-1]) if isinstance(state.get("events"), list) and state.get("events") else {}
                evt_ctx = (last_evt or {}).get("context") or {}
                if isinstance(evt_ctx, dict):
                    inbound_sender_id = str(evt_ctx.get("senderId") or "").strip()
                    inbound_transport = inbound_transport or str(evt_ctx.get("transport") or "a2a").strip()
                    inbound_sender_type = inbound_sender_type or str(evt_ctx.get("senderType") or "").strip()
            except Exception:
                pass

        # Also extract chatId from events context if not found
        if not chat_id:
            try:
                _events = state.get("events", [])
                if isinstance(_events, list) and _events:
                    _last_evt = _events[-1]
                    if isinstance(_last_evt, dict):
                        _ctx = _last_evt.get("context", {})
                        if isinstance(_ctx, dict):
                            _cid = _ctx.get("chatId")
                            if _cid:
                                _ordered_candidates.append(("events.context.chatId (fallback)", str(_cid)))
                                chat_id = str(_cid)
                                chat_id_source = "events.context.chatId (fallback)"
            except Exception:
                pass
        
        # Debug: Log all available data for diagnosis
        logger.debug(f"[send_response_back] Diagnosis: chat_id={chat_id}, inbound_sender_id={inbound_sender_id}, inbound_transport={inbound_transport}, inbound_sender_type={inbound_sender_type}")
        logger.debug(f"[send_response_back] candidates_tried={[s for s,_ in _ordered_candidates]}")
        logger.debug(f"[send_response_back] attributes keys={list(state.get('attributes', {}).keys())}")
        logger.debug(f"[send_response_back] events count={len(state.get('events', []))}")
        
        if not chat_id and not inbound_sender_id:
            # Last resort: try to find any agent in the system to reply to
            logger.warning("[send_response_back] No chatId or inbound sender found, attempting direct GUI send")
            # Continue to attempt sending to GUI directly

        opposite_agent = None
        
        # Check both metadata.notification and attributes.notification
        # build_pend_event_node sets notification in attributes, not metadata
        notification = None
        try:
            _meta_notif = state.get("metadata", {})
            if isinstance(_meta_notif, dict):
                notification = _meta_notif.get("notification")
        except Exception:
            pass
        
        if not notification:
            try:
                _attr_notif = state.get("attributes", {})
                if isinstance(_attr_notif, dict):
                    notification = _attr_notif.get("notification")
            except Exception:
                pass
        
        # Ensure notification is a dict, not None
        if notification is None:
            notification = {}
        
        # If we have a2a_task_result notification, we need to find the opposite agent
        # even if inbound sender is not set (notification was set by build_pend_event_node)
        _has_a2a_notification = (
            isinstance(notification, dict) and notification.get("type") == "a2a_task_result"
        )
        
        if _has_a2a_notification:
            logger.info(f"[send_response_back] Found a2a_task_result notification: {notification.get('type')}")
        
        # Try to find task_id from messages or events to trace the sender
        task_id = ""
        try:
            _msgs = state.get("messages", [])
            if isinstance(_msgs, list) and len(_msgs) > 3:
                task_id = str(_msgs[3]) if _msgs[3] else ""
                if task_id:
                    logger.debug(f"[send_response_back] Found task_id from messages[3]: {task_id}")
        except Exception:
            pass
        
        if inbound_transport == "a2a" and inbound_sender_type == "agent" and inbound_sender_id:
            opposite_agent = get_agent_by_id(inbound_sender_id)
            if opposite_agent:
                logger.info(
                    f"[send_response_back] Using inbound A2A sender as reply target: "
                    f"{inbound_sender_id}"
                )
            else:
                logger.warning(
                    f"[send_response_back] Inbound A2A sender not found as agent: {inbound_sender_id}"
                )
        elif chat_id and chat_id != "unknown":
            opposite_agent = find_opposite_agent(self_agent, chat_id)
        
        # If we have a2a_task_result notification but no opposite_agent yet, try harder to find it
        if _has_a2a_notification and not opposite_agent:
            logger.info(f"[send_response_back] a2a_task_result notification found but opposite_agent is None, trying to find it")
            
            # Try to get chat_id from multiple sources
            _effective_chat_id = chat_id
            if not _effective_chat_id or _effective_chat_id == "unknown":
                # Try from attributes
                _effective_chat_id = state.get("attributes", {}).get("chat_id")
                if _effective_chat_id:
                    logger.debug(f"[send_response_back] Found chat_id from attributes: {_effective_chat_id}")
            
            if not _effective_chat_id or _effective_chat_id == "unknown":
                # Try from messages
                try:
                    _msgs = state.get("messages", [])
                    if _msgs and len(_msgs) > 1:
                        _effective_chat_id = _msgs[1] if isinstance(_msgs[1], str) else None
                        if _effective_chat_id:
                            logger.debug(f"[send_response_back] Found chat_id from messages[1]: {_effective_chat_id}")
                except Exception:
                    pass
            
            if _effective_chat_id and _effective_chat_id != "unknown":
                opposite_agent = find_opposite_agent(self_agent, _effective_chat_id)
                if opposite_agent:
                    logger.info(f"[send_response_back] Found opposite_agent via chat_id for a2a_task_result: {opposite_agent.card.id}")
            else:
                # Last resort: try to find any agent in the A2A server that might be waiting for this result
                # This handles the case where chat doesn't exist in DB but agent is still running
                try:
                    _a2a_server = getattr(self_agent, 'a2a_server', None)
                    if _a2a_server:
                        # Try to find agents that might be the parent (waiting for this task)
                        _all_agents = getattr(_a2a_server, '_agents', {})
                        for _agent_id, _agent_info in _all_agents.items():
                            if _agent_id != self_agent.card.id:
                                # Found another agent - might be the parent
                                _parent_agent = get_agent_by_id(_agent_id)
                                if _parent_agent:
                                    opposite_agent = _parent_agent
                                    logger.info(f"[send_response_back] Found potential parent agent via registry: {_agent_id}")
                                    break
                except Exception as _reg_err:
                    logger.debug(f"[send_response_back] Registry fallback failed: {_reg_err}")
            
        # Determine if this is an A2A task response (child agent responding to parent)
        # Key indicators:
        # 1. inbound_sender_id exists and is not empty (set by prep_skills_run when A2A message received)
        # 2. inbound_sender_id is not the current agent's ID
        # 3. Check multiple sources: state.attributes, state.events[-1].context, prompt_refs
        _effective_inbound_sender_id = inbound_sender_id
        _effective_inbound_transport = inbound_transport
        _effective_inbound_sender_type = inbound_sender_type
        
        # Also check events context as fallback (some messages set context there)
        if not _effective_inbound_sender_id:
            try:
                _events = state.get("events", [])
                if _events and isinstance(_events, list):
                    _last_evt = _events[-1]
                    if isinstance(_last_evt, dict):
                        _ctx = _last_evt.get("context", {})
                        if isinstance(_ctx, dict):
                            _effective_inbound_sender_id = str(_ctx.get("senderId") or "").strip()
                            _effective_inbound_transport = str(_ctx.get("transport") or "").strip()
                            _effective_inbound_sender_type = str(_ctx.get("senderType") or "").strip()
            except Exception:
                pass
        
        # Check prompt_refs for original event data (important for A2A responses)
        # When new messages arrive, state.attributes may be overwritten with new sender info
        # but prompt_refs preserves the original event context
        if not _effective_inbound_sender_id or _effective_inbound_sender_id.startswith("system_"):
            try:
                _prompt_refs = state.get("prompt_refs", {})
                if isinstance(_prompt_refs, dict):
                    _events_str = _prompt_refs.get("events", "")
                    if isinstance(_events_str, str) and _events_str.strip():
                        import json as _json
                        _evt_data = _json.loads(_events_str)
                        if isinstance(_evt_data, dict):
                            _evt_sender = str(_evt_data.get("senderId") or "").strip()
                            _evt_transport = str(_evt_data.get("transport") or "").strip()
                            _evt_sender_type = str(_evt_data.get("senderType") or "").strip()
                            if _evt_sender and not _evt_sender.startswith("system_"):
                                _effective_inbound_sender_id = _evt_sender
                                _effective_inbound_transport = _evt_transport or "a2a"
                                _effective_inbound_sender_type = _evt_sender_type or "agent"
                                logger.info(f"[send_response_back] Recovered A2A sender from prompt_refs: {_effective_inbound_sender_id}, transport={_effective_inbound_transport}")
            except Exception:
                pass
        
        _is_a2a_task_response = (
            _effective_inbound_sender_id and 
            _effective_inbound_sender_id != agent_id and
            (
                _effective_inbound_transport == "a2a" or 
                _effective_inbound_sender_type == "agent" or
                "agent_" in _effective_inbound_sender_id  # Agent IDs typically start with "agent_"
            )
        )
        if _is_a2a_task_response:
            logger.info(f"[send_response_back] Detected A2A task response: inbound_sender_id={_effective_inbound_sender_id}, transport={_effective_inbound_transport}, sender_type={_effective_inbound_sender_type}")

        msg_type = "text"
        qa_form = state["metadata"].get("qa_form", {})
        if qa_form:
            msg_type = "form"
        elif notification:
            msg_type = "notification"
        elif _is_a2a_task_response:
            # A2A task responses should use notification type with a2a_task_result
            # This ensures parent's pend_event_node correctly resumes
            msg_type = "notification"
            notification = {
                "type": "a2a_task_result",
                "result": state.get("result", {}),
                "sender_agent_id": agent_id,
            }

        if state["attributes"].get("i_tag", ""):
            i_tag = state["attributes"].get("i_tag", "")
        else:
            if isinstance(state["attributes"].get("params"), dict):
                i_tag = state["attributes"].get("params", {}).get("i_tag", "")
            else:
                i_tag = ""

        msg_id = str(uuid.uuid4())

        # Extract displayable message text from state result
        logger.debug("state result:",state["result"])
        if isinstance(state["result"], str):
            next_msg = state["messages"][-1]
        else:
            if isinstance(state["result"], dict):
                llm_result = state["result"].get("llm_result", {})
                if isinstance(llm_result, str):
                    next_msg = llm_result
                elif isinstance(llm_result, dict):
                    # Try multiple keys: "message", "next_prompt", "content", "text", "clarification_text"
                    next_msg = (
                        llm_result.get("message") or
                        llm_result.get("next_prompt") or
                        llm_result.get("content") or
                        llm_result.get("text") or
                        llm_result.get("clarification_text") or
                        llm_result.get("casual_chat_response") or
                        ""
                    )
                    if not next_msg:
                        next_msg = json.dumps(llm_result, ensure_ascii=False)
                else:
                    next_msg = ""
            else:
                next_msg = "sorry, I was lost, could you rephrase your question?"
        
        # If we have a2a_task_result notification, extract the message from it
        if notification.get("type") == "a2a_task_result" and isinstance(notification, dict):
            notif_result = notification.get("result", {})
            if isinstance(notif_result, dict):
                _notif_msg = notif_result.get("message", "")
                if _notif_msg:
                    next_msg = _notif_msg
                    logger.debug(f"[send_response_back] Using message from a2a_task_result notification")

        # A2A SDK rejects empty TextPart content - skip sending if message is empty
        # This can happen when skill pauses at pend_event_node before any LLM response
        # But if we have notification (e.g., a2a_task_result), don't skip - we need to send it
        if (not next_msg or (isinstance(next_msg, str) and not next_msg.strip())) and not notification:
            logger.debug("[send_response_back] Skipping send: message text is empty and no notification")
            return state

        # If we have a2a_task_result notification but no opposite_agent, we need to directly
        # resume the parent workflow's pend_event. This handles the case where a dispatched
        # agent completes and sends its result back, but the parent workflow is waiting at
        # a pend_event_node for this result.
        if _has_a2a_notification and opposite_agent is None:
            logger.info("[send_response_back] a2a_task_result with no opposite_agent - attempting direct workflow resume")
            try:
                _notif_result = notification.get("result", {})
                _sender_agent_id = None
                
                # Try to get sender_agent_id from multiple sources
                # The dispatcher's agent_id was passed when sending the task
                if isinstance(_notif_result, dict):
                    _sender_agent_id = _notif_result.get("sender_agent_id")
                if not _sender_agent_id:
                    _sender_agent_id = notification.get("sender_agent_id")
                if not _sender_agent_id:
                    _sender_agent_id = state.get("attributes", {}).get("inbound_sender_id")
                if not _sender_agent_id:
                    # Check params.sender_agent_id (newly added in _build_chat_message)
                    _params = state.get("attributes", {}).get("params", {})
                    if isinstance(_params, dict):
                        _sender_agent_id = _params.get("sender_agent_id")
                        if not _sender_agent_id:
                            # Check params.metadata.sender_agent_id (nested structure from _build_chat_message)
                            _meta = _params.get("metadata", {})
                            if isinstance(_meta, dict):
                                _sender_agent_id = _meta.get("sender_agent_id")
                                if not _sender_agent_id:
                                    # Also check params.metadata.params.sender_agent_id (deeply nested)
                                    _meta_params = _meta.get("params", {})
                                    if isinstance(_meta_params, dict):
                                        _sender_agent_id = _meta_params.get("sender_agent_id")
                if not _sender_agent_id:
                    # Check attributes.metadata.sender_agent_id
                    _attrs_meta = state.get("attributes", {}).get("metadata", {})
                    if isinstance(_attrs_meta, dict):
                        _sender_agent_id = _attrs_meta.get("sender_agent_id")
                
                if _sender_agent_id:
                    # Build the resume payload with a2a_task_result event
                    _resume_payload = {
                        "event_type": "a2a_task_result",
                        "result": _notif_result,
                        "_event_envelope": {
                            "type": "a2a_task_result",
                            "data": _notif_result,
                            "source": _sender_agent_id
                        }
                    }
                    
                    # Try to find parent agent ID from state.input - this is the original send_chat JSON
                    # which contains the sender_agent_id of the parent that dispatched this task
                    _parent_agent_id = None
                    
                    # First priority: check notification.result.parent_agent_id (set by build_chat_node)
                    # This is the most reliable source for sub-agent -> parent A2A routing
                    if isinstance(_notif_result, dict):
                        _parent_agent_id = _notif_result.get("parent_agent_id")
                    
                    # Second priority: parse state.input for sender_agent_id (original send_chat payload)
                    if not _parent_agent_id:
                        try:
                            _input = state.get("input", "")
                            if _input and isinstance(_input, str):
                                _input_lower = _input.strip()
                                if _input_lower.startswith("{") and _input_lower.endswith("}"):
                                    try:
                                        _input_json = json.loads(_input)
                                        if isinstance(_input_json, dict):
                                            _parent_agent_id = _input_json.get("sender_agent_id")
                                            if _parent_agent_id:
                                                logger.info(f"[send_response_back] Found parent agent_id from state.input: {_parent_agent_id}")
                                    except Exception:
                                        pass
                        except Exception as _input_err:
                            logger.debug(f"[send_response_back] Error parsing state.input: {_input_err}")
                    
                    # Also try to find parent agent via events - the event from parent should contain parent's agent info
                    if not _parent_agent_id:
                        try:
                            _events = state.get("events", [])
                            for _evt in reversed(_events):
                                _evt_ctx = _evt.get("context", {}) if isinstance(_evt, dict) else {}
                                # Check if this event is from another agent (not user)
                                _evt_sender_type = _evt_ctx.get("senderType", "")
                                _evt_sender_id = _evt_ctx.get("senderId", "")
                                if _evt_sender_type == "agent" and _evt_sender_id and _evt_sender_id != _sender_agent_id:
                                    _parent_agent_id = _evt_sender_id
                                    logger.info(f"[send_response_back] Found parent agent from events: {_parent_agent_id}")
                                    break
                        except Exception as _evt_err:
                            logger.debug(f"[send_response_back] Error looking for parent in events: {_evt_err}")
                    
                    # If we found parent agent ID, use it as the waiter target
                    # Otherwise fallback to original sender (which is the user, not useful)
                    _effective_waiter_id = _parent_agent_id
                    if not _effective_waiter_id:
                        logger.warning(f"[send_response_back] Could not find parent agent ID, original sender={_sender_agent_id} is likely user not agent")
                    
                    # Try to find the parent agent and send A2A message back
                    # This is the correct approach: send response via A2A, which will trigger
                    # the parent's send_response_back and resume the pend_event_node
                    if _effective_waiter_id:
                        try:
                            _parent_agent = get_agent_by_id(_effective_waiter_id)
                            if _parent_agent:
                                # Build A2A response message
                                _agent_response_message = build_a2a_response_message(
                                    agent_id=agent_id,
                                    chat_id=chat_id or "",
                                    msg_id=msg_id or str(uuid.uuid4()),
                                    task_id="",
                                    msg_text=next_msg or "",
                                    sender_name=self_agent.card.name,
                                    msg_type="a2a_response",
                                    i_tag=i_tag or "",
                                    attachments=state.get("attachments", []),
                                    form=None,
                                    notification=notification if notification else None,
                                )
                                # Include the result data in the notification
                                if isinstance(_agent_response_message, dict) and _agent_response_message.get("attributes"):
                                    _agent_response_message["attributes"]["notification"] = {
                                        "type": "a2a_task_result",
                                        "result": _notif_result
                                    }
                                logger.info(f"[send_response_back] Sending A2A response to parent agent: {_effective_waiter_id}")
                                self_agent.a2a_send_chat_message_async(_parent_agent, _agent_response_message)
                                logger.info(f"[send_response_back] A2A response sent to parent via a2a_send_chat_message_async")
                                return state
                            else:
                                logger.warning(f"[send_response_back] Parent agent not found: {_effective_waiter_id}")
                        except Exception as _a2a_err:
                            logger.warning(f"[send_response_back] Failed to send A2A response to parent: {_a2a_err}")
                    
                    # Fallback: try to resolve via task_manager (handles Future-based waiters)
                    _task_manager = getattr(self_agent, 'a2a_server', None)
                    if _task_manager:
                        _task_manager = getattr(_task_manager, 'task_manager', None)
                    if not _task_manager:
                        _task_manager = getattr(self_agent, 'a2a_task_executor', None)
                    
                    if _effective_waiter_id and _task_manager and hasattr(_task_manager, 'resolve_waiter'):
                        try:
                            _task_manager.resolve_waiter(_effective_waiter_id, _resume_payload)
                            logger.info(f"[send_response_back] Resumed parent via task_manager with waiter_id={_effective_waiter_id}")
                            return state
                        except Exception as _tm_err:
                            logger.warning(f"[send_response_back] task_manager.resolve_waiter failed: {_tm_err}")
                    
                    # Alternative: try to find and resume the task directly via agent's runner
                    if _effective_waiter_id:
                        try:
                            _agent_runner = getattr(self_agent, 'runner', None)
                            if _agent_runner and hasattr(_agent_runner, 'resume_task'):
                                # Find the task waiting for this result
                                if hasattr(_agent_runner, 'tasks'):
                                    for _tid, _task in _agent_runner.tasks.items():
                                        _task_i_tag = (_task.metadata.get("state", {}) or {}).get("attributes", {}).get("i_tag", "")
                                        _task_cloud_id = (_task.metadata.get("state", {}) or {}).get("attributes", {}).get("cloud_task_id", "")
                                        if _task_i_tag == _effective_waiter_id or _task_cloud_id == _effective_waiter_id:
                                            # Found the waiting task - resume it
                                            _agent_runner.resume_task(_tid)
                                            logger.info(f"[send_response_back] Resumed waiting task {_tid} for waiter {_effective_waiter_id}")
                                            return state
                        except Exception as _resume_err:
                            logger.debug(f"[send_response_back] Agent runner resume failed: {_resume_err}")
                        
                else:
                    logger.warning("[send_response_back] Could not determine sender_agent_id for a2a_task_result resume")
            except Exception as _a2a_resume_err:
                logger.warning(f"[send_response_back] a2a_task_result direct resume failed: {_a2a_resume_err}")
        
        # If opposite agent exists (agent-to-agent chat), send via A2A
        if opposite_agent is not None:
            agent_response_message = build_a2a_response_message(
                agent_id=agent_id,
                chat_id=chat_id,
                msg_id=msg_id,
                task_id="",
                msg_text=next_msg,
                sender_name=self_agent.card.name,
                msg_type=msg_type,
                i_tag=i_tag,
                attachments=state.get("attachments", []),
                form=qa_form if qa_form else None,
                notification=notification if notification else None,
            )
            logger.info(f"[send_response_back] A2A path: opposite_agent={opposite_agent}, chat_id={chat_id}")
            self_agent.a2a_send_chat_message_async(opposite_agent, agent_response_message)
            logger.info(f"[send_response_back] A2A send initiated (fire-and-forget)")
            return state
        else:
            # No opposite agent found (human user chat)
            # Try to find chat_id from events if not available
            _effective_chat_id = chat_id
            if not _effective_chat_id:
                try:
                    _events = state.get("events", [])
                    if _events and isinstance(_events, list):
                        _last_evt = _events[-1]
                        if isinstance(_last_evt, dict):
                            _effective_chat_id = _last_evt.get("context", {}).get("chatId")
                            if _effective_chat_id:
                                logger.info(f"[send_response_back] Using chat_id from events: {_effective_chat_id}")
                except Exception:
                    pass
            
            # Check if this message originated from an external channel
            logger.warning(f"[send_response_back] GUI path: opposite_agent=None, will try ChatMessageSender, chat_id={_effective_chat_id}")
            try:
                from app_context import AppContext
                _mainwin = AppContext.get_main_window()
                _bridge = getattr(_mainwin, "channel_bridge", None)
                if _bridge:
                    _result = _bridge.route_reply(state, next_msg)
                    if _result is not None:
                        # Reply was routed to an external channel
                        return state
            except Exception as _ch_err:
                logger.debug(f"[send_response_back] Channel bridge check failed: {_ch_err}")

            # Fall through to GUI path
            from agent.ec_tasks.message_sender import ChatMessageSender
            sender = ChatMessageSender(self_agent)
            content_type = msg_type
            
            logger.info(f"[send_response_back] GUI path: sender.send_text(chat_id={_effective_chat_id}, msg_len={len(next_msg) if isinstance(next_msg, str) else 'N/A'})")
            
            if msg_type == "form" and qa_form:
                sender.send_form(_effective_chat_id, qa_form)
            elif msg_type == "notification" and notification:
                sender.send_notification(_effective_chat_id, notification)
            else:
                sender.send_text(_effective_chat_id, next_msg)
            return state
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.error(f"[send_response_back] EXCEPTION: {err_trace}")
        # Return state even on exception so the workflow can continue
        return state


def run_async_in_sync(awaitable):
    """Run an async awaitable from sync code with safe event loop lifecycle and cleanup."""
    # Event loop policy is handled at the application level (main.py)
    # Trust that the correct policy is already set for the main process

    loop = asyncio.new_event_loop()
    try:
        # Ensure the newly created loop is current in this thread
        asyncio.set_event_loop(loop)
        # Wrap in a Task so that asyncio.wait_for / asyncio.timeout (used by
        # browser_use's CDP click handler) work correctly.  Without this,
        # Python 3.11+ raises "RuntimeError: Timeout should be used inside a task"
        # which causes every CDP coordinate click to fail and fall back to a JS
        # .click() that doesn't honour target="_blank".
        return loop.run_until_complete(loop.create_task(awaitable))
    finally:
        try:
            pending_tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending_tasks:
                t.cancel()
            if pending_tasks:
                loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
            if hasattr(loop, "shutdown_asyncgens"):
                loop.run_until_complete(loop.shutdown_asyncgens())
            if hasattr(loop, "shutdown_default_executor"):
                loop.run_until_complete(loop.shutdown_default_executor())
        except Exception:
            pass
        loop.close()


def _run_async_in_worker_thread_once(awaitable_or_factory):
    """Legacy per-call thread fallback (used when persistent loop is unavailable)."""
    result_holder = {}
    error_holder = {}

    def _worker():
        if sys.platform.startswith("win"):
            try:
                if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
        try:
            loop = asyncio.get_event_loop_policy().new_event_loop()
        except Exception:
            try:
                if sys.platform.startswith("win") and hasattr(asyncio, "ProactorEventLoop"):
                    loop = asyncio.ProactorEventLoop()
                else:
                    loop = asyncio.new_event_loop()
            except Exception:
                loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            coro = awaitable_or_factory() if callable(awaitable_or_factory) else awaitable_or_factory
            result_holder["result"] = loop.run_until_complete(loop.create_task(coro))
        except Exception as e:
            error_holder["error"] = e
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                if hasattr(loop, "shutdown_asyncgens"):
                    loop.run_until_complete(loop.shutdown_asyncgens())
                if hasattr(loop, "shutdown_default_executor"):
                    loop.run_until_complete(loop.shutdown_default_executor())
            except Exception:
                pass
            loop.close()

    t = Thread(target=_worker, name="playwright-worker", daemon=True)
    t.start()
    t.join()
    if "error" in error_holder:
        raise error_holder["error"]
    return result_holder.get("result")


def run_async_in_worker_thread(awaitable_or_factory):
    """Run an async awaitable in a dedicated worker thread."""
    return _run_async_in_worker_thread_once(awaitable_or_factory)
_persistent_worker_runners: dict[str, "_PersistentAsyncWorkerThread"] = {}
_persistent_worker_runners_lock = threading.Lock()


class _PersistentAsyncWorkerThread:
    """Dedicated background thread with a long-lived asyncio loop."""

    def __init__(self, name: str):
        self.name = name
        self._thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._closed = False

    def _create_loop(self) -> asyncio.AbstractEventLoop:
        if sys.platform.startswith("win"):
            try:
                current_policy = asyncio.get_event_loop_policy()
                if hasattr(asyncio, "WindowsProactorEventLoopPolicy") and not isinstance(
                    current_policy, asyncio.WindowsProactorEventLoopPolicy
                ):
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
        try:
            return asyncio.get_event_loop_policy().new_event_loop()
        except Exception:
            try:
                if sys.platform.startswith("win") and hasattr(asyncio, "ProactorEventLoop"):
                    return asyncio.ProactorEventLoop()
            except Exception:
                pass
            return asyncio.new_event_loop()

    def start(self) -> None:
        if self._thread and self._thread.is_alive() and self._loop and not self._loop.is_closed():
            return

        self._ready.clear()
        self._closed = False

        def _worker() -> None:
            loop = self._create_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            logger.info(
                f"[PersistentAsyncWorker] Started thread={threading.current_thread().name}, "
                f"loop={type(loop).__name__}, name={self.name}"
            )
            self._ready.set()
            try:
                loop.run_forever()
            finally:
                try:
                    pending_tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                    for t in pending_tasks:
                        t.cancel()
                    if pending_tasks:
                        loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                    if hasattr(loop, "shutdown_asyncgens"):
                        loop.run_until_complete(loop.shutdown_asyncgens())
                    if hasattr(loop, "shutdown_default_executor"):
                        loop.run_until_complete(loop.shutdown_default_executor())
                except Exception:
                    pass
                loop.close()
                self._closed = True
                logger.info(f"[PersistentAsyncWorker] Stopped name={self.name}")

        self._thread = Thread(target=_worker, name=self.name, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10.0)
        if not self._loop:
            raise RuntimeError(f"Persistent worker loop failed to start: {self.name}")

    def submit(self, awaitable_or_factory, timeout_s: float | None = None):
        self.start()
        loop = self._loop
        if loop is None:
            raise RuntimeError(f"Persistent worker loop is unavailable: {self.name}")

        async def _invoke():
            # ws174: start-marker. The 2026-07-12 22:32:35 front-desk freeze was a
            # submitted coroutine that NEVER began executing while the caller
            # blocked in future.result() with no timeout — and thread stack dumps
            # can't show suspended coroutines, so nothing named the wedge. This
            # log line is the scheduled-vs-started discriminator for next time.
            logger.info(f"[PersistentAsyncWorker] task START name={self.name}")
            if callable(awaitable_or_factory):
                return await awaitable_or_factory()
            return await awaitable_or_factory

        future = asyncio.run_coroutine_threadsafe(_invoke(), loop)
        if timeout_s is None or timeout_s <= 0:
            return future.result()
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            # ws174: bound the wait — an unbounded result() froze the front-desk
            # node thread for 5+ minutes (user had to kill the app). Cancel the
            # straggler and dump the worker loop's task list so the wedge is
            # identifiable post-mortem.
            try:
                future.cancel()
            except Exception:
                pass
            _tasks_desc = "<unavailable>"
            try:
                _tasks_holder: list = []
                _done = threading.Event()

                def _snapshot_tasks():
                    try:
                        _tasks_holder.extend(
                            repr(t)[:200] for t in asyncio.all_tasks(loop)
                        )
                    finally:
                        _done.set()

                loop.call_soon_threadsafe(_snapshot_tasks)
                if _done.wait(timeout=2.0):
                    _tasks_desc = " | ".join(_tasks_holder[:8]) or "<none>"
            except Exception:
                pass
            logger.error(
                f"[PersistentAsyncWorker] ws174 submit TIMED OUT after "
                f"{timeout_s:.0f}s name={self.name} — coroutine cancelled; "
                f"loop tasks at timeout: {_tasks_desc}"
            )
            raise

    def stop(self) -> None:
        loop = self._loop
        if not loop or loop.is_closed():
            return
        loop.call_soon_threadsafe(loop.stop)
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=5.0)


def run_async_in_persistent_worker_thread(
    awaitable_or_factory,
    worker_name: str = "browser-use-persistent-worker",
    timeout_s: float | None = None,
):
    """Run an async awaitable on a long-lived worker thread/loop.

    Unlike run_async_in_worker_thread(), this keeps the event loop alive after the
    submitted coroutine completes. Use this for workloads that intentionally spawn
    background asyncio tasks that must survive the caller's completion.

    ws174: *timeout_s* bounds the caller-side wait (None/<=0 keeps the legacy
    unbounded wait). On expiry the pending coroutine is cancelled and
    ``concurrent.futures.TimeoutError`` is raised — an unbounded wait froze the
    live-chat front-desk node thread for 5+ minutes on 2026-07-12 when the
    submitted coroutine never started.
    """
    with _persistent_worker_runners_lock:
        runner = _persistent_worker_runners.get(worker_name)
        if runner is None or runner._closed:
            runner = _PersistentAsyncWorkerThread(name=worker_name)
            _persistent_worker_runners[worker_name] = runner

    logger.debug(f"[run_async_in_persistent_worker_thread] worker={worker_name}")
    return runner.submit(awaitable_or_factory, timeout_s=timeout_s)


def stop_persistent_worker_thread(worker_name: str) -> bool:
    with _persistent_worker_runners_lock:
        runner = _persistent_worker_runners.pop(worker_name, None)
    if runner is None:
        return False
    try:
        runner.stop()
        return True
    except Exception as exc:
        logger.warning(f"[PersistentAsyncWorker] Failed to stop name={worker_name}: {exc}")
        return False


def stop_persistent_worker_threads_by_prefix(prefix: str) -> int:
    stopped = 0
    with _persistent_worker_runners_lock:
        names = [name for name in _persistent_worker_runners if str(name).startswith(prefix)]
    for name in names:
        if stop_persistent_worker_thread(name):
            stopped += 1
    return stopped


def stop_persistent_worker_threads_containing(fragment: str) -> int:
    fragment = str(fragment or "")
    if not fragment:
        return 0
    stopped = 0
    with _persistent_worker_runners_lock:
        names = [name for name in _persistent_worker_runners if fragment in str(name)]
    for name in names:
        if stop_persistent_worker_thread(name):
            stopped += 1
    return stopped


def try_parse_json(s: str):
    """
    If `s` is valid JSON, return the parsed object.
    Otherwise, return the original string.
    """
    if not isinstance(s, str):
        return s  # not a string, leave it alone
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return s

def find_key(data, target_key, path=None):
    """
    Recursively search nested dict/list for a key.
    Returns list of (path, value) where the key was found.
    """
    if path is None:
        path = []

    results = []

    if isinstance(data, dict):
        for k, v in data.items():
            new_path = path + [k]
            if k == target_key:
                results.append((".".join(new_path), v))
            results.extend(find_key(v, target_key, new_path))

    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = path + [f"[{i}]"]
            results.extend(find_key(item, target_key, new_path))

    return results


def debuggable_node(node_fn, name):
    """Wrap a node so it can pause after execution."""
    def wrapper(state, *args, **kwargs):
        # Run the node normally
        result = node_fn(state, *args, **kwargs)

        # Always return both result and an interrupt "checkpoint"
        return [
            result,
            Interrupt(value={"at": name, "state": {**state, **result}})
        ]
    return wrapper


def breakpoint_wrapper(node_fn, node_name: str, bp_manager: BreakpointManager):
    """Wrap node function so it pauses if node has a breakpoint set."""
    def wrapper(state, *args, **kwargs):
        result = node_fn(state, *args, **kwargs)
        if bp_manager.has_breakpoint(node_name):
            return [
                result,
                Interrupt(value={"paused_at": node_name, "state": {**state, **result}})
            ]
        return result
    return wrapper


def step1(state): return {"a": 1}
def step2(state): return {"b": state["a"] + 2}
def step3(state): return {"c": state["b"] * 2}
# Build graph with wrapped nodes
# python
# 复制代码
# from langgraph.graph import StateGraph, END
#
# bp_manager = BreakpointManager()
#
# graph = StateGraph(dict)
# graph.add_node("step1", breakpoint_wrapper(step1, "step1", bp_manager))
# graph.add_node("step2", breakpoint_wrapper(step2, "step2", bp_manager))
# graph.add_node("step3", breakpoint_wrapper(step3, "step3", bp_manager))
#
# graph.set_entry_point("step1")
# graph.add_edge("step1", "step2")
# graph.add_edge("step2", "step3")
# graph.add_edge("step3", END)
#
# compiled = graph.compile()
# 🔹 Run + Pause/Resume from GUI
# python
# 复制代码
# # GUI (or user) sets a breakpoint
# bp_manager.set_breakpoint("step2")
#
# for event in compiled.stream({}):
#     if isinstance(event, dict):
#         print("State update:", event)
#
#     elif isinstance(event, Interrupt):
#         print(f"⏸ Paused at {event.value['paused_at']}")
#         bp_manager.capture_interrupt(event)
#         break   # stop loop here until GUI resumes
# Later in GUI callback
# python
# 复制代码
# # User clicks "resume"
# bp_manager.resume()
# Clear breakpoint at runtime
# python
# 复制代码
# bp_manager.clear_breakpoint("step2")

# Token limit for context window (adjust based on your model's limits and cost considerations)
CONTEXT_WINDOW_SIZE = 25536  # Conservative limit for GPT-4


def _compress_tool_result(content: str, max_length: int = 500) -> str:
    """
    Compress tool result content to save tokens while preserving key information.
    
    Strategy:
    - Success/failure status: Keep complete
    - Error messages: Keep first 200 chars
    - Data results:
      - Lists: Keep first 3 items + "...total N items"
      - Long text: Keep first 300 chars + "...(truncated)"
    - HTML/JSON: Extract key fields, discard redundant parts
    
    Args:
        content: Tool result content to compress
        max_length: Maximum length to keep (default: 500)
        
    Returns:
        Compressed content string
    """
    if not content or len(content) <= max_length:
        return content
    
    # Try to parse as JSON
    try:
        import json
        data = json.loads(content)
        
        if isinstance(data, list):
            # List: keep first 3 items
            compressed = data[:3]
            omitted = len(data) - 3
            result = json.dumps(compressed, ensure_ascii=False)
            if omitted > 0:
                result += f"\n...(total {len(data)} items, {omitted} omitted)"
            return result
            
        elif isinstance(data, dict):
            # Dict: only keep key fields
            key_fields = ['status', 'success', 'error', 'message', 'data', 'result', 'code']
            compressed = {k: v for k, v in data.items() if k in key_fields}
            return json.dumps(compressed, ensure_ascii=False)
    except:
        pass
    
    # Plain text: truncate
    return content[:max_length] + f"\n...(truncated, original length: {len(content)} chars)"


def _remove_old_screenshots(history: list, keep_recent: int = 3) -> list:
    """
    Remove old screenshots from history, keeping only the most recent N.
    
    In Vision mode, screenshots consume significant tokens (1000-3000 each).
    Usually only the most recent screenshots are needed to understand current state.
    
    Args:
        history: List of messages
        keep_recent: Number of recent screenshots to keep (default: 3)
        
    Returns:
        History with old screenshots removed
    """
    from langchain_core.messages import HumanMessage, AIMessage
    
    screenshot_count = 0
    result = []
    
    # Traverse from end to start (keep most recent)
    for msg in reversed(history):
        if isinstance(msg, (HumanMessage, AIMessage)):
            content = msg.content
            has_image = False
            
            # Check if message contains image
            if isinstance(content, list):
                has_image = any(
                    isinstance(item, dict) and item.get('type') == 'image_url'
                    for item in content
                )
            elif isinstance(content, str):
                has_image = 'data:image' in content or 'base64' in content
            
            if has_image:
                screenshot_count += 1
                if screenshot_count > keep_recent:
                    # Remove image, keep only text part
                    if isinstance(content, list):
                        text_only = [item for item in content if item.get('type') == 'text']
                        msg.content = text_only if text_only else "[Screenshot removed to save tokens]"
                    else:
                        msg.content = "[Screenshot removed to save tokens]"
        
        result.append(msg)
    
    return list(reversed(result))


def get_recent_context(
    history: list, 
    max_tokens: int = CONTEXT_WINDOW_SIZE,
    compress_tools: bool = True,
    remove_old_screenshots: bool = True,
    keep_screenshots: int = 3
) -> list:
    """
    Returns a subset of chat history that fits within the token limit.

    Strategy:
    1. Always include the most recent SystemMessage (if exists) for context
    2. Optimize for Agent scenarios: compress tool results, remove old screenshots
    3. Include as many recent messages as possible within the token limit
    4. Use conservative token estimation: ~3 characters per token (safer than 4)
    5. Trust the caller to provide appropriate max_tokens based on model capabilities

    Args:
        history: List of LangChain message objects (SystemMessage, HumanMessage, AIMessage)
        max_tokens: Maximum number of tokens to include (from model's actual capabilities)
        compress_tools: Compress tool results to save tokens (default: True)
        remove_old_screenshots: Remove old screenshots in Vision mode (default: True)
        keep_screenshots: Number of recent screenshots to keep (default: 3)

    Returns:
        List of messages that fit within the token limit
    """
    if not history or not isinstance(history, list):
        return []

    from langchain_core.messages import SystemMessage

    # Filter out unsupported message types that LangChain's OpenAI chat models 
    # cannot serialize. We keep standard chat message types.
    # ActionMessage (tool results) must be converted to HumanMessage for LangChain compatibility.
    allowed_types = {"system", "human", "ai", "tool", "function"}
    
    from langchain_core.messages import HumanMessage

    filtered_history: list = []
    for msg in history:
        try:
            msg_type = getattr(msg, "type", None)
            if msg_type in allowed_types or isinstance(msg, SystemMessage):
                filtered_history.append(msg)
            elif msg_type == "action":
                # Convert ActionMessage to HumanMessage for LangChain compatibility
                # This preserves the tool result content so the LLM can see it
                action_content = msg.content if hasattr(msg, 'content') else str(msg)
                # Wrap in a clear format so LLM knows this is a tool result
                converted_msg = HumanMessage(content=f"[Tool Result]\n{action_content}")
                filtered_history.append(converted_msg)
                logger.debug(f"[get_recent_context] Converted ActionMessage to HumanMessage (len={len(action_content)})")
            else:
                # Keep for debugging but do not send to LLM
                logger.debug(
                    f"[get_recent_context] Skipping unsupported message in history: "
                    f"{type(msg)} (type={msg_type})"
                )
        except Exception:
            # Defensive: if anything goes wrong during inspection, skip the msg
            continue

    if not filtered_history:
        return []

    # Agent optimization: Remove old screenshots to save tokens
    if remove_old_screenshots:
        original_count = len(filtered_history)
        filtered_history = _remove_old_screenshots(filtered_history, keep_recent=keep_screenshots)
        if len(filtered_history) < original_count:
            logger.debug(f"[get_recent_context] Removed old screenshots, kept {keep_screenshots} most recent")

    # ── Multimodal hygiene: rewrite stale string-form HumanMessages that carry
    # embedded ``data:image/...;base64,...`` blobs into proper multimodal
    # content lists ``[{"type":"text", ...}, {"type":"image_url", ...}]``.
    #
    # This is a Layer-3 safety net for messages that landed in history
    # BEFORE the build_node multimodal upgrade hook ran (e.g., turns from
    # a previous app start, or from code paths that bypass the LLM-node
    # pre-hook).  Without this, OpenAI's API tokenizer counts every base64
    # byte as text and the call fails with ``context_length_exceeded`` even
    # though our local token filter (estimate_message_tokens) correctly
    # ignored the blob.
    #
    # Behaviour:
    #   - String content with a data URI → rewritten in place to a
    #     multimodal list (text part with blob stripped + one
    #     ``image_url`` part per detected blob).
    #   - String content without a data URI → untouched.
    #   - List content → untouched (already multimodal).
    #   - Wrapped in try/except so any unexpected message shape is silently
    #     skipped (preserve current behaviour on the failure path).
    try:
        from agent.ec_skills.browser_use_extension.token_utils import (
            _DATA_URI_IMAGE_RE,
        )
        _mm_rewrites = 0
        for _i, _m in enumerate(filtered_history):
            try:
                _content = getattr(_m, "content", None)
                if not isinstance(_content, str):
                    continue
                if "data:image/" not in _content:
                    continue
                _uris = _DATA_URI_IMAGE_RE.findall(_content)
                if not _uris:
                    continue
                from utils.data_uri_sanitizer import sanitize_text_data_uris
                _stripped_text = sanitize_text_data_uris(_content, preview_chars=4000)
                _new_parts = [{"type": "text", "text": _stripped_text}]
                # Mutate in place so caller-visible message objects update.
                _m.content = _new_parts
                _mm_rewrites += 1
            except Exception:
                continue
        if _mm_rewrites:
            logger.info(
                f"[get_recent_context] Layer-3 multimodal rewrite: "
                f"{_mm_rewrites} stale string-form message(s) sanitized "
                f"(data_uri blobs removed from history context)"
            )
    except Exception as _mm_l3_exc:
        # Defensive: never let this rewrite break the rest of the pipeline.
        logger.warning(
            f"[get_recent_context] Layer-3 multimodal rewrite skipped: "
            f"{type(_mm_l3_exc).__name__}: {_mm_l3_exc}"
        )

    # Agent optimization: Compress tool results to save tokens
    if compress_tools:
        compressed_count = 0
        for msg in filtered_history:
            # Check if this is a tool result message
            is_tool_result = (
                msg.type in ('tool', 'function') or 
                '[Tool Result]' in str(msg.content)
            )
            
            if is_tool_result and hasattr(msg, 'content'):
                original_len = len(str(msg.content))
                if original_len > 4000:
                    msg.content = _compress_tool_result(str(msg.content), max_length=4000)
                    compressed_count += 1
                    logger.debug(f"[get_recent_context] Compressed tool result: {original_len} → {len(msg.content)} chars")
        
        if compressed_count > 0:
            logger.debug(f"[get_recent_context] Compressed {compressed_count} tool results")

    # Use unified token estimation from token_utils module
    # This ensures consistency across all components
    from agent.ec_skills.browser_use_extension.token_utils import estimate_message_tokens
    
    def estimate_tokens(msg) -> int:
        """
        Estimate tokens for a message using unified token_utils.
        Uses 2.5 chars/token for mixed content (more accurate than old 3 chars/token).
        """
        return estimate_message_tokens(msg)

    # Find the most recent SystemMessage
    system_msg = None
    system_msg_idx = -1
    for idx in range(len(filtered_history) - 1, -1, -1):
        if isinstance(filtered_history[idx], SystemMessage):
            system_msg = filtered_history[idx]
            system_msg_idx = idx
            break

    # Start with system message if it exists and fits
    result = []
    token_count = 0

    if system_msg:
        system_tokens = estimate_tokens(system_msg)
        if system_tokens < max_tokens:
            result.append(system_msg)
            token_count += system_tokens

    # Add messages from the end (most recent) going backwards
    # Skip the system message if we already added it
    for idx in range(len(filtered_history) - 1, -1, -1):
        if idx == system_msg_idx:
            continue  # Already added

        msg = filtered_history[idx]
            
        msg_tokens = estimate_tokens(msg)

        if token_count + msg_tokens > max_tokens:
            break  # Would exceed limit

        result.insert(1 if system_msg else 0, msg)  # Insert after system message
        token_count += msg_tokens

    logger.debug(f"Context window: {len(result)} messages, ~{token_count} tokens (limit: {max_tokens})")
    return result


# =============================================================================
# LLM JSON Error Diagnosis Utilities
# =============================================================================

def analyze_json_error(error_msg: str) -> dict:
    """
    Parse LLM JSON error message and extract key information.

    Example error:
        "Invalid JSON: EOF while parsing a list at line 1 column 6112"

    Returns:
        dict with keys: error_type, column, truncated_at, likely_cause, recommendation
    """
    import re

    result = {
        "error_type": None,
        "column": None,
        "truncated_at": None,
        "likely_cause": None,
        "recommendation": None
    }

    col_match = re.search(r'column\s+(\d+)', error_msg)
    if col_match:
        result["column"] = int(col_match.group(1))
        result["truncated_at"] = int(col_match.group(1))

    if "EOF" in error_msg and "parsing" in error_msg:
        result["error_type"] = "EOF_TRUNCATION"
        result["likely_cause"] = "LLM output was truncated (likely by max_tokens limit)"
        result["recommendation"] = (
            "Increase max_tokens in LLM configuration, or reduce message length. "
            "The LLM's output was cut off mid-JSON, causing parse failure."
        )
    elif "validation error" in error_msg.lower():
        result["error_type"] = "VALIDATION_ERROR"
        result["likely_cause"] = "LLM output doesn't match expected schema"
        result["recommendation"] = (
            "Check LLM output format. The model may not be following the JSON schema correctly."
        )
    elif "unexpected token" in error_msg.lower():
        result["error_type"] = "SYNTAX_ERROR"
        result["likely_cause"] = "LLM output has invalid JSON syntax"
        result["recommendation"] = (
            "Check if LLM is outputting valid JSON. The model may have added extra text or formatting."
        )

    return result


def test_content_truncation(content: str, model: str = "qwen3.6-flash") -> dict:
    """
    Test if content length could cause truncation issues.

    Args:
        content: The content to test
        model: Model name for token limit lookup

    Returns:
        dict with keys: content_length, estimated_tokens, max_tokens_for_model, likely_truncated
    """
    model_limits = {
        "qwen3.6-flash": 16384,
        "qwen3.6-bablo": 32768,
        "qwen3.6-plus": 16384,
        "qwen3.6-latest": 32768,
        "qwen-max": 8192,
        "qwen-plus": 8192,
        "gpt-4": 8192,
        "gpt-4o": 16384,
        "gpt-3.5-turbo": 16384,
    }

    estimated_tokens = len(content) // 4
    max_tokens = model_limits.get(model, 16384)

    return {
        "content_length": len(content),
        "estimated_tokens": estimated_tokens,
        "max_tokens_for_model": max_tokens,
        "likely_truncated": estimated_tokens > max_tokens
    }
