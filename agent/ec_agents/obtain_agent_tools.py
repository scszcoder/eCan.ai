import traceback
from agent.ec_agents.agent_utils import load_agent_tools_from_cloud
from utils.logger_helper import logger_helper as logger

def obtain_agent_tools(main_win):
    try:
        all_agent_tools = []

        # first try to obtain all agents from the cloud, if that fails or there are no agents
        # then build the agents locally
        all_agent_tools = load_agent_tools_from_cloud(main_win)
        logger.info("agents tools from cloud:", all_agent_tools)
        if not all_agent_tools:
            # for now just build a few agents.
            all_agent_tools =[]

        return all_agent_tools

    except Exception as e:
        logger.error(f"Error in get agent tools: {e} {traceback.format_exc()}")
        return []
