import ast
import json

from common.models import VehicleModel
from utils.server import HttpServer
from utils.time_util import TimeUtil
from gui.LocalServer import start_local_server_in_thread, create_mcp_client, create_sse_client
from agent.cloud_api.cloud_api import *
from agent.ec_agent import *
import asyncio
import traceback



from lzstring import LZString
import openpyxl
import tzlocal
from datetime import timedelta
import platform
from pynput.mouse import Controller
from PySide6.QtWebEngineWidgets import QWebEngineView

from utils.logger_helper import logger_helper
from tests.unittests import *
from tests.agent_tests import *

from agent.ec_agents.build_agents import *
import concurrent.futures


def add_new_agents_to_cloud(mainwin, agents):
    try:
        cloud_agents = prep_agent_data_for_cloud(mainwin, agents)
        jresp = send_add_agents_request_to_cloud(mainwin.session, cloud_agents, mainwin.tokens['AuthenticationResult']['IdToken'], mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentsToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentsToCloud: traceback information not available:" + str(e)
        log3(ex_stat)


def save_agents_to_cloud(mainwin, agents):
    try:
        cloud_agents = prep_agent_data_for_cloud(mainwin, agents)
        jresp = send_update_agents_request_to_cloud(mainwin.session, cloud_agents,
                                                 mainwin.tokens['AuthenticationResult']['IdToken'],
                                                 mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentsToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentsToCloud: traceback information not available:" + str(e)
        log3(ex_stat)



def load_agents_from_cloud(mainwin):
    try:
        cloud_agents = []
        jresp = send_get_agents_request_to_cloud(mainwin.session, mainwin.tokens['AuthenticationResult']['IdToken'], mainwin.getWanApiEndpoint())
        all_agents = jresp['body']
        for ajs in all_agents:
            new_agent = gen_new_agent(mainwin, ajs)
            if new_agent:
                cloud_agents.append(new_agent)

        mainwin.agents = cloud_agents

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentsFromCloud: traceback information not available:" + str(e)
        log3(ex_stat)


def gen_agent_from_cloud_data(mainwin, ajs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if ajs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in ajs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if ajs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in ajs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = ajs['id'],
            name=ajs['name'],
            description=ajs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        print("agent card created:", agent_card.name, agent_card.url)

        new_agent = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        log3(ex_stat)
        return None


def gen_new_agent(mainwin, ajs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if ajs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in ajs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if ajs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in ajs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = ajs['id'],
            name=ajs['name'],
            description=ajs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        print("agent card created:", agent_card.name, agent_card.url)

        new_agent = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        log3(ex_stat)
        return None


def prep_agent_data_for_cloud(mainwin, agents):
    try:
        ajs = []
        for agent in agents:
            aj = {
                "agid": agent.card.id,
                "owner": mainwin.user,
                "gender": agent.gender,
                "organizations": agent.organizations,
                "rank": agent.rank,
                "supervisors": agent.supervisors,
                "subordinates": agent.subordinates,
                "title": agent.title,
                "personalities": agent.personalities,
                "birthday": agent.birthday,
                "name": agent.card.name,
                "status": agent.status,
                "metadata": json.dumps({"description": agent.card.description}),
                "vehicle": agent.vehicle,
                "skills": json.dumps([sk.id for sk in agent.skill_set]),
                "tasks": json.dumps([task.id for task in agent.tasks]),
                "knowledges": ""
            }
            ajs.append(aj)

        return ajs
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        log3(ex_stat)
        return None


def remove_agents_from_cloud(mainwin, agents):
    try:
        api_removes=[{"id": item.card.id, "owner": "", "reason": ""} for item in agents]
        jresp = send_remove_agents_request_to_cloud(mainwin.session, api_removes, mainwin.tokens['AuthenticationResult']['IdToken'], mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveAgent: traceback information not available:" + str(e)
        log3(ex_stat)
        return None

