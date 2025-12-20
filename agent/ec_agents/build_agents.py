import traceback
from agent.ec_agents.agent_utils import load_agents_from_cloud
from agent.ec_agents.ec_helper_agent import set_up_ec_helper_agent
from agent.ec_agents.ec_procurement_agent import set_up_ec_procurement_agent
from agent.ec_agents.ec_rpa_operator_agent import set_up_ec_rpa_operator_agent
from agent.ec_agents.ec_tester_agent import set_up_ec_tester_agent
from agent.ec_agents.my_twin_agent import set_up_my_twin_agent
from utils.logger_helper import logger_helper as logger

def build_agents(main_win):
    try:
        all_agents = []

        # first try to obtain all agents from the cloud, if that fails or there are no agents
        # then build the agents locally
        all_agents = load_agents_from_cloud(main_win)
        logger.info("agents from cloud:", all_agents)
        if not all_agents:
            # for now just build a few agents.
            all_agents.append(set_up_my_twin_agent(main_win))
            if "Platoon" in main_win.machine_role:
                all_agents.append(set_up_ec_helper_agent(main_win))
                all_agents.append(set_up_ec_rpa_operator_agent(main_win))
                all_agents.append(set_up_ec_tester_agent(main_win))
            else:
                logger.info("building non-platoon agents")
                all_agents.append(set_up_ec_helper_agent(main_win))
                # self.agents.append(set_up_ec_rpa_supervisor_agent(self))
                if "ONLY" not in main_win.machine_role:
                    logger.info("building commander agents")
                    # self.agents.append(set_up_ec_rpa_operator_agent(self))
                    all_agents.append(set_up_ec_procurement_agent(main_win))
                    all_agents.append(set_up_ec_tester_agent(main_win))
        
        # 过滤掉None对象
        all_agents = [agent for agent in all_agents if agent is not None]
        logger.info(f"Total agents after filtering None: {len(all_agents)}")

        main_win.agents = all_agents

    except Exception as e:
        logger.error(f"Error in get agents handler: {e} {traceback.format_exc()}")
        main_win.agents = []
