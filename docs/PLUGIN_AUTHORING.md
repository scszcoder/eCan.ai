# Plugin Authoring Guide

This document is for third-party developers who want to write **eCan
plugins** — self-contained directories of Python + HTML that extend the
browser-automation node's behavior at runtime, without modifying the
host app.

It is the **GUI-author-friendly companion** to
[`HOOK_BUNDLES.md`](./HOOK_BUNDLES.md). HOOK_BUNDLES.md covers the
Python hook API exhaustively; this guide focuses on packaging,
installation, and the bridge protocol that connects your iframe-hosted
config UI to the host app.

## TL;DR

```bash
# generate a starter
python -m agent.ec_skills.browser_use_extension.plugin_scaffold my_plugin

# edit my_plugin/hooks.py and my_plugin/gui/config.html

# install into the user plugins dir via the Plugins page:
#   eCan → Plugins → Install… → point at my_plugin/

# the plugin warm-loads on app start; toggle it from the Plugins page.
```

## Concepts

A **plugin** is a directory with a manifest and at least one Python
hook class. Optionally it ships a `gui/` folder with HTML files the
host renders inside sandboxed iframes — that's how plugins expose
configuration UI without you having to compile against the host's React
version.

| Layer        | Files              | Documented in                           |
|--------------|--------------------|-----------------------------------------|
| Manifest     | `hook.yaml`        | this doc + HOOK_BUNDLES.md              |
| Python hooks | `hooks.py`         | [HOOK_BUNDLES.md](./HOOK_BUNDLES.md)    |
| GUI iframes  | `gui/*.html` + `bridge.js` | this doc (Bridge protocol)      |
| Tests        | `tests/test_*.py`  | this doc                                |

## Install paths

Plugins land under `<appdata>/plugins/<bundle>/` (the platform-aware
data dir — `~/.local/share/eCan/plugins/` on Linux,
`~/Library/Application Support/eCan/plugins/` on macOS,
`%LOCALAPPDATA%\eCan\plugins\` on Windows). The Plugins page's
"Install…" action accepts either a `.zip` archive or a path to a
directory.

In-tree reference bundles live under
`agent/ec_skills/browser_use_extension/hooks/external/` and are
discovered automatically; they cannot be uninstalled from the GUI.

## Bundle layout

```
my_plugin/
  hook.yaml          ← manifest (required)
  hooks.py           ← Python hook classes (entrypoints from manifest)
  README.md          ← optional but encouraged
  hook.sig           ← optional HMAC signature (for vendor distribution)
  gui/               ← optional iframe-hosted GUI
    bridge.js        ← copy of the bridge shim; do not modify
    config.html      ← global config panel (Plugins page)
    node.html        ← per-node config panel (skill editor)
    status.html      ← compact status widget
    theme.css        ← your styles
  tests/test_my_plugin.py
```

The scaffold CLI generates this layout for you.

## Manifest reference

```yaml
api_version: 1                # bridge/host contract version
kind: hook_bundle             # discriminator for future plugin types
bundle: my_plugin             # snake_case; must match the dir name
version: 0.1.0
author: "you"
description: >
  One sentence describing what this plugin does.

# Bundle-level config defaults. Users override globally via the Plugins
# page or per-node via the skill editor's hookBundles entry.
config:
  cooldown_ms: 1500

# JSON-Schema description used by the auto-form renderer when the
# plugin does NOT ship gui/config.html. Optional but strongly
# recommended even with a custom UI — the schema validates user input.
config_schema:
  type: object
  properties:
    cooldown_ms:
      type: integer
      title: "Cooldown (ms)"
      minimum: 0
      default: 1500

# Phase 3+ — iframe-hosted GUI. Omit the block entirely to fall back
# to the schema-driven auto-form.
gui:
  host_api_version: 1
  slots:
    config_panel:                    # rendered on Plugins page → Config tab
      entrypoint: "gui/config.html"
      height: 520
    node_config:                     # rendered inside skill editor (future)
      entrypoint: "gui/node.html"
      height: 360
    status_widget:                   # compact, optional
      entrypoint: "gui/status.html"
      height: 96
  permissions:
    storage_namespace: my_plugin      # KV namespace for ecan.plugin.storage
    bridge_methods:                   # explicit allowlist; methods missing = denied
      - config.get
      - config.set
      - storage.get
      - storage.set
      - storage.keys
      - ui.resize
      - ui.notify
      - host.context
    tools_ui: []                      # subset of permissions.tools usable from GUI

# Hooks: one or more — see HOOK_BUNDLES.md §Writing a hook.
hooks:
  - name: my_plugin_quick_reply
    entrypoint: "hooks.py:QuickReplyHook"
    stage: on_event_normalized
    tier: 1                          # external bundles MUST be >= 1
    priority: 20                     # lower fires first within stage
    permissions:
      tools: []
      network: none
    budget:
      timeout_ms: 200
    matches:
      event_type: ["chat_message"]
    state: memory                    # or 'disk' for persistence
```

`tier: 0` is rejected by the loader — that's reserved for in-tree
safety hooks.

## Bridge protocol (GUI authors)

When the host mounts your iframe it wires a `BridgeHost` to it. Inside
the iframe, load `bridge.js` (a verbatim copy shipped in your `gui/`
folder; the scaffold CLI puts it there) — that exposes
`window.ecan.plugin.*` to your scripts.

```html
<script src="bridge.js"></script>
<script>
  const r = await ecan.plugin.config.get();
  console.log(r.config_effective);
</script>
```

### Methods

All methods return Promises. Errors throw with a `.code` property
(`DENIED`, `BAD_ARGS`, `IPC_FAILED`, `VALIDATION_FAILED`, etc).

| Method                          | Returns                              | Notes |
|---------------------------------|--------------------------------------|-------|
| `ecan.plugin.config.get()`      | `{config_user, config_effective, config_schema}` | Read merged config (defaults ∪ overrides). |
| `ecan.plugin.config.set(patch)` | `{config_user, config_effective}`    | Merge patch into the global user-override. Validated against `config_schema`. |
| `ecan.plugin.config.onChange(cb)` | unsubscribe fn                     | Called when the host or another iframe edits config. |
| `ecan.plugin.storage.get(key)`  | value                                | Per-bundle KV; up to 1 MB total per bundle. |
| `ecan.plugin.storage.set(k, v)` | `{ok}`                               | Pass `v=null` to delete. |
| `ecan.plugin.storage.del(key)`  | `{ok}`                               | Convenience alias for `set(k, null)`. |
| `ecan.plugin.storage.keys()`    | list of strings                      | (Phase 3 returns []; populated in a follow-on.) |
| `ecan.plugin.ui.resize(h)`      | `{height}`                           | Request iframe height change; host clamps to [80, 1800]. |
| `ecan.plugin.ui.notify(type, msg)` | `{ok}`                            | Toast in host UI. Type ∈ {info, warning, error, success}. Rate-limited 2/sec. |
| `ecan.plugin.host.context()`    | `{bundle, scope, theme, locale, …}`  | Read-only context; theme is "dark" or "light". |
| `ecan.plugin.tools.invoke(name, args)` | tool result                   | Gated by `gui.permissions.tools_ui`. Currently returns NOT_IMPLEMENTED — wiring lands in a follow-on slice. |

### Permission gates

- A method must appear in `gui.permissions.bridge_methods` to be
  callable. The host rejects with `DENIED` otherwise.
- `tools.invoke` *additionally* requires the tool name to appear in
  `gui.permissions.tools_ui`.
- Per-node-scope iframes cannot call `config.set` (host denies with
  `WRONG_SCOPE`) — per-node config is persisted via the skill editor's
  hookBundles entry, not the global config file.

### Theme + locale

Read `theme` and `locale` from `ecan.plugin.host.context()`. The
sample `theme.css` from the scaffold uses CSS vars that switch on
`data-theme="dark"`; the suggested pattern is:

```js
const ctx = await ecan.plugin.host.context();
document.documentElement.setAttribute('data-theme', ctx.theme);
```

If the host's theme changes later, listen for the `host.theme_changed`
event (Phase 4 — not pushed yet).

### Security

- Iframes are mounted with `sandbox="allow-scripts"` only. No
  `allow-same-origin`. Your iframe gets its own opaque origin.
- The host applies a strict CSP:
  `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'`.
  That means **no XHR, no fetch, no WebSocket from the iframe** — go
  through the bridge for any data access.
- Plugin GUI files are served from `http://127.0.0.1:<random_port>/p/<bundle>/<file>`.
  Path-traversal is blocked. Only specific file types are served
  (`html, js, css, json, png, jpg, svg, ico, woff, woff2`).

## Authoring workflow

1. **Scaffold** — `python -m agent.ec_skills.browser_use_extension.plugin_scaffold my_plugin`.
2. **Implement** `hooks.py` — see [HOOK_BUNDLES.md](./HOOK_BUNDLES.md)
   for the full HookContext and Decision API.
3. **Implement** `gui/config.html` — the scaffold's example shows the
   common patterns (read context → init form → save back via
   `config.set`). Style with CSS vars so dark mode just works.
4. **Test** — `python -m pytest tests/test_my_plugin.py -v`.
5. **Install locally** — eCan app → Plugins → Install… → point at your
   directory. The bundle is copied into `<appdata>/plugins/<name>/`
   and warm-loaded.
6. **Iterate** — edit files in your source tree, then re-install (the
   installer replaces the previous version atomically).

## Distribution

- **Local install (zip)** — `zip -r my_plugin.zip my_plugin/`; share
  the zip. Users install via the Plugins page.
- **Catalog** — the canonical catalog at `https://plugins.ecan.ai/`
  is reserved for future. The frontend hides the Catalog tab while
  the URL is unset; nothing on the user's side changes.
- **Signing** — HMAC signatures via `hook_signing.py` remain
  supported for vendor-internal distribution where the secret can be
  shared. Public-catalog signing (ed25519) is deferred.

## Decision verbs cheat-sheet

(from HOOK_BUNDLES.md)

| Return                          | Effect                                                       |
|---------------------------------|--------------------------------------------------------------|
| `HookResult.cont()`             | Proceed normally.                                            |
| `HookResult.replace(p)`         | Rewrite the payload for the next hook / stage.               |
| `HookResult.bypass(actions)`    | Emit deterministic actions; skip the LLM.                    |
| `HookResult.drop()`             | Swallow the event entirely.                                  |
| `HookResult.handoff(agent)`     | Hand off to a named sub-agent.                               |
| `HookResult.escalate()`         | Force LLM even when a prior hook said Bypass.                |

## Troubleshooting

| Symptom                                          | Likely cause                                           |
|--------------------------------------------------|--------------------------------------------------------|
| Plugin not in Plugins list after install        | Manifest validation failed — check the install dialog's error. |
| Iframe shows "This plugin does not declare …"   | `gui` block missing or `slots.config_panel` absent.    |
| Bridge call rejects with `DENIED`               | Method not in `gui.permissions.bridge_methods`.        |
| `tools.invoke` returns `NOT_IMPLEMENTED`        | Backend tool gate is Phase 4; expected for now.        |
| `config.set` rejects with `VALIDATION_FAILED`   | Value doesn't match `config_schema`.                   |
| `storage.set` rejects with `STORAGE_LIMIT`      | Your KV exceeds 1 MB; trim.                            |
| Iframe never resizes despite `ui.resize`        | Value out of `[80, 1800]` clamp; check the resolved value the bridge returns. |
| Uninstall blocked by "in use"                   | At least one skill node references the bundle — confirm Force Uninstall, or remove from those nodes. |

## File map

| Path                                                                                | Purpose                              |
|-------------------------------------------------------------------------------------|--------------------------------------|
| `agent/ec_skills/browser_use_extension/plugin_registry.py`                          | Per-user registry + manifest summary |
| `agent/ec_skills/browser_use_extension/plugin_installer.py`                         | Install / uninstall flows            |
| `agent/ec_skills/browser_use_extension/plugin_dependents.py`                        | Skill-tree scanner for refs          |
| `agent/ec_skills/browser_use_extension/plugin_autoload.py`                          | Warm-load on app boot                |
| `agent/ec_skills/browser_use_extension/plugin_config.py`                            | Global config persistence            |
| `agent/ec_skills/browser_use_extension/plugin_storage.py`                           | Per-bundle KV store                  |
| `agent/ec_skills/browser_use_extension/plugin_gui_server.py`                        | Localhost HTTP for iframe assets     |
| `agent/ec_skills/browser_use_extension/catalog_client.py`                           | Catalog index fetcher (stub)         |
| `agent/ec_skills/browser_use_extension/plugin_scaffold.py`                          | Scaffolding CLI                      |
| `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/`                  | Reference bundle (Python + GUI)      |
| `gui_v2/src/modules/plugin-bridge/`                                                 | Frontend bridge host + iframe        |
| `gui_v2/src/pages/Plugins/`                                                         | Plugins page UI                      |
| `gui/ipc/w2p_handlers/plugin_handler.py`                                            | IPC handlers (plugin.*)              |
