import json
import os
import re
from datetime import datetime

import requests
import logging
import httpx
import asyncio

from bot.envi import getECBotDataHome
from utils.logger_helper import logger_helper
import websockets
import traceback
from config.constants import API_DEV_MODE

ecb_data_homepath = getECBotDataHome()
# Constants Copied from AppSync API 'Settings'
API_URL = 'https://w3lhm34x5jgxlbpr7zzxx7ckqq.appsync-api.ap-southeast-2.amazonaws.com/graphql'


def gen_screen_read_request_js(query, local_info):

    q_data = {
        "inScrn": query,
        "requester": local_info["user"],
        "host_name": local_info["host_name"],
        "host_ip": local_info["ip"],
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    logger_helper.debug(q_data)
    return q_data


def gen_obtain_review_request_js(query):
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


# reqTrain(input: [Skill]!): AWSJSON!
def gen_train_request_js(query):
    query_string = """
        mutation MyMutation {
      reqTrain (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        logger_helper.debug("query: "+json.dumps(query[i]))
        rec_string = rec_string + "{ skillName: \"" + query[i]["skillName"] + "\", "
        rec_string = rec_string + "skillFile: \"" + query[i]["skillFile"] + "\", "
        rec_string = rec_string + "imageFile: \"" + query[i]["imageFile"] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = "])  }"
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



async def req_lan_read_screen8(session, request, token, local_info, imgs, lan_endpoint):
    qdata = gen_screen_read_request_js(request, local_info)

    jresp = await lan_http_request8(qdata, imgs, session, token, lan_endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


def req_lan_read_screen(session, request, token, lan_endpoint):
    query = gen_screen_read_request(request)

    jresp = lan_http_request2(query, session, token, lan_endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse



def lan_http_request2(query_string, session, token, lan_endpoint):

    headers = {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    # Now we can simply post the request...
    response = session.request(
        url=lan_endpoint,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()

    return jresp


# since it's LAN, should be fast, so we send file and request data in 1 shot
async def lan_http_request8(query_js, imgs, session, token, lan_endpoint):
    host_ip = "192.168.0.2"
    LAN_API_ENDPOINT_URL= f"http://{host_ip}:8848/graphql/reqScreenTxtRead/"

    headers = {
        'Content-Type': "multipart/form-data",
        # 'Authorization': token,
        # 'cache-control': "no-cache",
    }
    print("endpoint:", LAN_API_ENDPOINT_URL, headers)

    timeout = httpx.Timeout(connect=10.0, read=100.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            print("no need to read files, img is already there...")
            # Prepare the multipart form-data request
            # files = {"file": (os.path.basename(query_js['img_file_name']), query_js['img'], "image/png")}
            files = {
                os.path.basename(img["file_name"]): (os.path.basename(img["file_name"]), img["bytes"],  "image/png")
                for img in imgs
            }
            payload = {"data": json.dumps(query_js)}

            print("Sending HTTP request...")

            # Send the async request
            response = await client.post(LAN_API_ENDPOINT_URL, files=files, data=payload)

            # need to repackage response to be the same format as from aws so that
            # the response handler can be the same. ... sc, well, let's push it to
            # the server side.

            print("Response:", response)

            return response

        except Exception as e:
            print(f"Unexpected error: {e}")
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorHttpxClient:" + traceback.format_exc() + " " + str(e)
                print(ex_stat)
