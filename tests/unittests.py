import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
import win32print
import win32api
import pytz
import socket
from io import BytesIO
import io
import httpx
import traceback

from bot.Cloud import send_account_info_request_to_cloud, send_query_chat_request_to_cloud, send_schedule_request_to_cloud, \
    req_cloud_obtain_review_w_aipkey, req_cloud_obtain_review, send_report_vehicles_to_cloud, send_dequeue_tasks_to_cloud, \
    send_update_missions_ex_status_to_cloud
from bot.lanAPI import req_lan_read_screen8
from bot.adsPowerSkill import readTxtProfile, removeUselessCookies, genProfileXlsx, convertTxtProfiles2XlsxProfiles, \
    processUpdateBotADSProfileFromSavedBatchTxt, formADSProfileBatches
from bot.amzBuyerSkill import processAMZScrapePLHtml
from bot.basicSkill import symTab, processSearchWordLine, process7z, convert_to_2d_array, genStepSearchWordLine, \
    get_top_visible_window, processExtractInfo, startSaveCSK, processUseExternalSkill, processReportExternalSkillRunStatus,\
    processDownloadFiles, processUploadFiles, processZipUnzip, processWaitUntil, processWaitUntil8, regSteps
from bot.printLabel import processPrintLabels, sync_win_print_labels1
from config.app_settings import ecb_data_homepath
from bot.ebbot import EBBOT
from bot.genSkills import genWinTestSkill, genWinTestSkill1, genWinTestSkill2
from bot.missions import EBMISSION
from bot.ordersData import ORDER, OrderPerson, OrderedProduct, Shipping
from bot.readSkill import prepRun1Skill, runAllSteps, prepRunSkill
from bot.scraperAmz import processAmzScrapeSoldOrdersHtml, amz_buyer_scrape_product_details
from bot.scraperEbay import ebaySellerGetSystemMsgThread, ebay_seller_fetch_page_of_order_list
from bot.scraperEtsy import processEtsyScrapeOrders
from bot.scrape1688 import *
from bot.seleniumScrapeAmzShop import processAmzSeleniumScrapeOrdersBuyLabels, processAmzSeleniumScrapeOrders, processAmzSeleniumConfirmShipments
# from my_skills.win_chrome_goodsupply_label.webdriver_buy_gs_labels import processMySeleniumBuyBulkGSLabels
from bot.seleniumScrapeAmz import processAmzSeleniumScrapeSearchResults
from bot.ragSkill import storeDocToVectorDB
from bot.wanChat import parseCommandString
from bot.labelSkill import handleExtLabelGenResults
from bot.seleniumSkill import *
# global symTab
import shutil
import pyautogui
import base64
import threading
import aiohttp

def test_eb_orders_scraper():
    orders = []
    html_file = "C:/temp/Orders — eBay Seller Hub.html"
    html_file = "C:/Users/songc/Downloads/Orders0eBaySellerHub.html"
    html_file = "C:/Users/songc/PycharmProjects/ecbot/runlogs/20240721/b89m789/win_ads_ebay_orders/skills/collect_orders/ebayOrders1721608436.html"
    ebay_seller_fetch_page_of_order_list(html_file, 0)
    html_file = "C:/Users/songc/PycharmProjects/ecbot/runlogs/20240722/b89m789/win_ads_ebay_orders/skills/collect_orders/ebayOrders1721682022.html"
    ebay_seller_fetch_page_of_order_list(html_file, 0)

    html_file = "C:/Users/songc/Downloads/MyeBay_ Messages00.html"
    # ebay_seller_get_customer_msg_list(html_file, 1)

    html_file = "C:/Users/songc/Downloads/MyeBay_ Messages18.html"
    # ebay_seller_get_customer_msg_thread(html_file)

    #html_file = "C:/Users/songc/Downloads/MyeBay_ Messages18.html"
    #ebay_seller_get_system_msg_thread(html_file)


def test_etsy_label_gen():
    # createLabelOrderFile(None, "C:/temp/etsy_orders20230730.xls")
    # searchTrackingCode("C:/Users/songc/Downloads/scszsj@gmail.com_SamC__0.pdf")
    # unCompressLabels("C:/Users/songc/Downloads/etsy_orders20230730_xls_122554.rar", "C:/temp/labels/")
    genWinUnRarSkill("", "", "", "")


# can use the following to tests any skill file, except the extractInfo one which requiers cloud service.
def test_use_func_instructions():
    psk0 = os.getenv('ECBOT_HOME') +"../testdata/ut0sk1.psk"
    test_settings = {"skfname": psk0}

    # a tests skill will be writen
    genWinTestSkill(test_settings, 0)

    print("done generating skill============================>")

    rpa_script = prepRun1Skill("UT000", psk0)

    print("done all address gen.................")

    # set mission to be None, skill to be None, since we won't be testing extractInfo step.
    # test_m = EBMISSION()
    runAllSteps(rpa_script, None, None)

    print("done testing.................")

# can use the following to tests any skill file, except the extractInfo one which requiers cloud service.
def test_multi_skills():

    psk1 = os.getenv('ECBOT_HOME') + "../testdata/ut1sk1.psk"
    psk2 = os.getenv('ECBOT_HOME') + "../testdata/ut1sk2.psk"
    test_settings = {"skfname": psk1}
    # a tests skill will be writen
    genWinTestSkill1(test_settings, 0)

    test_settings = {"skfname": psk2}
    # a tests skill will be writen
    genWinTestSkill2(test_settings, 0)

    print("done generating skill============================>")
    skodes = [{"ns": "UT1SK1", "skfile": psk1}, {"ns": "UT1SK2", "skfile": psk2}]
    rpa_script = prepRunSkill(skodes)

    print("done all address gen.................")

    # set mission to be None, skill to be None, since we won't be testing extractInfo step.

    # test_m = EBMISSION()
    runAllSteps(rpa_script, None, None)

    print("done testing.................")

def test_scrape_etsy_orders():
    # html_file = "c:/temp/EtsySoldOrders090423.html"
    html_file = "c:/temp/EtsySoldOrders090523.html"
    html_file = "c:/temp/EtsySoldOrdersDetails9523.html"
    html_file = "c:/temp/EtsySoldOrdersNoDetails9523.html"
    html_file = "c:/temp/EtsyMultiProductOrderNoDetails.html"
    # html_file = "c:/temp/EtsyMultiProductOrderWithDetails.html"
    # html_file = "c:/temp/EtsySamePersonMultiOrderNoDetails.html"
    # html_file = "c:/temp/EtsySamePersonMultiOrderWithDetails.html"
    # html_file = "c:/temp/EtsySoldOrdersPartialExpanded.html"


    # html_file = "c:/temp/Etsy -All Sold Orders P1.html"
    # html_file = "c:/temp/Etsy - All Sold Orders P3.html"

    step = {
            "type": "ETSY Scrape Orders",
            "pidx": 0,
            "html_file": html_file,
            "result": "orderListPage",
            "status": "scrapeStat"
    }
    next_step = processEtsyScrapeOrders(step, 10)

def test_scrape_etsy_orders():
    # html_file = "c:/temp/EtsySoldOrders090423.html"
    html_file = "c:/temp/EtsySoldOrders090523.html"
    html_file = "c:/temp/EtsySoldOrdersDetails9523.html"
    html_file = "c:/temp/EtsySoldOrdersNoDetails9523.html"
    html_file = "c:/temp/EtsyMultiProductOrderNoDetails.html"
    # html_file = "c:/temp/EtsyMultiProductOrderWithDetails.html"
    # html_file = "c:/temp/EtsySamePersonMultiOrderNoDetails.html"
    # html_file = "c:/temp/EtsySamePersonMultiOrderWithDetails.html"
    # html_file = "c:/temp/EtsySoldOrdersPartialExpanded.html"


    # html_file = "c:/temp/Etsy -All Sold Orders P1.html"
    # html_file = "c:/temp/Etsy - All Sold Orders P3.html"

    step = {
            "type": "ETSY Scrape Orders",
            "pidx": 0,
            "html_file": html_file,
            "result": "orderListPage",
            "status": "scrapeStat"
    }
    next_step = processEtsyScrapeOrders(step, 10)

def test_scrape_amz_prod_list():

    global test_html_file
    test_html_file = "C:/Users/songc/PycharmProjects/ecbot/runlogs/20240216/b15m323/win_chrome_amz_home/skills/browse_search/1708140221.html"
    # test_html_file = "C:/Users/songc/PycharmProjects/ecbot/runlogs/20240216/b15m322/win_chrome_amz_home/skills/browse_search/Amazon.com _ oil filter plier.html"
    global test_page_num
    test_page_num = 0

    step = {
        "type": "AMZ Scrape PL Html",
        "action": "Scrape PL",
        "html_var": "test_html_file",
        "product_list": "plSearchResult",
        "page_num": "test_page_num",
        "page_cfg": "",
    }

    # amission = EBMISSION(parent)
    # amission.setMid(30)    # MID
    # amission.setTicket(0)
    # amission.setOwner('songc@yahoo.com')
    # amission.setBid(2)
    # amission.setStatus('Assigned')
    # amission.setBD('2022-10-23 00:00:00')
    #
    # amission.setRetry("1")
    # amission.setCusPAS('win,chrome,amz')
    # amission.setSearchCat('')
    # amission.setSearchKW('yoga mats')
    # amission.setPseudoStore('')
    # amission.setPseudoBrand('')
    # amission.setPseudoASIN('')
    # amission.setMtype('Browse')
    # amission.setConfig('')
    # amission.setSkills('2, 3')
    # amission.setDelDate('3022-10-23 00:00:00')

    next_step = processAMZScrapePLHtml(step, 10, mission)
    # pl = amz_buyer_fetch_product_list(test_html_file, 0)
    # print("scrape product list result: ", pl)


def test_scrape_gs_labels():
    # html_file = "c:/temp/gsListLabels0000.html"
    # html_file = "c:/temp/gsListLabels000.html"
    html_file = "c:/temp/gsListLabels001.html"
    # html_file = "c:/temp/gsListLabels002.html"
    # html_file = "c:/temp/gsListLabels003.html"
    testorders = []

    new_order = ORDER("", "", "", "", "", "", "")
    recipient = OrderPerson("", "", "", "", "", "", "")
    recipient.setFullName("Alex Fischman")

    products = []
    product = OrderedProduct("", "", "", "")
    product.setPTitle("abc")
    products.append(product)

    shipping = Shipping("", "", "", "", "", "", "", "")
    new_order.setShipping(shipping)
    new_order.setProducts(products)
    new_order.setRecipient(recipient)
    testorders.append(new_order)

    new_order = ORDER("", "", "", "", "", "", "")
    recipient = OrderPerson("", "", "", "", "", "", "")
    recipient.setFullName("Melissa Clark")

    products = []
    product = OrderedProduct("", "", "", "")
    product.setPTitle("abc")
    products.append(product)

    shipping = Shipping("", "", "", "", "", "", "", "")
    new_order.setShipping(shipping)
    new_order.setProducts(products)
    new_order.setRecipient(recipient)
    testorders.append(new_order)

    symTab["testorders"] = testorders

    step = {
            "type": "GS Scrape Labels",
            "pidx": "pageidx",
            "html_file": html_file,
            "allOrders": "testorders",
            "result": "labelList",
            "status": "scrapeStat"
    }

    next_step = processScrapeGoodSupplyLabels(step, 10)


def test_processSearchWordline():
    # test_page0 = [{'name': 'paragraph', 'text': '5 6 7 8 9 10 \n', 'loc': (1870, 2938, 1892, 3254), 'type': 'info 1'}]
    test_page0 = [{'name': 'paragraph', 'text': '12345‘ \n', 'loc': (1869, 3426, 1914, 3747), 'type': 'info 1'}]
    symTab["test_page"] = test_page0
    symTab["tbs"] = "5"
    step = {
        "type": "Search Word Line",
        "screen": "test_page",
        "template_var": "tbs",
        "target_name": "paragraph",
        "target_type": "info 1",
        "site": "www.etsy.com",
        "result": "searchResult",
        "breakpoint": False,
        "status": "scrapeStat"
    }

    next_step = processSearchWordLine(step, 10)



def test_process7z():
    symTab["exe_link"] = 'C:/"Program Files"/7-Zip/7z.exe'
    symTab["in_file"] = "C:/Users/"+ os.environ.get("USERNAME") + "/Downloads/etsyOrdersPriority09122023.xls_0918221925.zip"
    symTab["opath"] = os.getenv('ECBOT_DATA_HOME') + "/runlogs/20230910/b3m3/win_chrome_etsy_orders/skills/fullfill_orders/etsyOrdersPriority09122023.xls_0918221925"
    symTab["ovar"] = 'nothing'
    step = {
        "type": "Seven Zip",
        "action": "unzip",
        "var_type": "expr",
        "exe_var": "exe_link",
        "in_var": "in_file",
        "out_path": "opath",
        "out_var": "ovar",
        "result": "scrapeStat"
    }

    next_step = process7z(step, 10)
    print("done unzipping tests....")


def test_rar():
    subprocess.Popen(["C:/Program Files/WinRAR/WinRAR.exe",  "C:/Users/"+os.environ.get("USERNAME")+"/Downloads/Downloads1.rar"])
    for i in range(10):
        print("waiting.......")
        time.sleep(2)

def test_get_tz():
    local_timezone = datetime.now(datetime.timezone.utc).astimezone().tzinfo
    print("time zone info:", local_timezone)
    for tz in pytz.all_timezones:
        print(tz)

    local_time = time.localtime()  # returns a `time.struct_time`
    tzname_local = local_time.tm_zone
    print("local time zone info:", local_timezone)

def test_basic():
    # order = "$340.049"
    # order_pattern = re.compile("\$[0-9]+\.[0-9]+")
    # matched = order_pattern.search(order)
    # if matched:
    #     print("price found!!!!")
    # else:
    #     print("price NOT FOUND!!!!")

    addr = "Coral Springs, FL "
    us_addr_pattern = re.compile(r"[a-zA-Z ]+, *[A-Z][A-Z] *$")  # Use raw string (r"") or double backslash
    ca_addr_pattern = re.compile(r"[a-zA-Z ]+, *Canada *$")  # Use raw string

    us_matched = us_addr_pattern.search(addr)
    ca_matched = ca_addr_pattern.search(addr)
    if us_matched or ca_matched:
        print("citystate found!!!!")
    else:
        print("citystate NOT FOUND!!!!")


def test_coordinates():
    # boxes = [
    #             [50, 60, 55, 65], [150, 60, 155, 65], [250, 60, 255, 65], [350, 60, 355, 65],
    #             [48, 121, 53, 126],                   [250, 121, 255, 126],
    #                               [151, 180, 156, 185],                   [350, 180, 355, 185],
    #                                                   [252, 238, 257, 243]
    #         ]
    boxes = [   [252, 238, 257, 243],  [151, 180, 156, 185],                   [350, 180, 355, 185],
                [50, 60, 55, 65], [150, 60, 155, 65], [250, 60, 255, 65], [350, 60, 355, 65],
                                [250, 121, 255, 126],  [48, 121, 53, 126]

            ]

    resulting_2d_array = convert_to_2d_array(boxes)
    for row in resulting_2d_array:
        print(row)


def test_get_account_info(host, session, token):
    qs = [{"actid": 5, "op":"", "options": ""}]

    result = send_account_info_request_to_cloud(session, qs, token, host.getWanApiEndpoint())

    print("RESULT:", result)

def test_api(parent, session, token):
    print("TESTING API....")
    # request = [{
    #     "id": 702,
    #     "bid": 85,
    #     "os": "win",
    #     "app": "ads",
    #     "domain": "local",
    #     "page": "ads_power",
    #     "layout": "",
    #     "skill_name": "batch_import",
    #     # "csk": "C:\\Users\\songc\\PycharmProjects\\ecbot/resource/skills/public/win_ads_local_load/batch_import.csk",
    #     "csk": "C:/Users/songc/PycharmProjects/ecbot/resource/skills/public/win_ads_local_load/batch_import.csk",
    #     "lastMove": "top",
    #     "options": "{\\\"anchors\\\": [{\\\"anchor_name\\\": \\\"bot_user\\\", \\\"anchor_type\\\": \\\"text\\\", \\\"template\\\": \\\"TeluguOttoYuGh\\\", \\\"ref_method\\\": \\\"0\\\", \\\"ref_location\\\": []}, {\\\"anchor_name\\\": \\\"bot_open\\\", \\\"anchor_type\\\": \\\"text\\\", \\\"template\\\": \\\"Open\\\", \\\"ref_method\\\": \\\"1\\\", \\\"ref_location\\\": [{\\\"ref\\\": \\\"bot_user\\\", \\\"side\\\": \\\"right\\\", \\\"dir\\\": \\\">\\\", \\\"offset\\\": \\\"1\\\", \\\"offset_unit\\\": \\\"box\\\"}]} ]}",
    #     "theme": "light",
    #     "imageFile": "C:\\\\Users\\\\songc\\\\PycharmProjects\\\\ecbot/runlogs/20240329/b85m702/win_ads_local_load/skills/batch_import/images/scrnsongc_yahoo_1711760595.png",
    #     # "imageFile": "C:/Users/songc/PycharmProjects/ecbot/runlogs/20240329/b85m702/win_ads_local_load/skills/batch_import/images/scrnsongc_yahoo_1711760595.png",
    #     "factor": "{}"
    # }]
    # # result = req_cloud_read_screen(session, request, token)
    # # print("result", request[0]["options"])
    # # print("result", result)
    #
    # allTodoReports = [{'mid': 702, 'bid': 85, 'starttime': 1712082891, 'endtime': 1712082891, 'status': 'Completed:0'},
    #  {'mid': 694, 'bid': 71, 'starttime': 1712082921, 'endtime': 1712082921, 'status': 'Completed:0'},
    #  {'mid': 698, 'bid': 77, 'starttime': 1712082951, 'endtime': 1712082951, 'status': 'Completed:0'}]
    # send_completion_status_to_cloud(session, allTodoReports, token, parent.getWanApiEndpoint())


    # // { "pass_method": "", "total_score": 0, "passing_score": 0, goals":[{"name": "xxx", "type": "xxx", "mandatory": true/false, "score": "", "standards": number/set of string, "weight": 1, passed": true/false}....]
    goals_json = {
        "pass_method": "all mandatory",
        "total_score": 0,
        "passed": False,
        "goals": [
            {
                "name": "test",
                "type": "echo",
                "mandatory": True,
                "score": 0,
                "standards": [],
                "weight": 1,
                "passed": False
            }
        ]
    }
    goals_string = json.dumps(goals_json).replace('"', '\\"')
    qs = [{"msgID": "1", "user": "john", "timeStamp": "2024-04-09T12:00:00.000Z", "products": "", "goals": goals_string, "background": "", "msg": "hi, do you sell fabric type?"}]
    result = send_query_chat_request_to_cloud(session, token, qs, parent.getWanApiEndpoint())
    print("send_query_chat_request_to_cloud RESULT:", result)



    # qs = [{"mid": 1, "bid": 1, "status":"Completed:0", "starttime": 123, "endtime": 123}]
    # result = send_completion_status_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_completion_status_to_cloud RESULT:", result)

    # tests passed - 2024-01-21
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_add_bots_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_add_bots_request_to_cloud RESULT:", result)
    #

    # tests passsed - 2024-01-23
    # abot = parent.bots[0]
    # abot.pubProfile.setPubBirthday("1992-03-01")
    # result = send_update_bots_request_to_cloud(session, [abot], token, parent.getWanApiEndpoint())
    # print("send_update_bots_request_to_cloud RESULT:", result)
    #
    # tests passed - 2024-01-21
    # qs = [{"id": 12, "owner": "", "reason": ""}]
    # result = send_remove_bots_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_remove_bots_request_to_cloud RESULT:", result)
    #
    # tests passed.
    # result = send_get_bots_request_to_cloud(session, token, parent.getWanApiEndpoint())
    # print("send_get_bots_request_to_cloud RESULT:", result)

    # tests passed
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "qphrase": "etsy male"}
    # result = send_query_bots_request_to_cloud(session, token, qs, parent.getWanApiEndpoint())
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    #
    # tests passed 202-01-24
    # amission = EBMISSION(parent)
    # amission.setMid(30)    # MID
    # amission.setTicket(0)
    # amission.setOwner('songc@yahoo.com')
    # amission.setBid(2)
    # amission.setStatus('')
    # amission.setBD('')
    #
    # amission.setRetry("1")
    # amission.setCusPAS('win,chrome,etsy')
    # amission.setSearchCat('')
    # amission.setSearchKW('yoga mats')
    # amission.setPseudoStore('')
    # amission.setPseudoBrand('')
    # amission.setPseudoASIN('')
    # amission.setMtype('Browse')
    # amission.setConfig('')
    # amission.setSkills('9, 3')
    # amission.setDelDate('3022-10-23 00:00:00')
    # result = send_add_missions_request_to_cloud(session, [amission], token, parent.getWanApiEndpoint())
    # print("send_add_missions_request_to_cloud RESULT:", result)
    #

    # tests passed 202-01-24
    # amission = EBMISSION(parent)
    # amission.setMid(30)    # MID
    # amission.setTicket(0)
    # amission.setOwner('songc@yahoo.com')
    # amission.setBid(2)
    # amission.setStatus('Assigned')
    # amission.setBD('2022-10-23 00:00:00')
    #
    # amission.setRetry("1")
    # amission.setCusPAS('win,chrome,amz')
    # amission.setSearchCat('')
    # amission.setSearchKW('yoga mats')
    # amission.setPseudoStore('')
    # amission.setPseudoBrand('')
    # amission.setPseudoASIN('')
    # amission.setMtype('Browse')
    # amission.setConfig('')
    # amission.setSkills('2, 3')
    # amission.setDelDate('3022-10-23 00:00:00')
    #
    # result = send_update_missions_request_to_cloud(session, [amission], token, parent.getWanApiEndpoint())
    # print("send_update_missions_request_to_cloud RESULT:", result)
    #
    # tests passed - 2024-01-21
    # qs = [{"id": 44, "owner": "", "reason": ""}]
    # result = send_remove_missions_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    #

    # tests passed
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "created_date_range": "2022-10-20 00:00:00,2022-10-25 00:00:00"}
    # result = send_query_missions_request_to_cloud(session, token, qs, parent.getWanApiEndpoint())
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    # tests passed.
    # ts_skill = WORKSKILL(parent, "test_skill")
    # qs = [ts_skill]
    # result = send_add_skills_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_add_skills_request_to_cloud RESULT:", result)
    # successfull result sample: {'statusCode': 200, 'body': [{'skid': 2, 'owner': 'songc@yahoo.com', 'createdOn': '2024-01-13', 'platform': 'win', 'app': 'chrome', 'site': 'amz', 'name': 'test_skill', 'path': '/resource/skills/public/', 'description': 'This skill does great automation.', 'runtime': 1, 'price_model': '', 'price': 0, 'privacy': 'PRV'}]}

    # tests passed.
    # ts_skill.setName("test_skill0")
    # ts_skill.setSkid(1)
    # result = send_update_skills_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_update_skills_request_to_cloud RESULT:", result)
    # sample successful result: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '906f94f0-d998-48aa-aca9-6faf60f1964e', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}

    # tests passed.
    # qs = [{"skid": 1, "owner": "", "reason": ""}]
    # result = send_remove_skills_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_remove_skills_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}

    # tests passed.
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "qphrase": "great automation"}
    # result = send_query_skills_request_to_cloud(session, token, qs, parent.getWanApiEndpoint())
    # print("send_remove_skills_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    # jresp = send_schedule_request_to_cloud(session, token, "", None)
    # print("send_schedule_request_to_cloud RESULT:", jresp)
    #
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = req_train_read_screen(session, qs, token, parent.getWanApiEndpoint())
    # print("req_train_read_screen RESULT:", result)
    #
    # tested many times by now
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = req_cloud_read_screen(session, qs, token)
    # print("req_cloud_read_screen RESULT:", result)
    #
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_account_info_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_account_info_request_to_cloud RESULT:", result)



    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_account_info_request_to_cloud(session, qs, token, parent.getWanApiEndpoint())
    # print("send_account_info_request_to_cloud RESULT:", result)


def fix_localDB(mw):
    print("fix local DB is no longer necessary")
    # fix local DB tables if their columns don't match the reference.
    # mw.bot_service.fix_local_table()
    # mission_table_cols = mw.mission_service.fix_local_table()

def test_sqlite3(mw):
    from sqlalchemy import Text, REAL
    mw.bot_service.describe_table()
    # mw.bot_service.add_column("createon", Text, "ebpw")
    # mw.bot_service.add_column("vehicle", Text, "createon")
    mw.mission_service.describe_table()
    mw.mission_service.find_all_missions()
    # mw.mission_service.add_column("follow_seller", Text, "store")
    # mw.mission_service.add_column("follow_price", REAL, "price")
    #mw.mission_service.describe_table()
    # sql = ''' INSERT INTO bots(botid, owner, levels, gender, birthday, interests, location, roles, status, delDate, name, pseudoname, nickname, addr, shipaddr, phone, email, epw, backemail, ebpw)
    #               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
    # data_tuple = (21, 'songc@yahoo.com', 'Amazon:Buyer:Green', 'Male', '1992-01-01', \
    #               'Any,Any,Any,Any,Any', 'miami|fl', 'Amazon:Buyer', '', '2524-01-22', \
    #               'joe', 'do', '', '', '', '', '', '', '', '')
    #
    # mw.dbCursor.execute(sql, data_tuple)
    #
    # # Check if the INSERT query was successful
    # if mw.dbCursor.rowcount == 1:
    #     print("Insertion successful.")
    # else:
    #     print("Insertion failed.")
    #
    # sql = ''' INSERT INTO bots(botid, owner, levels, gender, birthday, interests, location, roles, status, delDate, name, pseudoname, nickname, addr, shipaddr, phone, email, epw, backemail, ebpw)
    #               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
    # data_tuple = (22, 'songc@yahoo.com', 'Amazon:Buyer:Green', 'Female', '1992-01-01', \
    #               'Any,Any,Any,Any,Any', 'miami|fl', 'Amazon:Buyer', '', '2524-01-22', \
    #               'joe', 'do', '', '', '', '', '', '', '', '')
    #
    # mw.dbCursor.execute(sql, data_tuple)
    #
    # # Check if the INSERT query was successful
    # if mw.dbCursor.rowcount == 1:
    #     print("Insertion successful.")
    # else:
    #     print("Insertion failed.")
    #
    # mw.dbcon.commit()
    #
    # mw.dbCursor.execute("PRAGMA table_info(missions);")
    #
    # # Fetch all the rows (each row represents a column)
    # db_data = mw.dbCursor.fetchall()

    # print("DB Data:", db_data)


    # new_fb = 'backemail_site'
    # fb_type = 'TEXT'  # Change this to the desired data type
    # rt_col = 'ebpw'
    #
    # new_rrt = 'price'
    # rrt_type = 'REAL'  # Change this to the desired data type
    # est_col = 'feedbacks'

    # sql = f"ALTER TABLE bots ADD COLUMN {new_fb} {fb_type} AFTER {rt_col};"
    # sql = "ALTER TABLE missions DROP COLUMN COLUMNNAME"
    # mw.dbCursor.execute(sql)

    # new_rrt = 'variations'
    # rrt_type = 'TEXT'  # Change this to the desired data type
    # est_col = 'title'
    # sql = f"ALTER TABLE missions ADD COLUMN {new_rrt} {rrt_type} AFTER {est_col};"
    # # sql = "ALTER TABLE missions DROP COLUMN COLUMNNAME"
    # mw.dbCursor.execute(sql)
    #
    # # sql ="UPDATE bots SET email = 'kaiya34@gmail.com' WHERE botid = 15"
    # # mw.dbCursor.execute(sql)
    # # print("update bots")
    # mw.dbcon.commit()
    #
    # table_name = 'missions'
    # db_data = mw.dbCursor.fetchall()
    # print("DB Data:", db_data)
    # mw.dbCursor.execute(f"DROP TABLE {table_name};")
    # mw.dbcon.commit()
    #
    # mw.dbCursor.execute("PRAGMA table_info(missions);")

    # Fetch all the rows (each row represents a column)
    # db_data = mw.dbCursor.fetchall()
    # print("DB Data:", db_data)

    # sql = 'SELECT * FROM missions'
    # res = mw.dbCursor.execute(sql)

    # db_data = mw.dbCursor.fetchall()
    # print("DB Data:", db_data)

def test_read_buy_req_files(mw):
    mw.newBuyMissionFromFiles()


# tests passed SC - 02/20/2024
def test_ads_batch(parent):
    test_dir = "C:/AmazonSeller/SelfSwipe/test_ads_batch"
    # clean tests dir first.
    for filename in os.listdir(test_dir):
        # Construct the full file path
        file_path = os.path.join(test_dir, filename)
        # Delete the file
        os.remove(file_path)

    allbots = []
    # vTasks = {
    #     "eastern": [],
    #     "central": [],
    #     "mountain": [],
    #     "pacific": [],
    #     "alaska": [],
    #     "hawaii": [{ "bid" : 5, "bw_works" : [], "other_works" : [{ "start_time" : 3 }] }]
    # }

    # vTasks = {
    #     "eastern": [{ "bid" : 0, "bw_works" : [{ "start_time" : 12 }], "other_works" : [] }],
    #     "central": [],
    #     "mountain": [],
    #     "pacific": [],
    #     "alaska": [],
    #     "hawaii": [{ "bid" : 5, "bw_works" : [], "other_works" : [{ "start_time" : 3 }] }]
    # }
    #
    # vTasks = {
    #     "eastern": [{ "bid" : 0, "bw_works" : [{ "start_time" : 12 }], "other_works" : [] }],
    #     "central": [{ "bid" : 3, "bw_works" : [{ "start_time" : 4 }], "other_works" : [] }],
    #     "mountain": [{ "bid" : 6, "bw_works" : [{ "start_time" : 30 }], "other_works" : [] }],
    #     "pacific": [{ "bid" : 9, "bw_works" : [{ "start_time" : 0 }], "other_works" : [] }],
    #     "alaska": [{ "bid" : 12, "bw_works" : [{ "start_time" : 15 }], "other_works" : [] }],
    #     "hawaii": [{ "bid" : 5, "bw_works" : [], "other_works" : [{ "start_time" : 3 }] }]
    # }
    vTasks = {
        "eastern": [{ "bid" : 0, "bw_works" : [{ "start_time" : 12, "cuspas": "win,chrome,etsy" }], "other_works" : [] }],
        "central": [{ "bid" : 3, "bw_works" : [{ "start_time" : 4, "cuspas": "win,chrome,amz" }], "other_works" : [] }],
        "mountain": [{ "bid" : 6, "bw_works" : [{ "start_time" : 30, "cuspas": "win,chrome,amz" }], "other_works" : [{ "start_time" : 26, "cuspas": "win,chrome,amz" }] }],
        "pacific": [{ "bid" : 9, "bw_works" : [{ "start_time" : 0, "cuspas": "win,chrome,amz" }], "other_works" : [] }, { "bid" : 7, "bw_works" : [{ "start_time" : 21, "cuspas": "win,chrome,amz" }], "other_works" : [] }],
        "alaska": [{ "bid" : 12, "bw_works" : [{ "start_time" : 15, "cuspas": "win,chrome,etsy" }], "other_works" : [] }],
        "hawaii": [{ "bid" : 5, "bw_works" : [], "other_works" : [{ "start_time" : 3, "cuspas": "win,chrome,etsy" }] }]
    }

    fname = "C:/temp/adsProfilesTest0.json"
    fj = open(fname)
    pJsons = json.load(fj)
    fj.close()

    all_emails = pJsons["all_emails"]

    all_profiles_csv = "C:/AmazonSeller/SelfSwipe/test_all.xls"

    for i in range(42):
        new_bot = EBBOT()
        new_bot.setBid(i)
        new_bot.setEmail(all_emails[i])
        allbots.append(new_bot)

    all_ads_batches, batches_files = formADSProfileBatches(vTasks, allbots, all_profiles_csv, test_dir)
    print("all_ads_batches: ", all_ads_batches)
    print("batches_files: ", batches_files)

def test_misc():
    executable_path = shutil.which('AdsPower Global.exe')
    print("AdsPower:", executable_path)
    executable_path = shutil.which('chrome.exe')
    if executable_path:
        print("chrome:", executable_path)
    else:
        print("chrome not found")
    executable_path = shutil.which('git.exe')
    print("git:", executable_path)

    if os.path.exists('C:/Program Files/AdsPower Global/AdsPower Global.exe'):
        print("found ads power...")

def test_run_mission(main_vehicle):
    # run a skill here, to a skill, need to::
    # 1) set up a mission that will use this skill(we can use a default tests mission: self.trMission)
    # 2) need to set up a bot to run this mission (if we use self.trMission, it has a imaginary bot  with id 0 assigned to it already)
    # 3) set up today's work schedule to schedule in the mission
    # 4) then, call runbotworks() this will take care of the rest....
    trMission = EBMISSION(main_vehicle)
    trMission.setMid(98)
    trMission.setSkills("4")
    trMission.pubAttributes.setType("user", "Buy")
    trMission.pubAttributes.setBot(0)
    trMission.setCusPAS("win,ads,amz")
    trMission.setAppExe("C:/Program Files/AdsPower Global/AdsPower Global.exe")
    main_vehicle.missions.append(trMission)
    tbr_tasks = [{"name": "walk_routine",
                  "mid": 98,
                  "bid": 0,
                  "b_email": "jairgoldenvp89@gmail.com",
                  "full_site": "www.amazon.com",
                  "start_time": 40,
                  "cuspas": "win,ads,amz",
                  "tz": "eastern",
                  "batch_file": "C:/AmazonSeller/SelfSwipe/test_ads_batch/ads_profiles_amz_0.xls",   # profiles_dir + "/ads_profiles_" + one_site +"_"+str(bi)+".xls"
                  "config": {
                      "estRunTime": 2,
                      "searches": [
                          {
                              "type": "browse",
                              "site": "amz",
                              "os": "win",
                              "app": "ads",
                              "entry_paths": {
                                  "type": "Search",
                                  "words": [
                                      "electric scooter"
                                  ]
                              },
                              "top_menu_item": "Amazon Home",
                              "prodlist_pages": [
                                  {
                                      "flow_type": "down up down",
                                      "products": [
                                          {
                                              "selType": "op",
                                              "detailLvl": 0,
                                              "purchase": []
                                          },
                                          {
                                              "selType": "mr",
                                              "detailLvl": 0,
                                              "purchase": []
                                          }
                                      ]
                                  }
                              ],
                              "buy_cfg": None
                          }
                      ]},
                    }]
    main_vehicle.todays_work["tbd"].append(
        {"name": "automation", "works": tbr_tasks, "ip": "127.0.0.1", "status": "yet to start",
         "current widx": 0, "completed": [], "aborted": []})

    main_vehicle.runbotworks()


def test_processSearchWordLine():
    this_step, step_words = genStepSearchWordLine("screen_info", "bot_email", "expr", "any", "useless", "bot_loaded", "ads", False, 1)
    symTab["screen_info"] = [{"name": "paragraph",
                                "text": "uAdsPower Browser \\n",
                                "loc": [16, 32, 56, 531],
                                "type": "info",
                                "txt_struct": [{
                                  "num": 1,
                                  "text": "uAdsPower Browser ",
                                  "box": [32, 27, 323, 48],
                                  "words": [{
                                      "num": 0,
                                      "text": "uAdsPower",
                                      "box": [32, 16, 209, 56]
                                    },
                                    {"num": 1,
                                     "text": "Browser",
                                     "box": [220, 27, 323, 48]
                                     }]
                                }]
                            },
                            {"name": "paragraph",
                             "text": "| 4.9.20 \\n",
                             "loc": [27, 333, 48, 423],
                             "type": "info",
                             "txt_struct": [{"num": 2,
                                             "text": "| 4.9.20 ",
                                             "box": [333, 27, 423, 48],
                                             "words": [{"num": 2,
                                                        "text": "|",
                                                        "box": [333, 25, 336, 55]
                                                        },
                                                        {"num": 3,
                                                         "text": "4.9.20",
                                                         "box": [346, 27, 423, 48]
                                                         }]
                                             }]
                             },
                             {"name": "paragraph",
                              "text": "| 20.6.8.7 \\n",
                              "loc": [27, 435, 48, 531],
                              "type": "info",
                              "txt_struct": [{"num": 4,
                                              "text": "| 20.6.8.7 ",
                                              "box": [435, 27, 531, 48],
                                              "words": [{"num": 4,
                                                         "text": "|",
                                                         "box": [435, 25, 437, 55]
                                                         },
                                                        {"num": 5,
                                                         "text": "20.6.8.7",
                                                         "box": [449, 27, 531, 48]
                                                         }]
                                              }]
                              },
                             {"name": "paragraph",
                              "text": "Edit \\nWindow Help \\n",
                              "loc": [84, 34, 114, 389],
                              "type": "info",
                              "txt_struct": [{"num": 0,
                                              "text": "File ",
                                              "box": [34, 84, 75, 107],
                                              "words": [{"num": 6,
                                                         "text": "File",
                                                         "box": [34, 84, 75, 107]
                                                         }]
                                              },
                                             {"num": 1,
                                              "text": "Edit Window Help ",
                                              "box": [109, 84, 389, 114],
                                              "words": [{"num": 7,
                                                         "text": "Edit",
                                                         "box": [109, 84, 155, 107]
                                                         },
                                                        {"num": 8,
                                                         "text": "Window",
                                                         "box": [189, 84, 297, 107]
                                                         },
                                                        {"num": 9,
                                                         "text": "Help",
                                                         "box": [331, 84, 389, 114]
                                                         }]
                                              }]
                              }
                            ]

    symTab["test_pattern"] = r"2[0-9]\."  # Use raw string
    stepjson = {
        "type": "Search Word Line",
        "screen": "screen_info",
        "names": "test_pattern",
        "name_types": "expr pattern",
        "logic": "any",
        "result": "txt_on_screen",
        "site": "ads",
        "breakpoint": False,
        "status": "txt_on_screen"
    }

    processSearchWordLine(stepjson, 1)


def test_ads_profiling(username):
    fname = "C:/temp/adsProfilesTest0.json"
    fj = open(fname)
    pJsons = json.load(fj)
    fj.close()

    profile_json = readTxtProfile("C:/AmazonSeller/SelfSwipe/ADSProfiles/"+username+".txt")
    print("profile json is:", profile_json)
    print("# cookies:", len(profile_json[0]["cookie"]))
    print("============================================================")
    # removeUselessCookies(profile_json, ["amazon", "google", "gmail"])
    print("after filter, profile json is:", profile_json)

    print("# cookies:", len(profile_json[0]["cookie"]))
    print("============================================================")

    genProfileXlsx(profile_json, "C:/AmazonSeller/SelfSwipe/ADSProfiles/"+username+".xlsx", [username+"_"], pJsons["site_lists"])
    # genProfileXlsxs(pfJsons, fnames)


def test_batch_ads_profile_conversion(thisHost):
    fname = "C:/temp/adsProfilesTest0.json"
    fj = open(fname)
    pJsons = json.load(fj)
    fj.close()

    site_lists = pJsons["site_lists"]
    fnames =  pJsons["fnames"]

    convertTxtProfiles2XlsxProfiles(fnames, site_lists, thisHost)

def test_get_all_wins():
    get_top_visible_window()

def test_schedule_check():
    fname = "C:/temp/testSchedule.txt"
    # with open(fname, 'r') as file:
    #     for line in file:
    #         if '=' in line:
    # file.close()
    fj = open(fname)

    # returns JSON object as
    # a dictionary
    schJsons = json.load(fj)

    # schJsons = json.load(data)
    print("loaded Json:", len(schJsons))
    print("=================================")
    print(schJsons)
    fj.close()

    for schJson in schJsons:
        for tz in schJson.keys():
            print(tz, len(schJson[tz]))


def getProfileFileName(pf_dir, pf_email):
    return pf_dir+"/"+pf_email.split("@")[0]+"txt"

# tests run a schedule output from the cloud.
def test_run_group_of_tasks(commander):
    fname = "C:/temp/scheduleResultTest2.json"
    profiles_dir = "C:/AmazonSeller/SelfSwipe/ADSProfiles"
    fj = open(fname)

    # returns JSON object as
    # a dictionary
    schJsons = json.load(fj)

    fj.close()

    # from jsongs generate xlsx batches.
    batch_profiles = []                                # a list batch_profiles for ADS. and some will be send to corresponding vehicles.
    tgs = schJsons["task_groups"]

    commander.addNewlyAddedMissions(schJsons)
    # now that todays' newly added missions are in place, generate the cookie site list for the run.
    commander.build_cookie_site_lists()


    # on each machine
    commander.assignWork(tgs)


def test_UpdateBotADSProfileFromSavedBatchTxt():
    stepjson = {
        "type": "ADS Batch Text To Profiles",
        "batch_txt_dir": "C:/AmazonSeller/SelfSwipe/ADSProfiles",
        "n_files": 5,
        "output": "useless"
    }
    processUpdateBotADSProfileFromSavedBatchTxt(stepjson, 1)


def test_pyautogui():
    startx = 500
    starty = 300
    for i in range(30):
        pyautogui.moveTo(startx, starty)
        pyautogui.click()
        pyautogui.write("abc")
        time.sleep(3)
        startx = startx + 250
        starty = starty + 5
        pyautogui.moveTo(startx, starty)
        time.sleep(3)
        startx = startx + 3
        starty = starty + 250
        pyautogui.moveTo(startx, starty)
        time.sleep(3)
        startx = startx - 200
        starty = starty + 2
        pyautogui.moveTo(startx, starty)
        time.sleep(3)
        startx = startx + 2
        starty = starty - 200

# main  generate schedule
def run_genSchedules_test_case(host, session, token, tcn):
    tcdir = ecb_data_homepath + "/testcases/tc"+str(tcn)+"/"
    bots_json_file = tcdir+"newbots.json"
    if os.path.exists(bots_json_file):
        with open(bots_json_file, 'r') as bots_f:
            botsJson = json.load(bots_f)

        bots_f.close()

    missions_json_file = tcdir+"newmissions.json"
    if os.path.exists(missions_json_file):
        with open(missions_json_file, 'r') as missions_f:
            missionsJson = json.load(missions_f)

        missions_f.close()

    skills_json_file = tcdir+"newskills.json"
    if os.path.exists(skills_json_file):
        with open(skills_json_file, 'r') as skills_f:
            skillsJson = json.load(skills_f)

        skills_f.close()


    expected_json_file = tcdir+"expected.json"
    if os.path.exists(expected_json_file):
        with open(expected_json_file, 'r') as expected_f:
            expectedJson = json.load(expected_f)

        expected_f.close()

    schedule_test_settings = {
        "testmode_cloud": True,
        "test_stub": {
            "testmode": True,
            "allbots": botsJson,
            "allmissions": missionsJson,
            "allskills": skillsJson,
            "test_genActionItems": True,
            "test_getNextAvailableDate": True
        }
    }

    jresp = send_schedule_request_to_cloud(session, token, "tests", schedule_test_settings, host.getWanApiEndpoint())
    if "errorType" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
    else:
        # very important to use compress and decompress on Base64
        uncompressed = host.zipper.decompressFromBase64(jresp["body"])
        # uncompressed = jresp["body"]
        print("decomppressed response:", uncompressed, "!")
        if uncompressed != "":
            # print("body string:", uncompressed, "!", len(uncompressed), "::")
            rcvd_schedule = json.loads(uncompressed)

    result = check_expected_schedule(rcvd_schedule, expectedJson)

    if result["passed"]:
        print("Test case PASSED.")
    else:
        print("Test case FAILED.", result["cases"])



def check_expected_schedule(rcvd, expected):
    failed = False
    failed_mids = []
    # cross check task_groups with add_missions.

    # check task_groups against expected.
    # basically check bid, mid, timezone, starttime runtime
    for tz in rcvd["task_groups"]:
        if len(rcvd["task_groups"][tz]) > 0:
            for botwork in rcvd["task_groups"][tz]:
                if len(botwork["bw_works"]):
                    for bw in botwork["bw_works"]:
                        found = [sch for sch in expected if sch["bid"] == botwork["bid"] and sch["mid"] == bw["mid"] and sch["start_time"] == bw["start_time"] and sch["tz"] == tz]
                        if len(found)==0:
                            failed_mids.append(bw["mid"])


                if len(botwork["other_works"]):
                    for bw in botwork["other_works"]:
                        found = [sch for sch in expected if sch["bid"] == botwork["bid"] and sch["mid"] == bw["mid"] and sch["start_time"] == bw["start_time"] and sch["tz"] == tz]
                        if len(found)==0:
                            failed_mids.append(bw["mid"])

    if len(failed_mids) > 0:
        failed = True

    return {"passed": not failed, "cases": failed_mids}



async def test_send_file(xport):
    # tests sending 2 files across the network to a platoon. 1 json, 1 img
    file0 = "C:/Users/songc/PycharmProjects/ecbot/resource/skills/public/win_ads_amz_home/browse_search/scripts/amz_walk.psk"
    file0 = "C:/temp/top1500.png"
    with open(file0, 'rb') as fileTBSent:
        binary_data = fileTBSent.read()
        encoded_data = base64.b64encode(binary_data).decode('utf-8')
        print("sending file:", file0)
        # Embed in JSON
        json_data = json.dumps({"cmd": "reqSendFile", "file_name": file0, "file_contents": encoded_data})
        message = (json_data+"!ENDMSG!").encode('utf-8')
        length_prefix = len(message).to_bytes(4, byteorder='big')  # 4-byte length prefix
        # Send data
        xport.write(length_prefix + message)
        # await xport.drain()

        fileTBSent.close()

    #
    # file0 = "C:/Users/songc/PycharmProjects/ecbot/resource/skills/public/win_ads_amz_home/browse_search/images/trash1.png"
    #
    # with open(file0, 'rb') as fileTBSent:
    #     binary_data = fileTBSent.read()
    #     encoded_data = base64.b64encode(binary_data).decode('utf-8')
    #
    #     # Embed in JSON
    #     json_data = json.dumps({"cmd": "reqSendFile", "file_name": file0, "file_contents": encoded_data})
    #
    #     # Send data
    #     xport.write(json_data.encode('utf-8'))
    #     await xport.drain()
    #
    #     fileTBSent.close()



def test_scrape_amz_buy_orders():
    # html_file = "C:/temp/amz_buy_orders_files.html"
    # step = {
    #     "type": "AMZ Scrape Buy Orders Html",
    #     "pidx": "pidx",
    #     "html_dir": "C:/temp",
    #     "html_dir_type": "direct",
    #     "html_file": "amz_buy_orders2.html",
    #     "result": "scrape_result",
    #     "status": "scrape_stat"
    # }

    # next_step = processAmzScrapeBuyOrdersHtml(step, 10)

    step = {
        "type": "AMZ Scrape Buy Orders Html",
        "pidx": "pidx",
        "html_dir": "C:/temp",
        "html_dir_type": "direct",
        "html_file": "amz_seller_orders0.html",
        "result": "scrape_result",
        "status": "scrape_stat"
    }

    next_step = processAmzScrapeSoldOrdersHtml(step, 10)


def test_scrape_amz_product_details():
    html_file = "C:/temp/testAmzPd1.html"
    # html_file = "C:/temp/testAmzPd5.html"
    # html_file = "C:/temp/testAmzPd.html"
    pds = amz_buyer_scrape_product_details(html_file)



def test_detect_swatch():
    mission = None
    skill = None
    settings = {}
    dyn_options = "{'anchors': [{'anchor_name': 'this_var', 'anchor_type': 'text', 'template': 'Size', 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'next_var', 'anchor_type': 'text', 'template': 'BOS', 'ref_method': '0', 'ref_location': []}, {'anchor_name': 'swatch', 'anchor_type': 'polygon', 'template': '', 'ref_method': '1', 'ref_location': [{'ref': 'this_var', 'side': 'bottom', 'dir': '>', 'offset': '0', 'offset_unit': 'box'}]}, {'ref': 'this_var', 'side': 'right', 'dir': '>', 'offset': '-1', 'offset_unit': 'box'}]}, {'ref': 'next_var', 'side': 'top', 'dir': '<', 'offset': '0', 'offset_unit': 'box'}]}, {'ref': 'quantity', 'side': 'left', 'dir': '>', 'offset': '0', 'offset_unit': 'box'}]}], 'attention_area':[0.35, 0, 0.85, 1], 'attention_targets':['@all']}"

    step =  {
        "type": "Extract Info",
        "settings": settings,
        "template": "",
        "options": dyn_options,
        "data_sink": "screen_info",
        "page": "product_details",
        "page_data_info": None,
        "theme": "",
        "section": "top"
    }
    ni, status = processExtractInfo(step, 1, mission, skill)

async def test_printer_print():
    symTab["labels_dir"] = "C:/temp/label_print_test/"
    symTab["default_printer"] = ""
    symTab["ecsite"] = "ebay"

    step = {
        "type": "Print Labels",
        "action": "Print Labels",
        "labels_dir": "labels_dir",
        "printer": "default_printer",
        "ecsite": "ecsite",
        "print_status": "print_stat"
    }

    ni, status = await processPrintLabels(step, 1)


def test_printer_print_sync():
    font_full_path = "C:/Users/songc/PycharmProjects/ecbot/resource/fonts/Noto_Serif_SC/static/NotoSerifSC-Medium.ttf"
    order_data = []
    product_book = []
    stat = sync_win_print_labels1("C:/temp/label_print_test/", "", "ebay", order_data, product_book, font_full_path, 28)
    # win32print.SetDefaultPrinter("EPSON481B68 (ET-3750 Series)")
    # win32api.ShellExecute(0, "print", "C:/temp/label_print_test/ebay_george_pele_p1_v1_1_p2_v2_1.pdf", None, ".", 0)


def test_save_csk(endpoint, session, token):
    csk_dir = "C:/Users/songc/PycharmProjects/ecbot/my_skills/win_chrome_goodsupply_label/bulk_buy"
    threading.Thread(target=startSaveCSK, args=(endpoint, csk_dir, session, token), daemon=True).start()

def test_ebay(session, token):
    print("test ebay")

def test_1688():
    print("testing 1688")
    # Perform search and extract results
    product_list = search_and_extract_results(search_phrase)

    # Close the driver
    # stopDriver()

    # Print results in JSON format
    print(json.dumps(product_list, ensure_ascii=False, indent=4))

def test_selenium_amazon_shop():
    processAmzSeleniumScrapeOrdersBuyLabels()
    # processAmzSeleniumScrapeOrders()
    # processAmzSeleniumConfirmShipments()

def test_selenium_GS():
    #
    # "UPS 2nd Day Air"
    # "UPS Next Day Air Early"
    # "UPS Next Day Air"
    # "UPS Standard"
    # "UPS Expedited"
    # "UPS Express"
    # "UPS Express Early "
    # "USPS Ground Advantage (1-15oz)"
    # "UPS Express Saver"
    # "USPS Priority V4"
    # "USPS Express v4"
    # "USPS Priority Signature v4"
    # "USPS Express Signature v4"
    # "USPS Ground Advantage Signature (1-15oz)"
    # "Ups Next Day Air Saver"
    # "USPS Ground Advantage (1-70lb)"
    # "USPS Ground Advantage Signature (1-70lb)"
    # "UPS Next Day Air Early Saturday"
    # "UPS Next Day Air Saturday"
    # "UPS 2nd Day Air Saturday"
    #
    gs_request = {
        "bulk request form": "C:/temp/etsyOrdersGroundTest916.xlsx",
        "shipping service": "USPS Ground Advantage (1-15oz)",
        "orders": [
            {

            }
        ]
    }
    # processMySeleniumBuyBulkGSLabels(gs_request)


def test_selenium_amazon():
    print("running test selenium amazon")
    processAmzSeleniumScrapeSearchResults()

in_data_string = ""
# request myself to run a skill
def test_request_skill_run(mission):
    # mission = None
    # settings = mission.main_win_settings
    global symTab
    orders1 = [
        {
            "No": "123",
            "FromName": "john smith",
            "PhoneFrom": "123-456-7890",
            "Address1From": "1 A St",
            "Address2From": "Apt B",
            "CityFrom": "San Jose",
            "StateFrom": "CA",
            "ZipCodeFrom": "95123",
            "NameTo": "Joe Toe",
            "PhoneTo": "133-334-5566",
            "Address1To": "3 C St",
            "Address2To": "",
            "CityTo": "Chicago",
            "StateTo": "IL",
            "ZipTo": "23466",
            "Weight": 3,
            "length": 4,
            "width": 2,
            "height": 1,
            "description": ""
        },
        {
            "No": "234",
            "FromName": "john smith",
            "PhoneFrom": "123-456-7890",
            "Address1From": "1 A St",
            "Address2From": "Apt B",
            "CityFrom": "San Jose",
            "StateFrom": "CA",
            "ZipCodeFrom": "95123",
            "NameTo": "Jack Doe",
            "PhoneTo": "122-334-5566",
            "Address1To": "2 B St",
            "Address2To": "",
            "CityTo": "Chicago",
            "StateTo": "IL",
            "ZipTo": "23456",
            "Weight": 8,
            "length": 6,
            "width": 6,
            "height": 6,
            "description": ""
        }
    ]

    orders2 = [
        {
            "No": "345",
            "FromName": "john smith",
            "PhoneFrom": "123-456-7890",
            "Address1From": "1 A St",
            "Address2From": "Apt B",
            "CityFrom": "San Jose",
            "StateFrom": "CA",
            "ZipCodeFrom": "95123",
            "NameTo": "Tim Kay",
            "PhoneTo": "222-333-5566",
            "Address1To": "5 K St",
            "Address2To": "",
            "CityTo": "New York",
            "StateTo": "NY",
            "ZipTo": "12345",
            "Weight": 18,
            "length": 6,
            "width": 6,
            "height": 6,
            "description": ""
        }
    ]

    file_path="my_skills"
    ec_platform="ebay"
    dt_string="2024-08-29T00:00:00:000Z"
    ofname1 = file_path + "/" + ec_platform + "OrdersGround" + dt_string + ".xlsx"
    ofname1_unzipped = file_path + "/" + ec_platform + "OrdersGround" + dt_string

    ofname2 = file_path + "/" + ec_platform + "OrdersPriority" + dt_string + ".xlsx"
    ofname2_unzipped = file_path + "/" + ec_platform + "OrdersPriority" + dt_string

    in_data = [
        {
            "service": "USPS Ground Advantage (1-15oz)",
            "price": 2 * 2.25,
            "num_orders": 2,
            "dir": os.path.dirname(ofname1),
            "file": os.path.basename(ofname1),
            "unzipped_dir": ofname1_unzipped,
            "order_data": orders1,
            "succeed": True,
            "result": ""
        },
        {
            "service": "USPS Priority V4",
             "price": 1* 3,
             "num_orders": 1,
             "dir": os.path.dirname(ofname2),
             "file": os.path.basename(ofname2),
             "unzipped_dir": ofname2_unzipped,
             "order_data": orders2,
             "succeed": True,
             "result": ""
        }
    ]

    symTab["in_data_string"] = json.dumps(in_data).replace('"', '\\"')
    # symTab["in_data_string"] = "{}"

    current_time = datetime.now(timezone.utc)

    # Convert to AWSDATETIME string format
    start_time = current_time.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    step = {
        "type": "Use External Skill",
        "skid": 87,
        "requester_mid": 1000,
        "skname": "browser_gen_ecb_labels",
        "owner": "songc@yahoo.com",
        "in_data": "in_data_string",
        "start_time": start_time,
        "verbose": 'false',
        "output": "run_result"
    }
    processUseExternalSkill(step, 1, mission)


def test_report_skill_run_result(mission):
    global symTab
    results = {
        "labels_download_link": "https://1.2.3.4/"
    }
    symTab["results_string"] = json.dumps(results).replace('"', '\\"').replace('/', '\\/')
    step = {
        "type": "Report External Skill Run Status",
        "run_id": 123,
        "skid": 87,
        "runner_mid": 10000,
        "runner_bid": 13,
        "start_time": "2024-08-29T00:00:00.000Z",
        "end_time": "2024-08-29T00:00:01.123Z",
        "status": "Completed",
        "result_data": "results_string",
        "output": "run_result"
    }
    processReportExternalSkillRunStatus(step, 1, mission)


def test_request_rag_store(mission):
    global symTab
    settings = mission.main_win_settings
    reqs = [
        {
            "fid": 0,
            "pid": 12,
            "file": "abc",
            "type": "product:user manual",
            "format": "txt",
            "options": "{}",
            "version": "0.0"
        }
    ]
    storeDocToVectorDB(settings["session"], settings["token"], reqs)


def test_parse_xml():
    test_vec = ":<cmd>list<bots>all</bots></cmd>"
    test_vec = ":<cmd>list<missions>1,2,3</missions></cmd>"
    test_vec = ":<cmd>cancel<missions>1</missions></cmd>"
    test_vec = ":<cmd>show<logs>all</logs></cmd>"

    parseCommandString(test_vec)

# Note: upload/download file direction must follow this structure:
# always starts with runlogs/...
# then user/date/b*m*/skillpath/skills/.....
def test_presigned_updownload(mission):
    global symTab
    settings = mission.main_win_settings
    symTab["infile"] = "runlogs/songc_yahoo/20240817/b88m697/win_ads_ebay_orders/skills/images/scrnsongc_yahoo_1723916188.png"

    step = {
            "type": "Download File",
            "file_var": "infile",
            "ftype": "skill input",
            "presigned": "presigned"
    }
    processDownloadFile(step, 1, mission)

def test_pyzipunzip():
    global symTab
    symTab["infile"] = "runlogs/songc_yahoo/20240817/b88m697/win_ads_ebay_orders/skills/images/scrnsongc_yahoo_1723916188.png"
    print("about to test zip unzip")
    step = {
        "type": "Zip Unzip",
        "action": "zip",
        "var_type": "direct",
        "in_var": ["c:/software", "c:/shared/as_server.txt"],
        "out_path": "c:/temp",
        "out_var": "test123.zip",
        "result": "zip_result"
    }

    step = {
        "type": "Zip Unzip",
        "action": "unzip",
        "var_type": "direct",
        "in_var": "c:/temp/test123.zip",
        "out_path": "c:/temp/testzip",
        "out_var": "",
        "result": "zip_result"
    }

    processZipUnzip(step, 1)


def test_handle_extern_skill_run_report(endpoint, session, token):
    in_message = {"contents": "[{\"service\":\"USPS Ground Advantage (1-15oz)\",\"price\":6.75,\"num_orders\":3,\"dir\":\"C:\\Users\\songc\\PycharmProjects\\ecbot/songc_yahoo_com/runlogs/songc_yahoo/20240824/b88m697/win_ads_ebay_orders/skills/browser_fullfill_orders_with_ecb_labels/ecb_labels\",\"file\":\"runlogs/songc_yahoo/20240824/b88m697/win_ads_ebay_orders/skills/browser_fullfill_orders_with_ecb_labels/ecb_labels/ebayOrdersGround20240824183259.xlsx\",\"zip_file\":\"ebayOrdersGround20240824183259.zip\",\"zip_dir\":\"C:/Users/songc/PycharmProjects/ecbot/songc_yahoo_com/runlogs/songc_yahoo_com/20240824/b88m697/win_ads_ebay_orders/skills/browser_fullfill_orders_with_ecb_labels/ecb_labels\",\"order_data\":[{\\\"name\":\"Shaker Sediqi\",\"order_ids\":[\"04-11983-43763\"],\"tracking\":\"92346853310287736074040659\"},{\"name\":\"ramez boos\",\"order_ids\":[\"07-11979-59634\"],\"tracking\":\"92346143461007104750277876\"},{\"name\":\"Nicholas bumgardner\",\"order_ids\":[\"20-11961-97395\"],\"tracking\":\"92346407433757614105836042\"}],\"succeed\":false,\"result\":\"Completed\"}]"}
    ext_run_results = json.loads(in_message['contents'])
    handleExtLabelGenResults(endpoint, session, token, ext_run_results)



async def test_wait_until8():
    step = {
        "type": "Wait Until",
        "events": ["labels_ready"],
        "events_relation": "all",
        "time_out": 20,
        "result": "wait_result",
        "flag": "wait_flag",
    }
    symTab['labels_ready'] = False
    await processWaitUntil8(step, 1)


def setupExtSkillRunReportResultsTestData(mainwin):
    symTab['product_book'] = mainwin.getSellerProductCatelog()
    order_list = []
    # ====================================1===================================
    new_order = ORDER("", "", "", "", "", "", "")
    new_order.setOid("04-11983-43763")
    shipping = Shipping("USPS", "USPS Ground Advantage (1-15oz)", "", "", "", "", "", "")
    new_order.setShipping(shipping)
    products = []
    product = OrderedProduct("", "", "", "")
    product.setPid("364254906909")
    product.setQuantity(1)
    products.append(product)
    new_order.setProducts(products)
    # product.addVariation((var_name, var_val))
    order_list.append(new_order)
    # ====================================2===================================
    new_order = ORDER("", "", "", "", "", "", "")
    new_order.setOid("07-11979-59634")
    shipping = Shipping("USPS", "USPS Ground Advantage (1-15oz)", "", "", "", "", "", "")
    new_order.setShipping(shipping)
    products = []
    product = OrderedProduct("", "", "", "")
    product.setPid("364195853481")
    product.setQuantity(3)
    product.addVariation(("Model", "iPhone12 Pro Max"))
    products.append(product)
    new_order.setProducts(products)

    order_list.append(new_order)
    # ====================================3===================================
    new_order = ORDER("", "", "", "", "", "", "")
    new_order.setOid("20-11961-97395")
    shipping = Shipping("USPS", "USPS Ground Advantage (1-15oz)", "", "", "", "", "", "")
    new_order.setShipping(shipping)
    products = []
    product = OrderedProduct("", "", "", "")
    product.setPid("363931490608")
    product.setQuantity(1)
    product.addVariation(("Compatible Model", "For Apple iPhone 12 mini"))
    products.append(product)

    product = OrderedProduct("", "", "", "")
    product.setPid("363820170833")
    product.setQuantity(1)
    product.addVariation(("Color", "Yellow"))
    product.addVariation(("Length", "15ft"))
    products.append(product)

    new_order.setProducts(products)
    print("3rd order:", len(new_order.getProducts()))
    # product.addVariation((var_name, var_val))
    order_list.append(new_order)

    order_list.append(new_order)
    symTab['ebay_orders'] = [{
        "ol": order_list
    }]


def testCloudAccessWithAPIKey(session, token, mainwin):
    apikey = os.getenv('SC_ECB_TEST_API_KEY0')
    print("apikey:", apikey)
    req = [
        {
            "product":  "coffee mug",
            "instructions": json.dumps({"features": "", "occasion":""}).replace('"', '\\"')
        }
    ]

    # req_cloud_obtain_review(session, req, token)



    req_cloud_obtain_review_w_aipkey(session, req, apikey, mainwin.getWanImageEndpoint())



def testReportVehicles(mwinwin):
    vehicle_report = mwinwin.prepVehicleReportData()
    resp = send_report_vehicles_to_cloud(mwinwin.session, mwinwin.tokens['AuthenticationResult']['IdToken'], vehicle_report)


def testDequeue(mwinwin):
    vehicle_report = mwinwin.prepVehicleReportData()
    resp = send_dequeue_tasks_to_cloud(mwinwin.session, mwinwin.tokens['AuthenticationResult']['IdToken'], vehicle_report, mwinwin.getWanApiEndpoint())

def testUpdateMissionsExStatus(mwin):
    print("entering test....")
    mstats = [{
        "mid": 11098,
        "status": "started"
    }]
    resp = send_update_missions_ex_status_to_cloud(mwin.session, mstats, mwin.tokens['AuthenticationResult']['IdToken'], mwin.getWanApiEndpoint())
    print("test done!!!")


def testRegSteps(mwin):
    print("entering test....")
    resp = regSteps("Web Driver Wait Until Clickable", "", "2024-10-02 12:46:00.000", True, mwin)
    print("test done!!!")

def testWebdriverADSAndChromeConnection(mwin, browser_setup_file):
    print("test selenium connection to ADS power")

    if os.path.exists(browser_setup_file):
        with open(browser_setup_file, 'rb') as f:
            testSetup = json.load(f)
            # self.rebuildHTML()
            f.close()
    else:
        testSetup = {
            "chrome_driver_path": "C:/Users/sctis/PycharmProjects/ecbot/chromedriver-win32/v92.0.4515.107/chromedriver.exe",
            "ads_api_key": "59fe1c634e8f3e8e3737eda0ae065ecd",
            "ads_port": "50325",
            "ads_profile_id": "9aqgv6fxxld",
            "ads_options": "",
            "chrome_debug_port": "9226"
        }

    global symTab

    # run a few steps to connect to the already opend ads power.
    # just drive it to open a known profile and open a new tab.
    # that should be enough to prove the communication is set up right.
    # same with a chrome

    symTab["driver_path_var"] = testSetup["ads_chrome_driver_path"]
    symTab["debug_port"] = testSetup["chrome_debug_port"]

    symTab["port_var"] = testSetup["ads_port"]
    symTab["ads_api_key_var"] = testSetup["ads_api_key"]
    symTab["profile_id_var"] = testSetup["ads_profile_id"]
    symTab["options_var"] = testSetup["ads_options"]


    symTab["web_driver"] = None

    symTab["result_var"] = False
    symTab["flag_var"] = False


    # test_step = {
    #     "type": "Web Driver Start Existing ADS",
    #     "driver_var": "web_driver",  # anchor, info, text
    #     "ads_api_key_var": "ads_api_key_var",
    #     "profile_id_var": "profile_id_var",
    #     "port_var": "port_var",
    #     "driver_path_var": "driver_path_var",
    #     "options_var": "options_var",
    #     "flag_var": "flag_var"
    # }
    # nexti, xstat = processWebdriverStartExistingADS(test_step, 1)
    #
    # symTab["url_var"] = "https://www.amazon.com"
    # test_step = {
    #     "type": "Web Driver New Tab",
    #     "driver_var": "web_driver",  # anchor, info, text
    #     "url_var": "url_var",  # anchor, info, text
    #     "result": "result_var",
    #     "flag": "flag_var"
    # }
    # nexti, xstat = processWebdriverNewTab(test_step, 1)


    # symTab["driver_path_var"] = testSetup["chrome_driver_path"]
    #
    # test_step = {
    #     "type": "Web Driver Start Existing Chrome",
    #     "driver_path": "driver_path_var",
    #     "debug_port": "debug_port",
    #     "result": "web_driver",
    #     "flag": "flag_var"
    # }
    # nexti, xstat = processWebdriverStartExistingChrome(test_step, 1)
    #
    # symTab["url_var"] = "https://www.amazon.com"
    # test_step = {
    #     "type": "Web Driver New Tab",
    #     "driver_var": "web_driver",  # anchor, info, text
    #     "url_var": "url_var",  # anchor, info, text
    #     "result": "result_var",
    #     "flag": "flag_var"
    # }
    # nexti, xstat = processWebdriverNewTab(test_step, 1)


    symTab["driver_path_var"] = testSetup["chrome_driver_path"]
    test_step = {
        "type": "Web Driver Start New Chrome",
        "driver_path": "driver_path_var",
        "port": "debug_port",
        "result": "web_driver",
        "flag": "flag_var"
    }
    nexti, xstat = processWebdriverStartNewChrome(test_step, 1)

    symTab["url_var"] = "https://www.amazon.com"
    test_step = {
        "type": "Web Driver New Tab",
        "driver_var": "web_driver",  # anchor, info, text
        "url_var": "url_var",  # anchor, info, text
        "result": "result_var",
        "flag": "flag_var"
    }
    nexti, xstat = processWebdriverNewTab(test_step, 1)


# this doesn't work somehow, API2 works.
async def testLocalImageAPI(parent):
    print("TESTING LOCAL IMG API....")

    # Ensure ECB_HOME is set
    ecb_home = os.getenv("ECB_HOME")
    if not ecb_home:
        raise ValueError("Environment variable ECB_HOME is not set!")

    print(f"ecb_home: {ecb_home}")  # Debugging print

    # Construct file path
    img_file_name = os.path.join(ecb_home,
                                 "runlogs/20240606/b85m702/win_file_local_op/skills/open_save_as/images/scrnsongc_yahoo_1717735671.png")

    # Construct request payload
    request = [{
        "id": 702,
        "bid": 85,
        "os": "win",
        "app": "file",
        "domain": "local",
        "page": "op",
        "layout": "",
        "skill_name": "open_save_as",
        "csk": os.path.join(ecb_home, "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.csk"),
        "psk": os.path.join(ecb_home, "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.psk"),
        "lastMove": "top",
        "options": json.dumps({"attention_area": [0, 0, 1, 1], "attention_targets": ["@all"]}),  # Use valid JSON string
        "theme": "light",
        "imageFile": img_file_name,
        "factor": "{}"
    }]

    data = {
        "inScrn": request,
        "requester": "songc@yahoo.com",
        "host": "DESKTOP-DLLV0",
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    # Use local IP instead of .local hostname
    host_ip = "192.168.0.16"
    endpoint = f"http://{host_ip}:8848/graphql/reqScreenTxtRead"

    print("endpoint:", endpoint)

    async with aiohttp.ClientSession() as session:
        try:
            print("Reading file bytes...")
            with open(img_file_name, "rb") as img_file:
                form_data = aiohttp.FormData()
                # Add JSON data as a form field
                form_data.add_field("data", json.dumps(data), content_type="application/json")

                # Add the image file
                form_data.add_field("file", img_file, filename=os.path.basename(img_file_name), content_type="image/png")

                print("Sending HTTP request...")

                # Send the request (FormData will NOT be reused)
                async with session.post(endpoint, data=form_data, timeout=60) as response:
                    response_json = await response.json()
                    print("Response:", response_json)

            #
            # # Open the file inside the FormData block
            # with open(img_file_name, "rb") as img_file:
            #     mp_writer = aiohttp.MultipartWriter()
            #
            #     # Add JSON data as a part
            #     json_part = mp_writer.append(json.dumps(data))
            #     json_part.headers["Content-Disposition"] = 'form-data; name="data"'
            #     json_part.headers["Content-Type"] = "application/json"
            #
            #     # Add the image file as a part
            #     file_part = mp_writer.append(img_file)
            #     file_part.headers[
            #         "Content-Disposition"] = f'form-data; name="file"; filename="{os.path.basename(img_file_name)}"'
            #     file_part.headers["Content-Type"] = "image/png"
            #
            #     print("Sending HTTP request...")
            #
            #     # Force HTTP (disable SSL)
            #     async with session.post(endpoint, data=mp_writer, timeout=60, ssl=False) as response:
            #         response_json = await response.json()
            #         print("Response:", response_json)

        except FileNotFoundError as e:
            print(f"Error: {e}")
        except aiohttp.ClientError as e:
            print(f"Client Error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")


def testSyncLocalImageAPI(parent):

    print("TESTING LOCAL IMG API....")

    # Ensure ECB_HOME is set
    ecb_home = os.getenv("ECB_HOME")
    if not ecb_home:
        raise ValueError("Environment variable ECB_HOME is not set!")

    print(f"ecb_home: {ecb_home}")  # Debugging print

    # Construct file path
    img_file_name = os.path.join(ecb_home,
                                 "runlogs/20240606/b85m702/win_file_local_op/skills/open_save_as/images/scrnsongc_yahoo_1717735671.png")

    # Construct request payload
    request = [{
        "id": 702,
        "bid": 85,
        "os": "win",
        "app": "file",
        "domain": "local",
        "page": "op",
        "layout": "",
        "skill_name": "open_save_as",
        "csk": os.path.join(ecb_home,
                            "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.csk"),
        "psk": os.path.join(ecb_home,
                            "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.psk"),
        "lastMove": "top",
        "options": json.dumps({"attention_area": [0, 0, 1, 1], "attention_targets": ["@all"]}),
        # Use valid JSON string
        "theme": "light",
        "imageFile": img_file_name,
        "factor": "{}"
    }]

    data = {
        "inScrn": request,
        "requester": "songc@yahoo.com",
        "host": "DESKTOP-DLLV0",
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    # Use local IP instead of .local hostname
    host_ip = "192.168.0.11"
    endpoint = f"http://{host_ip}:8848/graphql/reqScreenTxtRead"

    print("endpoint:", endpoint)

    # Ensure file exists before sending
    if not os.path.exists(img_file_name):
        print(f"Error: File not found: {img_file_name}")
        return

    try:
        print("Reading file bytes...")

        # Prepare the multipart request
        with open(img_file_name, "rb") as img_file:
            files = {
                "file": (os.path.basename(img_file_name), img_file, "image/png"),
            }
            payload = {
                "data": json.dumps(data)  # Send JSON as a string
            }

            print("Sending HTTP request...")

            # Send the POST request
            response = requests.post(endpoint, files=files, data=payload, timeout=60)

            # Print response
            print("Response:", response.status_code, response.text)

    except Exception as e:
        print(f"Unexpected error: {e}")


async def testLocalImageAPI2(mwin):
    print("TESTING LOCAL IMG API2....")
    # Ensure ECB_HOME is set
    ecb_home = os.getenv("ECB_HOME")
    if not ecb_home:
        raise ValueError("Environment variable ECB_HOME is not set!")

    print(f"ecb_home: {ecb_home}")  # Debugging print

    # Construct file path
    img_file_name = os.path.join(ecb_home, "runlogs/songc_yahoo_com/20250214/b229m12455/win_ads_local_open/skills/open_profile/images/scrnsongc_yahoo_1739568219.png")
    print("img_file_name:", img_file_name)
    # Construct request payload
    request = [{
        "mid": 12455,
        "bid": 229,
        "os": "win",
        "app": "file",
        "domain": "local",
        "page": "op",
        "layout": "",
        "skill": "open_save_as",
        "csk": os.path.join(ecb_home, "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.csk"),
        "psk": os.path.join(ecb_home, "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.psk"),
        "lastMove": "top",
        "options": json.dumps({"attention_area": [0, 0, 700, 700], "attention_targets": ["@all"]}),
        "theme": "light",
        "imageFile": img_file_name,
        "factor": "{}"
    }]

    data = {
        "inScrn": request,
        "requester": "songc@yahoo.com",
        "host": "DESKTOP-DLLV0",
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    # Use local IP instead of .local hostname
    host_ip = "192.168.0.2"
    endpoint = mwin.getLanApiEndpoint() + "/reqScreenTxtRead/"

    print("endpoint:", endpoint)

    # Ensure file exists before sending
    if not os.path.exists(img_file_name):
        print(f"Error: File not found: {img_file_name}")
        return

    headers = {"Content-Type": "multipart/form-data"}
    timeout = httpx.Timeout(connect=10.0, read=100.0, write=30.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            print("Reading file bytes...")

            # # Open the file in binary mode
            with open(img_file_name, "rb") as img_file:
                # Prepare the multipart form-data request
                files = {"file": (os.path.basename(img_file_name), img_file, "image/png")}
                payload = {"data": json.dumps(data)}

                print("Sending HTTP request...", files)

                # Send the async request
                response = await client.post(endpoint, files=files, data=payload)

                # Print response
                print("Response:", response.status_code, response.text)

        except Exception as e:
            print(f"Unexpected error: {e}")
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorHttpxClient:" + traceback.format_exc() + " " + str(e)
                print(ex_stat)


async def testLocalImageAPI3(mwin):
    ecb_home = os.getenv("ECB_HOME")
    if not ecb_home:
        raise ValueError("Environment variable ECB_HOME is not set!")

    print(f"ecb_home: {ecb_home}")  # Debugging print

    # Construct file path
    img_file_name = os.path.join(ecb_home,
                                 "runlogs/songc_yahoo_com/20250214/b229m12455/win_ads_local_open/skills/open_profile/images/scrnsongc_yahoo_1739568219.png")
    print("img_file_name:", img_file_name)
    # Construct request payload
    request = [{
        "mid": 12455,
        "bid": 229,
        "os": "win",
        "app": "file",
        "domain": "local",
        "page": "op",
        "layout": "",
        "skill": "open_save_as",
        "csk": os.path.join(ecb_home, "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.csk"),
        "psk": os.path.join(ecb_home, "resource/skills/public/win_file_local_op/open_save_as/scripts/open_save_as.psk"),
        "lastMove": "top",
        "options": json.dumps({"attention_area": [0, 0, 700, 700], "attention_targets": ["@all"]}),
        "theme": "light",
        "imageFile": img_file_name,
        "factor": "{}"
    }]

    img_engine = mwin.getImageEngine()
    if img_engine == "lan":
        img_endpoint = mwin.getLanImageEndpoint()
    else:
        img_endpoint = mwin.getWanImageEndpoint()

    local_info = {
        "user": mwin.getUser(),
        "host_name": mwin.getHostName(),
        "ip": mwin.getIP()
    }
    with open(img_file_name, "rb") as image_bytes:
        imgs = [
            {
                "file_name": img_file_name,
                "bytes": image_bytes
            }
        ]
        await req_read_screen8(None, request, None, local_info, imgs, img_engine, img_endpoint)


async def stressTestImageAPI(mwin, iterations):
    tasks = []  # List to keep track of running tasks

    for i in range(iterations):
        print(f"Sending request {i + 1}")

        # Create and launch a task without awaiting it
        task = asyncio.create_task(testLocalImageAPI2(mwin))
        tasks.append(task)  # Store the task to keep track of it

        # Wait a random time between 0 and 7 seconds before sending the next request
        delay = random.uniform(0, 7)
        print(f"Waiting {delay:.2f} seconds before next request...")
        await asyncio.sleep(delay)

    # Optionally, wait for all tasks to complete before exiting
    await asyncio.gather(*tasks)
