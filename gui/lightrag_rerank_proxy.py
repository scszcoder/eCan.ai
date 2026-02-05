"""
LightRAG Rerank Proxy Module

Provides a unified proxy service for all non-native LightRAG rerank providers:
- Ollama: Uses /api/embed with "Query: xxx\nDocument: xxx" format
- RyoAIS: Uses OpenAI-compatible /v1/rerank endpoint
- Other OpenAI-compatible providers

Architecture:
1. LightRAG calls with standard format (Jina/Cohere/Aliyun)
2. Proxy detects provider type from configuration
3. Routes to appropriate handler
4. Returns results in original format
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
import httpx
import numpy as np
from starlette.responses import JSONResponse

from utils.logger_helper import logger_helper as logger
from knowledge.lightrag_constants import is_proxy_rerank_provider


class LightRAGRerankProxy:
    """
    LightRAG Rerank Proxy - Routes rerank requests to appropriate providers.
    
    Supports:
    - Ollama: Local rerank models via /api/embed
    - RyoAIS: OpenAI-compatible rerank API
    - Generic OpenAI-compatible providers
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
    
    async def _verify_model_exists(self, provider_type: str, base_url: str, model: str) -> bool:
        """
        Verify if model exists by calling provider's model list API.
        
        Args:
            provider_type: Provider type (ollama, ryoais, etc.)
            base_url: Provider base URL
            model: Model name to verify
            
        Returns:
            True if model exists or verification succeeded, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if provider_type == 'ollama':
                    # Ollama: GET /api/tags
                    response = await client.get(f"{base_url}/api/tags")
                    if response.status_code == 200:
                        data = response.json()
                        models = data.get('models', [])
                        # Check if model exists (with or without tag)
                        model_names = [m.get('name', '') for m in models]
                        # Support both "model:tag" and "model" formats
                        model_base = model.split(':')[0] if ':' in model else model
                        found = any(
                            m == model or m.startswith(f"{model_base}:")
                            for m in model_names
                        )
                        if found:
                            logger.debug(f"[Rerank Proxy] Model '{model}' verified in Ollama")
                        else:
                            logger.debug(f"[Rerank Proxy] Model '{model}' not in Ollama model list (may be rerank-specific)")
                        return found
                
                elif provider_type == 'ryoais':
                    # RyoAIS: GET /v1/models (OpenAI-compatible)
                    # Add model_type parameter to filter rerank models
                    response = await client.get(f"{base_url}/models", params={"model_type": "rerank"})
                    if response.status_code == 200:
                        data = response.json()
                        models = data.get('data', [])
                        model_ids = [m.get('id', '') for m in models]
                        found = model in model_ids
                        if found:
                            logger.debug(f"[Rerank Proxy] Model '{model}' verified in RyoAIS rerank models")
                        else:
                            logger.debug(f"[Rerank Proxy] Model '{model}' not in RyoAIS rerank model list")
                        return found
                
                return True  # Unknown provider type, skip verification
                
        except Exception as e:
            logger.warning(f"[Rerank Proxy] Failed to verify model '{model}': {e}")
            return True  # Don't block on verification failure
    
    def _detect_provider_type(self, model: str, provider_config: Optional[Dict[str, Any]]) -> str:
        """
        Detect provider type from provider configuration.
        
        Args:
            model: Model name
            provider_config: Provider configuration from rerank manager
            
        Returns:
            Provider type: 'ollama', 'ryoais', or 'openai_compatible'
        """
        if provider_config:
            # Use provider field from configuration
            provider_name = provider_config.get('provider', '').lower()
            if provider_name:
                return provider_name
        
        # Fallback: detect from model name for Ollama format
        if ':' in model:  # Ollama format: model:tag
            return 'ollama'
        
        # Default to OpenAI-compatible
        return 'openai_compatible'
    
    def _get_provider_config(self, provider_type: str) -> Optional[Dict[str, Any]]:
        """
        Get provider configuration from rerank manager.
        
        Args:
            provider_type: Provider type identifier
            
        Returns:
            Provider configuration dict or None
        """
        try:
            rerank_manager = self._get_rerank_manager()
            if not rerank_manager:
                return None
            
            providers = rerank_manager.get_all_providers()
            
            for provider in providers:
                provider_name = provider.get('provider', '').lower()
                if provider_type in provider_name or provider_name in provider_type:
                    return provider
            
            return None
        except Exception as e:
            logger.warning(f"[Rerank Proxy] Failed to get provider config: {e}")
            return None
    
    async def handle_rerank_request(self, request) -> JSONResponse:
        """
        Handle rerank request and route to appropriate provider.
        
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
            
            model = body.get("model", "")
            
            # Validate inputs
            if not query:
                return JSONResponse({"error": "Missing 'query' parameter"}, status_code=400)
            if not documents:
                return JSONResponse({"error": "Missing 'documents' parameter"}, status_code=400)
            
            # Get provider config from rerank manager
            # Read from config file (not environment variable, as proxy runs in parent process)
            provider_config = None
            base_url = None
            provider_type = None
            
            rerank_manager = self._get_rerank_manager()
            if not rerank_manager:
                return JSONResponse({"error": "Rerank manager not available"}, status_code=500)
            
            # Get original RERANK_BINDING from config file (lightrag.env)
            # Note: Proxy runs in parent process, so we read directly from config file
            from knowledge.lightrag_config_manager import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_effective_config()
            
            original_binding = config.get('RERANK_BINDING', '').lower()
            
            if not original_binding:
                return JSONResponse({"error": "RERANK_BINDING not configured"}, status_code=400)
            
            logger.debug(f"[Rerank Proxy] Read RERANK_BINDING from config: {original_binding}")
            
            # Get provider configuration
            provider_config = rerank_manager.get_provider(original_binding)
            if not provider_config:
                return JSONResponse({"error": f"Provider '{original_binding}' not found"}, status_code=400)
            
            base_url = provider_config.get('base_url', '')
            provider_type = provider_config.get('provider', '').lower()
            
            if not base_url:
                return JSONResponse({"error": f"Provider '{original_binding}' has no base_url configured"}, status_code=400)
            
            logger.debug(f"[Rerank Proxy] Using provider from RERANK_BINDING: {provider_type}, base_url={base_url}")
            
            # Verify model exists by calling provider's model list API if needed
            # Note: Some providers' /models API may only return embedding models, not rerank models
            if provider_type in ['ryoais', 'ollama']:
                model_verified = await self._verify_model_exists(provider_type, base_url, model)
                if not model_verified:
                    logger.debug(f"[Rerank Proxy] Model '{model}' not found in provider's model list, but proceeding (may be rerank-specific)")
            
            # Use provider type from config
            if not provider_type:
                return JSONResponse({"error": f"Provider type not determined for '{original_binding}'"}, status_code=400)
            
            logger.info(f"[Rerank Proxy] Detected provider: {provider_type}, model={model}, docs={len(documents)}, base_url={base_url}")
            
            # Route to appropriate handler
            if provider_type == 'ollama':
                results = await self._rerank_ollama(base_url, model, query, documents)
            elif provider_type == 'ryoais':
                results = await self._rerank_ryoais(base_url, model, query, documents)
            else:
                # Default to OpenAI-compatible format for other providers
                results = await self._rerank_openai_compatible(base_url, model, query, documents)
            
            # Sort by relevance score (descending)
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Apply top_n filter
            if top_n is not None and top_n > 0:
                results = results[:top_n]
            
            logger.info(f"[Rerank Proxy] Returning {len(results)} reranked results (from {len(documents)} documents)")
            
            # Return in appropriate format
            if response_format == "aliyun":
                return JSONResponse({"output": {"results": results}})
            else:
                return JSONResponse({"results": results})
                
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON in request body"}, status_code=400)
        except Exception as e:
            logger.error(f"[Rerank Proxy] Error: {e}", exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    
    async def _rerank_ollama(
        self,
        base_url: str,
        model: str,
        query: str,
        documents: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Rerank using Ollama's embed API.
        
        BGE rerank models use /api/embed with "Query: xxx\nDocument: xxx" format.
        The embedding output represents relevance features.
        
        Implementation based on ollama_proxy.py for compatibility.
        """
        logger.info(f"[Rerank Proxy] Using Ollama provider: {base_url}, model: {model}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def get_rerank_score(idx: int, doc: str) -> Optional[Dict[str, Any]]:
                """
                Get rerank score for a single document.
                
                Ollama rerank models expect: "Query: xxx\nDocument: xxx"
                The embedding output represents the relevance score.
                """
                try:
                    # Format the prompt as "Query: xxx\nDocument: xxx"
                    rerank_prompt = f"Query: {query}\nDocument: {doc}"
                    
                    logger.debug(f"[Rerank Proxy] Getting rerank score for document {idx}...")
                    
                    # Call Ollama's /api/embed API with the formatted prompt
                    response = await client.post(
                        f"{base_url}/api/embed",
                        json={
                            "model": model,
                            "input": rerank_prompt
                        }
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"[Rerank Proxy] Failed to get rerank score for document {idx}: {response.text}")
                        return None
                    
                    # Get the embedding (for rerank models, this represents relevance)
                    result = response.json()
                    embeddings = result.get("embeddings", [])
                    
                    if not embeddings or len(embeddings) == 0:
                        logger.warning(f"[Rerank Proxy] No embeddings returned for document {idx}")
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
                    
                    return {
                        "index": idx,
                        "relevance_score": relevance_score,
                        "document": doc
                    }
                    
                except Exception as e:
                    logger.warning(f"[Rerank Proxy] Error getting rerank score for document {idx}: {e}")
                    return None
            
            # Process all documents concurrently for better performance
            logger.debug(f"[Rerank Proxy] Processing {len(documents)} documents concurrently...")
            score_tasks = [get_rerank_score(idx, doc) for idx, doc in enumerate(documents)]
            results = await asyncio.gather(*score_tasks)
            
            # Filter out failed documents
            valid_results = [r for r in results if r is not None]
            
            if len(valid_results) < len(documents):
                logger.warning(f"[Rerank Proxy] {len(documents) - len(valid_results)} documents failed to process")
            
            return valid_results
    
    async def _rerank_ryoais(
        self,
        base_url: str,
        model: str,
        query: str,
        documents: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Rerank using RyoAIS OpenAI-compatible rerank API.
        
        RyoAIS uses standard Jina/Cohere format: /v1/rerank
        """
        logger.info(f"[Rerank Proxy] Using RyoAIS provider: {base_url}, model: {model}")
        
        # Normalize base_url
        base_url = base_url.rstrip('/')
        if not base_url.endswith('/v1'):
            base_url = f"{base_url}/v1"
        
        rerank_url = f"{base_url}/rerank"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # RyoAIS uses Jina-compatible format
                payload = {
                    "model": model,
                    "query": query,
                    "documents": documents,
                    "return_documents": True
                }
                
                response = await client.post(rerank_url, json=payload)
                
                if response.status_code != 200:
                    logger.error(f"[Rerank Proxy] RyoAIS API error {response.status_code}: {response.text}")
                    # Fallback: return documents with equal scores
                    return [
                        {"index": idx, "relevance_score": 0.5, "document": doc}
                        for idx, doc in enumerate(documents)
                    ]
                
                result = response.json()
                
                # Parse RyoAIS response (Jina-compatible format)
                results_list = result.get("results", [])
                
                parsed_results = []
                for item in results_list:
                    parsed_results.append({
                        "index": item.get("index", 0),
                        "relevance_score": item.get("relevance_score", 0.0),
                        "document": item.get("document", documents[item.get("index", 0)])
                    })
                
                return parsed_results
                
            except Exception as e:
                logger.error(f"[Rerank Proxy] RyoAIS error: {e}")
                # Fallback
                return [
                    {"index": idx, "relevance_score": 0.5, "document": doc}
                    for idx, doc in enumerate(documents)
                ]
    
    async def _rerank_openai_compatible(
        self,
        base_url: str,
        model: str,
        query: str,
        documents: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Rerank using generic OpenAI-compatible rerank API.
        
        Assumes Jina/Cohere format.
        """
        logger.info(f"[Rerank Proxy] Using OpenAI-compatible provider: {base_url}, model: {model}")
        
        # Similar to RyoAIS implementation
        base_url = base_url.rstrip('/')
        rerank_url = f"{base_url}/rerank" if not base_url.endswith('/rerank') else base_url
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                payload = {
                    "model": model,
                    "query": query,
                    "documents": documents,
                    "return_documents": True
                }
                
                response = await client.post(rerank_url, json=payload)
                
                if response.status_code != 200:
                    logger.error(f"[Rerank Proxy] OpenAI-compatible API error {response.status_code}: {response.text}")
                    return [
                        {"index": idx, "relevance_score": 0.5, "document": doc}
                        for idx, doc in enumerate(documents)
                    ]
                
                result = response.json()
                results_list = result.get("results", [])
                
                parsed_results = []
                for item in results_list:
                    parsed_results.append({
                        "index": item.get("index", 0),
                        "relevance_score": item.get("relevance_score", 0.0),
                        "document": item.get("document", documents[item.get("index", 0)])
                    })
                
                return parsed_results
                
            except Exception as e:
                logger.error(f"[Rerank Proxy] OpenAI-compatible error: {e}")
                return [
                    {"index": idx, "relevance_score": 0.5, "document": doc}
                    for idx, doc in enumerate(documents)
                ]


# Global instance
_lightrag_rerank_proxy = LightRAGRerankProxy()


async def lightrag_rerank_proxy(request) -> JSONResponse:
    """
    Entry point for LightRAG rerank proxy.
    
    Args:
        request: Starlette request object
        
    Returns:
        JSONResponse with rerank results
    """
    return await _lightrag_rerank_proxy.handle_rerank_request(request)
