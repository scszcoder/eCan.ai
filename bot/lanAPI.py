import json
import os
import re
from datetime import datetime

import requests
import boto3
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig
import logging
import aiohttp
import asyncio

from bot.envi import getECBotDataHome
from utils.logger_helper import logger_helper
import websockets
import traceback
from config.constants import API_DEV_MODE

ecb_data_homepath = getECBotDataHome()
# Constants Copied from AppSync API 'Settings'
API_URL = 'https://w3lhm34x5jgxlbpr7zzxx7ckqq.appsync-api.ap-southeast-2.amazonaws.com/graphql'


def gen_screen_read_request_string(query):
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        query MyQuery {
      reqScreenTxtRead (inScrn:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ mid: " + str(int(query[i]["id"])) + ", "
        rec_string = rec_string + "bid: " + str(int(query[i]["bid"])) + ", "
        rec_string = rec_string + "os: \"" + query[i]["os"] + "\", "
        rec_string = rec_string + "app: \"" + query[i]["app"] + "\", "
        rec_string = rec_string + "domain: \"" + query[i]["domain"] + "\", "
        rec_string = rec_string + "page: \"" + query[i]["page"] + "\", "
        rec_string = rec_string + "layout: \"" + query[i]["layout"] + "\", "
        rec_string = rec_string + "skill: \"" + query[i]["skill_name"] + "\", "
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


# reqTrain(input: [Skill]!): AWSJSON!
def gen_train_request_string(query):
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



def gen_screen_read_icon_request_string(query):
    query_string = """
        query MyQuery {
      reqScreenIconRead (inScrn:[
    """
    rec_string = ""
    for i in range(len(query)):
        rec_string = rec_string + "{ id: " + str(int(query[i].id)) + ", "
        rec_string = rec_string + "app: \"" + query[i].app + "\", "
        rec_string = rec_string + "domain: \"" + query[i].domain + "\", "
        rec_string = rec_string + "type: \"" + query[i].req_type + "\", "
        rec_string = rec_string + "intent: \"" + query[i].intent + "\", "
        rec_string = rec_string + "lastMove: \"" + query[i].last_move + "\", "
        rec_string = rec_string + "imageFile: \"" + query[i].image_file + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
        ]) {id}
        }"""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


async def req_lan_read_screen8(session, request, token, lan_endpoint):
    query = gen_screen_read_request_string(request)

    jresp = await lan_http_request8(query, session, token, lan_endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(
            jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


def req_lan_read_screen(session, request, token, lan_endpoint):
    query = gen_screen_read_request_string(request)

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


async def lan_http_request8(query_string, session, token, lan_endpoint):
    LAN_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    async with aiohttp.ClientSession() as session8:
        async with session8.post(
                url=lan_endpoint,
                timeout=aiohttp.ClientTimeout(total=300),
                headers=headers,
                json={'query': query_string}
        ) as response:
            jresp = await response.json()
            # print(jresp)
            return jresp
