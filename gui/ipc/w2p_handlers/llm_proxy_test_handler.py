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


# ── CN dual-mode (2026-08-30) ───────────────────────────────────────────────
# On CN builds the proxy tests exercise the PUBLIC OpenAI-compatible surface
# of the Tencent llm-proxy:
#   <lambda_proxy_endpoint>/v1/{models, chat/completions, embeddings, rerank}
# authenticated with the account's generated eCan API key (Account page /
# `ecan apikey add`). Intl builds keep the original Lambda-proxy behavior.

def _is_cn() -> bool:
    try:
        from utils.app_env import is_cn
        return is_cn()
    except Exception:
        return False


def _cn_v1_config() -> Dict[str, str]:
    """{'base', 'api_key'} for the CN public v1 surface; raises with an
    actionable message when the account has no API key yet."""
    config = _get_proxy_config()
    base = config['endpoint'].rstrip('/') + '/v1'
    from agent.cloud_api.cloud_api import _http_auth_header
    from agent.cloud_api.api_keys import get_api_key_with_local_fallback
    bearer = _http_auth_header(config['auth_token'] or '')
    session_token = bearer[7:] if bearer.lower().startswith('bearer ') else bearer
    key_resp = get_api_key_with_local_fallback(session_token)
    api_key = key_resp.get('apiKey') or ''
    if not api_key:
        raise ValueError(
            "No account API key found — generate one on the Account page "
            "(or `ecan apikey add`) before testing the CN llm-proxy v1 surface."
        )
    return {'base': base, 'api_key': api_key,
            'provider': config['provider'], 'model': config['model']}


def _cn_v1_request(method: str, path: str, cfg: Dict[str, str],
                   json_body: Optional[Dict[str, Any]] = None,
                   timeout: float = 60.0) -> Dict[str, Any]:
    import httpx
    import time
    url = cfg['base'] + path
    t0 = time.time()
    headers = {'Authorization': f"Bearer {cfg['api_key']}"}
    if method == 'GET':
        resp = httpx.get(url, timeout=timeout, headers=headers)
    else:
        resp = httpx.post(url, timeout=timeout, headers=headers, json=json_body or {})
    latency_ms = int((time.time() - t0) * 1000)
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text[:500]
    return {'mode': 'cn-v1', 'url': url, 'status': resp.status_code,
            'latency_ms': latency_ms, 'body': body}


IPCHandlerRegistry.add_to_whitelist('test_llm_proxy_models')


@IPCHandlerRegistry.handler('test_llm_proxy_models')
def handle_test_llm_proxy_models(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """List the models the proxy serves (GET <endpoint>/v1/models).

    CN: public v1 surface with the account API key. Intl: same route with the
    auth token (honest 404 if the Lambda proxy doesn't expose it).
    """
    try:
        if _is_cn():
            return create_success_response(request, _cn_v1_request('GET', '/models', _cn_v1_config()))
        import httpx
        import time
        config = _get_proxy_config()
        url = config['endpoint'].rstrip('/') + '/v1/models'
        t0 = time.time()
        resp = httpx.get(url, timeout=15.0,
                         headers={'Authorization': f"Bearer {config['auth_token']}"})
        try:
            body: Any = resp.json()
        except Exception:
            body = resp.text[:500]
        return create_success_response(request, {
            'mode': 'intl', 'url': url, 'status': resp.status_code,
            'latency_ms': int((time.time() - t0) * 1000), 'body': body,
        })
    except Exception as e:
        logger.error(f"[llm_proxy_test] Models error: {e}")
        return create_error_response(request, 'PROXY_MODELS_ERROR', str(e))


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

        if _is_cn():
            # CN: ping = list models on the public v1 surface (proves route,
            # auth via the account API key, and upstream registry in one call).
            result = _cn_v1_request('GET', '/models', _cn_v1_config(), timeout=15.0)
            return create_success_response(request, result)

        config = _get_proxy_config()
        url = config['endpoint'].rstrip('/')

        t0 = time.time()
        # Synchronous for simplicity — the handler runs in a thread anyway
        resp = httpx.get(url, timeout=10.0, headers={
            'Authorization': f"Bearer {config['auth_token']}",
        })
        latency_ms = int((time.time() - t0) * 1000)

        token = config['auth_token']
        result = {
            'status': resp.status_code,
            'latency_ms': latency_ms,
            'body': resp.text[:500],
            'endpoint': url,
            'has_token': bool(token),
            'token_preview': (token[:20] + '...') if token else None,
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
        from agent.ec_skills.lambda_proxy_langchain import create_lambda_proxy_langchain
        from langchain_core.messages import HumanMessage

        p = params or {}
        if _is_cn():
            # CN: POST the public /v1/chat/completions (relays to DashScope
            # Qwen). Model comes from params or the server default.
            cfg = _cn_v1_config()
            body: Dict[str, Any] = {
                'messages': [{'role': 'user',
                              'content': p.get('prompt', 'Say hello in one sentence.')}],
            }
            if p.get('model'):
                body['model'] = p['model']
            if p.get('provider'):
                body['provider'] = p['provider']
            result = _cn_v1_request('POST', '/chat/completions', cfg, body)
            resp_body = result.get('body')
            if isinstance(resp_body, dict):
                choices = resp_body.get('choices') or []
                if choices:
                    result['response'] = (choices[0].get('message') or {}).get('content')
                result['usage'] = resp_body.get('usage')
                result['model'] = resp_body.get('model')
            return create_success_response(request, result)

        config = _get_proxy_config()
        prompt = p.get('prompt', 'Say hello in one sentence.')
        provider = p.get('provider', config['provider'])
        model = p.get('model', config['model'])

        logger.info(f"[llm_proxy_test] LLM test: provider={provider}, model={model}, endpoint={config['endpoint']}")

        llm = create_lambda_proxy_langchain(
            provider=provider,
            model=model,
            user_id=config['user_id'],
            lambda_endpoint=config['endpoint'],
            auth_token=config['auth_token'],
            temperature=0.5,
            timeout=60.0,
        )

        # Use sync invoke — background_handler already runs in a thread
        messages = [HumanMessage(content=prompt)]
        response = llm.invoke(messages)

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
        from browser_use.llm.messages import UserMessage

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
                llm.ainvoke([UserMessage(content=prompt)])
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

        p = params or {}
        text = p.get('text', 'Hello world')

        if _is_cn():
            # CN: public /v1/embeddings (relays to DashScope text-embedding-v3).
            cfg = _cn_v1_config()
            body: Dict[str, Any] = {'input': text}
            if p.get('model'):
                body['model'] = p['model']
            result = _cn_v1_request('POST', '/embeddings', cfg, body, timeout=30.0)
            resp_body = result.get('body')
            if isinstance(resp_body, dict):
                data = resp_body.get('data') or []
                if data and isinstance(data[0], dict):
                    emb = data[0].get('embedding') or []
                    result['dimensions'] = len(emb)
                    result['embedding_preview'] = emb[:5]
                    resp_body.pop('data', None)  # keep the output readable
                result['usage'] = resp_body.get('usage')
                result['model'] = resp_body.get('model')
            return create_success_response(request, result)

        config = _get_proxy_config()
        # Use explicit provider/model for embedding test
        # Local-only providers (ollama) don't work through the proxy
        embed_provider = p.get('provider', 'openai')
        embed_model = p.get('model', 'text-embedding-3-small')

        url = config['endpoint'].rstrip('/') + '/v1/embeddings'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {config['auth_token']}",
            'X-User-Id': config['user_id'],
            'X-Provider': embed_provider,
        }
        payload = {
            'model': embed_model,
            'input': text,
        }

        logger.info(f"[llm_proxy_test] Embedding test: model={embed_model}, provider={headers['X-Provider']}, url={url}")
        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        if resp.status_code >= 400:
            body = resp.text[:500]
            logger.error(f"[llm_proxy_test] Embedding error {resp.status_code}: {body}")
            return create_error_response(request, 'PROXY_EMBEDDING_ERROR',
                f"HTTP {resp.status_code}: {body}")
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


IPCHandlerRegistry.add_to_whitelist('test_lambda_proxy_health_check')


@IPCHandlerRegistry.background_handler('test_lambda_proxy_health_check')
def handle_test_lambda_proxy_health_check(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Trigger the Lambda's /v1/test health-check endpoint.

    The Lambda itself visits all configured providers with cheap models
    and returns the results. We just forward the request.
    """
    try:
        import httpx
        import time

        if _is_cn():
            # CN: sweep every documented public v1 route in one shot.
            # /rerank returning 501 not_implemented is the EXPECTED healthy
            # answer until a reranking provider is configured server-side.
            cfg = _cn_v1_config()
            routes = {
                'models': _cn_v1_request('GET', '/models', cfg, timeout=15.0),
                'chat_completions': _cn_v1_request(
                    'POST', '/chat/completions', cfg,
                    {'messages': [{'role': 'user', 'content': 'ping — reply with pong'}]}),
                'embeddings': _cn_v1_request('POST', '/embeddings', cfg,
                                             {'input': 'health check'}, timeout=30.0),
                'rerank': _cn_v1_request(
                    'POST', '/rerank', cfg,
                    {'query': 'q', 'documents': ['a', 'b']}, timeout=15.0),
            }
            def _ok(name: str, r: Dict[str, Any]) -> bool:
                if name == 'rerank':
                    return r['status'] in (200, 501)
                return r['status'] == 200
            summary = {name: {'status': r['status'], 'latency_ms': r['latency_ms'],
                              'ok': _ok(name, r)} for name, r in routes.items()}
            return create_success_response(request, {
                'mode': 'cn-v1', 'base': cfg['base'],
                'healthy': all(v['ok'] for v in summary.values()),
                'summary': summary, 'routes': routes,
            })

        config = _get_proxy_config()
        url = config['endpoint'].rstrip('/') + '/v1/test'

        # Forward optional params: prompt, providers
        p = params or {}
        body = {}
        if p.get('prompt'):
            body['prompt'] = p['prompt']
        if p.get('providers'):
            body['providers'] = p['providers']

        t0 = time.time()
        resp = httpx.post(url, json=body, headers={
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {config['auth_token']}",
            'X-User-Id': config['user_id'],
        }, timeout=120.0)
        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code >= 400:
            return create_error_response(request, 'PROXY_HEALTH_ERROR',
                f"HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        data['total_latency_ms'] = latency_ms
        return create_success_response(request, data)

    except Exception as e:
        logger.error(f"[llm_proxy_test] Health check error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'PROXY_HEALTH_ERROR', str(e))


IPCHandlerRegistry.add_to_whitelist('test_req_create_scene')


@IPCHandlerRegistry.background_handler('test_req_create_scene')
def handle_test_req_create_scene(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Test ecan_ai_api_req_create_scene as if called from the LLM.

    Params:
        description: str (optional, default "create a paper tiger.")
        output_format: str (optional, default "IMAGE")
        style: str (optional, default "REALISTIC")
        output_resolution: list (optional, default [1024, 1024])
    """
    try:
        from app_context import AppContext
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene

        main_window = AppContext.get_main_window()
        if not main_window:
            return create_error_response(request, 'REQ_CREATE_SCENE_ERROR', 'Main window not available')

        p = params or {}
        config = {
            'agent_id': 'test_req_create_scene',
            'description': p.get('description', 'create a paper tiger.'),
            'output_format': p.get('output_format', 'IMAGE'),
            'output_resolution': p.get('output_resolution', [1024, 1024]),
            'duration_hint_ms': 0,
            'emotion': '',
            'mind_state': '',
            'style': p.get('style', 'REALISTIC'),
            'context': '',
            'refs': [],
        }

        logger.info(f"[llm_proxy_test] req_create_scene config: {config}")
        result = ecan_ai_api_req_create_scene(main_window, config)

        if hasattr(result, '__dict__'):
            result_data = vars(result)
        elif isinstance(result, dict):
            result_data = result
        else:
            result_data = {'text': str(result)}

        return create_success_response(request, result_data)

    except Exception as e:
        logger.error(f"[llm_proxy_test] req_create_scene error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'REQ_CREATE_SCENE_ERROR', str(e))
