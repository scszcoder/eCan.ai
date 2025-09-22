import json
import re
import os
import copy
from datetime import timedelta, datetime

from utils.lazy_import import lazy
from PyPDF2 import PdfReader

from bot.basicSkill import genStepHeader, genStepStub, genStepOpenApp, genStepCreateData, genStepCheckCondition, \
    genStepTextToNumber, genStepSearchAnchorInfo, genStepLoop, genStepCallExtern, DEFAULT_RUN_STATUS, genStepMouseClick, \
    genStepExtractInfo, genStepKeyInput, get_default_download_dir, genStepWait, genStepCheckExistence, genStepTextInput, \
    genStepCreateDir, genStep7z, genStepUseSkill, STEP_GAP, unzip_file, list_zip_file, safe_rename
from bot.scrapeGoodSupply import genStepGSScrapeLabels
from bot.Logger import log3
import traceback
from bot.readSkill import symTab
from bot.Cloud import download_file

# https://www.onlinebarcodereader.com/
# https://online-barcode-reader.inliteresearch.com/

# dashboard
url = "https://goodsupply.xyz/Dashboard/Report"

# bulk create
ul_url = "https://goodsupply.xyz/Dashboard/UploadBulk"

gs_cost = 0
gs_service = ""
gs_order_file_path = ""
gs_order_file_name = ""
gs_load_args = []
gs_zipped_label_file = ""
gs_unzipped_dir = ""

# this skill assumes the following input "fin": [file path, file name, shipping service name (ex. "USPS Ground"), cost]
# the caller skill must get these ready. There will be no error handling here.
# Limitations: if there is only 1 row in xls, no rar file will be generated, the label will be generated and ready for download
# in the
# etsyOrdersTest11.xlsx_0914022831.zip will be created for download. this could take minutes to complete. and
# to see the files, have to enter calender from yesterdya to today to see the files.
# to get the download file, will need to go to "File Imported" page, and on calendar search past 2 days result and then click the download
# when ready. then can use command line to extract all. skip winrar skill..... if output is rar, then use rar skill if .zip then use:
# C:\Program Files\7-Zip\7z.exe e abc.zip -oC:\.....  will extract the zip file into C:\.... dir.
#

def genWinChromeGSLabelBulkBuySkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://goodsupply.xyz/Dashboard/UploadBulk"


    this_step, step_words = genStepHeader("win_chrome_goodsupply_label/bulk_buy", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001", "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_goodsupply_label/bulk_buy", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("boolean", "actionSuccess", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "topWin", "NA", None, this_step)
    psk_words = psk_words + step_words

    # open the web page.
    this_step, step_words = genStepOpenApp("Run", True, "browser", site_url, "expr", "sk_work_settings['cargs']", "topWin", 5, "actionSuccess", this_step)
    psk_words = psk_words + step_words

    # fin is the input, which contains usps service type, xls file name, and total price.
    # the algorithm is as following:
    # if funding is not enough:
    #   exit and send warning.
    # else:
    #   click on service drop down buton, type in search word, select the 1st one.
    #   click on choose file.
    #   use file open skill with xls file name.
    #   click on verifiy data button
    #   read screen
    #   if no error
    #       click on Import button
    #
    # while result file not ready:
    #   wait(1)
    #
    # read file to fill in tracking code into the order list.
    # close the web page.
    # readn screen

    this_step, step_words = genStepCreateData("string", "gen_label_status", "NA", "Success", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "gs_not_signed_in", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "labels_ready", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "xls_file", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "unzipped_path", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "scrape_status", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "n_files_processed", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nTCUpdated", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nLabelsInOrder", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "labelProcessedCount", "NA", 0, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "in_orders", "NA", 'fin[1]', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "order_data", "NA", 'fin[0]', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "in_files_dir", "NA", "fin[1][n_files_processed]['dir']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "zip7z_exe", "NA", 'fin[2]', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "rar_exe", "NA", 'fin[3]', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("str", "pidx", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "more_to_update", "NA", True, this_step)
    psk_words = psk_words + step_words


    dl_dir = get_default_download_dir()
    this_step, step_words = genStepCreateData("string", "dl_path", "NA", dl_dir, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "downloaded_zip_file", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_order_files\nn_order_files = len(fin[1])\nprint('n_order_files', n_order_files)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("float", "funds_left_number", "NA", -1.0, this_step)
    psk_words = psk_words + step_words

    #
    # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "winrar", "top", theme, this_step, None)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "gs_sign_in", "direct", "anchor text", "any", "junk", "gs_not_signed_in", "goodsupply", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("global gs_not_signed_in, junk\nprint('gs_not_signed_in:', gs_not_signed_in, 'junk:', junk)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCheckCondition("gs_not_signed_in", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # click on sign in button to sign in and after sign in, extract screen again and get ready to
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "gs_sign_in", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 5, [0, 0], this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    #
    # # enter the loop here, for each round of the loop, we'll process 1 xls file, the loop should :
    # # 1) open site again, by this time, there should be no log in problem.
    # # 2) extract available fund. check if fund is enough to complete this purchase.
    # # 3) if with enough fund. then go thru the sequence to open the xls file and verify data.
    # # 4) scroll till import to click import to import the file
    # #       (actually since verify data doesn't really work, maybe just directly click on import)
    # # 5) wait till the rar file is generated.
    # # 6) if generated - unrar, else, record error.
    # # 7) close the tab ?
    #

    this_step, step_words = genStepLoop("n_files_processed < n_order_files", "", "", "buyGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('n_files_processed:', n_files_processed, 'n_order_files:', n_order_files)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("boolean", "actionSuccess", "NA", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "topWin", "NA", None, this_step)
    psk_words = psk_words + step_words

    # open the web page again.
    this_step, step_words = genStepOpenApp("Run", True, "browser", site_url, "expr", "sk_work_settings['cargs']", "topWin", 5, "actionSuccess", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "available_fund", "direct", "info 1", "any", "funds_left", "gs_signed_in", "gen_label_status", False, this_step)
    psk_words = psk_words + step_words

    # # check whether we have enough money in the account, if so, then proceed to purchasing labels....
    # # this routine could be optimized later to purchase as much as the remaining fund allows.
    # # the principle is to spent on Ground Service labels as much as possible, because of the lower ISP.
    # # this should be a separate instruction or a skill routine?
    this_step, step_words = genStepCheckCondition("len(funds_left) > 0", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "funds_left_text", "NA", "funds_left[0]['text']", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepTextToNumber("funds_left_text", "funds_left_number", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global funds_left_number\nprint('funds_left_number:', funds_left_number)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global fin\nprint('n_files_processed:', n_files_processed, 'fin[1]:', fin[1][n_files_processed])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # make sure we have enough fund
    this_step, step_words = genStepCheckCondition("funds_left_number >= fin[1][n_files_processed]['price']", "", "", this_step)
    psk_words = psk_words + step_words


    # # now that we have enough fund to buy labels on this sheet. go and execute that.
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "export_template", "direct", "anchor text", "any", "junk", "page_load_status", "goodsupply", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "verify_data", "direct", "anchor text", "any", "vd_locs", "page_load_status", "goodsupply", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "direct", "export_template", "anchor text", "", [0, 0], "left", [2, 0], "box", 1, 3, [0, -3], this_step)
    # psk_words = psk_words + step_words
    #
    #
    # this_step, step_words = genStepCreateData("expr", "shipping_service", "NA", "fin[1][n_files_processed]['service']", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("global shipping_service\nprint('shipping_service:', shipping_service)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # type in the shipping service to be used.
    # this_step, step_words = genStepTextInput("var", False, "shipping_service", "direct", 1, "enter", 2, this_step)
    # psk_words = psk_words + step_words
    #
    # # bring up the file open dialog
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "choose_file", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    # psk_words = psk_words + step_words
    #
    # # set up input parameter to the file operation sub skill
    #
    # this_step, step_words = genStepCreateData("expr", "file_open_input", "NA", "['open', fin[1][n_files_processed]['dir'], fin[1][n_files_processed]['file']]", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepCallExtern("global file_open_input\nprint('file_open_input:', file_open_input)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_open_input", "fileStatus", this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "vd_locs[0]['loc']", "expr", "", [0, 0], "center", [0, 0], "box", 1, 5, [0, 0], this_step)
    # psk_words = psk_words + step_words
    #
    # # readn screen again after verify data.
    # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    # psk_words = psk_words + step_words
    #
    # # GS site will NOT check for xls field content errors like , empty field, wrong field like, 3 letter state short-hands, or 7 digit zip,
    # # only missing weight colume will be checked, so it's really important to make sure xls is right.
    # # so no checking of error here..... directly search for import button.
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "import", "direct", "anchor text", "any", "import_buttons", "found_import", "goodsupply", False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepLoop("found_import == False", "", "", "buyGSLabels" + str(stepN), this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    # psk_words = psk_words + step_words
    #
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "import", "direct", "anchor text", "any", "import_buttons", "found_import", "goodsupply", False, this_step)
    # psk_words = psk_words + step_words
    #
    # # end of find import button scroll down loop
    # this_step, step_words = genStepStub("end loop", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # click on OPEN button to complete the drill
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "import", "anchor text", "", 1, "center", [0, 0], "box", 0, 10, [0, 0], this_step)
    # psk_words = psk_words + step_words

    ######################## now go the to <File imported> section to check for the file available for download.

    # click on <File imported>
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "file_imported", "anchor text", "File Imported", [0, 0], "center", [0, 0], "box", 2, 3, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    dt_today_string = datetime.today().strftime('%m/%d/%Y')
    yesterday = datetime.today() - timedelta(days=1)
    dt_yesterday_string = yesterday.strftime('%m/%d/%Y')
    dt_range_string = dt_yesterday_string + " - " + dt_today_string
    md_string = datetime.today().strftime('%m%d')

    log3("MD string is:"+md_string)

    this_step, step_words = genStepMouseClick("Triple Click", "", True, "screen_info", "apply", "anchor text", "Apply", [0, 0], "left", [1, 0], "box", 1, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", False, "bacckspace", "", 1, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "today_date_range", "NA", dt_range_string, this_step)
    psk_words = psk_words + step_words

    #now type in the correct date range
    # fill in the to be extracted dir
    this_step, step_words = genStepTextInput("var", False, "today_date_range", "direct", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words




    # wait timeout until the label file is ready. this could take as long as 5 minutes.....
    this_step, step_words = genStepCreateData("int", "gs_timeout", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # 40 x 15 second = 10 minutes, that's our time out time.
    this_step, step_words = genStepLoop("labels_ready != True and gs_timeout < 40", "", "", "waitGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # check every 15 seconds.
    this_step, step_words = genStepWait(15, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now hit Apply again.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "apply", "anchor text", "Apply",
                                              [0, 0], "center", [0, 0], "box", 2, 3, [0, 0], this_step)
    psk_words = psk_words + step_words

    # at this point, we should see list of files generated, and we should search for our file which has a pre-determined prefix.
    # now extract the screen again，

    this_step, step_words = genStepCreateData("expr", "file_wo_extension", "NA", "fin[1][n_files_processed]['file'].split('.')[0]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "partial", "NA", "{\\\"info\\\": [{\\\"info_name\\\": \\\"zip_row\\\", \\\"info_type\\\": \\\"lines 1\\\", \\\"template\\\": \\\"", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global file_wo_extension\nfile_wo_extension = partial + file_wo_extension", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "tail", "NA", ".*\\\", \\\"ref_method\\\": \\\"1\\\", \\\"refs\\\": [{\\\"dir\\\": \\\"left inline\\\", \\\"ref\\\": \\\"download\\\", \\\"offset\\\": 0, \\\"offset_unit\\\": \\\"box\\\"}]}]}", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "todate", "NA", md_string, this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallExtern("global file_wo_extension\nfile_wo_extension = file_wo_extension + todate + tail", "", "in_line", "", this_step)
    this_step, step_words = genStepCallExtern("global file_wo_extension\nfile_wo_extension = file_wo_extension + tail", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("sk_work_settings['options'] = file_wo_extension", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "zip_row", "direct", "info 1", "any", "zip_download_locs", "labels_ready", "goodsupply", False, this_step)
    psk_words = psk_words + step_words


    ######################## end of checking whether the zip/rar file is ready

    # check every 15 seconds.
    this_step, step_words = genStepCallExtern("sk_work_settings['options'] = file_wo_extension", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_timeout\ngs_timeout = gs_timeout + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    ###############################################################################################
    # now that shipping labels generated, use unrar skill to unzip it.
    ##############################################################################################
    # this_step, step_words = genStepCallExtern("global labels_ready\nlabels_ready = True", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("labels_ready", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "download", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 6, [0, 0], this_step)
    psk_words = psk_words + step_words
    #
    this_step, step_words = genStepCreateData("string", "dl_path", "NA", dl_dir, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepGSExtractZippedFileName("zip_download_locs", "dl_file_name", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global dl_path,downloaded_zip_file\ndownloaded_zip_file = dl_path + dl_file_name + '.zip'\nprint('downloaded_zip_file', downloaded_zip_file)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # should be a loop here....
    this_step, step_words = genStepCheckExistence("file var", "downloaded_zip_file", "zip_downloaded", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global gs_timeout\ngs_timeout = 0", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("zip_downloaded != True and gs_timeout < 5", "", "", "waitGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckExistence("file var", "downloaded_zip_file", "zip_downloaded", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_timeout\ngs_timeout = gs_timeout + 1\nprint('gs_timeout:',gs_timeout)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now that the file is downloaded, unzip it.

    # first, make sure the unzipped dir exits. , then unzip it.
    # this_step, step_words = genStepCallExtern("global downloaded_zip_file\ndownloaded_zip_file = 'etsyOrdersPriority09122023.xls_0918221925'\nprint('downloaded_zip_file:',downloaded_zip_file)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global in_files_dir, n_files_processed, dl_file_name\nin_files_dir = fin[1][n_files_processed]['dir']+'/'+dl_file_name\nprint('in_files_dir:',in_files_dir)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallExtern("global downloaded_zip_file\ndownloaded_zip_file = dl_path+downloaded_zip_file\nprint('downloaded_zip_file:',downloaded_zip_file)", "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    # create the unzipped dir....
    this_step, step_words = genStepCreateDir("in_files_dir", "direct", "fileStatus", this_step)
    psk_words = psk_words + step_words

    # genStep7z(action, var_type, exe_var, in_var, out_path, out_var, result, stepN):
    this_step, step_words = genStep7z("unzip", "expr", "zip7z_exe", "downloaded_zip_file", "in_files_dir", "", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepKeyInput("", False, "ctrl,x", "", 1, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now go back and obtain the tracking code and update the data structure with the tracking code.
    # this is done by scraping the GS tracking code web page....
    # now obtain tracking code. of the files....
    # click on <File imported>
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "transaction_usps", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    #now triple click and delete.
    this_step, step_words = genStepMouseClick("Triple Click", "", True, "screen_info", "apply", "anchor text", "Apply", [0, 0], "left", [1, 0], "box", 1, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", False, "bacckspace", "", 1, this_step)
    psk_words = psk_words + step_words

    #now type in the correct date range
    # fill in the to be extracted dir
    this_step, step_words = genStepTextInput("var", False, "today_date_range", "direct", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    #now hit Apply again.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "apply", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    this_step, step_words = genStepLoop("more_to_update and pidx != '0'", "", "", "waitGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "download_success", "direct", "anchor text", "any", "dl_successes", "labels_downloaded", "goodsupply", False, this_step)
    psk_words = psk_words + step_words


    # 40 x 15 second = 10 minutes, that's our time out time.
    this_step, step_words = genStepLoop("labels_downloaded != True", "", "", "waitGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "apply", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 5, [0, 0], this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "download_success", "direct", "anchor text", "any", "dl_successes", "download_status", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now save and scrape html which is the easiest way to get all the necessary infomation.....
    # again, this could span many pages.... and a particular, note is that due to screen size, the location of that
    # customer service chat icon could be located just there to block the last page index
    this_step, step_words = genStepCreateDir("sk_work_settings['log_path']", "expr", "fileStatus", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepKeyInput("", True, "ctrl,s", "", 4, this_step)
    psk_words = psk_words + step_words

    # save the html file.
    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))
    hfname = "etsyOrders" + dt_string + ".html"

    this_step, step_words = genStepCreateData("str", "hfname", "NA", hfname, this_step)
    psk_words = psk_words + step_words

    log3("SAVE HTML FILE: "+hfname)
    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA", "['save', sk_work_settings['log_path'], hfname]", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_save_input", "fileStatus", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepWait(12, 0, 0, this_step)
    psk_words = psk_words + step_words

    # now html saved, scrape the html
    this_step, step_words = genStepCreateData("expr", "html_file", "NA", "sk_work_settings['log_path'] + hfname", this_step)
    psk_words = psk_words + step_words

    # after scraping the etsy_orders data will be updated and ready to update to Etsy or any other ecommerce stores.....
    this_step, step_words = genStepGSScrapeLabels("html_file", "pidx", "order_data", "nTCUpdated", "more_to_update", this_step)
    psk_words = psk_words + step_words


    #if there is more to update，now click on next page......, first obtain the location of the next page number....

    this_step, step_words = genStepCreateData("string", "partial", "NA", "{\\\"info\\\": [{\\\"info_name\\\": \\\"page_n_loc\\\", \\\"info_type\\\": \\\"lines 1\\\", \\\"template\\\": \\\"", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global ops_string\nops_string = partial + pidx", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "tail", "NA", "\\\", \\\"ref_method\\\": \\\"1\\\", \\\"refs\\\": [{\\\"dir\\\": \\\"right inline\\\", \\\"ref\\\": \\\"entries\\\", \\\"offset\\\": 0, \\\"offset_unit\\\": \\\"box\\\"}]}]}", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallExtern("global file_wo_extension\nfile_wo_extension = file_wo_extension + todate + tail", "", "in_line", "", this_step)
    this_step, step_words = genStepCallExtern("global ops_string\nops_string = ops_string + tail\nprint('ops_string', ops_string)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("sk_work_settings['options'] = ops_string", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "page_n_loc", "direct", "info 1", "any", "page_n_locs", "found_next_page", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("found_next_page", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "page_n_loc", "info 1", "", [0, 0], "center", [0, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", "sk_work_settings", "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of all pages of tracking code....
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # end of if label is ready.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # end of if there is enough fund.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # increment n files processed counter....
    this_step, step_words = genStepCallExtern("global n_files_processed\nn_files_processed = n_files_processed + 1\nprint('n_files_processed', n_files_processed)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for processin all order xls files.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end skill", "public/win_chrome_goodsupply_label/bulk_buy", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # log3("DEBUG", "generated skill for buy shipping labels in bulk...." + psk_words)

    return this_step, psk_words



def genStepGSExtractZippedFileName(screen_txt_var, outvar, statusvar, stepN):
    stepjson = {
        "type": "GS Extract Zipped",
        "zipped_screen_text": screen_txt_var,
        "result": outvar,
        "status": statusvar
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processGSExtractZippedFileName(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        log3("extracting from:"+json.dumps(symTab[step["zipped_screen_text"]]))
        fn_txt = x = re.sub(' +', ' ', symTab[step["zipped_screen_text"]][0]["text"])
        fn_txts = fn_txt.split(" ")

        # Define a regular expression pattern to match "x*s" where * can be any character
        pattern = r'\.x\ws'

        # Use re.sub() to replace all occurrences of the pattern with "xls"
        symTab[step["result"]] = re.sub(pattern, '.xls', fn_txts[0])
        # log3("Extracted ZIPPED file name:", symTab[step["result"]])
    except:
        ex_stat = "ErrorGSExtractZippedFileName:" + str(i)
        log3(ex_stat)

    return (i + 1), ex_stat



def searchTrackingCodeFromPdf(pdffile):
    reader = PdfReader(pdffile)

    # printing number of pages in pdf file
    # log3(str(len(reader.pages)))

    # getting a specific page from the pdf file
    page = reader.pages[0]

    # extracting text from page
    text = page.extract_text()

    # luckily, for good supply generated label, there is only 1 line of text in the pdf which is the tracking code.
    words = text.split()
    tc = ""
    tc = tc.join(words)
    log3("tracking code:["+tc+"]")
    return tc


def genStepPrepareGSOrder(order_var_name, gs_order_var_name, prod_book_var_name, seller, ec_platform, fpath, stepN):

    stepjson = {
        "type": "Prepare GS Order",
        "ec_order": order_var_name,
        "gs_order": gs_order_var_name,
        "prod_book": prod_book_var_name,
        "ec_platform": ec_platform,
        "file_path": fpath,
        "seller": seller
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processPrepareGSOrder(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        gs_label_orders = []
        ec_platform = step["ec_platform"]
        seller = symTab[step["seller"]]
        file_path = symTab[step["file_path"]]
        new_orders = symTab[step["ec_order"]]
        print("ec_order: # new_orders", step["ec_order"], len(new_orders))
        print("ec_platform, seller, file_path", ec_platform, seller, file_path)
        # collaps all pages of order list into a single list or orders.
        flatlist=[element for sublist in new_orders for element in sublist["ol"]]

        log3("FLAT LIST: "+str(len(flatlist)))

        # combine orders into same person and address into 1 order.
        combined = combine_duplicates(flatlist)

        # filter out Non-USA orders. International Orders such as canadian and mexican should be treatly separately at this time.
        us_orders = [o for o in combined if o.getRecipientAddrState() != "Canada" and o.getRecipientAddrState() != "Mexico"]

        # don't put in the order that's not going to be fullfilled by the seller him/her self.
        fbs_orders = [o for o in us_orders if orderIsForFBS(o, ec_platform, symTab[step["prod_book"]])]

        # group orders into two categories: weights less than 1lb and weights more than 1lb
        light_orders = [o for o in fbs_orders if calcOrderWeight(o, ec_platform, symTab[step["prod_book"]]) < 16 ]
        regular_orders = [o for o in fbs_orders if calcOrderWeight(o, ec_platform, symTab[step["prod_book"]]) >= 16]

        # ofname is the order file name, should be etsy_orders+Date.xls
        # dt_string = datetime.now().strftime('%Y%m%d%H%M%S%f')
        dt_string = datetime.now().strftime('%Y%m%d%H%M%S')
        # today for testing only:
        dt_string = "20240901202600"

        if len(light_orders) > 0:
            ofname1 = file_path+"/"+ec_platform+"OrdersGround"+dt_string+".xlsx"
            zipped_ofname1 = ec_platform+"OrdersGround"+dt_string+".zip"
            ofname1_unzipped = file_path + "/"+ec_platform+"OrdersGround" + dt_string
            gs_order_data = createLabelOrderFile(seller, "ozs", light_orders, ec_platform, symTab[step["prod_book"]], ofname1)
            gs_label_orders.append({"service":"USPS Ground Advantage (1-15oz)",
                                    "price": len(light_orders)*2.25,
                                    "num_orders": len(light_orders),
                                    "dir": os.path.dirname(ofname1),
                                    "file": os.path.basename(ofname1),
                                    "zip_dir": os.path.dirname(ofname1),   #must consider cloud side dir structure and naming scheme
                                    "zip_file": zipped_ofname1,
                                    "unzipped_dir": ofname1_unzipped,
                                    "order_data": gs_order_data,
                                    "succeed": True,
                                    "result": ""
                                    })

            #create unziped label dir ahead of time.
            if not os.path.exists(ofname1_unzipped):
                os.makedirs(ofname1_unzipped)

        if len(regular_orders) > 0:
            ofname2 = file_path+"/"+ec_platform+"OrdersPriority"+dt_string+".xlsx"
            zipped_ofname2 = ec_platform + "OrdersPriority" + dt_string + ".zip"
            ofname2_unzipped =  file_path+"/"+ec_platform+"OrdersPriority"+dt_string

            gs_order_data = createLabelOrderFile(seller, "lbs", regular_orders, ec_platform, symTab[step["prod_book"]], ofname2)
            gs_label_orders.append({"service":"USPS Priority V4",
                                    "price": len(regular_orders)*3,
                                    "num_orders": len(regular_orders),
                                    "dir": os.path.dirname(ofname2),
                                    "file": os.path.basename(ofname2),
                                    "zip_dir": os.path.dirname(ofname2),   #must consider cloud side dir structure and naming scheme
                                    "zip_file": zipped_ofname2,
                                    "unzipped_dir": ofname2_unzipped,
                                    "order_data": gs_order_data,
                                    "succeed": True,
                                    "result": ""
                                    })

            #create unziped label dir ahead of time.
            if not os.path.exists(ofname2_unzipped):
                os.makedirs(ofname2_unzipped)

        print("GS labels orders:", gs_label_orders)
        symTab[step["gs_order"]] = gs_label_orders

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorPrepareGSOrder:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorPrepareGSOrder: traceback information not available:" + str(e)

        log3(ex_stat)

    return next_i, ex_stat


def combine_duplicates(orders):
    merged_dict = {}
    for order in orders:
        key = (order.getRecipientName(), order.getRecipientAddrStreet1(), order.getRecipientAddrStreet2(), order.getRecipientAddrCity(), order.getRecipientAddrState())
        if key in merged_dict:
            merged_dict[key].products.extend(order.products)
            merged_dict[key].combineOid(order.getOid())
        else:
            merged_dict[key] = copy.deepcopy(order)

    return list(merged_dict.values())

# ofname is the order file name, should be etsy_orders+Date.xls
def createLabelOrderFile(seller, weight_unit, orders, ec_platform, book, ofname):
    gs_orders = []
    if weight_unit == "ozs":
        allorders = [{
            "No": str(oi+1),
            "FromName": seller["FromName"],
            "PhoneFrom": seller["PhoneFrom"],
            "Address1From": seller["Address1From"],
            "CompanyFrom": "",
            "Address2From": seller["Address2From"],
            "CityFrom": seller["CityFrom"],
            "StateFrom": seller["StateFrom"],
            "ZipCodeFrom": seller["ZipCodeFrom"],
            "NameTo": o.getRecipientName(),
            "PhoneTo": o.getRecipientPhone(),
            "Address1To": o.getRecipientAddrStreet1(),
            "CompanyTo": "",
            "Address2To": o.getRecipientAddrStreet2(),
            "CityTo": o.getRecipientAddrCity(),
            "StateTo": o.getRecipientAddrState(),
            "ZipTo": o.getRecipientAddrZip(),
            "Weight": calcOrderWeight(o, ec_platform, book, "ozs"),
            "length": calcOrderLength(o, ec_platform, book, "inches"),
            "width": calcOrderWidth(o, ec_platform, book, "inches"),
            "height": calcOrderHeight(o, ec_platform, book, "inches"),
            "description": ""
        } for oi, o in enumerate(orders)]
    else:
        allorders = [{
            "No": str(oi+1),
            "FromName": seller["FromName"],
            "PhoneFrom": seller["PhoneFrom"],
            "Address1From": seller["Address1From"],
            "CompanyFrom": "",
            "Address2From": seller["Address2From"],
            "CityFrom": seller["CityFrom"],
            "StateFrom": seller["StateFrom"],
            "ZipCodeFrom": seller["ZipCodeFrom"],
            "NameTo": o.getRecipientName(),
            "PhoneTo": o.getRecipientPhone(),
            "Address1To": o.getRecipientAddrStreet1(),
            "CompanyTo": "",
            "Address2To": o.getRecipientAddrStreet2(),
            "CityTo": o.getRecipientAddrCity(),
            "StateTo": o.getRecipientAddrState(),
            "ZipTo": o.getRecipientAddrZip(),
            "Weight": calcOrderWeight(o, ec_platform, book, "lbs"),
            "length": calcOrderLength(o, ec_platform, book, "inches"),
            "width": calcOrderWidth(o, ec_platform, book, "inches"),
            "height": calcOrderHeight(o, ec_platform, book, "inches"),
            "description": ""
        } for oi, o in enumerate(orders)]

    gs_orders = [{
            "name": o.getRecipientName(),
            "order_ids": [o.getOid()]+o.getCombinedOids(),
            "tracking": ""
        } for oi, o in enumerate(orders)]

    df = lazy.pd.DataFrame(allorders)

    # Save to .xls file
    # Create a new workbook and select the active worksheet
    wb = lazy.openpyxl.Workbook()
    ws = wb.active

    # Write data to worksheet
    for r in lazy.openpyxl.utils.dataframe.dataframe_to_rows(df, index=False, header=True):
        ws.append(r)

    # Iterate through rows in column 2 (the 'age' column)
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = '@'  # text format

    log3("saving to file: "+ofname)
    ofdir = os.path.dirname(ofname)
    if not os.path.exists(ofdir):
        os.makedirs(ofdir)
    # Save workbook
    wb.save(ofname)

    return gs_orders

def compSentences(sent1, sent2):
    cleaned_sent1 = re.sub(r'\s+', ' ', sent1.strip())
    cleaned_sent2 = re.sub(r'\s+', ' ', sent2.strip())
    return (cleaned_sent1 == cleaned_sent2)


# if 1 product is not FBS, then the whole order is FBS... requires manual work.....
def orderIsForFBS(order, ec_platform, pbook):
    fbs = True
    for op in order.getProducts():
        prod = next((p for i, p in enumerate(pbook) if any(listing["platform"] == ec_platform and compSentences(listing["title"], op.getPTitle()) for listing in p["listings"])), None)
        if prod:
            listing = next((l for i, l in enumerate(prod["listings"]) if l["platform"] == ec_platform and compSentences(l["title"], op.getPTitle())), None)
            if listing["fullfiller"] != "self":
                fbs = False
                break
    return fbs

def calcOrderWeight(order, ec_platform, pbook, unit="ozs"):
    total_weight = 0
    for op in order.getProducts():
        prod = next((p for i, p in enumerate(pbook) if any(listing["platform"] == ec_platform and compSentences(listing["title"], op.getPTitle()) for listing in p["listings"])), None)
        if prod:
            listing = next((l for i, l in enumerate(prod["listings"]) if l["platform"] == ec_platform and compSentences(l["title"], op.getPTitle())), None)
            if listing["variations"]:
                pv = op.getVariations()
                vweight = next((vw for i, vw in enumerate(listing["weight"]) if all(pv[pvn] == vw[pvn] for pvn in pv)), None)
                print("adding variation weight:", vweight, int(op.getQuantity()))
                total_weight = total_weight + vweight["weight"] * int(op.getQuantity())
            else:
                print("adding weight:", listing["weight"], int(op.getQuantity()))
                total_weight = total_weight + listing["weight"] * int(op.getQuantity())
        else:
            print("WARNING: PRODUCT NOT FOUND["+op.getPTitle()+"]")

    if unit == "lbs":
        total_weight = total_weight/16
        print("calculated weight in lbs", total_weight)
    else:
        print("calculated weight in ozs", total_weight)

    return total_weight



def calcOrderLength(order, ec_platform, pbook, unit="inches"):
    total_length = 0
    for op in order.getProducts():
        prod = next((p for i, p in enumerate(pbook) if any(listing["platform"] == ec_platform and compSentences(listing["title"], op.getPTitle()) for listing in p["listings"])), None)
        if prod:
            listing = next((l for i, l in enumerate(prod["listings"]) if l["platform"] == ec_platform and compSentences(l["title"], op.getPTitle())), None)
            if listing["variations"]:
                pv = op.getVariations()
                vsize = next((vw for i, vw in enumerate(listing["size"]) if all(pv[pvn] == vw[pvn] for pvn in pv)), None)
                print("adding variation dimension length:", vsize, int(op.getQuantity()))
                if vsize["dimension"][0] > total_length:
                    total_length = vsize["dimension"][0]
            else:
                print("adding size:", listing["size"], int(op.getQuantity()))
                if listing["size"][0] > total_length:
                    total_length = listing["size"][0]

    print("calculated length", total_length)
    return total_length

def calcOrderWidth(order, ec_platform, pbook, unit):
    total_width = 0
    for op in order.getProducts():
        prod = next((p for i, p in enumerate(pbook) if any(
            listing["platform"] == ec_platform and compSentences(listing["title"], op.getPTitle()) for listing in p["listings"])),
                    None)
        if prod:
            listing = next((l for i, l in enumerate(prod["listings"]) if l["platform"] == ec_platform and compSentences(l["title"], op.getPTitle())), None)
            if listing["variations"]:
                pv = op.getVariations()
                vsize = next((vw for i, vw in enumerate(listing["size"]) if all(pv[pvn] == vw[pvn] for pvn in pv)), None)
                print("adding variation dimension width:", vsize, int(op.getQuantity()))
                if vsize["dimension"][1] > total_width:
                    total_width = vsize["dimension"][1]
            else:
                print("adding size:", listing["size"], int(op.getQuantity()))
                if listing["size"][1] > total_width:
                    total_width = listing["size"][1]

    print("calculated width", total_width)
    return total_width

def calcOrderHeight(order, ec_platform, pbook, unit):
    total_height = 0
    for op in order.getProducts():
        prod = next((p for i, p in enumerate(pbook) if any(listing["platform"] == ec_platform and compSentences(listing["title"], op.getPTitle()) for listing in p["listings"])), None)
        if prod:
            listing = next((l for i, l in enumerate(prod["listings"]) if l["platform"] == ec_platform and compSentences(l["title"], op.getPTitle())), None)
            if listing["variations"]:
                pv = op.getVariations()
                vsize = next((vw for i, vw in enumerate(listing["size"]) if all(pv[pvn] == vw[pvn] for pvn in pv)), None)
                print("adding variation dimension height:", vsize, int(op.getQuantity()))
                total_height = total_height + vsize["dimension"][2] * int(op.getQuantity())
            else:
                print("adding height:", listing["size"], int(op.getQuantity()))
                total_height = total_height + listing["size"][2] * int(op.getQuantity())

    print("calculated height", total_height)
    return total_height


def findProdName(pid, catelog, ):
    pname = ""
    for item in catelog:
        for listing in item['listings']:
            if pid == listing['asin']:
                if 'short name' in item:
                    pname = item['short name']
                else:
                    pname = item['product name']
                break
        if pname:
            break

    return pname, listing


def findVarShortNames(in_vars, book_item):
    short_vars = {}
    if in_vars:
        for in_var in in_vars.keys():
            var_val = in_vars[in_var]

            if "short" in  book_item['variations'][in_var]['vals'][var_val]:
                short_vars[in_var] = book_item['variations'][in_var]['vals'][var_val]['short']
            else:
                short_vars[in_var] = in_vars[in_var]

    return short_vars

# ebay_orders data structure
# ebay_orders = [ pagefull_of_orders ....]
# pagefull_of_orders =  {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": [
# {
#   order class
# }
# ]}
#
# order class:
#    oid
#    products [ {pid, title, quantity, variations {var_name1: var_value1, var_name2: var_value2 ...}} .... ]
#    recipient : id, ship addr,
#    shipping: carrier, method,
def lookUpProductNameQuantityAndUpdateTracking(order_ids, tracking_code):
    # symTab['product_book'], symTab['ebay_orders']
    products = []
    found_order = None
    for oid in order_ids:
        # look up products in orders.
        found_order = None
        for page_of_order in symTab['ebay_orders']:
            for order in page_of_order["ol"]:
                if oid == order.getOid():
                    found_order = order
                    break
            if found_order:
                break

        if found_order:
            pds = found_order.getProducts()
            # for each product, look up variations
            for prod in pds:
                pname, listing = findProdName(prod.getPid(), symTab['product_book'])
                product = {
                    "name": pname,
                    "pvs": findVarShortNames(prod.getVariations(), listing),
                    "quant": prod.getQuantity()
                }
                products.append(product)

            order.setShippingTracking(tracking_code)

    return products


def setLabelsReady():
    symTab['labels_ready'] = True
    print("LABELS READY"+str(symTab['labels_ready']))



def handleExtLabelGenResults(session, token, endpoint, ext_run_results):
    for req in ext_run_results:  # per batch of orders for one shipping method.
        dl_stat = download_file(session, req['zip_dir'], req['zip_file'], req['zip_dir'], token, endpoint,"general")
        dl_zip = req['zip_dir'] + "/" + req['zip_file']
        print("dl_zip", dl_zip, req['zip_dir'])
        unzip_file(dl_zip, req['zip_dir'])
        rel_zip_contents = list_zip_file(dl_zip)  # obtain pdf files from the zipped lable files.
        zip_contents = [req['zip_dir'] + "/" + rel_file for rel_file in rel_zip_contents if 'pdf' in rel_file]
        print("zip_contents:", zip_contents)
        # now zip_contents is a list of label files in pdf format. now we need to update
        # tracking info and pdf file name into the original ebay_orders data structure,
        # this will make the data structure ready for the next stage of the RPA process which is update
        # tracking code. and the labels will be need to be further renamed to include product info in it.
        # file name should start with ec site like "ebay" then recipient then product then tracking code.pdf
        # the files should be moved into ecb_labels dir and this directory name will be put as the input to the
        # label reformat and print skill.

        for fi, full_file_name in enumerate(zip_contents):  # per each shipping label (i.e. order)
            f_name = os.path.basename(full_file_name)
            f_dir = os.path.dirname(full_file_name)
            final_f_dir = os.path.dirname(f_dir)
            full_f_name_prefix = f_name.split(".")[0]

            f_name_prefix = full_f_name_prefix.split("_")[0]+"_"+full_f_name_prefix.split("_")[1][-5:]

            # print("f_name_prefix:", f_name_prefix, "f_name:", f_name, "f_dir:", f_dir, "final_f_dir:", final_f_dir)
            # print("order_ids:", req['order_data'][fi]['order_ids'], "tracking:", req['order_data'][fi]['tracking'])
            # update tracking code to the origianl ebay_orders data structure, and find the products involved in this order.
            prods = lookUpProductNameQuantityAndUpdateTracking(req['order_data'][fi]['order_ids'], req['order_data'][fi]['tracking'])
            # use order Id to get products (including variations) and quantity,
            # use porduct id to get product name, use variation get variations short hand.
            prodq_info = "_"
            for pi, pd in enumerate(prods):
                prodq_info = prodq_info + "".join(pn.capitalize() for pn in pd['name'].split())  # product name no space, each word's 1st letter capitalized.
                print("per product prodq_info:[" + prodq_info + "]")
                if pd['pvs']:  # whether this product has variations
                    for pvi, pvn in enumerate(pd['pvs'].keys()):  # iterate thru variation dimensions
                        prodq_info = prodq_info + "".join(pn.capitalize() for pn in str(pd['pvs'][pvn]).split())  # product name + variation1name + variation2name etc. + "_" + quantity
                        print("per variation, prodq_info:[" + prodq_info + "]")
                        # if pvi == len(pd['pvs'].keys()) - 1:
                        #     prodq_info = prodq_info + "_"
                        #     print("last variation, prodq_info:[" + prodq_info + "]")
                prodq_info = prodq_info + "_" + str(pd['quant'])  # MenShirtRedMedium_1_GirsTennisSneakerSmall6_2
                print("add quantity, prodq_info:[" + prodq_info + "]")
                if pi < len(prods) - 1:
                    prodq_info = prodq_info + "_"
                    print("not last product, prodq_info:[" + prodq_info + "]")

            # now ready to put product name + variation + quantity into the label file name.
            final_prefix = f_name_prefix + prodq_info
            # make sure file name never too long.
            if len(final_prefix) > 60:
                final_prefix = final_prefix[:60]
            new_f_name = final_prefix + ".pdf"
            new_file = final_f_dir + "/" + new_f_name
            # rename the shipping label file and move it to a common dir for this run.
            print("rename label from: " + full_file_name + " TO: " + new_file)
            safe_rename(full_file_name, new_file)
            # os.rename(full_file_name, new_file)

    # finally set the global flag for the relavant event(s) so that the RPA loop can continue...
    setLabelsReady()


