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
from langgraph.types import Interrupt
from agent.ec_skills.dev_defs import BreakpointManager


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
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatAnthropic, ChatOllama
from langchain_deepseek import ChatDeepSeek
from langchain_qwq import ChatQwQ


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
                    logger.info(f"Successfully created LLM instance using default provider: {default_llm}")
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
            logger.info(f"Successfully created LLM instance and updated default to: {selected_provider['name']}")
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
    regional_preferences = {
        'CN': ['deepseek', 'qwen', 'openai', 'claude'],  # China prefers local providers
        'US': ['openai', 'claude', 'deepseek', 'qwen'],  # US prefers US providers
        'default': ['openai', 'claude', 'qwen', 'deepseek']  # Default order
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
    try:
        provider_name = provider.get('name', '').lower()
        supported_models = provider.get('supported_models', [])
        preferred_model = provider.get('preferred_model')
        default_model_name = provider.get('default_model')
        
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
        
        logger.info(f"Creating LLM instance for {provider_name} with model: {model_name}")
        
        if 'deepseek' in provider_name:
            model_name = model_name or 'deepseek-chat'
            return ChatDeepSeek(model=model_name, temperature=0)
            
        elif 'qwen' in provider_name or 'qwq' in provider_name:
            model_name = model_name or 'qwq-plus'
            return ChatQwQ(model=model_name, temperature=0)
            
        elif 'openai' in provider_name:
            model_name = model_name or 'gpt-4o'
            return ChatOpenAI(model=model_name, temperature=0)
            
        elif 'claude' in provider_name or 'anthropic' in provider_name:
            model_name = model_name or 'claude-3-5-sonnet-20241022'
            return ChatAnthropic(model=model_name, temperature=0)
            
        elif 'ollama' in provider_name:
            model_name = model_name or 'llama3.2'
            return ChatOllama(model=model_name, temperature=0)
            
        else:
            logger.warning(f"Unknown provider type: {provider_name}")
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
    logger.warning("Using fallback LLM selection - API keys may not be configured")
    
    try:
        if country == "CN":
            logger.info("Fallback: Using DeepSeek for China")
            return ChatDeepSeek(model="deepseek-chat", temperature=0)
        elif country == "US":
            logger.info("Fallback: Using OpenAI for US")
            return ChatOpenAI(model="gpt-4o", temperature=0)
        else:
            logger.info("Fallback: Using OpenAI as default")
            return ChatOpenAI(model="gpt-4o", temperature=0)
    except Exception as e:
        logger.error(f"Fallback LLM creation failed: {e}")
        return None



def get_standard_prompt(state:NodeState) -> NodeState:
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



def send_response_back(state: NodeState) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        print("standard_post_llm_hook send_response_back:", state)
        chat_id = state["messages"][1]
        msg_type = "text"
        msg_id = str(uuid.uuid4()),
        # send self a message to trigger the real component search work-flow

        # The goal here is facilitate fomulating the message to be as close to this format as possible:
        # frontend_message = {
        #                 "content": {
        #                     "type": dtype,
        #                     "text": state["messages"][-1],
        #                     "card": card,
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
                        "text": state["result"]["llm_result"]["casual_chat_response"],
                        "dtype": msg_type,
                        "card": {},
                        "code": {},
                        "form": {},
                        "notification": {},
                    },
                    "attachments": state["attachments"],
                    "role": "",
                    "chatId": f"{chat_id}",
                    "senderId": f"{agent_id}",
                    "createAt": int(time.time() * 1000),
                    "senderName": f"{self_agent.card.name}",
                    "status": "success",
                    "ext": "",
                    "human": False
                }
            }
        }
        print("sending response msg back to twin:", agent_response_message)
        send_result = self_agent.a2a_send_chat_message(twin_agent, agent_response_message)
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
