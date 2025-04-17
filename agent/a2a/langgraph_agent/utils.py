from agent.a2a.common.client import A2AClient
from agent.service import Agent
from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.runner.service import Runner

def set_up_ecbot_helper_agent(llm, agent_skills):
    # a2a client+server
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)

    a2a_skill = AgentSkill(
			id=helper_skill.id,
			name=helper_skill.name,
			description=helper_skill.description,
			tags=["currency conversion", "currency exchange"],
			examples=["Please help fix this RPA run failure"],
    )
    host = "127.0.0.1"
    a2a_server_port = 3600
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
    server = A2AServer(
        agent_card=agent_card,
        task_manager=AgentTaskManager( notification_sender_auth=notification_sender_auth),
        host=host,
        port=a2a_server_port,
    )

    task = ""
    runner = Runner()
    helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    helper = Agent(task=task, llm=llm, runner=runner, init_skill=helper_skill)

    return helper


def set_up_ec_customer_support_agent(llm, agent_skills):
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
    helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    helper = Agent(task=task, llm=llm, runner=runner, init_skill=helper_skill)

    return helper

def set_up_ec_marketing_agent(llm, agent_skills):
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
    helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    helper = Agent(task=task, llm=llm, runner=runner, init_skill=helper_skill)

    return helper

def set_up_ec_sales_agent(llm, agent_skills):
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
    helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    helper = Agent(task=task, llm=llm, runner=runner, init_skill=helper_skill)

    return helper


def set_up_ec_research_agent(llm, agent_skills):
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
    helper_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    helper = Agent(task=task, llm=llm, runner=runner, init_skill=helper_skill)

    return helper