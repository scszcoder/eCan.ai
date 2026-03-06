import json
from typing import Any, Dict, Optional, TYPE_CHECKING
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

if TYPE_CHECKING:
    # Only import for type checking to avoid circular import at runtime
    from agent.ec_skill import NodeState, FileAttachment


from agent.ec_tasks.resume import (
    DEFAULT_MAPPINGS,
    build_resume_from_mapping,
    normalize_event,
)


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dict b into dict a and return a new dict."""
    out = dict(a or {})
    for k, v in (b or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _node_state_baseline(agent, task_id, msg, current_state: Optional[Dict[str, Any]] = None) -> "NodeState":
    """Provide a NodeState-shaped baseline for a new run.
    
    Note: msg=None is expected for schedule-triggered tasks (they have no input message).
    This is by design - see tasks.py line 2180: "Scheduled tasks don't have input messages"
    """
    _tag = "[_node_state_baseline]"
    agent_id = agent.card.id if agent and hasattr(agent, 'card') else None
    
    # msg=None is expected for schedule/initial triggers - not an error
    is_empty_msg = msg is None
    if is_empty_msg:
        logger.debug(f"{_tag} START: agent_id={agent_id}, task_id={task_id}, msg=None (schedule trigger)")
    else:
        logger.debug(f"{_tag} START: agent_id={agent_id}, task_id={task_id}, msg_type={type(msg).__name__}, has_current_state={current_state is not None}")
    
    # Track missing fields for summary log (only track unexpected missing fields)
    missing_fields = []
    
    try:
        if not isinstance(msg, dict):
            # Non-dict message (e.g., TaskSendParams object or None for schedule triggers)
            raw_params = getattr(msg, "params", None) if msg else None
            attachments = []
            msg_txt = ""
            
            # Convert TaskSendParams to dict for consistent handling downstream
            if raw_params is not None:
                if hasattr(raw_params, "model_dump"):
                    params = raw_params.model_dump()
                elif hasattr(raw_params, "dict"):
                    params = raw_params.dict()
                else:
                    params = raw_params
            else:
                params = {}
                if not is_empty_msg:
                    missing_fields.append("raw_params")
            
            if raw_params:
                msg_parts = msg.params.message.parts
                for part in msg_parts:
                    # New a2a-sdk uses 'kind' instead of 'type'
                    part_type = getattr(part, 'kind', None) or getattr(part, 'type', None)
                    if part_type == "text":
                        msg_txt = getattr(part, 'text', '')
                    elif part_type == "file":
                        file_obj = getattr(part, 'file', part)
                        attachments.append({"filename": getattr(file_obj, 'name', ''), "file_url": getattr(file_obj, 'uri', ''), "mime_type": getattr(file_obj, 'mimeType', getattr(file_obj, 'mime_type', '')),
                                    "file_data": getattr(file_obj, 'bytes', '')})
                meta_params = msg.params.metadata.get("params", {}) if msg.params.metadata else {}
                if not msg.params.metadata:
                    missing_fields.append("metadata")
                chat_id = meta_params.get("chatId", "")
                if not chat_id:
                    missing_fields.append("chatId")
                form = msg.params.metadata.get("form", {}) if msg.params.metadata else {}
            else:
                chat_id = ""
                form = {}
            
            method = getattr(msg, "method", "") if msg else ""
            human = False
            msg_id = getattr(msg, "id", "") if msg else ""
            if not is_empty_msg:
                if not method:
                    missing_fields.append("method")
                if not msg_id:
                    missing_fields.append("msg_id")
            form = {}
            
            logger.debug(f"{_tag} Non-dict msg parsed: chat_id={chat_id or 'N/A'}, msg_id={msg_id or 'N/A'}, method={method or 'N/A'}, msg_len={len(msg_txt)}, attachments={len(attachments)}, missing={missing_fields or 'none'}")
        else:
            # Dict message
            if "params" in msg:
                params = msg["params"]
                # Handle new A2A SDK dict structure (from _build_request_object)
                # Structure: {"id": ..., "params": {"message": {...}, "metadata": {...}, ...}}
                if "message" in params and isinstance(params["message"], dict):
                    # New A2A SDK format - extract from message dict
                    message_data = params["message"]
                    # Extract text from parts
                    msg_txt = ""
                    atts = []
                    parts = message_data.get("parts", [])
                    for part in parts:
                        part_kind = part.get("kind") or part.get("type")
                        if part_kind == "text":
                            msg_txt = part.get("text", "")
                        elif part_kind == "file":
                            from agent.ec_skill import FileAttachment
                            file_data = part.get("file", part)
                            atts.append(FileAttachment(
                                name=file_data.get("name", ""),
                                type=file_data.get("mimeType", file_data.get("mime_type", "")),
                                url=file_data.get("uri", ""),
                                data=""
                            ))
                    
                    # Extract metadata
                    metadata = params.get("metadata", {})
                    meta_params = metadata.get("params", {})
                    chat_id = meta_params.get("chatId", params.get("sessionId", ""))
                    msg_id = msg.get("id", "")
                    human = meta_params.get("human", False)
                    method = metadata.get("mtype", msg.get("method", ""))
                    form = metadata.get("form", {})
                    attachments = atts
                    
                    if not chat_id: missing_fields.append("chatId")
                    if not msg_id: missing_fields.append("msg_id")
                    if not method: missing_fields.append("method")
                    
                elif "content" in params:
                    # Legacy format
                    msg_txt = params['content']
                    atts = []
                    if params.get('attachments'):
                        for att in params['attachments']:
                            from agent.ec_skill import FileAttachment
                            atts.append(FileAttachment(name=att['name'], type=att['type'], url=att['url'], data=""))

                    chat_id = params.get('chatId', '')
                    msg_id = msg.get('id', '')
                    human = params.get('human', False)
                    method = msg.get("method", "")
                    
                    if not chat_id: missing_fields.append("chatId")
                    if not msg_id: missing_fields.append("msg_id")
                    if not method: missing_fields.append("method")
                    
                    if msg.get("method") == "form_submit":
                        form = msg["params"].get("formData", {})
                    else:
                        form = {}
                else:
                    missing_fields.append("content")
                    msg_id = ""
                    msg_txt = ""
                    attachments = []
                    human = False
                    params = {}
                    method = ""
                    form = {}
                    chat_id = ""
            else:
                missing_fields.append("params")
                chat_id = ""
                msg_id = ""
                msg_txt = ""
                attachments = []
                human = False
                params = {}
                method = ""
                form = {}
            
            logger.debug(f"{_tag} Dict msg parsed: chat_id={chat_id or 'N/A'}, msg_id={msg_id or 'N/A'}, method={method or 'N/A'}, human={human}, msg_len={len(msg_txt) if msg_txt else 0}, missing={missing_fields or 'none'}")

        # Extract async_response from request metadata if available
        # This controls whether send_response_back sends via A2A or skips (sync mode)
        async_response = None
        try:
            if msg and hasattr(msg, 'params') and msg.params and hasattr(msg.params, 'metadata') and msg.params.metadata:
                async_response = msg.params.metadata.get("async_response")
            elif isinstance(msg, dict):
                # New A2A SDK format: msg["params"]["metadata"]["async_response"]
                if "params" in msg and isinstance(msg["params"], dict) and "metadata" in msg["params"]:
                    async_response = msg["params"]["metadata"].get("async_response")
                elif "metadata" in msg:
                    async_response = msg["metadata"].get("async_response")
        except Exception:
            pass

        base: "NodeState" = {
            "input": "",
            "attachments": [],
            "prompts": [],
            "prompt_refs": {},
            "history": [],
            "events": [],
            "messages": [agent.card.id, chat_id, msg_id, task_id, msg_txt],
            "threads": [],
            "this_node": "",
            "attributes": {
                "human": human, 
                "method": method, 
                "params": params, 
                "agent_id": agent.card.id, 
                "chat_id": chat_id, 
                "msg_id": msg_id, 
                "task_id": task_id,
                "async_response": async_response,  # Controls response mode in send_response_back
            },
            "result": {"llm_result": {"all_done": False, "work_done": False}},
            "tool_name": "",
            "tool_input": {},
            "tool_result": {},
            "http_response": {},
            "cli_input": {},
            "cli_results": {},
            "error": "",
            "retries": 0,
            "condition": False,
            "condition_vars": {},
            "loop_end_vars": {},
            "case": "",
            "goals": [],
            "breakpoint": False,
            "max_steps": 300,
            "n_steps": 0,
            "metadata": {"form": form},
        }
        if isinstance(current_state, dict):
            base = _deep_merge(base, current_state)  # type: ignore[arg-type]
            logger.debug(f"{_tag} Merged with current_state (keys={list(current_state.keys())})")

        # Summary log - warning only for unexpected missing fields (not for empty msg)
        if missing_fields:
            logger.warning(f"{_tag} DONE: missing_fields={missing_fields}")
        elif is_empty_msg:
            logger.debug(f"{_tag} DONE: empty msg (schedule/initial trigger), using defaults")
        logger.debug(f"{_tag} DONE: chat_id={chat_id or 'N/A'}, task_id={task_id}, method={method or 'N/A'}")
        return base
    except Exception as e:
        err_msg = get_traceback(e, "ErrorNodeStateBaseline")
        logger.error(f"{_tag} ERROR: {err_msg}")
        return None


def _resolve_start_mapping(skill) -> Dict[str, Any]:
    """Pick mapping rules for initialization (START node rules / skill-level mapping).

    Precedence:
      1) skill.mapping_rules[run_mode] if present
      2) skill.mapping_rules (legacy, has 'mappings')
      3) DEFAULT_MAPPINGS[run_mode]
    """
    try:
        run_mode = getattr(skill, "run_mode", None) or "released"
        rules = getattr(skill, "mapping_rules", None)
        if isinstance(rules, dict):
            # New structure: separated by run_mode
            mode_rules = rules.get(run_mode)
            if isinstance(mode_rules, dict):
                return mode_rules
            # Legacy structure: contains 'mappings' at top-level
            if "mappings" in rules:
                return rules
    except Exception:
        pass
    return DEFAULT_MAPPINGS.get("released", {}) if getattr(skill, "run_mode", None) is None else DEFAULT_MAPPINGS.get(skill.run_mode, DEFAULT_MAPPINGS.get("released", {}))


# possible message types:
# 1. IPCRequest - from GUI front-end
# 2. SendTaskRequest
# 3. dict
# 4. websocket - event
# 5. mcp tool call results --
def prep_skills_run(skill, agent, task_id, msg=None, current_state=None):
    """Initialize the graph state for a skill run using DSP mapping rules.

    - Normalizes the incoming message into an `event` envelope.
    - Applies the START-node (skill-level) mapping rules to produce a state patch.
    - Deep-merges the patch into a baseline initial state and returns it.
    """
    try:

        # 1) Baseline NodeState
        node_state = _node_state_baseline(agent, task_id, msg, current_state=current_state if isinstance(current_state, dict) else None)
        logger.debug("[prep_skills_run] initial node state: ", node_state)

        # 1a) Inject node-level mapping rules from the skill's data_mapping.json
        try:
            rules = getattr(skill, "mapping_rules", {}) or {}
            node_transfers = rules.get("node_transfers", {}) if isinstance(rules, dict) else {}
            if not isinstance(node_state.get("attributes"), dict):
                node_state["attributes"] = {}
            node_state["attributes"]["node_transfer_rules"] = node_transfers if isinstance(node_transfers, dict) else {}
            logger.debug("[prep_skills_run] injected node_transfer_rules keys: ", list((node_transfers or {}).keys()))
        except Exception as _e:
            logger.debug("[prep_skills_run] skipping node_transfer_rules inject due to error: " + str(_e))

        # 2) Resolve START-node mapping
        mapping = _resolve_start_mapping(skill)
        logger.debug("[prep_skills_run] mapping: ", mapping)

        # 3) Normalize incoming message to event envelope (type inferred)
        logger.debug("[prep_skills_run] incoming message: ", msg)
        event = normalize_event("", msg)
        logger.debug("[prep_skills_run] normalized event: ", event)

        # 4) Apply mapping to produce state patch (ignore resume output for init)
        _resume, state_patch = build_resume_from_mapping(event=event, state=node_state, node_output=None, mapping=mapping)
        logger.debug("[prep_skills_run] resume: ", _resume)
        logger.debug("[prep_skills_run] state_patch: ", state_patch)
        # 5) Merge mapping outputs into NodeState fields
        # Write to known sections if present in patch
        if isinstance(state_patch, dict):
            # Preserve append semantics for list-like fields produced by mapping
            if "messages" in state_patch:
                sp_msgs = state_patch.pop("messages")
                try:
                    if isinstance(sp_msgs, list):
                        if isinstance(node_state.get("messages"), list):
                            node_state["messages"].extend(sp_msgs)
                        else:
                            node_state["messages"] = list(sp_msgs)
                    else:
                        # coerce scalar into list and append
                        if isinstance(node_state.get("messages"), list):
                            node_state["messages"].append(sp_msgs)
                        else:
                            node_state["messages"] = [sp_msgs]
                except Exception:
                    # fallback to overwrite if anything goes wrong
                    node_state["messages"] = sp_msgs
            # attributes/metadata/tool_input are primary targets from DSP
            attrs = state_patch.get("attributes")
            if isinstance(attrs, dict):
                logger.debug("deep merging node state attributes....")
                node_state["attributes"] = _deep_merge(node_state.get("attributes", {}), attrs)
            md = state_patch.get("metadata")
            if isinstance(md, dict):
                logger.debug("deep merging node state metadata....")
                node_state["metadata"] = _deep_merge(node_state.get("metadata", {}), md)
            tin = state_patch.get("tool_input")
            if isinstance(tin, dict):
                logger.debug("deep merging node state tool_input....")
                node_state["tool_input"] = _deep_merge(node_state.get("tool_input", {}), tin)
            # Merge any other top-level fields conservatively
            other = {k: v for k, v in state_patch.items() if k not in ("attributes", "metadata", "tool_input")}
            if other:
                logger.debug("deep merging node state other....")
                node_state = _deep_merge(node_state, other)  # type: ignore[assignment]
    except Exception as e:
        err_msg = get_traceback(e, "ErrorPrepSkillsRun")
        logger.error(f"{err_msg}")
        node_state = None

    logger.debug("deep merged node state....", node_state)
    return node_state