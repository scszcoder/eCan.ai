"""
SSE Manager for MCP Client (DEPRECATED - NOT IN USE)

This module was used for SSE (Server-Sent Events) protocol communication with MCP servers.
It has been replaced by streamablehttp_manager.py which uses the newer Streamable HTTP protocol.

This file is kept for reference only and may be removed in future versions.
"""
import anyio
import anyio.abc
from contextlib import asynccontextmanager
from typing import Optional, Tuple
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

class SSEManager:
    _instance: Optional["SSEManager"] = None

    def __init__(self, url: str) -> None:
        self._url = url
        self._lock = anyio.Lock()
        self._tg: Optional[anyio.abc.TaskGroup] = None
        self._session: Optional[ClientSession] = None
        self._ready: Optional[anyio.Event] = None
    # -------- singleton accessor ------------------------------------
    @classmethod
    def get(cls, url: str) -> "SSEManager":
        if cls._instance is None:
            cls._instance = cls(url)
        return cls._instance

    # -------- public API  -------------------------------------------
    async def session(self) -> ClientSession:
        async with self._lock:
            if self._session is None:
                await self._open()           # first time
            await self._ready.wait()
        return self._session                 # type: ignore[arg-type]

    async def close(self) -> None:
        async with self._lock:
            if self._tg is not None:
                # Cancel background tasks first
                self._tg.cancel_scope.cancel()

                # Store reference to avoid race conditions
                tg_to_close = self._tg
                self._tg = None
                self._session = None
                self._ready = None

                # Close the task group safely
                try:
                    # Wait for tasks to be cancelled
                    await anyio.sleep(0.1)  # Give tasks time to respond to cancellation
                    await tg_to_close.__aexit__(None, None, None)
                except (RuntimeError, anyio.get_cancelled_exc_class()) as e:
                    # Handle task group exit errors gracefully
                    print(f"SSEManager: Task group exit error (expected during shutdown): {e}")
                except Exception as e:
                    print(f"SSEManager: Unexpected error during close: {e}")
                    # Don't re-raise to avoid breaking the shutdown process

    # -------- internal ----------------------------------------------
    async def _open(self) -> None:
        self._tg = anyio.create_task_group()
        await self._tg.__aenter__()

        self._ready = anyio.Event()

        async def _runner() -> None:
            async with sse_client(self._url) as (r, w):
                async with ClientSession(r, w) as sess:
                    print("SSE client session initing................")
                    await sess.initialize()
                    print("SSE client created................")
                    self._session = sess
                    self._ready.set()
                    print("SSE client ready................")
                    await anyio.sleep_forever()   # keep everything alive

        self._tg.start_soon(_runner)


