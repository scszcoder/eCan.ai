"""The desktop app's A2A gateway: two-way messages between cloud agents (the Manager) and
the agents on this machine.

One gateway per app. It holds ONE subscription for the whole machine
(``onA2AMessageForMachine``), catches up on what arrived while the app was off
(``getA2AMessages``), and for each message:

- an envelope ``request`` (payload ``{"v": 1, "kind": "request", ...}``): ack it within
  seconds, check the allowlist, do it (``tool_call``: a curated MCP tool, in-process;
  ``run_skill``: ``run_skill_for_store``, answered when that run finishes; ``notify`` /
  ``ask_user`` for a named agent: handed to that agent), send ``progress`` while it runs
  and exactly one ``response``;
- a ``cancel``: stop the matching run if it is still waiting;
- anything else (plain A2A JSON-RPC, or an envelope reply for a local agent): handed to
  the named local agent, as the per-agent bridge always did.

Local -> cloud: ``send()`` (e.g. a skill telling the Manager "sign-in needed").
The contract is the server note "the cloud Manager and two-way cloud <-> local agent A2A";
until the server has it, every call fails with a schema error, logged once, and the app
works as before.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

V = 1
KINDS = ("request", "ack", "progress", "response", "event", "cancel")
ACK_STATUSES = ("delivered", "accepted", "rejected")
# Read-side tools a cloud agent may call on this machine (spec D9 curated list).
DEFAULT_TOOLS = ("ec_table_query", "ec_kb", "ec_unit_economics", "ec_schemas_get", "find_skill",
                 "list_worker_agents", "get_task_progress", "run_skill_for_store", "ping")
# Skills a cloud agent may start without asking: read-only / draft-only ones.
DEFAULT_SKILLS = ("google_ads_review",)
SKILL_STARTING_TOOLS = ("run_skill_for_store",)
PROGRESS_EVERY_S = 60
RUN_DEADLINE_S = 6 * 3600         # a run still unanswered after this is reported failed
SEEN_MAX = 2000
HEARTBEAT_S = 60
ENDPOINT_TTL_S = 180
POLL_S = 30                       # when the machine subscription is unavailable


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(s: Any) -> Optional[float]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def parse(payload: Any) -> Optional[Dict[str, Any]]:
    """The envelope in an A2A message payload, or None for a plain (non-envelope) payload."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict) or payload.get("v") != V or payload.get("kind") not in KINDS:
        return None
    return payload


def make(kind: str, *, correlation_id: str, reply_to: str, **fields: Any) -> Dict[str, Any]:
    env = {"v": V, "kind": kind, "msg_id": "", "correlation_id": correlation_id, "reply_to": reply_to,
           "created_at": now_iso()}
    env.update({k: v for k, v in fields.items() if v is not None})
    return env


# ── allowlist ─────────────────────────────────────────────────────────────────

def _allowlist_file() -> Path:
    from agent.ec_skills.ecom.store import home
    return home() / "a2a_allowlist.json"


def allowlist() -> Dict[str, List[str]]:
    """{"tools": [...], "skills": [...]}: the defaults, or the owner's file when it exists."""
    try:
        data = json.loads(_allowlist_file().read_text(encoding="utf-8"))
        return {"tools": list(data.get("tools") or DEFAULT_TOOLS), "skills": list(data.get("skills") or DEFAULT_SKILLS)}
    except (OSError, ValueError):
        return {"tools": list(DEFAULT_TOOLS), "skills": list(DEFAULT_SKILLS)}


def check_allowed(intent: str, task: Dict[str, Any]) -> Optional[str]:
    """None when allowed, else why not."""
    allow = allowlist()
    tool = str(task.get("tool") or "")
    tool_input = task.get("input") if isinstance(task.get("input"), dict) else {}
    if intent == "tool_call":
        if tool not in allow["tools"]:
            return f"tool {tool!r} is not on this machine's allowlist"
        if tool in SKILL_STARTING_TOOLS:
            skill = str((tool_input.get("input") or tool_input).get("skill_name") or
                        (tool_input.get("input") or tool_input).get("skill_id") or "")
            if skill not in allow["skills"]:
                return f"skill {skill!r} may not be started from the cloud"
        return None
    if intent == "run_skill":
        return None if str(task.get("skill") or "") in allow["skills"] else \
            f"skill {task.get('skill')!r} may not be started from the cloud"
    if intent in ("notify", "ask_user"):
        return None
    return f"unknown intent {intent!r}"


# ── GraphQL (contract: the server note, section 2) ─────────────────────────────

_FIELDS = "id toAgentId toMachineId fromAgentId org payload createdAt status"
GQL_SEND = ("mutation SendA2AMessage($input: A2AMessageInput!) { sendA2AMessage(input: $input) { %s } }" % _FIELDS)
GQL_SUB = ("subscription OnA2AMessageForMachine($toMachineId: ID!) { onA2AMessageForMachine(toMachineId: $toMachineId) "
           "{ %s } }" % _FIELDS)
GQL_LIST = ("query GetA2AMessages($toMachineId: ID!, $since: AWSDateTime, $status: String, $limit: Int) "
            "{ getA2AMessages(toMachineId: $toMachineId, since: $since, status: $status, limit: $limit) { %s } }" % _FIELDS)
GQL_ACK = "mutation AckA2AMessage($id: ID!, $status: String!) { ackA2AMessage(id: $id, status: $status) { id status } }"
GQL_UPSERT = ("mutation UpsertAgentEndpoint($input: AgentEndpointInput!) { upsertAgentEndpoint(input: $input) "
              "{ id machineId } }")

Transport = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


def _looks_like_missing_schema(err: Exception) -> bool:
    msg = str(err).lower()
    return any(s in msg for s in ("cannot query field", "unknown type", "unknown field", "not defined",
                                  "validation", "no field", "does not exist"))


class Gateway:
    def __init__(self, *, mainwin: Any, machine_id: str, org: str, post: Transport,
                 subscribe: Optional[Callable[[Callable[[Dict[str, Any]], Awaitable[None]]], Awaitable[None]]] = None,
                 bridge: Optional[Callable[[str, dict], Awaitable[None]]] = None,
                 tools: Optional[Dict[str, Callable]] = None, state_dir: Optional[Path] = None) -> None:
        self.mainwin, self.machine_id, self.org = mainwin, machine_id, org
        self.address = f"machine_{machine_id}"
        self._post, self._subscribe, self._bridge, self._tools = post, subscribe, bridge, tools
        self._seen: "OrderedDict[str, None]" = OrderedDict()
        self._running: Dict[str, Dict[str, Any]] = {}      # correlation_id -> {reply_to, task_id, thread_id, ...}
        self._lock = threading.RLock()
        self._schema_warned = False
        self._tasks: List[asyncio.Task] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._state_file = (state_dir or Path.home() / ".ecan") / "a2a_gateway_state.json"

    # ---- lifecycle -----------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        for coro in (self._inbox_loop(), self._heartbeat_loop(), self._progress_loop()):
            self._tasks.append(loop.create_task(coro))
        logger.info(f"[a2a-gateway] started for machine {self.machine_id[:8]}.. (org={self.org})")

    def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    # ---- transport -----------------------------------------------------------

    async def _gql(self, query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return await self._post(query, variables)
        except Exception as e:
            if _looks_like_missing_schema(e):
                if not self._schema_warned:
                    self._schema_warned = True
                    logger.warning(f"[a2a-gateway] the server has no A2A gateway contract yet ({e}); "
                                   f"cloud <-> local messages are off until it is deployed")
            else:
                logger.warning(f"[a2a-gateway] GraphQL call failed: {e}")
            return None

    async def send(self, to_agent_id: str, envelope: Dict[str, Any], to_machine_id: Optional[str] = None) -> Optional[str]:
        """Send *envelope* to an agent (cloud or another machine). Returns the stored message id."""
        env = dict(envelope)
        env.setdefault("v", V)
        env.setdefault("created_at", now_iso())
        out = await self._gql(GQL_SEND, {"input": {"toAgentId": to_agent_id, "toMachineId": to_machine_id,
                                                   "fromAgentId": self.address, "org": self.org,
                                                   "payload": json.dumps(env, ensure_ascii=False, default=str)}})
        msg = ((out or {}).get("data") or {}).get("sendA2AMessage") or {}
        return msg.get("id")

    async def _reply(self, req: Dict[str, Any], kind: str, **fields: Any) -> None:
        to = req.get("reply_to") or req.get("_from") or ""
        if not to:
            logger.warning(f"[a2a-gateway] {kind} for {req.get('correlation_id')} has nobody to go to")
            return
        await self.send(to, make(kind, correlation_id=req.get("correlation_id") or req.get("msg_id") or "",
                                 reply_to=self.address, thread_id=req.get("thread_id"), **fields))

    # ---- inbound -------------------------------------------------------------

    async def _inbox_loop(self) -> None:
        await self.catch_up()
        if self._subscribe is not None:
            try:
                await self._subscribe(self._on_envelope)
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.info(f"[a2a-gateway] machine subscription unavailable ({e}); polling every {POLL_S}s")
        while True:                              # no push (or it failed): poll the stored messages
            await asyncio.sleep(POLL_S)
            await self.catch_up()

    async def _on_envelope(self, envelope: Dict[str, Any]) -> None:
        data = (envelope.get("payload") or {}).get("data") or {}
        msg = data.get("onA2AMessageForMachine")
        if msg:
            await self.handle(msg)

    async def catch_up(self) -> int:
        """Messages stored for this machine since the last one seen, oldest first."""
        st = self._load_state()
        out = await self._gql(GQL_LIST, {"toMachineId": self.address, "since": st.get("since"), "status": None,
                                         "limit": 200})
        msgs = ((out or {}).get("data") or {}).get("getA2AMessages") or []
        for m in sorted(msgs, key=lambda m: str(m.get("createdAt") or "")):
            await self.handle(m)
        return len(msgs)

    async def handle(self, msg: Dict[str, Any]) -> str:
        """One stored A2A message for this machine. Returns what was done (for logs and tests)."""
        mid = str(msg.get("id") or "")
        if mid:
            with self._lock:
                if mid in self._seen:
                    return "duplicate"
                self._seen[mid] = None
                while len(self._seen) > SEEN_MAX:
                    self._seen.popitem(last=False)
            self._save_state(since=msg.get("createdAt"))
        env = parse(msg.get("payload"))
        to_agent = str(msg.get("toAgentId") or "")
        if env is None or env["kind"] not in ("request", "cancel"):     # plain A2A, or a reply for a local agent
            return await self._to_local_agent(to_agent, msg)
        env = {**env, "msg_id": env.get("msg_id") or mid, "_from": msg.get("fromAgentId"),
               "_to": "" if to_agent == self.address else to_agent}
        env.setdefault("correlation_id", env["msg_id"])
        if env["kind"] == "cancel":
            return await self._cancel(env)
        return await self._request(env, mid)

    async def _to_local_agent(self, to_agent: str, msg: Dict[str, Any]) -> str:
        if not to_agent or self._bridge is None:
            logger.warning(f"[a2a-gateway] message {msg.get('id')} names no local agent; dropped")
            return "dropped"
        payload = msg.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {"_raw": payload}
        if isinstance(payload, dict):
            payload.setdefault("_a2a_from", msg.get("fromAgentId"))
            payload.setdefault("_a2a_via", "a2a_gateway")
        await self._bridge(to_agent, payload if isinstance(payload, dict) else {"_raw": payload})
        return "forwarded"

    async def _request(self, env: Dict[str, Any], mid: str) -> str:
        deadline = _parse_time(env.get("deadline"))
        if deadline is not None and deadline < time.time():
            await self._ack(mid, "rejected")
            await self._reply(env, "response", status="expired",
                              error={"code": "EXPIRED", "message": "the request's deadline passed before it could start"})
            return "expired"
        intent, task = str(env.get("intent") or ""), env.get("task") if isinstance(env.get("task"), dict) else {}
        why = check_allowed(intent, task)
        if why:
            await self._ack(mid, "rejected")
            await self._reply(env, "ack", status="rejected", error={"code": "NOT_ALLOWED", "message": why})
            return "rejected"
        with self._lock:
            if env["correlation_id"] in self._running:   # already running: say so, don't start twice
                await self._reply(env, "progress", status="running", progress={"step": "already running"})
                return "already_running"
        await self._ack(mid, "accepted")
        await self._reply(env, "ack", status="accepted")
        if intent == "tool_call":
            return await self._tool_call(env, task)
        if intent == "run_skill":
            return await self._tool_call(env, {"tool": "run_skill_for_store", "input": {"input": {
                "skill_name": task.get("skill"), "store_id": task.get("store_id")}}}, wait_for_run=True)
        to_agent = str(task.get("agent_id") or env.get("_to") or "")
        if not to_agent:
            await self._reply(env, "response", status="failed",
                              error={"code": "NO_HANDLER", "message": "no local agent named for this message"})
            return "no_handler"
        await self._to_local_agent(to_agent, {"id": env["msg_id"], "fromAgentId": env.get("_from"),
                                              "payload": json.dumps(env, ensure_ascii=False, default=str)})
        await self._reply(env, "response", status="done", result={"delivered_to": to_agent})
        return "forwarded"

    async def _ack(self, mid: str, status: str) -> None:
        if mid:
            await self._gql(GQL_ACK, {"id": mid, "status": status})

    def _tool_map(self) -> Dict[str, Callable]:
        if self._tools is not None:
            return self._tools
        from agent.mcp.server.server import tool_function_mapping
        return tool_function_mapping

    async def _tool_call(self, env: Dict[str, Any], task: Dict[str, Any], wait_for_run: bool = False) -> str:
        tool = str(task.get("tool") or "")
        args = task.get("input") if isinstance(task.get("input"), dict) else {}
        if tool == "ping":
            await self._reply(env, "response", status="done", result={"pong": True, "machine": self.address})
            return "done"
        fn = self._tool_map().get(tool)
        if fn is None:
            await self._reply(env, "response", status="failed",
                              error={"code": "NO_HANDLER", "message": f"no tool {tool!r} on this machine"})
            return "no_handler"
        try:
            res = fn(self.mainwin, args)
            res = await res if asyncio.iscoroutine(res) else res
        except Exception as e:
            await self._reply(env, "response", status="failed", error={"code": "TOOL_ERROR", "message": str(e)[:500]})
            return "failed"
        text, meta = _tool_output(res)
        started = meta.get("task_result") if isinstance(meta.get("task_result"), dict) else {}
        if wait_for_run or tool in SKILL_STARTING_TOOLS:
            if not started.get("success") or not started.get("task_id"):
                await self._reply(env, "response", status="failed",
                                  error={"code": "NOT_STARTED", "message": text[:500] or "the run did not start"})
                return "failed"
            with self._lock:
                self._running[env["correlation_id"]] = {
                    "reply_to": env.get("reply_to") or env.get("_from"), "thread_id": env.get("thread_id"),
                    "task_id": str(started["task_id"]), "started": time.time(), "last_progress": time.time(),
                    "deadline": _parse_time(env.get("deadline")) or time.time() + RUN_DEADLINE_S,
                    "what": started.get("task_name") or tool}
            await self._reply(env, "progress", status="running",
                              progress={"step": text[:300] or "queued"}, result={"task_id": started["task_id"]})
            return "running"
        await self._reply(env, "response", status="done", result={"text": text[:20000], "data": started or None})
        return "done"

    async def _cancel(self, env: Dict[str, Any]) -> str:
        with self._lock:
            run = self._running.pop(env["correlation_id"], None)
        if run is None:
            return "nothing_to_cancel"
        stopped = False
        try:
            from agent.ec_tasks.task_mcp_tools import stop_agent_task
            stopped = bool((stop_agent_task(self.mainwin, {"task_id": run["task_id"]}) or {}).get("success"))
        except Exception as e:
            logger.warning(f"[a2a-gateway] could not stop task {run['task_id']}: {e}")
        await self._reply({**env, "reply_to": run["reply_to"], "thread_id": run["thread_id"]}, "response",
                          status="failed", error={"code": "CANCELLED", "message": "cancelled" + ("" if stopped else
                                                                                               " (the run may still finish)")})
        return "cancelled"

    # ---- runs finishing (called by the task runner) ----------------------------

    def task_finished(self, task_id: str, ok: bool, result: Any) -> None:
        """A task on this machine finished; if a cloud request is waiting on it, answer."""
        with self._lock:
            hit = next(((c, r) for c, r in self._running.items() if r["task_id"] == str(task_id)), None)
            if hit is None:
                return
            self._running.pop(hit[0], None)
        corr, run = hit
        req = {"correlation_id": corr, "reply_to": run["reply_to"], "thread_id": run["thread_id"]}
        fields = ({"status": "done", "result": {"message": _run_message(result), "task_id": task_id}} if ok else
                  {"status": "failed", "error": {"code": "RUN_FAILED", "message": _run_message(result)[:1000]}})
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._reply(req, "response", **fields), self._loop)

    async def _progress_loop(self) -> None:
        while True:
            await asyncio.sleep(PROGRESS_EVERY_S)
            await self.progress_tick()

    async def progress_tick(self) -> None:
        now = time.time()
        with self._lock:
            runs = list(self._running.items())
        for corr, run in runs:
            req = {"correlation_id": corr, "reply_to": run["reply_to"], "thread_id": run["thread_id"]}
            if now > run["deadline"]:
                with self._lock:
                    self._running.pop(corr, None)
                await self._reply(req, "response", status="failed",
                                  error={"code": "TIMEOUT", "message": f"{run['what']} did not finish in time"})
            elif now - run["last_progress"] >= PROGRESS_EVERY_S:
                run["last_progress"] = now
                await self._reply(req, "progress", status="running",
                                  progress={"step": f"{run['what']} running {int((now - run['started']) // 60)} min"})

    # ---- presence ----------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while True:
            await self.heartbeat()
            await asyncio.sleep(HEARTBEAT_S)

    async def heartbeat(self) -> None:
        """The machine's endpoint record: what it can run, seen every minute (presence)."""
        import socket
        await self._gql(GQL_UPSERT, {"input": {
            "id": self.address, "machineId": self.machine_id, "org": self.org, "name": socket.gethostname(),
            "role": "machine", "skills": ",".join(allowlist()["skills"]), "skillsHash": "",
            "a2aRelayChannel": self.address, "lanHint": None, "ecanVer": "", "os": "", "ttl": ENDPOINT_TTL_S}})

    # ---- state -------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, since: Any) -> None:
        if not since:
            return
        try:
            st = self._load_state()
            if str(since) > str(st.get("since") or ""):
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                self._state_file.write_text(json.dumps({"since": since}), encoding="utf-8")
        except OSError as e:
            logger.debug(f"[a2a-gateway] could not save state: {e}")


def _tool_output(res: Any) -> tuple:
    """(text, meta) from an MCP tool's return (a list of TextContent, or a dict)."""
    if isinstance(res, dict):
        return json.dumps(res, ensure_ascii=False, default=str), {"task_result": res}
    texts, meta = [], {}
    for item in res if isinstance(res, list) else [res]:
        t = getattr(item, "text", None)
        if t:
            texts.append(str(t))
        m = getattr(item, "meta", None)
        if isinstance(m, dict):
            meta.update(m)
    return "\n".join(texts), meta


def _run_message(result: Any) -> str:
    """What a finished run said: its chat reply when it has one."""
    if isinstance(result, dict):
        llm = ((result.get("result") or {}).get("llm_result") or {}) if isinstance(result.get("result"), dict) else {}
        msg = llm.get("message") if isinstance(llm, dict) else None
        if msg:
            return str(msg)[:20000]
    return "" if result is None else str(result)[:2000]


# ── process singleton ───────────────────────────────────────────────────────────

_gateway: Optional[Gateway] = None


def start_gateway(*, config: Any, mainwin: Any, machine_id: str, org: str, loop: asyncio.AbstractEventLoop,
                  bridge: Optional[Callable[[str, dict], Awaitable[None]]] = None) -> Optional[Gateway]:
    """Start the app's gateway on the AppSync config the cloud directory uses (idempotent)."""
    global _gateway
    if _gateway is not None:
        return _gateway
    from agent.ec_tasks.appsync_pubsub import _post_graphql, _subscribe

    async def post(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        # the signed-in user's token, so the server takes the org from a verified identity
        return await _post_graphql(config.http_endpoint, api_key=config.api_key, query=query,
                                   variables=variables, auth_token=getattr(config, "auth_token", None))

    async def subscribe(on_envelope):
        await _subscribe(config=config, query=GQL_SUB, variables={"toMachineId": f"machine_{machine_id}"},
                         operation_name="OnA2AMessageForMachine", field_name="onA2AMessageForMachine",
                         on_envelope=on_envelope, max_retries=5, max_idle_sec=600)

    try:
        gw = Gateway(mainwin=mainwin, machine_id=machine_id, org=org, post=post, subscribe=subscribe, bridge=bridge)
        gw.start(loop)
        _gateway = gw
        return gw
    except Exception as e:
        logger.warning(f"[a2a-gateway] start failed: {e}")
        return None


def get_gateway() -> Optional[Gateway]:
    return _gateway


def task_finished(task_id: str, ok: bool, result: Any) -> None:
    """Hook for the task runner: never raises."""
    try:
        if _gateway is not None:
            _gateway.task_finished(task_id, ok, result)
    except Exception as e:
        logger.debug(f"[a2a-gateway] task_finished hook: {e}")


def new_request(intent: str, task: Dict[str, Any], reply_to: str, thread_id: Optional[str] = None,
                deadline: Optional[str] = None) -> Dict[str, Any]:
    """A request envelope (used by tests and by local agents asking a cloud agent)."""
    cid = uuid.uuid4().hex
    return make("request", correlation_id=cid, reply_to=reply_to, msg_id=cid, intent=intent, task=task,
                thread_id=thread_id, deadline=deadline)
