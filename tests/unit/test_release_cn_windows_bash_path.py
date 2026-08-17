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