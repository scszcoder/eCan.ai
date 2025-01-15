import os
import subprocess
import platform
import errno

from bot.basicSkill import genStepHeader, genStepCreateData, genStepStub, genStepCallExtern, genStepCheckCondition, \
    genStepOpenApp, genStepWait, genStepExtractInfo, genStepSearchAnchorInfo, genStepKeyInput, genStepMouseClick, \
    genStepTextInput
from bot.Logger import log3

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
# input [ zipped files,  output path ]
def genWinRARLocalUnzipSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_file_all_op", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001",
                                          "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_rar_local_unzip/unzip_archive", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global rarexe\nrarexe = fin[0]\nprint('rarexe', rarexe)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global zipped_full_path\nzipped_full_path = fin[2]\nprint('zipped_full_path', zipped_full_path)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global unzipped_path\nunzipped_path = fin[1]\nprint('unzipped_path', unzipped_path)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("rarexe == ''", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("boolean", "actionSuccess", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "topWin", "NA", None, this_step)
    psk_words = psk_words + step_words

    # subprocess.Popen(r'explorer /root,"'+zipped_full_path+'"')
    # rar_file = '/root,"'+zipped_full_path+'"'
    this_step, step_words = genStepOpenApp("cmd", True, "shell", "explorer", "expr", "zipped_full_path", "topWin", 3, "actionSuccess", this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepOpenApp("cmd", True, "shell", "rarexe", "expr", "zipped_full_path", "topWin", 3, "actionSuccess", this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # wait 5 seconds for the pop up to show.
    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words


    # pop up window size, could be 2 possible pop ups，
    # 1) is “Please purchase WinRAR license”， should click on ”close“ button
    # 2) is “Your free trial period has ended!”， should click on ”X“ button

    # verify the popup,

    # extract screen info,
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "winrar", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "expired_notification", "direct", "anchor text", "any", "useless", "rar_trial_end_popped", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "buy_license", "direct", "anchor text", "any", "useless", "rar_license_popped", "amz", False, this_step)
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

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "close", "anchor text", "", [0, 0], "center", [0, 0], "pixel", 0, 0, [0, 0], this_step)
    psk_words = psk_words + step_words
    # # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # now that the pops are closed. do the real work .....

    # click on "Extract to"
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "winrar", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "extract_to", "anchor text", "Extract To", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    # read the file dialog
    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "winrar", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "backspace", "", 0, this_step)
    psk_words = psk_words + step_words


    # do offset to new_folder button.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "new_folder", "anchor text", "New folder", [0, 0], "left", [2, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    # fill in the to be extracted dir
    this_step, step_words = genStepTextInput("var", False, "unzipped_path", "direct", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # no need on OK click, double <enter> did the job
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "OK", "anchor text", "OK", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0], this_step)
    # psk_words = psk_words + step_words

    # list the files to double check???

    # use hot key to close the winrar app window
    this_step, step_words = genStepKeyInput("", False, "alt,f4", "", 0, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_rar_local_unzip/unzip_archive", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genWinRarSkill(fpath, dest_dir, dest_name, theme, page, sect, ):
    log3("hello")