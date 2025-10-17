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
    
    def is_configured(self) -> bool:
        """Check if S3 is configured."""
        return bool(self.access_key and self.secret_key and self.bucket)


class S3StorageService:
    """AWS S3 storage service."""
    
    def __init__(self, config: S3StorageConfig):
        self.config = config
        self._client = None
    
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
        Upload file to S3.
        
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
    
    def download_file(self, cloud_key: str, local_path: str) -> Tuple[bool, str]:
        """
        Download file from S3.
        
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
    
    def delete_file(self, cloud_key: str) -> Tuple[bool, str]:
        """
        Delete file from S3.
        
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


def create_s3_storage_service(config: S3StorageConfig = None) -> Optional[S3StorageService]:
    """
    Create AWS S3 storage service.
    
    Args:
        config: S3 storage configuration. If None, loads from environment.
    
    Returns:
        S3StorageService instance or None if not configured
    """
    if config is None:
        config = S3StorageConfig.from_env()
    
    if not config.is_configured():
        logger.info("[S3Storage] Not configured, skipping initialization")
        return None
    
    return S3StorageService(config)
