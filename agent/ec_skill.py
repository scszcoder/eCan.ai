from typing import Any, ClassVar, Optional, Dict, List, Literal, Type, Generic, Tuple, TypeVar, cast
import copy
import json
from typing import Callable, Annotated
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
import uuid
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, START
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessage, HumanMessage
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import subprocess
from dataclasses import dataclass
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import AnyMessage, add_messages, MessagesState, BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.errors import NodeInterrupt
from langgraph.checkpoint.memory import InMemorySaver
#from sqlalchemy.testing.suite.test_reflection import metadata
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from typing_extensions import TypedDict
from langgraph.prebuilt import tools_condition
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from agent.mcp.client.client_manager import MCPClientSessionManager
from agent.mcp.server.tool_schemas import tool_schemas
from agent.a2a.common.types import AgentSkill, Message, TextPart
import json
import traceback
import time
import random
import httpx
import asyncio
import requests
import socket
from urllib.parse import urlparse

import operator
from utils.logger_helper import logger_helper as logger
from agent.mcp.config import mcp_messages_url
from agent.ec_skills.dev_defs import BreakpointManager
from langgraph.types import Interrupt, interrupt

# ---------------------------------------------------------------------------
# ── 1.  Typed State for LangGraph ───────────────────────────────────────────
# ---------------------------------------------------------------------------
class State(TypedDict):
    """Top‑level LangGraph state object."""
    messages: Annotated[list[Any], "add_messages"]
    mcp_client: "MultiServerMCPClient"
    retries: int
    resolved: bool
    input: str

class EC_Skill(AgentSkill):
    """Holds a compiled LangGraph runnable and metadata."""

    id: str = str(uuid.uuid4())
    askid: int = 0
    work_flow: StateGraph = StateGraph(State)        # {"app_name": "app_context", ....} "ecbot" being the internal rpa runs.
    diagram: dict = {}
    runnable: CompiledStateGraph = None
    mcp_client: MultiServerMCPClient = None
    owner: str = ""
    name: str = "generic"
    description: str = "to do and not to do"
    config: dict = {}
    ui_info: dict = {"text": "skill", "icon": ""}
    objectives: List[str] = []
    need_inputs: List[dict] = []
    version: str = "0.0.0"
    level: str = "entry"
    path: str = ""
    # Optional: per-skill mapping rules for resume/state mapping DSL
    mapping_rules: dict | None = None

    tags: List[str] | None = None
    examples: List[str] | None = None
    inputModes: List[str] | None = None
    outputModes: List[str] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_config(self):
        return self.config

    def get_ui_info(self):
        return self.ui_info

    def set_runnable(self, compiled_graph):
        self.runnable = compiled_graph

    def get_runnable(self):
        return self.runnable

    def set_work_flow(self, wf):
        self.work_flow = wf
        checkpointer = InMemorySaver()
        self.runnable = wf.compile(checkpointer=checkpointer)

    def get_work_flow(self):
        return self.work_flow

    def loadFromFile(self, sk_json_file):
        with open(sk_json_file, "r") as skjsf:
            sk_js = json.load(skjsf)
            self.set_ui_info(sk_js["ui_info"])

    def getWorkFlowJSON(self):
        flowJS = self.work_flow
        flowJS = {}
        return flowJS

    def to_dict(self):
        return {
            "id": self.id,
            "work_flow": self.getWorkFlowJSON(),
            "owner": self.owner,
            "name": self.name,
            "description": self.description,
            "config": self.config,
            "ui_info": self.ui_info,
            "objectives": self.objectives,
            "need_inputs": self.need_inputs,
            "version": self.version,
            "level": self.level,
        }


@dataclass
class SkillDTO:
    name: str
    description: str
    config: Dict[str, Any]

@dataclass
class LoadedSkill:
    dto: SkillDTO
    work_flow: StateGraph


class BaseState(MessagesState):
    messages: Annotated[List[BaseMessage], operator.add]
    my_list: List[int]
    is_last_step: bool

# def _bind_to_system_message(state):
#     print(state) # Problem here
#     return "system prompt"


# Goal for graph
class Goal(TypedDict):
    name: str
    description: str
    value_type: str
    min_val: str
    max_val: str
    formula: str
    lut: dict
    score: float
    weight: float
    sub_goals: List[dict]

class FileAttachment(TypedDict):
    name: str
    type: str
    url: str
    data: bytes


# State for LangGraph
class NodeState(TypedDict):
    input: str
    attachments: List[FileAttachment]
    prompts: List[dict]
    prompt_refs: dict
    formatted_prompts: List[dict]
    messages: List[Any]
    threads: List[dict]
    metadata: dict
    this_node: str
    attributes: dict
    result: dict
    tool_input: dict
    tool_result: dict
    error: str
    retries: int
    condition: bool
    case: str
    goals: List[Goal]
    breakpoint: bool


class ToT_Context(TypedDict):
    max_depth: int
    threshold: float
    k: int
    beam_size: int


class WorkFlowContext(TypedDict, total=False):
    id: str
    topic: str
    summary: str
    msg_thread_id: str
    tot_context: dict
    app_context: dict
    this_node: dict


def node_wrapper(fn, node_name, skill_name, owner):
    def wrapped(state, *, runtime: Runtime[WorkFlowContext], store: BaseStore, **kwargs):
        # Inject node name into context or config
        runtime.context["this_node"] = {"name": node_name, "skill_name": skill_name, "owner": owner}
        return fn(state, runtime=runtime, store=store, **kwargs)
    return wrapped


def node_builder(node_fn, node_name, skill_name, owner, bp_manager, default_retries=3, base_delay=1, jitter=0.5):
    """
    A higher-order function that wraps a node's callable to add common functionality
    like retries, breakpoint handling, and context injection.
    """

    def wrapper(state: dict, *, runtime: Runtime[WorkFlowContext], store: BaseStore, **kwargs) -> dict:
        """This inner function is what gets executed by LangGraph for each node.
        It contains the retry logic and handles processing the return value.
        """ 
        # Execute the node function first
        # Safely get and cast the retry value to an integer

        # Safely get and cast the retry value to an integer
        try:
            retries = int(state.get("retry", default_retries))
        except (ValueError, TypeError):
            retries = default_retries

        attempts = 0
        last_exc = None
        result = None

        # Utility: produce a JSON/checkpoint safe view of state (whitelist fields, avoid cycles)
        def _prune_result(res: Any) -> Any:
            if isinstance(res, dict):
                forbidden = {
                    "input","attachments","prompts","formatted_prompts","messages","threads","metadata",
                    "attributes","result","tool_input","tool_result","error","retries","condition","case","goals"
                }
                # keep only non-forbidden keys from result
                return {k: _prune_result(v) for k, v in res.items() if k not in forbidden}
            elif isinstance(res, list):
                return [_prune_result(v) for v in res]
            else:
                return res

        def _safe_state_view(st: dict) -> dict:
            whitelist = [
                "input","attachments","prompts","formatted_prompts","messages","threads","metadata",
                "attributes","result","tool_input","tool_result","error","retries","condition","case","goals"
            ]
            out = {}
            for k in whitelist:
                v = st.get(k)
                # Prevent obvious self refs and heavy objects
                if k == "result" and v is st:
                    v = {}
                if k == "result":
                    # Always prune result to prevent nesting/recursion
                    out[k] = _prune_result(v)
                elif isinstance(v, dict):
                    # shallow copy and drop recursive 'result' if points back
                    vd = dict(v)
                    if vd.get("result") is st:
                        vd.pop("result", None)
                    out[k] = vd
                elif isinstance(v, (list, tuple, str, int, float, bool)) or v is None:
                    out[k] = copy.deepcopy(v)
                else:
                    # drop unsupported types
                    out[k] = None
            # Final JSON check; if fails, degrade fields
            try:
                json.dumps(out, ensure_ascii=False, default=str)
            except Exception:
                # best-effort: stringify any non-serializable remnants
                def _stringify(o):
                    try:
                        json.dumps(o)
                        return o
                    except Exception:
                        return str(o)
                out = {k: _stringify(v) for k, v in out.items()}
            return out

        # Check for breakpoints BEFORE executing the node
        # This ensures we pause before any node code runs
        if bp_manager and bp_manager.has_breakpoint(node_name):
            # sanitize potential self-referential result before any interrupt
            try:
                if state.get("result") is state:
                    logger.warning(f"Detected self-referential state.result at {node_name}; clearing to avoid recursion")
                    state["result"] = {}
                elif isinstance(state.get("result"), dict) and state["result"].get("result") is state:
                    logger.warning(f"Detected nested self-reference in state.result at {node_name}; trimming")
                    state["result"].pop("result", None)
            except Exception:
                pass
            # Support one-shot skip using runtime.context (controlled by the task loop)
            skip_list = []
            try:
                skip_list = runtime.context.get("skip_bp_once", [])
            except Exception:
                skip_list = []

            if isinstance(skip_list, (list, tuple)) and node_name in skip_list:
                logger.info(f"Skip-once: skipping breakpoint at {node_name} per runtime.context")
                # remove it so it only skips once
                try:
                    if isinstance(skip_list, list):
                        skip_list.remove(node_name)
                        runtime.context["skip_bp_once"] = skip_list
                except Exception:
                    pass
            else:
                # Fallback: state-based resume flag (kept for compatibility with older flows)
                resuming_from = state.get("_resuming_from")
                logger.info(f"DEBUG: Breakpoint check for {node_name}, _resuming_from = {resuming_from}")
                if resuming_from == node_name:
                    logger.info(f"Skipping breakpoint at {node_name} - resuming from this node (state flag)")
                    state.pop("_resuming_from", None)
                else:
                    logger.info(f"Breakpoint hit at node: {node_name}. Pausing before execution.")
                    interrupt({"paused_at": node_name, "i_tag": node_name, "state": _safe_state_view(state)})

        # Execute the node function with retry logic
        while attempts < retries:
            try:
                # Add node context to the state, which is mutable
                if "attributes" not in state or not isinstance(state.get("attributes"), dict):
                    state["attributes"] = {}
                state["attributes"]["__this_node__"] = {"name": node_name, "skill_name": skill_name, "owner": owner}
                
                # Execute the actual node function
                runtime.context["this_node"] = {"name": node_name}
                result = node_fn(state, runtime=runtime, store=store)
                break  # success - exit retry loop
                
            except Exception as e:
                attempts += 1
                last_exc = e
                logger.warning(f"[{node_name}] failed (attempt {attempts}/{retries}): {e}")
                if attempts < retries:
                    delay = base_delay * (2 ** (attempts - 1)) + random.uniform(0, jitter)
                    time.sleep(delay)

        if last_exc:
            raise last_exc

        # Process the result to ensure it's a valid dictionary for state update
        if isinstance(result, list):
            # Handle cases where debugging injects an Interrupt object
            dict_result = next((item for item in result if isinstance(item, dict)), None)
            state["result"] = _prune_result(dict_result or {})
        elif isinstance(result, dict):
            state["result"] = _prune_result(result)
        else:
            # If the result is not a dict (e.g., None), return an empty dict to prevent errors
            state["result"] = result

        # Final sanitation to avoid self-referential recursion in checkpoints
        try:
            if state.get("result") is state:
                logger.warning(f"Detected self-referential state.result after exec at {node_name}; clearing")
                state["result"] = {}
            elif isinstance(state.get("result"), dict) and state["result"].get("result") is state:
                logger.warning(f"Detected nested self-reference in state.result after exec at {node_name}; trimming")
                state["result"].pop("result", None)
            # ensure pruned
            state["result"] = _prune_result(state.get("result", {}))
        except Exception:
            pass

        print("returning state...", state)
        return state
    # The node_builder itself returns the wrapper function
    return wrapper


# ============ scratch here ==============================
prompt0 = ChatPromptTemplate.from_messages([
            ("system", """
                You're a electronics component procurement expert helping sourcing components for this provided BOM in JSON format. Analyze the screenshot image provided.
                - If an ad popup blocks the screen, identify the exact (x,y) coordinates to click.
                - If Wi-Fi is disconnected, instruct to reconnect Wi-Fi.
                Indicate clearly if the issue has been resolved.
            """),
            ("human", [
                {"type": "text", "text": "{input}"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
            ]),
            ("placeholder", "{messages}"),
        ])

prompt1 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                - given the parameters, please check against our knowledge base to check whether additional parameters or selection criteria needed from the user, if so, prompt user with questions to get the info about the additional parameters or criteria.
                - If all required parameters are collected, please generate a long tail search term for components search site: {site_url}
                Indicate clearly if the issue has been resolved.
            """),
            ("human", [
                {"type": "text", "text": "{input}"},
                {"type": "image", "source_type": "base64", "data":"{image_b64}", "mime_type": "image/jpeg"}
            ]),
            ("placeholder", "{messages}"),
        ])

# openai file id can be obtained after uploading files to the /v1/files
# post https://api.openai.com/v1/batches
# post https://api.openai.com/v1/files
# get https://api.openai.com/v1/files/{file_id}
# get https://api.openai.com/v1/files   ---  Returns a list of files.


prompt2 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                - given all required parameters, as well as the collected DOM tree of the current web page, please help collect as much required parameter info as possible
                - If all required parameters are collected, please generate a long tail search term for components search site: {site_url}
                Indicate clearly if the issue has been resolved.
            """),
            ("human", [
                {"type": "text", "text": "{input}"},
                {"type": "image_url", "source_type": "url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
                {"type": "audio", "source_type": "base64", "data": "audio_data", "mime_type": "audio/wav", "cache_control": {"type": "ephemeral"}},
                {"type": "file", "file": { "filename": "draconomicon.pdf", "file_data": "...base64 encoded bytes here..." }},
                {"type": "file", "file": { "file_id": "file-6F2ksmvXxt4VdoqmHRw6kL" }},
                { "type": "input_audio", "input_audio": { "data": "encoded_string", "format": "wav" }}
            ]),
            ("placeholder", "{messages}"),
        ])


def is_json_parsable(s):
    try:
        json.loads(s)
        return True
    except (ValueError, TypeError):
        return False