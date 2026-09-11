#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Support commands — bug report package + upload.

Same action as the GUI Help → Report Bug dialog, exposed on the CLI so
an agent (or a user in a headless/remote session) can file a support bundle:
the user's problem description (saved to runlogs/current_issues.md), attachments
(screenshots / screen recordings copied into runlogs/issue_attachments/), the
selected skills + their referenced prompts, and the whole runlogs folder — zipped
and uploaded to support.

The problem description goes through the same server-side intake gate the GUI
uses: a description the server can't act on comes back as "incomplete" (exit 2,
with the follow-up question on stderr) or "rejected" (exit 3) and nothing is
packaged or uploaded. An agent driving this should answer the question and
re-run with a fuller --description.

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
    """Package the runlogs + a problem report and upload to support. WRITE command.

    Exit codes: 0 uploaded, 1 error, 2 description incomplete (see stderr for the
    follow-up question), 3 report rejected.
    """
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

    from gui.ipc.w2p_handlers.debug_log_handler import (
        local_description_issue, validate_bug_description, perform_log_analysis_upload)

    # Local pre-check first — no server round-trip for an obviously thin report.
    issue = local_description_issue(description)
    if issue:
        out.error("The description is too thin to act on "
                  f"({issue}). Say what you were doing, what you expected, "
                  "and what actually happened.")
        raise SystemExit(2)

    # Server-side intake gate. Nothing is packaged until it says ok.
    try:
        verdict = validate_bug_description(description, skill_ids)
    except Exception as e:
        out.error(f"Description check failed: {e}")
        raise SystemExit(1)

    status = verdict.get("status") or "rejected"
    if status == "incomplete":
        out.error(verdict.get("question")
                  or "More detail needed: what were you doing, and what happened on screen?")
        raise SystemExit(2)
    if status != "ok":
        out.error(verdict.get("message") or "Report not accepted.")
        raise SystemExit(3)

    try:
        message = perform_log_analysis_upload(
            skill_ids, description, attachments, verdict.get("grant") or None)
    except Exception as e:
        out.error(f"Upload failed: {e}")
        raise SystemExit(1)
    out.success(message or "Debug package uploaded successfully.")
