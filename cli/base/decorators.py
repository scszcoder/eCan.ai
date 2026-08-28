#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Decorators - Reusable decorators for command groups.

Only ``requires_auth`` is used by the command modules. The previous
``group``/``command``/``option``/``argument``/``requires_db``/``handle_errors``/
``log_action`` helpers were dead scaffolding (never imported anywhere) — one
of them (``handle_errors``) also swallowed KeyboardInterrupt and returned
success — so they were removed.
"""

import functools
from typing import Callable


def requires_auth(f: Callable) -> Callable:
    """
    Decorator that requires authentication before executing command.

    Checks for a valid session and exits with an error if not authenticated.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        from .context import get_context
        ctx = get_context()
        ctx.require_auth()
        return f(*args, **kwargs)
    return wrapper
