"""Tier-aware port of FeigeQuickReplyHook (Step 2b, 2026-04-25).

This is the **first port** of an existing hook to the new
``LocalReactiveContext`` shape introduced in Step 2a.  Goal: validate
that the new context carries everything the original needed, with no
loss of expressiveness.

Differences from :class:`FeigeQuickReplyHook` in ``feige_hooks.py``:

* Takes :class:`LocalReactiveContext` instead of the legacy
  ``HookContext`` (``hook_api.py``).  The KV access pattern
  (``ctx.state.get/set``) is identical because both back ends satisfy
  the :class:`SessionKV` Protocol.
* No ``manifest`` attribute (manifest lives separately in the v2
  registry, not on the hook instance).
* Returns a generic ``HookResult`` import — that decision-output type
  is tier-agnostic and shared with the v1 loader.

The v1 :class:`FeigeQuickReplyHook` remains in place; it's still
loaded by the existing HookDispatcher integration.  This v2 file is
exercised only by ``tests/test_quick_reply_v2.py`` and does not yet
participate in the live runtime — that wiring lands in Step 4.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.ec_skills.browser_node.contexts import LocalReactiveContext

# Decision output types are tier-agnostic — reuse the existing ones.
from agent.ec_skills.browser_use_extension.hook_api import (
    BypassAction,
    HookResult,
)

logger = logging.getLogger("ecan.hooks.feige_chat.v2")


class FeigeQuickReplyHookV2:
    """Tier ``local_reactive`` port of FeigeQuickReplyHook.

    Identical decision logic; runs against :class:`LocalReactiveContext`
    instead of the legacy ``HookContext``.  Used by Step 2b's validation
    test to prove the new context shape is sufficient.
    """

    # Declared tier — read by the future tier-aware loader (Step 5).
    EXECUTION_TIER = "local_reactive"

    def __init__(self, config: dict | None = None):
        cfg = dict(config or {})
        self._replies: dict[str, str] = dict(cfg.get("quick_replies") or {})
        self._cooldown_ms: int = int(cfg.get("cooldown_ms", 1500) or 0)
        self._send_action: str = str(
            cfg.get("send_action") or "feige_send_message"
        )
        logger.info(
            f"[feige_quick_reply_v2] loaded {len(self._replies)} patterns "
            f"(cooldown={self._cooldown_ms}ms, send_action={self._send_action!r})"
        )

    async def run(
        self,
        ctx: LocalReactiveContext,
        payload: Any,
    ) -> HookResult:
        if not isinstance(payload, dict):
            return HookResult.cont(reason="feige_qr_v2:payload_not_dict")

        text = str(payload.get("text") or payload.get("message") or "").strip()
        customer = str(
            payload.get("customer_name") or payload.get("customer_id") or ""
        ).strip()
        if not text or not customer:
            return HookResult.cont(reason="feige_qr_v2:missing_text_or_customer")

        reply = self._replies.get(text)
        if not reply:
            return HookResult.cont(reason=f"feige_qr_v2:no_match:{text!r}")

        # Cooldown KV — exactly the same shape as v1 because SessionKV
        # mirrors HookContext.state.
        now_ms = time.monotonic() * 1000.0
        last_ms = float(ctx.state.get(f"last:{customer}", 0.0))
        if now_ms - last_ms < self._cooldown_ms:
            return HookResult.cont(
                reason=f"feige_qr_v2:cooldown:{customer}:{int(now_ms - last_ms)}ms"
            )
        ctx.state.set(f"last:{customer}", now_ms)

        actions = [
            BypassAction(
                name=self._send_action,
                args={"customer_name": customer, "text": reply},
            )
        ]
        logger.info(
            f"[feige_quick_reply_v2] BYPASS customer={customer!r} "
            f"trigger={text!r} → {self._send_action}"
        )
        return HookResult.bypass(actions, reason="feige_qr_v2:matched")
