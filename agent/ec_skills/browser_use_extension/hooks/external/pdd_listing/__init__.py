"""pdd_listing: the ``pdd_confirm_listing`` browser action (see ``site_tools``).

Actions only, no hooks; ``hook.yaml`` declares the per-listing meters. Importing
the package registers the action on the shared controller.
"""

try:
    from . import site_tools  # noqa: F401 -- registers the action
except Exception as _exc:  # a broken optional bundle must never stop the app
    try:
        from utils.logger_helper import logger_helper as logger
        logger.warning(f"[pdd_listing] not registered: {_exc}")
    except Exception:
        pass
