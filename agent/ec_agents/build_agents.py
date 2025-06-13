from agent.ec_skill import *
from agent.ec_agents.ec_marketing_agent import *
from agent.ec_agents.ec_sales_agent import *
from agent.ec_agents.ec_helper_agent import *
from agent.ec_agents.ec_rpa_supervisor_agent import *
from agent.ec_agents.ec_rpa_operator_agent import *
from agent.ec_agents.my_twin_agent import *
from agent.ec_agents.ec_procurement_agent import *
from agent.ec_agents.ec_marketing_agent import *


def build_agents(main_win):
    agents = []
    # for now just build a few agents.
    agents.append(set_up_my_twin_agent(main_win))
    if "Platoon" in main_win.machine_role:
        agents.append(set_up_ec_helper_agent(main_win))
        agents.append(set_up_ec_rpa_operator_agent(main_win))
    else:
        agents.append(set_up_ec_helper_agent(main_win))
        # self.agents.append(set_up_ec_rpa_supervisor_agent(self))
        if "ONLY" not in main_win.machine_role:
            # self.agents.append(set_up_ec_rpa_operator_agent(self))
            agents.append(set_up_ec_procurement_agent(main_win))

    return agents