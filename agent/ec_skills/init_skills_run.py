from agent.ec_skills.search_1688.init_search_1688_skill import *
from agent.ec_skills.search_1688.init_search_1688_chatter_skill import *
from agent.ec_skills.ecbot_rpa.init_ecbot_rpa_skill import *
from agent.ec_skills.ecbot_rpa.init_ecbot_rpa_chatter_skill import *
from agent.ec_skills.my_twin.init_my_twin_chatter_skill import *
SKILL_INIT_TABLE = {
    "chatter for my digital twin": init_my_twin_chatter_skill,
    "ecbot rpa helper": init_ecbot_rpa_helper_skill,
    "chatter for ecbot rpa helper": init_ecbot_rpa_helper_chatter_skill,
    "ecbot rpa operator run RPA": init_ecbot_rpa_operator_skill,
    "chatter for ecbot rpa operator run RPA": init_ecbot_rpa_operator_chatter_skill,
    "ecbot rpa supervisor task scheduling": init_ecbot_rpa_superviser_skill,
    "chatter for ecbot rpa supervisor": init_ecbot_rpa_superviser_chatter_skill,
    "meca search 1688 web site": init_search_1688_skill,
    "chatter for meca search 1688 web site": init_search_1688_chatter_skill
}

def init_skills_run(skillName, agent):
    print("skill name:", skillName)
    return SKILL_INIT_TABLE[skillName](agent)