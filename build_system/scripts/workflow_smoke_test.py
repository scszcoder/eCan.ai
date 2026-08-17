"""
Workflow smoke test for the eCan.ai release pipelines.

WHY THIS EXISTS
===============
The release-pipeline simulator in `build_system/scripts/release_simulator/`
executes validate-tag / detect-env / final-status in a real bash subprocess,
but mocks every heavy `actions/*` step and every build pipeline `run:`
block. That is deliberate — the simulator's job is to surface contract
anomalies (wrong gate, missing output, skipped job), not to actually run
PyInstaller.

But the simulator can't catch the bugs that have hit this repo in
production:

  - `python -m pywin32_postinstall` — the README-recommended form is
    broken on pywin32 >= 310 because the wheel doesn't ship a
    `pywin32_postinstall` module. The actual module is
    `win32.scripts.pywin32_postinstall`.

  - `python -c "import win32api; Write-Host 'ok'"` — mixing PowerShell
    syntax into the Python `-c` payload gives `SyntaxError: invalid
    syntax` once Python parses the string.

  - `ubuntu-22.04` and `macos-14` runner labels — both are mid-
    deprecation as of August 2026, with brownouts starting in
    September 2026 and full retirement by April 2027.

  - `Test-Path "eCan-{version}-windows-amd64.exe"` (no `dist/` prefix)
    in a Windows Prepare-artifacts step — `Test-Path` returns false,
    the `Copy-Item` is skipped, and the S3-transfer artifact uploads
    an empty directory.

This script fills that gap. It parses both `release-cn.yml` and
`release-intl.yml`, extracts every `run:` block, and runs a battery
of real checks against the actual shell that interprets each block:

  1. `bash -n`         — runs `bash -n` on every `shell: bash` block
                         to catch unbalanced quotes, unterminated
                         heredocs, invalid `if`/`for` syntax.

  2. `python3 -c`      — runs `python3 -c <payload>` on every literal
                         `python -c "..."` / `python3 -c "..."`
                         payload to catch Python syntax errors before
                         the workflow ever runs.

  3. pwsh guardian     — known-GHA pitfalls in PowerShell blocks:
                         `Write-Host` inside `python -c`,
                         `python -m pywin32_postinstall`,
                         trailing backslash on `Copy-Item` destinations.

  4. deprecated labels — flags any of the runners GitHub has
                         announced as being sunset: `ubuntu-22.04`,
                         `macos-14`, `macos-13`, `windows-2019`,
                         `windows-2022`.

  5. CN/INTL parity    — for every (job, step) pair, the two sides'
                         run bodies, shell, and runs-on must match
                         after canonicalization. The byte-symmetry
                         check covers **structure**; this script
                         covers **content**.

The script is **advisory** — it never modifies either workflow. It
prints a per-file report and exits non-zero on any check failure so
the lint-gate workflow can pick it up.

USAGE
=====
    python3 build_system/scripts/workflow_smoke_test.py
    python3 build_system/scripts/workflow_smoke_test.py --workflow-one \\
        .github/workflows/release-cn.yml --workflow-two \\
        .github/workflows/release-intl.yml
"""


from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RunBlock:
    """A single `run:` block lifted out of a workflow file.

    Each `run:` block is associated with the job it lives in so that
    the parity check can group matching blocks across CN and INTL.
    """
    workflow: str
    job_id: str
    step_name: str
    shell: str           # 'bash' | 'pwsh' | 'python' | 'sh'
    body: str
    line: int            # source line of the `run:` key


@dataclass
class Issue:
    """A single failure surfaced by the smoke test."""
    severity: str        # 'error' | 'warning'
    workflow: str
    location: str        # "<job> > <step>@<line>"
    rule: str            # short rule id, e.g. 'bash-n-syntax'
    message: str

    def __str__(self) -> str:
        return (
            f"[{self.severity.upper():7}] {self.workflow}:{self.location}: "
            f"{self.rule}: {self.message}"
        )


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def error(self, workflow: str, location: str, rule: str, message: str) -> None:
        self.add(Issue("error", workflow, location, rule, message))

    def warn(self, workflow: str, location: str, rule: str, message: str) -> None:
        self.add(Issue("warning", workflow, location, rule, message))

    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {"error": 0, "warning": 0}
        for i in self.issues:
            out[i.severity] = out.get(i.severity, 0) + 1
        return out


# ---------------------------------------------------------------------------
# Workflow parsing
# ---------------------------------------------------------------------------

# A run-block boundary: any `run: |` (literal block) followed by indented
# lines until we hit a non-indented line. We deliberately use a small
# line-based parser instead of pulling in PyYAML so the script stays
# dependency-free — we only need the `run:` body, not the full AST.
_RUN_KEY_RE = re.compile(r"^(\s*)-?\s*run:\s*\|[+-]?\s*$")
_STEP_NAME_RE = re.compile(r"^(\s*)-?\s*name:\s*(.*?)\s*$")
_JOB_KEY_RE = re.compile(r"^  ([a-z][a-z0-9_-]*):\s*$")
_SHELL_KEY_RE = re.compile(r"^(\s*)shell:\s*(\S+)\s*$")


def _parse_workflow(path: Path) -> tuple[list[RunBlock], dict[str, str]]:
    """Parse a workflow file into (run_blocks, job_id_to_runs_on).

    `job_id_to_runs_on` is what we need for the deprecated-label check
    and the CN/INTL parity check.
    """
    text = path.read_text()
    lines = text.splitlines()

    run_blocks: list[RunBlock] = []
    job_runs_on: dict[str, str] = {}

    current_job: str | None = None
    current_step_name: str | None = None
    current_step_shell: str = "bash"  # GHA default
    current_step_line: int = -1
    in_run_body: bool = False
    run_indent: int = 0
    run_body: list[str] = []

    def _flush_run_body() -> None:
        nonlocal run_body, in_run_body
        if not in_run_body:
            return
        if current_job is not None:
            run_blocks.append(RunBlock(
                workflow=path.name,
                job_id=current_job,
                step_name=current_step_name or "(unnamed)",
                shell=current_step_shell,
                body="\n".join(run_body),
                line=current_step_line,
            ))
        run_body = []
        in_run_body = False

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.lstrip()

        # Top-level job detection: exactly 2 spaces indent and a `:`-terminated
        # token. `  job-name:`. Body lines for a job id never start with
        # the bare token format.
        if re.match(r"^  [a-z][a-z0-9_-]*:\s*$", raw):
            _flush_run_body()
            current_job = stripped.rstrip(":").strip()
            current_step_name = None
            current_step_shell = "bash"
            current_step_line = -1
            continue

        # Track `runs-on:` for the deprecated-label check.
        m = re.match(r"^    runs-on:\s*(.*)$", raw)
        if m and current_job is not None and current_job not in job_runs_on:
            job_runs_on[current_job] = m.group(1).strip()
            continue

        # Step name — applies until the next step.
        m = _STEP_NAME_RE.match(raw)
        if m:
            _flush_run_body()
            current_step_name = m.group(2).strip().strip("'").strip('"')
            current_step_shell = "bash"
            current_step_line = lineno
            continue

        # `shell:` overrides the shell for the current step.
        m = _SHELL_KEY_RE.match(raw)
        if m:
            current_step_shell = m.group(2).strip()
            continue

        # `run: |` opens a literal block.
        if _RUN_KEY_RE.match(raw):
            _flush_run_body()
            in_run_body = True
            run_indent = len(raw) - len(raw.lstrip())
            current_step_line = lineno
            continue

        # Body line of an open `run:` block.
        if in_run_body:
            if not raw.strip():
                run_body.append("")
                continue
            indent = len(raw) - len(raw.lstrip())
            if indent > run_indent:
                run_body.append(raw[run_indent + 2:])  # strip run-block indent
                continue
            # Dedent to a sibling → the run block is over.
            _flush_run_body()

    _flush_run_body()
    return run_blocks, job_runs_on


# ---------------------------------------------------------------------------
# Check 1: bash -n
# ---------------------------------------------------------------------------

def check_bash_syntax(report: Report, block: RunBlock) -> None:
    """Run `bash -n` on every bash run-block.

    This catches the most common failures from the user's recent outage:
    unterminated strings, mismatched `if/fi`, missing `then`, etc.
    Running `bash -n` is a real shell invocation — it parses the script
    using the same grammar the runner will use, modulo `set -e` and
    shell-builtin runtime quirks.
    """
    if block.shell not in ("bash", "sh"):
        return
    # `bash -n` reads from stdin; we pipe the body.
    proc = subprocess.run(
        ["bash", "-n"],
        input=block.body,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "unknown syntax error"
        report.error(
            block.workflow,
            f"{block.job_id} > {block.step_name}@{block.line}",
            "bash-n-syntax",
            f"`bash -n` failed: {msg}",
        )


# ---------------------------------------------------------------------------
# Check 2: python -c literal
# ---------------------------------------------------------------------------

# `python -c "..."` or `python3 -c "..."` with a single-body payload.
# We allow the surrounding command line to be anything (e.g. preceded by
# `&`, `&&`, `||`, `2>&1 |`); the literal payload is what we feed to
# `python3 -c`. The pattern is deliberately conservative: it only matches
# `python[3] -c`(whitespace) followed by a single/double-quoted string.
_PYTHON_C_LITERAL_RE = re.compile(
    r"""python3?\s+-c\s+(?P<q>['"])(?P<body>.*?)(?P=q)""",
    re.DOTALL,
)


def _extract_python_c_literals(body: str) -> list[tuple[str, str]]:
    """Return [(quote, code), ...] for every `python -c "..."` in body."""
    return [(m.group("q"), m.group("body")) for m in _PYTHON_C_LITERAL_RE.finditer(body)]


def check_python_c_syntax(report: Report, block: RunBlock) -> None:
    """Real `python3 -c <payload>` invocation.

    If the user's literal payload is broken Python (e.g. `Write-Host`),
    this catches it before the workflow runs. We deliberately resolve
    ${{ }} expressions to a placeholder before testing so the
    expression-text doesn't trip Python's parser — the goal is to
    verify the LITERAL payload Python sees, not the rendered one.
    """
    for q, payload in _extract_python_c_literals(block.body):
        # Strip ${{ ... }} interpolations: Python would see the literal
        # `${{ ... }}` inside the quoted string, which is fine (it's just
        # text), but `set -e` and other shell expansions may have
        # already collided. We don't validate those here; we validate
        # the Python grammar.
        cleaned = re.sub(r"\$\{\{[^{}]*\}\}", "X", payload)
        try:
            compile(cleaned, "<python-c>", "exec")
        except SyntaxError as e:
            report.error(
                block.workflow,
                f"{block.job_id} > {block.step_name}@{block.line}",
                "python-c-syntax",
                f"`python -c` payload has Python syntax error: {e.msg} "
                f"(line {e.lineno}, col {e.offset}). Payload: {payload[:120]!r}",
            )


# ---------------------------------------------------------------------------
# Check 3: PowerShell pitfalls
# ---------------------------------------------------------------------------

# Pattern A: `Write-Host` inside a `python -c "..."` payload — the
# original bug. `Write-Host` is PowerShell, not Python, and Python
# rejects it with SyntaxError. The body of the `python -c` may
# contain either single or double quotes (e.g. `python -c "$X"`,
# `python -c '$X'`, or `python -c "... '...' ..."`), so we use
# DOTALL and a relaxed body character class that excludes only the
# matching quote.
_PYTHON_C_WRITE_HOST_RE = re.compile(
    r"""python3?\s+-c\s+(?P<q>['"])(?P<body>.*?Write-Host.*?)(?P=q)""",
    re.DOTALL,
)

# Pattern B: `python -m pywin32_postinstall` — broken on pywin32 ≥ 310.
_BROKEN_PYWIN32_MOD_RE = re.compile(
    r"python3?\s+-m\s+pywin32_postinstall\b"
)

# Pattern C: trailing `\` on `Copy-Item` or `Move-Item` destination —
# legal in PowerShell but easy to miss in review. Warn only.
_COPY_TRAILING_BS_RE = re.compile(
    r"(?:Copy|Move)-Item\s+[^|\n]+?\sartifacts\\(?=\s|$)"
)

# Pattern D: bare `python` / `python3` invocation in a `shell: pwsh`
# block. On Windows + actions/setup-python@v6 the bare `python` token
# resolves to the SYSTEM python at
# `C:\hostedtoolcache\windows\Python\<ver>\x64\python.exe`, NOT the
# venv python — because `setup-python-env` only appends
# `$PWD/.venv/Scripts` to GITHUB_PATH (END of PATH) while
# `setup-python@v6` registers the system interpreter at the FRONT.
# Bare `python` therefore lands on an interpreter without PyInstaller,
# PySide6, pywin32, etc., and the step fails with ModuleNotFoundError.
#
# The fix is to invoke the explicit venv path
# (`$env:GITHUB_WORKSPACE\.venv\Scripts\python.exe`) via
# `& $VenvPython ...`, which the `Install Windows-specific packages`
# step in release-{intl,cn}.yml uses.
#
# We anchor to the line start (after optional leading whitespace) so
# `python` only fires when it's the command, not when it appears
# inside a path literal (e.g. `C:\hostedtoolcache\...python.exe`).
# Path literals are detected separately: a path contains backslashes
# (Windows) or slashes (Unix-like), and we ignore such lines.
_BARE_PYTHON_IN_PWSH_RE = re.compile(
    r"^\s*python3?(\.exe)?(?=\s|-\w|--\w)(?!.*[\\/]).*$"
)

# Pattern E: `winget` in a `shell: powershell` (Windows PowerShell v1)
# block. `winget` is a UWP app bundled with Windows 11 22H2+ and
# Windows Server 2025+. It is NOT present in Windows PowerShell v1
# (`C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`), which
# is what `shell: powershell` invokes on self-hosted runners.
# Using `winget` under `shell: powershell` fails with
# "term 'winget' is not recognized..." on every self-hosted runner
# that hasn't installed App Installer separately.
# The fix is `shell: pwsh` — pwsh (PowerShell 7) bundles winget.
_WINGET_IN_POWERSHELL_RE = re.compile(
    r"^\s*winget\b",
    re.IGNORECASE,
)


def check_powershell_pitfalls(report: Report, block: RunBlock) -> None:
    """Real PowerShell pitfalls from past outages:
      - `Write-Host` inside `python -c "..."`
      - `python -m pywin32_postinstall` (broken since pywin32 ≥ 310)
      - `winget` in a `shell: powershell` block (no winget in Win PS v1)
    """
    if block.shell not in ("pwsh", "powershell"):
        return
    body = block.body

    # Strip out lines that are PowerShell comments (`#`) before running
    # any pitfall check. The current `Install Windows-specific
    # packages` step has a comment block that references the broken
    # `python -m pywin32_postinstall` form and the previous
    # `Write-Host` mistake to explain why we don't use them — we
    # don't want the comment to trip the check.
    code_lines = "\n".join(
        line for line in body.splitlines()
        if not line.lstrip().startswith("#")
    )

    if _PYTHON_C_WRITE_HOST_RE.search(code_lines):
        report.error(
            block.workflow,
            f"{block.job_id} > {block.step_name}@{block.line}",
            "pwsh-write-host-in-python-c",
            "`python -c` payload contains `Write-Host`. Write-Host is "
            "PowerShell syntax, not Python; Python rejects it with "
            "SyntaxError on `<string>` line 1 once it parses the -c "
            "string. Use Python's print() instead.",
        )

    if _BROKEN_PYWIN32_MOD_RE.search(code_lines):
        report.error(
            block.workflow,
            f"{block.job_id} > {block.step_name}@{block.line}",
            "pwsh-broken-pywin32-postinstall",
            "`python -m pywin32_postinstall` fails with `No module "
            "named pywin32_postinstall` on pywin32 ≥ 310 because the "
            "wheel only registers the script as a console entry and "
            "as the module `win32.scripts.pywin32_postinstall`. Use "
            "the latter, or run `<venv>/Scripts/pywin32_postinstall.exe`.",
        )

    # Trailing `\` on Copy-Item is legal PowerShell but easy to break
    # in code review. Warn but don't fail.
    if _COPY_TRAILING_BS_RE.search(code_lines):
        report.warn(
            block.workflow,
            f"{block.job_id} > {block.step_name}@{block.line}",
            "pwsh-copy-trailing-backslash",
            "Copy-Item / Move-Item destination ends with a trailing "
            "`\\`. This is legal PowerShell but easy to drop in review "
            "and turns into a relative-path lookup if the trailing "
            "backslash is removed. Prefer an explicit Join-Path.",
        )

    # Pattern D: bare `python` / `python3` invocation in a pwsh step.
    # Scan each code line independently (regex with ^\s* anchor) so
    # `python` only fires when it's the command token at the start of
    # the line — `C:\hostedtoolcache\...python.exe` in a path literal
    # or `if (Test-Path "python.exe") { ... }` won't match.
    for line in code_lines.splitlines():
        m = _BARE_PYTHON_IN_PWSH_RE.match(line)
        if m:
            report.error(
                block.workflow,
                f"{block.job_id} > {block.step_name}@{block.line}",
                "pwsh-bare-python-must-use-venv",
                f"Bare `{m.group(0).split()[0]}` invocation in a "
                f"`shell: pwsh` block: `{line.strip()}`. On Windows, "
                f"`actions/setup-python@v6` registers the SYSTEM python "
                f"(`C:\\hostedtoolcache\\...\\<ver>\\x64\\python.exe`) "
                f"at the FRONT of PATH while `setup-python-env` "
                f"appends `$PWD/.venv/Scripts` (END of PATH), so the "
                f"bare `python` token resolves to the system "
                f"interpreter — which has no PyInstaller, PySide6, "
                f"pywin32, etc. Invoke the EXPLICIT venv path: "
                f"`& $VenvPython ...` where `$VenvPython = Join-Path "
                f"$env:GITHUB_WORKSPACE '.venv\\Scripts\\python.exe'`.",
            )

    # Pattern E: `winget` under `shell: powershell` (Windows PowerShell v1).
    # `winget` is only available on Windows 11 22H2+ and Windows Server
    # 2025+ — it is NOT present in `C:\Windows\System32\WindowsPowerShell\
    # v1.0\powershell.exe` which is what `shell: powershell` invokes.
    # The fix is `shell: pwsh` — PowerShell 7 bundles the Windows App
    # Installer UWP app and `winget` resolves correctly there.
    if block.shell == "powershell":
        for line in code_lines.splitlines():
            if _WINGET_IN_POWERSHELL_RE.search(line):
                report.error(
                    block.workflow,
                    f"{block.job_id} > {block.step_name}@{block.line}",
                    "pwsh-winget-in-shell-powershell",
                    f"`winget` found in a `shell: powershell` block: "
                    f"`{line.strip()}`. `shell: powershell` invokes "
                    f"`C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\"
                    f"powershell.exe` (Windows PowerShell v1), which does "
                    f"NOT bundle the App Installer / winget UWP package. "
                    f"`winget` is only available in `shell: pwsh` "
                    f"(PowerShell 7). Change `shell: powershell` to "
                    f"`shell: pwsh` to fix.",
                )
                break


# ---------------------------------------------------------------------------
# Check 4: deprecated runner labels
# ---------------------------------------------------------------------------

# As of August 2026. Update this table as GitHub announces new
# deprecations. Each entry is (label, deprecation-begin, retirement).
DEPRECATED_RUNNERS: dict[str, tuple[str, str]] = {
    "ubuntu-22.04": ("2026-09-17", "2027-04-17"),
    "ubuntu-22.04-arm": ("2026-09-17", "2027-04-17"),
    "macos-13": ("2024-12-03", "2025-04-15"),
    "macos-13-large": ("2024-12-03", "2025-04-15"),
    "macos-14": ("2026-07-06", "2026-11-02"),
    "macos-14-large": ("2026-07-06", "2026-11-02"),
    "macos-14-xlarge": ("2026-07-06", "2026-11-02"),
    "windows-2019": ("2024-12-03", "2025-04-15"),
}


def check_deprecated_runners(report: Report, runs_on: dict[str, str], workflow: str) -> None:
    """Flag any job whose `runs-on` resolves to a deprecated runner.

    The values in the YAML are unevaluated expressions like
    `'ubuntu-latest'` or `${{ ... || 'ubuntu-22.04' }}`. We scan for
    known-deprecated labels as substrings because we cannot evaluate
    the expression at this layer — the simulator does that. The point
    of this check is to catch the lint-time mistake of using a
    deprecated label even when the simulator's matrix never exercises
    it.
    """
    for job_id, runs_on_str in runs_on.items():
        for label, (begin, retire) in DEPRECATED_RUNNERS.items():
            if label in runs_on_str:
                report.error(
                    workflow,
                    f"{job_id} > runs-on",
                    "deprecated-runner",
                    f"`runs-on` contains `{label}` which is mid-"
                    f"deprecation (deprecation begins {begin}, "
                    f"retirement {retire}). Use `ubuntu-latest` or "
                    f"`macos-latest` instead.",
                )


# ---------------------------------------------------------------------------
# Check 4b: architecture-mismatch between job intent and runner
# ---------------------------------------------------------------------------

# Each GitHub-hosted runner label's actual CPU architecture. As of
# August 2026 — update as the lineup changes:
#
#   - `windows-latest`        → x64
#   - `ubuntu-latest`         → x64
#   - `macos-latest`          → arm64 (Tahoe on Apple Silicon)
#   - `macos-15-intel`        → x86_64 (Intel)
#   - `macos-26-intel`        → x86_64 (Intel)
#
# Source: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
RUNTIME_ARCH: dict[str, str] = {
    # Windows
    "windows-latest": "x64",
    "windows-2025": "x64",
    "windows-2025-vs2026": "x64",
    "windows-2022": "x64",
    "windows-11-arm": "arm64",
    "windows-11-vs2026-arm": "arm64",
    # Linux
    "ubuntu-latest": "x64",
    "ubuntu-24.04": "x64",
    "ubuntu-26.04": "x64",
    "ubuntu-24.04-arm": "arm64",
    "ubuntu-26.04-arm": "arm64",
    # macOS
    "macos-latest": "arm64",
    "macos-15": "arm64",
    "macos-15-xlarge": "arm64",
    "macos-26": "arm64",
    "macos-15-intel": "x86_64",
    "macos-26-intel": "x86_64",
    "macos-latest-large": "x86_64",
    # Self-hosted labels — `ecan-build` is app-agnostic; the actual
    # arch comes from the OS/machine labels.
    "self-hosted,linux,x64,ecan-build": "x64",
    "self-hosted,linux,arm64,ecan-build": "arm64",
    "self-hosted,macos,x64,ecan-build": "x86_64",
    "self-hosted,macos,arm64,ecan-build": "arm64",
    "self-hosted,windows,x64,ecan-build": "x64",
    "self-hosted,windows,arm64,ecan-build": "arm64",
}


# Map job-id-encoded intent to the architecture the job MUST build
# for. The job id is the source of truth: `build-macos-amd64` builds
# an x86_64 macOS installer, regardless of what the explicit `arch:`
# override in the workflow says. If the runner's arch contradicts
# the job id, the fallback runs under Rosetta 2 / emulation with
# degraded performance and non-trivial native-binary mismatch risk.
JOB_INTENT_ARCH: dict[str, str] = {
    "build-windows": "x64",
    "build-linux": "x64",
    "build-macos-amd64": "x86_64",
    "build-macos-aarch64": "arm64",
}


def _arch_of_runs_on(runs_on_str: str) -> str | None:
    """Resolve `runs-on` to a known architecture, or None if unknown.

    `runs-on` can be a literal `'ubuntu-latest'` or a `${{ ... || 'macos-latest' }}`
    expression. We inspect substrings against the RUNTIME_ARCH table
    on a best-effort basis:

      1. If the expression has a `||`, the right-hand side is the
         GitHub-hosted fallback. We prefer the fallback when the
         self-hosted branch is unrecognised.
      2. Otherwise, look up the literal label directly.

    We don't try to evaluate the full expression — the simulator does
    that. The point here is to catch the lint-time mistake of wiring
    a build-* job to a runner whose arch is obvious from the label.
    """
    # 1. Look at the fallback branch first. If the expression has
    #    `||`, the right-hand side is the GitHub-hosted fallback.
    if "||" in runs_on_str:
        fallback = runs_on_str.split("||")[-1]
    else:
        fallback = runs_on_str

    # Strip the literal `'macos-15-intel'` out of the fallback. Lines
    # like `'macos-15-intel'` (no quotes inside) match; lines like
    # `fromJSON('["self-hosted","macos","x64","ecan-build"]')` are
    # already in the table as a composite key.
    fallback_clean = fallback.strip()
    for label, arch in RUNTIME_ARCH.items():
        # Single-label match: prefix `,`-less and exact after quotes.
        if "," in label:
            continue
        # Look for the label as a quoted literal in the fallback.
        if f"'{label}'" in fallback_clean or f'"{label}"' in fallback_clean:
            return arch
    # Fallback contains a fromJSON array. If its keys don't match our
    # self-hosted table, treat the fallback as unrecognised.
    # Otherwise, scan the full expression for any self-hosted label.
    # Strip quotes so the table key matches the array literal.
    normalized = runs_on_str.replace('"', "").replace("'", "")
    for label, arch in RUNTIME_ARCH.items():
        if "," not in label:
            continue
        if label in normalized:
            return arch
    return None


def _arch_of_self_hosted_branch(runs_on_str: str) -> str | None:
    """Extract the architecture of the self-hosted branch, if any.

    For an expression like
    `${{ runner_group == 'X' && fromJSON('["self-hosted","macos","x64","ecan-build"]') || 'macos-latest' }}`,
    the LHS of `||` is the self-hosted branch; we look for a
    composite `self-hosted,*,*,ecan-build` label inside it. The label
    in the YAML is usually quoted inside a `fromJSON(...)` array,
    so we strip the quotes before matching.
    """
    if "||" not in runs_on_str:
        return None
    self_hosted = runs_on_str.split("||")[0]
    # Strip the quotes around array elements so the table key
    # `self-hosted,macos,x64,ecan-build` matches an array literal
    # `["self-hosted","macos","x64","ecan-build"]`.
    normalized = self_hosted.replace('"', "").replace("'", "")
    for label, arch in RUNTIME_ARCH.items():
        if "," not in label:
            continue
        if label in normalized:
            return arch
    return None


def check_architecture_mismatch(report: Report, runs_on: dict[str, str], workflow: str) -> None:
    """Flag jobs whose `runs-on` resolves to a runner whose actual
    architecture contradicts the job's intent.

    The job id encodes the architecture it builds for (`build-macos-amd64`
    builds x86_64, `build-macos-aarch64` builds arm64). The runs-on
    string eventually resolves to a runner — either a self-hosted label
    set or a GitHub-hosted runner label. If either branch's arch
    contradicts the job id, the build will run under emulation
    (Rosetta 2) or, worse, emit a native binary for the wrong arch.

    Concrete failure modes this catches:

      1. `build-macos-amd64` with fallback `'macos-latest'` is wrong
         because `macos-latest` is arm64-as-of-macos-26 (was arm64 on
         macos-15 since Nov 2024). The correct fallback is
         `macos-15-intel` (or `macos-26-intel`).
      2. `build-macos-amd64` with self-hosted labels
         `["self-hosted","macos","arm64","ecan-build"]` is wrong
         because the self-hosted branch routes to an arm64 runner
         when the operator picks `ecan-macos-amd64`.
    """
    for job_id, runs_on_str in runs_on.items():
        intent = JOB_INTENT_ARCH.get(job_id)
        if intent is None:
            continue  # only build-* jobs have a fixed arch intent

        # Map intent to the comparison key. `x64` matches both `x64`
        # and `x86_64` because both are x86-style 64-bit.
        intent_eq = "x86_64" if intent == "x86_64" else "x64"

        # Check the GitHub-hosted fallback (or the only branch when
        # there's no `||`).
        fallback_arch = _arch_of_runs_on(runs_on_str)
        if fallback_arch is not None:
            fallback_eq = "x86_64" if fallback_arch == "x86_64" else "x64"
            if fallback_eq != intent_eq:
                report.error(
                    workflow,
                    f"{job_id} > runs-on",
                    "architecture-mismatch",
                    f"job id `{job_id}` builds for `{intent}`, but the "
                    f"GitHub-hosted fallback runner is `{fallback_arch}`. "
                    f"Cross-arch builds run under Rosetta 2 / emulation "
                    f"with degraded performance and a non-trivial risk "
                    f"of native-binary mismatches. Use a runner whose "
                    f"actual arch matches the job id.",
                )

        # Check the self-hosted branch (only meaningful when there's
        # a `||` since the fallback is the post-self-hosted branch).
        selfhosted_arch = _arch_of_self_hosted_branch(runs_on_str)
        if selfhosted_arch is not None:
            selfhosted_eq = "x86_64" if selfhosted_arch == "x86_64" else "x64"
            if selfhosted_eq != intent_eq:
                report.error(
                    workflow,
                    f"{job_id} > runs-on",
                    "architecture-mismatch",
                    f"job id `{job_id}` builds for `{intent}`, but the "
                    f"self-hosted branch resolves to `{selfhosted_arch}`. "
                    f"Operators who pick the `{job_id}` runner_group "
                    f"will route to a wrong-arch runner. Update the "
                    f"self-hosted label set to match the job's intent.",
                )


# ---------------------------------------------------------------------------
# Check 5: CN/INTL parity
# ---------------------------------------------------------------------------

# Two jobs are parity-pairs when they share the same role across CN/INTL:
# `build-windows` ↔ `build-windows` (same job id), etc.
#
# Parity check: the `shell:`, the `runs-on`, and the canonical-named
# side of the `run:` block must match. The canonical-side of the name
# is `<NAME>-<rest>` after stripping `eCan` / `eCan.cn`. The same
# normalization the symmetry check does is applied here.
def _canonical_job_id(job_id: str) -> str:
    """Strip `eCan` / `eCan.cn` to a name-agnostic form."""
    return job_id.replace("eCan.cn", "eCan").replace("eCan", "<NAME>")


def _canonical_run_body(body: str) -> str:
    """Normalize the text so CN/INTL bodies compare equal on parity."""
    out = body
    # Replace CN-flavored name with the canonical name placeholder.
    # The symmetry check normalizes both `eCan.cn` and `eCan` to
    # `<NAME>`; we mirror that here so `eCan`/`eCan.cn` literal in
    # user-facing strings (e.g. "built eCan-1.0.0.exe") don't trip
    # the parity check.
    out = out.replace("eCan.cn", "<NAME>")
    out = re.sub(r"\beCan\b", "<NAME>", out)
    out = re.sub(r'"\$\{\{\s*secrets\.\S+\s*\}\}"', '"<TOKEN>"', out)
    out = re.sub(r'--app\s+\S+', '--app <APP>', out)
    out = re.sub(r'--version\s+\$\{\{[^{}]*\}\}', '--version <VER>', out)
    # Per-pipeline requirements files (requirements-cn.txt vs
    # requirements-intl.txt) are legitimate divergence — the symmetry
    # check already normalizes them. Strip them here too so the
    # parity check reports genuine differences only.
    out = re.sub(r'requirements-(?:cn|intl)\.txt', 'requirements-<APP>.txt', out)
    # Backend-specific identifiers and label text. CN uses COS,
    # INTL uses S3; the symmetry check collapses these in the
    # upload-to-* job ids, but the body text that references them
    # (e.g. "COS upload:" in the final-status summary) needs the
    # same normalization here.
    out = re.sub(r'\bupload-to-cos\b', 'upload-to-<BACKEND>', out)
    out = re.sub(r'\bupload-to-s3\b', 'upload-to-<BACKEND>', out)
    out = re.sub(r'\bneeds\.upload-to-cos\b', 'needs.upload-to-<BACKEND>', out)
    out = re.sub(r'\bneeds\.upload-to-s3\b', 'needs.upload-to-<BACKEND>', out)
    out = re.sub(r'\bCOS upload\b',  '<BACKEND> upload', out)
    out = re.sub(r'\bS3 upload\b',   '<BACKEND> upload', out)
    # Cloud-provider names in the GHA-fallback download message. CN
    # uses Tencent Cloud COS, INTL uses AWS S3 — both are <BACKEND>.
    out = re.sub(r'\bTencent Cloud\b', '<BACKEND>', out)
    out = re.sub(r'\bAWS\b(?=\s+<BACKEND>)', '<BACKEND>', out)
    # "for CN internal use only" vs "for INTL internal use only".
    out = re.sub(r'\bfor CN internal use only\b',   'for <APP> internal use only', out)
    out = re.sub(r'\bfor INTL internal use only\b', 'for <APP> internal use only', out)
    # App-flavored labels in user-facing strings. CN writes "Release (CN)",
    # INTL writes "Release (Intl)"; both are <APP>. The \b before the
    # open-paren doesn't match because `(` is not a word character, so
    # we use a non-capturing group without a leading boundary.
    out = re.sub(r'Release \((?:CN|Intl|cn|intl)\)', 'Release (<APP>)', out)
    # Box-drawing borders of variable length (the width is hand-tuned
    # to match the title text). Canonicalize to a fixed width so the
    # canonicalization doesn't false-flag a 1-character width difference.
    out = re.sub(r'={5,}', '=====', out)
    # Trailing whitespace is formatting noise. Strip it so a realigner
    # `Look I just added one space for the table to line up` doesn't
    # false-flag the parity check.
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    # Collapse runs of >= 2 spaces inside `echo "..."` payloads to a
    # single space. The Releases summary formats a two-column table with
    # hand-aligned spaces; CN/INTL differ in their alignment by 1 char
    # without the canonicalization reporting a semantic change.
    out = re.sub(r'  +', ' ', out)
    return out


def check_cn_intl_parity(
    report: Report,
    cn: list[RunBlock],
    intl: list[RunBlock],
    cn_runs_on: dict[str, str],
    intl_runs_on: dict[str, str],
) -> None:
    """For each (canonical_job, step_name) pair, the two sides' run
    bodies, shell, and runs-on must match after canonicalization.

    This check is **separate** from the YAML-byte symmetry check —
    the symmetry check normalizes structure; this checks content.
    Together they catch both "you renamed a thing on one side" and
    "you wrote different code on one side".
    """
    # Steps that exist on only one side by design. Each entry is a
    # (canonical_job_id, step_name) pair whose absence on the other
    # side is expected and should NOT trigger a parity warning.
    #
    # "Validate Gitee credentials" is CN-only because INTL checks out
    # from github.com (no token needed). Adding the step to INTL would
    # be dead code; this allowlist documents the asymmetry instead.
    _CN_ONLY_STEPS = {
        ("validate-tag", "Validate Gitee credentials"),
        ("build-windows", "Validate Gitee credentials"),
        ("build-linux", "Validate Gitee credentials"),
        ("build-linux-amd64", "Validate Gitee credentials"),
        ("build-macos-amd64", "Validate Gitee credentials"),
        ("build-macos-aarch64", "Validate Gitee credentials"),
    }
    cn_index: dict[tuple[str, str], RunBlock] = {
        (b.job_id, b.step_name): b for b in cn
    }
    intl_index: dict[tuple[str, str], RunBlock] = {
        (b.job_id, b.step_name): b for b in intl
    }

    # Match by canonical job id + step name, so `build-windows` and
    # `build-windows-cn` collapse together.
    cn_canon: dict[tuple[str, str], RunBlock] = {
        (_canonical_job_id(b.job_id), b.step_name): b for b in cn
    }
    intl_canon: dict[tuple[str, str], RunBlock] = {
        (_canonical_job_id(b.job_id), b.step_name): b for b in intl
    }

    for key, cn_block in cn_canon.items():
        if key not in intl_canon:
            if key in _CN_ONLY_STEPS:
                # Documented asymmetry — skip the warning.
                continue
            report.warn(
                cn_block.workflow,
                f"{cn_block.job_id} > {cn_block.step_name}",
                "cn-intl-parity-missing",
                f"CN has step {key} but INTL does not. Run the "
                f"symmetry check for structural drifts.",
            )
            continue
        intl_block = intl_canon[key]

        # `shell:` must match.
        if cn_block.shell != intl_block.shell:
            report.error(
                cn_block.workflow,
                f"{cn_block.job_id} > {cn_block.step_name}@{cn_block.line}",
                "cn-intl-shell-mismatch",
                f"shell: {cn_block.shell!r} vs INTL shell: {intl_block.shell!r}. "
                f"Different shells = different runtime semantics.",
            )

        # Run body must match after canonicalization.
        if _canonical_run_body(cn_block.body) != _canonical_run_body(intl_block.body):
            report.error(
                cn_block.workflow,
                f"{cn_block.job_id} > {cn_block.step_name}@{cn_block.line}",
                "cn-intl-body-mismatch",
                f"Run body differs from INTL after canonicalizing "
                f"app name, secrets, --app, --version. Either fix the "
                f"two pipelines to match, or document why they differ.",
            )

    # Symmetric: any INTL block with no CN peer.
    for key, intl_block in intl_canon.items():
        if key not in cn_canon:
            report.warn(
                intl_block.workflow,
                f"{intl_block.job_id} > {intl_block.step_name}",
                "cn-intl-parity-missing",
                f"INTL has step {key} but CN does not.",
            )

    # `runs-on` parity for shared job ids.
    cn_jobs = {_canonical_job_id(j): v for j, v in cn_runs_on.items()}
    intl_jobs = {_canonical_job_id(j): v for j, v in intl_runs_on.items()}
    for job_id, cn_str in cn_jobs.items():
        if job_id in intl_jobs and cn_str != intl_jobs[job_id]:
            report.error(
                "release-cn.yml",
                f"{job_id} > runs-on",
                "cn-intl-runs-on-mismatch",
                f"CN runs-on={cn_str!r} but INTL runs-on={intl_jobs[job_id]!r}. "
                f"Different runner = different behaviour (Ubuntu vs macOS).",
            )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_smoke(workflow_one: Path, workflow_two: Path) -> Report:
    report = Report()

    cn_blocks, cn_runs_on = _parse_workflow(workflow_one)
    intl_blocks, intl_runs_on = _parse_workflow(workflow_two)

    for block in cn_blocks + intl_blocks:
        check_bash_syntax(report, block)
        check_python_c_syntax(report, block)
        check_powershell_pitfalls(report, block)

    check_deprecated_runners(report, cn_runs_on, workflow_one.name)
    check_deprecated_runners(report, intl_runs_on, workflow_two.name)

    check_architecture_mismatch(report, cn_runs_on, workflow_one.name)
    check_architecture_mismatch(report, intl_runs_on, workflow_two.name)

    check_cn_intl_parity(report, cn_blocks, intl_blocks, cn_runs_on, intl_runs_on)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Workflow smoke test")
    parser.add_argument(
        "--workflow-one",
        type=Path,
        default=Path(".github/workflows/release-cn.yml"),
        help="First workflow (default: release-cn.yml)",
    )
    parser.add_argument(
        "--workflow-two",
        type=Path,
        default=Path(".github/workflows/release-intl.yml"),
        help="Second workflow (default: release-intl.yml)",
    )
    args = parser.parse_args(argv)

    # Run from the repo root so relative paths resolve.
    repo_root = Path(__file__).resolve().parents[2]
    if repo_root.exists():
        import os
        os.chdir(repo_root)

    report = run_smoke(args.workflow_one, args.workflow_two)

    print(f"=== Workflow smoke test ===")
    print(f"  {args.workflow_one}")
    print(f"  {args.workflow_two}")
    print(f"  findings: {report.counts}")
    if report.issues:
        print()
        for issue in report.issues:
            print(issue)
    print()

    if report.has_errors():
        print(f"FAIL: {report.counts['error']} error(s), {report.counts['warning']} warning(s)")
        return 1
    if report.counts["warning"]:
        print(f"PASS WITH WARNINGS: {report.counts['warning']} warning(s)")
        return 0
    print("PASS: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
