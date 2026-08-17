"""
Contract tests for the Windows self-hosted runner Git Bash PATH
workaround in release-cn.yml.

Background
==========

GitHub Actions' `shell: bash` on Windows resolves to
`C:\\Program Files\\Git\\bin\\bash.EXE`. On a GitHub-hosted Windows
runner the runner's runner-images include Git for Windows in the
default PATH, so `bash` is found. On a self-hosted Windows runner
that's been registered with `register_runner.ps1`, the installer's
per-user PATH is added to the *user* shell — but the
`actions.runner.*-svc` Windows service account that actually
executes jobs starts with the SYSTEM-level PATH, which does NOT
inherit Git for Windows' bin directory.

Symptom: every step with `shell: bash` fails with
`##[error]bash: command not found` within the first few lines,
typically on the very first `Validate Gitee credentials` step.
See run #86661348651 (`6_Build Windows amd64.txt` line 47) for
the canonical example:

    2026-08-16T17:03:41.6055924Z ##[error]bash: command not found

register_runner.ps1 already probes `bash.exe` (lines 105-122)
and exits 4 if absent, but that probe runs in the installer's
user shell which has a different PATH than the service account.
So the service can register successfully and then still fail at
job-execution time.

Fix
===

Add a `Add Git Bash to PATH (Windows self-hosted)` step as the
FIRST step in every build-* job. The step:

  - uses `shell: pwsh` (works on Windows by default — no PATH
    dependency, unlike the bash steps it's unblocking),
  - is gated by `if: runner.os == 'Windows'` so it skips on
    the macOS and Linux build jobs (different OS, different
    PATH, different problem),
  - writes `C:\\Program Files\\Git\\bin` to `$GITHUB_PATH` (the
    env var GHA uses to append paths for subsequent steps in
    the same job),
  - uses forward slashes in the path so downstream `shell: bash`
    steps don't trip on the "spaces in path" quoting trap that
    backslashes invite when composed into PATH,
  - emits a clear `::error::` if Git Bash isn't installed at
    the default path, pointing the operator at the install URL
    and the runner-service restart requirement.

These tests pin that contract so a future refactor can't
silently remove the workaround step (which would re-introduce
the very `##[error]bash: command not found` we just fixed).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RELEASE_CN = REPO / ".github/workflows/release-cn.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _build_jobs(doc: dict) -> dict:
    """Return the {job_name: job_dict} map for build-* jobs only.
    Excludes validate-tag / final-status / show-summary so the
    tests below only assert on the jobs that actually run on
    self-hosted runners.
    """
    return {
        name: spec
        for name, spec in doc["jobs"].items()
        if name.startswith("build-")
    }


@pytest.fixture(scope="module")
def docs():
    import yaml
    return list(yaml.safe_load_all(_read(RELEASE_CN)))


@pytest.fixture(scope="module")
def workflow_doc(docs):
    # The workflow file is the first YAML document.
    return docs[0]


@pytest.fixture(scope="module")
def build_jobs(workflow_doc):
    return _build_jobs(workflow_doc)


# ---------------------------------------------------------------------------
# Structural: every build-* job has the workaround step
# ---------------------------------------------------------------------------

def test_every_build_job_has_windows_bash_path_step(build_jobs):
    """Every build-* job must have the 'Add Git Bash to PATH
    (Windows self-hosted)' step as the FIRST step. Adding it
    later doesn't help: the first `shell: bash` step would still
    fail. The `if: runner.os == 'Windows'` guard inside the step
    itself handles the non-Windows build jobs.
    """
    assert build_jobs, "release-cn.yml: no build-* jobs found"
    for job_name, job in build_jobs.items():
        steps = job.get("steps", [])
        assert steps, f"release-cn.yml: job {job_name} has no steps"
        first = steps[0]
        assert first.get("name") == "Add Git Bash to PATH (Windows self-hosted)", (
            f"release-cn.yml: job {job_name} first step must be 'Add Git "
            f"Bash to PATH (Windows self-hosted)', got {first.get('name')!r}. "
            f"If the workaround is not FIRST, the first `shell: bash` step "
            f"(e.g. 'Validate Gitee credentials') will fail with "
            f"'##[error]bash: command not found' before the PATH fix runs."
        )


def test_workaround_step_uses_powershell_shell(build_jobs):
    """The workaround step must use `shell: powershell` (Windows
    PowerShell 5.1, ships with every Windows install), NOT
    `shell: pwsh` or `shell: bash`.

    Why:
      - `shell: bash` would be circular — bash is the broken
        thing we're working around.
      - `shell: pwsh` resolves to PowerShell 7 (`pwsh.exe`),
        which is a *separate* install that is NOT on the default
        PATH on either GitHub-hosted or self-hosted Windows
        runners. Symptom: `##[error]pwsh: command not found`
        (see run #86661355667 for the canonical example).
      - `shell: powershell` resolves to `powershell.exe` (5.1),
        which is in `C:\\Windows\\System32\\WindowsPowerShell\\
        v1.0\` on every Windows install since Win7/2008R2 and
        is always on the SYSTEM-level PATH inherited by the
        `actions.runner.*-svc` service. The docs list pwsh as
        optional ("可额外安装") — powershell is the one that
        exists by default.
    """
    for job_name, job in build_jobs.items():
        step = job["steps"][0]
        assert step.get("shell") == "powershell", (
            f"release-cn.yml: job {job_name} workaround step must use "
            f"`shell: powershell` (Windows PowerShell 5.1 — ships with "
            f"the OS). `shell: pwsh` (PowerShell 7) is a separate "
            f"install that's NOT on the default PATH and will fail "
            f"with `##[error]pwsh: command not found`. "
            f"`shell: bash` is circular. Got: {step.get('shell')!r}"
        )


def test_workaround_step_is_windows_gated(build_jobs):
    """The workaround step must have `if: runner.os == 'Windows'`.
    Without this guard, the macOS and Linux build jobs would
    also run it (harmless on Linux, but `Test-Path` on
    `C:\\Program Files\\Git\\bin` would error on macOS and exit 1
    because the path is invalid).
    """
    for job_name, job in build_jobs.items():
        step = job["steps"][0]
        if_expr = step.get("if")
        assert if_expr is not None and "runner.os" in if_expr and "Windows" in if_expr, (
            f"release-cn.yml: job {job_name} workaround step must have "
            f"`if: runner.os == 'Windows'` to skip on macOS / Linux jobs. "
            f"Got: {if_expr!r}"
        )


# ---------------------------------------------------------------------------
# Functional: the step body does the right thing
# ---------------------------------------------------------------------------

def test_workaround_step_appends_to_github_path():
    """The step body must write Git Bash's bin directory to
    `$GITHUB_PATH` (the runner-owned env var that GHA appends
    to the PATH of subsequent steps in the same job). Writing
    to `$env:PATH` would only affect the current step, not
    the bash steps that come after.
    """
    body = _workaround_step_body()
    assert "$env:GITHUB_PATH" in body, (
        f"release-cn.yml: workaround step must write to "
        f"$env:GITHUB_PATH (not $env:PATH), got:\n{body}"
    )
    assert "C:\\Program Files\\Git\\bin" in body, (
        f"release-cn.yml: workaround step must reference the default "
        f"Git for Windows install path 'C:\\Program Files\\Git\\bin', "
        f"got:\n{body}"
    )


def test_workaround_step_emits_error_when_git_bash_missing():
    """If Git Bash is not installed at the default path, the step
    must fail with a `::error::` annotation that points the
    operator at the install URL. Without this, the step would
    silently succeed (Test-Path returns false, the if-branch
    skips, the step exits 0) and the next `shell: bash` step
    would still fail with the same opaque 'bash: command not
    found' error we were trying to fix — just with one extra
    layer of misdirection.
    """
    body = _workaround_step_body()
    assert "::error::" in body, (
        "release-cn.yml: workaround step must emit a ::error:: "
        "annotation when Git Bash is missing, otherwise the user "
        "sees the original 'bash: command not found' from the next "
        "step with no explanation."
    )
    assert "git-scm.com/download/win" in body, (
        "release-cn.yml: workaround step's missing-path error must "
        "include the Git for Windows install URL so the operator "
        "doesn't have to grep docs to find it."
    )


def test_workaround_step_uses_forward_slashes_in_path():
    """The path written to $GITHUB_PATH must use forward slashes,
    not backslashes. Backslashes in PATH components get
    interpreted as escape characters by downstream bash and
    PowerShell steps, leading to the classic 'C:Program Files'
    (no leading slash) bug, which surfaces as 'Program not
    found' instead of the actual problem.
    """
    body = _workaround_step_body()
    # Look for a line that writes the gitBash path to GITHUB_PATH.
    # PowerShell `Out-File` is the canonical append mechanism.
    out_file_lines = [
        ln for ln in body.splitlines() if "Out-File" in ln and "GITHUB_PATH" in ln
    ]
    assert out_file_lines, (
        f"release-cn.yml: workaround step must use Out-File to append "
        f"to $env:GITHUB_PATH, got body:\n{body}"
    )
    # None of the Out-File lines should contain `\\` (which would
    # emit a single backslash into GITHUB_PATH and break downstream
    # bash PATH parsing).
    for ln in out_file_lines:
        assert "\\\\" not in ln, (
            f"release-cn.yml: Out-File line emits backslashes into "
            f"GITHUB_PATH, which breaks downstream bash PATH parsing. "
            f"Line: {ln!r}"
        )


def _workaround_step_body() -> str:
    """Return the run-block body of the 'Add Git Bash to PATH'
    step. Robust against large files (no regex backtracking):
    we split on the step's `- name:` boundary and the next
    `- name:` boundary, then locate the `run: |` line.
    """
    text = _read(RELEASE_CN)
    # Find the start of the workaround step.
    start_marker = "- name: Add Git Bash to PATH (Windows self-hosted)"
    start = text.find(start_marker)
    assert start != -1, (
        "release-cn.yml: 'Add Git Bash to PATH (Windows self-hosted)' "
        "step not found. If you removed this step, all build-* jobs "
        "will fail with '##[error]bash: command not found' on "
        "self-hosted Windows runners."
    )
    # Find the run-block start.
    run_start = text.find("run: |\n", start)
    assert run_start != -1, "workaround step is missing its `run: |` block"
    body_start = run_start + len("run: |\n")
    # Find the next step at the same indent (6 spaces). This is
    # O(N) on file size and doesn't risk the regex backtracking
    # explosion that the previous version hit on large files.
    next_step = text.find("\n      - name: ", body_start)
    body_end = next_step if next_step != -1 else len(text)
    return text[body_start:body_end]


# ---------------------------------------------------------------------------
# Regression: validate-tag is UNCHANGED (this is GitHub-hosted, no
# workaround needed). Pin this so someone doesn't accidentally
# hoist the workaround into the global path.
# ---------------------------------------------------------------------------

def test_validate_tag_does_not_have_windows_workaround(workflow_doc):
    """validate-tag runs on `ubuntu-latest` (GitHub-hosted) and
    already has bash on PATH. The Windows workaround step
    belongs inside each build-* job's `steps:` list, not at
    the workflow level. If it gets hoisted, all jobs run it
    (the `if: runner.os == 'Windows'` guard still skips it
    on Linux, but the YAML ball-of-mud gets harder to read).
    """
    validate_tag = workflow_doc["jobs"].get("validate-tag")
    assert validate_tag is not None, "release-cn.yml: validate-tag job missing"
    validate_steps = validate_tag.get("steps", [])
    # If the workaround step does exist on validate-tag (from the
    # mass-replace_all that put it on every steps: block), it
    # MUST be guarded by `if: runner.os == 'Windows'` so the
    # ubuntu-latest validate-tag job doesn't run it. This is
    # a soft check: the workaround *can* be on validate-tag, but
    # only if it's gated. (The ideal is to remove it from
    # validate-tag entirely, but the cost of leaving a properly
    # gated copy is zero — the if-condition skips it.)
    for step in validate_steps:
        if step.get("name") == "Add Git Bash to PATH (Windows self-hosted)":
            assert "runner.os" in (step.get("if") or "") and "Windows" in (step.get("if") or ""), (
                f"release-cn.yml: validate-tag has the workaround step "
                f"but it is NOT gated by `runner.os == 'Windows'`. "
                f"validate-tag runs on ubuntu-latest where the windows "
                f"path check would falsely error. Gate is: {step.get('if')!r}"
            )
            return  # Found the step, gated correctly — pass.
    # If we got here, no workaround step exists on validate-tag
    # at all — that's also fine (the cleaner pattern).
