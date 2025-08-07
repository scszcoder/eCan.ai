from agent.ec_skill import *
from agent.ec_agents.ec_marketing_agent import *
from agent.ec_agents.ec_sales_agent import *
from agent.ec_agents.ec_helper_agent import *
from agent.ec_agents.ec_rpa_supervisor_agent import *
from agent.ec_agents.ec_rpa_operator_agent import *
from agent.ec_agents.my_twin_agent import *
from agent.ec_agents.ec_procurement_agent import *
from agent.ec_agents.ec_marketing_agent import *
from agent.ec_agents.agent_utils import load_agents_from_cloud, load_agent_tools_from_cloud
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
