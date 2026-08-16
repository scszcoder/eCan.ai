"""
Regression tests for the shared-{s3,cos}-upload.yml `set -e` + `rc=$?`
interaction bug.

GitHub Actions' default bash runs with `-e` (`/usr/bin/bash -e {0}`).
Under `-e`, a multi-line command that returns non-zero (e.g. `python3
...` exiting with code 2) immediately terminates the step *before*
the next statement (`rc=$?`) executes. The previous upload scripts
relied on `python3 ... ; rc=$? ; if [ $rc -eq 0 ]...`, so every
rc=2 upload exited the wrapper with code 2 *without* ever writing
`success=false` to `$GITHUB_OUTPUT`. Downstream jobs (appcast, links,
latest.json) then saw an empty `upload-success` output and printed
"S3 upload:" / "COS upload:" as a blank line in the Final Status
Summary.

The fix: `python3 ... || rc=$?` and `wait "$PY_PID" || rc=$?`. The
right-hand assignment always succeeds, suppressing errexit
propagation. These tests pin the contract.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
S3 = REPO / ".github/workflows/shared-s3-upload.yml"
COS = REPO / ".github/workflows/shared-cos-upload.yml"
INTL = REPO / ".github/workflows/release-intl.yml"
CN = REPO / ".github/workflows/release-cn.yml"


# ---------------------------------------------------------------------------
# Behavioral tests — exercise the bash pattern directly.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_bash_errexit_hides_rc_without_or_guard():
    """Repro: under `set -e`, `python3 ...; rc=$?` does NOT capture rc."""
    script = (
        "set -e\n"
        "echo before\n"
        "python3 -c 'import sys; sys.exit(2)'\n"
        "rc=$?\n"
        "echo after-rc-is-$rc\n"
    )
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        capture_output=True,
        text=True,
    )
    assert "before" in result.stdout, "sanity: echo before must run"
    assert "after-rc-is-" not in result.stdout, (
        "Expected `after-rc-is-` to NOT be printed — `set -e` terminates "
        "the script at the python3 failure before `rc=$?` runs. This is "
        "the bug we are guarding against."
    )
    assert result.returncode == 2, (
        f"Expected bash to exit 2 (python's exit), got {result.returncode}"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_bash_or_rc_guard_captures_rc():
    """The fix: `python3 ... || rc=$?` does capture rc under `set -e`."""
    script = (
        "set -e\n"
        "echo before\n"
        "python3 -c 'import sys; sys.exit(2)' || rc=$?\n"
        "echo after-rc-is-$rc\n"
        "exit $rc\n"
    )
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        capture_output=True,
        text=True,
    )
    assert "before" in result.stdout
    assert "after-rc-is-2" in result.stdout, (
        f"Expected `after-rc-is-2`, got stdout: {result.stdout!r}. "
        "The `|| rc=$?` pattern is required to suppress errexit while "
        "capturing the failed command's exit code."
    )
    assert result.returncode == 2, (
        f"Expected the script to exit 2 to faithfully model what the "
        f"wrapper does next (write success=false and exit 1, but here "
        f"we just propagate rc). Got {result.returncode}."
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_bash_wait_or_rc_guard_captures_rc():
    """The COS upload uses `wait "$PY_PID"; rc=$?` — same bug, same fix."""
    script = (
        "set -e\n"
        "python3 -c 'import sys; sys.exit(2)' &\n"
        "PY_PID=$!\n"
        "wait \"$PY_PID\" || rc=$?\n"
        "echo after-rc-is-$rc\n"
    )
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        capture_output=True,
        text=True,
    )
    assert "after-rc-is-2" in result.stdout, (
        "Expected `after-rc-is-2`. The `wait || rc=$?` pattern is the "
        "load-bearing piece in shared-cos-upload.yml."
    )


# ---------------------------------------------------------------------------
# Static analysis — pin the actual workflow files.
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_s3_upload_uses_or_rc_guard():
    """shared-s3-upload.yml's Upload to S3 step must use `python3 ... || rc=$?`.

    The exact pattern is `python3 build_system/scripts/upload_to_s3.py \\
        --version "$VERSION" \\
        ... \\
        "${PREFIX_ARG[@]}" || rc=$?`. Earlier commits used
    `python3 ... ; rc=$?` which failed under `set -e`.
    """
    text = _read(S3)
    # Find the upload block.
    m = re.search(
        r"python3 build_system/scripts/upload_to_s3\.py.*?\|\| rc=\$\?",
        text,
        flags=re.DOTALL,
    )
    assert m, (
        "shared-s3-upload.yml must call `python3 ... || rc=$?`. The "
        "`set -e` default in GHA bash would otherwise terminate the "
        "step at the python3 failure, leaving `success=false` unset "
        "and the Final Status Summary blank for `S3 upload:`."
    )


def test_cos_upload_uses_or_rc_guard():
    """shared-cos-upload.yml's COS upload step must use `wait ... || rc=$?`."""
    text = _read(COS)
    assert 'wait "$PY_PID" || rc=$?' in text, (
        "shared-cos-upload.yml must use `wait \"$PY_PID\" || rc=$?`. "
        "Earlier commits used `wait \"$PY_PID\"; rc=$?` which under "
        "`set -e` exits before rc=$? runs."
    )


def test_s3_upload_does_not_have_bare_rc_after_python():
    """Guard against the bad pattern sneaking back in.

    The bad pattern is: multi-line `python3 ...\` ending in `"${PREFIX_ARG[@]}"`,
    followed by an empty line, then `rc=$?` on its own line. That's the
    exact shape that triggered the bug.
    """
    text = _read(S3)
    # Find the python upload block; check what immediately follows it.
    block_match = re.search(
        r'python3 build_system/scripts/upload_to_s3\.py.*?"\$\{PREFIX_ARG\[@\]\}"',
        text,
        flags=re.DOTALL,
    )
    assert block_match, "could not locate python3 upload block in s3 file"
    after = text[block_match.end():block_match.end() + 80]
    # The line right after must be `|| rc=$?`, not a bare `rc=$?`.
    # Allow trailing whitespace / newline.
    assert after.lstrip().startswith("|| rc=$?") or after.lstrip().startswith("||"), (
        f"After `python3 ... \"${{PREFIX_ARG[@]}}\"` expected `|| rc=$?` "
        f"on the next line. Got: {after[:60]!r}"
    )


def test_intl_final_status_emits_error_for_empty_result():
    """The Final Status Summary must emit ::error:: for empty/failed
    results. Otherwise the operator sees a blank `S3 upload:` line
    instead of the actual signal.
    """
    text = _read(INTL)
    # The Show summary step is in the `final-status:` job.
    assert "final-status:" in text
    assert "any_failed=0" in text, (
        "release-intl.yml's Final Status Summary must track `any_failed` "
        "and emit ::error:: for empty/failure/cancelled results."
    )
    assert '::error::${name} failed' in text or "::error::${name}" in text, (
        "Show summary step must emit ::error:: annotations per failed tier."
    )


def test_cn_final_status_emits_error_for_empty_result():
    """Mirror of test_intl_final_status_emits_error_for_empty_result for CN."""
    text = _read(CN)
    assert "final-status:" in text
    assert "any_failed=0" in text, (
        "release-cn.yml's Final Status Summary must track `any_failed` "
        "and emit ::error:: for empty/failure/cancelled results."
    )