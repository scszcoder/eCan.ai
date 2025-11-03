"""
External Skill: search_digikey_chatter (flat code_dir layout)

Chats to gather requirements and searches Digikey, ranking results with a user-defined FOM.
This external skill is self-contained: all node functions and helpers are defined here.
"""
from typing import Any

from agent.ec_skill import EC_Skill, NodeState, WorkFlowContext, node_wrapper, node_builder
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync, try_parse_json
from agent.agent_service import get_agent_by_id
from agent.mcp.server.scrapers.eval_util import get_default_rerank_req
from agent.ec_skills.dev_defs import BreakpointManager
from agent.ec_skills.build_node import build_mcp_tool_calling_node, build_pend_event_node

from langgraph.graph import StateGraph
from langgraph.constants import END
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt

# Use split-out helpers to keep this module lean
from .helpers import (
    chat_or_work as h_chat_or_work,
    is_preliminary_component_info_ready as h_is_preliminary_component_info_ready,
    are_component_specs_filled as h_are_component_specs_filled,
    is_FOM_filled as h_is_FOM_filled,
    pend_for_human_input_node as h_pend_for_human_input_node,
    pend_for_human_fill_FOM_node as h_pend_for_human_fill_FOM_node,
    pend_for_human_fill_specs_node as h_pend_for_human_fill_specs_node,
    examine_filled_specs_node as h_examine_filled_specs_node,
    confirm_FOM_node as h_confirm_FOM_node,
    local_sort_search_results_node as h_local_sort_search_results_node,
    re_rank_search_results_node as h_re_rank_search_results_node,
)

from .digikey_nodes import (
    llm_node_with_raw_files as h_llm_node_with_raw_files,
    pend_for_human_input_node as h_pend_for_human_input_node,
    examine_filled_specs_node as h_examine_filled_specs_node,
    confirm_FOM_node as h_confirm_FOM_node,
    query_component_specs_node as h_query_component_specs_node,
    query_fom_basics_node as h_query_fom_basics_node,
    local_sort_search_results_node as h_local_sort_search_results_node,
    run_local_search_node as h_run_local_search_node,
    re_rank_search_results_node as h_re_rank_search_results_node,
)

THIS_SKILL_NAME = "search_digikey_chatter"
OWNER = "public"
DESCRIPTION = (
    "Chat assistant to search electronic parts on the Digikey website. "
    "Collects specs, builds parametric filters, and ranks results using an FOM (price, lead time, performance)."
)

def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[search_digikey_chatter_skill] chat_or_work input:", state)
    if isinstance(state.get('attributes'), dict) and state['attributes'].get("work_related", False):
        return "more_analysis_app"
    return "pend_for_next_human_msg"

def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[search_digikey_chatter_skill] is_preliminary_component_info_ready input:", state)
    return "query_component_specs" if state.get('condition') else "pend_for_next_human_msg0"

def are_component_specs_filled(state: NodeState) -> str:
    logger.debug("[search_digikey_chatter_skill] are_component_specs_filled input:", state)
    return "run_search" if state.get('condition') else "pend_for_next_human_msg1"

def is_FOM_filled(state: NodeState) -> str:
    logger.debug("[search_digikey_chatter_skill] is_FOM_filled input:", state)
    return "local_sort_search_results" if state.get('condition') else "pend_for_human_input_fill_FOM"

def has_parametric_filters(data: dict) -> bool:
    try:
        return "parametric_filters" in data["tool_result"]["components"][0]
    except (KeyError, IndexError, TypeError):
        return False

def is_form_filled(form: Any) -> bool:
    filled = True
    for item in form:
        if not item.get("selectedValue", ""):
            filled = False
            break
    return filled

def has_fom(data: dict) -> bool:
    try:
        return "fom_form" in data["tool_result"]["components"][0]["metadata"]
    except (KeyError, IndexError, TypeError):
        return False

def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[search_digikey_chatter_skill] runtime:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug(f"[search_digikey_chatter_skill] pend_for_human_input_node: {current_node_name}", state)
    if state.get("tool_result"):
        qa_form = state.get("tool_result").get("qa_form", {})
        notification = state.get("tool_result").get("notification", {})
    else:
        qa_form = {}
        notification = {}

    interrupted = interrupt({
        "i_tag": current_node_name,
        "prompt_to_human": state.get("result"),
        "qa_form_to_human": qa_form,
        "notification_to_human": notification,
    })

    logger.debug("[search_digikey_chatter_skill] node resumed, state:", state)
    logger.debug("[search_digikey_chatter_skill] interrupted:", interrupted)

    data = try_parse_json(interrupted.get("human_text"))
    if isinstance(data, dict):
        if data.get("type", "") == "normal":
            logger.debug("[search_digikey_chatter_skill] saving filled parametric filter form......")
            state["attributes"]["filled_parametric_filter"] = data
        elif data.get("type", "") == "score":
            logger.debug("[search_digikey_chatter_skill] saving filled fom form......")
            state["attributes"]["filled_fom_form"] = data

    return state

def pend_for_human_fill_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[search_digikey_chatter_skill] run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node:", current_node_name, state)
    if state.get("tool_result"):
        qa_form = state.get("tool_result").get("qa_form", None)
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = None
        notification = None

    interrupted = interrupt({
        "i_tag": current_node_name,
        "prompt_to_human": state.get("result"),
        "qa_form_to_human": qa_form,
        "notification_to_human": notification,
    })
    logger.debug("[search_digikey_chatter_skill] interrupted:", interrupted)
    return {"pended": interrupted}

def pend_for_human_fill_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[search_digikey_chatter_skill] run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_specs_node:", current_node_name, state)
    if state.get("tool_result"):
        pf_exists = has_parametric_filters(state)
        if pf_exists:
            parametric_filters = state["tool_result"]["components"][0]["metadata"].get("parametric_filters", {})
        else:
            parametric_filters = {}
        qa_form = parametric_filters
        notification = state.get("tool_result").get("notification", None)
    else:
        qa_form = {}
        notification = {}

    interrupted = interrupt({
        "i_tag": current_node_name,
        "prompt_to_human": state.get("result"),
        "qa_form_to_human": qa_form,
        "notification_to_human": notification,
    })
    logger.debug("[search_digikey_chatter_skill] interrupted:", interrupted)
    return {"pended": interrupted}

def examine_filled_specs_node(state: NodeState):
    logger.debug("[search_digikey_chatter_skill] examine filled specs node.......", state)
    pf_exists = has_parametric_filters(state)
    if pf_exists:
        parametric_filters = state["tool_result"]["components"][0].get("parametric_filters", [])
        state["metadata"]["parametric_filters"] = parametric_filters
    else:
        parametric_filters = []

    logger.debug("[search_digikey_chatter_skill] parametric_filters", parametric_filters)
    if is_form_filled(parametric_filters):
        state["condition"] = True
    else:
        state["condition"] = False
        # NOTE: original had a forced True for testing; omitted here for correctness
    return state

def confirm_FOM_node(state: NodeState):
    logger.debug("[search_digikey_chatter_skill] confirm FOM node.......", state)
    fom_exists = has_fom(state)
    if fom_exists:
        fom = state["tool_result"]["components"][0]["metadata"].get("parametric_filters", [])
        state["metadata"]["fom"] = fom
    else:
        fom = []

    if is_form_filled(fom):
        state["condition"] = True
    else:
        state["condition"] = False
    return state

def send_data_back2human(msg_type, dtype, data, state) -> NodeState:
    import uuid
    import time as _time
    try:
        agent_id = state["messages"][0]
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        logger.debug("[search_digikey_chatter_skill] standard_post_llm_hook send_response_back:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4()),

        if dtype == "form":
            card, code, form, notification = {}, {}, data, {}
        elif dtype == "notification":
            card, code, form, notification = {}, {}, [], data
        else:
            card, code, form, notification = {}, {}, [], {}

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
                    "mtype": msg_type,
                    "dtype": dtype,
                    "card": card,
                    "code": code,
                    "form": form,
                    "notification": notification,
                },
                "role": "",
                "senderId": f"{agent_id}",
                "createAt": int(_time.time() * 1000),
                "senderName": f"{self_agent.card.name}",
                "status": "success",
                "ext": "",
                "human": False,
            },
        }
        logger.debug("[search_digikey_chatter_skill] sending response msg back to twin:", agent_response_message)
        send_result = self_agent.a2a_send_chat_message(twin_agent, agent_response_message)
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
                "description": "",
                "category": "",
                "application": info["applications_usage"],
                "metadata": {},
            })
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAdaptPreliminaryInfo")
        logger.debug(err_trace)
        return []
    return components

def query_component_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    try:
        logger.debug("[search_digikey_chatter_skill] about to query components:", type(state), state)
        state["tool_input"] = {
            "components": adapt_preliminary_info(state["attributes"]["preliminary_info"], state["attributes"].get("extra_info", {}))
        }

        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]})

        tool_result = run_async_in_sync(run_tool_call())

        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            state["result"] = tool_result.content[0].text
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
            state["tool_result"] = meta

            if state["tool_result"]:
                meta_val = state["tool_result"]
                components = meta_val.get("components", []) if isinstance(meta_val, dict) else meta_val
                logger.debug("[search_digikey_chatter_skill] components:", components)
                if isinstance(components, list) and components:
                    parametric_filters = components[0].get('parametric_filters', {})
                    if parametric_filters:
                        _ = parametric_filters[0]
                else:
                    parametric_filters = []

                fe_parametric_filter = {
                    "id": "technical_query_form",
                    "type": "normal",
                    "title": components[0].get('title', 'Component under search') if components else 'Component under search',
                    "fields": parametric_filters,
                }

                state["result"] = {"llm_result": "Here is a parametric search filter form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."}
                send_data_back2human("send_chat", "form", fe_parametric_filter, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    return state

def convert_table_headers_to_params(headers):
    params = []
    for header in headers:
        params.append({"name": header, "ptype": "", "value": "header"})
    return params

def query_fom_basics_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug("[search_digikey_chatter_skill] about to query fom basics:", type(state), state)
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    try:
        table_headers = list(state["tool_result"][0].keys())
        params = convert_table_headers_to_params(table_headers)
        i = 0
        state["tool_input"] = {
            "component_results_info": {
                "component_name": state["attributes"]["preliminary_info"][i]["part name"],
                "product_app": state["attributes"]["preliminary_info"][i]["applications_usage"],
                "max_product_metrics": 3,
                "max_component_metrics": 3,
                "params": [params],
            }
        }

        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_fom", {"input": state["tool_input"]})

        tool_result = run_async_in_sync(run_tool_call())

        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
            if meta:
                components = meta["components"]
                state["tool_result"] = meta["components"]
            else:
                components = {}
                state["tool_result"] = {}

            if state["tool_result"]:
                component = state["attributes"]["preliminary_info"][i]["part name"]
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
                            "weight": 0.3,
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
                            "score_lut": {"20": 100, "10": 80, "8": 60},
                            "weight": 0.3,
                        },
                        {
                            "name": "performance",
                            "type": "integer",
                            "raw_value": {},
                            "weight": 0.4,
                        },
                    ],
                }
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

                state["result"] = {
                    "llm_result": "Here is a figure of merit (FOM) form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about.",
                }
                send_data_back2human("send_chat", "form", fom_form, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    return state

def local_sort_search_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug("[search_digikey_chatter_skill] about to sort search results:", type(state), state)
    try:
        table_headers = state["tool_result"]["fom"]["component_level_metrics"]
        header_text = table_headers[0]["metric_name"]
        ascending = True if table_headers[0].get("sort_order") == "asc" else False
        sites = list(state["attributes"].get("search_results", {}).keys())
        i = 0
        state["tool_input"] = {
            "sites": [
                {"url": sites[i], "ascending": ascending, "header_text": header_text, "max_n": 8}
            ]
        }

        async def run_tool_call():
            return await mcp_call_tool("ecan_local_sort_search_results", {"input": state["tool_input"]})

        tool_result = run_async_in_sync(run_tool_call())

        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
            if meta:
                state["tool_result"] = meta["results"]
                state["attributes"]["sorted_search_results"] = meta["results"]
            else:
                state["tool_result"] = []
                state["attributes"]["sorted_search_results"] = []
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    return state

def find_key(data, target_key, path=None):
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
    self_agent = get_agent_by_id(agent_id)
    _ = self_agent.mainwin
    logger.debug("[search_digikey_chatter_skill] run_local_search_node:", state)

    site_categories = state["tool_result"]["components"][0].get("site_categories", [[]])
    in_pfs = state["attributes"].get("filled_parametric_filter", [])
    if in_pfs:
        parametric_filters = [in_pfs.get("fields", [])]
    else:
        parametric_filters = [[]]

    url_short = "digikey"
    state["tool_input"]["urls"] = site_categories
    state["tool_input"]["parametric_filters"] = parametric_filters
    state["tool_input"]["fom_form"] = {}
    state["tool_input"]["max_n_results"] = 8

    async def run_tool_call():
        return await mcp_call_tool("ecan_local_search_components", {"input": state["tool_input"]})

    tool_result = run_async_in_sync(run_tool_call())
    state["tool_result"] = tool_result.content[0].meta["results"]
    if state["attributes"].get("search_results", {}):
        state["attributes"]["search_results"][url_short] = tool_result.content[0].meta["results"]
    else:
        state["attributes"]["search_results"] = {url_short: tool_result.content[0].meta["results"]}
    return state

def convert_rank_results_to_search_results(state) -> dict:
    try:
        attrs = state.get("attributes", {})
        rank_results = attrs.get("rank_results", {}) or {}
        ranked_list = rank_results.get("ranked_results", []) or []
        full_rows = attrs.get("sorted_search_results")
        if not isinstance(full_rows, list) or not full_rows:
            try:
                full_rows = get_default_rerank_req().get("rows", [])
            except Exception:
                full_rows = []
        prelim = (attrs.get("preliminary_info") or [{}])
        prelim0 = prelim[0] if prelim and isinstance(prelim, list) else {}
        component_name = prelim0.get("part name", "Component")
        items = []
        for pos, entry in enumerate(ranked_list, start=1):
            row_index = entry.get("row_index")
            total_score = entry.get("total_score", 0)
            row_data_short = entry.get("row_data", {}) or {}
            full_row = {}
            if isinstance(row_index, int) and 0 <= row_index < len(full_rows):
                full_row = full_rows[row_index] or {}
            highlights = []
            hl_list = entry.get("highligths")
            if isinstance(hl_list, list) and hl_list:
                for h in hl_list:
                    try:
                        if isinstance(h, dict):
                            highlights.append({
                                "label": str(h.get("label", "")),
                                "value": str(h.get("value", "")),
                                "unit": str(h.get("unit", "")),
                            })
                    except Exception:
                        continue
            else:
                for k, v in (row_data_short.items() if isinstance(row_data_short, dict) else []):
                    try:
                        highlights.append({"label": str(k), "value": str(v), "unit": ""})
                    except Exception:
                        continue
            product_name = full_row.get("product_name") or full_row.get("name") or full_row.get("Model") or f"item{pos}"
            brand = full_row.get("brand") or full_row.get("Brand") or ""
            model = full_row.get("model") or full_row.get("Model") or ""
            main_image = full_row.get("main_image") or full_row.get("image") or full_row.get("Image") or ""
            url = full_row.get("url") or full_row.get("URL") or full_row.get("link") or ""
            items.append({
                "product_id": component_name.lower().replace(" ", "_") if isinstance(component_name, str) else "component",
                "product_name": product_name,
                "brand": brand,
                "model": model,
                "main_image": main_image,
                "url": url,
                "rank": pos,
                "score": total_score,
                "highlights": highlights,
                "app_specific": [],
            })
        notification = {
            "id": "search_results_form",
            "title": f"{component_name} Search Results",
            "Items": items,
            "summary": {},
            "comments": [],
            "statistics": {
                "sites_visited": 1,
                "searches": 1,
                "pages_visited": 1,
                "input_tokens": 1,
                "output_tokens": 1,
                "products_compared": len(items),
            },
            "behind_the_scene": "",
            "show_feedback_options": True,
        }
        return notification
    except Exception as e:
        err_trace = get_traceback(e, "ErrorConvertRankResultsToSearchResults")
        logger.error(err_trace)
        return {
            "id": "search_results_form",
            "title": "Search Results",
            "Items": [],
            "summary": {},
            "comments": [],
            "statistics": {
                "sites_visited": 0,
                "searches": 0,
                "pages_visited": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "products_compared": 0,
            },
            "behind_the_scene": "",
            "show_feedback_options": True,
        }

def re_rank_search_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug("[search_digikey_chatter_skill] about to re-rank search results:", state.get('attributes', {}).get('search_results'))
    try:
        agent_id = state["messages"][0]
        task_id = state["messages"][3]
        agent = get_agent_by_id(agent_id)
        this_task = next((task for task in agent.tasks if task.id == task_id), None)
        mainwin = agent.mainwin
    except Exception as e:
        logger.error(f"[search_digikey_chatter_skill] CRITICAL ERROR in node setup: {e}")
        logger.error(f"[search_digikey_chatter_skill] State structure: {state}")
        raise e

    existing_cloud_task_id = state["attributes"].get("cloud_task_id")
    # Short-term guard: ignore node-tag-like placeholders (e.g., pend_for_*)
    def _is_node_tag_like(v: object) -> bool:
        try:
            s = (v or "") if isinstance(v, str) else str(v or "")
        except Exception:
            return False
        s = s.strip().lower()
        if not s:
            return False
        if s.startswith("pend_for_"):
            return True
        if s in {"chat", "more_analysis_app", "prep_query_components", "query_component_specs",
                 "pend_for_next_human_msg", "pend_for_next_human_msg0", "pend_for_next_human_msg1",
                 "pend_for_next_human_msg2", "pend_for_human_input_fill_specs",
                 "pend_for_human_input_fill_fom", "local_sort_search_results", "prep_local_sort"}:
            return True
        return False

    if _is_node_tag_like(existing_cloud_task_id):
        logger.debug(f"[search_digikey_chatter_skill] Ignoring node-tag-like existing cloud_task_id: {existing_cloud_task_id}")
        existing_cloud_task_id = None
    try:
        if not existing_cloud_task_id and this_task and hasattr(this_task, 'metadata') and 'state' in this_task.metadata:
            task_state = this_task.metadata['state']
            if isinstance(task_state, dict) and 'attributes' in task_state:
                task_cloud_task_id = task_state['attributes'].get('cloud_task_id')
                if task_cloud_task_id and not _is_node_tag_like(task_cloud_task_id):
                    state["attributes"]["cloud_task_id"] = task_cloud_task_id
                    existing_cloud_task_id = task_cloud_task_id
                elif task_cloud_task_id:
                    logger.debug(f"[search_digikey_chatter_skill] Discarding node-tag-like task_cloud_task_id from metadata: {task_cloud_task_id}")
        if existing_cloud_task_id and not _is_node_tag_like(existing_cloud_task_id):
            cloud_task_id = existing_cloud_task_id
        else:
            i = 0
            setup = get_default_rerank_req()
            rerank_req = {"agent_id": agent_id, "work_type": "rerank_search_results", "setup": setup}
            state["tool_input"] = rerank_req
            agent.runner.update_event_handler("rerank_search_results", this_task.queue)

            async def run_tool_call():
                return await mcp_call_tool("api_ecan_ai_rerank_results", {"input": state["tool_input"]})

            tool_result = run_async_in_sync(run_tool_call())
            if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
                content0 = tool_result.content[0]
                meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
                if meta:
                    cloud_task_id = meta["cloud_task_id"]
                    state["tool_result"] = meta["cloud_task_id"]
                    state["attributes"]["cloud_task_id"] = cloud_task_id
                else:
                    cloud_task_id = "unknown"
                    state["tool_result"] = {}
            elif hasattr(tool_result, 'isError') and tool_result.isError:
                state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
                return state
            else:
                state["error"] = "Unexpected tool result format"
                return state
    except Exception as e:
        logger.error(f"[search_digikey_chatter_skill] Exception in cloud_task_id detection: {e}")
        existing_cloud_task_id = None

    try:
        interrupted = interrupt({
            "i_tag": cloud_task_id,
            "rank_results": {},
        })

        cloud_results_raw = interrupted.get("notification_to_agent", {})
        if cloud_results_raw:
            logger.debug("[search_digikey_chatter_skill] received cloud ranking results (raw):", cloud_results_raw)
            try:
                if isinstance(cloud_results_raw, str):
                    import ast
                    cloud_results = ast.literal_eval(cloud_results_raw)
                else:
                    cloud_results = cloud_results_raw
                logger.debug("[search_digikey_chatter_skill] parsed cloud ranking results:", cloud_results)
                state["attributes"]["rank_results"] = cloud_results
            except (ValueError, SyntaxError) as e:
                logger.error(f"[search_digikey_chatter_skill] Failed to parse cloud results: {e}")
                state["attributes"]["rank_results"] = {}

        if state["attributes"].get("rank_results", []):
            notification = convert_rank_results_to_search_results(state)
            state["result"] = {
                "llm_result": "Here are the ranked search results based on your Figure of Merit.",
            }
            send_data_back2human("send_chat", "notification", notification, state)
    except GraphInterrupt:
        raise
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    return state

def build_skill(run_context: dict | None = None, mainwin=None) -> EC_Skill:
    """Entry called by build_agent_skills_from_files(); returns an EC_Skill."""
    try:
        skill = EC_Skill(name=THIS_SKILL_NAME, description=DESCRIPTION)

        # Build workflow graph
        wf = StateGraph(NodeState, WorkFlowContext)

        # Breakpoint manager for debug toggles
        bp_manager = BreakpointManager()

        # Chat lane
        wf.add_node("chat", node_builder(h_llm_node_with_raw_files, "chat", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("pend_for_next_human_msg", node_builder(h_pend_for_human_input_node, "pend_for_next_human_msg", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("more_analysis_app", node_builder(h_llm_node_with_raw_files, "more_analysis_app", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_conditional_edges("chat", h_chat_or_work, ["pend_for_next_human_msg", "more_analysis_app"])
        wf.add_edge("pend_for_next_human_msg", "chat")

        # Collect specs -> query components (prep -> MCP -> post)
        wf.add_node("pend_for_next_human_msg0", node_builder(h_pend_for_human_input_node, "pend_for_next_human_msg0", THIS_SKILL_NAME, OWNER, bp_manager))

        # Prep node: set state.tool_input = {"input": {...}}
        def prep_query_components(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            attrs = state.get("attributes", {})
            comps = adapt_preliminary_info(attrs.get("preliminary_info", []), attrs.get("extra_info", {}))
            state["tool_input"] = {"input": {"components": comps}}
            return state

        wf.add_node("prep_query_components", node_builder(prep_query_components, "prep_query_components", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_query_components", build_mcp_tool_calling_node({"tool_name": "api_ecan_ai_query_components"}, "mcp_query_components", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_query_components(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                results = state.get("results", [])
                tool_result = results[-1] if results else None
                if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
                    content0 = tool_result.content[0]
                    meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
                    state["tool_result"] = meta
                    components = meta.get("components", []) if isinstance(meta, dict) else meta
                    parametric_filters = []
                    if isinstance(components, list) and components:
                        parametric_filters = components[0].get('parametric_filters', []) or []
                    fe_parametric_filter = {
                        "id": "technical_query_form",
                        "type": "normal",
                        "title": components[0].get('title', 'Component under search') if isinstance(components, list) and components else 'Component under search',
                        "fields": parametric_filters,
                    }
                    state["result"] = {"llm_result": "Here is a parametric search filter form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."}
                    send_data_back2human("send_chat", "form", fe_parametric_filter, state)
                elif hasattr(tool_result, 'isError') and tool_result.isError:
                    state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostQueryComponents")
            return state

        wf.add_node("post_query_components", node_builder(post_query_components, "post_query_components", THIS_SKILL_NAME, OWNER, bp_manager))

        wf.add_conditional_edges("more_analysis_app", h_is_preliminary_component_info_ready, ["prep_query_components", "pend_for_next_human_msg0"])
        wf.add_edge("prep_query_components", "mcp_query_components")
        wf.add_edge("mcp_query_components", "post_query_components")

        # Human fills specs
        wf.add_node("pend_for_human_input_fill_specs", node_builder(h_pend_for_human_input_node, "pend_for_human_input_fill_specs", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("post_query_components", "pend_for_human_input_fill_specs")
        wf.add_node("examine_filled_specs", node_builder(h_examine_filled_specs_node, "examine_filled_specs", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("pend_for_next_human_msg1", node_builder(h_pend_for_human_input_node, "pend_for_next_human_msg1", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("pend_for_human_input_fill_specs", "examine_filled_specs")

        # Local search (Digikey): prep -> MCP -> post
        def prep_run_search(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                site_categories = state.get("tool_result", {}).get("components", [{}])
                in_pfs = state.get("attributes", {}).get("filled_parametric_filter", {})
                if in_pfs:
                    parametric_filters = [in_pfs.get("fields", [])]
                else:
                    parametric_filters = [[]]
                body = {
                    "urls": site_categories,
                    "parametric_filters": parametric_filters,
                    "fom_form": {},
                    "max_n_results": 8,
                }
                state["tool_input"] = {"input": body}
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPrepRunSearch")
            return state

        wf.add_node("prep_run_search", node_builder(prep_run_search, "prep_run_search", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_run_search", build_mcp_tool_calling_node({"tool_name": "ecan_local_search_components"}, "mcp_run_search", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_run_search(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                results = state.get("results", [])
                tr = results[-1] if results else None
                if hasattr(tr, 'content') and tr.content:
                    meta = getattr(tr.content[0], 'meta', None) or getattr(tr.content[0], '_meta', None)
                    if isinstance(meta, dict):
                        rows = meta.get("results")
                        state["tool_result"] = rows
                        url_short = "digikey"
                        attrs = state.setdefault("attributes", {})
                        if isinstance(attrs.get("search_results"), dict):
                            attrs["search_results"][url_short] = rows
                        else:
                            attrs["search_results"] = {url_short: rows}
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostRunSearch")
            return state

        wf.add_node("post_run_search", node_builder(post_run_search, "post_run_search", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_conditional_edges("examine_filled_specs", h_are_component_specs_filled, ["prep_run_search", "pend_for_next_human_msg1"])
        wf.add_edge("prep_run_search", "mcp_run_search")
        wf.add_edge("mcp_run_search", "post_run_search")
        wf.add_edge("pend_for_next_human_msg1", "examine_filled_specs")

        # FOM: prep -> MCP -> post
        wf.add_edge("post_run_search", "prep_query_fom")

        def prep_query_fom(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                table_headers = list((state.get("tool_result") or [{}])[0].keys())
                params = convert_table_headers_to_params(table_headers)
                attrs = state.get("attributes", {})
                i = 0
                state["tool_input"] = {"input": {
                    "component_results_info": {
                        "component_name": (attrs.get("preliminary_info") or [{}])[i].get("part name"),
                        "product_app": (attrs.get("preliminary_info") or [{}])[i].get("applications_usage"),
                        "max_product_metrics": 3,
                        "max_component_metrics": 3,
                        "params": [params],
                    }
                }}
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPrepQueryFOM")
            return state

        wf.add_node("prep_query_fom", node_builder(prep_query_fom, "prep_query_fom", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_query_fom", build_mcp_tool_calling_node({"tool_name": "api_ecan_ai_query_fom"}, "mcp_query_fom", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_query_fom(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                results = state.get("results", [])
                tr = results[-1] if results else None
                if hasattr(tr, 'content') and tr.content and "completed" in tr.content[0].text:
                    content0 = tr.content[0]
                    meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
                    components = meta.get("components") if isinstance(meta, dict) else None
                    state["tool_result"] = components or {}
                    if components:
                        attrs = state.get("attributes", {})
                        i = 0
                        component = (attrs.get("preliminary_info") or [{}])[i].get("part name")
                        fom_form = {
                            "id": "eval_system_form",
                            "type": "score",
                            "title": f"{component} under search",
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
                                    "weight": 0.3,
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
                                    "score_lut": {"20": 100, "10": 80, "8": 60},
                                    "weight": 0.3,
                                },
                                {"name": "performance", "type": "integer", "raw_value": {}, "weight": 0.4},
                            ],
                        }
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
                        state["result"] = {"llm_result": "Here is a figure of merit (FOM) form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."}
                        send_data_back2human("send_chat", "form", fom_form, state)
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostQueryFOM")
            return state

        wf.add_node("post_query_fom", node_builder(post_query_fom, "post_query_fom", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("mcp_query_fom", "post_query_fom")
        wf.add_edge("prep_query_fom", "mcp_query_fom")
        wf.add_edge("post_query_fom", "pend_for_human_input_fill_FOM")
        wf.add_node("pend_for_human_input_fill_FOM", node_builder(h_pend_for_human_input_node, "pend_for_human_input_fill_FOM", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("confirm_FOM", node_builder(h_confirm_FOM_node, "confirm_FOM", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("pend_for_human_input_fill_FOM", "confirm_FOM")

        # Sort: prep -> MCP -> post
        def prep_local_sort(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                table_headers = (state.get("tool_result") or {}).get("fom", {}).get("component_level_metrics", [])
                header_text = (table_headers[0] or {}).get("metric_name") if table_headers else "score"
                ascending = True if (table_headers[0] or {}).get("sort_order") == "asc" else False
                sites = list((state.get("attributes", {}).get("search_results", {}) or {}).keys())
                i = 0
                body = {"sites": [{"url": sites[i] if sites else "", "ascending": ascending, "header_text": header_text, "max_n": 8}]}
                state["tool_input"] = {"input": body}
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPrepLocalSort")
            return state

        wf.add_node("prep_local_sort", node_builder(prep_local_sort, "prep_local_sort", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_local_sort", build_mcp_tool_calling_node({"tool_name": "ecan_local_sort_search_results"}, "mcp_local_sort", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_local_sort(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                results = state.get("results", [])
                tr = results[-1] if results else None
                if hasattr(tr, 'content') and tr.content:
                    meta = getattr(tr.content[0], 'meta', None) or getattr(tr.content[0], '_meta', None)
                    if isinstance(meta, dict):
                        rows = meta.get("results")
                        state["tool_result"] = rows
                        state.setdefault("attributes", {}).setdefault("sorted_search_results", rows)
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostLocalSort")
            return state

        wf.add_node("post_local_sort", node_builder(post_local_sort, "post_local_sort", THIS_SKILL_NAME, OWNER, bp_manager))

        # Re-rank remains custom due to interrupt + cloud handoff
        wf.add_node("re_rank_search_results", node_builder(h_re_rank_search_results_node, "re_rank_search_results", THIS_SKILL_NAME, OWNER, bp_manager))
        # Start at chat to collect requirements; breakpoint wrappers enable graphical debugging
        wf.set_entry_point("chat")
        wf.add_conditional_edges("confirm_FOM", h_is_FOM_filled, ["prep_local_sort", "pend_for_human_input_fill_FOM"])
        wf.add_edge("prep_local_sort", "mcp_local_sort")
        wf.add_edge("mcp_local_sort", "post_local_sort")
        wf.add_edge("post_local_sort", "re_rank_search_results")
        wf.add_edge("re_rank_search_results", END)

        skill.set_work_flow(wf)

        # Prefer run_context for shared references; fallback to legacy mainwin
        ctx = run_context or ({"main_window": mainwin} if mainwin is not None else None)
        if isinstance(ctx, dict):
            # Expose for nodes if needed
            skill.config.setdefault("run_context", ctx)
            # Wire MCP client if available
            if ctx.get("mcp_client") is not None:
                skill.mcp_client = ctx["mcp_client"]
            elif mainwin and hasattr(mainwin, "mcp_client"):
                skill.mcp_client = mainwin.mcp_client

        logger.info(f"[search_digikey_chatter_skill] Built skill {THIS_SKILL_NAME}")
        return skill
    except Exception as e:
        logger.error(get_traceback(e, "ErrorBuildSearchDigikeyChatterSkill"))
        return None
