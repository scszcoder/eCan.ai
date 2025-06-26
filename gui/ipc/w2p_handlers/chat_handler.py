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
        chat_id = params['chatId']
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
            chat_id=chat_id,
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
        user_id = params.get('userId')
        deep = params.get('deep', False)
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.query_chats_by_user(user_id=user_id, deep=deep)
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
        chat_id = params.get('chatId')
        limit = params.get('limit', 20)
        offset = params.get('offset', 0)
        reverse = params.get('reverse', False)
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.query_messages_by_chat(chat_id=chat_id, limit=limit, offset=offset, reverse=reverse)
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
        chat_id = params.get('chatId')
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.delete_chat(chat_id=chat_id)
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
        message_ids = params.get('messageIds')
        user_id = params.get('userId')
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        chat_service = main_window.chat_service
        result = chat_service.mark_message_as_read(message_ids=message_ids, user_id=user_id)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in mark_message_as_read handler: {e}")
        return create_error_response(request, 'MARK_MESSAGE_AS_READ_ERROR', str(e))
