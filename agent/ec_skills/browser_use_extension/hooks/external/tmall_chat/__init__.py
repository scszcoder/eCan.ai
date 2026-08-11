"""Tmall / Qianniu (千牛) chat external hook bundle.

Phase 1 scaffold (2026-08-11) — see ``docs/TMALL_QIANNIU_CHAT_DESIGN.md``
and this bundle's ``README.md``.  Mirrors the ``feige_chat`` bundle shape:
the platform reaches everything here through the neutral extension points
(``live_chat_dispatch.runner_bridge()``, controller-action decorators),
never by importing this package directly.

Active-site gate (design decision D1): ``register_runner_bridge`` /
controller tool registration are last-write-wins, one per process — so a
site bundle registers ONLY when it is the active live-chat site:

    ECAN_LIVE_CHAT_SITE=tmall_chat   → this bundle registers
    ECAN_LIVE_CHAT_SITE unset/other  → this bundle imports but stays inert

The default active site is ``feige_chat`` (existing behavior unchanged).
"""

import os as _site_os

_ACTIVE_SITE = (_site_os.environ.get("ECAN_LIVE_CHAT_SITE") or "feige_chat").strip()
_SITE_ACTIVE = _ACTIVE_SITE == "tmall_chat"

# Register the runner bridge.  Guarded so re-importing this package (test /
# hot-reload paths) doesn't double-register.
_RUNNER_BRIDGE_REGISTERED = globals().get("_RUNNER_BRIDGE_REGISTERED", False)
if _SITE_ACTIVE and not _RUNNER_BRIDGE_REGISTERED:
    from . import runner_bridge as _runner_bridge
    _runner_bridge.register()
    _RUNNER_BRIDGE_REGISTERED = True

# Register the Tmall site tools (tmall_list_sessions / tmall_open_session /
# tmall_get_chat_thread / tmall_send_message).  Importing the module
# registers the actions on the shared custom_controller via decorators.
_SITE_TOOLS_REGISTERED = globals().get("_SITE_TOOLS_REGISTERED", False)
if _SITE_ACTIVE and not _SITE_TOOLS_REGISTERED:
    from . import site_tools as _site_tools  # noqa: F401
    _SITE_TOOLS_REGISTERED = True
