from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_rpa_operator_chat_task, create_ec_rpa_operator_work_task
from utils.logger_helper import logger_helper as logger
from agent.playwright import create_browser_use_llm

import traceback

def set_up_ec_rpa_operator_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if "ecbot rpa operator" in sk.name), None)
        if worker_skill:
            logger.info("agent_skill", worker_skill.name)
        else:
            logger.warning("Warning: worker_skill not found")
        chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa operator chatter"),None)
        if chatter_skill:
            logger.info("chatter_skill", chatter_skill.name)
        else:
            logger.warning("Warning: chatter_skill not found")

        # 过滤掉 None 值
        valid_skills = [skill for skill in [worker_skill, chatter_skill] if skill is not None]

        if not valid_skills:
            logger.error("Error: No valid skills found for ECBot RPA Operator Agent")
            return None

        agent_card = AgentCard(
            name="ECBot RPA Operator Agent",
            description="Run and operates ECBot RPA bots to do their scheduled work",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=valid_skills,
        )
        logger.info("agent card created:", agent_card.name, agent_card.url)

        chatter_task = create_ec_rpa_operator_chat_task(mainwin)
        worker_task = create_ec_rpa_operator_work_task(mainwin)

        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm

        # 过滤掉 None 值的任务列表
        valid_tasks = [task for task in [worker_task, chatter_task] if task is not None]

        operator = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=valid_skills, tasks=valid_tasks)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECRPAOperatorAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECRPAOperatorAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None
    return operator