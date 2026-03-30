import json
import os
import re
import time
from typing import Any

from utils.user_path_helper import ensure_user_data_dir
from utils.logger_helper import logger_helper as logger


def _cache_root() -> str:
    root = ensure_user_data_dir(subdir=os.path.join("runtime_cache", "skill_node_artifacts"))
    os.makedirs(root, exist_ok=True)
    return root


def _sanitize_tag(value: Any, default: str = "run") -> str:
    s = str(value or "").strip() or default
    return re.sub(r"[^\w\-]+", "_", s)


def _policy() -> dict:
    return {
        "ttl_sec": int(os.getenv("EC_ARTIFACT_TTL_SEC", "86400")),  # default 24h
        "max_files": int(os.getenv("EC_ARTIFACT_MAX_FILES", "500")),
        "max_total_bytes": int(os.getenv("EC_ARTIFACT_MAX_TOTAL_BYTES", str(512 * 1024 * 1024))),  # 512MB
    }


def _list_artifact_files(root: str) -> list[tuple[str, float, int]]:
    out: list[tuple[str, float, int]] = []
    try:
        for name in os.listdir(root):
            if not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
            except Exception:
                continue
            out.append((path, float(st.st_mtime), int(st.st_size)))
    except Exception:
        return []
    return out


def _parse_run_tag_from_filename(path: str) -> str:
    base = os.path.basename(path)
    if "__" not in base:
        return ""
    return base.split("__", 1)[0]


def prune_cache(*, ttl_sec: int | None = None, max_files: int | None = None, max_total_bytes: int | None = None) -> dict:
    root = _cache_root()
    pol = _policy()
    ttl = int(ttl_sec if ttl_sec is not None else pol["ttl_sec"])
    max_n = int(max_files if max_files is not None else pol["max_files"])
    max_b = int(max_total_bytes if max_total_bytes is not None else pol["max_total_bytes"])
    now = time.time()

    removed = {"expired": 0, "overflow": 0, "bytes_freed": 0}
    files = _list_artifact_files(root)

    # 1) Remove expired.
    keep: list[tuple[str, float, int]] = []
    for path, mtime, size in files:
        if ttl > 0 and (now - mtime) > ttl:
            try:
                os.remove(path)
                removed["expired"] += 1
                removed["bytes_freed"] += size
            except Exception:
                keep.append((path, mtime, size))
        else:
            keep.append((path, mtime, size))

    # 2) Enforce max_files / max_total_bytes by removing oldest first.
    keep.sort(key=lambda x: x[1])  # oldest first
    total_bytes = sum(s for _, _, s in keep)
    while keep and (len(keep) > max_n or total_bytes > max_b):
        path, _, size = keep.pop(0)
        try:
            os.remove(path)
            removed["overflow"] += 1
            removed["bytes_freed"] += size
            total_bytes -= size
        except Exception:
            pass

    return removed


def purge_run_artifacts(run_tag: str) -> int:
    rt = _sanitize_tag(run_tag, default="")
    if not rt:
        return 0
    root = _cache_root()
    removed = 0
    for path, _, size in _list_artifact_files(root):
        if _parse_run_tag_from_filename(path) != rt:
            continue
        try:
            os.remove(path)
            removed += 1
        except Exception:
            continue
    if removed:
        logger.info(f"[ArtifactStore] Purged {removed} artifacts for run_tag={rt}")
    return removed


def write_cached_artifact(*, run_tag: str, node_tag: str, payload: dict) -> dict:
    root = _cache_root()
    rt = _sanitize_tag(run_tag)
    nt = _sanitize_tag(node_tag, default="node")
    ts_ms = int(time.time() * 1000)
    artifact_id = f"{rt}__{nt}__{ts_ms}"
    path = os.path.join(root, f"{artifact_id}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    # Opportunistic cleanup on write to avoid unbounded growth.
    try:
        prune_cache()
    except Exception as e:
        logger.debug(f"[ArtifactStore] prune on write failed: {e}")

    return {
        "artifact_id": artifact_id,
        "artifact_type": "browser_node_result",
        "artifact_version": "v1",
        "path": path,
        "created_at_ms": ts_ms,
        "run_tag": rt,
        "node_tag": nt,
    }


def read_cached_artifact(index: dict) -> dict:
    if not isinstance(index, dict):
        return {}
    path = index.get("path")
    if not isinstance(path, str) or not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

