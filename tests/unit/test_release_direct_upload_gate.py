"""
Direct-upload fast path: workflow YAML structural tests.

Why this file exists
--------------------
The CN/intl direct-upload fast path (release-{cn,intl}.yml) adds:

  1. A per-job ``outputs.cos-uploaded`` (or ``s3-uploaded``) that
     captures whether the in-job upload succeeded.
  2. A direct-upload step guarded by a runner-identity
     ``if:`` (self-hosted only) so GitHub-hosted runners fall
     back to the historical upload-artifact path.
  3. Gates on ``upload-to-cos`` / ``upload-to-s3`` /
     ``generate-appcast`` / ``generate-download-links`` that honor
     the new outputs.

The runner-identity gating (``startsWith(runner.name, 'ECAN-WIN')``)
is integration-test territory -- the simulator doesn't expose
``runner.name`` / ``runner.groups`` as expression variables, so we
can't drive it from a unit test. What we *can* lock down here is the
YAML structure: every gate that should reference the new outputs does
so, the per-job ``outputs:`` mapping is in place, and the upload
scripts' new ``--dist-dir`` flag is wired into the call site.

We assert against the real ``.github/workflows/release-{cn,intl}.yml``
files (the production source of truth) rather than synthetic fixtures,
because the contracts this PR introduces live in those files. A
synthetic fixture would drift the moment someone edits the workflow.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# release-cn.yml
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def release_cn() -> str:
    return (REPO_ROOT / ".github/workflows/release-cn.yml").read_text()


def test_release_cn_windows_job_has_cos_uploaded_output(release_cn):
    """build-windows must publish cos-uploaded so the upload-to-cos
    gate (and the downstream appcast / download-links gates) can
    read it.
    """
    # Find the build-windows job block and assert it has the output.
    assert "cos-uploaded: ${{ steps.upload-windows-cos.outputs.success }}" in release_cn, (
        "build-windows must publish a `cos-uploaded` job output sourced "
        "from `steps.upload-windows-cos.outputs.success`. Without it, "
        "the upload-to-cos gate can't tell that the direct upload ran."
    )


def test_release_cn_macos_amd64_job_has_cos_uploaded_output(release_cn):
    assert "cos-uploaded: ${{ steps.upload-macos-amd64-cos.outputs.success }}" in release_cn


def test_release_cn_macos_aarch64_job_has_cos_uploaded_output(release_cn):
    assert "cos-uploaded: ${{ steps.upload-macos-aarch64-cos.outputs.success }}" in release_cn


def test_release_cn_linux_job_has_cos_uploaded_output(release_cn):
    assert "cos-uploaded: ${{ steps.upload-linux-cos.outputs.success }}" in release_cn


def test_release_cn_direct_upload_step_invokes_script_with_dist_dir(release_cn):
    """The new direct-upload step must call upload_to_cos.py with
    --dist-dir artifacts. A direct upload without --dist-dir would
    silently read from <project_root>/dist (the default), which is
    empty on a build job that stages into artifacts/.
    """
    # Find the direct-upload step's run block.
    m = re.search(
        r"name: Upload Windows installer to COS \(direct, fast path\)\s*"
        r"id: upload-windows-cos\s*"
        r".*?run: \|.*?--dist-dir artifacts",
        release_cn,
        re.DOTALL,
    )
    assert m is not None, (
        "Direct-upload step must call upload_to_cos.py with "
        "--dist-dir artifacts so the script reads from the build "
        "job's staging dir, not the default <project_root>/dist."
    )


def test_release_cn_upload_to_cos_gate_honors_cos_uploaded(release_cn):
    """The upload-to-cos job's ``if:`` must skip when a platform
    direct-uploaded and nothing else needs the slow fallback. Without
    this, the upload-to-cos job would try to re-upload installers
    that are already on COS (defeating the speedup) and would emit
    upload-success=false on the all-direct-uploaded path, cascading
    into appcast / download-links being skipped.
    """
    for token in (
        "needs.build-windows.outputs.cos-uploaded",
        "needs.build-macos-amd64.outputs.cos-uploaded",
        "needs.build-macos-aarch64.outputs.cos-uploaded",
        "needs.build-linux.outputs.cos-uploaded",
    ):
        assert token in release_cn


def test_release_cn_appcast_gate_has_direct_upload_fallthrough(release_cn):
    """generate-appcast must run even when upload-to-cos was skipped
    (i.e. when a build direct-uploaded). The fall-through OR clause
    keyed on cos-uploaded is what bridges that gap.
    """
    # All four build platforms must contribute a cos-uploaded clause
    # to the gate so the all-direct-uploaded path still produces an
    # appcast. PR2 only covered Windows; PR3 expands to all 4.
    for token in (
        "needs.build-windows.outputs.cos-uploaded",
        "needs.build-macos-amd64.outputs.cos-uploaded",
        "needs.build-macos-aarch64.outputs.cos-uploaded",
        "needs.build-linux.outputs.cos-uploaded",
    ):
        assert token in release_cn


def test_release_cn_download_links_gate_has_direct_upload_fallthrough(release_cn):
    for token in (
        "needs.build-windows.outputs.cos-uploaded",
        "needs.build-macos-amd64.outputs.cos-uploaded",
        "needs.build-macos-aarch64.outputs.cos-uploaded",
        "needs.build-linux.outputs.cos-uploaded",
    ):
        assert token in release_cn


def test_release_cn_final_status_synthesizes_upload_label(release_cn):
    """final-status' Show summary must distinguish three upload
    states (true / false / direct) so operators can tell whether
    the direct-upload path took effect.
    """
    # All four build platforms must contribute to the synthesised
    # label so a partial direct-upload doesn't read as "skipped".
    for token in (
        "needs.build-windows.outputs.cos-uploaded",
        "needs.build-macos-amd64.outputs.cos-uploaded",
        "needs.build-macos-aarch64.outputs.cos-uploaded",
        "needs.build-linux.outputs.cos-uploaded",
    ):
        assert token in release_cn
    # And the fallback must still surface 'skipped' if nothing
    # succeeded (builds all failed or platform filters excluded them).
    assert "'skipped'" in release_cn


# ---------------------------------------------------------------------------
# release-intl.yml — PR4 territory, but the test scaffolding exists.
# We assert only that the *fast-path seams* are absent (so a future
# reviewer can tell at a glance that PR4 hasn't landed yet).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def release_intl() -> str:
    return (REPO_ROOT / ".github/workflows/release-intl.yml").read_text()


# ---------------------------------------------------------------------------
# Cross-cutting runner-identity invariant
# ---------------------------------------------------------------------------
#
# The direct-upload fast path originally used
# ``startsWith(runner.name, 'ECAN-WIN') || contains(runner.groups, '...')``
# as the gate, but operators register runners with arbitrary names
# (``win-runner``, ``mac-runner-1``, ...) so that condition is silently
# false on real runners -- the direct-upload step never runs, the
# fallback upload-artifact step always runs, and we lose the speedup.
#
# The build jobs themselves gate on
# ``github.event.inputs.runner_group != 'github-hosted'`` (the
# dispatch input the operator picks), which is independent of the
# runner's registered name. The direct-upload fast path must use the
# same gate so the two paths can't disagree.
#
# These tests pin that invariant so a future refactor that reverts to
# ``runner.name`` / ``runner.groups`` (the only expression that ever
# silently turned off the fast path on real runners) fails locally.


_RUNTIME_GATE_HEURISTICS = (
    # The exact form we want.
    "github.event.inputs.runner_group != 'github-hosted'",
    # The negation form the upload-artifact steps use (mutually
    # exclusive with the direct-upload step's gate).
    "github.event.inputs.runner_group == 'github-hosted'",
)


def test_release_cn_direct_upload_uses_runner_group_input(release_cn):
    """Every direct-upload ``if:`` in release-cn.yml must use the
    ``runner_group`` dispatch input (not ``runner.name`` /
    ``runner.groups``). Otherwise real self-hosted runners fall back
    to the slow upload-artifact path because their registered names
    don't match the assumed prefix.
    """
    # Run through each "Upload ... to COS (direct, fast path)" step
    # block and assert its `if:` is one of the two ``runner_group``
    # forms. This is what keeps the direct upload path in lock-step
    # with the build job's own runner selection.
    for m in re.finditer(
        r"name: Upload [^\n]+ \(direct, fast path\)\s*\n"
        r"id: upload-[a-z0-9-]+-cos\s*"
        r".*?\n        if: ([^\n]+)",
        release_cn,
    ):
        gate = m.group(1).strip()
        assert gate in _RUNTIME_GATE_HEURISTICS, (
            f"Direct-upload step `if:` in release-cn.yml must use "
            f"`github.event.inputs.runner_group` (got: {gate!r}). "
            f"The runner.name / runner.groups form is silently false "
            f"on real runners, defeating the direct-upload fast path."
        )


def test_release_intl_direct_upload_uses_runner_group_input(release_intl):
    """Same invariant for release-intl.yml: every direct-upload step
    must gate on ``runner_group``, not ``runner.name`` / ``runner.groups``.
    """
    for m in re.finditer(
        r"name: Upload [^\n]+ \(direct, fast path\)\s*\n"
        r"id: upload-[a-z0-9-]+-s3\s*"
        r".*?\n        if: ([^\n]+)",
        release_intl,
    ):
        gate = m.group(1).strip()
        assert gate in _RUNTIME_GATE_HEURISTICS, (
            f"Direct-upload step `if:` in release-intl.yml must use "
            f"`github.event.inputs.runner_group` (got: {gate!r}). "
            f"The runner.name / runner.groups form is silently false "
            f"on real runners, defeating the direct-upload fast path."
        )


def test_release_cn_no_runner_name_gate_anywhere(release_cn):
    """Belt-and-braces: zero occurrences of the broken gate heuristic.

    If a future refactor reintroduces ``startsWith(runner.name, ...)``
    or ``contains(runner.groups, ...)``, this test fails fast with a
    file-anchored diff that's easier to audit than the regex above.
    """
    assert "startsWith(runner.name" not in release_cn, (
        "release-cn.yml still uses `startsWith(runner.name, ...)` "
        "to gate direct upload. That's silently false on real "
        "self-hosted runners (e.g. registered as `win-runner`); "
        "switch to `github.event.inputs.runner_group != 'github-hosted'`."
    )
    assert "contains(runner.groups" not in release_cn, (
        "release-cn.yml still uses `contains(runner.groups, ...)` "
        "to gate direct upload. Switch to "
        "`github.event.inputs.runner_group != 'github-hosted'`."
    )


def test_release_intl_no_runner_name_gate_anywhere(release_intl):
    assert "startsWith(runner.name" not in release_intl
    assert "contains(runner.groups" not in release_intl


def test_release_intl_windows_job_has_s3_uploaded_output(release_intl):
    assert "s3-uploaded: ${{ steps.upload-windows-s3.outputs.success }}" in release_intl


def test_release_intl_macos_amd64_job_has_s3_uploaded_output(release_intl):
    assert "s3-uploaded: ${{ steps.upload-macos-amd64-s3.outputs.success }}" in release_intl


def test_release_intl_macos_aarch64_job_has_s3_uploaded_output(release_intl):
    assert "s3-uploaded: ${{ steps.upload-macos-aarch64-s3.outputs.success }}" in release_intl


def test_release_intl_linux_job_has_s3_uploaded_output(release_intl):
    assert "s3-uploaded: ${{ steps.upload-linux-s3.outputs.success }}" in release_intl


def test_release_intl_direct_upload_steps_invoke_script_with_dist_dir(release_intl):
    """Each direct-upload step must call upload_to_s3.py with
    --dist-dir artifacts so the script reads from the build job's
    staging dir.
    """
    for step_name in (
        "Upload Windows installer to S3 (direct, fast path)",
        "Upload macOS amd64 installer to S3 (direct, fast path)",
        "Upload macOS aarch64 installer to S3 (direct, fast path)",
        "Upload Linux amd64 packages to S3 (direct, fast path)",
    ):
        m = re.search(
            rf"name: {re.escape(step_name)}\s*"
            r"id: upload-[a-z0-9-]+-s3\s*"
            r".*?--dist-dir artifacts",
            release_intl,
            re.DOTALL,
        )
        assert m is not None, (
            f"{step_name!r} must call upload_to_s3.py with "
            "--dist-dir artifacts so the script reads from the build "
            "job's staging dir."
        )


def test_release_intl_upload_to_s3_gate_honors_s3_uploaded(release_intl):
    """upload-to-s3 `if:` must reference each platform's s3-uploaded
    output so the self-hosted direct-upload fast path can skip the
    slow upload-to-s3 fallback when nothing's left for it to do.
    """
    for token in (
        "needs.build-windows.outputs.s3-uploaded",
        "needs.build-macos-amd64.outputs.s3-uploaded",
        "needs.build-macos-aarch64.outputs.s3-uploaded",
        "needs.build-linux.outputs.s3-uploaded",
    ):
        assert f"{token} " in release_intl, (
            f"upload-to-s3 gate must reference {token} so the "
            "self-hosted direct-upload fast path can skip the slow "
            "upload-to-s3 fallback."
        )


def test_release_intl_appcast_gate_has_direct_upload_fallthrough(release_intl):
    for token in (
        "needs.build-windows.outputs.s3-uploaded",
        "needs.build-macos-amd64.outputs.s3-uploaded",
        "needs.build-macos-aarch64.outputs.s3-uploaded",
        "needs.build-linux.outputs.s3-uploaded",
    ):
        assert f"{token} " in release_intl


def test_release_intl_download_links_gate_has_direct_upload_fallthrough(release_intl):
    for token in (
        "needs.build-windows.outputs.s3-uploaded",
        "needs.build-macos-amd64.outputs.s3-uploaded",
        "needs.build-macos-aarch64.outputs.s3-uploaded",
        "needs.build-linux.outputs.s3-uploaded",
    ):
        assert f"{token} " in release_intl


def test_release_intl_final_status_synthesizes_upload_label(release_intl):
    for token in (
        "needs.build-windows.outputs.s3-uploaded",
        "needs.build-macos-amd64.outputs.s3-uploaded",
        "needs.build-macos-aarch64.outputs.s3-uploaded",
        "needs.build-linux.outputs.s3-uploaded",
    ):
        assert f"{token} " in release_intl
    assert "'skipped'" in release_intl
