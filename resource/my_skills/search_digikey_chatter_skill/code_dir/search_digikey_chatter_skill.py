"""
External Skill: search_digikey_chatter (flat code_dir layout)

Chats to gather requirements and searches Digikey, ranking results with a user-defined FOM.
This external skill is designed to avoid importing app internals at module import time. All
dependencies are injected via run_context inside build_skill().
"""
from __future__ import annotations
from typing import Any
from config.constants import EXTENDED_API_TIMEOUT

# Dependencies from the host app are injected via _init_from_context(run_context)
# so we avoid importing app modules at import time.

# Use split-out helpers to keep this module lean
from .helpers import (
    chat_or_work as h_chat_or_work,
    is_preliminary_component_info_ready as h_is_preliminary_component_info_ready,
    are_component_specs_filled as h_are_component_specs_filled,
    is_FOM_filled as h_is_FOM_filled,
    llm_node_with_raw_files as h_llm_node_with_raw_files,
    pend_for_human_input_node as h_pend_for_human_input_node,
    pend_for_human_fill_FOM_node as h_pend_for_human_fill_FOM_node,
    pend_for_human_fill_specs_node as h_pend_for_human_fill_specs_node,
    examine_filled_specs_node as h_examine_filled_specs_node,
    confirm_FOM_node as h_confirm_FOM_node,
    re_rank_search_results_node as h_re_rank_search_results_node
)

# Globals to be injected from run_context at runtime
EC_Skill = None
NodeState = None
WorkFlowContext = None
node_builder = None
node_wrapper = None
llm_node_with_raw_files = None
logger = None
get_traceback = None
mcp_call_tool = None
run_async_in_sync = None
try_parse_json = None
get_agent_by_id = None
get_default_rerank_req = None
BreakpointManager = None
build_mcp_tool_calling_node = None
build_pend_event_node = None
StateGraph = None
END = None
Runtime = None
BaseStore = None
GraphInterrupt = None
interrupt = None

def _init_from_context(run_context):
    """Inject dependencies from run_context into module globals."""
    global EC_Skill, NodeState, WorkFlowContext, node_builder, node_wrapper
    global llm_node_with_raw_files, logger, get_traceback
    global mcp_call_tool, run_async_in_sync, try_parse_json
    global get_agent_by_id, get_default_rerank_req, BreakpointManager
    global build_mcp_tool_calling_node, build_pend_event_node
    global StateGraph, END, Runtime, BaseStore, GraphInterrupt, interrupt

    core = run_context.core()
    graph = run_context.graph()
    llm = run_context.llm()
    mcp = run_context.mcp()
    log = run_context.log()

    EC_Skill = core["EC_Skill"]
    WorkFlowContext = core["WorkFlowContext"]
    NodeState = core["NodeState"]
    node_builder = core["node_builder"]
    node_wrapper = core["node_wrapper"]
    BreakpointManager = core["BreakpointManager"]

    StateGraph = graph["StateGraph"]
    END = graph["END"]
    Runtime = graph["Runtime"]
    BaseStore = graph["BaseStore"]
    GraphInterrupt = graph["GraphInterrupt"]
    interrupt = graph["interrupt"]

    llm_node_with_raw_files = llm["llm_node_with_raw_files"]
    run_async_in_sync = llm["run_async_in_sync"]
    try_parse_json = llm["try_parse_json"]

    mcp_call_tool = mcp["mcp_call_tool"]

    logger = log["logger"]
    get_traceback = log["get_traceback"]

    # Items not currently exposed by run_context: import lazily here
    try:
        from agent.agent_service import get_agent_by_id as _get_agent_by_id
        globals()["get_agent_by_id"] = _get_agent_by_id
    except Exception:
        pass
    try:
        from agent.mcp.server.scrapers.eval_util import get_default_rerank_req as _get_default_rerank_req
        globals()["get_default_rerank_req"] = _get_default_rerank_req
    except Exception:
        pass
    try:
        from agent.ec_skills.build_node import build_mcp_tool_calling_node as _b1, build_pend_event_node as _b2
        globals()["build_mcp_tool_calling_node"] = _b1
        globals()["build_pend_event_node"] = _b2
    except Exception:
        pass

THIS_SKILL_NAME = "search_digikey_chatter"
OWNER = "public"
DESCRIPTION = (
    "Chat assistant to search electronic parts on the Digikey website. "
    "Collects specs, builds parametric filters, and ranks results using an FOM (price, lead time, performance)."
)



def send_data_back2human(msg_type, dtype, data, state) -> NodeState:
    import uuid
    import time as _time
    try:
        agent_id = state["attributes"]["agent_id"]
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        logger.debug("[search_digikey_chatter_skill] standard_post_llm_hook send_response_back:", state)
        chat_id = state["attributes"]["chat_id"]
        msg_id = str(uuid.uuid4()),

        if dtype == "form":
            card, code, form, notification = {}, {}, data, {}
            logger.debug("found form in msg:", form)
        elif dtype == "notification":
            card, code, form, notification = {}, {}, [], data
        else:
            card, code, form, notification = {}, {}, [], {}

        llm_result = state.get("result", {}).get("llm_result", "")
        print("llm result:", llm_result)
        agent_response_message = {
            "id": str(uuid.uuid4()),
            "chat": {
                "input": llm_result,
                "attachments": [],
                "messages": [self_agent.card.id, chat_id, msg_id, "", llm_result],
            },
            "attributes": {
                "params": {
                    "content": {
                        "text":llm_result,
                        "mtype": msg_type,
                        "dtype": dtype,
                        "card": card,
                        "code": code,
                        "form": form,
                        "notification": notification,
                    },
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
                    "chatId": chat_id,
                    "status": "success",
                    "ext": "",
                    "human": False,
                },
            }
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
                "application": ",".join(info["applications_usage"]),
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
            # Cloud API query may take 60+ seconds, use longer timeout
            return await mcp_call_tool("api_ecan_ai_query_components", {"input": state["tool_input"]}, timeout=EXTENDED_API_TIMEOUT)

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
        # Safely obtain headers/metrics for sorting
        tool_result = state.get("tool_result") or {}
        fom = (tool_result.get("fom") or {}) if isinstance(tool_result, dict) else {}
        table_headers = (fom.get("component_level_metrics") or []) if isinstance(fom, dict) else []

        header_text = None
        ascending = True
        if isinstance(table_headers, list) and table_headers:
            first_hdr = table_headers[0] or {}
            header_text = first_hdr.get("metric_name") or first_hdr.get("name") or "Price"
            so = first_hdr.get("sort_order")
            if isinstance(so, str) and so in ("asc", "desc"):
                ascending = (so == "asc")
            else:
                # Sensible defaults by metric name
                lname = str(header_text).lower()
                ascending = lname in ("price", "voltage dropout", "voltage dropout (max)")
        else:
            # Fallback when metrics are missing: default to Price ascending
            header_text = "Price"
            ascending = True

        sites = list((state.get("attributes") or {}).get("search_results", {}).keys())
        if not sites:
            logger.debug("[local_sort_search_results_node] no sites to sort; skipping")
            return state
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
    in_pfs = state["metadata"].get("filled_parametric_filter", [])
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



DEFAULT_CHATTER_MAPPING_RULES = [
          {
            "from": ["event.data.params", "event.data.params.metadata.params"],
            "to": [
              {"target": "state.attributes.params"}
            ],
            "on_conflict": "overwrite"
          },
          {
            "from": ["event.data.method", "event.data.params.metadata.method"],
            "to": [
              {"target": "state.attributes.method"}
            ],
            "on_conflict": "overwrite"
          }
    ]

def build_skill(run_context: dict | None = None, mainwin=None) -> EC_Skill:
    """Entry called by build_agent_skills_from_files(); returns an EC_Skill."""
    try:
        # Inject dependencies on first call
        print("building search_digikey_chatter_skill..................")
        _init_from_context(run_context)
        skill = EC_Skill(name=THIS_SKILL_NAME, description=DESCRIPTION)
        skill.mapping_rules["developing"]["mappings"] = DEFAULT_CHATTER_MAPPING_RULES
        skill.mapping_rules["released"]["mappings"] = DEFAULT_CHATTER_MAPPING_RULES

        # Build workflow graph
        wf = StateGraph(NodeState, WorkFlowContext)

        # Breakpoint manager for debug toggles
        bp_manager = BreakpointManager()

        # Chat lane
        wf.add_node("chat", node_builder(h_llm_node_with_raw_files, "chat", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.set_entry_point("chat")

        wf.add_node("pend_for_next_human_msg", node_builder(h_pend_for_human_input_node, "pend_for_next_human_msg", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("more_analysis_app", node_builder(h_llm_node_with_raw_files, "more_analysis_app", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_conditional_edges("chat", h_chat_or_work, ["pend_for_next_human_msg", "more_analysis_app"])
        wf.add_edge("pend_for_next_human_msg", "chat")

        # Collect specs -> query components (prep -> MCP -> post)
        wf.add_node("pend_for_next_human_msg0", node_builder(h_pend_for_human_input_node, "pend_for_next_human_msg0", THIS_SKILL_NAME, OWNER, bp_manager))

        # Prep node: set state.tool_input = {"input": {...}}
        def prep_query_components(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            # attrs = state.get("attributes", {})
            attrs = state.get("result", {}).get("llm_result", {})
            comps = adapt_preliminary_info(attrs.get("preliminary_info", []), attrs.get("extra_info", {}))
            state["tool_input"] = {"input": {"components": comps}}
            state["metadata"]["components"] = comps
            return state

        wf.add_node("prep_query_components", node_builder(prep_query_components, "prep_query_components", THIS_SKILL_NAME, OWNER, bp_manager))
        from config.constants import EXTENDED_API_TIMEOUT
        wf.add_node("mcp_query_components", build_mcp_tool_calling_node({"tool_name": "api_ecan_ai_query_components", "timeout": EXTENDED_API_TIMEOUT}, "mcp_query_components", THIS_SKILL_NAME, OWNER, bp_manager))

        # extract out paraetric filters
        def post_query_components(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                tool_result = state.get("tool_result", {})
                logger.debug("post_query_components tool results:", tool_result)
                if (hasattr(tool_result, 'content') and
                        tool_result.content and
                        len(tool_result.content) > 0 and
                        hasattr(tool_result.content[0], 'text') and
                        tool_result.content[0].text and
                        "completed" in tool_result.content[0].text):
                    logger.debug("processing tool result....")
                    content0 = tool_result.content[0]
                    logger.debug("processing tool result....content0:", content0)
                    meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
                    logger.debug("processing tool result....meta:", meta)
                    state["tool_result"] = meta
                    state["metadata"]["components"] = meta.get("components", []) if meta else []
                    components = meta.get("components", []) if isinstance(meta, dict) else meta
                    parametric_filters = []
                    logger.debug("processing tool result....components:", components)
                    if isinstance(components, list) and components:
                        logger.debug("processing tool result....parametric_filters:")
                        parametric_filters = components[0].get('parametric_filters', []) or []

                    # Handle empty results - send friendly message instead of empty form
                    if not components or not parametric_filters:
                        # Get component name from tool_input (metadata gets overwritten by result)
                        input_comps = state.get("tool_input", {}).get("input", {}).get("components") or []
                        component_name = input_comps[0].get("name", "the component") if input_comps else "the component"
                        
                        # Detect language
                        try:
                            from utils.i18n_helper import detect_language
                            lang = detect_language()
                        except Exception:
                            lang = 'en'
                        
                        if lang == 'zh-CN':
                            no_result_msg = (
                                f"抱歉，我在数据库中找不到关于 '{component_name}' 的任何匹配组件。\n"
                                f"可能的原因：\n"
                                f"1. 组件名称过于笼统或不是标准的电子元件名称\n"
                                f"2. 尝试使用英文关键词（如 'capacitor', 'resistor'）\n"
                                f"3. 如果有具体的零件编号，请尝试使用零件编号"
                            )
                        else:
                            no_result_msg = (
                                f"Sorry, I couldn't find any matching components for '{component_name}'. "
                                f"Try using more specific terms or part numbers."
                            )
                        state["result"] = {"llm_result": no_result_msg}
                        send_data_back2human("send_chat", "text", {}, state)
                        logger.info(f"[post_query_components] No results for '{component_name}'")
                    else:
                        fe_parametric_filter = {
                            "id": "technical_query_form",
                            "type": "normal",
                            "title": components[0].get('title', 'Component under search') if isinstance(components, list) and components else 'Component under search',
                            "fields": parametric_filters,
                        }
                        state["result"] = {"llm_result": "Here is a parametric search filter form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."}

                        logger.debug("parametric filter info:", fe_parametric_filter)
                        send_data_back2human("send_chat", "form", fe_parametric_filter, state)
                elif hasattr(tool_result, 'isError') and tool_result.isError:
                    state["error"] = tool_result.content[0].text if tool_result.content else "Unknown error occurred"
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostQueryComponents")
            return state

        wf.add_node("post_query_components", node_builder(post_query_components, "post_query_components", THIS_SKILL_NAME, OWNER, bp_manager))

        wf.add_conditional_edges("more_analysis_app", h_is_preliminary_component_info_ready, ["prep_query_components", "pend_for_next_human_msg0"])
        wf.add_edge("pend_for_next_human_msg0", "more_analysis_app")
        wf.add_edge("prep_query_components", "mcp_query_components")
        wf.add_edge("mcp_query_components", "post_query_components")

        # Human fills specs
        wf.add_node("pend_for_human_input_fill_specs", node_builder(h_pend_for_human_fill_specs_node, "pend_for_human_input_fill_specs", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("post_query_components", "pend_for_human_input_fill_specs")
        wf.add_node("examine_filled_specs", node_builder(h_examine_filled_specs_node, "examine_filled_specs", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("pend_for_next_human_msg1", node_builder(h_pend_for_human_input_node, "pend_for_next_human_msg1", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("pend_for_human_input_fill_specs", "examine_filled_specs")

        # Local search (Digikey): prep -> MCP -> post
        def prep_run_search(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                logger.debug("prep_run_search------------------->", state)
                # Get site_categories safely
                components = state.get("metadata", {}).get("components") or []
                site_categories = components[0].get("site_categories", {}) if components else {}
                logger.debug("site_categories:", site_categories)
                in_pfs = state.get("metadata", {}).get("filled_parametric_filter", {})
                if in_pfs:
                    parametric_filters = [in_pfs.get("fields", [])]
                else:
                    parametric_filters = [[]]

                fom_form = {}
                if "fom_template" in state["tool_result"]:
                    if "fom" in state["tool_result"]["fom_template"]:
                        fom_form =state["tool_result"]["fom_template"]["fom"]

                components = [{}]
                if "component_results_info" in state["tool_input"]["input"]:
                    if isinstance(state["tool_input"]["input"]["component_results_info"], list):
                        components = state["tool_input"]["input"]["component_results_info"]
                    else:
                        components = [state["tool_input"]["input"]["component_results_info"]]

                body = {
                    "components": components,
                    "urls": site_categories,
                    "parametric_filters": parametric_filters,
                    "fom_form": fom_form,
                    "max_n_results": 8,
                }
                state["tool_input"] = {"input": body}
                logger.debug("prep_run_search tool input:", state["tool_input"])

            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPrepRunSearch")

            return state

        wf.add_node("prep_run_search", node_builder(prep_run_search, "prep_run_search", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_run_search", build_mcp_tool_calling_node({"tool_name": "ecan_local_search_components"}, "mcp_run_search", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_run_search(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                logger.debug("post_run_search state:", state)

                tr = state.get("tool_result", None)
                if hasattr(tr, 'content') and tr.content:
                    meta = getattr(tr.content[0], 'meta', None) or getattr(tr.content[0], '_meta', None)
                    if isinstance(meta, dict):
                        print("post_run_search meta:", meta)
                        rows = meta.get("results")
                        state["tool_result"] = rows
                        url_short = "digikey"
                        attrs = state.setdefault("attributes", {})
                        if isinstance(attrs.get("search_results"), dict):
                            logger.debug("post_run_search attrs, add search results")
                            attrs["search_results"][url_short] = rows
                        else:
                            logger.debug("post_run_search attrs, set search results")
                            attrs["search_results"] = {url_short: rows}

                        logger.debug("post_run_search attrs:", state["attributes"].get("search_results"))
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostRunSearch")
            return state

        wf.add_node("post_run_search", node_builder(post_run_search, "post_run_search", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_conditional_edges("examine_filled_specs", h_are_component_specs_filled, ["prep_run_search", "pend_for_next_human_msg1"])
        # wf.add_conditional_edges("examine_filled_specs", h_are_component_specs_filled, ["prep_query_fom", "pend_for_next_human_msg1"])

        wf.add_edge("prep_run_search", "mcp_run_search")
        wf.add_edge("mcp_run_search", "post_run_search")
        wf.add_edge("pend_for_next_human_msg1", "examine_filled_specs")

        # FOM: prep -> MCP -> post
        wf.add_edge("post_run_search", "prep_query_fom")

        def prep_query_fom(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                logger.debug("prep_query_fom..........................>", state)
                # Get tool_result safely - could be dict, list, or CallToolResult
                tool_result = state.get("tool_result")
                tool_result_data = []
                if isinstance(tool_result, dict):
                    tool_result_data = [tool_result] if tool_result else []
                elif isinstance(tool_result, list):
                    tool_result_data = tool_result
                elif hasattr(tool_result, 'content'):
                    # CallToolResult object
                    try:
                        meta = getattr(tool_result.content[0], 'meta', None) or {}
                        tool_result_data = meta.get('results', []) if isinstance(meta, dict) else []
                    except (IndexError, AttributeError):
                        tool_result_data = []
                
                table_headers = list(tool_result_data[0].keys()) if tool_result_data and isinstance(tool_result_data[0], dict) else []
                if table_headers:
                    print("table headers:", table_headers)
                    params = convert_table_headers_to_params(table_headers)
                    print("params:", table_headers)
                else:
                    print("WARNING: table headers not found!")
                    params = []

                # components= state.get("tool_input", {}).get("input", {}).get("components", [])
                # if not components:
                components = state.get("metadata", {}).get("components", [])
                logger.debug("prep_query_fom components:", components)

                if components:
                    component_name = components[0]["title"]
                    component_app = components[0].get("application", "")
                    print("components:", components)
                    state["tool_input"] = {"input": {
                        "component_results_info": {
                            "component_name": component_name,
                            "product_app": component_app,
                            "max_product_metrics": 3,
                            "max_component_metrics": 3,
                            "params": [params],
                        }
                    }}
                    print("ready to query fom")
                else:
                    err_msg = "ErrorPrepQueryFOM: No component to work on....."
                    state['error'] = err_msg
            except Exception as e:
                err_msg = get_traceback(e, "ErrorPrepQueryFOM")
                state['error'] = err_msg
                logger.error(err_msg)
            return state

        wf.add_node("prep_query_fom", node_builder(prep_query_fom, "prep_query_fom", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_query_fom", build_mcp_tool_calling_node({"tool_name": "api_ecan_ai_query_fom"}, "mcp_query_fom", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_query_fom(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                print("post_query_fom===============================>")
                tool_result = state.get("tool_result", {})
                logger.debug("post_query_fom tool results:", tool_result)
                if (hasattr(tool_result, 'content') and
                        tool_result.content and
                        len(tool_result.content) > 0 and  # Add this check!
                        hasattr(tool_result.content[0], 'text') and
                        tool_result.content[0].text and
                        "completed" in tool_result.content[0].text):
                    logger.debug("processing tool result....")
                    content0 = tool_result.content[0]
                    logger.debug("processing tool result....content0:", content0)
                    meta = getattr(content0, 'meta', None) or getattr(content0, '_meta', None)
                    logger.debug("processing tool result....meta:", meta)
                    state["tool_result"] = meta
                    fom_template = meta.get("fom_template", []) if isinstance(meta, dict) else meta
                    parametric_filters = []
                    if fom_template:
                        attrs = state.get("attributes", {})
                        i = 0
                        component = (attrs.get("preliminary_info") or [{}])[i].get("part name")
                        fom_form = {
                            "id": "eval_system_form",
                            "type": "score",
                            "title": f"{component} under search",
                            "components": [
                                {
                                    "name": fom_template["fom"]["price_parameter"],
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
                                    "name": fom_template["fom"]["lead_time_parameter"],
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
                        for fom_item in fom_template["fom"]["component_level_metrics"]:
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
                err_msg = get_traceback(e, "ErrorPostQueryFOM")
                logger.error(f"{err_msg}")
                state['error'] = err_msg
            return state

        wf.add_node("post_query_fom", node_builder(post_query_fom, "post_query_fom", THIS_SKILL_NAME, OWNER, bp_manager))

        wf.add_edge("prep_query_fom", "mcp_query_fom")
        wf.add_edge("mcp_query_fom", "post_query_fom")
        wf.add_edge("post_query_fom", "pend_for_human_input_fill_FOM")
        wf.add_node("pend_for_human_input_fill_FOM", node_builder(h_pend_for_human_fill_FOM_node, "pend_for_human_input_fill_FOM", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("confirm_FOM", node_builder(h_confirm_FOM_node, "confirm_FOM", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_edge("pend_for_human_input_fill_FOM", "confirm_FOM")

        # Sort: prep -> MCP -> post
        def prep_local_sort(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                print("prep local sort..........", state)
                # Pull potential headers/metrics from tool_result
                tool_result = state.get("tool_result", {}).get("fom_template", {})
                logger.debug("[prep_local_sort] tool_result: ", tool_result)
                fom = (tool_result.get("fom") or {}) if isinstance(tool_result, dict) else {}
                logger.debug("[prep_local_sort] fom: ", fom)
                table_headers = (fom.get("component_level_metrics") or []) if isinstance(fom, dict) else []
                logger.debug("[prep_local_sort] table_headers: ", table_headers)

                # Choose header and sort direction with safe defaults
                header_text = "Price"
                ascending = True
                if isinstance(table_headers, list) and table_headers:
                    first_hdr = table_headers[0] or {}
                    header_text = first_hdr.get("metric_name") or first_hdr.get("name") or "Price"
                    so = first_hdr.get("sort_order")
                    logger.debug("[prep_local_sort] header_text: %s, sort_order: %s", header_text, so)
                    if isinstance(so, str) and so in ("asc", "desc"):
                        ascending = (so == "asc")
                    else:
                        lname = str(header_text).lower()
                        ascending = lname in ("price", "voltage dropout", "voltage dropout (max)")

                # Collect sites from prior local search results
                sites = list((state.get("attributes") or {}).get("search_results", {}).keys())
                if not sites:
                    logger.debug("[prep_local_sort] no sites available; skipping sort prep")
                    return state

                i = 0
                body = {
                    "sites": [
                        {"url": sites[i], "ascending": ascending, "header_text": header_text, "max_n": 8}
                    ]
                }
                state["tool_input"] = {"input": body}
                print("prep local sort......tool input:", state["tool_input"])
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPrepLocalSort")
            return state

        wf.add_node("prep_local_sort", node_builder(prep_local_sort, "prep_local_sort", THIS_SKILL_NAME, OWNER, bp_manager))
        wf.add_node("mcp_local_sort", build_mcp_tool_calling_node({"tool_name": "ecan_local_sort_search_results"}, "mcp_local_sort", THIS_SKILL_NAME, OWNER, bp_manager))

        def post_local_sort(state: NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
            try:
                logger.debug("post_local_sort................", state)
                results = state.get("results", [])
                tr = results[-1] if results else None
                if hasattr(tr, 'content') and tr.content:
                    print("checking content.....")
                    meta = getattr(tr.content[0], 'meta', None) or getattr(tr.content[0], '_meta', None)
                    if isinstance(meta, dict):
                        print("checking meta results.....")
                        rows = meta.get("results")
                        state["tool_result"] = rows
                        state.setdefault("attributes", {}).setdefault("sorted_search_results", rows)

                logger.debug("post_local_sort................done!")
            except Exception as e:
                state['error'] = get_traceback(e, "ErrorPostLocalSort")
            return state

        wf.add_node("post_local_sort", node_builder(post_local_sort, "post_local_sort", THIS_SKILL_NAME, OWNER, bp_manager))

        # Re-rank remains custom due to interrupt + cloud handoff
        wf.add_node("re_rank_search_results", node_builder(h_re_rank_search_results_node, "re_rank_search_results", THIS_SKILL_NAME, OWNER, bp_manager))
        # Start at chat to collect requirements; breakpoint wrappers enable graphical debugging


        # wf.add_conditional_edges("confirm_FOM", h_is_FOM_filled, ["prep_run_search", "pend_for_human_input_fill_FOM"])
        # wf.add_edge("post_run_search", END)
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

        logger.info(f"[search_digikey_chatter_skill] Built skill {THIS_SKILL_NAME}", skill.name, skill.id, skill.mapping_rules)
        return skill
    except Exception as e:
        logger.error(get_traceback(e, "ErrorBuildSearchDigikeyChatterSkill"))
        return None
