# Feige chat — reference external hook bundle

This bundle is the **reference implementation** of an external hook bundle.
If you want to add site-specific browser automation behavior for a new
customer site, copy this directory, rename it, and edit the two files.

## Files

```
feige_chat/
  hook.yaml         ← manifest (required)
  feige_hooks.py    ← Hook implementations
  README.md         ← this file (optional but polite)
```

## Enabling the bundle on a node

In the browser_automation node editor → **Node Behavior** → **Hook Bundles (JSON)**:

```json
[
  {
    "path": "feige_chat",
    "enabled": true,
    "config": {
      "cooldown_ms": 2000,
      "quick_replies": {
        "你好": "您好,请问有什么可以帮您?"
      }
    }
  }
]
```

`path` can be:

| Value                                | Resolution                                                                 |
|--------------------------------------|----------------------------------------------------------------------------|
| `"feige_chat"`                       | In-tree: `agent/ec_skills/browser_use_extension/hooks/external/feige_chat` |
| `"C:\\my-hooks\\acme_chat"`          | Absolute path anywhere on disk                                             |
| `"pkg:my_company.hooks.acme"`        | Pip-installed package; uses its `__path__[0]`                              |

## Loading order

`PrivacyAgent` registers in this order:

1. User hooks passed directly as `hooks=[...]`
2. External bundles from `hook_bundles=[...]`   ← **this bundle**
3. Built-in Tier-0 hooks (if `hooks_enabled=True`)

Within a stage, priority (lower = earlier) decides execution order regardless
of registration order.

## The two hooks shipped here

### `feige_quick_reply` — `on_event_normalized`, `Bypass`

Replaces the legacy `hotPathActions` JSON blob with real Python logic.
When an incoming normalized event has text that matches one of the
bundle's `quick_replies` keys, this hook returns `HookResult.bypass(...)`
with a deterministic `feige_send_message` action — **the LLM never runs
for that event**.

Per-customer cooldown (`cooldown_ms`) prevents runaway loops if a page
emits duplicate events during a DOM storm.

### `feige_crosstalk_guard_ext` — `on_pre_action`, `Drop`

Widens the in-tree Tier-0 `verify_active_session` crosstalk guard with
Feige-specific arg key aliases (`recipient`, `chat_target`) and adds
`feige_send_draft` to the guarded-actions list.  Runs *after* the
Tier-0 guard (priority 6 vs 5) so both nets catch mismatches — the
cost is negligible because each guard short-circuits the moment the
action name doesn't match.

## Authoring a new bundle — checklist

1. **Copy this directory** and rename to your bundle name (snake_case).
2. **Edit `hook.yaml`**:
   - Update `bundle:` and `version:`.
   - List every hook with its `stage`, `tier: 1`, `priority`, `entrypoint`.
   - Declare `permissions.tools` with exact tool names you'll call.
     The ScopedToolProxy enforces this at runtime; calling outside the
     list raises `PermissionDenied`.
   - Keep `tier: 1` or `tier: 2`. The loader refuses `tier: 0`
     (reserved for in-tree safety built-ins).
3. **Write your hook class**. Minimum contract:

    ```python
    class MyHook:
        manifest = None   # set by loader

        def __init__(self, config=None, manifest=None):
            self.config = config or {}
            self.manifest = manifest

        async def run(self, ctx, payload):
            return HookResult.cont()
    ```

4. **Test locally**. See `tests/test_feige_bundle.py` as a template —
   build a `HookBundleSpec`, call `load_bundle(spec)`, drive the hook
   through a mock `HookContext`.

## Decision verbs cheat-sheet

| Return value              | Effect                                                       |
|---------------------------|--------------------------------------------------------------|
| `HookResult.cont()`       | Proceed normally.                                            |
| `HookResult.replace(p)`   | Rewrite the payload for the next hook / stage.               |
| `HookResult.bypass(acts)` | Emit deterministic `[BypassAction]`, skip the LLM.           |
| `HookResult.drop()`       | Swallow the event entirely — no further action.              |
| `HookResult.handoff(a)`   | Hand off to a named sub-agent (orchestration-layer concept). |
| `HookResult.escalate()`   | Force LLM even when a prior hook said Bypass.                |

## Gotchas

- **No mutation of shared context.** `ctx.config`, `ctx.site_adapter`,
  `ctx.manifest` are shared across invocations.  `ctx.state` is yours
  to mutate freely.
- **Budget.** `manifest.budget.timeout_ms` is enforced by the dispatcher.
  Long-running operations (CDP calls, network) should use 1–2s; pure
  Python predicates should stay under 100ms.
- **Circuit breaker.** A hook that throws `failure_threshold` times (5 by
  default) within `cool_down_s` (60s) is disabled until the cool-down
  expires.  Fix your hook promptly; don't rely on cool-down to mask bugs.
- **State store.** `state: memory` clears on agent teardown; `state: disk`
  persists under the skill bundle's state dir.  Paired hooks that need
  to share state (acquire+release) should set the same `state_namespace`.
