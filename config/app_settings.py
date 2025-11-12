import os
import sys
import shutil
from config.constants import RESOURCE, FOLDER_SKILLS, FOLDER_SETTINGS, FOLDER_RUNLOGS, FOLDER_DATA, APP_NAME
from config.app_info import app_info
from pathlib import Path
from config.envi import getECBotDataHome

# Define the data home path at the module level so it can be imported by other modules.
ecb_data_homepath = getECBotDataHome()

def copy_skills_file():
    """
        If release version should copy some resource skills files from running unzip temp file to appdata files,
        only copy public files. This ensures skills can be modified without permission issues.
    """
    ecbot_home_path = app_info.app_home_path
    app_skills_public_dir = ecbot_home_path + "/" + RESOURCE + "/" + FOLDER_SKILLS + "/public"

    ecbot_appdata_path = app_info.appdata_path
    appdata_skills_public_dir = ecbot_appdata_path + "/" + FOLDER_SKILLS + "/public"

    if os.path.exists(appdata_skills_public_dir):
        try:
            shutil.rmtree(appdata_skills_public_dir)
            print(f"delete appdata skills public dir {appdata_skills_public_dir}")
        except FileNotFoundError:
            print(f"Warning: some files in {appdata_skills_public_dir} already missing, ignore.")
        except Exception as e:
            print(f"Warning: failed to delete {appdata_skills_public_dir}: {e}")
    else:
        print("appdata skills public dir not existed")

    # copy skills public files to appdata dir
    print(f"copy skills public files from {app_skills_public_dir} to {appdata_skills_public_dir}")
    try:
        shutil.copytree(app_skills_public_dir, appdata_skills_public_dir)
    except FileExistsError:
        print(f"Warning: {appdata_skills_public_dir} already exists, skipping copy")
    except FileNotFoundError as e:
        print(f"Warning: copytree failed, missing file: {e}")
    except Exception as e:
        print(f"Warning: copytree failed with error: {e}")


def create_appdata_dirs():
    ecbot_appdata_root_dir = app_info.appdata_path

    # init settings
    folder_settings = ecbot_appdata_root_dir + "/" + FOLDER_SETTINGS
    if not os.path.exists(folder_settings):
        os.mkdir(folder_settings)
    else:
        print(f"folder {folder_settings} is existed")

    # init runlogs
    folder_runlogs = ecbot_appdata_root_dir + "/" + FOLDER_RUNLOGS
    if not os.path.exists(folder_runlogs):
        os.mkdir(folder_runlogs)
    else:
        print(f"folder {folder_runlogs} is existed")

    # init skills
    folder_skills = ecbot_appdata_root_dir + "/" + FOLDER_SKILLS
    if not os.path.exists(folder_skills):
        os.mkdir(folder_skills)
    else:
        print(f"folder {folder_skills} is existed")

    # init data
    folder_data = ecbot_appdata_root_dir + "/" + FOLDER_DATA
    if not os.path.exists(folder_data):
        os.mkdir(folder_data)
    else:
        print(f"folder {folder_data} is existed")


# init some template file from resource to appdata
def init_settings_files():
    ecbot_appdata_root_dir = app_info.appdata_path
    ecbot_resources_dir = app_info.app_resources_path

    # copy role.json template file to appdata folder
    appdata_settings_role_file = ecbot_appdata_root_dir + "/" + FOLDER_SETTINGS + "/role.json"
    if not os.path.exists(appdata_settings_role_file):
        shutil.copyfile(ecbot_resources_dir + "/" + FOLDER_SETTINGS + "/role.json", appdata_settings_role_file)
    else:
        print(f"appdata settings role.json file is existed")


def is_frozen():
    return getattr(sys, 'frozen', False)

class AppSettings:
    def __init__(self):
        # Handle PyInstaller packaged path issues
        if getattr(sys, 'frozen', False):
            # PyInstaller packaged environment: use _MEIPASS as root directory
            if hasattr(sys, '_MEIPASS'):
                self.root_dir = Path(sys._MEIPASS)
            else:
                self.root_dir = Path(sys.executable).parent
            print(f"[PyInstaller] Using root_dir: {self.root_dir}")
        else:
            # Development environment: use relative path
            self.root_dir = Path(__file__).parent.parent
            print(f"[Development] Using root_dir: {self.root_dir}")

        self.gui_v2_dir = self.root_dir / "gui_v2"
        self.dist_dir = self.gui_v2_dir / "dist"

        # Debug information
        print(f"[AppSettings] gui_v2_dir: {self.gui_v2_dir}")
        print(f"[AppSettings] dist_dir: {self.dist_dir}")
        print(f"[AppSettings] dist_dir exists: {self.dist_dir.exists()}")
        if self.dist_dir.exists():
            print(f"[AppSettings] dist_dir contents: {list(self.dist_dir.iterdir())}")

        # Web mode configuration
        # If packaged, force prod, otherwise use environment variable
        if is_frozen():
            self.web_mode = 'prod'
        else:
            self.web_mode = os.getenv('ECBOT_WEB_MODE', 'dev')  # Default development mode
        self.vite_dev_server = "http://localhost:3000"
        
        print("init app settings")
        # init application some settings, include create some folder and copy some static files, etc. logs, skill files
        # logger_helper.setup(APP_NAME, app_info.app_home_path + "/runlogs/" + APP_NAME + ".log", logging.DEBUG)
        # logger_helper.setup(APP_NAME, ecb_data_homepath + "/runlogs/" + APP_NAME + ".log", logging.DEBUG)

        # if getattr(sys, 'frozen', False):
        #     create_appdata_dirs()
        #     init_settings_files()
        #     copy_skills_file()
        # else:
        #     print('debug mode version so not need init some appdata config files')

    @property
    def is_dev_mode(self):
        return self.web_mode.lower() == 'dev'
    
    @property
    def is_prod_mode(self):
        return self.web_mode.lower() == 'prod'
    
    def get_web_url(self):
        """Get Web page URL"""
        if self.is_dev_mode:
            print(f"[AppSettings] Development mode: using {self.vite_dev_server}")
            return self.vite_dev_server
        else:
            index_path = self.dist_dir / "index.html"
            print(f"[AppSettings] Production mode: looking for {index_path}")

            if index_path.exists():
                url = f"file://{index_path.absolute().as_posix()}"
                print(f"[AppSettings] Found index.html, URL: {url}")
                return url
            else:
                print(f"[AppSettings] ERROR: index.html not found at {index_path}")
                print(f"[AppSettings] dist_dir exists: {self.dist_dir.exists()}")
                if self.dist_dir.exists():
                    print(f"[AppSettings] dist_dir contents:")
                    for item in self.dist_dir.iterdir():
                        print(f"  - {item.name}")
                else:
                    print(f"[AppSettings] dist_dir does not exist: {self.dist_dir}")
                return None


app_settings = AppSettings()
