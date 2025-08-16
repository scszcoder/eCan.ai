from typing import TypedDict
import uuid

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt, Command
from langgraph.func import entrypoint, task
from langgraph.graph import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages.utils import (
    # highlight-next-line
    trim_messages,
    # highlight-next-line
    count_tokens_approximately
# highlight-next-line
)
from langgraph.prebuilt import create_react_agent
from langmem.short_term import SummarizationNode
from langgraph.store.base import BaseStore

from scipy.stats import chatterjeexi
import io
import os
import base64

from agent.chats.chat_utils import a2a_send_chat
from agent.ec_skills.file_utils.file_utils import extract_file_text
from bot.Logger import *
from agent.ec_skill import *
from utils.logger_helper import get_agent_by_id, get_traceback
from utils.logger_helper import logger_helper as logger
from agent.mcp.local_client import mcp_call_tool
from agent.chats.tests.test_notifications import sample_metrics_0
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts




def _ensure_context(ctx: WorkFlowContext) -> WorkFlowContext:
    """Get params that configure the search algorithm."""
    if ctx.this_node:
        if ctx.this_node.get("name", ""):
            ctx.this_node = ctx.this_node
    else:
        ctx.node = {"name": ""}

# this node will call ecan.ai api to obtain parametric filters of the searched components
def get_user_parametric_node(state: NodeState) -> NodeState:
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
            logger.debug("open URL: " + url)

        result_state = NodeState(messages=state["messages"], retries=0, goals=[], condition=False)

        return result_state
    except Exception as e:
        state.error = get_traceback(e, "ErrorGetUserParametricNode")
        logger.error(state.error)
        return state

def human_approval(state: NodeState) -> Command[Literal["some_node", "another_node"]]:
    is_approved = interrupt(
        {
            "question": "Is this correct?",
            # Surface the output that should be
            # reviewed and approved by the human.
            "llm_output": state["llm_output"]
        }
    )

    if is_approved:
        return Command(goto="some_node")
    else:
        return Command(goto="another_node")

def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    logger.debug("pend_for_human_input_node:", state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", None)
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = None
        notification = None

    interrupted = interrupt( # (1)!
        {
            "prompt_to_human": state["result"], # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )
    logger.debug("node running:", runtime.context.current_node)
    logger.debug("interrupted:", interrupted)
    return {
        "pended": interrupted # (3)!
    }

def human_review_and_edit(state: State):
    ...
    result = interrupt(
        # Interrupt information to surface to the client.
        # Can be any JSON serializable value.
        {
            "task": "Review the output from the LLM and make any necessary edits.",
            "llm_generated_summary": state["llm_generated_summary"]
        }
    )

    # Update the state with the edited text
    return {
        "llm_generated_summary": result["edited_text"]
    }


def verify_resolved(state: NodeState) -> NodeState:
    last_msg = state["messages"][-1].content.lower()
    if "resolved" in last_msg:
        state["resolved"] = True
    else:
        state["retries"] += 1
    return state


def any_unknown_part_numbers(state: NodeState) -> NodeState:
    last_msg = state["messages"][-1].content.lower()
    if "resolved" in last_msg:
        state["resolved"] = True
    else:
        state["retries"] += 1
    return state

def any_attachment(state: NodeState) -> str:
    logger.debug("go to digi-key site:", state)
    return state


def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("chat_or_work input:", state)
    if isinstance(state['result'], dict):
        state_output = state['result']
        if state_output.get("job_related", False):
            return "do_work"
        else:
            return "chat_back"
    else:
        return "chat_back"

def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("is_preliminary_component_info_ready input:", state)
    if state['condition']:
        return "preliminary_component_info_ready"
    else:
        return "query_human"

def all_requirement_filled(state: NodeState) -> str:
    logger.debug("all_requirement_filled:", state)
    if state["all_requirement_filled"]:
        return True
    return False

async def ask_cloud_expert_for_search_parameters(state: NodeState) -> str:
    logger.debug("ask_cloud_expert_for_search_parameters:", state)
    return ""

async def ask_cloud_expert_for_search_sites(state: NodeState) -> str:
    logger.debug("ask_cloud_expert_for_search_sites:", state)
    return ""

def read_attachments_node(state: NodeState) -> str:
    logger.debug("read attachments:", state)
    return {}

def eval_basic_info_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:

    return state

def debug_node(state: NodeState) -> NodeState:
    logger.debug("Debug node state:", state)
    return state



# for now, the raw files can only be pdf, PNG(.png) JPEG (.jpeg and .jpg) WEBP (.webp) Non-animated GIF (.gif),
# .wav (.mp3) and .mp4
def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug("in llm_node_with_raw_files....")
    user_input = state.get("input", "")
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    logger.debug("run time:", runtime)
    current_node = runtime.context["this_node"].get("name")
    # print("current node:", current_node)
    nodes = [{"askid": "skid0", "name": current_node}]
    nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, nodes)
    logger.debug("networked prompts:", nodes_prompts)
    node_prompt = nodes_prompts[0]

    attachments = state.get("attachments", [])
    user_content = []
    logger.debug("node running:", runtime)
    logger.debug("LLM input text:", user_input)
    # Add user text
    user_content.append({"type": "text", "text": user_input})

    # Add all attachments in supported format
    for att in attachments:
        fname = att["filename"].lower()

        mime_type = att.get("mime_type", "").lower()
        logger.debug(f"Processing file: {fname} (MIME: {mime_type})")

        # Skip if no file data
        if not att.get("file_data"):
            logger.debug(f"Skipping empty file: {fname}")
            continue

        data = att["file_data"]

        # file_text = extract_file_text(data, fname)

        # Handle image files (PNG, JPG, etc.)
        if mime_type.startswith('image/'):
            logger.debug(f"Processing image file: {fname}")
            file_data = data if isinstance(data, str) else base64.b64encode(data).decode('utf-8')
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{file_data}"
                    # "detail": "auto"
                }
            })

        # Handle PDF files
        elif mime_type == 'application/pdf':
            logger.debug(f"Processing PDF file: {fname}")
            # For PDFs, we'll just note its existence since we can't process it directly
            user_content.append({
                "type": "text",
                "text": f"[PDF file: {fname} - PDF content cannot be processed directly]"
            })

        # Handle audio files
        elif mime_type.startswith('audio/'):
            logger.debug(f"Processing audio file: {fname}")
            # For audio files, we'll just note its existence
            user_content.append({
                "type": "text",
                "text": f"[Audio file: {fname} - Audio content cannot be processed directly]"
            })

        # Handle other file types
        else:
            logger.warning(f"Unsupported file type: {fname} ({mime_type})")
            # user_content.append({
            #     "type": "text",
            #     "text": f"[File: {fname} - This file type is not supported for direct analysis]"
            # })



    llm = ChatOpenAI(model="gpt-4.1-2025-04-14")

    prompt_messages = [
        {
            "role": "system",
            "content": "You are an electronics component procurement expert helping sourcing and procuring components. Please carefully answer the user's request."
        },
        {
            "role": "user",
            "content": user_content
        }
    ]

    logger.debug("chat node: llm prompt ready:", node_prompt)
    response = llm.invoke(node_prompt)
    logger.debug("chat node: LLM response:", response)
    # Parse the response
    try:
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
        logger.error(f"Error parsing LLM response: {e}")
        logger.error(f"Raw response: {response}")
        return {**state, "analysis": {"job_related": False}}


def pre_model_hook(state):
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=384,
        start_on="human",
        end_on=("human", "tool"),
    )
    # highlight-next-line
    return {"llm_input_messages": trimmed_messages}

def query_human_about_components_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    return state

def check_preliminary_component_info_ready_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    return state

def query_component_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    try:
        logger.debug("about to query components:", type(state), state)
        loop = asyncio.get_event_loop()
    except RuntimeError as e:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tool_result = loop.run_until_complete(mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]} ))
            # tool_result = await mainwin.mcp_client.call_tool(
            #     "os_connect_to_adspower", arguments={"input": state.tool_input}
            # )
            logger.debug("query components completed:", type(tool_result), tool_result)
            if "completed" in tool_result.content[0].text:
                state.result = tool_result.content[0].text
                state.tool_result = getattr(tool_result, 'meta', None)
            else:
                state["error"] = tool_result.content[0].text

            return state
        except Exception as e:
            state['error'] = get_traceback(e, "ErrorGoToSiteNode0")
            logger.error(state['error'])
            return state
        finally:
            loop.close()
    else:
        try:
            tool_result = loop.run_until_complete(
                mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]}))
            # tool_result = await mainwin.mcp_client.call_tool(
            #     "os_connect_to_adspower", arguments={"input": state.tool_input}
            # )
            logger.debug("old loop query components tool completed:", type(tool_result), tool_result)
            if "completed" in tool_result.content[0].text:
                state.result = tool_result.content[0].text
                state.tool_result = getattr(tool_result, 'meta', None)
            else:
                state["error"] = tool_result.content[0].text

            return state
        except Exception as e:
            state['error'] = get_traceback(e, "ErrorGoToSiteNode1")
            logger.error(state['error'])
            return state

# this function takes the prompt generated by LLM from the previous node and puts ranking method template
# into the right place. This way, the correct data can be passed onto the GUI side of the chat interface.
def prep_ranking_method_template_node(state: NodeState) -> NodeState:
    try:
        ranking_method_template = sample_metrics_0
        if state.get("tool_result", None):
            state["tool_result"]["qa_form_to_human"] = ranking_method_template
        # highlight-next-line
        else:
            state["tool_result"] = {"qa_form_to_human": ranking_method_template}
        return state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorPrepRankingMethodTemplateNode")
        logger.error(state['error'])
        return state


def prep_component_specs_qa_form_node(state: NodeState) -> NodeState:
    try:
        component_specs_qa_form = state.get("result", {})
        if state.get("tool_result", None):
            state["tool_result"]["qa_form_to_human"] = component_specs_qa_form
        # highlight-next-line
        else:
            state["tool_result"] = {"qa_form_to_human": component_specs_qa_form}
        return state
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorPrepComponentSpecsQaFormNode")
        logger.error(state['error'])
        return state


def run_search_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    logger.debug("run_search_node:", state)

    # send self a message to trigger the real component search work-flow
    result = self_agent.a2a_send_chat_message(self_agent, {"message": "search_parts_request", "params": state.attributes})
    state.result = result
    return state

def show_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    """显示搜索结果"""
    logger.debug("show_results_node:", state)

    # 获取搜索结果
    result = state.get("result", {})

    # 格式化结果显示给用户
    if result:
        # 将结果添加到消息中，以便用户可以看到
        from langchain_core.messages import AIMessage
        result_message = AIMessage(content=f"搜索完成！找到以下结果：\n{result}")
        state["messages"].append(result_message)
    else:
        from langchain_core.messages import AIMessage
        result_message = AIMessage(content="搜索完成，但没有找到相关结果。")
        state["messages"].append(result_message)

    return state

# summarization_node = SummarizationNode(
#     token_counter=count_tokens_approximately,
#     model=model,
#     max_tokens=384,
#     max_summary_tokens=128,
#     output_messages_key="llm_input_messages",
# )



async def create_search_parts_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_chatter_skill = EC_Skill(name="chatter for ecan.ai search parts and components web site",
                             description="chat with human or other agents to help search a part/component or a product on 1688 website.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.5)
        logger.debug("llm loaded:", llm)
        prompt0 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing and procuring components, you job is to chat with your human boss to collect all the requirements for sourcing this component and distill all requirement information in a JSON format.
                 Of course you can chat with your human boss on any topic, but you should first distinguish whether the current chat message from human boss is directly related to sourcing components or not. if it has nothing to do with the job, or simply
                 showing the intention of trying to source components without revealing any of the actual component information, like a component name (for example, a resistor or a regulator or a variable capacitor etc.), you should return a json in the form of {{'job_related': false}}, 
                 otherwise you should return a json in the form of {{'job_related': true}}.
            """),
            ("human", "{input}")
        ])

        def process_chat(state: NodeState) -> NodeState:
            # Get the last message (the actual user input)
            last_message = state["messages"][-1]

            # Format the prompt with just the message content
            last_message = "how are you"
            messages = prompt0.invoke({"input": last_message})
            logger.debug("LLM prompt:", messages)
            # Call the LLM
            response = llm.invoke(messages)

            logger.debug("LLM response:", response)
            # Parse the response
            try:
                import json
                import ast  # Add this import at the top of your file

                # Extract content from AIMessage if needed
                content = response.content if hasattr(response, 'content') else str(response)
                logger.debug("Raw content:", content)  # Debug log

                # Clean up the response
                content = content.strip('`').strip()
                if content.startswith('json'):
                    content = content[4:].strip()
                # Parse the JSON
                # Convert to proper JSON string if it's a Python dict string
                if content.startswith('{') and content.endswith('}'):
                    # Replace single quotes with double quotes for JSON
                    content = content.replace("'", '"')
                    # Convert Python's True/False to JSON's true/false
                    content = content.replace("True", "true").replace("False", "false")

                # Return the full state with the analysis
                result = json.loads(content)
                return {**state, "result": result}
            except Exception as e:
                logger.error(f"Error parsing LLM response: {e}")
                logger.error(f"Raw response: {response}")
                return {**state, "analysis": {"job_related": False}}

        # initial classification node

        prompt_random_chat = ChatPromptTemplate.from_messages([
            ("system", """
                You're a personal assistant, given a chat message sequence, please respond to the latest chat message to your best effort.
            """),
            ("human", "{input}")
        ])

        def chat_back_node(state: NodeState, *, runtime: Runtime[WorkFlowContext], store: BaseStore) -> NodeState:
            # Get the last message (the actual user input)
            last_message = state["messages"][-1]
            logger.debug("gen_chat_back runtime:", runtime)

            # Format the prompt with just the message content
            messages = prompt_random_chat.invoke({"input": last_message})
            logger.debug("chat back LLM prompt:", messages)
            # Call the LLM
            response = llm.invoke(messages)

            logger.debug("chat back LLM response:", response)
            # Parse the response
            try:
                import json
                import ast  # Add this import at the top of your file

                # Extract content from AIMessage if needed
                content = response.content if hasattr(response, 'content') else str(response)
                logger.debug("Raw content:", content)  # Debug log

                state["messages"].append(content)
                # Return the full state with the analysis
                return {**state, "result": content}
            except Exception as e:
                logger.error(f"Error parsing LLM response: {e}")
                logger.error(f"Raw response: {response}")
                return {**state, "analysis": {"job_related": False}}



        prompt2 = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message,  did the human boss provided an attached document? please answer in json format: {'with_attachment': true/false, 'attachment_files': [list of file names] }.
            """),
            ("human", "{input}")
        ])

        # initial classification node
        check_attachment_node = prompt2 | llm



        prompt_check_bom_components = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message,  try to understand it and let me know in json format that whether the human boss provided a pasted BOM text or simply a list of component names of which the human boss want to source. please answer in json format {'with_attachment': true/false, 'bom': true/false, 'num_components': int, 'components': [list of component names]}.
            """),
            ("human", "{input}")
        ])

        # initial classification node
        check_bom_components_node = prompt_check_bom_components | llm

        prompt_check_product_application = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message, did human boss explain or mention the name of the product or an application that the components will reside in? please answer in json format: {'product_app_specified': true/false, 'product_app': ['list of products or apps, empty if not specified']}.
            """),
            ("human", "{input}")
        ])

        # initial classification node
        check_product_application_node = prompt_check_product_application | llm

        prompt2C = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message, did human boss provide the part number of the component being searched (unless they're passive commodity components like a resistor, capacitor etc.) please answer in json format: {'part_number_or_passives': ['list of part numbers'], 'part_number_unknown': ['list of component names mentioned']} ?.
            """),
            ("human", "Question: {user_input}\n\n"
                         "Files:\n{file_list}\n\n"
                         "File Contents:\n{file_contents}")
        ])

        prompt_request_product_app_usage = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the information that the human boss provided so far about the component he is looking for, please generate a query prompt to get him/her to answer to gather more info about the component. First, if the component's related product or application is not provided, 
                please include a request in the resulting prompt to ask human boss about the product or application of this component. Also don't forget to mention that human boss can tell you to skip this question if he/she doesn't want to share this info or doesn't know.
                to ask human boss about the application and usage of this component (which will have implications on the technical requirements such as temperature range, humidity range, power consumption etc.). If the component's product or application is provided, but other 
                settings such as usage environment, temperature range, humidity range, power consumption etc. are not provided, Please ask human boss to provide as much details as possible
                about the product such as consumer/commercial/industrial/automotive/aerospace/military. Again don't forget to mention that human boss can respond with don't know or skip if he/she
                doesn't want to answer this question. Please return the question prompt in json format: {'product_app_specified': true/false, 'product_app': 'product application', 'usage_grade_specified': true/false, 'usage_grade': 'consumer/commercial/industrial/automotive/aerospace/military'}
            """)
        ])
        request_product_app_usage_node = prompt_request_product_app_usage | llm

        prompt_request_oem_part_number = ChatPromptTemplate.from_messages([
            ("system", """
                        You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                        Given the information that the human boss provided so far about the component he is looking for, please generate a query prompt to get him/her to answer to gather more info about the component. First, if the component's OEM vendor company and/or part number or model number are not provided, 
                        please include a request in the resulting prompt to ask human boss about OEM vendor company and part number or model number of the component(s). Also don't forget to mention that human boss can tell you to skip this question if he/she doesn't want to share this info or doesn't know.
                        if the component's OEM vendor company and/or part number or model number are provided, create a prompt to ask the human boss in case the specified part or model are not available, will the human boss be willing to consider alternatives (yes or no)?
                        Please return the question prompt in json format: {'oem_specified': true/false, 'part_number_specified': true/false, , 'oem': "", 'part_number': "", 'alternative_specified': true/false, 'alternative_accepted': true/false}
                    """)
        ])
        request_oem_part_number_node = prompt_request_product_app_usage | llm

        prompt_request_ranking_method = ChatPromptTemplate.from_messages([
            ("system", """
                        You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                        Please generate a prompt asking the human boss to fill out an attached form to specify the ranking criteria for the component(s) you are looking for. 
                    """)
        ])
        request_ranking_method_node = prompt_request_ranking_method | llm

        prompt4 = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, for the component being searched, 
                and given this json about the component's application product and usage, and given the listed keys in the requirements json, which are the parameters we already 
                know are important and we need to collect detailed data from human boss. To your best knowledge, do you know of any other parameters that might be 
                important but are missing from the requirements list? Please add to the json like so, leaving the value to empty string {... , 'new_parameter': ''}.
            """)
        ])
        understand_level2_node = prompt4 | llm

        prompt4A = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, for the component being searched, 
                and given this requirements json, let's design a html pop-up form to show to human boss so that he/she can fill in paramters' value requirements.
                for parameters that could be a range of string name values, make it a pulldown menu of all possible values and let user be able to select multiple 
                values in case many values are acceptable to his application. For value range, simply use math inequality in string format like "> 0.5 and <= 1.5"
            """)
        ])
        understand_level2A_node = prompt4A | llm

        prompt_check_req_collection_done = ChatPromptTemplate.from_messages([
            ("system", """
                given the requirements json, are all key's values filled up, please return true or false..
            """)
        ])
        understand_level3_node = prompt_check_req_collection_done | llm

        prompt6 = ChatPromptTemplate.from_messages([
            ("system", """
                given the requirements json, are all key's values filled up, please return true or false..
            """)
        ])
        understand_level4_node = prompt6 | llm



        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("chat", node_wrapper(llm_node_with_raw_files, "chat"))
        workflow.set_entry_point("chat")
        # workflow.add_node("goto_site", goto_site)
        workflow.add_node("casually_respond_and_pend_for_next_human_msg", node_wrapper(llm_node_with_raw_files, "casually_respond_and_pend_for_next_human_msg"))
        workflow.add_node("more_analysis_app", node_wrapper(llm_node_with_raw_files, "more_analysis_app"))
        workflow.add_conditional_edges("chat", chat_or_work, ["casually_respond_and_pend_for_next_human_msg", "more_analysis_app"])
        workflow.add_edge("casually_respond_and_pend_for_next_human_msg", "chat")


        workflow.add_node("respond_and_pend_for_next_human_msg", node_wrapper(llm_node_with_raw_files, "respond_and_pend_for_next_human_msg"))
        workflow.add_node("query_component_specs", query_component_specs_node)

        workflow.add_conditional_edges("more_analysis_app", is_preliminary_component_info_ready, ["query_component_specs", "respond_and_pend_for_next_human_msg"])
        workflow.add_edge("respond_and_pend_for_next_human_msg", "more_analysis_app")      # chat infinite loop


        workflow.add_node("query_human_about_components", query_human_about_components_node)
        workflow.add_node("pend_for_human_input_fill_specs", pend_for_human_input_node)
        # workflow.add_node("request_oem_part_number", request_oem_part_number_node)
        workflow.add_edge("query_component_specs", "pend_for_human_input_fill_specs")

        workflow.add_node("request_FOM", request_ranking_method_node)
        workflow.add_node("pend_for_human_input_fill_FOM", pend_for_human_input_node)
        workflow.add_edge("pend_for_human_input_fill_specs", "request_FOM")
        workflow.add_edge("request_FOM", "pend_for_human_input_fill_FOM")


        workflow.add_node("run_search", run_search_node)
        workflow.add_edge("pend_for_human_input_fill_FOM", "run_search")

        workflow.add_node("show_results", show_results_node)
        workflow.add_edge("run_search", "show_results")
        workflow.add_edge("show_results", END)


        searcher_chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        searcher_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        logger.debug("search1688chatter_skill build is done!")

        return searcher_chatter_skill

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateSearch1688ChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateSearch1688ChatterSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        logger.error(ex_stat)
        return None

