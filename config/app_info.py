import sys
import os, errno
import tempfile
import platform
from pathlib import Path
from config.constants import *

# 只在 Windows 平台导入 winreg
if platform.system() == 'Windows':
    import winreg
    proc_arch = os.environ['PROCESSOR_ARCHITECTURE'].lower()


class AppInfo:
    def __init__(self):
        print("init app info object")
        self.app_home_path = self._app_home_path()
        self.app_resources_path = self._app_resources_path()
        self.appdata_path = self._appdata_path()
        self.appdata_temp_path = self._appdata_temp_path()

    # 在打包后的可执行文件中运行,获取每次运行时解压的临时文件路径
    def _prod_app_home_path(self):
        return getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))

    def _dev_app_home_path(self):
        # 获取当前脚本的绝对路径
        script_path = os.path.abspath(__file__)
        # 获取当前脚本所在的目录
        script_dir = os.path.dirname(script_path)
        # 获取当前运行项目的根目录
        root_dir = os.path.dirname(script_dir)
        # print(f"ecbot execute home path:{root_dir}")

        return root_dir

    def _app_home_path(self):
        # pyinstaller 打包程序运行后解压的临时文件根目录
        if getattr(sys, 'frozen', False):
            root_dir = self._prod_app_home_path()
        else:
            root_dir = self._dev_app_home_path()
        print(f"app ecbot home path:{root_dir}")

        return root_dir

    def _app_resources_path(self):
        ecbot_resource_dir = os.path.join(self._app_home_path(), "resource")
        print(f"app ecbot resources path:{ecbot_resource_dir}")

        return ecbot_resource_dir

    def _prod_appdata_path(self):
        # 检查操作系统类型，并确定 APPDATA 路径
        if platform.system() == 'Windows':
            ecb_data_home = ""

            # 获取处理器架构
            current_proc_arch = os.environ.get('PROCESSOR_ARCHITECTURE', '').lower()
            print(f"Processor architecture: {current_proc_arch}")

            # 设置注册表访问键
            if current_proc_arch in ['x86', 'amd64']:
                arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
            else:
                # 默认使用标准访问
                arch_keys = {0}

            print("arch_keys: ", arch_keys)

            for arch_key in arch_keys:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | arch_key)
                # print("key: ", key)
                # print("range: ", winreg.QueryInfoKey(key)[0])

                try:
                    ecb_data_home = winreg.QueryValueEx(key, 'ECBOT_DATA_HOME')[0]
                except OSError as e:
                    if e.errno == errno.ENOENT:
                        # DisplayName doesn't exist in this skey
                        pass
                finally:
                    key.Close()
                    if ecb_data_home:
                        ecb_data_home = ecb_data_home.replace('\\', '/')
                        print("ECBot DATA Home: ", ecb_data_home)
                        return ecb_data_home

            # 如果没有找到环境变量，使用默认路径
            default_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), APP_NAME)
            print(f"Using default Windows appdata path: {default_path}")
            if not os.path.exists(default_path):
                os.makedirs(default_path, exist_ok=True)
            return default_path

        elif platform.system() == 'Darwin':  # macOS
            # 获取当前用户的主目录路径
            home_dir = str(Path.home())
            appdata_os_path = os.path.join(home_dir, 'Library', 'Application Support')
            # 在 Application Support 文件夹中创建一个名为 "ecbot" 的子文件夹
            ecbot_appdata_path = os.path.join(appdata_os_path, APP_NAME)
            if not os.path.exists(ecbot_appdata_path):
                os.makedirs(ecbot_appdata_path, exist_ok=True)
            return ecbot_appdata_path

        else:  # Linux
            # 使用 XDG Base Directory 规范
            home_dir = str(Path.home())
            xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.join(home_dir, '.local', 'share'))
            ecbot_appdata_path = os.path.join(xdg_data_home, APP_NAME)
            if not os.path.exists(ecbot_appdata_path):
                os.makedirs(ecbot_appdata_path, exist_ok=True)
            return ecbot_appdata_path

    def _dev_appdata_path(self):
        root_dir = self._dev_app_home_path()
        # print(f"ecbot dev appdata root path:{root_dir}")

        return root_dir

    def _appdata_path(self):
        # release application
        if getattr(sys, 'frozen', False):
            root_dir = self._prod_appdata_path()
        else:
            root_dir = self._dev_appdata_path()
        print(f"ecbot appdata home path:{root_dir}")

        return root_dir

    def _appdata_temp_path(self):
        """获取应用临时目录"""
        if platform.system() == 'Windows':
            # 使用 LOCALAPPDATA 下的 ECBot 临时目录
            appdata_local = os.environ.get('LOCALAPPDATA', tempfile.gettempdir())
            temp_path = os.path.join(appdata_local, "ECBot", "Temp")
        else:  # macOS/Linux
            # 使用用户主目录下的隐藏临时目录
            home_dir = str(Path.home())
            temp_path = os.path.join(home_dir, ".ecbot", "temp")

        # 确保目录存在
        if not os.path.exists(temp_path):
            os.makedirs(temp_path, exist_ok=True)

        print(f"appdata temp path: {temp_path}")
        return temp_path


# init
app_info = AppInfo()