from agent.a2a.common.client import A2AClient
from agent.ec_agent import EC_Agent
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.a2a.common.types import TaskStatus, TaskState
from agent.tasks import TaskRunner, ManagedTask, TaskSchedule
from agent.tasks import Repeat_Types
from agent.ec_agents.create_agent_tasks import create_my_twin_chat_task
import traceback
import socket
import uuid
from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
from utils.logger_helper import logger_helper as logger

def set_up_my_twin_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for my digital twin"), None)
        logger.info("chatter skill:", chatter_skill)
        agent_card = AgentCard(
                name="My Twin Agent",
                description="Human Representative",
                url=get_a2a_server_url(mainwin) or "http://localhost:3600",
                version="1.0.0",
                defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                capabilities=capabilities,
                skills=[chatter_skill],
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)
        chat_task = create_my_twin_chat_task(mainwin)

        # 在打包环境中安全初始化browser_use_llm
        try:
            browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        except Exception as e:
            logger.warning(f"Failed to initialize BrowserUseChatOpenAI in packaged environment: {e}")

        helper = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skill_set=[chatter_skill], tasks=[chat_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpMyTwinAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpMyTwinAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return helper
