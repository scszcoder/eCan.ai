# auth/auth_manager.py

import webbrowser
import traceback
import asyncio
import time
import uuid
import keyring
import json
import os
import sys
import base64
import threading
from os.path import exists
from typing import Any, Dict, Optional

from config.envi import getECBotDataHome

from auth.cognito.cognito_service import CognitoService
from auth.oauth.local_oauth_server import LocalOAuthServer
from auth.auth_config import AuthConfig
from utils.app_env import is_cn as _is_cn
from utils.logger_helper import logger_helper as logger

class AuthManager:
    """Manages authentication state and business logic."""

    def __init__(self):
        # Set the path attributes FIRST, before anything that may raise.
        # Otherwise, an early exception in cognito_service construction
        # would leave the instance without `acct_file` / `ecb_data_homepath`,
        # and any cleanup path (e.g. _update_saved_login_info / store
        # refresh token) called from the exception handler would then raise
        # "'AuthManager' object has no attribute 'acct_file'".
        self._is_cn = _is_cn()
        self.ecb_data_homepath = getECBotDataHome()
        self.acct_file = self.ecb_data_homepath + "/uli.json"
        logger.info(f"[AuthManager.__init__] Initial acct_file path: {self.acct_file}")
        self.refresh_task = None
        self.tokens = None
        self.current_user = None
        self.user_profile = {}
        self.signed_in = False
        self.last_login_error = None
        self.machine_role = "Platoon"
        # Keychain availability is determined lazily on first actual use
        self._keychain_available = True

        if self._is_cn:
            logger.info("[AuthManager.__init__] ECAN_APP_ID=cn detected; using CloudBaseAuthAdapter")
            try:
                from auth.tencent.cloudbase_adapter import get_cloudbase_adapter
                # Expose it under .cognito_service so every existing
                # `self.cognito_service.<method>(...)` call site in this
                # file (login, refresh loop, _fetch_user_profile, etc.)
                # works unchanged. The adapter normalizes return shapes
                # to match Cognito's dict contract.
                self.cognito_service = get_cloudbase_adapter()
            except Exception as e:
                logger.error(f"[AuthManager.__init__] Failed to load CloudBase adapter: {e}")
                self.cognito_service = None
        else:
            self.cognito_service = CognitoService()

        if not exists(self.acct_file):
            logger.debug(f"[AuthManager.__init__] uli.json not found at {self.acct_file}, checking fallback locations")
            candidate_files: list[str] = []

            try:
                localappdata = os.environ.get('LOCALAPPDATA', '').strip()
                if localappdata:
                    candidate_files.append(os.path.join(localappdata, 'eCan', 'uli.json'))
            except Exception:
                pass

            try:
                repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                candidate_files.append(os.path.join(repo_root, 'uli.json'))
            except Exception:
                pass

            logger.debug(f"[AuthManager.__init__] Candidate files: {candidate_files}")
            for candidate in candidate_files:
                if candidate and exists(candidate):
                    self.acct_file = candidate
                    logger.info(f"[AuthManager.__init__] Found uli.json at fallback location: {candidate}")
                    break

        # Try to restore user info from uli.json for API key isolation
        # This ensures get_current_username() returns the correct user even without full session restore
        try:
            saved_username = self._get_saved_username()
            if saved_username:
                self.current_user = saved_username
                logger.debug(f"AuthManager: Restored user identity from uli.json: {saved_username}")
        except Exception as e:
            logger.debug(f"AuthManager: Could not restore user identity: {e}")

        # Try to restore session from persisted refresh token
        # try:
        # 尝试从存储的 refresh token 恢复会话（CN 版本 - CloudBase）
        if self._is_cn:
            try:
                if self.try_restore_cloudbase_session():
                    logger.info("[AuthManager.__init__] CloudBase session restored from stored credentials")
            except Exception as e:
                logger.warning(f"[AuthManager.__init__] Failed to restore CloudBase session: {e}")

    def is_signed_in(self):
        return self.signed_in

    def get_current_user(self):
        return self.current_user

    def get_tokens(self):
        return self.tokens

    @staticmethod
    def _decode_token_expiry_unsafe(token: str) -> int | None:
        try:
            claims = AuthManager._decode_jwt_payload_unsafe(token)
            exp = claims.get('exp') if isinstance(claims, dict) else None
            if exp is None:
                return None
            exp_int = int(exp)
            # CloudBase/WeChat sign claims with millisecond exp (~1e12);
            # standard JWT uses seconds (~1e9). Normalize to seconds.
            if exp_int > 10_000_000_000:
                exp_int //= 1000
            return exp_int
        except Exception:
            return None

    def _get_best_id_token(self) -> str | None:
        tokens = self.tokens
        if not tokens or not isinstance(tokens, dict):
            return None

        for k in ('IdToken', 'id_token'):
            value = tokens.get(k)
            if isinstance(value, str) and value:
                return value

        auth_result = tokens.get('AuthenticationResult') if isinstance(tokens, dict) else None
        if isinstance(auth_result, dict):
            value = auth_result.get('IdToken')
            if isinstance(value, str) and value:
                return value

        return None

    def _get_best_access_token(self) -> str | None:
        tokens = self.tokens
        if not tokens or not isinstance(tokens, dict):
            return None

        for k in ('AccessToken', 'access_token'):
            value = tokens.get(k)
            if isinstance(value, str) and value:
                return value

        auth_result = tokens.get('AuthenticationResult') if isinstance(tokens, dict) else None
        if isinstance(auth_result, dict):
            value = auth_result.get('AccessToken')
            if isinstance(value, str) and value:
                return value

        return None

    def ensure_valid_tokens(self, min_validity_seconds: int = 120) -> bool:
        try:
            if not self.tokens or not isinstance(self.tokens, dict):
                return False

            id_token = self._get_best_id_token()
            access_token = self._get_best_access_token()
            candidate_token = id_token or access_token
            if not candidate_token:
                return False

            exp = self._decode_token_expiry_unsafe(candidate_token)
            if exp is None:
                logger.debug("[AuthManager] ensure_valid_tokens: no exp claim, treating as valid")
                return True

            now = int(time.time())
            remaining = exp - now
            # Single structured INFO log so we can plot actual TTL distribution
            # from the eCan.log without scanning multiple lines. Keep it small
            # enough to never be filtered out.
            logger.info(
                f"[AuthManager] token-ttl: remaining={remaining}s "
                f"(~{remaining // 60}m{remaining % 60}s) "
                f"buffer={min_validity_seconds}s "
                f"has_refresh={bool(self.tokens.get('RefreshToken') or self.tokens.get('refresh_token'))} "
                f"is_cn={getattr(self, '_is_cn', False)}"
            )

            if remaining > min_validity_seconds:
                return True

            # Token is within the buffer window or already expired.
            # Still valid? Return it — don't churn tokens when we have no way
            # to refresh (e.g., WeChat login without a refresh_token).
            if remaining > 0:
                logger.info(
                    f"[AuthManager] token in grace window "
                    f"(remaining={remaining}s, buffer={min_validity_seconds}s); keeping in use"
                )
                return True

            refresh_token = self.tokens.get('RefreshToken') or self.tokens.get('refresh_token')
            if not refresh_token and not self._is_cn:
                logger.warning("AuthManager: Token is expiring/expired but no refresh token available")
                self.signed_in = False
                return False

            if not refresh_token and self._is_cn:
                # WeChat (or CN login without refresh token): try session token first.
                ok, session_tok = self._get_wechat_session_token()
                if ok:
                    # Cooldown: get_auth_token() runs this on EVERY API call.
                    # When the server is in the known WX_TOKEN_EXPIRED state a
                    # refresh attempt per call just hammers refreshWeChatToken;
                    # retry at most once per minute and keep the session alive
                    # in between (HTTP runs on the session token anyway).
                    now_ts = time.time()
                    if now_ts - getattr(self, '_wx_refresh_last_attempt', 0.0) < 60:
                        return True
                    self._wx_refresh_last_attempt = now_ts
                    ok2, result = self._refresh_wechat_token(session_tok)
                    if ok2:
                        self.tokens['AccessToken'] = result.get('accessToken', self.tokens.get('AccessToken'))
                        self.tokens['access_token'] = result.get('accessToken', self.tokens.get('access_token'))
                        self._wx_refresh_last_attempt = 0.0
                        self._wx_degraded_announced = False
                        logger.info("AuthManager: WeChat token refreshed via session token (on-demand).")
                        try:
                            from auth.session_supervisor import get_session_supervisor
                            sup = get_session_supervisor()
                            if sup is not None:
                                sup.notify_token_installed()
                        except Exception:
                            pass
                        return True
                    else:
                        err_code = (result or {}).get('code') if isinstance(result, dict) else None
                        err_msg = (result or {}).get('error') if isinstance(result, dict) else str(result)
                        logger.warning(f"AuthManager: WeChat session token refresh failed ({err_code}): {err_msg}")
                        if err_code == 'SESSION_EXPIRED':
                            logger.error("AuthManager: WeChat session expired — please re-scan QR code")
                            self.signed_in = False
                            self._delete_wechat_session_token()
                            try:
                                from auth.session_supervisor import get_session_supervisor
                                sup = get_session_supervisor()
                                if sup is not None:
                                    sup.notify_session_cleared(source="ensure_valid_tokens")
                            except Exception:
                                pass
                            return False
                        # WX_TOKEN_EXPIRED or a transient failure: only the WS
                        # JWT could not be refreshed. The 30-day session token
                        # still authenticates every HTTP GraphQL call
                        # (_http_auth_header swaps it in) AND the WS bridge
                        # (get_auth_token falls back to it), so keep the
                        # session alive instead of logging the user out.
                        # Announce once per degradation episode; this state is
                        # expected, not exceptional.
                        if not getattr(self, '_wx_degraded_announced', False):
                            self._wx_degraded_announced = True
                            logger.warning(
                                "AuthManager: WS-token refresh unavailable "
                                f"({err_code}); staying signed in — HTTP and WS "
                                "continue on the 30-day session token."
                            )
                        else:
                            logger.debug(
                                f"AuthManager: WS-token refresh still unavailable ({err_code})"
                            )
                        return True
                else:
                    logger.warning("AuthManager: Token expired, no WeChat session token available")
                    self.signed_in = False
                    # Mirror the SESSION_EXPIRED branch (line 240-248):
                    # when the session_token is gone, both the credential
                    # cache and the supervisor must observe it so the GUI
                    # can show the re-login banner and downstream callers
                    # (wan_chat, OfflineSyncManager, AppSync) stop using
                    # the stale cached token. Without this notify, wan_chat
                    # keeps getting the same expired token from
                    # get_auth_token(), server 401s every reconnect, and
                    # the WS loop spams 1 ERROR/min indefinitely.
                    try:
                        from auth.session_supervisor import get_session_supervisor
                        sup = get_session_supervisor()
                        if sup is not None:
                            sup.notify_session_cleared(source="ensure_valid_tokens_no_session_token")
                    except Exception:
                        pass
                    return False

            logger.info(f"AuthManager: Refreshing tokens on demand (remaining={remaining}s)")
            result = self.cognito_service.refresh_tokens(refresh_token)
            if not result.get('success'):
                logger.error(f"AuthManager: On-demand token refresh failed: {result.get('error')}")
                self.signed_in = False
                # Mirror the no-session-token branch (above): when refresh
                # itself fails, the credential cache and the supervisor must
                # both observe the loss so the GUI can show the re-login
                # banner and downstream callers (wan_chat, OfflineSyncManager,
                # AppSync) stop using the stale cached token. Without this
                # notify, the IPC keeps returning the same expired token and
                # every cloud call 401s in silence (CLAUDE.md §6 — refresh
                # failure without GUI notification).
                try:
                    from auth.session_supervisor import get_session_supervisor
                    sup = get_session_supervisor()
                    if sup is not None:
                        sup.notify_session_cleared(source="ensure_valid_tokens_refresh_failed")
                except Exception:
                    pass
                return False

            refreshed_tokens = result.get('data') or {}
            # Cognito / CloudBase may rotate the refresh_token on every
            # successful refresh. If the response carries a new one, prefer
            # it over the token we just sent — using the rotated value keeps
            # the session alive past the next refresh cycle (the previous
            # token is single-use for CloudBase WeChat OAuth). Fall back to
            # the input token when the server doesn't echo one back.
            new_refresh_token = refreshed_tokens.get('RefreshToken') or refreshed_tokens.get('refresh_token')
            if new_refresh_token:
                refreshed_tokens['RefreshToken'] = new_refresh_token
            else:
                refreshed_tokens['RefreshToken'] = refresh_token
            self.tokens.update(refreshed_tokens)
            self.signed_in = True
            logger.info("AuthManager: Tokens refreshed successfully on demand")
            return True
        except Exception as e:
            logger.error(f"AuthManager: Failed to ensure valid tokens: {e}")
            return False

    def get_role(self):
        return self.machine_role

    def set_role(self, role):
        self.machine_role = role

    def is_commander(self):
        return self.machine_role in ["Commander", "Commander Only"]

    def get_log_user(self):
        if not self.current_user:
            return ""
        parts = self.current_user.split("@")
        if len(parts) == 2:
            return f"{parts[0]}_{parts[1].replace('.', '_')}"
        return self.current_user

    def get_user_profile(self):
        """Get the current user's profile information."""
        return self.user_profile or {}

    @staticmethod
    def _decode_jwt_payload_unsafe(token: str) -> dict:
        """Decode a JWT payload WITHOUT cryptographic verification.
        Used only as a fallback to extract user identity (email) from an ID token
        that was just received over HTTPS from Cognito's /oauth2/token endpoint.
        """
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            payload_b64 = parts[1]
            # JWT base64url may lack padding
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += '=' * padding
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(payload_bytes)
        except Exception as e:
            logger.warning(f"[_decode_jwt_payload_unsafe] Could not decode JWT payload: {e}")
            return {}

    def _build_profile_from_claims(self, claim_data: dict):
        """Build user_profile dict and email from JWT claim data."""
        email = claim_data.get('email') or claim_data.get('username')

        # Construct name with fallback logic
        name = claim_data.get('name')
        given_name = claim_data.get('given_name', '')
        family_name = claim_data.get('family_name', '')

        # If no name provided, try to construct from given_name/family_name
        if not name and (given_name or family_name):
            # Check for CJK characters to decide on spacing
            has_cjk = any('\u4e00' <= c <= '\u9fff' for c in (given_name + family_name))
            if has_cjk:
                name = f"{family_name}{given_name}"
            else:
                name = f"{given_name} {family_name}".strip()

        # Final fallback: use email username part (before @)
        if not name and email:
            name = email.split('@')[0]

        user_profile = {
            'email': email,
            'name': name or '',
            'given_name': given_name,
            'family_name': family_name,
            'picture': claim_data.get('picture', ''),
            'email_verified': claim_data.get('email_verified', False),
        }
        return user_profile, email

    def _cn_fetch_user_profile(self, access_token):
        """CN-side equivalent of ``_fetch_user_profile``.

        Strategy:
        1. Decode the access_token JWT (no verification — token was just
           received over HTTPS from CloudBase, mirrors Intl's fallback).
           Extract whatever profile fields we can from the claims.
        2. If email is missing, fall back to ``GET /auth/v1/user/me`` and
           merge the response in. ``user_profile`` is the same dict shape
           Intl produces so ``user_handler._build_user_info_response``
           keeps working.

        Returns:
            ``(user_profile_dict, email_or_phone)``
        """
        user_profile: Dict[str, Any] = {}
        email: Optional[str] = None

        # Step 1: unverified JWT decode
        if access_token:
            claims = self._decode_jwt_payload_unsafe(access_token)
            if claims:
                logger.info(f"[_cn_fetch_user_profile] Decoded JWT claims keys: {list(claims.keys())}")
                # CloudBase standard fields: sub, email, phone_number, name, picture
                email = claims.get("email") or claims.get("phone_number")
                # CloudBase WeChat tokens carry an ``openid`` claim like
                # ``openid:AABE7F974D8D3866BD2923A07B62324A9D5CB06D9``.  We
                # extract it into the profile so callers can use it as a
                # *real* per-user identifier.  Without this every WeChat
                # login collapses onto the fallback ``wechat_user@local``
                # string, which causes the keyring entry for the previous
                # WeChat user to be silently overwritten by the next login.
                openid_claim = claims.get("openid") or ""
                user_profile = {
                    "email": claims.get("email", ""),
                    "phone": claims.get("phone_number", ""),
                    "name": (
                        claims.get("name")
                        or claims.get("nickname")
                        or (email.split("@")[0] if email and "@" in email else "")
                    ),
                    "given_name": claims.get("given_name", ""),
                    "family_name": claims.get("family_name", ""),
                    "picture": claims.get("picture", "") or claims.get("avatar_url", ""),
                    "email_verified": bool(claims.get("email_verified", False)),
                    "sub": claims.get("sub", ""),
                    "openid": openid_claim,
                }
            else:
                logger.warning("[_cn_fetch_user_profile] Could not decode access_token JWT")

        # Step 2: /user/me enrichment (only if we don't already have an email)
        if not email and access_token and self.cognito_service is not None:
            try:
                ui_result = self.cognito_service.get_userinfo(access_token)
                if ui_result.get("success") and isinstance(ui_result.get("data"), dict):
                    ui = ui_result["data"]
                    logger.info(f"[_cn_fetch_user_profile] /user/me keys: {list(ui.keys())}")
                    if not user_profile.get("email"):
                        user_profile["email"] = ui.get("email", "")
                    if not user_profile.get("phone"):
                        user_profile["phone"] = ui.get("phone_number", "")
                    if not user_profile.get("name"):
                        user_profile["name"] = (
                            ui.get("name")
                            or ui.get("username")
                            or ui.get("nickname")
                            or ""
                        )
                    if not user_profile.get("picture"):
                        user_profile["picture"] = ui.get("picture", "") or ui.get("avatar_url", "")
                    if not user_profile.get("sub"):
                        user_profile["sub"] = ui.get("sub") or ui.get("user_id") or ""
                    email = user_profile.get("email") or user_profile.get("phone")
                else:
                    logger.warning(
                        f"[_cn_fetch_user_profile] /user/me failed: "
                        f"{ui_result.get('error')}"
                    )
            except Exception as e:
                logger.warning(f"[_cn_fetch_user_profile] /user/me error: {e}")

        logger.info(
            f"[_cn_fetch_user_profile] Returning user_profile={user_profile}, "
            f"email={email}"
        )
        return user_profile, email

    def _fetch_user_profile(self, access_token, id_token=None):
        """
        Helper method to fetch and construct the user profile from ID token claims
        and/or the UserInfo endpoint.
        """
        # CN build — CloudBase JWTs are decoded unverified (the token was
        # just received over HTTPS from CloudBase seconds ago, same trust
        # argument as the Intl unverified-decode fallback). CN doesn't
        # issue an IdToken, so we decode access_token directly. If the
        # claim payload doesn't carry an email/phone, we fall back to
        # /auth/v1/user/me for enrichment.
        if self._is_cn:
            return self._cn_fetch_user_profile(access_token)

        user_profile = {}
        email = None

        # 1. Try extracting from ID Token via verified decode
        if id_token:
            claims = self.cognito_service.verify_token(id_token, 'id')
            logger.debug(f"[_fetch_user_profile] verify_token result: success={claims.get('success')}, error={claims.get('error')}")
            if claims.get('success'):
                claim_data = claims['data']
                logger.debug(f"ID Token Claims: {claim_data}")
                user_profile, email = self._build_profile_from_claims(claim_data)
                logger.info(f"[_fetch_user_profile] Constructed user_profile from verified token: {user_profile}")
            else:
                logger.warning(f"[_fetch_user_profile] verify_token failed: {claims.get('error')}")
                # 1b. FALLBACK: decode JWT payload without verification.
                # This is safe because the token was just received over HTTPS directly
                # from Cognito's /oauth2/token endpoint seconds ago.
                # Google federated ID tokens may fail verify_token due to missing
                # 'token_use' claim or JWKS fetch issues in slow networks.
                logger.info("[_fetch_user_profile] Attempting unverified JWT decode fallback for email extraction...")
                fallback_claims = self._decode_jwt_payload_unsafe(id_token)
                if fallback_claims:
                    logger.info(f"[_fetch_user_profile] Fallback claims keys: {list(fallback_claims.keys())}")
                    user_profile, email = self._build_profile_from_claims(fallback_claims)
                    if email:
                        logger.info(f"[_fetch_user_profile] Extracted email via fallback: {email}")
                    else:
                        logger.warning("[_fetch_user_profile] Fallback decode succeeded but no email found in claims")

        # 2. OPTIMIZATION: Skip UserInfo endpoint to avoid additional 90+ second network delay
        # ID Token already contains all necessary user information (email, name, given_name, family_name, picture)
        # The UserInfo endpoint (/oauth2/userInfo) requires another HTTPS request to AWS Cognito
        # In slow network conditions (e.g., China to us-east-1), this adds ~90s delay
        # By relying solely on ID Token claims, we reduce login time from ~180s to ~92s
        
        logger.info(f"[AuthManager] User profile fetched from ID Token (skipped UserInfo endpoint for performance)")
        logger.info(f"[_fetch_user_profile] Returning user_profile: {user_profile}, email: {email}")

        return user_profile, email

    def login(self, username, password, role):
        """Handle username/password login logic."""
        try:
            self.machine_role = role
            self.current_user = username

            result = self.cognito_service.login(username, password)

            if result['success']:
                self.tokens = result['data']
                self.signed_in = True
                
                # Fetch user profile using AccessToken
                access_token = self.tokens.get('AccessToken') or self.tokens.get('access_token')
                # Password login typically doesn't return ID token in the same way or we rely on access token
                id_token = self.tokens.get('IdToken') or self.tokens.get('id_token')
                
                self.user_profile, fetched_email = self._fetch_user_profile(access_token, id_token)
                
                # If we got a valid email from the profile, update current_user
                if fetched_email and '@' in fetched_email:
                    username = fetched_email
                
                logger.info(f"Password Login Final Profile: {self.user_profile}")
                self.current_user = username

                # Persist username/password and refresh token
                self._update_saved_login_info(username, password, role)  # Save credentials on success
                rt = (self.tokens.get('RefreshToken') or self.tokens.get('refresh_token'))
                if rt:
                    self._store_refresh_token(username, rt)
                else:
                    logger.error("auth manager refresh token is None")
                self.start_refresh_task()  # Start the background refresh task
                # Notify SessionSupervisor so the WS auth-failure latch is cleared.
                # Without this, any WS subscription started after login would bail
                # with "Session already flagged as auth-failed" if a previous session
                # had previously set the latch.
                try:
                    from auth.session_supervisor import get_session_supervisor
                    sup = get_session_supervisor()
                    if sup:
                        sup.notify_token_installed()
                except Exception as e:
                    logger.debug(f"[AuthManager] notify_token_installed skipped: {e}")
                logger.info(f"AuthManager: Login successful for {username}")
                return {'success': True}
            else:
                self.tokens = None
                self.signed_in = False
                logger.error(f"AuthManager: Login failed for {username}: {result['error']}")
                return {'success': False, 'error': result['error']}
        except Exception as e:
            logger.error(f"AuthManager: Unexpected error during login: {e}")
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}

    def google_login(self, role):
        """Orchestrates the entire Google login flow using a local callback server with PKCE and persists refresh token."""
        try:
            self.machine_role = role
            self.last_login_error = None

            # Step 1: Start a temporary local HTTP server to listen for the callback.
            callback_url = AuthConfig.GOOGLE.CALLBACK_URL
            with LocalOAuthServer(url=callback_url, timeout=300) as server:
                redirect_uri = server.get_redirect_uri()

                # Step 2: Include PKCE parameters in the Cognito Hosted UI URL.
                pkce_params = server.get_pkce_params()
                result = self.cognito_service.get_google_login_url(redirect_uri, pkce_params)
                if not result['success']:
                    raise Exception(f"Could not get Google login URL: {result.get('error')}")

                # Step 3: Open the URL in the user's default browser and wait for callback.
                webbrowser.open(result['data']['url'])
                logger.info("AuthManager: Browser opened for Google auth. Waiting for callback...")

                # Step 4: Wait for the local server to capture the callback request from Cognito.
                callback_result = server.wait_for_callback()
                if not callback_result.get('success'):
                    raise Exception(f"Google login failed during callback: {callback_result.get('error')}")

                # Step 5: Extract the one-time authorization code from the callback result.
                auth_code = callback_result.get('auth_code')
                if not auth_code:
                    raise Exception("Authorization code not found in callback.")

                # Step 6: Exchange the code for tokens, providing the PKCE code_verifier.
                logger.info("AuthManager: Authorization code received. Exchanging for tokens...")
                code_verifier = server.get_code_verifier()
                token_result = self.cognito_service.exchange_code_for_tokens(auth_code, redirect_uri, code_verifier)
                if not token_result.get('success'):
                    raise Exception(f"Failed to exchange code for tokens: {token_result.get('error')}")

                # Step 7: Normalize token keys and persist refresh token.
                tokens = token_result['data'] or {}
                # Normalize refresh token key to match refresh loop expectations
                if 'refresh_token' in tokens and 'RefreshToken' not in tokens:
                    tokens['RefreshToken'] = tokens['refresh_token']
                self.tokens = tokens
                self.signed_in = True

                # Reuse the helper to fetch user profile
                access_token = self.tokens.get('access_token') or self.tokens.get('AccessToken')
                id_token = self.tokens.get('id_token') or self.tokens.get('IdToken')
                
                logger.info(f"[google_login] Token keys received: {list(tokens.keys())}")
                logger.info(f"[google_login] id_token present: {bool(id_token)}, access_token present: {bool(access_token)}")
                
                self.user_profile, fetched_email = self._fetch_user_profile(access_token, id_token)
                
                # Extra fallback: if _fetch_user_profile couldn't get an email,
                # try decoding the access_token payload (Cognito access tokens
                # contain 'username' which for Google-federated users is often the email)
                if not fetched_email and access_token:
                    logger.info("[google_login] No email from id_token, trying access_token payload...")
                    at_claims = self._decode_jwt_payload_unsafe(access_token)
                    if at_claims:
                        fetched_email = at_claims.get('email') or at_claims.get('username')
                        if fetched_email:
                            logger.info(f"[google_login] Extracted email from access_token: {fetched_email}")
                            self.user_profile['email'] = fetched_email
                
                logger.info(f"Final User Profile: {self.user_profile}")
                self.current_user = fetched_email or self._get_saved_username() or "unknown@local"

                # Save signed-in user and refresh token for session persistence
                if self.current_user:
                    # Use ``_update_saved_login_info`` (instead of plain
                    # ``_set_saved_username``) so we also persist
                    # ``login_type='google'`` — otherwise the next
                    # ``get_saved_login_info`` returns ``login_type=None``
                    # and the frontend treats this as a password login,
                    # which would auto-fill the Google email into the
                    # username field without a password (an empty-password
                    # 401 + browser autofill noise). See CLAUDE.md §6
                    # ("Backend-side fixes for backend-side errors") —
                    # login_type metadata must follow the same code path
                    # for all providers.
                    self._update_saved_login_info(
                        username=self.current_user,
                        password="",  # Google OAuth doesn't have a password
                        role=role,
                        login_type="google",
                    )
                refresh_token = self.tokens.get('RefreshToken')
                if refresh_token and self.current_user:
                    self._store_refresh_token(self.current_user, refresh_token)
                else:
                    logger.error("auth manager refresh token is None")
                # Step 8: Start the background token refresh task to maintain a long-lived session.
                self.start_refresh_task()
                # Notify SessionSupervisor so the WS auth-failure latch is cleared.
                try:
                    from auth.session_supervisor import get_session_supervisor
                    sup = get_session_supervisor()
                    if sup:
                        sup.notify_token_installed()
                except Exception as e:
                    logger.debug(f"[AuthManager] notify_token_installed skipped: {e}")
                logger.info(f"AuthManager: Google login successful for {self.current_user}")
                return {'success': True}

        except Exception as e:
            logger.error(f"AuthManager: An unexpected error occurred during Google login: {e}")
            logger.error(traceback.format_exc())
            self.last_login_error = str(e)
            # Surface PortOccupiedError details so the IPC layer can offer a
            # "force-close other instance and retry" UX instead of just
            # printing the error. Lazy-import to avoid pulling the oauth
            # module at auth_manager import time.
            try:
                from auth.oauth.local_oauth_server import PortOccupiedError as _POE
                if isinstance(e, _POE):
                    self.last_login_error_details = e.to_dict()
                    self.last_login_error_details["kind"] = "port_occupied"
                    return {
                        'success': False,
                        'error': str(e),
                        'error_kind': 'port_occupied',
                        'error_details': self.last_login_error_details,
                    }
            except Exception:
                pass
            return {'success': False, 'error': str(e)}


            return {'success': False, 'error': str(e)}


    def sign_up(self, username, password):
        """Handle user signup logic."""
        try:
            result = self.cognito_service.sign_up(username, password)
            if result['success']:
                logger.info(f"AuthManager: Signup successful for {username}")
            else:
                logger.error(f"AuthManager: Signup failed for {username}: {result['error']}")
            return result
        except Exception as e:
            logger.error(f"AuthManager: Unexpected error during signup: {e}")
            return {'success': False, 'error': str(e)}

    def forgot_password(self, username):
        """Handle forgot password logic."""
        try:
            result = self.cognito_service.forgot_password(username)
            if result['success']:
                logger.info(f"AuthManager: Forgot password code sent for {username}")
            else:
                logger.error(f"AuthManager: Forgot password failed for {username}: {result['error']}")
            return result
        except Exception as e:
            logger.error(f"AuthManager: Unexpected error during forgot password: {e}")
            return {'success': False, 'error': str(e)}

    def confirm_forgot_password(self, username, code, new_password):
        """Handle confirm forgot password logic."""
        try:
            result = self.cognito_service.confirm_forgot_password(username, code, new_password)
            if result['success']:
                logger.info(f"AuthManager: Password reset successful for {username}")
            else:
                logger.error(f"AuthManager: Password reset failed for {username}: {result['error']}")
            return result
        except Exception as e:
            logger.error(f"AuthManager: Unexpected error during password reset: {e}")
            return {'success': False, 'error': str(e)}

    def logout(self):
        # Delete persisted refresh token for the saved user
        try:
            saved_username = self.current_user or self._get_saved_username()
            if saved_username:
                self._delete_refresh_token(saved_username)
        except Exception as e:
            logger.warning(f"AuthManager: Failed to delete stored refresh token on logout: {e}")

        # Clear IPC registry system ready cache
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            IPCHandlerRegistry.clear_system_ready_cache()
            logger.debug("AuthManager: Cleared IPC registry system ready cache on logout")
        except Exception as e:
            logger.error(f"AuthManager: Error clearing IPC registry cache: {e}")

        self.stop_refresh_task()  # Stop the background refresh task
        self.tokens = None
        self.current_user = None
        self.signed_in = False
        logger.info("AuthManager: User logged out.")
        return True

    # ============================================================
    # CN-specific entry points (only used when ECAN_APP_ID=cn)
    # ============================================================
    # These mirror the Intl ``cognito_service.*`` shape so the IPC
    # layer (``cloudbase_handler.py``, ``user_handler.handle_wechat_login``)
    # and the post-login pipeline (refresh task, profile fetch,
    # credential persistence) work without any per-app branching in
    # the consumer.

    def _persist_cn_login(self, *, username: str, password: Optional[str],
                          role: str, tokens: Dict[str, Any]) -> None:
        """Mirror ``_update_saved_login_info`` + ``_store_refresh_token``
        for the CN build.

        On Intl we save to ``ecan_auth`` (password) and the configured
        chunked refresh keyring service. On CN we save to
        ``ecan_cloudbase_auth`` (password) and ``ecan_cloudbase_refresh``
        — separate keyring services so both apps can coexist during dev.
        """
        try:
            self._update_saved_login_info(username, password or "", role)
        except Exception as e:
            logger.warning(f"[AuthManager] CN save info failed: {e}")

        rt = tokens.get("RefreshToken") or tokens.get("refresh_token")
        if rt:
            try:
                keyring.set_password("ecan_cloudbase_refresh", username, rt)
            except Exception as e:
                logger.warning(f"[AuthManager] CN refresh-token save failed: {e}")

    def complete_login_from_provider(self, *, access_token: str,
                                      refresh_token: Optional[str],
                                      expires_in: Optional[int] = None,
                                      user_identifier: str,
                                      role: str = "Commander",
                                      user_profile: Optional[Dict[str, Any]] = None,
                                      password: str = "",
                                      login_type: Optional[str] = None) -> Dict[str, Any]:
        """Install already-issued tokens into the session, without re-calling any auth backend.

        Use this when the upstream provider (CloudBase OTP / WeChat OAuth / etc.)
        has already returned tokens — we just need to wire them into the same
        ``self.tokens / signed_in / current_user / user_profile`` state that
        ``login()`` would have set, so that the rest of the post-login flow
        (``Login.handleLogin`` → ``MainWindow`` launch → ``token_manager`` →
        ``onboarding``) runs identically on Intl and CN.

        Args:
            access_token:     JWT access_token from the provider
            refresh_token:    refresh token (may be None for some flows)
            expires_in:       token TTL in seconds (defaults to 7200 = 2 h)
            user_identifier:  email / phone / uuid to use as ``current_user``
            role:             machine role, defaults to ``"Commander"``
            user_profile:     pre-fetched profile dict; if missing we will
                              enrich via ``_cn_fetch_user_profile`` for CN,
                              and leave ``self.user_profile`` empty for Intl
                              (the Intl flow doesn't reach this method).

        Returns:
            ``{"success": True, "data": {"user_info": ..., "tokens": ...}}``
            on success, ``{"success": False, "error": ...}`` otherwise.
        """
        try:
            expires = int(expires_in) if expires_in else 7200
            tokens: Dict[str, Any] = {
                "AccessToken": access_token,
                "IdToken": None,
                "RefreshToken": refresh_token,
                "ExpiresIn": expires,
                "TokenType": "Bearer",
            }

            self.machine_role = role
            self.tokens = tokens
            self.signed_in = True
            self.current_user = user_identifier

            # Profile enrichment: prefer the caller-supplied profile, then
            # fall back to /auth/v1/user/me on CN. Intl callers should pass a
            # complete ``user_profile`` because we don't want to call Cognito
            # get_userinfo from here (the Intl flow that calls this method
            # already has the user info from Cognito).
            if user_profile:
                self.user_profile = dict(user_profile)
                # Even with a caller-supplied profile, on CN we want the
                # real openid (extracted from the access_token JWT by
                # ``_cn_fetch_user_profile``) to drive ``current_user``.
                # Without this every WeChat login collapses onto the
                # caller's ``user_identifier`` and silently overwrites
                # the previous WeChat user's keyring / data-dir entries.
                if self._is_cn and access_token:
                    try:
                        _, fetched_claim = self._cn_fetch_user_profile(access_token)
                        cn_profile = (self._cn_fetch_user_profile.__self__.user_profile
                                      if hasattr(self._cn_fetch_user_profile, "__self__")
                                      else {})
                    except Exception:
                        fetched_claim, cn_profile = None, {}
                    openid_claim = cn_profile.get("openid") if isinstance(cn_profile, dict) else None
                    if openid_claim:
                        self.current_user = f"wechat_{openid_claim}@local"
                    elif fetched_claim:
                        self.current_user = fetched_claim
            elif self._is_cn:
                self.user_profile, fetched = self._cn_fetch_user_profile(access_token)
                openid_claim = (self.user_profile or {}).get("openid") or ""
                if openid_claim:
                    self.current_user = f"wechat_{openid_claim}@local"
                elif fetched:
                    self.current_user = fetched
                # else: keep user_identifier as a last-resort fallback
                # (e.g., phone-number-based login where neither openid
                # nor email is present in the JWT claims)
            else:
                self.user_profile = {"username": user_identifier, "email": user_identifier}

            # Persist identity + refresh token so try_restore_session works
            # on next launch AND so the frontend's get_last_login reads the
            # correct user next time. We use ``_update_saved_login_info``
            # (the same path Intl ``auth_manager.login`` takes) so the
            # resulting ``uli.json`` matches the Intl format exactly
            # (``{"user": ..., "machine_role": ...}``).
            #
            # ``_update_saved_login_info`` also writes the password to
            # keyring (``ecan_auth`` for Intl / ``ecan_cloudbase_auth`` for
            # CN) — that's intentional, mirroring Intl's password-login
            # behavior. For OTP / phone / WeChat flows the password is
            # empty, which keyring happily accepts.
            #
            # login_type gating (fix for "邮箱输入框被填充成 wechat id / 手机号"):
            # we explicitly persist `login_type` so the next
            # ``get_saved_login_info`` can filter out username/password for
            # non-password logins. Falls back to ``user_profile.login_type``
            # if the caller didn't pass it explicitly (preserves the
            # ``complete_login_from_provider`` call shape used by the
            # cloudbase_handler IPC).
            effective_login_type = (
                login_type
                or (user_profile.get("login_type") if user_profile else None)
            )
            # macOS Keychain ``set_password`` can take 1-12s on cold start
            # (Aug-20 trace measured 11.3s, blocking the whole login HTTP
            # roundtrip). The persistence below is for the NEXT launch only —
            # the current session's tokens are already in ``self.tokens``
            # above. Run it on a daemon thread and return immediately so the
            # frontend isn't gated on Keychain latency. The thread holds its
            # own copies (str / bool / AuthManager ref) and never touches
            # mutable shared state.
            persist_username = self.current_user
            persist_role = role
            persist_password = password or ""
            persist_refresh_token = refresh_token
            persist_is_cn = self._is_cn
            persist_effective_login_type = effective_login_type
            auth_manager_ref = self

            def _persist_credentials():
                try:
                    auth_manager_ref._update_saved_login_info(
                        username=persist_username,
                        password=persist_password,
                        role=persist_role,
                        login_type=persist_effective_login_type,
                    )
                except Exception as e:
                    logger.warning(
                        f"[AuthManager] complete_login: background save login info failed: {e}"
                    )
                if persist_refresh_token:
                    try:
                        if persist_is_cn:
                            keyring.set_password(
                                "ecan_cloudbase_refresh",
                                persist_username,
                                persist_refresh_token,
                            )
                        else:
                            auth_manager_ref._store_refresh_token(
                                persist_username, persist_refresh_token
                            )
                    except Exception as e:
                        logger.warning(
                            f"[AuthManager] complete_login: background refresh-token save failed: {e}"
                        )
                        # CN keyring fallback: encrypted file store. See
                        # ``wechat_login`` for the rationale — without this
                        # the user would have to re-scan the QR on every
                        # restart when macOS Keychain misbehaves.
                        if persist_is_cn:
                            try:
                                auth_manager_ref._store_refresh_token_file(
                                    persist_username, persist_refresh_token,
                                )
                                logger.info(
                                    "[AuthManager] complete_login: background "
                                    "CN refresh_token persisted via file fallback"
                                )
                            except Exception as file_e:
                                logger.warning(
                                    f"[AuthManager] complete_login: background "
                                    f"CN refresh_token file fallback failed: {file_e}"
                                )

            threading.Thread(
                target=_persist_credentials,
                name="persist-login-credentials",
                daemon=True,
            ).start()

            # Start the background refresh loop. Same fallback as
            # ``try_restore_session`` — wrap in try so a missing event loop
            # during IPC dispatch doesn't take the whole login down.
            try:
                self.start_refresh_task()
            except Exception as e:
                logger.warning(f"[AuthManager] complete_login: start_refresh_task deferred: {e}")

            # Wire SessionSupervisor so it knows a fresh token was just installed.
            # This resets the cache-lag grace window (fresh_token_installed_at) AND
            # fires on_session_refreshed → _auth_failure_event.clear() — so WS
            # reconnect loops can resume after a WeChat re-login.
            # Same pattern as ``try_restore_session`` / ``try_restore_cloudbase_session``.
            try:
                from auth.session_supervisor import get_session_supervisor
                sup = get_session_supervisor()
                if sup:
                    sup.notify_token_installed()
            except Exception as e:
                logger.debug(f"[AuthManager] notify_token_installed skipped: {e}")

            # CN HTTP session token.  The CloudBase access token is suitable
            # for provider/WS authentication, but the SCF GraphQL gate expects
            # an eCan-minted bearer token.  WeChat keeps its legacy exchange;
            # phone/password/email use mintHttpSessionToken.
            # Detected by: CN env + access_token present + NO refresh_token
            # (CloudBase WeChat OAuth doesn't return one) + the access_token
            # is a JWT carrying an ``openid`` claim (set in user_profile above).
            # Called AFTER notify_token_installed so the supervisor sees the
            # fresh access_token in self.tokens BEFORE we register the
            # session token. Idempotent: re-running with the same access_token
            # just refreshes the DB row (upsert on openid).
            try:
                self._finalize_http_session_token()
            except Exception as e:
                logger.warning(f"[AuthManager] HTTP session finalize skipped: {e}")

            logger.info(f"[AuthManager] complete_login_from_provider OK for {self.current_user}")
            return {
                "success": True,
                "data": {
                    "user_info": self.user_profile,
                    "tokens": tokens,
                    "user_identifier": self.current_user,
                },
            }
        except Exception as e:
            logger.error(f"[AuthManager] complete_login_from_provider error: {e}")
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}

    def sign_up_with_otp(self, *, phone_number: Optional[str] = None,
                         email: Optional[str] = None,
                         verification_token: str,
                         username: Optional[str] = None,
                         password: Optional[str] = None,
                         role: str = "Commander") -> Dict[str, Any]:
        """Sign up via email/phone OTP — CN-only entry point.

        Caller (IPC handler) is responsible for:
          1. send_verification_code(phone|email)  → ``verification_id``
          2. verify_verification_code(verification_id, code) → ``verification_token``
          3. THIS method

        On success the user is auto-logged-in and the session is
        persisted just like the Intl ``login()`` path.
        """
        if not self._is_cn or self.cognito_service is None:
            return {"success": False, "error": "sign_up_with_otp is CN-only"}

        result = self.cognito_service.sign_up_with_otp(
            phone_number=phone_number,
            email=email,
            verification_token=verification_token,
            username=username,
            password=password,
        )
        if not result.get("success"):
            return result

        tokens = result["data"] or {}
        self.tokens = tokens
        self.signed_in = True
        access_token = tokens.get("AccessToken") or tokens.get("access_token")
        self.user_profile, fetched = self._cn_fetch_user_profile(access_token)
        ident = fetched or username or email or phone_number or "unknown"
        self.current_user = ident

        self._persist_cn_login(
            username=ident, password=password, role=role, tokens=tokens,
        )
        self.start_refresh_task()
        try:
            from auth.session_supervisor import get_session_supervisor
            sup = get_session_supervisor()
            if sup:
                sup.notify_token_installed()
        except Exception:
            pass
        logger.info(f"[AuthManager] CN OTP signup successful for {ident}")
        return {"success": True, "data": {"user_info": self.user_profile}}

    def phone_login_with_otp(self, *, phone_number: str,
                             verification_token: str,
                             role: str = "Commander") -> Dict[str, Any]:
        """Phone OTP login — CN-only."""
        if not self._is_cn or self.cognito_service is None:
            return {"success": False, "error": "phone_login_with_otp is CN-only"}

        # Reuse the underlying service directly to avoid double-normalization
        # through the adapter for this entry point.
        from auth.tencent.cloudbase_auth import get_cloudbase_service
        svc = get_cloudbase_service()
        result = svc.sign_in_with_otp(
            phone_number=phone_number,
            verification_token=verification_token,
        )
        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "error_code": result.error_code,
            }

        # Normalize to Cognito shape and persist
        from auth.tencent.cloudbase_adapter import _normalize_tokens
        tokens = _normalize_tokens(result.data)
        self.tokens = tokens
        self.signed_in = True
        access_token = tokens.get("AccessToken")
        self.user_profile, fetched = self._cn_fetch_user_profile(access_token)
        # Use fetched email/phone as-is if CloudBase returns one; otherwise
        # tag the raw phone_number with a synthetic domain so downstream code
        # (which assumes "<local>@<domain>" for log_user / data-dir naming)
        # produces a per-account directory instead of collapsing every phone
        # login into the shared "unknown_local" dir.
        ident = fetched or (phone_number if "@" in (phone_number or "") else f"{phone_number}@phone.local")
        self.current_user = ident

        self._persist_cn_login(
            username=ident, password=None, role=role, tokens=tokens,
        )
        self.start_refresh_task()
        try:
            from auth.session_supervisor import get_session_supervisor
            sup = get_session_supervisor()
            if sup:
                sup.notify_token_installed()
        except Exception:
            pass
        logger.info(f"[AuthManager] CN phone OTP login successful for {ident}")
        return {"success": True, "data": {"user_info": self.user_profile}}

    def email_login_with_otp(self, *, email: str,
                             verification_token: str,
                             role: str = "Commander") -> Dict[str, Any]:
        """Email OTP login — CN-only."""
        if not self._is_cn or self.cognito_service is None:
            return {"success": False, "error": "email_login_with_otp is CN-only"}

        from auth.tencent.cloudbase_auth import get_cloudbase_service
        svc = get_cloudbase_service()
        result = svc.sign_in_with_otp(email=email, verification_token=verification_token)
        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "error_code": result.error_code,
            }

        from auth.tencent.cloudbase_adapter import _normalize_tokens
        tokens = _normalize_tokens(result.data)
        self.tokens = tokens
        self.signed_in = True
        access_token = tokens.get("AccessToken")
        self.user_profile, fetched = self._cn_fetch_user_profile(access_token)
        ident = fetched or email
        self.current_user = ident

        self._persist_cn_login(
            username=ident, password=None, role=role, tokens=tokens,
        )
        self.start_refresh_task()
        try:
            from auth.session_supervisor import get_session_supervisor
            sup = get_session_supervisor()
            if sup:
                sup.notify_token_installed()
        except Exception:
            pass
        logger.info(f"[AuthManager] CN email OTP login successful for {ident}")
        return {"success": True, "data": {"user_info": self.user_profile}}

    def reset_password_with_otp(self, *, phone_number: Optional[str] = None,
                                email: Optional[str] = None,
                                verification_id: str,
                                verification_code: str,
                                new_password: str) -> Dict[str, Any]:
        """Reset password via email/phone OTP — CN-only."""
        if not self._is_cn or self.cognito_service is None:
            return {"success": False, "error": "reset_password_with_otp is CN-only"}

        result = self.cognito_service.reset_password_with_otp(
            phone_number=phone_number,
            email=email,
            verification_id=verification_id,
            verification_code=verification_code,
            new_password=new_password,
        )
        return result

    def wechat_login(self, role: str = "Commander") -> Dict[str, Any]:
        """WeChat Open Platform login (CN-only).

        Mirrors ``google_login()`` step-for-step:

        1. Start ``LocalOAuthServer`` on the configured callback URL.
        2. Ask CloudBase for a WeChat Open Platform authorization URI
           via ``GET /auth/v1/provider/uri?provider_id=wx_open``.
           Pass the local ``redirect_uri`` so CloudBase knows where the
           browser should land after WeChat confirms.
        3. Open the URI in the system browser.
        4. Wait for the local server to capture the callback.
        5. Forward the captured ``code`` to ``sign_in_with_provider``
           (or equivalent) to exchange it for tokens.
        6. Persist tokens + profile, start refresh loop.

        IMPORTANT: this method blocks while waiting for the browser
        callback (max ~300s). Callers (IPC ``handle_wechat_login``)
        already run it in a background thread.
        """
        logger.info("===== [wechat_login] STARTING =====")
        if not self._is_cn or self.cognito_service is None:
            return {"success": False, "error": "wechat_login is CN-only"}

        # Defensive: bail early if WeChat isn't configured on this env.
        try:
            cb_cfg = self.cognito_service.config
            if hasattr(cb_cfg, "is_wechat_configured") and not cb_cfg.is_wechat_configured():
                return {"success": False, "error": "WeChat login not configured (APP_ID missing)"}
        except Exception:
            pass

        self.machine_role = role
        self.last_login_error = None

        # CN auth_config.yml does NOT declare WECHAT.CALLBACK_URL today
        # — fall back to the same port Google uses (9382) and let the
        # local server derive the redirect URI.
        callback_url = "http://localhost:9382/callback"

        try:
            with LocalOAuthServer(url=callback_url, timeout=300) as server:
                redirect_uri = server.get_redirect_uri()

                # Step 1: ask CloudBase for the WeChat authorization URI.
                # The provider_id is selected inside the adapter based on
                # apps/cn/config/auth_config.yml WECHAT.LOGIN_TYPE.
                uri_result = self.cognito_service.get_wechat_qrcode_uri(
                    state=f"wechat_{uuid.uuid4().hex[:16]}",
                    redirect_uri=redirect_uri,
                )
                if not uri_result.get("success"):
                    raise Exception(
                        f"Could not generate WeChat auth URL: "
                        f"{uri_result.get('error')}"
                    )

                wechat_uri = (uri_result.get("data") or {}).get("uri")
                if not wechat_uri:
                    raise Exception("CloudBase returned empty WeChat auth URI")

                # Step 2: open browser, wait for callback.
                webbrowser.open(wechat_uri)
                logger.info("[AuthManager.wechat_login] Browser opened, waiting for WeChat callback")
                callback_result = server.wait_for_callback()
                if not callback_result.get("success"):
                    raise Exception(
                        f"WeChat callback failed: {callback_result.get('error')}"
                    )
                auth_code = callback_result.get("auth_code")
                if not auth_code:
                    raise Exception("No authorization code in WeChat callback")

                # Step 3: exchange code for tokens.
                logger.info("[AuthManager.wechat_login] Received WeChat code, exchanging...")
                token_result = self._exchange_wechat_code(auth_code, redirect_uri)
                if not token_result.get("success"):
                    raise Exception(
                        f"WeChat token exchange failed: {token_result.get('error')}"
                    )

                tokens = token_result["data"] or {}
                logger.info(f"[AuthManager.wechat_login] Token keys: {list(tokens.keys())}")
                # Diagnose: is CloudBase actually returning a refresh_token?
                rt_keys = [k for k in tokens.keys() if 'refresh' in k.lower() or 'Refresh' in k]
                logger.info(f"[AuthManager.wechat_login] Refresh-related keys: {rt_keys}")
                if rt_keys:
                    for k in rt_keys:
                        logger.info(f"[AuthManager.wechat_login]   {k}: {str(tokens.get(k))[:80]}")
                if "access_token" in tokens:
                    # Log the first 50 chars of access_token to diagnose format issues
                    at = tokens["access_token"]
                    logger.info(f"[AuthManager.wechat_login] access_token[:50]: {at[:50] if len(at) > 50 else at}")
                    logger.info(f"[AuthManager.wechat_login] access_token contains '@@': {'@@' in at}")
                if "AccessToken" in tokens:
                    at = tokens["AccessToken"]
                    logger.info(f"[AuthManager.wechat_login] AccessToken[:50]: {at[:50] if len(at) > 50 else at}")
                    logger.info(f"[AuthManager.wechat_login] AccessToken contains '@@': {'@@' in at}")
                if "refresh_token" in tokens and "RefreshToken" not in tokens:
                    tokens["RefreshToken"] = tokens["refresh_token"]
                self.tokens = tokens
                self.signed_in = True

                access_token = tokens.get("AccessToken") or tokens.get("access_token")
                self.user_profile, fetched = self._cn_fetch_user_profile(access_token)
                # WeChat on CloudBase returns no password — we don't have
                # one to keyring, but we still persist refresh_token via
                # the CN-specific keyring service.
                # Use fetched email if CloudBase returns one; otherwise
                # fall back to the **real** WeChat openid extracted from
                # the access_token JWT (``_cn_fetch_user_profile`` populates
                # ``user_profile["openid"]``).  Without the openid fallback
                # every WeChat login would collapse onto the synthetic
                # ``wechat_user@local`` string, silently overwriting
                # the previous user's keyring / data-dir entries on the
                # next login.  See runlog 2026-08-14 19:02 — that bug caused
                # ``try_restore_cloudbase_session`` to lose refresh tokens
                # across WeChat users.
                openid = (self.user_profile or {}).get("openid") or ""
                ident = (
                    fetched
                    or (self.user_profile.get("email") if self.user_profile else "")
                    or (self.user_profile.get("phone") if self.user_profile else "")
                    or (f"wechat_{openid}@local" if openid else "")
                    or "wechat_user@local"
                )
                self.current_user = ident
                if self.current_user:
                    # Use ``_update_saved_login_info`` so we also persist
                    # ``login_type='wechat'`` — otherwise the next
                    # ``get_saved_login_info`` returns ``login_type=None``
                    # and the frontend treats this as a password login,
                    # auto-filling the synthetic WeChat identifier
                    # (``wechat_xxx@local``) into the email field
                    # on the login page. See CLAUDE.md §6 ("Backend-side
                    # fixes for backend-side errors") and the
                    # ``google_login()`` parallel below for the rationale.
                    self._update_saved_login_info(
                        username=self.current_user,
                        password="",  # WeChat OAuth doesn't have a password
                        role=role,
                        login_type="wechat",
                    )
                rt = tokens.get("RefreshToken") or tokens.get("refresh_token")
                if rt and self.current_user:
                    try:
                        keyring.set_password(
                            "ecan_cloudbase_refresh", self.current_user, rt
                        )
                    except Exception as e:
                        # Keychain can fail on macOS for a number of
                        # reasons (-25244 user-denied, locked keychain,
                        # ``@`` in the service key, etc.).  Mirror Intl's
                        # ``_store_refresh_token`` behaviour: write the
                        # token to the encrypted file fallback so a
                        # restart can still recover the session via
                        # ``try_restore_cloudbase_session``.
                        logger.warning(
                            f"[AuthManager.wechat_login] refresh_token keyring save failed: {e}"
                        )
                        try:
                            self._store_refresh_token_file(self.current_user, rt)
                            logger.info(
                                "[AuthManager.wechat_login] refresh_token "
                                "persisted via file fallback"
                            )
                        except Exception as file_e:
                            logger.warning(
                                f"[AuthManager.wechat_login] refresh_token "
                                f"file fallback also failed: {file_e}"
                            )

                # Single canonical session-token entry point — same path
                # used by complete_login_from_provider for the H5/QR flows.
                # Idempotent: re-running refreshes the DB row (upsert).
                self._finalize_wechat_session_token()

                self.start_refresh_task()
                try:
                    from auth.session_supervisor import get_session_supervisor
                    sup = get_session_supervisor()
                    if sup:
                        sup.notify_token_installed()
                except Exception:
                    pass
                logger.info(
                    f"[AuthManager.wechat_login] ✅ Successful for {self.current_user}"
                )
                return {"success": True}

        except Exception as e:
            logger.error(f"[AuthManager.wechat_login] Error: {e}")
            logger.error(traceback.format_exc())
            self.last_login_error = str(e)
            # Mirror Intl's google_login port-occupied propagation
            try:
                from auth.oauth.local_oauth_server import PortOccupiedError as _POE
                if isinstance(e, _POE):
                    self.last_login_error_details = e.to_dict()
                    self.last_login_error_details["kind"] = "port_occupied"
                    return {
                        "success": False,
                        "error": str(e),
                        "error_kind": "port_occupied",
                        "error_details": self.last_login_error_details,
                    }
            except Exception:
                pass
            return {"success": False, "error": str(e)}

    def _exchange_wechat_code(self, code: str, redirect_uri: str
                              ) -> Dict[str, Any]:
        """Exchange a WeChat authorization code for CloudBase tokens.

        Uses ``CloudBaseAuthService.sign_in_with_provider`` if it exists,
        otherwise falls back to a manual ``POST /auth/v1/authentication``
        call against the Web v3 gateway.
        """
        try:
            from auth.tencent.cloudbase_auth import get_cloudbase_service
            svc = get_cloudbase_service()
        except Exception as e:
            return {"success": False, "error": f"Cannot load CloudBase service: {e}"}

        # 1) Prefer a dedicated sign_in_with_provider if CloudBase service
        #    implements one (added in newer TCB SDKs).
        if hasattr(svc, "sign_in_with_provider"):
            from typing import Any as _Any  # noqa: F401  (import kept for clarity)
            try:
                res = svc.sign_in_with_provider(
                    provider_id="wx_open",  # Open Platform website app
                    redirect_uri=redirect_uri,
                    code=code,
                )
                if hasattr(res, "success"):
                    ok, data, err = res.success, res.data, res.error
                else:
                    ok, data, err = res.get("success"), res.get("data"), res.get("error")
                if ok and data:
                    from auth.tencent.cloudbase_adapter import _normalize_tokens
                    return {"success": True, "data": _normalize_tokens(data)}
                return {"success": False, "error": err or "sign_in_with_provider failed"}
            except Exception as e:
                logger.warning(
                    f"[AuthManager._exchange_wechat_code] sign_in_with_provider "
                    f"raised: {e}; falling back to manual endpoint"
                )

        # 2) Manual fallback — POST /auth/v1/authentication with the
        #    provider grant. Keeps this method self-contained even if
        #    CloudBaseAuthService hasn't been extended with the helper yet.
        import requests as _requests
        from auth.tencent.cloudbase_config import CloudBaseConfig
        cfg = CloudBaseConfig.from_auth_config()
        if not cfg.env_id:
            return {"success": False, "error": "CloudBase env_id not configured"}
        url = f"https://{cfg.env_id}.api.tcloudbasegateway.com/auth/v1/authentication"
        try:
            r = _requests.post(
                url,
                json={
                    "provider_id": "wx_open",
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "anonymous": False,
                },
                timeout=30,
            )
            body = r.json() if r.text else {}
            # One-shot diagnostic: dump full body so we can confirm whether
            # CloudBase's WeChat provider ever returns a refresh_token.
            # Cheap and only on the auth path — not in a hot loop. Remove
            # once the upstream behavior is documented.
            logger.info(
                f"[AuthManager._exchange_wechat_code] CloudBase response keys: "
                f"{sorted(body.keys()) if isinstance(body, dict) else type(body).__name__}"
            )
            # Diagnose: check if refresh_token is present
            if isinstance(body, dict):
                rt_keys = [k for k in body.keys() if 'refresh' in k.lower()]
                logger.info(f"[AuthManager._exchange_wechat_code] Refresh-related keys: {rt_keys}")
                if rt_keys:
                    for k in rt_keys:
                        logger.info(f"[AuthManager._exchange_wechat_code]   {k}: {str(body.get(k))[:80]}")
            if r.status_code >= 400:
                return {
                    "success": False,
                    "error": body.get("error_description") or body.get("error") or r.text,
                    "error_code": body.get("code", f"HTTP_{r.status_code}"),
                }
            if not body.get("access_token"):
                return {
                    "success": False,
                    "error": body.get("error") or "No access_token in response",
                    "error_code": body.get("code") or "NO_TOKEN",
                }
            from auth.tencent.cloudbase_adapter import _normalize_tokens
            return {"success": True, "data": _normalize_tokens(body)}
        except _requests.RequestException as e:
            return {"success": False, "error": str(e), "error_code": "NETWORK_ERROR"}

    def get_saved_login_info(self):
        """Get saved login information from keyring storage.

        IMPORTANT — login_type gating (fix for "微信/手机号登录后再次进入登录页,
        邮箱输入框被填充成 wechat id / 手机号"):

        ``uli.json`` 的 ``user`` 字段对所有登录方式都填入了"标识符":
          * email 登录 → ``user@example.com`` (可作为 username 填充到表单)
          * 手机号登录 → ``13800138000`` (不是邮箱,绝对不能填到 email 字段)
          * 微信登录 → ``wechat_xxx@local`` (不是邮箱)
          * Google 登录 → ``user@gmail.com`` (实际是 email,但因不带 password,
            也不应该自动填充)

        如果无脑把 ``user`` 字段回填到登录表单的 ``username`` 字段,会导致
        邮箱输入框显示 "wechat_xxx@local" 或 "13800138000" —
        既不是用户预期的邮箱,也触发浏览器/React keyring 的 autofill
        干扰下次输入。

        这里只对 ``login_type == "password"`` 返回 ``username/password``,
        其他登录方式通过 ``last_identifier`` (供前端识别) + 空 username/password
        通知前端"这个登录类型不应该自动填任何字段"。
        """
        try:
            username = self._get_saved_username()
            logger.debug(f"[get_saved_login_info] Retrieved username from uli.json: '{username}'")
            self.machine_role = self._get_saved_machine_role()
            logger.debug(f"[get_saved_login_info] Retrieved machine_role: '{self.machine_role}'")

            # Ensure machine_role is never None (should have default from _get_saved_machine_role)
            if not self.machine_role:
                self.machine_role = "Commander"

            # Read login_type from uli.json FIRST so we can decide whether to
            # expose username/password at all.
            language = None
            theme = None
            login_type = None
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        language = data.get('language')
                        theme = data.get('theme')
                        login_type = data.get('login_type')
                except Exception as e:
                    logger.warning(f"Error reading preferences from {self.acct_file}: {e}")

            # Login-type gating: only password login should autofill credentials.
            # For wechat / phone / google / custom, the "user" stored in
            # uli.json is NOT an email and must NEVER be put into the
            # login form's username field. The frontend uses login_type to
            # decide which tab to activate and which fields to render.
            is_password_login = (login_type == "password")

            password = ""
            if is_password_login and username:
                success, result = self._get_credentials(username)
                if success:
                    password = result
                    logger.debug(f"[get_saved_login_info] Password retrieved (login_type=password)")
                else:
                    logger.warning(f"[get_saved_login_info] Could not retrieve password: {result}")

            # For non-password login types, return the identifier under a
            # distinct field (``last_identifier``) so the frontend can log /
            # debug it WITHOUT leaking it into the form.
            #
            # Rationale for splitting: previously the response shape was
            # ``{username, password, login_type}`` and the frontend
            # special-cased login_type in JSX — but a stale `username` from a
            # previous login attempt (e.g. user typed an email then switched
            # to phone) could still leak through. Trimming at the source
            # closes that gap permanently.
            response_username = username if is_password_login else ""
            response_password = password if is_password_login else ""

            return {
                "machine_role": self.machine_role,
                "username": response_username,
                "password": response_password,
                "language": language,
                "theme": theme,
                "login_type": login_type,
                # last_identifier: the raw identifier (wechat id / phone /
                # google email) preserved for debugging / future use. The
                # frontend may use a phone identifier only for the dedicated
                # phone field; it must never put it into the email field.
                "last_identifier": username or "",
            }
        except Exception as e:
            logger.error(f"Error getting saved login info: {e}")
            # Ensure machine_role has a default value even on error
            return {
                "machine_role": self.machine_role or "Commander",
                "username": "",
                "password": "",
                "login_type": None,
                "last_identifier": "",
            }

    def _update_saved_login_info(self, username, password, role, login_type=None):
        """Update saved login information with new username and password.
        
        Args:
            username: The user's login identifier
            password: The user's password (or empty string for non-password auth)
            role: The user's machine role
            login_type: Optional login type ('password', 'wechat', 'phone', etc.)
        """
        try:
            logger.info(f"[_update_saved_login_info] Saving login info to: {self.acct_file}")
            data = {}
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r') as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading {self.acct_file}: {e}")

            data["user"] = username
            data["machine_role"] = role
            # Preserve language and theme if they exist
            # (don't overwrite them during login)
            # Save login_type if provided
            if login_type:
                data["login_type"] = login_type

            try:
                with open(self.acct_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error writing to {self.acct_file}: {e}")

            if not self._store_credentials(username, password):
                logger.error("Failed to store password")
                return False

            logger.info(f"Updated login info for user: {username}, login_type: {login_type}")
            return True
        except Exception as e:
            logger.error(f"Error updating login info: {e}")
            return False

    def _store_credentials(self, username, password):
        """Securely store credentials in the system keyring.

        On Intl writes to the ``ecan_auth`` service. On CN writes to the
        ``ecan_cloudbase_auth`` service so the two apps can coexist on the
        same developer machine without overwriting each other.
        """
        try:
            logger.debug(f"[_store_credentials] Storing password for username: '{username}'")
            service = "ecan_cloudbase_auth" if self._is_cn else "ecan_auth"
            keyring.set_password(service, username, password)
            logger.info(f"[_store_credentials] Successfully stored password for username: '{username}'")
            return True
        except Exception as e:
            logger.error(f"[_store_credentials] Failed to store credentials for '{username}': {e}")
            return False

    def _get_credentials(self, username):
        """Retrieve credentials from the system keyring.

        CN reads from ``ecan_cloudbase_auth``; Intl from ``ecan_auth``.
        """
        try:
            logger.debug(f"[_get_credentials] Attempting to retrieve password for username: '{username}'")
            service = "ecan_cloudbase_auth" if self._is_cn else "ecan_auth"
            password = keyring.get_password(service, username)
            if password is None:
                logger.warning(f"[_get_credentials] No password found in keyring for username: '{username}'")
                return False, "No password found"
            logger.debug(f"[_get_credentials] Successfully retrieved password (length: {len(password)})")
            return True, password
        except Exception as e:
            logger.error(f"[_get_credentials] Exception retrieving password: {e}")
            return False, str(e)

    # --- Session persistence helpers ---
    def _refresh_service(self) -> str:
        import sys
        if getattr(sys, 'frozen', False):
            # Running as packaged app
            return "ecan_refresh"
        else:
            # Running in development environment
            return "ecan_refresh_dev"

    def _check_keychain_access(self) -> tuple[bool, str]:
        """Check if keychain is accessible (lazy, no test writes).
        
        Returns cached availability status. Keychain is assumed available
        until an actual operation fails, avoiding macOS authorization popups on startup.
        """
        return getattr(self, '_keychain_available', True), "Lazy check - determined on first use"

    def diagnose_keychain_issues(self) -> dict:
        """Provide comprehensive keychain diagnostic information."""
        import platform

        diagnosis = {
            "platform": platform.system(),
            "keychain_accessible": False,
            "issues": [],
            "recommendations": []
        }

        if platform.system() != "Darwin":
            diagnosis["keychain_accessible"] = True
            diagnosis["recommendations"].append("Keychain not applicable on non-macOS systems")
            return diagnosis

        # Check keychain access
        keychain_ok, keychain_msg = self._check_keychain_access()
        diagnosis["keychain_accessible"] = keychain_ok

        if not keychain_ok:
            diagnosis["issues"].append(keychain_msg)
            diagnosis["recommendations"].extend([
                "Open 'Keychain Access' application",
                "Ensure 'login' keychain is unlocked",
                "Grant permission when prompted by the app",
                "If issues persist, try: security unlock-keychain ~/Library/Keychains/login.keychain"
            ])

        return diagnosis

    def _store_refresh_token(self, username: str, refresh_token: str) -> bool:
        """Store refresh token using platform-specific optimal storage method.

        Strategy:
        - Windows: Use chunked storage (due to Credential Manager length limits)
        - macOS: Use direct storage (Keychain can handle long content)
        - Linux: Use direct storage with chunked fallback
        - File storage: Only as last resort when keyring fails
        """
        # First, validate the refresh token
        if not refresh_token or len(refresh_token.strip()) == 0:
            logger.error("Cannot store empty refresh token")
            return False

        import platform
        platform_name = platform.system()
        is_macos = platform_name == "Darwin"
        is_windows = platform_name == "Windows"
        is_linux = platform_name == "Linux"

        try:
            if is_windows:
                # Windows: Always use chunked storage due to Credential Manager limitations
                logger.info("Windows detected: Using chunked storage for refresh token")
                success = self._store_refresh_token_chunked(username, refresh_token)
                if success:
                    logger.info("Refresh token stored successfully using Windows chunked storage")
                    return True
                else:
                    logger.warning("Windows chunked storage failed, falling back to file storage")

            elif is_macos:
                # macOS: Use direct storage (Keychain can handle long content)
                logger.info("macOS detected: Using direct storage for refresh token")
                success = self._store_refresh_token_direct(username, refresh_token)
                if success:
                    logger.info("Refresh token stored successfully using macOS direct storage")
                    return True
                else:
                    logger.warning("macOS direct storage failed, falling back to file storage")
                    logger.info("Note: In development environments, keychain access may be restricted.")
                    logger.info("File storage provides the same security for refresh tokens.")

            else:
                # Linux and other platforms: Try direct first, then chunked
                logger.info(f"{platform_name} detected: Trying direct storage first")
                success = self._store_refresh_token_direct(username, refresh_token)
                if success:
                    logger.info("Refresh token stored successfully using direct storage")
                    return True
                else:
                    logger.info("Direct storage failed, trying chunked storage")
                    success = self._store_refresh_token_chunked(username, refresh_token)
                    if success:
                        logger.info("Refresh token stored successfully using chunked storage")
                        return True
                    else:
                        logger.warning("Both direct and chunked storage failed, falling back to file storage")

            # If we reach here, keyring storage failed - use file fallback
            logger.info("Using file storage as fallback")
            file_success = self._store_refresh_token_file(username, refresh_token)
            if file_success:
                logger.info("Refresh token successfully stored using file fallback")
            else:
                logger.error("File storage also failed for refresh token")
            return file_success

        except Exception as e:
            logger.error(f"Unexpected error in refresh token storage: {e}")
            logger.info("Falling back to file-based storage due to exception")
            try:
                file_success = self._store_refresh_token_file(username, refresh_token)
                if file_success:
                    logger.info("Refresh token successfully stored using file fallback after exception")
                else:
                    logger.error("All storage methods failed for refresh token")
                return file_success
            except Exception as file_e:
                logger.error(f"File storage also failed: {file_e}")
                return False

    def _store_refresh_token_direct(self, username: str, refresh_token: str) -> bool:
        """Store refresh token directly in keyring with enhanced error handling.

        This method is optimized for macOS and Linux where keyring can handle longer content.
        """
        try:
            safe_username = self._sanitize_username_for_keyring(username)
            
            # Simple approach: try direct storage
            keyring.set_password(self._refresh_service(), safe_username, refresh_token)
            logger.info(f"✅ Stored refresh token directly in keychain")
            return True

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Direct keyring storage failed: {error_msg}")

            # Handle -25244 error specifically
            if "(-25244" in error_msg or "Can't store password on keychain" in error_msg:
                logger.warning("Keychain access denied. This is usually caused by:")
                logger.warning("1. Keychain is locked - unlock it in Keychain Access app")
                logger.warning("2. App lacks keychain permissions - grant access when prompted")
                logger.warning("3. Development environment restrictions")
                logger.info("💡 File storage will be used as fallback.")

            return False

    def _get_refresh_token(self, username: str) -> tuple[bool, str]:
        """Get refresh token using platform-specific retrieval strategy.

        Strategy matches storage strategy:
        - Windows: Try chunked first, then file
        - macOS: Try direct first, then file
        - Linux: Try direct first, then chunked, then file
        """
        import platform
        platform_name = platform.system()
        is_macos = platform_name == "Darwin"
        is_windows = platform_name == "Windows"

        if is_windows:
            # Windows: Try chunked storage first
            try:
                success, token = self._get_refresh_token_chunked(username)
                if success and token and len(token.strip()) > 0:
                    return True, token
            except Exception as e:
                logger.error(f"Failed to get refresh token from Windows chunked keyring: {e}")

        elif is_macos:
            # macOS: Try direct storage first
            try:
                success, token = self._get_refresh_token_direct(username)
                if success and token and len(token.strip()) > 0:
                    return True, token
            except Exception as e:
                logger.error(f"Failed to get refresh token from macOS direct keyring: {e}")

        else:
            # Linux and others: Try direct first, then chunked
            try:
                success, token = self._get_refresh_token_direct(username)
                if success and token and len(token.strip()) > 0:
                    return True, token
            except Exception as e:
                logger.error(f"Failed to get refresh token from direct keyring: {e}")

            try:
                success, token = self._get_refresh_token_chunked(username)
                if success and token and len(token.strip()) > 0:
                    return True, token
            except Exception as e:
                logger.error(f"Failed to get refresh token from chunked keyring: {e}")

        # Try file fallback for all platforms
        return self._get_refresh_token_file(username)

    def _get_refresh_token_direct(self, username: str) -> tuple[bool, str]:
        """Get refresh token from direct keyring storage with intelligent format detection."""
        try:
            safe_username = self._sanitize_username_for_keyring(username)
            
            stored_token = keyring.get_password(self._refresh_service(), safe_username)

            if stored_token is not None and len(stored_token.strip()) > 0:
                logger.debug(f"Retrieved refresh token from keychain")
                return True, stored_token
            else:
                return False, "No token found"

        except Exception as e:
            logger.error(f"Failed to get refresh token from direct keyring: {e}")
            return False, str(e)

    def _delete_refresh_token(self, username: str) -> bool:
        """Delete refresh token from both chunked keyring and file storage."""
        success = True
        
        # Delete from direct keyring
        try:
            safe_username = self._sanitize_username_for_keyring(username)
            try:
                keyring.delete_password(self._refresh_service(), safe_username)  # type: ignore[attr-defined]
            except Exception:
                keyring.set_password(self._refresh_service(), safe_username, "")
        except Exception as e:
            logger.error(f"Failed to delete refresh token from direct keyring: {e}")
            success = False
        
        # Delete from chunked keyring
        try:
            self._delete_refresh_token_chunked(username)
        except Exception as e:
            logger.error(f"Failed to delete refresh token from chunked keyring: {e}")
            success = False
            
        # Delete from file storage
        try:
            self._delete_refresh_token_file(username)
        except Exception as e:
            logger.error(f"Failed to delete refresh token from file: {e}")
            success = False
            
        return success

    def _get_refresh_token_file_path(self, username: str) -> str:
        """Get the file path for storing refresh token."""
        # Create a safe filename from username
        safe_username = base64.b64encode(username.encode('utf-8')).decode('ascii')
        return os.path.join(self.ecb_data_homepath, f".rt_{safe_username}")

    def _store_refresh_token_file(self, username: str, refresh_token: str) -> bool:
        """Store refresh token in an encrypted file as fallback."""
        try:
            file_path = self._get_refresh_token_file_path(username)
            
            # Simple base64 encoding for basic obfuscation
            encoded_token = base64.b64encode(refresh_token.encode('utf-8')).decode('ascii')
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w') as f:
                f.write(encoded_token)
            
            # Set restrictive permissions (Windows)
            try:
                os.chmod(file_path, 0o600)
            except Exception:
                pass  # Permissions may not be supported on all systems
                
            logger.info("Refresh token stored successfully in file")
            return True
        except Exception as e:
            logger.error(f"Failed to store refresh token in file: {e}")
            return False

    def _get_refresh_token_file(self, username: str) -> tuple[bool, str]:
        """Get refresh token from file storage."""
        try:
            file_path = self._get_refresh_token_file_path(username)
            
            if not os.path.exists(file_path):
                return False, "No refresh token file found"
                
            with open(file_path, 'r') as f:
                encoded_token = f.read().strip()
                
            if not encoded_token:
                return False, "Empty refresh token file"
                
            # Decode the token
            refresh_token = base64.b64decode(encoded_token.encode('ascii')).decode('utf-8')
            return True, refresh_token
        except Exception as e:
            logger.error(f"Failed to get refresh token from file: {e}")
            return False, str(e)

    def _delete_refresh_token_file(self, username: str) -> bool:
        """Delete refresh token file."""
        try:
            file_path = self._get_refresh_token_file_path(username)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug("Refresh token file deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete refresh token file: {e}")
            return False

    # --- Chunked keyring storage methods ---
    
    def _get_chunk_service_name(self, chunk_index: int) -> str:
        """Get service name for a specific chunk."""
        return f"ecan_refresh_chunk_{chunk_index}"
    
    def _get_chunk_count_service_name(self) -> str:
        """Get service name for storing chunk count."""
        return "ecan_refresh_chunk_count"
    
    def _store_refresh_token_chunked(self, username: str, refresh_token: str) -> bool:
        """Store refresh token in chunks to handle Windows Credential Manager length limitations.

        Note: This method is primarily designed for Windows systems where Credential Manager
        has length restrictions. On macOS, keychain access issues affect both direct and
        chunked storage equally, so file storage should be used as fallback instead.
        """
        try:
            # Validate inputs
            if not username or not refresh_token:
                logger.error("Invalid username or refresh_token for chunked storage")
                return False
            
            # Sanitize username for Windows Credential Manager
            safe_username = self._sanitize_username_for_keyring(username)
            
            # Encode token to base64 to ensure Windows compatibility
            encoded_token = base64.b64encode(refresh_token.encode('utf-8')).decode('ascii')
            
            # Windows Credential Manager safe chunk size for base64 data
            chunk_size = 1200  # More conservative for base64 encoded data
            
            # Split encoded token into chunks
            chunks = [encoded_token[i:i + chunk_size] for i in range(0, len(encoded_token), chunk_size)]
            chunk_count = len(chunks)
            
            logger.info(f"Storing refresh token in {chunk_count} base64-encoded chunks for user {username}")
            
            # First, clean up any existing chunks
            self._delete_refresh_token_chunked(username)
            
            # Store chunk count with safe username
            keyring.set_password(self._get_chunk_count_service_name(), safe_username, str(chunk_count))
            
            # Store each chunk
            for i, chunk in enumerate(chunks):
                if not chunk:  # Skip empty chunks
                    continue
                    
                service_name = self._get_chunk_service_name(i)
                keyring.set_password(service_name, safe_username, chunk)
                logger.debug(f"Stored base64 chunk {i + 1}/{chunk_count} ({len(chunk)} chars)")
            
            logger.info(f"Successfully stored refresh token in {chunk_count} base64-encoded chunks")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to store refresh token in chunks: {error_msg}")

            # Provide specific guidance for macOS keychain errors
            if "(-25244" in error_msg or "Can't store password on keychain" in error_msg:
                logger.warning("macOS Keychain access denied. This is usually caused by:")
                logger.warning("1. Keychain is locked - unlock it in Keychain Access app")
                logger.warning("2. App lacks keychain permissions - grant access when prompted")
                logger.warning("3. Development environment restrictions")
                logger.info("Refresh token will be stored in encrypted file as fallback")

            # Clean up partial storage on failure
            try:
                self._delete_refresh_token_chunked(username)
            except Exception:
                pass
            return False
    
    def _get_refresh_token_chunked(self, username: str) -> tuple[bool, str]:
        """Retrieve refresh token from chunked keyring storage."""
        try:
            # Sanitize username for consistency
            safe_username = self._sanitize_username_for_keyring(username)
            
            # Get chunk count
            chunk_count_str = keyring.get_password(self._get_chunk_count_service_name(), safe_username)
            if not chunk_count_str:
                return False, "No chunked token found"
            
            try:
                chunk_count = int(chunk_count_str)
            except ValueError:
                logger.error(f"Invalid chunk count: {chunk_count_str}")
                return False, "Invalid chunk count"
            
            if chunk_count <= 0:
                return False, "Invalid chunk count"
            
            logger.debug(f"Retrieving refresh token from {chunk_count} base64-encoded chunks")
            
            # Retrieve and concatenate chunks
            chunks = []
            for i in range(chunk_count):
                service_name = self._get_chunk_service_name(i)
                chunk = keyring.get_password(service_name, safe_username)
                if chunk is None:
                    logger.warning(f"Missing chunk {i + 1}/{chunk_count}")
                    return False, f"Missing chunk {i + 1}"
                chunks.append(chunk)
                logger.debug(f"Retrieved base64 chunk {i + 1}/{chunk_count} ({len(chunk)} chars)")
            
            # Concatenate all chunks and decode from base64
            encoded_token = ''.join(chunks)
            try:
                refresh_token = base64.b64decode(encoded_token.encode('ascii')).decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to decode base64 token: {e}")
                return False, "Failed to decode token"
            
            logger.info(f"Successfully retrieved and decoded refresh token from {chunk_count} chunks ({len(refresh_token)} total chars)")
            return True, refresh_token
            
        except Exception as e:
            logger.error(f"Failed to get refresh token from chunks: {e}")
            return False, str(e)
    
    def _delete_refresh_token_chunked(self, username: str) -> bool:
        """Delete all chunks of a refresh token from keyring."""
        try:
            success = True
            
            # Sanitize username for consistency
            safe_username = self._sanitize_username_for_keyring(username)
            
            # Get chunk count first
            chunk_count_str = keyring.get_password(self._get_chunk_count_service_name(), safe_username)
            if chunk_count_str:
                try:
                    chunk_count = int(chunk_count_str)
                    logger.debug(f"Deleting {chunk_count} chunks for user {username}")
                    
                    # Delete each chunk
                    for i in range(chunk_count):
                        service_name = self._get_chunk_service_name(i)
                        try:
                            keyring.delete_password(service_name, safe_username)  # type: ignore[attr-defined]
                        except Exception:
                            # Fallback to overwrite with empty string
                            try:
                                keyring.set_password(service_name, safe_username, "")
                            except Exception as e:
                                logger.error(f"Failed to delete chunk {i}: {e}")
                                success = False
                                
                except ValueError:
                    logger.error(f"Invalid chunk count when deleting: {chunk_count_str}")
            
            # Delete chunk count
            try:
                keyring.delete_password(self._get_chunk_count_service_name(), safe_username)  # type: ignore[attr-defined]
            except Exception:
                try:
                    keyring.set_password(self._get_chunk_count_service_name(), safe_username, "")
                except Exception as e:
                    logger.error(f"Failed to delete chunk count: {e}")
                    success = False
            
            if success:
                logger.debug("Successfully deleted all refresh token chunks")
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete refresh token chunks: {e}")
            return False
    
    def _sanitize_username_for_keyring(self, username: str) -> str:
        """Sanitize username for Windows Credential Manager compatibility."""
        if not username:
            return "default_user"
        
        # Replace problematic characters that might cause issues in Windows Credential Manager
        # Keep only alphanumeric, dots, underscores, and hyphens
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', username)
        
        # Ensure it's not too long (Windows has limits)
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        
        return sanitized

    def _set_saved_username(self, username: str) -> None:
        try:
            data = {}
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r') as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data["user"] = username
            with open(self.acct_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist username: {e}")

    def _get_saved_username(self) -> str | None:
        try:
            if exists(self.acct_file):
                with open(self.acct_file, 'r') as f:
                    data = json.load(f)
                    return data.get("user")
            return None
        except Exception as e:
            logger.error(f"Failed to read saved username: {e}")
            return None
        
    def _get_saved_machine_role(self) -> str:
        try:
            if exists(self.acct_file):
                with open(self.acct_file, 'r') as f:
                    data = json.load(f)
                    role = data.get("machine_role")
                    # Return the saved role if it exists, otherwise return default
                    return role if role else "Commander"
            # If uli.json doesn't exist, return default role
            return "Commander"
        except Exception as e:
            logger.error(f"Failed to read saved machine role: {e}")
            # Return default role on error
            return "Commander"

    def clear_auth_cache(self) -> dict:
        """Clear all cached authentication data (saved username, credentials, refresh tokens, uli.json user field).
        
        This is useful when switching login methods (e.g. from password to Google)
        and stale cached data causes issues.
        """
        cleared = []
        errors = []

        # 0. Capture saved username BEFORE clearing anything (needed for keyring cleanup)
        saved_user = self.current_user or self._get_saved_username()

        # 1. Clear in-memory state
        self.tokens = None
        self.current_user = None
        self.user_profile = {}
        self.signed_in = False
        self.stop_refresh_task()
        cleared.append("in_memory_state")

        # 2. Clear saved username from uli.json (but preserve language/theme)
        try:
            if exists(self.acct_file):
                with open(self.acct_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                old_user = data.get("user")
                data.pop("user", None)
                data.pop("machine_role", None)
                with open(self.acct_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                cleared.append(f"uli_json_user({old_user})")
        except Exception as e:
            errors.append(f"uli.json: {e}")

        # 3. Clear keyring credentials and refresh tokens for the saved user
        if saved_user:
            try:
                keyring.delete_password("ecan_auth", saved_user)
                cleared.append(f"keyring_credentials({saved_user})")
            except Exception:
                try:
                    keyring.set_password("ecan_auth", saved_user, "")
                    cleared.append(f"keyring_credentials_zeroed({saved_user})")
                except Exception as ke:
                    errors.append(f"keyring_credentials: {ke}")

            try:
                self._delete_refresh_token(saved_user)
                cleared.append(f"refresh_token({saved_user})")
            except Exception as re_err:
                errors.append(f"refresh_token: {re_err}")

        # 4. Clear IPC registry cache
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            IPCHandlerRegistry.clear_system_ready_cache()
            cleared.append("ipc_registry_cache")
        except Exception as e:
            errors.append(f"ipc_registry: {e}")

        logger.info(f"AuthManager.clear_auth_cache: cleared={cleared}, errors={errors}")
        return {
            'success': len(errors) == 0,
            'cleared': cleared,
            'errors': errors
        }

    def try_restore_session(self) -> bool:
        """Attempt to restore session from stored refresh token silently at startup."""
        username = self._get_saved_username()
        if not username:
            return False
        ok, rt = self._get_refresh_token(username)
        if not ok or not rt:
            return False
        try:
            result = self.cognito_service.refresh_tokens(rt)
            if not result.get('success'):
                logger.warning(f"AuthManager: Stored refresh token invalid for {username}: {result.get('error')}")
                self._delete_refresh_token(username)
                return False
            tokens = result['data'] or {}
            # Refresh-token rotation: prefer the server's response over the
            # token we just consumed (see Bug A fix in ensure_valid_tokens).
            rotated_rt = tokens.get('RefreshToken') or tokens.get('refresh_token')
            tokens['RefreshToken'] = rotated_rt if rotated_rt else rt
            self.tokens = tokens
            self.signed_in = True
            # Determine current user from id token if possible
            id_token = tokens.get('id_token') or tokens.get('IdToken')
            if id_token:
                claims = self.cognito_service.verify_token(id_token, 'id')
                if claims.get('success'):
                    self.current_user = claims['data'].get('email') or username
                else:
                    self.current_user = username
            else:
                self.current_user = username
            logger.info(f"AuthManager: Session restored for {self.current_user}")
            # Persist the rotated refresh_token so a future restart can
            # still restore the session — without this, the in-memory
            # rotation is lost and try_restore_session on the next launch
            # uses the already-consumed token (CloudBase refresh-tokens
            # are single-use).
            if rotated_rt and rotated_rt != rt:
                try:
                    self._store_refresh_token(username, rotated_rt)
                except Exception as _persist_exc:
                    logger.warning(
                        f"AuthManager: rotated refresh-token persistence "
                        f"skipped: {_persist_exc}"
                    )
            # Wire SessionSupervisor so OfflineSyncManager and WS reconnect loop
            # know a fresh token is installed (resets cache-lag grace window,
            # clears any stale expired/paused state).
            try:
                sup = get_session_supervisor()
                if sup:
                    sup.notify_token_installed()
            except Exception as e:
                logger.debug(f"[AuthManager] restore notify_token_installed skipped: {e}")
            # Try to start refresh task; skip if no running loop
            try:
                self.start_refresh_task()
            except Exception as e:
                logger.error(f"AuthManager: Could not start refresh task yet: {e}")
            return True
        except Exception as e:
            logger.error(f"AuthManager: Failed to restore session: {e}")
            return False

    def try_restore_cloudbase_session(self) -> bool:
        """Attempt to restore CloudBase session from stored credentials silently at startup.

        Mirrors the AWS Cognito try_restore_session() pattern:
        1. Read saved username from uli.json
        2. Retrieve password + refresh_token from keyring
        3. Call CloudBase refresh API to get new access_token
        4. Set up TokenManager with restored tokens
        """
        if not self._is_cn:
            return False

        username = self._get_saved_username()
        if not username:
            logger.debug("[try_restore_cloudbase_session] No saved username found")
            return False

        # Use CloudBase-specific keyring services (separate from AWS Cognito).
        # Mirrors Intl's ``try_restore_session`` which has a keyring→file
        # fallback via ``_get_refresh_token``.  We used to read keyring only
        # — when the keychain was locked or the keyring write had silently
        # failed on the previous login (runlog 2026-08-14 19:02), every
        # restart lost the refresh token and the user was forced to
        # re-scan the QR even though a perfectly good refresh token was
        # sitting in the file fallback.
        try:
            password = keyring.get_password("ecan_cloudbase_auth", username)
            if not password:
                logger.debug(f"[try_restore_cloudbase_session] No password in keyring for {username}")
                return False

            rt = keyring.get_password("ecan_cloudbase_refresh", username)
            if not rt:
                # Keyring didn't have it — fall back to the file-based
                # store that ``_store_refresh_token_file`` writes whenever
                # keyring storage is unavailable.
                ok_file, rt_file = self._get_refresh_token_file(username)
                if ok_file and rt_file:
                    logger.info(
                        f"[try_restore_cloudbase_session] refresh token "
                        f"recovered from file fallback for {username}"
                    )
                    rt = rt_file
                else:
                    logger.debug(f"[try_restore_cloudbase_session] No refresh token for {username}")
                    return False
        except Exception as e:
            logger.warning(f"[try_restore_cloudbase_session] Keyring error: {e}")
            return False

        try:
            from auth.tencent.cloudbase_auth import CloudBaseAuthService
            service = CloudBaseAuthService()

            refresh_result = service.refresh_token(rt)
            if not refresh_result.success:
                logger.warning(f"[try_restore_cloudbase_session] Refresh failed: {refresh_result.error}")
                # Only delete refresh token, preserve password so user can re-login
                self._delete_cloudbase_refresh_token(username)
                return False

            tokens = refresh_result.data
            self.tokens = tokens
            # CloudBase may rotate the refresh_token.  If the response
            # carries a new one, install it; otherwise keep the rt we sent
            # (the server is allowed to echo the same value back).
            rotated_rt = (tokens or {}).get("RefreshToken") or (tokens or {}).get("refresh_token")
            self.tokens["RefreshToken"] = rotated_rt if rotated_rt else rt
            self.signed_in = True
            self.current_user = username

            logger.info(f"[try_restore_cloudbase_session] Session restored for {username}")

            # Persist the rotated refresh_token so a future restart can
            # still restore the session — CloudBase refresh-tokens are
            # single-use (the old one dies the moment the server issues
            # the new one), so without this the in-memory rotation is
            # lost on every restart.
            if rotated_rt and rotated_rt != rt:
                try:
                    keyring.set_password(
                        "ecan_cloudbase_refresh", username, rotated_rt,
                    )
                except Exception as _kr_exc:
                    logger.warning(
                        f"[try_restore_cloudbase_session] keyring persist "
                        f"failed, falling back to file: {_kr_exc}"
                    )
                    try:
                        self._store_refresh_token_file(username, rotated_rt)
                    except Exception as _file_exc:
                        logger.warning(
                            f"[try_restore_cloudbase_session] file persist "
                            f"also failed: {_file_exc}"
                        )

            # Wire SessionSupervisor — same intent as Intl restore above.
            try:
                from auth.session_supervisor import get_session_supervisor
                sup = get_session_supervisor()
                if sup:
                    sup.notify_token_installed()
            except Exception as e:
                logger.debug(f"[try_restore_cloudbase_session] supervisor notify skipped: {e}")

            # CN HTTP session token on RESTORE (2026-08-25): the mint used to
            # run only in the login-finalize path, so an app restart with a
            # restored session never (re)acquired the eCan session token —
            # every HTTP GraphQL call then failed "Bearer token required"
            # (observed on a customer machine after the server deployed
            # mintHttpSessionToken: the restarted client never re-attempted
            # the exchange). Idempotent; failure is non-fatal (the lazy
            # self-heal in cloud_api retries later).
            try:
                self._finalize_http_session_token()
            except Exception as e:
                logger.warning(f"[try_restore_cloudbase_session] HTTP session finalize skipped: {e}")

            self._setup_token_manager_from_tokens(tokens, username)
            return True

        except Exception as e:
            logger.error(f"[try_restore_cloudbase_session] Failed: {e}")
            return False

    def _delete_cloudbase_credentials(self, username: str) -> None:
        """Delete all stored CloudBase credentials (password + refresh token).
        
        Use this when the user explicitly logs out or requests credential deletion.
        """
        import keyring
        try:
            keyring.delete_password("ecan_cloudbase_auth", username)
            logger.debug(f"[_delete_cloudbase_credentials] Deleted password for {username}")
        except Exception:
            pass
        try:
            keyring.delete_password("ecan_cloudbase_refresh", username)
            logger.debug(f"[_delete_cloudbase_credentials] Deleted refresh token for {username}")
        except Exception:
            pass
        logger.debug(f"[_delete_cloudbase_credentials] All credentials deleted for {username}")

    def _delete_cloudbase_refresh_token(self, username: str) -> None:
        """Delete stored CloudBase refresh token only, preserving the password.
        
        Use this when refresh token is expired/invalid - we need to clear the
        invalid refresh token but keep the password so the user can re-login.
        """
        import keyring
        try:
            keyring.delete_password("ecan_cloudbase_refresh", username)
            logger.debug(f"[_delete_cloudbase_refresh_token] Deleted refresh token for {username}")
        except Exception:
            pass
        logger.debug(f"[_delete_cloudbase_refresh_token] Refresh token deleted for {username} (password preserved)")

    def _delete_refresh_token(self, username: str) -> None:
        """Delete stored refresh token for username (from keyring + file)."""
        import platform
        platform_name = platform.system()
        is_windows = platform_name == "Windows"

        service = self._refresh_service()
        safe_username = self._sanitize_username_for_keyring(username)

        try:
            if is_windows:
                # Get chunk count and delete all chunks
                try:
                    count = keyring.get_password(service, f"{safe_username}_chunk_count")
                    if count:
                        for i in range(int(count)):
                            try:
                                keyring.delete_password(service, f"{safe_username}_chunk_{i}")
                            except Exception:
                                pass
                        keyring.delete_password(service, f"{safe_username}_chunk_count")
                except Exception:
                    pass
            else:
                try:
                    keyring.delete_password(service, safe_username)
                except Exception:
                    pass
        except Exception:
            pass

        # Also delete from file fallback
        file_path = self._get_refresh_token_file_path(username)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    def _setup_token_manager_from_tokens(self, tokens: dict, username: str) -> None:
        """Set up TokenManager with restored tokens."""
        try:
            from gui.ipc.token_manager import TokenManager
            token_mgr = TokenManager.get_instance()
            access_token = tokens.get("access_token") or tokens.get("AccessToken", "")
            refresh_token = tokens.get("refresh_token") or tokens.get("RefreshToken", "")
            expires_in = tokens.get("expires_in", 7200)

            token_mgr.set_tokens(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )
            logger.debug("[_setup_token_manager_from_tokens] TokenManager configured")
        except Exception as e:
            logger.warning(f"[_setup_token_manager_from_tokens] Failed: {e}")

    # -------------------------------------------------------------------------
    # WeChat session token (silent refresh — no QR re-scan needed)
    # -------------------------------------------------------------------------
    # Server-side scheme: backend mints a 30-day custom JWT ("session token") tied
    # to the WeChat openid. We store this token locally and replay it to refresh
    # the CloudBase access_token without user interaction.

    _WECHAT_SESSION_TOKEN_SERVICE = "ecan_wechat_session"
    _WECHAT_SESSION_TOKEN_FILE_PREFIX = ".wx_st"

    def _get_wechat_session_token(self) -> tuple[bool, str]:
        """Retrieve WeChat session token (opaque JWT) from keyring + file fallback."""
        username = self.current_user or self._get_saved_username()
        if not username:
            return False, "no username"
        safe = self._sanitize_username_for_keyring(username)
        # Try keyring first
        try:
            token = keyring.get_password(self._WECHAT_SESSION_TOKEN_SERVICE, safe)
            if token and len(token.strip()) > 10:
                return True, token
        except Exception:
            pass
        # File fallback
        return self._get_wechat_session_token_file(username)

    def _get_wechat_session_token_file(self, username: str) -> tuple[bool, str]:
        safe = base64.b64encode(username.encode('utf-8')).decode('ascii')
        path = os.path.join(self.ecb_data_homepath, f"{self._WECHAT_SESSION_TOKEN_FILE_PREFIX}_{safe}")
        if not os.path.exists(path):
            return False, "no file"
        try:
            with open(path, 'r') as f:
                return True, f.read().strip()
        except Exception:
            return False, "read error"

    def _save_wechat_session_token(self, session_token: str) -> bool:
        """Persist WeChat session token to keyring + file."""
        username = self.current_user
        if not username:
            return False
        safe = self._sanitize_username_for_keyring(username)
        # Keyring
        try:
            keyring.set_password(self._WECHAT_SESSION_TOKEN_SERVICE, safe, session_token)
        except Exception:
            pass
        # File fallback
        safe_file = base64.b64encode(username.encode('utf-8')).decode('ascii')
        path = os.path.join(self.ecb_data_homepath, f"{self._WECHAT_SESSION_TOKEN_FILE_PREFIX}_{safe_file}")
        try:
            with open(path, 'w') as f:
                f.write(session_token)
        except Exception as e:
            logger.warning(f"[_save_wechat_session_token] file fallback failed: {e}")
        return True

    def _delete_wechat_session_token(self) -> None:
        username = self.current_user
        if not username:
            return
        safe = self._sanitize_username_for_keyring(username)
        try:
            keyring.delete_password(self._WECHAT_SESSION_TOKEN_SERVICE, safe)
        except Exception:
            pass
        safe_file = base64.b64encode(username.encode('utf-8')).decode('ascii')
        path = os.path.join(self.ecb_data_homepath, f"{self._WECHAT_SESSION_TOKEN_FILE_PREFIX}_{safe_file}")
        if os.path.exists(path):
            os.remove(path)

    def _is_wechat_flow(self) -> bool:
        """Return True iff the current login is a CN WeChat OAuth flow.

        Two equivalent signals:

        1. ``self.user_profile.get("login_type") == "wechat"`` — set
           explicitly by every CN WeChat login handler
           (``cloudbase_handler._build_login_response`` /
           ``cloudbase_wechat_qr_login`` / ``wechat_login``). Intl paths
           never set ``login_type="wechat"`` and CN phone/password paths
           use ``"phone"`` / ``"password"``.
        2. ``self.current_user`` starts with ``wechat_`` (the convention
           set by ``complete_login_from_provider`` / ``wechat_login``
           after a WeChat OAuth callback). Both the canonical
           ``wechat_<openid>@local`` form and the shorter caller-
           supplied ``wechat_<openid>`` form are accepted — safe because
           Intl usernames are email-shaped and never start with
           ``wechat_``.

        Earlier this method inspected the access_token JWT for an
        ``openid`` claim. Real 2026-08 WeChat JWTs sign a payload with
        ``{alg, env, iat, exp, uid, refresh, expire}`` — no ``openid``
        field — so ``claims.get("openid")`` returned ``None`` on every
        login and ``_finalize_wechat_session_token`` silently no-op'd,
        meaning the 30-day server session was never registered and users
        were forced to re-scan the QR every 3600s access-token TTL.
        """
        if not self._is_cn:
            return False
        if (self.user_profile or {}).get("login_type") == "wechat":
            return True
        username = self.current_user or ""
        return username.startswith("wechat_")

    def _finalize_wechat_session_token(self) -> bool:
        """Single canonical entry point for WeChat session token setup.

        Called from any CN WeChat login path (wechat_login /
        complete_login_from_provider / cloudbase_finalize_session /
        cloudbase_wechat_qr_login) AFTER tokens + current_user have been
        installed and the supervisor has been notified.

        Idempotent. Re-running with the same access_token just refreshes the
        server-side row (upsert on openid). Safe to call from anywhere.

        Returns True iff a fresh session token was persisted locally.
        No-op (returns True) when this is not a WeChat flow — so callers
        can blindly invoke it without branching on login type.
        """
        if not self._is_wechat_flow():
            return True

        access_token = self.tokens.get("AccessToken") or self.tokens.get("access_token")
        ok, result = self._register_wechat_session(access_token)
        if ok and isinstance(result, dict):
            st = result.get("sessionToken") or ""
            if st:
                self._save_wechat_session_token(st)
                logger.info(
                    f"[AuthManager.wechat_finalize] Session token registered "
                    f"for {self.current_user} (expires in "
                    f"{result.get('expiresIn', 0)}s)"
                )
                return True
        logger.warning(
            f"[AuthManager.wechat_finalize] Session registration did not "
            f"return a token: {result}"
        )
        return False

    def _finalize_http_session_token(self) -> bool:
        """Install the durable bearer used by the CN HTTP GraphQL gateway.

        WeChat has a provider-specific exchange.  Other CloudBase providers
        use the generic mintHttpSessionToken mutation.  Intl authentication
        is unchanged.
        """
        if not self._is_cn:
            return True
        if self._is_wechat_flow():
            return self._finalize_wechat_session_token()
        return self._mint_http_session_token()

    def _mint_http_session_token(self) -> bool:
        """Exchange a non-WeChat CloudBase token for an HTTP session token."""
        access_token = self.tokens.get("AccessToken") or self.tokens.get("access_token")
        if not access_token:
            logger.warning("[AuthManager] No access token for HTTP session mint")
            return False

        login_type = (self.user_profile or {}).get("login_type") or "password"
        mutation = """
            mutation MintHttpSessionToken($input: MintHttpSessionTokenInput!) {
                mintHttpSessionToken(input: $input) {
                    sessionToken
                    expiresIn
                }
            }
        """
        try:
            import requests as _req
            from agent.cloud_api.cloud_api import get_appsync_endpoint

            jwt = access_token.split('/@@/', 1)[-1] if '/@@/' in access_token else access_token
            resp = _req.post(
                get_appsync_endpoint(),
                json={
                    'query': mutation,
                    'variables': {'input': {
                        'accessToken': access_token,
                        'loginType': login_type,
                        'userIdentifier': self.current_user,
                    }},
                },
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {jwt}',
                },
                timeout=30,
            )
            body = resp.json() if resp.text else {}
            data = (body.get('data') or {}).get('mintHttpSessionToken')
            session_token = (data or {}).get('sessionToken')
            if session_token:
                self._save_wechat_session_token(session_token)
                logger.info(
                    "[AuthManager] HTTP session token minted for login_type=%s "
                    "(expires in %ss)", login_type, (data or {}).get('expiresIn', 0)
                )
                return True
            logger.warning(
                "[_mint_http_session_token] GraphQL errors: %s",
                body.get('errors', []),
            )
        except Exception as e:
            logger.warning(f"[_mint_http_session_token] failed: {e}")
        return False

    def _register_wechat_session(self, access_token: str) -> tuple[bool, Any]:
        """Call GraphQL registerWeChatSession to mint a 30-day session token."""
        mutation = """
            mutation RegisterWeChatSession($input: RegisterWeChatSessionInput!) {
                registerWeChatSession(input: $input) {
                    sessionToken
                    expiresIn
                }
            }
        """
        try:
            import requests as _req
            from agent.cloud_api.cloud_api import get_appsync_endpoint
            endpoint = get_appsync_endpoint()
            jwt = access_token.split('/@@/', 1)[-1] if '/@@/' in access_token else access_token
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {jwt}',
            }
            resp = _req.post(endpoint, json={'query': mutation, 'variables': {
                'input': {'wxAccessToken': access_token}
            }}, headers=headers, timeout=30)
            body = resp.json() if resp.text else {}
            data = (body.get('data') or {}).get('registerWeChatSession')
            if data:
                return True, data
            errors = body.get('errors', [])
            logger.warning(f"[_register_wechat_session] GraphQL errors: {errors}")
            return False, errors
        except Exception as e:
            logger.warning(f"[_register_wechat_session] failed: {e}")
            return False, str(e)

    # Whether the deployed refreshWeChatToken payload exposes a rotated
    # sessionToken. None = unknown (try optimistically); flipped to False on a
    # schema-validation error so we retry with the legacy selection.
    _refresh_returns_rotated_session: Optional[bool] = None

    def _refresh_wechat_token(self, session_token: str) -> tuple[bool, Any]:
        """Call GraphQL refreshWeChatToken to get a fresh access_token.

        Refresh endpoints in this stack ROTATE the durable session credential
        (the web auth_refresh.php atomically replaces the opaque token), so if
        the server returns a rotated ``sessionToken`` we MUST persist it —
        keeping the old one strands us with a revoked credential and the next
        refresh fails with SESSION_EXPIRED. Falls back to the legacy
        ``accessToken expiresIn`` selection when the deployed schema has no
        sessionToken field on the payload.
        """
        def _post(select_rotation: bool):
            fields = "accessToken\n                    expiresIn"
            if select_rotation:
                fields += "\n                    sessionToken"
            mutation = f"""
                mutation RefreshWeChatToken($input: RefreshWeChatTokenInput!) {{
                    refreshWeChatToken(input: $input) {{
                        {fields}
                    }}
                }}
            """
            import requests as _req
            from agent.cloud_api.cloud_api import get_appsync_endpoint
            endpoint = get_appsync_endpoint()
            # The session token doubles as the bearer: the SCF gate
            # (resolveIdentity) rejects headerless requests before the
            # resolver can validate input.sessionToken, but it accepts the
            # session token itself via verifySessionToken.
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {session_token}',
            }
            resp = _req.post(endpoint, json={'query': mutation, 'variables': {
                'input': {'sessionToken': session_token}
            }}, headers=headers, timeout=30)
            return resp.json() if resp.text else {}

        try:
            cls = type(self)
            select_rotation = cls._refresh_returns_rotated_session is not False
            body = _post(select_rotation)
            errors = body.get('errors', [])

            # Schema without the rotated-token field: remember and retry once
            # with the legacy selection.
            if select_rotation and errors and any(
                isinstance(e, dict) and 'sessionToken' in str(e.get('message', ''))
                and 'Cannot query field' in str(e.get('message', ''))
                for e in errors
            ):
                logger.info(
                    "[_refresh_wechat_token] payload has no sessionToken field; "
                    "using legacy selection from now on"
                )
                cls._refresh_returns_rotated_session = False
                body = _post(False)
                errors = body.get('errors', [])

            data = (body.get('data') or {}).get('refreshWeChatToken')
            if data:
                new_st = data.get('sessionToken')
                if isinstance(new_st, str) and new_st:
                    cls._refresh_returns_rotated_session = True
                    if new_st != session_token:
                        if self._save_wechat_session_token(new_st):
                            logger.info(
                                "[_refresh_wechat_token] rotated session token "
                                "persisted (server replaced the old one)"
                            )
                        else:
                            logger.warning(
                                "[_refresh_wechat_token] rotated session token "
                                "could not be persisted — next refresh may fail"
                            )
                return True, data
            # Decode error code
            code = None
            msg = str(errors)
            for e in (errors if isinstance(errors, list) else [errors]):
                code = e.get('extensions', {}).get('code') if isinstance(e, dict) else None
                msg = e.get('message', str(e)) if isinstance(e, dict) else str(e)
            return False, {'error': msg, 'code': code}
        except Exception as e:
            logger.warning(f"[_refresh_wechat_token] failed: {e}")
            return False, str(e)

    _REFRESH_LOOP_START_MAX_RETRIES = 5
    _REFRESH_LOOP_START_RETRY_DELAY = 3  # seconds

    def start_refresh_task(self):
        """Starts the background token refresh task.

        If no asyncio event loop is running yet (common during early startup),
        retries up to _REFRESH_LOOP_START_MAX_RETRIES times using a background
        threading.Timer so the refresh loop is never silently skipped.
        """
        self._start_refresh_task_attempt(attempt=0)

    def _start_refresh_task_attempt(self, attempt: int):
        if self.refresh_task is not None and not self.refresh_task.done():
            return  # already running

        has_refresh_token = bool(self.tokens and self.tokens.get('RefreshToken'))
        has_wechat_session = self._is_cn and bool(
            self.tokens and self.tokens.get('AccessToken') and self.tokens.get('AccessToken') != self.tokens.get('RefreshToken')
        )

        if not has_refresh_token and not has_wechat_session:
            logger.warning("AuthManager: No refresh token and no WeChat session token — cannot start refresh loop")
            return

        # Prefer the qasync main loop from AppContext when it is available.
        # ``asyncio.get_running_loop()`` only sees a loop from the *current*
        # thread; during early startup ``AuthManager.__init__`` runs on the
        # main thread before qasync's loop has begun running, and the legacy
        # threading.Timer retries run on a fresh thread that will never see
        # the qasync loop — which is why the retry chain kept exhausting
        # silently. ``run_coroutine_threadsafe`` is the supported way to
        # schedule onto a known event loop from any thread.
        try:
            from app_context import AppContext
            loop = AppContext.get_main_loop()
        except Exception:
            loop = None

        if loop is not None and loop.is_running():
            try:
                self.refresh_task = asyncio.run_coroutine_threadsafe(
                    self._token_refresh_loop(), loop
                )
                logger.info("AuthManager: Token refresh task started")
                return
            except Exception as e:
                # Fall through to the retry chain below.
                logger.warning(
                    f"AuthManager: run_coroutine_threadsafe failed ({e}); "
                    "falling back to retry chain"
                )

        try:
            running_loop = asyncio.get_running_loop()
            self.refresh_task = running_loop.create_task(self._token_refresh_loop())
            logger.info("AuthManager: Token refresh task started")
        except RuntimeError:
            if attempt < self._REFRESH_LOOP_START_MAX_RETRIES:
                delay = self._REFRESH_LOOP_START_RETRY_DELAY * (attempt + 1)
                logger.info(
                    f"AuthManager: No running event loop yet, retrying refresh task start "
                    f"in {delay}s (attempt {attempt + 1}/{self._REFRESH_LOOP_START_MAX_RETRIES})"
                )
                import threading
                t = threading.Timer(delay, self._start_refresh_task_attempt, args=[attempt + 1])
                t.daemon = True
                t.start()
            else:
                logger.error(
                    "AuthManager: Failed to start refresh task after "
                    f"{self._REFRESH_LOOP_START_MAX_RETRIES} attempts — no event loop available"
                )
                self.refresh_task = None

    def stop_refresh_task(self):
        """Stops the background token refresh task."""
        if self.refresh_task and not self.refresh_task.done():
            logger.info("AuthManager: Stopping token refresh task.")
            self.refresh_task.cancel()
        self.refresh_task = None

    # Errors that mean the refresh token itself is invalid and retrying won't help.
    _FATAL_REFRESH_ERRORS = {'NotAuthorizedException', 'InvalidParameterException', 'UserNotFoundException'}

    async def _token_refresh_loop(self):
        """Periodically refreshes the authentication tokens.

        Designed to run for the entire lifetime of the app.  Transient failures
        (network errors, throttling) are retried with exponential backoff.
        Only truly fatal errors (token revoked, user deleted) break the loop.
        """
        consecutive_failures = 0
        normal_interval = 2700  # 45 minutes — well within the 60-min access token lifetime

        while True:
            try:
                # On success we wait the full interval; on failure we back off
                if consecutive_failures == 0:
                    await asyncio.sleep(normal_interval)
                else:
                    backoff = min(60 * (2 ** (consecutive_failures - 1)), 1800)  # cap at 30 min
                    logger.info(
                        f"AuthManager: Refresh retry backoff {backoff}s "
                        f"(consecutive failures: {consecutive_failures})"
                    )
                    await asyncio.sleep(backoff)

                if not self.signed_in or not self.tokens:
                    logger.info("AuthManager: User not signed in, stopping refresh loop.")
                    break

                refresh_token = self.tokens.get('RefreshToken')
                is_wechat = self._is_cn and not refresh_token and self.tokens.get('AccessToken')

                if is_wechat:
                    # WeChat: use session token to get a fresh access_token
                    ok, session_tok = self._get_wechat_session_token()
                    if not ok:
                        logger.warning("AuthManager: WeChat session token not found — stopping refresh loop")
                        break
                    logger.info("AuthManager: Refreshing WeChat token via session token...")
                    ok2, result = self._refresh_wechat_token(session_tok)
                    if ok2:
                        self.tokens['AccessToken'] = result.get('accessToken', self.tokens.get('AccessToken'))
                        self.tokens['access_token'] = result.get('accessToken', self.tokens.get('access_token'))
                        consecutive_failures = 0
                        logger.info("AuthManager: WeChat token refreshed successfully.")
                        try:
                            from auth.session_supervisor import get_session_supervisor
                            sup = get_session_supervisor()
                            if sup is not None:
                                sup.notify_token_installed()
                        except Exception:
                            pass
                        continue
                    else:
                        err_code = (result or {}).get('code') if isinstance(result, dict) else None
                        err_msg = (result or {}).get('error') if isinstance(result, dict) else str(result)
                        consecutive_failures += 1
                        logger.warning(f"AuthManager: WeChat token refresh failed ({err_code}): {err_msg}")
                        if err_code == 'SESSION_EXPIRED':
                            logger.error("AuthManager: WeChat session expired — please re-scan QR code")
                            self.signed_in = False
                            break
                        # WX_TOKEN_EXPIRED / transient: HTTP still works on the
                        # 30-day session token — keep looping (with backoff) in
                        # case the server starts minting WS tokens again.
                        continue

                logger.info("AuthManager: Refreshing tokens...")
                result = self.cognito_service.refresh_tokens(refresh_token)

                if result['success']:
                    self.tokens.update(result['data'])
                    consecutive_failures = 0
                    logger.info("AuthManager: Tokens refreshed successfully.")
                    # Persist the (possibly rotated) refresh_token so a
                    # restart can still restore the session. Without this,
                    # CloudBase refresh-token rotation silently drops the
                    # next-restart ability to log in: the old token is
                    # single-use, the new one is in memory only, and
                    # try_restore_session would fall back to the
                    # already-consumed value and 401 on first use.
                    try:
                        new_rt = (
                            (result.get('data') or {}).get('RefreshToken')
                            or (result.get('data') or {}).get('refresh_token')
                        )
                        # Only persist when the server actually returned one
                        # (rotation case). If it didn't rotate, the in-memory
                        # value is unchanged and the existing keyring entry
                        # is still correct.
                        if new_rt and new_rt != refresh_token and self.current_user:
                            if self._is_cn:
                                try:
                                    keyring.set_password(
                                        "ecan_cloudbase_refresh",
                                        self.current_user,
                                        new_rt,
                                    )
                                except Exception as _kr_exc:
                                    logger.warning(
                                        f"[AuthManager] keyring persist "
                                        f"failed, falling back to file: "
                                        f"{_kr_exc}"
                                    )
                                    self._store_refresh_token_file(
                                        self.current_user, new_rt,
                                    )
                            else:
                                self._store_refresh_token(
                                    self.current_user, new_rt,
                                )
                    except Exception as _persist_exc:
                        # Persistence is best-effort; never break the refresh
                        # loop because of a keyring / file write error.
                        logger.warning(
                            f"[AuthManager] refresh-token persistence "
                            f"skipped: {_persist_exc}"
                        )
                    # Notify SessionSupervisor so subscribed components
                    # (offline sync, websocket) can resume work that was
                    # paused on the previous expiration window.
                    try:
                        from auth.session_supervisor import get_session_supervisor
                        sup = get_session_supervisor()
                        if sup is not None:
                            sup.notify_token_installed()
                    except Exception as _sup_exc:
                        logger.debug(
                            f"[AuthManager] supervisor notify skipped: {_sup_exc}"
                        )
                else:
                    error_code = result.get('error', '')
                    consecutive_failures += 1
                    logger.error(
                        f"AuthManager: Token refresh failed ({error_code}), "
                        f"consecutive failures: {consecutive_failures}"
                    )

                    # Fatal: the refresh token itself is revoked/invalid — stop the loop
                    if error_code in self._FATAL_REFRESH_ERRORS:
                        logger.error(
                            f"AuthManager: Fatal refresh error ({error_code}). "
                            "User must re-login."
                        )
                        self.signed_in = False
                        break

                    # Transient: keep retrying (the backoff at the top of the loop handles delay)

            except asyncio.CancelledError:
                logger.info("AuthManager: Token refresh task was cancelled (normal during logout).")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"AuthManager: Unexpected error in token refresh loop: {e} "
                    f"(consecutive failures: {consecutive_failures})"
                )
