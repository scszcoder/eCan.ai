"""
聊天相关的后台 IPC 处理器
"""
import json
import os
import time
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
import tempfile

ECHO_REPLY_ENABLED = True  # 开关控制

def echo_and_push_message_async(chatId, message):
    """
    延迟2秒后异步推送一条 echo 消息到 chat，自动修改 role、status、发送者/接收者。
    """
    import copy
    import time
    import uuid  # 确保 uuid 在 do_push 作用域可用
    def do_push():
        time.sleep(1)
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
        # 为每个附件生成新的 uid，避免数据库唯一约束冲突
        if echo_msg.get('attachments'):
            for att in echo_msg['attachments']:
                att['uid'] = str(uuid.uuid4())
                if 'fileInstance' in att and isinstance(att['fileInstance'], dict):
                    att['fileInstance']['uid'] = att['uid']
        # 生成新 id
        echo_msg['id'] = str(uuid.uuid4())
        echo_msg['createAt'] = int(time.time() * 1000)
        # 存入数据库
        try:
            from app_context import AppContext
            app_ctx = AppContext()
            chat_service: ChatService = app_ctx.main_window.chat_service
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
                attachments=echo_msg.get('attachments')
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
        chat_service: ChatService = main_window.chat_service
        # 参数提取
        chatId = params['chatId']
        role = params['role']
        content = params['content']
        senderId = params['senderId']
        createAt = params['createAt'] or int(time.time() * 1000)
        # 可选参数
        messageId = params.get('id')
        status = params.get('status')
        senderName = params.get('senderName')
        time = params.get('time')
        ext = params.get('ext')
        attachments = params.get('attachments')
        # 调用 add_message
        result = chat_service.add_message(
            chatId=chatId,
            role=role,
            content=content,
            senderId=senderId,
            createAt=createAt,
            id=messageId,
            status=status,
            senderName=senderName,
            time=time,
            ext=ext,
            attachments=attachments
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
                'id': messageId,
                'status': status,
                'time': time,
                'ext': ext,
                'attachments': attachments
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
        lastMsgTime = params.get('lastMsgTime') or int(time.time() * 1000)
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

@IPCHandlerRegistry.handler('upload_attachment')
def handle_upload_attachment(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理上传附件，将附件保存到临时目录，并返回 url、name、type、size 等信息。
    """
    try:
        name = params['name']
        file_type = params['type']
        size = params['size']
        data = params['data']  # base64 或 bytes
        logger.debug(f"handle_upload_attachment handler called with params: {name},{file_type}, {size}")
        # 生成唯一文件名，防止冲突
        ext = os.path.splitext(name)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, unique_name)
        # 保存文件
        if isinstance(data, str):
            import base64
            if data.startswith('data:'):
                data = data.split(',', 1)[-1]
            file_bytes = base64.b64decode(data)
        else:
            raise ValueError("Only base64 string is supported for 'data' field")
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        # 构造 url
        url = os.path.join(main_window.temp_dir, unique_name)
        logger.debug(f"upload attachem name:{name}; url:{url};file  type:{file_type};size:{size}")
        result = {
            'url': url,
            'name': name,
            'type': file_type,
            'size': size,
            'status': 'done',
            'uid': str(uuid.uuid4()),
        }
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in upload_attachment handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPLOAD_ATTACHMENT_ERROR', str(e))

@IPCHandlerRegistry.handler('get_file_content')
def handle_get_file_content(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理获取文件内容请求，读取本地文件并返回 base64 数据。
    用于前端预览或下载本地文件附件。
    """
    try:
        file_path = params.get('filePath')
        if not file_path:
            return create_error_response(request, 'MISSING_FILE_PATH', 'filePath parameter is required')
        
        # 处理 pyqtfile:// 协议前缀
        if file_path.startswith('pyqtfile://'):
            file_path = file_path.replace('pyqtfile://', '')
        
        # 安全检查：确保文件路径在允许的目录内
        temp_dir = tempfile.gettempdir()
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        allowed_dir = main_window.temp_dir if hasattr(main_window, 'temp_dir') else temp_dir
        
        # 规范化路径并检查安全性
        file_path = os.path.abspath(file_path)
        allowed_dir = os.path.abspath(allowed_dir)
        
        if not file_path.startswith(allowed_dir):
            logger.warning(f"Access denied to file: {file_path} (not in allowed directory: {allowed_dir})")
            return create_error_response(request, 'ACCESS_DENIED', 'File access denied for security reasons')
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return create_error_response(request, 'FILE_NOT_FOUND', f'File not found: {file_path}')
        
        # 检查文件大小，防止读取过大的文件
        file_size = os.path.getsize(file_path)
        max_size = 50 * 1024 * 1024  # 50MB 限制
        if file_size > max_size:
            return create_error_response(request, 'FILE_TOO_LARGE', f'File too large: {file_size} bytes (max: {max_size})')
        
        # 读取文件并转换为 base64
        import base64
        import mimetypes
        
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        
        # 获取文件的 MIME 类型
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # 转换为 base64
        base64_data = base64.b64encode(file_bytes).decode('utf-8')
        
        # 构造 data URL
        data_url = f"data:{mime_type};base64,{base64_data}"
        
        result = {
            'dataUrl': data_url,
            'mimeType': mime_type,
            'fileName': os.path.basename(file_path),
            'fileSize': file_size
        }
        
        logger.debug(f"Successfully read file: {file_path} (size: {file_size} bytes)")
        return create_success_response(request, result)
        
    except PermissionError as e:
        logger.error(f"Permission error reading file: {e}")
        return create_error_response(request, 'PERMISSION_ERROR', f'Permission denied: {str(e)}')
    except Exception as e:
        logger.error(f"Error in get_file_content handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_FILE_CONTENT_ERROR', str(e))

@IPCHandlerRegistry.handler('get_file_info')
def handle_get_file_info(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理获取文件信息请求，返回文件的基本信息而不读取内容。
    用于前端判断文件类型和大小。
    """
    try:
        file_path = params.get('filePath')
        if not file_path:
            return create_error_response(request, 'MISSING_FILE_PATH', 'filePath parameter is required')
        
        # 处理 pyqtfile:// 协议前缀
        if file_path.startswith('pyqtfile://'):
            file_path = file_path.replace('pyqtfile://', '')
        
        # 安全检查：确保文件路径在允许的目录内
        temp_dir = tempfile.gettempdir()
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        allowed_dir = main_window.temp_dir if hasattr(main_window, 'temp_dir') else temp_dir
        
        # 规范化路径并检查安全性
        file_path = os.path.abspath(file_path)
        allowed_dir = os.path.abspath(allowed_dir)
        
        if not file_path.startswith(allowed_dir):
            logger.warning(f"Access denied to file: {file_path} (not in allowed directory: {allowed_dir})")
            return create_error_response(request, 'ACCESS_DENIED', 'File access denied for security reasons')
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return create_error_response(request, 'FILE_NOT_FOUND', f'File not found: {file_path}')
        
        # 获取文件信息
        import mimetypes
        import stat
        
        file_stat = os.stat(file_path)
        file_size = file_stat.st_size
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # 获取 MIME 类型
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # 判断是否为图片文件
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico'}
        is_image = file_ext in image_extensions or mime_type.startswith('image/')
        
        # 判断是否为文本文件
        text_extensions = {'.txt', '.md', '.json', '.xml', '.html', '.css', '.js', '.py', '.java', '.cpp', '.c', '.h', '.sql', '.log'}
        text_mime_types = {'text/', 'application/json', 'application/xml', 'application/javascript'}
        is_text = (file_ext in text_extensions or 
                   any(mime_type.startswith(prefix) for prefix in text_mime_types))
        
        result = {
            'fileName': file_name,
            'filePath': file_path,
            'fileSize': file_size,
            'fileExt': file_ext,
            'mimeType': mime_type,
            'isImage': is_image,
            'isText': is_text,
            'lastModified': int(file_stat.st_mtime * 1000),  # 转换为毫秒时间戳
            'created': int(file_stat.st_ctime * 1000)  # 转换为毫秒时间戳
        }
        
        logger.debug(f"File info retrieved: {file_path} (size: {file_size} bytes, type: {mime_type})")
        return create_success_response(request, result)
        
    except PermissionError as e:
        logger.error(f"Permission error getting file info: {e}")
        return create_error_response(request, 'PERMISSION_ERROR', f'Permission denied: {str(e)}')
    except Exception as e:
        logger.error(f"Error in get_file_info handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_FILE_INFO_ERROR', str(e))

