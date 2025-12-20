"""
Common cloud storage utility functions

Provides generic functionality across resource types:
- Content type detection
- Resource URL retrieval
- Path conversion
"""

from pathlib import Path
from typing import Optional, Any

from utils.logger_helper import logger_helper as logger


def get_content_type(file_path: str) -> str:
    """
    Get Content-Type (MIME type) based on file extension
    
    This is a generic function that supports multiple file types including images, videos, and documents.
    
    Args:
        file_path: File path
        
    Returns:
        MIME type string, defaults to 'application/octet-stream'
        
    Example:
        >>> get_content_type('/path/to/image.png')
        'image/png'
        >>> get_content_type('/path/to/video.mp4')
        'video/mp4'
        >>> get_content_type('/path/to/document.pdf')
        'application/pdf'
    """
    ext = Path(file_path).suffix.lower()
    
    content_types = {
        # Images
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
        
        # Videos
        '.mp4': 'video/mp4',
        '.webm': 'video/webm',
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.mkv': 'video/x-matroska',
        '.flv': 'video/x-flv',
        
        # Audio
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        
        # Documents
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        
        # Archives
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed',
        '.tar': 'application/x-tar',
        '.gz': 'application/gzip',
        
        # Text
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.html': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
    }
    
    return content_types.get(ext, 'application/octet-stream')


def get_resource_url(
    cloud_service,
    resource: Any,
    file_type: str = 'image',
    use_cdn: bool = True,
    expires_in: int = 3600
) -> Optional[str]:
    """
    Get resource access URL (cloud first, fallback to local)
    
    This is a generic function that can be used for any resource type with cloud storage.
    
    Args:
        cloud_service: S3StorageService instance (can be None)
        resource: Resource object, should have the following attributes:
                 - cloud_{file_type}_key: Cloud storage key
                 - {file_type}_path: Local file path
        file_type: File type identifier (image, video, document, etc.)
        use_cdn: Whether to use CDN
        expires_in: URL expiration time (seconds), 0 means permanent
        
    Returns:
        Access URL string, or None (if file doesn't exist)
        
    Example:
        >>> # Avatar resource
        >>> url = get_resource_url(s3_service, avatar_resource, 'image')
        
        >>> # Document resource
        >>> url = get_resource_url(s3_service, document_resource, 'document')
    """
    # Cloud service not enabled, return local path
    if not cloud_service:
        local_path = getattr(resource, f'{file_type}_path', None)
        return local_path
    
    try:
        # Prefer cloud URL
        cloud_key_attr = f'cloud_{file_type}_key'
        cloud_key = getattr(resource, cloud_key_attr, None)
        
        if cloud_key:
            url = cloud_service.get_file_url(
                cloud_key,
                expires_in=expires_in,
                use_cdn=use_cdn
            )
            return url
        else:
            # Cloud key doesn't exist, fallback to local path
            local_path = getattr(resource, f'{file_type}_path', None)
            return local_path
            
    except Exception as e:
        # Failed to get cloud URL, fallback to local path
        logger.warning(f"Failed to get cloud URL for {file_type}, falling back to local: {e}")
        local_path = getattr(resource, f'{file_type}_path', None)
        return local_path


def validate_file_size(file_path: str, max_size_mb: int = 100) -> tuple[bool, Optional[str]]:
    """
    Validate file size
    
    Args:
        file_path: File path
        max_size_mb: Maximum file size (MB)
        
    Returns:
        (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_file_size('/path/to/large_file.mp4', max_size_mb=50)
        >>> if not valid:
        ...     print(error)
    """
    try:
        import os
        
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if file_size > max_size_bytes:
            actual_size_mb = file_size / (1024 * 1024)
            return False, f"File too large: {actual_size_mb:.2f}MB (max: {max_size_mb}MB)"
        
        return True, None
        
    except Exception as e:
        return False, f"Error validating file size: {e}"


def get_file_hash(file_path: str, algorithm: str = 'sha256') -> Optional[str]:
    """
    Calculate file hash value
    
    Args:
        file_path: File path
        algorithm: Hash algorithm (md5, sha1, sha256)
        
    Returns:
        Hash value string, or None (if failed)
        
    Example:
        >>> hash_value = get_file_hash('/path/to/file.png')
        >>> print(hash_value)
        'a1b2c3d4e5f6...'
    """
    try:
        import hashlib
        
        hash_func = getattr(hashlib, algorithm)()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
        
    except Exception as e:
        logger.error(f"Error calculating file hash: {e}")
        return None
