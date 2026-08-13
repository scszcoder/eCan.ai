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
@click.option('--role', '-r', default='Commander', show_default=True,
              help='Machine role for this session')
def login(username, password, role):
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
        # AuthManager.login requires (username, password, role) and returns
        # {'success': bool, ...}; the tokens live on the instance (auth_mgr.tokens),
        # not under a 'token' key in the result.
        result = auth_mgr.login(username, password, role)

        if result.get('success'):
            tokens = getattr(auth_mgr, 'tokens', None) or {}
            token = (tokens.get('IdToken') or tokens.get('id_token')
                     or tokens.get('AccessToken') or tokens.get('access_token'))
            ctx.save_session({
                'username': auth_mgr.current_user or username,
                'role': role,
                'token': token,
                'logged_in_at': datetime.now().isoformat()
            })
            out.success(f"Logged in as {auth_mgr.current_user or username}")
        else:
            out.error(f"Login failed: {result.get('error', 'Unknown error')}")
            raise SystemExit(1)
    except ImportError:
        # The cloud auth module isn't importable (e.g. offline/minimal env).
        # Create a clearly-labeled LOCAL session so the local-DB CLI is usable,
        # but note this is not a verified cloud login.
        out.warning("Auth service unavailable — creating a LOCAL (unverified) session")
        ctx.save_session({
            'username': username,
            'role': role,
            'local_only': True,
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
            "Status": out._color(out._style.GREEN, "Logged in"),
            "Username": session['username'],
            "Role": session.get('role', 'unknown'),
            "Session": "local (unverified)" if session.get('local_only') else "authenticated",
            "Logged in at": session.get('logged_in_at', 'unknown'),
        })
    else:
        out.warning("Not logged in")
        out.print("  Use: ecan auth login")


@auth.command()
@click.option('--username', '-u', help='Desired username')
@click.option('--email', '-e', help='Email address')
def signup(username, email):
    """
    Create a new eCan.ai account.

    NOT YET IMPLEMENTED via the CLI — sign up through the app/web instead.
    (Deliberately does not prompt for a password, since it would be
    discarded.)
    """
    out = get_output()
    out.error("CLI signup is not implemented — please sign up via the app or web.")
    raise SystemExit(1)


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
