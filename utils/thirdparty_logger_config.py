#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Third-party Package Logger Unified Configuration
Redirects logs from third-party packages (e.g., browser_use) to the project's unified logger
"""

import logging
from utils.logger_helper import logger_helper as logger


def configure_browser_use_logger():
    """
    Configure the browser_use package logging system to use the project's unified logger
    
    How it works:
    1. Get all browser_use related loggers
    2. Clear their default handlers
    3. Add a custom handler that forwards logs to logger_helper
    """
    
    # Get browser_use related loggers
    browser_use_logger_names = [
        'browser_use',
        'browser_use.agent',
        'browser_use.agent.service',
        'browser_use.controller',
        'browser_use.browser',
        'browser_use.dom',
    ]
    
    # Create a custom handler that forwards logs to logger_helper
    class LoggerHelperHandler(logging.Handler):
        """Custom Handler that forwards logs to logger_helper"""
        
        def emit(self, record):
            """Forward log records"""
            try:
                # Format message
                msg = self.format(record)
                
                # Forward to logger_helper based on log level
                if record.levelno >= logging.CRITICAL:
                    logger.critical(msg)
                elif record.levelno >= logging.ERROR:
                    logger.error(msg)
                elif record.levelno >= logging.WARNING:
                    logger.warning(msg)
                elif record.levelno >= logging.INFO:
                    logger.info(msg)
                else:
                    logger.debug(msg)
                    
            except Exception:
                self.handleError(record)
    
    # Configure each logger
    for logger_name in browser_use_logger_names:
        third_party_logger = logging.getLogger(logger_name)
        
        # Clear existing handlers
        third_party_logger.handlers.clear()
        
        # Add custom handler
        handler = LoggerHelperHandler()
        handler.setLevel(logging.DEBUG)
        
        # Set format (optional, as logger_helper will reformat)
        formatter = logging.Formatter('[browser_use] %(message)s')
        handler.setFormatter(formatter)
        
        third_party_logger.addHandler(handler)
        
        # Set log level
        third_party_logger.setLevel(logging.DEBUG)
        
        # Don't propagate to parent logger (avoid duplication)
        third_party_logger.propagate = False
        
        logger.debug(f"✅ Configured logger: {logger_name}")


def configure_all_thirdparty_loggers():
    """Configure all third-party package loggers"""
    logger.info("🔧 Configuring third-party loggers...")
    
    # Configure browser_use
    try:
        configure_browser_use_logger()
        logger.info("✅ browser_use logger configured")
    except Exception as e:
        logger.warning(f"Failed to configure browser_use logger: {e}")
    
    # Add other third-party package configurations here
    # configure_other_package_logger()
    
    logger.info("✅ Third-party loggers configured")


def reset_thirdparty_loggers():
    """Reset third-party package logger configurations (for testing or reconfiguration)"""
    logger.info("🔄 Resetting third-party loggers...")
    
    # Reset browser_use
    browser_use_logger_names = [
        'browser_use',
        'browser_use.agent',
        'browser_use.agent.service',
        'browser_use.controller',
        'browser_use.browser',
        'browser_use.dom',
    ]
    
    for logger_name in browser_use_logger_names:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.handlers.clear()
        third_party_logger.setLevel(logging.NOTSET)
        third_party_logger.propagate = True
    
    logger.info("✅ Third-party loggers reset")


# Auto-configure (on module import)
# Note: Comment out this line if you don't want auto-configuration
# configure_all_thirdparty_loggers()

