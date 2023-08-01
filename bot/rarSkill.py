import os
import subprocess
import platform
import errno
from basicSkill import *


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


# this function takes  extractions, costs
def genWinUnRarSkill(lieutenant, bot_works, stepN, theme):
    psk_words = []
    subprocess.Popen(r'explorer /root,"C:\Users\songc\Downloads\etsy_order.rar"')

    # pop up window size, could be 2 possible pop ups，
    # 1) is “Please purchase WinRAR license”， should click on ”close“ button
    # 2) is “Your free trial period has ended!”， should click on ”X“ button

    # verify the popup,

    # extract screen info,
    this_step, step_words = genStepExtractInfo("", root, "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["free_trial_ended"], ["anchor text"], "any", "useless", "rar_trial_end_popped", "amz", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["please_purchase_license"], ["anchor text"], "any", "useless", "rar_license_popped", "amz", this_step)
    psk_words = psk_words + step_words

    # and click on upper right corner to close the pop up or click on Close button to close the pop-up window depends on which popup it is.
    this_step, step_words = genStepCheckCondition("rar_trial_end_popped", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Extract_To", "anchor text", "Extract To", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words
    # # close bracket
    this_step, step_words = genStepStub("else", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Extract_To", "anchor text", "Extract To", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words
    # # close bracket
    this_step, step_words = genStepStub("end condition", "", this_step)
    psk_words = psk_words + step_words


    # click on "Extract to"
    this_step, step_words = genStepExtractInfo("", root, "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Extract_To", "anchor text", "Extract To", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    # read the file dialog popup
    this_step, step_words = genStepExtractInfo("", root, "screen_info", "all_reviews", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    # do offset to new_folder button.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "new_folder", "anchor text", "New folder", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    # fill in the to be extracted dir
    this_step, step_words = genStepTextInput("type", run["entry_paths"]["words"], 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "OK", "anchor text", "OK", [0, 0], "center", [0, 0], "pixel", 2, 0, this_step)
    psk_words = psk_words + step_words

    # list the files to double check.



def genWinRarSkill(fpath, dest_dir, dest_name, theme, page, sect, ):
    print("hello")