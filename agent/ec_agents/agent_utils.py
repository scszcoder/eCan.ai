import ast
import json

from common.models import VehicleModel
from utils.server import HttpServer
from utils.time_util import TimeUtil
from gui.LocalServer import start_local_server_in_thread, create_mcp_client, create_sse_client
from agent.cloud_api.cloud_api import *
import asyncio
import traceback



from lzstring import LZString
import openpyxl
import tzlocal
from datetime import timedelta
import platform
from pynput.mouse import Controller
from PySide6.QtWebEngineWidgets import QWebEngineView

from utils.logger_helper import logger_helper
from tests.unittests import *
from tests.agent_tests import *

from agent.ec_agents.build_agents import *
import concurrent.futures


def save_agents(mainwin):
    try:
        mainwin.save_agents()
    except Exception as e:
        mainwin.showMsg(str(e))



def load_agents_from_cloud(mainwin):
    try:
        mainwin.load_agents_from_cloud()
    except Exception as e:
        mainwin.showMsg(str(e))