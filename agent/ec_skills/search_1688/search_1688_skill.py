
from agent.ec_skill import *

def check_browser_and_drivers(state: NodeState) -> NodeState:
    agent = state["messages"][0]
    mainwin = agent.mainwin
    webdriver = mainwin.default_webdriver
    try:
        url = state["input"]["url"]
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

        result_state =  NodeState(input=input_text, messages=[HumanMessage(content=input_text)], retries=0, goals=[], resolved=False)

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


def goto_site(state: NodeState) -> NodeState:
    agent = state["messages"][-1]
    mainwin = agent.mainwin
    webdriver = mainwin.default_webdriver
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

        result_state = NodeState(input=input_text, messages=[HumanMessage(content=input_text)], retries=0, goals=[],
                             resolved=False)
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
    agent = state["messages"][-1]
    mainwin = agent.mainwin
    webdriver = mainwin.default_webdriver
    try:
        url = state["messages"][0]
        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")


        new_state = await mainwin.browser_context.get_state()
        new_selector_map = new_state.selector_map

        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        result_state = NodeState(input=input_text, messages=[HumanMessage(content=input_text)], retries=0, goals=[],
                             resolved=False)
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


def get_next_action(state: NodeState) -> NodeState:
    agent = state["messages"][-1]
    mainwin = agent.mainwin
    webdriver = mainwin.default_webdriver
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

        result_state = NodeState(input=input_text, messages=[HumanMessage(content=input_text)], retries=0, goals=[],
                             resolved=False)

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

        await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        all_tools = mcp_client.get_tools()
        web_search_tool_names = ['reconnect_wifi', 'mouse_click', 'screen_capture', 'screen_analyze']
        web_search_tools = [t for t in all_tools if t.name in web_search_tool_names]
        print("searcher # tools ", len(all_tools), type(all_tools[-1]), all_tools[-1])
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
        workflow = StateGraph(NodeState)
        workflow.add_node("check_browser", check_browser_and_drivers)
        workflow.set_entry_point("check_browser")
        workflow.add_node("goto_site", goto_site)

        workflow.add_node("extract_web_page", extract_web_page)

        workflow.add_node("get_next_action", get_next_action)


        workflow.add_edge("check_browser", "goto_site")
        workflow.add_edge("goto_site", "extract_web_page")
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
        mainwin.showMsg(ex_stat)
        return None

    return searcher_skill



#
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