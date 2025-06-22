import json
import os
import re
from datetime import datetime
import base64
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
from aiolimiter import AsyncLimiter
from bot.Cloud import *

limiter = AsyncLimiter(1, 1)  # Max 5 requests per second

ecb_data_homepath = getECBotDataHome()
# Constants Copied from AppSync API 'Settings'
API_URL = 'https://w3lhm34x5jgxlbpr7zzxx7ckqq.appsync-api.ap-southeast-2.amazonaws.com/graphql'


#	requestRunExtAgentSkill(input: [SkillRun]): AWSJSON!
# 	skid: ID!
# 	owner: String
# 	name: String
# 	start: AWSDateTime
# 	in_data: AWSJSON!
# 	verbose: Boolean
def gen_query_reqest_run_ext_agent_skill_string(query):
    logger_helper.debug("in query:"+json.dumps(query))
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
    logger_helper.debug(query_string)
    return query_string

#
def gen_query_report_run_ext_agent_skill_status_string(query):
    logger_helper.debug("in query:"+json.dumps(query))
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
    logger_helper.debug(query_string)
    return query_string



def gen_add_agents_string(bots):
    query_string = "mutation MyMutation { addAgents(input: ["
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


def gen_update_agents_string(bots):
    query_string = """
        mutation MyUBMutation {
      updateAgents (input:[
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




def gen_remove_agents_string(removeOrders):
    query_string = """
        mutation MyRBMutation {
      removeAgents (input:[
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


def gen_query_agents_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MyBOTQuery { queryAgents(qb: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MyBOTQuery { queryAgents(qb: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string

def gen_get_agents_string():
    query_string = "query MyGetBotQuery { getAgents (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_add_agent_skills_string(skills):
    query_string = "mutation MyMutation { addAgentSkills(input: ["
    rec_string = ""
    for i in range(len(skills)):
        if isinstance(skills[i], dict):
            rec_string = rec_string + "{ askid: " + str(skills[i]["askid"]) + ", "
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





def gen_update_agent_skills_string(skills):
    query_string = """
        mutation MyUBMutation {
      updateAgentSkills (input:[
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




def gen_remove_agent_skills_string(removeOrders):
    query_string = """
        mutation MyRBMutation {
      removeAgentSkills (input:[
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



def gen_query_agent_skills_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MySkQuery { queryAgentSkills(qs: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { queryAgentSkills(qs: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string





def gen_add_agent_tasks_string(missions, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addAgentTasks (input:[
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


def gen_remove_agent_tasks_string(removeOrders):
    query_string = """
        mutation MyRMMutation {
      removeAgentTasks (input:[
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



def gen_update_agent_tasks_string(missions):
    query_string = """
        mutation MyUMMutation {
      updateAgentTasks (input:[
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
    logger_helper.debug(query_string)
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
    logger_helper.debug(query_string)
    return query_string



def gen_add_agent_tools_string(tools, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addAgentTools (input:[
    """
    rec_string = ""
    for i in range(len(tools)):
        if isinstance(tools[i], dict):
            rec_string = rec_string + "{ mid:" + str(tools[i]["pubAttributes"]["missionId"]) + ", "
            rec_string = rec_string + "ticket:" + str(tools[i]["pubAttributes"]["ticket"]) + ", "
            rec_string = rec_string + "owner:\"" + tools[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:" + str(tools[i]["pubAttributes"]["bot_id"]) + ", "
            rec_string = rec_string + "cuspas:\"" + tools[i]["pubAttributes"]["cuspas"] + "\", "
            rec_string = rec_string + "search_kw:\"" + tools[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + tools[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + tools[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "trepeat:" + str(tools[i]["pubAttributes"]["repeat"]) + ", "
            rec_string = rec_string + "stores:\"" + tools[i]["pubAttributes"]["pseudo_store"] + "\", "
            rec_string = rec_string + "asin:\"" + tools[i]["pubAttributes"]["pseudo_asin"] + "\", "
            rec_string = rec_string + "brand:\"" + tools[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + tools[i]["pubAttributes"]["ms_type"] + "\", "
            rec_string = rec_string + "esd:\"" + tools[i]["pubAttributes"]["esd"] + "\", "
            rec_string = rec_string + "as_server:" + str(int(tools[i]["pubAttributes"]["as_server"])) + ", "
            rec_string = rec_string + "skills:\"" + tools[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + tools[i]["pubAttributes"]["config"].replace('"', '\\"') + "\"} "
        else:
            rec_string = rec_string + "{ mid:" + str(tools[i].getMid()) + ", "
            rec_string = rec_string + "ticket:" + str(tools[i].getTicket()) + ", "
            rec_string = rec_string + "owner:\"" + tools[i].getOwner() + "\", "
            rec_string = rec_string + "botid:" + str(tools[i].getBid()) + ", "
            rec_string = rec_string + "cuspas:\"" + str(tools[i].getCusPAS()) + "\", "
            rec_string = rec_string + "search_kw:\"" + tools[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat:\"" + tools[i].getSearchCat() + "\", "
            rec_string = rec_string + "status:\"" + tools[i].getStatus() + "\", "
            rec_string = rec_string + "trepeat:" + str(tools[i].getRetry()) + ", "
            rec_string = rec_string + "stores:\"" + tools[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin:\"" + tools[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand:\"" + tools[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype:\"" + tools[i].getMtype() + "\", "
            rec_string = rec_string + "esd:\"" + tools[i].getEsd() + "\", "
            rec_string = rec_string + "as_server:" + str(int(tools[i].getAsServer())) + ", "
            rec_string = rec_string + "skills:\"" + tools[i].getSkills() + "\", "
            rec_string = rec_string + "config:\"" + tools[i].getConfig().replace('"', '\\"') + "\"} "

        if i != len(tools) - 1:
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


def gen_remove_agent_tools_string(removeOrders):
    query_string = """
        mutation MyRMMutation {
      removeAgentTools (input:[
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



def gen_update_agent_tools_string(tools):
    query_string = """
        mutation MyUMMutation {
      updateAgentTools (input:[
    """
    rec_string = ""
    for i in range(len(tools)):
        if isinstance(tools[i], dict):
            rec_string = rec_string + "{ mid:\"" + str(tools[i]["pubAttributes"]["missionId"]) + "\", "
            rec_string = rec_string + "ticket:\"" + str(tools[i]["pubAttributes"]["ticket"]) + "\", "
            rec_string = rec_string + "owner:\"" + tools[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:\"" + str(tools[i]["pubAttributes"]["botid"]) + "\", "
            rec_string = rec_string + "cuspas:\"" + str(tools[i]["pubAttributes"]["cuspas"]) + "\", "
            rec_string = rec_string + "search_kw:\"" + tools[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + tools[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + tools[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "trepeat:" + str(tools[i]["pubAttributes"]["repeat"]) + ", "
            rec_string = rec_string + "stores:\"" + str(tools[i]["pubAttributes"]["pseudo_store"]) + "\", "
            rec_string = rec_string + "asin:" + str(tools[i]["pubAttributes"]["pseudo_asin"]) + ", "
            rec_string = rec_string + "brand:\"" + tools[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + tools[i]["pubAttributes"]["mtype"] + "\", "
            rec_string = rec_string + "esd:\"" + tools[i]["pubAttributes"]["esd"] + "\", "
            rec_string = rec_string + "as_server:" + str(int(tools[i]["pubAttributes"]["as_server"])) + ", "
            rec_string = rec_string + "skills:\"" + tools[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + tools[i]["pubAttributes"]["config"].replace('"', '\\"') + "\"} "
        else:
            rec_string = rec_string + "{ mid: " + str(tools[i].getMid()) + ", "
            rec_string = rec_string + "ticket: " + str(tools[i].getTicket()) + ", "
            rec_string = rec_string + "owner: \"" + tools[i].getOwner() + "\", "
            rec_string = rec_string + "botid:" + str(tools[i].getBid()) + ", "
            rec_string = rec_string + "cuspas: \"" + tools[i].getCusPAS() + "\", "
            rec_string = rec_string + "search_kw: \"" + tools[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat: \"" + tools[i].getSearchCat() + "\", "
            rec_string = rec_string + "status: \"" + tools[i].getStatus() + "\", "
            rec_string = rec_string + "trepeat: " + str(tools[i].getRetry()) + ", "
            rec_string = rec_string + "stores: \"" + tools[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin: \"" + tools[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand: \"" + tools[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype: \"" + tools[i].getMtype() + "\", "
            rec_string = rec_string + "esd: \"" + tools[i].getEsd() + "\", "
            rec_string = rec_string + "as_server: " + str(int(tools[i].getAsServer())) + ", "
            rec_string = rec_string + "skills: \"" + tools[i].getSkills() + "\", "
            rec_string = rec_string + "config: \"" + tools[i].getConfig().replace('"', '\\"') + "\"} "

        if i != len(tools) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_query_agent_tools_by_time_string(query):

    query_string = """
        query MyQuery {
      queryAgentTools (qm:[
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


def gen_query_agent_tools_string(query):
    query_string = """
        query MyQuery {
      queryAgentTools (qm:[
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




def gen_add_knowledges_string(knowledges, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(knowledges)):
        if isinstance(knowledges[i], dict):
            rec_string = rec_string + "{ mid:" + str(knowledges[i]["pubAttributes"]["missionId"]) + ", "
            rec_string = rec_string + "ticket:" + str(knowledges[i]["pubAttributes"]["ticket"]) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:" + str(knowledges[i]["pubAttributes"]["bot_id"]) + ", "
            rec_string = rec_string + "cuspas:\"" + knowledges[i]["pubAttributes"]["cuspas"] + "\", "
            rec_string = rec_string + "search_kw:\"" + knowledges[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + knowledges[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "trepeat:" + str(knowledges[i]["pubAttributes"]["repeat"]) + ", "
            rec_string = rec_string + "stores:\"" + knowledges[i]["pubAttributes"]["pseudo_store"] + "\", "
            rec_string = rec_string + "asin:\"" + knowledges[i]["pubAttributes"]["pseudo_asin"] + "\", "
            rec_string = rec_string + "brand:\"" + knowledges[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + knowledges[i]["pubAttributes"]["ms_type"] + "\", "
            rec_string = rec_string + "esd:\"" + knowledges[i]["pubAttributes"]["esd"] + "\", "
            rec_string = rec_string + "as_server:" + str(int(knowledges[i]["pubAttributes"]["as_server"])) + ", "
            rec_string = rec_string + "skills:\"" + knowledges[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + knowledges[i]["pubAttributes"]["config"].replace('"', '\\"') + "\"} "
        else:
            rec_string = rec_string + "{ mid:" + str(knowledges[i].getMid()) + ", "
            rec_string = rec_string + "ticket:" + str(knowledges[i].getTicket()) + ", "
            rec_string = rec_string + "owner:\"" + knowledges[i].getOwner() + "\", "
            rec_string = rec_string + "botid:" + str(knowledges[i].getBid()) + ", "
            rec_string = rec_string + "cuspas:\"" + str(knowledges[i].getCusPAS()) + "\", "
            rec_string = rec_string + "search_kw:\"" + knowledges[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat:\"" + knowledges[i].getSearchCat() + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i].getStatus() + "\", "
            rec_string = rec_string + "trepeat:" + str(knowledges[i].getRetry()) + ", "
            rec_string = rec_string + "stores:\"" + knowledges[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin:\"" + knowledges[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand:\"" + knowledges[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype:\"" + knowledges[i].getMtype() + "\", "
            rec_string = rec_string + "esd:\"" + knowledges[i].getEsd() + "\", "
            rec_string = rec_string + "as_server:" + str(int(knowledges[i].getAsServer())) + ", "
            rec_string = rec_string + "skills:\"" + knowledges[i].getSkills() + "\", "
            rec_string = rec_string + "config:\"" + knowledges[i].getConfig().replace('"', '\\"') + "\"} "

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
    logger_helper.debug(query_string)
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
    logger_helper.debug(query_string)
    return query_string



def gen_update_knowledges_string(knowledges):
    query_string = """
        mutation MyUMMutation {
      updateKnowledges (input:[
    """
    rec_string = ""
    for i in range(len(knowledges)):
        if isinstance(knowledges[i], dict):
            rec_string = rec_string + "{ mid:\"" + str(knowledges[i]["pubAttributes"]["missionId"]) + "\", "
            rec_string = rec_string + "ticket:\"" + str(knowledges[i]["pubAttributes"]["ticket"]) + "\", "
            rec_string = rec_string + "owner:\"" + knowledges[i]["pubAttributes"]["owner"] + "\", "
            rec_string = rec_string + "botid:\"" + str(knowledges[i]["pubAttributes"]["botid"]) + "\", "
            rec_string = rec_string + "cuspas:\"" + str(knowledges[i]["pubAttributes"]["cuspas"]) + "\", "
            rec_string = rec_string + "search_kw:\"" + knowledges[i]["pubAttributes"]["search_kw"] + "\", "
            rec_string = rec_string + "search_cat:\"" + knowledges[i]["pubAttributes"]["search_cat"] + "\", "
            rec_string = rec_string + "status:\"" + knowledges[i]["pubAttributes"]["status"] + "\", "
            rec_string = rec_string + "trepeat:" + str(knowledges[i]["pubAttributes"]["repeat"]) + ", "
            rec_string = rec_string + "stores:\"" + str(knowledges[i]["pubAttributes"]["pseudo_store"]) + "\", "
            rec_string = rec_string + "asin:" + str(knowledges[i]["pubAttributes"]["pseudo_asin"]) + ", "
            rec_string = rec_string + "brand:\"" + knowledges[i]["pubAttributes"]["pseudo_brand"] + "\", "
            rec_string = rec_string + "mtype:\"" + knowledges[i]["pubAttributes"]["mtype"] + "\", "
            rec_string = rec_string + "esd:\"" + knowledges[i]["pubAttributes"]["esd"] + "\", "
            rec_string = rec_string + "as_server:" + str(int(knowledges[i]["pubAttributes"]["as_server"])) + ", "
            rec_string = rec_string + "skills:\"" + knowledges[i]["pubAttributes"]["skills"] + "\", "
            rec_string = rec_string + "config:\"" + knowledges[i]["pubAttributes"]["config"].replace('"', '\\"') + "\"} "
        else:
            rec_string = rec_string + "{ mid: " + str(knowledges[i].getMid()) + ", "
            rec_string = rec_string + "ticket: " + str(knowledges[i].getTicket()) + ", "
            rec_string = rec_string + "owner: \"" + knowledges[i].getOwner() + "\", "
            rec_string = rec_string + "botid:" + str(knowledges[i].getBid()) + ", "
            rec_string = rec_string + "cuspas: \"" + knowledges[i].getCusPAS() + "\", "
            rec_string = rec_string + "search_kw: \"" + knowledges[i].getSearchKW() + "\", "
            rec_string = rec_string + "search_cat: \"" + knowledges[i].getSearchCat() + "\", "
            rec_string = rec_string + "status: \"" + knowledges[i].getStatus() + "\", "
            rec_string = rec_string + "trepeat: " + str(knowledges[i].getRetry()) + ", "
            rec_string = rec_string + "stores: \"" + knowledges[i].getPseudoStore() + "\", "
            rec_string = rec_string + "asin: \"" + knowledges[i].getPseudoASIN() + "\", "
            rec_string = rec_string + "brand: \"" + knowledges[i].getPseudoBrand() + "\", "
            rec_string = rec_string + "mtype: \"" + knowledges[i].getMtype() + "\", "
            rec_string = rec_string + "esd: \"" + knowledges[i].getEsd() + "\", "
            rec_string = rec_string + "as_server: " + str(int(knowledges[i].getAsServer())) + ", "
            rec_string = rec_string + "skills: \"" + knowledges[i].getSkills() + "\", "
            rec_string = rec_string + "config: \"" + knowledges[i].getConfig().replace('"', '\\"') + "\"} "

        if i != len(knowledges) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = """
    ) 
    } """
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string



def gen_query_knowledges_by_time_string(query):

    query_string = """
        query MyQuery {
      queryKnowledges (qm:[
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


def gen_query_knowledges_string(query):
    query_string = """
        query MyQuery {
      queryKnowledges (qm:[
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





def gen_update_agent_tasks_ex_status_string(tasksStats):
    query_string = """
            mutation updateAgentTasksExStatus {
          updateAgentTasksExStatus (input:[
        """
    rec_string = ""
    for i in range(len(tasksStats)):
        if isinstance(tasksStats[i], dict):
            rec_string = rec_string + "{ mid:" + str(tasksStats[i]["mid"]) + ", "
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
    logger_helper.debug("DAILY REPORT QUERY STRING:"+query_string)
    return query_string




def send_update_agent_tasks_ex_status_to_cloud(session, missionStats, token, endpoint):
    if len(missionStats) > 0:
        query = gen_update_agent_tasks_ex_status_string(missionStats)

        jresp = appsync_http_request(query, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            jresponse = jresp["errors"][0]
            logger_helper.error("ERROR Type: " + json.dumps(jresponse["errorType"]) + " ERROR Info: " + json.dumps(jresponse["message"]))
        else:
            jresponse = json.loads(jresp["data"]["updateAgentTasksExStatus"])
    else:
        logger_helper.error("ERROR Type: EMPTY DAILY REPORTS")
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
            logger_helper.error("ERROR Type: " + json.dumps(jresponse["errorType"]) + " ERROR Info: " + json.dumps(jresponse["message"]))
        else:
            jresponse = json.loads(jresp["data"]["reportTaskStatus"])
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

# =================================================================================================
# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agents_request_to_cloud(session, bots, token, endpoint):

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
def send_update_agents_request_to_cloud(session, bots, token, endpoint):

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
def send_remove_agents_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_bots_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeBots"])
    return jresponse




def send_query_agents_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agents_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryAgents"])
        # print("jresponse", jresponse)

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agents_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_agents_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getAgents"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agent_skills_request_to_cloud(session, skills, token, endpoint):

    mutationInfo = gen_add_agent_skills_string(skills)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addAgentSkills"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_agent_skills_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_update_agent_skills_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateAgentSkills"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_agent_skills_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_agent_skills_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgentSkills"])

    return jresponse


def send_query_agent_skills_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agent_skills_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryAgentSkills"])


    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agent_tasks_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_add_missions_string(tasks)

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
def send_update_agent_tasks_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_update_missions_string(tasks)

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
def send_remove_agent_tasks_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_agent_tasks_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgentTasks"])

    return jresponse



def send_query_agent_tasks_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agent_tasks_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryAgentTasks"])


    return jresponse


def send_query_agent_tasks_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_agent_tasks_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
            jresponse = jresp["errors"][0]
        else:
            jresponse = json.loads(jresp["data"]["queryAgentTasks"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryAgentTasksByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryAgentTasksByTime traceback information not available:" + str(e)
        print(ex_stat)
        jresponse = {}

    return jresponse


def send_query_manager_agent_tasks_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_manager_agent_tasks_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
            jresponse = jresp["errors"][0]
        else:
            jresponse = json.loads(jresp["data"]["getManagerAgentTasks"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryManagerAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryManagerAgentTasks traceback information not available:" + str(e)
        print(ex_stat)
        jresponse = {}

    return jresponse



def send_update_knowledges_request_to_cloud(session, vehicles, token, endpoint):

    mutationInfo = gen_update_knowledges_string(vehicles)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateknowledges"])

    return jresponse














