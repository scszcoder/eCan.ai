"""
Convenience base class for built-in (Tier-0) hooks.

Hooks do not *have* to subclass this — the ``Hook`` Protocol only requires a
``manifest`` attribute and an ``async run()`` method — but built-ins benefit
from:

  * a default ``tier=0`` manifest builder,
  * a ``disabled=False`` runtime toggle third-party code cannot flip,
  * a ``_log`` helper that prefixes the hook name so log lines are
    greppable ("[hook:feige_verify_active_session] ..."),
  * a stable import path for any user who wants to read the base class.

Concrete built-ins (``BypassActionsHook``, ``VerifyActiveSessionHook``, ...)
are defined in sibling modules and registered by ``PrivacyAgent`` when the
node's config turns them on.
"""

from __future__ import annotations

import logging
from typing import Any

from ...hook_api import (
    HOOK_API_VERSION,
    Hook,
    HookManifest,
    Stage,
)


class BuiltinHook:
    """Minimal base class for Tier-0 hooks.

    Subclasses must:
      * populate ``self.manifest`` (usually via ``_make_manifest``) in
        ``__init__``;
      * implement ``async def run(self, ctx, payload) -> HookResult``.
    """

    # Subclasses override these class attributes; constructors may also
    # override via manifest kwargs.
    NAME: str = ""
    STAGE: Stage = Stage.ON_EVENT_NORMALIZED
    VERSION: str = "1.0.0"
    PRIORITY: int = 100

    def __init__(self) -> None:
        # Subclass __init__ should build self.manifest.  The Protocol check
        # in HookDispatcher.register will fail if a subclass forgets.
        if not hasattr(self, "manifest"):
            raise RuntimeError(
                f"BuiltinHook subclass {type(self).__name__} did not set self.manifest"
            )
        self._logger = logging.getLogger(
            f"hook.{self.manifest.name}"  # one logger per hook name
        )

    # ------------------------------------------------------------ helpers
    @classmethod
    def _make_manifest(
        cls,
        *,
        name: str | None = None,
        stage: Stage | None = None,
        priority: int | None = None,
        matches: dict[str, Any] | None = None,
        permissions: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        entrypoint: str | None = None,
    ) -> HookManifest:
        """Build a Tier-0 manifest with sensible defaults.

        Kept as a classmethod so subclasses can override a few fields via
        kwargs without rebuilding the entire manifest by hand.
        """
        return HookManifest(
            hook_api_version=HOOK_API_VERSION,
            name=name or cls.NAME,
            version=cls.VERSION,
            author="ecan.ai",
            runtime="python",
            stage=stage or cls.STAGE,
            priority=priority if priority is not None else cls.PRIORITY,
            tier=0,
            matches=matches or {},
            permissions=permissions or {},  # default: no tool access
            budget=budget or {"timeout_ms": 500, "rate_per_minute": 600},
            entrypoint=entrypoint or f"builtin:{cls.__name__}",
        )

    def _log(self, level: int, msg: str, *args: Any) -> None:
        self._logger.log(level, msg, *args)


__all__ = ["BuiltinHook"]
