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



def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    print("pend_for_human_input_node:", state)
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
    print("node running:", runtime.context.current_node)
    print("interrupted:", interrupted)
    return {
        "pended": interrupted # (3)!
    }


def any_attachment(state: NodeState) -> str:
    print("go to digi-key site:", state)
    return state


def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    print("chat_or_test input:", state)
    if isinstance(state['result'], dict):
        state_output = state['result']
        if state_output.get("job_related", False):
            return "do_test"
        else:
            return "chat_back"
    else:
        return "chat_back"


def read_attachments_node(state: NodeState) -> str:
    print("read attachments:", state)
    return {}


# for now, the raw files can only be pdf, PNG(.png) JPEG (.jpeg and .jpg) WEBP (.webp) Non-animated GIF (.gif),
# .wav (.mp3) and .mp4
def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    print("in llm_node_with_raw_files....")
    user_input = state.get("input", "")
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    print("run time:", runtime)
    current_node = runtime.context["this_node"].get("name")
    # print("current node:", current_node)
    nodes = [{"askid": "skid0", "name": current_node}]
    nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, nodes)
    print("networked prompts:", nodes_prompts)
    node_prompt = nodes_prompts[0]

    attachments = state.get("attachments", [])
    user_content = []
    print("node running:", runtime)
    print("LLM input text:", user_input)
    # Add user text
    user_content.append({"type": "text", "text": user_input})

    # Add all attachments in supported format
    for att in attachments:
        fname = att["filename"].lower()

        mime_type = att.get("mime_type", "").lower()
        print(f"Processing file: {fname} (MIME: {mime_type})")

        # Skip if no file data
        if not att.get("file_data"):
            print(f"Skipping empty file: {fname}")
            continue

        data = att["file_data"]

        # Handle image files (PNG, JPG, etc.)
        if mime_type.startswith('image/'):
            print(f"Processing image file: {fname}")
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
            print(f"Processing PDF file: {fname}")
            # For PDFs, we'll just note its existence since we can't process it directly
            user_content.append({
                "type": "text",
                "text": f"[PDF file: {fname} - PDF content cannot be processed directly]"
            })

        # Handle audio files
        elif mime_type.startswith('audio/'):
            print(f"Processing audio file: {fname}")
            # For audio files, we'll just note its existence
            user_content.append({
                "type": "text",
                "text": f"[Audio file: {fname} - Audio content cannot be processed directly]"
            })

        # Handle other file types
        else:
            print(f"Unsupported file type: {fname} ({mime_type})")
            # user_content.append({
            #     "type": "text",
            #     "text": f"[File: {fname} - This file type is not supported for direct analysis]"
            # })



    llm = ChatOpenAI(model="gpt-4.1-2025-04-14")

    prompt_messages = [
        {
            "role": "system",
            "content": """
                You are an expert assistant. given human prompt, please try understand and reply in json format {"request_test": True/False, "which_test": "test name"}
                """
        },
        {
            "role": "user",
            "content": user_content
        }
    ]

    print("chat node: llm prompt ready:", node_prompt)
    response = llm.invoke(node_prompt)
    print("chat node: LLM response:", response)
    # Parse the response
    try:
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
        print(f"Error parsing LLM response: {e}")
        print(f"Raw response: {response}")
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


def run_test_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    print("run_search_node:", state)

    # send self a message to trigger the real component search work-flow
    result = self_agent.a2a_send_chat_message(self_agent, {"message": "self_test_request", "params": state.attributes})
    state.result = result
    return state



async def create_self_test_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        self_test_chatter_skill = EC_Skill(name="chatter for ecan.ai self test",
                             description="chat with human or other agents to run self test.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.5)
        print("llm loaded:", llm)
        prompt0 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an test engineer helping test this software.
                your human boss will tell you what to test, if he/she ask you to run test, then do so, otherwise, you can just chat with him/her like a normal chat.
            """),
            ("human", "{input}")
        ])

        def process_chat(state: NodeState) -> NodeState:
            # Get the last message (the actual user input)
            last_message = state["messages"][-1]

            # Format the prompt with just the message content
            last_message = "how are you"
            messages = prompt0.invoke({"input": last_message})
            print("LLM prompt:", messages)
            # Call the LLM
            response = llm.invoke(messages)

            print("LLM response:", response)
            # Parse the response
            try:
                import json
                import ast  # Add this import at the top of your file

                # Extract content from AIMessage if needed
                content = response.content if hasattr(response, 'content') else str(response)
                print("Raw content:", content)  # Debug log

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
                print(f"Error parsing LLM response: {e}")
                print(f"Raw response: {response}")
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
            print("gen_chat_back runtime:", runtime)

            # Format the prompt with just the message content
            messages = prompt_random_chat.invoke({"input": last_message})
            print("chat back LLM prompt:", messages)
            # Call the LLM
            response = llm.invoke(messages)

            print("chat back LLM response:", response)
            # Parse the response
            try:
                import json
                import ast  # Add this import at the top of your file

                # Extract content from AIMessage if needed
                content = response.content if hasattr(response, 'content') else str(response)
                print("Raw content:", content)  # Debug log

                state["messages"].append(content)
                # Return the full state with the analysis
                return {**state, "result": content}
            except Exception as e:
                print(f"Error parsing LLM response: {e}")
                print(f"Raw response: {response}")
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



        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("chat", llm_node_with_raw_files)
        workflow.set_entry_point("chat")
        # workflow.add_node("goto_site", goto_site)
        workflow.add_conditional_edges("chat", chat_or_work, ["chat_back", "do_test"])


        workflow.add_node("chat_back", chat_back_node)
        workflow.add_node("pend_for_human_input_chat", pend_for_human_input_node)
        workflow.add_edge("chat_back", "pend_for_human_input_chat")
        workflow.add_edge("pend_for_human_input_chat", "chat")      # chat infinite loop


        workflow.add_node("do_test", check_attachment_node)
        workflow.add_edge("do_test", END)


        self_test_chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        self_test_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("self_test_chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateSelfTestChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateSelfTestChatterSkill: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None

    return self_test_chatter_skill

