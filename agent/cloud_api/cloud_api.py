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
from bot.Cloud import appsync_http_request, appsync_http_request8

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



def gen_add_agents_string(agents):
    query_string = "mutation MyMutation { addAgents(input: ["
    rec_string = ""
    for i in range(len(agents)):
        if isinstance(agents[i], dict):
            rec_string = rec_string + "{ agid: \"" + str(agents[i]["agid"]) + "\", "
            rec_string = rec_string + "owner: \"" + str(agents[i]["owner"]) + "\", "
            rec_string = rec_string + "gender: \"" + agents[i]["gender"] + "\", "
            rec_string = rec_string + "organizations: \"" + agents[i]["organizations"] + "\", "
            rec_string = rec_string + "rank: \"" + agents[i]["rank"] + "\", "
            rec_string = rec_string + "supervisors: \"" + agents[i]["supervisors"] + "\", "
            rec_string = rec_string + "subordinates: \"" + agents[i]["subordinates"] + "\", "
            rec_string = rec_string + "title: \"" + agents[i]["title"] + "\", "
            rec_string = rec_string + "personalities: \"" + agents[i]["personalities"] + "\", "
            rec_string = rec_string + "birthday: \"" + agents[i]["birthday"] + "\", "
            rec_string = rec_string + "name: \"" + agents[i]["name"] + "\", "
            rec_string = rec_string + "status: \"" + agents[i]["status"] + "\", "
            rec_string = rec_string + "metadata: \"" + agents[i]["metadata"] + "\", "
            rec_string = rec_string + "vehicle: \"" + agents[i]["vehicle"] + "\", "
            rec_string = rec_string + "skills: \"" + agents[i]["skills"] + "\", "
            rec_string = rec_string + "tasks: \"" + agents[i]["tasks"] + "\", "
            rec_string = rec_string + "knowledges: \"" + agents[i]["knowledges"] + "\"} "
        else:
            rec_string = rec_string + "{ agid: \"" + str(agents[i].getAgid()) + "\", "
            rec_string = rec_string + "owner: \"" + str(agents[i].getOwner()) + "\", "
            rec_string = rec_string + "gender: \"" + agents[i].getGender() + "\", "
            rec_string = rec_string + "organizations: \"" + agents[i].getOrganizations() + "\", "
            rec_string = rec_string + "rank: \"" + agents[i].getRank() + "\", "
            rec_string = rec_string + "supervisors: \"" + agents[i].getSupervisors() + "\", "
            rec_string = rec_string + "subordinates: \"" + agents[i].getSubordinates() + "\", "
            rec_string = rec_string + "title: \"" + agents[i].getTitle() + "\", "
            rec_string = rec_string + "personalities: \"" + agents[i].getPersonalities() + "\", "
            rec_string = rec_string + "birthday: \"" + agents[i].getBirthday() + "\", "
            rec_string = rec_string + "name: \"" + agents[i].getName() + "\", "
            rec_string = rec_string + "status: \"" + agents[i].getStatus() + "\", "
            rec_string = rec_string + "metadata: \"" + agents[i].getMetadata() + "\", "
            rec_string = rec_string + "vehicle: \"" + agents[i].getVehicle() + "\", "
            rec_string = rec_string + "skills: \"" + agents[i].getSkills() + "\", "
            rec_string = rec_string + "tasks: \"" + agents[i].getTasks() + "\", "
            rec_string = rec_string + "knowledges: \"" + agents[i].getKnowledges() + "\"} "


        if i != len(agents) - 1:
            rec_string = rec_string + ', '
        else:
            rec_string = rec_string + ']'

    tail_string = ") } "
    query_string = query_string + rec_string + tail_string
    logger_helper.debug("query string:"+query_string)
    return query_string


def gen_update_agents_string(agents):
    query_string = """
        mutation MyUBMutation {
      updateAgents (input:[
    """
    rec_string = ""
    for i in range(len(agents)):
        if isinstance(agents[i], dict):
            rec_string = rec_string + "{ agid: \"" + str(agents[i]["agid"]) + "\", "
            rec_string = rec_string + "owner: \"" + str(agents[i]["owner"]) + "\", "
            rec_string = rec_string + "gender: \"" + agents[i]["gender"] + "\", "
            rec_string = rec_string + "organizations: \"" + agents[i]["organizations"] + "\", "
            rec_string = rec_string + "rank: \"" + agents[i]["rank"] + "\", "
            rec_string = rec_string + "supervisors: \"" + agents[i]["supervisors"] + "\", "
            rec_string = rec_string + "subordinates: \"" + agents[i]["subordinates"] + "\", "
            rec_string = rec_string + "title: \"" + agents[i]["title"] + "\", "
            rec_string = rec_string + "personalities: \"" + agents[i]["personalities"] + "\", "
            rec_string = rec_string + "birthday: \"" + agents[i]["birthday"] + "\", "
            rec_string = rec_string + "name: \"" + agents[i]["name"] + "\", "
            rec_string = rec_string + "status: \"" + agents[i]["status"] + "\", "
            rec_string = rec_string + "metadata: \"" + agents[i]["metadata"] + "\", "
            rec_string = rec_string + "vehicle: \"" + agents[i]["vehicle"] + "\", "
            rec_string = rec_string + "skills: \"" + agents[i]["skills"] + "\", "
            rec_string = rec_string + "tasks: \"" + agents[i]["tasks"] + "\", "
            rec_string = rec_string + "knowledges: \"" + agents[i]["knowledges"] + "\"} "
        else:
            if agents[i].getOrg():
                org = agents[i].getOrg()
            else:
                org = ""
            rec_string = rec_string + "{ agid: \"" + str(agents[i].getAgid()) + "\", "
            rec_string = rec_string + "owner: \"" + str(agents[i].getOwner()) + "\", "
            rec_string = rec_string + "gender: \"" + agents[i].getGender() + "\", "
            rec_string = rec_string + "organizations: \"" + agents[i].getOrganizations() + "\", "
            rec_string = rec_string + "rank: \"" + agents[i].getRank() + "\", "
            rec_string = rec_string + "supervisors: \"" + agents[i].getSupervisors() + "\", "
            rec_string = rec_string + "subordinates: \"" + agents[i].getSubordinates() + "\", "
            rec_string = rec_string + "title: \"" + agents[i].getTitle() + "\", "
            rec_string = rec_string + "personalities: \"" + agents[i].getPersonalities() + "\", "
            rec_string = rec_string + "birthday: \"" + agents[i].getBirthday() + "\", "
            rec_string = rec_string + "name: \"" + agents[i].getName() + "\", "
            rec_string = rec_string + "status: \"" + agents[i].getStatus() + "\", "
            rec_string = rec_string + "metadata: \"" + agents[i].getMetadata() + "\", "
            rec_string = rec_string + "vehicle: \"" + agents[i].getVehicle() + "\", "
            rec_string = rec_string + "skills: \"" + agents[i].getSkills() + "\", "
            rec_string = rec_string + "tasks: \"" + agents[i].getTasks() + "\", "
            rec_string = rec_string + "knowledges: \"" + agents[i].getKnowledges() + "\"} "

        if i != len(agents) - 1:
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
        mutation MyRAMutation {
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
    query_string = "query MyGetAgentQuery { getAgents (ids:'"
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
            rec_string = rec_string + "name: \"" + skills[i]["name"] + "\", "
            rec_string = rec_string + "description: \"" + skills[i]["description"] + "\", "
            rec_string = rec_string + "status: \"" + skills[i]["status"] + "\", "
            rec_string = rec_string + "path: \"" + skills[i]["path"] + "\", "
            rec_string = rec_string + "flowgram: \"" + skills[i]["flowgram"] + "\", "
            rec_string = rec_string + "langgraph: \"" + skills[i]["langgraph"] + "\", "
            rec_string = rec_string + "config: " + str(skills[i]["config"]) + ", "
            rec_string = rec_string + "price: " + str(skills[i]["price"]) + "\"} "
        else:
            rec_string = rec_string + "{ askid: " + str(skills[i].getSkid()) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i].getOwner()) + "\", "
            rec_string = rec_string + "name: \"" + skills[i].getName() + "\", "
            rec_string = rec_string + "description: \"" + skills[i].getDescription() + "\", "
            rec_string = rec_string + "status: \"" + skills[i].getStatus() + "\", "
            rec_string = rec_string + "path: \"" + skills[i].getPath() + "\", "
            rec_string = rec_string + "flowgram: \"" + skills[i].getFlowgram() + "\", "
            rec_string = rec_string + "langgraph: \"" + skills[i].getLanggraph() + "\", "
            rec_string = rec_string + "config: " + str(skills[i].getConfig()) + ", "
            rec_string = rec_string + "price: " + str(skills[i].getPrice()) + "\"} "

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
        mutation MyUASMutation {
      updateAgentSkills (input:[
    """
    rec_string = ""
    for i in range(len(skills)):
        if isinstance(skills[i], dict):
            rec_string = rec_string + "{ askid: " + str(skills[i]["askid"]) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i]["owner"]) + "\", "
            rec_string = rec_string + "name: \"" + skills[i]["name"] + "\", "
            rec_string = rec_string + "description: \"" + skills[i]["description"] + "\", "
            rec_string = rec_string + "status: \"" + skills[i]["status"] + "\", "
            rec_string = rec_string + "path: \"" + skills[i]["path"] + "\", "
            rec_string = rec_string + "flowgram: \"" + skills[i]["flowgram"] + "\", "
            rec_string = rec_string + "langgraph: \"" + skills[i]["langgraph"] + "\", "
            rec_string = rec_string + "config: " + str(skills[i]["config"]) + ", "
            rec_string = rec_string + "price: " + str(skills[i]["price"]) + "\"} "
        else:
            rec_string = rec_string + "{ askid: " + str(skills[i].getSkid()) + ", "
            rec_string = rec_string + "owner: \"" + str(skills[i].getOwner()) + "\", "
            rec_string = rec_string + "name: \"" + skills[i].getName() + "\", "
            rec_string = rec_string + "description: \"" + skills[i].getDescription() + "\", "
            rec_string = rec_string + "status: \"" + skills[i].getStatus() + "\", "
            rec_string = rec_string + "path: \"" + skills[i].getPath() + "\", "
            rec_string = rec_string + "flowgram: \"" + skills[i].getFlowgram() + "\", "
            rec_string = rec_string + "langgraph: \"" + skills[i].getLanggraph() + "\", "
            rec_string = rec_string + "config: " + str(skills[i].getConfig()) + ", "
            rec_string = rec_string + "price: " + str(skills[i].getPrice()) + "\"} "

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
        mutation MyRASMutation {
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

def gen_get_agent_skills_string():
    query_string = "query MyGetAgentSkillsQuery { getAgentSkills (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    logger_helper.debug(query_string)
    return query_string


def gen_add_agent_tasks_string(tasks, test_settings={}):
    query_string = """
        mutation MyAMMutation {
      addAgentTasks (input:[
    """
    rec_string = ""
    for i in range(len(tasks)):
        if isinstance(tasks[i], dict):
            rec_string = rec_string + "{ ataskid:" + str(tasks[i]["ataskid"]) + ", "
            rec_string = rec_string + "owner:\"" + tasks[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + str(tasks[i]["name"]) + ", "
            rec_string = rec_string + "description:\"" + tasks[i]["description"] + "\", "
            rec_string = rec_string + "objectives:\"" + tasks[i]["objectives"].replace('"', '\\"') + "\", "
            rec_string = rec_string + "status:\"" + tasks[i]["status"] + "\", "
            rec_string = rec_string + "schedule:" + tasks[i]["schedule"].replace('"', '\\"') + ", "
            rec_string = rec_string + "metadata:\"" + tasks[i]["metadata"].replace('"', '\\"') + "\", "
            rec_string = rec_string + "start:\"" + tasks[i]["start"] + "\", "
            rec_string = rec_string + "priority:\"" + tasks[i]["priority"] + "\"} "
        else:
            rec_string = rec_string + "{ ataskid:" + str(tasks[i].getTaskId()) + ", "
            rec_string = rec_string + "owner:" + str(tasks[i].getOwner()) + ", "
            rec_string = rec_string + "name:\"" + tasks[i].getName() + "\", "
            rec_string = rec_string + "description:" + str(tasks[i].getDescription()) + ", "
            rec_string = rec_string + "objectives:\"" + tasks[i].getObjectives().replace('"', '\\"') + "\", "
            rec_string = rec_string + "status:\"" + tasks[i].getStatus() + "\", "
            rec_string = rec_string + "schedule:\"" + tasks[i].getSchedule().replace('"', '\\"') + "\", "
            rec_string = rec_string + "metadata:\"" + tasks[i].getMetadata().replace('"', '\\"') + "\", "
            rec_string = rec_string + "start:\"" + tasks[i].getStart() + "\", "
            rec_string = rec_string + "priority:\"" + tasks[i].getPriority() + "\"} "

        if i != len(tasks) - 1:
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



def gen_update_agent_tasks_string(tasks):
    query_string = """
        mutation MyUMMutation {
      updateAgentTasks (input:[
    """
    rec_string = ""
    for i in range(len(tasks)):
        if isinstance(tasks[i], dict):
            rec_string = rec_string + "{ ataskid:" + str(tasks[i]["ataskid"]) + ", "
            rec_string = rec_string + "owner:\"" + tasks[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + str(tasks[i]["name"]) + ", "
            rec_string = rec_string + "description:\"" + tasks[i]["description"] + "\", "
            rec_string = rec_string + "objectives:\"" + tasks[i]["objectives"].replace('"', '\\"') + "\", "
            rec_string = rec_string + "status:\"" + tasks[i]["status"] + "\", "
            rec_string = rec_string + "schedule:" + tasks[i]["schedule"].replace('"', '\\"') + ", "
            rec_string = rec_string + "metadata:\"" + tasks[i]["metadata"].replace('"', '\\"') + "\", "
            rec_string = rec_string + "start:\"" + tasks[i]["start"] + "\", "
            rec_string = rec_string + "priority:\"" + tasks[i]["priority"] + "\"} "
        else:
            rec_string = rec_string + "{ ataskid:" + str(tasks[i].getTaskId()) + ", "
            rec_string = rec_string + "owner:" + str(tasks[i].getOwner()) + ", "
            rec_string = rec_string + "name:\"" + tasks[i].getName() + "\", "
            rec_string = rec_string + "description:" + str(tasks[i].getDescription()) + ", "
            rec_string = rec_string + "objectives:\"" + tasks[i].getObjectives().replace('"', '\\"') + "\", "
            rec_string = rec_string + "status:\"" + tasks[i].getStatus() + "\", "
            rec_string = rec_string + "schedule:\"" + tasks[i].getSchedule().replace('"', '\\"') + "\", "
            rec_string = rec_string + "metadata:\"" + tasks[i].getMetadata().replace('"', '\\"') + "\", "
            rec_string = rec_string + "start:\"" + tasks[i].getStart() + "\", "
            rec_string = rec_string + "priority:\"" + tasks[i].getPriority() + "\"} "

        if i != len(tasks) - 1:
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


def gen_get_agent_tasks_string():
    query_string = "query MyGetAgentTasksQuery { getAgentTasks (ids:'"
    rec_string = "0"

    tail_string = "') }"
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
            rec_string = rec_string + "{ toolid:" + str(tools[i]["toolId"]) + ", "
            rec_string = rec_string + "owner:\"" + tools[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + tools[i]["name"] + ", "
            rec_string = rec_string + "description:\"" + tools[i]["description"] + "\", "
            rec_string = rec_string + "link:\"" + tools[i]["link"] + "\", "
            rec_string = rec_string + "protocol:\"" + tools[i]["protocol"] + "\", "
            rec_string = rec_string + "status:\"" + tools[i]["status"] + "\", "
            rec_string = rec_string + "metadata:\"" + tools[i]["metadata"].replace('"', '\\"') + "\", "
            rec_string = rec_string + "price:\"" + str(tools[i]["price"]) + "\"} "
        else:
            rec_string = rec_string + "{ toolid:" + str(tools[i].getToolId()) + ", "
            rec_string = rec_string + "owner:" + tools[i].getOwner() + ", "
            rec_string = rec_string + "name:\"" + tools[i].getName() + "\", "
            rec_string = rec_string + "description:" + tools[i].getDescription() + ", "
            rec_string = rec_string + "link:\"" + tools[i].getLink() + "\", "
            rec_string = rec_string + "protocol:\"" + tools[i].getProtocol() + "\", "
            rec_string = rec_string + "status:\"" + tools[i].getStatus() + "\", "
            rec_string = rec_string + "metadata:" + tools[i].getMetadata().replace('"', '\\"') + ", "
            rec_string = rec_string + "price:\"" + str(tools[i].getConfig()) + "\"} "

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
            rec_string = rec_string + "{ toolid:" + str(tools[i]["toolId"]) + ", "
            rec_string = rec_string + "owner:\"" + tools[i]["owner"] + "\", "
            rec_string = rec_string + "name:" + tools[i]["name"] + ", "
            rec_string = rec_string + "description:\"" + tools[i]["description"] + "\", "
            rec_string = rec_string + "link:\"" + tools[i]["link"] + "\", "
            rec_string = rec_string + "protocol:\"" + tools[i]["protocol"] + "\", "
            rec_string = rec_string + "status:\"" + tools[i]["status"] + "\", "
            rec_string = rec_string + "metadata:\"" + tools[i]["metadata"].replace('"', '\\"') + "\", "
            rec_string = rec_string + "price:\"" + str(tools[i]["price"]) + "\"} "
        else:
            rec_string = rec_string + "{ toolid:" + str(tools[i].getToolId()) + ", "
            rec_string = rec_string + "owner:" + tools[i].getOwner() + ", "
            rec_string = rec_string + "name:\"" + tools[i].getName() + "\", "
            rec_string = rec_string + "description:" + tools[i].getDescription() + ", "
            rec_string = rec_string + "link:\"" + tools[i].getLink() + "\", "
            rec_string = rec_string + "protocol:\"" + tools[i].getProtocol() + "\", "
            rec_string = rec_string + "status:\"" + tools[i].getStatus() + "\", "
            rec_string = rec_string + "metadata:" + tools[i].getMetadata().replace('"', '\\"') + ", "
            rec_string = rec_string + "price:\"" + str(tools[i].getConfig()) + "\"} "

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
      queryAgentTools (qt:[
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
    logger_helper.debug(query_string)
    return query_string



def gen_get_agent_tools_string():
    query_string = "query MyGetAgentToolsQuery { getAgentTools (ids:'"
    rec_string = "0"

    tail_string = "') }"
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
    logger_helper.debug(query_string)
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
    logger_helper.debug(query_string)
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
    logger_helper.debug(query_string)
    return query_string




def gen_get_knowledges_string():
    query_string = "query MyGetKnowledgesQuery { getKnowledges (ids:'"
    rec_string = "0"

    tail_string = "') }"
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
    logger_helper.debug("DAILY REPORT QUERY STRING:"+query_string)
    return query_string




def send_update_agent_tasks_ex_status_to_cloud(session, tasksStats, token, endpoint):
    if len(tasksStats) > 0:
        query = gen_update_agent_tasks_ex_status_string(tasksStats)

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


# =================================================================================================
# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agents_request_to_cloud(session, agents, token, endpoint):

    mutationInfo = gen_add_agents_string(agents)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addAgents"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_agents_request_to_cloud(session, bots, token, endpoint):

    mutationInfo = gen_update_agents_string(bots)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateAgents"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_agents_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_agents_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgents"])
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
def send_get_agent_skills_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_agent_skills_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getAgentSkills"])

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agent_tasks_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_add_agent_tasks_string(tasks)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addAgentTasks"])
    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_agent_tasks_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_update_agent_tasks_string(tasks)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateAgentTasks"])
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



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tasks_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_agent_tasks_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getAgentTasks"])

    return jresponse



def send_add_agent_tools_request_to_cloud(session, tools, token, endpoint):

    mutationInfo = gen_add_agent_tools_string(tools)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addAgentTools"])
    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_update_agent_tools_request_to_cloud(session, tools, token, endpoint):

    mutationInfo = gen_update_agent_tools_string(tools)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["updateAgentTools"])
    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_agent_tools_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_agent_tools_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgentTools"])

    return jresponse



def send_query_agent_tools_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agent_tools_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryAgentTools"])


    return jresponse


def send_query_agent_tools_by_time_request_to_cloud(session, token, q_settings, endpoint):
    try:
        queryInfo = gen_query_agent_tools_by_time_string(q_settings)

        jresp = appsync_http_request(queryInfo, session, token, endpoint)

        if "errors" in jresp:
            screen_error = True
            logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
            jresponse = jresp["errors"][0]
        else:
            jresponse = json.loads(jresp["data"]["queryAgentTools"])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorQueryAgentToolsByTime:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorQueryAgentToolsByTime traceback information not available:" + str(e)
        print(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tools_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_agent_tools_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getAgentTools"])

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_knowledges_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_add_knowledges_string(tasks)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addKnowledges"])

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



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_remove_knowledges_request_to_cloud(session, removes, token, endpoint):

    mutationInfo = gen_remove_knowledges_string(removes)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeKnowledges"])

    return jresponse


def send_query_knowledges_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_knowledges_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryKnowledges"])


    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_knowledges_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_knowledges_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger_helper.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["getKnowledges"])

    return jresponse









