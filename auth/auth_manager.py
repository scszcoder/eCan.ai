# auth/auth_manager.py

import webbrowser
import traceback
import asyncio
import keyring
import json
from os.path import exists

from bot.envi import getECBotDataHome

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
        self.signed_in = False
        self.machine_role = "Platoon"  # Default role
        self.ecb_data_homepath = getECBotDataHome()
        self.acct_file = self.ecb_data_homepath + "/uli.json"
        self.refresh_task = None
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


    def login(self, username, password, role):
        """Handle username/password login logic."""
        try:
            self.machine_role = role
            self.current_user = username

            result = self.cognito_service.login(username, password)

            if result['success']:
                self.tokens = result['data']
                self.signed_in = True
                # Persist username/password and refresh token
                self._update_saved_login_info(username, password, role)  # Save credentials on success
                rt = (self.tokens.get('RefreshToken') or self.tokens.get('refresh_token'))
                if rt:
                    self._store_refresh_token(username, rt)
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

                # Parse the user's identity (email) from tokens; fall back to userInfo endpoint.
                email = None
                id_token = self.tokens.get('id_token') or self.tokens.get('IdToken')
                if id_token:
                    claims = self.cognito_service.verify_token(id_token, 'id')
                    if claims.get('success'):
                        email = claims['data'].get('email') or claims['data'].get('username')

                if not email:
                    access_token = self.tokens.get('access_token') or self.tokens.get('AccessToken')
                    if access_token and hasattr(self.cognito_service, 'get_userinfo'):
                        ui = self.cognito_service.get_userinfo(access_token)
                        if ui.get('success'):
                            data = ui.get('data') or {}
                            email = data.get('email') or data.get('username')

                self.current_user = email or self._get_saved_username() or "unknown@local"

                # Save signed-in user and refresh token for session persistence
                if self.current_user:
                    self._set_saved_username(self.current_user)
                refresh_token = self.tokens.get('RefreshToken')
                if refresh_token and self.current_user:
                    self._store_refresh_token(self.current_user, refresh_token)

                # Step 8: Start the background token refresh task to maintain a long-lived session.
                self.start_refresh_task()
                logger.info(f"AuthManager: Google login successful for {self.current_user}")
                return {'success': True}

        except Exception as e:
            logger.error(f"AuthManager: An unexpected error occurred during Google login: {e}")
            logger.error(traceback.format_exc())
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
            self.machine_role = self._get_saved_machine_role()

            password = ""
            if username:
                success, result = self._get_credentials(username)
                if success:
                    password = result
                else:
                    logger.warning(f"Could not retrieve password: {result}")

            return {
                "machine_role": self.machine_role,
                "username": username or "",
                "password": password
            }
        except Exception as e:
            logger.error(f"Error getting saved login info: {e}")
            return {"machine_role": self.machine_role, "username": "", "password": ""}

    def _update_saved_login_info(self, username, password, role):
        """Update saved login information with new username and password."""
        try:
            data = {}
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r') as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading {self.acct_file}: {e}")

            data["user"] = username
            data["machine_role"] = role

            try:
                with open(self.acct_file, 'w') as f:
                    json.dump(data, f, indent=2)
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
            keyring.set_password("ecan_auth", username, password)
            return True
        except Exception as e:
            logger.error(f"Failed to store credentials: {e}")
            return False

    def _get_credentials(self, username):
        """Retrieve credentials from the system keyring."""
        try:
            password = keyring.get_password("ecan_auth", username)
            if password is None:
                return False, "No password found"
            return True, password
        except Exception as e:
            return False, str(e)

    # --- Session persistence helpers ---
    def _refresh_service(self) -> str:
        return "ecan_refresh"

    def _store_refresh_token(self, username: str, refresh_token: str) -> bool:
        try:
            keyring.set_password(self._refresh_service(), username, refresh_token)
            return True
        except Exception as e:
            logger.error(f"Failed to store refresh token: {e}")
            return False

    def _get_refresh_token(self, username: str) -> tuple[bool, str]:
        try:
            token = keyring.get_password(self._refresh_service(), username)
            if token is None:
                return False, "No refresh token found"
            return True, token
        except Exception as e:
            return False, str(e)

    def _delete_refresh_token(self, username: str) -> bool:
        try:
            # Some keyring backends may not implement delete_password; fallback to overwrite empty
            try:
                keyring.delete_password(self._refresh_service(), username)  # type: ignore[attr-defined]
            except Exception:
                keyring.set_password(self._refresh_service(), username, "")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete refresh token: {e}")
            return False

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
            logger.warning(f"Failed to persist username: {e}")

    def _get_saved_username(self) -> str | None:
        try:
            if exists(self.acct_file):
                with open(self.acct_file, 'r') as f:
                    data = json.load(f)
                    return data.get("user")
            return None
        except Exception as e:
            logger.warning(f"Failed to read saved username: {e}")
            return None
        
    def _get_saved_machine_role(self) -> str | None:
        try:
            if exists(self.acct_file):
                with open(self.acct_file, 'r') as f:
                    data = json.load(f)
                    return data.get("machine_role")
            return None
        except Exception as e:
            logger.warning(f"Failed to read saved machine role: {e}")
            return None

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
                logger.debug(f"AuthManager: Could not start refresh task yet: {e}")
            return True
        except Exception as e:
            logger.warning(f"AuthManager: Failed to restore session: {e}")
            return False

    def start_refresh_task(self):
        """Starts the background token refresh task."""
        if self.refresh_task is None or self.refresh_task.done():
            logger.info("AuthManager: Starting token refresh task.")
            try:
                self.refresh_task = asyncio.create_task(self._token_refresh_loop())
            except RuntimeError as e:
                # No running event loop; will be started later when loop is available
                logger.debug(f"AuthManager: Cannot start refresh task (no event loop?): {e}")
                self.refresh_task = None

    def stop_refresh_task(self):
        """Stops the background token refresh task."""
        if self.refresh_task and not self.refresh_task.done():
            logger.info("AuthManager: Stopping token refresh task.")
            self.refresh_task.cancel()
        self.refresh_task = None

    async def _token_refresh_loop(self):
        """Periodically refreshes the authentication tokens."""
        while True:
            try:
                # Wait for 45 minutes (2700 seconds) before refreshing.
                # Access tokens typically expire in 60 minutes.
                await asyncio.sleep(2700)

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
                    # Update the tokens with the new ones.
                    self.tokens.update(result['data'])
                    logger.info("AuthManager: Tokens refreshed successfully.")
                else:
                    logger.error(f"AuthManager: Failed to refresh tokens: {result['error']}. User may need to log in again.")
                    # If refresh fails (e.g., token revoked), stop the loop.
                    self.signed_in = False
                    break

            except asyncio.CancelledError:
                logger.info("AuthManager: Token refresh task was cancelled.")
                break
            except Exception as e:
                logger.error(f"AuthManager: An error occurred in the token refresh loop: {e}")
                # Wait a bit before retrying to avoid spamming on persistent errors.
                await asyncio.sleep(60)

