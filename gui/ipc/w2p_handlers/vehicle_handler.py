import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from app_context import AppContext
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from bot.vehicles import VEHICLE

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_vehicles')
def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """获取所有 vehicles 列表

    Args:
        request: IPC 请求对象
        params: 请求参数

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get vehicles handler called with request: {request}")
        main_window = AppContext.get_main_window()
        vehicles = main_window.vehicles

        logger.info(f"get vehicles successful")
        resultJS = {
            'vehicles': [v.to_dict() for v in vehicles],
            'message': 'Get all successful'
        }
        logger.debug('get vehicles resultJS:' + str(resultJS))
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
    """更新 vehicle 状态

    Args:
        request: IPC 请求对象
        params: 请求参数
            - vehicle_id: int - Vehicle ID
            - status: str - 新状态 (active/offline/maintenance)

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        vehicle_id = params.get('vehicle_id')
        new_status = params.get('status')
        
        if not vehicle_id or not new_status:
            return create_error_response(request, 'INVALID_PARAMS', 'vehicle_id and status are required')
        
        main_window = AppContext.get_main_window()
        vehicle = next((v for v in main_window.vehicles if str(v.id) == str(vehicle_id)), None)
        
        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')
        
        # 状态映射：前端 active -> 后端 online
        status_map = {'active': 'online', 'offline': 'offline', 'maintenance': 'maintenance'}
        backend_status = status_map.get(new_status, new_status)
        
        vehicle.setStatus(backend_status)
        main_window.saveVehicle(vehicle)
        
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
    """添加新的 vehicle

    Args:
        request: IPC 请求对象
        params: 请求参数
            - name: str - 设备名称
            - ip: str - IP 地址
            - os: str - 操作系统
            - arch: str - 系统架构

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        name = params.get('name')
        ip = params.get('ip', '0.0.0.0')
        
        if not name:
            return create_error_response(request, 'INVALID_PARAMS', 'name is required')
        
        main_window = AppContext.get_main_window()
        
        # 检查是否已存在同名或同IP的vehicle
        existing = next((v for v in main_window.vehicles if v.getName() == name or v.getIP() == ip), None)
        if existing:
            return create_error_response(request, 'VEHICLE_EXISTS', f'Vehicle with name {name} or ip {ip} already exists')
        
        # 创建新vehicle
        new_vehicle = VEHICLE(main_window, name=name, ip=ip)
        new_vehicle.setOS(params.get('os', main_window.os_short))
        new_vehicle.setArch(params.get('arch', ''))
        new_vehicle.setStatus(params.get('status', 'offline'))
        new_vehicle.setFunctions(params.get('functions', ''))
        new_vehicle.setTestDisabled(params.get('test_disabled', False))
        
        # 生成ID
        new_vehicle.setVid(len(main_window.vehicles) + 1)
        
        main_window.vehicles.append(new_vehicle)
        main_window.saveVehicle(new_vehicle)
        main_window.saveVehiclesJsonFile()
        
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
    """更新 vehicle 信息

    Args:
        request: IPC 请求对象
        params: 请求参数
            - vehicle_id: int - Vehicle ID
            - name: str - 设备名称
            - ip: str - IP 地址
            - status: str - 状态
            - ... 其他字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        vehicle_id = params.get('vehicle_id')
        
        if not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'vehicle_id is required')
        
        main_window = AppContext.get_main_window()
        vehicle = next((v for v in main_window.vehicles if str(v.id) == str(vehicle_id)), None)
        
        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')
        
        # 更新字段
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
        
        main_window.saveVehicle(vehicle)
        main_window.saveVehiclesJsonFile()
        
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
    """删除 vehicle

    Args:
        request: IPC 请求对象
        params: 请求参数
            - vehicle_id: int - Vehicle ID

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        vehicle_id = params.get('vehicle_id')
        
        if not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'vehicle_id is required')
        
        main_window = AppContext.get_main_window()
        vehicle = next((v for v in main_window.vehicles if str(v.id) == str(vehicle_id)), None)
        
        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')
        
        # 检查是否有关联的bots
        if len(vehicle.getBotIds()) > 0:
            return create_error_response(
                request, 
                'VEHICLE_HAS_BOTS', 
                f'Cannot delete vehicle with {len(vehicle.getBotIds())} assigned bots'
            )
        
        main_window.vehicles.remove(vehicle)
        main_window.saveVehiclesJsonFile()
        
        # 从数据库删除（如果是Commander角色）
        if hasattr(main_window, 'vehicle_service') and main_window.vehicle_service:
            try:
                db_vehicle = main_window.vehicle_service.find_vehicle_by_name(vehicle.getName())
                if db_vehicle:
                    main_window.vehicle_service.session.delete(db_vehicle)
                    main_window.vehicle_service.session.commit()
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
    """将 bot 分配到指定 vehicle

    Args:
        request: IPC 请求对象
        params: 请求参数
            - bot_id: str - Bot ID
            - vehicle_id: int - Vehicle ID

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        bot_id = params.get('bot_id')
        vehicle_id = params.get('vehicle_id')
        
        if not bot_id or not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'bot_id and vehicle_id are required')
        
        main_window = AppContext.get_main_window()
        vehicle = next((v for v in main_window.vehicles if str(v.id) == str(vehicle_id)), None)
        
        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')
        
        # 检查容量
        if vehicle.getBotsOverCapStatus():
            return create_error_response(
                request, 
                'VEHICLE_FULL', 
                f'Vehicle is at capacity ({vehicle.CAP} bots)'
            )
        
        # 添加bot
        added = vehicle.addBot(bot_id)
        if added == 0:
            return create_error_response(request, 'BOT_ALREADY_ASSIGNED', f'Bot {bot_id} already assigned to this vehicle')
        
        main_window.saveVehicle(vehicle)
        main_window.saveVehiclesJsonFile()
        
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
    """从 vehicle 移除 bot

    Args:
        request: IPC 请求对象
        params: 请求参数
            - bot_id: str - Bot ID
            - vehicle_id: int - Vehicle ID

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        bot_id = params.get('bot_id')
        vehicle_id = params.get('vehicle_id')
        
        if not bot_id or not vehicle_id:
            return create_error_response(request, 'INVALID_PARAMS', 'bot_id and vehicle_id are required')
        
        main_window = AppContext.get_main_window()
        vehicle = next((v for v in main_window.vehicles if str(v.id) == str(vehicle_id)), None)
        
        if not vehicle:
            return create_error_response(request, 'VEHICLE_NOT_FOUND', f'Vehicle {vehicle_id} not found')
        
        # 移除bot
        removed = vehicle.removeBot(bot_id)
        if removed == 0:
            return create_error_response(request, 'BOT_NOT_FOUND', f'Bot {bot_id} not assigned to this vehicle')
        
        main_window.saveVehicle(vehicle)
        main_window.saveVehiclesJsonFile()
        
        logger.info(f"Removed bot {bot_id} from vehicle {vehicle_id}")
        return create_success_response(request, {
            'vehicle': vehicle.to_dict(),
            'message': 'Bot removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing bot from vehicle: {e} {traceback.format_exc()}")
        return create_error_response(request, 'REMOVE_BOT_ERROR', str(e))