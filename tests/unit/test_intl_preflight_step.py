"""
Contract test: every Windows build job in `release-intl.yml` must have
the same `Ensure Git Bash + PowerShell 7 are on runner-service PATH
(Windows self-hosted)` preflight step that `release-cn.yml` has.

Background: intl and cn share the same runner class
(`self-hosted,windows,x64,ecan-build`). When an operator runs
`runner_group=ecan-windows-amd64` against the intl workflow, every
Windows job lands on a self-hosted Windows runner — which has the
same PowerShell / bash / ExecutionPolicy requirements as cn.

Without this preflight step, intl on self-hosted fails with the same
opaque `bash: command not found` and `UnauthorizedAccess` errors that
the cn preflight step was introduced to surface.

Without this contract test, future refactors of release-intl.yml
could silently drop the preflight step and reintroduce the bug.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
INTL = REPO / ".github/workflows/release-intl.yml"
CN = REPO / ".github/workflows/release-cn.yml"


def _wf_jobs(path: Path) -> dict:
    """Load YAML and return the jobs dict of the first document."""
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return docs[0]["jobs"]


# ---------------------------------------------------------------------------
# Step presence: intl Windows jobs must each have a preflight step.
# ---------------------------------------------------------------------------

JOBS_REQUIRING_PREFLIGHT = [
    "build-windows",
    "validate-tag",  # Windows runner host can run validate-tag too
]


@pytest.mark.parametrize("workflow", [INTL, CN], ids=["intl", "cn"])
@pytest.mark.parametrize("job_name", JOBS_REQUIRING_PREFLIGHT)
def test_job_has_preflight_step(workflow: Path, job_name: str):
    jobs = _wf_jobs(workflow)
    assert job_name in jobs, f"{workflow.name}: job `{job_name}` not found"
    steps = jobs[job_name].get("steps", [])
    preflight_names = [s.get("name", "") for s in steps if "Ensure Git Bash" in s.get("name", "")]
    assert preflight_names, (
        f"{workflow.name}: job `{job_name}` must contain the "
        "`Ensure Git Bash + PowerShell 7 are on runner-service PATH "
        "(Windows self-hosted)` preflight step. Without it, "
        "self-hosted runners fail with `bash: command not found` "
        "before the first build step. Found step names: "
        f"{[s.get('name','') for s in steps]}"
    )


# ---------------------------------------------------------------------------
# Step body symmetry: intl preflight body must match cn (so the contract
# stays identical across both pipelines).
# ---------------------------------------------------------------------------

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _extract_preflight_body(text: str) -> str:
    """Return the raw `run:` block of the preflight step (the heredoc body)."""
    docs = list(yaml.safe_load_all(text))
    for job in docs[0]["jobs"].values():
        for s in job.get("steps", []):
            if "Ensure Git Bash" in s.get("name", ""):
                return s.get("run", "")
    raise AssertionError("Could not find preflight step")


def test_intl_preflight_body_matches_cn():
    """The intl preflight body must be byte-identical to the cn preflight
    body. If cn's body evolves (e.g. add a Chocolatey probe), intl's
    body must evolve in lockstep. Otherwise intl on self-hosted
    silently regresses to a state without the operator's tooling."""
    intl_body = _extract_preflight_body(_read(INTL))
    cn_body = _extract_preflight_body(_read(CN))
    assert intl_body == cn_body, (
        "intl preflight body diverged from cn preflight body. The "
        "two workflows run on the same runner class and must have "
        "the identical preflight contract. Run "
        "`diff <(sed -n ... release-intl.yml) <(sed -n ... release-cn.yml)` "
        "to see the divergence."
    )


# ---------------------------------------------------------------------------
# The preflight step must be idempotent (safe on every job rerun).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("workflow", [INTL, CN], ids=["intl", "cn"])
def test_preflight_step_is_idempotent(workflow: Path):
    """Each preflight step must be idempotent: when Git Bash, PowerShell 7,
    and ExecutionPolicy are already correct, the step is a no-op (a few
    `Test-Path` + `Get-ExecutionPolicy` calls). Otherwise every job
    re-pays the install cost."""
    body = _extract_preflight_body(_read(workflow))
    assert "Test-Path $gitBashBin" in body, "git bash probe missing"
    assert "Test-Path $pwshBin" in body, "pwsh probe missing"
    assert "Get-ExecutionPolicy" in body, "ExecutionPolicy probe missing"


# ---------------------------------------------------------------------------
# The preflight step must NOT install dependencies silently (it must
# surface a precise error pointing to register_runner.ps1 + docs).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("workflow", [INTL, CN], ids=["intl", "cn"])
def test_preflight_emits_error_on_failure(workflow: Path):
    """When a prerequisite is missing AND cannot be auto-installed
    (winget blocked, network blocked), the preflight must emit
    `::error::` annotation pointing the operator at register_runner.ps1 +
    docs. Otherwise the failure mode is opaque."""
    body = _extract_preflight_body(_read(workflow))
    assert "::error::" in body, (
        f"{workflow.name}: preflight step must emit `::error::` "
        "annotation when a prerequisite cannot be installed."
    )
    assert "register_runner.ps1" in body, (
        f"{workflow.name}: preflight error message must point at "
        "`register_runner.ps1` so operators know where to fix the "
        "runner baseline."
    )
    assert "Windows构建环境部署清单.md" in body, (
        f"{workflow.name}: preflight error message must link to "
        "docs/Windows构建环境部署清单.md §九.3.1."
    )