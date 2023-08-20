import http.client
import json
import requests
import boto3
from boto3 import Session as AWSSession
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig
import logging
from requests_aws4auth import AWS4Auth
from datetime import datetime
from datetime import timedelta
from Logger import *
import os
import shutil

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

    print(file_name)
    print(object_name)
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

    #print("s3 bucket: ", my_bucket.objects)

    #for object_summary in my_bucket.objects.filter(Prefix="cognito/"):
    #   print(object_summary.key)
    # ==== end , conclusion, failed getting "NoCredentialsError"=========

    # from same link, but later comments:
    _BUCKET_NAME = 'winrpa'
    _PREFIX = 'EB/'
    s3_client = boto3.client('s3',  region_name='us-east-1',  aws_access_key_id="AWS_KEY_ID",  aws_secret_access_key="AWS_SECRET")
    """List files in specific S3 URL"""
    response = s3_client.list_objects(Bucket=_BUCKET_NAME, Prefix=_PREFIX)
    print("list s3 results:", response.get('Contents', []))
    for x in response.get('Contents', []):
        print("content::", x["Key"])

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
    print(r.status_code)

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


def gen_file_op_request_string(query):
    print("in query:", query)
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
    print(query_string)
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
    print("in query:", query)
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
        rec_string = rec_string + "factor: " + str(query[i]["factor"]) + " }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = """
    ]) 
    }"""
    query_string = query_string + rec_string + tail_string
    print(query_string)
    return query_string

# reqTrain(input: [Skill]!): AWSJSON!
def gen_train_request_string(query):
    query_string = """
        mutation MyMutation {
      reqTrain (input:[
    """
    rec_string = ""
    for i in range(len(query)):
        print("query: ", query[i])
        rec_string = rec_string + "{ skillName: \"" + query[i]["skillName"] + "\", "
        rec_string = rec_string + "skillFile: \"" + query[i]["skillFile"] + "\", "
        rec_string = rec_string + "imageFile: \"" + query[i]["imageFile"] + "\" }"
        if i != len(query) - 1:
            rec_string = rec_string + ', '

    tail_string = "])  }"
    query_string = query_string + rec_string + tail_string
    print(query_string)
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
    print(query_string)
    return query_string



def gen_schedule_request_string():
    query_string = "query MySchQuery { genSchedules(settings: \"{ \\\"testmode\\\": true, \\\"test_name\\\": \\\"5000\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    print(query_string)
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
    print(query_string)
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
    print(query_string)
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
            rec_string = rec_string + "location: \"" + bots[i].getLocation() + "\"} "


        if i != len(bots) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    print("query string:", query_string)
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
            rec_string = rec_string + "age: " + bots[i]["pubProfile"]["age"] + ", "
            rec_string = rec_string + "gender: \"" + bots[i]["pubProfile"]["gender"] + "\", "
            rec_string = rec_string + "interests: \"" + bots[i]["pubProfile"]["interests"] + "\", "
            rec_string = rec_string + "status: \"" + bots[i]["pubProfile"]["status"] + "\", "
            rec_string = rec_string + "levels: \"" + bots[i]["pubProfile"]["levels"] + "\", "
            rec_string = rec_string + "location: \"" + bots[i]["pubProfile"]["location"] + "\"} "
        else:
            rec_string = rec_string + "{ bid: \"" + str(bots[i].getBid()) + "\", "
            rec_string = rec_string + "owner: \"" + str(bots[i].getOwner()) + "\", "
            rec_string = rec_string + "roles: \"" + bots[i].getRoles() + "\", "
            rec_string = rec_string + "age: " + bots[i].getAge() + ", "
            rec_string = rec_string + "gender: \"" + bots[i].getGender() + "\", "
            rec_string = rec_string + "interests: \"" + bots[i].getInterests() + "\", "
            rec_string = rec_string + "status: \"" + bots[i].getStatus() + "\", "
            rec_string = rec_string + "levels: \"" + bots[i].getLevels() + "\", "
            rec_string = rec_string + "location: \"" + bots[i].getLocation() + "\"} "

        if i != len(bots) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    print(query_string)
    return query_string




def gen_remove_bots_string(removeOrders):
    query_string = """
        mutation MyRBMutation {
      removeBots (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string = rec_string + "{ id:\"" + str(removeOrders[i]["id"]) + "\", "
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
    print(query_string)
    return query_string



def gen_add_missions_string(missions):
    query_string = """
        mutation MyAMMutation {
      addMissions (input:[
    """
    rec_string = ""
    for i in range(len(missions)):
        if isinstance(missions[i], dict):
            rec_string = rec_string + "{ mid:\"" + str(missions[i]["pubAttributes"]["missionId"]) + "\", "
            rec_string = rec_string + "ticket:\"" + missions[i]["pubAttributes"]["ticket"] + "\", "
            rec_string = rec_string + "owner:\"" + missions[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:\"" + str(missions[i]["pubAttributes"]["bot_id"]) + "\", "
            rec_string = rec_string + "cuspas:\"" + missions[i]["pubAttributes"]["cuspas"] + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + missions[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "repeat:\"" + missions[i]["pubAttributes"]["repeat"] + "\", "
            rec_string = rec_string + "store:\"" + missions[i]["pubAttributes"]["pseudo_store"] + "\", "
            rec_string = rec_string + "asin:\"" + missions[i]["pubAttributes"]["pseudo_asin"] + "\", "
            rec_string = rec_string + "brand:\"" + missions[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i]["pubAttributes"]["ms_type"] + "\", "
            rec_string = rec_string + "skills:\"" + missions[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + missions[i]["pubAttributes"]["config"] + "\"} "
        else:
            rec_string = rec_string + "{ mid:\"" + str(missions[i].getMid()) + "\", "
            rec_string = rec_string + "ticket:\"" + missions[i].getTicket() + "\", "
            rec_string = rec_string + "owner:\"" + missions[i].getOwner() + "\", "
            rec_string = rec_string + "botid:\"" + str(missions[i].getBid()) + "\", "
            rec_string = rec_string + "cuspas:\"" + str(missions[i].getCusPAS()) + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i].getSearchCat() + "\", "
            rec_string = rec_string + "status:\"" + missions[i].getStatus() + "\", "
            rec_string = rec_string + "repeat:\"" + missions[i].getRepeat() + "\", "
            rec_string = rec_string + "store:\"" + missions[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin:" + missions[i].getPseudoASIN() + ", "
            rec_string = rec_string + "brand:\"" + missions[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i].getMtype() + "\", "
            rec_string = rec_string + "skills:\"" + missions[i].getSkills() + "\", "
            rec_string = rec_string + "config:\"" + missions[i].getConfig() + "\"} "

        if i != len(missions) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    print(query_string)
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
            rec_string = rec_string + "ticket:\"" + missions[i]["pubAttributes"]["ticket"] + "\", "
            rec_string = rec_string + "owner:\"" + missions[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:\"" + str(missions[i]["pubAttributes"]["botid"]) + "\", "
            rec_string = rec_string + "cuspas:\"" + str(missions[i]["pubAttributes"]["cuspas"]) + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + missions[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "repeat:\"" + missions[i]["pubAttributes"]["repeat"] + "\", "
            rec_string = rec_string + "store:\"" + str(missions[i]["pubAttributes"]["pseudo_store"]) + "\", "
            rec_string = rec_string + "asin:" + str(missions[i]["pubAttributes"]["pseudo_asin"]) + ", "
            rec_string = rec_string + "brand:\"" + missions[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i]["pubAttributes"]["mtype"] + "\", "
            rec_string = rec_string + "skills:\"" + missions[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + missions[i]["pubAttributes"]["config"] + "\"} "
        else:
            rec_string = rec_string + "{ mid:\"" + str(missions[i].getMid()) + "\", "
            rec_string = rec_string + "ticket:\"" + missions[i].getTicket() + "\", "
            rec_string = rec_string + "owner:\"" + missions[i].getOwner() + "\", "
            rec_string = rec_string + "botid:\"" + str(missions[i].getBid()) + "\", "
            rec_string = rec_string + "cuspas:\"" + str(missions[i].getCusPAS()) + "\", "
            rec_string = rec_string + "search_kw:\"" + missions[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat:\"" + missions[i].getSearchCat() + "\", "
            rec_string = rec_string + "status:\"" + missions[i].getStatus() + "\", "
            rec_string = rec_string + "repeat:\"" + missions[i].getRepeat() + "\", "
            rec_string = rec_string + "store:\"" + str(missions[i].getPseudoStore()) + "\", "
            rec_string = rec_string + "asin:" + str(missions[i].getPseudoASIN()) + ", "
            rec_string = rec_string + "brand:\"" + missions[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype:\"" + missions[i].getMtype() + "\", "
            rec_string = rec_string + "skills:\"" + missions[i].getSkills() + "\", "
            rec_string = rec_string + "config:\"" + missions[i].getConfig() + "\"} "

        if i != len(missions) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    print(query_string)
    return query_string


def gen_remove_missions_string(removeOrders):
    query_string = """
        mutation MyRMMutation {
      removeMissions (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string = rec_string + "{ id:\"" + str(removeOrders[i]["id"]) + "\", "
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
    print(query_string)
    return query_string


def gen_add_skills_string(skills):
    query_string = "mutation MyMutation { addSkills(input: ["
    rec_string = ""
    for i in range(len(skills)):
        if isinstance(skills[i], dict):
            rec_string = rec_string + "{ skid: " + str(skills[i]["skid"]) + ", "
            rec_string = rec_string + "owner: '" + str(skills[i]["owner"]) + "', "
            rec_string = rec_string + "platform: '" + skills[i]["platform"] + "', "
            rec_string = rec_string + "app: '" + skills[i]["app"] + "', "
            rec_string = rec_string + "site: '" + skills[i]["site"] + "', "
            rec_string = rec_string + "name: '" + skills[i]["name"] + "', "
            rec_string = rec_string + "path: '" + skills[i]["path"] + "', "
            rec_string = rec_string + "price_model: '" + skills[i]["price_model"] + "', "
            rec_string = rec_string + "price: '" + skills[i]["price"] + "', "
            rec_string = rec_string + "privacy: '" + skills[i]["privacy"] + "'} "
        else:
            rec_string = rec_string + "{ skid: " + str(skills[i].getSkid()) + ", "
            rec_string = rec_string + "owner: '" + str(skills[i].getOwner()) + "', "
            rec_string = rec_string + "platform: '" + skills[i].getPlatform() + "', "
            rec_string = rec_string + "app: '" + skills[i].getApp() + "', "
            rec_string = rec_string + "site: '" + skills[i].getSite() + "', "
            rec_string = rec_string + "name: '" + skills[i].getName() + "', "
            rec_string = rec_string + "path: '" + skills[i].getPath() + "', "
            rec_string = rec_string + "price_model: '" + skills[i].getPriceModel() + "', "
            rec_string = rec_string + "price: '" + skills[i].getPrice() + "', "
            rec_string = rec_string + "privacy: '" + skills[i].getPrivacy() + "'} "

        if i != len(skills) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    print(query_string)
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
            rec_string = rec_string + "owner: '" + str(skills[i]["owner"]) + "', "
            rec_string = rec_string + "platform: '" + skills[i]["platform"] + "', "
            rec_string = rec_string + "app: '" + skills[i]["app"] + "', "
            rec_string = rec_string + "site: '" + skills[i]["site"] + "', "
            rec_string = rec_string + "name: '" + skills[i]["name"] + "', "
            rec_string = rec_string + "path: '" + skills[i]["path"] + "', "
            rec_string = rec_string + "price_model: '" + skills[i]["price_model"] + "', "
            rec_string = rec_string + "price: '" + skills[i]["price"] + "', "
            rec_string = rec_string + "privacy: '" + skills[i]["privacy"] + "'} "
        else:
            rec_string = rec_string + "{ skid: " + str(skills[i].getSkid()) + ", "
            rec_string = rec_string + "owner: '" + str(skills[i].getOwner()) + "', "
            rec_string = rec_string + "platform: '" + skills[i].getPlatform() + "', "
            rec_string = rec_string + "app: '" + skills[i].getApp() + "', "
            rec_string = rec_string + "site: '" + skills[i].getSite() + "', "
            rec_string = rec_string + "name: '" + skills[i].getName() + "', "
            rec_string = rec_string + "path: '" + skills[i].getPath() + "', "
            rec_string = rec_string + "price_model: '" + skills[i].getPriceModel() + "', "
            rec_string = rec_string + "price: '" + skills[i].getPrice() + "', "
            rec_string = rec_string + "privacy: '" + skills[i].getPrivacy() + "'} "

        if i != len(skills) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    print(query_string)
    return query_string




def gen_remove_skills_string(removeOrders):
    query_string = """
        mutation MyRBMutation {
      removeSkills (input:[
    """
    rec_string = ""
    for i in range(len(removeOrders)):
        rec_string = rec_string + "{ skid:\"" + str(removeOrders[i]["skid"]) + "\", "
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
    print(query_string)
    return query_string



def set_up_cloud():
    REGION = 'us-east-1'
    session = requests.Session()
    # session.auth = AWS4Auth(
    #     # An AWS 'ACCESS KEY' associated with an IAM user.
    #     ACCESS_KEY,
    #     # The 'secret' that goes with the above access key.
    #     SECRET_KEY,
    #     # The region you want to access.
    #     REGION,
    #     # The service you want to access.
    #     'appsync'
    # )

    return session

# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_schedule_request_to_cloud(session, token, logfile='C:/CrawlerData/scrape_log.txt'):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutation = gen_schedule_request_string()


    print('QUERY-------------->')
    print(mutation)
    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutation}
    )

    #save response to a log file. with a time stamp.
    print(response)
    words = 'send_mf_info_to_cloud========>\n' + dt + '\n'
    words = words + response.text
    #log2file(words, 'None', 'None', logfile)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["genSchedules"])

        print("reponse:", jresponse)

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_cloud_read_screen(session, request, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }


    query = gen_screen_read_request_string(request)


    print('MUTATION-------------->')
    print(query)

    print("requesting cloud screen read.....@" + dt + "\n")
    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        timeout=300,
        json={'query': query}
    )
    #save response to a log file. with a time stamp.
    words = 'cloud responded @  ========>\n' + dt + '\n'
    # format(item.encode("utf-8")
    words = words + response.text
    # log2file(words, 'None', 'None', logfile)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqScreenTxtRead"])

    return jresponse

# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def req_train_read_screen(session, request, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }


    query = gen_train_request_string(request)


    print('Query-------------->')
    print(query)
    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': query}
    )
    #save response to a log file. with a time stamp.
    words = 'send_mf_info_to_cloud========>\n' + dt + '\n'
    # format(item.encode("utf-8")
    words = words + response.text
    # print("the response is: ", response.text)
    # log2file(words, 'None', 'None', logfile)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqTrain"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_completion_status_to_cloud(session, stat, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }


    query = """
    query MyQuery {
    getPeople(attrs: [{
        number: 100,
        startAge: 40,
        endAge: 50,
        race: "",
        sex: "",
        locState: "CA",
        incomeLow: 1000,
        incomeHigh: 50000,
        orderID: "65598",
        customer: "sctisz@163.com"}]) {
      birthday
      emails
      firstName
      id
      lastName
      middleName
      phones
      suffix
      addrs {
        city
        endDate
        startDate
        state
        street1
        street2
        zip
      }
    }
  }
 """


    print('QUERY-------------->')
    print(query)
    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': query}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_bots_request_to_cloud(session, bots, token):
    print("bots:", bots)

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_add_bots_string(bots)

    # mutationInfo = 'mutation MyMutation { addBots(input: [{age: 10, bid: "0", gender: "", interests: "", location: "", owner: "", role: ""}])}'


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_bots_request_to_cloud(session, bots, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_update_bots_string(bots)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateBots"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_bots_request_to_cloud(session, removes, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_remove_bots_string(removes)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeBots"])

    return jresponse




# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_missions_request_to_cloud(session, missions, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_add_missions_string(missions)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR message: ", jresp["errors"][0]["message"])
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addMissions"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_missions_request_to_cloud(session, missions, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_update_missions_string(missions)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateMissions"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_missions_request_to_cloud(session, removes, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_remove_missions_string(removes)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeMissions"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_skills_request_to_cloud(session, bots, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_add_skills_string(bots)

    # mutationInfo = 'mutation MyMutation { addBots(input: [{age: 10, bid: "0", gender: "", interests: "", location: "", owner: "", role: ""}])}'


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addSkills"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_skills_request_to_cloud(session, bots, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_update_skills_string(bots)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_skills_request_to_cloud(session, removes, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_remove_skills_string(removes)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)
    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_open_acct_request_to_cloud(session, accts, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_open_acct_string(accts)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    #save response to a log file. with a time stamp.
    print(response)

    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_make_order_request_to_cloud(session, orders, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    mutationInfo = gen_make_order_string(orders)


    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': mutationInfo}
    )
    # save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addBots"])

    return jresponse


def gen_get_bot_string():
    query_string = "query MyGetBotQuery { getBots (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    print(query_string)
    return query_string



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_bots_request_to_cloud(session, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    queryInfo = gen_get_bot_string()

    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': queryInfo}
    )
    #save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getBots"])


    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_file_op_request_to_cloud(session, fops, token):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    queryInfo = gen_file_op_request_string(fops)

    # Now we can simply post the request...
    response = session.request(
        url=APPSYNC_API_ENDPOINT_URL,
        method='POST',
        headers=headers,
        json={'query': queryInfo}
    )
    #save response to a log file. with a time stamp.
    # print(response)

    jresp = response.json()
    print("file op response:", jresp)
    if "errors" in jresp:
        screen_error = True
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["reqFileOp"])

    return jresponse

def findIdx(list, element):
    try:
        index_value = list.index(element)
    except ValueError:
        index_value = -1
    return index_value


def upload_file(session, f2ul, token, ftype):
    print(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp1: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    fname = os.path.basename(f2ul)
    fwords = f2ul.split("/")
    relf2ul = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2ul)

    fopreqs = [{"op": "upload", "names": fname, "options": prefix}]
    print("fopreqs:", fopreqs)

    res = send_file_op_request_to_cloud(session, fopreqs, token)
    print("cloud response: ", res['body']['urls']['result'])
    print(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp2: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    resd = json.loads(res['body']['urls']['result'])
    print("resd: ", resd)

    # now perform the upload of the presigned URL
    print("f2ul:", f2ul)
    resp = send_file_with_presigned_url(f2ul, resd['body'][0])
    # print("upload result: ", resp)
    print(">>>>>>>>>>>>>>>>>>>>>file Upload time stamp: ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))



def download_file(session, f2dl, token, ftype):
    fname = os.path.basename(f2dl)
    fwords = f2dl.split("/")
    relf2dl = "/".join([t for i, t in enumerate(fwords) if i > findIdx(fwords, 'testdata')])
    prefix = ftype + "|" + os.path.dirname(f2dl)

    fopreqs = [{"op": "download", "names": fname, "options": prefix}]

    res = send_file_op_request_to_cloud(session, fopreqs, token)
    # print("cloud response: ", res['body']['urls']['result'])

    resd = json.loads(res['body']['urls']['result'])
    # print("cloud response data: ", resd)
    resp = get_file_with_presigned_url(f2dl, resd['body'][0])
    #
    # print("resp:", resp)

# list dir on my cloud storage
def cloud_ls(session, token):
    flist = []
    fopreqs = [{"op" : "list", "names": "", "options": ""}]
    res = send_file_op_request_to_cloud(session, fopreqs, token)
    # print("cloud response: ", res['body']['urls']['result'])

    for k in res['body']["urls"][0]['Contents']:
        flist.append(k['Key'])

    return flist


def cloud_rm(session, f2rm, token):
    fopreqs = [{"op": "delete", "names": f2rm, "options": ""}]
    res = send_file_op_request_to_cloud(session, fopreqs, token)
    print("cloud response: ", res['body'])


