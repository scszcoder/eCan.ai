import json
import re
import math
import traceback
from bs4 import BeautifulSoup
import esprima
from bot.Logger import log3
from bot.ordersData import OrderedProduct, ORDER, OrderPerson, Shipping

from bot.basicSkill import DEFAULT_RUN_STATUS, STEP_GAP, symTab


# this module contains cross platform instructions needed for all e-commerce businesses.
def genStepGenShippingOrdersFromMsgResponses(responses_var, msgs_and_orders_var, product_book_type, label_orders_var, flag_var, stepN):
    stepjson = {
        "type": "Gen Shipping From Msg Responses",
        "responses": responses_var,                     # page index, there could be multiple pages of orders.
        "msgs_and_orders": msgs_and_orders_var,         # java scripts pointer
        "product_book": product_book_type,              # "direct"/"var"/"expr" this directory could be a literal string or a variable.
        "label_orders": label_orders_var,               # result variable
        "flag": flag_var                                # status of the execution of this instruction.
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))



def processGenShippingOrdersFromMsgResponses(step, i):
    global html_dir
    ex_stat = DEFAULT_RUN_STATUS
    try:
        responses = symTab[step["responses"]]
        msgs_and_orders = symTab[step["msgs_and_orders"]]
        product_book = symTab[step["product_book"]]
        responses = symTab[step["responses"]]

        # basically go thru each responses, check action items, if action items contains
        # shipping or return, then generate the shipping label request, these shipping label
        # request can be purchased thru varous means which is handled separately, but
        # the common info are needed such as sender,receiver, product weight, size, shipping service name
        label_orders = []

        symTab[step["label_orders"]] = label_orders

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGenShippingOrdersFromMsgResponses:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGenShippingOrdersFromMsgResponses traceback information not available:" + str(e)
        log3(ex_stat)

    return (i + 1), ex_stat
