from langgraph.constants import START, END
from langgraph.prebuilt import create_react_agent
from agent.ec_skill import *
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.search_parts.search_parts_testdata import SEARCH_PARTS_RESULTS
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


def check_captcha_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    try:
        # result_state = await mainwin.mcp_client.call_tool(
        #     state.result["selected_tool"], arguments={"input": state.tool_input}
        # )

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and mainwin.llm else None
        if not llm:
            raise ValueError("LLM not available in mainwin")
        user_content = """ 
                        Given the json formated partial dom tree elements, and I want to extract available top categories that all products
                        on digi-key are grouped into. please help figure out:
                        - 1) whether the provided dom elements contain one or more top level product categories, if no, go to step 2; if yes, please identify the selector type and name of the element to search for on the page.
                        - 2) if no dom element contains any seemingly top level product categories, with your best guess is there any dom element's children elements could contain the top level product categories.
                        please pack the response to step 1 and 2 into the following json data format:
                        {
                            "top_category_identifiers": [
                                {
                                    "selector_type": "ID|CLASS_NAME|CSS_SELECTOR|LINK_TEXT|NAME|PARTIAL_LINK_TEXT|TAG_NAME|XPATH",
                                    "selector_name": "name string",
                                }],
                            "top_category_containers": [
                                {
                                    "selector_type": "CSS_SELECTOR|XPATH",
                                    "selector_name": "name string",
                                }]
                        }
                        And here is the json formated partial dom tree elements: {dome_tree}
                        """
        prompt_messages = [
            {
                "role": "system",
                "content": """
                        You're an electronics component procurement expert helping sourcing this component on digi-key website.
                        your task is to help the user navigate the digi-key website and search for a product. The search will
                        done by first identify the product's category and sub-categories and then search for the product using
                        digi-key's parametric filter search scheme, I have a set of MCP tools that can excute in browser actions
                        such as click, hover, scroll, key input, as well as building dom tree and search web elements on a page.
                        since the page contents will be changing and dynamic and could be very large to present to you in full, 
                        along the way, user will attempt to provide the following to you:
                        -  1) partial top dom elements in json fashion
                        -  2) intentions - either to find out certain structure info on the page or execute certain action on the page.
                        please return a response to user in the desired format as specified in the user prompt.
                    """
            },
            {
                "role": "user",
                "content": user_content
            }
        ]

        print("llm prompt ready:", prompt_messages)
        response = llm.invoke(prompt_messages)
        print("LLM response:", response)
        # Parse the response

        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        print("Raw content:", raw_content)  # Debug log

        # Clean up the response
        if is_json_parsable(raw_content):
            result = json.loads(raw_content)
        else:
            content = raw_content.strip('`').strip()
            if content.startswith('json'):
                content = content[4:].strip()
            # Parse the JSON
            # Convert to proper JSON string if it's a Python dict string
            if content.startswith('{') and content.endswith('}'):
                # Replace single quotes with double quotes for JSON
                content = content.replace("'", '"')
                # Convert Python's True/False to JSON's true/false
                content = content.replace("True", "true").replace("False", "false")
                if is_json_parsable(content):
                    # Return the full state with the analysis
                    result = json.loads(content)
                else:
                    result = raw_content
            else:
                result = raw_content

        return {**state, "result": result}

    except Exception as e:
        state["error"] = get_traceback(e, "ErrorCheckCaptchaNode")
        logger.debug(state["error"])
        state["condition"] = False; 
        return state



def solve_captcha_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    try:
        # result_state = await mainwin.mcp_client.call_tool(
        #     state.result["selected_tool"], arguments={"input": state.tool_input}
        # )

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and mainwin.llm else None
        if not llm:
            raise ValueError("LLM not available in mainwin")
        user_content = """ 
                        Given the json formated partial dom tree elements, and I want to extract available top categories that all products
                        on digi-key are grouped into. please help figure out:
                        - 1) whether the provided dom elements contain one or more top level product categories, if no, go to step 2; if yes, please identify the selector type and name of the element to search for on the page.
                        - 2) if no dom element contains any seemingly top level product categories, with your best guess is there any dom element's children elements could contain the top level product categories.
                        please pack the response to step 1 and 2 into the following json data format:
                        {
                            "top_category_identifiers": [
                                {
                                    "selector_type": "ID|CLASS_NAME|CSS_SELECTOR|LINK_TEXT|NAME|PARTIAL_LINK_TEXT|TAG_NAME|XPATH",
                                    "selector_name": "name string",
                                }],
                            "top_category_containers": [
                                {
                                    "selector_type": "CSS_SELECTOR|XPATH",
                                    "selector_name": "name string",
                                }]
                        }
                        And here is the json formated partial dom tree elements: {dome_tree}
                        """
        prompt_messages = [
            {
                "role": "system",
                "content": """
                        You're an electronics component procurement expert helping sourcing this component on digi-key website.
                        your task is to help the user navigate the digi-key website and search for a product. The search will
                        done by first identify the product's category and sub-categories and then search for the product using
                        digi-key's parametric filter search scheme, I have a set of MCP tools that can excute in browser actions
                        such as click, hover, scroll, key input, as well as building dom tree and search web elements on a page.
                        since the page contents will be changing and dynamic and could be very large to present to you in full, 
                        along the way, user will attempt to provide the following to you:
                        -  1) partial top dom elements in json fashion
                        -  2) intentions - either to find out certain structure info on the page or execute certain action on the page.
                        please return a response to user in the desired format as specified in the user prompt.
                    """
            },
            {
                "role": "user",
                "content": user_content
            }
        ]

        print("llm prompt ready:", prompt_messages)
        response = llm.invoke(prompt_messages)
        print("LLM response:", response)
        # Parse the response

        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        print("Raw content:", raw_content)  # Debug log

        # Clean up the response
        if is_json_parsable(raw_content):
            result = json.loads(raw_content)
        else:
            content = raw_content.strip('`').strip()
            if content.startswith('json'):
                content = content[4:].strip()
            # Parse the JSON
            # Convert to proper JSON string if it's a Python dict string
            if content.startswith('{') and content.endswith('}'):
                # Replace single quotes with double quotes for JSON
                content = content.replace("'", '"')
                # Convert Python's True/False to JSON's true/false
                content = content.replace("True", "true").replace("False", "false")
                if is_json_parsable(content):
                    # Return the full state with the analysis
                    result = json.loads(content)
                else:
                    result = raw_content
            else:
                result = raw_content

        return {**state, "result": result}

    except Exception as e:
        state["error"] = get_traceback(e, "ErrorSolveCaptchaNode")
        logger.debug(state["error"])
        return state




def search_parametric_filters_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    webdriver = mainwin.getWebDriver()
    try:
        url = state["messages"][0]
        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state["error"] = get_traceback(e, "ErrorFillUserParametricNode")
        logger.debug(state["error"])
        return state


def collect_search_results_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    webdriver = mainwin.getWebDriver()
    try:
        url = state["messages"][0]
        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state["error"] = get_traceback(e, "ErrorObtainSearchResultsNode")
        logger.debug(state["error"])
        return state



def final_select_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    webdriver = mainwin.getWebDriver()
    try:
        # score and ranking
        if state["tool_result"]:
            for part_result in state["tool_result"]:
                score = calc_overall_score(part_result)
                part_result["score"] = score

            state["tool_result"] = sorted(state["tool_result"], key=lambda x: x["score"], reverse=True)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state["error"] = get_traceback(e, "ErrorFinalSelectNode")
        logger.debug(state["error"])
        return state


def check_goals_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    if agent is None:
        state["error"] = "Agent not ready"
        return state
    mainwin = agent.mainwin
    webdriver = mainwin.getWebDriver()
    try:
        url = state["messages"][0]
        # do final round of filtering and ranking based on original goals and user preferences
        # first do ranking select top N

        # done with searching a site, so remove it
        if state["tool_input"]["sites"]:
            state["tool_input"]["sites"].pop(0)

        # set up condition flag for the branch operation
        state["condition"] = len(state["tool_input"]["sites"]) > 0

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state["error"] = get_traceback(e, "ErrorCheckGoalsNode")
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

    webdriver = mainwin.getWebDriver()
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



def check_done_logic(state: NodeState) -> str:
    try:
        cond = state.get("condition", False) if isinstance(state, dict) else False
        return "go_to_next_site" if cond else "final_select"

    except Exception as e:
        state["error"] = get_traceback(e, "ErrorCheckDoneLogic")
        logger.debug(state["error"])
        return "errot"


def check_captcha_logic(state: NodeState) -> str:
    try:
        cond = state.get("condition", False) if isinstance(state, dict) else False
        return "solve_captcha" if cond else "search_parametric_filters"

    except Exception as e:
        state["error"] = get_traceback(e, "ErrorCheckCaptchaLogic")
        logger.debug(state["error"])
        return "error"

async def create_search_parts_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_skill = EC_Skill(name="ecan.ai search parts and components web site",
                             description="help search part/components.")

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        web_search_tools = []
        searcher_agent = create_react_agent(llm, web_search_tools)
        # Prompt Template


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

        searcher_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
         # type: ignore[attr-defined]
        print("search_parts_skill build is done!")
        return searcher_skill
    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateSearchPartsSkill")
        logger.debug(err_trace)
        return None
