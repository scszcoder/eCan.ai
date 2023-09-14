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
def genWinChromeGSLabelBulkBuySkill(worksettings, page, sect, stepN, theme):
    psk_words = "{"
    site_url = "https://goodsupply.xyz/Dashboard/UploadBulk"


    this_step, step_words = genStepHeader("win_chrome_goodsupply_label/bulk_buy", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001", "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_goodsupply_label/bulk_buy", "", this_step)
    psk_words = psk_words + step_words

    # open the web page.
    this_step, step_words = genStepOpenApp("Run", True, "browser", site_url, "", "", worksettings["cargs"], 5, this_step)
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

    this_step, step_words = genStepCreateData("int", "n_files_processed", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global n_order_files\nn_order_files = len(fin)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("float", "funds_left", "NA", 0.0, this_step)
    psk_words = psk_words + step_words



    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", "gs_sign_in", "anchor text", "any", "junk", "gs_not_signed_in", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_not_signed_in, junk\nprint('gs_not_signed_in:', gs_not_signed_in, 'junk:', junk)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("gs_not_signed_in", "", "", this_step)
    psk_words = psk_words + step_words

    # click on sign in button to sign in and after sign in, extract screen again and get ready to
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "gs_sign_in", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # enter the loop here, for each round of the loop, we'll process 1 xls file, the loop should :
    # 1) open site again, by this time, there should be no log in problem.
    # 2) extract available fund. check if fund is enough to complete this purchase.
    # 3) if with enough fund. then go thru the sequence to open the xls file and verify data.
    # 4) scroll till import to click import to import the file
    #       (actually since verify data doesn't really work, maybe just directly click on import)
    # 5) wait till the rar file is generated.
    # 6) if generated - unrar, else, record error.
    # 7) close the tab ?


    this_step, step_words = genStepLoop("n_files_processed < n_order_files", "", "", "buyGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    # open the web page again.
    this_step, step_words = genStepOpenApp("Run", True, "browser", site_url, "", "", worksettings["cargs"], 5, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", "available_fund", "info 1", "any", "funds_left", "gs_signed_in", "gen_label_status", False, this_step)
    psk_words = psk_words + step_words

    # check whether we have enough money in the account, if so, then proceed to purchasing labels....
    # this routine could be optimized later to purchase as much as the remaining fund allows.
    # the principle is to spent on Ground Service labels as much as possible, because of the lower ISP.
    # this should be a separate instruction or a skill routine?
    this_step, step_words = genStepCheckCondition("len(funds_left) > 0", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "funds_left_text", "NA", "funds_left[0]['text']", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("float", "funds_left_number", "NA", 0.0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepTextToNumber("funds_left_text", "funds_left_number", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global funds_left_number\nprint('funds_left_number:', funds_left_number)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # make sure we have enough fund
    this_step, step_words = genStepCheckCondition("funds_left_number >= fin[n_files_processed]['price']", "", "", this_step)
    psk_words = psk_words + step_words


    # now that we have enough fund to buy labels on this sheet. go and execute that.
    this_step, step_words = genStepSearch("screen_info", "export_template", "anchor text", "any", "junk", "page_load_status", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", "verify_data", "anchor text", "any", "vd_locs", "page_load_status", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "export_template", "anchor text", "", [0, 0], "left", [2, 0], "box", 1, 3, [0, -3], this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("expr", "shipping_service", "NA", "fin[n_files_processed]['service']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global shipping_service\nprint('shipping_service:', shipping_service)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # type in the shipping service to be used.
    this_step, step_words = genStepTextInput("var", False, "shipping_service", 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # bring up the file open dialog
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "choose_file", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    # set up input parameter to the file operation sub skill

    this_step, step_words = genStepCreateData("expr", "file_open_input", "NA", "['open', fin[n_files_processed]['dir'], fin[n_files_processed]['file']]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global file_open_input\nprint('file_open_input:', file_open_input)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_open_input", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "vd_locs[0]['loc']", "expr", "", [0, 0], "center", [0, 0], "box", 1, 5, [0, 0], this_step)
    psk_words = psk_words + step_words

    # readn screen again after verify data.
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # GS site will NOT check for xls field content errors like , empty field, wrong field like, 3 letter state short-hands, or 7 digit zip,
    # only missing weight colume will be checked, so it's really important to make sure xls is right.
    # so no checking of error here..... directly search for import button.
    this_step, step_words = genStepSearch("screen_info", "import", "anchor text", "any", "import_buttons", "found_import", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("found_import == False", "", "", "buyGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "label", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", "import", "anchor text", "any", "import_buttons", "found_import", "goodsupply", False, this_step)
    psk_words = psk_words + step_words

    # end of find import button scroll down loop
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "import", "anchor text", "", [0, 0], "center",
    #                                           [0, 0], "box", 0, 10, [0, 0], this_step)
    # psk_words = psk_words + step_words

    # wait timeout until the label file is ready.


    this_step, step_words = genStepCreateData("int", "gs_timeout", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("labels_ready != True and gs_timeout < 50", "", "", "waitGSLabels" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckExistence("direct", gs_zipped_label_file, "labels_ready", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_timeout\ngs_timeout = gs_timeout + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now, either the file is ready or time out.

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))

    ###############################################################################################
    # now that shipping labels generated, use unrar skill to unzip it.
    ##############################################################################################
    this_step, step_words = genStepCheckCondition("labels_ready", "", "", this_step)
    psk_words = psk_words + step_words

    hfname = "abc"
    dl_dir = get_default_download_dir()
    # input parameters [ rar exe path, zipped file fullpath, unziped_dir ]
    this_step, step_words = genStepCreateData("expr", "unzip_input", "NA", "['', '" + dl_dir + "', '" + hfname +"']", this_step)
    psk_words = psk_words + step_words

    # unzip the labels tar file, and update tracking code into
    this_step, step_words = genStepUseSkill("unzip_archive", "public/win_rar_local_unzip", "unzip_input", "label_dir", this_step)
    psk_words = psk_words + step_words

    # end of if label is ready.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # end of if there is enough fund.
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # increment n files processed counter....
    this_step, step_words = genStepCallExtern("n_files_processed = n_files_processed + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end of loop for processin all order xls files.
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now update the output file and exit skill

    # now that the labels are unzipped, extract tracking code from them and update the order list data structure

    this_step, step_words = genStepStub("end skill", "public/win_chrome_goodsupply_label/bulk_buy", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for buy shipping labels in bulk...." + psk_words)

    return this_step, psk_words



# ofname is the order file name, should be etsy_orders+Date.xls
def createLabelOrderFile(orders, ofname):
    orderTable = {"colNames": ("No", "FromName", "PhoneFrom", "Address1From", "CompanyFrom", "Address2From", "CityFrom", "StateFrom", "ZipCodeFrom", "NameTo", "PhoneTo", "Address1To",  "CompanyTo", "Address2To", "CityTo", "StateTo", "ZipTo",  "Weight", "length", "width", "height", "description"),
                  "rows": [
                      ("1", "Sam C", "9256222995", "2610 Laramie Gate Cir", "", "", "Pleasanton", "CA", "94566", "Annelise Salomon", "PhoneTo", "3628 Victoria Ln",  "", "", "CINCINNATI", "OH", "45208",  "5", "16", "12", "2", "")
                  ]}

    allorders = [{
        "No": "1",
        "FromName": "Sam C",
        "PhoneFrom": "9256222995",
        "Address1From": "2610 Laramie Gate Cir",
        "CompanyFrom": "",
        "Address2From": "",
        "CityFrom": "Pleasanton",
        "StateFrom": "CA",
        "ZipCodeFrom": "94566",
        "NameTo": "Annelise Salomon",
        "PhoneTo": "6930205545",
        "Address1To": "3628 Victoria Ln",
        "CompanyTo": "",
        "Address2To": "",
        "CityTo": "CINCINNATI",
        "StateTo": "OH",
        "ZipTo": "45208",
        "Weight": "5",
        "length": "16",
        "width": "12",
        "height": "2",
        "description": ""
    }]

    df = pd.DataFrame(allorders)

    # Save to .xls file
    # Create a new workbook and select the active worksheet
    wb = Workbook()
    ws = wb.active

    # Write data to worksheet
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)

    # Iterate through rows in column 2 (the 'age' column)
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = '@'  # text format

    # Save workbook
    wb.save(ofname)



def searchTrackingCodes(pdffiles):
    tcs = [searchTrackingCode(pdff) for pdff in pdffiles]

def searchTrackingCode(pdffile):
    reader = PdfReader(pdffile)

    # printing number of pages in pdf file
    # print(len(reader.pages))

    # getting a specific page from the pdf file
    page = reader.pages[0]

    # extracting text from page
    text = page.extract_text()

    # luckily, for good supply generated label, there is only 1 line of text in the pdf which is the tracking code.
    words = text.split()
    tc = ""
    tc = tc.join(words)
    print("tracking code:["+tc+"]")
    return tc