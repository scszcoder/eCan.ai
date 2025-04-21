from typing import Any, Dict, List, Literal, Optional, Type, Callable, Annotated
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
import uuid
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, START
from langgraph.graph.graph import CompiledGraph
from langgraph.graph.message import AnyMessage, add_messages
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from typing_extensions import TypedDict
from langgraph.prebuilt import tools_condition
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

from agent.a2a.common.types import AgentSkill
import json
import traceback
import time
import httpx
import asyncio
import requests

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

class EC_Skill(AgentSkill):
    id: str = str(uuid.uuid4())
    work_flow: StateGraph = StateGraph(State)        # {"app_name": "app_context", ....} "ecbot" being the internal rpa runs.
    runnable: CompiledGraph = None
    owner: str = ""
    name: str = "generic"
    description: str = "to do and not to do"
    config: dict = {}
    ui_info: dict = {"text": "skill", "icon": ""}
    objectives: [str] = []
    need_inputs: [dict] = []
    version: str = "0.0.0"
    level: str = "entry"

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

    def loadFromFile(self, sk_json_file):
        with open(sk_json_file, "r") as skjsf:
            sk_js = json.load(skjsf)
            self.set_ui_info(sk_js["ui_info"])


async def build_agent_skills(mainwin, skill_path=""):
    skills = []
    if not skill_path:
        print("build from code......")
        new_skill = await create_rpa_helper_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_rpa_operator_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_rpa_supervisor_skill(mainwin)
        skills.append(new_skill)
    else:
        skills = build_agent_skills_from_files(mainwin, skill_path)
    return skills

def build_agent_skills_from_files(mainwin, skill_path=""):
    return []

async def wait_until_server_ready(url: str, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.3)
    raise RuntimeError(f"Server not ready at {url}")

async def test_post_to_messages():
    url = "http://localhost:4668/messages"

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
    resp = requests.post("http://localhost:4668/messages", json={
        "type": "ping",
        "payload": "test message"
    })

    print("Status:", resp.status_code)
    print("Response body:", resp.text)

async def create_rpa_helper_skill(mainwin):
    try:
        llm = mainwin.llm
        helper_skill = EC_Skill(name="ecbot rpa helper",
                             description="help fix failures during ecbot RPA runs.")

        await wait_until_server_ready("http://localhost:4668/healthz")
        print("connecting...........sse")
        async with sse_client("http://localhost:4668/sse/") as streams:
            print("hihihihihi")
            async with ClientSession(streams[0], streams[1]) as session:
                print("hohohohoh initing.......")
                await session.initialize()
                # Send a message to the server
                print("hahahahha init done.......")
                # await session.send_message({
                #     "type": "ping",
                #     "payload": "hello from test client"
                # })
                #
                # # Receive a message from the server
                # response = await session.recv_message()
                # print("MCP client Received response:", response)

        print("connecting...........sse")
        # await test_post_to_messages()
        # test_msg()

        # async with MultiServerMCPClient(
        #         {
        #             "E-Commerce Agents Service": {
        #                 # make sure you start your weather server on port 8000
        #                 "url": "http://localhost:4668/sse",
        #                 "transport": "sse",
        #             }
        #         }
        # ) as client:
        #     # create_react_agent(
        #     # 	self.model, tools=self.tools, checkpointer=memory, prompt=self.SYSTEM_INSTRUCTION,
        #     # 	response_format=ResponseFormat
        #     # )
        #     mcp_agent = create_react_agent(llm, client.get_tools())
        #     helper_skill.set_runnable(mcp_agent)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPAHelperSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPAHelperSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return helper_skill


async def create_rpa_operator_skill(mainwin):
    try:
        llm = mainwin.llm
        helper_skill = EC_Skill(name="ecbot rpa operator",
                             description="help run ecbot RPA works.")

        await wait_until_server_ready("http://localhost:4668/healthz")
        print("connecting...........sse")
        async with sse_client("http://localhost:4668/sse/") as streams:
            print("hihihihihi")
            async with ClientSession(streams[0], streams[1]) as session:
                print("hohohohoh initing.......")
                await session.initialize()
                # Send a message to the server
                print("hahahahha init done.......")


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the fild
        mainwin.showMsg(ex_stat)
        return None

    return helper_skill



async def create_rpa_supervisor_skill(mainwin):
    try:
        llm = mainwin.llm
        helper_skill = EC_Skill(name="ecbot rpa supervisor",
                             description="Supervise ecbot RPA operators.")

        await wait_until_server_ready("http://localhost:4668/healthz")

        print("connecting...........sse")
        async with sse_client("http://localhost:4668/sse/") as streams:
            print("hihihihihi")
            async with ClientSession(streams[0], streams[1]) as session:
                print("hohohohoh initing.......")
                await session.initialize()
                # Send a message to the server
                print("hahahahha init done.......")
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPASupervisorSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPASupervisorSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return helper_skill