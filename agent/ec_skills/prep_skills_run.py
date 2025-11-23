import json
from typing import Any, Dict, Optional
from agent.ec_skill import NodeState
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.ec_skill import FileAttachment


from agent.tasks_resume import (
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


def _node_state_baseline(agent, task_id, msg, current_state: Optional[Dict[str, Any]] = None) -> NodeState:
    """Provide a NodeState-shaped baseline for a new run."""
    print(f"type of msg {type(msg)}")
    try:
        if not isinstance(msg, dict):
            print("incoming msg: ", msg)
            params = getattr(msg, "params", None)
            attachments = []
            msg_txt = ""
            if params:
                msg_parts = msg.params.message.parts
                for part in msg_parts:
                    if part.type == "text":
                        msg_txt = part.text
                    elif part.type == "file":
                        attachments.append({"filename": part.file.name, "file_url": part.file.uri, "mime_type": part.file.mimeType,
                                    "file_data": part.file.bytes})
                chat_id = msg.params.metadata["params"]["chatId"]
                form = msg.params.metadata.get("form", {})
            else:
                chat_id = ""
                form = {}
            method = getattr(msg, "method", "")
            human = False
            msg_id = getattr(msg, "id", "")
            form = {}
        else:
            logger.info("incoming dict msg: "+json.dumps(msg, indent=2))
            if "params" in msg:
                print("hello???")
                if "content" in msg["params"]:
                    print("prep response message", msg)
                    msg_txt = msg['params']['content']
                    print("prep task with message text:", msg_txt)
                    atts = []
                    if msg['params']['attachments']:
                        for att in msg['params']['attachments']:
                            atts.append(FileAttachment(name=att['name'], type=att['type'], url=att['url'], data=""))

                    chat_id = msg['params']['chatId']
                    msg_id = msg['id']
                    human = msg['params']['human']
                    params = msg['params']
                    method = msg["method"]
                    if msg["method"] == "form_submit":
                        form = msg["params"].get("formData", {})
                    else:
                        form = {}
                else:
                    msg_id = ""
                    msg_txt = ""
                    attachments = []
                    human = False
                    params = {}
                    method = ""
                    form = {}
                    chat_id = ""
            else:
                logger.info("non paramms....")
                chat_id = ""
                msg_id = ""
                msg_txt = ""
                attachments = []
                human = False
                params = {}
                method = ""
                form = {}

        base: NodeState = {
            "input": "",
            "attachments": [],
            "prompts": [],
            "prompt_refs": {},
            "history": [],
            "messages": [agent.card.id, chat_id, msg_id, task_id, msg_txt],
            "threads": [],
            "this_node": "",
            "attributes": {"human": human, "method": method, "params": params, "agent_id": agent.card.id, "chat_id": chat_id, "msg_id": msg_id, "task_id": task_id},
            "result": {},
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
            "metadata": {"form": form},
        }
        if isinstance(current_state, dict):
            logger.debug("deep merging current state")
            base = _deep_merge(base, existing)  # type: ignore[arg-type]

        logger.debug("base node state:", base)
        return base
    except Exception as e:
        err_msg = get_traceback(e, "ErrorNodeStateBaseline")
        logger.error(f"{err_msg}")
        base = None
    return base


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
                print("deep merging node state attributes....")
                node_state["attributes"] = _deep_merge(node_state.get("attributes", {}), attrs)
            md = state_patch.get("metadata")
            if isinstance(md, dict):
                print("deep merging node state metadata....")
                node_state["metadata"] = _deep_merge(node_state.get("metadata", {}), md)
            tin = state_patch.get("tool_input")
            if isinstance(tin, dict):
                print("deep merging node state tool_input....")
                node_state["tool_input"] = _deep_merge(node_state.get("tool_input", {}), tin)
            # Merge any other top-level fields conservatively
            other = {k: v for k, v in state_patch.items() if k not in ("attributes", "metadata", "tool_input")}
            if other:
                print("deep merging node state other....")
                node_state = _deep_merge(node_state, other)  # type: ignore[assignment]
    except Exception as e:
        err_msg = get_traceback(e, "ErrorPrepSkillsRun")
        logger.error(f"{e}")
        node_state = None

    print("deep merged node state....", node_state)
    return node_state