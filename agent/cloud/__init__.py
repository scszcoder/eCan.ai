"""
Cloud services module for eCan.ai

Provides unified interfaces for cloud storage and services.
"""

from .s3_storage_service import (
    S3StorageConfig,
    S3StorageService,
    create_s3_storage_service
)

from .standard_s3_uploader import (
    StandardS3Uploader,
    S3PathGenerator,
    create_standard_uploader
)

from .cloud_utils import (
    get_content_type,
    get_resource_url,
    validate_file_size,
    get_file_hash
)

__all__ = [
    # S3 Storage Service (boto3 wrapper)
    'S3StorageConfig',
    'S3StorageService',
    'create_s3_storage_service',
    
    # Standard S3 Uploader (high-level interface)
    'StandardS3Uploader',
    'S3PathGenerator',
    'create_standard_uploader',
    
    # Cloud Utilities (common functions)
    'get_content_type',
    'get_resource_url',
    'validate_file_size',
    'get_file_hash',
]
