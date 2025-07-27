from agent.a2a.common.client import A2AClient
from agent.ec_agent import EC_Agent
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.common.types import TaskStatus, TaskState
from agent.tasks import TaskRunner, ManagedTask, TaskSchedule
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_procurement_chat_task, create_ec_procurement_work_task

from agent.tasks import Repeat_Types
import traceback
import socket
import uuid




def set_up_ec_procurement_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if "search digi-key" in sk.name), None)
        print("ec_procurement skill:", worker_skill.name)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for meca search 1688 web site"),None)

        agent_card = AgentCard(
            name="Engineering Procurement Agent",
            description="Procure parts for product development",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[worker_skill, chatter_skill],
        )
        print("agent card created:", agent_card.name, agent_card.url)

        chatter_task = create_ec_procurement_chat_task(mainwin)
        worker_task = create_ec_procurement_work_task(mainwin)
        model = ChatOpenAI(model='gpt-4.1-mini')
        produrement_agent = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=model, task="", card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECProcurementAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECProcurementAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return produrement_agent