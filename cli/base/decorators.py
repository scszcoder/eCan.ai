#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Decorators - Reusable decorators for command groups.
"""

import functools
import click
from typing import Callable, Any


def group(name: str = None, **kwargs):
    """
    Decorator to create a command group with standard options.

    Adds common options:
    - --help/-h: Show help
    - --version/-v: Show version
    - --json/-j: Output as JSON
    - --quiet/-q: Quiet mode
    - --verbose/-V: Verbose mode
    """
    def decorator(f):
        @click.group(name=name, **kwargs)
        @click.option('--json', '-j', 'output_json', is_flag=True, help='Output as JSON')
        @click.option('--quiet', '-q', is_flag=True, help='Suppress non-error output')
        @click.option('--verbose', '-V', is_flag=True, help='Enable verbose output')
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


def command(name: str = None, **kwargs):
    """
    Decorator to create a command with standard options.

    Standard options:
    - --format/-f: Output format (table/json/yaml)
    - --no-color: Disable colors
    """
    def decorator(f):
        @click.command(name=name, **kwargs)
        @click.option('--format', '-f', type=click.Choice(['table', 'json', 'yaml', 'simple']),
                      default='table', help='Output format')
        @click.option('--no-color', is_flag=True, help='Disable color output')
        @click.pass_context
        @functools.wraps(f)
        def wrapper(ctx, *args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


def option(*args, **kwargs):
    """Alias for click.option with common defaults."""
    return click.option(*args, **kwargs)


def argument(*args, **kwargs):
    """Alias for click.argument with common defaults."""
    return click.argument(*args, **kwargs)


def requires_auth(f: Callable) -> Callable:
    """
    Decorator that requires authentication before executing command.

    Checks for valid session and exits with error if not authenticated.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        from .context import get_context
        ctx = get_context()
        ctx.require_auth()
        return f(*args, **kwargs)
    return wrapper


def requires_db(f: Callable) -> Callable:
    """
    Decorator that ensures database connection before executing command.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        from .context import get_context
        ctx = get_context()
        _ = ctx.db
        return f(*args, **kwargs)
    return wrapper


def handle_errors(f: Callable) -> Callable:
    """
    Decorator that handles common errors gracefully.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except KeyboardInterrupt:
            from .output import get_output
            get_output().warning("Operation cancelled")
        except Exception as e:
            from .output import get_output
            get_output().error(str(e))
            raise
    return wrapper


def log_action(action: str):
    """
    Decorator factory that logs command execution.

    Args:
        action: Action description (e.g., "Listing agents")
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            from .output import get_output
            out = get_output()
            out.info(f"{action}...")
            result = f(*args, **kwargs)
            return result
        return wrapper
    return decorator
