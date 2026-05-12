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
# thread.
#
# ─── Production-incident note (2026-04-27) ────────────────────────────
# The earlier version of this snippet used generic selectors
# (``[data-id][class*="message-item"]``, ``.msg-item[data-id]``,
# ``li[data-id]``) that matched *zero* elements in Feige's real DOM —
# Feige wraps each bubble in
#   ``<div data-qa-id="qa-message-warpper">
#      <div data-id="<uuid>" class="<obfuscated>">…</div>
#    </div>``
# with obfuscated, churning class names (e.g. ``tC9ap6QtAyeCD0jfuMns``).
# None of the generic selectors matched, so every scrape returned
# ``no_bubbles_found``, which fed through to ``pre_dispatch_v2._dispatch_one_item``
# as an empty ``scrape.msg_id``.  That blocked the ``set_last_dispatched_msg_id``
# recording at the bottom of ``_dispatch_one_item`` (the branch is
# ``if scrape.msg_id: …``), so **no dedup state was ever persisted**, and
# the next front-desk tick re-fired the same dispatch ~10–15 s later —
# producing the duplicate and crosstalk replies reported in production
# on 2026-04-27.
#
# The fix is to port the V1 selectors from
# ``dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS``, which use the stable
# ``data-qa-id="qa-message-warpper"`` wrapper and the inline
# ``flex-direction`` style to tell customer (``row``) from agent
# (``row-reverse``).  Those selectors have been battle-tested in V1
# for months and we also now extract attachments so the V2 multimodal
# path (``pre_dispatch_v2`` L281-295) can still eager-fetch images.
#
# If the selector tokens below ever need to change, KEEP THEM IN SYNC
# with ``dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS`` — the two JS
# snippets share the same Feige-DOM contract and should evolve
# together.  See ``tests/test_pre_dispatch_v2.py::
# FeigeLatestBubbleJsSelectorsTest`` for the regression guard.
#
# Returns ``{ok: bool, msg_id, text, attachments, error}``.  Caller does
# the focus-customer click (via ``primitives.click``) before calling
# this script if the desired customer's pane isn't already visible.
_FEIGE_LATEST_BUBBLE_JS = r"""
(function() {
  try {
    function _customerBubble(wrap) {
      // Customer-side row direction is "row"; agent-side is "row-reverse".
      // Feige sets flex-direction as an inline style, so reading
      // style.flexDirection is reliable across both real Feige and any
      // test emulation DOM.
      var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      if (!row) return null;
      if ((row.style.flexDirection || '').indexOf('reverse') !== -1) {
        return null;  // agent-side bubble
      }
      return row;
    }
    function _collectAttachments(row) {
      if (!row) return [];
      var atts = [];
      var imgs = Array.from(row.querySelectorAll('img'));
      for (var k = 0; k < imgs.length; k++) {
        var im = imgs[k];
        var cls = (im.className || '').toString();
        var alt = (im.getAttribute('alt') || '').trim();
        // Skip avatar imgs by class (sidebar or in-thread sender avatar).
        if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
        // Skip avatar imgs by alt (catches future class-name renames).
        if (alt === '头像') continue;
        // Prefer the resolved ``.src`` property so relative URLs are
        // absolutised — the downstream eager-fetch uses aiohttp, which
        // rejects relative URLs with ``InvalidURL``.
        var src = im.src || im.getAttribute('src') || '';
        if (!src) continue;
        // Skip data: URI fallback avatars (the default-avatar SVG).
        if (src.indexOf('data:image/svg') === 0) continue;
        atts.push({ kind: 'image', url: src, alt: alt });
      }
      return atts;
    }
    function _bubbleText(wrap) {
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1');
      if (!bubble) return '';
      if (bubble.classList.contains('messageIsMe')) return '';
      return (bubble.querySelector('pre') || bubble).textContent.trim();
    }
    function _isTransferMarker(text) {
      var t = String(text || '').replace(/\s+/g, '').trim();
      return t === '转人工' || t === '转人工客服' || t === '人工客服';
    }
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    if (!wrappers || wrappers.length === 0) {
      return JSON.stringify({ok: false, error: "no_bubbles_found"});
    }
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      var row = _customerBubble(wrap);
      if (!row) continue;                                   // agent-side or system
      var text = _bubbleText(wrap);
      var attachments = _collectAttachments(row);
      // A bubble counts as a customer message if it has either text or
      // a content image.  Image-only bubbles (text === '') must NOT be
      // silently dropped — customers routinely drag-drop screenshots
      // without any text.
      if (!text && attachments.length === 0) continue;
      if (text && _isTransferMarker(text)) continue;
      // Rebuild adjacent customer multimodal burst so burst-style
      // (text, image), (image, text), and (text, image, text) sequences
      // reach Q&A as one turn.  Stop at:
      //   * an agent-side bubble (real reply already happened) → STOP
      //   * a non-customer-non-agent wrapper (system/notice) → SKIP
      //   * the look-back cap (3 bubbles) → STOP
      // Dedup/msg_id stay anchored on the tail bubble so downstream logic
      // is unchanged.
      var tailText = text;
      var burstParts = [{ text: text, attachments: attachments }];
      var lookback = 0, j = i - 1;
      while (j >= 0 && lookback < 3) {
        var prevWrap = wrappers[j];
        var prevRowAny = prevWrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
        if (prevRowAny &&
            (prevRowAny.style.flexDirection || '').indexOf('reverse') !== -1) {
          break;  // agent reply already happened — don't reach across
        }
        var prevRow = _customerBubble(prevWrap);
        if (!prevRow) { j--; continue; }  // system/notice — skip, keep walking
        var prevText = _bubbleText(prevWrap);
        var prevAtts = _collectAttachments(prevRow);
        if (!prevText && prevAtts.length === 0) { j--; continue; }
        if (prevText && _isTransferMarker(prevText) && prevAtts.length === 0) { j--; continue; }
        burstParts.unshift({ text: prevText, attachments: prevAtts });
        lookback++;
        j--;
      }
      var textParts = [];
      attachments = [];
      for (var bp = 0; bp < burstParts.length; bp++) {
        var bpText = burstParts[bp].text || '';
        if (bpText && !_isTransferMarker(bpText)) textParts.push(bpText);
        var bpAtts = burstParts[bp].attachments || [];
        if (bpAtts.length) attachments = attachments.concat(bpAtts);
      }
      if (attachments.length) text = textParts.join('\n');
      else text = tailText;
      // ``data-id`` lives on an inner wrapper (``<div data-id="<uuid>"
      // class="<obfuscated>">``) inside the ``qa-message-warpper`` div,
      // not on the wrapper itself — querySelector for the first [data-id]
      // descendant.
      var msgIdEl = wrap.querySelector('[data-id]');
      var msgId = msgIdEl ? (msgIdEl.getAttribute('data-id') || '') : '';
      return JSON.stringify({
        ok: true,
        msg_id: msgId,
        text: text.slice(0, 4000),
        attachments: attachments,
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
    # Defensive: accept missing/non-list attachments and coerce items so
    # a selector drift in the JS can't push non-dict junk into the
    # downstream eager-fetch path.
    raw_atts = parsed.get("attachments") or []
    attachments: list[dict] = []
    if isinstance(raw_atts, list):
        for a in raw_atts:
            if isinstance(a, dict) and a.get("url"):
                attachments.append({
                    "kind": str(a.get("kind") or "image"),
                    "url": str(a.get("url") or ""),
                    "alt": str(a.get("alt") or ""),
                })
    logger.info(
        f"[V2 pre_dispatch_scrape] scraped cust={customer_name!r} "
        f"msg_id=...{msg_id[-8:] if msg_id else ''} "
        f"text_preview={text[:50]!r} "
        f"attachments={len(attachments)}"
    )
    return ScrapeResult(
        scrape_ok=True,
        msg_id=msg_id,
        text=text,
        attachments=attachments,
    )


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
