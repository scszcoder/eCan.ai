import json
import re
import parser
import ast
import pyautogui
from datetime import datetime
import time
from Cloud import *
import ctypes
import os
import subprocess
import win32gui
import platform

# syntax for the skill file:
# a series of steps: each step starts with
# a single line step number:
# followed by a json data describe the line.
# the file can have comments starts with #
# example:
#  header:
#  {
#     name : "whatever",                # skill name.
#     os   : "windows/mac/linux"        # platform.
#     version: ""                       # starts from 1.0
#     author: ""
#     skid:   ""                        #unique ID for skill
#     description: ""                   # max 2048 char
#  }
#  step 1:
#  {
#     type : "Loop Start",
#  }
#    loop ends can use "Check Condition"
#  step 3:
#  {
#    type: "App Open",
#    action: "Click",
#    target_type: "Icon"
#    target_link: "C:/path/to/icon/file.png"
#    anchor_type: "Text"            #this should be just the app name. (the text below the icon)
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)
#  }
#  step 4:
#  {
#    type: "Tab Open",
#    action: "Key Shortcut",
#    action_value: "Ctrl-Alt-Tab"
#    target: "NA"
#    target_link: "NA"
#    anchor_type: "Text"
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)
#  }
#  step 5:
#  {
#    type: "Button Click",
#    action: "Click",              # could be Double Click, Right Click
#    target: "NA"
#    target_link: "NA"
#    anchor_type: "Text"
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)  # unit is not in pixel, but in the unit of text height.
#    condition:
#  }
#  step 6:
#  {
#    type: "Text Input",
#    action: "Key In",
#    action_value: "Ctrl-Alt-Tab"
#    target: "NA"
#    target_link: "NA"
#    anchor_type: "Text"
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)
#    condition:
#  }
#  step 7:
#  {
#    type: "Info Extract",
#    action: "find text",
#    template: "ABC"
#    target_link: "NA"
#    anchor_type: "Text"
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)
#    condition: ""
#  }
#  step 8:
#  {
#    type: "Info Extract",
#    action: "extract image",
#    template: "C:/path/to/icon/file.png"
#    data_sink: ""              #same syntax as python data hierarchy representation
#    anchor_type: "Text"
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)
#    bound_left:  "offset value"     # in unit of text letter width
#    bound_left_type:  "Text/Icon"
#    bound_left_value: "Text Content or link to image"
#    bound_right:
#    bound_right_type:
#    bound_right_value:
#    bound_top:  "offset value"     # in unit of text letter height
#    bound_top_type:
#    bound_top_value:
#    bound_bottom:
#    bound_bottom_type:
#    bound_bottom_value:
#  }
#  step 9:
#  {
#    type: "Browse",
#    action: "Scoll Down",    # could be Scroll Up as well.
#    action_value: "5"        # number of mouse wheel roll steps....
#    condition:
#  }
#  step 10:
#  {
#    type: "Wait",
#    action: "Wait",            # could be Scroll Up as well.
#    action_value: "5"          # number of seconds to wait.
#  }
#  step 11:
#  {
#    type: "Halt",
#    action: "Halt",            # could be Scroll Up as well.
#    action_value: "600"        # number of minutes to wait.
#  }
#  step 12:
#  {
#    type: "Done",
#    action: "Done",            # could be Scroll Up as well.
#  }
#  step 13:
#  {
#    type: "Exception",
#    action: "Handle Exception",            # could be Scroll Up as well.
#  }
#  step 14:
#  {
#     type: "Use Skill",
#     name: "RunABC"
#  }
#  step 15:
#  {
#    type: "Create Data",
#    data_type: "String",       # Int, Float, List, Data, Icon
#    data_name: "Star"          # Score, Unit, Amount, .....
#    data_value: "NA"
#    size: "NA"                 # of element in a list (in case of being a list)
#  }
#  step 16:
#  {
#    type: "Fill Data",
#    action: "Append",          # Modify
#    data_type: "String",       # Int, Float, List, Data, Icon
#    data_name: "Star"          # Score, Unit, Amount, .....
#    data_value: "NA"
#    target_link: "NA"
#    anchor_type: "Text"
#    anchor_value: "ABC"
#    anchor_loc: (up, left, down, right)
#    condition:
#  }
#  step 17:
#  {
#    type: "Check Condition",
#    condition: "",          # can be compound with Not And Or and bracket, other keywords Exists
#    if_true: "step number or routine name",       # Int, Float, List, Data, Icon
#    else: "step number or routine name"          # Score, Unit, Amount, .....
#  }
#  step 18:
#  {
#    type: "Save Data",
#    file: "file path",          # will save all data accumulated so far and save them to a file.
#  }
#  step 19:
#  {
#    type: "Load Data",
#    file: "file path",          # will load all data from a file.
#  }
#  step 20:
#  {
#    type: "Create Anchor",
#    anchor_name: "ABC"
#    anchor_type: "text/image",          # will load all data from a file.
#    anchor_value: "file path",           # either text contents or image template file path
#  }
# process the file in 2 passes, 1) get rid of all comments starts with #
# 2) divide files into blocks

symTab = globals()
MAXNEST = 18                    # code level skill nest (skill calling skill)
MAXRECUR = 18                   # max level of recurrsion
MAXSTEPS = 2048                 # code level, maximum number of steps of any task. should never be more complicated.

nest_level = 0
steps = []
last_step = -1
next_step = 0

running = False

# read an lsk fill into steps (json data structure)
# input: steps - data structure to hold the results.
#        name_prefix - name to add to front of step # to make step name unique.
#                       typically this is the cascade of userID, skill name.
#       skill_file - full path file name of the .lsk file.
# output: None (sort of in step already)
# Note:
def readSkillFile(name_prefix, skill_file, lvl = 0):
    global steps
    step_keys = []
    json_as_string = open(skill_file, 'r')
    # Call this as a recursive function if your json is highly nested
    lines = [re.sub("#.*", "", one_object.rstrip()) for one_object in json_as_string.readlines()]
    useful_lines = filter(lambda x: x.rstrip(), lines)
    slines = []
    key = ""
    for l in useful_lines:
        if re.match("^step +.*:", l) or re.match("^header.*:", l):
            last_key = key
            l = l[0:len(l)-1]               #get rid of :
            if re.match("step", l):
                stepName = (l.split())[1]   # extract the step name.
                print(stepName)
                key = name_prefix + "!" + "step" + stepName
                # also need to modify the step name for condition statement if any.
            else:
                key = name_prefix + "!" + l
                print("matched header....", key)

            if len(slines) > 0:
                jlines = ''.join(slines)
                print("jlines:", jlines)
                step = json.loads(jlines)
                symTab[last_key] = step                      # make a variable that holds the json data structure.
                step_keys.append(last_key)               # also push this data into an list.
                slines = []
                print("reading in:", last_key, ", ", symTab[last_key])
                if "type" in step:
                    if step["type"] == "Use Skill":
                        subskill_file = step["name"]
                        subskill_file_name = os.path.basename(subskill_file)
                        # assume file name is in the format of *.lsk
                        subskill_name = subskill_file_name.split('.')[0]
                        lvl = lvl + 1
                        if lvl > MAXNEST:
                            print("ERROR: maximum level of nested skill reached!!!!")
                        else:
                            prefix = last_key + "_" + subskill_name
                            print("opening subskill...." + subskill_file)   #now how to prevent name convention conflict/duplicate?
                            step_keys = step_keys + readSkillFile(prefix, subskill_file, lvl)

        else:
            slines.append(l)

    # process the last item.
    if len(slines) > 0:
        jlines = ''.join(slines)
        step = json.loads(jlines)
        symTab[key] = step  # make a variable that holds the json data structure.
        step_keys.append(key)  # also push this data into an list.
        slines = []
        print("reading in last:", key, ", ", symTab[key])
        if "type" in step:
            if step["type"] == "Use Skill":
                subskill_file = step["name"]
                subskill_file_name = os.path.basename(subskill_file)
                # assume file name is in the format of *.lsk
                subskill_name = subskill_file_name.split('.')[0]
                lvl = lvl + 1
                if lvl > MAXNEST:
                    print("ERROR: maximum level of nested skill reached!!!!")
                else:
                    prefix = key + "_" + subskill_name
                    print("opening subskill...." + subskill_file)  # now how to prevent name convention conflict/duplicate?
                    step_keys = step_keys + readSkillFile(prefix, subskill_file, lvl)

    #for k in step_keys:
    #    print("steps: ", k, " -> ", symTab[k])
    #    steps.append({k : symTab[k]})
    #print("steps: ", steps)
    #return steps
    return step_keys

# settings contains the following info:
# reading_speed - words per minute
# pay attention amazon's choice, best seller, sponsored, top N reviews, price, price review rating ratio, particular brands - Yes/No
# browse sequence, - straight down, go thru to bottom first, back up and go thru down again slowly.
# which section spends extra time browsing?
# total time spent limit for this routine
# num of good reviews to read
# num of bad reviews to read
# num of products to browse,
# all of the above should be decided on the cloud and send to the client in form a list of psk to finish. each psk should be a
# very small section of the entire mission.
#
# on psk side, what's fundamental instructions to support above:
#

def runAllSteps(steps, settings):
    global last_step
    global next_step
    last_step = -1
    next_step = 0
    running = True
    print("running all steps.....")
    for k in steps:
        print("steps: ", k, " -> ", symTab[k])
    print("=====================================")
    while next_step <= len(steps)-1 and running:
        print("len steps:", len(steps), "next step:", next_step)
        run1step(steps, settings)

def runNSteps(steps, prev_step, i_step, e_step, settings):
    global last_step
    global next_step
    last_step = prev_step
    next_step = i_step
    running = True
    print("running N steps.....")
    while next_step <= e_step and running:
        print("len steps:", len(steps), "next step:", next_step)
        run1step(steps, settings)


def run1step(steps, settings):
    global next_step
    global last_step

    i = next_step
    step = symTab[steps[i]]
    print("running step [", i, "]: ",  steps[i], "step:", step)
    if "type" in step:
        if step["type"] == "Halt":
            processHalt(step)
        elif step["type"] == "Wait":
            processWait(step)
        elif step["type"] == "Browse":
            processBrowse(step)
        elif step["type"] == "Extract Info":
            #
            processExtractInfo(step, steps[i], settings)
        elif step["type"] == "Text Input":
            processTextInput(step)
        elif step["type"] == "Mouse Click":
            processClick(step)
        elif step["type"] == "Line Location":
            processRecordLineLocation(step)
        elif step["type"] == "Mouse Scroll":
            processScroll(step)
        elif step["type"] == "Calibrate Scroll":
            processCalibrateScroll(step)
        elif step["type"] == "Key Input":
            processHotKey(step)
        elif step["type"] == "App Open":
            processOpenApp(step)
        elif step["type"] == "Create Data":
            processCreateData(step)
        elif step["type"] == "Fill Data":
            processFillData(step)
        elif step["type"] == "Exception":
            processException(step, steps[i])
        elif step["type"] == "Check Condition":
            i = processCheckCondition(step, steps[i])
        elif step["type"] == "Load Data":
            processLoadData(step)
        elif step["type"] == "Save Data":
            processSaveData(step)
        elif step["type"] == "Search":
            processSearch(step)
        elif step["type"] == "Run Script":
            processRunScript(step)
        elif step["type"] == "Repeat":
            processRepeat(steps, step, steps[i], settings)
        else:
            print("skip header or unrecognized step")

        last_step = next_step
        if step["type"] != "Check Condition":
            next_step = i + 1
        else:
            next_step = i
    else:
        next_step = i + 1


def cancelRun():
    global next_step
    global last_step
    global running

    running = False
    last_step = -1
    next_step = 0

def pauseRun():
    global running
    running = False

def continueRun(steps, settings):
    global next_step
    global last_step
    global running
    i = next_step
    running = True
    while i <= len(steps)-1 and running:
        run1step(steps, settings)


def processHalt(step):
    print("Due to supply time lag, this mission is halted till  hours later....")
    #should kick off a timer to wait .

def processDone(step):
    print("Mission accomplished!")

def processWait(step, settings):
    print("waiting...... make mouse pointer wonder a little bit!")
    wtime = 1
    if step["time"] == "":
        # calculate wait based on page contents, and reading speed.
        print("waiting for last screen ", wtime, " seconds....")
        screen = symTab["last_screen"]
    elif step["time"].isnumeric() == False:
        # calculate wait based on page contents, and reading speed.
        screen = symTab[step["time"]]
        print("waiting for screen ", wtime, " seconds....")
    else:
        wtime = int(step["time"])
        print("waiting for ", wtime, " seconds....")

    time.sleep(wtime)

def processBrowse(step):
    print("browsing the page....")


def processExtractInfo(step, step_name, settings):
    # mission_id, session, token, top_win, skill_name, uid
    print("Extracting info....")
    global screen_error
    screen_error = False
    time.sleep(3)
    now = datetime.now()

    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    dt_string = str(int(now.timestamp()))
    print("date string:", dt_string)
    sfile = "C:/Users/Teco/PycharmProjects/ecbot/resource/songc_yahoo/win/chrome_amz_amazon_home/skills/browse_search_kw/images/"
    #sfile = sfile + settings["uid"] + "/win/adspower/"
    #sfile = sfile + "scrn" + settings["uid"] + "_" + dt_string + ".png"
    sfile = sfile + "scrn" + settings["uid"] + "_" + dt_string + ".png"
    print("sfile: ", sfile)

    # window_handle = win32gui.FindWindow(None, "Chrome")
    # window_rect = win32gui.GetWindowRect(window_handle)
    # EnumWindows = ctypes.windll.user32.EnumWindows
    # EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    #
    # titles = []
    #
    # EnumWindows(EnumWindowsProc(foreach_window), 0)
    #
    # print(titles)
    #
    names = []

    def winEnumHandler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            n = win32gui.GetWindowText(hwnd)
            if n:
                names.append(n)

    win32gui.EnumWindows(winEnumHandler, None)

    #print(names)
    window_handle = win32gui.FindWindow(None, names[0])
    window_rect = win32gui.GetWindowRect(window_handle)
    print("window: ", names[0], " rect: ", window_rect)

    # set window position and size.
    win32gui.MoveWindow(window_handle, window_rect[0], window_rect[1], window_rect[0] + 3300, window_rect[0] + 2000, True)

    im0 = pyautogui.screenshot(imageFilename=sfile, region=(window_rect[0], window_rect[1], window_rect[0] + 3300, window_rect[0] + 2000))

    print("platform:", platform.platform())
    #upload file onto S3
    send_screen(sfile)  # sfile should be the full path.
    request = [{
        "id": settings["mission_id"],
        "os": platform.system().lower()[0:3],
        "app": "chrome",
        "domain": "amz",
        "page": step["page_name"],
        "skill_name": settings["skill_name"],
        "psk": settings["lsk"],
        "csk": settings["csk"],
        "lastMove": step["sect_name"],
        "ssk": "{}",
        "imageFile": sfile
    }]
    # request for screen analysis
    result = req_cloud_read_screen(settings["session"], request, settings["token"])
    jresult = json.loads(result)
    print("cloud result: ", jresult)
    print("cloud result data: ", jresult["data"])
    if "errors" in jresult:
        screen_error = True
        print("ERROR Type: ", jresult["errors"][0]["errorType"], "ERROR Info: ", jresult["errors"][0]["errorInfo"], )
    else:
        jresponse = json.loads(jresult["data"]["reqScreenTxtRead"])
        print("cloud result data status code: ", jresponse["statusCode"])
        print("cloud result data body: ", jresponse["body"])
        jbody = json.loads(jresponse["body"])
        print("cloud result data body id: ", jbody["id"])
        print("cloud result data body data: ", jbody["data"])
        print("cloud result data body data length: ", len(jbody["data"]))

        # global var "last_screen" always contains information extracted from the last screen shot.
        if len(jbody["data"]) > 0:
            symTab["last_screen"] = jbody["data"]
        else:
            symTab["last_screen"] = []


def processTextInput(step):
    print("Keyboard typing......")
    names = []

    def winEnumHandler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            n = win32gui.GetWindowText(hwnd)
            if n:
                names.append(n)

    win32gui.EnumWindows(winEnumHandler, None)

    window_handle = win32gui.FindWindow(None, names[0])
    window_rect = win32gui.GetWindowRect(window_handle)

    txt_boxes = list(filter(lambda x: x["name"] == "text_input_box" and x["type"] == "info", symTab["last_screen"]))
    print("found input locations:", len(txt_boxes))
    if len(txt_boxes) > 0:
        loc = txt_boxes[0]["loc"]
        print("loc @ ", loc)
    print("global loc@ ", int(loc[0])+window_rect[0], " ,  ", int(loc[1])+window_rect[1])
    pyautogui.moveTo(int(loc[0])+window_rect[0], int(loc[1])+window_rect[1])
    pyautogui.click()          # 0th position is X, 1st position is Y
    print("typing.....", step["action_value"])
    time.sleep(1)
    pyautogui.write(step["action_value"], interval=0.5)
    time.sleep(1)
    pyautogui.press('enter')

# use target_name and target_type to find the matching item among the clickables. once found, click on that accordingly.
def processClick(step):
    print("Mouse Clicking .....")
    loc = symTab[step["target_name"]]["location"]
    pyautogui.moveTo(loc[0], loc[1])          # 0th position is X, 1st position is Y

    if step["action"] == "Single CLick":
        pyautogui.click()
    elif step["action"] == "Double CLick":
        pyautogui.click(clicks=2, interval=0.25)
    elif step["action"] == "Right CLick":
        pyautogui.click(button='right')

def processHotKey(step):
    print("Hotkeying.....")
    keys = step["hotkey"].split('_')
    if len(keys) == 4:
        pyautogui.hotkey(keys[0], keys[1], keys[2], keys[3])
    elif len(keys) == 3:
        pyautogui.hotkey(keys[0], keys[1], keys[2])
    if len(keys) == 2:
        pyautogui.hotkey(keys[0], keys[1])
    if len(keys) == 1:
        pyautogui.hotkey(keys[0])

# the assumption is that
def processRecordLineLocation(step):
    loc_word = step["location"]
    scrn = step["screen"]
    marker_text = step["text"]
    marker_name = step["random_line"]
    found_line = None

    if marker_text == "":
        # this means just grab any line closest to the target location.
        if loc_word == "middle":
            # now go thru scrn data structure to find a line that's nearest to middle of the screen.
            # grab the full screen item in the symTab[scrn] which should always be present.
            #mid = int(abc.get_box()[1] + 0.5*abc.get_box()[3])
            # now filter out all lines above mid point and leave only text lines below the mid point,
            # sort them based on vertical position, and then take the 1st item which is vertically nearest to the mid point.
            print("")

    symTab[marker_name] = found_line

def processScroll(step):
    scroll_amount = int(step["amount"])

    if step["action"] == "Scroll Down":
        scroll_amount = 0 - scroll_amount

    pyautogui.scroll(scroll_amount)

def processCalibrateScroll(step):
    screen_resolution = 30
    marker_name = step["marker"]
    scroll_amount = int(step["amount"])
    resolution = step["data_sink"]
    found_line = None

    delta_v = 0
    scroll_resolution = int(delta_v/scroll_amount)


    symTab[resolution] = scroll_resolution

def processOpenApp(step):
    print("Opening App .....", step["target_link"] + " " + step["argument"])
    subprocess.call(step["target_link"] + " " + step["argument"])


def processCreateData(step):
    print("Creating Data .....")
    if step["key_name"] == "NA":
        # this is the case of direct assignment.
        symTab[step["data_name"]] = step["key_value"]
    else:
        if not re.match("\[.*\]|\{.*\}", step["key_value"]):
            symTab[step["data_name"]] = {step["key_name"]: step["key_value"]}
        else:
            symTab[step["data_name"]] = {step["key_name"]: json.loads(step["key_value"])}

# this is for add an object to a list/array of object, or add another key-value pair to a json object.
def processFillData(step):
    print("Filling Data .....")

    # if not re.match("\[.*\]|\{.*\}", step["from"]):
    from_words = re.split('\[|\(|\{', step["from"])
    source = from_words[0]
    print("source var:", source)

    to_words = re.split('\[|\(|\{', step["to"])
    sink = to_words[0]
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
        statement = "global " + source + ", " + sink + "; " + step["to"] + " = " + step["from"]

    print("Statement: ", statement)
    exec(statement)

def processException(step, skey):
    print("Handle Exception .....")

def processCheckCondition(step, skey):
    print("Check Condition.....")
    condition = step["condition"]

    prefix = (skey.split("!"))[0]
    true_words = step["if_true"].split()
    true_branch = prefix + "!" + "step" + true_words[1]
    false_words = step["if_true"].split()
    false_branch = prefix + "!" + "step" + false_words[1]

    if evalCondition(condition):
        idx = steps.index(true_branch)
    else:
        idx = steps.index(false_branch)
    return idx

def processRepeat(steps, step, skey, settings):
    print("Looping.....")
    repeat_count = int(step["count"])
    loop_condition = step["until"]
    end_step = step["end"]

    prefix = (skey.split("!"))[0]
    end_words = step["end"].split()
    loop_end = prefix + "!" + "step" + end_words[1]
    end_idx = steps.index(loop_end)
    prev_idx = steps.index(skey)

    if loop_condition == "":
        # use loop count
        for c in range(repeat_count):
            end_idx = steps.index(loop_end)
    else:
        # use loop condition.
        while evalCondition(loop_condition):
            runNSteps(steps, prev_idx, prev_idx+1, end_idx, settings)

    return end_idx+1

# assumption: data is in form of a single json which can be easily dumped.
def processLoadData(step):
    print("Loading Data .....")
    with open(step["file_link"], 'r') as f:
        symTab[step["data_name"]] = json.load(f)

def processSaveData(step):
    print("Saving Data .....")
    with open(step["file_link"], 'w') as f:
        json.dump(symTab[step["data_name"]], f)


def processRunScript(step):
    print("Run External Script .....")
    args_strings = json.loads(step["args"])
    # converts string(var name) into variables in symbol table.
    args = list(map(lambda x:symTab[x], args_strings))

    cmdline = ["python", step["file"]]
    cmdline.extend(args)
    oargs = ["capture_output=True", "text=True"]
    cmdline.extend(oargs)
    print("command line: ", cmdline)
    # we can retrieve output in result.stdout and result.stderr
    result = subprocess.call(cmdline)

# this one calculate the distance between Info/Anchor that is nearest to the Location to the location
def processCalcInfoToLoc(step):
    vdistance = 0                         #unit in pixel.


def processExtractPrice(step):
    print("")


def processExtractRating(step):
    print("")


def processExtractTitle(step):
    print("")


def processExtractDiscount(step):
    print("")


# create a data structure holder for andchor....
def processSearch(step):
    print("Searching....", step["target"])

    scrn = symTab[step["screen"]]
    template = step["template"]           #contains anchor/info name, or the text string to matched against.

    if step["target"] == "Anchor":
        print("")
    elif step["target"] == "Info":
        print("")
    elif step["target"] == "Text":
        template = step["template"]
        print("")

    # search result should be put into the result variable.
    symTab[step["result"]] = None

# big assumptions: all involved variables have already been created in globals
# need to do 2 things:
# 1) get rid of all keywords and operators: and or not,  get rid of all [] "" '' pairs, compare operators > < == >= <=
# 2) extract all varaibles and declare them global before the condition string.
#    for example, if the original compare string is "x > 5 and y < 8", it should be "global x, y, cmp_result; cmp_result = x > 5 and y < 8"
def evalCondition(condition):
    global cmp_result
    fault = False
    root = ast.parse(condition)
    print(ast.dump(ast.parse(condition), indent=4))
    print("root:", root)
    varnames = sorted({node.id for node in ast.walk(root) if isinstance(node, ast.Name)})
    print("varnames:", varnames)
    # now filter out special keywords such int, str, float what's left should be variable names.
    varnames = list(filter(lambda k: not (k == "float" or k == "int" or k == "str"), varnames))
    print("filtered varnames:", varnames)
    prefix = "global "
    for varname in varnames:
        if varname in symTab:
            prefix = prefix + varname + ", "
        else:
            fault = True
            print("ERROR: variable " + varname + " does NOT exist.")
            break

    if not fault:
        prefix = prefix + "cmp_result; cmp_result = "
        condition = prefix + condition
        print("TBE: " + condition)
        exec(condition)
        print("TBE result: ", cmp_result)
    return cmp_result