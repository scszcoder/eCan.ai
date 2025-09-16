import json
import os
from datetime import datetime
import base64
import requests
import aiohttp
import asyncio

from bot.envi import getECBotDataHome
from utils.logger_helper import logger_helper
import traceback
from config.constants import API_DEV_MODE
from aiolimiter import AsyncLimiter
limiter = AsyncLimiter(1, 1)  # Max 5 requests per second

ecb_data_homepath = getECBotDataHome()
# Constants Copied from AppSync API 'Settings'
API_URL = 'https://w3lhm34x5jgxlbpr7zzxx7ckqq.appsync-api.ap-southeast-2.amazonaws.com/graphql'


#resp is the response from requesting the presigned_url
def send_file_with_presigned_url(src_file, resp):
    #Upload file to S3 using presigned URL
    files = { 'file': open(src_file, 'rb')}
    r = requests.post(resp['url'], data=resp['fields'], files=files)
    #r = requests.post(resp['body'][0], files=files)
    logger_helper.debug(str(r.status_code))

#resp is the response from requesting the presigned_url
def get_file_with_presigned_url(dest_file, url):
    #Download file to S3 using presigned URL
    # POST to S3 presigned url
    http_response = requests.get(url, stream=True)
    print("DL presigned:", http_response)
    if http_response.status_code == 200:
        dest_dir = os.path.dirname(dest_file)

        # Check if the directory exists, and if not, create it
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        with open(dest_file, 'wb') as f:
            #http_response.raw.decode_content = True
            #shutil.copyfileobj(http_response.raw, f)

            f.write(http_response.content)

            f.close()


#	requestRunExtSkill(input: [SkillRun]): AWSJSON!
# 	skid: ID!
# 	owner: String
# 	name: String
# 	start: AWSDateTime
# 	in_data: AWSJSON!
# 	verbose: Boolean
def gen_query_reqest_run_ext_skill_string(query):
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        mutation MyMutation {
      requestRunExtSkill (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ skid: " + str(query[i]["skid"]) + ", "
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
    logger_helper.debug(query_string)
    return query_string

#
def gen_query_report_run_ext_skill_status_string(query):
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        mutation MyMutation {
      reportRunExtSkillStatus (input:[
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
    logger_helper.debug(query_string)
    return query_string


def gen_query_reg_steps_string(query):
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        query MyQuery {
      regSteps (inSteps:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
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
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        query MyQuery {
      queryChats (msgs:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
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
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        query MyQuery {
      reqFileOp (fo:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
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
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        query MyQuery {
      reqAccountInfo (ops:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
        rec_string = rec_string + "{ actid: " + str(query[i]["actid"]) + ", "
        rec_string = rec_string + "op: \"" + query[i]["op"] + "\", "
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
#input ScreenImg {
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
    logger_helper.debug("in query:"+json.dumps(query))
    query_string = """
        query MyQuery {
      reqScreenTxtRead (inScrn:[
    """
    rec_string = ""
    for i in range(len(query)):
        #rec_string = rec_string + "{ id: \"" + query[i].id + "\", "
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
        rec_string = rec_string + "bids: \"" + vehicles[i]["bids"] + "\", "
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





def gen_query_skills_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MySkQuery { querySkills(qs: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { querySkills(qs: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string

def gen_query_bots_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MyBOTQuery { queryBots(qb: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MyBOTQuery { queryBots(qb: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_query_missions_by_time_string(query):

    query_string = """
        query MyQuery {
      queryMissions (qm:[
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
    logger_helper.debug(query_string)
    return query_string


def gen_query_missions_string(query):
    query_string = """
        query MyQuery {
      queryMissions (qm:[
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
        query_string = "query MySchQuery { genSchedules(settings: \"{ \\\"testmode\\\": false, \\\"test_name\\\": \\\""+test_name+"\\\", \\\"forceful\\\": " + schedule_settings.get("forceful", "false") + ", \\\"skillPreferences\\\": " + schedule_settings.get("skillPreferences", "{\\\"no_preference\\\":false, \\\"use_in_browser_skill\\\":true}") + ", \\\"tz\\\": \\\"" + schedule_settings.get("tz", "America/Los_Angeles") + "\\\"}\") } "
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

def gen_open_acct_string(acct):
    query_string = """
        mutation MyABMutation {
      addBots (input:[
    """
    rec_string = ""
    for i in range(len(acct)):
        rec_string = rec_string + "{ cid:\"" + acct[i].cid + "\", "
        rec_string = rec_string + "email:\"" + acct[i].email + "\", "
        rec_string = rec_string + "phone:\"" + acct[i].phone + "\", "
        rec_string = rec_string + "country:\"" + acct[i].country + "\", "
        rec_string = rec_string + "city:\"" + acct[i].city + "\", "
        rec_string = rec_string + "state:\"" + acct[i].state + "\", "
        rec_string = rec_string + "name:\"" + acct[i].name + "\", "
        rec_string = rec_string + "snid:\"" + acct[i].snid + "\" } "

        if i != len(acct) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_make_order_string(orders):
    query_string = "mutation MyABMutation { addBots (input:["
    rec_string = ""
    for i in range(len(orders)):
        rec_string = rec_string + "{ oid:\"" + orders[i].oid + "\", "
        rec_string = rec_string + "cid:\"" + orders[i].cid + "\", "
        rec_string = rec_string + "orderID:\"" + orders[i].orderID + "\", "
        rec_string = rec_string + "product:\"" + orders[i].product + "\", "
        rec_string = rec_string + "description:\"" + orders[i].description + "\", "
        rec_string = rec_string + "yek:\"" + orders[i].yek + "\", "
        rec_string = rec_string + "number:\"" + orders[i].number + "\", "
        rec_string = rec_string + "discount:\"" + orders[i].discount + "\", "
        rec_string = rec_string + "discountType:\"" + orders[i].discountType + "\", "
        rec_string = rec_string + "dealType:\"" + orders[i].dealType + "\", "
        rec_string = rec_string + "unitPrice:\"" + orders[i].unitPrice + "\", "
        rec_string = rec_string + "total:\"" + orders[i].total + "\", "
        rec_string = rec_string + "payMethod:\"" + orders[i].payMethod + "\", "
        rec_string = rec_string + "transactionID:\"" + orders[i].transactionID + "\" } "

        if i != len(orders) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_add_bots_string(bots):
    query_string = "mutation MyMutation { addBots(input: ["
    rec_string = ""
    for i in range(len(bots)):
        if isinstance(bots[i], dict):
            rec_string = rec_string + "{ bid: \"" + str(bots[i]["pubProfile"]["bid"]) + "\", "
            rec_string = rec_string + "owner: \"" + str(bots[i]["pubProfile"]["owner"]) + "\", "
            rec_string = rec_string + "roles: \"" + bots[i]["pubProfile"]["roles"] + "\", "
            rec_string = rec_string + "org: \"" + bots[i]["pubProfile"]["org"] + "\", "
            rec_string = rec_string + "birthday: \"" + bots[i]["pubProfile"]["pubbirthday"] + "\", "
            rec_string = rec_string + "gender: \"" + bots[i]["pubProfile"]["gender"] + "\", "
            rec_string = rec_string + "interests: \"" + bots[i]["pubProfile"]["interests"] + "\", "
            rec_string = rec_string + "status: \"" + bots[i]["pubProfile"]["status"] + "\", "
            rec_string = rec_string + "levels: \"" + bots[i]["pubProfile"]["levels"] + "\", "
            rec_string = rec_string + "vehicle: \"" + bots[i]["pubProfile"]["vehicle"] + "\", "
            rec_string = rec_string + "location: \"" + bots[i]["pubProfile"]["location"] + "\"} "
        else:
            rec_string = rec_string + "{ bid: \"" + str(bots[i].getBid()) + "\", "
            rec_string = rec_string + "owner: \"" + str(bots[i].getOwner()) + "\", "
            rec_string = rec_string + "roles: \"" + bots[i].getRoles() + "\", "
            rec_string = rec_string + "org: \"" + bots[i].getOrg() + "\", "
            rec_string = rec_string + "birthday: \"" + bots[i].getPubBirthday() + "\", "
            rec_string = rec_string + "gender: \"" + bots[i].getGender() + "\", "
            rec_string = rec_string + "interests: \"" + bots[i].getInterests() + "\", "
            rec_string = rec_string + "status: \"" + bots[i].getStatus() + "\", "
            rec_string = rec_string + "levels: \"" + bots[i].getLevels() + "\", "
            rec_string = rec_string + "vehicle: \"" + bots[i].getVehicle() + "\", "
            rec_string = rec_string + "location: \"" + bots[i].getLocation() + "\"} "


        if i != len(bots) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    logger_helper.debug("query string:"+query_string)
    return query_string


def gen_update_bots_string(bots):
    query_string = """
        mutation MyUBMutation {
      updateBots (input:[
    """
    rec_string = ""
    for i in range(len(bots)):
        if isinstance(bots[i], dict):
            rec_string = rec_string + "{ bid: \"" + str(bots[i]["pubProfile"]["bid"]) + "\", "
            rec_string = rec_string + "owner: \"" + str(bots[i]["pubProfile"]["owner"]) + "\", "
            rec_string = rec_string + "roles: \"" + bots[i]["pubProfile"]["roles"] + "\", "
            rec_string = rec_string + "org: \"" + bots[i]["pubProfile"]["org"] + "\", "
            rec_string = rec_string + "birthday: " + bots[i]["pubProfile"]["pubbirthday"] + ", "
            rec_string = rec_string + "gender: \"" + bots[i]["pubProfile"]["gender"] + "\", "
            rec_string = rec_string + "interests: \"" + bots[i]["pubProfile"]["interests"] + "\", "
            rec_string = rec_string + "status: \"" + bots[i]["pubProfile"]["status"] + "\", "
            rec_string = rec_string + "levels: \"" + bots[i]["pubProfile"]["levels"] + "\", "
            rec_string = rec_string + "vehicle: \"" + bots[i]["pubProfile"]["vehicle"] + "\", "
            rec_string = rec_string + "location: \"" + bots[i]["pubProfile"]["location"] + "\"} "
        else:
            if bots[i].getOrg():
                org = bots[i].getOrg()
            else:
                org = ""
            rec_string = rec_string + "{ bid: " + str(bots[i].getBid()) + ", "
            rec_string = rec_string + "owner: \"" + bots[i].getOwner() + "\", "
            rec_string = rec_string + "roles: \"" + bots[i].getRoles() + "\", "
            rec_string = rec_string + "org: \"" + org + "\", "
            rec_string = rec_string + "birthday: \"" + bots[i].getPubBirthday() + "\", "
            rec_string = rec_string + "gender: \"" + bots[i].getGender() + "\", "
            rec_string = rec_string + "interests: \"" + bots[i].getInterests() + "\", "
            rec_string = rec_string + "status: \"" + bots[i].getStatus() + "\", "
            rec_string = rec_string + "levels: \"" + bots[i].getLevels() + "\", "
            rec_string = rec_string + "vehicle: \"" + bots[i].getVehicle() + "\", "
            rec_string = rec_string + "location: \"" + bots[i].getLocation() + "\"} "

        if i != len(bots) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
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
        rec_string = rec_string + "bids: \"" + vehicles[i]["bids"] + "\", "
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


def gen_remove_bots_string(removeOrders):
    query_string = """
        mutation MyRBMutation {
      removeBots (input:[
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
    logger_helper.debug(query_string)
    return query_string



def gen_add_missions_string(missions, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addMissions (input:[
    """
    rec_string = ""
    for i in range(len(missions)):
        if isinstance(missions[i], dict):
            rec_string = rec_string + "{ mid:" + str(missions[i]["pubAttributes"]["missionId"]) + ", "
            rec_string = rec_string + "ticket:" + str(missions[i]["pubAttributes"]["ticket"]) + ", "
            rec_string = rec_string + "owner:\"" + missions[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:" + str(missions[i]["pubAttributes"]["bot_id"]) + ", "
            rec_string = rec_string + "cuspas:\"" + missions[i]["pubAttributes"]["cuspas"] + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + missions[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "trepeat:" + str(missions[i]["pubAttributes"]["repeat"]) + ", "
            rec_string = rec_string + "stores:\"" + missions[i]["pubAttributes"]["pseudo_store"] + "\", "
            rec_string = rec_string + "asin:\"" + missions[i]["pubAttributes"]["pseudo_asin"] + "\", "
            rec_string = rec_string + "brand:\"" + missions[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i]["pubAttributes"]["ms_type"] + "\", "
            rec_string = rec_string + "esd:\"" + missions[i]["pubAttributes"]["esd"] + "\", "
            rec_string = rec_string + "as_server:" + str(int(missions[i]["pubAttributes"]["as_server"])) + ", "
            rec_string = rec_string + "skills:\"" + missions[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + missions[i]["pubAttributes"]["config"].replace('"', '\\"') + "\"} "
        else:
            rec_string = rec_string + "{ mid:" + str(missions[i].getMid()) + ", "
            rec_string = rec_string + "ticket:" + str(missions[i].getTicket()) + ", "
            rec_string = rec_string + "owner:\"" + missions[i].getOwner() + "\", "
            rec_string = rec_string + "botid:" + str(missions[i].getBid()) + ", "
            rec_string = rec_string + "cuspas:\"" + str(missions[i].getCusPAS()) + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i].getSearchCat() + "\", "
            rec_string = rec_string + "status:\"" + missions[i].getStatus() + "\", "
            rec_string = rec_string + "trepeat:" + str(missions[i].getRetry()) + ", "
            rec_string = rec_string + "stores:\"" + missions[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin:\"" + missions[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand:\"" + missions[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i].getMtype() + "\", "
            rec_string = rec_string + "esd:\"" + missions[i].getEsd() + "\", "
            rec_string = rec_string + "as_server:" + str(int(missions[i].getAsServer())) + ", "
            rec_string = rec_string + "skills:\"" + missions[i].getSkills() + "\", "
            rec_string = rec_string + "config:\"" + missions[i].getConfig().replace('"', '\\"') + "\"} "

        if i != len(missions) - 1:
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
    logger_helper.debug(query_string)
    return query_string


def gen_update_missions_string(missions):
    query_string = """
        mutation MyUMMutation {
      updateMissions (input:[
    """
    rec_string = ""
    for i in range(len(missions)):
        if isinstance(missions[i], dict):
            rec_string = rec_string + "{ mid:\"" + str(missions[i]["pubAttributes"]["missionId"]) + "\", "
            rec_string = rec_string + "ticket:\"" + str(missions[i]["pubAttributes"]["ticket"]) + "\", "
            rec_string = rec_string + "owner:\"" + missions[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:\"" + str(missions[i]["pubAttributes"]["botid"]) + "\", "
            rec_string = rec_string + "cuspas:\"" + str(missions[i]["pubAttributes"]["cuspas"]) + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + missions[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "trepeat:" + str(missions[i]["pubAttributes"]["repeat"]) + ", "
            rec_string = rec_string + "stores:\"" + str(missions[i]["pubAttributes"]["pseudo_store"]) + "\", "
            rec_string = rec_string + "asin:" + str(missions[i]["pubAttributes"]["pseudo_asin"]) + ", "
            rec_string = rec_string + "brand:\"" + missions[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i]["pubAttributes"]["mtype"] + "\", "
            rec_string = rec_string + "esd:\"" + missions[i]["pubAttributes"]["esd"] + "\", "
            rec_string = rec_string + "as_server:" + str(int(missions[i]["pubAttributes"]["as_server"])) + ", "
            rec_string = rec_string + "skills:\"" + missions[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + missions[i]["pubAttributes"]["config"].replace('"', '\\"') + "\"} "
        else:
            rec_string = rec_string + "{ mid: " + str(missions[i].getMid()) + ", "
            rec_string = rec_string + "ticket: " + str(missions[i].getTicket()) + ", "
            rec_string = rec_string + "owner: \"" + missions[i].getOwner() + "\", "
            rec_string = rec_string + "botid:" + str(missions[i].getBid()) + ", "
            rec_string = rec_string + "cuspas: \"" + missions[i].getCusPAS() + "\", "
            rec_string = rec_string + "search_kw: \"" + missions[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat: \"" + missions[i].getSearchCat() + "\", "
            rec_string = rec_string + "status: \"" + missions[i].getStatus() + "\", "
            rec_string = rec_string + "trepeat: " + str(missions[i].getRetry()) + ", "
            rec_string = rec_string + "stores: \"" + missions[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin: \"" + missions[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand: \"" + missions[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype: \"" + missions[i].getMtype() + "\", "
            rec_string = rec_string + "esd: \"" + missions[i].getEsd() + "\", "
            rec_string = rec_string + "as_server: " + str(int(missions[i].getAsServer())) + ", "
            rec_string = rec_string + "skills: \"" + missions[i].getSkills() + "\", "
            rec_string = rec_string + "config: \"" + missions[i].getConfig().replace('"', '\\"') + "\"} "

        if i != len(missions) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string

def gen_daily_update_string(missionsStats, full):
    query_string = """
            mutation MyUMMutation {
          reportStatus (input:[
        """
    rec_string = ""
    for i in range(len(missionsStats)):
        if isinstance(missionsStats[i], dict):
            rec_string = rec_string + "{ mid:\"" + str(missionsStats[i]["mid"]) + "\", "

            if full:
                rec_string = rec_string + "bid:\"" + str(missionsStats[i]["bid"]) + "\", "
                rec_string = rec_string + "status:\"" + missionsStats[i]["status"] + "\", "
                rec_string = rec_string + "starttime:" + str(missionsStats[i]["starttime"]) + ", "
                rec_string = rec_string + "endtime:" + str(missionsStats[i]["endtime"]) + "} "
            else:
                rec_string = rec_string + "status:\"" + missionsStats[i]["status"] + "\"}"
        else:
            rec_string = rec_string + "{ mid:\"" + str(missionsStats[i].getMid()) + "\", "
            if full:
                rec_string = rec_string + "bid:\"" + str(missionsStats[i].getBid()) + "\", "
                rec_string = rec_string + "status:\"" + missionsStats[i].getStatus() + "\", "
                rec_string = rec_string + "starttime:\"" + missionsStats[i].getStartTime() + "\", "
                rec_string = rec_string + "endtime:\"" + missionsStats[i].getEndTime() + "\"} "
            else:
                rec_string = rec_string + "status:\"" + missionsStats[i].getStatus() + "\"} "


        if i != len(missionsStats) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug("DAILY REPORT QUERY STRING:"+query_string)
    return query_string


def gen_update_missions_ex_status_string(missionsStats):
    query_string = """
            mutation updateMissionsExStatus {
          updateMissionsExStatus (input:[
        """
    rec_string = ""
    for i in range(len(missionsStats)):
        if isinstance(missionsStats[i], dict):
            rec_string = rec_string + "{ mid:" + str(missionsStats[i]["mid"]) + ", "
            rec_string = rec_string + "status:\"" + missionsStats[i]["status"] + "\"}"
        else:
            rec_string = rec_string + "{ mid:" + str(missionsStats[i].getMid()) + ", "
            rec_string = rec_string + "status:\"" + missionsStats[i].getStatus() + "\"} "


        if i != len(missionsStats) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
        ) 
        } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug("DAILY REPORT QUERY STRING:"+query_string)
    return query_string


def gen_remove_missions_string(removeOrders):
    query_string = """
        mutation MyRMMutation {
      removeMissions (input:[
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
    logger_helper.debug(query_string)
    return query_string


def gen_add_skills_string(skills):
    query_string = "mutation MyMutation { addSkills(input: ["
    rec_string = ""
    for i in range(len(skills)):
        if isinstance(skills[i], dict):
            rec_string = rec_string + "{ skid: " + str(skills[i]["skid"]) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i]["owner"]) + "\", "
            rec_string = rec_string + "createdOn: \"" + str(skills[i]["createdOn"]) + "\", "
            rec_string = rec_string + "platform: \"" + skills[i]["platform"] + "\", "
            rec_string = rec_string + "app: \"" + skills[i]["app"] + "\", "
            rec_string = rec_string + "site_name: \"" + skills[i]["site_name"] + "\", "
            rec_string = rec_string + "site: \"" + skills[i]["site"] + "\", "
            rec_string = rec_string + "page: \"" + skills[i]["page"] + "\", "
            rec_string = rec_string + "name: \"" + skills[i]["name"] + "\", "
            rec_string = rec_string + "path: \"" + skills[i]["path"] + "\", "
            rec_string = rec_string + "main: \"" + skills[i]["main"] + "\", "
            rec_string = rec_string + "description: \"" + skills[i]["description"] + "\", "
            rec_string = rec_string + "runtime: " + str(skills[i]["runtime"]) + ", "
            rec_string = rec_string + "price_model: \"" + skills[i]["price_model"] + "\", "
            rec_string = rec_string + "price: " + str(skills[i]["price"]) + ", "
            rec_string = rec_string + "privacy: \"" + skills[i]["privacy"] + "\"} "
        else:
            rec_string = rec_string + "{ skid: " + str(skills[i].getSkid()) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i].getOwner()) + "\", "
            rec_string = rec_string + "createdOn: \"" + str(skills[i].getCreatedOn()) + "\", "
            rec_string = rec_string + "platform: \"" + skills[i].getPlatform() + "\", "
            rec_string = rec_string + "app: \"" + skills[i].getApp() + "\", "
            rec_string = rec_string + "site_name: \"" + skills[i].getSiteName() + "\", "
            rec_string = rec_string + "site: \"" + skills[i].getSite() + "\", "
            rec_string = rec_string + "page: \"" + skills[i].getPage() + "\", "
            rec_string = rec_string + "name: \"" + skills[i].getName() + "\", "
            rec_string = rec_string + "path: \"" + skills[i].getPath() + "\", "
            rec_string = rec_string + "main: \"" + skills[i].getMain() + "\", "
            rec_string = rec_string + "description: \"" + skills[i].getDescription() + "\", "
            rec_string = rec_string + "runtime: " + str(skills[i].getRunTime()) + ", "
            rec_string = rec_string + "price_model: \"" + skills[i].getPriceModel() + "\", "
            rec_string = rec_string + "price: " + str(skills[i].getPrice()) + ", "
            rec_string = rec_string + "privacy: \"" + skills[i].getPrivacy() + "\"} "

        if i != len(skills) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_update_skills_string(skills):
    query_string = """
        mutation MyUBMutation {
      updateSkills (input:[
    """
    rec_string = ""
    for i in range(len(skills)):
        if isinstance(skills[i], dict):
            rec_string = rec_string + "{ skid: " + str(skills[i]["skid"]) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i]["owner"]) + "\", "
            rec_string = rec_string + "createdOn: \"" + str(skills[i]["createdOn"]) + "\", "
            rec_string = rec_string + "platform: \"" + skills[i]["platform"] + "\", "
            rec_string = rec_string + "app: \"" + skills[i]["app"] + "\", "
            rec_string = rec_string + "site: \"" + skills[i]["site"] + "\", "
            rec_string = rec_string + "page: \"" + skills[i]["page"] + "\", "
            rec_string = rec_string + "name: \"" + skills[i]["name"] + "\", "
            rec_string = rec_string + "path: \"" + skills[i]["path"] + "\", "
            rec_string = rec_string + "main: \"" + skills[i]["main"] + "\", "
            rec_string = rec_string + "description: \"" + skills[i]["description"] + "\", "
            rec_string = rec_string + "runtime: " + str(skills[i]["runtime"]) + ", "
            rec_string = rec_string + "price_model: \"" + skills[i]["price_model"] + "\", "
            rec_string = rec_string + "price: " + str(skills[i]["price"]) + ", "
            rec_string = rec_string + "privacy: \"" + skills[i]["privacy"] + "\"} "
        else:
            rec_string = rec_string + "{ skid: " + str(skills[i].getSkid()) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i].getOwner()) + "\", "
            rec_string = rec_string + "createdOn: \"" + str(skills[i].getCreatedOn()) + "\", "
            rec_string = rec_string + "platform: \"" + skills[i].getPlatform() + "\", "
            rec_string = rec_string + "app: \"" + skills[i].getApp() + "\", "
            rec_string = rec_string + "site: \"" + skills[i].getSite() + "\", "
            rec_string = rec_string + "page: \"" + skills[i].getPage() + "\", "
            rec_string = rec_string + "name: \"" + skills[i].getName() + "\", "
            rec_string = rec_string + "path: \"" + skills[i].getPath() + "\", "
            rec_string = rec_string + "main: \"" + skills[i].getMain() + "\", "
            rec_string = rec_string + "description: \"" + skills[i].getDescription() + "\", "
            rec_string = rec_string + "runtime: " + str(skills[i].getRunTime()) + ", "
            rec_string = rec_string + "price_model: \"" + skills[i].getPriceModel() + "\", "
            rec_string = rec_string + "price: " + str(skills[i].getPrice()) + ", "
            rec_string = rec_string + "privacy: \"" + skills[i].getPrivacy() + "\"} "

        if i != len(skills) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string




def gen_remove_skills_string(removeOrders):
    query_string = """
        mutation MyRBMutation {
      removeSkills (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string = rec_string + "{ oid:" + str(removeOrders[i]["skid"]) + ", "
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
    logger_helper.debug(query_string)
    return query_string


def gen_train_request_string(skills):
    query_string = """
            mutation MyUBMutation {
          reqTrain (input:[
        """
    rec_string = ""
    for i in range(len(skills)):
        rec_string = rec_string + "{ mid: " + str(skills[i]["mid"]) + ", "
        rec_string = rec_string + "bid: '" + str(skills[i]["bid"]) + "', "
        rec_string = rec_string + "status: \"" + skills[i]["status"] + "\", "
        rec_string = rec_string + "starttime: \"" + skills[i]["starttime"] + "\", "
        rec_string = rec_string + "endtime: \"" + skills[i]["endtime"] + "\"} "

        if i != len(skills) - 1:
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
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


async def req_cloud_read_screen8(session, request, token, endpoint):

    query = gen_screen_read_request_string(request)

    jresp = await appsync_http_request8(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["errorInfo"]))
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
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["errorInfo"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_train_read_screen(session, request, token, endpoint):

    query = gen_train_request_string(request)

    jresp = appsync_http_request(query, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqTrain"])

    return jresponse


def send_update_missions_ex_status_to_cloud(session, missionStats, token, endpoint):
    if len(missionStats) > 0:
        query = gen_update_missions_ex_status_string(missionStats)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            logger_helper.error("ERROR Type: " + json.dumps(jresponse["errorType"]) + " ERROR Info: " + json.dumps(jresponse["message"]))
        else:
            jresponse = json.loads(jresp["data"]["updateMissionsExStatus"])
    else:
        logger_helper.error("ERROR Type: EMPTY DAILY REPORTS")
        jresponse = "ERROR: EMPTY REPORTS"
    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_completion_status_to_cloud(session, missionStats, token, endpoint, full=True):
    if len(missionStats) > 0:
        query = gen_daily_update_string(missionStats, full)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            logger_helper.error("ERROR Type: " + json.dumps(jresponse["errorType"]) + " ERROR Info: " + json.dumps(jresponse["message"]))
        else:
            jresponse = json.loads(jresp["data"]["reportStatus"])
    else:
        logger_helper.error("ERROR Type: EMPTY DAILY REPORTS")
        jresponse = "ERROR: EMPTY REPORTS"
    return jresponse

async def send_run_ext_skill_request_to_cloud8(session, reqs, token, endpoint):

    mutationInfo = gen_query_reqest_run_ext_skill_string(reqs)

    jresp = await appsync_http_request8(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["requestRunExtSkill"])

    return jresponse

def send_run_ext_skill_request_to_cloud(session, reqs, token, endpoint):

    mutationInfo = gen_query_reqest_run_ext_skill_string(reqs)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP::", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["requestRunExtSkill"])

    return jresponse


def send_report_run_ext_skill_status_request_to_cloud(session, reps, token, endpoint):

    mutationInfo = gen_query_report_run_ext_skill_status_string(reps)
    print("report status mutation:", mutationInfo)
    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reportRunExtSkillStatus"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_bots_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_add_bots_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_bots_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_update_bots_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateBots"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_bots_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_bots_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeBots"])
    return jresponse


def send_update_vehicles_request_to_cloud(session, vehicles, token, endpoint):

    mutationInfo = gen_update_vehicles_string(vehicles)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateVehicles"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_missions_request_to_cloud(session, missions, token, endpoint):

    mutationInfo = gen_add_missions_string(missions)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addMissions"])
    print("send_add_missions_request_to_cloud response:", send_add_missions_request_to_cloud)
    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_missions_request_to_cloud(session, missions, token, endpoint):

    mutationInfo = gen_update_missions_string(missions)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateMissions"])
    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_missions_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_missions_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeMissions"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_skills_request_to_cloud(session, skills, token, endpoint):

    mutationInfo = gen_add_skills_string(skills)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addSkills"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_skills_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_update_skills_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_skills_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_skills_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_open_acct_request_to_cloud(session, accts, token, endpoint):

    mutationInfo = gen_open_acct_string(accts)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_make_order_request_to_cloud(session, orders, token, endpoint):

    mutationInfo = gen_make_order_string(orders)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


def gen_get_bot_string():
    query_string = "query MyGetBotQuery { getBots (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_bots_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_bot_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getBots"])


    return jresponse

def send_query_skills_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_skills_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("AppSync querySkills error: " + json.dumps(jresp))
        # Handle case where user has no skills data (return empty list)
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger_helper.info("No skills data found for user - returning empty list")
            jresponse = []
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            skills_data = jresp["data"]["querySkills"]
            if skills_data is None:
                logger_helper.info("querySkills returned null - user has no skills data")
                jresponse = []
            else:
                jresponse = json.loads(skills_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger_helper.error(f"Failed to parse querySkills response: {e}")
            jresponse = []


    return jresponse


def send_report_vehicles_to_cloud(session, token, vehicles, endpoint):

    queryInfo = gen_report_vehicles_string(vehicles)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    # jresp = {"data": {"reportVehicles": {}}}
    if "errors" in jresp:
        screen_error = True
        print("JRESP:", jresp)
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["dequeueTasks"])


    return jresponse



def send_query_bots_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_bots_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryBots"])
        # print("jresponse", jresponse)
        logger_helper.debug("query bots response: ", jresponse)

    return jresponse

def send_query_missions_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_missions_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("AppSync queryMissions error: " + json.dumps(jresp))
        # Handle case where user has no missions data (return empty list)
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger_helper.info("No missions data found for user - returning empty list")
            jresponse = []
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            missions_data = jresp["data"]["queryMissions"]
            if missions_data is None:
                logger_helper.info("queryMissions returned null - user has no missions data")
                jresponse = []
            else:
                jresponse = json.loads(missions_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger_helper.error(f"Failed to parse queryMissions response: {e}")
            jresponse = []


    return jresponse


def send_query_missions_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_missions_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            logger_helper.error("AppSync queryMissions by time error: " + json.dumps(jresp))
            # Handle case where user has no missions data (return empty list)
            if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
                logger_helper.warning("No missions data found for user by time - returning empty list")
                jresponse = []
            else:
                jresponse = jresp["errors"][0] if jresp["errors"] else {}
        else:
            try:
                missions_data = jresp["data"]["queryMissions"]
                if missions_data is None:
                    logger_helper.info("queryMissions by time returned null - user has no missions data")
                    jresponse = []
                else:
                    jresponse = json.loads(missions_data)
            except (json.JSONDecodeError, TypeError) as e:
                logger_helper.error(f"Failed to parse queryMissions by time response: {e}")
                jresponse = []

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryMissionByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryMissionByTime traceback information not available:" + str(e)
        logger_helper.error(ex_stat)
        jresponse = {}

    return jresponse


def send_query_manager_missions_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_manager_missions_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            logger_helper.error("AppSync getManagerMissions error: " + json.dumps(jresp))
            # Handle case where user has no manager missions data (return empty dict)
            if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
                logger_helper.warning("No manager missions data found for user - returning empty dict")
                jresponse = {}
            else:
                jresponse = jresp["errors"][0] if jresp["errors"] else {}
        else:
            try:
                missions_data = jresp["data"]["getManagerMissions"]
                if missions_data is None:
                    logger_helper.info("getManagerMissions returned null - user has no manager missions data")
                    jresponse = {}
                else:
                    jresponse = json.loads(missions_data)
            except (json.JSONDecodeError, TypeError) as e:
                logger_helper.error(f"Failed to parse getManagerMissions response: {e}")
                jresponse = {}

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryManagerMissions:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryManagerMissions traceback information not available:" + str(e)
        logger_helper.error(ex_stat)
        jresponse = {}

    return jresponse


def send_query_chat_request_to_cloud(session, token, chat_request, endpoint):

    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])


    return jresponse


async def send_query_chat_request_to_cloud8(session, token, chat_request, endpoint):

    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = await appsync_http_request8(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse


def send_account_info_request_to_cloud(session, acct_ops, token, endpoint):

    queryInfo = gen_account_info_request_string(acct_ops)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqAccountInfo"])

    return jresponse



def send_reg_steps_to_cloud(session, localSteps, token, endpoint):

    queryInfo = gen_query_reg_steps_string(localSteps)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        fname = os.path.basename(f2ul)
        fwords = f2ul.split("/")
        relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
        if destination:
            prefix = ftype + "|" + destination
        else:
            prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

        fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
        logger_helper.debug("fopreqs:"+json.dumps(fopreqs))

        res = send_file_op_request_to_cloud(session, fopreqs, token, endpoint)
        logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))
        logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

        resd = json.loads(res['body']['urls']['result'])
        logger_helper.debug("resd: "+json.dumps(resd))

        # now perform the upload of the presigned URL
        logger_helper.debug("f2ul:"+json.dumps(f2ul))
        resp = send_file_with_presigned_url(f2ul, resd['body'][0])
        #  logger_helper.debug("upload result: "+json.dumps(resp))
        logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
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
        resp = get_file_with_presigned_url(datahome+"/"+local_f2dl, resd['body'][0])
        #
        # logger_helper.debug("resp:"+json.dumps(resp))
        link = datahome+"/"+local_f2dl

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

def appsync_http_request(query_string, session, token, endpoint):
    """
    Send AppSync GraphQL request with authentication.
    Supports both Cognito User Pool tokens and Google ID tokens.
    """
    if API_DEV_MODE:
        APPSYNC_API_ENDPOINT_URL = "https://cpzjfests5ea5nk7cipavakdnm.appsync-api.us-east-1.amazonaws.com/graphql"
    else:
        APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    
    if not endpoint:
        endpoint = APPSYNC_API_ENDPOINT_URL

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache"
    }

    try:
        # Send the request
        response = session.request(
            url=endpoint,
            method='POST',
            timeout=1200,
            headers=headers,
            json={'query': query_string}
        )
        
        jresp = response.json()
        
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
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
                logger_helper.debug("SENDING PRESIGNED URL STATUS:"+str(r.status))
                # print("PRESIGNED RESPONSE:",r)
                f.close()
                return r.status


async def upload_file8(session, f2ul, token, endpoint, ftype="general"):
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    fname = os.path.basename(f2ul)
    fwords = f2ul.split("/")
    relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

    fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
    logger_helper.debug("fopreqs:"+json.dumps(fopreqs))

    # get presigned URL
    res = await send_file_op_request_to_cloud8(session, fopreqs, token, endpoint)
    logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    resd = json.loads(res['body']['urls']['result'])
    logger_helper.debug("resd: "+json.dumps(resd))

    # now perform the upload of the presigned URL
    logger_helper.debug("f2ul:"+json.dumps(f2ul))
    resp = await send_file_with_presigned_url8(session, f2ul, resd['body'][0])
    #  logger_helper.debug("upload result: "+json.dumps(resp))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


# async def send_wan_chat_message(content, sender, token, endpoint):
#     variables = {
#         "content": content,
#         "sender": sender
#     }
#     query_string = gen_wan_send_chat_message_string(content['msg'])
#     headers = {
#         'Content-Type': "application/graphql",
#         'Authorization': token,
#         'cache-control': "no-cache",
#     }
#     async with aiohttp.ClientSession() as session8:
#         async with session8.post(
#                 url=endpoint,
#                 timeout=aiohttp.ClientTimeout(total=300),
#                 headers=headers,
#                 json={
#                         'query': query_string,
#                         'variables': variables
#                 }
#         ) as response:
#             jresp = await response.json()
#             print(jresp)
#             return jresp



# async def wan_chat_subscribe(token, endpoint):
#     query_string = gen_wan_subscription_connection_string()
#     async def handle_message(websocket):
#         while True:
#             try:
#                 response = await websocket.recv()
#                 response_data = json.loads(response)
#                 if response_data["type"] == "data":
#                     message = response_data["payload"]["data"]["onMessageSent"]
#                     print("New message received:", message)
#             except websockets.exceptions.ConnectionClosedError:
#                 print("Connection lost. Attempting to reconnect...")
#                 break

#     while True:
#         try:
#             async with websockets.connect(endpoint, extra_headers={
#                 'Content-Type': 'application/json',
#                 'Authorization': token
#             }) as websocket:
#                 # Send connection init message
#                 init_msg = {
#                     "type": "connection_init"
#                 }
#                 await websocket.send(json.dumps(init_msg))

#                 # Wait for connection ack
#                 while True:
#                     response = await websocket.recv()
#                     response_data = json.loads(response)
#                     if response_data["type"] == "connection_ack":
#                         break

#                 # Start subscription
#                 sub_msg = {
#                     "id": "1",
#                     "type": "start",
#                     "payload": {
#                         "query": query_string,
#                         "variables": {}
#                     }
#                 }
#                 await websocket.send(json.dumps(sub_msg))

#                 await handle_message(websocket)
#         except Exception as e:
#             print(f"ErrorInternetConnectionLost: {e}. Retrying websocket connection in 5 seconds...")
#             await asyncio.sleep(5)



# def local_http_request(query_string, session, api_Key, endpoint):

#     headers = {
#         'Content-Type': "application/graphql",
#         'Authorization': token,
#         'cache-control': "no-cache",
#     }

#     # Now we can simply post the request...
#     response = session.request(
#         url=endpoint,
#         method='POST',
#         timeout=300,
#         headers=headers,
#         json={'query': query_string}
#     )
#     # save response to a log file. with a time stamp.
#     print(response)

#     jresp = response.json()

#     return jresp



async def wanSendRequestSolvePuzzle(msg_req, token, endpoint):
    variables = {
        "input": {
            "content": msg_req["content"],
            "chatID": msg_req["chatID"],
            "receiver": msg_req["receiver"],
            "parameters": msg_req["parameters"],
            "sender": msg_req["sender"]
        }
    }
    query_string = gen_wan_send_chat_message_string()
    headers = {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    async with aiohttp.ClientSession() as session8:
        async with session8.post(
                url=endpoint,
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
                json={
                        'query': query_string,
                        'variables': variables
                }
        ) as response:
            jresp = await response.json()
            print(jresp)
            return jresp

async def wanSendConfirmSolvePuzzle(msg_req, token, endpoint):
    variables = {
        "input": {
            "content": msg_req["content"],
            "chatID": msg_req["chatID"],
            "receiver": msg_req["receiver"],
            "parameters": msg_req["parameters"],
            "sender": msg_req["sender"]
        }
    }
    query_string = gen_wan_send_chat_message_string()
    headers = {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    async with aiohttp.ClientSession() as session8:
        async with session8.post(
                url=endpoint,
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
                json={
                        'query': query_string,
                        'variables': variables
                }
        ) as response:
            jresp = await response.json()
            print(jresp)
            return jresp


def scramble_api_key(ak):
    salted = f"ECB|{ak}"
    scrambled = base64.b64encode(salted.encode("utf-8")).decode("utf-8")
    return scrambled