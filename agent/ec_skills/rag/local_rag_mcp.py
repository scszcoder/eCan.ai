import asyncio
import os
import threading
import time
from typing import Any, Dict, List, Optional

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from mcp.types import TextContent
from knowledge.lightrag_client import get_client


async def ragify(mainwin, args):
    """
    MCP Tool: Ingest documents into LightRAG for RAG indexing.
    
    Supports two modes:
    1. File upload: Upload files from file_paths to LightRAG
    2. Text insert: Directly insert text content into LightRAG
    
    Based on LightRAG API:
    - POST /documents/upload (file upload)
    - POST /documents/text (text insert)
    """
    try:
        rag_result = None
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
            
        logger.debug(f"[MCP][RAGIFY]: {input_data}")
        
        # Extract parameters
        file_paths = input_data.get("file_paths", [])
        text = input_data.get("text")
        file_source = input_data.get("file_source")
        
        # Initialize client
        client = get_client()
        
        # Mode 1: File upload
        if file_paths:
            rag_result = client.ingest_files(file_paths)
            logger.info(f"[MCP][RAGIFY] File ingestion result: {rag_result}")
            msg = f"Ingested {len(file_paths)} file(s)"
        # Mode 2: Text insert
        elif text:
            metadata = {"file_source": file_source} if file_source else None
            rag_result = client.insert_text(text, metadata)
            logger.info(f"[MCP][RAGIFY] Text insert result: {rag_result}")
            msg = "Text inserted successfully"
        else:
            rag_result = {"status": "error", "message": "No file_paths or text provided"}
            msg = "Error: No file_paths or text provided"

        # Build response
        if rag_result.get("status") == "success":
            result_text = f"{msg}. Track ID: {rag_result.get('data', {}).get('track_id', 'N/A')}"
        else:
            result_text = f"Error: {rag_result.get('message', 'Unknown error')}"
            
        result = TextContent(type="text", text=result_text)
        if isinstance(rag_result, dict):
            result.meta = rag_result
        else:
            result.meta = {"result": str(rag_result)}
             
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagifyTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rag_query(mainwin, args):
    """
    MCP Tool: Query LightRAG knowledge base.
    
    Based on LightRAG API POST /query:
    - query: Query text (required, min 3 chars)
    - mode: Query mode (local, global, hybrid, naive, mix, bypass), default: mix
    - only_need_context: Return only context without generating response
    - only_need_prompt: Return only prompt without generating response
    - response_type: Response format (e.g., 'Multiple Paragraphs', 'Bullet Points')
    - top_k: Number of top items to retrieve
    - conversation_history: Past conversation for context
    - user_prompt: Custom user prompt
    - enable_rerank: Enable reranking (default: True)
    - include_references: Include reference list (default: True)
    """
    try:
        rag_result = None
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
            
        logger.debug(f"[MCP][RAG_QUERY]: {input_data}")
        
        # Extract query (required)
        query_text = input_data.get("query")
        if not query_text or len(query_text.strip()) < 3:
            return [TextContent(type="text", text="Error: Query must be at least 3 characters")]
        
        # Initialize client
        client = get_client()
        
        # Build options from input - map to LightRAG QueryRequest parameters
        options = {}
        
        # Mode: local, global, hybrid, naive, mix, bypass
        mode = input_data.get("mode", "mix")
        if mode in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
            options["mode"] = mode
        else:
            options["mode"] = "mix"  # Default to mix
            
        # All optional parameters from LightRAG QueryRequest schema
        OPTIONAL_PARAMS = [
            "only_need_context",     # bool
            "only_need_prompt",      # bool
            "response_type",         # str
            "top_k",                 # int
            "chunk_top_k",           # int
            "max_entity_tokens",     # int
            "max_relation_tokens",   # int
            "max_total_tokens",      # int
            "hl_keywords",           # list[str]
            "ll_keywords",           # list[str]
            "conversation_history",  # list[dict]
            "user_prompt",           # str
            "enable_rerank",         # bool
            "include_references",    # bool
            "include_chunk_content", # bool
        ]
        
        for param in OPTIONAL_PARAMS:
            if param in input_data and input_data[param] is not None:
                # Skip empty lists/strings
                val = input_data[param]
                if isinstance(val, list) and len(val) == 0:
                    continue
                if isinstance(val, str) and not val.strip():
                    continue
                options[param] = val
        
        # Execute query
        response = client.query(query_text.strip(), options)
        
        if response.get("status") == "success":
            data = response.get("data", {})
            # LightRAG returns {"response": "...", "references": [...]}
            if isinstance(data, dict):
                answer = data.get("response", str(data))
            else:
                answer = str(data)
            rag_result = response
        else:
            answer = f"Error: {response.get('message', 'Query failed')}"
            rag_result = response

        result = TextContent(type="text", text=answer)
        if isinstance(rag_result, dict):
            result.meta = rag_result
        else:
            result.meta = {"result": str(rag_result)}
             
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagQueryTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def add_ragify_tool_schema(tool_schemas):
    """
    Add ragify tool schema for document ingestion into LightRAG.
    
    Based on LightRAG API:
    - POST /documents/upload - Upload files for indexing
    - POST /documents/text - Insert text directly
    
    Reference: https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/document_routes.py
    """
    import mcp.types as types

    tool_schema = types.Tool(
        name="ragify",
        description="Ingest documents or text into LightRAG for RAG indexing. Supports file upload or direct text insertion. Returns a track_id for monitoring processing status.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "file_paths": {
                            "type": "array",
                            "description": "List of file paths to upload and index. Supports: pdf, doc, docx, txt, md, html, csv, json, xml, py, js, etc.",
                            "items": {"type": "string"}
                        },
                        "text": {
                            "type": "string",
                            "description": "Direct text content to insert into the knowledge base (alternative to file_paths)."
                        },
                        "file_source": {
                            "type": "string",
                            "description": "Optional source identifier for the inserted text."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


# ==================== Option 4: wait_for_rag_completion ====================

def _calculate_timeout_seconds(file_paths: List[str], text: str = None) -> int:
    """
    Calculate timeout based on file sizes.
    Formula: (total_size_kb / 10) * 60 + 180 seconds (10KB/min + 3min buffer)
    """
    total_size_bytes = 0
    
    if file_paths:
        for path in file_paths:
            try:
                if os.path.exists(path):
                    total_size_bytes += os.path.getsize(path)
            except Exception:
                pass
    
    if text:
        total_size_bytes += len(text.encode('utf-8'))
    
    # Convert to KB
    total_size_kb = total_size_bytes / 1024
    
    # Formula: 10KB/min + 3min buffer
    timeout_seconds = int((total_size_kb / 10) * 60 + 180)
    
    # Minimum 3 minutes, maximum 60 minutes
    return max(180, min(timeout_seconds, 3600))


async def wait_for_rag_completion(mainwin, args):
    """
    MCP Tool: Wait for RAG ingestion to complete by polling track_id status.
    
    This is a synchronous blocking tool that polls LightRAG until all documents
    in the track_id are processed or failed, or timeout is reached.
    
    Timeout formula: (total_file_size_kb / 10) * 60 + 180 seconds (10KB/min + 3min buffer)
    
    Returns partial results if some documents succeed and others fail.
    """
    try:
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
        
        track_id = input_data.get("track_id")
        if not track_id:
            return [TextContent(type="text", text="Error: track_id is required")]
        
        poll_interval = input_data.get("poll_interval_seconds", 15)
        timeout_seconds = input_data.get("timeout_seconds")
        max_retries = input_data.get("max_retries", 3)
        
        # If timeout not provided, use default based on typical file size estimate
        # (we don't have file sizes here, so use a reasonable default)
        if timeout_seconds is None:
            timeout_seconds = 600  # 10 minutes default
        
        logger.info(f"[wait_for_rag_completion] Waiting for track_id={track_id}, "
                   f"timeout={timeout_seconds}s, poll_interval={poll_interval}s")
        
        client = get_client()
        start_time = time.time()
        retry_count = 0
        last_status = None
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed >= timeout_seconds:
                logger.warning(f"[wait_for_rag_completion] Timeout after {elapsed:.1f}s for track_id={track_id}")
                result_text = f"Timeout after {elapsed:.1f}s. Last status: {last_status}"
                result = TextContent(type="text", text=result_text)
                result.meta = {
                    "status": "timeout",
                    "track_id": track_id,
                    "elapsed_seconds": elapsed,
                    "last_status": last_status
                }
                return [result]
            
            # Poll status
            try:
                status_response = client.track_status(track_id)
                retry_count = 0  # Reset retry count on success
                
                if status_response.get("status") == "success":
                    data = status_response.get("data", {})
                    documents = data.get("documents", [])
                    status_summary = data.get("status_summary", {})
                    
                    last_status = status_summary
                    
                    # Check if all documents are done (processed or failed)
                    pending_count = status_summary.get("pending", 0)
                    processing_count = status_summary.get("processing", 0)
                    preprocessed_count = status_summary.get("preprocessed", 0)
                    processed_count = status_summary.get("processed", 0)
                    failed_count = status_summary.get("failed", 0)
                    
                    in_progress = pending_count + processing_count + preprocessed_count
                    
                    logger.debug(f"[wait_for_rag_completion] Status: pending={pending_count}, "
                               f"processing={processing_count}, preprocessed={preprocessed_count}, "
                               f"processed={processed_count}, failed={failed_count}")
                    
                    if in_progress == 0:
                        # All done
                        if failed_count > 0 and processed_count > 0:
                            result_text = f"Partial completion: {processed_count} processed, {failed_count} failed"
                            final_status = "partial_success"
                        elif failed_count > 0:
                            result_text = f"All {failed_count} document(s) failed"
                            final_status = "failed"
                        else:
                            result_text = f"All {processed_count} document(s) processed successfully"
                            final_status = "success"
                        
                        logger.info(f"[wait_for_rag_completion] Completed: {result_text}")
                        
                        result = TextContent(type="text", text=result_text)
                        result.meta = {
                            "status": final_status,
                            "track_id": track_id,
                            "elapsed_seconds": elapsed,
                            "processed_count": processed_count,
                            "failed_count": failed_count,
                            "documents": documents
                        }
                        return [result]
                else:
                    logger.warning(f"[wait_for_rag_completion] Status check failed: {status_response.get('message')}")
                    retry_count += 1
                    
            except Exception as e:
                logger.warning(f"[wait_for_rag_completion] Poll error: {e}")
                retry_count += 1
                
                if retry_count >= max_retries:
                    result_text = f"Max retries ({max_retries}) exceeded. Last error: {e}"
                    result = TextContent(type="text", text=result_text)
                    result.meta = {
                        "status": "error",
                        "track_id": track_id,
                        "elapsed_seconds": elapsed,
                        "error": str(e)
                    }
                    return [result]
            
            # Wait before next poll
            await asyncio.sleep(poll_interval)
            
    except Exception as e:
        err_trace = get_traceback(e, "ErrorWaitForRagCompletion")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Option 3: ragify_async with callback ====================

# Global registry for pending async RAG operations
_pending_rag_callbacks: Dict[str, Dict[str, Any]] = {}


def _rag_completion_monitor(
    track_id: str,
    timeout_seconds: int,
    poll_interval: int,
    task_id: str,
    chat_id: str,
    mainwin: Any,
    notification_message: str = None
):
    """
    Background thread that monitors RAG completion and sends notification to task queue.
    
    If the original task is ended, falls back to the chat task.
    """
    try:
        logger.info(f"[RAG_MONITOR] Started for track_id={track_id}, task_id={task_id}, timeout={timeout_seconds}s")
        
        client = get_client()
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed >= timeout_seconds:
                logger.warning(f"[RAG_MONITOR] Timeout for track_id={track_id}")
                _send_rag_notification(
                    mainwin, task_id, chat_id, track_id,
                    status="timeout",
                    message=notification_message or f"RAG ingestion timed out after {elapsed:.0f}s",
                    elapsed_seconds=elapsed
                )
                break
            
            # Poll status
            try:
                status_response = client.track_status(track_id)
                
                if status_response.get("status") == "success":
                    data = status_response.get("data", {})
                    status_summary = data.get("status_summary", {})
                    
                    pending_count = status_summary.get("pending", 0)
                    processing_count = status_summary.get("processing", 0)
                    preprocessed_count = status_summary.get("preprocessed", 0)
                    processed_count = status_summary.get("processed", 0)
                    failed_count = status_summary.get("failed", 0)
                    
                    in_progress = pending_count + processing_count + preprocessed_count
                    
                    if in_progress == 0:
                        # All done
                        if failed_count > 0 and processed_count > 0:
                            final_status = "partial_success"
                            msg = f"RAG ingestion partial: {processed_count} processed, {failed_count} failed"
                        elif failed_count > 0:
                            final_status = "failed"
                            msg = f"RAG ingestion failed: {failed_count} document(s)"
                        else:
                            final_status = "success"
                            msg = f"RAG ingestion complete: {processed_count} document(s) processed"
                        
                        logger.info(f"[RAG_MONITOR] Completed: {msg}")
                        _send_rag_notification(
                            mainwin, task_id, chat_id, track_id,
                            status=final_status,
                            message=notification_message or msg,
                            elapsed_seconds=elapsed,
                            processed_count=processed_count,
                            failed_count=failed_count,
                            documents=data.get("documents", [])
                        )
                        break
                        
            except Exception as e:
                logger.warning(f"[RAG_MONITOR] Poll error for track_id={track_id}: {e}")
            
            # Wait before next poll
            time.sleep(poll_interval)
            
    except Exception as e:
        logger.error(get_traceback(e, "ErrorRagMonitor"))
    finally:
        # Cleanup
        if track_id in _pending_rag_callbacks:
            del _pending_rag_callbacks[track_id]


def _send_rag_notification(
    mainwin: Any,
    task_id: str,
    chat_id: str,
    track_id: str,
    status: str,
    message: str,
    elapsed_seconds: float = 0,
    processed_count: int = 0,
    failed_count: int = 0,
    documents: List = None
):
    """
    Send RAG completion notification to the task's message queue.
    Falls back to chat task if original task is ended.
    """
    try:
        notification = {
            "type": "rag_completion",
            "track_id": track_id,
            "status": status,
            "message": message,
            "elapsed_seconds": elapsed_seconds,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "documents": documents or [],
            "timestamp": int(time.time() * 1000)
        }
        
        # Try to find the target task
        target_task = None
        
        if mainwin and hasattr(mainwin, 'agents'):
            for agent in mainwin.agents:
                tasks = getattr(agent, 'tasks', []) or []
                for task in tasks:
                    # First try to find the original task
                    if task_id and getattr(task, 'id', None) == task_id:
                        # Check if task is still active
                        task_status = getattr(task, 'status', None)
                        if task_status:
                            state = getattr(task_status, 'state', None)
                            state_str = state.value if hasattr(state, 'value') else str(state)
                            if state_str.lower() in ('working', 'running', 'in_progress', 'pending'):
                                target_task = task
                                break
                    
                    # Fallback: find chat task by chat_id
                    if not target_task and chat_id:
                        skill = getattr(task, 'skill', None)
                        if skill and getattr(skill, 'name', '').lower() in ('chat', 'chatter'):
                            target_task = task
                
                if target_task:
                    break
        
        if target_task and hasattr(target_task, 'queue') and target_task.queue:
            try:
                target_task.queue.put_nowait(notification)
                logger.info(f"[RAG_NOTIFY] Sent notification to task={getattr(target_task, 'name', 'unknown')}")
            except Exception as e:
                logger.error(f"[RAG_NOTIFY] Failed to queue notification: {e}")
        else:
            logger.warning(f"[RAG_NOTIFY] No active task found for notification. task_id={task_id}, chat_id={chat_id}")
            
    except Exception as e:
        logger.error(get_traceback(e, "ErrorSendRagNotification"))


async def ragify_async(mainwin, args):
    """
    MCP Tool: Ingest documents into LightRAG with async completion notification.
    
    This is a fire-and-forget tool that starts ingestion and optionally monitors
    completion in a background thread, sending a notification to the task queue
    when done.
    
    Parameters:
        - file_paths: List of file paths to upload
        - text: Direct text to insert (alternative to file_paths)
        - file_source: Source identifier for text
        - on_complete: If true, monitor completion and send notification
        - notify_task_id: Target task ID for notification (defaults to current task)
        - notify_chat_id: Fallback chat ID if task is ended
        - timeout_seconds: Max time to wait (auto-calculated from file size if not provided)
        - poll_interval_seconds: How often to check status (default: 15)
        - notification_message: Custom message to include in notification
    """
    try:
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
        
        logger.debug(f"[MCP][RAGIFY_ASYNC]: {input_data}")
        
        # Extract parameters
        file_paths = input_data.get("file_paths", [])
        text = input_data.get("text")
        file_source = input_data.get("file_source")
        on_complete = input_data.get("on_complete", False)
        notify_task_id = input_data.get("notify_task_id", "")
        notify_chat_id = input_data.get("notify_chat_id", "")
        timeout_seconds = input_data.get("timeout_seconds")
        poll_interval = input_data.get("poll_interval_seconds", 15)
        notification_message = input_data.get("notification_message")
        
        # Initialize client
        client = get_client()
        
        # Mode 1: File upload
        if file_paths:
            rag_result = client.ingest_files(file_paths)
            logger.info(f"[MCP][RAGIFY_ASYNC] File ingestion result: {rag_result}")
            msg = f"Ingested {len(file_paths)} file(s)"
            
            # Calculate timeout from file sizes if not provided
            if timeout_seconds is None:
                timeout_seconds = _calculate_timeout_seconds(file_paths)
                
        # Mode 2: Text insert
        elif text:
            metadata = {"file_source": file_source} if file_source else None
            rag_result = client.insert_text(text, metadata)
            logger.info(f"[MCP][RAGIFY_ASYNC] Text insert result: {rag_result}")
            msg = "Text inserted successfully"
            
            # Calculate timeout from text size if not provided
            if timeout_seconds is None:
                timeout_seconds = _calculate_timeout_seconds([], text)
        else:
            rag_result = {"status": "error", "message": "No file_paths or text provided"}
            msg = "Error: No file_paths or text provided"
        
        # Build response
        track_id = None
        if rag_result.get("status") == "success":
            track_id = rag_result.get('data', {}).get('track_id', 'N/A')
            result_text = f"{msg}. Track ID: {track_id}"
            
            # Start background monitor if on_complete is enabled
            if on_complete and track_id and track_id != 'N/A':
                logger.info(f"[RAGIFY_ASYNC] Starting completion monitor for track_id={track_id}")
                
                # Store callback info
                _pending_rag_callbacks[track_id] = {
                    "task_id": notify_task_id,
                    "chat_id": notify_chat_id,
                    "start_time": time.time()
                }
                
                # Start background thread
                monitor_thread = threading.Thread(
                    target=_rag_completion_monitor,
                    args=(track_id, timeout_seconds, poll_interval, notify_task_id, notify_chat_id, mainwin, notification_message),
                    daemon=True,
                    name=f"rag_monitor_{track_id}"
                )
                monitor_thread.start()
                
                result_text += f" (monitoring for completion, timeout={timeout_seconds}s)"
        else:
            result_text = f"Error: {rag_result.get('message', 'Unknown error')}"
        
        result = TextContent(type="text", text=result_text)
        if isinstance(rag_result, dict):
            result.meta = rag_result
            if on_complete:
                result.meta["monitoring"] = True
                result.meta["timeout_seconds"] = timeout_seconds
        else:
            result.meta = {"result": str(rag_result)}
        
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagifyAsyncTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Tool Schema Functions ====================

def add_rag_query_tool_schema(tool_schemas):
    """
    Add rag_query tool schema for querying LightRAG knowledge base.
    
    Based on LightRAG API POST /query QueryRequest schema.
    Reference: https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/query_routes.py
    """
    import mcp.types as types

    tool_schema = types.Tool(
        name="rag_query",
        description="Query LightRAG knowledge base using RAG. Retrieves relevant documents and generates natural language answers.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 3,
                            "description": "The query text to search for in the knowledge base."
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["local", "global", "hybrid", "naive", "mix", "bypass"],
                            "default": "mix",
                            "description": "Query mode: local (entity-focused), global (relationship patterns), hybrid (combined), naive (vector search), mix (knowledge graph + vector), bypass (direct LLM)."
                        },
                        "only_need_context": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, only returns the retrieved context without generating a response."
                        },
                        "only_need_prompt": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, only returns the generated prompt without producing a response."
                        },
                        "response_type": {
                            "type": "string",
                            "description": "Defines the response format. Examples: 'Multiple Paragraphs', 'Single Paragraph', 'Bullet Points'."
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Number of top items to retrieve. Represents entities in 'local' mode and relationships in 'global' mode."
                        },
                        "chunk_top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Number of text chunks to retrieve from vector search."
                        },
                        "max_entity_tokens": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum tokens for entity context."
                        },
                        "max_relation_tokens": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum tokens for relationship context."
                        },
                        "max_total_tokens": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum total tokens budget for query context."
                        },
                        "hl_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "High-level keywords to prioritize in retrieval."
                        },
                        "ll_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Low-level keywords to refine retrieval focus."
                        },
                        "conversation_history": {
                            "type": "array",
                            "description": "Past conversation history for context. Format: [{'role': 'user/assistant', 'content': 'message'}].",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["user", "assistant"]},
                                    "content": {"type": "string"}
                                },
                                "required": ["role", "content"]
                            }
                        },
                        "user_prompt": {
                            "type": "string",
                            "description": "Custom user prompt to guide LLM response generation (does not affect retrieval)."
                        },
                        "enable_rerank": {
                            "type": "boolean",
                            "default": True,
                            "description": "Enable reranking for retrieved text chunks."
                        },
                        "include_references": {
                            "type": "boolean",
                            "default": True,
                            "description": "If true, includes reference list in responses."
                        },
                        "include_chunk_content": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, includes actual chunk text content in references."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_wait_for_rag_completion_tool_schema(tool_schemas):
    """
    Add wait_for_rag_completion tool schema for synchronous waiting on RAG ingestion.
    """
    import mcp.types as types

    tool_schema = types.Tool(
        name="wait_for_rag_completion",
        description="Wait for RAG ingestion to complete by polling track_id status. Blocks until all documents are processed/failed or timeout. Use this when you need to query the documents immediately after ingestion. Timeout is auto-calculated: (file_size_kb / 10) * 60 + 180 seconds.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["track_id"],
                    "properties": {
                        "track_id": {
                            "type": "string",
                            "description": "The track_id returned from ragify or ragify_async tool."
                        },
                        "poll_interval_seconds": {
                            "type": "integer",
                            "default": 15,
                            "minimum": 5,
                            "description": "How often to check status (default: 15 seconds)."
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 60,
                            "description": "Max time to wait in seconds. If not provided, defaults to 600 seconds (10 minutes)."
                        },
                        "max_retries": {
                            "type": "integer",
                            "default": 3,
                            "minimum": 1,
                            "description": "Max consecutive poll failures before giving up (default: 3)."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_ragify_async_tool_schema(tool_schemas):
    """
    Add ragify_async tool schema for async RAG ingestion with completion notification.
    """
    import mcp.types as types

    tool_schema = types.Tool(
        name="ragify_async",
        description="Ingest documents into LightRAG with optional async completion notification. Fire-and-forget by default. Set on_complete=true to receive a notification in the task queue when processing finishes. Timeout is auto-calculated from file size: (size_kb / 10) * 60 + 180 seconds.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "file_paths": {
                            "type": "array",
                            "description": "List of file paths to upload and index.",
                            "items": {"type": "string"}
                        },
                        "text": {
                            "type": "string",
                            "description": "Direct text content to insert (alternative to file_paths)."
                        },
                        "file_source": {
                            "type": "string",
                            "description": "Optional source identifier for the inserted text."
                        },
                        "on_complete": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, monitor completion and send notification to task queue when done."
                        },
                        "notify_task_id": {
                            "type": "string",
                            "description": "Target task ID for completion notification. If task ends, falls back to chat task."
                        },
                        "notify_chat_id": {
                            "type": "string",
                            "description": "Fallback chat ID for notification if original task is ended."
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 60,
                            "description": "Max time to monitor for completion. Auto-calculated from file size if not provided."
                        },
                        "poll_interval_seconds": {
                            "type": "integer",
                            "default": 15,
                            "minimum": 5,
                            "description": "How often to check status when monitoring (default: 15 seconds)."
                        },
                        "notification_message": {
                            "type": "string",
                            "description": "Custom message to include in the completion notification."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)