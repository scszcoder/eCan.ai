import json
import os
import base64

from bot.envi import getECBotDataHome
from utils.logger_helper import logger_helper as logger
import traceback
from config.constants import API_DEV_MODE
from aiolimiter import AsyncLimiter
from bot.Cloud import appsync_http_request, gen_daily_update_string
import websocket
import threading
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl
from typing import Optional, Tuple
from utils.logger_helper import logger_helper
from agent.a2a.common.types import TaskSendParams, Message, TextPart


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
    logger.debug("query string:"+query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
    return query_string


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
    query_string = "query MyGetAgentQuery { getAgents (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
    return query_string



def gen_query_agent_skills_string(q_setting):
    if q_setting["byowneruser"]:
        query_string = "query MySkQuery { queryAgentSkills(qs: \"{ \\\"byowneruser\\\": true}\") } "
    else:
        query_string = "query MySkQuery { queryAgentSkills(qs: \"{ \\\"byowneruser\\\": false, \\\"qphrase\\\": \\\""+q_setting["qphrase"]+"\\\"}\") } "

    rec_string = ""
    tail_string = ""
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
    return query_string

def gen_get_agent_skills_string():
    query_string = "query MyGetAgentSkillsQuery { getAgentSkills (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    query_string = "query MyGetAgentTasksQuery { getAgentTasks (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
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
    logger.debug(query_string)
    return query_string



def gen_get_agent_tools_string():
    query_string = "query MyGetAgentToolsQuery { getAgentTools (ids:'"
    rec_string = "0"

    tail_string = "') }"
    query_string = query_string + rec_string + tail_string
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
    query_string = "query MyGetKnowledgesQuery { getKnowledges (ids:'"
    rec_string = "0"

    tail_string = "') }"
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
            logger.error("ERROR Type: " + json.dumps(jresponse["errorType"]) + " ERROR Info: " + json.dumps(jresponse["message"]))
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
            logger.error("ERROR Type: " + json.dumps(jresponse["errorType"]) + " ERROR Info: " + json.dumps(jresponse["message"]))
        else:
            jresponse = json.loads(jresp["data"]["reportTaskStatus"])
    else:
        logger.error("ERROR Type: EMPTY DAILY REPORTS")
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))

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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgents"])
    return jresponse




def send_query_agents_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agents_string(q_settings)
    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("AppSync getAgents error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agents data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            agents_data = jresp["data"]["getAgents"]
            if agents_data is None:
                logger.info("getAgents returned null - user has no agents data")
                jresponse = {}
            else:
                jresponse = json.loads(agents_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse getAgents response: {e}")
            jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agent_skills_request_to_cloud(session, skills, token, endpoint):

    mutationInfo = gen_add_agent_skills_string(skills)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgentSkills"])

    return jresponse


def send_query_agent_skills_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agent_skills_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("AppSync getAgentSkills error: " + json.dumps(jresp))
        # Handle case where user has no agent skills data (return empty dict)
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agent skills data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            skills_data = jresp["data"]["getAgentSkills"]
            if skills_data is None:
                logger.info("getAgentSkills returned null - user has no agent skills data")
                jresponse = {}
            else:
                jresponse = json.loads(skills_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse getAgentSkills response: {e}")
            jresponse = {}

    return jresponse


# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_agent_tasks_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_add_agent_tasks_string(tasks)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgentTasks"])

    return jresponse



def send_query_agent_tasks_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agent_tasks_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
            logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tasks_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_agent_tasks_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("AppSync getAgentTasks error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agent tasks data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            tasks_data = jresp["data"]["getAgentTasks"]
            if tasks_data is None:
                logger.info("getAgentTasks returned null - user has no agent tasks data")
                jresponse = {}
            else:
                jresponse = json.loads(tasks_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse getAgentTasks response: {e}")
            jresponse = {}

    return jresponse



def send_add_agent_tools_request_to_cloud(session, tools, token, endpoint):

    mutationInfo = gen_add_agent_tools_string(tools)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeAgentTools"])

    return jresponse



def send_query_agent_tools_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_agent_tools_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
            logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error(ex_stat)
        jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_get_agent_tools_request_to_cloud(session, token, endpoint):

    queryInfo = gen_get_agent_tools_string()

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("AppSync getAgentTools error: " + json.dumps(jresp))
        if any("Cannot return null for non-nullable type" in str(error.get("message", "")) for error in jresp.get("errors", [])):
            logger.info("No agent tools data found for user - returning empty dict")
            jresponse = {}
        else:
            jresponse = jresp["errors"][0] if jresp["errors"] else {}
    else:
        try:
            tools_data = jresp["data"]["getAgentTools"]
            if tools_data is None:
                logger.info("getAgentTools returned null - user has no agent tools data")
                jresponse = {}
            else:
                jresponse = json.loads(tools_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse getAgentTools response: {e}")
            jresponse = {}

    return jresponse



# interface appsync, directly use HTTP request.
# Use AWS4Auth to sign a requests session
def send_add_knowledges_request_to_cloud(session, tasks, token, endpoint):

    mutationInfo = gen_add_knowledges_string(tasks)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR message: "+json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["addKnowledges"])

    return jresponse


def send_update_knowledges_request_to_cloud(session, vehicles, token, endpoint):

    mutationInfo = gen_update_knowledges_string(vehicles)

    jresp = appsync_http_request(mutationInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: "+json.dumps(jresp["errors"][0]["errorType"])+" ERROR Info: "+json.dumps(jresp["errors"][0]["message"]) )
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["removeKnowledges"])

    return jresponse


def send_query_knowledges_request_to_cloud(session, token, q_settings, endpoint):

    queryInfo = gen_query_knowledges_string(q_settings)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)

    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryComponents"])

    return jresponse



def send_query_fom_request_to_cloud(session, token, fom_info, endpoint):

    queryInfo = gen_query_fom_string(fom_info)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_query_fom_request_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
    else:
        jresponse = json.loads(jresp["data"]["queryFOM"])

    return jresponse



def send_rank_results_request_to_cloud(session, token, rank_data_inut, endpoint):

    queryInfo = gen_rank_results_string(rank_data_inut)

    jresp = appsync_http_request(queryInfo, session, token, endpoint)
    logger.debug("send_query_rank_results_request_to_cloud, response:", jresp)
    if "errors" in jresp:
        screen_error = True
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
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
        logger.error("ERROR Type: " + json.dumps(jresp["errors"][0]["errorType"]) + " ERROR Info: " + json.dumps(jresp["errors"][0]["message"]))
        jresponse = jresp["errors"][0]
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
        print("hello hello......")
        try:
            data = json.loads(message)
        except Exception:
            data = {"raw": message}
        print("Subscription update:", json.dumps(data, indent=2))
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
                print("connection_ack received, sending start subscription ...")
                ws.send(json.dumps(start_payload))
            except Exception as e:
                print("Failed to send start payload:", e)

        elif msg_type in ("ka", "keepalive"):
            # Keep-alive from server; no action required
            return
        elif msg_type == "data" and isinstance(data.get("payload"), dict) and data.get("id") == "LongLLM1":
            # Extract structured object result per schema
            payload_data = data.get("payload", {}).get("data", {})
            result_obj = None
            if isinstance(payload_data, dict):
                result_obj = payload_data.get("onLongLLMTaskComplete")
                logger.debug(f"Received subscription result:{json.dumps(result_obj, indent=2, ensure_ascii=False)}")
                # now we can send result_obj to resume the pending workflow.
                # which msg queue should this be put into? (agent should maintain some kind of cloud_task_id to agent_task_queue LUT)
                agent_id = result_obj["agentID"]
                work_type = result_obj["workType"]
                handler_agent = get_agent_by_id(agent_id)
                # Convert cloud result to TaskSendParams format for _build_resume_payload()
                converted_result = convert_cloud_result_to_task_send_params(result_obj, work_type)
                event_response = handler_agent.runner.sync_task_wait_in_line(work_type, converted_result)

    def on_error(ws, error):
        print("WebSocket error:", error)

    def on_close(ws, status_code, msg):
        print(f"WebSocket closed: code={status_code}, msg={msg}")

    def on_open(ws):
        logger_helper.debug("web socket opened.......")
        init_payload = {
            "type": "connection_init",
            "payload": {}
        }
        try:
            logger_helper.debug("sending connection_init ...")
            ws.send(json.dumps(init_payload))
        except Exception as e:
            print("Failed to send connection_init:", e)

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

    print("ws_url ok.....")
    headers = []

    print("token seems to be ok.....")

    ws = websocket.WebSocketApp(
        signed_url,
        header=headers,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
        subprotocols=["graphql-ws"],
    )

    print("launch web socket thread")
    # Configure SSL options to handle certificate verification issues
    import ssl
    ssl_context = ssl.create_default_context()
    # For development/testing, you might want to disable certificate verification
    # ssl_context.check_hostname = False
    # ssl_context.verify_mode = ssl.CERT_NONE

    t = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
    t.start()
    print("web socket thread launched")
    return ws, t
