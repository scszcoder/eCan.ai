from agent.ec_skill import  *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from utils.logger_helper import get_agent_by_id, get_traceback

def pre_more_analysis_app(askid, full_node_name, agent, state):
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
        state["formatted_prompts"].append(formatted_prompt)

        logger.debug(f"standard_pre_llm_hook: {full_node_name} prompts: {nodes_prompts}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.debug(err_trace)