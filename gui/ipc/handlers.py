"""
IPC 处理器实现模块
提供各种 IPC 请求的具体处理实现
"""

from typing import Any, Optional, Dict

from gui.LoginoutGUI import Login
from .types import IPCRequest, IPCResponse, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger
import uuid
import traceback


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


@IPCHandlerRegistry.handler('get_all')
def handle_get_all(request: IPCRequest, params: Optional[Dict[str, Any]], py_login: Login) -> IPCResponse:
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
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        logger.debug("user name:" + data['username'])
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
        logger.debug('get all resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get all handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get all: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_vehicles')
def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> IPCResponse:
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
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get vehicles: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Get vehicles successful for user: {username}")
        vehicles = py_login.main_win.vehicles

        resultJS = {
            'token': token,
            'vehicles': [vehicle.genJson() for vehicle in vehicles],
            'message': 'Get all successful'
        }
        logger.debug('get vehicles resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get vehicles handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get vehicles: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_knowledges')
def handle_get_knowledges(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> IPCResponse:
    """处理获取知识库请求
    
    从知识库中获取条目。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，可以包含过滤条件
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        # 伪造一个知识库条目列表
        knowledges = [
            {'id': 'k1', 'title': 'How to setup environment', 'content': '...'},
            {'id': 'k2', 'title': 'Troubleshooting guide', 'content': '...'}
        ]
        
        logger.info("Knowledge base retrieved")
        return create_success_response(request, knowledges)
    except Exception as e:
        logger.error(f"Error getting knowledges: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'KNOWLEDGE_ERROR',
            f"Error getting knowledges: {str(e)}"
        )


@IPCHandlerRegistry.handler('save_all')
def handle_save_all(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> IPCResponse:
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
        logger.debug("save all:" + str(params))
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save all: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save all successful for user: {username}")
        return create_success_response(request, {
            'token': token,
            'message': 'Save all successful'
        })

    except Exception as e:
        logger.error(f"Error in save all handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save all: {str(e)}"
        )

@IPCHandlerRegistry.handler('get_available_tests')
def handle_get_available_tests(request: IPCRequest, params: Optional[Any], py_login:Any) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get available tests handler called with request: {request}, params: {params}")

        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        return create_success_response(request, {
            'token': token,
            "tests": ["test1", "test2", "test3"],
            'message': 'Get available tests successful'
        })

    except Exception as e:
        logger.error(f"Error in get available tests handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get available tests: {str(e)}"
        )


@IPCHandlerRegistry.handler('run_tests')
def handle_run_tests(request: IPCRequest, params: Optional[Any], py_login: Any) -> IPCResponse:
    """处理跑测试请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Run tests handler called with request: {request}, params: {params}")
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

        return create_success_response(request, {
            'results': results,
            'message': 'Tests executed successfully'
        })

    except Exception as e:
        logger.error(f"Error in run tests handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during run tests: {str(e)}"
        )


@IPCHandlerRegistry.handler('stop_tests')
def handle_stop_tests(request: IPCRequest, params: Optional[Any], py_login: Any) -> IPCResponse:
    """处理停止测试项请求

    Args:
        request: IPC 请求对象
        params: 测试项

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Stop tests handler called with request: {request}, params: {params}")

        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        return create_success_response(request, {
            'token': token,
            "tests": ["test1", "test2", "test3"],
            'message': 'Stop tests successful'
        })

    except Exception as e:
        logger.error(f"Error in stop tests handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during stop tests: {str(e)}"
        )

# 打印所有已注册的处理器
logger.info(f"Registered handlers: {IPCHandlerRegistry.list_handlers()}")