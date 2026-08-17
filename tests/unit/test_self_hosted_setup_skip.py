"""
Contract tests for the self-hosted vs GitHub-hosted environment-setup
optimisations.

Background: eCan.ai's release pipelines (release-intl.yml, release-cn.yml)
run on two classes of runners:

  - GitHub-hosted windows-latest / ubuntu-latest / macos-latest — every
    job gets a fresh VM, so system-level installs (Inno Setup, Node.js)
    and project-level caches (.venv, node_modules) must be rebuilt from
    scratch.
  - Self-hosted runners labelled `self-hosted,windows,x64,ecan-build`
    (and the linux/macos variants) — the OS image is persistent across
    jobs, but `$GITHUB_WORKSPACE` is still a fresh per-job directory
    under `_work/`, so the *project* workspace contents are not
    preserved between jobs.

Implications we encode in tests:

  1. The `Install Inno Setup` step must probe the canonical
     `${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe` path and skip
     the download/install when ISCC.exe is already there. The
     self-hosted runner ships with Inno Setup pre-installed (set up
     by the operator's first-run script); we must not waste 5MB +
     60s re-downloading it on every job.

  2. The `setup-node-env` composite action must probe for a system
     Node.js and skip the `actions/setup-node@v6` download when one
     is already on PATH.

  3. The `setup-wabaileys-bridge` composite action must probe for a
     system Node.js and skip the `actions/setup-node@v6` download
     when one is already on PATH.

  4. `actions/cache@v5` steps (`Cache Node.js dependencies`,
     `setup-playwright` browser cache, `setup-python-env` venv cache,
     `setup-wabaileys-bridge` npm cache) must be gated on
     `startsWith(runner.name, 'GitHub Actions')` so the cache lookup
     round-trip is skipped on self-hosted (where the per-job workspace
     makes the cache always miss anyway).

These tests are read-only static checks on the YAML / action.yml files;
they don't require a Windows host or any runner.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INTL = REPO / ".github/workflows/release-intl.yml"
CN = REPO / ".github/workflows/release-cn.yml"
SETUP_NODE_ENV = REPO / ".github/actions/setup-node-env/action.yml"
SETUP_WABA = REPO / ".github/actions/setup-wabaileys-bridge/action.yml"
SETUP_PLAYWRIGHT = REPO / ".github/actions/setup-playwright/action.yml"
SETUP_PYTHON_ENV = REPO / ".github/actions/setup-python-env/action.yml"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Inno Setup — must probe + skip when ISCC.exe already exists.
# ---------------------------------------------------------------------------

def _inno_block(text: str) -> str:
    """Return the body of the `Install Inno Setup` step."""
    m = re.search(
        r"- name: Install Inno Setup.*?(?=\n      - name:|\n  [a-z]|\Z)",
        text,
        flags=re.DOTALL,
    )
    if not m:
        return ""
    return m.group(0)


@pytest.mark.parametrize("workflow", [INTL, CN], ids=["intl", "cn"])
def test_inno_setup_probes_existing_iscc(workflow: Path):
    """Both release pipelines must probe for ISCC.exe before downloading."""
    body = _inno_block(_read(workflow))
    assert body, f"{workflow.name}: no Install Inno Setup step found"
    # The probe is the canonical path + a Test-Path check.
    assert 'Test-Path $innoIscc' in body, (
        f"{workflow.name}: Install Inno Setup must call `Test-Path $innoIscc` "
        "before downloading. Without this probe, self-hosted runners with "
        "Inno Setup pre-installed still pay the 5MB download + 60s Inno "
        "installer bootstrap on every job."
    )


@pytest.mark.parametrize("workflow", [INTL, CN], ids=["intl", "cn"])
def test_inno_setup_early_exit_on_hit(workflow: Path):
    """When ISCC.exe exists and the probe succeeds, the step must exit 0
    before the download block."""
    body = _inno_block(_read(workflow))
    assert "exit 0" in body, (
        f"{workflow.name}: Install Inno Setup must `exit 0` from the "
        "happy-path branch before the download/install block. Otherwise "
        "the download still runs even after the probe succeeds."
    )


@pytest.mark.parametrize("workflow", [INTL, CN], ids=["intl", "cn"])
def test_inno_setup_chinese_isl_skipped_when_present(workflow: Path):
    """The ChineseSimplified.isl download must also be a `if (-not Test-Path)`
    guard, so the 200KB language file is not re-downloaded every job."""
    body = _inno_block(_read(workflow))
    assert "if (-not (Test-Path $zhIsl))" in body, (
        f"{workflow.name}: ChineseSimplified.isl download must be "
        "guarded by `if (-not (Test-Path $zhIsl))`."
    )


# ---------------------------------------------------------------------------
# setup-node-env — must probe for system Node first.
# ---------------------------------------------------------------------------

def test_setup_node_env_probes_system_node():
    text = _read(SETUP_NODE_ENV)
    assert "Probe existing Node.js" in text, (
        "setup-node-env/action.yml must have a `Probe existing Node.js` "
        "step that detects a system-installed Node and short-circuits "
        "the actions/setup-node@v6 download."
    )
    assert "have-system-node" in text
    assert "actions/setup-node@v6" in text


def test_setup_node_env_system_node_skips_setup_action():
    """The `Set up Node.js` step must be gated on the probe result."""
    text = _read(SETUP_NODE_ENV)
    m = re.search(
        r"- name: Set up Node\.js[^\n]*\n[^\n]*if:[^\n]*steps\.probe-node\.outputs\.have-system-node",
        text,
    )
    assert m, (
        "setup-node-env/action.yml: `Set up Node.js` step must have an "
        "`if: steps.probe-node.outputs.have-system-node != 'true'` gate."
    )


def test_setup_node_env_default_node_version_20():
    """Bump default node-version from 18 to 20 — Node 18 is EOL as of
    2025-04-30 and several build dependencies (Vite 5, esbuild 0.20+)
    have moved past it.
    """
    text = _read(SETUP_NODE_ENV)
    m = re.search(
        r"node-version:\s*\n\s*description:.*?\n\s*required:\s*false\s*\n\s*default:\s*['\"](\d+)['\"]",
        text,
    )
    assert m, "Could not parse node-version default"
    assert int(m.group(1)) >= 20, (
        f"setup-node-env default node-version is {m.group(1)}; Node 18 is "
        "EOL. Bump to 20 (LTS)."
    )


def test_setup_wabaileys_system_node_skips_setup_action():
    text = _read(SETUP_WABA)
    m = re.search(
        r"- name: Set up Node\.js[^\n]*\n[^\n]*if:[^\n]*steps\.probe-node\.outputs\.have-system-node",
        text,
    )
    assert m, (
        "setup-wabaileys-bridge/action.yml: `Set up Node.js` step must "
        "be gated on the probe output."
    )


# ---------------------------------------------------------------------------
# setup-wabaileys-bridge — must probe for system Node first.
# ---------------------------------------------------------------------------

def test_setup_wabaileys_probes_system_node():
    text = _read(SETUP_WABA)
    assert "Probe existing Node.js" in text, (
        "setup-wabaileys-bridge/action.yml must have a `Probe existing "
        "Node.js` step before the actions/setup-node@v6 download."
    )
    assert "have-system-node" in text


# ---------------------------------------------------------------------------
# Cache steps must gate on runner.name to skip on self-hosted.
# ---------------------------------------------------------------------------

def _has_runner_name_gate(text: str, step_name_substr: str) -> bool:
    """Return True if the named step has `if:` containing the
    `startsWith(runner.name, 'GitHub Actions')` guard."""
    m = re.search(
        r"- name: [^\n]*" + re.escape(step_name_substr) + r"[^\n]*\n((?:[ ]+\S+.*\n)+)",
        text,
    )
    if not m:
        return False
    block = m.group(1)
    return "startsWith(runner.name, 'GitHub Actions')" in block


@pytest.mark.parametrize("workflow_path,step_name", [
    (INTL, "Cache Node.js dependencies"),
])
def test_workflow_node_cache_gated_on_hosted(workflow_path: Path, step_name: str):
    text = _read(workflow_path)
    assert _has_runner_name_gate(text, step_name), (
        f"{workflow_path.name}: `{step_name}` must have "
        "`if: startsWith(runner.name, 'GitHub Actions')`. Without it, "
        "self-hosted runners waste time on the cache lookup round-trip "
        "even though the per-job workspace always makes the cache miss."
    )


def test_release_cn_all_node_caches_gated():
    """release-cn.yml has 3 Cache Node.js dependencies steps (windows,
    linux, macos). All 3 must be gated. c082afd8 was supposed to bump
    them all to v5 but only the windows step was updated, and none
    got the runner.name gate.
    """
    text = _read(CN)
    matches = list(re.finditer(
        r"- name: Cache Node\.js dependencies", text,
    ))
    assert len(matches) >= 3, (
        f"release-cn.yml expected ≥3 'Cache Node.js dependencies' steps, "
        f"found {len(matches)}."
    )
    for i, m in enumerate(matches):
        # Each match's block must include the gate.
        block_end = text.find("\n      - name:", m.end())
        if block_end == -1:
            block_end = len(text)
        block = text[m.start():block_end]
        assert "startsWith(runner.name, 'GitHub Actions')" in block, (
            f"release-cn.yml Cache Node.js dependencies step #{i+1} "
            "missing the self-hosted skip gate."
        )


def test_setup_playwright_cache_gated_on_hosted():
    """All 3 platform branches in setup-playwright must gate cache@v5."""
    text = _read(SETUP_PLAYWRIGHT)
    for platform in ("Windows", "macOS", "Linux"):
        m = re.search(
            r"- name: Cache Playwright browsers \(" + platform + r"\)",
            text,
        )
        assert m, f"setup-playwright missing Cache Playwright ({platform}) step"
        block_end = text.find("\n    - name:", m.end())
        if block_end == -1:
            block_end = len(text)
        block = text[m.start():block_end]
        assert "startsWith(runner.name, 'GitHub Actions')" in block, (
            f"setup-playwright Cache ({platform}) missing self-hosted gate."
        )


def test_setup_python_env_venv_cache_gated_on_hosted():
    """The .venv and ~/.cache/pip caches must skip on self-hosted."""
    text = _read(SETUP_PYTHON_ENV)
    for step_name in ("Cache virtual environment", "Cache pip dependencies"):
        m = re.search(r"- name: " + step_name, text)
        assert m, f"setup-python-env missing '{step_name}'"
        block_end = text.find("\n    - name:", m.end())
        if block_end == -1:
            block_end = len(text)
        block = text[m.start():block_end]
        assert "startsWith(runner.name, 'GitHub Actions')" in block, (
            f"setup-python-env '{step_name}' missing self-hosted gate."
        )


def test_setup_wabaileys_npm_cache_gated_on_hosted():
    text = _read(SETUP_WABA)
    m = re.search(r"- name: Cache wa_bridge npm dependencies", text)
    assert m, "setup-wabaileys-bridge missing npm cache step"
    block_end = text.find("\n    - name:", m.end())
    if block_end == -1:
        block_end = len(text)
    block = text[m.start():block_end]
    assert "startsWith(runner.name, 'GitHub Actions')" in block, (
        "setup-wabaileys-bridge npm cache missing self-hosted gate."
    )