import traceback
import asyncio
import requests
from typing import TYPE_CHECKING, Any, Optional, Dict, Tuple
from uuid import uuid4
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from gui.ipc.handlers import validate_params, resolve_username
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.constants import Operation
import json
from pathlib import Path

# Track locally-deleted skill IDs to prevent cloud re-sync from re-adding them
_DELETED_SKILL_IDS: set = set()

# Guarded import of skill file sync (S3 upload/download)
_SKILL_FILE_SYNC_AVAILABLE = False
try:
    from gui.ipc.w2p_handlers.skill_file_sync import (
        upload_skill_files_to_cloud,
        download_skill_files_from_cloud,
        delete_skill_files_from_cloud,
        sync_all_skill_files_to_cloud,
    )
    _SKILL_FILE_SYNC_AVAILABLE = True
except ImportError as _imp_err:
    logger.debug(f"[skill_handler] skill_file_sync not available: {_imp_err}")

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
    """Get agent skills list from local memory/DB AND cloud.

    1. Reads local skills from memory (loaded from SQLite at startup).
    2. Fetches cloud skills via AppSync queryAgentSkills.
    3. Merges the two lists, deduplicating by skill ID (local wins on conflict).

    Args:
        request: IPC request object
        params: Request parameters, can contain 'username', 'owner', or 'userId' field

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get agent skills handler called with request: {request}")

        # Resolve username from params (supports username, owner, userId) or MainWindow context
        username = resolve_username(request, params)
        if not username:
            logger.warning(f"Invalid parameters for get agent skills: Missing username")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Missing required parameter: username (or owner/userId)'
            )

        logger.info(f"Getting agent skills for user: {username}")

        # ── Step 1: Get local skills from memory ──────────────────────
        skills_dicts = []
        try:
            ctx = get_handler_context(request, params)
            memory_skills = ctx.get_agent_skills() or []
            logger.info(f"Found {len(memory_skills)} skills in memory (mainwin.agent_skills)")

            for i, sk in enumerate(memory_skills):
                try:
                    sk_dict = sk.to_dict()
                    if not sk_dict.get('owner'):
                        sk_dict['owner'] = username
                    # Propagate extra publish metadata if attached to the in-memory skill
                    if 'extra_data' not in sk_dict and hasattr(sk, 'extra_data'):
                        try:
                            sk_dict['extra_data'] = getattr(sk, 'extra_data')
                        except Exception:
                            pass
                    if 'id' not in sk_dict:
                        sk_dict['id'] = f"skill_{i}"
                    
                    # Remove circular references from config to prevent frontend warnings
                    if 'config' in sk_dict and isinstance(sk_dict['config'], dict):
                        # Remove known circular reference fields
                        config_clean = {k: v for k, v in sk_dict['config'].items() 
                                       if k not in ['graph', 'mcp_client', 'store', 'checkpointer', 'runtime']}
                        sk_dict['config'] = config_clean

                    skills_dicts.append(sk_dict)
                    logger.debug(f"Converted skill: {sk_dict.get('name', 'NO NAME')} (id: {sk_dict.get('id', 'NO ID')})")
                except Exception as e:
                    logger.error(f"Failed to convert skill {i}: {e}")

        except Exception as e:
            logger.error(f"Failed to get agent skills from memory: {e}")

        # ── Step 2: Fetch cloud skills via AppSync ────────────────────
        cloud_skills_dicts = []
        try:
            cloud_skills_dicts = _fetch_cloud_skills(request, params)
            logger.info(f"Fetched {len(cloud_skills_dicts)} skills from cloud")
        except Exception as e:
            logger.warning(f"Cloud skill fetch failed (non-fatal): {e}")

        # ── Step 3: Merge local + cloud, local wins on conflict ─────────
        # Build lookup sets for dedup: by id, askid, and normalized name
        # Optimization: Use set comprehension for batch processing (faster than loop)
        local_ids = {str(sk['id']) for sk in skills_dicts if sk.get('id')}
        local_askids = {str(sk['askid']) for sk in skills_dicts if sk.get('askid')}
        local_names_norm = {sk['name'].strip().lower() for sk in skills_dicts if sk.get('name')}
        
        # Combine all local identifiers for efficient lookup
        all_local_identifiers = local_ids | local_askids

        cloud_added = 0
        for cloud_sk in cloud_skills_dicts:
            cid = str(cloud_sk['id']) if cloud_sk.get('id') else None
            c_askid = str(cloud_sk['askid']) if cloud_sk.get('askid') else None
            cname = cloud_sk.get('name', '').strip().lower() if cloud_sk.get('name') else None
            cowner = str(cloud_sk.get('owner') or '').strip().lower()
            current_user = str(username or '').strip().lower()

            # Standard list semantics:
            # - local memory/DB already contains my local skills and subscribed skills
            # - cloud merge should only backfill skills owned by the current user
            if current_user and cowner and cowner != current_user:
                continue
            
            # Optimization: Reduced from 6 checks to 3 by combining ID lookups
            # Skip if already present locally (by any identifier)
            if (cid and cid in all_local_identifiers) or (c_askid and c_askid in all_local_identifiers):
                continue
            if cname and cname in local_names_norm:
                continue
            
            if (cid and cid in _DELETED_SKILL_IDS) or (c_askid and c_askid in _DELETED_SKILL_IDS):
                logger.info(
                    f"[skill_handler] Skipping cloud skill rehydrate for deleted skill: "
                    f"id={cid}, askid={c_askid}, name={cloud_sk.get('name')}"
                )
                continue
            
            cloud_sk['_source'] = 'cloud'
            skills_dicts.append(cloud_sk)
            cloud_added += 1
            if cid:
                all_local_identifiers.add(cid)
            if c_askid:
                all_local_identifiers.add(c_askid)
            if cname:
                local_names_norm.add(cname)

        logger.info(f"Returning {len(skills_dicts)} skills to frontend "
                     f"(local={len(skills_dicts) - cloud_added}, cloud={cloud_added})")

        # Kick off background bulk upload of local skill files to S3
        if _SKILL_FILE_SYNC_AVAILABLE:
            try:
                local_skills = [sk for sk in skills_dicts if sk.get('_source') != 'cloud']
                sync_all_skill_files_to_cloud(local_skills)
            except Exception as fs_exc:
                logger.debug(f"[skill_handler] bulk skill file sync skipped: {fs_exc}")

            # For cloud-only skills that lack local files, download from S3
            try:
                download_batch_id = uuid4().hex[:8]
                download_triggered = 0
                skip_owner_mismatch = 0
                skip_local_exists = 0
                for sk in skills_dicts:
                    if sk.get('_source') == 'cloud':
                        # Skip external skills (those not in my_skills directory)
                        if sk.get('source') == 'external':
                            skip_owner_mismatch += 1
                            logger.debug(
                                f"[skill_handler][batch={download_batch_id}] Skip cloud file auto-download for skill '{sk.get('name', sk.get('id', '?'))}': "
                                f"external skill (not in my_skills)"
                            )
                            continue
                        
                        # Only auto-download files for current user's own cloud skills.
                        # Public/third-party skills may not have downloadable archives for this user.
                        if (sk.get('owner') or '').strip().lower() != (username or '').strip().lower():
                            skip_owner_mismatch += 1
                            logger.debug(
                                f"[skill_handler][batch={download_batch_id}] Skip cloud file auto-download for skill '{sk.get('name', sk.get('id', '?'))}': "
                                f"owner mismatch (skill_owner={sk.get('owner')}, current_user={username})"
                            )
                            continue
                        from gui.ipc.w2p_handlers.skill_file_sync import _resolve_skill_dir
                        local_dir = _resolve_skill_dir(sk)
                        if local_dir is None or not local_dir.is_dir():
                            download_triggered += 1
                            logger.info(
                                f"[skill_handler][batch={download_batch_id}] Trigger cloud file download for skill '{sk.get('name', sk.get('id', '?'))}' "
                                f"(owner={sk.get('owner')})"
                            )
                            download_skill_files_from_cloud(sk, trace_id=download_batch_id)
                        else:
                            skip_local_exists += 1
                            logger.debug(
                                f"[skill_handler][batch={download_batch_id}] Skip cloud file auto-download for skill '{sk.get('name', sk.get('id', '?'))}': "
                                f"local dir exists at '{local_dir}'"
                            )
                logger.info(
                    f"[skill_handler][batch={download_batch_id}] Cloud skill file auto-download decisions: "
                    f"triggered={download_triggered}, "
                    f"skip_owner_mismatch={skip_owner_mismatch}, "
                    f"skip_local_exists={skip_local_exists}"
                )
            except Exception as fs_exc:
                logger.warning(f"[skill_handler] cloud skill file download flow error: {fs_exc}")

        resultJS = {
            'skills': skills_dicts,
            'message': 'Get skills successful',
        }
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get agent skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_AGENT_SKILLS_ERROR',
            f"Error during get agent skills: {str(e)}"
        )


def _fetch_cloud_skills(request=None, params=None) -> list:
    """Fetch skills from cloud AppSync API.

    Returns a list of skill dicts in the local format.
    Raises on failure so the caller can log and continue.
    """
    from agent.cloud_api.cloud_api import (
        send_get_agent_skills_request_to_cloud,
        get_appsync_endpoint,
    )

    # Get auth token
    ctx = get_handler_context(request, params)
    token = ctx.get_auth_token()
    if not token:
        logger.debug("[_fetch_cloud_skills] No auth token — skipping cloud fetch")
        return []

    endpoint = get_appsync_endpoint()
    session = requests.Session()
    jresp = send_get_agent_skills_request_to_cloud(session, token, endpoint)

    if not isinstance(jresp, list):
        # Dict response indicates an error from the cloud API
        if isinstance(jresp, dict):
            error_msg = jresp.get('message', 'Unknown error')
            logger.warning(f"[_fetch_cloud_skills] Cloud API error: {error_msg}")
        else:
            # Truly unexpected type (not list or dict)
            logger.warning(f"[_fetch_cloud_skills] Unexpected response type: {type(jresp)}")
        return []

    # Convert cloud format to local dict format using schema registry,
    # then patch back any fields that from_cloud accidentally drops
    # (from_cloud skips fields listed in cloud_required_fields during auto-mapping).
    result = []
    try:
        from agent.cloud_api.constants import DataType
        from agent.cloud_api.schema_registry import get_schema_registry
        schema = get_schema_registry().get_schema(DataType.SKILL)
        for cloud_sk in jresp:
            try:
                local_sk = schema.from_cloud(cloud_sk)
                # Patch: from_cloud skips fields in required_fields during auto-mapping,
                # so re-copy them from the original cloud data if missing.
                for key in ('name', 'id', 'askid', 'owner', 'description', 'version',
                            'level', 'path', 'source', 'status', 'price', 'price_model',
                            'public', 'rentable'):
                    if key not in local_sk and key in cloud_sk:
                        local_sk[key] = cloud_sk[key]
                result.append(local_sk)
            except Exception as e:
                logger.debug(f"[_fetch_cloud_skills] Schema conversion failed for skill: {e}")
                result.append(cloud_sk)
    except Exception as e:
        logger.warning(f"[_fetch_cloud_skills] Schema conversion unavailable ({e}), using raw cloud data")
        result = jresp

    # Normalize: ensure frontend-required fields are present
    for sk in result:
        # Ensure 'id' is set (prefer existing 'id', fall back to 'askid')
        if not sk.get('id') and sk.get('askid'):
            sk['id'] = str(sk['askid'])
        # Ensure 'name' is present
        if not sk.get('name'):
            sk['name'] = sk.get('description', '') or f"Cloud Skill {sk.get('id', '?')}"
        # Ensure 'version' has a default
        if not sk.get('version'):
            sk['version'] = '1.0'
        logger.debug(f"[_fetch_cloud_skills] Normalized skill: id={sk.get('id')}, name={sk.get('name')}, "
                      f"owner={sk.get('owner')}, keys={list(sk.keys())}")

    if result:
        sample = result[0]
        logger.info(f"[_fetch_cloud_skills] Sample cloud skill keys: {list(sample.keys())}, "
                    f"id={sample.get('id')}, askid={sample.get('askid')}, "
                    f"name={sample.get('name')}, owner={sample.get('owner')}")

    return result



@IPCHandlerRegistry.handler('get_subscribed_skill_ids')
def handle_get_subscribed_skill_ids(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get list of subscribed skill IDs for a user

    Args:
        request: IPC request object
        params: Request parameters containing 'owner' or 'username'

    Returns:
        List of skill IDs that the user has subscribed to
    """
    try:
        # Resolve username from params
        username = resolve_username(request, params)
        if not username:
            logger.warning(f"Invalid parameters for get subscribed skill IDs: Missing username")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Missing required parameter: username (or owner/userId)'
            )

        logger.info(f"Getting subscribed skill IDs for user: {username}")

        # Get context to access database
        ctx = get_handler_context(request, params)
        if not ctx:
            logger.warning("[skill_handler] No context available for get_subscribed_skill_ids")
            return create_success_response(request, [])

        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            logger.warning("[skill_handler] No database manager available")
            return create_success_response(request, [])

        # Get skill service
        skill_service = ec_db_mgr.skill_service
        if not skill_service:
            logger.warning("[skill_handler] No skill service available")
            return create_success_response(request, [])

        # Get all skills for the user
        skills_result = skill_service.get_skills_by_owner(username)
        if not skills_result.get('success'):
            logger.warning(f"[skill_handler] Failed to get skills: {skills_result.get('error')}")
            return create_success_response(request, [])

        skills = skills_result.get('data', [])

        # Extract skill IDs from subscribed skills
        # For now, return all skill IDs as we don't have a separate subscription mechanism
        # In the future, this could filter based on a subscription status field
        skill_ids = [skill.get('id') for skill in skills if skill.get('id')]

        logger.info(f"[skill_handler] Found {len(skill_ids)} subscribed skill IDs for user {username}")
        return create_success_response(request, skill_ids)

    except Exception as e:
        logger.error(f"[skill_handler] Error getting subscribed skill IDs: {e}")
        traceback.print_exc()
        return create_error_response(
            request,
            'GET_SUBSCRIBED_SKILL_IDS_ERROR',
            f"Error getting subscribed skill IDs: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_public_skills')
def handle_get_public_skills(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        # Resolve username from params (supports username, owner, userId)
        username = resolve_username(request, params)
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: username (or owner/userId)')

        rows = _fetch_cloud_skills(request, params)
        username_norm = username.strip().lower()
        skills = []
        seen = set()

        for sk in rows:
            if not isinstance(sk, dict):
                continue

            owner = str(sk.get('owner') or '').strip().lower()
            is_public = bool(sk.get('public', False))
            if not is_public:
                continue
            if owner and owner == username_norm:
                continue

            key = str(sk.get('id') or sk.get('askid') or '').strip() or f"{owner}::{str(sk.get('name') or '').strip().lower()}"
            if key in seen:
                continue
            seen.add(key)
            skills.append(sk)

        return create_success_response(request, {
            'skills': skills,
            'message': 'Get public skills successful',
        })
    except Exception as e:
        logger.error(f"Error in get_public_skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_PUBLIC_SKILLS_ERROR',
            f"Error during get public skills: {str(e)}"
        )
    
@IPCHandlerRegistry.handler('subscribe_to_skill')
def handle_subscribe_to_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Subscribe to a public skill by saving it to the local database.

    Args:
        request: IPC request object
        params: Must include 'skillId' and 'owner' (current user)
    """
    try:
        username = resolve_username(request, params)
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: username')

        is_valid, data, error = validate_params(params, ['skillId'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        skill_id = data['skillId']

        skill_service = _get_skill_service(request, params)
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Check if already subscribed (skill already in local DB)
        existing = skill_service.get_skill_by_id(skill_id)
        if existing.get('success') and existing.get('data'):
            logger.info(f"[skill_handler] Skill {skill_id} already in local DB, subscription idempotent")
            return create_success_response(request, {'id': skill_id, 'success': True})

        # Fetch skill details from cloud to save locally
        cloud_skills = _fetch_cloud_skills(request, params)
        target = next((s for s in cloud_skills if str(s.get('id')) == str(skill_id)), None)

        if not target:
            return create_error_response(request, 'SKILL_NOT_FOUND', f'Skill {skill_id} not found in cloud')

        # Save the cloud skill to local DB so it appears in the user's skill list
        skill_data = _prepare_skill_data(target, target.get('owner', username), skill_id)
        result = skill_service.add_skill(skill_data)

        if result.get('success'):
            # Update in-memory skills list
            _update_skill_in_memory(skill_id, skill_data, request, params)
            try:
                ctx = get_handler_context(request, params)
                current = next((s for s in (ctx.get_agent_skills() or []) if str(getattr(s, 'id', '')) == str(skill_id)), None) if ctx else None
                _sync_runtime_tasks_for_skill(current, request, params)
            except Exception:
                pass
            logger.info(f"[skill_handler] Subscribed to skill {skill_id} (saved to local DB)")
            return create_success_response(request, {'id': skill_id, 'success': True})
        else:
            logger.error(f"[skill_handler] Failed to subscribe to skill {skill_id}: {result.get('error')}")
            return create_error_response(request, 'SUBSCRIBE_SKILL_ERROR', str(result.get('error')))

    except Exception as e:
        logger.error(f"Error in subscribe_to_skill handler: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SUBSCRIBE_SKILL_ERROR', f"Error during subscribe: {str(e)}")


@IPCHandlerRegistry.handler('unsubscribe_from_skill')
def handle_unsubscribe_from_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Unsubscribe from a skill by removing it from the local database.

    Args:
        request: IPC request object
        params: Must include 'skillId' and 'owner' (current user)
    """
    try:
        username = resolve_username(request, params)
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: username')

        is_valid, data, error = validate_params(params, ['skillId'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        skill_id = data['skillId']

        skill_service = _get_skill_service(request, params)
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Only allow unsubscribing skills not owned by current user
        existing = skill_service.get_skill_by_id(skill_id)
        if existing.get('success') and existing.get('data'):
            skill_owner = existing['data'].get('owner', '')
            if skill_owner and skill_owner.lower() == username.lower():
                return create_error_response(
                    request, 'UNSUBSCRIBE_OWN_SKILL',
                    'Cannot unsubscribe from your own skill. Use delete instead.'
                )

        result = skill_service.delete_skill(skill_id)
        if result.get('success'):
            # Remove from in-memory skills list
            try:
                ctx = get_handler_context(request, params)
                if ctx:
                    agent_skills = ctx.get_agent_skills() or []
                    updated = [s for s in agent_skills if not (hasattr(s, 'id') and s.id == skill_id)]
                    agent_skills[:] = updated
            except Exception as mem_e:
                logger.debug(f"[skill_handler] Failed to remove skill from memory: {mem_e}")

            logger.info(f"[skill_handler] Unsubscribed from skill {skill_id}")
            return create_success_response(request, {'id': skill_id, 'success': True})
        else:
            logger.error(f"[skill_handler] Failed to unsubscribe from skill {skill_id}: {result.get('error')}")
            return create_error_response(request, 'UNSUBSCRIBE_SKILL_ERROR', str(result.get('error')))

    except Exception as e:
        logger.error(f"Error in unsubscribe_from_skill handler: {e} {traceback.format_exc()}")
        return create_error_response(request, 'UNSUBSCRIBE_SKILL_ERROR', f"Error during unsubscribe: {str(e)}")


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

        # Resolve username from params (supports username, owner, userId)
        username = resolve_username(request, params)
        if not username:
            logger.warning(f"Invalid parameters for save agent skill: Missing username")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: username (or owner/userId)')

        # Validate skill_info parameter
        if not params or not params.get('skill_info'):
            logger.warning(f"Invalid parameters for save agent skill: Missing skill_info")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_info')

        skill_info = params['skill_info']
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

        # ── Publish gate: non-free skills must use cloud/hybrid execution ──
        # If price > 0 and the skill is not already marked for cloud execution,
        # forcefully enable hybrid_cloud_mode to protect prompt IP.
        _price = 0
        try:
            _price = int(skill_info.get('price', 0) or 0)
        except (TypeError, ValueError):
            pass
        _config = skill_info.get('config') or {}
        _ric = bool(skill_info.get('run_in_cloud', _config.get('run_in_cloud', False)))
        _hcm = bool(skill_info.get('hybrid_cloud_mode', _config.get('hybrid_cloud_mode', False)))
        if _price > 0 and not _ric and not _hcm:
            logger.warning(
                f"[skill_handler] Non-free skill '{skill_info.get('name')}' (price={_price}) "
                "saved as local — forcing hybrid_cloud_mode=true to protect prompt IP"
            )
            skill_info['hybrid_cloud_mode'] = True
            skill_info['run_in_cloud'] = True
            if isinstance(_config, dict):
                _config['hybrid_cloud_mode'] = True
                _config['run_in_cloud'] = True
                skill_info['config'] = _config

        logger.info(f"Saving agent skill for user: {username}, skill_id: {skill_id}")

        # Get database service
        skill_service = _get_skill_service(request, params)
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Check if skill exists
        existing_skill = skill_service.get_skill_by_id(skill_id)

        if existing_skill.get('success') and existing_skill.get('data'):
            # Update existing skill — merge incoming fields onto existing DB record
            # so partial updates (e.g. toggling public/rentable) don't wipe other fields
            existing_data = existing_skill['data']
            skill_data = _prepare_skill_data(existing_data, username, skill_id)
            # Overlay only the fields the caller actually sent
            for key in skill_info:
                if key in skill_data:
                    skill_data[key] = skill_info[key]
            logger.info(f"Updating existing skill: {skill_id}")
            result = skill_service.update_skill(skill_id, skill_data)
        else:
            # Create new skill
            skill_data = _prepare_skill_data(skill_info, username, skill_id)
            logger.info(f"Creating new skill: {skill_id}")
            result = skill_service.add_skill(skill_data)

        if result.get('success'):
            # Get the actual skill_id from database response (in case it was generated)
            actual_skill_id = result.get('id', skill_id)
            logger.info(f"Skill saved successfully: {skill_data['name']} (ID: {actual_skill_id})")

            # Step 2: Update memory after database update succeeds
            _update_skill_in_memory(actual_skill_id, skill_data, request, params)
            try:
                ctx = get_handler_context(request, params)
                current = next((s for s in (ctx.get_agent_skills() or []) if str(getattr(s, 'id', '')) == str(actual_skill_id)), None) if ctx else None
                _sync_runtime_tasks_for_skill(current, request, params)
            except Exception:
                pass

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
            
            # Sync Skill-Tool relationships (use skill_info, not skill_data which doesn't have these keys).
            # Always use ADD — cloud resolver handles upsert. UPDATE requires the cloud-side
            # auto-generated relation row 'id' which the local client doesn't have.
            tool_ids = skill_info.get('tool_ids', skill_info.get('tools', []))
            if tool_ids:
                _sync_skill_tool_relations(actual_skill_id, tool_ids, Operation.ADD)
            
            # Sync Skill-Knowledge relationships
            knowledge_ids = skill_info.get('knowledge_ids', skill_info.get('knowledges', []))
            if knowledge_ids:
                _sync_skill_knowledge_relations(actual_skill_id, knowledge_ids, Operation.ADD)

            # Step 5: Sync skill source files to S3 (async, fire and forget)
            if _SKILL_FILE_SYNC_AVAILABLE:
                try:
                    upload_skill_files_to_cloud(skill_data_with_id)
                except Exception as fs_exc:
                    logger.debug(f"[skill_handler] skill file sync skipped: {fs_exc}")

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

        # Resolve username from params (supports username, owner, userId)
        username = resolve_username(request, params)
        if not username:
            logger.warning(f"Invalid parameters for create agent skill: Missing username")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: username (or owner/userId)')

        # Validate skill_info parameter
        if not params or not params.get('skill_info'):
            logger.warning(f"Invalid parameters for create agent skill: Missing skill_info")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_info')

        skill_info = params['skill_info']

        logger.info(f"Creating new agent skill for user: {username}")

        # Get database service
        skill_service = _get_skill_service(request, params)
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
            _update_skill_in_memory(skill_id, skill_data, request, params)
            try:
                ctx = get_handler_context(request, params)
                current = next((s for s in (ctx.get_agent_skills() or []) if str(getattr(s, 'id', '')) == str(skill_id)), None) if ctx else None
                _sync_runtime_tasks_for_skill(current, request, params)
            except Exception:
                pass

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

            # Step 4: Sync skill source files to S3 (async, fire and forget)
            if _SKILL_FILE_SYNC_AVAILABLE:
                try:
                    upload_skill_files_to_cloud(skill_data_with_id)
                except Exception as fs_exc:
                    logger.debug(f"[skill_handler] skill file sync skipped: {fs_exc}")

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

        # Resolve username from params (supports username, owner, userId)
        username = resolve_username(request, params)
        if not username:
            logger.warning(f"Invalid parameters for delete skill: Missing username")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: username (or owner/userId)')

        # Validate skill_id parameter
        if not params or not params.get('skill_id'):
            logger.warning(f"Invalid parameters for delete skill: Missing skill_id")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing required parameter: skill_id')

        requested_skill_id = str(params['skill_id']).strip()
        skill_id = requested_skill_id
        local_db_skill_id = requested_skill_id
        cloud_skill_id = requested_skill_id
        resolved_skill_record = None
        resolved_from_cloud = False

        # Get database service
        skill_service = _get_skill_service(request, params)
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Resolve requested identifier against local DB records.
        # Frontend may pass cloud id while local DB primary key is stored separately.
        try:
            owned_skills_result = skill_service.get_skills_by_owner(username)
            owned_skills = owned_skills_result.get('data') if owned_skills_result.get('success') else []
            for sk in (owned_skills or []):
                db_id = str(sk.get('id') or '').strip()
                askid = str(sk.get('askid') or '').strip()
                if requested_skill_id and requested_skill_id in {db_id, askid}:
                    resolved_skill_record = sk
                    local_db_skill_id = db_id or requested_skill_id
                    cloud_skill_id = askid or requested_skill_id
                    skill_id = cloud_skill_id or local_db_skill_id
                    break
        except Exception as resolve_e:
            logger.warning(f"[skill_handler] Failed to resolve requested skill identifier: {resolve_e}")

        if not resolved_skill_record:
            try:
                cloud_skills = _fetch_cloud_skills(request, params)
                username_norm = str(username or '').strip().lower()
                for sk in (cloud_skills or []):
                    cloud_id = str(sk.get('id') or '').strip()
                    cloud_askid = str(sk.get('askid') or '').strip()
                    cloud_owner = str(sk.get('owner') or '').strip().lower()
                    if username_norm and cloud_owner and cloud_owner != username_norm:
                        continue
                    if requested_skill_id and requested_skill_id in {cloud_id, cloud_askid}:
                        resolved_skill_record = sk
                        resolved_from_cloud = True
                        cloud_skill_id = cloud_id or cloud_askid or requested_skill_id
                        skill_id = cloud_skill_id
                        break
            except Exception as cloud_resolve_e:
                logger.warning(f"[skill_handler] Failed to resolve requested skill from cloud: {cloud_resolve_e}")

        # Track deletion identifiers to prevent cloud re-sync from re-adding it
        for delete_id in {requested_skill_id, local_db_skill_id, cloud_skill_id}:
            if delete_id:
                _DELETED_SKILL_IDS.add(str(delete_id))

        logger.info(
            f"[skill_handler] delete_agent_skill request received: "
            f"username={username}, requested_skill_id={requested_skill_id}, "
            f"local_db_skill_id={local_db_skill_id}, cloud_skill_id={cloud_skill_id}, "
            f"resolved_from_cloud={resolved_from_cloud}, params={params}"
        )
        logger.info(
            f"Deleting agent skill for user: {username}, requested_skill_id: {requested_skill_id}, "
            f"local_db_skill_id: {local_db_skill_id}, cloud_skill_id: {cloud_skill_id}, "
            f"resolved_from_cloud: {resolved_from_cloud}"
        )

        # Check if this is a read-only skill (cannot be deleted from UI)
        # Also collect askid for deletion tracking
        try:
            ctx = get_handler_context(request, params)
            if ctx:
                for skill in (ctx.get_agent_skills() or []):
                    sid = str(getattr(skill, 'id', '') or '').strip()
                    askid = str(getattr(skill, 'askid', '') or '').strip()
                    if requested_skill_id in {sid, askid} or local_db_skill_id in {sid, askid} or cloud_skill_id in {sid, askid}:
                        source = getattr(skill, 'source', 'ui')
                        if source == 'code':
                            for delete_id in {requested_skill_id, local_db_skill_id, cloud_skill_id}:
                                if delete_id:
                                    _DELETED_SKILL_IDS.discard(delete_id)
                            logger.warning(f"Attempted to delete code-based skill: {skill_id} (source={source})")
                            return create_error_response(
                                request,
                                'SKILL_READ_ONLY',
                                'Code-based skills cannot be deleted. Please remove the source files directly.'
                            )
                        # Also track askid so cloud dedup catches it
                        askid_value = getattr(skill, 'askid', None)
                        if askid_value:
                            _DELETED_SKILL_IDS.add(str(askid_value))
                        break
        except Exception as e:
            logger.warning(f"[skill_handler] Failed to check skill source: {e}")

        # Only allow deleting skills owned by the current user.
        # Subscribed public skills must use unsubscribe_from_skill instead.
        try:
            existing = skill_service.get_skill_by_id(local_db_skill_id)
            if (not existing.get('success') or not existing.get('data')) and resolved_skill_record:
                existing = {'success': True, 'data': resolved_skill_record}
            if existing.get('success') and existing.get('data'):
                skill_owner = str(existing['data'].get('owner', '') or '').strip()
                if skill_owner and skill_owner.lower() != username.lower():
                    for delete_id in {requested_skill_id, local_db_skill_id, cloud_skill_id}:
                        if delete_id:
                            _DELETED_SKILL_IDS.discard(delete_id)
                    return create_error_response(
                        request,
                        'DELETE_SUBSCRIBED_SKILL_NOT_ALLOWED',
                        'Subscribed public skills cannot be deleted. Use unsubscribe instead.'
                    )
        except Exception as owner_check_e:
            logger.warning(f"[skill_handler] Failed to verify skill ownership before delete: {owner_check_e}")

        # Step 0: Get skill path from memory before deletion (for file cleanup)
        skill_path = None
        skill_name = None
        try:
            ctx = get_handler_context(request, params)
            if ctx:
                for skill in (ctx.get_agent_skills() or []):
                    sid = str(getattr(skill, 'id', '') or '').strip()
                    askid = str(getattr(skill, 'askid', '') or '').strip()
                    if requested_skill_id in {sid, askid} or local_db_skill_id in {sid, askid} or cloud_skill_id in {sid, askid}:
                        skill_path = getattr(skill, 'path', None)
                        skill_name = getattr(skill, 'name', None)
                        logger.info(f"[skill_handler] Found skill to delete: name={skill_name}, path={skill_path}")
                        break
        except Exception as e:
            logger.warning(f"[skill_handler] Failed to get skill path: {e}")

        if resolved_skill_record:
            skill_path = skill_path or resolved_skill_record.get('path')
            skill_name = skill_name or resolved_skill_record.get('name')

        # Step 1: Try to delete from database
        result = skill_service.delete_skill(local_db_skill_id)
        db_deleted = result.get('success', False)
        
        if db_deleted:
            logger.info(f"Skill deleted successfully from database: {local_db_skill_id}")
        else:
            # Database deletion failed (skill might not exist in DB), but continue to clean memory
            logger.warning(f"Database deletion returned: {result.get('error')} - will still try to clean memory")

        # Step 2: Remove from memory (always try, even if DB deletion failed)
        mem_deleted = False
        try:
            ctx = get_handler_context(request, params)
            agent_skills = ctx.get_agent_skills()
            if agent_skills is not None:
                original_count = len(agent_skills)
                agent_skills[:] = [
                    skill for skill in agent_skills
                    if str(getattr(skill, 'id', '') or '').strip() not in {requested_skill_id, local_db_skill_id, cloud_skill_id}
                    and str(getattr(skill, 'askid', '') or '').strip() not in {requested_skill_id, local_db_skill_id, cloud_skill_id}
                ]
                new_count = len(agent_skills)
                if new_count < original_count:
                    mem_deleted = True
                    logger.info(f"[skill_handler] Removed skill from memory: {skill_id} (count: {original_count} → {new_count})")
                else:
                    logger.info(f"[skill_handler] Skill not found in memory: {skill_id}")
        except Exception as e:
            logger.warning(f"[skill_handler] Failed to remove skill from memory: {e}")

        # Step 2.5: Delete skill files from disk
        file_deleted = False
        if skill_path:
            try:
                from pathlib import Path
                import shutil
                
                skill_file = Path(skill_path)
                if skill_file.exists():
                    # Path format: .../xxx_skill/diagram_dir/xxx_skill.json
                    # We need to delete the xxx_skill directory
                    diagram_dir = skill_file.parent  # diagram_dir/
                    skill_root = diagram_dir.parent  # xxx_skill/
                    
                    if skill_root.exists() and skill_root.is_dir():
                        # Safety check: only delete if it looks like a skill directory
                        if skill_root.name.endswith('_skill') or (diagram_dir.exists() and diagram_dir.name == 'diagram_dir'):
                            shutil.rmtree(str(skill_root))
                            file_deleted = True
                            logger.info(f"[skill_handler] ✅ Deleted skill directory: {skill_root}")
                        else:
                            logger.warning(f"[skill_handler] ⚠️ Skipped deletion - not a skill directory: {skill_root}")
                else:
                    logger.info(f"[skill_handler] Skill file not found on disk: {skill_path}")
            except Exception as e:
                logger.warning(f"[skill_handler] Failed to delete skill files: {e}")

        # Step 3: Clean up offline sync queue for this skill
        try:
            from agent.cloud_api.offline_sync_queue import get_offline_sync_queue
            sync_queue = get_offline_sync_queue()
            removed_count = sync_queue.remove_tasks_by_resource('skill', skill_id)
            if removed_count > 0:
                logger.info(f"[skill_handler] Removed {removed_count} pending sync tasks for skill: {skill_id}")
        except Exception as e:
            logger.warning(f"[skill_handler] Failed to clean offline sync queue: {e}")

        cloud_deleted = False
        cloud_cached = False
        cloud_error = None
        cloud_task_id = None
        should_attempt_cloud_delete = bool(
            db_deleted or (
                resolved_skill_record
                and str((resolved_skill_record.get('owner') or '')).strip().lower() == str(username).strip().lower()
                and cloud_skill_id
            )
        )
        if should_attempt_cloud_delete:
            try:
                cloud_delete_data = {
                    'id': cloud_skill_id,
                    'owner': username,
                }
                if skill_path:
                    cloud_delete_data['path'] = skill_path
                cloud_result = _sync_skill_delete_to_cloud(cloud_delete_data)
                cloud_deleted = bool(cloud_result.get('synced'))
                cloud_cached = bool(cloud_result.get('cached'))
                cloud_error = cloud_result.get('error')
                cloud_task_id = cloud_result.get('task_id')
                logger.info(
                    f"[skill_handler] Cloud delete status for {cloud_skill_id}: "
                    f"deleted={cloud_deleted}, cached={cloud_cached}, "
                    f"task_id={cloud_task_id or ''}, error={cloud_error or ''}"
                )
            except Exception as e:
                cloud_error = str(e)
                logger.warning(f"[skill_handler] Failed to sync cloud deletion for {cloud_skill_id}: {e}")

        # Return success if any deletion succeeded (local DB, memory, file, or cloud)
        if db_deleted or mem_deleted or file_deleted or cloud_deleted or cloud_cached:
            response_payload = {
                'message': 'Delete agent skill successful',
                'skill_id': cloud_skill_id or requested_skill_id,
                'db_deleted': db_deleted,
                'mem_deleted': mem_deleted,
                'file_deleted': file_deleted,
                'cloud_deleted': cloud_deleted,
                'cloud_cached': cloud_cached,
                'cloud_error': cloud_error,
                'cloud_task_id': cloud_task_id,
            }
            logger.info(
                f"[skill_handler] delete_agent_skill result: "
                f"requested_skill_id={requested_skill_id}, local_db_skill_id={local_db_skill_id}, "
                f"cloud_skill_id={cloud_skill_id}, resolved_from_cloud={resolved_from_cloud}, "
                f"db_deleted={db_deleted}, mem_deleted={mem_deleted}, "
                f"file_deleted={file_deleted}, cloud_deleted={cloud_deleted}, "
                f"cloud_cached={cloud_cached}, cloud_task_id={cloud_task_id or ''}, "
                f"cloud_error={cloud_error or ''}"
            )
            return create_success_response(request, response_payload)
        else:
            # Neither DB nor memory nor file nor cloud had this skill
            logger.warning(f"Skill not found in database, memory, disk, or cloud: {skill_id}")
            response_payload = {
                'message': 'Skill not found (may have been already deleted)',
                'skill_id': cloud_skill_id or requested_skill_id,
                'db_deleted': False,
                'mem_deleted': False,
                'file_deleted': False,
                'cloud_deleted': False,
                'cloud_cached': False,
                'cloud_error': cloud_error,
                'cloud_task_id': cloud_task_id,
            }
            logger.info(
                f"[skill_handler] delete_agent_skill result: "
                f"requested_skill_id={requested_skill_id}, local_db_skill_id={local_db_skill_id}, "
                f"cloud_skill_id={cloud_skill_id}, resolved_from_cloud={resolved_from_cloud}, "
                f"db_deleted=False, mem_deleted=False, "
                f"file_deleted=False, cloud_deleted=False, cloud_cached=False, "
                f"cloud_task_id={cloud_task_id or ''}, cloud_error={cloud_error or ''}"
            )
            return create_success_response(request, response_payload)

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

def _get_skill_service(request=None, params=None):
    """Get skill service from mainwin (uses correct user-specific database path)

    Returns:
        skill_service: Database skill service instance, or None if not available
    """
    ctx = get_handler_context(request, params)
    if ctx:
        ec_db_mgr = ctx.get_ec_db_mgr()
        if ec_db_mgr:
            return ec_db_mgr.skill_service
    logger.error("[skill_handler] Database manager not available - cannot access database")
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
        'ext': skill_info.get('ext', skill_info.get('extra_data', None)),
        'source': skill_info.get('source', 'ui'),
    }
    
    # Store cloud execution settings in config dict (not separate columns)
    # Top-level fields in skill_info take priority, then fall back to values already in config
    config = skill_data.get('config', {}) or {}
    # Ensure config is a dict (handle case where it might be a string or other type)
    if not isinstance(config, dict):
        logger.warning(f"[skill_handler] config is not a dict (type: {type(config)}), resetting to empty dict")
        config = {}
    
    config['run_in_cloud'] = skill_info.get('run_in_cloud', config.get('run_in_cloud', False))
    config['hybrid_cloud_mode'] = skill_info.get('hybrid_cloud_mode', config.get('hybrid_cloud_mode', False))
    config['local_helper_skill_id'] = skill_info.get('local_helper_skill_id', config.get('local_helper_skill_id', None))
    config['local_helper_machine'] = skill_info.get('local_helper_machine', config.get('local_helper_machine', None))
    skill_data['config'] = config

    # Only add ID if provided (for updates)
    if skill_id:
        skill_data['id'] = skill_id

    return skill_data


def _update_skill_in_memory(skill_id: str, skill_data: Dict[str, Any], request=None, params=None) -> bool:
    """Update or add skill in mainwin.agent_skills memory

    Args:
        skill_id: Skill ID
        skill_data: Skill data dictionary
        request: IPC request object (optional)
        params: Request parameters (optional)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ctx = get_handler_context(request, params)
        if not ctx or not hasattr(ctx, 'get_agent_skills'):
            logger.warning("[skill_handler] mainwin.agent_skills not available")
            return False

        from agent.ec_skill import EC_Skill

        skill_name = skill_data.get('name', 'Unknown')
        skill_path = skill_data.get('path', '')
        logger.info(f"[skill_handler] _update_skill_in_memory called: id={skill_id}, name={skill_name}, path={skill_path}")

        # Check if skill already exists in memory
        existing_index = None
        for i, skill in enumerate(ctx.get_agent_skills() or []):
            if hasattr(skill, 'id') and skill.id == skill_id:
                existing_index = i
                break

        # Try to compile skill object from skill_data for runtime execution.
        # Note: skill_data is already the latest from DB (caller just saved it)
        skill_obj = None
        try:
            from agent.ec_skills.build_agent_skills import _convert_db_skill_to_object
            # Use skill_data directly instead of re-querying DB
            compiled_skill = _convert_db_skill_to_object(skill_data)
            if compiled_skill and getattr(compiled_skill, 'runnable', None):
                skill_obj = compiled_skill
                logger.debug(f"[skill_handler] ✅ Using compiled skill object with runnable workflow")
            elif compiled_skill:
                logger.warning(f"[skill_handler] ⚠️ Skill compiled but has no runnable workflow: {skill_name}")
        except Exception as compile_err:
            logger.warning(f"[skill_handler] Failed to compile skill: {compile_err}")
            import traceback
            logger.debug(f"[skill_handler] Compile traceback: {traceback.format_exc()}")

        # Fallback: create plain skill object if compilation failed
        # This object will NOT have runnable workflow, but at least preserves metadata
        if not skill_obj:
            logger.warning(f"[skill_handler] Creating plain EC_Skill object (no runnable workflow): {skill_name}")
            skill_obj = EC_Skill()
            skill_obj.id = skill_id
            skill_obj.name = skill_name
            skill_obj.owner = skill_data.get('owner', '')
            skill_obj.description = skill_data.get('description', '')
            skill_obj.version = skill_data.get('version', '1.0.0')
            skill_obj.path = skill_path
            skill_obj.config = skill_data.get('config', {})
            skill_obj.diagram = skill_data.get('diagram', {})
            skill_obj.level = skill_data.get('level', 'entry')
            skill_obj.source = skill_data.get('source', 'ui')
            skill_obj.tags = skill_data.get('tags', [])
            skill_obj.examples = skill_data.get('examples', [])
            skill_obj.inputModes = skill_data.get('inputModes', [])
            skill_obj.outputModes = skill_data.get('outputModes', [])
            skill_obj.apps = skill_data.get('apps', [])
            skill_obj.limitations = skill_data.get('limitations', [])
            skill_obj.price = int(skill_data.get('price', 0) or 0)
            skill_obj.price_model = str(skill_data.get('price_model', '') or '')
            skill_obj.public = bool(skill_data.get('public', False))
            skill_obj.rentable = bool(skill_data.get('rentable', False))
            config = skill_data.get('config', {}) or {}
            skill_obj.run_in_cloud = bool(config.get('run_in_cloud', False))
            skill_obj.hybrid_cloud_mode = bool(config.get('hybrid_cloud_mode', False))
            skill_obj.local_helper_skill_id = config.get('local_helper_skill_id', None)
            skill_obj.local_helper_machine = config.get('local_helper_machine', None)
            try:
                setattr(skill_obj, 'extra_data', skill_data.get('ext', None))
            except Exception:
                pass
        
        if existing_index is not None:
            # Update existing skill
            agent_skills = ctx.get_agent_skills()
            agent_skills[existing_index] = skill_obj
            logger.info(f"[skill_handler] ✅ Updated skill in memory: {skill_name} (index={existing_index})")
        else:
            # Add new skill
            agent_skills = ctx.get_agent_skills()
            if agent_skills is not None:
                agent_skills.append(skill_obj)
                logger.info(f"[skill_handler] ✅ Added new skill to memory: {skill_name} (total={len(agent_skills)})")

        return True

    except Exception as e:
        logger.warning(f"[skill_handler] ❌ Failed to update mainwin.agent_skills: {e}")
        import traceback
        logger.warning(f"[skill_handler] Traceback: {traceback.format_exc()}")
        return False


def _sync_runtime_tasks_for_skill(skill_obj: Any, request=None, params=None) -> int:
    """Rebind runtime task.skill references to updated skill object.

    This makes provider/model edits on a skill effective immediately for queued chats.
    """
    try:
        if not skill_obj:
            return 0

        skill_id = str(getattr(skill_obj, 'id', '') or '')
        skill_name = str(getattr(skill_obj, 'name', '') or '')

        ctx = get_handler_context(request, params)
        agents = ctx.get_agents() if ctx else []
        updated = 0

        for agent in agents or []:
            for t in (getattr(agent, 'tasks', None) or []):
                cur = getattr(t, 'skill', None)
                cur_id = str(getattr(cur, 'id', '') or '')
                cur_name = str(getattr(cur, 'name', '') or '')
                if (skill_id and cur_id == skill_id) or (skill_name and cur_name == skill_name):
                    t.skill = skill_obj
                    updated += 1

            runner = getattr(agent, 'runner', None)
            runner_tasks = getattr(runner, 'tasks', None) if runner else None
            if isinstance(runner_tasks, dict):
                for rt in runner_tasks.values():
                    cur = getattr(rt, 'skill', None)
                    cur_id = str(getattr(cur, 'id', '') or '')
                    cur_name = str(getattr(cur, 'name', '') or '')
                    if (skill_id and cur_id == skill_id) or (skill_name and cur_name == skill_name):
                        rt.skill = skill_obj
                        updated += 1

        if updated > 0:
            logger.info(f"[skill_handler] ✅ Runtime tasks rebound to updated skill: skill={skill_name}, updated_tasks={updated}")
        return updated
    except Exception as e:
        logger.warning(f"[skill_handler] Failed to sync runtime tasks for updated skill: {e}")
        return 0


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
        'price': int(skill_data.get('price', 0)),
        'price_model': str(skill_data.get('price_model', '') or ''),
        # Cloud execution settings
        'run_in_cloud': bool(skill_data.get('run_in_cloud', False)),
        'hybrid_cloud_mode': bool(skill_data.get('hybrid_cloud_mode', False)),
        'local_helper_skill_id': skill_data.get('local_helper_skill_id', None),
        'local_helper_machine': skill_data.get('local_helper_machine', None),
    }
    
    # Add optional fields if they exist and are simple types
    if 'path' in skill_data:
        clean_data['path'] = str(skill_data['path'])
    if 'status' in skill_data:
        clean_data['status'] = str(skill_data['status'])
    if 'ext' in skill_data:
        clean_data['extra_data'] = skill_data.get('ext', None)
    
    return clean_data


# ============================================================================
# Cloud Synchronization Functions
# ============================================================================


def is_code_skill(file_path: str) -> bool:
    file_path_obj = Path(file_path)
    return 'resource/my_skills' in str(file_path_obj) or 'resource\\my_skills' in str(file_path_obj)


def _trigger_cloud_sync(skill_data: Dict[str, Any], operation: 'Operation') -> None:
    """Trigger cloud synchronization (async, non-blocking)
    
    Async background execution, doesn't block UI operations, ensures eventual consistency.
    If UPDATE fails with NOT_FOUND, automatically retries with ADD.
    
    Args:
        skill_data: Skill data to sync
        operation: Operation type (Operation enum)
    """
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType, Operation as Op
    
    def _log_result(result: Dict[str, Any]):
        """Log sync result and retry UPDATE→ADD on NOT_FOUND"""
        # Check per-item errors in the cloud response (transport may succeed but item may fail)
        cloud_resp = result.get('response')
        if isinstance(cloud_resp, list):
            for item in cloud_resp:
                if isinstance(item, dict) and 'NOT_FOUND' in str(item.get('error', '')):
                    # Skill doesn't exist in cloud yet — retry with ADD
                    logger.info(f"[skill_handler] 🔄 Cloud returned NOT_FOUND for UPDATE, retrying with ADD: {skill_data.get('name')}")
                    manager = get_sync_manager()
                    manager.sync_to_cloud_async(DataType.SKILL, cloud_data, Op.ADD, callback=_log_result_final)
                    return
        
        error_msg = result.get('error')
        if not error_msg:
            errors = result.get('errors')
            if isinstance(errors, list) and errors:
                error_msg = '; '.join([str(e) for e in errors if e])
        if result.get('synced'):
            logger.info(f"[skill_handler] ✅ Skill synced to cloud: {operation} - {skill_data.get('name')}")
        elif result.get('cached'):
            logger.info(f"[skill_handler] 💾 Skill cached for later sync: {operation} - {skill_data.get('name')}")
        else:
            logger.error(f"[skill_handler] ❌ Failed to sync skill: {error_msg or result}")
    
    def _log_result_final(result: Dict[str, Any]):
        """Log result for the ADD retry (no further retries)"""
        error_msg = result.get('error')
        if not error_msg:
            errors = result.get('errors')
            if isinstance(errors, list) and errors:
                error_msg = '; '.join([str(e) for e in errors if e])
        if result.get('synced'):
            logger.info(f"[skill_handler] ✅ Skill synced to cloud (ADD retry): {skill_data.get('name')}")
        else:
            logger.error(f"[skill_handler] ❌ ADD retry also failed: {error_msg or result}")
    
    # Relativize the 'path' field before sending to cloud.
    # Local DB stores the full filesystem path (e.g. C:\...\my_skills\passive0_skill\diagram_dir\...).
    # Cloud should only receive a relative path within the skill dir.
    cloud_data = skill_data.copy()
    raw_path = cloud_data.get('path', '')
    if raw_path:
        from pathlib import PurePosixPath, PureWindowsPath
        try:
            p = Path(raw_path)
            # Extract the portion starting from my_skills/ (or just the last 3 segments)
            parts = p.parts
            # Find 'my_skills' in the path parts
            for i, part in enumerate(parts):
                if part == 'my_skills':
                    cloud_data['path'] = '/'.join(parts[i:])
                    break
            else:
                # Fallback: just use the last segment (filename)
                cloud_data['path'] = p.name
        except Exception:
            pass

    # Use SyncManager's thread pool for async execution
    # Note: Use SKILL for Skill entity data (name, description, etc.)
    #       Use AGENT_SKILL for Agent-Skill relationship data (agid, skid, owner)
    manager = get_sync_manager()
    manager.sync_to_cloud_async(DataType.SKILL, cloud_data, operation, callback=_log_result)


def _sync_skill_delete_to_cloud(skill_data: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronously sync skill delete to cloud and return detailed result.

    This is used by delete_agent_skill so the caller can distinguish:
    - actually deleted in cloud
    - cached to offline queue for later retry
    - failed immediately
    """
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType

    cloud_data = skill_data.copy()
    raw_path = cloud_data.get('path', '')
    if raw_path:
        try:
            p = Path(raw_path)
            parts = p.parts
            for i, part in enumerate(parts):
                if part == 'my_skills':
                    cloud_data['path'] = '/'.join(parts[i:])
                    break
            else:
                cloud_data['path'] = p.name
        except Exception:
            pass

    logger.info(
        f"[skill_handler] Syncing skill delete to cloud: id={cloud_data.get('id')}, "
        f"owner={cloud_data.get('owner')}, path={cloud_data.get('path', '')}"
    )

    manager = get_sync_manager()
    result = manager.sync_to_cloud(DataType.SKILL, cloud_data, Operation.DELETE)

    error_msg = result.get('error')
    if not error_msg:
        errors = result.get('errors')
        if isinstance(errors, list) and errors:
            error_msg = '; '.join([str(e) for e in errors if e])

    logger.info(
        f"[skill_handler] Skill delete cloud sync result: "
        f"success={result.get('success')}, synced={result.get('synced')}, "
        f"cached={result.get('cached')}, error={error_msg or ''}"
    )

    return {
        'success': bool(result.get('success')),
        'synced': bool(result.get('synced')),
        'cached': bool(result.get('cached')),
        'task_id': result.get('task_id'),
        'error': error_msg,
        'response': result.get('response'),
    }


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
    from gui.ipc.context_bridge import get_handler_context
    
    manager = get_sync_manager()
    ctx = get_handler_context()
    owner = ctx.get_username() if ctx else 'unknown'
    
    logger.info(f"[skill_handler] Syncing {len(tool_ids)} tool relationships for skill: {skill_id}")
    
    for tool_id in tool_ids:
        relation_data = {
            'skill_id': skill_id,
            'tool_id': tool_id
        }
        
        def _log_result(result: Dict[str, Any]):
            error_msg = result.get('error')
            if not error_msg:
                errors = result.get('errors')
                if isinstance(errors, list) and errors:
                    error_msg = '; '.join([str(e) for e in errors if e])
            if result.get('synced'):
                logger.info(f"[skill_handler] ✅ Tool relation synced: {tool_id}")
            elif result.get('cached'):
                logger.info(f"[skill_handler] 💾 Tool relation cached: {tool_id}")
            else:
                logger.error(f"[skill_handler] ❌ Failed to sync tool relation: {error_msg or result}")
        
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
    from gui.ipc.context_bridge import get_handler_context
    
    manager = get_sync_manager()
    ctx = get_handler_context()
    owner = ctx.get_username() if ctx else 'unknown'
    
    logger.info(f"[skill_handler] Syncing {len(knowledge_ids)} knowledge relationships for skill: {skill_id}")
    
    for knowledge_id in knowledge_ids:
        relation_data = {
            'skill_id': skill_id,
            'knowledge_id': knowledge_id
        }
        
        def _log_result(result: Dict[str, Any]):
            error_msg = result.get('error')
            if not error_msg:
                errors = result.get('errors')
                if isinstance(errors, list) and errors:
                    error_msg = '; '.join([str(e) for e in errors if e])
            if result.get('synced'):
                logger.info(f"[skill_handler] ✅ Knowledge relation synced: {knowledge_id}")
            elif result.get('cached'):
                logger.info(f"[skill_handler] 💾 Knowledge relation cached: {knowledge_id}")
            else:
                logger.error(f"[skill_handler] ❌ Failed to sync knowledge relation: {error_msg or result}")
        
        manager.sync_to_cloud_async(DataType.SKILL_KNOWLEDGE, relation_data, operation, callback=_log_result)


def sync_skill_from_file(file_path: str, request=None, params=None) -> Dict[str, Any]:
    """
    Standard function to sync skill from file to database.
    This function reads the skill JSON file and creates/updates the skill in database.
    
    **IMPORTANT**: Skills from resource/my_skills are code-based (source=code) and should NOT
    be saved to database. They are read-only examples that only exist in memory.
    
    Args:
        file_path: Full path to the skill JSON file
        request: IPC request object (optional)
        params: Request parameters (optional)
    
    Returns:
        Dict with success status and skill_id
    """
    
    try:
        import os
        # Normalize file path to handle Chinese characters correctly
        # This ensures consistent path format in database for proper querying
        file_path = os.path.abspath(os.path.normpath(file_path))
        
        # Check if this is a code-based skill from resource/my_skills
        code_skill = is_code_skill(file_path)
        
        # Read skill JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            skill_data = json.load(f)
        
        # Get username from AppContext
        ctx = get_handler_context(request, params)
        if not ctx or not True:
            raise ValueError("Cannot get username: ctx or ctx.get_username() not available")
        
        username = ctx.get_username()
        
        # Get skill service
        skill_service = _get_skill_service(request, params)
        if not skill_service:
            return {'success': False, 'error': 'Database service not available'}
        
        # Prepare skill data - only use fields that have values
        skill_name = skill_data.get('name') or skill_data.get('skillName', 'Unnamed Skill')
        
        logger.info(f"[skill_handler] Syncing skill: {skill_name}, path: {file_path}")
        
        # Standard upsert logic: find existing skill by path first, then by name
        existing_skill = skill_service.get_skill_by_path(file_path)
        
        if not (existing_skill.get('success') and existing_skill.get('data')):
            # Not found by path, try by name (handles rename scenarios)
            logger.debug(f"[skill_handler] Skill not found by path, trying by name: {skill_name}")
            name_search = skill_service.query_skills(name=skill_name)
            if name_search.get('success') and name_search.get('data'):
                candidates = name_search.get('data', [])
                # Filter to user's skills only to avoid updating other users' skills
                user_candidates = [s for s in candidates if s.get('owner') == username]
                if user_candidates:
                    existing_skill = {'success': True, 'data': user_candidates[0]}
                    logger.info(f"[skill_handler] Found existing skill by name: {skill_name} (ID: {user_candidates[0].get('id')})")
        
        # At this point: existing_skill has data → UPDATE, no data → INSERT
        
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
                          'limitations', 'price', 'price_model', 'public', 'rentable',
                          'run_in_cloud', 'hybrid_cloud_mode', 'local_helper_skill_id', 'local_helper_machine']
        for field in optional_fields:
            if field in skill_data and skill_data[field] is not None:
                skill_info[field] = skill_data[field]
        
        logger.debug(f"[skill_handler] Prepared skill_info with {len(skill_info)} fields")
        
        # For code skills, skip database operations (only update memory)
        if code_skill:
            logger.info(f"[skill_handler] ⚠️ Code skill detected, skipping database sync: {skill_name}")
            return {
                'success': True,
                'skipped': True,
                'reason': 'code_skill',
                'message': 'Code skills are not saved to database'
            }
        
        # For UI skills, perform normal database operations
        if existing_skill.get('success') and existing_skill.get('data'):
            # Update existing skill
            skill_id = existing_skill['data']['id']
            logger.info(f"[skill_handler] Updating existing skill: {skill_name} (ID: {skill_id})")
            
            prepared_data = _prepare_skill_data(skill_info, username, skill_id)
            logger.debug(f"[skill_handler] Prepared data for update: path={prepared_data.get('path')}")
            result = skill_service.update_skill(skill_id, prepared_data)
            
            if result.get('success'):
                # Update memory
                _update_skill_in_memory(skill_id, prepared_data, request, params)
                
                # Sync to cloud
                skill_data_with_id = prepared_data.copy()
                skill_data_with_id['id'] = skill_id
                _trigger_cloud_sync(skill_data_with_id, Operation.UPDATE)
                
                # NOTE: S3 file upload is NOT done here.
                # sync_skill_from_file is a secondary path (triggered by file_handler
                # detecting a _skill.json write). The primary save handlers
                # (handle_save_agent_skill / handle_new_agent_skill) already handle
                # S3 upload, so doing it here would cause duplicate requests.
                
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
                _update_skill_in_memory(skill_id, prepared_data, request, params)
                
                # Sync to cloud
                skill_data_with_id = prepared_data.copy()
                skill_data_with_id['id'] = skill_id
                _trigger_cloud_sync(skill_data_with_id, Operation.ADD)
                
                # NOTE: S3 file upload is NOT done here (see comment in update branch above).
                
                logger.info(f"[skill_handler] ✅ Skill created successfully: {skill_name} (ID: {skill_id})")
                return {'success': True, 'skill_id': skill_id, 'operation': 'create'}
            else:
                logger.error(f"[skill_handler] ❌ Failed to create skill: {result.get('error')}")
                return {'success': False, 'error': result.get('error')}
                
    except Exception as e:
        logger.error(f"[skill_handler] ❌ Error syncing skill from file: {e}")
        return {'success': False, 'error': str(e)}
