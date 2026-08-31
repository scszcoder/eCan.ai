"""
Contract tests for the self-hosted vs GitHub-hosted environment-setup
optimisations.

Background: eCan.ai's release pipelines (release-intl.yml, release-cn.yml)
run on two classes of runners:

  - GitHub-hosted windows-latest / ubuntu-latest / macos-latest — every
    job gets a fresh VM, so reusable data must be restored explicitly.
  - Self-hosted runners labelled `self-hosted,windows,x64,ecan-build`
    (and the linux/macos variants) — the OS image is persistent across
    jobs. Builds still must not rely on stale project workspace contents.

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

  4. Versioned third-party caches must run on self-hosted runners too. Frontend
     `node_modules` is deliberately excluded and recreated from package-lock.json
     on every build to avoid stale native modules.

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
# Cache steps must also run on self-hosted.
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


@pytest.mark.parametrize("workflow", [INTL, CN])
def test_frontend_node_modules_is_not_cached(workflow: Path):
    text = _read(workflow)
    assert "Cache Node.js dependencies" not in text
    assert "path: gui_v2/node_modules" not in text


def test_frontend_dependencies_are_always_clean_installed():
    text = _read(SETUP_NODE_ENV)
    assert "npm ci --legacy-peer-deps" in text


def test_frontend_caches_only_npm_downloads():
    text = _read(SETUP_NODE_ENV)
    assert "Cache npm download cache" in text
    assert "path: ${{ runner.temp }}/npm-cache" in text
    assert "npm_config_cache: ${{ runner.temp }}/npm-cache" in text
    assert "path: ${{ inputs.frontend-dir }}/node_modules" not in text


def test_setup_playwright_cache_enabled_on_self_hosted():
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
        assert "startsWith(runner.name, 'GitHub Actions')" not in block, (
            f"setup-playwright Cache ({platform}) still skips self-hosted."
        )
        assert "${{ inputs.browsers }}" in block
        assert "third_party" not in block


def test_setup_python_env_pip_cache_enabled_on_self_hosted():
    text = _read(SETUP_PYTHON_ENV)
    m = re.search(r"- name: Cache pip dependencies", text)
    assert m, "setup-python-env missing pip cache step"
    block_end = text.find("\n    - name:", m.end())
    block = text[m.start():block_end if block_end != -1 else len(text)]
    assert "runner.environment" not in block
    assert "path: ${{ runner.temp }}/pip-cache" in block


def test_virtualenv_cache_is_hosted_only():
    text = _read(SETUP_PYTHON_ENV)
    m = re.search(r"- name: Cache virtual environment", text)
    assert m, "setup-python-env missing venv cache step"
    block_end = text.find("\n    - name:", m.end())
    block = text[m.start():block_end if block_end != -1 else len(text)]
    assert "runner.environment == 'github-hosted'" in block


def test_setup_wabaileys_npm_cache_enabled_on_self_hosted():
    text = _read(SETUP_WABA)
    m = re.search(r"- name: Cache wa_bridge npm downloads", text)
    assert m, "setup-wabaileys-bridge missing npm cache step"
    block_end = text.find("\n    - name:", m.end())
    if block_end == -1:
        block_end = len(text)
    block = text[m.start():block_end]
    assert "startsWith(runner.name, 'GitHub Actions')" not in block, (
        "setup-wabaileys-bridge npm cache still skips self-hosted."
    )
    assert "path: ${{ runner.temp }}/wa-bridge-npm-cache" in block
    assert "/node_modules" not in block
    assert "npm ci --prefer-offline" in text


def test_windows_virtualenv_is_exported_as_native_path():
    text = _read(SETUP_PYTHON_ENV)
    assert 'VENV_DIR_WIN="$(cygpath -w "$PWD/.venv")"' in text
    assert 'echo "VIRTUAL_ENV=$VENV_DIR_WIN"' in text


def test_virtualenv_cache_is_separated_by_app():
    text = _read(SETUP_PYTHON_ENV)
    assert "${{ env.ECAN_APP_ID }}-venv" in text
