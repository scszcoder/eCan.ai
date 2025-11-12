from prompt_toolkit import prompt
from agent.ec_skill import *
from bot.adsAPISkill import startADSWebDriver, queryAdspowerProfile
from bot.seleniumSkill import execute_js_script
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from agent.agent_service import get_agent_by_id
from langgraph.prebuilt import create_react_agent
from langgraph.graph import END, StateGraph, START
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from mcp.client.session import ClientSession
import json
import time
import traceback
def check_browser_and_drivers(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    webdriver_path = mainwin.getWebDriverPath()

    print("inital state:", state)
    try:
        url = state["attributes"]["url"]
        # global ads_config, local_api_key, local_api_port, sk_work_settings
        ads_port = mainwin.getADSSettings().get('ads_port', '50325')
        ads_api_key = mainwin.getADSSettings().get('ads_api_key', '')
        ads_chrome_version = mainwin.getADSSettings().get('chrome_version', '120')
        scraper_email = mainwin.getADSSettings().get("default_scraper_email", "")
        web_driver_options = ""
        print('check_browser_and_drivers:', 'ads_port:', ads_port, 'ads_api_key:', ads_api_key, 'ads_chrome_version:', ads_chrome_version)
        profiles = queryAdspowerProfile(ads_api_key, ads_port)
        loaded_profiles = {}
        for profile in profiles:
            loaded_profiles[profile['username']] = {"uid": profile['user_id'], "remark": profile['remark']}

        ads_profile_id = loaded_profiles[scraper_email]['uid']
        ads_profile_remark = loaded_profiles[scraper_email]['remark']
        print('ads_profile_id, ads_profile_remark:', ads_profile_id, ads_profile_remark)

        webdriver, result = startADSWebDriver(ads_api_key, ads_port, ads_profile_id, webdriver_path, web_driver_options)

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

        mainwin.setWebDriver(webdriver)
        # set up output.
        result_state =  NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckBrowserAndDrivers:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckBrowserAndDrivers: traceback information not available:" + str(e)
        log3(ex_stat)


def goto_site(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        url = state["attributes"]["url"]
        webdriver = mainwin.getWebDriver()
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
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGoToSite:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGoToSite: traceback information not available:" + str(e)
        log3(ex_stat)



async def extract_web_page(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        webdriver = mainwin.getWebDriver()
        script = mainwin.load_build_dom_tree_script()
        # print("dom tree build script to be executed", script)
        target = None
        domTree = execute_js_script(webdriver, script, target)
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print("obtained dom tree:", domTree)
        with open("domtree.json", 'w', encoding="utf-8") as f:
            json.dump(domTree, f, ensure_ascii=False, indent=4)
            # self.rebuildHTML()
            f.close()

        state.result = domTree
        state.error = ""            # clear error
        time.sleep(1)

        return state

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractWebPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractWebPage: traceback information not available:" + str(e)
        log3(ex_stat)
        state.error = ex_stat
        return state



async def search_product(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        webdriver = mainwin.getWebDriver()
        # assuming driver is already created and points to the page
        input_box = webdriver.find_element(By.ID, "alisearch-input")
        input_box.clear()
        search_phrase = state.attributes["search_phrase"]
        input_box.send_keys(search_phrase)
        input_box.send_keys(Keys.RETURN)  # if you want to simulate pressing Enter

        time.sleep(3)
        state.error = ""

        return state

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractWebPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractWebPage: traceback information not available:" + str(e)
        log3(ex_stat)
        state.error = ex_stat
        return state


async def review_search_results(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        webdriver = mainwin.getWebDriver()
        # assuming driver is already created and points to the page
        input_box = webdriver.find_element(By.ID, "alisearch-input")
        input_box.clear()
        search_phrase = state.attributes["search_phrase"]
        input_box.send_keys(search_phrase)
        input_box.send_keys(Keys.RETURN)  # if you want to simulate pressing Enter

        time.sleep(3)
        state.error = ""

        return state

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractWebPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractWebPage: traceback information not available:" + str(e)
        log3(ex_stat)
        state.error = ex_stat
        return state



async def review_product_details(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        webdriver = mainwin.getWebDriver()
        # assuming driver is already created and points to the page
        input_box = webdriver.find_element(By.ID, "alisearch-input")
        input_box.clear()
        search_phrase = state.attributes["search_phrase"]
        input_box.send_keys(search_phrase)
        input_box.send_keys(Keys.RETURN)  # if you want to simulate pressing Enter

        time.sleep(3)
        state.error = ""

        return state

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractWebPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractWebPage: traceback information not available:" + str(e)
        log3(ex_stat)
        state.error = ex_stat
        return state


def get_next_action(state: NodeState) -> NodeState:
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
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGoToSite:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGoToSite: traceback information not available:" + str(e)
        log3(ex_stat)


async def create_search_1688_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_skill = EC_Skill(name="meca search 1688 web site",
                             description="help search a part/component or a product on 1688 website.")

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
                - given the parameters, please check against our knowledge base to check whether additional parameters or selection criteria needed from the user, if so, prompt user with questions to get the info about the additional parameters or criteria.
                - If all required parameters are collected, please generate a long tail search term for components search site: {site_url}
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
                - given the scraped search result web page dom tree, please filter out the products in the search results that don't fit the provided requirement.
                - please return a list of clickable products dom object of no more than {max_candidates}.
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


        def initial_state(input_text: str) -> NodeState:
            return {"input": input_text, "messages": [HumanMessage(content=input_text)], "retries": 0, "resolved": False}

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
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("check_browser", check_browser_and_drivers)
        workflow.set_entry_point("check_browser")
        # workflow.add_node("goto_site", goto_site)

        workflow.add_node("extract_web_page", extract_web_page)

        workflow.add_node("get_next_action", get_next_action)


        workflow.add_edge("check_browser", "extract_web_page")
        workflow.add_edge("extract_web_page", "get_next_action")

        workflow.add_conditional_edges("get_next_action", route_logic, ["extract_web_page", END])

        searcher_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        searcher_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("search1688_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateSearch1688Skill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateSearch1688Skill: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None

    return searcher_skill



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
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
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
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
            ]),
            ("placeholder", "{messages}"),
        ])

prompt11 = ChatPromptTemplate.from_messages([
            ("system", """
                        You're an electronics component procurement expert helping sourcing this component {part} with the user provided parameters in JSON format.
                        - is this part passive or active?
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
                {"type": "text", "text": "{input}"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image_b64}"}},
            ]),
            ("placeholder", "{messages}"),
        ])