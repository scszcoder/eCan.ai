import os
import sys
import shutil
import logging
from config.constants import *
from config.app_info import app_info
from utils.logger_helper import logger_helper
from bot.envi import *

ecb_data_homepath = getECBotDataHome()
runlogs_dir = ecb_data_homepath + "/runlogs"
if not os.path.isdir(runlogs_dir):
    os.mkdir(runlogs_dir)

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


app_settings = AppSettings()