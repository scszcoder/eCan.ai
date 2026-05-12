#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from config.app_info import app_info


_STATE_FILE_NAME = "ota_install_state.json"
_DOWNLOAD_DIR_NAME = "ota_downloads"
_INSTALLER_VERSION_RE = re.compile(
    r"^ecan-(?P<version>.+?)-(?:windows|macos|darwin|linux)(?:[-_].*)?$",
    re.IGNORECASE,
)


def _get_state_file_path() -> Path:
    return Path(app_info.appdata_path) / _STATE_FILE_NAME


def _get_download_dir_path() -> Path:
    return Path(app_info.appdata_path) / _DOWNLOAD_DIR_NAME


def write_pending_install_state(target_version: str, package_path: str, logger=None, target_version_core: str = "") -> Path:
    state_path = _get_state_file_path()
    payload = {
        'target_version': str(target_version or '').strip(),
        'target_version_core': str(target_version_core or '').strip(),
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


def _installer_version_from_name(value: str) -> str:
    name = str(value or '').strip().replace('\\', '/').rsplit('/', 1)[-1]
    if not name:
        return ""
    match = _INSTALLER_VERSION_RE.match(name)
    if not match:
        return ""
    return str(match.group('version') or '').strip()


def _version_candidates(value: str) -> set[str]:
    raw = str(value or '').strip()
    if not raw:
        return set()
    values = {raw, raw.lower()}
    installer_version = _installer_version_from_name(raw)
    if installer_version:
        values.add(installer_version)
        values.add(installer_version.lower())
    if '_' in raw:
        values.add(raw.split('_', 1)[1])
        values.add(raw.rsplit('_', 1)[1])
    expanded = set(values)
    for item in list(values):
        if item.lower().startswith('v') and len(item) > 1:
            expanded.add(item[1:])
    return {item.strip().lower() for item in expanded if item and item.strip()}


def _numeric_version_key(value: str) -> Optional[tuple[int, ...]]:
    keys: list[tuple[int, ...]] = []
    for item in _version_candidates(value):
        parts = re.findall(r"\d+", item)
        if not parts:
            continue
        try:
            key = tuple(int(part) for part in parts)
        except Exception:
            continue
        if key:
            keys.append(key)
    if not keys:
        return None
    return max(keys, key=lambda item: (len(item), item))


def _compare_versions(left: str, right: str) -> Optional[int]:
    left_key = _numeric_version_key(left)
    right_key = _numeric_version_key(right)
    if not left_key or not right_key:
        return None
    width = max(len(left_key), len(right_key))
    left_padded = left_key + (0,) * (width - len(left_key))
    right_padded = right_key + (0,) * (width - len(right_key))
    if left_padded < right_padded:
        return -1
    if left_padded > right_padded:
        return 1
    return 0


def _versions_match(current_version: str, *target_versions: str) -> bool:
    current_candidates = _version_candidates(current_version)
    if not current_candidates:
        return False
    for target_version in target_versions:
        if current_candidates & _version_candidates(target_version):
            return True
    return False


def _cleanup_downloaded_installers_for_current_version(current_version: str, logger=None) -> tuple[int, int, int]:
    download_dir = _get_download_dir_path()
    if not download_dir.exists() or not download_dir.is_dir():
        return 0, 0, 0
    if not _numeric_version_key(current_version):
        return 0, 0, 0

    cleaned_count = 0
    cleaned_size = 0
    failed_count = 0
    try:
        for child in list(download_dir.iterdir()):
            if not child.is_file():
                continue
            installer_version = _installer_version_from_name(child.name)
            if not installer_version:
                continue
            comparison = _compare_versions(installer_version, current_version)
            if comparison is None:
                continue
            if comparison > 0 and not _versions_match(current_version, installer_version):
                continue
            ok, size = _unlink_file_with_retry(child, logger=logger)
            if ok:
                cleaned_count += 1
                cleaned_size += size
                if logger:
                    logger.info(f"[OTA] Deleted stale downloaded installer for current version {current_version}: {child}")
            else:
                failed_count += 1
        try:
            if download_dir.exists() and not any(download_dir.iterdir()):
                download_dir.rmdir()
                if logger:
                    logger.info(f"[OTA] Removed empty OTA download directory: {download_dir}")
        except Exception:
            pass
    except Exception as e:
        failed_count += 1
        if logger:
            logger.warning(f"[OTA] Failed to scan OTA download directory for stale installer cleanup: {e}")
    return cleaned_count, cleaned_size, failed_count


def _unlink_file_with_retry(path: Path, logger=None, attempts: int = 3, delay_seconds: float = 0.5) -> tuple[bool, int]:
    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            if not path.exists():
                return True, 0
            size = path.stat().st_size
            path.unlink()
            return True, size
        except Exception as e:
            last_error = e
            if attempt < max(1, attempts) - 1:
                time.sleep(delay_seconds)
    if logger:
        logger.warning(f"[OTA] Failed to delete downloaded installer after {attempts} attempt(s): {path} ({last_error})")
    return False, 0


def confirm_pending_install_result(current_version: str, logger=None, clear_state: bool = True) -> Optional[bool]:
    payload = read_pending_install_state(logger=logger)
    if not payload:
        return None

    target_version = str(payload.get('target_version') or '').strip()
    target_version_core = str(payload.get('target_version_core') or '').strip()
    package_path = str(payload.get('package_path') or '').strip()
    created_at = payload.get('created_at')

    if logger:
        logger.info(
            f"[OTA] Found pending install state on startup: "
            f"target_version={target_version}, current_version={current_version}, package_path={package_path}, created_at={created_at}"
        )

    if _versions_match(current_version, target_version, target_version_core):
        if logger:
            logger.info(f"[OTA] Installation confirmation succeeded: current version matches target version {target_version}")
        if clear_state:
            clear_pending_install_state(logger=logger)
        return True

    if logger:
        logger.warning(
            f"[OTA] Installation confirmation failed: installer was launched for target_version={target_version}, "
            f"but app restarted with current_version={current_version}"
        )
    if clear_state:
        clear_pending_install_state(logger=logger)
    return False


def handle_pending_install_cleanup(current_version: str, logger=None) -> Optional[bool]:
    payload = read_pending_install_state(logger=logger)
    if not payload:
        cleaned_count, cleaned_size, failed_count = _cleanup_downloaded_installers_for_current_version(
            current_version=current_version,
            logger=logger,
        )
        if cleaned_count and logger:
            logger.info(
                f"[OTA] Startup cleanup removed {cleaned_count} stale installer package(s), "
                f"freed {cleaned_size / (1024 * 1024):.2f} MB"
            )
        if failed_count and logger:
            logger.warning(f"[OTA] Startup cleanup left {failed_count} stale installer package(s)")
        return None

    result = confirm_pending_install_result(current_version=current_version, logger=logger, clear_state=False)
    if result is not True:
        if logger:
            logger.info(f"[OTA] Skipping downloaded package cleanup because install confirmation result={result}")
        clear_pending_install_state(logger=logger)
        return result

    package_path_raw = str(payload.get('package_path') or '').strip()
    if not package_path_raw:
        if logger:
            logger.info("[OTA] No package_path recorded in pending install state; nothing to clean up")
        clear_pending_install_state(logger=logger)
        return True

    package_path = Path(package_path_raw)
    cleaned_count = 0
    cleaned_size = 0
    failed_count = 0
    if not package_path.exists():
        if logger:
            logger.info(f"[OTA] Downloaded installer already absent, no cleanup needed: {package_path}")
    else:
        ok, size = _unlink_file_with_retry(package_path, logger=logger)
        if ok:
            cleaned_size += size
            cleaned_count += 1
            if logger:
                logger.info(f"[OTA] Deleted downloaded installer after successful upgrade: {package_path}")
        else:
            failed_count += 1

    download_dir = _get_download_dir_path()
    try:
        if download_dir.exists() and download_dir.is_dir():
            package_path_resolved = package_path.resolve(strict=False)
            for child in download_dir.iterdir():
                if not child.is_file():
                    continue
                try:
                    if child.resolve(strict=False) == package_path_resolved:
                        continue
                except Exception:
                    pass
                ok, size = _unlink_file_with_retry(child, logger=logger)
                if ok:
                    cleaned_size += size
                    cleaned_count += 1
                    if logger:
                        logger.info(f"[OTA] Deleted accumulated installer package after successful upgrade: {child}")
                else:
                    failed_count += 1
            try:
                if not any(download_dir.iterdir()):
                    download_dir.rmdir()
                    if logger:
                        logger.info(f"[OTA] Removed empty OTA download directory: {download_dir}")
            except Exception:
                pass
    except Exception as e:
        failed_count += 1
        if logger:
            logger.warning(f"[OTA] Failed to scan OTA download directory for cleanup: {e}")

    if cleaned_count and logger:
        logger.info(
            f"[OTA] Successful-install cleanup removed {cleaned_count} installer package(s), "
            f"freed {cleaned_size / (1024 * 1024):.2f} MB"
        )

    if failed_count:
        if logger:
            logger.warning(f"[OTA] Successful-install cleanup left {failed_count} item(s); pending state kept for retry")
    else:
        clear_pending_install_state(logger=logger)

    return True
