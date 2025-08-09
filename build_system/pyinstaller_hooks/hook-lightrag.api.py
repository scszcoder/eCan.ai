# -*- coding: utf-8 -*-
# Minimal set of submodules needed at runtime, avoid collect_submodules to prevent heavy imports.
hiddenimports = [
    'lightrag.api.lightrag_server',
    'lightrag.api.routers',
    'lightrag.api.routers.document_routes',
    'lightrag.api.routers.query_routes',
    'lightrag.api.routers.graph_routes',
    'lightrag.api.routers.ollama_api',
    'lightrag.api.utils_api',
    'lightrag.api.auth',
    'lightrag.api.config',
]



# Sanitize argv before importing lightrag.api in PyInstaller isolated child
# This prevents lightrag.api.config from parsing PyInstaller's own args

def pre_safe_import_module(api):
    import sys
    try:
        if hasattr(sys, 'argv') and isinstance(sys.argv, list) and len(sys.argv) > 1:
            # keep only script name to avoid unrecognized arguments
            sys.argv[:] = sys.argv[:1]
    except Exception:
        pass
