from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_helper_chat_task, create_ec_helper_work_task
from utils.logger_helper import logger_helper as logger
from agent.playwright import create_browser_use_llm

import traceback

def set_up_ec_helper_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa helper"), None)
        logger.info("worker_skill", getattr(worker_skill, 'name', None))
        logger.info("chatter_skill", getattr(chatter_skill, 'name', None))
        
        # 确保只有有效的技能被添加到skills列表中
        valid_skills = []
        if worker_skill:
            valid_skills.append(worker_skill)
        else:
            logger.error("No worker skill found for ec_helper agent!")
        if chatter_skill:
            valid_skills.append(chatter_skill)
        else:
            logger.error("No chatter skill found for ec_helper agent!")

        # 如果没有有效技能，记录错误并返回None
        if not valid_skills:
            logger.error("No valid skills found for ec_helper agent!")
        
        agent_card = AgentCard(
            name="ECBot Helper Agent",
            description="Helps with ECBot RPA works",
            url=get_a2a_server_url(mainwin) or "http://127.0.0.1:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=valid_skills,
        )

        logger.info("agent card created:", agent_card.name, agent_card.url)
        chatter_task = create_ec_helper_chat_task(mainwin)
        worker_task = create_ec_helper_work_task(mainwin)
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm

        # 尝试创建 EC_Agent，如果失败则使用备用方案
        try:
            helper = EC_Agent(
                mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="",
                card=agent_card, skills=valid_skills, tasks=[worker_task, chatter_task]
            )
        except RuntimeError as re:
            logger.error(f"Warning: browser_use resource loading failed in PyInstaller environment: {re}")
            logger.error("Attempting to create EC_Agent without browser_use features...")
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        if traceback_info:
            ex_stat = "ErrorSetUpECBOTHelperAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECBOTHelperAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None
    return helper
