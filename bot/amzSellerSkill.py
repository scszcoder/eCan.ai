from basicSkill import *
from scraperAmz import *

SAME_ROW_THRESHOLD = 16


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinEbayHandleOrderSkill(lieutenant, bot_works, start_step, theme):
    all_orders = []
    return all_orders

def processAMZScrapeOrdersHtml(step, i, mission, skill):
    print("Extract Order List from HTML: ", step)

    hfile = symTab[step["html_var"]]
    print("hfile: ", hfile)

    pl = amz_seller_fetch_order_list(hfile, step["page_num"])
    print("scrape product list result: ", pl)

    att_pl = []

    for p in step["page_cfg"]["products"]:
        print("current page config: ", p)
        found = found_match(p, pl["pl"])
        if found:
            # remove found from the pl
            if found["summery"]["title"] != "CUSTOM":
                pl["pl"].remove(found)
            else:
                # now swap in the swipe product.
                found = {"summery": {
                            "title": mission.getTitle(),
                            "rank": mission.getRating(),
                            "feedbacks": mission.getFeedbacks(),
                            "price": mission.getPrice()
                            },
                    "detailLvl": p["detailLvl"],
                    "purchase": p["purchase"]
                }

            att_pl.append(found)

