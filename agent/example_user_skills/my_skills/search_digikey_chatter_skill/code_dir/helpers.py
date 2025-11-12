"""
Helper nodes and utilities for search_digikey_chatter external skill.
Self-contained to avoid importing internal skill modules.
"""
from typing import Any
import uuid
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.ec_skill import NodeState, WorkFlowContext
from agent.agent_service import get_agent_by_id
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync, try_parse_json
from agent.mcp.server.scrapers.eval_util import get_default_rerank_req


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


## Removed: query_component_specs_node is now implemented via prep/mcp/post in search_digikey_chatter_skill.py


def convert_table_headers_to_params(headers):
    params = []
    for header in headers:
        params.append({"name": header, "ptype": "", "value": "header"})
    return params


## Removed: query_fom_basics_node is now implemented via prep/mcp/post in search_digikey_chatter_skill.py


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


## Removed: run_local_search_node is now implemented via prep/mcp/post in search_digikey_chatter_skill.py


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
        # Common node tag/name patterns to reject as cloud task ids
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
                # Guard against mistakenly mapped node tags
                if task_cloud_task_id and not _is_node_tag_like(task_cloud_task_id):
                    state["attributes"]["cloud_task_id"] = task_cloud_task_id
                    existing_cloud_task_id = task_cloud_task_id
                elif task_cloud_task_id:
                    logger.debug(f"[search_digikey_chatter_skill] Discarding node-tag-like task_cloud_task_id from metadata: {task_cloud_task_id}")
        if existing_cloud_task_id and not _is_node_tag_like(existing_cloud_task_id):
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
