from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_rpa_supervisor_chat_task, create_ec_rpa_supervisor_daily_task, create_ec_rpa_supervisor_on_request_task
from utils.logger_helper import logger_helper as logger
from agent.playwright import create_browser_use_llm

import traceback

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
        logger.info("agent card created:", agent_card.name, agent_card.url)

        chatter_task = create_ec_rpa_supervisor_chat_task(mainwin)
        daily_task = create_ec_rpa_supervisor_daily_task(mainwin)
        on_request_task = create_ec_rpa_supervisor_on_request_task(mainwin)
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        supervisor = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=[schedule_skill, serve_request_skill, chatter_skill], tasks=[daily_task, on_request_task, chatter_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECRPASupervisorAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECRPASupervisorAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None
    return supervisor