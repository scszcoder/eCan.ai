"""IPC handlers for testing the Lambda LLM proxy."""

import traceback
from typing import Any, Optional, Dict

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _get_proxy_config() -> Dict[str, str]:
    """Get Lambda proxy configuration from settings."""
    from app_context import AppContext
    main_window = AppContext.get_main_window()
    if not main_window or not hasattr(main_window, 'config_manager') or not main_window.config_manager:
        raise RuntimeError("Settings not available")
    gs = main_window.config_manager.general_settings
    endpoint = gs.lambda_proxy_endpoint
    if not endpoint:
        raise ValueError("Lambda proxy endpoint not configured. Set it in Settings > API > Cloud LLM Proxy.")

    # Auth token
    auth_token = ''
    if hasattr(main_window, 'get_auth_token'):
        auth_token = main_window.get_auth_token() or ''

    # User ID
    user_id = ''
    if hasattr(main_window, 'user_email'):
        user_id = main_window.user_email or ''

    # Default LLM provider/model
    provider = gs.default_llm or 'openai'
    model = gs.default_llm_model or 'gpt-4o-mini'

    return {
        'endpoint': endpoint,
        'auth_token': auth_token,
        'user_id': user_id,
        'provider': provider,
        'model': model,
    }


IPCHandlerRegistry.add_to_whitelist('test_lambda_proxy_ping')
IPCHandlerRegistry.add_to_whitelist('test_lambda_proxy_llm')
IPCHandlerRegistry.add_to_whitelist('test_lambda_proxy_browser_use')
IPCHandlerRegistry.add_to_whitelist('test_lambda_proxy_embedding')


@IPCHandlerRegistry.handler('test_lambda_proxy_ping')
def handle_test_lambda_proxy_ping(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Health-check the Lambda proxy endpoint.

    Sends GET to the Lambda Function URL root and reports status + latency.
    """
    try:
        import httpx
        import time

        config = _get_proxy_config()
        url = config['endpoint'].rstrip('/')

        t0 = time.time()
        # Synchronous for simplicity — the handler runs in a thread anyway
        resp = httpx.get(url, timeout=10.0, headers={
            'Authorization': f"Bearer {config['auth_token']}",
        })
        latency_ms = int((time.time() - t0) * 1000)

        result = {
            'status': resp.status_code,
            'latency_ms': latency_ms,
            'body': resp.text[:500],
            'endpoint': url,
        }
        return create_success_response(request, result)

    except Exception as e:
        logger.error(f"[llm_proxy_test] Ping error: {e}")
        return create_error_response(request, 'PROXY_PING_ERROR', str(e))


@IPCHandlerRegistry.background_handler('test_lambda_proxy_llm')
def handle_test_lambda_proxy_llm(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Test LLM chat completion through the Lambda proxy using LangChain.

    Params:
        prompt: str (optional, default "Say hello in one sentence.")
        provider: str (optional, override default LLM provider)
        model: str (optional, override default LLM model)
    """
    try:
        import asyncio
        from agent.ec_skills.lambda_proxy_langchain import create_lambda_proxy_langchain

        config = _get_proxy_config()
        p = params or {}
        prompt = p.get('prompt', 'Say hello in one sentence.')
        provider = p.get('provider', config['provider'])
        model = p.get('model', config['model'])

        llm = create_lambda_proxy_langchain(
            provider=provider,
            model=model,
            user_id=config['user_id'],
            lambda_endpoint=config['endpoint'],
            auth_token=config['auth_token'],
            temperature=0.5,
            timeout=60.0,
        )

        # Run async invoke
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(llm.ainvoke(prompt))
        finally:
            loop.close()

        result = {
            'provider': provider,
            'model': model,
            'prompt': prompt,
            'response': response.content if hasattr(response, 'content') else str(response),
            'usage': None,
        }
        # Try to extract usage metadata
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            result['usage'] = dict(response.usage_metadata)
        elif hasattr(response, 'response_metadata'):
            meta = response.response_metadata or {}
            if 'token_usage' in meta:
                result['usage'] = meta['token_usage']

        return create_success_response(request, result)

    except Exception as e:
        logger.error(f"[llm_proxy_test] LLM test error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'PROXY_LLM_ERROR', str(e))


@IPCHandlerRegistry.background_handler('test_lambda_proxy_browser_use')
def handle_test_lambda_proxy_browser_use(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Test browser-use ChatLambdaProxy.ainvoke().

    Params:
        prompt: str (optional)
        provider: str (optional)
        model: str (optional)
    """
    try:
        import asyncio
        from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy
        from browser_use.llm.messages import HumanMessage

        config = _get_proxy_config()
        p = params or {}
        prompt = p.get('prompt', 'What is 2 + 2? Reply with just the number.')
        provider = p.get('provider', config['provider'])
        model = p.get('model', config['model'])

        llm = ChatLambdaProxy(
            model=model,
            provider_name=provider,
            user_id=config['user_id'],
            lambda_endpoint=config['endpoint'],
            auth_token=config['auth_token'],
            timeout=60.0,
        )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                llm.ainvoke([HumanMessage(content=prompt)])
            )
        finally:
            loop.close()

        data = {
            'provider': provider,
            'model': model,
            'prompt': prompt,
            'response': str(result.completion),
            'usage': None,
            'stop_reason': result.stop_reason,
        }
        if result.usage:
            data['usage'] = {
                'prompt_tokens': result.usage.prompt_tokens,
                'completion_tokens': result.usage.completion_tokens,
                'total_tokens': result.usage.total_tokens,
            }

        return create_success_response(request, data)

    except Exception as e:
        logger.error(f"[llm_proxy_test] Browser-use test error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'PROXY_BROWSER_USE_ERROR', str(e))


@IPCHandlerRegistry.background_handler('test_lambda_proxy_embedding')
def handle_test_lambda_proxy_embedding(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Test embedding generation through the Lambda proxy.

    Params:
        text: str (optional, default "Hello world")
        model: str (optional, override embedding model)
    """
    try:
        import httpx

        config = _get_proxy_config()
        p = params or {}
        text = p.get('text', 'Hello world')

        # Get embedding model from settings
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        gs = main_window.config_manager.general_settings
        embed_model = p.get('model', gs.default_embedding_model or 'text-embedding-3-small')

        url = config['endpoint'].rstrip('/') + '/v1/embeddings'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {config['auth_token']}",
            'X-User-Id': config['user_id'],
            'X-Provider': gs.default_embedding or 'openai',
        }
        payload = {
            'model': embed_model,
            'input': text,
        }

        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        # Extract embedding info
        embedding_data = data.get('data', [{}])[0]
        embedding_vec = embedding_data.get('embedding', [])

        result = {
            'model': embed_model,
            'input': text,
            'dimensions': len(embedding_vec),
            'embedding_preview': embedding_vec[:5] if embedding_vec else [],
            'usage': data.get('usage'),
        }
        return create_success_response(request, result)

    except Exception as e:
        logger.error(f"[llm_proxy_test] Embedding test error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'PROXY_EMBEDDING_ERROR', str(e))
