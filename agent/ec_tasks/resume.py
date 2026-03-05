"""
Utilities for normalizing incoming events, selecting/injecting checkpoints,
and building a standardized "resume" payload + state patch using declarative
mapping rules. This module is intentionally dependency-light to avoid import
cycles with runtime/agent components.

Key concepts:
- event: unified envelope for heterogeneous incoming messages (GUI, cloud, etc.)
- resume: minimal payload sent back to orchestrator/cloud for bookkeeping
- state_patch: partial update applied into the graph state before resuming
- mapping rules: declarative rules describing how to extract/transform data
  from event/node/state into resume/state_patch.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, Union

from utils.logger_helper import logger_helper as logger


Json = Dict[str, Any]


def _safe_get(d: Any, path: str, default: Any = None) -> Any:
    """Safely get a dotted path from a nested dict.

    Example: _safe_get({"a": {"b": 1}}, "a.b") -> 1
    Returns `default` if any segment is missing.
    """
    if d is None:
        return default
    cur = d

    def _to_dict(obj: Any) -> Any:
        """Best-effort convert common container/DTO types to a dict for traversal."""
        try:
            # Pydantic v2
            if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
                return obj.model_dump(mode="python")
        except Exception:
            pass
        try:
            # Pydantic v1
            if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
                return obj.dict()
        except Exception:
            pass
        try:
            # Generic objects
            if hasattr(obj, "__dict__"):
                return vars(obj)
        except Exception:
            pass
        return obj

    for part in path.split("."):
        if cur is None:
            return default

        # 1) Direct dict access
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
                continue
            else:
                return default

        # 2) Attribute access on objects (e.g., Pydantic models)
        if hasattr(cur, part):
            try:
                cur = getattr(cur, part)
                continue
            except Exception:
                # Fall through to dict-conversion attempts
                pass

        # 3) Try converting object to dict-like and access again
        converted = _to_dict(cur)
        if isinstance(converted, dict) and part in converted:
            cur = converted[part]
            continue

        # If still not found, give up
        return default

    return cur


def _ensure_path(obj: Dict[str, Any], path: str) -> Tuple[Dict[str, Any], str]:
    """Ensure all parent objects exist for a dotted path on a dict.

    Returns a tuple of (parent_dict, leaf_key).
    """
    parts = path.split(".")
    for p in parts[:-1]:
        if p not in obj or not isinstance(obj[p], dict):
            obj[p] = {}
        obj = obj[p]
    return obj, parts[-1]


def _write(obj: Dict[str, Any], path: str, value: Any, on_conflict: str = "overwrite") -> None:
    """Write `value` to dotted `path` on `obj` with conflict policy.

    on_conflict policies:
    - overwrite (default)
    - skip
    - merge_deep | merge_shallow (dict-only)
    - append (list-only)
    """
    parent, leaf = _ensure_path(obj, path)
    if leaf in parent and parent[leaf] is not None:
        if on_conflict == "skip":
            return
        if on_conflict.startswith("merge") and isinstance(parent[leaf], dict) and isinstance(value, dict):
            # deep merge for merge_deep, shallow for merge_shallow
            if on_conflict == "merge_deep":
                parent[leaf] = _deep_merge(parent[leaf], value)
            else:
                parent[leaf].update(value)
            return
        if on_conflict == "append":
            existing = parent[leaf]
            # If the existing target is a list, append scalar or extend with list
            if isinstance(existing, list):
                if isinstance(value, list):
                    parent[leaf] += value
                else:
                    parent[leaf].append(value)
                return
            # If the existing target is a string and value is string, concatenate
            if isinstance(existing, str) and isinstance(value, str):
                parent[leaf] = existing + value
                return
            # Otherwise, fall through to overwrite for unsupported types
    else:
        # Leaf missing or None: honor append by initializing appropriately
        logger.debug("leaf missing or None", parent, leaf)
        if on_conflict == "append":
            if isinstance(value, list):
                parent[leaf] = list(value)
            else:
                # Initialize as a list to capture appended scalar values
                parent[leaf] = [value]
            return
    # Default behavior: overwrite
    parent[leaf] = value


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dict b into dict a and return a new dict."""
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_adapt_to_state_mapping(
    state_patch: Dict[str, Any],
    event_data: Dict[str, Any],
    adapt_to_state_config: Dict[str, str],
    on_conflict: str = "overwrite"
) -> None:
    """
    Apply adapt_to_state mapping from data_mapping.json to write event data to state paths.
    
    This is a modular function that can be used for any event type, not just passive_command.
    
    Args:
        state_patch: The state patch dict to write to
        event_data: The event data dict containing source values
        adapt_to_state_config: Mapping from source keys to target state paths
            Example: {
                "actions": "state.attributes.passive_command_actions",
                "run_id": "state.attributes.passive_run_id",
                "step_id": "state.attributes.passive_step_id"
            }
        on_conflict: Conflict resolution policy for _write()
    
    The target paths can start with "state." which will be stripped, or be direct paths.
    Example: "state.attributes.foo" -> writes to state_patch["attributes"]["foo"]
    """
    if not isinstance(adapt_to_state_config, dict) or not isinstance(event_data, dict):
        return
    
    for source_key, target_path in adapt_to_state_config.items():
        if not isinstance(target_path, str):
            continue
        
        # Get value from event_data
        value = event_data.get(source_key)
        if value is None:
            continue
        
        # Normalize target path - strip "state." prefix if present
        normalized_path = target_path
        if normalized_path.startswith("state."):
            normalized_path = normalized_path[6:]  # Remove "state." prefix
        
        # Write to state_patch
        try:
            _write(state_patch, normalized_path, value, on_conflict=on_conflict)
            logger.debug(f"[adapt_to_state] Wrote {source_key} -> {normalized_path}")
        except Exception as e:
            logger.warning(f"[adapt_to_state] Failed to write {source_key} -> {normalized_path}: {e}")


def _load_event_data_mapping(task: Any) -> Dict[str, Any]:
    """Load per-skill event-data-to-state mapping config from skill.mapping_rules.
    
    This reads the top-level 'event_data_mapping' (or legacy 'event_routing') key
    from the skill's data_mapping.json. These configs define how event payload fields
    are projected into the resuming node's state (adapt_to_state).
    
    Note: This is NOT task routing — that is handled by the global event_routing.json.
    """
    try:
        skill = getattr(task, "skill", None)
        if not skill:
            return {}
        mr = getattr(skill, "mapping_rules", None)
        if not isinstance(mr, dict):
            return {}
        # Prefer new key, fall back to legacy key
        edm = mr.get("event_data_mapping") or mr.get("event_routing") or {}
        return edm if isinstance(edm, dict) else {}
    except Exception:
        return {}


def _to_string(v: Any) -> str:
    """Best-effort convert a value to a UTF-8-safe JSON/string representation."""
    if isinstance(v, str):
        return v
    try:
        import json as _json
        return _json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


# ---------- Event normalization ----------

def normalize_event(event_type: str, msg: Any, src="", tag="", ctx={}) -> Dict[str, Any]:
    """Normalize heterogeneous incoming message into a unified event envelope."""
    if event_type == "":
        if isinstance(msg, dict):
            event_type = msg.get("method", "") or msg.get("type", "")
        else:
            event_type = getattr(msg, "method", "") or getattr(msg, "type", "")

    # Start with a minimal envelope
    event: Dict[str, Any] = {
        "type": event_type,
        "source": src or "",
        "tag": tag or "",
        "timestamp": "",
        "data": {},
        "context": dict(ctx) if isinstance(ctx, dict) else {},
    }

    try:
        # Extract message and metadata in a shape-agnostic way
        if hasattr(msg, "params"):
            p = msg.params
            message = getattr(p, "message", None)
            metadata = getattr(p, "metadata", {}) or {}
            event["context"].update({
                "id": getattr(p, "id", None),
                "sessionId": getattr(p, "sessionId", None),
            })
        elif isinstance(msg, dict):
            message = _safe_get(msg, "params.message") or msg.get("message")
            metadata = _safe_get(msg, "params.metadata") or msg.get("metadata") or {}
            event["context"].update({
                "id": _safe_get(msg, "params.id") or msg.get("id"),
                "sessionId": _safe_get(msg, "params.sessionId"),
            })
        else:
            message, metadata = None, {}

        # Metadata-derived fields: tag/i_tag, timestamp, context details
        if isinstance(metadata, dict):
            meta_params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
            # Tag/i_tag
            inferred_tag = (
                tag
                or metadata.get("i_tag")
                or metadata.get("tag")
                or (meta_params.get("i_tag") if isinstance(meta_params, dict) else None)
                or ""
            )
            if inferred_tag:
                event["tag"] = inferred_tag
                event["i_tag"] = inferred_tag  # backward compatibility for consumers checking i_tag

            # Timestamp (support both timestamp and createAt shapes)
            event["timestamp"] = metadata.get("timestamp") or (meta_params.get("createAt") if isinstance(meta_params, dict) else "") or ""

            # Enrich context
            event["context"].update({
                "chatId": meta_params.get("chatId") if isinstance(meta_params, dict) else metadata.get("chatId"),
                "msgId": meta_params.get("msgId") if isinstance(meta_params, dict) else metadata.get("msgId"),
                "senderId": meta_params.get("senderId") if isinstance(meta_params, dict) else metadata.get("senderId"),
                "senderName": meta_params.get("senderName") if isinstance(meta_params, dict) else metadata.get("senderName"),
            })

            # Fallback: legacy dict messages store chatId directly in msg["params"]
            if not event["context"].get("chatId") and isinstance(msg, dict):
                raw_params = msg.get("params", {})
                if isinstance(raw_params, dict):
                    event["context"]["chatId"] = raw_params.get("chatId")
                    if not event["context"].get("msgId"):
                        event["context"]["msgId"] = msg.get("id")
                    if not event["context"].get("senderId"):
                        event["context"]["senderId"] = raw_params.get("senderId")
                    if not event["context"].get("senderName"):
                        event["context"]["senderName"] = raw_params.get("senderName")

            # Event type/source best-effort
            mtype = metadata.get("mtype")
            if not event["type"]:
                event["type"] = _infer_event_type(mtype)
            if not event["source"]:
                event["source"] = (meta_params.get("senderId") if isinstance(meta_params, dict) else None) or metadata.get("senderId") or ""

        # Extract human text from message.parts
        human_text = None
        if message is not None:
            parts = getattr(message, "parts", None)
            if isinstance(parts, list) and parts:
                first = parts[0]
                text = getattr(first, "text", None)
                if text:
                    human_text = text
                elif isinstance(first, dict):
                    human_text = first.get("text")
            elif isinstance(message, dict):
                p = message.get("parts")
                if isinstance(p, list) and p:
                    first = p[0]
                    if isinstance(first, dict):
                        human_text = first.get("text")

        # Fallback: chat messages store content directly in params.content
        if not human_text and isinstance(msg, dict):
            raw_params = msg.get("params", {})
            if isinstance(raw_params, dict):
                content = raw_params.get("content")
                if isinstance(content, str) and content:
                    human_text = content

        data: Dict[str, Any] = {}
        if human_text is not None:
            data["human_text"] = human_text
        if isinstance(metadata, dict):
            data["metadata"] = metadata
        # Always include raw for debugging if nothing else
        if not data:
            data["raw"] = msg
        event["data"] = data
    except Exception as e:
        try:
            logger.debug(f"normalize_event error: {e}")
        except Exception:
            pass
        event["data"] = {"raw": msg}

    # Promote common routing fields into context for clean match paths
    # (e.g. context.run_id instead of data.raw.run_id)
    _PROMOTED_FIELDS = ("client_id", "task_id", "run_id", "timer_id", "timer_name")
    ctx = event["context"]
    for field in _PROMOTED_FIELDS:
        if ctx.get(field):
            continue  # already populated
        # 1. Top-level of raw msg
        val = msg.get(field) if isinstance(msg, dict) else getattr(msg, field, None)
        # 2. Nested in msg.command (e.g. PassiveBrowserCommand)
        if not val and isinstance(msg, dict):
            cmd = msg.get("command")
            if isinstance(cmd, dict):
                val = cmd.get(field)
            elif cmd is not None:
                val = getattr(cmd, field, None)
        if val:
            ctx[field] = val

    logger.debug("normalized event:", event)

    return event


def _infer_event_type(mtype: Optional[str]) -> str:
    """Map raw message type codes to canonical event types used downstream."""
    if not mtype:
        return "other"
    if mtype == "send_chat":
        return "human_chat"
    if mtype == "send_task":
        return "a2a"
    return mtype


def _infer_event_source(metadata: Dict[str, Any]) -> Optional[str]:
    """Derive a lightweight source identifier from metadata (e.g., gui:<chatId>)."""
    if not isinstance(metadata, dict):
        return None
    src = metadata.get("source")
    if src:
        return src
    chat_id = metadata.get("chatId")
    if chat_id:
        return f"gui:{chat_id}"
    return None


def _extract_text_from_message(message: Any) -> str:
    """Collect concatenated text from message.parts[] or message.text."""
    try:
        parts = getattr(message, "parts", None)
        if not parts and isinstance(message, dict):
            parts = message.get("parts")
        if not parts:
            return getattr(message, "text", "") if hasattr(message, "text") else (message or "")
        texts: List[str] = []
        for p in parts:
            ptype = getattr(p, "type", None) or (p.get("type") if isinstance(p, dict) else None)
            if ptype == "text":
                txt = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
                if txt:
                    texts.append(txt)
        return "\n".join(texts)
    except Exception:
        return ""


# ---------- Checkpoint selection & injection ----------

def peek_checkpoint(task: Any, tag: Optional[str]):
    """Return the checkpoint object for a given tag without removing it."""
    if not getattr(task, "checkpoint_nodes", None):
        return None
    try:
        if tag:
            for cpn in task.checkpoint_nodes:
                if cpn.get("tag") == tag:
                    return cpn.get("checkpoint")
        # fallback: latest checkpoint when tag missing
        return task.checkpoint_nodes[-1].get("checkpoint") if task.checkpoint_nodes else None
    except Exception as e:
        logger.debug(f"peek_checkpoint error: {e}")
        return None


def select_checkpoint(task: Any, tag: Optional[str]):
    """Pop and return the checkpoint object for a given tag, if present.

    Removes the matched checkpoint record from task.checkpoint_nodes to avoid
    reusing it multiple times.
    """
    if not tag:
        return None
    try:
        found_cp = next((cpn for cpn in task.checkpoint_nodes if cpn.get("tag") == tag), None)
        if found_cp:
            idx = task.checkpoint_nodes.index(found_cp)
            be_to_resumed = task.checkpoint_nodes.pop(idx)
            return be_to_resumed.get("checkpoint")
    except Exception as e:
        logger.debug(f"select_checkpoint error: {e}")
    return None


def inject_attributes_into_checkpoint(cp: Any, attrs: Dict[str, Any]) -> None:
    """Inject key/value pairs into checkpoint.values.attributes in-place.

    Creates the attributes dict if missing. Silently no-ops on unexpected
    checkpoint structure (logged at debug).
    """
    if not cp:
        return
    try:
        vals = getattr(cp, "values", None)
        if isinstance(vals, dict):
            attributes = vals.get("attributes")
            if not isinstance(attributes, dict):
                attributes = {}
                vals["attributes"] = attributes
            for k, v in attrs.items():
                attributes[k] = v
        else:
            logger.debug("inject_attributes_into_checkpoint: unexpected checkpoint values type")
    except Exception as e:
        logger.debug(f"inject_attributes_into_checkpoint error: {e}")


# ---------- Mapping rules ----------

# Base mappings shared between developing and released modes
_BASE_MAPPINGS = [
    {
        "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
        "to": [
            {"target": "state.attributes.forms.qa_form"},
            {"target": "resume.qa_form_to_agent"}
        ],
        "on_conflict": "merge_deep"
    },
    {
        "from": ["event.data.notification_to_agent", "event.data.notification"],
        "to": [
            {"target": "state.attributes.notifications.latest"},
            {"target": "resume.notification_to_agent"}
        ],
        "on_conflict": "merge_deep"
    },
    {
        "from": ["event.data.human_text"],
        "to": [
            {"target": "state.attributes.human.last_message"},
            {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
    },
    {
        "from": ["event.tag"],
        "to": [
            {"target": "state.attributes.cloud_task_id"}
        ],
        "on_conflict": "overwrite"
    },
    # Async response mode: controls whether send_response_back sends via A2A or skips
    {
        "from": ["event.data.metadata.async_response", "event.context.async_response"],
        "to": [
            {"target": "state.attributes.async_response"}
        ],
        "on_conflict": "overwrite"
    }
]

# Development-specific mapping for debug metadata
_DEV_DEBUG_MAPPING = {
    "from": ["event.data.metadata"],
    "to": [
        {"target": "state.attributes.debug.last_event_metadata"}
    ],
    "on_conflict": "overwrite"
}

DEFAULT_MAPPINGS: Dict[str, Any] = {
    "developing": {
        "mappings": _BASE_MAPPINGS + [_DEV_DEBUG_MAPPING],
        "options": {
            "strict": False,
            "default_on_missing": None,
            "apply_order": "top_down"
        }
    },
    "released": {
        "mappings": _BASE_MAPPINGS,
        "options": {
            "strict": True,
            "default_on_missing": None,
            "apply_order": "top_down"
        }
    }
}


def _resolve_from(event: Json, node: Json, state: Json, from_list: List[str], default_on_missing=None):
    """Resolve the first non-null value from a list of dotted source paths.

    Each path starts with a root namespace: event.|node.|state., followed by
    a dotted path. Returns `default_on_missing` if all candidates are None.
    """
    for path in from_list:
        root, *rest = path.split(".")
        if root == "event":
            val = _safe_get(event, ".".join(rest), default_on_missing)
        elif root == "node":
            val = _safe_get(node, ".".join(rest), default_on_missing)
        elif root == "state":
            val = _safe_get(state, ".".join(rest), default_on_missing)
        else:
            val = default_on_missing
        if val is not None:
            return val
    return default_on_missing


def _apply_transform(val: Any, transform: Optional[Union[str, Dict[str, Any]]]):
    """Apply a transform which may be a simple string or an object with args.
    Supported:
      - to_string
      - identity
      - parse_json
      - pick { path: 'a.b.c' }
      - coalesce { paths: ['x','y','z'] } (first non-null from value or context not used here)
    """
    if not transform:
        return val
    name: str
    args: Dict[str, Any] = {}
    if isinstance(transform, str):
        name = transform
    elif isinstance(transform, dict):
        name = transform.get("name") or "identity"
        args = transform.get("args") or {}
    else:
        return val

    if name == "identity":
        return val
    if name == "to_string":
        return _to_string(val)
    if name == "parse_json":
        try:
            import json as _json
            if isinstance(val, (dict, list)):
                return val
            return _json.loads(val)
        except Exception:
            return val
    if name == "pick":
        path = args.get("path")
        if isinstance(path, str):
            if isinstance(val, dict):
                return _safe_get(val, path)
            # allow picking from JSON string
            try:
                import json as _json
                parsed = _json.loads(val) if isinstance(val, str) else {}
                if isinstance(parsed, dict):
                    return _safe_get(parsed, path)
            except Exception:
                return None
        return None
    if name == "coalesce":
        # For simplicity, accept a list of paths to try within 'val' if it's a dict
        # If not dict, return val when not None
        paths = args.get("paths") or []
        if isinstance(val, dict) and paths:
            for p in paths:
                v = _safe_get(val, p)
                if v is not None:
                    return v
            return None
        return val if val is not None else None
    return val


def build_resume_from_mapping(event: Json, state: Json, node_output: Optional[Json], mapping: Json) -> Tuple[Json, Json]:
    """Apply declarative mapping rules to produce (resume, state_patch).

    - event: normalized event envelope
    - state: current graph state snapshot (read-only)
    - node_output: last node's output (if any)
    - mapping: mapping rules object ({ mappings:[...], options:{...} })
    """

    logger.debug("build_resume_from_mapping mapping===>", mapping)
    resume: Json = {}
    state_patch: Json = {}
    opts = mapping.get("options", {}) if isinstance(mapping, dict) else {}
    default_on_missing = opts.get("default_on_missing", None)
    rules = mapping.get("mappings", []) if isinstance(mapping, dict) else []
    logger.debug(f"[build_resume_from_mapping][mapping] rules: {rules}")
    for rule in rules:
        from_list = rule.get("from") or []
        to_list = rule.get("to") or []
        transform = rule.get("transform")
        on_conflict = rule.get("on_conflict", "overwrite")

        value = _resolve_from(event, node_output or {}, state or {}, from_list, default_on_missing)
        if value is None:
            try:
                logger.debug(f"[mapping] skip rule: no source value. from={from_list}")
            except Exception:
                pass
            continue

        value = _apply_transform(value, transform)
        logger.debug(f"[mapping] source value found: {value}")

        for target in to_list:
            tpath = target.get("target")
            if not tpath:
                continue
            root, *rest = tpath.split(".")
            rest_path = ".".join(rest)
            if root == "resume":
                _write(resume, rest_path, value, on_conflict)
                try:
                    logger.debug(f"[mapping] applied -> resume.{rest_path} (conflict={on_conflict})")
                except Exception:
                    pass
            elif root == "state":
                _write(state_patch, rest_path, value, on_conflict)
                try:
                    logger.debug(f"[mapping] applied -> state.{rest_path} (conflict={on_conflict})")
                except Exception:
                    pass
            else:
                logger.debug(f"Unknown mapping root: {root}")

    # Always include minimal event summary in resume for debugging/telemetry
    resume.setdefault("event", {
        "type": event.get("type"),
        "source": event.get("source"),
        "tag": event.get("tag"),
        "timestamp": event.get("timestamp"),
    })

    # Truncate screenshot data for logging
    try:
        from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
        log_state_patch = truncate_screenshot_for_logging(state_patch)
    except Exception:
        log_state_patch = str(state_patch)[:500] + "..."
    logger.debug("state after mapping:", log_state_patch)
    return resume, state_patch


def build_node_transfer_patch(node_id: str, state_snapshot: Json, node_transfer_rules: Dict[str, Any]) -> Json:
    """Build a state patch for a specific node using the same mapping DSL.

    Args:
        node_id: The id/name of the node we are resuming from.
        state_snapshot: A safe snapshot of the current state (typically checkpoint.values).
        node_transfer_rules: Dict keyed by node_id -> mapping spec ({mappings:[], options:{}}).

    Returns:
        A dict patch intended to be merged into the resume payload/state before continuing.
    """
    try:
        if not node_id or not isinstance(node_transfer_rules, dict):
            return {}
        mapping = node_transfer_rules.get(node_id)
        if not isinstance(mapping, dict):
            return {}
        # Backward compatibility: rewrite legacy node.* sources to state.result.*
        try:
            rules = mapping.get("mappings") if isinstance(mapping, dict) else None
            if isinstance(rules, list):
                rewritten = False
                for rule in rules:
                    from_list = rule.get("from") if isinstance(rule, dict) else None
                    if isinstance(from_list, list):
                        new_list = []
                        for src in from_list:
                            if isinstance(src, str) and src.startswith("node."):
                                # node.foo.bar -> state.result.foo.bar
                                new_list.append("state.result." + src[len("node."):])
                                rewritten = True
                            else:
                                new_list.append(src)
                        rule["from"] = new_list
                if rewritten:
                    mapping = {**mapping, "mappings": rules}
        except Exception:
            pass

        # Reuse the existing mapping engine. For per-node transfer, we have no external event,
        # and sources are expected to be state.* only now.
        logger.debug("build_node_transfer_patch......node_id", node_id)
        # Truncate screenshot data for logging
        try:
            from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
            log_state_snapshot = truncate_screenshot_for_logging(state_snapshot)
        except Exception:
            log_state_snapshot = str(state_snapshot)[:500] + "..."
        logger.debug("build_node_transfer_patch......state_snapshot", log_state_snapshot)
        logger.debug("build_node_transfer_patch......mapping", mapping)

        resume_patch, state_patch = build_resume_from_mapping(event={}, state=state_snapshot or {}, node_output=None, mapping=mapping)
        # We only need the state patch here; resume_patch can be ignored or used for telemetry.
        return state_patch or {}
    except Exception as e:
        try:
            logger.debug(f"build_node_transfer_patch error: {e}")
        except Exception:
            pass
        return {}

def load_mapping_for_task(task: Any) -> Dict[str, Any]:
    """Resolve mapping rules with precedence:
    1) Node-level mapping: task.skill.config.nodes[<this_node.name>].mapping_rules (node-to-node transfer)
    2) Skill-level mapping: task.skill.mapping_rules[<run_mode>] (event-to-state mapping)
    3) Defaults[<run_mode>]
    """
    try:
        skill = getattr(task, "skill", None)
        run_mode = getattr(skill, "run_mode", "released") if skill else "released"
        
        # 1) Node-level mapping (node-to-node transfer rules)
        try:
            state = (task.metadata or {}).get("state") or {}
            this_node = state.get("this_node") or {}
            node_name = this_node.get("name")
            if skill and isinstance(skill, object) and hasattr(skill, "config") and isinstance(skill.config, dict):
                logger.debug("getting node level rules:", skill.config)
                node_cfg = (skill.config.get("nodes") or {}).get(node_name) if node_name else None
                node_rules = node_cfg.get("mapping_rules") if isinstance(node_cfg, dict) else None
                if isinstance(node_rules, dict):
                    return node_rules
        except Exception:
            pass
        
        # 2) Skill-level mapping for current run_mode
        if skill and hasattr(skill, "mapping_rules") and isinstance(skill.mapping_rules, dict):
            # Check if mapping_rules has run_mode keys (developing/released)
            logger.debug("getting skill level mapping:", skill.id, skill.name, skill.mapping_rules)
            mode_rules = skill.mapping_rules.get(run_mode)
            if isinstance(mode_rules, dict):
                return mode_rules
            # Fallback: if mapping_rules doesn't have run_mode structure, return as-is (backward compat)
            if "mappings" in skill.mapping_rules:
                return skill.mapping_rules
    except Exception:
        pass
    
    # 3) Defaults for run_mode
    return DEFAULT_MAPPINGS.get(run_mode, DEFAULT_MAPPINGS.get("released", {}))

def get_current_state(task):
    current_state = (task.metadata or {}).get("state") or {}
    return current_state

def build_general_resume_payload(task: Any, msg: Any) -> Tuple[Json, Any, Json]:
    """
    Orchestrate general-purpose resume payload creation.
    Returns: (resume_payload, checkpoint, state_patch)
    """
    # Be robust to different shapes of msg/metadata. Avoid KeyError on missing i_tag.
    try:
        logger.debug(" build_general_resume_payload msg::", msg)
    except Exception:
        pass

    # Safely locate i_tag from common locations
    i_tag = (
        _safe_get(msg, "params.metadata.params.i_tag")
        or _safe_get(msg, "params.metadata.i_tag")
        or _safe_get(msg, "params.i_tag")
        or _safe_get(msg, "metadata.params.i_tag")
        or _safe_get(msg, "metadata.i_tag")
        or _safe_get(msg, "params.metadata.tag")
        or _safe_get(msg, "metadata.tag")
    )

    # Fallback: use any previously stored cloud_task_id from state
    if not i_tag:
        try:
            prev_state = get_current_state(task)
            i_tag = _safe_get(prev_state, "attributes.cloud_task_id")
        except Exception:
            i_tag = None

    # Event type best-effort
    event_type = getattr(msg, "method", None) or _safe_get(msg, "method") or ""

    logger.debug("found i_tag from raw msg::", i_tag)
    event = normalize_event(event_type, msg, tag=i_tag or "")
    # Unified tag to use for checkpoint lookup
    e_tag = event.get("i_tag") if isinstance(event, dict) and "i_tag" in event else event.get("tag")
    logger.debug("build resume load, normalized event>>>>", event)
    cp = peek_checkpoint(task, e_tag)
    if not e_tag and cp:
        try:
            # If tag missing, try to reuse latest checkpoint tag so downstream logic keeps context
            if isinstance(cp, dict):
                inferred_tag = _safe_get(cp, "values.attributes.i_tag") or _safe_get(cp, "values.attributes.cloud_task_id")
            else:
                inferred_tag = None
                try:
                    vals = getattr(cp, "values", None)
                    if isinstance(vals, dict):
                        inferred_tag = vals.get("attributes", {}).get("i_tag") or vals.get("attributes", {}).get("cloud_task_id")
                except Exception:
                    inferred_tag = None
            if inferred_tag:
                event["tag"] = inferred_tag
                event["i_tag"] = inferred_tag
                e_tag = inferred_tag
        except Exception:
            pass

    mapping = load_mapping_for_task(task)
    current_state = (task.metadata or {}).get("state") or {}
    # Truncate screenshot data for logging
    try:
        from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
        log_current_state = truncate_screenshot_for_logging(current_state)
    except Exception:
        log_current_state = str(current_state)[:500] + "..."
    logger.debug("build resume load, current_state>>>>", log_current_state)
    logger.debug("build resume load, mapping>>>>", mapping)
    resume_payload, state_patch = build_resume_from_mapping(event, current_state, node_output=None, mapping=mapping)

    # Fallback enrichment when mapping rules do not produce payload
    try:
        # Handle async_callback events (e.g., passive browser commands from cloud)
        if isinstance(msg, dict) and msg.get("type") == "async_callback":
            callback_result = msg.get("result")
            if isinstance(callback_result, dict):
                # Check if this is a passive browser command
                cmd_type = callback_result.get("type", "")
                if "browser" in cmd_type.lower() or "passive" in cmd_type.lower() or callback_result.get("actions") is not None:
                    # Extract browser command data into state_patch for browser_automation node
                    node_id = callback_result.get("node_id", "")
                    actions = callback_result.get("actions", [])
                    
                    # Put actions in tool_input for browser_automation node to find
                    if node_id:
                        _write(state_patch, f"tool_input.{node_id}.actions", actions, on_conflict="overwrite")
                        _write(state_patch, f"tool_input.{node_id}.include_screenshot", callback_result.get("include_screenshot", True), on_conflict="overwrite")
                        _write(state_patch, f"tool_input.{node_id}.stop_on_error", callback_result.get("stop_on_error", True), on_conflict="overwrite")
                    
                    # Also put in generic locations as fallback
                    _write(state_patch, "tool_input.actions", actions, on_conflict="overwrite")
                    _write(state_patch, "browser_use_actions", actions, on_conflict="overwrite")
                    _write(state_patch, "attributes.passive_command", callback_result, on_conflict="overwrite")
                    
                    # Write to paths expected by adapt_to_state config in data_mapping.json
                    # This ensures compatibility with skill-defined state paths
                    _write(state_patch, "attributes.passive_command_actions", actions, on_conflict="overwrite")
                    _write(state_patch, "attributes.passive_run_id", callback_result.get("run_id", ""), on_conflict="overwrite")
                    _write(state_patch, "attributes.passive_step_id", callback_result.get("step_id", ""), on_conflict="overwrite")
                    
                    # Apply any adapt_to_state mapping from the task's data_mapping.json
                    try:
                        edm = _load_event_data_mapping(task)
                        passive_cmd_edm = edm.get("passive_command", {}) or edm.get("PassiveCommandEvent", {})
                        adapt_config = passive_cmd_edm.get("adapt_to_state", {})
                        if adapt_config:
                            apply_adapt_to_state_mapping(state_patch, callback_result, adapt_config)
                            logger.debug(f"[build_general_resume_payload] Applied adapt_to_state mapping: {list(adapt_config.keys())}")
                    except Exception as adapt_err:
                        logger.debug(f"[build_general_resume_payload] adapt_to_state mapping skipped: {adapt_err}")
                    
                    logger.info(f"[build_general_resume_payload] Extracted passive browser command: node_id={node_id}, actions_count={len(actions)}, state_patch_keys={list(state_patch.keys())}")
                else:
                    # Generic async_callback result - store in attributes
                    _write(state_patch, "attributes.async_callback_result", callback_result, on_conflict="overwrite")
                    
                    # Try to apply adapt_to_state mapping for any event type
                    try:
                        edm = _load_event_data_mapping(task)
                        # Check for event_data_mapping config matching the callback result type
                        result_type = callback_result.get("type", "")
                        type_edm = edm.get(result_type, {})
                        adapt_config = type_edm.get("adapt_to_state", {})
                        if adapt_config:
                            apply_adapt_to_state_mapping(state_patch, callback_result, adapt_config)
                            logger.debug(f"[build_general_resume_payload] Applied adapt_to_state for {result_type}: {list(adapt_config.keys())}")
                    except Exception:
                        pass
        
        # Capture chat metadata for send_chat events
        message_mtype = (
            _safe_get(msg, "params.message.metadata.mtype")
            or _safe_get(msg, "params.metadata.mtype")
            or event.get("data", {}).get("metadata", {}).get("mtype")
        ) if isinstance(event, dict) else None
        resume_payload["event_type"] = message_mtype or event.get("type", "")
        # Include the full normalized event envelope so downstream nodes can inspect it
        resume_payload["_event_envelope"] = event
        if isinstance(message_mtype, str) and "send_chat" in message_mtype.lower():
            chat_params = _safe_get(msg, "params.metadata.params") or {}
            chat_attrs = {"mtype": message_mtype}
            for key in ("chatId", "senderId", "content", "receiverId", "attachments"):
                value = chat_params.get(key)
                if value is not None:
                    chat_attrs[key] = value
            if chat_attrs:
                resume_payload.setdefault("chat_attributes", {}).update(chat_attrs)

        # Enrich state_patch with chatId from event context when not already set
        # This ensures human chat messages propagate chatId into the running state
        evt_ctx = event.get("context", {}) if isinstance(event, dict) else {}
        evt_chat_id = evt_ctx.get("chatId")
        if evt_chat_id and not _safe_get(state_patch, "attributes.chat_id"):
            _write(state_patch, "attributes.chat_id", evt_chat_id, on_conflict="overwrite")
        if evt_chat_id and not _safe_get(state_patch, "messages"):
            # messages[1] is the chat_id slot in the baseline state
            existing_msgs = current_state.get("messages", [])
            if isinstance(existing_msgs, list) and len(existing_msgs) > 1 and not existing_msgs[1]:
                new_msgs = list(existing_msgs)
                new_msgs[1] = evt_chat_id
                _write(state_patch, "messages", new_msgs, on_conflict="overwrite")

        event_data = event.get("data", {}) if isinstance(event, dict) else {}
        human_text = event_data.get("human_text")
        if human_text and not resume_payload.get("human_text"):
            resume_payload["human_text"] = human_text
        if human_text and not _safe_get(state_patch, "attributes.human.last_message"):
            _write(state_patch, "attributes.human.last_message", human_text, on_conflict="overwrite")

        # Append the user's chat message to history so the LLM sees it in conversation context
        if human_text:
            try:
                from langchain_core.messages import HumanMessage
                existing_history = current_state.get("history") or []
                # Only add if not already the last message in history (avoid duplicates)
                already_present = (
                    existing_history
                    and hasattr(existing_history[-1], "content")
                    and existing_history[-1].content == human_text
                )
                if not already_present:
                    new_history = list(existing_history) + [HumanMessage(content=human_text)]
                    _write(state_patch, "history", new_history, on_conflict="overwrite")
                    logger.info(f"[resume] Added user message to history: len={len(human_text)}")
            except Exception as hist_err:
                logger.debug(f"[resume] Could not add user message to history: {hist_err}")

        metadata = event_data.get("metadata") if isinstance(event_data, dict) else None
        if metadata and not _safe_get(state_patch, "attributes.debug.last_event_metadata"):
            _write(state_patch, "attributes.debug.last_event_metadata", metadata, on_conflict="overwrite")
    except Exception:
        pass

    # Truncate screenshot data for logging
    try:
        from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
        log_state_patch = truncate_screenshot_for_logging(state_patch)
    except Exception:
        log_state_patch = str(state_patch)[:500] + "..."
    logger.debug("build_general_resume_payload===>", resume_payload)
    logger.debug("state_patch===>", log_state_patch)
    # Preserve existing behavior: inject cloud_task_id into checkpoint attributes, and mirror into state attributes
    cloud_task_id = event.get("tag")
    if cp and cloud_task_id:
        inject_attributes_into_checkpoint(cp, {"cloud_task_id": cloud_task_id})
        # Also reflect in our cached state attributes if present
        try:
            attrs = current_state.get("attributes")
            if isinstance(attrs, dict):
                attrs["cloud_task_id"] = cloud_task_id
        except Exception:
            pass

    return resume_payload, cp, state_patch
