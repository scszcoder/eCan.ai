# taken from stackoverflow
# https://stackoverflow.com/questions/5227107/python-code-to-read-registry

from config.app_info import app_info

def getECBotDataHome():
    return app_info.appdata_path
