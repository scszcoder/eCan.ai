"""
聊天相关的后台 IPC 处理器
"""
import json
import os
import traceback
from typing import Any, Dict, Optional
import uuid
from agent.ec_agent import EC_Agent
from app_context import AppContext
from gui.LoginoutGUI import Login
from gui.ipc.handlers import validate_params
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from gui.ipc.registry import IPCHandlerRegistry
import asyncio # 假设 runner.chat_wait_in_line 是异步的


# def find_sender(py_login, chat):
#     sender = next((ag for ag in py_login.main_win.agents if "My Twin Agent" == ag.card.name), None)
#     return sender


# def find_recipient(py_login, chat):
#     logger.debug("finding recipient for chat:" + str(chat))
#     chat_id = chat['chat_id']
#     recipient = next((ag for ag in py_login.main_win.agents if "Engineering Procurement Agent" == ag.card.name), None)
#     logger.debug("recipient found:" + recipient.card.name)
#     return recipient

def _find_agent_by_name(login: Login, name: str) -> Optional[EC_Agent]:
    """通过名称查找代理"""
    return next((agent for agent in login.main_win.agents if agent.card.name == name), None)

@IPCHandlerRegistry.background_handler('send_chat')
def handle_send_chat(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    处理发送聊天消息的后台任务。
    此函数在 QThreadPool 的一个工作线程中执行。
    """
    logger.info(f"Background task 'send_chat' started with params: {params}")
    ctx = AppContext()
    login: Login = ctx.login
    sender_agent = _find_agent_by_name(login, "My Twin Agent")
    recipient_agent = _find_agent_by_name(login, "Engineering Procurement Agent")

    if not sender_agent or not recipient_agent:
        error_msg = "Sender or recipient agent not found."
        logger.error(error_msg)
        # 在后台任务中，我们直接返回字典，而不是JSON字符串
        return {"error": "AGENT_NOT_FOUND", "message": error_msg}

    try:
        # 这里的 chat_wait_in_line 是一个耗时操作。
        # 如果它本身是同步阻塞函数，直接调用即可。
        # 如果它是一个 async 函数，我们需要在这里用 asyncio.run() 包装它。
        
        runner_method = sender_agent.runner.chat_wait_in_line
        
        if asyncio.iscoroutinefunction(runner_method):
            logger.debug("Runner method is a coroutine, running with asyncio.run()")
            # 在独立的后台线程中，可以安全使用 asyncio.run()
            result = asyncio.run(runner_method(request))
        else:
            logger.debug("Runner method is synchronous, calling directly.")
            result = runner_method(request)
            
        logger.info(f"Background task 'send_chat' completed with result: {result}")
        return create_success_response(request, {
            "send_chat_response": result
        })

    except Exception as e:
        logger.error(f"Error during 'send_chat' background task: {e}", exc_info=True)
        return {"error": "TASK_EXECUTION_ERROR", "message": str(e)} 
    
@IPCHandlerRegistry.handler('get_chats')
def handle_get_chats(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'chat_ids' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"get chats handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'chat_ids'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get chats: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']
        chat_ids = data['chat_ids']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get chats successful for user: {username}")
        
        script_dir = os.path.dirname(__file__)
        json_path = os.path.join(script_dir, 'chats_demo.json')

        with open(json_path, 'r', encoding='utf-8') as f:
            all_chats = json.load(f)

        if not chat_ids:
            chats = all_chats
        else:
            # chat_ids from frontend might be integer, but in json they are integers.
            # So convert them to int for comparison.
            chat_ids_int = [int(cid) for cid in chat_ids]
            
            chats = [chat for chat in all_chats if chat['id'] in chat_ids_int]
            
            found_ids = [chat['id'] for chat in chats]
            not_found_ids = [cid for cid in chat_ids_int if cid not in found_ids]

            if not_found_ids:
                logger.warning(f"Could not find chats with the following IDs: {not_found_ids}")

        resultJS = {
            'token': token,
            'chats': chats,
            'message': 'Get all successful'
        }
        logger.debug('get chats resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get chats handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get chats: {str(e)}"
        )