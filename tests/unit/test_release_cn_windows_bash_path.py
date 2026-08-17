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
# As of the setup-delegation refactor, register_runner.ps1 no longer
# contains the install logic inline — it shells out to
# setup-prerequisites.ps1 (single source of truth, callable
# standalone by the operator). The setup-related contract tests
# below pin behaviors in setup-prerequisites.ps1 instead.
SETUP_PREREQUISITES_SCRIPT = (
    REPO / "build_system/scripts/runner/setup-prerequisites.ps1"
)


def test_register_runner_ps1_sets_localmachine_execution_policy():
    """Two contract points: (1) register_runner.ps1 DELEGATES setup
    to setup-prerequisites.ps1 (single source of truth — no DRY
    violation). (2) setup-prerequisites.ps1 sets
    `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope
    LocalMachine -Force` so the runner service's child PowerShell
    processes can dot-source GHA's inline script wrapper.
    Without this, every `shell: powershell` step fails with
    `UnauthorizedAccess` (log #86728979772).
    The setting must be on `LocalMachine` scope (not `Process` /
    `CurrentUser`) because:
      - `Process` is too late (see
        test_preflight_step_does_not_set_execution_policy_inline)
      - `CurrentUser` only affects the operator's interactive
        shell, NOT the runner service's SYSTEM-account processes
    Only `LocalMachine` (and the registry writes it does)
    affect the SYSTEM account the runner service runs as.
    """
    # (1) Delegation: register_runner.ps1 shells out to
    # setup-prerequisites.ps1 instead of inlining the setup logic.
    rr_text = _read(REGISTER_RUNNER_SCRIPT)
    assert "setup-prerequisites.ps1" in rr_text, (
        "register_runner.ps1 must delegate baseline setup to "
        "setup-prerequisites.ps1 (single source of truth, no "
        "DRY violation). Without this delegation the two scripts "
        "would drift apart — a previous audit found 4 identical "
        "bugs in each copy. Got:\n" + rr_text[-2500:]
    )
    assert "-File $siblingSetup -ForceRestart" in rr_text, (
        "register_runner.ps1 must invoke setup-prerequisites.ps1 "
        "with -ForceRestart so the runner service re-reads env "
        "on its next start. Got:\n" + rr_text[-2500:]
    )
    # (2) The setup script actually does the work.
    setup_text = _read(SETUP_PREREQUISITES_SCRIPT)
    assert "Set-ExecutionPolicy" in setup_text, (
        "setup-prerequisites.ps1 must call `Set-ExecutionPolicy` "
        "to override the in-box `Restricted` policy on the "
        "runner. Without this, every `shell: powershell` step "
        "fails with `UnauthorizedAccess`. Got:\n" + setup_text[-2000:]
    )
    assert "LocalMachine" in setup_text, (
        "setup-prerequisites.ps1 must set ExecutionPolicy on "
        "`LocalMachine` scope (not `CurrentUser` / `Process`). "
        "Only `LocalMachine` affects the SYSTEM account the "
        "runner service runs as. Got:\n" + setup_text[-2000:]
    )
    assert "RemoteSigned" in setup_text, (
        "setup-prerequisites.ps1 must set ExecutionPolicy to "
        "`RemoteSigned` (not `Bypass`). `RemoteSigned` blocks "
        "unsigned internet scripts but allows the runner's "
        "local `_work\\_temp\\<guid>.ps1` dot-source — the "
        "right balance. Got:\n" + setup_text[-2000:]
    )


def test_register_runner_ps1_adds_git_bash_to_system_path():
    """Two contract points: (1) register_runner.ps1 delegates to
    setup-prerequisites.ps1. (2) setup-prerequisites.ps1 adds
    `C:\\Program Files\\Git\\bin` to SYSTEM PATH (Machine
    scope) so the `actions.runner.*-svc` service account
    — which inherits SYSTEM PATH — can find `bash.exe`.
    Git for Windows' installer only adds to user PATH,
    which the SYSTEM account doesn't see.
    """
    # (1) Delegation
    rr_text = _read(REGISTER_RUNNER_SCRIPT)
    assert "setup-prerequisites.ps1" in rr_text
    # (2) PATH write. The path is built via Join-Path
    # `$gitBashInstallDir 'bin'`, so the literal "Git\\bin"
    # substring doesn't appear directly — but $gitBashDir
    # does, and that's what gets appended to SYSTEM PATH.
    setup_text = _read(SETUP_PREREQUISITES_SCRIPT)
    assert "$gitBashDir" in setup_text, (
        "setup-prerequisites.ps1 must reference `$gitBashDir` "
        "(which resolves to `C:\\Program Files\\Git\\bin`) when "
        "writing SYSTEM PATH. Got:\n" + setup_text[-2500:]
    )
    assert "SetEnvironmentVariable" in setup_text, (
        "setup-prerequisites.ps1 must call `SetEnvironmentVariable` "
        "to write Git Bash to SYSTEM PATH. Got:\n"
        + setup_text[-2500:]
    )


def test_register_runner_ps1_auto_installs_git_for_windows_if_missing():
    """Two contract points: (1) register_runner.ps1 delegates to
    setup-prerequisites.ps1. (2) setup-prerequisites.ps1
    auto-installs Git for Windows when `C:\\Program Files\\Git\\bin\\bash.exe`
    is not present. docs §九.3.1 line 382 contract: the operator
    table says register_runner.ps1 "auto-installs" Git for
    Windows — this is now implemented by delegation rather than
    by inline code.

    Why symmetric matters: pwsh absent = every `shell: pwsh`
    step fails with `pwsh: command not found`. Git Bash
    absent = every `shell: bash` step fails with the same.
    Both fail in 30 seconds into the build, masking the real
    root cause. The preflight step in release-cn.yml is a
    per-job fallback safety net; the canonical install
    path is now setup-prerequisites.ps1.

    Test pins: `Test-Path $gitBashBin` (probes bash.exe specifically,
    not just the bin directory — bin/ can exist without bash.exe on
    a corrupt partial install) then else-branch that downloads +
    runs the Git for Windows installer via `Invoke-WebRequest` +
    `Start-Process` with the Inno Setup silent-install flags.
    """
    # (1) Delegation
    rr_text = _read(REGISTER_RUNNER_SCRIPT)
    assert "setup-prerequisites.ps1" in rr_text
    # (2) Git install logic now lives in setup-prerequisites.ps1
    setup_text = _read(SETUP_PREREQUISITES_SCRIPT)
    assert "Test-Path $gitBashBin" in setup_text, (
        "setup-prerequisites.ps1 must probe `C:\\Program Files\\Git\\bin\\bash.exe` "
        "specifically (not the bin directory) before deciding to install. "
        "Got:\n" + setup_text[-3000:]
    )
    assert "git-for-windows/git/releases/download" in setup_text, (
        "setup-prerequisites.ps1 must auto-download Git for Windows "
        "from the official git-for-windows GitHub release when "
        "`C:\\Program Files\\Git\\bin\\bash.exe` is missing. "
        "Got:\n" + setup_text[-3000:]
    )
    assert "/VERYSILENT" in setup_text, (
        "setup-prerequisites.ps1 must use `/VERYSILENT` (Inno Setup "
        "silent-install flag) when invoking Git-Setup.exe. "
        "Got:\n" + setup_text[-3000:]
    )
    # /DIR must point to the install TARGET dir (= parent of bin/),
    # not bin/ itself. The previous code used /DIR$gitBashDir which
    # was silently ignored by Inno Setup, falling back to its
    # default. Pin it explicitly.
    assert '"/DIR$gitBashInstallDir"' in setup_text, (
        "setup-prerequisites.ps1 must pin the install target "
        "dir via `/DIR$gitBashInstallDir` (= the parent of "
        "bin/, e.g. `C:\\Program Files\\Git`) — NOT "
        "`/DIR$gitBashDir` (which is bin/ and Inno Setup "
        "silently ignores). Without this pin, a future "
        "Inno-Setup / Git-for-Windows behavior change could "
        "shift the install dir and break the preflight's "
        "Test-Path probe. Got:\n" + setup_text[-3000:]
    )
    # Post-install verify: re-probe bash.exe after the installer
    # returns. Without this, a silently-failing installer (exit 0
    # but no files on disk) would let the script continue thinking
    # Git Bash is present. setup-prerequisites.ps1 uses the
    # positive form `if (Test-Path $gitBashBin) { Log ... } else {
    # Fail ... }` rather than the negated form used by pwsh and
    # choco — functionally equivalent.
    assert (
        "if (Test-Path $gitBashBin)" in setup_text
        or "if (-not (Test-Path $gitBashBin))" in setup_text
    ), (
        "setup-prerequisites.ps1 must verify bash.exe exists "
        "after the Git for Windows installer returns (positive "
        "or negative `Test-Path $gitBashBin` form). Got:\n"
        + setup_text[-3000:]
    )
    # On failure, must `Fail` (not `Warn` like the old code did) —
    # Git Bash is required for `shell: bash` steps; without it the
    # build will hard-fail. A `Warn` would let the operator skip it.
    # setup-prerequisites.ps1 uses the consolidated `Fail "Download/install failed"`
    # text in the catch block, plus a separate post-install verify Fail.
    assert "Fail \"Download/install failed" in setup_text, (
        "setup-prerequisites.ps1 must call `Fail` (not `Warn`) "
        "on Git for Windows install failure. Without it, the "
        "operator is told it's 'optional' and the next build "
        "fails with `bash: command not found` 30 seconds in. "
        "Got:\n" + setup_text[-3000:]
    )
    assert "Fail \"Installer ran but bash.exe" in setup_text, (
        "setup-prerequisites.ps1 must post-install verify bash.exe "
        "with a Fail when the installer reports success but "
        "bash.exe is missing. Got:\n" + setup_text[-3000:]
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


# ---------------------------------------------------------------------------
# Operator baseline: Git Bash /DIR semantics, post-install verify, Chocolatey Fail
# ---------------------------------------------------------------------------

def test_register_runner_ps1_uses_inno_setup_dir_semantics():
    """setup-prerequisites.ps1's Git for Windows auto-install must
    pass `/DIR=$gitBashInstallDir` (= the install TARGET dir,
    `C:\\Program Files\\Git`), NOT `/DIR=$gitBashDir` (= the bin
    subdir).

    Why this matters: Inno Setup's `/DIR` is documented as
    "Overrides the default directory name displayed on the
    Select Destination Location wizard page" — i.e. the install
    target dir, not a subdir of it. Git for Windows' installer
    uses `DefaultDirName={pf}\\{#APP_NAME}` so the default is
    `C:\\Program Files\\Git`. Passing `/DIR=C:\\Program Files\\Git\\bin`
    was silently IGNORED by Inno Setup (the install target dir
    must not equal a path that already exists as a subdir), and
    the install fell back to the default. This happened to
    work because the default matches what we want, but it's
    an undocumented accident — a future Inno Setup / Git for
    Windows change could break it.

    Test pins the correct `/DIR$gitBashInstallDir` form, so a
    future regression back to `/DIR$gitBashDir` fails this test
    instead of silently relying on the default path.

    As of the setup-delegation refactor, this contract lives in
    setup-prerequisites.ps1 (single source of truth) rather than
    register_runner.ps1.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    # Must use the install target dir.
    assert '"/DIR$gitBashInstallDir"' in text, (
        "setup-prerequisites.ps1's Git for Windows install must use "
        "`/DIR$gitBashInstallDir` (the install TARGET dir, e.g. "
        "`C:\\Program Files\\Git`) — NOT `/DIR$gitBashDir` (which "
        "is the bin subdir). Inno Setup's `/DIR` expects the "
        "install target dir; passing the bin subdir was silently "
        "ignored, falling back to the default `C:\\Program "
        "Files\\Git` (which happened to match — but is not "
        "explicitly pinned). Without this, a future Git for "
        "Windows / Inno Setup change that shifts the default "
        "would break the install silently. Got:\n" + text[-3000:]
    )
    # The buggy form must NOT be present (defensive — catches
    # accidental reverts to the old `/DIR$gitBashDir` form).
    assert '"/DIR$gitBashDir"' not in text, (
        "setup-prerequisites.ps1's Git for Windows install still "
        "uses the BUGGY `/DIR$gitBashDir` (= bin subdir) form. "
        "This was silently ignored by Inno Setup. Got:\n"
        + text[-3000:]
    )


def test_register_runner_ps1_post_install_verifies_all_components():
    """After each install (Git for Windows, PowerShell 7,
    Chocolatey), setup-prerequisites.ps1 must re-probe the exact
    binary it just installed and Fail if it's missing. Without
    this, a silently-failing installer (exit 0 but no files
    on disk — antivirus quarantine, blocked permissions,
    partial MSI install, etc.) lets the script continue
    thinking the component is present. The next CI job then
    fails with `pwsh: command not found` or
    `bash: command not found` 30 seconds in, masking the real
    cause.

    Test pins: each install branch must contain a Test-Path
    verify that Fails on miss. The verify can be either
    `if (Test-Path $bin) { ... } else { Fail ... }` (positive
    form) or `if (-not (Test-Path $bin)) { Fail ... }` (negative
    form) — both are functionally equivalent. We check for
    *either* form by scanning the install branch's relevant
    range for `Test-Path $binaryBin` + a nearby Fail.

    As of the setup-delegation refactor, this contract lives in
    setup-prerequisites.ps1 (single source of truth) rather than
    register_runner.ps1.
    """
    import re
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    for binary_name, path_var in [
        ("Git Bash",  "$gitBashBin"),
        ("PowerShell 7", "$pwshBin"),
        ("Chocolatey", "$chocoBin"),
    ]:
        # The contract is: after install, re-probe and Fail on
        # miss. Match either form by checking for both the
        # Test-Path probe AND a Fail line in proximity (within
        # 50 lines either side of the probe). The Git Bash
        # branch uses positive form `if (Test-Path $gitBashBin)
        # { Log ... } else { Fail ... }`; pwsh and choco use
        # `if (-not (Test-Path $bin)) { Fail ... }` and then a
        # second positive verify. Acceptable variations all
        # include both tokens.
        lines = text.splitlines()
        probe_indices = [
            i for i, line in enumerate(lines)
            if f"Test-Path {path_var}" in line
        ]
        assert probe_indices, (
            f"setup-prerequisites.ps1 must probe Test-Path "
            f"{path_var} for {binary_name}. Got:\n"
            + text[-4000:]
        )
        # Each probe must be paired with a Fail within ±50 lines
        # (the install branch scope).
        for probe_idx in probe_indices:
            window = lines[max(0, probe_idx-50):min(len(lines), probe_idx+50)]
            if any("Fail " in l for l in window):
                break
        else:
            assert False, (
                f"setup-prerequisites.ps1's Test-Path probe for "
                f"{path_var} ({binary_name}) is not paired with "
                f"a Fail within ±50 lines. Without a Fail, a "
                f"silently-failing install lets the script "
                f"continue and the next CI job fails with "
                f"`command not found`. Got:\n" + text[-4000:]
            )


def test_register_runner_ps1_chocolatey_install_fails_not_warns():
    """setup-prerequisites.ps1 must `Fail` (not `Warn`) on Chocolatey
    install failure. Why: choco is required by
    setup-signtool-env as the fallback path to install
    Windows SDK / signtool. Without choco, the first
    Windows build job fails inside setup-signtool-env with
    `choco: command not found` 10 minutes into the build —
    far from the obvious root cause. Failing here at
    register time surfaces the problem at the right step,
    with a clear remediation pointer.

    Test pins: the catch block for the Chocolatey install
    calls `Fail` (the helper that writes a `[fail]` line
    and `exit 1`s), not `Warn` (which only writes a
    `[warn]` line and continues).

    As of the setup-delegation refactor, this contract lives in
    setup-prerequisites.ps1 (single source of truth) rather than
    register_runner.ps1.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    assert 'Fail "Chocolatey install failed' in text, (
        "setup-prerequisites.ps1 must call `Fail` (not `Warn`) "
        "on Chocolatey install failure. Without choco, the "
        "Windows SDK signtool fallback in setup-signtool-env "
        "will fail during the first Windows build job — and "
        "that failure happens 10 minutes into the job, not "
        "at register time. Fail here so the operator sees the "
        "problem at the right step. Got:\n" + text[-3000:]
    )
    # Defensive: the old `Warn` form must not be present.
    assert 'Warn "Chocolatey install failed' not in text, (
        "setup-prerequisites.ps1 still has the OLD `Warn` form "
        "for Chocolatey install failure (the operator-is-told-"
        "it's-optional bug). Replace with `Fail`. Got:\n"
        + text[-3000:]
    )
    # Also pin the post-install verify Fail.
    assert 'Fail "Chocolatey install script ran' in text, (
        "setup-prerequisites.ps1 must call `Fail` (not `Warn`) "
        "when the Chocolatey installer reports success but "
        "$chocoBin is still missing. The community script "
        "can exit 0 even on partial failure. Got:\n"
        + text[-3000:]
    )


def test_register_runner_ps1_pwsh_msi_uses_start_process_passthru():
    """setup-prerequisites.ps1's pwsh MSI install must use
    `Start-Process -Wait -PassThru` to capture the real MSI
    exit code. Calling `msiexec.exe /i ... | Out-Null` is
    unreliable: msiexec is a GUI-subsystem application,
    so PowerShell doesn't block on it AND $LASTEXITCODE
    reflects the last NATIVE command in the pipeline,
    which may not be msiexec.

    Reference: https://stackoverflow.com/q/4124409 and
    https://stackoverflow.com/q/50867146.

    Test pins: the script uses `Start-Process -FilePath
    "msiexec.exe" -Wait -PassThru` (or equivalent) AND
    references `$proc.ExitCode` (or `.ExitCode`) for
    the post-install Fail message. The old `| Out-Null`
    form must not be present.

    As of the setup-delegation refactor, this contract lives
    in setup-prerequisites.ps1 (single source of truth).
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    assert "Start-Process -FilePath \"msiexec.exe\"" in text, (
        "setup-prerequisites.ps1's pwsh MSI install must use "
        "`Start-Process -FilePath \"msiexec.exe\" -Wait -PassThru` "
        "to capture the real MSI exit code. Calling `msiexec.exe "
        "/i ... | Out-Null` is unreliable because msiexec is "
        "GUI-subsystem; PowerShell doesn't block on it and "
        "$LASTEXITCODE reflects the last NATIVE command in the "
        "pipeline. Got:\n" + text[-4000:]
    )
    # The old buggy form must not be present.
    assert "msiexec.exe /i $msi /qn /norestart | Out-Null" not in text, (
        "setup-prerequisites.ps1's pwsh MSI install still uses the "
        "BUGGY `msiexec.exe /i $msi /qn /norestart | Out-Null` "
        "form. This doesn't block and doesn't capture the real "
        "exit code. Replace with Start-Process -PassThru. Got:\n"
        + text[-4000:]
    )


# ---------------------------------------------------------------------------
# Skip-token + delegation contract (refactor: register_runner.ps1 no
# longer inlines setup; it probes for an existing `.runner` to skip
# config.cmd --replace when the runner is already registered, and
# delegates to setup-prerequisites.ps1 for environment drift fixes).
# ---------------------------------------------------------------------------

def test_register_runner_ps1_delegates_setup_to_setup_prerequisites():
    """register_runner.ps1 must NOT re-implement the install logic
    inline; it must delegate to setup-prerequisites.ps1. Two
    copies of the same install logic were found in audit and
    drifted (4 identical bugs in each copy). Single source of
    truth is the canonical fix.

    Test pins both halves of the delegation contract:
      1. register_runner.ps1 invokes the setup script via
         `& powershell -NoProfile -ExecutionPolicy Bypass -File
         $siblingSetup -ForceRestart`.
      2. register_runner.ps1 must NOT contain the install logic
         it used to inline (no Set-ExecutionPolicy, no
         git-for-windows URL, no /DIR$, no Chocolatey install
         URL, no msiexec invocation).
    """
    rr_text = _read(REGISTER_RUNNER_SCRIPT)
    # (1) Delegation is present
    assert "& powershell -NoProfile -ExecutionPolicy Bypass -File $siblingSetup -ForceRestart" in rr_text, (
        "register_runner.ps1 must invoke setup-prerequisites.ps1 "
        "via `& powershell -NoProfile -ExecutionPolicy Bypass "
        "-File $siblingSetup -ForceRestart`. Single source of "
        "truth. Got:\n" + rr_text[-3000:]
    )
    assert "Setup is delegated" in rr_text or "DELEGATED to setup-prerequisites.ps1" in rr_text or "Operator-side baseline setup — DELEGATED" in rr_text, (
        "register_runner.ps1 must declare its delegation to "
        "setup-prerequisites.ps1 in a comment block. Got:\n"
        + rr_text[-3000:]
    )

    # (2) Inline install logic must be gone (DRY violation
    # defense — if a future change re-inlines these, two
    # implementations will drift again).
    forbidden_in_register = [
        "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine",
        "git-for-windows/git/releases/download",
        "/DIR$gitBashDir",  # the buggy form (=/DIR bin/)
        "/DIR$gitBashInstallDir",  # any /DIR is wrong here
        'community.chocolatey.org/install.ps1',
        "msiexec.exe /i $msi",  # any msiexec invocation
    ]
    for bad in forbidden_in_register:
        assert bad not in rr_text, (
            f"register_runner.ps1 must NOT contain inline install "
            f"logic — that would re-introduce the DRY violation. "
            f"Found forbidden substring: {bad!r}. Got:\n"
            + rr_text[-3000:]
        )


def test_register_runner_ps1_skips_token_when_already_registered():
    r"""register_runner.ps1 must probe `$runnerDir\.runner` for an
    existing registration and skip the `config.cmd --replace`
    step (which consumes the token) when the runner is already
    registered with the matching agentName + gitHubUrl.

    Why: registration tokens are short-lived (~1 hour) and
    require a `gh api ... /actions/runners/registration-token`
    call to mint. Operators routinely re-run register_runner.ps1
    after Windows Update, label changes, or service restart
    without going back to the GitHub UI. Forcing a fresh token
    every time is friction without value.

    Test pins the five contract points:
      1. Path probe: `$runnerDir\.runner`
      2. JSON parse: `Get-Content ... | ConvertFrom-Json`
      3. agentName match against `$runnerName`
      4. gitHubUrl match against `$repoUrl`
      5. Skip path: `Log "Skipping config.cmd --replace"`
      6. Refresh log: `Detected already-registered runner`
      7. Token Fail moved to `function Require-Token` (no
         immediate Fail on missing token at the top of the
         script; Fail is deferred to when config.cmd is actually
         needed).

    Drift defense: pin that the old "always Fail if no token"
    block at the top of the script is gone (line 41-44 area).
    """
    text = _read(REGISTER_RUNNER_SCRIPT)
    # (1) Probe
    assert "$runnerStateFile = Join-Path $runnerDir '.runner'" in text, (
        "register_runner.ps1 must probe `$runnerDir\\.runner` to "
        "detect an existing registration. Got:\n" + text[-3500:]
    )
    # (2) JSON parse
    assert "Get-Content $runnerStateFile -Raw | ConvertFrom-Json" in text, (
        "register_runner.ps1 must parse the .runner JSON to "
        "compare agentName/gitHubUrl. Got:\n" + text[-3500:]
    )
    # (3) agentName match
    assert "($runnerState.agentName -eq $runnerName)" in text, (
        "register_runner.ps1 must validate agentName matches "
        "$runnerName before skipping config.cmd. Otherwise a "
        "name switch could be silently applied. Got:\n" + text[-3500:]
    )
    # (4) gitHubUrl match
    assert "($runnerState.gitHubUrl -eq $repoUrl)" in text, (
        "register_runner.ps1 must validate gitHubUrl matches "
        "$repoUrl before skipping config.cmd. Otherwise a "
        "repo switch could be silently applied. Got:\n" + text[-3500:]
    )
    # (5) Skip path
    assert 'Log "Skipping config.cmd --replace (refresh mode)"' in text, (
        "register_runner.ps1 must log explicitly when it skips "
        "config.cmd --replace, so the operator can see the "
        "refresh path was taken (not a config.cmd failure). "
        "Got:\n" + text[-3500:]
    )
    # (6) Refresh log
    assert "Detected already-registered runner at $runnerStateFile" in text, (
        "register_runner.ps1 must log when it detects an "
        "already-registered runner. Got:\n" + text[-3500:]
    )
    # (7) Token Fail deferred
    assert "function Require-Token" in text, (
        "register_runner.ps1 must define a `Require-Token` "
        "helper instead of failing immediately on missing token. "
        "The fresh-registration path invokes it; the refresh "
        "path skips it. Got:\n" + text[-3500:]
    )

    # Drift defense: no immediate Fail on missing token at top
    # of script (the old line 41-44 block). The fresh-path Fail
    # must live inside `Require-Token`.
    # Allow the function body to have "Fail" once (inside
    # Require-Token), but NOT a top-level "Fail \"no token"
    # outside of the function.
    import re
    # Find any line that is at column 0 (top-level) and Fail with
    # "no token" text. Top-level = lines starting with no indent.
    top_level_token_fail = [
        line for line in text.splitlines()
        if line.startswith("Fail") and "no token provided" in line
    ]
    assert not top_level_token_fail, (
        "register_runner.ps1 must NOT have a top-level Fail on "
        "missing token (the old line 41-44 block). A immediate "
        "Fail breaks the refresh-mode skip-token path. Move it "
        "into the `Require-Token` helper. Found:\n"
        + "\n".join(top_level_token_fail)
    )


def test_setup_prerequisites_is_standalone_runnable():
    """setup-prerequisites.ps1 must be runnable as a standalone
    script (operator runs it directly to fix drift between CI
    runs, without going through register_runner.ps1). This is
    the contract that makes the delegation refactor worth it.

    Test pins:
      1. File has a proper `[CmdletBinding()]` header with params.
      2. Has -Check mode for dry-run.
      3. Has -ForceRestart mode (used by register_runner.ps1).
      4. Has `param()` declaring both switches.
      5. Sets `SETUP_RESULT=OK|CHANGES_SKIPPED` so callers
         (operators/CI) can detect drift programmatically.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    assert "[CmdletBinding()]" in text, (
        "setup-prerequisites.ps1 must declare [CmdletBinding()] "
        "for proper param() handling. Got:\n" + text[:1500]
    )
    assert "[switch]$Check" in text, (
        "setup-prerequisites.ps1 must declare [switch]$Check "
        "for dry-run mode. Got:\n" + text[:1500]
    )
    assert "[switch]$ForceRestart" in text, (
        "setup-prerequisites.ps1 must declare [switch]$ForceRestart "
        "so register_runner.ps1 can pass -ForceRestart on "
        "delegation. Got:\n" + text[:1500]
    )
    # SETUP_RESULT line should be present so callers can detect
    # outcome programmatically.
    assert "SETUP_RESULT=" in text, (
        "setup-prerequisites.ps1 must emit a `SETUP_RESULT=OK` "
        "or `SETUP_RESULT=CHANGES_SKIPPED` summary line so "
        "callers can detect drift. Got:\n" + text[-2000:]
    )
    assert "exit 1" in text, (
        "setup-prerequisites.ps1's `Fail` helper must call "
        "exit 1 (otherwise partial-setup state would not "
        "propagate to callers). Got:\n" + text[:2000]
    )


def test_preflight_uses_install_target_dir_for_git_dir_arg():
    """release-cn.yml's preflight step (5 occurrences) must
    pass `/DIR$gitBashInstallDir` (the install target dir)
    to the Git for Windows installer, NOT `/DIR$gitBashDir`
    (= bin subdir, silently ignored by Inno Setup). This
    is the workflow-side counterpart to
    test_register_runner_ps1_uses_inno_setup_dir_semantics:
    both install paths must use the same correct /DIR form.

    Pin exact count of 5 occurrences (one per Windows build
    job: build-windows-amd64 + preflight for each of 4
    jobs). Drift in this number means a future refactor
    either added or removed a build job — both warrant
    review.
    """
    wf_text = _read(WORKFLOW_FILE)
    install_dir_count = wf_text.count('"/DIR$gitBashInstallDir"')
    install_dir_decl_count = wf_text.count(
        '$gitBashInstallDir = \'C:\\Program Files\\Git\''
    )
    buggy_count = wf_text.count('"/DIR$gitBashDir"')

    assert install_dir_count == 5, (
        f"release-cn.yml: preflight must use `/DIR$gitBashInstallDir` "
        f"in exactly 5 places (one per Windows build/preflight job). "
        f"Found {install_dir_count}. If a build job was added or "
        f"removed, the count changes — that's expected, update the "
        f"test. Otherwise, /DIR semantics regressed."
    )
    assert install_dir_decl_count == 5, (
        f"release-cn.yml: `$gitBashInstallDir = 'C:\\Program Files\\Git'` "
        f"must be declared in exactly 5 places (one per preflight block). "
        f"Found {install_dir_decl_count}."
    )
    assert buggy_count == 0, (
        f"release-cn.yml: preflight must NOT use the buggy "
        f"`/DIR$gitBashDir` form (the bin subdir, silently ignored "
        f"by Inno Setup). Found {buggy_count} occurrence(s)."
    )


def test_preflight_pwsh_msi_uses_start_process_passthru():
    """release-cn.yml's preflight step (5 occurrences) must
    use `Start-Process -FilePath \"msiexec.exe\" -Wait
    -PassThru` for the PowerShell 7 MSI install — same
    correctness requirement as register_runner.ps1's pwsh
    install branch.

    Pin exact count of 5 occurrences to catch drift.
    """
    wf_text = _read(WORKFLOW_FILE)
    count = wf_text.count(
        'Start-Process -FilePath "msiexec.exe"'
    )
    assert count == 5, (
        f"release-cn.yml: preflight must use Start-Process "
        f"-Wait -PassThru for msiexec in exactly 5 places "
        f"(one per Windows build/preflight job). Found {count}."
    )
    buggy = wf_text.count(
        "msiexec.exe /i $msi /qn /norestart | Out-Null"
    )
    assert buggy == 0, (
        f"release-cn.yml: preflight must NOT use the buggy "
        f"`msiexec.exe /i ... | Out-Null` form (doesn't block, "
        f"doesn't capture exit code). Found {buggy} occurrence(s)."
    )