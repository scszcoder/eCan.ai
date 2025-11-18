#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OTA Download Manager - Global download state management
Manages download progress and state across the application
"""

from typing import Optional, Callable, Dict, Any
from PySide6.QtCore import QObject, Signal
from utils.logger_helper import logger_helper as logger


class DownloadState:
    """Download state enumeration"""
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadManager(QObject):
    """Global download manager - Singleton pattern"""
    
    # Signals for download state changes
    state_changed = Signal(str)  # state
    progress_updated = Signal(int, str, str)  # progress%, speed, remaining_time
    download_completed = Signal(bool, str)  # success, message
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        
        # Download state
        self.state = DownloadState.IDLE
        self.progress = 0
        self.speed = ""
        self.remaining_time = ""
        self.version = None
        self.update_info = None
        self.error_message = None
        
        # Download worker reference
        self.download_worker = None
        
        logger.info("[DownloadManager] Initialized")
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_state(self, state: str):
        """Set download state"""
        if self.state != state:
            self.state = state
            self.state_changed.emit(state)
            logger.debug(f"[DownloadManager] State changed: {state}")
    
    def update_progress(self, progress: int, speed: str = "", remaining_time: str = ""):
        """Update download progress"""
        self.progress = progress
        self.speed = speed
        self.remaining_time = remaining_time
        self.progress_updated.emit(progress, speed, remaining_time)
    
    def start_download(self, version: str, update_info: Dict[str, Any], worker):
        """Start download"""
        self.version = version
        self.update_info = update_info
        self.download_worker = worker
        self.progress = 0
        self.speed = ""
        self.remaining_time = ""
        self.error_message = None
        self.set_state(DownloadState.DOWNLOADING)
        logger.info(f"[DownloadManager] Download started: version {version}")
    
    def complete_download(self, success: bool, message: str = ""):
        """Complete download"""
        if success:
            self.set_state(DownloadState.COMPLETED)
            self.progress = 100
        else:
            self.set_state(DownloadState.FAILED)
            self.error_message = message
        
        self.download_completed.emit(success, message)
        self.download_worker = None
        logger.info(f"[DownloadManager] Download completed: success={success}")
    
    def cancel_download(self):
        """Cancel download"""
        if self.download_worker:
            self.download_worker.cancel()
            self.download_worker = None
        
        self.set_state(DownloadState.CANCELLED)
        self.progress = 0
        logger.info("[DownloadManager] Download cancelled")
    
    def reset(self):
        """Reset to idle state"""
        self.state = DownloadState.IDLE
        self.progress = 0
        self.speed = ""
        self.remaining_time = ""
        self.version = None
        self.update_info = None
        self.error_message = None
        self.download_worker = None
    
    def is_downloading(self) -> bool:
        """Check if currently downloading"""
        return self.state == DownloadState.DOWNLOADING
    
    def get_status_text(self, lang: str = "en-US") -> str:
        """Get status text for display"""
        if self.state == DownloadState.IDLE:
            return "检查更新..." if lang == "zh-CN" else "Check for Updates..."
        elif self.state == DownloadState.CHECKING:
            return "正在检查更新..." if lang == "zh-CN" else "Checking for updates..."
        elif self.state == DownloadState.DOWNLOADING:
            if self.progress > 0:
                return f"下载中... {self.progress}%" if lang == "zh-CN" else f"Downloading... {self.progress}%"
            else:
                return "准备下载..." if lang == "zh-CN" else "Preparing download..."
        elif self.state == DownloadState.VERIFYING:
            return "验证中..." if lang == "zh-CN" else "Verifying..."
        elif self.state == DownloadState.COMPLETED:
            return "下载完成" if lang == "zh-CN" else "Download complete"
        elif self.state == DownloadState.FAILED:
            return "下载失败" if lang == "zh-CN" else "Download failed"
        elif self.state == DownloadState.CANCELLED:
            return "已取消" if lang == "zh-CN" else "Cancelled"
        else:
            return "检查更新..." if lang == "zh-CN" else "Check for Updates..."


# Global instance
download_manager = DownloadManager.get_instance()
