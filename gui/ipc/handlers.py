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
from app_context import AppContext
import asyncio
from agent.ec_skills.dev_utils.skill_dev_utils import *

# Optional import for TaskRunnerRegistry to discover queues; guarded to avoid import issues
try:
    from agent.tasks import TaskRunnerRegistry  # type: ignore
except Exception:
    TaskRunnerRegistry = None  # type: ignore

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
def handle_get_all(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get all called with request: {request}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get all: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        logger.debug("user name:" + data['username'])
        # 获取用户名和密码
        username = data['username']

        main_window = AppContext.get_main_window()
        agents = main_window.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)

        skills = main_window.agent_skills
        vehicles = main_window.vehicles
        organizations = main_window.organizations
        titles = main_window.titles
        ranks = main_window.ranks
        personalities = main_window.personalities
        settings = main_window.config_manager.general_settings.data
        # knowledges = login.main_win.knowledges
        # chats = login.main_win.chats
        knowledges = {}
        chats = {}
        logger.info(f"Get all successful for user: {username}")
        resultJS = {
            'agents': [agent.to_dict() for agent in agents],
            'skills': [sk.to_dict() for sk in skills],
            'tools': [tool.model_dump() for tool in main_window.mcp_tools_schemas],
            'tasks': [task.to_dict() for task in all_tasks],
            'vehicles': [vehicle.genJson() for vehicle in vehicles],
            'settings': settings,
            'knowledges': knowledges,
            'chats': chats,
            'message': 'Get all successful'
        }
        resultJS_str = str(resultJS)
        truncated_resultJS = resultJS_str[:800] + "..." if len(resultJS_str) > 500 else resultJS_str
        logger.debug('get all resultJS:' + truncated_resultJS)
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get all handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get all: {str(e)}"
        )


# @IPCHandlerRegistry.handler('get_vehicles')
# def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
#     """处理登录请求

#     验证用户凭据并返回访问令牌。

#     Args:
#         request: IPC 请求对象
#         params: 请求参数，必须包含 'username' 和 'password' 字段

#     Returns:
#         str: JSON 格式的响应消息
#     """
#     try:
#         logger.debug(f"Get vehicles handler called with request: {request}")

#         # 验证参数
#         is_valid, data, error = validate_params(params, ['username'])
#         if not is_valid:
#             logger.warning(f"Invalid parameters for get vehicles: {error}")
#             return create_error_response(
#                 request,
#                 'INVALID_PARAMS',
#                 error
#             )

#         # 获取用户名和密码
#         username = data['username']

#         # 简单的密码验证
#         # 生成随机令牌
#         token = str(uuid.uuid4()).replace('-', '')
#         logger.info(f"Get vehicles successful for user: {username}")
#         login:Login = AppContext.login
#         vehicles = login.main_win.vehicles

#         resultJS = {
#             'token': token,
#             'vehicles': [vehicle.genJson() for vehicle in vehicles],
#             'message': 'Get all successful'
#         }
#         logger.debug('get vehicles resultJS:' + str(resultJS))
#         return create_success_response(request, resultJS)

#     except Exception as e:
#         logger.error(f"Error in get vehicles handler: {e} {traceback.format_exc()}")
#         return create_error_response(
#             request,
#             'LOGIN_ERROR',
#             f"Error during get vehicles: {str(e)}"
#         )


# @IPCHandlerRegistry.handler('get_knowledges')
# def handle_get_knowledges(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
#     """处理获取知识库请求
    
#     从知识库中获取条目。
    
#     Args:
#         request: IPC 请求对象
#         params: 请求参数，可以包含过滤条件
        
#     Returns:
#         str: JSON 格式的响应消息
#     """
#     try:
#         # 伪造一个知识库条目列表
#         knowledges = [
#             {'id': 'k1', 'title': 'How to setup environment', 'content': '...'},
#             {'id': 'k2', 'title': 'Troubleshooting guide', 'content': '...'}
#         ]
        
#         logger.info("Knowledge base retrieved")
#         return create_success_response(request, knowledges)
#     except Exception as e:
#         logger.error(f"Error getting knowledges: {e} {traceback.format_exc()}")
#         return create_error_response(
#             request,
#             'KNOWLEDGE_ERROR',
#             f"Error getting knowledges: {str(e)}"
#         )


@IPCHandlerRegistry.handler('save_all')
def handle_save_all(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save all handler called with request: {request}")

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


        logger.info(f"save all successful for user: {username}")
        return create_success_response(request, {
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
def handle_get_available_tests(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get available tests handler called with request: {request}")

        return create_success_response(request, {
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


@IPCHandlerRegistry.handler('run_skill')
def handle_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get start skill run handler called with request: {request}")

        main_window = AppContext.get_main_window()
        skill = request.meta["skill_flowgram"]
        results = run_dev_skill(main_window, skill)
        return create_success_response(request, {
            "results": results,
            'message': "Start skill run successful" if results["success"] else "Start skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in run skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during start skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('cancel_run_skill')
def handle_cancel_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get cancel skill run called with request: {request}")

        main_window = AppContext.get_main_window()
        results = cancel_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "Cancelling skill run successful" if results["success"] else "Cancelling skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in cancel skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during cancelling skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('pause_run_skill')
def handle_pause_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get pause skill run request: {request}")

        main_window = AppContext.get_main_window()
        results = pause_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "Get pause skill run successful" if results["success"] else "Pausing skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in pausing skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during pausing skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('resume_run_skill')
def handle_resume_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get resume skill run called with request: {request}")

        main_window = AppContext.get_main_window()
        results = resume_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "Resume skill run successful" if results["success"] else "Pausing skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in resume skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during resuming skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('step_run_skill')
def handle_step_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get single step skill run called with request: {request}")

        main_window = AppContext.get_main_window()
        results = step_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "single step skill run successful" if results["success"] else "Single Stepping skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in single step skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error single stepping skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('set_skill_breakpoints')
def handle_set_skill_breakpoints(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get setting skill breakpoints with request: {request}")

        main_window = AppContext.get_main_window()
        owner = params["username"]
        bps = [params["node_name"]]
        results = set_bps_dev_skill(main_window, bps)
        results = {"success": True}
        return create_success_response(request, {
            "results": results,
            "message": "Setting skill breakpoints successful" if results["success"] else "Setting skill breakpoints failed"
        })

    except Exception as e:
        logger.error(f"Error in setting skill breakpoints handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during setting skill breakpoints: {str(e)}"
        )

@IPCHandlerRegistry.handler('clear_skill_breakpoints')
def handle_clear_skill_breakpoints(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get clearing skill breakpoints with request: {request}")

        owner = params["username"]
        login: Login = AppContext.login
        bps = [params["node_name"]]
        login.main_win.clear_skill_breakpoints(owner, bps)
        return create_success_response(request, {
            "tests": ["test1", "test2", "test3"],
            'message': 'Clear skill breakpoints successful'
        })

    except Exception as e:
        logger.error(f"Error in get available tests handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during clearning skill breakpoints: {str(e)}"
        )


@IPCHandlerRegistry.handler('request_skill_state')
def handle_request_skill_state(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get current skill run state: {request}")

        return create_success_response(request, {
            "tests": ["test1", "test2", "test3"],
            'message': 'Request skill state successful'
        })

    except Exception as e:
        logger.error(f"Error in getting skill state handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during getting current skill state: {str(e)}"
        )

@IPCHandlerRegistry.handler('inject_skill_state')
def handle_inject_skill_state(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"injecting skill state: {request}")

        return create_success_response(request, {
            "tests": ["test1", "test2", "test3"],
            'message': 'Get available tests successful'
        })

    except Exception as e:
        logger.error(f"Error in inject skill state handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during injecting skill state: {str(e)}"
        )


@IPCHandlerRegistry.handler('load_skill_schemas')
def handle_load_skill_schemas(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取可用测试项请求

    Args:
        request: IPC 请求对象
        params: None

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"loading skill schemas: {request}")

        login: Login = AppContext.login
        node_schemas = login.main_win.node_schemas
        return create_success_response(request, {
            "node_schemas": node_schemas,
            'message': 'Load skill schemas successful'
        })

    except Exception as e:
        logger.error(f"Error in loading skill schemas handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during loading skill schemas: {str(e)}"
        )


@IPCHandlerRegistry.handler('run_tests')
def handle_run_tests(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
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
        login: Login = AppContext.login
        agents = login.main_win.agents

        web_gui = AppContext.web_gui
        for test in tests:
            test_id = test.get('test_id')
            test_args = test.get('args', {})

            # Process each test with its arguments
            if test_id == 'default_test':
                login: Login = AppContext.login
                result = run_default_tests(web_gui, login.main_win)
            # Add other test cases as needed
            else:
                print(">>>>>running test:", test_id, "trigger running procrement task")

                request['params'] = {
                    "message": [
                        {
                            "id": "10",
                            "chat_id": "2",
                            "session_id": "1",
                            "content": "please help analyze these files and provided a detailed description of each file.",
                            "attachments": [
                                {
                                    "id": "0",
                                    "name": "test0.png",
                                    "type": "image",
                                    "size": "",
                                    "url": "",
                                    "content": "",
                                    "file": "C:/Users/songc/PycharmProjects/ecbot/test0.png",
                                }
                        #         {
                        #             "id": "1",
                        #             "name": "test1.pdf",
                        #             "type": "application",
                        #             "size": "",
                        #             "url": "",
                        #             "content": "",
                        #             "file": "C:/Users/songc/PycharmProjects/ecbot/test1.pdf",
                        #         },
                        #         {
                        #             "id": "2",
                        #             "name": "test2.wav",
                        #             "type": "audio",
                        #             "size": "",
                        #             "url": "",
                        #             "content": "",
                        #             "file": "C:/Users/songc/PycharmProjects/ecbot/test2.wav",
                        #         }
                            ],
                            "sender_id": "1",
                            "sender_name": "twin",
                            "recipient_id": "2",
                            "recipient_name": "procurement",
                            "txTimestamp": "string",
                            "rxTimestamp": "string",
                            "readTimestamp": "string",
                            "status": 'sending',
                            "isEdited": False,
                            "isRetracted": False,
                            "ext": None,
                            "replyTo": "0",
                            "atList": []
                        }
                    ]
                }

                print("test params:", params)
                print("# agents:", len(agents), [ag.card.name for ag in agents])
                # simply drop a message to the queue
                procurement_agent = next((ag for ag in agents if ag.card.name == "Engineering Procurement Agent"), None)
                twin_agent = next((ag for ag in agents if ag.card.name == "My Twin Agent"), None)
                print("twin:", twin_agent.card.name, "procurement:", procurement_agent.card.name)

                runner_method = twin_agent.runner.chat_wait_in_line
                if asyncio.iscoroutinefunction(runner_method):
                    logger.debug("Runner method is a coroutine, running with asyncio.run()")

                    def run_async():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(runner_method(request))
                        finally:
                            loop.close()

                    # Run the coroutine in a separate thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_async)
                        result = future.result()

                    # loop = asyncio.get_event_loop()
                    # # asyncio.set_event_loop(loop)
                    # # 在独立的后台线程中，可以安全使用 asyncio.run()
                    # # result = await runner_method(params["message"])
                    # result = loop.run_until_complete(runner_method(params["message"]))
                else:
                    logger.debug("Runner method is synchronous, calling directly.")
                    result = runner_method(request)

                logger.info(f"Background task 'send_chat' completed with result: {result}")


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
            'RUN_TESTS_ERROR',
            f"Error during run tests: {str(e)}"
        )

@IPCHandlerRegistry.handler('stop_tests')
def handle_stop_tests(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理停止测试项请求

    Args:
        request: IPC 请求对象
        params: 测试项

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Stop tests handler called with request: {request}")

        return create_success_response(request, {
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

@IPCHandlerRegistry.handler('login_with_google')
def handle_login_with_google(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理停止测试项请求

    Args:
        request: IPC 请求对象
        params: 测试项

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login with google handler called with request: {request}")
        login: Login = AppContext.login
        result = login.login_google()

        return create_success_response(request, {
            "tests": ["test1", "test2", "test3"],
            'message': 'login with google successful'
        })

    except Exception as e:
        logger.error(f"Error in login with google handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GOOGLE_LOGIN_ERROR',
            f"Error during stop tests: {str(e)}"
        )


@IPCHandlerRegistry.handler('get_initialization_progress')
def handle_get_initialization_progress(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Get MainWindow initialization progress

    Args:
        request: IPC request object
        params: Request parameters (not used)

    Returns:
        IPCResponse: JSON response with initialization progress
    """
    try:
        logger.debug(f"Get initialization progress handler called with request: {request}")

        main_window = AppContext.get_main_window()
        if main_window is None:
            # MainWindow not yet created
            return create_success_response(request, {
                'ui_ready': False,
                'critical_services_ready': False,
                'async_init_complete': False,
                'fully_ready': False,
                'sync_init_complete': False,
                'message': 'MainWindow not yet initialized'
            })

        # Get progress from MainWindow
        progress = main_window.get_initialization_progress()
        progress['message'] = 'Initialization progress retrieved successfully'

        logger.debug(f"Initialization progress: {progress}")
        return create_success_response(request, progress)

    except Exception as e:
        logger.error(f"Error in get initialization progress handler: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(
            request,
            'INIT_PROGRESS_ERROR',
            f"Error getting initialization progress: {str(e)}"
        )


# 打印所有已注册的处理器
logger.info(f"Registered handlers: {IPCHandlerRegistry.list_handlers()}")