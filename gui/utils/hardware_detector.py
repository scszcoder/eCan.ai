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

        # Method 2: Fallback to wmic command
        logger.debug("Trying wmic as fallback for printer detection")
        try:
            result = subprocess.run(['wmic', 'printer', 'get', 'name,status'],
                                  capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                printers = []
                for line in lines[1:]:  # Skip header
                    line = line.strip()
                    if line and line != 'Name':
                        # Parse wmic output format
                        parts = line.split()
                        if parts:
                            printer_name = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
                            if printer_name and printer_name != 'Status':
                                printers.append(printer_name)
                logger.debug(f"Found {len(printers)} printers via wmic")
                return printers
        except Exception as e:
            logger.debug(f"wmic printer detection failed: {e}")

        # Method 3: Fallback to PowerShell
        logger.debug("Trying PowerShell as fallback for printer detection")
        try:
            ps_cmd = 'Get-Printer | Select-Object -ExpandProperty Name'
            result = subprocess.run(['powershell', '-Command', ps_cmd],
                                  capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=20)
            if result.returncode == 0:
                printers = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                logger.debug(f"Found {len(printers)} printers via PowerShell")
                return printers
        except Exception as e:
            logger.debug(f"PowerShell printer detection failed: {e}")

        logger.warning("All Windows printer detection methods failed")
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
                    if line and ('正在接受请求' in line or 'accepting requests' in line):
                        # Extract printer name (first word before space or status text)
                        printer_name = line.split('正在接受请求')[0].split('accepting requests')[0].strip()
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
        logger.debug("Executing _run_wifi_command")
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
            if result.stderr:
                logger.debug(f"WiFi command stderr: {result.stderr}")

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
                result = subprocess.run(['networksetup', '-getairportnetwork', 'en0'],
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

            # Try system_profiler as another fallback
            logger.debug("Trying system_profiler as additional fallback on macOS.")
            try:
                result = subprocess.run(['system_profiler', 'SPAirPortDataType'],
                                      capture_output=True, text=True, timeout=20)
                if result.returncode == 0:
                    output = result.stdout
                    # Look for current network information
                    lines = output.split('\n')
                    for i, line in enumerate(lines):
                        if "Current Network Information:" in line:
                            # The next line should contain the SSID
                            if i + 1 < len(lines):
                                next_line = lines[i + 1].strip()
                                # Extract SSID from format like "SSID-NAME:"
                                if ':' in next_line:
                                    ssid = next_line.split(':')[0].strip()
                                    if ssid and ssid != "Current Network Information":
                                        logger.debug(f"Found WiFi SSID via system_profiler: {ssid}")
                                        return ssid
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
            logger.debug("Getting default WiFi SSID using Windows methods.")

            # Method 1: netsh wlan show interfaces
            try:
                output = self._run_wifi_command('status')
                if output:
                    logger.debug("Processing netsh interfaces output")
                    for line in output.split('\n'):
                        line = line.strip()
                        if "SSID" in line and ":" in line:
                            # Handle different SSID line formats
                            if line.startswith("SSID"):
                                ssid = line.split(":", 1)[1].strip()
                                if ssid and ssid != "":
                                    logger.debug(f"Found WiFi SSID via netsh interfaces: {ssid}")
                                    return ssid
            except Exception as e:
                logger.debug(f"netsh interfaces method failed: {e}")

            # Method 2: netsh wlan show profiles (get connected profile)
            try:
                result = subprocess.run(['netsh', 'wlan', 'show', 'profiles'],
                                      capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15)
                if result.returncode == 0:
                    # Look for profiles and check which one is connected
                    profiles = re.findall(r"All User Profile\s*:\s*(.+)", result.stdout)
                    logger.debug(f"Found {len(profiles)} WiFi profiles")

                    # Check each profile to see if it's connected
                    for profile in profiles:
                        profile = profile.strip()
                        try:
                            detail_result = subprocess.run(['netsh', 'wlan', 'show', 'profile', f'name="{profile}"', 'key=clear'],
                                                         capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)
                            if detail_result.returncode == 0 and "Connection mode" in detail_result.stdout:
                                # This might be the connected profile, but we need to verify
                                # For now, we'll use the first profile as a fallback
                                pass
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"netsh profiles method failed: {e}")

            # Method 3: PowerShell method
            try:
                ps_cmd = 'Get-NetConnectionProfile | Where-Object {$_.InterfaceAlias -like "*Wi-Fi*"} | Select-Object -ExpandProperty Name'
                result = subprocess.run(['powershell', '-Command', ps_cmd],
                                      capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=20)
                if result.returncode == 0:
                    ssid = result.stdout.strip()
                    if ssid and ssid != "":
                        logger.debug(f"Found WiFi SSID via PowerShell: {ssid}")
                        return ssid
            except Exception as e:
                logger.debug(f"PowerShell method failed: {e}")

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
                                            if ssid and ssid not in ssid_list:
                                                ssid_list.append(ssid)
                                                logger.debug(f"Added WiFi network: {ssid}")
                                        except Exception as e:
                                            logger.debug(f"Error getting SSID from network object: {e}")
                                            continue
                                    corewlan_success = True
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
                    logger.debug("Scanning for WiFi networks using Windows methods.")

                    # Method 1: netsh wlan show networks
                    for i in range(3):
                        networks_output = self._run_wifi_command('scan')
                        if networks_output:
                            # Use correct regex pattern to match SSID
                            ssid_matches = re.findall(r"SSID \d+ : (.+)", networks_output)
                            new_ssids = [ssid.strip() for ssid in ssid_matches if ssid.strip() and ssid.strip() not in ssid_list]
                            ssid_list.extend(new_ssids)
                            logger.debug(f"Found {len(new_ssids)} new SSIDs via netsh scan")
                            if ssid_list:
                                break  # Found networks
                        else:
                            logger.warning(f"WiFi scan command returned no output (Scan {i + 1}).")
                        time.sleep(1)

                    # Method 2: netsh wlan show profiles (as fallback)
                    if not ssid_list:
                        logger.debug("Trying netsh profiles as fallback for Windows.")
                        try:
                            result = subprocess.run(['netsh', 'wlan', 'show', 'profiles'],
                                                  capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15)
                            if result.returncode == 0:
                                profile_matches = re.findall(r"All User Profile\s*:\s*(.+)", result.stdout)
                                new_profiles = [profile.strip() for profile in profile_matches if profile.strip() and profile.strip() not in ssid_list]
                                ssid_list.extend(new_profiles)
                                logger.info(f"Found {len(new_profiles)} WiFi profiles as fallback")
                        except Exception as e:
                            logger.debug(f"netsh profiles fallback failed: {e}")

                    # Method 3: PowerShell as additional fallback
                    if not ssid_list:
                        logger.debug("Trying PowerShell as additional fallback for Windows.")
                        try:
                            ps_cmd = 'netsh wlan show profiles | Select-String "All User Profile" | ForEach-Object {($_ -split ":")[1].Trim()}'
                            result = subprocess.run(['powershell', '-Command', ps_cmd],
                                                  capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=20)
                            if result.returncode == 0:
                                ps_profiles = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                                new_ps_profiles = [profile for profile in ps_profiles if profile and profile not in ssid_list]
                                ssid_list.extend(new_ps_profiles)
                                logger.info(f"Found {len(new_ps_profiles)} WiFi profiles via PowerShell")
                        except Exception as e:
                            logger.debug(f"PowerShell fallback failed: {e}")
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
