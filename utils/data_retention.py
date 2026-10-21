"""Keep local data from growing without bound on a long unattended run.

Policy (2026-10-18): chat messages and chat notifications older than 90 days
are deleted from the local DB; files in the user's ``generated_medias`` folder
older than 60 days are deleted. Runs a few minutes after start, then daily.
Nothing else is touched: chats, agents, skills, tasks and the knowledge base
are kept, and only the logs already rotate on their own.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from utils.logger_helper import logger_helper as logger

CHAT_RETENTION_DAYS = 90
MEDIA_RETENTION_DAYS = 60
FIRST_RUN_DELAY_SEC = 300
INTERVAL_SEC = 24 * 3600

# Bookkeeping the media nodes keep next to the files; never aged out.
_KEEP_NAMES = {"pending_media_jobs.json"}

_thread: Optional[threading.Thread] = None


def prune_media(root: str, days: int = MEDIA_RETENTION_DAYS) -> int:
    """Delete files under *root* last modified more than *days* ago; remove
    folders left empty. Returns how many files were deleted."""
    base = Path(root)
    if not base.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    deleted = 0
    for p in sorted(base.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        try:
            if p.is_file():
                if p.name in _KEEP_NAMES:
                    continue
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    deleted += 1
            elif p.is_dir() and p != base and not any(p.iterdir()):
                p.rmdir()
        except Exception as e:
            logger.debug(f"[Retention] could not prune {p}: {e}")
    return deleted


def run_once(db_chat_service: Any, media_root: Optional[str]) -> dict:
    result = {}
    if db_chat_service is not None:
        try:
            result.update(db_chat_service.prune_older_than(CHAT_RETENTION_DAYS))
        except Exception as e:
            logger.warning(f"[Retention] chat pruning failed: {e}")
    if media_root:
        try:
            result["media_files"] = prune_media(media_root, MEDIA_RETENTION_DAYS)
        except Exception as e:
            logger.warning(f"[Retention] media pruning failed: {e}")
    if any(result.values()):
        logger.info(f"[Retention] removed data past retention (chat {CHAT_RETENTION_DAYS} d, "
                    f"generated media {MEDIA_RETENTION_DAYS} d): {result}")
    return result


def start_retention(mainwin: Any) -> None:
    """Start the background pruning thread (once per process)."""
    global _thread
    if os.environ.get("ECAN_DATA_RETENTION", "1") == "0":
        return
    if _thread is not None and _thread.is_alive():
        return

    def _loop():
        time.sleep(FIRST_RUN_DELAY_SEC)
        while True:
            media_root = None
            try:
                from agent.ec_skills.media.media_gen_node import generated_medias_root
                media_root = generated_medias_root()
            except Exception:
                pass
            run_once(getattr(mainwin, "db_chat_service", None), media_root)
            time.sleep(INTERVAL_SEC)

    _thread = threading.Thread(target=_loop, name="DataRetention", daemon=True)
    _thread.start()
