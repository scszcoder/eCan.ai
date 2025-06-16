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

from agent.runner.service import Runner
from agent.tasks import Repeat_Types
import traceback
import socket
import uuid

def set_up_ec_rpa_supervisor_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        schedule_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor task scheduling"), None)
        serve_request_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor serve requests"), None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor chatter"),None)

        agent_card = AgentCard(
            name="ECBot RPA Supervisor Agent",
            description="Obtain Daily Run Task Schedule and Dispatches Tasks To Operators To Run",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[schedule_skill, serve_request_skill],
        )
        print("agent card created:", agent_card.name, agent_card.url)

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 03:00:00:000",
            end_date_time="2035-12-31 23:59:59:000",
            time_out=120                # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        daily_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Supervise Daily Routine Task",
            description="Do any routine like fetch todays work schedule, prepare operators team and dispatch work to the operators to do.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=schedule_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )

        non_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 23:59:59:000",
            end_date_time="2035-12-31 23:59:59:000",
            time_out=120  # seconds.
        )
        on_request_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Supervisor Service Task",
            description="Serve RPA operators in case they request human in loop or work reports",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=serve_request_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=non_schedule
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        chatter_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Supervisor Chatter Task",
            description="chat with human user about anything related to ECBot RPA supervising work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        supervisor = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[schedule_skill, serve_request_skill, chatter_skill], tasks=[daily_task, on_request_task, chatter_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECBOTSupervisorAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECBOTSupervisorAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return supervisor