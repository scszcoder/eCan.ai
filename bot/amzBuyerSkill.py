from basicSkill import *
from scraperAmz import *
from adsPowerSkill import *
import re
from difflib import SequenceMatcher
import traceback
SAME_ROW_THRESHOLD = 16

def genStepAMZCalScroll(sink, amount, screen, marker, prev_loc, stepN):
    stepjson = {
        "type": "Calibrate Scroll",
        "action": "Extract",
        "data_sink": sink,
        "amount": amount,
        "screen": screen,
        "last_record": prev_loc,
        "marker": marker
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genWinChromeAMZWalkSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_chrome_amz_browse_search", "win", "1.0", "AIPPS LLC", "PUBWINCHROMEAMZBROWSE001",
                                          "Amazon Browsing On Windows Chrome.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_chrome_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genWinChromeAMZWalkSteps("sk_work_settings", this_step, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_chrome_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words


def genWinADSAMZWalkSkill(worksettings, stepN, theme):
    psk_words = "{"
    site_url = "https://www.amazon.com/"

    this_step, step_words = genStepHeader("win_ads_amz_browse_search", "win", "1.0", "AIPPS LLC",
                                          "PUBWINCHROMEAMZBROWSE001",
                                          "AMZ Browse On Windows ADS.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill", "public/win_ads_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end skill", "public/win_ads_amz_home/browse_search", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    # print("DEBUG", "generated skill for windows file operation...." + psk_words)

    return this_step, psk_words

# pagesize - the entire pages size in the unit of # of scroll units.
# this info should be calculated and available from the previous flow.
# at the moment this info is not used, but can be used in future optimization
# start - starting location on this screen in %, if start from the top, this would be 0,
#         if start from half of the product list, it would be 50, meaning 50% of the total page contents.
# SC - at moment this will just be a dumb function， just scroll x numbers of screens down
def genAMZScrollProductListToBottom(stepN, worksettings, start):
    psk_words = ""
    print("DEBUG", "gen_psk_for_scroll_to_bottom...")

    # create loop count var
    lcvarname = "scrollDownProductList"+str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, stepN)
    psk_words = psk_words + step_words

    # give it a random value between 15 and 25 - magic number .  that's how many scrolls will have
    rand_count = random.randrange(15, 20)
    this_step, step_words = genStepCreateData("int", "down_cnt", "NA", rand_count, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("", str(rand_count), "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    print("scroll reached BOTTOM of the page")

    return this_step, psk_words, "down_cnt"

# this info should be calculated and available from the previous flow.
# at the moment this info is not used, but can be used in future optimization
# start - starting location on this screen in %, if start from the bottom, this would be 0,
#         if start from half of the product list, it would be 50, meaning 50% of the total page contents.
# this function has no screen read involved.....
def genAMZScrollProductListToTop(down_cnt, stepN, worksettings):
    psk_words = ""
    print("DEBUG", "gen_psk_for_scroll_to_top...")


    this_step, step_words = genStepCallExtern("global "+down_cnt+", up_cnt\nup_cnt = int("+down_cnt+"* 1.5)", "", "in_line", "", stepN)
    psk_words = psk_words + step_words

    # up must be preceeded by a down scroll, so the cnt is fixed :
    this_step, step_words = genStepLoop("up_cnt > 0", "", "", "scrollUpProductList"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll up", "screen_info", 100, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global up_cnt\nup_cnt = up_cnt-1\nprint('up_cnt:::::', up_cnt)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    print("scroll reached TOP of the page")

    return this_step,psk_words


def genAMZScrollProductDetailsToTop(pagesize, stepN, work_settings):
    psk_words = ""
    print("DEBUG", "gen_psk_for_scroll_to_bottom...")
    this_step, step_words = genStepCreateData("bool", "at_pd_top", "NA", "False", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("attop != True", "", "", "scrollUpProductDetails"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 50, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["add-to-cart"], "direct", ["anchor text"], "any", "useless", "at_pd_top", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    print("scroll reached TOP of the product details page")

    return this_step,psk_words

# result contains the location of center of the title area so that we can click onto it to enter the detail
# page
def genStepAMZMatchProduct(screen, product_list, result, flag, stepN):
    stepjson = {
        "type": "AMZ Match Products",
        "action": "AMZ Match Products",
        "screen": screen,
        "product_list": product_list,
        "result": result,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# the process of browsing a product list page all the way to the bottom of the page, if found product to be browsed in details,
# click into it and browse in details.
# flow_cfg = [ products ]
# page_cfg is the variable name that's pointed to page config, pl is the result of html scraping which should already contain
# the attention field, which are the ones to click into details on this page.....
def genAMZBrowseProductListToBottom(page_cfg, pl, stepN, worksettings, theme):
    psk_words = ""
    prod_cnt = 0
    print("DEBUG", "genAMZBrowseProductListToBottom...")

    this_step, step_words = genStepCreateData("bool", "atbottom", "NA", "False", stepN)
    psk_words = psk_words + step_words


    # scroll page until the 1st product's bottom is near bottom 10% of the page height.
    this_step, step_words = genScrollDownUntil("free_delivery", 90, this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words


    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_list", "top", theme, this_step, pl)
    psk_words = psk_words + step_words

    # now search ofr products and put them into the variable found_products.(alwasy append to the list)
    # this_step, step_words = genStepAMZSearchProducts("screen_info", "found_products", this_step)
    # psk_words = psk_words + step_words


    # star a loop to travel to the bottom of the page, along the way, collect product data and see whether we need
    # to go into product details.
    this_step, step_words = genStepLoop("atbottom != True", "", "", "browsePL2Bottom"+str(stepN), this_step)
    psk_words = psk_words + step_words

    ## scroll down 80% of the screen height.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(2, 0, 0, this_step)
    psk_words = psk_words + step_words

    # scroll page until the next product's bottom is near bottom 10% of the page height.
    this_step, step_words = genScrollDownUntil("free_delivery", 90, this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words
    #

    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_list", "top", theme, this_step, pl)
    psk_words = psk_words + step_words

    # now search for products and put them into the variable found_products.(alwasy append to the list)
    # this_step, step_words = genStepAMZSearchProducts("screen_info", "found_products", this_step)
    # psk_words = psk_words + step_words


    # here, needs to make sure the to-be-matched product list is ready.....

    # check whether there is any match of this flow's product to go into any details.
    # screen, product_list, result, flag, stepN):
    this_step, step_words = genStepAMZMatchProduct("screen_info", pl, "pl_need_attention", "any_interesting", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('pl_need_attention===>',pl_need_attention)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # create a loop to browse attention details...
    this_step, step_words = genStepCreateData("expr", "att_count", "NA", "len(pl_need_attention)-1", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('att_count===>',att_count)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("att_count >= 0", "", "", "browseAttens"+str(stepN), this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count]['box']", "expr", "", [0, 0], "bottom", [0, 0], "box", 1, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
    this_step, step_words = genAMZBrowseDetails(pl, "pl_need_attention", "att_count", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    # update li counter
    this_step, step_words = genStepCallExtern("att_count = att_count - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # after checking whethere there is anything interesting to click into details page.
    # check whether we have reached the end of the page.

    # need now click into the target product.
    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["previous", "next"], "direct", ["anchor text", "anchor text"], "and", "useless", "atbottom", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    return this_step,psk_words


# the process of browsing a product list page all the way to the bottom of the page, if found product to be browsed in details,
# click into it and browse in details.
def genAMZBrowseProductListToLastAttention(pl, stepN, worksettings, theme):
    psk_words = ""
    prod_cnt = 0
    print("DEBUG", "genAMZBrowseProductListToLastAttention...")

    this_step, step_words = genStepCreateData("expr", "nAttentions", "NA", "len("+pl+"['attention'])", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("nAttentions > 0", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("(nAttentions > 0)", "", "", "browsePL2LastAtt"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    # (action, action_args, smount, stepN):
    this_step, step_words = genScrollDownUntil("free_delivery", 80, this_step, worksettings, "amz", theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words


    # now extract the screen info.
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_list", "top", theme, this_step, pl)
    psk_words = psk_words + step_words


    # check whether there is any match of this page's product, if matched, click into it.
    this_step, step_words = genStepAMZMatchProduct("screen_info", pl, "pl_need_attention", "any_interesting", this_step)
    psk_words = psk_words + step_words

    # creat a loop to browse attention details...
    this_step, step_words = genStepCreateData("expr", "att_count", "NA", "len(pl_need_attention)-1", this_step)
    psk_words = psk_words + step_words

    # condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("att_count >= 0", "", "", "browseAttens"+str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global att_count\nprint('att_count:', att_count, pl_need_attention)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global "+pl+"\nprint('pl: ', "+pl+")", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN enter the product details page.
    this_step, step_words = genStepMouseClick("Single Click", "", True, "", "pl_need_attention[att_count]['txts']['box']", "expr", "", [0, 0], "right", [1, 0], "box", 2, 2, [0, 0], this_step)
    psk_words = psk_words + step_words

    # create a loop here to click into the interested product list. Note: loop is inside genAMZBrowseDetail
    this_step, step_words = genAMZBrowseDetails(pl, "pl_need_attention", "att_count", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    # update li counter
    this_step, step_words = genStepCallExtern("global att_count\natt_count = att_count - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("nAttentions = nAttentions - len(pl_need_attention)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # after checking whethere there is anything interesting to click into details page.
    # check whether we have reached the end of the page.

    # need now click into the target product.
    # this_step, step_words = genStepSearchAnchorInfo("screen_info", "add_to_cart", "direct", "info", "any", "useless", "attop", False, this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    #simly scroll down 5 times and be done with this page.
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # we can easily add a few more dumb scroll down actions here.

    return this_step,psk_words

# cfg is the flow config, machted is a list of matched product.
# pl is the complete product list on this page, where we'll update detailed info.
# tbBrowsed are a list of products that are to be browsed into details page.
# this function will run a loop, within the loop:
#    each iteration starts by clicking into the product tbBrowsed,
#    each iteration ends by hitting browser back button to go back to the product list page.
# Note: within the loop, depends on the detail level in the product browse config,
#       we could go further into the browse reviews page....
# if detail level = 1, then click up to 3 rv_expanders.  pseudo code:
# if detail level == 1:
#       max_expandables = 3
# else:
#       max_expandables = 0
# expandables_count = 0
# while expandables_count < max_expandables:
#    if expandables found == True:
#        click on expandable
#        expandables_count = expandables_count + 1
#        extract info again after click
#        search for expandable again
#        if expandables dissappear:
#           scroll down 1/2 screen.
#   else:
#       if end_of_detail == True:
#           break
#       scroll down 1/2 screen.
def genAMZBrowseDetails(pl, atpl, tbb_index, stepN, worksettings, theme):
    psk_words = ""
    print("DEBUG", "genAMZBrowseDetails...")


    # now, starts to browse into the product details page.......................................
    this_step, step_words = genStepCreateData("bool", "end_of_detail", "NA", "False", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("bool", "rv_expandable", "NA", "False", this_step)
    psk_words = psk_words + step_words


    lvl = atpl + "[" + tbb_index +"]['detailLvl']"
    purchase = atpl + "[" + tbb_index + "]['purchase']"

    this_step, step_words = genStepCreateData("expr", "detail_level", "NA", lvl, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global pl_need_attention, att_count, detail_level\nprint('attcnt: ', att_count, 'pl need att: ', pl_need_attention, 'detail_level: ', detail_level)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepCallExtern("global detail_level, "+tbb_index+"\ndetail_level = "+lvl, "", "in_line", "", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "buy_ops", "NA", purchase, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global buy_ops\nprint('buy_ops: ', buy_ops)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # expandables_count = 0
    this_step, step_words = genStepCreateData("int", "expandables_count", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # if detail level == 1:
    #       max_expandables = 3
    # else:
    #       max_expandables = 0
    this_step, step_words = genStepCheckCondition("detail_level == 1", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "max_expandables", "NA", 3, this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "max_expandables", "NA", 1, this_step)
    psk_words = psk_words + step_words

    # # close bracket
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 1, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 1, False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 100, "screen", "scroll_resolution", 0, 0, 1, False, this_step)
    psk_words = psk_words + step_words



    # browse all the way down, until seeing "No customer reviews" or "See all reviews"
    this_step, step_words = genStepLoop("end_of_detail != True", "", "", "browseDetails"+str(stepN+1), this_step)
    psk_words = psk_words + step_words

    #(action, screen, amount, unit, stepN):
    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_details", "top", theme, this_step, pl)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "read_more", "direct", "anchor text", "any", "rv_expanders", "rv_expandable", "amz", False, this_step)
    psk_words = psk_words + step_words

    # while end of detail not reached:
    #   scroll down 1/2 screen
    #   extract screen
    #   search expandables
    #   while expandables_count < max_expandables:
    #       if expandables found == True:
    #           click on expandable
    #           expandables_count = expandables_count + 1
    #           extract info again after click
    #           search expandable again
    #       else:
    #           search for end of details
    #           if end_of_detail == True:
    #               expandables_count = max_expandables
    #           else:
    #               scroll down 1/2 screen.
    #               extract screen info
    #               search expandable again
    #           endif
    #
    #   search for end of details
    this_step, step_words = genStepLoop("expandables_count < max_expandables", "", "", "browseDetails"+str(stepN+1), this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCheckCondition("rv_expandable == True and " + lvl + " == 2", "", "", this_step)
    psk_words = psk_words + step_words


    # # click into "Read more"
    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "read_more", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global expandables_count\nexpandables_count = expandables_count + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # after click on "Read more", capture screen again, at this time "Read More" should have dissappear, if there is more, then
    # let the loop takes care of it, if there is no more "Read More" on screen, scroll down a screen....
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_details", "top", theme, this_step, pl)
    psk_words = psk_words + step_words


    this_step, step_words = genStepSearchAnchorInfo("screen_info", "read_more", "direct", "anchor text", "any", "rv_expanders", "rv_expandable", "amz", False, this_step)
    psk_words = psk_words + step_words


    # else for if rv_expandable == True and " + lvl + " == 2
    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["see_all_reviews", "see_more_reviews", "no_customer_reviews"], "direct", ["anchor text", "anchor text", "anchor text"], "any", "temp", "end_of_detail", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("end_of_detail == True", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global expandables_count, max_expandables\nexpandables_count = max_expandables", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(1, 0, 0, this_step)
    # psk_words = psk_words + step_words


    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 75, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "product_details", "top", theme, this_step, pl)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "read_more", "direct", "anchor text", "any", "rv_expanders", "rv_expandable", "amz", False, this_step)
    psk_words = psk_words + step_words

    # # close bracket: end_of_detail == True
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # # close bracket for if rv_expandable == True and " + lvl + " == 2
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    # close for loop: expandables_count < max_expandables
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", ["see_all_reviews", "see_more_reviews", "no_customer_reviews"], "direct", ["anchor text", "anchor text", "anchor text"], "any", "see_reviews", "end_of_detail", "amz", False, this_step)
    psk_words = psk_words + step_words

    # close for loop: end_of_detail != True
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words


    # # check for whether we have reached end of product details. page.
    # # for level 1 details, will view all the way till the end of reviews
    # # for level 2 details, will view till end of all reviews and open hidden long reviews along the way (click on "see all").
    # # but if this product has no review or has all short reviews where there is no "see all", then this is equivalent to
    # # level 1
    this_step, step_words = genStepCheckCondition("detail_level >= 2", "", "", this_step)
    psk_words = psk_words + step_words

    # # for level 3 and beyond details, will click into read all reviews and examine all reviews
    # # pseudo code:
    # #   if (ncv == None) {
    # #     click on see all reviews.
    # #     gen steps to browse all reviews.
    # #   } else {
    # #    set flag done.
    # #   }
    #
    # this_step, step_words = genStepCheckCondition("len[ncv] == 0", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # for level 3 details, click on see_all_reviews and
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "see_reviews[0]['loc']", "expr", "", 0, "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words
    #
    # # go into all reviews.
    # # this_step, step_words = genStepAMZBrowseReviews("screen_info", lvl, this_step)
    this_step, step_words = genAMZBrowseAllReviewsPage("'4'", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    #
    # this_step, step_words = genStepStub("else", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # set flag to mark the end of the product detail browsing....
    # this_step, step_words = genStepFillData("direct", "True", "detail_done", "", stepN)
    # psk_words = psk_words + step_words
    #
    # # close on check len(ncv)
    # this_step, step_words = genStepStub("end condition", "", "", this_step)
    # psk_words = psk_words + step_words
    #
    # # close on check level <= 2
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    #==== Now that we have completed browsing the product details page. ========
    # check whether there is an buy action here, if there is, scroll to top and perform the buy actions.
    # purchase = page_cfg + "['products'][li]['purchase']"
    this_step, step_words = genStepCheckCondition("len(buy_ops) >  0", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll to top
    # pagesize, stepN, worksettings, page, sect
    this_step, step_words = genAMZScrollProductDetailsToTop([0, 0], this_step, worksettings)
    psk_words = psk_words + step_words

    # if action is add-to-cart, then click on add-to-cart
    this_step, step_words = genStepCheckCondition(purchase + "[0] == 'add cart'", "", "", this_step)
    psk_words = psk_words + step_words


    # if action is add-to-cart, then click on add-to-cart
    this_step, step_words = genAMZPurchaseFlow(purchase + "[0] == 'add cart'", "", this_step)
    psk_words = psk_words + step_words

    # close on check purchase + "[0] == 'add cart'"
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # close on len(buy_ops) >  0
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    # back to produc list page...
    # now go back to the previous browser page. by press alt-left
    this_step, step_words = genStepKeyInput("", True, "alt_left", "", 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(1, 0, 0, this_step)
    psk_words = psk_words + step_words


    return this_step,psk_words


def genAMZPurchaseFlow(screen, purchase_flow, stepN):
    psk_words = ""
    print("DEBUG", "genAMZPurchaseFlow...")

    this_step, step_words = genStepWait(1, 0, 0, stepN)
    psk_words = psk_words + step_words

    return this_step,psk_words


# extract review information from the current screen.
def genExtractReview(scrn, stepN):
    # there are better ways to do this, like reading directly from html, so not going to do this the dumb way...
    print("nop")

# this function generate code to scroll N pages of full reviews.
def genAMZBrowseAllReviewsPage(level, stepN, worksettings, theme):
    # now simply scroll down to the end, there is not even review expansion to click on.... since all are
    # fully expanded anyways.
    # now the question is whether to scroll all the way till the end? or end the scroll by either by # of
    # reviews or number of words.....
    # or even simpler, simply do randome # of scrolls, but need to get to the bottom anyways if need to advance
    # to the next page?
    # OK decided, will flip through
    # SC - 2023-06-09, pseudo code:
    # if level is even number, will scoll down some then back up to view some bad reviews, or if level is odd number
    # will directly scroll thru some bad reviews and then go back....
    psk_words = ""
    #
    this_step, step_words = genStepCreateData("expr", "nNRP", "NA", "random.randint(7, 12)", stepN)
    psk_words = psk_words + step_words

    #
    this_step, step_words = genStepCreateData("expr", "nPRP", "NA", "random.randint(5, 10)", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "nPRP_up", "NA", "nPRP", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nNRP, nPRP, nPRP_up\nprint('nNRP, nPRP, nPRP_up:', nNRP, nPRP, nPRP_up)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('LLlevel:', int(" + level + ")%2)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # extract screen info,
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "all_reviews", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("int(" + level + ")%2 == 0", "", "", this_step)
    psk_words = psk_words + step_words

    # do some overall review scroll, should be mostly positive.
    this_step, step_words = genStepLoop("nPRP > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 70, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nPRP\nnPRP = nPRP - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nPRP_up > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nPRP_up\nnPRP_up = nPRP_up - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # scroll back up to the top.

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepSearchAnchorInfo("screen_info", "all_critical_reviews", "direct", "anchor text", "any", "useless", "hasNegativeReviews", "amz", False, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("hasNegativeReviews", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", False, "screen_info", "all_critical_reviews", "anchor text", "", [0, 0], "center", [0, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nNRP > 0", "", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 0, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    # decrement loop counter.
    this_step, step_words = genStepCallExtern("global nNRP\nnNRP = nNRP - 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now scroll back to top, no need really

    # now simply go back to the previous browser page. by press alt-left
    this_step, step_words = genStepKeyInput("", True, "alt_left", "", 3, this_step)
    psk_words = psk_words + step_words

    return this_step,psk_words


def genScroll1StarReviewsPage(stepN, start):
    psk_words = ""
    print("DEBUG", "genBrowse1StarReviewsPage...")

    # create loop count var
    lcvarname = "scroll1Star" + str(stepN)
    this_step, step_words = genStepCreateData("int", lcvarname, "NA", 0, stepN)
    psk_words = psk_words + step_words

    # give it a random value between 15 and 25 - magic number .  that's how many scrolls will have
    rand_count = random.randrange(3, 10)

    # genStepLoop(condition, count, end, lc_name, stepN):
    this_step, step_words = genStepLoop("", str(rand_count), "", lcvarname, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 90, "screen", "scroll_resolution", 0, 2, 0.5, False, this_step)
    psk_words = psk_words + step_words

    # wait - sort of equivalent to screen read time
    this_step, step_words = genStepWait(0, 1, 3, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    print("scroll reached BOTTOM of the page")

    return this_step, psk_words, rand_count


def genAMZPurchase(cfg):
    print("generating skill for making purchase")



def genStepAMZScrapePLHtml(html_file_var_name, pl, page_num, page_cfg, stepN):
    stepjson = {
        "type": "AMZ Scrape PL Html",
        "action": "Scrape PL",
        "html_var": html_file_var_name,
        "product_list": pl,
        "page_num": page_num,
        "page_cfg": page_cfg,
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



# browse a product list page.
# lastone is True/False, tells whether ith is the last one on the list, this determins whether browsing will
# scoll all the way to the bottom.....
def genAMZBrowseProductLists(pageCfgsName, ith, lastone, flows, stepN, worksettings, theme):
    page_cnt = 0
    psk_words = ""

    # before browsing, first obtain the html code of the page, at the moment, result is not being used...
    # html_file_name, template, root, sink, page, sect, stepN, page_data, option=""
    # ("", lieutenant.homepath, "screen_info", "amazon_home", "top", this_step, None)
    dtnow = datetime.now()
    dt_string = str(int(dtnow.timestamp()))
    hfname = dt_string


    this_step, step_words = genStepCreateData("expr", "hf_name", "NA", "'"+hfname+"'+'_'+str("+ith+")+'.html'", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "file_save_input", "NA", "['save', sk_work_settings['log_path'], hf_name]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepKeyInput("", True, "ctrl,s", "", 4, this_step)
    psk_words = psk_words + step_words

    # save the html file.
    this_step, step_words = genStepUseSkill("open_save_as", "public/win_file_local_op", "file_save_input", "fileStatus", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(18, 0, 0, this_step)
    psk_words = psk_words + step_words

    # SC hacking for speed up the test
    # homepath = os.environ.get("ECBOT_HOME")
    # if homepath[len(homepath)-1] == "/":
    #   homepath=homepath[:len(homepath)-1]
    # hfname = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats1689147960.html"
    # this_step = stepN
    this_step, step_words = genStepCreateData("expr", "current_html_file", "NA", "sk_work_settings['log_path']+hf_name", this_step)
    psk_words = psk_words + step_words
    # this_step, step_words = genStepCreateData("string", "scroll_resolution", "NA", 250, this_step)
    # psk_words = psk_words + step_words
    # this_step, step_words = genStepCreateData("data", "screen_info", "NA", [{"loc": [0, 0, 2030, 3330]}, {"loc": []}], this_step)
    # psk_words = psk_words + step_words

    # very important info saved in "plSearchResult" variable.
    # and extract all useful contents from the html file, the useful contents can also assist the
    # screen read.
    # (html_file_var_name, pl, page_num, page_cfg, stepN):
    # SC hacked for quick testing other procedures.
    this_step, step_words = genStepAMZScrapePLHtml("current_html_file", "plSearchResult", ith, pageCfgsName, this_step)
    psk_words = psk_words + step_words

    print("gen flow: ", flows)

    this_step, step_words = genStepCallExtern("global numFlows\nnumFlows = len("+flows+")", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthFlow", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # algorithm goes like this:
    # for each search result, config will tell you how many product list pages to browse thru,
    # usually less than 3 pages, mostly just 1 or 2 pages.
    # for each page, one can scroll down and up and back down and back up several times.
    # for our algorithm, one will only browse page in details on a downward browse flow.
    # even though a real human could browse in details on an upward flow as well...
    #
    # so the algorithm goes: scroll up is always just scroll without browsing in any details.
    #             scroll down at the inital flow is also simply scroll down without browsing details.
    #             only at the last scroll, it pays attention to details and grab screen contents.
    #  while nthFlow < numFlows:
    #      if this is a scroll down browse flow:
    #           if this is before 2nd to the last flow:
    #               if this is the last product list page:
    #                   browse till the last attention     # at the last page, no need to scroll all the way down
    #               else:
    #                   browse to the bottom of the page.
    #           else:
    #               scroll to the bottom of the page, without browsing.
    #       else if this is a scroll up browse flow:
    #           scroll up to the top without browsi
    #       nthFLow = nthFlow + 1
    this_step, step_words = genStepCallExtern("global nthFlow, numFlows\nprint('000: nthFlow, numFlows', nthFlow, numFlows)",  "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthFlow < numFlows", "", "", "browseAmzPL" + str(stepN), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global nthFlow, numFlows\nprint('nthFlow, numFlows', nthFlow, numFlows)",  "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition(flows+"[nthFlow] == 'down'", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("nthFlow >= numFlows - 2", "", "", this_step)
    psk_words = psk_words + step_words

    # is this the last product list page?
    this_step, step_words = genStepCheckCondition(lastone, "", "", this_step)
    psk_words = psk_words + step_words

    # if this is the last page of this search, then no need to scroll to the bottom, simply scroll to whatever
    # the last attention point. If there is no attention needed, simply scroll a few times and be done.
    this_step, step_words = genAMZBrowseProductListToLastAttention("plSearchResult", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    # for speedy test, directly call other pages. here...
    # this_step, step_words = genAMZBrowseDetails("plSearchResult", "0", this_step, worksettings, theme1707977701.html)

    # this_step, step_words = genAMZBrowseAllReviewsPage("'4'", this_step, root, theme)

    # psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductListToBottom(pageCfgsName, "plSearchResult", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # simply scroll to the bottom, ....no browsing along the way
    this_step, step_words, down_count_var = genAMZScrollProductListToBottom(this_step, worksettings, 0)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # back up is always a quick scroll, will never browse along the way.
    print("scroll up for fun....")
    this_step, step_words = genAMZScrollProductListToTop(down_count_var, this_step, worksettings)
    psk_words = psk_words + step_words

    # # close bracket for condition (pageOfOrders['num_pages'] == pageOfOrders['page'])
    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("global nthFlow\nnthFlow = nthFlow + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    return this_step, psk_words


# create a process skill(.psk) file content for the client side execution.
#  at this point, several things should have been decided:
#  1) os-app-site
#     entrance path - search phrase, menu/category name
#  2) entrance method- search/category(side main menu)/top main menu/
#  3) how to go thru a list of search results:
#       flow - simple flow down, quick flow down then back up to targets,
#       # of pages to go thru (no more than 3)
#       # on each page, how many products and which products.(each page is different.)
#       # of products -
#                   order of browsing: 1st product (amazon choice, best seller, highest reviewer, highest price/review ratio, lowest price, randomly)
#           user on the client side may modify the random product code put in their own. the client side code will know from mission id that
#           what to do the replace random product code.
#       # level of details (glance only top and skip rest, glance thru, glance thru with glaces on 7 images and details)
#       # whether there is purchase action and what action(s)
#
#   type: task.name,
#   site: task.cuspas.split(",")[2],
#   os: task.cuspas.split(",")[0],
#   app: task.cuspas.split(",")[1],
#   runs: [                                        # a run is a search and browse session.
#                                                  # a search will result number of pages, then we'll select
#                                                  # number of pages to view(ususally top 3 pages)
#                                                  # then for each pages will, will determines how many times to
#                                                  # flow thru the page. (down then up , or down up down etc.)
#                                                  # during each flow, will determine how many products to
#                                                  # browse into details page and level of details.
#                                                  # another variable during the detail browsing is how many
#                                                  # reviews to browse, top N good reviews and top M bad reviews.
#                                                  #
#   entry_paths: {
#         type:  gen_entry_type(),                  # could be from "top main menu", "left main menu", or "search"
#         words: [],                                #why list of words here, because category->subcategory->subsubcategory...., need a list of words.
#   },
#   prodlist_pages: [],                                             # list of configurations for the # of product list pages to browse. min: 1, max: 3, only browse up to top 3 pages.
#   ]    -- end of array of run
# #     purchase: [] #[] contains sequential steps needed to get a purchase done, such as "cart", "order", "pay"
# };
# each elemet of prodlist_pages[] = [{
#     flow_type: "",
#     products: [{
#     selType: gen_prod_sel(),    # ["ac", "bs", "op", "mr", "mhr", "cp", "cus" ]; best seller/amazon choice/most rviews/most high ranks/cheapest price/customer defined.
#     detailLvl: gen_detail_lvl(), #1: pick top 5 reviews and expand them, 2: click into all reviews and examine top 5 bad reviews.
#     }]
#    }, ..... ] --> the array/list is list of flows for each page. on each flow there are #of products to pay attention to on that flow.
#                  it's up to the cloud side to arrange no products in the 1st flow down.
#   for the detailLvl, the data structure is as following:
#   { level: 1~5, seeAll : true/false, allPos: true/false, allNeg: true/false, nPosExpand: , nNegExpand:,  nPosPages: , nNegPages: }
# (step, i, mission, skill)
def genWinChromeAMZWalkSteps(worksettings, start_step, theme):
    psk_words = ""
    # this creates the local private skill file.
    #f = open(homepath+"resource/junk.txt", "a")
    # skill name should be some like: browse_search
    # find out skill ID from mission ID,


    # get parent settings which contains tokens to allow the machine to communicate with cloud side.
    site_url = "https://www.amazon.com"


    # open the order page again.
    this_step, step_words = genStepOpenApp("cmd", True, "browser", site_url, "", "", "expr", "sk_work_settings['cargs']", 5, start_step)
    psk_words = psk_words + step_words


    # this url points to a product list page after a keyword search
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats1689147960.html"

    # this url points to a detail page.
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats168914805.html"

    # this url points to all review page.
    # url = homepath+"runlogs/20230712/b3m3/win_chrome_amz_file_save_dialog/skills/browse_search/yoga_mats168914806.html"



    # extract the amazon home page info.
    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # get the location of text "Search" nearest to the top of the screen and store it in variable random_line.
    # loc, txt, screen, tovar, stepN
    # this_step, step_words = genStepRecordTxtLineLocation("middle", "", "screen_info", "cal_marker", this_step)
    # psk_words = psk_words + step_words

    # now scroll down 30 unit.
    # this_step, step_words = genStepMouseScroll("Scroll Down", "screen_info", 1, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    # psk_words = psk_words + step_words

    # this_step, step_words = genStepWait(2, 0, 0, this_step)
    # psk_words = psk_words + step_words

    # extract the amazon home page info again.
    # this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "amazon_home", "top", theme, this_step, None)
    # psk_words = psk_words + step_words

    # then calibrate the  # of pixels per scroll, the result is stored in scroll_resolution variable
    # sink, amount, screen, marker, prev_loc, stepN
    # this_step, step_words = genStepAMZCalScroll("scroll_resolution", "1", "screen_info", "", "cal_marker", this_step)
    # psk_words = psk_words + step_words

    # scroll back up so that we can start search.
    # this_step, step_words = genStepMouseScroll("Scroll Up", "screen_info", 1, "raw", "scroll_resolution", 0, 0, 0.5, False, this_step)
    # psk_words = psk_words + step_words

    # SC hacking for speed up the test   ---- uncomment above.


    # this_step, step_words = genStepCreateData("bool", "position_reached", "NA", "False", this_step)
    # psk_words = psk_words + step_words

    ######## scroll calibration completed #### if skip above, just added the next 2 lines for speed
    this_step, step_words = genStepCreateData("string", "scroll_resolution", "NA", 250, this_step)
    psk_words = psk_words + step_words

    print("DEBUG", "hello???")

    # go thru each entry path.this will be the only loop that we unroll, all other loops within the session will be generated
    # as part of the psk. do we have to unroll??????
    # run_config = worksettings["run_config"]
    this_step, step_words = genStepCreateData("expr", "run_config", "NA", "sk_work_settings['run_config']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numSearchs", "NA", "len(run_config['searches'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthSearch", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthSearch < numSearchs", "", "", "search" + str(start_step), this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("run_config['searches'][nthSearch]['entry_paths']['type'] == 'Top main menu'", "", "", this_step)
    psk_words = psk_words + step_words

    # old code run is run_config['searches'][nthSearch]
    this_step, step_words = genStepCreateData("expr", "top_menu_item", "NA", "run_config['searches'][nthSearch]['top_menu_item']", this_step)
    psk_words = psk_words + step_words

    # click the menu item and enter that page. \
    # (action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "top_menu_item", "var name", "", "1", "0", "right", "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    # much of this is not yet written....this could be somewhat complicated in that the product list entry might take a couple of screens in
    # which the contents could be changing by amazon...

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCheckCondition("run_config['searches'][nthSearch]['entry_paths']['type'] == 'Left main menu'", "", "", this_step)
    psk_words = psk_words + step_words

    # click on the left main menu.
    # (action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "All", "anchor text", "All",
                                              [0, 0], "right", [1, 0], "box", 1, 1, [0, 0], this_step)
    psk_words = psk_words + step_words

    # now scroll down and find the menu item.

    # much of this is not yet written....this could be somewhat complicated in that the product list entry might take a couple of screens in
    # which the contents could be changing by amazon...

    this_step, step_words = genStepStub("else", "", "", this_step)
    psk_words = psk_words + step_words

    # default is the search by phrase.
    # click, type search phrase and hit enter.
    # action, txt, speed, loc, key_after, wait_after, stepN
    # genStepKeyboardAction(action, action_args, screen, target, target_type, template, nth, offset_from, offset, offset_unit, stepN):
    # this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "main_search", "anchor icon", "", [-1, 0], "left", [10, ], "box", 2, 0, [0, 0], this_step)
    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "main_search", "anchor text",
                                              "Search Amazon", [0, 0], "center", [0, 0], "pixel", 2, 0, [0, 0],
                                              this_step)
    psk_words = psk_words + step_words

    # (txt_type, saverb, txt, txt_ref_type, speed, key_after, wait_after, stepN):
    this_step, step_words = genStepTextInput("list", False, "run_config['searches'][nthSearch]['entry_paths']['words']", "expr", 0.05, "enter", 2, this_step)
    psk_words = psk_words + step_words

    # html_file_name, root, result_name, stepN):
    this_step, step_words = genStepCallExtern("print('run entry_paths words', run_config['searches'][nthSearch])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "hfname", "NA", "run_config['searches'][nthSearch]['entry_paths']['words'][0].replace(' ', '_')", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "numPLPages", "NA", "len(run_config['searches'][nthSearch]['prodlist_pages'])", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "nthPLPage", "NA", 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepLoop("nthPLPage < numPLPages", "", "", "search" + str(start_step), this_step)
    psk_words = psk_words + step_words

    # process flow type, and browse the 1st page.
    this_step, step_words = genStepCreateData("expr", "flows", "NA", "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]['flow_type'].split(' ')", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('flows:', flows)", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('run[prodlist_pages][i]:', nthPLPage, '--', run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words


    # (fill_type, src, sink, result, stepN):
    this_step, step_words = genStepFillData("expr", "run_config['searches'][nthSearch]['prodlist_pages'][nthPLPage]", "pl_page_config", "temp", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "lastone", "NA", "nthPLPage == len(run_config['searches'][nthSearch]['prodlist_pages']) - 1", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZBrowseProductLists("pl_page_config", "nthPLPage", "lastone", "flows", this_step, worksettings, theme)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("print('***********************************************************')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "plPageCnt", "NA", 0, this_step)
    psk_words = psk_words + step_words

    # now click on the next page.
    # if not the last page yet, click and go to the next page, what if this product list happens has only 1 page? how to tell whether this is the
    # last page.Answer by SC - actually, never expect this happen on amazon....
    this_step, step_words = genStepCheckCondition("plPageCnt != len(run_config['searches'][nthSearch]['prodlist_pages'])-1", "", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global plPageCnt\nplPageCnt = plPageCnt + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepMouseClick("Single Click", "", True, "screen_info", "Next", "anchor text", "Next", [0, 0], "right", [1, 0], "box", 2, 0, [0, 0], this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("end condition", "", "", this_step)
    psk_words = psk_words + step_words


    this_step, step_words = genStepCallExtern("print('DEBUG', 'page count', plPageCnt, ' out of total [', len(run_config['searches'][nthSearch]['prodlist_pages']), '] of pages....')", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthPLPage\nnthPLPage = nthPLPage + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    # now 1 order update is finished. update the counter
    this_step, step_words = genStepCallExtern("global nthSearch\nnthSearch = nthSearch + 1", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # just give it 30 scrolls to scroll to the top, usually, this should be good enough.
    this_step, step_words = genStepCallExtern("global down_cnt\ndown_cnt = 20", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genAMZScrollProductListToTop("down_cnt", this_step, worksettings)
    psk_words = psk_words + step_words

    # now scroll to top of the page and, take a screen read, get ready for the next round of search.

    this_step, step_words = genStepExtractInfo("", worksettings, "screen_info", "amazon_home", "top", theme, this_step, None)
    psk_words = psk_words + step_words

    # end loop for going thru all completion buttons on the screen
    this_step, step_words = genStepStub("end loop", "", "", this_step)
    psk_words = psk_words + step_words

    #finally handle the purchase, if there is any.
    # if len(run_config["purchases"]) > 0:
    #     # purchase could be done in multiple days usually (put in cart first, then finish payment in a few days)
    #     this_step, step_words = genPurchase(run_config)
    #     psk_words = psk_words + step_words

    print("DEBUG", "ready to add stubs...." + psk_words)


    return this_step, psk_words


def genStepAMZScrapeDetailsHtml(html_file_name, html_file_var_name, root, sink, stepN):
    stepjson = {
        "type": "AMZ Scrape PL Html",
        "action": "Scrape PL",
        "local": html_file_name,
        "html_var": html_file_var_name,
        "root": root,
        "result": sink
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepAMZScrapeReviewsHtml(html_file_name, html_file_var_name, sink, stepN):
    stepjson = {
        "type": "AMZ Scrape PL Html",
        "action": "Scrape PL",
        "local": html_file_name,
        "html_var": html_file_var_name,
        "result": sink
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))




#this is kind of a customized step just for e-commerce.
def genStepAMZSearchProducts(screen, sink, stepN):
    stepjson = {
        "type": "AMZ Search Products",
        "action": "AMZ Search Products",
        "screen": screen,
        "sink": sink
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

# this is kind of a customized step just for e-commerce. extract detailed review page for a product.
## but this can be done in a much easier way, simply click on bad reviews and fake it.
#
def genStepAMZBrowseDetails(screen, sink, flag, stepN):
    stepjson = {
        "type": "AMZ Browse Details",
        "action": "AMZ Browse Details",
        "screen": screen,
        "sink": sink,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson,indent=4) + ",\n"))

# this is kind of a customized step just for e-commerce. extract relavant information in the detail page.
# mainly check product's store, asin, size, weight, category ranking, Q&A, review information.
def genStepAMZSearchReviews(screen, sink, flag, stepN):
    stepjson = {
        "type": "AMZ Search Reviews",
        "action": "AMZ Search Reviews",
        "screen": screen,
        "sink": sink,
        "flag": flag
    }

    return ((stepN+STEP_GAP), ("\"step "+ str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def processAMZSearchProducts(step, i):
    ex_stat = "success:0"
    try:
        scrn = symTab[step["screen"]]
        found = []

        # search for products on this screen.

        # search result should be put into the result variable.
        symTab[step["sink"]] = found
    except:
        ex_stat = "ErrorAMZSearchProducts:" + str(i)

    return (i + 1), ex_stat


# process product detail pages on screen, basically this function searches.
# for reviews to click.
def processAMZBrowseDetails(step, i):
    ex_stat = "success:0"
    try:
        print("Searching....", step["target"])

        scrn = symTab[step["screen"]]
        rvs = extractAMZProductsFromScreen(scrn)

        # search for details on this screen.

        # search result should be put into the result variable.
        symTab[step["sink"]] = None
    except:
        ex_stat = "ErrorAMZBrowseDetails:" + str(i)

    return (i + 1), ex_stat


def processAMZBrowseReviews(step, i):
    ex_stat = "success:0"
    try:
        print("Searching....", step["target"])

        scrn = symTab[step["screen"]]

        found = []

        # search for reviews on this screen.

        # search result should be put into the result variable.
        symTab[step["sink"]] = found
    except:
        ex_stat = "ErrorAMZBrowseReviews:" + str(i)

    return (i + 1), ex_stat


# screen is a list of clickables, we'll need to search thru the clickables to find extracted product list.
# CLICKABLE("product_list", json.dumps(ps), loc[0], loc[1], loc[2], loc[3], "summery", [])
def extractAMZProductsFromScreen(screen):
    products = []
    pl = list(filter(lambda c: c["name"] == "product_list", screen))

    if len(pl) > 0:
        product_summery = [json.loads(ps["text"]) for ps in pl]
        products.append(product_summery)

    return products

# when majority of the words matched.
def title_matched(template_words, scrn_txt_words):
    s = set(scrn_txt_words)
    diff = [i for i in template_words if i not in s]

    # screen text detection should be accurate enough that, there is at most 1 mistake on words, perhaps due to special char or some
    if len(diff) > 2:
        return False
    else:
        return True


# p is screen product.
# tbM is a list of products to be matched against for what's captured on screen right now...
# before tbM, the list of all product on the page has already being extracted from html file and
# filtered with today's walk/buy execution plan to extract out a list of products that fit today's
# plan, now all we need to do is to match the title, price, and number of feedbacks.
# the essence is title match
def prod_matched(ps, tbM):
    matched = False
    ps_words = ps["title"].split()
    for tbM_prod in tbM:
        tbM_title_words = tbM_prod["title"].split()
        matched = title_matched(tbM_title_words, ps_words) and (ps["reviews"] == tbM_prod["reviews"]) and (ps["price"] == tbM_prod["price"])
        if matched:
            break
    return matched



# SC - the hard part is a long title, where on screen, you see only part of that long title with "..." representing
#      what's on screen is not a complete title, in such a case, need to find these ... and
#      2023-07-25 the big assumption is that the product tile is bounded into a paragraph.
#
def match_product(summery, screen_data):
    # the criterial is that > 80% of the words in title, should be matched.
    matched = False
    lines = []
    matched_lines = []
    pmatchs = []
    match_count = 0
    ps = [element for index, element in enumerate(screen_data) if element["name"] == "paragraph"]
    title = re.sub(" +", " ", summery["title"])
    title_word_count = len(title.split())
    # print("initial title word count: ", title_word_count)
    eot = False

    # collect all lines.
    # for p in ps:
    #     lines.extend(p["txt_struct"])

    # sort lines by text length, match the longest ones's first.
    # len_sorted_lines = sorted(lines, key=lambda x: len(x["text"]), reverse=True)

    # for l in len_sorted_lines:
        # go thru each line seg

    for p in ps:
        lines = p["txt_struct"]
        lines = sorted(lines, key=lambda x: len(x["text"]), reverse=True)
        tail = ""
        matched_lines = []
        match_count = 0

        # ttbm - title to be matched is a copy of title.
        ttbm = (title + '.')[:-1]
        # print("TTBM BEFORE: ", ttbm)
        for l in lines:
            # print("LINE: ", l["text"])
            #if a line segment contains 5 or more words and are contained in the title.
            eot = False         # end of title flag
            seg = l["text"].strip()
            seg = re.sub(" +", " ", seg)
            if "..." in seg:
                seg = seg.replace("...", "")
                eot = True

            match = SequenceMatcher(None, seg, ttbm, ).find_longest_match(alo=0, ahi=len(seg), blo=0, bhi=len(ttbm))
            print(match)
            print(seg, "(", seg[match[0]:match[0]+match[2]], ") and ", ttbm, " ((", ttbm[match[1]:match[1]+match[2]], "))")
            matched_word = seg[match[0]:match[0]+match[2]]
            matched_word = re.sub(r'([()\[\].:!])', r'\\\1', matched_word)

            matched_words = seg[match[0]:match[0]+match[2]].split()
            print("matched_word:", matched_word, "<=>", ttbm)
            print("matched_words:[", matched_words, "]", len(matched_words))

            if len(matched_words) > 0:
                if not eot:
                    ttbm = re.sub(matched_word, '', ttbm)     # carve out the matched part.
                    ttbm = re.sub(" +", " ", ttbm)            # again remove redundant white spaces.

                    matched_lines.append(matched_word)
                    match_count = match_count + len(matched_words)
                    # print("title matched: ", l["text"], "#: ", len(l["words"]))
                else:
                    if matched_word.isspace() and matched_word != "":
                        ttbm = re.sub(matched_word, '^', ttbm)
                        tail = ttbm.split("^")[1]
                        # print("LONG title curtailed...", tail, "<<<<<<<<")
                        # done with the paragraph.
                    break

        # print("TTBM AFTER : ", ttbm)
        if tail != "":
            temp = (title + '.')[:-1]
            title_word_count = len(re.sub(tail, '', temp).split())
            # print("AFTRE TAIL CUT title_word_count: ", title_word_count, "TEMP: ", temp)
        pmatchs.append({"p": p, "mls": matched_lines, "mwc": match_count, "twc": title_word_count})

    print("ALL matches:: ", pmatchs)
    ptmatched = sorted(pmatchs, key=lambda x: x["mwc"], reverse=True)

    pt_best_matched = ptmatched[0]
    print("BEST matched:: ", pt_best_matched)
    if pt_best_matched["mwc"] > pt_best_matched["twc"]-3:
        matched = True

    return matched, pt_best_matched["p"]


def processAMZMatchProduct(step, i):
    ex_stat = "success:0"
    try:
        scrn = symTab[step["screen"]]

        tbMatched = symTab[step["product_list"]]["attention"]  # contains anchor/info name, or the text string to matched against.
        print("find to be paid attention: ", tbMatched)

        # now extract all products from the screen capture: scrn
        matched = []
        matched_tbm = []
        if len(tbMatched) > 0:
            for tbm in tbMatched:
                title_matched, matched_paragraph = match_product(tbm["summery"], scrn)
                if title_matched:
                    # swap x-y in prep for the mouse click function.....
                    tempy0 = matched_paragraph["txt_struct"][0]["box"][1]
                    tempy1 = matched_paragraph["txt_struct"][0]["box"][3]
                    matched_paragraph["txt_struct"][0]["box"][1] = matched_paragraph["txt_struct"][0]["box"][0]
                    matched_paragraph["txt_struct"][0]["box"][3] = matched_paragraph["txt_struct"][0]["box"][2]
                    matched_paragraph["txt_struct"][0]["box"][0] = tempy0
                    matched_paragraph["txt_struct"][0]["box"][2] = tempy1

                    matched.append({"txts": matched_paragraph["txt_struct"][0], "detailLvl": tbm["detailLvl"], "purchase": tbm["purchase"]})
                    matched_tbm.append(tbm)


        print(">>>>>>>>matched_tbm: ", matched_tbm)
        print("--------->matched locations: ", matched)
        #for the matched ones, remove from the attention list.
        for tbm in matched_tbm:
            symTab[step["product_list"]]["attention"].remove(tbm)

        print("<<<<>>>>>>>>>>>>remaining attention: ", symTab[step["product_list"]]["attention"])
        # see whether current screen contains the product to be cliced into.
        print("Setting result("+step["result"]+") to be: ", matched)
        symTab[step["result"]] = matched
        # search result should be put into the result variable.
        if len(matched) > 0:
            symTab[step["flag"]] = True
        else:
            symTab[step["flag"]] = False

        print("RESULT of check: ", step["flag"], " :: ", symTab[step["flag"]])


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZMatchProduct:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAMZMatchProduct traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat


def processExtractPurchaseOrder(step, i):
    ex_stat = "success:0"
    try:
        print("Searching....", step["target"])

        scrn = symTab[step["screen"]]
        template = step["template"]  # contains anchor/info name, or the text string to matched against.

        if step["target"] == "Anchor":
            print("")
        elif step["target"] == "Info":
            print("")
        elif step["target"] == "Text":
            template = step["template"]
            print("")

        # search result should be put into the result variable.
        symTab[step["result"]] = None

    except:
        ex_stat = "ErrorExtractPurchaseOrder:" + str(i)

    return (i + 1), ex_stat



# check whether a paragraph contains the keyword
# doesn't cover the special case of keyword sitting on two lines.
def textContains(p, txt):
    found = False
    found = txt in p["text"]
    return found

# check whether two product related text are on a same row.
# input: boundbox of the row of text (left, top, right, bottom)
def amzProductsOnSameRow(p1_txt_box, p2_txt_box):
    same_row = abs(p1_txt_box[1] - p2_txt_box[1]) < (p1_txt_box[3] - p1_txt_box[1])*SAME_ROW_THRESHOLD
    return same_row

# this one calculate the layout of the search result product list page, the result will be 2 variables:
# one in step["pl_page_layout" and step["pl_product_screen_size"]
# The algorithm analyze keyword "Free Shipping" to the next "Free Shipping" Assumption is there are
# at lease 2 free shipping on the page, and
def processAMZCalcProductLayout(step, i):
    ex_stat = "success:0"
    try:
        vdistance = 0                         #unit in pixel.
        scrn = symTab[step["screen"]]

        # first get all info paragraphs out
        ps = [element for index, element in enumerate(scrn["data"]) if element["name"] == "paragraph" and element["type"] == "info"]

        #then search for the one contains the Free Shipping
        found = [element for index, element in enumerate(ps) if textContains(element["name"], "FREE delivery")]
        foundBoxes = []

        if len(found) > 2:
            for p in found:
                for l in p["txt_struct"]:
                    if textContains(l["text"], "FREE delivery"):
                        foundBoxes.append(l["box"])
                        break

            # that check the location of the boxes.
            # if the last two occurances have the on-par vertical location and distinct horiznotal location, that means it's a grid type of layout.
            #
            if amzProductsOnSameRow(foundBoxes[len(foundBoxes)-1], foundBoxes[len(foundBoxes)-2]) or amzProductsOnSameRow(foundBoxes[len(foundBoxes) - 2], foundBoxes[len(foundBoxes) - 3]):
                symTab[step["pl_page_layout"]] = "grid"
            else:
                symTab[step["pl_page_layout"]] = "list"
        elif len(found) == 2:
            # if grid layout, we should never catch only 2 "free delivery" key phrases.
            symTab[step["pl_page_layout"]] = "list"
        else:
            # this is inconclusive, should re-scroll and check.....
            print("WARNING: inconclusive on the layout")


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZCalcProductLayout:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAMZCalcProductLayout traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat




# from a product list, check whether any product matches the search criteria p
#     products: [{
#     selType: gen_prod_sel(),    # ["ac", "op", "bs", "mr", "mhr", "cp", "cus" ]; best seller/amazon choice/most rviews/most high ranks/cheapest price/customer defined.
#     detailLvl: gen_detail_lvl(), #1: pick top 5 reviews and expand them, 2: click into all reviews and examine top 5 bad reviews.
#     }]

# pick a product from pl.
def found_match(p, pl):
    matches = []
    if p["selType"] == "ac":
        # amazon's choice.
        matches = [pr for index, pr in enumerate(pl) if pr["summery"]["ac"]]
    elif p["selType"] == "op":
        # amazon's best overall pick.
        matches = [pr for index, pr in enumerate(pl) if pr["summery"]["op"]]
    elif p["selType"] == "bs":
        # amazon's best seller.
        matches = [pr for index, pr in enumerate(pl) if pr["summery"]["bs"]]
    elif p["selType"] == "mr":
        # most reviews
        rvsorted = sorted(pl, key=lambda x: x["summery"]["feedbacks"], reverse=True)
        matches = [rvsorted[0]]
    elif p["selType"] == "mhr":
        # highest star ranking....
        rvsorted = sorted(pl, key=lambda x: x["summery"]["score"], reverse=True)
        matches = [rvsorted[0]]
    elif p["selType"] == "ms":
        # most past week sales
        rvsorted = sorted(pl, key=lambda x: x["summery"]["weekly_sales"], reverse=True)
        matches = [rvsorted[0]]
    elif p["selType"] == "cp":
        # cheapest price
        rvsorted = sorted(pl, key=lambda x: x["summery"]["price"], reverse=False)
        matches = [rvsorted[0]]
    elif p["selType"] == "cus":
        matches = [{"summery": {"title": "CUSTOM", "rank": 4.5, "feedbacks": 1, "price": 0.01}}]
    else:
        #randomly pick one.
        k = random.randint(0, len(pl)-1)
        matches = [pl[k]]

    if len(matches) > 0:
        for m in matches:
            m["detailLvl"] = p["detailLvl"]
            m["purchase"] = p["purchase"]


        found = matches[0]
    else:
        found = None

    return found


# "hfname": html_file_name,
# "result": sink
# this function scrape amz product search result product list page html file, and
# put results in product list data structure, then it compares the product list with
# this mission's config file to extract the "attention" product list that the user
# will "pay attention to" (i.e. click into it to browse more details).
# Note: this is the place, to swap the custom product to the actual to be swiped product.
def processAMZScrapePLHtml(step, i, mission):
    ex_stat = "success:0"
    try:
        print("Extract Product List from HTML: ", step)

        hfile = symTab[step["html_var"]]
        print("hfile: ", hfile)

        pl = amz_buyer_fetch_product_list(hfile, symTab[step["page_num"]])
        print("scrape product list result: ", pl)

        att_pl = []

        for p in symTab[step["page_cfg"]]["products"]:
            print("current page config: ", p)
            found = found_match(p, pl["pl"])
            if found:
                # remove found from the pl
                print("FOUND product:", found)
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



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZScrapePLHtml:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAMZScrapePLHtml traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat

def processAMZScrapeDetailsHtml(step, i):
    ex_stat = "success:0"
    try:
        print("Extract Product Details from HTML")

        hfile = symTab[step["html_var"]]
        print("hfile: ", hfile)

        if step["result"] in symTab:
            # if new, simply assign the result.
            symTab[step["result"]] = amz_buyer_fetch_product_details(hfile)
        else:
            # otherwise, extend the list with the new results.
            symTab[step["result"]] = symTab[step["result"]] + amz_buyer_fetch_product_details(hfile)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZScrapeDetailsHtml:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAMZScrapeDetailsHtml traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat

def processAMZScrapeReviewsHtml(step, i):
    ex_stat = "success:0"
    try:
        print("Extract Product Reviews from HTML")

        hfile = symTab[step["html_var"]]
        print("hfile: ", hfile)

        if step["result"] in symTab:
            # if new, simply assign the result.
            symTab[step["result"]] = amz_buyer_fetch_product_reviews(hfile)
        else:
            # otherwise, extend the list with the new results.
            symTab[step["result"]] = symTab[step["result"]] + amz_buyer_fetch_product_reviews(hfile)



    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAMZScrapeReviewsHtml:" + json.dumps(traceback_info, indent=4) + " " + str(e)
        else:
            ex_stat = "ErrorAMZScrapeReviewsHtml traceback information not available:" + str(e)
        print(ex_stat)

    return (i + 1), ex_stat
