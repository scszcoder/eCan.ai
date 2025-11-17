"""
OTA Update Server
Contains test update server and configuration files
"""

from .update_server import app as update_server_app

__all__ = [
    "update_server_app"
] 