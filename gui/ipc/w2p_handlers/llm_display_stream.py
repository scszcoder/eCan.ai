"""CN-only SSE display streaming for the app-wide assistant chat panel.

The CN backend exposes an OpenAI-compatible SSE gateway at
``POST https://<ecan-graphql-ws host>/v1/chat/completions``. While the
blocking cloud relay (``sendSkillEditorChatMessage``) computes the canonical
assistant reply, this module streams a display-progress completion in
parallel and forwards the accumulated text through the existing
``push_skill_editor_chat_chunk`` channel — the chat panel renders those
chunks in its streaming status line and the canonical ``stream_end`` /
sync response replaces them. No frontend changes are required.

This is the "trusted backend proxy" transport variant: the desktop backend
holds the session token and makes the SSE request itself, so the browser
never needs an Authorization-bearing EventSource and CORS is not involved.
"""

import json
import threading
import time
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger


def _resolve_stream_config() -> Optional[Dict[str, str]]:
    """Resolve the SSE gateway endpoint + bearer token, or None if unavailable.

    CN-only. Endpoint resolution order:
      1. ``lambda_proxy_endpoint`` from Settings (explicit override);
      2. derived from the TCB WS URL installed at login:
         ``wss://<host>/ws`` -> ``https://<host>``.

    The bearer is the eCan 30-day session token (the only credential the CN
    HTTP gate verifies), falling back to the bare JWT from the composite
    access token.
    """
    from utils.app_env import is_cn_app
    if not is_cn_app():
        return None

    from app_context import AppContext
    main_window = AppContext.get_main_window()
    if not main_window or not getattr(main_window, 'config_manager', None):
        return None
    gs = main_window.config_manager.general_settings

    endpoint = (gs.lambda_proxy_endpoint or '').strip().rstrip('/')
    if not endpoint:
        ws_url = (getattr(gs, 'ws_api_endpoint', '') or '').strip()
        if ws_url.startswith(('wss://', 'ws://')):
            from urllib.parse import urlparse
            host = urlparse(ws_url).netloc
            if host:
                endpoint = f"https://{host}"
    if not endpoint:
        return None

    from agent.cloud_api.cloud_api import _get_wechat_http_session_token
    token = _get_wechat_http_session_token()
    if not token and hasattr(main_window, 'get_auth_token'):
        raw = main_window.get_auth_token() or ''
        token = raw.split('/@@/', 1)[-1] if '/@@/' in raw else raw
    if not token:
        return None

    return {
        'endpoint': endpoint,
        'token': token,
        'model': gs.default_llm_model or 'gpt-4o-mini',
        'user_id': (getattr(main_window, 'user_email', '') or ''),
    }


def start_display_stream(session_id: str, message_id: str, content: str) -> Optional[threading.Event]:
    """Start a background SSE display stream for one user message.

    Returns a stop event the caller MUST set once the canonical response is
    ready (before pushing stream_end), or None when streaming is unavailable
    (intl build, not signed in, no endpoint) — in which case the buffered
    flow proceeds exactly as before.
    """
    config = _resolve_stream_config()
    if not config:
        return None
    stop = threading.Event()
    threading.Thread(
        target=_run_stream,
        args=(config, session_id, message_id, content, stop),
        daemon=True,
        name=f"sse-display-{session_id[:8]}",
    ).start()
    return stop


def _extract_delta(payload: Dict[str, Any]) -> str:
    """Delta text from one SSE data payload (OpenAI shape or llm.delta)."""
    try:
        delta = ((payload.get('choices') or [{}])[0].get('delta') or {}).get('content')
        if isinstance(delta, str):
            return delta
    except (AttributeError, IndexError, TypeError):
        pass
    if payload.get('type') == 'llm.delta' and isinstance(payload.get('delta'), str):
        return payload['delta']
    return ''


def _run_stream(config: Dict[str, str], session_id: str, message_id: str,
                content: str, stop: threading.Event) -> None:
    """Stream one completion and forward accumulated text as chat chunks.

    The panel's handleChunk renders each chunk payload wholesale as the
    streaming status text, so we push the ACCUMULATED text (throttled) —
    not individual token deltas. No stream_end is pushed from here: the
    canonical response path owns message finalization.
    """
    try:
        import httpx
        from gui.ipc.api import IPCAPI
        ipc = IPCAPI.get_instance()

        url = config['endpoint'] + '/v1/chat/completions'
        body = {
            'model': config['model'],
            'messages': [{'role': 'user', 'content': content}],
            'stream': True,
        }
        if config.get('user_id'):
            body['user'] = config['user_id']

        accumulated = ''
        chunk_index = 0
        last_push = 0.0

        logger.info(f"[llm_display_stream] Opening SSE display stream: {url}")
        with httpx.stream(
            'POST', url, json=body,
            headers={
                'Authorization': f"Bearer {config['token']}",
                'Accept': 'text/event-stream',
                'Content-Type': 'application/json',
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        ) as resp:
            if resp.status_code != 200:
                logger.info(f"[llm_display_stream] SSE gateway HTTP {resp.status_code} — display stream skipped")
                return
            logger.info(f"[llm_display_stream] SSE stream connected (HTTP 200, {resp.headers.get('content-type', '?')})")
            for line in resp.iter_lines():
                if stop.is_set():
                    logger.debug("[llm_display_stream] Stopped by canonical response — closing display stream")
                    return
                if not line or not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    delta = _extract_delta(json.loads(data))
                except ValueError:
                    continue
                if not delta:
                    continue
                accumulated += delta
                now = time.time()
                # Throttle pushes so the local WS isn't flooded per-token.
                if now - last_push >= 0.15:
                    last_push = now
                    ipc.push_skill_editor_chat_chunk(session_id, message_id, accumulated, chunk_index)
                    chunk_index += 1

        if accumulated and not stop.is_set():
            ipc.push_skill_editor_chat_chunk(session_id, message_id, accumulated, chunk_index)
        logger.info(f"[llm_display_stream] Display stream finished ({len(accumulated)} chars, {chunk_index + 1} pushes)")
    except Exception as e:
        # Display transport is best-effort — never disturb the canonical flow.
        logger.info(f"[llm_display_stream] Display stream ended: {e}")
