"""
The runner — what actually executes a release workflow.

Design intent
-------------
We do NOT try to faithfully reimplement every byte of GHA's runner
semantics. We try to faithfully reproduce the **contracts** that the
eCan.ai release workflows depend on:

  * `if:` expressions on jobs and steps resolve against the live
    variable namespace (needs.<jid>.result, needs.<jid>.outputs.*,
    github.event.inputs.*, secrets.*, inputs.*, env.*).
  * `$GITHUB_OUTPUT` writes inside a step are captured and exposed
    both as `step.outputs` AND as `job.outputs.<key>` so that
    `needs.<jid>.outputs.<key>` in downstream jobs is filled in.
  * Job-level `env:` blocks are resolved (with ${{ ... }}) before any
    step runs, and steps inherit that env plus their own `env:`.
  * `with:` on `uses:` to a reusable workflow is converted into
    `INPUT_<UPPER_NAME>` env vars on the callee's runner. This is the
    contract `shared-*.yml` Python scripts rely on.
  * `secrets: inherit` from caller propagates the parent's secret set
    to the callee.
  * `needs:` chains are honoured — a job only starts when all of its
    declared needs have either succeeded or been determined to be
    skipped/failed in the right way. We use the same rules as GHA:
    a job with `needs: [X]` runs iff X's `result` is `success` OR if
    the calling job has `if: always()` (then X's `result` is
    `success`, `failure`, `skipped`, or `cancelled` and the `if:`
    expression on the calling job decides what to do with it).
  * `if: always()` short-circuits to True regardless of upstream
    result.
  * Bash `run:` blocks are executed by `bash` directly with the
    resolved env so `set -euo pipefail` and `$GITHUB_OUTPUT` actually
    work. Build commands are not what we want to exercise; we replace
    them with deterministic stubs (see `mock_actions.py`).

The runner is *deterministic* — given the same workflow + inputs +
secrets, it produces the same `WorkflowRun`. This means the
assertion layer can compare two runs directly without time/random
worries.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import expr as _expr
from .models import (
    CANCELLED,
    FAILURE,
    SKIPPED,
    SUCCESS,
    JobRecord,
    StepRecord,
    WorkflowRun,
)


class RunnerError(Exception):
    """Raised by the runner for structural problems (bad YAML,
    unresolved needs, etc.)."""


# ---------------------------------------------------------------------------
# Expression interpolation helpers
# ---------------------------------------------------------------------------


def _interpolate(text: str, env: _expr.ExprEnv) -> str:
    """
    Resolve all ${{ ... }} occurrences in a string and return the
    concatenated result. This is what GH Actions does for `env:`,
    `run:` (after substitution), `with:`, `runs-on:`, etc. — basically
    anywhere a ${{ ... }} can appear it gets evaluated in the active
    context.

    Empty expressions (`${{ }}`) and pure whitespace are left alone —
    they don't make sense and the upstream parser already errored.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "$" and i + 3 < n and text[i:i + 3] == "${{":
            end = text.find("}}", i + 3)
            if end == -1:
                out.append(text[i:])
                break
            body = text[i + 3:end].strip()
            val = env.eval(body)
            out.append("" if val is None else str(val))
            i = end + 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# Job-id substrings that identify post-build contract surface jobs.
# These run on `ubuntu-latest` but their bash does real I/O (aws s3,
# cos upload, XML/JSON generation against `dist/*`). They must be
# neutralised alongside platform-specific build jobs or the simulator
# shells out to real cloud storage. Their `if:` / `needs:` / `with:`
# contracts are still validated — only the bash body is stubbed.
_HEAVY_JOB_ID_HINTS: tuple[str, ...] = (
    "upload",         # upload, upload-to-cos
    "appcast",        # generate-appcast (also matches a job in
                      # shared-cos-appcast-generation.yml)
    "download-links", # generate-download-links
    "latest-json",    # generate-latest-json
    "publish",        # publish-* (future-proofing)
    "sign",           # sign-* (future-proofing)
    "generate",       # generates an XML/JSON file from real dist
)


def _resolve_value(value: Any, env: _expr.ExprEnv) -> Any:
    """
    Recursively resolve ${{ ... }} inside a YAML-decoded value.

    - dict: resolve each value (keys stay as-is)
    - list: resolve each item
    - str: interpolate ${{ ... }}
    - everything else: pass through
    """
    if isinstance(value, dict):
        return {k: _resolve_value(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(v, env) for v in value]
    if isinstance(value, str):
        return _interpolate(value, env)
    return value


# ---------------------------------------------------------------------------
# Workflow YAML loader
# ---------------------------------------------------------------------------


def load_workflow_yaml(path: Path) -> dict:
    """Read a workflow YAML and return a normalised dict.

    PyYAML parses bare `on:` as the literal key `True`. GHA files
    always use `on:`. Normalise back so callers can use
    `wf["on"]["workflow_dispatch"]` regardless.
    """
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def _neutralise_build_runs(wf: dict, job_ids: list[str]) -> dict:
    """
    Replace the body of inline `run:` steps in the listed jobs with a
    single `echo MOCK ...; exit 0`. We do this so the simulator never
    tries to actually compile, sign, or upload artefacts. The jobs
    still flow through every contract check (if:, runs-on:, env:,
    needs.*, outputs:), they just don't execute the heavy bash.

    Steps we EXPLICITLY leave alone (run for real) include:

      * validate / detect-env / final-status / show-summary —
        these are the contracts we want exercised end-to-end.
      * Anything with `shell: pwsh` / `shell: powershell` — these
        are PowerShell; running them via bash is a guaranteed
        syntax error. They are skipped silently.

    This mutation is local to the simulator's view; the workflow file
    on disk is not touched.
    """
    jobs = wf.get("jobs") or {}
    for jid in job_ids:
        jdef = jobs.get(jid)
        if not isinstance(jdef, dict):
            continue
        steps = jdef.get("steps") or []
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            if "run" not in step:
                continue
            shell = str(step.get("shell") or "").lower()
            # PowerShell: skip silently rather than running it
            # through bash and getting a syntax error. The step's
            # env block is still recorded; only the body is skipped.
            if shell in ("pwsh", "powershell"):
                step["run"] = (
                    f"echo \"MOCK PowerShell step: {step.get('name') or 'unnamed'} "
                    f"(job-id: {jid}, shell: {shell})\"\n"
                )
                continue
            # Don't neutralise steps that look like validation /
            # detection / summary — these are the contracts.
            name = str(step.get("name") or "")
            if any(tag in name.lower() for tag in (
                "validate", "detect", "summary", "show summary",
                "final", "determine signing",
            )):
                continue
            step["run"] = (
                f"echo \"MOCK build step: {name or 'unnamed'} (job-id: {jid})\"\n"
                f"echo \"ok=true\" >> \"$GITHUB_OUTPUT\"\n"
            )
    return wf


def _resolve_inputs(wf: dict) -> dict[str, dict]:
    """
    Extract the workflow_dispatch input declarations.

    Returns {name: {type, default, description, required}}. Each value
    is the raw declaration dict, untouched (so we can check
    `wf_dispatch.inputs.X.default` later).
    """
    on = wf.get("on") or {}
    wd = on.get("workflow_dispatch") or {}
    inputs = wd.get("inputs") or {}
    return inputs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_workflow(
    *,
    workflow_path: Path,
    inputs: dict[str, str],
    ref: str = "main",
    secrets: dict[str, str] | None = None,
    env_overrides: dict[str, str] | None = None,
    app: str,
    bash_bin: str = "bash",
    scratch_root: Path | None = None,
    repo_root: Path | None = None,
) -> WorkflowRun:
    """
    Run a workflow end-to-end against a fixed set of inputs.

    `inputs` is treated as "values the operator actually selected in the
    Actions UI". Workflow YAML defaults for `platform`, `arch`, and
    `runner_group` are auto-applied (matching the Actions UI's
    pre-selected default and what every workflow `if:` and bash
    fallback assumes). Other inputs (environment, channel,
    upload_artifacts, ref, user_prefix) stay empty so the bash
    auto-detect logic can fire as it would for a blank UI submission.
    To bypass the auto-defaults entirely, pass the input explicitly
    (even as empty string).

    Parameters
    ----------
    workflow_path
        Path to the caller workflow YAML (release-cn.yml etc.).
    inputs
        Workflow_dispatch input values (strings — same as a user would
        type in the Actions UI). Unknown inputs are ignored silently.
    ref
        The git ref the workflow thinks it was triggered for. Affects
        validate-tag only.
    secrets
        Secrets visible to the workflow. If None, an empty dict is
        used (so `secrets.X || 'NOT_SET'` resolves to NOT_SET).
    env_overrides
        Repo-level env (rarely needed; GH sets GITHUB_REF etc. itself).
    app
        "intl" or "cn" — used by the run summary and by tests.
    bash_bin
        Executable used to run `run:` blocks. Default `bash`; tests
        can override to a stub that records invocations.
    scratch_root
        Where to put the temp dirs that bash runs in. If None, a
        tempfile.mkdtemp() is used.
    repo_root
        Filesystem path the simulated runner should treat as the
        checkout root. Bash steps that call `git show-ref` /
        `git rev-parse` / `cat VERSION` need this. If None, defaults
        to the directory containing `workflow_path`'s parent (i.e.
        the project root for workflows living under `.github/`).
    """
    wf = load_workflow_yaml(workflow_path)
    decl_inputs = _resolve_inputs(wf)

    # Neutralise build jobs (heavy bash). Validate-tag / detect-env
    # / final-status and similar "contract" steps are left intact.
    # The `_HEAVY_JOB_ID_HINTS` list covers the post-build jobs that
    # run on `ubuntu-latest` but do real I/O (aws s3 upload, generation
    # of JSON/XML files that depend on the dist tree) — neutralising
    # them keeps the simulator inside the contract envelope without
    # us actually shelling out to aws / cos. Their `if:` and `needs:`
    # are still evaluated; we only stub the body.
    build_job_ids = [
        jid for jid, jdef in (wf.get("jobs") or {}).items()
        if isinstance(jdef, dict) and _is_build_job(jdef)
    ]
    for jid, jdef in (wf.get("jobs") or {}).items():
        if isinstance(jdef, dict) and any(
            tag in jid for tag in _HEAVY_JOB_ID_HINTS
        ) and jid not in build_job_ids:
            build_job_ids.append(jid)
    _neutralise_build_runs(wf, build_job_ids)

    # Resolve the simulated checkout root. bash steps that call
    # `git show-ref` / `git rev-parse` / `cat VERSION` need this.
    # Default: the directory two levels above the workflow file
    # (i.e. the project root for `.github/workflows/foo.yml`).
    if repo_root is None:
        # .github/workflows/<name>.yml → repo root is two parents up.
        repo_root = workflow_path.parent.parent.parent.resolve()
    repo_root = Path(repo_root).resolve()

    # Fill in defaults ONLY for inputs whose default eCan.ai's workflows
    # actually depend on. The Actions UI shows the YAML default as the
    # initially-selected option; we simulate "operator clicked Run
    # without changing the default" by injecting that value. Other
    # inputs stay empty, matching what bash sees when the operator
    # leaves them blank in the UI.
    #
    # Concretely: runner_group's default 'github-hosted' is what every
    # job's `runs-on:` expression falls back to. If we left it empty
    # here, every build job's `if:` would fail to match and the whole
    # pipeline would silently skip. Other inputs (environment, channel,
    # upload_artifacts, etc.) use empty-string auto-detection in the
    # bash scripts, so we leave them empty here too.
    normalised: dict[str, str] = {}
    # Inputs whose YAML default MUST be applied to mirror what the
    # Actions UI shows as pre-selected. These are the inputs every
    # workflow `if:` and bash fallback assumes:
    #   * platform=all       — every build job's `if:` requires this
    #                          or a specific platform; without a default
    #                          here, all builds silently skip
    #   * arch=all           — same reason, every arch-gated job
    #   * runner_group=github-hosted — same, every runner-gated job
    # Other inputs (environment, channel, upload_artifacts, ref,
    # user_prefix) stay empty — those have explicit bash auto-detect
    # logic that should fire when the operator leaves them blank.
    DEFAULTS_TO_APPLY = {"platform", "arch", "runner_group"}
    for name, decl in decl_inputs.items():
        if name in inputs:
            normalised[name] = str(inputs[name])
        elif (name in DEFAULTS_TO_APPLY
              and "default" in decl
              and decl["default"] is not None):
            normalised[name] = str(decl["default"])
        else:
            normalised[name] = ""

    # Workspace (for `uses: ./path` resolution). Prefer caller-supplied;
    # otherwise infer from the workflow file's location.
    if isinstance(repo_root, Path):
        workspace = str(repo_root.resolve())
    else:
        workspace = str(workflow_path.parent.parent.parent.resolve())

    run = WorkflowRun(
        workflow_path=workflow_path,
        workflow_name=str(wf.get("name") or workflow_path.stem),
        app=app,
        inputs=normalised,
        ref=ref,
        secrets=dict(secrets or {}),
        env=dict(env_overrides or {}),
        workspace=workspace,
    )

    # Inject the synthetic GHA env that real GHA always provides.
    run.env.setdefault("GITHUB_REPOSITORY", "ecan/eCan.ai")
    run.env.setdefault("GITHUB_REF", f"refs/heads/{ref}")
    run.env.setdefault("GITHUB_SHA", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    run.env.setdefault("GITHUB_WORKSPACE", str(repo_root))
    run.env.setdefault("RUNNER_OS", "Linux")
    run.env.setdefault("RUNNER_TEMP", str(scratch_root or Path(tempfile.mkdtemp())))
    # GITHUB_STEP_SUMMARY is the path the runner writes the summary
    # markdown to. Real GHA sets it; we set it to a path inside the
    # runner's tempdir so steps that write to it don't error with
    # "ambiguous redirect" on `>> $GITHUB_STEP_SUMMARY`.
    summary_dir = Path(scratch_root or Path(tempfile.mkdtemp()))
    run.env.setdefault("GITHUB_STEP_SUMMARY", str(summary_dir / "step_summary.md"))

    # Build the job execution plan: topologically ordered, with needs
    # chain honoured. We do a simple Kahn-style pass.
    jobs_def = wf.get("jobs") or {}
    if not jobs_def:
        raise RunnerError(f"workflow has no jobs: {workflow_path}")

    # Phase 1: resolve `runs-on:` for every job (this does not need
    # upstream state) and stash the structural `if:` and `needs:`
    # blocks. We need them in phase 2 to actually decide whether the
    # job should run.
    plans: dict[str, dict] = {}
    for jid, jdef in jobs_def.items():
        if not isinstance(jdef, dict):
            continue
        plans[jid] = {
            "def": jdef,
            "needs": _normalise_needs(jdef.get("needs")),
            "if_expr": _strip_if_block(jdef.get("if")),
            "uses": jdef.get("uses"),
            "with": jdef.get("with") or {},
            "secrets": jdef.get("secrets") or {},
            "env": jdef.get("env") or {},
            "outputs_decl": jdef.get("outputs") or {},
            "runs_on_raw": jdef.get("runs-on"),
        }

    # Phase 2: execute jobs in topological order.
    executed: set[str] = set()
    remaining = set(plans)
    progress = True
    while progress and remaining:
        progress = False
        for jid in sorted(remaining):
            plan = plans[jid]
            upstream = plan["needs"]
            if any(u not in executed for u in upstream):
                continue
            _execute_job(run, jid, plan, decl_inputs_decl=decl_inputs,
                         bash_bin=bash_bin)
            executed.add(jid)
            remaining.discard(jid)
            progress = True

    if remaining:
        unresolved = sorted(remaining)
        raise RunnerError(
            f"could not resolve needs chain for jobs: {unresolved} "
            f"(possible cycle or missing needs target)"
        )

    return run


# ---------------------------------------------------------------------------
# Job-level execution
# ---------------------------------------------------------------------------


def _is_build_job(jdef: dict) -> bool:
    """
    A job is a "build" job if it produces a platform-specific binary
    (windows, macos, or self-hosted linux). The `ubuntu-latest` and
    `ubuntu-22.04` runners are NOT build jobs — they're used by
    validate-tag, final-status, and the various upload/appcast jobs.
    Treating them as build jobs would neutralise the contract scripts
    we actually want to verify.
    """
    runs_on = jdef.get("runs-on")
    if runs_on is None:
        return False
    runs_on_s = str(runs_on) if not isinstance(runs_on, list) else str(runs_on[0])
    # Only consider a job a "build" if its runner is genuinely
    # platform-specific: windows / macos / self-hosted / explicit
    # ecan-* runner labels. Generic ubuntu-* runners are service
    # runners and their bash IS the contract.
    if any(token in runs_on_s for token in (
        "windows-", "macos-",
        "self-hosted", "ecan-",
    )):
        return True
    return False


def _normalise_needs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _strip_if_block(value: Any) -> str | None:
    """
    Normalise an `if:` block. GHA accepts either a single-line string
    or a multi-line block scalar; YAML loads both as a string that
    can contain literal newlines. Collapse those newlines to spaces
    so our expression parser sees a single logical line — `if: |
      A && B && C` and `if: A && B && C` are semantically the same.
    Returns None when no `if:` was declared.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Collapse newlines (and runs of whitespace) to single spaces
        # so the expression evaluator sees one continuous statement.
        s = " ".join(value.split())
        return s or None
    return str(value)


def _execute_job(
    run: WorkflowRun,
    jid: str,
    plan: dict,
    *,
    decl_inputs_decl: dict,
    bash_bin: str,
) -> None:
    """
    Decide whether `jid` should run (via `if:`) and either execute its
    steps or mark it SKIPPED. For reusable-workflow callers (`uses:`),
    recurse into the callee with `with:` → INPUT_X and `secrets:` →
    secret dict.

    The decision tree mirrors GHA:

      1. If the job declares `if:` and it evaluates false, mark
         skipped and return.
      2. If `uses:` is set, treat this as a reusable-workflow caller:
         resolve `with:` (and any `secrets: inherit`), then load the
         callee workflow and run it with a synthetic input set.
      3. Otherwise resolve `runs-on:` and `env:`, then walk steps.
    """
    job = run.job(jid)

    # Build the variable namespace for THIS job. `needs.<upstream>.result`
    # comes from `run.jobs[upstream].result`; `needs.<upstream>.outputs`
    # comes from `run.jobs[upstream].outputs`.
    needs_ns: dict[str, dict[str, Any]] = {}
    for upstream in plan["needs"]:
        if upstream in run.jobs:
            needs_ns[upstream] = {
                "result": run.jobs[upstream].result,
                "outputs": dict(run.jobs[upstream].outputs),
            }
    var_env = {
        "needs": needs_ns,
        "github": {
            "event": {"inputs": run.inputs},
            "ref": run.env.get("GITHUB_REF", f"refs/heads/{run.ref}"),
            "repository": run.env.get("GITHUB_REPOSITORY", ""),
            "sha": run.env.get("GITHUB_SHA", ""),
            "workspace": run.env.get("GITHUB_WORKSPACE", ""),
        },
        "inputs": dict(run.inputs),
        "secrets": dict(run.secrets),
        "runner": {"os": run.env.get("RUNNER_OS", "Linux")},
        "env": dict(run.env),
    }
    expr_env = _expr.ExprEnv(var_env)

    # ---- gate 1: if: evaluation -------------------------------------------
    if_expr = plan["if_expr"]
    if if_expr is not None:
        try:
            opens = bool(expr_env.eval(if_expr))
        except _expr.ExprError as e:
            job.result = FAILURE
            job.note = f"if: evaluation error: {e}"
            return
        if not opens:
            job.result = SKIPPED
            job.note = f"if: {if_expr!r} evaluated false"
            return

    # ---- gate 2: reusable-workflow caller --------------------------------
    if plan["uses"]:
        _execute_caller_job(run, jid, plan, expr_env)
        return

    # ---- gate 3: ordinary job — resolve runs-on + env, then walk steps -----
    # Resolve runs-on
    runs_on_raw = plan["runs_on_raw"] or "ubuntu-latest"
    if isinstance(runs_on_raw, list):
        runs_on = str(runs_on_raw[0])
    elif isinstance(runs_on_raw, str):
        runs_on = _interpolate(runs_on_raw, expr_env)
    else:
        runs_on = str(runs_on_raw)
    job.runs_on = runs_on

    # Resolve job-level env (after runs-on so secrets are visible).
    resolved_env: dict[str, str] = {
        k: str(_resolve_value(v, expr_env)) for k, v in plan["env"].items()
    }
    # Merge in workflow-level env (workflow env wins per GHA semantics).
    resolved_env = {**resolved_env, **run.env}
    job.env = resolved_env

    # Resolve outputs mapping (${{ steps.X.outputs.Y }} → step outputs)
    # We run steps first then come back to fill `job.outputs`.

    # Walk steps
    steps_def = plan["def"].get("steps") or []
    if not isinstance(steps_def, list):
        job.result = FAILURE
        job.note = "steps is not a list"
        return

    # GH Actions exposes `steps.<step_id>.outputs.<key>` to subsequent
    # steps in the same job (and to the job-level `outputs:` map).
    # The simulator must mirror this: as we execute each step, we
    # publish its GITHUB_OUTPUT writes into the namespace so the next
    # step's ${{ steps.<id>.outputs.X }} resolves.
    steps_ns: dict[str, dict[str, Any]] = {}
    # Mutate the namespace the same way GHA does (in place). Using
    # the existing `steps` key avoids re-injecting later.
    var_env.setdefault("steps", {})
    var_env["steps"].update(steps_ns)

    step_records: list[StepRecord] = []
    any_fail = False
    for step in steps_def:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or step.get("name") or "")
        rec = _execute_step(step, expr_env, resolved_env,
                            bash_bin=bash_bin, run=run,
                            cwd=Path(run.env["GITHUB_WORKSPACE"]))
        rec.step_id = step_id
        step_records.append(rec)
        # Publish this step's outputs to the namespace so the next
        # step can read them.
        if step_id:
            var_env["steps"][step_id] = {
                "outputs": dict(rec.outputs),
                "conclusion": "success" if rec.ok else "failure",
                "outcome": "success" if rec.ok else "failure",
            }
        if rec.kind == "uses":
            # Action stub (see mock_actions.py). Treated as success
            # unless the stub recorded a failure.
            pass
        if not rec.ok:
            any_fail = True
            # GH semantics: a step that fails stops the job (unless
            # `continue-on-error: true`). We honour the flag and stop.
            if not step.get("continue-on-error"):
                break
    job.steps = step_records

    # Now fill job.outputs from the declared mapping. Re-evaluate the
    # expressions so steps.<id>.outputs.X is fresh — GH does this too.
    outputs: dict[str, str] = {}
    for out_name, out_expr in plan["outputs_decl"].items():
        # out_expr is something like "${{ steps.validate.outputs.valid }}"
        out_val = _interpolate(str(out_expr), expr_env)
        outputs[out_name] = out_val
    job.outputs = outputs

    job.result = SUCCESS if not any_fail else FAILURE


def _execute_caller_job(
    run: WorkflowRun,
    jid: str,
    plan: dict,
    expr_env: _expr.ExprEnv,
) -> None:
    """
    Execute a job that calls a reusable workflow (`uses: <path>`).

    The reusable-workflow contract:
      - `with:` becomes INPUT_<UPPER_NAME> env vars on the callee.
      - `secrets: inherit` propagates the parent's secrets.
      - The callee's `if:` is evaluated against the *caller's* context
        (matches GHA: a caller job's gate is what decides whether the
        whole reusable call happens).
      - The callee's `on.workflow_call.inputs` are merged with the
        caller's `with:` to produce the callee's `inputs` namespace.
    """
    uses = str(plan["uses"])
    job = run.job(jid)

    # Resolve the callee path. GHA treats `uses: ./path` as
    # workspace-relative (i.e. relative to the repo root, NOT the
    # caller's file location). For eCan.ai workflows, the caller
    # always lives in `<repo>/.github/workflows/<name>.yml` and
    # callees live in `<repo>/.github/workflows/shared-*.yml`, so
    # going up two parents from the caller file gives us the repo
    # root.
    uses = str(plan["uses"])
    job = run.job(jid)
    # Resolve the callee path. GHA treats `uses: ./path` as workspace-
    # relative, where `workspace` is the repo root. The repo root is
    # almost always `<wf_file>/.github` for eCan.ai; for tests where
    # the caller lives in a flat temp dir we use the workspace hint
    # passed in by `run_workflow(workspace=...)`, falling back to two
    # parents up (the conventional `.github/workflows/<file>.yml`
    # layout).
    if uses.startswith("./") or uses.startswith("../"):
        workspace = run.workspace
        if workspace is not None:
            callee_path = (Path(workspace) / uses.removeprefix("./")).resolve()
        elif run.workflow_path.parent.parent.name == ".github":
            callee_path = (run.workflow_path.parent.parent.parent
                           / uses.removeprefix("./")).resolve()
        else:
            callee_path = (run.workflow_path.parent / uses).resolve()
    elif uses.startswith("/"):
        callee_path = (Path(uses)).resolve()
    else:
        callee_path = (run.workflow_path.parent / uses).resolve()
    if not callee_path.exists():
        job.result = FAILURE
        job.note = f"reusable workflow not found: {callee_path}"
        return

    # Resolve `with:` — every value may contain ${{ ... }}.
    resolved_with: dict[str, str] = {}
    for k, v in plan["with"].items():
        resolved_with[k] = str(_resolve_value(v, expr_env))

    # Resolve `secrets:` — `inherit` means pass everything.
    if plan["secrets"] == "inherit" or (isinstance(plan["secrets"], dict)
                                        and plan["secrets"].get("inherit") == "inherit"):
        resolved_secrets = dict(run.secrets)
    elif isinstance(plan["secrets"], dict):
        resolved_secrets = {
            k: str(_resolve_value(v, expr_env))
            for k, v in plan["secrets"].items()
        }
    else:
        resolved_secrets = {}

    # Record the contract on the caller job so the assertion layer can
    # see what was sent.
    job.inputs = resolved_with
    job.secrets = resolved_secrets
    job.runs_on = "(reusable)"
    job.note = f"calls {callee_path.name} with keys {sorted(resolved_with.keys())}"

    # Load the callee and run it. The callee's `workflow_call.inputs`
    # is its declared inputs; we feed it the caller's `with:` plus the
    # synthetic callee environment.
    callee_wf = load_workflow_yaml(callee_path)
    callee_on = callee_wf.get("on") or {}
    callee_call = callee_on.get("workflow_call") or {}
    callee_inputs_decl = callee_call.get("inputs") or {}

    # Apply defaults the callee declared but the caller didn't pass.
    callee_inputs: dict[str, str] = {}
    for name, decl in callee_inputs_decl.items():
        if name in resolved_with:
            callee_inputs[name] = str(resolved_with[name])
        elif "default" in decl and decl["default"] is not None:
            callee_inputs[name] = str(decl["default"])
        else:
            callee_inputs[name] = ""

    # Recursively run the callee — but inline. We DO NOT spin up a
    # subprocess; the callee is just more YAML to drive. The runner
    # is already on the same Python interpreter.
    callee_run = WorkflowRun(
        workflow_path=callee_path,
        workflow_name=str(callee_wf.get("name") or callee_path.stem),
        app=run.app,
        inputs=callee_inputs,
        ref=run.ref,
        secrets=resolved_secrets,
        env={
            **run.env,
            # GH sets INPUT_<NAME> env vars for the callee. We do too.
            **{f"INPUT_{k.upper().replace('-', '_')}": v
               for k, v in callee_inputs.items()},
        },
    )

    # Neutralise build-like bash inside the callee too. Callee jobs
    # that build (e.g. shared-cos-upload's `upload` job runs `pip
    # install` and `aws s3 cp`) should not actually run during the
    # simulator — their contracts are about `with:` propagation and
    # `needs.<jid>.result` consumption, not about whether the upload
    # actually completes.
    callee_jobs_def = callee_wf.get("jobs") or {}
    callee_build_ids = [
        cid for cid, cdef in callee_jobs_def.items()
        if isinstance(cdef, dict) and _is_build_job(cdef)
    ]
    for cid, cdef in callee_jobs_def.items():
        if isinstance(cdef, dict) and any(
            tag in cid for tag in _HEAVY_JOB_ID_HINTS
        ) and cid not in callee_build_ids:
            callee_build_ids.append(cid)
    _neutralise_build_runs(callee_wf, callee_build_ids)
    callee_jobs_def = callee_wf.get("jobs") or {}
    plans: dict[str, dict] = {}
    for cid, cdef in callee_jobs_def.items():
        if not isinstance(cdef, dict):
            continue
        plans[cid] = {
            "def": cdef,
            "needs": _normalise_needs(cdef.get("needs")),
            "if_expr": _strip_if_block(cdef.get("if")),
            "uses": cdef.get("uses"),
            "with": cdef.get("with") or {},
            "secrets": cdef.get("secrets") or {},
            "env": cdef.get("env") or {},
            "outputs_decl": cdef.get("outputs") or {},
            "runs_on_raw": cdef.get("runs-on"),
        }

    executed: set[str] = set()
    remaining = set(plans)
    progress = True
    while progress and remaining:
        progress = False
        for cid in sorted(remaining):
            plan = plans[cid]
            upstream = plan["needs"]
            if any(u not in executed for u in upstream):
                continue
            _execute_job(callee_run, cid, plan,
                         decl_inputs_decl=callee_inputs_decl,
                         bash_bin="bash")
            executed.add(cid)
            remaining.discard(cid)
            progress = True

    # Promote callee jobs into the parent run so tests can inspect
    # them directly.
    for cid, rec in callee_run.jobs.items():
        run.jobs[cid] = rec

    # Caller job result = overall callee result. If any callee job
    # failed (and wasn't skipped), caller is failure.
    real_results = [
        r.result for cid, r in callee_run.jobs.items()
        if r.result != SKIPPED
    ]
    if not real_results:
        job.result = SKIPPED
    elif any(r == FAILURE for r in real_results):
        job.result = FAILURE
    elif any(r == CANCELLED for r in real_results):
        job.result = CANCELLED
    else:
        job.result = SUCCESS

    job.outputs = {}  # reusable caller jobs don't have job.outputs themselves


# ---------------------------------------------------------------------------
# Step-level execution
# ---------------------------------------------------------------------------


def _execute_step(
    step: dict,
    expr_env: _expr.ExprEnv,
    job_env: dict[str, str],
    *,
    bash_bin: str,
    run: WorkflowRun,
    cwd: Path | None = None,
) -> StepRecord:
    """
    Run one step. Two step kinds:

      - `uses:` step — record as a StepRecord with kind="uses"; the
        mock_actions layer is responsible for filling in env/outputs
        if the action needs to contribute. For now we treat every
        `actions/checkout@v6` etc. as a no-op success.
      - `run:` step — interpolate the script body (so ${{ ... }} in
        `run:` blocks resolves correctly), execute via bash in a
        tempdir with the merged env, capture $GITHUB_OUTPUT writes.
    """
    name = str(step.get("name") or "")

    if "uses" in step:
        return _execute_uses_step(name, step, expr_env, job_env)

    if "run" in step:
        return _execute_run_step(name, step, expr_env, job_env,
                                 bash_bin=bash_bin, cwd=cwd)

    rec = StepRecord(name=name, ok=True)
    rec.note = "step has neither uses nor run; treated as no-op"
    return rec


def _execute_uses_step(
    name: str,
    step: dict,
    expr_env: _expr.ExprEnv,
    job_env: dict[str, str],
) -> StepRecord:
    """
    Handle `uses:` steps.

    For eCan.ai's release workflows the only `uses:` forms we
    encounter are:
      - actions/checkout@v6
      - actions/setup-python@v6
      - actions/upload-artifact@v4 (or @v3)
      - ./.github/actions/setup-python-env (local composite)
      - ./.github/workflows/shared-*.yml (handled at job level, not step)

    We resolve `with:` for expression interpolation and record the
    step as a successful no-op. Real action semantics are out of scope;
    the test layer doesn't need to verify them.
    """
    rec = StepRecord(name=name, kind="uses", ok=True)
    rec.env = {
        **{k: str(_resolve_value(v, expr_env))
           for k, v in (step.get("env") or {}).items()},
        **job_env,
    }
    return rec


def _execute_run_step(
    name: str,
    step: dict,
    expr_env: _expr.ExprEnv,
    job_env: dict[str, str],
    *,
    bash_bin: str,
    cwd: Path | None = None,
) -> StepRecord:
    """
    Handle `run:` steps. Interpolates the script for ${{ ... }} and
    runs it via bash. Captures $GITHUB_OUTPUT by replacing the env var
    with a path the runner writes to and parses after the run.

    The simulator does NOT actually build anything — scripts inside
    build steps are replaced with deterministic stubs by
    `mock_actions.py` before this point. validate-tag, appcast
    generation, the macos-build-result expression, etc. are all run
    for real because they live in shell and are exactly the contracts
    we want to verify.

    `cwd` defaults to `job_env[GITHUB_WORKSPACE]` which is the
    repo root the simulator was started with. Bash steps that call
    `git show-ref` / `git rev-parse` / `cat VERSION` rely on this.
    """
    rec = StepRecord(name=name, kind="run")
    rec.env = {
        **job_env,
        **{k: str(_resolve_value(v, expr_env))
           for k, v in (step.get("env") or {}).items()},
    }

    raw = step.get("run") or ""
    if isinstance(raw, list):
        raw = "\n".join(str(line) for line in raw)
    if not raw.strip():
        rec.ok = True
        rec.note = "empty run block"
        return rec

    interpolated = _interpolate(str(raw), expr_env)

    # Hook for mock_actions: if the script starts with the magic
    # "MOCK-ACTION: ..." marker we let mock_actions take over.
    if interpolated.startswith("MOCK-ACTION:"):
        from . import mock_actions
        return mock_actions.handle(name, interpolated, rec)

    # Real bash execution.
    if cwd is None:
        cwd = Path(job_env.get("GITHUB_WORKSPACE") or tempfile.mkdtemp())
    with tempfile.TemporaryDirectory(prefix="relsim-") as tmp:
        out_path = Path(tmp) / "github_output"
        # Inherit the host's PATH and HOME so tools like sort, git,
        # python3 etc. resolve. Real GHA runners have /usr/bin/sort
        # etc. baked in; we rely on the simulator host having them.
        env = {**os.environ, **rec.env,
               "GITHUB_OUTPUT": str(out_path),
               "GITHUB_ENV": str(Path(tmp) / "github_env"),
               "GITHUB_PATH": str(Path(tmp) / "github_path"),
               "GITHUB_WORKSPACE": str(cwd),
               "RUNNER_TEMP": str(tmp)}
        try:
            proc = subprocess.run(
                [bash_bin, "-c", interpolated],
                env=env,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            rec.ok = False
            rec.note = f"run: timeout after 60s"
            return rec
        except FileNotFoundError:
            rec.ok = False
            rec.note = f"bash binary '{bash_bin}' not found"
            return rec
        if proc.returncode != 0:
            rec.ok = False
            rec.note = (f"run: bash exit {proc.returncode}; "
                        f"stderr={proc.stderr.strip()[:500]}; "
                        f"stdout_tail={proc.stdout.strip()[-500:]}")
            return rec

        # Parse GITHUB_OUTPUT into step.outputs WHILE we still hold
        # the tempdir open. The previous layout parsed outside the
        # `with` block, so by the time we read `out_path` the
        # TemporaryDirectory had been cleaned up and `exists()`
        # returned False — silently dropping every step's outputs.
        if out_path.exists():
            for line in out_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "<<" in line:
                    # Multiline form: <<name\nbody\nname. Skip for now —
                    # eCan.ai release workflows only use the simple form.
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    rec.outputs[k] = v
        if proc.returncode == 0:
            rec.ok = True
        return rec

    # Unreachable in the success path — the with-block always returns.
    # We keep a defensive `return rec` here so a future refactor that
    # moves the parse outside the with block does not silently lose
    # outputs again.
    return rec