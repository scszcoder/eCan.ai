import os
import os.path
import json
import win32gui
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
from ping3 import ping, verbose_ping

from scraper import *
from Cloud import *
from pynput.mouse import Button, Controller
from readSkill import *

STEP_GAP = 5
symTab = globals()
mouse = Controller()

mission_vars = []
# global function_table
MAX_STEPS = 1000000000

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




def genStepOpenApp(action, saverb, target_type, target_link, anchor_type, anchor_value, args, wait, stepN):
    stepjson = {
        "type": "App Open",
        "action": action,
        "save_rb": saverb,
        "target_type": target_type,
        "target_link": target_link,
        "anchor_type": anchor_type,
        "anchor_value": anchor_value,
        "cargs": args,
        "wait":wait
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepSaveHtml(html_file_name, html_file_var_name, template, root, sink, page, sect, theme, stepN, page_data, option=""):
    stepjson = {
        "type": "Save Html",
        "action": "Save Html",
        "root": root,
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
def genStepExtractInfo(template, root, sink, page, sect, theme, stepN, page_data, option=""):
    stepjson = {
        "type": "Extract Info",
        "root": root,
        "template": template,
        "option": option,
        "data_sink": sink,
        "page": page,
        "page_data_info": page_data,
        "theme": theme,
        "section": sect
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# search information on a screen with a given name and type.
def genStepSearch(screen, names, target_types, logic, result, flag, site, stepN):
    stepjson = {
        "type": "Search",
        "screen": screen,
        "names": names,
        "target_types": target_types,
        "logic": logic,
        "result": result,
        "site": site,
        "status": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


# search some target content on the page, and scroll the target to the target loction on the page.
# at_loc is a rough location, meaning the anchor closest to this location, NOT exactly at this location.
# at_loc is also a 2 dimensional x-y coordinates
def genStepSearchScroll(screen, anchor, at_loc, target_loc, flag, resolution, site, stepN):
    stepjson = {
        "type": "Search Scroll",
        "action": "Search Scroll",
        "anchor": anchor,
        "at_loc": at_loc,
        "target_loc": target_loc,
        "screen": screen,
        "resolution": resolution,
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
def genStepMouseScroll(action, screen, val, unit, resolution, ran_min, ran_max, stepN):
    stepjson = {
        "type": "Mouse Scroll",
        "action": action,
        "screen": screen,
        "amount": val,
        "resolution": resolution,
        "random_min": ran_min,
        "random_max": ran_max,
        "unit": unit
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def genStepMouseClick(action, action_args, saverb, screen, target, target_type, template, nth, offset_from, offset, offset_unit, move_pause, post_wait, stepN):
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
def genStepTextInput(action, saverb, txt, speed, key_after, wait_after, stepN):
    stepjson = {
        "type": "Text Input",
        "action": action,
        "save_rb": saverb,
        "text": txt,
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
def genStepGoto(gotostep, inpipe, returnstep, stepN):
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

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepListDir(dirname, fargs, result_var, stepN):
    stepjson = {
        "type": "List Dir",
        "dir": dirname,
        "fargs": fargs,
        "result": result_var
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepCheckExistence(fname, result_var, stepN):
    stepjson = {
        "type": "List Dir",
        "file": fname,
        "result": result_var
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
def genStepUseSkill(skname, skfname, skargs, output, stepN):
    stepjson = {
        "type": "Use Skill",
        "skill_name": skname,
        "skill_file_name": skfname,
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


def read_screen(site_page, page_sect, page_theme, layout, mission, sfile):
    names = []
    settings = mission.parent_settings
    def winEnumHandler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            n = win32gui.GetWindowText(hwnd)
            # print("windows: ", n)
            if n:
                names.append(n)

    win32gui.EnumWindows(winEnumHandler, None)

    #print(names)
    window_handle = win32gui.FindWindow(None, names[0])
    window_rect = win32gui.GetWindowRect(window_handle)
    print("window: ", names[0], " rect: ", window_rect)

    if not os.path.exists(os.path.dirname(sfile)):
        os.makedirs(os.path.dirname(sfile))

    #now we have obtained the top window, take a screen shot.
    im0 = pyautogui.screenshot(imageFilename=sfile, region=(window_rect[0], window_rect[1], window_rect[0] + 3300, window_rect[0] + 2000))

    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1B: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    #upload screen to S3
    upload_file(settings["session"], sfile, settings["token"], "screen")

    m_skill_names = mission.getSkillNames()
    m_psk_names = mission.getPSKFileNames()
    m_csk_names = mission.getCSKFileNames()

    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1C: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # request an analysis of the uploaded screen
    request = [{
        "id": mission.getMid(),
        "bid": mission.getBid(),
        "os": mission.getPlatform(),
        "app": mission.getApp(),
        "domain": mission.getSite(),
        "page": site_page,
        "layout": layout,
        "skill_name": m_skill_names[0],
        "psk": m_psk_names[0],
        "csk": m_csk_names[0],
        "lastMove": page_sect,
        "options": "{}",
        "theme": page_theme,
        "imageFile": sfile,
        "factor": 0.0
    }]

    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1D: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    result = req_cloud_read_screen(settings["session"], request, settings["token"])
    print("result::: ", result)
    jresult = json.loads(result['body'])
    print("cloud result data: ", jresult["data"])
    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1E: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    if "errors" in jresult:
        screen_error = True
        print("ERROR Type: ", jresult["errors"][0]["errorType"], "ERROR Info: ", jresult["errors"][0]["errorInfo"], )
    else:
        print("cloud result data body: ", result["body"])
        jbody = json.loads(result["body"])
        for p in jbody["data"]:
            if p["name"] == "paragraph":
                for tl in p["txt_struct"]:
                    print("TXT LINE: ", tl["text"])

                print("PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP")

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
    print("Due to supply time lag, this mission is halted till  hours later....")
    #should kick off a timer to wait .

def processDone(step, i):
    print("Mission accomplished!")

def processWait(step, i):
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
    return i+1



def processExtractInfo(step, i, mission, skill):
    # mission_id, session, token, top_win, skill_name, uid
    print("Extracting info....", mission, " SK: ", skill)
    print("mission[", mission.getMid(), "] cuspas: ", mission.getCusPAS())
    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    global screen_error
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
    sfile = "C:/Users/songc/PycharmProjects/testdata/"
    #sfile = sfile + settings["uid"] + "/win/adspower/"
    #sfile = sfile + "scrn" + settings["uid"] + "_" + dt_string + ".png"
    if skill.getPrivacy() == "public":
        ppword = skill.getPrivacy()
    else:
        ppword = mission.parent_settings["uid"]

    print("mission[", mission.getMid(), "] cuspas: ", mission.getCusPAS())
    platform = mission.getPlatform()
    app = mission.getApp()
    site = mission.getSite()
    #     local image:  C:/Users/songc/PycharmProjects/ecbot/resource/runlogs/date/b0m0/win_chrome_amz_home/browse_search_kw/images/scrnsongc_yahoo_1678175548.png"

    fdir = step["root"] + "/resource/runlogs/"
    fdir = fdir + date_word + "/"

    fdir = fdir + "b" + str(mission.getMid()) + "m" + str(mission.getBid()) + "/"
    # fdir = fdir + ppword + "/"
    fdir = fdir + platform + "_" + app + "_" + site + "_" + step["page"] + "/skills/"
    fdir = fdir + skill.getName() + "/images/"
    sfile = fdir + "scrn" + mission.parent_settings["uid"] + "_" + dt_string + ".png"
    print("sfile: ", sfile)


    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp1A: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


    result = read_screen(step["page"], step["section"], step["theme"], page_layout, mission, sfile)
    symTab[step["data_sink"]] = result
    print(">>>>>>>>>>>>>>>>>>>>>screen read time stamp2: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    return i+1

# text input, type only, the click onto the correction place to type should happen before this.
# action: action to perform here - simply text input
#  text: txt to be input.
#  speed: type speed.
#  key_after: key to hit after textinput. (could be "", "enter",
#  wait_after: number of seconds to wait after key_after action.
def processTextInput(step, i):
    global page_stack
    global current_context
    print("Keyboard typing......")
    names = []
    #sd = symTab[step["screen"]]
    #obj_box = find_clickable_object(sd, step["target"], step["target_type"], step["nth"])
    #loc = get_clickable_loc(obj_box, step["offset_from"], step["offset"])

    # def winEnumHandler(hwnd, ctx):
    #     if win32gui.IsWindowVisible(hwnd):
    #         n = win32gui.GetWindowText(hwnd)
    #         if n:
    #             names.append(n)
    #
    # win32gui.EnumWindows(winEnumHandler, None)
    #
    # window_handle = win32gui.FindWindow(None, names[0])
    # window_rect = win32gui.GetWindowRect(window_handle)
    #
    # txt_boxes = list(filter(lambda x: x["name"] == "text_input_box" and x["type"] == "info", symTab["last_screen"]))
    # print("found input locations:", len(txt_boxes))
    # if len(txt_boxes) > 0:
    #     loc = txt_boxes[0]["loc"]
    #     print("loc @ ", loc)
    # print("global loc@ ", int(loc[0])+window_rect[0], " ,  ", int(loc[1])+window_rect[1])
    #
    # pyautogui.moveTo(int(loc[0])+window_rect[0], int(loc[1])+window_rect[1])

    #pyautogui.moveTo(loc[0], loc[1])
    #pyautogui.click()          # 0th position is X, 1st position is Y
    pyautogui.doubleClick()
    print("typing.....", step["text"][0])
    time.sleep(5)
    pyautogui.click()
    pyautogui.write(step["text"][0],  interval=0.5)
    pyautogui.press('enter')
    time.sleep(1)
    pyautogui.press(step['key_after'])
    if step['key_after'] != "":
        print("after typing, pressing:", step['key_after'], "then wait for:", step['wait_after'])
        pyautogui.press(step['key_after'])
        time.sleep(step['wait_after'])

    # now save for roll back if ever needed.
    # first remove the previously save rollback point, but leave up to 3 rollback points
    while len(page_stack) > 3:
        page_stack.pop()
    # now save the current juncture.
    current_context = build_current_context()
    page_stack.append({"pc": i, "context": current_context})

    return i + 1


def find_clickable_object(sd, target, template, target_type, nth):
    print("LOOKING FOR:", target, "   ", template,  "   ", target_type, "   ", nth)
    found = {"loc": None}
    reg = re.compile(target+"[0-9]+")
    # grab all instances of the target object.
    objs = [x for x in sd if (x["name"] == target or reg.match(x["name"])) and x["type"] == target_type]

    # convert possible string to integer
    for o in objs:
        o["loc"] = [int(o["loc"][0]), int(o["loc"][1]), int(o["loc"][2]), int(o["loc"][3])]

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
            my_array[ri, ci] = ob

        # now, take out the nth element
        if nth[0] >= 0 and nth[1] >= 0:
            found = my_array[nth[0], nth[1]]
        elif nth[1] >= 0:
            found = ysorted[nth[1]]
        else:
            found = xsorted[nth[0]]

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
        click_loc = ((center[1] + int(offset[0]*box_length), center[0] + int(offset[1]*box_height)))

    return click_loc


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
    if step["target_type"] != "direct" and step["target_type"] != "expr":
        sd = symTab[step["screen"]]
        print("finding: ", step["text"], " target name: ", step["target_name"])
        print("from data: ", sd)
        obj_box = find_clickable_object(sd, step["target_name"], step["text"], step["target_type"], step["nth"])
        print("obj_box: ", obj_box)
        loc = get_clickable_loc(obj_box, step["offset_from"], step["offset"], step["offset_unit"])

    else:
        # the location is already calculated directly and stored here.
        if step["target_type"] == "direct":
            print("obtain directly.....")
            box = symTab[step["target_name"]]
            loc = box_center(box)
        else:
            print("obtain thru expression.....", step["target_name"])
            exec("global click_target\nclick_target = " + step["target_name"])
            print("box: ", symTab["click_target"])
            loc = box_center(symTab["click_target"])

    print("calculated locations:", loc)

    names = []
    def winEnumHandler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            n = win32gui.GetWindowText(hwnd)
            if n:
                names.append(n)

    win32gui.EnumWindows(winEnumHandler, None)

    # find the top window and get its size and location.
    window_handle = win32gui.FindWindow(None, names[0])
    window_rect = win32gui.GetWindowRect(window_handle)
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
    elif step["action"] == "Right CLick":
        pyautogui.click(button='right')
    elif step["action"] == "Drag Drop":
        # code drop location is embedded in action_args, the code need to added later to process that....
        pyautogui.dragTo(loc[0], loc[1], duration=2)

    time.sleep(step["post_wait"])

    # now save for roll back if ever needed.
    # first remove the previously save rollback point, but leave up to 3 rollback points
    while len(page_stack) > 3:
        page_stack.pop()
    # now save the current juncture.
    current_context = build_current_context()
    page_stack.append({"pc": i, "context": current_context})

    return i + 1

# max 4 combo key stroke
def processKeyInput(step, i):
    global page_stack
    global current_context
    print("Keyboard Action..... hot keys")
    keys = step["action_value"].split(',')

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

    return i + 1

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
    print("screen_data: ", screen_data)
    screen_vsize = screen_data[len(screen_data) - 2]['loc'][2]

    if step["unit"] == "screen":
        print("SCREEN SIZE: ", screen_data[len(screen_data) - 2]['loc'], "resultion var: ", step["resolution"], " val: ", symTab[step["resolution"]])
        if type(step["amount"]) is str:
            scroll_amount = int(((symTab[step["amount"]]/100)*screen_vsize)/symTab[step["resolution"]])
        else:
            scroll_amount = int(((step["amount"]/100)*screen_vsize)/symTab[step["resolution"]])
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
        scroll_amount = scroll_amount - random.randrange(step["random_min"], step["random_max"])

    print("after randomized Scroll Amount: ", scroll_amount)
    mouse.scroll(0, scroll_amount)
    return i + 1


def processOpenApp(step, i):
    print("Opening App .....", step["target_link"] + " " + step["cargs"])
    if step["target_type"] == "browser":
        url = step["target_link"]
        webbrowser.open(url, new=0, autoraise=True)
    else:
        subprocess.call(step["target_link"] + " " + step["cargs"])

    time.sleep(step["wait"])
    return i+1

# create a new variable in the name space and assign initial value to it.
# data_name: name of the variable.
# key_name, key_value, could be a dictionary with a key-value paire.
def processCreateData(step, i):
    print("Creating Data .....")
    global mission_vars
    if step["key_name"] == "NA":
        # this is the case of direct assignment.
        if step["data_type"] == "expr":
            print("TBEx: ", step["data_name"] + " = " + step["key_value"])
            symTab[step["data_name"]] = None
            exec("global " + step["data_name"] + "\n" + step["data_name"] + " = " + step["key_value"])
            print(step["data_name"] + " is now: ", symTab[step["data_name"]])

        else:
            symTab[step["data_name"]] = step["key_value"]
    else:
        if not re.match("\[.*\]|\{.*\}", step["key_value"]):
            symTab[step["data_name"]] = {step["key_name"]: step["key_value"]}
        else:
            symTab[step["data_name"]] = {step["key_name"]: json.loads(step["key_value"])}

    mission_vars.append(step["data_name"])
    return i + 1

# this is for add an object to a list/array of object, or add another key-value pair to a json object.
# from: value source
# to: value destination
# result: the destination variable when operation is a "pop" in which case, "from" is the index, "to" is the list variable name.
# fill_type: "assign"/"copy"/"append"/"prepend"/"merge"/"clear"/"pop":
def processFillData(step, i):
    print("Filling Data .....", step)

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
    return i + 1

# basically context switching here...
def processEndException(step, i, step_keys):
    global exception_stack
    global page_stack
    global in_exception
    print("Return from Exception .....")
    # basically do a rollback, and resume running from the last rollback point.
    rollback_point = page_stack.pop()
    idx = rollback_point["pc"]
    restore_current_context(rollback_point["context"])
    exception_stack.pop()
    if len(exception_stack) == 0:
        # clear the exception flag.
        in_exception = False

    return idx

# this is the exception handler, basically keep retry ping the target website until success.
def processExceptionHandler(step, i, step_keys):
    max_retries = 3
    min_retry_back_off = 3
    max_retry_back_off = 10
    site = "example.com"
    n_retries = 0
    global net_connected

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

    return i+1


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
    condition = step["condition"]

    if evalCondition(condition):
        idx = i + 1
    else:
        idx = step_keys.index(step["if_else"])
        print("else: ", step["if_else"], "else idx: ", idx)
    return idx


# "type": "Repeat",
# "lc_name": loop counter name. need to be unique, usually is the stepname.
# "until": loop condition condition,
# "count": repeat count,
# "end": loop end marker.
def processRepeat(step, i,  step_keys):
    print("Looping.....: ", step)

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

    return end_idx

# assumption: data is in form of a single json which can be easily dumped.
def processLoadData(step, i):
    print("Loading Data .....")
    with open(step["file_link"], 'r') as f:
        symTab[step["data_name"]] = json.load(f)

    return i + 1


def processSaveData(step, i):
    print("Saving Data .....")
    with open(step["file_link"], 'w') as f:
        json.dump(symTab[step["data_name"]], f)
    return i+1

# fname: external script/function name  - very IMPORTANT： this is calling python routine either in a file or a function， this is different from
#          psk function/subroutine
# args: arguments to the external functions.
# entity: "are we calling a script or function?"
# output: output data variable
def processCallExtern(step, i):
    print("Run External Script/code as strings .....")

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

    return i+1

# this is for call a skill function.
# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def processUseSkill(step, i, stack, sk_stack, sk_table, step_keys):
    global skill_code

    # push current address pointer onto stack,
    stack.append(i+1)
    sk_stack.append(step["skill_name"])

    #save current fin, fout whatever that is.
    stack.append(symTab["fout"])
    stack.append(symTab["fin"])

    # push function output var to the stack
    stack.append(step["output"])

    # push input args onto stack
    stack.append(step["skill_args"])

    fin_par = stack.pop()
    symTab["fin"] = symTab[fin_par]
    print("geting skill call input parameter: ", fin_par, " [val: ", symTab[fin_par])

    # start execuation on the function, find the function name's address, and set next pointer to it.
    # the function name address key value pair was created in gen_addresses
    idx = step_keys.index(sk_table[step["skill_name"]])

    return idx

# this is for call a skill function.
# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def processOverloadSkill(step, i, stack, step_keys):
    global skill_code
    global skill_table
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

    return idx


# this is for call a skill function.
# fname: function name.
# args: function arguments
# return_point: where does function return. (maybe not needed with stack.)
# output: function returned result
def processCallFunction(step, i, stack, func_table, step_keys):


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

    return idx


def processReturn(step, i, stack, step_keys):

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

    return next_i


# this is a stub/marker for end of if-else, end of function, end of loop etc. SC - 20230723 total mistake of this function....
# whatever written here should be in address generation.
def processStub(step, i, stack, sk_stack, sk_table, step_keys):
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
            if return_var_name != "" and step["fargs"] != "":
                symTab[return_var_name] = symTab[step["fargs"]]

            symTab["fin"] = stack.pop()
            symTab["fout"] = stack.pop()

            #  set the pointer to the return to pointer.
            next_i = stack.pop()

    return next_i


def processGoto(step, i,  step_keys):
    step_keys.index(step["goto"])
    return step_keys.index(step["goto"])


def processListDir(step, i):
    lof = os.listdir(step["dir"])
    symTab[step["result"]] = [f for f in lof if x.endswith(step["fargs"])]  # fargs contains extension such as ".pdf"
    return i + 1

def processCheckExistence(step, i):
    symTab[step["result"]] = os.path.isfile(step["file"])
    return i + 1

# create a data structure holder for anchor....
# "type": "Search",
# "action": "Search",
# "screen": screen,
# "name": name,
# "target_type": target_type, target type
# "result": result, result varaibel continas result.
# "status": flag - flag variable contains result
def processSearch(step, i):
    print("Searching....", step["target_types"])
    global in_exception
    scrn = symTab[step["screen"]]
    target_names = step["names"]           #contains anchor/info name, or the text string to matched against.
    target_types = step["target_types"]
    logic = step["logic"]

    fault_names = ["site_not_reached", "bad_request"]
    fault_found = []

    found = []
    n_targets_found = 0

    print("Searching screen....", scrn)

    if not (type(target_names) is list):
        target_names = [step["names"]]  # make it a list.
        target_types = [step["target_types"]]

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
        fault_found = [e for i, e in enumerate(scrn) if e["name"] in fault_names and e["type"] == "anchor text"]
        site_conn = ping(step["site"])
        if len(fault_found) > 0 or (not site_conn):
            # exception has occured, flag it.
            in_exception = True

    return i + 1



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

    # find all anchors matches the name and above the at_loc
    print("finding....:", anchor)
    anyancs = [element for index, element in enumerate(scrn) if element["name"] == anchor]
    print("found any anchorss: ", anyancs)
    ancs = [element for index, element in enumerate(scrn) if element["name"] == anchor and element["loc"][0] > at_loc_top_v and element["loc"][2] < at_loc_bottom_v]
    print("found anchorss in bound: ", ancs)
    if len(ancs) > 0:
        # sort them by vertial distance, largest v coordinate first, so the 1st one is the closest.
        vsorted = sorted(ancs, key=lambda x: x["loc"][2], reverse=True)
        print("FFOUND: ", vsorted[0])
        offset = int((target_loc_v - vsorted[0]["loc"][2])/symTab[scroll_resolution])
        print("calculated offset: ", offset, "setting flag var [", step["flag"], "] to be TRUE....")
        symTab[step["flag"]] = True
    else:
        # if anchor is not on the page, set the flag and scroll down 90 of a screen
        offset = 0-int(screensize[0]*0.5/symTab[scroll_resolution])
        symTab[step["flag"]] = False
        print("KEEP scrolling calculated offset: ", offset, "setting flag var [", step["flag"], "] to be FALSE....")

    mouse.scroll(0, offset)
    return i + 1


# this routine scroll until certain a product is right in the middle of the screen and capture its information.
# for grid based layout, it's be enough to do only 1 row, for row based layout, it could be multple rows captured.
# target_anchor: to anchor to adjust postion to
# tilpos: position to adjust anchor to... (+: # of scroll position till screen bottom, -: # of scroll postion from screen top)
def genScrollDownUntil(target_anchor, tilpos, stepN, root, page, sect, site, theme):
    psk_words = ""
    print("DEBUG", "gen_psk_for_scroll_down_until...")
    this_step, step_words = genStepFillData("direct", "False", "position_reached", "", stepN)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("postition_reached != True", "", "", "scrollDown"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 50, "screen", "scroll_resolution", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", root, "screen_info", "product_list", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    # this step search for the lowest position of phrases "free shipping" on the bottom half of the screen, then scroll it to be 1 scroll away from the bottom of the page
    # this action will position the entire product section from image to free shipping ready to be extracted.
    # the whole purpose is that we don't want to do stiching on information pieces to form the complete information block.
    # lateron, this will have to be done somehow with the long review comments, but at in this page anyways.
    # screen, anchor, at_loc, target_loc, flag, resolution, stepN
    this_step, step_words = genStepSearchScroll("screen_info", target_anchor, [1, 90], tilpos, "position_reached", "scroll_resolution", site, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step, psk_words


def get_html_file_dir_loc(result):
    target_loc = [0, 0]

    target_name = "refresh0"
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
        posX = int(refresh_icon_loc[1]) - (int(refresh_icon_loc[3]) - int(refresh_icon_loc[1]))*2.25
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
    print("Saving web page to a local html file .....", step)

    dtnow = datetime.now()

    date_word = dtnow.strftime("%Y%m%d")
    print("date word:", date_word)

    fdir = step["root"] + "/resource/runlogs/"
    fdir = fdir + date_word + "/"

    platform = mission.getPlatform()
    app = mission.getApp()
    site = mission.getSite()

    fdir = fdir + "b" + str(mission.getMid()) + "m" + str(mission.getBid()) + "/"
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
    pyautogui.moveTo(html_file_dir_loc[0], html_file_dir_loc[1])
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
    pyautogui.moveTo(html_file_name_loc[0], html_file_name_loc[1])
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
    pyautogui.moveTo(save_button_loc[0], save_button_loc[1])
    time.sleep(2)
    pyautogui.click()

    # give enough to save html, as it could take some time.
    time.sleep(65)

    # ni is already incremented by processExtract(), so simply return it.
    return ni
