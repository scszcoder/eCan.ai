"""eBay listing browser actions (API path: connect the seller account).

Actions only -- no hooks, no hook.yaml. Importing the package registers the
``ebay_*`` controller actions (see ``site_tools``). The listing work itself is
the ``ebay_*`` MCP tools; the no-API Seller Hub flows are prompt-driven.
"""

_REGISTERED = False


def register() -> bool:
    """Register the controller actions. Idempotent."""
    global _REGISTERED
    if not _REGISTERED:
        from . import site_tools  # noqa: F401 -- registers the ebay_* actions
        _REGISTERED = True
    return True


try:
    register()
except Exception as _exc:  # a broken optional bundle must never stop the app
    try:
        from utils.logger_helper import logger_helper as logger
        logger.warning(f"[ebay_listing] not registered: {_exc}")
    except Exception:
        pass
