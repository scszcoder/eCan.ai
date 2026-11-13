"""The desktop app's A2A gateway: two-way messages between cloud agents (the Manager) and
the agents on this machine.

One gateway per app. It holds ONE subscription for the whole machine
(``onA2AMessageForMachine``), catches up on what arrived while the app was off
(``getA2AMessages``), and for each message:

- an envelope ``request`` (payload ``{"v": 1, "kind": "request", ...}``): ack it within
  seconds, check the allowlist, do it (``tool_call``: a curated MCP tool, in-process;
  ``run_skill``: ``run_skill_for_store``, answered when that run finishes; ``notify`` /
  ``ask_user`` for a named agent: handed to that agent; ``get_agent_status``: each subject's
  status report as a ``progress``, then all of them; ``status_diagnose``: a scrubbed log tail
  or file excerpt), send ``progress`` while it runs and exactly one ``response``;
- a ``cancel``: stop the matching run if it is still waiting;
- anything else (plain A2A JSON-RPC, or an envelope reply for a local agent): handed to
  the named local agent, as the per-agent bridge always did.

Local -> cloud: ``send()`` (e.g. a skill telling the Manager "sign-in needed"), and an
``event`` when a status provider first reports a needs-human anomaly, and a ``status_report``
event per team (when its health or running state changes, at least every 12 minutes) so the
cloud keeps the last known progress after this machine goes down.
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
# list_chat_agents = the owner's agents and their tasks; list_worker_agents only knows workers
# spawned during a run. list_stores, machine_tree, store_reports (the latest saved store check
# of each store) and ping are answered by the gateway itself.
DEFAULT_TOOLS = ("ec_table_query", "ec_kb", "ec_unit_economics", "ec_schemas_get", "find_skill",
                 "list_chat_agents", "list_stores", "machine_tree", "store_reports", "list_worker_agents", "get_task_progress",
                 "run_skill_for_store", "ping", "get_agent_status", "status_diagnose")
# Skills a cloud agent may start (it asks the owner in chat first): read-only / draft-only ones.
DEFAULT_SKILLS = ("google_ads_review", "shopify_after_sales", "amazon_after_sales", "etsy_after_sales",
                  "ebay_after_sales")
SKILL_STARTING_TOOLS = ("run_skill_for_store",)
PROGRESS_EVERY_S = 60
RUN_DEADLINE_S = 6 * 3600         # a run still unanswered after this is reported failed
SEEN_MAX = 2000
HEARTBEAT_S = 60
ENDPOINT_TTL_S = 180
POLL_S = 30                       # when the machine subscription is unavailable
STATUS_INTENTS = ("get_agent_status", "status_diagnose")
ANOMALY_EVERY_S = 300             # status providers are run this often to spot new needs-human anomalies
STATUS_REPORT_EVERY_S = 720       # a team's status_report goes out at least this often while it is unchanged
NUDGE_SETTLE_S = 5                # after a run starts/stops, wait this long before reporting the new state
MANAGER_ADDRESS = "manager"       # where anomaly events go until a Manager has asked this machine for status
RESPONSE_MAX_BYTES = 48_000       # a get_agent_status response above this carries summaries (full reports went as progress)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(s: Any) -> Optional[float]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def parse(payload: Any) -> Optional[Dict[str, Any]]:
    """The envelope in an A2A message payload, or None for a plain (non-envelope) payload.
    Up to two JSON layers: stored messages read back by getA2AMessages came JSON-encoded twice."""
    for _ in range(2):
        if not isinstance(payload, str):
            break
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict) or payload.get("v") != V or payload.get("kind") not in KINDS:
        return None
    return payload


def _shape(payload: Any) -> str:
    """Why a payload is not an envelope, without its content: type, top-level keys, v and kind."""
    p = payload
    for _ in range(2):
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except ValueError:
                return f"is text that is not JSON ({len(payload)} chars)"
    if not isinstance(p, dict):
        return f"is {type(p).__name__} (after decoding {type(payload).__name__})"
    return f"keys={sorted(p)[:12]} v={p.get('v')!r} kind={p.get('kind')!r} (was {type(payload).__name__})"


def list_stores(mainwin: Any, include_archived: bool = False) -> List[Dict[str, Any]]:
    """The store catalog (what the Stores page shows) with the agents and tasks serving each store.
    The browser profile id is left out: it never leaves this machine."""
    from agent.ec_agents.store_catalog import _svc, delete_plan
    out = []
    for s in _svc(mainwin).list_stores(include_archived=include_archived):
        plan = delete_plan(mainwin, s.get("store_id"))          # read-only: who serves this store
        agents = {a["id"]: a["name"] for a in plan["agents"] + plan["kept_agents"]}
        out.append({"store_id": s.get("store_id"), "name": s.get("name"), "platform": s.get("platform"),
                    "store_urls": s.get("store_urls") or [], "status": s.get("status"),
                    "agents": [{"id": i, "name": n} for i, n in agents.items()],
                    "tasks": [t["name"] or t["id"] for t in plan["tasks"]]})
    return out


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


def tool_args(task: Dict[str, Any]) -> Dict[str, Any]:
    """A tool_call's arguments as MCP tools take them, {"input": {...}}. The task may carry them
    under "input" or "args", either already in that shape or flat."""
    args = next((task[k] for k in ("input", "args") if isinstance(task.get(k), dict)), {})
    return args if isinstance(args.get("input"), dict) else {"input": args}


def check_allowed(intent: str, task: Dict[str, Any]) -> Optional[str]:
    """None when allowed, else why not."""
    allow = allowlist()
    tool = str(task.get("tool") or "")
    tool_input = tool_args(task)
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
    if intent in STATUS_INTENTS:         # on the tools allowlist, so the owner's file can turn them off
        return None if intent in allow["tools"] else f"{intent} is not on this machine's allowlist"
    if intent in ("notify", "ask_user"):
        return None
    return f"unknown intent {intent!r}"


# ── GraphQL (contract: the server note, section 2) ─────────────────────────────

_FIELDS = "id toAgentId toMachineId fromAgentId org payload createdAt status"
GQL_SEND = ("mutation SendA2AMessage($input: A2AMessageInput!) { sendA2AMessage(input: $input) { %s } }" % _FIELDS)
GQL_SUB = ("subscription OnA2AMessageForMachine($toMachineId: ID!) { onA2AMessageForMachine(toMachineId: $toMachineId) "
           "{ %s } }" % _FIELDS)
GQL_LIST = ("query GetA2AMessages($toMachineId: ID!, $since: AWSDateTime, $status: String, $limit: Int) "
            "{ getA2AMessages(toMachineId: $toMachineId, since: $since, status: $status, limit: $limit) "
            "{ items { %s } nextToken } }" % _FIELDS)
CATCH_UP_PAGES = 10               # x 200 messages; later pages wait for the next catch-up
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
        self._sent_n: Dict[tuple, int] = {}                 # (correlation_id, kind) -> replies sent
        self._lock = threading.RLock()
        self._schema_warned = False
        self._tasks: List[asyncio.Task] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._state_file = (state_dir or Path.home() / ".ecan") / "a2a_gateway_state.json"
        self._caps_off = False             # the server's endpoint record takes no capabilities (yet)
        self._nudge: Optional[asyncio.Event] = None   # set when a run starts/stops: report status now

    # ---- lifecycle -----------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._nudge = asyncio.Event()
        for coro in (self._inbox_loop(), self._heartbeat_loop(), self._progress_loop(), self._anomaly_loop()):
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
            if type(e).__name__ == "Unauthorized":     # already logged once by the transport; it backs off
                logger.debug(f"[a2a-gateway] GraphQL call skipped: {e}")
            elif _looks_like_missing_schema(e):
                if not self._schema_warned:
                    self._schema_warned = True
                    logger.warning(f"[a2a-gateway] the server has no A2A gateway contract yet ({e}); "
                                   f"cloud <-> local messages are off until it is deployed")
            else:
                logger.warning(f"[a2a-gateway] GraphQL call failed: {e}")
            return None

    async def send(self, to_agent_id: str, envelope: Dict[str, Any], to_machine_id: Optional[str] = None) -> Optional[str]:
        """Send *envelope* to an agent (cloud or another machine). Returns the stored message id.
        A failed send is tried once more with the same ``msg_id``, so the server stores it once."""
        env = dict(envelope)
        env.setdefault("v", V)
        env.setdefault("created_at", now_iso())
        if not env.get("msg_id"):
            env["msg_id"] = uuid.uuid4().hex
        variables = {"input": {"toAgentId": to_agent_id, "toMachineId": to_machine_id, "fromAgentId": self.address,
                               "org": self.org, "payload": json.dumps(env, ensure_ascii=False, default=str)}}
        size = len(variables["input"]["payload"])
        for attempt in range(2):
            out = await self._gql(GQL_SEND, variables)
            msg = ((out or {}).get("data") or {}).get("sendA2AMessage") or {}
            if msg.get("id") or self._schema_warned:
                logger.info(f"[a2a-gateway] sent {env.get('kind')} {env['msg_id']} to {to_agent_id} ({size} bytes)")
                return msg.get("id")
            if attempt == 0:
                await asyncio.sleep(2)
        logger.warning(f"[a2a-gateway] could not send {env.get('kind')} {env['msg_id']} to {to_agent_id} "
                       f"({size} bytes) after 2 tries")
        return None

    async def _reply(self, req: Dict[str, Any], kind: str, **fields: Any) -> None:
        to = req.get("reply_to") or req.get("_from") or ""
        corr = req.get("correlation_id") or req.get("msg_id") or ""
        if not to:
            logger.warning(f"[a2a-gateway] {kind} for {corr} has nobody to go to")
            return
        # Stable id per reply: ack and response once per request, progress numbered.
        with self._lock:
            n = self._sent_n[(corr, kind)] = self._sent_n.get((corr, kind), 0) + 1
        msg_id = f"{corr}:{kind}" + (f":{n}" if kind == "progress" or n > 1 else "")
        await self.send(to, make(kind, correlation_id=corr, reply_to=self.address, thread_id=req.get("thread_id"),
                                 msg_id=msg_id, **fields))
        if kind == "response":
            with self._lock:
                for key in [k for k in self._sent_n if k[0] == corr]:
                    self._sent_n.pop(key, None)

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

    async def _on_envelope(self, msg: Dict[str, Any]) -> None:
        # _subscribe hands over the onA2AMessageForMachine record itself; its payload is the AWSJSON envelope
        if isinstance(msg, dict) and msg:
            await self.handle(msg)

    async def catch_up(self) -> int:
        """Messages stored for this machine since the last one seen, oldest first. Pages by
        ``since`` (the newest createdAt handled), so the query needs no paging argument."""
        n = 0
        for _ in range(CATCH_UP_PAGES):
            since = self._load_state().get("since")
            out = await self._gql(GQL_LIST, {"toMachineId": self.address, "since": since, "status": None,
                                             "limit": 200})
            page = ((out or {}).get("data") or {}).get("getA2AMessages") or {}
            msgs = (page.get("items") or []) if isinstance(page, dict) else []
            for m in sorted(msgs, key=lambda m: str(m.get("createdAt") or "")):
                await self.handle(m)
            n += len(msgs)
            if not msgs or not page.get("nextToken") or self._load_state().get("since") == since:
                break
        return n

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
        task = env.get("task") if isinstance(env.get("task"), dict) else {}
        logger.info(f"[a2a-gateway] {env['kind']} {env['correlation_id']} from {env.get('_from')}: "
                    f"{env.get('intent')} {task.get('tool') or task.get('skill') or ''}")
        if env["kind"] == "cancel":
            return await self._cancel(env)
        return await self._request(env, mid)

    async def _to_local_agent(self, to_agent: str, msg: Dict[str, Any]) -> str:
        if not to_agent or self._bridge is None:
            logger.warning(f"[a2a-gateway] message {msg.get('id')} names no local agent; dropped "
                           f"(to={to_agent!r}, payload {_shape(msg.get('payload'))})")
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
        if intent == "tool_call" and task.get("tool") in STATUS_INTENTS:     # the same, sent as a tool call
            intent, task = str(task["tool"]), _tool_args(task)
        if intent == "get_agent_status":
            return await self._status(env, task)
        if intent == "status_diagnose":
            return await self._diagnose(env, task)
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
        args = tool_args(task)
        if tool == "ping":
            await self._reply(env, "response", status="done", result={"pong": True, "machine": self.address})
            return "done"
        if tool == "machine_tree":
            try:
                from agent.a2a.machine_tree import build
                tree = build(self.mainwin, self.address)
            except Exception as e:
                await self._reply(env, "response", status="failed", error={"code": "TOOL_ERROR", "message": str(e)[:500]})
                return "failed"
            # result.widget goes into the chat as is; result.data is the same tree for the model to read
            await self._reply(env, "response", status="done",
                              result={"text": json.dumps(tree["data"], ensure_ascii=False, default=str)[:20000],
                                      "data": tree["data"], "widget": tree["widget"]})
            return "done"
        if tool == "store_reports":
            try:
                from agent.ec_agents.store_catalog import _svc
                from agent.ec_skills.reports.store_checks import latest_reports
                inp = args["input"]
                reports = latest_reports(_svc(self.mainwin).list_stores(), store_id=str(inp.get("store_id") or ""),
                                         days=int(inp.get("days") or 1))
            except Exception as e:
                await self._reply(env, "response", status="failed", error={"code": "TOOL_ERROR", "message": str(e)[:500]})
                return "failed"
            await self._reply(env, "response", status="done",
                              result={"text": json.dumps(reports, ensure_ascii=False, default=str)[:20000],
                                      "data": {"stores": reports, "count": len(reports)}})
            return "done"
        if tool == "list_stores":
            try:
                stores = list_stores(self.mainwin, include_archived=bool(args["input"].get("include_archived")))
            except Exception as e:
                await self._reply(env, "response", status="failed", error={"code": "TOOL_ERROR", "message": str(e)[:500]})
                return "failed"
            await self._reply(env, "response", status="done",
                              result={"text": json.dumps(stores, ensure_ascii=False, default=str)[:20000],
                                      "data": {"stores": stores, "count": len(stores)}})
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

    # ---- agent status (docs/AGENT_STATUS_PROBING_DESIGN.md) ----------------------

    def _machine(self) -> Dict[str, Any]:
        from agent.status.providers import machine_info
        return machine_info(self.address)

    async def _status(self, env: Dict[str, Any], task: Dict[str, Any]) -> str:
        """One progress per subject (its report, as soon as it is ready), then one response."""
        from agent.status import providers as P
        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, P.local_agents, self.mainwin)
        jobs = P.resolve(task.get("subjects"), agents)
        machine = self._machine()
        self._save_state(manager=env.get("reply_to") or env.get("_from"))
        depth, since = str(task.get("depth") or "summary"), task.get("since")
        budget = float(task.get("budget_s") or P.BUDGET_S)

        async def one(subject: dict, members: list) -> dict:
            return await loop.run_in_executor(None, lambda: P.report_for(
                subject, members, machine=machine, depth=depth, since=since, budget_s=budget))
        reports: List[Dict[str, Any]] = []
        for fut in asyncio.as_completed([one(s, m) for s, m in jobs]):
            rep = await fut
            reports.append(rep)
            await self._reply(env, "progress", status="running", result={"report": rep},
                              progress={"step": "status_report", "subject": rep["subject"],
                                        "done": len(reports), "of": len(jobs)})
        full = len(json.dumps(reports, ensure_ascii=False, default=str)) <= RESPONSE_MAX_BYTES
        out = reports if full else [{k: r.get(k) for k in ("subject", "health", "headline", "progress", "as_of")}
                                    for r in reports]
        await self._reply(env, "response", status="done", result={"reports": out, "count": len(reports),
                                                                  "complete": full, "machine": machine,
                                                                  "as_of": now_iso()})
        return "done"

    async def _diagnose(self, env: Dict[str, Any], task: Dict[str, Any]) -> str:
        """A scrubbed log tail or file excerpt for one subject (the Manager asked the user first)."""
        from agent.status import providers as P
        from agent.status.diagnose import diagnose
        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, P.local_agents, self.mainwin)
        subject = task.get("subject") if isinstance(task.get("subject"), dict) else {"name": task.get("subject")}
        (_, members), = P.resolve([subject], agents)
        if not members:
            await self._reply(env, "response", status="failed",
                              error={"code": "NOT_FOUND", "message": f"{subject} is not on this machine"})
            return "not_found"
        try:
            out = await loop.run_in_executor(None, lambda: diagnose(task, members, P.roots_for(members)))
        except (PermissionError, ValueError, FileNotFoundError) as e:
            await self._reply(env, "response", status="failed", error={"code": "REFUSED", "message": str(e)[:500]})
            return "refused"
        except Exception as e:
            await self._reply(env, "response", status="failed",
                              error={"code": "DIAGNOSE_ERROR", "message": str(e)[:500]})
            return "failed"
        await self._reply(env, "response", status="done", result=out)
        return "done"

    def nudge_status(self) -> None:
        """A run started, stopped or failed (any thread): report status soon, not at the next tick."""
        if self._loop is not None and self._nudge is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._nudge.set)

    async def _anomaly_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._nudge.wait(), timeout=ANOMALY_EVERY_S)
                await asyncio.sleep(NUDGE_SETTLE_S)
            except asyncio.TimeoutError:
                pass
            self._nudge.clear()
            try:
                await self.anomaly_tick()
            except Exception as e:
                logger.debug(f"[a2a-gateway] anomaly check: {e}")

    async def anomaly_tick(self) -> int:
        """Run the status providers; send one event per needs-human anomaly the first time it
        appears (one that clears and comes back is new again), and each team's status_report when
        it changed or is due. Returns the anomaly events sent."""
        from agent.status import providers as P
        loop = asyncio.get_running_loop()
        agents = await loop.run_in_executor(None, P.local_agents, self.mainwin)
        jobs = [(s, m) for s, m in P.resolve(None, agents) if any(a["provider"] for a in m)]
        machine = self._machine()
        st = self._load_state()
        seen: Dict[str, str] = dict(st.get("anomalies") or {})
        now_seen: Dict[str, str] = {}
        reported: Dict[str, Dict[str, Any]] = dict(st.get("reported") or {})
        sent = 0
        for subject, members in jobs:
            rep = await loop.run_in_executor(None, lambda: P.report_for(subject, members, machine=machine))
            await self._status_report(rep, members, reported, st.get("manager") or MANAGER_ADDRESS)
            for a in rep.get("anomalies") or []:
                if not a.get("needs_human"):
                    continue
                key = P.anomaly_key(rep, a)
                first = now_seen[key] = seen.get(key) or rep["as_of"]
                if key in seen:
                    continue
                await self.send(st.get("manager") or MANAGER_ADDRESS,
                                make("event", correlation_id=f"anomaly:{key}", reply_to=self.address,
                                     msg_id=f"anomaly:{self.address}:{key}:{first}", event="status_anomaly",
                                     subject=rep["subject"], anomaly=a, health=rep.get("health"),
                                     headline=rep.get("headline"), machine=machine))
                sent += 1
        self._save_state(anomalies=now_seen, reported=reported)
        return sent

    async def _status_report(self, rep: Dict[str, Any], members: List[dict], reported: Dict[str, Dict[str, Any]],
                             to: str) -> bool:
        """Send ``rep`` as a status_report event when its health or running state changed since the
        last one, or STATUS_REPORT_EVERY_S has passed. The cloud keeps the latest per subject."""
        subj = rep.get("subject") or {}
        key = f"{subj.get('kind')}:{subj.get('id')}"
        sig = f"{rep.get('health')}|" + ",".join(sorted(f"{m['id']}={int(bool(m.get('running')))}" for m in members))
        last = reported.get(key) or {}
        if last.get("sig") == sig and time.time() - float(last.get("at") or 0) < STATUS_REPORT_EVERY_S:
            return False
        mid = await self.send(to, make("event", correlation_id=f"status:{key}", reply_to=self.address,
                                       msg_id=f"status:{self.address}:{key}:{rep.get('as_of')}",
                                       event="status_report", report=rep, machine=self.address))
        if mid:
            reported[key] = {"sig": sig, "at": time.time()}
        return bool(mid)

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
        rec = {"id": self.address, "machineId": self.machine_id, "org": self.org, "name": socket.gethostname(),
               "role": "machine", "skills": ",".join(allowlist()["skills"]), "skillsHash": "",
               "a2aRelayChannel": self.address, "lanHint": None, "ecanVer": "", "os": "", "ttl": ENDPOINT_TTL_S}
        if not self._caps_off:
            try:            # the machine's agents and teams, for the Manager to find them (AWSJSON)
                from agent.status.providers import capabilities
                caps = json.dumps(capabilities(self.mainwin), ensure_ascii=False, default=str)
            except Exception as e:
                logger.debug(f"[a2a-gateway] capabilities: {e}")
                caps = None
            if caps is not None:
                try:
                    await self._post(GQL_UPSERT, {"input": {**rec, "capabilities": caps}})
                    return
                except Exception as e:
                    if "capabilities" not in str(e).lower():
                        logger.warning(f"[a2a-gateway] GraphQL call failed: {e}")
                        return
                    self._caps_off = True     # an older server: announce without the agent list
                    logger.info(f"[a2a-gateway] the server takes no capabilities yet ({e}); heartbeat without them")
        await self._gql(GQL_UPSERT, {"input": rec})

    # ---- state -------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, since: Any = None, **other: Any) -> None:
        """``since`` only moves forward; the ``other`` keys (manager, anomalies) are replaced."""
        try:
            with self._lock:
                st = self._load_state()
                new = dict(st)
                if since and str(since) > str(st.get("since") or ""):
                    new["since"] = since
                new.update({k: v for k, v in other.items() if v is not None})
                if new != st:
                    self._state_file.parent.mkdir(parents=True, exist_ok=True)
                    self._state_file.write_text(json.dumps(new), encoding="utf-8")
        except OSError as e:
            logger.debug(f"[a2a-gateway] could not save state: {e}")


def _tool_args(task: Dict[str, Any]) -> Dict[str, Any]:
    """A tool call's arguments, with or without the MCP ``{"input": {...}}`` wrapper."""
    args = task.get("input") if isinstance(task.get("input"), dict) else {}
    return args["input"] if isinstance(args.get("input"), dict) else args


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
    from agent.ec_tasks.appsync_pubsub import AuthBackoff, _subscribe, post_graphql_current_token
    backoff = AuthBackoff()

    async def post(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        # the signed-in user's token as it is now, so the server takes the org from a verified identity
        return await post_graphql_current_token(config, query, variables, backoff=backoff, who="a2a-gateway")

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


def nudge_status() -> None:
    """Hook for the task runner (a run started or ended): never raises."""
    try:
        if _gateway is not None:
            _gateway.nudge_status()
    except Exception as e:
        logger.debug(f"[a2a-gateway] nudge_status hook: {e}")


def new_request(intent: str, task: Dict[str, Any], reply_to: str, thread_id: Optional[str] = None,
                deadline: Optional[str] = None) -> Dict[str, Any]:
    """A request envelope (used by tests and by local agents asking a cloud agent)."""
    cid = uuid.uuid4().hex
    return make("request", correlation_id=cid, reply_to=reply_to, msg_id=cid, intent=intent, task=task,
                thread_id=thread_id, deadline=deadline)
