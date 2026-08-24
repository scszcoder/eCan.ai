"""LightRAG version policy and compatibility decisions.

Keep this module dependency-free so build and launcher tests can import it even
when LightRAG is not installed in the test environment.

eCan tests against LightRAG ≥ 1.5.0 (tested maximum: 1.5.6). Earlier versions
(including the 1.4.x line) are no longer supported: the 1.4-only monkey
patches this launcher used to ship have been removed because they corrupt the
upstream 1.5 pipeline (see docs/lightrag-1.5-upgrade-analysis.md).
"""

from __future__ import annotations

from importlib import metadata

from packaging.version import Version


TARGET_LIGHTRAG_VERSION = "1.5.6"
UPSTREAM_PIPELINE_VERSION = Version("1.5.0")
# 1.5.0 is the floor: that release owns routing, cancellation, bounded
# scheduling and crash recovery natively. Pre-1.5 (1.4.x line) is *below*
# this floor and will not be served by this launcher.
SUPPORTED_MIN_VERSION = Version("1.5.0")
SUPPORTED_MAX_VERSION = Version("1.5.6")


def installed_lightrag_version() -> Version:
    """Return the installed distribution version, or 0 when unavailable."""
    try:
        return Version(metadata.version("lightrag-hku"))
    except metadata.PackageNotFoundError:
        return Version("0")


def use_upstream_pipeline(version: Version | str | None = None) -> bool:
    """Whether upstream owns routes, cancellation, and recovery.

    LightRAG 1.5 introduced managed pipeline cancellation, manual-only failed
    retries, bounded scheduling, and strict recovery. Replacing those internals
    with the copied 1.4 implementation would discard the new guarantees, so
    eCan only supports versions where upstream owns the pipeline (≥ 1.5.0).
    """
    resolved = Version(str(version)) if version is not None else installed_lightrag_version()
    return resolved >= UPSTREAM_PIPELINE_VERSION


def support_status(
    version: Version | str | None = None,
) -> tuple[str, Version]:
    """Classify an installed version against the eCan-supported range.

    Returns ``(status, resolved_version)`` where ``status`` is one of:

    - ``"supported"`` — within ``[SUPPORTED_MIN_VERSION, SUPPORTED_MAX_VERSION]``
    - ``"below_minimum"`` — older than 1.5.0 (the 1.4.x line; no longer supported)
    - ``"above_tested"`` — newer than 1.5.6 (not yet validated by eCan)
    - ``"not_installed"`` — package metadata missing
    """
    resolved = (
        Version(str(version))
        if version is not None
        else installed_lightrag_version()
    )
    if resolved == Version("0"):
        return "not_installed", resolved
    if resolved < SUPPORTED_MIN_VERSION:
        return "below_minimum", resolved
    if resolved > SUPPORTED_MAX_VERSION:
        return "above_tested", resolved
    return "supported", resolved
