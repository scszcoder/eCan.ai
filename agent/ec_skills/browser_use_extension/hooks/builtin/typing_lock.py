"""
TypingLockHook — cross-customer exclusive-typing guard.

Prevents the classic live-chat race: when HOT-PATH-B is mid-way through
typing a reply into customer A's chat, a parallel PreDispatch scrape on
another scope can click customer B's sidebar row — which switches the
site's global active-chat state and causes our in-flight reply to land in
customer B's window.  (Observed 2026-04-22 16:48 with customer A's answer
typed into customer C's chat.)

This hook implements an in-memory single-holder lock, scoped to the
HookedAgent via ``ctx.state``:

  * ``on_pre_action`` (for guarded actions):
      - If nobody holds the lock OR the holder equals the action's
        customer → acquire/extend, Continue.
      - If a *different* customer holds the lock AND the TTL has not
        expired → Drop.  The action is skipped for this cycle; a future
        cycle will retry once the holder releases.
      - If the holder's TTL has expired → treat as released, acquire,
        Continue.  (Defence against a crashed responder holding the lock
        forever.)
  * ``on_post_action`` (same guarded actions):
      - Release the lock when we're the holder.

The lock state lives in ``ctx.state`` (a ``MemoryStateStore`` by default),
so each HookedAgent instance has its own lock.  Multi-process scenarios
need a different backend (disk, Redis); that's a future PR.

The original ``build_node.py`` maintained this as a module-level dict
(the typing-holder registry) because it needed to be shared across
PrivacyAgent instances in the same process that all drove the same chat
tab.  Migrating to ``ctx.state`` is correct when there's exactly one
HookedAgent per browser session; multi-agent/single-browser topologies
will need the cross-agent shared-state backend added later.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from ...hook_api import HookContext, HookResult, Stage
from .base import BuiltinHook


# ---------------------------------------------------------------------------
# Customer-id normaliser — reused from build_node.py's convention.  Stripped
# here so this module doesn't import from build_node.
# ---------------------------------------------------------------------------
def _normalize_customer_id(raw: Any) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    if "|" in s:
        prefix = s.split("|", 1)[0].strip()
        if prefix:
            return prefix
    return s


def _extract_customer(args: dict, lookup_keys: Iterable[str]) -> str:
    if not isinstance(args, dict):
        return ""
    for k in lookup_keys:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return _normalize_customer_id(v)
    return ""


def _bundle_default_guarded_actions() -> tuple[str, ...]:
    """Default guarded tool names (open-session + send) from the active
    live-chat bundle's runner bridge; empty tuple when no bundle is loaded
    (no site tools exist to guard in that case)."""
    try:
        from agent.ec_skills import live_chat_dispatch
        bridge = live_chat_dispatch.runner_bridge()
        names = (
            str(bridge.open_session_tool_name or ""),
            str(bridge.send_message_tool_name or ""),
        )
        return tuple(n for n in names if n)
    except Exception:
        return ()


def _bundle_send_tool_name() -> str:
    """The bundle's send-tool name ("" when no bundle is loaded)."""
    try:
        from agent.ec_skills import live_chat_dispatch
        return str(
            live_chat_dispatch.runner_bridge().send_message_tool_name or ""
        )
    except Exception:
        return ""


def _action_args(payload: dict, action_name: str) -> dict:
    """Pull the args dict out of an on_pre_action / on_post_action payload."""
    action_obj = payload.get("action")
    if action_obj is None:
        return {}
    if hasattr(action_obj, "model_dump"):
        try:
            dumped = action_obj.model_dump(exclude_unset=True) or {}
            if isinstance(dumped, dict):
                v = dumped.get(action_name)
                if isinstance(v, dict):
                    return v
        except Exception:
            return {}
    if isinstance(action_obj, dict):
        v = action_obj.get(action_name)
        if isinstance(v, dict):
            return v
        return action_obj
    return {}


# ---------------------------------------------------------------------------
# TypingLockHook — registered at TWO stages via two instances.  The base
# class carries shared logic; subclasses pick the stage.
# ---------------------------------------------------------------------------
class _TypingLockBase(BuiltinHook):
    # Default guarded actions come from the active live-chat bundle's
    # runner bridge (its open-session + send tool names) — see
    # ``_bundle_default_guarded_actions``.
    DEFAULT_CUSTOMER_KEYS: tuple[str, ...] = (
        "customer_name",
        "customer_id",
    )
    DEFAULT_TTL_S: float = 30.0

    # The lock is stored under this key in ctx.state.
    _STATE_KEY = "holder"

    # Shared namespace — both TypingLockAcquireHook and TypingLockReleaseHook
    # use "typing_lock" so the dispatcher gives them the SAME StateStore
    # (see HookedAgent._get_or_create_state_store).  Without this, acquire
    # writes to its own store and release reads an empty one.
    STATE_NAMESPACE: str = "typing_lock"

    def __init__(
        self,
        *,
        guarded_actions: Optional[list[str]] = None,
        customer_keys: Optional[list[str]] = None,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> None:
        self._guarded = tuple(guarded_actions or _bundle_default_guarded_actions())
        self._customer_keys = list(customer_keys or self.DEFAULT_CUSTOMER_KEYS)
        self._ttl_s = float(ttl_s)
        # The canonical "last step" that releases the lock — the bundle's
        # send tool (resolved once here; see TypingLockReleaseHook.run).
        self._terminal_action = _bundle_send_tool_name()
        self.manifest = self._make_manifest(
            matches={"action_name": list(self._guarded)},
            permissions={"tools": []},
            budget={"timeout_ms": 50, "rate_per_minute": 6000},
        )
        # Apply shared state namespace post-construction (the base
        # _make_manifest doesn't expose state_namespace as a kwarg).
        self.manifest = self.manifest.model_copy(
            update={"state_namespace": self.STATE_NAMESPACE},
        )
        super().__init__()

    # --------------------------------------------------------------- helpers
    @classmethod
    def _read_holder(cls, state) -> tuple[str, float]:
        """Return (holder, ts) from the state store; empty tuple when absent."""
        v = state.get(cls._STATE_KEY)
        if isinstance(v, dict):
            return (str(v.get("holder") or ""), float(v.get("ts") or 0.0))
        return ("", 0.0)

    @classmethod
    def _write_holder(cls, state, holder: str, ts: float) -> None:
        state.set(cls._STATE_KEY, {"holder": holder, "ts": float(ts)})

    @classmethod
    def _clear_holder(cls, state) -> None:
        state.delete(cls._STATE_KEY)


class TypingLockAcquireHook(_TypingLockBase):
    """Pre-action half of the typing lock."""

    NAME = "typing_lock_acquire"
    STAGE = Stage.ON_PRE_ACTION
    PRIORITY = 20  # after verify_active_session (priority=5)

    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="lock:payload_not_dict")
        action_name = str(payload.get("action_name") or "")
        if action_name not in self._guarded:
            return HookResult.cont(reason="lock:action_not_guarded")

        args = _action_args(payload, action_name)
        cust = _extract_customer(args, self._customer_keys)
        if not cust:
            return HookResult.cont(reason="lock:no_customer_in_args")

        holder, ts = self._read_holder(ctx.state)
        now = time.monotonic()

        if holder and holder != cust:
            # Different customer holds the lock.  Honour TTL.
            if (now - ts) < self._ttl_s:
                self._logger.warning(
                    f"[hook:{self.manifest.name}] BLOCK {cust!r} — "
                    f"lock held by {holder!r} for {now - ts:.1f}s "
                    f"(ttl={self._ttl_s}s)"
                )
                return HookResult.drop(reason=f"lock:held_by:{holder}")
            # Expired: reclaim.
            self._logger.warning(
                f"[hook:{self.manifest.name}] expired holder={holder!r} "
                f"({now - ts:.1f}s > ttl={self._ttl_s}s); reclaiming for {cust!r}"
            )

        # Acquire / extend.
        self._write_holder(ctx.state, cust, now)
        self._logger.info(
            f"[hook:{self.manifest.name}] acquired lock for {cust!r} "
            f"(action={action_name})"
        )
        return HookResult.cont(reason=f"lock:acquired:{cust}")


class TypingLockReleaseHook(_TypingLockBase):
    """Post-action half of the typing lock.

    Only releases when WE are the current holder — a separate customer's
    reclaim of an expired lock shouldn't be undone by our post-action.
    """

    NAME = "typing_lock_release"
    STAGE = Stage.ON_POST_ACTION
    PRIORITY = 90  # after most post-action hooks so the lock outlives them

    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="lock:payload_not_dict")
        action_name = str(payload.get("action_name") or "")
        if action_name not in self._guarded:
            return HookResult.cont(reason="lock:action_not_guarded")

        args = _action_args(payload, action_name)
        cust = _extract_customer(args, self._customer_keys)
        if not cust:
            return HookResult.cont(reason="lock:no_customer_in_args")

        # Only release the final guarded action in the sequence.  We use
        # the bundle's send tool as the canonical "last step"; earlier
        # steps (the open-session tool) should NOT release.
        #
        # If the caller wants a different release trigger they can pass
        # ``guarded_actions=[<send tool>]`` to this class only.
        if action_name != self._terminal_action:
            return HookResult.cont(reason=f"lock:non_terminal_action:{action_name}")

        holder, ts = self._read_holder(ctx.state)
        if not holder:
            return HookResult.cont(reason="lock:already_released")
        if holder != cust:
            self._logger.warning(
                f"[hook:{self.manifest.name}] not releasing — holder={holder!r} "
                f"but this cycle is for {cust!r} (post-action mismatch)"
            )
            return HookResult.cont(reason=f"lock:holder_mismatch:{holder}")

        self._clear_holder(ctx.state)
        self._logger.info(
            f"[hook:{self.manifest.name}] released lock for {cust!r}"
        )
        return HookResult.cont(reason=f"lock:released:{cust}")


__all__ = [
    "TypingLockAcquireHook",
    "TypingLockReleaseHook",
    # exposed for tests
    "_normalize_customer_id",
    "_extract_customer",
    "_action_args",
]
