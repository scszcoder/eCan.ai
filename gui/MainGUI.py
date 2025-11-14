# -*- coding: utf-8 -*-
"""
MainGUI.py - eCan.ai
"""

# ============================================================================
# 1. Standard Library Imports
# ============================================================================
import ast
import asyncio
import base64
import copy
import glob
import hashlib
import importlib
import importlib.util
import json
import math
import os
import platform
import requests
import socket
import random
import shutil
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from csv import reader
from os.path import exists
from typing import List, Optional


# ============================================================================
# 2. Core Utility Imports
# ============================================================================
from utils.time_util import TimeUtil
from utils.logger_helper import logger_helper as logger
from utils.port_allocator import get_port_allocator
from config.envi import getECBotDataHome

print(TimeUtil.formatted_now_with_ms() + " load MainGui start...")

# ============================================================================
# 3. Basic Model Imports (Required for startup)
# ============================================================================
from agent.legacy.missions import EBMISSION
from agent.vehicles.vehicles import VEHICLE
from common.models import VehicleModel

print(TimeUtil.formatted_now_with_ms() + " load MainGui #0 finished...")

# ============================================================================
# 4. Network Library Imports (already included in standard library imports)
# ============================================================================

# ============================================================================
# 5. Cryptography Library Imports
# ============================================================================
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

print(TimeUtil.formatted_now_with_ms() + " load MainGui #1 finished...")

# ============================================================================
# 6. Database Related Imports
# ============================================================================
from common.db_init import init_db, get_session
from common.services import ProductService, VehicleService

# ============================================================================
# 7. GUI Manager Imports
# ============================================================================

print(TimeUtil.formatted_now_with_ms() + " load MainGui #2 finished...")

# ============================================================================
# 8. Cloud Service Imports
# ============================================================================
from agent.cloud_api.cloud_api import (set_up_cloud, upload_file, download_file,
    send_query_chat_request_to_cloud, send_report_vehicles_to_cloud, send_update_vehicles_request_to_cloud)

print(TimeUtil.formatted_now_with_ms() + " load MainGui #3 finished...")

# ============================================================================
# 9. Bot Module Imports
# ============================================================================
from agent.ec_skills.sys_utils.sys_utils import symTab, getScreenSize
from e_commerce.inventories import INVENTORY
from agent.chats.wan_chat import wanSendMessage, wanSendMessage8
from agent.network.network import myname, fieldLinks, commanderIP, commanderXport, runCommanderLAN, runPlatoonLAN
from gui.utils.system_info import get_system_info_manager, get_complete_system_info

print(TimeUtil.formatted_now_with_ms() + " load MainGui #4 finished...")

# ============================================================================
# 10. External Library Imports
# ============================================================================
import concurrent.futures
from qasync import QEventLoop

# ============================================================================
# 11. GUI Tool Imports
# ============================================================================
from gui.tool.MainGUITool import FileResource, StaticResource
from gui.encrypt import *
from gui.unified_browser_manager import get_unified_browser_manager
from auth.auth_manager import AuthManager

print(TimeUtil.formatted_now_with_ms() + " load MainGui #5 finished...")

# ============================================================================
# 12. Agent Module Imports (Most time-consuming, placed last)
# ============================================================================
from agent.db import initialize_ecan_database

print(TimeUtil.formatted_now_with_ms() + " load MainGui #6 finished...")

# ============================================================================
# 13. Global Variables and Configuration
# ============================================================================

START_TIME = 15      # 15 x 20 minute = 5 o'clock in the morning
Tzs = ["eastern", "central", "mountain", "pacific", "alaska", "hawaii"]
rpaConfig = None
ecb_data_homepath = getECBotDataHome()
in_data_string = ""

print(TimeUtil.formatted_now_with_ms() + " load MainGui finished...")


# class MainWindow(QWidget):
class MainWindow:
    def __init__(self, auth_manager: AuthManager, mainloop, ip,
                 user, homepath, machine_role, schedule_mode):
        """Initialize MainWindow with optimized non-blocking initialization"""
        self._init_start_time = time.time()
        logger.info("[MainWindow] 🚀 Starting optimized MainWindow initialization...")

        # Initialize status tracking first
        self._initialization_status = {
            'sync_init_complete': False,
            'async_init_complete': False,
            'fully_ready': False,
            'ui_ready': False,
            'critical_services_ready': False
        }
        
        # Initialize shutdown flag
        self._shutting_down = False

        # ============================================================================
        # PHASE 1: CRITICAL SYNCHRONOUS INITIALIZATION (UI-blocking, keep minimal)
        # ============================================================================
        logger.info("[MainWindow] 📋 Phase 1: Critical synchronous initialization...")

        # 1. Core system (essential for basic functionality)
        self._init_core_system(auth_manager, mainloop, ip, user, homepath, machine_role, schedule_mode)

        # 2. User & environment (lightweight)
        self._init_user_environment(user, machine_role)

        # 3. System information (lightweight)
        self._init_system_info()

        # 4. Directory & file system (essential paths)
        self._init_file_system()

        # 5. Configuration management (needed for other components)
        self._init_configuration_manager()

        # 6. Business objects initialization (lightweight data structures)
        self._init_business_objects()

        # 7. Network communication setup (lightweight)
        self._init_network_communication()

        # 8. Database initialization (essential for data persistence)
        self._init_database()

        # 9. Setup local web server
        def _ensure_no_proxy_entries(extra_hosts: list[str]):
            existing = (
                os.environ.get("NO_PROXY")
                or os.environ.get("no_proxy")
                or ""
            )
            entries = [part.strip() for part in existing.split(',') if part.strip()]
            for host in extra_hosts:
                if host not in entries:
                    entries.append(host)
            no_proxy_value = ",".join(entries)
            os.environ["NO_PROXY"] = no_proxy_value
            os.environ["no_proxy"] = no_proxy_value

        _ensure_no_proxy_entries(["localhost", "127.0.0.1"])

        from agent.mcp.server.server import set_server_main_win
        from gui.LocalServer import start_local_server_in_thread

        set_server_main_win(self)
        start_local_server_in_thread(self)

        # Mark UI as ready for display and sync init complete
        self._initialization_status['ui_ready'] = True
        self._initialization_status['sync_init_complete'] = True
        ui_ready_time = time.time() - self._init_start_time
        logger.info(f"[MainWindow] ✅ Phase 1 completed in {ui_ready_time:.2f}s - UI ready for display")
        logger.info("[MainWindow] 🎯 Synchronous initialization complete - UI can be displayed to user")

        # ============================================================================
        # PHASE 2: BACKGROUND INITIALIZATION (Non-blocking)
        # ============================================================================
        logger.info("[MainWindow] 🚀 Phase 2: Starting background initialization...")

        # Notify IPC Registry that system is ready, clear cache to ensure immediate effect
        self._initialization_status['fully_ready'] = True
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            IPCHandlerRegistry.force_system_ready(True)
        except Exception as cache_e:
            logger.warning(f"[MainWindow] Failed to update IPC registry cache: {cache_e}")

        # Start background initialization immediately
        try:
            # Try to create task in existing event loop
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_background_initialization())
            logger.info("[MainWindow] ✅ Background initialization task created successfully")
        except RuntimeError as e:
            logger.error(f"[MainWindow] ⚠️ No running event loop for background initialization: {e}")
            # Mark initialization complete directly to avoid frontend infinite waiting
            self._initialization_status['async_init_complete'] = True
            logger.info("[MainWindow] ✅ Marked async_init_complete=True due to no event loop")

        logger.info("[MainWindow] ✅ MainWindow basic initialization completed - background services starting")

    async def _update_vehicle_metrics_async(self, vehicle):
        """Asynchronously update vehicle performance metrics without blocking main thread"""
        try:
            logger.debug(f"[MainWindow] 📊 Starting async metrics update for vehicle: {vehicle.getName()}")
            
            # Delay briefly to let main thread complete initialization
            await asyncio.sleep(0.5)
            
            # Update performance metrics in background
            start_time = time.time()
            vehicle.updateSystemMetrics()
            elapsed_time = time.time() - start_time
            
            logger.info(f"[MainWindow] ✅ Updated performance metrics for vehicle: {vehicle.getName()} in {elapsed_time:.3f}s")
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to update vehicle metrics for {vehicle.getName()}: {e}")
            import traceback
            logger.debug(f"[MainWindow] Vehicle metrics error traceback: {traceback.format_exc()}")

    def _validate_and_fix_default_llm_model(self):
        """
        Validate that default_llm_model belongs to the current default_llm provider.
        If not, clear it and use the provider's default model.
        This prevents issues when switching providers.
        """
        try:
            default_llm = self.config_manager.general_settings.default_llm
            default_llm_model = self.config_manager.general_settings.default_llm_model
            
            # Use llm_manager to validate and fix
            corrected_model, was_fixed = self.config_manager.llm_manager.validate_and_fix_default_llm_model(
                default_llm, default_llm_model
            )
            
            if was_fixed:
                # Update and save the corrected model
                self.config_manager.general_settings.default_llm_model = corrected_model
                self.config_manager.general_settings.save()
        except Exception as e:
            logger.warning(f"[MainWindow] Error validating default_llm_model: {e}")

    def update_all_llms(self, reason="unknown"):
        """
        Update mainwin.llm, mainwin.browser_use_llm and all agents' LLMs (skill_llm and browser_use LLM).
        
        This method should be called when:
        - LLM provider is changed
        - Proxy settings change
        - LLM configuration is updated
        
        Args:
            reason: Description of why the LLM is being updated (for logging)
        """
        try:
            logger.info(f"[MainWindow] 🔄 Updating all LLMs - Reason: {reason}")
            from agent.ec_skills.llm_utils.llm_utils import pick_llm, pick_browser_use_llm
            
            # Recreate mainwin.llm
            # Important: Use allow_fallback=False to prevent overriding user's provider selection
            new_llm = pick_llm(
                self.config_manager.general_settings.default_llm,
                self.config_manager.llm_manager.get_all_providers(),
                self.config_manager,
                allow_fallback=False  # Don't auto-fallback when hot-updating
            )
            
            if not new_llm:
                logger.warning("[MainWindow] ⚠️ Failed to recreate LLM")
                return False
            
            old_llm_type = type(self.llm).__name__ if self.llm else "None"
            new_llm_type = type(new_llm).__name__
            self.llm = new_llm
            logger.info(f"[MainWindow] ✅ LLM recreated successfully - {old_llm_type} → {new_llm_type}")
            
            # Recreate browser_use LLM with new configuration using pick_browser_use_llm
            old_browser_llm_type = type(self.browser_use_llm).__name__ if hasattr(self, 'browser_use_llm') and self.browser_use_llm else "None"
            new_browser_use_llm = pick_browser_use_llm(mainwin=self)
            
            if new_browser_use_llm:
                self.browser_use_llm = new_browser_use_llm
                new_browser_llm_type = type(new_browser_use_llm).__name__
                logger.info(f"[MainWindow] ✅ Browser-use LLM recreated successfully - {old_browser_llm_type} → {new_browser_llm_type}")
            else:
                logger.warning("[MainWindow] ⚠️ Failed to recreate browser-use LLM")
                self.browser_use_llm = None
            
            # Update all agents' skill_llm and llm (browser_use)
            updated_agents = 0
            for agent in self.agents:
                # Update skill_llm
                if hasattr(agent, 'set_skill_llm'):
                    agent.set_skill_llm(self.llm)
                    updated_agents += 1
                    logger.debug(f"[MainWindow] Updated skill_llm for agent: {agent.card.name}")
                
                # Update agent.llm (browser_use LLM) - use unified mainwin.browser_use_llm
                if self.browser_use_llm and hasattr(agent, 'llm'):
                    agent.llm = self.browser_use_llm
                    logger.debug(f"[MainWindow] Updated browser-use LLM for agent: {agent.card.name}")
            
            logger.info(f"[MainWindow] ✅ Updated LLMs for {updated_agents} agents")
            return True
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Error updating LLMs: {e}")
            import traceback
            logger.debug(f"[MainWindow] Error traceback: {traceback.format_exc()}")
            return False
    
    def _register_proxy_change_callback(self):
        """
        Register callback with ProxyManager to recreate LLM instances when proxy state changes.
        
        This ensures that when proxy is enabled/disabled, all LLM instances will be recreated
        with the correct proxy configuration.
        """
        try:
            from agent.ec_skills.system_proxy import get_proxy_manager
            
            proxy_manager = get_proxy_manager()
            if not proxy_manager:
                logger.debug("[MainWindow] ProxyManager not available, skipping callback registration")
                return
            
            def on_proxy_change(proxies):
                """
                Callback fired when proxy state changes.
                Args:
                    proxies: None if proxy disabled, Dict if proxy enabled
                """
                if proxies:
                    proxy_info = f"HTTP: {proxies.get('http://', 'N/A')}, HTTPS: {proxies.get('https://', 'N/A')}"
                    logger.info(f"[MainWindow] 🌐 Proxy enabled - {proxy_info}")
                    reason = f"Proxy enabled - {proxy_info}"
                else:
                    logger.info("[MainWindow] 🌐 Proxy disabled - using direct connection")
                    reason = "Proxy disabled"
                
                # Use unified method to update all LLMs
                self.update_all_llms(reason=reason)
            
            # Register the callback
            unregister = proxy_manager.register_callback(on_proxy_change)
            logger.info("[MainWindow] ✅ Registered proxy change callback for LLM recreation")
            
            # Store unregister function for cleanup (if needed)
            self._proxy_callback_unregister = unregister
            
        except Exception as e:
            logger.warning(f"[MainWindow] Failed to register proxy change callback: {e}")

    def _schedule_delayed_metrics_update(self, vehicle):
        """Schedule delayed performance monitoring update, waiting for event loop availability"""
        try:
            logger.debug(f"[MainWindow] 🔄 Attempting delayed metrics update for vehicle: {vehicle.getName()}")

            # Try to get event loop again
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._update_vehicle_metrics_async(vehicle))
                logger.debug(f"[MainWindow] ✅ Successfully scheduled delayed metrics update for vehicle: {vehicle.getName()}")
            except RuntimeError as e:
                # If event loop is still not available after delay, log as warning and continue with defaults
                logger.warning(f"[MainWindow] ⚠️ Event loop still not available for delayed metrics update: {e}")
                logger.info(f"[MainWindow] 📊 Vehicle {vehicle.getName()} will continue with default metrics")

        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to schedule delayed metrics update for {vehicle.getName()}: {e}")

    async def _async_background_initialization(self):
        """
        Perform heavy initialization operations in background to avoid blocking UI
        """
        try:
            logger.info("[MainWindow] 🔄 Starting background initialization phase...")

            # Phase 2A: Database and critical services (parallel where possible)
            logger.info("[MainWindow] 📊 Initializing database and critical services...")

            # Run database initialization in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None, self._init_database_services
            )

            # Now that database services are ready, check vehicles and load data
            logger.info("[MainWindow] 🚗 Checking vehicles after database services ready...")
            await asyncio.get_event_loop().run_in_executor(
                None, self._check_vehicles_with_database
            )

            # Phase 2B: Data loading (must be after database services are ready)
            logger.info("[MainWindow] 📂 Loading local data...")
            await asyncio.get_event_loop().run_in_executor(
                None, self._init_local_data_loading
            )

            # Phase 2C: Extensions and plugins (can run in parallel)


            # Phase 2D: Server and agent initialization (heavy operations)
            logger.info("[MainWindow] 🤖 Initializing servers and agents...")
            servers_task = asyncio.get_event_loop().run_in_executor(
                None, self._init_servers_and_agents
            )

            # Wait for remaining parallel services to complete
            await servers_task

            self._initialization_status['critical_services_ready'] = True
            logger.info("[MainWindow] ✅ Critical services ready")

            # Phase 2E: Task management and async tasks
            logger.info("[MainWindow] 📋 Initializing task management...")
            await asyncio.get_event_loop().run_in_executor(
                None, self._init_task_management
            )

            # Phase 2F: Start offline sync on startup (non-blocking)
            logger.info("[MainWindow] 🔄 Starting offline sync on startup (non-blocking)...")
            asyncio.get_event_loop().run_in_executor(
                None, self._startup_sync_offline_cloud_cache
            )
            
            # Initialize async tasks
            self._init_async_tasks()

            # Phase 2F: Final background services
            logger.info("[MainWindow] 🏁 Starting final background services...")
            await self._finalize_async_initialization()

            # Mark full initialization as complete
            self._initialization_status['async_init_complete'] = True
            
            total_time = time.time() - self._init_start_time
            logger.info(f"[MainWindow] ✅ Background initialization completed successfully in {total_time:.2f}s total")

        except Exception as e:
            logger.error(f"[MainWindow] ❌ Background initialization failed: {e}")
            import traceback
            logger.error(f"[MainWindow] Background initialization error traceback:\n{traceback.format_exc()}")
            # Even if background init fails, mark as complete to prevent hanging
            self._initialization_status['async_init_complete'] = True
            logger.info("[MainWindow] ✅ Marked async_init_complete=True after background initialization failure")

    async def _finalize_async_initialization(self):
        """Finalize async initialization and start final background services"""
        logger.info("[MainWindow] 🏁 Finalizing async initialization...")

        # Save current settings
        await asyncio.get_event_loop().run_in_executor(None, self.saveSettings)

        # Now that database services are available, save vehicles that were skipped earlier
        if hasattr(self, 'vehicles') and self.vehicles and hasattr(self, 'vehicle_service') and self.vehicle_service:
            logger.info("[MainWindow] 🚗 Saving vehicles to database (deferred from sync phase)...")
            # Run vehicle saving in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(None, self._save_vehicles_to_database)

        # Log final vehicle status
        logger.info(f"[MainWindow] Final vehicle count: {len(getattr(self, 'vehicles', []))}")
        for v in getattr(self, 'vehicles', []):
            logger.debug(f"[MainWindow] Vehicle: {v.getName()}, Status: {v.getStatus()}")

        # Start cloud sync if needed (deferred from sync phase)
        if getattr(self, '_should_start_cloud_sync', False):
            logger.info("[MainWindow] 🌐 Starting deferred cloud data sync...")
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_sync_cloud_data())
            except RuntimeError:
                logger.error("[MainWindow] No running event loop for cloud sync, skipping")

        # Start final background services - wait for agents to be ready before marking fully ready
        logger.info("[MainWindow] 🚀 Starting final background services...")
        try:
            loop = asyncio.get_running_loop()
            agents_task = loop.create_task(self.async_agents_init())
            loop.create_task(self._async_setup_browser_manager())
            loop.create_task(self._async_start_lightrag())
            self.wan_sub_task = loop.create_task(self._async_start_wan_chat())
            self.llm_sub_task = loop.create_task(self._async_start_llm_subscription())
            # self.cloud_show_sub_task = loop.create_task(self._async_start_cloud_show_subscription())
            logger.info("[MainWindow] ✅ All final background service tasks created successfully")
        except RuntimeError as e:
            logger.error(f"[MainWindow] ⚠️ No running event loop for final background services: {e}")
            logger.info("[MainWindow] 📋 Skipping background services - system will work with basic functionality")
            agents_task = None

        # Wait for agents initialization to complete before marking system fully ready
        try:
            if agents_task is not None:
                logger.info("[MainWindow] ⏳ Waiting for agents initialization to complete...")
                start_time = time.time()
                await agents_task
                elapsed_time = time.time() - start_time
                logger.info(f"[MainWindow] ✅ Agents initialization completed in {elapsed_time:.3f}s")
            else:
                logger.warning("[MainWindow] ⚠️ No agents task to wait for - skipping agent initialization")
                # Give system some time to stabilize
                await asyncio.sleep(1.0)
                logger.info("[MainWindow] 📋 System stabilization delay completed")
            
            # # Now mark system as fully ready since agents are loaded
            # self._initialization_status['fully_ready'] = True

            # # Notify IPC Registry that system is ready, clear cache to ensure immediate effect
            # try:
            #     from gui.ipc.registry import IPCHandlerRegistry
            #     IPCHandlerRegistry.force_system_ready(True)
            # except Exception as cache_e:
            #     logger.warning(f"[MainWindow] Failed to update IPC registry cache: {cache_e}")


            # Notify update home agents page
            from app_context import AppContext
            web_gui = AppContext.get_web_gui()
            web_gui.get_ipc_api().update_org_agents()

            logger.info("[MainWindow] 🎉 System is now fully ready with all data loaded!")
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Agents initialization failed: {e}")
            logger.warning("[MainWindow] ⚠️ System marked as ready despite agents initialization failure")



        logger.info("[MainWindow] ✅ Async initialization finalized")

        # Check LLM provider configuration and show onboarding guide if needed
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.config_manager.llm_manager.check_and_show_onboarding())
            logger.debug("[MainWindow] 📋 Scheduled LLM provider onboarding check (non-blocking)")
        except RuntimeError as e:
            logger.debug(f"[MainWindow] No event loop for LLM provider onboarding check: {e}")

        # Register proxy state change callback to recreate LLM when proxy changes
        self._register_proxy_change_callback()

    def _save_vehicles_to_database(self):
        """Save vehicles to database (synchronous helper method for executor)"""
        try:
            for vehicle in self.vehicles:
                try:
                    self.saveVehicle(vehicle)
                    logger.debug(f"[MainWindow] Saved vehicle: {vehicle.getName()}")
                except Exception as e:
                    logger.error(f"[MainWindow] Failed to save vehicle {vehicle.getName()}: {e}")
        except Exception as e:
            logger.error(f"[MainWindow] Error in vehicle saving process: {e}")

    def _copy_example_my_skills(self):
        """
        Copy example skills from resource/my_skills to appdata/my_skills directory
        This method is synchronous and designed to be run in an executor
        """
        try:
            from config.app_info import app_info
            
            # Source directory: resource/my_skills
            source_dir = os.path.join(app_info.app_resources_path, "my_skills")
            
            # Target directory: appdata/my_skills  
            target_dir = os.path.join(app_info.appdata_path, "my_skills")
            
            # Check if source directory exists
            if not os.path.exists(source_dir):
                logger.debug(f"[MainWindow] 📂 Source my_skills directory not found: {source_dir}")
                return
            
            # Create target directory if it doesn't exist
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                logger.debug(f"[MainWindow] 📁 Created target my_skills directory: {target_dir}")
            
            # Copy each skill directory from source to target
            copied_count = 0
            updated_count = 0
            skipped_count = 0
            
            for skill_name in os.listdir(source_dir):
                source_skill_path = os.path.join(source_dir, skill_name)
                target_skill_path = os.path.join(target_dir, skill_name)
                
                # Skip if not a directory
                if not os.path.isdir(source_skill_path):
                    continue
                
                try:
                    if os.path.exists(target_skill_path):
                        # Target exists: check if files need updating
                        # Only update files if source is newer or different
                        logger.debug(f"[MainWindow] 🔍 Skill already exists, checking for updates: {skill_name}")
                        
                        files_updated = 0
                        files_skipped = 0
                        
                        # Walk through source directory and compare files
                        for root, dirs, files in os.walk(source_skill_path):
                            # Calculate relative path from source
                            rel_path = os.path.relpath(root, source_skill_path)
                            target_root = os.path.join(target_skill_path, rel_path)
                            
                            # Create target directory if it doesn't exist
                            os.makedirs(target_root, exist_ok=True)
                            
                            # Check and copy files only if source is newer or different
                            for file in files:
                                source_file = os.path.join(root, file)
                                target_file = os.path.join(target_root, file)
                                
                                try:
                                    # Check if target file exists
                                    if os.path.exists(target_file):
                                        # Compare modification times
                                        source_mtime = os.path.getmtime(source_file)
                                        target_mtime = os.path.getmtime(target_file)
                                        
                                        # Only update if source is newer
                                        if source_mtime > target_mtime:
                                            shutil.copy2(source_file, target_file)
                                            files_updated += 1
                                            logger.debug(f"[MainWindow] 📝 Updated file: {os.path.join(rel_path, file)}")
                                        else:
                                            files_skipped += 1
                                    else:
                                        # Target file doesn't exist, copy it
                                        shutil.copy2(source_file, target_file)
                                        files_updated += 1
                                        logger.debug(f"[MainWindow] 📄 Copied new file: {os.path.join(rel_path, file)}")
                                except Exception as file_error:
                                    logger.debug(f"[MainWindow] ⚠️ Failed to process file {file}: {file_error}")
                        
                        if files_updated > 0:
                            updated_count += 1
                            logger.debug(f"[MainWindow] ✅ Updated {files_updated} file(s) in skill: {skill_name}")
                        else:
                            skipped_count += 1
                            logger.debug(f"[MainWindow] ⏭️ Skill up to date, skipped: {skill_name}")
                    else:
                        # Target doesn't exist: copy entire directory
                        shutil.copytree(source_skill_path, target_skill_path)
                        logger.debug(f"[MainWindow] ✅ Copied example skill: {skill_name}")
                        copied_count += 1
                except Exception as copy_error:
                    logger.debug(f"[MainWindow] ❌ Failed to copy/update skill {skill_name}: {copy_error}")
            
            if copied_count > 0:
                logger.info(f"[MainWindow] 🎉 Successfully copied {copied_count} example skill(s) to my_skills directory")
            if updated_count > 0:
                logger.info(f"[MainWindow] 🔄 Successfully updated {updated_count} example skill(s) in my_skills directory")
            if skipped_count > 0:
                logger.debug(f"[MainWindow] 📊 Skipped {skipped_count} existing skill(s)")
            if copied_count == 0 and updated_count == 0 and skipped_count == 0:
                logger.debug(f"[MainWindow] 📂 No skills found to copy from {source_dir}")
                
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Error copying example my_skills: {e}")
            # Silently continue - this is a nice-to-have feature

    def is_ui_ready(self) -> bool:
        """Check if UI is ready for display (minimal initialization complete)"""
        return self._initialization_status.get('ui_ready', False)

    def are_critical_services_ready(self) -> bool:
        """Check if critical services are ready"""
        return self._initialization_status.get('critical_services_ready', False)

    def get_initialization_progress(self) -> dict:
        """Get detailed initialization progress information"""
        return {
            'ui_ready': self._initialization_status.get('ui_ready', False),
            'critical_services_ready': self._initialization_status.get('critical_services_ready', False),
            'async_init_complete': self._initialization_status.get('async_init_complete', False),
            'fully_ready': self._initialization_status.get('fully_ready', False),
            'sync_init_complete': self._initialization_status.get('sync_init_complete', False)
        }



    def _init_core_system(self, auth_manager, mainloop, ip, user, homepath, machine_role, schedule_mode):
        """Initialize core system components"""
        logger.info("[MainWindow] 🔧 Initializing core system components...")

        # Core references
        self.auth_manager = auth_manager
        self.mainLoop: QEventLoop = mainloop
        self.ip = ip
        self.machine_role = machine_role
        self.schedule_mode_param = schedule_mode  # Store for potential config override

        # Path normalization
        self.homepath = homepath.rstrip('/')

        # Core queues for inter-component communication
        self.gui_net_msg_queue = asyncio.Queue()
        self.gui_rpa_msg_queue = asyncio.Queue()
        self.gui_manager_msg_queue = asyncio.Queue()
        self.virtual_cloud_task_queue = asyncio.Queue()
        self.gui_monitor_msg_queue = asyncio.Queue()
        self.gui_chat_msg_queue = asyncio.Queue()
        self.wan_chat_msg_queue = asyncio.Queue()

        # Core resources
        self.tz = self.obtainTZ()
        self.file_resource = FileResource(self.homepath)
        self.static_resource = StaticResource()
        self.session = set_up_cloud()
        self.threadPoolExecutor = concurrent.futures.ThreadPoolExecutor(max_workers=16)
        
        # Port allocation for thread-safe agent port management
        self._port_allocator = get_port_allocator()

        # Machine role configuration
        if "Platoon" in self.machine_role:
            self.functions = "buyer,seller"
        elif "Commander" in self.machine_role:
            self.functions = "manager,hr,it"
        else:
            self.functions = ""

        logger.info(f"[MainWindow] ✅ Core system initialized - Role: {machine_role}, Functions: {self.functions}")

    def _init_user_environment(self, user, machine_role):
        """Initialize user environment and identity"""
        logger.info("[MainWindow] 👤 Initializing user environment...")

        self.owner = user
        # Normalize user to a safe email-like value
        self.user = user if (user and isinstance(user, str) and "@" in user) else "unknown@local"

        # Build chat_id safely
        try:
            local_part, domain_part = self.user.split("@", 1)
        except ValueError:
            local_part, domain_part = self.user, "local"

        domain_part_sanitized = domain_part.replace(".", "_")
        self.chat_id = f"{local_part}_{domain_part_sanitized}"
        self.log_user = self.chat_id

        # User-specific paths
        self.my_ecb_data_homepath = f"{ecb_data_homepath}/{self.log_user}"
        self.ecb_data_homepath = ecb_data_homepath

        # Role-specific chat ID modification
        self.host_role = machine_role
        if "Only" in self.host_role:
            self.chat_id = self.chat_id + "_Commander"
        else:
            self.chat_id = self.chat_id + "_" + "".join(self.host_role.split())

        # User ID generation
        usrparts = self.user.split("@")
        usrdomainparts = usrparts[1].split(".")
        self.uid = usrparts[0] + "_" + usrdomainparts[0]

        logger.info(f"[MainWindow] ✅ User environment initialized - Chat ID: {self.chat_id}, UID: {self.uid}")

    def _init_system_info(self):
        """Initialize system information and hardware details"""
        logger.info("[MainWindow] 💻 Initializing system information...")

        # Use system information manager to get complete information
        self.system_info_manager = get_system_info_manager()
        system_info = self.system_info_manager.get_complete_system_info()
        
        # Basic system information
        self.os_info = system_info.get('os_info', 'Unknown OS')
        self.platform = system_info.get('platform', 'unk')
        self.system = system_info.get('system', 'Unknown')
        self.architecture = system_info.get('architecture', '64bit')

        # OS short name
        if self.system == "Windows":
            self.os_short = "win"
        elif self.system == "Linux":
            self.os_short = "linux"
        elif self.system == "Darwin":
            self.os_short = "mac"
        else:
            self.os_short = "other"
        
        # Processor information
        processor_info = system_info.get('processor', {})
        self.cpuinfo = processor_info
        self.processor = processor_info.get('brand_raw', 'Unknown Processor')
        self.cpu_cores = processor_info.get('count', 1)
        self.cpu_threads = processor_info.get('threads', 1)
        self.cpu_speed = processor_info.get('hz_advertised_friendly', 'Unknown Speed')

        # Memory information
        memory_info = system_info.get('memory', {})
        self.total_memory = memory_info.get('total_gb', 0.0)
        self.virtual_memory = type('VirtualMemory', (), {
            'total': memory_info.get('total', 0),
            'available': memory_info.get('available', 0),
            'percent': memory_info.get('percent', 0.0),
            'used': memory_info.get('used', 0)
        })()

        # Screen information
        self.screen_size = getScreenSize()

        # Machine identification information - using system information manager
        # self.machine_name = system_info.get('machine_name', 'Unknown-Computer')
        # Machine identification information - prefer OS hostname (avoid friendly names)
        try:
            candidates = []
            import socket, platform, os as _os
            if self.system == "Windows":
                candidates.extend([
                    _os.environ.get("COMPUTERNAME"),
                    socket.gethostname(),
                    platform.node(),
                ])
            else:
                candidates.extend([
                    _os.environ.get("HOSTNAME"),
                    socket.gethostname(),
                    platform.node(),
                ])
            candidates.append(system_info.get('machine_name'))
            print("candidates:", candidates)
            _mn = next((x for x in candidates if isinstance(x, str) and x.strip()), None)
            if isinstance(_mn, str):
                _mn = _mn.strip().strip('"').strip("'").replace("’", "'")
                _mn = " ".join(_mn.split())
                if "." in _mn:
                    _mn = _mn.split(".", 1)[0]
            self.machine_name = _mn or "Unknown-Computer"
        except Exception:
            self.machine_name = system_info.get('machine_name', 'Unknown-Computer')

        self.device_type = system_info.get('device_type', 'Computer')
        self.system_arch = system_info.get('system_arch', 'unknown')
        self.commander_name = ""

        logger.info(f"[MainWindow] ✅ System info initialized - OS: {self.os_info}, CPU: {self.processor}, Memory: {self.total_memory:.1f}GB")
        logger.info(f"[MainWindow] ✅ Device info - Name: {self.machine_name}, Type: {self.device_type}, Arch: {self.system_arch}")
        logger.info(f"[MainWindow] ✅ System info", system_info)


    def _init_file_system(self):
        """Initialize file system directories and paths"""
        logger.info("[MainWindow] 📁 Initializing file system...")

        # Create essential directories
        resource_data_dir = f"{self.my_ecb_data_homepath}/resource/data/"
        if not os.path.exists(resource_data_dir):
            os.makedirs(resource_data_dir)

        self.temp_dir = os.path.join(self.my_ecb_data_homepath, "temp")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)
            logger.info(f"Created temp directory: {self.temp_dir}")

        self.ads_profile_dir = self.my_ecb_data_homepath + "/ads_profiles/"
        if not os.path.exists(self.ads_profile_dir):
            os.makedirs(self.ads_profile_dir)

        # File paths
        self.VEHICLES_FILE = self.my_ecb_data_homepath + "/vehicles.json"
        self.dbfile = f"{self.my_ecb_data_homepath}/resource/data/myecb.db"
        self.product_catelog_file = f"{self.my_ecb_data_homepath}/resource/data/product_catelog.json"
        self.build_dom_tree_script_path = f"{self.homepath}/resource/build_dom_tree.js"

        logger.info(f"[MainWindow] ✅ File system initialized - Data path: {self.my_ecb_data_homepath}")

    def _init_configuration_manager(self):
        """Initialize configuration management system"""
        logger.info("[MainWindow] ⚙️ Initializing configuration manager...")

        from gui.manager import ConfigManager
        self.config_manager = ConfigManager(self.my_ecb_data_homepath)

        # Set display resolution after config_manager is initialized
        display_resolution = "D"+str(self.screen_size[0])+"X"+str(self.screen_size[1])
        self.config_manager.general_settings.display_resolution = display_resolution

        # Set default webdriver path if not already configured
        if not self.config_manager.general_settings.default_webdriver_path:
            self.config_manager.general_settings.default_webdriver_path = f"{self.homepath}/chromedriver-win64/chromedriver.exe"

        self.titles = ["Director", "Product Manager", "Engineer Manager", "Team Leader", "Engineer", "Sales", "Analyst", "Senior Analyst"]
        self.ranks = ["E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "E14", "E15", "E16", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
        self.personalities = ["Introvert", "Extrovert"]

        logger.info(f"[MainWindow] ✅ Configuration manager initialized - Debug: {self.config_manager.general_settings.debug_mode}, Schedule: {self.config_manager.general_settings.schedule_mode}")

    def _init_database(self):
        """Initialize database and related services with parallel optimization"""
        logger.info("[MainWindow] 🗄️ Initializing database ...")

        # Initialize database manager and chat service
        start_time = time.time()
        
        # Initialize eCan database system
        self.ec_db_mgr = initialize_ecan_database(
            self.my_ecb_data_homepath, 
            auto_migrate=True
        )
        db_init_time = time.time() - start_time
        logger.info(f"[MainWindow] ✅ Database manager initialized with optimized pool in {db_init_time:.3f}s")
        
        # Load default template data for new users
        start_time = time.time()
        self._load_default_template_data()
        template_init_time = time.time() - start_time
        logger.info(f"[MainWindow] ✅ Default template data loaded in {template_init_time:.3f}s")

        # TODO need to remove this, use ec_db_mgr get_chat_service
        self.db_chat_service = self.ec_db_mgr.get_chat_service()

        if "Commander" in self.machine_role:
            # Initialize database for Commander role
            start_time = time.time()
            engine = init_db(self.dbfile)
            session = get_session(engine)
            db_init_time = time.time() - start_time
            logger.info(f"[MainWindow] 🗄️ ecb Database engine created in {db_init_time:.3f}s")

            # Store engine and session for service initialization
            self._db_engine = engine
            self._db_session = session

    def _init_database_services(self):
        """Initialize database and related services with parallel optimization"""
        logger.info("[MainWindow] 🗄️ Initializing database services...")

        if "Commander" in self.machine_role:
            # Initialize database for Commander role

            # Initialize services in parallel using thread pool
            start_time = time.time()
            # Define services to initialize
            services_config = [
                ('product_service', ProductService),
                ('vehicle_service', VehicleService)
            ]

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                # Submit all service initialization tasks using the generic function
                future_to_service = {
                    executor.submit(self._init_service_threaded, service_class, service_name): service_name
                    for service_name, service_class in services_config
                }

                # Wait for all services to complete
                for future in concurrent.futures.as_completed(future_to_service):
                    service_name = future_to_service[future]
                    try:
                        service_instance = future.result()
                        setattr(self, service_name, service_instance)
                        logger.debug(f"[MainWindow] ✅ {service_name} initialized successfully")
                    except Exception as e:
                        logger.error(f"[MainWindow] ❌ Failed to initialize {service_name}: {e}")
                        setattr(self, service_name, None)

            services_init_time = time.time() - start_time
            logger.info(f"[MainWindow] ✅ Database services initialized in {services_init_time:.3f}s (parallel)")

        else:
            # Platoon role - no database services needed
            self.product_service: ProductService = None
            self.vehicle_service: VehicleService = None

            logger.info("[MainWindow] ✅ Database services skipped for Platoon role")

    def _init_service_threaded(self, service_class, service_name):
        """Generic function to initialize any service in a separate thread

        Args:
            service_class: The service class to instantiate (e.g., ProductService)
            service_name: The name of the service for logging (e.g., 'product_service')

        Returns:
            service_instance: The initialized service instance
        """
        try:
            logger.debug(f"[MainWindow] Initializing {service_name} in thread...")
            service_instance = service_class(self, self._db_session, self._db_engine)
            logger.debug(f"[MainWindow] {service_name} thread initialization completed")
            return service_instance
        except Exception as e:
            logger.error(f"[MainWindow] {service_name} initialization failed: {e}")
            raise

    def _check_vehicles_with_database(self):
        """Check vehicles after database services are ready"""
        logger.info("[MainWindow] 🚗 Checking vehicles with database services...")

        # Now we can safely call checkVehicles since vehicle_service is ready
        self.checkVehicles()
        logger.info(f"[MainWindow] Vehicles checked: {len(self.vehicles)} found")
        for v in self.vehicles:
            logger.debug(f"Vehicle: {v.getName()}, Status: {v.getStatus()}")

        # All vehicles created during checkVehicles() will be automatically saved
        # because vehicle_service is now guaranteed to be available

    def _load_default_template_data(self):
        """Load default template data for new users"""
        try:
            logger.info("[MainWindow] 📋 Loading default template data...")
            
            # Load organization template data
            self._load_organization_template()
            
            # TODO: Add other template data loading here (agents, skills, tasks, etc.)
            # self._load_agent_template()
            # self._load_skill_template()
            # self._load_task_template()
            
            logger.info("[MainWindow] ✅ Default template data loading completed")
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to load default template data: {e}")
            logger.error(traceback.format_exc())

    def _load_organization_template(self):
        """Load default organization structure from template"""
        try:
            from agent.ec_org_ctrl import get_ec_org_ctrl
            
            # Get org manager (use existing database manager to avoid conflicts)
            ec_org_ctrl = get_ec_org_ctrl(self.ec_db_mgr)
            
            # Load org template using the controller
            result = ec_org_ctrl.load_org_template()
            
            if result.get("success"):
                created_count = result.get("created_count", 0)
                if created_count > 0:
                    logger.info(f"[MainWindow] ✅ Successfully loaded organization template: {result.get('message')}")
                else:
                    logger.info(f"[MainWindow] ℹ️ {result.get('message')}")
            else:
                logger.error(f"[MainWindow] ❌ Failed to load organization template: {result.get('error')}")
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to load organization template: {e}")
            logger.error(traceback.format_exc())

    def _init_business_objects(self):
        """Initialize business objects and data structures"""
        logger.info("[MainWindow] 📊 Initializing business objects...")

        # Core business objects
        self.agent_skills = []
        self.agent_tasks = []
        self.agent_tools = []
        self.agent_knowledges = []

        # Bot and mission management
        self.missions = []
        self.vehicles = []
        self.products = []
        self.inventories = []

        # Additional missing variables
        self.commanderName = ""

        # Reports and tracking
        self.todaysReport = []
        self.todaysReports = []
        self.todaysPlatoonReports = []

        # Mission and task tracking (missing variables)
        self.missionsToday = []
        self.todaysSchedule = {}
        self.todays_scheduled_task_groups = {}
        self.unassigned_scheduled_task_groups = {}
        self.unassigned_reactive_task_groups = {}


        # Component managers
        self.lightrag_server = None
        self.platoonWin = None
        self.unified_browser_manager = None

        # Bot states and profiles
        self.bot_states = ["active", "disabled", "banned", "deleted"]

        # Working state
        self.rpa_work_assigned_for_today = False
        self.running_mission = None
        self.botsFingerPrintsReady = False
        self.default_webdriver = None
        self.working_state = "running_idle"
        self.staff_officer_on_line = False

        # Utility objects
        from lzstring import LZString
        self.zipper = LZString()
        self.trMission = self.createTrialRunMission()

        # Data files
        self.sellerInventoryJsonData = None
        self.fetch_schedule_counter = 1

        logger.info("[MainWindow] ✅ Business objects initialized")

    def _init_network_communication(self):
        """Initialize network communication and related services"""
        logger.info("[MainWindow] 🌐 Initializing network communication...")

        # Network state
        self.wan_connected = False
        self.wan_msg_subscribed = False
        self.websocket = None

        # Network configuration based on role
        if "Commander" in self.machine_role:
            self.tcpServer = None
            self.commanderXport = None
            self.commander_name = self.machine_name
            self.commanderIP = ""  # Initialize for Commander role
        elif self.machine_role == "Platoon":
            self.commanderXport = None
            self.commanderIP = commanderIP
            self.tcpServer = None


        # Start network services based on role
        if "Platoon" not in self.machine_role:
            logger.info("[MainWindow] Starting commander side networking...")
            self.lan_task = self.mainLoop.create_task(runCommanderLAN(self))
        else:
            logger.info("[MainWindow] Starting platoon side networking...")
            self.lan_task = self.mainLoop.create_task(runPlatoonLAN(self, self.mainLoop))

        logger.info(f"[MainWindow] ✅ Network communication initialized - Role: {self.machine_role}")

        # Note: Vehicle checking moved to background phase after database services are ready

    def _init_local_data_loading(self):
        """Initialize and load local data"""
        logger.info("[MainWindow] 📂 Loading local data initialization...")
        
        if "Commander" in self.machine_role:
            # Load vehicle configuration
            self.readVehicleJsonFile()
            logger.info(f"[MainWindow] Vehicle files loaded: {len(getattr(self, 'vehiclesJsonData', []))} vehicles")

            # Mark that cloud sync should be started after async initialization
            if not self.config_manager.general_settings.is_debug_enabled() or self.config_manager.general_settings.is_auto_mode():
                logger.info("[MainWindow] Cloud sync will be started after async initialization...")
                self._should_start_cloud_sync = True
            else:
                logger.info("[MainWindow] Cloud sync skipped (debug mode or manual schedule)")
                self._should_start_cloud_sync = False
                
        logger.info("[MainWindow] ✅ Local data loading completed")


    def _init_task_management(self):
        """Initialize task and work management"""
        logger.info("[MainWindow] 📋 Initializing task management...")

        # Initialize work queues
        self.todays_work = {"tbd": [], "allstat": "working"}
        self.reactive_work = {"tbd": [], "allstat": "working"}
        self.todays_completed = []
        self.reactive_completed = []
        self.num_todays_task_groups = 0
        self.num_reactive_task_groups = 0

        # Setup scheduled work fetching for Commander role
        if "Commander" in self.host_role:
            fetchCloudScheduledWork = {
                "name": "fetch schedule",
                "works": self.gen_default_fetch(),
                "status": "yet to start",
                "current widx": 0,
                "completed": [],
                "aborted": []
            }

            # Add to work queue if in auto mode and not debug
            if not self.config_manager.general_settings.is_debug_enabled() and self.config_manager.general_settings.is_auto_mode():
                logger.info("[MainWindow] Adding fetch schedule to work queue")
                self.todays_work["tbd"].append(fetchCloudScheduledWork)
            else:
                logger.info(f"[MainWindow] Skipping auto schedule - Debug: {self.config_manager.general_settings.debug_mode}, Mode: {self.config_manager.general_settings.schedule_mode}")

        logger.info("[MainWindow] ✅ Task management initialized")

    def _init_servers_and_agents(self):
        """Initialize servers and agent systems"""
        logger.info("[MainWindow] 🤖 Initializing servers and agents...")


        from agent.mcp.server.tool_schemas import build_agent_mcp_tools_schemas
        from agent.ec_skills.build_node import get_default_node_schemas


        # Validate and fix default_llm_model before initializing LLM
        self._validate_and_fix_default_llm_model()
        
        # Initialize LLM with proper error handling
        try:
            from agent.ec_skills.llm_utils.llm_utils import pick_llm, pick_browser_use_llm
            self.llm = pick_llm(
                self.config_manager.general_settings.default_llm,
                self.config_manager.llm_manager.get_all_providers(),
                self.config_manager
            )
            if self.llm:
                logger.info(f"[MainWindow] ✅ LLM initialized successfully - Type: {type(self.llm).__name__}")
                # Try to get provider info from config
                default_llm = self.config_manager.general_settings.default_llm
                if default_llm:
                    provider = self.config_manager.llm_manager.get_provider(default_llm)
                    if provider:
                        model_name = provider.get('default_model', 'unknown')
                        provider_display = provider.get('display_name', default_llm)
                        logger.info(f"[MainWindow] 📋 Current LLM: Provider={provider_display}, Name={default_llm}, Model={model_name}, Class={type(self.llm).__name__}")
            else:
                logger.warning(f"[MainWindow] ⚠️ LLM initialization failed - LLM is None")
            
            # Initialize browser_use LLM (unified instance for all agents)
            self.browser_use_llm = pick_browser_use_llm(mainwin=self)
            if self.browser_use_llm:
                logger.info(f"[MainWindow] ✅ Browser-use LLM initialized successfully - Type: {type(self.browser_use_llm).__name__}")
            else:
                logger.warning(f"[MainWindow] ⚠️ Browser-use LLM initialization failed - browser_use_llm is None")
                
        except Exception as e:
            logger.error(f"[MainWindow] Failed to initialize LLM: {e}")
            self.llm = None
            self.browser_use_llm = None

        # Initialize agent-related components
        self.agents = []
        self.mcp_tools_schemas = build_agent_mcp_tools_schemas()
        self.mcp_client = None
        self._sse_cm = None
        
        # Initialize browser file system path if needed
        if not self.config_manager.general_settings.browser_use_file_system_path:
            self.config_manager.general_settings.browser_use_file_system_path = os.path.join(
                self.my_ecb_data_homepath, 'browser_use_fs'
            )
            self.config_manager.general_settings.save()

        # Load GUI flowgram schema if configured
        gui_flowgram_schema = self.config_manager.general_settings.data.get("gui_flowgram_schema", "")
        if gui_flowgram_schema:
            node_schema_file = self.my_ecb_data_homepath + gui_flowgram_schema
            if os.path.exists(node_schema_file):
                try:
                    with open(node_schema_file, 'rb') as fileTBRead:
                        self.node_schemas = json.load(fileTBRead)
                    logger.info("[MainWindow] GUI flowgram schema loaded")
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"[MainWindow] Failed to load GUI flowgram schema: {e}")
                    self.node_schemas = get_default_node_schemas()
            else:
                self.node_schemas = get_default_node_schemas()
        else:
            self.node_schemas = get_default_node_schemas()

        logger.info("[MainWindow] ✅ Servers and agents initialized")

    def _init_async_tasks(self):
        """Initialize async tasks and background services"""
        logger.info("[MainWindow] ⚡ Initializing async tasks...")

        # Setup peer communication tasks based on role
        if self.host_role != "Platoon":
            if self.host_role != "Staff Officer":
                self.peer_task = asyncio.create_task(self.servePlatoons(self.gui_net_msg_queue))
                logger.info("[MainWindow] Started platoon serving task")
            else:
                self.peer_task = asyncio.create_task(self.wait_forever())
                logger.info("[MainWindow] Started staff officer waiting task")
        else:
            self.peer_task = asyncio.create_task(self.serveCommander(self.gui_net_msg_queue))
            logger.info("[MainWindow] Started commander serving task")

        # Initialize core monitoring and communication tasks
        self.monitor_task = asyncio.create_task(self.runAgentsMonitor(self.gui_monitor_msg_queue))
        self.chat_task = asyncio.create_task(self.connectChat(self.gui_chat_msg_queue))

        # Initialize core async tasks (non-blocking)
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(self.run_async_tasks(), loop)

        logger.info("[MainWindow] ✅ Async tasks initialized")

    def is_fully_initialized(self) -> bool:
        """Check if initialization is fully completed"""
        return self._initialization_status.get('fully_ready', False)
    
    def get_main_window_safely(self):
        """
        Safely get MainWindow instance with initialization check.
        
        Returns:
            bool: True if ready, False otherwise
        """
        try:
            return self.is_fully_initialized()
        except Exception as e:
            logger.error(f"[MainGUI] Error accessing MainWindow: {e}")
            return False

    def _start_lightrag_deferred(self):
        """Start LightRAG server in deferred mode."""
        try:
            from knowledge.lightrag_server import LightragServer
            from utils.env.secure_store import secure_store
            
            # Prepare environment variables for LightRAG server
            lightrag_env = {"APP_DATA_PATH": ecb_data_homepath + "/lightrag_data"}
            
            # Ensure OPENAI_API_KEY is passed to LightRAG server from secure store with user isolation
            from utils.env.secure_store import get_current_username
            username = get_current_username()
            openai_api_key = secure_store.get('OPENAI_API_KEY', username=username)
            if openai_api_key and openai_api_key.strip():
                lightrag_env['OPENAI_API_KEY'] = openai_api_key
                logger.info("[MainWindow] 🔑 OPENAI_API_KEY found in secure store and will be passed to LightRAG server (deferred)")
            else:
                logger.warning("[MainWindow] ⚠️ OPENAI_API_KEY not found in secure store (deferred)")

            self.lightrag_server = LightragServer(extra_env=lightrag_env)
            # Start server process but don't wait for it to be ready
            self.lightrag_server.start(wait_ready=False)
            logger.info("[MainWindow] LightRAG server started (deferred, non-blocking)")
        except Exception as e:
            logger.warning(f"[MainWindow] Deferred LightRAG start failed: {e}")


    def stop_lightrag_server(self):
        self.lightrag_server.stop()
        self.lightrag_server = None

    async def _async_sync_cloud_data(self):
        """
        Asynchronously sync cloud data in background without blocking UI
        """
        try:
            logger.info("[MainWindow] 🌐 Starting background cloud data synchronization...")

            # Sync data
            logger.info("📥 Syncing data from cloud...")

            # Reload local missions after cloud sync

            # Update UI to reflect new data
            logger.info("[MainWindow] 🎉 Background cloud data synchronization completed successfully!")

        except Exception as e:
            logger.error(f"[MainWindow] ❌ Background cloud sync failed: {e}")
            logger.error(f"[MainWindow] Cloud sync error details: {traceback.format_exc()}")
            logger.error(f"[MainWindow] Cloud sync failed: {str(e)}")

    def _startup_sync_offline_cloud_cache(self):
        """
        Startup sync: sync pending cache to cloud and start auto retry timer
        
        This is a BLOCKING synchronous function that:
        1. Checks if there are pending cached tasks
        2. If yes, syncs all cached tasks to cloud (blocking)
        3. Starts auto retry timer for periodic cache sync (every 5 minutes)
        
        Note: Loading data from cloud is handled by each module separately.
        """
        try:
            logger.info("[MainWindow] 🚀 Starting startup sync (blocking)...")
            
            # Get username
            username = self.user if hasattr(self, 'user') else None
            if not username:
                logger.warning("[MainWindow] No username available, skipping startup sync")
                return
            
            # Import sync manager and queue
            from agent.cloud_api.offline_sync_manager import get_sync_manager
            from agent.cloud_api.offline_sync_queue import get_sync_queue
            
            manager = get_sync_manager()
            queue = get_sync_queue()
            
            # Step 1: Check if there are pending tasks
            stats = queue.get_stats()
            pending_count = stats['pending_count']
            failed_count = stats['failed_count']
            total_count = pending_count + failed_count
            
            if total_count > 0:
                logger.info(f"[MainWindow] 📤 Found {total_count} tasks to sync ({pending_count} pending, {failed_count} failed)")
                logger.info(f"[MainWindow] Pending by type: {stats['pending_by_type']}")
                if failed_count > 0:
                    logger.info(f"[MainWindow] Failed by type: {stats['failed_by_type']}")
                
                # Use thread for sync, fully async, doesn't block any operations
                import threading
                import time
                
                def _sync_task():
                    """Background sync task"""
                    try:
                        start_time = time.time()
                        logger.info("[MainWindow] 🔄 Starting startup sync in background (timeout: 15s per task)...")
                        
                        # Limit to max 20 tasks, 15s timeout per task, include failed tasks
                        result = manager.sync_pending_queue(max_tasks=20, timeout_per_task=15.0, include_failed=True)
                        
                        elapsed = time.time() - start_time
                        logger.info(f"[MainWindow] ✅ Startup sync completed in {elapsed:.1f}s:")
                        logger.info(f"  - Total: {result['total']}")
                        logger.info(f"  - Synced: {result['synced']}")
                        logger.info(f"  - Failed: {result['failed']}")
                        
                        if result['failed'] > 0:
                            logger.warning(f"[MainWindow] ⚠️ {result['failed']} tasks failed (timeout or error), will retry later")
                        
                        if total_count > 20:
                            logger.info(f"[MainWindow] 💡 {total_count - 20} tasks will be synced by auto-retry timer")
                            
                    except Exception as e:
                        logger.error(f"[MainWindow] ❌ Startup sync error: {e}")
                        logger.error(f"[MainWindow] Traceback: {traceback.format_exc()}")
                
                # Start background thread (fully async, no waiting)
                sync_thread = threading.Thread(target=_sync_task, daemon=True, name="StartupSync")
                sync_thread.start()
                logger.info("[MainWindow] ✅ Startup sync started in background (non-blocking)")
            else:
                logger.info("[MainWindow] ✅ No pending tasks to sync")
            
            # Step 2: Start auto retry timer (background task for periodic sync)
            # This timer will automatically sync cached data every 5 minutes
            logger.info("[MainWindow] 🔄 Starting auto retry timer for periodic cache sync...")
            manager.start_auto_retry(interval=300)  # 300 seconds
            logger.info("[MainWindow] ✅ Auto retry timer started (interval: 300s)")
                
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Startup sync error: {e}")
            logger.error(f"[MainWindow] Startup sync error details: {traceback.format_exc()}")

    async def _async_setup_browser_manager(self):
        """
        Asynchronously setup browser manager and WebDriver in background
        """
        try:
            # Wait a bit to ensure main window is responsive first
            await asyncio.sleep(1.0)

            logger.info("[MainWindow] 🌐 Starting background browser manager initialization...")

            # Run browser manager setup in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.setupUnifiedBrowserManager
            )

            # Start WebDriver initialization after browser manager is ready
            await self._start_webdriver_initialization()

            logger.info("[MainWindow] ✅ Browser manager and WebDriver initialization completed!")

        except Exception as e:
            logger.error(f"[MainWindow] ❌ Background browser setup failed: {e}")
            logger.error(f"[MainWindow] Browser setup error details: {traceback.format_exc()}")
            # Don't crash the app if browser setup fails
            # The app should continue to work without browser automation

    async def _async_start_lightrag(self):
        """
        Asynchronously start LightRAG server in background
        """
        try:
            # Wait a bit to ensure other services are ready
            await asyncio.sleep(0.5)

            logger.info("[MainWindow] 🧠 Starting LightRAG server initialization...")

            # Initialize LightRAG server in main thread to allow signal handlers
            # but run the actual server start in executor for non-blocking behavior
            from knowledge.lightrag_server import LightragServer
            from utils.env.secure_store import secure_store
            
            # Prepare environment variables for LightRAG server
            lightrag_env = {"APP_DATA_PATH": ecb_data_homepath + "/lightrag_data"}
            
            # Ensure OPENAI_API_KEY is passed to LightRAG server from secure store with user isolation
            from utils.env.secure_store import get_current_username
            username = get_current_username()
            openai_api_key = secure_store.get('OPENAI_API_KEY', username=username)
            if openai_api_key and openai_api_key.strip():
                lightrag_env['OPENAI_API_KEY'] = openai_api_key
                logger.info("[MainWindow] 🔑 OPENAI_API_KEY found in secure store and will be passed to LightRAG server")
            else:
                logger.warning("[MainWindow] ⚠️ OPENAI_API_KEY not found in secure store")
            
            self.lightrag_server = LightragServer(extra_env=lightrag_env)

            # Start the server process in executor (this is the blocking part)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.lightrag_server.start(wait_ready=False)
            )

            logger.info("[MainWindow] ✅ LightRAG server initialization completed!")

        except Exception as e:
            logger.error(f"❌ LightRAG server initialization failed: {e}")
            logger.error(f"LightRAG server error details: {traceback.format_exc()}")



    async def _async_start_wan_chat(self):
        """
        Asynchronously start wan based chat service in background
        """
        try:
            # Wait a bit to ensure other services are ready
            await asyncio.sleep(0.5)

            logger.info("[MainWindow] 🧠 Starting websocket wan chat...")

            from agent.chats.wan_chat import subscribeToWanChat
            # Start the websocket subscribe coroutine as a background task
            token = self.get_auth_token()
            # Wait for token to become available if auth flow is still initializing
            wait_loops = 0
            while not token or not isinstance(token, str) or not token.strip():
                wait_loops += 1
                if wait_loops % 10 == 1:
                    logger.info("[MainWindow] Waiting for auth token before starting WAN chat...")
                await asyncio.sleep(0.5)
                token = self.get_auth_token()

            # Kick off WAN chat in background so this method can complete
            if getattr(self, 'wan_chat_task', None) and not self.wan_chat_task.done():
                # a previous task exists; cancel and replace
                try:
                    self.wan_chat_task.cancel()
                except Exception:
                    pass
            self.wan_chat_task = asyncio.create_task(subscribeToWanChat(self, token, self.chat_id))

            # Wait up to 15 seconds for subscription to be acknowledged
            for _ in range(30):
                if getattr(self, 'get_wan_msg_subscribed', None) and self.get_wan_msg_subscribed():
                    logger.info("[MainWindow] ✅ websocket wan chat initialization completed!")
                    break
                await asyncio.sleep(0.5)
            else:
                logger.warning("[MainWindow] ⚠️ WAN chat started but subscription not confirmed within timeout")

        except Exception as e:
            logger.error(f"[MainWindow] ❌ websocket wan chat initialization failed: {e}")
            logger.error(f"[MainWindow] websocket wan chat error details: {traceback.format_exc()}")



    async def _async_start_llm_subscription(self):
        """
        Asynchronously start eCan's own cloud side LLM service subscription
        """
        from agent.cloud_api.cloud_api import subscribe_cloud_llm_task
        try:
            # Check if shutting down before starting
            if hasattr(self, '_shutting_down') and self._shutting_down:
                logger.info("System is shutting down, skipping LLM subscription")
                return
                
            # Wait a bit to ensure other services are ready
            await asyncio.sleep(0.5)

            logger.info("🧠 Starting Cloud LLM Subscription...")

            # Initialize LightRAG server in main thread to allow signal handlers
            # but run the actual server start in executor for non-blocking behavior
            ws_host = self.getWSApiHost()
            ws_endpoint = self.getWSApiEndpoint()
            token = self.get_auth_token()
            masked_token = token[:15] + "..." + token[-4:] if len(token) > 20 else "***"
            logger.info("ws_host", ws_host, "token:", masked_token if token else "", "ws_endpoint:", ws_endpoint)
            acctSiteID = self.getAcctSiteID()
            print("acct site id:", acctSiteID)
            
            # Start the server process in executor and save references for cleanup
            ws, thread = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subscribe_cloud_llm_task(acctSiteID, token, ws_endpoint)
            )
            
            # Save references for cleanup
            self.cloud_llm_ws = ws
            self.cloud_llm_thread = thread

            logger.info("✅ Cloud LLM Subscription initialization completed!")

        except Exception as e:
            logger.error(f"❌ Cloud LLM Subscription initialization failed: {e}")
            logger.error(f"Cloud LLM Subscription error details: {traceback.format_exc()}")
            # Don't crash the app if Cloud LLM Subscription fails
            # The app should continue to work without Cloud LLM Subscription

    async def _async_start_cloud_show_subscription(self):
        """
        Asynchronously start eCan's own cloud side LLM service subscription
        """
        from agent.story.story_gen import subscribe_cloud_show
        try:
            # Check if shutting down before starting
            if hasattr(self, '_shutting_down') and self._shutting_down:
                logger.info("System is shutting down, skipping Cloud Show subscription")
                return

            # Wait a bit to ensure other services are ready
            await asyncio.sleep(0.5)

            logger.info("🧠 Starting Cloud LLM Subscription...")

            # Initialize LightRAG server in main thread to allow signal handlers
            # but run the actual server start in executor for non-blocking behavior
            ws_host = self.getWSApiHost()
            ws_endpoint = self.getWSApiEndpoint()
            token = self.get_auth_token()
            masked_token = token[:15] + "..." + token[-4:] if len(token) > 20 else "***"
            logger.info("ws_host", ws_host, "token:", masked_token if token else "", "ws_endpoint:", ws_endpoint)
            acctSiteID = self.getAcctSiteID()
            print("acct site id:", acctSiteID)

            # Start the server process in executor and save references for cleanup
            ws, thread = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subscribe_cloud_show(acctSiteID, token, ws_endpoint)
            )

            # Save references for cleanup
            self.cloud_show_ws = ws
            self.cloud_show_thread = thread

            logger.info("✅ Cloud Show Subscription initialization completed!")

        except Exception as e:
            err_msg = get_traceback(e, "ErrorCloudShowSubscription")
            logger.error(f"❌ {err_msg}")
            # Don't crash the app if Cloud LLM Subscription fails
            # The app should continue to work without Cloud LLM Subscription


    def get_auth_token(self):
        """Return a valid JWT for AppSync Authorization header.
        Prefer Cognito IdToken; fall back to AccessToken. Support multiple token shapes.
        """
        try:
            tokens = self.auth_manager.get_tokens()
            if not tokens or not isinstance(tokens, dict):
                return None
            # Common flat shapes from OAuth token exchange
            for k in ('IdToken', 'id_token'):
                if k in tokens and isinstance(tokens[k], str) and tokens[k]:
                    return tokens[k]
            for k in ('AccessToken', 'access_token'):
                if k in tokens and isinstance(tokens[k], str) and tokens[k]:
                    return tokens[k]
            # Nested shape from Cognito AWSSRP / refresh
            ar = tokens.get('AuthenticationResult') if isinstance(tokens, dict) else None
            if isinstance(ar, dict):
                for k in ('IdToken', 'AccessToken'):
                    if k in ar and isinstance(ar[k], str) and ar[k]:
                        return ar[k]
            return None
        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
            return None



    async def async_agents_init(self):
        """
        Highly optimized asynchronous Agent initialization with UI non-blocking design
        """
        start_time = time.time()
        
        try:
            logger.info("[MainWindow] 🚀 Starting ultra-optimized async agents initialization...")
            local_server_port = self.get_local_server_port()
            
            # Phase 1: Instant basic setup (target: <50ms)
            logger.info("[MainWindow] ⚡ Phase 1: Instant setup...")
            phase1_start = time.time()
            
            # Initialize basic data structures instantly
            self.agent_skills = []
            self.agent_tasks = []
            self.agent_tools = []
            self.agent_knowledges = []
            
            # Non-blocking server readiness check
            await self._wait_for_server_ready(local_server_port)
            
            elapsed_phase1 = time.time() - phase1_start
            logger.info(f"[MainWindow] ✅ Phase 1 completed in {elapsed_phase1:.3f}s")
            
            # Phase 2: Aggressive parallel initialization (target: <2s)
            logger.info("[MainWindow] 🚀 Phase 2: Aggressive parallel initialization...")
            phase2_start = time.time()
            
            # Create all parallel tasks with timeout protection
            # Adjusted timeouts for slower machines
            tasks = []
            
            # 1. MCP tools with adaptive timeout based on system performance
            # Detect system performance and adjust timeout accordingly
            import psutil
            cpu_count = psutil.cpu_count()
            memory_gb = psutil.virtual_memory().total / (1024**3)
            
            # Adaptive timeout calculation
            base_timeout = 3.0
            if cpu_count >= 8 and memory_gb >= 16:
                # High-performance system
                mcp_timeout = base_timeout
            elif cpu_count >= 4 and memory_gb >= 8:
                # Medium-performance system  
                mcp_timeout = base_timeout * 1.5
            else:
                # Low-performance system
                mcp_timeout = base_timeout * 2.5
            
            logger.info(f"[MainWindow] 🎯 Adaptive MCP timeout: {mcp_timeout:.1f}s (CPU: {cpu_count}, RAM: {memory_gb:.1f}GB)")
            
            tasks.append(asyncio.wait_for(
                self._get_mcp_tools_async(), 
                timeout=mcp_timeout
            ))
            
            # 2. Placeholder for skills dependencies (simplified)
            async def prepare_skills_deps():
                await asyncio.sleep(0.01)
                return True
            tasks.append(asyncio.wait_for(prepare_skills_deps(), timeout=1.0))
            
            # 3. Placeholder for agent components (simplified)
            async def prepare_agent_components():
                await asyncio.sleep(0.01)
                return True
            tasks.append(asyncio.wait_for(prepare_agent_components(), timeout=1.0))
            
            # 4. Placeholder for background data (simplified)
            async def load_background_data():
                await asyncio.sleep(0.01)
                return True
            tasks.append(asyncio.wait_for(load_background_data(), timeout=1.0))
            
            # Execute all tasks in parallel with exception handling
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results with graceful degradation
            mcp_tools, skills_deps, agent_components, background_data = results
            
            # Handle MCP tools result
            if isinstance(mcp_tools, Exception):
                logger.warning(f"[MainWindow] ⚠️ MCP tools failed, using empty list: {mcp_tools}")
                self.mcp_tools = []
            else:
                self.mcp_tools = mcp_tools
                logger.info(f"[MainWindow] ✅ MCP tools ready: {len(self.mcp_tools)} tools")
            
            # Handle skills dependencies result
            if isinstance(skills_deps, Exception):
                logger.warning(f"[MainWindow] ⚠️ Skills dependencies failed: {skills_deps}")
            else:
                logger.info(f"[MainWindow] ✅ Skills dependencies prepared")
            
            # Handle agent components result
            if isinstance(agent_components, Exception):
                logger.warning(f"[MainWindow] ⚠️ Agent components failed: {agent_components}")
                # Continue with minimal components
            
            elapsed_phase2 = time.time() - phase2_start
            logger.info(f"[MainWindow] ✅ Phase 2 completed in {elapsed_phase2:.3f}s")
            
            # Phase 3: Streamlined agent assembly (target: <1s)
            logger.info("[MainWindow] 🎯 Phase 3: Streamlined agent assembly...")
            phase3_start = time.time()
            
            # Pipelined Agent construction and startup
            logger.info("[MainWindow] 🔧 Starting pipelined agent initialization...")
            
            # Check if required components are ready
            missing_components = []
            if not hasattr(self, 'llm') or self.llm is None:
                missing_components.append('LLM')
            if not hasattr(self, 'mcp_client'):
                missing_components.append('MCP Client')
            
            if missing_components:
                logger.warning(f"[MainWindow] ⚠️ Missing components: {missing_components}, skipping agent skills building")
                self.agent_skills = []
            else:
                logger.info(f"[MainWindow] ✅ All components ready - LLM: {type(self.llm)}, MCP Client: {self.mcp_client is not None}")

                # CRITICAL: Copy example skills BEFORE building agent skills
                # This ensures skills like search_digikey_chatter are available when agents are initialized
                logger.info("[MainWindow] 📚 Pre-copying example skills before agent initialization...")
                try:
                    await asyncio.get_event_loop().run_in_executor(None, self._copy_example_my_skills)
                    logger.info("[MainWindow] ✅ Example skills pre-copied successfully")
                except Exception as e:
                    logger.warning(f"[MainWindow] ⚠️ Pre-copy of example skills failed: {e}")
                    # Continue anyway - skills might already exist

                # Start skill building task (asynchronous)
                agent_skills_task = asyncio.create_task(self._build_agent_skills_async())
                
                # Wait for skill building to complete
                try:
                    self.agent_skills = await agent_skills_task
                    logger.info(f"[MainWindow] ✅ Agent skills built: {len(self.agent_skills)} skills")
                except Exception as e:
                    logger.warning(f"[MainWindow] ⚠️ Agent skills building failed: {e}")
                    import traceback
                    logger.error(f"[MainWindow] Skills building traceback: {traceback.format_exc()}")
                    self.agent_skills = []

                # Start agent task building (asynchronous, parallel with skills)
                logger.info("[MainWindow] 📝 Building agent tasks...")
                agent_tasks_task = asyncio.create_task(self._build_agent_tasks_async())

                # Wait for agent task building to complete
                try:
                    self.agent_tasks = await agent_tasks_task
                    logger.info(f"[MainWindow] ✅ Agent tasks built: {len(self.agent_tasks)} agent tasks")
                except Exception as e:
                    logger.warning(f"[MainWindow] ⚠️ Agent tasks building failed: {e}")
                    import traceback
                    logger.error(f"[MainWindow] Agent tasks building traceback: {traceback.format_exc()}")
                    self.agent_tasks = []

            # Environment preparation (simplified handling)
            logger.info("[MainWindow] 🔧 Environment preparation completed")
            
            # Ultra-parallel Agent construction and startup
            try:
                logger.info("[MainWindow] 🚀 Building and launching agents with ultra-parallel optimization...")
                agents_built = await self._build_and_launch_agents_ultra_parallel()
                
                if agents_built:
                    logger.info(f"[MainWindow] ✅ Successfully built and launched {len(self.agents)} agents")

                    # TODO: Merge agent.tasks from built agents into mainwin.agent_tasks, This step will be deprecated in the future
                    self._merge_agent_tasks_to_memory()
                else:
                    logger.warning("[MainWindow] ⚠️ Agent ultra-parallel process completed with issues")

            except Exception as e:
                logger.error(f"[MainWindow] ❌ Agent ultra-parallel process failed: {e}")
                agents_built = False
            
            # Mark async initialization complete
            self._initialization_status['async_init_complete'] = True
            
            elapsed_phase3 = time.time() - phase3_start
            total_elapsed = time.time() - start_time
            
            logger.info(f"[MainWindow] ✅ Phase 3 completed in {elapsed_phase3:.3f}s")
            logger.info(f"[MainWindow] 🎉 Ultra-optimized initialization completed in {total_elapsed:.3f}s!")
            
            # Simple performance reporting
            logger.info("=" * 50)
            logger.info("📊 PERFORMANCE SUMMARY")
            logger.info("=" * 50)
            logger.info(f"⏱️  Total Time: {total_elapsed:.3f}s")
            logger.info(f"📋 Phase Breakdown:")
            logger.info(f"   Phase 1 (Setup): {elapsed_phase1:.3f}s")
            logger.info(f"   Phase 2 (Parallel): {elapsed_phase2:.3f}s") 
            logger.info(f"   Phase 3 (Assembly): {elapsed_phase3:.3f}s")
            logger.info(f"💻 System: CPU={cpu_count}, RAM={memory_gb:.1f}GB")
            logger.info("=" * 50)

        except Exception as e:
            total_elapsed = time.time() - start_time
            logger.error(f"[MainWindow] ❌ Optimized agents initialization failed after {total_elapsed:.3f}s: {e}")
            
            # Provide helpful error information
            error_msg = f"Agent initialization failed: {str(e)}\n\n" \
                       f"Optimization attempted but encountered issues.\n" \
                       f"Time taken: {total_elapsed:.3f}s\n\n" \
                       f"Possible causes:\n" \
                       f"• Server connection timeout\n" \
                       f"• Resource conflicts\n" \
                       f"• Configuration errors\n\n" \
                       f"Check logs for detailed information."
            
            # Show error message (simplified)
            self.showMsg(error_msg)
            raise

    async def _wait_for_server_ready(self, local_server_port: int):
        """Ultra-fast server readiness check with intelligent backoff"""
        
        logger.info(f"[MainWindow] 🔍 Fast server check on port {local_server_port}...")
        host = "127.0.0.1"
        
        # Quick port check first (usually succeeds immediately)
        for attempt in range(5):
            try:
                # Fast socket connection test
                sock = socket.create_connection((host, local_server_port), timeout=0.5)
                sock.close()
                logger.info(f"[MainWindow] ✅ Server ready on {host}:{local_server_port} (attempt {attempt + 1})")
                return True
            except (socket.error, OSError):
                if attempt < 4:
                    await asyncio.sleep(0.1)  # Very short wait
                continue
        
        # Fallback to HTTP check if socket check fails
        try:
            import httpx
            timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)  # Increased timeouts for slower machines
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"http://{host}:{local_server_port}/healthz")
                if response.status_code == 200:
                    logger.info(f"[MainWindow] ✅ Server HTTP ready on {host}:{local_server_port}")
                    return True
        except Exception as e:
            logger.warning(f"[MainWindow] ⚠️ Server check failed: {e}")
        
        return False



    async def _get_mcp_tools_async(self):
        """Enhanced cached MCP tools retrieval with memory caching"""
        
        # Memory cache strategy
        memory_cache_timeout = 300  # 5 minutes
        if hasattr(self, '_mcp_tools_cache'):
            cache_data, cache_time = self._mcp_tools_cache
            cache_age = time.time() - cache_time
            if cache_age < memory_cache_timeout:
                logger.info(f"[MainWindow] ⚡ Using memory cached MCP tools ({len(cache_data)} tools, age: {cache_age:.1f}s)")
                return cache_data
            else:
                logger.debug(f"[MainWindow] Memory cache expired (age: {cache_age:.1f}s > {memory_cache_timeout}s)")
        
        logger.info("[MainWindow] 📋 Getting MCP tools with timeout protection...")
        
        try:
            # Try to get MCP tools directly with timeout protection
            result = await asyncio.wait_for(self._get_mcp_tools_direct(), timeout=2.0)
            
            if result and len(result) > 0:
                # Update memory cache
                current_time = time.time()
                self._mcp_tools_cache = (result, current_time)
                
                logger.info(f"[MainWindow] ✅ Got {len(result)} MCP tools")
                return result
            else:
                logger.warning("[MainWindow] ⚠️ No MCP tools returned, using empty list")
                return []
            
        except asyncio.TimeoutError:
            logger.warning("[MainWindow] ⚠️ MCP tools request timed out (2s), using empty list")
            return []
        except Exception as e:
            logger.warning(f"[MainWindow] ⚠️ MCP tools failed: {e}, using empty list")
            return []

    async def _build_agent_skills_async(self):
        """Optimized parallel agent skills building"""
        logger.info("[MainWindow] 🔧 Building agent skills in parallel...")

        try:
            # Use the async build_agent_skills function directly
            from agent.ec_skills.build_agent_skills import build_agent_skills
            skills = await build_agent_skills(self)

            logger.info(f"[MainWindow] ✅ Built {len(skills)} agent skills")
            return skills or []

        except Exception as e:
            logger.warning(f"[MainWindow] ⚠️ Agent skills building failed: {e}")
            import traceback
            logger.debug(f"[MainWindow] Skills building traceback: {traceback.format_exc()}")
            return []

    async def _build_agent_tasks_async(self):
        """Optimized parallel agent tasks building"""
        logger.info("[MainWindow] 📝 Building agent tasks in parallel...")

        try:
            # Use the async build_agent_tasks function directly
            from agent.ec_agents.create_agent_tasks import build_agent_tasks
            agent_tasks = await build_agent_tasks(self)

            logger.info(f"[MainWindow] ✅ Built {len(agent_tasks)} agent tasks")
            return agent_tasks or []

        except Exception as e:
            logger.warning(f"[MainWindow] ⚠️ Agent tasks building failed: {e}")
            import traceback
            logger.debug(f"[MainWindow] Agent tasks building traceback: {traceback.format_exc()}")
            return []

    async def _obtain_agent_tools_async(self):
        """Asynchronously obtain Agent Tools"""
        try:
            from agent.ec_agents.obtain_agent_tools import obtain_agent_tools
            logger.debug("[MainWindow] 🛠️ Obtaining agent tools...")
            tools = obtain_agent_tools(self)
            return tools
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to obtain agent tools: {e}")
            raise

    async def _build_agent_knowledges_async(self):
        """Asynchronously build Agent Knowledges"""
        try:
            from agent.ec_agents.build_agent_knowledges import build_agent_knowledges
            logger.debug("[MainWindow] 📚 Building agent knowledges...")
            knowledges = build_agent_knowledges(self)
            return knowledges
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to build agent knowledges: {e}")
            raise

    async def wait_for_server_async(self, agent, timeout: float = 5.0):
        """Asynchronously wait for Agent server startup"""
        url = agent.get_card().url+'/ping'
        start = time.time()
        
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                while time.time() - start < timeout:
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                logger.info(f"✅ {agent.get_card().name} Server is up at {url}")
                                return True
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        pass
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"[MainWindow] Error checking server {url}: {e}")
        
        logger.warning(f"[MainWindow] ⚠️ Server did not start within {timeout} seconds, continuing anyway")
        return False

    def get_free_agent_ports(self, n):
        """
        Thread-safe port allocation for agents.
        Uses the global port allocator to prevent race conditions during parallel agent launch.
        """
        try:
            # Get currently used ports from existing agents
            used_ports = [ag.get_a2a_server_port() for ag in self.agents if ag is not None and hasattr(ag, 'get_a2a_server_port')]
            
            # Get port range from configuration
            local_agent_ports = self.config_manager.general_settings.local_agent_ports
                        
            # Use thread-safe allocator
            free_ports = self._port_allocator.get_free_ports(n, local_agent_ports, used_ports)
            
            logger.info(f"[MainWindow] Allocated ports: {free_ports}")
            return free_ports
            
        except Exception as e:
            logger.error(f"[MainWindow] Port allocation failed: {e}")
            # Fallback to original method if allocator fails
            used_ports = [ag.get_a2a_server_port() for ag in self.agents if ag is not None]
            local_agent_ports = self.config_manager.general_settings.local_agent_ports
            all_ports = range(local_agent_ports[0], local_agent_ports[1]+1)
            free_ports = [port for port in all_ports if port not in used_ports]
            
            if len(free_ports) < n:
                raise RuntimeError(f"[MainWindow] Only {len(free_ports)} free ports available, but {n} requested.")
            
            return free_ports[:n]


    def release_agent_port(self, port):
        """
        Release a port back to the allocator when an agent shuts down.
        """
        try:
            self._port_allocator.release_port(port)
            logger.info(f"[MainWindow] Released agent port: {port}")
        except Exception as e:
            logger.warning(f"[MainWindow] Failed to release port {port}: {e}")

    def release_agent_ports(self, ports):
        """
        Release multiple ports back to the allocator.
        """
        try:
            self._port_allocator.release_ports(ports)
            logger.info(f"[MainWindow] Released agent ports: {ports}")
        except Exception as e:
            logger.warning(f"[MainWindow] Failed to release ports {ports}: {e}")


    def save_agent_skill(self, skill):
        from agent.ec_skills.save_agent_skills import save_agent_skills
        return save_agent_skills(self, [skill])


    async def _get_mcp_tools_direct(self):
        """Direct MCP tools retrieval using original method"""
        try:
            from agent.mcp.local_client import mcp_client_manager
            from agent.mcp.config import mcp_http_base
            
            url = mcp_http_base()
            tl_result = await mcp_client_manager.list_tools(url)

            # Handle ListToolsResult object
            if hasattr(tl_result, 'tools'):
                tl = tl_result.tools
                logger.debug(f"✅ Successfully listed {len(tl)} MCP tools")
            elif isinstance(tl_result, list):
                tl = tl_result
                logger.debug(f"✅ Successfully listed {len(tl)} MCP tools")
            else:
                logger.warning(f"Unexpected tools result type: {type(tl_result)}")
                tl = []

            return tl or []
        except Exception as e:
            logger.debug(f"[MainWindow] Direct MCP tools failed: {e}")
            return []

    async def _build_and_launch_agents_ultra_parallel(self):
        """
        Ultra-parallel agent build and launch
        
        Integrates agents from three sources in parallel:
        1. Code-built agents (from builder functions)
        2. Local database agents (user-created via UI)
        3. Cloud agents (synced from cloud API)
        
        Returns:
            bool: True if agents were successfully built and initialized
        """
        try:
            logger.info("[MainWindow] 🚀 Starting ultra-parallel agent build and launch...")
            start_time = time.time()
            
            # Initialize agents list
            self.agents = []
            
            # Step 1: Parallel execution of THREE tasks
            logger.info("[MainWindow] 🔧 Starting 3-way parallel execution:")
            logger.info("[MainWindow]    1️⃣ Building code-built agents")
            logger.info("[MainWindow]    2️⃣ Loading local database agents")
            logger.info("[MainWindow]    3️⃣ Fetching cloud agents")
            
            built_agents, local_db_agents, cloud_agents = await asyncio.gather(
                self._build_code_agents_async(),
                self._load_local_db_agents(),
                self._fetch_cloud_agents(),
                return_exceptions=True
            )
            
            # Handle exceptions from parallel tasks
            if isinstance(built_agents, Exception):
                logger.error(f"[MainWindow] ❌ Failed to build code agents: {built_agents}")
                built_agents = []
            if isinstance(local_db_agents, Exception):
                logger.error(f"[MainWindow] ❌ Failed to load local DB agents: {local_db_agents}")
                local_db_agents = []
            if isinstance(cloud_agents, Exception):
                logger.error(f"[MainWindow] ❌ Failed to fetch cloud agents: {cloud_agents}")
                cloud_agents = []
            
            logger.info(f"[MainWindow] 📊 Parallel loading completed:")
            logger.info(f"[MainWindow]    - Code-built: {len(built_agents)}, DB: {len(local_db_agents)}, Cloud: {len(cloud_agents)}")
            
            # Step 2: Merge and deduplicate agents from all sources
            logger.info("[MainWindow] 🔀 Merging agents from all sources...")
            
            # Merge local DB and cloud agents (cloud overwrites local)
            merged_db_cloud = self._merge_agent_data(local_db_agents, cloud_agents)
            logger.info(f"[MainWindow] 📊 DB + Cloud merged: {len(merged_db_cloud)} agents")
            
            # Update local database with merged data
            await self._update_local_db_agents(merged_db_cloud)
            
            # Merge code-built agents with DB/Cloud agents (Priority: Code-built > Cloud > Local DB)
            self.agents = self._merge_all_agent_sources(
                code_built_agents=built_agents,
                db_cloud_agents=merged_db_cloud
            )
            
            logger.info(f"[MainWindow] ✅ Merged {len(self.agents)} unique agents")
            
            if len(self.agents) == 0:
                logger.error("[MainWindow] ❌ No agents available after merge")
                return False
            
            # Step 3: Verify all agents are EC_Agent objects (already converted in _merge_all_agent_sources)
            dict_count = sum(1 for a in self.agents if isinstance(a, dict))
            ec_agent_count = len(self.agents) - dict_count
            
            if dict_count > 0:
                logger.warning(f"[MainWindow] ⚠️ Found {dict_count} unconverted dict agents (expected 0)")
            
            logger.info(f"[MainWindow] ✅ Final agent list: {ec_agent_count} EC_Agent objects")
            
            # Log detailed agent and skill information before launch
            logger.info("[AGENT_INVENTORY] ========== Agent Skills Inventory ==========")
            for idx, agent in enumerate(self.agents):
                try:
                    agent_name = agent.get_card().name if hasattr(agent, 'get_card') and agent.get_card() else f"Agent_{idx}"
                    logger.info(f"[AGENT_INVENTORY] Agent {idx}: {agent_name}")
                    
                    if hasattr(agent, 'skills'):
                        skills_count = len(agent.skills) if agent.skills else 0
                        logger.info(f"[AGENT_INVENTORY]   - Skills count: {skills_count}")
                        
                        if skills_count > 0:
                            for skill_idx, skill in enumerate(agent.skills):
                                if skill is None:
                                    logger.error(f"[AGENT_INVENTORY]   - Skill[{skill_idx}]: None (MISSING!)")
                                else:
                                    skill_name = skill.name if hasattr(skill, 'name') else f"Skill_{skill_idx}"
                                    has_runnable = hasattr(skill, 'runnable') and skill.runnable is not None
                                    logger.info(f"[AGENT_INVENTORY]   - Skill[{skill_idx}]: {skill_name}, has_runnable: {has_runnable}")
                                    if not has_runnable:
                                        logger.error(f"[AGENT_INVENTORY]     ⚠️ Skill '{skill_name}' has no runnable!")
                        else:
                            logger.warning(f"[AGENT_INVENTORY]   - No skills assigned")
                    else:
                        logger.warning(f"[AGENT_INVENTORY]   - No 'skills' attribute")
                except Exception as e:
                    logger.error(f"[AGENT_INVENTORY] Error inspecting agent {idx}: {e}")
            logger.info("[AGENT_INVENTORY] =============================================")
            
            # Step 4: Launch agents in background (non-blocking)
            self._launch_agents_async(self.agents)
            
            total_time = time.time() - start_time
            logger.info(f"[MainWindow] 🎉 Ultra-parallel process completed in {total_time:.3f}s")
            logger.info(f"[MainWindow]    - {len(self.agents)} agents ready, launches running in background")
            
            return len(self.agents) > 0
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Ultra-parallel process failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _build_code_agents_async(self):
        """Build all code-built agents in parallel
        
        Returns:
            List of successfully built (agent_name, agent) tuples
        """
        try:
            # Import agent builder functions
            from agent.ec_agents.my_twin_agent import set_up_my_twin_agent
            from agent.ec_agents.ec_helper_agent import set_up_ec_helper_agent
            from agent.ec_agents.ec_rpa_operator_agent import set_up_ec_rpa_operator_agent
            from agent.ec_agents.ec_tester_agent import set_up_ec_tester_agent
            from agent.ec_agents.ec_procurement_agent import set_up_ec_procurement_agent
            
            # Define agent configurations based on role
            agent_configs = []
            
            # Basic Agent (always needed)
            agent_configs.append({
                'name': 'My Twin',
                'builder': set_up_my_twin_agent
            })
            
            # Add other agents based on role
            if "Platoon" in self.machine_role:
                agent_configs.extend([
                    {'name': 'Helper', 'builder': set_up_ec_helper_agent},
                    {'name': 'RPA Operator', 'builder': set_up_ec_rpa_operator_agent},
                    {'name': 'Tester', 'builder': set_up_ec_tester_agent}
                ])
            else:
                agent_configs.append({
                    'name': 'Helper',
                    'builder': set_up_ec_helper_agent
                })
                
                if "ONLY" not in self.machine_role:
                    agent_configs.extend([
                        {'name': 'Procurement', 'builder': set_up_ec_procurement_agent},
                        {'name': 'Tester', 'builder': set_up_ec_tester_agent}
                    ])
            
            logger.info(f"[MainWindow] 📋 Building {len(agent_configs)} code-built agents in parallel")
            
            # Build all agents in parallel
            async def build_single(config):
                try:
                    loop = asyncio.get_event_loop()
                    agent = await loop.run_in_executor(None, config['builder'], self)
                    return (config['name'], agent) if agent else None
                except Exception as e:
                    logger.error(f"[MainWindow] ❌ Failed to build {config['name']}: {e}")
                    return None
            
            build_tasks = [build_single(config) for config in agent_configs]
            results = await asyncio.gather(*build_tasks, return_exceptions=True)
            
            # Filter successful builds
            built_agents = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"[MainWindow] ❌ Failed to build {agent_configs[i]['name']}: {result}")
                elif result and result[1]:
                    built_agents.append(result)
                    logger.info(f"[MainWindow] ✅ Built {result[0]} agent ({len(built_agents)}/{len(agent_configs)})")
                else:
                    logger.warning(f"[MainWindow] ⚠️ {agent_configs[i]['name']} build returned None")
            
            logger.info(f"[MainWindow] 🎉 Code-built agents completed: {len(built_agents)}/{len(agent_configs)}")
            return built_agents
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to build code agents: {e}")
            return []

    def _launch_agents_async(self, agents_list):
        """Launch agents in background without blocking
        
        Creates a background task to launch all agents in parallel.
        This method returns immediately without waiting for launches to complete.
        
        Args:
            agents_list: List of EC_Agent objects to launch
        """
        async def launch_all_async():
            """Internal async function to launch all agents"""
            launchable_agents = [
                (f"Agent_{i}", agent) for i, agent in enumerate(agents_list)
                if hasattr(agent, 'launch') or hasattr(agent, 'start')
            ]
            
            if not launchable_agents:
                logger.info("[MainWindow] 🔍 No launchable agents found")
                return
            
            logger.info(f"[MainWindow] 🚀 Launching {len(launchable_agents)} agents in background (fire-and-forget)...")
            
            # Launch all agents in parallel using existing method
            launch_tasks = [
                self._launch_single_agent_with_name_async(name, agent)
                for name, agent in launchable_agents
            ]
            results = await asyncio.gather(*launch_tasks, return_exceptions=True)
            
            # Count results
            launched_count = sum(1 for r in results if r is True)
            logger.info(f"[MainWindow] 🎉 Background launch completed: {launched_count}/{len(launchable_agents)} agents launched")
        
        # Create task and run in background (fire-and-forget)
        asyncio.create_task(launch_all_async())
        logger.info(f"[MainWindow] 🔥 Agent launch task created (running in background)")
    
    async def _launch_single_agent_with_name_async(self, agent_name: str, agent):
        """Asynchronously launch a single Agent (returns launch result)"""
        try:
            # Log comprehensive agent and skill information
            agent_card_name = agent.get_card().name if hasattr(agent, 'get_card') and agent.get_card() else agent_name
            logger.info(f"[AGENT_LAUNCH] Starting launch for agent: {agent_card_name}")
            
            # Check and log agent skills
            if hasattr(agent, 'skills'):
                skills_count = len(agent.skills) if agent.skills else 0
                logger.info(f"[AGENT_SKILLS] Agent '{agent_card_name}' has {skills_count} skills")
                
                if skills_count > 0:
                    for idx, skill in enumerate(agent.skills):
                        if skill is None:
                            logger.error(f"[SKILL_MISSING] Agent '{agent_card_name}' skill[{idx}] is None!")
                        else:
                            skill_name = skill.name if hasattr(skill, 'name') else f"Skill_{idx}"
                            has_runnable = hasattr(skill, 'runnable') and skill.runnable is not None
                            runnable_type = type(skill.runnable).__name__ if has_runnable else "None"
                            logger.info(f"[SKILL_CHECK] Agent '{agent_card_name}' skill[{idx}]: {skill_name}, runnable: {runnable_type}")
                            
                            if not has_runnable:
                                logger.error(f"[SKILL_MISSING] Agent '{agent_card_name}' skill '{skill_name}' has runnable=None!")
                else:
                    logger.warning(f"[AGENT_SKILLS] Agent '{agent_card_name}' has no skills!")
            else:
                logger.warning(f"[AGENT_SKILLS] Agent '{agent_card_name}' has no 'skills' attribute")
            
            # Check if Agent has a launch method
            if hasattr(agent, 'launch') and callable(agent.launch):
                # Execute launch in thread pool (avoid blocking)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, agent.launch)
                # Wait for server to be ready
                await self.wait_for_server_async(agent, timeout=10.0)
                return True
            elif hasattr(agent, 'start') and callable(agent.start):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, agent.start)
                
                # 🔧 Critical fix: Wait for A2A Server to be fully ready before returning
                # Agent.start() launches Uvicorn in a thread but doesn't wait for it to be ready
                # We must explicitly wait for the server's /ping endpoint to respond
                logger.info(f"[MainWindow] 🔍 Waiting for {agent.get_card().name}'s A2A server to be ready...")
                server_ready = await self.wait_for_server_async(agent, timeout=15.0)
                
                if server_ready:
                    logger.info(f"[MainWindow] ✅ {agent.get_card().name}'s A2A server is ready")
                    return True
                else:
                    logger.error(f"[MainWindow] ❌ {agent.get_card().name}'s A2A server failed to start within 10s")
                    return False
            else:
                # If no specific launch method, try waiting for server readiness
                if hasattr(agent, 'get_card') and agent.get_card():
                    await self.wait_for_server_async(agent, timeout=3.0)
                    return True
                else:
                    logger.warning(f"[MainWindow] ⚠️ {agent.get_card().name} has no launch method or server card")
                    return False
                    
        except Exception as e:
            import traceback
            agent_name = "Unknown"
            try:
                agent_name = agent.get_card().name if hasattr(agent, 'get_card') else str(agent)
            except:
                pass
            logger.error(f"[MainWindow] ❌ Failed to launch {agent_name}: {e}")
            logger.error(f"[MainWindow] Traceback: {traceback.format_exc()}")
            return False

    async def _load_local_db_agents(self):
        """
        Load agents from local database using agent service
        Returns: List of agent dicts
        """
        try:
            logger.info("[MainWindow] 📂 Loading agents from local database...")
            logger.info(f"[MainWindow] 📂 Current user (original): {self.user}")
            logger.info(f"[MainWindow] 📂 Current user (sanitized): {self.log_user}")
            
            if not self.ec_db_mgr or not self.ec_db_mgr.agent_service:
                logger.warning("[MainWindow] ⚠️  Agent service not available")
                return []
            
            agent_service = self.ec_db_mgr.agent_service
            logger.info(f"[MainWindow] 📂 Agent service available: {agent_service}")
            
            # Use agent service method to load agents (run in executor to avoid blocking)
            # IMPORTANT: Use self.user (original email) not self.log_user (sanitized for filesystem)
            def load_from_service():
                logger.info(f"[MainWindow] 📂 Querying agents for owner: {self.user}")
                result = agent_service.get_agents_by_owner(self.user)
                logger.info(f"[MainWindow] 📂 Query result: success={result.get('success')}, data_count={len(result.get('data', []))}")
                if result.get("success"):
                    agents_data = result.get("data", [])
                    logger.info(f"[MainWindow] 📂 Found {len(agents_data)} agents in database")
                    return agents_data
                else:
                    logger.error(f"[MainWindow] ❌ Agent service query failed: {result.get('error')}")
                    return []
            
            agents = await asyncio.get_event_loop().run_in_executor(None, load_from_service)
            logger.info(f"[MainWindow] ✅ Loaded {len(agents)} agents from local database")
            return agents
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to load local DB agents: {e}")
            return []
    
    def _merge_agent_tasks_to_memory(self):
        """
        Merge agent.tasks from built agents into mainwin.agent_tasks
        
        This method consolidates tasks from all agents into the main window's task list,
        with deduplication by task ID and name.
        
        Returns:
            tuple: (merged_count, skipped_count, total_count)
        """
        try:
            logger.info("[MainWindow] 📝 Merging agent.tasks from built agents...")
            merged_count = 0
            skipped_count = 0

            # Build a set of existing task identifiers for fast lookup
            existing_task_ids = set()
            existing_task_names = set()
            for existing_task in self.agent_tasks:
                task_id = getattr(existing_task, 'id', None)
                task_name = getattr(existing_task, 'name', None)
                if task_id:
                    existing_task_ids.add(task_id)
                if task_name:
                    existing_task_names.add(task_name)

            logger.debug(f"[MainWindow] Existing tasks: {len(existing_task_ids)} with IDs, {len(existing_task_names)} with names")

            # Merge agent tasks with deduplication
            for agent in self.agents:
                if hasattr(agent, 'tasks') and agent.tasks:
                    agent_name = getattr(agent, 'name', 'Unknown')
                    logger.debug(f"[MainWindow] Processing {len(agent.tasks)} tasks from agent: {agent_name}")

                    for agent_task in agent.tasks:
                        task_id = getattr(agent_task, 'id', None)
                        task_name = getattr(agent_task, 'name', None)

                        # Check for duplicates by ID (primary) or name (fallback)
                        is_duplicate = False
                        if task_id and task_id in existing_task_ids:
                            is_duplicate = True
                            logger.debug(f"[MainWindow] Skipping duplicate task by ID: {task_id}")
                        elif task_name and task_name in existing_task_names:
                            is_duplicate = True
                            logger.debug(f"[MainWindow] Skipping duplicate task by name: {task_name}")

                        if not is_duplicate:
                            # Add to memory
                            self.agent_tasks.append(agent_task)

                            # Update tracking sets
                            if task_id:
                                existing_task_ids.add(task_id)
                            if task_name:
                                existing_task_names.add(task_name)

                            merged_count += 1
                            logger.debug(f"[MainWindow] Merged task: {task_name or task_id}")
                        else:
                            skipped_count += 1

            total_count = len(self.agent_tasks)
            logger.info(f"[MainWindow] ✅ Merged {merged_count} agent tasks from built agents")
            logger.info(f"[MainWindow] ⏭️  Skipped {skipped_count} duplicate agent tasks")
            logger.info(f"[MainWindow] 📊 Total agent tasks in memory: {total_count}")
            
            return merged_count, skipped_count, total_count
            
        except Exception as e:
            logger.warning(f"[MainWindow] ⚠️ Failed to merge agent.tasks: {e}")
            import traceback
            logger.debug(f"[MainWindow] Merge error traceback: {traceback.format_exc()}")
            return 0, 0, len(self.agent_tasks)
    
    async def _fetch_cloud_agents(self):
        """
        Fetch agents from cloud API
        Returns: List of agent dicts
        """
        try:
            logger.info("[MainWindow] 🌐 Fetching agents from cloud...")
            
            # Use load_agents_from_cloud to fetch agents from cloud
            from agent.ec_agents.agent_utils import load_agents_from_cloud
            
            # Run in executor to avoid blocking the event loop
            # Note: load_agents_from_cloud returns EC_Agent objects, not dicts
            cloud_agent_objects = await asyncio.get_event_loop().run_in_executor(
                None,
                load_agents_from_cloud,
                self
            )
            
            if not cloud_agent_objects:
                logger.info("[MainWindow] ℹ️  No agents returned from cloud")
                return []
            
            logger.info(f"[MainWindow] ✅ Fetched {len(cloud_agent_objects)} agents from cloud")
            
            # Convert EC_Agent objects to dicts for merging
            cloud_agent_dicts = []
            for agent_obj in cloud_agent_objects:
                try:
                    if hasattr(agent_obj, 'to_dict'):
                        agent_dict = agent_obj.to_dict(owner=self.user)
                    elif hasattr(agent_obj, 'card'):
                        # Extract basic info from agent card
                        agent_dict = {
                            'id': agent_obj.card.id if hasattr(agent_obj.card, 'id') else None,
                            'name': agent_obj.card.name if hasattr(agent_obj.card, 'name') else 'Unknown',
                            'description': agent_obj.card.description if hasattr(agent_obj.card, 'description') else '',
                            'owner': getattr(agent_obj, 'owner', 'unknown'),
                        }
                    else:
                        logger.warning(f"[MainWindow] Cannot convert agent object to dict: {agent_obj}")
                        continue
                    
                    cloud_agent_dicts.append(agent_dict)
                except Exception as e:
                    logger.warning(f"[MainWindow] Failed to convert agent to dict: {e}")
                    continue
            
            logger.info(f"[MainWindow] 🔄 Converted {len(cloud_agent_dicts)} cloud agents to dicts")
            return cloud_agent_dicts
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to fetch cloud agents: {e}")
            logger.error(f"[MainWindow] Traceback: {traceback.format_exc()}")
            return []
    
    def _merge_agent_data(self, local_agents, cloud_agents):
        """
        Merge local and cloud agent data
        Cloud data overwrites local data by agent ID
        
        Args:
            local_agents: List of agent dicts from local database
            cloud_agents: List of agent dicts from cloud API
        
        Returns:
            List of merged agent dicts
        """
        try:
            logger.info("[MainWindow] 🔀 Merging local and cloud agent data...")
            
            # Create a dict with local agents keyed by ID
            merged_dict = {agent.get('id'): agent for agent in local_agents}
            
            # Overwrite with cloud agents (cloud data takes precedence)
            for cloud_agent in cloud_agents:
                agent_id = cloud_agent.get('id')
                if agent_id:
                    merged_dict[agent_id] = cloud_agent
                    logger.debug(f"[MainWindow] 🔄 Cloud agent overwrites local: {agent_id}")
            
            merged_agents = list(merged_dict.values())
            logger.info(f"[MainWindow] ✅ Merged {len(merged_agents)} unique agents")
            
            return merged_agents
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to merge agent data: {e}")
            # Return local agents as fallback
            return local_agents
    
    def _merge_all_agent_sources(self, code_built_agents, db_cloud_agents):
        """
        Merge agents from all sources with deduplication into a unified list of EC_Agent objects
        
        Priority: Code-built > Cloud > Local DB
        
        Args:
            code_built_agents: List of (name, agent) tuples from code builders
            db_cloud_agents: List of agent dicts from DB/Cloud merge
        
        Returns:
            List of EC_Agent objects (unified type)
        """
        try:
            logger.info("[MainWindow] 🔀 Merging all agent sources into unified list...")
            
            # Import converter
            from agent.agent_converter import convert_agent_dict_to_ec_agent
            
            # Create a unified list of EC_Agent objects
            unified_agents = []
            
            # Track code-built agent names for deduplication
            code_built_names = set()
            
            # Step 1: Add all code-built agents (already EC_Agent objects)
            for name, agent in code_built_agents:
                if agent:
                    unified_agents.append(agent)
                    code_built_names.add(name)
                    logger.debug(f"[MainWindow] 🔧 Added code-built agent: {name}")
            
            # Step 2: Convert DB/Cloud agents (dicts) to EC_Agent objects
            converted_count = 0
            failed_count = 0
            
            for agent_data in db_cloud_agents:
                agent_name = agent_data.get('name', '')
                
                # Only keep DB/Cloud agent if no code-built agent with same name
                if agent_name not in code_built_names:
                    # Convert dict to EC_Agent object
                    ec_agent = convert_agent_dict_to_ec_agent(agent_data, self)
                    if ec_agent:
                        unified_agents.append(ec_agent)
                        converted_count += 1
                        logger.debug(f"[MainWindow] 📂 Converted DB/Cloud agent: {agent_name}")
                    else:
                        failed_count += 1
                        logger.warning(f"[MainWindow] ⚠️  Failed to convert DB/Cloud agent: {agent_name}")
                else:
                    logger.debug(f"[MainWindow] ⚠️  DB/Cloud agent '{agent_name}' overwritten by code-built agent")
            
            logger.info(f"[MainWindow] ✅ Merged all sources into unified list:")
            logger.info(f"[MainWindow]    - Code-built agents: {len(code_built_names)}")
            logger.info(f"[MainWindow]    - DB/Cloud agents converted: {converted_count}")
            if failed_count > 0:
                logger.warning(f"[MainWindow]    - Conversion failed: {failed_count}")
            logger.info(f"[MainWindow]    - Total EC_Agent objects: {len(unified_agents)}")
            
            return unified_agents
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to merge all agent sources: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Return code-built agents as fallback
            return [agent for _, agent in code_built_agents if agent]
    
    async def _update_local_db_agents(self, merged_agents):
        """
        Update local database with merged agent data
        
        Args:
            merged_agents: List of merged agent dicts
        """
        try:
            logger.info(f"[MainWindow] 💾 Updating local database with {len(merged_agents)} merged agents...")
            
            if not self.ec_db_mgr or not self.ec_db_mgr.agent_service:
                logger.warning("[MainWindow] ⚠️  Agent service not available, skipping DB update")
                return
            
            agent_service = self.ec_db_mgr.agent_service
            
            # Run database update in executor
            def update_db():
                try:
                    with agent_service.session_scope() as session:
                        from agent.db.models.agent_model import DBAgent
                        
                        updated_count = 0
                        for agent_data in merged_agents:
                            agent_id = agent_data.get('id')
                            if not agent_id:
                                continue
                            
                            # Check if agent exists
                            # IMPORTANT: Use self.user (original email) not self.log_user (sanitized)
                            existing = session.query(DBAgent).filter(
                                DBAgent.id == agent_id,
                                DBAgent.owner == self.user
                            ).first()
                            
                            if existing:
                                # Update existing agent
                                for key, value in agent_data.items():
                                    if hasattr(existing, key):
                                        # Convert timestamp to datetime for SQLite
                                        if key in ('created_at', 'updated_at') and isinstance(value, (int, float)):
                                            from datetime import datetime
                                            value = datetime.fromtimestamp(value / 1000.0)  # Convert ms to seconds
                                        setattr(existing, key, value)
                                updated_count += 1
                            else:
                                # Create new agent - convert timestamps
                                agent_dict = agent_data.copy()
                                for key in ('created_at', 'updated_at'):
                                    if key in agent_dict and isinstance(agent_dict[key], (int, float)):
                                        from datetime import datetime
                                        agent_dict[key] = datetime.fromtimestamp(agent_dict[key] / 1000.0)
                                new_agent = DBAgent(**agent_dict)
                                session.add(new_agent)
                                updated_count += 1
                        
                        session.commit()
                        logger.info(f"[MainWindow] ✅ Updated {updated_count} agents in database")
                        
                except Exception as e:
                    logger.error(f"[MainWindow] ❌ Database update failed: {e}")
                    session.rollback()
            
            await asyncio.get_event_loop().run_in_executor(None, update_db)
            
        except Exception as e:
            logger.error(f"[MainWindow] ❌ Failed to update local DB agents: {e}")


    def get_vehicle_ecbot_op_agent(self, v):
        # obtain agents on a vehicle.
        logger.debug(f"{len(self.agents)}")
        ecb_op_agent = next((ag for ag in self.agents if "ECBot RPA Operator Agent" in ag.card.name), None)
        logger.info("FOUND Operator......", ecb_op_agent.card.name)
        return ecb_op_agent

    # SC note - really need to have
    async def run_async_tasks(self):
        all_tasks = [self.peer_task, self.monitor_task, self.chat_task]
        await asyncio.gather(*all_tasks)


    def get_helper_agent(self):
        return self.helper_agent


    def translateSiteName(self, site_text):
        if site_text in self.static_resource.SITES_SH_DICT.keys():
            return self.static_resource.SITES_SH_DICT[site_text]
        else:
            return site_text

    def translatePlatform(self, site_text):
        if site_text in self.static_resource.PLATFORMS_SH_DICT.keys():
            return self.static_resource.PLATFORMS_SH_DICT[site_text]
        else:
            return site_text

    def translateShortSiteName(self, site_text):
        if site_text in self.static_resource.SH_SITES_DICT.keys():
            return self.static_resource.SH_SITES_DICT[site_text]
        else:
            return site_text

    def translateShortPlatform(self, site_text):
        if site_text in self.static_resource.SH_PLATFORMS_DICT.keys():
            return self.static_resource.SH_PLATFORMS_DICT[site_text]
        else:
            return site_text



    def setCommanderName(self, cn):
        self.commander_name = cn

    def getCommanderName(self):
        return self.commander_name

    def _get_cpu_info_safely(self):
        """
        Safely get CPU information, avoiding multiprocessing issues

        Returns:
            dict: CPU information dictionary containing fields like brand_raw and hz_advertised_friendly
        """
        from utils.cpu_info_helper import get_cpu_info_safely
        return get_cpu_info_safely()

    def getWifis(self):
        return self.config_manager.general_settings.get_wifi_networks()

    def getWebDriverPath(self):
        return self.config_manager.general_settings.default_webdriver_path



    def getWebDriver(self):
        return self.default_webdriver

    def setWebDriver(self, driver):
        self.default_webdriver = driver

    def getWebCrawler(self):
        return self.async_crawler

    def setupUnifiedBrowserManager(self):
        """Setup unified browser manager"""
        try:
            self.unified_browser_manager = get_unified_browser_manager()

            # Pass file system path
            file_system_path = self.config_manager.general_settings.browser_use_file_system_path

            if self.unified_browser_manager.initialize(file_system_path=file_system_path):
                logger.info("✅ Browser manager initialized successfully")
            else:
                logger.error("❌ Browser manager initialization failed")
                self.unified_browser_manager = None

        except Exception as e:
            logger.error(f"Browser manager setup failed: {e}")
            self.unified_browser_manager = None

    async def _start_webdriver_initialization(self):
        """Initializes the WebDriver using the simplified WebDriverManager."""
        try:
            from gui.webdriver.manager import get_webdriver_manager

            logger.info("🚀 Starting WebDriver initialization...")

            # Get the manager instance
            manager = await get_webdriver_manager()

            # Initialize the manager. This is now a self-contained async process.
            success = await manager.initialize()

            if success:
                new_path = await manager.get_webdriver_path()
                # If we found a new, valid path that is different from the one in settings, update and save.
                if new_path and new_path != self.config_manager.general_settings.default_webdriver_path:
                    logger.info(f"WebDriver path updated to: {new_path}. Saving settings...")
                    self.config_manager.general_settings.default_webdriver_path = new_path
                    self.config_manager.general_settings.save()
                else:
                    # Ensure it's set even if not saved
                    self.config_manager.general_settings.default_webdriver_path = new_path

                logger.info(f"✅ WebDriver initialization successful. Path: {self.config_manager.general_settings.default_webdriver_path}")
            else:
                logger.error("❌ WebDriver initialization failed.")

        except Exception as e:
            logger.error(f"An exception occurred during WebDriver initialization: {e}")

    @property
    def async_crawler(self):
        try:
            manager = self.unified_browser_manager
            if manager and manager.is_ready():
                return manager.get_async_crawler()
        except Exception as e:
            logger.error(f"Error accessing async_crawler: {e}")
        return None

    @property
    def browser_session(self):
        try:
            manager = self.unified_browser_manager
            if manager and manager.is_ready():
                return manager.get_browser_session()
        except Exception as e:
            logger.error(f"Error accessing browser_session: {e}")
        return None

    @property
    def browser_use_controller(self):
        try:
            manager = getattr(self, 'unified_browser_manager', None)
            if manager and manager.is_ready():
                return manager.get_browser_use_controller()
        except Exception as e:
            logger.error(f"Error accessing browser_use_controller: {e}")
        return None

    @property
    def browser_use_file_system(self):
        try:
            manager = getattr(self, 'unified_browser_manager', None)
            if manager and manager.is_ready():
                return manager.get_browser_use_file_system()
        except Exception as e:
            logger.error(f"Error accessing browser_use_file_system: {e}")
        return None

    def getBrowserSession(self):
        return self.browser_session

    def getBrowserUseController(self):
        return self.browser_use_controller

    def load_build_dom_tree_script(self):
        script = ""
        try:
            logger.debug("Loading build dom tree script...", self.build_dom_tree_script_path)
            with open(self.build_dom_tree_script_path, 'r', encoding='utf-8') as file:
                script = file.read()
            return script
        except FileNotFoundError:
            logger.error(f"Error: The file {self.build_dom_tree_script_path} was not found.")
            return ""
        except IOError as e:
            logger.error(f"Error reading {self.build_dom_tree_script_path}: {e}")
            return ""

    #async def networking(self, platoonCallBack):
    def set_host_role(self, role):
        self.host_role = role

    def set_default_wifi(self, default_wifi):
        self.config_manager.general_settings.default_wifi = default_wifi
        self.config_manager.general_settings.save()

    def get_default_wifi(self):
        return self.config_manager.general_settings.default_wifi

    def set_default_printer(self, default_printer):
        self.config_manager.general_settings.default_printer = default_printer
        self.config_manager.general_settings.save()

    def get_default_printer(self):
        return self.config_manager.general_settings.default_printer


    def saveSettings(self):
        try:
            self.showMsg("saving all settings...")
            return self.config_manager.save_all_settings()
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False

    @property
    def general_settings(self):
        """
        Unified access to general settings.
        Use this property to access any general settings field directly:
        
        Examples:
            self.general_settings.debug_mode
            self.general_settings.schedule_mode
            self.general_settings.default_wifi
            self.general_settings.lan_api_endpoint
        """
        return self.config_manager.general_settings
    
    def get_server_base_url(self) -> str:
        """
        Get the base URL of the local server.
        
        This is the unified method for getting server URL across the application.
        It directly uses the server_manager_instance to get the actual running server URL.
        
        Returns:
            str: Base URL like "http://localhost:4668"
        """
        try:
            from gui.LocalServer import server_manager_instance
            if server_manager_instance:
                return server_manager_instance.get_server_url()
        except Exception as e:
            from utils.logger_helper import logger_helper as logger
            logger.warning(f"Failed to get server URL from server_manager: {e}")
        
        # Fallback: construct from config port
        port = self.general_settings.local_server_port
        return f"http://localhost:{port}"

    def get_host_role(self):
        return self.host_role


    def setCommanderXPort(self, xport):
        self.commanderXport = xport

    def getGuiMsgQueue(self):
        return self.gui_net_msg_queue

    def setIP(self, ip):
        self.ip = ip

    def getUser(self):
        return self.user

    def getNetworkApiEngine(self):
        return self.config_manager.general_settings.network_api_engine

    def getLanOCREndpoint(self):
        return self.config_manager.general_settings.ocr_api_endpoint

    def getLanOCRApiKey(self):
        return self.config_manager.general_settings.ocr_api_key

    def getLanApiEndpoint(self):
        return self.config_manager.general_settings.lan_api_endpoint

    def get_local_server_port(self):
        return self.config_manager.general_settings.local_server_port

    def getWanApiEndpoint(self):
        return self.config_manager.general_settings.wan_api_endpoint

    def getWanApiKey(self):
        return self.config_manager.general_settings.wan_api_key

    def getWSApiEndpoint(self):
        return self.config_manager.general_settings.ws_api_endpoint

    def getWSApiHost(self):
        return self.config_manager.general_settings.ws_api_host

    def getAcctSiteID(self):
        site = self.machine_name
        user = self.user.replace("@", "_").replace(".", "_")
        return f"{user}_{site}"

    def setMILANServer(self, ip, port="8848"):
        self.config_manager.general_settings.lan_api_endpoint = f"http://{ip}:{port}"
        self.config_manager.general_settings.save()
        logger.info(f"lan_api_endpoint: {self.config_manager.general_settings.lan_api_endpoint}")

    def setLanDBServer(self, ip, port="5080"):
        self.config_manager.general_settings.local_user_db_host = ip
        self.config_manager.general_settings.local_user_db_port = port
        self.config_manager.general_settings.save()

    def getDisplayResolution(self):
        return self.config_manager.general_settings.display_resolution



    def warn(self, msg, level="info"):
        logger.warning(msg)

    def showMsg(self, msg, level="info"):
        logger.info(msg)




    #convert time zone, time slot to datetime
    # the time slot is defined as following:
    # time slot is defined as a 20 minute interval, an entire day has 72 slots indexed 0~71
    # counting timezone, and starts from eastern standard time, the timezone will extend to
    # cover hawaii, which is 5 timezone away from eastern, so total time zone slots are
    # 72+15=87 or index 0~86.
    def ts2time(self, ts):
        thistime = datetime.now()
        zerotime = datetime(thistime.date().year, thistime.date().month, thistime.date().day, 0, 0, 0)
        if ts < 0:      # in case of timeslot is -1 it means run it asap, so make it 0 zero time of today.
            ts = 0
        time_change = timedelta(minutes=20*ts)
        runtime = zerotime + time_change
        return runtime

    def time2ts(self, pdt):
        thistime = datetime.now()
        zerotime = datetime(thistime.date().year, thistime.date().month, thistime.date().day, 0, 0, 0)
        # Get the time difference in seconds
        ts = int((pdt - zerotime).total_seconds()/1200)         # computer time slot in 20minuts chunk

        return ts


    def logout(self):
        """Initiate graceful logout and cleanup of background tasks/servers."""
        if getattr(self, "_cleanup_in_progress", False):
            return
        self._cleanup_in_progress = True
        self.showMsg("logging out (graceful shutdown)........")
        try:
            # Run async cleanup without blocking the UI thread
            self.mainLoop.create_task(self._async_cleanup_and_logout())
        except Exception as e:
            logger.warning(f"Failed to schedule async cleanup: {e}")

    async def _async_cleanup_and_logout(self):
        """Asynchronously cleanup background tasks, servers, and resources, then logout."""
        logger.info("[MainWindow] 🧹 Starting comprehensive cleanup for logout...")
        
        # Set shutdown flag to prevent WAN Chat reconnections
        self._shutting_down = True
        
        # Unregister proxy change callback
        try:
            if hasattr(self, '_proxy_callback_unregister') and self._proxy_callback_unregister:
                self._proxy_callback_unregister()
                self._proxy_callback_unregister = None
                logger.info("[MainWindow] ✅ Proxy change callback unregistered")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error unregistering proxy callback: {e}")
        
        # Stop sync manager auto retry timer
        try:
            from agent.cloud_api.offline_sync_manager import get_sync_manager
            manager = get_sync_manager()
            manager.stop_auto_retry()
            logger.info("[MainWindow] ✅ Sync manager auto retry timer stopped")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error stopping sync manager: {e}")
        
        # Stop LightRAG server
        try:
            if hasattr(self, 'lightrag_server') and self.lightrag_server:
                self.stop_lightrag_server()
                logger.info("[MainWindow] ✅ LightRAG server stopped")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error stopping LightRAG server: {e}")

        # Stop local Starlette server (uvicorn) and join thread
        try:
            from gui.LocalServer import stop_local_server, MCPHandler
            
            # First, clean up MCP session manager BEFORE stopping the server
            # This prevents the TaskGroup context issues
            try:
                logger.info("[MainWindow] 🧹 Pre-cleaning MCP session manager...")
                await MCPHandler.cleanup()
                logger.info("[MainWindow] ✅ MCP session manager pre-cleaned")
            except Exception as e:
                logger.warning(f"[MainWindow] ❌ Error pre-cleaning MCP session manager: {e}")
            
            # Then stop the server
            stop_local_server()
            logger.info("[MainWindow] ✅ Local Starlette server stopped")
            
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error stopping local server: {e}")

        # Close MCP client manager session
        try:
            from agent.mcp.local_client import mcp_client_manager
            await mcp_client_manager.close()
            logger.info("[MainWindow] ✅ MCP client manager closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing MCP client manager: {e}")

        # Close MCP client if present
        try:
            if hasattr(self, 'mcp_client') and self.mcp_client:
                if hasattr(self.mcp_client, 'close'):
                    await self.mcp_client.close()
                self.mcp_client = None
                logger.info("[MainWindow] ✅ MCP client closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing MCP client: {e}")

        # Close SSE connection manager if present
        try:
            if hasattr(self, '_sse_cm') and self._sse_cm:
                if hasattr(self._sse_cm, 'close'):
                    await self._sse_cm.close()
                self._sse_cm = None
                logger.info("[MainWindow] ✅ SSE connection manager closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing SSE connection manager: {e}")

        # Close websocket if present
        try:
            if getattr(self, 'websocket', None):
                ws = self.websocket
                close_fn = getattr(ws, 'close', None)
                if close_fn:
                    if asyncio.iscoroutinefunction(close_fn):
                        await close_fn()
                    else:
                        close_fn()
                self.websocket = None
                logger.info("[MainWindow] ✅ Websocket closed")
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Error closing websocket: {e}")

        # Close unified browser manager
        try:
            if hasattr(self, 'unified_browser_manager') and self.unified_browser_manager:
                if hasattr(self.unified_browser_manager, 'cleanup'):
                    cleanup_fn = self.unified_browser_manager.cleanup
                    if asyncio.iscoroutinefunction(cleanup_fn):
                        await cleanup_fn()
                    else:
                        cleanup_fn()
                elif hasattr(self.unified_browser_manager, 'close'):
                    close_fn = self.unified_browser_manager.close
                    if asyncio.iscoroutinefunction(close_fn):
                        await close_fn()
                    else:
                        close_fn()
                self.unified_browser_manager = None
                logger.info("[MainWindow] ✅ Unified browser manager closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing unified browser manager: {e}")

        # Close default webdriver if present
        try:
            if hasattr(self, 'default_webdriver') and self.default_webdriver:
                self.default_webdriver.quit()
                self.default_webdriver = None
                logger.info("[MainWindow] ✅ Default webdriver closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing default webdriver: {e}")

        # Close TCP server if present
        try:
            if hasattr(self, 'tcpServer') and self.tcpServer:
                if hasattr(self.tcpServer, 'close'):
                    self.tcpServer.close()
                self.tcpServer = None
                logger.info("[MainWindow] ✅ TCP server closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing TCP server: {e}")

        # Close commander transport if present
        try:
            if hasattr(self, 'commanderXport') and self.commanderXport:
                if hasattr(self.commanderXport, 'close'):
                    self.commanderXport.close()
                self.commanderXport = None
                logger.info("[MainWindow] ✅ Commander transport closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing commander transport: {e}")

        # Close session (cloud connection)
        try:
            if hasattr(self, 'session') and self.session:
                if hasattr(self.session, 'close'):
                    close_fn = self.session.close
                    if asyncio.iscoroutinefunction(close_fn):
                        await close_fn()
                    else:
                        close_fn()
                self.session = None
                logger.info("[MainWindow] ✅ Cloud session closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing cloud session: {e}")

        # Signal all agent TaskRunner loops to stop (while-loops in threads)
        try:
            from agent.tasks import TaskRunnerRegistry
            TaskRunnerRegistry.stop_all()
            logger.info("[MainWindow] ✅ TaskRunners stopped")
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Error stopping TaskRunners: {e}")

        # Cancel asyncio tasks we manage
        to_cancel = []
        for name in (
            'lan_task', 'peer_task', 'monitor_task', 'chat_task', 'wan_sub_task',
            'wan_chat_task', 'llm_sub_task', 'cloud_show_sub_task'
        ):
            try:
                t = getattr(self, name, None)
                if t and not t.done():
                    t.cancel()
                    to_cancel.append(t)
            except Exception:
                pass
        if to_cancel:
            try:
                await asyncio.gather(*to_cancel, return_exceptions=True)
                logger.info(f"[MainWindow] ✅ Cancelled {len(to_cancel)} asyncio tasks")
            except Exception:
                pass

        # Close Cloud LLM WebSocket and thread
        try:
            if hasattr(self, 'cloud_llm_ws') and self.cloud_llm_ws:
                self.cloud_llm_ws.close()
                logger.info("[MainWindow] ✅ Cloud LLM WebSocket closed")
            if hasattr(self, 'cloud_llm_thread') and self.cloud_llm_thread:
                # Thread is daemon, so it will be terminated when main process exits
                logger.info("[MainWindow] ✅ Cloud LLM thread will terminate with main process")
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Error closing Cloud LLM WebSocket: {e}")

        # Shut down ThreadPoolExecutor
        try:
            if hasattr(self, 'threadPoolExecutor') and self.threadPoolExecutor:
                self.threadPoolExecutor.shutdown(wait=False, cancel_futures=True)
                logger.info("[MainWindow] ✅ ThreadPoolExecutor shutdown")
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Error shutting down ThreadPoolExecutor: {e}")

        # Close database services and connections
        try:
            # Close chat service
            if hasattr(self, 'db_chat_service') and self.db_chat_service:
                if hasattr(self.db_chat_service, 'close'):
                    self.db_chat_service.close()
                self.db_chat_service = None
                logger.info("[MainWindow] ✅ Database chat service closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing database chat service: {e}")

        try:
            # Close database engine and session
            if hasattr(self, '_db_engine') and self._db_engine:
                self._db_engine.dispose()
                self._db_engine = None
                logger.info("[MainWindow] ✅ Database engine disposed")
            
            if hasattr(self, '_db_session') and self._db_session:
                self._db_session.close()
                self._db_session = None
                logger.info("[MainWindow] ✅ Database session closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing database engine/session: {e}")

        # Clear IPC registry system ready cache
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            IPCHandlerRegistry.clear_system_ready_cache()
            logger.debug("[MainWindow] ✅ IPC registry system ready cache cleared")
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Error clearing IPC registry cache: {e}")

        # Close database manager and clean up database connections
        try:
            if hasattr(self, 'ec_db_mgr') and self.ec_db_mgr:
                self.ec_db_mgr.close()
                self.ec_db_mgr = None
                logger.info("[MainWindow] ✅ Database manager closed")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error closing database manager: {e}")

        # Clear component managers
        try:
            manager_attrs = [
                'config_manager'
            ]
            for attr in manager_attrs:
                if hasattr(self, attr):
                    manager = getattr(self, attr)
                    if manager and hasattr(manager, 'cleanup'):
                        try:
                            if asyncio.iscoroutinefunction(manager.cleanup):
                                await manager.cleanup()
                            else:
                                manager.cleanup()
                        except Exception as e:
                            logger.debug(f"[MainWindow] Error cleaning up {attr}: {e}")
                    setattr(self, attr, None)
            logger.info("[MainWindow] ✅ Component managers cleared")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error clearing component managers: {e}")

        # Clear resource objects
        try:
            resource_attrs = ['file_resource', 'static_resource', 'zipper']
            for attr in resource_attrs:
                if hasattr(self, attr):
                    setattr(self, attr, None)
            logger.info("[MainWindow] ✅ Resource objects cleared")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error clearing resource objects: {e}")

        # Clear data collections
        try:
            data_attrs = [
                'agents', 'sellerInventoryJsonData', 'mcp_tools_schemas',
                'todays_work', 'reactive_work'
            ]
            for attr in data_attrs:
                if hasattr(self, attr):
                    data = getattr(self, attr)
                    if isinstance(data, (list, dict)):
                        data.clear()
                    else:
                        setattr(self, attr, None)
            logger.info("[MainWindow] ✅ Data collections cleared")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error clearing data collections: {e}")

        # Clear AppContext references
        try:
            from app_context import AppContext
            if AppContext.cleanup_instance():
                logger.info("[MainWindow] ✅ AppContext cleared")
            else:
                logger.warning("[MainWindow] ⚠️  AppContext cleanup had issues")
        except Exception as e:
            logger.warning(f"[MainWindow] ❌ Error clearing AppContext: {e}")

        # Finally, call auth logout and close window
        try:
            if hasattr(self, 'auth_manager') and self.auth_manager:
                self.auth_manager.logout()
                logger.info("[MainWindow] ✅ Auth manager logout completed")
        except Exception as e:
            logger.debug(f"[MainWindow] ❌ Auth logout error: {e}")

        logger.info("[MainWindow] 🎉 Comprehensive cleanup completed - logged out successfully")



    def addConnectingVehicle(self, vname, vip):
        try:
            # ipfields = vinfo.peername[0].split(".")

            if len(self.vehicles) > 0:
                v_host_names = [v.getName().split(":")[0] for v in self.vehicles]
                print("existing vehicle "+json.dumps(v_host_names))
            else:
                vids = []

            found_fl = next((fl for i, fl in enumerate(fieldLinks) if vname in fl["name"]), None)

            if vname not in v_host_names:
                self.showMsg("adding a new vehicle..... "+vname+" "+vip)
                newVehicle = VEHICLE(self)
                newVehicle.setIP(vip)
                newVehicle.setVid(vip.split(".")[3])
                newVehicle.setName(vname+":")
                if found_fl:
                    print("found_fl IP:", found_fl["ip"])
                    newVehicle.setFieldLink(found_fl)
                    newVehicle.setStatus("connecting")
                self.saveVehicle(newVehicle)
                self.vehicles.append(newVehicle)


                resultV = newVehicle
            else:
                self.showMsg("Reconnected: "+vip)
                foundV = next((v for i, v in enumerate(self.vehicles) if vname in v.getName()), None)
                foundV.setIP(vip)
                foundV.setStatus("connecting")
                if found_fl:
                    print("found_fl IP:", found_fl["ip"])
                    foundV.setFieldLink(found_fl)

                resultV = foundV

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddConnectingVehicle:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddConnectingVehicle: traceback information not available:" + str(e)

            self.showMsg(ex_stat)
        print("added connecting vehicle:", resultV.getName(), resultV.getStatus())
        return resultV



    def markVehicleOffline(self, vip, vname):
        global fieldLinks
        lostName = vname.split(":")[0]
        self.showMsg("marking vehicle offline: "+vip+" "+json.dumps([v.getIP()+":"+v.getName() for v in self.vehicles]))

        found_v_idx = next((i for i, v in enumerate(self.vehicles) if lostName in v.getName()), -1)
        print("found_v_idx", found_v_idx)
        if found_v_idx > 0:
            print("markingoff......")
            found_v = self.vehicles[found_v_idx]
            found_v.setStatus("offline")

        return found_v

    # add vehicles based on fieldlinks.
    def checkVehicles(self):
        import time
        start_time = time.time()
        
        self.showMsg("adding self as a vehicle if is Commander.....")
        existing_names = [v.getName().split(":")[0] for v in self.vehicles]
        print("existing v names:", existing_names)
        if self.machine_role == "Commander":
            # Check if this machine is already in the vehicle list
            if self.machine_name not in existing_names:
                # should add this machine to vehicle list.
                newVehicle = VEHICLE(self, self.machine_name+":"+self.os_short, self.ip)
                newVehicle.setStatus("running_idle")
                
                # Set complete system information
                if hasattr(self, 'architecture'):
                    # Get architecture from platform.architecture()[0] and convert to common format
                    arch_mapping = {
                        '64bit': 'x86_64' if 'intel' in self.processor.lower() or 'amd' in self.processor.lower() else 'arm64',
                        '32bit': 'x86'
                    }
                    newVehicle.setArch(arch_mapping.get(self.architecture, self.architecture))
                else:
                    # Fallback: detect architecture
                    import platform
                    machine = platform.machine().lower()
                    if machine in ['x86_64', 'amd64']:
                        newVehicle.setArch('x86_64')
                    elif machine in ['arm64', 'aarch64']:
                        newVehicle.setArch('arm64')
                    else:
                        newVehicle.setArch(machine)
                
                # Set functions based on role
                if hasattr(self, 'functions'):
                    newVehicle.setFunctions(self.functions)
                
                # Set unique vehicle ID based on IP
                ip_parts = self.ip.split('.')
                if len(ip_parts) >= 4:
                    newVehicle.setVid(ip_parts[-1])  # Use last octet as ID
                else:
                    newVehicle.setVid(str(hash(self.machine_name) % 1000))  # Fallback ID
                
                # Set device information and performance metrics using system info manager
                newVehicle.setType(self.device_type)
                newVehicle.setLocation(f"Local - {self.machine_name}")
                newVehicle.setBattery(100)  # Desktop/laptop default to 100%
                newVehicle.setCurrentTask("System Management")
                
                # Set maintenance schedule (example: next maintenance in 30 days)
                from datetime import datetime, timedelta
                next_maintenance = datetime.now() + timedelta(days=30)
                newVehicle.setNextMaintenance(next_maintenance.strftime("%Y-%m-%d"))
                
                # Schedule async system metrics update (non-blocking)
                try:
                    # Try to create task in existing event loop
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._update_vehicle_metrics_async(newVehicle))
                    logger.debug(f"[MainWindow] ✅ Scheduled async metrics update for vehicle: {newVehicle.getName()}")
                except RuntimeError as e:
                    # This is expected during startup when event loop is not running yet
                    logger.debug(f"[MainWindow] ⏳ Event loop not running yet for vehicle metrics update: {e}")
                    # Use QTimer for delayed execution, waiting for event loop to be available
                    from PySide6.QtCore import QTimer
                    timer = QTimer()
                    timer.timeout.connect(lambda v=newVehicle: self._schedule_delayed_metrics_update(v))
                    timer.setSingleShot(True)
                    timer.start(2000)  # Retry after 2 seconds
                    logger.info(f"[MainWindow] 📊 Scheduled delayed metrics update for vehicle: {newVehicle.getName()}")
                
                self.saveVehicle(newVehicle)
                self.vehicles.append(newVehicle)

                logger.info(f"[MainWindow] Added local machine as vehicle: {self.machine_name} (arch: {newVehicle.getArch()}, functions: {newVehicle.getFunctions()})")
            else:
                logger.info(f"[MainWindow] Local machine already exists in vehicle list: {self.machine_name}")

        # Record performance statistics
        end_time = time.time()
        logger.info(f"[MainWindow] checkVehicles completed in {end_time - start_time:.3f}s")

        self.showMsg("adding already linked vehicles.....")
        for i in range(len(fieldLinks)):
            if fieldLinks[i]["name"].split(":")[0] not in existing_names:
                self.showMsg("a fieldlink....."+json.dumps(fieldLinks[i]["ip"]))
                newVehicle = VEHICLE(self, fieldLinks[i]["name"], fieldLinks[i]["ip"])
                newVehicle.setFieldLink(fieldLinks[i])
                newVehicle.setStatus("running_idle")        # if already has a fieldlink, that means it's tcp connected.
                ipfields = fieldLinks[i]["ip"].split(".")
                ip = ipfields[len(ipfields)-1]
                newVehicle.setVid(ip)
                self.saveVehicle(newVehicle)
                self.vehicles.append(newVehicle)


    def saveVehicle(self, vehicle: VEHICLE):
        """Save vehicle to database - only called when database services are ready"""
        # Check if this is a Commander role (only Commander has database services)
        if "Commander" not in self.machine_role:
            logger.debug(f"[MainWindow] Platoon role - no database save needed for vehicle: {vehicle.getName()}")
            return

        # At this point, vehicle_service MUST be available because saveVehicle should only be called
        # after database services are initialized. If it's not available, it's a programming error.
        if not hasattr(self, 'vehicle_service') or self.vehicle_service is None:
            logger.error(f"[MainWindow] PROGRAMMING ERROR: saveVehicle called before vehicle_service is ready!")
            logger.error(f"[MainWindow] This indicates a timing issue in the initialization sequence.")
            raise RuntimeError(f"saveVehicle called before vehicle_service initialization - fix the calling sequence!")

        try:
            v = self.vehicle_service.find_vehicle_by_ip(vehicle.ip)
            if v is None:
                # Create new vehicle record
                vehicle_model = VehicleModel()
                vehicle_model.arch = vehicle.arch
                vehicle_model.bot_ids = str(vehicle.bot_ids)
                vehicle_model.daily_mids = str(vehicle.daily_mids)
                vehicle_model.ip = vehicle.ip
                vehicle_model.mstats = str(vehicle.mstats)
                vehicle_model.name = vehicle.name
                vehicle_model.os = vehicle.os
                vehicle_model.cap = vehicle.CAP
                vehicle_model.status = vehicle.status
                self.vehicle_service.insert_vehicle(vehicle_model)
                vehicle.id = vehicle_model.id
                logger.debug(f"[MainWindow] Created new vehicle record: {vehicle.getName()} (ID: {vehicle.id})")
            else:
                # Update existing vehicle record and sync data
                vehicle.setVid(v.id)
                vehicle.setBotIds(ast.literal_eval(v.bot_ids))
                vehicle.setMStats(ast.literal_eval(v.mstats))
                vehicle.setMids(ast.literal_eval(v.daily_mids))
                v.cap = vehicle.CAP
                v.status = vehicle.status  # Update status in database
                self.vehicle_service.update_vehicle(v)
                logger.debug(f"[MainWindow] Updated vehicle record: {vehicle.getName()} (ID: {vehicle.id})")

        except Exception as e:
            logger.error(f"[MainWindow] Failed to save vehicle {vehicle.getName()}: {e}")
            raise  # Re-raise the exception to make the error visible

    def sendPlatoonCommand(self, command, rows, mids):
        self.showMsg("hello???")
        if command == "refresh":
            # cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqStatusUpdate", "missions":"all"}
        elif command == "halt":
            # cmd = '{\"cmd\":\"reqHaltMissions\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqHaltMissions", "missions":"all"}
        elif command == "resume":
            # cmd = '{\"cmd\":\"reqResumeMissions\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqResumeMissions", "missions":"all"}
        elif command == "cancel this":
            mission_list_string = ','.join(str(x) for x in mids)
            # cmd = '{\"cmd\":\"reqCancelMissions\", \"missions\":\"'+mission_list_string+'\"}'
            cmd = {"cmd":"reqCancelMissions", "missions": mission_list_string}
        elif command == "cancel all":
            # cmd = '{\"cmd\":\"reqCancelAllMissions\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqCancelAllMissions", "missions":"all"}
        else:
            # cmd = '{\"cmd\":\"ping\", \"missions\":\"all\"}'
            cmd = {"cmd":"ping", "missions":"all"}

        self.showMsg("cmd is: "+cmd)
        if len(rows) > 0:
            effective_rows = list(filter(lambda r: r >= 0, rows))
        else:
            effective_rows = []

        self.showMsg("effective_rows:"+json.dumps(effective_rows))
        self.sendToPlatoonsByRowIdxs(effective_rows, cmd)




    # this function sends commands to platoon(s)
    def sendToVehicleByVip(self, vip, cmd={"cmd": "ping"}):
        self.showMsg("sending commands to vehicle by vip.....")
        self.showMsg("tcp connections....." + vip + " " + json.dumps([flk["ip"] for flk in fieldLinks]))

        link = next((x for i, x in enumerate(fieldLinks) if x["ip"] == vip), None)

        # if not self.tcpServer == None:
        if link:
            self.send_json_to_platoon(link, cmd)
            self.showMsg("cmd sent on link:" + str(vip) + ":" + json.dumps(cmd))
        else:
            self.showMsg("Warning..... TCP server not up and running yet...")

    def getVehicleByName(self, vname):
        found_vehicle = next((v for i, v in enumerate(self.vehicles) if v.getName() == vname), None)
        return found_vehicle

    def readVehicleJsonFile(self):
        self.showMsg("Reading Vehicle Json File: "+self.VEHICLES_FILE)
        self.vehiclesJsonData = self.config_manager.get_vehicles()
        if self.vehiclesJsonData:
            self.translateVehiclesJson(self.vehiclesJsonData)
        else:
            self.showMsg("WARNING: Vehicle Json File NOT FOUND: " + self.VEHICLES_FILE)

    def translateVehiclesJson(self, vjds):
        all_vnames = [v.getName() for v in self.vehicles]
        print("vehicles names in the vehicle json file:", all_vnames)
        for vjd in vjds:
            if vjd["name"] not in all_vnames:
                print("add new vehicle to local vehicle data structure but no yet added to GUI", vjd["name"])
                new_v = VEHICLE(self)
                new_v.loadJson(vjd)
                new_v.setStatus("offline")      # always set to offline when load from file. will self correct as we update it later....
                self.saveVehicle(new_v)
                self.vehicles.append(new_v)

            else:
                if "test_disabled" in vjd:
                    foundV = self.getVehicleByName(vjd["name"])
                    foundV.setTestDisabled(vjd["test_disabled"])

    def saveVehiclesJsonFile(self):
        if self.VEHICLES_FILE:
            try:
                vehiclesdata = []
                for v in self.vehicles:
                    vehiclesdata.append(v.genJson())

                self.showMsg("WRITE TO VEHICLES_FILE: " + self.VEHICLES_FILE)
                self.vehiclesJsonData = vehiclesdata
                return self.config_manager.save_vehicles(vehiclesdata)
            except Exception as e:
                logger.error(f"Unable to save file: {self.VEHICLES_FILE}, error: {e}")
                return False
        else:
            self.showMsg("Vehicles json file does NOT exist.")


    def translateInventoryJson(self):
        #self.showMsg("Translating JSON to data......."+str(len(self.sellerInventoryJsonData)))
        for bj in self.sellerInventoryJsonData:
            new_inventory = INVENTORY()
            new_inventory.setJsonData(bj)
            self.inventories.append(new_inventory)


    def readSellerInventoryJsonFile(self, inv_file):
        if inv_file == "":
            inv_file_name = self.product_catelog_file
        else:
            inv_file_name = inv_file

        self.showMsg("product catelog file: "+inv_file_name)
        if exists(inv_file_name):
            self.showMsg("Reading inventory file: "+inv_file_name)
            with open(inv_file_name, 'r', encoding='utf-8') as file:
                self.sellerInventoryJsonData = json.load(file)
                self.translateInventoryJson()
        else:
            self.showMsg("NO inventory file found!")

    def getSellerProductCatelog(self):
        return self.sellerInventoryJsonData




    def eventFilter(self, source, event):
        return super().eventFilter(source, event)


    def process_original_xlsx_file(self, file_path):
        # Read the Excel file, skipping the first two rows
        import pandas as pd
        df = pd.read_excel(file_path, skiprows=2)

        # Drop rows where all elements are NaN
        df.dropna(how='all', inplace=True)

        # Convert each row to a JSON object and append to a list
        json_list = df.to_dict(orient='records')

        #add a reverse link back to
        for jl in json_list:
            jl["file_link"] = file_path

        print("READ XLSX::", json_list)
        return json_list

    def update_original_xlsx_file(self, file_path, mission_data):
        # Read the Excel file, skipping the first two rows
        dir_path = os.path.dirname(file_path)

        import pandas as pd
        df = pd.read_excel(file_path, skiprows=2)

        # Drop rows where all elements are NaN
        df.dropna(how='all', inplace=True)

        # Convert each row to a JSON object and append to a list
        json_list = df.to_dict(orient='records')

        mission_ids = [mission["mission ID"] for mission in mission_data]
        completion_dates = [mission["completion date"] for mission in mission_data]

        # Add new columns with default or empty values
        df['mission ID'] = mission_ids[:len(df)]
        df['completion date'] = completion_dates[:len(df)]

        # Get the new file name using the first row of the "mission ID" column
        new_mission_id = df.loc[0, 'mission ID']
        base_name = os.path.basename(file_path)
        new_file_name = f"{os.path.splitext(base_name)[0]}_{new_mission_id}.xlsx"
        new_file_path = os.path.join(dir_path, new_file_name)

        # Save the updated DataFrame to a new file
        df.to_excel(new_file_path, index=False)

        print(f"File saved as {new_file_name}")




    def newProductsFromFile(self):

        self.showMsg("loading products from a local file or DB...")
        api_products = []
        uncompressed = open(self.my_ecb_data_homepath + "/resource/testdata/newproducts.json")
        if uncompressed != None:
            # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
            fileproducts = json.load(uncompressed)
            if len(fileproducts) > 0:
                self.product_service.find_all_products()

            else:
                self.warn("NO products found in file.")
        else:
            self.warn("No tests products file")


    def setOwner(self, owner):
        self.owner = owner

    def get_vehicle_settings(self, forceful="false"):
        import tzlocal
        vsettings = {
            "vwins": len([v for v in self.vehicles if v.getOS() == "win"]),
            "vmacs": len([v for v in self.vehicles if v.getOS() == "mac"]),
            "vlnxs": len([v for v in self.vehicles if v.getOS() == "linux"]),
            "forceful": forceful,
            "tz": str(tzlocal.get_localzone())
        }

        print("v timezone:", tzlocal.get_localzone())
        # add self to the compute resource pool
        if self.host_role == "Commander":
            if self.platform == "win":
                vsettings["vwins"] = vsettings["vwins"] + 1
            elif self.platform == "mac":
                vsettings["vmacs"] = vsettings["vmacs"] + 1
            else:
                vsettings["vlnxs"] = vsettings["vlnxs"] + 1
        return vsettings

    # the message queue is for messsage from tcpip task to the GUI task. OPENAI's fix
    async def servePlatoons(self, msgQueue):
        self.showMsg("starting servePlatoons")

        while True:
            logger.trace("listening to platoons" + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

            if not msgQueue.empty():
                try:
                    # Process all available messages in the queue
                    while not msgQueue.empty():
                        net_message = await msgQueue.get()
                        print("received net message:", type(net_message), net_message)
                        if isinstance(net_message, str):
                            if len(net_message) > 256:
                                mlen = 256
                            else:
                                mlen = len(net_message)
                            self.showMsg(
                                "received queued msg from platoon..... [" + str(msgQueue.qsize()) + "]" + net_message[:mlen])

                            print("platoon server received message from queu...")
                            # Parse the message into parts
                            msg_parts = net_message.split("!")
                            if len(msg_parts) >= 3:  # Check for valid message structure
                                if msg_parts[1] == "net data":
                                    await self.processPlatoonMsgs(msg_parts[2], msg_parts[0])
                                elif msg_parts[1] == "connection":
                                    print("received connection message: " + msg_parts[0] + " " + msg_parts[2])

                                    addedV = self.addConnectingVehicle(msg_parts[2], msg_parts[0])
                                    # await asyncio.sleep(8)
                                    # if len(self.vehicles) > 0:
                                    #     print("pinging platoon: " + str(len(self.vehicles) - 1) + msg_parts[0])
                                    #     self.sendToVehicleByVip(msg_parts[0])
                                elif msg_parts[1] == "net loss":
                                    print("received net loss")
                                    found_vehicle = self.markVehicleOffline(msg_parts[0], msg_parts[2])
                                    vehicle_report = self.prepVehicleReportData(found_vehicle)
                                    resp = send_report_vehicles_to_cloud(
                                        self.session,
                                        self.get_auth_token(),
                                        vehicle_report,
                                        self.getWanApiEndpoint()
                                    )
                                    self.saveVehiclesJsonFile()
                        elif isinstance(net_message, dict):
                            print("process json from queue:")

                        msgQueue.task_done()

                except asyncio.QueueEmpty:
                    print("Queue unexpectedly empty when trying to get message.")
                except Exception as e:
                    print(f"Error processing Commander message: {e}")

            else:
                # if nothing on queue, do a quick check if any vehicle needs a ping-pong check
                for v in self.vehicles:
                    if "connecting" in v.getStatus():
                        print("pinging platoon: " + v.getIP())
                        self.sendToVehicleByVip(v.getIP())
            await asyncio.sleep(1)  # Short sleep to avoid busy-waiting







    # msg in json format
    # { sender: "ip addr", type: "intro/status/report", content : "another json" }
    # content format varies according to type.
    async def processPlatoonMsgs(self, msgString, ip):
        try:
            global fieldLinks
            fl_ips = [x["ip"] for x in fieldLinks]
            if len(msgString) < 128:
                logger.debug("Platoon Msg Received:"+msgString+" from::"+ip+"  "+str(len(fieldLinks)) + json.dumps(fl_ips))
            else:
                logger.debug("Platoon Msg Received: ..." + msgString[-127:0] + " from::" + ip + "  " + str(len(fieldLinks)) + json.dumps(
                    fl_ips))
            msg = json.loads(msgString)

            found = next((x for x in fieldLinks if x["ip"] == ip), None)
            found_vehicle = next((x for x in self.vehicles if x.getIP() == msg["ip"]), None)

            # first, check ip and make sure this from a know vehicle.
            if msg["type"] == "intro" or msg["type"] == "pong":
                if found:
                    self.showMsg("recevied a vehicle introduction/pong:" + msg["content"]["name"] + ":" + msg["content"]["os"] + ":"+ msg["content"]["machine"])

                    if found_vehicle:
                        print("found a vehicle to set.... "+found_vehicle.getOS())
                        if "connecting" in found_vehicle.getStatus():
                            found_vehicle.setStatus("running_idle")

                        if "Windows" in msg["content"]["os"]:
                            found_vehicle.setOS("Windows")
                            found_vehicle.setName(msg["content"]["name"]+":win")
                        elif "Mac" in msg["content"]["os"]:
                            found_vehicle.setOS("Mac")
                            found_vehicle.setName(msg["content"]["name"] + ":mac")
                        elif "Lin" in msg["content"]["os"]:
                            found_vehicle.setOS("Linux")
                            found_vehicle.setName(msg["content"]["name"] + ":linux")

                        print("now found vehicle" + found_vehicle.getName() + " " + found_vehicle.getOS())
                        # this is a good juncture to update vehicle status on cloud and local DB and JSON file.
                        #  now
                        vehicle_report = self.prepVehicleReportData(found_vehicle)
                        resp = send_report_vehicles_to_cloud(self.session,
                                                             self.get_auth_token(),
                                                             vehicle_report,
                                                             self.getWanApiEndpoint())
                        self.saveVehiclesJsonFile()

                        # sync finger print profiles from that vehicle.
                        if  msg["type"] == "pong":
                            # Launch async function without blocking
                            asyncio.ensure_future(self.syncFingerPrintOnConnectedVehicle(found_vehicle))

            elif msg["type"] == "status":
                # update vehicle status display.
                self.showMsg(msg["content"])
                logger.debug("msg type:" + "status", "servePlatoons", self)
                self.showMsg("recevied a status update message:"+msg["content"])
                if self.platoonWin:
                    self.showMsg("updating platoon WIN")
                    self.platoonWin.updatePlatoonStatAndShow(msg, fieldLinks)
                    self.platoonWin.show()
                else:
                    self.showMsg("ERROR: platoon win not yet exists.......")

                # update mission status to the cloud and to local data structure and to chat？
                # "mid": mid,
                # "botid": self.missions[mid].getBid(),
                # "sst": self.missions[mid].getEstimatedStartTime(),
                # "sd": self.missions[mid].getEstimatedRunTime(),
                # "ast": self.missions[mid].getActualStartTime(),
                # "aet": self.missions[mid].getActualEndTime(),
                # "status": m_stat,
                # "error": m_err
                if msg["content"]:
                    mStats = json.loads(msg["content"])

                    self.updateMStats(mStats)
                else:
                    print("WARN: status contents empty.")

            elif msg["type"] == "report":
                # collect report, the report should be already organized in json format and ready to submit to the network.
                logger.debug("msg type:"+"report", "servePlatoons", self)
                #msg should be in the following json format {"ip": self.ip, "type": "report", "content": []]}
                self.todaysPlatoonReports.append(msg)

                # now using ip to find the item added to self.self.todays_work["tbd"]
                task_idx = 0
                found = False
                for item in self.todays_work["tbd"]:
                    if "ip" in item:
                        if item["ip"] == msg["ip"]:
                            found = True
                            break
                    task_idx = task_idx + 1

                if found:
                    self.showMsg("pop a finising a remotely executed task...."+str(task_idx))
                    finished = self.todays_work["tbd"].pop(task_idx)
                    self.todays_completed.append(finished)

                    # Here need to update completed mission display subwindows.
                    self.updateCompletedMissions(finished)

                self.showMsg("len todays's reports: "+str(len(self.todaysPlatoonReports))+" len todays's completed:"+str(len(self.todays_completed)))
                self.showMsg("completd: "+json.dumps(self.todays_completed))

                # update vehicle status, now becomes idle again.
                self.updateVehicleStatusToRunningIdle(msg["ip"])

                # keep statistics on all platoon runs.
                if len(self.todaysPlatoonReports) == self.num_todays_task_groups:
                    # check = all(item in List1 for item in List2)
                    # this means all reports are collected, this is the last missing piece, ready to send to cloud.
                    await self.doneWithToday()
                    self.num_todays_task_groups = 0
            elif msg["type"] == "botsADSProfilesUpdate":
                logger.debug("received botsADSProfilesUpdate message", "servePlatoons", self)
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receivePlatoonBotsADSProfileUpdateMessage(msg)
            elif msg["type"] == "botsADSProfilesBatchUpdate":
                logger.debug("received botsADSProfilesBatchUpdate message", "servePlatoons", self)
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                remote_outdated = self.receiveBotsADSProfilesBatchUpdateMessage(msg)
                self.expected_vehicle_responses[found_vehicle.getName()] = "Yes"

                if self.allResponded():
                    logger.debug("all ads profiles updated...", "servePlatoons", self)
                    self.botsFingerPrintsReady = True

                if remote_outdated:
                    logger.debug("remote outdated...", "servePlatoons", self)
                    self.batchSendFingerPrintProfilesToCommander(remote_outdated)

                # now the profiles are updated. send this vehicle's schedule to it.
                vname = found_vehicle.getName()
                logger.debug("setup vehicle to do some work..."+vname, "servePlatoons", self)

                if self.unassigned_scheduled_task_groups:
                    if vname in self.unassigned_scheduled_task_groups:
                        p_task_groups = self.unassigned_scheduled_task_groups[vname]
                    else:
                        print(f"{vname} not found in unassigned_scheduled_task_groups empty")
                        print("keys:", list(self.unassigned_scheduled_task_groups.keys()))
                        p_task_groups = []
                else:
                    if self.todays_scheduled_task_groups:
                        if vname in self.todays_scheduled_task_groups:
                            p_task_groups = self.todays_scheduled_task_groups[vname]
                        else:
                            print(f"{vname} not found in todays_scheduled_task_groups empty")
                            print("keys:", list(self.todays_scheduled_task_groups.keys()))
                            p_task_groups = []
                    else:
                        print("time stamp "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]+" todays_scheduled_task_groups empty")
                        p_task_groups = []
                await self.vehicleSetupWorkSchedule(found_vehicle, p_task_groups)

            elif msg["type"] == "missionResultFile":
                self.showMsg("received missionResultFile message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receivePlatoonMissionResultFilesMessage(msg)

            elif msg["type"] == "reqResendWorkReq":
                logger.debug("received reqResendWorkReq message")
                # get work for this vehicle and send setWork
                self.reGenWorksForVehicle(found_vehicle)
                # self.vehicleSetupWorkSchedule(found_vehicle, self.todays_scheduled_task_groups)

            elif msg["type"] == "chat":
                logger.debug("received chat message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receiveBotChatMessage(msg["content"])

            elif msg["type"] == "exlog":
                self.showMsg("received exlog message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receiveBotLogMessage(msg["content"])
            elif msg["type"] == "heartbeat":
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text

                if found_vehicle:
                    # this will set status as well as the last_update_time parameter
                    if found_vehicle.getStatus() != msg["content"]["vstatus"]:
                        found_vehicle.setStatus(msg["content"]["vstatus"])

                logger.debug("Heartbeat From Vehicle: "+msg["ip"], "servePlatoons", self)
            else:
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.showMsg("unknown type:"+msg["contents"])

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorprocessPlatoonMsgs:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorprocessPlatoonMsgs: traceback information not available:" + str(e)
            logger.debug(ex_stat, "servePlatoons", self)

            self.showMsg(ex_stat)


    def allResponded(self):
        alldone = False

        alldone = all([self.expected_vehicle_responses[v] for v in self.expected_vehicle_responses])

        return alldone

    def obtainTZ(self):
        local_time = time.localtime()  # returns a `time.struct_time`
        tzname_local = local_time.tm_zone
        if "East" in tzname_local or "EST" in tzname_local:
            tz = "eastern"
        elif "Pacific" in tzname_local or "PST" in tzname_local:
            tz = "pacific"
        elif "Central" in tzname_local or "CST" in tzname_local:
            tz = "central"
        elif "Mountain" in tzname_local or "MST" in tzname_local:
            tz = "mountain"
        elif "Alaska" in tzname_local or "AST" in tzname_local:
            tz = "alaska"
        elif "Hawaii" in tzname_local or "HST" in tzname_local:
            tz = "hawaii"
        else:
            tz = "eastern"

        return tz

    def getTZ(self):
        return self.tz

    def gen_default_fetch(self):
        FETCH_ROUTINE = [{
                    "mid": 0,
                    "bid": 0,
                    "name": "fetch schedules",
                    "cuspas": "",
                    "todos": None,
                    "start_time": START_TIME,
                    "end_time": "",
                    "stat": "nys"
                }]

        return FETCH_ROUTINE

    def createTrialRunMission(self):
        trMission = EBMISSION(self)
        trMission.setMid(20231225)
        trMission.pubAttributes.setType("user", "Sell")
        trMission.pubAttributes.setBot(0)
        trMission.setCusPAS("win,chrome,amz")
        self.missions.append(trMission)

        return trMission

    def getTrialRunMission(self):
        return self.trMission

    def addSkillToTrialRunMission(self, skid):
        found = False
        for m in self.missions:
            if m.getMid() == 20231225:
                found = True
                break
        if found:
            m.setSkills([skid])

    def getTrialRunMission(self):
        found = False
        for m in self.missions:
            if m.getMid() == 20231225:
                found = True
                break
        if found:
            return m
        else:
            return None

    # Search functions removed - UI components no longer exist



    def getIP(self):
        return self.ip

    def getHostName(self):
        return self.machine_name



    def send_chat_to_local_bot(self, chat_msg):
        # """ Directly enqueue a message to the asyncio task when the button is clicked. """
        asyncio.create_task(self.gui_chat_msg_queue.put(chat_msg))

    # the message will be in the format of botid:send time stamp in yyyy:mm:dd hh:mm:ss format:msg in html format
    # from network the message will have chatmsg: prepend to the message.
    def update_chat_gui(self, rcvd_msg):
        # Chat GUI removed - no longer updating chat display
        pass

    # this is the interface to the chatting bots, taking message from the running bots and display them on GUI
    async def connectChat(self, chat_msg_queue):
        running = True
        while running:
            if not chat_msg_queue.empty():
                message = await chat_msg_queue.get()
                self.showMsg(f"Rx Chat message from bot: {message}")
                # Chat GUI removed - no longer updating chat display
                if self.host_role != "Staff Officer":
                    response = self.think_about_a_reponse(message)
                    self.c_send_chat(response)
                chat_msg_queue.task_done()

            logger.trace("chat Task ticking....")
            await asyncio.sleep(1)

    def getAgentV(self, agent):
        if agent.get_vehicle():
            return agent.get_vehicle()
        else:
            return ""

    def getAgentsOnThisVehicle(self):
        thisAgents = [a for a in self.agents if self.machine_name in self.getAgentV(a) ]
        return thisAgents

    def getAgentIdsOnThisVehicle(self):
        thisAgents = self.getAgentsOnThisVehicle()
        thisAgentIds = [a.card.id for a in thisAgents]
        thisAgentIdsString = json.dumps(thisAgentIds)
        self.showMsg("agent ids on this vehicle:"+thisAgentIdsString)
        return thisAgentIdsString

    def prepFullVehicleReportData(self):
        print("prepFullVehicleReportData...")
        report = []
        try:
            for v in self.vehicles:
                if v.getStatus() == "":
                    vstat = "offline"
                else:
                    vstat = v.getStatus()

                if self.machine_name not in v.getName():
                    vinfo = {
                        "vid": v.getVid(),
                        "vname": v.getName(),
                        "owner": self.user,
                        "status": vstat,
                        "lastseen": v.getLastUpdateTime().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                        "functions": v.getFunctions(),
                        "bids": ",".join(str(v.getBotIds())),
                        "hardware": v.getArch(),
                        "software": v.getOS(),
                        "ip": v.getIP(),
                        "created_at": ""
                    }
                else:
                    vinfo = {
                        "vid": 0,
                        "vname": self.machine_name+":"+self.os_short,
                        "owner": self.user,
                        "status": self.working_state,
                        "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                        "functions": self.functions,
                        "bids": self.getAgentIdsOnThisVehicle(),
                        "hardware": self.processor,
                        "software": self.platform,
                        "ip": self.ip,
                        "created_at": ""
                    }
                report.append(vinfo)
            print("vnames:", [v["vname"] for v in report])
            if (self.machine_name+":"+self.os_short) not in [v["vname"] for v in report]:
                if "Only" not in self.host_role and "Staff" not in self.host_role:
                    # add myself as a vehicle resource too.
                    vinfo = {
                        "vid": 0,
                        "vname": self.machine_name+":"+self.os_short,
                        "owner": self.user,
                        "status": self.working_state,
                        "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                        "functions": self.functions,
                        "bids": self.getBidsOnThisVehicle(),
                        "hardware": self.processor,
                        "software": self.platform,
                        "ip": self.ip,
                        "created_at": ""
                    }

                    report.append(vinfo)
                    print("report:", report)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorPrepFullVReport:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorPrepFullVReport traceback information not available:" + str(e)
            print(ex_stat)

        return report


    def prepVehicleReportData(self, v):
        report = []

        if v:
            vinfo = {
                "vid": v.getVid(),
                "vname": v.getName(),
                "owner": self.user,
                "status": v.getStatus(),
                "lastseen": v.getLastUpdateTime().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                "functions": v.getFunctions(),
                "bids": json.dumps(v.getBotIds()),
                "hardware": v.getArch(),
                "software": v.getOS(),
                "ip": v.getIP(),
                "created_at": ""
            }
        else:
            vinfo = {
                "vid": 0,
                "vname": self.machine_name+":"+self.os_short,
                "owner": self.user,
                "status": self.working_state,
                "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                "functions": self.functions,
                "bids": self.getBidsOnThisVehicle(),
                "hardware": self.processor,
                "software": self.platform,
                "ip": self.ip,
                "created_at": ""
            }
        report.append(vinfo)

        return report


    # this is the interface to the chatting bots, taking message from the running bots and display them on GUI
    async def runAgentsMonitor(self, monitor_msg_queue):
        running = True
        ticks = 0
        while running:
            ticks = ticks + 1
            if ticks > 255:
                ticks = 0

            #ping cloud every 8 second to see whether there is any monitor/control internet. use amazon's sqs
            if ticks % 8 == 0:
                self.showMsg(f"Access Internet Here with Websocket...")

            if ticks % 180 == 0:
                self.showMsg(f"report vehicle status")

                # update vehicles status to local disk, this is done either on platoon or commander
                self.saveVehiclesJsonFile()

                if "Commander" in self.host_role:
                    self.showMsg(f"sending vehicle heartbeat to cloud....")
                    hbInfo = self.stateCapture()
                    # update vehicle info to the chat channel (don't we need to update this to cloud lambda too?)
                    await self.wan_send_heartbeat(hbInfo)

                    # send vehicle status to cloud DB
                    vehicle_report = self.prepFullVehicleReportData()
                    resp = send_report_vehicles_to_cloud(self.session, self.get_auth_token(),
                                                         vehicle_report, self.getWanApiEndpoint())

            if not monitor_msg_queue.empty():
                message = await monitor_msg_queue.get()
                self.showMsg(f"RPA Monitor message: {message}")
                if type(message) != str:
                    print("GUI v")

                monitor_msg_queue.task_done()

            logger.trace("running monitoring Task....", ticks)
            await asyncio.sleep(1)
        print("RPA monitor ended!!!")



    def downloadForFullfillGenECBLabels(self, orders, worklink):
        try:
            for bi, batch in enumerate(orders):
                if batch['file']:
                    print("batch....", batch)
                    print("about to download....", batch['file'])

                    local_file = download_file(self.session, self.my_ecb_data_homepath, batch['dir'] + "/" + batch['file'],
                                               "", self.get_auth_token(),
                                               self.getWanApiEndpoint(), "general")
                    batch['dir'] = os.path.dirname(local_file)
                    orders[bi]['dir'] = os.path.dirname(local_file)
                    worklink['dir'] = os.path.dirname(local_file)


                    print("local file....", local_file)
                    print("local dir:", os.path.dirname(local_file))

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorDownloadForFullfillGenECBLabels:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorDownloadForFullfillGenECBLabels traceback information not available:" + str(e)
            print(ex_stat)


    # do any download if needed by the missions ONLY IF the mission will be run on this computer.
    # otherwise, don't do download and leave this to whichever computer that will run this mission.
    def prepareMissionRunAsServer(self, new_works):
        try:
            if new_works['added_missions'][0]['type'] == "sellFullfill_genECBLabels":
                first_v = next(iter(new_works['task_groups']))
                if self.machine_name in first_v:
                    self.downloadForFullfillGenECBLabels(new_works['added_missions'][0]['config'][1], new_works['task_groups'][first_v]['eastern'][0]['other_works'][0]['config'][1][0])

                print("updated new work:", new_works)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorPrepareMissionRunAsServer:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorPrepareMissionRunAsServer traceback information not available:" + str(e)
            print(ex_stat)

    # note recipient could be a group ID.
    def sendBotChatMessage(self, sender, recipient, text):
        # first find out where the recipient is at (which vehicle) and then, send the message to it.
        if isinstance(recipient, list):
            recipients = recipient
        else:
            recipients = [recipient]
        dtnow = datetime.now()
        date_word = dtnow.isoformat()
        allbids = [b.getBid() for b in self.bots]
        found = None
        for vidx, v in enumerate(self.vehicles):
            if len(recipients) > 0:
                receivers = set(recipients)
                vbots = set(v.getBotIds())

                # Find the intersection
                intersection = receivers.intersection(vbots)

                # Convert intersection back to a list (optional)
                bids_on_this_vehicle = list(intersection)
                if len(bids_on_this_vehicle) > 0:
                    bids_on_this_vehicle_string = ",".join(bids_on_this_vehicle)

                    #now send the message to bots on this vehicle.
                    full_txt = date_word + ">" + str(sender) + ">" + bids_on_this_vehicle_string + ">" + text
                    cmd = {"cmd": "chat", "message": full_txt.decode('latin1')}
                    cmd_str = json.dumps(cmd)
                    if v.getFieldLink()["transport"] and not v.getFieldLink()["transport"].is_closing():
                        v.getFieldLink()["transport"].write(cmd_str.encode('utf8'))
                    # v.getFieldLink()["transport"].get_loop().call_soon(lambda: print("CHAT MSG SENT2..."))

                    # Remove the intersection from the recipients.
                    receivers.difference_update(intersection)

                    # get updated recipients
                    recipients = list(receivers)

        # if there are still recipients not sent, that means these are local bots,
        #self.send_chat_to_local_bot(text)

        if len(recipient) > 0:
            # recipient here could be comma seperated recipient ids.
            receivers = set(recipients)
            vbots = set(allbids)

            # Find the intersection
            intersection = receivers.intersection(vbots)

            # Convert intersection back to a list (optional)
            bids_on_this_vehicle = list(intersection)

            # Chat GUI removed - no longer adding active chat history
            pass

            if len(bids_on_this_vehicle) > 0:
                # now send the message to local bots on this vehicle.
                unfound_bid_string = ",".join(bids_on_this_vehicle)
                self.showMsg(f"Error: Bot[{unfound_bid_string}] not found")


    # note recipient could be a group ID.
    def receiveBotChatMessage(self, msg_text):
        msg_parts = msg_text.split(">")
        sender = msg_parts[1]
        receiver = msg_parts[2]
        if "," in receiver:
            receivers = [int(rs.strip()) for rs in receiver.split(",")]
        else:
            receivers = [int(receiver.strip())]


        # deliver the message for the other bots. - allowed for inter-bot communication.
        if len(receivers) > 0:
            # now route message to everybody.
            # Chat GUI removed - no longer adding network chat history
            pass

    # note recipient could be a group ID.
    def receiveBotLogMessage(self, msg_text):
        msg_json = json.loads(msg_text)

        sender = msg_json["sender"]

        #logger will only be sent to the boss.
        receivers = [0]

        # deliver the message for the other bots. - allowed for inter-bot communication.
        # Chat GUI removed - no longer adding network chat history
        pass


    async def send_file_to_platoon(self, platoon_link, file_type, file_name_full_path):
        if os.path.exists(file_name_full_path) and platoon_link:
            self.showMsg(f"Sending File [{file_name_full_path}] to platoon: "+platoon_link["ip"])
            with open(file_name_full_path, 'rb') as fileTBSent:
                binary_data = fileTBSent.read()
                encoded_data = base64.b64encode(binary_data).decode('utf-8')

                # Embed in JSON
                json_data = json.dumps({"cmd": "reqSendFile", "file_name": file_name_full_path, "file_type": file_type, "file_contents": encoded_data})
                length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                # Send data
                self.showMsg(f"About to send file json with "+str(len(json_data.encode('utf-8')))+ " BYTES!")
                if platoon_link["transport"] and not platoon_link["transport"].is_closing():
                    platoon_link["transport"].write(length_prefix+json_data.encode('utf-8'))
                    # await platoon_link["transport"].drain()
                    asyncio.get_running_loop().call_soon(lambda: print("FILE MSG SENT2PLATOON..."))
                # await xport.drain()

                fileTBSent.close()
        else:
            if not os.path.exists(file_name_full_path):
                self.showMsg(f"ErrorSendFileToPlatoon: File [{file_name_full_path}] not found")
            else:
                self.showMsg(f"ErrorSendFileToPlatoon: TCP link doesn't exist")


    def send_json_to_platoon(self, platoon_link, json_data):
        if json_data and platoon_link:
            json_string = json.dumps(json_data)
            if len(json_string) < 128:
                logger.debug(f"Sending JSON Data to platoon " + platoon_link["ip"] + "::" + json_string, "sendLAN",
                     self)
            else:
                logger.debug(f"Sending JSON Data to platoon " + platoon_link["ip"] + ":: ..." + json_string[-127:], "sendLAN",
                     self)
            encoded_json_string = json_string.encode('utf-8')
            length_prefix = len(encoded_json_string).to_bytes(4, byteorder='big')
            # Send data
            if platoon_link["transport"] and not platoon_link["transport"].is_closing():
                platoon_link["transport"].write(length_prefix+encoded_json_string)
                # await platoon_link["transport"].drain()
        else:
            if json_data == None:
                logger.debug(f"ErrorSendJsonToPlatoon: JSON empty", "sendLAN", self)
            else:
                logger.debug(f"ErrorSendJsonToPlatoon: TCP link doesn't exist", "sendLAN", self)


    async def send_json_to_commander(self, commander_link, json_data):
        if json_data and commander_link:
            json_string = json.dumps(json_data)
            if len(json_string) < 128:
                logger.debug(f"Sending JSON Data to commander ::" + json.dumps(json_data), "sendLAN", self)
            else:
                logger.debug(f"Sending JSON Data to commander " + commander_link["ip"] + ":: ..." + json_string[-127:], "sendLAN",
                     self)
            encoded_json_string = json_string.encode('utf-8')
            length_prefix = len(encoded_json_string).to_bytes(4, byteorder='big')
            # Send data
            if commander_link and not commander_link.is_closing():
                commander_link.write(length_prefix+encoded_json_string)
                # await commander_link.drain()
                asyncio.get_running_loop().call_soon(lambda: print("JSON MSG SENT2COMMANDER..."))

        else:
            if json_data == None:
                logger.debug(f"ErrorSendJsonToCommander: JSON empty", "sendLAN", self)
            else:
                logger.debug(f"ErrorSendJsonToCommander: TCP link doesn't exist", "sendLAN", self)

    async def send_ads_profile_to_commander(self, commander_link, file_type, file_name_full_path):
        if os.path.exists(file_name_full_path) and commander_link:
            logger.debug(f"Sending File [{file_name_full_path}] to commander: " + self.commanderIP, "sendLAN", self)
            with open(file_name_full_path, 'rb') as fileTBSent:
                binary_data = fileTBSent.read()
                encoded_data = base64.b64encode(binary_data).decode('utf-8')

                # Embed in JSON
                json_data = json.dumps({"type": "botsADSProfilesUpdate", "file_name": file_name_full_path, "file_type": file_type,
                                        "file_contents": encoded_data})
                length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                # Send data
                if commander_link and not commander_link.is_closing():
                    commander_link.write(length_prefix + json_data.encode('utf-8'))
                    await commander_link.drain()
                # asyncio.get_running_loop().call_soon(lambda: print("FILE SENT2COMMANDER..."))

                # await xport.drain()

                fileTBSent.close()
        else:
            if not os.path.exists(file_name_full_path):
                self.showMsg(f"ErrorSendFileToCommander: File [{file_name_full_path}] not found")
            else:
                self.showMsg(f" : TCP link doesn't exist")

    def batch_send_ads_profiles_to_commander(self, commander_link, file_type, file_paths):
        try:
            if not commander_link:
                logger.debug("ErrorSendFilesToCommander: TCP link doesn't exist", "sendLAN", self)
                return

            profiles = []
            for file_name_full_path in file_paths:
                if os.path.exists(file_name_full_path):
                    logger.debug(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}", "sendLAN", self)
                    with open(file_name_full_path, 'rb') as fileTBSent:
                        binary_data = fileTBSent.read()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        # Embed in JSON
                        file_timestamp = os.path.getmtime(file_name_full_path)

                        profiles.append({
                            "file_name": file_name_full_path,
                            "file_type": file_type,
                            "timestamp": file_timestamp,  # Include file timestamp
                            "file_contents": encoded_data
                        })

                else:
                    self.showMsg(f"ErrorSendFileToCommander: File [{file_name_full_path}] not found")

            # Send data
            json_data = json.dumps({
                "type": "botsADSProfilesBatchUpdate",
                "ip": self.ip,
                "profiles": profiles
            })
            length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
            if len(json_data) < 128:
                print("About to send botsADSProfilesBatchUpdate to commander: "+json_data)
            else:
                print("About to send botsADSProfilesBatchUpdate to commander: ..." + json_data[-127:])

            if commander_link and not commander_link.is_closing():
                commander_link.write(length_prefix + json_data.encode('utf-8'))
                asyncio.get_running_loop().call_soon(lambda: print("ADS FILES SENT2COMMANDER..."))
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSendingBatchProfilesToCommander:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSendingBatchProfilesToCommander traceback information not available:" + str(e)


    def batch_send_ads_profiles_to_platoon(self, platoon_link, file_type, file_paths):
        try:
            if not platoon_link:
                logger.debug("ErrorSendFilesToCommander: TCP link doesn't exist", "sendLAN", self)
                return

            print("# files", len(file_paths))
            profiles = []
            for file_name_full_path in file_paths:
                print("checking", file_name_full_path)
                if os.path.exists(file_name_full_path):
                    print("exists!")
                    # logger.debug(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}", "gatherFingerPrints", self)
                    # print(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}")
                    with open(file_name_full_path, 'rb') as fileTBSent:
                        binary_data = fileTBSent.read()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        # Embed in JSON
                        file_timestamp = os.path.getmtime(file_name_full_path)

                        profiles.append({
                            "file_name": file_name_full_path,
                            "file_type": file_type,
                            "timestamp": file_timestamp,  # Include file timestamp
                            "file_contents": encoded_data
                        })

                else:
                    logger.debug(f"Warning: ADS Profile [{file_name_full_path}] not found", "sendLAN", self)
                    print(f"Warning: ADS Profile [{file_name_full_path}] not found")

            # Send data
            print("profiles ready")
            json_data = json.dumps({
                "cmd": "botsADSProfilesBatchUpdate",
                "ip": self.ip,
                "profiles": profiles
            })

            if len(json_data) < 128:
                print("About to send botsADSProfilesBatchUpdate to platoon: " + json_data)
            else:
                print("About to send botsADSProfilesBatchUpdate to platoon: ..." + json_data[-127:])


            length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
            if platoon_link["transport"] and not platoon_link["transport"].is_closing():
                platoon_link["transport"].write(length_prefix + json_data.encode('utf-8'))
            # asyncio.get_running_loop().call_soon(lambda: print("ADS FILES SENT2PLATOON..."))
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSendingBatchProfilesToCommander:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSendingBatchProfilesToCommander traceback information not available:" + str(e)



    def send_mission_result_files_to_commander(self, commander_link, mid, file_type, file_name_full_paths):
        try:
            validFiles = [fn for fn in file_name_full_paths if os.path.exists(fn)]

            nFiles = len(validFiles)
            for fidx, file_name_full_path in enumerate(validFiles):
                if os.path.exists(file_name_full_path) and commander_link:
                    self.showMsg(f"Sending File [{file_name_full_path}] to commander: " + self.commanderIP)
                    with open(file_name_full_path, 'rb') as fileTBSent:
                        binary_data = fileTBSent.read()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        # Embed in JSON
                        json_data = json.dumps({"type": "missionResultFile", "mid": mid, "nFiles": nFiles, "fidx": fidx, "file_name": file_name_full_path, "file_type": file_type,
                                                "file_contents": encoded_data})
                        length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                        # Send data
                        if commander_link and not commander_link.is_closing():
                            commander_link.write(length_prefix + json_data.encode('utf-8'))
                        # asyncio.get_running_loop().call_soon(lambda: print("RESULT FILES SENT2COMMANDER..."))
                        # await xport.drain()

                        fileTBSent.close()
                else:
                    if not os.path.exists(file_name_full_path):
                        self.showMsg(f"ErrorSendMissionResultsFilesToCommander: File [{file_name_full_path}] not found")
                    else:
                        self.showMsg(f"ErrorSendMissionResultsFilesToCommander: TCP link doesn't exist")

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSendMissionResultsFilesToCommander:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSendMissionResultsFilesToCommander: traceback information not available:" + str(e)
            logger.debug(ex_stat)


    def set_wan_connected(self, wan_stat):
        self.wan_connected = wan_stat

    def set_websocket(self, ws):
        self.websocket = ws

    def get_wan_connected(self):
        return self.wan_connected

    def get_websocket(self):
        return self.websocket

    def get_wan_msg_queue(self):
        return self.wan_chat_msg_queue

    def set_wan_msg_subscribed(self, ss):
        self.wan_msg_subscribed = ss

    def get_wan_msg_subscribed(self):
        return self.wan_msg_subscribed

    def set_staff_officer_online(self, ol):
        self.staff_officer_on_line = ol

    def get_staff_officer_online(self):
        return self.staff_officer_on_line

    # this is an empty task
    async def wait_forever(self):
        await asyncio.Event().wait()  # This will wait indefinitely

    # Serve as commander - listen for messages from platoons
    async def serveCommander(self, msgQueue):
        """Listen for messages from platoons when this instance is acting as commander"""
        self.showMsg("starting serveCommander")

        while True:
            logger.trace("listening to platoons as commander" + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

            if not msgQueue.empty():
                try:
                    # Process all available messages in the queue
                    while not msgQueue.empty():
                        net_message = await msgQueue.get()
                        print("received net message from platoon:", type(net_message), net_message)
                        if isinstance(net_message, str):
                            if len(net_message) > 256:
                                mlen = 256
                            else:
                                mlen = len(net_message)
                            self.showMsg(
                                "received queued msg from platoon..... [" + str(msgQueue.qsize()) + "]" + net_message[:mlen])
                except Exception as e:
                    logger.error(f"[serveCommander] Error processing message: {e}")
                    self.showMsg(f"Error processing platoon message: {str(e)}")

            await asyncio.sleep(0.1)  # Small delay to prevent busy waiting

    async def wan_ping(self):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            ping_msg = {
                "chatID": commander_chat_id,
                "sender": self.chat_id,
                "receiver": commander_chat_id,
                "type": "ping",
                "contents": json.dumps({"msg": "hello?"}).replace('"', '\\"'),
                "parameters": json.dumps({})
            }

            self.wan_sub_task = asyncio.create_task(wanSendMessage(ping_msg, self))

    async def wan_self_ping(self):
        if self.host_role == "Staff Officer":
            self_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
        else:
            self_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
        print("Self:", self_chat_id)
        ping_msg = {
            "chatID": self_chat_id,
            "sender": self.chat_id,
            "receiver": self_chat_id,
            "type": "loopback",
            "contents": json.dumps({"msg": "hello?"}).replace('"', '\\"'),
            "parameters": json.dumps({})
        }

        self.wan_sub_task = asyncio.create_task(wanSendMessage(ping_msg, self))


    async def wan_pong(self):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            pong_msg = {
                # "chatID": sa_chat_id,
                "chatID": self.chat_id,
                "sender": "Commander",
                "receiver": sa_chat_id,
                "type": "pong",
                "contents": json.dumps({"type": "cmd", "cmd": "pong"}).replace('"', '\\"'),
                "parameters": json.dumps({})
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(pong_msg, self))

    def wan_send_log(self, logmsg):
        if self.host_role != "Staff Officer":
            so_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            contents = {"msg": logmsg}
            parameters = {}
            req_msg = {
                "chatID": so_chat_id,
                "sender": "Commander",
                "receiver": self.user,
                "type": "logs",
                "contents": logmsg.replace('"', '\\"'),
                # "contents": json.dumps({"msg": logmsg}).replace('"', '\\"'),
                "parameters": json.dumps(parameters)
            }
            wanSendMessage(req_msg, self)

    async def wan_send_log8(self, logmsg):
        if self.host_role != "Staff Officer":
            so_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            req_msg = {
                "chatID": so_chat_id,
                "sender": "Commander",
                "receiver": self.user,
                "type": "logs",
                "contents": json.dumps({"msg": logmsg}).replace('"', '\\"'),
                "parameters": json.dumps({})
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))


    async def wan_request_log(self):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            req_msg = {
                "chatID": self.chat_id,
                "sender": "",
                "receiver": commander_chat_id,
                "type": "request",
                "contents": json.dumps({"type": "cmd", "cmd": "start log", "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))

    def wan_stop_log(self):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            log_msg = {
                "chatID": sa_chat_id,
                "sender": self.chat_id,
                "receiver": sa_chat_id,
                "type": "command",
                "contents": json.dumps({"type": "cmd", "cmd": "stop log", "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            wanSendMessage(log_msg, self)

    async def wan_stop_log(self):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            req_msg = {
                "chatID": commander_chat_id,
                "sender": "",
                "receiver": commander_chat_id,
                "type": "command",
                "contents": json.dumps({"type": "cmd", "cmd": "stop log", "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))

    def wan_rpa_ctrl(self, cmd):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            req_msg = {
                "chatID": self.chat_id,
                "sender": "",
                "receiver": commander_chat_id,
                "type": "command",
                "contents": json.dumps({"cmd": cmd, "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage(req_msg, self))

    async def wan_send_heartbeat(self, heartbeatInfo):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            req_msg = {
                "chatID": sa_chat_id,
                "sender": self.user.replace("@", "_").replace(".", "_") + "_Commander",
                "receiver": sa_chat_id,
                "type": "heartbeat",
                "contents": json.dumps(heartbeatInfo).replace('"', '\\"'),
                "parameters": json.dumps({}),
            }
            # self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self.get_auth_token(), self.websocket))
            await wanSendMessage8(req_msg, self)


    def send_heartbeat(self):
        if "Commander" in self.host_role:
            print("sending wan heartbeat")
            asyncio.ensure_future(self.wan_send_heartbeat())


    async def wan_chat_test(self):
        """Non-blocking WAN chat test - converted to async to avoid UI freeze"""
        if self.host_role == "Staff Officer":
            asyncio.ensure_future(self.wan_ping())
            await asyncio.sleep(1.0)  # Non-blocking wait
            asyncio.ensure_future(self.wan_self_ping())
        elif self.host_role != "Platoon":
            asyncio.ensure_future(self.wan_pong())
            # asyncio.ensure_future(self.wan_c_send_chat("got it!!!"))
            # await asyncio.sleep(1.0)
            # asyncio.ensure_future(self.wan_self_ping())
            # self.think_about_a_reponse("[abc]'hello?'")


    async def wan_sa_send_chat(self, msg):
        try:
            if self.host_role == "Staff Officer":
                commander_chat_id = self.user.split("@")[0] + "_Commander"
                req_msg = {
                    "chatID": commander_chat_id,
                    "sender": self.chat_id,
                    "receiver": commander_chat_id,
                    "type": "chat",
                    "contents": msg,
                    "parameters": json.dumps({})
                }

                self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorWanSaSendChat:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorWanSaSendChat: traceback information not available:" + str(e)
            logger.debug(ex_stat)


    def sa_send_chat(self, msg):
        asyncio.ensure_future(self.wan_sa_send_chat(msg))


    async def wan_c_send_chat(self, msg):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.split("@")[0] + "_StaffOfficer"
            req_msg = {
                "chatID": sa_chat_id,
                "sender": self.chat_id,
                "receiver": sa_chat_id,
                "type": "chat",
                "contents": msg,
                "parameters": json.dumps({})
            }

            self.wan_sub_task = asyncio.create_task(wanSendMessage(req_msg, self))


    def c_send_chat(self, msg):
        asyncio.ensure_future(self.wan_c_send_chat(msg))

        current_time = datetime.now(timezone.utc)
        # Convert to the required AWSDateTime format
        aws_datetime_string = current_time.isoformat()



    # from ip find vehicle, and update its status, and
    def updateVehicleStatusToRunningIdle(self, ip):
        found_vehicles = [v for v in self.vehicles if v.getIP() == ip]
        if found_vehicles:
            found_vehicle = found_vehicles[0]
            found_vehicle.setStatus("running_idle")       # this vehicle is ready to take more work if needed.
            vehicle_report = self.prepVehicleReportData(found_vehicle)
            logger.debug("vehicle status report"+json.dumps(vehicle_report))
            if not self.general_settings.is_test_mode():
                resp = send_report_vehicles_to_cloud(self.session, self.get_auth_token(),
                                                 vehicle_report, self.getWanApiEndpoint())
            self.saveVehiclesJsonFile()

    def updateVehicles(self, vehicles):
        vjs=[self.prepVehicleReportData(v) for v in vehicles]

        resp = send_update_vehicles_request_to_cloud(self.session, vjs, self.get_auth_token(), self.getWanApiEndpoint())
        # for now simply update json file, can put in local db if needed in future.... sc-01/06/2025
        self.saveVehiclesJsonFile()


    # capture current state and send in heartbeat signal to the cloud
    def stateCapture(self):
        current_time = datetime.now()
        for v in self.vehicles:
            current_time = datetime.now()
            if (current_time - v.getLastUpdateTime()).total_seconds() > 480:    # 8 minutes no contact is considered "offline"
                v.setStatus("offline")


        stateInfo = {"vehiclesInfo": [{"vehicles_status": v.getStatus(), "vname": v.getName()} for v in self.vehicles]}

        # we'll capture these info:
        # all vehicle status running_idle/running_working/offline
        # all the mission running status.??? may be this is not the good place for that, we'd have to ping vehicles
        # plus, don't they update periodically already?


        return stateInfo

    def vRunnable(self, vehicle):
        print("vname", vehicle.getName(), self.machine_name, self.host_role)
        runnable = True
        if self.machine_name in vehicle.getName() and self.host_role == "Commander Only":
            runnable = False
        return runnable


    def merge_dicts(self, dict1, dict2):
        merged_dict = {}
        for key in dict1.keys():
            merged_dict[key] = dict1[key] + dict2.get(key, [])
        return merged_dict



    def encrypt_string(self, key: bytes, plaintext: str) -> str:
        """Encrypt the given plaintext using the derived key."""
        fernet = Fernet(key)
        encrypted = fernet.encrypt(plaintext.encode())  # Encrypt the plaintext
        return encrypted.decode()  # Return as a string

    def decrypt_string(self, key: bytes, encrypted_text: str) -> str:
        """Decrypt the given encrypted text using the derived key."""
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_text.encode())  # Decrypt the text
        return decrypted.decode()  # Return as a string





    def isPlatoon(self):
        return (self.machine_role == "Platoon")



    def isValidAddr(self, addr):
        val = True

        if "Any,Any" in addr or not addr.split("\n")[0].strip():
            val = False

        return val


    def vehiclePing(self, vehicle):
        self.sendToVehicleByVip(vehicle.getIP())


print(TimeUtil.formatted_now_with_ms() + " load MainGui all finished...")