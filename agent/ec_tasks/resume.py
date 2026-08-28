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

import json
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


def _parse_browser_event_body(msg: Any) -> Dict[str, Any]:
    """Best-effort parse browser_event payloads from msg.params.body/responseBody."""
    try:
        if not isinstance(msg, dict):
            return {}
        event = msg.get("event")
        if isinstance(event, dict):
            payload = event.get("payload")
            if isinstance(payload, dict):
                return dict(payload)
        params = msg.get("params")
        if not isinstance(params, dict):
            return {}
        for key in ("body", "responseBody", "payload", "data"):
            raw = params.get(key)
            if isinstance(raw, dict):
                return dict(raw)
            if isinstance(raw, str):
                s = raw.strip()
                if not s:
                    continue
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        return {}
    except Exception:
        return {}


def _parse_browser_event_envelope(msg: Any) -> Dict[str, Any]:
    try:
        if not isinstance(msg, dict):
            return {}
        event = msg.get("event")
        return dict(event) if isinstance(event, dict) else {}
    except Exception:
        return {}


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
            
            # A2A message format: params.message.metadata contains mtype
            # Extract mtype from params.message.metadata if available
            _msg_metadata = _safe_get(msg, "params.message.metadata") if isinstance(_safe_get(msg, "params.message"), dict) else None
            if _msg_metadata and isinstance(_msg_metadata, dict):
                _a2a_mtype = _msg_metadata.get("mtype")
                if _a2a_mtype:
                    # Merge A2A message metadata into main metadata for consistent access
                    metadata = dict(metadata)  # Copy to avoid mutation
                    metadata["mtype"] = _a2a_mtype
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
                "receiverId": meta_params.get("receiverId") if isinstance(meta_params, dict) else metadata.get("receiverId"),
                "transport": _infer_transport(metadata.get("mtype"), metadata, src),
                "senderType": _infer_sender_type(metadata),
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
                    if not event["context"].get("receiverId"):
                        event["context"]["receiverId"] = raw_params.get("receiverId")
                    if not event["context"].get("transport"):
                        event["context"]["transport"] = raw_params.get("transport")
                    if not event["context"].get("senderType"):
                        event["context"]["senderType"] = "human" if raw_params.get("human") is True else raw_params.get("senderType")

            # Fallback: chat_tools._build_chat_message stores senderId/chatId in msg["attributes"]["params"]
            # This is the standard format for inter-agent A2A messages
            if not event["context"].get("senderId") and isinstance(msg, dict):
                _attrs = msg.get("attributes", {})
                _attrs_params = _attrs.get("params", {}) if isinstance(_attrs, dict) else {}
                if isinstance(_attrs_params, dict):
                    if not event["context"].get("senderId"):
                        event["context"]["senderId"] = _attrs_params.get("senderId")
                    if not event["context"].get("senderName"):
                        event["context"]["senderName"] = _attrs_params.get("senderName")
                    if not event["context"].get("receiverId"):
                        event["context"]["receiverId"] = _attrs_params.get("receiverId")
                    if not event["context"].get("chatId"):
                        event["context"]["chatId"] = _attrs_params.get("chatId")
                    if not event["context"].get("transport"):
                        event["context"]["transport"] = _attrs_params.get("transport")
                    if not event["context"].get("senderType"):
                        event["context"]["senderType"] = _attrs_params.get("senderType")

            # Also promote attributes.params into event.data.params for mapping rules
            # (mapping rules read from event.data, not event.context)
            if isinstance(msg, dict):
                _attrs = msg.get("attributes", {})
                if isinstance(_attrs, dict):
                    _attrs_params = _attrs.get("params")
                    if isinstance(_attrs_params, dict) and not isinstance(message, dict):
                        # Only set params if not already extracted from params.message
                        event["data"]["params"] = _attrs_params

                    # CRITICAL: Promote notification from attributes.params.content.notification
                    # This is where send_response_back stores the a2a_task_result notification.
                    # NOTE: _attrs_params is None when the msg has no `attributes.params`
                    # (e.g. plain A2A SendTaskRequest dicts) — `.get()` on None raises
                    # AttributeError, which the outer try/except swallows and replaces
                    # event["data"] with {"raw": msg}, silently dropping human_text.
                    # The dev merge introduced this NPE; gate on isinstance() to fix it.
                    if isinstance(_attrs_params, dict):
                        _content = _attrs_params.get("content", {})
                        if isinstance(_content, dict):
                            _notification = _content.get("notification", {})
                            if isinstance(_notification, dict) and _notification.get("type") == "a2a_task_result":
                                if not event["context"].get("notification"):
                                    event["context"]["notification"] = _notification
                                    logger.info(f"[normalize_event] Promoted a2a_task_result notification to context")

            # Event type/source best-effort
            mtype = metadata.get("mtype")
            inferred_type = _infer_event_type(mtype)
            if not event["type"] or event["type"] == "other":
                if inferred_type and inferred_type != "other":
                    event["type"] = inferred_type
            if not event["source"]:
                event["source"] = (meta_params.get("senderId") if isinstance(meta_params, dict) else None) or metadata.get("senderId") or ""
            
            # Detect A2A agent responses: when a message comes from another agent (not human),
            # and has mtype=send_chat, it should be treated as a2a_response to trigger
            # pend_event nodes listening for a2a_task_result
            _sender_type = _infer_sender_type(metadata)
            _transport = _infer_transport(mtype, metadata, src)
            _current_type = event.get("type", "")
            
            # CRITICAL: Check if notification.type indicates a2a_task_result
            # This takes priority over other type detection
            _notification_in_attrs = None
            if isinstance(_attrs_params, dict):
                _content = _attrs_params.get("content", {})
                if isinstance(_content, dict):
                    _notification_in_attrs = _content.get("notification", {})
            if isinstance(_notification_in_attrs, dict) and _notification_in_attrs.get("type") == "a2a_task_result":
                event["type"] = "a2a_task_result"
                logger.info(f"[normalize_event] Detected a2a_task_result via notification.type, setting event type")
            elif (
                _sender_type == "agent"
                and _transport == "a2a"
                and _current_type == "chat_message"
            ):
                # This is a response from another agent, mark it as a2a_response
                event["type"] = "a2a_response"
                logger.debug(f"[normalize_event] Detected A2A agent response, setting type to a2a_response")

        # Extract human text from message.parts
        #
        # IMPORTANT: a2a-sdk Part is `RootModel[TextPart | FilePart | DataPart]`,
        # so an incoming Message deserialized by the A2A SDK has
        # `parts=[Part(root=TextPart(text=...)), ...]` — the text lives at
        # `part.root.text`, not `part.text`. We must check the `root.text`
        # path *before* falling back to `part.text` / `part["text"]`, or every
        # A2A-wrapped reply (e.g. Q&A response_text payloads delivered to the
        # front-desk live-chat task) silently loses its body, which kills the
        # direct-delivery fast-path in `_try_direct_live_chat_delivery`. See also
        # `_queue_msg_text` and `_scan_for_text` in runner.py — both already
        # walk the same ladder; this brings normalize_event into agreement.
        human_text = None
        if message is not None:
            # Support both object and dict formats for message
            parts = None
            if isinstance(message, dict):
                parts = message.get("parts")
            else:
                parts = getattr(message, "parts", None)

            if isinstance(parts, list) and parts:
                first = parts[0]
                # Path A: Part wrapping a typed part (a2a-sdk RootModel).
                if isinstance(first, dict):
                    root = first.get("root")
                    if isinstance(root, dict):
                        text = root.get("text")
                        if isinstance(text, str) and text:
                            human_text = text
                    if human_text is None:
                        text = first.get("text")
                        if isinstance(text, str) and text:
                            human_text = text
                else:
                    root = getattr(first, "root", None)
                    if root is not None:
                        text = getattr(root, "text", None)
                        if isinstance(text, str) and text:
                            human_text = text
                    if human_text is None:
                        text = getattr(first, "text", None)
                        if isinstance(text, str) and text:
                            human_text = text
            elif isinstance(message, dict):
                p = message.get("parts")
                if isinstance(p, list) and p:
                    first = p[0]
                    if isinstance(first, dict):
                        root = first.get("root")
                        if isinstance(root, dict):
                            text = root.get("text")
                            if isinstance(text, str) and text:
                                human_text = text
                        if human_text is None:
                            text = first.get("text")
                            if isinstance(text, str) and text:
                                human_text = text

        # Fallback: chat messages store content directly in params.content
        if not human_text and isinstance(msg, dict):
            raw_params = msg.get("params", {})
            if isinstance(raw_params, dict):
                content = raw_params.get("content")
                if isinstance(content, str) and content:
                    human_text = content
                elif isinstance(content, dict) and content.get("text"):
                    human_text = content["text"]

        # Fallback: chat_tools._build_chat_message stores content in attributes.params.content
        if not human_text and isinstance(msg, dict):
            _attrs = msg.get("attributes", {})
            if isinstance(_attrs, dict):
                _attrs_params = _attrs.get("params", {})
                if isinstance(_attrs_params, dict):
                    content = _attrs_params.get("content")
                    if isinstance(content, str) and content:
                        human_text = content
                    elif isinstance(content, dict) and content.get("text"):
                        human_text = content["text"]

        # CRITICAL FIX: For a2a_task_result events, the content is structured JSON data,
        # NOT human-readable text. We should NOT inject it into human_text which causes
        # the entire skill to re-execute from the beginning (info_collector triggered again).
        # Instead, store it in the notification field for proper pend_event handling.
        if event_type == "a2a_task_result":
            _notification = event["context"].get("notification", {})
            if isinstance(_notification, dict):
                _result = _notification.get("result", {})
                if isinstance(_result, dict):
                    _msg_content = _result.get("message")
                    if isinstance(_msg_content, str) and _msg_content.strip().startswith("{"):
                        # This is JSON data from the sub-agent, store it separately
                        # Don't inject into human_text - it will be parsed by pend_event_node
                        logger.info(f"[normalize_event] a2a_task_result detected with JSON payload, NOT injecting to human_text")
                        # The notification payload will be properly handled by pend_event_node
                        # via the context.notification field

        data: Dict[str, Any] = {}
        if human_text is not None and event_type != "a2a_task_result":
            # Only set human_text for non-a2a_task_result events
            # a2a_task_result events have their payload in context.notification
            data["human_text"] = human_text
        elif human_text is not None and event_type == "a2a_task_result":
            # For a2a_task_result, store the raw content in data.notification_payload for debugging
            data["notification_payload"] = human_text
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
    _PROMOTED_FIELDS = ("client_id", "task_id", "run_id", "timer_id", "timer_name", "sub_type", "sub_id")
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
    # ws053: demoted INFO->DEBUG. normalize_event runs ~4x per turn (same event
    # re-normalized through the dispatch/resume path), and the human_text is
    # already captured at INFO by the live-chat bundle's WS-shadow and trace-ledger
    # latest_preview lines.
    logger.debug(f"[normalize_event] event.data.human_text='{str(event.get('data', {}).get('human_text', ''))[:200]}'")
    return event


def _infer_event_type(mtype: Optional[str]) -> str:
    """Map raw message type codes to canonical event types used downstream."""
    if not mtype:
        return "other"
    if mtype == "send_chat":
        return "chat_message"
    if mtype == "send_task":
        return "task_request"
    return mtype


def _infer_transport(mtype: Optional[str], metadata: Dict[str, Any], source: Optional[str]) -> str:
    if isinstance(metadata, dict):
        meta_params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
        transport = meta_params.get("transport") or metadata.get("transport")
        if transport:
            return str(transport)
    if mtype in {"send_chat", "send_task", "dev_send_chat"}:
        return "a2a"
    if source and str(source).startswith("gui:"):
        return "gui"
    return ""


def _infer_sender_type(metadata: Dict[str, Any]) -> str:
    if not isinstance(metadata, dict):
        return ""
    meta_params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    sender_type = meta_params.get("senderType") or metadata.get("senderType")
    if sender_type:
        return str(sender_type)
    if meta_params.get("human") is True or metadata.get("human") is True:
        return "human"
    role = meta_params.get("role") or metadata.get("role")
    if role == "agent":
        return "agent"
    return ""


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
    },
    # Note: chat_attributes is set directly by build_general_resume_payload for send_chat events
    # No mapping rule needed here - the direct assignment handles this case
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
            logger.info(f"[resume._resolve_from] ✓ resolved path='{path}' -> val='{str(val)[:200]}'")
            return val
    logger.info(f"[resume._resolve_from] ✗ no value found for any path in {from_list}")
    logger.info(f"[resume._resolve_from]   event keys: {list(event.keys()) if isinstance(event, dict) else type(event)}")
    logger.info(f"[resume._resolve_from]   state keys: {list(state.keys()) if isinstance(state, dict) else type(state)}")
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
    logger.info(f"[build_resume_from_mapping][mapping] rules_count={len(rules)}, rules={rules}")
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
        node_id: Target node id being entered (matches node_transfers keys in data_mapping.json).
        state_snapshot: Current LangGraph state (sources are typically state.tool_result.*).
        node_transfer_rules: Dict keyed by target node_id -> mapping spec ({mappings:[], options:{}}).

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
    # 2026-05-19 Option F REVERTED.  An earlier attempt restored the
    # runner-side _EVT_TYPE_ATTR='chat_message' tag here so HOT-PATH-B
    # would fire from the bypass-fallback path.  It did fire (14× in
    # the 2026-05-19 16:36 test) but immediately failed: HOT-PATH-B's
    # `acquire live-chat typing lock for cust=... within 12.0s` budget
    # times out under flood because the direct-delivery worker is
    # holding the lock continuously, and the per-task-queue path then
    # explicitly drops the reply with "the Q&A bot's answer was lost".
    # Net result: 12 dropped replies via HOT-PATH-B timeout instead of
    # 1 dropped via silent dedup.  Two competing consumers for one
    # typing-lock is architecturally wrong.
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

    # --- Inject prompt_refs.events for chat_message resumes ---
    # Mirrors prep_skills_run._extract_chat_message_input_patch: downstream
    # browser_automation nodes (HOT-PATH-B) read state.prompt_refs.events to
    # decide Phase 1 (dispatch) vs Phase 2 (reply). Without this write, parallel
    # node invocations during resume see an empty envelope and fall back to the
    # stale attributes.browser_event (event_type=none), producing template
    # responses and out-of-order delivery. pend_event_node writes this field
    # post-interrupt, but that happens AFTER the first build_node re-entry in
    # the same superstep, so we must seed it in state_patch here.
    try:
        _is_chat_message = False
        # normalize_event returns event["type"], not event["event_type"]
        if isinstance(event, dict) and event.get("type") == "chat_message":
            _is_chat_message = True
        elif isinstance(msg, dict) and msg.get("method") == "chat_message":
            _is_chat_message = True
        elif isinstance(msg, dict) and _safe_get(msg, "params.metadata.mtype") == "send_chat":
            _is_chat_message = True

        if _is_chat_message:
            compact_event: Dict[str, Any] = {"event_type": "chat_message"}
            if isinstance(event, dict):
                for k in ("source", "tag", "node", "timestamp", "id", "sessionId",
                          "chatId", "senderId", "senderName", "receiverId",
                          "transport", "senderType"):
                    v = event.get(k) or (event.get("context", {}) or {}).get(k)
                    if v is not None:
                        compact_event[k] = v
                if isinstance(event.get("data"), dict):
                    ht = event["data"].get("human_text")
                    if isinstance(ht, str) and ht:
                        compact_event["human_text"] = ht
            if isinstance(msg, dict):
                meta_params = _safe_get(msg, "params.metadata.params") or _safe_get(msg, "params.metadata") or {}
                if isinstance(meta_params, dict):
                    for k in ("chatId", "senderId", "senderName", "receiverId",
                              "transport", "senderType"):
                        if k not in compact_event and k in meta_params:
                            compact_event[k] = meta_params[k]

            _write(
                state_patch,
                "prompt_refs.events",
                json.dumps(compact_event, ensure_ascii=False, default=str),
                on_conflict="overwrite",
            )
            logger.info(
                f"[build_general_resume_payload] Injected prompt_refs.events for chat_message "
                f"(sender={compact_event.get('senderId', '?')}, chat={compact_event.get('chatId', '?')})"
            )

            # Also inject state.input with the human_text from event.data for resume scenarios
            # This ensures the skill receives the latest user input, not stale input from previous turn
            # CRITICAL: Skip this for a2a_task_result events - their payload is structured JSON data,
            # not human text, and should NOT be used as state.input
            _event_type = compact_event.get("event_type") or (event.get("type") if isinstance(event, dict) else "")
            if _event_type != "a2a_task_result":
                _ht = compact_event.get("human_text") or (event.get("data") or {}).get("human_text")
                if _ht and isinstance(_ht, str) and _ht.strip():
                    _write(state_patch, "input", _ht.strip(), on_conflict="overwrite")
                    logger.info(f"[build_general_resume_payload] Set state.input from human_text: '{_ht[:50]}...'")
            else:
                logger.info(f"[build_general_resume_payload] Skipping state.input injection for a2a_task_result event")
    except Exception as _env_err:
        logger.debug(f"[build_general_resume_payload] prompt_refs.events injection skipped: {_env_err}")

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
        
        # --- Handle A2A task result events ---
        # When an agent receives a response from another agent via A2A,
        # this event type should trigger resume of pend_event nodes listening for a2a_task_result
        try:
            is_a2a_result = False
            
            # Check if this is an A2A task result event
            if isinstance(msg, dict):
                # Direct format: {"type": "a2a_task_result", "result": {...}}
                if msg.get("type") == "a2a_task_result":
                    is_a2a_result = True
                # Also check for nested formats
                elif msg.get("event_type") == "a2a_task_result":
                    is_a2a_result = True
                # Check if this is an A2A message response (from another agent)
                elif _safe_get(msg, "params.metadata.mtype") == "a2a_response":
                    is_a2a_result = True
                # CRITICAL: Check notification.type for a2a_task_result
                # This is set by send_response_back when child agent responds to parent
                elif _safe_get(msg, "params.metadata.notification.type") == "a2a_task_result":
                    is_a2a_result = True
                    logger.info("[build_general_resume_payload] Detected a2a_task_result via notification.type")
            
            # Also check the event type from normalize_event
            if isinstance(event, dict):
                if event.get("type") == "a2a_task_result" or event.get("type") == "a2a_response":
                    is_a2a_result = True
                # Also check context.notification.type
                elif _safe_get(event, "context.notification.type") == "a2a_task_result":
                    is_a2a_result = True
                    logger.info("[build_general_resume_payload] Detected a2a_task_result via event.context.notification.type")
            
            if is_a2a_result:
                logger.info("[build_general_resume_payload] Processing A2A task result event")
                
                # Extract result from various possible locations
                a2a_result = None
                
                # From direct result field
                if isinstance(msg, dict):
                    a2a_result = msg.get("result")
                    if not a2a_result:
                        # From nested data.result
                        a2a_result = msg.get("data", {}).get("result")
                    if not a2a_result:
                        # From task response in params
                        a2a_result = _safe_get(msg, "params.message.parts.0.text")
                
                # CRITICAL: Also check notification.result - this is where send_response_back stores the result
                # when it sets notification = {"type": "a2a_task_result", "result": state.get("result", {})}
                if not a2a_result:
                    notification_result = (
                        _safe_get(msg, "params.metadata.notification.result")
                        or _safe_get(msg, "params.notification.result")
                        or _safe_get(event, "context.notification.result")
                        or _safe_get(event, "data.notification.result")
                        # Also check in attributes.params.content.notification.result
                        or _safe_get(msg, "attributes.params.content.notification.result")
                    )
                    if notification_result:
                        a2a_result = notification_result
                        logger.info("[build_general_resume_payload] Extracted result from notification.result")
                
                if a2a_result:
                    # Store in state_patch for downstream nodes
                    # Get the triggering node name from event context (set by pend_event_node via i_tag)
                    # This allows dynamic mapping without hardcoding node names
                    _trigger_node = (
                        event.get("context", {}).get("i_tag")
                        or event.get("tag")
                        or event.get("context", {}).get("cloud_task_id")
                    )
                    
                    # Infer dispatch node name from pend node name using common convention
                    # Convention: pend_{X}_result or pend_{X} -> {X}
                    # e.g., pend_research_result -> research
                    _dispatch_node = None
                    if _trigger_node and _trigger_node.startswith("pend_"):
                        _dispatch_node = _trigger_node[5:]
                        if _dispatch_node.endswith("_result"):
                            _dispatch_node = _dispatch_node[:-7]
                    
                    # Store to state.result (accessible by all downstream nodes via {{result}})
                    _write(state_patch, "result", a2a_result, on_conflict="merge_deep")
                    _write(state_patch, "tool_result.a2a_task_result", a2a_result, on_conflict="overwrite")
                    
                    # Also store to inferred dispatch node location
                    if _dispatch_node:
                        _write(state_patch, f"tool_result.{_dispatch_node}", a2a_result, on_conflict="overwrite")
                        logger.info(f"[build_general_resume_payload] A2A result stored to tool_result.{_dispatch_node}")
                    
                    # CRITICAL: Also store using the original trigger node name (the full name without 'pend_' prefix)
                    # This ensures templates using {{tool_result.pend_research_result.xxx}} work correctly.
                    # Some workflows reference the pend node name directly in templates.
                    if _trigger_node and _trigger_node.startswith("pend_"):
                        # e.g., "pend_research_result" -> "pend_research_result" (full name for tool_result key)
                        _pend_storage_name = _trigger_node
                        _write(state_patch, f"tool_result.{_pend_storage_name}", a2a_result, on_conflict="overwrite")
                        logger.info(f"[build_general_resume_payload] A2A result stored to tool_result.{_pend_storage_name}")
                    
                    logger.info(f"[build_general_resume_payload] A2A result stored to state.result")
                    
                    # CRITICAL: Also propagate notification to state.metadata.notification
                    # This is required for pend_event_node to read the notification
                    # pend_event_node reads from state.get("metadata").get("notification", None)
                    _notification = (
                        _safe_get(msg, "params.metadata.notification")
                        or _safe_get(msg, "params.notification")
                        or event.get("context", {}).get("notification")
                    )
                    if _notification:
                        _write(state_patch, "metadata.notification", _notification, on_conflict="overwrite")
                        logger.info(f"[build_general_resume_payload] A2A notification propagated to state.metadata.notification")
        except Exception as _a2a_err:
            logger.debug(f"[build_general_resume_payload] A2A result handling skipped: {_a2a_err}")
        
        # Capture chat metadata for send_chat events
        message_mtype = (
            _safe_get(msg, "params.message.metadata.mtype")
            or _safe_get(msg, "params.metadata.mtype")
            or event.get("data", {}).get("metadata", {}).get("mtype")
        ) if isinstance(event, dict) else None
        canonical_event_type = event.get("type", "") if isinstance(event, dict) else ""
        
        # CRITICAL: Check if message contains a2a_task_result notification
        # This takes priority over send_chat mtype - when child agent sends response
        # with notification.type="a2a_task_result", we should use that as event type
        # to ensure parent's pend_event_node correctly resumes
        if not canonical_event_type or canonical_event_type == "other":
            # Check notification.type in multiple locations
            notification_type = (
                _safe_get(msg, "params.metadata.notification.type")
                or _safe_get(msg, "params.notification.type")
                or event.get("data", {}).get("notification", {}).get("type")
                or _safe_get(event, "context.notification.type")
            )
            if notification_type == "a2a_task_result":
                canonical_event_type = "a2a_task_result"
                logger.info(f"[build_general_resume_payload] Detected a2a_task_result notification, using event_type=a2a_task_result")
            else:
                inferred_from_mtype = _infer_event_type(message_mtype)
                if inferred_from_mtype and inferred_from_mtype != "other":
                    canonical_event_type = inferred_from_mtype
                    if isinstance(event, dict):
                        event["type"] = canonical_event_type
        resume_payload["event_type"] = canonical_event_type or message_mtype or ""
        # Include the full normalized event envelope so downstream nodes can inspect it
        resume_payload["_event_envelope"] = event
        if isinstance(message_mtype, str) and "send_chat" in message_mtype.lower():
            # Use event.context (normalized by normalize_event) which handles
            # msg["attributes"]["params"] format from chat_tools._build_chat_message
            evt_ctx = event.get("context", {}) if isinstance(event, dict) else {}
            chat_attrs = {"mtype": message_mtype, "event_type": canonical_event_type or "chat_message"}
            for key in ("chatId", "senderId", "senderName", "senderType", "transport", "content", "receiverId", "attachments"):
                value = evt_ctx.get(key)
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

        # Propagate channel metadata into state so outbound bridge can route replies
        _ch_params = _safe_get(msg, "params") if isinstance(msg, dict) else None
        if isinstance(_ch_params, dict) and _ch_params.get("channel_id"):
            for _ck in ("channel_id", "channel_chat_id", "channel_sender_id",
                        "channel_message_id", "channel_thread_id", "channel_account_id"):
                _cv = _ch_params.get(_ck)
                if _cv:
                    _write(state_patch, f"attributes.{_ck}", _cv, on_conflict="overwrite")

        # Preserve browser_event payloads so resumed nodes can act without re-scraping.
        if isinstance(msg, dict) and event.get("type") == "browser_event":
            normalized_browser_event = _parse_browser_event_envelope(msg)
            browser_event_payload = {
                "type": "browser_event",
                "sub_type": msg.get("sub_type") or normalized_browser_event.get("label") or _safe_get(msg, "context.sub_type") or "",
                "sub_id": msg.get("sub_id") or normalized_browser_event.get("event_id") or _safe_get(msg, "context.sub_id") or "",
                "source": msg.get("source") or event.get("source") or "",
            }
            parsed_body = _parse_browser_event_body(msg)
            if parsed_body:
                browser_event_payload["body"] = parsed_body
            elif isinstance(msg.get("params"), dict):
                browser_event_payload["body"] = msg.get("params")
            if normalized_browser_event:
                browser_event_payload["normalized_event"] = normalized_browser_event

            customers = browser_event_payload.get("body", {}).get("customers")
            if not isinstance(customers, list):
                customers = []
            session_ids = []
            for customer in customers:
                if not isinstance(customer, dict):
                    continue
                sid = customer.get("session_id") or customer.get("sessionId") or customer.get("session")
                if isinstance(sid, str) and sid and sid not in session_ids:
                    session_ids.append(sid)

            body_items = browser_event_payload.get("body", {}).get("items")
            if isinstance(body_items, list):
                for item in body_items:
                    if not isinstance(item, dict):
                        continue
                    sid = item.get("session_id") or item.get("sessionId") or item.get("session")
                    if isinstance(sid, str) and sid and sid not in session_ids:
                        session_ids.append(sid)

            body_session_id = browser_event_payload.get("body", {}).get("session_id")
            if isinstance(body_session_id, str) and body_session_id and body_session_id not in session_ids:
                session_ids.append(body_session_id)

            if session_ids:
                browser_event_payload["session_ids"] = session_ids
                browser_event_payload["count"] = len(session_ids)
                _write(state_patch, "attributes.pending_customer_sessions", session_ids, on_conflict="overwrite")
                _write(state_patch, "attributes.pending_customers", customers, on_conflict="overwrite")

            _write(state_patch, "attributes.browser_event", browser_event_payload, on_conflict="overwrite")
            _write(state_patch, "attributes.browser_event_sub_type", browser_event_payload.get("sub_type", ""), on_conflict="overwrite")
            _write(state_patch, "attributes.browser_event_sub_id", browser_event_payload.get("sub_id", ""), on_conflict="overwrite")
            _write(state_patch, "attributes.debug.last_browser_event", browser_event_payload, on_conflict="overwrite")
            resume_payload["browser_event"] = browser_event_payload

        event_data = event.get("data", {}) if isinstance(event, dict) else {}
        human_text = event_data.get("human_text")
        persistent_human_text = human_text
        if isinstance(human_text, str) and "data:image/" in human_text:
            try:
                from utils.data_uri_sanitizer import sanitize_json_text, data_uri_stats
                _stats = data_uri_stats(human_text)
                persistent_human_text = sanitize_json_text(human_text)
                logger.info(
                    "[data-uri-mitigation] resume_human_text_sanitized "
                    "chars=%d->%d data_uri_count=%d data_uri_bytes=%d",
                    len(human_text),
                    len(persistent_human_text),
                    _stats.get("count", 0),
                    _stats.get("bytes", 0),
                )
            except Exception:
                persistent_human_text = human_text
        if human_text and not resume_payload.get("human_text"):
            resume_payload["human_text"] = persistent_human_text
        if human_text:
            # The resumed graph can execute one browser_automation step before
            # pend_event_node appends/merges the resume payload.  Under bursty
            # queues that left state.input/messages[4] pointing at the previous
            # customer's response, so HOT-PATH-B typed or deduped the wrong turn.
            # Seed every runtime input surface here before the checkpoint is
            # resumed so the first re-entry sees the current chat message.
            _write(state_patch, "input", persistent_human_text, on_conflict="overwrite")
            _write(state_patch, "current_invocation_input", persistent_human_text, on_conflict="overwrite")
            _write(
                state_patch,
                "current_invocation_input_source",
                "resume.event.data.human_text",
                on_conflict="overwrite",
            )
            _write(
                state_patch,
                "attributes.current_invocation_input",
                persistent_human_text,
                on_conflict="overwrite",
            )
            _write(
                state_patch,
                "attributes.current_invocation_input_source",
                "resume.event.data.human_text",
                on_conflict="overwrite",
            )

            try:
                msg_list = _safe_get(state_patch, "messages")
                if not isinstance(msg_list, list):
                    base_msgs = current_state.get("messages")
                    msg_list = list(base_msgs) if isinstance(base_msgs, list) else []
                while len(msg_list) <= 4:
                    msg_list.append("")
                if evt_chat_id and len(msg_list) > 1:
                    msg_list[1] = evt_chat_id
                msg_list[4] = persistent_human_text
                _write(state_patch, "messages", msg_list, on_conflict="overwrite")
            except Exception:
                pass
        if human_text and not _safe_get(state_patch, "attributes.human.last_message"):
            _write(state_patch, "attributes.human.last_message", persistent_human_text, on_conflict="overwrite")

        # Append the user's chat message to history so the LLM sees it in conversation context
        if human_text:
            try:
                from langchain_core.messages import HumanMessage
                existing_history = current_state.get("history") or []
                # Only add if not already the last message in history (avoid duplicates)
                already_present = (
                    existing_history
                    and hasattr(existing_history[-1], "content")
                    and existing_history[-1].content == persistent_human_text
                )
                if not already_present:
                    new_history = list(existing_history) + [HumanMessage(content=persistent_human_text)]
                    _write(state_patch, "history", new_history, on_conflict="overwrite")
                    logger.info(f"[resume] Added user message to history: len={len(persistent_human_text)}")
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
