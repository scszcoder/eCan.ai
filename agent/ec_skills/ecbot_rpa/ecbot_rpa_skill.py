from langgraph.graph import END, StateGraph, START
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent
# from sqlalchemy.testing.suite.test_reflection import metadata
from browser_use.agent.message_manager.utils import save_conversation
from browser_use.agent.views import (
	ActionResult,
	StepMetadata,
)
from mcp.client.session import ClientSession

from agent.ec_skill import *
from agent.agent_service import get_agent_by_id
from agent.a2a.common.types import Message, TextPart
from telemetry.views import AgentStepTelemetryEvent
import traceback
import asyncio


async def create_rpa_helper_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        helper_skill = EC_Skill(
            name="ecbot rpa helper",
            description="help fix failures during ecbot RPA runs.",
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
        print("helper_skill build is done!")

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
        logger.error(ex_stat)
        end_state["messages"][0] = f"Task Error: {ex_stat}"

    print("operator_message_handler task end state:", end_state)
    return end_state  # must return the new state


async def create_rpa_operator_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        operator_skill = EC_Skill(
            name="ecbot rpa operator run RPA",
            description="drive a bunch of bots to run their ecbot RPA works.",
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
        print("operator_skill build is done!")

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


async def create_rpa_supervisor_scheduling_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        supervisor_skill = EC_Skill(
            name="ecbot rpa supervisor task scheduling",
            description="help fix failures during ecbot RPA runs.",
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
        print("supervisor_scheduling_skill build is done!")

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
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
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
        logger.error(ex_stat)

    return end_state  # must return the new state



async def create_rpa_supervisor_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        supervisor_skill = EC_Skill(
            name="ecbot rpa supervisor serve requests",
            description="help fix failures during ecbot RPA runs.",
            source="code"  # Mark as code-generated skill
        )

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
        print("rpa_supervisor_skill build is done!")

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


async def in_browser_scrape_content(state: NodeState) -> NodeState:
    """Execute one step of the task"""
    state = None
    model_output = None
    result: list[ActionResult] = []
    step_start_time = time.time()
    tokens = 0
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin

    try:
        global_context = agent.global_context
        state = await agent.global_context.get_state()
        active_page = await agent.global_context.get_current_page()
        # generate procedural memory if needed
        if agent.settings.enable_memory and agent.memory and agent.state.n_steps % agent.settings.memory_interval == 0:
            agent.memory.create_procedural_memory(agent.state.n_steps)

        await agent._raise_if_stopped_or_paused()

        # Update action models with page-specific actions
        await agent._update_action_models_for_page(active_page, global_context)

        # Get page-specific filtered actions
        page_filtered_actions = agent.runner.registry.get_prompt_description(active_page, global_context)

        # If there are page-specific actions, add them as a special message for this step only
        if page_filtered_actions:
            page_action_message = f'For this page, these additional actions are available:\n{page_filtered_actions}'
            agent._message_manager._add_message_with_tokens(HumanMessage(content=page_action_message))

        # If using raw tool calling method, we need to update the message context with new actions
        # For raw tool calling, get all non-filtered actions plus the page-filtered ones
        all_unfiltered_actions = agent.runner.registry.get_prompt_description()
        all_actions = all_unfiltered_actions

        if page_filtered_actions:
            all_actions += '\n' + page_filtered_actions

            context_lines = agent._message_manager.settings.message_context.split('\n')
            non_action_lines = [line for line in context_lines if not line.startswith('Available actions:')]
            updated_context = '\n'.join(non_action_lines)
            if updated_context:
                updated_context += f'\n\nAvailable actions: {all_actions}'
            else:
                updated_context = f'Available actions: {all_actions}'
            agent._message_manager.settings.message_context = updated_context

        print("add state message:", state)
        agent._message_manager.add_state_message(state, agent.state.last_result,
                                                agent.settings.use_vision)



        input_messages = agent._message_manager.get_messages()
        tokens = agent._message_manager.state.history.current_tokens


        model_output = await agent.get_next_action(input_messages)

        # Check again for paused/stopped state after getting model output
        # This is needed in case Ctrl+C was pressed during the get_next_action call
        await agent._raise_if_stopped_or_paused()

        agent.state.n_steps += 1

        if agent.settings.save_conversation_path:
            target = agent.settings.save_conversation_path + f'_{agent.state.n_steps}.txt'
            save_conversation(input_messages, model_output, target,
                              agent.settings.save_conversation_path_encoding)

        agent._message_manager._remove_last_state_message()  # we dont want the whole state in the chat history

        # check again if Ctrl+C was pressed before we commit the output to history
        await agent._raise_if_stopped_or_paused()

        agent._message_manager.add_model_output(model_output)

        result: list[ActionResult] = await agent.multi_act(model_output.action)

        agent.state.last_result = result

        if len(result) > 0 and result[-1].is_done:
            # logger.info(f'📄 Result: {result[-1].extracted_content}')
            print(f'📄 Result: {result[-1].extracted_content}')

        agent.state.consecutive_failures = 0


    except InterruptedError:
        # logger.debug('Agent paused')
        agent.state.last_result = [
            ActionResult(
                error='The agent was paused mid-step - the last action might need to be repeated',
                include_in_memory=False
            )
        ]
        return
    except asyncio.CancelledError:
        # Directly handle the case where the step is cancelled at a higher level
        # logger.debug('Task cancelled - agent was paused with Ctrl+C')
        agent.state.last_result = [ActionResult(error='The agent was paused with Ctrl+C', include_in_memory=False)]
        raise InterruptedError('Step cancelled by user')
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorFetchSchedule:" + traceback.format_exc() + " " + str(e)
            # logger.error(f'❌  Failed to step: {ex_stat}')
            print(f'[ERROR] Failed to step: {ex_stat}')

        result = await agent._handle_step_error(e)
        agent.state.last_result = result

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

    finally:
        step_end_time = time.time()
        actions = [a.model_dump(exclude_unset=True) for a in model_output.action] if model_output else []
        agent.telemetry.capture(
            AgentStepTelemetryEvent(
                agent_id=agent.state.agent_id,
                step=agent.state.n_steps,
                actions=actions,
                consecutive_failures=agent.state.consecutive_failures,
                step_error=[r.error for r in result if r.error] if result else ['No result'],
            )
        )
        if not result:
            return

        if state:
            metadata = StepMetadata(
                step_number=state.n_steps,
                step_start_time=step_start_time,
                step_end_time=step_end_time,
                input_tokens=tokens,
            )
            agent._make_history_item(model_output, state, result, metadata)

