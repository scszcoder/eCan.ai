"""eCan.ai release-pipeline simulator.

A full executor (bash, reusable-workflow resolution, contract
assertions) that complements the static 4086-case simulator.

Modules:
    expr        — GitHub Actions ${{ ... }} expression evaluator
    models      — dataclasses for WorkflowRun / JobRecord / StepRecord
    runner      — the orchestrator (load YAML, walk jobs, run steps)
    mock_actions — stub implementations for the actions we use
    assertions  — post-run contract checks
"""
from . import expr, models, runner, mock_actions, assertions

__all__ = ["expr", "models", "runner", "mock_actions", "assertions"]