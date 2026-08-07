"""
External hook bundles.

Each subdirectory is a self-contained hook bundle.  The in-tree
live-chat bundle is the reference implementation — a third-party author
wanting to add a new site can copy-paste its directory and edit the
registration calls / selectors / manifest.

Two hook systems consume this tree (see ``docs/HOOK_BUNDLES.md`` and
``docs/BUILD_NODE_LIFECYCLE_HOOKS.md`` for the full picture):

1. **Lifecycle hooks** (``build_node.py`` early / prompt-build / late
   phases).  Every subpackage under this directory is auto-imported at
   process start by ``build_node._discover_external_hook_bundles``; its
   ``__init__.py`` is expected to call the ``register_before_*_hook``
   APIs exported by ``build_node``.  Drop a folder in → registered on
   next start, no edits to ``build_node.py`` required.  A bundle whose
   import raises is logged and skipped; other bundles still load.

2. **HookDispatcher** (manifest-driven, inside the browser-use agent
   loop).  That loader reads ``hook.yaml`` explicitly via
   ``hook_loader.load_bundle`` and does NOT rely on eager import.

A single bundle may participate in both systems (the reference live-chat
bundle does).
Importing this package itself is a no-op; the lifecycle auto-discovery
is performed by ``build_node``.
"""
