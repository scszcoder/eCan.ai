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
workflow assumes `windows-latest` semantics everywhere because
GitHub-hosted is what the project standardizes on. The
self-hosted runner must be **promoted to the same baseline
once, at registration time**, in
`docs/Windows构建环境部署清单.md` §九.3.1 — not patched
per-job in the workflow.

The docs are the source of truth for the operator setup. The
workflow keeps `shell: pwsh` / `shell: bash` everywhere
because the self-hosted runner is expected to match
`windows-latest` after `register_runner.ps1` + the §九.3.1
manual steps have run.

These tests pin the contract so a future refactor can't
silently remove the §九.3.1 docs instructions or change
the workflow's shell assumptions without realizing the
self-hosted runner depends on them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCS_FILE = REPO / "docs/Windows构建环境部署清单.md"
WORKFLOW_FILE = REPO / ".github/workflows/release-cn.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Docs: §一 基础清单 marks PowerShell 7 as required
# ---------------------------------------------------------------------------

def test_baseline_table_marks_powershell_7_required():
    """§一 基础清单 must list PowerShell 7 (`pwsh.exe`) as a
    required prerequisite. The previous version listed it as
    optional ("可额外安装") — that left self-hosted runners
    without pwsh, which breaks every `shell: pwsh` step in
    the workflow. The docs list must pin it as required so
    the operator knows to install it.
    """
    text = _read(DOCS_FILE)
    # The §一 table contains a row mentioning PowerShell 7.
    # We look for the row that pairs pwsh with a "必装" /
    # "required" framing. The simplest pin: PowerShell 7
    # appears in the "基础清单" section (line 9-25) without
    # the "可额外安装" optional framing.
    base_section_start = text.find("## 一、基础清单")
    base_section_end = text.find("## 二、", base_section_start)
    assert base_section_start != -1, "docs: §一 基础清单 section missing"
    assert base_section_end != -1, "docs: §二 missing"
    base_section = text[base_section_start:base_section_end]
    assert "PowerShell 7" in base_section, (
        "docs/Windows构建环境部署清单.md: §一 基础清单 must list "
        "PowerShell 7 (`pwsh.exe`) as a required prerequisite. "
        "Without it, every `shell: pwsh` step on the self-hosted "
        "runner fails with `##[error]pwsh: command not found`."
    )
    assert "pwsh" in base_section, (
        "docs/Windows构建环境部署清单.md: §一 基础清单 must "
        "explicitly reference `pwsh.exe` so the operator knows "
        "what to install."
    )


# ---------------------------------------------------------------------------
# Docs: §九.3.1 has the baseline install commands
# ---------------------------------------------------------------------------

def test_docs_3_1_section_exists():
    """§九.3.1 must exist. It is the single source of truth for
    the operator setup that brings a self-hosted runner up
    to `windows-latest` baseline. Without it, the operator
    has no instructions to follow.
    """
    text = _read(DOCS_FILE)
    assert "### 3.1 Windows runner 必备工具" in text, (
        "docs/Windows构建环境部署清单.md: §九.3.1 Windows runner "
        "必备工具 section missing. The operator has no way to "
        "install PowerShell 7 + Git Bash on the self-hosted runner "
        "without this section."
    )


def test_docs_3_1_documents_powershell_7_install():
    """§九.3.1 must include a working PowerShell 7 install
    command. We accept either the `winget` route (the fast
    path on Win10 1709+ / Server 2019+) or the direct MSI
    route (the fallback when winget isn't available / network
    is blocked). Both must be there OR a single one with
    enough detail to be copy-paste-runnable.
    """
    text = _read(DOCS_FILE)
    # Find the §九.3.1 block by anchoring on the heading.
    start = text.find("### 3.1 Windows runner 必备工具")
    assert start != -1, "docs: §九.3.1 missing"
    # Read until the next ### heading.
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    assert "winget install --id Microsoft.PowerShell" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must include "
        "`winget install --id Microsoft.PowerShell` as the "
        "primary install path. Got:\n" + block
    )
    assert "PowerShell-7" in block and ".msi" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must include "
        "a direct MSI fallback (`PowerShell-7.x.x-win-x64.msi`) "
        "for when winget isn't available. Got:\n" + block
    )


def test_docs_3_1_documents_git_bash_path_fix():
    """§九.3.1 must include the Git Bash SYSTEM PATH fix.

    Git for Windows installs its bin directory into the *user*
    PATH only. The `actions.runner.*-svc` service starts from
    SYSTEM PATH and never sees it. The fix is to add
    `C:\\Program Files\\Git\\bin` to SYSTEM PATH and restart
    the runner service so the new service process picks it up.
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    assert "C:\\Program Files\\Git\\bin" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must reference "
        "`C:\\Program Files\\Git\\bin` — the Git Bash PATH entry "
        "the operator needs to add. Got:\n" + block
    )
    assert "svc.cmd" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 must instruct "
        "the operator to restart the runner service (`svc.cmd "
        "stop / start`) after the PATH change so the new service "
        "process picks up the new PATH. Got:\n" + block
    )


def test_docs_3_1_has_baseline_verification():
    """§九.3.1 must include a copy-paste verification command
    so the operator can confirm the baseline matches
    `windows-latest` before triggering a build. Without this,
    the first sign that the baseline is wrong is a build
    failure 10 minutes into the workflow.
    """
    text = _read(DOCS_FILE)
    start = text.find("### 3.1 Windows runner 必备工具")
    next_heading = text.find("\n### ", start + 1)
    block = text[start:next_heading if next_heading != -1 else len(text)]
    # Must verify pwsh (not just powershell 5.1)
    assert "pwsh.exe" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 verification "
        "must check `pwsh.exe` is reachable. Got:\n" + block
    )
    assert "bash.exe" in block, (
        "docs/Windows构建环境部署清单.md: §九.3.1 verification "
        "must check `bash.exe` is reachable. Got:\n" + block
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
        "include an entry for `##[error]pwsh: command not found` "
        "pointing the operator at §九.3.1."
    )
    assert "bash: command not found" in checklist, (
        "docs/Windows构建环境部署清单.md: §六 排错 Checklist must "
        "include an entry for `##[error]bash: command not found` "
        "pointing the operator at §九.3.1."
    )
    assert "§九.3.1" in checklist, (
        "docs/Windows构建环境部署清单.md: §六 排错 Checklist must "
        "link to §九.3.1 (the install instructions) so the "
        "operator doesn't have to grep the doc to find them."
    )


# ---------------------------------------------------------------------------
# Workflow: must NOT add a per-job baseline step (we do it once at registration)
# ---------------------------------------------------------------------------

def test_workflow_does_not_have_per_job_baseline_step():
    """The workflow must not contain a per-job baseline step
    ("Bring Windows runner up to windows-latest baseline" or
    similar). The baseline is established once at runner
    registration via `register_runner.ps1` + §九.3.1, NOT per
    job. Adding a per-job step would:

      - inflate every job's runtime (winget + MSI install on
        every job start, even when pwsh is already there),
      - blur who owns the "is pwsh installed?" question
        (workflow vs. runner setup),
      - make the workflow diverge from `windows-latest`
        behavior, when the whole point is to align the two.
    """
    text = _read(WORKFLOW_FILE)
    assert "windows-latest baseline" not in text, (
        "release-cn.yml: contains a per-job 'windows-latest baseline' "
        "step. The baseline belongs in `register_runner.ps1` + "
        "docs/Windows构建环境部署清单.md §九.3.1, not in the workflow. "
        "Per-job steps inflate runtime and blur owner responsibility."
    )
    assert "winget install --id Microsoft.PowerShell" not in text, (
        "release-cn.yml: publishes a `winget install Microsoft.PowerShell` "
        "step. PowerShell 7 installation is a runner-setup concern, "
        "not a per-job concern. Move it to docs §九.3.1."
    )


def test_workflow_uses_pwsh_and_bash_shells():
    """The workflow uses `shell: pwsh` and `shell: bash` freely
    across build-* jobs. This is the contract that the
    self-hosted runner must satisfy — those shells are not
    installed on a vanilla Windows runner, so the docs §九.3.1
    must install them. This test asserts the workflow keeps
    using them so the docs contract stays meaningful (a future
    refactor that switches everything to `shell: powershell`
    would silently invalidate §九.3.1).
    """
    import yaml
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
    # Build-* jobs target at least one of pwsh / bash /
    # powershell. If a future refactor narrows down to ONLY
    # `powershell`, §九.3.1's PowerShell 7 install instruction
    # stops being load-bearing and the docs should be slimmed
    # down. This test forces the reverse: any powsh/bash usage
    # makes §九.3.1 mandatory.
    assert "pwsh" in shells_seen or "bash" in shells_seen, (
        "release-cn.yml: build-* jobs don't use `shell: pwsh` or "
        "`shell: bash` at all. If this is intentional, simplify "
        "docs/Windows构建环境部署清单.md §九.3.1 to remove the "
        "PowerShell 7 / Git Bash install instructions — they're "
        "no longer load-bearing."
    )
