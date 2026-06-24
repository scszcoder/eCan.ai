"""
Tencent CIAM identity service — China-region counterpart of ``CognitoService``.

CIAM (Customer Identity Access Management) mirrors Cognito's role: it brokers the
WeChat "Website App" scan-to-login the way Cognito's Hosted UI brokers Google. CIAM
is OIDC-standard, so this service is a plain OIDC client: it derives every endpoint
from the issuer's ``.well-known/openid-configuration`` discovery document rather than
hardcoding Tencent-specific paths, and exposes the same method surface + return shape
(``{'success': bool, 'data'|'error': ...}``) as ``CognitoService`` so ``AuthManager``
can use the two interchangeably.

Inert until configured: with an empty ``TENCENT_CIAM.ISSUER`` (the default), every
method returns a "not configured" error and no network is touched. Fill the config
from the CIAM console once Layer 0 is done (ICP-filed domain + WeChat Open Platform
app + CIAM instance). Verify the WeChat IdP hint + any CIAM-specific param names
against the CIAM console/docs before going live.
"""

import os
import threading

import requests
from jose import jwt
from jose.exceptions import JOSEError

from utils.logger_helper import logger_helper as logger
from auth.auth_config import AuthConfig

# CIAM runtime is in-China (CN user -> CN CIAM), so no GFW long-haul padding needed.
_DISCOVERY_TIMEOUT = 30
_TOKEN_TIMEOUT = 30
_USERINFO_TIMEOUT = 30


class CIAMService:

    def __init__(self):
        self._discovery = None      # cached .well-known/openid-configuration
        self.jwks = None            # cached signing keys
        # Only warm caches when actually configured, so an unconfigured CN build
        # (the default today) does zero network on startup.
        if self._is_configured():
            threading.Thread(target=self._preload, name="CIAM-Preload", daemon=True).start()

    # --- config helpers ---------------------------------------------------

    @staticmethod
    def _cfg(name: str, default: str = "") -> str:
        """Read a TENCENT_CIAM value, tolerating an absent key/block."""
        try:
            val = getattr(AuthConfig.TENCENT_CIAM, name)
        except AttributeError:
            return default
        return val if val is not None else default

    def _is_configured(self) -> bool:
        return bool(self._cfg("ISSUER").strip())

    def _not_configured(self) -> dict:
        return {'success': False, 'error': 'TENCENT_CIAM not configured (empty ISSUER)'}

    # --- OIDC discovery + JWKS -------------------------------------------

    def _preload(self):
        """Background warm of discovery + JWKS to cut first-login latency."""
        try:
            if self._get_discovery():
                self._get_jwks()
        except Exception as e:
            logger.debug(f"[CIAMService] preload skipped: {e}")

    def _get_discovery(self):
        """Fetch and cache the issuer's OIDC discovery document (or None)."""
        if self._discovery:
            return self._discovery
        issuer = self._cfg("ISSUER").strip().rstrip("/")
        if not issuer:
            return None
        url = f"{issuer}/.well-known/openid-configuration"
        try:
            resp = requests.get(url, timeout=_DISCOVERY_TIMEOUT)
            resp.raise_for_status()
            self._discovery = resp.json()
            logger.info(f"[CIAMService] OIDC discovery loaded from {url}")
            return self._discovery
        except requests.exceptions.RequestException as e:
            logger.error(f"[CIAMService] discovery fetch failed ({url}): {e}")
            return None

    def _get_jwks(self):
        """Fetch and cache signing keys from the discovery ``jwks_uri`` (or None)."""
        if self.jwks:
            return self.jwks
        disco = self._get_discovery()
        if not disco or not disco.get("jwks_uri"):
            return None
        try:
            resp = requests.get(disco["jwks_uri"], timeout=_DISCOVERY_TIMEOUT)
            resp.raise_for_status()
            self.jwks = resp.json().get("keys")
            return self.jwks
        except requests.exceptions.RequestException as e:
            logger.error(f"[CIAMService] JWKS fetch failed: {e}")
            return None

    def verify_token(self, token: str, token_use: str = 'id'):
        """Verify a CIAM-issued JWT against the discovery JWKS + issuer/audience."""
        if not self._is_configured():
            return self._not_configured()

        disco = self._get_discovery()
        if not disco:
            return {'success': False, 'error': 'OIDC discovery unavailable'}

        if not self.jwks:
            self.jwks = self._get_jwks()
            if not self.jwks:
                return {'success': False, 'error': 'JWKS not available'}

        try:
            unverified_header = jwt.get_unverified_header(token)
        except JOSEError as e:
            return {'success': False, 'error': f'Invalid token header: {e}'}

        kid = unverified_header.get('kid')
        if not kid:
            return {'success': False, 'error': 'Token header is missing "kid"'}

        key = next((k for k in self.jwks if k['kid'] == kid), None)
        if not key:
            return {'success': False, 'error': 'Public key not found in JWKS'}

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=self._cfg("CLIENT_ID"),
                issuer=disco.get("issuer"),
            )
            # WeChat-federated ID tokens may omit token_use; only reject on mismatch.
            actual = claims.get('token_use')
            if actual is not None and actual != token_use:
                return {'success': False, 'error': f'Invalid token_use. Expected "{token_use}", got "{actual}"'}
            return {'success': True, 'data': claims}
        except JOSEError as e:
            return {'success': False, 'error': f'Token is invalid: {e}'}

    # --- authorization-code (PKCE) flow ----------------------------------

    def get_wechat_login_url(self, redirect_uri, pkce_params: dict | None = None):
        """Build the CIAM authorize URL that initiates WeChat scan-to-login.

        Mirrors ``CognitoService.get_google_login_url``: ``response_type=code`` with
        an IdP hint so CIAM goes straight to WeChat instead of its own login page.
        The exact IdP-hint param name is CIAM-specific — verify ``WECHAT_IDP`` and the
        param key (``identity_provider`` here) against the CIAM console before use.
        """
        if not self._is_configured():
            return self._not_configured()
        disco = self._get_discovery()
        if not disco or not disco.get("authorization_endpoint"):
            return {'success': False, 'error': 'authorization_endpoint unavailable'}

        params = {
            'response_type': 'code',
            'client_id': self._cfg("CLIENT_ID"),
            'redirect_uri': redirect_uri,
            'scope': 'openid profile',
        }
        wechat_idp = self._cfg("WECHAT_IDP")
        if wechat_idp:
            params['identity_provider'] = wechat_idp
        if pkce_params:
            params.update(pkce_params)

        from urllib.parse import urlencode
        url = f"{disco['authorization_endpoint']}?{urlencode(params)}"
        return {'success': True, 'data': {'url': url}}

    def exchange_code_for_tokens(self, code, redirect_uri, code_verifier: str | None = None):
        """Back-channel exchange of an authorization code for OIDC tokens."""
        if not self._is_configured():
            return self._not_configured()
        disco = self._get_discovery()
        if not disco or not disco.get("token_endpoint"):
            return {'success': False, 'error': 'token_endpoint unavailable'}

        client_id = self._cfg("CLIENT_ID")
        client_secret = self._cfg("CLIENT_SECRET")
        auth = (client_id, client_secret) if client_secret else None
        data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'code': code,
            'redirect_uri': redirect_uri,
        }
        if code_verifier:
            data['code_verifier'] = code_verifier

        try:
            resp = requests.post(
                disco['token_endpoint'],
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=data, auth=auth, timeout=_TOKEN_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info("[CIAMService] token exchange successful")
            return {'success': True, 'data': resp.json()}
        except requests.exceptions.RequestException as e:
            error_msg = e.response.json() if getattr(e, 'response', None) else str(e)
            logger.error(f"[CIAMService] token exchange failed: {error_msg}")
            return {'success': False, 'error': error_msg}

    def refresh_tokens(self, refresh_token):
        """Refresh tokens via the OIDC ``refresh_token`` grant."""
        if not self._is_configured():
            return self._not_configured()
        disco = self._get_discovery()
        if not disco or not disco.get("token_endpoint"):
            return {'success': False, 'error': 'token_endpoint unavailable'}

        client_id = self._cfg("CLIENT_ID")
        client_secret = self._cfg("CLIENT_SECRET")
        auth = (client_id, client_secret) if client_secret else None
        data = {
            'grant_type': 'refresh_token',
            'client_id': client_id,
            'refresh_token': refresh_token,
        }
        try:
            resp = requests.post(
                disco['token_endpoint'],
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=data, auth=auth, timeout=_TOKEN_TIMEOUT,
            )
            resp.raise_for_status()
            new_tokens = resp.json()
            # OIDC may not re-issue a refresh token; preserve the existing one.
            new_tokens.setdefault('refresh_token', refresh_token)
            return {'success': True, 'data': new_tokens}
        except requests.exceptions.RequestException as e:
            error_msg = e.response.json() if getattr(e, 'response', None) else str(e)
            logger.error(f"[CIAMService] token refresh failed: {error_msg}")
            return {'success': False, 'error': error_msg}

    def get_userinfo(self, access_token: str):
        """Fetch user claims (email/openid/etc.) from the OIDC userinfo endpoint."""
        if not self._is_configured():
            return self._not_configured()
        disco = self._get_discovery()
        if not disco or not disco.get("userinfo_endpoint"):
            return {'success': False, 'error': 'userinfo_endpoint unavailable'}
        try:
            resp = requests.get(
                disco['userinfo_endpoint'],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=_USERINFO_TIMEOUT,
            )
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": e.response.json() if getattr(e, 'response', None) else str(e)}
