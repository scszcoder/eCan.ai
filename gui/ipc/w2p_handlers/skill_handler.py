import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict, Tuple
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from gui.LoginoutGUI import Login
from utils.logger_helper import logger_helper as logger

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
                    logger.debug(f"Converted skill: {sk_dict.get('name', 'NO NAME')}")
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

            # Update memory
            _update_skill_in_memory(actual_skill_id, skill_data)

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

            # Update memory
            _update_skill_in_memory(skill_id, skill_data)

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

        # Get database service
        skill_service = _get_skill_service()
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Delete from database
        result = skill_service.delete_skill(skill_id)

        if result.get('success'):
            logger.info(f"Skill deleted successfully from database: {skill_id}")

            # Remove from memory
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
        Dict containing clean skill data
    """
    return {
        'id': skill_id,
        'name': skill_data['name'],
        'owner': skill_data['owner'],
        'description': skill_data['description'],
        'version': skill_data['version'],
        'level': skill_data['level'],
        'public': skill_data.get('public', False),
        'rentable': skill_data.get('rentable', False),
        'price': skill_data.get('price', 0)
    }
