from utils.logger_helper import logger_helper as logger
from agent.ec_skill import  *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from utils.logger_helper import get_agent_by_id, get_traceback
from agent.ec_skills.search_parts.post_llm_hooks import *


# just get the right prompt for this node
def standard_pre_llm_hook(askid, full_node_name, agent, state):
    try:
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [full_node_name])
        state["prompts"] = nodes_prompts[0]
        logger.debug(f"standard_pre_llm_hook: {full_node_name} prompts: {nodes_prompts}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.debug(err_trace)



def standard_post_llm_func(state, response):
    try:
        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        print("Raw content:", raw_content)  # Debug log

        # Clean up the response
        if is_json_parsable(raw_content):
            result = json.loads(raw_content)
        else:
            content = raw_content.strip('`').strip()
            if content.startswith('json'):
                content = content[4:].strip()
            # Parse the JSON
            # Convert to proper JSON string if it's a Python dict string
            if content.startswith('{') and content.endswith('}'):
                # Replace single quotes with double quotes for JSON
                content = content.replace("'", '"')
                # Convert Python's True/False to JSON's true/false
                content = content.replace("True", "true").replace("False", "false")
                if is_json_parsable(content):
                    # Return the full state with the analysis
                    result = json.loads(content)
                else:
                    result = raw_content
            else:
                result = raw_content

        return {"llm_result": result}

    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMFunc")
        logger.debug(err_trace)
        return {"llm_result": err_trace}

def standard_post_llm_hook(askid, node_name, agent, state, response):
    logger.debug("standard_post_llm_hook: do none")


PRE_LLM_HOOKS_TABLE = {
    "public:chatter for my digital twin:chat": standard_pre_llm_hook,
    "public:ecbot rpa helper:chat": standard_pre_llm_hook,
    "public:chatter for ecbot rpa helper:chat": standard_pre_llm_hook,
    "public:ecbot rpa operator run RPA:chat": standard_pre_llm_hook,
    "public:chatter for ecbot rpa operator run RPA:chat": standard_pre_llm_hook,
    "public:ecbot rpa supervisor task scheduling:chat": standard_pre_llm_hook,
    "public:chatter for ecbot rpa supervisor:chat": standard_pre_llm_hook,
    "public:meca search 1688 web site:chat": standard_pre_llm_hook,
    "public:chatter for meca search 1688 web site:chat": standard_pre_llm_hook,
    "public:meca search digi-key web site:chat": standard_pre_llm_hook,
    "public:chatter for ecan.ai search parts and components web site:chat": standard_pre_llm_hook,
    "public:ecan.ai search parts and components web site:chat": standard_pre_llm_hook,
    "public:chatter for ecan.ai self test:chat": standard_pre_llm_hook,
    "public:ecan.ai self test:chat": standard_pre_llm_hook
}

POST_LLM_HOOKS_TABLE = {
    "public:chatter for my digital twin:chat": standard_post_llm_hook,
    "public:ecbot rpa helper:chat": standard_post_llm_hook,
    "public:chatter for ecbot rpa helper:chat": standard_post_llm_hook,
    "public:ecbot rpa operator run RPA:chat": standard_post_llm_hook,
    "public:chatter for ecbot rpa operator run RPA:chat": standard_post_llm_hook,
    "public:ecbot rpa supervisor task scheduling:chat": standard_post_llm_hook,
    "public:chatter for ecbot rpa supervisor:chat": standard_post_llm_hook,
    "public:ecan.ai search 1688 web site:chat": standard_post_llm_hook,
    "public:chatter for ecan.ai search 1688 web site:chat": standard_post_llm_hook,
    "public:ecan.ai search digi-key web site:chat": standard_post_llm_hook,
    "public:chatter for ecan.ai search parts and components web site:more_analysis_app": post_more_analysis_app,
    "public:chatter for ecan.ai search parts and components web site:casually_respond_and_pend_for_next_human_msg": post_casually_respond_and_pend_for_next_human_msg,
    "public:chatter for ecan.ai search parts and components web site:respond_and_pend_for_next_human_msg0": post_respond_and_pend_for_next_human_msg0,
    "public:chatter for ecan.ai search parts and components web site:respond_and_pend_for_next_human_msg1": post_respond_and_pend_for_next_human_msg1,
    "public:chatter for ecan.ai search parts and components web site:respond_and_pend_for_next_human_msg2": post_respond_and_pend_for_next_human_msg2,

    "public:ecan.ai search parts and components web site:chat": standard_post_llm_hook,
    "public:chatter for ecan.ai self test:chat": standard_post_llm_hook,
    "public:ecan.ai self test:chat": standard_post_llm_hook
}

# pre llm is mostly about preparing the prompt
def run_pre_llm_hook(node_name, agent, state):
    mainwin = agent.mainwin
    skill_name = node_name.split(":")[1]
    this_skill = next((sk for sk in mainwin.agent_skills if sk.name == skill_name), None)
    askid = this_skill.askid
    print("pre llm hook node name:", node_name, askid)
    # Try exact match first
    if node_name in PRE_LLM_HOOKS_TABLE:
        return PRE_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state)
    # Fallback to case-insensitive lookup
    lower_map = {k.lower(): v for k, v in PRE_LLM_HOOKS_TABLE.items()}
    key_lower = node_name.lower() if isinstance(node_name, str) else node_name
    if key_lower in lower_map:
        return lower_map[key_lower](askid, node_name, agent, state)
    # Not found: raise informative error listing available keys

    # just run standard pre llm hook
    standard_pre_llm_hook(askid, node_name, agent, state)
    # available = ", ".join(sorted(PRE_LLM_HOOKS_TABLE.keys()))
    # raise KeyError(f"pre llm hook not found for '{node_name}'. Available: {available}")

# post llm is mostly about parsing the response and set up conditional variable for conditional edges (if there is one)
def run_post_llm_hook(askid, node_name, agent, state, response):
    mainwin = agent.mainwin
    skill_name = node_name.split(":")[1]
    this_skill = next((sk for sk in mainwin.agent_skills if sk.name == skill_name), None)
    askid = this_skill.askid
    # first run standard stuff, then then the individual func for a specific skill node.
    state["result"] = standard_post_llm_func(askid, node_name, state, response)

    print("post llm hook  name:", node_name, askid)
    # Try exact match first
    if node_name in POST_LLM_HOOKS_TABLE:
        return POST_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state, response)
    # Fallback to case-insensitive lookup
    lower_map = {k.lower(): v for k, v in POST_LLM_HOOKS_TABLE.items()}
    key_lower = node_name.lower() if isinstance(node_name, str) else node_name
    if key_lower in lower_map:
        return POST_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state, response)

    return standard_post_llm_hook(askid, node_name, agent, state, response)

    # Not found: raise informative error listing available keys
    # available = ", ".join(sorted(POST_LLM_HOOKS_TABLE.keys()))
    # raise KeyError(f"post llm hook not found for '{node_name}'. Available: {available}")