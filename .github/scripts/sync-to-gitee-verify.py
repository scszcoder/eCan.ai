#!/usr/bin/env python3
"""
sync-to-gitee-verify.py
=======================

Post-push verification for the `sync-to-gitee.yml` workflow. Compares the
SHA of every ref listed in $VERIFY_REFS between:

  * the local bare clone in $CACHE_DIR (just-pushed state), and
  * the Gitee mirror (via `/tmp/lsremote.log` captured earlier by `git
    ls-remote`).

Also cross-checks the GitHub trigger SHA (`$TRIGGER_SHA`) against the
local tip of the ref in `$TRIGGER_REF`, so a run on `lq_dev_multi` whose
trigger head no longer matches the local tip is reported.

The script prints a sorted table for humans, and exits non-zero on:

  * any ref listed in $VERIFY_REFS that exists locally but is missing on
    Gitee, or whose remote SHA differs from the local SHA, or
  * the trigger-ref SHAs differing between GitHub (env) and local.

Workflow integration: see `.github/workflows/sync-to-gitee.yml`. The
yaml step invokes this script via `python3 .github/scripts/sync-to-gitee-
verify.py`, with cwd = $CACHE_DIR so `git` resolves refs against the
just-pushed bare repo.

Inputs (env vars):
  VERIFY_REFS   comma-separated list of ref globs/refs; refs/tags is a
                special token that prints the 3 most recent local tags
                (regardless of VERIFY_REFS shape).
  TRIGGER_REF   e.g. refs/heads/lq_dev_multi
  TRIGGER_SHA   the SHA that triggered this workflow run
  CACHE_DIR     already on PATH; only used for clearer error messages.

Inputs (files):
  /tmp/lsremote.log   lines of form "<sha>\t<refname>" produced by
                      `git ls-remote https://gitee.com/$OWNER/$REPO.git`.
"""
import os
import subprocess
import sys


def run(cmd):
    return subprocess.check_output(cmd).decode().strip()


def local_sha(ref):
    """Return the (short, full) SHA that the local bare clone resolves
    `ref` to, dereferencing annotated tags. Mirrors `git rev-parse
    <ref>^{commit}`.
    """
    full = run(["git", "rev-parse", f"{ref}^{{commit}}"])
    short = run(["git", "rev-parse", "--short", f"{ref}^{{commit}}"])
    return short, full


def remote_for_ref(remote_index, ref):
    """Look up the remote SHA for `ref` in /tmp/lsremote.log."""
    return remote_index.get(ref, "")


def print_table(rows):
    """Print a fixed-width comparison table. Rows is a list of
    (ref, local_short, local_full, remote_short_or_empty, status).
    """
    print(f"{'REF':<40} {'LOCAL(SHORT)':<13} {'LOCAL':<42} {'REMOTE':<42} STATUS")
    print("-" * 150)
    for ref, lshort, lfull, rfull, status in rows:
        print(f"{ref:<40} {lshort:<13} {lfull:<42} {rfull:<42} {status}")


def main():
    verify = [r.strip() for r in os.environ.get("VERIFY_REFS", "").split(",") if r.strip()]
    # Normalize bare names to refs/.
    verify = [r if r.startswith("refs/") else f"refs/heads/{r}" for r in verify]

    if os.path.exists("/tmp/lsremote.log"):
        lsremote = open("/tmp/lsremote.log").read()
    else:
        lsremote = ""

    remote_index = {}
    for line in lsremote.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, ref = parts
        remote_index[ref] = sha

    any_mismatch = False
    missing_local = False
    rows = []

    for ref in verify:
        if ref == "refs/tags":
            # Special case: show the 3 most recent local tags.
            out = run([
                "git", "for-each-ref",
                "--sort=-creatordate",
                "--format=%(objectname:short) %(objectname) %(refname:short)",
                "refs/tags",
            ]).splitlines()[:3]
            for line in out:
                short, full, shortref = line.split(" ", 2)
                remote_full = remote_index.get(f"refs/tags/{shortref}", "")
                if remote_full == full:
                    status = "OK"
                elif not remote_full:
                    status = "MISSING"
                else:
                    status = f"MISMATCH (remote={remote_full[:12]})"
                if status != "OK":
                    any_mismatch = True
                rows.append((shortref, short, full, remote_full, f"{status} (tag)"))
            continue

        try:
            lshort, lfull = local_sha(ref)
        except subprocess.CalledProcessError:
            rows.append((ref, "-", "(local ref missing)", "", "SKIP"))
            missing_local = True
            continue
        rfull = remote_for_ref(remote_index, ref)
        if not rfull:
            status = "MISSING ON GITEE"
            any_mismatch = True
        elif rfull == lfull:
            status = "OK"
        else:
            status = f"MISMATCH (remote={rfull[:12]})"
            any_mismatch = True
        rows.append((ref, lshort, lfull, rfull, status))

    # Cross-check the trigger ref.
    trigger_sha = os.environ.get("TRIGGER_SHA", "")
    trigger_ref_full = os.environ.get("TRIGGER_REF", "")  # e.g. refs/heads/lq_dev_multi
    trigger_ref_name = (
        trigger_ref_full.replace("refs/heads/", "")
        if trigger_ref_full.startswith("refs/heads/")
        else ""
    )
    print()
    print(f"trigger.ref_name = {trigger_ref_name}")
    print(f"trigger.sha       = {trigger_sha}")

    if trigger_ref_name:
        try:
            lshort, lfull = local_sha(f"refs/heads/{trigger_ref_name}")
            rfull = remote_index.get(f"refs/heads/{trigger_ref_name}", "")
            print(f"local  {trigger_ref_name:<15} = {lfull} ({lshort})")
            print(f"remote {trigger_ref_name:<15} = {rfull or '(missing on Gitee)'}")
            print()
            # Trigger SHA vs local tip: only meaningful when they're on
            # the same branch. If they differ, the workflow was
            # triggered by an out-of-date push event (race); log a
            # warning but don't fail solely on that.
            if trigger_sha and trigger_sha != lfull:
                print(
                    f"NOTE: trigger SHA {trigger_sha[:12]} != local tip {lshort}; "
                    "this run was triggered before the latest commit landed. "
                    "Compare remote vs local instead."
                )
            if not rfull:
                print(f"VERIFY: trigger ref '{trigger_ref_name}' is MISSING on Gitee [FAIL]")
                any_mismatch = True
            elif rfull != lfull:
                print(
                    f"VERIFY: trigger ref '{trigger_ref_name}' SHAs differ "
                    f"between local ({lshort}) and Gitee ({rfull[:12]}) [FAIL]"
                )
                any_mismatch = True
            else:
                print(f"VERIFY: trigger ref '{trigger_ref_name}' SHAs match [OK]")
        except subprocess.CalledProcessError:
            print(f"(trigger ref {trigger_ref_name} not present locally)")
            missing_local = True

    print()
    print_table(rows)

    if missing_local:
        print()
        print("One or more expected refs are missing locally; sync is incomplete.")
    if any_mismatch:
        print()
        print("One or more refs do NOT match between local and Gitee; sync is BROKEN.")
        sys.exit(2)
    print()
    print("All checked refs match between local and Gitee.")
    sys.exit(0)


if __name__ == "__main__":
    main()
