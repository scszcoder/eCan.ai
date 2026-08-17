"""
Contract tests for the Windows self-hosted runner baseline.

Background
==========

The repo has two runner classes:

  * GitHub-hosted `windows-latest` runner — ships with both
    PowerShell 7 (`pwsh.exe`) and Git for Windows on PATH.
    The rest of release-cn.yml uses `shell: pwsh` (PowerShell 7,
    modern syntax) and `shell: bash` (Git Bash) freely.

  * Self-hosted Windows runner registered via
    `register_runner.ps1` — only ships with PowerShell 5.1
    (`powershell.exe`) on PATH. No `pwsh`, no Git Bash on
    the runner service PATH.

This is a **baseline mismatch**, not a workflow bug. The
project standardizes on `windows-latest` semantics in the
workflow. The self-hosted runner is brought to the same
baseline by two layers, both **idempotent**:

  1. **On the runner, once** (operator setup, see
     `docs/Windows构建环境部署清单.md` §九.3.1): install
     PowerShell 7 + Git for Windows; add
     `C:\\Program Files\\Git\\bin` to SYSTEM PATH; restart
     the runner service.

  2. **Per job, as the first step** (workflow preflight):
     `Ensure Git Bash + PowerShell 7 are on runner-service
     PATH`. Detects the two binaries; if missing, installs
     via winget (or MSI fallback for PowerShell 7). If both
     are already there, the step is a 2-line no-op.

The preflight exists so:
  - A runner that was registered without §九.3.1 still
    picks up the missing pieces the first time a job runs.
  - A runner image that's re-provisioned doesn't require
    a separate "install baseline" Ansible/Packer step.

The preflight is intentionally not the recommended way to
set up the runner — it costs a `winget install` per first
job and clutters `$env:TEMP` with MSI downloads. The docs
§九.3.1 explicitly says: "强烈建议 在 `register_runner.ps1`
跑完后提前装好...这样 workflow 的 preflight step 跑得快
(只 `where.exe` 一次就 `[OK]`...)" — operator path is
preferred, preflight is the safety net.

These tests pin the contract so a future refactor can't
silently remove the preflight's idempotency, the §九.3.1
docs guidance, or the workflow's shell assumptions without
realizing the self-hosted runner depends on them.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DOCS_FILE = REPO / "docs/Windows构建环境部署清单.md"
WORKFLOW_FILE = REPO / ".github/workflows/release-cn.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Workflow: preflight step is idempotent and present on every self-hosted job
# ---------------------------------------------------------------------------

PREFLIGHT_STEP_NAME = (
    "Ensure Git Bash + PowerShell 7 are on runner-service PATH "
    "(Windows self-hosted)"
)


def _self_hosted_jobs_using_pwsh_or_bash() -> list[tuple[str, dict]]:
    """Return [(job_name, job)] for every job that targets a
    self-hosted Windows runner AND uses at least one of
    `shell: pwsh` or `shell: bash`. The preflight is only
    required for those jobs — a job that ONLY uses
    `shell: powershell` (5.1, always present on Windows)
    or no shell at all doesn't depend on the preflight.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    out = []
    for job_name, job in wf.get("jobs", {}).items():
        runs_on = job.get("runs-on")
        # `runs-on` may be a string or a list / list of lists.
        # Normalize to a flat list of strings for the lookup.
        flat = []
        if isinstance(runs_on, str):
            flat.append(runs_on)
        elif isinstance(runs_on, list):
            for item in runs_on:
                if isinstance(item, str):
                    flat.append(item)
                elif isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str):
                            flat.append(v)
                        elif isinstance(v, list):
                            flat.extend(v)
        elif isinstance(runs_on, dict):
            for v in runs_on.values():
                if isinstance(v, str):
                    flat.append(v)
                elif isinstance(v, list):
                    flat.extend(v)
        # Skip jobs that aren't on self-hosted Windows.
        if not any("self-hosted" in s for s in flat):
            continue
        if not any("windows" in s.lower() for s in flat):
            continue
        # Skip jobs that don't use pwsh / bash — they don't
        # depend on the preflight. (E.g., `print-gha-fallback-
        # downloads` uses GitHub-default bash but may also
        # target ubuntu-latest via runner_group input — its
        # only Windows target has no `shell:` at all, so it
        # runs the default `bash` but that's already covered
        # by GitHub's hosted runner PATH for the windows
        # case; if a fresh self-hosted runner is the target,
        # this test would need to be revisited.)
        shells = {
            s.get("shell")
            for s in job.get("steps", [])
            if s.get("shell") is not None
        }
        if not (shells & {"pwsh", "bash"}):
            continue
        out.append((job_name, job))
    return out


def test_preflight_step_present_on_every_self_hosted_windows_job():
    """Every self-hosted Windows job that uses `shell: pwsh`
    or `shell: bash` must have the idempotent preflight step.
    The preflight installs Git Bash + PowerShell 7 if missing
    so `shell: bash` / `shell: pwsh` downstream steps don't
    fail with `##[error]command not found` on a runner that
    was registered without §九.3.1 prep.

    Jobs that only use `shell: powershell` (5.1, ships with
    every Windows install) or no shell at all don't depend
    on the preflight — they're excluded.
    """
    targets = _self_hosted_jobs_using_pwsh_or_bash()
    assert targets, (
        "release-cn.yml: no self-hosted Windows job uses "
        "`shell: pwsh` or `shell: bash` — the contract this "
        "test pins is moot. Either the shell choices changed "
        "(and the preflight should be removed), or the matrix "
        "labels changed (update _self_hosted_jobs_using_pwsh_"
        "or_bash)."
    )
    missing = []
    for job_name, job in targets:
        step_names = [s.get("name", "") for s in job.get("steps", [])]
        if not any(PREFLIGHT_STEP_NAME in n for n in step_names):
            missing.append(job_name)
    assert not missing, (
        "release-cn.yml: preflight step "
        f"'{PREFLIGHT_STEP_NAME}' missing from self-hosted "
        f"Windows jobs: {missing}. The preflight installs Git "
        "Bash + PowerShell 7 if missing (idempotent: "
        "`where.exe` first, `winget install` only on miss). "
        "Without it, jobs that depend on `shell: bash` / "
        "`shell: pwsh` will fail on a runner that wasn't "
        "pre-populated per docs §九.3.1."
    )


def test_preflight_step_is_idempotent_skip_path():
    """The preflight step's run-block must short-circuit when
    both binaries are already present. If it doesn't, every
    job pays a `winget install` cost even on the happy path
    where the runner was already set up per §九.3.1. The
    contract is: present → `[OK]` + continue; absent →
    `winget install` → re-check → continue.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    step = None
    for job_name, job in wf.get("jobs", {}).items():
        for s in job.get("steps", []):
            if PREFLIGHT_STEP_NAME in s.get("name", ""):
                step = s
                break
        if step:
            break
    assert step is not None, "preflight step not found"
    run = step.get("run", "")
    # Each prerequisite must have a "skip if present" branch.
    assert "Test-Path" in run and "winget install" in run, (
        "release-cn.yml: preflight step must use `Test-Path` "
        "to detect a present binary and `winget install` as "
        "the install path. The contract is: present → skip "
        "(no `winget` call), absent → install. If the step "
        "always installs, it's not idempotent and every job "
        "pays 1-2 minutes of `winget` + MSI download cost."
    )
    # Both Git Bash and PowerShell 7 must be checked. The
    # step probes the binary path via Test-Path; we accept
    # either a literal `bash.exe` reference or a dynamic
    # Join-Path construction.
    assert "bash.exe" in run, (
        "release-cn.yml: preflight step must probe "
        "`bash.exe` for Git Bash. The path may be "
        "constructed (e.g., `Join-Path $gitBashDir "
        "'bash.exe'`) but the binary name `bash.exe` "
        "must appear in the run-block."
    )
    assert "pwsh.exe" in run, (
        "release-cn.yml: preflight step must probe "
        "`pwsh.exe` for PowerShell 7."
    )
    # Must probe the default install paths (not user-
    # overridable paths), so the contract pins WHERE the
    # expected install lives, not just THAT it lives
    # somewhere.
    assert "Program Files\\Git" in run or "Program Files\\\\Git" in run, (
        "release-cn.yml: preflight step must probe the "
        "default Git for Windows install path "
        "(`C:\\Program Files\\Git\\...`). Probing a "
        "configurable path means a misconfigured runner "
        "silently passes and the build fails 10 minutes "
        "in."
    )
    assert "Program Files\\PowerShell\\7" in run or "Program Files\\\\PowerShell\\\\7" in run, (
        "release-cn.yml: preflight step must probe the "
        "default PowerShell 7 install path "
        "(`C:\\Program Files\\PowerShell\\7\\pwsh.exe`)."
    )
    # Must use `shell: powershell` (5.1) — pwsh.exe may not
    # exist yet, so this step cannot depend on it.
    assert step.get("shell") == "powershell", (
        "release-cn.yml: preflight step must use "
        "`shell: powershell` (Windows PowerShell 5.1), not "
        "`shell: pwsh`. PowerShell 7 is one of the things "
        "this step is responsible for installing — using "
        "`pwsh` would be a chicken-and-egg failure on a "
        "fresh runner."
    )


def test_preflight_step_handles_install_failure_gracefully():
    """If `winget install` (and MSI fallback) both fail —
    e.g., winget not installed, network blocked, MSI URL
    404 — the preflight must exit 1 with a clear `::error::`
    message. It must NOT silently pass and let downstream
    `shell: pwsh` / `shell: bash` steps fail with cryptic
    `##[error]command not found` ten minutes into the job.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    run = ""
    for job_name, job in wf.get("jobs", {}).items():
        for s in job.get("steps", []):
            if PREFLIGHT_STEP_NAME in s.get("name", ""):
                run = s.get("run", "")
                break
        if run:
            break
    # At least one `::error::` + `exit 1` pattern per binary.
    assert run.count("::error::") >= 2, (
        "release-cn.yml: preflight step must emit "
        "`::error::...` and `exit 1` for EACH of Git Bash + "
        "PowerShell 7 install failures. One combined error "
        "message is acceptable but two separate ones (one "
        "per binary) is the contract — so the operator "
        "knows which one is broken."
    )
    assert "exit 1" in run, (
        "release-cn.yml: preflight step must `exit 1` on "
        "install failure, not silently continue. If it "
        "continues, downstream `shell: pwsh` / `shell: bash` "
        "steps will fail with `##[error]command not found` "
        "10 minutes into the build, and the root step won't "
        "show up as the failed step in the run UI."
    )


def test_preflight_step_guarded_by_runner_os_windows():
    """The preflight step must be `if: runner.os == 'Windows'`
    so it doesn't run (and try to install Windows-only
    packages) on macOS / Linux build jobs in the same
    matrix.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    for job_name, job in wf.get("jobs", {}).items():
        for s in job.get("steps", []):
            if PREFLIGHT_STEP_NAME in s.get("name", ""):
                # Self-hosted jobs must guard, otherwise the
                # step tries to run on non-Windows self-hosted
                # runners too.
                if "self-hosted" in str(job.get("runs-on", "")):
                    assert s.get("if") == "runner.os == 'Windows'", (
                        f"release-cn.yml: job '{job_name}' has the "
                        f"Windows preflight step without "
                        f"`if: runner.os == 'Windows'`. The step "
                        "must not run on macOS / Linux self-hosted "
                        "runners."
                    )


# ---------------------------------------------------------------------------
# Workflow: uses pwsh / bash shells (makes the preflight load-bearing)
# ---------------------------------------------------------------------------

def test_workflow_uses_pwsh_and_bash_shells():
    """The workflow uses `shell: pwsh` and `shell: bash` freely
    across build-* jobs. This is what makes the preflight
    necessary — without these shells, no preflight would be
    needed. The test pins the assumption so the docs /
    preflight stay load-bearing (a future refactor that
    switches everything to `shell: powershell` would
    invalidate §九.3.1 and the preflight — in that case,
    both should be slimmed down).
    """
    docs = list(yaml.safe_load_all(text := _read(WORKFLOW_FILE)))
    workflow = docs[0]
    shells_seen = set()
    for job_name, job in workflow.get("jobs", {}).items():
        if not job_name.startswith("build-"):
            continue
        for step in job.get("steps", []):
            shell = step.get("shell")
            if shell:
                shells_seen.add(shell)
    assert "pwsh" in shells_seen or "bash" in shells_seen, (
        "release-cn.yml: build-* jobs don't use `shell: pwsh` "
        "or `shell: bash` at all. If this is intentional, "
        "simplify docs/Windows构建环境部署清单.md §九.3.1 AND "
        "remove the preflight step — they're no longer "
        "load-bearing."
    )


# ---------------------------------------------------------------------------
# Docs: §一 基础清单 + §九.3.1
# ---------------------------------------------------------------------------

def test_baseline_table_marks_powershell_7_required():
    """§一 基础清单 must list PowerShell 7 (`pwsh.exe`) as a
    required prerequisite, because the preflight is a
    fallback (operator should pre-install) and the workflow
    uses `shell: pwsh` heavily. Without this row, an
    operator following §一 would not know to pre-install
    PowerShell 7.
    """
    text = _read(DOCS_FILE)
    base_section_start = text.find("## 一、基础清单")
    base_section_end = text.find("## 二、", base_section_start)
    assert base_section_start != -1, "docs: §一 基础清单 section missing"
    assert base_section_end != -1, "docs: §二 missing"
    base_section = text[base_section_start:base_section_end]
    assert "PowerShell 7" in base_section, (
        "docs/Windows构建环境部署清单.md: §一 基础清单 must list "
        "PowerShell 7 (`pwsh.exe`) as a required prerequisite."
    )
    assert "pwsh" in base_section, (
        "docs/Windows构建环境部署清单.md: §一 基础清单 must "
        "explicitly reference `pwsh.exe` so the operator knows "
        "what to install."
    )


def test_docs_3_1_section_exists():
    """§九.3.1 must exist. It is the operator-facing source
    of truth for the runner-side install (the workflow
    preflight is the job-side fallback; both are needed).
    """
    text = _read(DOCS_FILE)
    assert "### 3.1 Windows runner 必备工具" in text, (
        "docs/Windows构建环境部署清单.md: §九.3.1 Windows runner "
        "必备工具 section missing."
    )


def test_docs_3_1_documents_idempotent_preflight_contract():
    """§九.3.1 must explain the dual-layer contract:

      1. Operator should pre-install on the runner once
         (so the preflight is a no-op fast-path)
      2. Workflow preflight is idempotent: present → skip,
         absent → install

    This dual framing is what makes the contract clear:
    the operator knows that pre-installing is preferred
    but not strictly required (preflight is the safety
    net). Without this guidance, operators either:
      - skip pre-installing and rely on the preflight
        (slow first job), or
      - think they MUST pre-install and stop trusting the
        workflow preflight (which then becomes
        single-source-of-truth with no fallback).
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    # Must mention preflight by name.
    assert "Ensure Git Bash" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must reference "
        "the workflow preflight step (`Ensure Git Bash + "
        "PowerShell 7 ...`) so operators know it exists as a "
        "safety net. Got:\n" + block
    )
    # Must explain the idempotent contract.
    assert "幂等" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must explain "
        "that the preflight is idempotent. Without this, "
        "operators can't reason about whether pre-installing "
        "is faster than relying on the workflow. Got:\n" + block
    )
    # Must explain the operator path is preferred.
    assert "强烈建议" in block or "提前" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must say "
        "operator pre-install is the preferred path (with the "
        "preflight as fallback). Without this, operators "
        "either skip pre-install entirely (slow first job) "
        "or don't trust the preflight (no fallback). Got:\n"
        + block
    )


def test_docs_3_1_has_baseline_verification():
    """§九.3.1 must include copy-paste verification commands
    so the operator can confirm the baseline before
    triggering a build.
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    assert "where.exe pwsh.exe" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 verification "
        "must include `where.exe pwsh.exe`. Got:\n" + block
    )
    assert "where.exe bash.exe" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 verification "
        "must include `where.exe bash.exe`. Got:\n" + block
    )


def test_docs_3_1_documents_git_bash_system_path_fix():
    """§九.3.1 must still document the Git Bash SYSTEM PATH
    fix. The preflight adds Git Bash to `$GITHUB_PATH` for
    the *current job only*. The *runner service account's*
    SYSTEM PATH still doesn't have it, so anything operator-
    side that uses bash (manual debugging, other tools)
    won't find it. The doc keeps this guidance so operators
    don't have to keep re-adding it per job.
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    assert "C:\\Program Files\\Git\\bin" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must reference "
        "`C:\\Program Files\\Git\\bin` — the Git Bash PATH entry "
        "the operator needs to add to SYSTEM PATH once. "
        "Got:\n" + block
    )
    assert "svc.cmd" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must instruct "
        "the operator to restart the runner service (`svc.cmd "
        "stop / start`) after the PATH change so the new "
        "service process picks up the new PATH. Got:\n" + block
    )


def test_docs_troubleshooting_section_references_runner_baseline():
    """§六 排错 Checklist must include an entry for the
    PowerShell 7 / Git Bash baseline failures so when a
    self-hosted runner job fails with `command not found`,
    the operator's first stop is the checklist.
    """
    text = _read(DOCS_FILE)
    checklist_start = text.find("## 六、排错 Checklist")
    checklist_end = text.find("## 七、", checklist_start)
    checklist = text[checklist_start:checklist_end]
    assert "pwsh: command not found" in checklist, (
        "docs/Windows构建环境部署清单.md: §六 排错 Checklist must "
        "include an entry for `##[error]pwsh: command not "
        "found` pointing the operator at §九.3.1."
    )
    assert "bash: command not found" in checklist, (
        "docs/Windows构建环境部署清单.md: §六 排错 Checklist must "
        "include an entry for `##[error]bash: command not "
        "found` pointing the operator at §九.3.1."
    )
    assert "§九.3.1" in checklist, (
        "docs/Windows构建环境部署清单.md: §六 排错 Checklist must "
        "link to §九.3.1."
    )


# ---------------------------------------------------------------------------
# Workflow preflight: ExecutionPolicy detection (log #86728979772)
# ---------------------------------------------------------------------------

def test_preflight_step_detects_restricted_execution_policy():
    """The preflight step must detect PowerShell ExecutionPolicy
    `Restricted` on LocalMachine and emit a precise `::error::`
    pointing at register_runner.ps1 + §九.3.1.

    Background: GHA runner invokes `shell: powershell` steps via
    `powershell -command ". '<guid>.ps1'"` (dot-sources a temp
    file in `_work\\temp`). On a vanilla self-hosted Windows
    runner, the SYSTEM ExecutionPolicy is the in-box default
    `Restricted`, which rejects the dot-source with
    `UnauthorizedAccess` BEFORE any step body runs (real
    failure from log #86728979772, run 86728979772). The
    runner-side fix is in `register_runner.ps1` (sets
    `LocalMachine=RemoteSigned` + `svc.cmd restart`). The
    preflight's job is to detect this misconfiguration in
    advance and emit a clear error so the operator knows
    `register_runner.ps1` needs to be (re-)run, instead of
    failing with a cryptic `##[error]Process completed with
    exit code 1` 10 steps later.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    run = ""
    for job_name, job in wf.get("jobs", {}).items():
        for s in job.get("steps", []):
            if PREFLIGHT_STEP_NAME in s.get("name", ""):
                run = s.get("run", "")
                break
        if run:
            break
    assert "ExecutionPolicy" in run, (
        "release-cn.yml: preflight step must probe "
        "PowerShell ExecutionPolicy. Without this, the runner "
        "fails with `UnauthorizedAccess` on the dot-source of "
        "the inline script wrapper (log #86728979772), which "
        "is BEFORE the preflight body runs — so the preflight "
        "needs to actively detect (and fail with a clear "
        "message) rather than rely on being able to run at "
        "all. Got:\n" + run
    )
    assert "Restricted" in run, (
        "release-cn.yml: preflight step must check for the "
        "`Restricted` execution policy and emit a clear "
        "`::error::` with the remediation pointer. Got:\n"
        + run
    )
    assert "register_runner.ps1" in run, (
        "release-cn.yml: preflight step's error message must "
        "point the operator at `register_runner.ps1` so they "
        "know where the runner-side fix lives. Without this "
        "pointer, the operator sees `Restricted` and doesn't "
        "know it's already automated. Got:\n" + run
    )


def test_preflight_step_does_not_set_execution_policy_inline():
    """The preflight step must NOT call `Set-ExecutionPolicy`
    inline. Why: the GHA runner invokes `shell: powershell`
    via `powershell -command ". '<guid>.ps1'"` — the
    dot-source of the temp file happens BEFORE the
    preflight body runs, so a `Set-ExecutionPolicy -Scope
    Process` override set inside the body is too late.
    Only an OS-level `LocalMachine` change (in
    `register_runner.ps1`) can fix this. The preflight
    should detect + diagnose, not paper over with a
    no-op override.

    Note: the error message can mention `Set-ExecutionPolicy`
    as remediation text for the operator (telling them to
    run it on the runner is fine). The contract is: the
    *step itself* must not invoke `Set-ExecutionPolicy` to
    silently change the running process's policy.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    run = ""
    for job_name, job in wf.get("jobs", {}).items():
        for s in job.get("steps", []):
            if PREFLIGHT_STEP_NAME in s.get("name", ""):
                run = s.get("run", "")
                break
        if run:
            break
    # The step must NOT have a top-level `Set-ExecutionPolicy`
    # call as a command line. It may appear in a `Write-Host`
    # error message (remediation text), but never as a
    # standalone command.
    # Strip out write-host blocks to find bare invocations.
    bare_calls = [
        line.strip()
        for line in run.splitlines()
        if line.strip().startswith("Set-ExecutionPolicy")
        and not line.strip().startswith("Write-Host")
        and not line.strip().startswith("#")
    ]
    assert not bare_calls, (
        "release-cn.yml: preflight step must NOT call "
        "`Set-ExecutionPolicy` as a command. "
        "`Set-ExecutionPolicy -Scope Process` is too late — "
        "the GHA runner's dot-source of "
        "`_work\\_temp\\<guid>.ps1` has already failed "
        "under `Restricted` BEFORE this step's body runs. "
        "The right place to fix ExecutionPolicy is "
        "`register_runner.ps1` (LocalMachine scope + "
        "svc.cmd restart). The preflight should detect + "
        "diagnose, not paper over. Got bare calls: "
        f"{bare_calls!r}"
    )


# ---------------------------------------------------------------------------
# register_runner.ps1: operator-side baseline
# ---------------------------------------------------------------------------

REGISTER_RUNNER_SCRIPT = (
    REPO / "build_system/scripts/runner/register_runner.ps1"
)


def test_register_runner_ps1_sets_localmachine_execution_policy():
    """register_runner.ps1 must set
    `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned
    -Scope LocalMachine -Force` so the runner service's
    child PowerShell processes can dot-source GHA's inline
    script wrapper. Without this, every `shell: powershell`
    step fails with `UnauthorizedAccess` (log #86728979772).
    The setting must be on `LocalMachine` scope (not
    `Process` / `CurrentUser`) because:
      - `Process` is too late (see
        test_preflight_step_does_not_set_execution_policy_inline)
      - `CurrentUser` only affects the operator's interactive
        shell, NOT the runner service's SYSTEM-account
        processes
    Only `LocalMachine` (and the registry writes it does)
    affect the SYSTEM account the runner service runs as.
    """
    text = _read(REGISTER_RUNNER_SCRIPT)
    assert "Set-ExecutionPolicy" in text, (
        "register_runner.ps1 must call `Set-ExecutionPolicy` "
        "to override the in-box `Restricted` policy on the "
        "runner. Without this, every `shell: powershell` "
        "step fails with `UnauthorizedAccess` on the inline "
        "script dot-source (log #86728979772). Got:\n"
        + text[-2000:]
    )
    assert "LocalMachine" in text, (
        "register_runner.ps1 must set ExecutionPolicy on "
        "`LocalMachine` scope (not `CurrentUser` / `Process`). "
        "Only `LocalMachine` affects the SYSTEM account the "
        "runner service runs as. Got:\n" + text[-2000:]
    )
    assert "RemoteSigned" in text, (
        "register_runner.ps1 must set ExecutionPolicy to "
        "`RemoteSigned` (not `Bypass`). `RemoteSigned` blocks "
        "unsigned internet scripts but allows the runner's "
        "local `_work\\_temp\\<guid>.ps1` dot-source — the "
        "right balance. `Bypass` would disable all signing "
        "checks. Got:\n" + text[-2000:]
    )


def test_register_runner_ps1_adds_git_bash_to_system_path():
    """register_runner.ps1 must add
    `C:\\Program Files\\Git\\bin` to SYSTEM PATH (Machine
    scope) so the `actions.runner.*-svc` service account
    — which inherits SYSTEM PATH — can find `bash.exe`.
    Git for Windows' installer only adds to user PATH,
    which the SYSTEM account doesn't see. This is the
    the second half of the runner-side baseline fix
    (the first being ExecutionPolicy).
    """
    text = _read(REGISTER_RUNNER_SCRIPT)
    assert "Git\\\\bin" in text or "Git\\bin" in text, (
        "register_runner.ps1 must add `C:\\Program Files\\Git\\bin` "
        "to SYSTEM PATH. Without this, the runner service's "
        "SYSTEM account never sees Git Bash — `shell: bash` "
        "steps fail with `##[error]bash: command not found`. "
        "Got:\n" + text[-2000:]
    )
    assert "SetEnvironmentVariable" in text, (
        "register_runner.ps1 must call `SetEnvironmentVariable` "
        "to write Git Bash to SYSTEM PATH. Got:\n"
        + text[-2000:]
    )


def test_register_runner_ps1_restarts_runner_service():
    """register_runner.ps1 must restart the runner service
    (`svc.cmd stop` + `svc.cmd start`) after the
    ExecutionPolicy + SYSTEM PATH changes. Both changes
    only take effect for NEW processes — the existing
    runner service process still has the old env. Without
    a restart, the next CI job still fails with the same
    `UnauthorizedAccess` / `bash: command not found` until
    the operator manually restarts the service.
    """
    text = _read(REGISTER_RUNNER_SCRIPT)
    # Check it's running both stop and start (not just one)
    assert "svc.cmd stop" in text or "svc stop" in text, (
        "register_runner.ps1 must stop the runner service "
        "(`svc.cmd stop`) after the baseline changes so its "
        "child processes pick up the new env on restart. "
        "Got:\n" + text[-2000:]
    )
    assert "svc.cmd start" in text or "svc start" in text, (
        "register_runner.ps1 must start the runner service "
        "(`svc.cmd start`) after stop. Got:\n" + text[-2000:]
    )


# ---------------------------------------------------------------------------
# Docs: ExecutionPolicy coverage
# ---------------------------------------------------------------------------

def test_docs_3_1_documents_execution_policy_baseline():
    """§九.3.1 must document the ExecutionPolicy baseline
    that `register_runner.ps1` enforces. Without this, an
    operator following §九.3.1 might miss the ExecutionPolicy
    step and have their first CI job fail with a cryptic
    `UnauthorizedAccess` instead of the documented
    `bash: command not found` / `pwsh: command not found`.
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    assert "ExecutionPolicy" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must mention "
        "PowerShell ExecutionPolicy. The preflight detects "
        "`Restricted` and points at this section — if this "
        "section is silent on ExecutionPolicy, the operator "
        "follows the doc to the letter and still hits the "
        "UnauthorizedAccess error. Got:\n" + block
    )
    assert "RemoteSigned" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must say "
        "`RemoteSigned` (not just `Bypass` or `Unrestricted`). "
        "`RemoteSigned` is the right balance: blocks unsigned "
        "internet scripts but allows the runner's local temp "
        "dot-source. Got:\n" + block
    )
    assert "register_runner.ps1" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must reference "
        "`register_runner.ps1` as the canonical way to apply "
        "the baseline, since the script does it all in one "
        "shot. Got:\n" + block
    )


def test_docs_verification_block_includes_execution_policy():
    """§九.3.1's verification block must include
    `Get-ExecutionPolicy -List` so the operator can confirm
    the baseline is set correctly without running a CI job.
    Without this, the operator installs `pwsh` + `Git Bash`
    but forgets ExecutionPolicy, and the next CI job fails.
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    assert "Get-ExecutionPolicy" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 verification "
        "must include `Get-ExecutionPolicy -List` so the "
        "operator can verify the ExecutionPolicy baseline "
        "post-install. Got:\n" + block
    )


# ---------------------------------------------------------------------------
# Workflow `shell: powershell` (PS5.1) blocks: no non-ASCII string literals
# ---------------------------------------------------------------------------

def test_shell_powershell_blocks_have_no_non_ascii_string_literals():
    """Every step with `shell: powershell` (Windows PowerShell 5.1)
    must keep its non-comment, non-blank lines ASCII-only. Why:

    GitHub Actions writes `run: |` blocks to a temp .ps1 file
    *without* a UTF-8 BOM and invokes them via
    `powershell -command ". '<guid>.ps1'"`. Windows PowerShell
    5.1 parses BOM-less files using the active ANSI code page
    (Windows-1252 on US-English runners), not UTF-8. The em
    dash (U+2014, UTF-8 bytes E2 80 94) ends with byte 0x94,
    which Windows-1252 maps to RIGHT DOUBLE QUOTATION MARK
    (U+201D). PowerShell treats that as a string terminator,
    so any em dash inside `"..."` or `'...'` causes a parse
    error (`The string is missing the terminator: "`) on the
    affected step — and the error points at the wrong line
    because PowerShell counts the bogus terminator as the
    end of the string.

    This bit `Build Windows installer` (line 1441) on
    2026-08-17 with exactly that symptom: a UTF-8 em dash
    in a `throw "...— setup-python-env ..."` was decoded
    as cp1252, the trailing 0x94 closed the string early,
    and the step aborted with `Process completed with exit
    code 1` BEFORE the `& $VenvPython build.py prod`
    line ever ran.

    `shell: pwsh` (PowerShell 7) defaults to BOM-less UTF-8
    for both reads and writes, so it's not affected. The
    fix is therefore: every `shell: powershell` step's
    string literals stay ASCII. Comments and blank lines
    can stay as-is — PowerShell skips comments before
    tokenizing strings, so the parser never sees them.

    Reference: see CLAUDE.md §3 (surgical changes) — this
    contract pins the parser boundary so a future refactor
    that copies an em-dash / smart-quote / Chinese-char /
    box-drawing string from a `shell: pwsh` step into a
    `shell: powershell` step fails this test instead of
    waiting to fail on CI at runtime.
    """
    docs = list(yaml.safe_load_all(_read(WORKFLOW_FILE)))
    wf = docs[0]
    import re
    shell_powershell_re = re.compile(r"\s*shell:\s*powershell\s*$")
    offenders = []
    for job_name, job in wf.get("jobs", {}).items():
        for step in job.get("steps", []):
            shell = step.get("shell")
            if shell is None or not shell_powershell_re.match(
                f"shell: {shell}\n"
            ):
                continue
            run = step.get("run", "")
            # Walk run-block lines; comments and blanks are
            # parser-irrelevant, so we only check code lines.
            for line_no, line in enumerate(run.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for col, ch in enumerate(line):
                    if ord(ch) > 127:
                        offenders.append(
                            (
                                job_name,
                                step.get("name", "<unnamed>"),
                                line_no,
                                col,
                                ch,
                                hex(ord(ch)),
                                line.rstrip()[:120],
                            )
                        )
    assert not offenders, (
        "release-cn.yml: `shell: powershell` (Windows "
        "PowerShell 5.1) steps must keep non-comment lines "
        "ASCII-only. GHA writes the run-block to a BOM-less "
        "temp .ps1 and invokes it via `powershell -command "
        "\". '<guid>.ps1'\"`. PS5.1 parses BOM-less files "
        "as the active ANSI codepage (Windows-1252), so any "
        "non-ASCII char inside a string literal closes it "
        "early: U+2014 (em dash, UTF-8 ...94) decodes as "
        "U+201D (RIGHT DOUBLE QUOTATION MARK), which "
        "PowerShell treats as a string terminator. The step "
        "then fails with `The string is missing the "
        "terminator: \"` before any code runs. Use ASCII "
        "(`-`, `--`, `->`, etc.) in `shell: powershell` "
        "string literals. `shell: pwsh` is unaffected "
        "(PowerShell 7 defaults to BOM-less UTF-8). Offending "
        "chars:\n"
        + "\n".join(
            f"  - job={o[0]} step='{o[1]}' run-line={o[2]} "
            f"col={o[3]} char={o[4]!r} ({o[5]}): {o[6]}"
            for o in offenders
        )
    )