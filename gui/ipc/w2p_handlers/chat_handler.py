"""
Chat-related background IPC handlers
Overall structure optimization: parameter extraction, type dispatch, push logic layered, main flow simplified for easy maintenance.
"""
import json
import os
import threading
import time
import traceback
from typing import Any, Optional, TYPE_CHECKING
import uuid
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context

from utils.gui_dispatch import post_to_main_thread
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger
from utils.path_manager import path_manager
from gui.ipc.registry import IPCHandlerRegistry
import tempfile

if TYPE_CHECKING:
	from gui.MainGUI import MainWindow

ECHO_REPLY_ENABLED = False  # Switch control

# ===================== Helper Functions =====================
def extract_and_validate_chat_args(params: dict) -> dict:
    """Extract parameters, fill default values, validate required fields, return standardized dict"""
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
    # Validate required fields
    if not chatId or not role or content is None or not senderId:
        raise ValueError('chatId, role, content, senderId are required')
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

# ===================== Main Handlers =====================
# serialized IPCRequest
# {
#     "id": "3739721e-8205-4174-abb7-bd1223bea161",
#     "type": "request",
#     "method": "send_chat",
#     "params": {
#         "chatId": "chat-804150",
#         "senderId": "4864a82d505d4c89b965d848ea832c56",
#         "role": "user",
#         "content": "f",
#         "createAt": "1759801807448",
#         "senderName": "My Twin Agent",
#         "status": "complete",
#         "attachments": [],
#         "token": "df9bf922126d4b0d94f96e230c583bd7",
#         "human": True
#     },
#     "timestamp": 1759801807469
# }
@IPCHandlerRegistry.background_handler('send_chat')
def handle_send_chat(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Handle sending chat messages, dispatch to db_chat_service.add_xxx_message based on type, supports multiple content types.
    """
    try:
        t_start = time.time()
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        # 1. Extract and validate parameters
        t0 = time.time()
        chat_args = extract_and_validate_chat_args(params)
        logger.debug(f"[PERF] handle_send_chat - validate params: {time.time()-t0:.3f}s")
        
        # 2. Check if chat exists, if not create it
        chatId = chat_args['chatId']
        original_chatId = chatId  # Save original chatId for comparison
        
        # Check if chat exists
        t1 = time.time()
        existing_chat = db_chat_service.get_chat_by_id(chatId, deep=False)
        logger.debug(f"[PERF] handle_send_chat - get_chat_by_id: {time.time()-t1:.3f}s")
        
        if not existing_chat.get("success"):
            # Chat doesn't exist, create it
            logger.info(f"Chat {chatId} not found, creating new chat")
            
            # Extract sender and receiver info from params
            senderId = chat_args.get('senderId')
            senderName = chat_args.get('senderName', 'User')
            receiverId = chat_args.get('receiverId')
            receiverName = chat_args.get('receiverName', 'Agent')
            
            # Build members list
            members = [
                {
                    "userId": senderId,
                    "name": senderName,
                    "role": "user",
                    "avatar": None,
                    "status": "online",
                    "ext": {},
                    "agentName": senderName
                }
            ]
            
            # Add receiver if provided
            if receiverId:
                members.append({
                    "userId": receiverId,
                    "name": receiverName,
                    "role": "agent",
                    "avatar": None,
                    "status": "online",
                    "ext": {},
                    "agentName": receiverName
                })
            
            # Create chat
            create_result = db_chat_service.create_chat(
                members=members,
                name=receiverName if receiverId else senderName,
                type="user-agent",
                avatar=None,
                lastMsg=None,
                lastMsgTime=chat_args.get('createAt'),
                unread=0,
                pinned=False,
                muted=False,
                ext={},
                id=None,  # Let system generate new chatId
                agent_id=receiverId
            )
            
            if create_result.get("success"):
                # Update chatId with the real one from database
                chatId = create_result["id"]
                chat_args['chatId'] = chatId
                logger.info(f"Chat created successfully with new chatId: {chatId}")
            else:
                # If chat already exists (duplicate), use existing one
                if "already exists" in create_result.get("error", ""):
                    chatId = create_result["id"]
                    chat_args['chatId'] = chatId
                    logger.info(f"Chat already exists, using chatId: {chatId}")
                else:
                    logger.error(f"Failed to create chat: {create_result.get('error')}")
                    return create_error_response(request, 'CREATE_CHAT_ERROR', create_result.get('error'))
        
        # 3. Dispatch by type and save to database
        t2 = time.time()
        result = db_chat_service.dispatch_add_message(chatId, chat_args)
        logger.debug(f"[PERF] handle_send_chat - dispatch_add_message: {time.time()-t2:.3f}s")
        logger.info(f"add_message result: {result}")
        
        # 4. If chatId changed, include it in response so frontend can update
        if original_chatId != chatId:
            result['realChatId'] = chatId
            result['originalChatId'] = original_chatId
            logger.info(f"ChatId changed from {original_chatId} to {chatId}")
        
        # 5. Echo/push
        if ECHO_REPLY_ENABLED:
            echo_and_push_message_async(chatId, chat_args, request, params)
        else:
            # Lazy import for heavy dependencies
            from agent.chats.chat_utils import gui_a2a_send_chat
            request['params']['human'] = True
            request['params']['chatId'] = chatId  # Use real chatId
            # Preserve receiverId for gui_a2a_send_chat fallback (when chat doesn't exist yet)
            request['params']['receiverId'] = chat_args.get('receiverId')
            logger.info(f"[handle_send_chat] Calling gui_a2a_send_chat with chatId: {chatId}, original: {original_chatId}")
            logger.debug(f"[handle_send_chat] request['params']['chatId']: {request['params']['chatId']}")
            t3 = time.time()
            gui_a2a_send_chat(ctx, request)
            logger.debug(f"[PERF] handle_send_chat - gui_a2a_send_chat: {time.time()-t3:.3f}s")
        
        logger.info(f"[PERF] handle_send_chat - TOTAL: {time.time()-t_start:.3f}s")
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in handle_send_chat: {e}", exc_info=True)
        return create_error_response(request, 'SEND_CHAT_ERROR', str(e))

# ===================== echo_and_push_message_async Optimized Version =====================

def _do_push_and_echo(chatId, message, request=None, params=None):
    """
    Helper function to construct and push messages.
    This function is intended to be run on the main GUI thread via post_to_main_thread.
    """
    import copy
    import time
    import uuid
    from app_context import AppContext
    from gui.ipc.context_bridge import get_handler_context

    ctx = get_handler_context(request, params)
    web_gui = AppContext.get_web_gui()

    def build_echo_message(ctx, message):
        """Construct echo message, automatically handle role, content, attachments, etc., ensure all required fields are complete"""
        echo_msg = copy.deepcopy(message)
        # Fill required fields
        echo_msg['chatId'] = message.get('chatId') or echo_msg.get('chatId') or ''
        echo_msg['role'] = 'agent'  # Echo message role is fixed
        echo_msg['status'] = 'complete'
        echo_msg['senderId'] = message.get('senderId') or echo_msg.get('senderId') or 'agent'
        echo_msg['createAt'] = int(time.time() * 1000)
        if 'content' not in echo_msg or echo_msg['content'] is None:
            echo_msg['content'] = ''
        # Swap sender/receiver logic
        if 'senderId' in echo_msg and 'receiverId' in echo_msg:
            echo_msg['senderId'], echo_msg['receiverId'] = echo_msg['receiverId'], echo_msg['senderId']
        # Fill senderId again after swap to completely avoid None
        if not echo_msg.get('senderId'):
            echo_msg['senderId'] = 'agent'
        if 'senderName' in echo_msg and 'receiverName' in echo_msg:
            echo_msg['senderName'], echo_msg['receiverName'] = echo_msg['receiverName'], echo_msg['senderName']
        # Echo content prefix
        if isinstance(echo_msg.get('content'), dict):
            if 'text' in echo_msg['content']:
                echo_msg['content']['text'] = f"echo: {echo_msg['content']['text']}"
        elif isinstance(echo_msg.get('content'), str):
            echo_msg['content'] = f"echo: {echo_msg['content']}"
        # Attachment processing
        if echo_msg.get('attachments'):
            for att in echo_msg['attachments']:
                att['uid'] = str(uuid.uuid4())
                if 'name' in att:
                    ext = os.path.splitext(att['name'])[1]
                    new_filename = f"{uuid.uuid4().hex}{ext}"
                    new_url = os.path.join(ctx.get_temp_dir(), new_filename)
                    new_file_path = os.path.join(ctx.get_temp_dir(), new_filename)
                    original_url = att.get('url', '')
                    os.makedirs(ctx.get_temp_dir(), exist_ok=True)
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
        # Fill other optional fields
        if 'senderName' not in echo_msg or not echo_msg['senderName']:
            echo_msg['senderName'] = 'AI Assistant'
        if 'status' not in echo_msg or not echo_msg['status']:
            echo_msg['status'] = 'complete'
        if 'ext' not in echo_msg or not echo_msg['ext']:
            echo_msg['ext'] = {}
        if 'attachments' not in echo_msg or not echo_msg['attachments']:
            echo_msg['attachments'] = []
        if 'time' not in echo_msg or not echo_msg['time']:
            echo_msg['time'] = echo_msg['createAt']
        # Strong validation and logging
        required_fields = ['chatId', 'role', 'content', 'senderId', 'createAt']
        for f in required_fields:
            if not echo_msg.get(f):
                logger.error(f"echo_msg missing required field: {f}, content: {echo_msg}")
                return None
        logger.debug("build echo messge", echo_msg)
        return echo_msg

    def build_form_message(form_template, base_msg=None, chatId=None):
        """Construct form message, automatically fill all required fields"""
        now = int(time.time() * 1000)
        senderId = (base_msg.get('senderId') if base_msg and base_msg.get('senderId') else 'assistant')
        senderName = (base_msg.get('senderName') if base_msg and base_msg.get('senderName') else 'AI Assistant')
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

    def push_message(ctx: MainWindow, chatId, msg):
        """Type dispatch, automatically call db_chat_service.add_xxx_message, push to frontend, and log database write result"""
        logger.info(f"push_message echo_msg: {msg}")
        ctx.get_db_chat_service().push_message_to_chat(chatId, msg)

    logger.debug("start do push echo message")
    # 1. Construct and push echo message
    echo_msg = build_echo_message(ctx, message)
    if echo_msg: # Ensure echo_msg is not None
        push_message(ctx, chatId, echo_msg)
    # 2. Construct and push form template message
    try:
        template_path = os.path.join(os.path.dirname(__file__), '../../../agent/chats/templates/mcu_config_form.json')
        template_path = os.path.abspath(template_path)
        with open(template_path, 'r', encoding='utf-8') as f:
            form_template = json.load(f)
        form_msg = build_form_message(form_template, base_msg=echo_msg, chatId=chatId)
        push_message(ctx, chatId, form_msg)
    except Exception as e:
        logger.error(f"Failed to push form template message: {e}")
    # 3. Construct and push form template message
    try:
        template_path = os.path.join(os.path.dirname(__file__), '../../../agent/chats/templates/eval_system.json')
        template_path = os.path.abspath(template_path)
        with open(template_path, 'r', encoding='utf-8') as f:
            form_template = json.load(f)
        form_msg = build_form_message(form_template, base_msg=echo_msg, chatId=chatId)
        push_message(ctx, chatId, form_msg)
    except Exception as e:
        logger.error(f"Failed to push form template message: {e}")
    # 4. Construct and push agent notification message
    try:
        search_results_path = os.path.join(os.path.dirname(__file__), '../../../agent/chats/templates/search_results.json')
        search_results_path = os.path.abspath(search_results_path)
        with open(search_results_path, 'r', encoding='utf-8') as f:
            content = f.read()  # Read raw JSON text directly
        # New: Save content to database
        try:
            content_dict = json.loads(content)
        except Exception:
            content_dict = {"raw": content}
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.add_chat_notification(chatId, content_dict, int(time.time() * 1000), isRead=False)
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

def echo_and_push_message_async(chatId, message, request=None, params=None):
    """
    Asynchronously schedule message push logic, execute on main GUI thread after 1 second delay.
    This function is called from background thread, does not block current request, returns immediately.
    Uses threading.Timer to delay execution in background thread, then dispatches to main thread.
    """
    def delayed_push():
        post_to_main_thread(lambda: _do_push_and_echo(chatId, message, request, params))

    # Use Timer for async delayed execution, does not block current thread
    timer = threading.Timer(1.0, delayed_push)
    timer.daemon = True  # Set as daemon thread, won't prevent program exit
    timer.start()

# ===================== Other Handlers (Keep original structure, can be optimized later) =====================
@IPCHandlerRegistry.handler('get_chats')
def handle_get_chats(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle get chat list request, directly call db_chat_service.query_chats_by_user.
    """
    try:
        logger.debug(f"get chats handler called with request: {request}")
        userId = params.get('userId')
        deep = params.get('deep', False)
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.query_chats_by_user(userId=userId, deep=deep)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get chats handler: {e}")
        return create_error_response(request, 'GET_CHATS_ERROR', str(e))

@IPCHandlerRegistry.handler('search_chats')
def handle_search_chats(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle search chats by message content request.
    
    Params:
        userId (str): User ID to filter chats
        searchText (str): Text to search in message content
        deep (bool): Whether to include messages in response
    """
    try:
        logger.debug(f"search chats handler called with request: {request}")
        userId = params.get('userId')
        searchText = params.get('searchText', '')
        deep = params.get('deep', False)
        
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        
        result = db_chat_service.search_chats_by_message_content(
            userId=userId,
            searchText=searchText,
            deep=deep
        )
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in search chats handler: {e}")
        return create_error_response(request, 'SEARCH_CHATS_ERROR', str(e))

@IPCHandlerRegistry.handler('create_chat')
def handle_create_chat(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Create new chat session, directly call db_chat_service.create_chat.
    """
    logger.debug(f"create chat handler called with request: {request}")
    try:
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        # Split parameters
        members = params['members']
        name = params['name']
        chat_type = params.get('type', 'user-agent')
        avatar = params.get('avatar')
        agent_id = params.get('agent_id')
        lastMsg = params.get('lastMsg')
        lastMsgTime = params.get('lastMsgTime') or int(time.time() * 1000)
        unread = params.get('unread', 0)
        pinned = params.get('pinned', False)
        muted = params.get('muted', False)
        ext = params.get('ext')

        result = db_chat_service.create_chat(
            members=members,
            name=name,
            type=chat_type,
            avatar=avatar,
            agent_id=agent_id,
            lastMsg=lastMsg,
            lastMsgTime=lastMsgTime,
            unread=unread,
            pinned=pinned,
            muted=muted,
            ext=ext
        )
        logger.trace("create chat result" + str(result))
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in create_chat handler: {e}")
        return create_error_response(request, 'CREATE_CHAT_ERROR', str(e))

@IPCHandlerRegistry.handler('get_chat_messages')
def handle_get_chat_messages(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle get message list for specified chat request, call db_chat_service.query_messages_by_chat.
    """
    try:
        logger.debug(f"get_chat_messages handler called with request: {request}")
        chatId = params.get('chatId')
        limit = params.get('limit', 20)
        offset = params.get('offset', 0)
        reverse = params.get('reverse', False)
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.query_messages_by_chat(chatId=chatId, limit=limit, offset=offset, reverse=reverse)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get_chat_messages handler: {e}")
        return create_error_response(request, 'GET_CHAT_MESSAGES_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_chat')
def handle_delete_chat(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle delete chat request, call db_chat_service.delete_chat.
    """
    try:
        chatId = params.get('chatId')
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.delete_chat(chatId=chatId)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in delete_chat handler: {e}")
        return create_error_response(request, 'DELETE_CHAT_ERROR', str(e))

@IPCHandlerRegistry.handler('mark_message_as_read')
def handle_mark_message_as_read(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle batch mark messages as read request, call db_chat_service.mark_message_as_read.
    """
    try:
        messageIds = params.get('messageIds')
        userId = params.get('userId')
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.mark_message_as_read(messageIds=messageIds, userId=userId)
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
        ctx = get_handler_context(request, params)
        # Use ctx.get_temp_dir() instead of tempfile.gettempdir()
        file_path = os.path.join(ctx.get_temp_dir(), unique_name)
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
        # Verify file save success
        if os.path.exists(file_path):
            actual_size = os.path.getsize(file_path)
            logger.debug(f"File saved successfully: {file_path} (size: {actual_size} bytes)")
        else:
            logger.error(f"File save failed: {file_path}")
            raise Exception(f"Failed to save file to {file_path}")
        # Construct url
        url = os.path.join(ctx.get_temp_dir(), unique_name)
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
    Handle get file content request, read local file and return base64 data.
    Used for frontend preview or download local file attachments.
    """
    try:
        file_path = params.get('filePath')
        if not file_path:
            return create_error_response(request, 'MISSING_FILE_PATH', 'filePath parameter is required')
        # Handle pyqtfile:// protocol prefix
        if file_path.startswith('pyqtfile://'):
            file_path = file_path.replace('pyqtfile://', '')
        # Security check: ensure file path is within allowed directory
        temp_dir = tempfile.gettempdir()
        ctx = get_handler_context(request, params)
        allowed_dir = ctx.get_temp_dir() if True else temp_dir
        # Normalize path and check security
        file_path = os.path.abspath(file_path)
        allowed_dir = os.path.abspath(allowed_dir)
        if not file_path.startswith(allowed_dir):
            logger.warning(f"Access denied to file: {file_path} (not in allowed directory: {allowed_dir})")
            return create_error_response(request, 'ACCESS_DENIED', 'File access denied for security reasons')
        # Check if file exists
        if not os.path.exists(file_path):
            return create_error_response(request, 'FILE_NOT_FOUND', f'File not found: {file_path}')
        # Check file size to prevent reading oversized files
        file_size = os.path.getsize(file_path)
        max_size = 50 * 1024 * 1024  # 50MB limit
        if file_size > max_size:
            return create_error_response(request, 'FILE_TOO_LARGE', f'File too large: {file_size} bytes (max: {max_size})')
        # Read file and convert to base64
        import base64
        import mimetypes
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        # Get file MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        # Convert to base64
        base64_data = base64.b64encode(file_bytes).decode('utf-8')
        # Construct data URL
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
    Handle get file info request, return basic file information without reading content.
    Used for frontend to determine file type and size.
    """
    try:
        file_path = params.get('filePath')
        if not file_path:
            return create_error_response(request, 'MISSING_FILE_PATH', 'filePath parameter is required')
        # Handle pyqtfile:// protocol prefix
        if file_path.startswith('pyqtfile://'):
            file_path = file_path.replace('pyqtfile://', '')
        # Security check: ensure file path is within allowed directory
        temp_dir = tempfile.gettempdir()
        ctx = get_handler_context(request, params)
        allowed_dir = ctx.get_temp_dir() if True else temp_dir
        # Normalize path and check security
        file_path = os.path.abspath(file_path)
        allowed_dir = os.path.abspath(allowed_dir)
        if not file_path.startswith(allowed_dir):
            logger.warning(f"Access denied to file: {file_path} (not in allowed directory: {allowed_dir})")
            return create_error_response(request, 'ACCESS_DENIED', 'File access denied for security reasons')
        # Check if file exists
        if not os.path.exists(file_path):
            return create_error_response(request, 'FILE_NOT_FOUND', f'File not found: {file_path}')
        # Get file information
        import mimetypes
        file_stat = os.stat(file_path)
        file_size = file_stat.st_size
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1].lower()
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        # Determine if it's an image file
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico'}
        is_image = file_ext in image_extensions or mime_type.startswith('image/')
        # Determine if it's a text file
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
            'lastModified': int(file_stat.st_mtime * 1000),  # Convert to millisecond timestamp
            'created': int(file_stat.st_ctime * 1000)  # Convert to millisecond timestamp
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
    Handle chat form submit request, parameters include chatId, messageId, formId, formData.
    """
    try:
        logger.info(f"handle_chat_form_submit called with params: {request} {params}")
        chatId = params.get('chatId')
        messageId = params.get('messageId')
        formId = params.get('formId')
        formData = params.get('formData')
        if not chatId or not messageId or not formId or formData is None:
            logger.error("chat form submit invalid params")
            return create_error_response(request, 'INVALID_PARAMS', 'chatId, messageId, formId, formData are required')
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        # Assume db_chat_service has submit_form method, otherwise custom handling
        if hasattr(db_chat_service, 'submit_form'):
            result = db_chat_service.submit_form(chatId=chatId, messageId=messageId, formId=formId, formData=formData)
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
            logger.debug("a2a_send_chat form submit:", form_submit_req)
            # Lazy import for heavy dependencies
            from agent.chats.chat_utils import gui_a2a_send_chat
            request['params']['human'] = True
            gui_a2a_send_chat(ctx, form_submit_req)

            return create_success_response(request, result.get('data'))
        else:
            # If no submit_form method, simply log form data, can be customized
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
    Handle delete message request, call db_chat_service.delete_message.
    """
    try:
        chatId = params.get('chatId')
        messageId = params.get('messageId')
        if not chatId or not messageId:
            return create_error_response(request, 'INVALID_PARAMS', 'chatId, messageId are required')
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.delete_message(chatId=chatId, messageId=messageId)
        logger.debug("chat delete message  result: %s", result)
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in delete_message handler: {e}")
        return create_error_response(request, 'DELETE_MESSAGE_ERROR', str(e))

@IPCHandlerRegistry.handler('get_chat_notifications')
def handle_get_chat_notifications(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """
    Handle get chat notification list request, call db_chat_service.query_chat_notifications.
    """
    try:
        logger.debug(f"get_chat_notifications handler called with request: {request}")
        chatId = params.get('chatId')
        limit = params.get('limit', 20)
        offset = params.get('offset', 0)
        reverse = params.get('reverse', False)

        if not chatId:
            return create_error_response(request, 'INVALID_PARAMS', 'chatId is required')

        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        result = db_chat_service.query_chat_notifications(
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
    Handle clear chat unread count request, set chat's unread to 0.
    """
    try:
        chatId = params.get('chatId')
        if not chatId:
            return create_error_response(request, 'INVALID_PARAMS', 'chatId is required')
        ctx = get_handler_context(request, params)
        db_chat_service = ctx.get_db_chat_service()
        # Assume db_chat_service has set_chat_unread method, otherwise directly update chat's unread field
        if hasattr(db_chat_service, 'set_chat_unread'):
            result = db_chat_service.set_chat_unread(chatId=chatId, unread=0)
        else:
            # Compatibility: directly call update_chat or custom method
            if hasattr(db_chat_service, 'update_chat'):
                result = db_chat_service.update_chat(chatId=chatId, unread=0)
            else:
                return create_error_response(request, 'NOT_IMPLEMENTED', 'db_chat_service does not implement set_chat_unread or update_chat method')
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in clean_chat_unread handler: {e}")
        return create_error_response(request, 'CLEAN_CHAT_UNREAD_ERROR', str(e))

