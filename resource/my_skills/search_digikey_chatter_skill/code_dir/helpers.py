"""
Helper nodes and utilities for search_digikey_chatter external skill.
Self-contained to avoid importing internal skill modules.
"""
from typing import Any
import uuid
import json
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.ec_skill import NodeState, WorkFlowContext
from agent.agent_service import get_agent_by_id
from agent.mcp.local_client import mcp_call_tool
from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync, try_parse_json, get_standard_prompt, build_a2a_response_message
from agent.ec_skills.llm_hooks.llm_hooks import run_pre_llm_hook, run_post_llm_hook
from agent.mcp.server.scrapers.eval_util import get_default_rerank_req


def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[search_digikey_chatter_skill] chat_or_work input:", state)
    if isinstance(state["result"].get('llm_result', None), dict) and state["result"].get('llm_result', {}).get("work_related", False):
        return "more_analysis_app"
    return "pend_for_next_human_msg"


def is_preliminary_component_info_ready(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("[search_digikey_chatter_skill] is_preliminary_component_info_ready input:", state)

    llm_result = state.get('result', {}).get('llm_result', {})
    
    # Only proceed when LLM explicitly confirms (human_confirmed=true)
    # This ensures the LLM has processed user input and determined it's ready to search
    if llm_result.get('human_confirmed'):
        logger.debug("[search_digikey_chatter_skill] human_confirmed=True, proceeding to prep_query_components")
        return "prep_query_components"
    
    # Default: wait for more input from user
    logger.debug("[search_digikey_chatter_skill] human_confirmed=False, waiting for more input")
    return "pend_for_next_human_msg0"


def are_component_specs_filled(state: NodeState) -> str:
    logger.debug("[search_digikey_chatter_skill] are_component_specs_filled input:", state)
    return "prep_run_search" if state.get('condition') else "pend_for_next_human_msg1"


def is_FOM_filled(state: NodeState) -> str:
    logger.debug("[search_digikey_chatter_skill] is_FOM_filled input:", state)
    # return "prep_local_sort" if state.get('condition') else "pend_for_human_input_fill_FOM"
    return "prep_local_sort" if state.get('condition') else "pend_for_human_input_fill_FOM"


def has_parametric_filters(state: dict) -> bool:
    try:
        return "filled_parametric_filter" in state["metadata"]
    except (KeyError, IndexError, TypeError):
        return False

def extract_first_non_none_content_meta_dict(tr: dict) -> dict | None:
    for part in (tr.get("content") or []):
        meta = part.get("meta")
        if meta:
            return meta
    return None


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


# Token limit for context window (adjust based on your model's limits and cost considerations)
CONTEXT_WINDOW_SIZE = 25536  # Conservative limit for GPT-4


def get_recent_context(history: list, max_tokens: int = CONTEXT_WINDOW_SIZE) -> list:
    """
    Returns a subset of chat history that fits within the token limit.
    
    Strategy:
    1. Always include the most recent SystemMessage (if exists) for context
    2. Include as many recent messages as possible within the token limit
    3. Estimate ~4 characters per token (conservative estimate)
    
    Args:
        history: List of LangChain message objects (SystemMessage, HumanMessage, AIMessage)
        max_tokens: Maximum number of tokens to include
        
    Returns:
        List of messages that fit within the token limit
    """
    if not history or not isinstance(history, list):
        return []
    
    from langchain_core.messages import SystemMessage
    
    # Simple token estimation: ~4 chars per token (conservative)
    def estimate_tokens(msg) -> int:
        try:
            content = msg.content if hasattr(msg, 'content') else str(msg)
            return len(str(content)) // 4
        except Exception:
            return 0
    
    # Find the most recent SystemMessage
    system_msg = None
    system_msg_idx = -1
    for idx in range(len(history) - 1, -1, -1):
        if isinstance(history[idx], SystemMessage):
            system_msg = history[idx]
            system_msg_idx = idx
            break
    
    # Start with system message if it exists and fits
    result = []
    token_count = 0
    
    if system_msg:
        system_tokens = estimate_tokens(system_msg)
        if system_tokens < max_tokens:
            result.append(system_msg)
            token_count += system_tokens
    
    # Add messages from the end (most recent) going backwards
    # Skip the system message if we already added it
    for idx in range(len(history) - 1, -1, -1):
        if idx == system_msg_idx:
            continue  # Already added
        
        msg = history[idx]
        msg_tokens = estimate_tokens(msg)
        
        if token_count + msg_tokens > max_tokens:
            break  # Would exceed limit
        
        result.insert(1 if system_msg else 0, msg)  # Insert after system message
        token_count += msg_tokens
    
    logger.debug(f"Context window: {len(result)} messages, ~{token_count} tokens (limit: {max_tokens})")
    return result


def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    try:
        print("extern:: in llm_node_with_raw_files....", state)
        user_input = state.get("input", "")
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        print("run time:", json.dumps(runtime.context, indent=4))
        current_node_name = runtime.context["this_node"].get("name")
        skill_name = runtime.context["this_node"].get("skill_name")
        owner = runtime.context["this_node"].get("owner")

        # print("current node:", current_node)
        nodes = [{"askid": "skid0", "name": current_node_name}]
        full_node_name = f"{owner}:{skill_name}:{current_node_name}"
        run_pre_llm_hook(full_node_name, agent, state)

        print("networked prompts:", state["prompts"])
        node_prompt = state["prompts"]

        # mm_content = prep_multi_modal_content(state, runtime)
        # langchain_prompt = ChatPromptTemplate.from_messages(node_prompt)
        # formatted_prompt = langchain_prompt.format_messages(component_info=state["input"], categories=state["attributes"]["categories"])

        # if state["formatted_prompts"]:
        #     formatted_prompt = state["formatted_prompts"][-1]
        # else:
        #     formatted_prompt = get_standard_prompt(state)            #STARDARD_PROMPT

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        # This ensures API keys are properly configured from the system's LLM manager
        llm = mainwin.llm if mainwin and mainwin.llm else None
        if not llm:
            raise ValueError("LLM not available in mainwin. Please configure LLM provider API key in Settings.")

        # Get recent context within token limit to reduce costs and fit within model limits
        recent_context = get_recent_context(state.get("history", []))
        print("chat node: llm prompt ready with", len(recent_context), "messages in context")
        print("recent_context:", recent_context)
        response = llm.invoke(recent_context)
        print("chat node: LLM response:", response)
        # Parse the response
        run_post_llm_hook(full_node_name, agent, state, response)
        print("llm_node_with_raw_file exiting.....", state)
        return state
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.error(err_trace)
        state["result"] = {"error": err_trace}
        return state


def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[search_digikey_chatter_skill] runtime:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug(f"[search_digikey_chatter_skill] pend_for_human_input_node>: {current_node_name}", state)
    if state.get("metadata"):
        qa_form = state.get("metadata").get("qa_form", {})
        notification = state.get("metadata").get("notification", {})
    else:
        qa_form = {}
        notification = {}

    logger.debug(f"qa form: {qa_form}, notification, {notification}, result:, {state['result']}")

    llm_result = state.get("result", {}).get("llm_result", "")
    if isinstance(llm_result, str):
        prompt_to_human = llm_result
    elif isinstance(llm_result, dict):
        prompt_to_human = llm_result.get("next_prompt") or llm_result.get("casual_chat_response", "")
    else:
        prompt_to_human = ""

    resume_payload = interrupt({
        "i_tag": current_node_name,
        "prompt_to_human": prompt_to_human,
        "qa_form_to_human": qa_form,
        "notification_to_human": notification,
    })

    # If resumer supplied a state patch (e.g., via Command(resume={... "_state_patch": {...}})), merge it
    try:
        if isinstance(resume_payload, dict) and "_state_patch" in resume_payload:
            patch = resume_payload.get("_state_patch")
            if isinstance(patch, dict):
                def _deep_merge(a: dict, b: dict) -> dict:
                    out = dict(a)
                    for k, v in b.items():
                        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                            out[k] = _deep_merge(out[k], v)
                        else:
                            out[k] = v
                    return out
                # merge patch into state in place
                try:
                    if isinstance(state, dict):
                        merged = _deep_merge(state, patch)
                        state.clear()
                        state.update(merged)
                except Exception:
                    pass
    except Exception:
        pass

    logger.debug("[search_digikey_chatter_skill] node resume payload received:", resume_payload)
    logger.debug("[search_digikey_chatter_skill] node resumed, state:", state)

    # Normalize human_text: it may be a list with one JSON string, a string, or already a dict
    raw_ht = resume_payload.get("human_text")
    if isinstance(raw_ht, list):
        raw_ht = raw_ht[0] if raw_ht else None
    if isinstance(raw_ht, dict):
        data = raw_ht
    else:
        data = try_parse_json(raw_ht)

    # Ensure metadata container exists
    state.setdefault("metadata", {})

    if isinstance(data, dict):
        if data.get("type", "") == "normal":
            logger.debug("[search_digikey_chatter_skill] saving filled parametric filter form......")
            state["metadata"]["filled_parametric_filter"] = data
        elif data.get("type", "") == "score":
            logger.debug("[search_digikey_chatter_skill] saving filled fom form......")
            state["metadata"]["filled_fom_form"] = data

    return state


def pend_for_human_fill_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node state:", state)

    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node run time:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node:", current_node_name, state)
    if state.get("metadata"):
        qa_form = state.get("metadata").get("qa_form", None)
        notification = state.get("metadata").get("notification", None)
    else:
        qa_form = None
        notification = None

    resume_payload = interrupt({
        "i_tag": current_node_name,
        "qa_form_to_human": qa_form,
        "notification_to_human": notification,
    })
    # If resumer supplied a state patch (e.g., via Command(resume={... "_state_patch": {...}})), merge it
    try:
        if isinstance(resume_payload, dict) and "_state_patch" in resume_payload:
            patch = resume_payload.get("_state_patch")
            if isinstance(patch, dict):
                def _deep_merge(a: dict, b: dict) -> dict:
                    out = dict(a)
                    for k, v in b.items():
                        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                            out[k] = _deep_merge(out[k], v)
                        else:
                            out[k] = v
                    return out

                # merge patch into state in place
                try:
                    if isinstance(state, dict):
                        merged = _deep_merge(state, patch)
                        state.clear()
                        state.update(merged)
                except Exception:
                    pass
    except Exception:
        pass

    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node resume payload received:",
                 resume_payload)
    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node resumed, state:", state)

    # Normalize human_text and parse
    raw_ht = resume_payload.get("human_text")
    if isinstance(raw_ht, list):
        raw_ht = raw_ht[0] if raw_ht else None
    if isinstance(raw_ht, dict):
        data = raw_ht
    else:
        data = try_parse_json(raw_ht)
    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_FOM_node resumed, data:", data)

    state.setdefault("metadata", {})

    if isinstance(data, dict):
        if data.get("type", "") == "normal":
            state["metadata"]["filled_parametric_filter"] = data
            logger.debug("[search_digikey_chatter_skill] saving filled parametric filter form......",
                         state["metadata"]["filled_parametric_filter"])
        elif data.get("type", "") == "score":
            state["metadata"]["filled_fom_form"] = data
            logger.debug("[search_digikey_chatter_skill] saving filled fom form......",
                         state["metadata"]["filled_fom_form"])

    return state


def pend_for_human_fill_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[search_digikey_chatter_skill] runtime:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug(f"[search_digikey_chatter_skill] pend_for_human_input_node>: {current_node_name}", state)
    if state.get("metadata"):
        qa_form = state.get("metadata").get("qa_form", {})
        notification = state.get("metadata").get("notification", {})
    else:
        qa_form = {}
        notification = {}

    logger.debug(f"qa form: {qa_form}, notification, {notification}, result:, {state['result']}")

    resume_payload = interrupt({
        "i_tag": current_node_name,
        "qa_form_to_human": qa_form,
        "notification_to_human": notification,
    })

    # If resumer supplied a state patch (e.g., via Command(resume={... "_state_patch": {...}})), merge it
    try:
        if isinstance(resume_payload, dict) and "_state_patch" in resume_payload:
            patch = resume_payload.get("_state_patch")
            if isinstance(patch, dict):
                def _deep_merge(a: dict, b: dict) -> dict:
                    out = dict(a)
                    for k, v in b.items():
                        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                            out[k] = _deep_merge(out[k], v)
                        else:
                            out[k] = v
                    return out

                # merge patch into state in place
                try:
                    if isinstance(state, dict):
                        merged = _deep_merge(state, patch)
                        state.clear()
                        state.update(merged)
                except Exception:
                    pass
    except Exception:
        pass

    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_specs_nodenode resume payload received:", resume_payload)
    logger.debug("[search_digikey_chatter_skill] pend_for_human_fill_specs_nodenode resumed, state:", state)

    # Normalize human_text and parse
    raw_ht = resume_payload.get("human_text")
    if isinstance(raw_ht, list):
        raw_ht = raw_ht[0] if raw_ht else None
    if isinstance(raw_ht, dict):
        data = raw_ht
    else:
        data = try_parse_json(raw_ht)
    state.setdefault("metadata", {})
    if isinstance(data, dict):
        if data.get("type", "") == "normal":
            state["metadata"]["filled_parametric_filter"] = data
            logger.debug("[search_digikey_chatter_skill] saving filled parametric filter form......", state["metadata"]["filled_parametric_filter"])
        elif data.get("type", "") == "score":
            state["metadata"]["filled_fom_form"] = data
            logger.debug("[search_digikey_chatter_skill] saving filled fom form......", state["metadata"]["filled_fom_form"])

    return state

def _extract_fields(parametric_filters):
    # cases:
    # 1) dict with 'fields'
    if isinstance(parametric_filters, dict) and "fields" in parametric_filters:
        return parametric_filters["fields"]

    # 2) list whose first element is dict with 'fields'
    if isinstance(parametric_filters, list) and parametric_filters:
        first = parametric_filters[0]
        if isinstance(first, dict) and "fields" in first:
            return first["fields"]
        # 3) list of field dicts directly
        if all(isinstance(x, dict) and "id" in x for x in parametric_filters):
            return parametric_filters

    # 4) try common resume locations if you pass the larger state chunk
    try:
        return (
            (((parametric_filters.get("attributes") or {}).get("params") or {})
             .get("metadata") or {}).get("params", {})
        ).get("formData", {}).get("fields", [])
    except Exception:
        return []


def examine_filled_specs_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    logger.debug("[search_digikey_chatter_skill] examine filled specs node.......", state)
    pf_exists = has_parametric_filters(state)
    if pf_exists:
        parametric_filters = state["metadata"]["filled_parametric_filter"]
        print("pf_exists...", state["metadata"])
    else:
        print("pf not exists in state...")
        parametric_filters = []

    logger.debug("[search_digikey_chatter_skill] parametric_filters", parametric_filters)
    fields = _extract_fields(parametric_filters)
    logger.debug("[search_digikey_chatter_skill] parametric_filters fields", fields)

    if is_form_filled(fields):
        state["condition"] = True
    else:
        state["condition"] = False

    logger.debug("[search_digikey_chatter_skill] is_form_filled", state["condition"])
    return state


def confirm_FOM_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    logger.debug("[search_digikey_chatter_skill] confirm FOM node.......", state)
    fom_exists = has_fom(state)
    if fom_exists:
        fom = state["tool_result"]["components"][0]["metadata"].get("parametric_filters", [])
        state["metadata"]["fom"] = fom
        state["metadata"]["filled_fom"] = fom
    else:
        fom = []
        state["metadata"]["filled_fom"] = fom

    print("filled fom form:", fom)
    if is_form_filled(fom):
        state["condition"] = True
    else:
        state["condition"] = False

    print("is fom form filled:", state["condition"])
    return state


def send_data_back2human(msg_type, dtype, data, state) -> NodeState:
    try:
        agent_id = state["messages"][0]
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        logger.debug("[search_digikey_chatter_skill] send_data_back2human:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4())
        llm_result = state.get("result", {}).get("llm_result", "")

        # Determine form/notification data
        form = data if dtype == "form" else None
        notification = data if dtype == "notification" else None

        # Use standardized message builder
        agent_response_message = build_a2a_response_message(
            agent_id=self_agent.card.id,
            chat_id=chat_id,
            msg_id=msg_id,
            task_id="",
            msg_text=llm_result,
            sender_name=self_agent.card.name,
            msg_type=dtype,
            attachments=state.get("attachments", []),
            form=form,
            notification=notification,
        )
        logger.debug("[search_digikey_chatter_skill] sending response msg back to twin:", agent_response_message)
        # Use non-blocking send to avoid deadlock
        send_result = self_agent.a2a_send_chat_message_async(twin_agent, agent_response_message)
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
        logger.debug("convert_rank_results:", attrs)
        rank_results = attrs.get("rank_results", {}) or {}
        ranked_list = rank_results.get("ranked_results", []) or []
        full_rows = attrs.get("re_ranked_rows")
        if not isinstance(full_rows, list) or not full_rows:
            full_rows = attrs.get("sorted_search_results")
        if not isinstance(full_rows, list) or not full_rows:
            try:
                full_rows = get_default_rerank_req().get("rows", [])
            except Exception:
                full_rows = []
        has_reranked = isinstance(attrs.get("re_ranked_rows"), list) and bool(attrs.get("re_ranked_rows"))

        prelim = (attrs.get("preliminary_info") or [{}])
        prelim0 = prelim[0] if prelim and isinstance(prelim, list) else {}
        component_name = prelim0.get("part name", "Component")
        items = []
        for pos, entry in enumerate(ranked_list, start=1):
            row_index = entry.get("row_index")
            total_score = entry.get("total_score", 0)
            row_data_short = entry.get("row_data", {}) or {}
            full_row = {}
            if has_reranked:
                if 0 <= (pos - 1) < len(full_rows):
                    full_row = full_rows[pos - 1] or {}
            else:
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
        print("notification ready.....")
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

    # Add these diagnostics to match your log style
    logger.debug(">>BEFORE guard existing_cloud_task_id: %s", existing_cloud_task_id)

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
        if s in {
            "chat", "more_analysis_app", "prep_query_components", "query_component_specs",
            "pend_for_next_human_msg", "pend_for_next_human_msg0", "pend_for_next_human_msg1",
            "pend_for_next_human_msg2", "pend_for_human_input_fill_specs",
            "pend_for_human_input_fill_fom", "local_sort_search_results", "prep_local_sort"
        }:
            return True
        return False

    if _is_node_tag_like(existing_cloud_task_id):
        logger.debug(">>DISCARD node-tag existing_cloud_task_id: %s", existing_cloud_task_id)
        existing_cloud_task_id = None

    logger.debug(">>existing_cloud_task_id:", existing_cloud_task_id)
    try:
        if not existing_cloud_task_id and this_task and hasattr(this_task, 'metadata') and 'state' in this_task.metadata:
            task_state = this_task.metadata['state']
            if isinstance(task_state, dict) and 'attributes' in task_state:
                task_cloud_task_id = task_state['attributes'].get('cloud_task_id')
                print("task_cloud_task_id:", task_cloud_task_id)

                if task_cloud_task_id and not _is_node_tag_like(task_cloud_task_id):
                    state["attributes"]["cloud_task_id"] = task_cloud_task_id
                    existing_cloud_task_id = task_cloud_task_id
                elif task_cloud_task_id:
                    logger.debug(">>DISCARDED node-tag-like metadata cloud_task_id: %s", task_cloud_task_id)

        logger.debug("existing_cloud_task_id again:", existing_cloud_task_id)
        if existing_cloud_task_id and not _is_node_tag_like(existing_cloud_task_id):
            cloud_task_id = existing_cloud_task_id
        else:
            print("no existing cloud task id....")
            setup = get_default_rerank_req()
            rerank_req = {"agent_id": agent_id, "work_type": "rerank_search_results", "setup": setup}
            state["tool_input"] = rerank_req
            agent.runner.update_event_handler("rerank_search_results", this_task.queue)

            async def run_tool_call():
                return await mcp_call_tool("api_ecan_ai_rerank_results", {"input": state["tool_input"]})

            tool_result = run_async_in_sync(run_tool_call())
            logger.debug("mcp api_ecan_ai_rerank_results returned....", tool_result)
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
                cloud_task_id = "no_id"
                logger.error("ErrorRerank:", state["error"])
                return state
            else:
                state["error"] = "Unexpected tool result format"
                cloud_task_id = "err_no_id0"
                logger.error("ErrorRerank:", state["error"])
                return state
    except Exception as e:
        logger.error(f"[search_digikey_chatter_skill] Exception in cloud_task_id detection: {e}")
        cloud_task_id = "err_no_id1"

    try:
        logger.debug("waiting for long haul api to return...", cloud_task_id)
        resume_payload = interrupt({
            "i_tag": cloud_task_id,
            "rank_results": {},
        })

        try:
            if isinstance(resume_payload, dict) and "_state_patch" in resume_payload:
                patch = resume_payload.get("_state_patch")
                if isinstance(patch, dict):
                    def _deep_merge(a: dict, b: dict) -> dict:
                        out = dict(a)
                        for k, v in b.items():
                            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                                out[k] = _deep_merge(out[k], v)
                            else:
                                out[k] = v
                        return out

                    # merge patch into state in place
                    try:
                        if isinstance(state, dict):
                            merged = _deep_merge(state, patch)
                            state.clear()
                            state.update(merged)
                    except Exception as e:
                        print(get_traceback(e, "ErrReRank0"))
                        pass
        except Exception as e:
            print(get_traceback(e, "ErrReRank1"))
            pass

        logger.debug("[search_digikey_chatter_skill] re_rank_search_results_node resume payload received:",
                     resume_payload)
        logger.debug("[search_digikey_chatter_skill] re_rank_search_results_node resumed, state:", state)

        cloud_results_raw = resume_payload["_state_patch"]["attributes"]["params"]["metadata"]["notification_to_agent"]
        if cloud_results_raw:
            logger.debug("[search_digikey_chatter_skill] received cloud ranking results (raw):", cloud_results_raw)
            try:
                # Prefer JSON for cloud result strings; fallback to ast.literal_eval is already present above
                if isinstance(cloud_results_raw, str):
                    try:
                        import json
                        cloud_results = json.loads(cloud_results_raw)
                    except Exception:
                        import ast
                        cloud_results = ast.literal_eval(cloud_results_raw)
                else:
                    cloud_results = cloud_results_raw

                print("==cloud_results:", cloud_results)
                state["attributes"]["rank_results"] = cloud_results

                # Then immediately reorder and persist:
                attrs = state.setdefault("attributes", {})

                # 1) Choose base rows
                base_rows = None
                if isinstance(attrs.get("sorted_search_results"), list) and attrs["sorted_search_results"]:
                    base_rows = attrs["sorted_search_results"]
                elif isinstance(attrs.get("search_results"), dict) and attrs["search_results"]:
                    try:
                        first_site_rows = next(iter(attrs["search_results"].values()))
                        base_rows = first_site_rows if isinstance(first_site_rows, list) else []
                    except Exception:
                        base_rows = []
                if not base_rows:
                    try:
                        base_rows = get_default_rerank_req().get("rows", []) or []
                    except Exception:
                        base_rows = []

                # 2) Reorder by ranked row_index
                ranked_list = (attrs.get("rank_results") or {}).get("ranked_results", []) or []
                ordered_rows = []
                for entry in ranked_list:
                    idx = entry.get("row_index")
                    if isinstance(idx, int) and 0 <= idx < len(base_rows):
                        ordered_rows.append(base_rows[idx])

                # 3) Persist for downstream consumers
                attrs["re_ranked_rows"] = ordered_rows
                attrs["sorted_search_results"] = ordered_rows
                logger.debug("[search_digikey_chatter_skill] re-ordered rows count:", len(ordered_rows))


                logger.debug("[search_digikey_chatter_skill] parsed cloud ranking results:", cloud_results)
                state["attributes"]["rank_results"] = cloud_results
            except (ValueError, SyntaxError) as e:
                logger.error(f"[search_digikey_chatter_skill] Failed to parse cloud results: {e}")
                state["attributes"]["rank_results"] = {}

        print("morphing notification")
        if state["attributes"].get("rank_results", []):
            notification = convert_rank_results_to_search_results(state)
            state["result"] = {
                "llm_result": "Here are the ranked search results based on your Figure of Merit.",
            }
            logger.debug("about to send results to human:", notification)
            send_data_back2human("send_chat", "notification", notification, state)
    except GraphInterrupt:
        print("GraphInterrupt")
        raise
    except Exception as e:
        state['error'] = get_traceback(e, "ErrorQueryComponentSpecsNode")
        logger.error(state['error'])
    return state
