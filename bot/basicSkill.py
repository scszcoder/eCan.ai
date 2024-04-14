import os
import os.path


import json
import pyautogui
import time
import math
import ast
import re
import numpy as np
import webbrowser
import subprocess
import random
import socket
import sys
import traceback
from ping3 import ping, verbose_ping
if sys.platform == 'win32':
    import win32gui
    import win32con
elif sys.platform == 'darwin':
    from AppKit import NSWorkspace
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID
    )

    # fix bug of macos TypeError: '<' not supported between instances of 'str' and 'int' in _screenshot_osx
    # https://github.com/asweigart/pyautogui/issues/790
    import pyscreeze
    import PIL

    __PIL_TUPLE_VERSION = tuple(int(x) for x in PIL.__version__.split("."))
    pyscreeze.PIL__version__ = __PIL_TUPLE_VERSION

from scraper import *
from Cloud import *
from pynput.mouse import Button, Controller
from readSkill import *
from envi import *

STEP_GAP = 5
symTab = globals()
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
#####################################################################################
#  some useful utility functions
#####################################################################################

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




def genStepOpenApp(action, saverb, target_type, target_link, anchor_type, anchor_value, cargs_type, cargs, wait, stepN):
    stepjson = {
        "type": "App Open",
        "action": action,
        "save_rb": saverb,
        "target_type": target_type,
        "target_link": target_link,
        "anchor_type": anchor_type,
        "anchor_value": anchor_value,
        "cargs_type": cargs_type,
        "cargs": cargs,
        "wait":wait
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


# extract screen information:
# template: only extract template matched information.....
# root: file path prefix (installation root directory)
# sink: data sink, which holds result
# page: which page is this extration about?
# sect: which section of the page is this extraction about?
# page_data: data on the page extracted from analyzing html file contents. this info will help image analysis
# option: in case this page has no anchor, needs extra help.....
# example option:  "options": "{\"info\": [{\"info_name\": \"label_row\", \"info_type\": \"lines 1\", \"template\": \"2\", \"ref_method\": \"1\", \"refs\": [{\"dir\": \"right inline\", \"ref\": \"entries\", \"offset\": 0, \"offset_unit\": \"box\"}]}]}",
def genStepExtractInfo(template, settings, sink, page, sect, theme, stepN, page_data, options=""):
    stepjson = {
        "type": "Extract Info",
        "settings": settings,
        "template": template,
        "options": options,
        "data_sink": sink,
        "page": page,
        "page_data_info": page_data,
        "theme": theme,
        "section": sect
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
def genStepSearchScroll(screen, anchor, at_loc, target_loc, flag, resolution, postwait, site, stepN):
    stepjson = {
        "type": "Search Scroll",
        "action": "Search Scroll",
        "anchor": anchor,
        "at_loc": at_loc,
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
        "text_type": txt_type,
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
        print("GEN STEP STUB START SKILL: ", fname)
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepListDir(dirname, fargs, result_var, stepN):
    stepjson = {
        "type": "List Dir",
        "dir": dirname,
        "fargs": fargs,
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
    stepjson = {
        "type": "Wait",
        "random_min": random_min,
        "random_max": random_max,
        "time": wait
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
    stepjson = {
        "type": "Create Data",
        "data_type": dtype,
        "data_name": dname,
        "key_name": keyname,
        "key_value": keyval
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepCheckAppRunning(appname, result, stepN):
    stepjson = {
        "type": "Check App Running",
        "appname": appname,
        "result": result
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def genStepBringAppToFront(win_title, result, stepN):
    stepjson = {
        "type": "Check App Running",
        "win_title": win_title,
        "result": result
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

def genException():
    psk_words = ""
    this_step, step_words = genStepExceptionHandler("", "", 8000000)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEndException("", "", this_step)
    psk_words = psk_words + step_words
    return this_step, psk_words


def get_top_visible_window():
    if sys.platform == 'win32':
        names = []
        def winEnumHandler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                n = win32gui.GetWindowText(hwnd)
                # print("windows: ", n)
                if n:
                    names.append(n)

        win32gui.EnumWindows(winEnumHandler, None)

        # print(names)
        window_handle = win32gui.FindWindow(None, names[0])
        window_rect = win32gui.GetWindowRect(window_handle)
        print("top window: ", names[0], " rect: ", window_rect)

        return names[0], window_rect
    elif sys.platform == 'darwin':
        # 获取当前激活的应用
        active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        active_app_name = active_app.localizedName()
        window_rect = []

        # 获取所有可见窗口的列表
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)

        # 查找最上层的窗口（即当前激活的应用的窗口）
        for window in window_list:
            window_owner_name = window.get('kCGWindowOwnerName', '')
            if window_owner_name == active_app_name:
                window_name = window.get('kCGWindowName', 'Unknown')
                mac_window_rect = window.get('kCGWindowBounds', {'X': 0, 'Y': 0, 'Width': 0, 'Height': 0})
                print(f"Window: {window_owner_name}-{window_name}, Rect: {mac_window_rect}")
                # 转换为 (left, top, right, bottom) 格式
                left = mac_window_rect['X']
                top = mac_window_rect['Y']
                right = left + mac_window_rect['Width']
                bottom = top + mac_window_rect['Height']

                window_rect.extend([round(left), round(top), round(right), round(bottom)])

                print(f"Window Rect: ({window_rect[0], window_rect[1], window_rect[2], window_rect[3]})")

                break

        return active_app_name, window_rect


def read_screen(site_page, page_sect, page_theme, layout, mission, sk_settings, sfile, options):
    settings = mission.parent_settings
    global screen_loc

    window_name, window_rect = get_top_visible_window()

    if not os.path.exists(os.path.dirname(sfile)):
        os.makedirs(os.path.dirname(sfile))

    #now we have obtained the top window, take a screen shot , region is a 4-tuple of  left, top, width, and height.
    im0 = pyautogui.screenshot(region=(window_rect[0], window_rect[1], window_rect[2], window_rect[3]))
    im0.save(sfile)
    screen_loc = (window_rect[0], window_rect[1])

    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1B: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    #upload screen to S3
    upload_file(settings["session"], sfile, settings["token"], "screen")

    m_skill_names = [sk_settings["skname"]]
    m_psk_names = [sk_settings["skfname"]]
    csk_name = sk_settings["skfname"].replace("psk", "csk")
    m_csk_names = [csk_name]

    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1C: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # request an analysis of the uploaded screen
    # some example options usage:
    # Note: options is a global variable name that actually contains the options json string as shown below:
    # "options": "{\"info\": [{\"info_name\": \"label_row\", \"info_type\": \"lines 1\", \"template\": \"2\", \"ref_method\": \"1\", \"refs\": [{\"dir\": \"right inline\", \"ref\": \"entries\", \"offset\": 0, \"offset_unit\": \"box\"}]}]}",
    # basically let a user to modify csk file by appending some user defined way to extract certain information element.

    request = [{
        "id": mission.getMid(),
        "bid": mission.getBid(),
        "os": sk_settings["platform"],
        "app": sk_settings["app"],
        "domain": sk_settings["site"],
        "page": site_page,
        "layout": layout,
        "skill_name": m_skill_names[0],
        "psk": m_psk_names[0].replace("\\", "\\\\"),
        "csk": m_csk_names[0].replace("\\", "\\\\"),
        "lastMove": page_sect,
        "options": "",
        "theme": page_theme,
        "imageFile": sfile.replace("\\", "\\\\"),
        "factor": "{}"
    }]

    if options != "":
        request[0]["options"] = symTab[options]

    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1D: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    result = req_cloud_read_screen(settings["session"], request, settings["token"])
    print("result::: ", result)
    jresult = json.loads(result['body'])
    # print("cloud result data: ", jresult["data"])
    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1E: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    if "errors" in jresult:
        screen_error = True
        print("ERROR Type: ", jresult["errors"][0]["errorType"], "ERROR Info: ", jresult["errors"][0]["errorInfo"], )
    else:
        # print("cloud result data body: ", result["body"])
        jbody = json.loads(result["body"])
        # for p in jbody["data"]:
        #     if p["name"] == "paragraph":
        #         for tl in p["txt_struct"]:
        #             print("TXT LINE: ", tl["text"])



        # global var "last_screen" always contains information extracted from the last screen shot.
        if len(jbody["data"]) > 0:
            symTab["last_screen"] = jbody["data"]
            return jbody["data"]
        else:
            symTab["last_screen"] = []
            return []


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
        print("Due to supply time lag, this mission is halted till  hours later....")
        #should kick off a timer to wait .
    except:
        ex_stat = "ErrorHalt:" + str(i)

    return (i+1), ex_stat

def processDone(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        print("Mission accomplished!")
    except:
        ex_stat = "ErrorDone:" + str(i)

    return (i+1), ex_stat

def processWait(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        print("waiting...... make mouse pointer wonder a little bit!")
        wtime = 1
        if step["time"] == "":
            # calculate wait based on page contents, and reading speed.
            print("waiting for last screen ", wtime, " seconds....")
            # screen = symTab["last_screen"]
        else:
            wtime = step["time"]
            print("waiting for ", wtime, " seconds....")

        if step["random_max"] > 0:
            wtime = random.randrange(step["random_min"], step["random_max"])

        print("actually waiting for ", wtime, " seconds....")
        time.sleep(wtime)

    except:
        ex_stat = "ErrorWait:" + str(i)

    return (i+1), ex_stat



def processExtractInfo(step, i, mission, skill):
    # mission_id, session, token, top_win, skill_name, uid
    print("Extracting info....", mission, " SK: ", skill)
    print("mission[", mission.getMid(), "] cuspas: ", mission.getCusPAS())
    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    global screen_error

    ex_stat = DEFAULT_RUN_STATUS
    try:
        screen_error = False
        dtnow = datetime.now()

        if step["page_data_info"]:
            page_layout = symTab[step["page_data_info"]]["products"]["layout"]
        else:
            page_layout = ""

        print("page layout is: [", page_layout, "]")

        date_word = dtnow.strftime("%Y%m%d")
        dt_string = str(int(dtnow.timestamp()))
        print("date string:", dt_string)

        if skill.getPrivacy() == "public":
            ppword = skill.getPrivacy()
        else:
            ppword = mission.parent_settings["uid"]

        date_word = dtnow.strftime("%Y%m%d")
        dt_string = str(int(dtnow.timestamp()))
        print("date string:", dt_string)
        sfile = "C:/Users/songc/PycharmProjects/testdata/"
        #sfile = sfile + settings["uid"] + "/win/adspower/"
        #sfile = sfile + "scrn" + settings["uid"] + "_" + dt_string + ".png"
        if skill.getPrivacy() == "public":
            ppword = skill.getPrivacy()
        else:
            ppword = mission.parent_settings["uid"]

        print("mission[", mission.getMid(), "] cuspas: ", mission.getCusPAS(), "step settings:", step["settings"])

        if type(step["settings"]) == str:
            step_settings = symTab[step["settings"]]
            print("SETTINGS FROM STRING....", step_settings)
        else:
            step_settings = step["settings"]

        print("STEP SETTINGS", step_settings)
        platform = step_settings["platform"]
        app = step_settings["app"]
        site = step_settings["site"]
        page = step_settings["page"]

        if step_settings["root_path"][len(step_settings["root_path"])-1]=="/":
            step_settings["root_path"] = step_settings["root_path"][:len(step_settings["root_path"])-1]

        fdir = ecb_data_homepath + "/runlogs/"
        fdir = fdir + date_word + "/"

        fdir = fdir + "b" + str(step_settings["botid"]) + "m" + str(step_settings["mid"]) + "/"
        # fdir = fdir + ppword + "/"
        fdir = fdir + platform + "_" + app + "_" + site + "_" + page + "/skills/"
        fdir = fdir + step_settings["skname"] + "/images/"
        sfile = fdir + "scrn" + mission.parent_settings["uid"] + "_" + dt_string + ".png"
        print("sfile: ", sfile)


        print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1A: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


        result = read_screen(step["page"], step["section"], step["theme"], page_layout, mission, step_settings, sfile, step["options"])
        symTab[step["data_sink"]] = result
        print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp2: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractInfo:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorExtractInfo traceback information not available:" + str(e)
        print(ex_stat)

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
        print("txts var:", symTab[step["texts_var"]])
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
                print("ERROR, how could the name be not found?")

            # once found, update the relavant field. such as
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorFillRecipients:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorFillRecipients traceback information not available:" + str(e)
        print(ex_stat)

    return (i+1), ex_stat

# text input, type only, the click onto the correction place to type should happen before this.
# action: action to perform here - simply text input
#  text: txt to be input.
#  speed: type speed.
#  key_after: key to hit after textinput. (could be "", "enter",
#  wait_after: number of seconds to wait after key_after action.
def processTextInput(step, i):
    global page_stack
    global current_context
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # print("Keyboard typing......", nthSearch, type(nthSearch), type(run_config), run_config, list(run_config.keys()))

        if step["txt_ref_type"] == "direct":
            txt_to_be_input = step["text"]
        else:
            print("assign expression:", "txt_to_be_input = "+step["text"])
            exec("global input_texts\ninput_texts = "+step["text"])
            txt_to_be_input = input_texts
            print("after assignment:", txt_to_be_input)
            exec("global txt_to_be_input\ntxt_to_be_input = "+step["text"])

        print("typing.....", txt_to_be_input)
        time.sleep(2)
        # pyautogui.click()
        if step["text_type"] == "var":
            print("about to TYPE in:", symTab[txt_to_be_input])
            pyautogui.write(symTab[txt_to_be_input], interval=0.25)
        else:
            if len(txt_to_be_input) > 0:
                print("direct type in:", txt_to_be_input[0])
                pyautogui.write(txt_to_be_input[0], interval=step["speed"])
            else:
                pyautogui.write("Do not know", interval=step["speed"])

        time.sleep(1)
        if step['key_after'] != "":
            print("after typing, pressing:", step['key_after'], "then wait for:", step['wait_after'])
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
            ex_stat = "ErrorTextInput:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorTextInput traceback information not available:" + str(e)
        print(ex_stat)

    return (i+1), ex_stat


# calculate an object’s row col position in a virtual table, given the object's position, origin, table cell width, table cell height.
def calc_loc(box, cell_w, cell_h, origin):
    ci = round((box[0] - origin[0])/cell_w)
    ri = round((box[1] - origin[1])/cell_h)

    loc =[ci, ri]
    # print("location:", loc)
    return loc

# calculate an object’s sequence in a virtual table, given the object's position, origin, table cell width, table cell height, and row width.
def calc_seq(box, cell_w, cell_h, origin, ncols):
    loc = calc_loc(box, cell_w, cell_h, origin)
    seq = loc[1] * ncols + loc[0]
    print("sequence:", seq)
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
    print("xs:", xs)

    ys = [o[1] for o in object_list]
    ys.sort()
    print("ys:", ys)

    xgroups = group_1D(xs)

    ygroups = group_1D(ys)

    xgrp_avgs = [sum(grp)/len(grp) for grp in xgroups]
    xgaps = []
    for x, y in zip(xgrp_avgs[0::], xgrp_avgs[1::]):
        xgaps.append(y - x)

    print("xgrp_avgs:", xgrp_avgs, "xgaps:", xgaps)

    ygrp_avgs = [sum(grp)/len(grp) for grp in ygroups]
    ygaps = []
    for x, y in zip(ygrp_avgs[0::], ygrp_avgs[1::]):
        ygaps.append(y - x)

    xgap = min(xgaps)
    ygap = min(ygaps)

    print("ygrp_avgs:", ygrp_avgs, "ygaps:", ygaps)


    rows = round((ygrp_avgs[len(ygrp_avgs)-1] - ygrp_avgs[0])/ygap) + 1
    cols = round((xgrp_avgs[len(xgrp_avgs)-1] - xgrp_avgs[0])/xgap) + 1

    print("cols:", cols)
    print("rows:", rows)

    # Find calculate the origial list member's table index (col., row) (i.e. (x, y) coordinate)
    coords = [calc_loc(o, xgap, ygap, [xgrp_avgs[0], ygrp_avgs[0]]) for o in object_list]
    print("coords:", coords)

    xy_sorted = sorted(object_list, key=lambda x: calc_seq(x, xgap, ygap, [xgrp_avgs[0], ygrp_avgs[0]], cols), reverse=False)
    print("x-y sorted:", xy_sorted)
    coords = [calc_loc(o, xgap, ygap, [xgrp_avgs[0], ygrp_avgs[0]]) for o in xy_sorted]
    print("coords:", coords)

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
    print("LOOKING FOR:", target, "   ", template,  "   ", target_type, "   ", nth)
    found = {"loc": None}
    if target != "paragraph":
        reg = re.compile(target+"[0-9]+")
        targets = [x for x in sd if (x["name"] == target or reg.match(x["name"])) and x["type"] == target_type]
    else:
        reg = re.compile(template)
        targets = [x for x in sd if template in x["text"] and x["type"] == target_type and x["name"] == target]
    # grab all instances of the target object.

    print("found targets::", len(targets))
    objs = []

    # convert possible string to integer
    for o in targets:
        if o["name"] == "paragraph":
            lines = [l for l in o["txt_struct"] if (l["text"] == template or re.search(template, l["text"]))]
            print("found lines::", len(lines))
            if len(lines) > 0:
                for li, l in enumerate(lines):
                    pat_words = template.strip().split()
                    lreg = re.compile(pat_words[0])
                    print("checking line:", l, pat_words)
                    start_word = next((x for x in l["words"] if re.search(pat_words[0], x["text"])), None)
                    print("start_word:", start_word)
                    if start_word:
                        if len(pat_words) > 1:
                            lreg = re.compile(pat_words[len(pat_words)-1])
                            end_word = next((x for x in l["words"] if x["text"] == pat_words[len(pat_words)-1] or lreg.match(x["text"])), None)
                            print("multi word end_word:", end_word)
                        else:
                            end_word = start_word
                            print("single word")

                        objs.append({"loc": [int(start_word["box"][1]), int(start_word["box"][0]), int(end_word["box"][3]), int(end_word["box"][2])]})
                        print("objs:", objs)
        else:
            print("non paragraph:", o)
            o["loc"] = [int(o["loc"][0]), int(o["loc"][1]), int(o["loc"][2]), int(o["loc"][3])]
            objs.append({"loc": o["loc"]})

    print("objs:", objs)
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
        my_array = np.empty([nrows, ncols], dtype=object)
        for ob in ysorted:
            ri = math.floor((ob["loc"][1] - ysorted[0]["loc"][1])/cell_height)
            ci =  math.floor((ob["loc"][0] - xsorted[0]["loc"][0])/cell_width)
            print("Filling in row:", ri, " col:", ci)
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
                print("nth as a variable name is:", symTab[nth])
                found = objs[symTab[nth]]
                print("found object:", found)
        elif type(nth) == int:
            print("nth as an integer is:", nth)
            found = objs[nth]
        # the code is incomplete at the moment....
    elif len(objs) == 1:
        found = objs[0]

    return found["loc"]

def get_clickable_loc(box, off_from, offset, offset_unit):
    print("get_clickable_loc: ", box, " :: ", off_from, " :: ", offset, " :: ", offset_unit)
    center = box_center(box)
    if offset_unit == "box":
        box_length = box[3] - box[1]
        box_height = box[2] - box[0]
    else:
        box_length = 1
        box_height = 1

    if off_from == "left":
        click_loc = (box[1] - int(offset[0]*box_length), center[0])
    elif off_from == "right":
        click_loc = (box[3] + int(offset[0]*box_length), center[0])
    elif off_from == "top":
        click_loc = (center[1], box[0] - int(offset[1]*box_height))
    elif off_from == "bottom":
        click_loc = (center[1], box[2] + int(offset[1]*box_height))
    else:
        #offset from center case
        print("CENTER: ", center, "OFFSET:", offset)
        click_loc = ((center[1] + int(offset[0]*box_length), center[0] + int(offset[1]*box_height)))

    return click_loc


def get_post_move_offset(box, offset, offset_unit):
    print("calc post move offset:", offset_unit, box, offset)
    if offset_unit == "box":
        box_length = box[3] - box[2]
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
def processMouseClick(step, i):
    global page_stack
    global current_context
    print("Mouse Clicking .....")
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
            print("finding: ", step["text"], " target name: ", target_name, " text to be matched:["+step["text"]+"]")
            # print("from data: ", sd)
            obj_box = find_clickable_object(sd, target_name, step["text"], step["target_type"], step["nth"])
            print("obj_box: ", obj_box)
            loc = get_clickable_loc(obj_box, step["offset_from"], step["offset"], step["offset_unit"])
            post_offset = get_post_move_offset(obj_box, step["post_move"], step["offset_unit"])
            post_loc = [loc[0] + post_offset[0], loc[1] + post_offset[1]]
            print("indirect calculated locations:", loc, "post_offset:(", post_offset[0], ",", post_offset[1], ")", "post_loc:", post_loc)

        else:
            # the location is already calculated directly and stored here.
            if step["target_type"] == "direct":
                print("obtain directly..... from a variable which is a box type i.e. [l, t, r, b]")
                box = symTab[step["target_name"]]
                loc = box_center(box)
                post_offset_x = (box[2] - box[0]) * step["post_move"][0]
                post_offset_y = (box[3] - box[1]) * step["post_move"][1]
                post_loc = [loc[0] + post_offset_x, loc[1] + post_offset_y]
            else:
                print("obtain thru expression..... which after evaluate this expression, it should return a box i.e. [l, t, r, b]", step["target_name"])
                exec("global click_target\nclick_target = " + step["target_name"])
                print("box: ", symTab["target_name"])
                box = [symTab["target_name"][1], symTab["target_name"][0], symTab["target_name"][3], symTab["target_name"][2]]
                loc = box_center(box)
                post_offset_y = (symTab["target_name"][2] - symTab["target_name"][0]) * step["post_move"][0]
                post_offset_x = (symTab["target_name"][3] - symTab["target_name"][1]) * step["post_move"][1]
                post_loc = [loc[0] + post_offset_x, loc[1] + post_offset_y ]

            print("direct calculated locations:", loc, "post_offset:(", post_offset_x, ",", post_offset_y, ")", "post_loc:", post_loc)

        window_name, window_rect = get_top_visible_window()
        print("top windows rect:", window_rect)

        # loc[0] = int(loc[0]) + window_rect[0]
        loc = (int(loc[0]) + window_rect[0], int(loc[1]) + window_rect[1])
        print("global loc@ ", loc[0], " ,  ", loc[1])

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
        print("post click moveto :(", int(post_loc[0]) + window_rect[0], ",", int(post_loc[1]) + window_rect[1], ")")
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
            ex_stat = "ErrorMouseClick:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorMouseClick: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat

# max 4 combo key stroke
def processKeyInput(step, i):
    global page_stack
    global current_context

    ex_stat = DEFAULT_RUN_STATUS
    try:
        keys = step["action_value"].split(',')
        print("Keyboard Action..... hot keys", keys)
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
            ex_stat = "ErrorKeyInput:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorKeyInput: traceback information not available:" + str(e)
        print(ex_stat)

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
    # print("p2p distance: ", dist)
    return dist

# loc: (top, left, bottom, right)
def loc_center(box):
    return (box[1]+int((box[3]-box[1])/2), box[0]+int((box[2]-box[0])/2))

# box: (left, top, right, bottom)
def box_center(box):
    return (box[0]+int((box[2]-box[0])/2), box[1]+int((box[3]-box[1])/2))

def processMouseScroll(step, i):
    screen_data = symTab[step["screen"]]
    # print("screen_data: ", screen_data)
    ex_stat = DEFAULT_RUN_STATUS
    try:
        screen_vsize = screen_data[len(screen_data) - 2]['loc'][2]

        if step["unit"] == "screen":
            print("SCREEN SIZE: ", screen_data[len(screen_data) - 2]['loc'], "resolution var: ", step["resolution"], " val: ", symTab[step["resolution"]])
            if type(step["amount"]) is str:
                scroll_amount = int(((symTab[step["amount"]]/100)*screen_vsize)/symTab[step["resolution"]])
            else:
                scroll_amount = int(((step["amount"]/100)*screen_vsize)/symTab[step["resolution"]])
                print("screen size based scroll amount:", scroll_amount)
        elif step["unit"] == "raw":
            if type(step["amount"]) is str:
                scroll_amount = symTab[step["amount"]]
            else:
                scroll_amount = step["amount"]
        else:
            print("ERROR: unrecognized scroll unit!!!")

        if step["action"] == "Scroll Down":
            scroll_amount = 0 - scroll_amount

        if "scroll_resolution" in symTab:
            print("Calculated Scroll Amount: ", scroll_amount, "scroll resoution: ", symTab["scroll_resolution"])
        else:
            print("Calculated Scroll Amount: ", scroll_amount, "scroll resoution: NOT YET AVAILABLE")

        if step["random_max"] != step["random_min"]:
            if step["action"] == "Scroll Down":
                scroll_amount = scroll_amount - random.randrange(step["random_min"], step["random_max"])
            else:
                scroll_amount = scroll_amount + random.randrange(step["random_min"], step["random_max"])

        print("after randomized Scroll Amount: ", scroll_amount)
        mouse.scroll(0, scroll_amount)

        time.sleep(step["postwait"])


        if step["breakpoint"]:
            input("type any key to continue")


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorMouseScroll:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorMouseScroll: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processOpenApp(step, i):
    print("Opening App .....", step["target_link"] + " " + step["cargs"])
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["target_type"] == "browser":
            url = step["target_link"]
            webbrowser.open(url, new=0, autoraise=True)
        else:
            exec("global oa_exe\noa_exe = "+step["target_type"])
            if step["cargs_type"] == "direct":
                subprocess.call(symTab["oa_exe"] + " " + step["cargs"])
            else:
                # in case of "expr" type.
                exec("global oa_args\noa_args = " + step["cargs"])
                print("running shell", symTab["oa_exe"], "on :", step["cargs"], "with val["+symTab["oa_args"]+"]")
                subprocess.Popen([symTab["oa_exe"], symTab["oa_args"]])
        time.sleep(step["wait"])


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOpenApp:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorOpenApp: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def extract_variable_names(code_line):
    # Parse the code line into an abstract syntax tree (AST)
    try:
        # Wrap the code in a valid Python expression using eval()
        tree = ast.parse(code_line)
    except Exception as e:
        print("Error:", e)
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
    print("Creating Data .....")
    global mission_vars
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["key_name"] == "NA":
            # this is the case of direct assignment.
            # print("NOT AN DICT ENTRY ASSIGNMENT")
            if step["data_type"] == "expr":
                print("TBEx: ", step["data_name"] + " = " + step["key_value"])
                # symTab[step["data_name"]] = None
                # exec("global sk_work_settings")
                # exec("global "+step["data_name"])
                simple_expression = step["data_name"] + " = " + step["key_value"]
                expr_vars = extract_variable_names(simple_expression)
                print("vars in the expression:", expr_vars)
                executable = "global"
                for expr_var in expr_vars:
                    # print("woooooohahahahahah", executable)
                    executable = executable + " " + expr_var
                    if expr_vars.index(expr_var) != len(expr_vars) - 1:
                        executable = executable + ","
                executable = executable + "\n" + simple_expression
                print("full executable statement:", executable)
                exec(executable)
                print(step["data_name"] + " is now: ", symTab[step["data_name"]])
            else:
                symTab[step["data_name"]] = step["key_value"]
        else:
            if not re.match("\[.*\]|\{.*\}", step["key_value"]):
                symTab[step["data_name"]] = {step["key_name"]: step["key_value"]}
            else:
                symTab[step["data_name"]] = {step["key_name"]: json.loads(step["key_value"])}

        mission_vars.append(step["data_name"])


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateData:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCreateData: traceback information not available:" + str(e)
        print(ex_stat)

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
            ex_stat = "ErrorText2Number:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorText2Number: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat



# this is for add an object to a list/array of object, or add another key-value pair to a json object.
# from: value source
# to: value destination
# result: the destination variable when operation is a "pop" in which case, "from" is the index, "to" is the list variable name.
# fill_type: "assign"/"copy"/"append"/"prepend"/"merge"/"clear"/"pop":
def processFillData(step, i):
    print("Filling Data .....", step)
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # if not re.match("\[.*\]|\{.*\}", step["from"]):
        if type(step["from"]) is str:
            from_words = re.split('\[|\(|\{', step["from"])
            source = from_words[0]
        else:
            source = step["from"]
        print("source var:", source)

        if type(step["to"]) is str:
            to_words = re.split('\[|\(|\{', step["to"])
            sink = to_words[0]
        else:
            sink = step["to"]
        print("sink var:", sink)

        if step["result"] != "":
            res_words = re.split('\[|\(|\{', step["result"])
            res = to_words[0]
            print("res var:", res)

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
        print("Statement: ", statement)
        exec(statement)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorFillData:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorFillData: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat

# basically context switching here...
def processEndException(step, i, step_keys):
    global exception_stack
    global page_stack
    global in_exception
    print("Return from Exception .....")
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
            ex_stat = "ErrorException:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorException: traceback information not available:" + str(e)
        print(ex_stat)

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
            print("reconnected, set up to resume from the rollback point")
            # hit refresh page. Ctrl-F5
            pyautogui.hotkey("ctrl", "f5")

        else:
            print("MISSION failed...")



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExceptionHandler:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorExceptionHandler: traceback information not available:" + str(e)
        print(ex_stat)

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
    print(ast.dump(ast.parse(condition)))
    print("root:", root)
    # extract all variable names in the condition statement expression
    varnames = sorted({node.id for node in ast.walk(root) if isinstance(node, ast.Name)})
    print("varnames:", varnames)
    # now filter out special keywords such int, str, float what's left should be variable names.
    varnames = list(filter(lambda k: not (k == "float" or k == "int" or k == "str" or k == "len"), varnames))
    print("filtered varnames:", varnames)
    prefix = "global "
    for varname in varnames:
        if varname in symTab:
            prefix = prefix + varname + ", "
        else:
            # if the variable doesn't exist, create the variable.
            symTab[varname] = None

    prefix = prefix + "cmp_result\ncmp_result = ("
    condition = prefix + condition + ")"
    print("TBE: " + condition)
    exec(condition)
    print("TBE result: ", cmp_result)

    return cmp_result


# "type": "Check Condition",
# "condition": condition,
# "if_else": ifelse,
# "if_end": ifend
def processCheckCondition(step, i, step_keys):
    print("Check Condition.....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        condition = step["condition"]

        if evalCondition(condition):
            idx = i + 1
        else:
            idx = step_keys.index(step["if_else"])
            print("else: ", step["if_else"], "else idx: ", idx)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckCondition:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCheckCondition: traceback information not available:" + str(e)
        print(ex_stat)


    return idx, ex_stat


# "type": "Repeat",
# "lc_name": loop counter name. need to be unique, usually is the stepname.
# "until": loop condition condition,
# "count": repeat count,
# "end": loop end marker.
def processRepeat(step, i,  step_keys):
    print("Looping.....: ", step)
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
            print("repeat counter: ", symTab[lcvar_name], "target count: ", step["count"])
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
            ex_stat = "ErrorRepeat:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorRepeat: traceback information not available:" + str(e)
        print(ex_stat)

    return end_idx, ex_stat

# assumption: data is in form of a single json which can be easily dumped.
def processLoadData(step, i):
    print("Loading Data .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        with open(step["file_link"], 'r') as f:
            symTab[step["data_name"]] = json.load(f)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadData:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorLoadData: traceback information not available:" + str(e)
        print(ex_stat)

    return (i+1), ex_stat


def processSaveData(step, i):
    print("Saving Data .....")
    ex_stat = DEFAULT_RUN_STATUS
    try:
        with open(step["file_link"], 'w') as f:
            json.dump(symTab[step["data_name"]], f)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSaveData:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorSaveData: traceback information not available:" + str(e)
        print(ex_stat)

    return (i+1), ex_stat

# fname: external script/function name  - very IMPORTANT： this is calling python routine either in a file or a function， this is different from
#          psk function/subroutine
# args: arguments to the external functions.
# entity: "are we calling a script or function?"
# output: output data variable
def processCallExtern(step, i):
    print("Run External Script/code as strings .....")
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
            oargs = ["capture_output=True", "text=True"]
            cmdline.extend(oargs)
            print("command line: ", cmdline)
            result = subprocess.call(cmdline, shell=True)
        else:
            # execute a string as raw python code.
            result = exec(step["file"])
            if "nNRP" in step["file"]:
                print("nNRP: ", symTab["nNRP"])
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
            ex_stat = "ErrorCallExtern:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCallExtern: traceback information not available:" + str(e)
        print(ex_stat)

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
        print("getting skill call input parameter: ", fin_par, " [val: ", symTab[fin_par])
        print("current skill table: ", sk_table)

        # start execuation on the function, find the function name's address, and set next pointer to it.
        # the function name address key value pair was created in gen_addresses
        skname = step["skill_path"] + "/" + step["skill_name"]
        print("skname:", skname)
        idx = step_keys.index(sk_table[skname])
        print("idx:", idx)
        print("step_keys:", step_keys)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorUseSkill:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorUseSkill: traceback information not available:" + str(e)
        print(ex_stat)

    return idx, ex_stat

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
            ex_stat = "ErrorOverloadSkill:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorOverloadSkill: traceback information not available:" + str(e)
        print(ex_stat)

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
        print("geting function call input parameter: ", fin_par, " [val: ", symTab[fin_par])

        # start execuation on the function, find the function name's address, and set next pointer to it.
        # the function name address key value pair was created in gen_addresses
        idx = step_keys.index(func_table[step["fname"]])



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallFunction:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCallFunction: traceback information not available:" + str(e)
        print(ex_stat)

    return idx, ex_stat


def processReturn(step, i, stack, step_keys):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        # push current address pointer onto stack,
        return_var_name = stack.pop()

        if return_var_name != "":
            symTab[return_var_name] = symTab[step["val_var_name"]]
            # print("return var.....", step["val_var_name"], "[val:", symTab[step["val_var_name"]])
            # print("return result to .....", return_var_name, "[val:", symTab[return_var_name])

        # restoer original fin and fout.
        symTab["fin"] = stack.pop()
        symTab["fout"] = stack.pop()


        #  set the pointer to the return to pointer.
        next_i = stack.pop()
        print("after return, will run @", next_i)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorReturn:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorReturn: traceback information not available:" + str(e)
        print(ex_stat)

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
            print("end of a skill", step["func_name"], "reached.")
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

                print("TEST_RUN_CNT ex_stat:", TEST_RUN_CNT, "[" + ex_stat + "]")
                TEST_RUN_CNT = TEST_RUN_CNT + 1



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorStub:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorStub: traceback information not available:" + str(e)
        print(ex_stat)

    return next_i, ex_stat


def processGoto(step, i,  step_keys):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        print("stepGOTO:", step["goto"])
        if "step B" in step["goto"] and "!" in step["goto"] :
            next_step_index = step_keys.index(step["goto"])
        else:
            next_step_index = step_keys.index(symTab[step["goto"]])



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGoTo:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorGoTo: traceback information not available:" + str(e)
        print(ex_stat)

    return next_step_index, ex_stat


def processListDir(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        lof = os.listdir(step["dir"])
        symTab[step["result"]] = [f for f in lof if f.endswith(step["fargs"])]  # fargs contains extension such as ".pdf"



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorListDir:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorListDir: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processCheckExistence(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if "var" in step["fntype"]:
            fn = symTab[step["file"]]
        else:
            fn = step["file"]
        print("check existence for :", fn, "of type:", step["fntype"])
        if "dir" in  step["fntype"]:
            symTab[step["result"]] = os.path.isdir(fn)
        else:
            symTab[step["result"]] = os.path.isfile(fn)

        print("Existence is:", symTab[step["result"]])



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckExistence:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCheckExistence: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processCreateDir(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        if step["name_type"] == "direct":
            dir_tbc = step["dir"]
        else:
            exec("dir_tbc = " + step["dir"])

        subds = dir_tbc.split("/")
        if len(subds) == 1:
            newdir = symTab[dir_tbc]
        else:
            newdir = dir_tbc

        print("Creating dir:", newdir)
        if not os.path.exists(newdir):
            #create only if the dir doesn't exist
            os.makedirs(newdir)
            print("Created.....")
        else:
            print("Already existed.")



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCreateDir:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCreateDir: traceback information not available:" + str(e)
        print(ex_stat)

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
            if output_dir != "":

                symTab[step["result"]] = subprocess.call(exe + " a " + input + "-o" + output_dir)
            else:
                symTab[step["result"]] = subprocess.call(exe + " e " + input)

        elif step["action"] == "unzip":
            if output_dir != "":
                print("executing....", exe + " e " + input + " -o" + output_dir)
                # output_dir = "-o"+output_dir
                print("outputdir:", output_dir)
                # extremely key here, there should be no "" around Program Files....
                cmd = ['C:/Program Files/7-Zip/7z.exe', 'e', input,  f'-o{output_dir}']
                symTab[step["result"]] = subprocess.Popen(cmd)
                # symTab[step["result"]] = subprocess.run(exe + " e " + input + " -o" + output_dir)
                # symTab[step["result"]] = subprocess.Popen(['C:/Program Files/7-Zip/7z.exe'])
            else:
                symTab[step["result"]] = subprocess.call(exe + " e " + input)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "Error7z:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "Error7z: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


# create a data structure holder for anchor....
# "type": "Search",
# "action": "Search",
# "screen": screen,
# "name": name,
# "target_type": target_type, target type
# "result": result, result varaibel continas result.
# "status": flag - flag variable contains result
def processSearchAnchorInfo(step, i):
    print("Searching....", step["target_types"])
    global in_exception
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        print("SEARCH SCREEN INFO:", scrn)
        logic = step["logic"]
        fault_names = ["site_not_reached", "bad_request"]
        fault_found = []

        found = []
        n_targets_found = 0

        # print("Searching screen....", scrn)

        if not (type(step["names"]) is list):
            target_names = [step["names"]]  # make it a list.
            target_types = [step["target_types"]]
        else:
            target_names = step["names"]
            target_types = step["target_types"]

        for idx in range(len(target_names)):
            print("ith target:", idx, target_types[idx], target_names[idx])
            if step["name_type"] != "direct":
                exec("global temp_target_name\ntemp_target_name= " + target_names[idx])
                target_names[idx] = temp_target_name

        # now do the search
        for target_name, target_type in zip(target_names, target_types):
            print("searching: ", target_name, ", ", target_type, "==================")
            targets_found = [element for index, element in enumerate(scrn) if
                             element["name"] == target_name and element["type"] == target_type]
            if len(targets_found) > 0:
                n_targets_found = n_targets_found + 1
            found = found + targets_found

        # reg = re.compile(target_names + "[0-9]+")
        # found = [element for index, element in enumerate(scrn["data"]) if reg.match(element["name"]) and element["type"] == target_types]

        print("found.... ", found)
        # search result should be put into the result variable.
        symTab[step["result"]] = found

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

        print("status: ", symTab[step["status"]])

        # didn't find anything, check fault situation.
        if symTab[step["status"]] == False:
            fault_found = [e for j, e in enumerate(scrn) if e["name"] in fault_names and e["type"] == "anchor text"]
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
            ex_stat = "ErrorSearchAnchorInfo:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorSearchAnchorInfo: traceback information not available:" + str(e)
        print(ex_stat)

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
def processSearchWordLine(step, i):
    print("Searching....words and/or lines", step["name_types"])
    global in_exception
    p_stat = ""
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        fault_names = ["site_not_reached", "bad_request"]
        fault_found = []

        found = []
        n_targets_found = 0

        # print("Searching screen....", scrn)
        if not (type(step["names"]) is list):
            target_names = [step["names"]]  # make it a list.
            name_types = [step["name_types"]]
        else:
            target_names = step["names"]
            name_types = step["name_types"]

        print("target_names:", target_names, "name_types:", name_types)
        for idx in range(len(target_names)):
            if "direct" not in name_types[idx]:
                exec("global temp_target_name\ntemp_target_name= " + target_names[idx])
                target_names[idx] = temp_target_name
                print("ith target:", idx, name_types[idx], target_names[idx])

        # now do the search
        # all_lines = [element["txt_struct"] for index, element in enumerate(scrn) if element["name"] == "paragraph" and element["type"] == "info"]
        all_paragraphs = [element for index, element in enumerate(scrn) if element["name"] == "paragraph" and element["type"] == "info"]
        print("all_paragraphs:", all_paragraphs)
        print("==============================================================")
        # go thru each to be matched pattern and search paragraph by paragraph.
        all_found = []
        for target_name, name_type in zip(target_names, name_types):
            found = []
            for p in all_paragraphs:
                # search which line has the match
                for line in p["txt_struct"]:
                    lmatch = re.search(target_name, line["text"])
                    if lmatch:
                        print("line matched:", line["text"])
                        start_index = lmatch.start()
                        end_index = lmatch.end()
                        matched_pattern = line["text"][start_index:end_index]
                        matched_words = matched_pattern.split()
                        first_word = matched_words[0]
                        last_word = None
                        print("matched_words", matched_words, "first_word", first_word, "last_word", last_word)
                        if len(matched_words) >  1:
                            last_word = matched_words[len(matched_words)-1]

                        match_starts = [word for index, word in enumerate(line["words"]) if first_word in word["text"]]

                        if last_word:
                            match_ends = [word for index, word in enumerate(line["words"]) if last_word in word["text"]]

                        print("match_starts", match_starts)
                        for match_start in match_starts:
                            if last_word:
                                match_end = next((x for x in match_ends if x["box"][0] > match_start["box"][2] ), None)
                                matched_loc = [match_start["box"][0], match_start["box"][1], match_end["box"][2], match_end["box"][3]]
                                print("match more than 1 word")
                            else:
                                matched_loc = match_start["box"]
                                print("match only 1 word")

                            found.append({"txt": matched_pattern, "box": matched_loc})
                else:
                    p_stat = "pattern NOT FOUND in paragraph"
                    print(p_stat, p["text"])

            # line up the matched location top to bottom.
            if len(found) > 0:
                print("found here", found)
                sorted_found = sorted(found, key=lambda w: w["box"][1], reverse=False)
                all_found.extend(sorted_found)

            print("======================+++++++++++++++++++++++++++++++++++")

        print("all found.... ", all_found)
        # search result should be put into the result variable.
        symTab[step["result"]] = all_found

        if len(all_found) == 0:
            symTab[step["status"]] = False
        else:
            symTab[step["status"]] = True

        print("status: ", symTab[step["status"]])

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
            ex_stat = "ErrorSearchWordLine:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorSearchWordLine: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat

# this is a convinience function.
# scroll anchor nearest to the north of at_location, to the target loction.
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

    print("Searching....", step["anchor"])
    ex_stat = DEFAULT_RUN_STATUS
    try:
        scrn = symTab[step["screen"]]
        anchor = step["anchor"]
        at_loc_top = int(step["at_loc"][0])/100
        at_loc_bottom = int(step["at_loc"][1]) / 100
        target_loc = int(step["target_loc"])/100
        scroll_resolution = step["resolution"]
        screensize = (scrn[len(scrn)-2]["loc"][2], scrn[len(scrn)-2]["loc"][3])
        print("screen size: ", screensize, "scroll resolution: ", symTab[scroll_resolution], " target_loc:", target_loc)

        at_loc_top_v = int(screensize[0]*at_loc_top)
        at_loc_bottom_v = int(screensize[0] * at_loc_bottom)
        target_loc_v = int(screensize[0]*target_loc)
        print(" target_loc_V: ", target_loc_v, "at_loc_top_v: ", at_loc_top_v, "at_loc_bottom_v: ", at_loc_bottom_v)

        # find all images matches the name and above the at_loc
        print("finding....:", anchor)
        anyancs = [element for index, element in enumerate(scrn) if element["name"] == anchor]
        print("found any anchorss: ", anyancs)
        ancs = [element for index, element in enumerate(scrn) if element["name"] == anchor and element["loc"][0] > at_loc_top_v and element["loc"][2] < at_loc_bottom_v]
        print("found anchorss in bound: ", ancs)
        if len(ancs) > 0:
            # sort them by vertial distance, largest v coordinate first, so the 1st one is the closest.
            vsorted = sorted(ancs, key=lambda x: x["loc"][2], reverse=True)
            print("FFOUND: ", vsorted[0])
            offset = round((target_loc_v - vsorted[0]["loc"][2])/symTab[scroll_resolution])
            print("calculated offset: ", offset, "setting flag var [", step["flag"], "] to be TRUE....")
            symTab[step["flag"]] = True
        else:
            # if anchor is not on the page, set the flag and scroll down 90 of a screen
            offset = 0-round(screensize[0]*0.5/symTab[scroll_resolution])
            symTab[step["flag"]] = False
            print("KEEP scrolling calculated offset: ", offset, "setting flag var [", step["flag"], "] to be FALSE....")

        mouse.scroll(0, offset)
        time.sleep(step["postwait"])


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSearchScroll:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorSearchScroll: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


# this routine scroll until certain a product is right in the middle of the screen and capture its information.
# for grid based layout, it's be enough to do only 1 row, for row based layout, it could be multple rows captured.
# target_anchor: to anchor to adjust postion to
# tilpos: position to adjust anchor to... (+: # of scroll position till screen bottom, -: # of scroll postion from screen top)
def genScrollDownUntil(target_anchor, tilpos, stepN, worksettings, site, theme):
    psk_words = ""
    ex_stat = DEFAULT_RUN_STATUS
    print("DEBUG", "gen_psk_for_scroll_down_until...")
    this_step, step_words = genStepFillData("direct", "False", "position_reached", "", stepN)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("position_reached != True", "", "", "scrollDown"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, smount, stepN):
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 50, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_list", "body", theme, this_step, None)
    psk_words = psk_words + step_words


    # this step search for the lowest position of phrases "free shipping" on the bottom half of the screen, then scroll it to be 1 scroll away from the bottom of the page
    # this action will position the entire product section from image to free shipping ready to be extracted.
    # the whole purpose is that we don't want to do stiching on information pieces to form the complete information block.
    # lateron, this will have to be done somehow with the long review comments, but at in this page anyways.
    # screen, anchor, at_loc, target_loc, flag, resolution, stepN
    this_step, step_words = genStepSearchScroll("screen_info", target_anchor, [35, 100], tilpos, "position_reached", "scroll_resolution", 0.5, site, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words


def get_html_file_dir_loc(result):
    target_loc = [0, 0]

    target_name = "refresh"
    target_type = "anchor icon"
    # target_type = "anchor text"
    print("result: ", result)
    # for e in result:
    #     print(e)

    # now do the search
    targets_found = [element for index, element in enumerate(result) if
                     element["name"] == target_name and element["type"] == target_type]

    print("targets_found: ", targets_found)
    if len(targets_found) > 0:
        # sort found by vertical location.
        refresh_icon_loc = targets_found[len(targets_found)-1]['loc']
        posX = int(refresh_icon_loc[1]) - (int(refresh_icon_loc[3]) - int(refresh_icon_loc[1]))*2
        posY = int(refresh_icon_loc[0]) + int((int(refresh_icon_loc[2]) - int(refresh_icon_loc[0]))/2)
        target_loc = [posX, posY]
    else:
        print("ERROR: screen read unexpected FAILED TO FOUND DIR INPUT BOX")
        target_loc = [0, 0]

    print("target_loc: ", target_loc)

    return target_loc


def get_html_file_name_loc(result):
    target_loc = [0, 0]
    target_name = "File name:"
    # target_type = "anchor icon"
    target_type = "anchor text"
    target_text1 = "name:"
    target_text2 = "name"

    print("result: ", result)
    # now do the search
    targets_found = [element for index, element in enumerate(result) if
                     element["type"] == target_type and (re.search(target_text1, element["text"]) or re.search(target_text2, element["text"]))]

    print("targets_found: ", targets_found)

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
        print("ERROR: screen read unexpected FAILED TO FOUND FILE NAME INPUT BOX")
        target_loc = [0, 0]

    return target_loc


def get_save_button_loc(result):
    target_loc = [0, 0]
    target_name = "cancel"
    # target_type = "anchor icon"
    target_type = "anchor text"
    print("result: ", result)

    # now do the search
    targets_found = [element for index, element in enumerate(result) if
                     element["name"] == target_name and element["type"] == target_type]

    print("targets_found: ", targets_found)

    if len(targets_found) > 0:
        # sort found by vertical location.
        target_loc = targets_found[len(targets_found)-1]['loc']
        posX = target_loc[1] - int((target_loc[3] - target_loc[1])*2.25)
        posY = target_loc[0] + int((target_loc[2] - target_loc[0])/2)
        target_loc = [posX, posY]
    else:
        print("ERROR: screen read unexpected FAILED TO FOUND SAVE BUTTON")
        target_loc = [0, 0]

    return target_loc


# save web page into html file.
def processSaveHtml(step, i, mission, skill):
    global screen_loc
    print("Saving web page to a local html file .....", step)
    ex_stat = DEFAULT_RUN_STATUS
    try:
        dtnow = datetime.now()

        date_word = dtnow.strftime("%Y%m%d")
        print("date word:", date_word)

        fdir = ecb_data_homepath + "/runlogs/"
        fdir = fdir + date_word + "/"

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
        print("hfile: ", hfile)


        # now save the web page into a file.
        pyautogui.hotkey('ctrl', 's')

        # wait till the dialog windows is shown on screen
        time.sleep(3)

        # now a file save dialog box will show up on screen, analyze it to figure out where to type and click.
        ni = processExtractInfo(step, i, mission, skill)

        # get ready the html file path and the file name
        html_file_dir_name = fdir
        print("html_file_dir_name: ", html_file_dir_name)

        html_file_name = step["local"].split(".")[0]
        print("html_file_name: ", html_file_name)


        # locate the html file directory path input text box
        html_file_dir_loc = get_html_file_dir_loc(symTab[step["data_sink"]])
        print("html_file_dir_loc: ", html_file_dir_loc)
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
        print("html_file_name_loc: ", html_file_name_loc)
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
        print("save_button_loc: ", save_button_loc)
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
            ex_stat = "ErrorSaveHtml:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorSaveHtml: traceback information not available:" + str(e)
        print(ex_stat)

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
                    # print("windows: ", n)
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
            ex_stat = "ErrorCheckAppRunning:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorCheckAppRunning: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processBringAppToFront(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    symTab[step["result"]] = False
    try:
        if sys.platform == 'win32':
            names = []

            def winEnumHandler(hwnd, ctx):
                if win32gui.IsWindowVisible(hwnd):
                    n = win32gui.GetWindowText(hwnd)
                    # print("windows: ", n)
                    if n:
                        names.append(n)

            win32gui.EnumWindows(winEnumHandler, None)
            win_title = step["win_title"]
            hwnd = win32gui.FindWindow(None, win_title)

            # Bring the window to the foreground
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # Restore window if minimized
                win32gui.SetForegroundWindow(hwnd)
                symTab[step["result"]] = True
            else:
                print(f"Error: Window with title '{win_title}' not found.")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorBringAppToFront:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorBringAppToFront: traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat