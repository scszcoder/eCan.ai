#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account API-Key Commands - add / delete / query / test the account's API key.

The key is the one shown on the web app's Account page (myAPIKeygen backend,
``ecan_apikeys`` store) — CLI, desktop GUI, and web all manage the same key.

Auth: the eCan session token, from (in order) ``ECAN_CLI_AUTH_TOKEN`` or the
running app's keyring session. All calls go to the myAPIKeygen SCF HTTP route
on the CN TCB origin.
"""

import json
import os

import click


def _session_token() -> str:
    """Resolve the eCan session token for cloud calls (env wins)."""
    token = (os.environ.get("ECAN_CLI_AUTH_TOKEN") or "").strip()
    if token:
        return token
    try:
        from agent.cloud_api.cloud_api import _get_wechat_http_session_token
        return (_get_wechat_http_session_token() or "").strip()
    except Exception:
        return ""


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not result.get("success", True) or result.get("error"):
        click.echo(f"ERROR: {result.get('error', '')} {result.get('message', '')}".strip())
        raise SystemExit(1)
    click.echo(result.get("message") or json.dumps(result, ensure_ascii=False))


@click.group()
def apikey():
    """
    Account API-key management commands.

    Manages the SAME key as the web app's Account page.

    Examples:
      ecan apikey add
      ecan apikey query
      ecan apikey test
      ecan apikey delete
    """
    pass


@apikey.command('add')
@click.option('--customer', '-c', default='guest', help='Customer identifier (default: guest)')
@click.option('--json', 'as_json', is_flag=True, help='Raw JSON output')
def add_key(customer, as_json):
    """Create an API key (idempotent — returns the existing key if present)."""
    from agent.cloud_api.api_keys import create_api_key, mask_api_key
    result = create_api_key(_session_token(), customer=customer)
    if as_json:
        _emit(result, True)
        return
    key = result.get("apiKey")
    if key:
        click.echo(f"API key: {key}")
        click.echo(f"Masked:  {mask_api_key(key)}")
        click.echo(result.get("message") or "")
    else:
        _emit(result, False)


@apikey.command('query')
@click.option('--json', 'as_json', is_flag=True, help='Raw JSON output')
@click.option('--reveal', is_flag=True, help='Print the full key instead of the masked form')
def query_key(as_json, reveal):
    """Show the account's current API key (masked by default)."""
    from agent.cloud_api.api_keys import get_api_key, mask_api_key
    result = get_api_key(_session_token())
    if as_json:
        _emit(result, True)
        return
    key = result.get("apiKey")
    if key:
        click.echo(key if reveal else mask_api_key(key))
        if result.get("status"):
            click.echo(f"status: {result['status']}")
    elif result.get("success", True):
        click.echo("No active API key found.")
    else:
        _emit(result, False)


@apikey.command('test')
@click.argument('key', required=False)
@click.option('--json', 'as_json', is_flag=True, help='Raw JSON output')
def test_key(key, as_json):
    """Test an API key with a REAL request (llm-proxy GET /v1/models).

    Defaults to the account's current key.
    """
    from agent.cloud_api.api_keys import get_api_key, test_api_key_live
    if not key:
        current = get_api_key(_session_token())
        key = current.get("apiKey")
        if not key:
            click.echo("No API key to test — run `ecan apikey add` first.")
            raise SystemExit(1)
    result = test_api_key_live(key)
    if as_json:
        _emit(result, True)
        return
    if result.get("valid"):
        models = result.get("models") or []
        click.echo(f"VALID — HTTP 200 in {result.get('latency_ms')}ms, "
                   f"{len(models)} model(s) served")
        if models:
            click.echo("models: " + ", ".join(str(m) for m in models[:10]))
    else:
        click.echo(f"INVALID — HTTP {result.get('http_status', '?')} "
                   f"{result.get('message') or result.get('body') or ''}")
        raise SystemExit(1)


@apikey.command('delete')
@click.argument('key', required=False)
@click.option('--json', 'as_json', is_flag=True, help='Raw JSON output')
@click.confirmation_option(prompt='Revoke this API key?')
def delete_key(key, as_json):
    """Revoke an API key (defaults to the account's current key)."""
    from agent.cloud_api.api_keys import get_api_key, mask_api_key, remove_api_keys
    token = _session_token()
    if not key:
        current = get_api_key(token)
        key = current.get("apiKey")
        if not key:
            click.echo("No active API key to delete.")
            return
    result = remove_api_keys(token, [mask_api_key(key)])
    if as_json:
        _emit(result, True)
        return
    if result.get("success", True) and not result.get("error"):
        click.echo("API key revoked.")
    else:
        _emit(result, False)
