#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async preloader for MainWindow heavy dependencies
Preloads heavy libraries asynchronously without blocking UI
"""

import asyncio
import threading
import time
from typing import Dict, Any, Optional, Callable, List
from concurrent.futures import ThreadPoolExecutor
from utils.logger_helper import logger_helper as logger


class AsyncPreloader:
    """Async preloader for heavy dependencies"""
    
    def __init__(self):
        self._preload_tasks: Dict[str, asyncio.Task] = {}
        self._preload_results: Dict[str, Any] = {}
        self._preload_errors: Dict[str, Exception] = {}
        self._is_preloading = False
        self._start_time = None
        self._lock = asyncio.Lock()
        
    async def start_preload(self, wait_for_completion: bool = False) -> None:
        """
        Start async preload
        
        Args:
            wait_for_completion: If True, wait for all tasks to complete before returning
        """
        async with self._lock:
            if self._is_preloading:
                logger.info("[AsyncPreloader] Preload already in progress")
                return
                
            self._is_preloading = True
            self._start_time = time.time()
            
        logger.info("[AsyncPreloader] 🚀 Starting async preload...")
        
        # Start preload tasks
        await self._start_preload_tasks()
        
        # Monitor completion
        if wait_for_completion:
            # Wait for completion synchronously
            await self._monitor_completion()
        else:
            # Monitor completion in background
            asyncio.ensure_future(self._monitor_completion())
    
    async def _start_preload_tasks(self) -> None:
        """Start all preload tasks in parallel"""
        logger.info("[AsyncPreloader] 🚀 Starting parallel preload tasks...")
        
        # Create all tasks simultaneously for maximum parallelism
        task_definitions = [
            ('mainwindow_deps', self._preload_mainwindow_dependencies()),
            ('crypto_modules', self._preload_crypto_modules()),
            ('database_services', self._preload_database_services()),
            ('gui_tools', self._preload_gui_tools()),
        ]
        
        # Start all tasks at once
        start_time = time.time()
        for name, coro in task_definitions:
            self._preload_tasks[name] = asyncio.create_task(coro)
        
        startup_time = time.time() - start_time
        logger.info(f"[AsyncPreloader] ⚡ {len(self._preload_tasks)} parallel tasks started in {startup_time:.3f}s")
    
    async def _monitor_completion(self) -> None:
        """Monitor preload completion"""
        try:
            # Wait for all tasks to complete
            results = await asyncio.gather(*self._preload_tasks.values(), return_exceptions=True)
            
            # Process results
            for i, (name, result) in enumerate(zip(self._preload_tasks.keys(), results)):
                if isinstance(result, Exception):
                    self._preload_errors[name] = result
                    logger.warning(f"[AsyncPreloader] ❌ {name} preload failed: {result}")
                else:
                    self._preload_results[name] = result
                    logger.info(f"[AsyncPreloader] ✅ {name} preload completed: {result.get('description', 'N/A')}")
            
            total_time = time.time() - self._start_time if self._start_time else 0
            success_count = len(self._preload_results)
            total_count = len(self._preload_tasks)
            
            logger.info(f"[AsyncPreloader] 🎉 Preload completed: {success_count}/{total_count} successful, took {total_time:.2f}s")
            
        except Exception as e:
            logger.error(f"[AsyncPreloader] Monitor completion error: {e}")
        finally:
            async with self._lock:
                self._is_preloading = False
    
    async def _preload_mainwindow_dependencies(self) -> Dict[str, Any]:
        """Preload MainWindow heavy dependencies with parallel sub-tasks"""
        start_time = time.time()
        modules = []
        
        try:
            loop = asyncio.get_event_loop()
            
            # Define parallel sub-tasks
            def _load_stdlib():
                import ast, asyncio, base64, copy, glob, hashlib, importlib
                import json, math, os, platform, requests, socket, threading, time, traceback
                from datetime import datetime, timedelta
                return "Standard library heavy modules"
            
            def _load_core_utils():
                from utils.time_util import TimeUtil
                from utils.logger_helper import logger_helper
                from utils.port_allocator import get_port_allocator
                from config.envi import getECBotDataHome
                return "Core utilities"
            
            def _load_basic_models():
                try:
                    from agent.legacy.missions import EBMISSION
                    from agent.vehicles.vehicles import VEHICLE
                    from common.models import BotModel, MissionModel, VehicleModel
                    return "Basic models"
                except ImportError as e:
                    return f"Basic models (partial: {e})"
            
            # Execute sub-tasks in parallel
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="MainWindowParallel") as executor:
                tasks = [
                    loop.run_in_executor(executor, _load_stdlib),
                    loop.run_in_executor(executor, _load_core_utils),
                    loop.run_in_executor(executor, _load_basic_models),
                ]
                modules = await asyncio.gather(*tasks)
            
            load_time = time.time() - start_time
            return {
                'success': True,
                'modules': list(modules),
                'load_time': load_time,
                'description': f"MainWindow dependencies ({len(modules)} groups, parallel)"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'load_time': time.time() - start_time,
                'description': "MainWindow dependencies load failed"
            }
    
    async def _preload_crypto_modules(self) -> Dict[str, Any]:
        """Preload cryptography modules (heavy dependency)"""
        start_time = time.time()
        modules = []
        
        try:
            loop = asyncio.get_event_loop()
            
            def _load_crypto():
                nonlocal modules
                # Cryptography library imports (very heavy)
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.fernet import Fernet
                modules.append("cryptography.hazmat.primitives")
                modules.append("cryptography.fernet")
                
                return modules
            
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="CryptoPreload") as executor:
                modules = await loop.run_in_executor(executor, _load_crypto)
            
            load_time = time.time() - start_time
            return {
                'success': True,
                'modules': modules,
                'load_time': load_time,
                'description': f"Cryptography modules ({len(modules)} groups)"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'load_time': time.time() - start_time,
                'description': "Cryptography modules load failed"
            }
    
    async def _preload_database_services(self) -> Dict[str, Any]:
        """Preload database and services with parallel sub-tasks"""
        start_time = time.time()
        modules = []
        
        try:
            loop = asyncio.get_event_loop()
            
            # Define parallel sub-tasks
            def _load_database():
                from common.db_init import init_db, get_session
                return "Database initialization"
            
            def _load_services():
                from common.services import MissionService, ProductService, SkillService, BotService, VehicleService
                return "Common services"
            
            def _load_gui_managers():
                from gui.BotGUI import BotManager
                from gui.MissionGUI import MissionManager
                from gui.PlatoonGUI import PlatoonManager
                from gui.ScheduleGUI import ScheduleManager
                from gui.SkillManagerGUI import SkillManager
                from gui.TrainGUI import TrainManager, ReminderManager
                from gui.VehicleMonitorGUI import VehicleMonitorManager
                from gui.ui_settings import SettingsManager
                return "GUI Managers"
            
            # Execute sub-tasks in parallel
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="DatabaseParallel") as executor:
                tasks = [
                    loop.run_in_executor(executor, _load_database),
                    loop.run_in_executor(executor, _load_services),
                    loop.run_in_executor(executor, _load_gui_managers),
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for result in results:
                    if isinstance(result, Exception):
                        modules.append(f"Database service (failed: {result})")
                    else:
                        modules.append(result)
            
            load_time = time.time() - start_time
            return {
                'success': True,
                'modules': modules,
                'load_time': load_time,
                'description': f"Database services ({len(modules)} groups, parallel)"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'load_time': time.time() - start_time,
                'description': "Database services load failed"
            }
    
    async def _preload_gui_tools(self) -> Dict[str, Any]:
        """Preload GUI tools with maximum parallelism (most time-consuming)"""
        start_time = time.time()
        modules = []
        
        try:
            loop = asyncio.get_event_loop()
            
            # Define parallel sub-tasks for GUI tools
            def _load_main_gui_tool():
                from gui.tool.MainGUITool import FileResource, StaticResource
                return "MainGUITool"
            
            def _load_gui_encrypt():
                import gui.encrypt
                return "GUI encrypt"
            
            def _load_browser_manager():
                from gui.unified_browser_manager import get_unified_browser_manager
                return "Unified browser manager"
            
            def _load_auth_manager():
                from auth.auth_manager import AuthManager
                return "Auth manager"
            
            def _load_external_libs():
                import concurrent.futures
                from qasync import QEventLoop
                return "External libraries"
            
            # Execute all GUI tool sub-tasks in parallel
            with ThreadPoolExecutor(max_workers=5, thread_name_prefix="GUIToolsParallel") as executor:
                tasks = [
                    loop.run_in_executor(executor, _load_main_gui_tool),
                    loop.run_in_executor(executor, _load_gui_encrypt),
                    loop.run_in_executor(executor, _load_browser_manager),
                    loop.run_in_executor(executor, _load_auth_manager),
                    loop.run_in_executor(executor, _load_external_libs),
                ]
                
                # Use gather with return_exceptions to handle partial failures
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for result in results:
                    if isinstance(result, Exception):
                        modules.append(f"GUI tool (failed: {result})")
                    else:
                        modules.append(result)
            
            load_time = time.time() - start_time
            return {
                'success': True,
                'modules': modules,
                'load_time': load_time,
                'description': f"GUI tools ({len(modules)} groups, max parallel)"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'load_time': time.time() - start_time,
                'description': "GUI tools load failed"
            }
    
    async def wait_for_completion(self, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Wait for preload completion (thread-safe polling)
        
        Note: Uses polling instead of event waiting because preload runs in a separate thread
        with its own event loop, and asyncio.Event is not thread-safe across event loops.
        """
        import time
        start_time = time.time()
        poll_interval = 0.1  # Poll every 100ms
        
        try:
            while time.time() - start_time < timeout:
                # Check if preload is complete (thread-safe)
                if not self._is_preloading and len(self._preload_tasks) > 0:
                    logger.info(f"[AsyncPreloader] ✅ Preload completion detected")
                    break
                
                # Sleep asynchronously to not block the event loop
                await asyncio.sleep(poll_interval)
            else:
                # Timeout reached
                logger.warning(f"[AsyncPreloader] Wait for completion timed out after {timeout}s")
        except Exception as e:
            logger.error(f"[AsyncPreloader] Wait for completion error: {e}")
        
        return self.get_summary()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get preload summary"""
        total_tasks = len(self._preload_tasks)
        success_count = len(self._preload_results)
        error_count = len(self._preload_errors)
        total_time = time.time() - self._start_time if self._start_time else 0
        
        return {
            'total_tasks': total_tasks,
            'success_count': success_count,
            'error_count': error_count,
            'total_time': total_time,
            'is_complete': not self._is_preloading,
            'results': self._preload_results.copy(),
            'errors': {k: str(v) for k, v in self._preload_errors.items()}
        }
    
    def is_complete(self) -> bool:
        """Check if preload is complete"""
        return not self._is_preloading and len(self._preload_tasks) > 0
    
    def is_in_progress(self) -> bool:
        """Check if preload is in progress"""
        return self._is_preloading
    
    async def cleanup(self) -> None:
        """Cleanup preloader"""
        logger.info("[AsyncPreloader] Cleaning up...")
        
        # Cancel all running tasks
        for task in self._preload_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for cancellation
        if self._preload_tasks:
            await asyncio.gather(*self._preload_tasks.values(), return_exceptions=True)
        
        # Clear state
        self._preload_tasks.clear()
        self._preload_results.clear()
        self._preload_errors.clear()
        self._is_preloading = False
        
        logger.info("[AsyncPreloader] Cleanup completed")


# Global preloader instance
_global_preloader: Optional[AsyncPreloader] = None


def get_async_preloader() -> AsyncPreloader:
    """Get global async preloader instance"""
    global _global_preloader
    if _global_preloader is None:
        _global_preloader = AsyncPreloader()
    return _global_preloader


async def start_async_preload(wait_for_completion: bool = True) -> None:
    """Start async preload (convenience function)"""
    preloader = get_async_preloader()
    await preloader.start_preload(wait_for_completion=wait_for_completion)


async def wait_for_preload_completion(timeout: float = 30.0) -> Dict[str, Any]:
    """Wait for preload completion (convenience function)"""
    preloader = get_async_preloader()
    return await preloader.wait_for_completion(timeout)


def get_preload_summary() -> Dict[str, Any]:
    """Get preload summary (convenience function)"""
    preloader = get_async_preloader()
    return preloader.get_summary()


async def cleanup_async_preloader() -> None:
    """Cleanup global preloader"""
    global _global_preloader
    if _global_preloader:
        await _global_preloader.cleanup()
        _global_preloader = None
