"""
Avatar IPC Handler - Handles avatar-related IPC requests.

This handler provides endpoints for:
- Getting system default avatars
- Uploading user avatars
- Generating avatar videos
- Setting agent avatars
- Managing avatar resources
"""

import base64
import time
from pathlib import Path
from typing import Dict, Optional, Any

from agent.avatar.avatar_manager import AvatarManager
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger


class AvatarHandler:
    """Handler for avatar-related IPC requests."""
    
    def __init__(self):
        # Removed avatar_managers cache - create on-demand for better decoupling
        logger.info("[AvatarHandler] Initialized")
    
    def _get_avatar_manager(self, username: str) -> AvatarManager:
        """
        Create AvatarManager on-demand for each request.
        
        This ensures fresh instances with correct db_avatar_service,
        avoiding stale cache issues and improving decoupling.
        
        Args:
            username: User identifier
            
        Returns:
            AvatarManager: Fresh instance with db_avatar_service
        """
        # Get avatar_service from ECDBMgr
        ctx = get_handler_context(request, params)
        avatar_service = None
        if ctx:
            # Use the unified avatar_service from ECDBMgr
            avatar_service = ctx.get_ec_db_mgr().avatar_service
        
        # Create fresh AvatarManager instance for each request
        return AvatarManager(
            user_id=username,
            db_service=avatar_service
        )
    
    # ==================== Get Avatar Resource ====================
    
    def get_avatar_resource(self, request: Dict) -> Dict:
        """
        Get avatar resource info, automatically check and restore missing files from cloud.
        
        Request:
        {
            "username": "user123",
            "avatarResourceId": "avatar_abc123"
        }
        
        Response:
        {
            "success": true,
            "data": {
                "id": "avatar_abc123",
                "type": "uploaded",
                "name": "My Avatar",
                "imageUrl": "/path/to/image.png",
                "videoUrl": "/path/to/video.mp4",
                "cloudImageUrl": "https://s3.../image.png",
                "cloudVideoUrl": "https://s3.../video.mp4",
                "cloudSynced": true,
                "metadata": {...}
            }
        }
        """
        try:
            username = request.get('username')
            avatar_resource_id = request.get('avatarResourceId')
            
            if not username:
                return {
                    "success": False,
                    "error": "Missing required parameter: username"
                }
            
            if not avatar_resource_id:
                return {
                    "success": False,
                    "error": "Missing required parameter: avatarResourceId"
                }
            
            avatar_manager = self._get_avatar_manager(username)
            
            # Get avatar resource, automatically check and restore missing files
            avatar_data = avatar_manager.get_avatar_info(avatar_resource_id, auto_restore=True)
            
            if avatar_data:
                return {
                    "success": True,
                    "data": avatar_data
                }
            else:
                return {
                    "success": False,
                    "error": "Avatar resource not found"
                }
        except Exception as e:
            logger.error(f"[AvatarHandler] get_avatar_resource error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== System Avatars ====================
    
    def get_system_avatars(self, request: Dict) -> Dict:
        """
        Get list of system default avatars.
        
        Request: {}
        
        Response:
        {
            "success": true,
            "data": [
                {
                    "id": "A001",
                    "name": "Professional Male",
                    "tags": ["professional", "male", "formal"],
                    "type": "system",
                    "imageUrl": "/avatars/system/A001.png",
                    "videoUrl": "/avatars/system/A001.mp4",
                    "imageExists": true,
                    "videoExists": true
                },
                ...
            ]
        }
        """
        try:
            import urllib.parse
            username = request.get('username')
            
            if not username:
                return {
                    "success": False,
                    "error": "Missing required parameter: username"
                }
            
            avatar_manager = self._get_avatar_manager(username)
            
            avatars = avatar_manager.get_system_avatars()
            
            # Convert paths to HTTP URLs using unified utility
            from agent.avatar.avatar_url_utils import batch_convert_paths_to_urls
            batch_convert_paths_to_urls(avatars, ['imageUrl', 'videoUrl', 'videoMp4Path', 'videoWebmPath'])
            
            return {
                "success": True,
                "data": avatars
            }
        except Exception as e:
            logger.error(f"[AvatarHandler] get_system_avatars error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Upload Avatar ====================
    
    async def upload_avatar(self, request: Dict) -> Dict:
        """
        Upload user avatar image OR video.
        
        Request:
        {
            "username": "user123",
            "fileData": "base64_encoded_image_or_video_data",
            "filename": "avatar.png" or "avatar.webm",
            "fileType": "image" or "video"  // optional, auto-detected from filename
        }
        
        Response:
        {
            "success": true,
            "data": {
                "id": "avatar_abc123",
                "imageUrl": "/avatars/uploaded/abc123_original.png",
                "thumbnailUrl": "/avatars/uploaded/abc123_thumb.png",
                "videoUrl": "/avatars/uploaded/abc123_video.webm",  // if video uploaded
                "hash": "abc123",
                "metadata": {
                    "format": "png" or "webm",
                    "size": 12345,
                    "dimensions": [512, 512]  // for images
                }
            }
        }
        """
        try:
            username = request.get('username')
            file_data_b64 = request.get('fileData')
            filename = request.get('filename', 'avatar.png')
            file_type = request.get('fileType')  # 'image' or 'video'
            
            if not username or not file_data_b64:
                return {
                    "success": False,
                    "error": "Missing required parameters: username, fileData"
                }
            
            # Decode base64 file data
            try:
                file_data = base64.b64decode(file_data_b64)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Invalid base64 data: {str(e)}"
                }
            
            # Auto-detect file type if not provided
            if not file_type:
                ext = Path(filename).suffix.lower().lstrip('.')
                if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                    file_type = 'image'
                elif ext in ['mp4', 'webm', 'mov', 'avi']:
                    file_type = 'video'
                else:
                    return {
                        "success": False,
                        "error": f"Unknown file type: {ext}"
                    }
            
            avatar_manager = self._get_avatar_manager(username)
            
            # Handle video upload
            if file_type == 'video':
                result = await avatar_manager.upload_avatar_video(file_data, filename)
            else:
                result = await avatar_manager.upload_avatar(file_data, filename)
            
            if result["success"]:
                # Convert paths to HTTP URLs using unified utility
                from agent.avatar.avatar_url_utils import convert_paths_to_urls
                convert_paths_to_urls(result, ['imageUrl', 'thumbnailUrl', 'videoUrl'])
                
                # For video uploads, skip video generation
                if file_type == 'video':
                    logger.info("[AvatarHandler] Video uploaded directly, skipping video generation")
                    return {
                        "success": True,
                        "data": result
                    }
                
                # Check if video generation is enabled (for image uploads)
                from agent.avatar.video_generator import ENABLE_AVATAR_VIDEO_GENERATION
                
                if not ENABLE_AVATAR_VIDEO_GENERATION:
                    logger.info("[AvatarHandler] Video generation is disabled by configuration")
                    return {
                        "success": True,
                        "data": result
                    }
                
                # Get additional context for video generation
                org_name = request.get('orgName')  # Organization name from request
                agent_id = request.get('agentId')  # Agent ID if available
                avatar_id = result.get('id')  # Avatar resource ID
                
                # Generate avatar video in background (after response sent)
                try:
                    # Check if MainWindow is available
                    ctx = get_handler_context(request, params)
                    if ctx:
                        # Get organization name from agent if not provided
                        if not org_name and agent_id and ctx.get_ec_db_mgr():
                            try:
                                agent_service = ctx.get_ec_db_mgr().agent_service
                                agent = agent_service.get_agent(agent_id)
                                if agent and agent.get('org_id'):
                                    org_service = ctx.get_ec_db_mgr().org_service
                                    org = org_service.get_organization(agent['org_id'])
                                    if org:
                                        org_name = org.get('name')
                                        logger.info(f"[AvatarHandler] Retrieved org name from agent: {org_name}")
                            except Exception as e:
                                logger.warning(f"[AvatarHandler] Failed to get org name from agent: {e}")
                        
                        # Trigger video generation in background
                        logger.info(f"[AvatarHandler] Triggering video generation for avatar: {avatar_id}")
                        logger.info(f"[AvatarHandler] Organization context: {org_name or 'None'}")
                        
                        # Import and call video generator
                        from agent.avatar.video_generator import generate_avatar_video
                        import asyncio
                        import threading
                        
                        def generate_video_background():
                                """Background thread for video generation"""
                                try:
                                    # Create new event loop for this thread
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    
                                    # Get the actual file path (not HTTP URL)
                                    # The image_path at this point is still local path
                                    actual_image_path = result.get('imageUrl')
                                    if actual_image_path and actual_image_path.startswith('http'):
                                        # If already converted to URL, we need to get the original path
                                        # from the avatar manager
                                        from pathlib import Path
                                        hash_value = result.get('hash')
                                        if hash_value:
                                            from config.app_info import app_info
                                            resource_dir = Path(app_info.app_resources_path)
                                            actual_image_path = str(resource_dir / "avatars" / "uploaded" / f"{hash_value}_original.png")
                                    
                                    # Generate video
                                    video_result = loop.run_until_complete(
                                        generate_avatar_video(
                                            image_path=actual_image_path,
                                            org_name=org_name,
                                            llm=ctx.get_llm() if True else None,
                                            output_dir=None,  # Use same directory as image
                                            duration=5.0
                                        )
                                    )
                                    
                                    if video_result.get('success'):
                                        webm_path = video_result.get('webm_path')
                                        mp4_path = video_result.get('mp4_path')
                                        
                                        logger.info(f"[AvatarHandler] ✅ Video generation completed")
                                        logger.info(f"[AvatarHandler]   - WebM: {webm_path}")
                                        logger.info(f"[AvatarHandler]   - MP4: {mp4_path}")
                                        
                                        # Update avatar resource with both video paths
                                        # Frontend will choose which format to use based on browser support
                                        if ctx.get_ec_db_mgr():
                                            avatar_service = ctx.get_ec_db_mgr().avatar_service
                                            # Use WebM as primary video_path for backward compatibility
                                            # But store both paths in metadata for frontend to choose
                                            update_data = {
                                                'video_path': webm_path if webm_path else mp4_path
                                            }
                                            
                                            # Add metadata
                                            avatar_resource = avatar_service.get_avatar_resource(avatar_id)
                                            if avatar_resource:
                                                metadata = avatar_resource.get('avatar_metadata', {})
                                                metadata.update({
                                                    'video_mp4_path': video_result.get('mp4_path'),
                                                    'video_webm_path': video_result.get('webm_path'),
                                                    'video_duration': video_result.get('duration'),
                                                    'video_prompt': video_result.get('prompt'),
                                                    'video_generated_at': time.time()
                                                })
                                                update_data['avatar_metadata'] = metadata
                                            
                                            avatar_service.update_avatar_resource(avatar_id, update_data)
                                            logger.info(f"[AvatarHandler] ✅ Avatar resource updated with video paths")
                                            
                                            # Upload video to S3 if cloud sync is enabled
                                            avatar_resource = avatar_service.get_avatar_resource(avatar_id)
                                            if avatar_resource:
                                                from agent.db.models.avatar_model import DBAvatarResource
                                                if isinstance(avatar_resource, dict):
                                                    db_avatar = DBAvatarResource(
                                                        id=avatar_resource['id'],
                                                        resource_type=avatar_resource['resource_type'],
                                                        name=avatar_resource.get('name'),
                                                        image_path=avatar_resource.get('image_path'),
                                                        image_hash=avatar_resource.get('image_hash'),
                                                        video_path=avatar_resource.get('video_path'),
                                                        avatar_metadata=avatar_resource.get('avatar_metadata', {}),
                                                        owner=avatar_resource.get('owner')
                                                    )
                                                else:
                                                    db_avatar = avatar_resource
                                                
                                                # Upload to S3 in background
                                                from agent.avatar.avatar_cloud_sync import upload_avatar_to_cloud_async
                                                upload_avatar_to_cloud_async(db_avatar, db_service=avatar_service)
                                    else:
                                        logger.error(f"[AvatarHandler] ❌ Video generation failed: {video_result.get('error')}")
                                    
                                    loop.close()
                                except Exception as e:
                                    logger.error(f"[AvatarHandler] ❌ Error in background video generation: {e}", exc_info=True)
                        
                        # Start video generation in background thread
                        video_thread = threading.Thread(target=generate_video_background, daemon=True)
                        video_thread.start()
                        logger.info("[AvatarHandler] Video generation started in background thread")
                    else:
                        logger.warning("[AvatarHandler] MainWindow not available, skipping video generation")
                except Exception as e:
                    # Don't fail the upload if video generation fails
                    logger.warning(f"[AvatarHandler] Failed to trigger video generation: {e}")
                
                return {
                    "success": True,
                    "data": result
                }
            else:
                return result
        except Exception as e:
            logger.error(f"[AvatarHandler] upload_avatar error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Get Uploaded Avatars ====================
    
    def get_uploaded_avatars(self, request: Dict) -> Dict:
        """
        Get list of user uploaded avatars.
        
        Request:
        {
            "username": "user123"
        }
        
        Response:
        {
            "success": true,
            "data": [
                {
                    "type": "uploaded",
                    "hash": "abc123",
                    "imageUrl": "/avatars/uploaded/abc123_original.png",
                    "thumbnailUrl": "/avatars/uploaded/abc123_thumb.png",
                    "videoUrl": "/avatars/generated/abc123_video.mp4"
                },
                ...
            ]
        }
        """
        try:
            import urllib.parse
            username = request.get('username')
            
            if not username:
                return {
                    "success": False,
                    "error": "Missing required parameter: username"
                }
            
            avatar_manager = self._get_avatar_manager(username)
            
            avatars = avatar_manager.get_uploaded_avatars()
            
            # Convert paths to HTTP URLs using unified utility
            from agent.avatar.avatar_url_utils import batch_convert_paths_to_urls
            batch_convert_paths_to_urls(avatars, ['imageUrl', 'thumbnailUrl', 'videoUrl'])
            
            return {
                "success": True,
                "data": avatars
            }
        except Exception as e:
            logger.error(f"[AvatarHandler] get_uploaded_avatars error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Delete Uploaded Avatar ====================
    
    async def delete_uploaded_avatar(self, request: Dict) -> Dict:
        """
        Delete an uploaded avatar.
        
        Request:
        {
            "username": "user123",
            "avatarId": "avatar_abc123"
        }
        
        Response:
        {
            "success": true,
            "data": {
                "deleted_files": [...]
            }
        }
        """
        try:
            username = request.get('username')
            avatar_id = request.get('avatarId')
            
            if not username or not avatar_id:
                return {
                    "success": False,
                    "error": "Missing required parameters: username, avatarId"
                }
            
            avatar_manager = self._get_avatar_manager(username)
            result = await avatar_manager.delete_uploaded_avatar(avatar_id)
            
            if result["success"]:
                return {
                    "success": True,
                    "data": result
                }
            else:
                return result
        except Exception as e:
            logger.error(f"[AvatarHandler] delete_uploaded_avatar error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Set Agent Avatar ====================
    
    async def set_agent_avatar(self, request: Dict) -> Dict:
        """
        Set avatar for an agent.
        
        Request:
        {
            "username": "user123",
            "agentId": "agent_abc123",
            "avatarType": "system",  // system, uploaded, generated
            "imageUrl": "/avatars/system/A001.png",
            "videoUrl": "/avatars/system/A001.mp4",  // optional
            "metadata": {}  // optional
        }
        
        Response:
        {
            "success": true,
            "data": {
                "agent_id": "agent_abc123",
                "avatar_type": "system",
                "avatar_image_url": "/avatars/system/A001.png",
                "avatar_video_url": "/avatars/system/A001.mp4"
            }
        }
        """
        try:
            username = request.get('username')
            agent_id = request.get('agentId')
            avatar_type = request.get('avatarType')
            image_url = request.get('imageUrl')
            video_url = request.get('videoUrl')
            metadata = request.get('metadata')
            
            if not username or not agent_id or not avatar_type or not image_url:
                return {
                    "success": False,
                    "error": "Missing required parameters: username, agentId, avatarType, imageUrl"
                }
            
            avatar_manager = self._get_avatar_manager(username)
            result = await avatar_manager.set_agent_avatar(
                agent_id=agent_id,
                avatar_type=avatar_type,
                image_url=image_url,
                video_url=video_url,
                metadata=metadata
            )
            
            if result["success"]:
                return {
                    "success": True,
                    "data": result
                }
            else:
                return result
        except Exception as e:
            logger.error(f"[AvatarHandler] set_agent_avatar error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Generate Avatar Video ====================
    
    async def generate_avatar_video(self, request: Dict) -> Dict:
        """
        Generate avatar animation video from image using AI.
        
        Request:
        {
            "username": "user123",
            "imagePath": "/avatars/uploaded/abc123_original.png",
            "model": "stable-diffusion-video",  // optional
            "params": {  // optional
                "duration": 3.0,
                "motion_type": "subtle"
            }
        }
        
        Response:
        {
            "success": true,
            "data": {
                "videoUrl": "/avatars/generated/abc123_video.mp4",
                "duration": 3.0,
                "size": 67890
            }
        }
        """
        try:
            username = request.get('username')
            image_path = request.get('imagePath')
            model = request.get('model', 'stable-diffusion-video')
            params = request.get('params')
            
            if not username or not image_path:
                return {
                    "success": False,
                    "error": "Missing required parameters: username, imagePath"
                }
            
            avatar_manager = self._get_avatar_manager(username)
            result = await avatar_manager.generate_avatar_video(
                image_path=image_path,
                model=model,
                params=params
            )
            
            return result
        except Exception as e:
            logger.error(f"[AvatarHandler] generate_avatar_video error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


# Create singleton instance
avatar_handler = AvatarHandler()


# ==================== IPC Handler Functions ====================

@IPCHandlerRegistry.handler('avatar.get_avatar_resource')
def handle_get_avatar_resource(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Get avatar resource with auto-restore from cloud."""
    try:
        if not params or len(params) < 2:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters: username, avatarResourceId')
        
        username = params[0]
        avatar_resource_id = params[1]
        
        result = avatar_handler.get_avatar_resource({
            'username': username,
            'avatarResourceId': avatar_resource_id
        })
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'GET_AVATAR_RESOURCE_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_get_avatar_resource: {e}", exc_info=True)
        return create_error_response(request, 'GET_AVATAR_RESOURCE_ERROR', str(e))


@IPCHandlerRegistry.handler('avatar.get_system_avatars')
def handle_get_system_avatars(request: IPCRequest, params: Optional[dict[str, Any]]) -> IPCResponse:
    """Get system default avatars."""
    try:
        if not params or 'username' not in params:
            return create_error_response(request, 'MISSING_PARAM', 'Missing required parameter: username')
        username = params['username']
        result = avatar_handler.get_system_avatars({'username': username})
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'GET_SYSTEM_AVATARS_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_get_system_avatars: {e}", exc_info=True)
        return create_error_response(request, 'GET_SYSTEM_AVATARS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('avatar.upload_avatar')
async def handle_upload_avatar(request: IPCRequest, params: Optional[dict[str, Any]]) -> IPCResponse:
    """Upload user avatar."""
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters')
        
        username = params.get('username')
        file_data_b64 = params.get('fileData')
        filename = params.get('filename', 'avatar.png')
        
        if not username or not file_data_b64:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters: username, fileData')
        
        result = await avatar_handler.upload_avatar({
            'username': username,
            'fileData': file_data_b64,
            'filename': filename
        })
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'UPLOAD_AVATAR_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_upload_avatar: {e}", exc_info=True)
        return create_error_response(request, 'UPLOAD_AVATAR_ERROR', str(e))


@IPCHandlerRegistry.handler('avatar.get_uploaded_avatars')
def handle_get_uploaded_avatars(request: IPCRequest, params: Optional[dict[str, Any]]) -> IPCResponse:
    """Get user uploaded avatars."""
    try:
        if not params or 'username' not in params:
            return create_error_response(request, 'MISSING_PARAM', 'Missing required parameter: username')
        username = params['username']
        result = avatar_handler.get_uploaded_avatars({'username': username})
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'GET_UPLOADED_AVATARS_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_get_uploaded_avatars: {e}", exc_info=True)
        return create_error_response(request, 'GET_UPLOADED_AVATARS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('avatar.delete_uploaded_avatar')
async def handle_delete_uploaded_avatar(request: IPCRequest, params: Optional[dict[str, Any]]) -> IPCResponse:
    """Delete an uploaded avatar."""
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters')
        
        username = params.get('username')
        avatar_id = params.get('avatarId')
        
        if not username or not avatar_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters: username, avatarId')
        
        result = await avatar_handler.delete_uploaded_avatar({
            'username': username,
            'avatarId': avatar_id
        })
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'DELETE_UPLOADED_AVATAR_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_delete_uploaded_avatar: {e}", exc_info=True)
        return create_error_response(request, 'DELETE_UPLOADED_AVATAR_ERROR', str(e))


@IPCHandlerRegistry.background_handler('avatar.set_agent_avatar')
async def handle_set_agent_avatar(request: IPCRequest, params: Optional[dict[str, Any]]) -> IPCResponse:
    """Set agent avatar."""
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters')
        
        username = params.get('username')
        agent_id = params.get('agentId')
        avatar_type = params.get('avatarType')
        image_url = params.get('imageUrl')
        video_url = params.get('videoUrl')
        metadata = params.get('metadata')
        
        if not username or not agent_id or not avatar_type or not image_url:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters: username, agentId, avatarType, imageUrl')
        
        result = await avatar_handler.set_agent_avatar({
            'username': username,
            'agentId': agent_id,
            'avatarType': avatar_type,
            'imageUrl': image_url,
            'videoUrl': video_url,
            'metadata': metadata
        })
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'SET_AGENT_AVATAR_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_set_agent_avatar: {e}", exc_info=True)
        return create_error_response(request, 'SET_AGENT_AVATAR_ERROR', str(e))


@IPCHandlerRegistry.background_handler('avatar.generate_avatar_video')
async def handle_generate_avatar_video(request: IPCRequest, params: Optional[dict[str, Any]]) -> IPCResponse:
    """Generate avatar video."""
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters')
        
        username = params.get('username')
        image_path = params.get('imagePath')
        model = params.get('model', 'stable-diffusion-video')
        gen_params = params.get('params')
        
        if not username or not image_path:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameters: username, imagePath')
        
        result = await avatar_handler.generate_avatar_video({
            'username': username,
            'imagePath': image_path,
            'model': model,
            'params': gen_params
        })
        
        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'GENERATE_VIDEO_ERROR', result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"[avatar_handler] Error in handle_generate_avatar_video: {e}", exc_info=True)
        return create_error_response(request, 'GENERATE_VIDEO_ERROR', str(e))
