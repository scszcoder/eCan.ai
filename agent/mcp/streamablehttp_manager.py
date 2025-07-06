# gui/sse_manager.py  ────────────────────────────────────────────────
import anyio
import anyio.abc
from contextlib import asynccontextmanager
from typing import Optional, Tuple
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

class STREAMABLE_HTTP_Manager:
    _instance: Optional["STREAMABLE_HTTP_Manager"] = None

    def __init__(self, url: str) -> None:
        self._url = url
        self._lock = anyio.Lock()
        self._tg: Optional[anyio.abc.TaskGroup] = None
        self._session: Optional[ClientSession] = None
        self._ready: Optional[anyio.Event] = None
    # -------- singleton accessor ------------------------------------
    @classmethod
    def get(cls, url: str) -> "STREAMABLE_HTTP_Manager":
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
                await self._tg.cancel_scope.cancel()
                self._tg = None
                self._session = None

    # -------- internal ----------------------------------------------
    async def _open(self) -> None:
        self._tg = anyio.create_task_group()
        await self._tg.__aenter__()

        self._ready = anyio.Event()

        async def _runner() -> None:
            async with streamablehttp_client(self._url) as (r, w):
                async with ClientSession(r, w) as sess:
                    print("SSE client session initing................")
                    await sess.initialize()
                    print("SSE client created................")
                    self._session = sess
                    self._ready.set()
                    print("SSE client ready................")
                    await anyio.sleep_forever()   # keep everything alive

        self._tg.start_soon(_runner)
