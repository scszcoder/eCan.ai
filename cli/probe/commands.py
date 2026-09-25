#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Site probe commands - record a live site's WebSocket + API traffic to reverse-engineer it.

    ecan probe run --site pdd_chat --profile pdd-shop1 --minutes 30
    ecan probe run --site pdd_chat --cdp-url http://127.0.0.1:9222
    ecan probe summarize runlogs/probe/pdd_chat_20260924-221500.jsonl

Runs alongside a store session that is already open and logged in; it only
listens. The capture stays on this machine (runlogs/probe/) -- it holds real
customer messages.
"""

import asyncio
import json
import time

import click

from ..base.output import get_output


@click.group()
def probe():
    """Record a site's live traffic (WebSocket frames, chat APIs, DOM)."""


def _cdp_for_profile(profile_id: str) -> str:
    from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser
    st = fingerprint_browser.profile_status(profile_id)
    if not st.get("running"):
        raise click.ClickException(
            f"login '{profile_id}' is not open. Open it (Settings -> Browser Profiles -> Launch), "
            f"log in to the store, then run the probe.")
    return st["cdp_url"]


@probe.command("run")
@click.option("--site", required=True, help="Bundle whose site.py supplies the preset, e.g. pdd_chat")
@click.option("--profile", "profile_id", default="", help="A fingerprint-browser login that is open now")
@click.option("--cdp-url", default="", help="Or any browser's debugging endpoint, e.g. http://127.0.0.1:9222")
@click.option("--minutes", default=0.0, type=float, help="Stop after this long (default: until Ctrl+C)")
@click.pass_context
def run(ctx, site, profile_id, cdp_url, minutes):
    """Attach to a running browser and record until stopped."""
    out = get_output(ctx)
    from agent.ec_skills.browser_use_extension.site_probe import SiteProbe, load_preset
    if not (profile_id or cdp_url):
        raise click.ClickException("give --profile or --cdp-url")
    preset = load_preset(site)
    url = cdp_url or _cdp_for_profile(profile_id)

    async def _main():
        p = SiteProbe(url, preset)
        await p.start()
        click.echo(f"Recording {preset.name} -> {p.path}")
        click.echo("Use the chat normally (receive and send a few messages). Ctrl+C to stop.")
        deadline = time.time() + minutes * 60 if minutes else None
        try:
            while deadline is None or time.time() < deadline:
                await asyncio.sleep(5)
                s = p.stats
                click.echo(f"  sockets={s['ws_created']} recv={s['ws_recv']} sent={s['ws_sent']} "
                           f"api={s['api']} tabs={s['attached_page']} workers="
                           f"{s['attached_worker'] + s['attached_service_worker'] + s['attached_shared_worker']}")
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        return await p.stop()

    try:
        summary = asyncio.run(_main())
    except KeyboardInterrupt:
        return
    out.print(json.dumps(summary, ensure_ascii=False, indent=2)[:20000])


@probe.command("summarize")
@click.argument("capture_file")
@click.pass_context
def summarize_cmd(ctx, capture_file):
    """Sockets, frame shapes (with samples) and API endpoints in a capture."""
    from agent.ec_skills.browser_use_extension.site_probe import summarize
    get_output(ctx).print(json.dumps(summarize(capture_file), ensure_ascii=False, indent=2))
