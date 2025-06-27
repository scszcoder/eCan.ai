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
from gui.MainGUI import MainWindow
from gui.ipc.handlers import validate_params
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from gui.ipc.registry import IPCHandlerRegistry
import asyncio # 假设 runner.chat_wait_in_line 是异步的
from agent.chats.chat_service import ChatService
import threading

ECHO_REPLY_ENABLED = True  # 开关控制

def echo_and_push_message_async(chatId, message):
    """
    延迟2秒后异步推送一条 echo 消息到 chat，自动修改 role、status、发送者/接收者。
    """
    import copy
    import time
    def do_push():
        time.sleep(2)
        echo_msg = copy.deepcopy(message)
        # 互换 senderId/Name，role=agent，status=complete，内容加 echo
        echo_msg['role'] = 'agent'
        echo_msg['status'] = 'complete'
        # 互换 senderId/Name 和 receiverId/Name（如有）
        if 'senderId' in echo_msg and 'receiverId' in echo_msg:
            echo_msg['senderId'], echo_msg['receiverId'] = echo_msg['receiverId'], echo_msg['senderId']
        if 'senderName' in echo_msg and 'receiverName' in echo_msg:
            echo_msg['senderName'], echo_msg['receiverName'] = echo_msg['receiverName'], echo_msg['senderName']
        # 内容 echo
        if isinstance(echo_msg.get('content'), dict):
            if 'text' in echo_msg['content']:
                echo_msg['content']['text'] = f"echo: {echo_msg['content']['text']}"
        elif isinstance(echo_msg.get('content'), str):
            echo_msg['content'] = f"echo: {echo_msg['content']}"
        # 生成新 id
        import uuid
        echo_msg['id'] = str(uuid.uuid4())
        # 存入数据库
        try:
            from app_context import AppContext
            app_ctx = AppContext()
            chat_service = app_ctx.main_window.chat_service
            chat_service.add_message(
                chatId=chatId,
                role=echo_msg.get('role'),
                content=echo_msg.get('content'),
                senderId=echo_msg.get('senderId'),
                createAt=echo_msg.get('createAt'),
                id=echo_msg.get('id'),
                status=echo_msg.get('status'),
                senderName=echo_msg.get('senderName'),
                time=echo_msg.get('time'),
                ext=echo_msg.get('ext'),
                attachment=echo_msg.get('attachment')
            )
        except Exception as e:
            import traceback
            print(f"[echo_and_push_message_async] add_message error: {e}\n{traceback.format_exc()}")
        # 推送
        app_ctx = AppContext()
        web_gui = app_ctx.web_gui
        web_gui.get_ipc_api().push_chat_message(chatId, echo_msg)
    threading.Thread(target=do_push, daemon=True).start()

def _find_agent_by_id(login: Login, id: str) -> Optional[EC_Agent]:
    """通过名称查找代理"""
    return next((agent for agent in login.main_win.agents if agent.card.id == id), None)


@IPCHandlerRegistry.background_handler('send_chat')
def handle_send_chat(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    处理发送聊天消息，直接调用 chat_service.add_message。
    """
    logger.info(f"Background task 'send_chat' started with request: {request}")
    try:
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        # 参数提取
        chatId = params['chatId']
        role = params['role']
        content = params['content']
        senderId = params['senderId']
        createAt = params['createAt']
        # 可选参数
        message_id = params.get('id')
        status = params.get('status')
        senderName = params.get('senderName')
        time = params.get('time')
        ext = params.get('ext')
        attachment = params.get('attachment')
        # 调用 add_message
        result = chat_service.add_message(
            chatId=chatId,
            role=role,
            content=content,
            senderId=senderId,
            createAt=createAt,
            id=message_id,
            status=status,
            senderName=senderName,
            time=time,
            ext=ext,
            attachment=attachment
        )
        logger.info(f"add_message result: {result}")
        # echo reply
        if ECHO_REPLY_ENABLED:
            # 构造 message dict 传递给 echo_and_push_message_async
            msg_dict = {
                'chatId': chatId,
                'role': role,
                'content': content,
                'senderId': senderId,
                'senderName': senderName,
                'createAt': createAt,
                'id': message_id,
                'status': status,
                'time': time,
                'ext': ext,
                'attachment': attachment
            }
            # 补充 receiverId/receiverName（如有）
            if 'receiverId' in params:
                msg_dict['receiverId'] = params['receiverId']
            if 'receiverName' in params:
                msg_dict['receiverName'] = params['receiverName']
            echo_and_push_message_async(chatId, msg_dict)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in handle_send_chat: {e}", exc_info=True)
        return create_error_response(request, 'SEND_CHAT_ERROR', str(e))

@IPCHandlerRegistry.handler('get_chats')
def handle_get_chats(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理获取聊天列表请求，直接调用 chat_service.query_chats_by_user。
    """
    try:
        logger.debug(f"get chats handler called with request: {request}")
        userId = params.get('userId')
        deep = params.get('deep', False)
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.query_chats_by_user(userId=userId, deep=deep)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get chats handler: {e}")
        return create_error_response(request, 'GET_CHATS_ERROR', str(e))

@IPCHandlerRegistry.handler('create_chat')
def handle_create_chat(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    创建新的聊天会话，直接调用 chat_service.create_chat。
    """
    logger.debug(f"create chat handler called with request: {request}")
    try:
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        # 拆分参数
        members = params['members']
        name = params['name']
        chat_type = params.get('type', 'user-agent')
        avatar = params.get('avatar')
        lastMsg = params.get('lastMsg')
        lastMsgTime = params.get('lastMsgTime')
        unread = params.get('unread', 0)
        pinned = params.get('pinned', False)
        muted = params.get('muted', False)
        ext = params.get('ext')

        result = chat_service.create_chat(
            members=members,
            name=name,
            type=chat_type,
            avatar=avatar,
            lastMsg=lastMsg,
            lastMsgTime=lastMsgTime,
            unread=unread,
            pinned=pinned,
            muted=muted,
            ext=ext
        )
        logger.debug("create chat result" + str(result))
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in create_chat handler: {e}")
        return create_error_response(request, 'CREATE_CHAT_ERROR', str(e))

@IPCHandlerRegistry.handler('get_chat_messages')
def handle_get_chat_messages(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理获取指定会话消息列表请求，调用 chat_service.query_messages_by_chat。
    """
    try:
        logger.debug(f"get_chat_messages handler called with request: {request}")
        chatId = params.get('chatId')
        limit = params.get('limit', 20)
        offset = params.get('offset', 0)
        reverse = params.get('reverse', False)
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.query_messages_by_chat(chatId=chatId, limit=limit, offset=offset, reverse=reverse)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get_chat_messages handler: {e}")
        return create_error_response(request, 'GET_CHAT_MESSAGES_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_chat')
def handle_delete_chat(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理删除会话请求，调用 chat_service.delete_chat。
    """
    try:
        chatId = params.get('chatId')
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.delete_chat(chatId=chatId)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in delete_chat handler: {e}")
        return create_error_response(request, 'DELETE_CHAT_ERROR', str(e))

@IPCHandlerRegistry.handler('mark_message_as_read')
def handle_mark_message_as_read(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理批量标记消息为已读请求，调用 chat_service.mark_message_as_read。
    """
    try:
        messageIds = params.get('messageIds')
        userId = params.get('userId')
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.mark_message_as_read(messageIds=messageIds, userId=userId)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in mark_message_as_read handler: {e}")
        return create_error_response(request, 'MARK_MESSAGE_AS_READ_ERROR', str(e))

