#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified build logging system
Provides consistent logging across all build components
"""

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    """Log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class BuildLogger:
    """Unified build logger with component tracking"""
    
    def __init__(self, verbose: bool = False, log_file: Optional[Path] = None):
        self.verbose = verbose
        self.log_file = log_file
        self.start_time = time.time()
        self.component_times = {}
        self.error_count = 0
        self.warning_count = 0
        
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            
    def _format_message(self, level: LogLevel, component: str, message: str) -> str:
        """Format log message with timestamp and component"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"[{timestamp}] [{level.value}] [{component}] {message}"
        
    def _write_log(self, formatted_message: str) -> None:
        """Write to console and file if configured"""
        print(formatted_message)
        
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(formatted_message + '\n')
            except Exception:
                pass  # Don't fail build due to logging issues
                
    def debug(self, message: str, component: str = "BUILD") -> None:
        """Log debug message (only in verbose mode)"""
        if self.verbose:
            formatted = self._format_message(LogLevel.DEBUG, component, message)
            self._write_log(formatted)
            
    def info(self, message: str, component: str = "BUILD") -> None:
        """Log info message"""
        formatted = self._format_message(LogLevel.INFO, component, message)
        self._write_log(formatted)
        
    def warning(self, message: str, component: str = "BUILD") -> None:
        """Log warning message"""
        self.warning_count += 1
        formatted = self._format_message(LogLevel.WARNING, component, message)
        self._write_log(formatted)
        
    def error(self, message: str, component: str = "BUILD") -> None:
        """Log error message"""
        self.error_count += 1
        formatted = self._format_message(LogLevel.ERROR, component, message)
        self._write_log(formatted)
        
    def success(self, message: str, component: str = "BUILD") -> None:
        """Log success message"""
        formatted = self._format_message(LogLevel.SUCCESS, component, message)
        self._write_log(formatted)
        
    def start_component(self, component: str, description: str = "") -> None:
        """Start timing a build component"""
        self.component_times[component] = time.time()
        msg = f"Starting {component}"
        if description:
            msg += f": {description}"
        self.info(msg, component)
        
    def end_component(self, component: str, success: bool = True) -> float:
        """End timing a build component and return duration"""
        if component not in self.component_times:
            self.warning(f"Component {component} was not started", component)
            return 0.0
            
        duration = time.time() - self.component_times[component]
        status = "completed" if success else "failed"
        self.info(f"Component {component} {status} in {duration:.2f}s", component)
        
        if not success:
            self.error_count += 1
            
        return duration
        
    def log_platform_info(self, platform_handler) -> None:
        """Log platform information"""
        self.info(f"Platform: {platform_handler.platform}", "PLATFORM")
        self.info(f"Architecture: {platform_handler.architecture}", "PLATFORM")
        self.info(f"Platform ID: {platform_handler.get_platform_identifier()}", "PLATFORM")
        self.info(f"Python: {platform_handler.get_python_executable()}", "PLATFORM")
        
    def log_config_info(self, config: Dict[str, Any]) -> None:
        """Log configuration information"""
        app_info = config.get("app", {})
        self.info(f"App: {app_info.get('name', 'Unknown')} v{app_info.get('version', '0.0.0')}", "CONFIG")
        
        build_config = config.get("build", {})
        if "modes" in build_config:
            modes = list(build_config["modes"].keys())
            self.info(f"Available build modes: {', '.join(modes)}", "CONFIG")
            
    def log_macos_specific(self, message: str) -> None:
        """Log macOS-specific information"""
        self.info(message, "MACOS")
        
    def log_codesign_info(self, excluded_count: int, kept_count: int) -> None:
        """Log code signing information"""
        self.info(f"Excluded {excluded_count} binaries from codesign", "MACOS")
        self.info(f"Kept {kept_count} essential binaries", "MACOS")
        
    def log_symlink_validation(self, result: Dict[str, Any]) -> None:
        """Log symlink validation results"""
        status = result.get("status", "unknown")
        symlinks_count = len(result.get("symlinks_found", []))
        broken_count = len(result.get("broken_symlinks", []))
        
        self.info(f"Symlink validation: {status}", "SYMLINK")
        self.info(f"Found {symlinks_count} symlinks, {broken_count} broken", "SYMLINK")
        
        if broken_count > 0:
            self.warning(f"Found {broken_count} broken symlinks - may cause runtime issues", "SYMLINK")
            
        for issue in result.get("critical_issues", []):
            self.warning(issue, "SYMLINK")
            
    def print_summary(self) -> None:
        """Print build summary"""
        total_time = time.time() - self.start_time
        
        print("\n" + "="*60)
        print("BUILD SUMMARY")
        print("="*60)
        print(f"Total time: {total_time:.2f}s")
        print(f"Errors: {self.error_count}")
        print(f"Warnings: {self.warning_count}")
        
        if self.component_times:
            print("\nComponent times:")
            for component, start_time in self.component_times.items():
                # If component is still running, calculate current duration
                duration = time.time() - start_time
                print(f"  {component}: {duration:.2f}s")
                
        if self.error_count == 0:
            print("\n[SUCCESS] Build completed successfully!")
        else:
            print(f"\n[ERROR] Build completed with {self.error_count} errors")
            
        print("="*60)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get build statistics"""
        return {
            "total_time": time.time() - self.start_time,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "component_count": len(self.component_times),
            "success": self.error_count == 0
        }


# Global logger instance (will be initialized when first used)
build_logger = None

def get_build_logger(verbose: bool = False, log_file: Optional[Path] = None) -> BuildLogger:
    """Get or create the global build logger"""
    global build_logger
    if build_logger is None:
        build_logger = BuildLogger(verbose=verbose, log_file=log_file)
    return build_logger
