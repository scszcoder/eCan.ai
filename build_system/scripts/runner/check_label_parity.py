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
    """
    out: Dict[str, Tuple[Tuple[str, ...], int]] = {}

    rg_re = re.compile(
        r"^\s*(?:-\s+)?runner_group:\s*['\"]?([\w-]+)['\"]?\s*$",
        re.MULTILINE,
    )
    runner_re = re.compile(
        r"^\s*runner:\s*(\[[^\]]*\])\s*$",
        re.MULTILINE,
    )

    for m in rg_re.finditer(text):
        rg = m.group(1)
        if not rg.startswith("ecan-"):
            continue
        rg_line = text.count("\n", 0, m.start()) + 1
        # Search for the next `runner: [...]` list within ~10 lines.
        search_from = m.end()
        sub = text[search_from:search_from + 800]
        rm = runner_re.search(sub)
        if not rm:
            continue
        labels = _parse_list_literal(rm.group(1))
        if labels is None:
            continue
        out[rg] = (labels, rg_line)

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

    for os_val, arch_val, _ln in _parse_shell_outer_branches(text):
        resolved = (template
                    .replace("${PLATFORM_OS}",   os_val)
                    .replace("${PLATFORM_ARCH}", arch_val))
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


def _parse_shell_outer_branches(text: str) -> list[Tuple[str, str, int]]:
    """
    Walk the outer `case "$OS_RAW" in ... esac` block and return every
    (os_val, arch_val, line_no) combination the script can register.
    """
    cm = _OUTER_CASE.search(text)
    if not cm:
        return []
    body = cm.group(1)

    out: list[Tuple[str, str, int]] = []
    for bm in _OUTER_BRANCH.finditer(body):
        head = bm.group("head")
        bbody = bm.group("body")
        if head not in ("Linux", "Darwin"):
            continue
        os_match = _OS_ASSIGN.search(bbody)
        if not os_match:
            continue
        os_val = os_match.group("val")
        # Limit arch matches to the inner `case "$ARCH_RAW" in` block
        # so we don't accidentally pick up an unrelated PLATFORM_ARCH.
        inner = bbody.split("\nesac", 1)[0]
        for am in _ARCH_ASSIGN.finditer(inner):
            arch_val = am.group("val")
            out.append((os_val, arch_val, 0))

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

README_ROW_RE = re.compile(
    r"""
    ^\s*\|\s*[^|]*\|\s*[^|]*\|\s*
    `(?P<rg>ecan-[a-z0-9-]+)`\s*\|\s*
    `(?P<labels>[^`]+)`\s*\|
    \s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


def extract_from_readme(text: str) -> Dict[str, Tuple[Tuple[str, ...], int]]:
    out: Dict[str, Tuple[Tuple[str, ...], int]] = {}
    for m in README_ROW_RE.finditer(text):
        rg = m.group("rg")
        labels = tuple(p.strip() for p in m.group("labels").split(","))
        line_no = text.count("\n", 0, m.start()) + 1
        out[rg] = (labels, line_no)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runner_group_for(os_part: str, arch_part: str) -> Optional[str]:
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
    release_yml = repo_root / ".github" / "workflows" / "release.yml"
    sh_script   = repo_root / "build_system" / "scripts" / "runner" / "register_runner.sh"
    ps_script   = repo_root / "build_system" / "scripts" / "runner" / "register_runner.ps1"
    readme      = repo_root / "build_system" / "scripts" / "runner" / "README.md"

    for p in (release_yml, sh_script, ps_script, readme):
        if not p.exists():
            print(f"ERROR: required file missing: {p}", file=sys.stderr)
            return 1

    sources: Dict[str, Tuple[Dict[str, Tuple[Tuple[str, ...], int]], Path]] = {
        "release.yml":         (extract_from_release_yml(release_yml.read_text()), release_yml),
        "register_runner.sh":  (extract_from_shell(sh_script.read_text()),        sh_script),
        "register_runner.ps1": (extract_from_powershell(ps_script.read_text()),   ps_script),
        "runner/README.md":    (extract_from_readme(readme.read_text()),          readme),
    }

    canonical_rgs = set(sources["release.yml"][0].keys())

    # Summary table.
    print("Label parity summary:")
    print("-" * 100)
    header = f"  {'runner_group':<22}{'release.yml':<26}{'register.sh':<24}{'register.ps1':<24}README.md"
    print(header)
    for rg in sorted(canonical_rgs):
        cells = []
        for name in ("release.yml", "register_runner.sh", "register_runner.ps1", "runner/README.md"):
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
        canonical_labels = normalised["release.yml"].get(rg)
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
                    f"  - {rg}: label mismatch between release.yml "
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
                    str(sources["release.yml"][1].relative_to(repo_root)),
                    line_for["release.yml"].get(rg, 1),
                    f"{rg}: workflow declares {list(canonical_labels)} but "
                    f"{other_name} declares {list(other_labels)}",
                )

    if failures:
        print("\nFAIL: label parity violated.", file=sys.stderr)
        for line in failures:
            print(line, file=sys.stderr)
        print(
            "\nFix: ensure every source lists identical labels for each "
            "ecan-* runner_group. The canonical reference is release.yml; "
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