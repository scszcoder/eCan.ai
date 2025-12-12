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
from agent.ec_skill import EC_Skill
from agent.ec_tasks.models import ManagedTask
from agent.a2a.common.types import AgentCard, AgentCapabilities
from agent.ec_agents.agent_utils import get_a2a_server_url
from utils.logger_helper import logger_helper as logger
from agent.db.services.db_avatar_service import DBAvatarService

if TYPE_CHECKING:
    from gui.MainGUI import MainWindow


def _convert_dict_to_skill(skill_dict: Dict[str, Any]) -> EC_Skill:
    """
    Convert skill dictionary to EC_Skill object.
    
    Args:
        skill_dict: Skill data dictionary from database
        
    Returns:
        EC_Skill object
    """
    try:
        return EC_Skill(
            id=skill_dict.get('id'),
            name=skill_dict.get('name', 'Unnamed Skill'),
            description=skill_dict.get('description', ''),
            source=skill_dict.get('source', 'ui'),
            owner=skill_dict.get('owner', ''),
            version=skill_dict.get('version', '0.0.0'),
            level=skill_dict.get('level', 'entry'),
            path=skill_dict.get('path', ''),
            run_mode=skill_dict.get('run_mode', 'released'),
            # Optional fields
            tags=skill_dict.get('tags'),
            examples=skill_dict.get('examples'),
        )
    except Exception as e:
        logger.error(f"[AgentConverter] Failed to convert skill dict to object: {e}")
        # Return a minimal skill object
        return EC_Skill(
            name=skill_dict.get('name', 'Error Skill'),
            description=f"Failed to load: {e}"
        )


def _convert_dict_to_task(task_dict: Dict[str, Any]) -> ManagedTask:
    """
    Convert task dictionary to ManagedTask object.
    
    Args:
        task_dict: Task data dictionary from database
        
    Returns:
        ManagedTask object
    """
    from agent.a2a.common.types import TaskStatus, TaskState
    
    try:
        # Create required status object
        status = TaskStatus(state=TaskState.SUBMITTED)
        
        # Pass all fields to ManagedTask, let Pydantic validators handle conversion
        # Invalid values will be normalized by field_validator
        return ManagedTask(
            id=task_dict.get('id', str(uuid.uuid4())),
            name=task_dict.get('name', 'Unnamed Task'),
            description=task_dict.get('description', ''),
            source=task_dict.get('source', 'ui'),
            status=status,
            priority=task_dict.get('priority'),  # Validator will handle 'none' -> None
        )
    except Exception as e:
        logger.error(f"[AgentConverter] Failed to convert task dict to object: {e}")
        # Return a minimal task object with required fields
        try:
            status = TaskStatus(state=TaskState.SUBMITTED)
            return ManagedTask(
                id=str(uuid.uuid4()),
                name=task_dict.get('name', 'Error Task'),
                description=f"Failed to load: {e}",
                status=status,
            )
        except Exception as e2:
            logger.error(f"[AgentConverter] Failed to create fallback task: {e2}")
            raise


def _validate_and_filter_entities(data_list, entity_type, agent_id, agent_name):
    """
    Validate and filter entity data (skills/tasks).
    
    Filters out:
    - Relationship objects (have agent_id + skill_id/task_id but no name)
    - Invalid objects (missing name field)
    - Non-dict items
    
    Logs errors when relationship objects are detected.
    
    Args:
        data_list: List of entity dictionaries
        entity_type: 'skill' or 'task' for logging
        agent_id: Agent ID for error reporting
        agent_name: Agent name for error reporting
        
    Returns:
        List of valid entity objects with 'name' field
    """
    if not data_list:
        return []
    
    valid_entities = []
    
    for idx, item in enumerate(data_list):
        # Skip non-dict items with detailed error
        if not isinstance(item, dict):
            logger.error(
                f"[AgentConverter] ❌ Invalid {entity_type} type at index {idx}\n"
                f"  Agent: {agent_name} ({agent_id})\n"
                f"  Expected: dict (object with fields)\n"
                f"  Got: {type(item).__name__}\n"
                f"  Value: {repr(item)[:200]}\n"
                f"  Hint: Check DBAgent.to_dict(deep=True) - should return list of dicts, not list of strings/IDs"
            )
            continue
        
        # Detect relationship object: has agent_id and skill_id/task_id but no name
        entity_id_field = f"{entity_type}_id"
        is_relationship = (
            'agent_id' in item and 
            entity_id_field in item and 
            'name' not in item
        )
        
        if is_relationship:
            # Log error: relationship object should not be here
            logger.error(
                f"[AgentConverter] ❌ Data format error: Relationship object in {entity_type}s data\n"
                f"  Agent: {agent_name} ({agent_id}), Index: {idx}\n"
                f"  Found: agent_id={item.get('agent_id')}, {entity_id_field}={item.get(entity_id_field)}\n"
                f"  Expected: Entity object with 'name' field\n"
                f"  Hint: Check DBAgent.to_dict() - should return entity objects, not relationship objects"
            )
            continue
        
        # Keep valid entity objects (have 'name' field)
        if 'name' in item:
            valid_entities.append(item)
        else:
            logger.error(
                f"[AgentConverter] ❌ Invalid {entity_type} at index {idx}: missing 'name' field\n"
                f"  Agent: {agent_name} ({agent_id})\n"
                f"  Item keys: {list(item.keys())}\n"
                f"  Item preview: {str(item)[:200]}\n"
                f"  Hint: Entity objects must have a 'name' field"
            )
    
    return valid_entities


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
            tasks=[],  # Will be set after validation and conversion
            skills=[],  # Will be set after validation and conversion
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
        
        # ✅ Validate, filter, and convert skills/tasks data to objects
        # Detects relationship objects and logs errors
        filtered_skills_dicts = _validate_and_filter_entities(
            skills_data, 'skill', agent_data.get('id'), agent_data.get('name')
        )
        filtered_tasks_dicts = _validate_and_filter_entities(
            tasks_data, 'task', agent_data.get('id'), agent_data.get('name')
        )
        
        # Convert dictionaries to objects
        skill_objects = [_convert_dict_to_skill(s) for s in filtered_skills_dicts]
        task_objects = [_convert_dict_to_task(t) for t in filtered_tasks_dicts]
        
        # Update EC_Agent with converted objects
        ec_agent.skills = skill_objects
        ec_agent.tasks = task_objects
        
        logger.debug(f"[AgentConverter] ✅ Converted agent: {agent_data.get('name')}, org_id: {ec_agent.org_id}")
        return ec_agent
        
    except Exception as e:
        logger.error(f"[AgentConverter] ❌ Failed to convert agent {agent_data.get('name')}: {e}")
        logger.error(f"[AgentConverter] Traceback: {traceback.format_exc()}")
        return None
