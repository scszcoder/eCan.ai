from agent.a2a.common.client import A2AClient
from agent.ec_agent import EC_Agent
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.common.types import TaskStatus, TaskState
from agent.tasks import TaskRunner, ManagedTask, TaskSchedule
from agent.tasks import Repeat_Types
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_helper_chat_task, create_ec_helper_work_task
from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI

import traceback
import socket
import uuid

def set_up_ec_helper_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"),None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa helper"),None)
        print("worker_skill", worker_skill.name)
        print("chatter_skill", chatter_skill.name)
        agent_card = AgentCard(
                name="ECBot Helper Agent",
                description="Helps with ECBot RPA works",
                url=get_a2a_server_url(mainwin) or "http://localhost:3600",
                version="1.0.0",
                defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                capabilities=capabilities,
                skills=[worker_skill, chatter_skill],
        )

        print("agent card created:", agent_card.name, agent_card.url)
        chatter_task = create_ec_helper_chat_task(mainwin)
        worker_task = create_ec_helper_work_task(mainwin)
        browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        helper = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECBOTHelperAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECBOTHelperAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return helper
