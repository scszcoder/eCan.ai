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

# Constants Copied from AppSync API 'Settings'
API_URL = 'https://w3lhm34x5jgxlbpr7zzxx7ckqq.appsync-api.ap-southeast-2.amazonaws.com/graphql'
API_KEY = 'da2-hgqwkvc7ezeqlp2nc5uih2zjca'
AWS_KEY_ID = 'AKIAZWU23DOOSVDIR6G3'
AWS_SECRET = '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'

def send_screen(file_name, bucket="winrpa"):
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
    s3_client = boto3.client('s3',  region_name='us-east-1',  aws_access_key_id=AWS_KEY_ID,  aws_secret_access_key=AWS_SECRET)
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
        rec_string = rec_string + "os: \"" + query[i]["os"] + "\", "
        rec_string = rec_string + "app: \"" + query[i]["app"] + "\", "
        rec_string = rec_string + "domain: \"" + query[i]["domain"] + "\", "
        rec_string = rec_string + "page: \"" + query[i]["page"] + "\", "
        rec_string = rec_string + "skill: \"" + query[i]["skill_name"] + "\", "
        rec_string = rec_string + "psk: \"" + query[i]["psk"] + "\", "
        rec_string = rec_string + "csk: \"" + query[i]["csk"] + "\", "
        rec_string = rec_string + "lastMove: \"" + query[i]["lastMove"] + "\", "
        rec_string = rec_string + "ssk: \"" + query[i]["ssk"] + "\", "
        rec_string = rec_string + "imageFile: \"" + query[i]["imageFile"] + "\" }"
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
    query_string = "query MySchQuery { genSchedules(settings: \"{}\") } "
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
        rec_string = rec_string + "{ age: " + str(bots[i]["age"]) + ", "
        rec_string = rec_string + "bid: '" + str(bots[i]["bid"]) + "', "
        rec_string = rec_string + "gender: '" + bots[i]["gender"] + "', "
        rec_string = rec_string + "interests: '" + bots[i]["interests"] + "', "
        rec_string = rec_string + "location: '" + bots[i]["location"] + "', "
        rec_string = rec_string + "owner: '" + bots[i]["owner"] + "', "
        rec_string = rec_string + "role: '" + bots[i]["role"] + "'} "


        if i != len(bots) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    print(query_string)
    return query_string


def gen_update_bots_string(bots):
    query_string = """
        mutation MyUBMutation {
      updateBots (input:[
    """
    rec_string = ""
    for i in range(len(bots)):
        rec_string = rec_string + "{ bid: " + str(bots[i]["bid"]) + ", "
        rec_string = rec_string + "owner: \"" + bots[i]["owner"] + "\", "
        rec_string = rec_string + "role: \"" + bots[i]["role"] + "\", "
        rec_string = rec_string + "age: " + bots[i]["age"] + ", "
        rec_string = rec_string + "gender: \"" + bots[i]["gender"] + "\", "
        rec_string = rec_string + "interests: \"" + bots[i]["interests"] + "\", "
        rec_string = rec_string + "location: \"" + bots[i]["location"] + "\"} "

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
        rec_string = rec_string + "{ mid:\"" + str(missions[i]["mid"]) + "\", "
        rec_string = rec_string + "owner:\"" + missions[i]["owner"] + "\", "
        rec_string = rec_string + "search_kw:\"" + missions[i]["search_kw"] + "\", "
        rec_string = rec_string + "search_cat:\"" + missions[i]["search_cat"] + "\", "
        rec_string = rec_string + "botid:\"" + str(missions[i]["botid"]) + "\", "
        rec_string = rec_string + "repeat:" + str(missions[i]["repeat"]) + ", "
        rec_string = rec_string + "status:\"" + missions[i]["status"] + "\", "
        rec_string = rec_string + "mtype:\"" + missions[i]["mtype"] + "\"} "

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
        rec_string = rec_string + "{ mid:\"" + str(missions[i]["mid"]) + "\", "
        rec_string = rec_string + "owner:\"" + missions[i]["owner"] + "\", "
        rec_string = rec_string + "search_kw:\"" + missions[i]["search_kw"] + "\", "
        rec_string = rec_string + "search_cat:\"" + missions[i]["search_cat"] + "\", "
        rec_string = rec_string + "botid:\"" + str(missions[i]["botid"]) + "\", "
        rec_string = rec_string + "repeat:" + str(missions[i]["repeat"]) + ", "
        rec_string = rec_string + "status:\"" + missions[i]["status"] + "\", "
        rec_string = rec_string + "mtype:\"" + missions[i]["mtype"] + "\"} "

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




def set_up_cloud():
    ACCESS_KEY = 'AKIAZWU23DOOSVDIR6G3'
    SECRET_KEY = '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'
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }


    query = gen_screen_read_request_string(request)


    print('MUTATION-------------->')
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }

    # mutationInfo = gen_add_bots_string(bots)

    mutationInfo = 'mutation MyMutation { addBots(input: [{age: 10, bid: "0", gender: "", interests: "", location: "", owner: "", role: ""}])}'


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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
        print("ERROR Type: ", jresp["errors"][0]["errorType"], "ERROR Info: ", jresp["errors"][0]["errorInfo"], )
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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
def send_open_acct_request_to_cloud(session, accts):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'x-api-key': APPSYNC_API_KEY,
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
def send_make_order_request_to_cloud(session, orders):

    status = 0
    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # As found in AWS Appsync under Settings for your endpoint.
    # Constants Copied from AppSync API 'Settings'

    receiverId = "***"
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
    # Use JSON format string for the query. It does not need reformatting.

    headers = {
        'Content-Type': "application/graphql",
        'x-api-key': APPSYNC_API_KEY,
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
    #APPSYNC_API_KEY = 'da2-cqfzsjuqqffypb266ypkszjf6u'
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

