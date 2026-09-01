"""Contact-verification handshake IPC handlers (CN).

Server side (deployed 2026-09-01, ecbAccountManager 92e8741): accounts.email
/ accounts.phone are only written after a 6-digit code round-trips —

    verify_send_code  {action, channel: "email"|"phone", target}
        -> {success, channel, target: "us***@…", expiresInSeconds: 600}
    verify_confirm    {action, channel, code}
        -> {success, verified: true, account: {email, email_verified,
            phone, phone_verified, verify_deadline}}
    verify_status     {action}
        -> current fields + pending: [{channel, target, expires_at}]

Codes: 10-min expiry, 5 attempts, 60s resend gap, 5/hour cap. Typed error
codes pass through verbatim so the frontend can branch: retry_later,
hourly_limit, code_expired, too_many_attempts, invalid_code,
channel_not_configured (503 until SES/SMS templates are approved).

Auth: same bearer chain as payment orders — CloudBase AccessToken when the
auth manager holds one (email/phone logins), else the eCan HS256 session
token (WeChat logins). Sent as Authorization: Bearer on the service HTTP
route (this route does NOT strip the header, unlike the public Event
gateway ensure_account uses).
"""

import json
import traceback
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from utils.app_env import is_cn
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger


def _bearer_token() -> str:
    """CloudBase AccessToken if available, else the eCan session token."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
    except Exception:
        mainwin = None
    try:
        am = getattr(mainwin, "auth_manager", None)
        if am is not None:
            raw = am.get_tokens() or {}
            tok = str(raw.get("AccessToken") or raw.get("access_token") or "").strip()
            if tok:
                return tok
    except Exception:
        pass
    try:
        from agent.cloud_api.cloud_api import _http_auth_header
        bearer = _http_auth_header(mainwin.get_auth_token() or "")
        return bearer[7:] if bearer.lower().startswith("bearer ") else bearer
    except Exception:
        return ""


def _account_manager_url() -> str:
    from agent.cloud_api.endpoints import get_endpoint_config
    gql = (get_endpoint_config().graphql_endpoint or "").strip()
    if not gql:
        return ""
    parts = urlsplit(gql)
    return f"{parts.scheme}://{parts.netloc}/ecbAccountManager"


def _call_verify_action(request: IPCRequest, body: Dict[str, Any]) -> IPCResponse:
    """POST *body* to ecbAccountManager and map the reply to an IPC response.

    Server errors keep their typed code (invalid_code, retry_later, …) as the
    IPC error code, with the parsed body in details so fields like
    remaining_attempts reach the frontend.
    """
    if not is_cn():
        return create_error_response(
            request, "CN_ONLY", "Contact verification is CN-only")

    url = _account_manager_url()
    if not url:
        return create_error_response(
            request, "NOT_CONFIGURED", "No GraphQL endpoint configured")

    token = _bearer_token()
    if not token:
        return create_error_response(
            request, "NO_TOKEN", "Not signed in — no bearer token available")

    action = body.get("action", "?")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(65536).decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as he:
        raw = he.read(4096).decode("utf-8", "replace")
        status = he.code
    except Exception as exc:
        logger.warning(f"[AccountVerify] {action} transport error: {exc}")
        return create_error_response(request, "NETWORK_ERROR", str(exc))

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {"raw": raw[:500]}
    if not isinstance(payload, dict):
        payload = {"result": payload}

    code = str(payload.get("error") or payload.get("code") or "").strip()
    ok = bool(payload.get("success")) and status < 400
    # Log target-free: payload may carry the raw email/phone on send.
    logger.info(f"[AccountVerify] {action} status={status} "
                f"success={ok} error={code or '-'}")
    if ok:
        return create_success_response(request, payload)
    return create_error_response(
        request,
        code or f"HTTP_{status}",
        str(payload.get("message") or code or f"verification call failed ({status})"),
        details=payload,
    )


@IPCHandlerRegistry.handler("verify_send_code")
def handle_verify_send_code(request: IPCRequest,
                            params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Send a 6-digit code to a NEW email/phone. Nothing is written to the
    account until verify_confirm succeeds — that's the handshake."""
    try:
        channel = str((params or {}).get("channel") or "").strip()
        target = str((params or {}).get("target") or "").strip()
        if channel not in ("email", "phone") or not target:
            return create_error_response(
                request, "INVALID_PARAMS",
                "channel ('email'|'phone') and target are required")
        return _call_verify_action(request, {
            "action": "verify_send_code",
            "channel": channel,
            "target": target,
        })
    except Exception as e:
        logger.error(f"[AccountVerify] send_code error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "VERIFY_ERROR", str(e))


@IPCHandlerRegistry.handler("verify_confirm")
def handle_verify_confirm(request: IPCRequest,
                          params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Confirm the 6-digit code; on success the server commits the contact
    value and returns the updated account fields."""
    try:
        channel = str((params or {}).get("channel") or "").strip()
        code = str((params or {}).get("code") or "").strip()
        if channel not in ("email", "phone") or not code:
            return create_error_response(
                request, "INVALID_PARAMS",
                "channel ('email'|'phone') and code are required")
        return _call_verify_action(request, {
            "action": "verify_confirm",
            "channel": channel,
            "code": code,
        })
    except Exception as e:
        logger.error(f"[AccountVerify] confirm error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "VERIFY_ERROR", str(e))


@IPCHandlerRegistry.handler("verify_status")
def handle_verify_status(request: IPCRequest,
                         params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Current verified fields + pending (masked) verifications."""
    try:
        return _call_verify_action(request, {"action": "verify_status"})
    except Exception as e:
        logger.error(f"[AccountVerify] status error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "VERIFY_ERROR", str(e))
