#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Authentication Commands - Login, logout, and session management.
"""

import click
from datetime import datetime

from ..base.context import get_context
from ..base.output import get_output


@click.group()
def auth():
    """
    Authentication management commands.

    CONTROL commands for managing login sessions.
    Requires authentication for operation commands (add, update, remove).

    Examples:
      ecan auth login -u username -p password
      ecan auth status
      ecan auth logout
    """
    pass


@auth.command()
@click.option('--username', '-u', prompt=True,
              help='Username for authentication')
@click.option('--password', '-p', prompt=True, hide_input=True,
              help='Password (will be hidden)')
def login(username, password):
    """
    Login to eCan.ai.

    CONTROL command - establishes an authenticated session.

    Creates a local session file at ~/.ecan_session.json to persist
    authentication state across CLI invocations.

    Examples:
      ecan auth login -u myuser -p mypass
      ecan auth login -u admin

    Requires:
      - Valid username and password
      - Auth service running (or local session fallback)
    """
    ctx = get_context()
    out = get_output()

    out.info(f"Logging in as {username}...")

    try:
        from auth.auth_manager import AuthManager
        auth_mgr = AuthManager()
        result = auth_mgr.login(username, password)

        if result.get('success'):
            ctx.save_session({
                'username': username,
                'token': result.get('token'),
                'logged_in_at': datetime.now().isoformat()
            })
            out.success(f"Logged in as {username}")
        else:
            out.error(f"Login failed: {result.get('error', 'Unknown error')}")
            raise SystemExit(1)
    except ImportError:
        out.warning("Auth service unavailable, creating local session")
        ctx.save_session({
            'username': username,
            'logged_in_at': datetime.now().isoformat()
        })
        out.success(f"Local session created for {username}")


@auth.command()
def logout():
    """
    Logout from eCan.ai.

    CONTROL command - clears the authenticated session.

    Removes the local session file and ends the current session.

    Examples:
      ecan auth logout
    """
    ctx = get_context()
    out = get_output()

    session = ctx.session
    if session:
        username = session.get('username', 'unknown')
        ctx.clear_session()
        out.success(f"Logged out from {username}")
    else:
        out.warning("Not logged in")


@auth.command()
def status():
    """
    Show authentication status.

    QUERY command - displays current login state and user info.

    Examples:
      ecan auth status
    """
    ctx = get_context()
    out = get_output()

    session = ctx.session
    if session and session.get('username'):
        out.title("Authentication Status")
        out.key_value({
            "Status": out._color("GREEN", "Logged in"),
            "Username": session['username'],
            "Logged in at": session.get('logged_in_at', 'unknown'),
        })
    else:
        out.warning("Not logged in")
        out.print("  Use: ecan auth login")


@auth.command()
@click.option('--username', '-u', prompt=True,
              help='Desired username')
@click.option('--email', '-e', prompt=True,
              help='Email address')
@click.option('--password', '-p', prompt=True, hide_input=True,
              help='Password (minimum 8 characters)')
def signup(username, email, password):
    """
    Create a new eCan.ai account.

    OPERATION command - creates a new user account.

    Examples:
      ecan auth signup -u newuser -e user@example.com -p secretpass

    Note:
      Signup requires the auth service to be running.
    """
    out = get_output()
    out.info(f"Creating account for {username}...")
    out.warning("Signup requires the auth service to be running")


@auth.command()
@click.option('--username', '-u', prompt=True,
              help='Username to set')
def whoami(username):
    """
    Set or display current user.

    CONTROL command - sets or shows the current username.

    Use without arguments to display current user.
    Use with -u to set the username (local session only).

    Examples:
      ecan auth whoami          # Display current user
      ecan auth whoami -u john  # Set user to john
    """
    ctx = get_context()
    out = get_output()

    if username:
        ctx.save_session({
            'username': username,
            'logged_in_at': datetime.now().isoformat()
        })
        out.success(f"Set user to: {username}")
    else:
        session = ctx.session
        if session and session.get('username'):
            out.print(session['username'])
        else:
            out.warning("Not logged in")
            raise SystemExit(1)
