import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback


def _resolve_base_url() -> str:
    """Resolve LightRAG server base URL from the running server, env, or defaults.

    The server manager relocates to an alternative port when the default is
    occupied (e.g. by a stale orphan from a previous session), so prefer the
    port the LIVE LightragServer instance actually bound — otherwise clients
    keep talking to whatever squats on 9621.
    """
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "9621")
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        server = getattr(mainwin, "lightrag_server", None) if mainwin else None
        actual = getattr(server, "port", None)
        if actual:
            port = str(actual)
    except Exception:
        pass
    scheme = "http"
    return f"{scheme}://{host}:{port}"


def _ws_headers(workspace: Optional[str], base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build request headers with the optional LIGHTRAG-WORKSPACE header.

    LightRAG upstream (see ``lightrag/api/lightrag_server.py::get_workspace_from_request``)
    reads the custom ``LIGHTRAG-WORKSPACE`` header per request and falls back to the
    server's default workspace when the header is absent or empty.  Passing an empty
    string / ``None`` here leaves the default behavior untouched, so callers that
    don't care about multi-tenancy stay backward compatible.
    """
    headers: Dict[str, str] = dict(base or {})
    if workspace:
        _w = str(workspace).strip()
        if _w:
            # Percent-encode so any Unicode (e.g. Chinese) travels safely as
            # a valid ASCII HTTP header value (RFC 7230).
            headers["LIGHTRAG-WORKSPACE"] = quote(_w, safe='')
    return headers


def _is_app_shutdown_active() -> bool:
    try:
        from agent.ec_tasks.runner import is_app_shutdown_active
        return bool(is_app_shutdown_active())
    except Exception:
        return False


def _shutdown_abort_result(text: str, workspace: Optional[str] = None) -> Dict[str, Any]:
    message = "LightRAG query aborted because application shutdown is in progress"
    return {
        "status": "aborted",
        "message": message,
        "reason": "shutdown",
        "data": {
            "response": message,
            "aborted": True,
            "abort_reason": "shutdown",
            "query": text,
            "workspace": workspace,
            "references": [],
        },
    }


class LightragClient:
    """Backend adapter to proxy LightRAG WebGUI API calls from frontend IPC."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or _resolve_base_url()
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Configure proxy based on target URL (bypass for localhost/LAN)
        from agent.ec_skills.system_proxy import configure_requests_session
        configure_requests_session(self.session, self.base_url)
        
        if api_key:
            self.session.headers["X-API-Key"] = api_key
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        logger.info(f"[LightragClient] base_url={self.base_url}")

    # ---- Health/Auth ----
    def health(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/health", timeout=10)
            
            if r.status_code >= 400:
                logger.error(f"Health check failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.health HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.health")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Documents ingestion ----
    def ingest_files(self, paths: List[str], options: Optional[Dict[str, Any]] = None, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Request to vectorize and store files into the vector DB.
        
        Args:
            paths: List of file paths to ingest
            options: Optional configuration for ingestion
            workspace: Optional LightRAG workspace (tenant) name for data isolation.
                When omitted, the server's default workspace is used.
            
        Returns:
            Dict with status and job information
        """
        try:
            # Prepare multipart file upload
            files = []
            for path in paths:
                if not os.path.exists(path):
                    logger.warning(f"File not found: {path}")
                    continue
                try:
                    # Key must be 'file' based on server 422 error: "loc":["body","file"]
                    files.append(('file', (os.path.basename(path), open(path, 'rb'))))
                except Exception as e:
                    logger.error(f"Failed to open file {path}: {e}")
                    continue
            
            if not files:
                return {"status": "error", "message": "No valid files to ingest"}
            
            # Send files to the server using the correct endpoint
            # Note: options are not supported in multipart upload, they should be query params if needed
            # Important: Set Content-Type to None to let requests library generate the correct multipart/form-data header with boundary
            # Reduced timeout from 300s to 60s - large files should be handled by backend async processing
            r = self.session.post(
                f"{self.base_url}/documents/upload",
                files=files,
                timeout=60,
                headers=_ws_headers(workspace, {"Content-Type": None}),
            )
            
            if r.status_code >= 400:
                logger.error(f"Upload failed with status {r.status_code}: {r.text}")
                
            r.raise_for_status()
            
            # Close file handles
            for _, (_, file_handle) in files:
                file_handle.close()
            
            result = r.json()
            # API returns: {"status": "success", "message": "...", "track_id": "..."}
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.ingest_files HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.ingest_files")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # Allowed knowledge document types for RAG ingestion
    ALLOWED_EXTENSIONS = (
        # Documents
        '.pdf',
        '.doc', '.docx',
        '.ppt', '.pptx',
        '.xls', '.xlsx',
        '.rtf', '.odt', '.tex', '.epub',

        # Text / Config / Data
        '.txt', '.md', '.rst', '.log',
        '.html', '.htm',
        '.csv', '.tsv', '.json',
        '.xml', '.yaml', '.yml',
        '.conf', '.ini', '.properties',

        # Code
        '.sql', '.bat', '.sh',
        '.c', '.cpp', '.py', '.java', '.js', '.ts', '.swift', '.go', '.rb', '.php',
        '.css', '.scss', '.less',

        # Media
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp', '.tif', '.tiff',
        '.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.mpg', '.mpeg'
    )

    def scan_directory(self, dir_path: str) -> Dict[str, Any]:
        """Scan a directory and return list of files that can be ingested.

        Args:
            dir_path: Directory path to scan

        Returns:
            Dict with status and list of files
        """
        try:
            if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
                return {"status": "error", "message": f"Directory not found: {dir_path}"}

            file_paths: List[str] = []
            skipped_files: List[str] = []

            try:
                entries = os.listdir(dir_path)
            except Exception as e:
                return {"status": "error", "message": f"Failed to list directory {dir_path}: {e}"}

            for name in entries:
                # Skip hidden files
                if name.startswith('.'):
                    continue

                full_path = os.path.join(dir_path, name)

                # Only include regular files in the top-level directory
                if not os.path.isfile(full_path):
                    continue

                # Skip common non-document files
                if name.endswith(('.pyc', '.pyo', '.pyd')):
                    skipped_files.append(name)
                    continue

                # Only include files with allowed extensions
                lower_name = name.lower()
                if not lower_name.endswith(self.ALLOWED_EXTENSIONS):
                    skipped_files.append(name)
                    continue

                file_paths.append(full_path)

            return {
                "status": "success",
                "data": {
                    "files": file_paths,
                    "count": len(file_paths),
                    "skipped": skipped_files,
                    "skipped_count": len(skipped_files)
                }
            }
        except Exception as e:
            err = get_traceback(e, "LightragClient.scan_directory")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def ingest_directory(self, dir_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Request to ingest files in a directory (top-level only, non-recursive).

        Args:
            dir_path: Directory path to scan and ingest
            options: Optional configuration for ingestion

        Returns:
            Dict with status and job information
        """
        try:
            # Use scan_directory to get filtered file list
            scan_result = self.scan_directory(dir_path)
            if scan_result.get("status") == "error":
                return scan_result

            file_paths = scan_result.get("data", {}).get("files", [])
            if not file_paths:
                return {"status": "error", "message": "No files found in directory"}

            # Upload each file individually to ensure the backend processes all of them
            results = []
            success_count = 0
            failure_count = 0

            for path in file_paths:
                try:
                    resp = self.ingest_files([path], options)
                except Exception as e:  # Safety net, though ingest_files already catches
                    err = get_traceback(e, "LightragClient.ingest_directory.single_file")
                    logger.error(err)
                    resp = {"status": "error", "message": str(e)}

                if resp.get("status") == "success":
                    success_count += 1
                else:
                    failure_count += 1

                results.append({
                    "file_path": path,
                    "result": resp,
                })

            overall_status = "success" if success_count and not failure_count else (
                "partial_success" if success_count and failure_count else "error"
            )

            summary = {
                "status": overall_status,
                "total_files": len(file_paths),
                "success_count": success_count,
                "failure_count": failure_count,
                "files": results,
            }

            return {"status": "success", "data": summary}
        except Exception as e:
            err = get_traceback(e, "LightragClient.ingest_directory")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Query ----
    def query(self, text: str, options: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Query the knowledge base.
        
        Args:
            text: Query text
            workspace: Optional LightRAG workspace (tenant) name for data isolation.
                When omitted, the server's default workspace is used.
            options: Optional query parameters including:
                - mode: Query mode (naive, local, global, hybrid, mix, bypass)
                - only_need_context: Return only context
                - only_need_prompt: Return only prompt
                - enable_rerank: Enable reranking
                - top_k: Number of top results
                - chunk_top_k: Number of top chunks
                - max_entity_tokens: Max entity tokens
                - max_relation_tokens: Max relation tokens
                - max_total_tokens: Max total tokens
                - history_turns: Number of history turns
                - response_type: Response type
                - user_prompt: Custom user prompt
                - conversation_history: List of previous messages
                - ids: List of document IDs to search in
                
        Returns:
            Dict with query response
        """
        try:
            if _is_app_shutdown_active():
                logger.warning("[LightragClient] query aborted: app shutdown is active")
                return _shutdown_abort_result(text, workspace)

            payload = {
                "query": text,
                # Always request references + chunk text so the confidence scorer
                # can run faithfulness checks.  Callers can still override via options.
                "include_references": True,
                "include_chunk_content": True,
            }

            # Enforce token caps BEFORE sending to server.  LightRAG respects query-
            # param values over env values, so a caller's max_total_tokens=32768 can
            # exceed the model's deployed context window (8K) and cause vLLM 400 errors.
            # Values are hardcoded here (not read from env) because the client runs in
            # the main process whose env differs from the server subprocess env.
            # These defaults must match the server's _apply_retrieval_token_limits caps.
            # For 8K context models (Qwen3.8-27B-AWQ-INT4):
            #   - MAX_ENTITY_TOKENS:     capped at 2000  (covers ~10 entities with descriptions)
            #   - MAX_RELATION_TOKENS:  capped at 2500  (covers ~15 relations)
            #   - MAX_TOTAL_TOKENS:     capped at 8192  (matches deployed context window)
            _cap_entity = 2000
            _cap_relation = 2500
            _cap_total = 8192

            if options:
                # Map all supported parameters as defined in QueryRequest schema
                for key in [
                    'mode',
                    'only_need_context',
                    'only_need_prompt',
                    'response_type',
                    'top_k',
                    'chunk_top_k',
                    'max_entity_tokens',
                    'max_relation_tokens',
                    'max_total_tokens',
                    'hl_keywords',
                    'll_keywords',
                    'conversation_history',
                    'user_prompt',
                    'enable_rerank',
                    'include_references',
                    'include_chunk_content',
                    'include_progress',
                    'stream',
                ]:
                    if key in options:
                        payload[key] = options[key]

                # Hard cap: client-side options must not exceed server-side limits
                if payload.get('max_entity_tokens', 0) > _cap_entity:
                    payload['max_entity_tokens'] = _cap_entity
                if payload.get('max_relation_tokens', 0) > _cap_relation:
                    payload['max_relation_tokens'] = _cap_relation
                if payload.get('max_total_tokens', 0) > _cap_total:
                    payload['max_total_tokens'] = _cap_total
            
            # Use JSON content type
            headers = _ws_headers(workspace, {'Content-Type': 'application/json'})
            # Default 90s; mix+rerank can exceed 30s for large knowledge bases
            _timeout = timeout or 90
            r = self.session.post(f"{self.base_url}/query", json=payload, headers=headers, timeout=_timeout)

            if r.status_code >= 400:
                # Log full error body to help debug FastAPI validation errors
                logger.error(
                    f"LightragClient.query HTTP error {r.status_code}: {r.text}"
                )

            r.raise_for_status()
            result = r.json()

            # Debug: log what signals are available for confidence scoring
            refs = result.get('references') or []
            chunks = (result.get('data') or {}).get('chunks') or []
            has_chunk_content = any(r.get('content') for r in refs) or any(c.get('content') for c in chunks)
            logger.info(
                f"[Confidence input] refs={len(refs)} chunks={len(chunks)} "
                f"has_chunk_content={has_chunk_content}"
            )

            # Calculate confidence score for the response
            try:
                from knowledge.lightrag_confidence_scorer import score_lightrag_response
                confidence = score_lightrag_response(
                    query=text,
                    response_data=result,
                    query_options=options
                )
                result['confidence'] = confidence
                logger.info(f"Query confidence: {confidence.get('overall_score', 0):.2f} ({confidence.get('confidence_level', 'unknown')})")

                decision = (confidence or {}).get('decision') or {}
                if decision.get('should_answer') is False:
                    no_answer_message = (
                        "未找到足够相关的资料来可靠回答该问题。建议换个问法或上传/导入更多文档后再试。\n"
                        "I couldn't find enough relevant context to answer reliably. Try rephrasing your question or ingest more documents."
                    )
                    result['raw_response'] = result.get('response', '')
                    result['response'] = no_answer_message
                    result['no_answer_message'] = no_answer_message
            except Exception as conf_err:
                logger.warning(f"Failed to calculate confidence score: {conf_err}")
                # Don't fail the request if confidence calculation fails
            
            return {"status": "success", "data": result}
        except Exception as e:
            if _is_app_shutdown_active():
                logger.warning(f"[LightragClient] query aborted during shutdown: {e}")
                return _shutdown_abort_result(text, workspace)
            err = get_traceback(e, "LightragClient.query")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Status / Abort ----
    def track_status(self, track_id: str, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Get status of documents by tracking ID.
        
        Args:
            track_id: Track ID to check (returned from upload/scan operations)
            workspace: Optional LightRAG workspace (tenant) name. Tracks are
                scoped per workspace; use the same value that was passed to
                ``ingest_files`` / ``insert_text``.
            
        Returns:
            Dict with tracking status information including:
            - track_id: The tracking ID
            - documents: List of documents with their status
            - total_count: Total number of documents
            - status_summary: Count of documents by status
        """
        try:
            r = self.session.get(
                f"{self.base_url}/documents/track_status/{track_id}",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            if r.status_code >= 400:
                logger.error(f"Track status failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.track_status HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.track_status")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    # Keep old method name for backward compatibility
    def status(self, job_id: str) -> Dict[str, Any]:
        """Deprecated: Use track_status instead."""
        return self.track_status(job_id)
    
    def cancel_pipeline(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Cancel the currently running document processing pipeline.
        
        This will:
        1. Stop processing new documents
        2. Cancel all running document processing tasks
        3. Mark all PROCESSING documents as FAILED with reason "User cancelled"
        
        The cancellation is graceful and ensures data consistency.
        Documents that have completed processing will remain in PROCESSED status.
        
        Args:
            workspace: Optional LightRAG workspace (tenant) name. Cancellation
                only affects the pipeline of the targeted workspace.
        
        Returns:
            Dict with cancellation status:
            - status="cancellation_requested": Cancellation flag has been set
            - status="not_busy": Pipeline is not currently running
        """
        try:
            logger.info(f"[LightragClient] Requesting pipeline cancellation (workspace={workspace!r})")
            
            r = self.session.post(
                f"{self.base_url}/documents/cancel_pipeline",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            logger.info(f"[LightragClient] Cancel pipeline response status: {r.status_code}")
            
            if r.status_code >= 400:
                logger.error(f"Cancel pipeline failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            logger.info(f"[LightragClient] Pipeline cancellation result: {result}")
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.cancel_pipeline HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.cancel_pipeline")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    def abort_document(self, doc_id: str, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Abort processing of a specific document.
        
        Note: LightRAG doesn't have a per-document abort API.
        This method will cancel the entire pipeline, which will:
        1. Stop all document processing
        2. Mark all PROCESSING documents (including this one) as FAILED
        
        If you only want to stop this specific document, you'll need to:
        - Wait for it to complete, then delete it
        - Or use cancel_pipeline() to stop all processing
        
        Args:
            doc_id: ID of the document to abort
            
        Returns:
            Dict with abort status
        """
        logger.warning(f"[LightragClient] Aborting document {doc_id} by cancelling pipeline (workspace={workspace!r})")
        logger.warning(f"[LightragClient] Note: This will cancel ALL processing documents, not just {doc_id}")
        
        # Cancel the entire pipeline
        result = self.cancel_pipeline(workspace=workspace)
        
        if result.get('status') == 'success':
            logger.info(f"[LightragClient] Pipeline cancelled, document {doc_id} will be marked as FAILED")
        else:
            logger.error(f"[LightragClient] Failed to cancel pipeline for document {doc_id}: {result.get('message')}")
        
        return result

    def scan(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Trigger scanning for new documents in the input directory.
        
        Args:
            workspace: Optional LightRAG workspace (tenant) name. Newly
                discovered documents are ingested into the targeted workspace.
        
        Returns:
            Dict with scan status and track_id for monitoring progress
        """
        try:
            r = self.session.post(
                f"{self.base_url}/documents/scan",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            if r.status_code >= 400:
                logger.error(f"Scan failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            # API returns: {"status": "scanning_started", "message": "...", "track_id": "..."}
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.scan HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.scan")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    def list_documents(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """List all documents with their processing status.
        
        Args:
            workspace: Optional LightRAG workspace (tenant) name. Lists are
                scoped to the targeted workspace; omit for the server default.
        
        Returns:
            Dict with documents grouped by status (PENDING, PROCESSING, PROCESSED, FAILED)
        """
        try:
            r = self.session.get(
                f"{self.base_url}/documents",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            if r.status_code >= 400:
                logger.error(f"List documents failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.list_documents HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.list_documents")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    def delete_document(self, doc_id: str, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Delete a document from the knowledge base by ID.
        
        Args:
            doc_id: ID of the document to delete
            workspace: Optional LightRAG workspace (tenant). Deletion is
                scoped to the document's workspace; pass the same value used
                during ingestion.
            
        Returns:
            Dict with deletion status
        """
        try:
            logger.info(f"[LightragClient] Attempting to delete document: {doc_id} (workspace={workspace!r})")
            
            # Server expects list of doc_ids
            payload = {"doc_ids": [doc_id]}
            # Use request with json body for DELETE
            r = self.session.request(
                "DELETE",
                f"{self.base_url}/documents/delete_document",
                json=payload,
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            logger.info(f"[LightragClient] Delete response status: {r.status_code}")
            
            if r.status_code >= 400:
                error_text = r.text
                logger.error(f"[LightragClient] Delete failed with status {r.status_code}: {error_text}")
                
                # Try to parse error message from response
                try:
                    error_json = r.json()
                    error_detail = error_json.get('detail', error_text)
                    return {"status": "error", "message": f"Cannot delete document: {error_detail}"}
                except:
                    return {"status": "error", "message": f"Cannot delete document (HTTP {r.status_code}): {error_text}"}
                
            r.raise_for_status()
            result = r.json()
            logger.info(f"[LightragClient] Document deleted successfully: {doc_id}")
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"[LightragClient] delete_document HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.delete_document")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    def insert_text(self, text: str, metadata: Optional[Dict[str, Any]] = None, workspace: Optional[str] = None) -> Dict[str, Any]:
        """
        Insert text directly into the knowledge base.
        
        Based on LightRAG API POST /documents/text InsertTextRequest:
        - text: The text content to insert (required, min 1 char)
        - file_source: Source identifier for the text (optional)
        
        Args:
            text: Text content to insert
            metadata: Optional metadata containing file_source
            workspace: Optional LightRAG workspace (tenant) name for data isolation.
                When omitted, the server's default workspace is used.
            
        Returns:
            Response with insertion status and track_id
        """
        # Build payload matching InsertTextRequest schema
        payload = {"text": text.strip()}
        
        # Extract file_source from metadata if provided
        if metadata and "file_source" in metadata:
            payload["file_source"] = metadata["file_source"]
        
        try:
            r = self.session.post(
                f"{self.base_url}/documents/text",
                json=payload,
                timeout=60,
                headers=_ws_headers(workspace),
            )
            
            if r.status_code >= 400:
                logger.error(f"Insert text failed with status {r.status_code}: {r.text}")
                
            r.raise_for_status()
            # API returns: {"status": "success", "message": "...", "track_id": "..."}
            return {"status": "success", "data": r.json()}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.insert_text HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error inserting text: {e}")
            return {"status": "error", "message": str(e)}
    
    def query_stream(self, text: str, options: Optional[Dict[str, Any]] = None, workspace: Optional[str] = None):
        """
        Query the knowledge base with streaming response (SSE).
        
        Args:
            text: Query text
            options: Query options (mode, top_k, etc.)
            workspace: Optional LightRAG workspace (tenant) name for data isolation.
                When omitted, the server's default workspace is used.
            
        Yields:
            Streaming response chunks (including final confidence chunk)
        """
        if _is_app_shutdown_active():
            import json
            logger.warning("[LightragClient] query_stream aborted: app shutdown is active")
            abort_result = _shutdown_abort_result(text, workspace)
            yield json.dumps({
                "status": "aborted",
                "aborted": True,
                "reason": "shutdown",
                "message": abort_result.get("message"),
                "response": abort_result.get("message"),
                "references": [],
            })
            return

        payload = {
            "query": text,
            "include_references": True,
            "include_chunk_content": True,
        }

        # Enforce token caps (same as query method above)
        _cap_entity = 2000
        _cap_relation = 2500
        _cap_total = 8192

        if options:
            # Map all supported parameters as defined in QueryRequest schema
            for key in [
                'mode',
                'only_need_context',
                'only_need_prompt',
                'response_type',
                'top_k',
                'chunk_top_k',
                'max_entity_tokens',
                'max_relation_tokens',
                'max_total_tokens',
                'conversation_history',
                'user_prompt',
                'enable_rerank',
                'include_references',
                'include_chunk_content',
                'include_progress',
                'stream',
            ]:
                if key in options:
                    payload[key] = options[key]

            # Hard cap: client-side options must not exceed server-side limits
            if payload.get('max_entity_tokens', 0) > _cap_entity:
                payload['max_entity_tokens'] = _cap_entity
            if payload.get('max_relation_tokens', 0) > _cap_relation:
                payload['max_relation_tokens'] = _cap_relation
            if payload.get('max_total_tokens', 0) > _cap_total:
                payload['max_total_tokens'] = _cap_total

        # Log query parameters for debugging
        logger.info(f"[Stream Query] Payload: query='{text[:50]}...', mode={payload.get('mode')}, "
                   f"only_need_context={payload.get('only_need_context')}, "
                   f"only_need_prompt={payload.get('only_need_prompt')}, "
                   f"enable_rerank={payload.get('enable_rerank')}, "
                   f"stream={payload.get('stream')}")
        
        headers = _ws_headers(workspace, {
            'Content-Type': 'application/json',
            # LightRAG's /query/stream endpoint uses NDJSON streaming
            'Accept': 'application/x-ndjson',
        })

        # Accumulate response for confidence calculation
        accumulated_response = {'response': '', 'references': [], 'data': {'chunks': []}}
        # LightRAG 1.5 progress events: ``progress`` is an optional string field
        # emitted mid-stream (see docs/lightrag-1.5-upgrade-analysis.md §5).
        # We track the latest phase and the wall-clock time it was observed so
        # the GUI can render the four phases recommended in the upgrade plan
        # (关键词提取 / 图谱检索 / 文本检索 / 生成答案).
        progress_state: Dict[str, Any] = {
            'phase': None,
            'updated_at': None,
        }
        # Performance metrics surfaced as a final ``metrics`` chunk. Captures
        # ``response_time`` (server-reported) and client-side retrieval timing
        # (time-to-first-token, total elapsed) so the GUI can stop relying on
        # local wall-clock heuristics alone.
        stream_started_at = time.monotonic()
        first_token_at: Optional[float] = None
        server_response_time: Optional[float] = None

        try:
            with self.session.post(
                f"{self.base_url}/query/stream",
                json=payload,
                headers=headers,
                stream=True,
                timeout=180
            ) as r:
                if r.status_code >= 400:
                    # Log full error body to help debug FastAPI validation errors
                    logger.error(
                        f"LightragClient.query_stream HTTP error {r.status_code}: {r.text}"
                    )

                r.raise_for_status()
                line_count = 0
                logger.debug(f"[Stream] Starting to read response stream...")
                for line in r.iter_lines():
                    if line:
                        line_count += 1
                        line_str = line.decode('utf-8')
                        # /query/stream returns pure NDJSON lines, no 'data: ' prefix

                        # Accumulate response for confidence calculation
                        try:
                            import json
                            chunk_data = json.loads(line_str)
                            # Debug: log first chunk structure
                            if line_count == 1:
                                logger.info(f"[Stream] First chunk keys: {list(chunk_data.keys())}")
                            if chunk_data.get('error'):
                                raise RuntimeError(str(chunk_data['error']))
                            if 'response' in chunk_data and chunk_data.get('response'):
                                # Reference/progress packets can arrive earlier;
                                # TTFT specifically measures visible answer text.
                                if first_token_at is None:
                                    first_token_at = time.monotonic()
                                response_piece = str(chunk_data['response'])
                                if (
                                    response_piece.strip() == 'No relevant context found for the query.'
                                    and accumulated_response.get('references')
                                ):
                                    raise RuntimeError(
                                        '检索已命中文档，但答案生成失败。请检查 LLM 服务日志和模型上下文限制。'
                                    )
                                accumulated_response['response'] += response_piece
                                # Yield immediately for streaming animation
                                yield line_str
                            elif 'references' in chunk_data or 'data' in chunk_data:
                                # LightRAG's stream already carries references;
                                # forward them directly instead of issuing a duplicate
                                # non-streaming LLM query just to pre-fetch citations.
                                yield line_str
                            else:
                                # Yield other chunks (progress, metrics, etc.) as-is
                                yield line_str

                            # Fix: accumulate references from all chunks, don't overwrite
                            if 'references' in chunk_data:
                                incoming_refs = chunk_data.get('references', [])
                                if incoming_refs:
                                    if 'references' not in accumulated_response:
                                        accumulated_response['references'] = []
                                    # Extend instead of overwrite to capture all references
                                    accumulated_response['references'].extend(incoming_refs)
                            if 'data' in chunk_data and isinstance(chunk_data['data'], dict):
                                # Merge data.chunks if present
                                incoming_data = chunk_data['data']
                                if 'chunks' in incoming_data and incoming_data['chunks']:
                                    if 'data' not in accumulated_response:
                                        accumulated_response['data'] = {'chunks': []}
                                    if 'chunks' not in accumulated_response['data']:
                                        accumulated_response['data']['chunks'] = []
                                    accumulated_response['data']['chunks'].extend(incoming_data['chunks'])
                            # 1.5 progress tracking. ``progress`` is the
                            # streaming phase string. Older payloads won't
                            # have it; we just skip silently.
                            if 'progress' in chunk_data and chunk_data['progress']:
                                progress_state['phase'] = chunk_data['progress']
                                progress_state['updated_at'] = time.monotonic()
                            if 'response_time' in chunk_data and isinstance(
                                chunk_data['response_time'], (int, float)
                            ):
                                server_response_time = float(chunk_data['response_time'])
                        except json.JSONDecodeError:
                            accumulated_response['response'] += line_str
                            # Yield raw line for streaming
                            yield line_str

                logger.debug(f"[Stream] Finished reading stream, total chunks: {line_count}")

                # Emit a final ``metrics`` chunk so consumers can read timing
                # without re-parsing every NDJSON line. The keys are stable;
                # any of them may be ``None`` if the server didn't report them.
                # The ``import json`` is duplicated locally so it survives the
                # case where the upstream returned zero NDJSON lines (the only
                # other place it's imported lives inside the ``for`` loop and
                # therefore may never have run).
                try:
                    import json
                    stream_ended_at = time.monotonic()
                    elapsed_ms = (stream_ended_at - stream_started_at) * 1000.0
                    time_to_first_token_ms = (
                        (first_token_at - stream_started_at) * 1000.0
                        if first_token_at is not None
                        else None
                    )
                    metrics = {
                        'metrics': {
                            'response_time': server_response_time,
                            'elapsed_ms': elapsed_ms,
                            'time_to_first_token_ms': time_to_first_token_ms,
                            'progress_phase': progress_state['phase'],
                        }
                    }
                    yield json.dumps(metrics)
                except Exception as metrics_err:
                    logger.debug(f"[Stream] metrics chunk skipped: {metrics_err}")

                # Log stream statistics
                logger.info(
                    f"📊 Stream completed: {line_count} lines, "
                    f"response_length={len(accumulated_response['response'])}, "
                    f"references_count={len(accumulated_response.get('references', []))}, "
                    f"progress_phase={progress_state['phase']}, "
                    f"server_response_time={server_response_time}"
                )
                
                # Calculate and yield confidence as final chunk
                # Fix v2: use accumulated_response which now has proper references and chunks
                try:
                    from knowledge.lightrag_confidence_scorer import score_lightrag_response

                    # Log what we have for debugging
                    refs_count = len(accumulated_response.get('references', []))
                    chunks_count = len((accumulated_response.get('data') or {}).get('chunks', []))
                    resp_len = len(accumulated_response.get('response', ''))
                    logger.info(f"[Confidence v2] refs={refs_count}, chunks={chunks_count}, response_len={resp_len}")

                    confidence = score_lightrag_response(
                        query=text,
                        response_data=accumulated_response,
                        query_options=options
                    )

                    decision = (confidence or {}).get('decision') or {}
                    should_answer = decision.get('should_answer', True)

                    logger.info(f"Stream query confidence v2: {confidence.get('overall_score', 0):.2f} ({confidence.get('confidence_level', 'unknown')}), should_answer={should_answer}")

                    # 修复：即使置信度低，如果 should_answer=True 也显示 LLM 的回答
                    # 置信度分数只用于提示，不阻止显示
                    response_text = accumulated_response.get('response', '')
                    if should_answer:
                        # 不再重复 yield references，避免前端去重问题
                        yield json.dumps({'response': response_text, 'confidence': confidence})
                    else:
                        no_answer_message = (
                            "未找到足够相关的资料来可靠回答该问题。建议换个问法或上传/导入更多文档后再试。\n"
                            "I couldn't find enough relevant context to answer reliably. Try rephrasing your question or ingest more documents."
                        )
                        yield json.dumps({'response': no_answer_message, 'confidence': confidence})
                except Exception as conf_err:
                    logger.warning(f"Failed to calculate confidence score for stream: {conf_err}")
                    
        except requests.exceptions.RequestException as e:
            if _is_app_shutdown_active():
                import json
                logger.warning(f"[LightragClient] stream query aborted during shutdown: {e}")
                abort_result = _shutdown_abort_result(text, workspace)
                yield json.dumps({
                    "status": "aborted",
                    "aborted": True,
                    "reason": "shutdown",
                    "message": abort_result.get("message"),
                    "response": abort_result.get("message"),
                    "references": [],
                })
                return
            logger.error(f"Error in stream query: {e}")
            raise
    
    def clear_cache(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear LightRAG cache.
        
        Args:
            workspace: Optional LightRAG workspace (tenant) name. Cache
                clearing is scoped to the targeted workspace.
        
        Returns:
            Response with clear status
        """
        try:
            # Send empty json to satisfy potential pydantic validation
            r = self.session.post(
                f"{self.base_url}/documents/clear_cache",
                json={},
                headers=_ws_headers(workspace),
                timeout=30,
            )
            
            if r.status_code >= 400:
                logger.error(f"Clear cache failed with status {r.status_code}: {r.text}")
                
            r.raise_for_status()
            return {"status": "success", "data": r.json()}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.clear_cache HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error clearing cache: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_status_counts(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """
        Get document status counts.
        
        Args:
            workspace: Optional LightRAG workspace (tenant) name. Counts are
                scoped to the targeted workspace.
        
        Returns:
            Response with status counts
        """
        try:
            r = self.session.get(
                f"{self.base_url}/documents/status_counts",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            if r.status_code >= 400:
                logger.error(f"Get status counts failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            return {"status": "success", "data": r.json()}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.get_status_counts HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting status counts: {e}")
            return {"status": "error", "message": str(e)}

    # ---- Graph Editing ----
    def update_entity(self, entity_name: str, updated_data: Dict[str, Any], allow_rename: bool = False, allow_merge: bool = False) -> Dict[str, Any]:
        """Update an entity's properties in the knowledge graph."""
        try:
            payload = {
                "entity_name": entity_name,
                "updated_data": updated_data,
                "allow_rename": allow_rename,
                "allow_merge": allow_merge
            }
            r = self.session.post(f"{self.base_url}/graph/entity/edit", json=payload, timeout=30)
            
            if r.status_code >= 400:
                logger.error(f"Update entity failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.update_entity HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.update_entity")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def check_entity_name_exists(self, name: str) -> Dict[str, Any]:
        """Check if an entity name already exists in the knowledge graph."""
        try:
            r = self.session.get(
                f"{self.base_url}/graph/entity/exists",
                params={"name": name},
                timeout=10
            )
            
            if r.status_code >= 400:
                logger.error(f"Check entity name exists failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.check_entity_name_exists HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.check_entity_name_exists")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def update_relation(self, source_id: str, target_id: str, updated_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a relation's properties in the knowledge graph."""
        try:
            payload = {
                "source_id": source_id,
                "target_id": target_id,
                "updated_data": updated_data
            }
            r = self.session.post(f"{self.base_url}/graph/relation/edit", json=payload, timeout=30)
            
            if r.status_code >= 400:
                logger.error(f"Update relation failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.update_relation HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.update_relation")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def get_graph_label_list(self) -> Dict[str, Any]:
        """Get list of all labels in the graph."""
        try:
            r = self.session.get(f"{self.base_url}/graph/label/list", timeout=10)
            
            if r.status_code >= 400:
                logger.error(f"Get graph label list failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.get_graph_label_list HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_graph_label_list")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def get_pipeline_status(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Get the current status of the document indexing pipeline.
        
        Returns information about:
        - busy: Whether the pipeline is currently busy
        - job_name: Current job name (e.g., indexing files/indexing texts)
        - docs: Total number of documents to be indexed
        - batchs: Number of batches for processing documents
        - cur_batch: Current processing batch
        - latest_message: Latest message from pipeline processing
        """
        try:
            r = self.session.get(
                f"{self.base_url}/documents/pipeline_status",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            
            if r.status_code >= 400:
                logger.error(f"Get pipeline status failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.get_pipeline_status HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_pipeline_status")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def get_supported_file_types(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Return LightRAG's live upload allowlist and parser capabilities.

        Backed by a 5 minute module-level TTL cache so the GUI doesn't hit
        the server on every UI render. Cache key is ``(base_url, workspace)``
        so multi-tenant setups don't poison each other. Call
        :func:`clear_supported_file_types_cache` to force a refresh.
        """
        cache_key = (self.base_url, workspace)
        cached = _SUPPORTED_FILE_TYPES_CACHE.get(cache_key)
        now = time.monotonic()
        if cached is not None:
            payload, fetched_at = cached
            if (now - fetched_at) < _SUPPORTED_FILE_TYPES_TTL_SECONDS:
                return {"status": "success", "data": payload, "cached": True}

        try:
            r = self.session.get(
                f"{self.base_url}/documents/supported_file_types",
                headers=_ws_headers(workspace),
                timeout=10,
            )
            r.raise_for_status()
            payload = r.json()
            _SUPPORTED_FILE_TYPES_CACHE[cache_key] = (payload, now)
            return {"status": "success", "data": payload}
        except requests.exceptions.HTTPError as e:
            error_msg = (
                f"HTTP Error {e.response.status_code}: {e.response.text}"
                if e.response
                else str(e)
            )
            logger.error(f"LightragClient.get_supported_file_types HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_supported_file_types")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def get_popular_labels(self, limit: int = 300) -> Dict[str, Any]:
        """Get popular labels by node degree."""
        try:
            params = {"limit": limit}
            r = self.session.get(f"{self.base_url}/graph/label/popular", params=params, timeout=10)
            
            if r.status_code >= 400:
                logger.error(f"Get popular labels failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.get_popular_labels HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_popular_labels")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def search_labels(self, q: str, limit: int = 50) -> Dict[str, Any]:
        """Search labels with fuzzy matching."""
        try:
            params = {"q": q, "limit": limit}
            r = self.session.get(f"{self.base_url}/graph/label/search", params=params, timeout=10)
            
            if r.status_code >= 400:
                logger.error(f"Search labels failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.search_labels HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.search_labels")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def query_graphs(self, label: str, max_depth: int, max_nodes: int) -> Dict[str, Any]:
        """Query graph nodes and edges via GET /graphs.

        This aligns with LightRAG's OpenAPI where:
          - endpoint: GET /graphs
          - params: label (str, required), max_depth (int), max_nodes (int)
        """
        try:
            params = {
                "label": label,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
            }
            r = self.session.get(f"{self.base_url}/graphs", params=params, timeout=60)
            
            if r.status_code >= 400:
                logger.error(f"Query graphs failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.query_graphs HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.query_graphs")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Document Pagination ----
    def get_documents_paginated(self, params: Dict[str, Any], workspace: Optional[str] = None) -> Dict[str, Any]:
        """Get documents with pagination.
        
        Args:
            params: Pagination request body (page, page_size, status_filter, etc.)
            workspace: Optional LightRAG workspace (tenant) name. Pagination
                results are scoped to the targeted workspace.
        """
        try:
            logger.info(f"[LightragClient] get_documents_paginated called with params: {params} (workspace={workspace!r})")
            logger.info(f"[LightragClient] Calling LightRAG API: POST {self.base_url}/documents/paginated")
            
            # The settings page reloads this list immediately after requesting
            # a LightRAG restart. There is a short window after the old process
            # exits and before the new one binds the port. Absorb that expected
            # startup race here instead of returning a noisy GraphQL error.
            for attempt in range(4):
                try:
                    r = self.session.post(
                        f"{self.base_url}/documents/paginated",
                        json=params,
                        headers=_ws_headers(workspace),
                        timeout=30,
                    )
                    break
                except requests.exceptions.ConnectionError:
                    if attempt == 3:
                        raise
                    logger.debug(
                        "[LightragClient] Server is restarting; retrying document "
                        f"list request ({attempt + 1}/3)"
                    )
                    time.sleep(0.5)
            
            logger.info(f"[LightragClient] LightRAG API response status: {r.status_code}")
            
            if r.status_code >= 400:
                logger.error(f"Get documents paginated failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            
            logger.info(f"[LightragClient] LightRAG API returned data: {result}")
            logger.info(f"[LightragClient] Documents count: {len(result.get('documents', []))}")
            
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.get_documents_paginated HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except requests.exceptions.ConnectionError as e:
            # All 3 retries exhausted — server is genuinely down, not just
            # restarting. The handler/registry will still surface the error
            # to the frontend (so DocumentsTab can show "Waiting for
            # LightRAG server…"), but we MUST NOT log a full traceback for
            # an expected transient condition. Same pattern as
            # get_status_counts / get_processing_progress handlers.
            logger.debug(f"[LightragClient] get_documents_paginated: server not ready: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_documents_paginated")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def replace_document(
        self,
        file_path: str,
        workspace: Optional[str] = None,
        match_basename: bool = True,
    ) -> Dict[str, Any]:
        """Re-ingest a file, replacing any existing copies in the workspace.

        Workflow (see also ``ota/docs`` style note in the chat thread):

        1. List existing documents in the targeted workspace via the
           paginated endpoint.
        2. Find every doc whose stored ``file_path`` matches the new
           file's basename (case-insensitive on Windows-friendly paths).
        3. Delete each match (LightRAG's delete is async; we don't
           block on completion — the new ingest creates a fresh doc id
           with a new content hash, so there's no conflict).
        4. Re-ingest the file via the regular upload endpoint.

        Args:
            file_path: Local path to the *new* version of the file.
            workspace: Optional workspace (tenant). Both lookup and
                delete are scoped to it.
            match_basename: When True (default), match by filename only.
                Set False to require an exact ``file_path`` string match
                instead — useful if the workspace stores absolute paths
                and you want to be conservative.

        Returns:
            ``{"status": "success", "data": {...}}`` on success, where
            data contains ``deleted_ids`` (list of doc ids that were
            asked to delete), ``deleted_count``, ``ingest`` (the upload
            response), and ``matched_basename``. ``{"status": "error",
            ...}`` on any failure that prevents re-ingestion.
        """
        try:
            if not file_path or not os.path.exists(file_path):
                return {
                    "status": "error",
                    "message": f"File not found: {file_path}",
                }

            target_name = os.path.basename(file_path)
            target_norm = target_name.lower()

            # 1. Look up existing docs. Use a generous page size; if the
            #    workspace has more than this many docs we'll only see
            #    the first page, but that's the same behavior as the GUI
            #    grid the user is looking at, so it stays consistent.
            list_resp = self.get_documents_paginated(
                {
                    "page": 1,
                    "page_size": 1000,
                    "sort_field": "updated_at",
                    "sort_direction": "desc",
                },
                workspace=workspace,
            )
            if list_resp.get("status") != "success":
                return {
                    "status": "error",
                    "message": (
                        "Failed to list existing documents before replace: "
                        f"{list_resp.get('message')}"
                    ),
                }
            documents = (list_resp.get("data") or {}).get("documents") or []

            # 2. Find matches.
            matches: List[Dict[str, Any]] = []
            for doc in documents:
                doc_path = (doc.get("file_path") or "").strip()
                if not doc_path:
                    continue
                if match_basename:
                    if os.path.basename(doc_path).lower() == target_norm:
                        matches.append(doc)
                else:
                    if doc_path == file_path:
                        matches.append(doc)

            logger.info(
                f"[LightragClient.replace_document] target={target_name!r} "
                f"workspace={workspace!r} found {len(matches)} existing match(es)"
            )

            # 3. Delete each match. We log + collect failures but keep
            #    going — a partial cleanup is still better than no
            #    cleanup, and the new ingest below is independent.
            deleted_ids: List[str] = []
            delete_errors: List[Dict[str, Any]] = []
            for doc in matches:
                doc_id = doc.get("id")
                if not doc_id:
                    continue
                del_resp = self.delete_document(doc_id, workspace=workspace)
                if del_resp.get("status") == "success":
                    deleted_ids.append(doc_id)
                else:
                    delete_errors.append(
                        {"id": doc_id, "message": del_resp.get("message")}
                    )

            # 4. Re-ingest the new version.
            ingest_resp = self.ingest_files([file_path], workspace=workspace)
            if ingest_resp.get("status") != "success":
                return {
                    "status": "error",
                    "message": (
                        "Re-ingest failed after deleting "
                        f"{len(deleted_ids)} old copies: "
                        f"{ingest_resp.get('message')}"
                    ),
                    "data": {
                        "deleted_ids": deleted_ids,
                        "deleted_count": len(deleted_ids),
                        "delete_errors": delete_errors,
                    },
                }

            return {
                "status": "success",
                "data": {
                    "matched_basename": target_name,
                    "deleted_ids": deleted_ids,
                    "deleted_count": len(deleted_ids),
                    "delete_errors": delete_errors,
                    "ingest": ingest_resp.get("data"),
                },
            }
        except Exception as e:
            err = get_traceback(e, "LightragClient.replace_document")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def get_document_download_url(self, file_path: str) -> str:
        """Get the download URL for a document.
        
        Args:
            file_path: The file path/name of the document
            
        Returns:
            str: The download URL for the document
        """
        # URL encode the file path to handle special characters
        from urllib.parse import quote
        encoded_path = quote(file_path, safe='')
        return f"{self.base_url}/documents/download/{encoded_path}"


# Convenience factory
def get_client(api_key: Optional[str] = None, token: Optional[str] = None) -> LightragClient:
    return LightragClient(api_key=api_key, token=token)


# ============================================================================
# Cached capability discovery (LightRAG 1.5 §4 of upgrade analysis).
# ============================================================================
# Module-level TTL cache so the GUI doesn't hit ``/documents/supported_file_types``
# on every render.  Five minutes is a deliberately conservative budget — the
# parser matrix rarely changes between releases, and the cost of a stale list
# is just a slightly out-of-date "supported" hint in the upload widget.  See
# ``clear_supported_file_types_cache`` for forced refresh on test setups and
# after a hot-reload of upstream config.
_SUPPORTED_FILE_TYPES_TTL_SECONDS = 300.0
_SUPPORTED_FILE_TYPES_CACHE: Dict[tuple, tuple] = {}


def clear_supported_file_types_cache() -> None:
    """Drop every cached ``/documents/supported_file_types`` response."""
    _SUPPORTED_FILE_TYPES_CACHE.clear()
