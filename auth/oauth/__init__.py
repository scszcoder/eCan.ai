"""
OAuth authentication module

This module provides OAuth authentication capabilities for ECBot,
including local callback server and Google OAuth Authentication Package

This package provides OAuth authentication functionality for the application.
"""

from .google_oauth_manager import GoogleOAuthManager
from .cognito_integration import CognitoGoogleIntegration
from .local_oauth_server import create_oauth_server

__all__ = [
    'GoogleOAuthManager',
    'CognitoGoogleIntegration', 
    'create_oauth_server'
]
