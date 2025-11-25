"""
LightRAG IPC Handler
Handles knowledge base operations for the LightRAG system.
"""
import os
import traceback
from typing import Any, Optional, Dict, List
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from knowledge.lightrag_client import get_client
from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler('lightrag.ingestFiles')
def handle_ingest_files(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle file ingestion request.
    
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
            return create_error_response(request, 'INGEST_ERROR', result.get('message', 'Failed to ingest files'))
        
        return create_success_response(request, result)
        
    except Exception as e:
        logger.error(f"Error in ingest_files handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INGEST_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.ingestDirectory')
def handle_ingest_directory(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle directory ingestion request.
    
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
            return create_error_response(request, 'INGEST_ERROR', result.get('message', 'Failed to ingest directory'))
        
        return create_success_response(request, result)
        
    except Exception as e:
        logger.error(f"Error in ingest_directory handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INGEST_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.query')
def handle_query(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle knowledge query request.
    
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
        
        # Get LightRAG client
        client = get_client()
        
        # Call query method
        result = client.query(text, options)
        
        if result.get('status') == 'error':
            return create_error_response(request, 'QUERY_ERROR', result.get('message', 'Query failed'))
        
        return create_success_response(request, result)
        
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
            return create_error_response(request, 'STATUS_ERROR', result.get('message', 'Failed to get status'))
        
        return create_success_response(request, result)
        
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
            return create_error_response(request, 'SCAN_ERROR', result.get('message', 'Failed to start scan'))
        
        return create_success_response(request, result)
        
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
            return create_error_response(request, 'LIST_ERROR', result.get('message', 'Failed to list documents'))
        
        return create_success_response(request, result)
        
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
            return create_error_response(request, 'DELETE_ERROR', result.get('message', 'Failed to delete document'))
        
        return create_success_response(request, result)
        
    except Exception as e:
        logger.error(f"Error in delete_document handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'DELETE_ERROR', str(e))


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
            return create_error_response(request, 'INSERT_ERROR', result.get('message', 'Failed to insert text'))
        
        return create_success_response(request, result)
        
    except Exception as e:
        logger.error(f"Error in insert_text handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INSERT_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.queryStream')
def handle_query_stream(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle streaming query request.
    Streams data back to frontend via response chunks.
    """
    try:
        if not params:
            return create_error_response(request, 'MISSING_PARAMS', 'Missing query parameters')
        
        text = params.get('text')
        if not text:
            return create_error_response(request, 'MISSING_TEXT', 'Missing query text')
        
        options = params.get('options', {})
        
        # Get LightRAG client
        client = get_client()
        
        # Start streaming - send initial response
        initial_response = create_success_response(request, {'status': 'streaming', 'started': True})
        
        # Stream chunks back to frontend
        # Note: This requires IPC framework to support streaming/chunked responses
        # For now, we'll collect all chunks and send as complete response
        chunks = []
        try:
            for chunk in client.query_stream(text, options):
                chunks.append(chunk)
        except Exception as stream_error:
            logger.error(f"Error during streaming: {stream_error}")
            return create_error_response(request, 'STREAM_ERROR', str(stream_error))
        
        # Send complete response with all chunks
        full_response = ''.join(chunks)
        return create_success_response(request, {
            'response': full_response,
            'chunks': chunks,
            'streaming': True
        })
        
    except Exception as e:
        logger.error(f"Error in query_stream handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'QUERY_STREAM_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.clearCache')
def handle_clear_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle clear cache request.
    """
    try:
        # Get LightRAG client
        client = get_client()
        
        # Call clear_cache method
        result = client.clear_cache()
        
        if result.get('status') == 'error':
            return create_error_response(request, 'CLEAR_CACHE_ERROR', result.get('message', 'Clear cache failed'))
        
        return create_success_response(request, result)
        
    except Exception as e:
        logger.error(f"Error in clear_cache handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'CLEAR_CACHE_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getStatusCounts')
def handle_get_status_counts(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle get status counts request.
    """
    try:
        # Get LightRAG client
        client = get_client()
        
        # Call get_status_counts method
        result = client.get_status_counts()
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_STATUS_COUNTS_ERROR', result.get('message', 'Get status counts failed'))
        
        return create_success_response(request, result)
        
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
    try:
        from PySide6.QtWidgets import QFileDialog, QApplication
        
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
        
        # Show dialog
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        if multiple:
            file_paths, _ = QFileDialog.getOpenFileNames(
                None,
                "Select Files",
                os.path.expanduser("~"),
                filter_str
            )
            if file_paths:
                return create_success_response(request, {'paths': file_paths})
            else:
                return create_success_response(request, {'paths': [], 'cancelled': True})
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                None,
                "Select File",
                os.path.expanduser("~"),
                filter_str
            )
            if file_path:
                return create_success_response(request, {'path': file_path})
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
    try:
        from PySide6.QtWidgets import QFileDialog, QApplication
        
        # Show dialog
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        dir_path = QFileDialog.getExistingDirectory(
            None,
            "Select Directory",
            os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if dir_path:
            return create_success_response(request, {'path': dir_path})
        else:
            return create_success_response(request, {'path': '', 'cancelled': True})
        
    except Exception as e:
        logger.error(f"Error in select_directory handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SELECT_DIRECTORY_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.updateEntity')
def handle_update_entity(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle entity update request."""
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
            
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in update_entity handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_ENTITY_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.updateRelation')
def handle_update_relation(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle relation update request."""
    try:
        is_valid, data, error = validate_params(params, ['source_id', 'target_id', 'updated_data'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
            
        client = get_client()
        result = client.update_relation(
            data['source_id'],
            data['target_id'],
            data['updated_data']
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'UPDATE_RELATION_ERROR', result.get('message', 'Failed to update relation'))
            
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in update_relation handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_RELATION_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getGraphLabelList')
def handle_get_graph_label_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get graph label list request."""
    try:
        client = get_client()
        result = client.get_graph_label_list()
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_LABEL_LIST_ERROR', result.get('message', 'Failed to get label list'))
            
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get_graph_label_list handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_LABEL_LIST_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getDocumentsPaginated')
def handle_get_documents_paginated(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle paginated documents request."""
    try:
        # Default params
        defaults = {
            'page': 1,
            'page_size': 20,
            'sort_field': 'created_at',
            'sort_direction': 'desc'
        }
        request_params = {**defaults, **(params or {})}
        
        client = get_client()
        result = client.get_documents_paginated(request_params)
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_DOCUMENTS_ERROR', result.get('message', 'Failed to get documents'))
            
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in get_documents_paginated handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_DOCUMENTS_ERROR', str(e))


# Settings persistence using config manager
from knowledge.lightrag_config_manager import get_config_manager


@IPCHandlerRegistry.handler('lightrag.saveSettings')
def handle_save_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save LightRAG settings to .env file."""
    try:
        if not params:
            return create_error_response(request, 'INVALID_PARAMS', 'No settings provided')
        
        config_manager = get_config_manager()
        success = config_manager.update_config(params)
        
        if not success:
            return create_error_response(request, 'CONFIG_ERROR', 'Failed to save settings')
        
        return create_success_response(request, {'success': True, 'message': 'Settings saved'})
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return create_error_response(request, 'SAVE_SETTINGS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.restartServer')
def handle_restart_server(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Restart LightRAG server to apply new settings."""
    try:
        from gui.MainGUI import MainWindow
        
        # Get MainWindow instance
        main_window = MainWindow.get_instance()
        if not main_window:
            return create_error_response(request, 'MAIN_WINDOW_NOT_FOUND', 'MainWindow instance not found')
        
        # Check if server exists
        if not hasattr(main_window, 'lightrag_server') or not main_window.lightrag_server:
            return create_error_response(request, 'SERVER_NOT_RUNNING', 'LightRAG server is not running')
        
        # Stop the server
        logger.info("[LightRAG] Stopping server for restart...")
        main_window.stop_lightrag_server()
        
        # Restart the server asynchronously
        import asyncio
        from knowledge.lightrag_server import LightragServer
        from utils.env.secure_store import secure_store
        from config.app_info import app_info
        
        async def restart_server():
            try:
                # Prepare environment variables
                ecb_data_homepath = app_info.appdata_path
                runlogs_dir = os.path.join(app_info.appdata_path, "runlogs")
                lightrag_env = {
                    "APP_DATA_PATH": ecb_data_homepath + "/lightrag_data",
                    "LOG_DIR": runlogs_dir,
                }
                
                # Add OpenAI API key if available
                openai_key = secure_store.get_credential("openai_api_key")
                if openai_key:
                    lightrag_env["OPENAI_API_KEY"] = openai_key
                
                # Create and start new server instance
                main_window.lightrag_server = LightragServer(extra_env=lightrag_env)
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: main_window.lightrag_server.start(wait_ready=False)
                )
                logger.info("[LightRAG] Server restarted successfully")
            except Exception as e:
                logger.error(f"[LightRAG] Error restarting server: {e}")
        
        # Schedule restart in the event loop
        asyncio.create_task(restart_server())
        
        return create_success_response(request, {'success': True, 'message': 'Server restart initiated'})
    except Exception as e:
        logger.error(f"Error restarting LightRAG server: {e}")
        return create_error_response(request, 'RESTART_SERVER_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getSettings')
def handle_get_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get LightRAG settings from .env file."""
    try:
        config_manager = get_config_manager()
        settings = config_manager.read_config()
        return create_success_response(request, settings)
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return create_error_response(request, 'GET_SETTINGS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.queryGraphs')
def handle_query_graphs(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle graph query request.
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
            
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in query_graphs handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'QUERY_GRAPH_ERROR', str(e))
