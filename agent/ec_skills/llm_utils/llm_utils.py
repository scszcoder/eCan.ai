import re
import time

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
from langchain_community.chat_models import ChatAnthropic
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


def pick_llm(settings):
    """Return appropriate LLM instance depending on IP location."""
    country = get_country_by_ip()
    print(f"Detected country: {country}")

    if country == "CN":
        # Prefer DeepSeek, fallback to Qwen
        try:
            if settings.get("cn_llm_provider", False):
                if settings.get("cn_llm_model") == "deepseek":
                    if settings.get("cn_llm_model", False):
                        cn_llm = ChatDeepSeek(model=settings.get("cn_llm_model"), temperature=0)
                    else:
                        cn_llm = ChatDeepSeek(model="deepseek-chat", temperature=0)
                elif settings.get("cn_llm_model") == "qwen":
                    if settings.get("cn_llm_model", False):
                        cn_llm = ChatQwQ(model=settings.get("cn_llm_model"), temperature=0)
                    else:
                        cn_llm = ChatQwQ(model="qwq-plus", temperature=0)
            else:
                cn_llm = ChatDeepSeek(model="deepseek-chat", temperature=0)
            return cn_llm
        except Exception:
            cn_llm = None
            return cn_llm
    elif country == "US":
        try:
            if settings.get("us_llm_provider", False):
                if settings.get("us_llm_model") == "openai":
                    if settings.get("us_llm_model", False):
                        us_llm = ChatOpenAI(model=settings.get("us_llm_model"), temperature=0)
                    else:
                        us_llm = ChatOpenAI(model="gpt-4o", temperature=0)
                elif settings.get("us_llm_model") == "claude":
                    if settings.get("us_llm_model", False):
                        us_llm = ChatAnthropic(model=settings.get("us_llm_model"), temperature=0)
                    else:
                        us_llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
            else:
                us_llm = ChatOpenAI(model="gpt-4o", temperature=0)

            return us_llm
        except Exception:
            # us_llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
            us_llm = None
            return us_llm
    else:
        return ChatOpenAI(model="gpt-4o", temperature=0)



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
        msg_id = str(uuid.uuid4()),
        # send self a message to trigger the real component search work-flow
        agent_response_message = {
            "id": str(uuid.uuid4()),
            "chat": {
                "input": state["result"]["llm_result"],
                "attachments": [],
                "messages": [self_agent.card.id, chat_id, msg_id, "", state["result"]["llm_result"]],
            },
            "params": {
                "content": state["result"]["llm_result"],
                "attachments": state["attachments"],
                "metadata": {
                    "type": "text", # "text", "code", "form", "notification", "card
                    "card": {},
                    "code": {},
                    "form": {},
                    "notification": {},
                },
                "role": "",
                "senderId": f"{agent_id}",
                "createAt": int(time.time() * 1000),
                "senderName": f"{self_agent.card.name}",
                "status": "success",
                "ext": "",
                "human": False
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
    # On Windows, Playwright requires SelectorEventLoop for subprocess support
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            # If setting policy fails, continue with best effort
            pass

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
        # On Windows, asyncio subprocess support requires ProactorEventLoop
        if sys.platform.startswith("win"):
            try:
                if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
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

class BreakpointManager:
    def __init__(self):
        self.breakpoints = set()
        self.pending_interrupt = None

    def set_breakpoint(self, node_name: str):
        self.breakpoints.add(node_name)

    def clear_breakpoint(self, node_name: str):
        self.breakpoints.discard(node_name)

    def clear_all(self):
        self.breakpoints.clear()

    def has_breakpoint(self, node_name: str) -> bool:
        return node_name in self.breakpoints

    def capture_interrupt(self, interrupt: Interrupt):
        self.pending_interrupt = interrupt

    def resume(self):
        if self.pending_interrupt:
            self.pending_interrupt.resume()
            self.pending_interrupt = None


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


# def step1(state): return {"a": 1}
# def step2(state): return {"b": state["a"] + 2}
# def step3(state): return {"c": state["b"] * 2}
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