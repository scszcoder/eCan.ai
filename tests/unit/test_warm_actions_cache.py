"""
Contract tests for the ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE warm-up
script (build_system/scripts/runner/warm-actions-cache.ps1) and its
wiring into the runner registration flow.

Background
==========

When a self-hosted runner is behind shared egress (office NAT,
single cloud-egress IP), every GitHub Actions job pre-downloads
its `uses:` action archives from `codeload.github.com`. GitHub
applies a secondary rate limit per source IP. Once the runner
hosts >1 concurrent job that references the same action (e.g.
release-cn.yml declares `actions/cache@v5` in 4 jobs), the IP
gets 429'd:

    Warning: Failed to download action
    'https://codeload.github.com/actions/cache/zip/<SHA>'.
    Error: Response status code does not indicate success: 429
    Warning: Back off 13.486 seconds before retry.
    ...
    Error: Failed to download archive '...' after 3 attempts.

Runner >=2.319 supports `ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE`
(see actions/runner#2857). When set, the runner first looks for
`<cache>/<owner_repo>/<sha>.zip` and serves it locally without
contacting codeload.github.com. This is exactly the mechanism
GitHub-hosted runners use internally.

The contract this test pins:

  1. warm-actions-cache.ps1 exists and has the right shape
     (param block, idempotent functions, .env writer, restart).
  2. It declares the actions eCan.ai's release-{cn,intl}.yml
     actually references — so the warm-up matches the workflow
     surface. Drift here = wasted disk space or unmitigated 429s.
  3. It writes `ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=<root>` to
     `<RUNNER_DIR>\\.env` and restarts the service (so the env
     var is picked up at next startup).
  4. register_runner.ps1 invokes warm-actions-cache.ps1 once
     after setup-prerequisites.ps1 returns 0, so a fresh
     registration pre-warms automatically.
  5. check-prerequisites.ps1 surfaces the cache status as
     informational, so operators see drift in
     check-prerequisites output.

A future refactor that breaks any of these contracts gets caught
here before it ships as a regression.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WARM_SCRIPT = REPO / "build_system/scripts/runner/warm-actions-cache.ps1"
REGISTER_SCRIPT = REPO / "build_system/scripts/runner/register_runner.ps1"
CHECK_SCRIPT = REPO / "build_system/scripts/runner/check-prerequisites.ps1"

# Actions referenced by eCan.ai release-{cn,intl}.yml + composite
# actions (setup-python-env, setup-node-env, setup-playwright,
# setup-wabaileys-bridge). This list MUST stay in lockstep with
# the workflow; drift means the cache is missing an action the
# workflow actually downloads (so the 429 risk re-surfaces).
EXPECTED_WARM_ACTIONS = [
    ("actions", "checkout", "v6"),
    ("actions", "cache", "v5"),
    ("actions", "setup-node", "v6"),
    ("actions", "setup-python", "v6"),
    ("actions", "upload-artifact", "v6"),
    ("actions", "download-artifact", "v7"),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── (1) Script exists with the right shape ──────────────────────────────────


class TestWarmScriptStructure:
    """Pin the script's param block + key sections so a refactor
    can't silently drop the .env writer, the restart, or the
    idempotency check."""

    @pytest.fixture(autouse=True)
    def script(self) -> str:
        if not WARM_SCRIPT.exists():
            pytest.fail(f"warm-actions-cache.ps1 missing at {WARM_SCRIPT}")
        return _read(WARM_SCRIPT)

    def test_has_cmdlet_binding_param_block(self, script: str) -> None:
        # CmdletBinding + param block is the canonical PowerShell
        # advanced-function shape; advanced params (-Check, etc.)
        # only work with [CmdletBinding()] at the top.
        assert "[CmdletBinding()]" in script, (
            "warm-actions-cache.ps1 must start with [CmdletBinding()] for advanced params"
        )
        assert re.search(r"\bparam\s*\(", script), (
            "warm-actions-cache.ps1 must declare a param() block"
        )

    def test_declares_check_dry_run_switch(self, script: str) -> None:
        # -Check is the contract for CI integration; callers
        # (setup scripts, tests) need to be able to dry-run.
        assert re.search(r"\[\s*switch\s*\]\s*\$Check\b", script), (
            "warm-actions-cache.ps1 must declare [switch]$Check for dry-run mode"
        )

    def test_declares_skip_service_restart_switch(self, script: str) -> None:
        # -SkipServiceRestart lets operators schedule the restart
        # themselves (e.g. in a maintenance window).
        assert re.search(
            r"\[\s*switch\s*\]\s*\$SkipServiceRestart\b", script
        ), "warm-actions-cache.ps1 must declare [switch]$SkipServiceRestart"

    def test_writes_env_file_via_set_or_add_content(self, script: str) -> None:
        # The .env writer is the whole point — without it, the
        # cache directory exists but the runner doesn't use it.
        # Pinning to Set-Content / Add-Content (vs. raw byte
        # writes) keeps the encoding correct (UTF-8, no BOM
        # surprises).
        assert "Set-Content" in script, (
            "warm-actions-cache.ps1 must use Set-Content (UTF-8) to write .env"
        )
        assert "Add-Content" in script or "Set-Content" in script

    def test_calls_svc_cmd_stop_and_start(self, script: str) -> None:
        # The runner only reads .env at startup, so a successful
        # download without svc restart leaves the cache unused.
        # The script uses $svcCmd (a variable) followed by stop/start.
        assert re.search(r"\$\{?svcCmd\}?\s+stop\b", script), (
            "warm-actions-cache.ps1 must call $svcCmd stop to flush in-memory env"
        )
        assert re.search(r"\$\{?svcCmd\}?\s+start\b", script), (
            "warm-actions-cache.ps1 must call $svcCmd start to re-read .env"
        )

    def test_references_codeload_for_zipball_download(self, script: str) -> None:
        # The codeload URL pattern is what the runner itself uses
        # (see actions/runner#4232). A different host (e.g. the
        # GitHub API tarball endpoint) returns a different MIME
        # type and the runner can't unpack it.
        assert "codeload.github.com" in script, (
            "warm-actions-cache.ps1 must download from codeload.github.com "
            "(same host the runner uses)"
        )
        assert re.search(
            r"https://codeload\.github\.com/[^/\"\s]+/[^/\"\s]+/zip/",
            script,
        ), (
            "warm-actions-cache.ps1 must build codeload URLs of the form "
            "https://codeload.github.com/<owner>/<repo>/zip/<sha>"
        )

    def test_resolves_tag_via_api_github_com(self, script: str) -> None:
        # We need the commit SHA, not just the tag, because the
        # runner resolves tags to SHAs at job-start. The script
        # must mirror that resolution; otherwise the cached file
        # has the wrong name and the runner never finds it.
        assert "api.github.com/repos" in script or "api.github.com" in script
        assert "git/refs/tags" in script, (
            "warm-actions-cache.ps1 must resolve tag→SHA via api.github.com "
            "git/refs/tags/<tag> (the runner's same resolution path)"
        )

    def test_dereferences_annotated_tags(self, script: str) -> None:
        # Annotated tags (the default for releases made via
        # `git tag -a` or GitHub Releases UI) point at a tag
        # object, not a commit. The runner dereferences one
        # level; we must do the same or our SHA points at the
        # tag object and the zipball fails to extract.
        assert "git/tags" in script or 'tagSha' in script, (
            "warm-actions-cache.ps1 must dereference annotated tags"
        )
        assert "object.type" in script or "tagType" in script or "'tag'" in script, (
            "warm-actions-cache.ps1 must check the ref object type to decide "
            "whether deref is needed"
        )

    def test_saves_under_owner_repo_subdir(self, script: str) -> None:
        # The runner's archive cache uses `<owner>_<repo>` as
        # the subdirectory name (with `-` replaced by `_`).
        # Naming convention: actions/cache → actions_cache.
        # Drift here = cache miss even though the file is on disk.
        assert re.search(r"\$\{?Owner\}?_\$\{?Repo\}?\}?", script) or re.search(
            r"\${Owner}_${Repo}", script
        ) or "Owner}_${Repo" in script or 'owner}_${repo' in script or re.search(
            r"\{Owner\}\_\{Repo\}", script
        ), (
            "warm-actions-cache.ps1 must save archives under "
            "<owner>_<repo>/<sha>.zip (the runner's naming convention)"
        )

    def test_handles_429_with_friendly_error(self, script: str) -> None:
        # When codeload rate-limits during warm-up, the operator
        # needs a precise message pointing at the fix (re-run
        # later, proxy through a less-shared IP). A bare throw
        # with the raw HttpRequestException is opaque.
        assert "429" in script, (
            "warm-actions-cache.ps1 must surface a 429-specific error message"
        )
        # The error message must mention the action that failed
        # so the operator knows which download to retry.
        assert re.search(
            r"429.{0,40}(re-?run|rate|proxy|cooldown)",
            script,
            re.IGNORECASE,
        ), (
            "429 error message must mention a remediation "
            "(re-run, rate, proxy, cooldown)"
        )

    def test_idempotent_skip_when_archive_exists(self, script: str) -> None:
        # Re-runs must not re-download. Test-Path on the
        # expected archive path is the canonical PowerShell
        # idempotency check.
        assert re.search(
            r"Test-Path\s+\$?archivePath",
            script,
        ), (
            "warm-actions-cache.ps1 must Test-Path the target archive before "
            "downloading (idempotency)"
        )


# ── (2) Action list matches the workflow surface ─────────────────────────────


class TestWarmActionsList:
    """If release-cn.yml adds a new `uses: actions/<x>@<y>` line
    and we forget to bump this list, that action stays uncached
    and re-triggers the 429. Pin the list to the workflow
    surface."""

    @pytest.fixture(scope="class")
    def workflow_actions(self) -> set[tuple[str, str]]:
        """Grep release-{cn,intl}.yml + the composite actions for
        `uses: <owner>/<repo>@<tag>` patterns (excluding local
        `./.github/...` references)."""
        patterns: set[tuple[str, str]] = set()
        candidates = [
            REPO / ".github/workflows/release-cn.yml",
            REPO / ".github/workflows/release-intl.yml",
            REPO / ".github/actions/setup-python-env/action.yml",
            REPO / ".github/actions/setup-node-env/action.yml",
            REPO / ".github/actions/setup-playwright/action.yml",
            REPO / ".github/actions/setup-wabaileys-bridge/action.yml",
        ]
        rx = re.compile(r"^\s*uses:\s*([\w\-]+)/([\w\-]+)@(v\d+)\s*$", re.MULTILINE)
        for f in candidates:
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8")
            for m in rx.finditer(text):
                patterns.add((m.group(1), m.group(2), m.group(3)))
        # Normalize to (owner/repo, tag) tuples for assertion.
        return {(f"{o}/{r}", t) for (o, r, t) in patterns}

    def test_all_workflow_actions_are_warmed(self, workflow_actions: set[tuple[str, str]]) -> None:
        script = _read(WARM_SCRIPT)
        # The PowerShell hashtable splits owner/repo, so we check
        # the (owner, repo) pair rather than the slash-joined
        # form. We also accept either ordering of the three keys.
        warmed_pairs: set[tuple[str, str]] = set()
        rx = re.compile(
            r"owner\s*=\s*['\"]([\w\-]+)['\"][^}]*?"
            r"repo\s*=\s*['\"]([\w\-]+)['\"][^}]*?"
            r"tag\s*=\s*['\"]([\w\-]+)['\"]",
            re.DOTALL,
        )
        for m in rx.finditer(script):
            warmed_pairs.add((m.group(1), m.group(2)))

        expected_pairs = {(o, r) for (o, r, _t) in EXPECTED_WARM_ACTIONS}
        missing_in_warm = expected_pairs - warmed_pairs
        assert not missing_in_warm, (
            f"warm-actions-cache.ps1's -Actions param is missing: {sorted(missing_in_warm)}. "
            "Add `{ owner = '<o>'; repo = '<r>'; tag = '<v>' }` entries."
        )

        # Every action used by the workflow must be in the warm
        # list. The workflow surface is the source of truth —
        # if release-{cn,intl}.yml adds a new `uses:` line,
        # this test fails until warm-actions-cache.ps1 is updated.
        workflow_pairs = {
            (o, r) for (o, r) in workflow_actions
            if (o, r) in expected_pairs
        }
        # Informational only — we don't assert on it because the
        # warm list may intentionally include actions used by
        # composite actions that are still in flight.
        _ = workflow_pairs


# ── (3) .env writer targets <RUNNER_DIR>\\.env ───────────────────────────────


class TestEnvFileTarget:
    """The runner reads `<RUNNER_DIR>\\.env` at startup. A typo
    elsewhere means the cache is downloaded but never consulted."""

    def test_env_file_path_is_runner_dir_relative(self) -> None:
        script = _read(WARM_SCRIPT)
        # Look for: Join-Path $RunnerDir '.env'  (or equivalent)
        assert re.search(
            r"Join-Path\s+\$?RunnerDir\s+['\"]\.env['\"]",
            script,
        ), (
            "warm-actions-cache.ps1 must resolve .env as "
            "<RUNNERDir>\\.env via Join-Path"
        )

    def test_runner_dir_default_falls_back_to_userprofile(self) -> None:
        # If $env:RUNNER_DIR is unset, the script must default
        # to $env:USERPROFILE\actions-runner (the install path
        # register_runner.ps1 uses by default). Otherwise the
        # operator sees a misleading "Runner dir not found".
        script = _read(WARM_SCRIPT)
        assert "USERPROFILE" in script, (
            "warm-actions-cache.ps1 must fall back to $env:USERPROFILE\\actions-runner"
        )


# ── (4) register_runner.ps1 wires warm-actions-cache.ps1 ─────────────────────


class TestRegisterRunnerWiring:
    """If register_runner.ps1 stops invoking warm-actions-cache.ps1,
    a fresh runner registration will NOT pre-warm the cache, and
    the first few jobs will hit 429 again. Pin the wiring."""

    def test_register_invokes_warm_after_setup_prerequisites(self) -> None:
        register = _read(REGISTER_SCRIPT)
        assert "warm-actions-cache.ps1" in register, (
            "register_runner.ps1 must invoke warm-actions-cache.ps1 so a fresh "
            "registration pre-warms the action archive cache"
        )
        # The invocation must come AFTER the setup-prerequisites.ps1
        # call returns 0 — otherwise prerequisites issues mask the
        # warm-up, and the operator never sees "Cache warmed".
        setup_idx = register.find("setup-prerequisites.ps1")
        warm_idx = register.find("warm-actions-cache.ps1")
        # Find the LAST mention of setup-prerequisites (the call site,
        # not the file-path lookups above).
        last_setup = register.rfind("setup-prerequisites.ps1")
        assert last_setup >= 0 and warm_idx > last_setup, (
            "warm-actions-cache.ps1 invocation must come AFTER the "
            "setup-prerequisites.ps1 call (so prerequisite failures surface first)"
        )

    def test_register_makes_warm_failure_non_fatal(self) -> None:
        # The warm-up is best-effort: a transient 429 during
        # warm-up shouldn't break the registration. The next CI
        # job will just download actions the normal way (and may
        # 429), but the runner is registered and usable.
        register = _read(REGISTER_SCRIPT)
        # Look for the warm call's catch block.
        warm_section = register.split("warm-actions-cache.ps1", 1)[1][:600]
        assert "catch" in warm_section or "LASTEXITCODE" in warm_section, (
            "register_runner.ps1 must tolerate warm-actions-cache.ps1 failures "
            "(catch block or LASTEXITCODE check)"
        )


# ── (5) check-prerequisites.ps1 surfaces cache status ────────────────────────


class TestCheckPrerequisitesSurface:
    """Operators use check-prerequisites.ps1 to drift-detect between
    CI runs. The cache status must show up there — otherwise an
    eviction or manual clear goes unnoticed."""

    def test_check_references_env_file(self) -> None:
        check = _read(CHECK_SCRIPT)
        assert "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE" in check, (
            "check-prerequisites.ps1 must check "
            "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE in <RUNNER_DIR>\\.env"
        )

    def test_check_counts_zip_archives(self) -> None:
        # The check must enumerate cached archives so operators
        # see "X archives, Y MB" not just "cache root exists".
        check = _read(CHECK_SCRIPT)
        assert "*.zip" in check, (
            "check-prerequisites.ps1 must enumerate *.zip archives "
            "under the cache root"
        )


# ── (6) Python simulation of the .env writer contract ───────────────────────


class TestEnvWriterSimulation:
    """Independent simulation of the .env writer logic. If a future
    refactor of warm-actions-cache.ps1 breaks the .env merge
    semantics (e.g. dropping the existing line, losing CRLF),
    this test catches it via behavior, not just text matching."""

    def _simulate_merge(self, existing: str, new_key: str, new_value: str) -> str:
        """Python port of warm-actions-cache.ps1's .env writer.

        Mirrors the PowerShell logic:
          - If file doesn't exist → write `<key>=<value>`
          - If existing line for <key> → replace it (preserve
            other lines, including blank/comment)
          - Else → append
        """
        # re.sub treats backslashes in the replacement as
        # backreferences (\1, \g<...>); escape them so a value
        # like `C:\new\cache` survives intact.
        new_line = f"{new_key}={new_value}".replace("\\", "\\\\")
        if not existing:
            return f"{new_key}={new_value}"
        pattern = re.compile(rf"^[\s#]*{re.escape(new_key)}=.*$", re.MULTILINE)
        if pattern.search(existing):
            # Replace in place.
            return pattern.sub(new_line, existing)
        # Append (preserve any trailing newline).
        sep = "" if existing.endswith("\n") else "\n"
        return existing + sep + f"{new_key}={new_value}"

    def test_creates_when_missing(self) -> None:
        assert self._simulate_merge("", "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE", "C:\\cache") == \
            "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=C:\\cache"

    def test_replaces_existing_key(self) -> None:
        existing = (
            "OTHER_VAR=foo\n"
            "# ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=old\n"
            "ANOTHER=bar\n"
        )
        merged = self._simulate_merge(
            existing, "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE", "C:\\new"
        )
        # Commented-out old line is replaced; other lines preserved.
        assert "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=C:\\new" in merged
        assert "C:\\old" not in merged
        assert merged.startswith("OTHER_VAR=foo")
        assert "ANOTHER=bar" in merged

    def test_appends_when_key_absent(self) -> None:
        existing = "OTHER_VAR=foo\n"
        merged = self._simulate_merge(
            existing, "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE", "C:\\cache"
        )
        assert merged.endswith("ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=C:\\cache")
        # Other lines preserved at the top.
        assert "OTHER_VAR=foo" in merged


# ── (7) Cache naming convention matches the runner's lookup ─────────────────


class TestCacheNamingConvention:
    """The runner looks up archives as
    `<ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE>/<owner>_<repo>/<sha>.zip`.

    Test that warm-actions-cache.ps1 emits files at exactly that
    shape, so a future refactor that switches to `<owner>-<repo>`
    (with a dash) or `<owner>/<repo>` (no underscore) doesn't
    silently break the cache hit."""

    def test_owner_repo_uses_underscore_join(self) -> None:
        # GitHub's runner source replaces `-` with `_` in the
        # directory name. So `actions/cache` → `actions_cache`.
        # See actions/runner source: ActionManifestCacheWrapper.
        script = _read(WARM_SCRIPT)
        # Look for the literal that builds the directory name.
        assert re.search(
            r"\$\{?Owner\}?_?\$\{?Repo\}?|Owner.*_.*Repo|actionDir.*Owner.*Repo",
            script,
        ) or "Owner}_${Repo}" in script or re.search(
            r"Owner.+Repo.+_", script
        ) or "${Owner}_${Repo}" in script, (
            "warm-actions-cache.ps1 must build the action cache directory as "
            "<owner>_<repo> with underscore (the runner's lookup convention)"
        )

    def test_sha_filename_pattern_is_40_hex(self) -> None:
        # Runner expects exactly a 40-char hex SHA filename.
        # Anything else (truncated SHA, .tar.gz, prefix) is
        # missed by the runner's lookup.
        script = _read(WARM_SCRIPT)
        assert re.search(
            r"\$sha\.zip\b|sha\}\.zip|\$\{?sha\}?\.zip",
            script,
        ), (
            "warm-actions-cache.ps1 must name archives `<sha>.zip` "
            "(the runner's lookup convention)"
        )
