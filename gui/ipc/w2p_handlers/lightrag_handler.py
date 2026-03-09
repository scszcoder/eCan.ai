"""
LightRAG IPC Handler
Handles knowledge base operations for the LightRAG system.
"""
import os
import json
import traceback
from typing import Any, Optional, Dict, List
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from knowledge.lightrag_client import get_client
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.background_handler('lightrag.ingestFiles')
def handle_ingest_files(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle file ingestion request (runs in background thread to avoid blocking UI).
    File uploads can take a long time (up to 300s timeout).
    
    Expected params:
    - paths: List[str] - List of file paths to ingest
    - options: Optional[Dict] - Additional options for ingestion
    """
    try:
        is_valid, data, error = validate_params(params, ['paths'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        paths = data['paths']
        options = data.get('options', {})
        
        if not isinstance(paths, list) or len(paths) == 0:
            return create_error_response(request, 'INVALID_PARAMS', 'paths must be a non-empty list')
        
        # Get LightRAG client
        client = get_client()
        
        # Call ingest_files method
        result = client.ingest_files(paths, options)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to ingest files')
            logger.error(f"Ingest files failed: {error_msg}")
            return create_error_response(request, 'INGEST_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in ingest_files handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INGEST_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.scanDirectory')
def handle_scan_directory(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Scan a directory and return list of files that can be ingested (runs in background thread).
    Directory scanning can be slow for large directories.
    
    Expected params:
    - dirPath: str - Directory path to scan
    """
    try:
        is_valid, data, error = validate_params(params, ['dirPath'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        dir_path = data['dirPath']
        
        if not isinstance(dir_path, str) or not dir_path.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'dirPath must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call scan_directory method
        result = client.scan_directory(dir_path)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to scan directory')
            logger.error(f"Scan directory failed: {error_msg}")
            return create_error_response(request, 'SCAN_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in scan_directory handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SCAN_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.ingestDirectory')
def handle_ingest_directory(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle directory ingestion request (runs in background thread to avoid blocking UI).
    Directory ingestion can take a very long time.
    
    Expected params:
    - dirPath: str - Directory path to ingest
    - options: Optional[Dict] - Additional options for ingestion
    """
    try:
        is_valid, data, error = validate_params(params, ['dirPath'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        dir_path = data['dirPath']
        options = data.get('options', {})
        
        if not isinstance(dir_path, str) or not dir_path.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'dirPath must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call ingest_directory method
        result = client.ingest_directory(dir_path, options)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to ingest directory')
            logger.error(f"Ingest directory failed: {error_msg}")
            return create_error_response(request, 'INGEST_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in ingest_directory handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INGEST_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.query')
def handle_query(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle knowledge query request (runs in background thread to avoid blocking UI).
    
    Expected params:
    - text: str - Query text
    - options: Optional[Dict] - Query options including:
        - mode: str - Query mode (naive, local, global, hybrid, mix, bypass)
        - stream: bool - Whether to stream response
        - only_need_context: bool - Return only context
        - only_need_prompt: bool - Return only prompt
        - enable_rerank: bool - Enable reranking
        - top_k: int - Number of top results
        - chunk_top_k: int - Number of top chunks
        - max_entity_tokens: int - Max entity tokens
        - max_relation_tokens: int - Max relation tokens
        - max_total_tokens: int - Max total tokens
        - history_turns: int - Number of history turns
        - response_type: str - Response type
        - user_prompt: str - Custom user prompt
    """
    try:
        is_valid, data, error = validate_params(params, ['text'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        text = data['text']
        options = data.get('options', {})
        
        if not isinstance(text, str) or not text.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'text must be a non-empty string')
        
        client = get_client()
        result = client.query(text, options)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Query failed')
            logger.error(f"Query failed: {error_msg}")
            return create_error_response(request, 'QUERY_ERROR', error_msg)
        
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
        
    except Exception as e:
        logger.error(f"Error in query handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'QUERY_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.status')
def handle_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle job status request.
    
    Expected params:
    - jobId: str - Job ID to check status
    """
    try:
        is_valid, data, error = validate_params(params, ['jobId'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        job_id = data['jobId']
        
        if not isinstance(job_id, str) or not job_id.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'jobId must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call status method
        result = client.status(job_id)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to get status')
            logger.error(f"Get status failed: {error_msg}")
            return create_error_response(request, 'STATUS_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in status handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'STATUS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.scan')
def handle_scan(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle document scan request.
    Triggers scanning for new documents in the input directory.
    """
    try:
        # Get LightRAG client
        client = get_client()
        
        # Call scan method
        result = client.scan()
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to start scan')
            logger.error(f"Scan failed: {error_msg}")
            return create_error_response(request, 'SCAN_ERROR', error_msg)
        
        # Extract data from client response
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in scan handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SCAN_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.listDocuments')
def handle_list_documents(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle list documents request.
    Returns all documents grouped by status.
    """
    try:
        # Get LightRAG client
        client = get_client()
        
        # Call list_documents method
        result = client.list_documents()
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to list documents')
            logger.error(f"List documents failed: {error_msg}")
            return create_error_response(request, 'LIST_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in list_documents handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'LIST_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.deleteDocument')
def handle_delete_document(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle document deletion request.
    
    Expected params:
    - id: str - ID of the document to delete
    """
    try:
        is_valid, data, error = validate_params(params, ['id'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        doc_id = data['id']
        
        if not isinstance(doc_id, str) or not doc_id.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'id must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call delete_document method
        result = client.delete_document(doc_id)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to delete document')
            logger.error(f"Delete document failed: {error_msg}")
            return create_error_response(request, 'DELETE_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in delete_document handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'DELETE_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.abortDocument')
def handle_abort_document(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle document abort request (stop processing immediately).
    
    This immediately cancels all running document processing tasks by calling
    the enhanced cancel_pipeline API which cancels asyncio tasks directly.
    
    Expected params:
    - id: str - ID of the document to abort
    
    Returns:
    - Success response with abort result
    - Error response if abort fails
    """
    try:
        is_valid, data, error = validate_params(params, ['id'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        doc_id = data['id']
        
        if not isinstance(doc_id, str) or not doc_id.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'id must be a non-empty string')
        
        logger.info(f"[lightrag_handler] Aborting document immediately: {doc_id}")
        
        # Get LightRAG client
        client = get_client()
        
        # Call abort_document method (which calls cancel_pipeline - now with immediate task cancellation)
        result = client.abort_document(doc_id)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to abort document')
            logger.error(f"[lightrag_handler] Abort document failed for {doc_id}: {error_msg}")
            return create_error_response(request, 'ABORT_ERROR', error_msg)
        
        logger.info(f"[lightrag_handler] Successfully aborted document: {doc_id}")
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
        
    except Exception as e:
        logger.error(f"[lightrag_handler] Error in abort_document handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'ABORT_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.insertText')
def handle_insert_text(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle text insertion request.
    
    Expected params:
    - text: str - Text content to insert
    - metadata: Optional[Dict] - Optional metadata
    """
    try:
        is_valid, data, error = validate_params(params, ['text'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        text = data['text']
        metadata = data.get('metadata')
        
        if not isinstance(text, str) or not text.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'text must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call insert_text method
        result = client.insert_text(text, metadata)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to insert text')
            logger.error(f"Insert text failed: {error_msg}")
            return create_error_response(request, 'INSERT_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in insert_text handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INSERT_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.queryStream')
def handle_query_stream(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle streaming query request.
    Streams data back to frontend via events to avoid blocking.
    """
    try:
        if not params:
            return create_error_response(request, 'MISSING_PARAMS', 'Missing query parameters')
        
        text = params.get('text')
        if not text:
            return create_error_response(request, 'MISSING_TEXT', 'Missing query text')
        
        options = params.get('options', {})
        
        # Get IPC API for sending events
        from gui.ipc.api import IPCAPI
        try:
            ipc_api = IPCAPI.get_instance()
        except Exception as e:
             logger.error(f"IPC API not available: {e}")
             return create_error_response(request, 'IPC_ERROR', 'IPC service not available for streaming')

        # Start background thread for streaming
        import threading
        import json
        
        # Extract ID safely - request might be dict or object
        request_id = request['id'] if isinstance(request, dict) else request.id
        
        def stream_worker():
            try:
                client = get_client()
                # Use captured request_id
                stream_id = request_id
                
                for chunk_str in client.query_stream(text, options):
                    try:
                        # Parse JSON chunk
                        chunk_data = json.loads(chunk_str)
                        
                        # Send chunk event
                        ipc_api.push_lightrag_chunk(stream_id, chunk_data)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse chunk: {chunk_str}")
                        # Send raw if parse fails
                        ipc_api.push_lightrag_chunk(stream_id, {'response': chunk_str})
                
                # Send done event
                ipc_api.push_lightrag_done(stream_id)
                
            except Exception as e:
                logger.error(f"Error in stream worker: {e}")
                # Try-catch around error sending to prevent recursive errors
                try:
                    ipc_api.push_lightrag_error(request_id, str(e))
                except Exception:
                    pass

        # Start the worker thread
        thread = threading.Thread(target=stream_worker)
        thread.daemon = True
        thread.start()
        
        # Return immediate success to unblock UI
        return create_success_response(request, {
            'status': 'streaming_started',
            'stream_id': request_id
        })
        
    except Exception as e:
        logger.error(f"Error in query_stream handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'QUERY_STREAM_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.clearCache')
def handle_clear_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle clear cache request.
    Clears LLM cache and deletes all storage data files (vector DB, graph DB, etc.).
    After deletion, automatically recreates the necessary initialization files.
    """
    try:
        import shutil
        import json
        from pathlib import Path
        from knowledge.lightrag_config_manager import get_config_manager
        
        # Get LightRAG client
        client = get_client()
        
        # Step 1: Call clear_cache API to clear LLM cache
        result = client.clear_cache()
        
        if result.get('status') == 'error':
            logger.warning(f"Clear cache API returned error: {result.get('message')}")
        
        # Step 2: Delete all storage data files
        config_manager = get_config_manager()
        working_dir = config_manager.get_value('WORKING_DIR')
        
        if working_dir and os.path.exists(working_dir):
            logger.info(f"[ClearCache] Deleting all data in working directory: {working_dir}")
            
            deleted_items = []
            errors = []
            
            # Delete all subdirectories and files in working_dir
            for item in Path(working_dir).iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                        deleted_items.append(f"Directory: {item.name}")
                    else:
                        item.unlink()
                        deleted_items.append(f"File: {item.name}")
                except Exception as e:
                    error_msg = f"Failed to delete {item.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"[ClearCache] {error_msg}")
            
            logger.info(f"[ClearCache] Deleted {len(deleted_items)} items")
            
            # Step 3: Recreate necessary initialization files for the working directory
            try:
                logger.info(f"[ClearCache] Recreating initialization files in: {working_dir}")
                
                # Create the working directory if it doesn't exist
                os.makedirs(working_dir, exist_ok=True)
                
                # Create essential KV store files with empty JSON objects
                kv_files = [
                    'kv_store_doc_status.json',
                    'kv_store_full_docs.json', 
                    'kv_store_llm_response_cache.json'
                ]
                
                for kv_file in kv_files:
                    kv_path = os.path.join(working_dir, kv_file)
                    with open(kv_path, 'w', encoding='utf-8') as f:
                        json.dump({}, f)
                    logger.info(f"[ClearCache] Created: {kv_file}")
                
                # Create graph database initialization file
                graph_file = 'graph_chunk_entity_relation_table.json'
                graph_path = os.path.join(working_dir, graph_file)
                with open(graph_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f)
                logger.info(f"[ClearCache] Created: {graph_file}")
                
                logger.info(f"[ClearCache] ✅ Initialization files recreated successfully")
                logger.info(f"[ClearCache] Note: Vector database indexes will be recreated automatically on first document upload")
                
            except Exception as e:
                error_msg = f"Failed to recreate initialization files: {str(e)}"
                errors.append(error_msg)
                logger.error(f"[ClearCache] {error_msg}")
            
            # Step 4: Restart LightRAG server to clear all in-memory state
            try:
                logger.info(f"[ClearCache] Restarting LightRAG server to clear in-memory state...")
                from app_context import AppContext
                main_window = AppContext.get_main_window()
                
                if main_window and hasattr(main_window, 'lightrag_server') and main_window.lightrag_server:
                    # Stop the server
                    main_window.lightrag_server.stop()
                    logger.info(f"[ClearCache] LightRAG server stopped")
                    
                    # Start the server again (start() already waits for ready, no need for sleep)
                    success = main_window.lightrag_server.start(wait_ready=True)
                    if success:
                        logger.info(f"[ClearCache] ✅ LightRAG server restarted successfully")
                    else:
                        error_msg = "Failed to restart LightRAG server"
                        errors.append(error_msg)
                        logger.error(f"[ClearCache] {error_msg}")
                else:
                    logger.warning(f"[ClearCache] LightRAG server not found, skipping restart")
                    
            except Exception as e:
                error_msg = f"Failed to restart LightRAG server: {str(e)}"
                errors.append(error_msg)
                logger.error(f"[ClearCache] {error_msg}")
            
            return create_success_response(request, {
                'status': 'success',
                'message': f'Successfully cleared cache, deleted {len(deleted_items)} items, and recreated initialization files',
                'deleted_items': deleted_items,
                'errors': errors
            })
        else:
            logger.warning(f"[ClearCache] Working directory not found or not configured: {working_dir}")
            return create_success_response(request, {
                'status': 'success',
                'message': 'Cache cleared (no working directory to clean)',
                'data': result.get('data', {})
            })
        
    except Exception as e:
        logger.error(f"Error in clear_cache handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'CLEAR_CACHE_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getStatusCounts')
def handle_get_status_counts(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle get status counts request (runs in background thread to avoid blocking UI).
    This is called frequently (every 3 seconds) during document processing.
    """
    try:
        # Get LightRAG client
        client = get_client()
        
        # Call get_status_counts method
        result = client.get_status_counts()
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Get status counts failed')
            logger.error(f"Get status counts failed: {error_msg}")
            return create_error_response(request, 'GET_STATUS_COUNTS_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in get_status_counts handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_STATUS_COUNTS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.health')
def handle_health(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle health check request.
    """
    try:
        # Get LightRAG client
        client = get_client()
        
        # Call health method
        result = client.health()
        
        if result.get('status') == 'error':
            return create_error_response(request, 'HEALTH_ERROR', result.get('message', 'Health check failed'))
        
        return create_success_response(request, result)
        
    except Exception as e:
        logger.error(f"Error in health handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'HEALTH_ERROR', str(e))


# File selection handlers for UI
@IPCHandlerRegistry.handler('fs.selectFiles')
def handle_select_files(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle file selection dialog.
    
    Expected params:
    - multiple: bool - Allow multiple file selection
    - filters: List[Dict] - File type filters (optional)
    """
    # File dialogs are not available in web mode (headless)
    if os.getenv('ECAN_MODE') == 'web':
        return create_error_response(
            request,
            'NOT_SUPPORTED',
            'File dialogs are not available in web/headless mode. Use file path parameters instead.'
        )
    
    try:
        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtCore import QThread, QObject, Signal, Qt
        import threading
        
        multiple = params.get('multiple', False) if params else False
        filters = params.get('filters', []) if params else []
        
        # Build filter string
        filter_strings = []
        for filter_item in filters:
            name = filter_item.get('name', 'All Files')
            extensions = filter_item.get('extensions', ['*'])
            ext_pattern = ' '.join([f'*.{ext}' for ext in extensions])
            filter_strings.append(f"{name} ({ext_pattern})")
        
        if not filter_strings:
            filter_strings = ['All Files (*.*)']
        
        filter_str = ';;'.join(filter_strings)
        start_dir = os.path.expanduser("~")
        
        # Check if we're already on the main thread
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            # Already on main thread, call directly
            if multiple:
                file_paths, _ = QFileDialog.getOpenFileNames(
                    None,
                    "Select Files",
                    start_dir,
                    filter_str
                )
                result = file_paths if file_paths else []
            else:
                file_path, _ = QFileDialog.getOpenFileName(
                    None,
                    "Select File",
                    start_dir,
                    filter_str
                )
                result = file_path if file_path else ''
        else:
            # Not on main thread, use signal/slot with threading.Event
            if not app:
                logger.error("[FS] No QApplication instance available")
                return create_error_response(
                    request,
                    'NO_QAPPLICATION',
                    'Qt application not initialized'
                )
            
            # Helper class for cross-thread dialog
            class DialogHelper(QObject):
                show_dialog = Signal(str, str, bool)
                
                def __init__(self):
                    super().__init__()
                    self.result = None
                    self.done_event = threading.Event()
                    self.show_dialog.connect(self._show_dialog_slot, Qt.ConnectionType.QueuedConnection)
                    
                def _show_dialog_slot(self, directory, filters, is_multiple):
                    try:
                        if is_multiple:
                            file_paths, _ = QFileDialog.getOpenFileNames(
                                None,
                                "Select Files",
                                directory,
                                filters
                            )
                            self.result = file_paths if file_paths else []
                        else:
                            file_path, _ = QFileDialog.getOpenFileName(
                                None,
                                "Select File",
                                directory,
                                filters
                            )
                            self.result = file_path if file_path else ''
                    except Exception as e:
                        logger.error(f"[FS] Error in dialog: {e}", exc_info=True)
                        self.result = [] if is_multiple else ''
                    finally:
                        self.done_event.set()
            
            # Create helper and move to main thread
            helper = DialogHelper()
            helper.moveToThread(app.thread())
            
            # Emit signal and wait for result
            helper.show_dialog.emit(start_dir, filter_str, multiple)
            if not helper.done_event.wait(timeout=60):  # 60 second timeout
                logger.error("[FS] Dialog timeout")
                return create_error_response(
                    request,
                    'DIALOG_TIMEOUT',
                    'File dialog timed out'
                )
            
            result = helper.result
        
        # Return result
        if multiple:
            if result:
                return create_success_response(request, {'paths': result})
            else:
                return create_success_response(request, {'paths': [], 'cancelled': True})
        else:
            if result:
                return create_success_response(request, {'path': result})
            else:
                return create_success_response(request, {'path': '', 'cancelled': True})
        
    except Exception as e:
        logger.error(f"Error in select_files handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SELECT_FILES_ERROR', str(e))


@IPCHandlerRegistry.handler('fs.selectDirectory')
def handle_select_directory(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle directory selection dialog.
    """
    # File dialogs are not available in web mode (headless)
    if os.getenv('ECAN_MODE') == 'web':
        return create_error_response(
            request,
            'NOT_SUPPORTED',
            'File dialogs are not available in web/headless mode. Use directory path parameters instead.'
        )
    
    try:
        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtCore import QThread, QObject, Signal, Qt
        import threading
        
        start_dir = os.path.expanduser("~")
        
        # Check if we're already on the main thread
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            # Already on main thread, call directly
            dir_path = QFileDialog.getExistingDirectory(
                None,
                "Select Directory",
                start_dir,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            result = dir_path if dir_path else ''
        else:
            # Not on main thread, use signal/slot with threading.Event
            if not app:
                logger.error("[FS] No QApplication instance available")
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
                        dir_path = QFileDialog.getExistingDirectory(
                            None,
                            "Select Directory",
                            directory,
                            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
                        )
                        self.result = dir_path if dir_path else ''
                    except Exception as e:
                        logger.error(f"[FS] Error in directory dialog: {e}", exc_info=True)
                        self.result = ''
                    finally:
                        self.done_event.set()
            
            # Create helper and move to main thread
            helper = DialogHelper()
            helper.moveToThread(app.thread())
            
            # Emit signal and wait for result
            helper.show_dialog.emit(start_dir)
            if not helper.done_event.wait(timeout=60):  # 60 second timeout
                logger.error("[FS] Directory dialog timeout")
                return create_error_response(
                    request,
                    'DIALOG_TIMEOUT',
                    'Directory dialog timed out'
                )
            
            result = helper.result
        
        # Return result
        if result:
            return create_success_response(request, {'path': result})
        else:
            return create_success_response(request, {'path': '', 'cancelled': True})
        
    except Exception as e:
        logger.error(f"Error in select_directory handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SELECT_DIRECTORY_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.updateEntity')
def handle_update_entity(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle entity update request (runs in background thread to avoid blocking UI)."""
    try:
        is_valid, data, error = validate_params(params, ['entity_name', 'updated_data'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        client = get_client()
        result = client.update_entity(
            data['entity_name'],
            data['updated_data'],
            data.get('allow_rename', False),
            data.get('allow_merge', False)
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'UPDATE_ENTITY_ERROR', result.get('message', 'Failed to update entity'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in update_entity handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_ENTITY_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.checkEntityNameExists')
def handle_check_entity_name_exists(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle check entity name exists request (runs in background thread to avoid blocking UI)."""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        client = get_client()
        result = client.check_entity_name_exists(data['name'])
        
        if result.get('status') == 'error':
            return create_error_response(request, 'CHECK_ENTITY_ERROR', result.get('message', 'Failed to check entity'))
            
        return create_success_response(request, result.get('data', result))
    except Exception as e:
        logger.error(f"Error in check_entity_name_exists handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'CHECK_ENTITY_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.updateRelation')
def handle_update_relation(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle relation update request (runs in background thread to avoid blocking UI)."""
    try:
        is_valid, data, error = validate_params(params, ['source_id', 'target_id', 'updated_data'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        client = get_client()
        result = client.update_relation(data['source_id'], data['target_id'], data['updated_data'])
        
        if result.get('status') == 'error':
            return create_error_response(request, 'UPDATE_RELATION_ERROR', result.get('message', 'Failed to update relation'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in update_relation handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_RELATION_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getGraphLabelList')
def handle_get_graph_label_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get graph label list request (runs in background thread to avoid blocking UI)."""
    try:
        client = get_client()
        result = client.get_graph_label_list()
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_LABEL_LIST_ERROR', result.get('message', 'Failed to get label list'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in get_graph_label_list handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_LABEL_LIST_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getPopularLabels')
def handle_get_popular_labels(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get popular labels request (runs in background thread to avoid blocking UI)."""
    try:
        params = params or {}
        limit = params.get('limit', 300)
        
        client = get_client()
        # Check if client has the method (for backward compatibility)
        if not hasattr(client, 'get_popular_labels'):
             return create_error_response(request, 'NOT_IMPLEMENTED', 'get_popular_labels not implemented in client')

        result = client.get_popular_labels(limit=limit)
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_POPULAR_LABELS_ERROR', result.get('message', 'Failed to get popular labels'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in get_popular_labels handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_POPULAR_LABELS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.searchLabels')
def handle_search_labels(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle search labels request (runs in background thread to avoid blocking UI)."""
    try:
        params = params or {}
        query = params.get('query', '')
        limit = params.get('limit', 50)
        
        if not query:
             return create_error_response(request, 'INVALID_PARAMS', 'query must be provided')

        client = get_client()
        # Check if client has the method (for backward compatibility)
        if not hasattr(client, 'search_labels'):
             return create_error_response(request, 'NOT_IMPLEMENTED', 'search_labels not implemented in client')

        result = client.search_labels(q=query, limit=limit)
        
        if result.get('status') == 'error':
            return create_error_response(request, 'SEARCH_LABELS_ERROR', result.get('message', 'Failed to search labels'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in search_labels handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SEARCH_LABELS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getDocumentsPaginated')
def handle_get_documents_paginated(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle paginated documents request (runs in background thread to avoid blocking UI)."""
    try:
        # Default params
        defaults = {
            'page': 1,
            'page_size': 20,
            'sort_field': 'created_at',
            'sort_direction': 'desc'
        }
        request_params = {**defaults, **(params or {})}
        
        logger.info(f"[lightrag_handler] get_documents_paginated called with params: {request_params}")
        
        client = get_client()
        
        # Call synchronously (this runs in a background thread via registry)
        result = client.get_documents_paginated(request_params)
        
        # logger.info(f"[lightrag_handler] Client returned result type: {type(result)}, value: {result}")
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to get documents')
            logger.error(f"Get documents paginated failed: {error_msg}")
            return create_error_response(request, 'GET_DOCUMENTS_ERROR', error_msg)
            
        # Extract data from client response
        # Client returns: {"status": "success", "data": {...}}
        response_data = result.get('data', result)
        
        # Log document count for debugging
        if isinstance(response_data, dict):
            docs = response_data.get('documents', [])
            logger.info(f"[lightrag_handler] Returning {len(docs)} documents")
        
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"[lightrag_handler] Error in get_documents_paginated handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_DOCUMENTS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getProcessingProgress')
def handle_get_processing_progress(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get document processing progress using LightRAG track_status API (runs in background thread to avoid blocking UI).
    This is called frequently (every 3 seconds) during document processing.
    
    Expected params:
    - track_id: Optional track ID to monitor specific batch
    
    Returns progress information including:
    - processing_count: Number of documents being processed
    - pending_count: Number of documents pending
    - processed_count: Number of documents completed
    - failed_count: Number of documents failed
    - total_count: Total number of documents
    - progress_percentage: Progress as percentage (0-100)
    - status: Processing status (idle, processing, completed)
    - documents: List of documents with their status (if track_id provided)
    """
    try:
        track_id = params.get('track_id') if params else None
        
        # Get LightRAG client
        client = get_client()
        
        if track_id:
            # Get detailed progress for specific track_id
            result = client.track_status(track_id)
            
            if result.get('status') == 'error':
                error_msg = result.get('message', 'Failed to get track status')
                logger.error(f"Track status failed: {error_msg}")
                return create_error_response(request, 'TRACK_STATUS_ERROR', error_msg)
            
            data = result.get('data', {})
            documents = data.get('documents', [])
            status_summary = data.get('status_summary', {})
            
            # Calculate progress from status summary
            processing = status_summary.get('PROCESSING', 0) + status_summary.get('PREPROCESSED', 0)
            pending = status_summary.get('PENDING', 0)
            processed = status_summary.get('PROCESSED', 0)
            failed = status_summary.get('FAILED', 0)
            total = processing + pending + processed + failed
            
            if total > 0:
                progress_percentage = int((processed / total) * 100)
                if processing > 0 or pending > 0:
                    status = 'processing'
                else:
                    status = 'completed'
            else:
                progress_percentage = 0
                status = 'idle'
            
            return create_success_response(request, {
                'status': status,
                'processing_count': processing,
                'pending_count': pending,
                'processed_count': processed,
                'failed_count': failed,
                'total_count': total,
                'progress_percentage': progress_percentage,
                'track_id': track_id,
                'documents': documents
            })
        else:
            # Get overall status from status counts
            result = client.get_status_counts()
            
            if result.get('status') == 'error':
                error_msg = result.get('message', 'Failed to get status counts')
                logger.error(f"Get status counts failed: {error_msg}")
                return create_error_response(request, 'STATUS_COUNTS_ERROR', error_msg)
            
            data = result.get('data', {})
            status_counts = data.get('status_counts', {}) if 'status_counts' in data else data
            
            # Calculate progress from status counts
            processing = status_counts.get('PROCESSING', 0) + status_counts.get('PREPROCESSED', 0)
            pending = status_counts.get('PENDING', 0)
            processed = status_counts.get('PROCESSED', 0)
            failed = status_counts.get('FAILED', 0)
            total = processing + pending + processed + failed
            
            # Try to get more detailed progress from pipeline status
            pipeline_result = client.get_pipeline_status()
            pipeline_data = pipeline_result.get('data', {}) if pipeline_result.get('status') == 'success' else {}
            
            logger.info(f"[lightrag_handler] Pipeline status: busy={pipeline_data.get('busy')}, cur_batch={pipeline_data.get('cur_batch')}, total_batches={pipeline_data.get('batchs')}")
            
            if total > 0:
                # Base progress on completed documents
                base_progress = (processed + failed) / total
                
                # If pipeline is busy and provides batch info, add fine-grained progress
                if pipeline_data.get('busy') and processing > 0:
                    total_batches = pipeline_data.get('batchs', 0)
                    current_batch = pipeline_data.get('cur_batch', 0)
                    
                    if total_batches > 0 and current_batch > 0:
                        # Add progress within the current processing document
                        # Each document contributes 1/total to overall progress
                        # Within that document, batch progress contributes proportionally
                        batch_progress = current_batch / total_batches
                        document_contribution = 1 / total
                        
                        # Add partial progress for the document being processed
                        base_progress += (batch_progress * document_contribution)
                
                progress_percentage = int(min(100, base_progress * 100))
                
                if processing > 0 or pending > 0:
                    status = 'processing'
                else:
                    status = 'completed'
            else:
                progress_percentage = 0
                status = 'idle'
            
            response_data = {
                'status': status,
                'processing_count': processing,
                'pending_count': pending,
                'processed_count': processed,
                'failed_count': failed,
                'total_count': total,
                'progress_percentage': progress_percentage
            }
            
            # Include pipeline details if available
            # Show pipeline info when busy OR when there are processing/pending documents
            if pipeline_data.get('busy') or processing > 0 or pending > 0:
                logger.info(f"[lightrag_handler] Including pipeline data: busy={pipeline_data.get('busy')}, processing={processing}, pending={pending}")
                
                # Get chunk progress from pipeline_data (set by operate_custom.py)
                total_chunks = pipeline_data.get('total_chunks', 0)
                processed_chunks = pipeline_data.get('processed_chunks', 0)
                # Get current processing file path for per-document progress display
                current_chunk_file = pipeline_data.get('current_chunk_file', None)
                
                pipeline_info = {
                    'job_name': pipeline_data.get('job_name'),
                    'current_batch': pipeline_data.get('cur_batch', 0),
                    'total_batches': pipeline_data.get('batchs', 0),
                    'latest_message': pipeline_data.get('latest_message'),
                    'total_chunks': total_chunks if total_chunks > 0 else None,
                    'processed_chunks': processed_chunks if total_chunks > 0 else None,
                    'current_chunk_file': current_chunk_file  # File path of current processing document
                }
                
                logger.info(f"[lightrag_handler] Pipeline info: {pipeline_info}")
                response_data['pipeline'] = pipeline_info
            
            return create_success_response(request, response_data)
        
    except Exception as e:
        logger.error(f"Error in get_processing_progress handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_PROGRESS_ERROR', str(e))


# Settings persistence using config manager
from knowledge.lightrag_config_manager import get_config_manager


@IPCHandlerRegistry.handler('lightrag.saveSettings')
def handle_save_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save LightRAG settings to .env file."""
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'No settings provided')
        
        # Log received settings for debugging
        logger.info(f"[LightRAG] Received {len(params)} settings to save")
        
        # Log key Ollama settings
        ollama_keys = ['EMBEDDING_BINDING_HOST', 'LLM_BINDING_HOST', 'EMBEDDING_BINDING', 'LLM_BINDING']
        for key in ollama_keys:
            if key in params:
                logger.info(f"[LightRAG] {key} = {params[key]}")
        
        # Validate and adjust configuration based on provider limits
        from knowledge.provider_limits_validator import validate_lightrag_config
        
        embedding_provider = params.get('EMBEDDING_BINDING', '')
        if embedding_provider and 'EMBEDDING_BATCH_NUM' in params:
            logger.info(f"[LightRAG] Validating config for embedding provider: {embedding_provider}")
            adjusted_params, warnings = validate_lightrag_config(embedding_provider, params)
            
            # Log any adjustments
            if warnings:
                for warning in warnings:
                    logger.warning(f"[LightRAG] {warning}")
            
            # Use adjusted parameters
            params = adjusted_params
        
        # Process rerank provider settings - auto-configure proxy for non-native providers
        from knowledge.lightrag_constants import is_native_rerank_provider
        
        if 'RERANK_BINDING' in params:
            rerank_binding = params.get('RERANK_BINDING', '').lower()
            
            # Check if this is a non-native provider that needs proxy
            if rerank_binding and not is_native_rerank_provider(rerank_binding):
                logger.info(f"[LightRAG] Non-native rerank provider detected: {rerank_binding}")
                
                # Get local server port
                from app_context import AppContext
                main_window = AppContext.get_main_window()
                if main_window:
                    local_server_port = main_window.get_local_server_port()
                    proxy_url = f"http://localhost:{local_server_port}/api/rerank"
                    
                    # Only set proxy URL, keep original RERANK_BINDING for UI display
                    params['RERANK_BINDING_HOST'] = proxy_url
                    
                    logger.info(f"[LightRAG] Auto-configured rerank proxy:")
                    logger.info(f"[LightRAG]   - Provider: {rerank_binding}")
                    logger.info(f"[LightRAG]   - Proxy URL: {proxy_url}")
                    logger.info(f"[LightRAG]   - Note: Will be converted to jina format at runtime")
        
        # Filter out system-managed keys to avoid saving them to local env file
        # This ensures the file remains clean and system settings remain authoritative
        keys_to_exclude = ['_SYSTEM_LLM_KEY_SOURCE', '_SYSTEM_EMBED_KEY_SOURCE', '_SYSTEM_RERANK_KEY_SOURCE']
        
        # Also exclude the actual API key fields if they are system managed
        # The frontend sends back the system key value (masked or raw), but we must NOT save it
        if params.get('_SYSTEM_LLM_KEY_SOURCE'):
            keys_to_exclude.extend(['LLM_BINDING_API_KEY', 'OPENAI_API_KEY'])
            
        if params.get('_SYSTEM_EMBED_KEY_SOURCE'):
            keys_to_exclude.append('EMBEDDING_BINDING_API_KEY')
        
        if params.get('_SYSTEM_RERANK_KEY_SOURCE'):
            keys_to_exclude.append('RERANK_BINDING_API_KEY')
        
        settings_to_save = {k: v for k, v in params.items() if k not in keys_to_exclude}
        
        logger.info(f"[LightRAG] Saving {len(settings_to_save)} settings after filtering")
        
        config_manager = get_config_manager()
        success = config_manager.update_config(settings_to_save)
        
        if not success:
            logger.error("[LightRAG] Failed to save settings to file")
            return create_error_response(request, 'CONFIG_ERROR', 'Failed to save settings')
        
        logger.info("[LightRAG] ✅ Settings saved successfully")
        return create_success_response(request, {'success': True, 'message': 'Settings saved'})
    except Exception as e:
        logger.error(f"[LightRAG] Error saving settings: {e}", exc_info=True)
        return create_error_response(request, 'SAVE_SETTINGS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.restartServer')
def handle_restart_server(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Restart LightRAG server to apply new settings (runs in background thread to avoid blocking UI)."""
    try:
        from app_context import AppContext
        from knowledge.lightrag_server import LightragServer
        
        # Get MainWindow instance
        main_window = AppContext.get_main_window()
        if not main_window:
            return create_error_response(request, 'MAIN_WINDOW_NOT_FOUND', 'MainWindow instance not found')
        
        # Check if server exists
        if not hasattr(main_window, 'lightrag_server') or not main_window.lightrag_server:
            return create_error_response(request, 'SERVER_NOT_RUNNING', 'LightRAG server is not running')
        
        # Stop the server
        logger.info("[LightRAG] Stopping server for restart...")
        main_window.stop_lightrag_server()
        
        # Restart the server synchronously (we're already in a background thread)
        logger.info("[LightRAG] Starting new server instance...")
        main_window.lightrag_server = LightragServer()
        success = main_window.lightrag_server.start(wait_ready=True)
        
        if success:
            logger.info("[LightRAG] ✅ Server restarted successfully")
            return create_success_response(request, {'success': True, 'message': 'Server restarted successfully'})
        else:
            logger.error("[LightRAG] ❌ Server restart failed")
            startup_message = 'Failed to restart server'
            try:
                status = main_window.lightrag_server.get_startup_status()
                if status and status.get('message'):
                    startup_message = status['message']
            except Exception:
                pass
            return create_error_response(request, 'RESTART_FAILED', startup_message)
            
    except Exception as e:
        logger.error(f"Error restarting LightRAG server: {e}", exc_info=True)
        return create_error_response(request, 'RESTART_SERVER_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getStartupStatus')
def handle_get_startup_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get current LightRAG startup/running status for UI availability indicators."""
    try:
        from app_context import AppContext

        main_window = AppContext.get_main_window()
        if not main_window or not hasattr(main_window, 'lightrag_server') or not main_window.lightrag_server:
            return create_success_response(request, {
                'running': False,
                'ok': False,
                'message': 'LightRAG server is not initialized',
                'error_type': 'not_initialized',
                'timestamp': 0,
            })

        server = main_window.lightrag_server
        startup_status = server.get_startup_status() if hasattr(server, 'get_startup_status') else {}
        running = bool(server.is_running()) if hasattr(server, 'is_running') else False

        status_ok = startup_status.get('ok')
        if status_ok is None:
            status_ok = running

        return create_success_response(request, {
            'running': running,
            'ok': status_ok,
            'message': startup_status.get('message', ''),
            'error_type': startup_status.get('error_type', ''),
            'timestamp': startup_status.get('timestamp', 0),
        })
    except Exception as e:
        logger.error(f"[LightRAG] Error getting startup status: {e}", exc_info=True)
        return create_error_response(request, 'GET_STARTUP_STATUS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getWorkspaces')
def handle_get_workspaces(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get list of available LightRAG workspaces by scanning rag_storage subdirectories.
    
    Workspaces are subdirectories under rag_storage (e.g., rag_storage/test2, rag_storage/test3)
    Only actual workspace directories are included, not system directories like inputs.
    """
    try:
        config_manager = get_config_manager()
        
        # Get base working directory from config
        base_working_dir = config_manager.get_value('WORKING_DIR')
        
        if not base_working_dir:
            logger.warning("[LightRAG] WORKING_DIR not configured")
            return create_success_response(request, {
                'workspaces': [],
                'current': config_manager.get_value('WORKSPACE', 'default')
            })
        
        # Extract the rag_storage directory path
        # WORKING_DIR format: /path/to/lightrag/rag_storage/workspace_name
        # We need: /path/to/lightrag/rag_storage
        
        # First, check if WORKING_DIR already ends with rag_storage
        if base_working_dir.endswith('rag_storage'):
            rag_storage_dir = base_working_dir
        elif 'rag_storage' in base_working_dir:
            # Find the rag_storage directory
            parts = base_working_dir.split('/')
            rag_storage_index = -1
            for i, part in enumerate(parts):
                if part == 'rag_storage':
                    rag_storage_index = i
                    break
            
            if rag_storage_index >= 0:
                # Reconstruct path up to and including rag_storage
                rag_storage_dir = '/'.join(parts[:rag_storage_index + 1])
            else:
                # Fallback: remove last component
                rag_storage_dir = base_working_dir.rsplit('/', 1)[0]
        else:
            # Fallback: remove last component
            rag_storage_dir = base_working_dir.rsplit('/', 1)[0] if '/' in base_working_dir else base_working_dir
        
        logger.info(f"[LightRAG] Base WORKING_DIR: {base_working_dir}")
        logger.info(f"[LightRAG] Extracted rag_storage_dir: {rag_storage_dir}")
        
        # Scan for workspace subdirectories in rag_storage
        workspaces = []
        if os.path.exists(rag_storage_dir):
            logger.info(f"[LightRAG] Scanning workspaces in: {rag_storage_dir}")
            for item in os.listdir(rag_storage_dir):
                # Skip system directories and files
                if item in ['inputs', 'outputs', 'logs', '.git', '__pycache__', 'rag_storage', 'tiktoken', 'cache']:
                    logger.debug(f"[LightRAG] Skipping system directory: {item}")
                    continue
                
                # Skip hidden files and directories
                if item.startswith('.'):
                    continue
                    
                item_path = os.path.join(rag_storage_dir, item)
                if os.path.isdir(item_path):
                    logger.debug(f"[LightRAG] Found workspace candidate: {item}")
                    workspaces.append({
                        'name': item,
                        'is_valid': True
                    })
            logger.info(f"[LightRAG] Found {len(workspaces)} workspaces: {[w['name'] for w in workspaces]}")
        else:
            logger.warning(f"[LightRAG] rag_storage directory does not exist: {rag_storage_dir}")
        
        # Get current workspace from config
        current_workspace = config_manager.get_value('WORKSPACE', 'default')
        
        # If no workspaces found, add the current workspace as default
        if not workspaces:
            workspaces.append({
                'name': current_workspace,
                'is_valid': True
            })
        
        return create_success_response(request, {
            'workspaces': workspaces,
            'current': current_workspace
        })
    except Exception as e:
        logger.error(f"[LightRAG] Error getting workspaces: {e}", exc_info=True)
        return create_error_response(request, 'GET_WORKSPACES_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.deleteWorkspace')
def handle_delete_workspace(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete a workspace folder and its contents.
    
    This will delete the workspace-specific directory structure:
    - {user_data_path}/lightrag_{workspace_name}/
    """
    try:
        if not params or 'workspace_name' not in params:
            return create_error_response(request, 'INVALID_PARAMS', 'workspace_name is required')
        
        workspace_name = params['workspace_name'].strip()
        
        if not workspace_name:
            return create_error_response(request, 'INVALID_PARAMS', 'workspace_name cannot be empty')
        
        # Check if it's the current workspace
        config_manager = get_config_manager()
        current_workspace = config_manager.get_value('WORKSPACE', '')
        
        if current_workspace == workspace_name:
            return create_error_response(request, 'WORKSPACE_IN_USE', 
                                        f"Cannot delete workspace '{workspace_name}' because it is currently in use. Please switch to another workspace first.")
        
        from utils.path_manager import get_user_data_path
        from gui.ipc.context_bridge import get_handler_context
        import shutil
        
        # Get current user from context
        ctx = get_handler_context(request, params)
        user = ctx.main_window.log_user if ctx and ctx.main_window else None
        
        # Build workspace folder path
        user_data_path = get_user_data_path(user)
        workspace_folder = os.path.join(user_data_path, f'lightrag_{workspace_name}')
        
        # Check if workspace folder exists
        if not os.path.exists(workspace_folder):
            return create_error_response(request, 'WORKSPACE_NOT_FOUND', 
                                        f"Workspace folder '{workspace_name}' does not exist")
        
        # Delete the workspace folder
        shutil.rmtree(workspace_folder)
        logger.info(f"[LightRAG] ✅ Deleted workspace folder: {workspace_folder}")
        
        return create_success_response(request, {
            'success': True,
            'workspace_name': workspace_name,
            'message': f"Workspace '{workspace_name}' deleted successfully"
        })
    except Exception as e:
        logger.error(f"[LightRAG] Error deleting workspace: {e}", exc_info=True)
        return create_error_response(request, 'DELETE_WORKSPACE_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getSettings')
def handle_get_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get LightRAG settings from .env file."""
    try:
        config_manager = get_config_manager()
        # Use effective config which includes overlaid system API keys
        settings = config_manager.get_effective_config()
        
        # Log specific keys for debugging
        debug_keys = ['TOP_K', 'CHUNK_TOP_K', 'MAX_ENTITY_TOKENS', 'RERANK_BY_DEFAULT']
        debug_subset = {k: settings.get(k) for k in debug_keys}
        logger.info(f"[GetSettings] Returning {len(settings)} keys. Sample: {debug_subset}")
        
        return create_success_response(request, settings)
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return create_error_response(request, 'GET_SETTINGS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.queryGraphs')
def handle_query_graphs(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle graph query request (runs in background thread to avoid blocking UI).
    Expected params:
    - label: str - Node label to search for (or '*')
    - maxDepth: int - Traversal depth
    - maxNodes: int - Max nodes to return
    """
    try:
        params = params or {}
        label = params.get('label', '*')
        max_depth = params.get('maxDepth', 1)
        max_nodes = params.get('maxNodes', 400)
        
        client = get_client()
        # Call query_graphs method (assumed to be added to client)
        if hasattr(client, 'query_graphs'):
            result = client.query_graphs(label, max_depth, max_nodes)
        else:
            # Fallback mock if not implemented yet
            return create_success_response(request, {'nodes': [], 'edges': [], 'is_truncated': False})
        
        if isinstance(result, dict) and result.get('status') == 'error':
            return create_error_response(request, 'QUERY_GRAPH_ERROR', result.get('message', 'Failed to query graph'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in query_graphs handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'QUERY_GRAPH_ERROR', str(e))


def _convert_providers_to_lightrag_ui(providers: List[Dict[str, Any]], provider_type: str, manager) -> List[Dict[str, Any]]:
    """
    Convert standard provider format to LightRAG UI format.
    
    Args:
        providers: List of provider dicts from manager.get_all_providers()
        provider_type: 'LLM', 'EMBEDDING', or 'RERANK'
        manager: Manager instance for retrieving API keys
    
    Returns:
        List of provider dicts in LightRAG UI format
    """
    ui_providers = []
    
    for p in providers:
        # Build model field
        model_key = f'{provider_type}_MODEL'
        default_model = p.get('default_model', '')
        model_field = {
            'key': model_key,
            'label': 'fields.model',
            'type': 'text',
            'required': True,
            'defaultValue': default_model
        }
        
        # Add model options if available
        supported_models = p.get('supported_models', [])
        if supported_models:
            model_field['type'] = 'select'
            model_field['options'] = [
                {'value': m.get('model_id'), 'label': m.get('display_name') or m.get('name')}
                for m in supported_models
            ]
        
        fields = [model_field]
        model_metadata = {}
        
        # Embedding-specific fields
        if provider_type == 'EMBEDDING':
            fields.append({'key': 'EMBEDDING_DIM', 'label': 'fields.dimensions', 'type': 'number', 'placeholder': '1024', 'disabled': True})
            fields.append({'key': 'EMBEDDING_TOKEN_LIMIT', 'label': 'fields.tokenLimit', 'type': 'number', 'placeholder': '8192', 'disabled': True})
            # Build model metadata
            for m in supported_models:
                model_metadata[m.get('model_id')] = {
                    'dimensions': m.get('dimensions'),
                    'max_tokens': m.get('max_tokens')
                }
        
        # Host field for local providers
        if p.get('base_url') or p.get('is_local'):
            host_key = f'{provider_type}_BINDING_HOST'
            fields.append({
                'key': host_key,
                'label': 'fields.apiHost',
                'type': 'text',
                'defaultValue': p.get('base_url', ''),
                'disabled': True
            })
        
        # API key field
        api_key_env_vars = p.get('api_key_env_vars', [])
        if api_key_env_vars and manager:
            api_key_key = f'{provider_type}_BINDING_API_KEY'
            field_def = {
                'key': api_key_key,
                'label': 'fields.apiKey',
                'type': 'password',
                'required': True
            }
            
            # Try to retrieve API key
            try:
                for env_var in api_key_env_vars:
                    api_key = manager.retrieve_api_key(env_var)
                    if api_key:
                        field_def['isSystemManaged'] = True
                        field_def['defaultValue'] = api_key
                        break
            except Exception as e:
                logger.warning(f"Failed to retrieve API key for {p.get('provider')}: {e}")
            
            fields.append(field_def)
        
        # Build provider UI object
        provider_ui = {
            'id': p.get('provider'),
            'name': p.get('display_name'),
            'description': p.get('description'),
            'fields': fields
        }
        
        # Add model metadata for embedding providers
        if provider_type == 'EMBEDDING' and model_metadata:
            provider_ui['modelMetadata'] = model_metadata
        
        ui_providers.append(provider_ui)
    
    return ui_providers


@IPCHandlerRegistry.handler('lightrag.getSystemProviders')
def handle_get_system_providers(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Get system LLM, Embedding and Rerank providers for LightRAG configuration.
    
    Reuses existing provider handlers to ensure consistency with Settings page.
    """
    try:
        from app_context import AppContext
        from gui.ipc.context_bridge import get_handler_context
        from gui.ollama_utils import merge_ollama_models_to_providers
        from gui.ryoais_utils import merge_ryoais_models_to_providers
        
        # Get manager instances
        ctx = get_handler_context(request, params)
        llm_manager = ctx.get_config_manager().llm_manager if ctx else None
        embedding_manager = ctx.get_config_manager().embedding_manager if ctx else None
        rerank_manager = ctx.get_config_manager().rerank_manager if ctx else None
        
        # Get providers with Ollama and RyoAIS models merged (same as Settings page)
        llm_providers = merge_ollama_models_to_providers(
            llm_manager.get_all_providers() if llm_manager else [],
            provider_type='llm'
        )
        llm_providers = merge_ryoais_models_to_providers(
            llm_providers,
            provider_type='llm'
        )
        
        embedding_providers = merge_ollama_models_to_providers(
            embedding_manager.get_all_providers() if embedding_manager else [],
            provider_type='embedding'
        )
        embedding_providers = merge_ryoais_models_to_providers(
            embedding_providers,
            provider_type='embedding'
        )
        
        rerank_providers = merge_ollama_models_to_providers(
            rerank_manager.get_all_providers() if rerank_manager else [],
            provider_type='rerank'
        )
        rerank_providers = merge_ryoais_models_to_providers(
            rerank_providers,
            provider_type='rerank'
        )
        
        # Convert to LightRAG UI format
        llm_providers_ui = _convert_providers_to_lightrag_ui(llm_providers, 'LLM', llm_manager)
        embedding_providers_ui = _convert_providers_to_lightrag_ui(embedding_providers, 'EMBEDDING', embedding_manager)
        rerank_providers_ui = _convert_providers_to_lightrag_ui(rerank_providers, 'RERANK', rerank_manager)
        
        return create_success_response(request, {
            'llm_providers': llm_providers_ui,
            'embedding_providers': embedding_providers_ui,
            'rerank_providers': rerank_providers_ui
        })
    except Exception as e:
        logger.error(f"Error getting system providers: {e}")
        return create_error_response(request, 'SYSTEM_PROVIDERS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getInputHistory')
def handle_get_input_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get input history from storage."""
    try:
        config_manager = get_config_manager()
        working_dir = config_manager.get_value('WORKING_DIR')
        
        if not working_dir or not os.path.exists(working_dir):
            return create_success_response(request, [])
            
        history_file = os.path.join(working_dir, 'lightrag_input_history.json')
        if not os.path.exists(history_file):
            return create_success_response(request, [])
            
        with open(history_file, 'r', encoding='utf-8') as f:
            try:
                content = f.read().strip()
                if not content:
                    history = []
                else:
                    history = json.loads(content)
            except json.JSONDecodeError:
                logger.warning(f"Corrupted history file found at {history_file}, resetting to empty.")
                history = []
            
        return create_success_response(request, history)
    except Exception as e:
        logger.error(f"Error getting input history: {e}")
        # Return empty list on error to not break UI
        return create_success_response(request, [])


@IPCHandlerRegistry.handler('lightrag.saveInputHistory')
def handle_save_input_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save input history to storage."""
    try:
        history = params.get('history', [])
        if not isinstance(history, list):
            return create_error_response(request, 'INVALID_PARAMS', 'History must be a list')
            
        config_manager = get_config_manager()
        working_dir = config_manager.get_value('WORKING_DIR')
        
        if not working_dir:
             return create_error_response(request, 'CONFIG_ERROR', 'Working directory not configured')
             
        if not os.path.exists(working_dir):
            os.makedirs(working_dir, exist_ok=True)
            
        history_file = os.path.join(working_dir, 'lightrag_input_history.json')
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
        return create_success_response(request, {'success': True})
    except Exception as e:
        logger.error(f"Error saving input history: {e}")
        return create_error_response(request, 'SAVE_HISTORY_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getConversationHistory')
def handle_get_conversation_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get conversation history (messages) from storage."""
    try:
        config_manager = get_config_manager()
        working_dir = config_manager.get_value('WORKING_DIR')
        
        if not working_dir or not os.path.exists(working_dir):
            return create_success_response(request, [])
            
        history_file = os.path.join(working_dir, 'lightrag_conversation_history.json')
        if not os.path.exists(history_file):
            return create_success_response(request, [])
            
        with open(history_file, 'r', encoding='utf-8') as f:
            try:
                content = f.read().strip()
                if not content:
                    history = []
                else:
                    history = json.loads(content)
            except json.JSONDecodeError:
                logger.warning(f"Corrupted conversation history file at {history_file}, resetting.")
                history = []
            
        return create_success_response(request, history)
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        return create_success_response(request, [])


@IPCHandlerRegistry.handler('lightrag.saveConversationHistory')
def handle_save_conversation_history(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save conversation history (messages) to storage."""
    try:
        messages = params.get('messages', [])
        if not isinstance(messages, list):
            return create_error_response(request, 'INVALID_PARAMS', 'Messages must be a list')
            
        config_manager = get_config_manager()
        working_dir = config_manager.get_value('WORKING_DIR')
        
        if not working_dir:
             return create_error_response(request, 'CONFIG_ERROR', 'Working directory not configured')
             
        if not os.path.exists(working_dir):
            os.makedirs(working_dir, exist_ok=True)
            
        history_file = os.path.join(working_dir, 'lightrag_conversation_history.json')
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
            
        return create_success_response(request, {'success': True})
    except Exception as e:
        logger.error(f"Error saving conversation history: {e}")
        return create_error_response(request, 'SAVE_CONVERSATION_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.expandNode')
def handle_expand_node(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle node expansion request - query neighbors of a node.
    
    Expected params:
    - nodeId: str - Node ID to expand
    - maxDepth: int - Traversal depth (default: 1)
    - maxNodes: int - Max nodes to return (default: 50)
    """
    try:
        is_valid, data, error = validate_params(params, ['nodeId'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        node_id = data['nodeId']
        max_depth = data.get('maxDepth', 1)
        max_nodes = data.get('maxNodes', 50)
        
        client = get_client()
        
        # Call expand_node method
        if hasattr(client, 'expand_node'):
            result = client.expand_node(node_id, max_depth, max_nodes)
        else:
            # Fallback: use query_graphs with the node label
            logger.warning("expand_node not implemented in client, using query_graphs fallback")
            if hasattr(client, 'query_graphs'):
                # Try to get node label from node_id
                result = client.query_graphs(node_id, max_depth, max_nodes)
            else:
                return create_success_response(request, {'nodes': [], 'edges': [], 'is_truncated': False})
        
        if isinstance(result, dict) and result.get('status') == 'error':
            return create_error_response(request, 'EXPAND_NODE_ERROR', result.get('message', 'Failed to expand node'))
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in expand_node handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'EXPAND_NODE_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.pruneNode')
def handle_prune_node(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle node pruning request - remove a node from the graph.
    
    Expected params:
    - nodeId: str - Node ID to remove
    """
    try:
        is_valid, data, error = validate_params(params, ['nodeId'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        node_id = data['nodeId']
        
        client = get_client()
        
        # Call prune_node method
        if hasattr(client, 'prune_node'):
            result = client.prune_node(node_id)
        else:
            # Fallback: just return success (client-side removal only)
            logger.warning("prune_node not implemented in client, returning success for client-side removal")
            return create_success_response(request, {
                'success': True,
                'message': 'Node removed from client-side graph (server-side removal not implemented)'
            })
        
        if isinstance(result, dict) and result.get('status') == 'error':
            return create_error_response(request, 'PRUNE_NODE_ERROR', result.get('message', 'Failed to prune node'))
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in prune_node handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'PRUNE_NODE_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.checkEmbeddingDimension')
def handle_check_embedding_dimension(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Check if the new embedding dimension conflicts with existing vector database.
    
    Expected params:
    - newDimension: int - The new embedding dimension
    - workspaceName: str - Current workspace name
    
    Returns:
    - hasConflict: bool - Whether there's a dimension conflict
    - currentDimension: int|None - Current dimension in vector database (if exists)
    - vectorStorage: str - Type of vector storage being used
    - workspaces: List[Dict] - Available workspaces
    """
    try:
        is_valid, data, error = validate_params(params, ['newDimension', 'workspaceName'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        new_dimension = data['newDimension']
        workspace_name = data['workspaceName']
        
        if not isinstance(new_dimension, int) or new_dimension <= 0:
            return create_error_response(request, 'INVALID_PARAMS', 'newDimension must be a positive integer')
        
        config_manager = get_config_manager()
        base_working_dir = config_manager.get_value('WORKING_DIR')
        
        if not base_working_dir or not os.path.exists(base_working_dir):
            # No existing workspace, no conflict
            return create_success_response(request, {
                'hasConflict': False,
                'currentDimension': None,
                'newDimension': new_dimension,
                'vectorStorage': 'unknown',
                'workspaceName': workspace_name,
                'workspaces': []
            })
        
        # Resolve workspace directory robustly.
        # WORKING_DIR may already point to the current workspace folder,
        # or to a parent folder containing workspace subdirectories.
        workspace_candidates = []
        if workspace_name and os.path.basename(os.path.normpath(base_working_dir)) == workspace_name:
            workspace_candidates.append(base_working_dir)
        workspace_candidates.append(os.path.join(base_working_dir, workspace_name))
        workspace_candidates.append(base_working_dir)

        working_dir = next((p for p in workspace_candidates if p and os.path.isdir(p)), None)

        logger.info(f"Checking workspace directory candidates: {workspace_candidates}")
        logger.info(f"Resolved workspace directory: {working_dir}")

        if not working_dir:
            # Workspace directory doesn't exist yet, no conflict
            logger.info(f"Workspace directory does not exist for workspace: {workspace_name}")
            return create_success_response(request, {
                'hasConflict': False,
                'currentDimension': None,
                'newDimension': new_dimension,
                'vectorStorage': config_manager.get_value('LIGHTRAG_VECTOR_STORAGE') or 'FaissVectorDBStorage',
                'workspaceName': workspace_name,
                'workspaces': []
            })
        
        # Get vector storage type from config
        vector_storage = config_manager.get_value('LIGHTRAG_VECTOR_STORAGE') or 'FaissVectorDBStorage'
        logger.info(f"Checking dimension for vector storage: {vector_storage}")
        
        # Check dimension based on vector storage type
        current_dimension = None
        
        if 'Faiss' in vector_storage or 'FAISS' in vector_storage:
            # Check FAISS index files
            faiss_files = [
                'vdb_entities.index',
                'vdb_chunks.index',
                'vdb_relationships.index',
                'faiss_index_chunks.index',
                'faiss_index_entities.index',
                'faiss_index_relationships.index'
            ]
            
            for faiss_file in faiss_files:
                faiss_path = os.path.join(working_dir, faiss_file)
                if os.path.exists(faiss_path):
                    try:
                        import faiss
                        index = faiss.read_index(faiss_path)
                        current_dimension = index.d
                        logger.info(f"Detected FAISS index dimension: {current_dimension} from {faiss_file}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to read FAISS index {faiss_file}: {e}")
                        continue
        
        elif 'Milvus' in vector_storage:
            # Check Milvus collection schema
            try:
                from pymilvus import MilvusClient
                milvus_uri = config_manager.get_value('MILVUS_URI') or 'http://localhost:19530'
                milvus_db = config_manager.get_value('MILVUS_DB_NAME') or 'lightrag'
                
                client = MilvusClient(uri=milvus_uri, db_name=milvus_db)
                
                # Check chunks collection
                collection_name = f"{workspace_name}_chunks"
                if client.has_collection(collection_name):
                    schema = client.describe_collection(collection_name)
                    for field in schema.get('fields', []):
                        if field.get('name') == 'embedding':
                            current_dimension = field.get('params', {}).get('dim')
                            logger.info(f"Detected Milvus collection dimension: {current_dimension}")
                            break
                client.close()
            except Exception as e:
                logger.warning(f"Failed to check Milvus dimension: {e}")
        
        elif 'Qdrant' in vector_storage:
            # Check Qdrant collection config
            try:
                from qdrant_client import QdrantClient
                qdrant_url = config_manager.get_value('QDRANT_URL') or 'http://localhost:6333'
                
                client = QdrantClient(url=qdrant_url)
                
                # Check chunks collection
                collection_name = f"{workspace_name}_chunks"
                try:
                    collection_info = client.get_collection(collection_name)
                    current_dimension = collection_info.config.params.vectors.size
                    logger.info(f"Detected Qdrant collection dimension: {current_dimension}")
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Failed to check Qdrant dimension: {e}")
        
        elif 'Chroma' in vector_storage:
            # Check ChromaDB collection
            try:
                import chromadb
                chroma_path = config_manager.get_value('CHROMA_PATH') or os.path.join(working_dir, 'chroma')
                
                if os.path.exists(chroma_path):
                    client = chromadb.PersistentClient(path=chroma_path)
                    
                    # Check chunks collection
                    collection_name = f"{workspace_name}_chunks"
                    try:
                        collection = client.get_collection(collection_name)
                        # ChromaDB doesn't store dimension explicitly, try to get from metadata
                        metadata = collection.metadata
                        if metadata and 'dimension' in metadata:
                            current_dimension = int(metadata['dimension'])
                            logger.info(f"Detected ChromaDB collection dimension: {current_dimension}")
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Failed to check ChromaDB dimension: {e}")
        
        else:
            logger.warning(f"Unsupported vector storage type for dimension check: {vector_storage}")
        
        # Get available workspaces by scanning base_working_dir subdirectories
        workspaces = []
        try:
            if os.path.exists(base_working_dir):
                for item in os.listdir(base_working_dir):
                    item_path = os.path.join(base_working_dir, item)
                    if os.path.isdir(item_path):
                        # Check if it has typical workspace structure (has index files or is a valid directory)
                        workspaces.append({
                            'name': item,
                            'is_valid': True
                        })
                logger.info(f"Found {len(workspaces)} workspaces in {base_working_dir}")
        except Exception as e:
            logger.warning(f"Failed to scan workspaces: {e}")
        
        # Log detection result
        logger.info(f"Dimension check result: current={current_dimension}, new={new_dimension}, storage={vector_storage}, working_dir={working_dir}")
        
        # Check for conflict
        has_conflict = False
        if current_dimension is not None and current_dimension != new_dimension:
            has_conflict = True
            logger.warning(f"⚠️  Embedding dimension conflict detected: current={current_dimension}, new={new_dimension}, storage={vector_storage}")
        elif current_dimension is None:
            logger.info(f"No existing vector index found, no conflict (new dimension: {new_dimension})")
        else:
            logger.info(f"Dimensions match: {current_dimension} == {new_dimension}, no conflict")
        
        return create_success_response(request, {
            'hasConflict': has_conflict,
            'currentDimension': current_dimension,
            'newDimension': new_dimension,
            'vectorStorage': vector_storage,
            'workspaceName': workspace_name,
            'workspaces': workspaces
        })
        
    except Exception as e:
        logger.error(f"Error checking embedding dimension: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'DIMENSION_CHECK_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.downloadFile')
def handle_download_file(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Download a file from LightRAG server and save to Downloads folder.
    
    Expected params:
        fileName: str - The file name to download
    """
    try:
        is_valid, data, error = validate_params(params, ['fileName'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        file_name = data['fileName']
        
        # Get LightRAG server base URL
        client = get_client()
        base_url = client.base_url
        
        # Construct download URL
        import urllib.parse
        download_url = f"{base_url}/documents/download/{urllib.parse.quote(file_name)}"
        
        logger.info(f"Downloading file from: {download_url}")
        
        # Download file
        import requests
        response = requests.get(download_url, timeout=60)
        if response.status_code != 200:
            return create_error_response(request, 'DOWNLOAD_ERROR', f'下载失败: {response.status_code}')
        
        # Get Downloads folder
        downloads_dir = os.path.expanduser('~/Downloads')
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir, exist_ok=True)
        
        # Handle duplicate filenames
        dest_file = os.path.join(downloads_dir, file_name)
        if os.path.exists(dest_file):
            base_name = os.path.splitext(file_name)[0]
            extension = os.path.splitext(file_name)[1]
            counter = 1
            while os.path.exists(dest_file):
                dest_file = os.path.join(downloads_dir, f"{base_name}_{counter}{extension}")
                counter += 1
        
        # Write file
        with open(dest_file, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"File saved to: {dest_file}")
        
        return create_success_response(request, {
            'success': True,
            'filePath': dest_file,
            'fileName': os.path.basename(dest_file)
        })
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'DOWNLOAD_ERROR', str(e))


