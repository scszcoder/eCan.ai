"""
OAuth authentication module

This module provides OAuth authentication capabilities for ECBot,
including local callback server and Google OAuth Authentication Package

This package provides OAuth authentication functionality for the application.
"""

from .local_oauth_server import create_oauth_server

__all__ = [
    'LocalOAuthServer',
    'OAuthCallbackHandler', 
    'create_oauth_server'
]
