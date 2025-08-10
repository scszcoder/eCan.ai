# -*- coding: utf-8 -*-
"""
Generic hook for the top-level 'lightrag' package.
Ensures required lightrag.api submodules are bundled even if only 'lightrag' is
statically imported in the app code.
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# Explicit essentials used at runtime
hiddenimports = [
    'lightrag.api',
    'lightrag.api.lightrag_server',
    'lightrag.api.utils_api',
    'lightrag.api.auth',
    'lightrag.api.config',
]

# Collect all routers submodules
hiddenimports += collect_submodules('lightrag.api.routers')

# Collect data files used by lightrag (schemas/templates/static/etc.)
datas = []
try:
    datas += collect_data_files('lightrag', include_py_files=False)
except Exception:
    pass

# Collect dynamic libraries for FAISS if lightrag depends on it
binaries = []
try:
    binaries += collect_dynamic_libs('faiss')
except Exception:
    pass


def pre_safe_import_module(api):
    """Sanitize argv to avoid argparse side-effects in isolated child processes."""
    import sys
    try:
        if hasattr(sys, 'argv') and isinstance(sys.argv, list) and len(sys.argv) > 1:
            sys.argv[:] = sys.argv[:1]
    except Exception:
        pass

