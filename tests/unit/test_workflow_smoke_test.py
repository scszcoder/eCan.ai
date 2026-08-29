"""
Unit tests for build_system/scripts/workflow_smoke_test.py.

The smoke test complements the YAML-byte symmetry check:

  * Symmetry check normalizes **structure** (job ids, artifact names,
    secret interpolation, `dist/` prefixes) and confirms the two
    workflows collapse to the same form.
  * Smoke test normalizes **content** (run-block bodies, shell, runs-on)
    and confirms the two workflows actually do the same thing at
    runtime, and that each workflow's bash/PowerShell is itself
    syntactically valid.

The smoke test has six rule families: `bash-n-syntax`,
`python-c-syntax`, `pwsh-broken-pywin32-postinstall`,
`pwsh-write-host-in-python-c`, `deprecated-runner`,
`architecture-mismatch`, and `cn-intl-body-mismatch`. Each has its
own failure mode and its own test here, so a regression in one rule
can be isolated from the others.
"""

from __future__ import annotations

import re
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Make the script importable.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "build_system" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from workflow_smoke_test import (  # noqa: E402
    RunBlock,
    Report,
    _canonical_run_body,
    _parse_workflow,
    _arch_of_runs_on,
    _arch_of_self_hosted_branch,
    check_bash_syntax,
    check_python_c_syntax,
    check_powershell_pitfalls,
    check_deprecated_runners,
    check_architecture_mismatch,
    check_cn_intl_parity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, body: str) -> Path:
    """Write a single-block workflow YAML and return the path."""
    p = tmp_path / name
    p.write_text(body)
    return p


def _one_block_workflow(job_id: str, step_name: str, shell: str, body: str) -> str:
    """Minimal workflow containing a single `run:` block.

    The structure is the bare minimum the parser needs to compute
    (job_id, step_name, shell, body) for the run-block.
    """
    return f"""\
name: t
on: {{workflow_dispatch: {{inputs: {{}}}}}}
jobs:
  {job_id}:
    runs-on: ubuntu-latest
    steps:
      - name: {step_name}
        shell: {shell}
        run: |
{chr(10).join('          ' + line for line in body.splitlines())}
"""


# ---------------------------------------------------------------------------
# bash -n
# ---------------------------------------------------------------------------

def test_bash_n_passes_for_valid_script(tmp_path):
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="bash",
        body="if [ \"$FOO\" = \"bar\" ]; then echo ok; fi",
        line=10,
    )
    report = Report()
    check_bash_syntax(report, block)
    assert report.issues == []


def test_bash_n_passes_for_real_validate_tag_body():
    """The validate-tag block has a real, complex bash script. It must
    pass `bash -n` even though it's the most complex run-block in the
    repo. If this test fails, the validator has broken a working
    script — a regression we'd otherwise only catch on a real GHA run.
    """
    cn = Path(".github/workflows/release-cn.yml").read_text()
    blocks, _ = _parse_workflow(Path(".github/workflows/release-cn.yml"))
    validate_blocks = [
        b for b in blocks
        if b.step_name == "Validate and extract version"
    ]
    assert len(validate_blocks) == 1, "expected exactly one validate-tag block"
    report = Report()
    check_bash_syntax(report, validate_blocks[0])
    for issue in report.issues:
        assert not (issue.rule == "bash-n-syntax" and issue.severity == "error"), (
            f"validate-tag block failed `bash -n`: {issue.message}"
        )


def test_bash_n_flags_unterminated_quote(tmp_path):
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "break-quote", "bash",
        "export PATH=\"$PWD/.venv/bin:$PATH",
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_bash_syntax(report, blocks[0])
    assert any(
        i.rule == "bash-n-syntax" and i.severity == "error"
        for i in report.issues
    ), "unterminated quote should fail `bash -n`"


def test_bash_n_flags_unmatched_if(tmp_path):
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "unmatched-if", "bash",
        "if [ \"$FOO\" = \"bar\" ]; then echo ok",
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_bash_syntax(report, blocks[0])
    assert any(
        i.rule == "bash-n-syntax" and i.severity == "error"
        for i in report.issues
    )


def test_bash_n_skips_pwsh_blocks(tmp_path):
    """`shell: pwsh` blocks must NOT be passed to `bash -n`. bash is
    not the right interpreter and would produce false positives."""
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "ps-only", "pwsh",
        "if (Test-Path \"foo.exe\") { Write-Host \"bar\" }",
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_bash_syntax(report, blocks[0])
    assert report.issues == []


# ---------------------------------------------------------------------------
# python -c
# ---------------------------------------------------------------------------

def test_python_c_passes_for_clean_payload(tmp_path):
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "verify", "bash",
        "python -c \"import win32api; print('ok')\"",
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_python_c_syntax(report, blocks[0])
    assert report.issues == []


def test_python_c_catches_write_host_in_payload(tmp_path):
    """The original outage: `python -c \"...Write-Host...\"` is a
    Python syntax error because `Write-Host` is PowerShell, not Python.
    The smoke test must catch this and report it as a Python error.
    """
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "verify", "pwsh",
        'python -c "import win32api; Write-Host \'ok\'"',
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_python_c_syntax(report, blocks[0])
    assert any(
        i.rule == "python-c-syntax" and i.severity == "error"
        for i in report.issues
    ), "Write-Host inside python -c must fail Python compile"


def test_python_c_handles_expressions_in_payload(tmp_path):
    """A real `python -c "..."` payload in a workflow may contain
    `${{ ... }}` interpolations (e.g. `os.environ.get("${{ ... }}")`).
    The expression text is just a string to Python at the point
    `python -c` parses, so we don't strip it — we just confirm the
    Python *around* the expression is valid."""
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "verify", "bash",
        "python -c \"x = 1; print(x)\"",
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_python_c_syntax(report, blocks[0])
    assert report.issues == []


def test_python_c_handles_multiple_payloads(tmp_path):
    """A block can have multiple `python -c` invocations. Each must
    be checked independently — one bad payload shouldn't mask the
    other good ones."""
    p = _write(tmp_path, "wf.yml", _one_block_workflow(
        "build", "multi", "bash",
        "python -c \"import sys; print(sys.version)\"\n"
        "python -c \"import os; Write-Host 'oops'\"",
    ))
    blocks, _ = _parse_workflow(p)
    report = Report()
    check_python_c_syntax(report, blocks[0])
    assert any(
        i.rule == "python-c-syntax" and i.severity == "error"
        for i in report.issues
    )


# ---------------------------------------------------------------------------
# PowerShell pitfalls
# ---------------------------------------------------------------------------

def test_pwsh_flags_write_host_in_python_c(tmp_path):
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="pwsh",
        body='python -c "import win32api; Write-Host \'ok\'"',
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert any(
        i.rule == "pwsh-write-host-in-python-c" and i.severity == "error"
        for i in report.issues
    )


def test_pwsh_flags_broken_pywin32_postinstall(tmp_path):
    """The regression we just fixed: `python -m pywin32_postinstall`
    fails on pywin32 >= 310 because the wheel doesn't ship a
    `pywin32_postinstall` module. The smoke test must catch the
    broken module form even when it's the only line in the block."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="pwsh",
        body="python -m pywin32_postinstall -install",
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert any(
        i.rule == "pwsh-broken-pywin32-postinstall" and i.severity == "error"
        for i in report.issues
    )


def test_pwsh_ignores_broken_pywin32_in_comments():
    """The current `Install Windows-specific packages` step has a
    comment block that REFERENCES the broken form to explain why we
    don't use it. The smoke test must NOT mistake the comment for
    actual code. The check is line-based — comments starting with
    `#` are stripped before the regex runs."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="pwsh",
        body=(
            "python -m win32.scripts.pywin32_postinstall -install\n"
            "# The `python -m pywin32_postinstall` form recommended\n"
            "# by older revisions of the pywin32 README fails on\n"
            "# pywin32 >= 310. We use the correct form above.\n"
            "python -c \"import win32api; print('ok')\""
        ),
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert not any(
        i.rule == "pwsh-broken-pywin32-postinstall" and i.severity == "error"
        for i in report.issues
    ), "comment referencing the broken form must not trip the check"


def test_pwsh_warns_copy_item_trailing_backslash():
    """Windows Prepare-artifacts step has `Copy-Item ... artifacts\\`.
    Legal PowerShell but easy to drop in review. The smoke test must
    warn (not error) so the structural symmetry check still passes
    but the cosmetic risk is visible."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="pwsh",
        body='Copy-Item "foo.exe" artifacts\\',
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert any(
        i.rule == "pwsh-copy-trailing-backslash" and i.severity == "warning"
        for i in report.issues
    )


def test_pwsh_skips_bash_blocks(tmp_path):
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="bash",
        body="python -m pywin32_postinstall -install",
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert report.issues == []


def test_pwsh_also_runs_on_shell_powershell_blocks():
    """check_powershell_pitfalls must run on `shell: powershell` blocks
    too, not only `shell: pwsh`. The two shells have different
    capability surfaces (e.g. winget is absent from Win PS v1), and
    the original bug (`winget` in `shell: powershell` on a self-hosted
    runner that has no App Installer) would not have been caught if
    this guard only ran on `shell: pwsh`."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="powershell",
        body='Write-Host "hello"',
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert report.issues == [], (
        "check_powershell_pitfalls should run on shell=powershell blocks"
    )


def test_pwsh_flags_winget_in_shell_powershell():
    """`winget` in `shell: powershell` fails on self-hosted runners
    that don't have the App Installer / Windows Package Manager UWP
    package installed, because `shell: powershell` invokes
    `C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`
    which does NOT bundle winget. The smoke test must catch this."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="powershell",
        body="winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements",
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert any(
        i.rule == "pwsh-winget-in-shell-powershell" and i.severity == "error"
        for i in report.issues
    ), "`winget` in `shell: powershell` must error"


def test_pwsh_winget_is_allowed_in_shell_pwsh():
    """`winget` is fine under `shell: pwsh` (PowerShell 7) because
    pwsh bundles the App Installer / winget UWP package. The guard
    must NOT fire on `shell: pwsh` blocks."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="pwsh",
        body="winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements",
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert not any(
        i.rule == "pwsh-winget-in-shell-powershell" for i in report.issues
    ), "`winget` in `shell: pwsh` must not be flagged"


def test_pwsh_winget_ignores_comments():
    """A comment that mentions `winget` in a `shell: powershell` block
    must NOT trip the guard — only live code counts."""
    block = RunBlock(
        workflow="wf.yml", job_id="build", step_name="x", shell="powershell",
        body="# winget is not available in shell: powershell\nWrite-Host 'ok'",
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert not any(
        i.rule == "pwsh-winget-in-shell-powershell" for i in report.issues
    ), "comment mentioning winget must not trip the check"


def test_pwsh_flags_bare_python_invocation():
    """The bug we just fixed: a `shell: pwsh` step with
    `python build.py prod --version ...` resolves to the SYSTEM python
    (C:\\hostedtoolcache\\...\\python.exe), not the venv python —
    because setup-python@v6 prepends the system python to PATH while
    setup-python-env only appends `.venv/Scripts`. The smoke test
    must catch any bare `python[3]` invocation in a pwsh step."""
    block = RunBlock(
        workflow="wf.yml", job_id="build-windows", step_name="Build installer",
        shell="pwsh",
        body=(
            "$env:ECAN_ENVIRONMENT = 'production'\n"
            "python build.py prod --version 1.0.0 --app intl"
        ),
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert any(
        i.rule == "pwsh-bare-python-must-use-venv" and i.severity == "error"
        for i in report.issues
    ), "bare `python` invocation in a pwsh block must fail"


def test_pwsh_flags_bare_python3_invocation():
    """Symmetric to the above: `python3` is the same bare token on
    Windows when no venv python is on PATH."""
    block = RunBlock(
        workflow="wf.yml", job_id="build-windows", step_name="x", shell="pwsh",
        body="python3 -m pip --version",
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert any(
        i.rule == "pwsh-bare-python-must-use-venv" and i.severity == "error"
        for i in report.issues
    )


def test_pwsh_passes_with_explicit_venv_python():
    """The fix: `& $VenvPython ...` (where $VenvPython = the explicit
    `.venv\\Scripts\\python.exe` path) must NOT fire — the bare-token
    anchor should match only when `python` / `python3` is the
    command, not when it's the value of a PowerShell variable."""
    block = RunBlock(
        workflow="wf.yml", job_id="build-windows", step_name="x", shell="pwsh",
        body=(
            "$VenvPython = Join-Path $env:GITHUB_WORKSPACE '.venv\\Scripts\\python.exe'\n"
            "if (-not (Test-Path $VenvPython)) {\n"
            "    throw 'venv missing'\n"
            "}\n"
            "& $VenvPython build.py prod --version 1.0.0 --app intl\n"
            "& $VenvPython -m win32.scripts.pywin32_postinstall -install"
        ),
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert not any(
        i.rule == "pwsh-bare-python-must-use-venv" for i in report.issues
    ), "explicit `& $VenvPython ...` invocation must NOT fire"


def test_pwsh_passes_when_python_only_in_path_or_test():
    """The `python.exe` literal can appear in path expressions and
    `Test-Path` arguments without being an invocation. The check
    must not match those."""
    block = RunBlock(
        workflow="wf.yml", job_id="build-windows", step_name="x", shell="pwsh",
        body=(
            "# diag: C:\\hostedtoolcache\\windows\\Python\\3.12.10\\x64\\python.exe\n"
            "if (Test-Path 'C:\\hostedtoolcache\\windows\\Python\\3.12.10\\x64\\python.exe') {\n"
            "    Write-Host 'system python exists'\n"
            "}\n"
            "& $VenvPython build.py prod --version 1.0.0 --app intl"
        ),
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert not any(
        i.rule == "pwsh-bare-python-must-use-venv" for i in report.issues
    ), "python inside path literals or Test-Path args must NOT fire"


def test_pwsh_ignores_bare_python_in_comments():
    """Comments referencing the bare-`python` trap (to explain why
    we don't use it) must not trip the check. Comment-stripping
    already runs in `check_powershell_pitfalls` before this rule."""
    block = RunBlock(
        workflow="wf.yml", job_id="build-windows", step_name="x", shell="pwsh",
        body=(
            "# A bare `python` in pwsh resolves to the system python, NOT the venv.\n"
            "# Use `& $VenvPython ...` instead.\n"
            "& $VenvPython build.py prod --version 1.0.0 --app intl"
        ),
        line=10,
    )
    report = Report()
    check_powershell_pitfalls(report, block)
    assert not any(
        i.rule == "pwsh-bare-python-must-use-venv" for i in report.issues
    )


# ---------------------------------------------------------------------------
# Deprecated runner labels
# ---------------------------------------------------------------------------

def test_deprecated_runner_flags_ubuntu_22_04():
    report = Report()
    check_deprecated_runners(report, {
        "build-linux": "'ubuntu-22.04'",
    }, "w.yml")
    assert any(
        i.rule == "deprecated-runner" and i.severity == "error"
        for i in report.issues
    )


def test_deprecated_runner_flags_macos_14():
    report = Report()
    check_deprecated_runners(report, {
        "build-macos": "'macos-14'",
    }, "w.yml")
    assert any(
        i.rule == "deprecated-runner" and i.severity == "error"
        for i in report.issues
    )


def test_deprecated_runner_passes_for_latest():
    report = Report()
    check_deprecated_runners(report, {
        "build-linux":  "'ubuntu-latest'",
        "build-macos":  "'macos-latest'",
        "build-windows": "'windows-latest'",
    }, "w.yml")
    assert report.issues == []


def test_deprecated_runner_flags_conditional_fallback():
    """The release workflows use `'ubuntu-latest'` as the fallback
    branch of a conditional. The smoke test must surface the
    deprecated label even when it's nestled inside a `${{ ... || 'ubuntu-22.04' }}`
    expression — that's exactly the usage that broke here."""
    report = Report()
    check_deprecated_runners(report, {
        "build-linux":
            "${{ github.event.inputs.runner_group == 'ecan-linux-amd64' "
            "&& fromJSON('...') || 'ubuntu-22.04' }}",
    }, "w.yml")
    assert any(
        i.rule == "deprecated-runner" and i.severity == "error"
        for i in report.issues
    )


def test_deprecated_runner_flags_macos_14_large():
    """`macos-14-large` and `macos-14-xlarge` are also deprecated."""
    report = Report()
    check_deprecated_runners(report, {
        "build": "'macos-14-large'",
    }, "w.yml")
    assert any(i.rule == "deprecated-runner" for i in report.issues)


# ---------------------------------------------------------------------------
# Architecture-mismatch check
# ---------------------------------------------------------------------------

def test_arch_resolves_fallback_label():
    """`_arch_of_runs_on` returns the GitHub-hosted fallback arch
    when the runs-on has a `||` chain. Specifically, `macos-15-intel`
    (x86_64) is the right fallback for amd64 macOS builds."""
    s = "${{ github.event.inputs.runner_group == 'ecan-macos-amd64' " \
        "&& fromJSON('[\"self-hosted\",\"macos\",\"x64\",\"ecan-build\"]') " \
        "|| 'macos-15-intel' }}"
    assert _arch_of_runs_on(s) == "x86_64"


def test_arch_resolves_arm64_fallback():
    """`macos-latest` is arm64 (Tahoe on Apple Silicon).
    `_arch_of_runs_on` returns the runtime arch of the GitHub-hosted
    fallback, which is arm64 (not aarch64 — those are build-target
    vs runtime naming for the same thing)."""
    s = "${{ github.event.inputs.runner_group == 'ecan-macos-aarch64' " \
        "&& fromJSON('[\"self-hosted\",\"macos\",\"aarch64\",\"ecan-build\"]') " \
        "|| 'macos-latest' }}"
    assert _arch_of_runs_on(s) == "arm64"


def test_arch_resolves_unknown_to_none():
    """An unknown runner label returns None, signaling the check
    can't decide rather than firing a false positive."""
    assert _arch_of_runs_on("'custom-runner-pool-42'") is None


def test_arch_self_hosted_branch_extracts_x64():
    """The self-hosted branch of `build-macos-amd64` is
    `["self-hosted","macos","x64","ecan-build"]` — i.e. x86_64."""
    s = "${{ github.event.inputs.runner_group == 'ecan-macos-amd64' " \
        "&& fromJSON('[\"self-hosted\",\"macos\",\"x64\",\"ecan-build\"]') " \
        "|| 'macos-15-intel' }}"
    assert _arch_of_self_hosted_branch(s) == "x86_64"


def test_arch_self_hosted_branch_extracts_correct_label():
    """The self-hosted branch of `build-macos-aarch64` should
    contain `aarch64` so the arch check passes."""
    s = "${{ github.event.inputs.runner_group == 'ecan-macos-aarch64' " \
        "&& fromJSON('[\"self-hosted\",\"macos\",\"aarch64\",\"ecan-build\"]') " \
        "|| 'macos-latest' }}"
    assert _arch_of_self_hosted_branch(s) == "aarch64"


def test_arch_self_hosted_branch_none_for_literal_label():
    """`runs-on: 'ubuntu-latest'` has no `||`, so the self-hosted
    branch is the whole expression and we don't try to extract a
    self-hosted label from it."""
    assert _arch_of_self_hosted_branch("'ubuntu-latest'") is None


def test_arch_mismatch_catches_amd64_with_arm64_fallback():
    """The bug we just fixed: `build-macos-amd64` with fallback
    `macos-latest`. The smoke test must catch it."""
    report = Report()
    check_architecture_mismatch(report, {
        "build-macos-amd64":
            "${{ github.event.inputs.runner_group == 'ecan-macos-amd64' "
            "&& fromJSON('[\"self-hosted\",\"macos\",\"x64\",\"ecan-build\"]') "
            "|| 'macos-latest' }}",
    }, "w.yml")
    assert any(
        i.rule == "architecture-mismatch" and i.severity == "error"
        for i in report.issues
    ), "macos-amd64 with macos-latest fallback must fire"


def test_arch_mismatch_passes_for_correct_x86_64_fallback():
    """After the fix: `build-macos-amd64` with `macos-15-intel`
    fallback must NOT fire."""
    report = Report()
    check_architecture_mismatch(report, {
        "build-macos-amd64":
            "${{ github.event.inputs.runner_group == 'ecan-macos-amd64' "
            "&& fromJSON('[\"self-hosted\",\"macos\",\"x64\",\"ecan-build\"]') "
            "|| 'macos-15-intel' }}",
    }, "w.yml")
    assert not any(
        i.rule == "architecture-mismatch" for i in report.issues
    )


def test_arch_mismatch_catches_aarch64_with_intel_fallback():
    """Symmetric: `build-macos-aarch64` with `macos-15-intel`
    fallback is wrong — aarch64 builds need an Apple Silicon runner."""
    report = Report()
    check_architecture_mismatch(report, {
        "build-macos-aarch64":
            "${{ github.event.inputs.runner_group == 'ecan-macos-aarch64' "
            "&& fromJSON('[\"self-hosted\",\"macos\",\"aarch64\",\"ecan-build\"]') "
            "|| 'macos-15-intel' }}",
    }, "w.yml")
    assert any(i.rule == "architecture-mismatch" for i in report.issues)


def test_arch_mismatch_catches_broken_self_hosted_branch():
    """The bug we *could* see next: `build-macos-amd64` with the
    self-hosted branch pointing at aarch64. The check must catch this
    even when the GitHub-hosted fallback is correct (`macos-15-intel`).
    """
    report = Report()
    check_architecture_mismatch(report, {
        "build-macos-amd64":
            "${{ github.event.inputs.runner_group == 'ecan-macos-amd64' "
            "&& fromJSON('[\"self-hosted\",\"macos\",\"aarch64\",\"ecan-build\"]') "
            "|| 'macos-15-intel' }}",
    }, "w.yml")
    assert any(
        i.rule == "architecture-mismatch" and "self-hosted" in i.message
        for i in report.issues
    )


def test_arch_mismatch_passes_for_windows_and_linux():
    """`windows-latest` and `ubuntu-latest` are x64. Their build
    jobs (build-windows, build-linux) need x64 runners, so the
    fallback is correct."""
    report = Report()
    check_architecture_mismatch(report, {
        "build-windows": "'windows-latest'",
        "build-linux":  "'ubuntu-latest'",
    }, "w.yml")
    assert not any(
        i.rule == "architecture-mismatch" for i in report.issues
    )


def test_arch_mismatch_passes_for_arm64_build_with_arm64_fallback():
    """`build-macos-aarch64` needs aarch64; `macos-latest` is arm64
    (Nov 2026 macOS-26 Tahoe is the latest). No mismatch."""
    report = Report()
    check_architecture_mismatch(report, {
        "build-macos-aarch64":
            "${{ github.event.inputs.runner_group == 'ecan-macos-aarch64' "
            "&& fromJSON('[\"self-hosted\",\"macos\",\"aarch64\",\"ecan-build\"]') "
            "|| 'macos-latest' }}",
    }, "w.yml")
    assert not any(
        i.rule == "architecture-mismatch" for i in report.issues
    )


def test_arch_mismatch_ignores_non_build_jobs():
    """Service jobs (validate-tag, final-status, print-gha-fallback-
    downloads) don't have a fixed arch intent. The check must skip
    them so it doesn't trigger on e.g. `final-status: ubuntu-latest`."""
    report = Report()
    check_architecture_mismatch(report, {
        "validate-tag":       "'ubuntu-latest'",
        "final-status":       "'ubuntu-latest'",
        "print-gha-fallback": "'ubuntu-latest'",
    }, "w.yml")
    assert not any(
        i.rule == "architecture-mismatch" for i in report.issues
    )


def test_arch_mismatch_handles_macos_26_intel():
    """`macos-26-intel` is also a valid x86_64 fallback (the
    follow-on to macos-15-intel once 15-intel retires in Aug 2027)."""
    report = Report()
    check_architecture_mismatch(report, {
        "build-macos-amd64":
            "${{ github.event.inputs.runner_group == 'ecan-macos-amd64' "
            "&& fromJSON('[\"self-hosted\",\"macos\",\"x64\",\"ecan-build\"]') "
            "|| 'macos-26-intel' }}",
    }, "w.yml")
    assert not any(
        i.rule == "architecture-mismatch" for i in report.issues
    )


# ---------------------------------------------------------------------------
# CN/INTL parity
# ---------------------------------------------------------------------------

def test_parity_passes_for_matching_bodies(tmp_path):
    cn = _write(tmp_path, "cn.yml", _one_block_workflow(
        "build-windows", "x", "bash",
        'python build.py prod --version "1.0.0" --app cn',
    ))
    intl = _write(tmp_path, "intl.yml", _one_block_workflow(
        "build-windows", "x", "bash",
        'python build.py prod --version "1.0.0" --app intl',
    ))
    cn_blocks, cn_runs_on = _parse_workflow(cn)
    intl_blocks, intl_runs_on = _parse_workflow(intl)
    report = Report()
    check_cn_intl_parity(report, cn_blocks, intl_blocks, cn_runs_on, intl_runs_on)
    assert report.issues == []


def test_parity_flags_diverging_bodies(tmp_path):
    """The bug we just fixed: CN's Prepare-artifacts step had
    `Test-Path "eCan-...exe"` (no `dist\\`), INTL had `Test-Path
    "dist\\eCan-...exe"`. The YAML byte-symmetry check normalizes
    the `dist\\` prefix away, so it accepts both sides. The smoke
    test must catch the actual divergence."""
    cn = _write(tmp_path, "cn.yml", _one_block_workflow(
        "build-windows", "Prepare artifacts", "pwsh",
        'if (Test-Path "eCan-${{ needs.validate-tag.outputs.version }}-windows-amd64.exe") {\n'
        '    Copy-Item "eCan-${{ needs.validate-tag.outputs.version }}-windows-amd64.exe" artifacts\\\n'
        '}',
    ))
    intl = _write(tmp_path, "intl.yml", _one_block_workflow(
        "build-windows", "Prepare artifacts", "pwsh",
        'if (Test-Path "dist\\eCan-${{ needs.validate-tag.outputs.version }}-windows-amd64.exe") {\n'
        '    Copy-Item "dist\\eCan-${{ needs.validate-tag.outputs.version }}-windows-amd64.exe" artifacts\\\n'
        '}',
    ))
    cn_blocks, cn_runs_on = _parse_workflow(cn)
    intl_blocks, intl_runs_on = _parse_workflow(intl)
    report = Report()
    check_cn_intl_parity(report, cn_blocks, intl_blocks, cn_runs_on, intl_runs_on)
    assert any(
        i.rule == "cn-intl-body-mismatch" and i.severity == "error"
        for i in report.issues
    )


def test_parity_canonicalizes_app_name():
    """A body that differs only in `eCan.cn` vs `eCan` should pass
    the parity check, because that's a canonical form the symmetry
    check already normalizes."""
    cn_body = 'echo "Built eCan.cn-1.0.0.exe"'
    intl_body = 'echo "Built eCan-1.0.0.exe"'
    assert _canonical_run_body(cn_body) == _canonical_run_body(intl_body)


def test_parity_canonicalizes_secrets():
    cn_body = 'echo "${{ secrets.GITEE_TOKEN }}"'
    intl_body = 'echo "${{ secrets.OTHER_TOKEN }}"'
    assert _canonical_run_body(cn_body) == _canonical_run_body(intl_body)


def test_parity_canonicalizes_app_flag():
    """`--app cn` vs `--app intl` is the canonical per-pipeline
    difference. The parity check must NOT flag it as a divergence."""
    cn_body = 'python build.py prod --version 1.0.0 --app cn'
    intl_body = 'python build.py prod --version 1.0.0 --app intl'
    assert _canonical_run_body(cn_body) == _canonical_run_body(intl_body)


def test_parity_canonicalizes_cloud_provider():
    """CN uses COS, INTL uses S3. Both bodies should collapse to
    the same canonical form so the parity check doesn't false-flag
    the legitimate backend divergence."""
    cn_body = 'echo "COS upload: ok"'
    intl_body = 'echo "S3 upload: ok"'
    assert _canonical_run_body(cn_body) == _canonical_run_body(intl_body)


def test_parity_canonicalizes_requirements_filename():
    """`requirements-cn.txt` vs `requirements-intl.txt` is the
    one-per-pipeline dep-set difference. The canonicalization
    collapses them so the parity check reports semantic differences
    only."""
    cn_body = 'pip install -r "requirements-cn.txt"'
    intl_body = 'pip install -r "requirements-intl.txt"'
    assert _canonical_run_body(cn_body) == _canonical_run_body(intl_body)


def test_parity_canonicalizes_build_system_requirements_filename():
    """Storage jobs (upload / appcast / latest-json) intentionally use
    a narrow requirements file:

      * intl: ``build_system/scripts/requirements.txt``           (boto3 + pyyaml + packaging)
      * cn  : ``build_system/scripts/requirements-cos.txt``       (cos-python-sdk-v5 + pyyaml + packaging)

    Without collapsing these, the upload workflow bodies would no
    longer compare byte-equal across pipelines and the parity check
    would false-fail on the legitimate backend narrowing. This test
    pins the collapse so a future rename can't break the symmetry
    contract."""
    intl_body = 'pip install -r build_system/scripts/requirements.txt'
    cn_body = 'pip install -r build_system/scripts/requirements-cos.txt'
    canonical_intl = _canonical_run_body(intl_body)
    canonical_cn = _canonical_run_body(cn_body)
    assert canonical_intl == canonical_cn
    assert "requirements-<APP>.txt" in canonical_intl


def test_parity_flags_real_pipeline_diffs():
    """A real bug — different `actions` invoked on each side — must
    not be hidden by canonicalization."""
    cn_body = 'echo "Built eCan.cn-1.0.0.exe via pyinstaller"'
    intl_body = 'echo "Built eCan-1.0.0.exe via nuitka"'
    assert _canonical_run_body(cn_body) != _canonical_run_body(intl_body)


def test_parity_flags_runs_on_mismatch(tmp_path):
    """When CN and INTL disagree on the runner for the same job,
    the parity check must surface it. The bytesymmetry check
    compares whole-file structure; this catches per-job divergence."""
    cn_yaml = """\
name: cn
on: {workflow_dispatch: {inputs: {}}}
jobs:
  build-windows:
    runs-on: 'ubuntu-latest'
    steps:
      - name: x
        run: |
          echo "ok"
"""
    intl_yaml = """\
name: intl
on: {workflow_dispatch: {inputs: {}}}
jobs:
  build-windows:
    runs-on: 'macos-14'
    steps:
      - name: x
        run: |
          echo "ok"
"""
    cn = _write(tmp_path, "cn.yml", cn_yaml)
    intl = _write(tmp_path, "intl.yml", intl_yaml)
    cn_blocks, cn_runs_on = _parse_workflow(cn)
    intl_blocks, intl_runs_on = _parse_workflow(intl)
    report = Report()
    check_cn_intl_parity(report, cn_blocks, intl_blocks, cn_runs_on, intl_runs_on)
    assert any(
        i.rule == "cn-intl-runs-on-mismatch" and i.severity == "error"
        for i in report.issues
    )


def test_parity_warns_on_missing_peer(tmp_path):
    """If CN has a step that INTL doesn't (or vice versa), the
    parity check warns. We don't error because the symmetry check
    is the structural authority; this is a content-level smoke
    test for a class of bugs that go through review."""
    cn = _write(tmp_path, "cn.yml", _one_block_workflow(
        "build-windows", "Chinese-only step", "bash",
        'echo "uses Chinese mirror"',
    ))
    intl = _write(tmp_path, "intl.yml", _one_block_workflow(
        "build-windows", "Different step", "bash",
        'echo "uses AWS mirror"',
    ))
    cn_blocks, cn_runs_on = _parse_workflow(cn)
    intl_blocks, intl_runs_on = _parse_workflow(intl)
    report = Report()
    check_cn_intl_parity(report, cn_blocks, intl_blocks, cn_runs_on, intl_runs_on)
    assert any(
        i.rule == "cn-intl-parity-missing" and i.severity == "warning"
        for i in report.issues
    )


# ---------------------------------------------------------------------------
# Real workflow regression
# ---------------------------------------------------------------------------

def test_release_workflows_pass_smoke_test():
    """The two release workflows in the repo, with all the fixes
    applied, must satisfy the smoke test. Pinning this catches a
    future drift that re-introduces any of the bugs we just fixed.
    """
    cn = Path(".github/workflows/release-cn.yml")
    intl = Path(".github/workflows/release-intl.yml")
    if not cn.exists() or not intl.exists():
        pytest.skip("real workflow files not present")

    blocks_cn, runs_on_cn = _parse_workflow(cn)
    blocks_intl, runs_on_intl = _parse_workflow(intl)

    report = Report()
    for block in blocks_cn + blocks_intl:
        check_bash_syntax(report, block)
        check_python_c_syntax(report, block)
        check_powershell_pitfalls(report, block)
    check_deprecated_runners(report, runs_on_cn, cn.name)
    check_deprecated_runners(report, runs_on_intl, intl.name)
    check_architecture_mismatch(report, runs_on_cn, cn.name)
    check_architecture_mismatch(report, runs_on_intl, intl.name)
    check_cn_intl_parity(report, blocks_cn, blocks_intl, runs_on_cn, runs_on_intl)

    # Fail only on errors. Warnings (e.g. trailing backslash on
    # Copy-Item) are tolerated.
    errors = [i for i in report.issues if i.severity == "error"]
    assert not errors, (
        f"smoke test found {len(errors)} error(s):\n"
        + "\n".join(f"  {i}" for i in errors)
    )


def test_release_cn_has_validate_gitee_credentials_per_job():
    """The release-cn.yml workflow has 5 build jobs (Windows/Linux/
    macOS amd64/macOS aarch64/etc.), each of which checks out from
    `https://gitee.com/.../eCan.ai` via `actions/checkout@v6` with
    `token: ${{ secrets.GITEE_TOKEN }}`. The git server-side
    behaviour for missing/invalid tokens is to silently ask for a
    username via the terminal — which is disabled in CI — and fail
    with an opaque exit-128: "fatal: could not read Username for
    'https://gitee.com'".

    To prevent this opaque failure, every checkout must be preceded
    by a `Validate Gitee credentials` step that fails early with a
    precise ::error:: pointing the operator at Settings → Secrets →
    GITEE_TOKEN. This test pins that there is exactly one such
    validator per checkout (5 total) and that each appears in the
    same job as its checkout.

    Without this guard, a missing GITEE_TOKEN surfaces as "Checkout
    from Gitee mirror" failing in CI with no clue why."""
    cn = Path(".github/workflows/release-cn.yml")
    if not cn.exists():
        pytest.skip("real workflow file not present")
    text = cn.read_text()

    checkout_count = text.count("- name: Checkout from Gitee mirror")
    validate_count = text.count("- name: Validate Gitee credentials")
    # validate-tag runs on GitHub-hosted Ubuntu and has its own early token
    # validator, but checks out from GitHub. The four platform build jobs are
    # the only jobs that conditionally check out from Gitee.
    assert checkout_count == 4 and validate_count == 5, (
        f"release-cn.yml must have 4 Gitee checkout steps and 5 token "
        f"validators (validate-tag plus the 4 build jobs); "
        f"found checkout={checkout_count}, validate={validate_count}. "
        f"Each platform build job needs its own validator so a "
        f"missing GITEE_TOKEN fails fast with a precise message "
        f"instead of the opaque 'could not read Username for "
        f"https://gitee.com' exit-128."
    )

    # Checkout runs before repository files exist. It must also avoid Gitee's
    # /raw route, which the China self-hosted runner gateway rejects even when
    # Git Smart-HTTP is reachable.
    assert "/raw/" not in text
    assert ". build_system/scripts/checkout-gitee.ps1" not in text

    # The validator step must appear in each job BEFORE the checkout
    # step. If a future refactor moves it after, the early-fail
    # behaviour is lost and the checkout step still produces the
    # opaque error first.
    job_blocks = re.split(r"^\s{4}steps:\s*$", text, flags=re.MULTILINE)
    for block in job_blocks:
        if "- name: Checkout from Gitee mirror" not in block:
            continue
        # Find the relative positions of the two step names within
        # this job's step list.
        validator_pos = block.find("- name: Validate Gitee credentials")
        checkout_pos = block.find("- name: Checkout from Gitee mirror")
        assert 0 <= validator_pos < checkout_pos, (
            "Validate Gitee credentials must appear BEFORE the "
            "Checkout from Gitee mirror step in every job; otherwise "
            "the early-fail behaviour is lost and the checkout still "
            "produces the opaque 'could not read Username' error."
        )


def test_release_workflows_have_setup_ota_signing_key_in_build_windows():
    """The build-windows job in release-intl.yml and release-cn.yml
    must have a `Setup OTA signing key` step. Otherwise `build.py prod`
    reaches `sign_ota_artifacts()` (which the Windows-venv-python fix
    in 4e396687 made possible) and fails with the opaque:

        [OTA-SIGN] [ERROR] Ed25519 private key file does not exist

    on every Windows release for test/staging/production.

    Pin: both workflows have exactly one such step, gated on the
    same condition (`environment in {production, staging, test}`),
    AND it appears BEFORE `Build Windows installer` (otherwise the
    build script picks up the absence before the key is written).
    """
    for path in (
        Path(".github/workflows/release-intl.yml"),
        Path(".github/workflows/release-cn.yml"),
    ):
        if not path.exists():
            pytest.skip(f"{path} not present")
        text = path.read_text()
        # Exactly one (each file has its own; if a future PR adds
        # another, the parity check + byte-symmetry will catch it
        # either way, but we pin 1 here for clarity).
        ota_count = text.count("- name: Setup OTA signing key")
        assert ota_count >= 1, (
            f"{path.name} has no 'Setup OTA signing key' step. "
            f"`build.py prod` on Windows reaches sign_ota_artifacts() "
            f"after commit 4e396687 fixed the venv-python path; "
            f"without this step, every Windows release in "
            f"test/staging/production fails with 'Ed25519 private "
            f"key file does not exist'."
        )

        # The step must appear in the build-windows job (not just
        # somewhere). Find the build-windows job block and verify.
        bw_marker = "      - name: Setup signtool environment"
        if bw_marker not in text:
            pytest.fail(
                f"{path.name}: could not locate build-windows "
                f"anchor (`{bw_marker.strip()}`); the test cannot "
                f"verify the step lives in the right job."
            )
        bw_start = text.find(bw_marker)
        # Heuristic: look at the most recent `Setup OTA signing key`
        # whose byte offset is < bw_start. If none, the step is not
        # in build-windows.
        ota_positions = [
            m.start() for m in re.finditer(
                r"- name: Setup OTA signing key", text
            )
        ]
        ota_in_bw = [p for p in ota_positions if p < bw_start]
        if not ota_in_bw:
            pytest.fail(
                f"{path.name}: 'Setup OTA signing key' is not "
                f"positioned in the build-windows job (before "
                f"'Setup signtool environment'). Adjust the order "
                f"so the key is on disk before `Build Windows "
                f"installer` runs."
            )


def test_real_workflow_no_winget_in_shell_powershell():
    """After the `shell: powershell` -> `shell: pwsh` fix, neither
    release workflow should have any `shell: powershell` block that
    contains `winget`. This test pins the fix: if someone reverts the
    shell back to `powershell` on a step that uses `winget`, the smoke
    test will catch it before the next CI run on a real self-hosted
    runner."""
    for path in (
        Path(".github/workflows/release-intl.yml"),
        Path(".github/workflows/release-cn.yml"),
    ):
        if not path.exists():
            pytest.skip(f"{path} not present")
        blocks, _ = _parse_workflow(path)
        for block in blocks:
            if block.shell == "powershell":
                # Find winget in non-comment lines
                for line in block.body.splitlines():
                    if not line.lstrip().startswith("#"):
                        if re.search(r"^\s*winget\b", line, re.IGNORECASE):
                            pytest.fail(
                                f"{path.name}: {block.job_id} > "
                                f"{block.step_name}@{block.line}: "
                                f"`winget` found in `shell: powershell` "
                                f"block. Change `shell: powershell` to "
                                f"`shell: pwsh` to fix. "
                                f"Line: {line.strip()!r}"
                            )
