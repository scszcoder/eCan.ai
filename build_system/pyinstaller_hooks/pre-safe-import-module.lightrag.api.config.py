# Pre-safe import hook for lightrag.api.config
# Purpose: prevent argparse in lightrag.api.config from reading PyInstaller child process args
# Context: executed by PyInstaller before importing lightrag.api.config during Analysis
import sys

# Narrowly sanitize argv to avoid side effects during module import
# This runs only when lightrag.api.config is imported, after PyInstaller _child has parsed its own args.
try:
    if hasattr(sys, 'argv') and len(sys.argv) > 1:
        sys.argv = [sys.argv[0]]
except Exception:
    pass

