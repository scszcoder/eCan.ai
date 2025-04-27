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

from langgraph.graph.graph import CompiledGraph
from langgraph.graph.message import AnyMessage, add_messages, MessagesState, BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from typing_extensions import TypedDict
from langgraph.prebuilt import tools_condition
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from agent.mcp.client.client_manager import MCPClientSessionManager
from agent.mcp.server.tool_schemas import tool_schemas
from agent.a2a.common.types import AgentSkill
import json
import traceback
import time
import httpx
import asyncio
import requests
import operator


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
    work_flow: StateGraph = StateGraph(State)        # {"app_name": "app_context", ....} "ecbot" being the internal rpa runs.
    runnable: CompiledGraph = None
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
        self.runnable = wf.compile()

    def get_work_flow(self):
        return self.work_flow

    def loadFromFile(self, sk_json_file):
        with open(sk_json_file, "r") as skjsf:
            sk_js = json.load(skjsf)
            self.set_ui_info(sk_js["ui_info"])


async def build_agent_skills(mainwin, skill_path=""):
    skills = []
    print(f"tool_schemas: {len(tool_schemas)}.")
    if not skill_path:
        print("build agent skills from code......")
        new_skill = await create_rpa_helper_skill(mainwin)
        print("test skill mcp client:", len(new_skill.mcp_client.get_tools()))
        skills.append(new_skill)
        new_skill = await create_rpa_operator_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_rpa_supervisor_scheduling_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_rpa_supervisor_serve_requests_skill(mainwin)
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

class BaseState(MessagesState):
    messages: Annotated[List[BaseMessage], operator.add]
    my_list: List[int]
    is_last_step: bool

def _bind_to_system_message(state):
    print(state) # Problem here
    return "system prompt"

# State for LangGraph
class AgentState(TypedDict):
    input: str
    messages: List[Any]
    retries: int
    resolved: bool

async def create_rpa_helper_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        helper_skill = EC_Skill(name="ecbot rpa helper",
                             description="help fix failures during ecbot RPA runs.")

        await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        all_tools = mcp_client.get_tools()
        help_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        helper_tools = [t for t in all_tools if t.name in help_tool_names]
        print("helper # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])
        helper_agent = create_react_agent(llm, helper_tools)
        # Prompt Template
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
                You're a helper agent resolving browser RPA issues. Analyze the screenshot image provided.
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

        # Planner node
        planner_node = prompt | llm


        def initial_state(input_text: str) -> AgentState:
            return {"input": input_text, "messages": [HumanMessage(content=input_text)], "retries": 0,
                    "resolved": False}

        def make_llm_tool_node(session: ClientSession):
            async def node(state: AgentState) -> AgentState:
                result = await session.invoke(
                    input=state["input"],
                    messages=state["messages"],
                    tool_choice="auto"  # let the LLM decide
                )
                state["messages"].append(result)
                return state

            return node

        async def planner_with_image(state: AgentState):
            # Call your screenshot tool
            # REMOTE call over SSE → MCP tool
            image_b64: str = await helper_skill.mcp_session.call_tool(
                "screen_capture", arguments={"params": {}, "context_id": ""}
            )

            # Build prompt inputs with image
            inputs = {
                "input": state["input"],
                "image_b64": image_b64,
                "messages": state["messages"]
            }
            response = await (prompt | llm).ainvoke(inputs)

            # Append response to messages
            state["messages"].append(response)
            return state


        # Verify node (simple check)
        def verify_resolved(state: AgentState) -> AgentState:
            last_msg = state["messages"][-1].content.lower()
            if "resolved" in last_msg:
                state["resolved"] = True
            else:
                state["retries"] += 1
            return state

        # Router logic
        async def route_logic(state: AgentState) -> str:
            if state["resolved"] or state["retries"] >= 5:
                return END
            return "llm_loop"

        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(AgentState)
        workflow.add_node("llm_loop", helper_agent)
        workflow.add_node("verify", verify_resolved)

        workflow.set_entry_point("llm_loop")
        workflow.add_edge("llm_loop", "verify")
        workflow.add_conditional_edges("verify", route_logic, {
            "llm_loop": "llm_loop",
            END: END
        })

        helper_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        helper_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("helper_skill build is done!")

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
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        operator_skill = EC_Skill(name="ecbot rpa operator run RPA",
                                description="drive a bunch of bots to run their ecbot RPA works.")

        await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")


        all_tools = mcp_client.get_tools()
        help_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        helper_tools = [t for t in all_tools if t.name in help_tool_names]
        print("operator # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])


        # 2) ----- Make the work you want the node to do -----------------------------
        async def operator_message_handler(state: AgentState) -> AgentState:
            # handles these possible messages:
            # from supervisor: rpa_assignment, rpa_control_action
            # from helper: rpa_error_fix_result
            # from rpa task: rpa_result_report, rpa_state_update, rpa_error_help_request
            # to supervisor: (relay) rpa_result_report, rpa_state_update(in case of RPA require human/supervisor in the loop)
            # to helper: (relay) rpa_error_help_request
            text = state.get("text", None)
            if text is None:
                print("No 'text' found in state")
            else:
                print("Node saw:", text)

            state["text"] = state["text"].upper()  # trivial “work”
            return state  # must return the new state

        # 3) ----- Build a graph with ONE node ---------------------------------------
        workflow = StateGraph(AgentState)
        workflow.add_node("message_handler", operator_message_handler)
        workflow.set_entry_point("message_handler")  # where execution starts
        workflow.add_edge("message_handler", END)


        operator_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        operator_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("operator_skill build is done!")

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

    return operator_skill


async def supervisor_task_scheduler(state: AgentState) -> AgentState:
    end_state = {
        "input": "",
        "messages": ["task executed successfully!"],
        "retries": 0,
        "resolved": True
    }
    this_agent = state["messages"][0]
    mcp_client = this_agent.mainwin.mcp_client
    await mcp_client.__aenter__()
    all_tools = mcp_client.get_tools()

    session = mcp_client.sessions["E-Commerce Agents Service"]
    print(" start to say hello")
    # await session.call_tool("say_hello", {"seconds": 2})
    # print(" done to say hello")
    # await session.call_tool("rpa_supervisor_scheduling_work", {"id": "000"})
    # print(" start to say rpa_supervisor_scheduling_work")
    help_tool_names = ['rpa_supervisor_scheduling_work']
    supervisor_scheduler_tool = next((t for t in all_tools if t.name in help_tool_names), None)
    print("scheduler # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])

    if supervisor_scheduler_tool:
        print("start to call supervisor scheduler MCP tool......", supervisor_scheduler_tool)
        result = await supervisor_scheduler_tool.ainvoke({"context_id": "111", "options": {}})
        end_state["messages"].append(result)
    else:
        end_state["messages"][0] = "ERROR: no supervisor scheduler found!"
        print(end_state["messages"])

    return end_state  # must return the new state


async def create_rpa_supervisor_scheduling_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        supervisor_skill = EC_Skill(name="ecbot rpa supervisor task scheduling",
                                description="help fix failures during ecbot RPA runs.")

        await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")






        # 3) ----- Build a graph with ONE node ---------------------------------------
        workflow = StateGraph(AgentState)
        workflow.add_node("message_handler", supervisor_task_scheduler)
        workflow.set_entry_point("message_handler")  # where execution starts
        workflow.add_edge("message_handler", END)

        supervisor_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        supervisor_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("helper_skill build is done!")

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

    return supervisor_skill



async def create_rpa_supervisor_serve_requests_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        supervisor_skill = EC_Skill(name="ecbot rpa supervisor serve requests",
                                description="help fix failures during ecbot RPA runs.")

        await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")


        all_tools = mcp_client.get_tools()
        help_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        helper_tools = [t for t in all_tools if t.name in help_tool_names]
        print("serve # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])

        async def supervisor_message_handler(state: AgentState) -> AgentState:
            # handles these possible messages:
            # from supervisor: rpa_assignment, rpa_control_action
            # from helper: rpa_error_fix_result
            # from rpa task: rpa_result_report, rpa_state_update, rpa_error_help_request
            # to supervisor: (relay) rpa_result_report, rpa_state_update(in case of RPA require human/supervisor in the loop)
            # to helper: (relay) rpa_error_help_request
            text = state.get("text", None)
            if text is None:
                print("No 'text' found in state")
            else:
                print("Node saw:", text)
            state["text"] = state["text"].upper()  # trivial “work”
            return state  # must return the new state

        # 3) ----- Build a graph with ONE node ---------------------------------------
        workflow = StateGraph(AgentState)
        workflow.add_node("message_handler", supervisor_message_handler)
        workflow.set_entry_point("message_handler")  # where execution starts
        workflow.add_edge("message_handler", END)

        supervisor_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        supervisor_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("helper_skill build is done!")

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

    return supervisor_skill


# ============ scratch here ==============================