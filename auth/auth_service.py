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
from os.path import exists
from typing import Dict, Any, Tuple, Optional

import boto3
import botocore
from pycognito import Cognito, AWSSRP
from botocore.config import Config

from utils.logger_helper import logger_helper as logger
from auth.auth_messages import auth_messages
from auth.auth_config import AuthConfig
from config.app_info import app_info
from bot.envi import getECBotDataHome
from bot.network import commanderIP, commanderServer, commanderXport


class AuthService:
    """Pure business logic class for authentication operations."""
    
    def __init__(self, language: str = 'en-US'):
        self.cog = None
        self.aws_client = None
        self.aws_srp = None
        self.tokens = None
        self.id_token = None
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
                response = requests.get("https://cognito-idp.us-east-1.amazonaws.com", timeout=10)
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
            logger.info(f"Attempting login for user: {username}")
            
            # Check network connectivity
            if not self._check_network_connection():
                logger.error("Network connection check failed")
                return False, "Network connection failed"
            
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
    
    def get_saved_login_info(self) -> Dict[str, str]:
        """Get saved login information from uli.json and environment variables."""
        try:
            # Read from uli.json file
            if exists(self.acct_file):
                with open(self.acct_file, 'r') as jsonfile:
                    data = json.load(jsonfile)
                    
                    username = data.get("user", "")
                    password = ""
                    
                    # Get password from environment variable if it's stored as SCECBOTPW
                    if data.get("pw") == "SCECBOTPW":
                        scrambled_pw = os.environ.get("SCECBOTPW", "")
                        if scrambled_pw:
                            password = self.descramble(scrambled_pw)
                    else:
                        password = data.get("pw", "")
                    
                    return {
                        "machine_role": self.machine_role,
                        "username": username,
                        "password": password
                    }
            
            # Fallback to current values if file doesn't exist
            return {
                "machine_role": self.machine_role,
                "username": self.current_user,
                "password": self.current_user_pw
            }
            
        except Exception as e:
            logger.error(f"Error reading saved login info: {e}")
            return {
                "machine_role": self.machine_role,
                "username": "",
                "password": ""
            }
    

    def scramble(self, word: str) -> str:
        """Scramble password for storage."""
        min_val = 33
        max_val = 126
        word_list = list(word)
        
        for i in range(len(word_list)):
            asc = ord(word_list[i]) - (i + 1)
            if asc < min_val:
                asc = max_val - (min_val - asc) + 1
            word_list[i] = chr(asc)
        
        return ''.join(word_list)
    
    def descramble(self, word: str) -> str:
        """Descramble password from storage."""
        min_val = 33
        max_val = 126
        word_list = list(word)
        
        for i in range(len(word_list)):
            asc = ord(word_list[i]) + (i + 1)
            if asc > max_val:
                asc = min_val + (asc - max_val) - 1
            word_list[i] = chr(asc)
        
        return ''.join(word_list)
