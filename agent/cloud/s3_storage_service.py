"""
AWS S3 cloud storage service for avatar resources.

Features:
- Upload/download files to S3
- Generate signed URLs
- CDN support
- Automatic configuration from environment variables
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from utils.logger_helper import logger_helper as logger


class S3StorageConfig:
    """AWS S3 storage configuration."""
    
    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "",
        region: str = "us-east-1",
        endpoint: str = "",
        cdn_domain: str = "",
        use_ssl: bool = True,
        path_prefix: str = "avatars/"
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self.endpoint = endpoint
        self.cdn_domain = cdn_domain
        self.use_ssl = use_ssl
        self.path_prefix = path_prefix
    
    @classmethod
    def from_env(cls) -> 'S3StorageConfig':
        """Load configuration from environment variables."""
        return cls(
            access_key=os.getenv('AVATAR_CLOUD_ACCESS_KEY') or os.getenv('AWS_ACCESS_KEY_ID', ''),
            secret_key=os.getenv('AVATAR_CLOUD_SECRET_KEY') or os.getenv('AWS_SECRET_ACCESS_KEY', ''),
            bucket=os.getenv('AVATAR_CLOUD_BUCKET', ''),
            region=os.getenv('AVATAR_CLOUD_REGION', 'us-east-1'),
            endpoint=os.getenv('AVATAR_CLOUD_ENDPOINT', ''),
            cdn_domain=os.getenv('AVATAR_CLOUD_CDN_DOMAIN', ''),
            use_ssl=os.getenv('AVATAR_CLOUD_USE_SSL', 'true').lower() == 'true',
            path_prefix=os.getenv('AVATAR_CLOUD_PATH_PREFIX', 'avatars/')
        )
    
    @classmethod
    def from_default(cls, resource_type: str = 'avatar') -> 'S3StorageConfig':
        """
        Load default S3 configuration (hardcoded in code).
        
        This configuration is used when environment variables are not set.
        Uses Cognito temporary credentials by default (no static keys needed).
        
        Args:
            resource_type: Type of resource ('avatar' or 'skill')
        """
        # Different buckets for different resource types
        if resource_type == 'skill':
            bucket = 'ecan-skills'
            path_prefix = ''  # Skills are stored at bucket root level
        else:  # avatar
            bucket = 'ecan-avatars'
            path_prefix = ''  # Avatars are stored at bucket root level
        
        return cls(
            access_key='',  # Empty - will use Cognito temporary credentials
            secret_key='',  # Empty - will use Cognito temporary credentials
            bucket=bucket,  # Resource-specific bucket
            region='us-east-1',  # AWS region
            endpoint='',  # Empty for standard AWS S3
            cdn_domain='',  # Optional: Set CloudFront domain for CDN
            use_ssl=True,  # Always use HTTPS
            path_prefix=path_prefix  # Path prefix (empty for root level)
        )
    
    def is_configured(self) -> bool:
        """
        Check if S3 is configured.
        
        Note: When using Cognito credentials, we only need bucket name.
        Static credentials (access_key/secret_key) are optional.
        """
        return bool(self.bucket)


class S3StorageService:
    """AWS S3 storage service."""
    
    def __init__(self, config: S3StorageConfig, aws_credentials: dict = None):
        """
        Initialize S3 storage service.
        
        Args:
            config: S3 storage configuration
            aws_credentials: Optional AWS temporary credentials from Cognito
                           {'AccessKeyId': str, 'SecretKey': str, 'SessionToken': str, 'IdentityId': str}
        """
        self.config = config
        self.aws_credentials = aws_credentials
        self._client = None
        # Store Identity ID for S3 path generation
        self.identity_id = aws_credentials.get('IdentityId') if aws_credentials else None
    
    def _init_client(self):
        """Initialize S3 client."""
        try:
            import boto3
            from botocore.config import Config
            
            config = Config(
                region_name=self.config.region,
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'standard'}
            )
            
            # Use Cognito temporary credentials if available
            if self.aws_credentials:
                logger.info("[S3Storage] Using Cognito temporary credentials")
                
                self._client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_credentials.get('AccessKeyId'),
                    aws_secret_access_key=self.aws_credentials.get('SecretKey'),
                    aws_session_token=self.aws_credentials.get('SessionToken'),
                    endpoint_url=self.config.endpoint if self.config.endpoint else None,
                    config=config,
                    use_ssl=self.config.use_ssl
                )
            else:
                # Use static credentials from config
                logger.info("[S3Storage] Using static credentials from config")
                self._client = boto3.client(
                    's3',
                    aws_access_key_id=self.config.access_key,
                    aws_secret_access_key=self.config.secret_key,
                    endpoint_url=self.config.endpoint if self.config.endpoint else None,
                    config=config,
                    use_ssl=self.config.use_ssl
                )
            
            logger.info(f"[S3Storage] Initialized for bucket: {self.config.bucket}")
            return True
            
        except ImportError:
            logger.error("[S3Storage] boto3 not installed. Install with: pip install boto3")
            return False
        except Exception as e:
            logger.error(f"[S3Storage] Failed to initialize: {e}")
            return False
    
    def upload_file(
        self,
        local_path: str,
        cloud_key: str,
        content_type: str = None,
        metadata: Dict[str, str] = None
    ) -> Tuple[bool, str, str]:
        """
        Upload file to S3 (synchronous version).
        
        Args:
            local_path: Local file path
            cloud_key: S3 object key
            content_type: File MIME type
            metadata: File metadata
        
        Returns:
            (success, cloud_url, error_message)
        """
        if not self._client:
            if not self._init_client():
                return False, "", "S3 client not initialized"
        
        try:
            # Build full key with prefix
            full_key = f"{self.config.path_prefix}{cloud_key}"
            
            # Prepare upload parameters
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            if metadata:
                extra_args['Metadata'] = metadata
            
            # Upload file
            self._client.upload_file(
                local_path,
                self.config.bucket,
                full_key,
                ExtraArgs=extra_args
            )
            
            # Get URL
            url = self.get_file_url(cloud_key, expires_in=0, use_cdn=False)
            
            logger.info(f"[S3Storage] Uploaded: {full_key}")
            return True, url, ""
            
        except Exception as e:
            error_msg = f"Upload failed: {e}"
            logger.error(f"[S3Storage] {error_msg}")
            return False, "", error_msg
    
    async def upload_file_async(
        self,
        local_path: str,
        cloud_key: str,
        content_type: str = None,
        metadata: Dict[str, str] = None
    ) -> Tuple[bool, str, str]:
        """
        Upload file to S3 asynchronously (non-blocking).
        
        Runs upload in thread pool to avoid blocking the event loop.
        
        Args:
            local_path: Local file path
            cloud_key: S3 object key
            content_type: File MIME type
            metadata: File metadata
        
        Returns:
            (success, cloud_url, error_message)
        """
        import asyncio
        
        try:
            # Run synchronous upload in thread pool
            loop = asyncio.get_running_loop()
            
            result = await loop.run_in_executor(
                None,  # Use default executor instead of creating new one
                lambda: self.upload_file(local_path, cloud_key, content_type, metadata)
            )
            return result
        except Exception as e:
            logger.error(f"[S3Storage] upload_file_async exception: {e}", exc_info=True)
            return False, "", str(e)
    
    def download_file(self, cloud_key: str, local_path: str) -> Tuple[bool, str]:
        """
        Download file from S3 (synchronous version).
        
        Args:
            cloud_key: S3 object key
            local_path: Local save path
        
        Returns:
            (success, error_message)
        """
        if not self._client:
            if not self._init_client():
                return False, "S3 client not initialized"
        
        try:
            full_key = f"{self.config.path_prefix}{cloud_key}"
            
            # Ensure local directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download file
            self._client.download_file(
                self.config.bucket,
                full_key,
                local_path
            )
            
            logger.info(f"[S3Storage] Downloaded: {full_key}")
            return True, ""
            
        except Exception as e:
            error_msg = f"Download failed: {e}"
            logger.error(f"[S3Storage] {error_msg}")
            return False, error_msg
    
    async def download_file_async(self, cloud_key: str, local_path: str) -> Tuple[bool, str]:
        """
        Download file from S3 asynchronously (non-blocking).
        
        Args:
            cloud_key: S3 object key
            local_path: Local save path
        
        Returns:
            (success, error_message)
        """
        import asyncio
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,  # Use default executor
            lambda: self.download_file(cloud_key, local_path)
        )
        return result
    
    def delete_file(self, cloud_key: str) -> Tuple[bool, str]:
        """
        Delete file from S3 (synchronous version).
        
        Args:
            cloud_key: S3 object key
        
        Returns:
            (success, error_message)
        """
        if not self._client:
            if not self._init_client():
                return False, "S3 client not initialized"
        
        try:
            full_key = f"{self.config.path_prefix}{cloud_key}"
            
            self._client.delete_object(
                Bucket=self.config.bucket,
                Key=full_key
            )
            
            logger.info(f"[S3Storage] Deleted: {full_key}")
            return True, ""
            
        except Exception as e:
            error_msg = f"Delete failed: {e}"
            logger.error(f"[S3Storage] {error_msg}")
            return False, error_msg
    
    async def delete_file_async(self, cloud_key: str) -> Tuple[bool, str]:
        """
        Delete file from S3 asynchronously (non-blocking).
        
        Args:
            cloud_key: S3 object key
        
        Returns:
            (success, error_message)
        """
        import asyncio
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,  # Use default executor
            lambda: self.delete_file(cloud_key)
        )
        return result
    
    def get_file_url(
        self,
        cloud_key: str,
        expires_in: int = 3600,
        use_cdn: bool = True
    ) -> str:
        """
        Get file access URL.
        
        Args:
            cloud_key: S3 object key
            expires_in: Expiration time in seconds (0 for permanent)
            use_cdn: Whether to use CDN domain
        
        Returns:
            File access URL
        """
        full_key = f"{self.config.path_prefix}{cloud_key}"
        
        # Use CDN domain if configured
        if use_cdn and self.config.cdn_domain:
            protocol = "https" if self.config.use_ssl else "http"
            return f"{protocol}://{self.config.cdn_domain}/{full_key}"
        
        # Generate signed URL
        if not self._client:
            self._init_client()
        
        try:
            if expires_in > 0:
                # Generate presigned URL
                url = self._client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.config.bucket,
                        'Key': full_key
                    },
                    ExpiresIn=expires_in
                )
            else:
                # Generate public URL
                if self.config.endpoint:
                    url = f"{self.config.endpoint}/{self.config.bucket}/{full_key}"
                else:
                    url = f"https://{self.config.bucket}.s3.{self.config.region}.amazonaws.com/{full_key}"
            
            return url
            
        except Exception as e:
            logger.error(f"[S3Storage] Failed to generate URL: {e}")
            return ""
    
    def file_exists(self, cloud_key: str) -> bool:
        """
        Check if file exists in S3.
        
        Args:
            cloud_key: S3 object key
        
        Returns:
            True if file exists
        """
        if not self._client:
            if not self._init_client():
                return False
        
        try:
            full_key = f"{self.config.path_prefix}{cloud_key}"
            self._client.head_object(
                Bucket=self.config.bucket,
                Key=full_key
            )
            return True
        except:
            return False


def create_s3_storage_service(
    config: S3StorageConfig = None,
    use_cognito_credentials: bool = True
) -> Optional[S3StorageService]:
    """
    Create AWS S3 storage service.
    
    Args:
        config: S3 storage configuration. If None, loads from default config.
        use_cognito_credentials: Whether to use Cognito temporary credentials
    
    Returns:
        S3StorageService instance or None if not configured
    """
    if config is None:
        # Try loading from environment first, fallback to default
        env_config = S3StorageConfig.from_env()
        if env_config.bucket:
            config = env_config
            logger.info("[S3Storage] Using configuration from environment variables")
        else:
            config = S3StorageConfig.from_default()
            logger.info("[S3Storage] Using default hardcoded configuration")
    
    # Try to get Cognito credentials if enabled
    aws_credentials = None
    if use_cognito_credentials:
        try:
            from auth.aws_credentials_provider import create_credentials_provider
            from app_context import AppContext
            
            # Get auth manager from app context
            auth_manager = AppContext.get_auth_manager()
            if auth_manager and auth_manager.is_signed_in():
                tokens = auth_manager.get_tokens()
                id_token = tokens.get('IdToken') or tokens.get('id_token')
                
                if id_token:
                    credentials_provider = create_credentials_provider()
                    if credentials_provider:
                        aws_credentials = credentials_provider.get_credentials(id_token)
                        if aws_credentials:
                            logger.info("[S3Storage] ✅ Using Cognito temporary credentials")
                        else:
                            logger.warning("[S3Storage] Failed to get Cognito credentials, falling back to static config")
        except Exception as e:
            logger.warning(f"[S3Storage] Failed to get Cognito credentials: {e}")
    
    # Check if we have either Cognito credentials or static config
    if not aws_credentials and not config.is_configured():
        logger.info("[S3Storage] Not configured, skipping initialization")
        return None
    
    # If we have Cognito credentials, we don't need static config to be fully configured
    # Just need the bucket name
    if aws_credentials and not config.bucket:
        logger.warning("[S3Storage] Bucket name not configured")
        return None
    
    return S3StorageService(config, aws_credentials)
