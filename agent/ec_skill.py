from typing import Any, Dict, List, Literal, Optional, Type, Callable, Annotated
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
import uuid
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, START
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessage, HumanMessage
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from typing import TypedDict, List, Any
import subprocess
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import AnyMessage, add_messages, MessagesState, BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.errors import NodeInterrupt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
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
import httpx
import asyncio
import requests
import socket
from urllib.parse import urlparse

import operator
from utils.logger_helper import logger_helper as logger
from agent.mcp.config import mcp_messages_url

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
    objectives: [str] = []
    need_inputs: [dict] = []
    version: str = "0.0.0"
    level: str = "entry"
    path: str = ""

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



async def wait_until_server_ready(url: str, timeout=30):
    """
    更稳健的服务器就绪等待：
    1) 先等待 TCP 端口进入监听状态；
    2) 再轮询 /healthz；
    仅使用 httpx 的超时，不再叠加 asyncio.wait_for；复用连接池。
    """
    deadline = time.time() + float(timeout)
    last_error = None

    logger.info(f"Waiting for server ready at {url}, timeout: {timeout}s")

    # 解析 URL 获取主机和端口（用于 TCP 探测）
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if (parsed.scheme or "http") == "https" else 80)

    # 第一阶段：端口监听探测（快速轮询，避免首启盲等 HTTP）
    port_attempts = 0
    while time.time() < deadline:
        port_attempts += 1
        try:
            with socket.create_connection((host, port), timeout=1.0) as s:
                s.close()
                logger.debug(f"TCP {host}:{port} is listening (after {port_attempts} attempts)")
                break
        except OSError as e:
            last_error = f"TCP connect failed: {e}"
        await asyncio.sleep(0.3)
    else:
        error_msg = f"Server port not listening at {host}:{port} within {timeout}s. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # 第二阶段：HTTP 健康检查（复用客户端 + 单层超时）
    http_attempts = 0
    # 初始超时配置；后续根据剩余时间适当收敛
    timeout_cfg = httpx.Timeout(connect=2.0, read=2.5, write=1.0, pool=1.0)
    async with httpx.AsyncClient(timeout=timeout_cfg, trust_env=False) as client:
        while time.time() < deadline:
            http_attempts += 1
            remaining = max(0.5, deadline - time.time())
            # 动态调整读取超时，但不超过 3s
            client.timeout = httpx.Timeout(connect=2.0, read=min(3.0, remaining), write=1.0, pool=1.0)
            try:
                logger.debug(f"Attempt {http_attempts}: checking {url} (read timeout: {client.timeout.read:.1f}s)")
                resp = await client.get(url)
                if resp.status_code == 200:
                    logger.info(f"Server ready at {url} after {http_attempts} attempts")
                    return True
                else:
                    last_error = f"HTTP {resp.status_code}"
                    logger.debug(f"Server returned status {resp.status_code}")
            except httpx.TimeoutException as e:
                last_error = f"HTTPX timeout: {e}"
                logger.debug(f"Attempt {http_attempts}: httpx timeout")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.debug(f"Attempt {http_attempts}: connection failed - {e}")
            except httpx.HTTPError as e:
                last_error = f"HTTP error: {e}"
                logger.debug(f"Attempt {http_attempts}: HTTP error - {e}")
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.debug(f"Attempt {http_attempts}: unexpected error - {e}")

            await asyncio.sleep(0.5)

    error_msg = f"Server not ready at {url} after {timeout}s ({http_attempts} attempts). Last error: {last_error}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)

async def test_post_to_messages():
    url = mcp_messages_url()  # server expects trailing slash

    # Example MCP message format — adjust to match your server expectation
    payload = {
        "stream_id": "stream-1234",
        "message": {
            "role": "user",
            "content": "Hello from test client"
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            print("Status code:", response.status_code)
            print("Response body:", response.text)
    except Exception as e:
        print("Request failed:", str(e))


def test_msg():
    resp = requests.post(mcp_messages_url(), json={
        "type": "ping",
        "payload": "test message"
    })

    print("Status:", resp.status_code)
    print("Response body:", resp.text)

class BaseState(MessagesState):
    messages: Annotated[List[BaseMessage], operator.add]
    my_list: List[int]
    is_last_step: bool

def _bind_to_system_message(state):
    print(state) # Problem here
    return "system prompt"


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
    formatted_prompts: List[dict]
    messages: List[Any]
    threads: List[dict]
    metadata: dict
    attributes: dict
    result: dict
    tool_input: dict
    tool_result: dict
    error: str
    retries: int
    condition: bool
    case: str
    goals: List[Goal]


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


def is_json_parsable(s):
    try:
        json.loads(s)
        return True
    except (ValueError, TypeError):
        return False

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