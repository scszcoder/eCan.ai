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
                self._update_saved_login_info(username, password)  # Save credentials on success
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
        """Orchestrates the entire Google login flow using a local callback server."""
        try:
            self.machine_role = role

            # Step 1: Read the configuration and start a temporary local HTTP server to listen for the callback.
            # Using a `with` statement ensures the server is properly shut down after the flow completes or errors out.
            callback_url = AuthConfig.GOOGLE.CALLBACK_URL
            with LocalOAuthServer(url=callback_url, timeout=300) as server:
                redirect_uri = server.get_redirect_uri()

                # Step 2: Get the Cognito Hosted UI URL, which will direct the user straight to the Google login page.
                result = self.cognito_service.get_google_login_url(redirect_uri)
                if not result['success']:
                    raise Exception(f"Could not get Google login URL: {result.get('error')}")

                # Step 3: Open the URL in the user's default browser. The application will now pause and wait for the callback.
                webbrowser.open(result['data']['url'])
                logger.info("AuthManager: Browser opened for Google auth. Waiting for callback...")

                # Step 4: Wait for the local server to capture the callback request from Cognito.
                # This is a blocking call that will return upon receiving the code, an error, or a timeout.
                callback_result = server.wait_for_callback()
                if not callback_result.get('success'):
                    raise Exception(f"Google login failed during callback: {callback_result.get('error')}")

                # Step 5: Extract the one-time authorization code from the callback result.
                auth_code = callback_result.get('auth_code')
                if not auth_code:
                    raise Exception("Authorization code not found in callback.")

                # Step 6: Use the authorization code to exchange it for JWTs via a secure server-to-server request to Cognito.
                # This is the most critical security step, ensuring that only our backend can get the final tokens.
                logger.info("AuthManager: Authorization code received. Exchanging for tokens...")
                token_result = self.cognito_service.exchange_code_for_tokens(auth_code, redirect_uri)

                if not token_result.get('success'):
                    raise Exception(f"Failed to exchange code for tokens: {token_result.get('error')}")

                # Step 7: Login successful! Store the tokens and update the internal state.
                self.tokens = token_result['data']
                self.signed_in = True

                # Parse the user's email from the id_token and set it as the current user.
                id_token = self.tokens.get('id_token')
                if id_token:
                    claims = self.cognito_service.verify_token(id_token, 'id')
                    if claims['success']:
                        self.current_user = claims['data'].get('email')

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
        self.stop_refresh_task()  # Stop the background refresh task
        self.tokens = None
        self.current_user = None
        self.signed_in = False
        logger.info("AuthManager: User logged out.")
        return True

    def get_saved_login_info(self):
        """Get saved login information from keyring storage."""
        try:
            username = ""
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r') as f:
                        data = json.load(f)
                        username = data.get("user", "")
                except Exception as e:
                    logger.warning(f"Error reading username from {self.acct_file}: {e}")

            password = ""
            if username:
                success, result = self._get_credentials(username)
                if success:
                    password = result
                else:
                    logger.warning(f"Could not retrieve password: {result}")

            return {
                "machine_role": self.machine_role,
                "username": username,
                "password": password
            }
        except Exception as e:
            logger.error(f"Error getting saved login info: {e}")
            return {"machine_role": self.machine_role, "username": "", "password": ""}

    def _update_saved_login_info(self, username, password):
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
            keyring.set_password("ecbot_auth", username, password)
            return True
        except Exception as e:
            logger.error(f"Failed to store credentials: {e}")
            return False

    def _get_credentials(self, username):
        """Retrieve credentials from the system keyring."""
        try:
            password = keyring.get_password("ecbot_auth", username)
            if password is None:
                return False, "No password found"
            return True, password
        except Exception as e:
            return False, str(e)



    def start_refresh_task(self):
        """Starts the background token refresh task."""
        if self.refresh_task is None or self.refresh_task.done():
            logger.info("AuthManager: Starting token refresh task.")
            self.refresh_task = asyncio.create_task(self._token_refresh_loop())

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

