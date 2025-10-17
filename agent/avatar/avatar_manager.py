"""
Avatar Manager - Core avatar management functionality.

This module provides comprehensive avatar management including:
- System default avatars
- User uploaded avatars
- AI-generated avatar videos
- Local and cloud storage
- Avatar resource tracking
"""

import os
import hashlib
import base64
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from utils.logger_helper import logger_helper as logger

from PIL import Image
import io


class AvatarManager:
    """
    Avatar Manager for handling all avatar-related operations.
    
    Features:
    - System default avatars (A001-A007)
    - User uploaded avatars with validation
    - Avatar video generation via AI
    - Local and cloud storage management
    - Avatar resource tracking in database
    """
    
    # Supported image formats
    SUPPORTED_IMAGE_FORMATS = ['png', 'jpg', 'jpeg', 'gif', 'webp']
    
    # Maximum file sizes
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB
    
    # Recommended dimensions
    RECOMMENDED_IMAGE_SIZE = (512, 512)
    THUMBNAIL_SIZE = (256, 256)
    
    # System default avatars
    SYSTEM_AVATARS = [
        {
            "id": "A001",
            "name": "Professional Male",
            "tags": ["professional", "male", "formal"],
            "filename": "A001.png"
        },
        {
            "id": "A002",
            "name": "Professional Female",
            "tags": ["professional", "female", "formal"],
            "filename": "A002.png"
        },
        {
            "id": "A003",
            "name": "Casual Male",
            "tags": ["casual", "male", "friendly"],
            "filename": "A003.png"
        },
        # {
        #     "id": "A004",
        #     "name": "Casual Female",
        #     "tags": ["casual", "female", "friendly"],
        #     "filename": "A004.png"
        # },
        {
            "id": "A005",
            "name": "Tech Professional",
            "tags": ["tech", "professional", "modern"],
            "filename": "A005.png"
        },
        {
            "id": "A006",
            "name": "Creative Professional",
            "tags": ["creative", "artistic", "modern"],
            "filename": "A006.png"
        },
        {
            "id": "A007",
            "name": "Executive",
            "tags": ["executive", "leadership", "formal"],
            "filename": "A007.png"
        }
    ]
    
    def __init__(self, user_id: str, db_service=None, enable_cloud_sync: bool = True):
        """
        Initialize Avatar Manager.
        
        Args:
            user_id: User identifier
            db_service: Database service for avatar resource tracking
            enable_cloud_sync: Whether to enable cloud synchronization
        """
        self.user_id = user_id
        self.db_service = db_service
        
        # Initialize storage paths
        # System avatars: project resource/avatars directory
        self.system_dir = self._get_system_avatar_dir()
        
        # User avatars: user AppData resource/avatars directory
        self.user_base_dir = self._get_user_avatar_base_dir()
        self.uploaded_dir = self.user_base_dir / "uploaded"
        self.generated_dir = self.user_base_dir / "generated"
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Initialize cloud sync manager (temporarily disabled)
        self.cloud_sync_manager = None
        # TODO: Re-enable cloud sync when session management is fixed
        # if enable_cloud_sync and db_service:
        #     try:
        #         from .cloud_sync_manager import CloudSyncManager
        #         self.cloud_sync_manager = CloudSyncManager(db_service.session)
        #         if self.cloud_sync_manager.is_enabled():
        #             logger.info(f"[AvatarManager] Cloud sync enabled for user: {user_id}")
        #         else:
        #             logger.info(f"[AvatarManager] Cloud sync not configured")
        #     except Exception as e:
        #         logger.warning(f"[AvatarManager] Failed to initialize cloud sync: {e}")
        # Cloud sync disabled for now
        logger.debug(f"[AvatarManager] Initialized for user: {user_id}")
    
    def _get_system_avatar_dir(self) -> Path:
        """
        Get the system avatar directory (project resource/avatars/system).
        System avatars are stored in the project's resource/avatars/system folder.
        """
        from config.app_info import app_info
        resource_dir = app_info.app_resources_path
        return Path(resource_dir) / "avatars" / "system"
    
    def _get_user_avatar_base_dir(self) -> Path:
        """
        Get the user avatar base directory (AppData resource/avatars).
        User uploaded and generated avatars are stored in user's AppData folder.
        """
        from config.app_info import app_info
        user_data_dir = app_info.appdata_path
        return Path(user_data_dir) / "resource" / "avatars"
    
    def _ensure_directories(self):
        """Ensure all required directories exist."""
        # System directory (read-only, should already exist)
        self.system_dir.mkdir(parents=True, exist_ok=True)
        
        # User directories (writable)
        for directory in [self.uploaded_dir, self.generated_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    # ==================== System Default Avatars ====================
    
    def get_system_avatars(self) -> List[Dict]:
        """
        Get list of system default avatars.
        
        Returns:
            List of avatar information dictionaries with base64 encoded images
        """
        avatars = []
        for avatar_info in self.SYSTEM_AVATARS:
            avatar_id = avatar_info["id"]
            image_path = self.system_dir / avatar_info["filename"]
            video_mp4_path = self.system_dir / f"{avatar_id}.mp4"
            video_webm_path = self.system_dir / f"{avatar_id}.webm"
            
            # Use HTTP URL for image instead of base64 for better performance
            image_url = None
            if image_path.exists():
                # Return file path, will be converted to HTTP URL by caller
                image_url = str(image_path)
            
            avatar_data = {
                "id": avatar_id,
                "name": avatar_info["name"],
                "tags": avatar_info["tags"],
                "type": "system",
                "imageUrl": image_url,  # File path, will be converted to HTTP URL
                "videoUrl": None,  # Not used, use videoMp4Path/videoWebmPath instead
                "videoMp4Path": str(video_mp4_path) if video_mp4_path.exists() else None,
                "videoWebmPath": str(video_webm_path) if video_webm_path.exists() else None,
                "imageExists": image_path.exists(),
                "videoExists": video_mp4_path.exists() or video_webm_path.exists()
            }
            avatars.append(avatar_data)
        
        logger.debug(f"[AvatarManager] Retrieved {len(avatars)} system avatars")
        return avatars
    
    def get_system_avatar_path(self, avatar_id: str) -> Optional[Path]:
        """
        Get the file path for a system avatar.
        
        Args:
            avatar_id: System avatar ID (e.g., "A001")
            
        Returns:
            Path to the avatar image file, or None if not found
        """
        for avatar_info in self.SYSTEM_AVATARS:
            if avatar_info["id"] == avatar_id:
                image_path = self.system_dir / avatar_info["filename"]
                if image_path.exists():
                    return image_path
        return None
    
    def get_avatar_resource(self, avatar_resource_id: str, auto_restore: bool = True) -> Optional[Dict]:
        """
        获取头像资源信息，自动检查并恢复缺失的文件
        
        Args:
            avatar_resource_id: Avatar resource ID
            auto_restore: 是否自动从云端恢复缺失的文件
            
        Returns:
            头像资源信息字典，如果不存在返回 None
        """
        if not self.db_service:
            logger.warning("[AvatarManager] No db_service, cannot get avatar resource")
            return None
        
        try:
            from ..db.models.avatar_model import DBAvatarResource
            
            # 查询 avatar resource
            avatar_resource = self.db_service.session.query(DBAvatarResource).filter_by(
                id=avatar_resource_id
            ).first()
            
            if not avatar_resource:
                logger.warning(f"[AvatarManager] Avatar resource not found: {avatar_resource_id}")
                return None
            
            # 如果启用自动恢复，检查并恢复缺失的文件
            if auto_restore:
                self.ensure_avatar_file_exists(avatar_resource_id)
            
            # 返回头像资源信息（使用 pyqtfile:// 协议以便前端访问本地文件）
            return {
                "id": avatar_resource.id,
                "type": avatar_resource.resource_type,
                "name": avatar_resource.name,
                "imageUrl": f"pyqtfile://{avatar_resource.image_path}" if avatar_resource.image_path else None,
                "videoUrl": f"pyqtfile://{avatar_resource.video_path}" if avatar_resource.video_path else None,
                "cloudImageUrl": avatar_resource.cloud_image_url,
                "cloudVideoUrl": avatar_resource.cloud_video_url,
                "cloudSynced": avatar_resource.cloud_synced,
                "metadata": avatar_resource.avatar_metadata
            }
            
        except Exception as e:
            logger.error(f"[AvatarManager] Error getting avatar resource: {e}")
            return None
    
    def ensure_avatar_file_exists(self, avatar_resource_id: str) -> bool:
        """
        确保头像文件存在，如果本地不存在则从云端恢复
        
        Args:
            avatar_resource_id: Avatar resource ID
            
        Returns:
            文件是否可用
        """
        if not self.db_service:
            logger.warning("[AvatarManager] No db_service, cannot check avatar file")
            return False
        
        try:
            from ..db.models.avatar_model import DBAvatarResource
            
            # 查询 avatar resource
            avatar_resource = self.db_service.session.query(DBAvatarResource).filter_by(
                id=avatar_resource_id
            ).first()
            
            if not avatar_resource:
                logger.warning(f"[AvatarManager] Avatar resource not found: {avatar_resource_id}")
                return False
            
            # 检查本地文件是否存在
            image_exists = avatar_resource.image_path and os.path.exists(avatar_resource.image_path)
            video_exists = avatar_resource.video_path and os.path.exists(avatar_resource.video_path)
            
            # 如果本地文件都存在，直接返回
            if image_exists and (not avatar_resource.video_path or video_exists):
                return True
            
            # 如果本地文件缺失，尝试从云端恢复
            if self.cloud_sync_manager and self.cloud_sync_manager.is_enabled():
                logger.info(f"[AvatarManager] Local files missing, restoring from cloud: {avatar_resource_id}")
                success = self.cloud_sync_manager.sync_avatar_from_cloud(avatar_resource, force=False)
                
                if success:
                    logger.info(f"[AvatarManager] ✅ Successfully restored from cloud: {avatar_resource_id}")
                    return True
                else:
                    logger.warning(f"[AvatarManager] ⚠️ Failed to restore from cloud: {avatar_resource_id}")
                    return False
            else:
                logger.warning(f"[AvatarManager] Cloud sync not available, cannot restore: {avatar_resource_id}")
                return False
                
        except Exception as e:
            logger.error(f"[AvatarManager] Error ensuring avatar file exists: {e}")
            return False
    
    # ==================== Image Validation ====================
    
    def validate_image(self, file_data: bytes, filename: str) -> Dict:
        """
        Validate uploaded image file.
        
        Args:
            file_data: Image file bytes
            filename: Original filename
            
        Returns:
            Validation result dictionary with success status and details
        """
        result = {
            "success": False,
            "error": None,
            "format": None,
            "size": len(file_data),
            "dimensions": None
        }
        
        # Check file size
        if len(file_data) > self.MAX_IMAGE_SIZE:
            result["error"] = f"File size exceeds maximum {self.MAX_IMAGE_SIZE / 1024 / 1024}MB"
            return result
        
        # Check file extension
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in self.SUPPORTED_IMAGE_FORMATS:
            result["error"] = f"Unsupported format. Supported: {', '.join(self.SUPPORTED_IMAGE_FORMATS)}"
            return result
        
        # Validate image with PIL
        try:
            image = Image.open(io.BytesIO(file_data))
            result["format"] = image.format.lower()
            result["dimensions"] = image.size
            result["success"] = True
            
            logger.info(f"[AvatarManager] Image validated: {result['format']}, {result['dimensions']}, {result['size']} bytes")
        except Exception as e:
            result["error"] = f"Invalid image file: {str(e)}"
            logger.error(f"[AvatarManager] Image validation failed: {e}")
        
        return result
    
    # ==================== File Hash ====================
    
    def calculate_file_hash(self, file_data: bytes) -> str:
        """
        Calculate MD5 hash of file data.
        
        Args:
            file_data: File bytes
            
        Returns:
            MD5 hash string
        """
        return hashlib.md5(file_data).hexdigest()
    
    # ==================== Thumbnail Generation ====================
    
    def create_thumbnail(self, image_data: bytes, size: Tuple[int, int] = None) -> bytes:
        """
        Create thumbnail from image data.
        
        Args:
            image_data: Original image bytes
            size: Thumbnail size (width, height), defaults to THUMBNAIL_SIZE
            
        Returns:
            Thumbnail image bytes
        """
        if size is None:
            size = self.THUMBNAIL_SIZE
        
        try:
            image = Image.open(io.BytesIO(image_data))
            image.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            image.save(output, format='PNG')
            thumbnail_data = output.getvalue()
            
            logger.info(f"[AvatarManager] Created thumbnail: {size}, {len(thumbnail_data)} bytes")
            return thumbnail_data
        except Exception as e:
            logger.error(f"[AvatarManager] Failed to create thumbnail: {e}")
            raise
    
    # ==================== Upload Avatar ====================
    
    async def upload_avatar(self, file_data: bytes, filename: str) -> Dict:
        """
        Upload and process user avatar.
        
        Args:
            file_data: Image file bytes
            filename: Original filename
            
        Returns:
            Result dictionary with avatar information
        """
        logger.info(f"[AvatarManager] Uploading avatar: {filename}")
        
        # Validate image
        validation = self.validate_image(file_data, filename)
        if not validation["success"]:
            return {
                "success": False,
                "error": validation["error"]
            }
        
        # Calculate hash
        file_hash = self.calculate_file_hash(file_data)
        
        # Check if already exists
        existing_path = self.uploaded_dir / f"{file_hash}_original.png"
        thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"
        
        if existing_path.exists():
            logger.info(f"[AvatarManager] Avatar already exists: {file_hash}")
            return {
                "success": True,
                "message": "Avatar already exists",
                "imageUrl": f"pyqtfile://{existing_path}",
                "thumbnailUrl": f"pyqtfile://{thumbnail_path}" if thumbnail_path.exists() else None,
                "hash": file_hash
            }
        
        # Save original image
        with open(existing_path, 'wb') as f:
            f.write(file_data)
        
        # Create thumbnail
        thumbnail_data = self.create_thumbnail(file_data)
        thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"
        with open(thumbnail_path, 'wb') as f:
            f.write(thumbnail_data)
        
        # Save to database if db_service available
        avatar_resource = None
        if self.db_service:
            try:
                avatar_resource = await self._save_avatar_resource({
                    "resource_type": "uploaded",
                    "name": filename,
                    "image_path": str(existing_path),
                    "image_hash": file_hash,
                    "metadata": {
                        "image_format": validation["format"],
                        "image_size": validation["size"],
                        "image_width": validation["dimensions"][0],
                        "image_height": validation["dimensions"][1],
                        "thumbnail_path": str(thumbnail_path),
                        "original_filename": filename
                    },
                    "owner": self.user_id
                })
            except Exception as e:
                logger.error(f"[AvatarManager] Failed to save to database: {e}")
        
        # Sync to cloud if enabled
        if self.cloud_sync_manager and avatar_resource:
            try:
                sync_success = self.cloud_sync_manager.sync_avatar_to_cloud(avatar_resource)
                if sync_success:
                    logger.info(f"[AvatarManager] Avatar synced to cloud: {file_hash}")
                else:
                    logger.warning(f"[AvatarManager] Failed to sync avatar to cloud: {file_hash}")
            except Exception as e:
                logger.error(f"[AvatarManager] Cloud sync error: {e}")
        
        logger.info(f"[AvatarManager] Avatar uploaded successfully: {file_hash}")
        
        return {
            "success": True,
            "imageUrl": f"pyqtfile://{existing_path}",
            "thumbnailUrl": f"pyqtfile://{thumbnail_path}",
            "hash": file_hash,
            "metadata": validation
        }
    
    async def _save_avatar_resource(self, resource_data: Dict) -> Dict:
        """Save avatar resource to database."""
        # This will be implemented when db_service is integrated
        # For now, just log
        logger.info(f"[AvatarManager] Would save avatar resource: {resource_data.get('name')}")
        return {"success": True}
    
    # ==================== Get Uploaded Avatars ====================
    
    def get_uploaded_avatars(self) -> List[Dict]:
        """
        Get list of user uploaded avatars.
        
        Returns:
            List of uploaded avatar information
        """
        avatars = []
        
        # Scan uploaded directory for original images
        for image_path in self.uploaded_dir.glob("*_original.png"):
            file_hash = image_path.stem.replace("_original", "")
            thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"
            
            avatar_data = {
                "type": "uploaded",
                "hash": file_hash,
                "imageUrl": f"pyqtfile://{image_path}",
                "thumbnailUrl": f"pyqtfile://{thumbnail_path}" if thumbnail_path.exists() else None,
                "imageExists": True,
                "videoUrl": None  # Will be populated if video exists
            }
            
            # Check for associated video
            video_path = self.generated_dir / f"{file_hash}_video.mp4"
            if video_path.exists():
                avatar_data["videoUrl"] = f"pyqtfile://{video_path}"
                avatar_data["videoExists"] = True
            
            avatars.append(avatar_data)
        
        logger.debug(f"[AvatarManager] Retrieved {len(avatars)} uploaded avatars")
        return avatars
    
    # ==================== Set Agent Avatar ====================
    
    async def set_agent_avatar(
        self,
        agent_id: str,
        avatar_type: str,
        image_url: str,
        video_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Set avatar for an agent.
        
        Args:
            agent_id: Agent ID
            avatar_type: Avatar type (system, uploaded, generated)
            image_url: Image URL
            video_url: Optional video URL
            metadata: Optional metadata
            
        Returns:
            Result dictionary
        """
        logger.info(f"[AvatarManager] Setting avatar for agent {agent_id}: {avatar_type}")
        
        # This will update the agent record in database
        # For now, just return success
        return {
            "success": True,
            "agent_id": agent_id,
            "avatar_type": avatar_type,
            "avatar_image_url": image_url,
            "avatar_video_url": video_url
        }
    
    # ==================== Placeholder for Video Generation ====================
    
    async def generate_avatar_video(
        self,
        image_path: str,
        model: str = "stable-diffusion-video",
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Generate avatar animation video from image using AI.
        
        This is a placeholder for future implementation.
        Will integrate with LLM video generation models.
        
        Args:
            image_path: Path to source image
            model: AI model to use
            params: Generation parameters
            
        Returns:
            Result dictionary with video information
        """
        logger.warning("[AvatarManager] Video generation not yet implemented")
        return {
            "success": False,
            "error": "Video generation feature coming soon"
        }
