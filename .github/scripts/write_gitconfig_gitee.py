#!/usr/bin/env python3
"""
Write a job-scoped gitconfig for the Gitee credential helper.

Reads GITCONFIG_FILE and CREDS_FILE from the environment (set by the
calling workflow step), writes a gitconfig that points git's
credential helper at the job-scoped credentials file, and configures
core.autocrlf=false so the file is not re-expanded on read.

Why Python (and not printf / heredoc):
  On Windows self-hosted runners, Git Bash translates LF→CRLF on
  every file write through the bash layer. printf, heredoc, sed,
  and bash redirections all produce CRLF-terminated output. Only
  Python's open() with newline='\n' bypasses this translation,
  yielding an LF-only file on every runner. This is the same
  pattern used by run-id-bootstrap.ps1.

Why a separate script (and not inline `python -c '...'`):
  The inline form requires the Python code to start at column 0
  inside the `run: |` block, which collides with YAML's parser at
  lines like `with open(...) as f:` (the trailing colon looks like
  a mapping separator). js-yaml rejects this with "can not read a
  block mapping entry; a multiline key may not be an implicit key".
  Moving the code to a file eliminates the YAML ambiguity entirely.

Usage (from GHA `run:` step):
    python3 .github/scripts/write_gitconfig_gitee.py
"""
import os
import sys


def main() -> int:
    cf = os.environ.get("GITCONFIG_FILE")
    cr = os.environ.get("CREDS_FILE")
    if not cf or not cr:
        sys.stderr.write(
            "error: GITCONFIG_FILE and CREDS_FILE env vars are required\n"
        )
        return 1

    contents = (
        "[core]\n"
        "    autocrlf = false\n"
        '[credential "https://gitee.com"]\n'
        f"    helper = store --file {cr}\n"
        "    username = oauth2\n"
    )
    with open(cf, "w", newline="\n") as f:
        f.write(contents)
    return 0


if __name__ == "__main__":
    sys.exit(main())