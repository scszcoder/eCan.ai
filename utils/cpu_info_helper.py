"""
CPU信息获取工具模块

提供安全的CPU信息获取功能，避免多进程环境下的阻塞问题。
"""

import platform
import cpuinfo


def get_cpu_info_safely(timeout_seconds=5):
    """
    安全获取CPU信息，避免多进程问题
    
    Args:
        timeout_seconds (int): 超时时间，默认5秒
        
    Returns:
        dict: CPU信息字典，包含以下字段：
            - brand_raw: CPU品牌和型号
            - hz_advertised_friendly: CPU频率
            - arch: CPU架构
            - count: CPU核心数
            
    Example:
        >>> cpu_info = get_cpu_info_safely()
        >>> print(cpu_info['brand_raw'])
        'Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz'
    """
    try:
        # 设置超时和异常处理，避免子进程阻塞
        import signal
        
        # 在Windows上不支持signal.alarm，使用不同的策略
        if platform.system() == 'Windows':
            # Windows上使用线程超时机制
            import threading
            import time
            
            result = {'error': True}
            
            def get_cpu_info():
                try:
                    result['data'] = cpuinfo.get_cpu_info()
                    result['error'] = False
                except Exception as e:
                    result['error'] = True
                    result['exception'] = e
            
            thread = threading.Thread(target=get_cpu_info)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout_seconds)
            
            if result.get('error', True):
                raise TimeoutError("CPU info retrieval timed out or failed")
            
            return result['data']
        else:
            # Unix系统使用signal.alarm
            def timeout_handler(signum, frame):
                raise TimeoutError("CPU info retrieval timed out")

            # 设置超时
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)

            cpu_info = cpuinfo.get_cpu_info()
            signal.alarm(0)  # 取消超时
            
            return cpu_info

    except (TimeoutError, KeyboardInterrupt, Exception) as e:
        print(f"Warning: Failed to get CPU info: {e}")
        # 使用默认值
        return _get_default_cpu_info()


def _get_default_cpu_info():
    """
    获取默认的CPU信息，当无法获取真实信息时使用
    
    Returns:
        dict: 默认CPU信息
    """
    try:
        # 尝试获取一些基本的系统信息
        arch = platform.machine()
        processor = platform.processor()
        
        # 如果processor为空，使用platform.platform()
        if not processor:
            processor = platform.platform()
            
        return {
            'brand_raw': processor or 'Unknown Processor',
            'hz_advertised_friendly': 'Unknown Speed',
            'arch': arch or 'Unknown',
            'count': 1,
            'python_version': platform.python_version(),
            'system': platform.system(),
            'release': platform.release()
        }
    except Exception as e:
        print(f"Warning: Failed to get even basic system info: {e}")
        return {
            'brand_raw': 'Unknown Processor',
            'hz_advertised_friendly': 'Unknown Speed',
            'arch': 'Unknown',
            'count': 1
        }


def get_cpu_brand(cpu_info=None):
    """
    从CPU信息中提取品牌名称
    
    Args:
        cpu_info (dict, optional): CPU信息字典，如果为None则自动获取
        
    Returns:
        str: CPU品牌名称
    """
    if cpu_info is None:
        cpu_info = get_cpu_info_safely()
    
    return cpu_info.get('brand_raw', 'Unknown Processor')


def get_cpu_speed(cpu_info=None):
    """
    从CPU信息中提取频率信息
    
    Args:
        cpu_info (dict, optional): CPU信息字典，如果为None则自动获取
        
    Returns:
        str: CPU频率信息
    """
    if cpu_info is None:
        cpu_info = get_cpu_info_safely()
    
    return cpu_info.get('hz_advertised_friendly', 'Unknown Speed')


def get_cpu_count(cpu_info=None):
    """
    从CPU信息中提取核心数
    
    Args:
        cpu_info (dict, optional): CPU信息字典，如果为None则自动获取
        
    Returns:
        int: CPU核心数
    """
    if cpu_info is None:
        cpu_info = get_cpu_info_safely()
    
    return cpu_info.get('count', 1)


# 为了向后兼容，提供一个简单的接口
def get_cpu_info():
    """
    简单的CPU信息获取接口，向后兼容
    
    Returns:
        dict: CPU信息字典
    """
    return get_cpu_info_safely()


if __name__ == "__main__":
    # 测试代码
    print("Testing CPU info retrieval...")

    cpu_info = get_cpu_info_safely()
    print(f"CPU Brand: {get_cpu_brand(cpu_info)}")
    print(f"CPU Speed: {get_cpu_speed(cpu_info)}")
    print(f"CPU Count: {get_cpu_count(cpu_info)}")
    print(f"CPU Arch: {cpu_info.get('arch', 'Unknown')}")

    print("\nFull CPU info:")
    for key, value in cpu_info.items():
        if isinstance(value, (str, int, float)):
            print(f"  {key}: {value}")

    print("\n" + "="*50)
    print("使用示例:")
    print("="*50)
    print("""
# 基本使用
from utils.cpu_info_helper import get_cpu_info_safely

# 获取完整CPU信息
cpu_info = get_cpu_info_safely()
print(cpu_info['brand_raw'])  # CPU品牌和型号

# 使用便捷函数
from utils.cpu_info_helper import get_cpu_brand, get_cpu_speed, get_cpu_count

print(f"CPU: {get_cpu_brand()}")
print(f"Speed: {get_cpu_speed()}")
print(f"Cores: {get_cpu_count()}")

# 自定义超时时间
cpu_info = get_cpu_info_safely(timeout_seconds=3)

# 在MainGUI中的使用
class MainWindow:
    def __init__(self):
        from utils.cpu_info_helper import get_cpu_info_safely
        self.cpuinfo = get_cpu_info_safely()
    """)
