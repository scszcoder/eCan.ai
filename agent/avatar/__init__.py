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

from .avatar_manager import AvatarManager

__all__ = ['AvatarManager']

__version__ = '1.0.0'
