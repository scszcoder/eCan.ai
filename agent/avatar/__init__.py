"""
Avatar Management Module

This module provides comprehensive avatar management functionality for eCan.ai agents.

Features:
- System default avatars (A001-A007)
- User uploaded avatars with validation
- AI-generated avatar videos (coming soon)
- Local and cloud storage management
- Avatar resource tracking

Usage:
    from agent.avatar import AvatarManager
    
    manager = AvatarManager(user_id="user123")
    avatars = manager.get_system_avatars()
"""

from .avatar_manager import AvatarManager, init_system_avatars, check_system_avatars
from .avatar_url_utils import (
    get_server_base_url,
    file_path_to_http_url,
    build_avatar_urls,
    build_system_avatar_info,
    convert_paths_to_urls,
    batch_convert_paths_to_urls
)

__all__ = [
    'AvatarManager',
    'init_system_avatars',
    'check_system_avatars',
    'get_server_base_url',
    'file_path_to_http_url',
    'build_avatar_urls',
    'build_system_avatar_info',
    'convert_paths_to_urls',
    'batch_convert_paths_to_urls'
]

__version__ = '1.0.0'
