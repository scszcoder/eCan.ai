#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Settings Manager - Data and Business Logic Handler
Handles application settings and configuration without GUI components
"""

import sys
import platform
import os
import time
import json
import threading
from typing import List, Dict, Any, Optional
from utils.logger_helper import logger_helper as logger
from gui.utils.hardware_detector import get_hardware_detector

# Note: Hardware detection related imports have been moved to shared hardware detector
# Platform-specific imports are now handled by gui.utils.hardware_detector

def ensure_spooler_running():
    """Ensure printing backend is running on the current platform.

    Now uses shared hardware detector implementation, maintaining backward compatibility
    """
    # For backward compatibility, keep this function but use shared detector internally
    # Shared detector will automatically handle print services when needed
    pass


def ensure_cups_running():
    """Ensure printing backend is running on the current platform.

    Now uses shared hardware detector implementation, maintaining backward compatibility
    """
    # For backward compatibility, keep this function but use shared detector internally
    # Shared detector will automatically handle CUPS services when needed
    pass


def win_list_printers(server: str | None = None, level: int = 2):
    """
    Enumerate printers using shared hardware detector.
    Maintains backward compatible interface
    """
    try:
        # Use shared hardware detector
        detector = get_hardware_detector()
        return detector.detect_printers()
    except Exception as e:
        logger.error(f"Error listing printers via shared detector: {e}")
        return []


def mac_list_printers():
    """
    List macOS printers using shared hardware detector.
    Maintains backward compatible interface
    """
    try:
        # Use shared hardware detector
        detector = get_hardware_detector()
        return detector.detect_printers()
    except Exception as e:
        logger.error(f"Error listing macOS printers via shared detector: {e}")
        return []

def _run_wifi_command(command_type: str) -> Optional[str]:
    """
    Run WiFi command using shared hardware detector.
    Maintains backward compatible interface
    """
    try:
        # Use shared hardware detector
        detector = get_hardware_detector()
        return detector._run_wifi_command(command_type)
    except Exception as e:
        logger.error(f"Error running WiFi command via shared detector: {e}")
        return None

def get_default_wifi_ssid() -> Optional[str]:
    """
    Get the SSID of the currently connected WiFi network using shared hardware detector.
    Maintains backward compatible interface
    """
    try:
        # Use shared hardware detector
        detector = get_hardware_detector()
        return detector.get_current_wifi()
    except Exception as e:
        logger.error(f"Error getting current WiFi SSID via shared detector: {e}")
        return None

class SettingsManager:
    """
    Settings Manager class that handles application settings and configuration
    without GUI components. Now uses general_settings as the primary data source
    to eliminate duplicate attributes.
    """

    def __init__(self, parent):
        """
        Initialize SettingsManager

        Args:
            parent: Reference to parent application
        """
        self.parent = parent

        # UI-specific settings (not duplicated in general_settings)
        self.commander_run = False
        self.overcapcity_warning = True
        self.overcapcity_force = True
        self.num_vehicles = 0

        # Hardware detection cache (for performance)
        self.printers = []
        self.wifi_list = []

        # Initialize hardware detection asynchronously to avoid blocking main thread
        self._start_async_hardware_detection()

    def get_commander_run(self) -> bool:
        """Get commander self-run setting"""
        return self.commander_run

    def set_commander_run(self, value: bool):
        """Set commander self-run setting"""
        self.commander_run = value

    def get_overcapcity_warning(self) -> bool:
        """Get over-capacity warning setting"""
        return self.overcapcity_warning

    def set_overcapcity_warning(self, value: bool):
        """Set over-capacity warning setting"""
        self.overcapcity_warning = value

    def get_overcapcity_force(self) -> bool:
        """Get over-capacity force setting"""
        return self.overcapcity_force

    def set_overcapcity_force(self, value: bool):
        """Set over-capacity force setting"""
        self.overcapcity_force = value

    def get_auto_schedule_mode(self) -> bool:
        """Get auto schedule mode setting (maps to general_settings.schedule_mode)"""
        if hasattr(self.parent, 'config_manager'):
            return self.parent.config_manager.general_settings.is_auto_mode()
        return False

    def set_auto_schedule_mode(self, value: bool):
        """Set auto schedule mode setting (maps to general_settings.schedule_mode)"""
        if hasattr(self.parent, 'config_manager'):
            mode = "auto" if value else "manual"
            self.parent.config_manager.general_settings.schedule_mode = mode
            self.parent.config_manager.general_settings.save()

    def get_browser_path(self) -> str:
        """Get browser executable path (maps to general_settings.default_webdriver_path)"""
        if hasattr(self.parent, 'config_manager'):
            return self.parent.config_manager.general_settings.default_webdriver_path
        return ""

    def set_browser_path(self, path: str):
        """Set browser executable path (maps to general_settings.default_webdriver_path)"""
        if hasattr(self.parent, 'config_manager'):
            self.parent.config_manager.general_settings.default_webdriver_path = path
            self.parent.config_manager.general_settings.save()

    def get_num_vehicles(self) -> int:
        """Get number of vehicles setting"""
        return self.num_vehicles

    def set_num_vehicles(self, num: int):
        """Set number of vehicles setting"""
        try:
            self.num_vehicles = int(num)
        except (ValueError, TypeError):
            logger.warning(f"Invalid number of vehicles: {num}")
            self.num_vehicles = 0

    def get_default_printer(self) -> str:
        """Get default printer setting (from general_settings)"""
        if hasattr(self.parent, 'config_manager'):
            return self.parent.config_manager.general_settings.default_printer
        return ""

    def set_default_printer(self, printer: str):
        """Set default printer setting (to general_settings)"""
        if hasattr(self.parent, 'config_manager'):
            self.parent.config_manager.general_settings.default_printer = printer
            self.parent.config_manager.general_settings.save()

    def get_default_wifi(self) -> str:
        """Get default WiFi setting (from general_settings)"""
        if hasattr(self.parent, 'config_manager'):
            return self.parent.config_manager.general_settings.default_wifi
        return ""

    def set_default_wifi(self, wifi: str):
        """Set default WiFi setting (to general_settings)"""
        if hasattr(self.parent, 'config_manager'):
            self.parent.config_manager.general_settings.default_wifi = wifi
            self.parent.config_manager.general_settings.save()

    def get_printers(self) -> List[Any]:
        """Get list of available printers"""
        return self.printers.copy()

    def get_wifi_networks(self) -> List[str]:
        """Get list of available WiFi networks"""
        return self.wifi_list.copy()

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all current settings as a dictionary (unified with general_settings)"""
        return {
            # UI-specific settings
            'commander_run': self.commander_run,
            'overcapcity_warning': self.overcapcity_warning,
            'overcapcity_force': self.overcapcity_force,
            'num_vehicles': self.num_vehicles,

            # Settings from general_settings (unified)
            'auto_schedule_mode': self.get_auto_schedule_mode(),
            'browser_path': self.get_browser_path(),
            'default_printer': self.get_default_printer(),
            'default_wifi': self.get_default_wifi(),

            # Hardware detection results
            'available_printers': self.get_printer_names(),
            'available_wifi_networks': self.wifi_list
        }

    def set_all_settings(self, settings: Dict[str, Any]):
        """Set all settings from a dictionary (unified with general_settings)"""
        try:
            # UI-specific settings
            if 'commander_run' in settings:
                self.set_commander_run(settings['commander_run'])
            if 'overcapcity_warning' in settings:
                self.set_overcapcity_warning(settings['overcapcity_warning'])
            if 'overcapcity_force' in settings:
                self.set_overcapcity_force(settings['overcapcity_force'])
            if 'num_vehicles' in settings:
                self.set_num_vehicles(settings['num_vehicles'])

            # Settings that map to general_settings (unified)
            if 'auto_schedule_mode' in settings:
                self.set_auto_schedule_mode(settings['auto_schedule_mode'])
            if 'browser_path' in settings:
                self.set_browser_path(settings['browser_path'])
            if 'default_printer' in settings:
                self.set_default_printer(settings['default_printer'])
            if 'default_wifi' in settings:
                self.set_default_wifi(settings['default_wifi'])

            logger.info("All settings updated successfully (unified with general_settings)")

        except Exception as e:
            logger.error(f"Error setting all settings: {e}")

    def save_settings(self) -> bool:
        """
        Save current settings to parent application (unified with general_settings)

        Returns:
            True if settings saved successfully, False otherwise
        """
        try:
            # Settings are now automatically saved through general_settings
            # when using set_* methods, so we just need to ensure parent settings are updated

            if hasattr(self.parent, 'set_schedule_mode'):
                schedule_mode = "auto" if self.get_auto_schedule_mode() else "manual"
                self.parent.set_schedule_mode(schedule_mode)

            if hasattr(self.parent, 'set_default_wifi'):
                self.parent.set_default_wifi(self.get_default_wifi())

            if hasattr(self.parent, 'set_default_printer'):
                self.parent.set_default_printer(self.get_default_printer())

            if hasattr(self.parent, 'saveSettings'):
                self.parent.saveSettings()

            # Ensure general_settings are saved
            if hasattr(self.parent, 'config_manager'):
                self.parent.config_manager.general_settings.save()

            logger.info("Settings saved successfully (unified with general_settings)")
            return True

        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False

    def load_settings(self) -> bool:
        """
        Load settings from parent application (unified with general_settings)

        Returns:
            True if settings loaded successfully, False otherwise
        """
        try:
            # Settings are now loaded automatically from general_settings
            # No need to manually sync since we access them directly through get_* methods

            logger.info("Settings loaded successfully (unified with general_settings)")
            return True

        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            return False

    def list_printers(self) -> bool:
        """
        Detect and list available printers using shared hardware detector

        Returns:
            True if printers detected successfully, False otherwise
        """
        try:
            # Use shared hardware detector
            detector = get_hardware_detector()
            self.printers = detector.detect_printers()

            # Extract printer names safely for logging
            printer_names = self.get_printer_names()
            logger.info(f"Printers detected: {printer_names}")
            return True

        except Exception as e:
            logger.error(f"Error listing printers: {e}")
            self.printers = []
            return False

    def get_printer_names(self) -> List[str]:
        """Get list of printer names as strings"""
        printer_names = []
        for p in self.printers:
            if isinstance(p, dict) and 'pPrinterName' in p:
                printer_names.append(p['pPrinterName'])  # Windows dictionary format
            elif isinstance(p, (list, tuple)) and len(p) > 2:
                printer_names.append(p[2])  # Standard tuple format
            elif isinstance(p, (list, tuple)) and len(p) > 0:
                printer_names.append(str(p[0]))  # Fallback to first element
            else:
                printer_names.append(str(p))  # Fallback to string representation
        return printer_names

    def list_wifi_networks(self) -> bool:
        """
        Detect and list available WiFi networks using shared hardware detector.
        This method now triggers a background scan to avoid blocking the UI.

        Returns:
            True if a scan was started or data already available, False otherwise
        """
        try:
            detector = get_hardware_detector()

            def _on_complete(ssids):
                try:
                    self.wifi_list = ssids or []
                    logger.info(f"WiFi scan completed (background): {len(self.wifi_list)} networks")
                except Exception as e:
                    logger.warning(f"Failed to handle WiFi scan completion: {e}")

            started = detector.start_wifi_scan_background(on_complete=_on_complete)
            if started:
                logger.debug("Started background WiFi scan")
                # Return True to indicate the scan is in progress
                return True
            else:
                # Scan already running; return whether we have cached data
                logger.debug("Background WiFi scan already in progress")
                return len(self.wifi_list) > 0

        except Exception as e:
            logger.error(f"An unexpected error occurred while listing WiFi networks: {e}")
            self.wifi_list = []
            return False

    def validate_settings(self) -> Dict[str, Any]:
        """
        Validate current settings

        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': []
        }

        # Validate browser path (from general_settings)
        browser_path = self.get_browser_path()
        if browser_path and not os.path.exists(browser_path):
            validation_results['valid'] = False
            validation_results['errors'].append(f"Browser path does not exist: {browser_path}")

        # Validate number of vehicles
        if self.num_vehicles < 0:
            validation_results['valid'] = False
            validation_results['errors'].append("Number of vehicles cannot be negative")

        # Validate default printer (from general_settings)
        default_printer = self.get_default_printer()
        if default_printer and default_printer not in self.get_printer_names():
            validation_results['warnings'].append(f"Default printer not found in available printers: {default_printer}")

        # Validate default WiFi (from general_settings)
        default_wifi = self.get_default_wifi()
        if default_wifi and default_wifi not in self.wifi_list:
            validation_results['warnings'].append(f"Default WiFi not found in available networks: {default_wifi}")

        return validation_results

    def export_settings(self, filepath: str) -> bool:
        """
        Export settings to JSON file

        Args:
            filepath: Path to save JSON file

        Returns:
            True if exported successfully, False otherwise
        """
        try:
            export_data = {
                'export_timestamp': time.time(),
                'settings': self.get_all_settings(),
                'validation': self.validate_settings()
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Settings exported to: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Error exporting settings: {e}")
            return False

    def import_settings(self, filepath: str) -> bool:
        """
        Import settings from JSON file

        Args:
            filepath: Path to load JSON file from

        Returns:
            True if imported successfully, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                import_data = json.load(f)

            if 'settings' in import_data:
                self.set_all_settings(import_data['settings'])
                logger.info(f"Settings imported from: {filepath}")
                return True
            else:
                logger.error("Invalid settings file format")
                return False

        except Exception as e:
            logger.error(f"Error importing settings: {e}")
            return False

    def reset_to_defaults(self):
        """Reset all settings to default values (unified with general_settings)"""
        try:
            # Reset UI-specific settings
            self.commander_run = False
            self.overcapcity_warning = True
            self.overcapcity_force = True
            self.num_vehicles = 0

            # Reset settings in general_settings
            self.set_auto_schedule_mode(False)
            self.set_browser_path("")
            self.set_default_printer("")
            self.set_default_wifi("")

            logger.info("Settings reset to defaults (unified with general_settings)")

        except Exception as e:
            logger.error(f"Error resetting settings: {e}")

    def get_hardware_info(self) -> Dict[str, Any]:
        """Get comprehensive hardware information"""
        try:
            hardware_info = {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'available_printers': self.get_printer_names(),
                'available_wifi_networks': self.wifi_list,
                'default_printer': self.get_default_printer(),
                'default_wifi': self.get_default_wifi()
            }

            # Add platform-specific information
            if platform.system() == 'Windows':
                hardware_info['windows_version'] = platform.win32_ver()
            elif platform.system() == 'Darwin':
                hardware_info['macos_version'] = platform.mac_ver()
            elif platform.system() == 'Linux':
                hardware_info['linux_distribution'] = platform.linux_distribution()

            return hardware_info

        except Exception as e:
            logger.error(f"Error getting hardware info: {e}")
            return {}

    def _start_async_hardware_detection(self):
        """Start asynchronous hardware detection to avoid blocking main thread"""
        def hardware_detection_worker():
            """Worker function for hardware detection"""
            try:
                logger.info("Starting asynchronous hardware detection...")
                start_time = time.time()

                # Detect hardware in background with timeout protection
                try:
                    # Trigger background WiFi scan; do not block here
                    self.list_wifi_networks()
                    logger.debug("WiFi networks detection started (background)")
                except Exception as e:
                    logger.warning(f"WiFi detection failed in async mode: {e}")

                try:
                    self.list_printers()
                    logger.debug("Printer detection completed")
                except Exception as e:
                    logger.warning(f"Printer detection failed in async mode: {e}")

                # Auto-configure hardware settings in general_settings if not already set
                if hasattr(self.parent, 'config_manager'):
                    try:
                        general_settings = self.parent.config_manager.general_settings
                        settings_changed = False

                        # Always update WiFi to current connected WiFi
                        try:
                            current_wifi = get_default_wifi_ssid()
                            if current_wifi:
                                if general_settings.default_wifi != current_wifi:
                                    old_wifi = general_settings.default_wifi
                                    general_settings.default_wifi = current_wifi
                                    settings_changed = True
                                    logger.info(f"Updated default WiFi: '{old_wifi}' -> '{current_wifi}'")
                            else:
                                logger.debug("No current WiFi detected")
                        except Exception as e:
                            logger.warning(f"Failed to update WiFi: {e}")

                        # Always update printer to first detected printer
                        try:
                            printer_names = self.get_printer_names()
                            if printer_names:
                                first_printer = printer_names[0]
                                if general_settings.default_printer != first_printer:
                                    old_printer = general_settings.default_printer
                                    general_settings.default_printer = first_printer
                                    settings_changed = True
                                    logger.info(f"Updated default printer: '{old_printer}' -> '{first_printer}'")
                            else:
                                logger.debug("No printers detected")
                        except Exception as e:
                            logger.warning(f"Failed to update printer: {e}")

                        # Save settings if any changes were made
                        if settings_changed:
                            try:
                                general_settings.save()
                                logger.info("Hardware settings auto-configured and saved")
                            except Exception as e:
                                logger.error(f"Failed to save hardware settings: {e}")

                    except Exception as e:
                        logger.error(f"Error accessing config manager in async detection: {e}")

                detection_time = time.time() - start_time
                logger.info(f"Asynchronous hardware detection completed successfully in {detection_time:.2f}s")

            except Exception as e:
                logger.error(f"Critical error in asynchronous hardware detection: {e}")
                import traceback
                logger.debug(f"Hardware detection error traceback: {traceback.format_exc()}")

        # Start hardware detection in a daemon thread
        try:
            hardware_thread = threading.Thread(
                target=hardware_detection_worker,
                name="HardwareDetection",
                daemon=True
            )
            hardware_thread.start()
            logger.info("Hardware detection thread started in background")
        except Exception as e:
            logger.error(f"Failed to start hardware detection thread: {e}")
            # Fallback to synchronous detection if thread creation fails
            logger.warning("Falling back to synchronous hardware detection")
            try:
                self.list_wifi_networks()
                self.list_printers()
            except Exception as fallback_e:
                logger.error(f"Fallback hardware detection also failed: {fallback_e}")

    def cleanup(self):
        """Clean up resources"""
        try:
            # Clear lists to free memory
            self.printers.clear()
            self.wifi_list.clear()
            logger.info("SettingsManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
