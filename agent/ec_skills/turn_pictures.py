"""The picture a buyer sent in their current turn, by customer id, for a few
minutes -- so steps that only see the turn's text can still use it.

The answering LLM node sees the photo (prep_multi_modal_content builds the
image part), but the knowledge search behind rag_query gets a query a node
wrote from the turn text, base64 stripped (2026-10-24 KEN: 4/4 photo turns
searched without the photo). The node remembers the picture here when it
builds the image part; the search asks for the buyer's recent picture.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

KEEP_S = 600.0
MAX_BUYERS = 200
_lock = threading.Lock()
_recent: Dict[str, Tuple[float, str]] = {}


def remember(customer_id: str, data_uri: str) -> None:
    cid = str(customer_id or "").strip()
    if not cid or not str(data_uri or "").startswith("data:image/"):
        return
    with _lock:
        _recent[cid] = (time.time(), data_uri)
        if len(_recent) > MAX_BUYERS:
            for old in sorted(_recent, key=lambda k: _recent[k][0])[:len(_recent) - MAX_BUYERS]:
                _recent.pop(old, None)


def recent(customer_id: str, max_age_s: float = KEEP_S) -> str:
    """The buyer's picture from the last *max_age_s* seconds, or ""."""
    cid = str(customer_id or "").strip()
    with _lock:
        hit = _recent.get(cid)
    if not hit or time.time() - hit[0] > max_age_s:
        return ""
    return hit[1]
