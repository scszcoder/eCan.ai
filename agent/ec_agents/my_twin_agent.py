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
from agent.runner.service import Runner
from agent.tasks import Repeat_Types
import traceback
import socket
import uuid



def set_up_my_twin_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for my digital twin"), None)
        print("chatter skill:", chatter_skill)
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
        print("agent card created:", agent_card.name, agent_card.url)
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 23:59:59:000",
            end_date_time="2035-12-31 23:59:59:000",
            time_out=120  # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        chat_task = ManagedTask(
            id=task_id,
            name="Human Chat Task",
            description="Represent human to chat with others",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="interaction",
            schedule=task_schedule
        )
        helper = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[chatter_skill], tasks=[chat_task])

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
