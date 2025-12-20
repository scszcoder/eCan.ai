"""
Standard S3 Uploader - Unified S3 file upload tool

Features:
- Standardized S3 path generation
- Unified metadata format
- Automatic content type detection
- User isolation
- Highly reusable
"""

import os
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

from utils.logger_helper import logger_helper as logger


class S3PathGenerator:
    """S3 Path Generator - Standardized path generation logic"""
    
    @staticmethod
    def generate_path(
        resource_type: str,  # 'avatar', 'document', 'attachment', etc.
        owner: str,
        file_category: str,  # 'image', 'video', 'audio', 'document'
        file_hash: str,
        file_ext: str,
        date_prefix: bool = False
    ) -> str:
        """
        Generate standardized S3 path
        
        Format: {resource_type}s/{owner}/{file_category}s/{file_hash}{ext}
        Or:     {resource_type}s/{owner}/{file_category}s/{date}/{file_hash}{ext}
        
        Args:
            resource_type: Resource type (avatar, document, attachment)
            owner: User identifier (email/username)
            file_category: File category (image, video, audio, document)
            file_hash: File hash value
            file_ext: File extension
            date_prefix: Whether to add date prefix
        
        Returns:
            Standardized S3 path
        
        Examples:
            >>> S3PathGenerator.generate_path('avatar', 'user@example.com', 'image', 'abc123', '.png')
            'avatars/user@example.com/images/abc123.png'
            
            >>> S3PathGenerator.generate_path('document', 'user@example.com', 'pdf', 'xyz789', '.pdf', date_prefix=True)
            'documents/user@example.com/pdfs/2025-01-19/xyz789.pdf'
        """
        # Clean owner (remove path separators)
        safe_owner = owner.replace('/', '_').replace('\\', '_')
        
        # Resource type plural form
        resource_plural = f"{resource_type}s" if not resource_type.endswith('s') else resource_type
        
        # File category plural form
        category_plural = f"{file_category}s" if not file_category.endswith('s') else file_category
        
        # Ensure extension has dot
        if file_ext and not file_ext.startswith('.'):
            file_ext = f'.{file_ext}'
        
        # Build path
        if date_prefix:
            date_str = datetime.utcnow().strftime('%Y-%m-%d')
            return f"{resource_plural}/{safe_owner}/{category_plural}/{date_str}/{file_hash}{file_ext}"
        else:
            return f"{resource_plural}/{safe_owner}/{category_plural}/{file_hash}{file_ext}"
    
    @staticmethod
    def parse_path(s3_path: str) -> Dict[str, str]:
        """
        Parse S3 path and extract information
        
        Args:
            s3_path: S3 path (without bucket)
        
        Returns:
            {
                'resource_type': 'avatars',
                'owner': 'user@example.com',
                'file_category': 'images',
                'file_hash': 'abc123',
                'file_ext': '.png',
                'date': '2025-01-19' (if present)
            }
        
        Examples:
            >>> S3PathGenerator.parse_path('avatars/user@example.com/images/abc123.png')
            {'resource_type': 'avatars', 'owner': 'user@example.com', ...}
        """
        parts = s3_path.split('/')
        
        if len(parts) < 4:
            raise ValueError(f"Invalid S3 path: {s3_path}")
        
        result = {
            'resource_type': parts[0],  # avatars
            'owner': parts[1],           # user@example.com
            'file_category': parts[2],   # images
        }
        
        # Check if date prefix exists
        if len(parts) == 5:
            result['date'] = parts[3]    # 2025-01-19
            filename = parts[4]
        else:
            result['date'] = None
            filename = parts[3]
        
        # Separate filename and extension
        file_hash, file_ext = os.path.splitext(filename)
        result['file_hash'] = file_hash
        result['file_ext'] = file_ext
        
        return result


class StandardS3Uploader:
    """
    Unified S3 upload utility class
    
    Features:
    - Automatically generate standardized S3 paths
    - Unified metadata format
    - Automatic content type detection
    - User isolation
    - Error handling and retry
    """
    
    def __init__(self, s3_service):
        """
        Initialize standard S3 uploader.
        
        Args:
            s3_service: S3StorageService instance
        """
        self.s3_service = s3_service
    
    def upload(
        self,
        local_path: str,
        owner: str,
        resource_type: str,
        resource_id: str,
        file_category: str,
        file_hash: str,
        extra_metadata: Dict[str, str] = None,
        date_prefix: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Standardized upload file to S3
        
        Args:
            local_path: Local file path
            owner: User identifier (email/username)
            resource_type: Resource type (avatar, document, attachment)
            resource_id: Resource ID
            file_category: File category (image, video, audio, document)
            file_hash: File hash (for deduplication and unique identification)
            extra_metadata: Additional metadata
            date_prefix: Whether to add date prefix
        
        Returns:
            (success, cloud_url, error_message)
        
        Examples:
            >>> uploader = StandardS3Uploader(s3_service)
            >>> success, url, error = uploader.upload(
            ...     local_path='/path/to/avatar.png',
            ...     owner='user@example.com',
            ...     resource_type='avatar',
            ...     resource_id='avatar_123',
            ...     file_category='image',
            ...     file_hash='abc123def456'
            ... )
        """
        try:
            # 1. Generate standardized S3 path
            file_ext = Path(local_path).suffix
            s3_key = S3PathGenerator.generate_path(
                resource_type=resource_type,
                owner=owner,
                file_category=file_category,
                file_hash=file_hash,
                file_ext=file_ext,
                date_prefix=date_prefix
            )
            
            logger.info(f"[StandardS3Uploader] Generated S3 key: {s3_key}")
            
            # 2. Auto-detect content type
            content_type = self._detect_content_type(local_path)
            
            # 3. Build standard metadata
            metadata = self._build_standard_metadata(
                owner=owner,
                resource_type=resource_type,
                resource_id=resource_id,
                file_category=file_category,
                extra_metadata=extra_metadata
            )
            
            # 4. Upload to S3
            success, url, error = self.s3_service.upload_file(
                local_path=local_path,
                cloud_key=s3_key,
                content_type=content_type,
                metadata=metadata
            )
            
            if success:
                logger.info(f"[StandardS3Uploader] ✅ Upload successful: {s3_key}")
            else:
                logger.error(f"[StandardS3Uploader] ❌ Upload failed: {error}")
            
            return success, url, error
            
        except Exception as e:
            error_msg = f"Upload error: {str(e)}"
            logger.error(f"[StandardS3Uploader] {error_msg}")
            return False, "", error_msg
    
    async def upload_async(
        self,
        local_path: str,
        owner: str,
        resource_type: str,
        resource_id: str,
        file_category: str,
        file_hash: str,
        extra_metadata: Dict[str, str] = None,
        date_prefix: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Standardized asynchronous upload file to S3 (non-blocking).
        
        Args:
            local_path: Local file path
            owner: User identifier (email/username)
            resource_type: Resource type (avatar, document, attachment)
            resource_id: Resource ID
            file_category: File category (image, video, audio, document)
            file_hash: File hash (for deduplication and unique identification)
            extra_metadata: Additional metadata
            date_prefix: Whether to add date prefix
        
        Returns:
            (success, cloud_url, error_message)
        """
        try:
            # 1. Generate standardized S3 path
            file_ext = Path(local_path).suffix
            s3_key = S3PathGenerator.generate_path(
                resource_type=resource_type,
                owner=owner,
                file_category=file_category,
                file_hash=file_hash,
                file_ext=file_ext,
                date_prefix=date_prefix
            )
            
            logger.info(f"[StandardS3Uploader] Generated S3 key: {s3_key}")
            
            # 2. Auto-detect content type
            content_type = self._detect_content_type(local_path)
            
            # 3. Build standard metadata
            metadata = self._build_standard_metadata(
                owner=owner,
                resource_type=resource_type,
                resource_id=resource_id,
                file_category=file_category,
                extra_metadata=extra_metadata
            )
            
            # 4. Upload to S3 asynchronously (non-blocking)
            logger.debug(f"[StandardS3Uploader] Calling s3_service.upload_file_async...")
            success, url, error = await self.s3_service.upload_file_async(
                local_path=local_path,
                cloud_key=s3_key,
                content_type=content_type,
                metadata=metadata
            )
            logger.debug(f"[StandardS3Uploader] upload_file_async returned: success={success}")
            
            if success:
                logger.info(f"[StandardS3Uploader] ✅ Async upload successful: {s3_key}")
            else:
                logger.error(f"[StandardS3Uploader] ❌ Async upload failed: {error}")
            
            return success, url, error
            
        except Exception as e:
            error_msg = f"Async upload error: {str(e)}"
            logger.error(f"[StandardS3Uploader] {error_msg}")
            return False, "", error_msg
    
    def download(
        self,
        owner: str,
        resource_type: str,
        file_category: str,
        file_hash: str,
        file_ext: str,
        local_path: str,
        date: str = None
    ) -> Tuple[bool, str]:
        """
        Standardized download file
        
        Uses the same path generation logic
        
        Args:
            owner: User identifier
            resource_type: Resource type
            file_category: File category
            file_hash: File hash
            file_ext: File extension
            local_path: Local save path
            date: Optional, date prefix (if used during upload)
        
        Returns:
            (success, error_message)
        """
        try:
            # Generate S3 path
            s3_key = S3PathGenerator.generate_path(
                resource_type=resource_type,
                owner=owner,
                file_category=file_category,
                file_hash=file_hash,
                file_ext=file_ext,
                date_prefix=bool(date)
            )
            
            # If date exists, need to manually build path
            if date:
                parts = s3_key.split('/')
                # Insert date before filename
                parts.insert(-1, date)
                s3_key = '/'.join(parts)
            
            logger.info(f"[StandardS3Uploader] Downloading from S3 key: {s3_key}")
            
            return self.s3_service.download_file(s3_key, local_path)
            
        except Exception as e:
            error_msg = f"Download error: {str(e)}"
            logger.error(f"[StandardS3Uploader] {error_msg}")
            return False, error_msg
    
    def delete(
        self,
        owner: str,
        resource_type: str,
        file_category: str,
        file_hash: str,
        file_ext: str,
        date: str = None
    ) -> Tuple[bool, str]:
        """
        Standardized delete file
        
        Args:
            owner: User identifier
            resource_type: Resource type
            file_category: File category
            file_hash: File hash
            file_ext: File extension
            date: Optional, date prefix
        
        Returns:
            (success, error_message)
        """
        try:
            # Generate S3 path
            s3_key = S3PathGenerator.generate_path(
                resource_type=resource_type,
                owner=owner,
                file_category=file_category,
                file_hash=file_hash,
                file_ext=file_ext,
                date_prefix=bool(date)
            )
            
            if date:
                parts = s3_key.split('/')
                parts.insert(-1, date)
                s3_key = '/'.join(parts)
            
            logger.info(f"[StandardS3Uploader] Deleting S3 key: {s3_key}")
            
            return self.s3_service.delete_file(s3_key)
            
        except Exception as e:
            error_msg = f"Delete error: {str(e)}"
            logger.error(f"[StandardS3Uploader] {error_msg}")
            return False, error_msg
    
    def list_user_files(
        self,
        owner: str,
        resource_type: str = None,
        file_category: str = None
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        """
        List all files for a user
        
        Args:
            owner: User identifier
            resource_type: Optional, filter by resource type
            file_category: Optional, filter by file category
        
        Returns:
            (success, file_list, error_message)
            
        Examples:
            >>> success, files, error = uploader.list_user_files('user@example.com', 'avatar')
            >>> for file in files:
            ...     print(file['key'], file['size'], file['last_modified'])
        """
        try:
            # Build prefix
            safe_owner = owner.replace('/', '_').replace('\\', '_')
            
            if resource_type and file_category:
                resource_plural = f"{resource_type}s" if not resource_type.endswith('s') else resource_type
                category_plural = f"{file_category}s" if not file_category.endswith('s') else file_category
                prefix = f"{resource_plural}/{safe_owner}/{category_plural}/"
            elif resource_type:
                resource_plural = f"{resource_type}s" if not resource_type.endswith('s') else resource_type
                prefix = f"{resource_plural}/{safe_owner}/"
            else:
                # List all files for user (across resource types)
                # This requires multiple calls or a different strategy
                prefix = ""  # Need to implement more complex logic
            
            # Call S3 service to list objects
            # Note: Need to implement list_objects method in S3StorageService
            if hasattr(self.s3_service, 'list_objects'):
                return self.s3_service.list_objects(prefix)
            else:
                logger.warning("[StandardS3Uploader] S3 service does not support list_objects")
                return False, [], "List operation not supported"
            
        except Exception as e:
            error_msg = f"List error: {str(e)}"
            logger.error(f"[StandardS3Uploader] {error_msg}")
            return False, [], error_msg
    
    def _detect_content_type(self, file_path: str) -> str:
        """
        Automatically detect file MIME type
        
        Args:
            file_path: File path
        
        Returns:
            MIME type string
        """
        content_type, _ = mimetypes.guess_type(file_path)
        
        if not content_type:
            # Default type
            content_type = 'application/octet-stream'
            
            # Manually map common types based on extension
            ext = Path(file_path).suffix.lower()
            type_mapping = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.svg': 'image/svg+xml',
                '.mp4': 'video/mp4',
                '.webm': 'video/webm',
                '.mov': 'video/quicktime',
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.txt': 'text/plain',
                '.md': 'text/markdown',
            }
            content_type = type_mapping.get(ext, content_type)
        
        return content_type
    
    def _build_standard_metadata(
        self,
        owner: str,
        resource_type: str,
        resource_id: str,
        file_category: str,
        extra_metadata: Dict[str, str] = None
    ) -> Dict[str, str]:
        """
        Build standardized metadata
        
        All files include these basic metadata
        
        Args:
            owner: User identifier
            resource_type: Resource type
            resource_id: Resource ID
            file_category: File category
            extra_metadata: Additional metadata
        
        Returns:
            Standardized metadata dictionary
        """
        metadata = {
            'owner': owner,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'file_category': file_category,
            'upload_time': datetime.utcnow().isoformat(),
            'uploader': 'ecan_app',
            'version': '1.0'
        }
        
        # Merge additional metadata
        if extra_metadata:
            # Ensure additional metadata doesn't override standard fields
            for key, value in extra_metadata.items():
                if key not in metadata:
                    metadata[key] = value
        
        return metadata


# Convenience function: Create standard uploader instance
def create_standard_uploader():
    """
    Create standard S3 uploader instance
    
    Automatically get S3 service from environment variables or AppContext
    
    Returns:
        StandardS3Uploader instance or None
    """
    try:
        from agent.cloud.s3_storage_service import create_s3_storage_service
        
        s3_service = create_s3_storage_service()
        
        if s3_service:
            return StandardS3Uploader(s3_service)
        else:
            logger.warning("[create_standard_uploader] S3 service not configured")
            return None
            
    except Exception as e:
        logger.error(f"[create_standard_uploader] Failed to create uploader: {e}")
        return None
