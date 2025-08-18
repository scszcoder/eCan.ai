from utils.logger_helper import logger_helper as logger
from agent.ec_skill import  *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from utils.logger_helper import get_agent_by_id, get_traceback
from agent.ec_skills.search_parts.pre_llm_hooks import *
from agent.ec_skills.search_parts.post_llm_hooks import *
# from agent.ec_skills.llm_utils.llm_utils import *

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
        langchain_prompt = ChatPromptTemplate.from_messages(state["prompts"])
        formatted_prompt = langchain_prompt.format_messages(boss_name = "Guest User", input=state["input"])
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

def send_response_back(state: NodeState) -> NodeState:
    try:
        agent_id = state["messages"][0]
        # _ensure_context(runtime.context)
        self_agent = get_agent_by_id(agent_id)
        mainwin = self_agent.mainwin
        twin_agent = next((ag for ag in mainwin.agents if "twin" in ag.card.name.lower()), None)

        print("standard_post_llm_hook send_response_back:", state)
        chat_id = state["messages"][1]
        msg_id = str(uuid.uuid4()),
        # send self a message to trigger the real component search work-flow
        agent_response_message = {
            "id": str(uuid.uuid4()),
            "chat": {
                "input": state["result"]["llm_result"],
                "attachments": [],
                "messages": [self_agent.card.id, chat_id, msg_id, "", state["result"]["llm_result"]],
            },
            "params": {
                "content": state["result"]["llm_result"],
                "attachments": state["attachments"],
                "metadata": {
                    "type": "text", # "text", "code", "form", "notification", "card
                    "card": {},
                    "code": {},
                    "form": {},
                    "notification": {},
                },
                "role": "",
                "senderId": f"{agent_id}",
                "createAt": int(time.time() * 1000),
                "senderName": f"{self_agent.card.name}",
                "status": "success",
                "ext": "",
                "human": False
            }
        }
        print("sending response msg back to twin:", agent_response_message)
        send_result = self_agent.a2a_send_chat_message(twin_agent, agent_response_message)
        # state.result = result
        return send_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendResponseBack")
        logger.debug(err_trace)
        return err_trace



def standard_post_llm_hook(askid, node_name, agent, state, response):
    send_result = send_response_back(state)
    logger.debug(f"standard_post_llm_hook: {send_result}")


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
    print("node_name:", node_name, agent.card.name)
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
def run_post_llm_hook(node_name, agent, state, response):
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