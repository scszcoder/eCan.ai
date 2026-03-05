"""
ryoais Device Discovery Handler

Handles mDNS/DNS-SD based device discovery for ryoais inference servers.
"""

import traceback
import time
from typing import Any, Optional, Dict, List
try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    _HAS_ZEROCONF = True
except ImportError:
    _HAS_ZEROCONF = False
    Zeroconf = None  # type: ignore
    ServiceBrowser = None  # type: ignore
    ServiceListener = object  # type: ignore – base class fallback

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


class RyoAISServiceListener(ServiceListener):
    """Listener for ryoais mDNS/DNS-SD service discovery"""
    
    def __init__(self, zeroconf: Zeroconf):
        self.zeroconf = zeroconf
        self.devices: Dict[str, Dict[str, Any]] = {}
    
    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        """Called when a new service is discovered"""
        try:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                # Parse service information
                addresses = [addr for addr in info.parsed_addresses()]
                port = info.port
                properties = {k.decode('utf-8'): v.decode('utf-8') 
                             for k, v in info.properties.items()}
                
                # Get primary IP address
                local_ip = addresses[0] if addresses else 'unknown'
                
                # mDNS TXT record fields - 设备标识
                sn = properties.get('sn', 'unknown')
                uuid = properties.get('uuid', 'unknown')
                mac = properties.get('mac', 'unknown')
                hostname = properties.get('hostname', 'unknown')
                model = properties.get('model', 'unknown')
                device_name = properties.get('name', 'unknown')
                
                # mDNS TXT record fields - 版本信息
                version = properties.get('version', 'unknown')
                build_time = properties.get('build_time', 'unknown')
                git_commit = properties.get('git_commit', 'unknown')
                
                # mDNS TXT record fields - 服务信息
                environment = properties.get('environment', 'unknown')
                api_types = properties.get('api_types', '')
                api_version = properties.get('api_version', 'unknown')
                services = properties.get('services', '')
                
                # mDNS TXT record fields - 系统信息
                platform = properties.get('platform', 'unknown')
                python_version = properties.get('python_version', 'unknown')
                
                # mDNS TXT record fields - 网络信息
                ip = properties.get('ip', local_ip)
                port_str = properties.get('port', str(port))
                url = properties.get('url', f"http://{ip}:{port_str}")
                
                # mDNS TXT record fields - 描述
                description = properties.get('description', '')
                
                device_info = {
                    # mDNS TXT record fields - 设备标识
                    'sn': sn,
                    'uuid': uuid,
                    'mac': mac,
                    'hostname': hostname,
                    'model': model,
                    'name': device_name,
                    
                    # mDNS TXT record fields - 版本信息
                    'version': version,
                    'build_time': build_time,
                    'git_commit': git_commit,
                    
                    # mDNS TXT record fields - 服务信息
                    'environment': environment,
                    'api_types': api_types.split(',') if api_types else [],
                    'api_version': api_version,
                    'services': services.split(',') if services else [],
                    
                    # mDNS TXT record fields - 系统信息
                    'platform': platform,
                    'python_version': python_version,
                    
                    # mDNS TXT record fields - 网络信息
                    'ip': ip,
                    'port': port_str,
                    'url': url,
                    
                    # mDNS TXT record fields - 描述
                    'description': description,
                    
                    # mDNS Discovery metadata
                    'service_name': name,
                    'service_type': service_type,
                    
                    # Legacy fields for backward compatibility
                    'device_uuid': uuid,  # 向后兼容
                    'short_uuid': uuid[:12] if uuid != 'unknown' else 'unknown',
                    'addresses': addresses,
                    'local_ip': local_ip,
                    'properties': properties,
                    'discovered_at': time.time()
                }
                
                self.devices[uuid] = device_info
                logger.info(f"[ryoais] Discovered device: {device_name} ({sn}) at {url}")
                
        except Exception as e:
            logger.error(f"[ryoais] Error processing service {name}: {e}")
    
    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        """Called when a service goes offline"""
        # Find and remove device by name
        for uuid, device in list(self.devices.items()):
            if device['name'] == name:
                logger.info(f"[ryoais] Device offline: {name} ({uuid[:8]}...)")
                del self.devices[uuid]
                break
    
    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        """Called when a service is updated"""
        # Re-add the service to update its info
        self.add_service(zeroconf, service_type, name)


@IPCHandlerRegistry.background_handler('ryoais.scanDevices')
def handle_scan_devices(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Scan for ryoais devices on the local network using mDNS/DNS-SD.
    
    Args:
        request: IPC request object
        params: Optional parameters
            - timeout: int - Scan timeout in seconds (default: 5)
            - environment: str - Filter by environment (optional)
    
    Returns:
        IPCResponse with discovered devices
    """
    if not _HAS_ZEROCONF:
        return create_error_response(request, 'MISSING_DEPENDENCY', 'zeroconf package is not installed')
    try:
        timeout = params.get('timeout', 5) if params else 5
        filter_env = params.get('environment') if params else None
        
        logger.info(f"[ryoais] Starting device scan (timeout: {timeout}s, filter: {filter_env or 'none'})")
        
        # Create Zeroconf instance
        zeroconf = Zeroconf()
        listener = RyoAISServiceListener(zeroconf)
        
        # Start browsing for ryoais services
        browser = ServiceBrowser(zeroconf, "_ryoais._tcp.local.", listener)
        
        # Wait for discovery using Event.wait() instead of time.sleep() for better responsiveness
        # This allows the wait to be interrupted if needed
        import threading
        stop_event = threading.Event()
        stop_event.wait(timeout)  # More responsive than time.sleep()
        
        # Get discovered devices
        devices = list(listener.devices.values())
        
        # Apply environment filter if specified
        if filter_env:
            devices = [d for d in devices if d['environment'] == filter_env]
        
        # Clean up
        browser.cancel()
        zeroconf.close()
        
        logger.info(f"[ryoais] Scan complete. Found {len(devices)} device(s)")
        
        return create_success_response(request, {
            'devices': devices,
            'count': len(devices),
            'scan_duration': timeout
        })
        
    except Exception as e:
        logger.error(f"[ryoais] Error scanning devices: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'SCAN_ERROR',
            f"Failed to scan for devices: {str(e)}"
        )


@IPCHandlerRegistry.handler('ryoais.getDeviceInfo')
def handle_get_device_info(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Get detailed information about a specific ryoais device.
    
    Args:
        request: IPC request object
        params: Required parameters
            - url: str - Device URL (e.g., 'http://192.168.1.100:8000')
    
    Returns:
        IPCResponse with device information
    """
    try:
        if not params or 'url' not in params:
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Device URL is required'
            )
        
        url = params['url']
        
        logger.info(f"[ryoais] Fetching device info from: {url}")
        
        # Import requests here to avoid dependency issues
        import requests
        
        # Fetch device discovery info
        try:
            response = requests.get(f"{url}/api/discovery/info", timeout=5)
            response.raise_for_status()
            device_info = response.json()
            
            logger.info(f"[ryoais] Successfully fetched info for device: {device_info.get('hostname', 'unknown')}")
            
            return create_success_response(request, {
                'device_info': device_info,
                'url': url
            })
            
        except requests.exceptions.Timeout:
            return create_error_response(
                request,
                'TIMEOUT_ERROR',
                f"Request to {url} timed out"
            )
        except requests.exceptions.ConnectionError:
            return create_error_response(
                request,
                'CONNECTION_ERROR',
                f"Cannot connect to {url}"
            )
        except requests.exceptions.HTTPError as e:
            return create_error_response(
                request,
                'HTTP_ERROR',
                f"HTTP error: {e.response.status_code}"
            )
        except Exception as e:
            return create_error_response(
                request,
                'REQUEST_ERROR',
                f"Failed to fetch device info: {str(e)}"
            )
        
    except Exception as e:
        logger.error(f"[ryoais] Error getting device info: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'INFO_ERROR',
            f"Failed to get device info: {str(e)}"
        )


@IPCHandlerRegistry.handler('ryoais.getDeviceStatus')
def handle_get_device_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Get the network discovery status of a ryoais device.
    
    Args:
        request: IPC request object
        params: Required parameters
            - url: str - Device URL
    
    Returns:
        IPCResponse with device status
    """
    try:
        if not params or 'url' not in params:
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Device URL is required'
            )
        
        url = params['url']
        
        logger.info(f"[ryoais] Fetching device status from: {url}")
        
        import requests
        
        try:
            response = requests.get(f"{url}/api/discovery/status", timeout=5)
            response.raise_for_status()
            status_info = response.json()
            
            return create_success_response(request, {
                'status': status_info,
                'url': url
            })
            
        except Exception as e:
            return create_error_response(
                request,
                'STATUS_ERROR',
                f"Failed to fetch device status: {str(e)}"
            )
        
    except Exception as e:
        logger.error(f"[ryoais] Error getting device status: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'STATUS_ERROR',
            f"Failed to get device status: {str(e)}"
        )
