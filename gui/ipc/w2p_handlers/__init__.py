# NOTE: Handlers are now imported lazily on-demand to improve startup performance
# Previously, all handlers were imported at module load time, causing ~10 second delay
# Now handlers are imported only when first accessed

# Import only essential handlers that are needed immediately
try:
    from . import user_handler  # noqa: F401 - Login/auth handlers
    from . import settings_handler  # noqa: F401 - Settings handlers
except Exception:
    pass

# Lazy import function for other handlers
def _ensure_handlers_loaded():
    """Lazy load all handlers when first needed"""
    import pkgutil
    import importlib
    
    for loader, name, is_pkg in pkgutil.walk_packages(__path__):
        try:
            importlib.import_module('.' + name, __name__)
        except Exception:
            pass
