from agent.ec_skill import *
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.ec_skills.llm_utils.llm_utils import *


def post_llm_hook(state: NodeState) -> NodeState:
    return state


def post_chat_hook(askid, node_name, agent, state, response):
    try:
        llm_output = state["result"]["llm_result"]
        response = llm_output["next_prompt"]

        state["attributes"]["work_related"] = llm_output["work_related"]
        state["result"]["llm_result"] = response
        logger.debug("post_chat_hook Raw llm response content:", state)  # Debug log

        # Clean up the response
        send_result = send_response_back(state)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorPostChatHook")
        logger.debug(err_trace)

# the llm node main routine has ask the llm for more analysis
# save any partial preliminary info. adjust state to fit send_back function
# and then send back prompt. set condition if the preliminary info is complete
# need a space in state to store the prelimiary info json data.
EMPTY_PRELIMINARY_INFO_TEMPLATE = [
    {
      "part name": "",
      "oems": [],
      "model_part_numbers": [],
      "applications_usage": [],
      "usage_grade": ""
    }
  ]


def is_filled(v):
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, dict):
        return len(v) > 0
    if isinstance(v, list):
        return len(v) > 0
    return False

def post_more_analysis_app_hook(askid, node_name, agent, state, response):
    try:
        # Check if all values in a target dict are acceptable per new rule:
        # acceptable if value is "NA" OR non-empty string OR non-empty dict OR non-empty list
        # If state["result"]["fields"] exists and is a dict, compute the check and store it back in state
        llm_output = state["result"]["llm_result"]
        print("post_more_analysis_app_hook llm_output:", llm_output)
        response = llm_output["next_prompt"]
        preliminary_info = llm_output.get("preliminary_info", EMPTY_PRELIMINARY_INFO_TEMPLATE)
        state["attributes"]["current_preliminary_info"] = preliminary_info
        extra_info = llm_output.get("extra_info", {})
        state["attributes"]["extra_info"] = extra_info
        print("post_more_analysis_app_hook llm_output:", preliminary_info)
        all_fields_accepted = False
        if isinstance(preliminary_info, dict):
            all_fields_accepted = all(is_filled(v) for v in preliminary_info.values())
        elif isinstance(preliminary_info, list):
            for item in preliminary_info:
                all_fields_accepted = all(is_filled(v) for v in item.values())
                if not all_fields_accepted:
                    break

        print(f"post_more_analysis_app_hook set state condition to {all_fields_accepted}")  # Debug log

        state["condition"] = all_fields_accepted

        # now send the prompt message back to human
        state["result"]["llm_result"] = response
        send_result = send_response_back(state)
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserWaitForElement")
        logger.debug(err_trace)


# grab LLM generated prompt and send it to human twin agent.
def post_pend_for_next_human_msg_hook(askid, node_name, agent, state, response):
    try:
        # Extract content from AIMessage if needed
        llm_output = state["result"]["llm_result"]
        response = state["result"]["llm_result"]["next_prompt"]

        state["job_related"] = state["result"]["job_related"]
        state["result"]["llm_result"] = response
        print("standard_post_llm_func Raw llm response content:", state)  # Debug log

        # Clean up the response
        send_result = send_response_back(state)
        logger.debug(f"standard_post_llm_hook: {send_result}")
        return send_result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMFunc")
        logger.debug(err_trace)
        return {"llm_result": err_trace}

# grab LLM generated prompt and send it to human twin agent.
def post_pend_for_next_human_msg0_hook(askid, node_name, agent, state, response):
    logger.debug("post_respond_and_pend_for_next_human_msg0: do none")


def post_pend_for_next_human_msg1_hook(askid, node_name, agent, state, response):
    logger.debug("post_respond_and_pend_for_next_human_msg2: do none")


def post_pend_for_next_human_msg2_hook(askid, node_name, agent, state, response):
    logger.debug("post_respond_and_pend_for_next_human_msg2: do none")