from utils.logger_helper import logger_helper as logger

from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts

def standard_pre_llm_hook(mainwin, skill_name, node_name, agent, state):
    nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [node_name])
    state["prompts"] = nodes_prompts
    logger.debug(f"standard_pre_llm_hook: {node_name} prompts: {nodes_prompts}")



PRE_LLM_HOOKS_TABLE = {
    "chatter for my digital twin": standard_pre_llm_hook,
    "ecbot rpa helper": standard_pre_llm_hook,
    "chatter for ecbot rpa helper": standard_pre_llm_hook,
    "ecbot rpa operator run RPA": standard_pre_llm_hook,
    "chatter for ecbot rpa operator run RPA": standard_pre_llm_hook,
    "ecbot rpa supervisor task scheduling": standard_pre_llm_hook,
    "chatter for ecbot rpa supervisor": standard_pre_llm_hook,
    "meca search 1688 web site": standard_pre_llm_hook,
    "chatter for meca search 1688 web site": standard_pre_llm_hook,
    "meca search digi-key web site": standard_pre_llm_hook,
    "chatter for ecan.ai search parts and components web site": standard_pre_llm_hook,
    "ecan.ai search parts and components web site": standard_pre_llm_hook,
    "chatter for ecan.ai self test": standard_pre_llm_hook,
    "ecan.ai self test": standard_pre_llm_hook
}

POST_LLM_HOOKS_TABLE = {
    "chatter for my digital twin": post_llm_hook,
    "ecbot rpa helper": init_ecbot_rpa_helper_skill,
    "chatter for ecbot rpa helper": init_ecbot_rpa_helper_chatter_skill,
    "ecbot rpa operator run RPA": init_ecbot_rpa_operator_skill,
    "chatter for ecbot rpa operator run RPA": init_ecbot_rpa_operator_chatter_skill,
    "ecbot rpa supervisor task scheduling": init_ecbot_rpa_superviser_skill,
    "chatter for ecbot rpa supervisor": init_ecbot_rpa_superviser_chatter_skill,
    "meca search 1688 web site": init_search_1688_skill,
    "chatter for meca search 1688 web site": init_search_1688_chatter_skill,
    "meca search digi-key web site": init_search_digi_key_skill,
    "chatter for ecan.ai search parts and components web site": init_search_parts_chatter_skill,
    "ecan.ai search parts and components web site": init_search_parts_skill,
    "chatter for ecan.ai self test": init_self_test_chatter_skill,
    "ecan.ai self test": init_self_test_skill
}

# pre llm is mostly about preparing the prompt
def run_pre_llm_hook(skill_name, node_name, agent, state):
    print("pre llm hook node name:", node_name)
    # Try exact match first
    if node_name in PRE_LLM_HOOKS_TABLE:
        return PRE_LLM_HOOKS_TABLE[node_name](agent, state)
    # Fallback to case-insensitive lookup
    lower_map = {k.lower(): v for k, v in PRE_LLM_HOOKS_TABLE.items()}
    key_lower = node_name.lower() if isinstance(node_name, str) else node_name
    if key_lower in lower_map:
        return lower_map[key_lower](agent, state)
    # Not found: raise informative error listing available keys

    # just run standard pre llm hook
    standard_pre_llm_hook(skill_name, node_name, agent, state)
    # available = ", ".join(sorted(PRE_LLM_HOOKS_TABLE.keys()))
    # raise KeyError(f"pre llm hook not found for '{node_name}'. Available: {available}")

# post llm is mostly about parsing the response and set up conditional variable for conditional edges (if there is one)
def run_post_llm_hook(node_name, agent, state):
    print("post llm hook  name:", node_name)
    # Try exact match first
    if node_name in POST_LLM_HOOKS_TABLE:
        return POST_LLM_HOOKS_TABLE[node_name](agent, state)
    # Fallback to case-insensitive lookup
    lower_map = {k.lower(): v for k, v in POST_LLM_HOOKS_TABLE.items()}
    key_lower = node_name.lower() if isinstance(node_name, str) else node_name
    if key_lower in lower_map:
        return lower_map[key_lower](agent, state)
    # Not found: raise informative error listing available keys
    available = ", ".join(sorted(POST_LLM_HOOKS_TABLE.keys()))
    raise KeyError(f"post llm hook not found for '{node_name}'. Available: {available}")