from scraperEbay import *
from labelCustomGeneneratorSkill import *
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
    test_settings = {"skfname": "unitest0"}

    # a test skill will be writen
    genWinTestSkill(test_settings, 0)

    print("done generating skill============================>")

    rpa_script = prepRun1Skill("UT000", "unitest0")

    print("done all address gen.................")

    # set mission to be None, skill to be None, since we won't be testing extractInfo step.

    # test_m = EBMISSION()
    runAllSteps(rpa_script, None, None)

    print("done testing.................")

