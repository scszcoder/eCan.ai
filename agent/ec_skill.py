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

from agent.a2a.common.types import AgentSkill
import json
import traceback
import time
import httpx
import asyncio
import requests
import operator

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

            # List available tools
            tools = await session.list_tools()
            print(tools)

            # Call the fetch tool
            # result = await session.call_tool("say_hello")
            # print(result)

            # await session.send_message({
            #     "type": "ping",
            #     "payload": "hello from test client"
            # })
            #
            # # Receive a message from the server
            # response = await session.recv_message()
            # print("MCP client Received response:", response)

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
            workflow = StateGraph(AgentState)
            workflow.add_node("llm_loop", make_llm_tool_node(session))
            workflow.add_node("verify", verify_resolved)

            workflow.set_entry_point("llm_loop")
            workflow.add_edge("llm_loop", "verify")
            workflow.add_conditional_edges("verify", route_logic, {
                "llm_loop": "llm_loop",
                END: END
            })

            helper_skill.set_work_flow(workflow)

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
        operator_skill = EC_Skill(name="ecbot rpa operator",
                             description="help run ecbot RPA works.")

        await wait_until_server_ready("http://localhost:4668/healthz")
        print("connecting...........sse")

        async def rpa_operator(state: AgentState) -> AgentState:
            """
            Connects to an MCP gateway via SSE, calls a tool, records the result.
            Replace 'take_screenshot' with whatever tool you actually need.
            """

            # 1. open a *temporary* SSE connection
            async with sse_client("http://localhost:4668/sse") as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()  # mandatory handshake

                    # 2. call the remote tool
                    image_b64: str = await session.call_tool("rpa_supervisor_work")

            # 3. update the LangGraph state
            state["messages"].append(f"received {len(image_b64)} base-64 chars")
            state["resolved"] = True  # or your real success criterion
            return state

        # ───────────────  compile a one-node graph ───────────────────────────
        workflow = StateGraph(AgentState)
        workflow.add_node("RPA Operator", rpa_operator)  # single node
        workflow.set_entry_point("RPA Operator")
        workflow.add_edge("RPA Operator", END)
        operator_skill.set_work_flow(workflow)

        # ───────────────  run it once ────────────────────────────────────────
        initial_state: AgentState = {
            "input": "grab a screenshot please",
            "messages": [],
            "retries": 0,
            "resolved": False,
        }

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
        supervisor_skill = EC_Skill(name="ecbot rpa supervisor",
                             description="Supervise ecbot RPA operators.")

        await wait_until_server_ready("http://localhost:4668/healthz")

        async def rpa_supervisor(state: AgentState) -> AgentState:
            """
            Connects to an MCP gateway via SSE, calls a tool, records the result.
            Replace 'take_screenshot' with whatever tool you actually need.
            """

            # 1. open a *temporary* SSE connection
            async with sse_client("http://localhost:4668/sse") as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()  # mandatory handshake

                    # 2. call the remote tool
                    image_b64: str = await session.call_tool("rpa_supervisor_work")

            # 3. update the LangGraph state
            state["messages"].append(f"received {len(image_b64)} base-64 chars")
            state["resolved"] = True  # or your real success criterion
            return state

        # ───────────────  compile a one-node graph ───────────────────────────
        workflow = StateGraph(AgentState)
        workflow.add_node("RPA Supervisor", rpa_supervisor)  # single node
        workflow.set_entry_point("RPA Supervisor")
        workflow.add_edge("RPA Supervisor", END)
        supervisor_skill.set_work_flow(workflow)

        # ───────────────  run it once ────────────────────────────────────────
        initial_state: AgentState = {
            "input": "grab a screenshot please",
            "messages": [],
            "retries": 0,
            "resolved": False,
        }



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