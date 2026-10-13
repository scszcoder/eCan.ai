"""Each store's current promotions, refreshed on a schedule by the promo-read
skill (抖店营销导出 and its per-platform siblings).

Unlike catalog files (pending_imports.py, staged once for the merchant to
review and import), promotions start and stop through the day. A snapshot is
therefore *auto-applied*: the skill overwrites the store's snapshot every cycle,
and the Q&A agents read it as a dated "[当前活动] 截至HH:MM：…" line so a buyer
asking about deals gets a fresh, timestamped answer instead of a stall.

A snapshot is small and read on every Q&A turn, so it is one JSON file per store
(not an embedded document). "No active promotions" is a real, useful snapshot
(summary "当前无活动") -- it lets Q&A answer definitively rather than deflect.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

# A snapshot older than this is no longer trusted for an answer (the refresh is
# every 30 min, so this tolerates a couple of missed cycles before going quiet).
_DEFAULT_STALE_AFTER_MIN = 90


def _safe_name(store_id: str) -> str:
    safe = "".join(c for c in str(store_id or "") if c.isalnum() or c in "-_.")
    return safe or "_"


class PromoSnapshots:
    def __init__(self, folder: str):
        self.folder = os.path.join(folder, "promo_snapshots")
        self._lock = threading.Lock()

    def _path(self, store_id: str) -> str:
        return os.path.join(self.folder, f"{_safe_name(store_id)}.json")

    def set(self, store_id: str, promotions: Optional[List[Dict[str, Any]]] = None,
            summary: str = "", source: str = "") -> Dict[str, Any]:
        """Overwrite the store's current-promotions snapshot (auto-applied)."""
        entry = {
            "store_id": str(store_id or ""),
            "captured_at": time.time(),
            "source": (source or "").strip(),
            "promotions": list(promotions or []),
            "summary": (summary or "").strip(),
        }
        with self._lock:
            os.makedirs(self.folder, exist_ok=True)
            dest = self._path(store_id)
            tmp = dest + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=1)
            os.replace(tmp, dest)
        return entry

    def get(self, store_id: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self._path(store_id), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def line(self, store_id: str, stale_after_min: float = _DEFAULT_STALE_AFTER_MIN) -> str:
        """The "[当前活动] 截至HH:MM：<summary>" line to hand a Q&A turn, or "" when
        there is no snapshot, it is empty, or it is too old to trust."""
        snap = self.get(store_id)
        if not snap:
            return ""
        captured = float(snap.get("captured_at") or 0)
        if stale_after_min > 0 and captured and time.time() - captured > stale_after_min * 60:
            return ""
        summary = str(snap.get("summary") or "").strip()
        if not summary:
            return ""
        if captured:
            return f"[当前活动] 截至{time.strftime('%H:%M', time.localtime(captured))}：{summary}"
        return f"[当前活动] {summary}"


def apply_snapshot(store_id: str, promotions: Optional[List[Dict[str, Any]]] = None,
                   summary: str = "", source: str = "") -> Dict[str, Any]:
    """For the promo-read skill's final code node: write this cycle's snapshot.

        from knowledge.ks.promo_snapshots import apply_snapshot
        apply_snapshot(store_id, promotions=rows, summary="满199减30；新人券立减10元", source="抖店营销中心")
    """
    from knowledge.ks.service import get_service
    return get_service().set_promos(store_id, promotions=promotions, summary=summary, source=source)
