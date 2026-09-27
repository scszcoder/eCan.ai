"""eBay OAuth (authorization-code grant) for one seller account.

The seller agrees once on eBay's consent page; the code on the redirect URL is
exchanged here for a user token pair. The refresh token (valid ~18 months) is
kept in the secure store; access tokens (2 h) are minted from it on demand and
cached in memory. Nothing token-shaped is ever returned to a caller that could
put it into an LLM prompt.
"""
import base64
import secrets
import time
from typing import Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from . import config

_TOKEN_PATH = "/identity/v1/oauth2/token"
_pending_state: Dict[str, str] = {}      # env -> state of the consent we opened
_access: Dict[str, tuple] = {}           # env -> (token, expires_at)


class EbayAuthError(RuntimeError):
    pass


def _basic(creds: Dict[str, str]) -> str:
    raw = f"{creds['client_id']}:{creds['client_secret']}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _require_creds(env: str) -> Dict[str, str]:
    creds = config.credentials(env)
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise EbayAuthError(
            f"eBay app credentials missing for {env}: {', '.join(missing)}. Store them with "
            "`python -m agent.ec_skills.listing.ebay_api.config set --env " + env + "`")
    return creds


def consent_url(env: Optional[str] = None) -> str:
    """The page where the seller signs in and agrees to let this app list for them."""
    env = env or config.current_env()
    creds = _require_creds(env)
    state = secrets.token_urlsafe(16)
    _pending_state[env] = state
    q = {"client_id": creds["client_id"], "redirect_uri": creds["ru_name"],
         "response_type": "code", "scope": " ".join(config.SCOPES), "state": state}
    return f"{config.hosts(env)['auth']}/oauth2/authorize?{urlencode(q)}"


def code_from_url(url: str) -> Optional[str]:
    """The authorization code on eBay's redirect URL (None if this is not it)."""
    q = parse_qs(urlparse(url or "").query)
    if (q.get("isAuthSuccessful") or [""])[0].lower() == "false":
        raise EbayAuthError("the seller declined the consent")
    return (q.get("code") or [None])[0]


async def _token_request(env: str, data: Dict[str, str]) -> dict:
    creds = _require_creds(env)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(config.hosts(env)["api"] + _TOKEN_PATH, data=data,
                         headers={"Authorization": _basic(creds),
                                  "Content-Type": "application/x-www-form-urlencoded"})
    body = r.json() if r.content else {}
    if r.status_code != 200:
        raise EbayAuthError(f"token request failed ({r.status_code}): "
                            f"{body.get('error_description') or body.get('error') or r.text[:200]}")
    return body


async def complete_consent(redirect_url: str, env: Optional[str] = None) -> dict:
    """Exchange the code on *redirect_url* and store the refresh token."""
    env = env or config.current_env()
    code = code_from_url(redirect_url)
    if not code:
        raise EbayAuthError("no authorization code on that URL")
    state = (parse_qs(urlparse(redirect_url).query).get("state") or [None])[0]
    expected = _pending_state.get(env)
    if state and expected and state != expected:
        raise EbayAuthError("consent state mismatch -- start the connection again")
    creds = _require_creds(env)
    body = await _token_request(env, {"grant_type": "authorization_code", "code": code,
                                      "redirect_uri": creds["ru_name"]})
    config.set_secret(env, "REFRESH_TOKEN", body["refresh_token"])
    config.set_secret(env, "REFRESH_EXPIRES_AT",
                      str(int(time.time()) + int(body.get("refresh_token_expires_in", 0))))
    _access[env] = (body["access_token"], time.time() + int(body.get("expires_in", 7200)) - 120)
    _pending_state.pop(env, None)
    return status(env)


async def access_token(env: Optional[str] = None) -> str:
    env = env or config.current_env()
    tok = _access.get(env)
    if tok and tok[1] > time.time():
        return tok[0]
    refresh = config.get_secret(env, "REFRESH_TOKEN")
    if not refresh:
        raise EbayAuthError("this eBay seller account is not connected yet")
    body = await _token_request(env, {"grant_type": "refresh_token", "refresh_token": refresh,
                                      "scope": " ".join(config.SCOPES)})
    _access[env] = (body["access_token"], time.time() + int(body.get("expires_in", 7200)) - 120)
    return _access[env][0]


def forget_access_token(env: Optional[str] = None) -> None:
    _access.pop(env or config.current_env(), None)


def status(env: Optional[str] = None) -> dict:
    env = env or config.current_env()
    creds = config.credentials(env)
    exp = config.get_secret(env, "REFRESH_EXPIRES_AT")
    connected = bool(config.get_secret(env, "REFRESH_TOKEN"))
    out = {"env": env, "app_configured": all(creds.values()), "connected": connected}
    if connected and exp and exp.isdigit() and int(exp) > 0:
        out["connection_expires_in_days"] = max(0, (int(exp) - int(time.time())) // 86400)
    return out


def disconnect(env: Optional[str] = None) -> None:
    env = env or config.current_env()
    for name in ("REFRESH_TOKEN", "REFRESH_EXPIRES_AT"):
        config.delete_secret(env, name)
    forget_access_token(env)
