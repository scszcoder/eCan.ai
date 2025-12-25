import json
import os
import base64
import requests
from config.envi import getECBotDataHome
from utils.logger_helper import logger_helper as logger
import traceback
from config.constants import API_DEV_MODE
from aiolimiter import AsyncLimiter
import websocket
import threading
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl
from typing import Optional, Tuple
from utils.logger_helper import logger_helper
from agent.a2a.common.types import TaskSendParams, Message, TextPart
from agent.cloud_api.constants import cloud_api, DataType, Operation
import aiohttp
# Import new generic GraphQL builder
from agent.cloud_api.graphql_builder import build_mutation

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from datetime import datetime

limiter = AsyncLimiter(1, 1)  # Max 5 requests per second

ecb_data_homepath = getECBotDataHome()

# ==========================================================

def get_appsync_endpoint() -> str:
    """
    Get AppSync API endpoint URL (common method)

    Priority:
    Return corresponding endpoint based on API_DEV_MODE

    Returns:
        AppSync API endpoint URL
    """
    # Return default endpoint based on development mode
    if API_DEV_MODE:
        return "https://cpzjfests5ea5nk7cipavakdnm.appsync-api.us-east-1.amazonaws.com/graphql"
    else:
        return "https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql"


# resp is the response from requesting the presigned_url
def send_file_with_presigned_url(src_file, resp):
    # Upload file to S3 using presigned URL
    with open(src_file, 'rb') as f:
        files = {'file': f}
        r = requests.post(resp['url'], data=resp['fields'], files=files, timeout=60)
    # r = requests.post(resp['body'][0], files=files)
    logger_helper.debug(str(r.status_code))


# resp is the response from requesting the presigned_url
def get_file_with_presigned_url(dest_file, url):
    # Download file to S3 using presigned URL
    # POST to S3 presigned url
    http_response = requests.get(url, stream=True, timeout=60)
    print("DL presigned:", http_response)
    if http_response.status_code == 200:
        dest_dir = os.path.dirname(dest_file)

        # Check if the directory exists, and if not, create it
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        with open(dest_file, 'wb') as f:
            # http_response.raw.decode_content = True
            # shutil.copyfileobj(http_response.raw, f)

            f.write(http_response.content)

            f.close()


def gen_query_reg_steps_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      regSteps (inSteps:[
    """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ type: \"" + query[i]["type"] + "\", "
        rec_string = rec_string + "data: \"" + query[i]["data"] + "\", "
        rec_string = rec_string + "start_time: \"" + query[i]["start_time"] + "\", "
        rec_string = rec_string + "end_time: \"" + query[i]["end_time"] + "\", "
        rec_string = rec_string + "result: \"" + str(query[i]["result"]) + "\" }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_query_chat_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      queryChats (msgs:[
    """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ msgID: \"" + query[i]["msgID"] + "\", "
        rec_string = rec_string + "user: \"" + query[i]["user"] + "\", "
        rec_string = rec_string + "timeStamp: \"" + query[i]["timeStamp"] + "\", "
        rec_string = rec_string + "products: \"" + query[i]["products"] + "\", "
        rec_string = rec_string + "goals: \"" + query[i]["goals"] + "\", "
        rec_string = rec_string + "options: \"" + query[i]["options"] + "\", "
        rec_string = rec_string + "background: \"" + query[i]["background"] + "\", "
        rec_string = rec_string + "msg: \"" + query[i]["msg"] + "\" }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_file_op_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      reqFileOp (fo:[
    """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ op: \"" + query[i]["op"] + "\", "
        rec_string = rec_string + "names: \"" + query[i]["names"] + "\", "
        rec_string = rec_string + "options: \"" + query[i]["options"] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_account_info_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      reqAccountInfo (ops:[
    """
    rec_string = ""
    for i in range(len(query)):
        # actid is ID! type in GraphQL schema, must be quoted as string
        rec_string = rec_string + "{ actid: \"" + str(query[i]["actid"]) + "\", "
        rec_string = rec_string + "op: \"" + json.dumps(query[i]["op"]).replace('"', '\\"') + "\", "
        rec_string = rec_string + "options: \"" + query[i]["options"] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


# graphQL schema:
# type Query {
# 	reqScreenRead(inScrn: [ScreenImg]!): [ScreenInfo]
# 	genSchedules(bots: [String]!, settings: SchSettings): [Schedule]
# input ScreenImg {
#	mid: Int
#	os: String
#	app: String
#	domain: String
#	page: String
#	skill: String
#	lastMove: String
#	mode: String
#	imageFile: String
# }
def gen_screen_read_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
        query MyQuery {
      reqScreenTxtRead (inScrn:[
    """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ mid: " + str(int(query[i]["mid"])) + ", "
        rec_string = rec_string + "bid: " + str(int(query[i]["bid"])) + ", "
        rec_string = rec_string + "os: \"" + query[i]["os"] + "\", "
        rec_string = rec_string + "app: \"" + query[i]["app"] + "\", "
        rec_string = rec_string + "domain: \"" + query[i]["domain"] + "\", "
        rec_string = rec_string + "page: \"" + query[i]["page"] + "\", "
        rec_string = rec_string + "layout: \"" + query[i]["layout"] + "\", "
        rec_string = rec_string + "skill: \"" + query[i]["skill"] + "\", "
        rec_string = rec_string + "psk: \"" + query[i]["psk"] + "\", "
        rec_string = rec_string + "csk: \"" + query[i]["csk"] + "\", "
        rec_string = rec_string + "lastMove: \"" + query[i]["lastMove"] + "\", "
        rec_string = rec_string + "options: \"" + query[i]["options"] + "\", "
        rec_string = rec_string + "theme: \"" + query[i]["theme"] + "\", "
        rec_string = rec_string + "imageFile: \"" + query[i]["imageFile"] + "\", "
        rec_string = rec_string + "factor:  \"" + str(query[i]["factor"]) + "\"" + " }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_obtain_review_request_string(query):
    logger_helper.debug("in query:" + json.dumps(query))
    query_string = """
            query MyQuery {
          getFB (fb_reqs:[
        """
    rec_string = ""
    for i in range(len(query)):
        # rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ number: 1, "
        rec_string = rec_string + "product: \"" + query[i]["product"] + "\", "
        rec_string = rec_string + "orderID: \"\", "
        rec_string = rec_string + "payType: \"\", "
        rec_string = rec_string + "total: 0, "
        rec_string = rec_string + "transactionID: \"\", "
        rec_string = rec_string + "customerMail: \"songc@yahoo.com\", "
        rec_string = rec_string + "customerPhone: \"\", "
        rec_string = rec_string + "instructions: \"" + query[i]["instructions"] + "\", "
        rec_string = rec_string + "origin:  \"ecbot app\"" + " }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_report_vehicles_string(vehicles):
    query_string = """
        mutation MyMutation {
      reportVehicles (input:[
    """
    rec_string = ""
    for i in range(len(vehicles)):
        rec_string = rec_string + "{ vid: " + str(int(vehicles[i]["vid"])) + ", "
        rec_string = rec_string + "vname: \"" + vehicles[i]["vname"] + "\", "
        rec_string = rec_string + "owner: \"" + vehicles[i]["owner"] + "\", "
        rec_string = rec_string + "status: \"" + vehicles[i]["status"] + "\", "
        rec_string = rec_string + "lastseen: \"" + vehicles[i]["lastseen"] + "\", "
        rec_string = rec_string + "functions: \"" + vehicles[i]["functions"] + "\", "
        rec_string = rec_string + "bids: \"" + vehicles[i]["agent_ids"] + "\", "
        rec_string = rec_string + "hardware: \"" + vehicles[i]["hardware"] + "\", "
        rec_string = rec_string + "software: \"" + vehicles[i]["software"] + "\", "
        rec_string = rec_string + "ip: \"" + vehicles[i]["ip"] + "\", "
        rec_string = rec_string + "created_at: \"" + vehicles[i]["created_at"] + "\" }"

        if i != len(vehicles) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string

    logger_helper.debug(query_string)
    return query_string


def gen_dequeue_tasks_string(vehicles):
    vnames = ",".join([v["vname"] for v in vehicles])

    query_string = """
        mutation MyMutation {
      dequeueTasks (input:[
    """
    rec_string = ""
    rec_string = rec_string + "{ "
    rec_string = rec_string + "vehicles: \"" + vnames + "\" }"

    rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string

    logger_helper.debug(query_string)
    return query_string




def gen_query_manager_missions_string(query):
    query_string = """
        query MyQuery {
      getManagerMissions (qm:
    """
    # rec_string = json.dumps({"a": "b"}).replace('"', '\"')
    rec_string = "\"{ \\\"byowneruser\\\": true}\""

    tail_string = """
        )
        }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_schedule_request_string(test_name, schedule_settings):
    if test_name == "":
        qvs = None
        query_string = "query MySchQuery { genSchedules(settings: \"{ \\\"testmode\\\": false, \\\"test_name\\\": \\\"" + test_name + "\\\", \\\"forceful\\\": " + schedule_settings.get(
            "forceful", "false") + ", \\\"skillPreferences\\\": " + schedule_settings.get("skillPreferences",
                                                                                          "{\\\"no_preference\\\":false, \\\"use_in_browser_skill\\\":true}") + ", \\\"tz\\\": \\\"" + schedule_settings.get(
            "tz", "America/Los_Angeles") + "\\\"}\") } "
    else:
        serialized_settings = json.dumps(schedule_settings)
        escaped_settings = serialized_settings.replace('"', '\"')

        query_string = '''
        query MySchQuery {
            genSchedules(settings: "%s")
        }
        ''' % serialized_settings.replace('"', '\\"')  # Escaping quotes

    logger_helper.debug(query_string)
    return query_string




def gen_update_vehicles_string(vehicles):
    query_string = """
        mutation MyMutation {
      updateVehicles (input:[
    """
    rec_string = ""
    for i in range(len(vehicles)):
        rec_string = rec_string + "{ vid: " + str(int(vehicles[i]["vid"])) + ", "
        rec_string = rec_string + "vname: \"" + vehicles[i]["vname"] + "\", "
        rec_string = rec_string + "owner: \"" + vehicles[i]["owner"] + "\", "
        rec_string = rec_string + "status: \"" + vehicles[i]["status"] + "\", "
        rec_string = rec_string + "lastseen: \"" + vehicles[i]["lastseen"] + "\", "
        rec_string = rec_string + "functions: \"" + vehicles[i]["functions"] + "\", "
        rec_string = rec_string + "bids: \"" + vehicles[i]["agent_ids"] + "\", "
        rec_string = rec_string + "hardware: \"" + vehicles[i]["hardware"] + "\", "
        rec_string = rec_string + "software: \"" + vehicles[i]["software"] + "\", "
        rec_string = rec_string + "ip: \"" + vehicles[i]["ip"] + "\", "
        rec_string = rec_string + "created_at: \"" + vehicles[i]["created_at"] + "\" }"

        if i != len(vehicles) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string

    logger_helper.debug(query_string)
    return query_string



def gen_feedback_request_string(fbReq):
    query_string = """
            mutation MyUBMutation {
          getFB (input:[
        """
    rec_string = ""
    for i in range(len(fbReq)):
        rec_string = rec_string + "{ mid: " + str(fbReq[i]["mid"]) + ", "
        rec_string = rec_string + "bid: '" + str(fbReq[i]["bid"]) + "', "
        rec_string = rec_string + "status: \"" + fbReq[i]["status"] + "\", "
        rec_string = rec_string + "starttime: \"" + fbReq[i]["starttime"] + "\", "
        rec_string = rec_string + "endtime: \"" + fbReq[i]["endtime"] + "\"} "

        if i != len(fbReq) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_rag_store_request_string(ragReqs):
    query_string = """
            mutation MyRAGMutation {
          reqRAGStore (input:[
        """
    rec_string = ""
    for i in range(len(ragReqs)):
        rec_string = rec_string + "{ fid: " + str(ragReqs[i]["fid"]) + ", "
        rec_string = rec_string + "pid: " + str(ragReqs[i]["pid"]) + ", "
        rec_string = rec_string + "file: \"" + ragReqs[i]["file"] + "\", "
        rec_string = rec_string + "type: \"" + ragReqs[i]["type"] + "\", "
        rec_string = rec_string + "format: \"" + ragReqs[i]["format"] + "\", "
        rec_string = rec_string + "options: \"" + ragReqs[i]["options"] + "\", "
        rec_string = rec_string + "version: \"" + ragReqs[i]["version"] + "\"} "

        if i != len(ragReqs) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_wan_send_chat_message_string():
    send_msg_mutation = """
        mutation sendWanMessage($input: WanChatMessageInput!) {
          sendWanMessage(input: $input) {
            id
            chatID
            sender
            receiver
            type
            contents
            parameters
            timestamp
          }
        }
        """

    return send_msg_mutation


def gen_wan_subscription_connection_string():
    sub_conn_string = """
        subscription onMessageReceived($chatID: String!) {
          onMessageReceived(chatID: $chatID) {
            id
            chatID
            sender
            receiver
            type
            contents
            parameters
            timestamp
          }
        }
        """

    return sub_conn_string


def set_up_cloud():
    this_session = requests.Session()
    return this_session


async def set_up_cloud8():
    REGION = 'us-east-1'
    this_session = None
    # session = requests.Session()

    async with aiohttp.ClientSession() as session:
        this_session = session
    return this_session


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_schedule_request_to_cloud(session, token, ts_name, schedule_settings, endpoint):
    mutation = gen_schedule_request_string(ts_name, schedule_settings)

    jresp = appsync_http_request2(mutation, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("cloud schedule error:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["genSchedules"])
        # no logging, the data could be large.
        # logger_helper.debug("reponse:"+json.dumps(jresponse))

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_cloud_read_screen(session, request, token, endpoint):
    query = gen_screen_read_request_string(request)

    jresp = appsync_http_request(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


async def req_cloud_read_screen8(session, request, token, endpoint):
    query = gen_screen_read_request_string(request)

    jresp = await appsync_http_request8(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


def req_cloud_obtain_review(session, request, token, endpoint):
    query = gen_obtain_review_request_string(request)

    jresp = appsync_http_request(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["errorInfo"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse


def req_cloud_obtain_review_w_aipkey(session, request, apikey, endpoint):
    query = gen_obtain_review_request_string(request)

    jresp = appsync_http_request_w_apikey(query, session, apikey, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["errorInfo"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse



def send_update_vehicles_request_to_cloud(session, vehicles, token, endpoint):
    mutationInfo = gen_update_vehicles_string(vehicles)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateVehicles"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_make_order_request_to_cloud(session, orders, token, endpoint):
    mutationInfo = gen_make_order_string(orders)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse



def send_report_vehicles_to_cloud(session, token, vehicles, endpoint):
    queryInfo = gen_report_vehicles_string(vehicles)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    # jresp = {"data": {"reportVehicles": {}}}
    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reportVehicles"])

    return jresponse


def send_dequeue_tasks_to_cloud(session, token, vehicles, endpoint):
    queryInfo = gen_dequeue_tasks_string(vehicles)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["dequeueTasks"])

    return jresponse



def send_query_chat_request_to_cloud(session, token, chat_request, endpoint):
    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])

    return jresponse


async def send_query_chat_request_to_cloud8(session, token, chat_request, endpoint):
    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = await appsync_http_request8(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_file_op_request_to_cloud(session, fops, token, endpoint):
    queryInfo = gen_file_op_request_string(fops)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse


def send_account_info_request_to_cloud(session, acct_ops, token, endpoint):
    queryInfo = gen_account_info_request_string(acct_ops)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    logger_helper.debug("account info response:" + json.dumps(jresp))
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"ERROR Type: {error_type} ERROR Info: {error_msg}")
        jresponse = {"errorType": error_type, "message": error_msg}
    else:
        jresponse = json.loads(jresp["data"]["reqAccountInfo"])

    return jresponse


def send_reg_steps_to_cloud(session, localSteps, token, endpoint):
    queryInfo = gen_query_reg_steps_string(localSteps)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["regSteps"])

    return jresponse


def send_feedback_request_to_cloud(session, fb_reqs, token, endpoint):
    queryInfo = gen_feedback_request_string(fb_reqs)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse


def send_rag_store_request_to_cloud(session, fb_reqs, token, endpoint):
    queryInfo = gen_rag_store_request_string(fb_reqs)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqRAGStore"])

    return jresponse


def findIdx(list, element):
    try:
        index_value = list.index(element)
    except ValueError:
        index_value = -1
    return index_value


def upload_file(session, f2ul, destination, token, endpoint, ftype="general"):
    try:
        logger_helper.debug(
            ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        fname = os.path.basename(f2ul)
        fwords = f2ul.split("/")
        relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
        if destination:
            prefix = ftype + "|" + destination
        else:
            prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

        fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
        logger_helper.debug("fopreqs:" + json.dumps(fopreqs))

        res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
        logger_helper.debug("cloud response: " + json.dumps(res['body']['urls']['result']))
        logger_helper.debug(
            ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        resd = json.loads(res['body']['urls']['result'])
        logger_helper.debug("resd: " + json.dumps(resd))

        # now perform the upload of the presigned URL
        logger_helper.debug("f2ul:" + json.dumps(f2ul))
        resp = send_file_with_presigned_url(f2ul, resd['body'][0])
        #  logger_helper.debug("upload result: "+json.dumps(resp))
        logger_helper.debug(
            ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        link = resd['body'][0]['fields']['key']

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "Errorupload_file:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "Errorupload_file traceback information not available:" + str(e)
        link = ""

    return link


# datahome should ends with "/", f2dl should starts with "runlogs"
def download_file(session, datahome, f2dl, source, token, endpoint, ftype="general"):
    try:
        fname = os.path.basename(f2dl)
        fwords = f2dl.split("/")
        relf2dl = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
        if source:
            prefix = ftype + "|" + source
        else:
            prefix = ftype + "|" + os.path.dirname(f2dl)

        # local_f2dl = re.sub(r'(runlogs/)[^/]+/', r'\1', f2dl)
        local_f2dl = f2dl

        fopreqs = [{"op": "download", "names": fname, "options": prefix}]
        print("FOPREQS:", fopreqs)

        res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
        # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

        resd = json.loads(res['body']['urls']['result'])
        print("RESD:", resd, resd['body'][0])
        # logger_helper.debug("cloud response data: "+json.dumps(resd))
        resp = get_file_with_presigned_url(datahome + "/" + local_f2dl, resd['body'][0])
        #
        # logger_helper.debug("resp:"+json.dumps(resp))
        link = datahome + "/" + local_f2dl

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "Errordownload_file:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "Errordownload_file traceback information not available:" + str(e)
        link = ""

    return link


# def download_file8(session, datahome, f2dl, token, endpoint, ftype="general"):
#     try:
#         fname = os.path.basename(f2dl)
#         fwords = f2dl.split("/")
#         relf2dl = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
#         prefix = ftype + "|" + os.path.dirname(f2dl)

#         fopreqs = [{"op": "download", "names": fname, "options": prefix}]

#         res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
#         # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

#         resd = json.loads(res['body']['urls']['result'])
#         # logger_helper.debug("cloud response data: "+json.dumps(resd))
#         resp = get_file_with_presigned_url(datahome+f2dl, resd['body'][0])
#         #
#         # logger_helper.debug("resp:"+json.dumps(resp))
#         link = resd['body'][0]

#     except Exception as e:
#         # Get the traceback information
#         traceback_info = traceback.extract_tb(e.__traceback__)
#         # Extract the file name and line number from the last entry in the traceback
#         if traceback_info:
#             ex_stat = "Errordownload_file8:" + traceback.format_exc() + " " + str(e)
#         else:
#             ex_stat = "Errordownload_file8 traceback information not available:" + str(e)
#         link = ""

#     return link


# list dir on my cloud storage
# def cloud_ls(session, token, endpoint):
#     flist = []
#     fopreqs = [{"op" : "list", "names": "", "options": ""}]
#     res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
#     # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

#     for k in res['body']["urls"][0]['Contents']:
#         flist.append(k['Key'])

#     return flist


# def cloud_rm(session, f2rm, token, endpoint):
#     fopreqs = [{"op": "delete", "names": f2rm, "options": ""}]
#     res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
#     logger_helper.debug("cloud response: "+json.dumps(res['body']))

def appsync_http_request(query_string, session, token, endpoint=None, timeout=180):
    """
    Send AppSync GraphQL request with authentication.
    Supports both Cognito User Pool tokens and Google ID tokens.

    Args:
        query_string: GraphQL query string
        session: requests.Session object
        token: Authentication token
        endpoint: API endpoint URL (optional, will use get_appsync_endpoint() if not provided)
        timeout: Request timeout in seconds (default: 180)
    """
    # 如果没有提供 endpoint，使用通用方法获取
    if not endpoint:
        endpoint = get_appsync_endpoint()

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache"
    }

    try:
        # Send the request with configurable timeout
        response = session.request(
            url=endpoint,
            method='POST',
            timeout=timeout,
            headers=headers,
            json={'query': query_string}
        )
        print("raw response: ", response)
        jresp = response.json()
        print("json respose: ", response)
        # Check for authentication errors
        if "errors" in jresp:
            for error in jresp["errors"]:
                if error.get("errorType") == "UnauthorizedException":
                    logger_helper.error(f"AppSync authentication failed: {error.get('message', 'Unknown error')}")
                    logger_helper.error(f"Token format: {token[:50]}...")

        return jresp

    except Exception as e:
        logger_helper.error(f"AppSync request failed: {e}")
        return {
            'errors': [{
                'errorType': 'RequestError',
                'message': str(e)
            }]
        }


def appsync_http_request_w_apikey(query_string, session, apikey, endpoint):
    headers = {
        'Content-Type': "application/graphql",
        'Authorization': apikey,
        'x-custom-api-key': apikey,
        'x-api-caller': "songc@yahoo.com",
        'cache-control': "no-cache"
    }

    # Now we can simply post the request...
    response = session.request(
        url=endpoint,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()

    return jresp


def appsync_http_request2(query_string, session, token, endpoint):
    headers = {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    # Now we can simply post the request...
    response = session.request(
        url=endpoint,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()

    return jresp


async def appsync_http_request8(query_string, token, endpoint, retries=3):
    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    for attempt in range(retries):
        try:
            async with limiter:  # Ensure only 5 requests run per second
                async with aiohttp.ClientSession() as session8:
                    async with session8.post(
                            url=endpoint,
                            timeout=aiohttp.ClientTimeout(total=300),
                            headers=headers,
                            json={'query': query_string}
                    ) as response:
                        return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff (2s, 4s, 8s...)

    raise Exception("Failed after multiple retries")
    # headers = {
    #     'Content-Type': "application/graphql",
    #     'Authorization': token,
    #     'cache-control': "no-cache",
    # }
    # async with aiohttp.ClientSession() as session8:
    #     async with session8.post(
    #             url=endpoint,
    #             timeout=aiohttp.ClientTimeout(total=300),
    #             headers=headers,
    #             json={'query': query_string}
    #     ) as response:
    #         jresp = await response.json()
    #         # print(jresp)
    #         return jresp


async def send_file_op_request_to_cloud8(session, fops, token, endpoint):
    queryInfo = gen_file_op_request_string(fops)

    jresp = await appsync_http_request8(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse


async def send_file_with_presigned_url8(session, src_file, resp):
    async with aiohttp.ClientSession() as session:
        with open(src_file, 'rb') as f:
            form = aiohttp.FormData()
            for key, value in resp['fields'].items():
                form.add_field(key, value)
            form.add_field('file', f, filename=src_file)
            async with session.post(resp['url'], data=form) as r:
                logger_helper.debug("SENDING PRESIGNED URL STATUS:" + str(r.status))
                # print("PRESIGNED RESPONSE:",r)
                f.close()
                return r.status


async def upload_file8(session, f2ul, token, endpoint, ftype="general"):
    logger_helper.debug(
        ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    fname = os.path.basename(f2ul)
    fwords = f2ul.split("/")
    relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

    fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
    logger_helper.debug("fopreqs:" + json.dumps(fopreqs))

    # get presigned URL
    res = await send_file_op_request_to_cloud8(session, fopreqs, token, endpoint)
    logger_helper.debug("cloud response: " + json.dumps(res['body']['urls']['result']))
    logger_helper.debug(
        ">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    resd = json.loads(res['body']['urls']['result'])
    logger_helper.debug("resd: " + json.dumps(resd))

    # now perform the upload of the presigned URL
    logger_helper.debug("f2ul:" + json.dumps(f2ul))
    resp = await send_file_with_presigned_url8(session, f2ul, resd['body'][0])
    #  logger_helper.debug("upload result: "+json.dumps(resp))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

# ==========================================================================================
#	requestRunExtAgentSkill(input: [SkillRun]): AWSJSON!
# 	skid: ID!
# 	owner: String
# 	name: String
# 	start: AWSDateTime
# 	in_data: AWSJSON!
# 	verbose: Boolean
def gen_query_reqest_run_ext_agent_skill_string(query):
    logger.debug("in query:"+json.dumps(query))
    query_string = """
        mutation MyMutation {
      requestRunExtAgentSkill (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ askid: " + str(query[i]["askid"]) + ", "
        rec_string = rec_string + "requester_mid: " + str(query[i]["requester_mid"]) + ", "
        rec_string = rec_string + "owner: \"" + query[i]["owner"] + "\", "
        rec_string = rec_string + "start: \"" + query[i]["start"] + "\", "
        rec_string = rec_string + "name: \"" + query[i]["name"] + "\", "
        rec_string = rec_string + "in_data: \"" + query[i]["in_data"] + "\", "
        # rec_string = rec_string + "verbose: " + str(query[i]["verbose"]) + " }"
        rec_string += "verbose: " + ("true" if query[i]["verbose"] else "false") + " }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

#
def gen_query_report_run_ext_agent_skill_status_string(query):
    logger.debug("in query:"+json.dumps(query))
    query_string = """
        mutation MyMutation {
      reportRunExtAgentSkillStatus (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ run_id: " + str(query[i]["run_id"]) + ", "
        rec_string = rec_string + "skid: " + str(query[i]["skid"]) + ", "
        rec_string = rec_string + "runner_mid: " + str(query[i]["runner_mid"]) + ", "
        rec_string = rec_string + "runner_bid: " + str(query[i]["runner_bid"]) + ", "
        rec_string = rec_string + "requester: \"" + str(query[i]["requester"]) + "\", "
        rec_string = rec_string + "status: \"" + query[i]["status"] + "\", "
        rec_string = rec_string + "start_time: \"" + query[i]["start_time"] + "\", "
        rec_string = rec_string + "end_time: \"" + query[i]["end_time"] + "\", "
        rec_string = rec_string + "result_data: \"" + query[i]["result_data"] + "\" }"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_add_agents_string(agents):
    """
    Generate GraphQL mutation string for adding agents
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.AGENT, Operation.ADD, agents)


def gen_update_agents_string(agents):
    """
    Generate GraphQL mutation string for updating agents
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.AGENT, Operation.UPDATE, agents)




def gen_remove_agents_string(removeOrders):
    """
    Generate GraphQL mutation string for removing agents
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.AGENT, Operation.DELETE, removeOrders)


def gen_query_agents_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MyBOTQuery { queryAgents(qb: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MyBOTQuery { queryAgents(qb: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

def gen_get_agents_string():
    """Generate GraphQL query string for getting all agents for current user"""
    # Use queryAgents with input parameter (AgentQueryInput type)
    # Returns [Agent!]! so we need to specify which fields to select
    query_string = '''query MyGetAgentQuery {
  queryAgents(input: {}) {
    id
    owner
    name
    title
    supervisor_id
    birthday
    gender
    personalities
    status
    rank
    vehicle_id
    avatar_resource_id
    description
    url
    version
    extra_data
    capabilities
    created_at
    updated_at
  }
}'''
    logger.debug(query_string)
    return query_string



def gen_add_agent_skills_string(skills):
    """
    Generate GraphQL mutation string for adding skills
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.SKILL, Operation.ADD, skills)





def gen_update_agent_skills_string(skills):
    """
    Generate GraphQL mutation string for updating skills
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.SKILL, Operation.UPDATE, skills)




def gen_remove_agent_skills_string(removeOrders):
    """
    Generate GraphQL mutation string for removing skills
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.SKILL, Operation.DELETE, removeOrders)



def gen_query_agent_skills_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MySkQuery { queryAgentSkillRelations(qs: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { queryAgentSkillRelations(qs: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\"" +q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

def gen_get_agent_skills_string():
    """Generate GraphQL query string for getting all skills for current user
    
    Server schema: queryAgentSkills(input: SkillQueryInput): [AgentSkill!]!
    SkillQueryInput: { id: ID, name: String, description: String }
    AgentSkill fields: id, askid, owner, name, description, version, level, config, diagram,
                       tags, examples, inputModes, outputModes, apps, limitations, path,
                       source, price, price_model, public, rentable
    """
    # Query all skills by passing empty input (no filters)
    query_string = '''query MyGetAgentSkillsQuery {
        queryAgentSkills(input: {}) {
            id
            askid
            owner
            name
            description
            version
            level
            config
            diagram
            tags
            examples
            inputModes
            outputModes
            apps
            limitations
            path
            source
            price
            price_model
            public
            rentable
        }
    }'''
    logger.debug(query_string)
    return query_string


def gen_add_agent_tasks_string(tasks, test_settings=None):
    """
    Generate GraphQL mutation string for adding tasks
    
    Now uses generic GraphQL builder based on Schema
    No hardcoded fields - all fields come from data and Schema mapping
    """
    # Don't pass settings - GraphQL schema doesn't support it
    return build_mutation(DataType.TASK, Operation.ADD, tasks)


def gen_remove_agent_tasks_string(removeOrders):
    """
    Generate GraphQL mutation string for removing tasks
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.TASK, Operation.DELETE, removeOrders)



def gen_update_agent_tasks_string(tasks):
    """
    Generate GraphQL mutation string for updating tasks
    
    Now uses generic GraphQL builder based on Schema
    No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.TASK, Operation.UPDATE, tasks)



def gen_query_agent_tasks_by_time_string(query):

    query_string = """
        query MyQuery {
      queryAgentTasks (qm:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{"
        if "byowneruser" in query[i]:
            rec_string = rec_string + "byowneruser: " + str(query[i]['byowneruser']).lower()
        else:
            rec_string = rec_string + "owner: \"" + str(query[i]['owner']).lower() + "\""

        if "created_date_range" in query[i]:
            rec_string = rec_string + ", "
            rec_string = rec_string + "created_date_range: \"" + query[i]['created_date_range'] + "\" }"
        else:
            rec_string = rec_string + "}"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_agent_tasks_string(query):
    query_string = """
        query MyQuery {
      queryAgentTasks (qm:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ mid: " + str(int(query[i]['mid'])) + ", "
        rec_string = rec_string + "ticket: " + str(int(query[i]['ticket'])) + ", "
        rec_string = rec_string + "botid: " + str(int(query[i]['botid'])) + ", "
        rec_string = rec_string + "owner: \"" + query[i]['owner'] + "\", "
        rec_string = rec_string + "skills: \"" + query[i]['skills'] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_get_agent_tasks_string():
    """Generate GraphQL query string for getting all tasks for current user"""
    # Use queryAgentTasks with qb parameter (byowneruser: true to get current user's tasks)
    qb = json.dumps({"byowneruser": True}, ensure_ascii=False).replace('"', '\\"')
    query_string = f'query MyGetAgentTasksQuery {{ queryAgentTasks(qb: "{qb}") }}'
    logger.debug(query_string)
    return query_string


def gen_add_agent_tools_string(tools, test_settings={}):
    """
    Generate GraphQL mutation string for adding tools
    
    Now uses generic GraphQL builder based on Schema
    No hardcoded fields - all fields come from data and Schema mapping
    """
    settings = test_settings if test_settings else {"testmode": False}
    return build_mutation(DataType.TOOL, Operation.ADD, tools, settings)


def gen_remove_agent_tools_string(removeOrders):
    """
    Generate GraphQL mutation string for removing tools
    
    Now uses generic GraphQL builder
    """
    return build_mutation(DataType.TOOL, Operation.DELETE, removeOrders)



def gen_update_agent_tools_string(tools):
    """
    Generate GraphQL mutation string for updating tools
    
    ✅ Now uses generic GraphQL builder based on Schema
    ✅ No hardcoded fields - all fields come from data and Schema mapping
    """
    return build_mutation(DataType.TOOL, Operation.UPDATE, tools)



def gen_query_agent_tools_by_time_string(query):

    query_string = """
        query MyQuery {
      queryAgentToolRelations (qm:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{"
        if "byowneruser" in query[i]:
            rec_string = rec_string + "byowneruser: " + str(query[i]['byowneruser']).lower()
        else:
            rec_string = rec_string + "owner: \"" + str(query[i]['owner']).lower() + "\""

        if "created_date_range" in query[i]:
            rec_string = rec_string + ", "
            rec_string = rec_string + "created_date_range: \"" + query[i]['created_date_range'] + "\" }"
        else:
            rec_string = rec_string + "}"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_agent_tools_string(query):
    query_string = """
        query MyQuery {
      queryAgentToolRelations (qt:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ toolid: " + str(int(query[i]['toolid'])) + ", "
        rec_string = rec_string + "owner: \"" + query[i]['owner'] + "\", "
        rec_string = rec_string + "name: \"" + query[i]['name'] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_get_agent_tools_string():
    """Generate GraphQL query string for getting all tools for current user"""
    # Use queryAgentTools with qb parameter (byowneruser: true to get current user's tools)
    qb = json.dumps({"byowneruser": True}, ensure_ascii=False).replace('"', '\\"')
    query_string = f'query MyGetAgentToolsQuery {{ queryAgentTools(qb: "{qb}") }}'
    logger.debug(query_string)
    return query_string




def gen_add_knowledges_string(knowledges, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(knowledges)):
        if isinstance(knowledges[i], dict):
            rec_string = rec_string + "{ knid:" + str(knowledges[i]["knId"]) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + knowledges[i]["name"] + ", "
            rec_string = rec_string + "description:\"" + knowledges[i]["description"] + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i]["path"] + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i]["status"] + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i]["metadata"].replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i]["rag"] + "\"} "
        else:
            rec_string = rec_string + "{ knid:" + str(knowledges[i].getKnid()) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i].getOwner() + "\", "
            rec_string = rec_string + "name:" + knowledges[i].getName() + ", "
            rec_string = rec_string + "description:\"" + knowledges[i].getDescription() + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i].getPath() + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i].getStatus() + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i].getMetadata().replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i].getRag() + "\"} "

        if i != len(knowledges) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    if len(test_settings) == 0:
        rec_string = rec_string + ", settings: \"{ \\\"testmode\\\": false}\""
    else:
        rec_string = rec_string + ", settings: \"{ \\\"testmode\\\": false}\""


    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_remove_knowledges_string(removeOrders):
    query_string = """
        mutation MyRMMutation {
      removeKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string = rec_string + "{ oid:" + str(removeOrders[i]["id"]) + ", "
        rec_string = rec_string + "owner:\"" + removeOrders[i]["owner"] + "\", "
        rec_string = rec_string + "reason:\"" + removeOrders[i]["reason"] + "\"} "

        if i != len(removeOrders) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_update_knowledges_string(knowledges):
    query_string = """
        mutation MyMutation {
      updateKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(knowledges)):
        if isinstance(knowledges[i], dict):
            rec_string = rec_string + "{ knid:" + str(knowledges[i]["knId"]) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + knowledges[i]["name"] + ", "
            rec_string = rec_string + "description:\"" + knowledges[i]["description"] + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i]["path"] + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i]["status"] + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i]["metadata"].replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i]["rag"] + "\"} "
        else:
            rec_string = rec_string + "{ knid:" + str(knowledges[i].getKnid()) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i].getOwner() + "\", "
            rec_string = rec_string + "name:" + knowledges[i].getName() + ", "
            rec_string = rec_string + "description:\"" + knowledges[i].getDescription() + "\", "
            rec_string = rec_string + "path:\"" + knowledges[i].getPath() + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i].getStatus() + "\", "
            rec_string = rec_string + "metadata:" + knowledges[i].getMetadata().replace('"', '\\"') + ", "
            rec_string = rec_string + "rag:\"" + knowledges[i].getRag() + "\"} "

        if i != len(knowledges) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_query_knowledges_by_time_string(query):

    query_string = """
        query MyQuery {
      queryKnowledges (qk:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{"
        if "byowneruser" in query[i]:
            rec_string = rec_string + "byowneruser: " + str(query[i]['byowneruser']).lower()
        else:
            rec_string = rec_string + "owner: \"" + str(query[i]['owner']).lower() + "\""

        if "created_date_range" in query[i]:
            rec_string = rec_string + ", "
            rec_string = rec_string + "created_date_range: \"" + query[i]['created_date_range'] + "\" }"
        else:
            rec_string = rec_string + "}"

        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_knowledges_string(query):
    query_string = """
        query MyQuery {
      queryKnowledges (qk:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ knid: " + str(int(query[i]['knid'])) + ", "
        rec_string = rec_string + "owner: \"" + query[i]['owner'] + "\", "
        rec_string = rec_string + "name: \"" + query[i]['name'] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ])
        }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string




def gen_get_knowledges_string():
    query_string = 'query MyGetKnowledgesQuery { getKnowledges (ids:"'
    rec_string = "0"

    tail_string = '") }'
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

# 	component_id: ID!
# 	name: String
# 	proj_id: ID!
# 	description: String
# 	category: String
# 	application: String
# 	metadata: AWSJSON
def gen_query_components_string(components):
    query_string = """
            query MyQuery {
          queryComponents (components:[
        """
    rec_string = ""
    for i in range(len(components)):
        rec_string = rec_string + "{ component_id: " + str(components[i]['component_id']) + ", "
        rec_string = rec_string + "name: \"" + components[i]['name'] + "\", "
        rec_string = rec_string + "proj_id: " + str(components[i]['proj_id']) + ", "
        rec_string = rec_string + "description: \"" + components[i]['description'] + "\", "
        rec_string = rec_string + "category: \"" + components[i]['category'] + "\", "
        rec_string = rec_string + "application: \"" + components[i]['application'] + "\", "
        rec_string = rec_string + "metadata: \"" + json.dumps(components[i]['metadata']).replace('"', '\\"') + "\" }"
        if i != len(components) - 1:
            rec_string = rec_string + ', '

    tail_string = """
            ])
            }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string


def gen_query_fom_string(fom_info):
    """Generates a GraphQL query string for the queryFOM mutation, ensuring correct syntax."""

    # Use json.dumps to safely format the list of strings for product_app.
    # This handles quoting and commas automatically, creating a valid JSON array string.
    logger.debug(f"fom_info: {fom_info}")
    product_app_str = json.dumps(fom_info.get('product_app', []))

    # Manually build the string for the 'params' list because GraphQL keys are not quoted.
    params_list = fom_info.get('params', [[]])[0]
    params_str_list = []
    for param in params_list:
        # Escape any double quotes within the values to prevent breaking the query string
        param_name = param.get('name', '').replace('"', '\\"')
        param_ptype = param.get('ptype', '').replace('"', '\\"')
        param_value = param.get('value', '').replace('"', '\\"')

        # Note: GraphQL keys (name, ptype, value) are not quoted in the object definition.
        param_str = f'{{name: "{param_name}", ptype: "{param_ptype}", value: "{param_value}"}}'
        params_str_list.append(param_str)

    # Join the list of parameter strings into a single string like "[{...}, {...}]"
    params_str = f"[{', '.join(params_str_list)}]"

    # Construct the final query using an f-string for clarity and correctness.
    # This is much safer than manual string concatenation.
    query_string = f"""
        query MyQuery {{
          queryFOM(params: {{
            component_name: "{fom_info.get('component_name', '')}",
            product_app: {product_app_str},
            max_product_metrics: {fom_info.get('max_product_metrics', 0)},
            max_component_metrics: {fom_info.get('max_component_metrics', 0)},
            params: {params_str}
          }})
        }}
    """

    logger.debug(f"Generated queryFOM string: {query_string}")
    return query_string




def gen_rank_results_string(rank_data_input):
    """Generate a GraphQL query string for queryRankResults using AWSJSON fields.

    The AppSync schema expects:
      input RankData { fom_form: AWSJSON!, rows: [AWSJSON!], component_info: AWSJSON! }

    Each AWSJSON value must be provided as a JSON string literal in the GraphQL query.
    We accomplish this by double-encoding the Python object: json.dumps(json.dumps(obj)).
    """

    try:
        fom_form = rank_data_input.get("fom_form", {})
        rows = rank_data_input.get("rows", []) or []
        component_info = rank_data_input.get("component_info", {})

        # Double-encode to embed JSON as a GraphQL string literal (AWSJSON)
        fom_form_literal = json.dumps(json.dumps(fom_form))          # => "\"{...}\""
        rows_literals = [json.dumps(json.dumps(r)) for r in rows]    # => ["\"{...}\"", ...]
        rows_array_literal = f"[{', '.join(rows_literals)}]"
        component_info_literal = json.dumps(json.dumps(component_info))

        query_string = f"""
        query MyQuery {{
          queryRankResults(rank_data: {{
            fom_form: {fom_form_literal}
            rows: {rows_array_literal}
            component_info: {component_info_literal}
          }})
        }}
        """


        logger.debug(f"Generated queryRankResults string: {query_string}")
        return query_string
    except Exception as e:
        logger.error(f"Error generating queryRankResults string: {e}\nrank_data_input={rank_data_input}")
        # Fallback minimal query to avoid crash; server will error with useful message
        return "query MyQuery { queryRankResults(rank_data: { fom_form: \"{}\", rows: [], component_info: \"{}\" }) }"




def gen_start_long_llm_task_string(task_input):
    """Generate a GraphQL query string for queryRankResults using AWSJSON fields.

    The AppSync schema expects:
      startLongLLMTask(task_input: AWSJSON!)
      where task_input internally looks like:
      {
        "acct_site_id": "",
        "agent_id": "",
        "work_type": "",
        "task_id": "",
        "task_data": { "fom_form": {...}, "rows": [{...}], "component_info": {...} }
      }

    For AWSJSON, the entire payload must be sent as a JSON string literal, i.e. the
    whole dictionary is double-encoded: json.dumps(json.dumps(task_input)).
    """

    try:
        # Validate and normalize structure
        if not isinstance(task_input, dict):
            raise ValueError("task_input must be a dict")

        payload = {
            "acct_site_id": task_input.get("acct_site_id", ""),
            "agent_id": task_input.get("agent_id", ""),
            "work_type": task_input.get("work_type", ""),
            "task_id": task_input.get("task_id", ""),
            "task_data": task_input.get("task_data", {}) or {}
        }

        # Double-encode so the GraphQL literal is a JSON string (AWSJSON)
        input_literal = json.dumps(json.dumps(payload))

        query_string = f"""
        mutation MyMutation {{
          startLongLLMTask(task_input: {input_literal})
        }}
        """

        logger.debug(f"Generated startLongLLMTask string: {query_string}")
        return query_string
    except Exception as e:
        logger.error(f"Error generating startLongLLMTask string: {e}\ninput={task_input}")
        # Fallback minimal mutation with empty object
        return "mutation MyMutation { startLongLLMTask(task_input: \"{}\") }"





def gen_get_nodes_prompts_string(nodes):
    query_string = """
            query MyQuery {
          getNodesPrompts (nodes:[
        """
    rec_string = ""
    for i in range(len(nodes)):
        rec_string = rec_string + "{ askid: \"" + str(nodes[i]['askid']) + "\", "
        rec_string = rec_string + "name: \"" + nodes[i]['name'] + "\", "
        rec_string = rec_string + "situation: \"" + "" + "\" }"
        if i != len(nodes) - 1:
            rec_string = rec_string + ', '

    tail_string = """
            ])
            }"""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string



def gen_update_agent_tasks_ex_status_string(tasksStats):
    query_string = """
            mutation updateAgentTasksExStatus {
          updateAgentTasksExStatus (input:[
        """
    rec_string = ""
    for i in range(len(tasksStats)):
        if isinstance(tasksStats[i], dict):
            rec_string = rec_string + "{ ataskid:" + str(tasksStats[i]["ataskid"]) + ", "
            rec_string = rec_string + "status:\"" + tasksStats[i]["status"] + "\"}"
        else:
            rec_string = rec_string + "{ mid:" + str(tasksStats[i].getMid()) + ", "
            rec_string = rec_string + "status:\"" + tasksStats[i].getStatus() + "\"} "


        if i != len(tasksStats) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger.debug("DAILY REPORT QUERY STRING:"+query_string)
    return query_string




def send_update_agent_tasks_ex_status_to_cloud(session, tasksStats, token, endpoint):
    if len(tasksStats) > 0:
        query = gen_update_agent_tasks_ex_status_string(tasksStats)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            error_type = jresponse.get("errorType", "Unknown")
            error_msg = jresponse.get("message", str(jresponse))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        else:
            jresponse = json.loads(jresp["data"]["updateAgentTasksExStatus"])
    else:
        logger.error("ERROR Type: EMPTY DAILY REPORTS")
        jresponse = "ERROR: EMPTY REPORTS"
    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_completion_status_to_cloud(session, taskStats, token, endpoint, full=True):
    if len(taskStats) > 0:
        query = gen_daily_update_string(taskStats, full)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            error_type = jresponse.get("errorType", "Unknown")
            error_msg = jresponse.get("message", str(jresponse))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        else:
            jresponse = json.loads(jresp["data"]["reportTaskStatus"])
    else:
        logger.error("ERROR Type: EMPTY DAILY REPORTS")
        jresponse = "ERROR: EMPTY REPORTS"
    return jresponse


# =================================================================================================
# Helper function for safe JSON parsing
def safe_parse_response(jresp, operation_name, data_key):
    """
    Safely parse AppSync response
    
    Args:
        jresp: JSON response from AppSync
        operation_name: Name of the operation (for error messages)
        data_key: Key to extract from response data
        
    Returns:
        Parsed response data
        
    Raises:
        Exception: If response contains errors or returns null
    """
    if "errors" in jresp:
        errors = jresp.get("errors", [])
        error_message = errors[0].get("message", "Unknown error") if errors else "Unknown error"
        logger.error(f"❌ GraphQL Error: {error_message}")
        logger.error(f"📋 Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        raise Exception(f"{operation_name} failed: {error_message}")
    else:
        # Check if data exists and is not None
        data = jresp.get("data", {})
        response_data = data.get(data_key) if data else None
        if response_data is not None:
            return json.loads(response_data)
        else:
            # Null response without errors - this is a server-side issue
            error_msg = f"{operation_name} returned null"
            logger.warning(f"⚠️ {error_msg} (server rejected the request)")
            logger.warning(f"📋 Full response: {json.dumps(jresp, ensure_ascii=False)}")
            logger.debug(f"💡 Possible causes:")
            logger.debug(f"   1. Resource not found (for UPDATE/DELETE)")
            logger.debug(f"   2. Resource already exists (for ADD)")
            logger.debug(f"   3. Data validation failed on server")
            logger.debug(f"   4. Permission denied (check IAM/Cognito)")
            logger.debug(f"   5. Backend timeout or internal error")

# =================================================================================================
# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT, Operation.ADD)
def send_add_agents_request_to_cloud(session, bots, token, endpoint):
    mutationInfo = gen_add_agents_string(bots)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "addAgents", "addAgents")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT, Operation.UPDATE)
def send_update_agents_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_update_agents_string(bots)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgents", "updateAgents")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT, Operation.DELETE)
def send_remove_agents_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_agents_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgents", "removeAgents")




@cloud_api(DataType.AGENT, Operation.QUERY)
def send_query_agents_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agents_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgents", "queryAgents")


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agents_request_to_cloud(session, token, endpoint):
    """Query all agents for current user using queryAgents with byowneruser"""
    queryInfo = gen_get_agents_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        logger.error("AppSync queryAgents error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agents data found for user - returning empty list")
            jresponse = []
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            agents_data = jresp["data"]["queryAgents"]
            if agents_data is None:
                logger.info("queryAgents returned null - user has no agents data")
                jresponse = []
            else:
                # Return type is now [Agent!]! - already a list of dicts, no json.loads needed
                jresponse = agents_data
        except (KeyError, TypeError) as e:
            logger.error(f"Failed to parse queryAgents response: {e}")
            jresponse = []

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_SKILL, Operation.ADD)
def send_add_agent_skill_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_SKILL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentSkillRelations", "addAgentSkillRelations")


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_SKILL, Operation.UPDATE)
def send_update_agent_skill_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_SKILL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "updateAgentSkillRelations", "updateAgentSkillRelations")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_SKILL, Operation.DELETE)
def send_remove_agent_skill_relations_request_to_cloud(session, removes, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "removeAgentSkillRelations", "removeAgentSkillRelations")


@cloud_api(DataType.AGENT_SKILL, Operation.QUERY)
def send_query_agent_skill_relations_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_agent_skills_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentSkillRelations", "queryAgentSkillRelations")


# ============================================================================
# Skill Entity Operations
# ============================================================================

@cloud_api(DataType.SKILL, Operation.ADD)
def send_add_skills_request_to_cloud(session, skills, token, endpoint, timeout=180):
    """Add Skill entities (skill data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.SKILL, Operation.ADD, skills)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentSkills", "addAgentSkills")


@cloud_api(DataType.SKILL, Operation.UPDATE)
def send_update_skills_request_to_cloud(session, skills, token, endpoint):
    """Update Skill entities (skill data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.SKILL, Operation.UPDATE, skills)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentSkills", "updateAgentSkills")


@cloud_api(DataType.SKILL, Operation.DELETE)
def send_remove_skills_request_to_cloud(session, removes, token, endpoint):
    """Remove Skill entities (skill data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentSkills", "removeAgentSkills")


# ============================================================================
# Skill File Upload Utilities
# ============================================================================

def collect_skill_files(skill_directory: str) -> list:
    """
    Recursively collect all files under the skill directory.
    
    Args:
        skill_directory: Absolute path to the skill directory
        
    Returns:
        List of relative file paths (relative to skill_directory)
    """
    import glob
    
    if not os.path.isdir(skill_directory):
        logger.warning(f"[SkillFiles] Skill directory not found: {skill_directory}")
        return []
    
    all_files = []
    for root, dirs, files in os.walk(skill_directory):
        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, skill_directory)
            # Normalize path separators to forward slashes
            rel_path = rel_path.replace("\\", "/")
            all_files.append(rel_path)
    
    logger.debug(f"[SkillFiles] Collected {len(all_files)} files from {skill_directory}")
    return all_files


def build_skill_source_string(file_paths: list) -> str:
    """
    Build comma-separated source string from file paths.
    
    Args:
        file_paths: List of relative file paths
        
    Returns:
        Comma-separated string of file paths
    """
    return ",".join(file_paths)


def prepare_skill_with_source(skill_data: dict, skill_directory: str = None) -> dict:
    """
    Prepare skill data with source attribute containing file paths.
    
    Args:
        skill_data: Original skill data dictionary
        skill_directory: Path to skill directory (if None, uses skill_data['path'])
        
    Returns:
        Skill data with 'source' attribute populated
    """
    skill = skill_data.copy()
    
    # Determine skill directory
    if skill_directory is None:
        skill_directory = skill.get('path', '')
    
    if skill_directory and os.path.isdir(skill_directory):
        # Collect all files recursively
        file_paths = collect_skill_files(skill_directory)
        # Build source string
        skill['source'] = build_skill_source_string(file_paths)
        logger.info(f"[SkillFiles] Prepared skill with {len(file_paths)} files in source")
    else:
        skill['source'] = skill.get('source', '')
        logger.debug(f"[SkillFiles] No valid skill directory, using existing source: {skill['source'][:100]}...")
    
    return skill


def upload_skill_files_with_presigned_urls(
    session, 
    skill_directory: str, 
    presigned_urls: list, 
    file_paths: list
) -> dict:
    """
    Upload skill files using presigned URLs returned from cloud.
    
    Args:
        session: Requests session
        skill_directory: Absolute path to skill directory
        presigned_urls: List of presigned URL objects from cloud response
        file_paths: List of relative file paths (matching order with presigned_urls)
        
    Returns:
        Dict with upload results: {'success': [...], 'failed': [...]}
    """
    results = {'success': [], 'failed': []}
    
    if len(presigned_urls) != len(file_paths):
        logger.warning(f"[SkillUpload] Mismatch: {len(presigned_urls)} URLs vs {len(file_paths)} files")
    
    for i, (url_info, rel_path) in enumerate(zip(presigned_urls, file_paths)):
        abs_path = os.path.join(skill_directory, rel_path)
        
        if not os.path.isfile(abs_path):
            logger.warning(f"[SkillUpload] File not found: {abs_path}")
            results['failed'].append({'path': rel_path, 'error': 'File not found'})
            continue
        
        try:
            # Upload using presigned URL
            resp = send_file_with_presigned_url(abs_path, url_info)
            results['success'].append({'path': rel_path, 'response': resp})
            logger.debug(f"[SkillUpload] Uploaded {rel_path}")
        except Exception as e:
            logger.error(f"[SkillUpload] Failed to upload {rel_path}: {e}")
            results['failed'].append({'path': rel_path, 'error': str(e)})
    
    logger.info(f"[SkillUpload] Upload complete: {len(results['success'])} success, {len(results['failed'])} failed")
    return results


def send_add_skills_with_files_to_cloud(
    session, 
    skills: list, 
    token: str, 
    endpoint: str, 
    timeout: int = 180
) -> dict:
    """
    Add skills to cloud with file upload support.
    
    This function:
    1. Prepares each skill with source attribute (comma-separated file paths)
    2. Sends add request to cloud
    3. Parses presigned URLs from response
    4. Uploads files using presigned URLs
    
    Args:
        session: Requests session
        skills: List of skill data dicts (each should have 'path' pointing to skill directory)
        token: Auth token
        endpoint: AppSync endpoint
        timeout: Request timeout
        
    Returns:
        Dict with cloud response and file upload results
    """
    from agent.cloud_api.graphql_builder import build_mutation
    
    # Step 1: Prepare skills with source attribute
    prepared_skills = []
    skill_file_map = {}  # Map skill ID to file paths for later upload
    
    for skill in skills:
        skill_dir = skill.get('path', '')
        prepared_skill = prepare_skill_with_source(skill, skill_dir)
        prepared_skills.append(prepared_skill)
        
        # Store file paths for upload
        skill_id = prepared_skill.get('askid') or prepared_skill.get('id', '')
        if skill_dir and os.path.isdir(skill_dir):
            skill_file_map[skill_id] = {
                'directory': skill_dir,
                'files': collect_skill_files(skill_dir)
            }
    
    # Step 2: Send add request to cloud
    mutationInfo = build_mutation(DataType.SKILL, Operation.ADD, prepared_skills)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    cloud_response = safe_parse_response(jresp, "addAgentSkills", "addAgentSkills")
    
    # Step 3: Parse presigned URLs and upload files
    upload_results = {}
    
    if isinstance(cloud_response, dict) and 'presigned_urls' in cloud_response:
        # Cloud returned presigned URLs for file uploads
        for skill_id, url_list in cloud_response.get('presigned_urls', {}).items():
            if skill_id in skill_file_map:
                skill_info = skill_file_map[skill_id]
                upload_result = upload_skill_files_with_presigned_urls(
                    session,
                    skill_info['directory'],
                    url_list,
                    skill_info['files']
                )
                upload_results[skill_id] = upload_result
    elif isinstance(cloud_response, dict) and 'body' in cloud_response:
        # Alternative response format with body containing URLs
        body = cloud_response.get('body', {})
        if isinstance(body, dict) and 'urls' in body:
            urls_data = body.get('urls', {})
            if isinstance(urls_data, dict) and 'result' in urls_data:
                try:
                    url_result = json.loads(urls_data['result']) if isinstance(urls_data['result'], str) else urls_data['result']
                    if 'body' in url_result and isinstance(url_result['body'], list):
                        # Upload files for each skill
                        for skill_id, skill_info in skill_file_map.items():
                            upload_result = upload_skill_files_with_presigned_urls(
                                session,
                                skill_info['directory'],
                                url_result['body'],
                                skill_info['files']
                            )
                            upload_results[skill_id] = upload_result
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"[SkillUpload] Failed to parse presigned URLs: {e}")
    
    return {
        'cloud_response': cloud_response,
        'upload_results': upload_results,
        'skills_processed': len(prepared_skills)
    }


def send_update_skills_with_files_to_cloud(
    session, 
    skills: list, 
    token: str, 
    endpoint: str, 
    timeout: int = 180
) -> dict:
    """
    Update skills in cloud with file upload support.
    
    Similar to send_add_skills_with_files_to_cloud but for updates.
    
    Args:
        session: Requests session
        skills: List of skill data dicts
        token: Auth token
        endpoint: AppSync endpoint
        timeout: Request timeout
        
    Returns:
        Dict with cloud response and file upload results
    """
    from agent.cloud_api.graphql_builder import build_mutation
    
    # Step 1: Prepare skills with source attribute
    prepared_skills = []
    skill_file_map = {}
    
    for skill in skills:
        skill_dir = skill.get('path', '')
        prepared_skill = prepare_skill_with_source(skill, skill_dir)
        prepared_skills.append(prepared_skill)
        
        skill_id = prepared_skill.get('askid') or prepared_skill.get('id', '')
        if skill_dir and os.path.isdir(skill_dir):
            skill_file_map[skill_id] = {
                'directory': skill_dir,
                'files': collect_skill_files(skill_dir)
            }
    
    # Step 2: Send update request to cloud
    mutationInfo = build_mutation(DataType.SKILL, Operation.UPDATE, prepared_skills)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    cloud_response = safe_parse_response(jresp, "updateAgentSkills", "updateAgentSkills")
    
    # Step 3: Parse presigned URLs and upload files
    upload_results = {}
    
    if isinstance(cloud_response, dict) and 'presigned_urls' in cloud_response:
        for skill_id, url_list in cloud_response.get('presigned_urls', {}).items():
            if skill_id in skill_file_map:
                skill_info = skill_file_map[skill_id]
                upload_result = upload_skill_files_with_presigned_urls(
                    session,
                    skill_info['directory'],
                    url_list,
                    skill_info['files']
                )
                upload_results[skill_id] = upload_result
    elif isinstance(cloud_response, dict) and 'body' in cloud_response:
        body = cloud_response.get('body', {})
        if isinstance(body, dict) and 'urls' in body:
            urls_data = body.get('urls', {})
            if isinstance(urls_data, dict) and 'result' in urls_data:
                try:
                    url_result = json.loads(urls_data['result']) if isinstance(urls_data['result'], str) else urls_data['result']
                    if 'body' in url_result and isinstance(url_result['body'], list):
                        for skill_id, skill_info in skill_file_map.items():
                            upload_result = upload_skill_files_with_presigned_urls(
                                session,
                                skill_info['directory'],
                                url_result['body'],
                                skill_info['files']
                            )
                            upload_results[skill_id] = upload_result
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"[SkillUpload] Failed to parse presigned URLs: {e}")
    
    return {
        'cloud_response': cloud_response,
        'upload_results': upload_results,
        'skills_processed': len(prepared_skills)
    }


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_skills_request_to_cloud(session, token, endpoint):
    """Query all skills for current user using queryAgentSkills
    
    Server returns [AgentSkill!]! - an array of skill objects (not AWSJSON)
    """
    queryInfo = gen_get_agent_skills_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        logger.error("AppSync queryAgentSkills error: " + json.dumps(jresp))
        # Handle case where user has no agent skills data (return empty list)
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agent skills data found for user - returning empty list")
            jresponse = []
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        # Response is already parsed as array of objects (not AWSJSON string)
        skills_data = jresp.get("data", {}).get("queryAgentSkills")
        if skills_data is None:
            logger.info("queryAgentSkills returned null - user has no agent skills data")
            jresponse = []
        else:
            # skills_data is already a list of dicts, no json.loads needed
            jresponse = skills_data

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_TASK, Operation.ADD)
def send_add_agent_task_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TASK, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTaskRelations", "addAgentTaskRelations")


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_TASK, Operation.UPDATE)
def send_update_agent_task_relations_request_to_cloud(session, relations, token, endpoint):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TASK, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentTaskRelations", "updateAgentTaskRelations")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_TASK, Operation.DELETE)
def send_remove_agent_task_relations_request_to_cloud(session, removes, token, endpoint):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TASK, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentTaskRelations", "removeAgentTaskRelations")



@cloud_api(DataType.AGENT_TASK, Operation.QUERY)
def send_query_agent_task_relations_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_agent_tasks_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTaskRelations", "queryAgentTaskRelations")


# ============================================================================
# Task Entity Operations
# ============================================================================

@cloud_api(DataType.TASK, Operation.ADD)
def send_add_tasks_request_to_cloud(session, tasks, token, endpoint, timeout=180):
    """Add Task entities (task data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TASK, Operation.ADD, tasks)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTasks", "addAgentTasks")


@cloud_api(DataType.TASK, Operation.UPDATE)
def send_update_tasks_request_to_cloud(session, tasks, token, endpoint):
    """Update Task entities (task data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TASK, Operation.UPDATE, tasks)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentTasks", "updateAgentTasks")


@cloud_api(DataType.TASK, Operation.DELETE)
def send_remove_tasks_request_to_cloud(session, removes, token, endpoint):
    """Remove Task entities (task data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TASK, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentTasks", "removeAgentTasks")


def send_query_agent_tasks_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_agent_tasks_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            error = jresp["errors"][0] if jresp["errors"] else {}
            error_type = error.get("errorType", "Unknown")
            error_msg = error.get("message", str(error))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = error
        else:
            jresponse = json.loads(jresp["data"]["queryAgentTaskRelations"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryAgentTasksByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryAgentTasksByTime traceback information not available:" + str(e)
        logger.error(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tasks_request_to_cloud(session, token, endpoint):
    """Query all tasks for current user using queryAgentTasks with byowneruser"""
    queryInfo = gen_get_agent_tasks_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        logger.error("AppSync queryAgentTasks error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agent tasks data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            tasks_data = jresp["data"]["queryAgentTasks"]
            if tasks_data is None:
                logger.info("queryAgentTasks returned null - user has no agent tasks data")
                jresponse = {}
            else:
                jresponse = json.loads(tasks_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse queryAgentTasks response: {e}")
            jresponse = {}

    return jresponse



@cloud_api(DataType.AGENT_TOOL, Operation.ADD)
def send_add_agent_tool_relations_request_to_cloud(session, relations, token, endpoint, timeout=180):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TOOL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentToolRelations", "addAgentToolRelations")


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_TOOL, Operation.UPDATE)
def send_update_agent_tool_relations_request_to_cloud(session, relations, token, endpoint):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TOOL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentToolRelations", "updateAgentToolRelations")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
@cloud_api(DataType.AGENT_TOOL, Operation.DELETE)
def send_remove_agent_tool_relations_request_to_cloud(session, removes, token, endpoint):
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.AGENT_TOOL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentToolRelations", "removeAgentToolRelations")



@cloud_api(DataType.AGENT_TOOL, Operation.QUERY)
def send_query_agent_tool_relations_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_agent_tools_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentToolRelations", "queryAgentToolRelations")


# ============================================================================
# Tool Entity Operations
# ============================================================================

@cloud_api(DataType.TOOL, Operation.ADD)
def send_add_tools_request_to_cloud(session, tools, token, endpoint, timeout=180):
    """Add Tool entities (tool data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TOOL, Operation.ADD, tools)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout)
    return safe_parse_response(jresp, "addAgentTools", "addAgentTools")


@cloud_api(DataType.TOOL, Operation.UPDATE)
def send_update_tools_request_to_cloud(session, tools, token, endpoint):
    """Update Tool entities (tool data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TOOL, Operation.UPDATE, tools)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateAgentTools", "updateAgentTools")


@cloud_api(DataType.TOOL, Operation.DELETE)
def send_remove_tools_request_to_cloud(session, removes, token, endpoint):
    """Remove Tool entities (tool data: name, description, etc.)"""
    from agent.cloud_api.graphql_builder import build_mutation
    from agent.cloud_api.constants import Operation
    mutationInfo = build_mutation(DataType.TOOL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeAgentTools", "removeAgentTools")


def send_query_agent_tools_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_agent_tools_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            error = jresp["errors"][0] if jresp["errors"] else {}
            error_type = error.get("errorType", "Unknown")
            error_msg = error.get("message", str(error))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = error
        else:
            jresponse = json.loads(jresp["data"]["queryAgentToolRelations"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryAgentToolsByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryAgentToolsByTime traceback information not available:" + str(e)
        logger.error(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tools_request_to_cloud(session, token, endpoint):
    """Query all tools for current user using queryAgentTools with byowneruser"""
    queryInfo = gen_get_agent_tools_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        logger.error("AppSync queryAgentTools error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agent tools data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            tools_data = jresp["data"]["queryAgentTools"]
            if tools_data is None:
                logger.info("queryAgentTools returned null - user has no agent tools data")
                jresponse = {}
            else:
                jresponse = json.loads(tools_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse queryAgentTools response: {e}")
            jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_knowledges_request_to_cloud(session, tasks, token, endpoint):
    mutationInfo = gen_add_knowledges_string(tasks)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "addKnowledges", "addKnowledges")


def send_update_knowledges_request_to_cloud(session, vehicles, token, endpoint):
    mutationInfo = gen_update_knowledges_string(vehicles)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "updateknowledges", "updateknowledges")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_knowledges_request_to_cloud(session, removes, token, endpoint):
    mutationInfo = gen_remove_knowledges_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)
    return safe_parse_response(jresp, "removeKnowledges", "removeKnowledges")


def send_query_knowledges_request_to_cloud(session, token, q_settings, endpoint):
    queryInfo = gen_query_knowledges_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryKnowledges", "queryKnowledges")



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_knowledges_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_knowledges_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("AppSync getKnowledges error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No knowledges data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            knowledges_data = jresp["data"]["getKnowledges"]
            if knowledges_data is None:
                logger.info("getKnowledges returned null - user has no knowledges data")
                jresponse = {}
            else:
                jresponse = json.loads(knowledges_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse getKnowledges response: {e}")
            jresponse = {}

    return jresponse


def send_query_components_request_to_cloud(session, token, components, endpoint):

    queryInfo = gen_query_components_string(components)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_query_components_request_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
        logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        jresponse = error
    else:
        jresponse = json.loads(jresp["data"]["queryComponents"])

    return jresponse



def send_query_fom_request_to_cloud(session, token, fom_info, endpoint):
    try:
        queryInfo = gen_query_fom_string(fom_info)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)
        logger.debug("send_query_fom_request_to_cloud, response:", jresp)
        if "errors" in jresp:
            screen_error = True
            error = jresp["errors"][0] if jresp["errors"] else {}
            error_type = error.get("errorType", "Unknown")
            error_msg = error.get("message", str(error))
            logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
            logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
            jresponse = error
        else:
            jresponse = json.loads(jresp["data"]["queryFOM"])
        logger.debug(f"{jresponse}")
    except Exception as e:
        err_msg = get_traceback(e, "ErrorSendQueryFOMRequestToCloud")
        logger.error(f"{err_msg}")
        jresponse = err_msg

    return jresponse



def send_rank_results_request_to_cloud(session, token, rank_data_inut, endpoint):

    queryInfo = gen_rank_results_string(rank_data_inut)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_query_rank_results_request_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
        logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        jresponse = error
    else:
        jresponse = json.loads(jresp["data"]["queryRankResults"])

    return jresponse


def send_get_nodes_prompts_request_to_cloud(session, token, nodes, endpoint):

    queryInfo = gen_get_nodes_prompts_string(nodes)
    logger.debug("send_get_nodes_prompts_request_to_cloud sending: ", queryInfo)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_get_nodes_prompts_request_to_cloud jresp: ", jresp)
    if "errors" in jresp:
        screen_error = True
        error_msg = f"ERROR Type: {jresp['errors'][0]['errorType']} ERROR Info: {jresp['errors'][0]['message']}"
        logger.error(error_msg)
        # 返回错误信息而不是抛出异常，让调用者处理
        return {"errors": jresp["errors"], "body": None}
    else:
        try:
            jresponse = json.loads(jresp["data"]["getNodesPrompts"])
            return {"body": json.dumps({"data": jresponse})}
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing response: {e}")
            return {"errors": [{"errorType": "ParseError", "message": str(e)}], "body": None}


def send_start_long_llm_task_to_cloud(session, token, rank_data_inut, endpoint):

    queryInfo = gen_start_long_llm_task_string(rank_data_inut)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_start_long_llm_task_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        error = jresp["errors"][0] if jresp["errors"] else {}
        error_type = error.get("errorType", "Unknown")
        error_msg = error.get("message", str(error))
        logger.error(f"ERROR Type: {error_type}, ERROR Info: {error_msg}")
        logger.error(f"Full error response: {json.dumps(jresp, ensure_ascii=False)}")
        jresponse = error
    else:
        jresponse = json.loads(jresp["data"]["startLongLLMTask"])

    return jresponse


def convert_cloud_result_to_task_send_params(result_obj: dict, work_type: str) -> dict:
    """
    Convert cloud API result object to TaskSendParams-compatible format for _build_resume_payload().
    
    Args:
        result_obj: The result object from cloud API containing taskID, results, etc.
        work_type: The type of work being performed (e.g., "rerank_search_results")
        
    Returns:
        dict: A dictionary in TaskSendParams format that can be consumed by _build_resume_payload()
    """
    try:
        # Extract key fields from result_obj
        task_id = result_obj.get("taskID", "")
        results = result_obj.get("results", {})
        
        # Create the message structure compatible with TaskSendParams
        # For now, message is None as requested
        message = None
        
        # Create metadata with required fields
        metadata = {
            "i_tag": task_id,  # Use taskID as the interrupt tag
            "notification_to_agent": results  # Use results as notification data
        }
        
        # Handle different work types
        if work_type == "rerank_search_results":
            # For rerank_search_results, we may need additional processing
            # but for now we'll use the basic structure
            pass
        # Add more work_type handling here as needed
        
        # Create the TaskSendParams-like structure with params wrapper
        # The _build_resume_payload expects msg to have either direct fields or params.field structure
        task_send_params = {
            "id": task_id,
            "params": {
                "id": task_id,
                "message": message,
                "metadata": metadata
            },
            "message": message,
            "metadata": metadata
        }
        
        logger.debug(f"Converted cloud result to TaskSendParams format: {json.dumps(task_send_params, indent=2)}")
        return task_send_params
        
    except Exception as e:
        logger.error(f"Error converting cloud result to TaskSendParams: {e}")
        # Return minimal structure on error with params wrapper
        task_id = result_obj.get("taskID", "")
        metadata = {
            "i_tag": task_id,
            "notification_to_agent": {}
        }
        return {
            "id": task_id,
            "params": {
                "id": task_id,
                "message": None,
                "metadata": metadata
            },
            "message": None,
            "metadata": metadata
        }


# ============================================================================
# SCENE GENERATION API FUNCTIONS
# ============================================================================

def gen_req_scene_mutation_string(scene_input: dict) -> str:
    """
    Generate GraphQL mutation string for requesting scene generation.
    
    Args:
        scene_input: Dict with keys: acctSiteID, agent_id, emotion, mind_state, 
                     description, style, output_format, duration_hint_ms, context
    """
    # Escape strings for GraphQL
    def escape_str(s):
        if s is None:
            return "null"
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    acct_site_id = escape_str(scene_input.get("acctSiteID"))
    agent_id = escape_str(scene_input.get("agent_id"))
    emotion = escape_str(scene_input.get("emotion"))
    mind_state = escape_str(scene_input.get("mind_state"))
    description = escape_str(scene_input.get("description"))
    style = scene_input.get("style", "ANIME")  # Enum, no quotes
    output_format = scene_input.get("output_format", "WEBM")  # Enum, no quotes
    duration_hint_ms = scene_input.get("duration_hint_ms")
    context = scene_input.get("context")
    
    # Build context JSON string if provided
    context_str = "null"
    if context:
        context_str = '"' + json.dumps(context).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    duration_str = str(duration_hint_ms) if duration_hint_ms else "null"
    
    mutation_string = f"""
        mutation ReqScene {{
          reqScene(input: {{
            acctSiteID: {acct_site_id}
            agent_id: {agent_id}
            emotion: {emotion}
            mind_state: {mind_state}
            description: {description}
            style: {style}
            output_format: {output_format}
            duration_hint_ms: {duration_str}
            context: {context_str}
          }}) {{
            request_id
            status
            message
            estimated_time_ms
          }}
        }}
    """
    logger_helper.debug(f"[Scene] Generated reqScene mutation: {mutation_string}")
    return mutation_string


def gen_query_scene_string(scene_id: str) -> str:
    """Generate GraphQL query string for getting a scene by ID."""
    query_string = f"""
        query GetScene {{
          getScene(id: "{scene_id}") {{
            id
            acctSiteID
            scene_id
            agent_ids
            label
            clip
            n_repeat
            priority
            captions
            trigger_events
            description
            dialogs
            actions
            duration_ms
            timestamp
            status
          }}
        }}
    """
    return query_string


def gen_query_scenes_string(query_input: dict) -> str:
    """
    Generate GraphQL query string for querying scenes with filters.
    
    Args:
        query_input: Dict with keys: acctSiteID, agent_id, label, emotion, status, limit, nextToken
    """
    def escape_str(s):
        if s is None:
            return "null"
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    acct_site_id = escape_str(query_input.get("acctSiteID"))
    agent_id = escape_str(query_input.get("agent_id")) if query_input.get("agent_id") else "null"
    label = escape_str(query_input.get("label")) if query_input.get("label") else "null"
    emotion = escape_str(query_input.get("emotion")) if query_input.get("emotion") else "null"
    status = query_input.get("status") if query_input.get("status") else "null"  # Enum
    limit = query_input.get("limit", 20)
    next_token = escape_str(query_input.get("nextToken")) if query_input.get("nextToken") else "null"
    
    query_string = f"""
        query QueryScenes {{
          queryScenes(input: {{
            acctSiteID: {acct_site_id}
            agent_id: {agent_id}
            label: {label}
            emotion: {emotion}
            status: {status}
            limit: {limit}
            nextToken: {next_token}
          }}) {{
            items {{
              id
              acctSiteID
              scene_id
              agent_ids
              label
              clip
              n_repeat
              priority
              captions
              description
              timestamp
              status
            }}
            nextToken
          }}
        }}
    """
    return query_string


def gen_start_soap_mutation_string(soap_input: dict) -> str:
    """
    Generate GraphQL mutation string for starting a soap opera.
    
    Args:
        soap_input: Dict with keys: acctSiteID, agent_ids, theme, mood, settings
    """
    def escape_str(s):
        if s is None:
            return "null"
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    acct_site_id = escape_str(soap_input.get("acctSiteID"))
    agent_ids = soap_input.get("agent_ids", [])
    agent_ids_str = "[" + ", ".join([f'"{aid}"' for aid in agent_ids]) + "]"
    theme = escape_str(soap_input.get("theme"))
    mood = escape_str(soap_input.get("mood"))
    settings = soap_input.get("settings")
    settings_str = "null"
    if settings:
        settings_str = '"' + json.dumps(settings).replace('\\', '\\\\').replace('"', '\\"') + '"'
    
    mutation_string = f"""
        mutation StartSoap {{
          startSoap(input: {{
            acctSiteID: {acct_site_id}
            agent_ids: {agent_ids_str}
            theme: {theme}
            mood: {mood}
            settings: {settings_str}
          }}) {{
            soap_id
            status
            message
          }}
        }}
    """
    return mutation_string


def send_req_scene_to_cloud(session, scene_input: dict, token: str, endpoint: str) -> dict:
    """
    Send a scene generation request to the cloud.
    
    Args:
        session: HTTP session
        scene_input: Scene generation parameters
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        dict with request_id, status, message, estimated_time_ms or error info
    """
    mutation_string = gen_req_scene_mutation_string(scene_input)
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] reqScene response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("reqScene", {})


def send_get_scene_to_cloud(session, scene_id: str, token: str, endpoint: str) -> dict:
    """
    Get a scene by ID from the cloud.
    
    Args:
        session: HTTP session
        scene_id: Scene ID to retrieve
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        Scene object or error info
    """
    query_string = gen_query_scene_string(scene_id)
    
    jresp = appsync_http_request(query_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] getScene response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("getScene", {})


def send_query_scenes_to_cloud(session, query_input: dict, token: str, endpoint: str) -> dict:
    """
    Query scenes with filters from the cloud.
    
    Args:
        session: HTTP session
        query_input: Query parameters (acctSiteID, agent_id, label, etc.)
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        dict with items list and nextToken, or error info
    """
    query_string = gen_query_scenes_string(query_input)
    
    jresp = appsync_http_request(query_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] queryScenes response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("queryScenes", {})


def send_start_soap_to_cloud(session, soap_input: dict, token: str, endpoint: str) -> dict:
    """
    Start a soap opera (continuous story generation) on the cloud.
    
    Args:
        session: HTTP session
        soap_input: Soap parameters (acctSiteID, agent_ids, theme, mood, settings)
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        dict with soap_id, status, message or error info
    """
    mutation_string = gen_start_soap_mutation_string(soap_input)
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] startSoap response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return {"errorType": error_type, "message": error_msg}
    else:
        return jresp.get("data", {}).get("startSoap", {})


def send_stop_soap_to_cloud(session, soap_id: str, token: str, endpoint: str) -> bool:
    """
    Stop a running soap opera.
    
    Args:
        session: HTTP session
        soap_id: Soap ID to stop
        token: Auth token
        endpoint: API endpoint
        
    Returns:
        True if successful, False otherwise
    """
    mutation_string = f"""
        mutation StopSoap {{
          stopSoap(soap_id: "{soap_id}")
        }}
    """
    
    jresp = appsync_http_request(mutation_string, session, token, endpoint)
    
    logger_helper.debug(f"[Scene] stopSoap response: {json.dumps(jresp)}")
    if "errors" in jresp:
        error_obj = jresp["errors"][0]
        error_type = error_obj.get("errorType", error_obj.get("type", "Unknown"))
        error_msg = error_obj.get("message", str(error_obj))
        logger_helper.error(f"[Scene] ERROR Type: {error_type} ERROR Info: {error_msg}")
        return False
    else:
        return jresp.get("data", {}).get("stopSoap", False)


# related to websocket sub/push to get long running task results
def subscribe_cloud_llm_task(acctSiteID: str, id_token: str, ws_url: Optional[str] = None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    from agent.agent_service import get_agent_by_id
    """Subscribe to long-running LLM task updates over WebSocket.

    Parameters:
        acctSiteID: Account/site identifier used by the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
    """

    def on_message(ws, message):
        logger.debug("[CloudLLMTask] Received WebSocket message")
        try:
            data = json.loads(message)
        except Exception:
            data = {"raw": message}
        logger.debug("[CloudLLMTask] Subscription update: %s", json.dumps(data, indent=2))
        # Determine message type for protocol handling
        msg_type = data.get("type")

        if msg_type == "connection_ack":
            # After ack, start the subscription (AppSync format: data + extensions.authorization)
            try:
                # Match updated schema: requires acctSiteID variable
                subscription = (
                    """
                    subscription OnComplete($acctSiteID: String!) {
                      onLongLLMTaskComplete(acctSiteID: $acctSiteID) {
                        id
                        acctSiteID
                        agentID
                        workType
                        taskID
                        status
                        results
                        timestamp
                      }
                    }
                    """
                )
                data_obj = {
                    "query": subscription,
                    "operationName": "OnComplete",
                    "variables": {"acctSiteID": acctSiteID},
                }
                start_payload = {
                    "id": "LongLLM1",
                    "type": "start",
                    "payload": {
                        "data": json.dumps(data_obj),
                        "extensions": {
                            "authorization": {
                                "host": api_host,
                                "Authorization": id_token,
                            }
                        },
                    },
                }
                logger.info("[CloudLLMTask] connection_ack received, sending start subscription", start_payload)
                ws.send(json.dumps(start_payload))
            except Exception as e:
                logger.error(f"[CloudLLMTask] Failed to send start payload: {e}")

        elif msg_type in ("ka", "keepalive"):
            # Keep-alive from server; no action required
            return
        elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "LongLLM1":
            # Extract structured object result per schema
            payload_data = data.get("payload", {}).get("data", {})
            result_obj = None
            if isinstance(payload_data, dict):
                result_obj = payload_data.get("onLongLLMTaskComplete")
                logger.debug(f"Received long LLM Task subscription result:{json.dumps(result_obj, indent=2, ensure_ascii=False)}")
                # now we can send result_obj to resume the pending workflow.
                # which msg queue should this be put into? (agent should maintain some kind of cloud_task_id to agent_task_queue LUT)
                agent_id = result_obj["agentID"]
                work_type = result_obj["workType"]
                handler_agent = get_agent_by_id(agent_id)
                # Convert cloud result to TaskSendParams format for _build_resume_payload()
                converted_result = convert_cloud_result_to_task_send_params(result_obj, work_type)
                # event_response = handler_agent.runner.sync_task_wait_in_line(work_type, converted_result)
                event_response = handler_agent.runner.sync_task_wait_in_line(work_type, converted_result, source="cloud_websocket")

    def on_error(ws, error):
        logger.error(f"[CloudLLMTask] WebSocket error: {error}")

    def on_close(ws, status_code, msg):
        logger.warning(f"[CloudLLMTask] WebSocket closed: code={status_code}, msg={msg}")

    def on_open(ws):
        logger_helper.debug("CloudLLMTask web socket opened.......")
        init_payload = {
            "type": "connection_init",
            "payload": {}
        }
        try:
            logger_helper.debug("CloudLLMTask sending connection_init ...")
            ws.send(json.dumps(init_payload))
        except Exception as e:
            logger.error(f"[CloudLLMTask] Failed to send connection_init: {e}")

    # Resolve WS URL and ensure it's the AppSync realtime endpoint
    if not ws_url:
        ws_url = os.getenv("ECAN_WS_URL", "")
    if not ws_url:
        logger_helper.warning(
            "Warning: WebSocket URL not provided and ECAN_WS_URL is not set. Cloud LLM subscription will be disabled.")
        raise ValueError("WebSocket URL not provided and ECAN_WS_URL is not set")

    if ws_url.startswith("https://") and "appsync-api" in ws_url:
        try:
            prefix = "https://"
            rest = ws_url[len(prefix):]
            rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
            ws_url = "wss://" + rest
            logger_helper.info(f"Converted to realtime endpoint: {ws_url}")
        except Exception:
            pass

    parsed = urlparse(ws_url)
    api_host = parsed.netloc.replace("appsync-realtime-api", "appsync-api")
    header_obj = {
        "host": api_host,
        "Authorization": id_token,
    }
    payload_obj = {}
    header_b64 = base64.b64encode(json.dumps(header_obj).encode("utf-8")).decode("utf-8")
    payload_b64 = base64.b64encode(json.dumps(payload_obj).encode("utf-8")).decode("utf-8")

    query = dict(parse_qsl(parsed.query))
    query.update({
        "header": header_b64,
        "payload": payload_b64,
    })
    signed_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query),
        parsed.fragment,
    ))

    logger.debug("[CloudAPI] ws_url ok")
    headers = []

    logger.debug("[CloudAPI] token seems to be ok")

    ws = websocket.WebSocketApp(
        signed_url,
        header=headers,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
        subprotocols=["graphql-ws"],
    )

    logger.info("[CloudLLMTask] Launching web socket thread")
    # Configure SSL options to handle certificate verification issues
    import ssl
    ssl_context = ssl.create_default_context()
    # For development/testing, you might want to disable certificate verification
    # ssl_context.check_hostname = False
    # ssl_context.verify_mode = ssl.CERT_NONE

    t = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
    t.start()
    logger.info("[CloudLLMTask] Web socket thread launched")
    return ws, t


# ============================================================================
# Account Notification Subscription (WebSocket)
# ============================================================================

def subscribe_account_notifications(owner: str, id_token: str, ws_url: Optional[str] = None, 
                                     on_notification_callback=None) -> Tuple[websocket.WebSocketApp, threading.Thread]:
    """Subscribe to account notifications over WebSocket.

    Parameters:
        owner: Owner email/identifier for the subscription filter.
        id_token: Cognito/AppSync ID token (Authorization header).
        ws_url: Optional AppSync GraphQL endpoint; if https, auto-converted to realtime wss.
        on_notification_callback: Optional callback function(notification_data) to handle received notifications.
    """

    def on_message(ws, message):
        logger.debug("[AccountNotification] Received WebSocket message")
        try:
            data = json.loads(message)
        except Exception:
            data = {"raw": message}
        logger.debug("[AccountNotification] Subscription update: %s", json.dumps(data, indent=2))
        
        msg_type = data.get("type")

        if msg_type == "connection_ack":
            # After ack, start the subscription
            try:
                subscription = (
                    """
                    subscription OnAccountNotification($owner: String!) {
                      onAccountNotification(owner: $owner) {
                        id
                        type
                        title
                        message
                        payload
                        cta_url
                        created_at
                      }
                    }
                    """
                )
                data_obj = {
                    "query": subscription,
                    "operationName": "OnAccountNotification",
                    "variables": {"owner": owner},
                }
                start_payload = {
                    "id": "AccountNotification1",
                    "type": "start",
                    "payload": {
                        "data": json.dumps(data_obj),
                        "extensions": {
                            "authorization": {
                                "host": api_host,
                                "Authorization": id_token,
                            }
                        },
                    },
                }
                logger.info("[AccountNotification] connection_ack received, sending start subscription")
                ws.send(json.dumps(start_payload))
            except Exception as e:
                logger.error(f"[AccountNotification] Failed to send start payload: {e}")

        elif msg_type in ("ka", "keepalive"):
            # Keep-alive from server; no action required
            return
        elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "AccountNotification1":
            # Extract notification data
            payload_data = data.get("payload", {}).get("data", {})
            notification = None
            if isinstance(payload_data, dict):
                notification = payload_data.get("onAccountNotification")
                logger.info(f"[AccountNotification] Received notification: {json.dumps(notification, indent=2, ensure_ascii=False)}")
                
                # Call the callback if provided
                if on_notification_callback and notification:
                    try:
                        on_notification_callback(notification)
                    except Exception as cb_err:
                        logger.error(f"[AccountNotification] Callback error: {cb_err}")

    def on_error(ws, error):
        logger.error(f"[AccountNotification] WebSocket error: {error}")

    def on_close(ws, status_code, msg):
        logger.warning(f"[AccountNotification] WebSocket closed: code={status_code}, msg={msg}")

    def on_open(ws):
        logger_helper.debug("[AccountNotification] WebSocket opened")
        init_payload = {
            "type": "connection_init",
            "payload": {}
        }
        try:
            logger_helper.debug("[AccountNotification] Sending connection_init...")
            ws.send(json.dumps(init_payload))
        except Exception as e:
            logger.error(f"[AccountNotification] Failed to send connection_init: {e}")

    # Resolve WS URL and ensure it's the AppSync realtime endpoint
    if not ws_url:
        ws_url = os.getenv("ECAN_WS_URL", "")
    if not ws_url:
        logger_helper.warning(
            "[AccountNotification] WebSocket URL not provided and ECAN_WS_URL is not set. Subscription disabled.")
        raise ValueError("WebSocket URL not provided and ECAN_WS_URL is not set")

    if ws_url.startswith("https://") and "appsync-api" in ws_url:
        try:
            prefix = "https://"
            rest = ws_url[len(prefix):]
            rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
            ws_url = "wss://" + rest
            logger_helper.info(f"[AccountNotification] Converted to realtime endpoint: {ws_url}")
        except Exception:
            pass

    parsed = urlparse(ws_url)
    api_host = parsed.netloc.replace("appsync-realtime-api", "appsync-api")
    header_obj = {
        "host": api_host,
        "Authorization": id_token,
    }
    payload_obj = {}
    header_b64 = base64.b64encode(json.dumps(header_obj).encode("utf-8")).decode("utf-8")
    payload_b64 = base64.b64encode(json.dumps(payload_obj).encode("utf-8")).decode("utf-8")

    query = dict(parse_qsl(parsed.query))
    query.update({
        "header": header_b64,
        "payload": payload_b64,
    })
    signed_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query),
        parsed.fragment,
    ))

    logger.debug("[AccountNotification] ws_url ok")
    headers = []

    ws = websocket.WebSocketApp(
        signed_url,
        header=headers,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
        subprotocols=["graphql-ws"],
    )

    logger.info("[AccountNotification] Launching WebSocket thread")
    import ssl

    t = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
    t.start()
    logger.info("[AccountNotification] WebSocket thread launched")
    return ws, t


def handle_account_notification(notification: dict):
    """
    Default handler for account notifications.
    Links notifications to ad banner and notification popup.
    
    Args:
        notification: Dict with keys: id, type, title, message, payload, cta_url, created_at
    """
    try:
        from gui.ipc.w2p_handlers.ad_handler import push_ad_to_frontend
        
        notification_type = notification.get("type", "")
        title = notification.get("title", "")
        message = notification.get("message", "")
        payload = notification.get("payload", {})
        cta_url = notification.get("cta_url", "")
        
        # Parse payload if it's a string
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except:
                payload = {}
        
        logger.info(f"[AccountNotification] Handling notification: type={notification_type}, title={title}")
        
        # Build banner text
        banner_text = f"📢 {title}" if title else f"📢 {message[:50]}..."
        
        # Build popup HTML
        popup_html = f"""
        <div style="padding: 20px; font-family: Arial, sans-serif;">
            <h2 style="margin-top: 0; color: #333;">{title}</h2>
            <p style="color: #666; line-height: 1.6;">{message}</p>
        """
        
        # Add payload info if present
        if payload:
            popup_html += '<div style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0;">'
            for key, value in payload.items():
                popup_html += f'<p style="margin: 5px 0;"><strong>{key}:</strong> {value}</p>'
            popup_html += '</div>'
        
        # Add CTA button if URL provided
        if cta_url:
            popup_html += f"""
            <a href="{cta_url}" target="_blank" 
               style="display: inline-block; background: #007bff; color: white; 
                      padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px;">
                Learn More
            </a>
            """
        
        popup_html += "</div>"
        
        # Determine duration based on notification type
        duration_ms = 60000  # Default 1 minute
        if notification_type in ("urgent", "alert", "critical"):
            duration_ms = 120000  # 2 minutes for urgent
        elif notification_type in ("info", "tip"):
            duration_ms = 30000  # 30 seconds for info
        
        # Push to frontend
        push_ad_to_frontend(
            banner_text=banner_text,
            popup_html=popup_html,
            duration_ms=duration_ms
        )
        
        logger.info(f"[AccountNotification] Pushed notification to frontend: {title}")
        
    except Exception as e:
        logger.error(f"[AccountNotification] Error handling notification: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ============================================================================
# Vehicle Operations (with decorator registration)
# ============================================================================

@cloud_api(DataType.VEHICLE, Operation.ADD)
def send_add_vehicles_request_to_cloud(session, vehicles, token, endpoint, timeout=180):
    """Add/Report vehicles to cloud"""
    mutationInfo = gen_report_vehicles_string(vehicles)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "reportVehicles", "reportVehicles")


@cloud_api(DataType.VEHICLE, Operation.UPDATE)
def send_update_vehicles_decorated_to_cloud(session, vehicles, token, endpoint, timeout=180):
    """Update vehicles in cloud"""
    mutationInfo = gen_update_vehicles_string(vehicles)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateVehicles", "updateVehicles")


# ============================================================================
# Knowledge Operations (with decorator registration)
# ============================================================================

@cloud_api(DataType.KNOWLEDGE, Operation.ADD)
def send_add_knowledges_decorated_to_cloud(session, knowledges, token, endpoint, timeout=180):
    """Add Knowledge entities to cloud"""
    mutationInfo = gen_add_knowledges_string(knowledges)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addKnowledges", "addKnowledges")


@cloud_api(DataType.KNOWLEDGE, Operation.UPDATE)
def send_update_knowledges_decorated_to_cloud(session, knowledges, token, endpoint, timeout=180):
    """Update Knowledge entities in cloud"""
    mutationInfo = gen_update_knowledges_string(knowledges)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateKnowledges", "updateKnowledges")


@cloud_api(DataType.KNOWLEDGE, Operation.DELETE)
def send_remove_knowledges_decorated_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Knowledge entities from cloud"""
    mutationInfo = gen_remove_knowledges_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeKnowledges", "removeKnowledges")


@cloud_api(DataType.KNOWLEDGE, Operation.QUERY)
def send_query_knowledges_decorated_to_cloud(session, token, q_settings, endpoint):
    """Query Knowledge entities from cloud"""
    queryInfo = gen_query_knowledges_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryKnowledges", "queryKnowledges")


# ============================================================================
# Avatar Resource Operations
# ============================================================================

def gen_add_avatar_resources_string(resources):
    """Generate GraphQL mutation string for adding avatar resources"""
    query_string = """
        mutation MyMutation {
      addAvatarResources (input:[
    """
    rec_string = ""
    for i, res in enumerate(resources):
        rec_string += "{ "
        rec_string += f'id: "{res.get("id", "")}", '
        rec_string += f'owner: "{res.get("owner", "")}", '
        rec_string += f'resource_type: "{res.get("resource_type", "")}", '
        rec_string += f'name: "{res.get("name", "")}", '
        rec_string += f'description: "{res.get("description", "")}", '
        rec_string += f'image_path: "{res.get("image_path", "")}", '
        rec_string += f'video_path: "{res.get("video_path", "")}", '
        rec_string += f'image_hash: "{res.get("image_hash", "")}", '
        rec_string += f'video_hash: "{res.get("video_hash", "")}", '
        rec_string += f'cloud_image_url: "{res.get("cloud_image_url", "")}", '
        rec_string += f'cloud_video_url: "{res.get("cloud_video_url", "")}", '
        rec_string += f'cloud_image_key: "{res.get("cloud_image_key", "")}", '
        rec_string += f'cloud_video_key: "{res.get("cloud_video_key", "")}", '
        rec_string += f'cloud_synced: {"true" if res.get("cloud_synced") else "false"}, '
        avatar_metadata = res.get("avatar_metadata", "{}")
        if isinstance(avatar_metadata, dict):
            avatar_metadata = json.dumps(avatar_metadata, ensure_ascii=False).replace('"', '\\"')
        rec_string += f'avatar_metadata: "{avatar_metadata}", '
        rec_string += f'usage_count: {res.get("usage_count", 0)}, '
        rec_string += f'is_public: {"true" if res.get("is_public") else "false"}'
        rec_string += " }"
        if i != len(resources) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_update_avatar_resources_string(resources):
    """Generate GraphQL mutation string for updating avatar resources"""
    query_string = """
        mutation MyMutation {
      updateAvatarResources (input:[
    """
    rec_string = ""
    for i, res in enumerate(resources):
        rec_string += "{ "
        rec_string += f'id: "{res.get("id", "")}", '
        if "owner" in res:
            rec_string += f'owner: "{res.get("owner", "")}", '
        if "resource_type" in res:
            rec_string += f'resource_type: "{res.get("resource_type", "")}", '
        if "name" in res:
            rec_string += f'name: "{res.get("name", "")}", '
        if "description" in res:
            rec_string += f'description: "{res.get("description", "")}", '
        if "cloud_image_url" in res:
            rec_string += f'cloud_image_url: "{res.get("cloud_image_url", "")}", '
        if "cloud_video_url" in res:
            rec_string += f'cloud_video_url: "{res.get("cloud_video_url", "")}", '
        if "cloud_synced" in res:
            rec_string += f'cloud_synced: {"true" if res.get("cloud_synced") else "false"}, '
        if "avatar_metadata" in res:
            avatar_metadata = res.get("avatar_metadata", "{}")
            if isinstance(avatar_metadata, dict):
                avatar_metadata = json.dumps(avatar_metadata, ensure_ascii=False).replace('"', '\\"')
            rec_string += f'avatar_metadata: "{avatar_metadata}", '
        if "usage_count" in res:
            rec_string += f'usage_count: {res.get("usage_count", 0)}, '
        if "is_public" in res:
            rec_string += f'is_public: {"true" if res.get("is_public") else "false"}'
        # Remove trailing comma if present
        rec_string = rec_string.rstrip(', ')
        rec_string += " }"
        if i != len(resources) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_remove_avatar_resources_string(removeOrders):
    """Generate GraphQL mutation string for removing avatar resources"""
    query_string = """
        mutation MyMutation {
      removeAvatarResources (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string += "{ "
        rec_string += f'oid: "{removeOrders[i]["oid"]}", '
        rec_string += f'owner: "{removeOrders[i]["owner"]}", '
        rec_string += f'reason: "{removeOrders[i]["reason"]}"'
        rec_string += " }"
        if i != len(removeOrders) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_query_avatar_resources_string(q_settings):
    """Generate GraphQL query string for querying avatar resources"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAvatarResources(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.AVATAR_RESOURCE, Operation.ADD)
def send_add_avatar_resources_to_cloud(session, resources, token, endpoint, timeout=180):
    """Add Avatar Resource entities to cloud"""
    mutationInfo = gen_add_avatar_resources_string(resources)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addAvatarResources", "addAvatarResources")


@cloud_api(DataType.AVATAR_RESOURCE, Operation.UPDATE)
def send_update_avatar_resources_to_cloud(session, resources, token, endpoint, timeout=180):
    """Update Avatar Resource entities in cloud"""
    mutationInfo = gen_update_avatar_resources_string(resources)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateAvatarResources", "updateAvatarResources")


@cloud_api(DataType.AVATAR_RESOURCE, Operation.DELETE)
def send_remove_avatar_resources_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Avatar Resource entities from cloud"""
    mutationInfo = gen_remove_avatar_resources_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeAvatarResources", "removeAvatarResources")


@cloud_api(DataType.AVATAR_RESOURCE, Operation.QUERY)
def send_query_avatar_resources_to_cloud(session, token, q_settings, endpoint):
    """Query Avatar Resource entities from cloud"""
    queryInfo = gen_query_avatar_resources_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAvatarResources", "queryAvatarResources")


# ============================================================================
# Organization Operations
# ============================================================================

def gen_query_organizations_string(q_settings):
    """Generate GraphQL query string for querying organizations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryOrganizations(qb: "{qb}")
        }}
    '''
    return query_string


def gen_get_organizations_string(ids):
    """Generate GraphQL query string for getting organizations by IDs"""
    ids_str = ",".join(ids) if isinstance(ids, list) else str(ids)
    query_string = f'''
        query MyQuery {{
            getOrganizations(ids: "{ids_str}")
        }}
    '''
    return query_string


@cloud_api(DataType.ORGANIZATION, Operation.QUERY)
def send_query_organizations_to_cloud(session, token, q_settings, endpoint):
    """Query Organization entities from cloud"""
    queryInfo = gen_query_organizations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryOrganizations", "queryOrganizations")


def gen_add_organizations_string(organizations):
    """Generate GraphQL mutation string for adding organizations"""
    query_string = """
        mutation MyMutation {
      addOrganizations (input:[
    """
    rec_string = ""
    for i, org in enumerate(organizations):
        rec_string += "{ "
        rec_string += f'id: "{org.get("id", "")}", '
        rec_string += f'owner: "{org.get("owner", "")}", '
        rec_string += f'name: "{org.get("name", "")}", '
        description = org.get("description", "").replace('"', '\\"').replace('\n', '\\n')
        rec_string += f'description: "{description}", '
        rec_string += f'org_type: "{org.get("org_type", "")}", '
        rec_string += f'status: "{org.get("status", "active")}"'
        if "parent_id" in org:
            rec_string += f', parent_id: "{org.get("parent_id", "")}"'
        if "metadata" in org:
            metadata = org.get("metadata", {})
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', metadata: "{metadata}"'
        rec_string += " }"
        if i != len(organizations) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_update_organizations_string(organizations):
    """Generate GraphQL mutation string for updating organizations"""
    query_string = """
        mutation MyMutation {
      updateOrganizations (input:[
    """
    rec_string = ""
    for i, org in enumerate(organizations):
        rec_string += "{ "
        rec_string += f'id: "{org.get("id", "")}"'
        if "owner" in org:
            rec_string += f', owner: "{org.get("owner", "")}"'
        if "name" in org:
            rec_string += f', name: "{org.get("name", "")}"'
        if "description" in org:
            description = org.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if "org_type" in org:
            rec_string += f', org_type: "{org.get("org_type", "")}"'
        if "status" in org:
            rec_string += f', status: "{org.get("status", "")}"'
        if "parent_id" in org:
            rec_string += f', parent_id: "{org.get("parent_id", "")}"'
        if "metadata" in org:
            metadata = org.get("metadata", {})
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', metadata: "{metadata}"'
        rec_string += " }"
        if i != len(organizations) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_remove_organizations_string(removeOrders):
    """Generate GraphQL mutation string for removing organizations"""
    query_string = """
        mutation MyMutation {
      removeOrganizations (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string += "{ "
        rec_string += f'oid: "{removeOrders[i].get("oid", removeOrders[i].get("id", ""))}", '
        rec_string += f'owner: "{removeOrders[i]["owner"]}", '
        rec_string += f'reason: "{removeOrders[i].get("reason", "removed")}"'
        rec_string += " }"
        if i != len(removeOrders) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


@cloud_api(DataType.ORGANIZATION, Operation.ADD)
def send_add_organizations_to_cloud(session, organizations, token, endpoint, timeout=180):
    """Add Organization entities to cloud"""
    mutationInfo = gen_add_organizations_string(organizations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addOrganizations", "addOrganizations")


@cloud_api(DataType.ORGANIZATION, Operation.UPDATE)
def send_update_organizations_to_cloud(session, organizations, token, endpoint, timeout=180):
    """Update Organization entities in cloud"""
    mutationInfo = gen_update_organizations_string(organizations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateOrganizations", "updateOrganizations")


@cloud_api(DataType.ORGANIZATION, Operation.DELETE)
def send_remove_organizations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Organization entities from cloud"""
    mutationInfo = gen_remove_organizations_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeOrganizations", "removeOrganizations")


# ============================================================================
# Skill Entity Query (missing query operation)
# ============================================================================

def gen_query_skills_entity_string(q_settings):
    """Generate GraphQL query string for querying skill entities"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAgentSkills(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.SKILL, Operation.QUERY)
def send_query_skills_entity_to_cloud(session, token, q_settings, endpoint):
    """Query Skill entities from cloud"""
    queryInfo = gen_query_skills_entity_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentSkills", "queryAgentSkills")


# ============================================================================
# Task Entity Query (missing query operation)
# ============================================================================

def gen_query_tasks_entity_string(q_settings):
    """Generate GraphQL query string for querying task entities"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAgentTasks(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.TASK, Operation.QUERY)
def send_query_tasks_entity_to_cloud(session, token, q_settings, endpoint):
    """Query Task entities from cloud"""
    queryInfo = gen_query_tasks_entity_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTasks", "queryAgentTasks")


# ============================================================================
# Tool Entity Query (missing query operation)
# ============================================================================

def gen_query_tools_entity_string(q_settings):
    """Generate GraphQL query string for querying tool entities"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryAgentTools(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.TOOL, Operation.QUERY)
def send_query_tools_entity_to_cloud(session, token, q_settings, endpoint):
    """Query Tool entities from cloud"""
    queryInfo = gen_query_tools_entity_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryAgentTools", "queryAgentTools")


# ============================================================================
# Second-Level Relationship Operations: Skill-Tool
# ============================================================================

def gen_add_skill_tool_relations_string(relations):
    """Generate GraphQL mutation string for adding skill-tool relations"""
    from agent.cloud_api.graphql_builder import build_mutation
    return build_mutation(DataType.SKILL_TOOL, Operation.ADD, relations)


def gen_query_skill_tool_relations_string(q_settings):
    """Generate GraphQL query string for querying skill-tool relations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            querySkillToolRelations(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.SKILL_TOOL, Operation.ADD)
def send_add_skill_tool_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Add Skill-Tool relations to cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addSkillToolRelations", "addSkillToolRelations")


@cloud_api(DataType.SKILL_TOOL, Operation.UPDATE)
def send_update_skill_tool_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Update Skill-Tool relations in cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateSkillToolRelations", "updateSkillToolRelations")


@cloud_api(DataType.SKILL_TOOL, Operation.DELETE)
def send_remove_skill_tool_relations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Skill-Tool relations from cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_TOOL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeSkillToolRelations", "removeSkillToolRelations")


@cloud_api(DataType.SKILL_TOOL, Operation.QUERY)
def send_query_skill_tool_relations_to_cloud(session, token, q_settings, endpoint):
    """Query Skill-Tool relations from cloud"""
    queryInfo = gen_query_skill_tool_relations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "querySkillToolRelations", "querySkillToolRelations")


# ============================================================================
# Second-Level Relationship Operations: Skill-Knowledge
# ============================================================================

def gen_query_skill_knowledge_relations_string(q_settings):
    """Generate GraphQL query string for querying skill-knowledge relations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            querySkillKnowledgeRelations(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.ADD)
def send_add_skill_knowledge_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Add Skill-Knowledge relations to cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addSkillKnowledgeRelations", "addSkillKnowledgeRelations")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.UPDATE)
def send_update_skill_knowledge_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Update Skill-Knowledge relations in cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateSkillKnowledgeRelations", "updateSkillKnowledgeRelations")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.DELETE)
def send_remove_skill_knowledge_relations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Skill-Knowledge relations from cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeSkillKnowledgeRelations", "removeSkillKnowledgeRelations")


@cloud_api(DataType.SKILL_KNOWLEDGE, Operation.QUERY)
def send_query_skill_knowledge_relations_to_cloud(session, token, q_settings, endpoint):
    """Query Skill-Knowledge relations from cloud"""
    queryInfo = gen_query_skill_knowledge_relations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "querySkillKnowledgeRelations", "querySkillKnowledgeRelations")


# ============================================================================
# Second-Level Relationship Operations: Task-Skill
# ============================================================================

def gen_query_task_skill_relations_string(q_settings):
    """Generate GraphQL query string for querying task-skill relations"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryTaskSkillRelations(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.TASK_SKILL, Operation.ADD)
def send_add_task_skill_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Add Task-Skill relations to cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.ADD, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addTaskSkillRelations", "addTaskSkillRelations")


@cloud_api(DataType.TASK_SKILL, Operation.UPDATE)
def send_update_task_skill_relations_to_cloud(session, relations, token, endpoint, timeout=180):
    """Update Task-Skill relations in cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.UPDATE, relations)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updateTaskSkillRelations", "updateTaskSkillRelations")


@cloud_api(DataType.TASK_SKILL, Operation.DELETE)
def send_remove_task_skill_relations_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Task-Skill relations from cloud"""
    from agent.cloud_api.graphql_builder import build_mutation
    mutationInfo = build_mutation(DataType.TASK_SKILL, Operation.DELETE, removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeTaskSkillRelations", "removeTaskSkillRelations")


@cloud_api(DataType.TASK_SKILL, Operation.QUERY)
def send_query_task_skill_relations_to_cloud(session, token, q_settings, endpoint):
    """Query Task-Skill relations from cloud"""
    queryInfo = gen_query_task_skill_relations_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryTaskSkillRelations", "queryTaskSkillRelations")


# ============================================================================
# Vehicle Operations (missing remove and query)
# ============================================================================

def gen_remove_vehicles_string(removeOrders):
    """Generate GraphQL mutation string for removing vehicles"""
    query_string = """
        mutation MyMutation {
      removeVehicles (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string += "{ "
        rec_string += f'oid: "{removeOrders[i].get("oid", removeOrders[i].get("vid", ""))}", '
        rec_string += f'owner: "{removeOrders[i]["owner"]}", '
        rec_string += f'reason: "{removeOrders[i].get("reason", "removed")}"'
        rec_string += " }"
        if i != len(removeOrders) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_query_vehicles_string(q_settings):
    """Generate GraphQL query string for querying vehicles"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryVehicles(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.VEHICLE, Operation.DELETE)
def send_remove_vehicles_request_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Vehicle entities from cloud"""
    mutationInfo = gen_remove_vehicles_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removeVehicles", "removeVehicles")


@cloud_api(DataType.VEHICLE, Operation.QUERY)
def send_query_vehicles_request_to_cloud(session, token, q_settings, endpoint):
    """Query Vehicle entities from cloud"""
    queryInfo = gen_query_vehicles_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryVehicles", "queryVehicles")


# ============================================================================
# Prompt Operations
# ============================================================================

def gen_add_prompts_string(prompts):
    """Generate GraphQL mutation string for adding prompts"""
    query_string = """
        mutation MyMutation {
      addPrompts (input:[
    """
    rec_string = ""
    for i, prompt in enumerate(prompts):
        rec_string += "{ "
        rec_string += f'id: "{prompt.get("id", "")}", '
        rec_string += f'owner: "{prompt.get("owner", "")}", '
        rec_string += f'name: "{prompt.get("name", "")}", '
        description = prompt.get("description", "").replace('"', '\\"').replace('\n', '\\n')
        rec_string += f'description: "{description}", '
        content = prompt.get("content", "").replace('"', '\\"').replace('\n', '\\n')
        rec_string += f'content: "{content}", '
        rec_string += f'category: "{prompt.get("category", "")}", '
        rec_string += f'version: "{prompt.get("version", "1.0.0")}", '
        rec_string += f'status: "{prompt.get("status", "active")}", '
        rec_string += f'is_public: {"true" if prompt.get("is_public") else "false"}'
        if "tags" in prompt:
            tags = prompt.get("tags", [])
            if isinstance(tags, list):
                tags = json.dumps(tags, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', tags: "{tags}"'
        if "metadata" in prompt:
            metadata = prompt.get("metadata", {})
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', metadata: "{metadata}"'
        rec_string += " }"
        if i != len(prompts) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_update_prompts_string(prompts):
    """Generate GraphQL mutation string for updating prompts"""
    query_string = """
        mutation MyMutation {
      updatePrompts (input:[
    """
    rec_string = ""
    for i, prompt in enumerate(prompts):
        rec_string += "{ "
        rec_string += f'id: "{prompt.get("id", "")}"'
        if "owner" in prompt:
            rec_string += f', owner: "{prompt.get("owner", "")}"'
        if "name" in prompt:
            rec_string += f', name: "{prompt.get("name", "")}"'
        if "description" in prompt:
            description = prompt.get("description", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', description: "{description}"'
        if "content" in prompt:
            content = prompt.get("content", "").replace('"', '\\"').replace('\n', '\\n')
            rec_string += f', content: "{content}"'
        if "category" in prompt:
            rec_string += f', category: "{prompt.get("category", "")}"'
        if "version" in prompt:
            rec_string += f', version: "{prompt.get("version", "")}"'
        if "status" in prompt:
            rec_string += f', status: "{prompt.get("status", "")}"'
        if "is_public" in prompt:
            rec_string += f', is_public: {"true" if prompt.get("is_public") else "false"}'
        if "tags" in prompt:
            tags = prompt.get("tags", [])
            if isinstance(tags, list):
                tags = json.dumps(tags, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', tags: "{tags}"'
        if "metadata" in prompt:
            metadata = prompt.get("metadata", {})
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False).replace('"', '\\"')
            rec_string += f', metadata: "{metadata}"'
        rec_string += " }"
        if i != len(prompts) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_remove_prompts_string(removeOrders):
    """Generate GraphQL mutation string for removing prompts"""
    query_string = """
        mutation MyMutation {
      removePrompts (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string += "{ "
        rec_string += f'oid: "{removeOrders[i].get("oid", removeOrders[i].get("id", ""))}", '
        rec_string += f'owner: "{removeOrders[i]["owner"]}", '
        rec_string += f'reason: "{removeOrders[i].get("reason", "removed")}"'
        rec_string += " }"
        if i != len(removeOrders) - 1:
            rec_string += ', '
        else:
            rec_string += ']'
    
    query_string += rec_string
    query_string += """
        )
    }
    """
    return query_string


def gen_query_prompts_string(q_settings):
    """Generate GraphQL query string for querying prompts"""
    qb = json.dumps(q_settings, ensure_ascii=False).replace('"', '\\"')
    query_string = f'''
        query MyQuery {{
            queryPrompts(qb: "{qb}")
        }}
    '''
    return query_string


@cloud_api(DataType.PROMPT, Operation.ADD)
def send_add_prompts_request_to_cloud(session, prompts, token, endpoint, timeout=180):
    """Add Prompt entities to cloud"""
    mutationInfo = gen_add_prompts_string(prompts)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "addPrompts", "addPrompts")


@cloud_api(DataType.PROMPT, Operation.UPDATE)
def send_update_prompts_request_to_cloud(session, prompts, token, endpoint, timeout=180):
    """Update Prompt entities in cloud"""
    mutationInfo = gen_update_prompts_string(prompts)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "updatePrompts", "updatePrompts")


@cloud_api(DataType.PROMPT, Operation.DELETE)
def send_remove_prompts_request_to_cloud(session, removes, token, endpoint, timeout=180):
    """Remove Prompt entities from cloud"""
    mutationInfo = gen_remove_prompts_string(removes)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint, timeout=timeout)
    return safe_parse_response(jresp, "removePrompts", "removePrompts")


@cloud_api(DataType.PROMPT, Operation.QUERY)
def send_query_prompts_request_to_cloud(session, token, q_settings, endpoint):
    """Query Prompt entities from cloud"""
    queryInfo = gen_query_prompts_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    return safe_parse_response(jresp, "queryPrompts", "queryPrompts")
