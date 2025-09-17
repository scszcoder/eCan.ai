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
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger
from agent.mcp.local_client import mcp_call_tool
from agent.chats.tests.test_notifications import sample_metrics_0
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from agent.ec_skills.llm_utils.llm_utils import prep_multi_modal_content, get_standard_prompt, run_async_in_sync
from agent.ec_skills.llm_hooks.llm_hooks import llm_node_with_raw_files
from agent.a2a.langgraph_agent.utils import send_data_to_agent
from agent.mcp.server.scrapers.eval_util import get_default_fom_form
from agent.ec_skills.llm_utils.llm_utils import try_parse_json
from agent.mcp.server.scrapers.digi_key_scrapers.unit_test import sample_pfs_1
from agent.mcp.server.scrapers.eval_util import calculate_score, get_default_fom_form


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
            logger.debug("[search_parts_chatter_skill] open URL: " + url)

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
    logger.debug("[search_parts_chatter_skill] un time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug(f"[search_parts_chatter_skill] pend_for_human_input_node: {current_node_name}", state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", {})
        notification = state.get("tool_result").get("notification", {})
    else:
        qa_form = {}
        notification = {}

    interrupted = interrupt( # (1)!
        {
            "prompt_to_human": state["result"], # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )

    logger.debug("[search_parts_chatter_skill] node resume running:", (runtime.context.get("current_node") if isinstance(runtime.context, dict) else None))
    logger.debug("[search_parts_chatter_skill] node state after resuming:", state)
    logger.debug("[search_parts_chatter_skill] interrupted:", interrupted)

    data = try_parse_json(interrupted["human_text"])
    if isinstance(data, dict):
        if data.get("type", "") == "normal":
            logger.debug("[search_parts_chatter_skill] saving filled parametric filter form......")
            state["attributes"]["filled_parametric_filter"] = data
        elif data.get("type", "") == "score":
            logger.debug("[search_parts_chatter_skill] saving filled fom form......")
            state["attributes"]["filled_fom_form"] = data

    return state
    # return {
    #     "pended": interrupted # (3)!
    # }


def pend_for_human_fill_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    logger.debug("[search_parts_chatter_skill] run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug("[search_parts_chatter_skill] pend_for_human_fill_FOM_node:", current_node_name, state)
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
    logger.debug("[search_parts_chatter_skill] node running:", (runtime.context.get("current_node") if isinstance(runtime.context, dict) else None))
    logger.debug("[search_parts_chatter_skill] interrupted:", interrupted)
    return {
        "pended": interrupted  # (3)!
    }

def has_parametric_filters(data):
    try:
        return "parametric_filters" in data["tool_result"]["components"][0]
    except (KeyError, IndexError, TypeError):
        return False

def pend_for_human_fill_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    logger.debug("[search_parts_chatter_skill] run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug("[search_parts_chatter_skill] pend_for_human_fill_specs_node:", current_node_name, state)
    if state.get("tool_result", None):
        pf_exists = has_parametric_filters(state)
        if pf_exists:
            parametric_filters = state["tool_result"]["components"][0]["metadata"]["parametric_filters"]
        else:
            parametric_filters = {}
        qa_form = parametric_filters
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = {}
        notification = {}

    interrupted = interrupt(  # (1)!
        {
            "prompt_to_human": state["result"],  # (2)!
            "qa_form_to_human": qa_form,
            "notification_to_human": notification
        }
    )
    logger.debug("[search_parts_chatter_skill] node running:", current_node_name)
    logger.debug("[search_parts_chatter_skill] interrupted:", interrupted)
    return {
        "pended": interrupted  # (3)!
    }


def is_dict_filled(form):
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



def is_form_filled(form):
    filled = True
    for item in form:
        if not item.get("selectedValue", ""):
            filled = False
            break

    return filled


def examine_filled_specs_node(state):
    logger.debug("[search_parts_chatter_skill] examine filled specs node.......", state)
    pf_exists = has_parametric_filters(state)
    if pf_exists:
        parametric_filters = state["tool_result"]["components"][0]["parametric_filters"]
        state["metadata"]["parametric_filters"] = parametric_filters
    else:
        parametric_filters = {}

    logger.debug("[search_parts_chatter_skill] parametric_filters", parametric_filters)
    if is_form_filled(parametric_filters):
        logger.debug("[search_parts_chatter_skill] parametric filters filled")
        state["condition"] = True
    else:
        logger.debug("[search_parts_chatter_skill] parametric filters NOT YET filled")
        state["condition"] = False
        state["condition"] = True       # just for testing...

    return state



def has_fom(data):
    try:
        return "fom_form" in data["tool_result"]["components"][0]["metadata"]
    except (KeyError, IndexError, TypeError):
        return False


def confirm_FOM_node(state):
    logger.debug("[search_parts_chatter_skill] confirm FOM node.......", state)
    fom_exists = has_fom(state)
    logger.debug("[search_parts_chatter_skill] fom_exists:", fom_exists)
    if fom_exists:
        fom = state["tool_result"]["components"][0]["metadata"]["parametric_filters"]
        state["metadata"]["fom"] = fom
    else:
        fom = {}

    logger.debug("[search_parts_chatter_skill] filled figure of merit", fom)
    if is_form_filled(fom):
        logger.debug("[search_parts_chatter_skill] FOM filled")
        state["condition"] = True
    else:
        logger.debug("[search_parts_chatter_skill] FOM NOT YET filled")
        state["condition"] = False
        state["condition"] = True

    return state

def pend_for_result_message_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    # highlight-next-line
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin
    logger.debug("[search_parts_chatter_skill] run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug("[search_parts_chatter_skill] pend_for_result_message_node:", current_node_name, state)
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
    logger.debug("[search_parts_chatter_skill] node running:", (runtime.context.get("current_node") if isinstance(runtime.context, dict) else None))
    logger.debug("[search_parts_chatter_skill] interrupted:", interrupted)
    return {
        "pended": interrupted # (3)!
    }



def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[search_parts_chatter_skill] chat_or_work input:", state)
    if isinstance(state['attributes'], dict):
        state_attributes = state['attributes']
        if state_attributes.get("work_related", False):
            return "more_analysis_app"
        else:
            return "pend_for_next_human_msg"
    else:
        return "pend_for_next_human_msg"


def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[search_parts_chatter_skill] is_preliminary_component_info_ready input:", state)
    if state['condition']:
        return "query_component_specs"
    else:
        return "pend_for_next_human_msg0"

def all_requirement_filled(state: NodeState) -> str:
    logger.debug("[search_parts_chatter_skill] all_requirement_filled:", state)
    if state["all_requirement_filled"]:
        return True
    return False


# for now, the raw files can only be pdf, PNG(.png) JPEG (.jpeg and .jpg) WEBP (.webp) Non-animated GIF (.gif),
# .wav (.mp3) and .mp4
# def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
#     try:
#         logger.debug("[search_parts_chatter_skill] in llm_node_with_raw_files....")
#         user_input = state.get("input", "")
#         agent_id = state["messages"][0]
#         agent = get_agent_by_id(agent_id)
#         mainwin = agent.mainwin
#         logger.debug("[search_parts_chatter_skill] "run time:", runtime)
#         current_node_name = runtime.context["this_node"].get("name")
#         # logger.debug("[search_parts_chatter_skill] current node:", current_node)
#         full_node_name = f"{OWNER}:{THIS_SKILL_NAME}:{current_node_name}"
#         run_pre_llm_hook(full_node_name, agent, state)
#
#         logger.debug("[search_parts_chatter_skill] networked prompts:", state["prompts"])
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
#         logger.debug("[search_parts_chatter_skill] chat node: llm prompt ready:", formatted_prompt)
#         response = llm.invoke(formatted_prompt)
#         logger.debug("[search_parts_chatter_skill] chat node: LLM response:", response)
#         # Parse the response
#         run_post_llm_hook(full_node_name, agent, state, response)
#
#     except Exception as e:
#         # Get the traceback information
#         err_trace = get_traceback(e, "ErrorLLMNodeWithRawFiles")
#         logger.debug(err_trace)

def send_data_back2human(msg_type, dtype, data, state) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        logger.debug("[search_parts_chatter_skill] standard_post_llm_hook send_response_back:", state)
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
            form = []
            notification = data
        else:
            card = {}
            code = {}
            form = []
            notification = {}

        llm_result = state.get("result", {}).get("llm_result", "")

        agent_response_message = {
            "id": str(uuid.uuid4()),
            "chat": {
                "input": llm_result,
                "attachments": [],
                "messages": [self_agent.card.id, chat_id, msg_id, "", llm_result],
            },
            "params": {
                "content": llm_result,
                "attachments": state.get("attachments", []),
                "metadata": {
                    "mtype": msg_type,  #send_task or send_chat
                    "dtype": dtype, # "text", "code", "form", "notification", "card
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
        logger.debug("[search_parts_chatter_skill] sending response msg back to twin:", agent_response_message)
        send_result = self_agent.a2a_send_chat_message(twin_agent, agent_response_message)
        # state.result = result
        return send_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.error(err_trace)
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
        logger.debug(f"[search_parts_chatter_skill] about to query components: {type(state)}, {state}")
        
        # need to set up state["tool_input"] to be components
        state["tool_input"] = {
            "components": adapt_preliminary_info(state["attributes"]["preliminary_info"], state["attributes"]["extra_info"])
        }
        
        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]})
        
        # Always use a dedicated local loop to avoid interfering with any global loop
        # Run the async call safely from sync
        tool_result = run_async_in_sync(run_tool_call())

        # what we should get here is a dict of parametric search filters based on the preliminary
        # component info, this should be passed to human for filling out and confirmation
        logger.debug("[search_parts_chatter_skill]  query components completed:", type(tool_result), tool_result)
        
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
                logger.debug("[search_parts_chatter_skill] components:", components)
                if isinstance(components, list) and components:
                    parametric_filters = components[0].get('parametric_filters', {})
                    if parametric_filters:
                        parametric_filter = parametric_filters[0]
                    else:
                        parametric_filter = {}
                else:
                    parametric_filters = []
                    parametric_filter = {}

                logger.debug("[search_parts_chatter_skill] about to send back parametric_filters:", parametric_filters)
                logger.debug("[search_parts_chatter_skill] about to send back parametric_filter:", parametric_filter)
                logger.debug("[search_parts_chatter_skill] state at the moment:", state)
                fe_parametric_filter = {
                    "id": "technical_query_form",
                    "type": "normal",
                    "title": components[0].get('title', 'Component under search') if components else 'Component under search',
                    "fields": parametric_filters
                }
                #     "fields": [
                #         {
                #             "id": "core",
                #             "type": "select",
                #             "label": "MCU Core",
                #             "tooltip": "MCU Core Types",
                #             "options": [
                #                 { "label": "ATmega328P", "value": "ATmega328P" },
                #                 { "label": "ESP32", "value": "ESP32" },
                #                 { "label": "STM32F103", "value": "STM32F103" },
                #                 { "label": "PIC16F84A", "value": "PIC16F84A" },
                #                 { "label": "Arduino Nano", "value": "Arduino Nano" }
                #             ],
                #             "defaultValue": "ESP32"
                #         },
                #         {
                #             "id": "factory",
                #             "type": "text",
                #             "label": "Factory",
                #             "tooltip": "Test field type text",
                #             "defaultValue": "ESP——32"
                #         },
                #         {
                #             "id": "voltage",
                #             "type": "select",
                #             "label": "Operating Voltage",
                #             "tooltip": "Operation Voltage Options",
                #             "options": [
                #                 { "label": "3.3V", "value": "3.3V" },
                #                 { "label": "5V", "value": "5V" },
                #                 { "label": "12V", "value": "12V" }
                #             ],
                #             "defaultValue": "3.3V"
                #         }
                #     ]
                # }
                state["result"] = {"llm_result": "Here is a parametric search filter form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."}
                # needs to make sure this is the response prompt......state["result"]["llm_result"]
                send_data_back2human("send_chat","form", fe_parametric_filter, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    finally:
        # Nothing to do; local loop was closed above
        pass

    logger.debug("[search_parts_chatter_skill] query_component_specs_node all done, current state is:", state)
    return state

def convert_table_headers_to_params(headers):
    params = []
    for header in headers:
        params.append({"name": header, "ptype": "", "value": "header"})

    return params

def query_fom_basics_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    print("hello??????????????")
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    mainwin = agent.mainwin

    loop = None
    try:
        logger.debug(f"[search_parts_chatter_skill] about to query fom basics: {type(state)}, {state}")

        table_headers = list(state["tool_result"][0].keys())
        print("here are table headers string:", table_headers)
        # need to set up state["tool_input"] to be components
        params = convert_table_headers_to_params(table_headers)
        i = 0
        state["tool_input"] = {
            "component_results_info": { "component_name":state["attributes"]["preliminary_info"][i]["part name"],
                                        "product_app":state["attributes"]["preliminary_info"][i]["applications_usage"],
                                        "max_product_metrics": 3,
                                        "max_component_metrics": 3,
                                        "params": [
                                            params
                                        ]
                                    }
        }

        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_fom", {"input": state["tool_input"]})

        # Always use a dedicated local loop to avoid interfering with any global loop
        # Run the async call safely from sync
        tool_result = run_async_in_sync(run_tool_call())

        # what we should get here is a dict of parametric search filters based on the preliminary
        # component info, this should be passed to human for filling out and confirmation
        logger.debug("[search_parts_chatter_skill]  query fom basics tool call completed:", type(tool_result), tool_result)

        # Check if the tool call was successful
        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            state["result"] = tool_result.content[0].text
            # Prefer 'meta' attribute; fall back to '_meta' (wire format) if needed
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None)
            if meta is None:
                meta = getattr(content0, '_meta', None)


            if meta:
                components = meta["components"]
                state["tool_result"] = meta["components"]
            else:
                print("ERROR: no meta in tool result!!!!!!!!!!!!")
                components = {}
                state["tool_result"] = {}

            print("state tool result:", state["tool_result"])
            # if parametric_search_filters are returned, pass them to human twin
            if state["tool_result"]:
                i = 0
                component = state["attributes"]["preliminary_info"][i]["part name"]
                logger.debug("[search_parts_chatter_skill] tool result:", state["tool_result"])
                # fom_form = sample_metrics_0
                fom_form = {
                    "id": "eval_system_form",
                    "type": "score",
                    "title": f'{component} under search',
                    "components": [
                        {
                            "name": components["fom"]["price_parameter"],
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
                            "name": components["fom"]["lead_time_parameter"],
                            "type": "integer",
                            "raw_value": 0,
                            "target_value": 0,
                            "max_value": 150,
                            "min_value": 0,
                            "unit": "days",
                            "tooltip": "lead time/availablility of the component",
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

                            },
                            "weight": 0.4
                        }
                    ]
                }
                print("fom form with price and lead time filled::", fom_form)
                for fom_item in components["fom"]["component_level_metrics"]:
                    item_name = fom_item["metric_name"]
                    fom_form["components"][-1]["raw_value"][item_name] = {
                        "name": item_name,
                        "type": "integer",
                        "raw_value": 0,
                        "target_value": 0,
                        "max_value": 100,
                        "min_value": 0,
                        "unit": "",
                        "tooltip": "",
                        "score_formula": fom_item["score_formula"],
                        "score_lut": fom_item["score_lut"],
                        "weight": fom_item["score_weight"],
                    }

                print("fom form to be filled:", fom_form)
                state["result"] = {
                    "llm_result": "Here is a figure of merit (FOM) form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."}
                # needs to make sure this is the response prompt......state["result"]["llm_result"]
                send_data_back2human("send_chat", "form", fom_form, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    finally:
        # Nothing to do; local loop was closed above
        pass

    logger.debug("[search_parts_chatter_skill] query_fom_basics_node all done, current state is:", state)
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
        fom = get_default_fom_form()
        return fom
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorPrepFOMForm")
        logger.debug(state['error'])
        return {}


def request_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        logger.debug(f"[search_parts_chatter_skill] request_FOM_node:{state}")

        # send self a message to trigger the real component search work-flow
        fom_form = prep_fom_form(state)
        send_data_back2human("send_chat","form", fom_form, state)
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorRequestFOMNode")
        logger.debug(state['error'])
    finally:
        # Nothing to do; local loop was closed above
        pass

    logger.debug("[search_parts_chatter_skill] request_FROM_node all done, current state is:", state)
    return state


async def browser_search_with_parametric_filters(mainwin, url, parametric_filters):
    # Run Browser Use inside a worker thread with a Selector event loop to support Playwright subprocesses on Windows.
    manager = mainwin.unified_browser_manager
    result = manager.run_basic_agent_task(product_phrase=parametric_filters.get("product_phrase") if isinstance(parametric_filters, dict) else None)
    try:
        if hasattr(result, "save_to_file"):
            result.save_to_file('./tmp/history.json')
    except Exception:
        pass
    return result

def re_rank_search_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug(f"re_rank_search_results_node about to re-rank search results: {state['attributes']['search_results']}")

    url_short = list(state["attributes"]['search_results'].keys())[0]
    calculate_score(state["attributes"]['filled_fom_form'], state["attributes"]['search_results'][url_short])

    sorted_search_results = sorted(state["attributes"]['search_results'][url_short], key=lambda x: x['score'], reverse=True)
    n_results = min(state["attributes"].get("max_n_results", 8), len(sorted_search_results))
    print("n_results: ", n_results, len(sorted_search_results))
    sorted_search_results = sorted_search_results[:n_results]
    return state


def package_search_results_notification(search_results):
    try:
        notification = {
            "id": "search_results_form",
            "title": "Component Search Results",
            "Items": search_results,
            "summary": {
                "product1": {
                    "criteria1": "value",
                    "criteria2": "value",
                    "criteria3": "value"
                },
                "product2": {
                    "criteria1": "value",
                    "criteria2": "value",
                    "criteria3": "value"
                },
                "product3": {
                    "criteria1": "value",
                    "criteria2": "value",
                    "criteria3": "value"
                }
            },
            "comments": [],
            "statistics": {
                "sites_visited": 1,
                "searches": 1,
                "pages_visited": 1,
                "input_tokens": 1,
                "output_tokens": 1,
                "products_compared": 1
            },
            "behind_the_scene": "url",
            "show_feedback_options": True
        }
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPackageSearchResultsNotification")
        logger.error(err_trace)
        notification = {}

    return notification

def find_key(data, target_key, path=None):
    """
    Recursively search nested dict/list for a key.
    Returns list of (path, value) where the key was found.
    """
    if path is None:
        path = []

    results = []

    if isinstance(data, dict):
        for k, v in data.items():
            new_path = path + [k]
            if k == target_key:
                results.append((".".join(new_path), v))
            results.extend(find_key(v, target_key, new_path))

    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = path + [f"[{i}]"]
            results.extend(find_key(item, target_key, new_path))

    return results


def run_local_search_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    # _ensure_context(runtime.context)
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    print("finding key route: ", find_key(state, "filled_parametric_filter"))
    logger.debug(f"[search_parts_chatter_skill] run_local_search_node: {state}")

    # site - [[{"name", "url"}, "name", "url", ....]...]
    site_categories = state["tool_result"]["components"][0].get("site_categories", [[]])
    in_pfs = state["attributes"].get("filled_parametric_filter", [])
    if in_pfs:
        parametric_filters = [in_pfs.get("fields", [])]
    else:
        parametric_filters = [[]]

    # url = state["tool_input"]["url"]
    url = {"url": "https://www.digikey.com/en/products", "categories": [["Voltage Regulators - Linear, Low Drop Out (LDO) Regulators"]]}
    url = {"url": "https://www.digikey.com/en/products/filter/power-management-pmic/voltage-regulators-linear-low-drop-out-ldo-regulators/699", "categories": [["Voltage Regulators - Linear, Low Drop Out (LDO) Regulators"]]}
    # url = {"url": "file:///C:/temp/parametric/digikeySC/Voltage Regulators - Linear, Low Drop Out (LDO) Regulators _ Power Management (PMIC) _ Electronic Components Distributor DigiKey.html", "categories": [["Voltage Regulators - Linear, Low Drop Out (LDO) Regulators"]]}
    url_short = "digikey"
    logger.debug("[search_parts_chatter_skill] site categories:", site_categories)
    # parametric_filters = sample_pfs_1
    # set up tool call input
    state["tool_input"]["urls"] = site_categories
    state["tool_input"]["parametric_filters"] = parametric_filters
    state["tool_input"]["fom_form"] = {}            # this will force the tool to use default fom
    state["tool_input"]["max_n_results"] = 8

    logger.debug(f"[search_parts_chatter_skill] tool input::{state['tool_input']}")
    async def run_tool_call():
        return await mcp_call_tool("api_ecan_local_search_components", {"input": state["tool_input"]})

    # Always use a dedicated local loop to avoid interfering with any global loop
    # Run the async call safely from sync
    tool_result = run_async_in_sync(run_tool_call())

    # what we should get here is a dict of parametric search filters based on the preliminary
    # component info, this should be passed to human for filling out and confirmation
    logger.info("[search_parts_chatter_skill] run local search completed:", type(tool_result), tool_result)


    # send self a message to trigger the real component search work-flow
    # state.attributes should look like this:
    #  [{
    #       "component": "",
    #       "preliminary_info": {},
    #       "extra_info": {},
    #       "parametric_filters": {...},
    #       "fom": {...}
    #  }....]
    # result = send_data_to_agent(agent_id, "json", state["attributes"], state)
    # result = self_agent.a2a_send_chat_message(self_agent, {"message": "search_parts_request", "params": state.attributes})

    state["tool_result"] = tool_result.content[0].meta["results"]
    if state["attributes"].get("search_results", {}):
        state["attributes"]["search_results"][url_short] = tool_result.content[0].meta["results"]
    else:
        state["attributes"]["search_results"] = {url_short: tool_result.content[0].meta["results"]}

    print("state tool results:", state["tool_result"])

    return state

def are_component_specs_filled(state):
    logger.debug(f"[search_parts_chatter_skill] are_component_specs_filled input:{state}")
    if state['condition']:
        return "run_search"
    else:
        return "pend_for_next_human_msg1"


def is_FOM_filled(state):
    logger.debug(f"[search_parts_chatter_skill] is_FOM_filled input: {state}")
    if state['condition']:
        return "re_rank_search_results"
    else:
        return "pend_for_human_input_fill_FOM"

def is_result_ready(state):
    logger.debug(f"[search_parts_chatter_skill] is_result_ready input: {state}")
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

    logger.debug("[search_parts_chatter_skill] show_results_node:", state)
    notifiable = package_search_results_notification(state["tool_result"])
    # send self a message to trigger the real component search work-flow
    final_search_results = state["tool_result"]
    send_data_back2human("send_chat","notification", final_search_results, state)
    return state


async def create_search_parts_chatter_skill(mainwin):
    try:
        llm = mainwin.llm
        mcp_client = mainwin.mcp_client
        local_server_port = mainwin.get_local_server_port()
        searcher_chatter_skill = EC_Skill(name="chatter for ecan.ai search parts and components web site",
                             description="chat with human or other agents to help search a part/component or a product on 1688 website.")

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.5)
        logger.debug("[search_parts_chatter_skill] llm loaded:", llm)


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


        workflow.add_node("pend_for_human_input_fill_specs", node_wrapper(pend_for_human_input_node, "pend_for_human_input_fill_specs", THIS_SKILL_NAME, OWNER))
        # workflow.add_node("request_oem_part_number", request_oem_part_number_node)
        workflow.add_edge("query_component_specs", "pend_for_human_input_fill_specs")
        workflow.add_node("examine_filled_specs", examine_filled_specs_node)

        workflow.add_node("pend_for_next_human_msg1", node_wrapper(pend_for_human_input_node, "pend_for_next_human_msg1", THIS_SKILL_NAME, OWNER))
        workflow.add_edge("pend_for_human_input_fill_specs", "examine_filled_specs")

        workflow.add_node("run_search", run_local_search_node)

        workflow.add_conditional_edges("examine_filled_specs", are_component_specs_filled, ["run_search", "pend_for_next_human_msg1"])
        workflow.add_edge("pend_for_next_human_msg1", "examine_filled_specs")


        # pend for result node is for cloud side search only, where search could take a while, and results come back asynchrously.
        # workflow.add_node("pend_for_result", node_wrapper(pend_for_result_message_node, "pend_for_result", THIS_SKILL_NAME, OWNER))
        # workflow.set_entry_point("run_search")

        workflow.add_edge("run_search", "query_fom_basics")



        # workflow.set_entry_point("query_fom_basics")
        workflow.add_node("query_fom_basics", query_fom_basics_node)

        workflow.add_node("request_FOM", request_FOM_node)

        workflow.add_edge("query_fom_basics", "request_FOM")


        workflow.add_node("pend_for_human_input_fill_FOM", node_wrapper(pend_for_human_input_node, "pend_for_human_input_fill_FOM", THIS_SKILL_NAME, OWNER))
        workflow.add_edge("request_FOM", "pend_for_human_input_fill_FOM")

        workflow.add_node("confirm_FOM", confirm_FOM_node)
        workflow.add_edge("pend_for_human_input_fill_FOM", "confirm_FOM")

        # workflow.add_node("pend_for_next_human_msg2", node_wrapper(pend_for_human_input_node, "pend_for_next_human_msg2", THIS_SKILL_NAME, OWNER))

        workflow.add_node("re_rank_search_results", re_rank_search_results_node)

        workflow.add_conditional_edges("confirm_FOM", is_FOM_filled, ["re_rank_search_results", "pend_for_human_input_fill_FOM"])
        # workflow.add_edge("pend_for_next_human_msg2", "confirm_FOM")



        workflow.add_node("show_results", show_results_node)
        # workflow.add_conditional_edges("run_search", is_result_ready, ["show_results", "pend_for_result"])

        # workflow.add_edge("run_search", "show_results")
        workflow.add_edge("re_rank_search_results", "show_results")

        workflow.add_edge("show_results", END)


        searcher_chatter_skill.set_work_flow(workflow)
        # Store manager so caller can close it after using the skill
        searcher_chatter_skill.mcp_client = mcp_client  # type: ignore[attr-defined]
        logger.debug("[search_parts_chatter_skill]search1688chatter_skill build is done!")

    except Exception as e:
        errMsg = get_traceback(e, "ErrorCreateSearchPartsChatterSkill")
        logger.error(errMsg)
        return None

    return searcher_chatter_skill

