"""URL detection helper for customer chat messages (mt048C, 2026-05-26).

Background
----------
When a customer pastes a product URL into Feige chat, the customer's
text bubble is short-lived: Feige's React app replaces the raw URL with
a rendered ``[商品卡片]`` widget within a second or two.  Our scrape
catches the widget (with title/price/coupon) but the ORIGINAL URL is
gone — the card's ``product_url`` field is intentionally null in
``dom_assets.py`` because Feige doesn't expose it on the DOM.

If a customer also sends the URL in PLAIN TEXT (often immediately
before / after the card), our scrape DOES capture that text, but the
existing dispatch path just sends the text to the Q&A LLM as opaque
input.  The Q&A bot then often asks the customer to "再发一下商品链接"
because it can't tell the URL apart from any other text.

This module is the first piece of mt048C: a regex-based detector that
surfaces customer-provided URLs as a structured field on the dispatch
item.  Downstream consumers (mt048D — the front-desk browser-fetch
routing) can then decide how to handle them.

What this module DOES
---------------------
* :func:`find_first_url` — return the first http/https URL found in a
  text blob.  Empty string when no URL.
* :func:`find_all_urls` — list of all unique URLs (order preserved).
* :func:`is_jinritemai_product_url` — predicate for the specific
  Feige/Douyin product URL pattern (``haohuo.jinritemai.com/.../id=N``)
  we expect from customer-pasted cards.
* :func:`extract_product_id` — pull the ``id=N`` query parameter from a
  product URL.  Empty when no match.

What this module DOES NOT do
----------------------------
* Fetch URL contents (mt048D).
* Modify dispatch routing (mt048D).
* Touch the Q&A worker / front-desk prompt (mt048D).

Tunable
-------
``ECAN_URL_DETECTION_ENABLED`` — default ``true``.  Set to a falsy
value to disable detection entirely (useful for A/B comparisons).
"""
from __future__ import annotations

import os
import re
from typing import Optional


# Conservative URL regex.  Matches http:// or https:// followed by a
# host + optional path/query/fragment.  Stops at whitespace or common
# punctuation that obviously isn't part of a URL (Chinese commas,
# brackets, quote characters).  Greedy on path/query so query strings
# like ?id=N&origin=X are captured fully.
_URL_RE = re.compile(
    r"https?://[^\s　、。，；：\"'<>\[\]\(\)（）「」【】]+",
    flags=re.IGNORECASE,
)

# Feige / Douyin e-commerce product detail URL.  Example:
#   https://haohuo.jinritemai.com/ecommerce/trade/detail/index.html?id=3806636940602769454&origin_type=604
# The host is stable; the path can vary slightly across Feige versions
# so we only require the host + an ``id=`` query parameter.
_JINRITEMAI_PRODUCT_HOST = "haohuo.jinritemai.com"
_PRODUCT_ID_RE = re.compile(r"[?&]id=([0-9]+)")


def _env_bool(name: str, default: bool) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    """True when URL detection is active.  Default true; set
    ``ECAN_URL_DETECTION_ENABLED=0`` to disable."""
    return _env_bool("ECAN_URL_DETECTION_ENABLED", True)


def find_first_url(text: str) -> str:
    """Return the first http(s) URL in *text*, or empty string."""
    if not text or not is_enabled():
        return ""
    m = _URL_RE.search(str(text))
    return m.group(0) if m else ""


def find_all_urls(text: str) -> list[str]:
    """Return all unique http(s) URLs in *text*, order preserved.

    Empty list when detection is disabled or *text* has no URLs.
    """
    if not text or not is_enabled():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(str(text)):
        u = m.group(0)
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def is_jinritemai_product_url(url: str) -> bool:
    """True when *url* matches the Feige / Douyin product detail URL
    shape (host = haohuo.jinritemai.com, has an ``id=N`` parameter)."""
    if not url:
        return False
    s = str(url).lower()
    if _JINRITEMAI_PRODUCT_HOST not in s:
        return False
    return bool(_PRODUCT_ID_RE.search(url))


def extract_product_id(url: str) -> str:
    """Return the value of the ``id=`` query parameter, or empty string
    when *url* doesn't carry one.  No URL-shape validation — call
    :func:`is_jinritemai_product_url` first if you need that."""
    if not url:
        return ""
    m = _PRODUCT_ID_RE.search(str(url))
    return m.group(1) if m else ""


__all__ = [
    "is_enabled",
    "find_first_url",
    "find_all_urls",
    "is_jinritemai_product_url",
    "extract_product_id",
]
