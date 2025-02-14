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


def gen_obtain_review_request_js(query, local_info):
    q_data = {
        "getFB": query,
        "requester": local_info["user"],
        "host_name": local_info["host_name"],
        "host_ip": local_info["ip"],
        "type": "reqScreenTxtRead",
        "query_type": "Query"
    }

    logger_helper.debug(q_data)
    return q_data


# reqTrain(input: [Skill]!): AWSJSON!
def gen_train_request_js(query, local_info):
    q_data = {
        "inScrn": query,
        "requester": local_info["user"],
        "host_name": local_info["host_name"],
        "host_ip": local_info["ip"],
        "type": "reqTrain",
        "query_type": "Query"
    }

    logger_helper.debug(q_data)
    return q_data



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


def req_lan_read_screen(session, request, token, local_info, imgs, lan_endpoint):
    qdata = gen_screen_read_request_js(request, local_info)

    jresp = lan_http_request2(qdata, imgs, session, token, lan_endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


# send request over the LAN synchronously.
def lan_http_request2(query_js, imgs, session, token, lan_endpoint):
    LAN_API_ENDPOINT_URL = f"{lan_endpoint}/reqScreenTxtRead/"
    print("lan endpoint: " + LAN_API_ENDPOINT_URL)
    headers = {
        'Content-Type': "multipart/form-data",
    }
    print("endpoint:", LAN_API_ENDPOINT_URL, headers)

    timeout = httpx.Timeout(connect=10.0, read=100.0, write=30.0, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        try:
            print("no need to read files, img is already there...")
            # Prepare the multipart form-data request
            # files = {"file": (os.path.basename(query_js['img_file_name']), query_js['img'], "image/png")}
            files = {
                os.path.basename(img["file_name"]): (os.path.basename(img["file_name"]), img["bytes"], "image/png")
                for img in imgs
            }
            payload = {"data": json.dumps(query_js)}

            print("Sending HTTP request...")

            # Send the async request
            response = client.post(LAN_API_ENDPOINT_URL, files=files, data=payload)

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


# since it's LAN, should be fast, so we send file and request data in 1 shot
async def lan_http_request8(query_js, imgs, session, token, lan_endpoint):
    LAN_API_ENDPOINT_URL= f"{lan_endpoint}/reqScreenTxtRead/"
    print("lan endpoint: "+LAN_API_ENDPOINT_URL)
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
