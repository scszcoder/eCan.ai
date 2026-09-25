import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from agent.vehicles.vehicles import VEHICLE

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.background_handler('get_vehicles')
def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get all vehicles list

    Args:
        request: IPC request object
        params: Request parameters

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get vehicles handler called with request: {request}")
        ctx = get_handler_context(request, params)
        vehicles = ctx.get_vehicles()

        # Add detailed debug logs
        logger.info(f"[DEBUG] get_vehicles called")
        logger.info(f"[DEBUG] ctx.get_vehicles() type: {type(vehicles)}")
        logger.info(f"[DEBUG] ctx.get_vehicles() count: {len(vehicles) if vehicles else 0}")
        if vehicles and len(vehicles) > 0:
            logger.info(f"[DEBUG] First vehicle: {vehicles[0].to_dict() if hasattr(vehicles[0], 'to_dict') else str(vehicles[0])}")
        else:
            logger.warning(f"[DEBUG] ctx.get_vehicles() is empty!")

        vehicle_dicts = [v.to_dict() for v in vehicles]

        # Merge DB vehicle rows (SHARED_SKILL_MULTI_TASK_PLAN Phase 1.5):
        # the affinity gate keys on the DBAgentVehicle row registered with
        # the discovery machine_id, which the legacy in-memory list doesn't
        # contain. Include DB rows so the agent vehicle-assignment dropdown
        # can select the canonical local vehicle.
        try:
            ec_db_mgr = ctx.get_ec_db_mgr() if hasattr(ctx, 'get_ec_db_mgr') else None
            vehicle_service = getattr(ec_db_mgr, 'vehicle_service', None)
            if vehicle_service is not None:
                db_result = vehicle_service.query_vehicles()
                db_rows = db_result.get('data', []) if isinstance(db_result, dict) and db_result.get('success') else []
                seen_ids = {str(v.get('id')) for v in vehicle_dicts if isinstance(v, dict) and v.get('id')}
                merged = 0
                for row in db_rows:
                    if not isinstance(row, dict):
                        continue
                    rid = str(row.get('id') or '')
                    if not rid or rid in seen_ids:
                        continue
                    seen_ids.add(rid)
                    entry = dict(row)
                    # Legacy VEHICLE dicts expose 'ip'; DB rows use 'ip_address'
                    if 'ip' not in entry and entry.get('ip_address'):
                        entry['ip'] = entry['ip_address']
                    vehicle_dicts.append(entry)
                    merged += 1
                if merged:
                    logger.info(f"[get_vehicles] merged {merged} DB vehicle row(s) into response")
        except Exception as db_err:
            logger.warning(f"[get_vehicles] DB vehicle merge failed (non-fatal): {db_err}")

        # Every other machine on this account, wherever it is. The lists above
        # only know this machine and what LAN discovery happened to hear, so a
        # machine in another office never appeared.
        try:
            seen_ids = {str(v.get('id')) for v in vehicle_dicts if isinstance(v, dict) and v.get('id')}
            remote = _cloud_machines(seen_ids)
            vehicle_dicts.extend(remote)
            if remote:
                logger.info(f"[get_vehicles] added {len(remote)} other machine(s) (cloud + LAN)")
        except Exception as cloud_err:
            logger.warning(f"[get_vehicles] cloud machine list unavailable (non-fatal): {cloud_err}")

        vehicle_dicts = _mark_self_and_scope(vehicle_dicts)

        logger.info(f"get vehicles successful")
        resultJS = {
            'vehicles': vehicle_dicts,
            'message': 'Get all successful'
        }
        # logger.debug('get vehicles resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get vehicles handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_VEHICLES_ERROR',
            f"Error during get vehicles: {str(e)}"
        )


# A desktop heartbeats every 60s; three missed beats = offline. Read from the
# heartbeat stamp rather than `status`, which the server's reaper only flips on
# its 5-minute timer.
_MACHINE_ONLINE_WITHIN_S = 180
# LAN discovery re-announces on its own cadence; a node not heard for this long
# is shown offline rather than dropped.
_LAN_ONLINE_WITHIN_S = 300


def _heartbeat_age_s(stamp) -> Optional[float]:
    """Seconds since an ISO heartbeat stamp (UTC), or None when absent/unparsable."""
    if not stamp:
        return None
    try:
        from datetime import datetime, timezone
        s = str(stamp).replace('Z', '+00:00')
        ts = datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)   # the server stamps UTC
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return None


def _machine_entry(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A cloud vehicle row as a Vehicles-page entry, or None when it is not a live machine.

    Desktops: online from the heartbeat stamp, which the vehicles heartbeat
    writes in UTC. Rows never stamped are skipped -- the pre-2026-09-24
    duplicates keyed by hostname (e.g. ``SCHOME:win``) for the same machines.

    Cloud pods: only running instances. Their stamp is written by the server in
    PRC local time and would read 8h in the future, so ``status`` -- which the
    reaper keeps for pods -- is the source. Offline pod tombstones and the
    customer's pod definitions are left to the Pods panel.
    """
    rid = str(row.get('id') or '')
    if not rid:
        return None
    is_pod = row.get('vehicle_type') == POD_VEHICLE_TYPE
    if is_pod:
        if _is_customer_pod(row) or row.get('status') != 'online':
            return None
        online = True
    else:
        if not row.get('last_heartbeat'):
            return None
        age = _heartbeat_age_s(row.get('last_heartbeat'))
        online = row.get('status') == 'online' and age is not None and age < _MACHINE_ONLINE_WITHIN_S
    return {
        'id': rid,
        'name': row.get('name') or row.get('hostname') or rid,
        'role': _reported_role(row),
        'type': 'cloud' if is_pod else 'desktop',
        'status': 'active' if online else 'offline',
        'ip': row.get('ip_address') or '',
        'os': row.get('platform') or '',
        'arch': row.get('architecture') or '',
        'last_heartbeat': row.get('last_heartbeat'),
        'capabilities': row.get('capabilities'),
        'source': 'cloud',
    }


def _reported_role(row: Dict[str, Any]) -> str:
    """Commander / Platoon / ... as the machine's heartbeat reported it, or ""."""
    meta = row.get('extra_metadata') or {}
    if isinstance(meta, str):
        try:
            import json as _json
            meta = _json.loads(meta)
        except Exception:
            return ''
    return str(meta.get('role') or '') if isinstance(meta, dict) else ''


def _mark_self_and_scope(entries: list) -> list:
    """Mark this machine (``is_self``, its role) and apply the role's view.

    A Commander sees the whole account. A Platoon sees itself and the
    Commander(s) it answers to -- not pods, not the other Platoons. This machine
    is always listed, even before its first heartbeat reaches the cloud.
    """
    mainwin = AppContext.get_main_window()
    if mainwin is None:
        return entries
    from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id, sees_whole_fleet
    try:
        me = resolve_local_vehicle_id(mainwin) or ''
    except Exception:
        me = ''
    role = str(getattr(mainwin, 'host_role', '') or '')
    found = False
    for e in entries:
        if isinstance(e, dict) and me and str(e.get('id')) == me:
            e['is_self'] = True
            e['role'] = role
            e['status'] = 'active'
            found = True
    if me and not found:
        entries.append({
            'id': me,
            'name': getattr(mainwin, 'machine_name', '') or me,
            'role': role,
            'is_self': True,
            'type': 'desktop',
            'status': 'active',
            'ip': getattr(mainwin, 'ip', '') or '',
            'os': getattr(mainwin, 'platform', '') or '',
            'arch': getattr(mainwin, 'processor', '') or '',
            'source': 'local',
        })
    if sees_whole_fleet(mainwin):
        return entries
    return [e for e in entries if isinstance(e, dict)
            and (e.get('is_self') or 'Commander' in str(e.get('role') or ''))]


def _lan_entry(node) -> Optional[Dict[str, Any]]:
    """A LAN-discovered eCan install (same account: discovery checks its auth fingerprint)."""
    import time as _time
    mid = str(getattr(node, 'machine_id', '') or '')
    if not mid:
        return None
    seen = float(getattr(node, 'lan_last_seen', 0) or 0)
    online = seen > 0 and (_time.time() - seen) < _LAN_ONLINE_WITHIN_S
    return {
        'id': mid,
        'name': getattr(node, 'machine_name', '') or mid,
        'role': getattr(node, 'role', '') or '',
        'type': 'desktop',
        'status': 'active' if online else 'offline',
        'ip': getattr(node, 'lan_host', '') or '',
        'os': getattr(node, 'os', '') or '',
        'arch': getattr(node, 'arch', '') or '',
        'source': 'lan',
    }


def _lan_machines() -> list:
    try:
        from agent.a2a.discovery.directory import get_directory
        return [e for e in (_lan_entry(n) for n in get_directory().list_nodes()) if e]
    except Exception as e:
        logger.debug(f"[get_vehicles] LAN discovery directory unavailable: {e}")
        return []


def _cloud_machines(exclude_ids) -> list:
    """This account's other machines: cloud registry (desktops + running pods) and LAN.

    One entry per machine id. Since 2026-09-24 a machine advertises its vehicle
    id on the LAN too, so the same machine seen both ways merges into one entry
    (``source: cloud+lan``); the LAN side contributes its address.
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    ctx = _cloud_ctx()
    if ctx is not None:
        try:
            for row in _query_pod_rows(ctx):
                entry = _machine_entry(row) if isinstance(row, dict) else None
                if entry:
                    by_id[entry['id']] = entry
        except Exception as e:
            logger.warning(f"[get_vehicles] cloud machine list unavailable: {e}")
    for lan in _lan_machines():
        cur = by_id.get(lan['id'])
        if cur is None:
            by_id[lan['id']] = lan
        else:
            cur['source'] = 'cloud+lan'
            cur['ip'] = lan['ip'] or cur['ip']
            cur['role'] = cur.get('role') or lan['role']
            if lan['status'] == 'active':
                cur['status'] = 'active'
    return [e for mid, e in by_id.items() if mid not in exclude_ids]


def _vehicle_db_service(ctx):
    """The local vehicle DB service, or None."""
    try:
        ec_db_mgr = ctx.get_ec_db_mgr() if hasattr(ctx, 'get_ec_db_mgr') else None
        return getattr(ec_db_mgr, 'vehicle_service', None)
    except Exception as e:
        logger.warning(f'[vehicles] vehicle DB service unavailable: {e}')
        return None


def _db_vehicle_row(ctx, vehicle_id):
    """One DB-backed vehicle row by id, or None."""
    service = _vehicle_db_service(ctx)
    if service is None:
        return None
    try:
        result = service.query_vehicles(id=str(vehicle_id))
    except Exception as e:
        logger.warning(f'[vehicles] DB lookup failed for {vehicle_id}: {e}')
        return None
    rows = result.get('data') if isinstance(result, dict) and result.get('success') else None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


@IPCHandlerRegistry.handler('update_vehicle_status')
def handle_update_vehicle_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Update vehicle status

    Args:
        request: IPC request object
        params: Request parameters
            - vehicle_id: int - Vehicle ID
            - status: str - New status (active/offline/maintenance)

    Returns:
        str: JSON formatted response message
    """
    try:
        vehicle_id = params.get('vehicle_id')
        new_status = params.get('status')

        if not vehicle_id or not new_status:
            return create_error_response(request, 'INVALID_PARAMS', 'vehicle_id and status are required')

        ctx = get_handler_context(request, params)

        # Status mapping: frontend active -> backend online
        status_map = {'active': 'online', 'offline': 'offline', 'maintenance': 'maintenance'}
        backend_status = status_map.get(new_status, new_status)

        vehicle = next((v for v in ctx.get_vehicles() if str(v.id) == str(vehicle_id)), None)
        if vehicle is not None:
            vehicle.setStatus(backend_status)
            ctx.main_window.saveVehicle(vehicle)

            logger.info(f"Updated vehicle {vehicle_id} status to {backend_status}")
            return create_success_response(request, {
                'vehicle': vehicle.to_dict(),
                'message': 'Status updated successfully'
            })

        # Not a discovered machine. The list also shows DB-backed rows (merged
        # in by get_vehicles), which have a string id and no `vid`, so they are
        # never in the in-memory registry and used to fail here as
        # VEHICLE_NOT_FOUND.
        row = _db_vehicle_row(ctx, vehicle_id)
        if row is None:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')

        if row.get('vehicle_type') == POD_VEHICLE_TYPE:
            # A pod's status is observed state: the fleet reports whether it is
            # up, and writing 'online' into a row would not start anything. It
            # would only make the UI claim a machine is serving when none is.
            return create_error_response(
                request, 'POD_STATUS_IS_REPORTED',
                "A pod's status is reported by the fleet, not set by hand. "
                "Change its lifecycle or replica count in the Pods panel instead.")

        service = _vehicle_db_service(ctx)
        result = service.update_vehicle(str(vehicle_id), {'status': backend_status})
        if isinstance(result, dict) and not result.get('success', True):
            return create_error_response(
                request, 'UPDATE_STATUS_ERROR',
                str(result.get('error') or 'Failed to update status'))

        logger.info(f"Updated DB vehicle {vehicle_id} status to {backend_status}")
        return create_success_response(request, {
            'vehicle': {**row, 'status': backend_status},
            'message': 'Status updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating vehicle status: {e} {traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_STATUS_ERROR', str(e))


@IPCHandlerRegistry.handler('add_vehicle')
def handle_add_vehicle(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Add new vehicle

    Args:
        request: IPC request object
        params: Request parameters
            - name: str - Device name
            - ip: str - IP address
            - os: str - Operating system
            - arch: str - System architecture

    Returns:
        str: JSON formatted response message
    """
    try:
        name = params.get('name')
        ip = params.get('ip', '0.0.0.0')

        if not name:
            return create_error_response(request, 'INVALID_PARAMS', 'name is required')

        ctx = get_handler_context(request, params)

        # Check if vehicle with same name or IP already exists
        existing = next((v for v in ctx.get_vehicles() if v.getName() == name or v.getIP() == ip), None)
        if existing:
            return create_error_response(request, 'VEHICLE_EXISTS', f'Vehicle with name {name} or ip {ip} already exists')

        # Create new vehicle
        new_vehicle = VEHICLE(ctx, name=name, ip=ip)
        new_vehicle.setOS(params.get('os', ctx.main_window.os_short))
        new_vehicle.setArch(params.get('arch', ''))
        new_vehicle.setStatus(params.get('status', 'offline'))
        new_vehicle.setFunctions(params.get('functions', ''))
        new_vehicle.setTestDisabled(params.get('test_disabled', False))

        # Generate ID
        new_vehicle.setVid(len(ctx.get_vehicles()) + 1)

        ctx.get_vehicles().append(new_vehicle)
        ctx.main_window.saveVehicle(new_vehicle)
        ctx.main_window.saveVehiclesJsonFile()

        logger.info(f"Added new vehicle: {name}")
        return create_success_response(request, {
            'vehicle': new_vehicle.to_dict(),
            'message': 'Vehicle added successfully'
        })

    except Exception as e:
        logger.error(f"Error adding vehicle: {e} {traceback.format_exc()}")
        return create_error_response(request, 'ADD_VEHICLE_ERROR', str(e))


@IPCHandlerRegistry.handler('update_vehicle')
def handle_update_vehicle(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Update vehicle information

    Args:
        request: IPC request object
        params: Request parameters
            - vehicle_id: int - Vehicle ID
            - name: str - Device name
            - ip: str - IP address
            - status: str - Status
            - ... Other fields

    Returns:
        str: JSON formatted response message
    """
    try:
        vehicle_id = params.get('vehicle_id')

        if not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'vehicle_id is required')

        ctx = get_handler_context(request, params)
        vehicle = next((v for v in ctx.get_vehicles() if str(v.id) == str(vehicle_id)), None)

        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')

        # Update fields
        if 'name' in params:
            vehicle.setName(params['name'])
        if 'ip' in params:
            vehicle.setIP(params['ip'])
        if 'os' in params:
            vehicle.setOS(params['os'])
        if 'arch' in params:
            vehicle.setArch(params['arch'])
        if 'status' in params:
            status_map = {'active': 'online', 'offline': 'offline', 'maintenance': 'maintenance'}
            backend_status = status_map.get(params['status'], params['status'])
            vehicle.setStatus(backend_status)
        if 'functions' in params:
            vehicle.setFunctions(params['functions'])
        if 'test_disabled' in params:
            vehicle.setTestDisabled(params['test_disabled'])

        ctx.main_window.saveVehicle(vehicle)
        ctx.main_window.saveVehiclesJsonFile()

        logger.info(f"Updated vehicle {vehicle_id}")
        return create_success_response(request, {
            'vehicle': vehicle.to_dict(),
            'message': 'Vehicle updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating vehicle: {e} {traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_VEHICLE_ERROR', str(e))


@IPCHandlerRegistry.handler('delete_vehicle')
def handle_delete_vehicle(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete vehicle

    Args:
        request: IPC request object
        params: Request parameters
            - vehicle_id: int - Vehicle ID

    Returns:
        str: JSON formatted response message
    """
    try:
        vehicle_id = params.get('vehicle_id')

        if not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'vehicle_id is required')

        ctx = get_handler_context(request, params)
        vehicle = next((v for v in ctx.get_vehicles() if str(v.id) == str(vehicle_id)), None)

        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')

        # Check if there are associated bots
        if len(vehicle.getBotIds()) > 0:
            return create_error_response(
                request,
                'VEHICLE_HAS_BOTS',
                f'Cannot delete vehicle with {len(vehicle.getBotIds())} assigned bots'
            )

        ctx.get_vehicles().remove(vehicle)
        ctx.main_window.saveVehiclesJsonFile()

        # Delete from database (if Commander role)
        if ctx.get_vehicle_service():
            try:
                db_vehicle = ctx.get_vehicle_service().find_vehicle_by_name(vehicle.getName())
                if db_vehicle:
                    ctx.get_vehicle_service().session.delete(db_vehicle)
                    ctx.get_vehicle_service().session.commit()
            except Exception as db_error:
                logger.warning(f"Failed to delete vehicle from database: {db_error}")

        logger.info(f"Deleted vehicle {vehicle_id}")
        return create_success_response(request, {
            'message': 'Vehicle deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting vehicle: {e} {traceback.format_exc()}")
        return create_error_response(request, 'DELETE_VEHICLE_ERROR', str(e))


@IPCHandlerRegistry.handler('assign_bot_to_vehicle')
def handle_assign_bot_to_vehicle(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Assign bot to specified vehicle

    Args:
        request: IPC request object
        params: Request parameters
            - bot_id: str - Bot ID
            - vehicle_id: int - Vehicle ID

    Returns:
        str: JSON formatted response message
    """
    try:
        bot_id = params.get('bot_id')
        vehicle_id = params.get('vehicle_id')

        if not bot_id or not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'bot_id and vehicle_id are required')

        ctx = get_handler_context(request, params)
        vehicle = next((v for v in ctx.get_vehicles() if str(v.id) == str(vehicle_id)), None)

        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')

        # Check capacity
        if vehicle.getBotsOverCapStatus():
            return create_error_response(
                request,
                'VEHICLE_FULL',
                f'Vehicle is at capacity ({vehicle.CAP} bots)'
            )

        # Add bot
        added = vehicle.addBot(bot_id)
        if added == 0:
            return create_error_response(request, 'BOT_ALREADY_ASSIGNED', f'Bot {bot_id} already assigned to this vehicle')
        
        ctx.main_window.saveVehicle(vehicle)
        ctx.main_window.saveVehiclesJsonFile()
        
        logger.info(f"Assigned bot {bot_id} to vehicle {vehicle_id}")
        return create_success_response(request, {
            'vehicle': vehicle.to_dict(),
            'message': 'Bot assigned successfully'
        })
        
    except Exception as e:
        logger.error(f"Error assigning bot to vehicle: {e} {traceback.format_exc()}")
        return create_error_response(request, 'ASSIGN_BOT_ERROR', str(e))


@IPCHandlerRegistry.handler('remove_bot_from_vehicle')
def handle_remove_bot_from_vehicle(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Remove bot from vehicle

    Args:
        request: IPC request object
        params: Request parameters
            - bot_id: str - Bot ID
            - vehicle_id: int - Vehicle ID

    Returns:
        str: JSON formatted response message
    """
    try:
        bot_id = params.get('bot_id')
        vehicle_id = params.get('vehicle_id')

        if not bot_id or not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'bot_id and vehicle_id are required')

        ctx = get_handler_context(request, params)
        vehicle = next((v for v in ctx.get_vehicles() if str(v.id) == str(vehicle_id)), None)

        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')

        # Remove bot
        removed = vehicle.removeBot(bot_id)
        if removed == 0:
            return create_error_response(request, 'BOT_NOT_FOUND', f'Bot {bot_id} not assigned to this vehicle')

        ctx.main_window.saveVehicle(vehicle)
        ctx.main_window.saveVehiclesJsonFile()

        logger.info(f"Removed bot {bot_id} from vehicle {vehicle_id}")
        return create_success_response(request, {
            'vehicle': vehicle.to_dict(),
            'message': 'Bot removed successfully'
        })

    except Exception as e:
        logger.error(f"Error removing bot from vehicle: {e} {traceback.format_exc()}")
        return create_error_response(request, 'REMOVE_BOT_ERROR', str(e))

# ===========================================================================
# Pods — a vehicle the customer creates, sizes and pays for
#
# The handlers above manage the legacy machine registry (in-memory VEHICLE list
# + vehicles JSON). A pod is not a discovered machine and it is not local: it
# is a row in the CLOUD vehicles table that the fleet scheduler places work on.
# The cloud is the source of truth — these handlers read and write it directly
# and keep no local copy, so a pod created on one desktop is the same pod
# everywhere the customer signs in. The machine handlers above are untouched.
#
# (The local agent_vehicles table still carries vehicle_type='cloud' rows, but
# those are written by `vehicle_affinity.register_pod_vehicle` — a running pod
# registering ITSELF on its own machine. Different producer, different box.)
#
# Desired state (lifecycle, desired_replicas) is what the customer sets;
# observed state (status, last_heartbeat, health_score) is what the fleet
# reports. Both are returned, never merged — a customer raising replicas should
# watch it converge, not be told it already happened.
# ===========================================================================

POD_VEHICLE_TYPE = 'cloud'

# The desired-state fields. They have no columns on the CN Vehicle type yet, so
# they travel inside `settings` under this key. When the columns land, the
# column wins and the blob becomes a fallback for rows written before the
# migration — see `_pod_view`.
POD_SETTINGS_KEY = 'pod'
POD_DESIRED_FIELDS = ('lifecycle', 'idle_shutdown_minutes', 'desired_replicas')

# None = not probed yet, True/False = this backend does/does not have the
# columns. Probed once per process: a backend does not grow columns mid-session.
_pod_columns_supported: Optional[bool] = None


def _cloud_ctx() -> Optional[Dict[str, Any]]:
    """{session, token, endpoint} from the running app, or None.

    No owner: every pod call lets the server resolve it from the verified
    identity, so the client never has to know which spelling of the id this
    session's identity.sub happens to be.
    """
    try:
        from agent.cloud_api.cloud_api import get_appsync_endpoint

        mainwin = AppContext.get_main_window()
        if mainwin is None:
            logger.warning('[pods] MainWindow not available')
            return None

        token = mainwin.get_auth_token()
        if not token:
            logger.warning('[pods] no auth token — not signed in')
            return None

        endpoint = (mainwin.getWanApiEndpoint()
                    if hasattr(mainwin, 'getWanApiEndpoint') else None) or get_appsync_endpoint()
        return {
            'session': mainwin.session,
            'token': token,
            'endpoint': endpoint,
        }
    except Exception as e:
        logger.warning(f'[pods] could not build cloud context: {e}')
        return None


def _is_missing_pod_columns(exc: Exception) -> bool:
    """True when *exc* is the backend saying it has no pod columns.

    A selection set naming a field the schema lacks fails the whole query with
    GRAPHQL_VALIDATION_FAILED, so this has to be told apart from a real error
    before falling back — otherwise every outage would look like an old schema.
    """
    msg = str(exc)
    return ('VALIDATION' in msg.upper() or 'Cannot query field' in msg) and \
        any(f in msg for f in POD_DESIRED_FIELDS)


def _query_pod_rows(ctx: Dict[str, Any]) -> list:
    """Every cloud vehicle of the signed-in owner's, pods and machines alike.

    Tries the pod columns first and remembers the answer, so a backend that has
    them is not punished with a doomed request on every call.
    """
    global _pod_columns_supported
    from agent.cloud_api.cloud_api import send_query_vehicles_request_to_cloud

    # Deliberately an empty input: the resolver scopes every read to the
    # verified identity anyway, and passing an explicit owner is what returned
    # "Cross-owner access is forbidden" for the WeChat account on 2026-09-08 --
    # the identity.sub for that session matched neither the prefixed nor the
    # bare openid. `queryAgents(input: {})` is the shape that works.
    q: Dict[str, Any] = {}

    if _pod_columns_supported is not False:
        try:
            rows = send_query_vehicles_request_to_cloud(
                ctx['session'], ctx['token'], q, ctx['endpoint'], with_pod_columns=True)
            _pod_columns_supported = True
            return rows or []
        except Exception as e:
            if not _is_missing_pod_columns(e):
                raise
            _pod_columns_supported = False
            logger.info('[pods] backend has no pod desired-state columns yet — '
                        'reading them from settings instead')

    rows = send_query_vehicles_request_to_cloud(
        ctx['session'], ctx['token'], q, ctx['endpoint'])
    return rows or []


def _pod_settings_blob(row: Dict[str, Any]) -> Dict[str, Any]:
    """The desired-state blob this client wrote, or {}."""
    settings = row.get('settings') or {}
    if isinstance(settings, str):
        try:
            import json as _json
            settings = _json.loads(settings)
        except Exception:
            return {}
    if not isinstance(settings, dict):
        return {}
    blob = settings.get(POD_SETTINGS_KEY)
    return blob if isinstance(blob, dict) else {}


def _is_customer_pod(row: Dict[str, Any]) -> bool:
    """True for a pod the customer created here, not a running instance.

    `vehicle_type` alone does NOT separate them: the fleet's own
    `vehicle_register` hard-codes `'cloud'` for every pod that registers itself
    (ecbAccountManager `vehicleRegister`), and a Deployment rollout registers a
    NEW row per pod name while the old ones linger as offline tombstones. Both
    would otherwise land in "your pods" — each with an invented cost and a
    Delete button — and, worse, count against the pod limit, so an owner with
    five running pods could not create a first one of their own.

    The desired-state blob is the discriminator: only `save_pod` writes it, and
    it keeps writing it even once the columns exist. Runtime instances never
    have one. What the fleet is actually running belongs in `get_fleet_status`,
    which reports it already.
    """
    return (row.get('vehicle_type') == POD_VEHICLE_TYPE
            and bool(_pod_settings_blob(row)))


def _pod_view(row: Dict[str, Any]) -> Dict[str, Any]:
    """One pod as the GUI needs it: desired state, observed state, and cost.

    Desired state is read column-first, blob-second. Both spellings of the
    sized fields are accepted because the cloud mirrors camelCase to snake_case
    on the way out and only one of them is guaranteed present.
    """
    from agent.pod_sizing import estimate_pod_cost, normalize_lifecycle

    def _pick(*names, default=None):
        for n in names:
            if row.get(n) is not None:
                return row.get(n)
        return default

    blob = _pod_settings_blob(row)

    def _desired(name, default=None):
        value = row.get(name)
        return blob.get(name, default) if value is None else value

    cpu = _pick('cpu_cores', 'cpuCores', default=0)
    memory_gb = _pick('memory_gb', 'memoryGb', default=0)
    lifecycle = normalize_lifecycle(_desired('lifecycle'))
    replicas = int(_desired('desired_replicas', 1) or 1)

    return {
        **row,
        'id': row.get('id'),
        'name': row.get('name'),
        'status': row.get('status') or 'offline',
        'cpu_cores': cpu,
        'memory_gb': memory_gb,
        'max_concurrent_tasks': _pick('max_concurrent_tasks', 'maxConcurrentTasks', default=1),
        'last_heartbeat': _pick('last_heartbeat', 'lastHeartbeat'),
        'health_score': _pick('health_score', 'healthScore'),
        'lifecycle': lifecycle,
        'desired_replicas': replicas,
        'idle_shutdown_minutes': _desired('idle_shutdown_minutes'),
        'capabilities': row.get('capabilities') or [],
        'cost': estimate_pod_cost(cpu, memory_gb, lifecycle=lifecycle, replicas=replicas),
    }


def _pod_limits() -> Dict[str, Any]:
    """The per-owner ceilings, as far as the client knows them.

    Advisory only: the server enforces caps at scale-up, and it is the
    authority. Showing them here is so a customer does not walk into a refusal
    — not so the client can decide who gets a pod.
    """
    import os

    def _int(name, default):
        try:
            return int(os.environ.get(name) or default)
        except ValueError:
            return default

    return {
        'max_pods': _int('ECAN_MAX_PODS_PER_OWNER', 5),
        'daily_spend_cny': _int('ECAN_MAX_DAILY_SPEND_CNY', 500),
        'enforced_by': 'server',
    }


@IPCHandlerRegistry.handler('get_pods')
def handle_get_pods(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """List this owner's pods, with sizes, costs and the caps that apply.

    An unreachable cloud is an error, not an empty list. Pods live only in the
    cloud, so returning [] would render as "you have no pods" and invite the
    customer to create a second one alongside the pod they are already paying
    for.
    """
    try:
        from agent.pod_sizing import POD_SIZES

        ctx = _cloud_ctx()
        if ctx is None:
            return create_error_response(
                request, 'NO_CLOUD',
                'Pods live in the cloud — sign in to see them')

        try:
            rows = _query_pod_rows(ctx)
        except Exception as e:
            logger.error(f'[pods] cloud read failed: {e}')
            return create_error_response(
                request, 'CLOUD_UNREACHABLE',
                f'Could not reach the fleet to list pods: {e}')

        pods = [_pod_view(row) for row in rows
                if isinstance(row, dict) and _is_customer_pod(row)]

        limits = _pod_limits()
        return create_success_response(request, {
            'pods': pods,
            'sizes': POD_SIZES,
            'limits': {**limits, 'used_pods': len(pods)},
        })
    except Exception as e:
        logger.error(f"Error listing pods: {e} {traceback.format_exc()}")
        return create_error_response(request, 'GET_PODS_ERROR', str(e))


@IPCHandlerRegistry.handler('save_pod')
def handle_save_pod(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Create or update a pod (upsert on id), in the cloud.

    Refuses rather than silently clamping: a customer who asked for four
    replicas and got one without being told would read the fleet as broken.
    """
    try:
        import uuid

        from agent.cloud_api.cloud_api import (
            send_add_vehicles_request_to_cloud, send_update_vehicles_decorated_to_cloud,
        )
        from agent.placement import normalize_requires
        from agent.pod_sizing import normalize_lifecycle, size_by_id

        params = params or {}
        name = str(params.get('name') or '').strip()
        if not name:
            return create_error_response(request, 'INVALID_PARAMS', 'name is required')

        ctx = _cloud_ctx()
        if ctx is None:
            return create_error_response(
                request, 'NO_CLOUD',
                'Pods live in the cloud — sign in to create one')

        pod_id = str(params.get('id') or '').strip()

        size = size_by_id(str(params.get('size_id') or '')) or {}
        cpu = params.get('cpu_cores', size.get('cpu'))
        memory_gb = params.get('memory_gb', size.get('memory_gb'))
        lifecycle = normalize_lifecycle(params.get('lifecycle'))
        replicas = max(1, int(params.get('desired_replicas') or 1))

        idle_minutes = params.get('idle_shutdown_minutes')
        if lifecycle != 'on_demand':
            # Meaningless on an always-on pod; storing it would show a shutdown
            # rule in the UI that nothing will ever apply.
            idle_minutes = None
        elif idle_minutes is not None:
            idle_minutes = max(1, int(idle_minutes))

        limits = _pod_limits()
        if not pod_id:
            try:
                rows = _query_pod_rows(ctx)
            except Exception as e:
                logger.error(f'[pods] cloud read failed during create: {e}')
                return create_error_response(
                    request, 'CLOUD_UNREACHABLE',
                    f'Could not reach the fleet to create a pod: {e}')
            current = len([r for r in rows if isinstance(r, dict) and _is_customer_pod(r)])
            if current + 1 > limits['max_pods']:
                return create_error_response(
                    request, 'POD_LIMIT_REACHED',
                    f"This account is limited to {limits['max_pods']} pods "
                    f"({current} already exist). The server enforces this limit.")

        desired = {
            'lifecycle': lifecycle,
            'idle_shutdown_minutes': idle_minutes,
            'desired_replicas': replicas,
        }

        fields: Dict[str, Any] = {
            'name': name,
            'vehicle_type': POD_VEHICLE_TYPE,
            'description': params.get('description') or '',
            'cpu_cores': int(cpu) if cpu is not None else None,
            'memory_gb': float(memory_gb) if memory_gb is not None else None,
            'capabilities': normalize_requires(params.get('capabilities')),
            'max_concurrent_tasks': int(params.get('max_concurrent_tasks')
                                        or size.get('concurrency') or 1),
            'environment': params.get('environment') or 'production',
            # Always written, whether or not the columns exist: it is what a
            # backend without them reads back, and what a backend with them
            # falls back to for rows written before the migration.
            'settings': {POD_SETTINGS_KEY: desired},
        }
        if _pod_columns_supported:
            fields.update(desired)

        try:
            if pod_id:
                result = send_update_vehicles_decorated_to_cloud(
                    ctx['session'], [{'id': pod_id, **fields}], ctx['token'], ctx['endpoint'])
            else:
                pod_id = f"pod_{uuid.uuid4().hex[:12]}"
                # A pod the customer just created has not been seen by the fleet
                # yet; saying offline is the truth until it registers itself.
                # owner is omitted on purpose: addVehicles resolves it from
                # the verified identity, and asserting it client-side is what
                # FORBIDDEN was about.
                result = send_add_vehicles_request_to_cloud(
                    ctx['session'],
                    [{'id': pod_id, 'status': 'offline', **fields}],
                    ctx['token'], ctx['endpoint'])
        except Exception as e:
            logger.error(f'[pods] cloud write failed: {e}')
            return create_error_response(request, 'SAVE_POD_ERROR', str(e))

        # addVehicles/updateVehicles report per-record success; a transport-level
        # success with success:false is still a failed save.
        failure = next((r for r in (result or []) if isinstance(r, dict)
                        and not r.get('success', True)), None)
        if failure:
            return create_error_response(
                request, 'SAVE_POD_ERROR', str(failure.get('error') or 'Failed to save pod'))

        logger.info(f"[pods] saved pod {pod_id} ({name}) lifecycle={lifecycle} "
                    f"replicas={replicas} columns={_pod_columns_supported}")
        return create_success_response(request, {
            'pod': _pod_view({'id': pod_id, 'status': 'offline', **fields}),
            'message': 'Pod saved',
        })
    except Exception as e:
        logger.error(f"Error saving pod: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SAVE_POD_ERROR', str(e))


@IPCHandlerRegistry.handler('delete_pod')
def handle_delete_pod(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete a pod.

    Deletes the desired state only. Anything the pod is currently running keeps
    running until the fleet reconciles it away, and turns it was holding are
    requeued by the server's reaper rather than lost.
    """
    try:
        from agent.cloud_api.cloud_api import send_remove_vehicles_request_to_cloud

        params = params or {}
        pod_id = str(params.get('id') or params.get('pod_id') or '').strip()
        if not pod_id:
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')

        ctx = _cloud_ctx()
        if ctx is None:
            return create_error_response(
                request, 'NO_CLOUD',
                'Pods live in the cloud — sign in to delete one')

        try:
            result = send_remove_vehicles_request_to_cloud(
                ctx['session'], [pod_id], ctx['token'], ctx['endpoint'])
        except Exception as e:
            logger.error(f'[pods] cloud delete failed: {e}')
            return create_error_response(request, 'DELETE_POD_ERROR', str(e))

        failure = next((r for r in (result or []) if isinstance(r, dict)
                        and not r.get('success', True)), None)
        if failure:
            return create_error_response(
                request, 'DELETE_POD_ERROR', str(failure.get('error') or 'Failed to delete pod'))

        logger.info(f"[pods] deleted pod {pod_id}")
        return create_success_response(request, {'id': pod_id, 'message': 'Pod deleted'})
    except Exception as e:
        logger.error(f"Error deleting pod: {e} {traceback.format_exc()}")
        return create_error_response(request, 'DELETE_POD_ERROR', str(e))


# ---------------------------------------------------------------------------
# ecbAccountManager, from the desktop
#
# Pods are not GraphQL: ecbAccountManager takes {action, input} over POST, and
# `pod_list`/`pod_save`/`pod_delete` write `fleet_pools` — the desired state the
# reconciler turns into a real Deployment.
#
# The web build calls it straight from the browser, which works because it is
# served from the cloud origin. The desktop cannot: its UI runs on
# http://localhost:3000 in dev and file:// when packaged, so the browser fetch
# is refused by CORS — and `file://` sends `Origin: null`, which no server
# allowlist can usefully admit. So the desktop makes the same call from here,
# where there is no origin to check and the session token already lives.
# ---------------------------------------------------------------------------

# An allowlist, not a passthrough: this is a local HTTP endpoint holding the
# user's bearer, and it should not become an open proxy to every action the
# account manager will ever grow.
_ACCOUNT_MANAGER_ACTIONS = frozenset({
    'pod_list', 'pod_save', 'pod_delete', 'fleet_status',
})


def _call_account_manager(action: str, payload: Dict[str, Any]):
    """POST one ecbAccountManager action as the signed-in user.

    Returns ``(status, data)``. Raises on configuration/credential problems so
    the caller can name them separately from a transport failure.
    """
    import json as _json
    import urllib.error
    import urllib.request

    from agent.cloud_api.turn_queue import _account_manager_url, _session_bearer_token

    url = _account_manager_url()
    token = _session_bearer_token()
    if not token:
        raise PermissionError('Not signed in — no session token available')

    body = _json.dumps({'action': action, 'input': payload or {}}).encode('utf-8')
    req = urllib.request.Request(
        url, data=body,
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {token}'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(262144).decode('utf-8', 'replace')
            status = resp.status
    except urllib.error.HTTPError as he:
        raw = he.read(65536).decode('utf-8', 'replace')
        status = he.code

    try:
        data = _json.loads(raw or '{}')
    except Exception:
        data = {'success': False, 'message': f'{action} returned non-JSON (HTTP {status})'}
    return status, data


@IPCHandlerRegistry.handler('account_manager_call')
def handle_account_manager_call(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Proxy one allowlisted ecbAccountManager action for the desktop UI.

    The response mirrors what the browser gets on the web build, so the two
    platforms return the same shape to the same caller. The server's own
    message is carried through untouched: the pod cap answers with the real
    number ("that would put this account at 6 pods; the limit is 5"), and a
    generic "failed" would throw away the only part the customer can act on.
    """
    from agent.cloud_api.turn_queue import TurnQueueNotConfigured

    params = params or {}
    action = str(params.get('action') or '').strip()
    if action not in _ACCOUNT_MANAGER_ACTIONS:
        return create_error_response(
            request, 'ACTION_NOT_ALLOWED',
            f"'{action}' is not an account-manager action this client may call")

    payload = params.get('input')
    if not isinstance(payload, dict):
        payload = {}

    try:
        status, data = _call_account_manager(action, payload)
    except TurnQueueNotConfigured as exc:
        return create_error_response(request, 'NOT_CONFIGURED', str(exc))
    except PermissionError as exc:
        return create_error_response(request, 'TOKEN_REQUIRED', str(exc))
    except Exception as exc:
        logger.warning(f'[account_manager] {action} transport error: {exc}')
        return create_error_response(request, 'NETWORK_ERROR', str(exc))

    if status == 401:
        return create_error_response(
            request, 'UNAUTHORIZED', f'The session was rejected by {action}; sign in again.')
    if status >= 400 or data.get('success') is False:
        return create_error_response(
            request,
            str(data.get('error') or f'HTTP_{status}'),
            str(data.get('message') or f'{action} failed'))

    return create_success_response(
        request, {k: v for k, v in data.items() if k != 'success'})


@IPCHandlerRegistry.handler('get_fleet_status')
def handle_get_fleet_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """What the fleet actually reports, as opposed to what was asked for.

    ``get_pods`` above returns desired state from the local row. This returns
    the server's view: which pods are **live**, what each is holding, and how
    deep the owner's queue is.

    Liveness is the server's ``live`` flag, not ``status``. A pod that dies
    keeps ``status='online'`` until the reaper notices — up to six minutes of
    showing a green pod that is gone — so rendering ``status`` would mean
    telling a customer their agent is being served by a machine that is not
    there.

    Authenticated as the user: the server derives the owner from the verified
    identity, so this can only ever show the caller's own fleet.
    """
    try:
        import json as _json
        import urllib.error
        import urllib.request

        from agent.cloud_api.turn_queue import (
            TurnQueueNotConfigured, _account_manager_url, _session_bearer_token,
        )

        try:
            url = _account_manager_url()
        except TurnQueueNotConfigured as exc:
            return create_error_response(request, 'NOT_CONFIGURED', str(exc))

        token = _session_bearer_token()
        if not token:
            return create_error_response(
                request, 'NO_TOKEN', 'Not signed in — no session token available')

        body = _json.dumps({
            'action': 'fleet_status',
            'input': {'include_all': bool((params or {}).get('include_all'))},
        }).encode('utf-8')
        req = urllib.request.Request(
            url, data=body,
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {token}'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read(262144).decode('utf-8', 'replace')
                status = resp.status
        except urllib.error.HTTPError as he:
            raw = he.read(8192).decode('utf-8', 'replace')
            status = he.code
        except Exception as exc:
            # A fleet view that cannot be fetched is not an error the customer
            # caused; the pod list still renders from desired state.
            logger.warning(f"[fleet_status] transport error: {exc}")
            return create_error_response(request, 'NETWORK_ERROR', str(exc))

        try:
            data = _json.loads(raw or '{}')
        except Exception:
            return create_error_response(
                request, 'BAD_RESPONSE', f'fleet_status returned non-JSON (HTTP {status})')

        if status == 401:
            return create_error_response(
                request, 'UNAUTHORIZED',
                'The session was rejected by fleet_status; sign in again.')
        if status >= 400 or not data.get('success'):
            return create_error_response(
                request, 'FLEET_STATUS_ERROR',
                str(data.get('message') or data.get('error') or f'HTTP {status}'))

        return create_success_response(request, {
            'vehicles': data.get('vehicles') or [],
            'liveVehicles': data.get('liveVehicles', 0),
            'hasLivePod': bool(data.get('hasLivePod')),
            'queue': data.get('queue') or {},
            'limits': data.get('limits') or {},
            'staleAfterSeconds': data.get('staleAfterSeconds'),
        })
    except Exception as e:
        logger.error(f"Error fetching fleet status: {e} {traceback.format_exc()}")
        return create_error_response(request, 'FLEET_STATUS_ERROR', str(e))
