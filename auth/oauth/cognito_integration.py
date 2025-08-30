"""
AWS Cognito Integration for Google OAuth

This module integrates Google OAuth tokens with AWS Cognito User Pool and Identity Pool
to provide AWS credentials and unified authentication.
"""

import json
import base64
import time
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pycognito import Cognito

from auth.auth_config import AuthConfig
from utils.logger_helper import logger_helper as logger


class CognitoGoogleIntegration:
    """
    Integrates Google OAuth with AWS Cognito for unified authentication
    """
    
    def __init__(self):
        """
        Initialize Cognito integration
        
        Args:
            
        """
        
        # Cognito configuration
        self.user_pool_id = AuthConfig.COGNITO.USER_POOL_ID
        self.client_id = AuthConfig.COGNITO.CLIENT_ID
        self.identity_pool_id = AuthConfig.COGNITO.IDENTITY_POOL_ID
        self.region = AuthConfig.COGNITO.REGION
        
        # Google Identity Provider configuration
        self.google_provider_name = AuthConfig.COGNITO.GOOGLE_PROVIDER.PROVIDER_NAME
        self.google_provider_client_id = AuthConfig.COGNITO.GOOGLE_PROVIDER.CLIENT_ID
        
        if not all([self.user_pool_id, self.client_id, self.identity_pool_id]):
            raise ValueError("AWS Cognito configuration not complete")
        
        if not all([self.google_provider_name, self.google_provider_client_id]):
            raise ValueError("Google Identity Provider configuration not complete")
        
        # Initialize Cognito client
        self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
        self.identity_client = boto3.client('cognito-identity', region_name=self.region)
        
        # Log essential configuration for debugging (mask sensitive parts)
        masked_client_id = (
            f"{self.google_provider_client_id[:6]}...{self.google_provider_client_id[-8:]}"
            if self.google_provider_client_id and len(self.google_provider_client_id) > 14 else "<unset>"
        )
        logger.info(
            f"Cognito Google integration initialized | region={self.region} | "
            f"identity_pool_id={self.identity_pool_id} | default_google_provider={self.google_provider_name} | "
            f"google_client_id={masked_client_id}"
        )
    
    def authenticate_with_google_token(self, google_tokens: Dict[str, Any], user_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Authenticate with Cognito using Google tokens
        
        Args:
            google_tokens: Google OAuth tokens
            user_info: Google user information
            
        Returns:
            Dict containing Cognito authentication result
        """
        try:
            logger.info(f"Authenticating with Cognito for user: {user_info['email']}")
            
            # Use Google ID token directly with Identity Pool (this is the correct flow for GoogleOAuthManager)
            google_id_token = google_tokens.get('id_token')
            if google_id_token:
                logger.info("Using Google ID token for Cognito Identity Pool authentication")
                identity_result = self._get_identity_credentials(google_id_token)
            else:
                logger.error("Google ID token not available for Cognito integration")
                return {
                    'success': False,
                    'error': 'Google ID token not available. Check GoogleOAuthManager token response.'
                }
            
            if not identity_result['success']:
                return identity_result
            
            # Get AWS credentials
            aws_credentials = identity_result['data']['credentials']
            identity_id = identity_result['data']['identity_id']
            
            logger.info(f"Cognito authentication successful for user: {user_info['email']}")
            
            return {
                'success': True,
                'data': {
                    'identity_id': identity_id,
                    'aws_credentials': {
                        'access_key': aws_credentials['AccessKeyId'],
                        'secret_key': aws_credentials['SecretKey'],
                        'session_token': aws_credentials['SessionToken'],
                        'expiration': aws_credentials['Expiration'].isoformat()
                    },
                    'google_tokens': google_tokens,
                    'user_info': user_info
                }
            }
            
        except Exception as e:
            logger.error(f"Cognito authentication failed: {e}")
            return {
                'success': False,
                'error': f'Cognito authentication failed: {str(e)}'
            }
    
    def _get_identity_credentials(self, google_id_token: str) -> Dict[str, Any]:
        """
        Get AWS credentials from Cognito Identity Pool using Google ID token
        
        Args:
            google_id_token: Google ID token
            
        Returns:
            Dict containing identity credentials or error
        """
        try:
            logger.debug("Getting identity credentials from Cognito Identity Pool")
            logins = {self.google_provider_name: google_id_token}
            # Safe diagnostics
            token_snippet = self._safe_token_snippet(google_id_token)
            claims = self._jwt_claims(google_id_token)
            logger.debug(
                "get_id() context | identity_pool_id=%s | provider=%s | logins_keys=%s | token=%s | claims.iss=%s | claims.aud=%s",
                self.identity_pool_id,
                self.google_provider_name,
                list(logins.keys()),
                token_snippet,
                claims.get('iss'),
                claims.get('aud')
            )
            
            # Get identity ID
            identity_response = self.identity_client.get_id(
                IdentityPoolId=self.identity_pool_id,
                Logins=logins
            )
            identity_id = identity_response['IdentityId']
            logger.debug(f"Got identity ID: {identity_id}")
            
            logger.debug(
                "get_credentials_for_identity() context | identity_id=%s | provider=%s | logins_keys=%s | token=%s",
                identity_id,
                self.google_provider_name,
                list(logins.keys()),
                token_snippet,
            )
            # Get credentials for identity
            credentials_response = self.identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins=logins
            )
            
            credentials = credentials_response['Credentials']
            logger.info("AWS credentials obtained successfully")
            
            return {
                'success': True,
                'data': {
                    'identity_id': identity_id,
                    'credentials': credentials
                }
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(
                "AWS Cognito error (%s): %s | identity_pool_id=%s | provider=%s",
                error_code,
                error_message,
                self.identity_pool_id,
                self.google_provider_name,
            )
            
            return {
                'success': False,
                'error': f'AWS Cognito error: {error_message}'
            }
        except Exception as e:
            logger.error(f"Unexpected error getting identity credentials: {e}")
            return {
                'success': False,
                'error': f'Identity credentials error: {str(e)}'
            }
    
    def refresh_aws_credentials(self, identity_id: str, google_id_token: str) -> Dict[str, Any]:
        """
        Deprecated: use refresh_aws_credentials_user_pool() when possible.
        This method refreshes credentials using Google provider key; retained for backward compatibility.
        """
        logger.warning("refresh_aws_credentials() is deprecated. Prefer refresh_aws_credentials_user_pool() with a Cognito id_token.")
        try:
            logger.debug("Refreshing AWS credentials (legacy Google provider)")
            logins = {self.google_provider_name: google_id_token}
            token_snippet = self._safe_token_snippet(google_id_token)
            logger.debug(
                "refresh.get_credentials_for_identity(Google) | identity_id=%s | provider=%s | logins_keys=%s | token=%s",
                identity_id,
                self.google_provider_name,
                list(logins.keys()),
                token_snippet,
            )
            credentials_response = self.identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins=logins
            )
            credentials = credentials_response['Credentials']
            logger.info("AWS credentials refreshed successfully (legacy Google provider)")
            return {
                'success': True,
                'data': {
                    'aws_credentials': {
                        'access_key': credentials['AccessKeyId'],
                        'secret_key': credentials['SecretKey'],
                        'session_token': credentials['SessionToken'],
                        'expiration': credentials['Expiration'].isoformat()
                    }
                }
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS credentials refresh error (legacy {error_code}): {error_message}")
            return {
                'success': False,
                'error': f'Credentials refresh error (legacy): {error_message}'
            }
        except Exception as e:
            logger.error(f"Unexpected error refreshing credentials (legacy Google): {e}")
            return {
                'success': False,
                'error': f'Credentials refresh error (legacy): {str(e)}'
            }

    def refresh_aws_credentials_unified(self, identity_id: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unified refresh: prefers User Pool provider if 'cognito_id_token' is present in tokens;
        otherwise falls back to Google 'id_token'.
        """
        cognito_id_token = tokens.get('cognito_id_token') if isinstance(tokens, dict) else None
        if cognito_id_token:
            return self.refresh_aws_credentials_user_pool(identity_id, cognito_id_token)
        google_id_token = tokens.get('id_token') if isinstance(tokens, dict) else None
        if google_id_token:
            return self.refresh_aws_credentials(identity_id, google_id_token)
        logger.error("refresh_aws_credentials_unified: No valid token found. Expect 'cognito_id_token' or 'id_token'.")
        return {
            'success': False,
            'error': "No valid token provided for refresh."
        }
    
    def create_aws_session(self, aws_credentials: Dict[str, str]) -> boto3.Session:
        """
        Create AWS session with temporary credentials
        
        Args:
            aws_credentials: AWS credentials dict
            
        Returns:
            Configured boto3 session
        """
        return boto3.Session(
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials['session_token'],
            region_name=self.region
        )
    
    def validate_aws_credentials(self, aws_credentials: Dict[str, str]) -> bool:
        """
        Validate AWS credentials by making a test call
        
        Args:
            aws_credentials: AWS credentials to validate
            
        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            session = self.create_aws_session(aws_credentials)
            sts_client = session.client('sts')
            
            # Test credentials with get_caller_identity
            response = sts_client.get_caller_identity()
            logger.debug(f"AWS credentials valid for: {response.get('Arn', 'Unknown')}")
            return True
            
        except Exception as e:
            logger.warning(f"AWS credentials validation failed: {e}")
            return False
    
    def get_user_attributes(self, access_token: str) -> Dict[str, Any]:
        """
        Get user attributes from Cognito User Pool
        
        Args:
            access_token: Cognito access token
            
        Returns:
            Dict containing user attributes or error
        """
        try:
            logger.debug("Getting user attributes from Cognito User Pool")
            
            response = self.cognito_client.get_user(
                AccessToken=access_token
            )
            
            # Convert attributes list to dict
            attributes = {}
            for attr in response.get('UserAttributes', []):
                attributes[attr['Name']] = attr['Value']
            
            return {
                'success': True,
                'data': {
                    'username': response['Username'],
                    'attributes': attributes,
                    'user_status': response.get('UserStatus'),
                    'mfa_options': response.get('MFAOptions', [])
                }
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Get user attributes error ({error_code}): {error_message}")
            
            return {
                'success': False,
                'error': f'Get user attributes error: {error_message}'
            }
        except Exception as e:
            logger.error(f"Unexpected error getting user attributes: {e}")
            return {
                'success': False,
                'error': f'User attributes error: {str(e)}'
            }

    # --------------------
    # User Pool provider based flows
    # --------------------
    def _user_pool_provider_key(self) -> str:
        """Return the Cognito User Pool provider key for Identity Pool Logins."""
        return f"cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    def _get_identity_credentials_with_user_pool(self, cognito_id_token: str) -> Dict[str, Any]:
        """
        Get AWS credentials from Identity Pool using Cognito User Pool id_token.
        This ensures a unified identity regardless of how the user logged into the User Pool (Google/password/etc.).
        """
        try:
            logger.debug("Getting identity credentials using User Pool provider")
            provider_key = self._user_pool_provider_key()
            logins = {provider_key: cognito_id_token}
            token_snippet = self._safe_token_snippet(cognito_id_token)
            claims = self._jwt_claims(cognito_id_token)
            logger.debug(
                "get_id(UserPool) | identity_pool_id=%s | provider=%s | logins_keys=%s | token=%s | iss=%s | aud=%s",
                self.identity_pool_id,
                provider_key,
                list(logins.keys()),
                token_snippet,
                claims.get('iss'),
                claims.get('aud')
            )

            identity_response = self.identity_client.get_id(
                IdentityPoolId=self.identity_pool_id,
                Logins=logins
            )
            identity_id = identity_response['IdentityId']
            logger.debug(f"Got identity ID (UserPool): {identity_id}")

            logger.debug(
                "get_credentials_for_identity(UserPool) | identity_id=%s | provider=%s | logins_keys=%s | token=%s",
                identity_id,
                provider_key,
                list(logins.keys()),
                token_snippet,
            )
            credentials_response = self.identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins=logins
            )
            credentials = credentials_response['Credentials']
            logger.info("AWS credentials obtained successfully (User Pool provider)")
            return {
                'success': True,
                'data': {
                    'identity_id': identity_id,
                    'credentials': credentials
                }
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(
                "AWS Cognito error (UserPool %s): %s | identity_pool_id=%s | provider=%s",
                error_code,
                error_message,
                self.identity_pool_id,
                self._user_pool_provider_key(),
            )
            return {
                'success': False,
                'error': f'AWS Cognito error (UserPool): {error_message}'
            }
        except Exception as e:
            logger.error(f"Unexpected error getting identity credentials (UserPool): {e}")
            return {
                'success': False,
                'error': f'Identity credentials error (UserPool): {str(e)}'
            }

    def refresh_aws_credentials_user_pool(self, identity_id: str, cognito_id_token: str) -> Dict[str, Any]:
        """Refresh AWS credentials using User Pool provider key and Cognito id_token."""
        try:
            logger.debug("Refreshing AWS credentials (User Pool provider)")
            provider_key = self._user_pool_provider_key()
            logins = {provider_key: cognito_id_token}
            token_snippet = self._safe_token_snippet(cognito_id_token)
            logger.debug(
                "refresh.get_credentials_for_identity(UserPool) | identity_id=%s | provider=%s | logins_keys=%s | token=%s",
                identity_id,
                provider_key,
                list(logins.keys()),
                token_snippet,
            )
            credentials_response = self.identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins=logins
            )
            credentials = credentials_response['Credentials']
            logger.info("AWS credentials refreshed successfully (User Pool provider)")
            return {
                'success': True,
                'data': {
                    'aws_credentials': {
                        'access_key': credentials['AccessKeyId'],
                        'secret_key': credentials['SecretKey'],
                        'session_token': credentials['SessionToken'],
                        'expiration': credentials['Expiration'].isoformat()
                    }
                }
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS credentials refresh error (UserPool {error_code}): {error_message}")
            return {
                'success': False,
                'error': f'Credentials refresh error (UserPool): {error_message}'
            }
        except Exception as e:
            logger.error(f"Unexpected error refreshing credentials (UserPool): {e}")
            return {
                'success': False,
                'error': f'Credentials refresh error (UserPool): {str(e)}'
            }

    # --------------------
    # Internal helpers for logging/debugging
    # --------------------
    def _safe_token_snippet(self, token: Optional[str]) -> str:
        """Return first/last 8 chars of token for logging, without exposing full secret."""
        if not token:
            return "<none>"
        try:
            return f"{token[:8]}...{token[-8:]}"
        except Exception:
            return "<invalid>"

    def _jwt_claims(self, token: Optional[str]) -> Dict[str, Any]:
        """Parse JWT payload to extract basic claims (iss, aud) safely without verification."""
        if not token or token.count('.') != 2:
            return {}
        try:
            parts = token.split('.')
            payload_b64 = parts[1]
            # Pad base64 string
            padding = '=' * (-len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode('utf-8')
            payload = json.loads(payload_json)
            return {k: payload.get(k) for k in ('iss', 'aud', 'exp', 'iat')}
        except Exception:
            return {}
