"""
IPC Handler Implementation Module
Provides specific implementations for various IPC requests
"""

from typing import Any, Optional, Dict
import os
from datetime import datetime

from .types import IPCRequest, IPCResponse, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger
import traceback
from app_context import AppContext
import asyncio


def validate_params(params: Optional[Dict[str, Any]], required: list[str]) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Validate request parameters

    Args:
        params: Request parameters
        required: List of required parameters

    Returns:
        tuple[bool, Optional[Dict[str, Any]], Optional[str]]: (is valid, parameter data, error message)
    """
    if not params:
        return False, None, f"Missing required parameters: {', '.join(required)}"

    missing = [param for param in required if param not in params]
    if missing:
        return False, None, f"Missing required parameters: {', '.join(missing)}"

    return True, params, None


@IPCHandlerRegistry.handler('get_all')
def handle_get_all(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get all request

    Retrieve all data for the user.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' field

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get all called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get all: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        logger.debug("user name:" + data['username'])
        # Get username
        username = data['username']

        main_window = AppContext.get_main_window()
        agents = main_window.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)

        skills = main_window.agent_skills
        vehicles = main_window.vehicles
        settings = main_window.config_manager.general_settings.data

        knowledges = {}
        chats = {}
        logger.info(f"Get all successful for user: {username}")
        resultJS = {
            'agents': [agent.to_dict(owner=username) for agent in agents],
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


@IPCHandlerRegistry.handler('save_all')
def handle_save_all(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle save all request

    Save all data for the user.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Save all handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save all: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username
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
    """Handle get available tests request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
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


@IPCHandlerRegistry.background_handler('run_tests')
def handle_run_tests(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle run tests request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    # from tests.main_test import run_default_tests  # Commented out to prevent UI freeze

    try:
        logger.debug(f"Run tests handler called with request: {request}, params: {params}")
        tests = params.get('tests', [])

        results = []
        main_win = AppContext.get_main_window()
        agents = main_win.agents

        web_gui = AppContext.web_gui
        for test in tests:
            test_id = test.get('test_id')
            test_args = test.get('args', {})

            # Process each test with its arguments
            if test_id == 'default_test':
                main_win = AppContext.get_main_window()
                print("oooooooooooooo running default test ooooooooooooooooooooooooooo")
                # results = []

                procurement_agent = next((ag for ag in agents if ag.card.name == "Engineering Procurement Agent"), None)
                procurement_agent.self_wan_ping()
                # from tests.unittests import run_default_tests
                # result = run_default_tests(main_win)
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

                # Use sync_task_wait_in_line instead of deprecated chat_wait_in_line
                # This is a synchronous method that takes (event_type, request) parameters
                logger.debug("Calling sync_task_wait_in_line for human_chat event")
                result = twin_agent.runner.sync_task_wait_in_line("human_chat", request)

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
    """Handle stop tests request

    Args:
        request: IPC request object
        params: Test items

    Returns:
        str: JSON formatted response message
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
        # logger.debug(f"Get initialization progress handler called with request: {request}")

        main_window = AppContext.get_main_window()
        if main_window is None and os.getenv("ECAN_MODE", "desktop") == "web":
            # In web mode we don't create a Qt MainWindow; report ready so the frontend can proceed
            return create_success_response(request, {
                'ui_ready': True,
                'critical_services_ready': True,
                'async_init_complete': True,
                'fully_ready': True,
                'sync_init_complete': True,
                'message': 'Web mode: backend ready'
            })
        if main_window is None:
            logger.info("MainWindow not yet created")
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


@IPCHandlerRegistry.handler('ping')
def handle_ping(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Simple health check handler"""
    try:
        return create_success_response(request, {
            "message": "pong",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    except Exception as e:
        logger.error(f"Error in ping handler: {e}")
        return create_error_response(request, 'PING_ERROR', str(e))


@IPCHandlerRegistry.handler('window_toggle_fullscreen')
def handle_window_toggle_fullscreen(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle window fullscreen toggle request
    
    Toggle the main window fullscreen state.
    
    Args:
        request: IPC request object
        params: Request parameters (optional)
        
    Returns:
        IPCResponse: Response with fullscreen state
    """
    try:
        logger.debug("Window toggle fullscreen called")
        
        # Get WebGUI instance (not MainWindow)
        web_gui = AppContext.get_instance().web_gui
        if not web_gui:
            logger.warning("WebGUI not available for fullscreen toggle")
            return create_error_response(
                request,
                'WINDOW_NOT_AVAILABLE',
                'WebGUI not yet initialized'
            )
        
        # Toggle fullscreen
        web_gui._toggle_fullscreen()
        
        # Get current fullscreen state
        is_fullscreen = web_gui.isFullScreen()
        
        logger.info(f"Window fullscreen toggled, current state: {is_fullscreen}")
        return create_success_response(request, {
            'is_fullscreen': is_fullscreen,
            'message': 'Fullscreen toggled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error in window toggle fullscreen handler: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(
            request,
            'FULLSCREEN_ERROR',
            f"Error toggling fullscreen: {str(e)}"
        )


@IPCHandlerRegistry.handler('window_get_fullscreen_state')
def handle_window_get_fullscreen_state(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle window fullscreen state query request
    
    Get the current fullscreen state of the main window.
    
    Args:
        request: IPC request object
        params: Request parameters (optional)
        
    Returns:
        IPCResponse: Response with fullscreen state
    """
    try:
        logger.debug("Window get fullscreen state called")
        
        # Get WebGUI instance (not MainWindow)
        web_gui = AppContext.get_instance().web_gui
        if not web_gui:
            logger.warning("WebGUI not available for fullscreen state query")
            return create_error_response(
                request,
                'WINDOW_NOT_AVAILABLE',
                'WebGUI not yet initialized'
            )
        
        # Get current fullscreen state
        is_fullscreen = web_gui.isFullScreen()
        
        logger.debug(f"Window fullscreen state: {is_fullscreen}")
        return create_success_response(request, {
            'is_fullscreen': is_fullscreen,
            'message': 'Fullscreen state retrieved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error in window get fullscreen state handler: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(
            request,
            'FULLSCREEN_STATE_ERROR',
            f"Error getting fullscreen state: {str(e)}"
        )


# Print all registered handlers
logger.info(f"Registered handlers: {IPCHandlerRegistry.list_handlers()}")
