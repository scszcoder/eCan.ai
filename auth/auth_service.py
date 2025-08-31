"""
Pure business logic class for user authentication and token management.
This class handles all authentication operations without any UI dependencies.
"""

import asyncio
import json
import os
import time
import base64
import hmac
import hashlib
import traceback
import keyring
import logging
from os.path import exists
from typing import Dict, Any, Tuple, Optional

import boto3
import botocore
from pycognito import Cognito, AWSSRP
from botocore.config import Config
from auth.auth_config import AuthConfig

from utils.logger_helper import logger_helper as logger
from auth.auth_messages import auth_messages

from config.app_info import app_info
from bot.envi import getECBotDataHome
from bot.network import commanderIP, commanderServer, commanderXport


class AuthService:
    """Pure business logic class for authentication operations."""
    
    def __init__(self, language: str = 'en-US'):
        """Initialize the authentication service."""
        # Initialize tokens and user state
        self.tokens = None
        self.old_access_token = None
        self.cognito_user_id = None
        self.current_user = ""
        self.current_user_pw = ""
        self.signed_in = False
        
        # Set language for messages
        auth_messages.set_language(language)
        
        # Initialize AWS client
        self.aws_client = boto3.client('cognito-idp', region_name=AuthConfig.COGNITO.REGION)
        
        # Configuration
        self.ecb_data_homepath = getECBotDataHome()
        self.acct_file = self.ecb_data_homepath + "/uli.json"
        self.role_file = self.ecb_data_homepath + "/role.json"
        self.max_retries = 5
        
        # User settings
        self.machine_role = "Platoon"
        self.schedule_mode = "manual"
        self.lang = "en"
        
        # Load initial configuration
        self.read_role()
    
    def _setup_aws_clients_with_credentials(self, aws_credentials: Dict[str, str]) -> None:
        """Set up AWS clients with temporary credentials from Cognito Identity Pool."""
        try:
            # Create session with temporary credentials
            self.aws_session = boto3.Session(
                aws_access_key_id=aws_credentials['access_key'],
                aws_secret_access_key=aws_credentials['secret_key'],
                aws_session_token=aws_credentials['session_token'],
                region_name=AuthConfig.COGNITO.REGION
            )
            
            # Update AWS client with new session
            self.aws_client = self.aws_session.client('cognito-idp')
            
            # Store credentials for other AWS services
            self.aws_credentials = aws_credentials
            
            logger.info("AWS clients updated with temporary credentials from Cognito Identity Pool")
            
        except Exception as e:
            logger.error(f"Failed to setup AWS clients with temporary credentials: {e}")
            raise
    
    def get_aws_client(self, service_name: str):
        """Get AWS client for specified service using current credentials."""
        if hasattr(self, 'aws_session') and self.aws_session:
            return self.aws_session.client(service_name)
        else:
            # Fallback to default credentials
            return boto3.client(service_name, region_name=AuthConfig.COGNITO.REGION)
    
    def read_role(self) -> None:
        """Read machine role from configuration file."""
        self.machine_role = "Platoon"
        if exists(self.role_file):
            try:
                with open(self.role_file, 'r') as file:
                    mr_data = json.load(file)
                    self.machine_role = mr_data["machine_role"]
                    logger.info(f"Loaded machine role: {self.machine_role}")
            except Exception as e:
                logger.error(f"Error reading role file: {e}")
        else:
            logger.info(f"Role file {self.role_file} does not exist, using default role")
    
    def get_role(self) -> str:
        """Get current machine role."""
        return self.machine_role
    
    def set_role(self, role: str):
        """Set machine role."""
        self.machine_role = role
    
    def set_language(self, language: str):
        """Set language for error messages."""
        auth_messages.set_language(language)
    
    def is_commander(self) -> bool:
        """Check if current role is commander."""
        return self.machine_role in ["Commander", "Commander Only"]
    
    def get_current_user(self) -> str:
        """Get current logged in user."""
        return self.current_user
    
    def get_log_user(self) -> str:
        """Get formatted user name for logging."""
        if not self.current_user:
            return ""
        parts = self.current_user.split("@")
        if len(parts) == 2:
            return f"{parts[0]}_{parts[1].replace('.', '_')}"
        return self.current_user
    
    def is_signed_in(self) -> bool:
        """Check if user is currently signed in."""
        return self.signed_in
    
    def decode_jwt(self, token: str) -> Dict[str, Any]:
        """Decode JWT token and return payload."""
        try:
            payload_part = token.split('.')[1]
            padding = '=' * (4 - len(payload_part) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload_part + padding)
            payload = json.loads(decoded_bytes.decode('utf-8'))
            return payload
        except Exception as e:
            logger.error(f"Error decoding JWT: {e}")
            raise
    
    def get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito authentication."""
        message = username + AuthConfig.COGNITO.CLIENT_ID
        dig = hmac.new(AuthConfig.COGNITO.CLIENT_SECRET.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
        secret_hash = base64.b64encode(dig).decode()
        return secret_hash
    
    def _check_network_connection(self) -> bool:
        """Check network connectivity."""
        try:
            import socket
            import requests
            
            # Check basic network connection
            socket.create_connection(("8.8.8.8", 53), timeout=10)
            
            # Check AWS service availability
            try:
                region = AuthConfig.COGNITO.REGION
                response = requests.get(f"https://cognito-idp.{region}.amazonaws.com", timeout=10)
                return response.status_code < 500
            except:
                return True  # Basic network is working
                
        except Exception as e:
            logger.warning(f"Network connection check failed: {e}")
            return False
    
    def authenticate_with_backoff(self, aws_srp, max_retries: int = None) -> Dict[str, Any]:
        """Authenticate with AWS using exponential backoff retry mechanism."""
        if max_retries is None:
            max_retries = self.max_retries
            
        for attempt in range(max_retries):
            try:
                logger.info(f"AWS authentication attempt {attempt + 1}/{max_retries}")
                
                # Configure client with timeout settings
                config = Config(
                    connect_timeout=60,
                    read_timeout=60,
                    retries={'max_attempts': 3}
                )
                
                if hasattr(aws_srp, 'client') and aws_srp.client:
                    aws_srp.client.config = config
                
                return aws_srp.authenticate_user()
                
            except botocore.exceptions.ClientError as e:
                error_code = e.response['Error']['Code']
                logger.warning(f"AWS authentication error (attempt {attempt + 1}): {error_code}")
                
                if error_code == 'TooManyRequestsException':
                    wait_time = min(2 ** attempt, 30)
                    logger.info(f"Too many requests, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                elif error_code == 'NetworkError':
                    wait_time = min(2 ** attempt, 15)
                    logger.info(f"Network error, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Unrecoverable AWS error: {error_code}")
                    raise e
                    
            except Exception as e:
                logger.error(f"Unexpected error during authentication (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise e
                wait_time = min(2 ** attempt, 10)
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        raise Exception(f"Max retries ({max_retries}) exceeded for AWS authentication")
    
    def login(self, username: str, password: str, role: str = None) -> Tuple[bool, str]:
        """
        Authenticate user with AWS Cognito.
        
        Args:
            username: User email
            password: User password
            role: Optional machine role override
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Update role if provided
            if role:
                self.set_role(role)
            
            # Store credentials if login is successful
            if not self._update_saved_login_info(username, password):
                logger.warning("Failed to update saved login info")
            
            # Set up AWS SRP authentication
            self.aws_srp = AWSSRP(
                username=username, 
                password=password, 
                pool_id=AuthConfig.COGNITO.USER_POOL_ID,
                client_id=AuthConfig.COGNITO.CLIENT_ID, 
                client=self.aws_client
            )
            
            if role:
                self.machine_role = role
            
            # Authenticate with retry mechanism
            self.tokens = self.authenticate_with_backoff(self.aws_srp)
            
            # Extract tokens and user information
            self.id_token = self.tokens['AuthenticationResult']['IdToken']
            self.old_access_token = self.tokens["AuthenticationResult"]["AccessToken"]
            refresh_token = self.tokens["AuthenticationResult"]["RefreshToken"]
            decoded_id_token = self.decode_jwt(self.id_token)
            
            # Extract Cognito User ID
            self.cognito_user_id = decoded_id_token.get('sub')
            decoded_username = decoded_id_token["cognito:username"]
            
            logger.info(f"Successfully authenticated user: {decoded_username}")
            
            # Set up Cognito client
            self.cog = Cognito(
                AuthConfig.COGNITO.USER_POOL_ID, 
                AuthConfig.COGNITO.CLIENT_ID, 
                username=self.cognito_user_id, 
                refresh_token=refresh_token
            )
            
            # Update user state
            self.current_user = username
            self.current_user_pw = password
            self.signed_in = True  # 🔧 Set signed_in flag to True after successful login
            
            # Update saved login info for next startup
            self._update_saved_login_info(username, password)
            
            logger.info(f"Successfully authenticated user: {self.cognito_user_id}")
            logger.info(f"Login successful for user: {username}")
            return True, auth_messages.get_message('login_success')
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Login failed: {traceback.format_exc()}")
            
            if "UserNotConfirmedException" in error_msg:
                return False, auth_messages.get_message('login_user_not_confirmed')
            elif "NotAuthorizedException" in error_msg:
                return False, auth_messages.get_message('login_password_incorrect')
            elif "UserNotFoundException" in error_msg:
                return False, auth_messages.get_message('login_invalid_credentials')
            else:
                return False, auth_messages.get_message('login_failed')
    
    def google_login(self, machine_role: str = "Commander") -> Tuple[bool, str, Dict[str, Any]]:
        """
        Authenticate user with LOCAL Google OAuth (not Hosted UI) and AWS Cognito.
        
        Args:
            machine_role: Machine role for the user
            
        Returns:
            Tuple of (success: bool, message: str, data: dict)
        """
        try:
            from auth.oauth import GoogleOAuthManager, CognitoGoogleIntegration
            
            logger.info(f"Starting LOCAL Google OAuth authentication for role: {machine_role}")
            
            # Initialize authentication components
            try:
                google_oauth = GoogleOAuthManager()  # Use direct Google OAuth, not Hosted UI
                cognito_integration = CognitoGoogleIntegration()
            except ValueError as e:
                logger.error(f"Authentication configuration error: {e}")
                return False, f'Authentication not configured: {str(e)}', {}
            
            # Perform DIRECT Google OAuth authentication (local callback)
            logger.info("Performing DIRECT Google OAuth authentication with local callback")
            google_auth_result = google_oauth.authenticate(timeout=300)
            
            if not google_auth_result['success']:
                logger.error(f"Google OAuth failed: {google_auth_result['error']}")
                return False, google_auth_result['error'], {}
            
            google_tokens = google_auth_result['data']['tokens']
            user_info = google_auth_result['data']['user_info']
            
            logger.info(f"Google OAuth successful for user: {user_info['email']}")
            
            # Integrate with AWS Cognito Identity Pool using Google tokens
            logger.info("Integrating with AWS Cognito Identity Pool using Google tokens")
            identity_result = cognito_integration.authenticate_with_google_token(
                google_tokens, user_info  # Direct Google tokens, not Cognito tokens
            )
            
            if not identity_result['success']:
                logger.error(f"Cognito Identity Pool integration failed: {identity_result['error']}")
                return False, identity_result['error'], {}
            
            # Set up AWS session with temporary credentials from Identity Pool
            aws_credentials = identity_result['data']['aws_credentials']
            self._setup_aws_clients_with_credentials(aws_credentials)
            
            # Set role and user data
            self.set_role(machine_role)
            self.current_user = user_info['email']
            self.current_user_pw = "cognito_google_oauth"  # Updated placeholder
            
            # For Google OAuth, first update saved login info with Google user, then get Cognito User Pool tokens
            google_email = user_info.get('email', '')
            
            # Update saved login info immediately with Google user information
            saved_info = self.get_saved_login_info()
            password = saved_info.get('password', '')
            
            if password and google_email:
                self._update_saved_login_info(google_email, password)
               # For Google OAuth, try to get Cognito User Pool tokens using saved credentials
            try:
                cognito_result = self._authenticate_with_cognito_user_pool_google(
                    google_tokens.get('id_token', ''), 
                    user_info
                )
                
                if cognito_result['success']:
                    # Use Cognito User Pool tokens for maximum compatibility
                    cognito_tokens = cognito_result['tokens']
                    self.tokens = {
                        "AuthenticationResult": {
                            "AccessToken": cognito_tokens.get('AccessToken', ''),
                            "IdToken": cognito_tokens.get('IdToken', ''),  # Cognito User Pool ID token
                            "RefreshToken": cognito_tokens.get('RefreshToken', ''),
                            "TokenType": "Bearer",
                            "ExpiresIn": cognito_tokens.get('ExpiresIn', 3600)
                        }
                    }
                    self.id_token = cognito_tokens.get('IdToken', '')
                    self.old_access_token = cognito_tokens.get('AccessToken', '')
                    logger.info("Using Cognito User Pool tokens - full AWS API access available")
                else:
                    # Use Google tokens with Identity Pool credentials
                    # This should work if Identity Pool Role Mappings are configured correctly
                    logger.warning("Cognito User Pool authentication failed, using Google tokens with Identity Pool credentials")
                    logger.info("Ensure Identity Pool Role Mappings are configured for Google OAuth users")
                    
                    self.tokens = {
                        "AuthenticationResult": {
                            "AccessToken": google_tokens.get('access_token', ''),
                            "IdToken": google_tokens.get('id_token', ''),  # Google ID token
                            "RefreshToken": google_tokens.get('refresh_token', ''),
                            "TokenType": google_tokens.get('token_type', 'Bearer'),
                            "ExpiresIn": google_tokens.get('expires_in', 3600)
                        }
                    }
                    self.id_token = google_tokens.get('id_token', '')
                    self.old_access_token = google_tokens.get('access_token', '')
                    
                    # Log guidance for fixing permissions
                    logger.info(" To fix Google OAuth permissions, run: python3 auth/fix_google_oauth_permissions.py")
                    
            except Exception as e:
                logger.error(f"Error getting Cognito User Pool tokens: {e}")
                logger.warning("Using Google tokens with Identity Pool credentials as fallback")
                
                # Use Google tokens as fallback
                self.tokens = {
                    "AuthenticationResult": {
                        "AccessToken": google_tokens.get('access_token', ''),
                        "IdToken": google_tokens.get('id_token', ''),
                        "RefreshToken": google_tokens.get('refresh_token', ''),
                        "TokenType": google_tokens.get('token_type', 'Bearer'),
                        "ExpiresIn": google_tokens.get('expires_in', 3600)
                    }
                }
                self.id_token = google_tokens.get('id_token', '')
                self.old_access_token = google_tokens.get('access_token', '')
                
                logger.info(" To fix Google OAuth permissions, run: python3 auth/fix_google_oauth_permissions.py")
            self.cognito_user_id = identity_result['data']['identity_id']
            refresh_token = google_tokens.get('refresh_token', '')

            if refresh_token:
                self.cog = Cognito(
                    AuthConfig.COGNITO.USER_POOL_ID,
                    AuthConfig.COGNITO.CLIENT_ID,
                    username=self.cognito_user_id,
                    refresh_token=refresh_token
                )
                logger.info(f"Cognito client initialized for user: {self.cognito_user_id}")
            else:
                logger.warning("No refresh token available for Cognito client setup")
                self.cog = None

            # Set up AWS clients with temporary credentials
            aws_credentials = identity_result['data']['aws_credentials']
            self._setup_aws_clients_with_credentials(aws_credentials)
            
            self.signed_in = True
            logger.info(f"Cognito login state set: signed_in={self.signed_in}, user={self.current_user}")
            
            # Prepare response data
            response_data = {
                'user_info': {
                    'email': user_info['email'],
                    'name': user_info['name'],
                    'picture': user_info.get('picture', ''),
                    'verified_email': user_info.get('email_verified', False)
                },
                'aws_credentials': aws_credentials,
                'identity_id': identity_result['data']['identity_id']
            }
            
            logger.info(f"Cognito Google login successful for user: {user_info['email']}")
            return True, auth_messages.get_message('login_success'), response_data
            
        except Exception as e:
            logger.error(f"Cognito Google login failed: {e}")
            logger.error(traceback.format_exc())
            return False, f'Cognito Google login failed: {str(e)}', {}
    
    def sign_up(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Sign up new user with AWS Cognito.
        
        Args:
            username: User email
            password: User password
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            response = self.aws_client.sign_up(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username,
                Password=password,
                UserAttributes=[{"Name": "email", "Value": username}]
            )
            logger.info(f"Sign up successful for user: {username}")
            return True, auth_messages.get_message('signup_success')
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Sign up failed: {error_msg}")
            if "UsernameExistsException" in error_msg:
                return False, auth_messages.get_message('signup_user_exists')
            elif "InvalidPasswordException" in error_msg:
                return False, auth_messages.get_message('signup_invalid_password')
            elif "InvalidParameterException" in error_msg:
                return False, auth_messages.get_message('signup_invalid_email')
            else:
                return False, auth_messages.get_message('signup_failed')    
    
    def forgot_password(self, username: str) -> Tuple[bool, str]:
        """
        Initiate forgot password flow.
        
        Args:
            username: User email
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            self.aws_client.forgot_password(ClientId=AuthConfig.COGNITO.CLIENT_ID, Username=username)
            logger.info("Forgot password initiated successfully")
            return True, auth_messages.get_message('forgot_password_sent')
            
        except Exception as e:
            logger.error(f"Forgot password error: {str(e)}")
            return False, auth_messages.get_message('forgot_password_failed') + f" reset: {str(e)}"
    
    def confirm_forgot_password(self, username: str, confirm_code: str, new_password: str) -> Tuple[bool, str]:
        """
        Confirm forgot password with verification code.
        
        Args:
            username: User email
            confirm_code: Verification code from email
            new_password: New password
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            response = self.aws_client.confirm_forgot_password(
                ClientId=AuthConfig.COGNITO.CLIENT_ID, 
                Username=username,
                ConfirmationCode=confirm_code,
                Password=new_password
            )
            logger.info(f"Password reset confirmed for user: {username}")
            return True, auth_messages.get_message('confirm_forgot_success')
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Confirm forgot password failed: {error_msg}")
            
            if "CodeMismatchException" in error_msg:
                return False, auth_messages.get_message('confirm_forgot_invalid_code')
            elif "ExpiredCodeException" in error_msg:
                return False, auth_messages.get_message('confirm_forgot_expired_code')
            elif "InvalidPasswordException" in error_msg:
                return False, auth_messages.get_message('confirm_forgot_invalid_password')
            elif "UserNotFoundException" in error_msg:
                return False, auth_messages.get_message('confirm_forgot_user_not_found')
            else:
                return False, auth_messages.get_message('confirm_forgot_failed')
    
    def logout(self) -> bool:
        """Logout current user."""
        try:
            # Try to logout from Cognito if we have valid tokens
            if self.cog and hasattr(self.cog, 'access_token') and self.cog.access_token:
                try:
                    self.cog.logout()
                except Exception as logout_error:
                    logger.warning(f"Cognito logout failed, but continuing with local logout: {logout_error}")
            
            # Always clear user state regardless of Cognito logout success
            self.current_user = ""
            self.current_user_pw = ""
            self.signed_in = False
            self.tokens = None
            self.id_token = None
            self.old_access_token = None
            self.cognito_user_id = None
            self.cog = None
            
            logger.info(auth_messages.get_message('logout_success'))
            return True
            
        except Exception as e:
            logger.error(f"{auth_messages.get_message('logout_failed')}: {e}")
            # Even if logout fails, clear local state
            self.current_user = ""
            self.current_user_pw = ""
            self.signed_in = False
            self.tokens = None
            self.id_token = None
            self.old_access_token = None
            self.cognito_user_id = None
            self.cog = None
            return False
    
    async def refresh_tokens_periodically(self, refresh_token: str, interval: int = 2700) -> None:
        """Refresh tokens periodically using the refresh token."""
        while True:
            await asyncio.sleep(interval)  # Wait for 45 minutes
            
            try:
                secret_hash = self.get_secret_hash(self.cognito_user_id)
                
                response = self.aws_client.initiate_auth(
                    ClientId=AuthConfig.COGNITO.CLIENT_ID,
                    AuthFlow='REFRESH_TOKEN_AUTH',
                    AuthParameters={'REFRESH_TOKEN': refresh_token}
                )
                
                if 'AuthenticationResult' in response:
                    self.tokens["AuthenticationResult"]["IdToken"] = response['AuthenticationResult']['IdToken']
                    self.tokens["AuthenticationResult"]["AccessToken"] = response['AuthenticationResult']['AccessToken']
                    logger.info("Tokens refreshed successfully")
                else:
                    raise Exception("AuthenticationResult not found in the response")
                    
            except Exception as e:
                logger.error(f"Error refreshing tokens: {traceback.format_exc()}")
    
    def get_tokens(self) -> Optional[Dict[str, Any]]:
        """Get current authentication tokens."""
        return self.tokens
    
    def _authenticate_with_cognito_user_pool_google(self, google_id_token: str, user_info: Dict) -> Dict:
        """
        Authenticate Google OAuth user with Cognito User Pool, updating saved credentials with Google user info.
        
        Args:
            google_id_token: Google ID token
            user_info: Google user information
            
        Returns:
            Dict containing success status and Cognito User Pool tokens
        """
        try:
            from pycognito import Cognito
            
            # Use Google user email as the username for Cognito User Pool
            google_email = user_info.get('email', '')
            if not google_email:
                logger.warning("No Google email found in user info")
                return {
                    'success': False,
                    'error': 'No Google email found in user info'
                }
            
            # Get saved login credentials for password
            saved_info = self.get_saved_login_info()
            password = saved_info.get('password', '')
            
            if not password:
                logger.warning("No saved password found for Cognito authentication")
                return {
                    'success': False,
                    'error': 'No saved password found for Cognito authentication'
                }
            
            logger.info(f"Authenticating Google OAuth user with Cognito User Pool: {google_email}")
            
            # Create Cognito client and authenticate with Google email as username
            cog = Cognito(
                AuthConfig.COGNITO.USER_POOL_ID,
                AuthConfig.COGNITO.CLIENT_ID,
                username=google_email
            )
            
            try:
                # Try to authenticate with existing user
                cog.authenticate(password=password)
                
                # Get the tokens
                tokens = {
                    'AccessToken': cog.access_token,
                    'IdToken': cog.id_token,
                    'RefreshToken': cog.refresh_token,
                    'ExpiresIn': 3600
                }
                
                # Login info already updated in main flow, no need to update again
                
                logger.info(f"Successfully authenticated existing Cognito User Pool user: {google_email}")
                
                return {
                    'success': True,
                    'tokens': tokens
                }
                
            except Exception as auth_error:
                # Check if user doesn't exist (expected for first-time Google OAuth users)
                if "NotAuthorizedException" in str(auth_error) and "Incorrect username or password" in str(auth_error):
                    logger.info(f"First-time Google OAuth user detected: {google_email}")
                    logger.info("Creating Cognito User Pool account for seamless future access...")
                else:
                    logger.warning(f"Cognito User Pool authentication failed: {auth_error}")
                
                # Try to create user if it doesn't exist
                try:
                    logger.info(f"Setting up Cognito User Pool account for Google user: {google_email}")
                    
                    # Create user using admin privileges with current AWS credentials
                    import boto3
                    
                    # Use the current AWS session with temporary credentials from Identity Pool
                    if hasattr(self, 'aws_session') and self.aws_session:
                        cognito_client = self.aws_session.client('cognito-idp', region_name=AuthConfig.COGNITO.REGION)
                    else:
                        # Fallback to default credentials
                        cognito_client = boto3.client('cognito-idp', region_name=AuthConfig.COGNITO.REGION)
                    
                    # Create user with admin privileges
                    cognito_client.admin_create_user(
                        UserPoolId=AuthConfig.COGNITO.USER_POOL_ID,
                        Username=google_email,
                        TemporaryPassword=password,
                        MessageAction='SUPPRESS',  # Don't send welcome email
                        UserAttributes=[
                            {
                                'Name': 'email',
                                'Value': google_email
                            },
                            {
                                'Name': 'email_verified',
                                'Value': 'true'
                            }
                        ]
                    )
                    
                    # Set permanent password
                    cognito_client.admin_set_user_password(
                        UserPoolId=AuthConfig.COGNITO.USER_POOL_ID,
                        Username=google_email,
                        Password=password,
                        Permanent=True
                    )
                    
                    logger.info(f"✅ Successfully created Cognito User Pool account for Google user: {google_email}")
                    
                    # Now try to authenticate again
                    cog.authenticate(password=password)
                    
                    # Get the tokens
                    tokens = {
                        'AccessToken': cog.access_token,
                        'IdToken': cog.id_token,
                        'RefreshToken': cog.refresh_token,
                        'ExpiresIn': 3600
                    }
                    
                    # Login info already updated in main flow, no need to update again
                    
                    logger.info("✅ Google OAuth user now has full Cognito User Pool access")
                    
                    return {
                        'success': True,
                        'tokens': tokens
                    }
                    
                except Exception as create_error:
                    logger.error(f"Failed to create Cognito User Pool user: {create_error}")
                    
                    # Check if it's a permission error
                    if "AccessDeniedException" in str(create_error):
                        logger.error("SOLUTION: Add cognito-idp:AdminCreateUser permission to AWS user, or manually create user in Cognito Console")
                        logger.error(f"Manual steps: 1) Go to AWS Cognito Console 2) Create user: {google_email} 3) Set password and verify email")
                    
                    raise auth_error  # Re-raise the original authentication error
            
        except Exception as e:
            logger.error(f"Error authenticating with Cognito User Pool: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _store_credentials(self, username: str, password: str) -> bool:
        """Securely store credentials in the system keyring."""
        try:
            keyring.set_password("ecbot_auth", username, password)
            return True
        except Exception as e:
            logger.error(f"Failed to store credentials: {e}")
            return False

    def _get_credentials(self, username: str) -> Tuple[bool, str]:
        """Retrieve credentials from the system keyring."""
        try:
            password = keyring.get_password("ecbot_auth", username)
            if password is None:
                return False, "No password found"
            return True, password
        except Exception as e:
            return False, str(e)

    def get_saved_login_info(self) -> Dict[str, str]:
        """Get saved login information from keyring storage."""
        try:
            # Get username from uli.json if it exists
            username = ""
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r') as f:
                        data = json.load(f)
                        username = data.get("user", "")
                except Exception as e:
                    logger.warning(f"Error reading username from {self.acct_file}: {e}")
            
            # Get password from keyring if username exists
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
            return {
                "machine_role": self.machine_role,
                "username": "",
                "password": ""
            }
    

    def _update_saved_login_info(self, username: str, password: str) -> bool:
        """Update saved login information with new username and password."""
        try:
            # Update username in uli.json
            data = {}
            if exists(self.acct_file):
                try:
                    with open(self.acct_file, 'r') as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading {self.acct_file}: {e}")
            
            data["user"] = username
            
            # Save updated data
            try:
                with open(self.acct_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Error writing to {self.acct_file}: {e}")
            
            # Store password in keyring
            if not self._store_credentials(username, password):
                logger.error("Failed to store password")
                return False
                
            logger.info(f"Updated login info for user: {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating login info: {e}")
            return False
    

    # def scramble(self, word: str) -> str:
    #     """Scramble password for storage."""
    #     min_val = 33
    #     max_val = 126
    #     word_list = list(word)
        
    #     for i in range(len(word_list)):
    #         asc = ord(word_list[i]) - (i + 1)
    #         if asc < min_val:
    #             asc = max_val - (min_val - asc) + 1
    #         word_list[i] = chr(asc)
        
    #     return ''.join(word_list)
    
    # def descramble(self, word: str) -> str:
    #     """Descramble password from storage."""
    #     min_val = 33
    #     max_val = 126
    #     word_list = list(word)
        
    #     for i in range(len(word_list)):
    #         asc = ord(word_list[i]) + (i + 1)
    #         if asc > max_val:
    #             asc = min_val + (asc - max_val) - 1
    #         word_list[i] = chr(asc)
        
    #     return ''.join(word_list)
