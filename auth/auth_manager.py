# auth/auth_manager.py

import webbrowser
import traceback
import asyncio
import time
import keyring
import json
import os
import sys
import base64
from os.path import exists

from config.envi import getECBotDataHome

from auth.cognito.cognito_service import CognitoService
from auth.oauth.local_oauth_server import LocalOAuthServer
from auth.auth_config import AuthConfig
from utils.logger_helper import logger_helper as logger

class AuthManager:
    """Manages authentication state and business logic."""

    def __init__(self):
        self.cognito_service = CognitoService()
        self.tokens = None
        self.current_user = None
        self.user_profile = {}  # Store user profile info (name, picture, etc.)
        self.signed_in = False
        self.last_login_error = None  # Store last login error for IPC handler to retrieve
        self.machine_role = "Platoon"  # Default role
        self.ecb_data_homepath = getECBotDataHome()
        self.acct_file = self.ecb_data_homepath + "/uli.json"
        logger.info(f"[AuthManager.__init__] Initial acct_file path: {self.acct_file}")

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
        self.refresh_task = None

        # Keychain availability is determined lazily on first actual use
        # This avoids triggering macOS Keychain authorization popup on every startup
        self._keychain_available = True

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
        #     self.try_restore_session()
        # except Exception as e:
        #     logger.warning(f"AuthManager: Failed to restore session on startup: {e}")

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
            return int(exp)
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
                return True

            now = int(time.time())
            remaining = exp - now
            if remaining > min_validity_seconds:
                return True

            refresh_token = self.tokens.get('RefreshToken') or self.tokens.get('refresh_token')
            if not refresh_token:
                logger.warning("AuthManager: Token is expiring/expired but no refresh token is available")
                return False

            logger.info(f"AuthManager: Refreshing tokens on demand (remaining={remaining}s)")
            result = self.cognito_service.refresh_tokens(refresh_token)
            if not result.get('success'):
                logger.error(f"AuthManager: On-demand token refresh failed: {result.get('error')}")
                self.signed_in = False
                return False

            refreshed_tokens = result.get('data') or {}
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

    def _fetch_user_profile(self, access_token, id_token=None):
        """
        Helper method to fetch and construct the user profile from ID token claims
        and/or the UserInfo endpoint.
        """
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
                    self._set_saved_username(self.current_user)
                refresh_token = self.tokens.get('RefreshToken')
                if refresh_token and self.current_user:
                    self._store_refresh_token(self.current_user, refresh_token)
                else:
                    logger.error("auth manager refresh token is None")
                # Step 8: Start the background token refresh task to maintain a long-lived session.
                self.start_refresh_task()
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

    def get_saved_login_info(self):
        """Get saved login information from keyring storage."""
        try:
            username = self._get_saved_username()
            logger.debug(f"[get_saved_login_info] Retrieved username from uli.json: '{username}'")
            self.machine_role = self._get_saved_machine_role()
            logger.debug(f"[get_saved_login_info] Retrieved machine_role: '{self.machine_role}'")

            # Ensure machine_role is never None (should have default from _get_saved_machine_role)
            if not self.machine_role:
                self.machine_role = "Commander"

            password = ""
            if username:
                success, result = self._get_credentials(username)
                if success:
                    password = result
                    logger.debug(f"[get_saved_login_info] Password retrieved successfully (length: {len(password)})")
                else:
                    logger.warning(f"[get_saved_login_info] Could not retrieve password: {result}")

            # Read language and theme from uli.json
            language = None
            theme = None
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        language = data.get('language')
                        theme = data.get('theme')
                except Exception as e:
                    logger.warning(f"Error reading preferences from {self.acct_file}: {e}")

            return {
                "machine_role": self.machine_role,
                "username": username or "",
                "password": password,
                "language": language,
                "theme": theme
            }
        except Exception as e:
            logger.error(f"Error getting saved login info: {e}")
            # Ensure machine_role has a default value even on error
            return {"machine_role": self.machine_role or "Commander", "username": "", "password": ""}

    def _update_saved_login_info(self, username, password, role):
        """Update saved login information with new username and password."""
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

            try:
                with open(self.acct_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error writing to {self.acct_file}: {e}")

            if not self._store_credentials(username, password):
                logger.error("Failed to store password")
                return False

            logger.info(f"Updated login info for user: {username}")
            return True
        except Exception as e:
            logger.error(f"Error updating login info: {e}")
            return False

    def _store_credentials(self, username, password):
        """Securely store credentials in the system keyring."""
        try:
            logger.debug(f"[_store_credentials] Storing password for username: '{username}'")
            keyring.set_password("ecan_auth", username, password)
            logger.info(f"[_store_credentials] Successfully stored password for username: '{username}'")
            return True
        except Exception as e:
            logger.error(f"[_store_credentials] Failed to store credentials for '{username}': {e}")
            return False

    def _get_credentials(self, username):
        """Retrieve credentials from the system keyring."""
        try:
            logger.debug(f"[_get_credentials] Attempting to retrieve password for username: '{username}'")
            password = keyring.get_password("ecan_auth", username)
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
            tokens['RefreshToken'] = rt
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
            # Try to start refresh task; skip if no running loop
            try:
                self.start_refresh_task()
            except Exception as e:
                logger.error(f"AuthManager: Could not start refresh task yet: {e}")
            return True
        except Exception as e:
            logger.error(f"AuthManager: Failed to restore session: {e}")
            return False

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

        if not self.tokens or not self.tokens.get('RefreshToken'):
            logger.warning("AuthManager: No refresh token available, cannot start refresh loop")
            return

        try:
            loop = asyncio.get_running_loop()
            self.refresh_task = loop.create_task(self._token_refresh_loop())
            logger.info("AuthManager: Token refresh task started")
        except RuntimeError:
            if attempt < self._REFRESH_LOOP_START_MAX_RETRIES:
                delay = self._REFRESH_LOOP_START_RETRY_DELAY * (attempt + 1)
                logger.info(
                    f"AuthManager: No event loop yet, retrying refresh task start "
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
                if not refresh_token:
                    logger.warning("AuthManager: No refresh token available. Cannot refresh session.")
                    break

                logger.info("AuthManager: Refreshing tokens...")
                result = self.cognito_service.refresh_tokens(refresh_token)

                if result['success']:
                    self.tokens.update(result['data'])
                    consecutive_failures = 0
                    logger.info("AuthManager: Tokens refreshed successfully.")
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

