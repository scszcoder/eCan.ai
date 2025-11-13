from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_self_tester_chat_task, create_ec_self_tester_work_task
from utils.logger_helper import logger_helper as logger
from agent.ec_agents.create_dev_task import create_skill_dev_task
from agent.playwright import create_browser_use_llm

import traceback



def set_up_ec_tester_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        worker_skill = next((sk for sk in agent_skills if sk and "self test" in sk.name.lower()), None)
        if worker_skill:
            logger.info("ec_tester worker skill:", worker_skill.name)
        else:
            logger.error("ec_tester worker skill not found! Make sure 'eCan.ai self test' skill is built.")
        chatter_skill = next((sk for sk in agent_skills if sk and sk.name == "self_test_chatter"), None)
        if chatter_skill:
            logger.info("ec_tester chatter skill:", chatter_skill.name)
        else:
            logger.error("ec_tester chatter skill not found! Make sure 'chatter for ecan.ai self test' is built.")

        test_dev_skill = next((sk for sk in agent_skills if sk and sk.name == "test skill under development"), None)
        if test_dev_skill:
            logger.info("ec_tester test dev skill:", test_dev_skill.name)
        else:
            logger.error("ec_tester test dev skill not found! Make sure 'test dev for ecan.ai self test' is built.")

        # Ensure we have at least one valid skill; otherwise abort setup gracefully
        skills_for_card = [s for s in [worker_skill, chatter_skill, test_dev_skill] if s is not None]
        if not skills_for_card:
            logger.error("ec_tester_agent setup aborted: no valid skills available.")
            return None

        agent_card = AgentCard(
            name="Self Tester Agent",
            description="Self Test eCan.ai",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            organization="research and development",
            title = "test engineer",
            skills=skills_for_card,
        )
        logger.info("ec_tester agent card created:", agent_card.name, agent_card.url)

        chatter_task = create_ec_self_tester_chat_task(mainwin)
        worker_task = create_ec_self_tester_work_task(mainwin)
        dev_run_task = create_skill_dev_task(mainwin)

        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        produrement_agent = EC_Agent(
            mainwin=mainwin,
            skill_llm=llm,
            llm=browser_use_llm,
            task="",
            card=agent_card,
            skills=skills_for_card,
            tasks=[t for t in [chatter_task, worker_task, dev_run_task] if t is not None]
        )

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECTesterAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECTesterAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None
    return produrement_agent