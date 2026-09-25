"""Pinduoduo manifest hooks.

``PddQuickReplyHook``: an exact-match canned reply, sent through
``pdd_send_message`` without asking the LLM. The default table is EMPTY -- a
store opts in by listing replies in the node's hookBundles config -- so out of
the box this hook only lets events through.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from agent.ec_skills.browser_use_extension.hook_api import BypassAction, HookContext, HookResult

logger = logging.getLogger(__name__)


class PddQuickReplyHook:
    manifest: Any = None

    def __init__(self, config: dict | None = None, manifest: Any = None):
        self.config = dict(config or {})
        self.manifest = manifest
        self._replies = {str(k).strip(): str(v) for k, v in (self.config.get("quick_replies") or {}).items()
                         if str(k).strip() and str(v).strip()}
        self._cooldown_ms = int(self.config.get("cooldown_ms", 1500) or 0)
        self._send_action = str(self.config.get("send_action") or "pdd_send_message")

    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        if not self._replies or not isinstance(payload, dict):
            return HookResult.cont(reason="pdd_qr:off")
        text = str(payload.get("text") or payload.get("message") or payload.get("latest_message") or "").strip()
        customer = str(payload.get("customer_name") or payload.get("customer_id") or "").strip()
        reply = self._replies.get(text)
        if not reply or not customer:
            return HookResult.cont(reason="pdd_qr:no_match")
        now_ms = time.monotonic() * 1000.0
        if now_ms - float(ctx.state.get(f"last:{customer}", 0.0)) < self._cooldown_ms:
            return HookResult.cont(reason="pdd_qr:cooldown")
        ctx.state.set(f"last:{customer}", now_ms)
        logger.info(f"[pdd_quick_reply] BYPASS customer={customer!r} trigger={text!r}")
        return HookResult.bypass([BypassAction(name=self._send_action,
                                               args={"customer_name": customer, "text": reply})],
                                 reason="pdd_qr:matched")
