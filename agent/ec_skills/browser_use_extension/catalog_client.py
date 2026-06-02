"""
Catalog Client — fetch the canonical plugin catalog index.

Phase 3 status: stub. The catalog URL is read from
``ECAN_PLUGIN_CATALOG_URL`` (defaults to empty string). When empty, all
catalog operations return empty results and don't make network calls —
the GUI is expected to hide the Catalog tab in that mode.

Index schema (forward contract; Phase 4 will populate)
------------------------------------------------------
{
  "schema_version": 1,
  "fetched_at": "<ISO8601>",
  "bundles": [
    {
      "name": "feige_chat",
      "latest_version": "1.0.0",
      "kind": "hook_bundle",
      "description": "...",
      "author": "...",
      "versions": [
        {
          "version": "1.0.0",
          "archive_url": "https://.../feige_chat-1.0.0.zip",
          "signature_url": "https://.../feige_chat-1.0.0.sig",
          "manifest_url": "https://.../feige_chat-1.0.0.manifest.json",
          "sha256": "...",
          "signed_by": "ecan_catalog"
        }
      ]
    }
  ]
}
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("eCan")


DEFAULT_CATALOG_URL = ""  # placeholder — set ECAN_PLUGIN_CATALOG_URL when ready
DEFAULT_TIMEOUT_SEC = 10.0


@dataclass
class CatalogIndex:
    schema_version: int = 1
    fetched_at: float = 0.0
    bundles: list[dict] = field(default_factory=list)
    source_url: str = ""
    is_stub: bool = True

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "fetched_at": self.fetched_at,
            "bundles": self.bundles,
            "source_url": self.source_url,
            "is_stub": self.is_stub,
        }


_LAST_INDEX: Optional[CatalogIndex] = None
_LAST_ETAG: Optional[str] = None


def catalog_url() -> str:
    return os.getenv("ECAN_PLUGIN_CATALOG_URL", DEFAULT_CATALOG_URL).strip()


def is_enabled() -> bool:
    return bool(catalog_url())


def fetch_index(*, force: bool = False, timeout: float = DEFAULT_TIMEOUT_SEC) -> CatalogIndex:
    """Fetch (or return cached) catalog index.

    When ``ECAN_PLUGIN_CATALOG_URL`` is empty, returns an empty stub
    index immediately — no network call. ``force=True`` bypasses cache.
    """
    global _LAST_INDEX, _LAST_ETAG
    url = catalog_url()
    if not url:
        return CatalogIndex(
            schema_version=1,
            fetched_at=time.time(),
            bundles=[],
            source_url="",
            is_stub=True,
        )

    if not force and _LAST_INDEX is not None:
        return _LAST_INDEX

    req = urllib.request.Request(url)
    if _LAST_ETAG and not force:
        req.add_header("If-None-Match", _LAST_ETAG)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            etag = resp.headers.get("ETag")
            try:
                parsed = json.loads(data.decode("utf-8"))
            except Exception as e:
                logger.warning(f"[CatalogClient] index parse failed ({e}); returning stub")
                return CatalogIndex(source_url=url, is_stub=True)
            idx = CatalogIndex(
                schema_version=int(parsed.get("schema_version") or 1),
                fetched_at=time.time(),
                bundles=parsed.get("bundles") or [],
                source_url=url,
                is_stub=False,
            )
            _LAST_INDEX = idx
            _LAST_ETAG = etag
            logger.info(f"[CatalogClient] fetched index from {url}: {len(idx.bundles)} bundles")
            return idx
    except urllib.error.HTTPError as e:
        if e.code == 304 and _LAST_INDEX is not None:
            return _LAST_INDEX
        logger.warning(f"[CatalogClient] fetch failed ({e}); returning stub")
        return CatalogIndex(source_url=url, is_stub=True)
    except Exception as e:
        logger.warning(f"[CatalogClient] fetch failed ({e}); returning stub")
        return CatalogIndex(source_url=url, is_stub=True)


def reset_cache() -> None:
    """Test helper."""
    global _LAST_INDEX, _LAST_ETAG
    _LAST_INDEX = None
    _LAST_ETAG = None


__all__ = ["CatalogIndex", "DEFAULT_CATALOG_URL", "catalog_url", "is_enabled", "fetch_index", "reset_cache"]
