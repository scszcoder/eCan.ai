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
    """setup-node-env must always do a clean install (no reusing the
    runner's previous node_modules), AND it must detect whether the
    lockfile is part of the project's contract (tracked vs gitignored)
    so a stale lockfile from a previous build cannot trip `npm ci`.

    Background: gui_v2/.gitignore lists package-lock.json — any
    lockfile on the self-hosted runner is leftover state from a
    previous build, not a build contract. Trusting it caused
    commit 78f12e10e to break Linux CI with:

      npm ci can only install packages when your package.json and
      package-lock.json ... are in sync.
      Missing: @babel/core@7.29.7 from lock file

    wabaileys-bridge commits its lockfile — that project keeps
    `npm ci` for reproducibility.
    """
    text = _read(SETUP_NODE_ENV)
    # The two install paths must coexist (USE_CI branch + fallback
    # branch). The fallback branch's "rm -rf node_modules" is the
    # clean-install guarantee for both branches.
    assert "npm ci --legacy-peer-deps" in text, (
        "setup-node-env must keep the `npm ci` path for projects "
        "that commit package-lock.json (e.g. wabaileys-bridge)"
    )
    assert "rm -rf node_modules" in text, (
        "setup-node-env must clean node_modules before installing "
        "in the non-ci branch (gitignored-lockfile path)"
    )


def test_frontend_dependencies_detect_gitignored_lockfile():
    """When package-lock.json is gitignored (e.g. gui_v2), the action
    must skip `npm ci` and use `npm install` instead. Otherwise a
    stale lockfile on a persistent self-hosted runner trips EUSAGE.

    The detection uses `git check-ignore` (cwd-relative). Pin that
    contract here so a future refactor that switches to absolute
    paths or a different ignore-detection tool gets caught before
    shipping as a CI regression.
    """
    text = _read(SETUP_NODE_ENV)
    assert "git check-ignore package-lock.json" in text, (
        "setup-node-env must detect gitignored package-lock.json "
        "via `git check-ignore package-lock.json` (cwd-relative). "
        "Without this branch, a stale lockfile on a self-hosted "
        "runner trips `npm ci` with EUSAGE whenever package.json "
        "drifts (see 78f12e10e)."
    )
    # USE_CI branch control — must drive both install paths.
    assert "USE_CI" in text, (
        "setup-node-env must drive `npm ci` vs `npm install` via "
        "a USE_CI variable controlled by the gitignore check"
    )


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


def test_setup_python_env_probes_ctypes_before_picking_interpreter():
    """The Python-selection logic in `Create and activate virtual
    environment` must verify that the chosen interpreter can actually
    import `_ctypes`, not just that `command -v python3` finds
    something.

    Background: a self-hosted Linux runner had a non-standard
    Python installation at
        /home/ecan/actions-runner/_work/_tool/Python/3.12.14/x64/
    whose `_ctypes.so` was compiled against a different Python version
    and is missing `_PyErr_SetLocaleString`. With the previous logic
    (`command -v python3` only), the action picked this broken
    interpreter, the venv was based on it, and every PyInstaller
    subprocess then crashed at
        File ".../ctypes/__init__.py", line 8, in <module>
            from _ctypes import Union, Structure, Array
        ImportError: ... undefined symbol: _PyErr_SetLocaleString
    Pin the probe so a future refactor that goes back to the cheap
    `command -v python3` check gets caught before shipping as a CI
    regression.

    Probe order must also prefer the apt-installed /usr/bin/python3.12
    over PATH-default `python`/`python3`, so the broken tool-cache
    Python (if present) loses the race.
    """
    text = _read(SETUP_PYTHON_ENV)
    assert "import _ctypes, ctypes.util" in text, (
        "setup-python-env must probe `_ctypes` (not just `command -v`) "
        "when picking the Python interpreter. A self-hosted Linux runner "
        "had a broken _ctypes in its tool-cache Python which crashed "
        "PyInstaller with 'undefined symbol: _PyErr_SetLocaleString'."
    )
    # The probe candidates must include /usr/bin/python3.12 BEFORE any
    # bare PATH-default fallback so the apt-installed interpreter wins
    # over a non-standard tool-cache shadow.
    import re as _re
    candidates_section = text[text.index("for candidate in"):text.index("for candidate in") + 800]
    assert "/usr/bin/python3.12" in candidates_section, (
        "setup-python-env's Python probe must list /usr/bin/python3.12 "
        "(apt-installed; matches requirements-base.txt)."
    )
    explicit_312 = candidates_section.index("/usr/bin/python3.12")
    # Match the bare `python`/`python3` fallbacks by anchoring on the
    # trailing whitespace/semicolon — this avoids matching python3.12
    # / python3.13 which appear earlier in the loop.
    bare_fallbacks = [
        m.start() for m in _re.finditer(
            r"(?:^|\s)(?:python|python3)(?:[\s;])", candidates_section
        )
    ]
    assert bare_fallbacks, (
        "Could not locate bare `python`/`python3` fallback in the probe "
        "loop. The candidates-section text may have drifted from the "
        "loop body."
    )
    assert explicit_312 < bare_fallbacks[0], (
        "/usr/bin/python3.12 must be probed BEFORE any bare `python`/"
        "`python3` fallback so a non-standard tool-cache Python on PATH "
        "cannot win the race."
    )


def test_setup_python_env_ctypes_probe_fails_loudly_when_no_working_python():
    """When every probe candidate either is missing or has a broken
    _ctypes, the action must `::error::` with an actionable fix
    rather than silently picking the broken one."""
    text = _read(SETUP_PYTHON_ENV)
    assert '::error::No working Python 3.12 found on PATH' in text, (
        "setup-python-env must emit a ::error:: with the install "
        "command when no working Python can be found, so the operator "
        "knows to fix the runner instead of wondering why builds fail."
    )
    assert "sudo apt install python3.12 python3.12-venv" in text, (
        "The fallback error message must include the apt-install command "
        "from docs/DEPLOYMENT_UBUNTU.md so the operator can fix the "
        "runner without leaving the log."
    )


def test_setup_python_env_existing_venv_is_ctypes_probed_before_reuse():
    """The venv REUSE branch must run the same `_ctypes` contract probe
    on the existing `.venv/bin/python` (or `.venv/Scripts/python.exe`)
    before declaring it reusable.

    Background: `actions/cache@v5` for the venv is gated to
    github-hosted runners only, so on a persistent self-hosted
    runner any pre-existing `.venv` is leftover workspace state from
    a previous job. If that previous job ran against an older version
    of this action (or before the launcher probe was added), the venv
    was created by whatever interpreter won `command -v` then — which
    on the Linux runner that produced the bug was the broken
    tool-cache Python at
        /home/ecan/actions-runner/_work/_tool/Python/3.12.14/x64/

    The launcher probe alone does not save us here: even if the
    system Python has since been fixed (or a fresh probe picks
    /usr/bin/python3.12), the script's naive `if [ -d .venv ] && [ -f
    $VENV_PYTHON ]` short-circuit would skip recreating the venv and
    inherit the broken `pyvenv.cfg` home, re-importing ctypes from
    the tool-cache Python's `_ctypes.so` on the very first PyInstaller
    subprocess.

    Pin the contract: the reuse branch must call
        $VENV_PYTHON -c "import _ctypes, ctypes.util"
    before printing a "reusing" message; on failure it must drop the
    venv and recreate it from the verified launcher.
    """
    text = _read(SETUP_PYTHON_ENV)
    assert "Existing virtual environment has working _ctypes; reusing .venv" in text, (
        "setup-python-env's venv-reuse branch must announce the probe "
        "result explicitly, so a future refactor that goes back to a "
        "naive `if [ -d .venv ]` check leaves an obvious signal in "
        "the CI log instead of silently reusing a poisoned venv."
    )
    assert "broken _ctypes" in text, (
        "setup-python-env must log when the existing venv's _ctypes "
        "fails, attributing it to a leftover from a previous job on "
        "this self-hosted runner so the operator isn't surprised by "
        "the `rm -rf .venv` that follows."
    )
    # The reuse branch must call the same `_ctypes` contract probe as
    # the launcher probe, before printing a "reusing" message. The
    # exact tokenizer-friendly pattern (split across the `&&` line
    # continuation in the YAML) is:
    #     "$VENV_PYTHON" -c "import _ctypes, ctypes.util"
    # Pin it as-is so a refactor that goes back to a naive
    # `if [ -d .venv ]` check leaves an obvious failure here, not
    # a quiet poison-venv regression in CI.
    import re as _re
    reuse_probes = _re.findall(
        r'"\$VENV_PYTHON"\s+-c\s+"import _ctypes,\s*ctypes\.util"',
        text,
    )
    assert len(reuse_probes) == 1, (
        "setup-python-env must run the `_ctypes` probe against "
        "`$VENV_PYTHON` exactly once before declaring the existing "
        "venv reusable. The probe is the contract that distinguishes "
        "a healthy venv from one created by the broken tool-cache "
        f"Python. Found {len(reuse_probes)} matching probes."
    )
    # And the reuse-probe must appear AFTER the launcher probe loop,
    # so the launcher has been verified before we trust it to
    # recreate the venv.
    launcher_marker = "Using Python launcher:"
    reuse_marker = "Existing virtual environment has working _ctypes"
    assert text.index(launcher_marker) < text.index(reuse_marker), (
        "launcher probe must run before venv-reuse probe; otherwise "
        "the reuse branch could recreate the venv from a launcher "
        "we haven't verified yet."
    )
