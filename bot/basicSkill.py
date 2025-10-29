#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ast
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import traceback
import webbrowser
from datetime import datetime, timedelta
import asyncio
import platform
import glob
import chardet
from utils.lazy_import import lazy
import importlib.util
import requests
import io

from ping3 import ping
from app_context import AppContext
from bot.Cloud import send_query_chat_request_to_cloud8, upload_file, req_cloud_read_screen, upload_file8, req_cloud_read_screen8, \
    send_query_chat_request_to_cloud, wanSendRequestSolvePuzzle, wanSendConfirmSolvePuzzle, \
    send_run_ext_skill_request_to_cloud, send_report_run_ext_skill_status_request_to_cloud, \
    download_file, send_update_missions_ex_status_to_cloud, send_reg_steps_to_cloud
from bot.lanAPI import req_lan_read_screen8
from bot.Logger import log3, log6, log68
from utils.logger_helper import logger_helper as logger
from utils.permission_helper import safe_write, safe_append
from utils.path_manager import path_manager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from bot.missions import EBMISSION
from bot.envi import getECBotDataHome
import shutil
import zipfile

import psutil

import pyperclip

if sys.platform == 'win32':
    import win32gui
    import win32con
    import win32api
    import win32process
    # import pyscreeze
elif sys.platform == 'darwin':
    from AppKit import NSWorkspace
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID
    )


symTab = globals()
from pynput.mouse import Controller
# from bot.envi import *
import ctypes

from config.app_info import app_info

STEP_GAP = 5
rd_screen_count = 0
mouse = Controller()

mission_vars = []
# global function_table
MAX_STEPS = 1000000000
page_stack = []
current_context = None

screen_loc = (0, 0)

DEFAULT_RUN_STATUS = "Completed:0"

TEST_RUN_CNT = 0

ecb_data_homepath = getECBotDataHome()


# the dictionary structure is {"machine name": {"skid", {"page": {"section": [{"icon anchor name": [scales...]}....]}}}}
# each time processExtractInfo executes, this dic will be accumulated and built up.
# and each time processExtractInfo executes, it will try to use this dict to predict the scale factor to use for a cloud side icon match action.
icon_match_dict = {}
#####################################################################################
#  some useful utility functions
#####################################################################################
def getScreenSize():
    """
    Get accurate screen size across different platforms

    Returns:
        tuple: (width, height) of the primary screen
    """
    try:
        if sys.platform == 'win32':
            # Windows: Get accurate physical resolution handling DPI scaling
            try:
                # Method 1: Try to get actual resolution using EnumDisplaySettings
                try:
                    import win32api
                    import win32con

                    # Get primary display device
                    device = win32api.EnumDisplayDevices()
                    if device:
                        # Get current display settings for actual resolution
                        settings = win32api.EnumDisplaySettings(device.DeviceName, win32con.ENUM_CURRENT_SETTINGS)
                        if settings:
                            width = settings.PelsWidth
                            height = settings.PelsHeight
                            logger.info(f"getScreenSize (Windows actual): {width}x{height}")
                            return (width, height)
                except:
                    pass

                # Method 2: Try DPI-aware GetSystemMetrics
                try:
                    import ctypes
                    from ctypes import wintypes

                    # Set process DPI awareness to get real resolution
                    try:
                        # Try Windows 8.1+ method first
                        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
                    except:
                        try:
                            # Fallback to Windows Vista+ method
                            ctypes.windll.user32.SetProcessDPIAware()
                        except:
                            pass

                    # Get screen dimensions
                    user32 = ctypes.windll.user32
                    width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                    height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

                    if width > 0 and height > 0:
                        logger.info(f"getScreenSize (Windows DPI aware): {width}x{height}")
                        return (width, height)
                except:
                    pass

                # Method 3: Fallback to basic win32api
                try:
                    import win32api
                    width = win32api.GetSystemMetrics(0)  # SM_CXSCREEN
                    height = win32api.GetSystemMetrics(1)  # SM_CYSCREEN
                    logger.info(f"getScreenSize (Windows basic): {width}x{height}")
                    return (width, height)
                except ImportError:
                    pass

            except Exception as e:
                logger.warning(f"Windows screen size detection failed: {e}")
                pass
        elif sys.platform == 'darwin':
            # macOS: Get accurate physical pixel resolution
            try:
                from Quartz import (
                    CGDisplayBounds, CGMainDisplayID, CGDisplayCopyDisplayMode,
                    CGDisplayModeGetPixelWidth, CGDisplayModeGetPixelHeight,
                    CGDisplayModeGetWidth, CGDisplayModeGetHeight
                )

                main_display = CGMainDisplayID()

                # Method 1: Get actual pixel dimensions from display mode (most accurate)
                try:
                    mode = CGDisplayCopyDisplayMode(main_display)
                    if mode:
                        # Try to get pixel dimensions (for Retina displays)
                        try:
                            pixel_width = CGDisplayModeGetPixelWidth(mode)
                            pixel_height = CGDisplayModeGetPixelHeight(mode)
                            if pixel_width > 0 and pixel_height > 0:
                                logger.info(f"getScreenSize (macOS pixel): {pixel_width}x{pixel_height}")
                                return (pixel_width, pixel_height)
                        except:
                            # Fallback to mode dimensions
                            width = CGDisplayModeGetWidth(mode)
                            height = CGDisplayModeGetHeight(mode)
                            if width > 0 and height > 0:
                                logger.info(f"getScreenSize (macOS mode): {width}x{height}")
                                return (width, height)
                except:
                    pass

                # Method 2: Use AppKit with scale factor calculation
                try:
                    from AppKit import NSScreen
                    screens = NSScreen.screens()
                    if screens:
                        main_screen = screens[0]
                        scale_factor = main_screen.backingScaleFactor()
                        frame = main_screen.frame()
                        # Calculate physical pixel dimensions
                        width = int(frame.size.width * scale_factor)
                        height = int(frame.size.height * scale_factor)
                        logger.info(f"getScreenSize (macOS AppKit): {width}x{height}")
                        return (width, height)
                except:
                    pass

                # Method 3: Fallback to bounds (logical resolution)
                bounds = CGDisplayBounds(main_display)
                width = int(bounds.size.width)
                height = int(bounds.size.height)
                logger.info(f"getScreenSize (macOS bounds): {width}x{height}")
                return (width, height)

            except ImportError:
                # If Quartz is not available, try AppKit only
                try:
                    from AppKit import NSScreen
                    screens = NSScreen.screens()
                    if screens:
                        main_screen = screens[0]
                        try:
                            scale_factor = main_screen.backingScaleFactor()
                            frame = main_screen.frame()
                            width = int(frame.size.width * scale_factor)
                            height = int(frame.size.height * scale_factor)
                            logger.info(f"getScreenSize (macOS AppKit only): {width}x{height}")
                            return (width, height)
                        except:
                            frame = main_screen.frame()
                            width = int(frame.size.width)
                            height = int(frame.size.height)
                            logger.info(f"getScreenSize (macOS AppKit logical): {width}x{height}")
                            return (width, height)
                except ImportError:
                    pass
        elif sys.platform.startswith('linux'):
            # Linux: Try to use xrandr or other methods
            try:
                import subprocess
                result = subprocess.run(['xrandr'], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if ' connected primary ' in line or (' connected ' in line and 'primary' in line):
                            # Parse resolution from line like "1920x1080+0+0"
                            import re
                            match = re.search(r'(\d+)x(\d+)', line)
                            if match:
                                width = int(match.group(1))
                                height = int(match.group(2))
                                logger.info(f"getScreenSize: {width}x{height}")
                                return (width, height)
            except (ImportError, subprocess.SubprocessError, FileNotFoundError):
                # Fallback to pyautogui if xrandr not available
                pass

        # Fallback to pyautogui for all platforms
        return lazy.pyautogui.size()

    except Exception as e:
        # Ultimate fallback - return a reasonable default
        print(f"Warning: Could not determine screen size, using default. Error: {e}")
        return (1920, 1080)


def get_default_download_dir():
    home = os.path.expanduser("~").replace("\\", "/")
    return home+"/Downloads/"


def genStepHeader(skillname, los, ver, author, skid, description, stepN):
    header = {
        "name": skillname,
        "os": los,
        "version": ver,
        "author": author,
        "skid": skid,
        "description": description
    }

    return ((stepN+STEP_GAP), ("\"header\":\n" + json.dumps(header, indent=4) + ",\n"))



def genStepOpenApp(action, saverb, app_type, app_link, cargs_type, cargs, win_info, wait, result, stepN):
    stepjson = {
        "type": "App Open",
        "action": action,
        "save_rb": saverb,
        "app_type": app_type,
        "app_link": app_link,
        "cargs_type": cargs_type,
        "cargs": cargs,
        "win_info": win_info,
        "wait":wait,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepGetDefault(var_name, result_var, stepN):
    stepjson = {
        "type": "Get Default",
        "var_name": var_name,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepSaveHtml(html_file_name, html_file_var_name, template, settings, sink, page, sect, theme, stepN, page_data, option=""):
    stepjson = {
        "type": "Save Html",
        "action": "Save Html",
        "settings": settings,
        "local": html_file_name,
        "html_var": html_file_var_name,
        "template": template,
        "option": option,
        "data_sink": sink,
        "page": page,
        "theme": theme,
        "page_data_info": page_data,
        "section": sect
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepPasteToData(result_var, flag_var, stepN):
    stepjson = {
        "type": "Paste To Data",
        "action": "Paste To Data",
        "result_var": result_var,
        "flag_var": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




# extract screen information:
# template: only extract template matched information.....
# root: file path prefix (installation root directory)
# sink: data sink, which holds result
# page: which page is this extration about?
# sect: which section of the page is this extraction about?
# page_data: data on the page extracted from analyzing html file contents. this info will help image analysis
# option: in case this page has no anchor, needs extra help.....
# window title keyword of the window to be screen captured, (default is "" which means top window)
# example option:  "options": "{\"info\": [{\"info_name\": \"label_row\", \"info_type\": \"lines 1\", \"template\": \"2\", \"ref_method\": \"1\", \"refs\": [{\"dir\": \"right inline\", \"ref\": \"entries\", \"offset\": 0, \"offset_unit\": \"box\"}]}]}",
def genStepExtractInfo(template, settings, sink, page, sect, theme, stepN, page_data, options="", win_title_kw=""):
    stepjson = {
        "type": "Extract Info",
        "settings": settings,
        "template": template,
        "options": options,
        "data_sink": sink,
        "win_title_kw": win_title_kw,
        "page": page,
        "theme": theme,
        "page_data_info": page_data,
        "section": sect
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepScreenCapture(area, fformat, text_var, img_var, img_file_var, flag, stepN):
    stepjson = {
        "type": "Screen Capture",
        "area": area,
        "format": fformat,
        "text_var": text_var,
        "img_var": img_var,
        "img_file_var": img_file_var,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepGetWindowsInfo(nth_var, results_var, flag_var, stepN):
    stepjson = {
        "type": "Get Windows Info",
        "nth_var": nth_var,
        "results_var": results_var,
        "flag_var": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepBringWindowToFront(title_var, flag_var, stepN):
    stepjson = {
        "type": "Bring Window To Front",
        "title_var": title_var,
        "flag_var": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# input: file_var - local file, locs - cloud file
# output: presigned_var
def genStepUploadFiles(files_var, settings, ftype, locs_var, results_var, flag_var, stepN):
    stepjson = {
        "type": "Upload Files",
        "settings": settings,
        "files_var": files_var,
        "ftype": ftype,
        "locs": locs_var,
        "results": results_var,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# input: file_var - local file, locs - cloud file
# output:
def genStepDownloadFiles(files_var, settings, ftype, locs_var, results_var, flag_var, stepN):
    stepjson = {
        "type": "Download Files",
        "files_var": files_var,
        "settings": settings,
        "ftype": ftype,
        "locs": locs_var,
        "results": results_var,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepUpdateMissionStatus(status_var_type, status_var, err_var_type, err_var, data_var, results_var, flag_var, stepN):
    stepjson = {
        "type": "Update Mission Status",
        "status_var_type": status_var_type,
        "status_var": status_var,
        "err_var_type": err_var_type,
        "err_var": err_var,
        "data_var": data_var,
        "results": results_var,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepFillRecipients(texts_var, orders_var, site, stepN, option=""):
    stepjson = {
        "type": "Fill Recipient",
        "texts_var": texts_var,
        "orders_var": orders_var,
        "site": site,
        "option": option
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# search information on a screen with a given name and type.
def genStepSearchAnchorInfo(screen, names, name_type, target_types, logic, result, flag, site, break_here, stepN):
    stepjson = {
        "type": "Search Anchor Info",
        "screen": screen,
        "names": names,
        "name_type": name_type,
        "target_types": target_types,
        "logic": logic,
        "result": result,
        "site": site,
        "breakpoint": break_here,
        "status": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# search substring(regular expression) on a piece of info on a screen.
def genStepSearchWordLine(screen, names, name_types, logic, result, flag, site, break_here, stepN):
    stepjson = {
        "type": "Search Word Line",
        "screen": screen,
        "names": names,
        "name_types": name_types,
        "logic": logic,
        "result": result,
        "site": site,
        "breakpoint": break_here,
        "status": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# search some target content on the page, and scroll the target to the target loction on the page.
# at_loc is a rough location, meaning the anchor closest to this location, NOT exactly at this location.
# at_loc is also a 2 dimensional x-y coordinates
def genStepSearchScroll(screen, dir, target, target_type, at_loc, target_loc, flag, resolution, postwait, site, adjustment, stepN):
    stepjson = {
        "type": "Search Scroll",
        "action": "Search Scroll",
        "dir": dir,
        "target": target,
        "target_type": target_type,
        "at_loc": at_loc,
        "target_loc": target_loc,
        "screen": screen,
        "resolution": resolution,
        "postwait": postwait,
        "adjustment": adjustment,
        "site": site,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




# search some target content on the page, and scroll the target to the target loction on the page.
# at_loc is a rough location, meaning the anchor closest to this location, NOT exactly at this location.
# at_loc is also a 2 dimensional x-y coordinates
def genStepScrollToLocation(screen, target, target_type, target_loc, flag, resolution, postwait, site, stepN):
    stepjson = {
        "type": "Scroll To Location",
        "action": "Scroll To Location",
        "target": target,
        "target_type": target_type,
        "target_loc": target_loc,
        "screen": screen,
        "resolution": resolution,
        "postwait": postwait,
        "site": site,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# loc: location on screen, could take value "", "middle" "bottome" "top" - meaning take some unique text that's nearest the location of the screen.
#       the resulting text is defauly putinto the variable "ResolutionCalibrationMarker"
# txt: text to record the location. - caller can also directly specify the text to be extracted, in such a case, loc = ""
# screen: variable that contains the screen content data structure.
# to: put result in this varable name.
# loc: target location on a screen.
def genStepRecordTxtLineLocation(loc, txt, screen, tovar, stepN):
    stepjson = {
        "type": "Text Line Location Record",
        "action": "Extract",
        "location": loc,
        "text": txt,
        "screen": screen,
        "to": tovar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# this could be either "Scroll Up" or "Scroll Down", screen is the screen data pointer, val is the amount to scroll up or down in terms of screen size.
def genStepMouseScroll(action, screen, val, unit, resolution, ran_min, ran_max, postwait, break_here, stepN):
    stepjson = {
        "type": "Mouse Scroll",
        "action": action,
        "screen": screen,
        "amount": val,
        "resolution": resolution,
        "random_min": ran_min,
        "random_max": ran_max,
        "breakpoint": break_here,
        "postwait": postwait,
        "unit": unit
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepMouseMove(x_amount_var, y_amount_var, x_destination_var, y_destination_var, postwait, break_here, stepN):
    stepjson = {
        "type": "Mouse Move",
        "x_amount_var": x_amount_var,
        "y_amount_var": y_amount_var,
        "x_destination_var": x_destination_var,
        "y_destination_var": y_destination_var,
        "breakpoint": break_here,
        "postwait": postwait,
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepMouseClick(action, action_args, saverb, screen, target, target_type, template, nth, offset_from, offset, offset_unit, move_pause, post_wait, post_move, stepN):
    stepjson = {
        "type": "Mouse Click",
        "action": action,               # double click, single click, drag and drop?
        "action_args": action_args,     #can be used to specify things like click speed, or mouse hold time, or mouse move speed?
        "save_rb": saverb,
        "screen": screen,               # screen data.
        "target_name": target,          # information name.
        "target_type": target_type,     #anchor or info or shape or direct,
        "text": template,              # text template
        "nth": nth,                     # [0,0] in case of there are multiple occurance of target on the screen, click on which one? [n, m] would be nth from left, mth from top
        "offset_from": offset_from,      # click at a offset from object's bound box side, left/top/right/bottom/center are choices. if left/right, y coordinate is default to be center, if top/bottom, x coordiate default to be center.
        "offset_unit": offset_unit,      # pixel, box
        "offset": offset,                # offset in x and y direction,
        "move_pause": move_pause,        # after move the mouse pointer to target, pause for certain seconds.
        "post_move": post_move,        # after click, move the mouse pointer to certain offset.
        "post_wait": post_wait           # after click action, wait for a number of seconds.
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepMouseDragDrop(route_var, speed_var, postwait, break_here, stepN):
    stepjson = {
        "type": "Mouse Drag Drop",
        "route_var": route_var,
        "speed_var": speed_var,
        "breakpoint": break_here,
        "postwait": postwait
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# val: key action
# wait_after: #  of seconds to waitafter the key action.
def genStepKeyInput(action, saverb, val, loc, wait_after, stepN):
    stepjson = {
        "type": "Key Input",
        "action": action,
        "action_value": val,
        "save_rb": saverb,
        "location": loc,
        "wait_after": wait_after
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# action: action to perform here - simply text input
#  text: txt to be input.
#  speed: type speed.
#  key_after: key to hit after textinput. (could be "", "enter",
#  wait_after: number of seconds to wait after key_after action.
def genStepTextInput(txt_type, saverb, txt, txt_ref_type, speed, key_after, wait_after, stepN):
    stepjson = {
        "type": "Text Input",
        "txt_ref_type": txt_ref_type,
        "save_rb": saverb,
        "text": txt,
        "txt_type": txt_type,
        "speed": speed,
        "key_after": key_after,
        "wait_after":  wait_after
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# condition is the string for eval condition, in python sytax.
# iftrue, ifelse are the step numbers that point to the instruction to jump to next if condition is true/false.
def genStepCheckCondition(condition, ifelse, ifend, stepN):
    stepjson = {
        "type": "Check Condition",
        "condition": condition,
        "if_else": ifelse,
        "if_end": ifend
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# this is equivalent to jump in assembley, but is this really usefull? I suppose could be used to implement "break" like statement in a loop.
def genStepGoto(gotostep, stepN):
    stepjson = {
        "type": "Goto",
        "goto": gotostep
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# "type": "Repeat",
# "lc_name": loop counter name. need to be unique, usually is the stepname.
# "until": loop condition condition,
# "count": repeat count,
# "end": loop end marker.
def genStepLoop(condition, count, end, lc_name, stepN):
    # for "repeat N times type of loop, add an extra line to initiaize loop counter"
    inserted = ""
    if condition == "":
        stepjson = {
            "type": "Fill Data",
            "fill_type": "direct",
            "from": 0,
            "to": lc_name,
            "result": ""
        }
        inserted =("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n")
        stepN = stepN + STEP_GAP

    stepjson = {
        "type": "Repeat",
        "lc_name": lc_name,
        "until": condition,
        "count": count,
        "end": end
    }

    return ((stepN+STEP_GAP), (inserted + "\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# there are 4 type of stubs(i.e. names) : "else", "end condition", "end loop", "end function", "start function"
# the start
def genStepStub(sname, fname, fargs, stepN):
    stepjson = {
        "type": "Stub",
        "stub_name": sname,
        "func_name": fname,
        "fargs": fargs
    }

    if sname == "start skill":
        logger.debug("GEN STEP STUB START SKILL: "+fname)
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepListDir(dirname, extension, sort_by, sort_order, most_recent, result_var, stepN):
    stepjson = {
        "type": "List Dir",
        "dir": dirname,
        "extension": extension,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "most_recent": most_recent,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepCheckExistence(fntype, fname, result_var, stepN):
    stepjson = {
        "type": "Check Existence",
        "fntype": fntype,
        "file": fname,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepCreateDir(dirname, nametype, result_var, stepN):
    stepjson = {
        "type": "Create Dir",
        "dir": dirname,
        "name_type": nametype,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepReadFile(filename, nametype, filetype, datasink, flag_var, stepN):
    stepjson = {
        "type": "Read File",
        "filename": filename,
        "name_type": nametype,
        "filetype": filetype,
        "datasink": datasink,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepWriteFile(filename, nametype, filetype, datasource, mode, result_var, stepN):
    stepjson = {
        "type": "Write File",
        "filename": filename,
        "name_type": nametype,
        "filetype": filetype,
        "mode": mode,
        "datasource": datasource,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepDeleteFile(filename, nametype, result_var, stepN):
    stepjson = {
        "type": "Delete File",
        "filename": filename,
        "name_type": nametype,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepObtainReviews(product, instructions, review_body, review_title, store_feedback, result_var, stepN):
    stepjson = {
        "type": "Obtain Reviews",
        "product": product,
        "instructions": instructions,
        "review_body": review_body,
        "review_title": review_title,
        "store_feedback": store_feedback,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStep7z(action, var_type, exe_var, in_var, out_path, out_var, result, stepN):
    stepjson = {
        "type": "Seven Zip",
        "action": action,
        "var_type": var_type,
        "exe_var": exe_var,
        "in_var": in_var,
        "out_path": out_path,
        "out_var": out_var,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepZipUnzip(action, var_type, in_var, out_path, out_var, result, stepN):
    stepjson = {
        "type": "Zip Unzip",
        "action": action,
        "var_type": var_type,
        "in_var": in_var,
        "out_path": out_path,
        "out_var": out_var,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepTextToNumber(invar, outvar, stepN):
    stepjson = {
        "type": "Text To Number",
        "intext": invar,
        "numvar": outvar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# when exception occurs, we need to know its cause, and is related data
def genStepEndException(cause, cdata, stepN):
    stepjson = {
        "type": "End Exception",
        "cause": cause,
        "cdata": cdata
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepExceptionHandler(cause, cdata, stepN):
    stepjson = {
        "type": "Exception Handler",
        "cause": cause,
        "cdata": cdata
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# wait
def genStepWait(wait, random_min, random_max, stepN):
    try:
        stepjson = {
            "type": "Wait",
            "random_min": random_min,
            "random_max": random_max,
            "time": wait
        }

        return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGenStepWait:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGenStepWait: traceback information not available:" + str(e)

        print(ex_stat)

def genStepWaitUntil(wait, events_var, ev_relation, result_var, flag_var, stepN):
    stepjson = {
        "type": "Wait Until",
        "events": events_var,
        "events_relation": ev_relation,
        "time_out": wait,
        "result": result_var,
        "flag": flag_var,
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# fname: external script/function name  - very IMPORTANT： this is calling python routine either in a file or a function， this is different from
#          psk function/subroutine
# args: arguments to the external functions.
# entity: "are we calling a script or function?"
# output: output data variable
# stepN: the step number of this step.
def genStepCallExtern(fname, args, entity, output, stepN):
    stepjson = {
        "type": "Call Extern",
        "file": fname,
        "args": args,
        "entity": entity,
        "output": output
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def genStepCallFunction(fname, fargs, output, stepN):
    stepjson = {
        "type": "Call Function",
        "fname": fname,
        "fargs": fargs,
        "return_to": stepN+STEP_GAP,
        "output": output
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def genStepReturn(output, stepN):
    stepjson = {
        "type": "Return",
        "val_var_name": output
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def genStepUseSkill(skname, skpath, skargs, output, stepN):
    stepjson = {
        "type": "Use Skill",
        "skill_name": skname,
        "skill_path": skpath,
        "skill_args": skargs,
        "output": output
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepUseExternalSkill(skid, req_mid, skname, owner, in_data, start_time, verbose, output_var, stepN):
    stepjson = {
        "type": "Use External Skill",
        "skid": skid,
        "requester_mid": req_mid,
        "skname": skname,
        "owner": owner,
        "in_data": in_data,
        "start_time": start_time,
        "verbose": verbose,
        "output": output_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepReportExternalSkillRunStatus(run_id, skid, start_time, end_time, mid, bid, requester, status, output, stepN):
    stepjson = {
        "type": "Report External Skill Run Status",
        "run_id": run_id,
        "skill_id": skid,
        "requester": requester,
        "start_time": start_time,
        "end_time": end_time,
        "status": status,
        "runner_mid": mid,
        "runner_bid": bid,
        "result_data": output
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def genStepOverloadSkill(skname, args, output, stepN):
    stepjson = {
        "type": "Call Function",
        "skill_name": skname,
        "args": args,
        "return_to": str(stepN+STEP_GAP),
        "output": output
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepCreateData(dtype, dname, keyname, keyval, stepN):
    try:
        stepjson = {
            "type": "Create Data",
            "data_type": dtype,
            "data_name": dname,
            "key_name": keyname,
            "key_value": keyval
        }

        return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGenStepCreateData:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGenStepCreateData: traceback information not available:" + str(e)

        print(ex_stat)

def genStepCheckAppRunning(appname, result, stepN):
    stepjson = {
        "type": "Check App Running",
        "appname": appname,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepBringAppToFront(win_title_kw, win_info, flag, stepN):
    stepjson = {
        "type": "Bring App To Front",
        "win_title_kw": win_title_kw,
        "win_info": win_info,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepGetTopWindow(win_info, step_flag, stepN):
    stepjson = {
        "type": "Get Top Window Info",
        "result": win_info,
        "flag": step_flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepGetAllWindowsInfo(win_info, step_flag, stepN):
    stepjson = {
        "type": "Get All Windows Info",
        "result": win_info,
        "flag": step_flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




#fill type: array fill, value fill, object fill?
# src : src variable
# sink : sink variable
# result: result variable to tell whether this fill succeeded or not? (could failed if type is not right or src or sink doesn't exist at all....)
def genStepFillData(fill_type, src, sink, result, stepN):
    stepjson = {
        "type": "Fill Data",
        "fill_type": fill_type,
        "from": src,
        "to": sink,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# goals: "ordered customer service"/"potential customer service"/"check system message"/"research product"/
# options: yet to be defined, room for expansion
# msgs_and_orders: [{ "order": {...order info....}, "msgs": [ {id, timestamp, sender, msg_text}....] (most recent at position 0)} .... ], "attachments": ["fullpath link1", "fullpath link2"]}.....]
# msg_reponses: [{order_id, most recent msg id, action itmes[action: , action target:, response_text:}....]]
# action: ["return_and_refund", "full refund", "partial refund %", "full resend", "partial resend"]
# action target would include: product id, product name, variations, quantity, weight,
# reponse_text would be the message to send back to customer.....
def genStepThink(goals_var, options_var, products_var, sys_prompt_var, user_prompt_var, msg_responses_var, flag_var, stepN):
    stepjson = {
        "type": "Think",
        "goals": goals_var,
        "options": options_var,
        "products": products_var,
        "sys_prompt": sys_prompt_var,
        "user_prompt": user_prompt_var,
        "msg_responses": msg_responses_var,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepGenRespMsg(llm_type, llm_model, parameters, products, setup, query, response, result, stepN):
    stepjson = {
        "type": "Gen Resp Msg",
        "llm_type": llm_type,
        "llm_model": llm_model,
        "parameters": parameters,
        "products": products,
        "setup": setup,
        "query": query,
        "response": response,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepUpdateBuyMissionResult(result, flag, stepN):
    stepjson = {
        "type": "Update Buy Mission Result",
        "result": result,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepGoToWindow(win_name, name_type, result, stepN):
    stepjson = {
        "type": "Go To Window",
        "win_name": win_name,
        "name_type": name_type,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# this instruction sends some info from agent/bot to commander.
def genStepReportToBoss(commander_link, self_ip, exlog_data, result, stepN):
    stepjson = {
        "type": "Report To Boss",
        "commander_link": commander_link,
        "self_ip": self_ip,
        "exlog_data": exlog_data,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepCalcObjectsDistance(obj1, obj_type1, obj2, obj_type2, distance_type, distance_dir, result_var, flag_var, stepN):
    stepjson = {
        "type": "Calc Objs Distance",
        "obj_name1": obj1,
        "obj_type1": obj_type1,                     # anchor, info, text
        "obj_name2": obj2,
        "obj_type2": obj_type2,
        "distance_type": distance_type,             # min, max, average
        "distance_dir": distance_dir,               # vertical, horizontal, c2c(center to center)
        "result": result_var,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepAmzDetailsCheckPosition(screen, marker_name, result_var, flag_var, stepN):
    stepjson = {
        "type": "AMZ Details Check Position",
        "marker_name": marker_name,
        "screen": screen,
        "result": result_var,
        "flag": flag_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepAmzPLCalcNCols(sponsors_name, carts_name, options_name, fd_name, result_var, flag_var, stepN):
    stepjson = {
        "type": "AMZ PL Calc Columns",
        "sponsors": sponsors_name,
        "options": options_name,
        "carts": carts_name,
        "deliveries": fd_name,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepMoveDownloadedFileToDestination(prefix, extension, destination, result_var, flag_var, stepN):
    stepjson = {
        "type": "Move Downloaded File",
        "prefix": prefix,
        "extension": extension,
        "destination": destination,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepReadJsonFile(file_name_type, file_name, result_var, flag_var, stepN):
    stepjson = {
        "type": "Read Json File",
        "file_name_type": file_name_type,
        "file_name": file_name,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepReadXlsxFile(file_name_type, file_name, result_var, flag_var, stepN):
    stepjson = {
        "type": "Read Xlsx File",
        "file_name_type": file_name_type,
        "file_name": file_name,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# check whether a list of sublist of another, the list could be a list of complicated jsons or list of list.
def genStepCheckSublist(main_list_name, sub_list_name, result_var, flag_var, stepN):
    stepjson = {
        "type": "Check Sublist",
        "main_list": main_list_name,
        "sub_list": sub_list_name,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepCheckAlreadyProcessed(in_list_name, record_dir_name, result_var, flag_var, stepN):
    stepjson = {
        "type": "Check Already Processed",
        "in_list": in_list_name,
        "record_dir": record_dir_name,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepReqHumanInLoop(qvar, img_var, type_var, time_var, retry_var, req_id_var, site_var, site_key_var, expected_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "Request Human In Loop",
        "question": qvar,
        "img_file": img_var,
        "type": type_var,
        "time_limit": time_var,
        "retry_limit": time_var,
        "req_id": req_id_var,
        "web_site": site_var,
        "web_site_ey": site_key_var,
        "expected_after": expected_var,
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepKillProcesses(process_name, flag_var, stepN):
    stepjson = {
        "type": "Kill Processes",
        "process_name": process_name,
        "flag": flag_var
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepExternalHook(file_name_type, file_path, file_name, params, result_var, flag_var, stepN):
    stepjson = {
        "type": "External Hook",
        "file_name_type": file_name_type,
        "file_path": file_path,
        "file_name": file_name,
        "params": params,  # Optional dictionary of parameters for the external script
        "result": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepCreateRequestsSession(session_var, flag_var, stepN):
    stepjson = {
        "type": "Create Requests Session",
        "session_var": session_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




def genStepECBScreenBotCandidates(cjs_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Screen Bot Candidates",
        "cjs_var": cjs_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepECBCreateBots(bjs_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Create Bots",
        "bjs_var": bjs_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBUpdateBots(bjs_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Update Bots",
        "bjs_var": bjs_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBDeleteBots(bids_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Delete Bots",
        "bids_var": bids_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBCreateMissions(mjs_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Create Missions",
        "mjs_var": mjs_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBUpdateMissions(mjs_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Update Missions",
        "mjs_var": mjs_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBDeleteMissions(mids_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Delete Missions",
        "mids_var": mids_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBFetchDailySchedule(ts_name_var, force_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Fetch Daily Schedule",
        "ts_name_var": ts_name_var,
        "force_var": force_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBDispatchTroops(schedule_var, result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Dispatch Troops",
        "schedule_var": schedule_var,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepECBCollectBotProfiles(result_var, flag_var, stepN):
    stepjson = {
        "type": "ECB Collect Bot Profiles",
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepLogCrossNetwork(var_type, msg, result_var, flag_var, stepN):
    stepjson = {
        "type": "Log Cross Network",
        "var_type": var_type,
        "msg": msg,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepLog(var_type, msg, result_var, flag_var, stepN):
    stepjson = {
        "type": "Log",
        "var_type": var_type,
        "msg": msg,
        "result_var": result_var,
        "flag": flag_var
    }
    return ((stepN + STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genException():
    psk_words = ""
    this_step, step_words = genStepExceptionHandler("", "", 8000000)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEndException("", "", this_step)
    psk_words = psk_words + step_words
    return this_step, psk_words


def get_top_visible_window(win_title_keyword):
    if sys.platform == 'win32':
        names = []
        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                n = win32gui.GetWindowText(hwnd)
                # logger.info("windows: "+str(n))
                if n:
                    names.append(n)

        win32gui.EnumWindows(winEnumHandler, None)

        logger.info("TOP5 WINDOWS:"+",".join(names[0:5]))
        effective_names = [nm for nm in names if "dummy" not in nm and "Remote Desktop" not in nm]
        found = False
        if win_title_keyword:
            for wi, wn in enumerate(effective_names):
                if win_title_keyword in wn:
                    win_title = effective_names[wi]
                    window_handle = win32gui.FindWindow(None, effective_names[wi])
                    win_rect = win32gui.GetWindowRect(window_handle)
                    logger.info("FOUND TOP target window: " + win_title + " rect: " + json.dumps(win_rect))
                    found = True
                    break

        if win_title_keyword == "" or not found:
            # set to default top window
            win_title = effective_names[0]
            window_handle = win32gui.FindWindow(None, effective_names[0])
            win_rect = win32gui.GetWindowRect(window_handle)
            logger.info("default top window: " + names[0] + " rect: " + json.dumps(win_rect))

        # Convert from (left, top, right, bottom) to (left, top, width, height) for pyautogui
        # GetWindowRect returns (left, top, right, bottom) but pyautogui.screenshot needs (left, top, width, height)
        win_rect_converted = [win_rect[0], win_rect[1], win_rect[2] - win_rect[0], win_rect[3] - win_rect[1]]
        logger.info(f"Converted win_rect from {win_rect} to {win_rect_converted} (left, top, width, height)")
        
        return win_title, win_rect_converted
    elif sys.platform == 'darwin':
        # 获取当前激活的应用
        active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        active_app_name = active_app.localizedName()
        window_rect = []
        
        logger.info(f"Looking for window with keyword: '{win_title_keyword}', active app: '{active_app_name}'")

        # 获取所有可见窗口的列表
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        
        # 调试：列出所有窗口
        if not window_list:
            logger.warning("No windows found in window list.")
        else:
            logger.info(f"Found {len(window_list)} windows in total")
            # 列出前几个窗口用于调试
            for i, window in enumerate(window_list[:5]):
                owner = window.get('kCGWindowOwnerName', '')
                name = window.get('kCGWindowName', 'No Title')
                layer = window.get('kCGWindowLayer', 0)
                logger.debug(f"  Window {i}: Owner='{owner}', Name='{name}', Layer={layer}")

        # 查找最上层的窗口
        matched_windows = []
        for window in window_list:
            window_owner_name = window.get('kCGWindowOwnerName', '')
            window_name = window.get('kCGWindowName', '')
            window_layer = window.get('kCGWindowLayer', 0)
            
            # 只处理普通窗口层级（layer 0）
            if window_layer != 0:
                continue
                
            # 如果指定了关键词，优先匹配窗口标题
            if win_title_keyword and window_name and win_title_keyword in window_name:
                matched_windows.append((window, window_owner_name, window_name, 2))  # 优先级2：关键词匹配
            # 匹配应用名称
            elif window_owner_name == active_app_name:
                # 有窗口标题的优先
                priority = 1 if window_name else 0
                matched_windows.append((window, window_owner_name, window_name, priority))
        
        # 按优先级排序，取第一个
        if matched_windows:
            matched_windows.sort(key=lambda x: x[3], reverse=True)
            window, window_owner_name, window_name, priority = matched_windows[0]
            
            mac_window_rect = window.get('kCGWindowBounds', {'X': 0, 'Y': 0, 'Width': 0, 'Height': 0})
            logger.info(f"Matched Window: {window_owner_name}-{window_name}, Rect: {mac_window_rect}, Priority: {priority}")
            
            # 转换为 (left, top, width, height) 格式（pyautogui.screenshot 需要）
            # 注意：macOS 的坐标系统原点在左上角，与 Windows 一致
            left = mac_window_rect['X']
            top = mac_window_rect['Y']
            width = mac_window_rect['Width']
            height = mac_window_rect['Height']
            
            # 验证窗口尺寸是否有效
            if width > 0 and height > 0:
                window_rect = [round(left), round(top), round(width), round(height)]
                logger.info(f"Window Rect (left, top, width, height): {window_rect}")
            else:
                logger.warning(f"Invalid window size (w={width}, h={height}).")

        # 如果没有找到窗口，使用全屏幕作为默认值
        if not window_rect:
            logger.warning(f"No valid window found for app '{active_app_name}' with keyword '{win_title_keyword}'. Using primary screen as fallback.")
            
            # 获取主屏幕尺寸（支持多屏幕）
            try:
                from AppKit import NSScreen
                main_screen = NSScreen.mainScreen()
                if main_screen:
                    frame = main_screen.frame()
                    # NSScreen 返回的是 (origin, size) 格式
                    window_rect = [0, 0, round(frame.size.width), round(frame.size.height)]
                    logger.info(f"Primary screen size: {window_rect[2]}x{window_rect[3]}")
                else:
                    raise Exception("No main screen found")
            except Exception as e:
                logger.warning("Failed to get NSScreen info; falling back to pyautogui size. Error: %s", e)
                screen_size = lazy.pyautogui.size()
                window_rect = [0, 0, screen_size[0], screen_size[1]]

        return active_app_name, window_rect

def list_windows():
    if sys.platform == 'win32':
        names = []
        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                n = win32gui.GetWindowText(hwnd)
                # logger.info("windows: "+str(n))
                if n:
                    names.append(n)

        win32gui.EnumWindows(winEnumHandler, None)

        # logger.info(",".join(names))
        effective_names = [nm for nm in names if "dummy" not in nm]
        logger.debug("list of windows: %s", effective_names)

        return effective_names

    elif sys.platform == 'darwin':
        # 获取所有可见窗口的列表
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        
        names = []
        seen = set()  # 避免重复
        
        for window in window_list:
            window_owner_name = window.get('kCGWindowOwnerName', '')
            window_name = window.get('kCGWindowName', '')
            window_layer = window.get('kCGWindowLayer', 0)
            
            # 只处理普通窗口层级（layer 0）
            if window_layer != 0:
                continue
            
            # 构建完整的窗口标识
            if window_name:
                full_name = f"{window_owner_name} - {window_name}"
            else:
                full_name = window_owner_name
            
            if full_name and full_name not in seen:
                names.append(full_name)
                seen.add(full_name)
        
        logger.debug("list of windows: %s", names)
        return names


def captureScreen(win_title_keyword, subArea=None):
    global screen_loc
    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BX: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    if win_title_keyword:
        window_name, window_rect = get_top_visible_window(win_title_keyword)
    else:
        logger.info("capture default top window")
        window_name, window_rect = get_top_visible_window("")
    
    # Validate window_rect before using it
    if not window_rect or len(window_rect) < 4:
        logger.error(f"ERROR: Invalid window_rect: {window_rect}, using full screen as fallback")
        screen_size = lazy.pyautogui.size()
        window_rect = [0, 0, screen_size[0], screen_size[1]]
    
    # now we have obtained the top window, take a screen shot , region is a 4-tuple of  left, top, width, and height.
    im0 = lazy.pyautogui.screenshot(region=(window_rect[0], window_rect[1], window_rect[2], window_rect[3]))

    if subArea:
        subimage = im0.crop(subArea)
    else:
        subimage = im0

    # Convert the PIL Image to bytes (in memory, no disk write)
    image_io = io.BytesIO()
    subimage.save(image_io, format="PNG")  # Convert image to PNG format
    image_bytes = image_io.getvalue()

    screen_loc = (window_rect[0], window_rect[1])
    return subimage, image_bytes, screen_loc


def saveImageToFile(img, sfile, fformat):
    if sfile:
        if not os.path.exists(os.path.dirname(sfile)):
            os.makedirs(os.path.dirname(sfile))

        img.save(sfile)
    else:
        logger.warning("File name not specified; skipping image save.")


# win_title_keyword == "" means capture the entire screen
def captureScreenToFile(win_title_keyword, sfile, subarea=None, fformat='png'):
    subimage, image_bytes, window_rect = captureScreen(win_title_keyword, subarea)
    saveImageToFile(subimage, sfile, fformat)

    return subimage, image_bytes, window_rect

def read_screen(win_title_keyword, site_page, page_sect, page_theme, layout, mission, sk_settings, sfile, options, factors):
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()

    screen_img, img_bytes, window_rect = captureScreenToFile(win_title_keyword, sfile)

    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BXX: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    #upload screen to S3
    upload_file(settings["session"], sfile, settings["token"],  mainwin.getWanApiEndpoint(), "screen")

    m_skill_names = [sk_settings["skname"]]
    m_psk_names = [sk_settings["skfname"]]
    csk_name = sk_settings["skfname"].replace("psk", "csk")
    csk_dir = os.path.dirname(csk_name)
    csk_file = os.path.basename(csk_name)
    local_csk_name = csk_dir + "/" + sk_settings["display_resolution"] + "/" + csk_file
    m_csk_names = [local_csk_name]

    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1C: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    # request an analysis of the uploaded screen
    # some example options usage:
    # Note: options is a global variable name that actually contains the options json string as shown below:
    # "options": "{\"info\": [{\"info_name\": \"label_row\", \"info_type\": \"lines 1\", \"template\": \"2\", \"ref_method\": \"1\", \"refs\": [{\"dir\": \"right inline\", \"ref\": \"entries\", \"offset\": 0, \"offset_unit\": \"box\"}]}]}",
    # basically let a user to modify csk file by appending some user defined way to extract certain information element.

    request = [{
        "mid": mission.getMid(),
        "bid": mission.getBid(),
        "os": sk_settings["platform"],
        "app": sk_settings["app"],
        "domain": sk_settings["site"],
        "page": site_page,
        "layout": layout,
        "skill": m_skill_names[0],
        "psk": m_psk_names[0].replace("\\", "\\\\"),
        "csk": m_csk_names[0].replace("\\", "\\\\"),
        "lastMove": page_sect,
        "options": "",
        "theme": page_theme,
        "imageFile": sfile.replace("\\", "\\\\"),
        "factor": factors
    }]

    if options != "":
        if isinstance(symTab[options], str):
            request[0]["options"] = symTab[options]

        elif isinstance(symTab[options], dict):
            # window_rect is now (left, top, width, height)
            full_width = window_rect[2]
            full_height = window_rect[3]
            if "txt_attention_area" in symTab[options]:
                full_width = window_rect[2]
                full_height = window_rect[3]
                symTab[options]["txt_attention_area"] = [ int(symTab[options]["txt_attention_area"][0]*full_width),
                                                      int(symTab[options]["txt_attention_area"][1]*full_height),
                                                      int(symTab[options]["txt_attention_area"][2]*full_width),
                                                      int(symTab[options]["txt_attention_area"][3]*full_height) ]

            if "icon_attention_area" in symTab[options]:
                full_width = window_rect[2]
                full_height = window_rect[3]
                symTab[options]["icon_attention_area"] = [ int(symTab[options]["icon_attention_area"][0]*full_width),
                                                      int(symTab[options]["icon_attention_area"][1]*full_height),
                                                      int(symTab[options]["icon_attention_area"][2]*full_width),
                                                      int(symTab[options]["icon_attention_area"][3]*full_height) ]


            if "display_resolution" not in symTab[options]:
                symTab[options]["display_resolution"] = sk_settings["display_resolution"]

            request[0]["options"] = json.dumps(symTab[options]).replace('"', '\\"')
    else:
        # txt_attention_area is a list of 4 numbers: left, top, right, bottom which defines the area to pay extra attention on the cloud side.
        # attention_targets is a list of text strings to find in the attention area. this whole attention scheme is about using more
        # robust image to text algorithms on the cloud side to get a better reading of the results. The downside is the image process time
        # is long, so limiting only certain area of the image helps keep speed in tact. Usually we home in on right half of the screen.
        # or center half of the screen.
        # window_rect is now (left, top, width, height)
        half_width = int(window_rect[2] / 2)
        half_height = int(window_rect[3] / 2)
        full_width = window_rect[2]
        full_height = window_rect[3]
        # request[0]["options"]["txt_attention_area"] = [half_width, 0, full_width, full_height]
        # request[0]["options"]["attention_targets"] = []
        request[0]["options"] = json.dumps({"display_resolution": sk_settings["display_resolution"], "txt_attention_area": [half_width, 0, full_width, full_height], "attention_targets": ["OK"]}).replace('"', '\\"')

    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1D: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    result = req_cloud_read_screen(settings["session"], request, settings["token"], mainwin.getWanApiEndpoint())
    # logger.info("result::: "+json.dumps(result))
    jresult = json.loads(result['body'])
    # logger.info("cloud result data: "+json.dumps(jresult["data"]))
    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1E: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    if "errors" in jresult:
        screen_error = True
        logger.error("ERROR Type: "+json.dumps(jresult["errors"][0]["errorType"])+"ERROR Info: "+json.dumps(jresult["errors"][0]["errorInfo"]))
        return []
    else:
        # logger.info("cloud result data body: "+json.dumps(result["body"]))
        jbody = json.loads(result["body"])

        # global var "last_screen" always contains information extracted from the last screen shot.
        if len(jbody["data"]) > 0:
            symTab["last_screen"] = jbody["data"]
            return jbody["data"]
        else:
            symTab["last_screen"] = []
            return []

# win_title_keyword == "" means capture the entire screen
async def readRandomWindow8(mission, win_title_keyword, log_user, session,  token):
    dtnow = datetime.now()
    date_word = dtnow.strftime("%Y%m%d")
    dt_string = str(int(dtnow.timestamp()))
    logger.info("date string:" + dt_string)
    
    fdir = path_manager.get_log_path(log_user, date_word, "b0m0/any_any_any_any/skills/any/images")
    image_file = os.path.join(fdir, f"scrn_{dt_string}.png")

    # Ensure directory exists
    path_manager.ensure_directory_exists(image_file)

    screen_img, img_bytes, window_rect = captureScreenToFile(win_title_keyword, image_file)
    # "imageFile": "C:/Users/***/PycharmProjects/ecbot/resource/runlogs/20240328/b0m0/any_any_any_any/skills/any/images/*.png"
    # shutil.copy(source_file, image_file)
    return await cloudAnalyzeRandomImage8(mission, screen_img, image_file, screen_img, session, token)

async def readScreen8(win_title_keyword, site_page, page_sect, page_theme, layout, mission, sk_settings, sfile, options, factors):
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()
    screen_img, img_bytes, window_rect = captureScreenToFile(win_title_keyword, sfile)

    session = settings["session"]
    token = settings["token"]
    mid = mission.getMid()
    bid = mission.getBid()
    image_file = sfile

    result = await cloudAnalyzeImage8(image_file, screen_img, img_bytes, site_page, page_sect, page_theme, layout, mid, bid, sk_settings, options, factors, session, token, mission)
    return result


#image_file *.png must be put in the following diretory
# "imageFile": "C:/Users/***/PycharmProjects/ecbot/resource/runlogs/20240328/b0m0/any_any_any_any/skills/any/images/*.png"
async def cloudAnalyzeRandomImage8(mission, screen_image, image_file, image_bytes, session, token):
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()
    sk_settings = {
        "platform": "any",
        "app": "any",
        "site": "any",
        "skname": "any",
        "skfname": "resource/skills/public/any_any_any_any/any.psk",
        "display_resolution": mainwin.config_manager.general_settings.display_resolution,
        "wan_api_key": mainwin.config_manager.general_settings.ocr_api_key
    }
    logger.debug("Skill settings prepared for random image analysis: %s", sk_settings)
    return await cloudAnalyzeImage8(image_file, screen_image, image_bytes,"any", "any", "", "", 0, 0, sk_settings, "", "{}", session, token, mission)

async def cloudAnalyzeImage8(img_file, screen_image, image_bytes, site_page, page_sect, page_theme, layout, mid, bid, sk_settings, options, factors, session, token, mission):

    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BXXX: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    mwin = mission.get_main_win()
    img_engine = mwin.getImageEngine()
    if img_engine == "lan":
        img_endpoint = mwin.getLanOCREndpoint()
        logger.info("Using LAN OCR endpoint: %s", img_endpoint)
    else:
        img_endpoint = mwin.getWanImageEndpoint()

    #upload screen to S3
    if img_engine == "wan":
        await upload_file8(session, img_file, token, mwin.getWanApiEndpoint(),"screen")

    full_width, full_height = screen_image.size

    m_skill_names = [sk_settings["skname"]]
    m_psk_names = [sk_settings["skfname"]]
    csk_name = sk_settings["skfname"].replace("psk", "csk")
    m_csk_names = [csk_name]

    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1C: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    # request an analysis of the uploaded screen
    # some example options usage:
    # Note: options is a global variable name that actually contains the options json string as shown below:
    # "options": "{\"info\": [{\"info_name\": \"label_row\", \"info_type\": \"lines 1\", \"template\": \"2\", \"ref_method\": \"1\", \"refs\": [{\"dir\": \"right inline\", \"ref\": \"entries\", \"offset\": 0, \"offset_unit\": \"box\"}]}]}",
    # basically let a user to modify csk file by appending some user defined way to extract certain information element.

    request = [{
        "mid": mid,
        "bid": bid,
        "os": sk_settings["platform"],
        "app": sk_settings["app"],
        "domain": sk_settings["site"],
        "page": site_page,
        "layout": layout,
        "skill": m_skill_names[0],
        "psk": m_psk_names[0].replace("\\", "\\\\"),
        "csk": m_csk_names[0].replace("\\", "\\\\"),
        "lastMove": page_sect,
        "options": "",
        "theme": page_theme,
        "imageFile": img_file.replace("\\", "\\\\"),
        "factor": factors
    }]

    if options != "":
        if isinstance(symTab[options], str):
            request[0]["options"] = symTab[options]
        elif isinstance(symTab[options], dict):
            if "txt_attention_area" in symTab[options]:
                symTab[options]["txt_attention_area"] = [ int(symTab[options]["txt_attention_area"][0]*full_width),
                                                      int(symTab[options]["txt_attention_area"][1]*full_height),
                                                      int(symTab[options]["txt_attention_area"][2]*full_width),
                                                      int(symTab[options]["txt_attention_area"][3]*full_height) ]

            if "icon_attention_area" in symTab[options]:
                symTab[options]["icon_attention_area"] = [ int(symTab[options]["icon_attention_area"][0]*full_width),
                                                      int(symTab[options]["icon_attention_area"][1]*full_height),
                                                      int(symTab[options]["icon_attention_area"][2]*full_width),
                                                      int(symTab[options]["icon_attention_area"][3]*full_height) ]


            if "display_resolution" not in symTab[options]:
                symTab[options]["display_resolution"] = sk_settings["display_resolution"]

            request[0]["options"] = json.dumps(symTab[options]).replace('"', '\\"')
    else:
        # txt_attention_area is a list of 4 numbers: left, top, right, bottom which defines the area to pay extra attention on the cloud side.
        # attention_targets is a list of text strings to find in the attention area. this whole attention scheme is about using more
        # robust image to text algorithms on the cloud side to get a better reading of the results. The downside is the image process time
        # is long, so limiting only certain area of the image helps keep speed in tact. Usually we home in on right half of the screen.
        # or center half of the screen.
        half_width = int(full_width/2)
        half_height = int((full_height)/2)
        request[0]["options"] = json.dumps({"display_resolution": sk_settings["display_resolution"], "txt_attention_area": [half_width, 0, full_width, full_height], "attention_targets": ["OK"]}).replace('"', '\\"')

    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1D: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])


    local_info = {
        "user": mwin.getUser(),
        "host_name": mwin.getHostName(),
        "ip": mwin.getIP()
    }

    imgs = [
        {
            "file_name": img_file,
            "bytes": image_bytes
        }
    ]
    api_key = sk_settings["wan_api_key"]
    if api_key:
        logger.debug("OCR API key detected (length=%d).", len(api_key))
    else:
        logger.warning("OCR API key missing or empty.")
    result = await req_read_screen8(session, request, token, api_key, local_info, imgs, img_engine, img_endpoint)
    
    # Check if result contains an error from network failure
    if isinstance(result, dict) and 'error' in result:
        logger.error(f"Network error in OCR request: {result.get('message', 'Unknown error')}")
        logger.error(f"Error details: {result.get('details', 'No details available')}")
        return []
    
    if img_engine == "wan":
        jresult = json.loads(result['body'])
    else:
        jresult = result['body']
    # logger.info("cloud result data: "+json.dumps(jresult["data"]))
    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1E: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    if "errors" in jresult:
        logger.error("ERROR Type: "+json.dumps(jresult["errors"][0]["errorType"])+"ERROR Info: "+json.dumps(jresult["errors"][0]["errorInfo"]))
        return []
    else:
        # logger.info("cloud result data body: "+json.dumps(result["body"]))
        if img_engine == "wan":
            jbody = json.loads(result['body'])
        else:
            jbody = json.loads(result['body']['data']['body'])
            logger.debug("OCR response body: %s", jbody)

        # global var "last_screen" always contains information extracted from the last screen shot.
        if len(jbody["data"]) > 0:
            symTab["last_screen"] = jbody["data"]
            return jbody["data"]
        else:
            symTab["last_screen"] = []
            return []


async def req_read_screen8(session, request, token, api_key, local_info, imgs, engine, api_endpoint):
    if engine == "aws":
        return await req_cloud_read_screen8(session, request, token, api_endpoint)
    elif engine == "lan":
        return await req_lan_read_screen8(session, request, token, api_key, local_info, imgs, api_endpoint)

# actual processing skill routines =========================================================>
def build_current_context():
    global mission_vars
    context = []

    for v in mission_vars:
        context.append({"var_name": v, "var_val": symTab[v]})

    return context

def restore_current_context(context):
    context = []

    # restore variable values.
    for c in context:
        symTab[c["var_name"]] = c["var_val"]



def processHalt(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("Due to supply time lag, this mission is halted till  hours later....")
        #should kick off a timer to wait .
    except:
        ex_stat = "ErrorHalt:" + str(i)

    return (i+1), ex_stat

def processDone(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("Mission accomplished!")
    except:
        ex_stat = "ErrorDone:" + str(i)

    return (i+1), ex_stat

def processWait(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("waiting...... make mouse pointer wonder a little bit!")
        wtime = 1
        if step["time"] == "":
            # calculate wait based on page contents, and reading speed.
            logger.info("waiting for last screen "+str(wtime)+" seconds....")
            # screen = symTab["last_screen"]
        else:
            if isinstance(step["time"], int):
                wtime = step["time"]
            else:
                wtime = symTab[step["time"]]
            logger.info("waiting for "+str(wtime)+" seconds....")

        if isinstance(step["random_max"], int):
            random_max = step["random_max"]
        else:
            random_max = symTab[step["random_max"]]

        if isinstance(step["random_min"], int):
            random_min = step["random_min"]
        else:
            random_min = symTab[step["random_min"]]


        if random_max > 0:
            wtime = random.randrange(random_min, random_max)

        logger.info("actually waiting for "+str(wtime)+" seconds....")
        time.sleep(wtime)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWait:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWait traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processWaitUntil(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("waiting...... make mouse pointer wonder a little bit!")
        wtime = 1

        if type(step["time_out"]) == int:
            wait_in_s = step["time_out"]
        else:
            wait_in_s = symTab[step["time_out"]]

        start_time = time.time()
        while True:
            print("tick....")
            # Check if all boolean variables are True
            if step["events_relation"] == "all":
                if all([symTab[e] for e in step["events"]]):
                    symTab[step["flag"]] = True
                    symTab[step["result"]] = "Completed:Event Received"
                    print(symTab[step["result"]])
                    break

            else:
                if any([symTab[e] for e in step["events"]]):
                    symTab[step["flag"]] = True
                    symTab[step["result"]] = "Completed:Event Received"
                    print(symTab[step["result"]])
                    break

            # Check if timeout has occurred
            elapsed_time = time.time() - start_time
            if elapsed_time > wait_in_s:
                symTab[step["flag"]] = False
                symTab[step["result"]] = "Error:Timed Out"
                print(symTab[step["result"]])
                break

            # Sleep for a short duration before checking again
            time.sleep(0.5)  # Adjust sleep duration as needed

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWaitUntil:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWaitUntil traceback information not available:" + str(e)
        symTab[["flag"]] = False
        symTab[["result"]] = ex_stat
        logger.error(ex_stat)

    return (i + 1), ex_stat


async def processWaitUntil8(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("waiting...... make mouse pointer wonder a little bit!")
        wtime = 1

        if type(step["time_out"]) == int:
            wait_in_s = step["time_out"]
        else:
            wait_in_s = symTab[step["time_out"]]

        start_time = time.time()
        while True:
            print("tick....")
            # Check if all boolean variables are True
            if step["events_relation"] == "all":
                if all([symTab[e] for e in step["events"]]):
                    symTab[step["flag"]] = True
                    symTab[step["result"]] = "Completed:Event Received"
                    print(symTab[step["result"]])
                    break

            else:
                if any([symTab[e] for e in step["events"]]):
                    symTab[step["flag"]] = True
                    symTab[step["result"]] = "Completed:Event Received"
                    print(symTab[step["result"]])
                    break

            # Check if timeout has occurred
            elapsed_time = time.time() - start_time
            if elapsed_time > wait_in_s:
                symTab[step["flag"]] = False
                symTab[step["result"]] = "Error:Timed Out"
                print(symTab[step["result"]])
                break

            # Sleep for a short duration before checking again
            await asyncio.sleep(wtime)  # Adjust sleep duration as needed

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWaitUntil:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWaitUntil traceback information not available:" + str(e)
        symTab[["flag"]] = False
        symTab[["result"]] = ex_stat
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processExtractInfo(step, i, mission, skill):
    # mission_id, session, token, top_win, skill_name, uid
    logger.info("Extracting info...."+"mission["+str(mission.getMid())+"] cuspas: "+mission.getCusPAS() + " skill["+str(skill.getSkid())+"] " + skill.getPskFileName())
    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    mainwin = mission.get_main_win()

    global screen_error

    ex_stat = DEFAULT_RUN_STATUS
    try:
        screen_error = False
        dtnow = datetime.now()

        if step["page_data_info"]:
            page_layout = symTab[step["page_data_info"]]["products"]["layout"]
        else:
            page_layout = ""

        logger.info("page layout is: ["+page_layout+"]")

        date_word = dtnow.strftime("%Y%m%d")
        dt_string = str(int(dtnow.timestamp()))
        logger.info("date string:"+dt_string)

        if skill.getPrivacy() == "public":
            ppword = skill.getPrivacy()
        else:
            ppword = mission.main_win_settings["uid"]

        date_word = dtnow.strftime("%Y%m%d")
        dt_string = str(int(dtnow.timestamp()))
        logger.info("date string:"+dt_string)
        sfile = "C:/Users/songc/PycharmProjects/testdata/"
        #sfile = sfile + settings["uid"] + "/win/adspower/"
        #sfile = sfile + "scrn" + settings["uid"] + "_" + dt_string + ".png"
        if skill.getPrivacy() == "public":
            ppword = skill.getPrivacy()
        else:
            ppword = mission.main_win_settings["uid"]

        logger.info("mission["+str(mission.getMid())+"] cuspas: "+mission.getCusPAS()+"step settings:"+json.dumps(step["settings"]))

        if type(step["settings"]) == str:
            step_settings = symTab[step["settings"]]
            # logger.info("SETTINGS FROM STRING...."+json.dumps(step_settings))
        else:
            step_settings = step["settings"]

        # logger.info("STEP SETTINGS"+json.dumps(step_settings))
        platform = step_settings["platform"]
        app = step_settings["app"]
        site = step_settings["site"]
        page = step_settings["page"]
        machine_name = step_settings["machine_name"]
        if step_settings["root_path"][len(step_settings["root_path"])-1]=="/":
            step_settings["root_path"] = step_settings["root_path"][:len(step_settings["root_path"])-1]

        fdir = ecb_data_homepath + f"/{mainwin.log_user}/runlogs/{mainwin.log_user}/"
        fdir = fdir + date_word + "/"

        fdir = fdir + "b" + str(step_settings["botid"]) + "m" + str(step_settings["mid"]) + "/"
        # fdir = fdir + ppword + "/"
        fdir = fdir + platform + "_" + app + "_" + site + "_" + page + "/skills/"
        fdir = fdir + step_settings["skname"] + "/images/"
        sfile = fdir + "scrn" + mission.main_win_settings["uid"] + "_" + dt_string + ".png"
        logger.info("sfile: "+sfile)
        found_skill = next((x for x in mainwin.skills if x.getName() == step_settings["skname"]), None)
        sk_name = platform + "_" + app + "_" + site + "_" + step_settings["skname"]
        logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1A: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
        icon_names = get_csk_icon_names(found_skill, step["page"], step["section"])
        factors = findAndFormIconScaleFactors(machine_name, sk_name, step["page"], step["section"], icon_names)

        result = read_screen(step['win_title_kw'], step["page"], step["section"], step["theme"], page_layout, mission, step_settings, sfile, step["options"], factors)
        symTab[step["data_sink"]] = result
        logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp2: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
        log6(">>>>>>>>>>>>>>>>>>>>>screen read time stamp2: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], "wan_log", mainwin, mission, i)

        if len(result) > 0:
            updateIconScalesDict(machine_name, sk_name, mainwin.log_user, step["page"], step["section"], result)

        rd_screen_count = rd_screen_count + 1
        logger.info("rd_screen_count: "+str(rd_screen_count))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractInfo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractInfo traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat


async def processExtractInfo8(step, i, mission, skill):
    # mission_id, session, token, top_win, skill_name, uid
    logger.info("Extracting info...."+"mission["+str(mission.getMid())+"] cuspas: "+mission.getCusPAS() + " skill["+str(skill.getSkid())+"] " + skill.getPskFileName())
    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    mainwin = mission.get_main_win()

    global screen_error

    ex_stat = DEFAULT_RUN_STATUS
    try:
        screen_error = False
        dtnow = datetime.now()

        if step["page_data_info"]:
            page_layout = symTab[step["page_data_info"]]["products"]["layout"]
        else:
            page_layout = ""

        logger.info("page layout is: ["+page_layout+"]")

        date_word = dtnow.strftime("%Y%m%d")
        dt_string = str(int(dtnow.timestamp()))
        logger.info("date string:"+dt_string)

        if skill.getPrivacy() == "public":
            ppword = skill.getPrivacy()
        else:
            ppword = mission.main_win_settings["uid"]

        date_word = dtnow.strftime("%Y%m%d")
        dt_string = str(int(dtnow.timestamp()))
        logger.info("date string:"+dt_string)
        sfile = "C:/Users/songc/PycharmProjects/testdata/"
        #sfile = sfile + settings["uid"] + "/win/adspower/"
        #sfile = sfile + "scrn" + settings["uid"] + "_" + dt_string + ".png"
        if skill.getPrivacy() == "public":
            ppword = skill.getPrivacy()
        else:
            ppword = mission.main_win_settings["uid"]

        logger.info("mission["+str(mission.getMid())+"] cuspas: "+mission.getCusPAS()+"step settings:"+json.dumps(step["settings"]))

        if type(step["settings"]) == str:
            step_settings = symTab[step["settings"]]
            logger.info("SETTINGS FROM STRING...."+json.dumps(step_settings))
        else:
            step_settings = step["settings"]

        # logger.info("STEP SETTINGS"+json.dumps(step_settings))
        platform = step_settings["platform"]
        app = step_settings["app"]
        site = step_settings["site"]
        page = step_settings["page"]
        machine_name = step_settings["machine_name"]
        if step_settings["root_path"][len(step_settings["root_path"])-1]=="/":
            step_settings["root_path"] = step_settings["root_path"][:len(step_settings["root_path"])-1]

        fdir = ecb_data_homepath + f"/{mainwin.log_user}/runlogs/{mainwin.log_user}/"
        fdir = fdir + date_word + "/"

        fdir = fdir + "b" + str(step_settings["botid"]) + "m" + str(step_settings["mid"]) + "/"
        # fdir = fdir + ppword + "/"
        fdir = fdir + platform + "_" + app + "_" + site + "_" + page + "/skills/"
        fdir = fdir + step_settings["skname"] + "/images/"
        sfile = fdir + "scrn" + mission.main_win_settings["uid"] + "_" + dt_string + ".png"
        logger.info("sfile: "+sfile)
        found_skill = next((x for x in mainwin.skills if x.getName() == step_settings["skname"]), None)
        sk_name = platform + "_" + app + "_" + site + "_" + step_settings["skname"]
        logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1A: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
        icon_names = get_csk_icon_names(found_skill, step["page"], step["section"])
        factors = findAndFormIconScaleFactors(machine_name, sk_name, step["page"], step["section"], icon_names)

        result = await readScreen8(step['win_title_kw'], step["page"], step["section"], step["theme"], page_layout, mission, step_settings, sfile, step["options"], factors)
        symTab[step["data_sink"]] = result
        log6(">>>>>>>>>>>>>>>>>>>>>screen read time stamp2: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], "wan_log", mainwin, mission, i)

        if len(result) > 0:
            updateIconScalesDict(machine_name, sk_name, mainwin.log_user, step["page"], step["section"], result)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractInfo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractInfo traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat

def takeScreenShot(win_title_keyword, subArea=None):
    global screen_loc
    logger.info(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BBX: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    if win_title_keyword:
        window_name, window_rect = get_top_visible_window(win_title_keyword)
    else:
        logger.info("capture default top window")
        window_name, window_rect = get_top_visible_window("")
    
    # Validate window_rect before using it
    if not window_rect or len(window_rect) < 4:
        logger.error(f"ERROR: Invalid window_rect: {window_rect}, using full screen as fallback")
        screen_size = lazy.pyautogui.size()
        window_rect = [0, 0, screen_size[0], screen_size[1]]
    
    # now we have obtained the top window, take a screen shot , region is a 4-tuple of  left, top, width, and height.
    im0 = lazy.pyautogui.screenshot(region=(window_rect[0], window_rect[1], window_rect[2], window_rect[3]))

    return im0, window_rect


def findBoundBox(ref_boxes):
    m0 = min([b[0] for b in ref_boxes])
    m1 = min([b[1] for b in ref_boxes])
    m2 = max([b[2] for b in ref_boxes])
    m3 = max([b[3] for b in ref_boxes])
    return [m0, m1, m2, m3]

def findRef(ref_name, img_mark_up):
    found = next((x for x in img_mark_up if ref_name in x["name"]), None)
    return found

# given a list anchor info in img_mark_up, and given area_spec which is list of anchors
# carve out a subimage of the original "img" which is the boundbox formed the
# list of area_spec anchors.
# area_spec will be the same as defined in CSK
# assumes: the boundbox defining anchors are unique on the image
def carveOutImage(img0, area_spec, img_mark_up):
    subimage = img0
    if area_spec:
        if "sub_refs" in area_spec:
            ref_names = [ref["ref"] for ref in area_spec["sub_refs"]]
            refs = []
            for ref_name in ref_names:
                ref = findRef(ref_name, img_mark_up)
                if ref:
                    refs.append(ref[0])
            ref_boxes = [r["loc"] for r in refs]
            print(f"ref boxes: {ref_boxes}")

            if len(ref_boxes) >=2:
                subArea = findBoundBox(ref_boxes)
                if subArea[0] < subArea[2] and subArea[1] < subArea[3]:
                    print(f"Carve out {subArea}")
                    subimage = img0.crop(subArea)

    return subimage

# given a list anchor info in img_mark_up, and given area_spec which is list of anchors
# mask out (smear with all black or all white) a sub-section of the original "img" which
# is the boundbox formed the  list of area_spec anchors.
# area_spec will be the same as defined in CSK
# loc in T, L, B, R
def maskOutImage(img, area_spec, img_mark_up):
    for mask in area_spec["masks"]:
        ref = findRef(mask["ref"], img_mark_up)
        if ref:
            ref = ref[0]
            box_height = ref["loc"][2] - ref["loc"][0]
            box_width = ref["loc"][3] - ref["loc"][1]
            if ref["side"] == "bottom":
                top = ref["loc"][2] + ref["voffset"]*box_height
                bottom = top + ref["height"]*box_height
                left = ref["loc"][0] + ref["hoffset"]*box_width
                right = left + ref["width"] * box_width
            elif ref["side"] == "top":
                bottom = ref["loc"][0] - ref["voffset"] * box_height
                top = bottom - ref["height"] * box_height
                left = ref["loc"][0] + ref["hoffset"] * box_width
                right = left + ref["width"] * box_width
            elif ref["side"] == "left":
                top = ref["loc"][0] + ref["voffset"] * box_height
                bottom = top + ref["height"] * box_height
                right = ref["loc"][1] - ref["hoffset"] * box_width
                left = right - ref["width"] * box_width
            elif ref["side"] == "right":
                top = ref["loc"][0] + ref["voffset"] * box_height
                bottom = top + ref["height"] * box_height
                left = ref["loc"][3] + ref["hoffset"] * box_width
                right = left + ref["width"] * box_width

            print(f"mask left, top, right, bottom: {[left, top, right, bottom]}")
            # Define the area to black out (x1, y1) -> (x2, y2)
            # x1, y1 = 50, 50  # Top-left corner
            # x2, y2 = 200, 200  # Bottom-right corner

            # Make the region black
            img[left:top, right:bottom] = (0, 0, 0)

# "type": "Screen Capture",
# "area": area,
# "format": fformat,
# "img_var": img_var,
# "img_file_var": img_file_var,
# "flag": flag
def processScreenCapture(step, i):
    # mission_id, session, token, top_win, skill_name, uid
    logger.info("Capturing Screen....")

    global screen_error

    ex_stat = DEFAULT_RUN_STATUS
    try:

        img_mark_up = symTab[step["text_var"]]
        area_spec = symTab[step["area"]]
        sfile = symTab[step["img_file_var"]]
        fformat = step["format"]

        screen_img, window_rect = takeScreenShot("")
        img_section = carveOutImage(screen_img, area_spec, img_mark_up)
        maskOutImage(img_section, area_spec, img_mark_up)

        saveImageToFile(img_section, sfile, fformat)

        if step["img_var"]:
            symTab[step["img_var"]] = img_section


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorScreenCapture:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorScreenCapture traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat



def processUploadFiles(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = True
        symTab[step["results"]] = []
        settings = mission.main_win_settings
        mainwin = mission.get_main_win()
        endpoint = mainwin.getWanApiEndpoint()
        if "/" in step["files_var"]:
            sfiles = [step["files_var"]]
        elif type(step["files_var"]) == list:
            sfiles = step["files_var"]
        else:
            sfiles = symTab[step["files_var"]]
            print("gvar is list")
            if type(sfiles) == str:
                print("gvar is string")
                sfiles = [sfiles]

        print("SFILES:", sfiles)
        ftype = step["ftype"]
        for si, sfile in enumerate(sfiles):
            print("uploading....", sfile)
            if type(symTab[step["locs"]]) == list:
                print("tos....", symTab[step["locs"]][si])
                symTab[step["results"]].append(upload_file(settings["session"], sfile, symTab[step["locs"]][si], settings["token"], endpoint, ftype))
            else:
                print("to....", symTab[step["locs"]])
                symTab[step["results"]].append(upload_file(settings["session"], sfile, symTab[step["locs"]], settings["token"], endpoint, ftype))
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorUploadFiles:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorUploadFiles traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i+1), ex_stat



def processDownloadFiles(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = True
        symTab[step["results"]] = []
        mainwin = mission.get_main_win()
        endpoint = mainwin.getWanApiEndpoint()
        dh = ecb_data_homepath + f"/{mainwin.log_user}/"
        settings = mission.main_win_settings
        if "/" in step["files_var"]:
            sfiles = [step["files_var"]]
        elif type(step["files_var"]) == list:
            sfiles = step["files_var"]
        else:
            sfiles = symTab[step["files_var"]]
            if type(sfiles) == str:
                sfiles = [sfiles]

        ftype = step["ftype"]

        for si, sfile in enumerate(sfiles):
            if type(symTab[step["locs"]]) == list:
                symTab[step["results"]].append(download_file(settings["session"], dh, sfile, symTab[step["locs"]][si], settings["token"], endpoint, ftype))
            else:
                symTab[step["results"]].append(download_file(settings["session"], dh, sfile, symTab[step["locs"]], settings["token"], endpoint, ftype))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorDownloadFiles:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorDownloadFiles traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i+1), ex_stat



def processUpdateMissionStatus(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = True
        symTab[step["results"]] = []
        settings = mission.main_win_settings

        session = settings["session"]
        token = settings["token"]

        settings = mission.main_win_settings
        if step["status_var_type"] == "direct":
            status = step["status_var"]
        else:
            status = symTab[step["status_var"]]

        if step["err_var_type"] == "direct":
            error = step["err_var"]
        else:
            error = symTab[step["err_var"]]

        mission.setStatus(status)
        mission.setError(error)
        mission.setIntermediateData(symTab[step["data_var"]])
        mstat = {
            "mid": mission.getMid(),
            "status": status
        }

        mainwin = mission.get_main_win()
        symTab[step["results"]] = send_update_missions_ex_status_to_cloud(session, [mstat], token, mainwin.getWanApiEndpoint())

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorUpdateMissionStatus:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorUpdateMissionStatus traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i+1), ex_stat



# this is function is more or less for Etsy or others...
# needs to accomodate mistakes like this:
# Vincent
# 250 E 14th St, Bloomington, IN 47408
# Apt. 1209 A
# Bloomington, IN 47408
#
# Mason Stachowicz
# 817 E Shaw Ln, East Lansing, MI 48825
# East 666
# EAST LANSING, MI 48825
# or canadian addresses......

def processFillRecipients(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("txts var:"+json.dumps(symTab[step["texts_var"]]))
        for txt_bloc in symTab[step["texts_var"]]:
            fullname = txt_bloc[0].strip()
            city_state_zip = txt_bloc[len(txt_bloc)-1].strip().split(",")
            city = city_state_zip[0].strip()
            state_zip = city_state_zip[1].strip().split()
            state = state_zip[0].strip()
            zip = state_zip[1].strip()
            if len(txt_bloc) == 4:
                street2 = txt_bloc[2].strip()
            else:
                street2 = ""

            street1 = txt_bloc[1].split(",")[0].strip()

            # find a match of name in the orders data structure.
            match = next((x for x in symTab[step["orders_var"]] if x.getRecipientName() == fullname and x.getRecipientCity() == city), None)
            if match:
                match.setRecipientAddrState(street1)
                match.setRecipientAddrState(street2)
                match.setRecipientAddrState(zip)
            else:
                # need to add a recipient
                logger.error("ERROR, how could the name be not found?")

            # once found, update the relavant field. such as
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorFillRecipients:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorFillRecipients traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat

# text input, type only, the click onto the correction place to type should happen before this.
# action: action to perform here - simply text input
#  text: txt to be input.
#  speed: type speed.
#  key_after: key to hit after textinput. (could be "", "enter",
#  wait_after: number of seconds to wait after key_after action.
def processTextInput(step, i, mission):
    global page_stack
    global current_context
    mainwin = mission.get_main_win()
    ex_stat = DEFAULT_RUN_STATUS
    try:

        if step["txt_ref_type"] == "direct":
            txt_to_be_input = step["text"]
            logger.info("typing....." + txt_to_be_input)
        else:
            logger.info("assign expression:"+"txt_to_be_input = "+step["text"])
            exec("global input_texts\ninput_texts = "+step["text"])
            txt_to_be_input = input_texts
            logger.info("after assignment:"+json.dumps(txt_to_be_input))
            exec("global txt_to_be_input\ntxt_to_be_input = "+step["text"])


        time.sleep(2)
        # pyautogui.click()
        if step["txt_type"] == "var" and step["txt_ref_type"] == "direct":
            logger.info("about to TYPE in:"+symTab[txt_to_be_input])
            pyautogui.write(symTab[txt_to_be_input], interval=0.25)
            log_text = symTab[txt_to_be_input]
        else:
            if step["txt_type"] == "list":
                logger.info("direct type in:"+txt_to_be_input[0])
                pyautogui.write(txt_to_be_input[0], interval=step["speed"])
                log_text = txt_to_be_input[0]
            else:
                pyautogui.write(txt_to_be_input, interval=step["speed"])
                log_text = txt_to_be_input

        log6(f"Keyboard typing......{log_text}", "wan_log", mainwin, mission, i)

        time.sleep(1)
        if step['key_after'] != "":
            logger.info("after typing, pressing:"+step['key_after']+"then wait for:"+str(step['wait_after']))
            pyautogui.press(step['key_after'])
            time.sleep(1)
            pyautogui.press("enter")
            time.sleep(step['wait_after'])


        # now save for roll back if ever needed.
        # first remove the previously save rollback point, but leave up to 3 rollback points
        while len(page_stack) > 3:
            page_stack.pop()
        # now save the current juncture.
        current_context = build_current_context()
        page_stack.append({"pc": i, "context": current_context})


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorTextInput:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorTextInput traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat


# calculate an object’s row col position in a virtual table, given the object's position, origin, table cell width, table cell height.
def calc_loc(box, cell_w, cell_h, origin):
    ci = round((box[0] - origin[0])/cell_w)
    ri = round((box[1] - origin[1])/cell_h)

    loc =[ci, ri]
    # logger.info("location:", loc)
    return loc

# calculate an object’s sequence in a virtual table, given the object's position, origin, table cell width, table cell height, and row width.
def calc_seq(box, cell_w, cell_h, origin, ncols):
    loc = calc_loc(box, cell_w, cell_h, origin)
    seq = loc[1] * ncols + loc[0]
    logger.info("sequence:"+str(seq))
    return seq

# sort a list of boxes spatially, if we already know they're placed in a tabular fasion. (i.e. rows and cols, roughtly)
# will automatically calculate # of rows and cols, and cell width, height, and then sort the boxes in rows and cols.
# and calcualte each box's row and col index.
def convert_to_2d_array(object_list):
    if not object_list:
        return []

    # Sort the objects by their y-coordinates (rows).
    sorted_objects = sorted(object_list, key=lambda obj: obj[1])

    xs = [o[0] for o in object_list]
    xs.sort()
    logger.info("xs:"+json.dumps(xs))

    ys = [o[1] for o in object_list]
    ys.sort()
    logger.info("ys:"+json.dumps(ys))

    xgroups = group_1D(xs)

    ygroups = group_1D(ys)

    xgrp_avgs = [sum(grp)/len(grp) for grp in xgroups]
    xgaps = []
    for x, y in zip(xgrp_avgs[0::], xgrp_avgs[1::]):
        xgaps.append(y - x)

    logger.info("xgrp_avgs:"+json.dumps(xgrp_avgs)+"xgaps:"+json.dumps(xgaps))

    ygrp_avgs = [sum(grp)/len(grp) for grp in ygroups]
    ygaps = []
    for x, y in zip(ygrp_avgs[0::], ygrp_avgs[1::]):
        ygaps.append(y - x)

    xgap = min(xgaps)
    ygap = min(ygaps)

    logger.info("ygrp_avgs:"+json.dumps(ygrp_avgs)+"ygaps:"+json.dumps(ygaps))


    rows = round((ygrp_avgs[len(ygrp_avgs)-1] - ygrp_avgs[0])/ygap) + 1
    cols = round((xgrp_avgs[len(xgrp_avgs)-1] - xgrp_avgs[0])/xgap) + 1

    logger.info("cols:"+json.dumps(cols))
    logger.info("rows:"+json.dumps(rows))

    # Find calculate the origial list member's table index (col., row) (i.e. (x, y) coordinate)
    coords = [calc_loc(o, xgap, ygap, [xgrp_avgs[0], ygrp_avgs[0]]) for o in object_list]
    logger.info("coords:"+json.dumps(coords))

    xy_sorted = sorted(object_list, key=lambda x: calc_seq(x, xgap, ygap, [xgrp_avgs[0], ygrp_avgs[0]], cols), reverse=False)
    logger.info("x-y sorted:"+json.dumps(xy_sorted))
    coords = [calc_loc(o, xgap, ygap, [xgrp_avgs[0], ygrp_avgs[0]]) for o in xy_sorted]
    logger.info("coords:"+json.dumps(coords))

    return xy_sorted

# group a 1d list of integers by clusters. with a distanc threshold
def group_1D(int_list, threshold=25):
    if not int_list:
        return []

    int_list.sort()  # Sort the input list in ascending order.
    grouped = [[int_list[0]]]  # Initialize the first group with the first integer.

    for i in range(1, len(int_list)):
        current_int = int_list[i]
        previous_group = grouped[-1]

        if abs(current_int - previous_group[-1]) <= threshold:
            # If the current integer is within the threshold of the previous group,
            # add it to the same group.
            previous_group.append(current_int)
        else:
            # Otherwise, start a new group.
            grouped.append([current_int])

    return grouped

# sd - screen data
# target_name
# template text
# target_type
# nth - which target， if multiple are found
def find_clickable_object(sd, target, template, target_type, nth):
    logger.info("LOOKING FOR:"+json.dumps(target)+"   "+json.dumps(template)+"   "+json.dumps(target_type)+"   "+json.dumps(nth))
    found = {"loc": None}
    if target != "paragraph":           # for anchors and info.
        # reg = re.compile(target+"[0-9]+")
        reg = re.compile(rf"^{target}([0-9]*)$")
        targets = [x for x in sd if (x["name"] == target or reg.match(x["name"].split("!")[0])) and x["type"] == target_type]
    else:
        reg = re.compile(template)
        targets = [x for x in sd if template in x["text"] and x["type"] == target_type and x["name"] == target]
    # grab all instances of the target object.

    logger.info("found targets::"+str(len(targets)))
    objs = []

    # convert possible string to integer
    for o in targets:
        if o["name"] == "paragraph":
            lines = [l for l in o["txt_struct"] if (l["text"] == template or re.search(template, l["text"]))]
            logger.info("found lines::"+str(len(lines)))
            if len(lines) > 0:
                for li, l in enumerate(lines):
                    pat_words = template.strip().split()
                    lreg = re.compile(pat_words[0])
                    logger.info("checking line:"+json.dumps(l)+json.dumps(pat_words))
                    start_word = next((x for x in l["words"] if re.search(pat_words[0], x["text"])), None)
                    logger.info("start_word:"+json.dumps(start_word))
                    if start_word:
                        if len(pat_words) > 1:
                            lreg = re.compile(pat_words[len(pat_words)-1])
                            end_word = next((x for x in l["words"] if x["text"] == pat_words[len(pat_words)-1] or lreg.match(x["text"])), None)
                            logger.info("multi word end_word:"+json.dumps(end_word))
                        else:
                            end_word = start_word
                            logger.info("single word")

                        objs.append({"loc": [int(start_word["box"][1]), int(start_word["box"][0]), int(end_word["box"][3]), int(end_word["box"][2])]})
                        logger.info("objs:"+json.dumps(objs))
        else:
            logger.info("non paragraph:"+json.dumps(o))
            o["loc"] = [int(o["loc"][0]), int(o["loc"][1]), int(o["loc"][2]), int(o["loc"][3])]
            objs.append({"loc": o["loc"]})

    logger.info("objs:"+json.dumps(objs))
    if len(objs) > 1:
        # need to organized found objects into rows and cols, then access the nth object.
        xsorted = sorted(objs, key=lambda x: x["loc"][0], reverse=False)
        ysorted = sorted(objs, key=lambda x: x["loc"][1], reverse=False)
        cell_width = int(sum((c["loc"][2] - c["loc"][0]) for c in xsorted) / len(xsorted))
        cell_height = int(sum((c["loc"][3]-c["loc"][1]) for c in ysorted)/len(ysorted))
        #now calculate the row grid and column grid size
        ncols = 1+math.floor((xsorted[len(xsorted)-1]["loc"][0] - xsorted[0]["loc"][0]) / cell_width)
        nrows = 1+math.floor((ysorted[len(ysorted)-1]["loc"][1] - ysorted[0]["loc"][1]) / cell_height)
        # now place objects into their relavant row and colume position.
        my_array = lazy.np.empty([nrows, ncols], dtype=object)
        for ob in ysorted:
            ri = math.floor((ob["loc"][1] - ysorted[0]["loc"][1])/cell_height)
            ci =  math.floor((ob["loc"][0] - xsorted[0]["loc"][0])/cell_width)
            logger.info("Filling in row:"+str(ri)+" col:"+str(ci))
            my_array[ri, ci] = ob

        # now, take out the nth element
        if type(nth) == list:
            if len(nth) == 2:
                if nth[0] >= 0 and nth[1] >= 0:
                    found = my_array[nth[0], nth[1]]
                elif nth[1] >= 0:
                    found = ysorted[nth[1]]
                else:
                    found = xsorted[nth[0]]
            else:
                found = objs[nth[0]]
        elif type(nth) == str:
            # nth is a variable
            if "[" not in nth and "]" not in nth:
                logger.info("nth as a variable name is:"+str(symTab[nth]))
                found = objs[symTab[nth]]
                logger.info("found object:"+json.dumps(found))
        elif type(nth) == int:
            logger.info("nth as an integer is:"+str(nth))
            found = objs[nth]
        # the code is incomplete at the moment....
    elif len(objs) == 1:
        found = objs[0]

    return found["loc"]

def get_clickable_loc(box, off_from, offset, offset_unit):
    logger.info("get_clickable_loc: "+json.dumps(box)+" :: "+json.dumps(off_from)+" :: "+json.dumps(offset)+" :: "+offset_unit)
    center = box_center(box)
    if offset_unit == "box":
        box_length = box[3] - box[1]
        box_height = box[2] - box[0]
    else:
        box_length = 1
        box_height = 1

    if off_from == "left":
        click_loc = (box[1] - int(offset[0]*box_length), center[0]+int(offset[1]*box_height))
    elif off_from == "right":
        click_loc = (box[3] + int(offset[0]*box_length), center[0]+int(offset[1]*box_height))
    elif off_from == "top":
        click_loc = (center[1] + int(offset[0]*box_length), box[0] - int(offset[1]*box_height))
    elif off_from == "bottom":
        click_loc = (center[1] + int(offset[0]*box_length), box[2] + int(offset[1]*box_height))
    else:
        #offset from center case
        logger.info("CENTER: "+json.dumps(center)+"OFFSET:"+json.dumps(offset))
        click_loc = ((center[1] + int(offset[0]*box_length), center[0] + int(offset[1]*box_height)))

    return click_loc


def get_post_move_offset(box, offset, offset_unit):
    logger.info("calc post move offset:"+json.dumps(offset_unit)+" "+json.dumps(box)+" "+json.dumps(offset))
    if offset_unit == "box":
        box_length = box[3] - box[1]
        box_height = box[2] - box[0]
    else:
        box_length = 1
        box_height = 1

    offset = [offset[0]*box_length, offset[1]*box_height]

    return offset


def is_float(string):
    try:
        float(string)
        return True
    except ValueError:
        return False


# use target_name and target_type to find the matching item among the clickables. once found, click on that accordingly.
# "action": action,  # double click, single click, drag and drop?
# "action_args": action_args,  # can be used to specify things like click speed, or mouse hold time, or mouse move speed?
# "screen": screen,  # screen data.
# "target_name": target,  # information name.
# "target_type": target_type,  # anchor or info or shape,
# "nth": nth,  # [0,0] in case of there are multiple occurance of target on the screen, click on which one? [n, m] would be nth from left, mth from top
# "offset_from": offset_from,  # click at a offset from object's bound box side, left/top/right/bottom/center are choices. if left/right, y coordinate is default to be center, if top/bottom, x coordiate default to be center.
# "offset": offset  # offset in x and y direction,
def processMouseClick(step, i, mission):
    global page_stack
    global current_context
    mainwin = mission.get_main_win()
    log6(f"Mouse Clicking .....{step['target_name']}", "wan_log", mainwin, mission, i)
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["target_type"] != "direct" and step["target_type"] != "expr":
            if step["target_type"] == "var name":
                target_name = symTab[step["target_name"]]
            else:
                target_name = step["target_name"]
            sd = symTab[step["screen"]]

            if step["text"] != "":
                if step["text"] in symTab:
                    step["text"] = symTab[step["text"]]
            logger.info("finding: "+step["text"]+" target name: "+target_name+" text to be matched:["+step["text"]+"]")
            # logger.info("from data: "+json.dumps(sd))
            obj_box = find_clickable_object(sd, target_name, step["text"], step["target_type"], step["nth"])
            logger.info("obj_box: "+json.dumps(obj_box))
            if obj_box:
                loc = get_clickable_loc(obj_box, step["offset_from"], step["offset"], step["offset_unit"])
                post_offset = get_post_move_offset(obj_box, step["post_move"], step["offset_unit"])
                post_loc = [loc[0] + post_offset[0], loc[1] + post_offset[1]]
                logger.info("indirect calculated locations:"+json.dumps(loc)+"post_offset:("+str(post_offset[0])+","+str(post_offset[1])+") post_loc:"+json.dumps(post_loc))
            else:
                loc = None
        else:
            # the location is already calculated directly and stored here.
            if step["target_type"] == "direct":
                logger.info("obtain directly..... from a variable which is a box type i.e. [l, t, r, b]")
                box = symTab[step["target_name"]]
                loc = box_center(box)
                post_offset_x = (box[2] - box[0]) * step["post_move"][0]
                post_offset_y = (box[3] - box[1]) * step["post_move"][1]
                post_loc = [loc[0] + post_offset_x, loc[1] + post_offset_y]
            else:
                logger.info("obtain thru expression..... which after evaluate this expression, it should return a box i.e. [l, t, r, b]"+step["target_name"])
                exec("global click_target\nclick_target = " + step["target_name"])
                logger.info("box: "+step["target_name"]+" "+json.dumps(click_target))
                # box = [symTab["target_name"][1], symTab["target_name"][0], symTab["target_name"][3], symTab["target_name"][2]]
                box = [click_target[1], click_target[0], click_target[3], click_target[2]]
                loc = box_center(box)
                post_offset_y = (click_target[2] - click_target[0]) * step["post_move"][1]
                post_offset_x = (click_target[3] - click_target[1]) * step["post_move"][0]
                post_loc = [loc[0] + post_offset_x, loc[1] + post_offset_y ]

            logger.info("direct calculated locations:"+json.dumps(loc)+"post_offset:("+str(post_offset_x)+","+str(post_offset_y)+")"+"post_loc:"+json.dumps(post_loc))

        window_name, window_rect = get_top_visible_window("")
        logger.info("top windows rect:"+json.dumps(window_rect))
        
        # Validate window_rect before using it
        if not window_rect or len(window_rect) < 4:
            logger.error(f"ERROR: Invalid window_rect: {window_rect}, using full screen as fallback")
            screen_size = lazy.pyautogui.size()
            window_rect = [0, 0, screen_size[0], screen_size[1]]

        if loc:
            # loc[0] = int(loc[0]) + window_rect[0]
            loc = (int(loc[0]) + window_rect[0], int(loc[1]) + window_rect[1])
            logger.info("global loc@ "+str(loc[0])+" ,  "+str(loc[1]))

            pyautogui.moveTo(loc[0], loc[1])          # move mouse to this location 0th position is X, 1st position is Y

            time.sleep(step["move_pause"])

            if step["action"] == "Single Click":
                pyautogui.click()
                # pyautogui.click()
            elif step["action"] == "Double Click":
                if is_float(step["action_args"]):
                    pyautogui.click(clicks=2, interval=float(step["action_args"]))
                else:
                    pyautogui.click(clicks=2, interval=0.3)
            elif step["action"] == "Triple Click":
                if is_float(step["action_args"]):
                    pyautogui.click(clicks=3, interval=float(step["action_args"]))
                else:
                    pyautogui.click(clicks=3, interval=0.3)
            elif step["action"] == "Right CLick":
                pyautogui.click(button='right')
            elif step["action"] == "Drag Drop":
                # code drop location is embedded in action_args, the code need to added later to process that....
                pyautogui.dragTo(loc[0], loc[1], duration=2)

            time.sleep(1)
            logger.info("post click moveto :("+str(int(post_loc[0]) + window_rect[0])+","+str(int(post_loc[1]) + window_rect[1])+")")
            pyautogui.moveTo(int(post_loc[0]) + window_rect[0], int(post_loc[1]) + window_rect[1])
            if step["post_wait"] > 0:
                time.sleep(step["post_wait"]-1)

            # now save for roll back if ever needed.
            # first remove the previously save rollback point, but leave up to 3 rollback points
            while len(page_stack) > 3:
                page_stack.pop()
            # now save the current juncture.
            current_context = build_current_context()
            page_stack.append({"pc": i, "context": current_context})


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorMouseClick:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorMouseClick: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def DragDrop(route, speed):
    """
    Perform a drag-and-drop mouse action along a series of points with varying speeds.

    :param route: List of (x, y) tuples representing the path to follow.
    :param speed: List of integers representing milliseconds to move between consecutive points.
    """
    if len(route) < 2:
        raise ValueError("Route must contain at least two points.")
    if len(speed) != len(route) - 1:
        raise ValueError("Speed list must have exactly N-1 elements, where N is the number of route points.")

    # Move to the starting point
    start_point = route[0]
    pyautogui.moveTo(start_point[0], start_point[1])
    pyautogui.mouseDown()  # Simulate mouse press

    # Drag through the route
    for i in range(1, len(route)):
        x, y = route[i]
        duration = speed[i - 1] / 1000.0  # Convert speed to seconds
        pyautogui.moveTo(x, y, duration=duration)

    pyautogui.mouseUp()  # Release the mouse button at the end


def processMouseDragDrop(step, i, mission):
    global page_stack
    global current_context
    mainwin = mission.get_main_win()
    logger.info("Mouse Drag Drop .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:

        DragDrop(symTab[step["route_var"]], symTab[step["speed_var"]])

        if step["post_wait"] > 0:
            time.sleep(step["post_wait"]-1)

        # now save for roll back if ever needed.
        # first remove the previously save rollback point, but leave up to 3 rollback points
        while len(page_stack) > 3:
            page_stack.pop()
        # now save the current juncture.
        current_context = build_current_context()
        page_stack.append({"pc": i, "context": current_context})


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorMouseDragDrop:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorMouseDragDrop: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


# max 4 combo key stroke
def processKeyInput(step, i, mission):
    global page_stack
    global current_context
    mainwin = mission.get_main_win()
    ex_stat = DEFAULT_RUN_STATUS
    try:
        keys = step["action_value"].split(',')
        log6("Keyboard Action..... hot keys"+json.dumps(keys), "wan_log", mainwin, mission, i)
        if len(keys) == 4:
            pyautogui.hotkey(keys[0], keys[1], keys[2], keys[3])
        elif len(keys) == 3:
            pyautogui.hotkey(keys[0], keys[1], keys[2])
        if len(keys) == 2:
            pyautogui.hotkey(keys[0], keys[1])
        if len(keys) == 1:
            pyautogui.press(keys[0])

        # now save for roll back if ever needed.
        # first remove the previously save rollback point, but leave up to 3 rollback points
        while len(page_stack) > 3:
            page_stack.pop()
        # now save the current juncture.
        current_context = build_current_context()
        page_stack.append({"pc": i, "context": current_context})

        # wait after key action.
        time.sleep(step["wait_after"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorKeyInput:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorKeyInput: traceback information not available:" + str(e)(ex_stat)

    return (i + 1), ex_stat

# cloud returned screen information data struture:
# {"id": 0, "data": json_fullinfo}
# ... = [allFoundText + allicons + allTextAnchors +allinfo]

#each info element is:
# { "name": "", "text": "", "loc" : [top, left, bottom, right], "type" : "anchor icon/h line/v line/polygon/anchor text/info/info block/full page/word stats" }
# fullinfo: [...., fullpage, word_stats]

# compute distance between 2 points
# p1,p2 in tuple format (x, y)
def p2p_distance(p1, p2):
    dist = int(math.sqrt((p1[0]-p2[0])*(p1[0]-p2[0]) + (p1[1]-p2[1])*(p1[1]-p2[1])))
    # logger.info("p2p distance: "+json.dumps(dist))
    return dist

# loc: (top, left, bottom, right)
def loc_center(box):
    return (box[1]+int((box[3]-box[1])/2), box[0]+int((box[2]-box[0])/2))

# box: (left, top, right, bottom)
def box_center(box):
    return (box[0]+int((box[2]-box[0])/2), box[1]+int((box[3]-box[1])/2))

def processMouseScroll(step, i, mission):
    screen_data = symTab[step["screen"]]
    mainwin = mission.get_main_win()
    # logger.info("screen_data: "+json.dumps(screen_data))
    ex_stat = DEFAULT_RUN_STATUS
    try:
        screen_vsize = screen_data[len(screen_data) - 2]['loc'][2]

        if step["unit"] == "screen":
            logger.info("SCREEN SIZE: "+json.dumps(screen_data[len(screen_data) - 2]['loc'])+"resolution var: "+json.dumps(step["resolution"])+" val: "+json.dumps(symTab[step["resolution"]]))
            if type(step["amount"]) is str:
                scroll_amount = int(((symTab[step["amount"]]/100)*screen_vsize)/symTab[step["resolution"]])
            else:
                scroll_amount = int(((step["amount"]/100)*screen_vsize)/symTab[step["resolution"]])
                logger.info("screen size based scroll amount:"+str(scroll_amount))
        elif step["unit"] == "raw":
            if type(step["amount"]) is str:
                scroll_amount = symTab[step["amount"]]
            else:
                scroll_amount = step["amount"]
        else:
            logger.error("ERROR: unrecognized scroll unit!!!")

        if step["action"] == "Scroll Down":
            scroll_amount = 0 - scroll_amount

        if "scroll_resolution" in symTab:
            logger.info("Calculated Scroll Amount: "+str(scroll_amount)+"scroll resoution: "+str(symTab["scroll_resolution"]))
        else:
            logger.info("Calculated Scroll Amount: "+str(scroll_amount)+"scroll resoution: NOT YET AVAILABLE")

        if step["random_max"] != step["random_min"]:
            if step["action"] == "Scroll Down":
                scroll_amount = scroll_amount - random.randrange(step["random_min"], step["random_max"])
            else:
                scroll_amount = scroll_amount + random.randrange(step["random_min"], step["random_max"])

        log6(f"Mouse Scroll Amount: {scroll_amount}", "wan_log", mainwin, mission, i)
        mouse.scroll(0, scroll_amount)

        time.sleep(step["postwait"])


        if step["breakpoint"]:
            input("type any key to continue")


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorMouseScroll:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorMouseScroll: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def kill_process_using_port(port):
    for conn in psutil.net_connections():
        if conn.laddr.port == port:
            psutil.Process(conn.pid).terminate()
            print(f"Terminated process with PID {conn.pid} using port {port}.")


def is_app_running(process_name):
    """Check if a process with the given name is running."""
    for proc in psutil.process_iter(['name']):
        if process_name.lower() in proc.info['name'].lower():
            return proc
    return None


# step['app_link'] full path location of the executable, it could be variable.
# step['app_type'] short name for the app, used to locate app window, so must be a substring of window title.
# step['cargs_type'] -  "direct" "expr"
# step['cargs'] - command arguments could be string, could be a list of strings, could be a variable holding the arguments....
def processOpenApp(step, i, mission):
    # logger.info("Opening App ....." + step["app_link"] + " " + step["cargs"])
    ex_stat = DEFAULT_RUN_STATUS
    mainwin = mission.get_main_win()
    try:
        log6(f"Open App .....{step['app_type']}...{step['app_link']}", "wan_log", mainwin, mission, i)
        if step["app_type"] == "browser":
            url = step["app_link"]
            webbrowser.open(url, new=0, autoraise=True)
        else:
            if ("/" in step["app_link"] or "\\" in step["app_link"] or ".exe" in step["app_link"]) and "[" not in step["app_link"] and "{" not in step["app_link"]:
                executable = step["app_link"]
            elif (("[" not in step["app_link"]) or ("{" not in step["app_link"])):
                # this is an expression, so need to eval
                exec("global oa_exe\noa_exe = " + step['app_link'] + "\nprint('oa_exe: ', oa_exe)")
                executable = oa_exe
            else:
                executable = symTab[step["app_link"]]

            if is_app_running(step["app_type"]):
                #simply bring the process/window to the front.
                symTab[step["result"]], symTab[step["win_info"]] = switchToWindow(step["app_type"])
            else:
                # start the app afresh
                # exec("global oa_exe\noa_exe = "+step["app_type"])
                if step["cargs_type"] == "direct":
                    # 将字符串命令转换为列表格式
                    from utils.subprocess_helper import run_no_window
                    if step["cargs"]:
                        cmd_args = step["cargs"].split()
                        run_no_window([executable] + cmd_args)
                    else:
                        run_no_window([executable])
                else:
                    # in case of "expr" type.
                    if type(step["cargs"]) == list or step["cargs"] == "":
                        cmd = [executable] + step["cargs"]
                    else:
                        exec("global oa_args\noa_args = "+step['cargs']+"\nprint('oa_args: ', oa_args)")
                        if type(oa_args) == str:
                            cmd = [executable] + [oa_args]
                        elif type(oa_args) == list:
                            cmd = [executable] + oa_args

                    # Use subprocess helper to prevent console window popup in frozen environment
                    from utils.subprocess_helper import popen_no_window
                    popen_no_window(cmd, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        time.sleep(step["wait"])
        symTab[step["result"]] = True

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOpenApp:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOpenApp: traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["result"]] = False
        symTab[step["win_info"]] = None

    return (i + 1), ex_stat


def extract_variable_names(code_line):
    # Parse the code line into an abstract syntax tree (AST)
    try:
        # Wrap the code in a valid Python expression using eval()
        tree = ast.parse(code_line)
    except Exception as e:
        logger.error("Error:"+json.dumps(e))
        return []  # Return empty list if parsing fails

    # Traverse the AST and extract variable names
    variable_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            variable_names.append(node.id)

    return variable_names

# create a new variable in the name space and assign initial value to it.
# data_name: name of the variable.
# key_name, key_value, could be a dictionary with a key-value paire.
def processCreateData(step, i):
    logger.info("Creating Data .....")
    global mission_vars
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["key_name"] == "NA":
            # this is the case of direct assignment.
            # logger.info("NOT AN DICT ENTRY ASSIGNMENT")
            if step["data_type"] == "expr":
                logger.info("TBEx: "+json.dumps(step["data_name"]) + " = "+json.dumps(step["key_value"]))
                # symTab[step["data_name"]] = None
                # exec("global sk_work_settings")
                # exec("global "+step["data_name"])
                simple_expression = step["data_name"] + " = " + step["key_value"]
                expr_vars = extract_variable_names(simple_expression)
                logger.info("vars in the expression:"+json.dumps(expr_vars))
                executable = "global"
                for expr_var in expr_vars:
                    # logger.info("woooooohahahahahah"+json.dumps(executable))
                    executable = executable + " " + expr_var
                    if expr_vars.index(expr_var) != len(expr_vars) - 1:
                        executable = executable + ","
                logger.info("full executable statement:" + executable)
                executable = executable + "\n" + simple_expression

                exec(executable)
                # logger.info(step["data_name"] + " is now: "+json.dumps(symTab[step["data_name"]]))
            else:
                symTab[step["data_name"]] = step["key_value"]
        else:
            if not re.match(r"\[.*\]|\{.*\}", step["key_value"]):
                symTab[step["data_name"]] = {step["key_name"]: step["key_value"]}
            else:
                symTab[step["data_name"]] = {step["key_name"]: json.loads(step["key_value"])}

        mission_vars.append(step["data_name"])


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateData:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateData: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processTextToNumber(step, i):
    original = symTab[step["intext"]]
    ex_stat = DEFAULT_RUN_STATUS
    try:
        num = original.strip().split(" ")[0].replace("$", "").replace("#", "").replace("%", "").replace(",", "").replace(" ", "")

        if "." in num:
            symTab[step["numvar"]] = float(num)
        else:
            symTab[step["numvar"]] = int(num)

        if "%" in original:
            symTab[step["numvar"]] = symTab[step["numvar"]]/100


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorText2Number:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorText2Number: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat



# this is for add an object to a list/array of object, or add another key-value pair to a json object.
# from: value source
# to: value destination
# result: the destination variable when operation is a "pop" in which case, "from" is the index, "to" is the list variable name.
# fill_type: "assign"/"copy"/"append"/"prepend"/"merge"/"clear"/"pop":
def processFillData(step, i):
    logger.info("Filling Data ....."+json.dumps(step))
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # if not re.match("\[.*\]|\{.*\}", step["from"]):
        if type(step["from"]) is str:
            from_words = re.split(r'\[|\(|\{', step["from"])
            source = from_words[0]
        else:
            source = step["from"]
        logger.info("source var:"+json.dumps(source))

        if type(step["to"]) is str:
            to_words = re.split(r'\[|\(|\{', step["to"])
            sink = to_words[0]
        else:
            sink = step["to"]
        logger.info("sink var:"+json.dumps(sink))

        if step["result"] != "":
            res_words = re.split(r'\[|\(|\{', step["result"])
            res = to_words[0]
            logger.info("res var:"+json.dumps(res))

        if step["fill_type"] == "assign":
            statement = "global " + source + ", " + sink + "; " + step["to"] + " = " + step["from"]
        elif step["fill_type"] == "copy":
            statement = "global " + source + ", " + sink + "; " + step["to"] + " = deepcopy(" + step["from"] + ")"
        elif step["fill_type"] == "append":
            statement = "global " + source + ", " + sink + "; " + step["to"] + ".append(" + step["from"] + ")"
        elif step["fill_type"] == "prepend":
            statement = "global " + source + ", " + sink + "; " + step["to"] + ".insert(0, " + step["from"] + ")"
        elif step["fill_type"] == "merge":
            statement = "global " + source + ", " + sink + "; " + step["to"] + ".extend(" + step["from"] + ")"
        elif step["fill_type"] == "clear":
            statement = "global " + sink + "; " + step["to"] + ".clear()"
        elif step["fill_type"] == "pop":
            if step["result"] != "":
                if step["from"].isnumeric():
                    statement = "global " + res + ", " + sink + "; " + step["result"] + " = " + step["to"] + ".pop(" + \
                                step["from"] + ")"
                else:
                    statement = "global " + res + ", " + source + ", " + sink + "; " + step["result"] + " = " + step[
                        "to"] + ".pop(" + step["from"] + ")"
        else:
            #in the special case of "direct" assign value.
            if type(step["from"]) is str:
                statement = "global " + sink + "; " + step["to"] + " = " + step["from"]
            elif type(step["from"]) is dict:
                statement = "global " + sink + "; " + step["to"] + " = " + json.dumps(step["from"])
            else:
                statement = "global " + sink + "; " + step["to"] + " = " + str(step["from"])
        logger.info("Statement: "+statement)
        exec(statement)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorFillData:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorFillData: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

# basically context switching here...
def processEndException(step, i, step_keys):
    global exception_stack
    global page_stack
    global in_exception
    logger.info("Return from Exception .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # basically do a rollback, and resume running from the last rollback point.
        rollback_point = page_stack.pop()
        idx = rollback_point["pc"]
        restore_current_context(rollback_point["context"])
        exception_stack.pop()
        if len(exception_stack) == 0:
            # clear the exception flag.
            in_exception = False



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorException:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorException: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return idx, ex_stat


# this is the exception handler, basically keep retry ping the target website until success.
def processExceptionHandler(step, i, step_keys):
    max_retries = 3
    min_retry_back_off = 3
    max_retry_back_off = 10
    site = "example.com"
    n_retries = 0
    global net_connected

    ex_stat = DEFAULT_RUN_STATUS
    try:
        while n_retries <= max_retries:
            # back off some time,
            rand_back_off = random.randrange(min_retry_back_off, max_retry_back_off)
            time.sleep(rand_back_off)

            # then retry connect to the internet, later can add more action here to use mouse to disconnect and reconnect wifi....
            conn_time = ping(site)

            if conn_time:
                net_connected = True
                break

        if net_connected:
            logger.info("reconnected, set up to resume from the rollback point")
            # hit refresh page. Ctrl-F5
            pyautogui.hotkey("ctrl", "f5")

        else:
            logger.info("MISSION failed...")



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExceptionHandler:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExceptionHandler: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


# big assumptions: all involved variables have already been created in globals
# need to do 2 things:
# 1) get rid of all keywords and operators: and or not,  get rid of all [] "" '' pairs, compare operators > < == >= <=
# 2) extract all varaibles and declare them global before the condition string.
#    for example, if the original compare string is "x > 5 and y < 8", it should be "global x, y, cmp_result; cmp_result = x > 5 and y < 8"
def evalCondition(condition):
    global cmp_result
    fault = False
    root = ast.parse(condition)
    logger.info(ast.dump(ast.parse(condition)))
    # logger.info("root:"+json.dumps(root))
    # extract all variable names in the condition statement expression
    varnames = sorted({node.id for node in ast.walk(root) if isinstance(node, ast.Name)})
    # logger.info("varnames:"+json.dumps(varnames))
    # now filter out special keywords such int, str, float what's left should be variable names.
    varnames = list(filter(lambda k: not (k == "float" or k == "int" or k == "str" or k == "len"), varnames))
    logger.info("filtered varnames:"+json.dumps(varnames))
    prefix = "global "
    for varname in varnames:
        if varname in symTab:
            prefix = prefix + varname + ", "
        else:
            # if the variable doesn't exist, create the variable.
            symTab[varname] = None

    prefix = prefix + "cmp_result\ncmp_result = ("
    condition = prefix + condition + ")"
    logger.info("TBE: " + condition)
    exec(condition)
    logger.info("TBE result: "+str(cmp_result))

    return cmp_result


# "type": "Check Condition",
# "condition": condition,
# "if_else": ifelse,
# "if_end": ifend
def processCheckCondition(step, i, step_keys):
    logger.info("Check Condition.....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        condition = step["condition"]

        if evalCondition(condition):
            idx = i + 1
        else:
            idx = step_keys.index(step["if_else"])
            logger.info("else: "+json.dumps(step["if_else"])+"else idx: "+str(idx))


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckCondition:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckCondition: traceback information not available:" + str(e)
        logger.error(ex_stat)


    return idx, ex_stat


# "type": "Repeat",
# "lc_name": loop counter name. need to be unique, usually is the stepname.
# "until": loop condition condition,
# "count": repeat count,
# "end": loop end marker.
def processRepeat(step, i,  step_keys):
    logger.info("Looping.....: "+json.dumps(step))
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["count"].isnumeric():
            repeat_count = int(step["count"])
        else:
            repeat_count = 0

        loop_condition = step["until"]
        end_step = step_keys.index(step["end"])

        #prefix = (skey.split("!"))[0]
        #end_words = step["end"].split()
        #loop_end = prefix + "!" + "step" + end_words[1]
        end_idx = end_step
        #prev_idx = steps.index(skey)

        if loop_condition == "":
            # create eval loop condition which is whether loop counter is the repeat count.
            # at the address generation routine, at the loop end stub, needs to add a code to
            # update loop counter, before jumping back to condition here.
            # lcvar_name = "lcv_" + step["lc_name"]+str(i)
            lcvar_name = step["lc_name"]
            logger.info("repeat counter: "+str(symTab[lcvar_name])+"target count: "+str(step["count"]))
            if symTab[lcvar_name] < int(step["count"]):
                symTab[lcvar_name] = symTab[lcvar_name] + 1
                end_idx = i + 1

        else:
            # use loop condition.
            if evalCondition(loop_condition):
                end_idx = i + 1



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRepeat:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRepeat: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return end_idx, ex_stat

# assumption: data is in form of a single json which can be easily dumped.
def processLoadData(step, i):
    logger.info("Loading Data .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        with open(step["file_link"], 'r') as f:
            symTab[step["data_name"]] = json.load(f)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadData:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadData: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat


def processSaveData(step, i):
    logger.info("Saving Data .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        with open(step["file_link"], 'w') as f:
            json.dump(symTab[step["data_name"]], f)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSaveData:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSaveData: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat

# fname: external script/function name  - very IMPORTANT： this is calling python routine either in a file or a function， this is different from
#          psk function/subroutine
# args: arguments to the external functions.
# entity: "are we calling a script or function?"
# output: output data variable
def processCallExtern(step, i):
    logger.info("Run External Script/code as strings .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["entity"] == "file":
            cmdline = ["python", step["file"]]

            if step["args"] != "":
                args_strings = json.loads(step["args"])
                # converts string(var name) into variables in symbol table.
                args = list(map(lambda x: symTab[x], args_strings))
            else:
                args = []

            cmdline.extend(args)
            logger.info("command line: "+json.dumps(cmdline))
            from utils.subprocess_helper import run_no_window
            result = run_no_window(cmdline, capture_output=True, text=True)
        else:
            # execute a string as raw python code.
            result = exec(step["file"])
            if "nNRP" in step["file"]:
                logger.info("nNRP: "+json.dumps(symTab["nNRP"]))
        # if symTab[step["fill_method"]] == "assign":
        #     symTab[step["output"]] = result
        # elif symTab[step["fill_method"]] == "copy_obj":
        #     symTab[step["output"]] = copy.deepcopy(result)

        symTab[step["output"]] = result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallExtern:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallExtern: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat


async def processCallExtern8(step, i):
    logger.info("Run External Script/code as strings .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["entity"] == "file":
            cmdline = ["python", step["file"]]

            if step["args"] != "":
                args_strings = json.loads(step["args"])
                # converts string(var name) into variables in symbol table.
                args = list(map(lambda x: symTab[x], args_strings))
            else:
                args = []

            cmdline.extend(args)
            logger.info("command line: " + json.dumps(cmdline))
            from utils.subprocess_helper import run_no_window
            result = run_no_window(cmdline, capture_output=True, text=True)
        else:
            # execute a string as raw python code.
            result = exec(step["file"])
            if "nNRP" in step["file"]:
                logger.info("nNRP: " + json.dumps(symTab["nNRP"]))
        # if symTab[step["fill_method"]] == "assign":
        #     symTab[step["output"]] = result
        # elif symTab[step["fill_method"]] == "copy_obj":
        #     symTab[step["output"]] = copy.deepcopy(result)

        symTab[step["output"]] = result

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallExtern:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallExtern: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i+1), ex_stat

# this is for call a skill function.
# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def processUseSkill(step, i, stack, sk_stack, sk_table, step_keys):
    global skill_code

    ex_stat = DEFAULT_RUN_STATUS
    try:
        # push current address pointer onto stack,
        stack.append(i+1)
        sk_stack.append(step["skill_name"])
        stack.append(symTab["sk_work_settings"])
        #save current fin, fout whatever that is.
        stack.append(symTab["fout"])
        stack.append(symTab["fin"])

        # push function output var to the stack
        stack.append(step["output"])

        # push input args onto stack
        stack.append(step["skill_args"])

        fin_par = stack.pop()
        symTab["fin"] = symTab[fin_par]
        # logger.info("getting skill call input parameter: "+json.dumps(fin_par)+" [val: "+json.dumps(symTab[fin_par]))
        logger.info("current skill table: "+json.dumps(sk_table))

        # start execuation on the function, find the function name's address, and set next pointer to it.
        # the function name address key value pair was created in gen_addresses
        skname = step["skill_path"] + "/" + step["skill_name"]
        logger.info("curr skill name: "+skname)

        if skname in sk_table:
            logger.info("skname:"+skname+"  "+sk_table[skname])
            idx = step_keys.index(sk_table[skname])
            logger.info("idx:"+str(idx))
        else:
            logger.error("ERROR: LOCAL SKILL NOT FOUND, DONT KNOW WHAT TO DO")
            idx = -1


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorUseSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorUseSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return idx, ex_stat


# this is essentially an AppSync mutation API call to request running external skill.
# the cloud side will check permission, and then create a mission for a bot with this
# skill to run by the skill provider.
def processUseExternalSkill(step, i, mission):
    global skill_code

    ex_stat = DEFAULT_RUN_STATUS
    try:
        settings = mission.main_win_settings
        # 	skid: ID!
        # 	requester_mid: ID!
        # 	owner: String
        # 	name: String
        # 	start: AWSDateTime
        # 	in_data: AWSJSON!
        # 	verbose: Boolean
        req = {
            "skid": step["skid"],
            "requester_mid": symTab[step["requester_mid"]],
            "owner": step["owner"],
            "start": symTab[step["start_time"]],
            "name": step["skname"],
            "in_data": json.dumps(symTab[step["in_data"]]).replace('"', '\\"'),
            # "in_data": json.dumps({}).replace('"', '\\"'),
            "verbose": step["verbose"]
        }
        reqs = [req]
        print("REQS:", reqs)

        mainwin = mission.get_main_win()
        symTab[step["output"]] = send_run_ext_skill_request_to_cloud(settings["session"], reqs, settings["token"], mainwin.getWanApiEndpoint())

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorUseExternalSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorUseExternalSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return i+1, ex_stat


def processReportExternalSkillRunStatus(step, i, mission):
    global skill_code

    ex_stat = DEFAULT_RUN_STATUS
    try:
        settings = mission.main_win_settings
        print("report reuslt data:", type(symTab[step["result_data"]]), symTab[step["result_data"]])
        req = {
            "run_id": symTab[step["run_id"]],
            "skid": step["skill_id"],
            "runner_mid": symTab[step["runner_mid"]],
            "runner_bid": symTab[step["runner_bid"]],
            "requester": symTab[step["requester"]],
            "start_time": symTab[step["start_time"]],
            "end_time": symTab[step["end_time"]],
            "status": symTab[step["status"]],
            # "result_data": "[{\"dir\": \"\"}]"
            # "result_data": json.dumps(symTab[step["result_data"]])
            "result_data": json.dumps(symTab[step["result_data"]]).replace('"', '\\"')
        }
        reqs = [req]

        mainwin = mission.get_main_win()
        send_result = send_report_run_ext_skill_status_request_to_cloud(settings["session"], reqs, settings["token"], mainwin.getWanApiEndpoint())

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReportExternalSkillRunStatus:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorReportExternalSkillRunStatus: traceback information not available:" + str(e)
        logger.error(ex_stat, "processReportExternalSkillRunStatus", )

    return i+1, ex_stat


# this is for call a skill function.
# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def processOverloadSkill(step, i, stack, step_keys):
    global skill_code
    global skill_table
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # push current address pointer onto stack,
        stack.append(i)

        #save current fin, fout whatever that is.
        stack.append(symTab["fout"])
        stack.append(symTab["fin"])

        # push function output var to the stack
        stack.append(step["output"])

        # push input args onto stack
        stack.append(step["args"])

        # start execuation on the function, find the function name's address, and set next pointer to it.
        # the function name address key value pair was created in gen_addresses
        idx = step_keys.index(skill_table[step["skill_name"]])



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOverloadSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOverloadSkill: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return idx, ex_stat


# this is for call a skill function.
# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def processCallFunction(step, i, stack, func_table, step_keys):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # push current address pointer onto stack,
        stack.append(i+1)

        #save current fin, fout whatever that is.
        stack.append(symTab["fout"])
        stack.append(symTab["fin"])

        # push function output var name to the stack
        stack.append(step["output"])

        # push input args onto stack
        stack.append(step["fargs"])

        fin_par = stack.pop()
        symTab["fin"] = symTab[fin_par]
        logger.info("geting function call input parameter: "+json.dumps(fin_par)+" [val: "+json.dumps(symTab[fin_par]))

        # start execuation on the function, find the function name's address, and set next pointer to it.
        # the function name address key value pair was created in gen_addresses
        idx = step_keys.index(func_table[step["fname"]])



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallFunction:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallFunction: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return idx, ex_stat


def processReturn(step, i, stack, step_keys):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # push current address pointer onto stack,
        return_var_name = stack.pop()

        if return_var_name != "":
            symTab[return_var_name] = symTab[step["val_var_name"]]
            # logger.info("return var.....", step["val_var_name"], "[val:", symTab[step["val_var_name"]])
            # logger.info("return result to .....", return_var_name, "[val:", symTab[return_var_name])

        # restoer original fin and fout.
        symTab["fin"] = stack.pop()
        symTab["fout"] = stack.pop()


        #  set the pointer to the return to pointer.
        next_i = stack.pop()
        logger.info("after return, will run @"+str(next_i))



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReturn:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorReturn: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return next_i, ex_stat


# this is a stub/marker for end of if-else, end of function, end of loop etc. SC - 20230723 total mistake of this function....
# whatever written here should be in address generation.
def processStub(step, i, stack, sk_stack, sk_table, step_keys):
    global TEST_RUN_CNT
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1

        # note, end condition, else, end loop will not even exist because they will be replaced by "Goto" during
        # the gen_addresses step.
        if step["stub_name"] == "end function":
            # restore caller's fin and fout.
            # when reaching here, there is nothing to return. so, the return receiver var is a junk.
            junk = stack.pop()

            # restore fin and fout.
            symTab["fin"] = stack.pop()
            symTab["fout"] = stack.pop()

            #  set the pointer to the return to pointer.
            next_i = stack.pop()

        if step["stub_name"] == "end skill":
            logger.info("end of a skill "+step["func_name"]+" reached.<"+str(len(sk_stack))+">")
            if len(sk_stack) == 0:
                #set next_i to be a huage number, that wuold stop the code.
                next_i = MAX_STEPS
            else:
                junk = sk_stack.pop()

                return_var_name = stack.pop()
                if return_var_name != "":
                    symTab[return_var_name] = symTab["fout"]      # assign return value

                symTab["fin"] = stack.pop()
                symTab["fout"] = stack.pop()
                symTab["sk_work_settings"] = stack.pop()
                #  set the pointer to the return to pointer.
                next_i = stack.pop()

            if step["func_name"] == "public/win_ads_amz_home/***_***":
                if TEST_RUN_CNT > 1:
                    ex_stat = "ErrorStub: Manually Set Error"

                logger.info("TEST_RUN_CNT ex_stat:"+str(TEST_RUN_CNT)+"[" + ex_stat + "]")
                TEST_RUN_CNT = TEST_RUN_CNT + 1
        elif step["stub_name"] == "start skill main":
            stack.append(0)
            stack.append("main_in")
            stack.append("main_out")
            stack.append("main_settings")
            stack.append("main_args")



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorStub:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorStub: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return next_i, ex_stat


def processGoto(step, i,  step_keys):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        logger.info("stepGOTO:"+step["goto"])
        if "step B" in step["goto"] and "!" in step["goto"] :
            next_step_index = step_keys.index(step["goto"])
        else:
            next_step_index = step_keys.index(symTab[step["goto"]])



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGoTo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGoTo: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return next_step_index, ex_stat


def processListDir(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        current_time = datetime.now()
        hours = step["most_recent"]
        cutoff_time = current_time - timedelta(hours=hours)
        if "/" in step["dir"]:
            target_dir = step["dir"]
        else:
            target_dir = symTab[step["dir"]]

        all_files = []
        lof = os.listdir(target_dir)
        for filename in lof:
            file_path = os.path.join(target_dir, filename)
            if os.path.isfile(file_path):
                file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mod_time > cutoff_time:
                    all_files.append((file_path, file_mod_time))

        if step["extension"]:
            file_list = [f for f in all_files if f[0].endswith(step["extension"])]  # fargs contains extension such as ".pdf"
        else:
            file_list = all_files

        if step["sort_by"] == "time":
            if step["sort_order"] == "min-max":
                sorted_list = sorted(file_list, key=lambda x: x[1], reverse=False)
            else:
                sorted_list =sorted(file_list, key=lambda x: x[1], reverse=True)
        elif step["sort_by"] == "name":
            if step["sort_order"] == "min-max":
                sorted_list = sorted(file_list, key=lambda x: x[0], reverse=False)
            else:
                sorted_list =sorted(file_list, key=lambda x: x[0], reverse=True)

        symTab[step["result"]] = [f[0] for f in sorted_list]

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorListDir:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorListDir: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processCheckExistence(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if "var" in step["fntype"]:
            fn = symTab[step["file"]]
        else:
            fn = step["file"]
        logger.info("check existence for :"+fn+" of type:"+step["fntype"])
        if "dir" in step["fntype"]:
            symTab[step["result"]] = os.path.isdir(fn)
        else:
            symTab[step["result"]] = os.path.isfile(fn)

        logger.info("Existence is:"+json.dumps(symTab[step["result"]]))



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckExistence:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckExistence: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

dir_tbc = ""
def processCreateDir(step, i):
    global dir_tbc
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["name_type"] == "direct":
            dir_tbc = step["dir"]
        else:
            if "[" in step["dir"]:
                src_var_name = step["dir"].split("[")[0]
            else:
                src_var_name = step["dir"]
            exec("global dir_tbc, "+src_var_name+"\ndir_tbc = " + step["dir"])
            # symTab[step["dir_tbc"]] = step["dir"]

        newdir = dir_tbc

        if not os.path.exists(newdir):
            #create only if the dir doesn't exist
            os.makedirs(newdir)
            logger.info("Created....." + newdir)
        else:
            logger.info(newdir + " already existed.")



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateDir:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCreateDir: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

def processReadFile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True
    symTab[step["datasink"]] = ""
    try:
        if step["name_type"] == "direct":
            file_full_path = step["filename"]
        else:
            # exec("file_full_path = " + step["filename"])
            file_full_path = symTab[step["filename"]]

        logger.info("Read from file:"+file_full_path)
        if os.path.exists(file_full_path):
            #create only if the dir doesn't exist
            with open(file_full_path, 'r') as fileTBR:
                if step["filetype"] == "json":
                    symTab[step["datasink"]] = json.load(fileTBR)
                elif step["filetype"] == "txt":
                    symTab[step["datasink"]] = fileTBR.read()

            fileTBR.close()
        else:
            logger.error("ERROR: File not exists")
            symTab[step["flag"]] = False

        print("read succeeded:", symTab[step["flag"]])
        print("read result:", step["datasink"], symTab[step["datasink"]])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReadFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorReadFile: traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat

def processWriteFile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["result"]] = True
    try:
        if step["name_type"] == "direct":
            file_full_path = step["filename"]
        else:
            file_full_path = symTab[step["filename"]]

        logger.info("Write to file:" + file_full_path)

        # Ensure directory exists
        path_manager.ensure_directory_exists(file_full_path)

        # Prepare content based on file type
        if step["filetype"] == "json":
            content = json.dumps(symTab[step["datasource"]], indent=2)
        elif step["filetype"] == "txt":
            if isinstance(symTab[step["datasource"]], list):
                content = ''.join(symTab[step["datasource"]])
            else:
                content = str(symTab[step["datasource"]])
        else:
            content = str(symTab[step["datasource"]])

        # Write or append using safe methods
        if step["mode"] == "overwrite":
            safe_write(file_full_path, content)
        else:
            # append mode
            safe_append(file_full_path, content)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWriteFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWriteFile: traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat


def processDeleteFile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["result"]] = True
    try:
        if step["name_type"] == "direct":
            file_full_path = step["filename"]
        else:
            exec("file_full_path = " + step["filename"])

        logger.info("Delete a file:" + file_full_path)
        if os.path.exists(file_full_path):
            # create only if the dir doesn't exist
            os.remove(file_full_path)
        else:
            logger.warning("WARNING: File not exists")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorDeleteFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorDeleteFile: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processObtainReviews(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    mainwin = mission.get_main_win()

    review_request = [{"product": symTab[step["product"]], "instructions": symTab[step["instructions"]]}]
    try:
        settings = mission.main_win_settings
        resp = req_cloud_obtain_review(settings["session"], review_request, settings["token"], mainwin.getWanApiEndpoint())
        netReview = json.loads(resp['body'])
        symTab[step["review_body"]] = netReview["body"]
        symTab[step["review_title"]] = netReview["title"]
        symTab[step["store_feedback"]] = netReview["store_fb"]

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorObtainReview:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorObtainReview: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

# run 7z for the zip and unzip.
def process7z(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["var_type"] == "direct":
            exe = step["exe_var"]
            input = step["in_var"]
            output_dir = step["out_path"]
            out_file = step["out_var"]
        else:
            exe = symTab[step["exe_var"]]
            input = symTab[step["in_var"]]
            output_dir = symTab[step["out_path"]]
            out_file = symTab[step["out_var"]]

        if step["action"] == "zip":
            from utils.subprocess_helper import run_no_window
            if output_dir != "":
                symTab[step["result"]] = run_no_window([exe, "a", input, "-o" + output_dir])
            else:
                symTab[step["result"]] = run_no_window([exe, "e", input])

        elif step["action"] == "unzip":
            if output_dir != "":
                logger.info("executing...."+ exe + " e " + input + " -o" + output_dir)
                # output_dir = "-o"+output_dir
                logger.info("outputdir:"+output_dir)
                # extremely key here, there should be no "" around Program Files....
                cmd = ['C:/Program Files/7-Zip/7z.exe', 'e', input,  f'-o{output_dir}']
                # Use subprocess helper to prevent console window popup in frozen environment
                from utils.subprocess_helper import popen_no_window
                symTab[step["result"]] = popen_no_window(cmd)
                # symTab[step["result"]] = subprocess.run(exe + " e " + input + " -o" + output_dir)
            else:
                from utils.subprocess_helper import run_no_window
                symTab[step["result"]] = run_no_window([exe, "e", input])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "Error7z:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "Error7z: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

def zip_files(files_and_dirs, output_zip_path):
    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in files_and_dirs:
            if os.path.isdir(item):
                # If it's a directory, walk through all its contents
                for root, dirs, files in os.walk(item):
                    for file in files:
                        # Create the full path of the file
                        file_path = os.path.join(root, file)
                        # Add the file to the zip, using a relative path
                        print("zipping file:", file_path)
                        zipf.write(file_path, os.path.relpath(file_path, os.path.dirname(item)))
            else:
                # If it's a file, just add it
                zipf.write(item, os.path.basename(item))


def list_zip_file(fullzip):
    zip_contents = []
    with zipfile.ZipFile(fullzip, 'r') as zip_ref:
        # List all the contents of the zip file
        zip_contents = zip_ref.namelist()

    return zip_contents


def safe_rename(src, dst):
    """Rename a file or directory, handling long paths on Windows."""
    src = make_unc_path(src)
    dst = make_unc_path(dst)
    os.rename(src, dst)


def make_unc_path(path):
    """Convert a path to UNC format if on Windows and path exceeds 260 characters."""
    if platform.system() == "Windows" and len(path) > 260:
        # Convert to UNC path
        return r"\\?\{}".format(os.path.abspath(path))
    return path

def unzip_file(fullzip, extract_to):
    # Convert paths to UNC format on Windows if necessary
    fullzip = make_unc_path(fullzip)
    extract_to = make_unc_path(extract_to)

    if extract_to:
        # Ensure the destination directory exists
        os.makedirs(extract_to, exist_ok=True)
    else:
        # If no destination directory is provided, use the current directory
        extract_to = os.getcwd()

    with zipfile.ZipFile(fullzip, 'r') as zipf:
        for zipinfo in zipf.infolist():
            try:
                # Construct the full path where the file will be extracted
                extracted_path = os.path.join(extract_to, zipinfo.filename)

                # Convert the extracted path to UNC format if necessary
                extracted_path = make_unc_path(extracted_path)

                # Create the directory if it's not already present
                if not os.path.exists(os.path.dirname(extracted_path)):
                    os.makedirs(os.path.dirname(extracted_path), exist_ok=True)

                # Extract the file
                with open(extracted_path, 'wb') as f:
                    f.write(zipf.read(zipinfo.filename))

                # print(f"Extracted: {extracted_path}")

            except FileNotFoundError as e:
                print(f"Error extracting {zipinfo.filename}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while extracting {zipinfo.filename}: {e}")


def processZipUnzip(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["var_type"] == "direct":
            input = step["in_var"]
            output_dir = step["out_path"]
            out_file = step["out_var"]
        else:
            input = symTab[step["in_var"]]
            output_dir = symTab[step["out_path"]]
            out_file = symTab[step["out_var"]]

        if step["action"] == "zip":
            print("Zippping.....", input, output_dir, out_file)
            norm_out = os.path.normpath(os.path.join(output_dir, out_file))
            if type(input) == list:
                norm_in = [os.path.normpath(inf) for inf in input]
                zip_files(norm_in, norm_out)
            else:
                zip_files([os.path.normpath(input)], norm_out)
        elif step["action"] == "unzip":
            logger.info("executing....unzip" + input + " to" + output_dir)
            norm_out = os.path.normpath(output_dir)
            if not os.path.exists(norm_out):
                os.makedirs(norm_out)

            norm_in = os.path.normpath(input)
            unzip_file(norm_in, norm_out)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorZipUnzip:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorZipUnzip: traceback information not available:" + str(e)
        symTab[step["result"]] = ex_stat
        logger.error(ex_stat)

    return (i + 1), ex_stat


def are_locs_close(obj1, obj2, threshold=10):
    """
    Check if two rectangles are within a threshold distance.
    """
    left1, top1, right1, bottom1 = obj1["loc"]
    left2, top2, right2, bottom2 = obj2["loc"]

    return (abs(left1 - left2) <= threshold and
            abs(top1 - top2) <= threshold and
            abs(right1 - right2) <= threshold and
            abs(bottom1 - bottom2) <= threshold)


def filter_duplicates(objs, threshold=10):
    """
    Filter out duplicate rectangles within a given threshold.
    """
    filtered_objs = []
    for obj in objs:
        if not any(are_locs_close(obj, unique_one, threshold) for unique_one in filtered_objs):
            filtered_objs.append(obj)
    return filtered_objs


# create a data structure holder for anchor....
# "type": "Search",
# "action": "Search",
# "screen": screen,
# "name": name,
# "target_type": target_type, target type
# "result": result, result varaibel continas result.
# "status": flag - flag variable contains result
def processSearchAnchorInfo(step, i):
    logger.info("Searching...."+json.dumps(step["target_types"]))
    global in_exception
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        # logger.info("SEARCH SCREEN INFO:"+json.dumps(scrn))
        logic = step["logic"]
        fault_names = ["site_not_reached", "bad_request"]
        fault_found = []

        found = []
        n_targets_found = 0

        # logger.info("Searching screen...."+json.dumps(scrn))

        if not (type(step["names"]) is list):
            target_names = [step["names"]]  # make it a list.
        else:
            target_names = step["names"]

        if not (type(step["target_types"]) is list):
            target_types = [step["target_types"]]*len(target_names)
        else:
            target_types = step["target_types"]


        for idx in range(len(target_names)):
            logger.info("ith target:"+str(idx)+" "+target_types[idx]+" "+target_names[idx])
            if step["name_type"] != "direct":
                exec("global temp_target_name\ntemp_target_name= " + target_names[idx])
                target_names[idx] = temp_target_name

        # now do the search
        for target_name, target_type in zip(target_names, target_types):
            logger.info("searching: "+target_name+", "+target_type+"==================")
            targets_found = [element for index, element in enumerate(scrn) if
                             element["name"] == target_name and element["type"] == target_type]
            if len(targets_found) > 0:
                n_targets_found = n_targets_found + 1
            found = found + targets_found

        # reg = re.compile(target_names + "[0-9]+")
        # found = [element for index, element in enumerate(scrn["data"]) if reg.match(element["name"]) and element["type"] == target_types]

        #now remove duplicates
        uniquely_found = filter_duplicates(found)

        logger.info("found.... "+json.dumps(uniquely_found))
        # search result should be put into the result variable.
        symTab[step["result"]] = uniquely_found

        if logic == "any":
            if len(found) == 0:
                symTab[step["status"]] = False
            else:
                symTab[step["status"]] = True
        else:
            # treat everything else as "all" logic.
            if n_targets_found < len(target_names):
                symTab[step["status"]] = False
            else:
                symTab[step["status"]] = True

        logger.info("status: "+json.dumps(symTab[step["status"]]))

        # didn't find anything, check fault situation.
        # if symTab[step["status"]] == False:
        #     fault_found = [e for j, e in enumerate(scrn) if e["name"] in fault_names and e["type"] == "anchor text"]
        #     site_conn = ping(step["site"])
        #     if len(fault_found) > 0 or (not site_conn):
        #         # exception has occured, flag it.
        #         in_exception = True

        if step["breakpoint"]:
            input("type any key to continuue")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSearchAnchorInfo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSearchAnchorInfo: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

def matched_loc(pattern, text):
    match = re.search(pattern, text)
    if match:
        # Pattern found, get the starting index of the match
        index = match.start()
    else:
        index = -1

    return index

# search a subword out of a word or line....
# "type": "Search Word Line",
# "screen": screen,
# "names": names,
# "name_types": name_types,
# "patterns": patterns,
# "logic": logic,
# "result": result,
# "site": site,
# "breakpoint": break_here,
# "status": flag
def fuzzy_substring_match(small_string, large_string, threshold=85):
    match_score = lazy.fuzz.partial_ratio(small_string, large_string)
    return match_score >= threshold


def processSearchWordLine(step, i):
    logger.info("Searching....words and/or lines"+json.dumps(step["name_types"]))
    global in_exception
    p_stat = ""
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        fault_names = ["site_not_reached", "bad_request"]
        fault_found = []

        found = []
        n_targets_found = 0

        # logger.info("Searching screen...."+dumps(scrn))
        if not (type(step["names"]) is list):
            target_names = [step["names"]]  # make it a list.
            name_types = [step["name_types"]]
        else:
            target_names = step["names"]
            name_types = step["name_types"]

        logger.info("target_names:"+json.dumps(target_names)+"name_types:"+json.dumps(name_types))
        for idx in range(len(target_names)):
            if "direct" not in name_types[idx]:
                exec("global temp_target_name\ntemp_target_name= " + target_names[idx])
                target_names[idx] = temp_target_name
                logger.info("ith target:"+str(idx)+" "+name_types[idx]+" "+target_names[idx])

        # now do the search
        # all_lines = [element["txt_struct"] for index, element in enumerate(scrn) if element["name"] == "paragraph" and element["type"] == "info"]
        all_paragraphs = [element for index, element in enumerate(scrn) if element["name"] == "paragraph" and element["type"] == "info"]
        logger.info("all_paragraphs:"+json.dumps(all_paragraphs))
        logger.info("==============================================================")
        # go thru each to be matched pattern and search paragraph by paragraph.
        all_found = []
        for target_name, name_type in zip(target_names, name_types):
            found = []
            for p in all_paragraphs:
                # search which line has the match
                for line in p["txt_struct"]:
                    lmatch = re.search(target_name, line["text"])
                    if lmatch:
                        logger.info("line matched:"+line["text"])
                        start_index = lmatch.start()
                        end_index = lmatch.end()
                        matched_pattern = line["text"][start_index:end_index]
                        matched_words = matched_pattern.split()
                        first_word = matched_words[0]
                        last_word = None
                        logger.info("matched_words"+json.dumps(matched_words)+"first_word"+json.dumps(first_word)+"last_word"+json.dumps(last_word))
                        if len(matched_words) >  1:
                            last_word = matched_words[len(matched_words)-1]
                            logger.info("last_word" + last_word)

                        linewords = [word["text"] for index, word in enumerate(line["words"])]
                        logger.info("linewords" + json.dumps(linewords))
                        match_starts = [word for index, word in enumerate(line["words"]) if fuzzy_substring_match(first_word, word["text"])]

                        if last_word:
                            match_ends = [word for index, word in enumerate(line["words"]) if fuzzy_substring_match(last_word, word["text"])]

                        logger.info("match_starts"+json.dumps(match_starts))
                        for match_start in match_starts:
                            if last_word:
                                match_end = next((x for x in match_ends if x["box"][0] > match_start["box"][2] ), None)
                                matched_loc = [match_start["box"][0], match_start["box"][1], match_end["box"][2], match_end["box"][3]]
                                logger.info("match more than 1 word")
                            else:
                                matched_loc = match_start["box"]
                                logger.info("match only 1 word")

                            found.append({"txt": matched_pattern, "box": matched_loc, "line_txt": line["text"]})
                    else:
                        p_stat = "pattern NOT FOUND in paragraph"
                        # logger.info(p_stat+">>"+p["text"])

            # line up the matched location top to bottom.
            if len(found) > 0:
                logger.info("found here"+json.dumps(found))
                sorted_found = sorted(found, key=lambda w: w["box"][1], reverse=False)
                all_found.extend(sorted_found)

            logger.info("======================+++++++++++++++++++++++++++++++++++")

        logger.info("all found.... "+json.dumps(all_found))
        # search result should be put into the result variable.
        symTab[step["result"]] = all_found

        if len(all_found) == 0:
            symTab[step["status"]] = False
        else:
            symTab[step["status"]] = True

        logger.info("status: "+str(symTab[step["status"]]))

        # didn't find anything, check fault situation.
        if symTab[step["status"]] == False:
            fault_found = [e for i, e in enumerate(scrn) if e["name"] in fault_names and e["type"] == "anchor text"]
            site_conn = ping(step["site"])
            if len(fault_found) > 0 or (not site_conn):
                # exception has occured, flag it.
                in_exception = True

        if step["breakpoint"]:
            input("type any key to continuue")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSearchWordLine:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSearchWordLine: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

# this is a convenience function.
# scroll anchor nearest to the north of at_location, to the target location.
# target location, only y direction is used, as we don't intend to mess with x directional scrolling ...
# if value is positive, it's distance from top, if negative, it's the distance from bottom
# anchor: anchor, at_loc: at_loc, target_loc: target_loc, screen: screen, flag: flag
# at loc is x,y coordinate with unit bing % of screen size.
# "type": "Search Scroll",
# "action": "Search Scroll",
# "anchor": anchor,
# "at_loc": at_loc, Example [50, 99] 50% screen height is the upper bound, 99% screen height is the lower bound.
# "target_loc": target_loc, Example 90 meaning at 90% screen height
# "screen": screen,
# "resolution": resolution, scroll resolution
# "flag": flag
def processSearchScroll(step, i):

    logger.info("Searching...."+json.dumps(step["target"]))
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        if isinstance(step["target"], list):
            targets = step["target"]
        else:
            targets = [step["target"]]
        at_loc_top = int(step["at_loc"][0])/100
        at_loc_bottom = int(step["at_loc"][1]) / 100
        target_loc = int(step["target_loc"])/100
        scroll_resolution = step["resolution"]
        screensize = (scrn[len(scrn)-2]["loc"][2], scrn[len(scrn)-2]["loc"][3])
        logger.info("screen size: "+json.dumps(screensize)+"scroll resolution: "+str(symTab[scroll_resolution])+" target_loc:"+json.dumps(target_loc))

        at_loc_top_v = int(screensize[0]*at_loc_top)
        at_loc_bottom_v = int(screensize[0] * at_loc_bottom)
        target_loc_v = int(screensize[0]*target_loc)
        logger.info(" target_loc_V: "+str(target_loc_v)+"at_loc_top_v: "+str(at_loc_top_v)+"at_loc_bottom_v: "+str(at_loc_bottom_v))

        # find all images matches the name and above the at_loc
        logger.info("finding....:"+json.dumps(targets))
        if "anchor" in step["target_type"]:
            if step["dir"] == "down":
                ancs = [element for index, element in enumerate(scrn) if element["name"] in targets and element["loc"][0] > at_loc_top_v and element["loc"][2] < target_loc_v]
            else:
                ancs = [element for index, element in enumerate(scrn) if element["name"] in targets and element["loc"][0] > target_loc_v and element["loc"][2] < at_loc_bottom_v]
        elif step["target_type"] == "text var":
            exec("global target_txt\ntarget_txt = " + step["target"])
            all_paragraphs = [element for index, element in enumerate(scrn) if element["name"] == "paragraph"]
            all_lines = []
            for p in all_paragraphs:
                all_lines = all_lines + p["txt_struct"]

            if step["dir"] == "down":
                matched_lines = [line for index, line in enumerate(all_lines) if target_txt in line["text"] and line["box"][1] > at_loc_top_v and line["box"][3] < at_loc_bottom_v]
            else:
                matched_lines = [line for index, line in enumerate(all_lines) if target_txt in line["text"] and line["box"][1] > target_loc_v and line["box"][3] < at_loc_bottom_v]

            # do a format conversion due to stupid "box", "loc" format mismatch, got to fix this at some point.
            ancs = [{"loc": [ml["box"][1], ml["box"][0], ml["box"][3], ml["box"][2]]} for ml in matched_lines]

        logger.info("found targets in bound: "+json.dumps(ancs))
        if len(ancs) > 0:
            # sort them by vertial distance, largest v coordinate first, so the 1st one is the closest.
            if step["dir"] == "down":
                vsorted = sorted(ancs, key=lambda x: x["loc"][2], reverse=True)
            else:
                vsorted = sorted(ancs, key=lambda x: x["loc"][2], reverse=False)

            logger.info("FFOUND: "+json.dumps(vsorted[0]))
            offset = round((target_loc_v - vsorted[0]["loc"][2])/symTab[scroll_resolution])
            logger.info("calculated offset: "+str(offset)+"target loc"+str(target_loc_v)+"scroll_resolution"+str(symTab[scroll_resolution])+" setting flag var ["+str(step["flag"])+"] to be TRUE....")
            symTab[step["flag"]] = True
        else:
            # if anchor is not on the page, set the flag and scroll down or up 0% of a screen height
            if step["dir"] == "down":
                offset = 0-round(screensize[0]*0.6/symTab[scroll_resolution])
            else:
                offset = round(screensize[0] * 0.6/symTab[scroll_resolution])
            symTab[step["flag"]] = False
            logger.info("KEEP scrolling calculated offset: "+str(offset)+"setting flag var ["+str(step["flag"])+"] to be FALSE....")

        mouse.scroll(0, offset)
        symTab[step["adjustment"]] = symTab[step["adjustment"]] + offset
        time.sleep(step["postwait"])


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSearchScroll:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSearchScroll: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat



# this routine scroll an object to the target location. if multiple targets are found, the one nearest to target will be scrolled to target
# location. location will be an integer that respresent the percentage of screen height from the top of the screen
def processScrollToLocation(step, i):

    logger.info("ScrollToLocation Searching...."+json.dumps(step["target"]))
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        if isinstance(step["target"], list):
            targets = step["target"]
        else:
            targets = [step["target"]]

        target_loc = int(step["target_loc"])/100
        scroll_resolution = step["resolution"]
        screensize = (scrn[len(scrn)-2]["loc"][2], scrn[len(scrn)-2]["loc"][3])
        logger.info("screen size: "+json.dumps(screensize)+"scroll resolution: "+str(symTab[scroll_resolution])+" target_loc:"+json.dumps(target_loc))

        target_loc_v = int(screensize[0]*target_loc)

        # find all images matches the name and above the at_loc
        logger.info("finding....:"+json.dumps(targets))
        if "anchor" in step["target_type"]:
            ancs = [element for index, element in enumerate(scrn) if element["name"] in targets]
        elif step["target_type"] == "text var":
            exec("global target_txt\ntarget_txt = " + step["target"])
            all_paragraphs = [element for index, element in enumerate(scrn) if element["name"] == "paragraph"]
            all_lines = []
            for p in all_paragraphs:
                all_lines = all_lines + p["txt_struct"]
            matched_lines = [line for index, line in enumerate(all_lines) if target_txt in line["text"]]
            # do a format conversion due to stupid "box", "loc" format mismatch, got to fix this at some point.
            ancs = [{"loc": [ml["box"][1], ml["box"][0], ml["box"][3], ml["box"][2]]} for ml in matched_lines]

        logger.info("found targets in bound: "+json.dumps(ancs))
        if len(ancs) > 0:
            # sort them by vertial distance, largest v coordinate first, so the 1st one is the closest.
            vsorted = sorted(ancs, key=lambda x: abs(x["loc"][0]-target_loc_v), reverse=False)
            logger.info("FFOUND: "+json.dumps(vsorted[0]))
            offset = round((target_loc_v - vsorted[0]["loc"][0])/symTab[scroll_resolution])
            logger.info("calculated offset: "+str(offset)+"target loc"+str(target_loc_v)+"scroll_resolution"+str(symTab[scroll_resolution])+" setting flag var ["+str(step["flag"])+"] to be TRUE....")

        mouse.scroll(0, offset)
        time.sleep(step["postwait"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorScrollToLocation:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorScrollToLocation: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat



# this routine scroll until certain a product is right in the middle of the screen and capture its information.
# for grid based layout, it's be enough to do only 1 row, for row based layout, it could be multple rows captured.
# target_anchor: to anchor to adjust postion to
# tilpos: position to adjust anchor to... (+: # of scroll position till screen bottom, -: # of scroll postion from screen top)
def genScrollDownUntilLoc(target_anchor, target_type, tilpos, page, section, adjust_val, stepN, worksettings, site, theme):
    psk_words = ""
    ex_stat = DEFAULT_RUN_STATUS
    logger.trace("DEBUG genScrollDownUntilLoc...")
    this_step, step_words = genStepFillData("direct", "False", "position_reached", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_adjustment\nscroll_adjustment = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("position_reached != True", "", "", "scrollDown"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, smount, stepN):
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 50, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", page, section, theme, this_step, None)
    psk_words = psk_words + step_words


    # this step search for the lowest position of phrases "free shipping" on the bottom half of the screen, then scroll it to be 1 scroll away from the bottom of the page
    # this action will position the entire product section from image to free shipping ready to be extracted.
    # the whole purpose is that we don't want to do stiching on information pieces to form the complete information block.
    # lateron, this will have to be done somehow with the long review comments, but at in this page anyways.
    # screen, anchor, at_loc, target_loc, flag, resolution, stepN
    this_step, step_words = genStepSearchScroll("screen_info", "down", target_anchor, target_type, [20, 100], tilpos, "position_reached", "scroll_resolution", 0.5, site, adjust_val, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words

def genScrollDownUntil(target_anchor, target_type, page, section, stepN, worksettings, site, theme):
    psk_words = ""
    ex_stat = DEFAULT_RUN_STATUS
    logger.trace("DEBUG genScrollDownUntil...")
    this_step, step_words = genStepFillData("direct", "False", "position_reached", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_adjustment\nscroll_adjustment = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("position_reached != True", "", "", "scrollDown"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 70, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", page, section, theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", target_anchor, "direct", target_type, "any", "useless", "position_reached", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words

def genScrollUpUntilLoc(target_anchor, target_type, tilpos, page, section, adjust_val, stepN, worksettings, site, theme):
    psk_words = ""
    ex_stat = DEFAULT_RUN_STATUS
    logger.trace("DEBUG genScrollUpUntilLoc...")
    this_step, step_words = genStepFillData("direct", "False", "position_reached", "", stepN)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("position_reached != True", "", "", "scrollDown"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, smount, stepN):
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 50, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", page, section, theme, this_step, None)
    psk_words = psk_words + step_words


    # this step search for the lowest position of phrases "free shipping" on the bottom half of the screen, then scroll it to be 1 scroll away from the bottom of the page
    # this action will position the entire product section from image to free shipping ready to be extracted.
    # the whole purpose is that we don't want to do stiching on information pieces to form the complete information block.
    # lateron, this will have to be done somehow with the long review comments, but at in this page anyways.
    # screen, anchor, at_loc, target_loc, flag, resolution, stepN
    this_step, step_words = genStepSearchScroll("screen_info", "up", target_anchor, target_type, [35, 100], tilpos, "position_reached", "scroll_resolution", 0.5, site, adjust_val, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def genScrollUpUntil(target_anchor, target_type, page, section, stepN, worksettings, site, theme):
    psk_words = ""
    ex_stat = DEFAULT_RUN_STATUS
    logger.trace("DEBUG genScrollUpUntil...")
    this_step, step_words = genStepFillData("direct", "False", "position_reached", "", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global scroll_adjustment\nscroll_adjustment = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("position_reached != True", "", "", "scrollDown"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 70, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", page, section, theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", target_anchor, "direct", target_type, "any", "useless", "position_reached", "", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


def get_html_file_dir_loc(result):
    target_loc = [0, 0]

    target_name = "refresh"
    target_type = "anchor icon"
    # target_type = "anchor text"
    logger.info("result: "+json.dumps(result))
    # for e in result:
    #     logger.info(json.dumps(e))

    # now do the search
    targets_found = [element for index, element in enumerate(result) if
                     element["name"] == target_name and element["type"] == target_type]

    logger.info("targets_found: "+json.dumps(targets_found))
    if len(targets_found) > 0:
        # sort found by vertical location.
        refresh_icon_loc = targets_found[len(targets_found)-1]['loc']
        posX = int(refresh_icon_loc[1]) - (int(refresh_icon_loc[3]) - int(refresh_icon_loc[1]))*2
        posY = int(refresh_icon_loc[0]) + int((int(refresh_icon_loc[2]) - int(refresh_icon_loc[0]))/2)
        target_loc = [posX, posY]
    else:
        logger.error("ERROR: screen read unexpected FAILED TO FOUND DIR INPUT BOX")
        target_loc = [0, 0]

    logger.info("target_loc: "+json.dumps(target_loc))

    return target_loc


def get_html_file_name_loc(result):
    target_loc = [0, 0]
    target_name = "File name:"
    # target_type = "anchor icon"
    target_type = "anchor text"
    target_text1 = "name:"
    target_text2 = "name"

    logger.info("result: "+json.dumps(result))
    # now do the search
    targets_found = [element for index, element in enumerate(result) if
                     element["type"] == target_type and (re.search(target_text1, element["text"]) or re.search(target_text2, element["text"]))]

    logger.info("targets_found: "+json.dumps(targets_found))

    if len(targets_found) > 0:
        # sort found by vertical location.
        txt_loc = targets_found[len(targets_found)-1]["loc"]
        # txts_found = [txt for index, txt in enumerate(target_struct) if re.search(target_text, txt["text"])]
        # txt_loc = txts_found[len(txts_found)-1]['box']

        posY = txt_loc[0] + int((txt_loc[2] - txt_loc[0])/2)

        # X location should line up with Save button.
        save_loc = get_save_button_loc(result)
        if save_loc[0] > 0:
            posX = save_loc[0]
            target_loc = [posX, posY]
        else:
            target_loc = [0, 0]

    else:
        logger.error("ERROR: screen read unexpected FAILED TO FOUND FILE NAME INPUT BOX")
        target_loc = [0, 0]

    return target_loc


def get_save_button_loc(result):
    target_loc = [0, 0]
    target_name = "cancel"
    # target_type = "anchor icon"
    target_type = "anchor text"
    logger.info("result: "+json.dumps(result))

    # now do the search
    targets_found = [element for index, element in enumerate(result) if
                     element["name"] == target_name and element["type"] == target_type]

    logger.info("targets_found: "+json.dumps(targets_found))

    if len(targets_found) > 0:
        # sort found by vertical location.
        target_loc = targets_found[len(targets_found)-1]['loc']
        posX = target_loc[1] - int((target_loc[3] - target_loc[1])*2.25)
        posY = target_loc[0] + int((target_loc[2] - target_loc[0])/2)
        target_loc = [posX, posY]
    else:
        logger.error("ERROR: screen read unexpected FAILED TO FOUND SAVE BUTTON")
        target_loc = [0, 0]

    return target_loc


# save web page into html file.
def processSaveHtml(step, i, mission, skill):
    global screen_loc
    logger.info("Saving web page to a local html file ....."+json.dumps(step))
    ex_stat = DEFAULT_RUN_STATUS
    try:
        mainwin = mission.get_main_win()
        dtnow = datetime.now()

        date_word = dtnow.strftime("%Y%m%d")
        logger.info("date word:"+date_word)

        fdir = path_manager.get_log_path(mainwin.log_user, date_word)

        platform = mission.getPlatform()
        app = mission.getApp()
        site = mission.getSite()

        fdir = fdir + "b" + str(step["settings"]["mid"]) + "m" + str(step["settings"]["botid"]) + "/"
        # fdir = fdir + ppword + "/"
        fdir = fdir + platform + "_" + app + "_" + site + "_" + step["page"] + "/skills/"
        # fdir = fdir + skill.getName() + "/webpages/"
        fdir = fdir + skill.getName()

        hfile = fdir + "/" + step["local"]

        symTab[step["html_var"]] = hfile
        logger.info("hfile: "+hfile)


        # now save the web page into a file.
        pyautogui.hotkey('ctrl', 's')

        # wait till the dialog windows is shown on screen
        time.sleep(3)

        # now a file save dialog box will show up on screen, analyze it to figure out where to type and click.
        ni = processExtractInfo(step, i, mission, skill)

        # get ready the html file path and the file name
        html_file_dir_name = fdir
        logger.info("html_file_dir_name: "+html_file_dir_name)

        html_file_name = step["local"].split(".")[0]
        logger.info("html_file_name: "+html_file_name)


        # locate the html file directory path input text box
        html_file_dir_loc = get_html_file_dir_loc(symTab[step["data_sink"]])
        logger.info("html_file_dir_loc: "+json.dumps(html_file_dir_loc))
        pyautogui.moveTo(html_file_dir_loc[0]+screen_loc[0], html_file_dir_loc[1]+screen_loc[1])
        # pyautogui.click(clicks=2)
        pyautogui.click()
        time.sleep(2)
        for i in range(50):
            pyautogui.press('backspace')
        time.sleep(2)
        pyautogui.write(html_file_dir_name)
        time.sleep(5)
        pyautogui.press('enter')

        # locate the file name input text box
        html_file_name_loc = get_html_file_name_loc(symTab[step["data_sink"]])
        logger.info("html_file_name_loc: "+json.dumps(html_file_name_loc))
        pyautogui.moveTo(html_file_name_loc[0]+screen_loc[0], html_file_name_loc[1]+screen_loc[1])
        pyautogui.click()
        time.sleep(2)
        pyautogui.click()
        pyautogui.click(clicks=2)
        time.sleep(2)
        for i in range(50):
            pyautogui.press('backspace')
        pyautogui.write(html_file_name)
        time.sleep(2)
        # pyautogui.press('enter')

        # locate the save button
        save_button_loc = get_save_button_loc(symTab[step["data_sink"]])
        logger.info("save_button_loc: "+json.dumps(save_button_loc))
        pyautogui.moveTo(save_button_loc[0]+screen_loc[0], save_button_loc[1]+screen_loc[1])
        time.sleep(2)
        pyautogui.click()

        # give enough to save html, as it could take some time.
        time.sleep(65)

    # ni is already incremented by processExtract(), so simply return it.
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSaveHtml:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSaveHtml: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return ni, ex_stat


def processCheckAppRunning(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["result"]] = False
    try:
        if sys.platform == 'win32':
            names = []

            def winEnumHandler(hwnd, ctx):
                if win32gui.IsWindowVisible(hwnd):
                    n = win32gui.GetWindowText(hwnd)
                    # logger.info("windows: "+str(n))
                    if n:
                        names.append(n)

            win32gui.EnumWindows(winEnumHandler, None)

            for win_name in names:
                if step["appname"] in win_name:
                    symTab[step["result"]] = True
                    break

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckAppRunning:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckAppRunning: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

def switchToWindow(winTitleKW):
    successful = False
    window_handle = None
    win_title = ""
    winInfo = None
    win_rect = None
    if sys.platform == 'win32':
        names = []

        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                n = win32gui.GetWindowText(hwnd)
                # logger.info("windows: "+str(n))
                if n:
                    names.append(n)

        win32gui.EnumWindows(winEnumHandler, None)
        win_title_keyword = winTitleKW

        effective_names = [nm for nm in names if "dummy" not in nm]
        window_handle = None
        if win_title_keyword:
            for wi, wn in enumerate(effective_names):
                if win_title_keyword in wn:
                    win_title = effective_names[wi]
                    window_handle = win32gui.FindWindow(None, effective_names[wi])
                    win_rect = win32gui.GetWindowRect(window_handle)
                    logger.info("FOUND target window: " + win_title + " rect: " + json.dumps(win_rect))
                    break


        # Bring the window to the foreground
        if window_handle:
            # Restore if minimized
            if win32gui.IsIconic(window_handle):
                win32gui.ShowWindow(window_handle, win32con.SW_RESTORE)

            ctypes.windll.user32.AllowSetForegroundWindow(-1)

            win32gui.ShowWindow(window_handle, win32con.SW_RESTORE)  # Restore window if minimized
            win32gui.SetForegroundWindow(window_handle)
            successful = True
        else:
            logger.error(f"Error: Window with title '{win_title_keyword}' not found.")

        winInfo = { "title": win_title, "handle": window_handle, "rect": win_rect}

    return successful, winInfo


def getTopWindow():
    winInfo = None
    if sys.platform == 'win32':
        names = []

        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                n = win32gui.GetWindowText(hwnd)
                # logger.info("windows: "+str(n))
                if n:
                    names.append(n)

        win32gui.EnumWindows(winEnumHandler, None)

        effective_names = [nm for nm in names if "dummy" not in nm]
        winInfo = { "title": effective_names[0] }
        top_win_title = effective_names[0]
        window_handle = win32gui.FindWindow(None, top_win_title)
        win_rect = win32gui.GetWindowRect(window_handle)
        winInfo["handle": window_handle]
        winInfo["rect": win_rect]

    return winInfo



def getWindows():
    winInfo = []
    if sys.platform == 'win32':
        names = []

        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                n = win32gui.GetWindowText(hwnd)
                # logger.info("windows: "+str(n))
                if n:
                    names.append(n)

        win32gui.EnumWindows(winEnumHandler, None)

        effective_names = [nm for nm in names if "dummy" not in nm]

        for wi, wn in enumerate(effective_names):
            win_title = effective_names[wi]
            window_handle = win32gui.FindWindow(None, effective_names[wi])
            win_rect = win32gui.GetWindowRect(window_handle)

            if window_handle:
                 winInfo.append({"title": win_title, "handle": window_handle, "rect": win_rect})

    return winInfo




def processGetTopWindow(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True

    try:
        symTab[step["result"]]= getTopWindow()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGetTopWindow:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGetTopWindow: traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat




def processGetAllWindowsInfo(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True

    try:
        symTab[step["result"]]= getWindows()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGetAllWindowsInfo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGetAllWindowsInfo: traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False

    return (i + 1), ex_stat





def processBringAppToFront(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True
    winTitleKW = step["win_title_kw"]

    try:
        symTab[step["flag"]], symTab[step["win_info"]] = switchToWindow(winTitleKW)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorBringAppToFront:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorBringAppToFront: traceback information not available:" + str(e)
        logger.error(ex_stat)
        symTab[step["flag"]] = False
        symTab[step["win_info"]] = None

    return (i + 1), ex_stat


# "type"
# "goals"
# "options"
# "products"
# "msgs_and_orders"
# "msg_responses"
# "flag"
def processThink(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True
    dtnow = datetime.now()

    date_word = dtnow.isoformat()
    try:
        # goals is a json converted string, the json is of the following format:
        # { "pass_method": "", "total_score": 0, "passing_score": 0, goals":[{"name": "xxx", "type": "xxx", "mandatory": true/false, "score": "", "standards": number/set of string, "weight": 1, passed": true/false}....]
        # each individual goal "name" could be "customer service", "procure web search","procure chat","sales chat", "test", if set goal name to "test", this
        # will get a simple echo back of whatever message sent upstream.
        # background could the thread up to the latest message, msg is the latest message
        # background is also a json converted string. in terms of chat or messaging, the json is of the following format:
        # {"orderID": "", "thread": [{"time stamp": yyyy-mm-dd hh:mm:ss, "from": "", "msg txt": "", "attachments": ["",...], }....]}

        user = "m"+str(mission.getMid())+"b"+str(mission.getBid())

        qs = [{
            "msgID": "1",
            "user": user,
            "timeStamp": date_word,
            "products": json.dumps(symTab[step["products"]]).replace('"', '\\"'),
            "goals": step["goals"],
            "options": json.dumps(symTab[step["options"]]).replace('"', '\\"'),
            "background": json.dumps(symTab[step["sys_prompt"]]).replace('"', '\\"'),
            "msg": symTab[step["user_prompt"]]
        }]
        settings = mission.main_win_settings

        mainwin = mission.get_main_win()
        symTab[step["response"]] = send_query_chat_request_to_cloud(settings["session"], settings["token"], qs, mainwin.getWanApiEndpoint())


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorThink:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorThink: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


async def processThink8(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True
    dtnow = datetime.now()

    date_word = dtnow.isoformat()
    try:
        # goals is a json converted string, the json is of the following format:
        # { "pass_method": "", "total_score": 0, "passing_score": 0, goals":[{"name": "xxx", "type": "xxx", "mandatory": true/false, "score": "", "standards": number/set of string, "weight": 1, passed": true/false}....]
        # each individual goal "name" could be "customer service", "procure web search","procure chat","sales chat", "test", if set goal name to "test", this
        # will get a simple echo back of whatever message sent upstream.
        # background could the thread up to the latest message, msg is the latest message
        # background is also a json converted string. in terms of chat or messaging, the json is of the following format:
        # {"orderID": "", "thread": [{"time stamp": yyyy-mm-dd hh:mm:ss, "from": "", "msg txt": "", "attachments": ["",...], }....]}
        user = "m"+str(mission.getMid())+"b"+str(mission.getBid())
        qs = [{
            "msgID": "1",
            "user": user,
            "timeStamp": date_word,
            "products": json.dumps(symTab[step["products"]]).replace('"', '\\"'),
            "goals": step["goals"],
            "options": json.dumps(symTab[step["options"]]).replace('"', '\\"'),
            "background": json.dumps(symTab[step["msgs_and_orders"]]).replace('"', '\\"'),
            "msg": "provide answer"
        }]
        settings = mission.main_win_settings
        mainwin = mission.get_main_win()
        symTab[step["response"]] = await send_query_chat_request_to_cloud8(settings["session"], settings["token"], qs, mainwin.getWanApiEndpoint())


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorThink:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorThink: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat



def processGenRespMsg(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["result"]] = True
    dtnow = datetime.now()

    date_word = dtnow.isoformat()
    try:
        if symTab[step["response"]] == "complain":
            print("respond:")
        elif symTab[step["response"]] == "complain":
            print("respond:")

        qs = [{"msgID": "1", "bot": str(mission.botid), "timeStamp": date_word, "product": symTab[step["products"]],
               "goals": step["setup"], "background": "", "msg_thread": symTab[step["query"]]}]
        settings = mission.main_win_settings

        mainwin = mission.get_main_win()
        symTab[step["response"]] = send_query_chat_request_to_cloud(settings["session"], settings["token"], qs, mainwin.getWanApiEndpoint())


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGenRespMsg:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGenRespMsg: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

def find_original_buy(mainwin, buy_mission):
    # Construct the SQL query with a parameterized IN clause
    mainwin.showMsg("find_original_buy ......")
    if mainwin.mission_service:
        db_data = mainwin.mission_service.find_missions_by_ticket(buy_mission.getTicket())
    else:
        db_data = []
    allMids = [m.getMid() for m in mainwin.missions]
    mainwin.showMsg("same ticket missions: " + json.dumps(db_data))
    if db_data:
        if db_data["mid"] in allMids:
            original_buy_mission = next((m for m in mainwin.missions if m.getMid() == db_data["mid"] ), None)
        else:
            original_buy_mission = EBMISSION(mainwin)
            original_buy_mission.loadDBData(db_data[0])
            mainwin.mission.append(original_buy_mission)
    else:
        print("warning: dbData not found")
        original_buy_mission = next((m for m in mainwin.missions if m.getMid() == buy_mission.getTicket()), None)

    return original_buy_mission


def processUpdateBuyMissionResult(step, i, this_buy_mission):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        mainwin = this_buy_mission.get_main_win()

        this_buy_mission.setResult(symTab[step["result"]])
        original_buy_mission = find_original_buy(mainwin, this_buy_mission)
        if original_buy_mission:
            original_buy_mission.setResult(symTab[step["result"]])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorUpdateBuyMissionResult:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorUpdateBuyMissionResult: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

# this function takes a list of shipping labels and check to see whether they have arrived. use API?
def processSellCheckShipping(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        midx = next((i for i, mission in enumerate(step["mainwin"].missions) if str(mission.getMid()) == symTab[step["mid_var"]]), -1)
        if midx >= 0:
            this_buy_mission = step["mainwin"].missions[midx]
            this_buy_mission.setResult(symTab[step["mid_var"]])
            original_buy_mission = find_original_buy(step["mainwin"], this_buy_mission)
            original_buy_mission.setResult(symTab[step["mid_var"]])
        else:
            ex_stat = "ErrorUpdateBuyMissionResult:"+str(symTab[step["mid_var"]])+" mission NOT found."
            logger.error(ex_stat)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSellCheckShipping:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSellCheckShipping: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processGoToWindow(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        win_names = list_windows()
        found = [win_name for win_name in win_names if step["win_name"] in win_name]
        print("found taget window:", found)
        if len(found) > 0:
            hwnd = win32gui.FindWindow(None, found[0])
            print("setting foreground window", hwnd)
            win32gui.SetForegroundWindow(hwnd)

            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            fg_window = win32gui.GetForegroundWindow()

            if fg_window != hwnd:
                current_thread = win32api.GetCurrentThreadId()
                fg_thread, _ = win32process.GetWindowThreadProcessId(fg_window)
                target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

                # Attach the input processing mechanism of the current thread to the input processing mechanism of another thread
                win32process.AttachThreadInput(current_thread, target_thread, True)

                # Bring the window to the foreground
                win32gui.SetForegroundWindow(hwnd)
                win32gui.SetFocus(hwnd)

                # Detach the input processing mechanism of the current thread from the input processing mechanism of another thread
                win32process.AttachThreadInput(current_thread, target_thread, False)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGoToWindow:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGoToWindow: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

# find the network link transport of the commander-platoon link by the platoon's IP address.
def get_commander_link_by_ip(ip):
    global login
    return login.get_mainwin().commanderXport


# this function sends some logging logging message to the commander, that a commander can see what's going on remotely via TCP/IP
def processReportToBoss(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        msg = "{\"ip\": \"" + step["self_ip"] + "\", \"type\":\"exlog\", \"content\":\"" + json.dumps(step["exlog_data"]).replace('"', '\\"') +"\"}"
        # send to commander
        commander_link = get_commander_link_by_ip(step["self_ip"])
        if commander_link:
            commander_link.write(msg.encode('utf8'))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSellCheckShipping:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSellCheckShipping: traceback information not available:" + str(e)
        logger.error(ex_stat)

    return (i + 1), ex_stat

def updateIconScalesDict(machine_name, sk_name, log_user, page, section, screen_data):
    all_icons = [x for x in screen_data if (x["type"] == "anchor icon")]
    print("all icons with scale factors to be saved: ", all_icons)
    icon_scales = []
    icon_scale_data = {}
    print("updating icon_match_dict:", icon_match_dict)
    if len(all_icons) > 0:
        # build up an empty dictionary if needed.
        if machine_name not in icon_match_dict:
            icon_match_dict[machine_name] = {sk_name: {page: {section: {}}}}
        elif sk_name not in icon_match_dict[machine_name]:
            icon_match_dict[machine_name][sk_name] = {page: {section: {}}}
        elif page not in icon_match_dict[machine_name][sk_name]:
            icon_match_dict[machine_name][sk_name][page] = {section: {}}
        elif section not in icon_match_dict[machine_name][sk_name][page]:
            icon_match_dict[machine_name][sk_name][page][section] = {}

        uniq_icon_names = list(icon_match_dict[machine_name][sk_name][page][section].keys())

        for icon in all_icons:
            if icon["name"] not in uniq_icon_names:
                icon_match_dict[machine_name][sk_name][page][section][icon["name"]] = [icon["scale"]]
            else:
                if icon["scale"] not in icon_match_dict[machine_name][sk_name][page][section][icon["name"]]:
                    icon_match_dict[machine_name][sk_name][page][section][icon["name"]].append(icon["scale"])

        # save the updated to a file.
        run_experience_file = ecb_data_homepath + f"/{log_user}/run_experience.txt"
        print("run_experience_file: "+run_experience_file)
        print("icon match dict: ", icon_match_dict)
        with open(run_experience_file, 'w') as fileTBSaved:
            json.dump(icon_match_dict, fileTBSaved, indent=4)
            fileTBSaved.close()


def findAndFormIconScaleFactors(machine_name, sk_name, page, section, icon_names):
    icon_scale_option = "{}"
    found_icon_scales = {}
    # print("finding scale from:", machine_name, sk_name, page, section)
    # print("current icon_match_dict:", icon_match_dict)
    if machine_name in icon_match_dict:
        if sk_name in icon_match_dict[machine_name]:
            if page in icon_match_dict[machine_name][sk_name]:
                if section in icon_match_dict[machine_name][sk_name][page]:
                    icon_scales = icon_match_dict[machine_name][sk_name][page][section]
                    found_icon_names = [x for x in icon_names if x in icon_scales]
                    if len(found_icon_names) > 0:
                        for icon_name in found_icon_names:
                            found_icon_scales[icon_name] = [round(float(x), 2) for x in icon_scales[icon_name]]
                        icon_scale_option = json.dumps(found_icon_scales).replace('"', '\\"')
                        print("found previous icon scale factors:", icon_scale_option)

    print("formed icon scale option:", icon_scale_option)
    return icon_scale_option


def get_csk_icon_names(skill, page, section):
    icon_names = []
    csk_file_name = skill.getCskFileName()
    csk_json = None
    print("checking csk file:", skill.getSkid(), csk_file_name)
    if os.path.exists(csk_file_name):
        with open(csk_file_name, 'rb') as csk_file:
            csk_json = json.load(csk_file)
            csk_file.close()
    # print("read csk json:", page, section, csk_json)
    if csk_json:
        for page_section in csk_json:
            if page in page_section:
                if section in page_section[page]:
                    # print("read page section of csk json:", page_section[page][section])
                    icon_names = [x["anchor_name"] for x in page_section[page][section]["anchors"] if x["anchor_type"] == "icon"]
                    break

    print("csk icon names:", icon_names)
    return icon_names


def processCalcObjectsDistance(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["flag"]] = True
    symTab[step["result"]] = -1

    try:
        logger.info("calculating object distance")
        if step["distance_type"] == "min":
            if step["distance_dir"] == "vertical":              # always assume obj1 is above obj2
                # find the lowest of obj1 and highest of obj2
                # print("obj_name1:", step["obj_name1"], symTab[step["obj_name1"]])
                # print("obj_name2:", step["obj_name2"], symTab[step["obj_name2"]])
                vsorted1 = sorted(symTab[step["obj_name1"]], key=lambda x: x["loc"][2], reverse=True)
                vsorted2 = sorted(symTab[step["obj_name2"]], key=lambda x: x["loc"][0], reverse=False)
                logger.info("calc min vertical gap:"+json.dumps(vsorted1[0]["loc"])+", "+json.dumps(vsorted2[0]["loc"]))
                op1 = vsorted1[0]["loc"][2]
                op2 = vsorted2[0]["loc"][0]
            elif step["distance_dir"] == "horizontal":          # always assume obj1 is to the left of obj2
                # find the right mostobj1 and left most obj2, then calculate the distance.
                hsorted1 = sorted(symTab[step["obj_name1"]], key=lambda x: x["loc"][3], reverse=True)
                hsorted2 = sorted(symTab[step["obj_name2"]], key=lambda x: x["loc"][1], reverse=False)
                logger.info("calc min horizontal gap:" + json.dumps(hsorted1[0]["loc"]) + ", " + json.dumps(hsorted2[0]["loc"]))
                op1 = hsorted1[0]["loc"][3]
                op2 = hsorted2[0]["loc"][1]
        elif step["distance_type"] == "max":
            if step["distance_dir"] == "vertical":              # always assume obj1 is above obj2
                # find the highest of obj1 and lowest of obj2
                vsorted1 = sorted(symTab[step["obj_name1"]], key=lambda x: x["loc"][2], reverse=False)
                vsorted2 = sorted(symTab[step["obj_name2"]], key=lambda x: x["loc"][0], reverse=True)
                logger.info("calc max vertical gap:" + json.dumps(vsorted1[0]["loc"]) + ", " + json.dumps(vsorted2[0]["loc"]))
                op1 = vsorted1[0]["loc"][2]
                op2 = vsorted2[0]["loc"][0]
            elif step["distance_dir"] == "horizontal":          # always assume obj1 is to the left of obj2
                # find the left most mostobj1 and right most obj2, then calculate the distance.
                hsorted1 = sorted(symTab[step["obj_name1"]], key=lambda x: x["loc"][3], reverse=False)
                hsorted2 = sorted(symTab[step["obj_name2"]], key=lambda x: x["loc"][1], reverse=True)
                logger.info("calc max horizontal gap:" + json.dumps(hsorted1[0]["loc"]) + ", " + json.dumps(hsorted2[0]["loc"]))
                op1 = hsorted1[0]["loc"][3]
                op2 = hsorted2[0]["loc"][1]

        symTab[step["result"]] = op2 - op1
        logger.info("calced gap:" + str(symTab[step["result"]]))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCalcObjectsDistance:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCalcObjectsDistance: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


# this instruction is specific to amazon product details page, it look at info found on a screen
# and determines whether this screen is before/after/on/unknown the ASIN or Review Section information on the page.
def processAmzDetailsCheckPosition(step, i):
    ex_stat = DEFAULT_RUN_STATUS

    check_dict = {
        "asin": {"before": ["product_info", "product_details", "bought_together"], "after": ["similar_items", "star", "reviewed", "related_to", "also_bought", "also_viewed", "back_to_top", "conditions_of_use"]},
        "reviewed": {"before": [], "after": ["also_bought", "reviewed", "also_viewed", "review_helpful", "see_more_reviews", "see_all_reviews", "back_to_top", "conditions_of_use"]}
    }
    try:
        logger.info("check position:"+step["marker_name"])
        scrn = symTab[step["screen"]]

        symTab[step["result"]] = "unknown"

        ancs = [x for x in scrn if x["type"] == "anchor text"]
        anc_names = [x["name"] for x in ancs]
        # if "asin" in anc_names:
        if False:
            symTab[step["result"]] = "on"
        else:
            before_match = [x for x in ancs if x["name"] in check_dict[step["marker_name"]]["before"]]
            after_match = [x for x in ancs if x["name"] in check_dict[step["marker_name"]]["after"]]

            print("before_match:", before_match)
            print("after_match:", after_match)

            if len(before_match) > len(after_match):
                symTab[step["result"]] = "before"
            elif len(before_match) < len(after_match):
                symTab[step["result"]] = "after"


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAmzDetailsCheckPosition:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAmzDetailsCheckPosition: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat

# calculate number of columns from a Amazon product list page screen shot
# assumption: this screen shot is at the top of the page with sponsored and free delivery info as the markers.
def processAmzPLCalcNCols(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = True

        # for deliveries, columnize them, and remove the in-paragrph duplicates.
        delivery_hsorted = sorted(symTab[step["deliveries"]], key=lambda x: x["loc"][1], reverse=False)
        prev_x = -1000
        delivery_width = delivery_hsorted[0]["loc"][3] - delivery_hsorted[0]["loc"][1]
        print("first delivery loc:", delivery_width, delivery_hsorted)

        in_par_deliveries = []
        for delivery in delivery_hsorted:
            if delivery["loc"][1] - prev_x > delivery_width * 3.25:
                in_par_deliveries.append(delivery)
                prev_x = delivery["loc"][1]

        print("delivery in paragraphs:", in_par_deliveries)

        nd = len(in_par_deliveries)
        logger.info("to be check carts:" + json.dumps(symTab[step["carts"]]))
        if len(symTab[step["sponsors"]]) > 0:
            if len(symTab[step["carts"]]) > 0:
                carts_vsorted = sorted(symTab[step["carts"]], key=lambda x: x["loc"][0], reverse=False)

                line_height = carts_vsorted[0]["loc"][2]-carts_vsorted[0]["loc"][0]
                last_vloc = carts_vsorted[0]["loc"][0]
                carts_rows = []
                carts_row = []
                for spi, sp in enumerate(carts_vsorted):
                    if abs(carts_vsorted[spi]["loc"][0] - last_vloc) > 6*line_height:
                        carts_rows.append(carts_row)
                        carts_row=[]

                    last_vloc = carts_vsorted[spi]["loc"][0]
                    carts_row.append(sp)

                carts_rows.append(carts_row)      #get the final row.
                logger.info("carts rows:" + json.dumps(carts_rows))

                longest_carts_row = max(carts_rows, key=len)
                logger.info("longest carts row:" + json.dumps(longest_carts_row))
            else:
                longest_carts_row = []

            if len(symTab[step["options"]]) > 0:
                ops_vsorted = sorted(symTab[step["options"]], key=lambda x: x["loc"][0], reverse=False)

                line_height = ops_vsorted[0]["loc"][2] - ops_vsorted[0]["loc"][0]
                last_vloc = ops_vsorted[0]["loc"][0]
                ops_rows = []
                ops_row = []
                for spi, sp in enumerate(ops_vsorted):
                    if abs(ops_vsorted[spi]["loc"][0] - last_vloc) > 6 * line_height:
                        ops_rows.append(ops_row)
                        ops_row = []

                    last_vloc = ops_vsorted[spi]["loc"][0]
                    ops_row.append(sp)

                ops_rows.append(ops_row)  # get the final row.
                logger.info("options rows:" + json.dumps(ops_rows))

                longest_op_row = max(ops_rows, key=len)
                logger.info("longest ops row:" + json.dumps(longest_op_row))
            else:
                longest_op_row = []

            if len(longest_carts_row) + len(longest_op_row) < nd:
                symTab[step["result"]] = nd
            else:
                symTab[step["result"]] = len(longest_carts_row) + len(longest_op_row)

        else:
            longest_carts_row = []
            longest_op_row = []
            symTab[step["flag"]] = False
            symTab[step["result"]] = 0

        logger.info("num columns:" + str(symTab[step["result"]]))


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAmzPLCalcNCols:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAmzPLCalcNCols: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat



def startSaveCSK(endpoint, csk_dir, session, token):
    print("hello????")
    loop = asyncio.new_event_loop()
    print("hohohohohoh????")
    loop.run_until_complete(saveCSKToCloud(endpoint, csk_dir, session, token))

# def on_upload_button_click(loop, csk_dir):
#     threading.Thread(target=start_upload, args=(loop, csk_dir), daemon=True).start()


async def saveCSKToCloud(endpoint, csk_dir, session, token):
    try:
        images_dir = os.path.join(csk_dir, 'images')
        scripts_dir = os.path.join(csk_dir, 'scripts')

        image_files = [
            (os.path.join(images_dir, file), "anchor")
            for file in os.listdir(images_dir) if file.endswith('.png')
        ]

        script_files = [
            (os.path.join(scripts_dir, file), "csk")
            for file in os.listdir(scripts_dir) if file.endswith('.csk')
        ]

        tasks = [upload_file8(session, file, token, endpoint, ftype) for (file, ftype) in image_files + script_files]

        await asyncio.gather(*tasks)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSaveCSKToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSaveCSKToCloud: traceback information not available:" + str(e)
        logger.error(ex_stat)


def processMoveDownloadedFileToDestination(step, i):
        ex_stat = DEFAULT_RUN_STATUS

        try:
            default_download_dir = getDefaultDownloadDirectory()

            new_file = getMostRecentFile(default_download_dir, prefix=step["prefix"], extension=step["extension"])

            destination_file = os.path.join(symTab[step["destination"]], os.path.basename(new_file))
            shutil.move(new_file, destination_file)

            symTab[step["result"]] = destination_file


        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorMoveDownloadedFileToDestination:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorMoveDownloadedFileToDestination: traceback information not available:" + str(e)
            symTab[step["flag"]] = False
            logger.error(ex_stat)

        return (i + 1), ex_stat


def getDefaultDownloadDirectory():
    if platform.system() == "Windows":
        download_dir = os.path.join(os.environ['USERPROFILE'], 'Downloads')
    else:
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads')

    return download_dir


def getMostRecentFile(download_dir, prefix="", extension="pdf"):
    pattern = os.path.join(download_dir, f"{prefix}*."+extension)
    list_of_files = glob.glob(pattern)

    if not list_of_files:
        return None

    most_recent_file = max(list_of_files, key=os.path.getctime)
    return most_recent_file


global hil_queue
WAIT_HIL_RESPONSE = "Waiting For Human"
async def processReqHumanInLoop(step, i, mission, hq):
        ex_stat = DEFAULT_RUN_STATUS

        try:
            msg = {}
            # send request to cloud
            settings = mission.main_win_settings
            response = wanSendRequestSolvePuzzle(msg, settings["token"])

            # put request into queue
            # add time stamp to
            asyncio.create_task(hq.put(msg))

            # starts a time


            #setting the state here will suspend.
            ex_stat = WAIT_HIL_RESPONSE

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorMoveDownloadedFileToDestination:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorMoveDownloadedFileToDestination: traceback information not available:" + str(e)
            symTab[step["flag"]] = False
            logger.error(ex_stat)

        return (i + 1), ex_stat




# this is not really a step, some kind of internal step in the sense, it will
# 1) execute human suggested action in the message,
# 2) run an extract info step, the result of it will be picked up by actual skill step instructions.
# 3) find corresponding queued HIL request message, and compare i) time limit ii) expected after effect
#    if successful, then:
#      a) send the confirmation out to cloud side
#      b) dequeue the HIL request,
#      c) resume instruction execution
#    else:
#      a) still send confimration out to cloud (with failure status)
#      b) retry -
#
#
# msg{} format:
#   {  "action": "key"/"clicks"/"drags", "key": "text", "clicks": [{"loc": [], "wait": 1},...], "drags": [{"loc":[], "wait":0}...] }
def processCloseHumanInLoop(step, i, mission, hq):
    ex_stat = DEFAULT_RUN_STATUS

    try:
        # dequeue the HIL item
        settings = mission.main_win_settings
        logger.info("Close the HIL Loop")
        msg = {}
        #
        # put back the program counter.
        response = wanSendConfirmSolvePuzzle(msg, settings["token"])
        #


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorMoveDownloadedFileToDestination:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorMoveDownloadedFileToDestination: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat

#         "file_name_type": file_name_type,
#         "file_name": file_name,
#         "result": result_var,
#         "flag": flag_var
def processReadJsonFile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global json_file
    try:
        if step["file_name_type"] == "direct":
            json_file = step["file_name"]
        elif step["file_name_type"] == "var":
            json_file = symTab[step["file_name"]]
        elif step["file_name_type"] == "expr":
            exec("global json_file\njson_file = "+step["file_name"]+"\nprint('json_file',json_file)")
            # exec("json_file = "+step["file_name"]+"\nprint('json_file',json_file)")

        print("reading json file:", json_file)

        if os.path.exists(json_file):
            with open(json_file, 'rb') as jf:
                raw_data = jf.read()
                encoding_result = chardet.detect(raw_data)
                detected_encoding = encoding_result['encoding']

            with open(json_file, 'r', encoding=detected_encoding) as jf:
                symTab[step["result"]] = json.load(jf)
                jf.close()


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReadJsonFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorReadJsonFile: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processReadXlsxFile(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global json_file
    try:
        if step["file_name_type"] == "direct":
            json_file = step["file_name"]
        elif step["file_name_type"] == "var":
            json_file = symTab[step["file_name"]]
        elif step["file_name_type"] == "expr":
            exec("global json_file\njson_file = "+step["file_name"]+"\nprint('json_file',json_file)")
            # exec("json_file = "+step["file_name"]+"\nprint('json_file',json_file)")

        print("reading xlsx file:", json_file)

        if os.path.exists(json_file):
            # with open(json_file, 'rb') as jf:
            df = lazy.pd.read_excel(json_file, engine='openpyxl')

            # Convert the DataFrame to a list of dictionaries (JSON objects)
            symTab[step["result"]] = df.to_dict(orient='records')
            symTab[step["flag"]] = True
            print("read xlsx reslt data", symTab[step["result"]])
        else:
            print("ERROR, file not found."+json_file)
            symTab[step["result"]] = None
            symTab[step["flag"]] = False

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReadXlsxFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorReadXlsxFile: traceback information not available:" + str(e)
        symTab[step["result"]] = None
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processGetDefault(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global json_file
    try:
        if step["var_name"] == "download dir":
            symTab[step["result"]] = getDefaultDownloadDirectory()
            print("get default::", step["result"], symTab[step["result"]])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReadXlsxFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorReadXlsxFile: traceback information not available:" + str(e)
        # symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processKillProcesses(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = True

        if type(step['process_name']) == list:
            target_names = step['process_name']
        else:
            target_names = [symTab[['process_name']]]
        print("target names:", target_names)
        for proc in psutil.process_iter():
            # Check if process name contains 'chrome'
            if proc.name().lower() in target_names:
                print("process to be killed:", proc.name())
                proc.kill()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorKillProcesses:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorKillProcesses: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processCheckSublist(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = False
        main_list = symTab[step['main_list']]
        sub_list = symTab[step['sub_list']]

        main_len = len(main_list)
        sub_len = len(sub_list)

        # Track the position of where we are in the sub_list
        sub_index = 0

        for main_item in main_list:
            # Compare the current element in the main list with the current element in the sub list
            if not DeepDiff(main_item, sub_list[sub_index], ignore_order=True):
                # If they match, move to the next element in the sub list
                sub_index += 1
                # If we've matched all elements in the sub list, return True
                if sub_index == sub_len:
                    symTab[step["flag"]] = True
                    break

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckSublist:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckSublist: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def load_json_files(directory):
    json_data = []
    # os.walk generates the file names in a directory tree, recursively
    for root, dirs, files in os.walk(directory):
        # print("checking files:", files)
        for filename in files:

            if filename.endswith(".json"):
                file_path = os.path.join(root, filename)
                with open(file_path, 'r') as json_file:
                    data = json.load(json_file)
                    json_data.append({"data": data, "file": file_path})
    print("json data and files:", json_data)
    return json_data

def processCheckAlreadyProcessed(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag"]] = False
        found_file = ""
        in_list = symTab[step['in_list']]
        record_dir = symTab[step['record_dir']]

        processed = load_json_files(record_dir)
        # print("in_list:", in_list)
        # print("found json:", processed)

        if processed:
            for shipping_info in in_list[:]:  # Iterate through selenium_shipping_info
                found = False
                for data in processed:
                    if data["data"].get("paid") is True:
                        orders = data["data"].get("orders", [])
                        for order in orders:
                            if DeepDiff(order, shipping_info, ignore_order=True) == {}:
                                found = True
                                found_file = data["file"]
                                print("Found match:", shipping_info)
                                break
                    if found:
                        break
                # If a matching order is found, remove the item from selenium_shipping_info
                if found:
                    print("removing matched...")
                    in_list.remove(shipping_info)

            if not in_list:
                symTab[step["flag"]] = True
                symTab[step["result"]] = found_file
                print("all found meaning already processed.", symTab[step["result"]])
            else:
                print("orders not yet processed.")


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckAlreadyProcessed:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckAlreadyProcessed: traceback information not available:" + str(e)
        symTab[step["flag"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def setMissionInput(input):
    symTab["fin"] = input


def regSteps(stepType, stepData, start, result, mainWin):

    steps = [
        {
            "type": stepType,
            "data": stepData,
            "start_time": start,           # in milliseconds
            "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            "result": result
        }
    ]
    #upload screen to S3
    resp = send_reg_steps_to_cloud(mainWin.session, steps, mainWin.get_auth_token(), mainWin.getWanApiEndpoint())


def processPasteToData(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag_var"]] = True
        symTab[step["result_var"]] =  pyperclip.paste()
        print("pasted:", symTab[step["result_var"]])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckAlreadyProcessed:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckAlreadyProcessed: traceback information not available:" + str(e)
        symTab[step["flag_var"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processMouseMove(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    mainwin = mission.get_main_win()
    try:
        if (not step["x_destination_var"]) and (not step["y_destination_var"]):
            # this is the case of move
            pyautogui.move(symTab[step["x_amount_var"]], symTab[step["y_amount_var"]])
        else:
            # this is the case of move to -
            pyautogui.moveTo(symTab[step["x_destination_var"]], symTab[step["y_destination_var"]])

        time.sleep(step["postwait"])

        if step["breakpoint"]:
            input("type any key to continuue")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorMouseMove:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorMouseMove: traceback information not available:" + str(e)
        symTab[step["flag_var"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat

def processGetWindowsInfo(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag_var"]] = True
        found_wins = []
        if sys.platform == 'win32':
            names = []

            def winEnumHandler(hwnd, ctx):
                if win32gui.IsWindowVisible(hwnd):
                    n = win32gui.GetWindowText(hwnd)
                    # logger.info("windows: "+str(n))
                    if n:
                        names.append(n)

            win32gui.EnumWindows(winEnumHandler, None)

            logger.info("TOP5 WINDOWS:" + ",".join(names[0:5]))
            effective_names = [nm for nm in names if "dummy" not in nm and "Remote Desktop" not in nm]
            print("effective_names--", effective_names)
            found = False
            if isinstance(step["nth_var"], str):
                for wi, wn in enumerate(effective_names):
                    win_title = effective_names[wi]
                    window_handle = win32gui.FindWindow(None, effective_names[wi])
                    win_rect = win32gui.GetWindowRect(window_handle)
                    found_wins.append({"title": win_title, "rect": win_rect})

            else:
                # set to default top window
                nth = step["nth_var"]
                win_title = effective_names[nth]
                print("win name2: ", nth, effective_names[nth])
                window_handle = win32gui.FindWindow(None, effective_names[nth])
                win_rect = win32gui.GetWindowRect(window_handle)
                logger.info("default top window: " + names[nth] + " rect: " + json.dumps(win_rect))
                found_wins.append({"title": names[nth], "rect": win_rect})

        symTab[step["results_var"]] = found_wins
        print("windows info:", found_wins)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorWindowsInfo:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorWindowsInfo: traceback information not available:" + str(e)
        symTab[step["flag_var"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat



def processBringWindowToFront(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        symTab[step["flag_var"]] = True
        # Find the window by its title
        target_window = lazy.gw.getWindowsWithTitle(symTab[step["title_var"]])[0]

        # Activate the window (bring it to front)
        target_window.activate()

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorBringWindowToFront:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorBringWindowToFront: traceback information not available:" + str(e)
        symTab[step["flag_var"]] = False
        logger.error(ex_stat)

    return (i + 1), ex_stat


def processExternalHook(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        script_prefix = "none"
        script_file = "none"
        # Determine the script file name
        if step["file_name_type"] == "direct":
            script_file = step["file_name"]
            script_prefix = step["file_path"]
        elif step["file_name_type"] == "var":
            script_file = symTab[step["file_name"]]
            script_prefix = symTab[step["file_path"]]
        elif step["file_name_type"] == "expr":
            exec("global script_path\nscript_file = " + step["file_name"])
            exec("global script_prefix\nscript_prefix = " + step["file_path"])

        print("script file prefix:", script_prefix, script_file)
        script_path = script_prefix + "/" + script_file
        print(f"Attempting to execute external script: {script_path}")

        # Check if the file exists
        if not os.path.exists(script_path):
            print(f"Script file not found: {script_path}. Skipping...")
            symTab[step["result"]] = "Script file not found!"
            symTab[step["flag"]] = False
            return (i + 1), ex_stat  # Skip gracefully

        # Load and execute the script dynamically
        spec = importlib.util.spec_from_file_location("external_hook", script_path)
        external_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(external_module)

        # Call the `run` function inside the external script
        if hasattr(external_module, "run"):
            params = symTab[step["params"]]

            hook_out = external_module.run(params)  # Pass parameters
            symTab[step["result"]] = hook_out
            symTab[step["flag"]] = True
            # print(f"Hook result: {hook_out}")
        else:
            print(f"Script {script_path} does not have a 'run' function. Skipping...")
            symTab[step["result"]] = "No run function found"
            symTab[step["flag"]] = False

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in Hook: {traceback.format_exc()} {str(e)}"
        print(f"Error while executing hook: {ex_stat}")
        symTab[step["result"]] = ex_stat
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


async def processExternalHook8(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        script_prefix = "none"
        script_file = "none"

        # Determine the script file name
        if step["file_name_type"] == "direct":
            script_file = step["file_name"]
            script_prefix = step["file_path"]
        elif step["file_name_type"] == "var":
            script_file = symTab[step["file_name"]]
            script_prefix = symTab[step["file_path"]]
        elif step["file_name_type"] == "expr":
            exec("global script_path\nscript_file = " + step["file_name"])
            exec("global script_prefix\nscript_prefix = " + step["file_path"])

        print("script file prefix:", script_prefix, script_file)
        script_path = f"{script_prefix}/{script_file}"
        print(f"Attempting to execute external script: {script_path}")

        # Check if the file exists asynchronously
        file_exists = await asyncio.to_thread(os.path.exists, script_path)
        if not file_exists:
            print(f"Script file not found: {script_path}. Skipping...")
            symTab[step["result"]] = "Script file not found!"
            symTab[step["flag"]] = False
            return (i + 1), ex_stat  # Skip gracefully

        # Load and execute the script dynamically
        spec = importlib.util.spec_from_file_location("external_hook", script_path)
        external_module = importlib.util.module_from_spec(spec)
        await asyncio.to_thread(spec.loader.exec_module, external_module)  # Run module import in a thread

        # Call the `run` function inside the external script
        if hasattr(external_module, "run"):
            params = symTab[step["params"]]

            if asyncio.iscoroutinefunction(external_module.run):
                hook_out = await external_module.run(params)  # Await if async
            else:
                hook_out = await asyncio.to_thread(external_module.run, params)  # Run sync function in a thread

            symTab[step["result"]] = hook_out
            symTab[step["flag"]] = True
            # print(f"Hook result: {hook_out}")
        else:
            print(f"Script {script_path} does not have a 'run' function. Skipping...")
            symTab[step["result"]] = "No run function found"
            symTab[step["flag"]] = False

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in Hook: {traceback.format_exc()} {str(e)}"
        print(f"Error while executing hook: {ex_stat}")
        symTab[step["result"]] = ex_stat
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processCreateRequestsSession(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab

    try:
        symTab[step["session_var"]] = requests.Session()
        symTab[step["flag"]] = True

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in Create Requests Session: {traceback.format_exc()} {str(e)}"
        print(f"Error while creating requests session: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processECBScreenBotCandidates(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    global login
    mainWin = login.get_mainwin()

    try:
        symTab[step["flag"]] = True
        cjs = symTab[step["cjs_var"]]
        symTab[step["result_var"]] = mainWin.screenBuyerBotCandidates(cjs)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Screen Bot Candidates: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB Screen Bot Candidates: {ex_stat}")

        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processECBCreateBots(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    global login
    mainWin = login.get_mainwin()

    try:
        symTab[step["flag"]] = True
        bjs = symTab[step["bjs_var"]]
        mainWin.createBotsFromFilesOrJsData(bjs)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Create Bots: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB creating bots: {ex_stat}")

        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processECBUpdateBots(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    global login
    mainWin = login.get_mainwin()

    try:
        symTab[step["flag"]] = True
        bjs = symTab[step["bjs_var"]]
        mainWin.updateBotsWithJsData(bjs)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Update Bots: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB updating bots: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processECBDeleteBots(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    global login
    mainWin = login.get_mainwin()

    try:
        symTab[step["flag"]] = True
        bids = symTab[step["bjs_var"]]
        # note: the bjs is in this format [{"id": bid, "owner": "", "reason": ""} .... ]
        mainWin.deleteBotsWithJsons(True, bids)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Delete Bots: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB deleting bots: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS



def processECBCreateMissions(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    global login
    mainWin = login.get_mainwin()

    try:
        symTab[step["flag"]] = True
        bjs = symTab[step["bjs_var"]]
        mainWin.createMissionsFromFilesOrJsData(True, bjs)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Create Missions: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB creating missions: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processECBUpdateMissions(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    global login
    mainWin = login.get_mainwin()

    try:
        symTab[step["flag"]] = True
        bjs = symTab[step["bjs_var"]]
        mainWin.updateMissionsWithJsData(bjs)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Update Missions: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB updating missions: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processECBDeleteMissions(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = AppContext.get_main_window()

    try:
        symTab[step["flag"]] = True
        mids = symTab[step["mids_var"]]
        # note: the mids is in this format [{"id": mid, "owner": "", "reason": ""} .... ]
        mainWin.deleteMissionsWithJsons(True, mids)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Delete Missions: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB deleting missions: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS

def processECBFetchDailySchedule(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = mission.get_main_win()

    try:
        print("ecb step: fetch schedule....")
        symTab[step["flag"]] = True
        ts_name = symTab[step["ts_name_var"]]
        forceful = symTab[step["force_var"]]
        sch_setting = mainWin.get_vehicle_settings(forceful)
        symTab[step["result_var"]] = mainWin.fetchSchedule(ts_name, sch_setting)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Fetch Daily Schedule: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB fetch daily schedule: {ex_stat}")
        symTab[step["session_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processECBDispatchTroops(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = mission.get_main_win()

    try:
        symTab[step["flag"]] = True
        print("to be dispatched schedule.....", symTab[step["schedule_var"]])
        if isinstance(symTab[step["schedule_var"]], str):
            print("string type????")
            if "error" in symTab[step["schedule_var"]].lower():
                symTab[step["flag"]] = False
                symTab[step["result_var"]] = symTab[step["schedule_var"]]
        elif isinstance(symTab[step["schedule_var"]], dict):
            print("dispatching....")
            symTab[step["result_var"]] = mainWin.handleCloudScheduledWorks(symTab[step["schedule_var"]])


        # once works are dispatched, empty the report data for a fresh start.....
        if len(mainWin.todays_work["tbd"]) > 0:
            mainWin.todays_work["tbd"][0]["status"] = ex_stat
            # now that a new day starts, clear all reports data structure
            mainWin.todaysReports = []
        else:
            logger.warning("WARNING!!!! no work TBD after fetching schedule...", "fetchSchedule", mainWin)


    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Dispatch Troops: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB dispatch troops: {ex_stat}")
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processECBCollectBotProfiles(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = AppContext.get_main_window()

    try:
        symTab[step["flag"]] = True
        mainWin.syncFingerPrintRequest()

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in ECB Collect Field Bot Profiles: {traceback.format_exc()} {str(e)}"
        print(f"Error while ECB Collect Field Bot Profiles: {ex_stat}")
        symTab[step["result_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processLogCrossNetwork(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = AppContext.get_main_window()

    try:
        symTab[step["flag"]] = True
        if step["var_type"] == "direct":
            log6(step["msg"], "wan_log", mainWin, mission, i)
        else:
            log6(symTab[step["msg"]], "wan_log", mainWin, mission, i)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in Log Cross Network: {traceback.format_exc()} {str(e)}"
        print(f"Error while Log Cross Network: {ex_stat}")
        symTab[step["result_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS


def processLog(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = AppContext.get_main_window()

    try:
        symTab[step["flag"]] = True
        if step["var_type"] == "direct":
            logger.info(step["msg"], "local_log", mainWin)
        else:
            logger.info(symTab[step["msg"]], "local_log", mainWin)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in Log Cross Network: {traceback.format_exc()} {str(e)}"
        print(f"Error while Log Cross Network: {ex_stat}")
        symTab[step["result_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS

async def processLogCrossNetwork8(step, i, mission):
    ex_stat = DEFAULT_RUN_STATUS
    global symTab
    mainWin = AppContext.get_main_window()

    try:
        symTab[step["flag"]] = True
        symTab[step["result_var"]] = None
        if step["var_type"] == "direct":
            await log68(step["msg"], "wan_log", mainWin, mission, i)
        else:
            await log68(symTab[step["msg"]], "wan_log", mainWin, mission, i)

    except Exception as e:
        # Log and skip errors gracefully
        ex_stat = f"Error in Log Cross Network8: {traceback.format_exc()} {str(e)}"
        print(f"Error while Log Cross Network8: {ex_stat}")
        symTab[step["result_var"]] = None
        symTab[step["flag"]] = False

    # Always proceed to the next instruction
    return (i + 1), DEFAULT_RUN_STATUS

def mouseClick(loc):
    pyautogui.moveTo(loc[0], loc[1])
    pyautogui.click()

def mousePressAndHold(loc, duration):
    # Move to the position
    pyautogui.moveTo(loc[0], loc[1])

    # Press and hold left mouse button down
    pyautogui.mouseDown()

    # Wait
    time.sleep(duration)

    # Release the mouse button
    pyautogui.mouseUp()

# sd is the screen data, word is the word to be press and hold on.
def mousePressAndHoldOnScreenWord(sd, word, duration= 12, nth=0):
    # find the word,
    obj_box = find_clickable_object(sd, "paragraph", word, "info", 0)
    if obj_box:
        loc = get_clickable_loc(obj_box, "center", [0, 0], "box")
        if duration:
            mousePressAndHold(loc, duration)
        else:
            mouseClick(loc)






