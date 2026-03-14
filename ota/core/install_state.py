#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Optional

from config.app_info import app_info


_STATE_FILE_NAME = "ota_install_state.json"


def _get_state_file_path() -> Path:
    return Path(app_info.appdata_path) / _STATE_FILE_NAME


def write_pending_install_state(target_version: str, package_path: str, logger=None) -> Path:
    state_path = _get_state_file_path()
    payload = {
        'target_version': str(target_version or '').strip(),
        'package_path': str(package_path or '').strip(),
        'created_at': int(time.time()),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if logger:
        logger.info(f"[OTA] Pending install state written: {state_path} -> target_version={payload['target_version']}")
    return state_path


def read_pending_install_state(logger=None) -> Optional[dict[str, Any]]:
    state_path = _get_state_file_path()
    if not state_path.exists() or not state_path.is_file():
        return None

    try:
        payload = json.loads(state_path.read_text(encoding='utf-8'))
        if isinstance(payload, dict):
            return payload
    except Exception as e:
        if logger:
            logger.warning(f"[OTA] Failed to read pending install state: {e}")
    return None


def clear_pending_install_state(logger=None) -> None:
    state_path = _get_state_file_path()
    try:
        if state_path.exists():
            state_path.unlink()
            if logger:
                logger.info(f"[OTA] Cleared pending install state: {state_path}")
    except Exception as e:
        if logger:
            logger.warning(f"[OTA] Failed to clear pending install state: {e}")


def confirm_pending_install_result(current_version: str, logger=None) -> Optional[bool]:
    payload = read_pending_install_state(logger=logger)
    if not payload:
        return None

    target_version = str(payload.get('target_version') or '').strip()
    package_path = str(payload.get('package_path') or '').strip()
    created_at = payload.get('created_at')

    if logger:
        logger.info(
            f"[OTA] Found pending install state on startup: "
            f"target_version={target_version}, current_version={current_version}, package_path={package_path}, created_at={created_at}"
        )

    if target_version and str(current_version).strip() == target_version:
        if logger:
            logger.info(f"[OTA] Installation confirmation succeeded: current version matches target version {target_version}")
        clear_pending_install_state(logger=logger)
        return True

    if logger:
        logger.warning(
            f"[OTA] Installation confirmation failed: installer was launched for target_version={target_version}, "
            f"but app restarted with current_version={current_version}"
        )
    clear_pending_install_state(logger=logger)
    return False


def handle_pending_install_cleanup(current_version: str, logger=None) -> Optional[bool]:
    payload = read_pending_install_state(logger=logger)
    if not payload:
        return None

    result = confirm_pending_install_result(current_version=current_version, logger=logger)
    if result is not True:
        if logger:
            logger.info(f"[OTA] Skipping downloaded package cleanup because install confirmation result={result}")
        return result

    package_path_raw = str(payload.get('package_path') or '').strip()
    if not package_path_raw:
        if logger:
            logger.info("[OTA] No package_path recorded in pending install state; nothing to clean up")
        return True

    package_path = Path(package_path_raw)
    if not package_path.exists():
        if logger:
            logger.info(f"[OTA] Downloaded installer already absent, no cleanup needed: {package_path}")
        return True

    try:
        package_path.unlink()
        if logger:
            logger.info(f"[OTA] Deleted downloaded installer after successful upgrade: {package_path}")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"[OTA] Failed to delete downloaded installer after successful upgrade: {e}")
        return True
