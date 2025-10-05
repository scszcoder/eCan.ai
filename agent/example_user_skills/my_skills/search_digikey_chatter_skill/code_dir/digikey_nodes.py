"""
External node implementations for the search_digikey_chatter skill.
Copied and adapted from agent/ec_skills/search_parts/search_parts_chatter_skill.py
so that the external skill is self-contained.
"""
from typing import Any
import uuid
import time

from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger

from agent.ec_skill import *  # Provides NodeState, WorkFlowContext, EC_Skill types
from agent.agent_service import get_agent_by_id
from agent.ec_skills.llm_utils.llm_utils import try_parse_json, run_async_in_sync
from agent.mcp.local_client import mcp_call_tool
from agent.mcp.server.scrapers.eval_util import get_default_rerank_req

# Optional helpers referenced in original code
# from agent.mcp.server.scrapers.eval_util import get_default_fom_form, get_default_rerank_req


def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    _ = agent.mainwin
    logger.debug("[digikey_nodes] runtime:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug(f"[digikey_nodes] pend_for_human_input_node: {current_node_name}", state)
    if state.get("tool_result", None):
        qa_form = state.get("tool_result").get("qa_form", {})
        notification = state.get("tool_result").get("notification", {})
    else:
        qa_form = {}
        notification = {}

    interrupted = interrupt(
        {
            "i_tag": current_node_name,
            "prompt_to_human": state.get("result"),
            "qa_form_to_human": qa_form,
            "notification_to_human": notification,
        }
    )

    logger.debug("[digikey_nodes] node resume running:", (runtime.context.get("current_node") if isinstance(runtime.context, dict) else None))
    logger.debug("[digikey_nodes] node state after resuming:", state)
    logger.debug("[digikey_nodes] interrupted:", interrupted)

    data = try_parse_json(interrupted.get("human_text"))
    if isinstance(data, dict):
        if data.get("type", "") == "normal":
            logger.debug("[digikey_nodes] saving filled parametric filter form......")
            state["attributes"]["filled_parametric_filter"] = data
        elif data.get("type", "") == "score":
            logger.debug("[digikey_nodes] saving filled fom form......")
            state["attributes"]["filled_fom_form"] = data

    return state


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


def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[digikey_nodes] chat_or_work input:", state)
    if isinstance(state.get('attributes'), dict):
        state_attributes = state['attributes']
        if state_attributes.get("work_related", False):
            return "more_analysis_app"
        else:
            return "pend_for_next_human_msg"
    else:
        return "pend_for_next_human_msg"


def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[digikey_nodes] is_preliminary_component_info_ready input:", state)
    if state.get('condition'):
        return "query_component_specs"
    else:
        return "pend_for_next_human_msg0"


def examine_filled_specs_node(state: NodeState) -> NodeState:
    logger.debug("[digikey_nodes] examine filled specs node.......", state)
    pf_exists = has_parametric_filters(state)
    if pf_exists:
        parametric_filters = state["tool_result"]["components"][0]["parametric_filters"]
        state["metadata"]["parametric_filters"] = parametric_filters
    else:
        parametric_filters = {}

    logger.debug("[digikey_nodes] parametric_filters", parametric_filters)
    if is_form_filled(parametric_filters):
        logger.debug("[digikey_nodes] parametric filters filled")
        state["condition"] = True
    else:
        logger.debug("[digikey_nodes] parametric filters NOT YET filled")
        state["condition"] = False
        # For testing; consider removing in production
        state["condition"] = True

    return state


def has_fom(data: dict) -> bool:
    try:
        return "fom_form" in data["tool_result"]["components"][0]["metadata"]
    except (KeyError, IndexError, TypeError):
        return False


def confirm_FOM_node(state: NodeState) -> NodeState:
    logger.debug("[digikey_nodes] confirm FOM node.......", state)
    fom_exists = has_fom(state)
    logger.debug("[digikey_nodes] fom_exists:", fom_exists)
    if fom_exists:
        fom = state["tool_result"]["components"][0]["metadata"]["parametric_filters"]
        state["metadata"]["fom"] = fom
    else:
        fom = {}

    logger.debug("[digikey_nodes] filled figure of merit", fom)
    if is_form_filled(fom):
        logger.debug("[digikey_nodes] FOM filled")
        state["condition"] = True
    else:
        logger.debug("[digikey_nodes] FOM NOT YET filled")
        state["condition"] = False
        # For testing; consider removing in production
        state["condition"] = True

    return state


def send_data_back2human(msg_type, dtype, data, state) -> NodeState:
    try:
        agent_id = state["messages"][0]
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        logger.debug("[digikey_nodes] standard_post_llm_hook send_response_back:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4()),
        
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
                    "mtype": msg_type,
                    "dtype": dtype,
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
        logger.debug("[digikey_nodes] sending response msg back to twin:", agent_response_message)
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
                "metadata": {}
            })
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAdaptPreliminaryInfo")
        logger.debug(err_trace)
        return []
    return components


def query_component_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    agent = get_agent_by_id(agent_id)
    _ = agent.mainwin
    
    try:
        logger.debug(f"[digikey_nodes] about to query components: {type(state)}, {state}")
        state["tool_input"] = {
            "components": adapt_preliminary_info(state["attributes"]["preliminary_info"], state["attributes"]["extra_info"])
        }
        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]})
        tool_result = run_async_in_sync(run_tool_call())

        logger.debug("[digikey_nodes] query components completed:", type(tool_result), tool_result)
        
        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            state["result"] = tool_result.content[0].text
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None)
            if meta is None:
                meta = getattr(content0, '_meta', None)
            state["tool_result"] = meta

            if state["tool_result"]:
                meta_val = state["tool_result"]
                if isinstance(meta_val, dict):
                    components = meta_val.get("components", [])
                else:
                    components = meta_val
                logger.debug("[digikey_nodes] components:", components)
                if isinstance(components, list) and components:
                    parametric_filters = components[0].get('parametric_filters', {})
                    if parametric_filters:
                        parametric_filter = parametric_filters[0]
                    else:
                        parametric_filter = {}
                else:
                    parametric_filters = []
                    parametric_filter = {}

                logger.debug("[digikey_nodes] about to send back parametric_filters:", parametric_filters)
                fe_parametric_filter = {
                    "id": "technical_query_form",
                    "type": "normal",
                    "title": components[0].get('title', 'Component under search on Digikey') if components else 'Component under search on Digikey',
                    "fields": parametric_filters
                }

                state["result"] = {"llm_result": "Here is a parametric search filter form for Digikey to help you find the parts you're looking for. Please fill it out to the best of your ability and send it back to me. If you're unsure about certain parameters, just leave them blank. Feel free to ask any questions about the meaning or implications of any parameters."}
                send_data_back2human("send_chat", "form", fe_parametric_filter, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    
    logger.debug("[digikey_nodes] query_component_specs_node all done, current state is:", state)
    return state


def convert_table_headers_to_params(headers):
    params = []
    for header in headers:
        params.append({"name": header, "ptype": "", "value": "header"})
    return params


def query_fom_basics_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug(f"[digikey_nodes] about to query fom basics: {type(state)}, {state}")

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
                "params": [params]
            }
        }

        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_query_fom", {"input": state["tool_input"]})

        tool_result = run_async_in_sync(run_tool_call())

        logger.debug("[digikey_nodes] query fom basics tool call completed:", type(tool_result), tool_result)

        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            state["result"] = tool_result.content[0].text
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None)
            if meta is None:
                meta = getattr(content0, '_meta', None)

            if meta:
                components = meta["components"]
                state["tool_result"] = meta["components"]
            else:
                components = {}
                state["tool_result"] = {}

            if state["tool_result"]:
                i = 0
                component = state["attributes"]["preliminary_info"][i]["part name"]
                fom_form = {
                    "id": "eval_system_form",
                    "type": "score",
                    "title": f'{component} under search on Digikey',
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
                            "tooltip": "lead time/availability of the component",
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
                            "raw_value": {},
                            "weight": 0.4
                        }
                    ]
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
                    "llm_result": "Here is a figure of merit (FOM) form for Digikey component ranking. Please fill it out to define how you want to rank the search results. If you're unsure about certain parameters, just leave them blank. Feel free to ask questions about the meaning and implications of any parameters."}
                send_data_back2human("send_chat", "form", fom_form, state)
        elif hasattr(tool_result, 'isError') and tool_result.isError:
            state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
        else:
            state["error"] = "Unexpected tool result format"

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])

    logger.debug("[digikey_nodes] query_fom_basics_node all done, current state is:", state)
    return state


def local_sort_search_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug(f"[digikey_nodes] about to sort search results: {type(state)}, {state}")

    try:
        table_headers = state["tool_result"]["fom"]["component_level_metrics"]
        header_text = table_headers[0]["metric_name"]
        ascending = True if table_headers[0]["sort_order"] == "asc" else False
        sites = list(state["attributes"]["search_results"].keys())
        i = 0
        state["tool_input"] = {
            "sites": [
                {
                    "url": sites[i],
                    "ascending": ascending,
                    "header_text": header_text,
                    "max_n": 8
                }
            ]
        }

        async def run_tool_call():
            return await mcp_call_tool("ecan_local_sort_search_results", {"input": state["tool_input"]})

        tool_result = run_async_in_sync(run_tool_call())

        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            state["result"] = tool_result.content[0].text
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None)
            if meta is None:
                meta = getattr(content0, '_meta', None)

            if meta:
                state["tool_result"] = meta["results"]
                state["attributes"]["sorted_search_results"] = meta["results"]
            else:
                state["tool_result"] = []
                state["attributes"]["sorted_search_results"] = []

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])

    logger.debug("[digikey_nodes] local_sort_search_results_node all done, current state is:", state)
    return state


def re_rank_search_results_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    logger.debug(f"[digikey_nodes] about to re-rank search results: {state['attributes'].get('search_results', None)}")

    try:
        agent_id = state["messages"][0]
        task_id = state["messages"][3]
        agent = get_agent_by_id(agent_id)
        this_task = next((task for task in agent.tasks if task.id == task_id), None)
        _ = agent.mainwin
    except Exception as e:
        logger.error(f"[digikey_nodes] CRITICAL ERROR in node setup: {e}")
        logger.error(f"[digikey_nodes] State structure: {state}")
        raise e

    existing_cloud_task_id = state["attributes"].get("cloud_task_id")

    try:
        if not existing_cloud_task_id and this_task and hasattr(this_task, 'metadata') and 'state' in this_task.metadata:
            task_state = this_task.metadata['state']
            if isinstance(task_state, dict) and 'attributes' in task_state:
                task_cloud_task_id = task_state['attributes'].get('cloud_task_id')
                if task_cloud_task_id:
                    state["attributes"]["cloud_task_id"] = task_cloud_task_id
                    existing_cloud_task_id = task_cloud_task_id
    except Exception as e:
        logger.error(f"[digikey_nodes] Exception in cloud_task_id detection: {e}")
        existing_cloud_task_id = None

    if existing_cloud_task_id:
        cloud_task_id = existing_cloud_task_id
    else:
        setup = get_default_rerank_req()
        rerank_req = {"agent_id": agent_id, "work_type": "rerank_search_results", "setup": setup}
        state["tool_input"] = rerank_req
        agent.runner.update_event_handler("rerank_search_results", this_task.queue)
        
        async def run_tool_call():
            return await mcp_call_tool("api_ecan_ai_rerank_results", {"input": state["tool_input"]})

        tool_result = run_async_in_sync(run_tool_call())

        if hasattr(tool_result, 'content') and tool_result.content and "completed" in tool_result.content[0].text:
            content0 = tool_result.content[0]
            meta = getattr(content0, 'meta', None)
            if meta is None:
                meta = getattr(content0, '_meta', None)

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

    try:
        interrupted = interrupt({"i_tag": cloud_task_id, "rank_results": {}})
        cloud_results_raw = interrupted.get("notification_to_agent", {})
        if cloud_results_raw:
            try:
                if isinstance(cloud_results_raw, str):
                    import ast
                    cloud_results = ast.literal_eval(cloud_results_raw)
                else:
                    cloud_results = cloud_results_raw
                state["attributes"]["rank_results"] = cloud_results
            except (ValueError, SyntaxError) as e:
                logger.error(f"[digikey_nodes] Failed to parse cloud results: {e}")
                state["attributes"]["rank_results"] = {}

        if state["attributes"].get("rank_results", []):
            notification = convert_rank_results_to_search_results(state)
            state["result"] = {
                "llm_result": "FOM-based ranking complete for Digikey results."
            }
            send_data_back2human("send_chat", "notification", notification, state)

    except Exception as e:
        state['error'] = get_traceback(e, "ErrorReRankSearchResultsNode")
        logger.error(state['error'])

    logger.debug("[digikey_nodes] re_rank_search_results_node all done, current state is:", state)
    return state


def convert_rank_results_to_search_results(state) -> dict:
    try:
        attrs = state.get("attributes", {})
        rank_results = attrs.get("rank_results", {}) or {}
        ranked_list = rank_results.get("ranked_results", []) or []

        full_rows = attrs.get("sorted_search_results")
        if not isinstance(full_rows, list) or not full_rows:
            try:
                from agent.mcp.server.scrapers.eval_util import get_default_rerank_req
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
                                "unit": str(h.get("unit", ""))
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
                "app_specific": []
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
                "products_compared": len(items)
            },
            "behind_the_scene": "",
            "show_feedback_options": True
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
                "products_compared": 0
            },
            "behind_the_scene": "",
            "show_feedback_options": True
        }


def run_local_search_node(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    agent_id = state["messages"][0]
    self_agent = get_agent_by_id(agent_id)
    mainwin = self_agent.mainwin
    logger.debug(f"[digikey_nodes] run_local_search_node: {state}")

    site_categories = state.get("tool_result", {}).get("components", [{}])[0].get("site_categories", [[]])
    in_pfs = state["attributes"].get("filled_parametric_filter", [])
    if in_pfs:
        parametric_filters = [in_pfs.get("fields", [])]
    else:
        parametric_filters = [[]]

    url_short = "digikey"
    state.setdefault("tool_input", {})
    state["tool_input"]["urls"] = site_categories
    state["tool_input"]["parametric_filters"] = parametric_filters
    state["tool_input"]["fom_form"] = {}
    state["tool_input"]["max_n_results"] = 8

    logger.debug(f"[digikey_nodes] tool input::{state['tool_input']}")
    async def run_tool_call():
        return await mcp_call_tool("ecan_local_search_components", {"input": state["tool_input"]})

    tool_result = run_async_in_sync(run_tool_call())
    logger.info("[digikey_nodes] run local search completed:", type(tool_result), tool_result)

    if hasattr(tool_result, 'content') and tool_result.content and hasattr(tool_result.content[0], 'meta'):
        results = tool_result.content[0].meta.get("results", [])
        state["tool_result"] = results
        if state["attributes"].get("search_results", {}):
            state["attributes"]["search_results"][url_short] = results
        else:
            state["attributes"]["search_results"] = {url_short: results}

    return state
