#!/usr/bin/env python3
"""
check_label_parity.py
=====================

Cross-check that all sources of truth agree on the label sets registered
for each ecan-* self-hosted runner. Emits GitHub Actions
`::error file=...,line=...::...` annotations when run inside $GITHUB_ACTIONS
so failures surface as inline PR review comments.

Sources of truth and their natural coverage:
    .github/workflows/release.yml                ALL ecan-* (matrix source-of-truth)
    build_system/scripts/runner/register_runner.sh   linux + macos (Darwin)
    build_system/scripts/runner/register_runner.ps1  windows only
    build_system/scripts/runner/README.md            ALL ecan-* (documentation)

The script treats release.yml as the canonical set of runner_groups, then
for each runner_group verifies that every source capable of expressing it
agrees on the label tuple. Sources that legitimately can't express a
runner_group (e.g. ps1 can't register macOS) are skipped.

Usage:
    python3 build_system/scripts/runner/check_label_parity.py \\
        [--repo-root <dir>]

Read-only, dependency-free (Python 3.8+ stdlib).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# runner_group -> (os-segment-in-label, arch-segment-in-label)
PLATFORM_KEYS: Dict[str, Tuple[str, str]] = {
    "ecan-linux-amd64":   ("linux",  "x64"),
    "ecan-linux-arm64":   ("linux",  "arm64"),
    "ecan-windows-amd64": ("windows", "x64"),
    "ecan-windows-arm64": ("windows", "arm64"),
    "ecan-macos-amd64":   ("macos",  "x64"),
    "ecan-macos-arm64":   ("macos",  "arm64"),
}

# Which scripts are physically able to register which OS family.
SCRIPT_OS_SUPPORT = {
    "register_runner.sh":  {"linux", "macos"},
    "register_runner.ps1": {"windows"},
}


# ---------------------------------------------------------------------------
# GitHub Actions annotation
# ---------------------------------------------------------------------------

def gh_annot(level: str, rel_path: str, line: int, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    safe_msg = message.replace("\r", " ").replace("\n", " ")
    if len(safe_msg) > 4096:
        safe_msg = safe_msg[:4093] + "..."
    print(f"::{level} file={rel_path},line={line}::{safe_msg}", flush=True)


# ---------------------------------------------------------------------------
# release.yml extractor
# ---------------------------------------------------------------------------

def extract_from_release_yml(text: str) -> Dict[str, Tuple[Tuple[str, ...], int]]:
    """
    Return {runner_group: (label_tuple, source_line_number)}.
    Only ecan-* runner_groups are captured.

    After dropping the build-job matrix (refactor 8b2cfa20) the workflow no
    longer carries a `strategy.matrix.include` block with `runner_group:`
    rows. The runner label list now lives inside the `runs-on:` conditional
    expression:

        runs-on: ${{ runner_group == '<ecan-...>' &&
                    fromJSON('["self-hosted","<os>","<arch>","ecan-build"]') ||
                    '<gh-fallback>' }}

    So we parse those `fromJSON('[...]')` literals, group them by the
    runner_group they gate on, and emit one canonical entry per ecan-*
    runner_group. The four-element label list parses cleanly with the
    existing `_parse_list_literal` helper.
    """
    out: Dict[str, Tuple[Tuple[str, ...], int]] = {}

    # Match `runner_group == 'ecan-<os>-<arch>' && fromJSON('[<labels>]')`
    rg_re = re.compile(
        r"runner_group\s*==\s*'(?P<rg>ecan-[\w-]+)'\s*&&\s*"
        r"fromJSON\('(?P<labels>\[[^\]]+\])'\)",
    )

    for m in rg_re.finditer(text):
        rg = m.group("rg")
        labels = _parse_list_literal(m.group("labels"))
        if labels is None:
            # Treat unparseable / wrong-arity runners as a hard failure so
            # the operator sees the drift instead of silently passing.
            raise SystemExit(
                f"check_label_parity.py: malformed fromJSON('...') label list "
                f"for {rg!r} in release.yml — expected 4-element list literal"
            )
        line_no = text.count("\n", 0, m.start()) + 1
        out[rg] = (labels, line_no)

    return out


def _parse_list_literal(s: str) -> Optional[Tuple[str, ...]]:
    s = s.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    inner = s[1:-1]
    parts: list[str] = []
    for raw in inner.split(","):
        p = raw.strip().strip("'\"")
        if p:
            parts.append(p)
    if len(parts) != 4:
        return None
    return tuple(parts)


# ---------------------------------------------------------------------------
# Shell script extractor (register_runner.sh)
# ---------------------------------------------------------------------------

SH_LABEL_LINE_RE = re.compile(
    r'^\s*LABELS\s*=\s*"(?P<template>[^"]+)"\s*$',
    re.MULTILINE,
)


def extract_from_shell(text: str) -> Dict[str, Tuple[Tuple[str, ...], int]]:
    """
    Return {runner_group: (resolved_label_tuple, source_line)}.

    Resolution: parse the outer `case "$OS_RAW" in` block. For each OS
    branch, take the PLATFORM_OS assignment + every PLATFORM_ARCH
    assignment inside the inner `case "$ARCH_RAW" in` block. Each
    (OS, ARCH) pair becomes a runner_group.
    """
    out: Dict[str, Tuple[Tuple[str, ...], int]] = {}

    m = SH_LABEL_LINE_RE.search(text)
    if not m:
        return out
    template = m.group("template")
    labels_line = text.count("\n", 0, m.start()) + 1

    for os_val, arch_val, branch_vars in _parse_shell_outer_branches(text):
        resolved = template
        # Substitute ${VAR} for every captured variable in this branch.
        # Apply longest-first so that, e.g., PLATFORM_OS is replaced
        # before PLATFORM_ (which would otherwise match the prefix).
        for name in sorted(branch_vars, key=len, reverse=True):
            resolved = resolved.replace("${" + name + "}", branch_vars[name])
        labels = tuple(p.strip() for p in resolved.split(","))
        rg = _runner_group_for(os_val, arch_val)
        if rg is not None:
            out[rg] = (labels, labels_line)

    # Annotations on the shell script should always point at the LABELS
    # line — that's where the operator fixes it. But we don't know which
    # (os, arch) pair is broken until check() runs, so we stash the
    # LABELS line on every key the shell produces (and, if the script
    # produces zero keys for an OS family, line 1 as a fallback).

    return out


# Outer case block: column-0 `case` to column-0 `esac`.
_OUTER_CASE = re.compile(
    r'^case\s+"\$OS_RAW"\s+in(.*?)^esac',
    re.MULTILINE | re.DOTALL,
)
# Each outer branch head (e.g. `    Linux)`) up to its outer `;;`.
_OUTER_BRANCH = re.compile(
    r'(?:\A|\n)\s*(?P<head>Linux|Darwin|Windows|\*)\)\s*\n(?P<body>.*?)(?=\n[ ]{0,8};;)',
    re.DOTALL,
)
_OS_ASSIGN = re.compile(r'PLATFORM_OS\s*=\s*"(?P<val>[^"]+)"')
_ARCH_ASSIGN = re.compile(r'PLATFORM_ARCH\s*=\s*"(?P<val>[^"]+)"')
# Captures any UPPERCASE_VAR="value" assignment, used to populate the
# vars dict for shell template substitution.
_GENERIC_ASSIGN = re.compile(r'(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*"(?P<val>[^"]+)"')


def _parse_shell_outer_branches(text: str) -> list[Tuple[str, str, Dict[str, str]]]:
    """
    Walk the outer `case "$OS_RAW" in ... esac` block. For each OS
    branch:

      1. Collect outer-branch-level assignments (PLATFORM_OS=..., LABEL_OS=...)
         once.
      2. Walk the inner `case "$ARCH_RAW" in ... esac` and for each
         inner branch pick up the PLATFORM_ARCH=... assignment on that
         branch's line.

    Then yield (os_val, arch_val, branch_vars) for each (os, arch)
    combination the script can register.
    """
    cm = _OUTER_CASE.search(text)
    if not cm:
        return []
    body = cm.group(1)

    out: list[Tuple[str, str, Dict[str, str]]] = []
    for bm in _OUTER_BRANCH.finditer(body):
        head = bm.group("head")
        bbody = bm.group("body")
        if head not in ("Linux", "Darwin"):
            continue

        # Outer-branch level assignments (PLATFORM_OS, LABEL_OS, etc.).
        # We only capture the FIRST occurrence of each variable name,
        # which is the first line of the branch body in practice.
        outer_vars: Dict[str, str] = {}
        for em in _GENERIC_ASSIGN.finditer(bbody):
            # Only take assignments that appear BEFORE the inner
            # `case "$ARCH_RAW" in` block, so we don't accidentally
            # pick up PLATFORM_ARCH or other arch-branch-local vars.
            header_end = bbody.find('case "$ARCH_RAW"')
            if header_end == -1 or em.start() < header_end:
                if em.group("name") not in outer_vars:
                    outer_vars[em.group("name")] = em.group("val")

        os_val = outer_vars.get("PLATFORM_OS")
        if os_val is None:
            continue

        # Inner case statement body. Split at the inner `esac`.
        inner = bbody.split("\nesac", 1)[0]
        for am in _ARCH_ASSIGN.finditer(inner):
            arch_val = am.group("val")
            branch_vars = dict(outer_vars)
            branch_vars["PLATFORM_ARCH"] = arch_val
            out.append((os_val, arch_val, branch_vars))

    return out


# ---------------------------------------------------------------------------
# PowerShell script extractor (register_runner.ps1)
# ---------------------------------------------------------------------------

PS_LABEL_LINE_RE = re.compile(
    r'^\s*\$labels\s*=\s*"(?P<template>[^"]+)"\s*$',
    re.MULTILINE,
)
PS_ARCH_ASSIGN = re.compile(
    r'\$arch\s*=\s*"(?P<val>[^"]+)"',
)


def extract_from_powershell(text: str) -> Dict[str, Tuple[Tuple[str, ...], int]]:
    """
    Return {runner_group: (label_tuple, line_of_labels_template)}.

    The ps1 script handles Windows only. We resolve every `$arch` value
    it can set (one per `case` branch) and substitute into the
    `$labels = "..."` template.
    """
    out: Dict[str, Tuple[Tuple[str, ...], int]] = {}

    m = PS_LABEL_LINE_RE.search(text)
    if not m:
        return out

    template = m.group("template")
    template_line = text.count("\n", 0, m.start()) + 1

    for am in PS_ARCH_ASSIGN.finditer(text):
        resolved = template.replace("$arch", am.group("val"))
        labels = tuple(p.strip() for p in resolved.split(","))
        rg = _runner_group_for("windows", am.group("val"))
        if rg is not None:
            out[rg] = (labels, template_line)

    return out


# ---------------------------------------------------------------------------
# README.md table extractor
# ---------------------------------------------------------------------------

# Two layouts seen across README versions. Layout A (current): platform |
# label 4-tuple | runner_group. Layout B (legacy): platform | runner_group
# | label 4-tuple. We accept both, picking up whichever column carries the
# label list and the runner_group id respectively.
README_TABLE_ROW_A = re.compile(
    r"""
    ^\s*\|\s*[^|]*\|\s*
    `(?P<labels>[^`]+)`\s*\|\s*
    `(?P<rg>ecan-[a-z0-9-]+)`\s*\|
    """,
    re.VERBOSE | re.MULTILINE,
)
README_TABLE_ROW_B = re.compile(
    r"""
    ^\s*\|\s*[^|]*\|\s*[^|]*\|\s*
    `(?P<rg>ecan-[a-z0-9-]+)`\s*\|\s*
    `(?P<labels>[^`]+)`\s*\|
    """,
    re.VERBOSE | re.MULTILINE,
)


def extract_from_readme(text: str) -> Dict[str, Tuple[Tuple[str, ...], int]]:
    """
    Locate the runner_group → label-tuple mapping declared in README.md.
    Tolerate either of the two column orderings used historically by the
    file (see README_TABLE_ROW_A / _B). Rows are matched line-by-line so
    "Notes" / "(deprecated)" suffixes in trailing columns never bleed
    into the captured groups.
    """
    out: Dict[str, Tuple[Tuple[str, ...], int]] = {}
    # Layout A and B can both legitimately appear in the same file
    # (e.g. legacy docs alongside the new table). Try A first; fall back
    # to B for any row A didn't capture.
    captured_lines: set[int] = set()
    for pattern in (README_TABLE_ROW_A, README_TABLE_ROW_B):
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            if line_no in captured_lines:
                continue
            captured_lines.add(line_no)
            rg = m.group("rg")
            labels = tuple(p.strip() for p in m.group("labels").split(","))
            out[rg] = (labels, line_no)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runner_group_for(os_part: str, arch_part: str) -> Optional[str]:
    # GitHub's tarball uses `osx` for macOS while the workflow matrix
    # uses `macos`. Normalise so a single (os, arch) lookup works for
    # either naming.
    aliases = {"osx": "macos"}
    os_part = aliases.get(os_part, os_part)
    for rg, (o, a) in PLATFORM_KEYS.items():
        if o == os_part and a == arch_part:
            return rg
    return None


def _normalise(d: Dict[str, Tuple[Tuple[str, ...], int]]) -> Dict[str, Tuple[str, ...]]:
    out: Dict[str, Tuple[str, ...]] = {}
    for k, (v, _ln) in d.items():
        out[k] = tuple(s.lower().strip() for s in v)
    return out


def _lines(d: Dict[str, Tuple[Tuple[str, ...], int]]) -> Dict[str, int]:
    return {k: ln for k, (_v, ln) in d.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def check(repo_root: Path) -> int:
    # The set of pipeline workflow files that declare `ecan-*` self-hosted
    # runner labels. Each one is treated as a canonical source — every
    # runner_group appearing in any of these flows must be agreed on by
    # the operator-facing scripts and the README.
    pipeline_files = [
        repo_root / ".github" / "workflows" / "release-intl.yml",
        repo_root / ".github" / "workflows" / "release-cn.yml",
    ]
    sh_script   = repo_root / "build_system" / "scripts" / "runner" / "register_runner.sh"
    ps_script   = repo_root / "build_system" / "scripts" / "runner" / "register_runner.ps1"
    readme      = repo_root / "build_system" / "scripts" / "runner" / "README.md"

    for p in (*pipeline_files, sh_script, ps_script, readme):
        if not p.exists():
            print(f"ERROR: required file missing: {p}", file=sys.stderr)
            return 1

    # Merge canonical labels across both pipeline files. The two pipelines
    # (intl / cn) declare an identical set of `ecan-*` runner_groups — if
    # they ever diverge, treat it as a hard error.
    canonical_per_file = [
        extract_from_release_yml(p.read_text()) for p in pipeline_files
    ]
    canonical_dicts = [d for d in canonical_per_file]  # rename for readability
    canonical: Dict[str, Tuple[Tuple[str, ...], int]] = {}
    for d in canonical_dicts:
        for rg, val in d.items():
            if rg in canonical and canonical[rg][0] != val[0]:
                print(
                    f"ERROR: runner_group {rg!r} declared inconsistently across "
                    f"{pipeline_files[0].name} and {pipeline_files[1].name}: "
                    f"{canonical[rg][0]} vs {val[0]}",
                    file=sys.stderr,
                )
                return 1
            canonical[rg] = val

    sources: Dict[str, Tuple[Dict[str, Tuple[Tuple[str, ...], int]], Path]] = {
        "release-intl.yml":      (canonical_per_file[0], pipeline_files[0]),
        "register_runner.sh":    (extract_from_shell(sh_script.read_text()),       sh_script),
        "register_runner.ps1":   (extract_from_powershell(ps_script.read_text()),  ps_script),
        "runner/README.md":      (extract_from_readme(readme.read_text()),         readme),
    }

    # Mute the unused-variable warning for canonical_dicts while keeping it
    # as a documentation aid above.
    _ = canonical_dicts

    # The release-intl.yml dict is the canonical reference because
    # release-intl.yml is the file operators most often touch. release-cn.yml
    # is required to declare an identical set; we already verified that on
    # input (the divergence-guard above). So either canonical dict is
    # equivalent for downstream checks.
    canonical_rgs = set(sources["release-intl.yml"][0].keys())

    # Summary table.
    print("Label parity summary:")
    print("-" * 100)
    header = f"  {'runner_group':<22}{'release-intl.yml':<26}{'register.sh':<24}{'register.ps1':<24}README.md"
    print(header)
    for rg in sorted(canonical_rgs):
        cells = []
        for name in ("release-intl.yml", "register_runner.sh", "register_runner.ps1", "runner/README.md"):
            d = sources[name][0]
            v = d.get(rg)
            cells.append(_fmt(v))
        print(f"  {rg:<22}{cells[0]:<26}{cells[1]:<24}{cells[2]:<24}{cells[3]}")
    print("-" * 100)

    failures: list[str] = []
    normalised: Dict[str, Dict[str, Tuple[str, ...]]] = {
        name: _normalise(d) for name, (d, _p) in sources.items()
    }
    line_for: Dict[str, Dict[str, int]] = {
        name: _lines(d) for name, (d, _p) in sources.items()
    }

    for rg in sorted(canonical_rgs):
        canonical_labels = normalised["release-intl.yml"].get(rg)
        if canonical_labels is None:
            continue

        os_seg = PLATFORM_KEYS[rg][0]
        expected_others: list[Tuple[str, Path]] = []
        if os_seg in SCRIPT_OS_SUPPORT["register_runner.sh"]:
            expected_others.append(("register_runner.sh", sources["register_runner.sh"][1]))
        if os_seg in SCRIPT_OS_SUPPORT["register_runner.ps1"]:
            expected_others.append(("register_runner.ps1", sources["register_runner.ps1"][1]))
        expected_others.append(("runner/README.md", sources["runner/README.md"][1]))

        for other_name, other_path in expected_others:
            other_labels = normalised[other_name].get(rg)
            if other_labels is None:
                failures.append(
                    f"  - {rg}: {other_name} has no entry for this runner_group "
                    f"(expected {list(canonical_labels)})"
                )
                gh_annot(
                    "error",
                    str(other_path.relative_to(repo_root)),
                    line_for[other_name].get(rg, 1),
                    f"{rg}: missing label entry (workflow expects {list(canonical_labels)})",
                )
                continue
            if other_labels != canonical_labels:
                failures.append(
                    f"  - {rg}: label mismatch between release-intl.yml "
                    f"{list(canonical_labels)} and {other_name} {list(other_labels)}"
                )
                gh_annot(
                    "error",
                    str(other_path.relative_to(repo_root)),
                    line_for[other_name].get(rg, 1),
                    f"{rg}: labels {list(other_labels)} do not match workflow "
                    f"{list(canonical_labels)}",
                )
                gh_annot(
                    "error",
                    str(sources["release-intl.yml"][1].relative_to(repo_root)),
                    line_for["release-intl.yml"].get(rg, 1),
                    f"{rg}: workflow declares {list(canonical_labels)} but "
                    f"{other_name} declares {list(other_labels)}",
                )

    if failures:
        print("\nFAIL: label parity violated.", file=sys.stderr)
        for line in failures:
            print(line, file=sys.stderr)
        print(
            "\nFix: ensure every source lists identical labels for each "
            "ecan-* runner_group. The canonical reference is release-intl.yml; "
            "update other sources to match.",
            file=sys.stderr,
        )
        return 1

    print("OK: all four sources agree on every ecan-* runner_group label set.")
    return 0


def _fmt(present: Optional[Tuple[Tuple[str, ...], int]]) -> str:
    if not present:
        return "<missing>"
    return ",".join(present[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--repo-root",
        default=os.environ.get("GITHUB_WORKSPACE", "."),
        help="Path to the eCan.ai repo root (default: GITHUB_WORKSPACE or cwd).",
    )
    args = parser.parse_args()
    return check(Path(args.repo_root).resolve())


if __name__ == "__main__":
    sys.exit(main())