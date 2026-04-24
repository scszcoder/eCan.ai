"""
External hook bundles.

Each subdirectory is a self-contained hook bundle loaded by
``hook_loader.load_bundle``.  The reference implementation lives in
``feige_chat/`` — a customer wanting to mirror that for a new site can
copy-paste the directory and edit the manifest + selectors.

Bundles are NOT imported eagerly.  Importing this package does nothing;
the loader reads ``hook.yaml`` first, then side-loads the entrypoint.
"""
