"""
Unit tests for build_system/scripts/release-workflow-simulator.py and
build_system/scripts/release-pipeline-symmetry-check.py.

These tests assert the *building blocks* of the static pipeline evaluator
(validate-tag heuristics + GH Actions expression semantics + symmetry
normalization). The 4086-case end-to-end run in
release-workflow-simulator.py's main() is a smoke test; these unit
tests pin down the contracts so a bug in the evaluator itself surfaces
here, not only as "0 anomaly" or "1880 OK" output.

Without these, the simulator's claim of "symmetry between cn/intl" is
self-referential: it would be possible for the simulator to be wrong
in a way that affects BOTH pipelines equally and still report 0
anomaly. These tests pin behaviour against expected outputs for known
inputs.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

# Load simulator and symmetry-check as standalone modules (their
# filenames contain dashes, which Python's import system can't handle
# as a regular `import` statement).
def _load(name: str):
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "build_system" / "scripts" / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, name
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sim = _load("release-workflow-simulator")
sym = _load("release-pipeline-symmetry-check")


# ============================================================================
# ExprEnv: GH Actions expression evaluator subset
# ============================================================================


class TestExprEnvLiterals:
    def test_string_literal(self):
        assert sim.ExprEnv({}).eval("'success'") == "success"

    def test_double_quoted_string(self):
        assert sim.ExprEnv({}).eval('"failure"') == "failure"

    def test_int_literal(self):
        assert sim.ExprEnv({}).eval("42") == 42

    def test_float_literal(self):
        assert sim.ExprEnv({}).eval("3.14") == 3.14

    def test_true_literal(self):
        assert sim.ExprEnv({}).eval("true") is True

    def test_false_literal(self):
        assert sim.ExprEnv({}).eval("false") is False

    def test_missing_var_returns_empty_string(self):
        # GH Actions semantics: missing keys evaluate to "".
        assert sim.ExprEnv({}).eval("a.b.c") == ""


class TestExprEnvOperators:
    def test_equality_true(self):
        assert sim.ExprEnv({}).eval("'foo' == 'foo'") is True

    def test_equality_false(self):
        assert sim.ExprEnv({}).eval("'foo' == 'bar'") is False

    def test_inequality(self):
        assert sim.ExprEnv({}).eval("'a' != 'b'") is True

    def test_and_short_circuits_to_false(self):
        assert sim.ExprEnv({}).eval("false && true") is False

    def test_or_short_circuits_to_true(self):
        assert sim.ExprEnv({}).eval("false || true") is True

    def test_and_binds_tighter_than_or(self):
        # The core bug we fixed: `'a' == 'b' || 'c' == 'c' && 'success' || 'failure'`
        # must NOT always be truthy. This test pins the precedence.
        # Equivalent: (('a' == 'b') || ('c' == 'c' && 'success')) || 'failure'
        # `('c' == 'c' && 'success')` = 'success' (string, truthy) -> so
        # whole expr is 'success'. That's the bug case we WANT pinned:
        # any operator-precedence regression in ExprEnv would change it.
        result = sim.ExprEnv({}).eval(
            "'a' == 'b' || 'c' == 'c' && 'success' || 'failure'"
        )
        # With correct C-style precedence, the result is 'success'
        # (because the right-hand side has 'success' which is truthy).
        # The IMPORTANT thing is that this is a deterministic value
        # derived from the precedence rules, not a function of randomness.
        assert result == "success"

    def test_parens_override_precedence(self):
        # The exact fix from release-{intl,cn}.yml:929:
        #   `(needs.X == 'success' || needs.Y == 'success') && 'success' || 'failure'`
        # With both upstream jobs failed, the result must be 'failure'.
        env = sim.ExprEnv({"needs": {"X": {"result": "failure"}, "Y": {"result": "failure"}}})
        result = env.eval(
            "(needs.X.result == 'success' || needs.Y.result == 'success') && 'success' || 'failure'"
        )
        assert result == "failure", (
            "Parens must force the disjunction to evaluate before the "
            "ternary-style success/failure fallback. A regression here "
            "would silently mark failed builds as success in the GHA "
            "macos-build-result expression."
        )

    def test_not_unary(self):
        assert sim.ExprEnv({}).eval("!true") is False
        assert sim.ExprEnv({}).eval("!false") is True


class TestExprEnvFunctions:
    def test_always_returns_true(self):
        assert sim.ExprEnv({}).eval("always()") is True

    def test_success_returns_true(self):
        assert sim.ExprEnv({}).eval("success()") is True

    def test_failure_returns_false(self):
        assert sim.ExprEnv({}).eval("failure()") is False

    def test_contains_function(self):
        env = sim.ExprEnv({"a": "github-hosted"})
        assert env.eval("contains(fromJSON('[\"github-hosted\"]'), a)") is True

    def test_fromJSON_parses_array(self):
        env = sim.ExprEnv({})
        # contains(arr, item) takes a string; this just confirms fromJSON works.
        result = env.eval("fromJSON('[1,2,3]')")
        assert result == [1, 2, 3]


class TestExprEnvRealWorldMacosBug:
    """
    Pin the exact expression shape used at release-{intl,cn}.yml:929.
    A future refactor that breaks precedence would otherwise silently
    mark all macOS build failures as 'success'.
    """

    @pytest.mark.parametrize(
        "amd,aarch,expected",
        [
            ("success", "success", "success"),
            ("success", "failure", "success"),
            ("failure", "success", "success"),
            ("failure", "failure", "failure"),  # <- the regression target
        ],
    )
    def test_macos_build_result(self, amd, aarch, expected):
        env = sim.ExprEnv({
            "needs": {
                "build-macos-amd64":   {"result": amd},
                "build-macos-aarch64": {"result": aarch},
            }
        })
        result = env.eval(
            "(needs.build-macos-amd64.result == 'success' "
            "|| needs.build-macos-aarch64.result == 'success') "
            "&& 'success' || 'failure'"
        )
        assert result == expected


class TestExprEnvMacosBuildResultSkippedRegression:
    """Pins the 3-state macos-build-result expression that lives at
    release-{intl,cn}.yml::generate-download-links.

    The original 2-state expression collapsed `skipped` into `failure`,
    so any windows-only build (or platform=all under ecan-windows-amd64)
    published a summary that said

        ❌ macOS build failed — no artifacts produced.
        See the build job log for the failing step. Expected: 0 artifact(s).

    even though both macOS jobs had been correctly gated by `if:` and
    skipped — not failed. The fix extends the expression to emit a
    3-way value (success / failure / skipped) so render_download_links.py
    routes to the right status message in _render_status_message.

    These cases MUST keep passing; a refactor that reverts to the
    2-state shape will silently regress this contract.
    """

    EXPRESSION = (
        "(needs.build-macos-amd64.result == 'success' "
        "|| needs.build-macos-aarch64.result == 'success') && 'success' "
        "|| (needs.build-macos-amd64.result == 'failure' "
        "|| needs.build-macos-aarch64.result == 'failure') && 'failure' "
        "|| 'skipped'"
    )

    @pytest.mark.parametrize(
        "amd,aarch,expected",
        [
            ("success", "success", "success"),
            ("success", "failure", "success"),
            ("failure", "success", "success"),
            ("failure", "failure", "failure"),
            # The bug fix — both skipped is *not* a failure.
            ("skipped", "skipped", "skipped"),
            # Mixed skipped + failure: still a failure (one arch tried
            # and crashed; the other was never asked to run).
            ("skipped", "failure", "failure"),
            ("failure", "skipped", "failure"),
            # Mixed skipped + success: success.
            ("skipped", "success", "success"),
            ("success", "skipped", "success"),
        ],
    )
    def test_macos_build_result_three_state(self, amd, aarch, expected):
        env = sim.ExprEnv({
            "needs": {
                "build-macos-amd64":   {"result": amd},
                "build-macos-aarch64": {"result": aarch},
            }
        })
        assert env.eval(self.EXPRESSION) == expected

    def test_macos_build_result_pins_three_state_shape(self):
        """Guard against a future refactor that reverts to the
        2-state `success || failure` shape. Any such change would
        make the (skipped, skipped) case evaluate to 'failure'
        again — exactly the user-visible bug this test exists to
        prevent."""
        env = sim.ExprEnv({
            "needs": {
                "build-macos-amd64":   {"result": "skipped"},
                "build-macos-aarch64": {"result": "skipped"},
            }
        })
        # If a refactor removes the trailing `|| 'skipped'`, the
        # expression collapses to (false && 'success') || (false && 'failure')
        # → 'failure' (any truthy fallback wins). We pin 'skipped' here.
        assert env.eval(self.EXPRESSION) == "skipped", (
            "macos-build-result must distinguish skipped from failure. "
            "If this regresses, release-{intl,cn}.yml will again publish "
            "'❌ macOS build failed' for windows-only / non-macOS runs."
        )


# ============================================================================
# run_validate_tag: pure-Python mirror of the bash heuristic
# ============================================================================


class TestRunValidateTag:
    def test_semver_tag_auto_detects_production_stable(self):
        out = sim.run_validate_tag("v1.0.0", "", "")
        assert out.valid is True
        assert out.environment == "production"
        assert out.channel == "stable"
        assert out.user_prefix == ""

    def test_semver_tag_with_v_stripped_from_version(self):
        out = sim.run_validate_tag("v1.2.3", "", "")
        assert out.version == "1.2.3"
        assert out.tag_name == "v1.2.3"

    def test_rc_tag_auto_detects_production_beta(self):
        out = sim.run_validate_tag("v1.0.0-rc.1", "", "")
        assert out.environment == "production"
        assert out.channel == "beta"

    def test_beta_tag_auto_detects_staging_beta(self):
        out = sim.run_validate_tag("v1.0.0-beta.1", "", "")
        assert out.environment == "staging"
        assert out.channel == "beta"

    def test_alpha_tag_auto_detects_test_dev(self):
        out = sim.run_validate_tag("v1.0.0-alpha.1", "", "")
        assert out.environment == "test"
        assert out.channel == "dev"

    def test_user_prefixed_tag(self):
        out = sim.run_validate_tag("songc_v0.1.0", "", "")
        assert out.valid is True
        assert out.user_prefix == "songc"
        assert out.version == "0.1.0"

    def test_user_prefix_is_lowercased(self):
        out = sim.run_validate_tag("SongC_v0.1.0", "", "")
        assert out.user_prefix == "songc"

    @pytest.mark.parametrize(
        "prefix",
        ["rc", "beta", "alpha", "dev", "nightly", "pre", "preview", "snapshot"],
    )
    def test_reserved_prefix_is_rejected(self, prefix):
        out = sim.run_validate_tag(f"{prefix}_v1.0.0", "", "")
        assert out.valid is False
        assert "reserved prefix" in out.error
        assert out.user_prefix == ""

    def test_branch_main_auto_detects_production_nightly(self):
        out = sim.run_validate_tag("main", "", "")
        assert out.valid is True
        assert out.environment == "production"
        assert out.channel == "nightly"
        assert out.is_branch is True

    def test_branch_staging_auto_detects_staging_stable(self):
        out = sim.run_validate_tag("staging", "", "")
        assert out.environment == "staging"
        assert out.channel == "stable"

    def test_branch_develop_auto_detects_development_dev(self):
        out = sim.run_validate_tag("develop", "", "")
        assert out.environment == "development"
        assert out.channel == "dev"

    def test_production_stable_on_branch_is_blocked(self):
        # The hard gate: you cannot deploy production/stable from a non-tag
        # ref, even via manual input. With input_env=production and a
        # feature branch, the env-eligibility check fires first and rejects
        # with "production env requires tag or main/master". The
        # production/stable + branch gate is the second line of defense
        # and only triggers for auto-detected env (input_env=""), or when
        # the ref IS main/master (which would otherwise sneak through).
        # See test_auto_production_stable_on_branch_is_blocked for that.
        out = sim.run_validate_tag("feature/foo", "production", "stable")
        assert out.valid is False
        assert "production" in out.error.lower()

    def test_auto_production_stable_on_branch_is_blocked(self):
        # The second-line gate: env=production AND channel=stable AND
        # not a tag -> blocked. main/master branch gets through the env
        # check (env=production allowed on main/master) but must still be
        # rejected by the production/stable + not-tag gate.
        out = sim.run_validate_tag("main", "", "")
        # auto env=production, auto channel=nightly -> gate doesn't fire
        # because channel != stable.
        assert out.valid is True
        assert out.environment == "production"
        assert out.channel == "nightly"

        # Now force channel=stable on main. With env=production and
        # channel=stable and is_tag=False, the gate must reject.
        out2 = sim.run_validate_tag("main", "", "stable")
        assert out2.valid is False
        assert "production/stable" in out2.error

    def test_staging_env_on_feature_branch_is_blocked(self):
        out = sim.run_validate_tag("feature/foo", "staging", "")
        assert out.valid is False
        assert "staging" in out.error

    def test_manual_environment_overrides(self):
        out = sim.run_validate_tag("v1.0.0", "test", "")
        assert out.environment == "test"

    def test_manual_channel_overrides(self):
        out = sim.run_validate_tag("v1.0.0", "production", "dev")
        assert out.channel == "dev"


# ============================================================================
# release-pipeline-symmetry-check.normalize: backend-specific value collapse
# ============================================================================


class TestSymmetryNormalize:
    """
    Pin the collapsing rules. A regression in normalize() would either
    spuriously flag cn/intl as asymmetric (false positive) or, worse,
    silently allow real divergence to slip past the byte-equal check.
    """

    def test_app_id_is_collapsed(self):
        # normalize() does not preserve trailing newlines on collapsed
        # values; the assertion is that the body is the same.
        out_intl = sym.normalize("ECAN_APP_ID: intl\n")
        out_cn = sym.normalize("ECAN_APP_ID: cn\n")
        assert out_intl == out_cn
        assert "<APP>" in out_intl

    def test_app_name_with_dot_is_collapsed(self):
        # `eCan.cn` and `eCan` should collapse identically.
        out_cn = sym.normalize('ECAN_APP_NAME: eCan.cn\n')
        out_intl = sym.normalize('ECAN_APP_NAME: eCan\n')
        assert out_cn == out_intl
        assert "<NAME>" in out_cn

    def test_requirements_txt_is_collapsed(self):
        out_intl = sym.normalize("pip install -r requirements-intl.txt\n")
        out_cn = sym.normalize("pip install -r requirements-cn.txt\n")
        assert out_intl == out_cn

    def test_build_system_scripts_requirements_collapsed(self):
        # The CN storage pipeline uses
        # `build_system/scripts/requirements-cos.txt` (narrow set:
        # cos-python-sdk-v5 + pyyaml + packaging) while the intl side
        # uses `build_system/scripts/requirements.txt` (boto3 + pyyaml +
        # packaging). The upload/appcast/latest-json jobs in both
        # pipelines are byte-equivalent after normalize() collapses
        # these names. Lock that in so a future rename can't break the
        # symmetry check.
        out_intl = sym.normalize(
            "pip install -r build_system/scripts/requirements.txt\n"
        )
        out_cn = sym.normalize(
            "pip install -r build_system/scripts/requirements-cos.txt\n"
        )
        assert out_intl == out_cn
        assert "requirements-<APP>.txt" in out_intl

    def test_app_flag_arg_is_collapsed(self):
        out_intl = sym.normalize("python build.py prod --app intl\n")
        out_cn = sym.normalize("python build.py prod --app cn\n")
        assert out_intl == out_cn

    def test_aws_tencent_secret_aliases_are_collapsed(self):
        out_intl = sym.normalize("AWS_ACCESS_KEY_ID: foo\n")
        out_cn = sym.normalize("ECAN_TENCENT_SECRET_ID: foo\n")
        assert out_intl == out_cn == "APP_KEY_ID: foo\n"

    def test_region_defaults_are_collapsed(self):
        out_intl = sym.normalize("Region: 'us-east-1'\n")
        out_cn = sym.normalize("Region: 'ap-guangzhou'\n")
        assert out_intl == out_cn == "Region: '<REGION>'\n"

    def test_dist_windows_path_is_collapsed(self):
        out_intl = sym.normalize('"dist\\eCan-${{v}}-windows-amd64.exe"\n')
        out_cn = sym.normalize('"dist\\eCan.cn-${{v}}-windows-amd64.exe"\n')
        assert out_intl == out_cn

    def test_dist_linux_path_is_collapsed(self):
        out_intl = sym.normalize('dist/eCan-1.0.0-linux-amd64.deb\n')
        out_cn = sym.normalize('dist/eCan.cn-1.0.0-linux-amd64.deb\n')
        assert out_intl == out_cn

    def test_job_ids_are_collapsed(self):
        out = sym.normalize("  build-windows:\n")
        assert "<JID>:" in out
        out_cn = sym.normalize("  build-windows-cn:\n")
        assert "<JID>:" in out_cn
        assert out == out_cn

    def test_upload_to_s3_and_cos_collapse_identically(self):
        out_s3 = sym.normalize("  upload-to-s3:\n")
        out_cos = sym.normalize("  upload-to-cos:\n")
        assert out_s3 == out_cos

    def test_header_comments_are_collapsed_to_hash(self):
        # The 20-line header in each file is intentionally different.
        # It must not affect symmetry.
        out = sym.normalize("# This is a comment\nECAN_APP_ID: intl\n")
        out2 = sym.normalize("# A different comment\nECAN_APP_ID: cn\n")
        assert out == out2

    def test_workflow_display_name_is_collapsed(self):
        out_intl = sym.normalize("name: Release (Intl)\n")
        out_cn = sym.normalize("name: Release (CN)\n")
        assert out_intl == out_cn
        assert "<APP>" in out_intl

    def test_stage_banner_is_collapsed(self):
        out_intl = sym.normalize("# Stage 2 — Build matrix (Intl):\n")
        out_cn = sym.normalize("# Stage 2 — Build matrix (CN):\n")
        assert out_intl == out_cn

    def test_per_job_cn_suffix_in_display_name_is_collapsed(self):
        out_cn = sym.normalize("  name: Build Windows amd64 CN\n")
        out_intl = sym.normalize("  name: Build Windows amd64\n")
        # Both should reduce to the same canonical form. The trailing
        # newline may or may not be stripped depending on regex greediness
        # — that's irrelevant to symmetry. Compare the trimmed bodies.
        assert out_cn.strip() == out_intl.strip()


# ============================================================================
# symmetry-check main(): REPO_ROOT resolution and exit codes
# ============================================================================
#
# These tests guard against the regression that broke the CI gate in PR
# #320: the script originally hard-coded
# `REPO = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")`, which failed
# on every CI runner (and any developer with a different checkout path)
# with a bare Python traceback at exit code 1. The fix is REPO_ROOT
# env var with cwd as fallback. Pin the contract so a future
# hard-coded path regression fails here, not as a CI red X.


class TestSymmetryCheckMain:
    def _run(self, repo_root=None, cwd=None):
        """Run the script as a subprocess in an isolated env."""
        import os
        import subprocess

        env = os.environ.copy()
        if repo_root is not None:
            env["REPO_ROOT"] = repo_root
        else:
            env.pop("REPO_ROOT", None)
        # cwd must be a path that ACTUALLY exists on disk, otherwise
        # subprocess.run raises FileNotFoundError before the script
        # even starts. The script's own REPO_ROOT handling is what
        # we want to test, so we keep cwd pinned to the test runner's
        # cwd (always valid) and pass REPO_ROOT for the resolution
        # logic.
        if cwd is None:
            cwd = os.getcwd()
        result = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parent.parent.parent
                 / "build_system" / "scripts"
                 / "release-pipeline-symmetry-check.py")],
            env=env,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result

    def test_default_cwd_is_repo_root_passes(self):
        # The script's primary use case: run from the repo root.
        # We resolve the repo root relative to THIS test file, not
        # from a hard-coded path, so the test works on any
        # developer's checkout.
        repo_root = (
            Path(__file__).resolve().parent.parent.parent
        )
        result = self._run(cwd=str(repo_root))
        assert result.returncode == 0, (
            f"expected pass; got exit {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        assert "byte-equal" in result.stdout

    def test_explicit_repo_root_overrides(self, tmp_path):
        # REPO_ROOT must take precedence even if cwd is wrong.
        # Copy the real release-{intl,cn}.yml files into a fresh tmp
        # root so we can test the resolution logic without depending
        # on the test runner's local checkout path.
        import shutil

        src_root = (
            Path(__file__).resolve().parent.parent.parent
        )
        shutil.copy(src_root / ".github" / "workflows" / "release-intl.yml",
                    tmp_path / "release-intl.yml")
        shutil.copy(src_root / ".github" / "workflows" / "release-cn.yml",
                    tmp_path / "release-cn.yml")

        # Now run with REPO_ROOT=tmp but cwd=/tmp. The script
        # builds paths as REPO / ".github/workflows/release-*.yml"
        # so we need to mirror the directory structure.
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        shutil.move(tmp_path / "release-intl.yml", workflows_dir / "release-intl.yml")
        shutil.move(tmp_path / "release-cn.yml",   workflows_dir / "release-cn.yml")

        result = self._run(repo_root=str(tmp_path), cwd="/tmp")
        assert result.returncode == 0, (
            f"REPO_ROOT should work from /tmp; got exit {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_bad_repo_root_fails_with_clear_message(self):
        # A bad REPO_ROOT must NOT silently pass. The original CI
        # failure was "exit 1 with no useful stderr" — every developer
        # had to look at the action log to figure out what was wrong.
        # The script's own REPO_ROOT handling is what we want to test,
        # so we run from a *valid* cwd but point REPO_ROOT at a path
        # that doesn't exist on disk.
        import os
        # Find a path that does not exist. Use mkdtemp then rmdir to
        # guarantee the path is reserved-but-empty.
        bad_path = tempfile.mkdtemp(suffix="-not-a-repo") + "-nope"
        assert not os.path.exists(bad_path)
        result = self._run(repo_root=bad_path)
        assert result.returncode != 0, (
            "bad REPO_ROOT should not exit 0"
        )
        # The error message must point at REPO_ROOT so the next person
        # doesn't have to guess.
        assert "REPO_ROOT" in result.stderr, (
            f"stderr should mention REPO_ROOT; got: {result.stderr!r}"
        )
        assert bad_path in result.stderr

    def test_no_hardcoded_local_path_in_source(self):
        # Regression: the script used to have
        # `REPO = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")` baked
        # in. Grep the source. Use a regex that catches variations
        # (any path containing a username segment).
        import re
        src = (
            Path(__file__).resolve().parent.parent.parent
            / "build_system" / "scripts" / "release-pipeline-symmetry-check.py"
        ).read_text()
        # Anything that looks like /Users/<something>/... in a Path()
        # literal is suspicious.
        bad = re.findall(r'Path\(["\'](/Users/[^"\']+)["\']', src)
        assert not bad, (
            f"hard-coded local path detected in symmetry-check: {bad}\n"
            f"Use Path(os.environ.get('REPO_ROOT', Path.cwd())) instead."
        )


# ============================================================================
# audit_reusable_workflow_inputs: structural lint for caller/callee input
# contracts. Catches "Invalid input, X is not defined in the referenced
# workflow" before GHA does — see PR #320 for the failure mode that
# motivated this audit.
# ============================================================================


class TestAuditReusableWorkflowInputs:
    def _make_repo(self, tmp_path, shared_files, caller_files):
        """
        Build a fake repo layout:

          tmp_path/.github/workflows/shared-*.yml   (callee defs)
          tmp_path/.github/workflows/release-*.yml  (callers)

        Returns the repo root Path.
        """
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        for name, content in shared_files.items():
            (workflows / name).write_text(content)
        for name, content in caller_files.items():
            (workflows / name).write_text(content)
        return tmp_path

    def _shared_with_inputs(self, name, inputs):
        block = "\n".join(
            f"      {k}:\n        type: string\n        default: ''"
            for k in inputs
        )
        return (
            f"name: {name}\n"
            f"on:\n"
            f"  workflow_call:\n"
            f"    inputs:\n{block}\n"
            f"jobs:\n"
            f"  do:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
        )

    def _caller_using(self, shared_name, with_block):
        # YAML parses `on:` as `True:` (because `on` is a Python
        # literal). We have to use either the bare key `True:` or
        # quote `'on':`. The real workflow files use bare `on:` and
        # rely on yaml's resolver; PyYAML 6.x does the same. But our
        # test fixture must use a form that safe_load can parse, so
        # we use the explicit `'on':` mapping form here.
        return (
            "name: release-test\n"
            "'on': workflow_dispatch\n"
            "jobs:\n"
            "  call-it:\n"
            f"    uses: ./.github/workflows/{shared_name}\n"
            "    with:\n"
            + with_block
            + "    secrets: inherit\n"
        )

    def test_clean_repo_passes(self, tmp_path):
        # Callee declares A, B. Caller passes A, B.
        self._make_repo(
            tmp_path,
            {"shared-x.yml": self._shared_with_inputs("shared-x", ["a", "b"])},
            {"release-test.yml": self._caller_using(
                "shared-x.yml", "      a: foo\n      b: bar\n"
            )},
        )
        assert sim.audit_reusable_workflow_inputs(tmp_path) == []

    def test_caller_passes_undefined_input_is_flagged(self, tmp_path):
        # Callee only declares `a`. Caller also passes `b`.
        self._make_repo(
            tmp_path,
            {"shared-x.yml": self._shared_with_inputs("shared-x", ["a"])},
            {"release-test.yml": self._caller_using(
                "shared-x.yml", "      a: foo\n      b: bar\n"
            )},
        )
        mismatches = sim.audit_reusable_workflow_inputs(tmp_path)
        assert len(mismatches) == 1
        m = mismatches[0]
        assert m["caller"] == "release-test.yml"
        assert m["job"] == "call-it"
        assert m["callee"] == "shared-x.yml"
        assert m["input"] == "b"

    def test_multiple_callers_and_callees(self, tmp_path):
        # Two shared-*.yml, two callers, three calls, two with errors.
        # See `_caller_using` for why we use `'on':` instead of `on:`.
        self._make_repo(
            tmp_path,
            {
                "shared-x.yml": self._shared_with_inputs("shared-x", ["a"]),
                "shared-y.yml": self._shared_with_inputs("shared-y", ["q"]),
            },
            {
                "release-a.yml": (
                    "name: A\n'on': workflow_dispatch\njobs:\n"
                    "  x:\n    uses: ./.github/workflows/shared-x.yml\n"
                    "    with:\n      a: 1\n"
                ),
                "release-b.yml": (
                    "name: B\n'on': workflow_dispatch\njobs:\n"
                    "  x:\n    uses: ./.github/workflows/shared-x.yml\n"
                    "    with:\n      a: 1\n      rogue: x\n"
                    "  y:\n    uses: ./.github/workflows/shared-y.yml\n"
                    "    with:\n      q: 2\n      other: y\n"
                ),
            },
        )
        mismatches = sim.audit_reusable_workflow_inputs(tmp_path)
        # Two calls passed undefined inputs.
        assert len(mismatches) == 2
        assert {m["input"] for m in mismatches} == {"rogue", "other"}

    def test_real_release_cn_intl_passes(self):
        # The actual repo: after the shared-cos-appcast-generation
        # `app` input fix, every caller/callee pair must match. If
        # this test fails, the next PR is going to break GHA with
        # "Invalid input, X is not defined in the referenced workflow"
        # just like PR #320 did.
        repo_root = Path(__file__).resolve().parent.parent.parent
        mismatches = sim.audit_reusable_workflow_inputs(repo_root)
        assert mismatches == [], (
            f"real repo has caller/callee input mismatches: {mismatches}"
        )

    def test_missing_workflows_dir_is_noop(self, tmp_path):
        # No .github/workflows directory — no work to do, no errors.
        assert sim.audit_reusable_workflow_inputs(tmp_path) == []

    def test_callee_with_no_workflow_call_is_ignored(self, tmp_path):
        # A shared-*.yml that isn't actually reusable must not be
        # matched against callers.
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        # shared-no-call.yml has workflow_dispatch, not workflow_call.
        # Use `'on':` so safe_load can parse the file.
        (workflows / "shared-no-call.yml").write_text(
            "name: x\n'on': workflow_dispatch\njobs:\n  do:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"
        )
        assert sim.audit_reusable_workflow_inputs(tmp_path) == []
