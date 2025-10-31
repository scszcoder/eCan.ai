"""
macOS System Proxy Detection

This module provides functionality to read macOS system proxy settings
and automatically set environment variables at application startup.

Usage:
    In main.py, call initialize_proxy_environment() at startup:
    
    from agent.ec_skills.macos_proxy import initialize_proxy_environment
    initialize_proxy_environment()
    
This will automatically detect and set proxy environment variables,
making all HTTP libraries (httpx, requests, etc.) work seamlessly.
"""

import subprocess
import re
import os
from typing import Optional, Dict
from utils.logger_helper import logger_helper as logger


def get_macos_system_proxy() -> Optional[Dict[str, str]]:
    """
    Read macOS system proxy settings using scutil command.
    
    Returns:
        Dict with 'http' and 'https' proxy URLs, or None if no proxy is configured.
    """
    try:
        # Use scutil to read system proxy configuration
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
        
        if proxies:
            logger.debug(f"📡 Detected macOS system proxy: {proxies}")
            return proxies
        
        return None
        
    except Exception as e:
        logger.debug(f"Failed to read macOS system proxy: {e}")
        return None


def initialize_proxy_environment():
    """
    Initialize proxy environment variables from macOS system settings.
    
    This function should be called once at application startup (in main.py).
    It will:
    1. Check if proxy environment variables are already set
    2. If not, read macOS system proxy settings (global proxy only)
    3. Set HTTP_PROXY and HTTPS_PROXY environment variables
    
    After calling this function, all HTTP libraries (httpx, requests, urllib, etc.)
    will automatically use the proxy without any additional configuration.
    
    Limitations:
    - Only works with system-level global proxy settings
    - Does NOT work with application-level proxy (e.g., Clash enhanced mode for specific apps)
    - If using TUN mode (virtual network interface), this is not needed as traffic is transparent
    
    Alternative solutions if this doesn't work:
    1. Use TUN mode in your proxy tool (Clash/V2Ray) - recommended
    2. Manually set environment variables in ~/.zshrc
    3. Configure proxy in the application settings (if available)
    
    This is the recommended approach - set environment variables once at startup,
    rather than passing proxy parameters everywhere.
    """
    # Check if environment variables are already set
    if os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY'):
        logger.info("🌐 Proxy environment variables already set, skipping auto-detection")
        return
    
    # Read macOS system proxy
    system_proxies = get_macos_system_proxy()
    if not system_proxies:
        logger.debug("No macOS system proxy configured")
        return
    
    # Set environment variables
    http_proxy = system_proxies.get('http://')
    https_proxy = system_proxies.get('https://')
    
    if https_proxy:
        os.environ['HTTPS_PROXY'] = https_proxy
        os.environ['https_proxy'] = https_proxy  # Some libraries check lowercase
        logger.info(f"🌐 Set HTTPS_PROXY from macOS system settings: {https_proxy}")
    
    if http_proxy:
        os.environ['HTTP_PROXY'] = http_proxy
        os.environ['http_proxy'] = http_proxy  # Some libraries check lowercase
        logger.info(f"🌐 Set HTTP_PROXY from macOS system settings: {http_proxy}")
    
    # Set NO_PROXY to exclude local and LAN network
    # Only bypass proxy for local/private network access
    # Note: If your proxy has issues with certain servers, add them here
    no_proxy_list = [
        'localhost',
        '127.0.0.1',
        '::1',
        '.local',        # Domains ending with .local
        '.lan',          # Common intranet suffix
        '.home',
        '.internal',
        '10.0.0.0/8',    # Private network (10.0.0.0/8)
        '172.16.0.0/12', # Private network (172.16.0.0/12)
        '192.168.0.0/16',# Private network (192.168.0.0/16)
        '47.120.48.82',  # Cloud API server (direct connection faster)
    ]
    no_proxy = ','.join(no_proxy_list)
    os.environ['NO_PROXY'] = no_proxy
    os.environ['no_proxy'] = no_proxy
    logger.info(f"🌐 Set NO_PROXY for local/LAN: {no_proxy}")
    
    logger.info("✅ Proxy environment initialized - all external requests will use proxy")


def get_proxy_for_httpx() -> Optional[str]:
    """
    Get proxy configuration for httpx.
    
    Note: This function is now deprecated. Use initialize_proxy_environment() at startup instead.
    
    Priority:
    1. Environment variables (HTTP_PROXY, HTTPS_PROXY) - if set by user or initialize_proxy_environment()
    2. macOS system proxy settings - automatic detection (fallback)
    
    Returns:
        Proxy URL string for httpx, or None if no proxy is configured.
        httpx uses a single proxy URL for all protocols.
    """
    # Check if environment variables are set (user's explicit configuration)
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    
    if https_proxy:
        logger.debug(f"🌐 Using HTTPS proxy from environment: {https_proxy}")
        return https_proxy
    elif http_proxy:
        logger.debug(f"🌐 Using HTTP proxy from environment: {http_proxy}")
        return http_proxy
    
    # Fall back to macOS system proxy
    system_proxies = get_macos_system_proxy()
    if system_proxies:
        # Prefer HTTPS proxy, fall back to HTTP proxy
        proxy_url = system_proxies.get('https://') or system_proxies.get('http://')
        if proxy_url:
            logger.debug(f"🌐 Using macOS system proxy: {proxy_url}")
            return proxy_url
    
    logger.debug("No proxy configured (neither environment variables nor system proxy)")
    return None
