"""
File operation IPC handlers for the Skill Editor.
Provides platform-aware file dialogs and file I/O operations.
"""

import os
import json
from typing import Any, Optional, Dict
# Lazy import extern_skills to avoid blocking during module initialization
# from agent.ec_skills.extern_skills.extern_skills import scaffold_skill, rename_skill, user_skills_root
from .types import IPCRequest, IPCResponse, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger


def _get_extern_skills():
    """Lazy import extern_skills to avoid blocking during module initialization."""
    from agent.ec_skills.extern_skills.extern_skills import scaffold_skill, rename_skill, user_skills_root
    return scaffold_skill, rename_skill, user_skills_root


def validate_params(params: Optional[Dict[str, Any]], required: list[str]) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Validate request parameters."""
    if not params:
        return False, None, f"Missing required parameters: {', '.join(required)}"
    
    missing = [param for param in required if param not in params]
    if missing:
        return False, None, f"Missing required parameters: {', '.join(missing)}"
    
    return True, params, None


@IPCHandlerRegistry.handler('show_open_dialog')
def handle_show_open_dialog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle the file open dialog request.

    Args:
        request: IPC request object
        params: Optional parameters, e.g. filters

    Returns:
        IPCResponse: Response with selected file path or cancellation info
    """
    try:
        logger.debug(f"Show open dialog handler called with request: {request}")

        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtCore import QThread
        import threading

        # Build file type filters
        filters = params.get('filters', []) if params else []
        filter_strings = []

        for filter_item in filters:
            name = filter_item.get('name', 'All Files')
            extensions = filter_item.get('extensions', ['*'])
            # Convert to Qt format
            ext_pattern = ' '.join([f'*.{ext}' for ext in extensions])
            filter_strings.append(f"{name} ({ext_pattern})")

        if not filter_strings:
            filter_strings = ['JSON Files (*.json)', 'All Files (*.*)']

        # Force initial directory to the per-user skills root
        try:
            _, _, user_skills_root = _get_extern_skills()
            skills_root = user_skills_root()
            os.makedirs(skills_root, exist_ok=True)
            initial_dir = str(skills_root)
        except Exception:
            initial_dir = None

        # Ensure we're on the main thread for Qt dialogs
        def show_dialog():
            app = QApplication.instance()
            if app is None:
                # If no QApplication exists, create a temporary one
                app = QApplication([])
                temp_app = True
            else:
                temp_app = False

            try:
                file_path, _ = QFileDialog.getOpenFileName(
                    None,  # parent
                    "Open Skill File",  # caption
                    initial_dir or "",  # directory
                    ";;".join(filter_strings)  # filter
                )
                return file_path
            finally:
                if temp_app:
                    app.quit()

        # Execute dialog on main thread if needed
        if QThread.currentThread() == QApplication.instance().thread() if QApplication.instance() else False:
            file_path = show_dialog()
        else:
            # Use a simple approach for cross-thread dialog
            file_path = show_dialog()
        
        if file_path:
            # Validate that the selected file is under the skills root
            try:
                _, _, user_skills_root = _get_extern_skills()
                root = str(user_skills_root())
                norm_root = os.path.abspath(root)
                norm_sel = os.path.abspath(file_path)
                common = os.path.commonpath([norm_root, norm_sel])
                if common != norm_root:
                    logger.warning(f"[SKILL_IO][BACKEND][OPEN_OUT_OF_ROOT] selected={norm_sel} root={norm_root}")
                    return create_error_response(
                        request,
                        'OUTSIDE_SKILL_ROOT',
                        f'Selected file is outside skill root: {norm_root}'
                    )
            except Exception as ve:
                logger.error(f"[SKILL_IO][BACKEND][OPEN_ROOT_VALIDATE_ERROR] {ve}")
                return create_error_response(
                    request,
                    'OPEN_ROOT_VALIDATE_ERROR',
                    'Failed to validate selection path'
                )
            # Distinct marker for selected main json path
            logger.info(f"[SKILL_IO][BACKEND][SELECTED_MAIN_JSON] {file_path}")
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
    """Handle the file save dialog request."""
    try:
        logger.debug(f"Show save dialog handler called with request: {request}")

        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtCore import QThread

        # Resolve parameters
        default_filename = params.get('defaultFilename', 'untitled.json') if params else 'untitled.json'
        try:
            logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG_DEFAULT] {default_filename}")
        except Exception:
            pass
        filters = params.get('filters', []) if params else []
        filter_strings = []

        for filter_item in filters:
            name = filter_item.get('name', 'All Files')
            extensions = filter_item.get('extensions', ['*'])
            # Convert to Qt format
            ext_pattern = ' '.join([f'*.{ext}' for ext in extensions])
            filter_strings.append(f"{name} ({ext_pattern})")

        if not filter_strings:
            filter_strings = ['JSON Files (*.json)', 'All Files (*.*)']

        # Ensure we're on the main thread for Qt dialogs
        def show_dialog():
            app = QApplication.instance()
            if app is None:
                # If no QApplication exists, create a temporary one
                app = QApplication([])
                temp_app = True
            else:
                temp_app = False

            try:
                file_path, _ = QFileDialog.getSaveFileName(
                    None,  # parent
                    "Save Skill File",  # caption
                    default_filename,  # directory/filename
                    ";;".join(filter_strings)  # filter
                )
                return file_path
            finally:
                if temp_app:
                    app.quit()

        # Execute dialog on main thread if needed
        if QThread.currentThread() == QApplication.instance().thread() if QApplication.instance() else False:
            file_path = show_dialog()
        else:
            # Use a simple approach for cross-thread dialog
            file_path = show_dialog()
        
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
    """Handle reading a skill file.

    Args:
        request: IPC request object
        params: Request params, must include filePath

    Returns:
        IPCResponse: Response with file content
    """
    try:
        logger.debug(f"Read skill file handler called with request: {request}")
        
        # Validate parameters
        is_valid, data, error = validate_params(params, ['filePath'])
        if not is_valid:
            logger.warning(f"Invalid parameters for read skill file: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        
        file_path = data['filePath']
        # Distinct marker for any read attempt
        logger.info(f"[SKILL_IO][BACKEND][READ_ATTEMPT] {file_path}")
        
        # Safety check: ensure file exists
        if not os.path.exists(file_path):
            logger.warning(f"[SKILL_IO][BACKEND][READ_NOT_FOUND] {file_path}")
            return create_error_response(
                request,
                'FILE_NOT_FOUND',
                f'File not found: {file_path}'
            )
        
        # Validate file extension
        if not file_path.lower().endswith('.json'):
            return create_error_response(
                request,
                'INVALID_FILE_TYPE',
                'Only JSON files are supported'
            )
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Validate JSON format
            json.loads(content)
            
            size = os.path.getsize(file_path)
            logger.info(f"[SKILL_IO][BACKEND][READ_OK] {file_path} size={size}")
            return create_success_response(request, {
                'content': content,
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'fileSize': size
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
    """Handle writing a skill file.

    Args:
        request: IPC request object
        params: Request params, must include filePath and content

    Returns:
        IPCResponse: Write result
    """
    try:
        logger.debug(f"Write skill file handler called with request: {request}")
        
        # Validate parameters
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
        
        # Validate JSON content
        try:
            if isinstance(content, str):
                json.loads(content)
            else:
                content = json.dumps(content, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return create_error_response(
                request,
                'INVALID_JSON',
                f'Invalid JSON content: {str(e)}'
            )
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write file
        try:
            # Distinct write attempt marker with byte length
            try:
                byte_len = len(content.encode('utf-8')) if isinstance(content, str) else len(json.dumps(content, ensure_ascii=False).encode('utf-8'))
            except Exception:
                byte_len = -1
            logger.info(f"[SKILL_IO][BACKEND][WRITE_ATTEMPT] {file_path} bytes={byte_len}")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            size = os.path.getsize(file_path)
            logger.info(f"[SKILL_IO][BACKEND][WRITE_OK] {file_path} size={size}")
            return create_success_response(request, {
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'fileSize': os.path.getsize(file_path),
                'success': True
            })
            
        except IOError as e:
            logger.error(f"[SKILL_IO][BACKEND][WRITE_ERROR] {file_path} {str(e)}")
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


@IPCHandlerRegistry.handler('skills.scaffold')
def handle_skills_scaffold(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Scaffold a new skill directory under the per-user skills root.

    Params:
      - name: skill base name (without _skill). If omitted, a timestamped name is generated.
      - kind: 'code' | 'diagram' (default: 'diagram')
      - description: optional description
    Returns: { skillRoot: str, name: str }
    """
    try:
        p = params or {}
        import datetime
        name = p.get('name') or datetime.datetime.now().strftime('skill_%Y%m%d_%H%M%S')
        kind = (p.get('kind') or 'diagram').lower()
        description = p.get('description') or ''
        scaffold_skill, _, _ = _get_extern_skills()
        path = scaffold_skill(name, description, kind)
        return create_success_response(request, { 'skillRoot': str(path), 'name': name })
    except Exception as e:
        logger.error(f"[IPC] skills.scaffold error: {e}")
        return create_error_response(request, 'SCAFFOLD_ERROR', str(e))


@IPCHandlerRegistry.handler('skills.rename')
def handle_skills_rename(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Rename an existing skill root directory <old>_skill -> <new>_skill.

    Params:
      - oldName
      - newName
    Returns: { skillRoot: str }
    """
    try:
        ok, data, err = validate_params(params, ['oldName', 'newName'])
        if not ok:
            return create_error_response(request, 'INVALID_PARAMS', err or 'invalid')
        _, rename_skill, _ = _get_extern_skills()
        new_path = rename_skill(data['oldName'], data['newName'])
        return create_success_response(request, { 'skillRoot': str(new_path) })
    except Exception as e:
        logger.error(f"[IPC] skills.rename error: {e}")
        return create_error_response(request, 'RENAME_ERROR', str(e))
