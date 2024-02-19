import json
import random
import re
import ast
import pyautogui
import time
from Cloud import *
import ctypes
import os
import subprocess
import platform
import math
import copy
from printLabel import *
from scraper import *
from adsPowerSkill import *
from amzBuyerSkill import *
from amzSellerSkill import *
from ebaySellerSkill import *
from etsySellerSkill import *
from labelSkill import *


symTab["fout"] = ""
symTab["fin"] = ""
MAXNEST = 18                    # code level skill nest (skill calling skill)
MAXRECUR = 18                   # max level of recurrsion
MAXSTEPS = 2048                 # code level, maximum number of steps of any task. should never be more complicated.

nest_level = 0
steps = []
last_step = -1
next_step = 0
STEP_GAP = 5
first_step = 0

running = False
net_connected = False
in_exception = False

sys_stack = []
exception_stack = []
breakpoints = []
skill_code = None
skill_table = {"nothing": ""}
function_table = {"nothing": ""}
skill_stack = []


# SC - 2023-03-07 files and dirs orgnization structure:
#
#     local image:  C:/Users/***/PycharmProjects/ecbot/runlogs/date/b0m0/win_chrome_amz_home/browse_search/images/scrnsongc_yahoo_1678175548.png"
#     local skill:  C:/Users/***/PycharmProjects/ecbot/resource/skills/public/win_chrome_amz_walk/scripts/skillname.psk
#

# SC - 2023-07-28 to make this instructionset extensible, make vicrop file based? if someone wants to extends the instruction set.
# simply add a file in certain DIR or add thru GUI settings section?
#
# for example, how does a customer supply its own label purchasing function? use patch scheme? create a function overload scheme? (a name to functions mapping tables of some sort)
# do we need code patch scheme?
# How to add an external skill to be called?
#

# VItual-Computer-RObot-Processor
# SC 08/05/2023 - to extend this instruction set, have user create an extended IS json file, we'll reading this json file and attached it to
# the existing one., the question really is about how to run it. the user would have a .py script file that contains the function
# processXXXX itself, the question is how to make our code recognize to call extern on that???
# solution, make instruction naming convention, like starts with "EXT:", then, at our run1step function,
# whenever we see EXT: in front of the name, we use call extern instead.
# Q: how to specify the extended instruction? it should be done locally on PC, per 1 user account. should cloud know anything about it?
# A: from what we know so far, cloud has no need to know the details of the private skill.
# where should the extension IS file be? - skills/my/is_extension.json this should be read in during initialization.
# Note: this extension file as well as the custom skill should be transported to networked vehicle machines, so that they can run it too.
#        then the question Q: is how we do that? A: during initiallization the commander machine archive the skills/my dir and send to all
#        networked machines.
# the development and testing of the IS should be done in-app or separately? if in app, need GUI support, where on GUI?
# A: preferrably in app, but not high priority, initially can get by without having it in-app.
vicrop = {
    "Halt": lambda x,y: processHalt(x, y),
    "Wait": lambda x,y: processWait(x, y),
    "Save Html": lambda x,y,z,k: processSaveHtml(x, y, z, k),
    "Browse": lambda x,y: processBrowse(x, y),
    "Text To Number": lambda x,y: processTextToNumber(x, y),
    "Extract Info": lambda x,y,z,k: processExtractInfo(x, y, z, k),
    "Text Input": lambda x,y: processTextInput(x, y),
    "Mouse Click": lambda x,y: processMouseClick(x, y),
    "Mouse Scroll": lambda x,y: processMouseScroll(x, y),
    "Calibrate Scroll": lambda x,y: processCalibrateScroll(x, y),
    "Text Line Location Record": lambda x,y: processRecordTxtLineLocation(x, y),
    "Key Input": lambda x,y: processKeyInput(x, y),
    "App Open": lambda x,y: processOpenApp(x, y),
    "Create Data": lambda x,y: processCreateData(x, y),
    "Fill Data": lambda x,y: processFillData(x, y),
    "Load Data": lambda x,y: processLoadData(x, y),
    "Save Data": lambda x,y: processSaveData(x, y),
    "Check Condition": lambda x,y,z: processCheckCondition(x, y, z),
    "Repeat": lambda x,y,z: processRepeat(x, y, z),
    "Goto": lambda x,y,z: processGoto(x, y, z),
    "Call Function": lambda x,y,z,v,w: processCallFunction(x, y, z, v, w),
    "Return": lambda x,y,z,w: processReturn(x, y, z, w),
    "Use Skill": lambda x,y,z,u,v,w: processUseSkill(x, y, z, u, v, w),
    "Overload Skill": lambda x,y,z,w: processOverloadSkill(x, y, z, w),
    "Stub": lambda x,y,z,u,v,w: processStub(x, y, z, u, v, w),
    "Call Extern": lambda x,y: processCallExtern(x, y),
    "Exception Handler": lambda x,y,z,w: processExceptionHandler(x, y, z, w),
    "End Exception": lambda x,y,z,w: processEndException(x, y, z, w),
    "Search Anchor Info": lambda x,y: processSearchAnchorInfo(x, y),
    "Search Word Line": lambda x, y: processSearchWordLine(x, y),
    "FillRecipients": lambda x,y: processFillRecipients(x, y),
    "Search Scroll": lambda x,y: processSearchScroll(x, y),
    "Seven Zip": lambda x,y: process7z(x, y),
    "List Dir": lambda x, y: processListDir(x, y),
    "Check Existence": lambda x, y: processCheckExistence(x, y),
    "Create Dir": lambda x, y: processCreateDir(x, y),
    "Print Label": lambda x,y: processPrintLabel(x, y),
    "AMZ Search Products": lambda x,y: processAMZSearchProducts(x, y),
    "AMZ Scrape PL Html": lambda x, y, z: processAMZScrapePLHtml(x, y, z),
    "AMZ Browse Details": lambda x,y: processAMZBrowseDetails(x, y),
    "AMZ Scrape Details Html": lambda x, y: processAMZScrapeDetailsHtml(x, y),
    "AMZ Browse Reviews": lambda x,y: processAMZBrowseReviews(x, y),
    "AMZ Scrape Reviews Html": lambda x, y: processAMZScrapeReviewsHtml(x, y),
    "AMZ Scrape Orders Html": lambda x, y: processAMZScrapeOrdersHtml(x, y),
    "EBAY Scrape Orders Html": lambda x, y: processEbayScrapeOrdersHtml(x, y),
    "ETSY Scrape Orders": lambda x, y: processEtsyScrapeOrders(x, y),
    "Etsy Get Order Clicked Status": lambda x, y: processEtsyGetOrderClickedStatus(x, y),
    "Etsy Set Order Clicked Status": lambda x, y: processEtsySetOrderClickedStatus(x, y),
    "Etsy Find Screen Order": lambda x, y: processEtsyFindScreenOrder(x, y),
    "Etsy Remove Expanded": lambda x, y: processEtsyRemoveAlreadyExpanded(x, y),
    "Etsy Extract Tracking": lambda x, y: processEtsyExtractTracking(x, y),
    "Etsy Add Page Of Order": lambda x, y: processEtsyAddPageOfOrder(x, y),
    "GS Scrape Labels": lambda x, y: processGSScrapeLabels(x, y),
    "GS Extract Zipped": lambda x, y: processGSExtractZippedFileName(x, y),
    "Prep GS Order": lambda x, y: processPrepGSOrder(x, y),
    "AMZ Match Products": lambda x,y: processAMZMatchProduct(x, y)
}


# read an psk fill into steps (json data structure)
# input: steps - data structure to hold the results.
#        name_prefix - name to add to front of step # to make step name unique.
#                       typically this is the cascade of userID, skill name.
#       skill_file - full path file name of the .psk file.
# output: None (sort of in step already)
# step name should be in the form of "B"+BotID+"M" + MissionID + "!" + skillname + "!" + level # + step number
# Note:
def readPSkillFile(name_space, skill_file, lvl = 0):
    global steps
    step_keys = []
    global skill_code
    this_skill_code = None
    try:
        with open(skill_file, "r") as json_as_string:
            # inj = json.load(json_as_string)
            # Call this as a recursive function if your json is highly nested

            # get rid of comments.
            lines = [re.sub("#.*", "", one_object.rstrip()) for one_object in json_as_string.readlines()]
            json_as_string.close()

            # get rid of empty lines.
            #new_list = list(filter(lambda x: x != '', list_with_empty_strings))
            useful_lines = list(filter(lambda x: x.rstrip(), lines))
            slines = ""
            key = ""
            # reg = re.compile("step +[0-9]")
            # reg = re.compile(r'"([^"]*)"')
            # #if reg.match('aaa"step 123":'):
            # if len(re.findall(r'"([^"]*)"', 'aaa"step 123":')) > 0:
            #     print("FOUND MATCH")
            # else:
            #     print("NO MATCH")
            print("NUM USEFUL:", str(len(useful_lines)))
            for l in useful_lines:
                #need to create prefix and add the step name.
                # l = adressAddNameSpace(l, name_space, lvl)            # will do this later.

                #print("USEFUL: ", l)
                slines = slines + l + "\n"

            # print("SLINES:", slines)
            this_skill_code = json.loads(slines)

            # call the sub skills
            step_keys = list(this_skill_code.keys())
            for key in step_keys:
                if key == "header" or key == "dummy":
                    del this_skill_code[key]
            # print("=============================================================")
            # print("SKILL CODE:", len(this_skill_code.keys()), this_skill_code)
    except OSError as err:
        print("ERROR: Read PSK Error!", err)

    return this_skill_code


def addNameSpaceToAddress(stepsJson, name_space, lvl):
    # add name space to json step names.
    steps_keys = list(stepsJson.keys())
    print("name space:", name_space)
    print("STEP KEYS::::", steps_keys)
    for old_key in steps_keys:
        new_key = adressAddNameSpace(old_key, name_space, lvl)
        print("New Key:", new_key)
        stepsJson[new_key] = stepsJson[old_key]
        stepsJson.pop(old_key)


def adressAddNameSpace(l, name_space, lvl):
    if len(re.findall(r'step [0-9]+', l)) > 0:

        # need to handle "Use Skill" calling to sub-skill files.
        # print("STEP line:", l)
        step_word = re.findall(r'([^"]*)', l)[0]
        # print("STEP word:", step_word)
        sn = step_word.split(' ')[1]
        global_sn = name_space + str(lvl) + "!" + sn
        print("GLOBAL NS:", global_sn)
        # re.sub(r'"([^"]*)"', global_sn, l)
        l = re.sub(r'[0-9]+', global_sn, l)

    return l

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

def runAllSteps(steps, mission, skill, mode="normal"):
    global last_step
    global next_step
    run_result = "Completed:0"
    last_step = -1
    next_step = 0
    next_step_index = 0
    running = True
    run_stack = []
    print("running all steps.....", mission)
    stepKeys = list(steps.keys())
    # for k in stepKeys:
    #     print("steps: ", k, " -> ", steps[k])
    print("=====================================")
    while next_step_index <= len(stepKeys)-1 and running:
        next_step_index, step_stat = run1step(steps, next_step_index, mission, skill, run_stack)

        if step_stat == "success:0":

            # debugging mode. if the next instruction is one of the breakpoints, then stop and pendin for
            # keyboard input. (should fix later to support GUI button press.....)
            if next_step_index in breakpoints:
                cmd = input("cmd for next action('<Space>' to step, 'c' to continue to run, 'q' to abort. \n")
                if cmd == "c":
                    mode = "normal"
                elif cmd == "q":
                    break

            # in case an exeption occurred, handle the exception.
            if in_exception:
                print("EXCEPTION THROWN:")
                # push next_step_index onto exception stack.
                exception_stack.append(next_step_index)

                # set the next_step_index to be the start of the exception handler, which always starts @8000000
                next_step_index = stepKeys.index("step8000000")

            if mode == "debug":
                input("hit any key to continue")

            print("next_step_index: ", next_step_index, "len(stepKeys)-1: ", len(stepKeys)-1)
        else:
            break

    if step_stat == "success:0":
        print("RUN COMPLETED!")
    else:
        print("RUN ABORTED!")
        run_result = step_stat

    return run_result

def runNSteps(steps, prev_step, i_step, e_step, mission, skill, run_stack):
    global last_step
    global next_step
    last_step = prev_step
    next_step = i_step
    running = True
    print("running N steps.....")
    while next_step <= e_step and running:
        print("len steps:", len(steps), "next step:", next_step)
        run1step(steps, mission, skill, run_stack)


def run1step(steps, si, mission, skill, stack):
    global next_step
    global last_step
    # settings = mission.parent_settings
    i = next_step
    stepKeys = list(steps.keys())
    step = steps[stepKeys[si]]
    last_si = si
    print("============>running step [", si, "]: ",  step)

    if "type" in step:
        if step["type"] == "Halt":
            # run step using the funcion look up table.
            si,isat = vicrop[step["type"]](step, si)
        elif step["type"] == "Goto" or step["type"] == "Check Condition" or step["type"] == "Repeat":
            # run step using the funcion look up table.
            si,isat = vicrop[step["type"]](step, si, stepKeys)
        elif step["type"] == "Extract Info" or step["type"] == "Save Html":
            si,isat = vicrop[step["type"]](step, si, mission, skill)
        elif step["type"] == "AMZ Scrape PL Html":
            si,isat = vicrop[step["type"]](step, si, mission)
        elif step["type"] == "End Exception" or step["type"] == "Exception Handler" or step["type"] == "Return":
            si,isat = vicrop[step["type"]](step, si, stack, stepKeys)
        elif step["type"] == "Stub" or step["type"] == "Use Skill":
            si,isat = vicrop[step["type"]](step, si, stack, skill_stack, skill_table, stepKeys)
        elif step["type"] == "Call Function":
            si,isat = vicrop[step["type"]](step, si, stack, function_table, stepKeys)
        elif "EXT:" in step["type"]:
            if step["type"].index("EXT:") == 0:
                # this is an extension instruction, execute differently, simply call extern. as to what to actually call, it's all
                # embedded in the step dictionary.
                si,isat = processCallExtern(step, si)
        else:
            si,isat = vicrop[step["type"]](step, si)

    else:
        si = si + 1
        isat = "ErrorInstructionNotType:400"

    return si, isat


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
        i = run1step(steps, settings)



def processBrowse(step, i):
    ex_stat = "success:0"
    try:
        print("browsing the page....")
    except:
        ex_stat = "ErrorBrowse:" + str(i)

    return (i + 1), ex_stat

def is_uniq(word, allwords):
    matched = [x for x in allwords if word in x["text"]]
    print("# matched: ", len(matched))
    if len(matched) == 1:
        return True
    else:
        return False

# this function finds a unique line of text nearest to the specified target location on the screen.
def find_phrase_at_target(screen_data, target_loc):
    print("finding text around target loc: ", target_loc)
    found_phrase = ""
    found_box = [0, 0, 0, 0]
    # first, filter out all shapes and non text contents.
    paragrphs = [x for x in screen_data if x['name'] == 'paragraph']

    allwords = []

    for p in paragrphs:
        for l in p["txt_struct"]:
            for w in l["words"]:
                allwords.append(w)

    sorted_words = sorted(allwords, key=lambda w: p2p_distance(box_center(w["box"]), target_loc), reverse=False)

    print("found paragraphs: ", len(paragrphs))

    # then sort by paragraph center's distance to target location.
    # box: (left, top, right, bottom)
    # paragrphs = sorted(paragrphs, key=lambda x: p2p_distance(loc_center(x["loc"]), target_loc), reverse=False)
    time.sleep(1)
    print("w0: ", sorted_words[0], "dist: ", p2p_distance(box_center(sorted_words[0]["box"]), target_loc))
    print("w1: ", sorted_words[1], "dist: ", p2p_distance(box_center(sorted_words[1]["box"]), target_loc))
    print("w2: ", sorted_words[2], "dist: ", p2p_distance(box_center(sorted_words[2]["box"]), target_loc))
    # then find an unique line in that paragraph, if none found, go the next paragraph until find one.
    for w in sorted_words:
        # now filter out lines contains non alphabetical chars. and non-unique phrases.
        # afterstrip = [x['text'].lstrip() for x in lines]
        actual_w = w["text"].strip()
        if len(actual_w) >= 6:
            if is_uniq(actual_w, sorted_words):
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                found_phrase = actual_w
                found_box = w['box']
                print("found the implicit marker: ", found_phrase, " loc: ", found_box)
                break

    return(found_phrase, found_box)

def find_marker_on_screen(screen_data, target_word):
    # first, filter out all shapes and non text contents.
    print("finding.......", target_word)
    paragraphs = [x for x in screen_data if x['name'] == 'paragraph']
    found_box = []
    found_loc = None
    for p in paragraphs:
        for l in p["txt_struct"]:
            for w in l["words"]:
                if w["text"].strip() == target_word:
                    found_box = w["box"]
                    break
            if found_box:
                break
        if found_box:
            break
    # no need to worry about multiple findings, there should be either 1 or 0 occurance.

    return(found_box)


# record the location of a specific text on screen, the result will be used to calibrate scroll amount.
# loc: location on screen, could take value "", "middle" "bottome" "top" - meaning take some unique text that's nearest the location of the screen.
#       the resulting text is defauly putinto the variable "ResolutionCalibrationMarker"
# txt: text to record the location. - caller can also directly specify the text to be extracted, in such a case, loc = ""
# screen: variable that contains the screen content data structure.
# to: put result in this varable name.
def processRecordTxtLineLocation(step, i):
    ex_stat = "success:0"
    try:
        loc_word = step["location"]
        scrn = step["screen"]
        marker_text = step["text"]
        marker_loc = step["to"]
        found_line = None
        found_text = None
        screen_data = symTab[scrn]
        symTab["last_screen_cal01"] = screen_data
        screen_size = (screen_data[len(screen_data) - 2]['loc'][3], screen_data[len(screen_data) - 2]['loc'][2])
        print("screen_size: ", screen_size)

        if marker_text == "":
            # this means just grab any line closest to the target location.
            if loc_word == "middle":
                # now go thru scrn data structure to find a line that's nearest to middle of the screen.
                # grab the full screen item in the symTab[scrn] which should always be present.
                target_loc = (int(screen_size[0]*2/3), int(screen_size[1]*2/3))
                found_phrase, found_box = find_phrase_at_target(screen_data, target_loc)

                print("FOUND implicit marker: [", found_phrase, "] at location: ", found_box)

                #mid = int(abc.get_box()[1] + 0.5*abc.get_box()[3])
                # now filter out all lines above mid point and leave only text lines below the mid point,
                # sort them based on vertical position, and then take the 1st item which is vertically nearest to the mid point.
                symTab["InternalMarker"] = found_phrase

        else:
            print("FINDINg text: ", marker_text, " ............ ")
            if loc_word.isnumeric():
                # percentage deal
                target_loc = (int(screen_size[0] / 2), int(screen_size[1] * (int(loc_word)/100)))
            else:
                if loc_word == "top":
                    target_loc = (int(screen_size[0]/2), 0)
                    # find the template text that's nearest to refvloc
                elif loc_word == "middle":
                    target_loc = (int(screen_size[0] / 2), int(screen_size[1] / 2))
                elif loc_word == "bottom":
                    target_loc = (int(screen_size[0] / 2), int(screen_size[1]))
                else:
                    target_loc = (int(screen_size[0] / 2), 0)

            print("target_loc: ", target_loc)

            found_box = find_marker_on_screen(screen_data, marker_text)
            print("found_loc: ", found_box)

        # symTab[marker_loc] = box_center(found_paragraph["loc"])
        symTab[marker_loc] = box_center(found_box)
        print("found text at loc: ", found_box, "stored in var: ", marker_loc, " with box center: ", symTab[marker_loc])

    except:
        ex_stat = "ErrorRecordTxtLineLocation:" + str(i)

    return (i + 1), ex_stat



def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

# find a paragraph on screen that matches the target paragraph.
def find_paragraph_match(target, screen_data):
    paragrphs = [x for x in screen_data if x['name'] == 'paragraph']
    print("find_paragraph_match:", paragrphs)
    print("Target:", target)
    # then sort by paragraph center's distance to target location.
    # box: (left, top, right, bottom)
    similarity = [similar(target['text'],  x['text']) for x in paragrphs]
    print(similarity.index(max(similarity)), ",", similarity[similarity.index(max(similarity))], ", ", paragrphs[similarity.index(max(similarity))]['text'])
    print("similarity: ", similarity)
    matched = [x for x in paragrphs if similar(target['text'],  x['text']) > 0.95]
    print("matched:", matched)

    if len(matched) > 0:
        return matched[0]
    else:
        return None

# sink, amount, screen, marker, stepN
# "data_sink": sink
# "amount": amount
# "screen": screen
# "marker": marker
def processCalibrateScroll(step, i):
    ex_stat = "success:0"
    try:
        screen_resolution = 30
        marker_text = step["marker"]
        scroll_amount = int(step["amount"])
        resolution = step["data_sink"]
        prev_loc = symTab[step["last_record"]]
        screen = step["screen"]
        found_line = None

        screen_data = symTab[screen]
        screen_size = (screen_data[len(screen_data) - 2]['loc'][3], screen_data[len(screen_data) - 2]['loc'][2])

        target_loc = (int(screen_size[0] / 2), 0)
        print("FINDing near target loc: ", target_loc)
        # find the template text that's nearest to refvloc
        if marker_text == "":
            marker_text = symTab["InternalMarker"]
            print("finding implicit marker: [", symTab["InternalMarker"], "]")
        found_box = find_marker_on_screen(screen_data, marker_text)
        print("calibration scroll found location:: ", found_box, " vs. previous location::", prev_loc, " in var: ", step["last_record"])
        # matched_paragraph = find_paragraph_match(marker_paragraph, screen)

        if found_box:
            delta_v = abs(box_center(found_box)[1] - prev_loc[1])
            print("abs delta v: ", delta_v, " for scrool_amount: ", scroll_amount)
            scroll_resolution = delta_v/scroll_amount
        else:
            scroll_resolution = 0
            print("ERROR: scroll calibration FAILED!!!!")

        symTab[resolution] = scroll_resolution
        symTab[screen] = symTab["last_screen_cal01"]
        print("scroll resolution is found as: ", scroll_resolution, " stored in var: ", resolution)

    except:
        ex_stat = "ErrorCalibrateScroll:" + str(i)

    return (i + 1), ex_stat




def getPrevStepName(sName):
    prev = int(sName[4, len(sName)]) - STEP_GAP
    return "step"+str(prev)

def getNextStepName(sName):
    next = int(sName[4, len(sName)]) + STEP_GAP
    return "step"+str(next)

def gen_addresses(stepcodes, nth_pass):
    global skill_table
    global function_table
    temp_stack = []
    print("nth pass: ", nth_pass)
    # go thruthe program as we see condition / loop / function def , push them onto stack, then pop them off as we see
    # else, end - if, end - loop, end - function....until at last the stack is empty again.
    # sk
    #skcode = json.loads(sk)
    stepkeys = list(stepcodes.keys())
    print("total " + str(len(stepkeys)) + " steps.")

    if nth_pass == 1:
        # parse thru the json objects and work on stubs.
        for i in range(len(stepkeys)):
            stepName = stepkeys[i]
            # print("working on: ", stepName)

            if i != 0:
                prevStepName = stepkeys[i - 1]
            else:
                prevStepName = stepName

            if i != len(stepkeys) - 1:
                nextStepName = stepkeys[i + 1]
            else:
                nextStepName = stepName

            if stepcodes[stepName]["type"] == "Stub":
                # code block
                # build up function table, and skill table.
                if "start skill" in stepcodes[stepName]["stub_name"]:
                    # this effectively includes the skill overload function. - SC
                    print("ADDING TO SKILL TABLE: ", stepcodes[stepName]["func_name"], nextStepName)
                    skill_table[stepcodes[stepName]["func_name"]] = nextStepName
                elif stepcodes[stepName]["stub_name"] == "start function":
                    # this effectively includes the skill overload function. - SC
                    print(stepcodes[stepName]["func_name"])
                    function_table[stepcodes[stepName]["func_name"]] = nextStepName

    elif nth_pass == 2:
        # parse thru the json objects and work on stubs.
        for i in range(len(stepkeys)):
            stepName = stepkeys[i]


            if i != 0:
                prevStepName = stepkeys[i-1]
            else:
                prevStepName = stepName

            if i != len(stepkeys)-1:
                nextStepName = stepkeys[i+1]
            else:
                nextStepName = stepName


            if stepcodes[stepName]["type"] == "Stub":
                #code block

                if stepcodes[stepName]["stub_name"] == "else":
                    # pop from stack, modify else, then push back, assume condition step will be pushed onto stack. as it executes.
                    tempStepName = temp_stack.pop()
                    print("poped out due to else step[", len(temp_stack), "]: ", tempStepName, "(", stepcodes[tempStepName], ")")

                    stepcodes[tempStepName]["if_else"] = nextStepName
                    # now replace with current stub with a goto statement and push this onto stack.

                    print("replacing else with an empty Goto which will be filled up later...")
                    stepcodes[stepName] = {"type": "Goto", "goto": ""}

                    temp_stack.append(stepName)
                    print("pushed step[", len(temp_stack), "]: ", stepName, "(", stepcodes[stepName], ")")

                elif stepcodes[stepName]["stub_name"] == "end condition":
                    # pop from stack
                    print("before popped out due to end condition step[", len(temp_stack), "]: ", tempStepName, "(", stepcodes[tempStepName], ")")

                    tempStepName = temp_stack.pop()
                    print("popped out due to end condition step[", len(temp_stack), "]: ", tempStepName, "(", stepcodes[tempStepName], ")")

                    if (stepcodes[tempStepName]["type"] == "Goto"):
                        # in case that this is a check condition with an else stub....
                        print("popped goto.....")
                        stepcodes[tempStepName]["goto"] = nextStepName
                    elif ( stepcodes[tempStepName]["type"] == "Check Condition"):
                        # in case that this is a check condition without else stub....
                        stepcodes[tempStepName]["if_else"] = nextStepName
                        print("replace if_else to:", nextStepName)
                        # so stub "else" will be replaced by a "Goto" step instead.
                        # stepcodes[stepName] = {"type": "Goto", "goto": nextStepName}
                elif stepcodes[stepName]["stub_name"] == "break":
                    # push on to stack
                    temp_stack.append(stepName)
                    print("pushed step[", len(temp_stack), "]: ", stepName, "(", stepcodes[stepName], ")")
                elif stepcodes[stepName]["stub_name"] == "end loop":
                    # pop from stack
                    loop_start_found = False
                    fi = 0
                    print("working on: ", prevStepName, "(", stepcodes[prevStepName], ")")
                    while not loop_start_found:
                        tempStepName = temp_stack.pop()
                        print("popped out due to end looop step[", len(temp_stack), "]: ", fi, " :: ", tempStepName, "(", stepcodes[tempStepName], ")")
                        fi = fi + 1
                        if stepcodes[tempStepName]["type"] == "Repeat":
                            stepcodes[tempStepName]["end"] = nextStepName
                            loop_start_found = True
                            # now replace with current stub with a goto statement and push this onto stack.
                            stepcodes[stepName] = { "type": "Goto", "goto": tempStepName }
                        elif stepcodes[tempStepName]["type"] == "Stub":
                            if stepcodes[tempStepName]["stub_name"] == "break":
                                stepcodes[tempStepName] = {"type": "Goto", "goto": nextStepName}

                elif stepcodes[stepName]["stub_name"] == "def function":
                    # add function name and address pair to stepcodes - kind of a symbal table here.
                    stepcodes[symTab[stepName]["name"]] = nextStepName
                elif stepcodes[stepName]["stub_name"] == "end skill":
                    # add function name and address pair to stepcodes - kind of a symbal table here.
                    print("END OF SKILL - do nothing...", stepcodes[stepName]["func_name"])
                elif stepcodes[stepName]["stub_name"] == "tag":
                    # this is for Goto statement, so that goto doesn't have to goto an explicict address,
                    # but can goto a String name instead. if any step is the goto target, just add
                    # a stub step with "tag" and "whatever you like to name the tag name"
                    # simply add tag and previous step address to the hash address space
                    symTab[stepcodes[stepName]["func_name"]] = prevStepName
            elif stepcodes[stepName]["type"] == "Check Condition":
                # push ont stack
                temp_stack.append(stepName)
                print("pushed step[", len(temp_stack), "]: ", stepName, "(", stepcodes[stepName], ")")

            elif stepcodes[stepName]["type"] == "Repeat":
                # push on to stack
                temp_stack.append(stepName)
                print("pushed step[", len(temp_stack), "]: ", stepName, "(", stepcodes[stepName], ")")

    elif nth_pass == 3:
        #on 3nd pass replace all function call address. -- SC 2023/03/27 I don't think we need this pass anymore....at least for now..
        for i in range(len(stepkeys)):
            stepName = stepkeys[i]
            if i != 0:
                prevStepName = stepkeys[i-1]
            else:
                prevStepName = stepName

            if i != len(stepkeys)-1:
                nextStepName = stepkeys[i+1]
            else:
                nextStepName = stepName

            if stepcodes[stepName]["type"] == "Call Function":
                stepcodes[stepName]["addr"] = stepcodes[stepcodes[stepName]["name"]]
            elif stepcodes[stepName]["type"] == "Use Skill":
                stepcodes[stepName]["addr"] = stepcodes[stepcodes[stepName]["name"]]


def prepRun1Skill(name_space, skill_file, lvl = 0):
    global skill_code
    global function_table
    run_steps = readPSkillFile(name_space, skill_file, lvl)
    print("DONE reading skill file...")

    # generate real address for stubs and functions. (essentially update the addresses or the closing brackets...)
    gen_addresses(run_steps, 1)
    # 2nd pass: resolve overload.
    gen_addresses(run_steps, 2)
    print("DONE generating addressess...")
    print("READY2RUN1: ", run_steps)
    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print("function table:", function_table)
    return run_steps


# load all runnable skill files into memeory space, and start to assemble them into runnable instructions.
def prepRunSkill(all_skill_codes):
    global skill_code

    for sk in all_skill_codes:
        print("READING SKILL CODE:", sk["ns"], sk["skfile"])

        f = open(sk["skfile"])
        run_steps = json.load(f)
        f.close()

        if skill_code:
            skill_code.update(run_steps)         # merge run steps.
            # skill_code = skill_code + run_steps
        else:
            skill_code = run_steps

    # 1st pass: get obvious addresses defined. if else end-if, loop end-loop,
    gen_addresses(skill_code, 1)

    #2nd pass: resolve overload.
    gen_addresses(skill_code, 2)

    print("DONE generating addressess...")
    # print("READY2RUN: ", skill_code)
    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    return skill_code

def genNextStepNumber(currentN, steps=1):
    nextStepN = currentN + STEP_GAP * steps
    return nextStepN



# for the detail config:
# #   { level: 1~5, seeAll : true/false, allPos: true/false, allNeg: true/false, nExpand: ,nPosPages: , nNegPages: }
# seeAll: whether to click on seeAll
# allPos: whether to click on all positive review link.
# allNeg: whether to click on all negative review link
# nPosExpand: max number of times to expand to see a very long positive reviews
# nNegExpand: max number of times to expand to see a very long negative reviews
# nPosPages: number of positive review pages to browse thru.
# nPosPages: number of negative review pages to browse thru.
# pseudo code:
#    if seeAll:
#       click on seeAll which will take us to the all review page.
#       if allPos:
#           click on all positive reviews, this will take us to the all positive review page.
#           for i in range(nPosPages):
#               while not reached bottom:
#                   view all review, (tricky, could have long reviews which span multiple screen without images)
#                   scroll down
#                   check whether reached bottom
#           whether we have reached the last page
#               if so:
#                   go back. there are two strategy here, A: browse previous page. B: scroll to top and click on the product again.
#               else:
#                   click on "Next page"
#
#    else:
#        while not reached bottom:
#            extract screen info.
#            if there is expand mark,
#                if  nPosExand > 0:
#                   click on "read more",
#                   view expanded review, (tricky, could span multiple screen without images)
#                   scroll till the end of this review.
#                   nPosExand = nPosExand - 1
#            are we at the bottom of the page.
#
#  SC - 20230506 - this routine is kind of useless for now..............

def genStepAMZBrowseReviews(screen, detail_cfg, stepN, worksettings, page, sect, theme):
    psk_words = ""
    # grab location of the title of the "matchedProducts" and put it into variable "product_title"
    #(action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "See All Reviews", "anchor text", "See All Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    if detail_cfg.seeAll:
        #(action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
        this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "See All Reviews", "anchor text", "See All Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepWait(3, 0, 0, this_step)
        psk_words = psk_words + step_words

        if detail_cfg.allPos:
            # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
            this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "All positive Reviews", "anchor text", "All positive Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
            psk_words = psk_words + step_words

            this_step, step_words = genStepWait(3, 0, 0, this_step)
            psk_words = psk_words + step_words

            # screen, np, nn, stepN, root, page, sect):
            this_step, step_words = genBrowseAllReviewsPage("screen_info", 1, 1, this_step, worksettings, "all reviews", "top")

        if detail_cfg.allNeg:
            # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
            this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "All negative Reviews", "anchor text", "All negative Reviews", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
            psk_words = psk_words + step_words

            this_step, step_words = genStepWait(3, 0, 0, this_step)
            psk_words = psk_words + step_words

            this_step, step_words = genBrowseAllReviewsPage("screen_info", 1, 1, this_step, worksettings, "all reviews", "top")

    else:
        # now simply scroll down
        this_step, step_words = genStepCreateData("bool", "endOfReviews", "NA", "False", this_step)
        psk_words = psk_words + step_words

        this_step, step_words = genStepLoop("endOfReviews != True", "", "", "browseReviews"+str(stepN), this_step)
        psk_words = psk_words + step_words

        # (action, screen, amount, unit, stepN):
        this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "50", "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
        psk_words = psk_words + step_words

        # check whether there is any match of this page's product, if matched, click into it.
        this_step, step_words = genStepSearchAnchorInfo("screen_info", detail_cfg.products, "direct", "text", "any", "matchedProducts", "expandable", False, this_step)
        psk_words = psk_words + step_words

        if detail_cfg.nExpand > 0:
            # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
            this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "read more", "anchor text", "read more", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
            psk_words = psk_words + step_words

            #now scroll until the end of this review.

            detail_cfg.nExpand = detail_cfg.nExpand-1

        this_step, step_words = genStepStub("end loop", "", "", this_step)
        psk_words = psk_words + step_words

    # click into the product title.
    # (action, action_args, screen, target, target_type, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "1 star", "anchor text", "1 star", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    ## browse all the way down, until seeing "No customer reviews" or "See all reviews"
    this_step, step_words = genStepLoop("reviews_eop != True", "", "", "browseListOfDetails"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # (action, screen, amount, unit, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", "50", "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepAMZSearchReviews("screen_info", "prod_details", "atbottom", this_step)
    psk_words = psk_words + step_words

    # here, if need to click open half hidden long reviews.....
    this_step, step_words = genStepSearchAnchorInfo("screen_info","See all details", "direct", "screen_info", "any", "eop_review", "reviews_eop", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words




