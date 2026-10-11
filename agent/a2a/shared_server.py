"""One A2A HTTP server for every agent of this process.

Each agent used to start its own uvicorn server (a thread, an event loop and a
port per agent).  Now one server listens on one port and dispatches by path:
``/a2a/<agent_id>/...`` goes to that agent's own A2A Starlette app (its
executor, task store and agent card are unchanged).  An agent's card URL is
``http://<lan ip>:<port>/a2a/<agent_id>/``.

Kill switch: ``ECAN_A2A_SHARED_SERVER=0`` (each agent serves on its own port,
as before).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from typing import Any, Callable, Dict, Optional

from utils.logger_helper import logger_helper as logger

_PATH = re.compile(r"^/a2a/([^/]+)(/.*)?$")


def enabled() -> bool:
    return os.environ.get("ECAN_A2A_SHARED_SERVER", "1") != "0"


def is_shared_url(url: str) -> bool:
    return "/a2a/" in str(url or "")


class SharedA2AServer:
    def __init__(self, port_allocator: Optional[Callable[[], int]] = None,
                 host_ip: Optional[Callable[[], str]] = None):
        self._apps: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._port: Optional[int] = None
        self._allocate = port_allocator
        self._host_ip = host_ip
        self._server = None
        self._thread: Optional[threading.Thread] = None
        # agent id -> True when it could make that agent register (a deferred
        # agent built and started on first request).
        self.resolver: Optional[Callable[[str], bool]] = None

    # ── addressing ──
    def port(self) -> int:
        with self._lock:
            if self._port is None:
                self._port = int(self._allocate()) if self._allocate else 3600
            return self._port

    def url_for(self, agent_id: str) -> str:
        host = self._host_ip() if self._host_ip else "127.0.0.1"
        return f"http://{host}:{self.port()}/a2a/{agent_id}/"

    # ── agents ──
    def register(self, agent_id: str, app: Any) -> None:
        with self._lock:
            self._apps[str(agent_id)] = app
        self._ensure_running()

    def unregister(self, agent_id: str) -> None:
        with self._lock:
            self._apps.pop(str(agent_id), None)

    def registered(self) -> list:
        with self._lock:
            return list(self._apps)

    # ── ASGI ──
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif msg["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        m = _PATH.match(scope.get("path") or "")
        app = self._apps.get(m.group(1)) if m else None
        if app is None and m and self.resolver is not None and scope["type"] == "http":
            try:
                if await asyncio.to_thread(self.resolver, m.group(1)):
                    app = self._apps.get(m.group(1))
            except Exception as e:
                logger.warning(f"[a2a-shared] waking agent {m.group(1)} failed: {e}")
        if app is None:
            if scope["type"] == "http":
                body = json.dumps({"error": "unknown agent", "path": scope.get("path")}).encode()
                await send({"type": "http.response.start", "status": 404,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
            return
        prefix = f"/a2a/{m.group(1)}"
        rest = "/" + (m.group(2) or "/").lstrip("/")
        sub = dict(scope)
        sub["path"] = rest
        sub["raw_path"] = rest.encode()
        sub["root_path"] = scope.get("root_path", "") + prefix
        await app(sub, receive, send)

    # ── server ──
    def _ensure_running(self) -> None:
        if self._thread is not None:
            return
        port = self.port()
        import uvicorn

        def run():
            try:
                config = uvicorn.Config(self, host="0.0.0.0", port=port, log_level="warning",
                                        log_config=None, lifespan="off", limit_concurrency=200,
                                        backlog=512, access_log=False)
                server = uvicorn.Server(config)
                server.install_signal_handlers = lambda: None
                self._server = server
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.info(f"[a2a-shared] one A2A server for all agents on port {port}")
                loop.run_until_complete(server.serve())
            except Exception as e:
                logger.error(f"[a2a-shared] A2A server on port {port} failed: {e}")

        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=run, name="A2A-shared", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True


_shared: Optional[SharedA2AServer] = None
_shared_lock = threading.Lock()


def get_shared_server(mainwin: Any = None) -> SharedA2AServer:
    global _shared
    with _shared_lock:
        if _shared is None:
            def _alloc() -> int:
                ports = mainwin.get_free_agent_ports(1) if mainwin is not None else []
                return int(ports[0]) if ports else 3600

            def _ip() -> str:
                from agent.a2a.langgraph_agent.utils import get_lan_ip
                return get_lan_ip()
            _shared = SharedA2AServer(port_allocator=_alloc, host_ip=_ip)

            def _wake(agent_id: str) -> bool:
                from agent.ec_agents.lazy_agent import find_agent, wake
                ag = find_agent(mainwin, agent_id) if mainwin is not None else None
                if ag is None or not getattr(type(ag), "lazy_is_cold", None) or not ag.lazy_is_cold:
                    return False
                wake(ag, "A2A request")
                return True
            _shared.resolver = _wake
        return _shared
