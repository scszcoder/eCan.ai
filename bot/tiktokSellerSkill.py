from bot.Logger import log3
from bot.basicSkill import genStepHeader, genStepStub, genStepWait, genStepCreateData, genStepCallExtern

SAME_ROW_THRESHOLD = 16

site_url = "https://www.tiktok.com/sh/ord/?filter=status:AWAITING_SHIPMENT"


# this skill simply obtain a list of name/address/phone/order amount/products of the pending orders
# 1） open the orders page
# 2） save and scrape HTML
# 3） if more than 1 page, go thru all pages. get all.
def genWinADSTiktokFullfillOrdersSkill(worksettings, stepN, theme):
    psk_words = "{"

    this_step, step_words = genStepHeader("win_ads_tiktok_fullfill_orders", "win", "1.0", "AIPPS LLC", "PUBWINADSTIKTOK001",
                                          "Tiktok Fullfill New Orders On Windows.", stepN)
    psk_words = psk_words + step_words

    this_step, step_words = genStepStub("start skill main", "public/win_ads_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepWait(5, 0, 0, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("string", "ebay_status", "NA", "", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("obj", "sk_work_settings", "NA", worksettings, this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "product_book", "NA", "sk_work_settings['products']", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCallExtern("global product_book\nprint('product_book:', product_book[0])", "", "in_line", "", this_step)
    psk_words = psk_words + step_words

    # mask out for testing purpose only....
    # this_step, step_words = genStepCreateData("expr", "etsy_orders", "NA", "[]", this_step)
    # psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("expr", "dummy_in", "NA", "[]", this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("int", "scroll_resolution", "NA", 253, this_step)
    psk_words = psk_words + step_words

     # hard default exe path code here just for testing purpose, eventually will be from input or settings....
    this_step, step_words = genStepCreateData("str", "sevenZExe", "NA", 'C:/Program Files/7-Zip/7z.exe', this_step)
    psk_words = psk_words + step_words

    this_step, step_words = genStepCreateData("str", "rarExe", "NA", 'C:/Program Files/WinRaR/WinRaR.exe', this_step)
    psk_words = psk_words + step_words



    this_step, step_words = genStepStub("end skill", "public/win_ads_ebay_orders/fullfill_orders", "", this_step)
    psk_words = psk_words + step_words

    psk_words = psk_words + "\"dummy\" : \"\"}"
    log3("DEBUG", "generated skill for windows ebay order fullfill operation...." + psk_words)

    return this_step, psk_words