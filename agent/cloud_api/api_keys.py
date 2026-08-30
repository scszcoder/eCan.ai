# -*- coding: utf-8 -*-
"""CN account API-key operations (create / get / remove / test).

Talks to the ``myAPIKeygen`` CloudBase function — the SAME backend the web
app's Account page uses via the CloudBase JS SDK (``callFunction``), so
desktop, CLI, and web all manage the one key stored in ``ecan_apikeys``.

Desktop/CLI cannot use the JS SDK, so they POST to the function's SCF HTTP
route at ``<tcb-origin>/myAPIKeygen``. Following the ecbAccountManager
contract, the public Event gateway strips the Authorization header on such
routes, so the eCan session token travels in the JSON body as
``sessionToken``; the server verifies it (HS256, ECAN_JWT_SECRET) and derives
the owner identity from the verified claims — it must not trust any
caller-provided identity fields.

Server prerequisite (deployed separately, not from this repo): the
``myAPIKeygen`` HTTP route must accept
``{"action": "createApiKey"|"getApiKey"|"removeApiKeys"|"queryApiKey",
"sessionToken": ..., ...}`` — today its HTTP branch only serves
``queryApiKey`` without identity.
"""

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from utils.logger_helper import logger_helper as logger

_ROUTE = "/myAPIKeygen"
_TIMEOUT_S = 20


def mask_api_key(key: str) -> str:
    """first6 + '*'... + last6 — mirrors the web Account page's maskApiKey."""
    key = str(key or "")
    if len(key) <= 12:
        return key
    return key[:6] + "*" * (len(key) - 12) + key[-6:]


def _endpoint_url() -> str:
    from agent.cloud_api.endpoints import get_endpoint_config
    gql = (get_endpoint_config().graphql_endpoint or "").strip()
    if not gql:
        return ""
    parts = urlsplit(gql)
    return f"{parts.scheme}://{parts.netloc}{_ROUTE}"


def _post(action: str, session_token: str,
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """POST one action to the myAPIKeygen HTTP route; never raises."""
    import urllib.request as _rq
    import urllib.error as _err

    url = _endpoint_url()
    if not url:
        return {"success": False, "error": "no_endpoint",
                "message": "GraphQL endpoint not configured"}
    token = str(session_token or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return {"success": False, "error": "no_token",
                "message": "No session token available — sign in first"}

    body = {"action": action, "sessionToken": token}
    body.update(extra or {})
    req = _rq.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _rq.urlopen(req, timeout=_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except _err.HTTPError as he:
        raw = he.read().decode("utf-8", "replace")
        logger.warning(f"[api_keys] {action} HTTP {he.code}: {raw[:300]}")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"message": raw[:300]}
        return {"success": False, "error": f"http_{he.code}", **parsed} \
            if isinstance(parsed, dict) else {"success": False, "error": f"http_{he.code}"}
    except Exception as exc:
        logger.warning(f"[api_keys] {action} request failed: {exc}")
        return {"success": False, "error": "request_failed", "message": str(exc)}

    try:
        parsed = json.loads(raw)
    except Exception:
        return {"success": False, "error": "bad_response", "message": raw[:300]}
    # SCF HTTP wrapper may nest the function result under 'body'.
    if isinstance(parsed, dict) and isinstance(parsed.get("body"), str):
        try:
            parsed = json.loads(parsed["body"])
        except Exception:
            pass
    if isinstance(parsed, dict):
        parsed.setdefault("success", "error" not in parsed)
        return parsed
    return {"success": True, "result": parsed}


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
