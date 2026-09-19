#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drift commands — read the permanent record of site changes.

The journal accumulates one immutable record per site change, for years
(``agent/ec_skills/browser_use_extension/drift_journal.py``). Without a way to
read it back it is a file nobody will ever find, so this is the surface that
turns it into a tool.

The question it exists to answer, on a machine that has been running for a
year: *has this happened before, when, and what moved?*

    ecan drift list                    # every change recorded, newest first
    ecan drift list --kind site_deploy # just the deploy calendar
    ecan drift show 42                 # the full delta for one record
    ecan drift stats                   # how much history exists
    ecan drift shapes                  # what the site currently looks like

All of it is read-only. Nothing here deletes: the journal's whole value is that
the record of the LAST site change is still there when the next one lands.
"""

import json

import click

from ..base.output import get_output


def _journal():
    from agent.ec_skills.browser_use_extension import drift_journal
    return drift_journal


@click.group()
def drift():
    """Site-change history (read-only)."""


@drift.command('list')
@click.option('--site', '-s', default='', help='Only this site (e.g. feige_chat).')
@click.option('--kind', '-k', default='',
              help='Only this kind: dom_shape_change, ws_schema_change, '
                   'site_deploy, strategy_collapse.')
@click.option('--since-year', type=int, default=None, help='From this year on.')
@click.option('--limit', '-n', default=50, help='Most recent N (default 50).')
@click.option('--json', 'as_json', is_flag=True, help='Machine-readable output.')
def list_events(site, kind, since_year, limit, as_json):
    """List recorded site changes, newest first. QUERY command."""
    out = get_output()
    events = _journal().read_events(site=site, kind=kind,
                                    since_year=since_year, limit=limit)
    if as_json:
        out.json(events)
        return
    if not events:
        out.warning("No site changes recorded yet.")
        out.info("That is the expected state until a site actually moves — "
                 "changes are rare, which is why they are worth keeping.")
        return

    rows = [[e.get('seq', ''),
             str(e.get('ts', ''))[:19].replace('T', ' '),
             e.get('site', ''),
             e.get('kind', ''),
             e.get('summary', '')] for e in events]
    out.table("Site changes", ["#", "when (UTC)", "site", "kind", "what moved"],
              rows, max_col_width=70)
    out.info(f"\n{len(events)} record(s). `ecan drift show <#>` for the full delta.")


@drift.command('show')
@click.argument('seq', type=int)
@click.option('--json', 'as_json', is_flag=True, help='Machine-readable output.')
def show(seq, as_json):
    """Show one record in full, by its # from `drift list`. QUERY command."""
    out = get_output()
    match = next((e for e in _journal().read_events(limit=100000)
                  if e.get('seq') == seq), None)
    if not match:
        out.error(f"No record #{seq}.")
        raise SystemExit(1)
    if as_json:
        out.json(match)
        return

    out.header(f"#{match.get('seq')} — {match.get('summary', '')}")
    out.print(f"when     : {match.get('ts', '')}")
    out.print(f"site     : {match.get('site', '')}")
    out.print(f"element  : {match.get('element', '')}")
    out.print(f"kind     : {match.get('kind', '')}")
    build = match.get('build') or {}
    if build:
        out.print(f"build    : {build.get('version', '?')} "
                  f"on {build.get('platform', '?')}")
    repeats = match.get('repeats_in_window')
    if repeats and repeats > 1:
        out.print(f"repeats  : {repeats} within the coalescing window")

    evidence = match.get('evidence') or {}
    changed = evidence.get('changed')
    if changed:
        out.print("\nwhat changed:")
        out.print(json.dumps(changed, indent=2, ensure_ascii=False))
    held = evidence.get('previous_shape_held_since')
    if held:
        out.print(f"\nthe previous shape had held since {held}")


@drift.command('stats')
@click.option('--json', 'as_json', is_flag=True, help='Machine-readable output.')
def stats(as_json):
    """How much history exists on this machine. QUERY command."""
    out = get_output()
    journal = _journal()
    data = journal.journal_stats()
    if as_json:
        data['dir'] = str(journal.journal_dir())
        data['retention_floor_years'] = journal.RETENTION_FLOOR_YEARS
        out.json(data)
        return

    out.header("Site-change journal")
    out.print(f"location : {journal.journal_dir()}")
    out.print(f"records  : {data.get('events', 0)}")
    out.print(f"size     : {data.get('bytes', 0):,} bytes")
    out.print(f"retention: {journal.RETENTION_FLOOR_YEARS} years minimum — "
              f"nothing here is rotated or overwritten")
    files = data.get('files') or []
    if files:
        out.print("")
        out.table("By year", ["file", "records", "bytes"],
                  [[f['name'], f['events'], f"{f['bytes']:,}"] for f in files])

    deploys = journal.read_events(kind='site_deploy', limit=1000)
    if deploys:
        out.print(f"\ndeploys observed: {len(deploys)}, "
                  f"most recent {str(deploys[0].get('ts', ''))[:10]}")


@drift.command('shapes')
@click.option('--json', 'as_json', is_flag=True, help='Machine-readable output.')
def shapes(as_json):
    """What each watched thing currently looks like. QUERY command.

    This is the live baseline the next observation is compared against — not
    history. History is `drift list`.
    """
    out = get_output()
    journal = _journal()
    try:
        known = json.loads(journal._shapes_path().read_text(encoding='utf-8'))
    except Exception:
        known = {}
    if as_json:
        out.json(known)
        return
    if not known:
        out.warning("Nothing watched yet — run a browser task first.")
        return

    out.header("Current baselines")
    for key, entry in sorted(known.items()):
        if not isinstance(entry, dict):
            continue
        out.print(f"\n{key}")
        out.print(f"  held since : {entry.get('first_seen', '?')}")
        out.print(f"  last seen  : {entry.get('last_seen', '?')}")
        shape = entry.get('shape')
        if isinstance(shape, dict):
            for name, value in list(shape.items())[:8]:
                if isinstance(value, list):
                    preview = ', '.join(map(str, value[:6]))
                    more = f" (+{len(value) - 6})" if len(value) > 6 else ""
                    out.print(f"  {name:<12}: {preview}{more}")
                else:
                    out.print(f"  {name:<12}: {value}")
