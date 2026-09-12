# Fleet turn queue — the client half

Path 1.5 Phases 0–6 built a pod that can serve. This is the wiring that gives it
work: claim turns from the control plane, heartbeat them, report what they cost.

Server side: `eCan_lambda/cn/tencent/ecbAccountManager` internal actions
(`vehicle_register`, `turn_claim`, `turn_heartbeat`, `turn_done`).
Client side: `agent/cloud_worker/fleet_client.py` + the `fleet` intake in
`agent/cloud_worker/cn_serve.py`.

## Running a pod against the queue

```bash
ECAN_APP_ID=cn \
ECAN_VEHICLE_ID=pod-a1                      # scheduler-assigned; a pod is cattle
ECAN_FLEET_INTERNAL_TOKEN=<PAYMENT_CREDIT_SHARED_TOKEN> \
ECAN_VEHICLE_CAPABILITIES=cn_llm,browser_local \
ECAN_VEHICLE_CAPACITY=1 \
ECAN_CHECKPOINTER=postgres ECAN_CHECKPOINTER_DSN=postgres://... \
ECAN_TCB_REFRESH_TOKEN=<owner token> \
ECAN_TASK_ID=<task>                          # see "the task gap" below
python -m agent.cloud_worker.cn_worker_main --mode serve --intake fleet
```

| Variable | Meaning |
|---|---|
| `ECAN_FLEET_ENDPOINT` | `ecbAccountManager` URL. Defaults to the GraphQL host + `/ecbAccountManager`. |
| `ECAN_FLEET_INTERNAL_TOKEN` | The internal shared credential. These actions are worker↔control-plane, not user-facing; a 401 here is a wrong credential, never an expiry. |
| `ECAN_VEHICLE_ID` | This pod's fleet identity. Without it the pod has no address and refuses to start. |
| `ECAN_VEHICLE_CAPABILITIES` | Comma/semicolon list. Placement is a WHERE clause: a turn's `requires[]` must be a subset of this. |
| `ECAN_VEHICLE_CAPACITY` | `max_concurrent_tasks` on the roster; feeds the autoscale signal. **The loop still runs one turn at a time** — see "concurrency" below. |
| `ECAN_SERVE_INTAKE` | `stdin` (default) or `fleet`; `--intake` overrides. |

`--intake stdin` is unchanged: NDJSON work items, no fleet, no reporting.

## What one turn does

```
turn_claim  ->  map to a worker message  ->  run_single_cn  ->  turn_done
                     (heartbeat every 30s while it runs)
```

* **Idempotency belongs to the server.** The client never mints or regenerates a
  turn id; `run_id` is set *to* the turn id, so a redelivered turn overwrites its
  own run state rather than opening a second one. At-least-once delivery plus an
  LLM call with a side effect means a second answer to one customer is the
  failure mode to design against.
* **Heartbeat during the run, not after.** A turn slower than
  `TURN_STALE_SECONDS` (120s server-side) is reaped and requeued, and a second
  pod starts answering the same customer.
* **Mapping failures are permanent** (`retry: false`). A turn that names no task
  maps to the same nothing on every attempt; reporting it as retryable burns all
  three and reads as a flaky worker instead of a missing field.
* **Nothing here may kill the pod.** Claim errors back off and retry; a failed
  `turn_done` is logged loudly (the server will reap and requeue) but not raised.

## The task gap — an open contract item

A turn names an **owner, conversation, agent and input text**. `run_single_cn`
loads work by **task id**. Nothing on the turn row carries one, and
`TaskQueryInput` has no `agent_id`, so the agent→task lookup is not available
over GraphQL either.

`turn_to_worker_message` resolves the task in this order:

1. `turn.input` parsed as a JSON object carrying `task_id` — the structured form
   an enqueuer can use to name the work exactly;
2. `ECAN_TASK_ID` — the pod is pinned to one task (single-tenant serving).

Neither → `TurnMappingError`, reported permanent. **The durable fix is a server
decision**: either `turns` carries `task_id` (mirroring `agent_id`), or
`TaskQueryInput` gains `agentId` so the worker can resolve agent→task itself.
Until one of those lands, a multi-tenant pod cannot serve turns from more than
one task.

## Cost reporting

`turn_done` carries `cost_usd` / `input_tokens` / `output_tokens`.
`TokenTracker` already computes those per call — and then dropped them in a pod,
because it returns early when `token_usage_service` is missing (no `ec_db_mgr`).
`agent/ec_skills/usage_window.py` keeps them: a cumulative counter updated where
the cost is computed, and a snapshot delta measured across each turn.

**Concurrency constraint:** the counter is global. `serve()` runs one item at a
time, so a delta is that turn's usage. If a pod ever runs turns concurrently,
`usage_window` must become contextvar-scoped *first* — otherwise one turn is
charged for another's tokens, and cost attribution that is quietly wrong is worse
than none. `ECAN_VEHICLE_CAPACITY` advertises capacity to the scheduler; it does
not make the loop concurrent.

## Phase 2.2 — where conversation threads now work, and where they don't

**Serving path: done, behind the flag.** A turn names its conversation, so the
thread key needs no payload sniffing. With `ECAN_CONVERSATION_THREADS=1`,
`turn_to_worker_message` sets `options.thread_id` to
`thread_id_for(agent_id, conversation_id)`, `run_single_cn` passes it as
`WorkerMessage.thread_id`, and `_run_skill_once` puts it in `task.metadata`
config — which `prepare_config` already honours. Off (the default), each turn is
its own thread exactly as before.

**Desktop/live path: still not flipped, and not because of nerve.** On that path
a turn usually arrives as `Command(resume=...)` against a *checkpoint on the
task's existing thread* (`ec_tasks/runner.py`, `_build_resume_payload` + `cp`).
Re-keying such a turn onto a conversation thread would resume from a different,
empty thread and lose the parked interrupt. Making the live path
conversation-threaded therefore means **each conversation parks its own
interrupt** — a change to the invocation model, not a config swap.
`resolve_thread_config` exists for that day and has no caller yet.

### A/B procedure (serving path)

Two flags, and they are independent:

| `ECAN_CONVERSATION_THREADS` | `ECAN_QA_HISTORY_ISOLATION` | What you are testing |
|---|---|---|
| unset | `1` (default) | today's production behaviour |
| `1` | `1` | threads live, clear still guarding — **run this first** |
| `1` | `0` | the actual question: do threads alone keep customers apart? |
| unset | `0` | never run this; it is the 2026-04-27 incident with no guard |

Run the third row only after the second has served a real multi-customer load,
and check for the incident's shape: an answer to customer A appearing in
customer B's conversation. `ECAN_QA_HISTORY_ISOLATION=0` logs a warning naming
that risk on every turn — it is meant to be noisy.

Phase 3.2 (deleting the per-turn clear) stays blocked until that run exists.
