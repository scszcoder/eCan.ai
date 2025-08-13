from langgraph.constants import START, END
from bot.Logger import *
from agent.ec_skill import *
from bot.adsAPISkill import startADSWebDriver, queryAdspowerProfile
from bot.seleniumSkill import execute_js_script
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_agent_by_id, get_traceback
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.search_parts.search_parts_testdata import SEARCH_PARTS_RESULTS
import re
from agent.ec_skills.search_parts.decision_utils import *




def go_to_next_site_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    try:
        print("about to connect to ads power:", type(state), state)

        # 安全地获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 调用工具
        tool_result = loop.run_until_complete(
            mcp_call_tool("in_browser_open_tab", {"input": state["tool_input"]})
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
        state["error"] = get_traceback(e, "ErrorGoToSiteNode")
        logger.debug(state["error"])
        return state




def send_results_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

    webdriver = mainwin.webdriver
    try:
        # use A2A to send results to chatter process, and chatter will send
        # results to supervisor via chat.
        state["result"] = SEARCH_PARTS_RESULTS
        print("about to send this result: ", state["result"])
        # adapt results to GUI notification format.
        agent.a2a_send_chat_message(twin_agent, {"type": "search results", "content": state["result"]})
        # send result notification to GUI

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
        searcher_skill = EC_Skill(name="ecan.ai self test", description="run eCan.ai self test.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        # all_tools = mcp_client.get_tools()
        # web_search_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        # web_search_tools = [t for t in all_tools if t.name in web_search_tool_names]
        # print("searcher # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])

        web_search_tools = []
        searcher_agent = create_react_agent(llm, web_search_tools)
        # Prompt Template
        prompt0 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                - given the component name, lets first try to find the product category and sub-categories that this component might belong to given 
                digi-key website's product category scheme.
            """),
            ("human", [
                {"type": "text", "text": "{input}"},
            ]),
        ])

        prompt1 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                - given the scraped search result web page dom tree, please filter out the products in the search results that don't fit the provided requirement.
                - please return a list of clickable products dom object of no more than {max_candidates}.
            """),
            ("human", [
                {"type": "text", "text": "{input}"}
            ])
        ])

        prompt1 = ChatPromptTemplate.from_messages([
            ("system", """
                        You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                        - given the scraped search result web page dom tree, please filter out the products in the search results that don't fit the provided requirement.
                        - please return a list of clickable products dom object of no more than {max_candidates}.
                    """),
            ("human", [
                {"type": "text", "text": "{input}"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
            ]),
            ("placeholder", "{messages}"),
        ])

        # Planner node
        planner_node = prompt0 | llm


        async def planner_with_image(state: NodeState):
            # Call your screenshot tool
            # REMOTE call over SSE → MCP tool
            image_b64: str = await searcher_skill.mcp_session.call_tool(
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
        workflow.add_node("go_to_next_site", go_to_next_site_node)
        workflow.set_entry_point("go_to_next_site")
        # workflow.add_node("goto_site", goto_site)

        workflow.add_node("check_captcha", check_captcha_node)

        workflow.add_node("solve_captcha", solve_captcha_node)

        workflow.add_node("search_parametric_filters", search_parametric_filters_node)

        workflow.add_node("collect_search_results", collect_search_results_node)

        #now starts the loop.
        workflow.add_node("check_goals", check_goals_node)
        workflow.add_node("final_select", final_select_node)
        workflow.add_node("send_results", send_results_node)
        workflow.add_edge("send_results", END)

        workflow.add_edge("go_to_next_site", "check_captcha")
        workflow.add_conditional_edges("check_captcha", check_captcha_logic, ["solve_captcha", "search_parametric_filters"])
        workflow.add_edge("search_parametric_filters", "collect_search_results")
        workflow.add_edge("collect_search_results", "check_goals")

        workflow.add_conditional_edges("check_goals", check_done_logic, ["go_to_next_site", "final_select"])

        self_test_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
         # type: ignore[attr-defined]
        print("self_test_skill build is done!")
        return self_test_skill
    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateSearchPartsSkill")
        logger.debug(err_trace)
        return None

#

prompt01 = ChatPromptTemplate.from_messages([
            ("system", """
                        You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                        - given user's chat message, please understand the user's intent in his/her chat message and summerize to me in
                        - from one of the following lists:
                        -  1) search a product or multiple products
                        -  2) random chat not related to finding a product or service.
                        - please return a list of clickable products dom object of no more than {max_candidates}.
                    """),
            ("human", [
                {"type": "text", "text": "{input}"},
            ]),
            ("placeholder", "{messages}"),
        ])

prompt01 = ChatPromptTemplate.from_messages([
            ("system", """
                        You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                        - given the user's chat message, and given the user is searching a product or multiple products
                        - please extract as much info as possible from the user's message and file which could be .xlsx file or image file or pdf file.
                        - and try to fill out the following json template about the target product(s).
                        - 
                    """),
            ("human", [
                {"type": "text", "text": "{input}"},
            ]),
            ("placeholder", "{messages}"),
        ])

prompt11 = ChatPromptTemplate.from_messages([
            ("system", """
                        You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                        - is this part thru-hole or surface mount?
                        - is this part an audio or acoustic device?(speaker or microphone)
                        - is this part optical device?()
                        - is this part an discrete components or integrated circuit? 
                        - is this part an image sensor
                        - is this part an power linear IC?
                        -  
                        - is this part  R(Resister), C(Capacitor), L(Inductor), Coupler, Transformer
                        - please return a list of clickable products dom object of no more than {max_candidates}.
                    """),
            ("human", [
                {"type": "text", "text": "given the browser extracted dom tree content {dome_tree}, and the goal of finding the category and subcategory of which this component belongs to, "
                                         "please tell me whether this page is the overall product category page which includes all the prouct categorities as well as the subcategories of the "
                                         "main categories. If this is the correct age, please organized the page's contents into the following json schema. "},
            ]),
        ])

