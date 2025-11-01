import re
import time
import random
from selenium.webdriver.support.expected_conditions import element_selection_state_to_be

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.ec_skill import *
import json
import base64
import asyncio
import sys
from threading import Thread
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from agent.ec_skills.dev_defs import BreakpointManager
from agent.memory.models import MemoryItem


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
        print("node running:", runtime)
        user_input = state.get("input", "")
        print("LLM input text:", user_input)
        # Add user text
        user_content.append({"type": "text", "text": user_input})

        # Add all attachments in supported format
        for att in attachments:
            fname = att["filename"].lower()

            mime_type = att.get("mime_type", "").lower()
            print(f"Processing file: {fname} (MIME: {mime_type})")

            # Skip if no file data
            if not att.get("file_data"):
                print(f"Skipping empty file: {fname}")
                continue

            data = att["file_data"]

            # file_text = extract_file_text(data, fname)

            # Handle image files (PNG, JPG, etc.)
            if mime_type.startswith('image/'):
                print(f"Processing image file: {fname}")
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
                print(f"Processing PDF file: {fname}")
                # For PDFs, we'll just note its existence since we can't process it directly
                user_content.append({
                    "type": "text",
                    "text": f"[PDF file: {fname} - PDF content cannot be processed directly]"
                })

            # Handle audio files
            elif mime_type.startswith('audio/'):
                print(f"Processing audio file: {fname}")
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



import requests
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_community.chat_models import ChatAnthropic, ChatOllama
from langchain_deepseek import ChatDeepSeek
from langchain_qwq import ChatQwQ

# Import optional providers that may not be available
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_aws import ChatBedrock
except ImportError:
    ChatBedrock = None


def get_country_by_ip() -> str | None:
    """Return country code of current public IP, e.g., 'CN' for China."""
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            logger.debug(f"This host IP lookup result: {resp.json()}")
            return resp.json().get("country")
    except Exception as e:
        print(f"IP lookup failed: {e}")
    return None


def pick_llm(default_llm, llm_providers, config_manager=None):
    """
    Return appropriate LLM instance with intelligent provider selection.

    Logic:
    1. Check if default_llm is configured and has valid API key
    2. If not, select available provider by region (CN: DeepSeek/Qwen, US: OpenAI/Claude)
    3. Update default_llm setting if a new provider is selected
    4. Fallback to hardcoded defaults if no providers are available

    Args:
        default_llm: Current default LLM provider name
        llm_providers: List of available LLM providers with configuration
        config_manager: Configuration manager instance (optional)

    Returns:
        LLM instance or None if all attempts fail
    """
    from app_context import AppContext
    
    logger.info(f"Starting LLM selection process. Default LLM: {default_llm}")
    logger.debug(f"Available providers: {[p.get('name') for p in llm_providers]}")
    
    # Step 1: Try to use the default LLM if configured
    if default_llm:
        logger.info(f"Checking default LLM provider: {default_llm}")
        default_provider = _find_provider_by_name(default_llm, llm_providers)
        
        if default_provider:
            logger.info(f"Found default provider: {default_provider.get('name')}")
            if default_provider.get('api_key_configured', False):
                logger.info(f"Default LLM provider {default_llm} is configured and has API key")
                llm_instance = _create_llm_instance(default_provider)
                if llm_instance:
                    provider_display = default_provider.get('display_name', default_llm)
                    model_name = default_provider.get('default_model', 'default')
                    llm_type = type(llm_instance).__name__
                    
                    # Verify the LLM instance is correct
                    logger.info(f"✅ Successfully created LLM instance - Provider: {provider_display} ({default_llm}), Model: {model_name}, Type: {llm_type}")
                    
                    # Test that the instance has required attributes
                    if hasattr(llm_instance, 'model'):
                        logger.debug(f"   LLM instance verified: model={getattr(llm_instance, 'model', 'N/A')}")
                    
                    return llm_instance
                else:
                    logger.warning(f"Failed to create LLM instance for {default_llm}, trying alternatives")
            else:
                logger.warning(f"Default LLM provider {default_llm} found but API key not configured")
        else:
            logger.warning(f"Default LLM provider {default_llm} not found in available providers")
    
    # Step 2: Select available provider by region
    country = get_country_by_ip()
    logger.info(f"Detected country: {country}, selecting regional provider")
    
    selected_provider = _select_regional_provider(country, llm_providers)
    
    if selected_provider:
        logger.info(f"Selected regional provider: {selected_provider['name']}")
        llm_instance = _create_llm_instance(selected_provider)
        
        if llm_instance:
            # Update default_llm setting through LLM manager
            _update_default_llm_via_config_manager(selected_provider['name'], config_manager)
            provider_display = selected_provider.get('display_name', selected_provider['name'])
            model_name = selected_provider.get('default_model', 'default')
            logger.info(f"✅ Successfully created LLM instance and updated default - Provider: {provider_display} ({selected_provider['name']}), Model: {model_name}, Type: {type(llm_instance).__name__}")
            return llm_instance
        else:
            logger.error(f"Failed to create LLM instance for selected provider: {selected_provider['name']}")
    
    # Step 3: Fallback to hardcoded defaults
    logger.warning("No configured providers available, falling back to hardcoded defaults")
    return _fallback_llm_selection(country)


def _find_provider_by_name(provider_name, llm_providers):
    """Find provider by name in the providers list"""
    if not provider_name:
        return None
        
    provider_name_lower = provider_name.lower()
    
    # First try exact match
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


def _select_regional_provider(country, llm_providers):
    """Select best available provider based on region"""
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
        'ollama'         # Local deployment
    ]
    
    regional_preferences = {
        'CN': [
            'deepseek',      # Chinese provider, accessible in CN
            'qwen',          # Chinese provider (Alibaba), accessible in CN
            'qwq',           # Chinese provider (Alibaba DashScope), accessible in CN
            'azure',         # Azure OpenAI (if configured), may be accessible depending on region
            'bedrock',       # AWS Bedrock (if configured), may be accessible depending on region
            'ollama'         # Local deployment, accessible anywhere
            # Excluded: 'openai', 'claude', 'anthropic', 'google', 'gemini' (not accessible in CN)
        ],
        'US': us_preferences,
        'default': us_preferences  # Same as US
    }
    
    preferences = regional_preferences.get(country, regional_preferences['default'])
    logger.debug(f"Regional preferences for {country}: {preferences}")
    
    # Find first available provider with API key
    for preferred_name in preferences:
        logger.debug(f"Looking for provider matching: {preferred_name}")
        for provider in llm_providers:
            provider_name = provider.get('name', '').lower()
            api_key_configured = provider.get('api_key_configured', False)
            logger.debug(f"Checking provider: {provider.get('name')}, API key configured: {api_key_configured}")
            
            if (preferred_name.lower() in provider_name and api_key_configured):
                logger.info(f"Found matching provider: {provider.get('name')} for preference: {preferred_name}")
                return provider
    
    # If no preferred providers found, try any available provider with API key
    logger.debug("No preferred providers found, trying any available provider with API key")
    for provider in llm_providers:
        if provider.get('api_key_configured', False):
            logger.info(f"Found available provider with API key: {provider.get('name')}")
            return provider
    
    logger.warning("No providers found with configured API keys")
    return None


def _create_llm_instance(provider):
    """Create LLM instance based on provider configuration"""
    import os
    
    try:
        provider_name = provider.get('name', '').lower()
        supported_models = provider.get('supported_models', [])
        preferred_model = provider.get('preferred_model')
        default_model_name = provider.get('default_model')
        api_key_env_vars = provider.get('api_key_env_vars', [])
        
        # Determine which model to use
        model_name = None
        if preferred_model:
            model_name = preferred_model
        elif default_model_name:
            model_name = default_model_name
        elif supported_models:
            # Use the first supported model's model_id
            first_model = supported_models[0]
            model_name = first_model.get('model_id', first_model.get('name'))
        
        provider_display = provider.get('display_name', provider.get('name', provider_name))
        provider_name_actual = provider.get('name', provider_name)
        logger.info(f"🔄 Creating LLM instance - Provider: {provider_display} ({provider_name_actual}), Model: {model_name}")
        
        # Match provider by class_name or name to support all configured providers
        class_name = provider.get('class_name', '').lower()
        provider_type = provider.get('provider', '').lower()
        
        # Helper function to get API key from environment
        def get_api_key(env_var):
            return os.environ.get(env_var)
        
        # Check for Azure OpenAI (specific class_name match - must be before OpenAI check)
        if class_name == 'azureopenai' or ('azure' in provider_name.lower() and 'openai' in provider_name.lower()):
            model_name = model_name or 'gpt-4'
            # Azure OpenAI requires AZURE_ENDPOINT and AZURE_OPENAI_API_KEY from environment
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
                logger.error(f"Azure OpenAI requires AZURE_ENDPOINT and AZURE_OPENAI_API_KEY environment variables")
                return None
        
        # Check for AWS Bedrock (specific class_name match)
        elif 'chatbedrockconverse' == class_name or 'bedrock' in provider_name.lower():
            if ChatBedrock is None:
                logger.error("ChatBedrock is not available. Install with: pip install langchain-aws")
                return None
            model_name = model_name or 'anthropic.claude-3-sonnet-20240229-v1:0'
            # AWS Bedrock requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
            aws_access_key_id = get_api_key('AWS_ACCESS_KEY_ID')
            aws_secret_access_key = get_api_key('AWS_SECRET_ACCESS_KEY')
            if not aws_access_key_id or not aws_secret_access_key:
                logger.error("AWS Bedrock requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
                return None
            try:
                # ChatBedrock uses boto3 credentials from environment automatically
                # Credentials should be set via AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars
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
            # Google Gemini requires GEMINI_API_KEY
            gemini_api_key = get_api_key('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.error("Google Gemini requires GEMINI_API_KEY environment variable")
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
            # DeepSeek requires DEEPSEEK_API_KEY
            deepseek_api_key = get_api_key('DEEPSEEK_API_KEY')
            if not deepseek_api_key:
                logger.error("DeepSeek requires DEEPSEEK_API_KEY environment variable")
                return None
            
            # Log proxy settings if configured (for debugging)
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']
            active_proxies = {var: os.environ.get(var) for var in proxy_vars if os.environ.get(var)}
            if active_proxies:
                logger.info(f"[DeepSeek] 🌐 Proxy settings detected: {active_proxies}")
            else:
                logger.debug("[DeepSeek] No proxy environment variables detected")
            
            # ChatDeepSeek uses OpenAI-compatible API and should automatically respect
            # HTTP_PROXY/HTTPS_PROXY environment variables (set by system_proxy.py)
            # timeout: Total timeout in seconds (120s = 2 minutes)
            # Note: langchain_deepseek uses httpx/requests under the hood, which automatically
            # reads HTTP_PROXY/HTTPS_PROXY from environment variables
            logger.debug(f"[DeepSeek] 🔧 Creating ChatDeepSeek with timeout=120.0s")
            return ChatDeepSeek(
                model=model_name,
                api_key=deepseek_api_key,
                temperature=0,
                timeout=120.0  # 120 seconds total timeout to handle slow networks/proxies
            )
        
        # Check for Qwen/QwQ
        elif 'qwen' in provider_name.lower() or 'qwq' in provider_name.lower() or 'chatqwq' == class_name:
            model_name = model_name or 'qwq-plus'
            # QwQ/DashScope requires DASHSCOPE_API_KEY
            dashscope_api_key = get_api_key('DASHSCOPE_API_KEY')
            if not dashscope_api_key:
                logger.error("QwQ requires DASHSCOPE_API_KEY environment variable")
                return None
            return ChatQwQ(
                model=model_name,
                api_key=dashscope_api_key,
                temperature=0
            )
        
        # Check for OpenAI (must be after Azure check)
        elif 'chatanthropic' != class_name and ('openai' in provider_name.lower() or 'chatopenai' == class_name):
            model_name = model_name or 'gpt-4o'
            # OpenAI requires OPENAI_API_KEY
            openai_api_key = get_api_key('OPENAI_API_KEY')
            if not openai_api_key:
                logger.error("OpenAI requires OPENAI_API_KEY environment variable")
                return None
            return ChatOpenAI(
                model=model_name,
                api_key=openai_api_key,
                temperature=0
            )
        
        # Check for Anthropic Claude
        elif 'claude' in provider_name.lower() or 'anthropic' in provider_name.lower() or 'chatanthropic' == class_name:
            model_name = model_name or 'claude-3-5-sonnet-20241022'
            # Anthropic requires ANTHROPIC_API_KEY
            anthropic_api_key = get_api_key('ANTHROPIC_API_KEY')
            if not anthropic_api_key:
                logger.error("Anthropic requires ANTHROPIC_API_KEY environment variable")
                return None
            return ChatAnthropic(
                model=model_name,
                api_key=anthropic_api_key,
                temperature=0
            )
        
        # Check for Ollama
        elif 'ollama' in provider_name.lower() or 'chatollama' == class_name:
            model_name = model_name or 'llama3.2'
            return ChatOllama(model=model_name, temperature=0)
        
        else:
            logger.warning(f"Unknown provider type: {provider_name} (class_name: {class_name}, provider: {provider_type})")
            return None
            
    except Exception as e:
        logger.error(f"Error creating LLM instance for {provider.get('name')}: {e}")
        return None


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


def _fallback_llm_selection(country):
    """Fallback LLM selection when no configured providers are available"""
    logger.warning("⚠️ Using fallback LLM selection - API keys may not be configured")
    
    try:
        if country == "CN":
            logger.info("🔄 Fallback: Using DeepSeek for China")
            llm = ChatDeepSeek(model="deepseek-chat", temperature=0)
            logger.info(f"✅ Fallback LLM created - Provider: DeepSeek, Model: deepseek-chat, Type: {type(llm).__name__}")
            return llm
        elif country == "US":
            logger.info("🔄 Fallback: Using OpenAI for US")
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            logger.info(f"✅ Fallback LLM created - Provider: OpenAI, Model: gpt-4o, Type: {type(llm).__name__}")
            return llm
        else:
            logger.info("🔄 Fallback: Using OpenAI as default")
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            logger.info(f"✅ Fallback LLM created - Provider: OpenAI, Model: gpt-4o, Type: {type(llm).__name__}")
            return llm
    except Exception as e:
        logger.error(f"❌ Fallback LLM creation failed: {e}")
        return None

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
    print("found chat:", this_chat)

    # Check if chat exists and has data
    if not this_chat.get("success") or this_chat.get("data") is None:
        logger.error(f"Chat not found or has no data: {chat_id}, error: {this_chat.get('error')}")
        return None

    members = this_chat["data"].get("members", [])
    print("chat members:", members)
    print("me id:", self_agent.card.id)
    # for now, let's just assume 1-1 chat, find first chat member not myself.
    oppsite_member = next((ag for ag in members if ag["userId"] != self_agent.card.id), None)
    if oppsite_member:
        opposite_side = get_agent_by_id(oppsite_member["userId"])
        print("found opposite side agent:", opposite_side.card.name)
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

        print("standard_post_llm_hook send_response_back:", state)
        
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
        agent_response_message = {
            "id": str(uuid.uuid4()),
            "attributes": {
                "params": {
                    "content": {
                        "type": msg_type, # "text", "code", "form", "notification", "card
                        "text": state["result"].get("llm_result", {}).get("next_prompt", ""),
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
        print("sending response msg back to twin:", agent_response_message)
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
            print(f"[run_async_in_worker_thread] thread={__import__('threading').current_thread().name}, policy={type(asyncio.get_event_loop_policy()).__name__}, loop={type(loop).__name__}")
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


from langgraph.types import Interrupt

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
