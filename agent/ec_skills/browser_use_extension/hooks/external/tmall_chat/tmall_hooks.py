"""Tmall/Qianniu chat — manifest-driven external hook implementations.

Ported from ``feige_chat/feige_hooks.py`` (the reference bundle):

    TmallQuickReplyHook        (on_event_normalized, Bypass)
    TmallCrosstalkGuardHook    (on_pre_action, Drop)

Both are instantiated by the hook loader from this bundle's ``hook.yaml``
when a browser_automation node enables the bundle via its
"Hook Bundles (JSON)" field.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.ec_skills.browser_use_extension.hook_api import (
    BypassAction,
    HookContext,
    HookResult,
)

from agent.ec_skills.browser_use_extension.hooks.builtin.verify_active_session import (
    VerifyActiveSessionHook,
)

logger = logging.getLogger("ecan.hooks.tmall_chat")


# =============================================================================
# Hook 1 — deterministic LLM bypass for known buyer prompts.
# =============================================================================
class TmallQuickReplyHook:
    """Emit a canned reply (via Decision.BYPASS) when the incoming event
    text matches a key in the bundle's ``quick_replies`` config table.
    Keyed exact-match; per-customer cooldown guards against repeat-send
    races during storms of duplicated DOM events."""

    manifest: Any = None

    def __init__(self, config: dict | None = None, manifest: Any = None):
        self.config = dict(config or {})
        self.manifest = manifest
        self._replies: dict[str, str] = dict(self.config.get("quick_replies") or {})
        self._cooldown_ms: int = int(self.config.get("cooldown_ms", 1500) or 0)
        self._send_action: str = str(
            self.config.get("send_action") or "tmall_send_message"
        )
        logger.info(
            f"[tmall_quick_reply] loaded {len(self._replies)} quick-reply patterns "
            f"(cooldown={self._cooldown_ms}ms, send_action={self._send_action!r})"
        )

    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="tmall_qr:payload_not_dict")

        text = str(payload.get("text") or payload.get("message") or "").strip()
        customer = (
            str(payload.get("customer_name") or payload.get("customer_id") or "").strip()
        )
        if not text or not customer:
            return HookResult.cont(reason="tmall_qr:missing_text_or_customer")

        reply = self._replies.get(text)
        if not reply:
            return HookResult.cont(reason=f"tmall_qr:no_match:{text!r}")

        now_ms = time.monotonic() * 1000.0
        last_ms = float(ctx.state.get(f"last:{customer}", 0.0))
        if now_ms - last_ms < self._cooldown_ms:
            return HookResult.cont(
                reason=f"tmall_qr:cooldown:{customer}:{int(now_ms - last_ms)}ms"
            )
        ctx.state.set(f"last:{customer}", now_ms)

        actions = [
            BypassAction(
                name=self._send_action,
                args={"customer_name": customer, "text": reply},
            )
        ]
        logger.info(
            f"[tmall_quick_reply] BYPASS customer={customer!r} trigger={text!r} "
            f"→ {self._send_action}"
        )
        return HookResult.bypass(actions, reason="tmall_qr:matched")


# =============================================================================
# Hook 2 — Tmall-specific crosstalk guard.
# =============================================================================
class TmallCrosstalkGuardHook(VerifyActiveSessionHook):
    """Tier-1 widening of the Tier-0 VerifyActiveSessionHook for the
    Tmall write-path tool and its arg-key aliases."""

    NAME = "tmall_crosstalk_guard_ext"
    VERSION = "1.0.0"
    PRIORITY = 6

    DEFAULT_GUARDED_ACTIONS = ("tmall_send_message",)
    DEFAULT_EXPECTED_CUSTOMER_KEYS = (
        "customer_name",
        "expected_customer",
        "customer_id",
        "recipient",
        "chat_target",
    )

    def __init__(self, config: dict | None = None, manifest: Any = None):
        cfg = dict(config or {})
        guarded = cfg.get("guarded_actions") or list(self.DEFAULT_GUARDED_ACTIONS)
        expected_keys = (
            cfg.get("expected_customer_keys")
            or list(self.DEFAULT_EXPECTED_CUSTOMER_KEYS)
        )
        super().__init__(
            guarded_actions=list(guarded),
            expected_customer_keys=list(expected_keys),
        )
        self.config = cfg
        if manifest is not None:
            self.manifest = manifest
