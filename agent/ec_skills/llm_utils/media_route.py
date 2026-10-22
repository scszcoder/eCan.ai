"""Where an LLM call that carries images / video goes, and on which model.

The llm-proxy's normal route (/api/llm-proxy) sits behind the CloudBase gateway,
which refuses request bodies above ~100 KB (HTTP 413 EXCEED_MAX_PAYLOAD_SIZE): a
buyer's photo of a damaged item (0.5-3 MB) never reached the model. The direct
web-function route (/api/llm-proxy-b) takes ~6 MB and serves the same
/v1/chat/completions (checked 2026-10-21: a 91 KB screenshot -> 413 on the
normal route, answered in 2.7 s on the direct one).

Media turns also switch to a vision model: the Q&A's fast text model does see a
small image, but a vision model reads detail (damage, labels) better.

Env: ECAN_MEDIA_MODEL (default qwen3-vl-plus), ECAN_MEDIA_LLM_URL (full base URL
override), ECAN_MEDIA_ROUTE=0 keeps the node's own host and model.
"""
from __future__ import annotations

import os
from typing import Tuple

DEFAULT_MEDIA_MODEL = "qwen3-vl-plus"


def media_route(host: str, model: str) -> Tuple[str, str]:
    """(host, model) for an eCanAI call carrying media."""
    if os.environ.get("ECAN_MEDIA_ROUTE", "1") == "0":
        return host, model
    media_model = os.environ.get("ECAN_MEDIA_MODEL", "").strip() or DEFAULT_MEDIA_MODEL
    override = os.environ.get("ECAN_MEDIA_LLM_URL", "").strip()
    if override:
        return override, media_model
    h = (host or "").rstrip("/")
    for normal, direct in (("/api/llm-proxy/", "/api/llm-proxy-b/"),):
        if normal in h + "/":
            h = (h + "/").replace(normal, direct, 1).rstrip("/")
            break
    return h, media_model
