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
     PATH`. **PROBE-THEN-INSTALL**: detects the two binaries
     via `Find-BashLocation` / `Find-PwshLocation` (PATH +
     common candidate dirs so non-standard installs are
     found first); if found, logs `[OK]` and continues; if
     missing, auto-installs (canonical URLs, `Start-Process
     -Wait -PassThru` for exit codes), with `::error::` +
     `exit 1` only on install failure. Happy path is a
     2-line no-op.

The preflight exists so:
  - A runner that was registered without §九.3.1 still
    picks up the missing pieces the first time a job runs
    (so the workflow can complete end-to-end).
  - A runner image that's re-provisioned doesn't require
    a separate "install baseline" Ansible/Packer step.

The preflight is intentionally not the recommended way to
set up the runner — it costs an MSI/EXE download per first
job and clutters `$env:TEMP`. The docs §九.3.1 explicitly
says: "强烈建议 在 `register_runner.ps1` 跑完后提前装好...
这样 workflow 的 preflight step 跑得快 (只 `where.exe` 一次
就 `[OK]`...)" — operator path is preferred, preflight is
the safety net. The user's latest feedback: "应该还是要支持
安装的，如果检查到没有安装的时候，确保流程能完整执行" —
so the preflight MUST install on probe miss, not just Fail.

These tests pin the contract so a future refactor can't
silently remove the preflight's probe-then-install
idempotency, the §九.3.1 docs guidance, or the workflow's
shell assumptions without realizing the self-hosted runner
depends on them.
"""
from __future__ import annotations

import re
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
    """The preflight step must be PROBE-THEN-INSTALL: it probes
    first via Find-BashLocation / Find-PwshLocation (so any
    existing install — including operator-style non-standard
    paths like `C:\\Users\\<user>\\opt\\pwsh7\\`, scoop, choco)
    is detected and used without re-installing. If the probe
    misses, it auto-installs (the canonical URLs,
    `/DIR$gitBashInstallDir`, `msiexec -PassThru` MSI) so the
    workflow can ALWAYS run end-to-end without an operator
    pre-install step.

    Why install-on-miss: the previous probe-only contract
    turned into a green run UI + 80 MB per-job download cost
    on operators who hadn't pre-installed (`run #86820634953`).
    The current contract — probe first, install only on miss —
    gets the speed of probe-first on happy-path runs AND the
    self-healing of auto-install on cold runners, so the
    workflow can always complete end-to-end.

    Test pins:
      1. The preflight uses Find-BashLocation / Find-PwshLocation
         (probe-first, not hardcoded `C:\\Program Files\\` paths).
      2. The preflight DOES install Git for Windows on miss
         (the canonical URL, `/DIR$gitBashInstallDir`, `/VERYSILENT`).
      3. The preflight DOES install PowerShell 7 on miss
         (the canonical MSI URL, `msiexec -PassThru`).
      4. Install failure emits `::error::` + `exit 1` so the
         operator sees the problem at the right step.
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
    # (1) Probe-first via Find-*Location helpers.
    assert "Find-BashLocation" in run and "Find-PwshLocation" in run, (
        "release-cn.yml: preflight step must probe via "
        "Find-BashLocation / Find-PwshLocation (probe-first). "
        "Hardcoded `C:\\Program Files\\` paths would shadow "
        "non-standard installs (operator-style paths, scoop, "
        "choco) and trigger multi-minute downloads. Got:\n" + run
    )
    # (2) Install Git for Windows on miss (canonical URL + correct
    # /DIR argument parent directory).
    assert "git-for-windows/git/releases/download" in run, (
        "release-cn.yml: preflight must install Git for Windows "
        "on probe miss (canonical release URL). Got:\n" + run[-2000:]
    )
    assert "/DIR$gitBashInstallDir" in run, (
        "release-cn.yml: preflight must pass `/DIR$gitBashInstallDir` "
        "(the dir=parent of bin/, NOT bin/ which is silently ignored). "
        "Got:\n" + run[-2000:]
    )
    # (3) Install PowerShell 7 on miss (canonical MSI URL +
    # msiexec -PassThru for reliable exit code).
    assert "PowerShell-7.4.6-win-x64.msi" in run, (
        "release-cn.yml: preflight must install PowerShell 7 on "
        "probe miss (canonical MSI URL). Got:\n" + run[-2000:]
    )
    assert 'Start-Process -FilePath "msiexec.exe"' in run, (
        "release-cn.yml: preflight must call "
        "`Start-Process -FilePath \"msiexec.exe\"` so the real "
        "MSI exit code is captured (-PassThru captures the exit "
        "code; `msiexec ... | Out-Null` is unreliable). Got:\n"
        + run[-2000:]
    )
    # (4) Install failure must Fail (::error:: + exit 1), not
    # silently continue. The ::error:: message is the operator's
    # first stop; the install-failure path must emit one.
    assert "::error::" in run, (
        "release-cn.yml: preflight must emit `::error::` on "
        "install failure so the operator sees the problem at "
        "the right step. Got:\n" + run[-2000:]
    )
    # Must use `shell: pwsh` (PowerShell 7) so modern syntax
    # (Get-Command, Find-*) works natively.
    assert step.get("shell") == "pwsh", (
        "release-cn.yml: preflight step must use `shell: pwsh` "
        "not `shell: powershell` (5.1). The run-block now uses "
        "Get-Command / Find-*Location helpers that work in pwsh 7 "
        "natively."
    )


def test_preflight_step_handles_install_failure_gracefully():
    """If Git Bash or PowerShell 7 is not found anywhere on the
    runner (probe + PATH lookup both miss, then the auto-install
    fails — e.g. download blocked, no admin, MSI exit code != 0),
    the preflight must emit `::error::` + `exit 1` so the
    operator sees the problem at the right step.

    Without this, the preflight would silently continue on a
    failed install, and downstream `shell: pwsh` / `shell: bash`
    steps would fail with cryptic `##[error]command not found`
    ten minutes into the job, and the root preflight step
    wouldn't show up as the failed step in the run UI.

    Contract: probe-then-install. Probe first, then install on
    miss. Install failure -> `::error::` + `exit 1`.

    Both Git Bash install-failure and PowerShell 7 install-failure
    paths must emit a `::error::` (>= 2 occurrences in the run
    block).
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
    # At least one `::error::` per probe path (git + pwsh).
    assert run.count("::error::") >= 2, (
        "release-cn.yml: preflight step must emit "
        "`::error::...` for EACH of Git Bash + PowerShell 7 "
        "when the install fails. Two separate error messages "
        "(one per binary) is the contract. Got:\n" + run[-2000:]
    )
    assert "exit 1" in run, (
        "release-cn.yml: preflight step must `exit 1` on "
        "install failure, not silently continue. If it "
        "continues, downstream `shell: pwsh` / `shell: bash` "
        "steps fail with `##[error]command not found` 10 "
        "minutes into the build, and the root preflight step "
        "won't show up as the failed step. Got:\n" + run[-2000:]
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
    pointing at setup-prerequisites.ps1 + §九.3.1.

    Background: GHA runner invokes `shell: powershell` steps via
    `powershell -command ". '<guid>.ps1'"` (dot-sources a temp
    file in `_work\\temp`). On a vanilla self-hosted Windows
    runner, the SYSTEM ExecutionPolicy is the in-box default
    `Restricted`, which rejects the dot-source with
    `UnauthorizedAccess` BEFORE any step body runs (real
    failure from log #86728979772, run 86728979772). The
    runner-side fix is in `setup-prerequisites.ps1` (sets
    `LocalMachine=RemoteSigned` + `svc.cmd restart`). The
    preflight's job is to detect this misconfiguration in
    advance and emit a clear error so the operator knows
    `setup-prerequisites.ps1` needs to be (re-)run, instead of
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
    assert "setup-prerequisites.ps1" in run, (
        "release-cn.yml: preflight step's error message must "
        "point the operator at setup-prerequisites.ps1 (the "
        "canonical place to apply ExecutionPolicy "
        "`LocalMachine` = `RemoteSigned` + restart the "
        "service). Got:\n" + run
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


def test_register_runner_ps1_installs_git_for_windows_on_miss():
    """Probe-then-install contract: setup-prerequisites.ps1 auto-installs
    Git for Windows when bash.exe is missing. The install uses the
    canonical release URL and the correct `/DIR$gitBashInstallDir`
    argument (parent of bin/, NOT bin/ which Inno Setup silently
    ignores).

    Rationale: the user explicitly reversed the previous
    "probe-only, FAIL on miss" strategy ("不应该执行安装的，没有就报错")
    with "应该还是要支持安装的，如果检查到没有安装的时候，确保流程能完整执行"
    [transcript, latest user feedback]. The current contract is
    PROBE-THEN-INSTALL.

    Test pins:
      1. The script uses Find-BashLocation (probe-first).
      2. The script DOES contain the Git-for-Windows release URL.
      3. The script DOES invoke Inno Setup (`/VERYSILENT`).
      4. The script DOES pass the `/DIR=$gitBashInstallDir`
         argument (parent of bin/, which is correct).
      5. On install failure, the script calls Fail with the
         canonical install URL.
    """
    setup_text = _read(SETUP_PREREQUISITES_SCRIPT)
    # (1) Probe-first via Find-BashLocation helper.
    assert "Find-BashLocation" in setup_text, (
        "setup-prerequisites.ps1 must probe Git Bash via "
        "Find-BashLocation (probe-first), then install on miss. "
        "Got:\n" + setup_text[-3000:]
    )
    # Verify it's wired up (probe result assigned to a variable,
    # then conditional install based on the variable).
    assert "= Find-BashLocation" in setup_text, (
        "setup-prerequisites.ps1 must assign the probe result "
        "to a variable (e.g. `$gitBashDiscovered = Find-BashLocation`) "
        "and use it to gate the install. Got:\n" + setup_text[-3000:]
    )
    # (2) Auto-install URL present.
    assert "git-for-windows/git/releases/download" in setup_text, (
        "setup-prerequisites.ps1 must auto-download Git for "
        "Windows on probe miss (probe-then-install contract). "
        "Got:\n" + setup_text[-3000:]
    )
    # (3) Inno Setup silent-install flag.
    assert "/VERYSILENT" in setup_text, (
        "setup-prerequisites.ps1 must invoke the Git for "
        "Windows Inno Setup installer in silent mode "
        "(`/VERYSILENT`). Got:\n" + setup_text[-3000:]
    )
    # (4) Correct `/DIR=$gitBashInstallDir` argument present.
    assert "/DIR$gitBashInstallDir" in setup_text, (
        "setup-prerequisites.ps1 must pass `/DIR$gitBashInstallDir` "
        "(the parent of bin/, NOT bin/ which Inno Setup silently "
        "ignores). Got:\n" + setup_text[-3000:]
    )
    # (5) On install failure, Fail with the canonical install URL.
    assert "git-scm.com/download/win" in setup_text, (
        "setup-prerequisites.ps1's Fail message (when the "
        "install fails) must point the operator at the canonical "
        "install URL. Got:\n" + setup_text[-3000:]
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

def test_setup_prerequisites_ps1_invokes_git_installer_on_miss():
    """Probe-then-install contract: setup-prerequisites.ps1 auto-installs
    Git for Windows when bash.exe is missing. The install uses the
    canonical release URL and the correct `/DIR$gitBashInstallDir`
    argument (parent of bin/, NOT bin/ which Inno Setup silently
    ignores). The user's latest feedback: "应该还是要支持安装的，如果
    检查到没有安装的时候，确保流程能完整执行".

    Test pins:
      1. The script DOES contain `/DIR$gitBashInstallDir` (parent
         of bin/, correct).
      2. The script DOES contain `Start-Process -Wait -FilePath
         $gitExe` (the installer process is invoked).
      3. The script DOES contain `/VERYSILENT` (Inno Setup flags).
      4. The script DOES contain the git-for-windows URL
         (auto-download).
      5. On install failure, the script calls `Fail` with the
         canonical install URL.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    # (1) `/DIR$gitBashInstallDir` argument present.
    assert "/DIR$gitBashInstallDir" in text, (
        "setup-prerequisites.ps1 must pass `/DIR$gitBashInstallDir` "
        "(the parent of bin/, NOT bin/ which Inno Setup silently "
        "ignores). Got:\n" + text[-3000:]
    )
    # (2) `Start-Process -Wait -FilePath $gitExe` invocation.
    assert "Start-Process -Wait -FilePath $gitExe" in text, (
        "setup-prerequisites.ps1 must invoke the Git for "
        "Windows installer via `Start-Process -Wait -FilePath $gitExe`. "
        "Got:\n" + text[-3000:]
    )
    # (3) Inno Setup silent-install flag.
    assert "/VERYSILENT" in text, (
        "setup-prerequisites.ps1 must pass `/VERYSILENT` "
        "(Inno Setup silent-install flag). Got:\n" + text[-3000:]
    )
    # (4) git-for-windows release URL.
    assert "git-for-windows/git/releases/download" in text, (
        "setup-prerequisites.ps1 must auto-download from the "
        "git-for-windows release URL. Got:\n" + text[-3000:]
    )
    # (5) Fail with the canonical install URL on install failure.
    assert "git-scm.com/download/win" in text, (
        "setup-prerequisites.ps1's Fail message (when install fails) "
        "must point the operator at the canonical install URL. "
        "Got:\n" + text[-3000:]
    )


def test_setup_prerequisites_ps1_installs_each_missing_binary():
    """Probe-then-install contract: setup-prerequisites.ps1
    installs any missing binary (bash.exe, pwsh.exe, choco.exe)
    and uses the canonical install URL on each branch. The
    user's latest feedback: "应该还是要支持安装的，如果检查到
    没有安装的时候，确保流程能完整执行".

    Test pins:
      1. The script references the canonical install URLs for
         each binary (git-scm.com/download/win,
         PowerShell-7.4.6-win-x64.msi, chocolatey.org/install)
         — these appear in the download URL or the Fail message.
      2. The script probes via Find-BashLocation / Find-PwshLocation
         and `Get-Command choco.exe` (probe-first).
      3. On install failure, the script `Fail`s with the
         canonical install URL.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    # (1) Canonical install URLs / paths present.
    assert "git-scm.com/download/win" in text, (
        "setup-prerequisites.ps1's bash.exe branch must reference "
        "the canonical install URL `https://git-scm.com/download/win`. "
        "Got:\n" + text[-3000:]
    )
    assert "PowerShell-7.4.6-win-x64.msi" in text, (
        "setup-prerequisites.ps1's pwsh.exe branch must reference "
        "the canonical MSI URL `PowerShell-7.4.6-win-x64.msi`. "
        "Got:\n" + text[-3000:]
    )
    assert "chocolatey.org/install" in text, (
        "setup-prerequisites.ps1's choco.exe branch must reference "
        "the canonical install URL `https://chocolatey.org/install`. "
        "Got:\n" + text[-3000:]
    )
    # (2) Probe-first via Find-*Location / Get-Command.
    # Git Bash + PowerShell 7 use the Find-*Location helpers;
    # Chocolatey uses an inline Get-Command.
    for branch_name, expected_probe in [
        ("Git Bash", "= Find-BashLocation"),
        ("PowerShell 7", "= Find-PwshLocation"),
        ("Chocolatey", "Get-Command choco.exe"),
    ]:
        assert expected_probe in text, (
            f"setup-prerequisites.ps1's {branch_name} branch must "
            f"probe first via `{expected_probe}` (probe-then-install). "
            f"Got:\n" + text[-3000:]
        )


def test_setup_prerequisites_ps1_installs_choco_on_miss():
    """setup-prerequisites.ps1 must auto-install Chocolatey
    (choco.exe) when it's not on the runner, NOT just `Fail`.
    The user's latest feedback: "应该还是要支持安装的".

    Why auto-install: choco is required by setup-signtool-env as
    the fallback path to install Windows SDK / signtool. Without
    choco, the first Windows build job fails inside
    setup-signtool-env with `choco: command not found` 10 minutes
    into the build — far from the obvious root cause. Auto-install
    here at setup time surfaces the problem at the right step.

    Pin the install path (community-chocolatey.org install script)
    so an operator can manually redo the install if needed.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    # The script must reference the canonical install script URL.
    assert "community-chocolatey.org/install.ps1" in text or "chocolatey.org/install" in text, (
        "setup-prerequisites.ps1's choco install branch must "
        "reference the canonical install script URL "
        "(`community-chocolatey.org/install.ps1`). Got:\n"
        + text[-3000:]
    )
    # Drift defense: the install branch must be present (not just
    # a Warn that tells the user to install).
    assert "Invoke-Expression" in text or "DownloadString" in text, (
        "setup-prerequisites.ps1 must actually invoke the choco "
        "install script (Invoke-Expression / DownloadString). "
        "Got:\n" + text[-3000:]
    )


def test_setup_prerequisites_ps1_invokes_pwsh_msi_on_miss():
    """Probe-then-install contract: setup-prerequisites.ps1
    auto-installs PowerShell 7 via the MSI when probe misses.
    The user's latest feedback: "应该还是要支持安装的，如果检查到
    没有安装的时候，确保流程能完整执行".

    Test pins:
      1. The script DOES invoke the MSI via msiexec with
         `-PassThru` (so the real MSI exit code is captured).
      2. The script DOES auto-download from the PowerShell
         release URL.
    """
    text = _read(SETUP_PREREQUISITES_SCRIPT)
    # msiexec invocation present.
    assert "msiexec" in text, (
        "setup-prerequisites.ps1 must invoke msiexec on miss "
        "(probe-then-install contract). Got:\n" + text[-4000:]
    )
    # `-PassThru` captures the real exit code.
    assert "-PassThru" in text, (
        "setup-prerequisites.ps1 must use `Start-Process -PassThru` "
        "to capture the real MSI exit code (msiexec is GUI-subsystem, "
        "`Out-Null` would lose it). Got:\n" + text[-4000:]
    )
    # Auto-download from PowerShell release URL.
    assert "PowerShell/PowerShell/releases/download" in text, (
        "setup-prerequisites.ps1 must auto-download from the "
        "PowerShell release URL. Got:\n" + text[-4000:]
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


def test_preflight_release_cn_installs_git_and_pwsh_on_miss():
    """Probe-then-install contract: release-cn.yml's preflight
    step installs Git for Windows AND PowerShell 7 on probe miss.
    The user's latest feedback: "应该还是要支持安装的，如果检查到
    没有安装的时候，确保流程能完整执行".

    The OLD version of this test (pre-#86820634953 follow-up)
    pinned that the preflight was PROBE-ONLY (no `/DIR$gitBashInstallDir`,
    no `msiexec`). Now the contract is PROBE-THEN-INSTALL — the
    probe happens first (so non-standard installs are found and
    used), and on miss the install happens with the correct
    arguments.

    Test pins:
      1. `/DIR$gitBashInstallDir` appears in 5 places (one per
         Windows preflight block).
      2. The preflight uses Find-BashLocation / Find-PwshLocation
         (probe-first, not hardcoded `C:\\Program Files\\...`).
      3. PowerShell 7 MSI is invoked via `msiexec -PassThru`.
    """
    wf_text = _read(WORKFLOW_FILE)
    # (1) `/DIR$gitBashInstallDir` exactly 5 occurrences
    # (one per Windows preflight block).
    install_dir_count = wf_text.count('"/DIR$gitBashInstallDir"')
    assert install_dir_count == 5, (
        f"release-cn.yml: preflight must install on probe miss, "
        f"using `/DIR$gitBashInstallDir`. Expected 5 occurrences "
        f"(one per Windows preflight block). Found "
        f"{install_dir_count}."
    )
    # (2) Probe helpers present in every preflight block.
    # Count only the *call sites* (not the inline-fallback
    # function definitions, which double the count). The 5
    # actual call sites use the form `$var = Find-BashLocation`.
    find_bash_count = wf_text.count("$gitBashBin = Find-BashLocation")
    find_pwsh_count = wf_text.count("$pwshBin = Find-PwshLocation")
    assert find_bash_count == 5 and find_pwsh_count == 5, (
        f"release-cn.yml: preflight must use Find-BashLocation "
        f"AND Find-PwshLocation in exactly 5 call sites (one per "
        f"Windows build/preflight job). Found "
        f"Find-BashLocation={find_bash_count}, "
        f"Find-PwshLocation={find_pwsh_count}. If a build job "
        f"was added, the count changes — that's expected, "
        f"update the test."
    )
    # (3) PowerShell 7 MSI invoked via msiexec -PassThru.
    assert 'Start-Process -FilePath "msiexec.exe"' in wf_text, (
        "release-cn.yml: preflight must invoke "
        "`Start-Process -FilePath \"msiexec.exe\"` so the real "
        "MSI exit code is captured (-PassThru captures the exit "
        "code; `msiexec ... | Out-Null` is unreliable). Got:\n"
        + wf_text[-4000:]
    )


def test_preflight_release_cn_invokes_pwsh_msi_on_miss():
    """Probe-then-install contract: release-cn.yml's preflight
    step invokes the PowerShell 7 MSI installer via `msiexec`
    on probe miss. The user's latest feedback: "应该还是要支持
    安装的，如果检查到没有安装的时候，确保流程能完整执行".

    The OLD version of this test pinned ZERO occurrences of
    `Start-Process -FilePath "msiexec.exe"`. Now the contract
    is PROBE-THEN-INSTALL, so 5 occurrences is correct (one
    per Windows preflight block).

    Test pins:
      1. 5 occurrences of `Start-Process -FilePath "msiexec.exe"`
         (one per Windows preflight block).
      2. 5 occurrences of Find-PwshLocation (the probe-first
         counterpart).
    """
    wf_text = _read(WORKFLOW_FILE)
    count = wf_text.count('Start-Process -FilePath "msiexec.exe"')
    assert count == 5, (
        f"release-cn.yml: preflight must invoke "
        f"`Start-Process -FilePath \"msiexec.exe\"` on probe miss. "
        f"Expected 5 occurrences (one per Windows preflight block). "
        f"Found {count}. If a build job was added, update the "
        f"count."
    )
    # Drift defense: 5 occurrences of Find-PwshLocation (count
    # only call sites, not inline-fallback function definitions
    # which double the count).
    find_pwsh_count = wf_text.count("$pwshBin = Find-PwshLocation")
    assert find_pwsh_count == 5, (
        f"release-cn.yml: preflight must use Find-PwshLocation "
        f"in exactly 5 call sites (one per Windows preflight "
        f"job). Found {find_pwsh_count}. If a build job was "
        f"added, update the test."
    )


# ---------------------------------------------------------------------------
# Workflow: dist\<NAME>-...-Setup.exe ↔ ecan_build.py:installer_filename
# ---------------------------------------------------------------------------
# Per CLAUDE.md §7: workflows are a contract with build_system/. Every
# hard-coded `dist\<NAME>-…-Setup.exe` reference must resolve to the same
# on-disk filename that build_system/ecan_build.py emits. This contract was
# broken when build.py switched to `app_info.get('name', 'eCan')` while
# the workflow kept `dist\eCan-{ver}-...-Setup.exe` (release-cn.yml#1528,
# build run #86820634953), causing Prepare-artifacts to throw on a
# real on-disk `eCan.cn-{ver}-...-Setup.exe`. The fix parameterises the
# workflow path with `${{ env.DIST_APP }}` and lets each pipeline's env
# declare its own per-app short name (eCan for intl, eCan.cn for cn).
# This test pins both sides of that contract so a future drift surfaces
# here, not as a red Build Windows job.


ECAN_BUILD_FILE = REPO / "build_system/ecan_build.py"
WORKFLOW_INTL_FILE = REPO / ".github/workflows/release-intl.yml"


def test_dist_app_path_matches_installer_filename_template():
    r"""For each pipeline (intl, cn) the workflow Prepare-artifacts path

        `dist\${{ env.DIST_APP }}-{ver}-windows-{arch}-Setup.exe`

    must resolve to the same on-disk filename that build_system/ecan_build.py
    emits via `installer_filename = f"{app_info.get('name', 'eCan')}-..."`,
    because env.DIST_APP is set from the per-app env (eCan for intl,
    eCan.cn for cn) and app.name == ECAN_APP_NAME == DIST_APP. A future
    divergence here means Prepare-artifacts will throw "Expected Windows
    installer not found" on a real build (see run #86820634953).
    """
    cn_text = _read(WORKFLOW_FILE)
    intl_text = _read(WORKFLOW_INTL_FILE)
    build_text = _read(ECAN_BUILD_FILE)

    # The Windows installer path template in each workflow's
    # Prepare-artifacts step must use the env.DIST_APP substitution.
    # (The legacy hardcoded `dist\\eCan-...` form is what caused the bug.)
    assert "dist\\${{ env.DIST_APP }}-${{ needs.validate-tag.outputs.version }}-windows-amd64-Setup.exe" in cn_text, (
        "release-cn.yml: Prepare-artifacts must reference the Windows "
        "installer via `dist\\${{ env.DIST_APP }}-…-windows-amd64-Setup.exe`. "
        "If this contract regresses to a hardcoded `dist\\eCan-…` (or "
        "`dist\\eCan.cn-…`), the workflow will look for a file build.py "
        "never writes (run #86820634953)."
    )
    assert "dist\\${{ env.DIST_APP }}-${{ needs.validate-tag.outputs.version }}-windows-amd64-Setup.exe" in intl_text, (
        "release-intl.yml: Prepare-artifacts must use the same "
        "`dist\\${{ env.DIST_APP }}-…-windows-amd64-Setup.exe` "
        "form as release-cn.yml, so the two pipelines remain "
        "byte-equal after sym-check normalisation."
    )

    # cn must declare DIST_APP=eCan.cn (matches apps/cn/build/build_config_cn.json
    # :app.name = "eCan.cn" → installer_filename = "eCan.cn-{ver}-...-Setup").
    # intl must declare DIST_APP=eCan (matches build_config_intl.json).
    cn_dist_app = re.search(r"DIST_APP:\s*(\S+)", cn_text)
    intl_dist_app = re.search(r"DIST_APP:\s*(\S+)", intl_text)
    assert cn_dist_app, "release-cn.yml: must declare DIST_APP env var"
    assert intl_dist_app, "release-intl.yml: must declare DIST_APP env var"
    assert cn_dist_app.group(1) == "eCan.cn", (
        f"release-cn.yml: DIST_APP must be `eCan.cn` to match "
        f"apps/cn/build/build_config_cn.json:app.name. "
        f"Got `{cn_dist_app.group(1)}`."
    )
    assert intl_dist_app.group(1) == "eCan", (
        f"release-intl.yml: DIST_APP must be `eCan` to match "
        f"apps/intl/build/build_config_intl.json:app.name. "
        f"Got `{intl_dist_app.group(1)}`."
    )

    # build.py must emit the installer_filename using app.name (the same
    # value the workflow's DIST_APP resolves to). If a future commit
    # changes build.py to hardcode 'eCan' for both pipelines (or to
    # derive the prefix from somewhere else), this test catches it.
    assert "installer_filename = f\"{app_info.get('name', 'eCan')}-" in build_text, (
        "build_system/ecan_build.py: installer_filename must template "
        "from app_info.get('name', 'eCan') so cn produces eCan.cn-{ver} "
        "and intl produces eCan-{ver}. A hardcoded 'eCan' here would "
        "make both pipelines emit the same filename and break "
        "distinguishability in shared dist/."
    )

    # The `[INFO] Installer:` log line in ecan_build.py must mirror the
    # actual OutputBaseFilename so a log-grep operator doesn't get told
    # the installer is `eCan-{ver}-...` when build.py actually wrote
    # `eCan.cn-{ver}-...` (historical bug, fixed in this commit).
    assert "app_info.get('name', 'eCan')}" in build_text, (
        "build_system/ecan_build.py: [INFO] Installer: log line must "
        "use app_info.get('name', 'eCan') (not a hardcoded 'eCan') so "
        "the log message matches the on-disk filename for both cn and intl."
    )