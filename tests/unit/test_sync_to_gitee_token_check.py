"""
Contract tests for sync-to-gitee.yml's GITEE_TOKEN validation step.

Background
==========

The `Validate Gitee credentials` step in sync-to-gitee.yml is the
earliest diagnostic guard for the failure pattern

    fatal: could not read Username for https://gitee.com:
    terminal prompts disabled

which fires when GITEE_TOKEN is empty/unset and `git push origin` falls
back to asking the terminal for credentials. The step's job is to fail
fast with a precise message pointing at Settings → Secrets → GITEE_TOKEN
rather than letting the git push die with exit-128 several seconds later.

Release-cn.yml has 5 copies of the same step (one per build-* job),
each with `set -euo pipefail` + `tr -d '\r\n'` cleaning + a SHA-256
fingerprint + a byte-length line. sync-to-gitee's copy used to be
the bare `if [ -z ... ]; then exit 1; fi` form without any of that
chrome, which made cross-workflow log triage inconsistent: an
operator reading sync-to-gitee logs could not match the
"[OK] GITEE_TOKEN present (length=N bytes, sha256=xxxxxxxx)" line
they were used to seeing in release-cn's logs.

These tests pin the contract:

  1. sync-to-gitee's `Validate Gitee credentials` step has
     `set -euo pipefail` as its first body line.
  2. The step computes the cleaned token (`tr -d '\r\n'`),
     SHA-256 fingerprint, and length — the same trio as release-cn.
  3. The `[OK]` log line emits both length and sha256 — the same
     format as release-cn.
  4. The unset-token diagnostic uses `::error::` (so it appears
     red in the GitHub Actions UI summary).
  5. The `set -euo pipefail` line is *not* indented as if it were
     inside the `if` block. (A previous form accidentally indented
     it 10 spaces, which would still parse fine but mismatch the
     `if`-then-fi alignment — a subtle "code smell" that future
     readers would copy.)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SYNC = REPO / ".github/workflows/sync-to-gitee.yml"
CN = REPO / ".github/workflows/release-cn.yml"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# sync-to-gitee.yml — Validate Gitee credentials step
# ---------------------------------------------------------------------------

def _validate_step_body(text: str) -> str:
    """Return the body (after `run: |`) of the Validate Gitee
    credentials step in sync-to-gitee.yml. Used by all the
    structural tests below.
    """
    # The step body follows `run: |\n` which appears AFTER a block
    # of comments. Walk forward from `- name: Validate Gitee
    # credentials` until we hit `run: |` and capture everything
    # after it as the body.
    m = re.search(r"- name: Validate Gitee credentials", text)
    assert m, "sync-to-gitee.yml: could not locate `Validate Gitee credentials` step"
    run_match = re.search(r"run: \|\n", text[m.end():])
    assert run_match, (
        "sync-to-gitee.yml: Validate Gitee credentials step has no `run: |` "
        "block — the step body is malformed."
    )
    body_start = m.end() + run_match.end()
    # Find the next step's `- name:` at the same indent (6 spaces).
    next_step = re.search(r"\n      - name:", text[body_start:])
    body_end = body_start + next_step.start() if next_step else len(text)
    return text[body_start:body_end]


def test_sync_validate_step_uses_strict_mode():
    """The step body must begin with `set -euo pipefail` to match
    release-cn.yml's same step. This pins the operator-facing
    diagnostic to the same format across both workflows.
    """
    body = _validate_step_body(_read(SYNC))
    first_nonblank = next((ln for ln in body.splitlines() if ln.strip()), "")
    assert first_nonblank.strip() == "set -euo pipefail", (
        f"sync-to-gitee.yml: Validate Gitee credentials step must "
        f"begin with `set -euo pipefail` (10-space indented), but "
        f"first body line is {first_nonblank!r}. Without it, an "
        f"intermediate command failure (e.g. `sha256sum` missing on "
        f"a stripped image) would silently continue and the GITEE_TOKEN "
        f"validation would look successful when it isn't."
    )


def test_sync_validate_step_computes_clean_fpr_len():
    """The step must compute CLEAN, FPR, and LEN exactly the same
    way as release-cn.yml so cross-workflow log triage is uniform.
    """
    body = _validate_step_body(_read(SYNC))
    for marker in (
        "CLEAN=$(printf '%s' \"$GITEE_TOKEN\" | tr -d '\\r\\n')",
        "FPR=$(printf '%s' \"$CLEAN\" | sha256sum | cut -c1-8)",
        "LEN=$(printf '%s' \"$CLEAN\" | wc -c | tr -d ' ')",
    ):
        assert marker in body, (
            f"sync-to-gitee.yml: Validate Gitee credentials step is "
            f"missing line: {marker!r}. release-cn.yml has this exact "
            f"trio in all 5 of its Validate steps; sync-to-gitee.yml "
            f"should match so log lines look identical across workflows."
        )


def test_sync_validate_step_emits_length_and_sha256():
    """The `[OK]` log line must include both `length=${LEN}` and
    `sha256=${FPR}`. Operators triage token-rotation issues by
    matching these two fields; if sync-to-gitee omits sha256 they
    get a false "different token?" false alarm.
    """
    body = _validate_step_body(_read(SYNC))
    ok_line = next((ln for ln in body.splitlines() if '"[OK] GITEE_TOKEN present' in ln), None)
    assert ok_line is not None, (
        "sync-to-gitee.yml: Validate Gitee credentials step is missing "
        "the `[OK] GITEE_TOKEN present` log line."
    )
    assert "length=${LEN}" in ok_line, (
        f"sync-to-gitee.yml: [OK] line missing `length=${LEN}`: {ok_line!r}"
    )
    assert "sha256=${FPR}" in ok_line, (
        f"sync-to-gitee.yml: [OK] line missing `sha256=${FPR}`: {ok_line!r}"
    )


def test_sync_validate_step_uses_error_annotation_when_unset():
    """The empty-token branch must use `::error::` so it shows up
    red in the GitHub Actions UI summary — not just a plain `echo`.
    Without this annotation, an operator scrolling through the
    job log might miss the diagnostic and only see the later
    git-push failure.
    """
    body = _validate_step_body(_read(SYNC))
    assert '::error::' in body, (
        "sync-to-gitee.yml: Validate Gitee credentials step must "
        "use `echo \"::error::...\"` for the empty-token branch "
        "so the failure surfaces in the GHA UI summary."
    )


def test_sync_validate_step_messages_match_release_cn_pattern():
    """The `::error::` message should still mention GITEE_TOKEN and
    gitee.com (the symptom keywords operators grep for) even after
    the refactor.
    """
    body = _validate_step_body(_read(SYNC))
    err_line = next((ln for ln in body.splitlines() if '::error::' in ln), None)
    assert err_line is not None
    assert "GITEE_TOKEN" in err_line
    assert "gitee.com" in err_line


# ---------------------------------------------------------------------------
# release-cn.yml — same step format (regression guard so we don't
# silently diverge the two workflows again).
# ---------------------------------------------------------------------------

def test_release_cn_validate_step_count():
    """release-cn.yml has 5 build jobs (windows, linux, macos-amd64,
    macos-aarch64, and a 5th). Each must have a Validate Gitee
    credentials step in the same format. If this drops below 4,
    someone removed a build job without removing its token check.
    """
    text = _read(CN)
    n = len(re.findall(r"- name: Validate Gitee credentials", text))
    assert n >= 4, (
        f"release-cn.yml: expected at least 4 'Validate Gitee credentials' "
        f"steps (one per build-* job), found {n}. If you removed a build "
        f"job, remove its token-validation step too — leaving it dangling "
        f"silently disables a useful diagnostic."
    )


def test_release_cn_validate_steps_all_strict_mode():
    """Every Validate Gitee credentials step in release-cn.yml must
    start with `set -euo pipefail` as its first body line.
    """
    text = _read(CN)
    matches = list(re.finditer(
        r"- name: Validate Gitee credentials.*?run: \|\n",
        text,
        flags=re.DOTALL,
    ))
    assert matches, "release-cn.yml: no Validate Gitee credentials steps found"
    for i, m in enumerate(matches):
        # The body starts on the line after the `run: |` match.
        body_start = m.end()
        # Find the next blank-line-or-dedent that ends this step.
        body_end = text.find("\n      - name:", body_start)
        if body_end == -1:
            body_end = len(text)
        body = text[body_start:body_end]
        first_nonblank = next((ln for ln in body.splitlines() if ln.strip()), "")
        assert first_nonblank.strip() == "set -euo pipefail", (
            f"release-cn.yml: Validate Gitee credentials step #{i+1} "
            f"first body line is {first_nonblank!r}, expected "
            f"`set -euo pipefail`."
        )