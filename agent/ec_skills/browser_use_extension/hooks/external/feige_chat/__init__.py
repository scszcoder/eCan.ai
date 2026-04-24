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
