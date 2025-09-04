#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Settings Manager - Data and Business Logic Handler
Handles application settings and configuration without GUI components
"""

import sys
import subprocess
import re
import time
import traceback
import platform
import os
from typing import List, Dict, Any, Optional
from utils.logger_helper import logger_helper as logger

# Platform-specific imports
if sys.platform == "win32":
    import win32print
    import pywintypes
    import win32serviceutil
else:
    win32print = None
    pywintypes = None
    win32serviceutil = None


def ensure_spooler_running():
    """Ensure printing backend is running on the current platform.

    - Windows: ensure Spooler service is running
    - Others: no-op
    """
    if sys.platform == "win32" and win32serviceutil is not None:
        try:
            status = win32serviceutil.QueryServiceStatus("Spooler")[1]
            if status != 4:
                win32serviceutil.StartService("Spooler")
                for _ in range(10):
                    time.sleep(0.5)
                    if win32serviceutil.QueryServiceStatus("Spooler")[1] == 4:
                        break
        except Exception:
            logger.error("Error ensuring spooler running: " + traceback.format_exc())
            pass
    else:
        return


def ensure_cups_running():
    """Ensure printing backend is running on the current platform.

    - macOS: ensure CUPS scheduler is running
    - Others: no-op
    """
    if sys.platform == "darwin":
        try:
            res = subprocess.run(["lpstat", "-r"], capture_output=True, text=True)
            if "not running" in (res.stdout or "").lower():
                # Best-effort start without sudo; may fail silently on restricted envs
                subprocess.run(["launchctl", "start", "org.cups.cupsd"], capture_output=True)
        except Exception:
            logger.error("Error ensuring cups running: " + traceback.format_exc())
            pass
    else:
        return


def win_list_printers(server: str | None = None, level: int = 2):
    """
    Enumerate printers. If `server` is None -> local; else enumerate on \\server.
    Retries once if the spooler isn't running (common cause of RPC 1722).
    """
    if server:
        server = r"\\" + server.lstrip("\\")   # ensure UNC
        flags = win32print.PRINTER_ENUM_NAME
        name  = server
    else:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        name  = None

    def _enum():
        return win32print.EnumPrinters(flags, name, level)

    try:
        return _enum()
    except Exception as e:
        if sys.platform == 'win32' and pywintypes is not None and isinstance(e, pywintypes.error) and getattr(e, 'winerror', None) == 1722:
            try:
                win32serviceutil.StartService("Spooler")
            except Exception:
                pass
            time.sleep(1.0)
            return _enum()
        raise


def mac_list_printers():
    result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
    printer_lines = result.stdout.strip().split('\n')
    printers = []
    for line in printer_lines:
        if line.startswith('printer'):
            printer_name = line.split(' ')[1]
            printers.append(printer_name)
    return printers

def _run_wifi_command(command_type: str) -> Optional[str]:
    """
    Run a platform-specific WiFi command and return the output.

    Args:
        command_type: 'scan' for available networks or 'status' for current connection.

    Returns:
        The command's stdout as a string, or None if the command fails.
    """
    system = platform.system()
    command: List[str] = []

    try:
        if system == 'Windows':
            if command_type == 'status':
                command = ["netsh", "wlan", "show", "interfaces"]
            elif command_type == 'scan':
                command = ["netsh", "wlan", "show", "networks"]
        elif system == 'Darwin':
            airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport'
            if not os.path.exists(airport_path):
                airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Resources/airport'

            if os.path.exists(airport_path):
                if command_type == 'status':
                    command = [airport_path, '-I']
                elif command_type == 'scan':
                    command = [airport_path, '-s']
            elif command_type == 'scan': # Fallback for scan if airport is not found
                command = ['networksetup', '-listpreferredwirelessnetworks', 'en0']

        if not command:
            logger.warning(f"Unsupported platform or command type for WiFi operation: {system}, {command_type}")
            return None

        result = subprocess.run(
            command, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True
        )
        return result.stdout

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"Could not execute WiFi command '{' '.join(command)}': {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while running WiFi command: {e}")

    return None

def get_default_wifi_ssid() -> Optional[str]:
    """
    Get the SSID of the currently connected WiFi network.

    Returns:
        The SSID as a string, or None if not connected or not found.
    """
    output = _run_wifi_command('status')
    if not output:
        return None

    for line in output.split('\n'):
        if "SSID" in line and ":" in line:
            ssid = line.split(":")[1].strip()
            if ssid:
                return ssid

    return None

class SettingsManager:
    """
    Settings Manager class that handles application settings and configuration
    without GUI components
    """

    def __init__(self, parent):
        """
        Initialize SettingsManager

        Args:
            parent: Reference to parent application
        """
        self.parent = parent

        # Settings state
        self.commander_run = False
        self.overcapcity_warning = True
        self.overcapcity_force = True
        self.auto_schedule_mode = False
        self.browser_path = ""
        self.num_vehicles = 0

        # Hardware configuration
        self.printers = []
        self.wifi_list = []
        self.default_printer = ""
        self.default_wifi = ""

        # Initialize hardware detection
        try:
            self.list_wifi_networks()
            self.list_printers()
            self.default_wifi = get_default_wifi_ssid() or ""
        except Exception as e:
            logger.error(f"Error initializing SettingsManager: {e}")

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
        """Get auto schedule mode setting"""
        return self.auto_schedule_mode

    def set_auto_schedule_mode(self, value: bool):
        """Set auto schedule mode setting"""
        self.auto_schedule_mode = value

    def get_browser_path(self) -> str:
        """Get browser executable path"""
        return self.browser_path

    def set_browser_path(self, path: str):
        """Set browser executable path"""
        self.browser_path = path

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
        """Get default printer setting"""
        return self.default_printer

    def set_default_printer(self, printer: str):
        """Set default printer setting"""
        self.default_printer = printer

    def get_default_wifi(self) -> str:
        """Get default WiFi setting"""
        return self.default_wifi

    def set_default_wifi(self, wifi: str):
        """Set default WiFi setting"""
        self.default_wifi = wifi

    def get_printers(self) -> List[Any]:
        """Get list of available printers"""
        return self.printers.copy()

    def get_wifi_networks(self) -> List[str]:
        """Get list of available WiFi networks"""
        return self.wifi_list.copy()

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all current settings as a dictionary"""
        return {
            'commander_run': self.commander_run,
            'overcapcity_warning': self.overcapcity_warning,
            'overcapcity_force': self.overcapcity_force,
            'auto_schedule_mode': self.auto_schedule_mode,
            'browser_path': self.browser_path,
            'num_vehicles': self.num_vehicles,
            'default_printer': self.default_printer,
            'default_wifi': self.default_wifi,
            'available_printers': self.get_printer_names(),
            'available_wifi_networks': self.wifi_list
        }

    def set_all_settings(self, settings: Dict[str, Any]):
        """Set all settings from a dictionary"""
        try:
            if 'commander_run' in settings:
                self.set_commander_run(settings['commander_run'])
            if 'overcapcity_warning' in settings:
                self.set_overcapcity_warning(settings['overcapcity_warning'])
            if 'overcapcity_force' in settings:
                self.set_overcapcity_force(settings['overcapcity_force'])
            if 'auto_schedule_mode' in settings:
                self.set_auto_schedule_mode(settings['auto_schedule_mode'])
            if 'browser_path' in settings:
                self.set_browser_path(settings['browser_path'])
            if 'num_vehicles' in settings:
                self.set_num_vehicles(settings['num_vehicles'])
            if 'default_printer' in settings:
                self.set_default_printer(settings['default_printer'])
            if 'default_wifi' in settings:
                self.set_default_wifi(settings['default_wifi'])

            logger.info("All settings updated successfully")

        except Exception as e:
            logger.error(f"Error setting all settings: {e}")

    def save_settings(self) -> bool:
        """
        Save current settings to parent application

        Returns:
            True if settings saved successfully, False otherwise
        """
        try:
            # Update parent application settings
            if hasattr(self.parent, 'set_schedule_mode'):
                schedule_mode = "auto" if self.auto_schedule_mode else "manual"
                self.parent.set_schedule_mode(schedule_mode)

            if hasattr(self.parent, 'set_default_wifi'):
                self.parent.set_default_wifi(self.default_wifi)

            if hasattr(self.parent, 'set_default_printer'):
                self.parent.set_default_printer(self.default_printer)

            if hasattr(self.parent, 'saveSettings'):
                self.parent.saveSettings()

            logger.info("Settings saved successfully")
            return True

        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False

    def load_settings(self) -> bool:
        """
        Load settings from parent application

        Returns:
            True if settings loaded successfully, False otherwise
        """
        try:
            # Load settings from parent if available
            if hasattr(self.parent, 'get_default_printer'):
                self.default_printer = self.parent.get_default_printer()

            if hasattr(self.parent, 'get_default_wifi'):
                self.default_wifi = self.parent.get_default_wifi()

            logger.info("Settings loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            return False

    def list_printers(self) -> bool:
        """
        Detect and list available printers

        Returns:
            True if printers detected successfully, False otherwise
        """
        try:
            if platform.system() == 'Windows':
                ensure_spooler_running()
                self.printers = win_list_printers()
            elif platform.system() == 'Darwin':  # macOS
                ensure_cups_running()
                self.printers = mac_list_printers()
            else:
                # Linux or other platforms
                self.printers = []

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
        Detect and list available WiFi networks

        Returns:
            True if WiFi networks detected successfully, False otherwise
        """
        try:
            ssid_list = []
            networks_output = None

            for i in range(3):  # Try scanning multiple times
                networks_output = _run_wifi_command('scan')
                if networks_output:
                    # Use regular expression to find all SSID lines and extract SSID names
                    ssid_list = re.findall(r"SSID \d+ : (.+)", networks_output)
                    if not ssid_list and platform.system() == 'Darwin': # Handle different macOS outputs
                        lines = networks_output.strip().split('\n')
                        if lines and "SSID" in lines[0]: # Airport output
                            lines = lines[1:] # Skip header
                        ssid_list = [line.split()[0] for line in lines if line.strip()]

                    if ssid_list:
                        logger.info(f"Available Wi-Fi Networks (Scan {i + 1}):")
                        for ssid in ssid_list:
                            logger.info(f"- {ssid}")
                        break  # Successfully found networks, no need to retry
                else:
                    logger.warning(f"No Wi-Fi networks found in scan {i + 1}.")

            self.wifi_list = sorted(list(set(ssid_list))) # Store unique SSIDs
            return len(self.wifi_list) > 0

        except Exception as e:
            logger.error(f"Error listing WiFi networks: {e}")
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

        # Validate browser path
        if self.browser_path and not os.path.exists(self.browser_path):
            validation_results['valid'] = False
            validation_results['errors'].append(f"Browser path does not exist: {self.browser_path}")

        # Validate number of vehicles
        if self.num_vehicles < 0:
            validation_results['valid'] = False
            validation_results['errors'].append("Number of vehicles cannot be negative")

        # Validate default printer
        if self.default_printer and self.default_printer not in self.get_printer_names():
            validation_results['warnings'].append(f"Default printer not found in available printers: {self.default_printer}")

        # Validate default WiFi
        if self.default_wifi and self.default_wifi not in self.wifi_list:
            validation_results['warnings'].append(f"Default WiFi not found in available networks: {self.default_wifi}")

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
            import json
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
            import json
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
        """Reset all settings to default values"""
        try:
            self.commander_run = False
            self.overcapcity_warning = True
            self.overcapcity_force = True
            self.auto_schedule_mode = False
            self.browser_path = ""
            self.num_vehicles = 0
            self.default_printer = ""
            self.default_wifi = ""

            logger.info("Settings reset to defaults")

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
                'default_printer': self.default_printer,
                'default_wifi': self.default_wifi
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

    def cleanup(self):
        """Clean up resources"""
        try:
            # Clear lists to free memory
            self.printers.clear()
            self.wifi_list.clear()
            logger.info("SettingsManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
