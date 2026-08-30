# -*- coding: utf-8 -*-
"""CN account API-key operations (create / get / remove / test).

Talks to the ``myAPIKeygen`` CloudBase function — the SAME backend the web
app's Account page uses via the CloudBase JS SDK (``callFunction``), so
desktop, CLI, and web all manage the one key stored in ``ecan_apikeys``.

Transport (2026-08-30, live-verified): the CloudBase gateway's function
invoke route — the HTTP equivalent of the web SDK's callFunction:

    POST https://{env_id}.api.tcloudbasegateway.com/v1/functions/myAPIKeygen
    Authorization: Bearer <CloudBase access token>
    {"action": "createApiKey" | "getApiKey" | "removeApiKeys" | "queryApiKey", ...}

The function derives the owner from the authenticated CloudBase context
(``cloudbaseIdentity()``) exactly as it does for web callers; the response is
the function's return value as JSON. (The earlier ``<origin>/myAPIKeygen``
service route does NOT exist — the gateway answers INVALID_PATH — so no
server-side HTTP-route work is needed for this path.)

Auth resolution: callers pass whatever bearer they have; the helper tries it,
then the running app's auth token, then mints a fresh CloudBase access token
from the keyring refresh token (``ecan_cloudbase_refresh`` / <username>) —
which is what makes the CLI and deploy-subprocess paths work headlessly.
"""

import json
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_FUNCTION = "myAPIKeygen"
_TIMEOUT_S = 20


def mask_api_key(key: str) -> str:
    """first6 + '*'... + last6 — mirrors the web Account page's maskApiKey."""
    key = str(key or "")
    if len(key) <= 12:
        return key
    return key[:6] + "*" * (len(key) - 12) + key[-6:]


def _env_id() -> str:
    try:
        from auth.auth_config import AuthConfig
        return str(AuthConfig.CLOUDBASE.ENV_ID or "").strip()
    except Exception:
        return ""


def _gateway_base() -> str:
    env = _env_id()
    return f"https://{env}.api.tcloudbasegateway.com" if env else ""


def _strip_bearer(token: str) -> str:
    token = str(token or "").strip()
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def _mint_access_token_from_refresh() -> str:
    """Mint a CloudBase access token from the stored refresh token (headless
    CLI / subprocess path). Empty string when unavailable."""
    import os
    import urllib.request as _rq
    try:
        import keyring
        username = (os.environ.get("ECAN_CLI_USER") or "").strip()
        if not username:
            try:
                from utils.path_manager import path_manager
                uli = json.loads(
                    (path_manager.get_appdata_path() / "uli.json").read_text(encoding="utf-8"))
                username = str(uli.get("username") or uli.get("user") or "").strip()
            except Exception:
                username = ""
        if not username:
            return ""
        rt = keyring.get_password("ecan_cloudbase_refresh", username)
        if not rt:
            return ""
        base = _gateway_base()
        if not base:
            return ""
        body = json.dumps({"client_id": _env_id(), "grant_type": "refresh_token",
                           "refresh_token": rt}).encode("utf-8")
        req = _rq.Request(base + "/auth/v1/token", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
        with _rq.urlopen(req, timeout=_TIMEOUT_S) as resp:
            payload = json.load(resp)
        # CloudBase ROTATES refresh tokens on every mint (single-use). Persist
        # the new one immediately or the next mint — and the app's own session
        # restore — fails with unauthorized_client.
        new_rt = str(payload.get("refresh_token") or "").strip()
        if new_rt and new_rt != rt:
            try:
                keyring.set_password("ecan_cloudbase_refresh", username, new_rt)
            except Exception as save_err:
                logger.warning(f"[api_keys] rotated refresh token NOT saved: {save_err}")
        return str(payload.get("access_token") or "")
    except Exception as exc:
        logger.debug(f"[api_keys] refresh-token mint failed: {exc}")
        return ""


def _candidate_tokens(given: str) -> List[str]:
    tokens: List[str] = []
    given = _strip_bearer(given)
    if given:
        tokens.append(given)
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is not None:
            app_tok = _strip_bearer(mainwin.get_auth_token() or "")
            if app_tok and app_tok not in tokens:
                tokens.append(app_tok)
    except Exception:
        pass
    return tokens


def _post(action: str, session_token: str,
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Invoke myAPIKeygen via the gateway with auth fallback; never raises."""
    import urllib.request as _rq
    import urllib.error as _err

    base = _gateway_base()
    if not base:
        return {"success": False, "error": "no_endpoint",
                "message": "CloudBase env id not configured"}
    url = f"{base}/v1/functions/{_FUNCTION}"
    body = json.dumps({"action": action, **(extra or {})}).encode("utf-8")

    tokens = _candidate_tokens(session_token)
    tokens.append("")  # sentinel: last chance = mint from refresh token
    last: Dict[str, Any] = {"success": False, "error": "no_token",
                            "message": "No usable auth token — sign in first"}
    for tok in tokens:
        if tok == "":
            tok = _mint_access_token_from_refresh()
            if not tok:
                break
        req = _rq.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {tok}",
        }, method="POST")
        try:
            with _rq.urlopen(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except _err.HTTPError as he:
            raw = he.read().decode("utf-8", "replace")
            if he.code in (401, 403):
                # wrong credential type — try the next candidate
                last = {"success": False, "error": f"http_{he.code}",
                        "message": raw[:300]}
                continue
            logger.warning(f"[api_keys] {action} HTTP {he.code}: {raw[:300]}")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"message": raw[:300]}
            return {"success": False, "error": f"http_{he.code}",
                    **(parsed if isinstance(parsed, dict) else {})}
        except Exception as exc:
            logger.warning(f"[api_keys] {action} request failed: {exc}")
            return {"success": False, "error": "request_failed", "message": str(exc)}

        try:
            parsed = json.loads(raw)
        except Exception:
            return {"success": False, "error": "bad_response", "message": raw[:300]}
        if isinstance(parsed, dict):
            parsed.setdefault("success", "error" not in parsed)
            return parsed
        return {"success": True, "result": parsed}
    return last


def create_api_key(session_token: str, customer: str = "guest") -> Dict[str, Any]:
    """Create (or return the existing) API key for the signed-in account."""
    return _post("createApiKey", session_token, {"customer": customer})


def get_api_key(session_token: str) -> Dict[str, Any]:
    """Fetch the account's active API key ({'apiKey': None, 'status':
    'not_found'} when absent — that is a success, not an error)."""
    return _post("getApiKey", session_token)


def remove_api_keys(session_token: str, keys: List[str]) -> Dict[str, Any]:
    """Revoke key(s); accepts full keys or masked (first6*last6) forms."""
    return _post("removeApiKeys", session_token, {"keys": list(keys or [])})


def test_api_key(session_token: str, api_key: str) -> Dict[str, Any]:
    """Validate a key against the store (server queryApiKey lookup)."""
    return _post("queryApiKey", session_token, {"apiKey": api_key})


def get_local_synced_api_key() -> str:
    """The account API key previously synced into local provider settings
    (Account page → sync_ecanai_account_api_key stores it as
    ECANAI_LLM_API_KEY). Lets desktop flows use the key without a cloud
    round-trip. Empty string when never synced."""
    try:
        from utils.env.secure_store import secure_store, get_current_username
        value = secure_store.get("ECANAI_LLM_API_KEY", username=get_current_username())
        return str(value or "").strip()
    except Exception:
        return ""


def get_api_key_with_local_fallback(session_token: str) -> Dict[str, Any]:
    """Local synced key first (no network); cloud getApiKey otherwise."""
    local = get_local_synced_api_key()
    if local:
        return {"success": True, "apiKey": local, "source": "local"}
    result = get_api_key(session_token)
    result.setdefault("source", "cloud")
    return result


def ensure_api_key(session_token: str, customer: str = "guest") -> Dict[str, Any]:
    """Idempotent: return the existing key, creating one when absent.

    Result dict carries ``created`` (bool) alongside the server fields.
    """
    existing = get_api_key(session_token)
    if existing.get("apiKey"):
        return {**existing, "created": False}
    created = create_api_key(session_token, customer=customer)
    created["created"] = bool(created.get("apiKey"))
    return created
