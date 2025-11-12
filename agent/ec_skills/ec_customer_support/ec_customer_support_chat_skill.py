from typing import TypedDict
import uuid

from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command
from langgraph.func import entrypoint, task
from langgraph.graph import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.base import BaseStore
from langchain_core.messages.utils import (
    # highlight-next-line
    trim_messages,
    # highlight-next-line
    count_tokens_approximately
# highlight-next-line
)
from langgraph.prebuilt import create_react_agent
from langmem.short_term import SummarizationNode

from prompt_toolkit import prompt
from scipy.stats import chatterjeexi
import base64
from agent.ec_skill import *
from agent.agent_service import get_agent_by_id


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

def pend_for_human_input_node(state: NodeState):
    # highlight-next-line
    print("pend_for_human_input_node:", state)
    interrupted = interrupt( # (1)!
        {
            "prompt_to_human": state["result"] # (2)!
        }
    )
    print("interrupted:", interrupted)
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


# def gen_prompt_node(state: NodeState) -> Command[Literal["call_llm", "run_tool"]]:
#     # This is the value we'll be providing via Command(resume=<human_review>)
#
async def any_attachment(state: NodeState) -> str:
    print("any_attachment input:", state)
    state_output = state.messages[-1]
    if state_output.get("job_related", False):
        return "do_work"
    return "chat_back"

def chat_or_work(state: NodeState) -> str:
    print("chat_or_work input:", state)
    state_output = state['result']
    if state_output.get("job_related", False):
        return "do_work"
    return "chat_back"

def all_requirement_filled(state: NodeState) -> str:
    print("all_requirement_filled:", state)
    if state["all_requirement_filled"]:
        return True
    return False

async def ask_cloud_expert_for_search_parameters(state: NodeState) -> str:
    print("ask_cloud_expert_for_search_parameters:", state)
    return ""

async def ask_cloud_expert_for_search_sites(state: NodeState) -> str:
    print("ask_cloud_expert_for_search_sites:", state)
    return ""

def read_attachments(state: NodeState) -> str:
    print("read attachments:", state)
    return {}

def debug_node(state: NodeState) -> NodeState:
    print("Debug node state:", state)
    return state




def extract_file_text(file_bytes: bytes, filename: str) -> str:
    # Example for PDFs; add more logic for other file types as needed
    import io
    import PyPDF2
    with io.BytesIO(file_bytes) as buf:
        reader = PyPDF2.PdfReader(buf)
        return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())

def llm_node_with_files(state: dict) -> dict:
    user_input = state.get("input", "")
    attachments = state.get("attachments", [])
    if not attachments:
        raise ValueError("No files attached!")

    # Get mainwin's llm object from agent
    agent_id = state.get("messages", [None])[0]
    agent = get_agent_by_id(agent_id) if agent_id else None
    mainwin = agent.mainwin if agent else None
    llm = mainwin.llm if mainwin and mainwin.llm else None
    if not llm:
        raise ValueError("LLM not available in mainwin")

    file_list = "\n".join(f"- {att['filename']}" for att in attachments)
    contents_list = []
    for att in attachments:
        filename = att["filename"]
        file_bytes = att["content"]
        if isinstance(file_bytes, str):
            file_bytes = base64.b64decode(file_bytes)
        file_text = extract_file_text(file_bytes, filename)
        # Optionally, limit per-file content for LLM context size
        contents_list.append(f"--- {filename} ---\n{file_text[:2000]}")

    file_contents = "\n\n".join(contents_list)

    prompt_vars = {
        "user_input": user_input,
        "file_list": file_list,
        "file_contents": file_contents
    }
    prompt_str = prompt.format(**prompt_vars)
    result = llm.invoke(prompt_str)
    return {"llm_response": result.content}



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


# summarization_node = SummarizationNode(
#     token_counter=count_tokens_approximately,
#     model=model,
#     max_tokens=384,
#     max_summary_tokens=128,
#     output_messages_key="llm_input_messages",
# )



async def create_ec_customer_support_chat_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_chatter_skill = EC_Skill(name="chatter for meca search 1688 web site",
                             description="chat with human or other agents to help search a part/component or a product on 1688 website.")

        # await wait_until_server_ready(f"http://localhost:{local_server_port}/healthz")
        # print("connecting...........sse")

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        print("llm loaded:", llm)
        prompt0 = ChatPromptTemplate.from_messages([
            ("system", """
                You're an electronics component procurement expert helping sourcing and procuring components, you job is to chat with your human boss to collect all the requirements for sourcing this component and distill all requirement information in a JSON format.
                 Of course you can chat with your human boss on any topic, but you should first distinguish whether the current chat message from human boss is directly related to sourcing components or not. if it has nothing to do with the job, or simply
                 showing the intention of trying to source components without revealing any of the actual component information, like a component name (for example, a resistor or a regulator or a variable capacitor etc.), you should return a json in the form of {{'job_related': false}}, 
                 otherwise you should return a json in the form of {{'job_related': true}}.
            """),
            ("human", "{input}")
        ])

        async def process_chat(state: NodeState) -> NodeState:
            # Get the last message (the actual user input)
            last_message = state["messages"][-1]

            # Format the prompt with just the message content
            messages = await prompt0.ainvoke({"input": last_message})
            print("LLM prompt:", messages)
            # Call the LLM
            response = await llm.ainvoke(messages)

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
        chat_node = process_chat

        prompt1 = ChatPromptTemplate.from_messages([
            ("system", """
                You're a personal assistant, given a chat message sequence, please respond to the latest chat message to your best effort.
            """),
            ("human", "{input}")
        ])

        async def gen_chat_back(state: NodeState) -> NodeState:
            # Get the last message (the actual user input)
            last_message = state["messages"][-1]

            # Format the prompt with just the message content
            messages = await prompt1.ainvoke({"input": last_message})
            print("chat back LLM prompt:", messages)
            # Call the LLM
            response = await llm.ainvoke(messages)

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

        # casual response node
        chat_back_node = gen_chat_back


        prompt2 = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message,  did the human boss provided an attached document? please answer in json format: {'with_attachment': true/false, 'attachment_files': [list of file names] }.
            """),
            ("human", "{input}")
        ])

        # initial classification node
        check_attachment_node = prompt2 | llm



        prompt2A = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message,  try to understand it and let me know in json format that whether the human boss provided a pasted BOM text or simply looking for source a few components with the following json format {'with_attachment': true/false, 'bom': true/false, 'num_components': int }.
            """),
            ("human", "{input}")
        ])

        # initial classification node
        understand_level0A_node = prompt2A | llm

        prompt2B = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message, did human boss provide the part number of the component being searched (unless they're passive commodity components like a resistor, capacitor etc.) please answer in json format: {'part_number_or_passives': ['list of part numbers'], 'part_number_unknown': ['list of component names mentioned']} ?.
            """),
            ("human", "{input}")
        ])

        # initial classification node
        understand_level0B_node = prompt2B | llm

        prompt2C = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given the latest human boss message, did human boss provide the part number of the component being searched (unless they're passive commodity components like a resistor, capacitor etc.) please answer in json format: {'part_number_or_passives': ['list of part numbers'], 'part_number_unknown': ['list of component names mentioned']} ?.
            """),
            ("human", "Question: {user_input}\n\n"
                         "Files:\n{file_list}\n\n"
                         "File Contents:\n{file_contents}")
        ])

        prompt3 = ChatPromptTemplate.from_messages([
            ("system", """
                You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                Given that human boss provided only vague info about the component he is looking for, we should design a series of prompt to get him/her to answer to gather technical parametric requirements. First, lets generate a question prompt
                to ask human boss about the application and usage of this component (which will have implications on the technical requirements such as temperature range, humidity range, power consumption etc.). Please ask human boss to provide as much details as possible
                about the product as well as the product's usage environment. so that we can classify this usage environment being consumer or industrial or automotive or aerospace or military. Also don't forget to mention that human boss can tell you to skip this question if
                he/she doesn't want to answer this question. Please return the question prompt in json format: {'question_prompt': 'question prompt text'}
            """)
        ])
        understand_level1_node = prompt3 | llm

        prompt3A = ChatPromptTemplate.from_messages([
            ("system", """
                        You're a component procurement expert helping your human boss sourcing components for making a product, you job is to chat with your human boss to collect all the requirements for sourcing the component(s) and distill all requirement information in a JSON format. 
                        Given that human boss' answer regarding the component's usage product information. please try to fill the following json data {'decide_skip': true/false, 'product_name': 'product name', 'product_usage/NA': 'product usage/NA', 'usage_classification': 'consumer/industrial/automotive/aerospace/military/NA'}
                    """)
        ])
        understand_level1A_node = prompt3A | llm

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

        prompt5 = ChatPromptTemplate.from_messages([
            ("system", """
                given the requirements json, are all key's values filled up, please return true or false..
            """)
        ])
        understand_level3_node = prompt5 | llm

        prompt6 = ChatPromptTemplate.from_messages([
            ("system", """
                given the requirements json, are all key's values filled up, please return true or false..
            """)
        ])
        understand_level4_node = prompt6 | llm



        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("chat", chat_node)
        workflow.set_entry_point("chat")
        # workflow.add_node("goto_site", goto_site)
        workflow.add_node("debug", debug_node)
        workflow.add_conditional_edges("chat", chat_or_work, ["chat_back", "do_work"])


        workflow.add_node("chat_back", chat_back_node)
        workflow.add_node("pend_for_human_input", pend_for_human_input_node)
        workflow.add_edge("chat_back", "pend_for_human_input")
        workflow.add_edge("pend_for_human_input", "chat")      # chat infinite loop


        workflow.add_node("do_work", check_attachment_node)
        workflow.add_node("understand_level0A", understand_level0A_node)
        # workflow.add_node("do_work", check_attachment_node)

        workflow.add_conditional_edges("do_work", any_attachment, ["read_attachment", "understand_level0A"])
        # workflow.add_edge("do_work", "understand_level0A")
        workflow.add_edge("understand_level0A", END)

        workflow.add_node("read_attachment", read_attachments)
        workflow.add_edge("read_attachment", END)

        # workflow.add_edge("understand_level0A_node", "understand_level0B_node")
        # workflow.add_node("understand1", understand_level1_node)
        # workflow.add_edge("understand_level0B_node", "understand_level1_node")
        # workflow.add_node("understand2", understand_level2_node)
        # workflow.add_edge("understand_level1_node", "understand_level2_node")
        # workflow.add_node("understand3", understand_level3_node)
        # workflow.add_edge("understand_level2_node", "understand_level3_node")
        # workflow.add_node("understand4", understand_level4_node)
        # workflow.add_edge("understand_level3_node", "understand_level4_node")
        # workflow.add_conditional_edges("all_parameters_filled", understand_level4_node, ["ask_to_fill_requirements_node", "confirm_requirements_node"])
        #
        # prompt15A = ChatPromptTemplate.from_messages([
        #     ("system", """
        #         given yet empty requirements key values, ask human boss to fill them in or skip if they choose to..
        #     """)
        # ])
        # ask_to_fill_requirements_node = prompt15A | llm
        # workflow.add_node("ask_to_fill_requirements", ask_to_fill_requirements_node)
        #
        # prompt15B = ChatPromptTemplate.from_messages([
        #     ("system", """
        #         given the all filled requirements json data, ask human boss to review, edit some if needed and confirm.
        #     """)
        # ])
        # confirm_requirements_node = prompt15B | llm
        # workflow.add_node("confirm_requirements", confirm_requirements_node)
        #
        #
        # # workflow.add_node("ask_parameters", ask_cloud_expert_for_search_parameters)
        # # workflow.add_node("ask_sites", ask_cloud_expert_for_search_sites)

        # obtain search parameters from search sites.


        searcher_chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        searcher_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("search1688chatter_skill build is done!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateSearch1688ChatterSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateSearch1688ChatterSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None

    return searcher_chatter_skill


