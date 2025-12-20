"""
Avatar URL utilities for converting file paths to HTTP URLs.

This module provides unified functions for avatar URL generation,
avoiding code duplication across multiple files.
"""

import urllib.parse
from typing import Optional, Dict, Any
from pathlib import Path
from utils.logger_helper import logger_helper as logger


def get_server_base_url() -> str:
    """
    Get server base URL from MainWindow.
    
    This is a convenience wrapper that delegates to MainWindow.get_server_base_url().
    MainWindow is the single source of truth for server URL.
    
    Returns:
        str: Base URL like "http://localhost:4668"
    """
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if main_window:
            return main_window.get_server_base_url()
    except Exception as e:
        logger.warning(f"Failed to get server URL from MainWindow: {e}, using default")
    
    # Last resort fallback (should rarely happen)
    return "http://localhost:4668"


def file_path_to_http_url(file_path: Optional[str]) -> Optional[str]:
    """
    Convert a local file path to an HTTP URL via /api/avatar endpoint.
    
    Args:
        file_path: Local file path (absolute path)
        
    Returns:
        str: HTTP URL for accessing the file, or None if file_path is None/empty
        
    Example:
        >>> file_path_to_http_url("/path/to/avatar.png")
        'http://localhost:4668/api/avatar?path=%2Fpath%2Fto%2Favatar.png'
    """
    if not file_path:
        return None
    
    base_url = get_server_base_url()
    encoded_path = urllib.parse.quote(str(file_path))
    return f"{base_url}/api/avatar?path={encoded_path}"


def build_avatar_urls(
    image_path: Optional[str] = None,
    video_path: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    video_mp4_path: Optional[str] = None,
    video_webm_path: Optional[str] = None
) -> Dict[str, Optional[str]]:
    """
    Build avatar URLs from file paths.
    
    Args:
        image_path: Path to image file
        video_path: Path to video file (generic)
        thumbnail_path: Path to thumbnail file
        video_mp4_path: Path to MP4 video file
        video_webm_path: Path to WebM video file
        
    Returns:
        dict: Dictionary with URL keys (imageUrl, videoPath, thumbnailUrl, etc.)
        
    Example:
        >>> build_avatar_urls(
        ...     image_path="/path/to/avatar.png",
        ...     video_webm_path="/path/to/avatar.webm"
        ... )
        {
            'imageUrl': 'http://localhost:4668/api/avatar?path=...',
            'videoPath': 'http://localhost:4668/api/avatar?path=...',
            'thumbnailUrl': None,
            'videoMp4Path': None,
            'videoWebmPath': 'http://localhost:4668/api/avatar?path=...'
        }
    """
    return {
        'imageUrl': file_path_to_http_url(image_path),
        'videoPath': file_path_to_http_url(video_path),
        'thumbnailUrl': file_path_to_http_url(thumbnail_path),
        'videoMp4Path': file_path_to_http_url(video_mp4_path),
        'videoWebmPath': file_path_to_http_url(video_webm_path)
    }


def build_system_avatar_info(
    avatar_id: str,
    avatars_dir: Path,
    include_video: bool = True
) -> Dict[str, Any]:
    """
    Build complete avatar information for a system avatar.
    
    Args:
        avatar_id: Avatar ID (e.g., "A001")
        avatars_dir: Directory containing avatar files
        include_video: Whether to include video URLs
        
    Returns:
        dict: Complete avatar information with URLs
        
    Example:
        >>> build_system_avatar_info("A001", Path("/path/to/avatars"))
        {
            'id': 'A001',
            'type': 'system',
            'imageUrl': 'http://localhost:4668/api/avatar?path=...',
            'videoPath': 'http://localhost:4668/api/avatar?path=...',
            'videoExists': True
        }
    """
    # Build file paths
    image_path = avatars_dir / f"{avatar_id}.png"
    video_mp4_path = avatars_dir / f"{avatar_id}.mp4"
    video_webm_path = avatars_dir / f"{avatar_id}.webm"
    
    # Check video existence
    video_exists = video_webm_path.exists() or video_mp4_path.exists()
    
    # Prefer WebM over MP4
    video_file_path = None
    if include_video and video_exists:
        video_file_path = video_webm_path if video_webm_path.exists() else video_mp4_path
    
    # Build URLs
    result = {
        'id': avatar_id,
        'type': 'system',
        'imageUrl': file_path_to_http_url(str(image_path)),
        'videoPath': file_path_to_http_url(str(video_file_path)) if video_file_path else None,
        'videoExists': video_exists
    }
    
    return result


def convert_paths_to_urls(avatar_data: Dict[str, Any], path_keys: Optional[list] = None) -> Dict[str, Any]:
    """
    Convert file paths to HTTP URLs in an avatar data dictionary.
    
    This is useful for converting data from database or other sources
    that contain file paths instead of URLs.
    
    Args:
        avatar_data: Avatar data dictionary
        path_keys: List of keys to convert (default: common path keys)
        
    Returns:
        dict: Avatar data with paths converted to URLs (modifies in place)
        
    Example:
        >>> data = {'imageUrl': '/path/to/image.png', 'name': 'Avatar'}
        >>> convert_paths_to_urls(data)
        {'imageUrl': 'http://localhost:4668/api/avatar?path=...', 'name': 'Avatar'}
    """
    if path_keys is None:
        path_keys = [
            'imageUrl', 'videoUrl', 'videoPath', 'thumbnailUrl',
            'videoMp4Path', 'videoWebmPath', 'image_path', 'video_path'
        ]
    
    for key in path_keys:
        if key in avatar_data and avatar_data[key]:
            # Only convert if it's not already an HTTP URL
            value = avatar_data[key]
            if isinstance(value, str) and not value.startswith('http'):
                avatar_data[key] = file_path_to_http_url(value)
    
    return avatar_data


def batch_convert_paths_to_urls(avatars: list[Dict[str, Any]], path_keys: Optional[list] = None) -> list[Dict[str, Any]]:
    """
    Convert file paths to HTTP URLs for a list of avatars.
    
    Args:
        avatars: List of avatar data dictionaries
        path_keys: List of keys to convert (default: common path keys)
        
    Returns:
        list: List of avatars with paths converted to URLs (modifies in place)
        
    Example:
        >>> avatars = [
        ...     {'imageUrl': '/path/1.png'},
        ...     {'imageUrl': '/path/2.png'}
        ... ]
        >>> batch_convert_paths_to_urls(avatars)
        [
            {'imageUrl': 'http://localhost:4668/api/avatar?path=...'},
            {'imageUrl': 'http://localhost:4668/api/avatar?path=...'}
        ]
    """
    for avatar in avatars:
        convert_paths_to_urls(avatar, path_keys)
    
    return avatars
