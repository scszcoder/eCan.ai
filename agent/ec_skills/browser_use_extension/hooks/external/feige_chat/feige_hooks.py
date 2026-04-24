"""
Feige chat — reference external hook implementations.

Two hooks ship in this bundle:

    FeigeQuickReplyHook        (on_event_normalized, Bypass)
    FeigeCrosstalkGuardHook    (on_pre_action, Drop)

Both are **external** hooks — the loader instantiates them from hook.yaml
rather than an in-tree import.  Authoring a new external hook for a
different site is a copy-and-edit exercise on this file.

Key authoring patterns illustrated here:

  * A bundle-supplied ``config`` dict arrives via ``__init__(config=...)``.
    Hooks should be defensive: only read keys they expect, ignore unknown
    keys, and provide sensible fallbacks.
  * Every ``run()`` returns a ``HookResult``.  The 6 decision verbs are:
        cont()     → let downstream hooks + LLM proceed
        replace()  → rewrite the payload for the next stage
        bypass()   → emit deterministic actions, skip the LLM
        drop()     → swallow the event entirely
        handoff()  → transfer to a named sub-agent
        escalate() → promote to LLM even if prior hook said Bypass
  * Hooks NEVER mutate ``ctx.config``, ``ctx.site_adapter``, or ``ctx.manifest``.
    They ARE allowed to read/write ``ctx.state``.
  * Logging goes through ``ctx.logger`` when available so span correlation
    works; a plain ``logging.getLogger`` call is an acceptable fallback.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.ec_skills.browser_use_extension.hook_api import (
    BypassAction,
    HookContext,
    HookResult,
    Stage,
)

# Re-use the in-tree Tier-0 verify logic — we don't need to reimplement
# the DOM round-trip when we just want to add a new arg-key list.
from agent.ec_skills.browser_use_extension.hooks.builtin.verify_active_session import (
    VerifyActiveSessionHook,
)

logger = logging.getLogger("ecan.hooks.feige_chat")


# =============================================================================
# Hook 1 — deterministic LLM bypass for known customer prompts.
# =============================================================================
class FeigeQuickReplyHook:
    """Emit a canned reply (via Decision.BYPASS) when the incoming event
    text matches a key in the bundle's ``quick_replies`` config table.

    Design notes
    ------------
    * Keyed exact-match on message text.  Real deployments typically want
      a richer matcher (regex, embedding similarity, etc.) — add it here.
    * Per-customer cooldown guards against repeat-send races during storms
      of duplicated DOM events.
    * State is stored via the shared ``state_namespace: feige_quickreply``
      declared in hook.yaml so any future Feige sibling hook can observe
      the same cooldown map.
    """

    # ``manifest`` is attached by the loader post-init; kept as a class
    # attribute hint so static analysers see it.
    manifest: Any = None

    def __init__(self, config: dict | None = None, manifest: Any = None):
        self.config = dict(config or {})
        self.manifest = manifest
        self._replies: dict[str, str] = dict(self.config.get("quick_replies") or {})
        self._cooldown_ms: int = int(self.config.get("cooldown_ms", 1500) or 0)
        self._send_action: str = str(
            self.config.get("send_action") or "feige_send_message"
        )
        logger.info(
            f"[feige_quick_reply] loaded {len(self._replies)} quick-reply patterns "
            f"(cooldown={self._cooldown_ms}ms, send_action={self._send_action!r})"
        )

    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="feige_qr:payload_not_dict")

        # Event shape is loose — the event-monitor pipeline normalises
        # ``chat_message`` / ``customer_message`` dicts.  We read
        # defensively and skip on any structural surprise.
        text = str(payload.get("text") or payload.get("message") or "").strip()
        customer = (
            str(payload.get("customer_name") or payload.get("customer_id") or "").strip()
        )
        if not text or not customer:
            return HookResult.cont(reason="feige_qr:missing_text_or_customer")

        reply = self._replies.get(text)
        if not reply:
            return HookResult.cont(reason=f"feige_qr:no_match:{text!r}")

        # Cooldown check — ctx.state is a small KV store; we key by
        # customer so two different customers can trigger back-to-back.
        now_ms = time.monotonic() * 1000.0
        last_ms = float(ctx.state.get(f"last:{customer}", 0.0))
        if now_ms - last_ms < self._cooldown_ms:
            return HookResult.cont(
                reason=f"feige_qr:cooldown:{customer}:{int(now_ms - last_ms)}ms"
            )
        ctx.state.set(f"last:{customer}", now_ms)

        # Emit the deterministic action.  The dispatcher will route it
        # through multi_act, and the ScopedToolProxy will enforce that
        # ``feige_send_message`` is in our manifest's permissions.tools.
        actions = [
            BypassAction(
                name=self._send_action,
                args={"customer_name": customer, "text": reply},
            )
        ]
        logger.info(
            f"[feige_quick_reply] BYPASS customer={customer!r} trigger={text!r} "
            f"→ {self._send_action}"
        )
        return HookResult.bypass(actions, reason="feige_qr:matched")


# =============================================================================
# Hook 2 — Feige-specific crosstalk guard.
# =============================================================================
class FeigeCrosstalkGuardHook(VerifyActiveSessionHook):
    """Same semantics as the Tier-0 VerifyActiveSessionHook but tailored:

    * ``guarded_actions`` defaults include ``feige_send_draft`` in addition
      to ``feige_send_message``, matching Feige's two write-path tools.
    * ``expected_customer_keys`` add Feige-internal aliases (``recipient``,
      ``chat_target``) that some node-editor authors use in their
      hotPathActions args.

    The built-in Tier-0 guard already provides a safety net; this wrapper
    simply widens the net for a specific site.  Running both (Tier-0 at
    priority 5, this one at priority 6) is cheap because the second call
    short-circuits on the same ``action_name`` matcher.
    """

    # New name so the dispatcher doesn't reject us as a duplicate of the
    # Tier-0 hook.
    NAME = "feige_crosstalk_guard_ext"
    VERSION = "1.0.0"
    PRIORITY = 6

    # These override the Tier-0 defaults.
    DEFAULT_GUARDED_ACTIONS = ("feige_send_message", "feige_send_draft")
    DEFAULT_EXPECTED_CUSTOMER_KEYS = (
        "customer_name",
        "expected_customer",
        "customer_id",
        # Feige-flavoured aliases:
        "recipient",
        "chat_target",
    )

    def __init__(self, config: dict | None = None, manifest: Any = None):
        # Honor any overrides from the bundle/user config.
        cfg = dict(config or {})
        guarded = cfg.get("guarded_actions") or list(self.DEFAULT_GUARDED_ACTIONS)
        expected_keys = (
            cfg.get("expected_customer_keys")
            or list(self.DEFAULT_EXPECTED_CUSTOMER_KEYS)
        )
        # Call the Tier-0 constructor which builds a manifest for the
        # built-in name.  We then overwrite the manifest with the one the
        # loader built from hook.yaml (the loader attaches it post-init).
        super().__init__(
            guarded_actions=list(guarded),
            expected_customer_keys=list(expected_keys),
        )
        self.config = cfg
        if manifest is not None:
            self.manifest = manifest
