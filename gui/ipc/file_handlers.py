"""
File operation IPC handlers for skill editor
Provides platform-aware file dialog and file I/O operations
"""

import os
import json
from typing import Any, Optional, Dict
from .types import IPCRequest, IPCResponse, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger


def validate_params(params: Optional[Dict[str, Any]], required: list[str]) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """验证请求参数"""
    if not params:
        return False, None, f"Missing required parameters: {', '.join(required)}"
    
    missing = [param for param in required if param not in params]
    if missing:
        return False, None, f"Missing required parameters: {', '.join(missing)}"
    
    return True, params, None


@IPCHandlerRegistry.handler('show_open_dialog')
def handle_show_open_dialog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理显示文件打开对话框请求
    
    Args:
        request: IPC 请求对象
        params: 请求参数，包含 filters 等选项
        
    Returns:
        IPCResponse: 包含选中文件路径的响应
    """
    try:
        logger.debug(f"Show open dialog handler called with request: {request}")
        
        from tkinter import filedialog
        import tkinter as tk
        
        # 创建隐藏的根窗口
        root = tk.Tk()
        root.withdraw()
        
        # 获取过滤器参数
        filters = params.get('filters', []) if params else []
        file_types = []
        
        for filter_item in filters:
            name = filter_item.get('name', 'All Files')
            extensions = filter_item.get('extensions', ['*'])
            # 转换为 tkinter 格式
            ext_pattern = ';'.join([f'*.{ext}' for ext in extensions])
            file_types.append((name, ext_pattern))
        
        if not file_types:
            file_types = [('JSON Files', '*.json'), ('All Files', '*.*')]
        
        # 显示文件对话框
        file_path = filedialog.askopenfilename(
            title="Open Skill File",
            filetypes=file_types
        )
        
        # 清理根窗口
        root.destroy()
        
        if file_path:
            return create_success_response(request, {
                'filePath': file_path,
                'fileName': os.path.basename(file_path)
            })
        else:
            return create_success_response(request, {
                'cancelled': True
            })
            
    except Exception as e:
        logger.error(f"Error in show_open_dialog handler: {e}")
        return create_error_response(
            request,
            'SHOW_OPEN_DIALOG_ERROR',
            f"Error showing open dialog: {str(e)}"
        )


@IPCHandlerRegistry.handler('show_save_dialog')
def handle_show_save_dialog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理显示文件保存对话框请求"""
    try:
        logger.debug(f"Show save dialog handler called with request: {request}")
        
        from tkinter import filedialog
        import tkinter as tk
        
        root = tk.Tk()
        root.withdraw()
        
        # 获取参数
        default_filename = params.get('defaultFilename', 'untitled.json') if params else 'untitled.json'
        filters = params.get('filters', []) if params else []
        file_types = []
        
        for filter_item in filters:
            name = filter_item.get('name', 'All Files')
            extensions = filter_item.get('extensions', ['*'])
            ext_pattern = ';'.join([f'*.{ext}' for ext in extensions])
            file_types.append((name, ext_pattern))
        
        if not file_types:
            file_types = [('JSON Files', '*.json'), ('All Files', '*.*')]
        
        # 显示保存对话框
        file_path = filedialog.asksaveasfilename(
            title="Save Skill File",
            defaultextension=".json",
            filetypes=file_types,
            initialvalue=default_filename
        )
        
        root.destroy()
        
        if file_path:
            return create_success_response(request, {
                'filePath': file_path,
                'fileName': os.path.basename(file_path)
            })
        else:
            return create_success_response(request, {
                'cancelled': True
            })
            
    except Exception as e:
        logger.error(f"Error in show_save_dialog handler: {e}")
        return create_error_response(
            request,
            'SHOW_SAVE_DIALOG_ERROR',
            f"Error showing save dialog: {str(e)}"
        )


@IPCHandlerRegistry.handler('read_skill_file')
def handle_read_skill_file(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理读取技能文件请求
    
    Args:
        request: IPC 请求对象
        params: 请求参数，包含 filePath
        
    Returns:
        IPCResponse: 包含文件内容的响应
    """
    try:
        logger.debug(f"Read skill file handler called with request: {request}")
        
        # 验证参数
        is_valid, data, error = validate_params(params, ['filePath'])
        if not is_valid:
            logger.warning(f"Invalid parameters for read skill file: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        
        file_path = data['filePath']
        
        # 安全检查：确保文件存在
        if not os.path.exists(file_path):
            return create_error_response(
                request,
                'FILE_NOT_FOUND',
                f'File not found: {file_path}'
            )
        
        # 检查文件扩展名
        if not file_path.lower().endswith('.json'):
            return create_error_response(
                request,
                'INVALID_FILE_TYPE',
                'Only JSON files are supported'
            )
        
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 验证 JSON 格式
            json.loads(content)  # 验证是否为有效 JSON
            
            return create_success_response(request, {
                'content': content,
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'fileSize': os.path.getsize(file_path)
            })
            
        except json.JSONDecodeError as e:
            return create_error_response(
                request,
                'INVALID_JSON',
                f'Invalid JSON file: {str(e)}'
            )
        except UnicodeDecodeError as e:
            return create_error_response(
                request,
                'ENCODING_ERROR',
                f'File encoding error: {str(e)}'
            )
            
    except Exception as e:
        logger.error(f"Error in read_skill_file handler: {e}")
        return create_error_response(
            request,
            'READ_SKILL_FILE_ERROR',
            f"Error reading skill file: {str(e)}"
        )


@IPCHandlerRegistry.handler('write_skill_file')
def handle_write_skill_file(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理写入技能文件请求
    
    Args:
        request: IPC 请求对象
        params: 请求参数，包含 filePath 和 content
        
    Returns:
        IPCResponse: 写入结果响应
    """
    try:
        logger.debug(f"Write skill file handler called with request: {request}")
        
        # 验证参数
        is_valid, data, error = validate_params(params, ['filePath', 'content'])
        if not is_valid:
            logger.warning(f"Invalid parameters for write skill file: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        
        file_path = data['filePath']
        content = data['content']
        
        # 验证 JSON 内容
        try:
            if isinstance(content, str):
                json.loads(content)  # 验证 JSON 格式
            else:
                content = json.dumps(content, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return create_error_response(
                request,
                'INVALID_JSON',
                f'Invalid JSON content: {str(e)}'
            )
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 写入文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return create_success_response(request, {
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'fileSize': os.path.getsize(file_path),
                'success': True
            })
            
        except IOError as e:
            return create_error_response(
                request,
                'WRITE_ERROR',
                f'Failed to write file: {str(e)}'
            )
            
    except Exception as e:
        logger.error(f"Error in write_skill_file handler: {e}")
        return create_error_response(
            request,
            'WRITE_SKILL_FILE_ERROR',
            f"Error writing skill file: {str(e)}"
        )


logger.info("File operation handlers registered successfully")
