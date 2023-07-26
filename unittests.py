from scraperEbay import *


def test_eb_orders_scraper():
    orders = []
    html_file = "C:/temp/Orders — eBay Seller Hub.html"
    ebay_seller_fetch_order_list(html_file, orders)