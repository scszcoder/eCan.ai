import traceback
from mcp.client.session import ClientSession
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent
from langgraph.graph import END, StateGraph, START
from agent.ec_skill import *
import json
import time
from agent.a2a.common.types import Message, TextPart

async def create_rpa_helper_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        helper_skill = EC_Skill(
            name="chatter for ecbot rpa helper",
            description="human and agent chat for helping fix failures during ecbot RPA runs.",
            source="code"  # Mark as code-generated skill
        )        
        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        # all_tools = mcp_client.get_tools()
        # help_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        # helper_tools = [t for t in all_tools if t.name in help_tool_names]
        # print("helper # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])
        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        helper_tools = []
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
            print("verify_resolved current state", state)
            last_msg = state["messages"][-1].content.lower()
            if "resolved" in last_msg:
                state["resolved"] = True
            else:
                state["resolved"] = False
                state["retries"] = int(state.get("retries") or 0) + 1
            return state

        # Router logic
        def route_logic(state: NodeState) -> str:
            if bool(state.get("resolved")) or int(state.get("retries") or 0) >= 5:
                return END
            return "llm_loop"

        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState, WorkFlowContext)
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
        print("helper_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPAHelperSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPAHelperSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
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


async def create_rpa_operator_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        operator_skill = EC_Skill(
            name="chatter for ecbot rpa operator run RPA",
            description="human and agent chat for RPA operator agent who drive a bunch of RPA bots to run their ecbot RPA works.",
            source="code"  # Mark as code-generated skill
        )        
        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")


        # all_tools = mcp_client.get_tools()
        # help_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        # helper_tools = [t for t in all_tools if t.name in help_tool_names]
        # print("operator # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])


        # 3) ----- Build a graph with ONE node ---------------------------------------

        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("message_handler", operator_message_handler)
        workflow.set_entry_point("message_handler")  # where execution starts
        workflow.add_edge("message_handler", END)


        operator_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        operator_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("operator_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPASupervisorSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPASupervisorSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
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


async def create_rpa_supervisor_scheduling_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        supervisor_skill = EC_Skill(
            name="chatter for ecbot rpa supervisor task scheduling",
            description="human and agent chat for RPA supervisor agent who schedule tasks for RPA operator agents.",
            source="code"  # Mark as code-generated skill
        )        
        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")


        # 3) ----- Build a graph with ONE node ---------------------------------------
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("message_handler", supervisor_task_scheduler)
        workflow.set_entry_point("message_handler")  # where execution starts
        workflow.add_edge("message_handler", END)

        supervisor_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        supervisor_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("supervisor_scheduling_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPASupervisorSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPASupervisorSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None

    return supervisor_skill



async def reconnect_wifi(params):
    from utils.subprocess_helper import run_no_window
    # Disconnect current Wi-Fi
    run_no_window(["netsh", "wlan", "disconnect"])
    time.sleep(2)

    # Reconnect to a specific network
    cmd = ["netsh", "wlan", "connect", f"name={params['network_name']}"]
    result = run_no_window(cmd, capture_output=True, text=True)
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



async def create_rpa_supervisor_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        supervisor_skill = EC_Skill(name="ecbot rpa supervisor serve requests",
                                description="help fix failures during ecbot RPA runs.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")


        # all_tools = mcp_client.get_tools()
        # help_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        # helper_tools = [t for t in all_tools if t.name in help_tool_names]
        # print("serve # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])


        # 3) ----- Build a graph with ONE node ---------------------------------------
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("message_handler", supervisor_message_handler)
        workflow.set_entry_point("message_handler")  # where execution starts
        workflow.add_edge("message_handler", END)

        supervisor_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        supervisor_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("supervisor_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateRPASupervisorSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateRPASupervisorSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None

    return supervisor_skill



