#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Detector - Cross-platform hardware detection module
Provides printer and WiFi network detection functionality across platforms
"""

import sys
import subprocess
import platform
import time
import re
import traceback
from typing import List, Dict, Any, Optional
from utils.logger_helper import logger_helper as logger

# Platform-specific imports
if sys.platform == "win32":
    try:
        import win32print
        import pywintypes
        import win32serviceutil
    except ImportError:
        win32print = None
        pywintypes = None
        win32serviceutil = None
else:
    win32print = None
    pywintypes = None
    win32serviceutil = None

if sys.platform == "darwin":
    try:
        from CoreWLAN import CWInterface
    except ImportError:
        CWInterface = None
else:
    CWInterface = None


class HardwareDetector:
    """Hardware detector - provides printer and WiFi detection functionality"""

    def __init__(self):
        """Initialize hardware detector"""
        self._printers = []
        self._wifi_networks = []

    # ==================== Printer Detection ====================

    def _ensure_spooler_running(self):
        """Ensure Windows print spooler service is running"""
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
    
    def _win_list_printers(self, server: str = None, level: int = 2):
        """Windows printer enumeration"""
        if not win32print:
            return []
            
        if server:
            server = r"\\" + server.lstrip("\\")
            flags = win32print.PRINTER_ENUM_NAME
            name = server
        else:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            name = None
            
        try:
            return win32print.EnumPrinters(flags, name, level)
        except pywintypes.error as e:
            if e.winerror == 1722:  # RPC server unavailable
                logger.warning("RPC server unavailable, ensuring spooler is running...")
                self._ensure_spooler_running()
                try:
                    return win32print.EnumPrinters(flags, name, level)
                except Exception as retry_e:
                    logger.error(f"Retry failed: {retry_e}")
                    return []
            else:
                logger.error(f"Error listing printers: {e}")
                return []
    
    def _mac_list_printers(self):
        """macOS printer enumeration"""
        try:
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
            printer_lines = result.stdout.strip().split('\n')
            printers = []
            for line in printer_lines:
                if line.startswith('printer'):
                    printer_name = line.split(' ')[1]
                    printers.append(printer_name)
            return printers
        except Exception as e:
            logger.error(f"Error listing macOS printers: {e}")
            return []
    
    def _linux_list_printers(self):
        """Linux printer enumeration"""
        try:
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
            printer_lines = result.stdout.strip().split('\n')
            printers = []
            for line in printer_lines:
                if line.startswith('printer'):
                    printer_name = line.split(' ')[1]
                    printers.append(printer_name)
            return printers
        except Exception as e:
            logger.error(f"Error listing Linux printers: {e}")
            return []
    
    def detect_printers(self) -> List[Any]:
        """Detect available printers"""
        try:
            system = platform.system()
            if system == 'Windows':
                self._ensure_spooler_running()
                self._printers = self._win_list_printers()
            elif system == 'Darwin':
                self._printers = self._mac_list_printers()
            elif system == 'Linux':
                self._printers = self._linux_list_printers()
            else:
                logger.warning(f"Unsupported platform for printer detection: {system}")
                self._printers = []
                
            logger.info(f"Detected {len(self._printers)} printers")
            return self._printers
            
        except Exception as e:
            logger.error(f"Error detecting printers: {e}")
            self._printers = []
            return []
    
    def get_printer_names(self) -> List[str]:
        """Get list of printer names"""
        printer_names = []
        for p in self._printers:
            if isinstance(p, dict) and 'pPrinterName' in p:
                printer_names.append(p['pPrinterName'])  # Windows dictionary format
            elif isinstance(p, (list, tuple)) and len(p) > 2:
                printer_names.append(p[2])  # Standard tuple format
            elif isinstance(p, (list, tuple)) and len(p) > 0:
                printer_names.append(str(p[0]))  # Fallback to first element
            elif isinstance(p, str):
                printer_names.append(p)  # Direct string (macOS/Linux)
            else:
                printer_names.append(str(p))  # Fallback to string conversion
        return printer_names
    
    # ==================== WiFi Detection ====================

    def _run_wifi_command(self, command_type: str) -> Optional[str]:
        """
        Run WiFi command - using verified original code
        This function is now only intended for Windows, as macOS uses CoreWLAN.
        """
        logger.debug("Executing _run_wifi_command (version 2025-09-05-A)")
        system = platform.system()
        if system != 'Windows':
            logger.debug(f"No command-line implementation for WiFi operation on platform: {system}")
            return None

        command = []
        try:
            if command_type == 'status':
                command = ["netsh", "wlan", "show", "interfaces"]
            elif command_type == 'scan':
                command = ["netsh", "wlan", "show", "networks"]

            if not command:
                logger.warning(f"Unsupported command type for WiFi operation on Windows: {command_type}")
                return None

            result = subprocess.run(
                command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15
            )

            logger.debug(f"WiFi command '{' '.join(command)}' finished with return code: {result.returncode}")
            if result.stdout:
                logger.debug(f"WiFi command stdout:\n{result.stdout}")
            if result.stderr:
                logger.debug(f"WiFi command stderr:\n{result.stderr}")

            if result.returncode != 0:
                logger.warning(f"WiFi command '{' '.join(command)}' exited with a non-zero status code.")
                return None

            return result.stdout

        except FileNotFoundError as e:
            logger.warning(f"Could not execute WiFi command '{' '.join(command)}': {e}")
        except subprocess.TimeoutExpired:
            logger.warning(f"WiFi command '{' '.join(command)}' timed out after 15 seconds.")
        except Exception as e:
            logger.error(f"An unexpected error occurred while running WiFi command: {e}")

        return None
    
    def _get_current_wifi_ssid(self) -> Optional[str]:
        """
        Get current connected WiFi SSID - using verified original code
        Get the SSID of the currently connected WiFi network.
        """
        if platform.system() == 'Darwin' and CWInterface is not None:
            logger.debug("Getting default WiFi SSID using CoreWLAN on macOS.")
            try:
                # Get the names of all supported Wi-Fi interfaces
                interface_names = CWInterface.supportedInterfaces()
                # Iterate through all supported Wi-Fi interfaces to find the one that is connected
                for name in interface_names:
                    iface = CWInterface.interfaceWithName_(name)
                    logger.debug(f"Checking interface: {name}, iface object is not None: {iface is not None} (version 2025-09-05-B)")
                    if iface:
                        ssid = iface.ssid()
                        if ssid:
                            return ssid
                return None  # No connected interface found
            except Exception as e:
                logger.error(f"Could not get default WiFi SSID using CoreWLAN: {e}")
                return None
        else:
            # Fallback to command-line for other platforms
            logger.debug("Getting default WiFi SSID using command-line method.")
            output = self._run_wifi_command('status')
            if not output:
                return None

            for line in output.split('\n'):
                if "SSID" in line and ":" in line:
                    ssid = line.split(":")[1].strip()
                    if ssid:
                        return ssid

        return None
    
    def detect_wifi_networks(self) -> List[str]:
        """Detect available WiFi networks"""
        try:
            system = platform.system()
            ssid_list = []

            if system == 'Darwin' and CWInterface is not None:
                # macOS using CoreWLAN - using verified original code
                logger.debug("Scanning for WiFi networks using CoreWLAN on macOS.")
                try:
                    interface = CWInterface.interface()
                    if interface:
                        # Use correct method name: scanForNetworksWithSSID_error_
                        networks, error = interface.scanForNetworksWithSSID_error_(None, None)
                        if error:
                            logger.error(f"CoreWLAN scan error: {error}")
                            # Check if it's a permission issue
                            if 'CoreWLAN CWWiFiClient.h' in str(error) and 'kCWErrNotPermitted' in str(error):
                                logger.error("Wi-Fi scan failed on macOS. This may be due to missing Location Services permissions for the application. Please check System Settings > Privacy & Security > Location Services.")
                        elif networks:
                            # networks is a collection of network objects
                            for network in networks:
                                try:
                                    ssid = network.ssid()
                                    if ssid and ssid not in ssid_list:
                                        ssid_list.append(ssid)
                                except Exception as e:
                                    logger.debug(f"Error getting SSID from network object: {e}")
                                    continue
                except Exception as e:
                    logger.error(f"An unexpected error occurred during CoreWLAN scan: {e}")
            else:
                # Windows/Linux fallback - using verified original code
                logger.debug("Scanning for WiFi networks using command-line method.")
                for i in range(3):
                    networks_output = self._run_wifi_command('scan')
                    if networks_output:
                        if system == 'Windows':
                            # Use correct regex pattern to match SSID
                            ssid_matches = re.findall(r"SSID \d+ : (.+)", networks_output)
                            ssid_list.extend([ssid.strip() for ssid in ssid_matches if ssid.strip() and ssid.strip() not in ssid_list])
                            if ssid_list:
                                break  # Found networks
                    else:
                        logger.warning(f"WiFi scan command returned no output (Scan {i + 1}).")
                    time.sleep(1)
            
            self._wifi_networks = ssid_list
            logger.info(f"Detected {len(ssid_list)} WiFi networks")
            return ssid_list
            
        except Exception as e:
            logger.error(f"Error detecting WiFi networks: {e}")
            self._wifi_networks = []
            return []
    
    # ==================== Public Interface ====================

    def get_printers(self) -> List[Any]:
        """Get detected printer list"""
        return self._printers.copy()

    def get_wifi_networks(self) -> List[str]:
        """Get detected WiFi network list"""
        return self._wifi_networks.copy()

    def get_current_wifi(self) -> Optional[str]:
        """Get current connected WiFi"""
        return self._get_current_wifi_ssid()

    def detect_all_hardware(self) -> Dict[str, Any]:
        """Detect all hardware"""
        printers = self.detect_printers()
        wifi_networks = self.detect_wifi_networks()
        current_wifi = self.get_current_wifi()
        
        return {
            'printers': printers,
            'printer_names': self.get_printer_names(),
            'wifi_networks': wifi_networks,
            'current_wifi': current_wifi,
            'platform': platform.system()
        }


# Global hardware detector instance
_hardware_detector = None

def get_hardware_detector() -> HardwareDetector:
    """Get global hardware detector instance"""
    global _hardware_detector
    if _hardware_detector is None:
        _hardware_detector = HardwareDetector()
    return _hardware_detector
