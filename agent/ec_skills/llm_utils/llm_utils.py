# Standard library imports
import asyncio
import base64
import json
import re
import sys
import time
import uuid
from threading import Thread
from typing import Any, Dict, Tuple

# Third-party library imports
import requests
from langchain_community.chat_models import ChatAnthropic
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_qwq import ChatQwQ
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
from agent.ec_skill import *
from agent.ec_skills.dev_defs import BreakpointManager
from agent.memory.models import MemoryItem
from utils.env.secure_store import secure_store, get_current_username
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger


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


def prep_multi_modal_content(state, runtime):
    try:
        attachments = state.get("attachments", [])
        user_content = []
        logger.debug(f"node running: {runtime}")
        user_input = state.get("input", "")
        logger.debug(f"LLM input text: {user_input}")
        # Add user text
        user_content.append({"type": "text", "text": user_input})

        # Add all attachments in supported format
        for att in attachments:
            fname = att["filename"].lower()

            mime_type = att.get("mime_type", "").lower()
            logger.debug(f"Processing file: {fname} (MIME: {mime_type})")

            # Skip if no file data
            if not att.get("file_data"):
                logger.debug(f"Skipping empty file: {fname}")
                continue

            data = att["file_data"]

            # file_text = extract_file_text(data, fname)

            # Handle image files (PNG, JPG, etc.)
            if mime_type.startswith('image/'):
                logger.debug(f"Processing image file: {fname}")
                file_data = data if isinstance(data, str) else base64.b64encode(data).decode('utf-8')
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{file_data}"
                        # "detail": "auto"
                    }
                })

            # Handle PDF files
            elif mime_type == 'application/pdf':
                logger.debug(f"Processing PDF file: {fname}")
                # For PDFs, we'll just note its existence since we can't process it directly
                user_content.append({
                    "type": "text",
                    "text": f"[PDF file: {fname} - PDF content cannot be processed directly]"
                })

            # Handle audio files
            elif mime_type.startswith('audio/'):
                logger.debug(f"Processing audio file: {fname}")
                # For audio files, we'll just note its existence
                user_content.append({
                    "type": "text",
                    "text": f"[Audio file: {fname} - Audio content cannot be processed directly]"
                })

            # Handle other file types
            else:
                logger.warning(f"Unsupported file type: {fname} ({mime_type})")
                # user_content.append({
                #     "type": "text",
                #     "text": f"[File: {fname} - This file type is not supported for direct analysis]"
                # })

        return user_content

    except Exception as e:
        err_trace = get_traceback(e, "ErrorPrepMultiModalContent")
        logger.debug(err_trace)


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


def extract_provider_config(provider, config_manager=None):
    """
    Extract common configuration from provider (dict or LLMProvider object).
    
    This function provides backward compatibility by accepting both:
    - Legacy dict-based provider configurations
    - New LLMProvider class instances
    
    Args:
        provider: Either a dict or LLMProvider instance
        config_manager: Optional ConfigManager to get user-selected model (overrides provider's default)
    
    Returns:
        Dict with:
            - model_name: The model to use (user-selected or provider default)
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
        
        # Get supports_vision from model config (default True if not found)
        supports_vision = True  # Default to True
        if provider.supported_models:
            for model in provider.supported_models:
                if (model.model_id == model_name or 
                    model.name == model_name or
                    model.display_name == model_name):
                    supports_vision = getattr(model, 'supports_vision', True)
                    break
        
        # Override with user-selected model if available and valid for this provider
        if config_manager and hasattr(config_manager, 'general_settings'):
            user_selected_model = config_manager.general_settings.default_llm_model
            if user_selected_model:
                # Validate that user-selected model belongs to this provider
                is_valid_model = False
                selected_model_config = None
                if provider.supported_models:
                    # Check if model_id or name matches
                    for model in provider.supported_models:
                        if (user_selected_model == model.model_id or 
                            user_selected_model == model.name or
                            user_selected_model == model.display_name):
                            is_valid_model = True
                            selected_model_config = model
                            break
                
                if is_valid_model:
                    logger.debug(f"[extract_provider_config] Using user-selected model: {user_selected_model} (instead of {model_name})")
                    model_name = user_selected_model
                    # Update supports_vision from selected model
                    if selected_model_config:
                        supports_vision = getattr(selected_model_config, 'supports_vision', True)
                else:
                    # Use the original provider default model, not preferred_model (which may be from wrong provider)
                    model_name = original_provider_model
                    logger.warning(
                        f"[extract_provider_config] User-selected model '{user_selected_model}' "
                        f"does not belong to provider '{provider.name}'. Using provider's default model '{model_name}' instead."
                    )
        
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
    selected_model_config = None
    
    # Override with user-selected model if available and valid for this provider (for dict-based providers)
    if config_manager and hasattr(config_manager, 'general_settings'):
        user_selected_model = config_manager.general_settings.default_llm_model
        if user_selected_model:
            # Validate that user-selected model belongs to this provider
            is_valid_model = False
            if supported_models:
                # Check if model_id or name matches
                for model in supported_models:
                    model_id = model.get('model_id', '')
                    model_name_key = model.get('name', '')
                    display_name = model.get('display_name', '')
                    if (user_selected_model == model_id or 
                        user_selected_model == model_name_key or
                        user_selected_model == display_name):
                        is_valid_model = True
                        selected_model_config = model
                        break
            
            if is_valid_model:
                logger.debug(f"[extract_provider_config] Using user-selected model: {user_selected_model} (instead of {model_name})")
                model_name = user_selected_model
            else:
                # Use the original provider default model, not preferred_model (which may be from wrong provider)
                model_name = original_provider_model
                logger.warning(
                    f"[extract_provider_config] User-selected model '{user_selected_model}' "
                    f"does not belong to provider '{provider_name}'. Using provider's default model '{model_name}' instead."
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
        elif 'anthropic' in provider_name or 'claude' in provider_name or 'chatanthropic' == class_name:
            provider_type = 'anthropic'
        elif 'azure' in provider_name or 'azureopenai' == class_name:
            provider_type = 'azure_openai'
        else:
            # Default to provider_name if still empty
            provider_type = provider_name
    
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
        
        # Helper to get API key from secure store with user isolation (no env fallback)
        def get_api_key(env_var):
            try:
                # Get current username for user isolation
                username = get_current_username()
                return secure_store.get(env_var, username=username)
            except Exception:
                return None
        
        # Check for Azure OpenAI (specific class_name match - must be before OpenAI check)
        if class_name == 'azureopenai' or ('azure' in provider_name.lower() and 'openai' in provider_name.lower()):
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
        
        # Check for DeepSeek
        elif 'deepseek' in provider_name.lower() or 'chatdeepseek' == class_name:
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
        elif 'qwen' in provider_name.lower() or 'qwq' in provider_name.lower() or 'chatqwq' == class_name:
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
            logger.debug(f"[DashScope] Creating ChatQwQ with base_url={base_url}")
            
            # Create no-proxy httpx clients (thread-safe, doesn't modify global env vars)
            # Optimization: Only creates if proxy is configured
            sync_client, async_client = _create_no_proxy_http_client()
            
            if sync_client or async_client:
                logger.debug(f"[DashScope] Using no-proxy httpx clients (Alibaba Cloud security policy)")
                
                # ChatQwQ inherits from ChatOpenAI, which supports both http_client and http_async_client
                llm_instance = ChatQwQ(
                    model=model_name,
                    api_key=dashscope_api_key,
                    base_url=base_url,
                    temperature=0,
                    http_client=sync_client,  # Use custom SYNC client that bypasses proxy (for llm.invoke())
                    http_async_client=async_client  # Use custom ASYNC client that bypasses proxy (for llm.ainvoke())
                )
                
                return llm_instance
            else:
                # No proxy configured - use default clients (more efficient)
                logger.debug(f"[DashScope] Using default httpx clients (no proxy configured)")
                return ChatQwQ(
                    model=model_name,
                    api_key=dashscope_api_key,
                    base_url=base_url,
                    temperature=0
                )
        
        # Check for OpenAI (must be after Azure check)
        elif 'chatanthropic' != class_name and ('openai' in provider_name.lower() or 'chatopenai' == class_name):
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
        
        # Check for Anthropic Claude
        elif 'claude' in provider_name.lower() or 'anthropic' in provider_name.lower() or 'chatanthropic' == class_name:
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
        
        # Check for Baidu Qianfan - use OpenAI-compatible V2 API
        elif 'baidu' in provider_name.lower() or 'qianfan' in provider_name.lower() or 'chatbaiduqianfan' == class_name:
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
        elif 'bytedance' in provider_name.lower() or 'doubao' in provider_name.lower() or 'chatdoubao' == class_name:
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
        
        # Check for Ollama
        elif 'ollama' in provider_name.lower() or 'chatollama' == class_name:
            model_name = model_name or 'llama3.2'
            # Ollama local endpoint
            base_url = base_url or 'http://localhost:11434'
            return ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=0
            )
        
        else:
            logger.warning(f"Unknown provider type: {provider_name} (class_name: {class_name}, provider: {provider_type})")
            return None
            
    except Exception as e:
        logger.error(f"Error creating LLM instance for {provider.get('name')}: {e}")
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
        'qwen', 
        'qwq'
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
        'qwen',
        'qwq'
    ]


def _create_and_validate_browser_use_llm(bu_config: dict):
    """
    Create and validate a BrowserUseChatOpenAI instance.
    
    This helper function ensures that only BrowserUseChatOpenAI instances are returned,
    preventing incompatible LLM types from being passed to browser_use.
    
    Args:
        bu_config: Configuration dict for BrowserUseChatOpenAI (model, api_key, base_url, etc.)
        
    Returns:
        BrowserUseChatOpenAI instance or None if creation/validation fails
    """
    try:
        from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
        
        # Create the instance
        llm_instance = BrowserUseChatOpenAI(**bu_config)
        
        # Validate it's actually BrowserUseChatOpenAI (should always be true if creation succeeded)
        if isinstance(llm_instance, BrowserUseChatOpenAI):
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
    
    # Check compatibility
    is_compatible = is_provider_browser_use_compatible(provider_type)
    logger.debug(
        f"[create_browser_use_llm_by_provider_type] Provider: {provider_type}, "
        f"Model: {model_name}, Compatible: {is_compatible}"
    )
    
    # OpenAI or Azure OpenAI
    if provider_type in ['openai', 'azure_openai'] or 'openai' in class_name:
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key']
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        logger.info(
            f"[create_browser_use_llm_by_provider_type] Creating BrowserUseChatOpenAI "
            f"for {provider_type}, model: {bu_config['model']}"
        )
        return _create_and_validate_browser_use_llm(bu_config)
    
    # OpenAI-compatible providers (DeepSeek, DashScope, Ollama, Qwen, Baidu Qianfan, Bytedance, etc.)
    elif provider_type in ['deepseek', 'dashscope', 'ollama', 'qwen', 'qwq', 'baidu_qianfan', 'bytedance']:
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key'] or 'dummy-key'
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        logger.info(
            f"[create_browser_use_llm_by_provider_type] Creating BrowserUseChatOpenAI "
            f"for {provider_type} (OpenAI-compatible), model: {bu_config['model']}"
        )
        
        # Check if this is a domestic API that needs proxy bypass
        # Domestic APIs (DashScope, DeepSeek, Baidu Qianfan, Bytedance) may have proxy restrictions
        # Optimization: Only creates no-proxy clients if proxy is actually configured
        domestic_apis_need_direct = ['dashscope', 'qwen', 'qwq', 'deepseek', 'baidu_qianfan', 'bytedance']
        
        if provider_type in domestic_apis_need_direct:
            # Create no-proxy httpx clients (sync + async, thread-safe, doesn't modify global env vars)
            # Optimization: Only creates if proxy is configured
            # Note: BrowserUseChatOpenAI only supports http_client (sync), not http_async_client
            # For async calls, it will use default async client or create new one, which should be fine
            sync_client, async_client = _create_no_proxy_http_client()
            
            if sync_client:
                # Proxy is configured - use no-proxy sync client (bypass proxy for domestic APIs)
                logger.debug(
                    f"[create_browser_use_llm_by_provider_type] Using no-proxy clients for {provider_type} "
                    f"(proxy detected, bypassing for domestic API)"
                )
                # BrowserUseChatOpenAI only supports http_client parameter (not http_async_client)
                bu_config['http_client'] = sync_client
                return _create_and_validate_browser_use_llm(bu_config)
            else:
                # No proxy configured - use default clients (more efficient, direct connection)
                logger.debug(
                    f"[create_browser_use_llm_by_provider_type] No proxy configured for {provider_type}, "
                    f"using default clients (direct connection)"
                )
                return _create_and_validate_browser_use_llm(bu_config)
        else:
            # Ollama, etc. - use default clients (respects system proxy if configured)
            return _create_and_validate_browser_use_llm(bu_config)
    
    # Non-OpenAI-compatible providers (Anthropic, Google, Bedrock)
    # Try to create BrowserUseChatOpenAI with provider's data, fallback if fails
    elif provider_type in ['anthropic', 'google', 'bedrock']:
        logger.warning(
            f"[create_browser_use_llm_by_provider_type] Provider '{provider_type}' is not natively "
            f"supported by browser_use, attempting workaround"
        )
        
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key']
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        llm_instance = _create_and_validate_browser_use_llm(bu_config)
        if llm_instance is not None:
            logger.info(
                f"[create_browser_use_llm_by_provider_type] Successfully created BrowserUseChatOpenAI "
                f"for {provider_type} using workaround, model: {bu_config['model']}"
            )
            return llm_instance
        else:
            logger.error(
                f"[create_browser_use_llm_by_provider_type] Failed to create BrowserUseChatOpenAI "
                f"for {provider_type}"
            )
            return None
    
    # Unknown provider - try OpenAI-compatible mode
    else:
        logger.warning(
            f"[create_browser_use_llm_by_provider_type] Unknown provider '{provider_type}', "
            f"attempting OpenAI-compatible mode"
        )
        
        bu_config = {
            'model': model_name or default_config['model'],
            'api_key': api_key or default_config['api_key']
        }
        if base_url:
            bu_config['base_url'] = base_url
        
        llm_instance = _create_and_validate_browser_use_llm(bu_config)
        if llm_instance is not None:
            logger.info(
                f"[create_browser_use_llm_by_provider_type] Successfully created BrowserUseChatOpenAI "
                f"for {provider_type} (OpenAI-compatible mode), model: {bu_config['model']}"
            )
            return llm_instance
        else:
            logger.error(
                f"[create_browser_use_llm_by_provider_type] Failed to create BrowserUseChatOpenAI "
                f"for {provider_type}"
            )
            return None


def get_use_vision_from_llm(llm, context="") -> bool:
    """
    Get use_vision value from LLM object, defaulting to True if not found.
    
    Args:
        llm: LLM instance that may have supports_vision attribute
        context: Optional context string for logging (e.g., "EC_Agent", "build_node")
    
    Returns:
        bool: use_vision value (True by default)
    """
    if llm and hasattr(llm, 'supports_vision'):
        use_vision = llm.supports_vision
        if context:
            logger.debug(f"[{context}] Auto-set use_vision={use_vision} from LLM config")
        return use_vision
    else:
        # Default to True if not found (browser-use default behavior)
        if context:
            logger.debug(f"[{context}] Auto-set use_vision=True (default, no config found)")
        return True


def create_browser_use_llm(mainwin=None, fallback_llm=None, skip_playwright_check=False):
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
                default_llm_name = config_manager.general_settings.default_llm
                
                if not default_llm_name:
                    logger.error("[create_browser_use_llm] default_llm is empty - this should not happen")
                    return None
                
                # Use get_provider() to get the specific provider dict
                provider_dict = config_manager.llm_manager.get_provider(default_llm_name)
                
                if not provider_dict:
                    logger.error(f"[create_browser_use_llm] Default LLM '{default_llm_name}' not found in providers")
                    return None
                
                # Use shared extract_provider_config to get configuration
                # Pass config_manager to automatically use user-selected model
                config = extract_provider_config(provider_dict, config_manager=config_manager)
                
                provider_type = config['provider_type']
                model_name = config['model_name']  # Already includes user-selected model from extract_provider_config
                api_key = config.get('api_key')  # May be None if not configured
                base_url = config.get('base_url')
                class_name = config.get('class_name', '')
                
                # Use dummy API key if no API key is available (for initialization purposes)
                # This allows browser_use to initialize even without API key
                if not api_key:
                    logger.debug(
                        f"[create_browser_use_llm] No API key for provider '{default_llm_name}', "
                        f"using placeholder key for initialization (this is expected on first use)"
                    )
                    api_key = 'sk-placeholder-key-for-first-time-setup'
                
                logger.info(
                    f"[create_browser_use_llm] Using default LLM: "
                    f"provider={config.get('provider_display', default_llm_name)}, model={model_name}"
                )
                
                # Get supports_vision from config (default True if not found)
                supports_vision = config.get('supports_vision', True)
                
                # Use centralized function (already validates BrowserUseChatOpenAI type)
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
                    logger.error(
                        f"[create_browser_use_llm] Type check failed: expected BrowserUseChatOpenAI, "
                        f"got {type(llm_instance).__name__}, returning None"
                    )
                    return None
                
                # Attach supports_vision to LLM instance for later use
                if llm_instance is not None:
                    llm_instance.supports_vision = supports_vision
                    logger.debug(f"[create_browser_use_llm] Model {model_name} supports_vision: {supports_vision}")
                
                return llm_instance
                        
            except Exception as e:
                logger.error(
                    f"[create_browser_use_llm] Exception getting LLM config from mainwin: {e}"
                )
                import traceback
                logger.debug(f"[create_browser_use_llm] Exception details: {traceback.format_exc()}")
                return None
        else:
            if not mainwin:
                logger.error("[create_browser_use_llm] No mainwin provided - cannot create LLM without mainwin configuration")
            else:
                logger.error("[create_browser_use_llm] mainwin has no config_manager - cannot create LLM")
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

def get_standard_prompt(state:NodeState) -> NodeState:
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
    logger.debug(f"found chat: {this_chat['data']['id']}")

    # Check if chat exists and has data
    if not this_chat.get("success") or this_chat.get("data") is None:
        logger.error(f"Chat not found or has no data: {chat_id}, error: {this_chat.get('error')}")
        return None

    members = this_chat["data"].get("members", [])
    logger.debug(f"chat members: {members}")
    logger.debug(f"me id: {self_agent.card.id}")
    # for now, let's just assume 1-1 chat, find first chat member not myself.
    oppsite_member = next((ag for ag in members if ag["userId"] != self_agent.card.id), None)
    if oppsite_member:
        opposite_side = get_agent_by_id(oppsite_member["userId"])
        logger.debug(f"found opposite side agent: {opposite_side.card.name}")
    else:
        logger.error("No chat mate found for chat:", chat_id)
        opposite_side = None
    return opposite_side

def send_response_back(state: NodeState) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin

        logger.debug(f"standard_post_llm_hook send_response_back: {state}")
        
        # CRITICAL FIX: Use chatId from attributes.params if available, otherwise fallback to messages[1]
        # When a chat is deleted and recreated, attributes.params.chatId has the new chatId,
        # but messages[1] still has the old deleted chatId
        chat_id = None
        chat_id_source = None
        try:
            # Try multiple locations to get the most up-to-date chatId
            params = state.get("attributes", {}).get("params", {})
            
            # Check if params is a TaskSendParams object with metadata
            if hasattr(params, 'metadata') and isinstance(params.metadata, dict):
                metadata_params = params.metadata.get("params", {})
                if isinstance(metadata_params, dict):
                    chat_id = metadata_params.get("chatId")
                    if chat_id:
                        chat_id_source = "params.metadata.params"
            
            # If not found, try direct params dict access
            if not chat_id and isinstance(params, dict):
                chat_id = params.get("chatId")
                if chat_id:
                    chat_id_source = "params"
            
            # If still not found, fallback to messages[1]
            if not chat_id and isinstance(state.get("messages"), list) and len(state["messages"]) > 1:
                chat_id = state["messages"][1]
                chat_id_source = "messages[1]"
                
            if chat_id:
                logger.info(f"[send_response_back] Using chatId: {chat_id} (from {chat_id_source})")
            else:
                logger.error("[send_response_back] No chatId found in any location")
        except Exception as e:
            logger.error(f"[send_response_back] Error extracting chatId: {e}, falling back to messages[1]")
            chat_id = state.get("messages", [None])[1] if len(state.get("messages", [])) > 1 else None
            chat_id_source = "messages[1] (fallback)"
        
        if not chat_id:
            logger.error("[send_response_back] No chatId found in state")
            return state
            
        opposite_agent = find_opposite_agent(self_agent, chat_id)
        
        # If chat not found, log error and skip response
        if opposite_agent is None:
            logger.error(f"Cannot send response: chat {chat_id} not found or has no opposite agent")
            return state
            
        msg_type = "text"
        qa_form = state["metadata"].get("qa_form", {})
        notification = state["metadata"].get("notification", {})
        if qa_form :
            msg_type = "form"
        elif notification:
            msg_type = "notification"

        if state["attributes"].get("i_tag", ""):
            i_tag = state["attributes"].get("i_tag", "")
        else:
            if isinstance(state["attributes"].get("params"), dict):
                i_tag = state["attributes"].get("params", {}).get("i_tag", "")
            else:
                i_tag = ""

        msg_id = str(uuid.uuid4())
        # send self a message to trigger the real component search work-flow

        # The goal here is facilitate fomulating the message to be as close to this format as possible:
        # frontend_message = {
        #                 "content": {
        #                     "type": dtype,
        #                     "text": state["messages"][-1],
        #                     "card": card,
        #                     "i_tag": i_tag,
        #                     "code": code,
        #                     "form": form,
        #                     "notification": notification,
        #                 },
        #                 "role": role,
        #                 "senderId": senderId,
        #                 "createAt": createAt,
        #                 "senderName": senderName,
        #                 "status": status,
        #                 "ext": ext,
        #             }
        # as this is the format the GUI will take and display.
        print("state result:",state["result"])
        if isinstance(state["result"], str):
            next_msg = state["messages"][-1]
        else:
            if isinstance(state["result"], dict):
                llm_result = state["result"].get("llm_result", {})
                if isinstance(llm_result, str):
                    next_msg = llm_result
                else:
                    next_msg = state["result"].get("llm_result", {}).get("next_prompt", "")
            else:
                next_msg = "sorry, I was lost, could you rephrase your question?"

        agent_response_message = {
            "id": str(uuid.uuid4()),
            "attributes": {
                "params": {
                    "content": {
                        "type": msg_type, # "text", "code", "form", "notification", "card
                        "text": next_msg,
                        "i_tag": i_tag,
                        "dtype": msg_type,
                        "card": {},
                        "code": {},
                        "form": qa_form,
                        "notification": notification,
                    },
                    "attachments": state["attachments"],
                    "role": "",
                    "chatId": f"{chat_id}",
                    "senderId": f"{agent_id}",
                    "i_tag": i_tag,
                    "createAt": int(time.time() * 1000),
                    "senderName": f"{self_agent.card.name}",
                    "status": "success",
                    "ext": "",
                    "human": False
                }
            }
        }
        logger.debug(f"sending response msg back to twin: {agent_response_message}")
        send_result = self_agent.a2a_send_chat_message(opposite_agent, agent_response_message)
        # state.result = result
        return send_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.debug(err_trace)
        return err_trace


def run_async_in_sync(awaitable):
    """Run an async awaitable from sync code with safe event loop lifecycle and cleanup."""
    # Event loop policy is handled at the application level (main.py)
    # Trust that the correct policy is already set for the main process

    loop = asyncio.new_event_loop()
    try:
        # Ensure the newly created loop is current in this thread
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(awaitable)
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


def run_async_in_worker_thread(awaitable_or_factory):
    """Run an async awaitable in a dedicated worker thread with its own Selector event loop.

    Accepts either:
    - a zero-arg callable that returns a coroutine (preferred), or
    - a coroutine object (will still work, but may be created on the caller thread).

    Use a factory when possible so the coroutine is created inside the worker thread,
    ensuring no binding to a GUI/qasync loop on Windows.
    """
    result_holder = {}
    error_holder = {}

    def _worker():
        # On Windows, check current policy and set ProactorEventLoop for subprocess support in worker thread
        if sys.platform.startswith("win"):
            try:
                current_policy = asyncio.get_event_loop_policy()
                # In worker thread, we may need ProactorEventLoop for subprocess support
                if hasattr(asyncio, "WindowsProactorEventLoopPolicy") and \
                   not isinstance(current_policy, asyncio.WindowsProactorEventLoopPolicy):
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass

        # Create loop using current policy (Proactor on Windows)
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
            logger.debug(f"[run_async_in_worker_thread] thread={__import__('threading').current_thread().name}, policy={type(asyncio.get_event_loop_policy()).__name__}, loop={type(loop).__name__}")
            # Create the coroutine inside the worker thread if a factory is provided
            if callable(awaitable_or_factory):
                coro = awaitable_or_factory()
            else:
                coro = awaitable_or_factory
            res = loop.run_until_complete(coro)
            result_holder["result"] = res
        except Exception as e:
            error_holder["error"] = e
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

    t = Thread(target=_worker, name="playwright-worker", daemon=True)
    t.start()
    t.join()

    if "error" in error_holder:
        raise error_holder["error"]
    return result_holder.get("result")


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


def get_recent_context(history: list, max_tokens: int = CONTEXT_WINDOW_SIZE) -> list:
    """
    Returns a subset of chat history that fits within the token limit.

    Strategy:
    1. Always include the most recent SystemMessage (if exists) for context
    2. Include as many recent messages as possible within the token limit
    3. Estimate ~4 characters per token (conservative estimate)

    Args:
        history: List of LangChain message objects (SystemMessage, HumanMessage, AIMessage)
        max_tokens: Maximum number of tokens to include

    Returns:
        List of messages that fit within the token limit
    """
    if not history or not isinstance(history, list):
        return []

    from langchain_core.messages import SystemMessage

    # Simple token estimation: ~4 chars per token (conservative)
    def estimate_tokens(msg) -> int:
        try:
            content = msg.content if hasattr(msg, 'content') else str(msg)
            return len(str(content)) // 4
        except Exception:
            return 0

    # Find the most recent SystemMessage
    system_msg = None
    system_msg_idx = -1
    for idx in range(len(history) - 1, -1, -1):
        if isinstance(history[idx], SystemMessage):
            system_msg = history[idx]
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
    for idx in range(len(history) - 1, -1, -1):
        if idx == system_msg_idx:
            continue  # Already added

        msg = history[idx]
            
        msg_tokens = estimate_tokens(msg)

        if token_count + msg_tokens > max_tokens:
            break  # Would exceed limit

        result.insert(1 if system_msg else 0, msg)  # Insert after system message
        token_count += msg_tokens

    logger.debug(f"Context window: {len(result)} messages, ~{token_count} tokens (limit: {max_tokens})")
    return result
