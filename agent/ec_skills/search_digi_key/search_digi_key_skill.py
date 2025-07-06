from bot.Logger import *
from agent.ec_skill import *
from bot.adsAPISkill import startADSWebDriver, queryAdspowerProfile
from bot.seleniumSkill import execute_js_script
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from utils.logger_helper import get_agent_by_id

# async def mcp_call_tool(mcp_client, tool_name, args):
#     async with mcp_client.session("E-Commerce Agents Service") as session:
#         print("MCP client call tool................")
#         tool_result = await session.call_tool(tool_name, args)
#         print("MCP client call tool returned................", type(tool_result), tool_result)
#         return tool_result

async def mcp_call_tool(mcp_client, tool_name, args):
    async with mcp_client.session("E-Commerce Agents Service") as session:
        print(f"MCP client calling tool: {tool_name} with args: {args}")
        try:
            # Call the tool and get the raw response
            response = await session.call_tool(tool_name, args)
            print(f"Raw response type: {type(response)}")
            print(f"Raw response: {response}")

            # If the response is a CallToolResult with an error, return the error
            if hasattr(response, 'isError') and response.isError:
                error_text = str(response.content[0].text) if hasattr(response,
                                                                      'content') and response.content else "Unknown error"
                return {"error": error_text}

            # If we got a successful CallToolResult with content, extract the text
            if hasattr(response, 'content') and response.content:
                content = response.content[0]
                if hasattr(content, 'text'):
                    return {"content": [{"type": "text", "text": content.text}], "isError": False}
                return {"content": [{"type": "text", "text": str(content)}], "isError": False}

            # If it's already a dictionary, return it as is
            if isinstance(response, dict):
                return response

            # For any other type, convert to string and return as content
            return {"content": [{"type": "text", "text": str(response)}], "isError": False}

        except Exception as e:
            error_msg = f"Error calling {tool_name}: {str(e)}"
            print(error_msg)
            return {"content": [{"type": "text", "text": error_msg}], "isError": True}


def go_to_site_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        print("about to connect to ads power:", type(state), state)
        loop = asyncio.get_event_loop()
    except RuntimeError as e:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tool_result = loop.run_until_complete(mcp_call_tool(mainwin.mcp_client,"os_connect_to_adspower", args={"input": state["tool_input"]} ))
        # tool_result = await mainwin.mcp_client.call_tool(
        #     "os_connect_to_adspower", arguments={"input": state.tool_input}
        # )
        print("tool completed:", type(tool_result), tool_result)
        if "completed" in tool_result["content"][0]["text"]:
            state.result = tool_result
        else:
            state.error = tool_result
        return state
    else:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorToolNode:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorToolNode: traceback information not available:" + str(e)
        log3(ex_stat)
        state.error = ex_stat
        return state


async def llm_with_tool_node(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        result_state = await mainwin.mcp_client.call_tool(
            state.result["selected_tool"], arguments={"input": state.tool_input}
        )

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14")

        prompt_messages = [
            {
                "role": "system",
                "content": "You are an expert procurement assistant trying to help the user find a component for his project."
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
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorToolNode:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorToolNode: traceback information not available:" + str(e)
        log3(ex_stat)
        state.error = ex_stat
        return state


def extract_web_page(state: NodeState) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        loop = asyncio.get_event_loop()
        tool_result = loop.run_until_complete(mainwin.mcp_client.call_tool(
            "in_browser_build_dom_tree", arguments={"input": state.tool_input}
        ))

        # tool_result = await mainwin.mcp_client.call_tool(
        #     "in_browser_build_dom_tree", arguments={"input": state.tool_input}
        # )

        print("tool completed:", tool_result)
        if "completed" in tool_result["content"][0]["text"]:
            state.result = tool_result
        else:
            state.error = tool_result
        return state
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorToolNode:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorToolNode: traceback information not available:" + str(e)
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
    webdriver = mainwin.webdriver
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


async def create_search_digi_key_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_skill = EC_Skill(name="meca search digi-key web site",
                             description="help search a part/component or a product on digi-key website.")

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
        workflow.add_node("go to digi-key site", go_to_site_node)
        workflow.set_entry_point("go to digi-key site")
        # workflow.add_node("goto_site", goto_site)

        workflow.add_node("extract_web_page", extract_web_page)

        workflow.add_node("get_next_action", get_next_action)


        workflow.add_edge("go to digi-key site", "extract_web_page")
        workflow.add_edge("extract_web_page", "get_next_action")

        workflow.add_conditional_edges("get_next_action", route_logic, ["extract_web_page", END])

        searcher_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
         # type: ignore[attr-defined]
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