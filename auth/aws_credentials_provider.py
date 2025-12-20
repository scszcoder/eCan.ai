"""
AWS Credentials Provider using Cognito Identity Pool.

This module provides AWS temporary credentials by exchanging Cognito ID tokens
for AWS credentials through Cognito Identity Pool.
"""

import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from utils.logger_helper import logger_helper as logger


class AWSCredentialsProvider:
    """
    Provides AWS temporary credentials using Cognito Identity Pool.
    
    This class exchanges Cognito ID tokens for AWS temporary credentials
    that can be used to access AWS services like S3.
    """
    
    def __init__(self, identity_pool_id: str, region: str, user_pool_id: str):
        """
        Initialize AWS credentials provider.
        
        Args:
            identity_pool_id: Cognito Identity Pool ID
            region: AWS region
            user_pool_id: Cognito User Pool ID
        """
        self.identity_pool_id = identity_pool_id
        self.region = region
        self.user_pool_id = user_pool_id
        
        # Cache for credentials
        self._cached_credentials: Optional[Dict[str, Any]] = None
        self._credentials_expiry: Optional[datetime] = None
        
        # Initialize Cognito Identity client
        self._identity_client = boto3.client(
            'cognito-identity',
            region_name=region
        )
    
    def get_credentials(self, id_token: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get AWS temporary credentials using Cognito ID token.
        
        Args:
            id_token: Cognito ID token from authentication
            force_refresh: Force refresh even if cached credentials are valid
        
        Returns:
            Dictionary with AWS credentials:
            {
                'AccessKeyId': str,
                'SecretKey': str,
                'SessionToken': str,
                'Expiration': datetime
            }
            Or None if failed
        """
        # Check if cached credentials are still valid
        if not force_refresh and self._is_credentials_valid():
            logger.debug("[AWSCredentials] Using cached credentials")
            return self._cached_credentials
        
        try:
            # Step 1: Get Identity ID
            identity_id = self._get_identity_id(id_token)
            if not identity_id:
                logger.error("[AWSCredentials] Failed to get identity ID")
                return None
            
            # Step 2: Get credentials for identity
            credentials = self._get_credentials_for_identity(identity_id, id_token)
            if not credentials:
                logger.error("[AWSCredentials] Failed to get credentials")
                return None
            
            # Cache credentials
            self._cached_credentials = credentials
            self._credentials_expiry = credentials.get('Expiration')
            
            logger.info(f"[AWSCredentials] ✅ Got AWS credentials, expires at {self._credentials_expiry}")
            return credentials
            
        except Exception as e:
            logger.error(f"[AWSCredentials] ❌ Failed to get credentials: {e}")
            return None
    
    def _get_identity_id(self, id_token: str) -> Optional[str]:
        """
        Get Cognito Identity ID using ID token.
        
        Args:
            id_token: Cognito ID token
        
        Returns:
            Identity ID or None if failed
        """
        try:
            # Build the logins map
            # Format: cognito-idp.{region}.amazonaws.com/{user_pool_id}
            provider_name = f"cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
            
            response = self._identity_client.get_id(
                IdentityPoolId=self.identity_pool_id,
                Logins={
                    provider_name: id_token
                }
            )
            
            identity_id = response.get('IdentityId')
            logger.debug(f"[AWSCredentials] Got identity ID: {identity_id}")
            return identity_id
            
        except ClientError as e:
            logger.error(f"[AWSCredentials] Failed to get identity ID: {e}")
            return None
    
    def _get_credentials_for_identity(
        self,
        identity_id: str,
        id_token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get AWS credentials for a Cognito identity.
        
        Args:
            identity_id: Cognito Identity ID
            id_token: Cognito ID token
        
        Returns:
            AWS credentials dictionary or None if failed
        """
        try:
            provider_name = f"cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
            
            response = self._identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins={
                    provider_name: id_token
                }
            )
            
            credentials = response.get('Credentials', {})
            
            # AWS Cognito Identity returns 'SecretKey', not 'SecretAccessKey'
            return {
                'AccessKeyId': credentials.get('AccessKeyId'),
                'SecretKey': credentials.get('SecretKey'),
                'SessionToken': credentials.get('SessionToken'),
                'Expiration': credentials.get('Expiration'),
                'IdentityId': identity_id  # Add Identity ID for S3 path
            }
            
        except ClientError as e:
            logger.error(f"[AWSCredentials] Failed to get credentials for identity: {e}")
            return None
    
    def _is_credentials_valid(self) -> bool:
        """
        Check if cached credentials are still valid.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        if not self._cached_credentials or not self._credentials_expiry:
            return False
        
        # Consider credentials invalid if they expire in less than 5 minutes
        buffer_time = timedelta(minutes=5)
        now = datetime.now(self._credentials_expiry.tzinfo)
        
        return now + buffer_time < self._credentials_expiry
    
    def clear_cache(self):
        """Clear cached credentials."""
        self._cached_credentials = None
        self._credentials_expiry = None
        logger.debug("[AWSCredentials] Credentials cache cleared")


def create_credentials_provider() -> Optional[AWSCredentialsProvider]:
    """
    Create AWS credentials provider from auth configuration.
    
    Returns:
        AWSCredentialsProvider instance or None if not configured
    """
    try:
        from auth.auth_config import AuthConfig
        
        identity_pool_id = AuthConfig.COGNITO.IDENTITY_POOL_ID
        region = AuthConfig.COGNITO.REGION
        user_pool_id = AuthConfig.COGNITO.USER_POOL_ID
        
        if not identity_pool_id or not region or not user_pool_id:
            logger.warning("[AWSCredentials] Cognito Identity Pool not configured")
            return None
        
        return AWSCredentialsProvider(identity_pool_id, region, user_pool_id)
        
    except Exception as e:
        logger.error(f"[AWSCredentials] Failed to create credentials provider: {e}")
        return None
