"""
CPU information retrieval utility module

Provides safe CPU information retrieval functionality, avoiding blocking issues in multi-process environments.
"""

import platform
import cpuinfo
from utils.logger_helper import logger_helper as logger


def get_cpu_info_safely(timeout_seconds=5):
    """
    Safely get CPU information, avoiding multi-process issues

    Args:
        timeout_seconds (int): Timeout duration, default 5 seconds

    Returns:
        dict: CPU information dictionary containing the following fields:
            - brand_raw: CPU brand and model
            - hz_advertised_friendly: CPU frequency
            - arch: CPU architecture
            - count: CPU core count

    Example:
        >>> cpu_info = get_cpu_info_safely()
        >>> print(cpu_info['brand_raw'])
        'Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz'
    """
    try:
        import threading

        is_main_thread = threading.current_thread() is threading.main_thread()

        # signal.alarm only works in main thread on Unix, use threading elsewhere
        if platform.system() == 'Windows' or not is_main_thread:
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
                raise TimeoutError("CPU info retrieval timed out")

            return result['data']
        else:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError("CPU info retrieval timed out")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
            cpu_info = cpuinfo.get_cpu_info()
            signal.alarm(0)

            return cpu_info

    except (TimeoutError, KeyboardInterrupt, Exception) as e:
        logger.error(f"Failed to get CPU info: {e}")
        return _get_default_cpu_info()


def _get_default_cpu_info():
    """
    Get default CPU information, used when real information cannot be obtained

    Returns:
        dict: Default CPU information
    """
    try:
        # Try to get some basic system information
        arch = platform.machine()
        processor = platform.processor()

        # If processor is empty, use platform.platform()
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
        logger.error(f"Warning: Failed to get even basic system info: {e}")
        return {
            'brand_raw': 'Unknown Processor',
            'hz_advertised_friendly': 'Unknown Speed',
            'arch': 'Unknown',
            'count': 1
        }


def get_cpu_brand(cpu_info=None):
    """
    Extract brand name from CPU information

    Args:
        cpu_info (dict, optional): CPU information dictionary, automatically retrieved if None

    Returns:
        str: CPU brand name
    """
    if cpu_info is None:
        cpu_info = get_cpu_info_safely()

    return cpu_info.get('brand_raw', 'Unknown Processor')


def get_cpu_speed(cpu_info=None):
    """
    Extract frequency information from CPU information

    Args:
        cpu_info (dict, optional): CPU information dictionary, automatically retrieved if None

    Returns:
        str: CPU frequency information
    """
    if cpu_info is None:
        cpu_info = get_cpu_info_safely()

    return cpu_info.get('hz_advertised_friendly', 'Unknown Speed')


def get_cpu_count(cpu_info=None):
    """
    Extract core count from CPU information

    Args:
        cpu_info (dict, optional): CPU information dictionary, automatically retrieved if None

    Returns:
        int: CPU core count
    """
    if cpu_info is None:
        cpu_info = get_cpu_info_safely()

    return cpu_info.get('count', 1)


# For backward compatibility, provide a simple interface
def get_cpu_info():
    """
    Simple CPU information retrieval interface, backward compatible

    Returns:
        dict: CPU information dictionary
    """
    return get_cpu_info_safely()


if __name__ == "__main__":
    # Test code
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
    print("Usage examples:")
    print("="*50)
    print("""
# Basic usage
from utils.cpu_info_helper import get_cpu_info_safely

# Get complete CPU information
cpu_info = get_cpu_info_safely()
print(cpu_info['brand_raw'])  # CPU brand and model

# Use convenience functions
from utils.cpu_info_helper import get_cpu_brand, get_cpu_speed, get_cpu_count

print(f"CPU: {get_cpu_brand()}")
print(f"Speed: {get_cpu_speed()}")
print(f"Cores: {get_cpu_count()}")

# Custom timeout
cpu_info = get_cpu_info_safely(timeout_seconds=3)

# Usage in MainGUI
class MainWindow:
    def __init__(self):
        from utils.cpu_info_helper import get_cpu_info_safely
        self.cpuinfo = get_cpu_info_safely()
    """)
