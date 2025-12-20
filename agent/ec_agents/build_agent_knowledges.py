import traceback
from agent.ec_agents.agent_utils import load_knowledges_from_cloud
from utils.logger_helper import logger_helper as logger

def build_agent_knowledges(main_win):
    try:
        # first try to obtain all agents from the cloud, if that fails or there are no agents
        # then build the agents locally
        all_agent_knowledges = load_knowledges_from_cloud(main_win)
        logger.info("agent knowledges from cloud:", all_agent_knowledges)
        if not all_agent_knowledges:
            # for now just build a few agents.
            all_agent_knowledges = []

        return all_agent_knowledges

    except Exception as e:
        logger.error(f"Error in get agent knowledges: {e} {traceback.format_exc()}")
        return []
