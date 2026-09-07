#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Support commands — request-log-analysis package + upload.

Same action as the GUI Help → Request Log Analysis dialog, exposed on the CLI so
an agent (or a user in a headless/remote session) can file a support bundle:
the user's problem description (saved to runlogs/current_issues.md), attachments
(screenshots / screen recordings copied into runlogs/issue_attachments/), the
selected skills + their referenced prompts, and the whole runlogs folder — zipped
and uploaded to support.

The heavy lifting is the shared ``debug_log_handler.perform_log_analysis_upload``
(one code path with the GUI). Cloud auth uses the CLI env token
(``ECAN_CLI_AUTH_TOKEN``, set by the app for its subprocesses) with a fallback to
the CLI session token.
"""

import os
from pathlib import Path

import click

from ..base.context import get_context
from ..base.output import get_output


@click.group()
def support():
    """Support tools (log analysis upload)."""


@support.command('upload')
@click.option('--description', '-d', default='', help='Problem description (saved to current_issues.md).')
@click.option('--description-file', '-D', 'description_file',
              type=click.Path(exists=True), help='Read the description from a UTF-8 file.')
@click.option('--attach', '-a', 'attachments', multiple=True,
              type=click.Path(exists=True), help='Attach a screenshot / recording (repeatable).')
@click.option('--skill', '-s', 'skill_ids', multiple=True, help='Skill id to include (repeatable).')
@click.option('--yes', '-y', is_flag=True, help='Skip the confirmation prompt.')
def upload(description, description_file, attachments, skill_ids, yes):
    """Package the runlogs + a problem report and upload to support. WRITE command."""
    ctx = get_context()
    out = get_output()

    if description_file:
        description = Path(description_file).read_text(encoding='utf-8')
    description = (description or '').strip()
    if not description:
        out.error("A problem description is required (use --description or --description-file).")
        raise SystemExit(1)

    attachments = list(attachments)
    skill_ids = list(skill_ids)

    if not yes:
        out.info(f"About to upload: description ({len(description)} chars), "
                 f"{len(attachments)} attachment(s), {len(skill_ids)} skill(s), "
                 f"and the full runlogs folder.")
        if not click.confirm("Proceed?", default=True):
            out.info("Cancelled.")
            return

    # Bridge the CLI session token into the env fallback the handler reads.
    if not os.environ.get("ECAN_CLI_AUTH_TOKEN"):
        sess = ctx.session or {}
        tok = sess.get("token") or sess.get("access_token") or sess.get("accessToken")
        if tok:
            os.environ["ECAN_CLI_AUTH_TOKEN"] = str(tok)
    if ctx.username and not os.environ.get("ECAN_CLI_USER"):
        os.environ["ECAN_CLI_USER"] = str(ctx.username)

    try:
        from gui.ipc.w2p_handlers.debug_log_handler import perform_log_analysis_upload
        message = perform_log_analysis_upload(skill_ids, description, attachments)
    except Exception as e:
        out.error(f"Upload failed: {e}")
        raise SystemExit(1)
    out.success(message or "Debug package uploaded successfully.")
