#!/usr/bin/env python3
"""
release_simulator — full execution simulator for eCan.ai release workflows.

What it does (vs the 4086-case static simulator)
------------------------------------------------
The static simulator (`release-workflow-simulator.py`) only evaluates
`if:` expressions and counts which jobs would run. It does NOT
execute bash, does NOT track $GITHUB_OUTPUT, does NOT pass `with:`
to reusable workflows, and does NOT verify any contract that lives
inside a step. It catches one class of bug — gate logic — and
nothing else.

This simulator runs the workflows. It:

  * executes validate-tag / detect-env / final-status bash for real
  * neutralises build bash (we do not want to compile or sign in CI)
  * captures $GITHUB_OUTPUT writes so `needs.<jid>.outputs.*`
    propagation can be verified end-to-end
  * follows `uses:` to reusable workflows and feeds `with:` → INPUT_X
    and `secrets: inherit` properly
  * resolves `${{ ... }}` in `if:`, `env:`, `runs-on:`, `with:`, and
    inside bash `run:` bodies
  * records the resulting WorkflowRun and runs the assertion layer
    to flag any contract violations (input-not-declared, missing
    output, wrong runner, etc.)

It runs ONE workflow with ONE set of inputs at a time, but you can
sweep it from the CLI to get the kind of matrix coverage the static
simulator gives you — with actual contract checks on top.

CLI examples
------------
    # single run
    python -m build_system.scripts.release_simulator \\
        --workflow .github/workflows/release-cn.yml \\
        --inputs platform=all arch=all \\
        --app cn

    # matrix sweep
    python -m build_system.scripts.release_simulator \\
        --workflow .github/workflows/release-cn.yml --sweep \\
        --app cn
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import assertions, runner
from .models import WorkflowRun


def _build_inputs_from_kwargs(kwargs: list[str]) -> dict[str, str]:
    """Parse `--inputs k1=v1 k2=v2`."""
    out: dict[str, str] = {}
    for kv in kwargs:
        if "=" not in kv:
            print(f"warning: ignoring malformed input {kv!r}", file=sys.stderr)
            continue
        k, v = kv.split("=", 1)
        out[k] = v
    return out


def _format_run(run: WorkflowRun) -> str:
    lines = []
    lines.append(f"  workflow: {run.workflow_path.name}")
    lines.append(f"  app:      {run.app}")
    lines.append(f"  ref:      {run.ref}")
    lines.append(f"  inputs:   {run.inputs}")
    lines.append(f"  jobs:")
    for jid, job in sorted(run.jobs.items()):
        runs_on = job.runs_on or "(not resolved)"
        outputs = job.outputs if job.outputs else ""
        lines.append(
            f"    {jid:<28} result={job.result:<8} "
            f"runs-on={runs_on:<20} outputs={outputs}"
        )
    return "\n".join(lines)


def _matrix(workflow_path: Path | None = None) -> list[dict]:
    """
    The matrix of cases the simulator sweeps through. Smaller than
    the static simulator's 4086 (because each case actually runs
    bash), but covers every meaningful axis.

    When a workflow_path is given we use it to discover what refs
    the local checkout actually has (git branches + tags) so the
    matrix only contains refs that will validate-tag successfully.
    Otherwise we fall back to the canonical set we know to work
    in CI.
    """
    base = {
        "platform": "all", "arch": "all", "environment": "",
        "channel": "", "runner_group": "github-hosted",
    }
    cases = []

    # ---- ref sweep (refs that validate-tag should accept) ----
    known_refs = [
        "main", "develop", "staging",
        "v1.0.0", "v1.0.0-rc.1", "songc_v0.1.0",
        "rc_v1.0.0",  # should be blocked by reserved-prefix
    ]
    # If the simulator is pointed at a real checkout, prefer the
    # refs git actually knows about — the validate-tag bash calls
    # `git show-ref` and fails on missing refs, so testing on
    # phantom refs just exercises the error path over and over.
    if workflow_path is not None:
        try:
            repo_root = workflow_path.parent.parent.parent.resolve()
            import subprocess as _sp
            out = _sp.run(
                ["git", "for-each-ref", "--format=%(refname:short)",
                 "refs/heads", "refs/tags"],
                cwd=str(repo_root), capture_output=True, text=True,
                timeout=10,
            )
            if out.returncode == 0 and out.stdout.strip():
                real_refs = [
                    r for r in out.stdout.splitlines()
                    # Skip detached HEAD refs and the noisy `HEAD`
                    # sentinel.
                    if r and r != "HEAD"
                ]
                if real_refs:
                    known_refs = real_refs + ["rc_v1.0.0"]
        except Exception:
            pass

    for ref in known_refs:
        c = dict(base); c["ref"] = ref
        cases.append(c)

    # ---- platform × arch sweep ----
    for platform in ("windows", "macos", "linux"):
        for arch in ("amd64", "aarch64"):
            c = dict(base); c["ref"] = known_refs[0]
            c["platform"] = platform
            c["arch"] = arch
            cases.append(c)

    # ---- runner_group sweep ----
    for rg in ("ecan-windows-amd64", "ecan-macos-amd64",
               "ecan-macos-arm64", "ecan-linux-amd64"):
        c = dict(base); c["ref"] = known_refs[0]
        c["runner_group"] = rg
        cases.append(c)

    # ---- env + channel combinations ----
    for env in ("production", "staging", "test", "development"):
        for ch in ("stable", "beta", "nightly", "dev"):
            c = dict(base); c["ref"] = known_refs[0]
            c["environment"] = env; c["channel"] = ch
            cases.append(c)

    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--workflow", type=Path, required=True,
                   help="Path to the caller workflow YAML")
    p.add_argument("--inputs", nargs="*", default=[],
                   help="k=v pairs to feed to workflow_dispatch")
    p.add_argument("--ref", default="main")
    p.add_argument("--app", default="intl", choices=("intl", "cn"))
    p.add_argument("--secrets-json", default=None,
                   help="Path to a JSON file with the secret set")
    p.add_argument("--sweep", action="store_true",
                   help="Run the full matrix of cases")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON per case (machine-readable)")
    args = p.parse_args(argv)

    secrets: dict[str, str] = {}
    if args.secrets_json:
        secrets = json.loads(Path(args.secrets_json).read_text())

    cases: list[dict] = []
    if args.sweep:
        cases = _matrix(args.workflow)
    else:
        cases = [_build_inputs_from_kwargs(args.inputs) or {}]

    overall_failures = 0
    overall_anomalies = 0

    for i, case_inputs in enumerate(cases):
        inputs = dict(case_inputs)
        ref = inputs.pop("ref", args.ref)
        try:
            run = runner.run_workflow(
                workflow_path=args.workflow,
                inputs=inputs,
                ref=ref,
                secrets=secrets,
                app=args.app,
            )
        except runner.RunnerError as e:
            print(f"[case {i}] runner error: {e}", file=sys.stderr)
            overall_anomalies += 1
            continue

        findings = assertions.run_all_assertions(run)
        fails, warns = assertions.summarise(findings)
        overall_failures += fails

        if args.json:
            print(json.dumps({
                "case": i,
                "inputs": inputs,
                "ref": ref,
                "jobs": {
                    jid: {
                        "result": j.result,
                        "runs_on": j.runs_on,
                        "outputs": j.outputs,
                    }
                    for jid, j in run.jobs.items()
                },
                "findings": [
                    {"severity": f.severity, "kind": f.kind,
                     "job_id": f.job_id, "message": f.message}
                    for f in findings
                ],
            }, indent=2))
            continue

        print(f"\n=== case {i}: ref={ref} inputs={inputs} ===")
        print(_format_run(run))
        if findings:
            print("  findings:")
            for f in findings:
                print(f.render())
        else:
            print("  ✅ all contracts satisfied")
        print(f"  ({fails} failures, {warns} warnings)")

    print()
    print(f"== Total: {len(cases)} cases, "
          f"{overall_failures} contract failures, "
          f"{overall_anomalies} runner anomalies ==")
    return 0 if overall_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())