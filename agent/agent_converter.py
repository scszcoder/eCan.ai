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
from utils.logger_helper import logger_helper as logger
from agent.db.services.db_avatar_service import DBAvatarService

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
            url=agent_data.get('url') or get_a2a_server_url(main_window),
            version=agent_data.get('version') or '1.0.0',
            capabilities=capabilities,
            skills=[]  # DB agents don't have skills initially
        )
        
        # Get org_id (single value)
        org_id = agent_data.get('org_id')
        
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
        
        # Create browser_use compatible LLM from main_window configuration (no fallback)
        from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
        browser_use_llm = create_browser_use_llm(mainwin=main_window, skip_playwright_check=True)
        if not browser_use_llm:
            raise ValueError("Failed to create browser_use LLM from main_window. Please configure LLM provider API key in Settings.")
        
        avatar = agent_data.get('avatar') or DBAvatarService.generate_default_avatar(agent_data.get('id'))
        
        # Extract relationship data from agent_data
        # IMPORTANT: Database returns relationship objects (dicts), but EC_Agent expects:
        # - skills: EC_Skill objects (not implemented yet, so keep empty)
        # - tasks: ManagedTask objects (not implemented yet, so keep empty)
        # These relationship data are stored separately for frontend display via to_dict()
        skills_data = agent_data.get('skills', [])
        tasks_data = agent_data.get('tasks', [])
        title = agent_data.get('title', '')
        if isinstance(title, str) and title.startswith('['):
            try:
                title = json.loads(title)
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Parse personalities if it's a JSON string
        personalities = agent_data.get('personalities', [])
        if isinstance(personalities, str) and personalities.startswith('['):
            try:
                personalities = json.loads(personalities)
            except (json.JSONDecodeError, ValueError):
                personalities = []
        
        main_window_llm = getattr(main_window, 'llm', None)
        
        ec_agent = EC_Agent(
            mainwin=main_window,
            skill_llm=main_window_llm,
            llm=browser_use_llm or main_window_llm,
            task="",  # Required by parent Agent class
            tasks=[],  # Don't pass raw DB data - EC_Agent expects ManagedTask objects
            skills=[],  # Don't pass raw DB data - EC_Agent expects EC_Skill objects
            card=card,
            supervisor_id=agent_data.get('supervisor_id'),
            rank=agent_data.get('rank', 'member'),
            org_id=org_id,
            title=title,
            gender=agent_data.get('gender', 'male'),
            birthday=agent_data.get('birthday'),
            personalities=personalities,
            vehicle=agent_data.get('vehicle_id'),  # 只使用标准字段
            avatar=avatar
        )
        
        # Store additional fields that might not be in __init__ but needed for serialization
        ec_agent.owner = agent_data.get('owner')
        ec_agent.description = agent_data.get('description', '')
        ec_agent.status = agent_data.get('status', 'active')
        ec_agent.vehicle_id = agent_data.get('vehicle_id')  # 只使用标准字段
        ec_agent.extra_data = agent_data.get('extra_data', '')
        
        # ✅ Store raw relationship data for frontend display (to_dict)
        # These are dicts from database, not EC_Skill/ManagedTask objects
        ec_agent._db_skills = skills_data  # Store for to_dict() serialization
        ec_agent._db_tasks = tasks_data    # Store for to_dict() serialization
        
        logger.debug(f"[AgentConverter] ✅ Converted agent: {agent_data.get('name')}, org_id: {ec_agent.org_id}")
        return ec_agent
        
    except Exception as e:
        logger.error(f"[AgentConverter] ❌ Failed to convert agent {agent_data.get('name')}: {e}")
        logger.error(f"[AgentConverter] Traceback: {traceback.format_exc()}")
        return None
