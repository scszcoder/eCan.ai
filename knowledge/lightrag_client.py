import os
from typing import Any, Dict, List, Optional

import requests

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback


def _resolve_base_url() -> str:
    """Resolve LightRAG server base URL from environment or defaults."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "9621")
    scheme = "http"
    return f"{scheme}://{host}:{port}"


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
    def ingest_files(self, paths: List[str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Request to vectorize and store files into the vector DB.
        
        Args:
            paths: List of file paths to ingest
            options: Optional configuration for ingestion
            
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
            r = self.session.post(
                f"{self.base_url}/documents/upload", 
                files=files, 
                timeout=300,
                headers={"Content-Type": None}
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
    def query(self, text: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query the knowledge base.
        
        Args:
            text: Query text
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
            payload = {"query": text}
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
                    'stream',
                ]:
                    if key in options:
                        payload[key] = options[key]
            
            # Use JSON content type
            headers = {'Content-Type': 'application/json'}
            r = self.session.post(f"{self.base_url}/query", json=payload, headers=headers, timeout=180)

            if r.status_code >= 400:
                # Log full error body to help debug FastAPI validation errors
                logger.error(
                    f"LightragClient.query HTTP error {r.status_code}: {r.text}"
                )

            r.raise_for_status()
            result = r.json()
            
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
            err = get_traceback(e, "LightragClient.query")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Status / Abort ----
    def track_status(self, track_id: str) -> Dict[str, Any]:
        """Get status of documents by tracking ID.
        
        Args:
            track_id: Track ID to check (returned from upload/scan operations)
            
        Returns:
            Dict with tracking status information including:
            - track_id: The tracking ID
            - documents: List of documents with their status
            - total_count: Total number of documents
            - status_summary: Count of documents by status
        """
        try:
            r = self.session.get(f"{self.base_url}/documents/track_status/{track_id}", timeout=10)
            
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
    
    def cancel_pipeline(self) -> Dict[str, Any]:
        """Cancel the currently running document processing pipeline.
        
        This will:
        1. Stop processing new documents
        2. Cancel all running document processing tasks
        3. Mark all PROCESSING documents as FAILED with reason "User cancelled"
        
        The cancellation is graceful and ensures data consistency.
        Documents that have completed processing will remain in PROCESSED status.
        
        Returns:
            Dict with cancellation status:
            - status="cancellation_requested": Cancellation flag has been set
            - status="not_busy": Pipeline is not currently running
        """
        try:
            logger.info(f"[LightragClient] Requesting pipeline cancellation")
            
            r = self.session.post(f"{self.base_url}/documents/cancel_pipeline", timeout=10)
            
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
    
    def abort_document(self, doc_id: str) -> Dict[str, Any]:
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
        logger.warning(f"[LightragClient] Aborting document {doc_id} by cancelling pipeline")
        logger.warning(f"[LightragClient] Note: This will cancel ALL processing documents, not just {doc_id}")
        
        # Cancel the entire pipeline
        result = self.cancel_pipeline()
        
        if result.get('status') == 'success':
            logger.info(f"[LightragClient] Pipeline cancelled, document {doc_id} will be marked as FAILED")
        else:
            logger.error(f"[LightragClient] Failed to cancel pipeline for document {doc_id}: {result.get('message')}")
        
        return result

    def scan(self) -> Dict[str, Any]:
        """Trigger scanning for new documents in the input directory.
        
        Returns:
            Dict with scan status and track_id for monitoring progress
        """
        try:
            r = self.session.post(f"{self.base_url}/documents/scan", timeout=10)
            
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
    
    def list_documents(self) -> Dict[str, Any]:
        """List all documents with their processing status.
        
        Returns:
            Dict with documents grouped by status (PENDING, PROCESSING, PROCESSED, FAILED)
        """
        try:
            r = self.session.get(f"{self.base_url}/documents", timeout=10)
            
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
    
    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Delete a document from the knowledge base by ID.
        
        Args:
            doc_id: ID of the document to delete
            
        Returns:
            Dict with deletion status
        """
        try:
            logger.info(f"[LightragClient] Attempting to delete document: {doc_id}")
            
            # Server expects list of doc_ids
            payload = {"doc_ids": [doc_id]}
            # Use request with json body for DELETE
            r = self.session.request("DELETE", f"{self.base_url}/documents/delete_document", json=payload, timeout=10)
            
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
    
    def insert_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Insert text directly into the knowledge base.
        
        Based on LightRAG API POST /documents/text InsertTextRequest:
        - text: The text content to insert (required, min 1 char)
        - file_source: Source identifier for the text (optional)
        
        Args:
            text: Text content to insert
            metadata: Optional metadata containing file_source
            
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
                timeout=60
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
    
    def query_stream(self, text: str, options: Optional[Dict[str, Any]] = None):
        """
        Query the knowledge base with streaming response (SSE).
        
        Args:
            text: Query text
            options: Query options (mode, top_k, etc.)
            
        Yields:
            Streaming response chunks (including final confidence chunk)
        """
        payload = {"query": text}
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
                'stream',
            ]:
                if key in options:
                    payload[key] = options[key]
        
        headers = {
            'Content-Type': 'application/json',
            # LightRAG's /query/stream endpoint uses NDJSON streaming
            'Accept': 'application/x-ndjson',
        }
        
        # Accumulate response for confidence calculation
        accumulated_response = {'response': '', 'references': []}
        
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
                for line in r.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        # /query/stream returns pure NDJSON lines, no 'data: ' prefix
                        yield line_str
                        
                        # Accumulate response for confidence calculation
                        try:
                            import json
                            chunk_data = json.loads(line_str)
                            if 'response' in chunk_data:
                                accumulated_response['response'] += chunk_data.get('response', '')
                            if 'references' in chunk_data:
                                accumulated_response['references'] = chunk_data.get('references', [])
                        except json.JSONDecodeError:
                            accumulated_response['response'] += line_str
                
                # Calculate and yield confidence as final chunk
                try:
                    from knowledge.lightrag_confidence_scorer import score_lightrag_response
                    confidence = score_lightrag_response(
                        query=text,
                        response_data=accumulated_response,
                        query_options=options
                    )
                    logger.info(f"Stream query confidence: {confidence.get('overall_score', 0):.2f} ({confidence.get('confidence_level', 'unknown')})")
                    decision = (confidence or {}).get('decision') or {}
                    if decision.get('should_answer') is False:
                        no_answer_message = (
                            "未找到足够相关的资料来可靠回答该问题。建议换个问法或上传/导入更多文档后再试。\n"
                            "I couldn't find enough relevant context to answer reliably. Try rephrasing your question or ingest more documents."
                        )
                        import json
                        yield json.dumps({'confidence': confidence, 'no_answer_message': no_answer_message})
                    else:
                        # Yield confidence as final JSON chunk
                        import json
                        yield json.dumps({'confidence': confidence})
                except Exception as conf_err:
                    logger.warning(f"Failed to calculate confidence score for stream: {conf_err}")
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in stream query: {e}")
            raise
    
    def clear_cache(self) -> Dict[str, Any]:
        """
        Clear LightRAG cache.
        
        Returns:
            Response with clear status
        """
        try:
            # Send empty json to satisfy potential pydantic validation
            r = self.session.post(
                f"{self.base_url}/documents/clear_cache",
                json={},
                timeout=30
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
    
    def get_status_counts(self) -> Dict[str, Any]:
        """
        Get document status counts.
        
        Returns:
            Response with status counts
        """
        try:
            r = self.session.get(
                f"{self.base_url}/documents/status_counts",
                timeout=10
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

    def get_pipeline_status(self) -> Dict[str, Any]:
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
            r = self.session.get(f"{self.base_url}/documents/pipeline_status", timeout=10)
            
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
    def get_documents_paginated(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get documents with pagination."""
        try:
            logger.info(f"[LightragClient] get_documents_paginated called with params: {params}")
            logger.info(f"[LightragClient] Calling LightRAG API: POST {self.base_url}/documents/paginated")
            
            r = self.session.post(f"{self.base_url}/documents/paginated", json=params, timeout=30)
            
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
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_documents_paginated")
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