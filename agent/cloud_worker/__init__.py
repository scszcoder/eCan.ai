"""
Cloud Worker - Fargate-based skill execution for eCan.ai

This package provides:
- worker_main: Main entry point for cloud worker execution
- cloud_logger: Unified logging that works in both desktop and cloud modes
"""

from .cloud_logger import (
    configure_cloud_logger,
    stop_cloud_logger,
    get_skill_editor_logger,
    send_skill_editor_log,
    is_cloud_mode,
    SkillEditorLogger,
)

__all__ = [
    "configure_cloud_logger",
    "stop_cloud_logger",
    "get_skill_editor_logger",
    "send_skill_editor_log",
    "is_cloud_mode",
    "SkillEditorLogger",
]