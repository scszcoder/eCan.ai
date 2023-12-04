from basicSkill import *
from scraperEbay import *

SAME_ROW_THRESHOLD = 16

site_url = "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT"


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinEbayHandleOrderSkill(lieutenant, bot_works, start_step, theme):
    all_orders = []
    return all_orders

def processEbayScrapeOrdersHtml(step, i, mission, skill):
    ex_stat = "success:0"
    try:
        print("Extract Order List from HTML: ", step)

        hfile = symTab[step["html_var"]]
        print("hfile: ", hfile)

        pl = ebay_seller_fetch_order_list(hfile, step["page_num"])
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

        if not step["product_list"] in symTab:
            # if new, simply assign the result.
            symTab[step["product_list"]] = {"products": pl, "attention": att_pl}
        else:
            # otherwise, extend the list with the new results.
            symTab[step["product_list"]].append({"products": pl, "attention": att_pl})

        print("var step['product_list']: ", symTab[step["product_list"]])
    except:
        ex_stat = "ErrorEbayScrapeOrdersHtml:" + str(i)

    return (i + 1), ex_stat

#
def genWinEbayObtainLabelsSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []
    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", "direct", worksettings["cargs"], 5, this_step)
    psk_words = psk_words + step_words


def genWinEbayUpdateOrderSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []


def genWinEbayHandleReturnSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []
