import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from agent.vehicles.vehicles import VEHICLE

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_vehicles')
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
        vehicle = next((v for v in ctx.get_vehicles() if str(v.id) == str(vehicle_id)), None)

        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')

        # Status mapping: frontend active -> backend online
        status_map = {'active': 'online', 'offline': 'offline', 'maintenance': 'maintenance'}
        backend_status = status_map.get(new_status, new_status)

        vehicle.setStatus(backend_status)
        ctx.main_window.saveVehicle(vehicle)

        logger.info(f"Updated vehicle {vehicle_id} status to {backend_status}")
        return create_success_response(request, {
            'vehicle': vehicle.to_dict(),
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
# + vehicles JSON). A pod is not a discovered machine: it is a row in
# agent_vehicles with vehicle_type='cloud' that the fleet scheduler places work
# on. These handlers therefore go to the DB service, and deliberately leave the
# machine handlers alone.
#
# Desired state (lifecycle, desired_replicas) is what the customer sets;
# observed state (status, last_heartbeat, health_score) is what the fleet
# reports. Both are returned, never merged — a customer raising replicas should
# watch it converge, not be told it already happened.
# ===========================================================================

POD_VEHICLE_TYPE = 'cloud'


def _pod_service(request, params):
    """The vehicle DB service, or None (with the reason logged)."""
    try:
        from gui.ipc.context_bridge import get_ec_db_mgr

        ec_db_mgr = get_ec_db_mgr(request, params)
        service = getattr(ec_db_mgr, 'vehicle_service', None)
        if service is None:
            logger.warning('[pods] vehicle_service is not available on ec_db_mgr')
        return service
    except Exception as e:
        logger.warning(f'[pods] could not reach the vehicle service: {e}')
        return None


def _pod_view(row: Dict[str, Any]) -> Dict[str, Any]:
    """One pod as the GUI needs it: desired state, observed state, and cost."""
    from agent.pod_sizing import estimate_pod_cost, normalize_lifecycle

    cpu = row.get('cpu_cores') or 0
    memory_gb = row.get('memory_gb') or 0
    lifecycle = normalize_lifecycle(row.get('lifecycle'))
    replicas = int(row.get('desired_replicas') or 1)

    return {
        **row,
        'lifecycle': lifecycle,
        'desired_replicas': replicas,
        'idle_shutdown_minutes': row.get('idle_shutdown_minutes'),
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
    """List this owner's pods, with sizes, costs and the caps that apply."""
    try:
        from agent.pod_sizing import POD_SIZES

        service = _pod_service(request, params)
        pods = []
        if service is not None:
            result = service.query_vehicles()
            rows = result.get('data', []) if isinstance(result, dict) and result.get('success') else []
            pods = [
                _pod_view(row) for row in rows
                if isinstance(row, dict) and row.get('vehicle_type') == POD_VEHICLE_TYPE
            ]

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
    """Create or update a pod (upsert on id).

    Refuses rather than silently clamping: a customer who asked for four
    replicas and got one without being told would read the fleet as broken.
    """
    try:
        import uuid

        from agent.placement import normalize_requires
        from agent.pod_sizing import normalize_lifecycle, size_by_id
        from gui.ipc.context_bridge import get_username

        params = params or {}
        name = str(params.get('name') or '').strip()
        if not name:
            return create_error_response(request, 'INVALID_PARAMS', 'name is required')

        service = _pod_service(request, params)
        if service is None:
            return create_error_response(
                request, 'NO_DB', 'The vehicle store is not available on this instance')

        pod_id = str(params.get('id') or '').strip()
        owner = str(params.get('owner') or get_username(request, params) or '')

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
            existing = service.query_vehicles()
            rows = existing.get('data', []) if isinstance(existing, dict) and existing.get('success') else []
            current = len([r for r in rows if isinstance(r, dict) and r.get('vehicle_type') == POD_VEHICLE_TYPE])
            if current + 1 > limits['max_pods']:
                return create_error_response(
                    request, 'POD_LIMIT_REACHED',
                    f"This account is limited to {limits['max_pods']} pods "
                    f"({current} already exist). The server enforces this limit.")

        fields: Dict[str, Any] = {
            'name': name,
            'owner': owner,
            'vehicle_type': POD_VEHICLE_TYPE,
            'description': params.get('description') or '',
            'cpu_cores': int(cpu) if cpu is not None else None,
            'memory_gb': float(memory_gb) if memory_gb is not None else None,
            'capabilities': normalize_requires(params.get('capabilities')),
            'max_concurrent_tasks': int(params.get('max_concurrent_tasks')
                                        or size.get('concurrency') or 1),
            'lifecycle': lifecycle,
            'idle_shutdown_minutes': idle_minutes,
            'desired_replicas': replicas,
            'environment': params.get('environment') or 'production',
        }

        if pod_id:
            result = service.update_vehicle(pod_id, fields)
        else:
            pod_id = f"pod_{uuid.uuid4().hex[:12]}"
            # A pod the customer just created has not been seen by the fleet
            # yet; saying offline is the truth until it registers itself.
            result = service.add_vehicle({'id': pod_id, 'status': 'offline', **fields})

        if isinstance(result, dict) and not result.get('success', True):
            return create_error_response(
                request, 'SAVE_POD_ERROR', str(result.get('error') or 'Failed to save pod'))

        logger.info(f"[pods] saved pod {pod_id} ({name}) lifecycle={lifecycle} replicas={replicas}")
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
        params = params or {}
        pod_id = str(params.get('id') or params.get('pod_id') or '').strip()
        if not pod_id:
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')

        service = _pod_service(request, params)
        if service is None:
            return create_error_response(
                request, 'NO_DB', 'The vehicle store is not available on this instance')

        result = service.delete_vehicle(pod_id)
        if isinstance(result, dict) and not result.get('success', True):
            return create_error_response(
                request, 'DELETE_POD_ERROR', str(result.get('error') or 'Failed to delete pod'))

        logger.info(f"[pods] deleted pod {pod_id}")
        return create_success_response(request, {'id': pod_id, 'message': 'Pod deleted'})
    except Exception as e:
        logger.error(f"Error deleting pod: {e} {traceback.format_exc()}")
        return create_error_response(request, 'DELETE_POD_ERROR', str(e))
