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

