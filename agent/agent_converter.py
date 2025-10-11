"""
Agent Converter Utility

Provides common functions to convert agent data (dict) to EC_Agent objects.
Used by both MainGUI and IPC handlers to ensure consistency.
"""

import json
import uuid
import traceback
from typing import Dict, Any, Optional, TYPE_CHECKING

from agent.ec_agent import EC_Agent
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.ec_agents.agent_utils import get_a2a_server_url
from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from gui.MainGUI import MainWindow


def convert_agent_dict_to_ec_agent(
    agent_data: Dict[str, Any],
    main_window: 'MainWindow'
) -> Optional[EC_Agent]:
    """
    Convert agent data (dict) to EC_Agent object.
    
    This is the standard conversion logic used across the application
    to ensure consistency between MainGUI and IPC handlers.
    
    Args:
        agent_data: Agent data dictionary from database
        main_window: MainWindow instance for accessing llm and other resources
        
    Returns:
        EC_Agent object or None if conversion fails
    """
    try:
        # Create capabilities
        capabilities_data = agent_data.get('capabilities')
        if isinstance(capabilities_data, dict):
            capabilities = AgentCapabilities(**capabilities_data)
        else:
            capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        
        # Create AgentCard
        card = AgentCard(
            id=agent_data.get('id', str(uuid.uuid4())),
            name=agent_data.get('name', 'Unknown Agent'),
            description=agent_data.get('description') or '',
            url=agent_data.get('url') or get_a2a_server_url(main_window) or "http://localhost:3600",
            version=agent_data.get('version') or '1.0.0',
            capabilities=capabilities,
            skills=[]  # DB agents don't have skills initially
        )
        
        # Get org_id and convert to list
        org_id = agent_data.get('org_id')
        org_ids = [org_id] if org_id else []
        
        # Parse extra_data if it's a JSON string
        extra_data = agent_data.get('extra_data', {})
        if isinstance(extra_data, str):
            try:
                extra_data = json.loads(extra_data) if extra_data else {}
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"[AgentConverter] Failed to parse extra_data JSON: {extra_data}")
                extra_data = {}
        elif not isinstance(extra_data, dict):
            extra_data = {}
        
        # Create browser_use compatible LLM
        try:
            browser_use_llm = BrowserUseChatOpenAI(model='gpt-4.1-mini')
        except Exception as e:
            logger.warning(f"[AgentConverter] Failed to create BrowserUseChatOpenAI: {e}")
            browser_use_llm = None
        
        # Create EC_Agent object
        ec_agent = EC_Agent(
            mainwin=main_window,
            skill_llm=main_window.llm,
            llm=browser_use_llm or main_window.llm,
            task="",  # Required by parent Agent class
            tasks=[],
            skill_set=[],
            card=card,
            supervisors=[agent_data.get('supervisor_id')] if agent_data.get('supervisor_id') else [],
            subordinates=[],
            peers=[],
            rank=agent_data.get('rank', 'member'),
            org_ids=org_ids,
            title=agent_data.get('title', ''),
            gender=agent_data.get('gender', 'male'),
            birthday=agent_data.get('birthday'),
            personalities=agent_data.get('personality_traits', []),
            vehicle=extra_data.get('default_vehicle_id')
        )
        
        logger.debug(f"[AgentConverter] ✅ Converted agent: {agent_data.get('name')}, org_ids: {ec_agent.org_ids}")
        return ec_agent
        
    except Exception as e:
        logger.error(f"[AgentConverter] ❌ Failed to convert agent {agent_data.get('name')}: {e}")
        logger.error(f"[AgentConverter] Traceback: {traceback.format_exc()}")
        return None
