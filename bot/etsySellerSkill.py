from basicSkill import *
from scraperEtsy import *

SAME_ROW_THRESHOLD = 16

# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinEtsyHandleOrderSkill(lieutenant, bot_works, stepN, theme):
    psk_words = ""
    url = "https://www.etsy.com/your/orders/sold"
    this_step, step_words = genStepOpenApp("Run", True, "browser", url, "", "", lieutenant.skills[skidx].getAppArgs(), stepN)
    psk_words = psk_words + step_words

    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))
    hfname = hfname + dt_string + ".html"

    # SC hacking for speed up the test
    this_step, step_words = genStepSaveHtml(hfname, "current_html_file", "", root, "screen_info", "file_save_dialog", "top", theme, stepN, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepEtsyScrapeOrdersHtml(hfname, "current_html_file", root, "orderListResult", ith, pageCfgs, this_step)
    psk_words = psk_words + step_words

    # now work with orderListResult , the next step is to purchase shipping labels, this will be highly diverse, but at the end,
    # we should obtain a list of tracking number vs. order number. and we fill these back to this page and complete the transaction.


    # now assume the result available in "order_track_codes" which is a list if [{"oid": ***, "sc": ***, "service": ***, "code": ***}]

    return this_step, psk_words


def processEtsyScrapeOrdersHtml(step, i, mission, skill):
    print("Extract Order List from HTML: ", step)

    hfile = symTab[step["html_var"]]
    print("hfile: ", hfile)

    pl = etsy_seller_fetch_order_list(hfile, step["page_num"])
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
    return i+1

#
def genWinEtsyObtainLabelsSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []

def genWinEtsyUpdateOrderSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []

def genWinEtsyHandleReturnSkill(lieutenant, bot_works, start_step, theme):
    all_labels = []
