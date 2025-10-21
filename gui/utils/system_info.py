"""
System Information Management Module

Provides system information retrieval, device identification, and performance monitoring
"""

import os
import platform
import socket
import subprocess
import time
from typing import Dict, Optional, Any

from utils.logger_helper import logger_helper as logger


class SystemInfoManager:
    """System Information Manager"""
    
    def __init__(self):
        self._cache = {}
        self._cache_timeout = 300  # 5-minute cache
        self._last_update = 0
    
    def get_friendly_machine_name(self) -> str:
        """Get user-friendly machine name"""
        cache_key = 'machine_name'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            machine_name = None
            
            # Method 1: Try to get system display name (macOS)
            if platform.system() == 'Darwin':
                try:
                    result = subprocess.run(['scutil', '--get', 'ComputerName'], 
                                          capture_output=True, text=True, timeout=3)
                    if result.returncode == 0 and result.stdout.strip():
                        machine_name = result.stdout.strip()
                except Exception as e:
                    logger.debug(f"Failed to get macOS computer name: {e}")
            
            # Method 2: Try to get Windows computer name
            elif platform.system() == 'Windows':
                try:
                    # Prefer COMPUTERNAME environment variable
                    machine_name = os.environ.get('COMPUTERNAME')
                    
                    # If not available, try using wmic for friendlier name
                    if not machine_name:
                        result = subprocess.run(['wmic', 'computersystem', 'get', 'name'], 
                                              capture_output=True, text=True, timeout=2)
                        if result.returncode == 0:
                            lines = result.stdout.strip().split('\n')
                            if len(lines) > 1:
                                machine_name = lines[1].strip()
                    
                    # Try to get user-friendly display name
                    if machine_name:
                        try:
                            # Get current username
                            username = os.environ.get('USERNAME', '')
                            if username and machine_name != username:
                                # If machine name is not username, combine for display
                                machine_name = f"{username}'s {machine_name}"
                        except Exception:
                            pass
                            
                except Exception as e:
                    logger.debug(f"Failed to get Windows computer name: {e}")
            
            # Method 3: Use username + system type
            if not machine_name:
                try:
                    username = os.getlogin()
                    system_type = "Mac" if platform.system() == 'Darwin' else platform.system()
                    machine_name = f"{username}'s {system_type}"
                except Exception as e:
                    logger.debug(f"Failed to generate username-based name: {e}")
            
            # Method 4: Fallback to hostname
            if not machine_name:
                machine_name = platform.node() or socket.gethostname()
            
            # Clean name (remove domain suffix, etc.)
            if machine_name and '.' in machine_name:
                machine_name = machine_name.split('.')[0]
            
            result = machine_name or "Unknown-Computer"
            self._cache[cache_key] = result
            logger.info(f"[SystemInfo] Machine name resolved: {result}")
            return result
            
        except Exception as e:
            logger.warning(f"[SystemInfo] Failed to get friendly machine name: {e}")
            return socket.gethostname() or "Unknown-Computer"
    
    def get_device_type(self) -> str:
        """Intelligently identify device type"""
        cache_key = 'device_type'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            system = platform.system()
            
            # macOS device type identification
            if system == 'Darwin':
                try:
                    result = subprocess.run(['sysctl', '-n', 'hw.model'], 
                                          capture_output=True, text=True, timeout=3)
                    if result.returncode == 0:
                        model = result.stdout.strip().lower()
                        if 'macbook' in model:
                            if 'air' in model:
                                device_type = "MacBook Air"
                            elif 'pro' in model:
                                device_type = "MacBook Pro"
                            else:
                                device_type = "MacBook"
                        elif 'imac' in model:
                            device_type = "iMac"
                        elif 'mac' in model:
                            if 'mini' in model:
                                device_type = "Mac mini"
                            elif 'pro' in model:
                                device_type = "Mac Pro"
                            elif 'studio' in model:
                                device_type = "Mac Studio"
                            else:
                                device_type = "Mac"
                        else:
                            device_type = "Mac Computer"
                    else:
                        device_type = "Mac Computer"
                except Exception as e:
                    logger.debug(f"Failed to get macOS device model: {e}")
                    device_type = "Mac Computer"
            
            # Windows device type identification
            elif system == 'Windows':
                try:
                    # Method 1: Check system type
                    result = subprocess.run(['wmic', 'computersystem', 'get', 'PCSystemType'], 
                                          capture_output=True, text=True, timeout=2)
                    if result.returncode == 0 and '2' in result.stdout:  # 2 = Mobile
                        device_type = "Windows Laptop"
                    else:
                        # Method 2: Check battery presence
                        try:
                            battery_result = subprocess.run(['wmic', 'path', 'win32_battery', 'get', 'name'], 
                                                          capture_output=True, text=True, timeout=2)
                            if battery_result.returncode == 0 and battery_result.stdout.strip():
                                # Has battery info, likely a laptop
                                lines = battery_result.stdout.strip().split('\n')
                                if len(lines) > 1 and any(line.strip() for line in lines[1:]):
                                    device_type = "Windows Laptop"
                                else:
                                    device_type = "Windows Desktop"
                            else:
                                device_type = "Windows Desktop"
                        except Exception:
                            device_type = "Windows Desktop"
                except Exception as e:
                    logger.debug(f"Failed to get Windows system type: {e}")
                    # Method 3: Fallback check - check for power management
                    try:
                        import os
                        if os.path.exists('C:\\Windows\\System32\\powercfg.exe'):
                            power_result = subprocess.run(['powercfg', '/batteryreport', '/output', 'NUL'], 
                                                        capture_output=True, text=True, timeout=2)
                            # If command succeeds, has battery
                            if power_result.returncode == 0:
                                device_type = "Windows Laptop"
                            else:
                                device_type = "Windows Desktop"
                        else:
                            device_type = "Windows Computer"
                    except Exception:
                        device_type = "Windows Computer"
            
            # Linux device type identification
            elif system == 'Linux':
                try:
                    # Check for battery (laptop indicator)
                    if os.path.exists('/sys/class/power_supply/BAT0') or os.path.exists('/sys/class/power_supply/BAT1'):
                        device_type = "Linux Laptop"
                    else:
                        device_type = "Linux Desktop"
                except Exception as e:
                    logger.debug(f"Failed to detect Linux device type: {e}")
                    device_type = "Linux Computer"
            
            # Other systems
            else:
                device_type = f"{system} Computer"
            
            self._cache[cache_key] = device_type
            logger.info(f"[SystemInfo] Device type detected: {device_type}")
            return device_type
                
        except Exception as e:
            logger.warning(f"[SystemInfo] Failed to detect device type: {e}")
            return "Computer"
    
    def get_system_architecture(self) -> str:
        """Get system architecture information"""
        cache_key = 'architecture'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            # Get processor info for architecture determination
            processor_info = self.get_processor_info()
            processor = processor_info.get('brand_raw', '').lower()
            
            # Get architecture info
            architecture = platform.architecture()[0]
            
            # Architecture mapping logic
            arch_mapping = {
                '64bit': 'x86_64' if 'intel' in processor or 'amd' in processor else 'arm64',
                '32bit': 'x86'
            }
            
            result = arch_mapping.get(architecture, architecture)
            
            # Fallback detection method
            if not result or result == architecture:
                machine = platform.machine().lower()
                if machine in ['x86_64', 'amd64']:
                    result = 'x86_64'
                elif machine in ['arm64', 'aarch64']:
                    result = 'arm64'
                else:
                    result = machine or 'unknown'
            
            self._cache[cache_key] = result
            logger.info(f"[SystemInfo] Architecture detected: {result}")
            return result
            
        except Exception as e:
            logger.warning(f"[SystemInfo] Failed to detect architecture: {e}")
            return 'unknown'
    
    def get_processor_info(self) -> Dict[str, Any]:
        """Get processor information"""
        cache_key = 'processor_info'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            import psutil
            from cpuinfo import get_cpu_info
            
            cpu_info = get_cpu_info()
            processor_info = {
                'brand_raw': cpu_info.get('brand_raw', 'Unknown Processor'),
                'arch': cpu_info.get('arch_string_raw', 'Unknown'),
                'bits': cpu_info.get('bits', 0),
                'count': psutil.cpu_count(logical=False),  # Physical cores
                'threads': psutil.cpu_count(logical=True),  # Logical cores
                'hz_advertised_friendly': cpu_info.get('hz_advertised_friendly', 'Unknown Speed'),
                'flags': cpu_info.get('flags', [])
            }
            
            self._cache[cache_key] = processor_info
            return processor_info
            
        except ImportError:
            logger.warning("[SystemInfo] cpuinfo package not available, using basic info")
            # Fallback to basic info
            try:
                import psutil
                processor_info = {
                    'brand_raw': 'Unknown Processor',
                    'arch': platform.machine(),
                    'bits': 64 if '64' in platform.architecture()[0] else 32,
                    'count': psutil.cpu_count(logical=False),
                    'threads': psutil.cpu_count(logical=True),
                    'hz_advertised_friendly': 'Unknown Speed',
                    'flags': []
                }
                self._cache[cache_key] = processor_info
                return processor_info
            except Exception as e:
                logger.error(f"[SystemInfo] Failed to get basic processor info: {e}")
                return {
                    'brand_raw': 'Unknown Processor',
                    'arch': 'unknown',
                    'bits': 64,
                    'count': 1,
                    'threads': 1,
                    'hz_advertised_friendly': 'Unknown Speed',
                    'flags': []
                }
        except Exception as e:
            logger.error(f"[SystemInfo] Failed to get processor info: {e}")
            return {
                'brand_raw': 'Unknown Processor',
                'arch': 'unknown',
                'bits': 64,
                'count': 1,
                'threads': 1,
                'hz_advertised_friendly': 'Unknown Speed',
                'flags': []
            }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information"""
        try:
            import psutil
            
            virtual_memory = psutil.virtual_memory()
            return {
                'total': virtual_memory.total,
                'total_gb': virtual_memory.total / (1024 ** 3),
                'available': virtual_memory.available,
                'available_gb': virtual_memory.available / (1024 ** 3),
                'percent': virtual_memory.percent,
                'used': virtual_memory.used,
                'used_gb': virtual_memory.used / (1024 ** 3)
            }
        except Exception as e:
            logger.error(f"[SystemInfo] Failed to get memory info: {e}")
            return {
                'total': 0,
                'total_gb': 0.0,
                'available': 0,
                'available_gb': 0.0,
                'percent': 0.0,
                'used': 0,
                'used_gb': 0.0
            }
    
    def get_system_performance(self) -> Dict[str, Any]:
        """Get system performance metrics"""
        try:
            import psutil
            
            # CPU usage - reduced wait time
            cpu_usage = psutil.cpu_percent(interval=0.05)  # Reduced from 0.1s to 0.05s
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            
            # Disk usage - cross-platform compatible
            try:
                if platform.system() == 'Windows':
                    disk = psutil.disk_usage('C:\\')
                else:
                    disk = psutil.disk_usage('/')
                disk_usage = (disk.used / disk.total) * 100
            except Exception as e:
                logger.debug(f"Failed to get disk usage: {e}")
                disk_usage = 0.0
            
            # Network status detection
            network_status = self._check_network_connectivity()
            
            # System uptime
            uptime = int(time.time() - psutil.boot_time())
            
            return {
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'network_status': network_status,
                'uptime': uptime,
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.error(f"[SystemInfo] Failed to get system performance: {e}")
            return {
                'cpu_usage': 0.0,
                'memory_usage': 0.0,
                'disk_usage': 0.0,
                'network_status': 'unknown',
                'uptime': 0,
                'timestamp': time.time()
            }
    
    def get_complete_system_info(self) -> Dict[str, Any]:
        """Get complete system information"""
        try:
            system = platform.system()
            release = platform.release()
            version = platform.version()
            architecture = platform.architecture()[0]
            
            processor_info = self.get_processor_info()
            memory_info = self.get_memory_info()
            performance = self.get_system_performance()
            
            return {
                # Basic system info
                'system': system,
                'release': release,
                'version': version,
                'architecture': architecture,
                'os_info': f"{system} {release} ({architecture}), Version: {version}",
                'platform': system.lower()[:3],
                
                # Machine identification info
                'machine_name': self.get_friendly_machine_name(),
                'device_type': self.get_device_type(),
                'system_arch': self.get_system_architecture(),
                
                # Hardware info
                'processor': processor_info,
                'memory': memory_info,
                
                # Performance metrics
                'performance': performance,
                
                # Timestamp
                'collected_at': time.time()
            }
            
        except Exception as e:
            logger.error(f"[SystemInfo] Failed to get complete system info: {e}")
            return {}
    
    def _check_network_connectivity(self) -> str:
        """Check network connectivity status"""
        try:
            # Reduce timeout for faster response
            socket.create_connection(("8.8.8.8", 53), timeout=1)
            return "connected"
        except Exception:
            return "disconnected"
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache is valid"""
        if key not in self._cache:
            return False
        
        current_time = time.time()
        if current_time - self._last_update > self._cache_timeout:
            self._cache.clear()
            self._last_update = current_time
            return False
        
        return True
    
    def clear_cache(self):
        """Clear cache"""
        self._cache.clear()
        self._last_update = 0
        logger.info("[SystemInfo] Cache cleared")


# Global instance
_system_info_manager = None


def get_system_info_manager() -> SystemInfoManager:
    """Get system info manager instance (singleton pattern)"""
    global _system_info_manager
    if _system_info_manager is None:
        _system_info_manager = SystemInfoManager()
    return _system_info_manager


# Convenience functions
def get_friendly_machine_name() -> str:
    """Get user-friendly machine name"""
    return get_system_info_manager().get_friendly_machine_name()


def get_device_type() -> str:
    """Get device type"""
    return get_system_info_manager().get_device_type()


def get_system_architecture() -> str:
    """Get system architecture"""
    return get_system_info_manager().get_system_architecture()


def get_processor_info() -> Dict[str, Any]:
    """Get processor information"""
    return get_system_info_manager().get_processor_info()


def get_memory_info() -> Dict[str, Any]:
    """Get memory information"""
    return get_system_info_manager().get_memory_info()


def get_system_performance() -> Dict[str, Any]:
    """Get system performance metrics"""
    return get_system_info_manager().get_system_performance()


def get_complete_system_info() -> Dict[str, Any]:
    """Get complete system information"""
    return get_system_info_manager().get_complete_system_info()
