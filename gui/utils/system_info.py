"""
系统信息管理模块

提供系统信息获取、设备识别、性能监控等功能
"""

import os
import platform
import socket
import subprocess
import time
from typing import Dict, Optional, Any

from utils.logger_helper import logger_helper as logger


class SystemInfoManager:
    """系统信息管理器"""
    
    def __init__(self):
        self._cache = {}
        self._cache_timeout = 300  # 5分钟缓存
        self._last_update = 0
    
    def get_friendly_machine_name(self) -> str:
        """获取用户友好的机器名称"""
        cache_key = 'machine_name'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            machine_name = None
            
            # 方法1: 尝试获取系统显示名称 (macOS)
            if platform.system() == 'Darwin':
                try:
                    result = subprocess.run(['scutil', '--get', 'ComputerName'], 
                                          capture_output=True, text=True, timeout=3)
                    if result.returncode == 0 and result.stdout.strip():
                        machine_name = result.stdout.strip()
                except Exception as e:
                    logger.debug(f"Failed to get macOS computer name: {e}")
            
            # 方法2: 尝试获取 Windows 计算机名
            elif platform.system() == 'Windows':
                try:
                    # 优先使用 COMPUTERNAME 环境变量
                    machine_name = os.environ.get('COMPUTERNAME')
                    
                    # 如果没有，尝试使用 wmic 获取更友好的名称
                    if not machine_name:
                        result = subprocess.run(['wmic', 'computersystem', 'get', 'name'], 
                                              capture_output=True, text=True, timeout=2)
                        if result.returncode == 0:
                            lines = result.stdout.strip().split('\n')
                            if len(lines) > 1:
                                machine_name = lines[1].strip()
                    
                    # 尝试获取用户友好的显示名称
                    if machine_name:
                        try:
                            # 获取当前用户名
                            username = os.environ.get('USERNAME', '')
                            if username and machine_name != username:
                                # 如果机器名不是用户名，组合显示
                                machine_name = f"{username} 的 {machine_name}"
                        except Exception:
                            pass
                            
                except Exception as e:
                    logger.debug(f"Failed to get Windows computer name: {e}")
            
            # 方法3: 使用用户名 + 系统类型
            if not machine_name:
                try:
                    username = os.getlogin()
                    system_type = "Mac" if platform.system() == 'Darwin' else platform.system()
                    machine_name = f"{username}'s {system_type}"
                except Exception as e:
                    logger.debug(f"Failed to generate username-based name: {e}")
            
            # 方法4: 回退到主机名
            if not machine_name:
                machine_name = platform.node() or socket.gethostname()
            
            # 清理名称 (移除域名后缀等)
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
        """智能识别设备类型"""
        cache_key = 'device_type'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            system = platform.system()
            
            # macOS 设备类型识别
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
                            device_type = "Mac 电脑"
                    else:
                        device_type = "Mac 电脑"
                except Exception as e:
                    logger.debug(f"Failed to get macOS device model: {e}")
                    device_type = "Mac 电脑"
            
            # Windows 设备类型识别
            elif system == 'Windows':
                try:
                    # 方法1: 检查系统类型
                    result = subprocess.run(['wmic', 'computersystem', 'get', 'PCSystemType'], 
                                          capture_output=True, text=True, timeout=2)
                    if result.returncode == 0 and '2' in result.stdout:  # 2 = Mobile
                        device_type = "Windows 笔记本"
                    else:
                        # 方法2: 检查电池存在性
                        try:
                            battery_result = subprocess.run(['wmic', 'path', 'win32_battery', 'get', 'name'], 
                                                          capture_output=True, text=True, timeout=2)
                            if battery_result.returncode == 0 and battery_result.stdout.strip():
                                # 有电池信息，可能是笔记本
                                lines = battery_result.stdout.strip().split('\n')
                                if len(lines) > 1 and any(line.strip() for line in lines[1:]):
                                    device_type = "Windows 笔记本"
                                else:
                                    device_type = "Windows 台式机"
                            else:
                                device_type = "Windows 台式机"
                        except Exception:
                            device_type = "Windows 台式机"
                except Exception as e:
                    logger.debug(f"Failed to get Windows system type: {e}")
                    # 方法3: 回退检查 - 检查是否有电源管理
                    try:
                        import os
                        if os.path.exists('C:\\Windows\\System32\\powercfg.exe'):
                            power_result = subprocess.run(['powercfg', '/batteryreport', '/output', 'NUL'], 
                                                        capture_output=True, text=True, timeout=2)
                            # 如果命令成功执行，说明有电池
                            if power_result.returncode == 0:
                                device_type = "Windows 笔记本"
                            else:
                                device_type = "Windows 台式机"
                        else:
                            device_type = "Windows 电脑"
                    except Exception:
                        device_type = "Windows 电脑"
            
            # Linux 设备类型识别
            elif system == 'Linux':
                try:
                    # 检查是否有电池 (笔记本电脑的标志)
                    if os.path.exists('/sys/class/power_supply/BAT0') or os.path.exists('/sys/class/power_supply/BAT1'):
                        device_type = "Linux 笔记本"
                    else:
                        device_type = "Linux 台式机"
                except Exception as e:
                    logger.debug(f"Failed to detect Linux device type: {e}")
                    device_type = "Linux 电脑"
            
            # 其他系统
            else:
                device_type = f"{system} 电脑"
            
            self._cache[cache_key] = device_type
            logger.info(f"[SystemInfo] Device type detected: {device_type}")
            return device_type
                
        except Exception as e:
            logger.warning(f"[SystemInfo] Failed to detect device type: {e}")
            return "电脑"
    
    def get_system_architecture(self) -> str:
        """获取系统架构信息"""
        cache_key = 'architecture'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            # 获取处理器信息用于架构判断
            processor_info = self.get_processor_info()
            processor = processor_info.get('brand_raw', '').lower()
            
            # 获取架构信息
            architecture = platform.architecture()[0]
            
            # 架构映射逻辑
            arch_mapping = {
                '64bit': 'x86_64' if 'intel' in processor or 'amd' in processor else 'arm64',
                '32bit': 'x86'
            }
            
            result = arch_mapping.get(architecture, architecture)
            
            # 备用检测方法
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
        """获取处理器信息"""
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
            # 回退到基础信息
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
        """获取内存信息"""
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
        """获取系统性能指标"""
        try:
            import psutil
            
            # CPU 使用率 - 减少等待时间
            cpu_usage = psutil.cpu_percent(interval=0.05)  # 从0.1秒减少到0.05秒
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            
            # 磁盘使用率 - 跨平台兼容
            try:
                if platform.system() == 'Windows':
                    disk = psutil.disk_usage('C:\\')
                else:
                    disk = psutil.disk_usage('/')
                disk_usage = (disk.used / disk.total) * 100
            except Exception as e:
                logger.debug(f"Failed to get disk usage: {e}")
                disk_usage = 0.0
            
            # 网络状态检测
            network_status = self._check_network_connectivity()
            
            # 系统运行时间
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
        """获取完整的系统信息"""
        try:
            system = platform.system()
            release = platform.release()
            version = platform.version()
            architecture = platform.architecture()[0]
            
            processor_info = self.get_processor_info()
            memory_info = self.get_memory_info()
            performance = self.get_system_performance()
            
            return {
                # 基础系统信息
                'system': system,
                'release': release,
                'version': version,
                'architecture': architecture,
                'os_info': f"{system} {release} ({architecture}), Version: {version}",
                'platform': system.lower()[:3],
                
                # 机器识别信息
                'machine_name': self.get_friendly_machine_name(),
                'device_type': self.get_device_type(),
                'system_arch': self.get_system_architecture(),
                
                # 硬件信息
                'processor': processor_info,
                'memory': memory_info,
                
                # 性能指标
                'performance': performance,
                
                # 时间戳
                'collected_at': time.time()
            }
            
        except Exception as e:
            logger.error(f"[SystemInfo] Failed to get complete system info: {e}")
            return {}
    
    def _check_network_connectivity(self) -> str:
        """检查网络连接状态"""
        try:
            # 减少超时时间，提升响应速度
            socket.create_connection(("8.8.8.8", 53), timeout=1)
            return "connected"
        except Exception:
            return "disconnected"
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        
        current_time = time.time()
        if current_time - self._last_update > self._cache_timeout:
            self._cache.clear()
            self._last_update = current_time
            return False
        
        return True
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        self._last_update = 0
        logger.info("[SystemInfo] Cache cleared")


# 全局实例
_system_info_manager = None


def get_system_info_manager() -> SystemInfoManager:
    """获取系统信息管理器实例 (单例模式)"""
    global _system_info_manager
    if _system_info_manager is None:
        _system_info_manager = SystemInfoManager()
    return _system_info_manager


# 便捷函数
def get_friendly_machine_name() -> str:
    """获取用户友好的机器名称"""
    return get_system_info_manager().get_friendly_machine_name()


def get_device_type() -> str:
    """获取设备类型"""
    return get_system_info_manager().get_device_type()


def get_system_architecture() -> str:
    """获取系统架构"""
    return get_system_info_manager().get_system_architecture()


def get_processor_info() -> Dict[str, Any]:
    """获取处理器信息"""
    return get_system_info_manager().get_processor_info()


def get_memory_info() -> Dict[str, Any]:
    """获取内存信息"""
    return get_system_info_manager().get_memory_info()


def get_system_performance() -> Dict[str, Any]:
    """获取系统性能指标"""
    return get_system_info_manager().get_system_performance()


def get_complete_system_info() -> Dict[str, Any]:
    """获取完整系统信息"""
    return get_system_info_manager().get_complete_system_info()
