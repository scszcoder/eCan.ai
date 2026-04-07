"""
Skill history IPC handler.

This module provides IPC handlers for skill history operations:
- save_skill_history: Save current skill state to history
- get_skill_history_list: Get history list for a skill
- get_skill_history: Get specific history record
- restore_skill_from_history: Restore skill from history
- delete_skill_history: Delete a history record
- compare_skill_versions: Compare two history versions
"""

import traceback
from typing import Optional, Dict, Any

from gui.ipc.handlers import validate_params, resolve_username
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

# Maximum history records to keep per skill
MAX_HISTORY_PER_SKILL = 100


def _get_history_service(request=None, params=None):
    """Get the skill history service instance."""
    try:
        from agent.db.services.db_skill_history_service import DBSkillHistoryService
        from gui.ipc.context_bridge import get_handler_context

        ctx = get_handler_context(request, params)
        if not ctx:
            logger.warning("[skill_history_handler] No context available")
            return None

        # Get ECDBMgr from context
        ec_db_mgr = ctx.get_ec_db_mgr()
        if ec_db_mgr:
            # Check if skill_history service exists in the db manager
            if hasattr(ec_db_mgr, 'skill_history_service'):
                return ec_db_mgr.skill_history_service
            elif hasattr(ec_db_mgr, 'engine'):
                return DBSkillHistoryService(engine=ec_db_mgr.engine)
            else:
                # Create service with db_manager
                return DBSkillHistoryService(db_manager=ec_db_mgr)

        logger.warning("[skill_history_handler] ECDBMgr not available")
        return None

    except Exception as e:
        logger.error(f"[skill_history_handler] Failed to get history service: {e} {traceback.format_exc()}")
        return None


def _get_skill_service(request=None, params=None):
    """Get the skill service instance."""
    try:
        from gui.ipc.context_bridge import get_handler_context

        ctx = get_handler_context(request, params)
        if not ctx:
            logger.warning("[skill_history_handler] No context available for skill service")
            return None

        # Get ECDBMgr from context
        ec_db_mgr = ctx.get_ec_db_mgr()
        if ec_db_mgr:
            return ec_db_mgr.skill_service

        logger.warning("[skill_history_handler] ECDBMgr not available for skill service")
        return None

    except Exception as e:
        logger.error(f"[skill_history_handler] Failed to get skill service: {e}")
        return None


@IPCHandlerRegistry.handler('save_skill_history')
def handle_save_skill_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save current skill state to history.

    Args:
        request: IPC request object
        params: Request parameters containing 'skill_id' and 'skill_data'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Save skill history handler called with request: {request}")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        skill_id = params.get('skill_id')
        if not skill_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_id')

        skill_data = params.get('skill_data')
        if not skill_data:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_data')

        save_type = params.get('save_type', 'manual')

        logger.info(f"Saving skill history for skill_id: {skill_id}, save_type: {save_type}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Save to history
        result = history_service.save_history(skill_id, skill_data, save_type)

        if result.get('success'):
            history_record = result.get('data', {})
            history_count = history_service.get_history_count(skill_id)
            logger.info(f"Skill history saved successfully: {history_record.get('id')}, total records: {history_count}")

            return create_success_response(request, {
                'history_id': history_record.get('id'),
                'version': history_record.get('version'),
                'version_number': history_record.get('version_number'),
                'history_count': history_count,
                'max_history': MAX_HISTORY_PER_SKILL,
                'data': history_record
            })
        else:
            return create_error_response(request, 'SAVE_HISTORY_ERROR', result.get('error', 'Unknown error'))

    except Exception as e:
        logger.error(f"Error in save skill history handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_SKILL_HISTORY_ERROR',
            f"Error saving skill history: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_skill_history_list')
def handle_get_skill_history_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get history list for a skill.

    Args:
        request: IPC request object
        params: Request parameters containing 'skill_id', optional 'limit' and 'offset'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get skill history list handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        skill_id = params.get('skill_id')
        if not skill_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_id')

        limit = params.get('limit', 100)
        offset = params.get('offset', 0)

        # Ensure limit doesn't exceed maximum
        limit = min(limit, MAX_HISTORY_PER_SKILL)

        logger.info(f"Getting skill history list for skill_id: {skill_id}, limit: {limit}, offset: {offset}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Get history list
        result = history_service.get_history_list(skill_id, limit, offset)

        if result.get('success'):
            return create_success_response(request, {
                'history_list': result.get('data', []),
                'total': result.get('total', 0),
                'limit': limit,
                'offset': offset,
                'max_history': MAX_HISTORY_PER_SKILL
            })
        else:
            return create_error_response(request, 'GET_HISTORY_LIST_ERROR', result.get('error', 'Unknown error'))

    except Exception as e:
        logger.error(f"Error in get skill history list handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_SKILL_HISTORY_LIST_ERROR',
            f"Error getting skill history list: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_skill_history')
def handle_get_skill_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get a specific history record.

    Args:
        request: IPC request object
        params: Request parameters containing 'history_id'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get skill history handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        history_id = params.get('history_id')
        if not history_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: history_id')

        logger.info(f"Getting skill history record: {history_id}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Get history record
        result = history_service.get_history_by_id(history_id)

        if result.get('success'):
            return create_success_response(request, {
                'history': result.get('data')
            })
        else:
            return create_error_response(request, 'GET_HISTORY_ERROR', result.get('error', 'Unknown error'))

    except Exception as e:
        logger.error(f"Error in get skill history handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_SKILL_HISTORY_ERROR',
            f"Error getting skill history: {str(e)}"
        )


@IPCHandlerRegistry.handler('restore_skill_from_history')
def handle_restore_skill_from_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Restore skill from history.

    This will:
    1. Get the skill data from the history record
    2. Update the skill with the historical data

    No backup or new history record is written during restore, keeping the
    history list unchanged and avoiding duplicate version entries.

    Args:
        request: IPC request object
        params: Request parameters containing 'history_id'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Restore skill from history handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        history_id = params.get('history_id')
        if not history_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: history_id')

        logger.info(f"Restoring skill from history record: {history_id}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Get skill service
        skill_service = _get_skill_service(request, params)
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Skill service not available')

        # Step 1: Get the history record
        history_result = history_service.get_history_by_id(history_id)
        if not history_result.get('success'):
            return create_error_response(request, 'HISTORY_NOT_FOUND', history_result.get('error', 'History not found'))

        history_record = history_result.get('data', {})
        skill_data = history_record.get('skill_data', {})
        skill_id = history_record.get('skill_id')

        if not skill_data:
            return create_error_response(request, 'INVALID_HISTORY', 'History record has no skill data')

        # Step 2: Update the skill in the database
        update_fields = {
            'name': skill_data.get('name', ''),
            'description': skill_data.get('description', ''),
            'version': skill_data.get('version', '1.0.0'),
            'path': skill_data.get('path', ''),
            'level': skill_data.get('level', 'entry'),
            'config': skill_data.get('config', {}),
            'diagram': skill_data.get('diagram', {}),
            'tags': skill_data.get('tags', []),
        }

        update_result = skill_service.update_skill(skill_id, update_fields)

        if not update_result.get('success'):
            return create_error_response(request, 'UPDATE_SKILL_ERROR',
                f"Failed to update skill: {update_result.get('error')}")

        logger.info(f"Skill restored successfully from history: {history_id}")

        return create_success_response(request, {
            'success': True,
            'skill_id': skill_id,
            'restored_from': {
                'history_id': history_id,
                'version': history_record.get('version'),
                'version_number': history_record.get('version_number'),
                'created_at': history_record.get('created_at'),
                'skill_name': history_record.get('skill_name')
            },
            'skill_data': skill_data
        })

    except Exception as e:
        logger.error(f"Error in restore skill from history handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'RESTORE_SKILL_FROM_HISTORY_ERROR',
            f"Error restoring skill from history: {str(e)}"
        )


@IPCHandlerRegistry.handler('delete_skill_history')
def handle_delete_skill_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete a specific history record.

    Args:
        request: IPC request object
        params: Request parameters containing 'history_id'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Delete skill history handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        history_id = params.get('history_id')
        if not history_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: history_id')

        logger.info(f"Deleting skill history record: {history_id}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Delete history record
        result = history_service.delete_history(history_id)

        if result.get('success'):
            return create_success_response(request, {
                'success': True,
                'deleted_id': history_id
            })
        else:
            return create_error_response(request, 'DELETE_HISTORY_ERROR', result.get('error', 'Unknown error'))

    except Exception as e:
        logger.error(f"Error in delete skill history handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'DELETE_SKILL_HISTORY_ERROR',
            f"Error deleting skill history: {str(e)}"
        )


@IPCHandlerRegistry.handler('delete_all_skill_history')
def handle_delete_all_skill_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete all history records for a skill.

    Args:
        request: IPC request object
        params: Request parameters containing 'skill_id'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Delete all skill history handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        skill_id = params.get('skill_id')
        if not skill_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_id')

        logger.info(f"Deleting all skill history for skill_id: {skill_id}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Delete all history
        result = history_service.delete_all_history(skill_id)

        if result.get('success'):
            return create_success_response(request, {
                'success': True,
                'skill_id': skill_id,
                'deleted_count': result.get('deleted_count', 0)
            })
        else:
            return create_error_response(request, 'DELETE_HISTORY_ERROR', result.get('error', 'Unknown error'))

    except Exception as e:
        logger.error(f"Error in delete all skill history handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'DELETE_ALL_SKILL_HISTORY_ERROR',
            f"Error deleting all skill history: {str(e)}"
        )


@IPCHandlerRegistry.handler('compare_skill_versions')
def handle_compare_skill_versions(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Compare two history versions.

    Args:
        request: IPC request object
        params: Request parameters containing 'history_id1' and 'history_id2'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Compare skill versions handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        history_id1 = params.get('history_id1')
        history_id2 = params.get('history_id2')

        if not history_id1 or not history_id2:
            return create_error_response(request, 'INVALID_PARAMS',
                'Missing required parameters: history_id1 and history_id2')

        logger.info(f"Comparing skill versions: {history_id1} vs {history_id2}")

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        # Compare versions
        result = history_service.compare_versions(history_id1, history_id2)

        if result.get('success'):
            return create_success_response(request, result.get('data'))
        else:
            return create_error_response(request, 'COMPARE_ERROR', result.get('error', 'Unknown error'))

    except Exception as e:
        logger.error(f"Error in compare skill versions handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'COMPARE_SKILL_VERSIONS_ERROR',
            f"Error comparing skill versions: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_skill_history_count')
def handle_get_skill_history_count(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get the number of history records for a skill.

    Args:
        request: IPC request object
        params: Request parameters containing 'skill_id'

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get skill history count handler called")

        # Validate parameters
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing parameters')

        skill_id = params.get('skill_id')
        if not skill_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_id')

        # Get history service
        history_service = _get_history_service(request, params)
        if not history_service:
            return create_error_response(request, 'SERVICE_ERROR', 'History service not available')

        count = history_service.get_history_count(skill_id)

        return create_success_response(request, {
            'skill_id': skill_id,
            'count': count,
            'max_history': MAX_HISTORY_PER_SKILL,
            'has_more': count >= MAX_HISTORY_PER_SKILL
        })

    except Exception as e:
        logger.error(f"Error in get skill history count handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_HISTORY_COUNT_ERROR',
            f"Error getting skill history count: {str(e)}"
        )
