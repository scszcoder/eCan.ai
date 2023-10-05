from scraperEbay import *
from scraperEtsy import *
from scrapeGoodSupply import *
from labelSkill import *
from missions import *
from rarSkill import *
from genSkills import *
from readSkill import *
import re

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
    psk0 = "C:/Users/songc/PycharmProjects/testdata/ut0sk1.psk"
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

    psk1 = "C:/Users/songc/PycharmProjects/testdata/ut1sk1.psk"
    psk2 = "C:/Users/songc/PycharmProjects/testdata/ut1sk2.psk"
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
    symTab["in_file"] = 'C:/Users/songc/Downloads/etsyOrdersPriority09122023.xls_0918221925.zip'
    symTab["opath"] = 'C:/Users/songc/PycharmProjects/ecbot/runlogs/20230910/b3m3/win_chrome_etsy_orders/skills/fullfill_orders/etsyOrdersPriority09122023.xls_0918221925'
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
    # subprocess.Popen("C:/Program Files/WinRAR/WinRAR.exe C:/Users/songc/Downloads/Downloads1.rar")
    subprocess.Popen(["C:/Program Files/WinRAR/WinRAR.exe",  "C:/Users/songc/Downloads/Downloads1.rar"])
    for i in range(10):
        print("waiting.......")
        time.sleep(2)


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



