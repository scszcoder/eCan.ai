# -*- coding: utf-8 -*-
"""The frontend dependency set and the bundle contents are a build contract.

Two regressions are pinned here.

**1. Floating @flowgram.ai ranges broke the production build.**
`gui_v2/package-lock.json` is gitignored (gui_v2/.gitignore:44), so nothing
pinned the npm tree, and CI installs gui_v2 with a plain `npm install`
(.github/actions/setup-node-env: `rm -rf node_modules` then install). With
`^1.0.3` / `^1.0.7` ranges, npm resolved `@flowgram.ai/core` and
`free-layout-core` to 1.0.15 while `free-layout-editor` stayed at 1.0.3. The
mixed tree re-exports `useService` from two different modules, rollup drops the
ambiguous name, and the build dies with::

    EditorBridge.tsx (9:9): "useService" is not exported by
    "@flowgram.ai/free-layout-editor/dist/esm/index.js"

Every @flowgram.ai package must therefore carry one exact version, matching the
tracked pnpm-lock.yaml.

**2. `npm ci` cannot work for a frontend whose lockfile is gitignored.**
`build_system/ecan_build.py` called `npm ci` unconditionally; on a fresh clone
there is no lockfile at all, and on a reused runner a stale one makes npm exit
with EUSAGE (the failure commit 78f12e10e caused). The verb must follow the
same lockfile-contract rule setup-node-env already applies.

**3. The bundle shipped ~1.3k test files for an import that cannot work.**
`minibuild_core.py` kept the project's `tests/` tree because
`gui/ipc/handlers.py` imports `tests.unittests` -- a module that does not exist
and never has. Both call sites are dead debug paths.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PACKAGE_JSON = PROJECT_ROOT / "gui_v2" / "package.json"
PNPM_LOCK = PROJECT_ROOT / "gui_v2" / "pnpm-lock.yaml"
ECAN_BUILD = PROJECT_ROOT / "build_system" / "ecan_build.py"
MINIBUILD = PROJECT_ROOT / "build_system" / "minibuild_core.py"

EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _deps():
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    merged = {}
    merged.update(data.get("dependencies", {}))
    merged.update(data.get("devDependencies", {}))
    return merged


def _flowgram_deps():
    return {k: v for k, v in _deps().items() if k.startswith("@flowgram.ai/")}


# ---------------------------------------------------------------------------
# 1. the @flowgram.ai family must be pinned, and pinned consistently
# ---------------------------------------------------------------------------

def test_the_flowgram_family_is_not_empty():
    """Guard the guard: if this ever matches nothing the pin tests prove nothing."""
    assert len(_flowgram_deps()) >= 15


def test_every_flowgram_dependency_is_an_exact_version():
    """A `^`/`~` range is what let npm resolve a mixed, build-breaking tree."""
    floating = {k: v for k, v in _flowgram_deps().items()
                if not EXACT_VERSION.match(v)}
    assert not floating, f"unpinned @flowgram.ai ranges: {floating}"


def test_every_flowgram_dependency_agrees_on_one_version():
    """The failure was a *mixed* tree (1.0.15 next to 1.0.3), not a new version."""
    versions = set(_flowgram_deps().values())
    assert len(versions) == 1, f"@flowgram.ai versions disagree: {sorted(versions)}"


def test_the_tracked_lockfile_resolves_the_pinned_version():
    """package.json and the tracked pnpm-lock.yaml must not drift apart."""
    lock = PNPM_LOCK.read_text(encoding="utf-8")
    drifted = {}
    for name, want in _flowgram_deps().items():
        short = name.split("/", 1)[1]
        found = re.search(
            r"'@flowgram\.ai/" + re.escape(short) + r"@([0-9][0-9.]*)'", lock)
        if not found or found.group(1) != want:
            drifted[name] = (want, found.group(1) if found else None)
    assert not drifted, f"pnpm-lock.yaml disagrees with package.json: {drifted}"


def test_the_pinned_version_satisfies_the_previously_declared_floor():
    """Pinning must not silently downgrade below what the code was written for."""
    for name, version in _flowgram_deps().items():
        major, minor, patch = (int(p) for p in version.split("."))
        assert (major, minor, patch) >= (1, 0, 7), f"{name} pinned below 1.0.7"


# ---------------------------------------------------------------------------
# 2. the install verb must follow the lockfile contract
# ---------------------------------------------------------------------------

def _frontend_builder(project_root):
    from build_system.ecan_build import FrontendBuilder
    return FrontendBuilder(Path(project_root))


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A throwaway git repo with a gui_v2 dir, so check-ignore has something to say."""
    if not shutil.which("git"):
        pytest.skip("git is required to probe the lockfile contract")
    frontend = tmp_path / "gui_v2"
    frontend.mkdir()
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"]):
        _git(cmd, tmp_path)
    return tmp_path, frontend


def test_no_lockfile_means_no_npm_ci(repo):
    """`npm ci` without a lockfile is a hard EUSAGE failure, not a slow install."""
    tmp_path, _ = repo
    assert _frontend_builder(tmp_path)._lockfile_is_a_contract() is False


def test_a_gitignored_lockfile_is_leftover_state_not_a_contract(repo):
    """The gui_v2 situation: present on the runner, but not part of the build."""
    tmp_path, frontend = repo
    (tmp_path / "gui_v2" / ".gitignore").write_text(
        "package-lock.json\n", encoding="utf-8")
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    assert _frontend_builder(tmp_path)._lockfile_is_a_contract() is False


def test_a_tracked_lockfile_is_a_contract(repo):
    """The wabaileys-bridge situation: committed, so `npm ci` is both possible and right."""
    tmp_path, frontend = repo
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    _git(["add", "gui_v2/package-lock.json"], tmp_path)
    assert _frontend_builder(tmp_path)._lockfile_is_a_contract() is True


def test_gui_v2_itself_does_not_get_npm_ci():
    """The real repo: gui_v2's lockfile is gitignored, so the verb must be install."""
    if not shutil.which("git"):
        pytest.skip("git is required to probe the lockfile contract")
    assert _frontend_builder(PROJECT_ROOT)._lockfile_is_a_contract() is False


def test_the_build_never_hardcodes_npm_ci():
    """The unconditional `npm ci` string is what broke fresh clones."""
    source = ECAN_BUILD.read_text(encoding="utf-8")
    assert '"npm ci' not in source and "'npm ci" not in source
    assert '_lockfile_is_a_contract' in source


# ---------------------------------------------------------------------------
# 3. the bundle must not ship the test suite
# ---------------------------------------------------------------------------

def _drop_tokens():
    """Extract the drop_tokens list the generated .spec filters datas with."""
    source = MINIBUILD.read_text(encoding="utf-8")
    match = re.search(r"^drop_tokens = \[(.*?)^\]", source,
                      re.DOTALL | re.MULTILINE)
    assert match, "drop_tokens not found in minibuild_core.py"
    body = match.group(1)
    body = re.sub(r"#.*", "", body)          # strip inline comments
    return ast.literal_eval("[" + body + "]")


def test_the_bundle_drops_the_tests_tree():
    tokens = _drop_tokens()
    assert any(t.strip("/") == "tests" for t in tokens), (
        f"no tests token in drop_tokens: {tokens}")


def test_a_project_test_path_is_dropped_but_runtime_data_is_not():
    """Both the token and the near-misses that must survive it."""
    tokens = _drop_tokens()

    def drops(dest):
        lp = dest.lower().replace("\\", "/")
        return any(tok in lp for tok in tokens)

    assert drops("tests/unit/test_app_watchdog.py")
    assert drops("tests\\unit\\test_watchdog_breaker.py")
    assert drops("site-packages/pytest/tests/test_x.py")
    # Near-misses that are real runtime data and must NOT be caught.
    assert not drops("resource/testdata/sample.json")
    assert not drops("agent/ec_skills/self_test/skill.py")
    assert not drops("gui_v2/dist/assets/index.js")


def test_tests_unittests_is_not_a_runtime_dependency():
    """The premise of the old exclusion: the module it protected does not exist."""
    assert not (PROJECT_ROOT / "tests" / "unittests").exists()
    assert not (PROJECT_ROOT / "tests" / "unittests.py").exists()


def test_the_stale_justification_is_gone():
    """The comment must not keep telling the next reader that tests/ is needed."""
    source = MINIBUILD.read_text(encoding="utf-8")
    assert "needed at runtime" not in source or "tests.unittests" in source
    assert not re.search(r"Do NOT include '/tests/'", source)
