"""
Data model for the full release-pipeline simulator.

Three layers, mirroring GitHub Actions:

  Workflow  →  Job  →  Step

Each layer records what happened so downstream steps (and the test
assertions) can verify the *contract* — not the build artefacts.

What is recorded here is intentionally small: result strings, the
mapping from `inputs:` to INPUT_* env vars, the resolved `env:` map,
and the resolved `runs-on` runner label. The runner code that fills
these is in `runner.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# GH Actions canonical result strings.
SUCCESS = "success"
FAILURE = "failure"
SKIPPED = "skipped"
CANCELLED = "cancelled"


@dataclass
class StepRecord:
    """One `step:` inside a job."""
    name: str
    # The YAML `id:` field if the step has one. GH Actions exposes
    # `steps.<id>.outputs.<key>` to subsequent steps and the job's
    # `outputs:` mapping. Without recording this the assertion layer
    # cannot validate the `steps.validate.outputs.valid` style
    # references in `outputs:` maps.
    step_id: str = ""
    # Resolved env at execution time (job env merged with step env).
    env: dict[str, str] = field(default_factory=dict)
    # The GITHUB_OUTPUT map captured during this step. This is what
    # `job.outputs` is built from. Without recording this we cannot
    # verify that `needs.<job>.outputs.X` actually delivers what the
    # step wrote.
    outputs: dict[str, str] = field(default_factory=dict)
    # True if the step's bash exit code was 0.
    ok: bool = True
    # Free-form breadcrumb so assertion failures can tell the user
    # exactly what the simulator did and why.
    note: str = ""
    # What kind of step: "run" (a `run:` block) or "uses" (an action).
    kind: str = "run"


@dataclass
class JobRecord:
    """One `jobs.<id>` entry in the workflow."""
    id: str
    # Resolved runner label after evaluating `runs-on:`. Empty string if
    # the job was skipped before runner resolution.
    runs_on: str = ""
    # GH result string after the job finishes.
    result: str = SKIPPED
    # step records in execution order
    steps: list[StepRecord] = field(default_factory=list)
    # The job's declared outputs (resolved from ${{ steps.<id>.outputs.X }}).
    outputs: dict[str, str] = field(default_factory=dict)
    # Resolved inputs at execution time. For a top-level job this is the
    # workflow_dispatch inputs. For a reusable-workflow caller job this
    # is the `with:` block, resolved for expressions.
    inputs: dict[str, str] = field(default_factory=dict)
    # Resolved secrets visible to the job. For a caller job with
    # `secrets: inherit` this is the parent's full secret set.
    secrets: dict[str, str] = field(default_factory=dict)
    # Raw env block after expression resolution.
    env: dict[str, str] = field(default_factory=dict)
    # Human-readable note for debug.
    note: str = ""


@dataclass
class WorkflowRun:
    """One full run of one workflow with one set of inputs."""
    workflow_path: Path
    workflow_name: str
    app: str  # "intl" | "cn"
    inputs: dict[str, str] = field(default_factory=dict)
    ref: str = ""
    # Jobs keyed by job id; values populated as the run progresses.
    jobs: dict[str, JobRecord] = field(default_factory=dict)
    # Top-level secrets set by the caller of the workflow (the
    # `workflow_dispatch` trigger does not expose a way to set secrets,
    # so this is fed by a CI fixture file).
    secrets: dict[str, str] = field(default_factory=dict)
    # Top-level `env:` block (rarely used in eCan.ai).
    env: dict[str, str] = field(default_factory=dict)
    # Explicit repo-root hint used when the simulator needs to resolve
    # `uses: ./<path>` calls. If unset, the runner infers it from the
    # workflow file's location (parent.parent == ".github" → 3 up).
    workspace: str | None = None
    # Snapshot of the variable namespace used to evaluate
    # `workflow_call.outputs:` mappings for reusable-workflow callers.
    # The runner populates this once per workflow so the output
    # interpolator has the same `${{ ... }}` context the steps saw.
    expr_env_vars: dict[str, Any] = field(default_factory=dict)

    def job(self, jid: str) -> JobRecord:
        if jid not in self.jobs:
            self.jobs[jid] = JobRecord(id=jid)
        return self.jobs[jid]