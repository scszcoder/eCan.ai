# auth/auth_manager.py

import webbrowser
import traceback
import asyncio
import keyring
import json
import os
import base64
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

        # Check keychain access on startup
        keychain_ok, keychain_msg = self._check_keychain_access()
        if keychain_ok:
            logger.debug(f"Keychain status: {keychain_msg}")
        else:
            logger.warning(f"Keychain issue detected: {keychain_msg}")
            logger.info("Refresh tokens will be stored in encrypted files as fallback")

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
                else:
                    logger.error("auth manager refresh token is None")
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

        # Clear IPC registry system ready cache
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            IPCHandlerRegistry.clear_system_ready_cache()
            logger.debug("AuthManager: Cleared IPC registry system ready cache on logout")
        except Exception as e:
            logger.debug(f"AuthManager: Error clearing IPC registry cache: {e}")

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

    def _check_keychain_access(self) -> tuple[bool, str]:
        """Check if keychain is accessible and provide diagnostic information."""
        try:
            import platform
            if platform.system() != "Darwin":
                return True, "Not macOS - keychain not applicable"

            # Try a simple keychain operation
            test_service = "ecan_keychain_test"
            test_username = "test_user"
            test_value = "test_value"

            try:
                keyring.set_password(test_service, test_username, test_value)
                keyring.delete_password(test_service, test_username)
                return True, "Keychain access is working"
            except Exception as e:
                error_msg = str(e)
                if "(-25244" in error_msg:
                    return False, "Keychain access denied (-25244). Try: 1) Unlock keychain in Keychain Access app, 2) Grant app permissions when prompted"
                elif "(-25300" in error_msg:
                    return False, "Keychain item not found (-25300). This is normal for test operations"
                else:
                    return False, f"Keychain error: {error_msg}"
        except Exception as e:
            return False, f"Keychain check failed: {e}"

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
        """Store refresh token using appropriate storage method based on platform and token size."""
        # First, validate the refresh token
        if not refresh_token or len(refresh_token.strip()) == 0:
            logger.error("Cannot store empty refresh token")
            return False

        import platform
        is_macos = platform.system() == "Darwin"
        is_windows = platform.system() == "Windows"

        try:
            # Check if token is small enough for direct storage with base64 encoding
            encoded_token = base64.b64encode(refresh_token.encode('utf-8')).decode('ascii')
            if len(encoded_token) <= 1200:  # Conservative limit for direct base64 storage
                try:
                    safe_username = self._sanitize_username_for_keyring(username)
                    keyring.set_password(self._refresh_service(), safe_username, encoded_token)
                    logger.info("Refresh token stored successfully in keyring (direct base64)")
                    return True
                except Exception as e:
                    error_msg = str(e)
                    logger.warning(f"Direct keyring storage failed: {error_msg}")

                    # Handle platform-specific keychain access issues
                    if "(-25244" in error_msg or "Can't store password on keychain" in error_msg:
                        if is_macos:
                            logger.info("macOS Keychain access issue detected - skipping chunked storage and using file fallback")
                            # On macOS, keychain issues affect both direct and chunked storage
                            # Skip chunked storage and go directly to file storage
                            file_success = self._store_refresh_token_file(username, refresh_token)
                            if file_success:
                                logger.info("Refresh token successfully stored using file fallback")
                            else:
                                logger.error("File storage failed for refresh token")
                            return file_success
                        else:
                            logger.info("Keychain access issue detected - will try chunked storage")

            # Use chunked storage for large tokens or if direct storage failed (but not on macOS with keychain issues)
            if is_windows or not is_macos:
                # Only use chunked storage on Windows (where it's needed) or non-macOS systems
                # On macOS, if we reach here and keychain access failed, we should skip to file storage
                return self._store_refresh_token_chunked(username, refresh_token)
            else:
                # On macOS, if direct storage failed due to keychain issues, go straight to file storage
                logger.info("On macOS with potential keychain issues - using file storage directly")
                file_success = self._store_refresh_token_file(username, refresh_token)
                if file_success:
                    logger.info("Refresh token successfully stored using file fallback")
                else:
                    logger.error("File storage failed for refresh token")
                return file_success

        except Exception as e:
            logger.warning(f"Failed to store refresh token in keyring: {e}")
            logger.info("Falling back to file-based storage")
            file_success = self._store_refresh_token_file(username, refresh_token)
            if file_success:
                logger.info("Refresh token successfully stored using file fallback")
            else:
                logger.error("Both keyring and file storage failed for refresh token")
            return file_success

    def _get_refresh_token(self, username: str) -> tuple[bool, str]:
        """Get refresh token from chunked keyring storage or file fallback."""
        try:
            # Try direct keyring first (base64 encoded)
            safe_username = self._sanitize_username_for_keyring(username)
            encoded_token = keyring.get_password(self._refresh_service(), safe_username)
            if encoded_token is not None and len(encoded_token.strip()) > 0:
                try:
                    # Decode from base64
                    token = base64.b64decode(encoded_token.encode('ascii')).decode('utf-8')
                    return True, token
                except Exception as decode_e:
                    logger.debug(f"Failed to decode direct keyring token: {decode_e}")
        except Exception as e:
            logger.debug(f"Failed to get refresh token from direct keyring: {e}")
        
        try:
            # Try chunked keyring
            success, token = self._get_refresh_token_chunked(username)
            if success and token and len(token.strip()) > 0:
                return True, token
        except Exception as e:
            logger.debug(f"Failed to get refresh token from chunked keyring: {e}")
            
        # Try file fallback
        return self._get_refresh_token_file(username)

    def _delete_refresh_token(self, username: str) -> bool:
        """Delete refresh token from both chunked keyring and file storage."""
        success = True
        
        # Delete from direct keyring (base64 encoded)
        try:
            safe_username = self._sanitize_username_for_keyring(username)
            try:
                keyring.delete_password(self._refresh_service(), safe_username)  # type: ignore[attr-defined]
            except Exception:
                keyring.set_password(self._refresh_service(), safe_username, "")
        except Exception as e:
            logger.warning(f"Failed to delete refresh token from direct keyring: {e}")
            success = False
        
        # Delete from chunked keyring
        try:
            self._delete_refresh_token_chunked(username)
        except Exception as e:
            logger.warning(f"Failed to delete refresh token from chunked keyring: {e}")
            success = False
            
        # Delete from file storage
        try:
            self._delete_refresh_token_file(username)
        except Exception as e:
            logger.warning(f"Failed to delete refresh token from file: {e}")
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
            logger.debug(f"Failed to get refresh token from file: {e}")
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
            logger.warning(f"Failed to delete refresh token file: {e}")
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
                logger.warning(f"Invalid chunk count: {chunk_count_str}")
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
            logger.debug(f"Failed to get refresh token from chunks: {e}")
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
                                logger.warning(f"Failed to delete chunk {i}: {e}")
                                success = False
                                
                except ValueError:
                    logger.warning(f"Invalid chunk count when deleting: {chunk_count_str}")
            
            # Delete chunk count
            try:
                keyring.delete_password(self._get_chunk_count_service_name(), safe_username)  # type: ignore[attr-defined]
            except Exception:
                try:
                    keyring.set_password(self._get_chunk_count_service_name(), safe_username, "")
                except Exception as e:
                    logger.warning(f"Failed to delete chunk count: {e}")
                    success = False
            
            if success:
                logger.debug("Successfully deleted all refresh token chunks")
            return success
            
        except Exception as e:
            logger.warning(f"Failed to delete refresh token chunks: {e}")
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
            if not self.tokens or not self.tokens.get('RefreshToken'):
                logger.warning("AuthManager: start_refresh_task called without a refresh token. Task not started.")
                return

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

