"""
Browser Profile Lock Cleaner

Automatically detects and cleans up stale browser profile lock files
to prevent browser startup failures caused by previous abnormal exits.

Supports:
- macOS: SingletonLock, SingletonCookie, SingletonSocket (symlinks or files)
- Windows: SingletonLock, SingletonCookie, SingletonSocket (files)
- Linux: SingletonLock, SingletonCookie, SingletonSocket (symlinks or files)

These lock files are created by Chromium/Chrome browsers on all platforms
to prevent multiple instances from using the same profile directory.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"


# ── Live profile owners ─────────────────────────────────────────────────────
# The Singleton* files below are how Chromium locks a profile on macOS/Linux.
# On Windows there are none: the profile is held by an exclusively-open
# ``lockfile`` that disappears with the process, so a file check always says
# "not locked" -- even while a Chrome left behind by an app that exited (its
# parent is gone) still owns the profile. A new launch on that user-data-dir is
# then handed to the old instance and exits, the new debug port never opens,
# and browser-use times out after 30s on BrowserLaunchEvent. So also look for
# the owning process itself.

_CHROMIUM_EXE_HINTS = ("chrome", "chromium", "msedge")


def _norm_dir(p) -> str:
    return os.path.normcase(os.path.normpath(str(p).strip().strip('"')))


def _cmdline_user_data_dir(cmd: list) -> Optional[str]:
    for i, arg in enumerate(cmd):
        if arg.startswith("--user-data-dir="):
            return arg.split("=", 1)[1]
        if arg == "--user-data-dir" and i + 1 < len(cmd):
            return cmd[i + 1]
    return None


def find_profile_owner_processes(user_data_dir: str | Path | None) -> list:
    """Live Chromium *browser* processes (not their ``--type=`` children) whose
    ``--user-data-dir`` is this profile. Empty when psutil is unavailable."""
    if not user_data_dir:
        return []
    try:
        import psutil
    except Exception:
        return []
    target = _norm_dir(user_data_dir)
    owners = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if not any(h in name for h in _CHROMIUM_EXE_HINTS):
                continue
            cmd = proc.cmdline()
            if not cmd or any(a.startswith("--type=") for a in cmd):
                continue
            udd = _cmdline_user_data_dir(cmd)
            if udd and _norm_dir(udd) == target:
                owners.append(proc)
        except Exception:  # NoSuchProcess / AccessDenied / ZombieProcess
            continue
    return owners


def _is_orphan(proc) -> bool:
    """True when the process that launched this browser is gone (or its PID now
    belongs to a newer, unrelated process)."""
    import psutil
    try:
        parent = proc.parent()
        if parent is None:
            return True
        return parent.create_time() > proc.create_time()  # PID reused
    except psutil.NoSuchProcess:
        return True
    except Exception:
        return False


def reclaim_orphaned_profile(user_data_dir: str | Path | None) -> dict:
    """Kill orphaned Chromium instances holding this profile; report live ones.

    Only processes launched with exactly this ``--user-data-dir`` are touched,
    so a person's own Chrome (a different profile) is never affected."""
    result = {"orphans_killed": [], "live_owners": []}
    # A fingerprint browser outlives the app on purpose: the next start attaches
    # to it (fingerprint_browser, its debug port in .ecan_cdp.json). Its parent
    # is gone too, but it is not an orphan -- never kill it.
    try:
        if user_data_dir and (Path(user_data_dir) / ".ecan_cdp.json").is_file():
            return result
    except Exception:
        pass
    owners = find_profile_owner_processes(user_data_dir)
    if not owners:
        return result
    import psutil
    for proc in owners:
        if not _is_orphan(proc):
            result["live_owners"].append(proc.pid)
            logger.warning(
                f"[ProfileLockCleaner] ⚠️  Profile is in use by live browser pid={proc.pid} "
                f"(parent alive); a new launch on {user_data_dir} will fail until it exits")
            continue
        try:
            tree = proc.children(recursive=True) + [proc]
            for p in tree:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(tree, timeout=5)
            result["orphans_killed"].append(proc.pid)
            logger.info(
                f"[ProfileLockCleaner] 🧹 Killed orphaned browser pid={proc.pid} "
                f"({len(tree)} processes) that was holding {user_data_dir}")
        except Exception as e:
            logger.error(f"[ProfileLockCleaner] ❌ Failed to kill orphaned browser pid={proc.pid}: {e}")
    return result


def clean_browser_profile_locks(user_data_dir: str | Path | None) -> bool:
    """
    Clean stale lock files from browser profile directory.
    
    This prevents browser startup failures caused by:
    - SingletonLock: Prevents multiple browser instances using same profile
    - SingletonCookie: Session identifier
    - SingletonSocket: IPC socket for browser communication
    
    Args:
        user_data_dir: Path to browser profile directory
        
    Returns:
        True if locks were cleaned or no locks found, False on error
    """
    if not user_data_dir:
        logger.debug("[ProfileLockCleaner] No user_data_dir specified, skipping lock cleanup")
        return True
    
    try:
        profile_path = Path(user_data_dir)
        
        if not profile_path.exists():
            logger.debug(f"[ProfileLockCleaner] Profile directory does not exist yet: {profile_path}")
            return True

        # A live browser's locks are not stale: removing them lets a second
        # browser open the same profile and corrupt it.
        owners = find_profile_owner_processes(profile_path)
        if owners:
            logger.warning(f"[ProfileLockCleaner] ⚠️  Profile is in use by pid(s) "
                           f"{[p.pid for p in owners]}; its lock files were left in place")
            return False

        # Lock files to clean
        lock_files = [
            'SingletonLock',
            'SingletonCookie', 
            'SingletonSocket'
        ]
        
        cleaned_files = []
        for lock_file in lock_files:
            lock_path = profile_path / lock_file
            
            if lock_path.exists() or lock_path.is_symlink():
                try:
                    # Remove file or symlink
                    if lock_path.is_symlink() or lock_path.is_file():
                        lock_path.unlink()
                        cleaned_files.append(lock_file)
                        logger.info(f"[ProfileLockCleaner] ✅ Removed lock file: {lock_file}")
                    else:
                        logger.warning(f"[ProfileLockCleaner] ⚠️  {lock_file} is not a file/symlink, skipping")
                        
                except Exception as e:
                    logger.error(f"[ProfileLockCleaner] ❌ Failed to remove {lock_file}: {e}")
                    return False
        
        if cleaned_files:
            logger.info(f"[ProfileLockCleaner] 🧹 Cleaned {len(cleaned_files)} lock file(s): {', '.join(cleaned_files)}")
        else:
            logger.debug(f"[ProfileLockCleaner] ✅ No stale lock files found in {profile_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"[ProfileLockCleaner] ❌ Error cleaning profile locks: {e}")
        import traceback
        logger.debug(f"[ProfileLockCleaner] Traceback: {traceback.format_exc()}")
        return False


def check_profile_is_locked(user_data_dir: str | Path | None) -> bool:
    """
    Check if browser profile directory has active lock files.

    Args:
        user_data_dir: Path to browser profile directory

    Returns:
        True if profile is locked, False otherwise
    """
    if not user_data_dir:
        return False

    import time as _time
    try:
        profile_path = Path(user_data_dir)

        # Diagnostic: time each filesystem probe. On Windows, .exists() /
        # .is_symlink() against a SingletonLock held by a live Chrome can
        # block multiple seconds when AV or filesystem locks are contended.
        _t0 = _time.perf_counter()
        exists_root = profile_path.exists()
        _root_ms = (_time.perf_counter() - _t0) * 1000.0
        if _root_ms > 200.0:
            logger.warning(
                f"[ProfileLockCleaner][Perf] profile_path.exists() took {_root_ms:.0f} ms "
                f"({profile_path})"
            )
        if not exists_root:
            return False

        # Check for lock files
        lock_files = ['SingletonLock', 'SingletonCookie', 'SingletonSocket']

        for lock_file in lock_files:
            lock_path = profile_path / lock_file
            _t0 = _time.perf_counter()
            try:
                hit = lock_path.exists() or lock_path.is_symlink()
            finally:
                _dt_ms = (_time.perf_counter() - _t0) * 1000.0
                if _dt_ms > 200.0:
                    logger.warning(
                        f"[ProfileLockCleaner][Perf] stat on {lock_file} took {_dt_ms:.0f} ms "
                        f"({lock_path})"
                    )
            if hit:
                logger.debug(f"[ProfileLockCleaner] Found lock file: {lock_file}")
                return True

        return False

    except Exception as e:
        logger.debug(f"[ProfileLockCleaner] Error checking profile lock: {e}")
        return False


def get_lock_info(user_data_dir: str | Path | None) -> dict:
    """
    Get information about lock files in browser profile.
    
    Args:
        user_data_dir: Path to browser profile directory
        
    Returns:
        Dict with lock file information
    """
    info = {
        'is_locked': False,
        'lock_files': [],
        'profile_path': str(user_data_dir) if user_data_dir else None
    }
    
    if not user_data_dir:
        return info
    
    try:
        profile_path = Path(user_data_dir)
        
        if not profile_path.exists():
            return info
        
        lock_files = ['SingletonLock', 'SingletonCookie', 'SingletonSocket']
        
        for lock_file in lock_files:
            lock_path = profile_path / lock_file
            if lock_path.exists() or lock_path.is_symlink():
                info['lock_files'].append({
                    'name': lock_file,
                    'path': str(lock_path),
                    'is_symlink': lock_path.is_symlink(),
                    'target': str(lock_path.readlink()) if lock_path.is_symlink() else None
                })
        
        info['is_locked'] = len(info['lock_files']) > 0
        
    except Exception as e:
        logger.debug(f"[ProfileLockCleaner] Error getting lock info: {e}")
    
    return info


def ensure_profile_unlocked(user_data_dir: str | Path | None, auto_clean: bool = True) -> bool:
    """
    Ensure browser profile is unlocked and ready for use.
    
    Args:
        user_data_dir: Path to browser profile directory
        auto_clean: Automatically clean locks if found
        
    Returns:
        True if profile is ready (unlocked or cleaned), False otherwise
    """
    if not user_data_dir:
        return True

    try:
        # A browser left behind by an exited app owns the profile even though
        # (on Windows) no lock file says so -- reclaim it first.
        if auto_clean:
            reclaimed = reclaim_orphaned_profile(user_data_dir)
            if reclaimed["live_owners"]:
                return False

        # Check if locked
        is_locked = check_profile_is_locked(user_data_dir)
        
        if not is_locked:
            logger.debug(f"[ProfileLockCleaner] ✅ Profile is not locked: {user_data_dir}")
            return True
        
        # Get lock info for logging
        lock_info = get_lock_info(user_data_dir)
        logger.warning(f"[ProfileLockCleaner] ⚠️  Profile is locked with {len(lock_info['lock_files'])} lock file(s)")
        
        if auto_clean:
            logger.info(f"[ProfileLockCleaner] 🔧 Auto-cleaning lock files...")
            return clean_browser_profile_locks(user_data_dir)
        else:
            logger.warning(f"[ProfileLockCleaner] ⚠️  Auto-clean disabled, profile remains locked")
            return False
            
    except Exception as e:
        logger.error(f"[ProfileLockCleaner] ❌ Error ensuring profile unlocked: {e}")
        return False
