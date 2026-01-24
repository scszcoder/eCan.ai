import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import boto3

from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, publish_skill_editor_stream_event
from agent.skill_editor.skill_editor_agent import SkillEditorAgent, _safe_user_dir_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class _Env:
    s3_bucket: str
    s3_key_root: str
    appsync_api_url: str
    appsync_api_key: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _load_env() -> _Env:
    return _Env(
        s3_bucket=_require_env("S3_BUCKET"),
        s3_key_root=(os.environ.get("S3_KEY_ROOT") or "").strip(),
        appsync_api_url=_require_env("APPSYNC_API_URL"),
        appsync_api_key=_require_env("APPSYNC_API_KEY"),
    )


def _norm_prefix(prefix: str) -> str:
    p = (prefix or "").strip().strip("/")
    return p


def _s3_key(prefix: str, *parts: str) -> str:
    clean = [p.strip("/") for p in [prefix, *parts] if p and str(p).strip("/")]
    return "/".join(clean)


def _s3_client():
    return boto3.client("s3")


def _s3_get_json(*, bucket: str, key: str) -> Optional[Dict[str, Any]]:
    try:
        resp = _s3_client().get_object(Bucket=bucket, Key=key)
        raw = resp["Body"].read().decode("utf-8")
        return json.loads(raw)
    except _s3_client().exceptions.NoSuchKey:
        return None
    except Exception:
        return None


def _s3_put_json(*, bucket: str, key: str, data: Dict[str, Any]) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    _s3_client().put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def _s3_list_keys(*, bucket: str, prefix: str) -> List[str]:
    client = _s3_client()
    keys: List[str] = []
    continuation: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            k = obj.get("Key")
            if k and not k.endswith("/"):
                keys.append(k)
        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
            continue
        break
    return keys


def _owner_from_event(event: Dict[str, Any]) -> str:
    args = (event.get("arguments") or {})
    if isinstance(args.get("input"), dict):
        user_id = args["input"].get("userId")
        if isinstance(user_id, str) and user_id.strip():
            return user_id.strip()

    ident = event.get("identity") or {}
    for key in ("username", "sub", "claims"):
        v = ident.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if key == "claims" and isinstance(v, dict):
            c = v.get("email") or v.get("cognito:username")
            if isinstance(c, str) and c.strip():
                return c.strip()

    return "unknown@local"


def _session_meta_key(env: _Env, owner: str, session_id: str) -> str:
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir, "skill_editor_chat", "sessions", f"{session_id}.json")


def _session_history_key(env: _Env, owner: str, session_id: str) -> str:
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir, "skill_editor_chat", "histories", f"{session_id}.json")


def _load_session(env: _Env, owner: str, session_id: str) -> Optional[Dict[str, Any]]:
    return _s3_get_json(bucket=env.s3_bucket, key=_session_meta_key(env, owner, session_id))


def _save_session(env: _Env, owner: str, session: Dict[str, Any]) -> None:
    _s3_put_json(bucket=env.s3_bucket, key=_session_meta_key(env, owner, str(session.get("id"))), data=session)


def _load_history(env: _Env, owner: str, session_id: str) -> Dict[str, Any]:
    return _s3_get_json(bucket=env.s3_bucket, key=_session_history_key(env, owner, session_id)) or {
        "sessionId": session_id,
        "messages": [],
    }


def _save_history(env: _Env, owner: str, session_id: str, history: Dict[str, Any]) -> None:
    _s3_put_json(bucket=env.s3_bucket, key=_session_history_key(env, owner, session_id), data=history)


def _mk_appsync_cfg(env: _Env) -> AppSyncApiKeyConfig:
    return AppSyncApiKeyConfig(http_endpoint=env.appsync_api_url, api_key=env.appsync_api_key)


def _publish(env: _Env, *, owner: str, session_id: str, flowgram_id: Optional[str], event_type: str, payload: Any) -> None:
    cfg = _mk_appsync_cfg(env)

    import asyncio

    async def _do():
        await publish_skill_editor_stream_event(
            config=cfg,
            owner=owner,
            session_id=session_id,
            flowgram_id=flowgram_id,
            event_type=event_type,
            payload=payload,
        )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync

            run_async_in_sync(_do())
        else:
            loop.run_until_complete(_do())
    except RuntimeError:
        asyncio.run(_do())


def _to_session_gql(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": session["id"],
        "name": session.get("name") or "New Chat",
        "flowgramId": session.get("flowgramId"),
        "createdAt": session.get("createdAt") or _utc_now_iso(),
        "updatedAt": session.get("updatedAt") or session.get("createdAt") or _utc_now_iso(),
    }


def _to_message_gql(msg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": msg["id"],
        "role": msg.get("role") or "assistant",
        "content": msg.get("content") or "",
        "timestamp": msg.get("timestamp") or _utc_now_iso(),
        "attachments": msg.get("attachments"),
        "metadata": msg.get("metadata"),
    }


def _handle_create_session(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[createSkillEditorChatSession] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    owner = _owner_from_event(event)
    session_id = str(uuid4())
    now = _utc_now_iso()

    logger.info(f"[createSkillEditorChatSession] owner={owner}, session_id={session_id}, name={input_.get('name')}")

    session = {
        "id": session_id,
        "name": (input_.get("name") or "New Chat"),
        "flowgramId": input_.get("flowgramId"),
        "createdAt": now,
        "updatedAt": now,
        "pipelineState": "idle",
        "currentPlan": None,
        "currentRequest": None,
    }

    _save_session(env, owner, session)
    _save_history(env, owner, session_id, {"sessionId": session_id, "messages": []})

    logger.info(f"[createSkillEditorChatSession] Session created successfully: {session_id}")
    return _to_session_gql(session)


def _handle_get_sessions(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("[getSkillEditorChatSessions] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    owner = (args.get("userId") or _owner_from_event(event) or "").strip() or _owner_from_event(event)

    logger.info(f"[getSkillEditorChatSessions] owner={owner}")

    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    sessions_prefix = _s3_key(prefix, user_dir, "skill_editor_chat", "sessions")
    if sessions_prefix:
        sessions_prefix += "/"

    logger.info(f"[getSkillEditorChatSessions] Listing S3 prefix: {sessions_prefix}")
    keys = _s3_list_keys(bucket=env.s3_bucket, prefix=sessions_prefix)
    logger.info(f"[getSkillEditorChatSessions] Found {len(keys)} session keys")

    sessions: List[Dict[str, Any]] = []
    for k in keys:
        doc = _s3_get_json(bucket=env.s3_bucket, key=k)
        if isinstance(doc, dict) and doc.get("id"):
            sessions.append(doc)

    sessions.sort(key=lambda s: (s.get("updatedAt") or ""), reverse=True)
    logger.info(f"[getSkillEditorChatSessions] Returning {len(sessions)} sessions")
    return [_to_session_gql(s) for s in sessions]


def _handle_get_history(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("[getSkillEditorChatHistory] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    session_id = str(args.get("sessionId") or "")
    owner = _owner_from_event(event)

    logger.info(f"[getSkillEditorChatHistory] owner={owner}, session_id={session_id}")

    limit = args.get("limit")
    offset = int(args.get("offset") or 0)

    history = _load_history(env, owner, session_id)
    messages = history.get("messages") or []
    if not isinstance(messages, list):
        messages = []

    logger.info(f"[getSkillEditorChatHistory] Found {len(messages)} messages, offset={offset}, limit={limit}")

    sliced = messages[offset:]
    if isinstance(limit, int) and limit > 0:
        sliced = sliced[:limit]

    logger.info(f"[getSkillEditorChatHistory] Returning {len(sliced)} messages")
    return [_to_message_gql(m) for m in sliced if isinstance(m, dict) and m.get("id")]


def _handle_delete_session(event: Dict[str, Any]) -> bool:
    logger.info("[deleteSkillEditorChatSession] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    session_id = str(args.get("sessionId") or "")
    owner = _owner_from_event(event)

    logger.info(f"[deleteSkillEditorChatSession] owner={owner}, session_id={session_id}")

    if not session_id:
        logger.warning("[deleteSkillEditorChatSession] No session_id provided")
        return False

    client = _s3_client()
    deleted_any = False
    for key in (
        _session_meta_key(env, owner, session_id),
        _session_history_key(env, owner, session_id),
    ):
        try:
            client.delete_object(Bucket=env.s3_bucket, Key=key)
            logger.info(f"[deleteSkillEditorChatSession] Deleted S3 key: {key}")
            deleted_any = True
        except Exception as e:
            logger.warning(f"[deleteSkillEditorChatSession] Failed to delete {key}: {e}")
            continue

    logger.info(f"[deleteSkillEditorChatSession] Completed, deleted_any={deleted_any}")
    return deleted_any


def _handle_cancel_generation(event: Dict[str, Any]) -> bool:
    logger.info("[cancelSkillEditorChatGeneration] Starting handler")
    # Best-effort only in Lambda: we cannot cancel an in-flight invocation.
    # Return true so UI can stop waiting / reset local streaming state.
    _ = event
    logger.info("[cancelSkillEditorChatGeneration] Returning True (best-effort)")
    return True


def _handle_send_message(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[sendSkillEditorChatMessage] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    owner = _owner_from_event(event)
    session_id = str(input_.get("sessionId") or "")
    content = str(input_.get("content") or "")

    logger.info(f"[sendSkillEditorChatMessage] owner={owner}, session_id={session_id}, content_len={len(content)}")

    if not session_id:
        logger.error("[sendSkillEditorChatMessage] sessionId is required")
        raise ValueError("sessionId is required")
    if not content.strip():
        logger.error("[sendSkillEditorChatMessage] content is required")
        raise ValueError("content is required")

    # Initialize variables for finally block
    session: Optional[Dict[str, Any]] = None
    history: Optional[Dict[str, Any]] = None
    agent: Optional[SkillEditorAgent] = None
    assistant_message_id = str(uuid4())
    error_occurred: Optional[str] = None
    response = None

    try:
        logger.info(f"[sendSkillEditorChatMessage] Loading session from S3...")
        session = _load_session(env, owner, session_id)
        if not session:
            logger.info(f"[sendSkillEditorChatMessage] Session not found, auto-creating...")
            now = _utc_now_iso()
            session = {
                "id": session_id,
                "name": "New Chat",
                "flowgramId": input_.get("flowgramId"),
                "createdAt": now,
                "updatedAt": now,
                "pipelineState": "idle",
                "currentPlan": None,
                "currentRequest": None,
            }
        else:
            logger.info(f"[sendSkillEditorChatMessage] Session loaded, pipelineState={session.get('pipelineState')}")

        history = _load_history(env, owner, session_id)
        logger.info(f"[sendSkillEditorChatMessage] History loaded, {len(history.get('messages', []))} existing messages")

        now = _utc_now_iso()
        user_msg = {
            "id": str(uuid4()),
            "role": "user",
            "content": content,
            "timestamp": now,
            "attachments": input_.get("attachments"),
            "metadata": {
                "canvasContext": input_.get("canvasContext"),
                "clarificationResponses": input_.get("clarificationResponses"),
            },
        }
        history.setdefault("messages", [])
        if isinstance(history["messages"], list):
            history["messages"].append(user_msg)

        chunk_index = 0
        flowgram_id = input_.get("flowgramId")

        def on_event(evt: Dict[str, Any]) -> None:
            nonlocal chunk_index
            if not isinstance(evt, dict):
                return
            etype = evt.get("type")
            if etype not in {"progress", "chunk"}:
                return
            data = evt.get("data") or {}
            text = data.get("message") if etype == "progress" else data.get("content")
            if not isinstance(text, str) or not text.strip():
                return
            payload = {
                "messageId": assistant_message_id,
                "chunk": text,
                "index": chunk_index,
            }
            try:
                _publish(
                    env,
                    owner=owner,
                    session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.chat.stream_chunk",
                    payload=payload,
                )
            except Exception as pub_err:
                logger.warning(f"[sendSkillEditorChatMessage] Error publishing chunk: {pub_err}")
            chunk_index += 1

        logger.info("[sendSkillEditorChatMessage] Creating SkillEditorAgent...")
        agent = SkillEditorAgent(user_name=owner)

        try:
            pipeline_state = session.get("pipelineState")
            if isinstance(pipeline_state, str) and pipeline_state and pipeline_state != "idle":
                logger.info(f"[sendSkillEditorChatMessage] Restoring agent state: {pipeline_state}")
                agent.restore_state(
                    pipeline_state=pipeline_state,
                    current_plan=session.get("currentPlan") if isinstance(session.get("currentPlan"), dict) else session.get("currentPlan"),
                    current_request=session.get("currentRequest") if isinstance(session.get("currentRequest"), str) else None,
                )
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to restore agent state: {e}")

        canvas_context = input_.get("canvasContext")
        clarification = input_.get("clarificationResponses")

        logger.info(f"[sendSkillEditorChatMessage] Calling agent.process_message_sync, canvas_context_type={type(canvas_context).__name__}")
        response = agent.process_message_sync(
            message=content,
            canvas_context=canvas_context,
            session_id=session_id,
            clarification_responses=clarification,
            on_event=on_event,
        )
        logger.info(f"[sendSkillEditorChatMessage] Agent response received, intent={getattr(response, 'intent', None)}, message_len={len(response.message or '')}")

        logger.info("[sendSkillEditorChatMessage] Publishing stream_end event...")
        try:
            _publish(
                env,
                owner=owner,
                session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": assistant_message_id,
                    "fullContent": response.message or "",
                },
            )
        except Exception as pub_err:
            logger.warning(f"[sendSkillEditorChatMessage] Error publishing stream_end: {pub_err}")

        try:
            commands_count = len(response.commands or [])
            if commands_count > 0:
                logger.info(f"[sendSkillEditorChatMessage] Publishing {commands_count} commands...")
            for cmd in response.commands or []:
                cmd_dict = cmd.to_dict() if hasattr(cmd, "to_dict") else (cmd or {})
                _publish(
                    env,
                    owner=owner,
                    session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.event",
                    payload={
                        "type": cmd_dict.get("type"),
                        "payload": cmd_dict.get("payload"),
                    },
                )
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Error publishing commands: {e}")

        assistant_msg = {
            "id": assistant_message_id,
            "role": "assistant",
            "content": response.message or "",
            "timestamp": _utc_now_iso(),
            "attachments": None,
            "metadata": {
                "state": response.metadata.get("state") if isinstance(getattr(response, "metadata", None), dict) else None,
                "intent": response.intent.value if getattr(response, "intent", None) is not None else None,
                "hasClarification": bool(getattr(response, "clarification", None)),
                "hasPlan": bool(getattr(response, "plan", None)),
                "hasFlowgram": bool(getattr(response, "flowgram", None)),
            },
        }

        if isinstance(history.get("messages"), list):
            history["messages"].append(assistant_msg)

        session["updatedAt"] = _utc_now_iso()
        session["pipelineState"] = agent.pipeline_state.value
        session["currentPlan"] = agent.current_plan.model_dump() if agent.current_plan else None
        session["currentRequest"] = agent.current_request

    except Exception as e:
        import traceback
        error_occurred = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"[sendSkillEditorChatMessage] Exception occurred: {error_occurred}")
        logger.error(f"[sendSkillEditorChatMessage] Traceback: {error_traceback}")

        # Create error message for chat history
        error_msg = {
            "id": assistant_message_id,
            "role": "assistant",
            "content": f"An error occurred while processing your request: {error_occurred}",
            "timestamp": _utc_now_iso(),
            "attachments": None,
            "metadata": {
                "error": True,
                "errorMessage": error_occurred,
                "errorTraceback": error_traceback,
            },
        }

        if history and isinstance(history.get("messages"), list):
            history["messages"].append(error_msg)

        if session:
            session["updatedAt"] = _utc_now_iso()
            session["lastError"] = {
                "message": error_occurred,
                "traceback": error_traceback,
                "timestamp": _utc_now_iso(),
            }

        # Publish error event to frontend
        try:
            _publish(
                env,
                owner=owner,
                session_id=session_id,
                flowgram_id=input_.get("flowgramId"),
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": assistant_message_id,
                    "fullContent": f"Error: {error_occurred}",
                    "error": True,
                },
            )
        except Exception as pub_err:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to publish error event: {pub_err}")

    finally:
        # Always save history and session to S3, even on error
        logger.info(f"[sendSkillEditorChatMessage] Finally block: saving history and session to S3...")
        try:
            if history:
                _save_history(env, owner, session_id, history)
                logger.info(f"[sendSkillEditorChatMessage] History saved successfully")
        except Exception as save_err:
            logger.error(f"[sendSkillEditorChatMessage] Failed to save history: {save_err}")

        try:
            if session:
                _save_session(env, owner, session)
                logger.info(f"[sendSkillEditorChatMessage] Session saved successfully")
        except Exception as save_err:
            logger.error(f"[sendSkillEditorChatMessage] Failed to save session: {save_err}")

    # If error occurred, raise it after saving
    if error_occurred:
        logger.info(f"[sendSkillEditorChatMessage] Re-raising error after saving state")
        # Return error response instead of raising to allow frontend to handle gracefully
        return {
            "sessionId": session_id,
            "sessionName": session.get("name") if session else "New Chat",
            "state": "error",
            "intent": None,
            "message": {
                "id": assistant_message_id,
                "role": "assistant",
                "content": f"An error occurred: {error_occurred}",
                "timestamp": _utc_now_iso(),
                "attachments": None,
                "metadata": {"error": True, "errorMessage": error_occurred},
            },
            "clarification": None,
            "plan": None,
            "flowgram": None,
            "validation": None,
        }

    logger.info(f"[sendSkillEditorChatMessage] Completed successfully, returning response")
    return {
        "sessionId": session_id,
        "sessionName": session.get("name") or "New Chat",
        "state": agent.pipeline_state.value if agent else "idle",
        "intent": response.intent.value if response and getattr(response, "intent", None) is not None else None,
        "message": _to_message_gql(assistant_msg),
        "clarification": [q.model_dump() for q in (response.clarification or [])] if response and getattr(response, "clarification", None) else None,
        "plan": response.plan.model_dump() if response and getattr(response, "plan", None) else None,
        "flowgram": response.flowgram.model_dump() if response and getattr(response, "flowgram", None) else None,
        "validation": response.validation.model_dump() if response and getattr(response, "validation", None) else None,
    }


def _skill_context_key(env: _Env, owner: str, skill_name: str) -> str:
    """S3 key for skill context: <prefix>/<user>/skill_contexts/<skill_name>/context.json"""
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir, "skill_contexts", skill_name, "context.json")


def _handle_load_skill_editor_contexts(event: Dict[str, Any]) -> Dict[str, Any]:
    """Load skill editor contexts from S3 (per user, per skill)."""
    logger.info("[loadSkillEditorContexts] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}
    
    owner = _owner_from_event(event)
    skill_names = input_.get("skillNames") or []
    skill_ids = input_.get("skillIds") or []
    
    logger.info(f"[loadSkillEditorContexts] owner={owner}, skillNames={skill_names}, skillIds={skill_ids}")
    
    items: List[Dict[str, Any]] = []
    
    # If specific skill names requested, load those
    if skill_names:
        logger.info(f"[loadSkillEditorContexts] Loading {len(skill_names)} specific skills")
        for idx, skill_name in enumerate(skill_names):
            key = _skill_context_key(env, owner, skill_name)
            logger.info(f"[loadSkillEditorContexts] Fetching S3 key: {key}")
            context_data = _s3_get_json(bucket=env.s3_bucket, key=key)
            if context_data is not None:
                logger.info(f"[loadSkillEditorContexts] Found context for skill: {skill_name}")
                # Get object metadata for updatedAt
                try:
                    resp = _s3_client().head_object(Bucket=env.s3_bucket, Key=key)
                    last_modified = resp.get("LastModified")
                    updated_at = last_modified.isoformat() if last_modified else _utc_now_iso()
                except Exception as e:
                    logger.warning(f"[loadSkillEditorContexts] Failed to get LastModified for {key}: {e}")
                    updated_at = _utc_now_iso()
                
                items.append({
                    "skillId": skill_ids[idx] if idx < len(skill_ids) else None,
                    "skillName": skill_name,
                    "context": json.dumps(context_data) if isinstance(context_data, dict) else context_data,
                    "updatedAt": updated_at,
                })
            else:
                logger.info(f"[loadSkillEditorContexts] No context found for skill: {skill_name}")
    
    # If no specific skills requested, list all available contexts for this user
    elif not skill_names and not skill_ids:
        prefix = _norm_prefix(env.s3_key_root)
        user_dir = _safe_user_dir_name(owner)
        contexts_prefix = _s3_key(prefix, user_dir, "skill_contexts")
        if contexts_prefix:
            contexts_prefix += "/"
        
        logger.info(f"[loadSkillEditorContexts] Listing all contexts with prefix: {contexts_prefix}")
        keys = _s3_list_keys(bucket=env.s3_bucket, prefix=contexts_prefix)
        logger.info(f"[loadSkillEditorContexts] Found {len(keys)} keys")
        
        for key in keys:
            if key.endswith("/context.json"):
                # Extract skill name from key path
                # Format: <prefix>/<user>/skill_contexts/<skill_name>/context.json
                parts = key.split("/")
                if len(parts) >= 2:
                    skill_name = parts[-2]  # skill_name is second to last
                    logger.info(f"[loadSkillEditorContexts] Loading context for skill: {skill_name} from {key}")
                    context_data = _s3_get_json(bucket=env.s3_bucket, key=key)
                    if context_data is not None:
                        try:
                            resp = _s3_client().head_object(Bucket=env.s3_bucket, Key=key)
                            last_modified = resp.get("LastModified")
                            updated_at = last_modified.isoformat() if last_modified else _utc_now_iso()
                        except Exception as e:
                            logger.warning(f"[loadSkillEditorContexts] Failed to get LastModified for {key}: {e}")
                            updated_at = _utc_now_iso()
                        
                        items.append({
                            "skillId": None,
                            "skillName": skill_name,
                            "context": json.dumps(context_data) if isinstance(context_data, dict) else context_data,
                            "updatedAt": updated_at,
                        })
    
    logger.info(f"[loadSkillEditorContexts] Returning {len(items)} context items")
    return {"items": items}


def handler(event, context):
    _ = context

    info = event.get("info") or {}
    field = info.get("fieldName")

    logger.info(f"[handler] Lambda invoked, fieldName={field}")

    try:
        if field == "createSkillEditorChatSession":
            return _handle_create_session(event)
        if field == "getSkillEditorChatSessions":
            return _handle_get_sessions(event)
        if field == "getSkillEditorChatHistory":
            return _handle_get_history(event)
        if field == "sendSkillEditorChatMessage":
            return _handle_send_message(event)
        if field == "cancelSkillEditorChatGeneration":
            return _handle_cancel_generation(event)
        if field == "deleteSkillEditorChatSession":
            return _handle_delete_session(event)
        if field == "loadSkillEditorContexts":
            return _handle_load_skill_editor_contexts(event)

        logger.error(f"[handler] Unsupported fieldName: {field}")
        raise RuntimeError(f"Unsupported fieldName: {field}")

    except Exception as e:
        import traceback
        error_msg = str(e)
        error_tb = traceback.format_exc()
        logger.error(f"[handler] Unhandled exception in {field}: {error_msg}")
        logger.error(f"[handler] Traceback: {error_tb}")
        
        # For sendSkillEditorChatMessage, the error is already handled with S3 persistence
        # For other operations, re-raise to let AppSync handle the error
        raise
