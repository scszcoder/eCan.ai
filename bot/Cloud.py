import json
import os
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

ecb_data_homepath = getECBotDataHome()
# Constants Copied from AppSync API 'Settings'
API_URL = 'https://w3lhm34x5jgxlbpr7zzxx7ckqq.appsync-api.ap-southeast-2.amazonaws.com/graphql'

def direct_send_screen(file_name, bucket="winrpa"):
    response = "nothing"
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """
    # Set the desired multipart threshold value (5GB)
    GB = 1024 ** 3
    config = TransferConfig(multipart_threshold=5 * GB)
    config = TransferConfig(max_concurrency=5)
    config = TransferConfig(use_threads=False)

    # for remote object full path:
    # username/os_app/site_page/task/filename.
    # the relative dir name should be the same, EC platform/date/
    # for example, ebay should be EB/D20220201/****
    # file name should be in the format of (8char)ownerID_timestamp.png
    object_name = os.path.basename(file_name)
    full_dir_name = os.path.dirname(file_name)
    subdirname5 = os.path.basename(full_dir_name)
    sub_dir_name5 = os.path.dirname(full_dir_name)
    subdirname4 = os.path.basename(sub_dir_name5)
    sub_dir_name4 = os.path.dirname(sub_dir_name5)
    subdirname3 = os.path.basename(sub_dir_name4)
    sub_dir_name3 = os.path.dirname(sub_dir_name4)
    subdirname2 = os.path.basename(sub_dir_name3)
    sub_dir_name2 = os.path.dirname(sub_dir_name3)
    subdirname1 = os.path.basename(sub_dir_name2)
    sub_dir_name1 = os.path.dirname(sub_dir_name2)
    subdirname0 = os.path.basename(sub_dir_name1)
    sub_dir_name0 = os.path.dirname(sub_dir_name1)

    object_name = subdirname0 + "/" + subdirname1 + "/" + subdirname2 + "/" + subdirname3 + "/" + subdirname4 + "/" + subdirname5 + "/" + object_name

    logger_helper.debug(file_name)
    logger_helper.debug(object_name)
    # Upload the file
    s3_client = boto3.client('s3',  region_name='us-east-1',  aws_access_key_id="AWS_KEY_ID",  aws_secret_access_key="AWS_SECRET")
    try:
        response = s3_client.upload_file(file_name, bucket, object_name, Config=config)
    except ClientError as e:
        logging.error(e)
        return str(e)
    return response


def download_file(file_name, bucket, object_name=None):
    s3 = boto3.client('s3')
    with open('FILE_NAME', 'wb') as f:
        s3.download_fileobj('BUCKET_NAME', 'OBJECT_NAME', f)


def list_s3_file():
    # method 1 per: https://stackoverflow.com/questions/27292145/python-boto-list-contents-of-specific-dir-in-bucket
    #s3 = boto3.resource('s3')
    #my_bucket = s3.Bucket('winrpa')

    #logger_helper.debug("s3 bucket: "+json.dumps(my_bucket.objects))

    #for object_summary in my_bucket.objects.filter(Prefix="cognito/"):
    #   logger_helper.debug(object_summary.key)
    # ==== end , conclusion, failed getting "NoCredentialsError"=========

    # from same link, but later comments:
    _BUCKET_NAME = 'winrpa'
    _PREFIX = 'EB/'
    s3_client = boto3.client('s3',  region_name='us-east-1',  aws_access_key_id="AWS_KEY_ID",  aws_secret_access_key="AWS_SECRET")
    """List files in specific S3 URL"""
    response = s3_client.list_objects(Bucket=_BUCKET_NAME, Prefix=_PREFIX)
    logger_helper.debug("list s3 results:"+json.dumps(response.get('Contents', [])))
    for x in response.get('Contents', []):
        logger_helper.debug("content::"+json.dumps(x["Key"]))

def get_presigned_url(target):
    s3_client = boto3.client('s3', region_name='us-east-1', aws_access_key_id="AWS_KEY_ID", aws_secret_access_key="AWS_SECRET")

    # Generate the presigned URL
    response = s3_client.generate_presigned_post(Bucket='winrpa', Key=target, ExpiresIn=120)

    print("get presign resp: ", response)
    return response

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
    if http_response.status_code == 200:
        with open(dest_file, 'wb') as f:
            #http_response.raw.decode_content = True
            #shutil.copyfileobj(http_response.raw, f)

            f.write(http_response.content)

            f.close()


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
        rec_string = rec_string + "product: " + str(int(query[i]["product"])) + ", "
        rec_string = rec_string + "orderID: \"\", "
        rec_string = rec_string + "payType: \"\", "
        rec_string = rec_string + "total: \"\", "
        rec_string = rec_string + "transactionID: \"\", "
        rec_string = rec_string + "customerMail: \"\", "
        rec_string = rec_string + "customerPhone: \"\", "
        rec_string = rec_string + "instructions: \"" + query[i]["instructions"] + "\", "
        rec_string = rec_string + "origin:  \"" + str(query[i]["origin"]) + "\"" + " }"

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
        query_string = "query MySkQuery { queryBots(qb: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { queryBots(qb: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_query_missions_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MySkQuery { queryMissions(qm: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { queryMissions(qm: \"{ \\\"byowneruser\\\": false "
        if "created_date_range" in q_setting:
            query_string = query_string + ", \\\"created_date_range\\\": \\\"" + q_setting["created_date_range"] + "\\\""

        if "status" in q_setting:
            query_string = query_string + ", \\\"status\\\":" + q_setting["status"] + "\\\","

        if "type" in q_setting:
            query_string = query_string + ", \\\"type\\\":" + q_setting["type"] + "\\\","

        if "phrase" in q_setting:
            query_string = query_string + ", \\\"phrase\\\":" + q_setting["phrase"] + "\\\","

        if "pseudo_store" in q_setting:
            query_string = query_string + ", \\\"pseudo_store\\\":" + q_setting["pseudo_store"] + "\\\""

        query_string = query_string + "}\") } "


    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_schedule_request_string(test_name, schedule_settings):
    if test_name == "":
        qvs = None
        query_string = "query MySchQuery { genSchedules(settings: \"{ \\\"testmode\\\": false, \\\"test_name\\\": \\\""+test_name+"\\\"}\") } "
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
            rec_string = rec_string + "birthday: \"" + bots[i].getPubBirthday() + "\", "
            rec_string = rec_string + "gender: \"" + bots[i].getGender() + "\", "
            rec_string = rec_string + "interests: \"" + bots[i].getInterests() + "\", "
            rec_string = rec_string + "status: \"" + bots[i].getStatus() + "\", "
            rec_string = rec_string + "levels: \"" + bots[i].getLevels() + "\", "
            rec_string = rec_string + "vehicle: \"" + bots[i].getv() + "\", "
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
            rec_string = rec_string + "birthday: " + bots[i]["pubProfile"]["pubbirthday"] + ", "
            rec_string = rec_string + "gender: \"" + bots[i]["pubProfile"]["gender"] + "\", "
            rec_string = rec_string + "interests: \"" + bots[i]["pubProfile"]["interests"] + "\", "
            rec_string = rec_string + "status: \"" + bots[i]["pubProfile"]["status"] + "\", "
            rec_string = rec_string + "levels: \"" + bots[i]["pubProfile"]["levels"] + "\", "
            rec_string = rec_string + "vehicle: \"" + bots[i]["pubProfile"]["vehicle"] + "\", "
            rec_string = rec_string + "location: \"" + bots[i]["pubProfile"]["location"] + "\"} "
        else:
            rec_string = rec_string + "{ bid: " + str(bots[i].getBid()) + ", "
            rec_string = rec_string + "owner: \"" + bots[i].getOwner() + "\", "
            rec_string = rec_string + "roles: \"" + bots[i].getRoles() + "\", "
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
            rec_string = rec_string + "store:\"" + missions[i]["pubAttributes"]["pseudo_store"] + "\", "
            rec_string = rec_string + "asin:\"" + missions[i]["pubAttributes"]["pseudo_asin"] + "\", "
            rec_string = rec_string + "brand:\"" + missions[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i]["pubAttributes"]["ms_type"] + "\", "
            rec_string = rec_string + "skills:\"" + missions[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + missions[i]["pubAttributes"]["config"] + "\"} "
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
            rec_string = rec_string + "store:\"" + missions[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin:\"" + missions[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand:\"" + missions[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i].getMtype() + "\", "
            rec_string = rec_string + "skills:\"" + missions[i].getSkills() + "\", "
            rec_string = rec_string + "config:\"" + missions[i].getConfig() + "\"} "

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
            rec_string = rec_string + "store:\"" + str(missions[i]["pubAttributes"]["pseudo_store"]) + "\", "
            rec_string = rec_string + "asin:" + str(missions[i]["pubAttributes"]["pseudo_asin"]) + ", "
            rec_string = rec_string + "brand:\"" + missions[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i]["pubAttributes"]["mtype"] + "\", "
            rec_string = rec_string + "skills:\"" + missions[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + missions[i]["pubAttributes"]["config"] + "\"} "
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
            rec_string = rec_string + "store: \"" + missions[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin: \"" + missions[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand: \"" + missions[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype: \"" + missions[i].getMtype() + "\", "
            rec_string = rec_string + "skills: \"" + missions[i].getSkills() + "\", "
            rec_string = rec_string + "config: \"" + missions[i].getConfig() + "\"} "

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

def gen_daily_update_string(missionsStats):
    query_string = """
            mutation MyUMMutation {
          reportStatus (input:[
        """
    rec_string = ""
    for i in range(len(missionsStats)):
        if isinstance(missionsStats[i], dict):
            rec_string = rec_string + "{ mid:\"" + str(missionsStats[i]["mid"]) + "\", "
            rec_string = rec_string + "bid:\"" + str(missionsStats[i]["bid"]) + "\", "
            rec_string = rec_string + "status:\"" + missionsStats[i]["status"] + "\", "
            rec_string = rec_string + "starttime:" + str(missionsStats[i]["starttime"]) + ", "
            rec_string = rec_string + "endtime:" + str(missionsStats[i]["endtime"]) + "} "
        else:
            rec_string = rec_string + "{ mid:\"" + str(missionsStats[i].getMid()) + "\", "
            rec_string = rec_string + "bid:\"" + str(missionsStats[i].getBid()) + "\", "
            rec_string = rec_string + "status:\"" + missionsStats[i].getStatus() + "\", "
            rec_string = rec_string + "starttime:\"" + missionsStats[i].getStartTime() + "\", "
            rec_string = rec_string + "endtime:\"" + missionsStats[i].getEndTime() + "\"} "

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


def gen_train_request_string(mStats):
    query_string = """
            mutation MyUBMutation {
          updateMissionsExStatus (input:[
        """
    rec_string = ""
    for i in range(len(mStats)):
        rec_string = rec_string + "{ mid: " + str(mStats[i]["mid"]) + ", "
        rec_string = rec_string + "bid: '" + str(mStats[i]["bid"]) + "', "
        rec_string = rec_string + "status: '" + mStats[i]["status"] + "', "
        rec_string = rec_string + "starttime: '" + mStats[i]["starttime"] + "', "
        rec_string = rec_string + "endtime: '" + mStats[i]["endtime"] + "'} "

        if i != len(mStats) - 1:
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
          updateMissionsExStatus (input:[
        """
    rec_string = ""
    for i in range(len(mStats)):
        rec_string = rec_string + "{ mid: " + str(mStats[i]["mid"]) + ", "
        rec_string = rec_string + "bid: '" + str(mStats[i]["bid"]) + "', "
        rec_string = rec_string + "status: '" + mStats[i]["status"] + "', "
        rec_string = rec_string + "starttime: '" + mStats[i]["starttime"] + "', "
        rec_string = rec_string + "endtime: '" + mStats[i]["endtime"] + "'} "

        if i != len(mStats) - 1:
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
    # send_msg_mutation = """
    #     mutation publish($input: WanChatMessageInput!) {
    #       publish(input: $input) {
    #         chatID
    #       }
    #     }
    #     """
    send_msg_mutation = """
        mutation publish($name: String!, $data: AWSJSON!) {
            publish(name: $name, data: $data) {
                name
                data
            }
        }
    """
    return send_msg_mutation

def gen_wan_subscription_connection_string():
    subscription_query = """
        subscription subscribe($name: String!) {
            subscribe(name: $name) {
                name
                data
            }
        }
    """
    return subscription_query

#
# def gen_wan_subscription_connection_string(wan_chat_req):
#     sub_conn_string = """
#         subscription onMessageSent {
#           onMessageSent {
#             id
#             content
#             sender
#             timestamp
#           }
#         }
#         """
#
#     return sub_conn_string


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
def send_schedule_request_to_cloud(session, token, ts_name, schedule_settings):

    mutation = gen_schedule_request_string(ts_name, schedule_settings)

    jresp = appsync_http_request2(mutation, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["genSchedules"])

        logger_helper.debug("reponse:"+json.dumps(jresponse))

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_cloud_read_screen(session, request, token):

    query = gen_screen_read_request_string(request)

    jresp = appsync_http_request(query, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


async def req_cloud_read_screen8(session, request, token):

    query = gen_screen_read_request_string(request)

    jresp = await appsync_http_request8(query, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse


def req_cloud_obtain_review(session, request, token):

    query = gen_obtain_review_request_string(request)

    jresp = appsync_http_request(query, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.debug("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["errorInfo"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getFB"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_train_read_screen(session, request, token):

    query = gen_train_request_string(request)

    jresp = appsync_http_request(query, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqTrain"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_completion_status_to_cloud(session, missionStats, token):
    if len(missionStats) > 0:
        query = gen_daily_update_string(missionStats)

        jresp = appsync_http_request(query, session, token)

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


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_bots_request_to_cloud(session, bots, token):

    mutationInfo = gen_add_bots_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_bots_request_to_cloud(session, bots, token):

    mutationInfo = gen_update_bots_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateBots"])
        logger_helper.error("updateBots Response: " + jresp["data"]["updateBots"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_bots_request_to_cloud(session, removes, token):

    mutationInfo = gen_remove_bots_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeBots"])
        logger_helper.error("removeBots Response: " + jresp["data"]["removeBots"])
    return jresponse




# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_missions_request_to_cloud(session, missions, token):

    mutationInfo = gen_add_missions_string(missions)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addMissions"])
        logger_helper.error("addMissions Response: " + jresp["data"]["addMissions"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_missions_request_to_cloud(session, missions, token):

    mutationInfo = gen_update_missions_string(missions)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateMissions"])
        logger_helper.error("updateMissions Response: " + jresp["data"]["updateMissions"])
    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_missions_request_to_cloud(session, removes, token):

    mutationInfo = gen_remove_missions_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeMissions"])
        logger_helper.error("removeMissions Response: " + jresp["data"]["removeMissions"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_skills_request_to_cloud(session, skills, token):

    mutationInfo = gen_add_skills_string(skills)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addSkills"])
        logger_helper.error("addSkills Response: " + jresp["data"]["addSkills"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_skills_request_to_cloud(session, bots, token):

    mutationInfo = gen_update_skills_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateSkills"])
        logger_helper.error("updateSkills Response: " + jresp["data"]["updateSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_skills_request_to_cloud(session, removes, token):

    mutationInfo = gen_remove_skills_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeSkills"])
        logger_helper.error("removeSkills Response: " + jresp["data"]["removeSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_open_acct_request_to_cloud(session, accts, token):

    mutationInfo = gen_open_acct_string(accts)

    jresp = appsync_http_request(mutationInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_make_order_request_to_cloud(session, orders, token):

    mutationInfo = gen_make_order_string(orders)

    jresp = appsync_http_request(mutationInfo, session, token)

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
def send_get_bots_request_to_cloud(session, token):

    queryInfo = gen_get_bot_string()

    jresp = appsync_http_request(queryInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getBots"])


    return jresponse

def send_query_skills_request_to_cloud(session, token, q_settings):

    queryInfo = gen_query_skills_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["querySkills"])


    return jresponse

def send_query_bots_request_to_cloud(session, token, q_settings):

    queryInfo = gen_query_bots_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryBots"])


    return jresponse

def send_query_missions_request_to_cloud(session, token, q_settings):

    queryInfo = gen_query_missions_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryMissions"])


    return jresponse



def send_query_chat_request_to_cloud(session, token, chat_request):

    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = appsync_http_request(queryInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])


    return jresponse


async def send_query_chat_request_to_cloud8(session, token, chat_request):

    queryInfo = gen_query_chat_request_string(chat_request)

    jresp = await appsync_http_request8(queryInfo, session, token)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryChats"])


    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_file_op_request_to_cloud(session, fops, token):

    queryInfo = gen_file_op_request_string(fops)

    jresp = appsync_http_request(queryInfo, session, token)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse


def send_account_info_request_to_cloud(session, acct_ops, token):

    queryInfo = gen_account_info_request_string(acct_ops)

    jresp = appsync_http_request(queryInfo, session, token)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqAccountInfo"])

    return jresponse



def send_feedback_request_to_cloud(session, fb_reqs, token):

    queryInfo = gen_feedback_request_string(fb_reqs)

    jresp = appsync_http_request(queryInfo, session, token)

    #  logger_helper.debug("file op response:"+json.dumps(jresp))
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqAccountInfo"])

    return jresponse



def findIdx(list, element):
    try:
        index_value = list.index(element)
    except ValueError:
        index_value = -1
    return index_value


def upload_file(session, f2ul, token, ftype):
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    fname = os.path.basename(f2ul)
    fwords = f2ul.split("/")
    relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

    fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
    logger_helper.debug("fopreqs:"+json.dumps(fopreqs))

    res = send_file_op_request_to_cloud(session, fopreqs, token)
    logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    resd = json.loads(res['body']['urls']['result'])
    logger_helper.debug("resd: "+json.dumps(resd))

    # now perform the upload of the presigned URL
    logger_helper.debug("f2ul:"+json.dumps(f2ul))
    resp = send_file_with_presigned_url(f2ul, resd['body'][0])
    #  logger_helper.debug("upload result: "+json.dumps(resp))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))



def download_file(session, f2dl, token, ftype):
    fname = os.path.basename(f2dl)
    fwords = f2dl.split("/")
    relf2dl = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2dl)

    fopreqs = [{"op": "download", "names": fname, "options": prefix}]

    res = send_file_op_request_to_cloud(session, fopreqs, token)
    # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

    resd = json.loads(res['body']['urls']['result'])
    # logger_helper.debug("cloud response data: "+json.dumps(resd))
    resp = get_file_with_presigned_url(f2dl, resd['body'][0])
    #
    # logger_helper.debug("resp:"+json.dumps(resp))

# list dir on my cloud storage
def cloud_ls(session, token):
    flist = []
    fopreqs = [{"op" : "list", "names": "", "options": ""}]
    res = send_file_op_request_to_cloud(session, fopreqs, token)
    # logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))

    for k in res['body']["urls"][0]['Contents']:
        flist.append(k['Key'])

    return flist


def cloud_rm(session, f2rm, token):
    fopreqs = [{"op": "delete", "names": f2rm, "options": ""}]
    res = send_file_op_request_to_cloud(session, fopreqs, token)
    logger_helper.debug("cloud response: "+json.dumps(res['body']))

def appsync_http_request(query_string, session, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    print(response)

    jresp = response.json()

    return jresp


def appsync_http_request2(query_string, session, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    print(response)

    jresp = response.json()

    return jresp


async def appsync_http_request8(query_string, session, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    async with aiohttp.ClientSession() as session8:
        async with session8.post(
                url=APPSYNC_API_ENDPOINT_URL,
                timeout=aiohttp.ClientTimeout(total=300),
                headers=headers,
                json={'query': query_string}
        ) as response:
            jresp = await response.json()
            print(jresp)
            return jresp


async def send_file_op_request_to_cloud8(session, fops, token):

    queryInfo = gen_file_op_request_string(fops)

    jresp = await appsync_http_request8(queryInfo, session, token)

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


async def upload_file8(session, f2ul, token, ftype):
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    fname = os.path.basename(f2ul)
    fwords = f2ul.split("/")
    relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2ul).replace("\\", "\\\\")

    fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
    logger_helper.debug("fopreqs:"+json.dumps(fopreqs))

    # get presigned URL
    res = await send_file_op_request_to_cloud8(session, fopreqs, token)
    logger_helper.debug("cloud response: "+json.dumps(res['body']['urls']['result']))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    resd = json.loads(res['body']['urls']['result'])
    logger_helper.debug("resd: "+json.dumps(resd))

    # now perform the upload of the presigned URL
    logger_helper.debug("f2ul:"+json.dumps(f2ul))
    resp = await send_file_with_presigned_url8(session, f2ul, resd['body'][0])
    #  logger_helper.debug("upload result: "+json.dumps(resp))
    logger_helper.debug(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: "+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


async def send_wan_chat_message(content, sender, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    variables = {
        "content": content,
        "sender": sender
    }
    query_string = gen_wan_send_chat_message_string(content['msg'])
    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    async with aiohttp.ClientSession() as session8:
        async with session8.post(
                url=APPSYNC_API_ENDPOINT_URL,
                timeout=aiohttp.ClientTimeout(total=300),
                headers=headers,
                json={
                        'query': query_string,
                        'variables': variables
                }
        ) as response:
            jresp = await response.json()
            print(jresp)
            return jresp



async def wan_chat_subscribe(token):
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    query_string = gen_wan_subscription_connection_string()
    async def handle_message(websocket):
        while True:
            try:
                response = await websocket.recv()
                response_data = json.loads(response)
                if response_data["type"] == "data":
                    message = response_data["payload"]["data"]["onMessageSent"]
                    print("New message received:", message)
            except websockets.exceptions.ConnectionClosedError:
                print("Connection lost. Attempting to reconnect...")
                break

    while True:
        try:
            async with websockets.connect(WS_URL, extra_headers={
                'Content-Type': 'application/json',
                'Authorization': token
            }) as websocket:
                # Send connection init message
                init_msg = {
                    "type": "connection_init"
                }
                await websocket.send(json.dumps(init_msg))

                # Wait for connection ack
                while True:
                    response = await websocket.recv()
                    response_data = json.loads(response)
                    if response_data["type"] == "connection_ack":
                        break

                # Start subscription
                sub_msg = {
                    "id": "1",
                    "type": "start",
                    "payload": {
                        "query": query_string,
                        "variables": {}
                    }
                }
                await websocket.send(json.dumps(sub_msg))

                await handle_message(websocket)
        except Exception as e:
            print(f"ErrorInternetConnectionLost: {e}. Retrying websocket connection in 5 seconds...")
            await asyncio.sleep(5)



def local_http_request(query_string, session, api_Key, url):

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    # Now we can simply post the request...
    response = session.request(
        url=url,
        method='POST',
        timeout=300,
        headers=headers,
        json={'query': query_string}
    )
    # save response to a log file. with a time stamp.
    print(response)

    jresp = response.json()

    return jresp



async def wanSendRequestSolvePuzzle(msg_req, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
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
                url=APPSYNC_API_ENDPOINT_URL,
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

async def wanSendConfirmSolvePuzzle(msg_req, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
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
                url=APPSYNC_API_ENDPOINT_URL,
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

