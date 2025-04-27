from __future__ import annotations

import uuid
import json
import traceback
from typing import TypedDict, List, Annotated, Any, Dict, Optional

import anyio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.shared.session import JSONRPCMessage


# ---------------------------------------------------------------------------
# ── MCP Client Session Manager ─────────────────────────────────────────
# ---------------------------------------------------------------------------
class MCPClientSessionManager:
    """Async context manager that keeps an MCP ClientSession alive.

    Serialises writes with a lock and auto‑reconnects on ClosedResourceError.
    Accessible via .session or helper wrappers.
    """

    def __init__(self, url: str, *, max_retries: int = 3, backoff: float = 1.5):
        self.url = url
        self.max_retries = max_retries
        self.backoff = backoff

        self._lock = anyio.Lock()
        self._sse_cm = None  # will hold the context‑manager from sse_client
        self._session: Optional[ClientSession] = None
        self._streams = None

    # ---------------- context management ----------------
    async def __aenter__(self):
        await self._open()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._close()

    # ---------------- public wrappers -------------------
    @property
    def session(self) -> ClientSession:
        return self._session

    async def list_tools(self):
        return await self._call(lambda s: s.list_tools())

    async def call_tool(self, name: str, **kwargs):
        return await self._call(lambda s: s.call_tool(name, **kwargs))

    # ---------------- internal helpers ------------------
    async def _call(self, fn):
        async with self._lock:
            for attempt in range(1, self.max_retries + 1):
                try:
                    return await fn(self._session)
                except anyio.ClosedResourceError:
                    if attempt == self.max_retries:
                        raise  # bubble up after last retry
                    await self._reconnect()

    async def _open(self):
        self._sse_cm = sse_client(self.url)
        self._streams = await self._sse_cm.__aenter__()
        self._session = ClientSession(*self._streams)
        await self._session.__aenter__()
        await self._session.initialize()

    async def _close(self):
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
        if self._sse_cm is not None:
            await self._sse_cm.__aexit__(None, None, None)

    async def _reconnect(self):
        await self._close()
        await anyio.sleep(self.backoff)
        await self._open()