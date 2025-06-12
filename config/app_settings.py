import os
import sys
import shutil
import logging
from config.constants import RESOURCE, FOLDER_SKILLS, FOLDER_SETTINGS, FOLDER_RUNLOGS, FOLDER_DATA, APP_NAME
from config.app_info import app_info
from utils.logger_helper import logger_helper
from bot.envi import getECBotDataHome
from pathlib import Path

ecb_data_homepath = getECBotDataHome()
runlogs_dir = ecb_data_homepath + "/runlogs"
if not os.path.isdir(runlogs_dir):
    os.mkdir(runlogs_dir)
    print("create runlogs directory ", runlogs_dir)
else:
    print(f"runlogs {runlogs_dir} directory is existed")

def copy_skills_file():
    """
        if release version should copy some resource skills files from running unzip temp file to appdata files,
        only copy public files
    """
    ecbot_home_path = app_info.app_home_path
    app_skills_public_dir = ecbot_home_path + "/" + RESOURCE + "/" + FOLDER_SKILLS + "/public"

    ecbot_appdata_path = app_info.appdata_path
    appdata_skills_public_dir = ecbot_appdata_path + "/" + FOLDER_SKILLS + "/public"

    if os.path.exists(appdata_skills_public_dir):
        shutil.rmtree(appdata_skills_public_dir)
        print(f"delete appdata skills public dir {appdata_skills_public_dir}")
    else:
        print("appdata skills public dir existed")

    # copy skills public files to appdata dir
    print(f"copy skills public files from {app_skills_public_dir} to {appdata_skills_public_dir}")
    shutil.copytree(app_skills_public_dir, appdata_skills_public_dir)


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


class AppSettings:
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent
        self.gui_v2_dir = self.root_dir / "gui_v2"
        self.dist_dir = self.gui_v2_dir / "dist"
        
        # Web 模式配置
        self.web_mode = os.getenv('ECBOT_WEB_MODE', 'dev')  # 默认开发模式
        self.vite_dev_server = "http://localhost:3000"
        
        print("init app settings")
        # init application some settings, include create some folder and copy some static files, etc. logs, skill files
        # logger_helper.setup(APP_NAME, app_info.app_home_path + "/runlogs/" + APP_NAME + ".log", logging.DEBUG)
        logger_helper.setup(APP_NAME, ecb_data_homepath + "/runlogs/" + APP_NAME + ".log", logging.DEBUG)

        if getattr(sys, 'frozen', False):
            create_appdata_dirs()
            init_settings_files()
            copy_skills_file()
        else:
            print('debug mode version so not need init some appdata config files')

    @property
    def is_dev_mode(self):
        return self.web_mode.lower() == 'dev'
    
    @property
    def is_prod_mode(self):
        return self.web_mode.lower() == 'prod'
    
    def get_web_url(self):
        """获取 Web 页面的 URL"""
        if self.is_dev_mode:
            return self.vite_dev_server
        else:
            index_path = self.dist_dir / "index.html"
            if index_path.exists():
                return f"file://{index_path}"
            return None


app_settings = AppSettings()
