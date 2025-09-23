from agent.ec_skills.search_1688.prep_search_1688_skill import *
from agent.ec_skills.search_digi_key.prep_search_digi_key_skill import *
from agent.ec_skills.search_1688.prep_search_1688_chatter_skill import *
# from agent.ec_skills.search_digi_key.prep_search_digi_key_chatter_skill import *
from agent.ec_skills.search_parts.prep_search_parts_skill import *
from agent.ec_skills.search_parts.prep_search_parts_chatter_skill import *
from agent.ec_skills.self_test.prep_self_test_skill import *
from agent.ec_skills.self_test.prep_self_test_chatter_skill import *
from agent.ec_skills.ecbot_rpa.prep_ecbot_rpa_skill import *
from agent.ec_skills.ecbot_rpa.prep_ecbot_rpa_chatter_skill import *
from agent.ec_skills.my_twin.prep_my_twin_chatter_skill import *

SKILL_PREP_TABLE = {
    "chatter for my digital twin": prep_my_twin_chatter_skill,
    "ecbot rpa helper": prep_ecbot_rpa_helper_skill,
    "chatter for ecbot rpa helper": prep_ecbot_rpa_helper_chatter_skill,
    "ecbot rpa operator run RPA": prep_ecbot_rpa_operator_skill,
    "chatter for ecbot rpa operator run RPA": prep_ecbot_rpa_operator_chatter_skill,
    "ecbot rpa supervisor task scheduling": prep_ecbot_rpa_superviser_skill,
    "chatter for ecbot rpa supervisor": prep_ecbot_rpa_superviser_chatter_skill,
    "meca search 1688 web site": prep_search_1688_skill,
    "chatter for meca search 1688 web site": prep_search_1688_chatter_skill,
    "meca search digi-key web site": prep_search_digi_key_skill,
    "chatter for ecan.ai search parts and components web site": prep_search_parts_chatter_skill,
    "ecan.ai search parts and components web site": prep_search_parts_skill,
    "chatter for ecan.ai self test": prep_self_test_chatter_skill,
    "ecan.ai self test": prep_self_test_skill
}

def prep_skills_run(skillName, agent, task_id, msg=None, current_state=None):
    print("skill name:", skillName)
    # Try exact match first
    if skillName in SKILL_PREP_TABLE:
        return SKILL_PREP_TABLE[skillName](agent, task_id, msg, current_state)
    # Fallback to case-insensitive lookup
    lower_map = {k.lower(): v for k, v in SKILL_PREP_TABLE.items()}
    key_lower = skillName.lower() if isinstance(skillName, str) else skillName
    if key_lower in lower_map:
        return lower_map[key_lower](agent, msg, current_state)
    # Not found: raise informative error listing available keys
    available = ", ".join(sorted(SKILL_PREP_TABLE.keys()))
    raise KeyError(f"Skill preper not found for '{skillName}'. Available: {available}")