import os
import json
import time
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
            r.raise_for_status()
            return r.json()
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
                    files.append(('files', (os.path.basename(path), open(path, 'rb'))))
                except Exception as e:
                    logger.error(f"Failed to open file {path}: {e}")
                    continue
            
            if not files:
                return {"status": "error", "message": "No valid files to ingest"}
            
            # Send files to the server using the correct endpoint
            # Note: options are not supported in multipart upload, they should be query params if needed
            r = self.session.post(f"{self.base_url}/documents/upload", files=files, timeout=300)
            r.raise_for_status()
            
            # Close file handles
            for _, (_, file_handle) in files:
                file_handle.close()
            
            result = r.json()
            # API returns: {"status": "success", "message": "...", "track_id": "..."}
            return {"status": "success", "data": result}
        except Exception as e:
            err = get_traceback(e, "LightragClient.ingest_files")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def ingest_directory(self, dir_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Request to ingest all files in a directory.
        
        Args:
            dir_path: Directory path to scan and ingest
            options: Optional configuration for ingestion
            
        Returns:
            Dict with status and job information
        """
        try:
            if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
                return {"status": "error", "message": f"Directory not found: {dir_path}"}
            
            # Collect all files in the directory
            file_paths = []
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    # Skip hidden files and common non-document files
                    if not file.startswith('.') and not file.endswith(('.pyc', '.pyo', '.pyd')):
                        file_paths.append(os.path.join(root, file))
            
            if not file_paths:
                return {"status": "error", "message": "No files found in directory"}
            
            # Use ingest_files to process all files
            return self.ingest_files(file_paths, options)
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
                # Map all supported parameters
                for key in ['mode', 'only_need_context', 'only_need_prompt', 'response_type',
                           'top_k', 'chunk_top_k', 'max_entity_tokens', 'max_relation_tokens',
                           'max_total_tokens', 'conversation_history', 'history_turns', 'ids',
                           'user_prompt', 'enable_rerank']:
                    if key in options:
                        payload[key] = options[key]
            
            # Use JSON content type
            headers = {'Content-Type': 'application/json'}
            r = self.session.post(f"{self.base_url}/query", json=payload, headers=headers, timeout=180)
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
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
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
            r.raise_for_status()
            result = r.json()
            # API returns: {"status": "scanning_started", "message": "...", "track_id": "..."}
            return {"status": "success", "data": result}
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
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
        except Exception as e:
            err = get_traceback(e, "LightragClient.list_documents")
            logger.error(err)
            return {"status": "error", "message": str(e)}
    
    def delete_document(self, file_path: str) -> Dict[str, Any]:
        """Delete a document from the knowledge base.
        
        Args:
            file_path: Path of the document to delete
            
        Returns:
            Dict with deletion status
        """
        try:
            payload = {"file_path": file_path}
            r = self.session.delete(f"{self.base_url}/documents/delete_document", json=payload, timeout=10)
            r.raise_for_status()
            result = r.json()
            return {"status": "success", "data": result}
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
            # Map all query parameters
            for key in ['mode', 'only_need_context', 'only_need_prompt', 'response_type',
                       'top_k', 'chunk_top_k', 'max_entity_tokens', 'max_relation_tokens',
                       'max_total_tokens', 'conversation_history', 'history_turns', 'ids',
                       'user_prompt', 'enable_rerank']:
                if key in options:
                    payload[key] = options[key]
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        }
        
        try:
            with self.session.post(
                f"{self.base_url}/query/stream",
                json=payload,
                headers=headers,
                stream=True,
                timeout=180
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            yield line_str[6:]  # Remove 'data: ' prefix
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
            r = self.session.post(
                f"{self.base_url}/documents/clear_cache",
                timeout=30
            )
            r.raise_for_status()
            return {"status": "success", "data": r.json()}
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
            r.raise_for_status()
            return {"status": "success", "data": r.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting status counts: {e}")
            return {"status": "error", "message": str(e)}


# Convenience factory
def get_client(api_key: Optional[str] = None, token: Optional[str] = None) -> LightragClient:
    return LightragClient(api_key=api_key, token=token)