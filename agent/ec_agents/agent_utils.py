import json

from utils.time_util import TimeUtil
from agent.cloud_api.cloud_api import *
from agent.ec_agent import *
import traceback
from utils.logger_helper import logger_helper as logger
from agent.a2a.langgraph_agent.utils import get_a2a_server_url

from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI





import concurrent.futures
SUPPORTED_CONTENT_TYPES = ["text", "text/plain", "json", "file"]

def add_new_agents_to_cloud(mainwin, agents):
    try:
        cloud_agents = prep_agent_data_for_cloud(mainwin, agents)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_add_agents_request_to_cloud(mainwin.session, cloud_agents, auth_token, mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentsToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentsToCloud: traceback information not available:" + str(e)
        logger.error(ex_stat)
        # log3(ex_stat)


def save_agents_to_cloud(mainwin, agents):
    try:
        cloud_agents = prep_agent_data_for_cloud(mainwin, agents)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_update_agents_request_to_cloud(mainwin.session, cloud_agents,
                                                 auth_token,
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
        logger.error(ex_stat)
        # log3(ex_stat)



def load_agents_from_cloud(mainwin):
    cloud_agents = []
    try:
        logger.info("load_agents_from_cloud.......")
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agents
        jresp = send_get_agents_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        logger.info("cloud returns.......", jresp)
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agents = json.loads(jresp['body'])
        else:
            logger.warning("No agents data returned from cloud")
            all_agents = []
        for ajs in all_agents:
            new_agent = gen_new_agent(mainwin, ajs)
            if new_agent:
                cloud_agents.append(new_agent)

        mainwin.agents = cloud_agents
        return cloud_agents

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentsFromCloud: traceback information not available:" + str(e)
        logger.error(ex_stat)
        # log3(ex_stat)
    
    return cloud_agents


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
            defaultInputModes=SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        # 在打包环境中安全初始化browser_use_llm
        try:
            browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        except Exception as e:
            logger.warning(f"Warning: Failed to initialize BrowserUseChatOpenAI in packaged environment: {e}")

        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent(mainwin, ajs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        logger.debug("ajs:", ajs)
        if ajs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in ajs['skills'].split(",")]
        else:
            skids = []

        logger.debug("skids:", skids, len(all_skills), all_skills[0])
        agent_skills = [sk for sk in all_skills if int(sk.id) in skids]

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
        logger.info("agent card created:", agent_card.name, agent_card.url)

        # 在打包环境中安全初始化browser_use_llm
        try:
            browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        except Exception as e:
            logger.warning(f"Warning: Failed to initialize BrowserUseChatOpenAI in packaged environment: {e}")
            # 使用主LLM作为备用方案
            browser_use_llm = llm

        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
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
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def remove_agents_from_cloud(mainwin, agents):
    try:
        api_removes=[{"id": item.card.id, "owner": "", "reason": ""} for item in agents]
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return
        jresp = send_remove_agents_request_to_cloud(mainwin.session, api_removes, auth_token, mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None

# ###########################################################################################
# agent skill related
# ###########################################################################################

def add_new_agent_skills_to_cloud(mainwin, skills):
    try:
        cloud_agent_skills = prep_agent_skills_data_for_cloud(mainwin, skills)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_add_agent_skills_request_to_cloud(mainwin.session, cloud_agent_skills, auth_token, mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentSkillsToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentSkillsToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)


def save_agent_skills_to_cloud(mainwin, skills):
    try:
        cloud_agent_skills = prep_agent_skills_data_for_cloud(mainwin, skills)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_update_agents_request_to_cloud(mainwin.session, cloud_agent_skills,
                                                 auth_token,
                                                 mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentSkillsToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentSkillsToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)


def load_agent_skills_from_cloud(mainwin):
    cloud_agent_skills = []
    try:
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agent_skills
        jresp = send_get_agent_skills_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        logger.info("cloud get agent skills returns.......", jresp)
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agent_skills = json.loads(jresp['body'])
        else:
            logger.warning("No agent skills data returned from cloud")
            all_agent_skills = []
        logger.info("true cloud agent skills ...", all_agent_skills)
        for askjs in all_agent_skills:
            new_agent_skill = gen_new_agent_skill(mainwin, askjs)
            if new_agent_skill:
                cloud_agent_skills.append(new_agent_skill)

        mainwin.agent_skills = cloud_agent_skills
        return cloud_agent_skills

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentsFromCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []

    return cloud_agent_skills


def gen_agent_skill_from_cloud_data(mainwin, askjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if askjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in askjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if askjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in askjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = askjs['id'],
            name=askjs['name'],
            description=askjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        # 在打包环境中安全初始化browser_use_llm
        try:
            browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        except Exception as e:
            logger.warning(f"Warning: Failed to initialize BrowserUseChatOpenAI in packaged environment: {e}")
            # 使用主LLM作为备用方案
            browser_use_llm = llm

        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgent: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent_skill(mainwin, askjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if askjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in askjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if askjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in askjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = askjs['id'],
            name=askjs['name'],
            description=askjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        new_agent_skill = EC_Skill(mainwin=mainwin, llm=llm, card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent_skill
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentSkill: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def prep_agent_skills_data_for_cloud(mainwin, agent_skills):
    try:
        askjs = []
        for ask in agent_skills:
            askj = {
                "askid": ask.id,
                "owner": mainwin.user,
                "name": ask.name,
                "description": ask.description,
                "status": ask.status,
                "path": ask.path,
                "flowgram": json.dumps(ask.diagram),
                "langgraph": json.dumps(ask.work_flow),
                "config": json.dumps(ask.config),
                "price": str(ask.price)
            }
            askjs.append(askj)

        return askjs
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentSkill:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentSkill: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def remove_agent_skills_from_cloud(mainwin, agent_skills):
    try:
        api_removes=[{"id": item.id, "owner": "", "reason": ""} for item in agent_skills]
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return
        jresp = send_remove_agent_skills_request_to_cloud(mainwin.session, api_removes, auth_token, mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveAgentSkills:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveAgentSkills: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None

# ###########################################################################################
# agent task related
# ###########################################################################################

def add_new_agent_tools_to_cloud(mainwin, tools):
    try:
        cloud_agent_tools = prep_agent_tools_data_for_cloud(mainwin, tools)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_add_agent_tools_request_to_cloud(mainwin.session, cloud_agent_tools, auth_token, mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentTasksToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentTasksToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def save_agent_tools_to_cloud(mainwin, tools):
    try:
        cloud_agent_tools = prep_agent_tools_data_for_cloud(mainwin, tools)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_update_agent_tools_request_to_cloud(mainwin.session, cloud_agent_tools,
                                                 auth_token,
                                                 mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentTasksToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentTasksToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []



def load_agent_tools_from_cloud(mainwin):
    try:
        cloud_agent_tools = []
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agent_tools
        jresp = send_get_agent_tools_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agent_tools = json.loads(jresp['body'])
        else:
            logger.warning("No agent tools data returned from cloud")
            all_agent_tools = []
        for atooljs in all_agent_tools:
            new_agent_tool = gen_new_agent_tools(mainwin, atooljs)
            if new_agent_tool:
                cloud_agent_tools.append(new_agent_tool)

        mainwin.agent_tools = cloud_agent_tools
        return cloud_agent_tools

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentToolsFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentToolsFromCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def gen_agent_tools_from_cloud_data(mainwin, taskjs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if taskjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in taskjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if taskjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in taskjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = taskjs['id'],
            name=taskjs['name'],
            description=taskjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent_tools(mainwin, tooljs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if tooljs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in tooljs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if tooljs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in tooljs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = tooljs['id'],
            name=tooljs['name'],
            description=tooljs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        new_agent_task = EC_Skill(mainwin=mainwin, llm=llm, card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent_task
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTools:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTools: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def prep_agent_tools_data_for_cloud(mainwin, agent_tools):
    try:
        tooljs = []
        for tool in agent_tools:
            toolj = {
                "agid": tool.card.id,
                "owner": mainwin.user,
                "gender": tool.gender,
                "organizations": tool.organizations,
                "rank": tool.rank,
                "supervisors": tool.supervisors,
                "subordinates": tool.subordinates,
                "title": tool.title,
                "personalities": tool.personalities,
                "birthday": tool.birthday,
                "name": tool.card.name,
                "status": tool.status,
                "metadata": json.dumps({"description": tool.card.description}),
                "vehicle": tool.vehicle,
                "skills": json.dumps([sk.id for sk in tool.skill_set]),
                "tasks": json.dumps([task.id for task in tool.tasks]),
                "knowledges": ""
            }
            tooljs.append(toolj)

        return tooljs
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTools:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTools: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def remove_agent_tools_from_cloud(mainwin, agent_tools):
    try:
        api_removes=[{"id": item.id, "owner": "", "reason": ""} for item in agent_tools]
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return
        jresp = send_remove_agent_tools_request_to_cloud(mainwin.session, api_removes, auth_token, mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveAgentTools:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveAgentTools: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None

# ###########################################################################################
# agent tools related
# ###########################################################################################

def add_new_agent_tasks_to_cloud(mainwin, tasks):
    try:
        cloud_agent_tasks = prep_agent_tasks_data_for_cloud(mainwin, tasks)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_add_agent_tasks_request_to_cloud(mainwin.session, cloud_agent_tasks, auth_token, mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentTasksToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentTasksToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def save_agent_tasks_to_cloud(mainwin, tasks):
    try:
        cloud_agent_tasks = prep_agent_tasks_data_for_cloud(mainwin, tasks)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_update_agent_tasks_request_to_cloud(mainwin.session, cloud_agent_tasks,
                                                 auth_token,
                                                 mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewAgentTasksToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewAgentTasksToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []



def load_agent_tasks_from_cloud(mainwin):
    cloud_agent_tasks = []
    try:
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_agent_tasks
        jresp = send_get_agent_tasks_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        if isinstance(jresp, dict) and 'body' in jresp:
            all_agent_tasks = json.loads(jresp['body'])
        else:
            logger.warning("No agent tasks data returned from cloud")
            all_agent_tasks = []
        logger.info("true cloud agent tasks ...", all_agent_tasks)
        for askjs in all_agent_tasks:
            new_agent_task = gen_new_agent_tasks(mainwin, askjs)
            if new_agent_task:
                cloud_agent_tasks.append(new_agent_task)

        mainwin.agent_tasks = cloud_agent_tasks
        return cloud_agent_tasks

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadAgentTasksFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadAgentTasksFromCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []

    return cloud_agent_tasks


def gen_agent_tasks_from_cloud_data(mainwin, taskjs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if taskjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in taskjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if taskjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in taskjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = taskjs['id'],
            name=taskjs['name'],
            description=taskjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_agent_tasks(mainwin, taskjs):
    try:
        llm = mainwin.llm
        all_tasks = mainwin.agent_tasks
        if taskjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in taskjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_tasks if sk.getSkid() in skids]

        if taskjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in taskjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = taskjs['id'],
            name=taskjs['name'],
            description=taskjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        new_agent_task = EC_Skill(mainwin=mainwin, llm=llm, card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent_task
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def prep_agent_tasks_data_for_cloud(mainwin, agent_tasks):
    try:
        taskjs = []
        for task in agent_tasks:
            taskj = {
                "toolid": task.id,
                "owner": mainwin.user,
                "name": task.name,
                "description": task.description,
                "link": task.link,
                "protocol": json.dumps(task.protocol),
                "status": task.status,
                "metadata": json.dumps(task.work_flow),
                "price": json.dumps(task.config)
            }
            taskjs.append(taskj)

        return taskjs
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def remove_agent_tasks_from_cloud(mainwin, agent_tasks):
    try:
        api_removes=[{"id": item.id, "owner": "", "reason": ""} for item in agent_tasks]
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return
        jresp = send_remove_agent_tasks_request_to_cloud(mainwin.session, api_removes, auth_token, mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveAgentTasks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveAgentTasks: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None

# ###########################################################################################
# agent knowledge related
# ###########################################################################################

def add_new_knowledges_to_cloud(mainwin, knowledges):
    try:
        cloud_knowledges = prep_agent_data_for_cloud(mainwin, knowledges)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_add_knowledges_request_to_cloud(mainwin.session, cloud_knowledges, auth_token, mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewKnowledgesToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewKnowledgesToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def save_knowledges_to_cloud(mainwin, knowledges):
    try:
        cloud_knowledges = prep_knowledges_data_for_cloud(mainwin, knowledges)
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return {"success": False, "message": "No authentication token"}
        jresp = send_update_knowledges_request_to_cloud(mainwin.session, cloud_knowledges,
                                                 auth_token,
                                                 mainwin.getWanApiEndpoint())
        return jresp
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorAddNewKnowledgesToCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorAddNewKnowledgesToCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []



def load_knowledges_from_cloud(mainwin):
    try:
        cloud_knowledges = []
        auth_token = mainwin.get_auth_token()
        if not auth_token:
            logger.error("No valid authentication token available")
            return cloud_knowledges
        jresp = send_get_knowledges_request_to_cloud(mainwin.session, auth_token, mainwin.getWanApiEndpoint())
        if isinstance(jresp, dict) and 'body' in jresp:
            all_knowledges = json.loads(jresp['body'])
        else:
            logger.warning("No knowledges data returned from cloud")
            all_knowledges = []
        for kjs in all_knowledges:
            new_knowledge = gen_new_knowledge(mainwin, kjs)
            if new_knowledge:
                cloud_knowledges.append(new_knowledge)

        mainwin.knowledges = cloud_knowledges
        return cloud_knowledges

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorLoadKnowledgesFromCloud:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorLoadKnowledgesFromCloud: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return []


def gen_knowledge_from_cloud_data(mainwin, kjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if kjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in kjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if kjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in kjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = kjs['id'],
            name=kjs['name'],
            description=kjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        new_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_agent
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def gen_new_knowledge(mainwin, kjs):
    try:
        llm = mainwin.llm
        all_skills = mainwin.agent_skills
        all_tasks = mainwin.agent_tasks
        if kjs['skills'].strip():
            skids = [int(sskid.strip()) for sskid in kjs['skills'].split(",")]
        else:
            skids = []
        agent_skills = [sk for sk in all_skills if sk.getSkid() in skids]

        if kjs['tasks'].strip():
            taskids = [int(staskid.strip()) for staskid in kjs['tasks'].split(",")]
        else:
            taskids = []
        agent_tasks = [sk for sk in all_tasks if sk.getSkid() in taskids]

        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        agent_card = AgentCard(
            id = kjs['id'],
            name=kjs['name'],
            description=kjs['description'],
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=agent_skills,
        )
        logger.info("knowledge created:", agent_card.name, agent_card.url)
        browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        new_knowledge = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=agent_skills, tasks=agent_tasks)
        return new_knowledge
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def prep_knowledges_data_for_cloud(mainwin, knowledges):
    try:
        knjs = []
        for knowledge in knowledges:
            knj = {
                "knid": knowledge.card.id,
                "owner": mainwin.user,
                "name": knowledge.name,
                "description": knowledge.description,
                "path": knowledge.path,
                "status": knowledge.status,
                "metadata": json.dumps(knowledge.metadata),
                "rag": knowledge.rag
            }
            knjs.append(knj)

        return knjs
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorNewKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorNewKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None


def remove_knowledges_from_cloud(mainwin, knowledges):
    try:
        api_removes=[{"id": item.id, "owner": "", "reason": ""} for item in knowledges]
        jresp = send_remove_knowledges_request_to_cloud(mainwin.session, api_removes, mainwin.get_auth_token(), mainwin.getWanApiEndpoint())

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRemoveKnowledges:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRemoveKnowledges: traceback information not available:" + str(e)
        # log3(ex_stat)
        logger.error(ex_stat)
        return None