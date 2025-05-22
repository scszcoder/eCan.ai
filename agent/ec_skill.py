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
from langgraph.graph.graph import CompiledGraph
from langgraph.graph.message import AnyMessage, add_messages, MessagesState, BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from pyqtgraph.examples.MatrixDisplayExample import main_window
from sqlalchemy.testing.suite.test_reflection import metadata

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


# Goal for graph
class Goal(TypedDict):
    name: str
    description: str
    min_criteria: str
    score: float
    weight: float


# State for LangGraph
class NodeState(TypedDict):
    input: str
    messages: List[Any]
    retries: int
    resolved: bool
    goals: List[Goal]

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


        def initial_state(input_text: str) -> NodeState:
            return {"input": input_text, "messages": [HumanMessage(content=input_text)], "retries": 0,
                    "resolved": False}

        def make_llm_tool_node(session: ClientSession):
            async def node(state: NodeState) -> NodeState:
                result = await session.invoke(
                    input=state["input"],
                    messages=state["messages"][-1],
                    tool_choice="auto"  # let the LLM decide
                )
                state["messages"].append(result)
                return state

            return node

        async def planner_with_image(state: NodeState):
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
        def verify_resolved(state: NodeState) -> NodeState:
            last_msg = state["messages"][-1].content.lower()
            if "resolved" in last_msg:
                state["resolved"] = True
            else:
                state["retries"] += 1
            return state

        # Router logic
        async def route_logic(state: NodeState) -> str:
            if state["resolved"] or state["retries"] >= 5:
                return END
            return "llm_loop"

        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState)
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


async def operator_message_handler(state: NodeState) -> NodeState:
    end_state = NodeState(
        input="",
        messages= ["task executed successfully!"],
        retries=0,
        resolved=True
    )

    try:
        print("operator_message_handler......", state)
        if state:
            agent = state["messages"][0]
            a2a_task_req = state["messages"][1]
            req2operator = a2a_task_req.params.message.metadata
            msg_type = req2operator["msg_type"]
            print("operator_message_handler......about to call func.", req2operator)
            result = await operator_msg_function_mapping[msg_type](req2operator, agent)
            end_state["messages"].append(result)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
        print(ex_stat)
        end_state["messages"][0] = f"Task Error: {ex_stat}"

    print("operator_message_handler task end state:", end_state)
    return end_state  # must return the new state


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


        # 3) ----- Build a graph with ONE node ---------------------------------------

        workflow = StateGraph(NodeState)
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


async def supervisor_task_scheduler(state: NodeState) -> NodeState:
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
    print(" start to call mcp to fetch schedule......")
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
        print("mcp tool call result.....", result)
        # now that work schedule is obtained, find out which agent to send the work to, and
        # then send to work to the assigned agents.(this is per vehicle, each vehicle will have
        # an operator agent on it.
        per_vehicle_works = json.loads(result[1])
        print("per_vehicle_works:", per_vehicle_works)
        for v in per_vehicle_works:
            vehicle_operator_agent = this_agent.mainwin.get_vehicle_ecbot_op_agent(v)
            # setup a2a client to send the work to this agent.
            req_data = {"msg_type": "rpa_tasks", "rpa_tasks": per_vehicle_works[v]}
            rpa_task_request = Message(role="user", parts=[TextPart(type="text", text="Here are the RPA work to run")], metadata=req_data)
            rpa_task_reponse = await this_agent.a2a_send_message(vehicle_operator_agent, rpa_task_request)
            print("a2a send response:", rpa_task_reponse)
            if "error" in rpa_task_reponse:
                print("rpa_task_reponse", rpa_task_reponse)
            else:
                print("rpa_task_reponse", rpa_task_reponse)

        print("scheduling done......")
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
        workflow = StateGraph(NodeState)
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



async def reconnect_wifi(params):
    # Disconnect current Wi-Fi
    subprocess.run(["netsh", "wlan", "disconnect"])
    time.sleep(2)

    # Reconnect to a specific network
    cmd = ["netsh", "wlan", "connect", f"name={params['network_name']}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)


async def supervisor_handle_rpa_task_report(mainwin, agent, req_data):
    print("supervisor_handle_rpa_task_report")
    await mainwin.todo_wait_in_line.put(req_data)


async def supervisor_handle_rpa_completion_report(mainwin, agent, req_data):
    print("supervisor_handle_rpa_completion_report")
    await mainwin.todo_wait_in_line.put(req_data)


async def supervisor_handle_rpa_status(mainwin, agent, req_data):
    print("supervisor_handle_rpa_status")
    await mainwin.todo_wait_in_line.put(req_data)


async def supervisor_handle_human_in_loop_request(mainwin, agent, req_data):
    print("supervisor_handle_human_in_loop_request")
    await mainwin.todo_wait_in_line.put(req_data)


async def supervisor_handle_agent_in_loop_request(mainwin, agent, req_data):
    print("supervisor_handle_agent_in_loop_request")
    await mainwin.todo_wait_in_line.put(req_data)

supervisor_msg_function_mapping = {
        "rpa_task_report": supervisor_handle_rpa_task_report,
        "rpa_completion_report": supervisor_handle_rpa_completion_report,
        "rpa_status": supervisor_handle_rpa_status,
        "human_in_loop_request": supervisor_handle_human_in_loop_request,
        "agent_in_loop_request": supervisor_handle_agent_in_loop_request
    }

async def operaor_handle_rpa_tasks(req_data, agent):
    print("operaor_handle_rpa_tasks", req_data, "simply enqueue", len(agent.mainwin.bots))
    # future = asyncio.ensure_future(agent.mainwin.todo_wait_in_line(req_data))
    task_run_stat = await agent.mainwin.todo_wait_in_line(req_data)
    return task_run_stat


async def operaor_handle_run_control(req_data, agent):
    print("operaor_handle_run_control")
    # enqueue
    await agent.mainwin.rpa_wait_in_line.put(req_data)

async def operaor_handle_human_in_loop_response(req_data, agent):
    print("operaor_handle_human_in_loop_response")
    # asyncio.ensure_future(agent.mainwin.rpa_wait_in_line.put(req_data))
    task_run_stat = await agent.mainwin.todo_wait_in_line(req_data)
    return task_run_stat

async def operaor_handle_agent_in_loop_response(req_data, agent):
    print("operaor_handle_agent_in_loop_response")
    task_run_stat = await agent.mainwin.todo_wait_in_line(req_data)
    return task_run_stat

async def operaor_handle_help_response(req_data, agent):
    print("operaor_handle_help_response")
    task_run_stat = await agent.mainwin.todo_wait_in_line(req_data)
    return task_run_stat

operator_msg_function_mapping = {
        "rpa_tasks": operaor_handle_rpa_tasks,
        "run_control": operaor_handle_run_control,
        "human_in_loop_response": operaor_handle_human_in_loop_response,
        "agent_in_loop_response": operaor_handle_agent_in_loop_response,
        "help_response": operaor_handle_help_response
    }


async def supervisor_message_handler(state: NodeState) -> NodeState:
    end_state = {
        "input": "",
        "messages": ["task executed successfully!"],
        "retries": 0,
        "resolved": True
    }

    try:
        print("running supervisor_message_handler....")
        msg_type = state["input"]
        agent = state["messages"][-1]
        mainwin = agent.mainwin
        req_data = state["messages"][-2]
        result = await supervisor_msg_function_mapping[msg_type](mainwin, agent, req_data)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
        end_state["messages"][0] = f"Task Error: {ex_stat}"

    return end_state  # must return the new state



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


        # 3) ----- Build a graph with ONE node ---------------------------------------
        workflow = StateGraph(NodeState)
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


async def in_browser_extract_content(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    page = await browser.get_current_page()
    import markdownify

    strip = []
    if should_strip_link_urls:
        strip = ['a', 'img']

    content = markdownify.markdownify(await page.content(), strip=strip)

    # manually append iframe text into the content so it's readable by the LLM (includes cross-origin iframes)
    for iframe in page.frames:
        if iframe.url != page.url and not iframe.url.startswith('data:'):
            content += f'\n\nIFRAME {iframe.url}:\n'
            content += markdownify.markdownify(await iframe.content())

    prompt = 'Your task is to extract the content of the page. You will be given a page and a goal and you should extract all relevant information around this goal from the page. If the goal is vague, summarize the page. Respond in json format. Extraction goal: {goal}, Page: {page}'
    template = PromptTemplate(input_variables=['goal', 'page'], template=prompt)
    try:
        output = page_extraction_llm.invoke(template.format(goal=goal, page=content))
        msg = f'📄  Extracted from page\n: {output.content}\n'
        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        logger.debug(f'Error extracting content: {e}')
        msg = f'📄  Extracted from page\n: {content}\n'
        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)])


def gen_tool_node_to_extract_web_page(state: NodeState) -> NodeState:
    clickable_dom = state["messages"][-1].content.lower()
    dom_tree = await helper_skill.mcp_session.call_tool(
        "screen_capture", arguments={"params": {}, "context_id": ""}
    )
    return state


def gen_tool_node_to_extract_web_page(state: NodeState) -> NodeState:
    last_msg = state["messages"][-1].content.lower()
    if "resolved" in last_msg:
        state["resolved"] = True
    else:
        state["retries"] += 1
    return state



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
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
            ]),
            ("placeholder", "{messages}"),
        ])


prompt2 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                - given all required parameters, as well as the collected DOM tree of the current web page, please help collect as much required parameter info as possible 
                - If all required parameters are collected, please generate a long tail search term for components search site: {site_url}
                Indicate clearly if the issue has been resolved.
            """),
            ("human", [
                {"type": "text", "text": "{input}"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
            ]),
            ("placeholder", "{messages}"),
        ])