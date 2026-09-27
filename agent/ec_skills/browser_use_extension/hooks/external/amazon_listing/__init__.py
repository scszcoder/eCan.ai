"""Amazon Seller Central listing actions (Add Products via Upload).

Actions only -- no hooks, no hook.yaml. Importing the package registers the
``amazon_*`` controller actions (see ``site_tools``); the spreadsheet half is
the ``amazon_template_*`` / ``amazon_parse_feedback`` MCP tools.
"""

_REGISTERED = False


def register() -> bool:
    """Register the controller actions. Idempotent."""
    global _REGISTERED
    if not _REGISTERED:
        from . import site_tools  # noqa: F401 -- registers the amazon_* actions
        _REGISTERED = True
    return True


try:
    register()
except Exception as _exc:  # a broken optional bundle must never stop the app
    try:
        from utils.logger_helper import logger_helper as logger
        logger.warning(f"[amazon_listing] not registered: {_exc}")
    except Exception:
        pass
