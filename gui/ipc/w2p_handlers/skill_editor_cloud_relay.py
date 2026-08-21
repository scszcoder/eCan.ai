"""Cloud relay for Skill Editor Chat: forwards requests to AppSync/Lambda
instead of running the local SkillEditorAgent.

Flow:  Frontend → IPC (local Python) → this module → AppSync → Lambda
       (SkillEditorAgent runs in Lambda, not locally)

Reuses the same auth/endpoint helpers as prompt_cloud_sync.py.
Uses Content-Type: application/json (required when variables are present).
"""

from __future__ import annotations

import json
import time
import traceback
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Auth / endpoint helpers (same pattern as prompt_cloud_sync)
# ---------------------------------------------------------------------------

def _get_cloud_context() -> Optional[Dict[str, Any]]:
    """Return {session, token, endpoint, owner} from the running MainWindow, or None."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            logger.debug("[se_cloud_relay] MainWindow not available")
            return None

        token = mainwin.get_auth_token()
        if not token:
            logger.debug("[se_cloud_relay] No auth token")
            return None

        session = mainwin.session
        endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, 'getWanApiEndpoint') else None
        from agent.cloud_api.cloud_api import normalize_cloud_owner
        owner = normalize_cloud_owner(getattr(mainwin, 'user', None) or "")

        if not owner:
            logger.debug("[se_cloud_relay] No owner/user")
            return None

        return {
            "session": session,
            "token": token,
            "endpoint": endpoint,
            "owner": owner,
        }
    except Exception as exc:
        logger.debug(f"[se_cloud_relay] Failed to get cloud context: {exc}")
        return None


def _appsync_request(query_string: str, ctx: Dict[str, Any],
                     variables: Optional[Dict] = None,
                     timeout: int = 300) -> Dict:
    """Send a GraphQL request to AppSync with variables support.

    Uses Content-Type: application/json (matching the web app's appSyncClient.ts)
    because AppSync requires JSON content-type when variables are present.
    """
    from agent.cloud_api.cloud_api import get_appsync_endpoint, _http_auth_header

    endpoint = ctx.get("endpoint") or get_appsync_endpoint()
    token = ctx["token"]
    session = ctx["session"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": _http_auth_header(token),
        "cache-control": "no-cache",
    }

    payload: Dict[str, Any] = {"query": query_string}
    if variables:
        payload["variables"] = variables

    try:
        resp = session.request(
            url=endpoint,
            method="POST",
            timeout=timeout,
            headers=headers,
            json=payload,
        )
        jresp = resp.json()
        logger.debug(
            f"[se_cloud_relay] AppSync response status={resp.status_code}, "
            f"keys={list(jresp.keys()) if isinstance(jresp, dict) else 'N/A'}"
        )
        return jresp
    except Exception as exc:
        logger.warning(f"[se_cloud_relay] AppSync request failed: {exc}")
        return {"errors": [{"errorType": "RequestError", "message": str(exc)}]}


# ---------------------------------------------------------------------------
# GraphQL query/mutation strings (matching gui_v2/src/services/api/api-config.ts)
# ---------------------------------------------------------------------------

_GQL_CREATE_SESSION = """
mutation CreateSkillEditorChatSession($input: SkillEditorChatSessionInput!) {
  createSkillEditorChatSession(input: $input) {
    id name flowgramId createdAt updatedAt
  }
}
"""

_GQL_SEND_MESSAGE = """
mutation SendSkillEditorChatMessage($input: SkillEditorChatMessageInput!) {
  sendSkillEditorChatMessage(input: $input) {
    sessionId sessionName state intent
    message { id role content timestamp attachments metadata }
    clarification plan flowgram validation
  }
}
"""

_GQL_CANCEL_GENERATION = """
mutation CancelSkillEditorChatGeneration($sessionId: ID!) {
  cancelSkillEditorChatGeneration(sessionId: $sessionId)
}
"""

_GQL_DELETE_SESSION = """
mutation DeleteSkillEditorChatSession($sessionId: ID!) {
  deleteSkillEditorChatSession(sessionId: $sessionId)
}
"""

_GQL_GET_SESSIONS = """
query GetSkillEditorChatSessions($userId: ID!) {
  getSkillEditorChatSessions(userId: $userId) {
    id name flowgramId createdAt updatedAt
  }
}
"""

_GQL_GET_HISTORY = """
query GetSkillEditorChatHistory($sessionId: ID!, $limit: Int, $offset: Int) {
  getSkillEditorChatHistory(sessionId: $sessionId, limit: $limit, offset: $offset) {
    id role content timestamp attachments metadata
  }
}
"""


# ---------------------------------------------------------------------------
# Helper: parse AWSJSON fields that AppSync may return as JSON strings
# ---------------------------------------------------------------------------

def _parse_awsjson(value: Any) -> Any:
    """Parse an AWSJSON field (string → object). Returns original if already parsed or None."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _extract_data(jresp: Dict[str, Any], operation_name: str) -> Any:
    """Extract data from a GraphQL response: jresp['data'][operation_name]."""
    if not isinstance(jresp, dict):
        return None
    data = jresp.get("data")
    if not isinstance(data, dict):
        return None
    return data.get(operation_name)


# ---------------------------------------------------------------------------
# Public relay functions — called by skill_editor_chat_handler.py
# ---------------------------------------------------------------------------

def relay_create_session(name: str = "New Chat",
                         flowgram_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Relay createSkillEditorChatSession to cloud.

    Returns the session dict or None on failure.
    """
    ctx = _get_cloud_context()
    if ctx is None:
        logger.warning("[se_cloud_relay] No cloud context for create_session")
        return None

    variables = {"input": {"name": name, "flowgramId": flowgram_id}}
    jresp = _appsync_request(_GQL_CREATE_SESSION, ctx, variables=variables, timeout=30)

    if "errors" in jresp:
        logger.error(f"[se_cloud_relay] create_session errors: {jresp['errors']}")
        return None

    return _extract_data(jresp, "createSkillEditorChatSession")


def relay_get_sessions() -> Optional[List[Dict[str, Any]]]:
    """Relay getSkillEditorChatSessions to cloud.

    Returns list of session dicts, or None on failure (no cloud context or
    cloud errors) so the caller can fall back instead of treating a failure
    as an empty session list.
    """
    ctx = _get_cloud_context()
    if ctx is None:
        logger.warning("[se_cloud_relay] No cloud context for get_sessions")
        return None

    owner = ctx["owner"]
    variables = {"userId": owner}
    jresp = _appsync_request(_GQL_GET_SESSIONS, ctx, variables=variables, timeout=30)

    if "errors" in jresp:
        logger.error(f"[se_cloud_relay] get_sessions errors: {jresp['errors']}")
        return None

    result = _extract_data(jresp, "getSkillEditorChatSessions")
    return result if isinstance(result, list) else None


def relay_get_history(session_id: str,
                      limit: Optional[int] = None,
                      offset: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Relay getSkillEditorChatHistory to cloud.

    Returns {messages: [...], total, sessionId} or None.
    The AppSync query returns a flat list of message objects; we wrap it
    into the {messages, total, sessionId} shape the IPC handler expects.
    """
    ctx = _get_cloud_context()
    if ctx is None:
        logger.warning("[se_cloud_relay] No cloud context for get_history")
        return None

    variables: Dict[str, Any] = {"sessionId": session_id}
    if limit is not None:
        variables["limit"] = limit
    if offset is not None:
        variables["offset"] = offset

    jresp = _appsync_request(_GQL_GET_HISTORY, ctx, variables=variables, timeout=30)

    if "errors" in jresp:
        logger.error(f"[se_cloud_relay] get_history errors: {jresp['errors']}")
        return None

    raw = _extract_data(jresp, "getSkillEditorChatHistory")

    # Normalise: could be a list (flat) or a dict with 'messages' key
    if isinstance(raw, list):
        messages = raw
    elif isinstance(raw, dict) and "messages" in raw:
        messages = raw["messages"] if isinstance(raw["messages"], list) else []
    else:
        messages = []

    # Parse AWSJSON fields on each message
    for msg in messages:
        if isinstance(msg, dict):
            msg["metadata"] = _parse_awsjson(msg.get("metadata"))
            msg["attachments"] = _parse_awsjson(msg.get("attachments"))

    return {
        "messages": messages,
        "total": len(messages),
        "sessionId": session_id,
    }


def relay_send_message(session_id: str,
                       content: str,
                       attachments: Optional[List] = None,
                       canvas_context: Optional[Dict] = None,
                       clarification_responses: Optional[Dict] = None,
                       flowgram_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Relay sendSkillEditorChatMessage to cloud.

    Returns the ChatMessageResponse dict (with AWSJSON fields parsed) or None.
    """
    ctx = _get_cloud_context()
    if ctx is None:
        logger.warning("[se_cloud_relay] No cloud context for send_message")
        return None

    owner = ctx["owner"]

    # Build input matching SkillEditorChatMessageInput schema
    input_data: Dict[str, Any] = {
        "sessionId": session_id,
        "content": content,
        "userId": owner,
    }
    if flowgram_id:
        input_data["flowgramId"] = flowgram_id
    # AWSJSON fields must be serialized as JSON strings
    if attachments:
        input_data["attachments"] = json.dumps(attachments, ensure_ascii=False)
    if canvas_context:
        input_data["canvasContext"] = (
            json.dumps(canvas_context, ensure_ascii=False)
            if isinstance(canvas_context, dict)
            else canvas_context
        )
    if clarification_responses:
        input_data["clarificationResponses"] = (
            json.dumps(clarification_responses, ensure_ascii=False)
            if isinstance(clarification_responses, dict)
            else clarification_responses
        )

    variables = {"input": input_data}

    logger.info(
        f"[se_cloud_relay] send_message → AppSync: session={session_id}, "
        f"content_len={len(content)}, has_canvas={canvas_context is not None}"
    )

    jresp = _appsync_request(_GQL_SEND_MESSAGE, ctx, variables=variables, timeout=300)

    if "errors" in jresp:
        errors = jresp["errors"]
        # AppSync has a ~30s response timeout.  If the Lambda exceeds that,
        # AppSync returns a Lambda:ExecutionTimeoutException — but the Lambda
        # itself keeps running (up to its 15-min hard limit).  We must NOT
        # fall back to the local agent in this case because the cloud Lambda
        # is still processing the request.
        is_lambda_timeout = any(
            e.get("errorType") == "Lambda:ExecutionTimeoutException"
            for e in errors
            if isinstance(e, dict)
        )
        if is_lambda_timeout:
            logger.info(
                f"[se_cloud_relay] send_message: AppSync response timeout "
                f"(Lambda still running) for session={session_id}. "
                f"Result will arrive via AppSync subscription relay."
            )
            return {
                "sessionId": session_id,
                "state": "processing",
                "message": {
                    "id": None,
                    "role": "assistant",
                    "content": "⏳ Processing your request — the cloud agent is still working on it. The response will arrive shortly via streaming.",
                    "timestamp": int(time.time() * 1000),
                    "metadata": {"placeholder": True},
                },
            }
        logger.error(f"[se_cloud_relay] send_message errors: {errors}")
        return None

    raw = _extract_data(jresp, "sendSkillEditorChatMessage")
    if not isinstance(raw, dict):
        return None

    # Parse AWSJSON fields
    raw["clarification"] = _parse_awsjson(raw.get("clarification"))
    raw["plan"] = _parse_awsjson(raw.get("plan"))
    raw["flowgram"] = _parse_awsjson(raw.get("flowgram"))
    raw["validation"] = _parse_awsjson(raw.get("validation"))

    # Parse message.metadata and message.attachments if they are AWSJSON
    msg = raw.get("message")
    if isinstance(msg, dict):
        msg["metadata"] = _parse_awsjson(msg.get("metadata"))
        msg["attachments"] = _parse_awsjson(msg.get("attachments"))

    return raw


def relay_cancel_generation(session_id: str) -> bool:
    """Relay cancelSkillEditorChatGeneration to cloud."""
    ctx = _get_cloud_context()
    if ctx is None:
        logger.warning("[se_cloud_relay] No cloud context for cancel_generation")
        return False

    variables = {"sessionId": session_id}
    jresp = _appsync_request(_GQL_CANCEL_GENERATION, ctx, variables=variables, timeout=30)

    if "errors" in jresp:
        logger.error(f"[se_cloud_relay] cancel_generation errors: {jresp['errors']}")
        return False

    result = _extract_data(jresp, "cancelSkillEditorChatGeneration")
    return bool(result)


def relay_delete_session(session_id: str) -> bool:
    """Relay deleteSkillEditorChatSession to cloud."""
    ctx = _get_cloud_context()
    if ctx is None:
        logger.warning("[se_cloud_relay] No cloud context for delete_session")
        return False

    variables = {"sessionId": session_id}
    jresp = _appsync_request(_GQL_DELETE_SESSION, ctx, variables=variables, timeout=30)

    if "errors" in jresp:
        logger.error(f"[se_cloud_relay] delete_session errors: {jresp['errors']}")
        return False

    result = _extract_data(jresp, "deleteSkillEditorChatSession")
    return bool(result)
