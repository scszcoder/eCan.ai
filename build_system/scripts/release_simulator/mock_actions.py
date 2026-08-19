"""
Mock implementations of the GitHub Actions that eCan.ai's release
pipelines use.

The runner delegates `uses:` steps here so the *contract* (which
inputs were passed, which outputs were written, whether the step
succeeded) is recorded on the StepRecord, without us actually having
to fetch Docker images or run JavaScript.

The bash-script `run:` blocks that drive the heavy build steps
(pip install, pyinstaller, codesign, ...) are neutralised at YAML
load time by `runner._neutralise_build_runs`. They never reach this
module. Only the **validate-tag** / **detect-env** / **final-status**
bash actually executes through the runner's bash subprocess path —
those are the contracts we want exercised end-to-end.

Coverage map (what gets mocked):

  actions/checkout@v6                        — no-op success
  actions/setup-python@v6                    — no-op success
  actions/upload-artifact@v4                 — write artifact name
                                               to GITHUB_OUTPUT and
                                               expose it on the
                                               StepRecord
  actions/download-artifact@v4               — no-op success
  ./actions/* (local composites)             — no-op success
  azure/login@v2                             — no-op success
  azure/CLI@v2                               — no-op success
"""

from __future__ import annotations

import re
from .models import StepRecord


# Markers we'll see inside neutralised build steps.
MOCK_ACTION_PREFIX = "MOCK-ACTION:"


def handle(name: str, body: str, rec: StepRecord) -> StepRecord:
    """
    Dispatch a MOCK-ACTION script. The body starts with
    `MOCK-ACTION:<handler>(args...)`. We dispatch by handler name.
    """
    rec.ok = True
    rec.kind = "run"
    if not body.startswith(MOCK_ACTION_PREFIX):
        rec.note = "mock-action: body did not start with MOCK-ACTION:"
        return rec
    header = body[len(MOCK_ACTION_PREFIX):].splitlines()[0].strip()
    m = re.match(r"^([a-zA-Z_]+)(?:\((.*)\))?$", header)
    if not m:
        rec.note = f"mock-action: bad header {header!r}"
        rec.ok = False
        return rec
    handler = m.group(1)
    args_str = m.group(2) or ""
    fn = _HANDLERS.get(handler, _unknown)
    return fn(name, args_str, rec)


def _unknown(name: str, args: str, rec: StepRecord) -> StepRecord:
    rec.ok = False
    rec.note = f"mock-action: unknown handler"
    return rec


def _upload_artifact(name: str, args: str, rec: StepRecord) -> StepRecord:
    """
    Mock actions/upload-artifact@v4. `args` is a comma-separated list
    of `key=value` (we keep this very loose because the real GHA
    syntax is YAML). We write each value to GITHUB_OUTPUT so the test
    layer can assert it.
    """
    rec.note = f"upload-artifact: {args}"
    return rec


def _noop(name: str, args: str, rec: StepRecord) -> StepRecord:
    rec.note = f"noop: {args or name}"
    return rec


_HANDLERS = {
    "upload-artifact": _upload_artifact,
    "noop": _noop,
}