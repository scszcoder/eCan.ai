"""
Cloud Logger - Unified logging for skill editor that works in both desktop and cloud modes.

In desktop mode: Uses IPC to send logs to the local GUI
In cloud mode: Publishes logs via AppSync for real-time streaming to the web frontend

Usage:
    from agent.cloud_worker.cloud_logger import get_skill_editor_logger
    
    logger = get_skill_editor_logger()
    logger.log("Processing node X")
    logger.warning("Something unexpected")
    logger.error("Failed to execute")
"""

import asyncio
import json
import os
import threading
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from utils.logger_helper import logger_helper as logger


@dataclass
class CloudLoggerConfig:
    """Configuration for cloud logger."""
    appsync_url: str
    appsync_api_key: str
    owner: str  # username
    session_id: str  # run_id
    flowgram_id: Optional[str] = None


# Global cloud logger config (set when running in cloud mode)
_cloud_config: Optional[CloudLoggerConfig] = None
_log_queue: Optional[Queue] = None
_log_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None


def configure_cloud_logger(
    appsync_url: str,
    appsync_api_key: str,
    owner: str,
    session_id: str,
    flowgram_id: Optional[str] = None,
) -> None:
    """
    Configure the cloud logger for AppSync publishing.
    Call this at the start of a cloud worker run.
    """
    global _cloud_config, _log_queue, _log_thread, _stop_event
    
    logger.info(f"[CloudLogger] Configuring cloud logger: owner={owner}, session_id={session_id}, flowgram_id={flowgram_id}")
    logger.info(f"[CloudLogger] AppSync URL: {appsync_url[:50]}...")
    
    _cloud_config = CloudLoggerConfig(
        appsync_url=appsync_url,
        appsync_api_key=appsync_api_key,
        owner=owner,
        session_id=session_id,
        flowgram_id=flowgram_id,
    )
    
    # Start background log publishing thread
    if _log_queue is None:
        _log_queue = Queue()
        logger.info("[CloudLogger] Created log queue")
    if _stop_event is None:
        _stop_event = threading.Event()
    
    if _log_thread is None or not _log_thread.is_alive():
        _stop_event.clear()
        _log_thread = threading.Thread(target=_log_publisher_thread, daemon=True)
        _log_thread.start()
        logger.info("[CloudLogger] Started background log publisher thread")
    else:
        logger.info("[CloudLogger] Log publisher thread already running")


def stop_cloud_logger() -> None:
    """Stop the cloud logger background thread."""
    global _stop_event, _log_thread, _cloud_config
    
    if _stop_event:
        _stop_event.set()
    if _log_thread and _log_thread.is_alive():
        _log_thread.join(timeout=2.0)
    _cloud_config = None
    logger.info("[CloudLogger] Stopped cloud logger")


def is_cloud_mode() -> bool:
    """Check if we're running in cloud mode (Fargate/Lambda)."""
    # Check for ECS metadata (Fargate) or Lambda runtime
    return (
        os.environ.get("ECS_CONTAINER_METADATA_URI_V4") is not None
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
        or os.environ.get("ECAN_CLOUD_MODE", "").lower() in ("true", "1", "yes")
        or _cloud_config is not None
    )


def _get_ipc():
    """Get IPC API instance for desktop mode."""
    try:
        from gui.ipc.api import IPCAPI
        return IPCAPI.get_instance()
    except Exception:
        return None


def _log_publisher_thread() -> None:
    """Background thread that publishes logs to AppSync."""
    global _log_queue, _stop_event, _cloud_config
    
    # Create a dedicated event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    logger.info("[CloudLogger] Log publisher thread started")
    
    while not (_stop_event and _stop_event.is_set()):
        try:
            # Get log entry from queue with timeout
            try:
                entry = _log_queue.get(timeout=0.5)
            except Empty:
                continue
            
            if entry is None:
                continue
            
            if _cloud_config is None:
                logger.warning("[CloudLogger] No cloud config, skipping log entry")
                continue
            
            # Publish to AppSync using the thread's event loop
            try:
                loop.run_until_complete(_publish_log_entry(entry))
            except Exception as e:
                logger.warning(f"[CloudLogger] Failed to publish log: {e}")
                
        except Exception as e:
            logger.warning(f"[CloudLogger] Log publisher error: {e}")
    
    loop.close()
    logger.info("[CloudLogger] Log publisher thread stopped")


async def _publish_log_entry(entry: Dict[str, Any]) -> None:
    """Publish a log entry to AppSync."""
    global _cloud_config
    
    if not _cloud_config:
        logger.warning("[CloudLogger] _publish_log_entry called but no _cloud_config")
        return
    
    try:
        from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, publish_skill_editor_stream_event
        
        config = AppSyncApiKeyConfig(
            http_endpoint=_cloud_config.appsync_url,
            api_key=_cloud_config.appsync_api_key,
        )
        
        logger.debug(f"[CloudLogger] Publishing log to owner={_cloud_config.owner}, session={_cloud_config.session_id}")
        
        await publish_skill_editor_stream_event(
            config=config,
            owner=_cloud_config.owner,
            session_id=_cloud_config.session_id,
            flowgram_id=_cloud_config.flowgram_id,
            event_type="skill_editor.log",
            payload={
                "level": entry.get("level", "log"),
                "message": entry.get("message", ""),
                "timestamp": entry.get("timestamp"),
                "node_id": entry.get("node_id"),
                "extra": entry.get("extra"),
            },
        )
        logger.debug(f"[CloudLogger] Successfully published log entry")
    except Exception as e:
        logger.warning(f"[CloudLogger] AppSync publish failed: {e}")


class SkillEditorLogger:
    """
    Unified logger for skill editor that works in both desktop and cloud modes.
    
    In desktop mode: Sends logs via IPC to the local GUI
    In cloud mode: Publishes logs via AppSync to the web frontend
    """
    
    def __init__(self, node_id: Optional[str] = None):
        """
        Initialize the logger.
        
        Args:
            node_id: Optional node ID to associate logs with a specific node
        """
        self.node_id = node_id
    
    def _send(self, level: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Send a log message."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        if is_cloud_mode():
            # Cloud mode: queue for AppSync publishing
            if _log_queue is not None:
                _log_queue.put({
                    "level": level,
                    "message": message,
                    "timestamp": timestamp,
                    "node_id": self.node_id,
                    "extra": extra,
                })
                logger.debug(f"[CloudLogger] Queued log: {message[:50]}...")
            else:
                logger.warning(f"[CloudLogger] Log queue is None, cannot send: {message[:50]}...")
        else:
            # Desktop mode: send via IPC
            ipc = _get_ipc()
            if ipc:
                try:
                    ipc.send_skill_editor_log(level, message)
                except Exception:
                    pass
        
        # Also log to standard logger for debugging
        log_fn = getattr(logger, level if level in ("debug", "info", "warning", "error") else "info")
        log_fn(f"[SkillEditor] {message}")
    
    def log(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Send a log-level message."""
        self._send("log", message, extra)
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Send an info-level message."""
        self._send("info", message, extra)
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Send a debug-level message."""
        self._send("debug", message, extra)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Send a warning-level message."""
        self._send("warning", message, extra)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Send an error-level message."""
        self._send("error", message, extra)
    
    def with_node(self, node_id: str) -> "SkillEditorLogger":
        """Create a new logger instance associated with a specific node."""
        return SkillEditorLogger(node_id=node_id)


# Global logger instance
_skill_editor_logger: Optional[SkillEditorLogger] = None


def get_skill_editor_logger(node_id: Optional[str] = None) -> SkillEditorLogger:
    """
    Get the skill editor logger instance.
    
    Args:
        node_id: Optional node ID to associate logs with a specific node
        
    Returns:
        SkillEditorLogger instance
    """
    global _skill_editor_logger
    
    if node_id:
        return SkillEditorLogger(node_id=node_id)
    
    if _skill_editor_logger is None:
        _skill_editor_logger = SkillEditorLogger()
    
    return _skill_editor_logger


def send_skill_editor_log(level: str, message: str, node_id: Optional[str] = None) -> None:
    """
    Convenience function to send a skill editor log.
    
    This is a drop-in replacement for:
        web_gui.get_ipc_api().send_skill_editor_log(level, msg)
    
    Usage:
        from agent.cloud_worker.cloud_logger import send_skill_editor_log
        send_skill_editor_log("log", "Processing node X")
        send_skill_editor_log("error", "Failed", node_id="node_123")
    """
    logger_instance = get_skill_editor_logger(node_id)
    logger_instance._send(level, message)
