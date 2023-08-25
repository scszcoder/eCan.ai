import os
import subprocess
import platform
import errno
from basicSkill import *

global symTab
global STEP_GAP

def is_tool(name):
    try:
        devnull = open(os.devnull)
        subprocess.Popen([name], stdout=devnull, stderr=devnull).communicate()
    except OSError as e:
        if e.errno == errno.ENOENT:
            return False
    return True

def find_prog(prog):
    if is_tool(prog):
        cmd = "where" if platform.system() == "Windows" else "which"
        return subprocess.call([cmd, prog])


zipped_full_path = ""
unziped_path = ""
# this skill assumes the following input "fin": [file full path, result_path]
# the caller skill must get these ready. There will be no error handling here.
def genWinRARLocalUnzipSkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_file_all_op", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                                          "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_rar_local_unzip/unzip_archive", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global zipped_full_path\nzipped_full_path = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global unziped_path\nunziped_path = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # subprocess.Popen(r'explorer /root,"'+zipped_full_path+'"')
    rar_file = '/root,"'+zipped_full_path+'"'
    this_step, step_words = genStepOpenApp("cmd", True, "shell", "explorer", "", "", rar_file, 2, this_step)
    psk_words = psk_words + step_words


    # pop up window size, could be 2 possible pop ups，
    # 1) is “Please purchase WinRAR license”， should click on ”close“ button
    # 2) is “Your free trial period has ended!”， should click on ”X“ button

    # verify the popup,

    # extract screen info,
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "winrar", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["free_trial_ended"], ["anchor text"], "any", "useless", "rar_trial_end_popped", "amz", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["please_purchase_license"], ["anchor text"], "any", "useless", "rar_license_popped", "amz", this_step)
    psk_words = psk_words + step_words

    # and click on upper right corner to close the pop up or click on Close button to close the pop-up window depends on which popup it is.
    this_step, step_words = genStepCheckCondition("rar_trial_end_popped", "", "", this_step)
    psk_words = psk_words + step_words

    # use hot key to close the window
    this_step, step_words = genStepKeyInput("", True, "alt,f4", "", 0, this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "close", "anchor text", "Extract To", [0, 0], "center", [0, 0], "pixel", 0, 0, this_step)
    psk_words = psk_words + step_words
    # # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # click on "Extract to"
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "winrar", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Extract_To", "anchor text", "Extract To", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    # read the file dialog popup
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "winrar", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 0, this_step)
    psk_words = psk_words + step_words


    # do offset to new_folder button.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "new_folder", "anchor text", "New folder", [0, 0], "left", [2, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # fill in the to be extracted dir
    this_step, step_words = genStepTextInput("type", False, unziped_path, 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "OK", "anchor text", "OK", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    # list the files to double check???

    # use hot key to close the winrar app window
    this_step, step_words = genStepKeyInput("", True, "alt,f4", "", 0, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_rar_local_unzip/unzip_archive", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genWinRarSkill(fpath, dest_dir, dest_name, theme, page, sect, ):
    print("hello")