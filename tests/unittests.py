import json
import os
import re
import subprocess
import time
from datetime import datetime

import pytz

from bot.Cloud import send_account_info_request_to_cloud, send_query_chat_request_to_cloud, send_schedule_request_to_cloud
from bot.adsPowerSkill import readTxtProfile, removeUselessCookies, genProfileXlsx, covertTxtProfiles2XlsxProfiles, \
    processUpdateBotADSProfileFromSavedBatchTxt, formADSProfileBatches
from bot.amzBuyerSkill import processAMZScrapePLHtml
from bot.basicSkill import processSearchWordLine, process7z, convert_to_2d_array, genStepSearchWordLine, \
    get_top_visible_window
from config.app_settings import ecb_data_homepath
from bot.ebbot import EBBOT
from bot.genSkills import genWinTestSkill, genWinTestSkill1, genWinTestSkill2
from bot.missions import EBMISSION
from bot.ordersData import ORDER, OrderPerson, OrderedProduct, Shipping
from bot.readSkill import prepRun1Skill, runAllSteps, prepRunSkill
from bot.scraperAmz import processAmzScrapeSoldOrdersHtml
from bot.scraperEbay import ebay_seller_get_system_msg_thread
from bot.scraperEtsy import processEtsyScrapeOrders

global symTab
import shutil
import pyautogui
import base64


def test_eb_orders_scraper():
    orders = []
    html_file = "C:/temp/Orders — eBay Seller Hub.html"
    html_file = "C:/Users/songc/Downloads/Orders0eBaySellerHub.html"
    # ebay_seller_fetch_page_of_order_list(html_file, 1)

    html_file = "C:/Users/songc/Downloads/MyeBay_ Messages00.html"
    # ebay_seller_get_customer_msg_list(html_file, 1)

    html_file = "C:/Users/songc/Downloads/MyeBay_ Messages18.html"
    # ebay_seller_get_customer_msg_thread(html_file)

    html_file = "C:/Users/songc/Downloads/MyeBay_ Messages18.html"
    ebay_seller_get_system_msg_thread(html_file)


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
    us_addr_pattern = re.compile("[a-zA-Z ]+\, *[A-Z][A-Z] *$")
    ca_addr_pattern = re.compile("[a-zA-Z ]+\, *Canada *$")

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


def test_get_account_info(session, token):
    qs = [{"actid": 5, "op":"", "options": ""}]

    result = send_account_info_request_to_cloud(session, qs, token)

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
    #     # "psk": "C:\\Users\\songc\\PycharmProjects\\ecbot/resource/skills/public/win_ads_local_load/batch_import.psk", -- not working...
    #     "psk": "C:/Users/songc/PycharmProjects/ecbot/resource/skills/public/win_ads_local_load/batch_import.psk",
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
    # send_completion_status_to_cloud(session, allTodoReports, token)


    qs = [{"msgID": "1", "user": "john", "timeStamp": "2024-04-09T12:00:00.000Z", "product": "resistance band", "goal": "customer service", "background": "", "msg_thread": "hi, do you sell fabric type?"}]
    result = send_query_chat_request_to_cloud(session, token, qs)
    print("send_query_chat_request_to_cloud RESULT:", result)



    # qs = [{"mid": 1, "bid": 1, "status":"Completed:0", "starttime": 123, "endtime": 123}]
    # result = send_completion_status_to_cloud(session, qs, token)
    # print("send_completion_status_to_cloud RESULT:", result)

    # tests passed - 2024-01-21
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_add_bots_request_to_cloud(session, qs, token)
    # print("send_add_bots_request_to_cloud RESULT:", result)
    #

    # tests passsed - 2024-01-23
    # abot = parent.bots[0]
    # abot.pubProfile.setPubBirthday("1992-03-01")
    # result = send_update_bots_request_to_cloud(session, [abot], token)
    # print("send_update_bots_request_to_cloud RESULT:", result)
    #
    # tests passed - 2024-01-21
    # qs = [{"id": 12, "owner": "", "reason": ""}]
    # result = send_remove_bots_request_to_cloud(session, qs, token)
    # print("send_remove_bots_request_to_cloud RESULT:", result)
    #
    # tests passed.
    # result = send_get_bots_request_to_cloud(session, token)
    # print("send_get_bots_request_to_cloud RESULT:", result)

    # tests passed
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "qphrase": "etsy male"}
    # result = send_query_bots_request_to_cloud(session, token, qs)
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
    # result = send_add_missions_request_to_cloud(session, [amission], token)
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
    # result = send_update_missions_request_to_cloud(session, [amission], token)
    # print("send_update_missions_request_to_cloud RESULT:", result)
    #
    # tests passed - 2024-01-21
    # qs = [{"id": 44, "owner": "", "reason": ""}]
    # result = send_remove_missions_request_to_cloud(session, qs, token)
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    #

    # tests passed
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "created_date_range": "2022-10-20 00:00:00,2022-10-25 00:00:00"}
    # result = send_query_missions_request_to_cloud(session, token, qs)
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    # tests passed.
    # ts_skill = WORKSKILL(parent, "test_skill")
    # qs = [ts_skill]
    # result = send_add_skills_request_to_cloud(session, qs, token)
    # print("send_add_skills_request_to_cloud RESULT:", result)
    # successfull result sample: {'statusCode': 200, 'body': [{'skid': 2, 'owner': 'songc@yahoo.com', 'createdOn': '2024-01-13', 'platform': 'win', 'app': 'chrome', 'site': 'amz', 'name': 'test_skill', 'path': '/resource/skills/public/', 'description': 'This skill does great automation.', 'runtime': 1, 'price_model': '', 'price': 0, 'privacy': 'PRV'}]}

    # tests passed.
    # ts_skill.setName("test_skill0")
    # ts_skill.setSkid(1)
    # result = send_update_skills_request_to_cloud(session, qs, token)
    # print("send_update_skills_request_to_cloud RESULT:", result)
    # sample successful result: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '906f94f0-d998-48aa-aca9-6faf60f1964e', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}

    # tests passed.
    # qs = [{"skid": 1, "owner": "", "reason": ""}]
    # result = send_remove_skills_request_to_cloud(session, qs, token)
    # print("send_remove_skills_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}

    # tests passed.
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "qphrase": "great automation"}
    # result = send_query_skills_request_to_cloud(session, token, qs)
    # print("send_remove_skills_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    # jresp = send_schedule_request_to_cloud(session, token, "", None)
    # print("send_schedule_request_to_cloud RESULT:", jresp)
    #
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = req_train_read_screen(session, qs, token)
    # print("req_train_read_screen RESULT:", result)
    #
    # tested many times by now
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = req_cloud_read_screen(session, qs, token)
    # print("req_cloud_read_screen RESULT:", result)
    #
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_account_info_request_to_cloud(session, qs, token)
    # print("send_account_info_request_to_cloud RESULT:", result)



    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_account_info_request_to_cloud(session, qs, token)
    # print("send_account_info_request_to_cloud RESULT:", result)

def test_sqlite3(mw):
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

    # new_rrt = 'result'
    # rrt_type = 'TEXT'  # Change this to the desired data type
    # est_col = 'platoon'
    # sql = f"ALTER TABLE missions ADD COLUMN {new_rrt} {rrt_type} AFTER {est_col};"
    # sql = "ALTER TABLE missions DROP COLUMN COLUMNNAME"
    # mw.dbCursor.execute(sql)

    # sql ="UPDATE bots SET email = 'kaiya34@gmail.com' WHERE botid = 15"
    # mw.dbCursor.execute(sql)
    # print("update bots")
    mw.dbcon.commit()

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
        new_bot = EBBOT(parent)
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

    symTab["test_pattern"] = "2[0-9]\."
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


def test_ads_profiling():
    profile_json = readTxtProfile("C:/AmazonSeller/SelfSwipe/ADSProfiles/test_profile.txt")
    print("profile json is:", profile_json)
    print("# cookies:", len(profile_json["cookie"]))
    print("============================================================")
    removeUselessCookies(profile_json, ["amazon"])
    print("after filter, profile json is:", profile_json)

    print("# cookies:", len(profile_json["cookie"]))
    print("============================================================")

    genProfileXlsx(profile_json, "C:/AmazonSeller/SelfSwipe/ADSProfiles/temp0.xlsx")
    # genProfileXlsxs(pfJsons, fnames)


def test_batch_ads_profile_conversion():
    fname = "C:/temp/adsProfilesTest0.json"
    fj = open(fname)
    pJsons = json.load(fj)
    fj.close()

    site_lists = pJsons["site_lists"]
    fnames =  pJsons["fnames"]

    covertTxtProfiles2XlsxProfiles(fnames, site_lists)

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

    jresp = send_schedule_request_to_cloud(session, token, "tests", schedule_test_settings)
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
        message = json_data.encode('utf-8')
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
