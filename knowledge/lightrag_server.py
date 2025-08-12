import subprocess
import os
import sys
import signal
from pathlib import Path
from dataclasses import dataclass
import threading
import time
from utils.logger_helper import logger_helper as logger

# 优先读取 knowledge 目录下的 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
except ImportError:
    pass


class LightragServer:
    def __init__(self, extra_env=None):
        self.extra_env = extra_env or {}
        logger.info(f"[LightragServer] extra_env: {self.extra_env}")
        self.proc = None

        # 检测是否在 PyInstaller 打包环境中
        self.is_frozen = getattr(sys, 'frozen', False)

        # 重启控制 - 从环境变量读取配置
        self.restart_count = 0
        self.max_restarts = int(self.extra_env.get("MAX_RESTARTS", "3"))
        self.last_restart_time = 0
        self.restart_cooldown = int(self.extra_env.get("RESTART_COOLDOWN", "30"))  # 秒

        # Get parent process ID - handle Windows compatibility and PyInstaller
        import platform
        is_windows = platform.system().lower().startswith('win')

        # 在 PyInstaller 环境中，默认禁用父进程监控以避免问题
        if self.is_frozen:
            logger.info("[LightragServer] Running in PyInstaller environment, disabling parent monitoring by default")
            self.disable_parent_monitoring = True
            self.parent_pid = None
        else:
            if is_windows:
                try:
                    import psutil
                    self.parent_pid = psutil.Process().ppid()
                except (ImportError, AttributeError):
                    # Fallback to os.getppid() if psutil is not available
                    self.parent_pid = os.getppid()
            else:
                self.parent_pid = os.getppid()

            # Check if parent process monitoring should be disabled
            self.disable_parent_monitoring = self.extra_env.get("DISABLE_PARENT_MONITORING", "false").lower() == "true"

        self._monitor_running = False
        self._monitor_thread = None

        logger.info(f"[LightragServer] Parent PID: {self.parent_pid}, Monitoring disabled: {self.disable_parent_monitoring}")

        # 设置信号处理器
        self._setup_signal_handlers()

        # 自动处理 APP_DATA 生成相关目录
        app_data_path = self.extra_env.get("APP_DATA_PATH")
        if app_data_path:
            input_dir = os.path.join(app_data_path, "inputs")
            working_dir = os.path.join(app_data_path, "rag_storage")
            log_dir = os.path.join(app_data_path, "runlogs")
            self.extra_env.setdefault("INPUT_DIR", input_dir)
            self.extra_env.setdefault("WORKING_DIR", working_dir)
            self.extra_env.setdefault("LOG_DIR", log_dir)
            logger.info(f"[LightragServer] INPUT_DIR: {input_dir}, WORKING_DIR: {working_dir}, LOG_DIR: {log_dir}")

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"[LightragServer] Received signal {signum}, stopping server...")
            self.stop()
            if not self.is_frozen:  # 只在非打包环境中退出
                sys.exit(0)

        try:
            # 注册信号处理器
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)

            # macOS/Linux 特有信号
            if hasattr(signal, 'SIGHUP'):
                signal.signal(signal.SIGHUP, signal_handler)

            logger.info("[LightragServer] Signal handlers registered")
        except Exception as e:
            logger.warning(f"[LightragServer] Failed to setup signal handlers: {e}")

    def build_env(self):
        env = os.environ.copy()

        # 强力修复 Windows 编码问题
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONUNBUFFERED'] = '1'  # 强制子进程无缓冲输出，避免日志缺失
        env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
        env['LANG'] = 'en_US.UTF-8'
        env['LC_ALL'] = 'en_US.UTF-8'

        # 设置默认值
        env.setdefault('HOST', '127.0.0.1')
        env.setdefault('PORT', '9621')
        env.setdefault('MAX_RESTARTS', '3')
        env.setdefault('RESTART_COOLDOWN', '5')
        # 禁用 LightRAG 彩色输出/启动横幅（可通过环境变量覆盖）
        env.setdefault('ECBOT_LIGHTRAG_DISABLE_SPLASH', '1')
        env.setdefault('NO_COLOR', '1')
        env.setdefault('ASCII_COLORS_DISABLE', '1')

        # 健康检查参数（可通过环境变量配置）
        env.setdefault('LIGHTRAG_HEALTH_TIMEOUT', '45')  # seconds
        env.setdefault('LIGHTRAG_HEALTH_INTERVAL_INITIAL', '0.5')  # seconds
        env.setdefault('LIGHTRAG_HEALTH_INTERVAL_MAX', '1.5')  # seconds

        if self.extra_env:
            env.update({str(k): str(v) for k, v in self.extra_env.items()})

        # 在打包环境中的特殊处理
        if self.is_frozen:
            # 清除可能导致冲突的Python环境变量
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            logger.info("[LightragServer] Cleaned Python environment variables for packaged environment")
            # 强制绑定到 127.0.0.1，避免打包环境下 .env 中的 0.0.0.0 影响健康检查
            host = str(env.get('HOST', '127.0.0.1')).strip()
            if host in ('0.0.0.0', '::', ''):
                env['HOST'] = '127.0.0.1'

        # 设置路径相关的环境变量
        if 'APP_DATA_PATH' in env:
            app_data_path = env['APP_DATA_PATH']
            env.setdefault('INPUT_DIR', os.path.join(app_data_path, 'inputs'))
            env.setdefault('WORKING_DIR', os.path.join(app_data_path, 'rag_storage'))
            env.setdefault('LOG_DIR', os.path.join(app_data_path, 'runlogs'))

        return env

    def _get_virtual_env_python(self):
        """获取虚拟环境中的 Python 解释器路径"""
        # 在打包环境中，sys.executable 就是包含所有依赖的exe文件
        # LightRAG服务器应该使用相同的exe来保证环境一致性
        if self.is_frozen:
            logger.info(f"[LightragServer] Running in PyInstaller environment, using current executable: {sys.executable}")
            return sys.executable

        # 非打包环境的原有逻辑
        # 检查当前是否在虚拟环境中
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            logger.info(f"[LightragServer] Already in virtual environment: {sys.executable}")
            return sys.executable

        # 尝试找到项目根目录下的虚拟环境
        project_root = os.path.dirname(os.path.dirname(__file__))
        venv_paths = [
            os.path.join(project_root, "venv", "bin", "python"),
            os.path.join(project_root, "venv", "Scripts", "python.exe"),
        ]

        for venv_python in venv_paths:
            if os.path.exists(venv_python):
                logger.info(f"[LightragServer] Found virtual environment Python: {venv_python}")
                return venv_python

        # 如果找不到虚拟环境，返回当前解释器
        logger.warning(f"[LightragServer] No virtual environment found, using current Python: {sys.executable}")
        return sys.executable

    def _validate_python_executable(self, python_path):
        """验证Python解释器是否可用"""
        try:
            # 在打包环境中，验证exe文件是否存在且可执行
            if self.is_frozen:
                if os.path.exists(python_path) and os.access(python_path, os.X_OK):
                    logger.info(f"[LightragServer] PyInstaller executable validation successful: {python_path}")
                    return True
                else:
                    logger.error(f"[LightragServer] PyInstaller executable not found or not executable: {python_path}")
                    return False

            # 非打包环境中，测试Python解释器版本
            result = subprocess.run(
                [python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info(f"[LightragServer] Python validation successful: {result.stdout.strip()}")
                return True
            else:
                logger.error(f"[LightragServer] Python validation failed with return code {result.returncode}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"[LightragServer] Python validation timed out: {python_path}")
            return False
        except FileNotFoundError:
            logger.error(f"[LightragServer] Python executable not found: {python_path}")
            return False
        except Exception as e:
            logger.error(f"[LightragServer] Python validation error: {e}")
            return False

    def _create_lightrag_startup_script(self):
        """为打包环境创建LightRAG启动脚本"""
        try:
            import tempfile

            # 安全处理路径，避免转义问题
            working_dir = self.extra_env.get('WORKING_DIR', '').replace('\\', '/')
            input_dir = self.extra_env.get('INPUT_DIR', '').replace('\\', '/')
            log_dir = self.extra_env.get('LOG_DIR', '').replace('\\', '/')
            host = self.extra_env.get('HOST', '127.0.0.1')
            port = self.extra_env.get('PORT', '9621')

            # 创建临时启动脚本
            # 创建跨平台兼容的独立LightRAG启动脚本
            script_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LightRAG服务器独立启动脚本 - 跨平台兼容版本
支持Windows和macOS，不导入main.py避免冲突
"""

import sys
import os
import platform
import traceback

def setup_environment():
    """设置LightRAG运行环境 - 跨平台兼容"""
    # 检测操作系统
    current_os = platform.system().lower()
    print(f"Operating System: {{current_os}}")

    # 直接从环境变量获取路径，避免字符串插值的转义问题
    import os

    # 环境变量设置（使用预处理的变量避免转义问题）
    env_vars = {{
        "HOST": "{host}",
        "PORT": "{port}",
        "LOG_LEVEL": "INFO",
        "MAX_TOKENS": "32768",
        "MAX_ASYNC": "16",
        "TIMEOUT": "60"
    }}

    # 安全设置路径环境变量（使用正斜杠，在脚本中转换）
    path_vars = {{
        "WORKING_DIR": "{working_dir}",
        "INPUT_DIR": "{input_dir}",
        "LOG_DIR": "{log_dir}"
    }}

    # 设置非路径环境变量
    for key, value in env_vars.items():
        if value:
            os.environ[key] = str(value)

    # 安全设置路径环境变量（避免转义问题）
    for key, value in path_vars.items():
        if value:
            # 使用os.path.normpath标准化路径
            normalized_path = os.path.normpath(value)
            os.environ[key] = normalized_path

    # 清理命令行参数，避免argparse冲突
    sys.argv = ["lightrag_server"]

    # 显示环境信息
    print(f"LightRAG Environment Setup ({{current_os}}):")
    print(f"  HOST: {{os.environ.get('HOST', 'not set')}}")
    print(f"  PORT: {{os.environ.get('PORT', 'not set')}}")
    print(f"  WORKING_DIR: {{os.environ.get('WORKING_DIR', 'not set')}}")
    print(f"  INPUT_DIR: {{os.environ.get('INPUT_DIR', 'not set')}}")
    print(f"  LOG_DIR: {{os.environ.get('LOG_DIR', 'not set')}}")

def check_python_environment():
    """检查Python环境兼容性"""
    print(f"Python Version: {{sys.version}}")
    print(f"Python Executable: {{sys.executable}}")
    print(f"Platform: {{platform.platform()}}")
    print(f"Architecture: {{platform.architecture()}}")

    # 检查是否在PyInstaller环境中
    if getattr(sys, 'frozen', False):
        print("✅ Running in PyInstaller packaged environment")
        if hasattr(sys, '_MEIPASS'):
            print(f"   PyInstaller temp directory: {{sys._MEIPASS}}")
        return True
    else:
        print("ℹ️  Running in development environment")
        return False

def main():
    """主函数 - 独立运行LightRAG服务器"""
    try:
        print("=" * 70)
        print("LightRAG Independent Server Starting...")
        print("=" * 70)

        # 检查Python环境
        is_packaged = check_python_environment()

        # 设置运行环境
        setup_environment()

        # 尝试导入LightRAG
        print("\\n" + "=" * 50)
        print("Importing LightRAG...")
        print("=" * 50)

        try:
            import lightrag
            print(f"✅ LightRAG imported successfully")
            if hasattr(lightrag, '__version__'):
                print(f"   Version: {{lightrag.__version__}}")
            else:
                print("   Version: unknown")
        except ImportError as e:
            print(f"❌ Failed to import LightRAG: {{e}}")
            print("   LightRAG is not available in this environment")
            if is_packaged:
                print("   This is normal if LightRAG was not packaged with the application")
                print("   LightRAG server will be disabled, but main application will continue")
                return 0  # 返回而不是退出，让主程序继续运行
            else:
                print("   Please install LightRAG: pip install lightrag")
                print("   Exiting gracefully...")
                sys.exit(0)  # 只在开发环境中退出

        # 导入并启动LightRAG API服务器
        print("\\n" + "=" * 50)
        print("Starting LightRAG API Server...")
        print("=" * 50)

        try:
            from lightrag.api.lightrag_server import main as lightrag_main
            print("🚀 Calling LightRAG main function...")
            lightrag_main()
        except Exception as e:
            print(f"❌ LightRAG server startup failed: {{e}}")
            print("\\nFull traceback:")
            traceback.print_exc()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\\n⚠️  LightRAG server interrupted by user (Ctrl+C)")
        sys.exit(0)
    except SystemExit as e:
        if e.code == 0:
            print(f"\\n✅ LightRAG server exited normally")
        else:
            print(f"\\n❌ LightRAG server exited with error code: {{e.code}}")
        sys.exit(e.code)
    except Exception as e:
        print(f"\\n❌ Unexpected error in LightRAG server: {{e}}")
        print("\\nFull traceback:")
        traceback.print_exc()
        sys.exit(1)

# 直接运行，不检查__name__ == "__main__"
# 这样就不会触发main.py中的主程序逻辑
if True:  # 总是执行，跨平台兼容
    main()
'''

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                script_path = f.name

            logger.info(f"[LightragServer] Created startup script: {script_path}")
            return script_path

        except Exception as e:
            logger.error(f"[LightragServer] Failed to create startup script: {e}")
            return None

    def _create_simple_lightrag_script(self):
        """创建简单的LightRAG启动脚本，利用main.py的保护机制"""
        try:
            import tempfile

            # 安全处理环境变量
            env_settings = []
            for key, value in self.extra_env.items():
                # 安全转义路径
                safe_value = str(value).replace('\\', '/')
                env_settings.append(f'os.environ["{key}"] = r"{safe_value}"')

            env_code = '\n    '.join(env_settings)

            # 创建简单的启动脚本
            # 关键：不导入main模块，直接运行LightRAG
            script_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LightRAG简单启动脚本
利用main.py现有的保护机制，不导入主程序模块
"""

import sys
import os
import io

# 强制设置 UTF-8 编码，避免 Windows GBK 控制台编码导致的 UnicodeEncodeError
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
os.environ.setdefault('PYTHONUTF8', '1')
# 多数着色库支持 NO_COLOR 关闭彩色输出，尽量减少非 ASCII 字符
os.environ.setdefault('NO_COLOR', '1')

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

def setup_lightrag_environment():
    """设置LightRAG环境"""
    # 设置环境变量
    {env_code}

    # 清理命令行参数
    sys.argv = ["lightrag_server"]

    print("LightRAG Environment Setup Complete")

def main():
    """启动LightRAG服务器"""
    try:
        print("=" * 50)
        print("LightRAG Server Starting...")
        print("=" * 50)

        # 设置环境
        setup_lightrag_environment()

        # 检查LightRAG可用性
        try:
            import lightrag
            print(f"LightRAG version: {{getattr(lightrag, '__version__', 'unknown')}}")
        except ImportError as e:
            print(f"LightRAG not available: {{e}}")
            print("Exiting gracefully...")
            return 0

        # 启动LightRAG服务器
        from lightrag.api.lightrag_server import main as lightrag_main
        print("Starting LightRAG API server...")
        lightrag_main()

    except KeyboardInterrupt:
        print("LightRAG server interrupted")
        return 0
    except Exception as e:
        print(f"LightRAG server error: {{e}}")
        import traceback
        traceback.print_exc()
        return 1

# 使用标准的if __name__ == '__main__'
# 这样会被main.py的保护机制正确处理
if __name__ == '__main__':
    sys.exit(main())
'''

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                script_path = f.name

            logger.info(f"[LightragServer] Created simple startup script: {script_path}")
            return script_path

        except Exception as e:
            logger.error(f"[LightragServer] Failed to create simple startup script: {e}")
            return None



    def _check_and_free_port(self):
        """检查端口是否被占用，如果被占用则尝试释放"""
        try:
            import socket
            import platform
            import subprocess
            import time

            port = int(self.extra_env.get("PORT", "9621"))
            is_windows = platform.system().lower().startswith('win')

            # 检查端口是否被占用
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()

            if result == 0:
                # 端口被占用，尝试释放
                logger.warning(f"[LightragServer] Port {port} is in use, attempting to free it...")

                pids = self._find_processes_using_port(port, is_windows)

                if pids:
                    logger.info(f"[LightragServer] Found {len(pids)} process(es) using port {port}: {pids}")

                    # 尝试杀死进程
                    killed_count = 0
                    for pid in pids:
                        if self._kill_process(pid, is_windows):
                            killed_count += 1
                            logger.info(f"[LightragServer] Successfully killed process {pid}")
                        else:
                            logger.warning(f"[LightragServer] Failed to kill process {pid}")

                    if killed_count > 0:
                        # 等待端口释放
                        for i in range(15):  # 最多等待15秒
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(1)
                            result = sock.connect_ex(('localhost', port))
                            sock.close()
                            if result != 0:
                                logger.info(f"[LightragServer] Port {port} is now free after killing {killed_count} process(es)")
                                return True
                            time.sleep(1)

                        logger.warning(f"[LightragServer] Port {port} is still in use after killing processes")
                    else:
                        logger.warning(f"[LightragServer] Could not kill any processes using port {port}")

                    # 如果无法杀死进程，尝试使用不同的端口
                    return self._try_alternative_port(port)
                else:
                    logger.warning(f"[LightragServer] Could not find processes using port {port}")
                    return self._try_alternative_port(port)
            else:
                # 端口可用
                return True

        except Exception as e:
            logger.warning(f"[LightragServer] Error checking port: {e}")
            return True  # 如果检查失败，假设端口可用

    def _find_processes_using_port(self, port, is_windows):
        """查找使用指定端口的进程"""
        try:
            if is_windows:
                # Windows: 使用 netstat
                result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    pids = []
                    for line in result.stdout.split('\n'):
                        if f':{port}' in line and 'LISTENING' in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                pid = parts[-1]
                                if pid.isdigit():
                                    pids.append(pid)
                    return pids
            else:
                # Unix/Linux/macOS: 使用 lsof
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split('\n')

            return []
        except Exception as e:
            logger.warning(f"[LightragServer] Error finding processes using port {port}: {e}")
            return []

    def _kill_process(self, pid, is_windows):
        """尝试杀死进程"""
        try:
            if is_windows:
                # Windows: 使用 taskkill
                result = subprocess.run(
                    ['taskkill', '/PID', str(pid), '/F'],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            else:
                # Unix/Linux/macOS: 使用 kill
                result = subprocess.run(
                    ['kill', '-9', str(pid)],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
        except Exception as e:
            logger.warning(f"[LightragServer] Error killing process {pid}: {e}")
            return False

    def _try_alternative_port(self, original_port):
        """尝试使用替代端口"""
        try:
            import socket

            # 尝试端口范围 9621-9630
            for port in range(original_port, original_port + 10):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result != 0:
                    # 找到可用端口
                    logger.info(f"[LightragServer] Found alternative port {port}")
                    self.extra_env["PORT"] = str(port)
                    return True

            logger.error(f"[LightragServer] No available ports found in range {original_port}-{original_port + 9}")
            return False

        except Exception as e:
            logger.warning(f"[LightragServer] Error trying alternative ports: {e}")
            return False

    def _monitor_parent(self):
        import platform
        is_windows = platform.system().lower().startswith('win')

        # Try to import psutil for Windows process monitoring
        psutil_available = False
        if is_windows:
            try:
                import psutil
                psutil_available = True
            except ImportError:
                logger.warning("psutil not available, parent process monitoring may not work properly on Windows")
            except Exception as e:
                logger.warning(f"psutil import error: {e}, falling back to basic monitoring")

        # 添加失败计数器，避免偶发性检查失败导致退出
        failure_count = 0
        max_failures = 3  # 连续失败3次才退出

        logger.info(f"[LightragServer] Starting parent process monitoring for PID {self.parent_pid}")

        while self._monitor_running:
            try:
                if self.parent_pid is None:
                    # 如果没有父进程 PID，跳过检查
                    time.sleep(5)
                    continue

                if is_windows and psutil_available:
                    # On Windows, use psutil to check if parent process exists
                    try:
                        parent_process = psutil.Process(self.parent_pid)
                        # Check if process is still running
                        if not parent_process.is_running():
                            failure_count += 1
                            logger.warning(f"Parent process check failed ({failure_count}/{max_failures})")
                            if failure_count >= max_failures:
                                logger.error("Parent process is gone, exiting lightrag server...")
                                os._exit(1)
                        else:
                            failure_count = 0  # 重置失败计数
                    except psutil.NoSuchProcess:
                        failure_count += 1
                        logger.warning(f"Parent process not found ({failure_count}/{max_failures})")
                        if failure_count >= max_failures:
                            logger.error("Parent process is gone, exiting lightrag server...")
                            os._exit(1)
                else:
                    # On Unix-like systems or Windows without psutil, use os.kill
                    # Note: This may not work reliably on Windows
                    try:
                        os.kill(self.parent_pid, 0)
                        failure_count = 0  # 重置失败计数
                    except (OSError, ProcessLookupError):
                        failure_count += 1
                        logger.warning(f"Parent process check failed ({failure_count}/{max_failures})")
                        if failure_count >= max_failures:
                            logger.error("Parent process is gone, exiting lightrag server...")
                            os._exit(1)

            except Exception as e:
                failure_count += 1
                logger.warning(f"Parent process monitoring error: {e} ({failure_count}/{max_failures})")
                if failure_count >= max_failures:
                    logger.error("Too many parent process monitoring errors, exiting lightrag server...")
                    os._exit(1)

            time.sleep(5)  # 增加检查间隔到5秒

    def _monitor_server_process(self):
        """监控服务器进程，支持自动重启"""
        while self._monitor_running:
            try:
                if self.proc is None:
                    time.sleep(5)
                    continue

                # 检查进程是否还在运行
                if self.proc.poll() is not None:
                    # 进程已退出
                    return_code = self.proc.returncode
                    logger.warning(f"[LightragServer] Server process exited with code {return_code}")

                    # 检查是否需要重启
                    current_time = time.time()
                    if (current_time - self.last_restart_time) > self.restart_cooldown:
                        self.restart_count = 0  # 重置重启计数

                    if self.restart_count < self.max_restarts:
                        self.restart_count += 1
                        self.last_restart_time = current_time
                        logger.info(f"[LightragServer] Attempting restart {self.restart_count}/{self.max_restarts}")

                        # 等待一段时间后重启
                        time.sleep(5)
                        if self._start_server_process():
                            continue

                    logger.error(f"[LightragServer] Max restarts ({self.max_restarts}) reached, giving up")
                    break

                time.sleep(5)  # 每5秒检查一次

            except Exception as e:
                logger.error(f"[LightragServer] Process monitor error: {e}")
                time.sleep(5)

    def _create_log_files(self):
        """创建日志文件"""
        log_dir = self.extra_env.get("LOG_DIR", ".")
        os.makedirs(log_dir, exist_ok=True)

        stdout_log_path = os.path.join(log_dir, "lightrag_server_stdout.log")
        stderr_log_path = os.path.join(log_dir, "lightrag_server_stderr.log")

        stdout_log = open(stdout_log_path, "a", encoding="utf-8")
        stderr_log = open(stderr_log_path, "a", encoding="utf-8")

        return stdout_log, stderr_log, stdout_log_path, stderr_log_path

    def _start_server_process(self, wait_gating: bool = False):
        """启动服务器进程
        
        Args:
            wait_gating: 是否在前台等待健康检查通过（阻塞）。默认 False 非阻塞。
        """
        try:
            env = self.build_env()
            stdout_log, stderr_log, stdout_log_path, stderr_log_path = self._create_log_files()

            # 检查并确定最终端口（以 env 为准，必要时寻找可用端口），保持 env 与 extra_env 一致
            try:
                desired_port = int(env.get("PORT", "9621"))
            except (ValueError, TypeError):
                desired_port = 9621
                logger.warning("[LightragServer] Invalid PORT in env, falling back to 9621")

            if not self._try_alternative_port(desired_port):
                logger.error("[LightragServer] No available port found, cannot start server")
                return False

            # _try_alternative_port 会把选中的端口写回 self.extra_env['PORT']，这里同步到 env，确保子进程读取一致
            env["PORT"] = str(self.extra_env.get("PORT", desired_port))

            # 尝试找到虚拟环境中的 Python 解释器
            python_executable = self._get_virtual_env_python()

            # 验证Python解释器是否可用
            if not self._validate_python_executable(python_executable):
                logger.error(f"[LightragServer] Python executable validation failed: {python_executable}")
                if self.is_frozen:
                    logger.warning("[LightragServer] In packaged environment, LightRAG server will be disabled")
                    logger.warning("[LightragServer] This is normal if lightrag is not packaged with the application")
                    return False
                else:
                    logger.error("[LightragServer] Cannot start server without valid Python interpreter")
                    return False

            # 在打包环境中，检查lightrag模块是否可用
            if self.is_frozen:
                try:
                    import lightrag
                    logger.info("[LightragServer] lightrag module is available in packaged environment")
                except ImportError:
                    logger.warning("[LightragServer] lightrag module not available in packaged environment")
                    logger.warning("[LightragServer] LightRAG server will be disabled")
                    return False

            import platform

            # 构建启动命令
            if self.is_frozen:
                # 在打包环境中，利用main.py现有的保护机制
                logger.info("[LightragServer] Using main.py protection mechanism for packaged environment")

                # 创建一个简单的启动脚本，导入并运行LightRAG
                script_path = self._create_simple_lightrag_script()
                if not script_path:
                    logger.error("[LightragServer] Failed to create startup script")
                    return False

                # 保存脚本路径以便停止时清理
                self._script_path = script_path

                # Use environment variable to deliver script path to main.exe (worker mode)
                env['ECBOT_RUN_SCRIPT'] = script_path
                env['ECBOT_BYPASS_SINGLE_INSTANCE'] = '1'
                cmd = [python_executable]  # 无需 -u，这里已通过 PYTHONUNBUFFERED=1 强制无缓冲
                logger.info(f"[LightragServer] PyInstaller mode command: {cmd} with ECBOT_RUN_SCRIPT={script_path}")
            else:
                # 开发环境：使用 -u 打印无缓冲输出，便于快速定位错误
                cmd = [python_executable, "-u", "-m", "lightrag.api.lightrag_server"]
                logger.info(f"[LightragServer] Development mode command: {' '.join(cmd)}")

            if platform.system().lower().startswith('win'):
                # Hide console window in production by default; enable via env for debugging
                show_console = os.getenv("ECBOT_CHILD_SHOW_CONSOLE") == "1"
                creation_flags = 0
                if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                    creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
                if not show_console and hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creation_flags |= subprocess.CREATE_NO_WINDOW

                self.proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=creation_flags
                )
                try:
                    self.proc.stdin.write("yes\n")
                    self.proc.stdin.flush()
                except Exception as e:
                    logger.error(f"[LightragServer] Failed to write to stdin: {e}")
            else:
                # Unix-like 系统
                yes_proc = subprocess.Popen(["yes", "yes"], stdout=subprocess.PIPE)
                self.proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdin=yes_proc.stdout,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )

            final_host = env.get("HOST", "127.0.0.1")
            final_port = env.get("PORT", "9621")

            # 确保端口是有效的数字
            try:
                final_port = str(int(final_port))
            except (ValueError, TypeError):
                final_port = "9621"
                logger.warning(f"[LightragServer] Invalid port, using default: 9621")

            logger.info(f"[LightragServer] Logs: {stdout_log_path}, {stderr_log_path}")

            if wait_gating:
                # Health-check gating to confirm server is actually listening（参数化 + 指数退避）
                try:
                    import httpx
                    health_host = '127.0.0.1' if str(final_host) in ('0.0.0.0', '::', '') else str(final_host)
                    hc_url = f"http://{health_host}:{final_port}/healthz"
                    total_timeout = float(env.get('LIGHTRAG_HEALTH_TIMEOUT', '45'))
                    interval = float(env.get('LIGHTRAG_HEALTH_INTERVAL_INITIAL', '0.5'))
                    max_interval = float(env.get('LIGHTRAG_HEALTH_INTERVAL_MAX', '1.5'))
                    deadline = time.time() + total_timeout
                    last_err = None
                    # 快速检测是否瞬时退出，便于尽早给出日志
                    time.sleep(0.2)
                    if self.proc and self.proc.poll() is not None:
                        logger.error(f"[LightragServer] Server process exited immediately with code {self.proc.returncode}")
                        _stderr_tail = _safe_tail(stderr_log_path)
                        _stdout_tail = _safe_tail(stdout_log_path)
                        if _stderr_tail:
                            logger.error(f"[LightragServer] stderr tail:\n{_stderr_tail}")
                        if _stdout_tail:
                            logger.error(f"[LightragServer] stdout tail:\n{_stdout_tail}")
                        return False

                    while time.time() < deadline:
                        try:
                            r = httpx.get(hc_url, timeout=2.0)
                            if r.status_code < 500:
                                logger.info(f"[LightragServer] Server started at http://{final_host}:{final_port}")
                                logger.info(f"[LightragServer] WebUI: http://{final_host}:{final_port}/webui")
                                return True
                        except Exception as e:
                            last_err = e
                        time.sleep(interval)
                        interval = min(max_interval, interval * 1.2)
                    logger.error(f"[LightragServer] Health check failed for {hc_url}: {last_err}")
                    # Try to surface last few stderr/stdout lines to parent log for quick diagnosis
                    _stderr_tail = _safe_tail(stderr_log_path)
                    _stdout_tail = _safe_tail(stdout_log_path)
                    if _stderr_tail:
                        logger.error(f"[LightragServer] stderr tail:\n{_stderr_tail}")
                    if _stdout_tail:
                        logger.error(f"[LightragServer] stdout tail:\n{_stdout_tail}")
                except Exception as e:
                    logger.error(f"[LightragServer] Health check gating error: {e}")

                return False
            else:
                # 非阻塞模式：立即返回，健康检查在监控线程中由使用方自行处理或查看日志
                logger.info(f"[LightragServer] Started (non-blocking) at http://{final_host}:{final_port}, skipping health-gating")
                return True

        except Exception as e:
            logger.error(f"[LightragServer] Failed to start server: {e}")
            return False

    def start(self, wait_ready: bool = False):
        """启动服务器
        
        Args:
            wait_ready: 是否阻塞等待健康检查通过
        """
        if self.proc is not None and self.proc.poll() is None:
            logger.warning("[LightragServer] Server is already running")
            return self.proc

        logger.info("[LightragServer] Starting LightRAG server...")

        # 启动服务器进程
        if not self._start_server_process(wait_gating=wait_ready):
            return None

        # 任何监控开启都需要运行标志
        self._monitor_running = True

        # 启动父进程监控线程
        if not self.disable_parent_monitoring and self.parent_pid is not None:
            self._monitor_thread = threading.Thread(target=self._monitor_parent, daemon=True)
            self._monitor_thread.start()
            logger.info(f"[LightragServer] Parent process monitoring enabled for PID {self.parent_pid}")
        else:
            logger.info(f"[LightragServer] Parent process monitoring disabled (disabled={self.disable_parent_monitoring}, pid={self.parent_pid})")

        # 启动进程监控线程（用于自动重启）
        if self.max_restarts > 0:
            self._proc_monitor_thread = threading.Thread(target=self._monitor_server_process, daemon=True)
            self._proc_monitor_thread.start()
            logger.info("[LightragServer] Process monitoring enabled for auto-restart")

        return self.proc

    def stop(self):
        """停止服务器"""
        logger.info("[LightragServer] Stopping server...")

        # 停止监控线程
        self._monitor_running = False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None
        if getattr(self, "_proc_monitor_thread", None) is not None:
            try:
                self._proc_monitor_thread.join(timeout=2)
            except Exception:
                pass
            self._proc_monitor_thread = None

        # 停止服务器进程
        if self.proc is not None:
            try:
                # 尝试优雅关闭
                self.proc.terminate()

                # 等待进程结束
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # 强制杀死进程
                    logger.warning("[LightragServer] Force killing server process")
                    self.proc.kill()
                    self.proc.wait()

                logger.info("[LightragServer] Server stopped")

            except Exception as e:
                logger.error(f"[LightragServer] Error stopping server: {e}")
            finally:
                self.proc = None
        else:
            logger.info("[LightragServer] Server is not running")

        # 清理临时启动脚本
        try:
            if getattr(self, "_script_path", None):
                os.remove(self._script_path)
                self._script_path = None
        except Exception:
            pass

    def is_running(self):
        """检查服务器是否在运行"""
        return self.proc is not None and self.proc.poll() is None

    def get_current_port(self):
        """获取当前使用的端口号"""
        try:
            # 从环境变量中获取端口
            port = self.extra_env.get("PORT", "9621")
            return int(port)
        except (ValueError, TypeError):
            # 如果端口不是有效数字，返回默认端口
            return 9621

    def get_server_url(self):
        """获取服务器URL"""
        port = self.get_current_port()
        host = self.extra_env.get("HOST", "127.0.0.1")
        return f"http://{host}:{port}"

    def get_webui_url(self):
        """获取WebUI URL"""
        port = self.get_current_port()
        host = self.extra_env.get("HOST", "127.0.0.1")
        return f"http://{host}:{port}/webui"


# -------- helpers --------
def _safe_tail(file_path: str, num_lines: int = 80) -> str:
    try:
        if not file_path or not os.path.exists(file_path):
            return ""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return ''.join(lines[-num_lines:])
    except Exception:
        return ""

if __name__ == "__main__":
    server = LightragServer()
    proc = server.start()
    try:
        proc.wait()
    except KeyboardInterrupt:
        server.stop()

    # import openai
    # client = openai.OpenAI(api_key="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")
    # resp = client.embeddings.create(
    #     input="test",
    #     model="text-embedding-3-large"
    # )
    # print(len(resp.data[0].embedding))