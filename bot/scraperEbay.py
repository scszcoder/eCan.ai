import json
import re
import traceback
from bs4 import BeautifulSoup
import esprima

from bot.basicSkill import DEFAULT_RUN_STATUS, STEP_GAP, symTab
from bot.Logger import log3
from bot.ordersData import OrderedProduct, ORDER, OrderPerson, Shipping


def ebay_seller_fetch_page_of_order_list(html_file,  pidx):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        pagefull_of_orders = {"page": pidx, "ol": None}
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
                    print("js tree:",tokens)

                    usefull = [t for i, t in enumerate(tokens) if t.type != "Identifier" and t.type != "Punctuator" and t.value != "\"textSpans\"" and t.value != "\"text\""]
                    nindex = 0
                    in_order = False
                    node_stack = []
                    products = []
                    for node in usefull:
                        # log3("node: "+json.dumps(node.value))
                        # stuff we want to grab out of...
                        # creationDate
                        # Ship by ....Jul 12
                        # totalQuantity
                        # displayTotalPrice
                        # orderLineItems -
                        # listingId - after listingSummary line
                        # "363861703280"
                        # title - after listingId
                        # "10W auto clamping car wireless charger - black"
                        # quantity - somewhere 1st appearance after title
                        # buyerDetails
                        # buyerid
                        # "caleb9190"
                        # "orderId"
                        # "05-10261-38305"
                        # "toShippingAddress"
                        # "street1"
                        # "209 Elmer St"
                        # "street2"
                        # "city"
                        # "Auburndale"
                        # "stateOrProvince"
                        # "FL"
                        # "fullName"
                        # "Gimberg Preval"
                        # "zipCode"
                        # "72764-7191"

                        # it is a sequential state machine, the start marker is: "creationDate" , the last marker is "zipCode"
                        if node.type == "String" and node.value == "\"creationDate\"":
                            in_order = True
                            order = ORDER("", "", "", "", "", "", "")
                        elif node.type == "String" and node.value == "\"displayTotalPrice\"":
                            product = OrderedProduct("", "", "", "")
                            product.setPrice(usefull[nindex + 1].value[2:-1])
                            # log3("PRICE:"+usefull[nindex + 1].value[2:-1])
                        elif node.type == "String" and node.value == "\"listingId\"":
                            product.setPid(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"title\"":
                            if in_order:
                                if usefull[nindex-2].value == "\"listingId\"":
                                    product.setPTitle(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"quantity\"":
                            product.setQuantity(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"buyerid\"":
                            buyer = OrderPerson("", "", "", "", "", "", "")
                            buyer.setId(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"toShippingAddress\"":
                            products.append(product)
                        elif node.type == "String" and node.value == "\"street1\"":
                            buyer.setStreet1(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"street2\"":
                            if usefull[nindex+1] != "city":
                                buyer.setStreet2(usefull[nindex+1].value[1:-1])
                        elif node.type == "String" and node.value == "\"city\"":
                            buyer.setCity(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"stateOrProvince\"":
                            buyer.setState(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"fullName\"":
                            buyer.setFullName(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"Order number:\"":
                            order.setOid(usefull[nindex + 1].value[1:-1])
                        elif node.type == "String" and node.value == "\"zipCode\"":
                            buyer.setZip(usefull[nindex + 1].value[1:-1])
                            in_order = False

                            # buyer info collection completed, add buyer and products info to order data
                            order.setProducts(products)
                            order.setRecipient(buyer)
                            shipping = Shipping("", "", "", "", "", "", "", "")
                            order.setShipping(shipping)

                            products = []

                            # now that the order info collection is completed. added this order to the pagefull list of orders.
                            orders.append(order)

                        nindex = nindex + 1

                    # log3(json.dumps(summery.toJson()))
                    # product = OrderedProduct()
                    # order = ORDER()

                    # product.setSummery(summery)
                    # orders.append(order)

        pagefull_of_orders["ol"] = orders
        log3("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # log3(json.dumps(pagefull_of_orders))
        log3("# of orders:"+str(len(orders)))
        print(orders[0].toJson())
        print([ord.toJson() for ord in orders])
        # print(orders)
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
        "type": "EBAY Scrape Orders",
        "pidx": pidx,
        "html_dir": html_dir,
        "html_dir_type": dir_name_type,
        "html_file": html_file,
        "result": outvar,
        "status": statusvar
    }
    return ((stepN+STEP_GAP), ("\"step " + str(stepN) + "\":\n" + json.dumps(stepjson, indent=4) + ",\n"))

def processEbayScrapeOrdersHtml(step, i):
    ex_stat = DEFAULT_RUN_STATUS
    try:
        next_i = i + 1
        pidx = step["pidx"]

        if step["html_dir_type"] == "direct":
            html_dir = step["html_dir"]
        else:
            exec("html_dir = " + step["html_dir"])

        html_file = html_dir + "/" + step["html_file"]
        pagefull_of_orders = {"page": pidx, "n_new_orders": 0, "num_pages": 0, "ol": None}
        orders = []
        option_tags = []

        ebay_seller_fetch_page_of_order_list(html_file, pidx)

        symTab[step["result"]] = pagefull_of_orders


    except Exception as e:
        log3(f"Exception info:{e}")
        ex_stat = "ErrorEtsyExtractTracking:" + str(i)
        log3(ex_stat)

    return next_i, ex_stat
