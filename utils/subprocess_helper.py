#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subprocess Helper Utilities

This module provides cross-platform subprocess utilities with proper
Windows console window hiding for PyInstaller frozen environments.

Key Features:
- Automatic console window hiding in Windows frozen environment
- Cross-platform compatibility (Windows, macOS, Linux)
- Easy-to-use wrapper functions
- Prevents window flashing/popup in packaged applications

Usage:
    from utils.subprocess_helper import popen_no_window, get_subprocess_kwargs
    
    # Method 1: Use popen_no_window wrapper
    proc = popen_no_window(['python', 'script.py'], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
    
    # Method 2: Use get_subprocess_kwargs for subprocess.run
    kwargs = get_subprocess_kwargs({
        'capture_output': True,
        'timeout': 60
    })
    result = subprocess.run(['pip', 'install', 'package'], **kwargs)
"""

import subprocess
import sys
from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    # For type checking only - subprocess.STARTUPINFO only exists on Windows
    if sys.platform == 'win32':
        from subprocess import STARTUPINFO
    else:
        STARTUPINFO = Any

# Detect if running in PyInstaller packaged environment
IS_FROZEN = getattr(sys, 'frozen', False)


def get_subprocess_creation_flags() -> Tuple[int, Optional[Any]]:
    """Get subprocess creation flags with proper Windows console hiding.
    
    This function returns appropriate flags to prevent console window
    popup/flashing when running subprocess in PyInstaller frozen environment
    on Windows.
    
    Returns:
        tuple: (creation_flags, startupinfo)
            - creation_flags: int, flags for subprocess creation (0 on non-Windows)
            - startupinfo: STARTUPINFO object or None
    
    Platform Behavior:
        - Windows (Frozen): Multiple flags to completely hide console window
        - Windows (Dev): Basic flags for process management
        - macOS/Linux: No flags needed (returns 0, None)
    """
    if sys.platform != "win32":
        return 0, None
    
    creation_flags = 0
    startupinfo = None
    
    # Always create new process group for better process management
    if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
        creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    
    # DETACHED_PROCESS - process not attached to parent console
    # This is the traditional flag, but not sufficient in frozen environment
    DETACHED_PROCESS = 0x00000008
    creation_flags |= DETACHED_PROCESS
    
    # In frozen environment, add additional flags to completely hide window
    # NOTE: For consistency with development runs, we now apply these flags
    # whenever available on Windows, not only when IS_FROZEN is True.
    # CREATE_NO_WINDOW - prevents console window creation (Windows 10+)
    # This is the most effective flag for preventing window popup
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
        creation_flags |= subprocess.CREATE_NO_WINDOW
    
    # STARTF_USESHOWWINDOW - hide window (compatible with older Windows)
    # This provides backward compatibility
    if hasattr(subprocess, 'STARTF_USESHOWWINDOW'):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
    
    return creation_flags, startupinfo


def get_subprocess_kwargs(base_kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get subprocess kwargs with proper Windows console hiding for frozen environment.
    
    This function takes base subprocess kwargs and adds Windows-specific flags
    to prevent console window popup in PyInstaller frozen environment.
    
    Args:
        base_kwargs: Base kwargs dict to extend (optional)
            Example: {'capture_output': True, 'timeout': 60, 'encoding': 'utf-8'}
    
    Returns:
        Dict with subprocess kwargs including Windows-specific flags if needed
    
    Example:
        >>> base_kwargs = {
        ...     'timeout': 300,
        ...     'capture_output': True,
        ...     'text': True,
        ...     'encoding': 'utf-8',
        ... }
        >>> kwargs = get_subprocess_kwargs(base_kwargs)
        >>> result = subprocess.run(['pip', 'install', 'package'], **kwargs)
    """
    kwargs = base_kwargs.copy() if base_kwargs else {}
    
    if sys.platform == "win32":
        creation_flags, startupinfo = get_subprocess_creation_flags()
        
        # Merge creation flags if user provided some
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creation_flags
        else:
            kwargs['creationflags'] = creation_flags
        
        # Set startupinfo if we have one
        if startupinfo is not None:
            kwargs['startupinfo'] = startupinfo
    
    return kwargs


def popen_no_window(cmd, **kwargs) -> subprocess.Popen:
    """Create subprocess.Popen without console window on Windows.
    
    This is a drop-in replacement for subprocess.Popen that automatically
    handles console window hiding in PyInstaller frozen environment on Windows.
    
    Args:
        cmd: Command to execute (list or string)
        **kwargs: Additional arguments for Popen (same as subprocess.Popen)
    
    Returns:
        subprocess.Popen instance
    
    Example:
        >>> # Instead of:
        >>> # proc = subprocess.Popen(['python', 'script.py'], stdout=subprocess.PIPE)
        >>> 
        >>> # Use:
        >>> proc = popen_no_window(['python', 'script.py'], stdout=subprocess.PIPE)
        >>> 
        >>> # The console window won't popup in frozen environment
    
    Note:
        On macOS and Linux, this function behaves exactly like subprocess.Popen
        since console window hiding is only needed on Windows.
    """
    if sys.platform == "win32":
        creation_flags, startupinfo = get_subprocess_creation_flags()
        
        # Merge creation flags if user provided some
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creation_flags
        else:
            kwargs['creationflags'] = creation_flags
        
        # Set startupinfo if we have one
        if startupinfo is not None:
            kwargs['startupinfo'] = startupinfo
    
    return subprocess.Popen(cmd, **kwargs)


def run_no_window(cmd, **kwargs) -> subprocess.CompletedProcess:
    """Run subprocess without console window on Windows.
    
    This is a drop-in replacement for subprocess.run that automatically
    handles console window hiding in PyInstaller frozen environment on Windows.
    
    Args:
        cmd: Command to execute (list or string)
        **kwargs: Additional arguments for run (same as subprocess.run)
    
    Returns:
        subprocess.CompletedProcess instance
    
    Example:
        >>> # Instead of:
        >>> # result = subprocess.run(['pip', 'install', 'package'], capture_output=True)
        >>> 
        >>> # Use:
        >>> result = run_no_window(['pip', 'install', 'package'], capture_output=True)
        >>> 
        >>> # The console window won't popup in frozen environment
    """
    kwargs = get_subprocess_kwargs(kwargs)
    return subprocess.run(cmd, **kwargs)


# For backward compatibility with legacy code
def get_windows_creation_flags() -> int:
    """Legacy function for backward compatibility.
    
    Returns only creation flags without startupinfo.
    Use get_subprocess_creation_flags() for complete solution.
    
    Returns:
        int: Windows creation flags
    """
    creation_flags, _ = get_subprocess_creation_flags()
    return creation_flags


if __name__ == "__main__":
    # Self-test
    print("=" * 60)
    print("Subprocess Helper Self-Test")
    print("=" * 60)
    print(f"Platform: {sys.platform}")
    print(f"Frozen: {IS_FROZEN}")
    
    creation_flags, startupinfo = get_subprocess_creation_flags()
    print(f"\nCreation flags: 0x{creation_flags:08X}")
    print(f"Startupinfo: {startupinfo}")
    
    if sys.platform == "win32":
        print("\nFlags breakdown:")
        if creation_flags & 0x00000008:
            print("  ✓ DETACHED_PROCESS (0x00000008)")
        if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') and (creation_flags & subprocess.CREATE_NEW_PROCESS_GROUP):
            print(f"  ✓ CREATE_NEW_PROCESS_GROUP (0x{subprocess.CREATE_NEW_PROCESS_GROUP:08X})")
        if hasattr(subprocess, 'CREATE_NO_WINDOW') and (creation_flags & subprocess.CREATE_NO_WINDOW):
            print(f"  ✓ CREATE_NO_WINDOW (0x{subprocess.CREATE_NO_WINDOW:08X})")
        if startupinfo:
            print("  ✓ STARTF_USESHOWWINDOW with SW_HIDE")
    
    print("\n" + "=" * 60)
    print("Test completed. Import this module to use its functions.")
    print("=" * 60)
