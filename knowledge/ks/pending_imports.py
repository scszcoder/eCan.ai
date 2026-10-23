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


# ---- per-store auto-apply (the store's operations agent refreshes the catalog
#      nightly; 快速生成 turns it on) ----
_AUTO_FILE = "catalog_auto_apply.json"
_auto_lock = threading.Lock()


def _auto_path() -> str:
    from knowledge.ks.service import get_service
    return os.path.join(get_service().data_dir, _AUTO_FILE)


def auto_apply_enabled(store_id: str) -> bool:
    # Fast Deploy before ybw wrote the flag to ~/.ecan (its CLI had no app
    # window); those stores keep their nightly auto-apply.
    legacy = os.path.join(os.path.expanduser("~"), ".ecan", "knowledge_service", _AUTO_FILE)
    for path in (_auto_path(), legacy):
        try:
            with open(path, encoding="utf-8") as f:
                if json.load(f).get(str(store_id or "")):
                    return True
        except Exception:
            continue
    return False


def set_auto_apply(store_id: str, on: bool = True) -> None:
    """A store whose fetched catalog is imported straight away (added / updated
    products; nothing is deleted) instead of waiting in 商品知识 → 导入."""
    with _auto_lock:
        path = _auto_path()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        if on:
            data[str(store_id)] = True
        else:
            data.pop(str(store_id), None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


def _auto_import(svc, path: str, store_id: str, source: str) -> Dict[str, Any]:
    """Import *path* for eCan store *store_id* with the suggested column mapping;
    raises when the file doesn't map cleanly (the caller stages it instead)."""
    headers, _rows = catalog_import.read_table(path)
    mapping = catalog_import.suggest_mapping(headers)
    check = svc.recheck_catalog(path, mapping)
    errors = (check.get("report") or {}).get("errors") or []
    if errors:
        raise ValueError("; ".join(map(str, errors)))
    tid = svc.tenant_id(None)
    ks_store = svc.store.find_store(tid, store_id) or svc.store.upsert_store(
        tid, name=store_id, ecan_store_id=store_id)
    result = svc.import_catalog(path, mapping, default_store_id=ks_store["id"], run_inline=True)
    return {"auto_applied": True, "store_id": store_id, "source": source, "result": result}


def stage_for_review(path_or_folder: str, store_id: str = "", source: str = "", note: str = "",
                     since: float = 0.0) -> Dict[str, Any]:
    """For a skill's code node: stage a downloaded catalog file (or the newest
    one in a downloads folder, written after ``since``) for the merchant.

        from knowledge.ks.pending_imports import stage_for_review
        stage_for_review(downloads_dir, store_id=store_id, source="抖店商品导出", since=t_start)

    A store with auto-apply on (its nightly operations refresh) is imported
    right away instead -- added / updated products, nothing deleted. A file
    that doesn't map cleanly is staged for review as before.
    """
    path = newest_file(path_or_folder, since) if os.path.isdir(path_or_folder) else path_or_folder
    if not path:
        raise FileNotFoundError(f"no catalog file in {path_or_folder}")
    from knowledge.ks.service import get_service
    svc = get_service()
    if store_id and auto_apply_enabled(store_id):
        from utils.logger_helper import logger_helper as logger
        try:
            out = _auto_import(svc, path, store_id, source)
            logger.info(f"[KS] auto-applied {source or 'catalog'} for store {store_id!r}: "
                        f"{(out.get('result') or {}).get('_message') or out.get('result')}")
            return out
        except Exception as e:
            logger.warning(f"[KS] auto-apply of {source or 'catalog'} for store {store_id!r} failed "
                           f"({e}); staged for review in 商品知识 → 导入 instead")
    return svc.stage_catalog(path, store_id=store_id, source=source, note=note)
