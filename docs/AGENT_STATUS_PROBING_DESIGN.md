# Agent Status Probing — Design

Status: draft, 2026-11-11. Nothing here is built yet; the "Today" sections describe code that exists.

## 1. Goal

A user chats with the cloud manager/helper agent ("how is the Amazon crawl doing?", "is the
抖店 客服 agent healthy?", "why did ProductCrawler3 stop?") and gets the kind of answer a person
would give after looking: where the work stands, how fast it moves, what is wrong, what needs a
human, and a percentage toward the goal.

To do that, the manager must:

1. **Identify** the agents the question is about and **locate** them (which machine, online or not).
2. **Ask** those machines to collect the agents' status, let the host do the work locally, and
   **collect** the results.
3. **Compose** an answer, including what changed since the user last asked.

This must work for **any** agent, not only crawlers. "Status" is not a state enum: it is a
description with numbers, recent events, anomalies and suggested actions, and what matters
differs by agent.

## 2. Worked example: the product research crawl (done by hand today)

The design generalizes what was done manually, many times, for the Amazon crawler
(`agent/ec_skills/product_research/`, agents ProductResearchCoordinator + ProductCrawler1-4 on one
Windows host). One "check now" read:

| Source | What it gave |
|---|---|
| `C:/product_research/_queue/BLOCKED` | blocked by Amazon (captcha / sign-in) or not, and why |
| `_queue/status.md` (one row per phrase) | phrases done / crawling / pending; which phrase is current; finish times |
| `<phrase>/status.md` (one row per product) | products done since the last check, by which crawler, failures + reasons |
| `store.queue_rows` + `phrases.txt` seeds | overall % (done / all queued) and seed % (done / 447) |
| `runlogs/eCan.log` `[SESSION] build=` | which build the app runs (did the restart pick up the fix?) |
| Chrome processes per profile | which crawlers are actually alive |
| `df` on C:, NAS listing | disk headroom, upload result |
| One live page probe (spare profile) | root cause when the data looked wrong |

Derived, not read: rate (products/h since last check), ETA, "since last check" lists, the moving
total (finished seeds keep adding subcategories, so % can stall while work progresses), and
anomalies.

The most expensive lesson: **"no captcha for 9 days" looked healthy while Amazon had limited the
account's review access for 8 of them** — every product saved identical negative and positive
reviews. Liveness and "not blocked" were green; the *data* was wrong. It was found only when
someone on another machine read the output. A status design that only reports running/blocked
would have missed it too. Agents must report **data-quality invariants**, not just activity.

Typical answer produced:

> The crawl is healthy (09:13). Full planned crawl **29.6%** (484 of 1,636 phrases), seeds **99.8%**.
> 491 products since 20:14 (~38/h), 0 failures; 25 phrases finished and uploaded. Review access
> still limited (486 products marked) — 2.7 days since the verify request. ETA ~25 days.
> Nothing blocked; C: 81 GB free.

## 3. Today: what exists to build on

| Need | Existing piece | Gap |
|---|---|---|
| Machine → cloud push | Fleet feed `agent/fleet/activity_feed.py` (`FleetFeed`, WAN chat `fleet.feed`, `sendWanMessage` via `agent/chats/wan_chat.py`); snapshot every 60 s with agents (`running`, `status`, `readiness`) + last 50 tasks; batches ≤24 KB / 60 events | snapshot is generic; no domain status |
| Cloud → machine command | `fleet.cmd` (`FleetFeed.handle_command`: `log_start`, `log_stop`, `ping`, `snapshot`), addressed by `machine` id or `"*"` | no request id, no reply correlation, no agent-scoped commands |
| Where is agent X | DB `agents.vehicle_id`, `agent_vehicles`; `agent/ec_agents/vehicle_affinity.py`; A2A directory `AgentDirectory.lookup`, `query.find_agents(skill=, role=, machine_id=, name_contains=)`, cloud `AgentEndpoint` table with 60 s heartbeat | no "team"/group notion (coordinator + crawlers = one job) |
| Liveness | `agent/ec_tasks/progress.py` `note_task_progress` (timestamp only); runner cancels a task silent > 300 s | no content |
| Task progress | `agent/ec_tasks/task_progress_bus.py` `TaskProgressBus` (events, snapshots by run_id/correlation_id); MCP `get_task_progress` | per run, not per job; not on the feed |
| Free-form agent status | `utils/agent_status.py` `report(agent_id, **fields)`, `snapshot_all()` — already shown as `readiness` in the feed and on the Agents page | flat key/value, no schema, no history |
| Cloud chat agent | `lambda_functions/chatter/` (LangGraph; tools `list_agents`, `list_tasks`, `stop_task`, …) | no tool reads fleet/machine status |
| Status MCP tool | `ecan_ai_api_get_agent_status` (`agent/mcp/server/api/ecan_ai/ecan_ai_api.py`) | stub returning empty lists |
| Consumers today | web Staff Officer (`gui_v2/src/services/web/fleetFeed.ts`), desktop drawer via IPC `fleet_feed.watch` | humans only |

The design adds a **status provider** contract on the host, a **probe request/reply** on the
existing fleet channels, and **one manager tool** on the cloud side.

## 4. Status model

Four levels, cheapest first. The manager answers from the cheapest level that covers the question.

| Level | What | Source | Cost |
|---|---|---|---|
| L0 Presence | machine online, app build, agent process up, last heartbeat | fleet feed snapshot (already pushed) | free, cached in cloud |
| L1 Task | task state, last progress age, recent task start/fail | fleet feed `task` events, `TaskProgressBus` | free, cached |
| L2 Domain report | agent-defined progress, rate, current work, recent results, anomalies, needs-human | **status provider** run on the host | one probe, seconds |
| L3 Diagnostics | log tail, file excerpts, a live page check | on-demand, explicitly requested; may be slow or touch external sites | expensive, rare |

### 4.1 The status report (L2) schema

One schema for every agent; the agent fills what applies and puts the rest in `metrics`/`detail`.

```jsonc
{
  "v": 1,
  "subject": {"kind": "agent" | "team", "id": "...", "name": "ProductResearch", "members": ["ProductCrawler1", "..."]},
  "machine": {"id": "...", "name": "...", "build": "0.7.0-dev-daa2de280"},
  "as_of": "2026-11-11T09:13:20-08:00",
  "since": "2026-11-10T20:14:55-08:00",          // echo of the request's cursor, null = full report
  "health": "ok" | "degraded" | "blocked" | "stalled" | "down",
  "headline": "Crawl healthy; review access still limited",   // one line, for lists
  "progress": {
    "unit": "phrases", "done": 484, "in_progress": 1, "total": 1636, "percent": 29.6,
    "total_is_moving": true,                     // total still grows (seeds add subcategories)
    "secondary": [{"label": "seeds", "done": 446, "total": 447, "percent": 99.8}]
  },
  "rate": {"value": 38, "unit": "products/h", "window": "since"},
  "eta": {"at": "2026-12-06", "basis": "1152 phrases left at 38 products/h"},
  "current": [{"what": "portable neck fan", "who": "crawler1..4", "detail": "10/20 products"}],
  "recent": [                                    // what happened in the window, newest first, capped
    {"ts": "...", "kind": "finished", "what": "luggage scale", "detail": "20/20, on NAS"}
  ],
  "anomalies": [{
    "id": "amazon-review-limit",                 // stable id: lets the manager say "still" / "new" / "cleared"
    "severity": "warn",                          // info | warn | error
    "since": "2026-10-31T07:00",
    "what": "Amazon limits review access on the shopper account",
    "evidence": "486 of 491 products saved with reviews_limited",
    "impact": "reviews need a re-fetch pass later",
    "needs_human": true,
    "suggested_action": "wait for Amazon's verify email; then run the reviews-only pass"
  }],
  "resources": {"disk_free_gb": 81, "ram_free_gb": 3.1},
  "metrics": {"products_since": 491, "failed_since": 0, "reviews_limited_since": 486},
  "links": [{"label": "plan", "path": "C:/product_research/plan.md"}],
  "detail": "free markdown for anything the schema does not cover (≤ 4 KB)"
}
```

Rules:

- `health` is the agent's own judgment; the manager may downgrade it from L0/L1 (agent says ok
  but its process is gone → `down`; no progress for 2× its expected interval → `stalled`).
- `progress.percent` is required whenever the agent has a goal. If the total is not known yet,
  say so (`total: null`) instead of inventing one; `total_is_moving` explains a stalled %.
- **Anomalies carry data-quality checks**, not only failures (see §2). Each provider should
  assert its output's invariants (e.g. negative ≠ positive reviews, files present, counts sane).
- `needs_human` marks anything only a person can do (sign in, solve a captcha, approve a
  deletion, reply to a platform). The manager surfaces these first.
- Size cap 16 KB per report (fits a fleet batch); `recent` is truncated with a count.
- No secrets, no credentials, no customer PII; paths are fine, file contents are not (that is L3).

### 4.2 Teams

Users ask about a *job*, not a process: "the Amazon crawl" is a coordinator plus four crawlers
whose percentage only exists for the group. A **team** is a named set of agents with one provider
that reports for all of them (members' L0/L1 come for free from the feed).

- Declared in the skill (see §5): `team: "product_research"`; every agent running a skill of that
  team is a member.
- The team report is produced by **one** member (the coordinator, or any member on the same
  machine; members on other machines report their own L2 and the manager merges).

## 5. Host side: status providers

A skill (or plain agent) may provide a status function:

```python
def status(ctx: StatusContext) -> dict:   # returns the §4.1 report (partial is fine)
    ...
```

- `StatusContext`: `subject` (agent or team ids), `since` (cursor or None), `depth` (`summary` |
  `full`), `budget_s` (default 10), the agent's skill inputs (e.g. `research_root`), and helpers
  for L0/L1 facts the host already knows (agent running, last progress, build).
- **Read-only and bounded**: no browser, no network to third-party sites, no writes except its own
  cache; must return within `budget_s` (runs in a worker thread; on timeout the host returns L0/L1
  with `health: "unknown"` and an anomaly "status provider timed out").
- Registration: skill metadata `status_provider: "<module>:<function>"` (code skills) or a
  `code_dir/status.py` with `status(ctx)` (diagram skills), plus optional `team: "<name>"`.
  Agents without a provider still answer with L0/L1 + whatever they wrote to
  `utils/agent_status.report` (the existing ledger becomes the zero-effort L2).
- The host keeps the last report per subject; `since` lets providers compute "since last check"
  without the manager re-reading everything.

Product research provider (sketch, all from existing `store` functions):

```python
def status(ctx):
    root = Path(ctx.inputs["research_root"])
    rows = store.queue_rows(root); seeds = {store.slug(p) for p in store._seeds(root) if p}
    products = done_products_since(root, ctx.since)          # from <phrase>/status.md rows
    anomalies = []
    if (b := store.blocked(root)): anomalies.append(blocked_anomaly(b))      # needs_human
    if limited := [p for p in products if "reviews limited" in p.note]:
        anomalies.append(review_limit_anomaly(len(limited), len(products)))
    if dup := neg_equals_pos(products): anomalies.append(duplicate_reviews_anomaly(dup))  # data quality
    ...
    return {"progress": {...percent...}, "rate": ..., "eta": ..., "anomalies": anomalies, ...}
```

## 6. The probe protocol

Reuse the fleet channels; add correlation.

**Request** — cloud → `fleet.cmd`, `type: "fleet_cmd"`:

```jsonc
{"cmd": "status_probe", "request_id": "sp_9f2c…", "machine": "<machine id>",
 "subjects": [{"kind": "team", "id": "product_research"}],   // or agent ids
 "depth": "summary" | "full", "since": "<as_of of the user's last report>", "deadline_ms": 15000}
```

**Reply** — host → `fleet.feed`, event `{"kind": "status_report", "request_id": "sp_9f2c…", "report": {…}}`,
one event per subject, sent immediately (bypassing the 3 s flush wait), plus a final
`{"kind": "status_done", "request_id": …, "count": n}`.

- Unknown subject on that machine → `status_report` with `health: "down"` and an anomaly
  "agent not on this machine" (directory is stale).
- **L3** is a separate command, `status_diagnose` (`what: "log_tail" | "file" | …`), never
  triggered implicitly; anything that touches an external site (like the live review-page check)
  is L3 and is listed as such so the manager asks before running it.
- **Commands that change things** (delete BLOCKED, restart an agent, change a pace setting) are
  **not** part of probing. They go through the existing task/agent tools with explicit user
  approval. A probe must never fix what it finds.
- Contract: `fleet.cmd`/`fleet.feed` contents are opaque strings through `sendWanMessage`, so no
  GraphQL schema change is needed; if one ever is, it must land on both AWS AppSync and the TCB
  backend (CLAUDE.md §5).

## 7. Cloud side: manager tool

One tool for the chatter/helper agent (`lambda_functions/chatter/tools/`), backed by a small
service that subscribes to `fleet.feed`:

```
get_agent_status(query: str | ids, depth="summary", since="last" | iso | null, diagnose=None)
  -> {"subjects": [report…], "missing": [{"id", "reason", "last_seen"}], "as_of"}
```

Steps:

1. **Resolve** the query to subjects: exact agent names, team names, skill/role (`find_agents`),
   and fuzzy phrases ("the Amazon crawl" → team `product_research` via team/skill descriptions).
   Ambiguous → the agent asks the user which one.
2. **Locate**: `agents.vehicle_id` / `AgentEndpoint.machine_id`; group subjects by machine.
3. **Answer cheap first**: L0/L1 from the cached feed snapshot. If the question needs L2 (progress,
   anomalies, "how is it doing"), send one `status_probe` per machine in parallel.
4. **Collect** replies until `status_done` or the deadline; offline machine → last cached report
   with its age ("last seen 3 h ago; at that time …").
5. **Diff** against the user's previous report for that subject (stored per user + subject):
   new / still / cleared anomalies, progress delta, rate. This is what makes "check now" useful.
6. Return structured reports; the LLM writes the answer. Answer style the user expects (from the
   manual practice): headline with health and **percentage**, since-last-check numbers, current
   work, anomalies needing a human first, resources, ETA.

The existing stub `ecan_ai_api_get_agent_status` should be replaced by (or delegate to) the same
service so local and cloud chat give the same answer.

## 8. Security and limits

- Only the owner's machines answer; the host checks the request comes from its own user's channel.
- Providers are read-only; L3 output is size-capped and filtered for secrets (`.env`, credential
  files such as the NAS password file, tokens) before it leaves the machine.
- Rate limit probes per machine (e.g. 1 per 10 s per subject; repeated asks reuse a fresh report).
- Probing must not disturb the work: no extra load on rate-limited sites (an extra Amazon page
  load from a probe counts against the same account), no locks held on files the agents write
  (the crawler hit Errno 13 when a reader overlapped a replace).

## 9. Rollout

| Step | Work | Done when |
|---|---|---|
| 1 | Report schema + `status_probe`/`status_report` in `FleetFeed`; L0/L1-only reply for every agent | the web Staff Officer can request and show a report |
| 2 | Provider registration (`status_provider` / `code_dir/status.py`, `team`); fallback to `agent_status` ledger | an agent without a provider still returns a sensible L2 |
| 3 | Product research provider (first real one), incl. data-quality checks | its report matches a manual "check now" |
| 4 | Cloud service + `get_agent_status` tool in chatter; per-user "last report" cursor | "how is the Amazon crawl doing?" answered in chat with % and deltas |
| 5 | `status_diagnose` (L3) with approval prompt | "why did crawler3 stop?" can pull a log tail |
| 6 | Providers for the next agents (chip_docs crawlers, 客服 agents, eBay messages) | |
| later | Proactive: manager watches reports and messages the user when a `needs_human` anomaly appears | |

## 10. Open questions

- Team identity: declared in skill metadata, or a cloud-side grouping the user edits?
- Where the per-user "last report" cursor lives (cloud DB vs. the chat history).
- Should a provider's anomalies be pushed on change (cheap, timely) instead of only on probe?
- Multi-machine teams (crawlers on a second machine via NAS claims): merge rules for progress.

## 11. Wire contract v1 (client side built 2026-11-11)

The desktop side runs on the A2A gateway (`agent/a2a/gateway.py`), not the fleet channels of §6:
requests arrive as envelope `request`s through `onA2AMessageForMachine` / `getA2AMessages`, and
every reply is a normal envelope with a stable `msg_id` (`<correlation_id>:ack`,
`<correlation_id>:progress:<n>`, `<correlation_id>:response`).

**Heartbeat** — `upsertAgentEndpoint` input gains `capabilities` (AWSJSON string, ≤ 8 KB):

```jsonc
{"v": 1,
 "status": {"v": 1, "intents": ["get_agent_status", "status_diagnose"]},
 "agents": [{"id": "...", "name": "ProductCrawler1", "running": true,
             "skills": ["product_crawler_00"],          // dropped first when over 8 KB
             "team": "product_research", "has_provider": true}],
 "teams": [{"id": "product_research", "name": "Amazon product research crawl",
            "description": "...", "members": ["<agent id>", "..."]}],
 "agents_truncated": 0}                                  // only when agents were cut
```

A server that rejects the field (error text mentions `capabilities`) gets the old record from
then on (until the app restarts); presence never depends on it.

**get_agent_status** — request `intent: "get_agent_status"`,
`task: {"subjects": [{"kind": "team", "id": "product_research"} | {"kind": "agent", "id" | "name": "..."}],
"depth": "summary" | "full", "since": "<ISO of the user's last report>" | null, "budget_s": 10}`.
No/empty `subjects` = every team plus every agent outside a team on that machine.

- `ack` accepted, then one `progress` per subject as soon as its report is ready:
  `progress: {"step": "status_report", "subject": {...}, "done": n, "of": m}`, `result: {"report": <§4.1>}`.
- one `response`: `status: "done"`, `result: {"reports": [...], "count", "complete", "machine", "as_of"}`.
  `complete: false` when the full reports exceed 48 KB: `reports` then carries
  `{subject, health, headline, progress, as_of}` only (the progress messages had the full ones).
- A subject not on the machine: a report with `health: "down"`, `headline: "not on this machine"`,
  anomaly `not-on-this-machine`.
- A provider over its budget or raising: `health: "unknown"`, anomaly `status-provider-timeout` /
  `status-provider-error`, with `presence` still filled.
- Every report carries `presence: [{id, name, running, status, tasks: [{id, name, skill, status,
  progress_age_s}]}]` — the facts the server uses to downgrade to `down` / `stalled`
  (`progress_age_s: null` = no progress for over 10 min, or never).

**status_diagnose** — `intent: "status_diagnose"`, `task: {"subject": {...}, "what": "log_tail" | "file",
"lines": 200, "path": "<for file>"}`. Response `result: {"what", "text", "scrubbed": <n masked>, "truncated"}`
(≤ 400 lines, ≤ 32 KB), or `status: "failed"` with `error.code` `NOT_FOUND` | `REFUSED` | `DIAGNOSE_ERROR`.
Files only under the subject's provider `roots`; credential-looking files are always refused;
tokens, keys, passwords, cookies and e-mail addresses are masked on the machine.

**Anomaly event** — every 5 min the gateway runs the providers; the first time a
`needs_human` anomaly id appears for a subject it sends
`{"kind": "event", "event": "status_anomaly", "correlation_id": "anomaly:<key>",
"msg_id": "anomaly:<machine address>:<key>:<first seen>", "subject", "anomaly", "health", "headline", "machine"}`,
`<key>` = `<kind>:<subject id>:<anomaly id>`. It goes to the address that last sent this machine a
`get_agent_status` (`reply_to`), else `"manager"`. Seen ids persist across restarts; an anomaly
that clears and returns is announced again.

**Providers** — `agent.status.providers.register(name, fn, skills=(prefixes), team=, team_name=,
description=, roots=)`; built-in providers are listed in `BUILTIN` and imported on first use.
First provider: `agent/ec_skills/product_research/status.py` (team `product_research`).
