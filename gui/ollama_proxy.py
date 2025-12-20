"""
Ollama Proxy Module

Provides proxy services for Ollama models to support standard APIs:
- Rerank API: Translates Aliyun/Jina/Cohere format to Ollama's rerank format
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
import httpx
import numpy as np
from starlette.responses import JSONResponse

from utils.logger_helper import logger_helper as logger


class OllamaRerankProxy:
    """
    Ollama Rerank Proxy - Translates standard Rerank APIs to Ollama format.
    
    Architecture:
    1. LightRAG calls with Aliyun/Jina/Cohere format
    2. Proxy translates to Ollama's format: "Query: xxx\nDocument: xxx"
    3. Calls Ollama's /api/embed API with formatted prompts
    4. Returns results in the original format
    
    Supports concurrent document processing for optimal performance.
    """
    
    def __init__(self):
        """Initialize the proxy"""
        self._rerank_manager = None
    
    def _get_rerank_manager(self):
        """Lazy load rerank manager to avoid circular imports"""
        if self._rerank_manager is None:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if main_window:
                self._rerank_manager = main_window.config_manager.rerank_manager
        return self._rerank_manager
    
    def _get_ollama_host_from_config(self) -> Optional[str]:
        """
        Get Ollama host from rerank provider configuration.
        
        Returns:
            Ollama host URL if configured, None otherwise
        """
        try:
            rerank_manager = self._get_rerank_manager()
            if not rerank_manager:
                return None
            
            # Get all providers
            providers = rerank_manager.get_all_providers()
            
            # Find Ollama provider
            for provider in providers:
                if provider.get('provider', '').lower() == 'ollama':
                    base_url = provider.get('base_url')
                    if base_url:
                        logger.debug(f"[Ollama Rerank Proxy] Using ollama_host from provider config: {base_url}")
                        return base_url
            
            return None
        except Exception as e:
            logger.warning(f"[Ollama Rerank Proxy] Failed to get ollama_host from config: {e}")
            return None
    
    async def handle_rerank_request(self, request) -> JSONResponse:
        """
        Handle rerank request and proxy to Ollama.
        
        Args:
            request: Starlette request object
            
        Returns:
            JSONResponse with rerank results
        """
        try:
            # Parse request body
            body = await request.json()
            
            # Determine format and extract parameters
            if "input" in body:
                # Aliyun format
                query = body.get("input", {}).get("query")
                documents = body.get("input", {}).get("documents", [])
                parameters = body.get("parameters", {})
                top_n = parameters.get("top_n")
                response_format = "aliyun"
            else:
                # Standard format (Jina/Cohere)
                query = body.get("query")
                documents = body.get("documents", [])
                top_n = body.get("top_n")
                response_format = "standard"
            
            model = body.get("model", "xitao/bge-reranker-v2-m3:latest")
            
            # Get ollama_host from config (unified method via RerankManager)
            ollama_host = self._get_ollama_host_from_config()
            
            # Fallback to default if config not available
            if not ollama_host:
                ollama_host = "http://localhost:11434"
            
            # Validate inputs
            if not query:
                return JSONResponse({"error": "Missing 'query' parameter"}, status_code=400)
            if not documents:
                return JSONResponse({"error": "Missing 'documents' parameter"}, status_code=400)
            
            logger.info(f"[Ollama Rerank Proxy] Processing rerank request: model={model}, docs={len(documents)}, format={response_format}, ollama_host={ollama_host}")
            
            # Process rerank request with document passthrough
            results = await self._rerank_documents(
                ollama_host=ollama_host,
                model=model,
                query=query,
                documents=documents,
                return_documents=True  # Enable document passthrough
            )
            
            # Sort by relevance score (descending)
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Apply top_n filter
            if top_n is not None and top_n > 0:
                results = results[:top_n]
            
            logger.info(f"[Ollama Rerank Proxy] Returning {len(results)} reranked results (from {len(documents)} documents)")
            
            # Return in appropriate format
            if response_format == "aliyun":
                return JSONResponse({"output": {"results": results}})
            else:
                return JSONResponse({"results": results})
                
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON in request body"}, status_code=400)
        except Exception as e:
            logger.error(f"[Ollama Rerank Proxy] Error: {e}", exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    
    async def _rerank_documents(
        self,
        ollama_host: str,
        model: str,
        query: str,
        documents: List[str],
        return_documents: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using Ollama's rerank model.
        
        Uses concurrent processing for better performance.
        
        Args:
            ollama_host: Ollama server URL
            model: Rerank model name
            query: Search query
            documents: List of documents to rerank
            return_documents: Whether to include document text in results
            
        Returns:
            List of results with index, relevance_score, and optionally document text
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Process all documents concurrently
            async def get_rerank_score(idx: int, doc: str) -> Optional[Dict[str, Any]]:
                """
                Get rerank score for a single document.
                
                Ollama rerank models expect: "Query: xxx\nDocument: xxx"
                The embedding output represents the relevance score.
                """
                try:
                    # Format the prompt as "Query: xxx\nDocument: xxx"
                    rerank_prompt = f"Query: {query}\nDocument: {doc}"
                    
                    logger.debug(f"[Ollama Rerank Proxy] Getting rerank score for document {idx}...")
                    
                    # Call Ollama's /api/embed API with the formatted prompt
                    response = await client.post(
                        f"{ollama_host}/api/embed",
                        json={
                            "model": model,
                            "input": rerank_prompt
                        }
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"[Ollama Rerank Proxy] Failed to get rerank score for document {idx}: {response.text}")
                        return None
                    
                    # Get the embedding (for rerank models, this represents relevance)
                    result = response.json()
                    embeddings = result.get("embeddings", [])
                    
                    if not embeddings or len(embeddings) == 0:
                        logger.warning(f"[Ollama Rerank Proxy] No embeddings returned for document {idx}")
                        return None
                    
                    # For BGE rerank models, the embedding represents relevance features
                    # We use the sum of the embedding vector as the raw relevance score
                    embedding = embeddings[0]
                    embedding_array = np.array(embedding)
                    
                    # Use sum of embedding as raw score (shows better discrimination)
                    # For BGE reranker: More negative sum = MORE relevant
                    # Less negative/positive sum = LESS relevant
                    raw_score = float(np.sum(embedding_array))
                    
                    # Invert and normalize to [0, 1] range
                    # Negate the score so that more negative (more relevant) becomes higher
                    relevance_score = 1 / (1 + np.exp(raw_score / 10.0))
                    
                    result = {
                        "index": idx,
                        "relevance_score": relevance_score
                    }
                    
                    # Include document text if requested (passthrough)
                    if return_documents:
                        result["document"] = doc
                    
                    return result
                    
                except Exception as e:
                    logger.warning(f"[Ollama Rerank Proxy] Error getting rerank score for document {idx}: {e}")
                    return None
            
            # Process all documents concurrently for better performance
            logger.debug(f"[Ollama Rerank Proxy] Processing {len(documents)} documents concurrently...")
            score_tasks = [get_rerank_score(idx, doc) for idx, doc in enumerate(documents)]
            results = await asyncio.gather(*score_tasks)
            
            # Filter out failed documents
            valid_results = [r for r in results if r is not None]
            
            if len(valid_results) < len(documents):
                logger.warning(f"[Ollama Rerank Proxy] {len(documents) - len(valid_results)} documents failed to process")
            
            return valid_results


# Global instance
_ollama_rerank_proxy = OllamaRerankProxy()


async def ollama_rerank_proxy(request) -> JSONResponse:
    """
    Entry point for Ollama rerank proxy.
    
    Args:
        request: Starlette request object
        
    Returns:
        JSONResponse with rerank results
    """
    return await _ollama_rerank_proxy.handle_rerank_request(request)
