"""
Avatar database service class.

This module provides database operations for avatar resources,
following the same pattern as other service classes.
"""

from typing import Optional, Dict, Any, List
from sqlalchemy import and_, or_
from .base_service import BaseService
from ..models.avatar_model import DBAvatarResource
from ..models.agent_model import DBAgent
from utils.logger_helper import logger_helper as logger


class DBAvatarService(BaseService):
    """Avatar database service class providing all avatar-related database operations"""
    
    def __init__(self, engine=None, session=None):
        """
        Initialize avatar service.
        
        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
        super().__init__(engine, session)
    
    @classmethod
    def generate_default_avatar(cls, agent_id: str, owner: str = None) -> Optional[Dict[str, Any]]:
        """
        Generate a default random system avatar for an agent.
        
        This method directly uses AvatarManager's static SYSTEM_AVATARS data
        without creating an instance, maintaining decoupling.

        Args:
            agent_id: Agent ID (used as seed for consistent random selection)
            owner: Owner username (optional, kept for backward compatibility but not used)

        Returns:
            dict: Avatar information with id, imageUrl, videoPath, videoExists
            None: If avatar generation fails
        """
        try:
            # Use AvatarManager's static system avatars data
            from agent.avatar.avatar_manager import AvatarManager
            system_avatars = AvatarManager.SYSTEM_AVATARS
            
            if not system_avatars:
                logger.warning(f"[DBAvatarService] No system avatars available")
                return None

            # Use agent ID as seed for consistent random selection
            import hashlib
            seed = int(hashlib.md5(agent_id.encode()).hexdigest(), 16)
            avatar_def = system_avatars[seed % len(system_avatars)]
            
            # Use unified avatar URL builder
            from config.app_info import app_info
            from pathlib import Path
            from agent.avatar.avatar_url_utils import build_system_avatar_info
            
            resource_dir = Path(app_info.app_resources_path)
            avatars_dir = resource_dir / "avatars" / "system"
            
            avatar_id = avatar_def['id']
            return build_system_avatar_info(avatar_id, avatars_dir)

        except Exception as e:
            logger.error(f"[DBAvatarService] Failed to generate default avatar: {e}")
            return None
    
    def get_avatar_resource(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        Get avatar resource by ID.
        
        Args:
            avatar_id: Avatar resource ID
            
        Returns:
            Avatar resource dict or None if not found
        """
        try:
            with self.session_scope() as session:
                avatar_resource = session.query(DBAvatarResource).filter_by(
                    id=avatar_id
                ).first()
                
                if not avatar_resource:
                    logger.debug(f"[DBAvatarService] Avatar resource not found: {avatar_id}")
                    return None
                
                return {
                    'id': avatar_resource.id,
                    'resource_type': avatar_resource.resource_type,
                    'name': avatar_resource.name,
                    'image_path': avatar_resource.image_path,
                    'image_hash': avatar_resource.image_hash,
                    'video_path': avatar_resource.video_path,
                    'avatar_metadata': avatar_resource.avatar_metadata,
                    'owner': avatar_resource.owner,
                    'created_at': avatar_resource.created_at,
                    'updated_at': avatar_resource.updated_at
                }
        except Exception as e:
            logger.error(f"[DBAvatarService] Error getting avatar resource {avatar_id}: {e}")
            return None
    
    def get_avatar_resources_by_owner(self, owner: str, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all avatar resources for a specific owner.
        
        Args:
            owner: Owner username
            resource_type: Optional filter by resource type ('uploaded', 'generated', etc.)
            
        Returns:
            List of avatar resource dicts
        """
        try:
            with self.session_scope() as session:
                query = session.query(DBAvatarResource).filter_by(owner=owner)
                
                if resource_type:
                    query = query.filter_by(resource_type=resource_type)
                
                resources = query.order_by(DBAvatarResource.created_at.desc()).all()
                
                return [
                    {
                        'id': r.id,
                        'resource_type': r.resource_type,
                        'name': r.name,
                        'image_path': r.image_path,
                        'image_hash': r.image_hash,
                        'video_path': r.video_path,
                        'avatar_metadata': r.avatar_metadata,
                        'owner': r.owner,
                        'created_at': r.created_at,
                        'updated_at': r.updated_at
                    }
                    for r in resources
                ]
        except Exception as e:
            logger.error(f"[DBAvatarService] Error getting avatar resources for owner {owner}: {e}")
            return []
    
    def create_avatar_resource(self, resource_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new avatar resource.
        
        Args:
            resource_data: Avatar resource data dict
            
        Returns:
            Avatar resource ID if successful, None otherwise
        """
        try:
            with self.session_scope() as session:
                # Check if already exists
                existing = session.query(DBAvatarResource).filter_by(
                    id=resource_data.get('id')
                ).first()
                
                if existing:
                    logger.info(f"[DBAvatarService] Avatar resource already exists: {resource_data.get('id')}")
                    return existing.id
                
                # Create new resource
                avatar_resource = DBAvatarResource(
                    id=resource_data.get('id'),
                    resource_type=resource_data.get('resource_type', 'uploaded'),
                    name=resource_data.get('name'),
                    image_path=resource_data.get('image_path'),
                    image_hash=resource_data.get('image_hash'),
                    video_path=resource_data.get('video_path'),
                    avatar_metadata=resource_data.get('avatar_metadata', {}),
                    owner=resource_data.get('owner')
                )
                
                session.add(avatar_resource)
                session.flush()
                
                logger.info(f"[DBAvatarService] Created avatar resource: {avatar_resource.id}")
                return avatar_resource.id
                
        except Exception as e:
            logger.error(f"[DBAvatarService] Error creating avatar resource: {e}")
            return None
    
    def update_avatar_resource(self, avatar_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an existing avatar resource.
        
        Args:
            avatar_id: Avatar resource ID
            update_data: Data to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.session_scope() as session:
                avatar_resource = session.query(DBAvatarResource).filter_by(
                    id=avatar_id
                ).first()
                
                if not avatar_resource:
                    logger.warning(f"[DBAvatarService] Avatar resource not found for update: {avatar_id}")
                    return False
                
                # Update fields
                for key, value in update_data.items():
                    if hasattr(avatar_resource, key) and key != 'id':
                        setattr(avatar_resource, key, value)
                
                session.flush()
                logger.info(f"[DBAvatarService] Updated avatar resource: {avatar_id}")
                return True
                
        except Exception as e:
            logger.error(f"[DBAvatarService] Error updating avatar resource {avatar_id}: {e}")
            return False
    
    def delete_avatar_resource(self, avatar_id: str) -> bool:
        """
        Delete an avatar resource from database.
        Also clears all agent references to this avatar to maintain data consistency.
        
        Args:
            avatar_id: Avatar resource ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.session_scope() as session:
                avatar_resource = session.query(DBAvatarResource).filter_by(
                    id=avatar_id
                ).first()
                
                if not avatar_resource:
                    logger.warning(f"[DBAvatarService] Avatar resource not found for deletion: {avatar_id}")
                    return False
                
                # First, clear all agent references to this avatar to prevent data inconsistency
                from ..models.agent_model import DBAgent
                agents_using_avatar = session.query(DBAgent).filter_by(
                    avatar_resource_id=avatar_id
                ).all()
                
                if agents_using_avatar:
                    logger.warning(f"[DBAvatarService] Found {len(agents_using_avatar)} agents using avatar {avatar_id}, clearing references...")
                    for agent in agents_using_avatar:
                        logger.info(f"[DBAvatarService] Clearing avatar reference for agent {agent.id}")
                        agent.avatar_resource_id = None
                        agent.avatar_type = None
                    session.flush()
                    logger.info(f"[DBAvatarService] ✅ Cleared avatar references for {len(agents_using_avatar)} agents")
                
                # Now delete the avatar resource
                session.delete(avatar_resource)
                session.flush()
                
                logger.info(f"[DBAvatarService] Deleted avatar resource: {avatar_id}")
                return True
                
        except Exception as e:
            logger.error(f"[DBAvatarService] Error deleting avatar resource {avatar_id}: {e}")
            return False
    
    def check_avatar_exists(self, avatar_id: str) -> bool:
        """
        Check if an avatar resource exists.
        
        Args:
            avatar_id: Avatar resource ID
            
        Returns:
            True if exists, False otherwise
        """
        try:
            with self.session_scope() as session:
                exists = session.query(DBAvatarResource).filter_by(
                    id=avatar_id
                ).first() is not None
                
                return exists
        except Exception as e:
            logger.error(f"[DBAvatarService] Error checking avatar existence {avatar_id}: {e}")
            return False
    
    def get_avatar_by_hash(self, image_hash: str, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get avatar resource by image hash (for deduplication).
        
        Args:
            image_hash: Image hash
            owner: Optional owner filter
            
        Returns:
            Avatar resource dict or None if not found
        """
        try:
            with self.session_scope() as session:
                query = session.query(DBAvatarResource).filter_by(image_hash=image_hash)
                
                if owner:
                    query = query.filter_by(owner=owner)
                
                avatar_resource = query.first()
                
                if not avatar_resource:
                    return None
                
                return {
                    'id': avatar_resource.id,
                    'resource_type': avatar_resource.resource_type,
                    'name': avatar_resource.name,
                    'image_path': avatar_resource.image_path,
                    'image_hash': avatar_resource.image_hash,
                    'video_path': avatar_resource.video_path,
                    'avatar_metadata': avatar_resource.avatar_metadata,
                    'owner': avatar_resource.owner,
                    'created_at': avatar_resource.created_at,
                    'updated_at': avatar_resource.updated_at
                }
        except Exception as e:
            logger.error(f"[DBAvatarService] Error getting avatar by hash {image_hash}: {e}")
            return None
    
    def get_all_avatar_resources(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all avatar resources (for admin purposes).
        
        Args:
            limit: Optional limit on number of results
            
        Returns:
            List of avatar resource dicts
        """
        try:
            with self.session_scope() as session:
                query = session.query(DBAvatarResource).order_by(
                    DBAvatarResource.created_at.desc()
                )
                
                if limit:
                    query = query.limit(limit)
                
                resources = query.all()
                
                return [
                    {
                        'id': r.id,
                        'resource_type': r.resource_type,
                        'name': r.name,
                        'image_path': r.image_path,
                        'image_hash': r.image_hash,
                        'video_path': r.video_path,
                        'avatar_metadata': r.avatar_metadata,
                        'owner': r.owner,
                        'created_at': r.created_at,
                        'updated_at': r.updated_at
                    }
                    for r in resources
                ]
        except Exception as e:
            logger.error(f"[DBAvatarService] Error getting all avatar resources: {e}")
            return []
    
    def get_agent_avatar_info(self, agent: DBAgent, owner: str = None) -> Optional[Dict[str, Any]]:
        """
        Get avatar information for an agent.
        
        Returns complete avatar information including URLs for frontend display.

        Args:
            agent: DBAgent instance
            owner: Owner username (kept for backward compatibility)

        Returns:
            dict: Avatar information with id, type, imageUrl, videoPath, videoExists
            None: If agent has no avatar
        """
        try:
            # If agent has no avatar_resource_id, generate a default one
            if not agent.avatar_resource_id:
                logger.debug(f"[DBAvatarService] No avatar for agent {agent.id}, generating default")
                return self.generate_default_avatar(agent.id, owner)
            
            # Determine avatar type
            avatar_type = 'system' if agent.avatar_resource_id.startswith('A00') else 'uploaded'
            
            # For system avatars, build URLs directly
            if avatar_type == 'system':
                from config.app_info import app_info
                from pathlib import Path
                from agent.avatar.avatar_url_utils import build_system_avatar_info
                
                resource_dir = Path(app_info.app_resources_path)
                avatars_dir = resource_dir / "avatars" / "system"
                
                avatar_id = agent.avatar_resource_id
                return build_system_avatar_info(avatar_id, avatars_dir)
            
            # For uploaded avatars, query from database and build URLs
            logger.debug(f"[DBAvatarService] Querying uploaded avatar: {agent.avatar_resource_id}")
            avatar_resource = self.get_avatar_resource(agent.avatar_resource_id)
            
            if not avatar_resource:
                # Data inconsistency: agent references non-existent avatar
                logger.error(f"[DBAvatarService] ❌ DATA INCONSISTENCY: Agent {agent.id} references non-existent uploaded avatar {agent.avatar_resource_id}")
                logger.error(f"[DBAvatarService] This indicates a bug in avatar upload or deletion logic. 加保护")
                
                # Auto-fix: Clear the invalid avatar reference and use default avatar
                try:
                    logger.warning(f"[DBAvatarService] Auto-fixing: Clearing invalid avatar_resource_id for agent {agent.id}")
                    with self.session_scope() as s:
                        agent_to_fix = s.get(DBAgent, agent.id)
                        if agent_to_fix:
                            agent_to_fix.avatar_resource_id = None
                            agent_to_fix.avatar_type = None
                            s.flush()
                            logger.info(f"[DBAvatarService] ✅ Successfully cleared invalid avatar reference for agent {agent.id}")
                        else:
                            logger.error(f"[DBAvatarService] Failed to find agent {agent.id} for auto-fix")
                except Exception as fix_error:
                    logger.error(f"[DBAvatarService] Failed to auto-fix agent {agent.id}: {fix_error}")
                
                # Return default avatar to keep system running
                logger.info(f"[DBAvatarService] Returning default avatar for agent {agent.id}")
                return self.generate_default_avatar(agent.id, owner)
            
            logger.debug(f"[DBAvatarService] Found uploaded avatar resource: {avatar_resource['id']}")
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            
            if not main_window:
                logger.error(f"[DBAvatarService] MainWindow not available, cannot build avatar URLs")
                return None
            
            server_url = main_window.get_server_base_url()
            
            # Build URLs using the same format as upload response
            image_url = f"{server_url}/api/avatar?path={avatar_resource['image_path']}"
            video_url = None
            if avatar_resource.get('video_path'):
                video_url = f"{server_url}/api/avatar?path={avatar_resource['video_path']}"
            
            # Get thumbnail URL from metadata if available
            thumbnail_url = image_url  # Default to image
            if avatar_resource.get('avatar_metadata'):
                metadata = avatar_resource['avatar_metadata']
                if isinstance(metadata, dict) and metadata.get('thumbnail_path'):
                    thumbnail_url = f"{server_url}/api/avatar?path={metadata['thumbnail_path']}"
            
            return {
                'id': avatar_resource['id'],
                'type': avatar_type,
                'imageUrl': image_url,
                'thumbnailUrl': thumbnail_url,
                'videoPath': video_url,
                'videoExists': bool(avatar_resource.get('video_path'))
            }

        except Exception as e:
            logger.error(f"[DBAvatarService] Failed to get avatar info for agent {agent.id}: {e}")
            return None
