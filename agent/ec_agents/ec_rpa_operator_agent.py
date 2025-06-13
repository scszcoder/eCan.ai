from agent.a2a.common.client import A2AClient
from agent.ec_agent import EC_Agent
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.common.types import TaskStatus, TaskState
from agent.tasks import TaskRunner, ManagedTask, TaskSchedule
from agent.runner.service import Runner
from agent.tasks import Repeat_Types
import traceback
import socket
import uuid

def set_up_ec_rpa_operator_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if "ecbot rpa operator" in sk.name), None)
        print("agent_skill", worker_skill.name)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa operator chatter"),None)

        agent_card = AgentCard(
            name="ECBot RPA Operator Agent",
            description="Run and operates ECBot RPA bots to do their scheduled work",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[worker_skill, chatter_skill],
        )
        print("agent card created:", agent_card.name, agent_card.url)

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 23:59:59:000",
            end_date_time="2035-12-31 23:59:59:000",
            time_out=120                # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot RPA operates daily routine task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        chatter_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Operator Chatter Task",
            description="chat with human user about anything related to ECBOT RPA work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )

        operator = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECBOTOperatorAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECBOTOperatorAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return operator