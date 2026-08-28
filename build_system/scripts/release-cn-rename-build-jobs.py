#!/usr/bin/env python3
"""
Rename cn build jobs (and their references) so cn matches intl structurally.

Specifically:
  build-windows-cn         → build-windows
  build-macos-amd64-cn     → build-macos-amd64
  build-macos-aarch64-cn   → build-macos-aarch64
  build-linux-cn           → build-linux

DOES NOT touch:
  - requirements-cn.txt  (kept — real filename)
  - release-cn-…         (kept — concurrency group)
  - ECAN_APP_NAME / DIST_APP env values (cn keeps eCan.cn; the cn/intl
    symmetry check normalises both to `<NAME>` so the per-app branding
    value does not break the symmetry contract)
  - shared-cos-*.yml references (that's backend-specific and intentional)

We only touch occurrences of `build-{platform}-cn` as a job-id or job-id
reference. The pattern `(\\W|^)build-(windows|macos-amd64|macos-aarch64|linux)-cn(\\W|$)`
gives us a tight anchor.
"""
import re
from pathlib import Path

REPO = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")
FILE = REPO / ".github/workflows/release-cn.yml"

text = FILE.read_text()


def rename(match: re.Match[str]) -> str:
    pre, jid, post = match.group(1), match.group(2), match.group(3)
    return f"{pre}{jid}{post}"


out = re.sub(
    r"(\W|^)(build-(?:windows|macos-amd64|macos-aarch64|linux))-cn(\W|$)",
    rename, text,
)

# Final-style display names: drop trailing ` CN`.
# 'Build Windows amd64 CN'  →  'Build Windows amd64'
out = re.sub(
    r"(name:\s*Build Windows amd64) CN\b",
    r"\1",
    out,
)
out = re.sub(
    r"(name:\s*Build macOS amd64) CN\b",
    r"\1",
    out,
)
out = re.sub(
    r"(name:\s*Build macOS aarch64) CN\b",
    r"\1",
    out,
)
out = re.sub(
    r"(name:\s*Build Linux amd64) CN\b",
    r"\1",
    out,
)
out = re.sub(
    r"(name:\s*Generate Appcast \(all platforms × archs\)) CN\b",
    r"\1",
    out,
)

# NOTE: ECAN_APP_NAME / DIST_APP env values are intentionally left as
# per-app branding (eCan for intl, eCan.cn for cn). The sym-check
# (release-pipeline-symmetry-check.py Step 1) collapses both to `<NAME>`
# so this difference does not break the symmetry contract. Workflow
# Prepare-artifacts paths now use `${{ env.DIST_APP }}-…` so they
# resolve to the correct per-app filename on each pipeline.

# Pipeline name in the `name:` header — keep `Release (CN)` (it's UI display).
# Pipeline concurrency group — keep `release-cn-…` (it's the unique key).

# Generic " CN" suffix outside of quoted display names.  Only match
# `   CN` (whitespace + literal CN) at the END of a YAML scalar value.
# (Conservative: keep pipeline name, concurrency group, and quoted env values.)

FILE.write_text(out)
print(f"OK: renamed cn build jobs in {FILE}")
print(f"  ({len(text)} → {len(out)} chars)")
