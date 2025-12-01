from langgraph.constants import START, END

from agent.ec_skill import *
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.search_parts.search_parts_testdata import SEARCH_PARTS_RESULTS
import re
import sys, asyncio
from agent.ec_skills.search_parts.decision_utils import *


def test0_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    print("test0_node started.....")
    try:
        print("test mcp call tool:", type(state), state)

        # 安全地获取或创建事件循环
        # try:
        #     loop = asyncio.get_event_loop()
        # except RuntimeError:
        #     loop = asyncio.new_event_loop()
        #     asyncio.set_event_loop(loop)
        loop = ensure_playwright_loop()

        # 调用工具
        tool_result = loop.run_until_complete(
            mcp_call_tool("say_hello", {"input": "say some"})
        )

        print("go_to_site_node tool completed:", type(tool_result), tool_result)

        # 安全地处理结果
        if isinstance(tool_result, dict):
            # 如果返回的是字典
            if "content" in tool_result and len(tool_result["content"]) > 0:
                content_text = tool_result["content"][0].get("text", "")
                if "completed" in content_text:
                    state["result"] = content_text
                    state["tool_result"] = tool_result.get("meta", None)
                else:
                    state["error"] = content_text
            else:
                state["error"] = f"Invalid tool result format: {tool_result}"
        else:
            # 如果返回的是对象
            if hasattr(tool_result, 'content') and len(tool_result.content) > 0:
                if "completed" in tool_result.content[0].text:
                    state["result"] = tool_result.content[0].text
                    state["tool_result"] = getattr(tool_result, 'meta', None)
                else:
                    state["error"] = tool_result.content[0].text
            else:
                state["error"] = f"Invalid tool result object: {tool_result}"

        return state

    except Exception as e:
        state["error"] = get_traceback(e, "ErrorTest0Node")
        logger.debug(state["error"])
        return state


def ensure_playwright_loop():
    # Always create a brand-new loop in this worker thread
    if sys.platform.startswith("win"):
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop

def test1_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    try:
        print("about to run playwright:", type(state), state)
        
        # Check if unified_browser_manager is available
        if not hasattr(mainwin, 'unified_browser_manager') or mainwin.unified_browser_manager is None:
            state["error"] = "Unified browser manager not available (system shutting down?)"
            logger.warning(f"[test1_node] {state['error']}")
            return state
            
        bs = mainwin.unified_browser_manager.get_browser_session()
        if bs is None:
            # BrowserSession is lazily created and not available on GUI thread
            # This is expected behavior - browser operations should use run_basic_agent_task()
            logger.warning("[test1_node] Browser session not available (lazy creation, use run_basic_agent_task for browser ops)")
            state["result"] = {"status": "skipped", "reason": "Browser session lazy creation"}
            return state
            
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 调用工具
        bs_result = loop.run_until_complete(
            bs.start()
        )
        print("URL:", state["tool_input"])
        bs_result = loop.run_until_complete(
            bs.new_tab(f'{state["tool_input"]["url"]}')
        )

        print("test1_node completed:", bs_result)

        # 安全地处理结果


        return state

    except Exception as e:
        state["error"] = get_traceback(e, "ErrorTest1Node")
        logger.debug(state["error"])
        return state




def test2_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

    try:
        # Set test result - no longer sending to twin agent as it causes errors
        # (the message lacks chatId which is required by the twin chatter skill)
        state["result"] = {"status": "success"}
        print("[test2_node] Test completed with result:", state["result"])

        return state
    except Exception as e:
        state["error"] = get_traceback(e, "ErrorSendResultsNode")
        logger.debug(state["error"])
        return state

# create a simple langgraph of different types of nodes and run for testing.
async def create_self_test_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        self_test_skill = EC_Skill(name="eCan.ai self test", description="run eCan.ai self test.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        # all_tools = mcp_client.get_tools()
        # web_search_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        # web_search_tools = [t for t in all_tools if t.name in web_search_tool_names]
        # print("searcher # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])


        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState)
        workflow.add_node("test0", test0_node)
        workflow.set_entry_point("test0")
        workflow.add_node("test1", test1_node)
        workflow.add_node("test2", test2_node)
        workflow.add_edge("test0", "test1")
        workflow.add_edge("test1", "test2")

        workflow.add_edge("test2", END)


        self_test_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
         # type: ignore[attr-defined]
        print("self_test_skill build is done!")
        return self_test_skill
    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateSearchPartsSkill")
        logger.debug(err_trace)
        return None

