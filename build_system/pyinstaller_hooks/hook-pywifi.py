"""
PyInstaller hook for pywifi - Windows only

pywifi is used for WiFi scanning on Windows.
On other platforms (macOS, Linux), native APIs are used instead.
"""
import sys

# Only include pywifi modules on Windows AND only when it is actually installed.
# pywifi has no release for Python >=3.12, so on a 3.12 build it is absent and the
# runtime falls back gracefully (hardware_detector.py skips the WiFi scan). Guard
# the hidden imports on importability so PyInstaller doesn't warn/fail on a missing
# module it was told to bundle.
if sys.platform == 'win32':
    import importlib.util
    if importlib.util.find_spec('pywifi') is not None:
        hiddenimports = [
            'pywifi',
            'pywifi.const',
            'pywifi.ifaces',
        ]
        print("[HOOK] Including pywifi for Windows")
    else:
        hiddenimports = []
        print("[HOOK] Skipping pywifi (not installed — e.g. Python >=3.12)")
else:
    hiddenimports = []
    print("[HOOK] Skipping pywifi (not Windows)")
