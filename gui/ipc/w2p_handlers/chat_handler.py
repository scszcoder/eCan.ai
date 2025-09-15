"""
聊天相关的后台 IPC 处理器
整体结构优化：参数提取、类型分发、推送等逻辑分层，主流程极简，便于维护。
"""
import json
import os
import time
import traceback
from typing import Any, Optional
import uuid
from app_context import AppContext

from utils.gui_dispatch import post_to_main_thread
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from utils.path_manager import path_manager
from gui.ipc.registry import IPCHandlerRegistry
from agent.chats.chat_service import ChatService
import tempfile
from agent.chats.chat_utils import a2a_send_chat

ECHO_REPLY_ENABLED = False  # 开关控制

# ===================== 辅助函数 =====================
def extract_and_validate_chat_args(params: dict) -> dict:
    """参数提取、补全默认值、校验必填项，返回标准化 dict"""
    chatId = params.get('chatId')
    role = params.get('role')
    content = params.get('content')
    senderId = params.get('senderId')
    createAt = params.get('createAt') or int(time.time() * 1000)
    messageId = params.get('id')
    status = params.get('status')
    senderName = params.get('senderName')
    time_ = params.get('time')
    ext = params.get('ext')
    attachments = params.get('attachments')
    receiverId = params.get('receiverId')
    receiverName = params.get('receiverName')
    # 校验必填
    if not chatId or not role or content is None or not senderId:
        raise ValueError('chatId, role, content, senderId 必填')
    return {
        'chatId': chatId,
        'role': role,
        'content': content,
        'senderId': senderId,
        'createAt': createAt,
        'id': messageId,
        'status': status,
        'senderName': senderName,
        'time': time_,
        'ext': ext,
        'attachments': attachments,
        'receiverId': receiverId,
        'receiverName': receiverName
    }

# ===================== 主处理器 =====================
@IPCHandlerRegistry.background_handler('send_chat')
def handle_send_chat(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    处理发送聊天消息，类型分发调用 chat_service.add_xxx_message，支持多内容类型。
    """
    try:
        main_window = AppContext.get_main_window()
        chat_service = main_window.chat_service
        # 1. 参数提取与校验
        chat_args = extract_and_validate_chat_args(params)
        # 2. 类型分发并入库
        chatId = chat_args['chatId']
        result = chat_service.dispatch_add_message(chatId, chat_args)
        logger.info(f"add_message result: {result}")
        # 3. 回显/推送
        if ECHO_REPLY_ENABLED:
            echo_and_push_message_async(chatId, chat_args)
        else:
            request['params']['human'] = True
            a2a_send_chat(main_window, request)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in handle_send_chat: {e}", exc_info=True)
        return create_error_response(request, 'SEND_CHAT_ERROR', str(e))

# ===================== echo_and_push_message_async 优化版 =====================

def _do_push_and_echo(chatId, message):
    """
    Helper function to construct and push messages.
    This function is intended to be run on the main GUI thread via post_to_main_thread.
    """
    import copy
    import time
    import uuid
    from app_context import AppContext

    main_window = AppContext.get_main_window()
    web_gui = AppContext.get_web_gui()

    def build_echo_message(main_window, message):
        """构造 echo 回显消息，自动处理角色、内容、附件等，确保所有必需字段齐全"""
        echo_msg = copy.deepcopy(message)
        # 必需字段补全
        echo_msg['chatId'] = message.get('chatId') or echo_msg.get('chatId') or ''
        echo_msg['role'] = 'agent'  # echo 回显角色固定
        echo_msg['status'] = 'complete'
        echo_msg['senderId'] = message.get('senderId') or echo_msg.get('senderId') or 'agent'
        echo_msg['createAt'] = int(time.time() * 1000)
        if 'content' not in echo_msg or echo_msg['content'] is None:
            echo_msg['content'] = ''
        # 交换 sender/receiver 逻辑
        if 'senderId' in echo_msg and 'receiverId' in echo_msg:
            echo_msg['senderId'], echo_msg['receiverId'] = echo_msg['receiverId'], echo_msg['senderId']
        # 交换后再次补全 senderId，彻底避免 None
        if not echo_msg.get('senderId'):
            echo_msg['senderId'] = 'agent'
        if 'senderName' in echo_msg and 'receiverName' in echo_msg:
            echo_msg['senderName'], echo_msg['receiverName'] = echo_msg['receiverName'], echo_msg['senderName']
        # echo 内容前缀
        if isinstance(echo_msg.get('content'), dict):
            if 'text' in echo_msg['content']:
                echo_msg['content']['text'] = f"echo: {echo_msg['content']['text']}"
        elif isinstance(echo_msg.get('content'), str):
            echo_msg['content'] = f"echo: {echo_msg['content']}"
        # 附件处理
        if echo_msg.get('attachments'):
            for att in echo_msg['attachments']:
                att['uid'] = str(uuid.uuid4())
                if 'name' in att:
                    ext = os.path.splitext(att['name'])[1]
                    new_filename = f"{uuid.uuid4().hex}{ext}"
                    new_url = os.path.join(main_window.temp_dir, new_filename)
                    new_file_path = os.path.join(main_window.temp_dir, new_filename)
                    original_url = att.get('url', '')
                    os.makedirs(main_window.temp_dir, exist_ok=True)
                    try:
                        if original_url:
                            if original_url.startswith('pyqtfile://'):
                                original_url = original_url.replace('pyqtfile://', '')
                            if os.path.exists(original_url):
                                import shutil
                                shutil.copy2(original_url, new_file_path)
                    except Exception as e:
                        logger.error(f"Failed to copy file: {e}")
                    att['url'] = new_url
                if 'fileInstance' in att and isinstance(att['fileInstance'], dict):
                    att['fileInstance']['uid'] = att['uid']
        echo_msg['id'] = str(uuid.uuid4())
        # 其它可选字段补全
        if 'senderName' not in echo_msg or not echo_msg['senderName']:
            echo_msg['senderName'] = 'AI助手'
        if 'status' not in echo_msg or not echo_msg['status']:
            echo_msg['status'] = 'complete'
        if 'ext' not in echo_msg or not echo_msg['ext']:
            echo_msg['ext'] = {}
        if 'attachments' not in echo_msg or not echo_msg['attachments']:
            echo_msg['attachments'] = []
        if 'time' not in echo_msg or not echo_msg['time']:
            echo_msg['time'] = echo_msg['createAt']
        # 强校验并日志
        required_fields = ['chatId', 'role', 'content', 'senderId', 'createAt']
        for f in required_fields:
            if not echo_msg.get(f):
                logger.error(f"echo_msg 缺少必需字段: {f}，内容: {echo_msg}")
                return None
        logger.debug("build echo messge", echo_msg)
        return echo_msg

    def build_form_message(form_template, base_msg=None, chatId=None):
        """构造表单消息，自动补全所有必需字段"""
        now = int(time.time() * 1000)
        senderId = (base_msg.get('senderId') if base_msg and base_msg.get('senderId') else 'assistant')
        senderName = (base_msg.get('senderName') if base_msg and base_msg.get('senderName') else 'AI助手')
        ext = base_msg.get('ext') if base_msg and base_msg.get('ext') else {}
        attachments = [] # base_msg.get('attachments') if base_msg and base_msg.get('attachments') else []
        msg_chatId = chatId or (base_msg.get('chatId') if base_msg and base_msg.get('chatId') else None)
        if not msg_chatId:
            raise ValueError('chatId is required for form message')
        return {
            'id': str(uuid.uuid4()),
            'chatId': msg_chatId,
            'role': 'assistant',
            'content': {
                'type': 'form',
                'form': form_template
            },
            'createAt': now,
            'status': 'complete',
            'senderId': senderId,
            'senderName': senderName,
            'time': now,
            'ext': ext or {},
            'attachments': attachments or []
        }

    def push_message(main_window, chatId, msg):
        """类型分发，自动调用 chat_service.add_xxx_message，推送到前端，并记录数据库写入结果"""
        logger.info(f"push_message echo_msg: {msg}")
        main_window.chat_service.push_message_to_chat(chatId, msg)

    logger.debug("start do push echo message")
    # 1. 构造并推送 echo 消息
    echo_msg = build_echo_message(main_window, message)
    if echo_msg: # 确保 echo_msg 不为 None
        push_message(main_window, chatId, echo_msg)
    # 2. 构造并推送表单模板消息
    try:
        template_path = os.path.join(os.path.dirname(__file__), '../../../agent/chats/templates/mcu_config_form.json')
        template_path = os.path.abspath(template_path)
        with open(template_path, 'r', encoding='utf-8') as f:
            form_template = json.load(f)
        form_msg = build_form_message(form_template, base_msg=echo_msg, chatId=chatId)
        push_message(main_window, chatId, form_msg)
    except Exception as e:
        logger.error(f"Failed to push form template message: {e}")
    # 3. 构造并推送表单模板消息
    try:
        template_path = os.path.join(os.path.dirname(__file__), '../../../agent/chats/templates/eval_system.json')
        template_path = os.path.abspath(template_path)
        with open(template_path, 'r', encoding='utf-8') as f:
            form_template = json.load(f)
        form_msg = build_form_message(form_template, base_msg=echo_msg, chatId=chatId)
        push_message(main_window, chatId, form_msg)
    except Exception as e:
        logger.error(f"Failed to push form template message: {e}")
    # 4. 构造并推送 agent notification 消息
    try:
        search_results_path = os.path.join(os.path.dirname(__file__), '../../../agent/chats/templates/search_results.json')
        search_results_path = os.path.abspath(search_results_path)
        with open(search_results_path, 'r', encoding='utf-8') as f:
            content = f.read()  # 直接读取原始 JSON 文本
        # 新增：保存 content 到数据库
        try:
            content_dict = json.loads(content)
        except Exception:
            content_dict = {"raw": content}
        chat_service = main_window.chat_service
        result = chat_service.add_chat_notification(chatId, content_dict, int(time.time() * 1000), isRead=False)
        if result and result.get('success') and result.get('data'):
            notif_data = result['data']
            isRead = notif_data.get('isRead', False)
            content = notif_data.get('content', "")
            timestamp = notif_data.get('timestamp', int(time.time() * 1000))
            uid = notif_data.get('uid')
            web_gui.get_ipc_api().push_chat_notification(chatId, content, isRead=isRead, timestamp=timestamp, uid=uid)
        else:
            logger.error(f"Failed to add chat notification to db: {result}")
    except Exception as e:
        logger.error(f"Failed to push agent notification: {e}")

def echo_and_push_message_async(chatId, message):
    """
    Schedules the message push logic to run on the main GUI thread after a 1-second delay.
    This function is called from a background thread. It blocks the *current* worker thread for 1 second,
    but does not block the GUI.
    """
    time.sleep(1)
    post_to_main_thread(lambda: _do_push_and_echo(chatId, message))

# ===================== 其他处理器（保持原有结构，可后续优化） =====================
@IPCHandlerRegistry.handler('get_chats')
def handle_get_chats(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理获取聊天列表请求，直接调用 chat_service.query_chats_by_user。
    """
    try:
        logger.debug(f"get chats handler called with request: {request}")
        userId = params.get('userId')
        deep = params.get('deep', False)
        main_window = AppContext.get_main_window()
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
        main_window = AppContext.get_main_window()
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
        main_window = AppContext.get_main_window()
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
        main_window = AppContext.get_main_window()
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
        main_window = AppContext.get_main_window()
        chat_service = main_window.chat_service
        result = chat_service.mark_message_as_read(messageIds=messageIds, userId=userId)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in mark_message_as_read handler: {e}")
        return create_error_response(request, 'MARK_MESSAGE_AS_READ_ERROR', str(e))

@IPCHandlerRegistry.handler('upload_attachment')
def handle_upload_attachment(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle upload attachment, save attachment to temporary directory, and return url, name, type, size and other information.
    """
    try:
        name = params['name']
        file_type = params['type']
        size = params['size']
        data = params['data']  # base64 or bytes
        logger.debug(f"handle_upload_attachment handler called with params: {name},{file_type}, {size}")
        # Generate unique filename to prevent conflicts
        ext = os.path.splitext(name)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        main_window = AppContext.get_main_window()
        # Use main_window.temp_dir instead of tempfile.gettempdir()
        file_path = os.path.join(main_window.temp_dir, unique_name)
        # Ensure directory exists using safe method

        path_manager.ensure_directory_exists(file_path)
        # Save file
        if isinstance(data, str):
            import base64
            if data.startswith('data:'):
                data = data.split(',', 1)[-1]
            file_bytes = base64.b64decode(data)
        else:
            raise ValueError("Only base64 string is supported for 'data' field")
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        # 验证文件是否保存成功
        if os.path.exists(file_path):
            actual_size = os.path.getsize(file_path)
            logger.debug(f"File saved successfully: {file_path} (size: {actual_size} bytes)")
        else:
            logger.error(f"File save failed: {file_path}")
            raise Exception(f"Failed to save file to {file_path}")
        # 构造 url
        url = os.path.join(main_window.temp_dir, unique_name)
        logger.debug(f"upload attachem name:{name}; url:{url};file  type:{file_type};size:{size}")
        result = {
            'url': url,
            'name': name,
            'type': file_type,
            'size': size
        }
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in upload_attachment handler: {e}")
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
        main_window = AppContext.get_main_window()
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
        main_window = AppContext.get_main_window()
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

@IPCHandlerRegistry.handler('chat_form_submit')
def handle_chat_form_submit(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理聊天表单提交请求，参数包括 chatId, messageId, formId, formData。
    """
    try:
        logger.info(f"handle_chat_form_submit called with params: {request} {params}")
        chatId = params.get('chatId')
        messageId = params.get('messageId')
        formId = params.get('formId')
        formData = params.get('formData')
        if not chatId or not messageId or not formId or formData is None:
            logger.error("chat form submit invalid params")
            return create_error_response(request, 'INVALID_PARAMS', 'chatId, messageId, formId, formData 必填')
        main_window = AppContext.get_main_window()
        chat_service = main_window.chat_service
        # 假设 chat_service 有 submit_form 方法，否则可自定义处理
        if hasattr(chat_service, 'submit_form'):
            result = chat_service.submit_form(chatId=chatId, messageId=messageId, formId=formId, formData=formData)
            logger.debug("chat submit form result: %s", result)
            if not result.get('success'):
                return create_error_response(request, 'CHAT_FORM_SUBMIT_ERROR', result.get('error', 'Unknown error'))
            
            params["senderId"] = "b9a9bd0e29b94fe4aaf4542cba7f5a27"
            params["senderName"] = "My Twin Agent"
            params["role"] = "user"
            params["createAt"] = int(time.time() * 1000)
            params["status"] = "complete"
            params["attachments"] = []
            params["content"] = json.dumps(params.get("formData"))
            form_submit_req =IPCRequest(id="", type='request', method="form_submit", params=params, meta={}, timestamp=params["createAt"] )
            print("a2a_send_chat form submit:", form_submit_req)
            request['params']['human'] = True
            a2a_send_chat(main_window, form_submit_req)

            return create_success_response(request, result.get('data'))
        else:
            # 如果没有 submit_form 方法，简单记录表单数据，可自定义扩展
            result = {
                'chatId': chatId,
                'messageId': messageId,
                'formId': formId,
                'formData': formData,
                'status': 'received'
            }
            logger.error("no submit form function in chat service")
            return create_error_response(request, 'CHAT_FORM_SUBMIT_ERROR', "no submit form function")
    except Exception as e:
        logger.error(f"Error in handle_chat_form_submit: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'CHAT_FORM_SUBMIT_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_message')
def handle_delete_message(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理删除消息请求，调用 chat_service.delete_message。
    """
    try:
        chatId = params.get('chatId')
        messageId = params.get('messageId')
        if not chatId or not messageId:
            return create_error_response(request, 'INVALID_PARAMS', 'chatId, messageId 必填')
        main_window = AppContext.get_main_window()
        chat_service = main_window.chat_service
        result = chat_service.delete_message(chatId=chatId, messageId=messageId)
        logger.debug("chat delete message  result: %s", result)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in delete_message handler: {e}")
        return create_error_response(request, 'DELETE_MESSAGE_ERROR', str(e))

@IPCHandlerRegistry.handler('get_chat_notifications')
def handle_get_chat_notifications(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理获取指定会话通知列表请求，调用 chat_service.query_chat_notifications。
    """
    try:
        logger.debug(f"get_chat_notifications handler called with request: {request}")
        chatId = params.get('chatId')
        limit = params.get('limit', 20)
        offset = params.get('offset', 0)
        reverse = params.get('reverse', False)
        
        if not chatId:
            return create_error_response(request, 'INVALID_PARAMS', 'chatId 必填')
            
        main_window = AppContext.get_main_window()
        chat_service = main_window.chat_service
        result = chat_service.query_chat_notifications(
            chatId=chatId, 
            limit=limit, 
            offset=offset, 
            reverse=reverse
        )
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get_chat_notifications handler: {e}")
        return create_error_response(request, 'GET_CHAT_NOTIFICATIONS_ERROR', str(e))

@IPCHandlerRegistry.handler('clean_chat_unread')
def handle_clean_chat_unread(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    处理清除指定会话未读数请求，将 chat 的 unread 设置为 0。
    """
    try:
        chatId = params.get('chatId')
        if not chatId:
            return create_error_response(request, 'INVALID_PARAMS', 'chatId 必填')
        main_window = AppContext.get_main_window()
        chat_service = main_window.chat_service
        # 假设 chat_service 有 set_chat_unread 方法，否则直接更新 chat 的 unread 字段
        if hasattr(chat_service, 'set_chat_unread'):
            result = chat_service.set_chat_unread(chatId=chatId, unread=0)
        else:
            # 兼容：直接调用 update_chat 或自定义方法
            if hasattr(chat_service, 'update_chat'):
                result = chat_service.update_chat(chatId=chatId, unread=0)
            else:
                return create_error_response(request, 'NOT_IMPLEMENTED', 'chat_service 未实现 set_chat_unread 或 update_chat 方法')
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in clean_chat_unread handler: {e}")
        return create_error_response(request, 'CLEAN_CHAT_UNREAD_ERROR', str(e))

