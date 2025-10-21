import sys
import os, errno
import tempfile
import platform
from pathlib import Path
from config.constants import *

# Only import winreg on Windows platform
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
        self.version = self._get_version()

    # Running in packaged executable, get temporary file path extracted at each run
    def _prod_app_home_path(self):
        return getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))

    def _dev_app_home_path(self):
        # Get absolute path of current script
        script_path = os.path.abspath(__file__)
        # Get directory containing current script
        script_dir = os.path.dirname(script_path)
        # Get root directory of current running project
        root_dir = os.path.dirname(script_dir)
        # print(f"ecbot execute home path:{root_dir}")

        return root_dir

    def _app_home_path(self):
        # PyInstaller packaged program's temporary file root directory after extraction
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
        # Check OS type and determine APPDATA path
        if platform.system() == 'Windows':
            ecb_data_home = ""

            # Get processor architecture
            current_proc_arch = os.environ.get('PROCESSOR_ARCHITECTURE', '').lower()
            print(f"Processor architecture: {current_proc_arch}")

            # Set registry access keys
            if current_proc_arch in ['x86', 'amd64']:
                arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
            else:
                # Use standard access by default
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

            # If environment variable not found, use default path
            default_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), APP_NAME)
            print(f"Using default Windows appdata path: {default_path}")
            if not os.path.exists(default_path):
                os.makedirs(default_path, exist_ok=True)
            return default_path

        elif platform.system() == 'Darwin':  # macOS
            # Get current user's home directory path
            home_dir = str(Path.home())
            appdata_os_path = os.path.join(home_dir, 'Library', 'Application Support')
            # Create a subfolder named "ecbot" in Application Support folder
            ecbot_appdata_path = os.path.join(appdata_os_path, APP_NAME)
            if not os.path.exists(ecbot_appdata_path):
                os.makedirs(ecbot_appdata_path, exist_ok=True)
            return ecbot_appdata_path

        else:  # Linux
            # Use XDG Base Directory specification
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
        """Get application temporary directory"""
        if platform.system() == 'Windows':
            # Use LOCALAPPDATA APP_NAME temporary directory
            appdata_local = os.environ.get('LOCALAPPDATA', tempfile.gettempdir())
            temp_path = os.path.join(appdata_local, APP_NAME, "Temp")
        else:  # macOS/Linux
            # Use hidden temporary directory under user home directory, following APP_NAME
            home_dir = str(Path.home())
            temp_path = os.path.join(home_dir, f".{APP_NAME}", "temp")

        # Ensure directory exists
        if not os.path.exists(temp_path):
            os.makedirs(temp_path, exist_ok=True)

        print(f"appdata temp path: {temp_path}")
        return temp_path
    
    def _get_version(self):
        """Get application version from VERSION file"""
        try:
            # Try to read from VERSION file in project root
            version_file = Path(self.app_home_path) / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
                if version:
                    print(f"App version from VERSION file: {version}")
                    return version
        except Exception as e:
            print(f"Failed to read VERSION file: {e}")
        
        # Fallback to default version
        default_version = "1.0.0"
        print(f"Using default version: {default_version}")
        return default_version


# init
app_info = AppInfo()