"""
OTA更新服务器
包含测试更新服务器和配置文件
"""

from .update_server import app as update_server_app

__all__ = [
    "update_server_app"
] 