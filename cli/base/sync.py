#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloud-sync helper for CLI write operations.

The CLI writes to the local SQLite DB only. The GUI, by contrast, calls
``_trigger_cloud_sync`` after every write so changes reach the cloud backend.
This helper gives the CLI the same behavior so that an ``ecan agents add`` (or
update/remove) propagates to the cloud just like the GUI does — which is what
the cloud-side agent relies on when it proposes CLI commands for local
execution.

Sync is best-effort and synchronous (the CLI is a short-lived process, so a
background thread might not finish before exit). Failures never fail the CLI
command — the local write already succeeded and the offline queue will retry.
"""

from typing import Any, Dict

from .output import get_output


def cloud_sync(data_type: str, data: Dict[str, Any], operation: str) -> None:
    """Best-effort synchronous cloud sync after a local write.

    Args:
        data_type: a DataType value (e.g. DataType.AGENT).
        data: the record payload; must include an ``id`` for update/delete.
        operation: an Operation value (Operation.ADD / UPDATE / DELETE).
    """
    out = get_output()
    try:
        from agent.cloud_api.offline_sync_manager import get_sync_manager

        manager = get_sync_manager()
        result = manager.sync_to_cloud(data_type, data, operation)
    except Exception as e:  # cloud libs missing, not authed, offline, etc.
        out.warning(f"Saved locally; cloud sync skipped ({e}).")
        return

    if isinstance(result, dict) and result.get("synced"):
        out.info("☁️  Synced to cloud.")
    elif isinstance(result, dict) and result.get("cached"):
        out.info("💾 Queued for cloud sync (will retry).")
    else:
        err = (result or {}).get("error") if isinstance(result, dict) else None
        out.warning(f"Saved locally; cloud sync incomplete{f' ({err})' if err else ''}.")
