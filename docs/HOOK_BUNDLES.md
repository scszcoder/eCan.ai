# Browser-Automation Hook Bundles

A **hook bundle** is a self-contained directory of code + manifest that
extends the browser-automation node's behavior **without editing
`build_node.py` or any core agent code**.  The feature is fully opt-in
and strictly additive — existing skills continue to work unchanged.

> **TL;DR** – Copy `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/`,
> rename it, edit the manifest, point your node at it via the **Hook
> Bundles (JSON)** field.  No redeploy required.

> **Two hook systems coexist in this repo.**  The one described in this
> document (`HookDispatcher`, `hook.yaml`, stages like `on_pre_action` /
> `on_event_normalized`, signed bundles, runtime lanes) fires **inside
> the browser-use agent loop** — it intercepts individual events,
> actions, and per-step page state.  A *separate* lightweight system
> (`register_before_prompt_build_hook` / `register_before_browser_use_run_hook`
> / `register_before_browser_session_setup_hook`) wraps the entire
> browser-automation node and is documented in
> [`BUILD_NODE_LIFECYCLE_HOOKS.md`](./BUILD_NODE_LIFECYCLE_HOOKS.md).
> A single bundle directory (e.g. `feige_chat`) can — and does — serve
> both systems; they solve non-overlapping problems.  Pick the right
> layer for your use case before authoring.

> **Hybrid-cloud bundle delivery.**  The signing infrastructure
> described under *Trust model and signing* below is reused verbatim
> for **on-demand bundle distribution** to local agents in
> `runEnvironment=hybrid_cloud` skills (the cloud worker holds the
> authoritative bundle catalogue; locals receive bundles over the
> hybrid wire protocol when a skill needs them).  See
> [`HYBRID_CLOUD_HOOKS.md`](./HYBRID_CLOUD_HOOKS.md) §
> *Bundle delivery* for the cloud-side `pack_bundle_request` and the
> local-side `BundleDeliveryExecutor`.  No new crypto is introduced;
> only the transport changes.

- [Concepts](#concepts)
- [Bundle layout](#bundle-layout)
- [Writing a hook](#writing-a-hook)
- [Decision verbs](#decision-verbs)
- [Runtime lanes](#runtime-lanes)
- [Trust model and signing](#trust-model-and-signing)
- [Wiring a node](#wiring-a-node)
- [Catalog / indexer](#catalog--indexer)
- [Authoring checklist](#authoring-checklist)
- [Troubleshooting](#troubleshooting)
- [Design notes](#design-notes)

## Concepts

### Stages

The dispatcher fires hooks at nine well-defined points in the agent
loop.  Pick the earliest one that can answer your question:

| Stage                   | When it fires                                                   |
|-------------------------|-----------------------------------------------------------------|
| `on_event_raw`          | New DOM/browser event arrives, pre-normalisation                |
| `on_event_normalized`   | Normalised event dict ready for dispatch                        |
| `on_pre_step`           | Beginning of each agent step                                    |
| `on_post_observe`       | After page state captured, before LLM sees it                   |
| `on_pre_action`         | An action is about to execute                                   |
| `on_post_action`        | An action just executed                                         |
| `on_step_end`           | End of each step                                                |
| `on_error`              | An error bubbled up                                             |
| `on_done`               | Agent completed                                                 |

### Tiers

| Tier | Source                                      | Privileges                      |
|------|---------------------------------------------|---------------------------------|
| 0    | In-tree `hooks/builtin/` (safety rails)     | Cannot be shadowed or unregistered |
| 1    | Distributor / vendor bundles (signed, strict mode) | Full hook surface         |
| 2    | Skill-local bundles                         | Same surface as Tier 1, weaker trust |

The loader **refuses** any external bundle that declares `tier: 0`.
Tier-0 is reserved for a fixed set of in-tree hooks like
`verify_active_session` and the typing-lock acquire/release pair.

### Decisions

A hook returns a `HookResult`.  The dispatcher reads the decision and
acts accordingly:

| Decision     | Meaning                                                       |
|--------------|---------------------------------------------------------------|
| `CONTINUE`   | Default — next hook runs, then the LLM                        |
| `REPLACE`    | Rewrite the payload that flows into the next stage/hook       |
| `BYPASS`     | Skip the LLM; run these deterministic actions instead         |
| `DROP`       | Swallow this event entirely                                   |
| `HANDOFF`    | Transfer control to a named sub-agent (orchestrator concept)  |
| `ESCALATE`   | Force LLM execution even if a prior hook said `BYPASS`        |

## Bundle layout

```
my_bundle/
  hook.yaml         ← manifest (required)
  hooks.py          ← Python hook classes (for runtime:python)
  predicate.js      ← optional, for runtime:js_injected
  README.md         ← optional but encouraged
  hook.sig          ← optional detached HMAC signature
```

### `hook.yaml`

```yaml
api_version: 1
bundle: my_site_chat
version: 1.0.0
author: "Acme Corp"
description: "My site's chatbot automation"

# Bundle-level defaults, merged with per-node user overrides.
config:
  cooldown_ms: 1500
  quick_replies:
    "hi": "hello!"

# Optional JSON-schema description of user-configurable keys.  The
# node editor will consume this in a future release to render a typed
# form instead of a free-form JSON blob.
config_schema:
  type: object
  properties:
    cooldown_ms:
      type: integer
      title: "Cooldown (ms)"
      minimum: 0
      default: 1500

hooks:
  - name: my_quick_reply
    entrypoint: "hooks.py:QuickReplyHook"   # module:Class OR file.py:Class
    stage: on_event_normalized
    tier: 1
    priority: 20                            # lower = earlier
    permissions:
      tools: ["my_send_message"]           # enforced at runtime
      network: none                         # none / whitelist / full
    budget:
      timeout_ms: 200
    matches:                                 # optional prefilter
      event_type: ["chat_message"]
    state: memory                            # or 'disk' for persistence
    state_namespace: my_quickreply           # share across paired hooks
```

Every field above is validated by `HookManifest` (Pydantic).  Unknown
top-level keys are forward-compatible (ignored) so bundles written
for newer API versions degrade gracefully on older agents.

## Writing a hook

The minimum contract is a class with a `manifest` attribute and an
async `run()` method:

```python
from agent.ec_skills.browser_use_extension.hook_api import HookResult

class QuickReplyHook:
    manifest = None   # set by loader post-init

    def __init__(self, config=None, manifest=None):
        self.config = config or {}
        self.manifest = manifest

    async def run(self, ctx, payload):
        # ctx.config   — merged config dict (bundle < user < per-hook)
        # ctx.state    — small KV store (memory or disk)
        # ctx.tools    — ScopedToolProxy (permissions enforced)
        # ctx.browser_session — live BrowserSession or None in tests
        # ctx.logger, ctx.trace_id, ctx.span_id — diagnostics
        if not isinstance(payload, dict):
            return HookResult.cont(reason="not-a-dict")
        ...
        return HookResult.cont()
```

**Never mutate** `ctx.config`, `ctx.site_adapter`, or `ctx.manifest` —
those are shared across invocations.  `ctx.state` is yours.

## Decision verbs

```python
HookResult.cont(reason="...")
HookResult.replace(new_payload, reason="...")
HookResult.bypass([BypassAction(name="send", args={...})], reason="...")
HookResult.drop(reason="...")
HookResult.handoff("other_agent")
HookResult.escalate()
```

## Runtime lanes

Three runtimes, all sharing the same `HookResult` response shape:

### `runtime: python` (default)

Direct in-process import.  Fastest path; no serialization overhead.

### `runtime: js_injected`

Ship a `.js` file with a top-level `hook(payload) → {decision, ...}`
function.  The dispatcher wraps it in an IIFE, evaluates via CDP, and
parses the stringified JSON result.  Great for pure-DOM predicates —
avoids a Python↔browser round-trip per check.

```yaml
- name: js_predicate
  runtime: js_injected
  entrypoint: "predicate.js"
  stage: on_pre_action
  tier: 1
```

```javascript
// predicate.js
function hook(payload) {
  if (!payload || !payload.text) return {decision: "continue"};
  const active = !!document.querySelector(".chat.active");
  return active
    ? {decision: "continue", reason: "js:ok"}
    : {decision: "drop",     reason: "js:no-active"};
}
```

Fail-open: missing browser, eval error, or malformed JSON all collapse
to `CONTINUE` with a structured reason.

### `runtime: subprocess`

Run any executable; the dispatcher speaks JSON-lines over stdio.

```yaml
- name: legacy_score
  runtime: subprocess
  entrypoint: ["node", "hook.js"]    # argv
  stage: on_event_normalized
  tier: 1
  budget:
    timeout_ms: 1200
```

Protocol: one request JSON per line in, one response JSON per line out.
Child process is reused across invocations (lazy spawn), killed +
respawned on timeout, and torn down by `PrivacyAgent.shutdown_hooks()`.

## Trust model and signing

Environment variable `EC_HOOK_TRUST_MODE` selects the gate:

| Mode          | In-tree bundles    | Out-of-tree bundles             |
|---------------|--------------------|---------------------------------|
| `permissive`  | Trusted            | Trusted (signature verified if present) |
| `strict`      | Trusted            | **Must have valid `hook.sig`**  |
| `lockdown`    | **Must be signed** | **Must be signed**              |

### Signing a bundle (HMAC-SHA256)

```bash
# Vendor side
EC_HOOK_KEY_VENDOR_A="hexsecretordisplaystring" \
  python -m agent.ec_skills.browser_use_extension.hook_signing \
  path/to/bundle vendor-a
# → writes path/to/bundle/hook.sig
```

### Verifying on the operator side

Either set the secret in the environment:

```bash
export EC_HOOK_KEY_VENDOR_A="hexsecretordisplaystring"
export EC_HOOK_TRUST_MODE=strict
```

Or point at a keyring file:

```bash
export EC_HOOK_KEYRING=/path/to/keyring.json
# keyring.json: {"vendor-a": "hexsecretordisplaystring"}
```

The signature covers the raw UTF-8 bytes of `hook.yaml`; any tamper —
a single added whitespace — breaks verification.  A present-but-
invalid signature is **always** a hard error regardless of trust mode.

## Wiring a node

In the browser-automation node editor, **Node Behavior → Hook Bundles
(JSON)**:

```json
[
  {
    "path": "feige_chat",
    "enabled": true,
    "config": {
      "cooldown_ms": 2000,
      "quick_replies": { "hello": "hi there!" }
    }
  },
  {
    "path": "C:/customer-x/acme_hooks",
    "config": {}
  },
  {
    "path": "pkg:my_company.hooks.acme"
  }
]
```

Path resolution:

| Value                        | Resolves to                                         |
|------------------------------|-----------------------------------------------------|
| `feige_chat`                 | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat` |
| `C:/abs/path/my_bundle`      | Absolute path on disk                               |
| `pkg:my_co.hooks.acme`       | Pip-installed package; uses `__path__[0]`           |

Setting this field (or **Site Adapter (JSON)**, or env var
`EC_BROWSER_USE_HOOKS_ENABLED=1`) automatically opts the node's
`PrivacyAgent` into the hook system.  Tier-0 safety hooks
(`verify_active_session`, `typing_lock_*`) register alongside your
bundle hooks; they always run **first** within their stage regardless
of what your bundle declares.

## Catalog / indexer

List every bundle under the in-tree dir with structured metadata:

```python
from agent.ec_skills.browser_use_extension.hook_loader import (
    list_available_bundles,
    write_bundle_index,
)

for entry in list_available_bundles():
    print(entry["name"], entry["version"], entry["description"])

# Or bake into a static JSON for the GUI to consume:
write_bundle_index("gui_v2/public/hook_bundles_index.json")
```

The index record per bundle includes `name`, `version`, `description`,
`signed`, `hooks[]`, `config_defaults`, and `config_schema`.  That's
the forward contract for the node editor's future dynamic form
renderer.

## Authoring checklist

1. Copy `hooks/external/feige_chat/` and rename the directory.
2. Edit `hook.yaml` — update `bundle:`, `version:`, every hook's
   `name`, `entrypoint`, `stage`, `priority`, `permissions.tools`.
3. Never declare `tier: 0` (loader rejects it).
4. Implement each hook class following the minimum contract above.
5. Add a `config_schema` block if you want the GUI to pre-populate
   user-facing config keys in a future release.
6. Run the bundle's tests (`python -m unittest tests.test_<bundle>`).
7. Point one canary node at it via **Hook Bundles (JSON)**.
8. Monitor: each hook logs `[HookDispatcher] <name> decision=<verb>
   duration=<ms>`.  Circuit breaker trips at 5 failures / 60s.
9. Optional — sign the bundle for `strict`/`lockdown` deployments.

## Troubleshooting

| Symptom                                             | Likely cause                                         |
|-----------------------------------------------------|------------------------------------------------------|
| `BundlePathError: bundle directory not found`       | `path` typo, or in-tree name isn't under `hooks/external/` |
| `TierViolation: external bundle may not declare tier=0` | Remove `tier: 0` from manifest                   |
| `IncompatibleHookApiVersion`                         | Manifest `hook_api_version` doesn't match runtime    |
| `BundleSignatureError: ... no hook.sig`              | Trust mode is `strict`/`lockdown` but bundle unsigned |
| `BundleSignatureError: ... signature mismatch`       | Manifest was edited after signing, or wrong key      |
| `PermissionDenied` from a tool call                  | Tool name not in `permissions.tools`                 |
| Hook silently doesn't fire                          | Check `matches:` filter; `priority`; and that `stage` enum value is correct |

## Design notes

- **Opt-in everywhere.**  `PrivacyAgent(hooks_enabled=False)` remains
  the default.  `build_node.py` only turns hooks on when a node
  explicitly provides `hookBundles`, `siteAdapter`, or when the
  `EC_BROWSER_USE_HOOKS_ENABLED` env var is set.
- **No `build_node.py` edits** are required to add a new site
  behavior.  That file is ~14k lines; keeping it out of the hot
  iteration path is the primary reason the hook system exists.
- **Tier-0 is un-shadowable.**  A malicious or buggy external bundle
  cannot replace a built-in safety hook.  Name collisions fail
  registration loudly.
- **Fail-open by default.**  Verify/predicate errors collapse to
  `CONTINUE` so a single broken hook cannot wedge an automation.  Use
  Tier-0 hooks for *must-block* policies; those remain authoritative.
- **Per-runtime fault isolation.**  A crashing JS or subprocess hook
  is respawned on the next call and counted against its own circuit
  breaker; the agent loop is unaffected.
- **Shutdown hygiene.**  `PrivacyAgent.shutdown_hooks()` terminates
  subprocess lane children on agent teardown.  Idempotent.

## File map

| Path                                                                                              | Purpose                              |
|---------------------------------------------------------------------------------------------------|--------------------------------------|
| `agent/ec_skills/browser_use_extension/hook_api.py`                                               | Public contract (stages, decisions)  |
| `agent/ec_skills/browser_use_extension/hook_dispatcher.py`                                        | Runtime registry + execution engine  |
| `agent/ec_skills/browser_use_extension/hook_loader.py`                                            | External bundle discovery + loading  |
| `agent/ec_skills/browser_use_extension/hook_signing.py`                                           | HMAC-SHA256 signing + trust gate     |
| `agent/ec_skills/browser_use_extension/hooks/builtin/`                                            | Tier-0 in-tree hooks                 |
| `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/`                                | Reference external bundle            |
| `agent/ec_skills/browser_use_extension/hooks/runtime_lanes/js_lane.py`                            | JS-injected runtime                  |
| `agent/ec_skills/browser_use_extension/hooks/runtime_lanes/subprocess_lane.py`                    | Subprocess runtime                   |
| `agent/ec_skills/browser_use_extension/privacy_agent.py`                                          | PrivacyAgent hook plumbing           |
| `tests/test_hook_*.py, test_feige_bundle.py, test_js_lane.py, test_subprocess_lane.py, test_bundle_index.py` | Test suite (280+ cases)     |
