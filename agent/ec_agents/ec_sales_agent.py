from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_sales_chat_task, create_ec_sales_work_task
from utils.logger_helper import logger_helper as logger
from agent.playwright import create_browser_use_llm

import traceback


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
        logger.info("agent card created:", agent_card.name, agent_card.url)

        chatter_task = create_ec_sales_chat_task(mainwin)
        worker_task = create_ec_sales_work_task(mainwin)
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        sales = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=[worker_skill, chatter_skill], tasks=[worker_task, chatter_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECSalesAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECSalesAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None

    return sales
