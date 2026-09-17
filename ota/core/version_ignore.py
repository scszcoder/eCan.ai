"""
OTA Version Ignore Manager
Manages versions that users choose to ignore ("Don't remind me again")

The on-disk format is JSON. Both the load and save paths are hardened
against the two failure modes that bit us in ``install_state.py``:

  * **Atomic write**: ``_save`` writes to a sibling ``.partial`` file,
    fsyncs it, then ``os.replace``s onto the destination. A power
    loss / OOM kill / blue-screen between truncate and flush leaves a
    ``.partial`` ghost we can sweep on the next load — not a half-
    written ``ota_ignored_versions.json`` that loses the user's
    ignored list.
  * **Corrupt-file quarantine**: ``_load`` moves a JSON-broken file to
    ``.ota_ignored_versions.json.corrupt-<ts>`` and starts fresh.
    Without this, a corrupt file would fail JSON parsing on EVERY
    startup and the user's ignored list would never recover until
    they manually deleted the file.

We share the implementation with ``ota.core.install_state._atomic_write_text``
by importing it (it lives in the same package and is the single
canonical atomic-write helper for OTA state files).
"""

import json
import threading
import time
from pathlib import Path
from typing import Optional, Set

from utils.logger_helper import logger_helper as logger
from .installer import safe_makedirs
# Reuse the OTA canonical atomic write so a future refactor only has
# to touch one place. If install_state ever splits the helper out into
# ``ota.core.atomic_io`` we'll re-import from there.
from .install_state import _atomic_write_text


class VersionIgnoreManager:
    """Manages ignored OTA versions"""

    def __init__(self, config_dir: str = None):
        """Initialize version ignore manager

        Args:
            config_dir: Configuration directory, defaults to user data directory
        """
        if config_dir is None:
            from config.envi import getECBotDataHome
            config_dir = getECBotDataHome()

        self.config_file = Path(config_dir) / "ota_ignored_versions.json"
        self.ignored_versions: Set[str] = set()
        self._load()

    def _load(self):
        """Load ignored version list from file. Corrupt files are quarantined."""
        if not self.config_file.exists():
            logger.info("[OTA] No ignored versions file found, starting fresh")
            return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.ignored_versions = set(data.get('ignored_versions', []) or [])
            logger.info(f"[OTA] Loaded {len(self.ignored_versions)} ignored versions")
        except Exception as e:
            logger.error(f"[OTA] Failed to load ignored versions: {e}")
            self.ignored_versions = set()
            # Mirror the install_state quarantine pattern so a corrupt
            # file doesn't keep failing JSON parsing on every startup
            # and the user is silently losing their ignore list.
            try:
                quarantine = self.config_file.with_name(
                    f".{self.config_file.name}.corrupt-{int(time.time())}"
                )
                self.config_file.replace(quarantine)
                logger.warning(
                    f"[OTA] Corrupt ignored-versions file quarantined to {quarantine}"
                )
            except Exception as move_err:
                logger.warning(
                    f"[OTA] Failed to quarantine corrupt ignored-versions "
                    f"file {self.config_file}: {move_err}"
                )
                try:
                    self.config_file.unlink(missing_ok=True)
                except Exception:
                    pass

    def _save(self):
        """Save ignored version list to file atomically."""
        try:
            safe_makedirs(self.config_file.parent, purpose="OTA ignored versions")
            content = json.dumps(
                {'ignored_versions': sorted(self.ignored_versions)},
                indent=2,
                ensure_ascii=False,
            )
            _atomic_write_text(self.config_file, content, encoding="utf-8")
            logger.info(f"[OTA] Saved {len(self.ignored_versions)} ignored versions")
        except RuntimeError as e:
            # safe_makedirs already produced an actionable message —
            # surface it and propagate so the GUI can decide whether
            # to retry vs. ignore.
            logger.error(f"[OTA] {e}")
            raise
        except Exception as e:
            logger.error(f"[OTA] Failed to save ignored versions: {e}")

    def ignore_version(self, version: str):
        """Add version to ignore list

        Args:
            version: Version number to ignore
        """
        if version and version not in self.ignored_versions:
            self.ignored_versions.add(version)
            self._save()
            logger.info(f"[OTA] Version {version} added to ignore list")

    def unignore_version(self, version: str):
        """Remove version from ignore list

        Args:
            version: Version number to remove
        """
        if version in self.ignored_versions:
            self.ignored_versions.remove(version)
            self._save()
            logger.info(f"[OTA] Version {version} removed from ignore list")

    def is_ignored(self, version: str) -> bool:
        """Check if version is ignored

        Args:
            version: Version number to check

        Returns:
            True if version is ignored, False otherwise
        """
        return version in self.ignored_versions

    def clear_all(self):
        """Clear all ignored versions"""
        self.ignored_versions.clear()
        self._save()
        logger.info("[OTA] Cleared all ignored versions")

    def get_ignored_versions(self) -> list:
        """Get list of all ignored versions

        Returns:
            List of ignored versions
        """
        return sorted(list(self.ignored_versions))


# Global singleton — protected by a lock so concurrent calls from the
# auto-check thread + the GUI thread can't end up with two managers
# (each writing to the same file from different in-memory states would
# silently lose the other's writes).
_version_ignore_manager: Optional[VersionIgnoreManager] = None
_version_ignore_lock = threading.Lock()


def get_version_ignore_manager() -> VersionIgnoreManager:
    """Get global version ignore manager singleton (thread-safe).

    Returns:
        VersionIgnoreManager instance
    """
    global _version_ignore_manager
    # Double-checked locking: the fast path is unlocked (after init),
    # the slow path takes the lock.
    if _version_ignore_manager is not None:
        return _version_ignore_manager
    with _version_ignore_lock:
        if _version_ignore_manager is None:
            _version_ignore_manager = VersionIgnoreManager()
    return _version_ignore_manager
