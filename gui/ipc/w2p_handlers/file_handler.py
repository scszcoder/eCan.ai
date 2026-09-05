"""
File operation IPC handlers for the Skill Editor.
Provides platform-aware file dialogs and file I/O operations.
"""

import os
import json
import sys
import subprocess
from typing import Any, Optional, Dict
from pathlib import Path
# Lazy import extern_skills to avoid blocking during module initialization
# from agent.ec_skills.extern_skills.extern_skills import scaffold_skill, rename_skill, user_skills_root
from ..types import IPCRequest, IPCResponse, create_success_response, create_error_response
from ..registry import IPCHandlerRegistry
from gui.ipc.context_bridge import get_handler_context
from utils.logger_helper import logger_helper as logger


def _get_extern_skills(request=None, params=None):
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
    # File dialogs are not available in web mode (headless)
    if os.getenv('ECAN_MODE') == 'web':
        return create_error_response(
            request,
            'NOT_SUPPORTED',
            'File dialogs are not available in web/headless mode. Use file path parameters instead.'
        )
    
    try:
        logger.debug(f"Show open dialog handler called with request: {request}")

        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtCore import QThread, QObject, Signal, QMetaObject, Qt
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
            _, _, user_skills_root = _get_extern_skills(request, params)
            skills_root = user_skills_root()
            os.makedirs(skills_root, exist_ok=True)
            initial_dir = str(skills_root)
            logger.info(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Default directory: {initial_dir}")
            logger.info(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Directory exists: {os.path.exists(initial_dir)}")
        except Exception as e:
            logger.error(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Failed to get skills root: {e}", exc_info=True)
            initial_dir = ""

        # Prepare dialog parameters
        start_dir = initial_dir if initial_dir and os.path.exists(initial_dir) else os.getcwd()
        logger.info(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Opening dialog with directory: {start_dir}")
        
        # Check if we're already on the main thread
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            # Already on main thread, call directly
            file_path, _ = QFileDialog.getOpenFileName(
                None,
                "Select Skill File",
                start_dir,
                "Skill Files (*.json);;All Files (*.*)"
            )
            folder_path = file_path
        else:
            # Not on main thread, use signal/slot with threading.Event
            if not app:
                logger.error("[SKILL_IO][BACKEND][OPEN_DIALOG] No QApplication instance available")
                return create_error_response(
                    request,
                    'NO_QAPPLICATION',
                    'Qt application not initialized'
                )
            
            # Helper class for cross-thread dialog
            class DialogHelper(QObject):
                show_dialog = Signal(str)
                
                def __init__(self):
                    super().__init__()
                    self.result = None
                    self.done_event = threading.Event()
                    self.show_dialog.connect(self._show_dialog_slot, Qt.ConnectionType.QueuedConnection)
                    
                def _show_dialog_slot(self, directory):
                    try:
                        file_path, _ = QFileDialog.getOpenFileName(
                            None,
                            "Select Skill File",
                            directory,
                            "Skill Files (*.json);;All Files (*.*)"
                        )
                        self.result = file_path
                    except Exception as e:
                        logger.error(f"[SKILL_IO][BACKEND][OPEN_DIALOG] Error in dialog: {e}", exc_info=True)
                        self.result = None
                    finally:
                        self.done_event.set()
            
            # Create helper and move to main thread
            helper = DialogHelper()
            helper.moveToThread(app.thread())
            
            # Emit signal and wait for result
            helper.show_dialog.emit(start_dir)
            # Human-scale timeout: the dialog blocks on the user browsing and
            # typing a filename (often via IME) — must comfortably exceed that.
            # The frontend waits 630s (file-api.ts DIALOG_TIMEOUT_MS) so this
            # timeout response still reaches it.
            if not helper.done_event.wait(timeout=600):
                logger.error("[SKILL_IO][BACKEND][OPEN_DIALOG] Dialog timeout")
                return create_error_response(
                    request,
                    'DIALOG_TIMEOUT',
                    'File dialog timed out'
                )
            
            folder_path = helper.result
        
        folder_path = folder_path if folder_path else None
        
        if folder_path:
            # ç”¨æˆ·é€‰æ‹©äº†æ–‡ä»¶
            file_path = folder_path
            logger.info(f"[SKILL_IO][BACKEND][FILE_SELECTED] {file_path}")
            
            # éªŒè¯æ–‡ä»¶å­˜åœ¨
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
            
            # æå– skillNameï¼šä»Žæ–‡ä»¶è·¯å¾„å‘ä¸ŠæŸ¥æ‰¾ skill æ–‡ä»¶å¤¹
            # ä¾‹å¦‚ï¼šmy_skills/abcd/diagram_dir/abcd_skill.json â†’ skillName = "abcd"
            # æˆ–è€…ï¼šmy_skills/abcd/abcd_skill.json â†’ skillName = "abcd"
            file_dir = os.path.dirname(file_path)
            parent_dir = os.path.dirname(file_dir)
            
            # å¦‚æžœæ–‡ä»¶åœ¨ diagram_dir ä¸­ï¼Œskill æ–‡ä»¶å¤¹æ˜¯ diagram_dir çš„çˆ¶ç›®å½•
            if os.path.basename(file_dir) == 'diagram_dir':
                skill_folder_name = os.path.basename(parent_dir)
            else:
                # å¦åˆ™ï¼Œskill æ–‡ä»¶å¤¹å°±æ˜¯æ–‡ä»¶æ‰€åœ¨ç›®å½•
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
    # File dialogs are not available in web mode (headless)
    if os.getenv('ECAN_MODE') == 'web':
        return create_error_response(
            request,
            'NOT_SUPPORTED',
            'File dialogs are not available in web/headless mode. Use file path parameters instead.'
        )
    
    try:
        logger.debug(f"Show save dialog handler called with request: {request}")

        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtCore import QThread, QObject, Signal, Qt
        import threading

        # Resolve parameters
        default_filename = params.get('defaultFilename', 'untitled.json') if params else 'untitled.json'
        
        # Remove .json suffix for display
        display_name = default_filename[:-5] if default_filename.endswith('.json') else default_filename
        logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Default filename: {display_name}")
        

        # Get per-user skills root directory
        try:
            _, _, user_skills_root = _get_extern_skills(request, params)
            skills_root = user_skills_root()
            os.makedirs(skills_root, exist_ok=True)
            initial_dir = str(skills_root)
            logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Skills directory: {initial_dir}")
        except Exception as e:
            logger.error(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Failed to get skills root: {e}", exc_info=True)
            initial_dir = ""

        # Prepare dialog parameters
        start_dir = initial_dir if initial_dir and os.path.exists(initial_dir) else os.getcwd()
        os.makedirs(start_dir, exist_ok=True)
        
        # Use the original filename with .json extension
        filename_with_ext = display_name + '.json' if not display_name.endswith('.json') else display_name
        dialog_path = os.path.join(start_dir, filename_with_ext)
        
        # Check if we're already on the main thread
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            # Already on main thread, call directly
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                "Save Skill",
                dialog_path,
                "JSON Files (*.json)",
                None,
                QFileDialog.Option.DontConfirmOverwrite
            )
            
            # Add .json suffix if not present
            if file_path and not file_path.endswith('.json'):
                file_path = file_path + '.json'
        else:
            # Not on main thread, use signal/slot with threading.Event
            if not app:
                logger.error("[SKILL_IO][BACKEND][SAVE_DIALOG] No QApplication instance available")
                return create_error_response(
                    request,
                    'NO_QAPPLICATION',
                    'Qt application not initialized'
                )
            
            # Helper class for cross-thread dialog
            class DialogHelper(QObject):
                show_dialog = Signal(str)
                
                def __init__(self):
                    super().__init__()
                    self.result = None
                    self.done_event = threading.Event()
                    self.show_dialog.connect(self._show_dialog_slot, Qt.ConnectionType.QueuedConnection)
                    
                def _show_dialog_slot(self, path):
                    try:
                        file_path, _ = QFileDialog.getSaveFileName(
                            None,
                            "Save Skill",
                            path,
                            "JSON Files (*.json)",
                            None,
                            QFileDialog.Option.DontConfirmOverwrite
                        )
                        
                        # Add .json suffix if not present
                        if file_path and not file_path.endswith('.json'):
                            file_path = file_path + '.json'
                        
                        logger.info(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Selected: {file_path or 'cancelled'}")
                        self.result = file_path
                    except Exception as e:
                        logger.error(f"[SKILL_IO][BACKEND][SAVE_DIALOG] Error in dialog: {e}", exc_info=True)
                        self.result = None
                    finally:
                        self.done_event.set()
            
            # Create helper and move to main thread
            helper = DialogHelper()
            helper.moveToThread(app.thread())
            
            # Emit signal and wait for result
            helper.show_dialog.emit(dialog_path)
            # Human-scale timeout: the dialog blocks on the user browsing and
            # typing a filename (often via IME) — must comfortably exceed that.
            # The frontend waits 630s (file-api.ts DIALOG_TIMEOUT_MS) so this
            # timeout response still reaches it.
            if not helper.done_event.wait(timeout=600):
                logger.error("[SKILL_IO][BACKEND][SAVE_DIALOG] Dialog timeout")
                return create_error_response(
                    request,
                    'DIALOG_TIMEOUT',
                    'File dialog timed out'
                )
            
            file_path = helper.result
        
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


@IPCHandlerRegistry.handler('open_skill_file')
def handle_open_skill_file(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Open a skill file (main skill json) and update recent files list.

    This is a semantic operation representing a user opening a skill.
    Bundle files should still be read via read_skill_file.

    Args:
        request: IPC request object
        params: Request params, must include filePath; optional skillName

    Returns:
        IPCResponse: Response with file content
    """
    try:
        logger.debug(f"Open skill file handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['filePath'])
        if not is_valid:
            logger.warning(f"Invalid parameters for open skill file: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        file_path = data['filePath']
        original_path = file_path
        skill_name = (params or {}).get('skillName')

        # Convert relative path to absolute path
        if not os.path.isabs(file_path):
            from config.app_info import app_info
            base_dir = app_info.appdata_path
            file_path = os.path.join(base_dir, file_path)

        logger.info(f"[SKILL_IO][BACKEND][OPEN_ATTEMPT] Original: {original_path} -> Resolved: {file_path}")

        # Safety check: ensure file exists
        if not os.path.exists(file_path):
            logger.warning(f"[SKILL_IO][BACKEND][OPEN_NOT_FOUND] {file_path}")
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
            logger.info(f"[SKILL_IO][BACKEND][OPEN_OK] {file_path} size={size}")

            # Update recent files (skip bundle files)
            file_name = os.path.basename(file_path)
            is_bundle_file = file_name.endswith('_bundle.json') or file_name.endswith('-bundle.json')
            if not is_bundle_file:
                try:
                    from gui.ipc.w2p_handlers.skill_editor_handler import _update_recent_files

                    if not skill_name:
                        file_dir = os.path.dirname(file_path)
                        parent_dir = os.path.dirname(file_dir)
                        if os.path.basename(file_dir) == 'diagram_dir':
                            skill_name = os.path.basename(parent_dir)
                        else:
                            skill_name = os.path.basename(file_dir)

                    _update_recent_files(file_path, skill_name)
                    logger.debug(f"[SKILL_IO][BACKEND][RECENT_FILES_UPDATED] {file_path}")
                except Exception as e:
                    logger.warning(f"[SKILL_IO][BACKEND][RECENT_FILES_UPDATE_FAILED] {e}")

            return create_success_response(request, {
                'content': content,
                'filePath': file_path,
                'fileName': os.path.basename(file_path),
                'fileSize': size
            })

        except IOError as e:
            error_str = str(e)
            logger.error(f"[SKILL_IO][BACKEND][OPEN_ERROR] {file_path} {error_str}")
            
            # Provide user-friendly error message for permission issues
            error_message = f'Failed to read file: {error_str}'
            
            # macOS-specific permission error handling
            if "Permission denied" in error_str or "[Errno 13]" in error_str:
                import platform
                if platform.system() == "Darwin":  # macOS
                    if "/Downloads/" in file_path or file_path.startswith(os.path.expanduser("~/Downloads")):
                        error_message = (
                            "æ— æ³•è¯»å– Downloads æ–‡ä»¶å¤¹ä¸­çš„æ–‡ä»¶ï¼ˆæƒé™è¢«æ‹’ç»ï¼‰ã€‚\n\n"
                            "macOS è§£å†³æ–¹æ³•ï¼š\n"
                            "1. ä½¿ç”¨ã€Œæ–‡ä»¶ â†’ æ‰“å¼€ã€èœå•é€šè¿‡ç³»ç»Ÿå¯¹è¯æ¡†é€‰æ‹©æ–‡ä»¶ï¼ˆæŽ¨èï¼‰\n"
                            "2. å°†æ–‡ä»¶ç§»åŠ¨åˆ° Documents æˆ– Desktop æ–‡ä»¶å¤¹\n"
                            "3. æˆ–åœ¨ã€Œç³»ç»Ÿè®¾ç½® â†’ éšç§ä¸Žå®‰å…¨æ€§ â†’ æ–‡ä»¶å’Œæ–‡ä»¶å¤¹ã€ä¸­æŽˆäºˆ eCan.ai è®¿é—®ä¸‹è½½æ–‡ä»¶å¤¹çš„æƒé™"
                        )
                    else:
                        error_message = (
                            f"æ— æ³•è¯»å–æ–‡ä»¶ {os.path.dirname(file_path)}ï¼ˆæƒé™è¢«æ‹’ç»ï¼‰ã€‚\n\n"
                            "å»ºè®®ï¼š\n"
                            "1. ä½¿ç”¨ã€Œæ–‡ä»¶ â†’ æ‰“å¼€ã€èœå•é€šè¿‡ç³»ç»Ÿå¯¹è¯æ¡†é€‰æ‹©æ–‡ä»¶\n"
                            "2. æˆ–åœ¨ç³»ç»Ÿè®¾ç½®ä¸­æŽˆäºˆåº”ç”¨ç›¸åº”çš„æ–‡ä»¶å¤¹è®¿é—®æƒé™"
                        )
            
            return create_error_response(
                request,
                'READ_ERROR',
                error_message
            )
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
        logger.error(f"Error in open_skill_file handler: {e}")
        return create_error_response(
            request,
            'OPEN_SKILL_FILE_ERROR',
            f"Error opening skill file: {str(e)}"
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
            from config.app_info import app_info
            base_dir = app_info.appdata_path
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
        
        except IOError as e:
            error_str = str(e)
            logger.error(f"[SKILL_IO][BACKEND][READ_ERROR] {file_path} {error_str}")
            
            # Provide user-friendly error message for permission issues
            error_message = f'Failed to read file: {error_str}'
            
            # macOS-specific permission error handling
            if "Permission denied" in error_str or "[Errno 13]" in error_str:
                import platform
                if platform.system() == "Darwin":  # macOS
                    if "/Downloads/" in file_path or file_path.startswith(os.path.expanduser("~/Downloads")):
                        error_message = (
                            "æ— æ³•è¯»å– Downloads æ–‡ä»¶å¤¹ä¸­çš„æ–‡ä»¶ï¼ˆæƒé™è¢«æ‹’ç»ï¼‰ã€‚\n\n"
                            "macOS è§£å†³æ–¹æ³•ï¼š\n"
                            "1. ä½¿ç”¨ã€Œæ–‡ä»¶ â†’ æ‰“å¼€ã€èœå•é€šè¿‡ç³»ç»Ÿå¯¹è¯æ¡†é€‰æ‹©æ–‡ä»¶ï¼ˆæŽ¨èï¼‰\n"
                            "2. å°†æ–‡ä»¶ç§»åŠ¨åˆ° Documents æˆ– Desktop æ–‡ä»¶å¤¹\n"
                            "3. æˆ–åœ¨ã€Œç³»ç»Ÿè®¾ç½® â†’ éšç§ä¸Žå®‰å…¨æ€§ â†’ æ–‡ä»¶å’Œæ–‡ä»¶å¤¹ã€ä¸­æŽˆäºˆ eCan.ai è®¿é—®ä¸‹è½½æ–‡ä»¶å¤¹çš„æƒé™"
                        )
                    else:
                        error_message = (
                            f"æ— æ³•è¯»å–æ–‡ä»¶ {os.path.dirname(file_path)}ï¼ˆæƒé™è¢«æ‹’ç»ï¼‰ã€‚\n\n"
                            "å»ºè®®ï¼š\n"
                            "1. ä½¿ç”¨ã€Œæ–‡ä»¶ â†’ æ‰“å¼€ã€èœå•é€šè¿‡ç³»ç»Ÿå¯¹è¯æ¡†é€‰æ‹©æ–‡ä»¶\n"
                            "2. æˆ–åœ¨ç³»ç»Ÿè®¾ç½®ä¸­æŽˆäºˆåº”ç”¨ç›¸åº”çš„æ–‡ä»¶å¤¹è®¿é—®æƒé™"
                        )
            
            return create_error_response(
                request,
                'READ_ERROR',
                error_message
            )
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
    """Handle writing skill file(s) - supports both single and batch write.

    Args:
        request: IPC request object
        params: Request params, can be:
            - New format: { input: [{ filePath, content }, ...] }
            - Old format: { filePath, content } (for backward compatibility)

    Returns:
        IPCResponse: Write result(s)
    """
    try:
        # Check if it's the new batch format or old single file format
        if 'input' in params:
            # New format: batch write
            input_list = params['input']
            if not isinstance(input_list, list):
                return create_error_response(
                    request,
                    'INVALID_PARAMS',
                    'input must be an array'
                )
            
            results = []
            for item in input_list:
                result = _write_single_file(item)
                if result['success']:
                    results.append(result['data'])
                else:
                    # If any file fails, return error
                    return create_error_response(
                        request,
                        result['error_code'],
                        result['error_message']
                    )
            
            return create_success_response(request, results)
        else:
            # Old format: single file (backward compatibility)
            is_valid, data, error = validate_params(params, ['filePath', 'content'])
            if not is_valid:
                logger.warning(f"Invalid parameters for write skill file: {error}")
                return create_error_response(
                    request,
                    'INVALID_PARAMS',
                    error
                )
            
            result = _write_single_file(data)
            if result['success']:
                return create_success_response(request, result['data'])
            else:
                return create_error_response(
                    request,
                    result['error_code'],
                    result['error_message']
                )
            
    except Exception as e:
        logger.error(f"Error in write_skill_file handler: {e}")
        return create_error_response(
            request,
            'WRITE_SKILL_FILE_ERROR',
            f"Error writing skill file: {str(e)}"
        )


def _write_single_file(data: Dict[str, Any]) -> Dict[str, Any]:
    """Write a single skill file.
    
    Args:
        data: Dict with 'filePath' and 'content'
    
    Returns:
        Dict with 'success', 'data' (if success), or 'error_code' and 'error_message' (if failed)
    """
    try:
        file_path = data.get('filePath')
        content = data.get('content')
        
        if not file_path or not content:
            return {
                'success': False,
                'error_code': 'INVALID_PARAMS',
                'error_message': 'Missing required parameters: filePath, content'
            }
        
        file_path = data['filePath']
        content = data['content']
        
        # Normalize file path to handle Chinese characters correctly
        # This ensures consistent path format for database queries
        file_path = os.path.abspath(os.path.normpath(file_path))
        
        # Extract skill name from file path (fallback)
        # IMPORTANT: Preserve the original file path - do not redirect to my_skills directory
        # This allows users to open and save skill files from any directory
        file_name = os.path.basename(file_path)
        parent_dir = os.path.dirname(file_path)
        
        # Extract skill name from file path as fallback
        skill_name_from_path = file_name[:-5] if file_name.endswith('.json') else file_name
        
        # Remove known suffixes to get the base skill name
        if skill_name_from_path.endswith('_data_mapping'):
            skill_name_from_path = skill_name_from_path[:-13]
        elif skill_name_from_path.endswith('_skill_bundle'):
            skill_name_from_path = skill_name_from_path[:-13]
        elif skill_name_from_path.endswith('_skill'):
            skill_name_from_path = skill_name_from_path[:-6]
        
        # Validate JSON content and extract skillName from content
        skill_name = skill_name_from_path  # Default to path-based name
        try:
            if isinstance(content, str):
                content_obj = json.loads(content)
                # Prefer skillName from content over path-based name
                if isinstance(content_obj, dict) and 'skillName' in content_obj:
                    skill_name = content_obj['skillName']
                    logger.info(f"[SKILL_IO][BACKEND] Using skillName from content: {skill_name}")
                # Debug: Check if hFlip data exists in nodes
                if isinstance(content_obj, dict) and 'workFlow' in content_obj:
                    workflow = content_obj['workFlow']
                    if isinstance(workflow, dict) and 'nodes' in workflow:
                        nodes_with_hflip = [n for n in workflow['nodes'] if isinstance(n, dict) and n.get('data', {}).get('hFlip')]
                        if nodes_with_hflip:
                            logger.info(f"[SKILL_IO][BACKEND] Found {len(nodes_with_hflip)} nodes with hFlip=true")
            else:
                if isinstance(content, dict) and 'skillName' in content:
                    skill_name = content['skillName']
                    logger.info(f"[SKILL_IO][BACKEND] Using skillName from content: {skill_name}")
                content = json.dumps(content, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'error_code': 'INVALID_JSON',
                'error_message': f'Invalid JSON content: {str(e)}'
            }
        
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
                        logger.info(f"[SKILL_IO][BACKEND] âœ… Skill {operation}d successfully (ID: {skill_id})")
                    else:
                        logger.warning(f"[SKILL_IO][BACKEND] âŒ Failed to sync skill: {result.get('error')}")
                except Exception as sync_error:
                    logger.error(f"[SKILL_IO][BACKEND] âŒ Error syncing skill to database: {sync_error}", exc_info=True)
            
            # Use skill_name extracted from content (not from file path)
            # skill_name was already extracted from content in lines 742-754
            from datetime import datetime
            return {
                'success': True,
                'data': {
                    'filePath': file_path,
                    'fileName': os.path.basename(file_path),
                    'skillName': skill_name,  # Use skill_name from content, not from file path
                    'fileSize': os.path.getsize(file_path),
                    'updatedAt': datetime.now().isoformat()
                }
            }
            
        except IOError as e:
            error_str = str(e)
            logger.error(f"[SKILL_IO][BACKEND][WRITE_ERROR] {file_path} {error_str}")
            
            # Provide user-friendly error message for permission issues
            error_message = f'Failed to write file: {error_str}'
            
            # macOS-specific permission error handling
            if "Permission denied" in error_str or "[Errno 13]" in error_str:
                import platform
                if platform.system() == "Darwin":  # macOS
                    if "/Downloads/" in file_path or file_path.startswith(os.path.expanduser("~/Downloads")):
                        error_message = (
                            "æ— æ³•ä¿å­˜åˆ° Downloads æ–‡ä»¶å¤¹ï¼ˆæƒé™è¢«æ‹’ç»ï¼‰ã€‚\n\n"
                            "macOS è§£å†³æ–¹æ³•ï¼š\n"
                            "1. ä½¿ç”¨ã€Œå¦å­˜ä¸ºã€å¯¹è¯æ¡†é€‰æ‹©ä¿å­˜ä½ç½®ï¼ˆæŽ¨èï¼‰\n"
                            "2. ä¿å­˜åˆ° Documents æˆ– Desktop æ–‡ä»¶å¤¹\n"
                            "3. æˆ–åœ¨ã€Œç³»ç»Ÿè®¾ç½® â†’ éšç§ä¸Žå®‰å…¨æ€§ â†’ æ–‡ä»¶å’Œæ–‡ä»¶å¤¹ã€ä¸­æŽˆäºˆ eCan.ai è®¿é—®ä¸‹è½½æ–‡ä»¶å¤¹çš„æƒé™"
                        )
                    else:
                        error_message = (
                            f"æ— æ³•ä¿å­˜æ–‡ä»¶åˆ° {os.path.dirname(file_path)}ï¼ˆæƒé™è¢«æ‹’ç»ï¼‰ã€‚\n\n"
                            "å»ºè®®ï¼š\n"
                            "1. ä½¿ç”¨ã€Œå¦å­˜ä¸ºã€å¯¹è¯æ¡†é€‰æ‹©æœ‰æƒé™çš„ä½ç½®\n"
                            "2. æˆ–åœ¨ç³»ç»Ÿè®¾ç½®ä¸­æŽˆäºˆåº”ç”¨ç›¸åº”çš„æ–‡ä»¶å¤¹è®¿é—®æƒé™"
                        )
            
            return {
                'success': False,
                'error_code': 'WRITE_ERROR',
                'error_message': error_message,
                'original_error': error_str
            }
            
    except Exception as e:
        logger.error(f"Error in _write_single_file: {e}")
        return {
            'success': False,
            'error_code': 'WRITE_SINGLE_FILE_ERROR',
            'error_message': f"Error writing file: {str(e)}"
        }


logger.info("File operation handlers registered successfully")


@IPCHandlerRegistry.handler('skills.load')
def handle_skills_load(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Load a skill from disk by path.

    Params:
      - skillPath: path to the skill root directory (e.g., my_skills/ebay000_skill)
      - skillName: skill name (optional, inferred from path if not provided)
    Returns: skill JSON data including workFlow, metadata, etc.
    """
    try:
        p = params or {}
        skill_path = p.get('skillPath')
        skill_name = p.get('skillName')
        
        if not skill_path:
            return create_error_response(request, 'INVALID_PARAMS', 'skillPath is required')
        
        from pathlib import Path
        skill_path = Path(skill_path)
        
        # Infer skill name from path if not provided
        if not skill_name:
            # Extract from path like "my_skills/ebay000_skill" -> "ebay000"
            dir_name = skill_path.name
            if dir_name.endswith('_skill'):
                skill_name = dir_name[:-6]
            else:
                skill_name = dir_name
        
        # Look for the skill JSON file
        diagram_dir = skill_path / "diagram_dir"
        skill_json_path = diagram_dir / f"{skill_name}_skill.json"
        
        if not skill_json_path.exists():
            # Try alternative naming
            json_files = list(diagram_dir.glob("*_skill.json")) if diagram_dir.exists() else []
            if json_files:
                skill_json_path = json_files[0]
            else:
                logger.warning(f"[IPC] skills.load: skill JSON not found at {skill_json_path}")
                return create_error_response(request, 'FILE_NOT_FOUND', f'Skill JSON not found: {skill_json_path}')
        
        # Read and parse the skill JSON
        with open(skill_json_path, 'r', encoding='utf-8') as f:
            skill_data = json.load(f)
        
        # Also try to load bundle if it exists
        bundle_path = diagram_dir / f"{skill_name}_skill_bundle.json"
        bundle_data = None
        if bundle_path.exists():
            try:
                with open(bundle_path, 'r', encoding='utf-8') as f:
                    bundle_data = json.load(f)
            except Exception as e:
                logger.warning(f"[IPC] skills.load: failed to load bundle: {e}")
        
        logger.info(f"[IPC] skills.load: loaded skill '{skill_name}' from {skill_json_path}")
        
        return create_success_response(request, {
            'skillName': skill_data.get('skillName', skill_name),
            'description': skill_data.get('description', ''),
            'workFlow': skill_data.get('workFlow', {'nodes': [], 'edges': []}),
            'metadata': skill_data.get('metadata', {}),
            'bundle': bundle_data,
            'skillPath': str(skill_path),
            'diagramPath': str(skill_json_path),
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"[IPC] skills.load: invalid JSON: {e}")
        return create_error_response(request, 'INVALID_JSON', f'Invalid JSON: {e}')
    except Exception as e:
        logger.error(f"[IPC] skills.load error: {e}")
        return create_error_response(request, 'LOAD_ERROR', str(e))


@IPCHandlerRegistry.handler('skills.scaffold')
def handle_skills_scaffold(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Scaffold a new skill directory under the per-user skills root.

    Params:
      - name: skill base name (without _skill). If omitted, a timestamped name is generated.
      - kind: 'code' | 'diagram' (default: 'diagram')
      - description: optional description
      - skillJson: optional skill JSON content from frontend (for diagram type)
      - bundleJson: optional bundle JSON content from frontend (for diagram type)
      - checkOnly: if true, only check if skill exists without creating
    Returns: { skillRoot: str, name: str, diagramPath: str } or { exists: bool } if checkOnly
    """
    try:
        p = params or {}
        import datetime
        name = p.get('name') or datetime.datetime.now().strftime('skill_%Y%m%d_%H%M%S')
        kind = (p.get('kind') or 'diagram').lower()
        description = p.get('description') or ''
        skill_json = p.get('skillJson')
        bundle_json = p.get('bundleJson')
        mapping_json = p.get('mappingJson')
        check_only = p.get('checkOnly', False)
        
        # Get skills root directory
        _, _, user_skills_root = _get_extern_skills(request, params)
        skills_root = user_skills_root()
        skill_dir = skills_root / f"{name}_skill"
        
        # If checkOnly, just return whether the skill exists
        if check_only:
            exists = skill_dir.exists()
            logger.info(f"[IPC] skills.scaffold: check only - skill '{name}' exists: {exists}")
            return create_success_response(request, { 'exists': exists, 'name': name })
        
        # Check if skill already exists
        if skill_dir.exists():
            logger.warning(f"[IPC] skills.scaffold: skill '{name}' already exists at {skill_dir}")
            return create_error_response(request, 'SKILL_EXISTS', f"Skill '{name}' already exists. Please choose a different name.")
        
        scaffold_skill, _, _ = _get_extern_skills(request, params)
        path = scaffold_skill(name, description, kind, skill_json, bundle_json, mapping_json)
        
        # Return the diagram file path for frontend to use
        diagram_path = str(path / "diagram_dir" / f"{name}_skill.json") if kind == "diagram" else ""
        
        # Sync skill to database so it appears in skill list
        actual_skill_id = None
        if kind == "diagram" and diagram_path:
            try:
                from gui.ipc.w2p_handlers.skill_handler import sync_skill_from_file
                sync_result = sync_skill_from_file(diagram_path)
                if sync_result.get('success'):
                    actual_skill_id = sync_result.get('skill_id')
                    logger.info(f"[IPC] skills.scaffold: skill synced to database (ID: {actual_skill_id})")
                else:
                    logger.warning(f"[IPC] skills.scaffold: failed to sync skill to database: {sync_result.get('error')}")
            except Exception as sync_err:
                logger.warning(f"[IPC] skills.scaffold: failed to sync skill: {sync_err}")
        
        response_data = {
            'skillRoot': str(path),
            'name': name,
            'diagramPath': diagram_path,
        }
        if actual_skill_id:
            response_data['skillId'] = actual_skill_id

        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"[IPC] skills.scaffold error: {e}")
        return create_error_response(request, 'SCAFFOLD_ERROR', str(e))


@IPCHandlerRegistry.handler('skills.rename')
def handle_skills_rename(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Rename an existing skill root directory <old>_skill -> <new>_skill.
    
    Standard approach: uses skillId to uniquely identify the record.
    ID-based lookup ensures no duplicates or missed updates.

    Params:
      - oldName: Old skill name (without _skill suffix) - used for file system rename
      - newName: New skill name (without _skill suffix) - used for file system rename
      - skillId: (Required) The unique skill ID - used to locate DB record
      - currentFilePath: (Optional) Current skill JSON file path for external directories
    Returns: { skillRoot: str, skillId: str }
    """
    try:
        logger.info(f"[SKILL_RENAME] === START ===")
        logger.info(f"[SKILL_RENAME] params received: {params}")
        
        ok, data, err = validate_params(params, ['oldName', 'newName'])
        if not ok:
            logger.error(f"[SKILL_RENAME] Invalid params: {err}")
            return create_error_response(request, 'INVALID_PARAMS', err or 'invalid')

        old_name = data['oldName']
        new_name = data['newName']
        skill_id = data.get('skillId')  # Optional - can be derived from oldName if not provided
        current_file_path = data.get('currentFilePath')
        
        logger.info(f"[SKILL_RENAME] old_name={old_name}, new_name={new_name}, skill_id={skill_id}, current_file_path={current_file_path}")
        
        ctx = get_handler_context(request, params)
        old_skill_full_name = f"{old_name}_skill"
        new_skill_full_name = f"{new_name}_skill"
        
        # Resolve skill_root_path from currentFilePath or from DB using skillId
        skill_root_path = None
        if current_file_path:
            current_path = Path(current_file_path)
            if 'diagram_dir' in str(current_path):
                skill_root_path = str(current_path.parent.parent)
                logger.info(f"[SKILL_RENAME] Using external directory from currentFilePath: {skill_root_path}")
        
        # If skillId is provided but no currentFilePath, look up the actual path from DB
        if not skill_root_path and skill_id and ctx:
            try:
                ec_db_mgr = ctx.get_ec_db_mgr()
                if ec_db_mgr:
                    skill_service = ec_db_mgr.get_skill_service()
                    if skill_service:
                        # Query skill by ID to get actual path
                        all_skills = skill_service.search_skills()
                        for s in all_skills:
                            if str(s.get('id')) == str(skill_id):
                                db_path = s.get('path', '')
                                if db_path:
                                    db_path_obj = Path(db_path)
                                    if 'diagram_dir' in str(db_path_obj):
                                        skill_root_path = str(db_path_obj.parent.parent)
                                        logger.info(f"[SKILL_RENAME] Resolved skill_root_path from DB: {skill_root_path}")
                                break
            except Exception as db_err:
                logger.warning(f"[SKILL_RENAME] Failed to lookup skill path from DB: {db_err}")
        
        # Rename the skill directory on file system
        _, rename_skill, _ = _get_extern_skills(request, params)
        new_path = rename_skill(old_name, new_name, skill_root_path)
        
        # Rename files inside diagram_dir to match new name
        try:
            diagram_dir = new_path / "diagram_dir"
            if diagram_dir.exists():
                # Rename skill JSON
                old_skill_json = diagram_dir / f"{old_name}_skill.json"
                new_skill_json = diagram_dir / f"{new_name}_skill.json"
                if old_skill_json.exists():
                    old_skill_json.rename(new_skill_json)
                    logger.info(f"[SKILL_RENAME] Renamed skill file: {old_skill_json.name} -> {new_skill_json.name}")
                
                # Rename bundle JSON
                old_bundle_json = diagram_dir / f"{old_name}_skill_bundle.json"
                new_bundle_json = diagram_dir / f"{new_name}_skill_bundle.json"
                if old_bundle_json.exists():
                    old_bundle_json.rename(new_bundle_json)
                    logger.info(f"[SKILL_RENAME] Renamed bundle file: {old_bundle_json.name} -> {new_bundle_json.name}")
                
        except Exception as file_err:
            logger.warning(f"[SKILL_RENAME] Failed to rename inner files: {file_err}")
        
        # data_mapping.json is at skill root level with fixed name, no rename needed

        new_skill_file = str(new_path / "diagram_dir" / f"{new_name}_skill.json")

        # Resolve target skill ID (prefer explicit ID, fallback to name search)
        target_skill_id = skill_id
        db_updated = False

        # Update local DB and in-memory
        try:
            if ctx:
                ec_db_mgr = ctx.get_ec_db_mgr()
                if ec_db_mgr:
                    skill_service = ec_db_mgr.get_skill_service()
                    if skill_service:
                        # If skillId not provided, search by old name in DB
                        if not target_skill_id:
                            all_skills = skill_service.search_skills()
                            for s in all_skills:
                                if s.get('name') == old_name or (old_skill_full_name in (s.get('path') or '')):
                                    target_skill_id = s.get('id')
                                    logger.info(f"[SKILL_RENAME] Found skill ID by name: {target_skill_id}")
                                    break

                        if target_skill_id:
                            update_result = skill_service.update_skill(target_skill_id, {
                                'name': new_name,
                                'path': new_skill_file,
                            })
                            if update_result.get('success'):
                                logger.info(f"[SKILL_RENAME] Updated local DB: id={target_skill_id} -> name={new_name}")
                                db_updated = True
                            else:
                                logger.warning(f"[SKILL_RENAME] Failed to update DB: {update_result.get('error')}")
                        else:
                            logger.warning(f"[SKILL_RENAME] No skill found in DB for: {old_name}")

                # Update in-memory skill list by ID or by name/path
                if hasattr(ctx, 'agent_skills'):
                    mem_updated = False
                    for mem_skill in (ctx.get_agent_skills() or []):
                        mem_skill_id = str(getattr(mem_skill, 'id', '') or '').strip()
                        mem_askid = str(getattr(mem_skill, 'askid', '') or '').strip()
                        mem_name = getattr(mem_skill, 'name', '') or ''
                        mem_path = getattr(mem_skill, 'path', '') or ''

                        # Match by ID or by name/path
                        id_match = (target_skill_id and (mem_skill_id == target_skill_id or mem_askid == target_skill_id))
                        name_match = mem_name == old_name
                        path_match = old_skill_full_name in mem_path

                        if id_match or name_match or path_match:
                            mem_skill.name = new_name
                            if hasattr(mem_skill, 'path'):
                                mem_skill.path = new_skill_file
                            logger.info(f"[SKILL_RENAME] Updated in-memory skill: {old_name} -> {new_name}")
                            mem_updated = True
                            break
                    if not mem_updated:
                        logger.warning(f"[SKILL_RENAME] No matching in-memory skill for: {old_name}")

                if not db_updated:
                    logger.warning(f"[SKILL_RENAME] Local DB update failed")
        except Exception as sync_err:
            logger.warning(f"[SKILL_RENAME] Failed to update local DB/memory after rename: {sync_err}")

        logger.info(f"[SKILL_RENAME] File system rename complete. Local DB/memory updated immediately.")

        # Trigger cloud sync after rename (critical for keeping cloud in sync)
        try:
            _trigger_cloud_sync_after_rename(
                skill_id=target_skill_id,
                new_skill_name=new_name,
                new_skill_file=new_skill_file,
                old_skill_name=old_name
            )
        except Exception as cloud_err:
            logger.warning(f"[SKILL_RENAME] Failed to trigger cloud sync: {cloud_err}")

        # Update backend recent files to ensure correct path is loaded after refresh
        try:
            from gui.ipc.w2p_handlers.skill_editor_handler import _update_recent_files
            _update_recent_files(new_skill_file, new_name)
            logger.info(f"[SKILL_RENAME] âœ… Updated backend recent files with new path: {new_skill_file}")
        except Exception as rf_err:
            logger.warning(f"[SKILL_RENAME] Failed to update backend recent files: {rf_err}")
        
        return create_success_response(request, { 'skillRoot': str(new_path) })
    except Exception as e:
        logger.error(f"[IPC] skills.rename error: {e}")
        return create_error_response(request, 'RENAME_ERROR', str(e))


def _trigger_cloud_sync_after_rename(skill_id, new_skill_name, new_skill_file, old_skill_name):
    """Sync skill after rename by calling the standardized save flow."""
    try:
        from gui.ipc.w2p_handlers.skill_handler import prepare_skill_info_from_json, get_current_username, handle_save_agent_skill
        from gui.ipc.types import IPCRequest

        skill_info = prepare_skill_info_from_json(new_skill_file, skill_id, new_skill_name)
        username = get_current_username()

        mock_request = IPCRequest(params={'username': username, 'skill_info': skill_info})
        result = handle_save_agent_skill(mock_request, {'username': username, 'skill_info': skill_info})

        if result and result.get('success'):
            logger.info(f"[SKILL_RENAME] Skill synced after rename: {old_skill_name} -> {new_skill_name}")
        else:
            logger.warning(f"[SKILL_RENAME] Skill sync failed after rename: {result}")
    except Exception as e:
        logger.warning(f"[SKILL_RENAME] Rename sync failed for {old_skill_name} -> {new_skill_name}: {e}")


@IPCHandlerRegistry.handler('skills.copyTo')
def handle_skills_copy_to(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Copy entire skill directory to a new location with a new name.
    
    This is used for "Save As" functionality to copy the entire skill folder
    (including diagram_dir, all JSON files, etc.) to a new location.

    Params:
      - sourcePath: Current skill file path (e.g., .../xxx_skill/diagram_dir/xxx_skill.json)
      - newName: New skill base name (without _skill suffix)
      - skillJson: Updated skill JSON content to save
      - bundleJson: Updated bundle JSON content to save
      - targetDir: Optional target directory (defaults to same parent as source)
    Returns: { skillRoot: str, diagramPath: str, name: str }
    """
    import shutil
    from pathlib import Path
    
    try:
        ok, data, err = validate_params(params, ['sourcePath', 'newName'])
        if not ok:
            return create_error_response(request, 'INVALID_PARAMS', err or 'invalid')
        
        source_path = data['sourcePath']
        new_name = data['newName']
        skill_json = data.get('skillJson')
        bundle_json = data.get('bundleJson')
        target_dir = data.get('targetDir')  # Optional target directory
        
        # Parse source path to find skill root
        # Expected: .../xxx_skill/diagram_dir/xxx_skill.json
        source_path = Path(source_path).expanduser().resolve()

        # Guardrail: source must be an existing diagram json file under */<name>_skill/diagram_dir/.
        # Without this check, a stale/invalid sourcePath can resolve to a broad parent directory
        # (including app root on Windows) and copy unintended content.
        if not source_path.exists() or not source_path.is_file():
            return create_error_response(
                request,
                'SOURCE_FILE_NOT_FOUND',
                f'Source skill file not found: {source_path}'
            )

        if source_path.suffix.lower() != '.json':
            return create_error_response(
                request,
                'INVALID_SOURCE_FILE',
                f'Source must be a JSON skill file: {source_path}'
            )

        diagram_dir = source_path.parent
        if diagram_dir.name != 'diagram_dir':
            return create_error_response(
                request,
                'INVALID_SOURCE_PATH',
                f'Source must be under diagram_dir: {source_path}'
            )

        old_skill_root = diagram_dir.parent
        if not old_skill_root.name.endswith('_skill'):
            return create_error_response(
                request,
                'INVALID_SKILL_ROOT',
                f'Source parent is not a *_skill directory: {old_skill_root}'
            )

        if not (old_skill_root / 'diagram_dir').is_dir():
            return create_error_response(
                request,
                'INVALID_SKILL_STRUCTURE',
                f'Source skill root missing diagram_dir: {old_skill_root}'
            )
        
        if not old_skill_root.exists():
            return create_error_response(request, 'SOURCE_NOT_FOUND', f'Source skill directory not found: {old_skill_root}')
        
        # Determine target parent directory
        if target_dir:
            parent_dir = Path(target_dir).resolve()
            os.makedirs(parent_dir, exist_ok=True)
        else:
            # Default: same parent directory as source (my_skills/)
            parent_dir = old_skill_root.parent
        
        new_skill_root = parent_dir / f"{new_name}_skill"
        
        # Check if destination already exists
        if new_skill_root.exists():
            return create_error_response(request, 'DESTINATION_EXISTS', f'Skill "{new_name}" already exists at {parent_dir}')
        
        logger.info(f"[SKILL_COPY] Copying skill from {old_skill_root} to {new_skill_root}")
        
        # Copy entire directory
        shutil.copytree(old_skill_root, new_skill_root)
        
        # Rename files inside diagram_dir to match new name
        new_diagram_dir = new_skill_root / "diagram_dir"
        if not new_diagram_dir.exists():
            # Defensive rollback: do not keep a partially/incorrectly copied folder.
            shutil.rmtree(new_skill_root, ignore_errors=True)
            return create_error_response(
                request,
                'INVALID_COPY_RESULT',
                f'Copied directory is not a valid skill (missing diagram_dir): {new_skill_root}'
            )

        if new_diagram_dir.exists():
            # Get old skill name from directory name
            old_name = old_skill_root.name.replace('_skill', '')
            
            # Rename skill JSON file
            old_skill_json = new_diagram_dir / f"{old_name}_skill.json"
            new_skill_json = new_diagram_dir / f"{new_name}_skill.json"
            if old_skill_json.exists():
                old_skill_json.rename(new_skill_json)
                logger.info(f"[SKILL_COPY] Renamed {old_skill_json.name} -> {new_skill_json.name}")
            
            # Rename bundle JSON file
            old_bundle_json = new_diagram_dir / f"{old_name}_skill_bundle.json"
            new_bundle_json = new_diagram_dir / f"{new_name}_skill_bundle.json"
            if old_bundle_json.exists():
                old_bundle_json.rename(new_bundle_json)
                logger.info(f"[SKILL_COPY] Renamed {old_bundle_json.name} -> {new_bundle_json.name}")
            
        # data_mapping.json is at skill root level, copied automatically by copytree
        
        if new_diagram_dir.exists():
            # Write updated skill JSON if provided
            if skill_json:
                # Update skillName in the JSON
                if isinstance(skill_json, dict):
                    skill_json['skillName'] = new_name
                    skill_json.pop('skillId', None)
                    skill_json.pop('id', None)
                with new_skill_json.open('w', encoding='utf-8') as f:
                    json.dump(skill_json, f, indent=2, ensure_ascii=False)
                logger.info(f"[SKILL_COPY] Updated skill JSON with new name: {new_name}")
            
            # Write updated bundle JSON if provided
            if bundle_json:
                with new_bundle_json.open('w', encoding='utf-8') as f:
                    json.dump(bundle_json, f, indent=2, ensure_ascii=False)
                logger.info(f"[SKILL_COPY] Updated bundle JSON")
        
        diagram_path = str(new_diagram_dir / f"{new_name}_skill.json")
        
        # SaveAs/Copy: create a NEW skill record for the copied directory.
        # Do not mutate the original DB record, in-memory skill, or source folder.
        skill_id = None
        try:
            from gui.ipc.w2p_handlers.skill_handler import sync_skill_from_file
            sync_params = dict(params or {})
            sync_params['_skip_cloud_sync'] = True
            sync_result = sync_skill_from_file(diagram_path, request=request, params=sync_params)
            if sync_result.get('success'):
                skill_id = sync_result.get('skill_id')
                try:
                    from app_context import AppContext
                    from agent.cloud_api.cloud_api import (
                        send_add_skills_request_to_cloud,
                        upload_skill_files_to_cloud,
                    )

                    mainwin = AppContext.get_main_window()
                    token = mainwin.get_auth_token() if mainwin else None
                    session = getattr(mainwin, 'session', None) if mainwin else None
                    endpoint = mainwin.getWanApiEndpoint() if mainwin and hasattr(mainwin, 'getWanApiEndpoint') else None

                    if token and session and endpoint:
                        rel_diagram_path = os.path.relpath(diagram_path, start=Path.cwd())
                        cloud_skill_payload = {
                            'id': skill_id,
                            'name': new_name,
                            'description': (skill_json or {}).get('description', '') if isinstance(skill_json, dict) else '',
                            'version': (skill_json or {}).get('version', '1.0.0') if isinstance(skill_json, dict) else '1.0.0',
                            'path': rel_diagram_path.replace('\\', '/'),
                            'level': (skill_json or {}).get('level', 'entry') if isinstance(skill_json, dict) else 'entry',
                            'config': (skill_json or {}).get('config', {}) if isinstance(skill_json, dict) else {},
                            'diagram': (skill_json or {}).get('workFlow') or (skill_json or {}).get('diagram') or {},
                            'tags': (skill_json or {}).get('tags', []) if isinstance(skill_json, dict) else [],
                            'source': 'ui',
                        }
                        cloud_result = send_add_skills_request_to_cloud(session, [cloud_skill_payload], token, endpoint)
                        first = cloud_result[0] if isinstance(cloud_result, list) and cloud_result else {}
                        if first.get('success'):
                            username = getattr(mainwin, 'user', '') if mainwin else ''
                            safe_username = username.replace("@", "_").replace(".", "_") if username else "unknown"
                            bundle_path = new_diagram_dir / f"{new_name}_skill_bundle.json"
                            data_mapping_path = new_skill_root / "data_mapping.json"
                            files_to_upload = []
                            with new_skill_json.open('r', encoding='utf-8') as f:
                                files_to_upload.append({
                                    "filePath": f"{safe_username}/my_skills/{new_name}_skill/diagram_dir/{new_name}_skill.json",
                                    "content": f.read(),
                                    "userId": username,
                                })
                            if bundle_path.exists():
                                with bundle_path.open('r', encoding='utf-8') as f:
                                    files_to_upload.append({
                                        "filePath": f"{safe_username}/my_skills/{new_name}_skill/diagram_dir/{new_name}_skill_bundle.json",
                                        "content": f.read(),
                                        "userId": username,
                                    })
                            if data_mapping_path.exists():
                                with data_mapping_path.open('r', encoding='utf-8') as f:
                                    files_to_upload.append({
                                        "filePath": f"{safe_username}/my_skills/{new_name}_skill/data_mapping.json",
                                        "content": f.read(),
                                        "userId": username,
                                    })

                            upload_result = upload_skill_files_to_cloud(session, token, files_to_upload, endpoint)
                            if upload_result.get('success'):
                                logger.info(f"[SKILL_COPY] Uploaded copied skill files via writeSkillFile: {new_name} (ID: {skill_id})")
                            else:
                                logger.warning(f"[SKILL_COPY] writeSkillFile upload failed for copied skill: {new_name} result={upload_result}")
                        else:
                            logger.warning(f"[SKILL_COPY] Cloud add failed for copied skill: {new_name} result={first}")
                    else:
                        logger.warning(f"[SKILL_COPY] Missing cloud auth/session context, skipped cloud file upload for copied skill: {new_name}")
                except Exception as upload_err:
                    logger.warning(f"[SKILL_COPY] Failed to upload copied skill files to cloud: {upload_err}")
                logger.info(f"[SKILL_COPY] âœ… New copied skill created in database (ID: {skill_id})")
            else:
                logger.warning(f"[SKILL_COPY] âš ï¸ Failed to sync copied skill to database: {sync_result.get('error')}")
        except Exception as sync_err:
            logger.warning(f"[SKILL_COPY] âš ï¸ Error updating skill in database/memory: {sync_err}")
        
        return create_success_response(request, {
            'skillRoot': str(new_skill_root),
            'diagramPath': diagram_path,
            'name': new_name,
            'skillId': skill_id
        })
        
    except Exception as e:
        logger.error(f"[IPC] skills.copyTo error: {e}", exc_info=True)
        return create_error_response(request, 'COPY_ERROR', str(e))


@IPCHandlerRegistry.handler('open_file')
def handle_open_file(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Open a file in the OS default application.
    
    Args:
        request: IPC request object
        params: Parameters containing 'path' - file path to open
        
    Returns:
        IPCResponse: Response indicating success or failure
    """
    try:
        ok, data, err = validate_params(params, ['path'])
        if not ok:
            return create_error_response(request, 'INVALID_PARAMS', err or 'Path is required')
        
        path = data['path']
        path = os.path.expanduser(path)
        path = os.path.abspath(path)
        
        if not os.path.exists(path):
            logger.warning(f"[OPEN_FILE] Path does not exist: {path}")
            return create_error_response(request, 'PATH_NOT_FOUND', f'Path does not exist: {path}')
        
        logger.info(f"[OPEN_FILE] Opening file: {path}")
        
        if sys.platform == 'darwin':
            subprocess.run(['open', path], check=True, timeout=5)
        elif sys.platform == 'win32':
            os.startfile(path)
        else:  # Linux
            # Check if xdg-open is available
            import shutil
            if not shutil.which('xdg-open'):
                error_msg = (
                    "xdg-open not found. Please install xdg-utils:\n"
                    "  Ubuntu/Debian: sudo apt install xdg-utils\n"
                    "  Fedora/RHEL: sudo dnf install xdg-utils\n"
                    "  Arch Linux: sudo pacman -S xdg-utils"
                )
                logger.error(f"[OPEN_FILE] {error_msg}")
                return create_error_response(request, 'XDG_UTILS_NOT_FOUND', error_msg)
            
            try:
                # xdg-open may not return immediately, use timeout
                subprocess.run(
                    ['xdg-open', path],
                    check=True,
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )
            except subprocess.TimeoutExpired:
                # This is normal for xdg-open, it may spawn the app and return
                logger.debug(f"[OPEN_FILE] xdg-open timeout (normal behavior)")
                pass
        
        return create_success_response(request, {'success': True, 'path': path})
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        logger.error(f"[OPEN_FILE] Failed to open file: {error_msg}")
        return create_error_response(request, 'OPEN_FILE_ERROR', f'Failed to open file: {error_msg}')
    except Exception as e:
        logger.error(f"[OPEN_FILE] Error: {e}")
        return create_error_response(request, 'OPEN_FILE_ERROR', str(e))


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
            subprocess.run(['open', path], check=True, timeout=5)
        elif sys.platform == 'win32':  # Windows
            os.startfile(path)
        else:  # Linux and other Unix-like systems
            import shutil
            
            # Try different file managers in order of preference
            file_managers = [
                'nautilus',      # GNOME
                'dolphin',       # KDE
                'thunar',        # XFCE
                'pcmanfm',       # LXDE
                'caja',          # MATE
                'nemo',          # Cinnamon
                'xdg-open'       # Generic fallback
            ]
            
            opened = False
            last_error = None
            
            for fm in file_managers:
                if shutil.which(fm):
                    try:
                        subprocess.run(
                            [fm, path],
                            check=True,
                            timeout=5,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE
                        )
                        logger.info(f"[OPEN_FOLDER] Opened with {fm}")
                        opened = True
                        break
                    except subprocess.TimeoutExpired:
                        # Normal behavior for some file managers
                        logger.debug(f"[OPEN_FOLDER] {fm} timeout (normal)")
                        opened = True
                        break
                    except subprocess.CalledProcessError as e:
                        last_error = e
                        logger.debug(f"[OPEN_FOLDER] {fm} failed: {e}")
                        continue
            
            if not opened:
                error_msg = (
                    "No file manager found. Please install one:\n"
                    "  GNOME: sudo apt install nautilus\n"
                    "  KDE: sudo apt install dolphin\n"
                    "  XFCE: sudo apt install thunar\n"
                    "  Or install xdg-utils: sudo apt install xdg-utils"
                )
                if last_error:
                    error_msg += f"\nLast error: {last_error}"
                logger.error(f"[OPEN_FOLDER] {error_msg}")
                return create_error_response(request, 'NO_FILE_MANAGER', error_msg)
        
        return create_success_response(request, {'success': True, 'path': path})
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        logger.error(f"[OPEN_FOLDER] Failed to open folder: {error_msg}")
        return create_error_response(request, 'OPEN_FOLDER_ERROR', f'Failed to open folder: {error_msg}')
    except Exception as e:
        logger.error(f"[OPEN_FOLDER] Error: {e}")
        return create_error_response(request, 'OPEN_FOLDER_ERROR', str(e))


