#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Detector - Cross-platform hardware detection module
Provides printer and WiFi network detection functionality across platforms
"""

import sys
import threading
import subprocess
import platform
import time
import traceback
from typing import List, Dict, Any, Optional, Callable
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
        # Background WiFi scan state
        self._wifi_scan_thread: Optional[threading.Thread] = None
        self._wifi_scan_lock = threading.Lock()
        self._wifi_scan_in_progress: bool = False

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
        """Windows printer enumeration with fallback methods"""
        # Method 1: Try pywin32 if available
        if win32print:
            if server:
                server = r"\\" + server.lstrip("\\")
                flags = win32print.PRINTER_ENUM_NAME
                name = server
            else:
                flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                name = None

            try:
                printers = win32print.EnumPrinters(flags, name, level)
                logger.debug(f"Found {len(printers)} printers via pywin32")
                return printers
            except pywintypes.error as e:
                if e.winerror == 1722:  # RPC server unavailable
                    logger.warning("RPC server unavailable, ensuring spooler is running...")
                    self._ensure_spooler_running()
                    try:
                        printers = win32print.EnumPrinters(flags, name, level)
                        logger.debug(f"Found {len(printers)} printers via pywin32 (retry)")
                        return printers
                    except Exception as retry_e:
                        logger.error(f"Retry failed: {retry_e}")
                else:
                    logger.error(f"Error listing printers: {e}")
            except Exception as e:
                logger.error(f"Unexpected error with pywin32: {e}")

        logger.debug("win32print unavailable or failed; skipping command-line fallbacks to avoid console flashing")
        return []
    
    def _mac_list_printers(self):
        """macOS printer enumeration with multiple methods"""
        printers = []

        # Method 1: Try lpstat -a (available printers)
        try:
            result = subprocess.run(['lpstat', '-a'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                printer_lines = result.stdout.strip().split('\n')
                for line in printer_lines:
                    if line and ('accepting requests' in line or 'idle' in line):
                        # Extract printer name (first word before space or status text)
                        printer_name = line.split('accepting requests')[0].split('idle')[0].strip()
                        if printer_name and printer_name not in printers:
                            printers.append(printer_name)
                logger.debug(f"Found {len(printers)} printers via lpstat -a")
        except Exception as e:
            logger.debug(f"lpstat -a failed: {e}")

        # Method 2: Try lpstat -p (printer status) as fallback
        if not printers:
            try:
                result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    printer_lines = result.stdout.strip().split('\n')
                    for line in printer_lines:
                        if line.startswith('printer'):
                            printer_name = line.split(' ')[1]
                            if printer_name and printer_name not in printers:
                                printers.append(printer_name)
                    logger.debug(f"Found {len(printers)} printers via lpstat -p")
            except Exception as e:
                logger.debug(f"lpstat -p failed: {e}")

        # Method 3: Try system_profiler as additional fallback
        if not printers:
            try:
                result = subprocess.run(['system_profiler', 'SPPrintersDataType'],
                                      capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    # Parse system_profiler output for printer names
                    lines = result.stdout.split('\n')
                    in_printers_section = False
                    for line in lines:
                        original_line = line
                        line = line.strip()

                        if line == 'Printers:':
                            in_printers_section = True
                            continue

                        # Look for printer names (lines that end with : and are indented with exactly 4 spaces)
                        if (in_printers_section and line.endswith(':') and
                            original_line.startswith('    ') and not original_line.startswith('      ')):
                            printer_name = line.rstrip(':').strip()
                            # Filter out common non-printer entries
                            if (printer_name and printer_name not in printers and
                                printer_name not in ['CUPS filters', 'PDEs', 'Status', 'Driver Version']):
                                printers.append(printer_name)
                    logger.debug(f"Found {len(printers)} printers via system_profiler")
            except Exception as e:
                logger.debug(f"system_profiler failed: {e}")

        if not printers:
            logger.debug("No printers found using any macOS method")

        return printers
    
    def _linux_list_printers(self):
        """Linux printer enumeration"""
        try:
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=10)
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
        logger.debug("Executing _run_wifi_command")
        system = platform.system()
        if system == 'Windows':
            logger.debug("Skipping command-line WiFi invocation on Windows to avoid console popups")
        else:
            logger.debug(f"No command-line implementation for WiFi operation on platform: {system}")
        return None

    def _scan_windows_wifi_networks(self) -> List[str]:
        """Use pywifi to scan available WiFi networks on Windows."""
        try:
            from pywifi import PyWiFi  # type: ignore
        except ImportError:
            logger.warning("pywifi not installed; skipping Windows WiFi scan")
            return []

        try:
            wifi = PyWiFi()
            interfaces = wifi.interfaces()
            if not interfaces:
                logger.warning("No WiFi interfaces found by pywifi")
                return []

            iface = interfaces[0]
            iface.scan()
            
            # Poll for scan results with short delays to avoid UI blocking
            # Maximum wait: 1.5s, but check every 100ms
            max_attempts = 15
            networks = []
            for attempt in range(max_attempts):
                networks = iface.scan_results()
                if networks:  # Got results, exit early
                    break
                time.sleep(0.1)  # 100ms increments
            ssids: List[str] = []
            for network in networks:
                ssid = getattr(network, 'ssid', None)
                if ssid and ssid not in ssids:
                    ssids.append(ssid)

            logger.debug(f"pywifi discovered {len(ssids)} WiFi networks")
            return ssids

        except Exception as e:
            logger.error(f"pywifi WiFi scan failed: {e}")
            return []
    
    def _get_current_wifi_ssid(self) -> Optional[str]:
        """
        Get current connected WiFi SSID - using verified original code
        Get the SSID of the currently connected WiFi network.
        """
        if platform.system() == 'Darwin':
            # Try CoreWLAN first
            if CWInterface is not None:
                logger.debug("Getting default WiFi SSID using CoreWLAN on macOS.")
                try:
                    # Get the names of all supported Wi-Fi interfaces
                    interface_names = CWInterface.supportedInterfaces()
                    # Iterate through all supported Wi-Fi interfaces to find the one that is connected
                    for name in interface_names:
                        iface = CWInterface.interfaceWithName_(name)
                        logger.debug(f"Checking interface: {name}, iface object is not None: {iface is not None}")
                        if iface:
                            ssid = iface.ssid()
                            if ssid:
                                return ssid
                except Exception as e:
                    logger.error(f"Could not get default WiFi SSID using CoreWLAN: {e}")
            
            # Fallback to networksetup command on macOS
            logger.debug("Trying networksetup command as fallback on macOS.")
            try:
                # Detect actual Wi‑Fi device (en0/en1/...) via networksetup to avoid hardcoding
                wifi_device = 'en0'
                try:
                    dev_result = subprocess.run(
                        ['networksetup', '-listallhardwareports'],
                        capture_output=True, text=True, timeout=10
                    )
                    if dev_result.returncode == 0:
                        lines = dev_result.stdout.split('\n')
                        for i, line in enumerate(lines):
                            if 'Hardware Port: Wi-Fi' in line or 'Hardware Port: Wi‑Fi' in line:
                                # Find following line starting with "Device:"
                                j = i + 1
                                while j < len(lines):
                                    dev_line = lines[j].strip()
                                    if dev_line.startswith('Device:'):
                                        wifi_device = dev_line.split(':', 1)[1].strip()
                                        break
                                    if dev_line.startswith('Hardware Port:'):
                                        break
                                    j += 1
                                break
                        logger.debug(f"Detected Wi‑Fi device: {wifi_device}")
                except Exception as e:
                    logger.debug(f"Failed to detect Wi‑Fi device, fallback to en0: {e}")

                result = subprocess.run(['networksetup', '-getairportnetwork', wifi_device],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    output = result.stdout.strip()
                    logger.debug(f"networksetup output: '{output}'")
                    if "Current Wi-Fi Network:" in output:
                        ssid = output.split("Current Wi-Fi Network:")[1].strip()
                        if ssid and ssid != "You are not associated with an AirPort network.":
                            logger.debug(f"Found WiFi SSID via networksetup: {ssid}")
                            return ssid
                    elif not "You are not associated" in output and output:
                        # Sometimes it just returns the SSID directly
                        logger.debug(f"Found WiFi SSID directly: {output}")
                        return output
            except Exception as e:
                logger.debug(f"networksetup command failed: {e}")

            # Try private 'airport -I' utility which often reports current SSID reliably
            logger.debug("Trying 'airport -I' as additional fallback on macOS.")
            try:
                airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport'
                result = subprocess.run([airport_path, '-I'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        # Typical format: 'SSID: Oliver_Su'
                        if line.startswith('SSID:'):
                            ssid = line.split(':', 1)[1].strip()
                            if ssid:
                                logger.debug(f"Found WiFi SSID via airport -I: {ssid}")
                                return ssid
            except Exception as e:
                logger.debug(f"airport -I failed: {e}")

            # Try system_profiler as another fallback
            logger.debug("Trying system_profiler as additional fallback on macOS.")
            try:
                result = subprocess.run(['system_profiler', 'SPAirPortDataType'],
                                      capture_output=True, text=True, timeout=20)
                if result.returncode == 0:
                    output = result.stdout
                    # Look for current network information
                    lines = output.split('\n')
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        if "Current Network Information:" in line:
                            # Scan following few lines for 'SSID:' key
                            for j in range(1, 8):
                                if i + j >= len(lines):
                                    break
                                kv = lines[i + j].strip()
                                # Expected format like: 'SSID: Oliver_Su'
                                if kv.startswith('SSID:'):
                                    ssid = kv.split(':', 1)[1].strip()
                                    if ssid and ssid != "Current Network Information":
                                        logger.debug(f"Found WiFi SSID via system_profiler: {ssid}")
                                        return ssid
                            # If no SSID key found, try older format like '<ssid_name>:' on the next line
                            if i + 1 < len(lines):
                                nl = lines[i + 1].strip()
                                if ':' in nl:
                                    candidate = nl.split(':', 1)[0].strip()
                                    if candidate and candidate != "Current Network Information":
                                        logger.debug(f"Found WiFi SSID via system_profiler (legacy parse): {candidate}")
                                        return candidate
                        i += 1
            except Exception as e:
                logger.debug(f"system_profiler command failed: {e}")

            # Try iwgetid if available (some systems might have it)
            logger.debug("Trying iwgetid as final fallback on macOS.")
            try:
                result = subprocess.run(['iwgetid', '-r'],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    ssid = result.stdout.strip()
                    if ssid:
                        logger.debug(f"Found WiFi SSID via iwgetid: {ssid}")
                        return ssid
            except FileNotFoundError:
                logger.debug("iwgetid command not found")
            except Exception as e:
                logger.debug(f"iwgetid command failed: {e}")

            return None
        elif platform.system() == 'Windows':
            # Windows-specific WiFi detection
            logger.debug("Getting default WiFi SSID using Windows APIs.")

            # Method 1: Query MSFT_NetConnectionProfile via WMI (no console window)
            try:
                import win32com.client  # type: ignore

                locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                service = locator.ConnectServer('.', 'root\\StandardCimv2')
                query = "SELECT Name FROM MSFT_NetConnectionProfile WHERE ConnectionStatus = 2"
                for profile in service.ExecQuery(query):
                    ssid = getattr(profile, 'Name', None)
                    if ssid:
                        logger.debug(f"Found WiFi SSID via MSFT_NetConnectionProfile: {ssid}")
                        return ssid
            except Exception as e:
                logger.debug(f"WMI method for WiFi SSID failed: {e}")

            logger.debug("No WiFi SSID detected using Windows APIs")
            return None
        else:
            # Other platforms fallback
            logger.debug("Getting default WiFi SSID using generic command-line method.")
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

            if system == 'Darwin':
                # Try CoreWLAN first on macOS
                corewlan_success = False
                if CWInterface is not None:
                    logger.debug("Scanning for WiFi networks using CoreWLAN on macOS.")
                    try:
                        interface = CWInterface.interface()
                        if interface:
                            # Use correct method name: scanForNetworksWithSSID_error_
                            networks, error = interface.scanForNetworksWithSSID_error_(None, None)
                            if error:
                                error_code = error.code() if hasattr(error, 'code') else 'unknown'
                                logger.warning(f"CoreWLAN scan error (code {error_code}): {error}")
                                # Check for specific error types
                                if 'kCWErrNotPermitted' in str(error):
                                    logger.error("Wi-Fi scan failed on macOS. This may be due to missing Location Services permissions for the application. Please check System Settings > Privacy & Security > Location Services.")
                                elif error_code == 16:  # Resource busy
                                    logger.warning("WiFi interface is busy, will try command-line fallback")
                            elif networks:
                                # networks is a NSSet collection of network objects
                                # Convert NSSet to list for iteration
                                try:
                                    # Convert NSSet to Python list
                                    network_list = list(networks)
                                    logger.debug(f"CoreWLAN found {len(network_list)} networks")

                                    for network in network_list:
                                        try:
                                            ssid = network.ssid()
                                            logger.trace(f"Network SSID raw value: {repr(ssid)} (type: {type(ssid).__name__})")
                                            if ssid and ssid not in ssid_list:
                                                ssid_list.append(ssid)
                                                logger.debug(f"Added WiFi network: {ssid}")
                                            elif not ssid:
                                                logger.debug(f"Skipped network with empty SSID")
                                        except Exception as e:
                                            logger.debug(f"Error getting SSID from network object: {e}")
                                            continue
                                    corewlan_success = len(ssid_list) > 0 if ssid_list else False
                                    if not corewlan_success:
                                        logger.warning(f"CoreWLAN found {len(network_list)} networks but extracted 0 SSIDs")
                                except Exception as e:
                                    logger.error(f"Error converting NSSet to list: {e}")
                                    # Fall back to trying direct iteration
                                    try:
                                        for network in networks:
                                            try:
                                                ssid = network.ssid()
                                                if ssid and ssid not in ssid_list:
                                                    ssid_list.append(ssid)
                                                    logger.debug(f"Added WiFi network (fallback): {ssid}")
                                            except Exception as e:
                                                logger.debug(f"Error getting SSID from network object (fallback): {e}")
                                                continue
                                        corewlan_success = True
                                    except Exception as e2:
                                        logger.error(f"Both NSSet conversion methods failed: {e2}")
                                        corewlan_success = False
                    except Exception as e:
                        logger.error(f"An unexpected error occurred during CoreWLAN scan: {e}")
                
                # Fallback to command-line on macOS if CoreWLAN failed
                if not corewlan_success:
                    logger.debug("Trying command-line WiFi scan as fallback on macOS.")
                    try:
                        # Try iwlist if available (some systems have it)
                        result = subprocess.run(['iwlist', 'scan'], capture_output=True, text=True, timeout=15)
                        if result.returncode == 0:
                            # Parse iwlist output
                            for line in result.stdout.split('\n'):
                                if 'ESSID:' in line:
                                    ssid = line.split('ESSID:')[1].strip().strip('"')
                                    if ssid and ssid not in ssid_list:
                                        ssid_list.append(ssid)
                        else:
                            logger.debug("iwlist command not available or failed")
                    except FileNotFoundError:
                        logger.debug("iwlist command not found")
                    except Exception as e:
                        logger.debug(f"iwlist command failed: {e}")
                    
                    # Try networksetup to get preferred networks (these are previously connected networks)
                    if not ssid_list:
                        logger.debug("Trying networksetup to get preferred WiFi networks on macOS.")
                        try:
                            result = subprocess.run(['networksetup', '-listpreferredwirelessnetworks', 'en0'], 
                                                  capture_output=True, text=True, timeout=15)
                            if result.returncode == 0:
                                lines = result.stdout.strip().split('\n')
                                for line in lines[1:]:  # Skip header line
                                    ssid = line.strip()
                                    if ssid and ssid not in ssid_list:
                                        ssid_list.append(ssid)
                                logger.info(f"Found {len(ssid_list)} preferred WiFi networks")
                        except Exception as e:
                            logger.debug(f"networksetup preferred networks command failed: {e}")
                    
                    # If still no results, try system_profiler (slower but more reliable)
                    if not ssid_list:
                        logger.debug("Trying system_profiler as last resort on macOS.")
                        try:
                            result = subprocess.run(['system_profiler', 'SPAirPortDataType'], 
                                                  capture_output=True, text=True, timeout=30)
                            if result.returncode == 0:
                                # This gives us info about available networks (if any)
                                logger.debug("system_profiler executed successfully")
                        except Exception as e:
                            logger.debug(f"system_profiler command failed: {e}")
            else:
                # Windows/Linux fallback - enhanced with multiple methods
                if system == 'Windows':
                    logger.debug("Scanning for WiFi networks using pywifi on Windows.")
                    ssid_list = self._scan_windows_wifi_networks()
                else:
                    # Linux/other platforms
                    logger.debug("Scanning for WiFi networks using generic command-line method.")
                    for i in range(3):
                        networks_output = self._run_wifi_command('scan')
                        if networks_output:
                            # Generic parsing for other platforms
                            # Add platform-specific parsing here if needed
                            logger.debug("Processing generic WiFi scan output")
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

    def start_wifi_scan_background(self, on_complete: Optional[Callable[[List[str]], None]] = None) -> bool:
        """Start WiFi scan on a background thread to avoid UI blocking.

        Returns True if a new scan was started, False if a scan is already running.
        """
        with self._wifi_scan_lock:
            if self._wifi_scan_thread is not None and self._wifi_scan_thread.is_alive():
                logger.debug("WiFi scan request ignored: scan already in progress")
                self._wifi_scan_in_progress = True
                return False

            self._wifi_scan_in_progress = True

            def _worker():
                try:
                    results = self.detect_wifi_networks()
                    if on_complete:
                        try:
                            on_complete(results)
                        except Exception as cb_err:
                            logger.error(f"WiFi scan callback error: {cb_err}")
                except Exception as e:
                    logger.error(f"Background WiFi scan failed: {e}")
                finally:
                    with self._wifi_scan_lock:
                        self._wifi_scan_in_progress = False
                        self._wifi_scan_thread = None

            self._wifi_scan_thread = threading.Thread(target=_worker, name="WiFiScanThread", daemon=True)
            self._wifi_scan_thread.start()
            return True

    def is_wifi_scan_in_progress(self) -> bool:
        """Check if a background WiFi scan is currently running."""
        with self._wifi_scan_lock:
            return self._wifi_scan_in_progress and self._wifi_scan_thread is not None and self._wifi_scan_thread.is_alive()

    def wait_for_wifi_scan(self, timeout: Optional[float] = None) -> List[str]:
        """Wait for the current background WiFi scan to finish and return results.

        If no scan is running, returns current cached results immediately.
        """
        thread = None
        with self._wifi_scan_lock:
            thread = self._wifi_scan_thread
        if thread is not None:
            thread.join(timeout=timeout)
        return self.get_wifi_networks()

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
