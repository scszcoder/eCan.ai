from agent.ec_skill import  *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.ec_skills.llm_utils.llm_utils import *

# try to set up prompts right, with the right parameters
def pre_more_analysis_app_hook(askid, full_node_name, agent, state, prompt_src="cloud", prompt_data=None):
    try:
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        node_info = {"askid": askid, "name": full_node_name}
        nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [node_info])
        # mm_content = prep_multi_modal_content(state, runtime)

        state["prompts"] = nodes_prompts[0]
        current_preliminary_info = state["attributes"].get("current_preliminary_info", {})
        langchain_prompt = ChatPromptTemplate.from_messages(state["prompts"])
        formatted_prompt = langchain_prompt.format_messages(boss_name="Guest User", human_input=state["input"], current_preliminary_info=current_preliminary_info)
        state["history"].extend(formatted_prompt)

        logger.debug(f"pre_more_analysis_app: {full_node_name} prompts: {formatted_prompt}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPreMoreAnalysisApp")
        logger.debug(err_trace)


def pre_examine_filled_specs(askid, full_node_name, agent, state, prompt_src="cloud", prompt_data=None):
    try:
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        node_info = {"askid": askid, "name": full_node_name}
        nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [node_info])
        # mm_content = prep_multi_modal_content(state, runtime)

        state["prompts"] = nodes_prompts[0]
        langchain_prompt = ChatPromptTemplate.from_messages(state["prompts"])
        formatted_prompt = langchain_prompt.format_messages(boss_name="Guest User", human_input=state["input"])
        state["history"].extend(formatted_prompt)

        logger.debug(f"pre_examine_filled_specs: {full_node_name} prompts: {nodes_prompts}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPreExamineFilledSpecs")
        logger.debug(err_trace)



def pre_confirm_FOM(askid, full_node_name, agent, state, prompt_src="cloud", prompt_data=None):
    try:
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        node_info = {"askid": askid, "name": full_node_name}
        nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [node_info])
        # mm_content = prep_multi_modal_content(state, runtime)

        state["prompts"] = nodes_prompts[0]
        langchain_prompt = ChatPromptTemplate.from_messages(state["prompts"])
        formatted_prompt = langchain_prompt.format_messages(boss_name="Guest User", input=state["input"])
        state["history"].extend(formatted_prompt)

        logger.debug(f"pre_confirm_FOM: {full_node_name} prompts: {nodes_prompts}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPreConfirmFOM")
        logger.debug(err_trace)


def pre_pend_for_next_human_msg_hook(askid, node_name, agent, state, response):
    try:
        # Extract content from AIMessage if needed
        llm_output = state["result"]["llm_result"]
        response = state["result"]["llm_result"]["next_prompt"]

        state["job_related"] = state["result"]["job_related"]
        state["result"]["llm_result"] = response
        logger.debug("standard_post_llm_func Raw llm response content:", state)  # Debug log

        # Clean up the response
        send_result = send_response_back(state)
        logger.debug(f"standard_post_llm_hook: {send_result}")
        return send_result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMFunc")
        logger.debug(err_trace)
        return {"llm_result": err_trace}