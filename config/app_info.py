import sys
import os, errno
import tempfile
from pathlib import Path
from config.constants import *
if sys.platform == 'win32':
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
        ecbot_resource_dir = self._app_home_path() + "/resource"
        print(f"app ecbot resources path:{ecbot_resource_dir}")

        return ecbot_resource_dir

    def _prod_appdata_path(self):
        # 检查操作系统类型，并确定 APPDATA 路径
        if os.name == 'nt':  # Windows
            ecb_data_home = ""
            print(proc_arch)
            #    print(proc_arch64)
            #     if proc_arch == 'x86' and not proc_arch64:
            #         arch_keys = {0}
            #    elif proc_arch == 'x86' or proc_arch == 'amd64':
            if proc_arch == 'x86' or proc_arch == 'amd64':
                arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
            else:
                raise Exception("Unhandled arch: %s" % proc_arch)

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
                    ecb_data_home = ecb_data_home.replace('\\', '/')
                    print("ECBot DATA Home: ", ecb_data_home)
                    return ecb_data_home
        else:  # macOS
            # 获取当前用户的主目录路径
            home_dir = str(Path.home())
            appdata_os_path = os.path.join(home_dir, 'Library', 'Application Support')
            # 在 APPDATA 或 Application Support 文件夹中创建一个名为 "ecbot" 的子文件夹
            ecbot_appdata_path = os.path.join(appdata_os_path, APP_NAME)
            if not os.path.exists(ecbot_appdata_path):
                os.makedirs(ecbot_appdata_path)

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
        temp_path = os.path.join(tempfile.gettempdir(), "AppData", "Local", "Temp")
        if not os.path.exists(temp_path):
            os.makedirs(temp_path)
        print(f"appdata temp path:{temp_path}")

        return temp_path


# init
app_info = AppInfo()