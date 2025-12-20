import sys
import os
import tempfile
import platform
from pathlib import Path
from config.constants import *


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
        """Get production application data path.
        
        Uses standard OS-specific paths (matches build_config.json):
        - Windows: %LOCALAPPDATA%\eCan
        - macOS: ~/Library/Application Support/eCan
        - Linux: ~/.local/share/eCan (XDG Base Directory)
        """
        if platform.system() == 'Windows':
            # Windows: Use %LOCALAPPDATA%\eCan
            localappdata = os.environ.get('LOCALAPPDATA', '')
            if not localappdata:
                # Fallback to %USERPROFILE%\AppData\Local if LOCALAPPDATA not set
                userprofile = os.environ.get('USERPROFILE', '')
                localappdata = os.path.join(userprofile, 'AppData', 'Local')
            
            appdata_path = os.path.join(localappdata, APP_NAME)
            print(f"Windows appdata path: {appdata_path}")
            
        elif platform.system() == 'Darwin':  # macOS
            # macOS: Use ~/Library/Application Support/eCan
            home_dir = str(Path.home())
            appdata_path = os.path.join(home_dir, 'Library', 'Application Support', APP_NAME)
            print(f"macOS appdata path: {appdata_path}")
            
        else:  # Linux
            # Linux: Use XDG Base Directory specification (~/.local/share/eCan)
            home_dir = str(Path.home())
            xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.join(home_dir, '.local', 'share'))
            appdata_path = os.path.join(xdg_data_home, APP_NAME)
            print(f"Linux appdata path: {appdata_path}")
        
        # Create directory if it doesn't exist
        if not os.path.exists(appdata_path):
            os.makedirs(appdata_path, exist_ok=True)
            print(f"Created appdata directory: {appdata_path}")
        
        return appdata_path

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