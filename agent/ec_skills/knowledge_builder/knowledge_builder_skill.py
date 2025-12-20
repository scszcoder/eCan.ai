

from agent.ec_skill import NodeState
from utils.logger_helper import get_traceback, logger_helper as logger
from agent.agent_service import get_agent_by_id
import time


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
        state.error = get_traceback(e, "ErrorCheckTopCategoriesNode")
        logger.debug(state.error)
        return state


def check_sub_categories_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and hasattr(mainwin, 'llm') and mainwin.llm else None
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
        state.error = get_traceback(e, "ErrorCheckSubCategoriesNode")
        logger.debug(state.error)
        return state



def check_is_parametric_filter_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and hasattr(mainwin, 'llm') and mainwin.llm else None
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
        state.error = get_traceback(e, "ErrorCheckIsParametricFilterNode")
        logger.debug(state.error)
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
            print("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state.error = get_traceback(e, "ErrorGetUserParametricNode")
        logger.debug(state.error)
        return state