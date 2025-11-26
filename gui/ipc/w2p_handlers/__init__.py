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
    import sys
    from utils.logger_helper import logger_helper as logger
    
    # Explicitly import embedding_handler to ensure it's loaded
    try:
        from . import embedding_handler  # noqa: F401
    except Exception as e:
        import traceback
        logger.error(f"Failed to import embedding_handler: {e}")
        logger.debug(traceback.format_exc())
    
    # Explicitly import rerank_handler to ensure it's loaded
    try:
        from . import rerank_handler  # noqa: F401
    except Exception as e:
        import traceback
        logger.error(f"Failed to import rerank_handler: {e}")
        logger.debug(traceback.format_exc())
    
    for loader, name, is_pkg in pkgutil.walk_packages(__path__):
        try:
            # Skip __init__ and already imported modules
            if name == '__init__':
                continue
            module_name = f'{__name__}.{name}'
            if module_name in sys.modules:
                continue
            importlib.import_module('.' + name, __name__)
        except Exception as e:
            logger.warning(f"Failed to import handler module {name}: {e}")
            pass
