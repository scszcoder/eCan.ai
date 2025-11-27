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
            error_msg = result.get('message', 'Failed to ingest files')
            logger.error(f"Ingest files failed: {error_msg}")
            return create_error_response(request, 'INGEST_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
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
            error_msg = result.get('message', 'Failed to ingest directory')
            logger.error(f"Ingest directory failed: {error_msg}")
            return create_error_response(request, 'INGEST_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in ingest_directory handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'INGEST_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.query')
async def handle_query(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle knowledge query request (async to avoid blocking UI).
    
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
        
        import asyncio
        client = get_client()
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.query(text, options)
        )
        
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
    """
    try:
        import shutil
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
            
            return create_success_response(request, {
                'status': 'success',
                'message': f'Successfully cleared cache and deleted {len(deleted_items)} items',
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


@IPCHandlerRegistry.background_handler('lightrag.updateEntity')
async def handle_update_entity(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle entity update request (async to avoid blocking UI)."""
    try:
        is_valid, data, error = validate_params(params, ['entity_name', 'updated_data'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        import asyncio
        client = get_client()
        # Run the blocking HTTP call in a thread pool to avoid blocking the event loop
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.update_entity(
                data['entity_name'],
                data['updated_data'],
                data.get('allow_rename', False),
                data.get('allow_merge', False)
            )
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'UPDATE_ENTITY_ERROR', result.get('message', 'Failed to update entity'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in update_entity handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_ENTITY_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.checkEntityNameExists')
async def handle_check_entity_name_exists(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle check entity name exists request (async to avoid blocking UI)."""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        import asyncio
        client = get_client()
        # Run the blocking HTTP call in a thread pool
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.check_entity_name_exists(data['name'])
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'CHECK_ENTITY_ERROR', result.get('message', 'Failed to check entity'))
            
        return create_success_response(request, result.get('data', result))
    except Exception as e:
        logger.error(f"Error in check_entity_name_exists handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'CHECK_ENTITY_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.updateRelation')
async def handle_update_relation(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle relation update request (async to avoid blocking UI)."""
    try:
        is_valid, data, error = validate_params(params, ['source_id', 'target_id', 'updated_data'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        import asyncio
        client = get_client()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.update_relation(data['source_id'], data['target_id'], data['updated_data'])
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'UPDATE_RELATION_ERROR', result.get('message', 'Failed to update relation'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in update_relation handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'UPDATE_RELATION_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getGraphLabelList')
async def handle_get_graph_label_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get graph label list request (async to avoid blocking UI)."""
    try:
        import asyncio
        client = get_client()
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.get_graph_label_list()
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_LABEL_LIST_ERROR', result.get('message', 'Failed to get label list'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in get_graph_label_list handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_LABEL_LIST_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getPopularLabels')
async def handle_get_popular_labels(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get popular labels request (async to avoid blocking UI)."""
    try:
        params = params or {}
        limit = params.get('limit', 300)
        
        client = get_client()
        # Check if client has the method (for backward compatibility)
        if not hasattr(client, 'get_popular_labels'):
             return create_error_response(request, 'NOT_IMPLEMENTED', 'get_popular_labels not implemented in client')

        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.get_popular_labels(limit=limit)
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_POPULAR_LABELS_ERROR', result.get('message', 'Failed to get popular labels'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in get_popular_labels handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'GET_POPULAR_LABELS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.searchLabels')
async def handle_search_labels(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle search labels request (async to avoid blocking UI)."""
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

        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.search_labels(q=query, limit=limit)
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'SEARCH_LABELS_ERROR', result.get('message', 'Failed to search labels'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
    except Exception as e:
        logger.error(f"Error in search_labels handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SEARCH_LABELS_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.getDocumentsPaginated')
async def handle_get_documents_paginated(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle paginated documents request (async to avoid blocking UI)."""
    try:
        # Default params
        defaults = {
            'page': 1,
            'page_size': 20,
            'sort_field': 'created_at',
            'sort_direction': 'desc'
        }
        request_params = {**defaults, **(params or {})}
        
        import asyncio
        client = get_client()
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.get_documents_paginated(request_params)
        )
        
        if result.get('status') == 'error':
            return create_error_response(request, 'GET_DOCUMENTS_ERROR', result.get('message', 'Failed to get documents'))
            
        response_data = result.get('data', result)
        return create_success_response(request, response_data)
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
        
        # Filter out system-managed keys to avoid saving them to local env file
        # This ensures the file remains clean and system settings remain authoritative
        keys_to_exclude = ['_SYSTEM_LLM_KEY_SOURCE', '_SYSTEM_EMBED_KEY_SOURCE']
        
        # Also exclude the actual API key fields if they are system managed
        # The frontend sends back the system key value (masked or raw), but we must NOT save it
        if params.get('_SYSTEM_LLM_KEY_SOURCE'):
            keys_to_exclude.extend(['LLM_BINDING_API_KEY', 'OPENAI_API_KEY'])
            
        if params.get('_SYSTEM_EMBED_KEY_SOURCE'):
            keys_to_exclude.append('EMBEDDING_BINDING_API_KEY')
        
        settings_to_save = {k: v for k, v in params.items() if k not in keys_to_exclude}
        
        config_manager = get_config_manager()
        success = config_manager.update_config(settings_to_save)
        
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
        from app_context import AppContext
        
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
        
        # Restart the server asynchronously
        import asyncio
        from knowledge.lightrag_server import LightragServer
        
        async def restart_server():
            try:
                # Create and start new server instance
                # Paths are automatically handled by LightragServer using app_info defaults
                # API Keys are automatically handled by LightragServer using config_manager
                main_window.lightrag_server = LightragServer()
                success = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: main_window.lightrag_server.start(wait_ready=True)
                )
                
                if success:
                    logger.info("[LightRAG] Server restarted successfully")
                else:
                    logger.error("[LightRAG] Server restart failed - check logs for details")
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
async def handle_query_graphs(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Handle graph query request (async to avoid blocking UI).
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
        
        import asyncio
        client = get_client()
        # Call query_graphs method (assumed to be added to client)
        if hasattr(client, 'query_graphs'):
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.query_graphs(label, max_depth, max_nodes)
            )
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


@IPCHandlerRegistry.handler('lightrag.getSystemProviders')
def handle_get_system_providers(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get system LLM, Embedding and Rerank providers for LightRAG configuration."""
    try:
        from gui.config.llm_config import llm_config
        from gui.config.embedding_config import embedding_config
        from gui.config.rerank_config import RerankConfig
        from app_context import AppContext
        
        # Get manager instances to retrieve API keys
        main_window = AppContext.get_main_window()
        llm_manager = main_window.config_manager.llm_manager if main_window else None
        embedding_manager = main_window.config_manager.embedding_manager if main_window else None
        rerank_manager = main_window.config_manager.rerank_manager if main_window else None
        
        # Create fresh RerankConfig instance to ensure latest JSON is loaded
        rerank_conf_instance = RerankConfig()
        
        system_llm_providers = llm_config.get_all_providers()
        system_embed_providers = embedding_config.get_all_providers()
        system_rerank_providers = rerank_conf_instance.get_all_providers()
        
        llm_providers_ui = []
        for key, p in system_llm_providers.items():
            # Check if provider has models list
            model_field = {'key': 'LLM_MODEL', 'label': 'fields.model', 'type': 'text', 'required': True, 'defaultValue': p.default_model or ''}
            if hasattr(p, 'supported_models') and p.supported_models:
                model_field['type'] = 'select'
                model_field['options'] = [{'value': m.model_id, 'label': m.display_name or m.name} for m in p.supported_models]
            
            fields = [model_field]
            
            if p.base_url or p.is_local:
                fields.append({'key': 'LLM_BINDING_HOST', 'label': 'fields.apiHost', 'type': 'text', 'defaultValue': p.base_url or '', 'disabled': True})
            
            # Always check for API keys
            if p.api_key_env_vars:
                field_def = {'key': 'LLM_BINDING_API_KEY', 'label': 'fields.apiKey', 'type': 'password', 'required': True}
                
                # Try to retrieve API key using manager
                if llm_manager:
                    try:
                        # Check if any of the env vars has a configured key
                        api_key = None
                        for env_var in p.api_key_env_vars:
                            key_val = llm_manager.retrieve_api_key(env_var)
                            if key_val:
                                api_key = key_val
                                break
                        
                        if api_key:
                            field_def['isSystemManaged'] = True
                            # Return full API key - frontend Input.Password will handle visibility
                            field_def['defaultValue'] = api_key
                    except Exception as e:
                        logger.warning(f"Failed to retrieve API key for {p.provider.value}: {e}")
                
                fields.append(field_def)
            
            llm_providers_ui.append({
                'id': p.provider.value,
                'name': p.display_name,
                'description': p.description,
                'fields': fields
            })
            
        embedding_providers_ui = []
        for key, p in system_embed_providers.items():
             # Check if provider has models list
             model_field = {'key': 'EMBEDDING_MODEL', 'label': 'fields.model', 'type': 'text', 'required': True, 'defaultValue': p.default_model or ''}
             model_metadata = {}
             
             if hasattr(p, 'supported_models') and p.supported_models:
                 model_field['type'] = 'select'
                 model_field['options'] = [{'value': m.model_id, 'label': m.display_name or m.name} for m in p.supported_models]
                 # Build metadata map
                 for m in p.supported_models:
                     model_metadata[m.model_id] = {
                         'dimensions': m.dimensions,
                         'max_tokens': getattr(m, 'max_tokens', None) # max_tokens might not be in EmbeddingModelConfig
                     }

             fields = [model_field]
             fields.append({'key': 'EMBEDDING_DIM', 'label': 'fields.dimensions', 'type': 'number', 'placeholder': '1024', 'disabled': True})
             fields.append({'key': 'EMBEDDING_TOKEN_LIMIT', 'label': 'fields.tokenLimit', 'type': 'number', 'placeholder': '8192', 'disabled': True})

             if p.base_url or p.is_local:
                fields.append({'key': 'EMBEDDING_BINDING_HOST', 'label': 'fields.apiHost', 'type': 'text', 'defaultValue': p.base_url or '', 'disabled': True})
            
             if p.api_key_env_vars:
                 field_def = {'key': 'EMBEDDING_BINDING_API_KEY', 'label': 'fields.apiKey', 'type': 'password', 'required': True}
                 
                 # Try to retrieve API key using manager
                 if embedding_manager:
                     try:
                         # Check if any of the env vars has a configured key
                         api_key = None
                         for env_var in p.api_key_env_vars:
                             key_val = embedding_manager.retrieve_api_key(env_var)
                             if key_val:
                                 api_key = key_val
                                 break
                         
                         if api_key:
                            field_def['isSystemManaged'] = True
                            # Return full API key - frontend Input.Password will handle visibility
                            field_def['defaultValue'] = api_key
                     except Exception as e:
                         logger.warning(f"Failed to retrieve API key for {p.provider.value}: {e}")
                 
                 fields.append(field_def)

             embedding_providers_ui.append({
                'id': p.provider.value,
                'name': p.display_name,
                'description': p.description,
                'fields': fields,
                'modelMetadata': model_metadata
            })

        # Build Rerank providers UI
        rerank_providers_ui = []
        if not rerank_manager:
            logger.warning("[SystemProviders] Rerank manager is not available!")

        for key, p in system_rerank_providers.items():
            # Check if provider has models list
            model_field = {'key': 'RERANK_MODEL', 'label': 'fields.model', 'type': 'text', 'required': True, 'defaultValue': p.default_model or ''}

            if hasattr(p, 'supported_models') and p.supported_models:
                model_field['type'] = 'select'
                model_field['options'] = [{'value': m.model_id, 'label': m.display_name or m.name} for m in p.supported_models]
            
            fields = [model_field]
            
            if p.base_url or p.is_local:
                fields.append({'key': 'RERANK_BINDING_HOST', 'label': 'fields.apiHost', 'type': 'text', 'defaultValue': p.base_url or '', 'disabled': True})
            
            # Always check for API keys
            if p.api_key_env_vars:
                field_def = {'key': 'RERANK_BINDING_API_KEY', 'label': 'fields.apiKey', 'type': 'password', 'required': True}
                
                # Try to retrieve API key using manager
                if rerank_manager:
                    try:
                        # Check if any of the env vars has a configured key
                        api_key = None
                        for env_var in p.api_key_env_vars:
                            key_val = rerank_manager.retrieve_api_key(env_var)
                            if key_val:
                                api_key = key_val
                                break
                        
                        if api_key:
                            field_def['isSystemManaged'] = True
                            # Return full API key - frontend Input.Password will handle visibility
                            field_def['defaultValue'] = api_key
                    except Exception as e:
                        logger.warning(f"Failed to retrieve API key for {p.provider.value}: {e}")
                
                fields.append(field_def)

            rerank_providers_ui.append({
                'id': p.provider.value,
                'name': p.display_name,
                'description': p.description,
                'fields': fields
            })

        return create_success_response(request, {
            'llm_providers': llm_providers_ui,
            'embedding_providers': embedding_providers_ui,
            'rerank_providers': rerank_providers_ui
        })
    except Exception as e:
        logger.error(f"Error getting system providers: {e}")
        return create_error_response(request, 'GET_PROVIDERS_ERROR', str(e))


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
