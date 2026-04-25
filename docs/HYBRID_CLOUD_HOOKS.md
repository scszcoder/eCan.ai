# Hybrid-Cloud Hook System (v2)

A tier-aware extension of the lifecycle hook system that lets a single
hook implementation run unchanged across three deployment shapes:
**fully local**, **fully cloud**, and **hybrid cloud** (cloud
decision-making, local DOM execution).

> **Read first.**  This document assumes you already understand the
> two pre-existing hook systems:
>
> - [`BUILD_NODE_LIFECYCLE_HOOKS.md`](./BUILD_NODE_LIFECYCLE_HOOKS.md)
>   — three lifecycle phases that wrap a browser-automation node.
> - [`HOOK_BUNDLES.md`](./HOOK_BUNDLES.md) — the `HookDispatcher` that
>   fires **inside** the browser-use agent loop.
>
> The v2 system described here is a **typing layer** added on top of
> the lifecycle hooks; it does **not** replace either v1 system.
> Legacy v1 hooks continue to work unchanged.

- [Why v2 exists](#why-v2-exists)
- [The three execution tiers](#the-three-execution-tiers)
- [The four run modes](#the-four-run-modes)
- [Where the run mode comes from](#where-the-run-mode-comes-from)
- [Authoring a v2 hook](#authoring-a-v2-hook)
- [Runtime dispatch flow](#runtime-dispatch-flow)
- [Hybrid wire protocol](#hybrid-wire-protocol)
- [Bundle delivery (hybrid_cloud only)](#bundle-delivery-hybrid_cloud-only)
- [Migrating a v1 hook to v2](#migrating-a-v1-hook-to-v2)
- [Reference: file layout](#reference-file-layout)
- [Testing](#testing)
- [FAQ](#faq)

---

## Why v2 exists

The original lifecycle hook contract gives hooks a single,
all-encompassing context object (`BrowserUseHookContext`) that mixes
**cloud-decidable** state (DOM extraction outputs, agent registries,
inflight maps) with **local-only** capabilities (the live
`browser_session`, `mainwin`, the typing lock).

This works fine when everything runs in the same process. It breaks
the moment a cloud worker — running on hardware that has **no
browser** and **no `mainwin`** — needs to invoke the same hook.
Concretely, the symptom that motivated v2 was:

> `RuntimeError: mainwin not available` when a `runEnvironment=hybrid_cloud`
> skill tried to invoke `BrowserAutomation` on a cloud worker.

v2 fixes this by **classifying every hook by where it is allowed to
run**, and giving each tier a context object that contains only the
capabilities legitimately available at that tier. A hook that
declares itself `cloud_only` cannot accidentally reach for
`browser_session` because the field doesn't exist on its context.

## The three execution tiers

Every v2 hook declares an `EXECUTION_TIER` class attribute:

| Tier | Context | Has `browser_session`? | Has `mainwin`? | Typical role |
|---|---|---|---|---|
| `cloud_only` | `CloudHookContext` | ❌ | ❌ | Decide *what* to do (LLM input shaping, dispatch routing, prompt build) |
| `local_reactive` | `LocalReactiveContext` | ✅ | ✅ | React to live DOM events (typing, clicking, hot-path orchestration) |
| `local_extract` | `LocalExtractContext` | ✅ | ✅ | Read DOM state and ship it back to the cloud (scrape-only, never types) |

The class lives at
[`agent/ec_skills/browser_node/contexts.py`](../agent/ec_skills/browser_node/contexts.py).

```python
from agent.ec_skills.browser_node.contexts import CloudHookContext

class MyPromptBuilder:
    EXECUTION_TIER = "cloud_only"

    async def run(self, ctx: CloudHookContext, state: dict, inputs: dict):
        # ctx has: state_kv, agent_registry, send_chat, scrape_fn,
        #          resolve_template, run_id, etc.
        # ctx does NOT have: browser_session, mainwin, typing_lock.
        ...
```

A hook that does not declare `EXECUTION_TIER` is treated as a
**legacy v1 hook** and runs through the original code path — there is
no breaking change.

## The four run modes

The runtime knows about four `runEnvironment` values (set per-node in
the flowgram JSON):

| `runEnvironment` | Effective `RunMode` | What runs where |
|---|---|---|
| `full_local` (default) | `FULL_LOCAL` | All hooks in-process on the user's machine |
| `passive_local` | `FULL_LOCAL` | Same as full_local; the "passive" qualifier is about transport, not hook tiering |
| `full_cloud` | `FULL_LOCAL` | All hooks in-process on the cloud worker (the cloud worker IS the local from the hook's POV) |
| `hybrid_cloud` | `HYBRID_CLOUD` | `cloud_only` hooks on cloud worker; `local_reactive` / `local_extract` hooks on local agent; calls cross via RPC |

`RunMode` lives at
[`agent/ec_skills/browser_use_extension/tier_aware_runner.py`](../agent/ec_skills/browser_use_extension/tier_aware_runner.py).
Only **two** values exist (`FULL_LOCAL` and `HYBRID_CLOUD`); the
collapse is intentional — when everything sits in one process there
is no transport selection to make.

## Where the run mode comes from

**This is per-skill, per-node config — not an environment variable.**

The flowgram JSON for a `BrowserAutomation` node carries:

```json
{
  "runEnvironment": { "content": "hybrid_cloud" }
}
```

`build_browser_automation_node` reads it into
`BrowserUseRunContext.run_environment_setting`
([`build_node.py:7007`](../agent/ec_skills/build_node.py)).

For v2 hooks, `BrowserUseRunner._build_hook_ctx` propagates that field
into the new `BrowserUseHookContext.run_environment` slot
([`runner.py:3453`](../agent/ec_skills/browser_node/runner.py)). The
v2 dispatcher (`_dispatch_v2_if_eligible` in
[`hooks.py`](../agent/ec_skills/browser_node/hooks.py)) reads
`ctx.run_environment` and picks the corresponding `RunMode`.

```python
mode = (
    RunMode.HYBRID_CLOUD
    if str(ctx.run_environment).lower() == "hybrid_cloud"
    else RunMode.FULL_LOCAL
)
```

There is no `EC_RUN_MODE` or similar env var. Do not add one — the
mode is a property of the skill graph, not the deployment.

## Authoring a v2 hook

### Minimum viable cloud_only hook

```python
# my_bundle/my_prompt_hook.py
from agent.ec_skills.browser_node.contexts import CloudHookContext

class MyPromptBuilder:
    EXECUTION_TIER = "cloud_only"

    async def run(self, ctx: CloudHookContext, state: dict, inputs: dict):
        # Read state via the SessionKV abstraction, not raw dicts.
        last_msg = ctx.state.get("last_msg") or ""
        if not last_msg:
            return None  # Don't short-circuit
        # Optionally short-circuit by returning a result dict.
        return {
            "task_text_override": f"Reply to: {last_msg}",
            "consumed_event_id": state.get("event_id"),
        }
```

### Registration

Same as a v1 hook. Inside your bundle's `__init__.py` (or wherever
you currently call `register_before_*_hook`):

```python
from agent.ec_skills.browser_node.hooks import register_before_prompt_build_hook
from .my_prompt_hook import MyPromptBuilder

register_before_prompt_build_hook(MyPromptBuilder())
```

The runtime detects `EXECUTION_TIER` automatically and routes through
the tier-aware runner. **No changes to your registration code are
required to migrate.**

### The three context types

Pick the smallest one that suffices for what your hook does.

| Capability | `CloudHookContext` | `LocalReactiveContext` | `LocalExtractContext` |
|---|:---:|:---:|:---:|
| `state` (SessionKV) | ✅ | ✅ | ✅ |
| `node_name`, `calling_agent_id` | ✅ | ✅ | ✅ |
| `resolve_template` | ✅ | ✅ | ✅ |
| `dispatch_state` (inflight + msg-id) | ✅ | ✅ | ❌ |
| `agent_registry` | ✅ | ❌ | ❌ |
| `send_chat` | ✅ | ❌ | ❌ |
| `scrape_fn` | ✅ | ❌ | ❌ |
| `primitives` (BrowserPrimitives) | ❌ | ✅ | ✅ |
| `typing_lock` | ❌ | ✅ | ❌ |
| `browser_session` | ❌ | ❌ | ❌ |

`browser_session` is **deliberately absent** from all three. A v2
hook that needs DOM access goes through `primitives` (eval_js, click,
type, wait_for, read_dom) — these are the only operations the
hybrid-cloud transport can serialise.

### `BrowserPrimitives` — the only DOM surface

```python
class BrowserPrimitives(Protocol):
    async def eval_js(self, snippet: str, *, timeout_ms: int = 3000) -> Any: ...
    async def click(self, selector: str, *, timeout_ms: int = 3000) -> bool: ...
    async def type(self, selector: str, text: str, *,
                   clear_first: bool = True, submit: bool = False) -> bool: ...
    async def wait_for(self, selector: str, *, condition: str = "present",
                       timeout_ms: int = 5000) -> bool: ...
    async def read_dom(self, selector: str, *, depth: int = 2) -> dict: ...
```

When `RunMode.FULL_LOCAL`, calls go straight to a `browser_session`
adapter. When `RunMode.HYBRID_CLOUD` and the hook is running on the
cloud worker, calls are serialised into `PrimitiveCommand` messages,
shipped to the local agent over AppSync, and the result comes back as
`PrimitiveResult`.

This is the **single integration point** that makes a hook portable.
A hook that uses only `primitives` is automatically hybrid-safe.

## Runtime dispatch flow

```
                    ┌──────────────────────────────┐
                    │  BrowserUseRunner            │
                    │  build_node.py invokes:      │
                    │    invoke_early_hooks()      │
                    │    invoke_prompt_build_hooks│
                    │    invoke_late_hooks()       │
                    └──────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │  for hook in registered:           │
              │    _dispatch_v2_if_eligible(hook)  │
              │       │                            │
              │       ├─ has EXECUTION_TIER + run? │
              │       │   yes → tier-aware path    │
              │       │   no  → legacy fallback    │
              └───────┬────────────────────────────┘
                      │
        tier-aware    │       legacy
        path          │       fallback
                      ▼              ▼
        ┌──────────────────────┐  ┌──────────────────────┐
        │ legacy_bridge:       │  │ await hook(           │
        │   backends_from_     │  │   agent, state,       │
        │   legacy_context()   │  │   inputs, ctx)        │
        │                      │  └──────────────────────┘
        │ TierAwareRunner(     │
        │   mode=...,          │
        │   backends=...)      │
        │                      │
        │ runner.dispatch(hook)│
        │   └─ build typed ctx │
        │   └─ await hook.run()│
        └──────────────────────┘
```

The legacy fallback path is **bit-for-bit identical** to pre-v2
behaviour. v2 is purely additive; opting in is a per-hook decision
made by adding a single `EXECUTION_TIER` class attribute.

## Hybrid wire protocol

Lives at
[`agent/ec_skills/browser_use_extension/hybrid_protocol.py`](../agent/ec_skills/browser_use_extension/hybrid_protocol.py).

Eight message types travel over a single `HybridTransport`:

| Message | Direction | Purpose |
|---|---|---|
| `PrimitiveCommand` | cloud → local | Invoke a `BrowserPrimitives` method |
| `PrimitiveResult` | local → cloud | Result of a primitive call |
| `ScrapeRequest` | cloud → local | Request a `local_extract` hook to run |
| `ScrapeResponse` | local → cloud | Extract output |
| `EventEnvelope` | local → cloud | DOM event → cloud-side `local_reactive` decision |
| `HookOutcome` | either | Generic hook return marshalling |
| `BundleDeliveryRequest` | cloud → local | Ship a signed bundle to a local agent |
| `BundleDeliveryResponse` | local → cloud | Install outcome |

The transport itself is a `Protocol` with two methods:

```python
class HybridTransport(Protocol):
    async def send(self, msg: BaseModel) -> None: ...
    async def recv(self) -> BaseModel: ...
```

Two concrete implementations exist:

- `LoopbackTransport` — in-memory queue, used by tests.
- `AppSyncHybridTransport` — production AWS AppSync wire format
  ([`appsync_hybrid_transport.py`](../agent/ec_skills/browser_use_extension/appsync_hybrid_transport.py)).
  Discriminates messages by a `type` string in the GraphQL payload;
  the discriminator → Pydantic class map lives in
  `MESSAGE_TYPE_REGISTRY`.

### GraphQL schema (production-side)

```graphql
type Mutation {
  publishHybridMessage(input: HybridMessageInput!): HybridMessage
}
type Subscription {
  onHybridMessage(runId: ID!, clientId: ID!): HybridMessage
}
input HybridMessageInput {
  runId: ID!
  clientId: ID!
  stepId: ID
  type: String!     # one of MESSAGE_TYPE_REGISTRY keys
  payload: AWSJSON! # serialised Pydantic model
}
```

## Bundle delivery (hybrid_cloud only)

In `full_local` and `full_cloud`, every bundle that should run is
already on the machine that runs it. In `hybrid_cloud` the cloud
worker holds the authoritative bundle catalogue, and the local agent
needs the bundle code to actually run `local_reactive` /
`local_extract` hooks.

The solution is **on-demand signed bundle delivery**, implemented in
[`bundle_delivery.py`](../agent/ec_skills/browser_use_extension/bundle_delivery.py).

### Cloud side

```python
from agent.ec_skills.browser_use_extension.bundle_delivery import pack_bundle_request

req = pack_bundle_request(
    bundle_dir="/path/to/bundle",
    secret=secret_bytes,           # HMAC key
    key_id="bundle-signing-key-1", # for receiver lookup
    run_id="run_abc",
    step_id="step_xyz",
)
await transport.send(req)
```

The pack function reuses the existing `hook_signing` HMAC-SHA256
infrastructure verbatim (see `HOOK_BUNDLES.md` § *Trust model and
signing*). No new crypto is introduced. Files travel as either
UTF-8 strings or `{"b64": "..."}` dicts; per-file size is capped at
200 KB to fit AppSync's payload ceiling.

### Local side

```python
from agent.ec_skills.browser_use_extension.bundle_delivery import BundleDeliveryExecutor

ex = BundleDeliveryExecutor(install_root="/path/to/hooks/external")
resp: BundleDeliveryResponse = await ex.run_one(req)
if resp.ok:
    print("installed at", resp.installed_path)
else:
    print("rejected:", resp.error, resp.error_detail)
```

The executor:

1. Materialises files to a **temp staging directory**.
2. Refuses any path-escape entries (`../`, absolute paths).
3. Writes `hook.sig` and calls `hook_signing.enforce_trust()`
   **before** any Python import of bundle code.
4. On signature failure: deletes the staging dir and returns a
   structured `error` tag.
5. On success: atomic-ish rename into `install_root/<bundle_name>`.

Error vocabulary is fixed (`signature_invalid`, `manifest_missing`,
`extract_failed`) so cloud-side categorisation never needs string
parsing.

### Threat model

The transport already terminates TLS, so files are not separately
encrypted. The HMAC signature exists to defeat **misuse of an
honest transport**, not eavesdropping — i.e. an operator must not be
able to ship a bundle they don't have the key for. If a stricter
threat model is required (e.g. vendor-distributed bundles where the
operator must not see the source), the `files` field accepts
arbitrary dict-shaped values, leaving room for a future
`{"enc": "...", "iv": "..."}` envelope.

## Migrating a v1 hook to v2

The migration is **one class attribute and one method signature
change** per hook. The hook's logic does not change.

### Before (v1)

```python
class FeigeQuickReplyHook:
    async def __call__(self, agent, state, inputs, ctx):
        # ctx is BrowserUseHookContext (the wide one)
        if not state.get("active_customer"):
            return None
        ...
        return {"short_circuit_state": "done"}
```

### After (v2)

```python
from agent.ec_skills.browser_node.contexts import LocalReactiveContext

class FeigeQuickReplyHook:
    EXECUTION_TIER = "local_reactive"

    async def run(self, ctx: LocalReactiveContext, state: dict, inputs: dict):
        if not ctx.state.get("active_customer"):
            return None
        ...
        return {"short_circuit_state": "done"}
```

Two real changes:

1. `__call__(self, agent, state, inputs, ctx)` → `run(self, ctx, state, inputs)`.
2. Dict access on `ctx.dispatch_state_by_agent[k]` becomes
   `ctx.state.get(k)` / `.set(k, v)` via the SessionKV abstraction.

The reward: the same hook now runs unchanged when the operator
flips `runEnvironment` to `hybrid_cloud` — provided every DOM access
goes through `ctx.primitives`.

### Reference migrations

The Feige bundle has been fully ported. Compare the v1 → v2 for
each:

| v1 file | v2 file | Tier |
|---|---|---|
| `pre_dispatch.py::before_run_hook` | `pre_dispatch_v2.py` (split into 2) | `cloud_only` + `local_extract` |
| `actionable_items.py::before_prompt_build_hook` | `actionable_items_v2.py` | `cloud_only` |
| `quick_reply_hook.py::FeigeQuickReplyHook` | `quick_reply_v2.py` | `local_reactive` |
| `crosstalk_guard.py::FeigeCrosstalkGuardHook` | `crosstalk_guard_v2.py` | `local_reactive` |
| `front_desk_hot_path.py::before_session_setup_hook` | `front_desk_hot_path_v2.py` + `hot_path_v2.py` | `local_reactive` |

Tests for each: `tests/test_*_v2.py`.

## Reference: file layout

```
agent/ec_skills/
├── browser_node/
│   ├── contexts.py             ← Context Protocols + dataclasses
│   │                              (CloudHookContext, LocalReactiveContext,
│   │                               LocalExtractContext, BackendBundle,
│   │                               BrowserPrimitives Protocol, SessionKV
│   │                               Protocol, AgentRegistry Protocol, ...)
│   ├── hooks.py                ← register_*_hook + _dispatch_v2_if_eligible
│   └── runner.py               ← _build_hook_ctx populates run_environment
│
└── browser_use_extension/
    ├── tier_aware_runner.py    ← RunMode enum + TierAwareRunner +
    │                              ContextBuilder
    ├── hybrid_protocol.py      ← 8 Pydantic message types + HybridTransport
    │                              Protocol + LoopbackTransport
    │                              + RpcBrowserPrimitives + RpcScrapeFunction
    ├── appsync_hybrid_transport.py ← AWS AppSync HybridTransport impl
    ├── legacy_bridge.py        ← BrowserUseHookContext → BackendBundle
    │                              (wire-up bridge for v2 hooks invoked
    │                               from the legacy lifecycle path)
    ├── bundle_delivery.py      ← pack_bundle_request (cloud) +
    │                              BundleDeliveryExecutor (local)
    ├── hook_signing.py         ← Existing HMAC-SHA256 (reused, unchanged)
    └── hooks/external/feige_chat/
        ├── pre_dispatch_v2.py
        ├── actionable_items_v2.py
        ├── quick_reply_v2.py
        ├── crosstalk_guard_v2.py
        ├── front_desk_hot_path_v2.py
        └── hot_path_v2.py      ← BrowserPrimitives + ToolInvoker port of
                                   v1 hot_path.execute (no browser_session)
```

## Testing

Every layer has a dedicated test file. All tests run as plain
`unittest` (no fixtures, no marks) so they execute in any
environment that can import the package.

| Test file | What it validates |
|---|---|
| `tests/test_tier_aware_runner.py` | Mode-aware backend selection, message-registry contract, structural typing |
| `tests/test_hybrid_protocol.py` | Pydantic round-trip, `LoopbackTransport`, `RpcBrowserPrimitives` end-to-end |
| `tests/test_pre_dispatch_v2.py` | Cross-tier split (cloud_only + local_extract) |
| `tests/test_quick_reply_v2.py` | LocalReactive port of FeigeQuickReplyHook |
| `tests/test_actionable_items_v2.py` | CloudHook port of prompt-build |
| `tests/test_crosstalk_guard_v2.py` | LocalReactive port |
| `tests/test_front_desk_hot_path_v2.py` | LocalReactive outer flow |
| `tests/test_step5_and_wireup.py` | `legacy_bridge` adapters, `_dispatch_v2_if_eligible` mode selection, `hot_path_v2` DOM orchestration, `bundle_delivery` pack + install + round-trip |

Run all hook v2 tests:

```powershell
python -m unittest `
  tests.test_tier_aware_runner `
  tests.test_hybrid_protocol `
  tests.test_pre_dispatch_v2 `
  tests.test_quick_reply_v2 `
  tests.test_actionable_items_v2 `
  tests.test_crosstalk_guard_v2 `
  tests.test_front_desk_hot_path_v2 `
  tests.test_step5_and_wireup `
  tests.test_feige_bundle
```

## FAQ

### Do I need to migrate my v1 hooks?

No. Legacy hooks (no `EXECUTION_TIER` attribute) keep working
forever. Migrate only when you want hybrid-cloud portability for
that specific hook.

### Can a single bundle mix v1 and v2 hooks?

Yes. The dispatcher decides per-hook based on `EXECUTION_TIER`. A
bundle can register a v1 callable and a v2 class side by side.

### My hook needs `mainwin` / `agent.browser_session`. Can it be v2?

Only if you classify it as `local_reactive` or `local_extract` —
those tiers do still have local-side capabilities. But you should
prefer `ctx.primitives` over reaching for `browser_session` directly,
because primitives are the only DOM surface that is hybrid-safe.

If you genuinely need raw `browser_session` access (e.g. for a
browser-use API not exposed via primitives), keep the hook as v1
and accept that it cannot run hybrid_cloud.

### Why not auto-detect the tier from the hook's behaviour?

Static analysis can't reliably tell whether a hook reaches into
`agent.browser_session` through any of dozens of indirection paths
(decorators, getattr, helper functions). Making the author state
the tier explicitly is the only honest contract.

### Can I run cloud_only hooks locally for testing?

Yes — `RunMode.FULL_LOCAL` runs every tier in-process. The cloud
side will simply use in-process implementations of `agent_registry`,
`send_chat`, etc. The transport is unused. This is how the test
suite exercises the cloud_only Feige hooks without spinning up
AppSync.

### How do I trigger bundle delivery in production?

The cloud worker, on receiving a step that requires a bundle the
local doesn't have, calls `pack_bundle_request` and ships the result
via `transport.send`. The local agent's message dispatcher
recognises `bundle_delivery_request` and hands it to a
`BundleDeliveryExecutor`. Wiring the dispatcher → executor link is
**not yet enabled by default** — when an operator flips a specific
bundle to `hybrid_cloud`, that's the moment to add the dispatcher
case (one if-branch). The executor itself is fully implemented and
tested.

### Is `EC_HOOK_TRUST_MODE` still respected for delivered bundles?

Yes. Bundle delivery uses the exact same `enforce_trust()` call as
on-disk bundles, so `permissive` / `strict` / `lockdown` semantics
carry over verbatim. See `HOOK_BUNDLES.md` § *Trust model and
signing*.

---

## See also

- [`BUILD_NODE_LIFECYCLE_HOOKS.md`](./BUILD_NODE_LIFECYCLE_HOOKS.md) —
  the v1 lifecycle hook contract that v2 extends.
- [`HOOK_BUNDLES.md`](./HOOK_BUNDLES.md) — the in-agent-loop
  `HookDispatcher` system; orthogonal to v2.
- [`BROWSER_AUTOMATION_NODE_CONFIG.md`](./BROWSER_AUTOMATION_NODE_CONFIG.md) —
  where `runEnvironment` (and other per-node fields) come from.
