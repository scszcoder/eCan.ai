"""
Logging helper for ecan_ai.db package.

This module provides a logger that works both when the package is used
standalone and when it's used within the full eCan.ai application.
"""

import logging

# Try to import the eCan.ai logger, fall back to standard logging
try:
    from utils.logger_helper import logger_helper as logger
except ImportError:
    # Create a basic logger when utils.logger_helper is not available
    logger = logging.getLogger("ecan_ai.db")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

__all__ = ['logger']
