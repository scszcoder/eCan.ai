from agent.ec_skill import *
from utils.logger_helper import get_agent_by_id, get_traceback

def post_llm_hook(state: NodeState) -> NodeState:
    return state



# the llm node main routine has ask the llm for more analysis
def post_more_analysis_app(state: NodeState):
    try:
        # Check if all values in a target dict are acceptable per new rule:
        # acceptable if value is "NA" OR non-empty string OR non-empty dict OR non-empty list
        # If state["result"]["fields"] exists and is a dict, compute the check and store it back in state
        target_dict = state.get("result", {}).get("fields")
        all_fields_accepted = False
        if isinstance(target_dict, dict):
            def is_accepted(v):
                if v == "NA":
                    return True
                if isinstance(v, str):
                    return v.strip() != ""
                if isinstance(v, dict):
                    return len(v) > 0
                if isinstance(v, list):
                    return len(v) > 0
                return False

            all_fields_accepted = all(is_accepted(v) for v in target_dict.values())

        state["condition"] = all_fields_accepted
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserWaitForElement")
        logger.debug(err_trace)


# grab LLM generated prompt and send it to human twin agent.
def post_casually_respond_and_pend_for_next_human_msg(state: NodeState) -> NodeState:
    logger.debug("post_casually_respond_and_pend_for_next_human_msg: do none")

# grab LLM generated prompt and send it to human twin agent.
def post_respond_and_pend_for_next_human_msg0(state: NodeState) -> NodeState:
    logger.debug("post_respond_and_pend_for_next_human_msg0: do none")


def post_respond_and_pend_for_next_human_msg1(state: NodeState) -> NodeState:
    logger.debug("post_respond_and_pend_for_next_human_msg2: do none")


def post_respond_and_pend_for_next_human_msg2(state: NodeState) -> NodeState:
    logger.debug("post_respond_and_pend_for_next_human_msg2: do none")