"""
Cross-Platform System Proxy Detection

This module provides functionality to read system proxy settings on both macOS and Windows,
and automatically set environment variables at application startup.

Usage:
    In main.py, call initialize_proxy_environment() at startup:
    
    from agent.ec_skills.system_proxy import initialize_proxy_environment
    initialize_proxy_environment()
    
This will automatically detect and set proxy environment variables,
making all HTTP libraries (httpx, requests, etc.) work seamlessly.
"""

import subprocess
import re
import os
import sys
from typing import Optional, Dict
from utils.logger_helper import logger_helper as logger


def get_macos_system_proxy() -> Optional[Dict[str, str]]:
    """
    Read macOS system proxy settings using scutil command.
    
    Returns:
        Dict with 'http://' and 'https://' proxy URLs, or None if no proxy is configured.
    """
    try:
        result = subprocess.run(
            ['scutil', '--proxy'],
            capture_output=True,
            text=True,
            timeout=2
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
    
    if proxies:
        logger.debug(f"📡 Detected system proxy: {proxies}")
    
    return proxies


def initialize_proxy_environment():
    """
    Initialize proxy environment variables from system settings (cross-platform).
    
    This function should be called once at application startup (in main.py).
    It will:
    1. Check if proxy environment variables are already set
    2. If not, read system proxy settings (macOS/Windows)
    3. Set HTTP_PROXY and HTTPS_PROXY environment variables
    
    After calling this function, all HTTP libraries (httpx, requests, urllib, etc.)
    will automatically use the proxy without any additional configuration.
    
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
    # Check if environment variables are already set
    if os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY'):
        logger.info("🌐 Proxy environment variables already set, skipping auto-detection")
        return
    
    # Read system proxy
    system_proxies = get_system_proxy()
    if not system_proxies:
        logger.debug("No system proxy configured")
        return
    
    # Set environment variables
    http_proxy = system_proxies.get('http://')
    https_proxy = system_proxies.get('https://')
    
    if https_proxy:
        os.environ['HTTPS_PROXY'] = https_proxy
        os.environ['https_proxy'] = https_proxy  # Some libraries check lowercase
        logger.info(f"🌐 Set HTTPS_PROXY from system settings: {https_proxy}")
    
    if http_proxy:
        os.environ['HTTP_PROXY'] = http_proxy
        os.environ['http_proxy'] = http_proxy  # Some libraries check lowercase
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
    ]
    no_proxy = ','.join(no_proxy_list)
    os.environ['NO_PROXY'] = no_proxy
    os.environ['no_proxy'] = no_proxy
    logger.info(f"🌐 Set NO_PROXY for local/LAN: {no_proxy}")
    
    logger.info("✅ Proxy environment initialized - all external requests will use proxy")
    logger.info("✅ Proxy settings will be inherited by all subprocess (including lightrag_server)")


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
