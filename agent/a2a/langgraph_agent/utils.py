from agent.a2a.common.client import A2AClient
from agent.service import Agent
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.tasks import TaskScheduler
from agent.runner.service import Runner
import traceback
import socket


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


def set_up_ecbot_helper_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

        a2a_skill = AgentSkill(
                id=helper_skill.id,
                name=helper_skill.name,
                description=helper_skill.description,
                tags=["help fix errors", "help fix failure"],
                examples=["Please help fix this RPA run failure"],
        )
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)
        if free_ports:
            return None
        a2a_server_port = free_ports[0]

        agent_card = AgentCard(
                name="ECBot Helper Agent",
                description="Helps with ECBot RPA works",
                url=f"http://{host}:{a2a_server_port}/",
                version="1.0.0",
                defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                capabilities=capabilities,
                skills=[a2a_skill],
        )
        a2a_client = A2AClient(agent_card)
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        a2a_server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager( notification_sender_auth=notification_sender_auth),
            host=host,
            port=a2a_server_port,
        )

        task = ""
        task_scheduler = TaskScheduler()
        helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
        helper = Agent(task=task, llm=llm, a2a_client=a2a_client, a2a_server=a2a_server, task_scheduler=task_scheduler, init_skill=helper_skill)

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
        helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa operator"), None)

        a2a_skill = AgentSkill(
            id=helper_skill.id,
            name=helper_skill.name,
            description=helper_skill.description,
            tags=["run RPA works", "run RPA missions"],
            examples=["Please help operate these RPA missions"],
        )
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)
        if free_ports:
            return None
        a2a_server_port = free_ports[0]

        agent_card = AgentCard(
            name="ECBot RPA Operator Agent",
            description="Run ECBot RPA works",
            url=f"http://{host}:{a2a_server_port}/",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[a2a_skill],
        )
        a2a_client = A2AClient(agent_card)
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        a2a_server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(notification_sender_auth=notification_sender_auth),
            host=host,
            port=a2a_server_port,
        )

        task = ""
        task_scheduler = TaskScheduler()
        support_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
        customer_support = Agent(task=task, llm=llm, a2a_client=a2a_client, a2a_server=a2a_server,
                         task_scheduler=task_scheduler,
                         init_skill=support_skill)

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
        helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa operator"), None)

        a2a_skill = AgentSkill(
            id=helper_skill.id,
            name=helper_skill.name,
            description=helper_skill.description,
            tags=["run RPA works", "run RPA missions"],
            examples=["Please help operate these RPA missions"],
        )
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)
        if free_ports:
            return None
        a2a_server_port = free_ports[0]

        agent_card = AgentCard(
            name="ECBot RPA Operator Agent",
            description="Run ECBot RPA works",
            url=f"http://{host}:{a2a_server_port}/",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[a2a_skill],
        )
        a2a_client = A2AClient(agent_card)
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        a2a_server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(notification_sender_auth=notification_sender_auth),
            host=host,
            port=a2a_server_port,
        )

        task = ""
        task_scheduler = TaskScheduler()
        operator_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa operator"), None)
        operator = Agent(task=task, llm=llm, a2a_client=a2a_client, a2a_server=a2a_server, task_scheduler=task_scheduler,
                       init_skill=operator_skill)

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
        helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor"), None)

        a2a_skill = AgentSkill(
            id=helper_skill.id,
            name=helper_skill.name,
            description=helper_skill.description,
            tags=["Supervise run RPA works", "Supervise run RPA missions"],
            examples=["Please supervise this RPA run works"],
        )
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)
        if free_ports:
            return None
        a2a_server_port = free_ports[0]

        agent_card = AgentCard(
            name="ECBot Supervisor Agent",
            description="ECBot RPA Supervisor",
            url=f"http://{host}:{a2a_server_port}/",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[a2a_skill],
        )
        a2a_client = A2AClient(agent_card)
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        a2a_server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(notification_sender_auth=notification_sender_auth),
            host=host,
            port=a2a_server_port,
        )

        task = ""
        task_scheduler = TaskScheduler()
        supervisor_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor"), None)
        supervisor = Agent(task=task, llm=llm, a2a_client=a2a_client, a2a_server=a2a_server, task_scheduler=task_scheduler,
                       init_skill=supervisor_skill)

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
    # a2a client+server
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    a2a_skill = AgentSkill(
			id="convert_currency",
			name="Currency Exchange Rates Tool",
			description="Helps with exchange values between various currencies",
			tags=["currency conversion", "currency exchange"],
			examples=["What is exchange rate between USD and GBP?"],
    )
    host = "127.0.0.1"
    port = str(4668)
    agent_card = AgentCard(
			name="ECBot Helper Agent",
			description="Helps with ECBot RPA works",
			url=f"http://{host}:{port}/",
			version="1.0.0",
			defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
			defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
			capabilities=capabilities,
			skills=[a2a_skill],
		)

    notification_sender_auth = PushNotificationSenderAuth()
    notification_sender_auth.generate_jwk()

    a2a_server_port = 3600

    task = ""
    runner = Runner()
    marketer_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    marketer = Agent(task=task, llm=llm, runner=runner, init_skill=helper_skill)

    return marketer

def set_up_ec_sales_agent(mainwin):
    # a2a client+server
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    a2a_skill = AgentSkill(
			id="convert_currency",
			name="Currency Exchange Rates Tool",
			description="Helps with exchange values between various currencies",
			tags=["currency conversion", "currency exchange"],
			examples=["What is exchange rate between USD and GBP?"],
    )
    host = "127.0.0.1"
    port = str(4668)
    agent_card = AgentCard(
			name="ECBot Helper Agent",
			description="Helps with ECBot RPA works",
			url=f"http://{host}:{port}/",
			version="1.0.0",
			defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
			defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
			capabilities=capabilities,
			skills=[a2a_skill],
		)

    notification_sender_auth = PushNotificationSenderAuth()
    notification_sender_auth.generate_jwk()

    a2a_server_port = 3600

    task = ""
    runner = Runner()
    sales_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    sales = Agent(task=task, llm=llm, runner=runner, init_skill=sales_skill)

    return sales


def set_up_ec_research_agent(mainwin):
    # a2a client+server
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    a2a_skill = AgentSkill(
			id="convert_currency",
			name="Currency Exchange Rates Tool",
			description="Helps with exchange values between various currencies",
			tags=["currency conversion", "currency exchange"],
			examples=["What is exchange rate between USD and GBP?"],
    )
    host = "127.0.0.1"
    port = str(4668)
    agent_card = AgentCard(
			name="ECBot Helper Agent",
			description="Helps with ECBot RPA works",
			url=f"http://{host}:{port}/",
			version="1.0.0",
			defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
			defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
			capabilities=capabilities,
			skills=[a2a_skill],
		)

    notification_sender_auth = PushNotificationSenderAuth()
    notification_sender_auth.generate_jwk()

    a2a_server_port = 3600

    task = ""
    runner = Runner()
    researcher_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    marketing_researcher = Agent(task=task, llm=llm, runner=runner, init_skill=researcher_skill)

    return marketing_researcher