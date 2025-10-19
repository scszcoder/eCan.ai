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
from typing import Dict, Optional, Any

from agent.avatar.avatar_manager import AvatarManager
from app_context import AppContext
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
        main_window = AppContext.get_main_window()
        avatar_service = None
        if main_window and hasattr(main_window, 'ec_db_mgr'):
            # Use the unified avatar_service from ECDBMgr
            avatar_service = main_window.ec_db_mgr.avatar_service
        
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
            username = request.get('username', 'default')
            avatar_resource_id = request.get('avatarResourceId')
            
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
            username = request.get('username', 'default')
            avatar_manager = self._get_avatar_manager(username)
            
            avatars = avatar_manager.get_system_avatars()
            
            # Convert paths to HTTP URLs using unified utility
            from agent.avatar.avatar_url_utils import batch_convert_paths_to_urls
            batch_convert_paths_to_urls(avatars, ['imageUrl', 'videoMp4Path', 'videoWebmPath'])
            
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
        Upload user avatar image.
        
        Request:
        {
            "username": "user123",
            "fileData": "base64_encoded_image_data",
            "filename": "avatar.png"
        }
        
        Response:
        {
            "success": true,
            "data": {
                "imageUrl": "/avatars/uploaded/abc123_original.png",
                "thumbnailUrl": "/avatars/uploaded/abc123_thumb.png",
                "hash": "abc123",
                "metadata": {
                    "format": "png",
                    "size": 12345,
                    "dimensions": [512, 512]
                }
            }
        }
        """
        try:
            username = request.get('username')
            file_data_b64 = request.get('fileData')
            filename = request.get('filename', 'avatar.png')
            
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
            
            avatar_manager = self._get_avatar_manager(username)
            result = await avatar_manager.upload_avatar(file_data, filename)
            
            if result["success"]:
                # Convert paths to HTTP URLs using unified utility
                from agent.avatar.avatar_url_utils import convert_paths_to_urls
                convert_paths_to_urls(result, ['imageUrl', 'thumbnailUrl'])
                
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
            username = request.get('username', 'default')
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
        username = params.get('username', 'default') if params else 'default'
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
        username = params.get('username', 'default') if params else 'default'
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
