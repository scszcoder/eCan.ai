"""
PyInstaller hook for pywintypes package.

This hook ensures that pywintypes and related win32 modules are properly included
in the PyInstaller bundle on Windows platforms only.
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

print("[HOOK] pywintypes hook executing...")

# Only enable this hook on Windows to avoid introducing win32 modules on other platforms
if sys.platform.startswith('win'):
    print("[HOOK] Windows platform detected - collecting pywintypes modules")
    
    # Collect all pywintypes content
    datas, binaries, hiddenimports = collect_all('pywintypes')
    
    # Collect dynamic libraries
    pywintypes_libs = collect_dynamic_libs('pywintypes')
    binaries.extend(pywintypes_libs)
    
    # Add essential win32 modules that are commonly used
    win32_modules = [
        'win32api', 'win32con', 'win32file', 'win32pipe', 'win32process',
        'win32security', 'win32service', 'win32serviceutil', 'win32event',
        'win32evtlog', 'win32gui', 'win32clipboard', 'win32print',
    ]
    hiddenimports.extend(win32_modules)
    
    print(f"[HOOK] pywintypes hook completed:")
    print(f"  - Hidden imports: {len(hiddenimports)} modules")
    print(f"  - Data files: {len(datas)} files")
    print(f"  - Binary files: {len(binaries)} files")
else:
    # Non-Windows platforms: provide empty placeholders to avoid PyInstaller errors
    datas, binaries, hiddenimports = [], [], []
    print("[HOOK] Non-Windows platform - skipping pywintypes processing")
