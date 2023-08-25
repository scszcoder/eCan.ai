from basicSkill import *
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from PyPDF2 import PdfReader
import rarfile
from rarfile import RarFile
from rarfile import is_rarfile
import subprocess
import os
from datetime import datetime
import time
from basicSkill import *

global symTab
global STEP_GAP

fopen_f_path = ""
fopen_f_name = ""

# this skill assumes the following input "fin": [file path, file name, file operation name ("open"/"save")]
# the caller skill must get these ready. There will be no error handling here.
def genWinFileLocalOpenSaveSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_file_local_open_save_as", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                                          "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_file_local_op/open_save_as", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global f_op\nf_op = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fopen_f_path\nfopen_f_path = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fopen_f_name\nfopen_f_name = fin[2]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    print("fopen_f_path: ", fopen_f_path, "fopen_f_name: ", fopen_f_name)

    # readn screen
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "file_dialog", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # click on path input win
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "refresh", "anchor icon", "", [0, 0], "left", [3, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # delete everything there
    # do some overall review scroll, should be mostly positive.
    lcvarname = "fopen" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("", "50", "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # type in the path
    #action, saverb, txt, speed, key_after, wait_after, stepN
    this_step, step_words = genStepTextInput("type", False, fopen_f_path, 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # click on file name input win
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "open", "anchor text", "", [0, 0], "right", [1, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # delete everything there
    # do some overall review scroll, should be mostly positive.
    lcvarname = "fopen" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("", "30", "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # type in the path
    this_step, step_words = genStepTextInput("type", False, fopen_f_name, 1, "", 2, this_step)
    psk_words = psk_words + step_words


    # click on OPEN button to complete the drill
    this_step, step_words = genStepCheckCondition("fin[2] == 'open'", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "open", "anchor text", "", [0, 0], "center", [0, 0], "box", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "save", "anchor text", "", [0, 0], "center", [0, 0], "box", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_file_local_op/open_save_as", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words

