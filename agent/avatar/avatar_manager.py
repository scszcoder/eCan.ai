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
    
    def __init__(self, user_id: str, db_service=None):
        """
        Initialize Avatar Manager.
        
        Args:
            user_id: User identifier
            db_service: Database service for avatar resource tracking
        
        Note:
            Cloud sync is handled at the agent level (agent new/save operations).
            Avatar manager only handles local file operations and database storage.
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
        
        # Note: Cloud sync is handled at the agent level (agent new/save operations)
        # Avatar manager only handles local file operations and database storage
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
            List of avatar information dictionaries with HTTP URLs
        """
        avatars = []
        for avatar_info in self.SYSTEM_AVATARS:
            avatar_id = avatar_info["id"]
            image_path = self.system_dir / avatar_info["filename"]
            video_mp4_path = self.system_dir / f"{avatar_id}.mp4"
            video_webm_path = self.system_dir / f"{avatar_id}.webm"
            
            # Return file path, will be converted to HTTP URL by handler
            image_url = None
            if image_path.exists():
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
    
    def get_avatar_info(self, avatar_resource_id: str, auto_restore: bool = False) -> Optional[Dict]:
        """
        Get avatar resource information with HTTP URLs for frontend.
        
        This is a high-level method that:
        1. Fetches avatar data from database (via db_service)
        2. Converts file paths to HTTP URLs
        3. Checks file existence
        4. Optionally restores missing files from cloud
        
        Args:
            avatar_resource_id: Avatar resource ID
            auto_restore: Whether to automatically restore missing files from cloud
            
        Returns:
            Avatar info dict with HTTP URLs, or None if not found
        """
        if not self.db_service:
            logger.warning("[AvatarManager] No db_service, cannot get avatar resource")
            return None
        
        try:
            # Get data using DBAvatarService
            avatar_data = self.db_service.get_avatar_resource(avatar_resource_id)
            
            if not avatar_data:
                logger.warning(f"[AvatarManager] Avatar resource not found: {avatar_resource_id}")
                return None
            
            # If auto-restore is enabled, check and restore missing files
            if auto_restore:
                self.ensure_avatar_file_exists(avatar_resource_id)
            
            # Return avatar resource info (using HTTP URLs for web frontend access)
            from .avatar_url_utils import build_avatar_urls
            
            thumbnail_path = avatar_data.get('avatar_metadata', {}).get('thumbnail_path') if avatar_data.get('avatar_metadata') else None
            
            # Use unified URL builder
            urls = build_avatar_urls(
                image_path=avatar_data.get('image_path'),
                video_path=avatar_data.get('video_path'),
                thumbnail_path=thumbnail_path
            )
            
            return {
                'id': avatar_data['id'],
                'type': avatar_data['resource_type'],
                'imageUrl': urls['imageUrl'],
                'videoPath': urls['videoPath'],  # Use videoPath instead of videoUrl to match frontend
                'thumbnailUrl': urls['thumbnailUrl'],
                'hash': avatar_data.get('image_hash'),
                'name': avatar_data.get('name'),
                'imageExists': avatar_data.get('image_path') and os.path.exists(avatar_data['image_path']),
                'videoExists': avatar_data.get('video_path') and os.path.exists(avatar_data['video_path']),
                'metadata': avatar_data.get('avatar_metadata', {})
            }
        except Exception as e:
            logger.error(f"[AvatarManager] Error getting avatar resource: {e}")
            return None
    
    def ensure_avatar_file_exists(self, avatar_resource_id: str) -> bool:
        """
        Ensure avatar file exists, restore from cloud if not available locally.
        
        Args:
            avatar_resource_id: Avatar resource ID
            
        Returns:
            Whether the file is available
        """
        if not self.db_service:
            logger.warning("[AvatarManager] No db_service, cannot check avatar file")
            return False
        
        try:
            # Get data using DBAvatarService
            avatar_data = self.db_service.get_avatar_resource(avatar_resource_id)
            
            if not avatar_data:
                logger.warning(f"[AvatarManager] Avatar resource not found: {avatar_resource_id}")
                return False
            
            # Check if local files exist
            image_exists = avatar_data.get('image_path') and os.path.exists(avatar_data['image_path'])
            video_exists = avatar_data.get('video_path') and os.path.exists(avatar_data['video_path'])
            
            # If all local files exist, return directly
            if image_exists and (not avatar_data.get('video_path') or video_exists):
                return True
            
            # If local files are missing, try to restore from cloud
            if self.cloud_sync_manager and self.cloud_sync_manager.is_enabled():
                logger.info(f"[AvatarManager] Local files missing, restoring from cloud: {avatar_resource_id}")
                success = self.cloud_sync_manager.sync_avatar_from_cloud(avatar_data, force=False)
                
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
        Upload and process user avatar with transaction rollback support.
        
        Args:
            file_data: Image file bytes
            filename: Original filename
            
        Returns:
            Result dictionary with avatar information
        """
        logger.info(f"[AvatarManager] Uploading avatar: {filename}")
        
        # Track created files for rollback
        local_files = []
        
        try:
            # Validate image
            validation = self.validate_image(file_data, filename)
            if not validation["success"]:
                return {
                    "success": False,
                    "error": validation["error"]
                }
            
            # Calculate hash
            file_hash = self.calculate_file_hash(file_data)
            avatar_id = f"avatar_{file_hash}"  # Generate avatar resource ID

            # Check if already exists
            existing_path = self.uploaded_dir / f"{file_hash}_original.png"
            thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"

            if existing_path.exists():
                logger.info(f"[AvatarManager] Avatar already exists: {avatar_id}")
                # Return file paths, will be converted to HTTP URLs by handler
                return {
                    "success": True,
                    "message": "Avatar already exists",
                    "id": avatar_id,
                    "imageUrl": str(existing_path),
                    "thumbnailUrl": str(thumbnail_path) if thumbnail_path.exists() else None,
                    "hash": file_hash
                }
            
            # Save original image
            with open(existing_path, 'wb') as f:
                f.write(file_data)
            local_files.append(existing_path)
            logger.debug(f"[AvatarManager] Saved original image: {existing_path}")
            
            # Create thumbnail
            thumbnail_data = self.create_thumbnail(file_data)
            thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"
            with open(thumbnail_path, 'wb') as f:
                f.write(thumbnail_data)
            local_files.append(thumbnail_path)
            logger.debug(f"[AvatarManager] Saved thumbnail: {thumbnail_path}")
            
            # Save to database if db_service available
            avatar_resource = None
            if self.db_service:
                try:
                    avatar_resource = self._save_avatar_resource({
                        "resource_type": "uploaded",
                        "name": filename,
                        "image_path": str(existing_path),
                        "image_hash": file_hash,
                        "avatar_metadata": {
                            "image_format": validation["format"],
                            "image_size": validation["size"],
                            "image_width": validation["dimensions"][0],
                            "image_height": validation["dimensions"][1],
                            "thumbnail_path": str(thumbnail_path),
                            "original_filename": filename
                        },
                        "owner": self.user_id
                    })
                    
                    if not avatar_resource:
                        # Database save failed, rollback local files
                        logger.error(f"[AvatarManager] ❌ Failed to save avatar to database")
                        raise Exception("Failed to save avatar resource to database")
                    
                    logger.info(f"[AvatarManager] ✅ Avatar resource saved to database: {avatar_id}")
                except Exception as e:
                    logger.error(f"[AvatarManager] ❌ Database save failed: {e}")
                    # Rollback local files
                    for file_path in local_files:
                        try:
                            if file_path.exists():
                                file_path.unlink()
                                logger.debug(f"[AvatarManager] Deleted file during rollback: {file_path}")
                        except Exception as cleanup_error:
                            logger.warning(f"[AvatarManager] Failed to delete file during rollback: {cleanup_error}")
                    # Re-raise to let caller know upload failed
                    raise

            # Note: Cloud sync (S3 + AppSync) is handled at the agent level
            # when creating or updating agents with this avatar

            logger.info(f"[AvatarManager] ✅ Avatar uploaded successfully: {avatar_id}")

            # Return file paths, will be converted to HTTP URLs by handler
            return {
                "success": True,
                "id": avatar_id,  # Return avatar_resource_id for agent association
                "imageUrl": str(existing_path),
                "thumbnailUrl": str(thumbnail_path),
                "hash": file_hash,
                "metadata": validation
            }
            
        except Exception as e:
            # Rollback: delete local files on error
            logger.error(f"[AvatarManager] ❌ Upload failed, rolling back: {e}")
            for file_path in local_files:
                try:
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug(f"[AvatarManager] Deleted file during rollback: {file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"[AvatarManager] Failed to delete file during rollback: {cleanup_error}")
            
            return {
                "success": False,
                "error": f"Upload failed: {str(e)}"
            }
    
    def _save_avatar_resource(self, resource_data: Dict) -> Optional[Dict]:
        """
        Save avatar resource to database.
        
        Args:
            resource_data: Avatar resource data dictionary
            
        Returns:
            DBAvatarResource instance if successful, None otherwise
        """
        if not self.db_service:
            logger.warning("[AvatarManager] No db_service available, cannot save to database")
            return None
        
        try:
            # Generate avatar resource ID
            avatar_id = f"avatar_{resource_data['image_hash']}"
            
            # Prepare data for DBAvatarService
            avatar_data = {
                'id': avatar_id,
                'owner': resource_data.get('owner', self.user_id),
                'resource_type': resource_data.get('resource_type', 'uploaded'),
                'name': resource_data.get('name'),
                'image_path': resource_data.get('image_path'),
                'image_hash': resource_data['image_hash'],
                'video_path': resource_data.get('video_path'),
                'avatar_metadata': resource_data.get('avatar_metadata', {})
            }
            
            # Use DBAvatarService to create resource
            created_id = self.db_service.create_avatar_resource(avatar_data)
            
            if created_id:
                logger.info(f"[AvatarManager] ✅ Saved avatar resource to database: {created_id}")
                # Return the created resource data
                return self.db_service.get_avatar_resource(created_id)
            else:
                logger.error(f"[AvatarManager] ❌ Failed to save avatar resource to database")
                return None
            
        except Exception as e:
            logger.error(f"[AvatarManager] ❌ Failed to save avatar resource to database: {e}")
            # Session rollback is handled automatically by context manager
            return None
    
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
            avatar_id = f"avatar_{file_hash}"  # Generate avatar resource ID
            thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"

            # Return file paths, will be converted to HTTP URLs by handler
            avatar_data = {
                "type": "uploaded",
                "id": avatar_id,  # Avatar resource ID for agent association
                "hash": file_hash,
                "imageUrl": str(image_path),
                "thumbnailUrl": str(thumbnail_path) if thumbnail_path.exists() else None,
                "imageExists": True,
                "videoUrl": None  # Will be populated if video exists
            }

            # Check for associated video
            video_path = self.generated_dir / f"{file_hash}_video.mp4"
            if video_path.exists():
                avatar_data["videoUrl"] = str(video_path)
                avatar_data["videoExists"] = True

            avatars.append(avatar_data)
        
        logger.debug(f"[AvatarManager] Retrieved {len(avatars)} uploaded avatars")
        return avatars
    
    # ==================== Delete Uploaded Avatar ====================
    
    async def delete_uploaded_avatar(self, avatar_id: str) -> Dict:
        """
        Delete an uploaded avatar.
        
        Args:
            avatar_id: Avatar ID (format: avatar_{hash})
            
        Returns:
            Result dictionary
        """
        try:
            # Extract hash from avatar_id
            if not avatar_id.startswith("avatar_"):
                return {
                    "success": False,
                    "error": "Invalid avatar ID format"
                }
            
            file_hash = avatar_id.replace("avatar_", "")
            
            # File paths
            original_path = self.uploaded_dir / f"{file_hash}_original.png"
            thumbnail_path = self.uploaded_dir / f"{file_hash}_thumb.png"
            video_path = self.generated_dir / f"{file_hash}_video.mp4"
            
            deleted_files = []
            
            # Delete original image
            if original_path.exists():
                original_path.unlink()
                deleted_files.append(str(original_path))
                logger.debug(f"[AvatarManager] Deleted original: {original_path}")
            
            # Delete thumbnail
            if thumbnail_path.exists():
                thumbnail_path.unlink()
                deleted_files.append(str(thumbnail_path))
                logger.debug(f"[AvatarManager] Deleted thumbnail: {thumbnail_path}")
            
            # Delete associated video if exists
            if video_path.exists():
                video_path.unlink()
                deleted_files.append(str(video_path))
                logger.debug(f"[AvatarManager] Deleted video: {video_path}")
            
            # Delete from database if db_service available
            if self.db_service:
                try:
                    # Use DBAvatarService to delete resource
                    if self.db_service.delete_avatar_resource(avatar_id):
                        logger.info(f"[AvatarManager] Deleted from database: {avatar_id}")
                    else:
                        logger.warning(f"[AvatarManager] Avatar not found in database: {avatar_id}")
                except Exception as e:
                    logger.warning(f"[AvatarManager] Failed to delete from database: {e}")
            
            if not deleted_files:
                return {
                    "success": False,
                    "error": "Avatar not found"
                }
            
            logger.info(f"[AvatarManager] ✅ Avatar deleted successfully: {avatar_id}")
            return {
                "success": True,
                "deleted_files": deleted_files
            }
            
        except Exception as e:
            logger.error(f"[AvatarManager] ❌ Failed to delete avatar: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
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


# ==================== System Avatar Initialization ====================
# Merged from init_system_avatars.py for better cohesion

def init_system_avatars(force: bool = False) -> bool:
    """
    Initialize system default avatars by copying them to project resource directory.
    
    System avatars are stored in the project's resource/avatars directory,
    not in user's AppData directory.
    
    Args:
        force: If True, overwrite existing files
        
    Returns:
        bool: True if successful
    """
    try:
        from config.app_info import app_info
        import shutil
        
        # Source: frontend assets
        project_root = Path(__file__).parent.parent.parent
        image_source_dir = project_root / "gui_v2" / "src" / "assets"
        video_source_dir = project_root / "gui_v2" / "src" / "assets" / "gifs"
        
        # Destination: project resource/avatars/system directory (system avatars)
        resource_dir = Path(app_info.app_resources_path)
        dest_dir = resource_dir / "avatars" / "system"
        
        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # System avatar files (images from assets/, videos from assets/gifs/)
        # Note: A004 is missing, agent videos map to: agent0->A001, agent1->A002, etc.
        system_avatars = [
            ("A001.png", image_source_dir, "A001.png"),
            ("A001.mp4", video_source_dir, "agent0.mp4"),
            ("A001.webm", video_source_dir, "agent0.webm"),
            ("A002.png", image_source_dir, "A002.png"),
            ("A002.mp4", video_source_dir, "agent1.mp4"),
            ("A002.webm", video_source_dir, "agent1.webm"),
            ("A003.png", image_source_dir, "A003.png"),
            ("A003.mp4", video_source_dir, "agent2.mp4"),
            ("A003.webm", video_source_dir, "agent2.webm"),
            # A004 is missing
            ("A005.png", image_source_dir, "A005.png"),
            ("A005.mp4", video_source_dir, "agent3.mp4"),
            ("A005.webm", video_source_dir, "agent3.webm"),
            ("A006.png", image_source_dir, "A006.png"),
            ("A006.mp4", video_source_dir, "agent4.mp4"),
            ("A006.webm", video_source_dir, "agent4.webm"),
            ("A007.png", image_source_dir, "A007.png"),
            ("A007.mp4", video_source_dir, "agent5.mp4"),
            ("A007.webm", video_source_dir, "agent5.webm"),
        ]
        
        copied_count = 0
        skipped_count = 0
        missing_count = 0
        
        for dest_filename, source_dir, source_filename in system_avatars:
            source_file = source_dir / source_filename
            dest_file = dest_dir / dest_filename
            
            # Check if source exists
            if not source_file.exists():
                logger.warning(f"[InitAvatars] Source file not found: {source_file}")
                missing_count += 1
                continue
            
            # Check if destination exists
            if dest_file.exists() and not force:
                logger.debug(f"[InitAvatars] File already exists, skipping: {dest_filename}")
                skipped_count += 1
                continue
            
            # Copy file
            try:
                shutil.copy2(source_file, dest_file)
                logger.info(f"[InitAvatars] Copied: {source_filename} -> {dest_filename}")
                copied_count += 1
            except Exception as e:
                logger.error(f"[InitAvatars] Failed to copy {dest_filename}: {e}")
        
        # Summary
        logger.info(
            f"[InitAvatars] Summary: "
            f"Copied={copied_count}, Skipped={skipped_count}, Missing={missing_count}"
        )
        
        if missing_count > 0:
            logger.warning(
                f"[InitAvatars] {missing_count} avatar files are missing. "
                f"Please ensure all A001-A007 images and videos are present in gui_v2/src/assets/"
            )
        
        return True
        
    except Exception as e:
        logger.error(f"[InitAvatars] Failed to initialize system avatars: {e}", exc_info=True)
        return False


def check_system_avatars() -> dict:
    """
    Check which system avatars are available.
    
    Returns:
        dict: Status of each avatar file
    """
    try:
        from config.app_info import app_info
        
        resource_dir = Path(app_info.app_resources_path)
        avatars_dir = resource_dir / "avatars" / "system"
        
        status = {}
        
        for i in range(1, 8):
            avatar_id = f"A{i:03d}"
            image_file = avatars_dir / f"{avatar_id}.png"
            video_file = avatars_dir / f"{avatar_id}.mp4"
            
            status[avatar_id] = {
                "image_exists": image_file.exists(),
                "image_path": str(image_file) if image_file.exists() else None,
                "video_exists": video_file.exists(),
                "video_path": str(video_file) if video_file.exists() else None
            }
        
        return status
        
    except Exception as e:
        logger.error(f"[InitAvatars] Failed to check system avatars: {e}")
        return {}
