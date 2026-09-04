"""
LightRAG IPC Handler
Handles knowledge base operations for the LightRAG system.
"""
import os
import json
import traceback
import requests
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
        # Optional LightRAG workspace (tenant) for data isolation.
        workspace = (data.get('workspace') or '').strip() or None
        
        if not isinstance(paths, list) or len(paths) == 0:
            return create_error_response(request, 'INVALID_PARAMS', 'paths must be a non-empty list')

        from knowledge.lightrag_config_manager import get_config_manager
        from knowledge.lightrag_parser_config import unsupported_parser_files
        unsupported = unsupported_parser_files(
            get_config_manager().get_effective_config(), paths
        )
        if unsupported:
            names = ', '.join(os.path.basename(path) for path in unsupported[:5])
            if len(unsupported) > 5:
                names += f' 等 {len(unsupported)} 个文件'
            return create_error_response(
                request,
                'UNSUPPORTED_PARSER_FORMAT',
                f'MinerU 3.4.4 不支持这些文件：{names}。支持 PDF、DOCX、PPTX、'
                'XLSX，以及 PNG、JPEG、JP2、WebP、GIF、BMP、TIFF（仅 .tiff）。'
                '请选择 Docling 或 Native 解析引擎后再上传。',
                {'engine': 'mineru', 'files': unsupported},
            )
        
        # Get LightRAG client
        client = get_client()
        
        # Call ingest_files method
        result = client.ingest_files(paths, options, workspace=workspace)
        
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
        # Optional LightRAG workspace (tenant) for data isolation.
        workspace = (data.get('workspace') or '').strip() or None
        
        if not isinstance(dir_path, str) or not dir_path.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'dirPath must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call ingest_directory method. ingest_directory internally calls
        # ingest_files, which now accepts `workspace`; stash it into options so
        # the lower-level client can pick it up without changing its signature.
        if workspace:
            options = dict(options or {})
            options.setdefault('workspace', workspace)
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
        # Optional LightRAG workspace (tenant) for data isolation. Either
        # passed at the top level of params, or carried inside options.
        workspace = (data.get('workspace') or (options.get('workspace') if isinstance(options, dict) else None) or '').strip() or None
        
        if not isinstance(text, str) or not text.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'text must be a non-empty string')
        
        client = get_client()
        result = client.query(text, options, workspace=workspace)
        
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
        # Optional LightRAG workspace (tenant) for data isolation. Track
        # IDs are workspace-scoped on the server, so callers should pass
        # the same workspace they used during ingestion.
        workspace = (data.get('workspace') or '').strip() or None
        
        if not isinstance(job_id, str) or not job_id.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'jobId must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call status method (uses track_status internally)
        result = client.track_status(job_id, workspace=workspace)
        
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
    
    Optional params:
    - workspace: str - LightRAG workspace (tenant) name. Newly discovered
      documents are ingested into the targeted workspace.
    """
    try:
        # Optional LightRAG workspace (tenant).
        workspace = ((params or {}).get('workspace') or '').strip() or None
        # Get LightRAG client
        client = get_client()
        
        # Call scan method
        result = client.scan(workspace=workspace)
        
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
    
    Optional params:
    - workspace: str - LightRAG workspace (tenant) name to list documents
      from. Omit for the server's default workspace.
    """
    try:
        # Optional LightRAG workspace (tenant).
        workspace = ((params or {}).get('workspace') or '').strip() or None
        # Get LightRAG client
        client = get_client()
        
        # Call list_documents method
        result = client.list_documents(workspace=workspace)
        
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
        # Optional LightRAG workspace (tenant). Deletion is scoped to the
        # workspace the document was ingested into.
        workspace = (data.get('workspace') or '').strip() or None
        
        if not isinstance(doc_id, str) or not doc_id.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'id must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call delete_document method
        result = client.delete_document(doc_id, workspace=workspace)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to delete document')
            logger.error(f"Delete document failed: {error_msg}")
            return create_error_response(request, 'DELETE_ERROR', error_msg)
        
        data = result.get('data', result)
        return create_success_response(request, data)
        
    except Exception as e:
        logger.error(f"Error in delete_document handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'DELETE_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.replaceDocument')
def handle_replace_document(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Re-ingest a file in place: delete any existing copies in the
    workspace (matched by basename) and upload the new version.

    Runs in a background thread because it does a list-then-delete-then-
    upload chain whose total time is dominated by the upload step. The
    LightragClient.replace_document docstring covers the semantics.

    Expected params:
    - path: str — absolute local path to the *new* version of the file.
    - workspace: Optional[str] — LightRAG workspace (tenant). Empty means server default.
    - matchBasename: Optional[bool] — default True. Set False to require
      an exact file_path match instead of a basename match.
    """
    try:
        is_valid, data, error = validate_params(params, ['path'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        path = data['path']
        workspace = (data.get('workspace') or '').strip() or None
        match_basename = bool(data.get('matchBasename', True))

        if not isinstance(path, str) or not path.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'path must be a non-empty string')

        client = get_client()
        result = client.replace_document(path, workspace=workspace, match_basename=match_basename)

        if result.get('status') == 'error':
            error_msg = result.get('message', 'Failed to replace document')
            logger.error(f"Replace document failed: {error_msg}")
            return create_error_response(request, 'REPLACE_ERROR', error_msg)

        return create_success_response(request, result.get('data', result))
    except Exception as e:
        logger.error(f"Error in replace_document handler: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'REPLACE_ERROR', str(e))


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
        # Optional LightRAG workspace (tenant). Pipeline cancellation is
        # scoped to the targeted workspace.
        workspace = (data.get('workspace') or '').strip() or None
        
        if not isinstance(doc_id, str) or not doc_id.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'id must be a non-empty string')
        
        logger.info(f"[lightrag_handler] Aborting document immediately: {doc_id} (workspace={workspace!r})")
        
        # Get LightRAG client
        client = get_client()
        
        # Call abort_document method (which calls cancel_pipeline - now with immediate task cancellation)
        result = client.abort_document(doc_id, workspace=workspace)
        
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
        # Optional LightRAG workspace (tenant) for data isolation.
        workspace = (data.get('workspace') or '').strip() or None
        
        if not isinstance(text, str) or not text.strip():
            return create_error_response(request, 'INVALID_PARAMS', 'text must be a non-empty string')
        
        # Get LightRAG client
        client = get_client()
        
        # Call insert_text method
        result = client.insert_text(text, metadata, workspace=workspace)
        
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
        # Optional LightRAG workspace (tenant) for data isolation. Accept
        # either a top-level `workspace` param or one embedded in options.
        _ws_raw = params.get('workspace')
        if not _ws_raw and isinstance(options, dict):
            _ws_raw = options.get('workspace')
        workspace = (_ws_raw or '').strip() or None
        
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
                
                for chunk_str in client.query_stream(text, options, workspace=workspace):
                    try:
                        # Parse JSON chunk
                        chunk_data = json.loads(chunk_str)

                        if chunk_data.get('error'):
                            raise RuntimeError(str(chunk_data['error']))
                        
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
        
        # Optional LightRAG workspace (tenant) for the API-side cache clear.
        # The on-disk cleanup below targets the global WORKING_DIR; mixing
        # workspace-scoped cache clears with full disk wipe is intentional
        # because the latter is the user-visible behavior the UI expects.
        workspace = ((params or {}).get('workspace') or '').strip() or None
        # Get LightRAG client
        client = get_client()
        
        # Step 1: Call clear_cache API to clear LLM cache
        result = client.clear_cache(workspace=workspace)
        
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
    
    Optional params:
    - workspace: str - LightRAG workspace (tenant) name. Counts are scoped
      to the targeted workspace.
    """
    try:
        # Optional LightRAG workspace (tenant).
        workspace = ((params or {}).get('workspace') or '').strip() or None
        # Get LightRAG client
        client = get_client()
        
        # Call get_status_counts method
        result = client.get_status_counts(workspace=workspace)

        if result.get('status') == 'error':
            error_msg = result.get('message', 'Get status counts failed')
            logger.error(f"Get status counts failed: {error_msg}")
            return create_error_response(request, 'GET_STATUS_COUNTS_ERROR', error_msg)

        data = result.get('data', result)
        return create_success_response(request, data)

    except requests.exceptions.ConnectionError:
        # LightRAG server not yet started — return empty data instead of error.
        logger.debug(f"[lightrag_handler] Server not ready for get_status_counts, returning empty data")
        return create_success_response(request, {'status_counts': {}})

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
        # Optional LightRAG workspace (tenant). Strip from the body params
        # before forwarding to the LightRAG /documents/paginated endpoint
        # (it is sent as a header instead).
        workspace = (request_params.pop('workspace', None) or '').strip() or None
        
        logger.info(f"[lightrag_handler] get_documents_paginated called with params: {request_params} (workspace={workspace!r})")
        
        client = get_client()
        
        # Call synchronously (this runs in a background thread via registry)
        result = client.get_documents_paginated(request_params, workspace=workspace)
        
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

    except requests.exceptions.ConnectionError:
        # LightRAG server not yet started — return empty data instead of error.
        logger.debug(f"[lightrag_handler] Server not ready for get_documents_paginated, returning empty data")
        return create_success_response(request, {'documents': [], 'total': 0, 'page': 1, 'page_size': 20})

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
        # Optional LightRAG workspace (tenant). Track IDs are workspace-
        # scoped on the server, and progress polling is the same.
        workspace = ((params or {}).get('workspace') or '').strip() or None
        
        # Get LightRAG client
        client = get_client()
        
        if track_id:
            # Get detailed progress for specific track_id
            result = client.track_status(track_id, workspace=workspace)
            
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
            result = client.get_status_counts(workspace=workspace)
            
            if result.get('status') == 'error':
                error_msg = result.get('message', 'Failed to get status counts')
                if 'connection refused' in error_msg.lower() or 'failed to establish a new connection' in error_msg.lower():
                    logger.debug("[lightrag_handler] LightRAG is not ready; returning idle progress")
                    return create_success_response(request, {
                        'status': 'idle',
                        'processing_count': 0,
                        'pending_count': 0,
                        'processed_count': 0,
                        'failed_count': 0,
                        'total_count': 0,
                        'progress_percentage': 0,
                        'server_ready': False,
                    })
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
            pipeline_busy = bool(pipeline_data.get('busy'))
            
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
                
                if pipeline_busy or processing > 0 or pending > 0:
                    status = 'processing'
                else:
                    status = 'completed'
            else:
                progress_percentage = 0
                # Parsing/analyzing can make the pipeline busy before the
                # document appears in the PROCESSING status count.
                status = 'processing' if pipeline_busy else 'idle'
            
            response_data = {
                'status': status,
                'processing_count': processing,
                'pending_count': pending,
                'processed_count': processed,
                'failed_count': failed,
                'total_count': total,
                'progress_percentage': progress_percentage,
                'pipeline_busy': pipeline_busy,
            }
            
            # Include pipeline details if available
            # Show pipeline info when busy OR when there are processing/pending documents
            if pipeline_data.get('busy') or processing > 0 or pending > 0:
                logger.info(f"[lightrag_handler] Including pipeline data: busy={pipeline_data.get('busy')}, processing={processing}, pending={pending}")
                
                # Chunk-level progress fields. LightRAG ≥ 1.5 no longer exposes
                # them through /documents/pipeline_status (only batch-level via
                # ``cur_batch`` / ``batchs``). We keep the keys in the GUI
                # response as None so older GUI builds that read them do not
                # crash; they will simply show no chunk progress.
                total_chunks = pipeline_data.get('total_chunks', 0)
                processed_chunks = pipeline_data.get('processed_chunks', 0)
                current_chunk_file = pipeline_data.get('current_chunk_file', None)

                pipeline_info = {
                    'busy': pipeline_busy,
                    'job_name': pipeline_data.get('job_name'),
                    'current_batch': pipeline_data.get('cur_batch', 0),
                    'total_batches': pipeline_data.get('batchs', 0),
                    'latest_message': pipeline_data.get('latest_message'),
                    'total_chunks': total_chunks if total_chunks > 0 else None,
                    'processed_chunks': processed_chunks if total_chunks > 0 else None,
                    'current_chunk_file': current_chunk_file,  # File path of current processing document (1.5: always None)
                }
                
                logger.info(f"[lightrag_handler] Pipeline info: {pipeline_info}")
                response_data['pipeline'] = pipeline_info
            
            return create_success_response(request, response_data)

    except requests.exceptions.ConnectionError:
        # LightRAG server not yet started — return idle progress instead of error.
        logger.debug(f"[lightrag_handler] Server not ready for get_processing_progress, returning idle data")
        return create_success_response(request, {
            'status': 'idle',
            'processing_count': 0,
            'pending_count': 0,
            'processed_count': 0,
            'failed_count': 0,
            'total_count': 0,
            'progress_percentage': 0
        })

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
        
        # Filter out system-managed keys and the UI-only parsing engine
        # selection to avoid saving them to the local env file. The engine
        # selection is derived from LIGHTRAG_PARSER and never persisted;
        # PARSING_ENGINE is only kept for backward compatibility with older
        # frontends that still send it.
        keys_to_exclude = [
            '_SYSTEM_LLM_KEY_SOURCE', '_SYSTEM_EMBED_KEY_SOURCE',
            '_SYSTEM_RERANK_KEY_SOURCE', 'PARSING_ENGINE',
            'PARSER_IMAGE_ANALYSIS',
            '_RERANK_RUNTIME_HOST', '_RERANK_USES_PROXY',
        ]
        
        # Also exclude the actual API key fields if they are system managed
        # The frontend sends back the system key value (masked or raw), but we must NOT save it
        if params.get('_SYSTEM_LLM_KEY_SOURCE'):
            keys_to_exclude.extend(['LLM_BINDING_API_KEY', 'OPENAI_API_KEY'])
            
        if params.get('_SYSTEM_EMBED_KEY_SOURCE'):
            keys_to_exclude.append('EMBEDDING_BINDING_API_KEY')
        
        if params.get('_SYSTEM_RERANK_KEY_SOURCE'):
            keys_to_exclude.append('RERANK_BINDING_API_KEY')
        
        settings_to_save = {k: v for k, v in params.items() if k not in keys_to_exclude}

        # Resolve the selected protocol into the canonical fields consumed by
        # LightRAG. Local/official values come from their isolated UI slots;
        # eCanAI prefers the user-typed value (MINERU_API_TOKEN /
        # DOCLING_API_KEY / per-mode local key) and only falls back to the
        # account-level ECANAI_LLM_API_KEY when none of those are set.
        from knowledge.lightrag_parser_config import (
            ECANAI_PARSER_BASE_URL,
            derive_docling_provider,
            derive_mineru_provider,
            LIGHTRAG_PARSER_KEY,
            normalize_parser_routing,
            resolve_ecanai_parser_secrets,
        )
        routing = normalize_parser_routing(settings_to_save.get(LIGHTRAG_PARSER_KEY)).lower()
        mineru_in_routing = "mineru" in routing
        docling_in_routing = "docling" in routing

        mineru_ecanai = derive_mineru_provider(settings_to_save) == "ecanai"
        docling_ecanai = derive_docling_provider(settings_to_save) == "ecanai"
        ecanai_api_key = ""
        if (mineru_ecanai and mineru_in_routing) or (docling_ecanai and docling_in_routing):
            # 1. Check whether the user has already typed the eCanAI key
            #    in the dedicated UI field. The save resolver refreshes
            #    this from the account store at write time, so a typed
            #    value here is a user-typed custom key (e.g. for a
            #    self-managed ecanai proxy). ``*_LOCAL_API_KEY`` belongs
            #    to local mode and is the wrong credential here, so it
            #    MUST NOT be treated as satisfying the ecanai requirement.
            user_typed_mineru = (
                mineru_in_routing
                and bool(str(settings_to_save.get("MINERU_API_TOKEN") or "").strip())
            )
            user_typed_docling = (
                docling_in_routing
                and bool(str(settings_to_save.get("DOCLING_API_KEY") or "").strip())
            )
            has_user_key = user_typed_mineru or user_typed_docling

            if not has_user_key:
                # 2. No per-mode key typed; try the account-level secret.
                try:
                    from utils.env.secure_store import secure_store
                    from gui.ipc.context_bridge import get_username
                    username = get_username(request, params)
                    ecanai_api_key = (
                        str(secure_store.get("ECANAI_LLM_API_KEY", username=username) or "").strip()
                        if username else ""
                    )
                except Exception as ecanai_lookup_error:
                    logger.debug(f"[LightRAG] Account API key lookup failed: {ecanai_lookup_error}")

            if not has_user_key and not ecanai_api_key:
                # Only surface the eCanAI key requirement for the engine that
                # is actually in the routing; do not demand docling credentials
                # when the user has switched to mineru/native and left
                # DOCLING_PROVIDER=ecanai from a prior session.
                if mineru_ecanai and mineru_in_routing:
                    provider_label = "MinerU"
                elif docling_ecanai and docling_in_routing:
                    provider_label = "Docling"
                else:
                    # Neither engine in routing — this should not normally be
                    # reachable, but handle gracefully instead of crashing.
                    provider_label = None

                if provider_label:
                    return create_error_response(
                        request,
                        'PARSER_CONFIG_ERROR',
                        f'{provider_label} eCanAI mode requires an API key. '
                        'Type one in the settings UI, or sign in to an account '
                        'that has ECANAI_LLM_API_KEY provisioned.',
                    )

        # Run for every mode: besides eCanAI account values this maps the
        # selected Local/Official per-mode key into LightRAG's active key.
        settings_to_save = resolve_ecanai_parser_secrets(
            settings_to_save, ECANAI_PARSER_BASE_URL, ecanai_api_key
        )

        # eCanAI is a UI-only alias for MinerU local mode. LightRAG's
        # MinerURawClient rejects any ``MINERU_API_MODE`` outside
        # ``{official, local}`` and the eCanAI proxy requires only the
        # account-level LLM API key (``ECANAI_LLM_API_KEY``); the rest of
        # the configuration is fixed (endpoint, model). Translate here so
        # the saved .env is always valid and the runtime never sees
        # ``ecanai`` as a real value.
        from knowledge.lightrag_parser_config import (
            normalize_parser_ecanai_alias,
        )
        settings_to_save = normalize_parser_ecanai_alias(settings_to_save, ECANAI_PARSER_BASE_URL)

        from knowledge.lightrag_parser_config import LIGHTRAG_PARSER_KEY, normalize_parser_routing
        settings_to_save[LIGHTRAG_PARSER_KEY] = normalize_parser_routing(
            settings_to_save.get(LIGHTRAG_PARSER_KEY)
        )
        
        logger.info(f"[LightRAG] Saving {len(settings_to_save)} settings after filtering")

        # Reject saves that would make LightRAG fail its startup validation
        # (a LIGHTRAG_PARSER rule referencing mineru/docling requires the
        # corresponding endpoint to be configured).
        from knowledge.lightrag_parser_config import validate_parser_endpoints
        parser_errors = validate_parser_endpoints(settings_to_save)
        if parser_errors:
            logger.error(f"[LightRAG] Parser config invalid: {parser_errors}")
            return create_error_response(
                request, 'PARSER_CONFIG_ERROR', '; '.join(parser_errors)
            )
        
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
        
        # Always include the configured workspace. It may be new/empty and
        # therefore not have a storage directory yet; omitting it makes the
        # UI selector unable to display the workspace that is actually in
        # use whenever other workspace directories already exist.
        known_workspace_names = {item['name'] for item in workspaces}
        if current_workspace and current_workspace not in known_workspace_names:
            workspaces.append({
                'name': current_workspace,
                'is_valid': os.path.isdir(os.path.join(rag_storage_dir, current_workspace))
            })

        workspaces.sort(key=lambda item: item['name'].lower())
        
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
        from knowledge.lightrag_parser_config import LIGHTRAG_PARSER_KEY, normalize_parser_routing
        settings[LIGHTRAG_PARSER_KEY] = normalize_parser_routing(settings.get(LIGHTRAG_PARSER_KEY))

        # System Settings is the source of truth for shared local providers.
        # Overlay their real addresses so LightRAG never displays/tests a
        # stale copy left in lightrag.env.
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if main_window:
            for kind, prefix in (('llm', 'LLM'), ('embedding', 'EMBEDDING')):
                binding = str(settings.get(f'{prefix}_BINDING') or '').strip()
                manager = getattr(main_window.config_manager, f'{kind}_manager', None)
                provider = manager.get_provider(binding) if manager and binding else None
                real_host = str((provider or {}).get('base_url') or '').strip()
                if provider and provider.get('is_local') and real_host:
                    settings[f'{prefix}_BINDING_HOST'] = real_host

        # Keep the UI-facing provider address separate from LightRAG's
        # effective compatibility-proxy address.
        from knowledge.lightrag_constants import is_native_rerank_provider
        rerank_binding = str(settings.get('RERANK_BINDING') or '').strip().lower()
        if rerank_binding and not is_native_rerank_provider(rerank_binding):
            try:
                manager = main_window.config_manager.rerank_manager if main_window else None
                provider = manager.get_provider(rerank_binding) if manager else None
                real_host = str((provider or {}).get('base_url') or '').strip()
                runtime_host = str(settings.get('RERANK_BINDING_HOST') or '').strip()
                if real_host:
                    settings['RERANK_BINDING_HOST'] = real_host
                if runtime_host:
                    settings['_RERANK_RUNTIME_HOST'] = runtime_host
                    settings['_RERANK_USES_PROXY'] = 'true'
            except Exception as overlay_error:
                logger.warning(f"[GetSettings] Could not overlay real rerank host: {overlay_error}")
        
        # Log specific keys for debugging
        debug_keys = ['TOP_K', 'CHUNK_TOP_K', 'MAX_ENTITY_TOKENS', 'RERANK_BY_DEFAULT']
        debug_subset = {k: settings.get(k) for k in debug_keys}
        logger.info(f"[GetSettings] Returning {len(settings)} keys. Sample: {debug_subset}")
        
        return create_success_response(request, settings)
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return create_error_response(request, 'GET_SETTINGS_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getParserEngines')
def handle_get_parser_engines(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Get document parsing engine definitions and current values for the
    LightRAG settings UI.

    Returns:
        engines: list of parser engine definitions (id, name, description,
                 fields with env var names, defaults, options, tooltips).
                 Fields whose value comes from account state (``ECANAI_LLM_API_KEY``
                 and the eCanAI proxy URL) carry ``isSystemManaged: true`` when
                 the active provider is ``ecanai`` so the UI can render them
                 as read-only.
        current: current values of every parser-related env var.
        engine:  UI engine selection derived from LIGHTRAG_PARSER
                 ('native' | 'mineru' | 'docling') — never persisted.
    """
    try:
        from knowledge.lightrag_parser_config import (
            ECANAI_PARSER_BASE_URL,
            LIGHTRAG_PARSER_KEY,
            PARSER_ENGINE_DEFINITIONS,
            PARSER_SETTINGS_KEYS,
            derive_parsing_engine,
            mark_system_managed_parser_fields,
            normalize_parser_routing,
        )

        config_manager = get_config_manager()
        settings = config_manager.get_effective_config()
        settings[LIGHTRAG_PARSER_KEY] = normalize_parser_routing(settings.get(LIGHTRAG_PARSER_KEY))

        # Backward-compat migration: older .env files store the self-hosted /
        # official API key in the shared ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY``
        # env var. Per-mode keys (``MINERU_LOCAL_API_KEY``,
        # ``MINERU_OFFICIAL_API_KEY``, etc.) were introduced later so a
        # user-typed credential survives mode switches. Mirror the legacy
        # value into the right per-mode var once if it's still empty — this
        # only runs in-memory, the .env file is rewritten on the next save.
        mineru_mode = str(settings.get('MINERU_API_MODE') or '').strip().lower()
        mineru_runtime_endpoint = str(settings.get('MINERU_LOCAL_ENDPOINT') or '').strip()
        if not mineru_mode and mineru_runtime_endpoint:
            mineru_mode = (
                'ecanai'
                if mineru_runtime_endpoint.rstrip('/') == ECANAI_PARSER_BASE_URL.rstrip('/')
                else 'local'
            )
            settings['MINERU_API_MODE'] = mineru_mode
        # Saved eCanAI configuration is translated to LightRAG's local mode.
        # Reconstruct the UI protocol without treating its account key or
        # fixed endpoint as the user's Local configuration.
        if mineru_mode == 'local' and mineru_runtime_endpoint.rstrip('/') == ECANAI_PARSER_BASE_URL.rstrip('/'):
            mineru_mode = 'ecanai'
            settings['MINERU_API_MODE'] = 'ecanai'
        if mineru_mode == 'local':
            if not str(settings.get('MINERU_LOCAL_ENDPOINT_SETTING') or '').strip():
                settings['MINERU_LOCAL_ENDPOINT_SETTING'] = mineru_runtime_endpoint
            if not str(settings.get('MINERU_LOCAL_API_KEY') or '').strip():
                legacy = str(settings.get('MINERU_API_TOKEN') or '').strip()
                if legacy:
                    settings['MINERU_LOCAL_API_KEY'] = legacy
        elif mineru_mode == 'official':
            if not str(settings.get('MINERU_OFFICIAL_API_KEY') or '').strip():
                legacy = str(settings.get('MINERU_API_TOKEN') or '').strip()
                if legacy:
                    settings['MINERU_OFFICIAL_API_KEY'] = legacy

        docling_mode = str(settings.get('DOCLING_PROVIDER') or '').strip().lower()
        legacy_docling_endpoint = str(settings.get('DOCLING_ENDPOINT') or '').strip()
        if not docling_mode and legacy_docling_endpoint:
            docling_mode = (
                'ecanai'
                if legacy_docling_endpoint.rstrip('/') == ECANAI_PARSER_BASE_URL.rstrip('/')
                else 'local'
            )
            settings['DOCLING_PROVIDER'] = docling_mode
        if docling_mode == 'local':
            if not str(settings.get('DOCLING_LOCAL_ENDPOINT') or '').strip():
                settings['DOCLING_LOCAL_ENDPOINT'] = legacy_docling_endpoint
            if not str(settings.get('DOCLING_LOCAL_API_KEY') or '').strip():
                legacy = str(settings.get('DOCLING_API_KEY') or '').strip()
                if legacy:
                    settings['DOCLING_LOCAL_API_KEY'] = legacy
        elif docling_mode == 'official':
            if not str(settings.get('DOCLING_OFFICIAL_ENDPOINT') or '').strip():
                settings['DOCLING_OFFICIAL_ENDPOINT'] = legacy_docling_endpoint
            if not str(settings.get('DOCLING_OFFICIAL_API_KEY') or '').strip():
                legacy = str(settings.get('DOCLING_API_KEY') or '').strip()
                if legacy:
                    settings['DOCLING_OFFICIAL_API_KEY'] = legacy

        current = {key: settings.get(key) for key in PARSER_SETTINGS_KEYS}

        # eCanAI mode: the active key is account-managed and the save path
        # (resolve_ecanai_parser_secrets) refreshes it from secure_store at
        # write time. Read it back from the same source here so the UI field
        # always reflects the live account key — not a stale .env value
        # captured at the previous save (which can also be a Local key that
        # happened to live in the same env var). When no account key is
        # provisioned we explicitly clear the field so the UI surfaces the
        # missing-credential state instead of silently showing the env value.
        ecanai_account_key = _read_ecanai_account_key(request)
        if mineru_mode == 'ecanai':
            current['MINERU_API_TOKEN'] = ecanai_account_key or ''
        if docling_mode == 'ecanai':
            current['DOCLING_API_KEY'] = ecanai_account_key or ''

        return create_success_response(request, {
            'engines': mark_system_managed_parser_fields(PARSER_ENGINE_DEFINITIONS, settings),
            'current': current,
            'engine': derive_parsing_engine(settings),
        })
    except Exception as e:
        logger.error(f"Error getting parser engines: {e}", exc_info=True)
        return create_error_response(request, 'GET_PARSER_ENGINES_ERROR', str(e))


@IPCHandlerRegistry.background_handler('lightrag.testParserConfig')
def handle_test_parser_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Probe an external parser using the current, possibly unsaved UI values."""
    try:
        is_valid, data, error = validate_params(params, ['engine', 'settings'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        engine = str(data.get('engine') or '').strip().lower()
        settings = data.get('settings')
        if not isinstance(settings, dict):
            return create_error_response(request, 'INVALID_PARAMS', 'settings must be an object')

        from knowledge.lightrag_parser_probe import probe_parser

        result = probe_parser(engine, settings)
        logger.info(f"[LightRAG] Parser probe succeeded: engine={engine}, url={result.get('url')}")
        return create_success_response(request, {'available': True, **result})
    except (ValueError, RuntimeError) as e:
        logger.warning(f"[LightRAG] Parser probe failed: {e}")
        technical_detail = str(e)
        detail_lower = technical_detail.lower()
        if '未配置' in technical_detail:
            category = 'missing_config'
        elif '有效的 http' in detail_lower or '只能是 local' in detail_lower:
            category = 'invalid_config'
        elif '鉴权失败' in technical_detail or '401' in technical_detail or '403' in technical_detail:
            category = 'authentication'
        elif '超时' in technical_detail:
            category = 'timeout'
        elif '无法连接' in technical_detail:
            category = 'connection'
        elif '不像 mineru' in detail_lower:
            category = 'wrong_service'
        elif 'http ' in detail_lower or '服务异常' in technical_detail:
            category = 'service_error'
        else:
            category = 'unknown'
        # An unavailable provider is an expected probe result, not a GraphQL
        # transport/handler failure. Returning structured data avoids noisy
        # registry tracebacks while preserving the exact diagnostic for UI.
        return create_success_response(request, {
            'available': False,
            'category': category,
            'technical_detail': technical_detail,
        })
    except Exception as e:
        logger.error(f"[LightRAG] Parser probe error: {e}", exc_info=True)
        return create_error_response(
            request,
            'PARSER_PROBE_ERROR',
            'Parser configuration test failed',
            {'category': 'unknown', 'technical_detail': str(e)},
        )


@IPCHandlerRegistry.background_handler('lightrag.testModelServiceConfig')
def handle_test_model_service_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Run a minimal real request against the selected LLM/embed/rerank service."""
    try:
        is_valid, data, error = validate_params(params, ['kind', 'settings'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        settings = data.get('settings')
        if not isinstance(settings, dict):
            return create_error_response(request, 'INVALID_PARAMS', 'settings must be an object')
        kind = str(data.get('kind') or '').strip().lower()
        prefix = {'llm': 'LLM', 'embedding': 'EMBEDDING', 'rerank': 'RERANK'}.get(kind)
        if not prefix:
            return create_error_response(request, 'INVALID_PARAMS', 'Unsupported provider kind')

        # Resolve the same provider configuration used by System Settings.
        # Browser state may contain masked keys and rerank's internal proxy
        # URL, neither of which should be used to probe the upstream service.
        resolved_settings = dict(settings)
        provider_id = str(settings.get(f'{prefix}_BINDING') or '').strip()
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        manager = getattr(main_window.config_manager, f'{kind}_manager', None) if main_window else None
        provider = manager.get_provider(provider_id) if manager and provider_id else None
        if provider:
            system_host = str(provider.get('base_url') or '').strip()
            ui_host = str(settings.get(f'{prefix}_BINDING_HOST') or '').strip()
            if kind == 'rerank':
                from knowledge.lightrag_constants import is_native_rerank_provider
                host = system_host if not is_native_rerank_provider(provider_id) else (ui_host or system_host)
            elif provider.get('is_local'):
                # Ollama/RyoAIS addresses are managed centrally in System
                # Settings and shared by LightRAG.
                host = system_host or ui_host
            else:
                host = ui_host or system_host
            resolved_settings[f'{prefix}_BINDING_HOST'] = host
            resolved_settings[f'{prefix}_MODEL'] = str(
                settings.get(f'{prefix}_MODEL') or provider.get('preferred_model') or provider.get('default_model') or ''
            ).strip()
            api_key = ''
            for env_name in provider.get('api_key_env_vars', []) or []:
                api_key = manager.retrieve_api_key(env_name) or ''
                if api_key:
                    break
            resolved_settings[f'{prefix}_BINDING_API_KEY'] = api_key
        resolved_settings.setdefault('SSL_VERIFY', False)
        from knowledge.lightrag_service_probe import probe_model_service
        return create_success_response(request, probe_model_service(kind, resolved_settings))
    except Exception as e:
        from knowledge.lightrag_service_probe import ServiceProbeError
        category = e.category if isinstance(e, ServiceProbeError) else 'unknown'
        logger.warning(f"[LightRAG] Model service probe failed: kind={(params or {}).get('kind')}, error={e}")
        # Unavailable is an expected probe result, not a GraphQL transport
        # failure. Returning it as normal data prevents noisy console errors
        # and lets the UI render the categorized reason.
        return create_success_response(request, {
            'available': False,
            'category': category,
            'technical_detail': str(e),
        })


@IPCHandlerRegistry.background_handler('lightrag.testSystemProvider')
def handle_test_system_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Probe one provider from System Settings without exposing its stored key."""
    try:
        is_valid, data, error = validate_params(params, ['kind', 'provider'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        kind = str(data.get('kind') or '').lower()
        provider_id = str(data.get('provider') or '').strip()
        prefix = {'llm': 'LLM', 'embedding': 'EMBEDDING', 'rerank': 'RERANK'}.get(kind)
        if not prefix:
            return create_error_response(request, 'INVALID_PARAMS', 'Unsupported provider kind')

        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return create_error_response(request, 'APP_NOT_READY', 'Application is not ready')
        manager = getattr(main_window.config_manager, f'{kind}_manager')
        provider = manager.get_provider(provider_id)
        if not provider:
            return create_error_response(request, 'PROVIDER_NOT_FOUND', 'Provider not found')

        model = str(data.get('model') or provider.get('preferred_model') or provider.get('default_model') or '').strip()
        host = str(data.get('host') or provider.get('base_url') or '').strip()
        api_key = ''
        for env_name in provider.get('api_key_env_vars', []) or []:
            api_key = manager.retrieve_api_key(env_name) or ''
            if api_key:
                break
        if provider.get('api_key_env_vars') and not api_key and not provider.get('is_local'):
            return create_success_response(request, {
                'available': False,
                'category': 'missing_config',
                'technical_detail': 'API key is not configured',
            })

        from knowledge.lightrag_service_probe import probe_model_service
        result = probe_model_service(kind, {
            f'{prefix}_BINDING': provider_id,
            f'{prefix}_BINDING_HOST': host,
            f'{prefix}_MODEL': model,
            f'{prefix}_BINDING_API_KEY': api_key,
            # System provider custom endpoints commonly use private/self-
            # signed certificates. Match the LightRAG runtime default.
            'SSL_VERIFY': False,
        })
        return create_success_response(request, result)
    except Exception as e:
        from knowledge.lightrag_service_probe import ServiceProbeError
        category = e.category if isinstance(e, ServiceProbeError) else 'unknown'
        logger.warning(f"[SystemSettings] Provider probe failed: {e}")
        return create_success_response(request, {
            'available': False,
            'category': category,
            'technical_detail': str(e),
        })


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


@IPCHandlerRegistry.handler('lightrag.getSystemProviders')
def handle_get_system_providers(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Get system LLM, Embedding and Rerank providers for LightRAG configuration.
    
    Reuses existing provider handlers to ensure consistency with Settings page.
    """
    try:
        from app_context import AppContext
        from gui.ipc.context_bridge import get_handler_context, get_username
        from gui.ollama_utils import merge_ollama_models_to_providers
        from gui.ryoais_utils import merge_ryoais_models_to_providers, load_ryoais_models
        
        # Get manager instances
        ctx = get_handler_context(request, params)
        llm_manager = ctx.get_config_manager().llm_manager if ctx else None
        embedding_manager = ctx.get_config_manager().embedding_manager if ctx else None
        rerank_manager = ctx.get_config_manager().rerank_manager if ctx else None

        # Get current username for user-specific file paths
        username = get_username(request, params)

        # Pre-load RyoAIS models with correct username so merge finds them
        ryoais_llm = load_ryoais_models(username=username, model_type='llm')
        ryoais_emb = load_ryoais_models(username=username, model_type='embedding')
        ryoais_rerank = load_ryoais_models(username=username, model_type='rerank')

        # Get providers with Ollama and RyoAIS models merged (same as Settings page)
        llm_providers = merge_ollama_models_to_providers(
            llm_manager.get_all_providers() if llm_manager else [],
            provider_type='llm'
        )
        llm_providers = merge_ryoais_models_to_providers(
            llm_providers,
            ryoais_models=ryoais_llm,
            provider_type='llm'
        )
        
        embedding_providers = merge_ollama_models_to_providers(
            embedding_manager.get_all_providers() if embedding_manager else [],
            provider_type='embedding'
        )
        embedding_providers = merge_ryoais_models_to_providers(
            embedding_providers,
            ryoais_models=ryoais_emb,
            provider_type='embedding'
        )
        
        rerank_providers = merge_ollama_models_to_providers(
            rerank_manager.get_all_providers() if rerank_manager else [],
            provider_type='rerank'
        )
        rerank_providers = merge_ryoais_models_to_providers(
            rerank_providers,
            ryoais_models=ryoais_rerank,
            provider_type='rerank'
        )
        
        return create_success_response(request, {
            'llm_providers': llm_providers,
            'embedding_providers': embedding_providers,
            'rerank_providers': rerank_providers
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
        
        file_reference = str(data['fileName']).strip()
        if not file_reference:
            return create_error_response(request, 'INVALID_PARAMS', 'fileName must not be empty')

        # LightRAG does not expose a document-download API. Uploaded source
        # files are retained beneath INPUT_DIR, so resolve the reference there
        # instead of calling the non-existent /documents/download route.
        import shutil
        from pathlib import Path
        from knowledge.lightrag_config_manager import get_config_manager

        input_dir_value = get_config_manager().get_value('INPUT_DIR')
        if not input_dir_value:
            return create_error_response(
                request,
                'DOWNLOAD_CONFIG_ERROR',
                '下载失败：LightRAG 未配置 INPUT_DIR'
            )

        input_dir = Path(os.path.expandvars(os.path.expanduser(input_dir_value))).resolve()
        if not input_dir.is_dir():
            return create_error_response(
                request,
                'DOWNLOAD_CONFIG_ERROR',
                f'下载失败：LightRAG 文档目录不存在 ({input_dir})'
            )

        normalized_reference = file_reference.replace('\\', '/')
        reference_path = Path(normalized_reference)
        candidates = []

        # Prefer the exact relative path when the reference contains folders.
        if not reference_path.is_absolute():
            relative_candidate = (input_dir / reference_path).resolve()
            try:
                relative_candidate.relative_to(input_dir)
                candidates.append(relative_candidate)
            except ValueError:
                pass

        # Query references can contain an old absolute path or just a basename.
        # Resolve those by basename, but only inside INPUT_DIR.
        basename = reference_path.name
        if basename:
            candidates.extend(input_dir.rglob(basename))

        source_file = next(
            (candidate for candidate in candidates if candidate.is_file()),
            None,
        )
        if source_file is None:
            logger.warning(
                "[LightRAG] Download source not found: reference=%s input_dir=%s",
                file_reference,
                input_dir,
            )
            return create_error_response(
                request,
                'DOWNLOAD_FILE_NOT_FOUND',
                f'下载失败：在 LightRAG 文档目录中找不到“{basename or file_reference}”'
            )

        logger.info(f"Downloading LightRAG source file: {source_file}")
        
        # Get Downloads folder
        downloads_dir = os.path.expanduser('~/Downloads')
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir, exist_ok=True)
        
        # Handle duplicate filenames
        file_name = source_file.name
        dest_file = os.path.join(downloads_dir, file_name)
        if os.path.exists(dest_file):
            base_name = os.path.splitext(file_name)[0]
            extension = os.path.splitext(file_name)[1]
            counter = 1
            while os.path.exists(dest_file):
                dest_file = os.path.join(downloads_dir, f"{base_name}_{counter}{extension}")
                counter += 1
        
        shutil.copy2(source_file, dest_file)
        
        logger.info(f"File saved to: {dest_file}")

        return create_success_response(request, {
            'success': True,
            'filePath': dest_file,
            'fileName': os.path.basename(dest_file)
        })

    except Exception as e:
        logger.error(f"Error downloading file: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'DOWNLOAD_ERROR', str(e))


@IPCHandlerRegistry.handler('lightrag.getEcanaiApiKey')
def handle_get_ecanai_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Retrieve the eCanAI account-level LLM API key from secure_store.

    Used by the parser settings UI to auto-fill MINERU_API_TOKEN and
    DOCLING_API_KEY when the user selects the eCanAI provider.  Returns
    None (not an error) when no key has been provisioned yet.
    """
    try:
        from utils.env.secure_store import secure_store
        from gui.ipc.context_bridge import get_username
        username = get_username(request, params)
        key = secure_store.get("ECANAI_LLM_API_KEY", username=username) if username else None
        key = str(key).strip() if key else ""
        return create_success_response(request, {
            "apiKey": key or None,
        })
    except Exception as e:
        logger.debug(f"[lightrag.getEcanaiApiKey] failed: {e}")
        return create_success_response(request, {"apiKey": None})


def _read_ecanai_account_key(request: IPCRequest) -> str:
    """
    Return the current account-level eCanAI API key, or '' when no key is
    provisioned / no user is signed in / secure_store is unreachable.

    Used by ``handle_get_parser_engines`` to seed the eCanAI-mode UI field
    with the live account credential instead of the stale ``.env`` value.
    Mirrors the lookup in ``handle_get_ecanai_api_key`` so the two paths
    cannot drift.
    """
    try:
        from utils.env.secure_store import secure_store
        from gui.ipc.context_bridge import get_username
        username = get_username(request, {})
        if not username:
            return ""
        key = secure_store.get("ECANAI_LLM_API_KEY", username=username)
        return str(key).strip() if key else ""
    except Exception as ecanai_lookup_error:
        logger.debug(
            f"[getParserEngines] eCanAI account key lookup failed: {ecanai_lookup_error}"
        )
        return ""
