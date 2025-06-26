from typing import TypedDict
import uuid

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from bot.Logger import *
from agent.ec_skill import *
from utils.logger_helper import get_agent_by_id

# this is simply an parrot agent, no thinking, no intelligent, simply pipe human message to agent
# and pipe agent response back to human

def human_message(state):
    human_msg = True
    return human_msg

def parrot(state: NodeState) -> NodeState:
    # this function simply routes the incoming chat message, if the chat message is for
    # human, then sends it to the GUI section, (update message DB)
    # if the chat message is for agent, then sends it to the recipient agent using A2A protocol (update message DB)
    print("my twin parrot chatting...")
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        if human_message(state):
            # this is a human to agent chat message
            # loop = asyncio.get_event_loop()
            # if loop.is_running():
            #     # In this case, you can't call loop.run_until_complete directly in the main thread.
            #     # Workaround: Use "asyncio.run_coroutine_threadsafe" (if in a thread) or refactor to be async.
            #     # Example (if in a thread):
            #     future = asyncio.run_coroutine_threadsafe(
            #         agent.a2a_send_chat_message(recipient_agent, {"chat": chat}), loop)
            #     result = future.result()
            # else:
            #     # this is an agent to humanchat message
            #     ipc_api = mainwin.top_gui.get_ipc_api()
            #     await ipc_api.update_chats({"chats": [chat], "agent": agent})
            recipient_agent = next((ag for ag in mainwin.agents if "Engineering Procurement Agent" == ag.card.name), None)
            print("parrot recipient found:", recipient_agent.card.name)
            # result = await agent.a2a_send_chat_message(recipient_agent, {"chat": state["messages"][-1]})
            result = agent.a2a_send_chat_message(recipient_agent, {"chat": state["messages"][-1]})

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateMyTwinChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateMyTwinChatterSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

    return result_state

async def create_my_twin_chatter_skill(mainwin):
    try:
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        chatter_skill = EC_Skill(name="chatter for my digital twin",
                             description="chat on behalf of human.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")

        workflow = StateGraph(NodeState)
        workflow.add_node("relay", parrot)
        workflow.set_entry_point("relay")
        workflow.add_edge("relay", END)

        chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("my_twin_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateMyTwinChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateMyTwinChatterSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return chatter_skill



#
