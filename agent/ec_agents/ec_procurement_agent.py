from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_ec_procurement_chat_task, create_ec_procurement_work_task
from agent.playwright import create_browser_use_llm

from utils.logger_helper import logger_helper as logger
from utils.str_utils import all_substrings
import traceback



def set_up_ec_procurement_agent(mainwin):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        logger.debug("set_up_ec_procurement_agent", [sk.name for sk in agent_skills])
        # Search for worker skill: must contain "search" and "digikey"
        # Note: search_digikey_chatter can serve as both worker and chatter skill
        worker_skill = next((sk for sk in agent_skills if all_substrings(["search","digikey"], sk.name)), None)
        # Search for chatter skill: must contain "search", "digikey", and "chatter"
        chatter_skill = next((sk for sk in agent_skills if all_substrings(["search","digikey","chatter"], sk.name)),None)


        # 确保只有有效的技能被添加到skills列表中
        valid_skills = []
        if worker_skill:
            valid_skills.append(worker_skill)
            logger.info("ec_procurement worker skill:", worker_skill.name)
        else:
            logger.error("ec_procurement worker skill not found!")

        if chatter_skill:
            valid_skills.append(chatter_skill)
            logger.info("ec_procurement chatter skill:", chatter_skill.name)
        else:
            logger.error("ec_procurement chatter skill not found!")
        
        # 如果没有有效技能，记录错误并返回None
        if not valid_skills:
            logger.error("No valid skills found for ec_procurement agent!")
            logger.error(f"Available skills: {[sk.name for sk in agent_skills] if agent_skills else 'None'}")
            return None

        agent_card = AgentCard(
            name="Engineering Procurement Agent",
            description="Procure parts for product development",
            url=get_a2a_server_url(mainwin) or "http://localhost:3600",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=valid_skills,
        )
        logger.info("ec_procurement agent card created:", agent_card.id, agent_card.name, agent_card.url)

        org_id = "org_rnd_001"
        chatter_task = create_ec_procurement_chat_task(mainwin)
        if not chatter_task:
            logger.error("Failed to create chatter task for ec_procurement agent! Aborting setup.")
            return None
            
        worker_task = create_ec_procurement_work_task(mainwin)
        if not worker_task:
            logger.error("Failed to create worker task for ec_procurement agent! Aborting setup.")
            return None
            
        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm
        
        produrement_agent = EC_Agent(mainwin=mainwin, skill_llm=llm,
                                     llm=browser_use_llm,
                                     task="",
                                     card=agent_card,
                                     org_id = org_id,
                                     skills=valid_skills,
                                     tasks=[chatter_task, worker_task])
        logger.info("ec_procurement agent ready to go!")

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpECProcurementAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpECProcurementAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None
    return produrement_agent