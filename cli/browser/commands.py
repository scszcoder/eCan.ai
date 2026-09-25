#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Browser Profile Commands - import/list/show/remove logged-in browser profiles.

A browser profile is one logged-in identity on one site, bound to the
user-data-dir that holds its session, the proxy it egresses through, and the
fingerprint it presents. Wraps
``agent.ec_skills.browser_use_extension.fingerprint`` -- the same registry the
browser-automation node reads when its browser type is ``fingerprint``.

Proxy passwords live in the OS keyring, never in the registry file, so nothing
here ever prints one.
"""

import click

from ..base.output import get_output


def _registry():
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry
    return profile_registry


def _status(profile_id):
    """Live state of one profile's browser, or an all-false record.

    Reads the port file in the user-data-dir, so it sees a browser the desktop
    app started just as well as one a skill run did.
    """
    try:
        from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser
        return fingerprint_browser.profile_status(profile_id)
    except Exception:
        return {"running": False, "port": 0, "pid": 0, "relay_port": 0,
                "relay_alive": False, "cdp_url": "", "owned": False}


@click.group()
def browser():
    """Manage browser profiles (logged-in sessions + proxy + fingerprint)."""


@browser.command('list')
@click.option('--format', '-f', 'format', type=click.Choice(['table', 'json', 'simple']),
              default='table')
def list_profiles(format):
    """List registered browser profiles. QUERY command."""
    out = get_output()
    try:
        rows = []
        for p in _registry().list_profiles():
            proxy = p.get('proxy') or {}
            st = _status(p.get('id', ''))
            if not st['running']:
                running = 'stopped'
            elif not st['relay_alive']:
                # Up, but the proxy relay died with whoever launched it: the
                # browser would now egress from this machine's own address.
                running = f":{st['port']} NO PROXY"
            else:
                running = f":{st['port']}"
            rows.append({
                'id': p.get('id', ''),
                'label': p.get('label', ''),
                'domain': p.get('domain_name', ''),
                'proxy': f"{proxy.get('host', '')}:{proxy.get('port', '')}" if proxy.get('host') else '',
                'fingerprint': p.get('fingerprint_profile', '') or '-',
                'running': running,
            })
        if not rows:
            out.info("No browser profiles registered. Import one with "
                     "'ecan browser import'.")
            return
        if format == 'json':
            out.json({'profiles': rows, 'count': len(rows)})
        elif format == 'simple':
            for r in rows:
                out.print(f"{r['id']}	{r['label']}	{r['domain']}")
        else:
            out.table("Browser profiles",
                      ["ID", "Label", "Domain", "Proxy", "Fingerprint", "Running"],
                      [[r['id'], r['label'], r['domain'], r['proxy'],
                        r['fingerprint'], r['running']] for r in rows])
    except Exception as e:
        out.error(f"Failed to list browser profiles: {e}")
        raise SystemExit(1)


@browser.command('show')
@click.argument('profile_id')
def show_profile(profile_id):
    """Show one browser profile. QUERY command.

    Never prints the proxy password -- it is in the OS keyring, not the record.
    """
    out = get_output()
    prof = _registry().get_profile(profile_id)
    if not prof:
        out.error(f"No browser profile registered as '{profile_id}'")
        raise SystemExit(1)
    st = _status(profile_id)
    out.json({**prof, 'status': st})

    if not st['running']:
        out.info("Not running.")
        return
    out.info(f"Running on {st['cdp_url']} (pid {st['pid']})")
    if st['relay_port'] and not st['relay_alive']:
        out.warning(
            f"Its proxy relay (127.0.0.1:{st['relay_port']}) is DEAD -- the "
            f"process that launched it has exited, so this browser is now "
            f"reaching the site from this machine's own IP. Close it before "
            f"using the profile again.")


@browser.command('import')
@click.option('--from', 'vendor', type=click.Choice(['adspower', 'ziniao']),
              default='adspower',
              help='Which anti-detect browser to import from (ziniao is UNVALIDATED)')
@click.option('--profile', 'vendor_profile_id', required=True,
              help="The vendor's profile id (AdsPower calls it the serial)")
@click.option('--as', 'new_id', required=True, help='Id to register it under')
@click.option('--label', default='', help='Display name (default: the vendor name)')
@click.option('--fingerprint', 'fingerprint_profile', default='',
              help='Fingerprint preset to present (see the bundled profiles)')
@click.option('--api-key', default='', help='Vendor API key, if their API needs one')
@click.option('--api-port', default=50325, help='Vendor local API port (default 50325)')
@click.option('--api-url', default='', help='Vendor local API base url')
@click.option('--overwrite', is_flag=True, help='Replace an existing profile of this id')
def import_profile(vendor, vendor_profile_id, new_id, label, fingerprint_profile,
                   api_key, api_port, api_url, overwrite):
    """Copy a logged-in profile out of an anti-detect browser. WRITE command.

    The vendor profile is started briefly (its directory is only visible on the
    running process's command line) and then STOPPED -- if you have it open, it
    will be closed. Caches are excluded, so expect ~20MB rather than ~800MB.
    """
    out = get_output()
    from agent.ec_skills.browser_use_extension.fingerprint import vendor_import

    out.info(f"Importing {vendor} profile '{vendor_profile_id}' as '{new_id}'")
    try:
        if vendor == 'ziniao':
            out.warning("The Ziniao importer has not been validated against a "
                        "live install -- report what it does.")
            zn = {}
            try:
                from gui.ipc.w2p_handlers.browser_use_handler import (
                    load_browser_use_settings,
                )
                zn = ((load_browser_use_settings() or {})
                      .get('browserProviders') or {}).get('ziniao') or {}
            except Exception:
                pass
            record = vendor_import.import_ziniao(
                vendor_profile_id,
                new_id,
                api_url=api_url or zn.get('api_url', ''),
                api_port=api_port if api_port != 50325 else int(zn.get('api_port') or 0),
                company=zn.get('company', ''),
                username=zn.get('username', ''),
                password=zn.get('password', ''),
                use_socket=bool(zn.get('use_socket')),
                label=label,
                fingerprint_profile=fingerprint_profile,
                overwrite=overwrite,
                progress=out.info,
            )
        else:
            record = vendor_import.import_adspower(
                vendor_profile_id,
                new_id,
                api_key=api_key,
                api_port=api_port,
                api_url=api_url,
                label=label,
                fingerprint_profile=fingerprint_profile,
                overwrite=overwrite,
                progress=out.info,
            )
    except Exception as e:
        out.error(f"Import failed: {e}")
        raise SystemExit(1)

    out.success(f"Registered '{record['id']}' ({record.get('label', '')})")
    out.info(f"  session:  {record['user_data_dir']}")
    proxy = record.get('proxy') or {}
    if proxy.get('host'):
        out.info(f"  proxy:    {proxy.get('scheme')}://{proxy.get('host')}:{proxy.get('port')}"
                 f" (password in the OS keyring)")
    out.info(f"Use it in a browser-automation node: browser = fingerprint, "
             f"browserProfileId = {record['id']}")


@browser.command('create')
@click.option('--id', 'profile_id', required=True, help='Profile id (becomes the session folder name)')
@click.option('--label', default='', help='Display name')
@click.option('--store', 'store_id', default='', help='Store this login belongs to')
@click.option('--domain', 'domain_name', default='', help='Site, e.g. im.jinritemai.com')
@click.option('--fingerprint', 'fingerprint_profile', default='', help='Fingerprint preset')
@click.option('--locale', default='zh-CN', help='Browser locale (default zh-CN)')
@click.option('--proxy', default='', help='host:port of an egress proxy (several profiles may share one)')
@click.option('--proxy-scheme', default='socks5', type=click.Choice(['socks5', 'http', 'https']))
@click.option('--proxy-user', default='', help='Proxy username')
@click.option('--proxy-password', default='', help='Proxy password (stored in the OS keyring only)')
def create_profile(profile_id, label, store_id, domain_name, fingerprint_profile, locale,
                   proxy, proxy_scheme, proxy_user, proxy_password):
    """Register a new browser profile (starts as needs_login). WRITE command.

    Sign in once in its browser (Settings -> Browser Profiles -> Launch), then
    mark it: ecan browser login-state <id> ok
    """
    import re
    out = get_output()
    reg = _registry()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", profile_id):
        raise click.ClickException("profile id: letters, digits, '_' or '-', up to 64 characters")
    if reg.get_profile(profile_id):
        raise click.ClickException(f"a browser profile '{profile_id}' already exists")
    proxy_cfg = None
    if proxy:
        host, _, port = proxy.rpartition(':')
        if not host or not port.isdigit():
            raise click.ClickException("--proxy must be host:port")
        proxy_cfg = {"scheme": proxy_scheme, "host": host, "port": int(port), "username": proxy_user}
    prof = reg.make_profile(profile_id, label=label or profile_id, domain_name=domain_name,
                            fingerprint_profile=fingerprint_profile, locale=locale,
                            proxy=proxy_cfg, store_id=store_id)
    reg.save_profile(prof, proxy_password=proxy_password)
    out.success(f"Created browser profile '{profile_id}' (needs_login) at {prof['user_data_dir']}")


@browser.command('login-state')
@click.argument('profile_id')
@click.argument('state', type=click.Choice(['ok', 'needs_login', 'unknown']))
def set_login_state(profile_id, state):
    """Record whether this profile's seller session works. WRITE command."""
    out = get_output()
    if not _registry().set_login_state(profile_id, state):
        raise click.ClickException(f"no browser profile '{profile_id}'")
    out.success(f"'{profile_id}' login state -> {state}")


@browser.command('remove')
@click.argument('profile_id')
@click.option('--delete-session', is_flag=True,
              help='Also delete the user-data-dir -- this destroys the login')
@click.confirmation_option(prompt='Remove this browser profile?')
def remove_profile(profile_id, delete_session):
    """Remove a browser profile from the registry. WRITE command.

    The session directory is kept unless --delete-session is given: the
    registry record is cheap to recreate, the logged-in session is not.
    """
    out = get_output()
    reg = _registry()
    prof = reg.get_profile(profile_id)
    if not prof:
        out.error(f"No browser profile registered as '{profile_id}'")
        raise SystemExit(1)

    user_data_dir = prof.get('user_data_dir', '')
    if not reg.delete_profile(profile_id):
        out.error(f"Failed to remove '{profile_id}'")
        raise SystemExit(1)

    if delete_session and user_data_dir:
        import shutil
        try:
            shutil.rmtree(user_data_dir)
            out.info(f"Deleted session directory {user_data_dir}")
        except Exception as e:
            out.warning(f"Could not delete {user_data_dir}: {e}")
    elif user_data_dir:
        out.info(f"Session kept at {user_data_dir}")

    out.success(f"Removed browser profile '{profile_id}'")
