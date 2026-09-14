# Cloud skill serving — getting a web customer-chat turn answered

**2026-09-13/14.** From "a pod exists" to a visitor typing 你好 and getting
您好，在的，请问有什么可以帮您？ back. Twenty-five commits, and almost none of
them were the thing we thought we were fixing when we started.

Read this before touching serving mode, pods, or the worker image. Every
section below is a blocker that cost real time and would cost it again.

Related: `FLEET_TURN_QUEUE_CLIENT.md`, `UNIFIED_EXECUTION_CLIENT.md`,
`eCan_lambda/cn/tencent/FLEET_SERVING_POD.md`,
`eCan_lambda/cn/tencent/CHAT_EMPTY_REPLY_FOR_CLIENT.md`.

---

## 1. The chain, end to end

```
widget / turn_enqueue
  └─ turns table                       (ecbAccountManager, CloudBase)
      └─ pod claims it                 cn_serve.fleet_intake  → turn_claim
          └─ turn_to_worker_message    cn_serve
              └─ run_single_cn         cn_worker_main   fetch task+skill, materialise
                  └─ _run_skill_once   worker_main      build graph, run
                      └─ pend_event    interrupts IMMEDIATELY, always
                      └─ auto-resume   feeds the message back in
                          └─ llm ×2    classifier, then answer
                              └─ send_chat  → serving lane → reply window
                                  └─ turn_done result  → the widget
```

**Every single link in that chain was broken.** They failed one at a time, each
hidden behind the one before it, which is why this took a day.

---

## 2. The message never reached the model

### 2.1 `_safe_get` could not index a list  — `agent/ec_tasks/resume.py`

The one that cost the most. It walked dict keys and object attributes only, so
a numeric path segment against a list fell through to `return default`:

```python
_safe_get(msg, "params.message.parts.0.text")   ->  None    ALWAYS
```

That is the **primary** chat accessor in
`prep_skills_run._extract_chat_message_input_patch`, and `parts[0].text` is
exactly where `_run_skill_once` puts the prompt. So a worker message could never
populate `state["input"]`, and the LLM node renders `{{input}}` as empty.

**Why the desktop never showed it:** desktop chat messages match a *later*
candidate (`metadata.params.content.text`). The bug was only ever fatal on the
worker path — so "diff against the working desktop" points at the wrong layer.

Both numeric-path callers were dead; the other is `resume.py`'s `a2a_result`.

### 2.2 `WorkerMessage.prompt` carried an envelope, not a sentence

`cn_worker_main` passed `json.dumps(test_inputs)`, so once the text did arrive
the model was asked to answer `{"text": "…", "conversation_id": ""}`.

**The contract:** `WorkerMessage.prompt` → `in_msg.params.message.parts[0].text`
→ `state["input"]` → the user-turn template, which defaults to `{{input}}`
(`build_node.py:3235`). It must be the **bare sentence**. Nothing anywhere
unwraps JSON.

`_prompt_from_test_inputs` now sends `testInputs["text"]` bare and keeps the
envelope only when there is no `text` key, so launcher-run skills are unchanged.

Fixed: `c3635d0b4`. Tests: `tests/test_serving_chat_input_contract.py`.

---

## 3. The graph parked on its first node

`build_pend_event_node` calls `interrupt()` **unconditionally** on entry. There
is no branch that consumes an event already sitting in the state — so
**seeding an event into the run cannot work**, no matter how it is shaped.

A skill whose loop begins with `pend_event` therefore interrupts on its FIRST
node and the turn is reported done having asked the model nothing.

The desktop doesn't hit this because its executor auto-resumes —
`ec_tasks/runner.py`, whose comment states the problem exactly:

> the message is already in the state but pend_event always interrupts on first
> visit; auto-resume feeds the message as a resume payload so the graph advances
> to the LLM node

`_run_skill_once` calls `execute_task_hybrid` directly and skipped that.
`_auto_resume_pend_event` is the same move on the worker path: run, detect the
interrupt, resume **inside the same call** on the checkpoint just parked at.

**Design consequence, chosen deliberately:** one turn stays one complete
request/response. Nothing is carried between turns, so any pod can serve any
turn, and this needs neither `ECAN_CONVERSATION_THREADS` (off in production,
pending a live multi-customer run) nor a shared checkpoint — and it does not
inherit the resume-from-stale-checkpoint swallow.

`event_type` is `chat_message`: a skill waiting on `human_chat` accepts that
alias, and unlike `send_chat` it is not subject to the agent-self-echo guard.

Fixed: `7f83a4d23`. Tests: `tests/test_serving_pend_event_autoresume.py`.

---

## 4. The answer could not be delivered

### 4.1 `send_chat` had no lane for a web visitor

```
❌ Failed to send message: Either recipient_agent_id or recipient_agent_name is required
```

**`send_chat` is not an A2A-only tool.** It already routes between the A2A lane
and the off-DOM live-chat lanes Feige uses. The bug was that an **A2A
precondition ran before any lane was chosen** — so a reply with no recipient was
rejected even though two other lanes don't need one either.

The serving lane now goes in front of that check, and is deliberately narrow:
**no recipient at all, AND a turn open to collect the reply.** A Feige reply
names its recipient and never reaches it.

The reply waits in `agent/ec_skills/serving_reply.py`, a `ContextVar` window for
the same reason `usage_window` is one: a pod runs several turns at once and a
process-wide slot would let **one turn answer another turn's visitor**.

### 4.2 The turn reported the interrupt, not the answer

A chat skill answers and then loops back to `pend_event`, so the run's return
value is the **interrupt** — and `_json_safe_result` reported it verbatim. That
is the LangGraph `StateSnapshot` dump that appeared in the chat window.

`_turn_result` now prefers what `send_chat` actually delivered, falls back to
reading the answer out of the final state (for a reply sent from a raw thread,
which does not inherit the context), and only then reports the raw shape — a
turn that genuinely failed must still say why.

Fixed: `ebb2028c8`, `83219df15`. Tests:
`tests/test_send_chat_serving_lane.py`, `tests/test_serving_turn_reply_text.py`.

---

## 5. Pods — three wrong layers in a row

1. **Local only.** `save_pod` wrote the local DB and stopped. `DataType.VEHICLE`
   → `reportVehicles` had been wired since C1 with no production caller.
2. **Wrong table.** Writing a pod through GraphQL `addVehicles` puts it in
   `vehicles`, which is **OBSERVED** state. The row appears and **no pod is ever
   built from it.** Pods are DESIRED state in `fleet_pools`, written by
   `ecbAccountManager` actions `pod_list` / `pod_save` / `pod_delete`.
3. **`vehicle_type` does not identify a customer pod.** The fleet's own
   `vehicleRegister` hard-codes `'cloud'` for every pod that registers itself,
   and each Deployment rollout leaves the previous pod as an offline tombstone.
   Filtering on type alone listed runtime instances as "your pods" — with
   invented costs and Delete buttons — and counted them against the pod limit,
   so an owner with 5 running pods could not create a first one of their own.
   The discriminator is the desired-state blob, which only `save_pod` writes.

---

## 6. Two transports, one app

`gui_v2` runs on **both** desktop and web. `api-router.selectChannel` picks
LOCAL (localhost → Python GraphQL) or CLOUD (cloud domain → CloudBase) from
`detectPlatform()`.

**A method only exists on web if its call site carries a `graphql:` mapping —
and only 76 of 224 `apiRouter.execute` call sites do.** Nothing flags the
omission: no generator, no type error, no test. A new IPC method is silently
desktop-only, and the first signal is a user looking at an empty page.

### The desktop cannot fetch a cloud endpoint from the browser

Its UI runs on `http://localhost:3000` (dev) or `file://` (packaged), so
CloudBase refuses with CORS → "Failed to fetch". **A server-side allowlist
cannot fix the packaged case: `file://` sends `Origin: null`.** The desktop
proxies through the Python IPC handler `account_manager_call` (allowlisted
actions only — it holds the user's bearer). The web build is served from the
cloud origin and calls directly.

### ecbAccountManager takes the SAME bearer as GraphQL

`_session_bearer_token` read `tokens["AccessToken"]` first. For a WeChat login
that is the CloudBase **access** JWT (`sub=uid`, ~10 min, **unrefreshable by
design**) — not the eCan 30-day **session** token (`sub=openid`) the HTTP gate
verifies. Every `pod_*`, `fleet_status` and `turn_enqueue` call 401'd, and
would have forever, because that token cannot be refreshed.

> **Tell:** HTTP 401 from the account manager while GraphQL calls in the same
> log succeed seconds apart → wrong credential, not an expired session.

It now delegates to `_http_auth_header`, which already makes that choice for
every GraphQL call, so the two cannot drift.

---

## 7. Deploying the worker image

Everything runs on the CVM **49.235.169.108** (`~/.ssh/config` has the entry).
The Windows box has neither docker nor kubectl — **check SSH before concluding
you cannot deploy.**

### Three traps

1. **The default kubeconfig is dead.** `~/.kube/config` points at a host that no
   longer resolves; every kubectl call fails with `no such host` and looks like
   a broken cluster. Use `export KUBECONFIG=$HOME/.kube-ecan-runner.yaml`.
2. **The repo is `~/repo/eCan_lambda`**, not `~/eCan_lambda`. A `nohup bash
   <wrong path>` fails silently into the log and the build never starts.
3. **`docker push` can report success and not land the tag.** Observed
   2026-09-14: every layer `Pushed`, a digest returned, `PUBLISHED` printed —
   and the tag resolved from neither the cluster nor the machine that pushed it.
   A plain re-push fixed it.
   **Always verify before rolling:** `docker manifest inspect <repo>:<tag>`.

### Procedure

```bash
SRC=/home/ubuntu/build/ecan-worker-src
cd $SRC && git fetch origin && git merge --ff-only origin/master
#  NOT reset --hard — the tree carries the fleet_client.py overlay
#  GitHub is flaky from this box; `merge --ff-only` will say "Already up to
#  date" against a STALE ref after a failed fetch. Verify by grepping for a
#  symbol you just added, not by trusting the merge output.

bash /home/ubuntu/repo/eCan_lambda/cn/tencent/runner_image/build-serve-image.sh
docker manifest inspect ccr.ccs.tencentyun.com/ecan/ecan-cn-worker:<tag>   # ← the gate

# The pin and the deployments must move TOGETHER: reconcile-pools.sh:26
# hard-codes the tag and cron re-applies it every 2 minutes, so a hand roll
# without this edit is reverted.
sed -i 's|<old-tag>|<new-tag>|g' /home/ubuntu/repo/eCan_lambda/cn/tencent/runner_image/reconcile-pools.sh

export KUBECONFIG=$HOME/.kube-ecan-runner.yaml
kubectl -n ecan-workers set image deploy/ecan-fleet-worker worker=<image>
kubectl -n ecan-workers set image deploy/pod-<id>          worker=<image>
kubectl -n ecan-workers rollout status deploy/<name>
```

**Verify the CODE, not the tag:**
`kubectl -n ecan-workers exec <pod> -- grep -c <symbol> /app/<path>`.
An image can be published and the deployment still be serving the old one.

Container is `worker` on both. `ecan-fleet-worker` is the hand-made original;
`pod-<id>` deployments are reconciler-owned (`ecan.pool=pod_<id>`) and are built
from customer pods created in the desktop app.

### Sending a test turn

No `turn_get` read action exists — the account manager has only
enqueue/claim/heartbeat/done/route/send. Enqueue from INSIDE a pod so its own
`ECAN_TCB_ACCESS_TOKEN` is used and no token is printed, then read the outcome
from the pod log:

```bash
kubectl -n ecan-workers exec -i <pod> -- python3 - < enqueue.py
# POST <cloudbase>/ecbAccountManager {"action":"turn_enqueue","input":{owner,agent_id,input}}
```

---

## 8. Performance, measured

Four consecutive turns, 2026-09-14, same question:

| turn | setup (claim→first LLM) | total (claim→done) | cache |
|---|---|---|---|
| 1 | 14.3s | 21.6s | miss — cold pod |
| 2 | 9.8s | 15.9s | miss — the OTHER pod's cold start |
| 3 | **2.0s** | **7.1s** | HIT |
| 4 | **1.5s** | **6.3s** | HIT |

**Cold start ≈ 14s** and it is one-time per process: importing the agent stack
(8.5s — the Azure/GCloud SDK probes are import side effects), browser-use
registering 53 actions and the Feige hook bundle (3.4s), IPC registry (1.5s).
A serving pod imports the **whole desktop agent stack** to answer a text
message. Irrelevant while pods are long-lived; it becomes per-wake if you ever
run `on_demand` pods that scale to zero.

**Warm ≈ 6-7s**, of which **~5s is two LLM calls** — the skill runs a classifier
(`{"needs_rag": false, "category": "greeting"}`) before answering, 1568 input
tokens every turn. That is now ~75% of a warm turn and is a **prompt change**,
not a code one.

**The skill cache** (`38db94b79`) removed ~1s of per-turn setup: the task
record, its skill, and the materialised folder, cached per `(owner, task_id)`
with a 300s TTL (`ECAN_SKILL_CACHE_TTL=0` disables). The compiled graph is
deliberately **not** cached — sharing one across turns would share whatever its
nodes captured, and a wrong answer to the wrong visitor is worse than a slow one.

**Each pod has its own cache**, so N pods means N cold starts and N first-misses.
An argument for sticky routing by conversation (`vehicleHint` already exists).

---

## 9. Lessons that generalise

- **Zero tokens is the honest signal.** `0in/0out $0.0000` means the model was
  never asked. An empty reply with zero tokens and an empty reply after a real
  model call look identical in the UI and are completely different bugs. Read
  the token counter before reading anything else.
- **A green deploy is not a working deploy.** Three times a step reported
  success and had not done its job: `docker push` (tag missing), `git merge
  --ff-only` ("Already up to date" against a stale ref), and the build script
  that never ran because its path was wrong. Verify the artefact, not the exit
  code.
- **The desktop working is not evidence.** Two bugs here were invisible on the
  desktop because it takes a different branch (`_safe_get`, `send_chat` lanes).
  "Diff against the working path" sent us to the wrong layer twice.
- **Tests caught two bugs in their own commits** — a cache that was read and
  swept but never populated, and a function referencing a lazily-imported symbol
  as a global (`NameError` on the first real turn, in production). Both would
  have shipped looking implemented.
