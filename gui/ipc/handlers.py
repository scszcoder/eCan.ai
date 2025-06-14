"""
IPC 处理器实现模块
提供各种 IPC 请求的具体处理实现
"""

from typing import Any, Optional, Dict

from gui.LoginoutGUI import Login
from .types import IPCRequest, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper
import json
import uuid
import asyncio
from gui.ipc.tests import *
from .callable.manager import callable_manager

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
    sender = next((ag for ag in py_login.main_win.agents if chat['sender'] == ag.card.name), None)
    return sender


def find_recipient(py_login, chat):
    recipient = next((ag for ag in py_login.main_win.agents if chat['recipient'] == ag.card.name), None)
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
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]], py_login: Login) -> str:
    """处理登录请求
    
    验证用户凭据并返回访问令牌。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}")
        
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

        # 获取用户名和密码
        username = data['username']

        agents = py_login.main_win.agents

        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Get all successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'agents': agents,
            'message': 'Get all successful'
        }))

    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
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
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        agents = py_login.main_win.agents

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        return json.dumps(create_success_response(request, {
            'token': token,
            'agents': agents,
            'message': 'Login successful'
        }))

    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)} "
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

        # 简单的密码验证
        if password == 'admin123#':
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

        # 简单的密码验证
        if username == 'admin123#':
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

        # 简单的密码验证
        if username == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Get vehicles successful'
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

        # 简单的密码验证
        if username == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Get tools successful'
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


@IPCHandlerRegistry.handler('get_chats')
def handle_get_chats(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
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

        # 简单的密码验证
        if username == 'admin123#':
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



@IPCHandlerRegistry.handler('send_chat')
def handle_send_chat(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
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
        is_valid, data, error = validate_params(params, [])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        chat = data[0]
        sender_agent = find_sender(py_login, chat)
        recipient_agent = find_recipient(py_login,chat)
        if sender_agent and recipient_agent:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In this case, you can't call loop.run_until_complete directly in the main thread.
                # Workaround: Use "asyncio.run_coroutine_threadsafe" (if in a thread) or refactor to be async.
                # Example (if in a thread):
                future = asyncio.run_coroutine_threadsafe(sender_agent.a2a_send_chat_message(recipient_agent, {"chat": chat}), loop)
                result = future.result()
            else:
                result = loop.run_until_complete(sender_agent.a2a_send_message(recipient_agent, {"chat": chat}))
            result_message = json.dumps({"send_chat_response": result})

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
        logger.debug(f"Login handler called with request: {request}, params: {params}")
        print("save agents:", params)
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


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Login successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Get agents successful'
        }))

    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
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

@IPCHandlerRegistry.handler('get_callables')
def handle_get_callables(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理获取可调用函数列表请求

    获取系统中所有可调用函数列表，支持按文本内容（函数名、描述、参数等）和类型过滤。

    Args:
        request: IPC 请求对象
        params: 请求参数，可选包含：
            - text: 文本过滤条件，会搜索函数名、描述和参数
            - type: 类型过滤条件（'system' 或 'custom'）

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get callables handler called with request: {request}")

        # 使用 CallableManager 获取过滤后的可调用函数列表
        filtered_callables = callable_manager.get_callables(params)
        logger.debug(f"Filtered callables count: {len(filtered_callables)}")

        response = create_success_response(request, {
            'data': filtered_callables,
            'message': 'Get callables successful'
        })
        # logger.debug(f"Response: {response}")
        return json.dumps(response)

    except Exception as e:
        logger.error(f"Error in get callables handler: {e}")
        return json.dumps(create_error_response(
            request,
            'GET_CALLABLES_ERROR',
            f"Error getting callables: {str(e)}"
        ))

# 打印所有已注册的处理器
logger.info(f"Registered handlers: {IPCHandlerRegistry.list_handlers()}")