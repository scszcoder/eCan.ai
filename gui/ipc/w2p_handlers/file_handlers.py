"""
File operation IPC handlers for the Skill Editor.
Provides platform-aware file dialogs and file I/O operations.
"""

import os
import json
import sys
import subprocess
from typing import Any, Optional, Dict
# Lazy import extern_skills to avoid blocking during module initialization
# from agent.ec_skills.extern_skills.extern_skills import scaffold_skill, rename_skill, user_skills_root
from ..types import IPCRequest, IPCResponse, create_success_response, create_error_response
from ..registry import IPCHandlerRegistry
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
            logger.info(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Default directory: {initial_dir}")
            logger.info(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Directory exists: {os.path.exists(initial_dir)}")
        except Exception as e:
            logger.error(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Failed to get skills root: {e}", exc_info=True)
            initial_dir = ""

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
                # 允许用户选择文件或文件夹
                start_dir = initial_dir if initial_dir and os.path.exists(initial_dir) else os.getcwd()
                logger.info(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Opening dialog with directory: {start_dir}")
                
                # 使用文件选择对话框，允许选择 JSON 文件
                file_path, _ = QFileDialog.getOpenFileName(
                    None,  # parent
                    "Select Skill File",  # caption
                    start_dir,  # directory
                    "Skill Files (*.json);;All Files (*.*)"  # filter
                )
                return file_path
            finally:
                if temp_app:
                    app.quit()

        # Execute dialog on main thread if needed
        if QThread.currentThread() == QApplication.instance().thread() if QApplication.instance() else False:
            folder_path = show_dialog()
        else:
            # Use a simple approach for cross-thread dialog
            folder_path = show_dialog()
        
        if folder_path:
            # 用户选择了文件
            file_path = folder_path
            logger.info(f"[SKILL_IO][BACKEND][FILE_SELECTED] {file_path}")
            
            # 验证文件存在
            if not os.path.exists(file_path):
                logger.warning(f"[SKILL_IO][BACKEND][FILE_NOT_FOUND] {file_path}")
                return create_error_response(
                    request,
                    'FILE_NOT_FOUND',
                    f'Selected file does not exist: {file_path}'
                )
            # Note: We no longer restrict files to skills root directory
            # Users can open skill files from any directory
            # The file will be saved back to its original location
            # Distinct marker for selected main json path
            logger.info(f"[SKILL_IO][BACKEND][SELECTED_MAIN_JSON] {file_path}")
            
            # 提取 skillName：从文件路径向上查找 skill 文件夹
            # 例如：my_skills/abcd/diagram_dir/abcd_skill.json → skillName = "abcd"
            # 或者：my_skills/abcd/abcd_skill.json → skillName = "abcd"
            file_dir = os.path.dirname(file_path)
            parent_dir = os.path.dirname(file_dir)
            
            # 如果文件在 diagram_dir 中，skill 文件夹是 diagram_dir 的父目录
            if os.path.basename(file_dir) == 'diagram_dir':
                skill_folder_name = os.path.basename(parent_dir)
            else:
                # 否则，skill 文件夹就是文件所在目录
                skill_folder_name = os.path.basename(file_dir)
            
            logger.info(f"[SKILL_IO][BACKEND][SKILL_NAME_FROM_PATH] {skill_folder_name}")
            
            return create_success_response(request, {
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'skillName': skill_folder_name
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
        
        # Remove .json suffix for display
        display_name = default_filename[:-5] if default_filename.endswith('.json') else default_filename
        logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Default filename: {display_name}")
        

        # Get per-user skills root directory
        try:
            _, _, user_skills_root = _get_extern_skills()
            skills_root = user_skills_root()
            os.makedirs(skills_root, exist_ok=True)
            initial_dir = str(skills_root)
            logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Skills directory: {initial_dir}")
        except Exception as e:
            logger.error(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Failed to get skills root: {e}", exc_info=True)
            initial_dir = ""

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
                start_dir = initial_dir if initial_dir and os.path.exists(initial_dir) else os.getcwd()
                os.makedirs(start_dir, exist_ok=True)
                
                # Generate unique default name if directory already exists
                # This prevents macOS from entering an existing directory
                default_skill_name = display_name
                counter = 1
                while os.path.isdir(os.path.join(start_dir, default_skill_name)) and counter <= 100:
                    counter += 1
                    default_skill_name = f"{display_name}_{counter}"
                
                if default_skill_name != display_name:
                    logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Using unique name: {default_skill_name}")
                
                dialog_path = os.path.join(start_dir, default_skill_name)
                
                file_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Skill",
                    dialog_path,
                    "",
                    None,
                    QFileDialog.Option.DontConfirmOverwrite
                )
                
                # Add .json suffix if not present
                if file_path and not file_path.endswith('.json'):
                    file_path = file_path + '.json'
                
                logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Selected: {file_path or 'cancelled'}")
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
        original_path = file_path  # Save original for logging
        
        # Convert relative path to absolute path
        if not os.path.isabs(file_path):
            from app_context import AppContext
            app_context = AppContext()
            base_dir = app_context.get_app_dir()
            file_path = os.path.join(base_dir, file_path)
        
        # Distinct marker for any read attempt
        logger.info(f"[SKILL_IO][BACKEND][READ_ATTEMPT] Original: {original_path} -> Resolved: {file_path}")
        
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
        # logger.debug(f"Write skill file handler called with request: {request}")
        
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
        
        # Extract skill name from file path
        # IMPORTANT: Preserve the original file path - do not redirect to my_skills directory
        # This allows users to open and save skill files from any directory
        file_name = os.path.basename(file_path)
        parent_dir = os.path.dirname(file_path)
        
        # Extract skill name for metadata purposes only (not for path manipulation)
        skill_name = file_name[:-5] if file_name.endswith('.json') else file_name
        
        # Remove known suffixes to get the base skill name
        if skill_name.endswith('_data_mapping'):
            skill_name = skill_name[:-13]
        elif skill_name.endswith('_skill_bundle'):
            skill_name = skill_name[:-13]
        elif skill_name.endswith('_skill'):
            skill_name = skill_name[:-6]
        
        logger.info(f"[SKILL_IO][BACKEND] Skill: {skill_name}, Path: {file_path} (preserving original path)")
        
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
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            if not os.path.exists(file_path):
                logger.error(f"[SKILL_IO][BACKEND] File does not exist after write: {file_path}")
                raise IOError(f"Failed to write file: {file_path}")
            
            # Sync with skill database if it's a skill workflow JSON file
            if file_path.endswith('_skill.json'):
                logger.info(f"[SKILL_IO][BACKEND] Syncing skill to database: {file_path}")
                try:
                    from gui.ipc.w2p_handlers.skill_handler import sync_skill_from_file
                    result = sync_skill_from_file(file_path)
                    
                    if result.get('success'):
                        operation = result.get('operation', 'unknown')
                        skill_id = result.get('skill_id', 'unknown')
                        logger.info(f"[SKILL_IO][BACKEND] ✅ Skill {operation}d successfully (ID: {skill_id})")
                    else:
                        logger.warning(f"[SKILL_IO][BACKEND] ❌ Failed to sync skill: {result.get('error')}")
                except Exception as sync_error:
                    logger.error(f"[SKILL_IO][BACKEND] ❌ Error syncing skill to database: {sync_error}", exc_info=True)
            
            # Extract skill name without suffix for frontend
            final_file_name = os.path.basename(file_path)
            if final_file_name.endswith('_skill.json'):
                skill_name_only = final_file_name[:-11]
            elif final_file_name.endswith('_data_mapping.json'):
                skill_name_only = final_file_name[:-18]
            elif final_file_name.endswith('_skill_bundle.json'):
                skill_name_only = final_file_name[:-18]
            else:
                skill_name_only = final_file_name[:-5] if final_file_name.endswith('.json') else final_file_name
            
            return create_success_response(request, {
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'skillName': skill_name_only,  # 需求4: 返回不带后缀的 skill 名称
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
        
        old_name = data['oldName']
        new_name = data['newName']
        
        # Rename the skill directory
        _, rename_skill, _ = _get_extern_skills()
        new_path = rename_skill(old_name, new_name)
        
        # Update skill database if old skill exists
        try:
            from gui.ipc.w2p_handlers.skill_handler import sync_skill_from_file
            from gui.context.app_context import AppContext
            
            # Construct old and new skill file paths
            old_skill_path = str(new_path).replace(f'/{new_name}_skill/', f'/{old_name}_skill/')
            old_skill_file = f"{old_skill_path}/diagram_dir/{old_name}_skill.json"
            new_skill_file = f"{new_path}/diagram_dir/{new_name}_skill.json"
            
            logger.info(f"[SKILL_RENAME] Checking for existing skill at: {old_skill_file}")
            
            # Get skill service to check if old skill exists in database
            main_window = AppContext.get_main_window()
            if main_window and hasattr(main_window, 'ec_db_mgr') and main_window.ec_db_mgr:
                skill_service = main_window.ec_db_mgr.skill_service
                if skill_service:
                    # Check if skill exists by old path
                    existing_skill = skill_service.get_skill_by_path(old_skill_file)
                    
                    if existing_skill.get('success') and existing_skill.get('data'):
                        logger.info(f"[SKILL_RENAME] Found existing skill in database, updating path to: {new_skill_file}")
                        
                        # Check if new skill file exists
                        if os.path.exists(new_skill_file):
                            # Sync the renamed skill file to update database
                            sync_result = sync_skill_from_file(new_skill_file)
                            
                            if sync_result.get('success'):
                                logger.info(f"[SKILL_RENAME] ✅ Skill database updated successfully")
                            else:
                                logger.warning(f"[SKILL_RENAME] ⚠️ Failed to update skill database: {sync_result.get('error')}")
                        else:
                            logger.warning(f"[SKILL_RENAME] ⚠️ New skill file not found: {new_skill_file}")
                    else:
                        logger.info(f"[SKILL_RENAME] No existing skill found in database for old path")
        except Exception as sync_error:
            # Don't fail the rename if database sync fails
            logger.warning(f"[SKILL_RENAME] Error syncing renamed skill to database: {sync_error}")
        
        return create_success_response(request, { 'skillRoot': str(new_path) })
    except Exception as e:
        logger.error(f"[IPC] skills.rename error: {e}")
        return create_error_response(request, 'RENAME_ERROR', str(e))


@IPCHandlerRegistry.handler('open_folder')
def handle_open_folder(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Open folder in system file explorer.
    
    Args:
        request: IPC request object
        params: Parameters containing 'path' - folder path to open
        
    Returns:
        IPCResponse: Response indicating success or failure
    """
    try:
        ok, data, err = validate_params(params, ['path'])
        if not ok:
            return create_error_response(request, 'INVALID_PARAMS', err or 'Path is required')
        
        path = data['path']
        
        # Normalize path
        path = os.path.expanduser(path)
        path = os.path.abspath(path)
        
        # Check if path exists
        if not os.path.exists(path):
            logger.warning(f"[OPEN_FOLDER] Path does not exist: {path}")
            return create_error_response(request, 'PATH_NOT_FOUND', f'Path does not exist: {path}')
        
        # If path is a file, get its directory
        if os.path.isfile(path):
            path = os.path.dirname(path)
        
        logger.info(f"[OPEN_FOLDER] Opening folder: {path}")
        
        # Open folder based on platform
        if sys.platform == 'darwin':  # macOS
            subprocess.run(['open', path], check=True)
        elif sys.platform == 'win32':  # Windows
            os.startfile(path)
        else:  # Linux and other Unix-like systems
            subprocess.run(['xdg-open', path], check=True)
        
        return create_success_response(request, {'success': True, 'path': path})
        
    except subprocess.CalledProcessError as e:
        logger.error(f"[OPEN_FOLDER] Failed to open folder: {e}")
        return create_error_response(request, 'OPEN_FOLDER_ERROR', f'Failed to open folder: {str(e)}')
    except Exception as e:
        logger.error(f"[OPEN_FOLDER] Error: {e}")
        return create_error_response(request, 'OPEN_FOLDER_ERROR', str(e))
