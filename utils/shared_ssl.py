"""One process-wide TLS context for outbound HTTPS clients.

``httpx.AsyncClient()`` / ``httpx.Client()`` and ``ssl.create_default_context()``
load the CA bundle from disk synchronously on EVERY construction. Code that
builds a client per call on an asyncio event loop therefore blocks that loop:
the 2026-10-17 customer log (build yao) showed loop freezes of up to 3.5s from
the A2A heartbeat and from the browser-use LLM proxy. Build the context once and
pass it as ``httpx.AsyncClient(verify=get_shared_ssl_context())`` (or
``aiohttp.TCPConnector(ssl=...)``). An SSLContext is loop-agnostic
configuration, so it is safe to share across event loops and threads.
"""

import ssl
import threading
from typing import Optional

import certifi

_shared_ssl_ctx: Optional[ssl.SSLContext] = None
_shared_ssl_lock = threading.Lock()


def get_shared_ssl_context() -> ssl.SSLContext:
    global _shared_ssl_ctx
    ctx = _shared_ssl_ctx
    if ctx is None:
        with _shared_ssl_lock:
            ctx = _shared_ssl_ctx
            if ctx is None:
                ctx = ssl.create_default_context(cafile=certifi.where())
                _shared_ssl_ctx = ctx
    return ctx
