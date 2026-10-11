# Shared Q&A pool across stores

Several stores of one platform (抖店, 拼多多) can share one set of Q&A agents.
Each store keeps its own front desk (its own login, its own browser); the Q&A
agents answer for all of them, and every answer uses the store that asked.

Status (2026-10-11): built and unit-tested, **not yet live-tested with two
stores** (docs/OPEN_ITEMS.md).

## Using it (快速生成)

1. 快速生成 → pick the platform → pick the store → add 客服.
2. If another store of this platform already has Q&A agents, the option
   **与本平台其他店铺共享问答客服** appears and is **on by default**.
   - Several existing pools: choose which store(s)' Q&A agents to share.
   - **新增问答客服**: how many Q&A agents to add to the shared pool (default 0).
   - With sharing on, the usual "# of Q&A agents" field is hidden; turn sharing
     off to give the store its own Q&A agents instead.
3. Generate, then **restart eCan**: the running Q&A agents only pick up the new
   front desk at startup.

Not offered for 千牛 (one store per machine), or when the only existing pool is
this store's own.

## What the deploy changes

`_deploy_live_chat` with `share_with` (a front desk agent id of the pool to
join) and `qa_agents_extra` (cli/deploy/commands.py):

- **New store:** its own front desk task + agent (store id, store URLs, its own
  login profile), as in a normal deploy.
- **Existing Q&A tasks** (`_share_pool`): `task_vars.front_desk_agent_id`
  becomes the list of all the front desks; their own `store_id` / `store_url` /
  `store_urls` are removed -- each turn names its store (below).
- **Extra Q&A agents:** new tasks `<qa prefix>共享NNN` serving all the front desks.
- **Pool size:** every front desk's `pool` setting covers all the members.
- Changed tasks are synced to the cloud as updates.

`cs_pools(ctx, scenario)` lists a platform's deployments grouped by the Q&A
agents they share; the panel reads it through IPC `fast_deploy.cs_pools`.

The CLI-only scenarios `douyin_cs_multi` / `pdd_cs_multi` deploy several stores
with one shared pool in a single step (`_deploy_live_chat_multi`); the result
has the same shape.

## How a turn knows its store

A shared Q&A task has no store of its own. The front desk puts its `store_id`
in every dispatch (top-level key of the JSON built by
`frontdesk_dispatch._build_assignment_payload`; the buyer's text is a string
inside it and can't set it). On the Q&A side:

| What | Where | Store used |
|---|---|---|
| Knowledge search (policies, products) | `knowledge/ks/agent_bridge.scope_from_state` → `resolve_store_id(state)` | the task's own store, else the turn's dispatch `store_id` (`_dispatched_store_id`) |
| `{{store_id}}` prompt variable | `prompt_variable_providers.resolve_store_id` | same |
| Token usage, metering, log scope | `runner._scope_turn_store`, per turn, in the turn's own context copy | same |
| The LLM's `store_id` tool argument | `agent_bridge.try_product_answer` | ignored inside a run (a buyer could steer it) |

A task's own store always wins, so single-store deployments behave as before.

## Pool sizing for a shared pool

The pool controller (agent/ec_agents/agent_pool.py) sizes front desks whose Q&A
members overlap as **one group**:

- members = all of their members; min / max = the largest of theirs (max capped
  at the member count); idle minutes = the shortest;
- traffic forecast = the group's (all front desks count the same members' turns);
- every front desk in the group gets the same active set;
- a pin (`ecan agents pool <front desk> --pin N`) on any front desk sizes the group;
- `pool_view` (the pool panel's data) lists the other front desks in `shared_with`.

## Open

- Live test with two 抖店 stores sharing one pool: each store's answers use its
  own policies and products; `[agent-pool]` log lines show one group.
- The pool panel doesn't show which stores share the pool yet (data only).
