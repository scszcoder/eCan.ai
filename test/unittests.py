from genSkills import *
from readSkill import *
import re
from datetime import datetime
import time
import pytz
from ebbot import *
from missions import *

global symTab


def test_eb_orders_scraper():
    orders = []
    html_file = "C:/temp/Orders — eBay Seller Hub.html"
    ebay_seller_fetch_page_of_order_list(html_file, orders)



def test_etsy_label_gen():
    # createLabelOrderFile(None, "C:/temp/etsy_orders20230730.xls")
    # searchTrackingCode("C:/Users/songc/Downloads/scszsj@gmail.com_SamC__0.pdf")
    # unCompressLabels("C:/Users/songc/Downloads/etsy_orders20230730_xls_122554.rar", "C:/temp/labels/")
    genWinUnRarSkill("", "", "", "")


# can use the following to test any skill file, except the extractInfo one which requiers cloud service.
def test_use_func_instructions():
    psk0 = os.getenv('ECBOT_HOME') +"../testdata/ut0sk1.psk"
    test_settings = {"skfname": psk0}

    # a test skill will be writen
    genWinTestSkill(test_settings, 0)

    print("done generating skill============================>")

    rpa_script = prepRun1Skill("UT000", psk0)

    print("done all address gen.................")

    # set mission to be None, skill to be None, since we won't be testing extractInfo step.
    # test_m = EBMISSION()
    runAllSteps(rpa_script, None, None)

    print("done testing.................")

# can use the following to test any skill file, except the extractInfo one which requiers cloud service.
def test_multi_skills():

    psk1 = os.getenv('ECBOT_HOME') + "../testdata/ut1sk1.psk"
    psk2 = os.getenv('ECBOT_HOME') + "../testdata/ut1sk2.psk"
    test_settings = {"skfname": psk1}
    # a test skill will be writen
    genWinTestSkill1(test_settings, 0)

    test_settings = {"skfname": psk2}
    # a test skill will be writen
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
    global test_page_num = 0

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
    # amission.setStatus('ASSIGNED')
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
    print("done unzipping test....")


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
    # qs = [{"mid": 1, "bid": 1, "status":"Completed:0", "starttime": 123, "endtime": 123}]
    # result = send_completion_status_to_cloud(session, qs, token)
    # print("send_completion_status_to_cloud RESULT:", result)

    # test passed - 2024-01-21
    # qs = [{"actid": 5, "op":"", "options": ""}]
    # result = send_add_bots_request_to_cloud(session, qs, token)
    # print("send_add_bots_request_to_cloud RESULT:", result)
    #

    # test passsed - 2024-01-23
    # abot = parent.bots[0]
    # abot.pubProfile.setPubBirthday("1992-03-01")
    # result = send_update_bots_request_to_cloud(session, [abot], token)
    # print("send_update_bots_request_to_cloud RESULT:", result)
    #
    # test passed - 2024-01-21
    # qs = [{"id": 12, "owner": "", "reason": ""}]
    # result = send_remove_bots_request_to_cloud(session, qs, token)
    # print("send_remove_bots_request_to_cloud RESULT:", result)
    #
    # test passed.
    # result = send_get_bots_request_to_cloud(session, token)
    # print("send_get_bots_request_to_cloud RESULT:", result)

    # test passed
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "qphrase": "etsy male"}
    # result = send_query_bots_request_to_cloud(session, token, qs)
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    #
    # test passed 202-01-24
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

    # test passed 202-01-24
    # amission = EBMISSION(parent)
    # amission.setMid(30)    # MID
    # amission.setTicket(0)
    # amission.setOwner('songc@yahoo.com')
    # amission.setBid(2)
    # amission.setStatus('ASSIGNED')
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
    # test passed - 2024-01-21
    # qs = [{"id": 44, "owner": "", "reason": ""}]
    # result = send_remove_missions_request_to_cloud(session, qs, token)
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    #

    # test passed
    # qs = {"byowneruser": True}
    # qs = {"byowneruser": False, "created_date_range": "2022-10-20 00:00:00,2022-10-25 00:00:00"}
    # result = send_query_missions_request_to_cloud(session, token, qs)
    # print("send_remove_missions_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}


    # test passed.
    # ts_skill = WORKSKILL(parent, "test_skill")
    # qs = [ts_skill]
    # result = send_add_skills_request_to_cloud(session, qs, token)
    # print("send_add_skills_request_to_cloud RESULT:", result)
    # successfull result sample: {'statusCode': 200, 'body': [{'skid': 2, 'owner': 'songc@yahoo.com', 'createdOn': '2024-01-13', 'platform': 'win', 'app': 'chrome', 'site': 'amz', 'name': 'test_skill', 'path': '/resource/skills/public/', 'description': 'This skill does great automation.', 'runtime': 1, 'price_model': '', 'price': 0, 'privacy': 'PRV'}]}

    # test passed.
    # ts_skill.setName("test_skill0")
    # ts_skill.setSkid(1)
    # result = send_update_skills_request_to_cloud(session, qs, token)
    # print("send_update_skills_request_to_cloud RESULT:", result)
    # sample successful result: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '906f94f0-d998-48aa-aca9-6faf60f1964e', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}

    # test passed.
    # qs = [{"skid": 1, "owner": "", "reason": ""}]
    # result = send_remove_skills_request_to_cloud(session, qs, token)
    # print("send_remove_skills_request_to_cloud RESULT:", result)
    # sample results: {'statusCode': 200, 'body': {'$metadata': {'httpStatusCode': 200, 'requestId': '38991f4b-ea44-471a-b48a-f59d93357cfc', 'attempts': 1, 'totalRetryDelay': 0}, 'generatedFields': [], 'numberOfRecordsUpdated': 1}}

    # test passed.
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


    # new_fb = 'feedbacks'
    # fb_type = 'INTEGER'  # Change this to the desired data type
    # rt_col = 'rating'
    #
    # new_rrt = 'price'
    # rrt_type = 'REAL'  # Change this to the desired data type
    # est_col = 'feedbacks'

    # sql = f"ALTER TABLE missions ADD COLUMN {new_fb} {fb_type} AFTER {rt_col};"
    # # sql = "ALTER TABLE missions DROP COLUMN COLUMNNAME"
    # mw.dbCursor.execute(sql)

    # sql = f"ALTER TABLE missions ADD COLUMN {new_rrt} {rrt_type} AFTER {est_col};"
    # sql = "ALTER TABLE missions DROP COLUMN COLUMNNAME"
    # mw.dbCursor.execute(sql)

    # sql ="UPDATE bots SET delDate = '2345-01-01' WHERE botid > 20"
    # mw.dbCursor.execute(sql)
    # print("update bots")
    # mw.dbcon.commit()
    # table_name = 'missions'
    # db_data = mw.dbCursor.fetchall()
    # print("DB Data:", db_data)
    # mw.dbCursor.execute(f"DROP TABLE {table_name};")
    #
    # mw.dbCursor.execute("PRAGMA table_info(missions);")

    # Fetch all the rows (each row represents a column)
    # db_data = mw.dbCursor.fetchall()
    # print("DB Data:", db_data)

    sql = 'SELECT * FROM bots'
    res = mw.dbCursor.execute(sql)

    db_data = res.fetchall()
    print("DB Data:", db_data)