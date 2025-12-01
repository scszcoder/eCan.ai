import traceback
import asyncio
import requests
from typing import TYPE_CHECKING, Any, Optional, Dict, Tuple
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.constants import Operation

# --- Simple in-memory simulation state for step-sim debug ---
_SIM_BUNDLE: Optional[Dict[str, Any]] = None
_SIM_CURRENT_SHEET_ID: Optional[str] = None
_SIM_CURRENT_NODE_ID: Optional[str] = None
_SIM_COUNTER: int = 0

# Whitelist the debug endpoints to avoid auth friction during editor testing
IPCHandlerRegistry.add_to_whitelist('setup_sim_step')
IPCHandlerRegistry.add_to_whitelist('step_sim')
IPCHandlerRegistry.add_to_whitelist('test_langgraph2flowgram')


@IPCHandlerRegistry.handler('get_agent_skills')
def handle_get_agent_skills(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get agent skills list, supports dual data sources: local database + cloud data

    On startup, prioritizes reading from local database, builds test skills in memory,
    then requests cloud data. If cloud data exists, it overwrites local data and updates database.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' field

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get agent skills handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get agent skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        username = data['username']
        logger.info(f"Getting agent skills for user: {username}")

        # Read skill data directly from memory (build_agent_skills has completed all data integration)
        try:
            main_window = AppContext.get_main_window()
            memory_skills = main_window.agent_skills or []
            logger.info(f"Found {len(memory_skills)} skills in memory (mainwin.agent_skills)")

            # Convert memory skills to dictionary format
            skills_dicts = []
            for i, sk in enumerate(memory_skills):
                try:
                    sk_dict = sk.to_dict()
                    # Ensure necessary fields exist
                    sk_dict['owner'] = username
                    if 'id' not in sk_dict:
                        sk_dict['id'] = f"skill_{i}"
                    skills_dicts.append(sk_dict)
                    logger.debug(f"Converted skill: {sk_dict.get('name', 'NO NAME')} (id: {sk_dict.get('id', 'NO ID')})")
                except Exception as e:
                    logger.error(f"Failed to convert skill {i}: {e}")

            logger.info(f"Returning {len(skills_dicts)} skills to frontend")

            resultJS = {
                'skills': skills_dicts,
                'message': 'Get skills successful',
                'source': 'memory'
            }
            return create_success_response(request, resultJS)

        except Exception as e:
            logger.error(f"Failed to get agent skills from memory: {e}")
            # Return empty list as fallback
            return create_success_response(request, {
                'skills': [],
                'message': 'No agent skills available',
                'source': 'empty'
            })

    except Exception as e:
        logger.error(f"Error in get agent skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_AGENT_SKILLS_ERROR',
            f"Error during get agent skills: {str(e)}"
        )
    
@IPCHandlerRegistry.handler('save_agent_skill')
def handle_save_agent_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle saving agent skill workflow to local database

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'skill_info' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Save agent skill handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'skill_info'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save agent skill: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        skill_info = data['skill_info']
        skill_id = skill_info.get('id')

        if not skill_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Skill ID is required for save operation')

        # Check if this is a read-only skill
        # - 'code': code/example skills (read-only)
        # - 'ui': dynamically created via editor (editable)
        source = skill_info.get('source', 'ui')
        if source == 'code':
            logger.warning(f"Attempted to save code-based skill: {skill_info.get('name')} (source={source})")
            return create_error_response(
                request, 
                'SKILL_READ_ONLY', 
                'Code-based skills cannot be edited. Please modify the source files directly.'
            )

        logger.info(f"Saving agent skill for user: {username}, skill_id: {skill_id}")

        # Get database service
        skill_service = _get_skill_service()
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Prepare skill data
        skill_data = _prepare_skill_data(skill_info, username, skill_id)

        # Check if skill exists
        existing_skill = skill_service.get_skill_by_id(skill_id)

        if existing_skill.get('success') and existing_skill.get('data'):
            # Update existing skill
            logger.info(f"Updating existing skill: {skill_id}")
            result = skill_service.update_skill(skill_id, skill_data)
        else:
            # Create new skill
            logger.info(f"Creating new skill: {skill_id}")
            result = skill_service.add_skill(skill_data)

        if result.get('success'):
            # Get the actual skill_id from database response (in case it was generated)
            actual_skill_id = result.get('id', skill_id)
            logger.info(f"Skill saved successfully: {skill_data['name']} (ID: {actual_skill_id})")

            # Step 2: Update memory after database update succeeds
            _update_skill_in_memory(actual_skill_id, skill_data)

            # Step 3: Clean up offline sync queue for this skill (remove pending add/update operations)
            try:
                from agent.cloud_api.offline_sync_queue import get_offline_sync_queue
                sync_queue = get_offline_sync_queue()
                # Remove any pending add operations (they're now redundant since we're updating)
                removed_add = sync_queue.remove_tasks_by_resource('skill', actual_skill_id, operation='add')
                # Remove any pending update operations (they're now redundant since we have a new update)
                removed_update = sync_queue.remove_tasks_by_resource('skill', actual_skill_id, operation='update')
                if removed_add + removed_update > 0:
                    logger.info(f"[skill_handler] Removed {removed_add + removed_update} pending sync tasks for skill: {actual_skill_id}")
            except Exception as e:
                logger.warning(f"[skill_handler] Failed to clean offline sync queue: {e}")

            # Step 4: Sync to cloud after memory update succeeds (async, fire and forget)
            skill_data_with_id = skill_data.copy()
            skill_data_with_id['id'] = actual_skill_id
            
            # Sync Skill entity
            _trigger_cloud_sync(skill_data_with_id, Operation.UPDATE)
            
            # Sync Skill-Tool relationships (if changed)
            if 'tools' in skill_data:
                _sync_skill_tool_relations(actual_skill_id, skill_data.get('tools', []), Operation.UPDATE)
            
            # Sync Skill-Knowledge relationships (if changed)
            if 'knowledges' in skill_data:
                _sync_skill_knowledge_relations(actual_skill_id, skill_data.get('knowledges', []), Operation.UPDATE)

            # Create clean response
            clean_skill_data = _create_clean_skill_response(actual_skill_id, skill_data)

            return create_success_response(request, {
                'message': 'Save agent skill successful',
                'skill_id': actual_skill_id,
                'data': clean_skill_data
            })
        else:
            logger.error(f"Failed to save agent skill: {result.get('error')}")
            return create_error_response(
                request,
                'SAVE_AGENT_SKILL_ERROR',
                f"Failed to save agent skill: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error in save agent skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_AGENT_SKILL_ERROR',
            f"Error during save agent skill: {str(e)}"
        )

@IPCHandlerRegistry.handler('new_agent_skill')
def handle_new_agent_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle creating new agent skill and saving to local database

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'skill_info' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Create new agent skill handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'skill_info'])
        if not is_valid:
            logger.warning(f"Invalid parameters for create agent skill: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        skill_info = data['skill_info']

        logger.info(f"Creating new agent skill for user: {username}")

        # Get database service
        skill_service = _get_skill_service()
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Prepare skill data (without ID - let database generate it)
        skill_data = _prepare_skill_data(skill_info, username, skill_id=None)

        # Create new skill in database
        logger.info(f"Creating new skill: {skill_data['name']}")
        result = skill_service.add_skill(skill_data)

        if result.get('success'):
            # Get the database-generated skill ID
            skill_id = result.get('id')
            if not skill_id:
                logger.error("Database did not return skill ID after creation")
                return create_error_response(
                    request,
                    'CREATE_SKILL_ERROR',
                    'Database did not return skill ID'
                )

            logger.info(f"Skill created successfully: {skill_data['name']} (ID: {skill_id})")

            # Step 2: Update memory after database creation succeeds
            _update_skill_in_memory(skill_id, skill_data)

            # Step 3: Sync to cloud after memory update succeeds (async, fire and forget)
            skill_data_with_id = skill_data.copy()
            skill_data_with_id['id'] = skill_id
            
            # Sync Skill entity
            _trigger_cloud_sync(skill_data_with_id, Operation.ADD)
            
            # Sync Skill-Tool relationships
            if 'tools' in skill_data:
                _sync_skill_tool_relations(skill_id, skill_data.get('tools', []), Operation.ADD)
            
            # Sync Skill-Knowledge relationships
            if 'knowledges' in skill_data:
                _sync_skill_knowledge_relations(skill_id, skill_data.get('knowledges', []), Operation.ADD)

            # Create clean response
            clean_skill_data = _create_clean_skill_response(skill_id, skill_data)

            return create_success_response(request, {
                'message': 'Create agent skill successful',
                'skill_id': skill_id,
                'data': clean_skill_data
            })
        else:
            logger.error(f"Failed to create agent skill: {result.get('error')}")
            return create_error_response(
                request,
                'CREATE_AGENT_SKILL_ERROR',
                f"Failed to create agent skill: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error in create agent skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'CREATE_AGENT_SKILL_ERROR',
            f"Error during create agent skill: {str(e)}"
        )


@IPCHandlerRegistry.handler('delete_agent_skill')
def handle_delete_agent_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle deleting agent skill from database and memory

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'skill_id' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Delete skill handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'skill_id'])
        if not is_valid:
            logger.warning(f"Invalid parameters for delete skill: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        skill_id = data['skill_id']

        logger.info(f"Deleting agent skill for user: {username}, skill_id: {skill_id}")

        # Check if this is a read-only skill (cannot be deleted from UI)
        try:
            main_window = AppContext.get_main_window()
            if main_window and hasattr(main_window, 'agent_skills'):
                for skill in (main_window.agent_skills or []):
                    if hasattr(skill, 'id') and skill.id == skill_id:
                        source = getattr(skill, 'source', 'ui')
                        if source == 'code':
                            logger.warning(f"Attempted to delete code-based skill: {skill_id} (source={source})")
                            return create_error_response(
                                request,
                                'SKILL_READ_ONLY',
                                'Code-based skills cannot be deleted. Please remove the source files directly.'
                            )
                        break
        except Exception as e:
            logger.warning(f"[skill_handler] Failed to check skill source: {e}")

        # Get database service
        skill_service = _get_skill_service()
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Step 1: Delete from database first
        result = skill_service.delete_skill(skill_id)

        if result.get('success'):
            logger.info(f"Skill deleted successfully from database: {skill_id}")

            # Step 2: Remove from memory after database deletion succeeds
            try:
                main_window = AppContext.get_main_window()
                if main_window and hasattr(main_window, 'agent_skills'):
                    original_count = len(main_window.agent_skills or [])
                    main_window.agent_skills = [
                        skill for skill in (main_window.agent_skills or [])
                        if not (hasattr(skill, 'id') and skill.id == skill_id)
                    ]
                    new_count = len(main_window.agent_skills)
                    logger.info(f"[skill_handler] Removed skill from memory: {skill_id} (count: {original_count} → {new_count})")
            except Exception as e:
                logger.warning(f"[skill_handler] Failed to remove skill from memory: {e}")

            # Step 3: Clean up offline sync queue for this skill
            try:
                from agent.cloud_api.offline_sync_queue import get_offline_sync_queue
                sync_queue = get_offline_sync_queue()
                removed_count = sync_queue.remove_tasks_by_resource('skill', skill_id)
                if removed_count > 0:
                    logger.info(f"[skill_handler] Removed {removed_count} pending sync tasks for skill: {skill_id}")
            except Exception as e:
                logger.warning(f"[skill_handler] Failed to clean offline sync queue: {e}")

            # Step 4: Sync deletion to cloud after memory update (async, fire and forget)
            delete_skill_data = {
                'id': skill_id,
                'owner': username,
                'name': f"Skill_{skill_id}"  # Placeholder name for deletion
            }
            _trigger_cloud_sync(delete_skill_data, Operation.DELETE)

            return create_success_response(request, {
                'message': 'Delete agent skill successful',
                'skill_id': skill_id
            })
        else:
            logger.error(f"Failed to delete agent skill: {result.get('error')}")
            return create_error_response(
                request,
                'DELETE_SKILL_ERROR',
                f"Failed to delete agent skill: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error in delete skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'DELETE_SKILL_ERROR',
            f"Error during delete skill: {str(e)}"
        )


# ============================================================================
# Helper Functions for Skill Management
# ============================================================================

def _get_skill_service():
    """Get skill service from mainwin (uses correct user-specific database path)

    Returns:
        skill_service: Database skill service instance, or None if not available
    """
    main_window = AppContext.get_main_window()
    if main_window and hasattr(main_window, 'ec_db_mgr'):
        return main_window.ec_db_mgr.skill_service
    else:
        logger.error("[skill_handler] mainwin.ec_db_mgr not available - cannot access database")
        return None


def _prepare_skill_data(skill_info: Dict[str, Any], username: str, skill_id: Optional[str] = None) -> Dict[str, Any]:
    """Prepare skill data for database storage

    Args:
        skill_info: Raw skill information from frontend
        username: Owner username
        skill_id: Optional skill ID (if None, will be generated by database)

    Returns:
        Dict containing prepared skill data
    """
   
    skill_data = {
        'name': skill_info.get('name', skill_info.get('skillName', 'Unnamed Skill')),
        'owner': username,
        'description': skill_info.get('description', ''),
        'version': skill_info.get('version', '1.0.0'),
        'path': skill_info.get('path', ''),
        'level': skill_info.get('level', 'entry'),
        'config': skill_info.get('config', {}),
        'diagram': skill_info.get('diagram', {}),
        'tags': skill_info.get('tags', []),
        'examples': skill_info.get('examples', []),
        'inputModes': skill_info.get('inputModes', []),
        'outputModes': skill_info.get('outputModes', []),
        'apps': skill_info.get('apps', []),
        'limitations': skill_info.get('limitations', []),
        'price': skill_info.get('price', 0),
        'price_model': skill_info.get('price_model', ''),
        'public': skill_info.get('public', False),
        'rentable': skill_info.get('rentable', False),
    }

    # Only add ID if provided (for updates)
    if skill_id:
        skill_data['id'] = skill_id

    return skill_data


def _update_skill_in_memory(skill_id: str, skill_data: Dict[str, Any]) -> bool:
    """Update or add skill in mainwin.agent_skills memory

    Args:
        skill_id: Skill ID
        skill_data: Skill data dictionary

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        main_window = AppContext.get_main_window()
        if not main_window or not hasattr(main_window, 'agent_skills'):
            logger.warning("[skill_handler] mainwin.agent_skills not available")
            return False

        from agent.ec_skill import EC_Skill

        # Check if skill already exists in memory
        existing_index = None
        for i, skill in enumerate(main_window.agent_skills or []):
            if hasattr(skill, 'id') and skill.id == skill_id:
                existing_index = i
                break

        # Create skill object
        skill_obj = EC_Skill()
        skill_obj.id = skill_id
        skill_obj.name = skill_data['name']
        skill_obj.owner = skill_data['owner']
        skill_obj.description = skill_data['description']
        skill_obj.version = skill_data['version']
        skill_obj.path = skill_data.get('path', '')
        skill_obj.config = skill_data.get('config', {})
        skill_obj.level = skill_data.get('level', 'entry')

        if existing_index is not None:
            # Update existing skill
            main_window.agent_skills[existing_index] = skill_obj
            logger.info(f"[skill_handler] Updated skill in memory: {skill_data['name']}")
        else:
            # Add new skill
            if main_window.agent_skills is None:
                main_window.agent_skills = []
            main_window.agent_skills.append(skill_obj)
            logger.info(f"[skill_handler] Added new skill to memory: {skill_data['name']}")

        return True

    except Exception as e:
        logger.warning(f"[skill_handler] Failed to update mainwin.agent_skills: {e}")
        return False


def _create_clean_skill_response(skill_id: str, skill_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create clean skill data for response (avoid circular references)

    Args:
        skill_id: Skill ID
        skill_data: Skill data dictionary

    Returns:
        Dict containing clean skill data (serializable, no circular refs)
    """
    # Only return primitive types and simple structures
    clean_data = {
        'id': skill_id,
        'name': str(skill_data.get('name', '')),
        'owner': str(skill_data.get('owner', '')),
        'description': str(skill_data.get('description', '')),
        'version': str(skill_data.get('version', '0.0.0')),
        'level': str(skill_data.get('level', 'entry')),
        'public': bool(skill_data.get('public', False)),
        'rentable': bool(skill_data.get('rentable', False)),
        'price': int(skill_data.get('price', 0))
    }
    
    # Add optional fields if they exist and are simple types
    if 'path' in skill_data:
        clean_data['path'] = str(skill_data['path'])
    if 'status' in skill_data:
        clean_data['status'] = str(skill_data['status'])
    
    return clean_data


# ============================================================================
# Cloud Synchronization Functions
# ============================================================================


def _trigger_cloud_sync(skill_data: Dict[str, Any], operation: 'Operation') -> None:
    """Trigger cloud synchronization (async, non-blocking)
    
    Async background execution, doesn't block UI operations, ensures eventual consistency.
    
    Args:
        skill_data: Skill data to sync
        operation: Operation type (Operation enum)
    """
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    
    def _log_result(result: Dict[str, Any]):
        """Log sync result"""
        if result.get('synced'):
            logger.info(f"[skill_handler] ✅ Skill synced to cloud: {operation} - {skill_data.get('name')}")
        elif result.get('cached'):
            logger.info(f"[skill_handler] 💾 Skill cached for later sync: {operation} - {skill_data.get('name')}")
        elif not result.get('success'):
            logger.error(f"[skill_handler] ❌ Failed to sync skill: {result.get('error')}")
    
    # Use SyncManager's thread pool for async execution
    # Note: Use SKILL for Skill entity data (name, description, etc.)
    #       Use AGENT_SKILL for Agent-Skill relationship data (agid, skid, owner)
    manager = get_sync_manager()
    manager.sync_to_cloud_async(DataType.SKILL, skill_data, operation, callback=_log_result)


def _sync_skill_tool_relations(skill_id: str, tool_ids: list, operation: 'Operation') -> None:
    """Sync Skill-Tool relationships to cloud (async, non-blocking)
    
    Args:
        skill_id: Skill ID
        tool_ids: List of tool IDs
        operation: Operation type (ADD/UPDATE/DELETE)
    """
    if not tool_ids:
        return
    
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    from app_context import AppContext
    
    manager = get_sync_manager()
    main_window = AppContext.get_main_window()
    owner = main_window.current_user if main_window else 'unknown'
    
    logger.info(f"[skill_handler] Syncing {len(tool_ids)} tool relationships for skill: {skill_id}")
    
    for tool_id in tool_ids:
        relation_data = {
            'skill_id': skill_id,
            'tool_id': tool_id,
            'owner': owner
        }
        
        def _log_result(result: Dict[str, Any]):
            if result.get('synced'):
                logger.info(f"[skill_handler] ✅ Tool relation synced: {tool_id}")
            elif result.get('cached'):
                logger.info(f"[skill_handler] 💾 Tool relation cached: {tool_id}")
            elif not result.get('success'):
                logger.error(f"[skill_handler] ❌ Failed to sync tool relation: {result.get('error')}")
        
        manager.sync_to_cloud_async(DataType.SKILL_TOOL, relation_data, operation, callback=_log_result)


def _sync_skill_knowledge_relations(skill_id: str, knowledge_ids: list, operation: 'Operation') -> None:
    """Sync Skill-Knowledge relationships to cloud (async, non-blocking)
    
    Args:
        skill_id: Skill ID
        knowledge_ids: List of knowledge IDs
        operation: Operation type (ADD/UPDATE/DELETE)
    """
    if not knowledge_ids:
        return
    
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    from app_context import AppContext
    
    manager = get_sync_manager()
    main_window = AppContext.get_main_window()
    owner = main_window.current_user if main_window else 'unknown'
    
    logger.info(f"[skill_handler] Syncing {len(knowledge_ids)} knowledge relationships for skill: {skill_id}")
    
    for knowledge_id in knowledge_ids:
        relation_data = {
            'skill_id': skill_id,
            'knowledge_id': knowledge_id,
            'owner': owner
        }
        
        def _log_result(result: Dict[str, Any]):
            if result.get('synced'):
                logger.info(f"[skill_handler] ✅ Knowledge relation synced: {knowledge_id}")
            elif result.get('cached'):
                logger.info(f"[skill_handler] 💾 Knowledge relation cached: {knowledge_id}")
            elif not result.get('success'):
                logger.error(f"[skill_handler] ❌ Failed to sync knowledge relation: {result.get('error')}")
        
        manager.sync_to_cloud_async(DataType.SKILL_KNOWLEDGE, relation_data, operation, callback=_log_result)


def sync_skill_from_file(file_path: str) -> Dict[str, Any]:
    """
    Standard function to sync skill from file to database.
    This function reads the skill JSON file and creates/updates the skill in database.
    
    Args:
        file_path: Full path to the skill JSON file
    
    Returns:
        Dict with success status and skill_id
    """
    import json
    
    try:
        # Get username from AppContext
        main_window = AppContext.get_main_window()
        if not main_window or not hasattr(main_window, 'user'):
            raise ValueError("Cannot get username: main_window or main_window.user not available")
        
        username = main_window.user
        logger.debug(f"[skill_handler] Using username: {username}")
        
        # Read skill data from file
        with open(file_path, 'r', encoding='utf-8') as f:
            skill_data = json.load(f)
        
        # Get skill service
        skill_service = _get_skill_service()
        if not skill_service:
            return {'success': False, 'error': 'Database service not available'}
        
        # Check if skill exists by path
        existing_skill = skill_service.get_skill_by_path(file_path)
        
        # Prepare skill data - only use fields that have values
        skill_name = skill_data.get('name') or skill_data.get('skillName', 'Unnamed Skill')
        
        logger.info(f"[skill_handler] Syncing skill: {skill_name}, path: {file_path}")
        
        # Build minimal skill_info - only include fields with actual values
        skill_info = {
            'name': skill_name,
            'path': file_path,
        }
        
        # Add diagram field - check both 'diagram' and 'workFlow' for compatibility
        diagram_data = None
        if 'diagram' in skill_data and skill_data['diagram']:
            diagram_data = skill_data['diagram']
        elif 'workFlow' in skill_data and skill_data['workFlow']:
            diagram_data = skill_data['workFlow']
        
        if diagram_data:
            skill_info['diagram'] = diagram_data
        
        # Add other fields only if they have non-empty values
        optional_fields = ['description', 'version', 'level', 'config', 'tags', 
                          'examples', 'inputModes', 'outputModes', 'apps', 
                          'limitations', 'price', 'price_model', 'public', 'rentable']
        for field in optional_fields:
            if field in skill_data and skill_data[field]:
                skill_info[field] = skill_data[field]
        
        logger.debug(f"[skill_handler] Prepared skill_info with {len(skill_info)} fields")
        
        if existing_skill.get('success') and existing_skill.get('data'):
            # Update existing skill
            skill_id = existing_skill['data']['id']
            logger.info(f"[skill_handler] Updating existing skill: {skill_name} (ID: {skill_id})")
            
            prepared_data = _prepare_skill_data(skill_info, username, skill_id)
            logger.debug(f"[skill_handler] Prepared data for update: path={prepared_data.get('path')}")
            result = skill_service.update_skill(skill_id, prepared_data)
            
            if result.get('success'):
                # Update memory
                _update_skill_in_memory(skill_id, prepared_data)
                
                # Sync to cloud
                skill_data_with_id = prepared_data.copy()
                skill_data_with_id['id'] = skill_id
                _trigger_cloud_sync(skill_data_with_id, Operation.UPDATE)
                
                logger.info(f"[skill_handler] ✅ Skill updated successfully: {skill_name}")
                return {'success': True, 'skill_id': skill_id, 'operation': 'update'}
            else:
                logger.error(f"[skill_handler] ❌ Failed to update skill: {result.get('error')}")
                return {'success': False, 'error': result.get('error')}
        else:
            # Create new skill
            logger.info(f"[skill_handler] Creating new skill: {skill_name}")
            
            prepared_data = _prepare_skill_data(skill_info, username, skill_id=None)
            logger.debug(f"[skill_handler] Prepared data for create: path={prepared_data.get('path')}")
            result = skill_service.add_skill(prepared_data)
            
            if result.get('success'):
                skill_id = result.get('id')
                
                # Update memory
                _update_skill_in_memory(skill_id, prepared_data)
                
                # Sync to cloud
                skill_data_with_id = prepared_data.copy()
                skill_data_with_id['id'] = skill_id
                _trigger_cloud_sync(skill_data_with_id, Operation.ADD)
                
                logger.info(f"[skill_handler] ✅ Skill created successfully: {skill_name} (ID: {skill_id})")
                return {'success': True, 'skill_id': skill_id, 'operation': 'create'}
            else:
                logger.error(f"[skill_handler] ❌ Failed to create skill: {result.get('error')}")
                return {'success': False, 'error': result.get('error')}
                
    except Exception as e:
        logger.error(f"[skill_handler] ❌ Error syncing skill from file: {e}")
        return {'success': False, 'error': str(e)}
