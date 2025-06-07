from agent.ec_skills.search_1688.init_search_1688_skill import *
from agent.ec_skills.ecbot_rpa.init_ecbot_rpa_skill import *

SKILL_INIT_TABLE = {
    "ecbot rpa helper": init_ecbot_rpa_helper_skill,
    "ecbot rpa operator run RPA": init_ecbot_rpa_operator_skill,
    "ecbot rpa supervisor task scheduling": init_ecbot_rpa_superviser_skill,
    "meca search 1688 web site": init_search_1688_skill
}

def init_skills_run(skillName, agent):
    return SKILL_INIT_TABLE[skillName](agent)