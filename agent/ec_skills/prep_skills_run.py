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
    _safe_get,
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


def _extract_browser_event_patch(msg: Any) -> Dict[str, Any]:
    """Build a state patch for browser_event messages in fresh message-triggered runs."""
    try:
        if not isinstance(msg, dict) or msg.get("type") != "browser_event":
            return {}

        normalized_event = msg.get("event") if isinstance(msg.get("event"), dict) else {}

        params = msg.get("params")
        if not isinstance(params, dict):
            params = {}

        body = {}
        if isinstance(normalized_event.get("payload"), dict):
            body = dict(normalized_event.get("payload") or {})
        else:
            for key in ("body", "responseBody", "payload", "data"):
                raw = params.get(key)
                if isinstance(raw, dict):
                    body = dict(raw)
                    break
                if isinstance(raw, str):
                    s = raw.strip()
                    if not s:
                        continue
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, dict):
                            body = parsed
                            break
                    except Exception:
                        continue

        payload = {
            "type": "browser_event",
            "sub_type": str(msg.get("sub_type") or normalized_event.get("label") or ""),
            "sub_id": str(msg.get("sub_id") or normalized_event.get("event_id") or ""),
            "source": str(msg.get("source") or ""),
            "body": body if isinstance(body, dict) else {},
        }
        if normalized_event:
            payload["normalized_event"] = normalized_event

        customers = payload["body"].get("customers")
        if not isinstance(customers, list):
            customers = []

        session_ids = []
        for customer in customers:
            if not isinstance(customer, dict):
                continue
            sid = (
                customer.get("session_id")
                or customer.get("sessionId")
                or customer.get("session")
            )
            if isinstance(sid, str) and sid and sid not in session_ids:
                session_ids.append(sid)

        # Also support polling new_chat_msg payload shape with a single session_id.
        body_session_id = payload["body"].get("session_id") if isinstance(payload["body"], dict) else None
        if isinstance(body_session_id, str) and body_session_id and body_session_id not in session_ids:
            session_ids.append(body_session_id)

        body_items = payload["body"].get("items") if isinstance(payload["body"], dict) else None
        if isinstance(body_items, list):
            for item in body_items:
                if not isinstance(item, dict):
                    continue
                sid = item.get("session_id") or item.get("sessionId") or item.get("session")
                if isinstance(sid, str) and sid and sid not in session_ids:
                    session_ids.append(sid)

        patch = {
            "attributes": {
                "browser_event": payload,
                "browser_event_sub_type": payload["sub_type"],
                "browser_event_sub_id": payload["sub_id"],
                "debug": {
                    "last_browser_event": payload,
                },
            }
        }
        if session_ids:
            patch["attributes"]["pending_customer_sessions"] = session_ids
        if customers:
            patch["attributes"]["pending_customers"] = customers
        return patch
    except Exception:
        return {}


def _extract_chat_message_input_patch(msg: Any, event: Dict[str, Any], node_state: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback injection for chat-message style resumes when mapping leaves state.input empty.

    Also injects prompt_refs.events with the chat_message event envelope so that
    downstream browser_automation nodes know the triggering event type.  Without
    this, an initial-run triggered by a chat_message would fall back to the last
    stored browser_event and run Phase 1 (dispatch) instead of Phase 2 (reply).
    """
    try:
        existing_input = ""
        if isinstance(node_state, dict):
            raw_existing = node_state.get("input")
            if isinstance(raw_existing, str):
                existing_input = raw_existing.strip()

        # --- Always inject prompt_refs.events for chat_message events ---
        # Even if state.input is already populated, browser_automation needs the
        # event envelope in prompt_refs.events to choose Phase 2 over Phase 1.
        _event_envelope_patch: Dict[str, Any] = {}
        _is_chat_message = False
        # normalize_event returns event["type"], not event["event_type"]
        if isinstance(event, dict) and event.get("type") == "chat_message":
            _is_chat_message = True
        elif isinstance(msg, dict) and msg.get("method") == "chat_message":
            _is_chat_message = True
        elif isinstance(msg, dict) and _safe_get(msg, "params.metadata.mtype") == "send_chat":
            _is_chat_message = True

        if _is_chat_message:
            # Build a compact event envelope matching the shape pend_event_node produces
            compact_event: Dict[str, Any] = {"event_type": "chat_message"}
            if isinstance(event, dict):
                for k in ("source", "tag", "node", "timestamp", "id", "sessionId",
                          "chatId", "senderId", "senderName", "receiverId",
                          "transport", "senderType"):
                    v = event.get(k) or (event.get("context", {}) or {}).get(k)
                    if v is not None:
                        compact_event[k] = v
                # Include human_text from event.data
                if isinstance(event.get("data"), dict):
                    ht = event["data"].get("human_text")
                    if isinstance(ht, str) and ht:
                        compact_event["human_text"] = ht
            # Also extract from msg metadata as fallback
            # Note: event.context is already populated by normalize_event which handles
            # msg["attributes"]["params"] format from chat_tools._build_chat_message
            if isinstance(msg, dict):
                meta_params = _safe_get(msg, "params.metadata.params") or _safe_get(msg, "params.metadata") or {}
                if isinstance(meta_params, dict):
                    for k in ("chatId", "senderId", "senderName", "receiverId",
                              "transport", "senderType"):
                        if k not in compact_event and k in meta_params:
                            compact_event[k] = meta_params[k]

            _event_envelope_patch = {
                "prompt_refs": {
                    "events": json.dumps(compact_event, ensure_ascii=False, default=str),
                },
            }
            logger.info(
                f"[prep_skills_run] Injecting prompt_refs.events for chat_message "
                f"(sender={compact_event.get('senderId', '?')}, chat={compact_event.get('chatId', '?')})"
            )

        # --- For chat_message events, check if event.data already has human_text ---
        # This handles resume events where normalize_event extracted human_text into event.data
        _event_human_text = ""
        if _is_chat_message and isinstance(event, dict):
            ht = (event.get("data") or {}).get("human_text")
            if isinstance(ht, str) and ht.strip():
                _event_human_text = ht.strip()

        candidates = []

        # Prioritize event.data.human_text for resume events (most reliable for user input)
        if _event_human_text:
            candidates.append(("event.data.human_text", _event_human_text))

        if isinstance(msg, dict):
            text = _safe_get(msg, "params.message.parts.0.text")
            if isinstance(text, str) and text.strip():
                candidates.append(("msg.params.message.parts[0].text", text.strip()))

            text = _safe_get(msg, "params.metadata.params.content.text")
            if isinstance(text, str) and text.strip():
                candidates.append(("msg.params.metadata.params.content.text", text.strip()))

            text = _safe_get(msg, "params.content")
            if isinstance(text, str) and text.strip():
                candidates.append(("msg.params.content", text.strip()))

            if not candidates:
                raw_content = _safe_get(msg, "params.metadata.params.content")
                if isinstance(raw_content, dict):
                    raw_text = raw_content.get("text")
                    if isinstance(raw_text, str) and raw_text.strip():
                        candidates.append(("msg.params.metadata.params.content[text]", raw_text.strip()))

        # Check if there's new input that should override existing state.input
        _has_new_input = bool(_event_human_text) or candidates
        if existing_input and not _has_new_input:
            # No new input found, keep existing and just return event envelope
            return _event_envelope_patch

        for source, payload in candidates:
            # Only inject plausible assignment/customer-chat payload text.
            if payload:
                logger.info(f"[prep_skills_run] Injecting fallback state.input from {source} (len={len(payload)})")
                patch = {
                    "input": payload,
                    "attributes": {
                        "current_invocation_input": payload,
                        "current_invocation_input_source": source,
                    },
                }
                # Merge event envelope patch if present
                if _event_envelope_patch:
                    patch = _deep_merge(patch, _event_envelope_patch)
                return patch

        logger.debug("[prep_skills_run] No fallback chat-message input payload found")
        return _event_envelope_patch
    except Exception as e:
        logger.debug("[prep_skills_run] chat-message input fallback failed: " + str(e))
        return {}


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

        # Extract inbound A2A sender information for reply routing
        # This allows send_response_back to send results back to the calling agent
        inbound_sender_id = ""
        inbound_sender_name = ""
        inbound_sender_type = ""
        inbound_transport = ""
        inbound_chat_id = ""
        try:
            if msg and hasattr(msg, 'params') and msg.params and hasattr(msg.params, 'metadata') and msg.params.metadata:
                # TaskSendParams format
                metadata = msg.params.metadata
                inbound_sender_id = str(metadata.get("senderId") or "").strip()
                inbound_sender_name = str(metadata.get("senderName") or "").strip()
                inbound_sender_type = str(metadata.get("senderType") or "").strip()
                inbound_transport = str(metadata.get("transport") or "a2a").strip()
                inbound_chat_id = str(metadata.get("chatId") or "").strip()
            elif isinstance(msg, dict):
                # Dict format - check both params.metadata.senderId AND params.senderId
                # _build_chat_message in chat_tools.py puts senderId directly in params, not in metadata
                params = msg.get("params", {})
                metadata = params.get("metadata", {}) if isinstance(params, dict) else {}
                if isinstance(params, dict) and "metadata" in params:
                    metadata = params["metadata"]
                # First try metadata.senderId (standard A2A format)
                inbound_sender_id = str(metadata.get("senderId") or "").strip()
                inbound_sender_name = str(metadata.get("senderName") or "").strip()
                inbound_sender_type = str(metadata.get("senderType") or "").strip()
                inbound_transport = str(metadata.get("transport") or "a2a").strip()
                inbound_chat_id = str(metadata.get("chatId") or params.get("chatId") or "").strip()
                
                # If not found in metadata, check params.senderId directly
                # This is where _build_chat_message puts the senderId
                if not inbound_sender_id and isinstance(params, dict):
                    inbound_sender_id = str(params.get("senderId") or "").strip()
                    inbound_sender_name = str(params.get("senderName") or "").strip()
                    inbound_sender_type = str(params.get("senderType") or "agent").strip()
                    inbound_transport = str(params.get("transport") or "a2a").strip()
                    if not inbound_chat_id:
                        inbound_chat_id = str(params.get("chatId") or "").strip()
        except Exception:
            pass

        # Build chat_attributes dict for send_response_back routing
        chat_attributes = {}
        if inbound_sender_id:
            chat_attributes = {
                "senderId": inbound_sender_id,
                "senderName": inbound_sender_name,
                "senderType": inbound_sender_type or ("agent" if inbound_transport == "a2a" else "human"),
                "transport": inbound_transport or "a2a",
                "chatId": inbound_chat_id or chat_id,
            }
            logger.debug(f"{_tag} Extracted inbound sender: {inbound_sender_id} ({inbound_sender_name}), transport={inbound_transport}")

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
                "inbound_sender_id": inbound_sender_id,  # For A2A reply routing
                "inbound_sender_name": inbound_sender_name,
                "inbound_sender_type": inbound_sender_type,
                "inbound_transport": inbound_transport,
                "chat_attributes": chat_attributes,  # For send_response_back routing
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
            # Reset per-run runtime fields after merge. _deep_merge lets current_state
            # win for shared keys, which poisons fresh event-triggered runs on shared
            # task instances: a previous turn's terminal result.llm_result.all_done=True
            # would carry over and cause the loop's while-condition to exit before any
            # node executes for the new customer (silent drop). Persistent fields like
            # attributes / history / metadata still carry over from the merge above.
            base["result"] = {"llm_result": {"all_done": False, "work_done": False}}
            base["tool_name"] = ""
            base["tool_input"] = {}
            base["tool_result"] = {}
            base["http_response"] = {}
            base["cli_input"] = {}
            base["cli_results"] = {}
            base["error"] = ""
            base["retries"] = 0
            base["condition"] = False
            base["condition_vars"] = {}
            base["loop_end_vars"] = {}
            base["case"] = ""
            base["n_steps"] = 0
            base["breakpoint"] = False

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


def apply_task_vars(task, state) -> None:
    """Merge the task's carried variables into a freshly prepared run state.

    SHARED_SKILL_MULTI_TASK_PLAN Phase 2: a task referencing a shared skill
    carries its per-task variable data in ``task.metadata["task_vars"]``
    (persisted in the DB task's settings/metadata JSON). At run start those
    variables are seeded into ``state["prompt_refs"]`` — the FIRST stop of
    the prompt-variable resolution cascade (see
    ``prompt_variable_providers.resolve_prompt_variables``) — so ``{{var}}``
    slots in the shared skill's prompts resolve per task.

    Semantics:
    - Applied for EVERY trigger type (schedule/auto/message/dev), unlike the
      message-only full-state merge.
    - Overwrites same-named ``prompt_refs`` keys at run START (task intent
      wins over stale values carried from a previous run); upstream nodes
      may still overwrite during the run (their output is more current).
    - The raw dict is also kept at ``state["attributes"]["task_vars"]`` for
      diagnostics and non-prompt consumers.
    - Phase 3: a ``task.metadata["browser_identity"]`` dict (keys:
      ``browser_profile``/``profile``, ``cdp_port``, ``browser_slot_id``/
      ``slot``, ``user_data_dir``, ``headless``) is seeded into state
      attributes under the keys the browser-node runtime already honors
      (``build_helpers.resolve_state_browser_identity``), so tasks sharing
      one skill can each run their own browser identity.
    - No-op when the task carries neither; never raises.
    """
    _BROWSER_IDENTITY_KEYS = {
        "browser_profile": "browser_profile",
        "profile": "browser_profile",
        "cdp_port": "cdp_port",
        "browser_slot_id": "browser_slot_id",
        "slot": "browser_slot_id",
        "user_data_dir": "user_data_dir",
        "headless": "headless",
    }
    try:
        if not isinstance(state, dict):
            return
        metadata = getattr(task, "metadata", None)
        if not isinstance(metadata, dict):
            return
        task_vars = metadata.get("task_vars")
        browser_identity = metadata.get("browser_identity")
        has_vars = isinstance(task_vars, dict) and task_vars
        has_identity = isinstance(browser_identity, dict) and browser_identity
        if not has_vars and not has_identity:
            return

        attrs = state.get("attributes")
        if not isinstance(attrs, dict):
            attrs = {}
            state["attributes"] = attrs

        if has_vars:
            prompt_refs = state.get("prompt_refs")
            if not isinstance(prompt_refs, dict):
                prompt_refs = {}
                state["prompt_refs"] = prompt_refs
            prompt_refs.update(task_vars)
            attrs["task_vars"] = dict(task_vars)
            # INFO: "my task vars didn't reach the prompt" is the first thing
            # to check when a shared-skill run misbehaves — names only, values
            # may be sensitive.
            logger.info(
                f"[apply_task_vars] task '{getattr(task, 'name', '?')}' seeded "
                f"{len(task_vars)} var(s) into prompt_refs: {sorted(task_vars.keys())}"
            )

        if has_identity:
            seeded = []
            for raw_key, state_key in _BROWSER_IDENTITY_KEYS.items():
                if raw_key in browser_identity and browser_identity[raw_key] not in (None, ""):
                    attrs[state_key] = browser_identity[raw_key]
                    seeded.append(state_key)
            if seeded:
                logger.info(
                    f"[apply_task_vars] task '{getattr(task, 'name', '?')}' seeded "
                    f"browser identity keys: {seeded}"
                )
    except Exception as e:
        logger.warning(f"[apply_task_vars] failed (non-fatal): {e}")


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
            node_transfers = {}
            if isinstance(rules, dict):
                # Preferred: top-level node_transfers (data_mapping.json current format)
                top_level = rules.get("node_transfers", {})
                if isinstance(top_level, dict) and top_level:
                    node_transfers = top_level
                else:
                    # Backward-compatible fallback: run_mode-scoped node_transfers
                    run_mode = getattr(skill, "run_mode", None) or "released"
                    mode_rules = rules.get(run_mode, {})
                    if isinstance(mode_rules, dict):
                        mode_level = mode_rules.get("node_transfers", {})
                        if isinstance(mode_level, dict) and mode_level:
                            node_transfers = mode_level
            if not isinstance(node_state.get("attributes"), dict):
                node_state["attributes"] = {}
            node_state["attributes"]["node_transfer_rules"] = node_transfers if isinstance(node_transfers, dict) else {}
            logger.debug("[prep_skills_run] injected node_transfer_rules keys: ", list((node_transfers or {}).keys()))
        except Exception as _e:
            logger.debug("[prep_skills_run] skipping node_transfer_rules inject due to error: " + str(_e))

        # 2) Resolve START-node mapping
        mapping = _resolve_start_mapping(skill)
        logger.info(f"[prep_skills_run] skill={getattr(skill, 'name', '?')}, run_mode={getattr(skill, 'run_mode', '?')}, resolved_mapping_keys={list(mapping.keys()) if isinstance(mapping, dict) else 'N/A'}")

        # 3) Normalize incoming message to event envelope (type inferred)
        logger.debug("[prep_skills_run] incoming message: ", msg)
        event = normalize_event("", msg)
        logger.debug("[prep_skills_run] normalized event: ", event)

        # 4) Apply mapping to produce state patch (ignore resume output for init)
        _resume, state_patch = build_resume_from_mapping(event=event, state=node_state, node_output=None, mapping=mapping)
        logger.debug("[prep_skills_run] resume: ", _resume)
        logger.debug("[prep_skills_run] state_patch: ", state_patch)
        browser_event_patch = _extract_browser_event_patch(msg)
        if browser_event_patch:
            state_patch = _deep_merge(state_patch or {}, browser_event_patch)
            logger.debug("[prep_skills_run] browser_event_patch: ", browser_event_patch)
        chat_input_patch = _extract_chat_message_input_patch(msg, event, node_state)
        if chat_input_patch:
            state_patch = _deep_merge(state_patch or {}, chat_input_patch)
            logger.debug("[prep_skills_run] chat_input_patch: ", chat_input_patch)
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
