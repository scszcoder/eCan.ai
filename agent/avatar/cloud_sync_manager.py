"""
Cloud sync manager for avatar resources.

Handles automatic synchronization between local storage and cloud storage.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from .cloud_storage import S3StorageService, create_s3_storage_service
from ..db.models.avatar_model import DBAvatarResource
from sqlalchemy.orm import Session

from utils.logger_helper import logger_helper as logger


class CloudSyncManager:
    """云端同步管理器"""
    
    def __init__(self, db_session: Session, cloud_service: S3StorageService = None):
        """
        初始化云端同步管理器
        
        Args:
            db_session: 数据库会话
            cloud_service: 云存储服务，如果为 None 则自动创建
        """
        self.db_session = db_session
        self.cloud_service = cloud_service or create_s3_storage_service()
        
        if self.cloud_service:
            logger.info("✅ Cloud sync manager initialized")
        else:
            logger.warning("⚠️  Cloud sync manager initialized without cloud service")
    
    def is_enabled(self) -> bool:
        """检查云端同步是否启用"""
        return self.cloud_service is not None
    
    def sync_avatar_to_cloud(
        self,
        avatar_resource: DBAvatarResource,
        force: bool = False
    ) -> bool:
        """
        同步头像资源到云端
        
        Args:
            avatar_resource: 头像资源对象
            force: 是否强制同步（即使已同步）
        
        Returns:
            是否同步成功
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled, skipping sync")
            return False
        
        # 检查是否需要同步
        if avatar_resource.cloud_synced and not force:
            logger.info(f"Avatar {avatar_resource.id} already synced, skipping")
            return True
        
        try:
            success = True
            
            # 同步图片
            if avatar_resource.image_path and os.path.exists(avatar_resource.image_path):
                image_success = self._sync_file_to_cloud(
                    avatar_resource,
                    avatar_resource.image_path,
                    'image'
                )
                success = success and image_success
            
            # 同步视频
            if avatar_resource.video_path and os.path.exists(avatar_resource.video_path):
                video_success = self._sync_file_to_cloud(
                    avatar_resource,
                    avatar_resource.video_path,
                    'video'
                )
                success = success and video_success
            
            # 更新同步状态
            if success:
                avatar_resource.cloud_synced = True
                self.db_session.commit()
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
        同步单个文件到云端
        
        Args:
            avatar_resource: 头像资源对象
            local_path: 本地文件路径
            file_type: 文件类型（image 或 video）
        
        Returns:
            是否同步成功
        """
        try:
            # 构建云端 key
            file_hash = avatar_resource.image_hash if file_type == 'image' else avatar_resource.video_hash
            file_ext = Path(local_path).suffix
            cloud_key = f"{avatar_resource.owner}/{file_type}s/{file_hash}{file_ext}"
            
            # 检测文件类型
            content_type = self._get_content_type(local_path)
            
            # 准备元数据
            metadata = {
                'resource_id': avatar_resource.id,
                'resource_type': avatar_resource.resource_type,
                'owner': avatar_resource.owner,
                'file_type': file_type,
                'upload_time': datetime.utcnow().isoformat()
            }
            
            # 上传到云端
            success, cloud_url, error = self.cloud_service.upload_file(
                local_path,
                cloud_key,
                content_type=content_type,
                metadata=metadata
            )
            
            if success:
                # 更新数据库记录
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
        从云端同步头像资源到本地
        
        Args:
            avatar_resource: 头像资源对象
            force: 是否强制同步（即使本地已存在）
        
        Returns:
            是否同步成功
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled, skipping sync")
            return False
        
        try:
            success = True
            
            # 同步图片
            if avatar_resource.cloud_image_key:
                if force or not (avatar_resource.image_path and os.path.exists(avatar_resource.image_path)):
                    image_success = self._sync_file_from_cloud(
                        avatar_resource,
                        avatar_resource.cloud_image_key,
                        'image'
                    )
                    success = success and image_success
            
            # 同步视频
            if avatar_resource.cloud_video_key:
                if force or not (avatar_resource.video_path and os.path.exists(avatar_resource.video_path)):
                    video_success = self._sync_file_from_cloud(
                        avatar_resource,
                        avatar_resource.cloud_video_key,
                        'video'
                    )
                    success = success and video_success
            
            if success:
                self.db_session.commit()
                logger.info(f"✅ Avatar {avatar_resource.id} synced from cloud")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to sync avatar {avatar_resource.id} from cloud: {e}")
            return False
    
    def _sync_file_from_cloud(
        self,
        avatar_resource: DBAvatarResource,
        cloud_key: str,
        file_type: str
    ) -> bool:
        """
        从云端同步单个文件到本地
        
        Args:
            avatar_resource: 头像资源对象
            cloud_key: 云端存储 key
            file_type: 文件类型（image 或 video）
        
        Returns:
            是否同步成功
        """
        try:
            # 构建本地路径
            file_hash = avatar_resource.image_hash if file_type == 'image' else avatar_resource.video_hash
            file_ext = Path(cloud_key).suffix
            
            # 获取本地存储目录
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
            
            # 从云端下载
            success, error = self.cloud_service.download_file(cloud_key, local_path)
            
            if success:
                # 更新数据库记录
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
        从云端删除头像资源
        
        Args:
            avatar_resource: 头像资源对象
        
        Returns:
            是否删除成功
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled, skipping delete")
            return False
        
        try:
            success = True
            
            # 删除图片
            if avatar_resource.cloud_image_key:
                image_success, error = self.cloud_service.delete_file(
                    avatar_resource.cloud_image_key
                )
                if not image_success:
                    logger.error(f"❌ Failed to delete image from cloud: {error}")
                success = success and image_success
            
            # 删除视频
            if avatar_resource.cloud_video_key:
                video_success, error = self.cloud_service.delete_file(
                    avatar_resource.cloud_video_key
                )
                if not video_success:
                    logger.error(f"❌ Failed to delete video from cloud: {error}")
                success = success and video_success
            
            if success:
                # 更新数据库记录
                avatar_resource.cloud_image_url = None
                avatar_resource.cloud_video_url = None
                avatar_resource.cloud_image_key = None
                avatar_resource.cloud_video_key = None
                avatar_resource.cloud_synced = False
                self.db_session.commit()
                
                logger.info(f"✅ Avatar {avatar_resource.id} deleted from cloud")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to delete avatar {avatar_resource.id} from cloud: {e}")
            return False
    
    def get_avatar_url(
        self,
        avatar_resource: DBAvatarResource,
        file_type: str = 'image',
        use_cdn: bool = True,
        expires_in: int = 3600
    ) -> Optional[str]:
        """
        获取头像访问 URL（优先使用云端 URL）
        
        Args:
            avatar_resource: 头像资源对象
            file_type: 文件类型（image 或 video）
            use_cdn: 是否使用 CDN
            expires_in: URL 过期时间（秒）
        
        Returns:
            访问 URL，如果不可用则返回 None
        """
        if not self.is_enabled():
            # 云端未启用，返回本地路径
            if file_type == 'image':
                return avatar_resource.image_path
            else:
                return avatar_resource.video_path
        
        try:
            # 优先使用云端 URL
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
                # 云端不可用，返回本地路径
                if file_type == 'image':
                    return avatar_resource.image_path
                else:
                    return avatar_resource.video_path
                    
        except Exception as e:
            logger.error(f"❌ Failed to get avatar URL: {e}")
            # 降级到本地路径
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
        批量同步头像
        
        Args:
            owner: 所有者用户名（None 表示所有用户）
            resource_type: 资源类型（None 表示所有类型）
            direction: 同步方向（to_cloud 或 from_cloud）
        
        Returns:
            同步统计信息 {'total': 10, 'success': 8, 'failed': 2}
        """
        if not self.is_enabled():
            logger.warning("⚠️  Cloud sync disabled")
            return {'total': 0, 'success': 0, 'failed': 0}
        
        try:
            # 查询需要同步的头像
            query = self.db_session.query(DBAvatarResource)
            
            if owner:
                query = query.filter(DBAvatarResource.owner == owner)
            if resource_type:
                query = query.filter(DBAvatarResource.resource_type == resource_type)
            
            avatars = query.all()
            
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
        """根据文件扩展名获取 Content-Type"""
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
