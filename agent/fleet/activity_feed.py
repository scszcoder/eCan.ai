"""Fleet activity feed: what this machine's agents are doing, for the account's web view.

Each desktop (Commander or Platoon) publishes a compact feed on the WAN chat
channel ``fleet.feed``; the web app (a Staff Officer, e.g. on a phone) subscribes
to it and can send commands back on ``fleet.cmd``. Both channels are scoped by
the server to the caller's verified identity, so a feed only ever reaches the
same account (see the server contract in the commit that added this file).

What goes out, batched every few seconds (never more than one send per
``FLUSH_S``, each capped in size):

* ``snapshot`` -- every 60 s and on request: this machine, its role, its agents
  (running or not, readiness);
* ``agent_status`` -- an agent's readiness changed (the ``[AGENT-STATUS]`` ledger);
* ``task`` -- a task started, completed or failed;
* ``log`` -- log lines, ONLY while a web user asked for a tail (``log_start``),
  for at most ``ttl_s``, rate-capped.

A slow or unreachable cloud is expected: events queue in a bounded ring, sends
back off, and nothing here ever blocks or breaks an agent. Off switch:
``ECAN_FLEET_FEED=0``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

FEED_CHANNEL = "fleet.feed"
CMD_CHANNEL = "fleet.cmd"
FLUSH_S = 3.0
SNAPSHOT_S = 60.0
MAX_EVENTS_PER_SEND = 60
MAX_SEND_BYTES = 24_000          # under the server's 32 KB cap
QUEUE_MAX = 600
LOG_LINES_PER_S = 20
LOG_TTL_MAX_S = 1800
_TAG = "[FLEET-FEED]"            # our own lines never enter the log tail


def enabled() -> bool:
    return os.environ.get("ECAN_FLEET_FEED", "1") != "0"


class _TailHandler(logging.Handler):
    """Copies log lines into the feed while a tail is active."""

    def __init__(self, feed: "FleetFeed", level: int):
        super().__init__(level)
        self._feed = feed
        self._window = [time.monotonic(), 0]
        self.dropped = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if _TAG in msg or "sendWanMessage" in msg or "wan send" in msg:
                return
            now = time.monotonic()
            if now - self._window[0] >= 1.0:
                self._window = [now, 0]
            if self._window[1] >= LOG_LINES_PER_S:
                self.dropped += 1
                return
            self._window[1] += 1
            self._feed.note("log", level=record.levelname, text=msg[:500])
        except Exception:
            pass


class FleetFeed:
    def __init__(self):
        self._mainwin = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._events: deque = deque(maxlen=QUEUE_MAX)
        self._lock = threading.Lock()
        self._tasks: List[asyncio.Task] = []
        self._tail: Optional[_TailHandler] = None
        self._tail_until = 0.0
        self._snapshot_due = True
        self._backoff_until = 0.0
        self._fail_streak = 0
        self._task_status: Dict[str, Dict[str, Any]] = {}

    # ── producers (any thread) ──────────────────────────────────────────
    def note(self, kind: str, **fields: Any) -> None:
        if not enabled():
            return
        ev = {"ts": int(time.time() * 1000), "kind": kind, **fields}
        with self._lock:
            self._events.append(ev)

    def note_task(self, task: Any, status: str) -> None:
        tid = str(getattr(task, "id", "") or "")
        name = str(getattr(task, "name", "") or "")
        with self._lock:
            self._task_status[tid] = {"task": name, "status": status, "ts": int(time.time() * 1000)}
        err = ""
        if status == "failed":
            msg = getattr(getattr(task, "status", None), "message", None)
            err = str(getattr(msg, "text", "") or msg or "")[:300]
        self.note("task", task=name, task_id=tid, status=status,
                  agent_id=str(getattr(task, "agent_id", "") or ""), error=err or None)

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self, mainwin) -> None:
        if not enabled() or self._tasks:
            return
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(f"{_TAG} no running loop -- feed not started")
            return
        self._mainwin = mainwin
        self._tasks = [self._loop.create_task(self._flush_loop()),
                       self._loop.create_task(self._cmd_loop())]
        logger.info(f"{_TAG} publishing this machine's activity on {FEED_CHANNEL}")

    # ── machine identity ─────────────────────────────────────────────────
    def _machine(self) -> Dict[str, Any]:
        mw = self._mainwin
        vid = ""
        try:
            from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
            vid = resolve_local_vehicle_id(mw) or ""
        except Exception:
            pass
        return {"id": vid, "name": str(getattr(mw, "machine_name", "") or ""),
                "role": str(getattr(mw, "host_role", "") or "")}

    def _snapshot(self) -> Dict[str, Any]:
        agents = []
        try:
            from utils import agent_status as _as
            with _as._lock:
                ready = {k: dict(v) for k, v in _as._status.items()}
        except Exception:
            ready = {}
        for a in list(getattr(self._mainwin, "agents", None) or []):
            card = getattr(a, "card", None)
            aid = str(getattr(card, "id", "") or "")
            agents.append({"id": aid, "name": str(getattr(card, "name", "") or ""),
                           "running": bool(getattr(a, "_running", False)),
                           "status": str(getattr(a, "status", "") or ""),
                           "readiness": ready.get(aid)})
        with self._lock:
            tasks = list(self._task_status.values())[-50:]
        return {"kind": "snapshot", "ts": int(time.time() * 1000), "agents": agents, "tasks": tasks,
                "log_tail": self._tail is not None}

    # ── sending ──────────────────────────────────────────────────────────
    def _take_batch(self) -> List[dict]:
        batch, size = [], 0
        with self._lock:
            while self._events and len(batch) < MAX_EVENTS_PER_SEND:
                ev = self._events[0]
                n = len(json.dumps(ev, ensure_ascii=False, default=str))
                if batch and size + n > MAX_SEND_BYTES:
                    break
                batch.append(self._events.popleft())
                size += n
        return batch

    async def _send(self, events: List[dict]) -> bool:
        from agent.chats.wan_chat import wanSendMessage8
        body = {"v": 1, "machine": self._machine(), "events": events}
        if self._tail is not None and self._tail.dropped:
            body["log_dropped"], self._tail.dropped = self._tail.dropped, 0
        req = {"chatID": FEED_CHANNEL, "sender": body["machine"]["id"] or "desktop",
               "receiver": "staff", "type": "fleet_feed",
               "contents": json.dumps(body, ensure_ascii=False, default=str),
               "parameters": json.dumps({})}
        resp = await wanSendMessage8(req, self._mainwin)
        return isinstance(resp, dict) and not resp.get("errors") and bool(resp.get("data"))

    async def _flush_loop(self) -> None:
        last_snapshot = 0.0
        while True:
            try:
                await asyncio.sleep(FLUSH_S)
                now = time.monotonic()
                if self._tail is not None and now >= self._tail_until:
                    self._stop_tail("expired")
                if self._snapshot_due or now - last_snapshot >= SNAPSHOT_S:
                    self._snapshot_due = False
                    last_snapshot = now
                    snap = self._snapshot()          # takes the lock itself: build it first
                    with self._lock:
                        self._events.append(snap)
                if now < self._backoff_until:
                    continue
                batch = self._take_batch()
                if not batch:
                    continue
                if await self._send(batch):
                    self._fail_streak = 0
                else:
                    with self._lock:           # keep them; the ring drops the oldest
                        self._events.extendleft(reversed(batch))
                    self._fail_streak += 1
                    wait = min(300.0, FLUSH_S * (2 ** min(self._fail_streak, 7)))
                    self._backoff_until = time.monotonic() + wait
                    if self._fail_streak in (1, 5) or self._fail_streak % 20 == 0:
                        logger.warning(f"{_TAG} cloud did not take the feed "
                                       f"({self._fail_streak}x); retrying in {wait:.0f}s")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"{_TAG} flush tick failed: {e}")

    # ── commands from the web ────────────────────────────────────────────
    def _start_tail(self, ttl_s: float, level: str) -> None:
        lvl = getattr(logging, str(level or "INFO").upper(), logging.INFO)
        self._tail_until = time.monotonic() + max(10.0, min(float(ttl_s or 300), LOG_TTL_MAX_S))
        if self._tail is None:
            self._tail = _TailHandler(self, lvl)
            logger.logger.addHandler(self._tail)
        else:
            self._tail.setLevel(lvl)
        logger.info(f"{_TAG} log tail on (level={logging.getLevelName(lvl)})")

    def _stop_tail(self, why: str) -> None:
        if self._tail is not None:
            try:
                logger.logger.removeHandler(self._tail)
            except Exception:
                pass
            self._tail = None
            logger.info(f"{_TAG} log tail off ({why})")
        self._snapshot_due = True

    def handle_command(self, msg: Dict[str, Any]) -> None:
        if (msg or {}).get("type") != "fleet_cmd":
            return
        try:
            c = msg.get("contents")
            cmd = json.loads(c) if isinstance(c, str) else (c or {})
        except Exception:
            return
        target = str(cmd.get("machine") or "*")
        if target not in ("*", self._machine()["id"]):
            return
        what = cmd.get("cmd")
        if what == "log_start":
            self._start_tail(cmd.get("ttl_s") or 300, cmd.get("level") or "INFO")
            self._snapshot_due = True
        elif what == "log_stop":
            self._stop_tail("requested")
        elif what in ("ping", "snapshot"):
            self._snapshot_due = True

    async def _cmd_loop(self) -> None:
        """Listen on fleet.cmd (AppSync-compatible graphql-ws; CN TCB and intl)."""
        import aiohttp
        import certifi
        import ssl
        from agent.chats.wan_chat import _resolve_ws_token
        from agent.cloud_api.cloud_api import gen_wan_subscription_connection_string
        from agent.cloud_api.endpoints import get_endpoint_config
        backoff = 5.0
        while True:
            try:
                cfg = get_endpoint_config()
                mw = self._mainwin
                token = _resolve_ws_token(mw, mw.get_auth_token() if hasattr(mw, "get_auth_token") else None)
                if not token and not getattr(cfg, "api_key", None):
                    await asyncio.sleep(60)
                    continue
                auth = token.split("/@@/", 1)[-1] if token and "/@@/" in token else token
                url = cfg.build_ws_url(auth)
                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
                timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=330)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(url, protocols=["graphql-ws"], ssl=ssl_ctx,
                                                  heartbeat=25, autoping=True) as ws:
                        await ws.send_str(json.dumps({"type": "connection_init"}))
                        sub = {"id": "fleet-cmd", "type": "start", "payload": {
                            "data": json.dumps({"query": gen_wan_subscription_connection_string(),
                                                "variables": {"chatID": CMD_CHANNEL}}),
                            "extensions": {"authorization": {"host": cfg.host, "Authorization": auth}
                                           if auth else {"host": cfg.host, "x-api-key": cfg.api_key}}}}
                        started = False
                        async for m in ws:
                            if m.type != aiohttp.WSMsgType.TEXT:
                                break
                            f = json.loads(m.data)
                            t = f.get("type")
                            if t == "connection_ack" and not started:
                                await ws.send_str(json.dumps(sub))
                                started = True
                            elif t == "start_ack":
                                backoff = 5.0
                                logger.info(f"{_TAG} listening for commands on {CMD_CHANNEL}")
                            elif t == "data":
                                inner = ((f.get("payload") or {}).get("data") or {}).get("onMessageReceived")
                                if inner:
                                    self.handle_command(inner)
                            elif t in ("error", "connection_error"):
                                logger.info(f"{_TAG} command channel refused: {str(f)[:200]}")
                                break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"{_TAG} command channel dropped: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300.0)


_FEED = FleetFeed()


def get_feed() -> FleetFeed:
    return _FEED
