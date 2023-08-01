from scraperEbay import *
from labelCustomGeneneratorSkill import *
from rarSkill import *


def test_eb_orders_scraper():
    orders = []
    html_file = "C:/temp/Orders — eBay Seller Hub.html"
    ebay_seller_fetch_order_list(html_file, orders)



def test_etsy_label_gen():
    # createLabelOrderFile(None, "C:/temp/etsy_orders20230730.xls")
    # searchTrackingCode("C:/Users/songc/Downloads/scszsj@gmail.com_SamC__0.pdf")
    # unCompressLabels("C:/Users/songc/Downloads/etsy_orders20230730_xls_122554.rar", "C:/temp/labels/")
    genWinUnRarSkill("", "", "", "")
