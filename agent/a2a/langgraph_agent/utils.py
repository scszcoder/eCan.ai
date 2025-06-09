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
        print("getting a2a  serer ports:", host, free_ports)
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


def set_up_my_twin_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "human chatter"), None)

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
        task = ManagedTask(
            id=task_id,
            name="Human Chat Task",
            description="Represent human to chat with others",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        helper = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[chatter_skill], tasks=[task])

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


def set_up_ec_helper_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"),None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper chatter"),None)

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
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
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
        helper_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Chatter Task",
            description="chat with human about anything related to helper work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )

        helper = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

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
        worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa customer support"), None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa customer support internal chatter"),None)

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
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot RPA After Sales Support Work like shipping prep, customer Q&A, handle return, refund, resend, etc.",
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
            name="ECBot RPA Customer Support Internal Chatter Task",
            description="chat with human user about anything related to customer support work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        customer_support = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

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



def set_up_ec_marketing_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa marketing"), None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa marketing chatter"),None)

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
        worker_task = ManagedTask(
            id=task_id,
            name="MECA Marketing Director",
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
            name="MECA Marketing Chatter Task",
            description="chat with human user about anything related to e-commerce marketing work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        marketer = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

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
        worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales"), None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales internal chatter"),None)

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
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot Sales",
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
            name="MECA Sales Chatter Task",
            description="chat with human user about anything related to e-commerce sales work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )

        sales = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

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
        worker_skill = next((sk for sk in agent_skills if sk.name == "search 1688 web site"), None)
        print("found agent skill:", worker_skill)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales internal chatter"),None)

        agent_card = AgentCard(
            name="MECA Product Researcher Agent",
            description="MECA Product Research",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[worker_skill, chatter_skill],
        )
        print("agent card created:", agent_card.name, agent_card.url)

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
        worker_task = ManagedTask(
            id=task_id,
            name="MECA search product on 1688 task",
            description="find a part or product on 1688",
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
            name="MECA Sales Chatter Task",
            description="chat with human user about anything related to e-commerce sales work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        marketing_researcher = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECResearcherAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECResearcherAgent: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return None
    return marketing_researcher



def set_up_ec_procurement_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if "search 1688" in sk.name), None)
        print("ec_procurement skill:", worker_skill.name)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "meca procurement chatter"),None)

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

        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 01:00:00:000",
            end_date_time="2035-12-31 01:30:00:000",
            time_out=1800                # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot Part Procurement Task",
            description="Help sourcing products/parts for product development",
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
            name="MECA Procurement Chatter Task",
            description="chat with human user about anything related to e-commerce procurement work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        produrement_agent = EC_Agent(mainwin=mainwin, llm=llm, card=agent_card, skill_set=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

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
    return produrement_agent