# Pre-safe import hook for lightrag.api
# Prevent argparse in lightrag.api submodules from parsing PyInstaller isolated child args
import sys
try:
    if hasattr(sys, 'argv') and isinstance(sys.argv, list) and len(sys.argv) > 1:
        sys.argv[:] = sys.argv[:1]
except Exception:
    pass

