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

def get_lan_ip():
    try:
        # Connect to an external address, but don't actually send anything
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's DNS IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"  # fallback

def get_a2a_server_url(mainwin):
    try:
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)

        if not free_ports:
            return None
        a2a_server_port = free_ports[0]
        url=f"http://{host}:{a2a_server_port}"
        print("a2a server url:", url)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGetA2AServerURL:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGetA2AServerURL: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return ""
    return url

def set_up_ec_helper_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
                name="ECBot Helper Agent",
                description="Helps with ECBot RPA works",
                url=get_a2a_server_url(mainwin) or "http://localhost:3600",
                version="1.0.0",
                defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                capabilities=capabilities,
                skills=[agent_skill],
        )

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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        helper = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

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


def set_up_ec_customer_support_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
            name="ECBot Helper Agent",
            description="Helps with ECBot RPA works",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[agent_skill],
        )

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        customer_support = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECBOTSuppportAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECBOTSuppportAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return customer_support


def set_up_ec_rpa_operator_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
            name="ECBot RPA Operator Agent",
            description="Run and operates ECBot RPA bots to do their scheduled work",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[agent_skill],
        )

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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        operator = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

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


def set_up_ec_rpa_supervisor_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
            name="ECBot RPA Supervisor Agent",
            description="Obtain Daily Run Task Schedule and Dispatches Tasks To Operators To Run",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[agent_skill],
        )


        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        supervisor = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

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



def set_up_ec_marketing_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
            name="ECBot Helper Agent",
            description="Helps with ECBot RPA works",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[agent_skill],
        )

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        marketer = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

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

    return marketer

def set_up_ec_sales_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
            name="ECBot Helper Agent",
            description="Helps with ECBot RPA works",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[agent_skill],
        )

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        sales = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

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

    return sales


def set_up_ec_research_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        agent_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        agent_card = AgentCard(
            name="ECBot Helper Agent",
            description="Helps with ECBot RPA works",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[agent_skill],
        )

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
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
        task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=agent_skill,
            task=agent_skill.runnable,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        marketing_researcher = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[agent_skill], tasks=[task])

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
    return marketing_researcher