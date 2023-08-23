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

    this_step, step_words = genStepHeader("win_chrome_goodsupply_label/bulk_buy", "win", "1.0", "AIPPS LLC", "PUBWINFILEOP001", "File Open Dialog Handling for Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_chrome_goodsupply_label/bulk_buy", "", this_step)
    psk_words = psk_words + step_words

    # open the web page.
    this_step, step_words = genStepOpenApp("Run", True, "browser", ul_url, "", "", worksettings["cargs"], 2, this_step)
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

    this_step, step_words = genStepCallExtern("global gs_order_file_path\ngs_order_file_path = fin[0]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "labels_ready", "NA", "False", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_order_file_name\ngs_order_file_name = fin[1]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global gs_service\ngs_service = fin[2]", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "goodsupply_bulkbuy", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", "fund_left", "info text", "any", "available_fund", "foundFund", "goodsupply", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepCheckCondition("float(available_fund) >= float(fin[3])", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "export_template", "anchor text", "", [0, 0], "left", [2, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # type in the shipping service to be used.
    this_step, step_words = genStepTextInput("type", False, gs_service, 1, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # bring up the file open dialog
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "choose_file", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepUseSkill("win_file_all_op", "public", [gs_order_file_path, gs_order_file_name, "open"], "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "verify_data", "anchor text", "", [0, 0], "center", [0, 0], "box", 2, 0, this_step)
    psk_words = psk_words + step_words

    # readn screen again after verify data.
    this_step, step_words = genStepExtractInfo("", worksettings["root_path"], "screen_info", "goodsupply_bulkbuy", "top", theme, this_step, None)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearch("screen_info", "total", "anchor text", "any", "total_price", "found_total", "goodsupply", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepCheckCondition("float(total_price) == 0", "", "", this_step)
    psk_words = psk_words + step_words

    # go back a page.
    this_step, step_words = genStepKeyInput("", True, "browserback", "", 2, this_step)
    psk_words = psk_words + step_words
    print("Label Order File Error")


    this_step, step_words = genStepCallExtern("gen_label_status = 'Failed xls format'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # click on OPEN button to complete the drill
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "import", "anchor text", "", [0, 0], "center",
                                              [0, 0], "box", 0, 10, this_step)
    psk_words = psk_words + step_words

    # wait until the label file is ready.
    lcv = "gsLabel"+str(stepN)
    this_step, step_words = genStepLoop("labels_ready != True and "+lcv+" < 50", "", "", lcv, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckExistence(gs_zipped_label_file, "labels_ready", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global "+lcv+"\n"+lcv+" = "+lcv+"+1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now check whether file is ready

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("gen_label_status = 'Failed Lack Fund'", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("labels_ready", "", "", this_step)
    psk_words = psk_words + step_words

    # now that shipping labels generated, use unrar skill to unzip it.
    this_step, step_words = genStepUseSkill("win_rar_local_unzip", "public", [gs_zipped_label_file, gs_unzipped_dir], "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

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