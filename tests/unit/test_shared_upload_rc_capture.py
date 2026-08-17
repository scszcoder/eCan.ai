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


# ---------------------------------------------------------------------------
# Success-path regression — pinning the rc=0 initialization.
# ---------------------------------------------------------------------------
# The earlier tests above guard the FAILURE path: under `set -e`,
# `python3 ... || rc=$?` correctly captures a non-zero rc and writes
# `success=false`. The SUCCESS path was the actual production bug
# (log #86724325753, build 96a1935a): under `set -e`, `|| rc=$?`
# only fires on failure. On success, `rc` would be unset, so
# `[ $rc -eq 0 ]` failed with "[: -eq: unary operator expected"
# and the wrapper fell into the `else` branch, mis-classifying a
# successful upload as a soft runtime failure and emitting
# `success=false` plus a `::warning::`. With `continue-on-error:
# true` the job still showed green, but downstream jobs (appcast,
# download-links, latest.json) skipped because `upload-success=false`
# was written, and the Final Status Summary printed `S3 upload:
# false`.
#
# The contract here is: `rc=0` must be set BEFORE the
# `python3 ... || rc=$?` / `wait ... || rc=$?` line so that on a
# successful python3 exit the `[ "$rc" -eq 0 ]` test fires. The
# tests below pin that initialization contract for both files.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_bash_success_path_rc_initialized_to_zero():
    """Repro the production bug: `python3 ... || rc=$?` leaves rc unset on
    success, and `[ $rc -eq 0 ]` then errors. The fix is to initialize
    `rc=0` before the `|| rc=$?` line.
    """
    # Bad pattern (the bug): rc unset on success → test fails → falls
    # through into the warning branch.
    bad_script = (
        "set -e\n"
        "python3 -c 'print(\"uploaded\")' || rc=$?\n"
        "if [ $rc -eq 0 ]; then echo SUCCESS_BRANCH; else echo WARNING_BRANCH; fi\n"
    )
    bad = subprocess.run(
        ["bash", "-e", "-c", bad_script],
        capture_output=True,
        text=True,
    )
    # On a successful python3, the BAD pattern should NOT have reached
    # the SUCCESS branch (it errors out and falls through to WARNING).
    assert "WARNING_BRANCH" in bad.stdout, (
        "Sanity: the bad pattern should mis-classify a successful "
        "upload as a failure. If this assertion fails, the test no "
        "longer models the bug correctly."
    )
    assert "SUCCESS_BRANCH" not in bad.stdout, (
        "Sanity: the bad pattern should NOT reach SUCCESS_BRANCH."
    )

    # Good pattern (the fix): rc=0 init → test passes → success branch.
    good_script = (
        "set -e\n"
        "rc=0\n"
        "python3 -c 'print(\"uploaded\")' || rc=$?\n"
        "if [ \"$rc\" -eq 0 ]; then echo SUCCESS_BRANCH; else echo WARNING_BRANCH; fi\n"
    )
    good = subprocess.run(
        ["bash", "-e", "-c", good_script],
        capture_output=True,
        text=True,
    )
    assert "SUCCESS_BRANCH" in good.stdout, (
        "Expected SUCCESS_BRANCH on a successful upload when `rc=0` "
        "is initialized before `python3 ... || rc=$?`. Without the "
        "init, `[ $rc -eq 0 ]` errors with `[: -eq: unary operator "
        "expected` and the wrapper mis-classifies success as "
        "failure (see log #86724325753).\n"
        f"stdout={good.stdout!r}\nstderr={good.stderr!r}"
    )
    assert "WARNING_BRANCH" not in good.stdout, (
        "The fix should NOT reach WARNING_BRANCH on a successful upload."
    )


def test_s3_upload_initializes_rc_before_or_guard():
    """shared-s3-upload.yml must initialize `rc=0` BEFORE the
    `python3 ... || rc=$?` line. Without this, a successful upload
    leaves rc unset, `[ $rc -eq 0 ]` errors, and the wrapper
    mis-classifies success as a soft runtime failure (log #86724325753).
    """
    text = _read(S3)
    # Locate the python3 upload block and find the `|| rc=$?` line.
    upload_match = re.search(
        r"python3 build_system/scripts/upload_to_s3\.py.*?\|\| rc=\$\?",
        text,
        flags=re.DOTALL,
    )
    assert upload_match, (
        "shared-s3-upload.yml must contain `python3 ... || rc=$?`. "
        "Earlier contract test (test_s3_upload_uses_or_rc_guard) "
        "should already be enforcing this."
    )
    # Walk backwards from the upload match to find the most recent
    # `rc=0` initialization line. It must come BEFORE the upload match.
    init_matches = list(re.finditer(r"^\s*rc=0\s*$", text, flags=re.MULTILINE))
    assert init_matches, (
        "shared-s3-upload.yml must contain a `rc=0` initialization line "
        "BEFORE the `python3 ... || rc=$?` upload block. Without it, a "
        "successful upload leaves rc unset under `set -e` and "
        "`[ $rc -eq 0 ]` errors with `[: -eq: unary operator expected`, "
        "causing the wrapper to mis-classify success as a soft "
        "runtime failure (see log #86724325753)."
    )
    latest_init = init_matches[-1]
    assert latest_init.start() < upload_match.start(), (
        "The `rc=0` initialization must come BEFORE the "
        "`python3 ... || rc=$?` upload block. The most recent "
        "`rc=0` is at offset "
        f"{latest_init.start()}, but the upload block is at offset "
        f"{upload_match.start()}."
    )


def test_cos_upload_initializes_rc_before_or_guard():
    """shared-cos-upload.yml must initialize `rc=0` BEFORE the
    `wait "$PY_PID" || rc=$?` line. Same reasoning as the S3 test
    above (log #86724325753).
    """
    text = _read(COS)
    wait_match = re.search(
        r'wait "\$PY_PID" \|\| rc=\$\?',
        text,
    )
    assert wait_match, (
        "shared-cos-upload.yml must contain `wait \"$PY_PID\" || rc=$?`. "
        "Earlier contract test (test_cos_upload_uses_or_rc_guard) "
        "should already be enforcing this."
    )
    init_matches = list(re.finditer(r"^\s*rc=0\s*$", text, flags=re.MULTILINE))
    assert init_matches, (
        "shared-cos-upload.yml must contain a `rc=0` initialization "
        "line BEFORE the `wait \"$PY_PID\" || rc=$?` block."
    )
    latest_init = init_matches[-1]
    assert latest_init.start() < wait_match.start(), (
        "The `rc=0` initialization must come BEFORE the "
        "`wait \"$PY_PID\" || rc=$?` block."
    )


def test_s3_upload_quotes_rc_in_arithmetic_tests():
    """All `[ $rc -eq N ]` tests must quote `$rc` as `"$rc"` so an
    empty `$rc` (e.g. if `rc=0` init ever gets removed by a future
    commit) degrades to a clear `[: integer expression expected`
    instead of the more confusing `[ -eq: unary operator expected`.
    The quoted version is what the production fix uses (and what the
    above init tests now pin).

    The regex matches actual `[ $rc -eq N ]` constructs on a
    non-comment line. It uses a negative lookbehind for `#` so a
    textual reference inside a comment (e.g. "# `[ $rc -eq 0 ]`
    test below") does not false-positive.
    """
    text = _read(S3)
    # Strip comment lines first to avoid matching text inside `# ...`.
    code_lines = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    bad = re.findall(r"\[\s+\$rc\s+-eq\s+\d+\s+\]", code_lines)
    assert not bad, (
        "shared-s3-upload.yml still has unquoted `[ $rc -eq N ]` "
        "tests on a code line. Use `[ \"$rc\" -eq N ]` so an unset "
        "rc degrades gracefully. Found: " + repr(bad)
    )


def test_cos_upload_quotes_rc_in_arithmetic_tests():
    """Mirror of test_s3_upload_quotes_rc_in_arithmetic_tests for COS."""
    text = _read(COS)
    code_lines = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    bad = re.findall(r"\[\s+\$rc\s+-eq\s+\d+\s+\]", code_lines)
    assert not bad, (
        "shared-cos-upload.yml still has unquoted `[ $rc -eq N ]` "
        "tests on a code line. Use `[ \"$rc\" -eq N ]`. Found: " + repr(bad)
    )