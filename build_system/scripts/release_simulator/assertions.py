"""
Contract assertions for release-pipeline runs.

The simulator records what happened; this layer asks "is that what we
want?".

Each `assert_*` returns a list of `Finding` records (empty == pass).
Run them all and pretty-print.

A finding has:
    severity : "fail" | "warn"
    job_id   : which job it relates to (or "" for workflow-level)
    kind     : machine-readable tag (e.g. "input-not-declared")
    message  : human-readable explanation

The kinds are stable — tests assert on them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import FAILURE, SKIPPED, SUCCESS, WorkflowRun
from . import runner as _runner


@dataclass
class Finding:
    severity: str  # "fail" | "warn"
    job_id: str = ""
    kind: str = ""
    message: str = ""

    def render(self) -> str:
        prefix = "❌" if self.severity == "fail" else "⚠️"
        loc = f"[job={self.job_id}] " if self.job_id else ""
        return f"  {prefix} {loc}{self.kind}: {self.message}"


# ---------------------------------------------------------------------------
# 1. caller/callee input parity
# ---------------------------------------------------------------------------


def assert_caller_inputs_match_callee(run: WorkflowRun) -> list[Finding]:
    """
    Every input that a caller passes via `with:` to a reusable
    workflow must be declared on the callee's
    `on.workflow_call.inputs`. The GHA server rejects the workflow
    with "Invalid input, X is not defined in the referenced workflow"
    if a caller passes an undefined input.

    Same check as `release-workflow-simulator.py`'s
    `audit_reusable_workflow_inputs`, but applied to a *run* (so it
    sees only the jobs that actually ran, with their resolved inputs).
    """
    findings: list[Finding] = []
    for jid, job in run.jobs.items():
        # Identify which reusable workflow this job called by looking
        # at job.note — we wrote the callee name there.
        # Format: "calls <callee.yml> with keys [...]"
        if not job.note.startswith("calls "):
            continue
        rest = job.note[len("calls "):]
        callee_name, _, _ = rest.partition(" with keys")
        callee_path = run.workflow_path.parent / callee_name
        if not callee_path.exists():
            findings.append(Finding(
                severity="fail", job_id=jid,
                kind="callee-not-found",
                message=f"caller refers to missing workflow: {callee_path}",
            ))
            continue
        try:
            callee_wf = _runner.load_workflow_yaml(callee_path)
        except Exception as e:
            findings.append(Finding(
                severity="fail", job_id=jid,
                kind="callee-unparseable",
                message=f"could not parse callee YAML: {e}",
            ))
            continue
        callee_on = callee_wf.get("on") or {}
        callee_inputs = set(
            (callee_on.get("workflow_call") or {}).get("inputs") or {}
        )
        passed = set(job.inputs.keys())
        for missing in passed - callee_inputs:
            findings.append(Finding(
                severity="fail", job_id=jid,
                kind="input-not-declared",
                message=(
                    f"caller passes input '{missing}' but callee "
                    f"{callee_name} does not declare it. GHA will reject "
                    f"this workflow with "
                    f"'Invalid input, {missing} is not defined in the "
                    f"referenced workflow'."
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# 2. needs.<jid>.outputs.<key> contract
# ---------------------------------------------------------------------------


def assert_validate_tag_outputs_read(run: WorkflowRun) -> list[Finding]:
    """
    validate-tag's declared job-level `outputs:` map must resolve to
    non-empty values, AND every key in the map must be backed by
    something in the live step-namespace.

    GH Actions aggregates outputs across all steps in a job and then
    resolves `${{ steps.<id>.outputs.X }}` from the declared map. If
    a key is declared but its mapping points at a step that doesn't
    exist, or at an output key the step never wrote, the downstream
    `needs.validate-tag.outputs.<key>` is the empty string — silent
    failure mode that has bitten this codebase before.

    We check three things:
      1. The mapping expression itself parsed (it must be a ${{ ... }}
         that references steps.<id>.outputs.X).
      2. The step it points at exists in the recorded run.
      3. The step actually wrote the named output key.
    """
    findings: list[Finding] = []
    vt = run.jobs.get("validate-tag")
    if vt is None:
        return [Finding(
            severity="fail", kind="missing-job",
            message="validate-tag job is missing entirely",
        )]

    # We need the raw `outputs:` block to know what each declared
    # key is mapped FROM. Re-load the workflow YAML.
    try:
        wf = _runner.load_workflow_yaml(run.workflow_path)
    except Exception as e:
        return [Finding(
            severity="fail", kind="workflow-unparseable",
            message=f"could not reload workflow for output audit: {e}",
        )]
    vt_def = (wf.get("jobs") or {}).get("validate-tag") or {}
    outputs_decl = vt_def.get("outputs") or {}

    # Build a map: step_id → set of keys that step actually wrote.
    step_writes: dict[str, set[str]] = {}
    for step in vt.steps:
        if step.step_id:
            step_writes.setdefault(step.step_id, set()).update(
                step.outputs.keys()
            )

    # If validate-tag itself failed (bash exited non-zero), the
    # "outputs were not written" question is moot — the whole job
    # was rejected. Don't pile on output-not-written findings in
    # that case; the upstream reject IS the contract being honoured.
    if vt.result != "success":
        return findings

    for declared_key, mapping in outputs_decl.items():
        mapping_s = str(mapping)
        # Look for `steps.<id>.outputs.<key>` reference.
        import re as _re
        m = _re.search(r"steps\.([\w-]+)\.outputs\.([\w-]+)", mapping_s)
        if not m:
            findings.append(Finding(
                severity="fail", job_id="validate-tag",
                kind="output-malformed-mapping",
                message=(
                    f"declared output '{declared_key}' has mapping "
                    f"{mapping_s!r} that does not reference "
                    f"steps.<id>.outputs.X. GH Actions treats this as "
                    f"a literal expression that always evaluates to ''."
                ),
            ))
            continue
        step_id, key = m.group(1), m.group(2)
        # Did any step with this id write this key?
        # We try the exact id, then the lowercase name fallback.
        if step_id in step_writes:
            if key not in step_writes[step_id]:
                findings.append(Finding(
                    severity="fail", job_id="validate-tag",
                    kind="output-not-written",
                    message=(
                        f"declared output '{declared_key}' maps to "
                        f"steps.{step_id}.outputs.{key} but no step "
                        f"with id={step_id!r} wrote that key. "
                        f"Downstream needs.validate-tag.outputs."
                        f"{declared_key} will be empty."
                    ),
                ))
        else:
            findings.append(Finding(
                severity="warn", job_id="validate-tag",
                kind="output-step-unrecorded",
                message=(
                    f"declared output '{declared_key}' maps to "
                    f"steps.{step_id}.outputs.{key} but no step with "
                    f"that id was recorded by the simulator (id "
                    f"resolution is fuzzy by design)."
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# 3. concurrency group parity (intl vs cn must not collide)
# ---------------------------------------------------------------------------


def assert_concurrency_groups_are_scoped(run: WorkflowRun) -> list[Finding]:
    """
    The workflow's concurrency group must include every dimension
    that distinguishes "two simultaneous runs that should NOT cancel
    each other". For eCan.ai that's at minimum `app`. If app is not
    in the group key, an intl and a cn run on the same ref/branch
    will cancel each other.

    This is a structural check (it inspects the YAML rather than the
    run state), but it lives in the assertions layer so it's run
    alongside the others in CI.
    """
    findings: list[Finding] = []
    try:
        wf = _runner.load_workflow_yaml(run.workflow_path)
    except Exception as e:
        return [Finding(
            severity="fail", kind="workflow-unparseable",
            message=str(e),
        )]
    conc = (wf.get("concurrency") or {})
    group = str(conc.get("group") or "")
    # The concurrency group is app-scoped if it either:
    #   - references github.event.inputs.app / inputs.app directly, OR
    #   - embeds the app identifier as a string literal (e.g.
    #     `release-cn-${{ ... }}` for the cn workflow).
    is_app_scoped = (
        "github.event.inputs.app" in group
        or "inputs.app" in group
        or (run.app and f"release-{run.app}" in group)
        or (run.app and f"{run.app}-$" in group)
    )
    if not is_app_scoped:
        findings.append(Finding(
            severity="warn",
            kind="concurrency-not-app-scoped",
            message=(
                f"concurrency.group {group!r} does not include "
                f"github.event.inputs.app and does not embed the "
                f"current app ({run.app!r}) in the key. An intl run "
                f"and a cn run on the same ref/branch/arch will "
                f"cancel each other."
            ),
        ))
    return findings


# ---------------------------------------------------------------------------
# 4. runner selection — every build job must resolve runs-on to a
#    runner that actually matches the runner_group input.
# ---------------------------------------------------------------------------


def assert_runner_selection_matches_runner_group(run: WorkflowRun) -> list[Finding]:
    """
    For each build job, the resolved `runs-on:` must agree with
    `github.event.inputs.runner_group`. If the user picks
    `runner_group=ecan-macos-aarch64` the macOS-aarch64 build job must
    run on the self-hosted aarch64 runner, not on macos-latest.

    Only build jobs are checked. validate-tag, final-status, and any
    job that runs on ubuntu-latest regardless of the runner_group
    input are exempt — they don't consume the runner_group input.
    """
    findings: list[Finding] = []
    rg = run.inputs.get("runner_group", "github-hosted")
    # Jobs whose runner is fixed regardless of runner_group. These
    # are the "service" jobs in each pipeline and any callee from
    # a shared-* workflow (which always runs on ubuntu-latest).
    exempt_jobs = {"validate-tag", "final-status", "upload",
                   "generate", "generate-links", "generate-appcast",
                   "generate-latest-json", "generate-download-links",
                   "upload-to-cos"}
    for jid, job in run.jobs.items():
        if jid in exempt_jobs:
            continue
        if not job.runs_on or job.runs_on == "(reusable)":
            continue
        if job.result == "skipped":
            continue
        # Heuristic: ecan-windows-amd64 → runs-on must include
        # self-hosted (not windows-latest). github-hosted → github.
        if rg.startswith("ecan-"):
            if "self-hosted" not in job.runs_on and "[" not in job.runs_on:
                # fromJSON('["self-hosted",...]') produces an array;
                # the runner records only the first label.
                findings.append(Finding(
                    severity="fail", job_id=jid,
                    kind="wrong-runner-for-group",
                    message=(
                        f"runner_group={rg!r} selected, but job resolved "
                        f"runs-on={job.runs_on!r} which is not a "
                        f"self-hosted label. The job will run on a "
                        f"github-hosted runner instead."
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# 5. final-status always sees every build job's real result
# ---------------------------------------------------------------------------


def assert_final_status_reports_all_results(run: WorkflowRun) -> list[Finding]:
    """
    final-status should print every build job's `result` via
    needs.<jid>.result. If any of those refs is not actually present
    on the job (typo, etc.), the summary silently prints empty. This
    is a real footgun — caught in the 894 bug class.
    """
    findings: list[Finding] = []
    fs = run.jobs.get("final-status")
    if fs is None:
        return [Finding(
            severity="warn", kind="missing-job",
            message="final-status job is missing",
        )]
    # Check declared `needs:` against actual jobs in the run record.
    # Walk the workflow YAML to read final-status's `needs:` list.
    try:
        wf = _runner.load_workflow_yaml(run.workflow_path)
    except Exception:
        return []
    fs_def = (wf.get("jobs") or {}).get("final-status") or {}
    declared_needs = fs_def.get("needs") or []
    if isinstance(declared_needs, str):
        declared_needs = [declared_needs]
    for n in declared_needs:
        if n not in run.jobs and n != "final-status":
            findings.append(Finding(
                severity="warn", job_id="final-status",
                kind="missing-needs-target",
                message=(
                    f"final-status declares needs.{n} but no job with "
                    f"id {n!r} exists in the workflow. The summary "
                    f"will print empty for that result."
                ),
            ))
    return findings


def assert_declared_outputs_have_values(run: WorkflowRun) -> list[Finding]:
    """
    For every job that ran successfully AND declared an `outputs:` map,
    verify each output key actually has a non-empty value in the recorded
    run. This catches the silent-empty-output contract bug: the YAML
    says `outputs.wanted: ${{ steps.x.outputs.unwritten }}` but the
    step writes `different=1` instead — downstream `needs.x.outputs.wanted`
    is "" and the workflow silently misbehaves.

    Scope: jobs whose YAML declares `outputs:` AND whose recorded
    `job.outputs` shows an empty value for the declared key. These two
    signals together mean the YAML promised something the runtime
    couldn't deliver. Jobs marked SKIPPED are excluded (their outputs
    were never going to be present).
    """
    import re as _re
    findings: list[Finding] = []
    try:
        wf = _runner.load_workflow_yaml(run.workflow_path)
    except Exception:
        # If the workflow is already unparseable, the runtime assertion
        # has surfaced that; don't double-flag here.
        return findings
    for jid, jdef in (wf.get("jobs") or {}).items():
        if not isinstance(jdef, dict):
            continue
        outputs_decl = jdef.get("outputs") or {}
        if not outputs_decl:
            continue
        # Callee jobs come from reusable workflows; their YAML lives in
        # another file. Skip — those are caught by the caller-inputs
        # assertion and by `assert_validate_tag_outputs_read` for the
        # canonical case.
        if "uses" in jdef:
            continue
        rec = run.jobs.get(jid)
        if rec is None or rec.result == SKIPPED:
            continue
        if rec.result != SUCCESS:
            # The job failed; missing outputs are not a contract bug,
            # they're a symptom. Don't pile on.
            continue
        for declared_key, mapping in outputs_decl.items():
            mapping_s = str(mapping)
            m = _re.search(r"steps\.([\w-]+)\.outputs\.([\w-]+)", mapping_s)
            if not m:
                continue  # Not a step reference; handled elsewhere.
            step_id, key = m.group(1), m.group(2)
            actual = rec.outputs.get(declared_key, "")
            # If the recorded value is empty but the step DID write the
            # named key in its GITHUB_OUTPUT, the mapping expression
            # was malformed; if the step didn't write the key either,
            # the bug is that nothing wrote it.
            step_records = [s for s in rec.steps
                            if s.step_id == step_id or s.name == step_id]
            step_wrote = any(key in s.outputs for s in step_records)
            if not actual and not step_wrote:
                findings.append(Finding(
                    severity="fail", job_id=jid,
                    kind="output-not-written",
                    message=(
                        f"job '{jid}' declares output '{declared_key}' "
                        f"mapping to steps.{step_id}.outputs.{key}, but "
                        f"no step with id={step_id!r} wrote that key. "
                        f"Downstream needs.{jid}.outputs.{declared_key} "
                        f"will be the empty string."
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------


def run_all_assertions(run: WorkflowRun) -> list[Finding]:
    """
    Run every assertion. Returns the full list; the caller decides
    what to do (PR gate, CLI summary, etc.).
    """
    findings: list[Finding] = []
    findings += assert_caller_inputs_match_callee(run)
    findings += assert_validate_tag_outputs_read(run)
    findings += assert_declared_outputs_have_values(run)
    findings += assert_concurrency_groups_are_scoped(run)
    findings += assert_runner_selection_matches_runner_group(run)
    findings += assert_final_status_reports_all_results(run)
    return findings


def summarise(findings: list[Finding]) -> tuple[int, int]:
    fails = sum(1 for f in findings if f.severity == "fail")
    warns = sum(1 for f in findings if f.severity == "warn")
    return fails, warns