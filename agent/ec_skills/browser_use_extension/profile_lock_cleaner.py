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
