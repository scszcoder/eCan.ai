from langgraph.constants import START, END
from prompt_toolkit import prompt
from langchain_core.prompts import ChatPromptTemplate
from agent.ec_skill import *
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.mcp.local_client import mcp_call_tool
from langgraph.prebuilt import create_react_agent


def go_to_site_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        logger.debug("about to connect to ads power:", type(state), state)

        # 安全地获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 调用工具
        tool_result = loop.run_until_complete(
            mcp_call_tool("os_connect_to_adspower", {"input": state["tool_input"]})
        )

        logger.debug("go_to_site_node tool completed:", type(tool_result), tool_result)

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
        logger.error(state["error"])
        return state


def check_captcha_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
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

        logger.debug("llm prompt ready:", prompt_messages)
        response = llm.invoke(prompt_messages)
        logger.debug("LLM response:", response)
        # Parse the response

        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        logger.debug("Raw content:", raw_content)  # Debug log

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
        state['error'] = get_traceback(e, "ErrorCheckCaptchaNode")
        logger.debug(state['error'])
        return state



def solve_captcha_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
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

        logger.debug("llm prompt ready:", prompt_messages)
        response = llm.invoke(prompt_messages)
        logger.debug("LLM response:", response)
        # Parse the response

        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        logger.debug("Raw content:", raw_content)  # Debug log

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
        state['error'] = get_traceback(e, "ErrorSolveCaptchaNode")
        logger.error(state['error'])
        return state



def check_top_categories_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
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

        return state

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorCheckTopCategoriesNode")
        logger.error(state['error'])
        return state


def check_sub_categories_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
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

        return state

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorCheckSubCategoriesNode")
        logger.error(state['error'])
        return state



def check_is_parametric_filter_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and mainwin.llm else None
        if not llm:
            raise ValueError("LLM not available in mainwin")
        user_content = """ 
                                        Given the json formated partial dom tree elements, and I want to extract available top categories that all products
                                        on digi-key are grouped into. please help figure out:
                                        - 1) whether the provided dom elements contain full or partial parametric filters, if no, go to step 2; if yes, please identify the selector type and name of the selector card element to search for on the page.
                                        - 2) if no dom element contains any seemingly full or partial parametric filters, with your best guess doesany dom element contains further divided sub-sub-categories information? If Yes, please identify the selector type and name of the element to search for the further divided sub-sub-categories info on the page.
                                        please pack the response to step 1 and 2 into the following json data format:
                                        {
                                            "parametric_filter_identifiers": [
                                                {
                                                    "selector_type": "ID|CLASS_NAME|CSS_SELECTOR|LINK_TEXT|NAME|PARTIAL_LINK_TEXT|TAG_NAME|XPATH",
                                                    "selector_name": "name string",
                                                }],
                                            "sub_sub_category_identifiers": [
                                                {
                                                    "selector_type": "ID|CLASS_NAME|CSS_SELECTOR|LINK_TEXT|NAME|PARTIAL_LINK_TEXT|TAG_NAME|XPATH",
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

        return state

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorCheckIsParametricFilterNode")
        logger.error(state['error'])
        return state


def get_user_parametric_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
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
            logger.debug("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorGetUserParametricNode")
        logger.error(state['error'])
        return state


def fill_user_parametric_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
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
            logger.debug("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorFillUserParametricNode")
        logger.error(state['error'])
        return state


def obtain_search_results_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
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
            logger.debug("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorObtainSearchResultsNode")
        logger.error(state['error'])
        return state



def final_select_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
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
            logger.debug("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorFinalSelectNode")
        logger.error(state['error'])
        return state


def check_goals_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    webdriver = mainwin.getWebDriver()
    try:
        url = state["messages"][0]
        # do final round of filtering and ranking based on original goals and user preferences
        # first do ranking select top N

        # put together summary and score card

        # create a final result greeting message

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorCheckGoalsNode")
        logger.error(state['error'])
        return state



def send_results_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    webdriver = mainwin.getWebDriver()
    try:
        url = state["messages"][0]
        # adapt results to GUI notification format.

        # send result notification to GUI

        return result_state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorSendResultsNode")
        logger.error(state['error'])
        return state



def check_done_logic(state: NodeState) -> str:
    try:
        return "final_select" if state.condition else "check_is_parametric_filter"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorCheckDoneLogic")
        logger.error(state['error'])
        return "Error"


def check_captcha_logic(state: NodeState) -> str:
    try:
        return "solve_captcha" if state.condition else "check_sub_categories"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorCheckCaptchaLogic")
        logger.error(state['error'])
        return "error"

async def create_search_digi_key_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_skill = EC_Skill(
            name="meca search digi-key web site",
            description="help search a part/component or a product on digi-key website.",
            source="code"  # Mark as code-generated skill
        )        
        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        # all_tools = mcp_client.get_tools()
        # web_search_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        # web_search_tools = [t for t in all_tools if t.name in web_search_tool_names]
        # print("searcher # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])
        # Use mainwin's llm object instead of hardcoded ChatOpenAI
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
        def route_logic(state: NodeState) -> str:
            if state["resolved"] or state["retries"] >= 5:
                return END
            return "llm_loop"

        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState)
        workflow.add_node("go to digi-key site", go_to_site_node)
        workflow.set_entry_point("go to digi-key site")
        # workflow.add_node("goto_site", goto_site)

        workflow.add_node("check_captcha", check_captcha_node)
        workflow.add_conditional_edges("check_captcha", check_captcha_logic, ["solve_captcha", "check_sub_categories"])

        workflow.add_node("solve_captcha", solve_captcha_node)

        workflow.add_node("check_top_categories", check_top_categories_node)

        workflow.add_node("check_sub_categories", check_sub_categories_node)

        #now starts the loop.

        workflow.add_node("check_is_parametric_filter", check_is_parametric_filter_node)

        workflow.add_node("get_user_parametric", get_user_parametric_node)
        workflow.add_node("fill_user_parametric", fill_user_parametric_node)
        workflow.add_node("obtain_search_results", obtain_search_results_node)
        workflow.add_node("check_goals", check_goals_node)
        workflow.add_node("final_select", final_select_node)
        workflow.add_node("send_results", send_results_node)
        workflow.add_edge("send_results", END)

        workflow.add_edge("go to digi-key site", "check_captcha")

        workflow.add_conditional_edges("check_goals", check_done_logic, ["check_is_parametric_filter", "final_select"])

        searcher_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
         # type: ignore[attr-defined]
        logger.debug("search_digi_key_skill build is done!")
        return searcher_skill
    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateSearchDigiKeySkill")
        logger.error(err_trace)
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


prompt12 = ChatPromptTemplate.from_messages([
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