from utils.logger_helper import logger_helper as logger
from agent.ec_skill import  *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import api_ecan_ai_get_nodes_prompts
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from agent.ec_skills.search_parts.pre_llm_hooks import *
from agent.ec_skills.search_parts.post_llm_hooks import *
from agent.ec_skills.llm_utils.llm_utils import _deep_merge


# just get the right prompt for this node
def standard_pre_llm_hook(askid, full_node_name, agent, state, prompt_src, prompt_data):
    try:
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        node_info = {"askid": askid, "name": full_node_name}

        # obtain the right prompt for this node (fetch from cloud) but
        # if this node name is not in the cloud, we use the default prompt
        if prompt_src=="cloud":
            nodes_prompts = api_ecan_ai_get_nodes_prompts(mainwin, [node_info])
            state["prompts"] = nodes_prompts[0]
            logger.debug(f"cloud state prompts: {state['input']} {nodes_prompts}")
        # mm_content = prep_multi_modal_content(state, runtime)
        else:
            nodes_prompts = prompt_data
            state["prompts"] = nodes_prompts
            logger.debug(f"GUI state prompts: {state['input']} {nodes_prompts}")

        logger.debug(f"standard_pre_llm_hook current state: {state}")
        langchain_prompt = ChatPromptTemplate.from_messages(state["prompts"])

        # Collect variables required by the prompt template
        try:
            required_vars = set(getattr(langchain_prompt, "input_variables", []))
        except Exception:
            required_vars = set()

        logger.debug("prompt required_vars:",required_vars)
        # Build variable map from state["prompt_refs"], prior LLM results, and sensible defaults
        refs = state.get("prompt_refs", {}) or {}
        # Prefer singular 'result' per NodeState; also check 'results' if present for robustness
        llm_res = {}
        try:
            if isinstance(state.get("result"), dict):
                rr = state["result"].get("llm_result")
                if isinstance(rr, dict):
                    llm_res = rr
        except Exception:
            pass

        # Helper to extract latest human input reliably
        def _get_human_input(_state):
            try:
                # 1) direct input field if provided
                if isinstance(_state.get("input"), str) and _state.get("input"):
                    return _state.get("input")

                # 2) Extract from attributes.params (TaskSendParams or dict)
                attrs = _state.get("attributes", {}) or {}
                # Support both dict and object for attributes
                if isinstance(attrs, dict):
                    tparams = attrs.get("params")
                else:
                    tparams = getattr(attrs, "params", None)

                # 2a) If dict-like
                if isinstance(tparams, dict):
                    # message.parts[0].text
                    try:
                        parts = (((tparams.get("message") or {}).get("parts")) or [])
                        if parts and isinstance(parts, list):
                            part0 = parts[0]
                            text_val = part0.get("text") if isinstance(part0, dict) else None
                            if isinstance(text_val, str) and text_val:
                                return text_val
                    except Exception:
                        pass

                    # metadata.params.content
                    try:
                        meta2 = (tparams.get("metadata") or {})
                        inner_params = (meta2.get("params") or {})
                        content = inner_params.get("content")
                        if isinstance(content, str) and content:
                            return content
                    except Exception:
                        pass

                # 2b) If object-like (TaskSendParams)
                if tparams is not None and not isinstance(tparams, dict):
                    # message.parts[0].text
                    try:
                        message = getattr(tparams, "message", None)
                        parts = getattr(message, "parts", None)
                        if isinstance(parts, (list, tuple)) and parts:
                            p0 = parts[0]
                            text_val = getattr(p0, "text", None)
                            if isinstance(text_val, str) and text_val:
                                return text_val
                    except Exception:
                        pass

                    # metadata["params"]["content"]
                    try:
                        meta_obj = getattr(tparams, "metadata", None)
                        if isinstance(meta_obj, dict):
                            inner_params = meta_obj.get("params") or {}
                            content = inner_params.get("content")
                            if isinstance(content, str) and content:
                                return content
                    except Exception:
                        pass

                # 2c) attributes-level metadata.params.content if present
                try:
                    if isinstance(attrs, dict):
                        meta_top = attrs.get("metadata") or {}
                        inner_params_top = meta_top.get("params") or {}
                        content_top = inner_params_top.get("content")
                        if isinstance(content_top, str) and content_top:
                            return content_top
                    else:
                        meta_top = getattr(attrs, "metadata", None)
                        if isinstance(meta_top, dict):
                            inner_params_top = meta_top.get("params") or {}
                            content_top = inner_params_top.get("content")
                            if isinstance(content_top, str) and content_top:
                                return content_top
                except Exception:
                    pass
            except Exception:
                pass

            # 3) fallback: last non-LLM message in state["messages"]
            msgs = _state.get("messages") or []
            for m in reversed(msgs):
                if isinstance(m, str) and not m.startswith("llm:") and m:
                    return m
            return ""

        var_values = {}
        for var in required_vars:
            if var in refs:
                var_values[var] = refs[var]
            elif var in llm_res:
                var_values[var] = llm_res[var]
            elif var == "human_input":
                hi_val = _get_human_input(state)
                logger.debug(f"[standard_pre_llm_hook] extracted human_input: {hi_val!r}")
                var_values[var] = hi_val
            elif var == "boss_name":
                var_values[var] = "Guest User"
            else:
                # default empty if not found
                var_values[var] = ""
        logger.debug("pre ll hook vars:", var_values)

        formatted_prompt = langchain_prompt.format_messages(**var_values)
        logger.debug(f"formatted_prompt ready to use: {formatted_prompt}")
        logger.debug(f"state: {state}")
        # Ensure list exists
        if not isinstance(state.get("history"), list):
            state["history"] = []

        # Smart history management: avoid duplicate SystemMessages
        # formatted_prompt is typically [SystemMessage(...), HumanMessage(...)]
        from langchain_core.messages import SystemMessage

        if formatted_prompt and len(formatted_prompt) > 0:
            logger.debug(f"updating messages to history......")

            first_msg = formatted_prompt[0]
            # Check if first message is a SystemMessage
            if isinstance(first_msg, SystemMessage):
                # Find the most recent SystemMessage in history (from the end)
                recent_system = None
                for _msg in reversed(state["history"]):
                    if isinstance(_msg, SystemMessage):
                        recent_system = _msg
                        break

                is_duplicate_of_recent = (
                    recent_system is not None and recent_system.content == first_msg.content
                )

                if is_duplicate_of_recent:
                    # Skip the SystemMessage, only add the rest (e.g., HumanMessage)
                    state["history"].extend(formatted_prompt[1:])
                    state["prompts"] = formatted_prompt[1:]
                    logger.debug(f"Skipped duplicate SystemMessage, added {len(formatted_prompt) - 1} messages to history")
                else:
                    # Add all messages including the new SystemMessage
                    state["history"].extend(formatted_prompt)
                    state["prompts"] = formatted_prompt
                    logger.debug(f"Added all {len(formatted_prompt)} messages to history (new SystemMessage)")
            else:
                # No SystemMessage at start, add all messages
                state["history"].extend(formatted_prompt)
                state["prompts"] = formatted_prompt
                logger.debug(f"Added all {len(formatted_prompt)} messages to history (no SystemMessage)")

        logger.debug("pre ll hook formatted_prompt:",formatted_prompt)

        logger.debug(f"standard_pre_llm_hook: {full_node_name} prompts: {formatted_prompt}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.error(err_trace)
        raise e


def standard_post_llm_func(askid, node_name, state, response):
    try:
        import json
        import ast  # Add this import at the top of your file

        # Extract content from AIMessage if needed
        raw_content = response.content if hasattr(response, 'content') else str(response)
        logger.debug(f"standard_post_llm_func Raw llm response content: {raw_content}")  # Debug log

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

        # Ensure result is always a dict, not a string representation of a dict
        if isinstance(result, str):
            # Try to parse string as JSON first
            if is_json_parsable(result):
                result = json.loads(result)
            else:
                # Try to parse as Python literal (handles single quotes)
                try:
                    parsed = ast.literal_eval(result)
                    if isinstance(parsed, dict):
                        result = parsed
                    else:
                        # Wrap non-dict results in a dict
                        result = {"message": result}
                except (ValueError, SyntaxError):
                    # If all parsing fails, wrap the string in a dict
                    result = {"message": result}
        elif not isinstance(result, dict):
            # If result is not a dict or string, wrap it
            result = {"message": str(result)}

        llm_result = {"llm_result": result}
        logger.debug(f"standard_post_llm_func: llm_result: {llm_result}")
        return llm_result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMFunc")
        logger.error(err_trace)
        raise e



def standard_post_llm_hook(askid, node_name, agent, state, response):
    try:
        # we really shouldn't send the reponse back here, instead we should update state and other node takes care of what to do with the results.
        post_hook_result = None
        state["result"] = response
        logger.debug(f"post llm hook input response: {type(response)} {response}")
        state["metadata"] = _deep_merge(state["metadata"], response["llm_result"].get("meta_data", {}))
        state["messages"].append(f"llm:{response['llm_result'].get('next_prompt', '')}")

        # Add AI response to chat history
        from langchain_core.messages import AIMessage
        next_prompt_text = response['llm_result'].get('next_prompt', '')
        work_related = response['llm_result'].get('work_related', False)
        prelim = response['llm_result'].get('preliminary_info', [{}])[0]
        if work_related:
            if prelim:
                logger.debug(f"prelim: {prelim}")
                if "part name" in prelim:
                    apps = prelim.get('applications_usage', "")
                    # "part name": "string", "oems": ["string"], "model_part_numbers": ["string"], "applications_usage": ["string"]
                    topic = f"search {prelim.get('part name')}"
                    if apps:
                        topic = topic + f" for {prelim.get('applications_usage')}"
                    if prelim.get('oems'):
                        topic = topic + f", given oems being: {prelim.get('oems')}"
                    if prelim.get('model_part_numbers'):
                        topic += f", and part number being {prelim.get('model_part_numbers')}"
                else:
                    topic = state["attributes"].get("topic", "random")
            else:
                topic = state["attributes"].get("topic", "random")
        else:
            topic = state["attributes"].get("topic", "random")

        if next_prompt_text:
            ai_message = AIMessage(content=next_prompt_text)
            if not isinstance(state.get("history"), list):
                state["history"] = []
            state["history"].append(ai_message)
            msgs = state["prompts"].append(ai_message)
            logger.debug(f"Added AIMessage to history: {next_prompt_text[:100]}...")  # Log first 100 chars

        # save this back-and-forth message pair to memory
        for msg in state["prompts"]:
            msg_id = state["attributes"]["msg_id"]
            skill_run_id = state["attributes"]["thread_id"]
            ns = (agent.card.id, askid, skill_run_id, state["attributes"]["chat_id"], topic)
            mem_item = to_memory_item(msg, ns, msg_id)
            agent.mem_manager.put(mem_item)

        logger.debug(f"standard_post_llm_hook: {post_hook_result}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMHook")
        logger.error(err_trace)


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
def run_pre_llm_hook(node_name, agent, state, prompt_src="cloud", prompt_data=None):
    try:
        mainwin = agent.mainwin
        logger.debug(f"node_name: {node_name} {agent.card.name}")
        skill_name = node_name.split(":")[1]
        this_skill = next((sk for sk in mainwin.agent_skills if sk.name == skill_name), None)
        askid = this_skill.askid
        logger.debug(f"[run_pre_llm_hook] askid: {askid}")
        askid = "skid0"
        logger.debug(f"pre llm hook node name: {node_name} {askid}")
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
        standard_pre_llm_hook(askid, node_name, agent, state, prompt_src=prompt_src, prompt_data=prompt_data)
        # available = ", ".join(sorted(PRE_LLM_HOOKS_TABLE.keys()))
        # raise KeyError(f"pre llm hook not found for '{node_name}'. Available: {available}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.error(err_trace)
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

        logger.debug(f"post llm hook  name: {node_name} {askid} {type(parsed_response)} {parsed_response}")
        # Try exact match first
        if node_name in POST_LLM_HOOKS_TABLE:
            return POST_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state, parsed_response)
        # Fallback to case-insensitive lookup
        lower_map = {k.lower(): v for k, v in POST_LLM_HOOKS_TABLE.items()}
        key_lower = node_name.lower() if isinstance(node_name, str) else node_name
        if key_lower in lower_map:
            return POST_LLM_HOOKS_TABLE[node_name](askid, node_name, agent, state, response)

        return standard_post_llm_hook(askid, node_name, agent, state, parsed_response)

        # Not found: raise informative error listing available keys
        # available = ", ".join(sorted(POST_LLM_HOOKS_TABLE.keys()))
        # raise KeyError(f"post llm hook not found for '{node_name}'. Available: {available}")
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPostLLMHook")
        logger.error(err_trace)
        return err_trace

def llm_node_with_raw_files(state:NodeState, *, runtime: Runtime, store: BaseStore) -> NodeState:
    try:
        logger.debug("in llm_node_with_raw_files....")
        user_input = state.get("input", "")
        agent_id = state["messages"][0]
        agent = get_agent_by_id(agent_id)
        mainwin = agent.mainwin
        logger.debug(f"run time: {runtime}")
        current_node_name = runtime.context["this_node"].get("name")
        skill_name = runtime.context["this_node"].get("skill_name")
        owner = runtime.context["this_node"].get("owner")

        # logger.debug(f"current node: {current_node}")
        full_node_name = f"{owner}:{skill_name}:{current_node_name}"
        run_pre_llm_hook(full_node_name, agent, state)

        logger.debug(f"networked prompts: {state['prompts']}")
        node_prompt = state["prompts"]

        # mm_content = prep_multi_modal_content(state, runtime)
        # langchain_prompt = ChatPromptTemplate.from_messages(node_prompt)
        # formatted_prompt = langchain_prompt.format_messages(component_info=state["input"], categories=state["attributes"]["categories"])

        if state["history"]:
            formatted_prompt = state["history"][-1]
        else:
            formatted_prompt = get_standard_prompt(state)            #STARDARD_PROMPT

        # Ensure formatted_prompt is a list (llm.invoke expects a list of messages)
        # If it's a single message object, wrap it in a list
        if not isinstance(formatted_prompt, list):
            formatted_prompt = [formatted_prompt]

        # Use mainwin's llm object instead of hardcoded ChatOpenAI
        llm = mainwin.llm if mainwin and mainwin.llm else None
        if not llm:
            raise ValueError("LLM not available in mainwin")


        logger.debug(f"chat node: llm prompt ready: {formatted_prompt}")
        response = llm.invoke(formatted_prompt)
        logger.debug(f"chat node: LLM response: {response}")
        # Parse the response
        run_post_llm_hook(full_node_name, agent, state, response)
        logger.debug(f"llm_node_with_raw_file finished..... {state}")
        return state
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStardardPreLLMHook")
        logger.error(err_trace)
        state["result"] = {"error": err_trace}
        return state
