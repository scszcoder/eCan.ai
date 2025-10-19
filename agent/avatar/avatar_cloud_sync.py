"""
Avatar cloud sync manager.

Handles automatic synchronization between local storage and cloud storage for avatars.
Renamed from CloudSyncManager to AvatarCloudSync for better clarity.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from .cloud_storage import S3StorageService, create_s3_storage_service
from ..db.models.avatar_model import DBAvatarResource

from utils.logger_helper import logger_helper as logger


class AvatarCloudSync:
    """
    Avatar cloud synchronization manager.

    Handles bidirectional sync between local and cloud storage for avatar resources.
    Uses db_service instead of db_session for better architecture.
    """

    def __init__(self, db_service=None, cloud_service: S3StorageService = None):
        """
        Initialize avatar cloud sync manager.

        Args:
            db_service: Database service (DBAvatarService) for avatar operations
            cloud_service: Cloud storage service, auto-created if None
        """
        self.db_service = db_service
        self.cloud_service = cloud_service or create_s3_storage_service()

        if self.cloud_service:
            logger.info("✅ AvatarCloudSync initialized")
        else:
            logger.warning("⚠️  AvatarCloudSync initialized without cloud service")

    def is_enabled(self) -> bool:
        """Check if cloud sync is enabled"""
        return self.cloud_service is not None

    def sync_avatar_to_cloud(
        self,
        avatar_resource: DBAvatarResource,
        force: bool = False
    ) -> bool:
        """
        Sync avatar resource to cloud.

        Args:
            avatar_resource: Avatar resource object
            force: Whether to force sync (even if already synced)

        Returns:
            Whether sync was successful
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled, skipping sync")
            return False

        # Check if sync is needed
        if avatar_resource.cloud_synced and not force:
            logger.info(f"Avatar {avatar_resource.id} already synced, skipping")
            return True

        try:
            success = True

            # Sync image
            if avatar_resource.image_path and os.path.exists(avatar_resource.image_path):
                image_success = self._sync_file_to_cloud(
                    avatar_resource,
                    avatar_resource.image_path,
                    'image'
                )
                success = success and image_success

            # Sync video
            if avatar_resource.video_path and os.path.exists(avatar_resource.video_path):
                video_success = self._sync_file_to_cloud(
                    avatar_resource,
                    avatar_resource.video_path,
                    'video'
                )
                success = success and video_success

            # Update sync status
            if success:
                avatar_resource.cloud_synced = True
                # Update via db_service if available
                if self.db_service:
                    self.db_service.update_avatar_resource(avatar_resource.id, {'cloud_synced': True})
                logger.info(f"✅ Avatar {avatar_resource.id} synced to cloud")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to sync avatar {avatar_resource.id}: {e}")
            return False

    def _sync_file_to_cloud(
        self,
        avatar_resource: DBAvatarResource,
        local_path: str,
        file_type: str  # 'image' or 'video'
    ) -> bool:
        """
        Sync a single file to cloud.

        Args:
            avatar_resource: Avatar resource object
            local_path: Local file path
            file_type: File type (image or video)

        Returns:
            Whether sync was successful
        """
        try:
            # Build cloud key
            file_hash = avatar_resource.image_hash if file_type == 'image' else avatar_resource.video_hash
            file_ext = Path(local_path).suffix
            cloud_key = f"{avatar_resource.owner}/{file_type}s/{file_hash}{file_ext}"

            # Detect file type
            content_type = self._get_content_type(local_path)

            # Prepare metadata
            metadata = {
                'resource_id': avatar_resource.id,
                'resource_type': avatar_resource.resource_type,
                'owner': avatar_resource.owner,
                'file_type': file_type,
                'upload_time': datetime.utcnow().isoformat()
            }

            # Upload to cloud
            success, cloud_url, error = self.cloud_service.upload_file(
                local_path,
                cloud_key,
                content_type=content_type,
                metadata=metadata
            )

            if success:
                # Update database record
                if file_type == 'image':
                    avatar_resource.cloud_image_url = cloud_url
                    avatar_resource.cloud_image_key = cloud_key
                else:
                    avatar_resource.cloud_video_url = cloud_url
                    avatar_resource.cloud_video_key = cloud_key

                logger.info(f"✅ Uploaded {file_type} to cloud: {cloud_key}")
                return True
            else:
                logger.error(f"❌ Failed to upload {file_type}: {error}")
                return False

        except Exception as e:
            logger.error(f"❌ Error syncing {file_type} to cloud: {e}")
            return False

    def sync_avatar_from_cloud(
        self,
        avatar_resource: DBAvatarResource,
        force: bool = False
    ) -> bool:
        """
        Sync avatar resource from cloud to local.

        Args:
            avatar_resource: Avatar resource object
            force: Whether to force sync (even if local exists)

        Returns:
            Whether sync was successful
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled, skipping sync")
            return False

        try:
            success = True

            # Sync image
            if avatar_resource.cloud_image_key:
                if force or not (avatar_resource.image_path and os.path.exists(avatar_resource.image_path)):
                    image_success = self._sync_file_from_cloud(
                        avatar_resource,
                        avatar_resource.cloud_image_key,
                        'image'
                    )
                    success = success and image_success

            # Sync video
            if avatar_resource.cloud_video_key:
                if force or not (avatar_resource.video_path and os.path.exists(avatar_resource.video_path)):
                    video_success = self._sync_file_from_cloud(
                        avatar_resource,
                        avatar_resource.cloud_video_key,
                        'video'
                    )
                    success = success and video_success

            if success:
                # Commit handled by db_service
                logger.info(f"✅ Avatar {avatar_resource.id} synced from cloud")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to sync avatar {avatar_resource.id} from cloud: {e}")

    def _sync_file_from_cloud(
        self,
        avatar_resource: DBAvatarResource,
        cloud_key: str,
        file_type: str
    ) -> bool:
        """
        Sync a single file from cloud to local.

        Args:
            avatar_resource: Avatar resource object
            cloud_key: Cloud storage key
            file_type: File type (image or video)

        Returns:
            Whether sync was successful
        """
        try:
            # Build local path
            file_hash = avatar_resource.image_hash if file_type == 'image' else avatar_resource.video_hash
            file_ext = Path(cloud_key).suffix

            # Get local storage directory
            from config.app_info import app_info
            user_data_dir = Path(app_info.appdata_path)

            if avatar_resource.resource_type == 'system':
                local_dir = user_data_dir / "avatars" / "system"
            elif avatar_resource.resource_type == 'uploaded':
                local_dir = user_data_dir / "avatars" / "uploaded"
            else:
                local_dir = user_data_dir / "avatars" / "generated"

            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = str(local_dir / f"{file_hash}{file_ext}")

            # Download from cloud
            success, error = self.cloud_service.download_file(cloud_key, local_path)

            if success:
                # Update database record
                if file_type == 'image':
                    avatar_resource.image_path = local_path
                else:
                    avatar_resource.video_path = local_path

                logger.info(f"✅ Downloaded {file_type} from cloud: {cloud_key}")
                return True
            else:
                logger.error(f"❌ Failed to download {file_type}: {error}")
                return False

        except Exception as e:
            logger.error(f"❌ Error syncing {file_type} from cloud: {e}")
            return False

    def delete_avatar_from_cloud(self, avatar_resource: DBAvatarResource) -> bool:
        """
        Delete avatar resource from cloud.

        Args:
            avatar_resource: Avatar resource object

        Returns:
            Whether deletion was successful
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled, skipping delete")
            return False

        try:
            success = True

            # Delete image
            if avatar_resource.cloud_image_key:
                image_success, error = self.cloud_service.delete_file(
                    avatar_resource.cloud_image_key
                )
                if not image_success:
                    logger.error(f"❌ Failed to delete image from cloud: {error}")
                success = success and image_success

            # Delete video
            if avatar_resource.cloud_video_key:
                video_success, error = self.cloud_service.delete_file(
                    avatar_resource.cloud_video_key
                )
                if not video_success:
                    logger.error(f"❌ Failed to delete video from cloud: {error}")
                success = success and video_success

            if success:
                # Update database record
                avatar_resource.cloud_image_url = None
                avatar_resource.cloud_video_url = None
                avatar_resource.cloud_image_key = None
                avatar_resource.cloud_video_key = None
                avatar_resource.cloud_synced = False
                # Update via db_service if available
                if self.db_service:
                    self.db_service.update_avatar_resource(avatar_resource.id, {
                        'cloud_image_url': None,
                        'cloud_video_url': None,
                        'cloud_image_key': None,
                        'cloud_video_key': None,
                        'cloud_synced': False
                    })

                logger.info(f"✅ Avatar {avatar_resource.id} deleted from cloud")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to delete avatar {avatar_resource.id} from cloud: {e}")

    def get_avatar_url(
        self,
        avatar_resource: DBAvatarResource,
        file_type: str = 'image',
        use_cdn: bool = True,
        expires_in: int = 3600
    ) -> Optional[str]:
        """
        Get avatar access URL (prefer cloud URL).

        Args:
            avatar_resource: Avatar resource object
            file_type: File type (image or video)
            use_cdn: Whether to use CDN
            expires_in: URL expiration time (seconds)

        Returns:
            Access URL, or None if not available
        """
        if not self.is_enabled():
            # Cloud not enabled, return local path
            if file_type == 'image':
                return avatar_resource.image_path
            else:
                return avatar_resource.video_path

        try:
            # Prefer cloud URL
            if file_type == 'image' and avatar_resource.cloud_image_key:
                return self.cloud_service.get_file_url(
                    avatar_resource.cloud_image_key,
                    expires_in=expires_in,
                    use_cdn=use_cdn
                )
            elif file_type == 'video' and avatar_resource.cloud_video_key:
                return self.cloud_service.get_file_url(
                    avatar_resource.cloud_video_key,
                    expires_in=expires_in,
                    use_cdn=use_cdn
                )
            else:
                # Cloud not available, return local path
                if file_type == 'image':
                    return avatar_resource.image_path
                else:
                    return avatar_resource.video_path

        except Exception as e:
            logger.error(f"❌ Failed to get avatar URL: {e}")
            # Fallback to local path
            if file_type == 'image':
                return avatar_resource.image_path
            else:
                return avatar_resource.video_path

    def sync_all_avatars(
        self,
        owner: str = None,
        resource_type: str = None,
        direction: str = 'to_cloud'  # 'to_cloud' or 'from_cloud'
    ) -> Dict[str, int]:
        """
        Batch sync avatars.

        Args:
            owner: Owner username (None for all users)
            resource_type: Resource type (None for all types)
            direction: Sync direction (to_cloud or from_cloud)

        Returns:
            Sync statistics {'total': 10, 'success': 8, 'failed': 2}
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled")
            return {'total': 0, 'success': 0, 'failed': 0}

        try:
            # Query avatars via db_service
            if not self.db_service:
                logger.warning("No db_service available for batch sync")
                return {'total': 0, 'success': 0, 'failed': 0}

            # Get avatars from db_service
            avatars = self.db_service.get_avatar_resources(owner=owner, resource_type=resource_type)

            stats = {'total': len(avatars), 'success': 0, 'failed': 0}

            for avatar in avatars:
                if direction == 'to_cloud':
                    success = self.sync_avatar_to_cloud(avatar)
                else:
                    success = self.sync_avatar_from_cloud(avatar)
                
                if success:
                    stats['success'] += 1
                else:
                    stats['failed'] += 1
            
            logger.info(f"✅ Batch sync completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to batch sync avatars: {e}")
            return {'total': 0, 'success': 0, 'failed': 0}
    
    @staticmethod
    def _get_content_type(file_path: str) -> str:
        """Get Content-Type based on file extension"""
        ext = Path(file_path).suffix.lower()
        
        content_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mov': 'video/quicktime'
        }
        
        return content_types.get(ext, 'application/octet-stream')
