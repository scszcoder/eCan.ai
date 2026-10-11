"""
Catalog files an agent fetched for the merchant (e.g. a store's product export),
waiting for the merchant to review and import them.

An agent never imports on its own: it stages the file here, and 商品知识 → 导入
shows it with the usual column mapping and preview, one click from imported.
The staged copy lives under the Knowledge Service's data folder, so the
original download can be cleaned up by the site without losing it.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from knowledge.ks import catalog_import

_EXTS = (".xlsx", ".xls", ".csv", ".tsv", ".json")


def newest_file(folder: str, since: float = 0.0, exts=_EXTS) -> str:
    """The most recently written catalog-like file in ``folder`` (newer than
    ``since``), or "" -- for a skill that just downloaded an export."""
    best, best_t = "", since
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if name.lower().endswith(exts) and os.path.isfile(p):
                t = os.path.getmtime(p)
                if t > best_t:
                    best, best_t = p, t
    except OSError:
        return ""
    return best


class PendingImports:
    def __init__(self, folder: str):
        self.folder = folder
        self.files = os.path.join(folder, "staged_imports")
        self.index = os.path.join(folder, "pending_imports.json")
        self._lock = threading.Lock()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.index, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.index + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.index)

    def stage(self, path: str, store_id: str = "", source: str = "", note: str = "") -> Dict[str, Any]:
        """Copy a catalog file in and list it for review. Raises if it can't be read."""
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        headers, rows = catalog_import.read_table(path)
        if not headers or not rows:
            raise ValueError(f"no product rows in {os.path.basename(path)}")
        os.makedirs(self.files, exist_ok=True)
        pid = uuid.uuid4().hex[:12]
        dest = os.path.join(self.files, f"{pid}_{os.path.basename(path)}")
        shutil.copy2(path, dest)
        entry = {"id": pid, "path": dest, "file_name": os.path.basename(path), "store_id": store_id or "",
                 "source": source or "", "note": note or "", "rows": len(rows), "created_at": time.time()}
        with self._lock:
            items = self._load()
            items.append(entry)
            self._save(items)
        return entry

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e for e in self._load() if os.path.isfile(e.get("path", ""))]

    def get(self, pid: str) -> Optional[Dict[str, Any]]:
        return next((e for e in self.list() if e.get("id") == pid), None)

    def remove(self, pid: str, delete_file: bool = True) -> bool:
        with self._lock:
            items = self._load()
            keep = [e for e in items if e.get("id") != pid]
            gone = [e for e in items if e.get("id") == pid]
            if not gone:
                return False
            self._save(keep)
        if delete_file:
            for e in gone:
                try:
                    os.remove(e["path"])
                except OSError:
                    pass
        return True


def stage_for_review(path_or_folder: str, store_id: str = "", source: str = "", note: str = "",
                     since: float = 0.0) -> Dict[str, Any]:
    """For a skill's code node: stage a downloaded catalog file (or the newest
    one in a downloads folder, written after ``since``) for the merchant.

        from knowledge.ks.pending_imports import stage_for_review
        stage_for_review(downloads_dir, store_id=store_id, source="抖店商品导出", since=t_start)
    """
    path = newest_file(path_or_folder, since) if os.path.isdir(path_or_folder) else path_or_folder
    if not path:
        raise FileNotFoundError(f"no catalog file in {path_or_folder}")
    from knowledge.ks.service import get_service
    return get_service().stage_catalog(path, store_id=store_id, source=source, note=note)
