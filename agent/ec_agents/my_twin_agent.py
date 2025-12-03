from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.langgraph_agent.utils import get_a2a_server_url
from agent.ec_agents.create_agent_tasks import create_my_twin_chat_task
import traceback
import typing
from utils.logger_helper import logger_helper as logger
from agent.playwright import create_browser_use_llm
if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow

# 固定的 My Twin Agent ID - 这是系统默认的后台 agent
MY_TWIN_AGENT_ID = "system_my_twin_agent"
MY_TWIN_AGENT_NAME = "My Twin Agent"

def set_up_my_twin_agent(mainwin: 'MainWindow'):
    try:
        llm = mainwin.llm
        agent_skills = mainwin.agent_skills
        # a2a client+server
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for my digital twin"), None)
        
        if not chatter_skill:
            logger.error(f"[MyTwinAgent] Critical Error: Skill 'chatter for my digital twin' not found! Agent setup aborted.")
            return None
            
        logger.info("chatter skill found:", chatter_skill.name)
        
        # 使用固定的 ID 和 name 创建 agent card
        agent_card = AgentCard(
                id=MY_TWIN_AGENT_ID,  # 固定 ID
                name=MY_TWIN_AGENT_NAME,  # 固定 name
                description="Human Representative (System Background Agent)",
                url=get_a2a_server_url(mainwin) or "http://localhost:3600",
                version="1.0.0",
                defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
                capabilities=capabilities,
                skills=[chatter_skill],
        )
        logger.info(f"[MyTwinAgent] Created system agent with fixed ID: {MY_TWIN_AGENT_ID}, name: {MY_TWIN_AGENT_NAME}")
        chat_task = create_my_twin_chat_task(mainwin)
        
        if not chat_task:
            logger.error(f"[MyTwinAgent] Critical Error: Failed to create chat task! Agent setup aborted.")
            return None

        # Use mainwin's unified browser_use_llm instance (shared across all agents)
        browser_use_llm = mainwin.browser_use_llm

        helper = EC_Agent(mainwin=mainwin, skill_llm=llm, llm=browser_use_llm, task="", card=agent_card, skills=[chatter_skill], tasks=[chat_task])

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSetUpMyTwinAgent:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSetUpMyTwinAgent: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return None
    return helper
