"""
PyInstaller hook for pywifi - Windows only

pywifi is used for WiFi scanning on Windows.
On other platforms (macOS, Linux), native APIs are used instead.
"""
import sys

# Only include pywifi modules on Windows
if sys.platform == 'win32':
    hiddenimports = [
        'pywifi',
        'pywifi.const',
        'pywifi.ifaces',
    ]
    print("[HOOK] Including pywifi for Windows")
else:
    hiddenimports = []
    print("[HOOK] Skipping pywifi (not Windows)")
