from utils.logger_helper import logger_helper as logger
from agent.ec_skill import  *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.ec_skills.search_parts.pre_llm_hooks import *
from agent.ec_skills.search_parts.post_llm_hooks import *
from agent.ec_skills.llm_utils.llm_utils import send_response_back, _deep_merge




# just get the right prompt for this node
def standard_pre_llm_hook(askid, full_node_name, agent, state):
    try:
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        node_info = {"askid": askid, "name": full_node_name}
        nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [node_info])
        # mm_content = prep_multi_modal_content(state, runtime)

        state["prompts"] = nodes_prompts[0]
        print("state prompts:", state["prompts"])
        langchain_prompt = ChatPromptTemplate.from_messages(state["prompts"])
        formatted_prompt = langchain_prompt.format_messages(boss_name = "Guest User", human_input=state["input"])
        print("state:", state)
        state["formatted_prompts"].append(formatted_prompt)

        logger.debug(f"standard_pre_llm_hook: {full_node_name} prompts: {nodes_prompts}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.debug(err_trace)



def standard_post_llm_func(askid, node_name, state, response):
    try:
        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        print("standard_post_llm_func Raw llm response content:", raw_content)  # Debug log

        # as a good convention LLM should always return structured data rather than pure string text
        # we should always ask LLM to return {"message": "your message here", "meta_data": dict}
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

        llm_result = {"llm_result": result}
        logger.debug(f"standard_post_llm_func: llm_result: {llm_result}")
        return llm_result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMFunc")
        logger.debug(err_trace)
        return {"llm_result": err_trace}



def standard_post_llm_hook(askid, node_name, agent, state, response):
    try:
        # we really shouldn't send the reponse back here, instead we should update state and other node takes care of what to do with the results.
        post_hook_result = None
        state["result"] = response
        state["metadata"] = _deep_merge(state["metadata"], response["llm_result"].get("meta_data", {}))
        state["messages"].append(f"llm:{response['llm_result'].get('casual_chat_response', '')}")
        logger.debug(f"standard_post_llm_hook: {post_hook_result}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMHook")
        logger.debug(err_trace)


PRE_LLM_HOOKS_TABLE = {
    "public:chatter for my digital twin:chat": standard_pre_llm_hook,
    "public:ecbot rpa helper:chat": standard_pre_llm_hook,
    "public:chatter for ecbot rpa helper:chat": standard_pre_llm_hook,
    "public:ecbot rpa operator run RPA:chat": standard_pre_llm_hook,
    "public:chatter for ecbot rpa operator run RPA:chat": standard_pre_llm_hook,
    "public:ecbot rpa supervisor task scheduling:chat": standard_pre_llm_hook,
    "public:chatter for ecbot rpa supervisor:chat": standard_pre_llm_hook,
    "public:eCan.ai search 1688 web site:chat": standard_pre_llm_hook,
    "public:chatter for meca search 1688 web site:chat": standard_pre_llm_hook,
    "public:search_digikey_chatter:chat": standard_pre_llm_hook,
    "public:chatter for ecan.ai search parts and components web site:chat": standard_pre_llm_hook,
    "public:chatter for ecan.ai search parts and components web site:more_analysis_app": pre_more_analysis_app_hook,

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
    "public:search_digikey_chatter:chat": standard_post_llm_hook,
    "public:chatter for ecan.ai search parts and components web site:chat": post_chat_hook,
    "public:chatter for ecan.ai search parts and components web site:more_analysis_app": post_more_analysis_app_hook,
    "public:chatter for ecan.ai search parts and components web site:pend_for_next_human_msg": post_pend_for_next_human_msg_hook,
    "public:chatter for ecan.ai search parts and components web site:pend_for_next_human_msg0": post_pend_for_next_human_msg0_hook,
    "public:chatter for ecan.ai search parts and components web site:pend_for_next_human_msg1": post_pend_for_next_human_msg1_hook,
    "public:chatter for ecan.ai search parts and components web site:pend_for_next_human_msg2": post_pend_for_next_human_msg2_hook,

    "public:ecan.ai search parts and components web site:chat": standard_post_llm_hook,
    "public:chatter for ecan.ai self test:chat": standard_post_llm_hook,
    "public:ecan.ai self test:chat": standard_post_llm_hook
}

# pre llm is mostly about preparing the prompt
def run_pre_llm_hook(node_name, agent, state):
    try:
        mainwin = agent.mainwin
        print("node_name:", node_name, agent.card.name)
        skill_name = node_name.split(":")[1]
        this_skill = next((sk for sk in mainwin.agent_skills if sk.name == skill_name), None)
        askid = this_skill.askid
        askid = "skid0"
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
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.debug(err_trace)
        return err_trace

# post llm is mostly about parsing the response and set up conditional variable for conditional edges (if there is one)
def run_post_llm_hook(node_name, agent, state, response):
    try:
        mainwin = agent.mainwin
        skill_name = node_name.split(":")[1]
        this_skill = next((sk for sk in mainwin.agent_skills if sk.name == skill_name), None)
        askid = this_skill.askid
        # first run standard stuff, then then the individual func for a specific skill node.
        parsed_response = standard_post_llm_func(askid, node_name, state, response)

        print("post llm hook  name:", node_name, askid, parsed_response)
        # Try exact match first
        if node_name in POST_LLM_HOOKS_TABLE:
            return POST_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state, parsed_response)
        # Fallback to case-insensitive lookup
        lower_map = {k.lower(): v for k, v in POST_LLM_HOOKS_TABLE.items()}
        key_lower = node_name.lower() if isinstance(node_name, str) else node_name
        if key_lower in lower_map:
            return POST_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state, response)

        return standard_post_llm_hook(askid, node_name, agent, state, response)

        # Not found: raise informative error listing available keys
        # available = ", ".join(sorted(POST_LLM_HOOKS_TABLE.keys()))
        # raise KeyError(f"post llm hook not found for '{node_name}'. Available: {available}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMHook")
        logger.debug(err_trace)
        return err_trace

def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    try:
        print("in llm_node_with_raw_files....")
        user_input = state.get("input", "")
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        print("run time:", runtime)
        current_node_name = runtime.context["this_node"].get("name")
        skill_name = runtime.context["this_node"].get("skill_name")
        owner = runtime.context["this_node"].get("owner")

        # print("current node:", current_node)
        nodes = [{"askid": "skid0", "name": current_node_name}]
        full_node_name = f"{owner}:{skill_name}:{current_node_name}"
        run_pre_llm_hook(full_node_name, agent, state)

        print("networked prompts:", state["prompts"])
        node_prompt = state["prompts"]

        # mm_content = prep_multi_modal_content(state, runtime)
        # langchain_prompt = ChatPromptTemplate.from_messages(node_prompt)
        # formatted_prompt = langchain_prompt.format_messages(component_info=state["input"], categories=state["attributes"]["categories"])

        if state["formatted_prompts"]:
            formatted_prompt = state["formatted_prompts"][-1]
        else:
            formatted_prompt = get_standard_prompt(state)            #STARDARD_PROMPT

        llm = ChatOpenAI(model="gpt-4.1-2025-04-14")


        print("chat node: llm prompt ready:", formatted_prompt)
        response = llm.invoke(formatted_prompt)
        print("chat node: LLM response:", response)
        # Parse the response
        run_post_llm_hook(full_node_name, agent, state, response)
        print("llm_node_with_raw_file finished.....", state)
        return state
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.debug(err_trace)
        state["result"] = {"error": err_trace}
        return state
