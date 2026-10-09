"""Logger for the Knowledge Service: the app's logger inside eCan, standard
logging when KS runs as a stand-alone server (no desktop app packages)."""
try:
    from utils.logger_helper import logger_helper as logger  # noqa: F401
except Exception:  # pragma: no cover - stand-alone server image
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("ecan.ks")
