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
import os
from typing import List, Dict, Any, Optional
import httpx
import numpy as np
from starlette.responses import JSONResponse

from utils.logger_helper import logger_helper as logger
from knowledge.lightrag_constants import is_proxy_rerank_provider

# Providers whose API the proxy cannot actually speak. baidu_qianfan's
# /wenxinworkshop/reranker endpoint expects a Baidu-specific payload, but the
# proxy only knows OpenAI/Jina/Cohere shapes — every call returned
# "0 reranked results" while costing 0.5–9 s of round-trip latency. Until a
# real Baidu adapter exists, we passthrough instead of firing.
_UNSUPPORTED_RERANK_PROVIDERS = frozenset({'baidu_qianfan'})


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
    
    async def _verify_model_exists(self, provider_type: str, base_url: str, model: str, api_key: str = '') -> bool:
        """
        Verify if model exists by calling provider's model list API.
        
        Args:
            provider_type: Provider type (ollama, ryoais, etc.)
            base_url: Provider base URL
            model: Model name to verify
            api_key: API key for the provider
            
        Returns:
            True if model exists or verification succeeded, False otherwise
        """
        try:
            headers = {}
            if api_key and api_key != 'your_api_key':
                headers['Authorization'] = f'Bearer {api_key}'

            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                if provider_type == 'ollama':
                    # Ollama: GET /api/tags (no auth needed, localhost)
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
                
                elif provider_type in ('ryoais', 'ecanai'):
                    # OpenAI-compatible providers: GET /v1/models
                    # Add model_type parameter to filter rerank models
                    response = await client.get(f"{base_url}/models", params={"model_type": "rerank"}, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        models = data.get('data', [])
                        model_ids = [m.get('id', '') for m in models]
                        found = model in model_ids
                        if found:
                            logger.debug(f"[Rerank Proxy] Model '{model}' verified in {provider_type} rerank models")
                        else:
                            logger.debug(f"[Rerank Proxy] Model '{model}' not in {provider_type} rerank model list")
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
            # Log incoming request for debugging
            logger.info(f"[Rerank Proxy] ========== INCOMING RERANK REQUEST ==========")
            logger.info(f"[Rerank Proxy] Request keys: {list(request.keys())}")
            logger.info(f"[Rerank Proxy] Model: {request.get('model', 'NOT SET')}")
            logger.info(f"[Rerank Proxy] Query: {request.get('query', '')[:50]}...")
            logger.info(f"[Rerank Proxy] Documents count: {len(request.get('documents', []))}")
            logger.info(f"[Rerank Proxy] ================================================")
            
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

            # Disable-rerank sentinels.  When a user sets RERANK_BINDING to
            # "null"/"none"/etc. their intent is "I don't want reranking".
            # LightRAG, however, doesn't have a "rerank disabled" path on the
            # query side once it's globally enabled — it still issues a rerank
            # HTTP call.  Without this short-circuit we'd return 400, LightRAG
            # would retry 3× with 8-12s of backoff per retry (~30s tax per
            # query), and most of that time the client side has already hit
            # its read timeout.  Forensic case: 2026-05-18 13:40:23-57 where
            # a customer's 110cm sizing question took 33.7s on LightRAG side
            # — 30.7s of it spent on 3 failed rerank retries — and the client
            # timed out at 30s, forcing a no-rag fallback answer.
            _RERANK_DISABLED_SENTINELS = {"null", "none", "disabled", "off", "false", "0"}
            if not original_binding or original_binding in _RERANK_DISABLED_SENTINELS:
                logger.info(
                    f"[Rerank Proxy] RERANK_BINDING={original_binding!r} → rerank "
                    f"disabled; returning passthrough (original ordering) without "
                    f"contacting any remote."
                )
                passthrough = [
                    {"index": idx, "relevance_score": 1.0, "document": doc}
                    for idx, doc in enumerate(documents)
                ]
                if top_n is not None and top_n > 0:
                    passthrough = passthrough[:top_n]
                if response_format == "aliyun":
                    return JSONResponse({"output": {"results": passthrough}})
                return JSONResponse({"results": passthrough})

            logger.debug(f"[Rerank Proxy] Read RERANK_BINDING from config: {original_binding}")

            # Get provider configuration
            provider_config = rerank_manager.get_provider(original_binding)
            if not provider_config:
                return JSONResponse({"error": f"Provider '{original_binding}' not found"}, status_code=400)

            base_url = provider_config.get('base_url', '')
            provider_type = provider_config.get('provider', '').lower()

            # API key can come from two places (in priority order):
            # 1. RERANK_BINDING_API_KEY env var — set by lightrag_config_manager at startup
            #    (same source LightRAG uses, so it always has the current value)
            # 2. secure_store fallback — read via api_key_env_vars if env var is absent
            api_key = os.environ.get('RERANK_BINDING_API_KEY', '')
            if not api_key:
                for env_var in (provider_config.get('api_key_env_vars') or []):
                    if env_var:
                        key = rerank_manager.retrieve_api_key(env_var)
                        if key and key.strip():
                            api_key = key.strip()
                            logger.debug(f"[Rerank Proxy] API key for {provider_type} loaded from secure_store ({env_var})")
                            break
            logger.debug(f"[Rerank Proxy] API key for {provider_type}: {'found' if api_key else 'NOT FOUND'}")

            if not base_url:
                return JSONResponse({"error": f"Provider '{original_binding}' has no base_url configured"}, status_code=400)

            # Refuse-and-passthrough cases:
            #   (a) Provider needs an API key and none is configured.
            #   (b) Provider's API isn't actually supported by this proxy
            #       (currently baidu_qianfan — it expects a Baidu-specific
            #       payload shape we don't speak, so every call returned 0
            #       results while costing 0.5–9 s of network time).
            # In both cases we short-circuit to a neutral-score passthrough so
            # retrieval continues with the original ordering at zero cost.
            local_providers = {'ollama', 'ryoais', 'lollms'}
            requires_key = provider_config.get('special_features', {}).get('requires_api_key', True)
            needs_key = provider_type not in local_providers and requires_key
            no_key = needs_key and not provider_config.get('api_key_configured', False)
            unsupported = provider_type in _UNSUPPORTED_RERANK_PROVIDERS
            if no_key or unsupported:
                if unsupported:
                    reason = (
                        f"provider '{original_binding}' is not supported by this proxy "
                        f"(no Baidu-format adapter)"
                    )
                else:
                    reason = f"provider '{original_binding}' has no API key configured"
                logger.warning(
                    f"[Rerank Proxy] {reason}; returning passthrough (original "
                    f"ordering) without contacting remote. To stop seeing this, "
                    f"either set RERANK_BINDING=null in lightrag.env (disables "
                    f"rerank entirely) or switch to a supported provider in "
                    f"Settings → Rerank (Cohere / Jina / Aliyun / Ollama / RyoAIS)."
                )
                passthrough = [
                    {"index": idx, "relevance_score": 1.0, "document": doc}
                    for idx, doc in enumerate(documents)
                ]
                if top_n is not None and top_n > 0:
                    passthrough = passthrough[:top_n]
                logger.info(
                    f"[Rerank Proxy] Returning {len(passthrough)} passthrough results "
                    f"(from {len(documents)} documents, reason={reason})"
                )
                if response_format == "aliyun":
                    return JSONResponse({"output": {"results": passthrough}})
                return JSONResponse({"results": passthrough})
            
            # Log detailed routing information with VERY OBVIOUS markers
            logger.info(f"")
            logger.info(f"🔥🔥🔥 [Rerank Proxy] ========== PROXY CALLED ========== 🔥🔥🔥")
            logger.info(f"[Rerank Proxy] User Config (from lightrag.env):")
            logger.info(f"[Rerank Proxy]   RERANK_BINDING = {original_binding}")
            logger.info(f"[Rerank Proxy] Actual Provider (for routing):")
            logger.info(f"[Rerank Proxy]   Provider Type = {provider_type}")
            logger.info(f"[Rerank Proxy]   Base URL = {base_url}")
            logger.info(f"[Rerank Proxy] Request Info:")
            logger.info(f"[Rerank Proxy]   Model (from LightRAG) = {model}")
            logger.info(f"[Rerank Proxy]   Query = {query[:50]}..." if len(query) > 50 else f"[Rerank Proxy]   Query = {query}")
            logger.info(f"[Rerank Proxy]   Documents = {len(documents)} items")
            logger.info(f"🔥🔥🔥 [Rerank Proxy] ================================== 🔥🔥🔥")
            logger.info(f"")
            
            # Verify model exists by calling provider's model list API if needed
            # Note: Some providers' /models API may only return embedding models, not rerank models
            if provider_type in ['ryoais', 'ecanai', 'ollama']:
                model_verified = await self._verify_model_exists(provider_type, base_url, model, api_key)
                if not model_verified:
                    logger.debug(f"[Rerank Proxy] Model '{model}' not found in provider's model list, but proceeding (may be rerank-specific)")
            
            # Use provider type from config
            if not provider_type:
                return JSONResponse({"error": f"Provider type not determined for '{original_binding}'"}, status_code=400)
            
            logger.info(f"[Rerank Proxy] Detected provider: {provider_type}, model={model}, docs={len(documents)}, base_url={base_url}")
            
            # Route to appropriate handler
            if provider_type == 'ollama':
                results = await self._rerank_ollama(base_url, model, query, documents)
            elif provider_type in ('ryoais', 'ecanai'):
                results = await self._rerank_ryoais(base_url, model, query, documents, api_key)
            else:
                # Default to OpenAI-compatible format for other providers
                results = await self._rerank_openai_compatible(base_url, model, query, documents, api_key)
            
            # Sort by relevance score (descending)
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Apply minimum score threshold filter to remove irrelevant documents
            # RERANK_MIN_SCORE threshold: below this score, document is considered irrelevant
            from knowledge.lightrag_config_manager import get_config_manager
            config = get_config_manager().get_effective_config()
            rerank_min_score = float(config.get('RERANK_MIN_SCORE', 0.35))
            
            original_count = len(results)
            results = [r for r in results if r.get("relevance_score", 0) >= rerank_min_score]
            
            if len(results) < original_count:
                logger.info(f"[Rerank Proxy] Filtered {original_count - len(results)} results below RERANK_MIN_SCORE={rerank_min_score}")
            
            # Ensure at least 1 result if we have any documents (avoid empty results)
            if not results and original_count > 0:
                # Restore top result if all were filtered out
                logger.warning(f"[Rerank Proxy] All results filtered out, restoring top 1 result")
                # Re-sort and get top 1 (sort already done above, so first element is highest)
                all_results_sorted = sorted(
                    [{"index": idx, "relevance_score": 1.0, "document": doc} for idx, doc in enumerate(documents)],
                    key=lambda x: x["relevance_score"],
                    reverse=True
                )
                results = [all_results_sorted[0]] if all_results_sorted else []
            
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
        
        # Log target service URL
        embed_url = f"{base_url.rstrip('/')}/api/embed"
        logger.info(f"[Rerank Proxy] 🎯 Target Service URL: {embed_url}")
        logger.info(f"[Rerank Proxy] 📦 Payload: model={model}, query_len={len(query)}, docs={len(documents)}")
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
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
    
    def _normalize_scores_batch(self, results_list: List[Dict[str, Any]], model_name: str = "unknown") -> List[Dict[str, Any]]:
        """
        Normalize rerank scores using shared normalization module.
        
        This is a wrapper around the shared normalize_rerank_scores function
        to maintain backward compatibility with existing code.
        
        Args:
            results_list: List of result dicts with 'relevance_score' and 'index'
            model_name: Model name (for logging only)
            
        Returns:
            List of results with normalized scores in [0, 1] range
        """
        from knowledge.rerank_score_normalizer import normalize_rerank_scores
        return normalize_rerank_scores(results_list, model_name, log_prefix="[Rerank Proxy]")
    
    async def _rerank_ryoais(
        self,
        base_url: str,
        model: str,
        query: str,
        documents: List[str],
        api_key: str = ''
    ) -> List[Dict[str, Any]]:
        """
        Rerank using RyoAIS OpenAI-compatible rerank API.
        
        RyoAIS uses standard Jina/Cohere format: /v1/rerank
        """
        # Map generic model names to RyoAIS actual models
        # LightRAG sends generic names like "jina-reranker-v2-base-multilingual"
        # We need to map them to RyoAIS's actual BGE model
        MODEL_MAPPING = {
            'jina-reranker-v2-base-multilingual': 'bge-reranker-v2-m3-GGUF/bge-reranker-v2-m3-Q6_K.gguf',
            'jina-reranker-v1-base-en': 'bge-reranker-v2-m3-GGUF/bge-reranker-v2-m3-Q6_K.gguf',
            'jina-reranker-v3': 'bge-reranker-v2-m3-GGUF/bge-reranker-v2-m3-Q6_K.gguf',
        }
        
        original_model = model
        if model in MODEL_MAPPING:
            model = MODEL_MAPPING[model]
            logger.info(f"[Rerank Proxy] Mapped model: {original_model} → {model}")
        
        logger.info(f"[Rerank Proxy] Using RyoAIS provider: {base_url}, model: {model}")
        
        # Normalize base_url - remove trailing slash
        base_url = base_url.rstrip('/')
        
        # Build rerank URL
        # If base_url already ends with /v1, just append /rerank
        # Otherwise, append /v1/rerank
        if base_url.endswith('/v1'):
            rerank_url = f"{base_url}/rerank"
        else:
            rerank_url = f"{base_url}/v1/rerank"
        
        # Log target service URL
        logger.info(f"[Rerank Proxy] 🎯 Target Service URL: {rerank_url}")
        logger.info(f"[Rerank Proxy] 📦 Payload: model={model}, query_len={len(query)}, docs={len(documents)}")
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            try:
                # Smart document reduction to avoid context size limits
                # Jina Reranker v3 has 1024 token limit (~4096 chars total)
                # Instead of truncating (losing info), reduce document count if needed
                
                # Estimate total tokens: ~4 chars per token
                total_chars = sum(len(doc) for doc in documents)
                query_tokens = len(query) // 4
                doc_tokens = total_chars // 4
                total_tokens = query_tokens + doc_tokens
                max_tokens = 1024  # Jina v3 limit
                
                final_documents = documents
                
                if total_tokens > max_tokens:
                    # Calculate how many docs we can fit
                    available_tokens = max_tokens - query_tokens - 50  # 50 token buffer
                    avg_doc_tokens = doc_tokens / len(documents)
                    max_docs = max(1, int(available_tokens / avg_doc_tokens))
                    
                    logger.info(
                        f"[Rerank Proxy] 📊 Context optimization: {total_tokens} tokens > {max_tokens} tokens "
                        f"(query: {query_tokens}, docs: {doc_tokens})"
                    )
                    logger.info(
                        f"[Rerank Proxy] 🔄 Smart reduction: keeping top {max_docs}/{len(documents)} documents "
                        f"(NO truncation, preserving full content)"
                    )
                    
                    final_documents = documents[:max_docs]
                else:
                    logger.debug(
                        f"[Rerank Proxy] ✅ All {len(documents)} documents fit within context "
                        f"({total_tokens}/{max_tokens} tokens)"
                    )
                
                # RyoAIS uses Jina-compatible format
                payload = {
                    "model": model,
                    "query": query,
                    "documents": final_documents,
                    "return_documents": True
                }
                
                logger.debug(f"[Rerank Proxy] Sending {len(final_documents)} documents to rerank (query: {len(query)} chars)")

                headers = {}
                if api_key and api_key != 'your_api_key':
                    headers['Authorization'] = f'Bearer {api_key}'

                response = await client.post(rerank_url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"[Rerank Proxy] RyoAIS API error {response.status_code}: {error_text}")
                    
                    # Check if error is due to context size limit
                    if "exceed_context_size_error" in error_text or "larger than the max context size" in error_text:
                        # Extract token info from error message
                        import re
                        token_match = re.search(r'input \((\d+) tokens\).*max context size \((\d+) tokens\)', error_text)
                        if token_match:
                            input_tokens = int(token_match.group(1))
                            max_tokens = int(token_match.group(2))
                            logger.error(
                                f"[Rerank Proxy] ❌ Context limit exceeded: "
                                f"input={input_tokens} tokens > max={max_tokens} tokens "
                                f"(overflow: {input_tokens - max_tokens} tokens)"
                            )
                        
                        # Auto-retry with fewer documents
                        max_docs = len(documents) // 2  # Try with half the documents
                        if max_docs >= 1:
                            logger.warning(
                                f"[Rerank Proxy] 🔄 Auto-retry strategy: "
                                f"reducing from {len(documents)} → {max_docs} documents "
                                f"(keeping top {max_docs} by retrieval order)"
                            )
                            
                            # Use reduced document set (no truncation)
                            retry_docs = documents[:max_docs]
                            
                            retry_payload = {
                                "model": model,
                                "query": query,
                                "documents": retry_docs,
                                "return_documents": True
                            }
                            
                            retry_response = await client.post(rerank_url, json=retry_payload)
                            
                            if retry_response.status_code == 200:
                                result = retry_response.json()
                                results_list = result.get("results", [])
                                
                                # Add document content
                                for item in results_list:
                                    if "document" not in item:
                                        doc_index = item.get("index", 0)
                                        item["document"] = retry_docs[doc_index]
                                
                                # Normalize and return
                                normalized_results = self._normalize_scores_batch(results_list, model)
                                logger.info(
                                    f"[Rerank Proxy] ✅ Retry succeeded: "
                                    f"reranked {len(normalized_results)}/{len(documents)} documents "
                                    f"({len(documents) - len(normalized_results)} docs dropped)"
                                )
                                return normalized_results
                            else:
                                logger.error(
                                    f"[Rerank Proxy] ❌ Retry also failed ({retry_response.status_code}): {retry_response.text}"
                                )
                        else:
                            logger.error(f"[Rerank Proxy] ❌ Cannot retry: already at minimum document count")
                    
                    # Fallback: return documents with equal scores
                    logger.warning(
                        f"[Rerank Proxy] ⚠️  Fallback mode activated: "
                        f"returning {len(documents)} documents with uniform score=0.5 "
                        f"(reranking failed, using original retrieval order)"
                    )
                    return [
                        {"index": idx, "relevance_score": 0.5, "document": doc}
                        for idx, doc in enumerate(documents)
                    ]
                
                result = response.json()
                
                # Log raw response for debugging
                logger.debug(f"[Rerank Proxy] RyoAIS raw response: {result}")
                
                # Parse RyoAIS response (Jina-compatible format)
                results_list = result.get("results", [])
                
                # Add document content to results if not present
                for item in results_list:
                    if "document" not in item:
                        doc_index = item.get("index", 0)
                        item["document"] = documents[doc_index]
                
                # Normalize scores using batch normalization
                normalized_results = self._normalize_scores_batch(results_list, model)
                
                return normalized_results
                
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
        documents: List[str],
        api_key: str = ''
    ) -> List[Dict[str, Any]]:
        """
        Rerank using generic OpenAI-compatible rerank API.
        
        Assumes Jina/Cohere format.
        """
        logger.info(f"[Rerank Proxy] Using OpenAI-compatible provider: {base_url}, model: {model}")
        
        # Similar to RyoAIS implementation
        base_url = base_url.rstrip('/')
        rerank_url = f"{base_url}/rerank" if not base_url.endswith('/rerank') else base_url
        
        # Log target service URL
        logger.info(f"[Rerank Proxy] 🎯 Target Service URL: {rerank_url}")
        logger.info(f"[Rerank Proxy] 📦 Payload: model={model}, query_len={len(query)}, docs={len(documents)}")
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            try:
                payload = {
                    "model": model,
                    "query": query,
                    "documents": documents,
                    "return_documents": True
                }

                headers = {}
                if api_key and api_key != 'your_api_key':
                    headers['Authorization'] = f'Bearer {api_key}'

                response = await client.post(rerank_url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"[Rerank Proxy] OpenAI-compatible API error {response.status_code}: {response.text}")
                    return [
                        {"index": idx, "relevance_score": 0.5, "document": doc}
                        for idx, doc in enumerate(documents)
                    ]
                
                result = response.json()
                results_list = result.get("results", [])
                
                # Add document content to results if not present
                for item in results_list:
                    if "document" not in item:
                        doc_index = item.get("index", 0)
                        item["document"] = documents[doc_index]
                
                # Normalize scores using batch normalization
                normalized_results = self._normalize_scores_batch(results_list, model)
                
                return normalized_results
                
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
