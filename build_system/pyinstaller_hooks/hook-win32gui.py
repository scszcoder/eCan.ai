"""
PyInstaller hook for Windows GUI modules - Windows only

win32gui, win32api, etc. are Windows-specific modules.
"""
import sys

# Only include win32 modules on Windows
if sys.platform == 'win32':
    hiddenimports = [
        'win32gui',
        'win32api',
        'win32con',
        'win32process',
        'pywintypes',
    ]
    print("[HOOK] Including win32 modules for Windows")
else:
    hiddenimports = []
    print("[HOOK] Skipping win32 modules (not Windows)")
