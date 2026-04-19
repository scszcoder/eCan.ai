"""
ECTestClient - Test client for eCan.ai IPC and WebSocket interactions.

Provides two transport modes:
  - "direct":  Calls IPC handlers directly (fastest, no network)
  - "websocket": Calls through WebSocket transport (mimics real frontend)

Usage:
    # Direct mode (no server needed)
    client = ECTestClient(transport="direct")
    await client.initialize()
    session_id = await client.login("test@test.com", "password")
    agents = await client.list_agents()
    await client.shutdown()

    # WebSocket mode
    client = ECTestClient(transport="websocket")
    await client.connect("ws://localhost:8765")
    session_id = await client.login("test@test.com", "password")
    await client.disconnect()
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)


class ECTestClient:
    """
    Unified test client for eCan.ai.

    Supports two transport modes:
      - "direct": Direct handler invocation (for unit/integration tests)
      - "websocket": WebSocket transport (for E2E tests)
    """

    def __init__(
        self,
        transport: Literal["direct", "websocket"] = "direct",
        ws_url: str = "ws://localhost:8765",
        auto_login: bool = False,
        username: str = "test@test.com",
        password: str = "test123",
    ) -> None:
        if transport not in ("direct", "websocket"):
            raise ValueError(f"Unknown transport: {transport}")
        self._transport = transport
        self._ws_url = ws_url
        self._auto_login = auto_login
        self._username = username
        self._password = password

        self._ws: Optional[Any] = None
        self._session_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._connected = False
        self._pending: dict[str, asyncio.Future] = {}
        self._response_store: dict[str, Any] = {}
        self._handler_registry: dict[str, tuple] = {}

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize the test client. Loads IPC handler registry in direct mode."""
        if self._transport == "direct":
            self._load_handlers()
            logger.info("[ECTestClient] Initialized in direct mode")
        else:
            await self.connect()

    async def connect(self, url: str | None = None) -> None:
        """Connect to WebSocket server."""
        if url:
            self._ws_url = url
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets not installed. Run: pip install websockets"
            )

        import websockets as _ws_module
        self._ws = await _ws_module.connect(self._ws_url)
        self._connected = True
        asyncio.create_task(self._ws_reader())
        logger.info(f"[ECTestClient] Connected to {self._ws_url}")

    async def disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        if self._ws and self._connected:
            await self._ws.close()
            self._connected = False
            self._ws = None
        logger.info("[ECTestClient] Disconnected")

    async def shutdown(self) -> None:
        """Shutdown the client."""
        await self.disconnect()
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()

    def _load_handlers(self) -> None:
        """Load IPC handler registry in direct mode."""
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            handlers = IPCHandlerRegistry.list_handlers()
            for cat in ("sync", "background"):
                for handler_info in handlers.get(cat, []):
                    name = handler_info.get("name") if isinstance(handler_info, dict) else handler_info[0].__name__
                    if isinstance(handler_info, dict):
                        self._handler_registry[name] = (handler_info.get("handler"), cat)
                    else:
                        self._handler_registry[name] = (handler_info, cat)
        except ImportError as e:
            logger.warning(f"[ECTestClient] Could not load handler registry: {e}")

    # -------------------------------------------------------------------------
    # WebSocket reader
    # -------------------------------------------------------------------------

    async def _ws_reader(self) -> None:
        """Background task: read WebSocket responses and resolve pending futures."""
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                resp_id = msg.get("id") or msg.get("response_id")
                if resp_id and resp_id in self._pending:
                    fut = self._pending.pop(resp_id)
                    fut.set_result(msg)
                elif msg.get("type") == "event":
                    self._on_event(msg)
        except Exception as e:
            logger.error(f"[ECTestClient] WebSocket reader error: {e}")

    def _on_event(self, msg: dict) -> None:
        """Handle incoming event messages."""
        logger.debug(f"[ECTestClient] Event: {msg.get('event')}")

    # -------------------------------------------------------------------------
    # IPC call helpers
    # -------------------------------------------------------------------------

    def _make_request_id(self) -> str:
        return f"req_{uuid.uuid4().hex[:12]}"

    async def _call_direct(self, method: str, params: dict) -> dict:
        """Call an IPC handler directly (synchronous, runs in executor)."""
        if method not in self._handler_registry:
            return {"status": "error", "error": f"Handler not found: {method}"}

        handler, _ = self._handler_registry[method]
        req_id = self._make_request_id()
        message = {"id": req_id, "method": method, "params": params}

        def run():
            return handler(message, params)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, run)

    async def _call_websocket(self, method: str, params: dict) -> dict:
        """Call an IPC handler via WebSocket."""
        req_id = self._make_request_id()
        message = {
            "id": req_id,
            "type": "request",
            "method": method,
            "params": params,
            "meta": {"session_id": self._session_id},
        }

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut

        await self._ws.send(json.dumps(message))

        try:
            resp = await asyncio.wait_for(fut, timeout=30.0)
            return resp
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            return {"status": "error", "error": "Request timeout"}

    async def call_handler(self, method: str, params: dict | None = None) -> dict:
        """
        Call an IPC handler. Transport is determined by mode.

        Args:
            method: Handler method name (e.g., "agent.getAgents")
            params: Handler parameters

        Returns:
            Handler response dict
        """
        params = params or {}
        params["_session_id"] = self._session_id
        params["_user_id"] = self._user_id

        if self._transport == "direct":
            return await self._call_direct(method, params)
        else:
            return await self._call_websocket(method, params)

    # -------------------------------------------------------------------------
    # Auth / Session
    # -------------------------------------------------------------------------

    async def login(self, username: str | None = None, password: str | None = None) -> str | None:
        """
        Attempt login and store session credentials.

        Returns:
            session_id on success, None on failure.
        """
        username = username or self._username
        password = password or self._password

        try:
            resp = await self.call_handler(
                "auth.login",
                {"username": username, "password": password},
            )
            if resp.get("status") == "success":
                self._session_id = resp.get("session_id") or resp.get("data", {}).get("session_id")
                self._user_id = resp.get("user_id") or resp.get("data", {}).get("user_id")
                logger.info(f"[ECTestClient] Logged in: session={self._session_id}")
                return self._session_id
            else:
                logger.warning(f"[ECTestClient] Login failed: {resp.get('error')}")
                return None
        except Exception as e:
            logger.error(f"[ECTestClient] Login error: {e}")
            return None

    async def logout(self) -> dict:
        """Logout the current session."""
        resp = await self.call_handler("auth.logout", {"session_id": self._session_id})
        self._session_id = None
        self._user_id = None
        return resp

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def user_id(self) -> str | None:
        return self._user_id

    # -------------------------------------------------------------------------
    # Agent API
    # -------------------------------------------------------------------------

    async def create_agent(self, config: dict) -> dict:
        """Create a new agent."""
        return await self.call_handler(
            "agent.add",
            {"agents": [config], "session_id": self._session_id},
        )

    async def list_agents(self, filters: dict | None = None) -> list[dict]:
        """List agents."""
        resp = await self.call_handler(
            "agent.query",
            {"filters": filters or {}, "session_id": self._session_id},
        )
        data = resp.get("data", {})
        if isinstance(data, dict):
            return data.get("agents", [])
        return []

    async def update_agent(self, agent: dict) -> dict:
        """Update an agent."""
        return await self.call_handler(
            "agent.update",
            {"agents": [agent], "session_id": self._session_id},
        )

    async def delete_agent(self, agent_id: str) -> dict:
        """Delete an agent."""
        return await self.call_handler(
            "agent.remove",
            {"agents": [{"id": agent_id}], "session_id": self._session_id},
        )

    # -------------------------------------------------------------------------
    # Skill API
    # -------------------------------------------------------------------------

    async def create_skill(self, config: dict) -> dict:
        """Create a new skill."""
        return await self.call_handler(
            "skill.add",
            {"skills": [config], "session_id": self._session_id},
        )

    async def list_skills(self, filters: dict | None = None) -> list[dict]:
        """List skills."""
        resp = await self.call_handler(
            "skill.query",
            {"filters": filters or {}, "session_id": self._session_id},
        )
        data = resp.get("data", {})
        if isinstance(data, dict):
            return data.get("skills", [])
        return []

    # -------------------------------------------------------------------------
    # Task API
    # -------------------------------------------------------------------------

    async def create_task(self, config: dict) -> dict:
        """Create a new task."""
        return await self.call_handler(
            "task.add",
            {"tasks": [config], "session_id": self._session_id},
        )

    async def list_tasks(self, filters: dict | None = None) -> list[dict]:
        """List tasks."""
        resp = await self.call_handler(
            "task.query",
            {"filters": filters or {}, "session_id": self._session_id},
        )
        data = resp.get("data", {})
        if isinstance(data, dict):
            return data.get("tasks", [])
        return []

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    def store_response(self, key: str, value: Any) -> None:
        """Store a value for later retrieval within the same test."""
        self._response_store[key] = value

    def get_stored_response(self, key: str, default: Any = None) -> Any:
        """Retrieve a stored value."""
        return self._response_store.get(key, default)
