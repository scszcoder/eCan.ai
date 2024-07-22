import json
import re
import traceback
from bs4 import BeautifulSoup
import esprima

from bot.basicSkill import DEFAULT_RUN_STATUS, STEP_GAP, symTab
from bot.Logger import log3
from bot.ordersData import OrderedProduct, ORDER, OrderPerson, Shipping


def extract_order_data(aj):
    orders = []
    products = []
    try:
        resultsPerPage = int(aj["_initialValue"]["pagination"]["itemsPerPage"]["model"]["selectedValue"]["value"])
        for od in aj["_initialValue"]["orders"]["members"]:
            order = ORDER("", "", "", "", "", "", "")
            order.setOid(od["orderId"])
            order.setCreationDate(od["creationDate"]["textSpans"][0]["text"])
            order.setPaidDate(od["paidDate"]["textSpans"][0]["text"])
            order.setTotalQuantity(int(od["totalQuantity"]["textSpans"][0]["text"]))
            order.setTotalPrice(float(od["displayTotalPrice"]["textSpans"][0]["text"].split("$")[1]))

            products = []
            for pd in od["orderLineItems"]:
                product = OrderedProduct("", "", "", "")

                product.setPid(pd["listingSummary"]["listingId"])
                product.setPTitle(pd["listingSummary"]["title"]["textSpans"][0]["text"])
                product.setQuantity(int(pd["listingSummary"]["quantity"]["textSpans"][0]["text"]))

                for pv in pd["__sh"]["variations"]:
                    var_name = pv["name"]["textSpans"][0]["text"]
                    var_val = pv["value"]["textSpans"][0]["text"]
                    product.addVariation((var_name, var_val))

                products.append(product)

            order.setProducts(products)

            buyer = OrderPerson("", "", "", "", "", "", "")
            buyer.setId(od["__sh"]["buyerDetails"]["buyerid"]["textSpans"][0]["text"])

            buyer.setStreet1(od["__sh"]["buyerDetails"]["toShippingAddress"]["street1"]["textSpans"][0]["text"])
            if od["__sh"]["buyerDetails"]["toShippingAddress"]["street2"]["textSpans"][0]:
                buyer.setStreet2(od["__sh"]["buyerDetails"]["toShippingAddress"]["street2"]["textSpans"][0]["text"])
            else:
                buyer.setStreet2("")
            buyer.setCity(od["__sh"]["buyerDetails"]["toShippingAddress"]["city"]["textSpans"][0]["text"])
            buyer.setState(od["__sh"]["buyerDetails"]["toShippingAddress"]["stateOrProvince"]["textSpans"][0]["text"])
            buyer.setFullName(od["__sh"]["buyerDetails"]["fullName"]["textSpans"][0]["text"])
            buyer.setZip(od["zipCode"]["textSpans"][0]["text"])
            order.setRecipient(buyer)

            shipping = Shipping("", "", "", "", "", "", "", "")
            order.setShipping(shipping)

            orders.append(order)
    except Exception as e:
        log3(f"Exception info:{e}")
        traceback_info = traceback.extract_tb(e.__traceback__)
        if traceback_info:
            ex_stat = "ErrorExtractOrderData:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractOrderData: traceback information not available:" + str(e)
        log3(ex_stat)

    return orders
def extract_orders_from_tokens(tokens):
    is_variations = False
    brace_count = 0
    bracket_count = 0
    json_data = []
    variations_json = None

    try:
        for token in tokens:
            if is_variations:
                json_data.append(token.value)
                if token.type == 'Punctuator':
                    if token.value == '{':
                        brace_count += 1
                    elif token.value == '}':
                        brace_count -= 1
                    elif token.value == '[':
                        bracket_count += 1
                    elif token.value == ']':
                        bracket_count -= 1
                    if brace_count == 0 and bracket_count == 0 and token.value == ',':
                        # End of the JSON object or array
                        is_variations = False
                        json_string = ''.join(json_data)[1:-1]
                        try:
                            # print("jstring:", json_string)
                            variations_json = json.loads(json_string)
                        except json.JSONDecodeError as e:
                            print(f"Error decoding JSON: {e}")

            elif token.type == 'String' and token.value == '"ordersData"':
                # Next token should be `:`
                print("in ordersData")
                next_token_index = tokens.index(token) + 1
                if next_token_index < len(tokens) and tokens[next_token_index].type == 'Punctuator' and tokens[next_token_index].value == ':':
                    # Check if the next token is `{` or `[`
                    next_token_index += 1
                    if next_token_index < len(tokens) and tokens[next_token_index].type == 'Punctuator' and tokens[next_token_index].value in ['{', '[']:
                        is_variations = True
                        json_data = []
                        # if tokens[next_token_index].value == '{':
                        #     brace_count = 1
                        # elif tokens[next_token_index].value == '[':
                        #     bracket_count = 1

    except Exception as e:
        log3(f"Exception info:{e}")
        traceback_info = traceback.extract_tb(e.__traceback__)
        if traceback_info:
            ex_stat = "ErrorExtractOrderFromTokens:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractOrderFromTokens: traceback information not available:" + str(e)
        log3(ex_stat)

    return variations_json


def ebay_seller_fetch_page_of_order_list(html_file,  pidx):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        pagefull_of_orders = {"page": pidx, "ol": None, "n_new_orders": 0, "num_pages": 0}
        orders = []

        # Use Esprima to parse your JavaScript code
        # esprima_output = context.eval("esprima.parse('{}')".format(js_code))

        # Output will be a dictionary representing the parsed JavaScript code
        # log3(esprima_output)

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            print("soup soup")
            # all useful information are here:
            # extract all div tags which contains data-index attribute which is a indication of a product in the product list.
            scriptItems = soup.findAll("script")
            log3(str(len(scriptItems)))

            for item in scriptItems:
                pattern = r'orderId.*?feedbackScore'
                found = re.findall(pattern, item.text)
                if found:
                    print("right script found....")
                    tokens = esprima.tokenize(item.text)
                    # js_tree = esprima.visitor.Visitor(item.text)

                    aj = extract_orders_from_tokens(tokens)

                    orders = extract_order_data(aj)

        pagefull_of_orders["ol"] = orders
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        log3("# of orders:"+str(len(orders)))
        print([ord.toJson() for ord in orders])
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEbaySellerFetchPageOfOrderList:" + str(pidx)
        log3(ex_stat)

    return pagefull_of_orders


def genStepEbayScrapeMsgList(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "EBAY Scrape Msg Lists",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def genStepEbayScrapeCustomerMsgThread(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "EBAY Scrape Customer Msg",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


def processEbayScrapeMsgList(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = " + step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_msg_titles = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ml": None}
        threads = []

        ebay_seller_get_customer_msg_list(html_file, pidx)

        symTab[step["result"]] = pagefull_of_msg_titles

    except Exception as e:
        ex_stat = "ErrorEbayScrapeMsgListHtml:" + traceback.format_exc() + " " + str(e)
        log3(ex_stat)

    return next_i, ex_stat



def processEbayScrapeCustomerMsgThread(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = " + step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_msg_titles = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "thread": None}
        threads = []

        ebay_seller_get_customer_msg_thread(html_file, pidx)

        symTab[step["result"]] = pagefull_of_msg_titles

    except Exception as e:
        ex_stat = "ErrorEbayScrapeCustomerMsgThreadHtml:" + traceback.format_exc() + " " + str(e)
        log3(ex_stat)

    return next_i, ex_stat

def ebay_seller_get_customer_msg_list(html_file, pidx):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        pagefull_of_msgs = {"page": pidx, "msgs": None}
        threads = []

        # Use Esprima to parse your JavaScript code
        # esprima_output = context.eval("esprima.parse('{}')".format(js_code))

        # Output will be a dictionary representing the parsed JavaScript code
        # log3(json.dumps(esprima_output))

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            messages = []
            rows = soup.find_all('tr')
            for row in rows:
                message_id = row.get('id', '')
                if row.find('td', {'id': f'{message_id}-from'}):
                    from_user = row.find('td', {'id': f'{message_id}-from'}).div.text
                    print("from_user:", from_user)
                else:
                    from_user = ""

                if row.find('td', {'id': f'{message_id}-sub'}):
                    subject_div = row.find('td', {'id': f'{message_id}-sub'}).div
                    subject = subject_div.text
                    print("subject:", subject)
                else:
                    subject = ""

                if row.find('td', {'id': f'{message_id}-itm-ends'}):
                    item_ends = row.find('td', {'id': f'{message_id}-itm-ends'}).div.text
                    print("item_ends:", item_ends)
                else:
                    item_ends = ""

                if row.find('td', {'id': f'{message_id}-msg-recvd'}):
                    received_date = row.find('td', {'id': f'{message_id}-msg-recvd'}).div.text
                    print("received_date:", received_date)
                else:
                    received_date = ""

                read_status = 'unread' if 'msg-unread' in row.get('class', []) else 'read'

                # Creating a message dictionary
                message = {
                    'id': message_id,
                    'from': from_user,
                    'subject': subject,
                    'item_ends': item_ends,
                    'received_date': received_date,
                    'read_status': read_status
                }
                messages.append(message)


        pagefull_of_msgs["msgs"] = messages
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # log3(json.dumps(pagefull_of_orders))
        log3("# of messages:"+str(len(messages)))
        log3(json.dumps(pagefull_of_msgs))
        log3("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEbaySellerFetchPageOfOrderList:" + str(pidx)
        log3(ex_stat)

    return pagefull_of_msgs



def ebay_seller_get_customer_msg_thread(html_file):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        thread = []

        # Use Esprima to parse your JavaScript code
        # esprima_output = context.eval("esprima.parse('{}')".format(js_code))

        # Output will be a dictionary representing the parsed JavaScript code
        # log3(json.dumps(esprima_output))

        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            scriptItems = soup.findAll("script")

            for item in scriptItems:
                pattern = r'New message from'
                found = re.findall(pattern, item.text)
                if found:
                    print("found script segment")
                    # New message from:\n            \u003Ca href =
                    pattern = r'u003Cstrong>(.*?)\\u003Cdiv style=\\\"font-weight\:bold'

                    # Use re.findall to extract all occurrences
                    messages = re.findall(pattern, item.text, re.DOTALL)

                    # Output the messages
                    print("found N:", len(messages))
                    for index, message in enumerate(messages):
                        pattern = r'\\.*?>'
                        # Replace the pattern with a newline character
                        modified_text = re.sub(pattern, '\n', message)
                        print(f"Message {index + 1}: {modified_text.strip()}")
                        thread.append(modified_text)


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEbaySellerFetchPageOfOrderList:" + str(e)
        log3(ex_stat)

    return thread


def ebay_seller_get_system_msg_thread(html_file):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        thread = []

        # Use Esprima to parse your JavaScript code
        # esprima_output = context.eval("esprima.parse('{}')".format(js_code))

        # Output will be a dictionary representing the parsed JavaScript code
        # log3(json.dumps(esprima_output))
        with open(html_file, 'rb') as fp:
            soup = BeautifulSoup(fp, 'html.parser')

            scriptItems = soup.findAll("script")

            for item in scriptItems:
                pattern = r'New message from'
                found = extracted_texts = extract_text(item.text)

                for text in found:
                    print(text)
                    print("--------------------------------------------------")
            fp.close()

        #
        # with open(html_file, 'r', encoding='utf-8') as fp:
        #     html_content = fp.read()
        #
        #     pattern = r'From\:(.*?)<button class=\"btn btn-s btn-ter pd-lr\" aria-label=\"Archive message\">Archive</button>'
        #     # match = re.search(pattern, html_content, re.DOTALL)
        #
        #     extracted_texts = extract_text(html_content)
        #
        #     # Printing the extracted texts
        #     for text in extracted_texts:
        #         print(text)

            # print("matched:", match.group(0))
            # # If a match is found, return the section including the button
            # if match:
            #     return match.group(0)
            # else:
            #     return "No matching section found."



    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEbaySellerFetchPageOfOrderList:" + str(e)
        log3(ex_stat)

    return thread


def extract_text(html_content):
    # This pattern matches text within HTML tags and attempts to exclude scripts and non-textual content
    pattern = re.compile(r'>([^<]+)<')

    # Find all matches of the pattern
    matches = pattern.findall(html_content)

    # Filter out any results that are only whitespace or non-meaningful text
    meaningful_texts = [text.strip() for text in matches if text.strip() and not text.startswith(('{', 'window.', 'if('))]

    return meaningful_texts



def genStepEbayScrapeOrdersHtml(html_dir, dir_name_type, html_file, pidx, outvar, statusvar, stepN):
    stepjson = {
        "type": "EBAY Scrape Orders Html",
        "pidx": pidx,                   # page index, there could be multiple pages of orders.
        "html_dir": html_dir,           # html file directory
        "html_dir_type": dir_name_type, # "direct"/"var"/"expr" this directory could be a literal string or a variable.
        "html_file": html_file,         # "file name" again this could be either a string or a variable.
        "result": outvar,               # result variable
        "status": statusvar             # status of the execution of this instruction.
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))


html_dir = ""
def processEbayScrapeOrdersHtml(step, i):
    global html_dir
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = symTab[step["pidx"]]
        print("hello??????????")
        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
            html_file = html_dir + "/" + step["html_file"]
        else:
            print("input html_dir:", step["html_dir"], symTab[step["html_file"]])

            # print("input html_dir:", step["html_dir"], symTab["sk_work_settings"]['log_path'], symTab[step["html_file"]])
            # exec("global html_dir, "+step["html_dir"]+"\nhtml_dir = "+step["html_dir"]+"\nprint('html_dir',html_dir)")
            html_file = symTab[step["html_dir"]] + "/" + symTab[step["html_file"]]

        pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
        orders = []
        option_tags = []
        print("BEFORE SCRAPE:", pagefull_of_orders)

        pagefull_of_orders = ebay_seller_fetch_page_of_order_list(html_file, pidx)

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEbayScrapeOrdersHtml:" + str(e)
        log3(ex_stat)

    return next_i, ex_stat
