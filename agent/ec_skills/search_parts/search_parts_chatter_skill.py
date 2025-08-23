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
import asyncio
import time

from agent.chats.chat_utils import a2a_send_chat
from agent.ec_skills.file_utils.file_utils import extract_file_text
from bot.Logger import *
from agent.ec_skill import *
from agent.ec_skills.llm_hooks.llm_hooks import run_pre_llm_hook, run_post_llm_hook
from utils.logger_helper import get_agent_by_id, get_traceback
from utils.logger_helper import logger_helper as logger
from agent.mcp.local_client import mcp_call_tool
from agent.chats.tests.test_notifications import sample_metrics_0
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from agent.ec_skills.llm_utils.llm_utils import prep_multi_modal_content, get_standard_prompt
from agent.ec_skills.llm_hooks.llm_hooks import llm_node_with_raw_files
from agent.a2a.langgraph_agent.utils import send_data_to_agent


THIS_SKILL_NAME = "chatter for ecan.ai search parts and components web site"
OWNER = "public"
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


def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    print("run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    print(f"pend_for_human_input_node: {current_node_name}", state)
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


def pend_for_human_fill_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    print("run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    print("pend_for_human_fill_FOM_node:", current_node_name, state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", None)
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = None
        notification = None

    interrupted = interrupt(  # (1)!
        {
            "prompt_to_human": state["result"],  # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )
    print("node running:", runtime.context.current_node)
    print("interrupted:", interrupted)
    return {
        "pended": interrupted  # (3)!
    }



def pend_for_human_fill_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    print("run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    print("pend_for_human_fill_specs_node:", current_node_name, state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", None)
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = None
        notification = None

    interrupted = interrupt(  # (1)!
        {
            "prompt_to_human": state["result"],  # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )
    print("node running:", runtime.context.current_node)
    print("interrupted:", interrupted)
    return {
        "pended": interrupted  # (3)!
    }


def is_form_filled(form):
    filled = True
    for key, value in form.items():
        if isinstance(value, dict) or isinstance(value, list):
            if not value:
                filled = False
                break
        elif isinstance(value, str):
            if not value.strip():
                filled = False
                break

    return filled


def examine_filled_specs_node(state):

    if is_form_filled(state["attributes"]["parametric_filters"]):
        state["condition"] = True
    else:
        state["condition"] = False

def confirm_FOM_node(state):
    if is_form_filled(state["attributes"]["FOM"]):
        state["condition"] = True
    else:
        state["condition"] = False

def pend_for_result_message_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    print("run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    print("pend_for_result_message_node:", current_node_name, state)
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



def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    print("chat_or_work input:", state)
    if isinstance(state['attributes'], dict):
        state_attributes = state['attributes']
        if state_attributes.get("work_related", False):
            return "more_analysis_app"
        else:
            return "pend_for_next_human_msg"
    else:
        return "pend_for_next_human_msg"


def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    print("is_preliminary_component_info_ready input:", state)
    if state['condition']:
        return "query_component_specs"
    else:
        return "pend_for_next_human_msg0"

def all_requirement_filled(state: NodeState) -> str:
    print("all_requirement_filled:", state)
    if state["all_requirement_filled"]:
        return True
    return False


# for now, the raw files can only be pdf, PNG(.png) JPEG (.jpeg and .jpg) WEBP (.webp) Non-animated GIF (.gif),
# .wav (.mp3) and .mp4
# def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
#     try:
#         print("in llm_node_with_raw_files....")
#         user_input = state.get("input", "")
#         agent_id = state["messages"][0]
#         agent = get_agent_by_id(agent_id)
#         mainwin = agent.mainwin
#         print("run time:", runtime)
#         current_node_name = runtime.context["this_node"].get("name")
#         # print("current node:", current_node)
#         full_node_name = f"{OWNER}:{THIS_SKILL_NAME}:{current_node_name}"
#         run_pre_llm_hook(full_node_name, agent, state)
#
#         print("networked prompts:", state["prompts"])
#         node_prompt = state["prompts"]
#
#         mm_content = prep_multi_modal_content(state, runtime)
#
#         if state["formatted_prompts"]:
#             formatted_prompt = state["formatted_prompts"][-1]
#         else:
#             formatted_prompt = get_standard_prompt(state)            #STARDARD_PROMPT
#
#         llm = ChatOpenAI(model="gpt-4.1-2025-04-14")
#
#
#         print("chat node: llm prompt ready:", formatted_prompt)
#         response = llm.invoke(formatted_prompt)
#         print("chat node: LLM response:", response)
#         # Parse the response
#         run_post_llm_hook(full_node_name, agent, state, response)
#
#     except Exception as e:
#         # Get the traceback information
#         err_trace = get_traceback(e, "ErrorLLMNodeWithRawFiles")
#         logger.debug(err_trace)

def send_data_back2human(dtype, data, state) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        print("standard_post_llm_hook send_response_back:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4()),
        # send self a message to trigger the real component search work-flow
        if dtype == "form":
            card = {}
            code = {}
            form = data
            notification = {}
        elif dtype == "notification":
            card = {}
            code = {}
            form = {}
            notification = data
        else:
            card = {}
            code = {}
            form = {}
            notification = {}

        agent_response_message = {
            "id": str(uuid.uuid4()),
            "chat": {
                "input": state["result"]["llm_result"],
                "attachments": [],
                "messages": [self_agent.card.id, chat_id, msg_id, "", state["result"]["llm_result"]],
            },
            "params": {
                "content": state["result"]["llm_result"],
                "attachments": state["attachments"],
                "metadata": {
                    "type": dtype, # "text", "code", "form", "notification", "card
                    "card": card,
                    "code": code,
                    "form": form,
                    "notification": notification,
                },
                "role": "",
                "senderId": f"{agent_id}",
                "createAt": int(time.time() * 1000),
                "senderName": f"{self_agent.card.name}",
                "status": "success",
                "ext": "",
                "human": False
            }
        }
        print("sending response msg back to twin:", agent_response_message)
        send_result = self_agent.a2a_send_chat_message(twin_agent, agent_response_message)
        # state.result = result
        return send_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.debug(err_trace)
        return err_trace


def adapt_preliminary_info(preliminary_info, extra_info):
    try:
        components = []
        for info in preliminary_info:
            components.append({
                "component_id": 0,
                "name": info["part name"],
                "proj_id": 0,
                "description":"",
                "category":"",
                "application":info["applications_usage"],
                "metadata": {}
                #     "extra_info" : extra_info,
                #     "oems": info["oems"],
                #     "model_part_numbers": info["model_part_numbers"],
                #     "usage_grade": info["usage_grade"]
                # }
            })
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAdaptPreliminaryInfo")
        logger.debug(err_trace)
        return []
    return components


def query_component_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    
    loop = None
    try:
        print("about to query components:", type(state), state)
        
        # Handle event loop creation for ThreadPoolExecutor
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # need to set up state["tool_input"] to be components
        state["tool_input"] = {
            "components": adapt_preliminary_info(state["attributes"]["preliminary_info"], state["attributes"]["extra_info"])
        }
        
        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]})
        
        # Run the async function and wait for all tasks to complete
        tool_result = loop.run_until_complete(run_tool_call())
        
        # Cancel any remaining tasks to prevent TaskGroup errors
        pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending_tasks:
            task.cancel()
        
        # Wait for cancelled tasks to finish
        if pending_tasks:
            loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
        
        # what we should get here is a dict of parametric search filters based on the preliminary
        # component info, this should be passed to human for filling out and confirmation
        print("query components completed:", type(tool_result), tool_result)
        
        # Check if the tool call was successful
        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            state["result"] = tool_result.content[0].text
            # Prefer 'meta' attribute; fall back to '_meta' (wire format) if needed
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None)
            if meta is None:
                meta = getattr(content0, '_meta', None)
            state["tool_result"] = meta

            # if parametric_search_filters are returned, pass them to human twin
            if state["tool_result"]:
                meta_val = state["tool_result"]
                # Support both dict-wrapped meta {"components": [...]} and legacy list [...]
                if isinstance(meta_val, dict):
                    components = meta_val.get("components", [])
                else:
                    components = meta_val
                print("components:", components)
                if isinstance(components, list) and components:
                    parametric_filters = components[0].get('metadata', {}).get('parametric_filters', {})
                else:
                    parametric_filters = {}
                # needs to make sure this is the response prompt......state["result"]["llm_result"]
                send_data_back2human("form", parametric_filters, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorGoToSiteNode0")
        logger.debug(state['error'])
    finally:
        if loop and not loop.is_closed():
            # Cancel any remaining tasks before closing the loop
            try:
                pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending_tasks:
                    task.cancel()
                if pending_tasks:
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                # Ensure async generators and default executor are shut down cleanly
                try:
                    if hasattr(loop, "shutdown_asyncgens"):
                        loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                try:
                    if hasattr(loop, "shutdown_default_executor"):
                        loop.run_until_complete(loop.shutdown_default_executor())
                except Exception:
                    pass
            except Exception:
                pass  # Ignore errors during cleanup
            loop.close()
    
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
        logger.debug(state['error'])
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
        logger.debug(state['error'])
        return state


def prep_fom_form(state: NodeState):
    try:
        fom = {
          "id": "100",
          "type": "score",
          "title": "score system",
          "components": [
            {
              "name": "price",
              "type": "integer",
              "raw_value": 125,
              "target_value": 125,
              "max_value": 150,
              "min_value": 0,
              "unit": "cents",
              "tooltip": "unit price in cents, 1.25 is the target max price",
              "score_formula": "80 + (125-price)",
              "score_lut": {},
              "weight": 0.3
            },
            {
              "name": "availability",
              "type": "integer",
              "raw_value": 0,
              "target_value": 0,
              "max_value": 150,
              "min_value": 0,
              "unit": "days",
              "tooltip": "nuber of days before the part is available",
              "score_formula": "",
              "score_lut": {
                "20": 100,
                "10": 80,
                "8": 60
              },
              "weight": 0.3
            },
            {
              "name": "performance",
              "type": "integer",
              "raw_value": {
                "power": {
                  "raw_value": 3,
                  "target_value": 125,
                  "type": "integer",
                  "unit": "mA",
                  "tooltip": "power consumption in mA",
                  "score_formula": "80 + (5-current)",
                  "score_lut": {},
                  "weight": 0.7
                },
                "clock_rate": {
                  "raw_value": 10,
                  "target_value": 125,
                  "max_value": 120,
                  "min_value": 0,
                  "type": "integer",
                  "unit": "MHz",
                  "tooltip": "max clock speed in MHz",
                  "score_formula": "80 + (speed - 10)",
                  "score_lut": {},
                  "weight": 0.3
                }
              },
              "unit": "",
              "tooltip": "technical performance",
              "score_formula": "100 - 5*performance",
              "score_lut": {},
              "weight": 0.4
            }
          ]
        }
        return fom
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorPrepFOMForm")
        logger.debug(state['error'])
        return state


def request_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    print("request_FOM_node:", state)

    # send self a message to trigger the real component search work-flow
    fom_form = prep_fom_form(state)
    send_data_back2human("form", fom_form, state)

    return state


def run_search_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    print("run_search_node:", state)

    # send self a message to trigger the real component search work-flow
    # state.attributes should look like this:
    #  [{
    #       "component": "",
    #       "preliminary_info": {},
    #       "extra_info": {},
    #       "parametric_filters": {...},
    #       "fom": {...}
    #  }....]
    result = send_data_to_agent(agent_id, "json", state["attributes"], state)
    # result = self_agent.a2a_send_chat_message(self_agent, {"message": "search_parts_request", "params": state.attributes})
    state.result = result
    return state

def are_component_specs_filled(state):
    print("is_result_ready input:", state)
    if state['condition']:
        return "send_FOM_request"
    else:
        return "pend_for_next_human_msg1"


def is_FOM_filled(state):
    print("is_result_ready input:", state)
    if state['condition']:
        return "show_results"
    else:
        return "pend_for_result"


def is_result_ready(state):
    print("is_result_ready input:", state)
    if state['condition']:
        return "show_results"
    else:
        return "pend_for_result"



# grab results, stuff it into a message and send to human twin agent for
def show_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

    print("show_results_node:", state)

    # send self a message to trigger the real component search work-flow
    final_search_results = state.tool_result
    send_data_back2human("notification", final_search_results, state)
    return state


async def create_search_parts_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_chatter_skill = EC_Skill(name="chatter for ecan.ai search parts and components web site",
                             description="chat with human or other agents to help search a part/component or a product on 1688 website.")

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.5)
        print("llm loaded:", llm)


        # Graph construction
        # graph = StateGraph(State, config_schema=ConfigSchema)
        workflow = StateGraph(NodeState, WorkFlowContext)
        workflow.add_node("chat", node_wrapper(llm_node_with_raw_files, "chat", THIS_SKILL_NAME, OWNER))
        # workflow.set_entry_point("chat")
        # workflow.add_node("goto_site", goto_site)
        workflow.add_node("pend_for_next_human_msg", node_wrapper(pend_for_human_input_node, "pend_for_next_human_msg", THIS_SKILL_NAME, OWNER))
        workflow.add_node("more_analysis_app", node_wrapper(llm_node_with_raw_files, "more_analysis_app", THIS_SKILL_NAME, OWNER))
        workflow.add_conditional_edges("chat", chat_or_work, ["pend_for_next_human_msg", "more_analysis_app"])
        workflow.add_edge("pend_for_next_human_msg", "chat")


        workflow.add_node("pend_for_next_human_msg0", node_wrapper(pend_for_human_input_node, "pend_for_next_human_msg0", THIS_SKILL_NAME, OWNER))

        workflow.set_entry_point("query_component_specs")
        workflow.add_node("query_component_specs", query_component_specs_node)

        workflow.add_conditional_edges("more_analysis_app", is_preliminary_component_info_ready, ["query_component_specs", "pend_for_next_human_msg0"])
        workflow.add_edge("pend_for_next_human_msg0", "more_analysis_app")      # chat infinite loop


        workflow.add_node("pend_for_human_input_fill_specs", pend_for_human_input_node)
        # workflow.add_node("request_oem_part_number", request_oem_part_number_node)
        workflow.add_edge("query_component_specs", "pend_for_human_input_fill_specs")
        workflow.add_node("examine_filled_specs", examine_filled_specs_node)

        workflow.add_node("pend_for_next_human_msg1", node_wrapper(pend_for_human_input_node, "pend_for_next_human_msg1", THIS_SKILL_NAME, OWNER))
        workflow.add_edge("pend_for_human_input_fill_specs", "examine_filled_specs")

        workflow.add_conditional_edges("examine_filled_specs", are_component_specs_filled, ["request_FOM", "pend_for_next_human_msg1"])
        workflow.add_edge("pend_for_next_human_msg1", "examine_filled_specs")

        workflow.add_node("request_FOM", request_FOM_node)

        workflow.add_node("pend_for_human_input_fill_FOM", pend_for_human_fill_FOM_node)
        workflow.add_node("confirm_FOM", confirm_FOM_node)

        workflow.add_node("pend_for_next_human_msg2", node_wrapper(pend_for_human_input_node, "pend_for_next_human_msg2", THIS_SKILL_NAME, OWNER))

        workflow.add_conditional_edges("confirm_FOM", is_FOM_filled, ["run_search", "pend_for_next_human_msg2"])
        workflow.add_edge("pend_for_next_human_msg2", "confirm_FOM")


        workflow.add_node("run_search", run_search_node)
        workflow.add_node("pend_for_result", node_wrapper(pend_for_result_message_node, "pend_for_result", THIS_SKILL_NAME, OWNER))

        workflow.add_node("show_results", show_results_node)
        workflow.add_conditional_edges("run_search", is_result_ready, ["show_results", "pend_for_result"])
        workflow.add_edge("show_results", END)


        searcher_chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        searcher_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        print("search1688chatter_skill build is done!")

    except Exception as e:
        errMsg = get_traceback(e, "ErrorCreateSearchPartsChatterSkill")
        logger.debug(errMsg)
        return None

    return searcher_chatter_skill

