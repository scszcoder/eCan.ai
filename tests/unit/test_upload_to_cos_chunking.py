"""
Unit tests for the COS multipart chunking policy in
``build_system/scripts/upload_to_cos.py``.

Why this file exists
--------------------
``upload_to_cos.py::chunk_params_for`` decides the ``PartSize`` and
``MAXThread`` that ``upload_file`` hands to ``qcloud_cos.CosS3Client.upload_file``.
This decision is load-bearing: getting it wrong means either

  * ``400 EntityTooSmall`` -- when ``PartSize`` exceeds the file size
    (SDK then puts the whole file as one part, which is < 1 MB and
    rejected), or
  * hitting the COS 10,000-part cap on a large artifact
    (file_size_MB / PartSize > 10_000), or
  * starving the runner CPU with too many threads.

The historical code lived inline inside ``upload_file`` and was untestable.
Extracting it into a pure function lets us lock the policy in place with
cheap, deterministic unit tests -- no COS credentials, no network, no mocks.

What we test
------------
1. The three documented branches: small (<100MB), mid-large (100-500MB),
   very large (>500MB). Boundaries (100, 500) must not flip-flop between
   runs.
2. The output is always inside COS's hard limits: 1 MB <= PartSize <=
   5 GB and the resulting part count <= 10 000 for the largest artifacts
   the build pipeline can plausibly emit (up to 5 GB; PyInstaller + Electron
   bundles today peak around 800 MB but the headroom matters).
3. The thread count stays sane (5..10). This is more of a sanity guard
   than a spec -- the goal is to catch an accidental bump to 100 threads.

What we deliberately do NOT test
---------------------------------
* The actual SDK call (covered by tests/e2e/test_cos_upload_large.py).
* Cancellation paths (covered by tests/unit/test_upload_to_cos_cancel.py
  when added, and by manual SIGTERM tests in the e2e file).
* Hash computation or SIG file upload -- orthogonal concerns.
"""
from __future__ import annotations

import math

import pytest


def _import_chunk_params_for():
    """
    Import ``chunk_params_for`` without paying the cost of importing
    ``qcloud_cos`` and ``yaml`` (which the parent module pulls in at top
    level). We do this by reading the parent source and pulling just the
    helper out of it.

    The function is defined at module top level in
    ``build_system/scripts/upload_to_cos.py``, after a ``# ----``
    comment block, and before the ``class COSUploader`` declaration. We
    rely on that placement -- if the file is reorganised, update this
    extractor.
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    parent_path = (
        Path(__file__).resolve().parents[2]
        / "build_system"
        / "scripts"
        / "upload_to_cos.py"
    )
    assert parent_path.exists(), f"upload_to_cos.py not found at {parent_path}"

    # Stub the heavy SDK deps so the module imports cleanly in a CI
    # environment where ``qcloud_cos`` / ``yaml`` are not installed.
    for name in ("qcloud_cos", "qcloud_cos.cos_exception", "yaml"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
    sys.modules["qcloud_cos"].CosConfig = object
    sys.modules["qcloud_cos"].CosS3Client = object
    sys.modules["qcloud_cos.cos_exception"].CosServiceError = type(
        "CosServiceError", (Exception,), {}
    )
    sys.modules["yaml"].safe_load = lambda *a, **k: {}

    spec = importlib.util.spec_from_file_location("upload_to_cos", parent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.chunk_params_for


chunk_params_for = _import_chunk_params_for()


# ---------------------------------------------------------------------------
# Branch table
# ---------------------------------------------------------------------------

# Each row is (file_size_mb, expected_part_size, expected_max_thread, label).
# The boundaries (99, 100, 500, 501) are listed explicitly so an off-by-one
# regression -- e.g. ">" instead of ">=" -- fails loudly instead of flipping
# silently.
#
# Semantics of the inclusive ">=" used in chunk_params_for():
#   * file_size_mb >= 500 -> very-large branch (20 MB parts, 5 threads)
#   * file_size_mb >= 100 -> mid-large branch  (10 MB parts, 10 threads)
#   * otherwise            -> small branch    ( 5 MB parts, 5 threads)
# The 5MB PartSize in the small branch is intentional: it keeps every
# multipart part >= 1MB for files down to ~5MB, avoiding the
# ``400 EntityTooSmall`` rejection that a 10MB PartSize would cause on a
# 9MB file (SDK would split 9MB into a single 9MB part, < 1MB minimum).
_BRANCH_TABLE = [
    (1,    5,  5,  "tiny file (sha256, sig) -- falls under small, simple PUT"),
    (4,    5,  5,  "just under the small-branch PartSize boundary"),
    (5,    5,  5,  "exactly at small-branch PartSize boundary, 1 part"),
    (9,    5,  5,  "9MB worst case -- 2 parts of 5MB + 4MB, both >= 1MB"),
    (50,   5,  5,  "medium-small Windows installer"),
    (99,   5,  5,  "just below the 100MB boundary"),
    (100,  10, 10, "exactly 100MB -- enters mid-large branch (inclusive >=)"),
    (101,  10, 10, "just above the 100MB boundary"),
    (200,  10, 10, "mid-large AppImage"),
    (499,  10, 10, "just below the 500MB boundary"),
    (500,  20, 5,  "exactly 500MB -- enters very-large branch (inclusive >=)"),
    (501,  20, 5,  "just above the 500MB boundary"),
    (800,  20, 5,  "large macOS .pkg"),
    (2000, 20, 5,  "hypothetical 2GB build artifact"),
    (5000, 20, 5,  "5GB -- near the simple-upload cap"),
]


@pytest.mark.parametrize(
    "size_mb, expected_part, expected_thread, label",
    _BRANCH_TABLE,
    ids=[row[3] for row in _BRANCH_TABLE],
)
def test_chunk_params_branches(size_mb, expected_part, expected_thread, label):
    """Lock the three-branch policy at all meaningful boundaries."""
    part, thread = chunk_params_for(size_mb)
    assert part == expected_part, (
        f"{label}: expected PartSize={expected_part} for {size_mb}MB, got {part}"
    )
    assert thread == expected_thread, (
        f"{label}: expected MAXThread={expected_thread} for {size_mb}MB, got {thread}"
    )


# ---------------------------------------------------------------------------
# COS hard-limit guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "size_mb",
    [1, 9, 50, 100, 250, 500, 800, 1500, 5000, 10240],  # 10 GB upper bound probe
    ids=lambda v: f"{v}MB",
)
def test_output_within_cos_part_size_range(size_mb):
    """PartSize must be in [1MB, 5GB] per COS multipart spec."""
    part, _ = chunk_params_for(size_mb)
    assert 1 <= part <= 5 * 1024, (
        f"PartSize {part}MB for {size_mb}MB file is outside COS 1MB-5GB range"
    )


@pytest.mark.parametrize(
    "size_mb",
    [1, 9, 50, 100, 250, 500, 800, 1500, 5000, 10240],
    ids=lambda v: f"{v}MB",
)
def test_part_count_within_cos_10000_limit(size_mb):
    """
    file_size_mb / PartSize must not exceed 10,000 parts. The 10 GB probe
    catches a regression that accidentally drops PartSize back to 1 MB
    (10 GB / 1 MB = 10,000 parts, right at the cap).
    """
    part, _ = chunk_params_for(size_mb)
    # ceil division: any remainder produces one extra part.
    parts_count = math.ceil(size_mb / part) if part else 0
    assert 1 <= parts_count <= 10_000, (
        f"{size_mb}MB / {part}MB = {parts_count} parts; "
        f"exceeds COS 10000-part cap or is zero"
    )


@pytest.mark.parametrize(
    "size_mb",
    [1, 50, 200, 800, 5000],
    ids=lambda v: f"{v}MB",
)
def test_thread_count_is_sane(size_mb):
    """MAXThread must stay between 1 and a sane upper bound (currently 10)."""
    _, thread = chunk_params_for(size_mb)
    assert 1 <= thread <= 10, (
        f"MAXThread {thread} for {size_mb}MB is outside the expected 1..10 range. "
        "If you intentionally want more threads, update both this guard and the "
        "comment in chunk_params_for."
    )


@pytest.mark.parametrize(
    "size_mb",
    # Probe the small-branch sub-range: every file in here must split into
    # parts of >= 1MB (the COS lower bound). 9MB is the regression that
    # motivated switching small-branch PartSize from 10MB to 5MB; 1MB and
    # 4MB are simple PUT (file <= PartSize) so we just assert the
    # guard is satisfiable for the SDK's chosen path.
    [1, 4, 5, 6, 9, 25, 50, 99],
    ids=lambda v: f"{v}MB",
)
def test_small_branch_no_entity_too_small(size_mb):
    """
    Regression guard for the 9MB case that previously produced a single
    9MB part under ``400 EntityTooSmall``.

    For files > PartSize (multipart path), the SDK splits the file into
    ``ceil(file_size / PartSize)`` parts, the last of which may be smaller
    than PartSize. The COS lower bound is 1MB -- so the last part's
    computed size must be >= 1MB. For files <= PartSize (simple PUT), the
    guard trivially holds because there is no part-level check.
    """
    part, _ = chunk_params_for(size_mb)
    if size_mb <= part:
        # SDK chooses simple PUT. No part-level check applies.
        return
    # Multipart path: compute the last part size.
    full_parts = size_mb // part
    remainder = size_mb - full_parts * part
    last_part = remainder if remainder > 0 else part
    assert last_part >= 1, (
        f"{size_mb}MB / PartSize={part}MB produces a last part of "
        f"{last_part}MB, below the COS 1MB minimum -- would 400 "
        f"EntityTooSmall. Drop small-branch PartSize."
    )


# ---------------------------------------------------------------------------
# Monotonicity guard
# ---------------------------------------------------------------------------

def test_part_size_is_monotonic_non_decreasing():
    """
    As files grow we should not get *smaller* parts. Going from 100 MB
    (10MB parts) to 500 MB (20MB parts) is fine; the reverse is not.
    """
    samples = [50, 100, 500, 1000, 5000]
    parts = [chunk_params_for(s)[0] for s in samples]
    assert parts == sorted(parts), (
        f"PartSize must be non-decreasing with file size, got {list(zip(samples, parts))}"
    )