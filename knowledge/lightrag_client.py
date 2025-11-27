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
    """Backend adapter to proxy LightRAG WebGUI API calls from frontend IPC.

    NOTE: This is a skeleton. Fill in implementations to call the real LightRAG
    endpoints and translate responses as needed.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or _resolve_base_url()
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })
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

    def ingest_directory(self, dir_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Request to ingest files in a directory (top-level only, non-recursive).

        Args:
            dir_path: Directory path to scan and ingest
            options: Optional configuration for ingestion

        Returns:
            Dict with status and job information
        """
        try:
            if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
                return {"status": "error", "message": f"Directory not found: {dir_path}"}

            # Collect files in the top-level directory only (non-recursive)
            file_paths: List[str] = []

            # Allowed knowledge document types for RAG ingestion
            # - PDF
            # - Office docs: DOC/DOCX/PPT/PPTX/XLS/XLSX
            # - Text/Markdown/HTML/CSV/JSON
            # - Common image formats
            # - Common video formats
            allowed_extensions = (
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
            try:
                entries = os.listdir(dir_path)
            except Exception as e:
                return {"status": "error", "message": f"Failed to list directory {dir_path}: {e}"}

            for name in entries:
                # Skip hidden files
                if name.startswith('.'):
                    continue

                full_path = os.path.join(dir_path, name)

                # Only ingest regular files in the top-level directory
                if not os.path.isfile(full_path):
                    continue

                # Skip common non-document files we never want to ingest
                if name.endswith(('.pyc', '.pyo', '.pyd')):
                    continue

                # Only ingest files with allowed knowledge document extensions
                lower_name = name.lower()
                if not lower_name.endswith(allowed_extensions):
                    logger.debug(f"[LightragClient] Skipping non-knowledge file in directory ingest: {full_path}")
                    continue

                file_paths.append(full_path)

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
                    'conversation_history',
                    'user_prompt',
                    'enable_rerank',
                    'include_references',
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
            # Server expects list of doc_ids
            payload = {"doc_ids": [doc_id]}
            # Use request with json body for DELETE
            r = self.session.request("DELETE", f"{self.base_url}/documents/delete_document", json=payload, timeout=10)
            
            if r.status_code >= 400:
                logger.error(f"Delete failed with status {r.status_code}: {r.text}")
                
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.delete_document HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.delete_document")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    def insert_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Insert text directly into the knowledge base.
        
        Args:
            text: Text content to insert
            metadata: Optional metadata for the text
            
        Returns:
            Response with insertion status
        """
        payload = {"text": text}
        if metadata:
            payload["metadata"] = metadata
        
        try:
            r = self.session.post(
                f"{self.base_url}/documents/text",
                json=payload,
                timeout=60
            )
            r.raise_for_status()
            return {"status": "success", "data": r.json()}
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
            Streaming response chunks
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
            r = self.session.post(f"{self.base_url}/documents/paginated", json=params, timeout=30)
            
            if r.status_code >= 400:
                logger.error(f"Get documents paginated failed with status {r.status_code}: {r.text}")
            
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}: {e.response.text}" if e.response else str(e)
            logger.error(f"LightragClient.get_documents_paginated HTTP error: {error_msg}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            err = get_traceback(e, "LightragClient.get_documents_paginated")
            logger.error(err)
            return {"status": "error", "message": str(e)}


# Convenience factory
def get_client(api_key: Optional[str] = None, token: Optional[str] = None) -> LightragClient:
    return LightragClient(api_key=api_key, token=token)