"""Feige chat external hook bundle.

See ``hook.yaml`` for the runtime manifest, ``feige_hooks.py`` for the
hook implementations, and ``dom_assets.py`` for the DOM selectors / JS
snippets / verification helpers relocated out of ``build_node.py``.

Phase 5A (2026-04-24): ``front_desk.py`` now owns the PreDispatch
fast-path wrapper and registers itself with ``build_node`` as a
before-browser-use-run hook on package import.
"""

# Register the front-desk PreDispatch hook with build_node.  Guarded
# so re-importing this package (which can happen under some test / hot
# reload paths) doesn't double-register the hook.
_FD_HOOK_REGISTERED = globals().get("_FD_HOOK_REGISTERED", False)
if not _FD_HOOK_REGISTERED:
    from . import front_desk as _front_desk
    _front_desk.register()
    _FD_HOOK_REGISTERED = True

# Register the actionable-items prompt-build hook (Phase 7, 2026-04-24).
# Owns the front-desk pattern's filter + protocol-override + agent_list
# injection + auto-dispatch short-circuit, previously inline in
# ``build_node._run_browser_use``.
_AI_HOOK_REGISTERED = globals().get("_AI_HOOK_REGISTERED", False)
if not _AI_HOOK_REGISTERED:
    from . import actionable_items as _actionable_items
    _actionable_items.register()
    _AI_HOOK_REGISTERED = True

# Register the live-chat placeholder handler (mt051C, 2026-05-28).
# Owns the direct-delivery placeholder typing coroutine that runner.py
# used to inline as ``_enqueue_direct_placeholder``'s closure.  Runner
# now fires ``Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED`` via
# ``live_chat_dispatch``; this registration plugs Feige in.
_DD_HOOK_REGISTERED = globals().get("_DD_HOOK_REGISTERED", False)
if not _DD_HOOK_REGISTERED:
    from . import direct_delivery as _direct_delivery
    _direct_delivery.register()
    _DD_HOOK_REGISTERED = True

# Register the in-process A2A local-delivery hot-path (ws062).  Keeps the
# direct-to-runner-queue optimization in the Feige layer; the A2A core
# (ec_agent) only exposes a neutral register_a2a_local_delivery_hook point.
# Gated by ECAN_A2A_LOCAL_FASTPATH=1 inside the hook (default OFF).
_A2A_LOCAL_HOOK_REGISTERED = globals().get("_A2A_LOCAL_HOOK_REGISTERED", False)
if not _A2A_LOCAL_HOOK_REGISTERED:
    from . import a2a_local_delivery as _a2a_local_delivery
    _a2a_local_delivery.register()
    _A2A_LOCAL_HOOK_REGISTERED = True
