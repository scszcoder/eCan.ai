"""
Runtime lanes for non-Python hooks.

A "lane" is a shim that lets the dispatcher treat a JS blob or a
subprocess as if it were an ordinary Python ``Hook``.  Each lane module
exposes a ``<Lane>Hook`` class the loader instantiates when it sees the
matching ``manifest.runtime`` value:

    manifest.runtime == "python"       → no lane (direct import)
    manifest.runtime == "js_injected"  → JsInjectedLaneHook
    manifest.runtime == "subprocess"   → SubprocessLaneHook

Lanes are NEVER part of the Tier-0 trust surface.  They exist to make
third-party hooks safer and more language-agnostic.
"""

from .js_lane import JsInjectedLaneHook
from .subprocess_lane import SubprocessLaneHook

__all__ = ["JsInjectedLaneHook", "SubprocessLaneHook"]
