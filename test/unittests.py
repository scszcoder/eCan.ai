from scraperEbay import *
from labelSkill import *
from missions import *
from rarSkill import *
from genSkills import *
from readSkill import *


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
    html_file = "c:/temp/Etsy - 3Sold Orders.html"
    orders = etsy_seller_fetch_order_list(html_file, 0)
