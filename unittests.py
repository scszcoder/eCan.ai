from scraperEbay import *
from labelCustomGeneneratorSkill import *


def test_eb_orders_scraper():
    orders = []
    html_file = "C:/temp/Orders — eBay Seller Hub.html"
    ebay_seller_fetch_order_list(html_file, orders)



def test_etsy_label_gen():
    createLabelOrderFile(None, "C:/temp/etsy_orders20230730.xls")