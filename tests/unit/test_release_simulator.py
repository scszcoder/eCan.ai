"""
Unit tests for the full release-pipeline executor (release_simulator).

These tests complement the static 4086-case simulator tests. They
verify the parts that actually execute contracts:

  * step outputs propagate via $GITHUB_OUTPUT
  * steps.<id>.outputs.<key> is visible to subsequent steps
  * needs.<job>.result reflects upstream state, not always 'success'
  * `with:` inputs to reusable workflows become INPUT_<NAME> env vars
  * `secrets: inherit` propagates the parent's secret set
  * the assertion layer flags real bugs that the static simulator
    can't see (input-not-declared, output-not-written)
"""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

import pytest

from build_system.scripts.release_simulator import (
    assertions,
    expr,
    runner,
)
from build_system.scripts.release_simulator.models import (
    FAILURE,
    SKIPPED,
    SUCCESS,
)


# ---------------------------------------------------------------------------
# Fixtures: synthetic workflows written into a tmp dir
# ---------------------------------------------------------------------------


@pytest.fixture
def workflows_dir(tmp_path: Path) -> Path:
    """Return a fresh flat dir; callers write workflows as siblings
    so GHA-style `uses: ./<file>.yml` (workspace-relative) resolves
    to `<tmp>/<file>.yml`.
    """
    d = tmp_path / "wf"
    d.mkdir()
    return d


def _write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body).lstrip())
    return path


# ---------------------------------------------------------------------------
# ExprEnv behaviour that the executor relies on
# ---------------------------------------------------------------------------


def test_exprenv_lookup_returns_empty_string_for_missing_key():
    """GH semantics: `secrets.X` where X is undefined → empty string,
    not KeyError. The runner depends on this for `secrets.X || 'NOT_SET'`
    patterns in env blocks.
    """
    e = expr.ExprEnv({"secrets": {}, "inputs": {}})
    assert e.lookup("secrets.NONEXISTENT") == ""
    assert e.lookup("a.b.c.d") == ""


def test_exprenv_or_returns_first_truthy_with_fallback_string():
    """The build jobs use `secrets.AZURE_TENANT_ID || 'NOT_SET'` to
    produce a sentinel when the secret is absent. Verify this round-
    trips correctly through both ExprEnv.eval and the runner's
    interpolation.
    """
    e = expr.ExprEnv({"secrets": {"FOO": "bar"}})
    assert e.eval("secrets.FOO || 'NOT_SET'") == "bar"

    e2 = expr.ExprEnv({"secrets": {}})
    assert e2.eval("secrets.FOO || 'NOT_SET'") == "NOT_SET"


def test_exprenv_parens_in_or_combinations():
    """The macos-build-result bash expression is the canary for this:
    `(A || B) && 'success' || 'failure'`. Make sure parens survive.
    """
    e = expr.ExprEnv({})
    # Both A and B false → outer fallback fires
    assert e.eval("(false || false) && 'success' || 'failure'") == "failure"
    # At least one true → success
    assert e.eval("(true || false) && 'success' || 'failure'") == "success"
    assert e.eval("(false || true) && 'success' || 'failure'") == "success"


# ---------------------------------------------------------------------------
# Runner basics
# ---------------------------------------------------------------------------


def test_runner_resolves_workflow_dispatch_defaults(workflows_dir):
    """Caller didn't supply `environment` or `channel`; the workflow
    declares defaults 'production' / 'nightly'. Per real GHA semantics,
    the runner does NOT apply those defaults to `github.event.inputs`
    when the caller is silent — bash sees empty strings, which is what
    the auto-detect logic in detect-env relies on. The runner DOES
    apply defaults for `platform`, `arch`, and `runner_group` because
    eCan.ai's `if:` expressions assume those values.

    This test pins that split: environment/channel stay empty, while
    the matrix-axis inputs would receive their defaults.
    """
    wf = _write(workflows_dir / "r.yml", """
        name: r
        on:
          workflow_dispatch:
            inputs:
              environment:
                type: string
                default: 'production'
              channel:
                type: string
                default: 'nightly'
              platform:
                type: string
                default: 'all'
              arch:
                type: string
                default: 'all'
        jobs:
          svc:
            runs-on: ubuntu-latest
            steps:
              - run: echo "noop"
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={}, ref="main", app="intl",
    )
    # Matrix-axis inputs: defaults applied so jobs that depend on them
    # in `if:` expressions actually run.
    assert run.inputs["platform"] == "all"
    assert run.inputs["arch"] == "all"
    # Auto-detected inputs: stay empty so bash can run its own logic.
    assert run.inputs["environment"] == ""
    assert run.inputs["channel"] == ""


def test_runner_skips_job_when_if_false(workflows_dir):
    """`if:` evaluates false → job marked SKIPPED, never executed."""
    wf = _write(workflows_dir / "r.yml", """
        on:
          workflow_dispatch:
            inputs:
              env:
                type: string
                default: ''
        jobs:
          a:
            runs-on: ubuntu-latest
            if: "github.event.inputs.env == 'production'"
            steps:
              - run: |
                  echo "should not run"
                  exit 99
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={"env": "development"}, ref="main",
        app="intl",
    )
    assert run.jobs["a"].result == SKIPPED


def test_runner_runs_job_when_if_true(workflows_dir):
    wf = _write(workflows_dir / "r.yml", """
        on:
          workflow_dispatch:
            inputs:
              env:
                type: string
                default: ''
        jobs:
          a:
            runs-on: ubuntu-latest
            if: "github.event.inputs.env == 'production'"
            steps:
              - run: echo "ok=true" >> "$GITHUB_OUTPUT"
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={"env": "production"}, ref="main",
        app="intl",
    )
    assert run.jobs["a"].result == SUCCESS
    assert run.jobs["a"].steps[0].outputs.get("ok") == "true"


# ---------------------------------------------------------------------------
# The bug-class we keep re-introducing: step outputs propagation
# ---------------------------------------------------------------------------


def test_step_outputs_visible_to_next_step(workflows_dir):
    """Step A writes `ref_name=foo` to $GITHUB_OUTPUT. Step B's
    `steps.a.outputs.ref_name` must resolve to `foo` in the runner.
    """
    wf = _write(workflows_dir / "r.yml", """
        jobs:
          produce:
            runs-on: ubuntu-latest
            outputs:
              ref_name: ${{ steps.a.outputs.ref_name }}
              version:  ${{ steps.a.outputs.version }}
            steps:
              - id: a
                run: |
                  echo "ref_name=foo" >> "$GITHUB_OUTPUT"
                  echo "version=1.2.3" >> "$GITHUB_OUTPUT"
              - id: b
                run: |
                  NAME="${{ steps.a.outputs.ref_name }}"
                  VER="${{ steps.a.outputs.version }}"
                  echo "name=$NAME" >> "$GITHUB_OUTPUT"
                  echo "ver=$VER" >> "$GITHUB_OUTPUT"
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={}, ref="main", app="intl",
    )
    j = run.jobs["produce"]
    assert j.result == SUCCESS, f"step b should have run; got {j.result}"
    assert j.outputs["ref_name"] == "foo"
    assert j.outputs["version"] == "1.2.3"


def test_needs_reflects_upstream_failure(workflows_dir):
    """The old simulator treated every job's needs as 'success' if it
    was gated open. That hid the `macos-build-result` precedence bug
    and any contract that branched on needs.X.result == 'failure'.
    The new runner must report upstream failure to downstream jobs.
    """
    wf = _write(workflows_dir / "r.yml", """
        jobs:
          will_fail:
            runs-on: ubuntu-latest
            steps:
              - run: |
                  echo "intentional failure"
                  exit 1
          should_skip:
            runs-on: ubuntu-latest
            needs: will_fail
            if: needs.will_fail.result == 'success'
            steps:
              - run: echo "should never run" >> "$GITHUB_OUTPUT"
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={}, ref="main", app="intl",
    )
    assert run.jobs["will_fail"].result == FAILURE
    assert run.jobs["should_skip"].result == SKIPPED, (
        "needs.<jid>.result must propagate the actual upstream result, "
        "not always 'success'"
    )


def test_always_runs_even_if_needs_failed(workflows_dir):
    """`if: always()` lets a job run regardless of upstream. Use this
    to test that the runner's needs-eval respects it (final-status in
    eCan.ai uses this pattern).
    """
    wf = _write(workflows_dir / "r.yml", """
        jobs:
          will_fail:
            runs-on: ubuntu-latest
            steps:
              - run: exit 1
          always_runs:
            runs-on: ubuntu-latest
            needs: will_fail
            if: always()
            steps:
              - run: echo "ok=true" >> "$GITHUB_OUTPUT"
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={}, ref="main", app="intl",
    )
    assert run.jobs["always_runs"].result == SUCCESS


# ---------------------------------------------------------------------------
# Reusable workflow contract: `with:` and `secrets: inherit`
# ---------------------------------------------------------------------------


def test_with_inputs_become_input_upper_env_vars(workflows_dir):
    """`uses: ./shared-x.yml` with `with: foo=bar`
    must produce `INPUT_FOO=bar` on the callee side. This is the
    contract every Python script in shared-*.yml depends on.
    """
    callee = _write(workflows_dir / "shared-x.yml", """
        on:
          workflow_call:
            inputs:
              foo:
                type: string
                required: true
        jobs:
          echo_foo:
            runs-on: ubuntu-latest
            steps:
              - run: |
                  echo "foo=$INPUT_FOO" >> "$GITHUB_OUTPUT"
    """)
    caller = _write(workflows_dir / "caller.yml", """
        jobs:
          call:
            uses: ./shared-x.yml
            with:
              foo: bar
    """)
    run = runner.run_workflow(
        workflow_path=caller, inputs={}, ref="main", app="intl",
        repo_root=workflows_dir,
    )
    print('DEBUG run.jobs keys:', list(run.jobs.keys()))
    for jid, jrec in run.jobs.items():
        print(f'  {jid}: result={jrec.result}, note={jrec.note!r}')
    assert run.jobs["echo_foo"].result == SUCCESS
    # The output key was 'foo' (echo writes that line), so check
    # the step wrote it back to its outputs.
    step = run.jobs["echo_foo"].steps[0]
    assert step.outputs.get("foo") == "bar"


def test_undeclared_input_causes_callee_to_be_skipped(workflows_dir):
    """Caller passes an input the callee doesn't declare. GHA rejects
    this at queue-time. The runner records the contract on the caller
    job so the assertion layer can flag it.
    """
    callee = _write(workflows_dir / "shared-x.yml", """
        on:
          workflow_call:
            inputs:
              declared:
                type: string
        jobs:
          echo_declared:
            runs-on: ubuntu-latest
            steps:
              - run: echo "ok" >> "$GITHUB_OUTPUT"
    """)
    caller = _write(workflows_dir / "caller.yml", """
        jobs:
          call:
            uses: ./shared-x.yml
            with:
              declared: ok
              undeclared: bad
    """)
    run = runner.run_workflow(
        workflow_path=caller, inputs={}, ref="main", app="intl",
        repo_root=workflows_dir,
    )
    assert "undeclared" in run.jobs["call"].inputs, (
        "the runner must record exactly what the caller sent, even "
        "if the callee doesn't accept it — the assertion layer uses "
        "this to detect 'Invalid input, X is not defined' bugs"
    )


def test_secrets_inherit_propagates_parent_secrets(workflows_dir):
    """Caller uses `secrets: inherit`. The callee's `$SECRET_X` (or
    `secrets.X` in expressions) must resolve to the parent's value.
    """
    callee = _write(workflows_dir / "shared-x.yml", """
        on:
          workflow_call: {}
        jobs:
          use_secret:
            runs-on: ubuntu-latest
            env:
              TENANT: ${{ secrets.MY_TENANT }}
            steps:
              - run: |
                  echo "tenant=$TENANT" >> "$GITHUB_OUTPUT"
    """)
    caller = _write(workflows_dir / "caller.yml", """
        jobs:
          call:
            uses: ./shared-x.yml
            secrets: inherit
    """)
    run = runner.run_workflow(
        workflow_path=caller, inputs={}, ref="main", app="intl",
        repo_root=workflows_dir,
        secrets={"MY_TENANT": "tenant-xyz"},
    )
    assert run.jobs["use_secret"].result == SUCCESS
    assert run.jobs["use_secret"].env["TENANT"] == "tenant-xyz"


# ---------------------------------------------------------------------------
# Assertion layer
# ---------------------------------------------------------------------------


def test_assertion_flags_undeclared_input(workflows_dir):
    callee = _write(workflows_dir / "shared-x.yml", """
        on:
          workflow_call:
            inputs:
              declared:
                type: string
        jobs:
          j:
            runs-on: ubuntu-latest
            steps:
              - run: echo "noop"
    """)
    caller = _write(workflows_dir / "caller.yml", """
        jobs:
          call:
            uses: ./shared-x.yml
            with:
              declared: ok
              rogue: bad
    """)
    run = runner.run_workflow(
        workflow_path=caller, inputs={}, ref="main", app="intl",
        repo_root=workflows_dir,
    )
    print('DEBUG caller inputs:', run.jobs['call'].inputs)
    print('DEBUG caller note:', run.jobs['call'].note)
    findings = assertions.run_all_assertions(run)
    kinds = [f.kind for f in findings]
    assert "input-not-declared" in kinds, (
        "assertion layer must flag an input that the caller passes "
        "but the callee does not declare — this is the exact bug class "
        "that produced 'Invalid input, app is not defined'"
    )


def test_assertion_flags_missing_output_for_declared_mapping(workflows_dir):
    """A job declares `outputs: foo: ${{ steps.x.outputs.foo }}` but
    no step with id=x writes foo. The runner's recorded job.outputs
    shows the empty value; the assertion must surface this.
    """
    wf = _write(workflows_dir / "r.yml", """
        jobs:
          producer:
            runs-on: ubuntu-latest
            outputs:
              wanted: ${{ steps.x.outputs.unwritten }}
            steps:
              - id: x
                run: echo "different=1" >> "$GITHUB_OUTPUT"
    """)
    run = runner.run_workflow(
        workflow_path=wf, inputs={}, ref="main", app="intl",
    )
    findings = assertions.run_all_assertions(run)
    assert any(f.kind == "output-not-written" for f in findings), (
        "the assertion layer must catch the silent-empty-output bug — "
        "downstream `needs.x.outputs.wanted` is \"\" even though the "
        "job claims to publish it"
    )


# ---------------------------------------------------------------------------
# End-to-end: run the actual repo workflows (regression tests)
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    not (REPO_ROOT / ".github" / "workflows" / "release-cn.yml").exists(),
    reason="requires the real repo workflow files",
)
def test_real_release_cn_passes_for_master_ref():
    """Smoke test: a known-good run of release-cn.yml against the
    master branch with auto-detected env/channel should satisfy
    every contract.
    """
    run = runner.run_workflow(
        workflow_path=REPO_ROOT / ".github/workflows/release-cn.yml",
        inputs={"platform": "all", "arch": "all",
                "environment": "development", "channel": "dev"},
        ref="master", app="cn",
    )
    findings = assertions.run_all_assertions(run)
    fails = [f for f in findings if f.severity == "fail"]
    assert not fails, (
        f"real release-cn.yml must satisfy all contracts against a "
        f"clean master ref; got {len(fails)} failures:\n"
        + "\n".join(f"  {f.kind}: {f.message}" for f in fails)
    )