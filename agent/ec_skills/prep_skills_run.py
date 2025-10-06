from typing import Any, Dict, Optional
from agent.ec_skill import NodeState
from utils.logger_helper import logger_helper as logger

from utils.logger_helper import get_traceback


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
    if not isinstance(msg, dict):
        msg_parts = msg.params.message.parts
        attachments = []
        msg_txt = ""
        for part in msg_parts:
            if part.type == "text":
                msg_txt = part.text
            elif part.type == "file":
                attachments.append({"filename": part.file.name, "file_url": part.file.uri, "mime_type": part.file.mimeType,
                                    "file_data": part.file.bytes})

        chat_id = msg.params.metadata["chatId"]
        msg_id = msg.id
    else:
        chat_id = ""
        msg_id = ""
        msg_txt = ""
        attachments = []

    base: NodeState = {
        "input": "",
        "attachments": [],
        "prompts": [],
        "prompt_refs": {},
        "formatted_prompts": [],
        "messages": [agent.card.id, chat_id, msg_id, task_id, msg_txt],
        "threads": [],
        "this_node": "",
        "attributes": {},
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
        "metadata": {},
    }
    if isinstance(current_state, dict):
        base = _deep_merge(base, existing)  # type: ignore[arg-type]
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


def prep_skills_run(skill, agent, task_id, msg=None, current_state=None):
    """Initialize the graph state for a skill run using DSP mapping rules.

    - Normalizes the incoming message into an `event` envelope.
    - Applies the START-node (skill-level) mapping rules to produce a state patch.
    - Deep-merges the patch into a baseline initial state and returns it.
    """
    try:
        # 1) Baseline NodeState
        node_state = _node_state_baseline(agent, task_id, msg, current_state=current_state if isinstance(current_state, dict) else None)

        # 2) Resolve START-node mapping
        mapping = _resolve_start_mapping(skill)

        # 3) Normalize incoming message to event envelope (type inferred)
        event = normalize_event("", msg)

        # 4) Apply mapping to produce state patch (ignore resume output for init)
        _resume, state_patch = build_resume_from_mapping(event=event, state=node_state, node_output=None, mapping=mapping)

        # 5) Merge mapping outputs into NodeState fields
        # Write to known sections if present in patch
        if isinstance(state_patch, dict):
            # attributes/metadata/tool_input are primary targets from DSP
            attrs = state_patch.get("attributes")
            if isinstance(attrs, dict):
                node_state["attributes"] = _deep_merge(node_state.get("attributes", {}), attrs)
            md = state_patch.get("metadata")
            if isinstance(md, dict):
                node_state["metadata"] = _deep_merge(node_state.get("metadata", {}), md)
            tin = state_patch.get("tool_input")
            if isinstance(tin, dict):
                node_state["tool_input"] = _deep_merge(node_state.get("tool_input", {}), tin)
            # Merge any other top-level fields conservatively
            other = {k: v for k, v in state_patch.items() if k not in ("attributes", "metadata", "tool_input")}
            if other:
                node_state = _deep_merge(node_state, other)  # type: ignore[assignment]
    except Exception as e:
        err_msg = get_traceback(e, "ErrorPrepSkillsRun")
        logger.error(f"{e}")
        node_state = None

    return node_state