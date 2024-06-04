from basicSkill import *
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from PyPDF2 import PdfReader
import subprocess
import os
from basicSkill import *
from Logger import *

global symTab
global STEP_GAP

fopen_f_path = ""
fopen_f_name = ""

# this skill assumes the following input "fin": [file path, file name, file operation name ("open"/"save")]
# the caller skill must get these ready. There will be no error handling here.
def genWinFileLocalOpenSaveSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_file_local_open_save_as", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                                          "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_file_local_op/open_save_as", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global f_op\nf_op = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fopen_f_path\nfopen_f_path = fin[1]\nprint('fopen_f_path:', fopen_f_path)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fopen_f_name\nfopen_f_name = fin[2]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    log3("fopen_f_path: "+fopen_f_path+"fopen_f_name: "+fopen_f_name)

    # this_step, step_words = genStepCallExtern("global file_wo_extension\nfile_wo_extension = file_wo_extension + todate + tail", "", "in_line", "", this_step)
    this_step, step_words = genStepCallExtern("global scrn_options\nscrn_options = {'attention_area':[0, 0, 1, 1],'attention_targets':['Open', 'File name']}\nprint('scrn_options', scrn_options)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # readn screen
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "op", "top", theme, this_step, None, "scrn_options")
    psk_words = psk_words + step_words

    # click on path input win
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "search", "anchor text", "", [0, -1], "left", [2.5, 0], "box", 1, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # delete everything there
    # do some overall review scroll, should be mostly positive.
    lcvarname = "fopen" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("", "20", "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # type in the path
    #action, saverb, txt, speed, key_after, wait_after, stepN
    this_step, step_words = genStepTextInput("var", False, "fopen_f_path", "direct", 0.05, "enter", 1, this_step)
    psk_words = psk_words + step_words

    # click on file name input win
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "file_name", "anchor text", "", [0, 0], "right", [2, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # delete everything there
    # do some overall review scroll, should be mostly positive.
    lcvarname = "fopen" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("", "10", "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 0, this_step)

    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # type in the path
    this_step, step_words = genStepTextInput("var", False, "fopen_f_name", "direct", 0.01, "", 1, this_step)
    psk_words = psk_words + step_words


    # click on OPEN button to complete the drill
    this_step, step_words = genStepCheckCondition("fin[0] == 'open'", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill (don't use open, use offset from canel button for better certainty
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "file_cancel", "anchor text", "", [0, 0], "left", [2, 0], "box", 0, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "file_cancel", "anchor text", "", [0, 0], "left", [0, 0], "box", 0, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_file_local_op/open_save_as", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words

