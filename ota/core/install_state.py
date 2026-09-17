#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from config.app_info import app_info
from .installer import safe_makedirs


_STATE_FILE_NAME = "ota_install_state.json"
_DOWNLOAD_DIR_NAME = "ota_downloads"
# Match installer filenames emitted by ``build_system/ecan_build.py``. The
# pattern covers both variants:
#   * INTL:  ``eCan-{ver}-{platform}-{arch}-{setup}.exe``
#   * CN:    ``eCan.cn-{ver}-{platform}-{arch}-{setup}.exe``
#
# The CN ``.cn`` suffix MUST be optional in the pattern; otherwise the
# lazy version capture consumes ``.cn-1.0.0`` as the "version" and
# ``_numeric_version_key`` ends up comparing only the trailing digits
# (``1.0.0``) — which happens to be right for ``1.0.0`` ↔ ``1.0.0`` but
# silently breaks for any version with extra channel/build suffixes
# (e.g. ``1.0.0-rc1`` → parsed as ``.cn-1.0.0-rc1`` → numeric key
# ``(1, 0, 0, 1)`` instead of ``(1, 0, 0)``). See
# ``tests/unit/test_ota_path_safety.py::TestInstallerFilenameRegex`` for
# the regression test pinning this.
_INSTALLER_VERSION_RE = re.compile(
    r"^ecan(?:\.cn)?-(?P<version>.+?)-(?:windows|macos|darwin|linux)(?:[-_].*)?$",
    re.IGNORECASE,
)


def _get_state_file_path() -> Path:
    return Path(app_info.appdata_path) / _STATE_FILE_NAME


def _get_download_dir_path() -> Path:
    return Path(app_info.appdata_path) / _DOWNLOAD_DIR_NAME


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically.

    The naive ``path.write_text(...)`` opens the destination file for
    writing and truncates it before the new bytes are flushed. If the
    process is killed (power loss, OOM kill, ``kill -9``, blue-screen)
    between the truncate and the flush, the destination file is left
    partially written or empty — which ``read_pending_install_state``
    then interprets as "no state file", silently dropping the install
    record and (much worse) preventing ``confirm_pending_install_result``
    from running its cleanup branch.

    The fix: write to a sibling temp file, fsync it, then ``os.replace``
    the temp file onto the destination. ``os.replace`` is atomic on
    POSIX (a single ``rename(2)`` syscall) and on Windows
    (``MoveFileEx`` with ``MOVEFILE_REPLACE_EXISTING``), so observers
    always see either the previous fully-written state file or the new
    fully-written one — never a torn half-written file.
    """
    path = Path(path)
    parent = path.parent
    safe_makedirs(parent, purpose="OTA state file")

    # ``delete=False`` + manual cleanup so a crash between temp-file
    # write and rename leaves a ``.partial`` file we can sweep on the
    # next startup rather than a phantom zero-byte state file.
    fd, tmp_name = None, None
    try:
        fd = os.open(
            str(parent / f".{path.name}.partial"),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,  # user-only on POSIX; harmless on Windows
        )
        try:
            os.write(fd, content.encode(encoding))
            os.fsync(fd)
        finally:
            os.close(fd)
            fd = None
        os.replace(str(parent / f".{path.name}.partial"), str(path))
    except Exception:
        # Best-effort cleanup of the temp file so we don't accumulate
        # half-written ghosts across many OTA flows.
        try:
            (parent / f".{path.name}.partial").unlink(missing_ok=True)
        except Exception:
            pass
        raise


def write_pending_install_state(target_version: str, package_path: str, logger=None, target_version_core: str = "") -> Path:
    state_path = _get_state_file_path()
    payload = {
        'target_version': str(target_version or '').strip(),
        'target_version_core': str(target_version_core or '').strip(),
        'package_path': str(package_path or '').strip(),
        'created_at': int(time.time()),
    }
    _atomic_write_text(
        state_path,
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
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
        # Don't leave a corrupt state file lying around — the next
        # OTA cycle would re-read it, hit the same JSON error, and
        # the user would see repeated warnings with no remediation.
        # Quarantine to ``.<name>.corrupt-<ts>`` for postmortem and
        # clear the active slot so the cleanup path can run.
        try:
            quarantine = state_path.with_name(
                f".{state_path.name}.corrupt-{int(time.time())}"
            )
            state_path.replace(quarantine)
            if logger:
                logger.warning(
                    f"[OTA] Corrupt state file quarantined to {quarantine} "
                    f"so subsequent reads return None and cleanup runs"
                )
        except Exception as move_err:
            if logger:
                logger.warning(
                    f"[OTA] Failed to quarantine corrupt state file "
                    f"{state_path}: {move_err}"
                )
            # Last resort: try to delete it outright.
            try:
                state_path.unlink(missing_ok=True)
            except Exception:
                pass
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
    package_path: Optional[Path] = Path(package_path_raw) if package_path_raw else None
    cleaned_count = 0
    cleaned_size = 0
    failed_count = 0
    if package_path is not None and not package_path.exists():
        if logger:
            logger.info(f"[OTA] Downloaded installer already absent, no cleanup needed: {package_path}")
        package_path = None  # nothing to unlink; treat like the unknown case below
    elif package_path is not None:
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
            # Pre-resolve so the "skip the package we just deleted" check
            # works even when the package_path no longer exists on disk
            # (``.resolve(strict=False)`` returns the canonical path
            # without requiring the file to be present).
            package_path_resolved: Optional[Path] = None
            if package_path is not None:
                try:
                    package_path_resolved = package_path.resolve(strict=False)
                except Exception:
                    package_path_resolved = None
            for child in download_dir.iterdir():
                if not child.is_file():
                    continue
                # Skip partial / quarantine files left by earlier crashes
                # — those are managed by the partial-file sweeper, not
                # the install cleanup. Deleting them here would mask the
                # original failure mode.
                if child.name.startswith("."):
                    continue
                # Skip the package we already deleted above. Compare by
                # resolved path so symlinks and ``..`` components don't
                # cause a false mismatch.
                if package_path_resolved is not None:
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
