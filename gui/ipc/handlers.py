"""
IPC 处理器实现模块
提供各种 IPC 请求的具体处理实现
"""

from typing import Any, Optional, Dict

import utils.logger_helper
from .types import IPCRequest, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper
import json
import uuid
import asyncio
from utils.logger_helper import *
from gui.ipc.tests import *
import traceback

logger = logger_helper.logger

def validate_params(params: Optional[Dict[str, Any]], required: list[str]) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """验证请求参数
    
    Args:
        params: 请求参数
        required: 必需参数列表
        
    Returns:
        tuple[bool, Optional[Dict[str, Any]], Optional[str]]: (是否有效, 参数数据, 错误信息)
    """
    if not params:
        return False, None, f"Missing required parameters: {', '.join(required)}"
    
    missing = [param for param in required if param not in params]
    if missing:
        return False, None, f"Missing required parameters: {', '.join(missing)}"
    
    return True, params, None

def find_sender(py_login, chat):
    sender = next((ag for ag in py_login.main_win.agents if "My Twin Agent" == ag.card.name), None)
    return sender


def find_recipient(py_login, chat):
    print("finding recipient for chat:", chat)
    chat_id = chat['chat_id']
    recipient = next((ag for ag in py_login.main_win.agents if "Engineering Procurement Agent" == ag.card.name), None)
    print("recipient found:", recipient.card.name)
    return recipient

@IPCHandlerRegistry.handler('get_config')
def handle_get_config(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理获取配置请求
    
    从配置存储中获取指定键的配置值。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'key' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        # 验证参数
        is_valid, data, error = validate_params(params, ['key'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get_config: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        
        # 获取配置
        key = data['key']
        # TODO: 实现实际的配置获取逻辑
        config_value = {'key': key, 'value': 'Config value'}
        
        logger.info(f"Config retrieved: {key}")
        return json.dumps(create_success_response(request, config_value))
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return json.dumps(create_error_response(
            request,
            'CONFIG_ERROR',
            f"Error getting config: {str(e)}"
        ))

@IPCHandlerRegistry.handler('set_config')
def handle_set_config(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理设置配置请求
    
    将配置值保存到配置存储中。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'key' 和 'value' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        # 验证参数
        is_valid, data, error = validate_params(params, ['key', 'value'])
        if not is_valid:
            logger.warning(f"Invalid parameters for set_config: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        
        # 设置配置
        key = data['key']
        value = data['value']
        # TODO: 实现实际的配置设置逻辑
        
        logger.info(f"Config set: {key} = {value}")
        return json.dumps(create_success_response(request, {'success': True}))
    except Exception as e:
        logger.error(f"Error setting config: {e}")
        return json.dumps(create_error_response(
            request,
            'CONFIG_ERROR',
            f"Error setting config: {str(e)}"
        ))

@IPCHandlerRegistry.handler('login')
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求
    
    验证用户凭据并返回访问令牌。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")
        
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        
        # 获取用户名和密码
        username = data['username']
        password = data['password']
        machine_role = data['machine_role']
        print("user name:", username, "password:", password, "machine_role:", machine_role)
        result = py_login.handleLogin(username, password, machine_role)
        # 简单的密码验证
        if result == 'Successful':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))

@IPCHandlerRegistry.handler('get_last_login')
def handle_get_last_login(request: IPCRequest, params: Optional[Any], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get Last Login handler called with request: {request}, params: {params}")

        # 验证参数
        result = py_login.handleGetLastLogin()

        # 生成Response
        logger.info(f"Get Last Login Info successful.")
        return json.dumps(create_success_response(request, {
            'last_login': result,
            'message': 'Get Last Login successful'
        }))

    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_all')
def handle_get_all(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get all called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        print("user name:", data['username'])
        # 获取用户名和密码
        username = data['username']

        agents = py_login.main_win.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)

        skills = py_login.main_win.agent_skills
        vehicles = py_login.main_win.vehicles
        settings = py_login.main_win.general_settings
        # knowledges = py_login.main_win.knowledges
        # chats = py_login.main_win.chats
        knowledges = {}
        chats = {}
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Get all successful for user: {username}")
        resultJS = {
            'token': token,
            'agents': [agent.to_dict() for agent in agents],
            'skills': [sk.to_dict() for sk in skills],
            'tools': [tool.model_dump() for tool in py_login.main_win.mcp_tools_schemas],
            'tasks': [task.to_dict() for task in all_tasks],
            'vehicles': [vehicle.genJson() for vehicle in vehicles],
            'settings': settings,
            'knowledges': knowledges,
            'chats': chats,
            'message': 'Get all successful'
        }
        print('resultJS:', resultJS)
        return json.dumps(create_success_response(request, resultJS))

    except Exception as e:
        logger.error(f"Error in get all handler: {e} {traceback.format_exc()}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get all: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_agents')
def handle_get_agents(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get agents handler called with request: {request}, params: {params}")
        print("get agents:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get agents: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        agents = py_login.main_win.agents

        # 简单的密码验证
        # 生成随机令牌
        username = data['username']
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get agents successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'agents': [agent.to_dict() for agent in agents],
            'message': 'get agents successful'
        }))

    except Exception as e:
        logger.error(f"Error in get agents handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get agents: {str(e)} "
        ))



@IPCHandlerRegistry.handler('get_skills')
def handle_get_skills(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get skills handler called with request: {request}, params: {params}")
        skills = py_login.main_win.agent_skills
        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get skills: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        username = data['username']
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get skills successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'skills': [sk.to_dict() for sk in skills],
            'message': 'get skills successful'
        }))

    except Exception as e:
        logger.error(f"Error in get skills handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get skills: {str(e)}"
        ))



@IPCHandlerRegistry.handler('get_tasks')
def handle_get_tasks(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get tasks handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get tasks: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        agents = py_login.main_win.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)
        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Get tasks successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'tasks': [task.to_dict() for task in all_tasks],
            'message': 'get tasks successful'
        }))

    except Exception as e:
        logger.error(f"Error in get tasks handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get tasks: {str(e)}"
        ))



@IPCHandlerRegistry.handler('get_vehicles')
def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get vehicles handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get vehicles: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Get vehicles successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'vehicles': [vehicle.genJson() for vehicle in py_login.main_win.vehicles],
            'message': 'Get vehicles successful'
        }))

    except Exception as e:
        logger.error(f"Error in get vehicles handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get vehicles: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_tools')
def handle_get_tools(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get tools handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get tools: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get tools successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'tools_schemas': py_login.main_win.mcp_tools_schemas,
            'message': 'Get tools successful'
        }))

    except Exception as e:
        logger.error(f"Error in get tools handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get tools: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_chats')
async def handle_get_chats(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"get chats handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get chats: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get chats successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'get chats successful'
        }))

    except Exception as e:
        logger.error(f"Error in get chats handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get chats: {str(e)}"
        ))



@IPCHandlerRegistry.handler('send_chat')
async def handle_send_chat(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理Chat

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: chat message data structure

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"send chat handler called with request: {request}, params: {params}")

        # 验证参数
        # is_valid, data, error = validate_params(params, [])
        # if not is_valid:
        #     logger.warning(f"Invalid parameters for login: {error}")
        #     return json.dumps(create_error_response(
        #         request,
        #         'INVALID_PARAMS',
        #         error
        #     ))

        # 获取用户名和密码
        chat = params
        sender_agent = find_sender(py_login, chat)
        recipient_agent = find_recipient(py_login,chat)
        if sender_agent and recipient_agent:
            # send message to twin agent and let it handle the message from there.
            agent_wait_response = await sender_agent.runner.chat_wait_in_line(request)
            result_message = json.dumps({"send_chat_response": agent_wait_response})

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"sending a chat: {chat['content']}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': result_message
        }))

    except Exception as e:
        logger.error(f"Error in send chat handler: {e}")
        return json.dumps(create_error_response(
            request,
            'SEND_CHAT_ERROR',
            f"Error during send chat: {str(e)}"
        ))

@IPCHandlerRegistry.handler('save_agents')
def handle_save_agents(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save agents handler called with request: {request}, params: {params}")
        print("save agents:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save agents: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save agents successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Save agents successful'
        }))

    except Exception as e:
        logger.error(f"Error in save agents handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save agents: {str(e)}"
        ))



@IPCHandlerRegistry.handler('save_skills')
def handle_save_skills(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save skills handler called with request: {request}, params: {params}")
        print("save skills:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save skills: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save skills successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Save skills successful'
        }))

    except Exception as e:
        logger.error(f"Error in save skills handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save skills: {str(e)}"
        ))


@IPCHandlerRegistry.handler('save_settings')
def handle_save_settings(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save settings handler called with request: {request}, params: {params}")
        print("save settings:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save settings: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save settings successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Save settings successful'
        }))

    except Exception as e:
        logger.error(f"Error in save settings handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save settings: {str(e)}"
        ))



@IPCHandlerRegistry.handler('save_tasks')
def handle_save_tasks(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save tasks handler called with request: {request}, params: {params}")
        print("save agents:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save tasks: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save tasks successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Save tasks successful'
        }))

    except Exception as e:
        logger.error(f"Error in save tasks handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save tasks: {str(e)}"
        ))



@IPCHandlerRegistry.handler('save_all')
def handle_save_all(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save all handler called with request: {request}, params: {params}")
        print("save all:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save all: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save all successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Save all successful'
        }))

    except Exception as e:
        logger.error(f"Error in save all handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save all: {str(e)}"
        ))

@IPCHandlerRegistry.handler('get_available_tests')
def handle_get_available_tests(request: IPCRequest, params: Optional[Any], py_login:Any) -> str:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get available tests handler called with request: {request}, params: {params}")
        print("get available tests:", params)


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        return json.dumps(create_success_response(request, {
            'token': token,
            "tests": ["test1", "test2", "test3"],
            'message': 'Get available tests successful'
        }))

    except Exception as e:
        logger.error(f"Error in get available tests handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get available tests: {str(e)}"
        ))


@IPCHandlerRegistry.handler('run_tests')
def handle_run_tests(request: IPCRequest, params: Optional[Any], py_login: Any) -> str:
    """处理跑测试请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Run tests handler called with request: {request}, params: {params}")
        print("run tests:", params)

        tests = params.get('tests', [])

        results = []
        top_web_gui = get_top_web_gui()
        for test in tests:
            test_id = test.get('test_id')
            test_args = test.get('args', {})

            # Process each test with its arguments
            if test_id == 'default_test':
                result = run_default_tests(top_web_gui, py_login.main_win)
            # Add other test cases as needed
            else:
                result = {"status": "error", "message": f"Unknown test: {test_id}"}

            results.append({
                "test_id": test_id,
                "result": result
            })

        return json.dumps(create_success_response(request, {
            'results': results,
            'message': 'Tests executed successfully'
        }))

    except Exception as e:
        logger.error(f"Error in run tests handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during run tests: {str(e)}"
        ))


@IPCHandlerRegistry.handler('stop_tests')
def handle_stop_tests(request: IPCRequest, params: Optional[Any], py_login: Any) -> str:
    """处理停止测试项请求

    Args:
        request: IPC 请求对象
        params: 测试项

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Stop tests handler called with request: {request}, params: {params}")
        print("stop tests:", params)

        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        return json.dumps(create_success_response(request, {
            'token': token,
            "tests": ["test1", "test2", "test3"],
            'message': 'Stop tests successful'
        }))

    except Exception as e:
        logger.error(f"Error in stop tests handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during stop tests: {str(e)}"
        ))


# 打印所有已注册的处理器
logger.info(f"Registered handlers: {IPCHandlerRegistry.list_handlers()}")