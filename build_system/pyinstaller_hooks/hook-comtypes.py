"""
PyInstaller hook for comtypes - Windows only

comtypes is used for COM automation on Windows.
"""
import sys

# Only include comtypes on Windows
if sys.platform == 'win32':
    hiddenimports = [
        'comtypes',
        'comtypes.client',
        'comtypes.gen',
    ]
    print("[HOOK] Including comtypes for Windows")
else:
    hiddenimports = []
    print("[HOOK] Skipping comtypes (not Windows)")
