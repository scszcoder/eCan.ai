from basicSkill import *
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# https://www.onlinebarcodereader.com/
# https://online-barcode-reader.inliteresearch.com/

# dashboard
url = "https://goodsupply.xyz/Dashboard/Report"

# usps
url = "https://goodsupply.xyz/Dashboard/Usps"

# address book
url = "https://goodsupply.xyz/Template/Index"

# bulk create
url = "https://goodsupply.xyz/Dashboard/UploadBulk"


def genWinCreateBulkLabels(lieutenant, bot_works, stepN, theme):
    psk_words = ""
    url = "https://www.etsy.com/your/orders/sold"
    this_step, step_words = genStepOpenApp("Run", True, "browser", url, "", "", lieutenant.skills[skidx].getAppArgs(), stepN)
    psk_words = psk_words + step_words

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))


def genWinGetLabelTrackingCodes(lieutenant, bot_works, stepN, theme):
    psk_words = ""
    url = "https://www.etsy.com/your/orders/sold"
    this_step, step_words = genStepOpenApp("Run", True, "browser", url, "", "", lieutenant.skills[skidx].getAppArgs(), stepN)
    psk_words = psk_words + step_words

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))

    this_step, step_words = genStepCreateData("bool", "foundMark", "NA", "False", stepN)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("bool", "startOfOrdersPage", "NA", "False", stepN)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCreateData("int", "nTrackingUpdated", "NA", 0, stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nTrackingUpdated >= 0", "", "", "allTrackCodeUpdated" + str(stepN), stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global startOfOrdersPage\nstartOfOrdersPage = False", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # (action, action_args, smount, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 75, "screen", "scroll_resolution", 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", root, "screen_info", "orders", "top", theme, this_step, pl)
    psk_words = psk_words + step_words


    # search "etsy, inc" and page list as indicators for the bottom of the order list page.
    this_step, step_words = genStepSearch("screen_info", ["complete_order"], ["anchor icon"], "any", "foundMark", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearch("screen_info", ["orders_per_page"], ["anchor text"], "any", "startOfOrdersPage", "useless", "etsy", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("foundMark == True", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "enter_tracking_number", "expr", "", "", "", "", "",this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "complete_order", "expr", "", "", "", "", "",this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "USPS", "expr", "", "", "", "", "",this_step)
    psk_words = psk_words + step_words



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