"""Tier-aware port of pre_dispatch_enrich (Step 2f, local half).

This is the **local_extract** half of PreDispatch.  Pure DOM-to-dict
function: focus the customer's chat pane, scrape the most recent
customer bubble, return a serializable ``ScrapeResult``.

What this owns
--------------

* The Feige-specific JS for finding the latest customer bubble
  (``FEIGE_LATEST_CUSTOMER_BUBBLE_JS`` from ``dom_assets``)
* Wrapping the eval result in a typed dataclass

What this does NOT own
----------------------

* msg-id dedup            — cloud-side decision (PreDispatchHookV2)
* dom-echo guard          — cloud-side decision (PreDispatchHookV2)
* assigned_sessions clear — cloud-side decision (PreDispatchHookV2)
* item mutation           — cloud picks how to integrate scrape output

This separation is exactly the user's described split:

    "1) local side, the hot path analyze dom and gather all the info,
     and then send these raw info to the cloud side; 2) the front-desk
     agent's cloud side skill's hot path part finish off dispatching"

Bundles in tier ``local_extract`` ship unencrypted (low IP value —
selectors are easy to recreate by inspecting the page) and run inside
the local sandbox with bounded primitives.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agent.ec_skills.browser_node.contexts import (
    BrowserPrimitives,
    LocalExtractContext,
)

logger = logging.getLogger("ecan.hooks.feige_chat.v2")

__all__ = [
    "ScrapeResult",
    "ScrapeFunction",
    "FeigePreDispatchScrapeHookV2",
    "scrape_customer_bubble_v2",
]


@dataclass
class ScrapeResult:
    """Pure data: what local scraped from the DOM.

    Wire-format-friendly — a dataclass with str/bool fields so it
    serializes cleanly across the local→cloud boundary in hybrid mode.

    ``attachments`` is a list of dicts (each ``{"kind": "image", "url":
    "https://...", "alt": "..."}``) extracted from the customer bubble
    along with the text.  Empty list when the bubble was text-only or
    when scrape failed.  Cloud side is responsible for downloading and
    base64-encoding the URLs (see ``image_fetch.fetch_image_to_data_uri``)
    before forwarding to the Q&A worker — the wire format intentionally
    keeps URLs (not data URIs) here so the local→cloud RPC stays small.
    """
    scrape_ok: bool
    msg_id: str = ""
    text: str = ""
    error: str = ""
    attachments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scrape_ok": self.scrape_ok,
            "msg_id": self.msg_id,
            "text": self.text,
            "error": self.error,
            "attachments": list(self.attachments or []),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScrapeResult":
        # Defensive: accept missing/non-list attachments and coerce items.
        raw_atts = d.get("attachments") or []
        atts: list[dict] = []
        if isinstance(raw_atts, list):
            for a in raw_atts:
                if isinstance(a, dict) and a.get("url"):
                    atts.append({
                        "kind": str(a.get("kind") or "image"),
                        "url": str(a.get("url") or ""),
                        "alt": str(a.get("alt") or ""),
                    })
        return cls(
            scrape_ok=bool(d.get("scrape_ok")),
            msg_id=str(d.get("msg_id") or ""),
            text=str(d.get("text") or ""),
            error=str(d.get("error") or ""),
            attachments=atts,
        )


@runtime_checkable
class ScrapeFunction(Protocol):
    """Cross-tier interface: cloud asks local to scrape one customer.

    Implementations:

    * full_local: direct in-process call to
      :func:`scrape_customer_bubble_v2`.
    * hybrid_cloud (cloud-side proxy): RPCs the local executor and
      awaits a serialized :class:`ScrapeResult`.

    Tests pass a plain async callable.
    """
    async def __call__(self, *, customer_name: str) -> ScrapeResult: ...


# ─────────────────────────────────────────────────────────────────────────────
# The local_extract hook
# ─────────────────────────────────────────────────────────────────────────────


# JS scaffold for finding the latest customer bubble in Feige's chat
# thread.  Lifted verbatim from ``dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS``
# — selectors are Feige-specific (low IP, audit-classified ``local_extract``).
#
# Returns ``{ok: bool, msg_id, text, error}``.  Caller does the
# focus-customer click (via ``primitives.click``) before calling this
# script if the desired customer's pane isn't already visible.
_FEIGE_LATEST_BUBBLE_JS = r"""
(function() {
  try {
    const bubbles = document.querySelectorAll(
      '[data-id][class*="message-item"], .msg-item[data-id], li[data-id]'
    );
    if (!bubbles || bubbles.length === 0) {
      return JSON.stringify({ok: false, error: "no_bubbles_found"});
    }
    // Walk backwards looking for the most recent CUSTOMER bubble (not agent/system).
    for (let i = bubbles.length - 1; i >= 0; i--) {
      const node = bubbles[i];
      const cls = (node.className || "").toString();
      // Skip agent-side and system bubbles by class name heuristic.
      if (/agent|system|reply-self|outgoing/i.test(cls)) continue;
      const msg_id = node.getAttribute("data-id") || "";
      // Try a handful of common text containers.
      const textEl = node.querySelector(
        '.msg-text, .text-content, .content, [class*="message-text"]'
      );
      const text = (textEl ? textEl.textContent : node.textContent) || "";
      return JSON.stringify({
        ok: true,
        msg_id: msg_id,
        text: text.trim().slice(0, 4000),
      });
    }
    return JSON.stringify({ok: false, error: "no_customer_bubble"});
  } catch (e) {
    return JSON.stringify({ok: false, error: String(e)});
  }
})();
"""


async def scrape_customer_bubble_v2(
    ctx: LocalExtractContext,
    *,
    customer_name: str,
) -> ScrapeResult:
    """Scrape the latest customer bubble for ``customer_name``.

    Returns a populated :class:`ScrapeResult`.  This function is
    deliberately small — its only job is to run the bundled JS via
    ``ctx.primitives.eval_js`` and parse the result.

    Pre-conditions:
      * The Feige tab is already focused (cloud-side orchestrator
        ensures this via a prior ``primitives.click`` if needed).
      * ``customer_name`` is the human-readable name (used only for
        logging here; the JS finds the latest bubble in the currently
        active chat pane).

    On any failure (eval exception, unparseable JSON, malformed result)
    returns ``ScrapeResult(scrape_ok=False, error=...)`` — the caller
    falls back to alternate dedup strategies.
    """
    if ctx.primitives is None:
        return ScrapeResult(scrape_ok=False, error="no_primitives")

    try:
        raw = await ctx.primitives.eval_js(_FEIGE_LATEST_BUBBLE_JS)
    except Exception as err:
        logger.warning(
            f"[V2 pre_dispatch_scrape] eval_js failed for cust={customer_name!r}: "
            f"{type(err).__name__}: {err!r}"
        )
        return ScrapeResult(
            scrape_ok=False,
            error=f"eval_error:{type(err).__name__}",
        )

    # The JS returns a JSON-stringified result; eval_js implementations
    # may pre-parse or pass through, so accept both shapes.
    parsed: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            return ScrapeResult(
                scrape_ok=False,
                error=f"parse_error:non_json:{raw[:120]}",
            )

    if not isinstance(parsed, dict):
        return ScrapeResult(
            scrape_ok=False,
            error=f"parse_error:not_dict:{type(parsed).__name__}",
        )

    if not parsed.get("ok"):
        return ScrapeResult(
            scrape_ok=False,
            error=str(parsed.get("error") or "unknown"),
        )

    msg_id = str(parsed.get("msg_id") or "")
    text = str(parsed.get("text") or "")
    logger.info(
        f"[V2 pre_dispatch_scrape] scraped cust={customer_name!r} "
        f"msg_id=...{msg_id[-8:] if msg_id else ''} "
        f"text_preview={text[:50]!r}"
    )
    return ScrapeResult(scrape_ok=True, msg_id=msg_id, text=text)


# ─────────────────────────────────────────────────────────────────────────────
# Class wrapper — for symmetry with other v2 hooks
# ─────────────────────────────────────────────────────────────────────────────


class FeigePreDispatchScrapeHookV2:
    """Tier ``local_extract`` hook for PreDispatch.

    Wraps :func:`scrape_customer_bubble_v2` with a configurable bundle
    so the future tier-aware loader (Step 4) can instantiate it via the
    same path as the other v2 hooks.
    """

    EXECUTION_TIER = "local_extract"

    def __init__(self, config: dict | None = None):
        self.config = dict(config or {})

    async def run(
        self,
        ctx: LocalExtractContext,
        *,
        customer_name: str,
    ) -> ScrapeResult:
        return await scrape_customer_bubble_v2(ctx, customer_name=customer_name)
