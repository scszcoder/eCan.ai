
import json
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

from agent.ec_skill import NodeState, Runtime
from langgraph.store.base import BaseStore
from agent.agent_service import get_agent_by_id
from agent.ec_skills.llm_utils.llm_utils import get_standard_prompt
from agent.ec_skills.llm_hooks.llm_hooks import run_pre_llm_hook, run_post_llm_hook
from langgraph.types import interrupt

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
PUBLIC_OWNER = "public"
def chat_or_work(state: NodeState, *, runtime: Runtime) -> str:
    logger.debug("chat_or_work input:", state)
    if isinstance(state.get('attributes'), dict) and state['attributes'].get("work_related", False):
        return "do_work"
    return "pend_for_next_human_msg"


def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    try:
        logger.debug("extern:: in llm_node_with_raw_files....", state)
        user_input = state.get("input", "")
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        logger.debug("run time:", json.dumps(runtime.context, indent=4))
        current_node_name = runtime.context["this_node"].get("name")
        skill_name = runtime.context["this_node"].get("skill_name")
        owner = runtime.context["this_node"].get("owner")

        # logger.debug("current node:", current_node)
        nodes = [{"askid": "skid0", "name": current_node_name}]
        full_node_name = f"{owner}:{skill_name}:{current_node_name}"
        run_pre_llm_hook(full_node_name, agent, state)

        logger.debug("networked prompts:", state["prompts"])
        node_prompt = state["prompts"]

        # mm_content = prep_multi_modal_content(state, runtime)
        # langchain_prompt = ChatPromptTemplate.from_messages(node_prompt)
        # formatted_prompt = langchain_prompt.format_messages(component_info=state["input"], categories=state["attributes"]["categories"])

        if state["history"]:
            formatted_prompt = state["history"][-1]
        else:
            formatted_prompt = get_standard_prompt(state)            #STARDARD_PROMPT

        # Ensure formatted_prompt is a list (llm.invoke expects a list of messages)
        # If it's a single message object, wrap it in a list
        if not isinstance(formatted_prompt, list):
            formatted_prompt = [formatted_prompt]

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and mainwin.llm else None
        if not llm:
            raise ValueError("LLM not available in mainwin")


        logger.debug("chat node: llm prompt ready:", formatted_prompt)
        response = llm.invoke(formatted_prompt)
        logger.debug("chat node: LLM response:", response)
        # Parse the response
        run_post_llm_hook(full_node_name, agent, state, response)
        logger.debug("llm_node_with_raw_file exiting.....", state)
        return state
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.error(err_trace)
        state["result"] = {"error": err_trace}
        return state


def pend_for_human_input_node(state: NodeState, *, runtime: Runtime, store: BaseStore):
    agent_id = state["messages"][0]
    _ = get_agent_by_id(agent_id)
    logger.debug("[pend_for_human_input_node] runtime:", runtime)
    current_node_name = runtime.context["this_node"].get("name")

    logger.debug(f"pend_for_human_input_node>: {current_node_name}", state)
    if state.get("metadata"):
        qa_form = state.get("metadata").get("qa_form", {})
        notification = state.get("metadata").get("notification", {})
    else:
        qa_form = {}
        notification = {}

    logger.debug(f"qa form: {qa_form}, notification, {notification}, result:, {state['result']}")
    resume_payload = interrupt({
        "i_tag": current_node_name,
        "prompt_to_human": state["result"].get("llm_result", {}).get("casual_chat_response", ""),
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

    logger.debug("pend_for_human_input_node resume payload received:", resume_payload)
    logger.debug("pend_for_human_input_node resumed, state:", state)

    return state
