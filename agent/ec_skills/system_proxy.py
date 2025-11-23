"""
Cross-Platform System Proxy Detection with Dynamic Monitoring

This module provides functionality to read system proxy settings on both macOS and Windows,
and automatically set environment variables with real-time monitoring.

Key Features:
- Automatic proxy detection from system settings
- Connectivity testing before setting environment variables
- Background monitoring of proxy state changes
- Real-time environment variable updates
- Callback mechanism for proxy state change notifications
- Seamless support for subprocesses (inherited via environment variables)
- **Fully non-blocking**: All operations (proxy detection, connectivity testing, monitoring)
  happen in background threads, never blocking UI or application startup

Usage:
    In main.py, call initialize_proxy_environment() at startup:
    
    from agent.ec_skills.system_proxy import initialize_proxy_environment
    initialize_proxy_environment()  # Default: enables background monitoring
    
    This will (all operations are non-blocking):
    1. Start background thread for proxy detection (does not block startup)
    2. Detect and test system proxy in background
    3. Set HTTP_PROXY/HTTPS_PROXY environment variables if proxy is available
    4. Start background monitoring thread (checks every 30s by default)
    5. Automatically update environment variables when proxy state changes
    
    Note: All network operations and system calls happen in background threads
    to ensure application startup and UI remain responsive.
    
    Disable proxy management:
    
    # Method 1: Via environment variable
    export ECAN_PROXY_ENABLED=false
    python main.py
    
    # Method 2: Via function parameter
    initialize_proxy_environment(enable=False)
    
    # Method 3: Runtime control
    from agent.ec_skills.system_proxy import disable_proxy_management, enable_proxy_management
    disable_proxy_management()  # Stop proxy management
    enable_proxy_management()    # Re-enable proxy management
    
Subprocess Integration:
    Subprocesses (like lightrag_server) automatically inherit proxy settings
    via environment variables. They can register callbacks for real-time updates:
    
    from agent.ec_skills.system_proxy import get_proxy_manager
    
    proxy_manager = get_proxy_manager()
    if proxy_manager:
        def on_proxy_change(proxies):
            # Handle proxy state change
            pass
        proxy_manager.register_callback(on_proxy_change)
    
Auto-Restart for Subprocesses:
    To enable auto-restart when proxy state changes, set environment variable:
    PROXY_AUTO_RESTART=true
    
    This will automatically restart subprocesses (like lightrag_server) to pick up
    new proxy settings immediately.
"""

import subprocess
import re
import os
import sys
import socket
import threading
import time
from typing import Optional, Dict, Callable, List
from utils.logger_helper import logger_helper as logger


def get_macos_system_proxy() -> Optional[Dict[str, str]]:
    """
    Read macOS system proxy settings using scutil command.
    
    Returns:
        Dict with 'http://' and 'https://' proxy URLs, or None if no proxy is configured.
    
    Note: This function uses subprocess with timeout to avoid blocking.
    """
    try:
        result = subprocess.run(
            ['scutil', '--proxy'],
            capture_output=True,
            text=True,
            timeout=2  # Short timeout to avoid blocking
        )
        
        if result.returncode != 0:
            return None
        
        output = result.stdout
        proxies = {}
        
        # Parse HTTP proxy
        http_enabled = re.search(r'HTTPEnable\s*:\s*1', output)
        if http_enabled:
            http_proxy = re.search(r'HTTPProxy\s*:\s*(\S+)', output)
            http_port = re.search(r'HTTPPort\s*:\s*(\d+)', output)
            if http_proxy and http_port:
                proxies['http://'] = f"http://{http_proxy.group(1)}:{http_port.group(1)}"
        
        # Parse HTTPS proxy
        https_enabled = re.search(r'HTTPSEnable\s*:\s*1', output)
        if https_enabled:
            https_proxy = re.search(r'HTTPSProxy\s*:\s*(\S+)', output)
            https_port = re.search(r'HTTPSPort\s*:\s*(\d+)', output)
            if https_proxy and https_port:
                proxies['https://'] = f"http://{https_proxy.group(1)}:{https_port.group(1)}"
        
        return proxies if proxies else None
        
    except Exception as e:
        logger.debug(f"Failed to read macOS system proxy: {e}")
        return None


def get_windows_system_proxy() -> Optional[Dict[str, str]]:
    """
    Read Windows system proxy settings from registry.
    
    Returns:
        Dict with 'http://' and 'https://' proxy URLs, or None if no proxy is configured.
    """
    try:
        import winreg
        
        # Open registry key for Internet Settings
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
            0,
            winreg.KEY_READ
        )
        
        try:
            # Check if proxy is enabled
            proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')
            if not proxy_enable:
                return None
            
            # Get proxy server address
            proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
            
            proxies = {}
            
            # Parse proxy server string
            # Format: "proxy:8080" or "http=proxy1:8080;https=proxy2:8080"
            if ';' in proxy_server:
                for item in proxy_server.split(';'):
                    if '=' in item:
                        protocol, address = item.split('=', 1)
                        protocol = protocol.strip().lower()
                        if protocol in ['http', 'https']:
                            proxies[f'{protocol}://'] = f'http://{address}'
            else:
                # Single proxy for all protocols
                proxies['http://'] = f'http://{proxy_server}'
                proxies['https://'] = f'http://{proxy_server}'
            
            return proxies if proxies else None
            
        finally:
            winreg.CloseKey(key)
            
    except Exception as e:
        logger.debug(f"Failed to read Windows system proxy: {e}")
        return None


def get_system_proxy() -> Optional[Dict[str, str]]:
    """
    Get system proxy settings for current platform.
    
    Returns:
        Dict with 'http://' and 'https://' proxy URLs, or None if no proxy is configured.
    """
    if sys.platform == 'darwin':
        proxies = get_macos_system_proxy()
    elif sys.platform.startswith('win'):
        proxies = get_windows_system_proxy()
    else:
        logger.debug(f"Proxy auto-detection not supported on {sys.platform}")
        return None
    
    return proxies


def test_proxy_connectivity(proxy_url: str, timeout: float = 2.0) -> bool:
    """
    Test if a proxy server is actually reachable and working.
    
    This function attempts to connect to the proxy server to verify it's running.
    This prevents setting proxy environment variables when the proxy service
    is configured but not actually running.
    
    Args:
        proxy_url: Proxy URL in format "http://host:port" or "https://host:port"
        timeout: Connection timeout in seconds (default: 2.0)
    
    Returns:
        True if proxy is reachable, False otherwise
    """
    try:
        # Parse proxy URL
        # Remove protocol prefix (http:// or https://)
        if proxy_url.startswith('http://'):
            host_port = proxy_url[7:]
        elif proxy_url.startswith('https://'):
            host_port = proxy_url[8:]
        else:
            host_port = proxy_url
        
        # Split host and port
        if ':' in host_port:
            host, port_str = host_port.split(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                logger.debug(f"Invalid proxy port: {port_str}")
                return False
        else:
            logger.debug(f"Proxy URL missing port: {proxy_url}")
            return False
        
        # Test TCP connection to proxy
        # Use getaddrinfo to support both IPv4 and IPv6
        try:
            # Get address info for the host (supports both IPv4 and IPv6)
            addr_info = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            raise  # Re-raise to be caught by outer exception handler
        
        # Try to connect to the first available address
        for family, socktype, proto, canonname, sockaddr in addr_info:
            try:
                sock = socket.socket(family, socktype, proto)
                sock.settimeout(timeout)
                result = sock.connect_ex(sockaddr)
                sock.close()
                
                if result == 0:
                    return True
            except Exception:
                continue
        
        # All connection attempts failed
        # Use debug level since proxy unavailability is normal (user may not have proxy service running)
        logger.debug(f"❌ Proxy connectivity test failed: {proxy_url} (connection refused)")
        return False
            
    except socket.gaierror as e:
        logger.debug(f"❌ Proxy connectivity test failed: {proxy_url} (DNS resolution failed: {e})")
        return False
    except socket.timeout:
        logger.debug(f"❌ Proxy connectivity test failed: {proxy_url} (connection timeout)")
        return False
    except Exception as e:
        logger.debug(f"❌ Proxy connectivity test failed: {proxy_url} (error: {e})")
        return False


def filter_available_proxies(proxies: Dict[str, str]) -> Optional[Dict[str, str]]:
    """
    Filter proxy dictionary to only include proxies that are actually reachable.
    
    Args:
        proxies: Dict with protocol as key (e.g., 'http://') and proxy URL as value
    
    Returns:
        Dict with only reachable proxies, or None if no proxies are available
    """
    if not proxies:
        return None
    
    available_proxies = {}
    for protocol, proxy_url in proxies.items():
        if test_proxy_connectivity(proxy_url):
            available_proxies[protocol] = proxy_url
        else:
            logger.debug(f"⚠️  Skipping unavailable proxy {protocol}: {proxy_url}")
    
    return available_proxies if available_proxies else None

def apply_direct_connection_baseline() -> bool:
    cleared = False
    try:
        for key in list(os.environ.keys()):
            if key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
                try:
                    del os.environ[key]
                    cleared = True
                except Exception:
                    pass
        os.environ['NO_PROXY'] = '*'
        os.environ['no_proxy'] = '*'
        os.environ['CURL_NO_PROXY'] = '*'
    except Exception:
        pass
    return cleared

class ProxyManager:
    """
    Dynamic proxy manager that monitors proxy availability and updates environment variables.
    
    This class provides a standard solution for handling proxy state changes:
    - Monitors proxy availability in the background
    - Automatically updates environment variables when proxy state changes
    - Handles all protocols (HTTP, HTTPS, WebSocket, Socket) transparently
    - No need to modify application code or third-party libraries
    
    Standard usage:
        manager = ProxyManager()
        manager.start()  # Start background monitoring
        
    The manager will:
    1. Detect system proxy settings
    2. Test proxy connectivity
    3. Set/clear environment variables based on proxy availability
    4. Periodically re-check proxy status
    5. Update environment variables when proxy state changes
    """
    
    def __init__(self, check_interval: float = 30.0, connectivity_timeout: float = 2.0):
        """
        Initialize proxy manager.
        
        Args:
            check_interval: How often to check proxy status (seconds), default 30s
            connectivity_timeout: Proxy connectivity test timeout (seconds), default 2s
        """
        self.check_interval = check_interval
        self.connectivity_timeout = connectivity_timeout
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._current_proxies: Optional[Dict[str, str]] = None
        self._env_proxies_set = False
        self._callbacks: List[Callable[[Optional[Dict[str, str]]], None]] = []
    
    def _update_proxy_environment(self, proxies: Optional[Dict[str, str]]):
        """
        Update environment variables based on proxy availability.
        Thread-safe operation.
        """
        # Track if we need to notify callbacks (outside the lock)
        should_notify = False
        notify_proxies = None
        
        with self._lock:
            # Check if state changed (compare dict contents, not object reference)
            if proxies is None and self._current_proxies is None:
                return  # No change
            if proxies is not None and self._current_proxies is not None:
                if proxies == self._current_proxies:
                    return  # No change
            # State changed (None -> dict, dict -> None, or dict -> different dict)
            
            # Clear existing proxy environment variables if proxies are unavailable
            if not proxies:
                if self._env_proxies_set:
                    # Clear proxy env vars
                    for key in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy']:
                        if key in os.environ:
                            del os.environ[key]
                            logger.debug(f"🗑️  Cleared {key} (proxy unavailable)")
                    # Force disable proxies explicitly for all libraries
                    os.environ['NO_PROXY'] = '*'
                    os.environ['no_proxy'] = '*'
                    self._env_proxies_set = False
                    self._current_proxies = None
                    logger.info("🌐 Proxy environment cleared (NO_PROXY=*) - using direct connection")
                    
                    # Schedule callback notification (after releasing lock)
                    should_notify = True
                    notify_proxies = None
                else:
                    # No change - proxy was already cleared
                    return
            else:
                # Set proxy environment variables
                http_proxy = proxies.get('http://')
                https_proxy = proxies.get('https://')
                
                if https_proxy:
                    os.environ['HTTPS_PROXY'] = https_proxy
                    os.environ['https_proxy'] = https_proxy
                    logger.debug(f"✅ Set HTTPS_PROXY: {https_proxy}")
                
                if http_proxy:
                    os.environ['HTTP_PROXY'] = http_proxy
                    os.environ['http_proxy'] = http_proxy
                    logger.debug(f"✅ Set HTTP_PROXY: {http_proxy}")
                
                # Always set NO_PROXY for local/LAN network
                no_proxy_list = [
                    'localhost',
                    '127.0.0.1',
                    '::1',
                    '.local',
                    '.lan',
                    '.home',
                    '.internal',
                    '10.0.0.0/8',
                    '172.16.0.0/12',
                    '192.168.0.0/16',
                    '47.120.48.82',  # Cloud API server
                    '52.204.81.197',  # Cloud API server
                ]
                no_proxy = ','.join(no_proxy_list)
                os.environ['NO_PROXY'] = no_proxy
                os.environ['no_proxy'] = no_proxy
                
                self._env_proxies_set = True
                self._current_proxies = proxies.copy()
                
                proxy_info = f"HTTP: {http_proxy or 'N/A'}, HTTPS: {https_proxy or 'N/A'}"
                logger.info(f"🌐 Proxy environment updated: {proxy_info}")
                
                # Schedule callback notification (after releasing lock)
                should_notify = True
                notify_proxies = proxies.copy()
        
        # Notify callbacks OUTSIDE the lock to avoid deadlock
        if should_notify:
            self._notify_callbacks(notify_proxies)
    
    def _monitor_loop(self):
        """
        Background monitoring loop - checks proxy status periodically.
        
        This runs in a separate daemon thread, so it won't block application shutdown.
        All network operations (proxy detection, connectivity testing) happen here.
        """
        logger.info(f"🔄 Starting proxy monitor (background thread, check_interval={self.check_interval}s)")
        
        # Do initial check immediately (but in background thread, so non-blocking)
        try:
            logger.info("🔍 Performing initial proxy check in background...")
            self._do_proxy_check()
        except Exception as e:
            logger.warning(f"Error in initial proxy check: {e}", exc_info=True)
        
        check_count = 0
        try:
            while not self._stop_event.is_set():
                # Wait for next check or stop signal
                waited = self._stop_event.wait(self.check_interval)
                if waited:  # stop_event was set, exit loop
                    break
                
                check_count += 1
                # Perform periodic proxy check
                try:
                    self._do_proxy_check()
                except Exception as e:
                    logger.warning(f"Error in proxy monitor loop (check #{check_count}): {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Fatal error in proxy monitor loop: {e}", exc_info=True)
        finally:
            # Ensure thread reference is cleared on exit (even on unexpected exit)
            # Use lock to safely clear reference if this thread is still the active one
            with self._lock:
                # Only clear if this is the current active thread (prevent race condition)
                if self._monitor_thread == threading.current_thread():
                    self._monitor_thread = None
            logger.info(f"🛑 Proxy monitor stopped (performed {check_count} checks)")
    
    def start(self):
        """
        Start background proxy monitoring (non-blocking).
        
        This method returns immediately. The initial proxy check happens
        asynchronously in the background thread to avoid blocking startup.
        """
        # Clean up dead thread reference if exists
        if self._monitor_thread is not None:
            if self._monitor_thread.is_alive():
                logger.warning("Proxy monitor already running")
                return
            else:
                # Thread is dead but reference exists, clean it up
                logger.debug("Cleaning up dead thread reference")
                self._monitor_thread = None
        
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="ProxyMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("✅ Proxy manager started (background thread, non-blocking)")
    
    def stop(self):
        """Stop background proxy monitoring."""
        if self._monitor_thread is None:
            return
        
        # Set stop event to signal thread to exit
        self._stop_event.set()
        
        # Wait for thread to finish (with timeout to avoid blocking)
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
            if self._monitor_thread.is_alive():
                logger.warning("Proxy monitor thread did not stop within timeout, may still be running")
        
        # Clear thread reference (important for preventing leaks)
        self._monitor_thread = None
        logger.info("🛑 Proxy manager stopped")
    
    def _do_proxy_check(self):
        """
        Internal method to perform proxy check.
        This is called from background thread to avoid blocking.
        """
        # Check if env vars were manually set by user (outside our management)
        with self._lock:
            env_https = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            env_http = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
            manual_proxy_set = bool(env_https or env_http)
            was_set_by_manager = self._env_proxies_set

        if manual_proxy_set and not was_set_by_manager:
            # Validate manually set proxies; if unreachable, clear them so we fall back to direct/system detection
            try:
                proxies_to_test = {}
                if env_http:
                    proxies_to_test['http://'] = env_http
                if env_https:
                    proxies_to_test['https://'] = env_https

                reachable = False
                for _, purl in proxies_to_test.items():
                    if test_proxy_connectivity(purl, timeout=self.connectivity_timeout):
                        reachable = True
                        break

                if reachable:
                    logger.debug("⏭️  Proxy env vars manually set and reachable, skipping auto-detection")
                    return
                else:
                    # Clear stale/unreachable manual proxies
                    for key in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy']:
                        if key in os.environ:
                            del os.environ[key]
                    # Force disable proxies for all libs until a valid proxy is detected
                    os.environ['NO_PROXY'] = '*'
                    os.environ['no_proxy'] = '*'
                    logger.info("🌐 Cleared unreachable manual proxy env vars (NO_PROXY=*) - using direct/system detection")
            except Exception:
                # In case of any error, do not block; proceed to system detection
                pass

        # Get system proxy settings (may involve system calls, but in background thread)
        system_proxies = get_system_proxy()
        
        if system_proxies:
            # Test connectivity for all proxies (network operations in background thread)
            available_proxies = {}
            for protocol, proxy_url in system_proxies.items():
                if test_proxy_connectivity(proxy_url, timeout=self.connectivity_timeout):
                    available_proxies[protocol] = proxy_url
                else:
                    logger.debug(f"❌ Proxy {protocol} is not reachable")
            
            # Update environment variables (only if state changed)
            self._update_proxy_environment(
                available_proxies if available_proxies else None
            )
        else:
            # No system proxy configured, clear env vars if we set them
            self._update_proxy_environment(None)
    
    def check_now(self):
        """
        Manually trigger an immediate proxy status check.
        
        Note: This method may block briefly for network operations.
        For non-blocking operation, ensure the proxy manager is running
        in background mode and let it handle checks automatically.
        """
        try:
            self._do_proxy_check()
        except Exception as e:
            logger.warning(f"Error in manual proxy check: {e}")
    
    def register_callback(self, callback: Callable[[Optional[Dict[str, str]]], None]):
        """
        Register a callback function to be notified when proxy state changes.
        
        The callback will be called with:
        - None if proxy is unavailable/cleared
        - Dict[str, str] with available proxies (e.g., {'http://': 'http://proxy:8080', 'https://': 'http://proxy:8080'})
        
        Args:
            callback: Callable that takes Optional[Dict[str, str]] as parameter
        
        Returns:
            Callable to unregister the callback (can be called later)
        """
        with self._lock:
            self._callbacks.append(callback)
        
        def unregister():
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)
        
        return unregister
    
    def _notify_callbacks(self, proxies: Optional[Dict[str, str]]):
        """Notify all registered callbacks about proxy state change."""
        callbacks_copy = []
        with self._lock:
            callbacks_copy = self._callbacks.copy()
        
        for callback in callbacks_copy:
            try:
                callback(proxies)
            except Exception as e:
                logger.warning(f"Error in proxy state change callback: {e}")
    
    def get_current_proxies(self) -> Optional[Dict[str, str]]:
        """
        Get current proxy configuration (thread-safe).
        
        Returns:
            Dict with current proxy URLs, or None if no proxy is available
        """
        with self._lock:
            return self._current_proxies.copy() if self._current_proxies else None


# Global proxy manager instance
_proxy_manager: Optional[ProxyManager] = None


def initialize_proxy_environment(
    enable: Optional[bool] = None,
    enable_background_monitoring: bool = True, 
    check_interval: float = 30.0
):
    """
    Initialize proxy environment variables from system settings (cross-platform).
    
    This is the standard solution for proxy management that handles:
    - Initial proxy detection and setup
    - Dynamic proxy state monitoring (proxy can be started/stopped anytime)
    - Automatic environment variable updates
    - Transparent handling for all protocols (HTTP, HTTPS, WebSocket, Socket)
    - No need to modify application code or third-party libraries
    
    This function should be called once at application startup (in main.py).
    
    Standard behavior:
    1. Checks if proxy management is enabled (via parameter or ECAN_PROXY_ENABLED env var)
    2. Checks if proxy environment variables are already manually set (user override)
    3. Reads system proxy settings (macOS/Windows)
    4. Tests proxy connectivity before setting environment variables
    5. Sets HTTP_PROXY and HTTPS_PROXY only if proxies are available
    6. If enable_background_monitoring=True, starts a background thread that:
       - Periodically checks proxy status (default: every 30 seconds)
       - Automatically updates environment variables when proxy state changes
       - Handles proxy start/stop scenarios transparently
    
    This prevents setting proxy environment variables when the proxy service
    is configured but not running, and automatically adapts when proxy state changes.
    
    After calling this function, all HTTP libraries (httpx, requests, urllib, etc.)
    will automatically use the proxy without any additional configuration.
    
    Args:
        enable: If False, disables proxy management entirely. If None (default), 
               checks ECAN_PROXY_ENABLED environment variable. If True, enables proxy management.
               When disabled, the function returns immediately without any proxy setup.
        enable_background_monitoring: If True (default), starts background monitoring
                                     to handle proxy state changes dynamically.
                                     Only effective if enable=True.
        check_interval: How often to check proxy status in background (seconds).
                       Only effective if enable=True and enable_background_monitoring=True.
    
    Environment Variables:
        ECAN_PROXY_ENABLED: Set to "0", "false", "False" to disable proxy management.
                           Set to "1", "true", "True" to enable (or leave unset for default).
    
    Supported platforms:
    - macOS: Reads from scutil --proxy
    - Windows: Reads from registry (Internet Settings)
    - Linux: Not yet supported (manual configuration required)
    
    Limitations:
    - Only works with system-level global proxy settings
    - Does NOT work with application-level proxy (e.g., Clash enhanced mode)
    - If using TUN mode (virtual network interface), this is not needed
    
    Alternative solutions if this doesn't work:
    1. Use TUN mode in your proxy tool (Clash/V2Ray) - recommended
    2. Manually set environment variables in system settings
    3. Configure proxy in the application settings (if available)
    """
    global _proxy_manager
    
    # Check if proxy management is enabled
    # Priority: function parameter > environment variable > default (True)
    if enable is None:
        # Check environment variable
        env_enable = os.environ.get('ECAN_PROXY_ENABLED', '').strip().lower()
        if env_enable in ('0', 'false', 'no', 'off', 'disable', 'disabled'):
            enable = False
            logger.info("🌐 Proxy management disabled via ECAN_PROXY_ENABLED environment variable")
        elif env_enable in ('1', 'true', 'yes', 'on', 'enable', 'enabled'):
            enable = True
            logger.info("🌐 Proxy management enabled via ECAN_PROXY_ENABLED environment variable")
        else:
            # Default: enabled
            enable = True
    elif enable is False:
        logger.info("🌐 Proxy management disabled via function parameter")
    else:
        logger.info("🌐 Proxy management enabled via function parameter")
    
    # If disabled, return immediately
    if not enable:
        logger.info("⏭️  Skipping proxy initialization - proxy management is disabled")
        # Stop any existing proxy manager if running
        if _proxy_manager is not None:
            _proxy_manager.stop()
            _proxy_manager = None
        return
    
    # Check if environment variables are already manually set by user (before we start)
    # Note: We'll still monitor if background monitoring is enabled, so we can detect
    # when user clears the manual proxy and switch to system proxy detection
    manual_proxy_detected = bool(os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY'))
    if manual_proxy_detected:
        logger.info("🌐 Proxy environment variables already set (may be user-set), will monitor for changes")
        # Continue with initialization to enable monitoring, but _do_proxy_check will skip
        # auto-detection if proxy is still manually set
    
    # Create and configure proxy manager
    if enable_background_monitoring:
        # Stop existing proxy manager if any (prevent thread leakage)
        if _proxy_manager is not None:
            logger.debug("Stopping existing proxy manager before creating new one")
            _proxy_manager.stop()
            _proxy_manager = None
        
        _proxy_manager = ProxyManager(check_interval=check_interval)
        # Start background monitoring (non-blocking)
        # Initial check will happen in background thread, not blocking startup
        _proxy_manager.start()
        logger.info(
            f"✅ Proxy manager initialized with background monitoring "
            f"(check interval: {check_interval}s, initial check will happen in background)"
        )
        # Note: First proxy detection happens in background thread to avoid blocking startup
    else:
        # One-time initialization without background monitoring (background compatible)
        # Even without monitoring, we still do the initial check in a background thread
        # to avoid blocking startup/UI
        logger.info("🔍 Scheduling one-time proxy initialization in background thread...")
        
        def _do_one_time_init():
            """Perform one-time proxy initialization in background thread."""
            try:
                logger.debug("🔍 Performing one-time proxy initialization in background...")
                system_proxies = get_system_proxy()
                if not system_proxies:
                    logger.debug("No system proxy configured")
                    return
                
                available_proxies = filter_available_proxies(system_proxies)
                if not available_proxies:
                    logger.warning(
                        "⚠️  System proxy is configured but not available (service may be stopped). "
                        "Skipping proxy setup - requests will use direct connection."
                    )
                    return
                
                # Set environment variables only for available proxies
                http_proxy = available_proxies.get('http://')
                https_proxy = available_proxies.get('https://')
                
                if https_proxy:
                    os.environ['HTTPS_PROXY'] = https_proxy
                    os.environ['https_proxy'] = https_proxy
                    logger.info(f"🌐 Set HTTPS_PROXY from system settings: {https_proxy}")
                
                if http_proxy:
                    os.environ['HTTP_PROXY'] = http_proxy
                    os.environ['http_proxy'] = http_proxy
                    logger.info(f"🌐 Set HTTP_PROXY from system settings: {http_proxy}")
                
                # Set NO_PROXY to exclude local and LAN network
                no_proxy_list = [
                    'localhost',
                    '127.0.0.1',
                    '::1',
                    '.local',
                    '.lan',
                    '.home',
                    '.internal',
                    '10.0.0.0/8',
                    '172.16.0.0/12',
                    '192.168.0.0/16',
                    '47.120.48.82',  # Cloud API server
                    '52.204.81.197',  # Cloud API server
                ]
                no_proxy = ','.join(no_proxy_list)
                os.environ['NO_PROXY'] = no_proxy
                os.environ['no_proxy'] = no_proxy
                logger.info(f"🌐 Set NO_PROXY for local/LAN: {no_proxy}")
                
                logger.info("✅ Proxy environment initialized - all external requests will use proxy")
                logger.info("✅ Proxy settings will be inherited by all subprocess (including lightrag_server)")
            except Exception as e:
                logger.warning(f"Error in one-time proxy initialization: {e}")
        
        # Run in background thread (daemon, so won't block shutdown)
        init_thread = threading.Thread(
            target=_do_one_time_init,
            name="ProxyInit",
            daemon=True
        )
        init_thread.start()
        logger.info("✅ Proxy initialization scheduled in background thread (non-blocking)")


def get_proxy_manager() -> Optional[ProxyManager]:
    """
    Get the global proxy manager instance.
    
    Returns:
        ProxyManager instance if initialized, None otherwise
    """
    return _proxy_manager


def is_proxy_management_enabled() -> bool:
    """
    Check if proxy management is currently enabled.
    
    Returns:
        True if proxy management is enabled, False otherwise
    """
    # Check environment variable first
    env_enable = os.environ.get('ECAN_PROXY_ENABLED', '').strip().lower()
    if env_enable in ('0', 'false', 'no', 'off', 'disable', 'disabled'):
        return False
    elif env_enable in ('1', 'true', 'yes', 'on', 'enable', 'enabled'):
        return True
    else:
        # Default: enabled if proxy manager exists
        return _proxy_manager is not None


def disable_proxy_management():
    """
    Disable proxy management and stop background monitoring.
    
    This will:
    - Stop the proxy manager if running
    - Clear any proxy-related environment variables set by the manager
    - Note: This will NOT clear manually set environment variables
    """
    global _proxy_manager
    
    if _proxy_manager is not None:
        logger.info("🛑 Disabling proxy management...")
        _proxy_manager.stop()
        
        # Clear proxy environment variables set by manager
        with _proxy_manager._lock:
            if _proxy_manager._env_proxies_set:
                for key in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy']:
                    if key in os.environ:
                        del os.environ[key]
                        logger.debug(f"🗑️  Cleared {key}")
                _proxy_manager._env_proxies_set = False
                _proxy_manager._current_proxies = None
        
        _proxy_manager = None
        logger.info("✅ Proxy management disabled")
    else:
        logger.debug("Proxy management was not enabled")


def enable_proxy_management(enable_background_monitoring: bool = True, check_interval: float = 30.0):
    """
    Enable proxy management and start monitoring.
    
    Args:
        enable_background_monitoring: If True, starts background monitoring
        check_interval: How often to check proxy status in background (seconds)
    """
    # Call initialize_proxy_environment to enable
    initialize_proxy_environment(
        enable=True,
        enable_background_monitoring=enable_background_monitoring,
        check_interval=check_interval
    )


def get_proxy_config_for_library(library_name: str = "httpx") -> Optional[Dict[str, str]]:
    """
    Get proxy configuration for libraries that don't support environment variables.
    
    This is useful for libraries like websocket that require manual proxy configuration.
    
    Args:
        library_name: Name of the library (currently only "websocket" is supported)
    
    Returns:
        Dict with proxy configuration, or None if no proxy is available.
        For websocket: Returns {'host': '...', 'port': ...}
        For other libraries: Returns proxy URLs dict
    """
    proxy_manager = get_proxy_manager()
    if proxy_manager is None:
        # Fallback: read from environment
        https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        if not https_proxy and not http_proxy:
            return None
        proxies = {}
        if https_proxy:
            proxies['https://'] = https_proxy
        if http_proxy:
            proxies['http://'] = http_proxy
    else:
        proxies = proxy_manager.get_current_proxies()
    
    if not proxies:
        return None
    
    if library_name == "websocket":
        # Parse proxy URL for websocket
        from urllib.parse import urlparse
        proxy_url = proxies.get('https://') or proxies.get('http://')
        if proxy_url:
            try:
                parsed = urlparse(proxy_url)
                return {
                    'host': parsed.hostname,
                    'port': parsed.port or (8080 if 'http' in proxy_url else 443),
                    'url': proxy_url
                }
            except Exception as e:
                logger.warning(f"Failed to parse proxy URL for websocket: {e}")
                return None
    
    # For other libraries, return proxy URLs
    return proxies


def get_proxy_for_httpx() -> Optional[str]:
    """
    Get proxy configuration for httpx (deprecated - use initialize_proxy_environment instead).
    
    Priority:
    1. Environment variables (HTTP_PROXY, HTTPS_PROXY)
    2. System proxy settings (automatic detection)
    
    Returns:
        Proxy URL string for httpx, or None if no proxy is configured.
    """
    # Check environment variables first
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    
    if https_proxy:
        return https_proxy
    elif http_proxy:
        return http_proxy
    
    # Fall back to system proxy
    system_proxies = get_system_proxy()
    if system_proxies:
        return system_proxies.get('https://') or system_proxies.get('http://')
    
    return None
