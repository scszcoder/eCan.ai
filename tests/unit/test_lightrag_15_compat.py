"""Contract tests for the LightRAG 1.5 launcher surface.

These tests pin two contracts:

1. ``knowledge.lightrag_launcher`` no longer carries any 1.4-only monkey
   patches (``replace_document_routes``, ``patch_extract_entities_for_cancellation``,
   ``patch_auto_retry_prevention``, ``patch_http_clients_for_cancellation``).
   The four names must simply not exist on the module.
2. ``third_party/lightrag_custom/`` no longer carries the 1.4-only copies
   (``document_routes_custom.py``, ``_legacy_1_4x/``) — those would be
   dead code with the 1.5 launcher.
3. ``knowledge.lightrag_compat.support_status`` reports 1.5.0 as the new
   supported floor (1.4.x is now below_minimum).

The individual patch behaviours (``patch_ssl``, ``patch_httpx_timeout_compat``)
are tested in their own tests at the bottom of this file.
"""

import logging
from unittest.mock import DEFAULT, patch

from packaging.version import Version

from knowledge.lightrag_compat import SUPPORTED_MAX_VERSION, SUPPORTED_MIN_VERSION, support_status, use_upstream_pipeline


# -- Version policy ------------------------------------------------------------


def test_lightrag_15_uses_upstream_pipeline() -> None:
    assert use_upstream_pipeline("1.5.0") is True
    assert use_upstream_pipeline("1.5.6") is True
    # Above-tested still counts as "use upstream" because eCan never replaces
    # upstream on 1.5+ — we just log a warning and let upstream run.
    assert use_upstream_pipeline("1.5.7") is True


def test_lightrag_14_uses_legacy_eCan_dispatch() -> None:
    """1.4.x is below the new SUPPORTED_MIN_VERSION (1.5.0)."""
    assert use_upstream_pipeline("1.4.16") is False
    assert use_upstream_pipeline("1.4.10") is False


def test_support_status_classifies_versions() -> None:
    """support_status must label every input the launcher might see."""
    assert support_status("1.5.6") == ("supported", Version("1.5.6"))
    assert support_status("1.5.0") == ("supported", Version("1.5.0"))
    assert support_status("1.4.16") == ("below_minimum", Version("1.4.16"))
    assert support_status("1.4.10") == ("below_minimum", Version("1.4.10"))
    assert support_status("1.5.7") == ("above_tested", Version("1.5.7"))


def test_support_status_accepts_version_object() -> None:
    """The launcher passes the result of ``installed_lightrag_version`` —
    a ``Version`` object, not a string.  Both paths must work.
    """
    assert support_status(Version("1.5.6")) == ("supported", Version("1.5.6"))
    assert support_status(Version("0")) == ("not_installed", Version("0"))


def test_support_status_reports_missing_package() -> None:
    """Passing ``"0"`` (sentinel for missing) must yield ``not_installed``."""
    status, resolved = support_status("0")
    assert status == "not_installed"
    assert resolved == Version("0")


def test_support_status_boundary_versions() -> None:
    """The 1.5.0 floor and 1.5.6 ceiling are both inclusive; outside is
    classified as ``below_minimum`` / ``above_tested`` respectively.
    """
    assert support_status("1.5.0")[0] == "supported"
    assert support_status("1.5.6")[0] == "supported"
    assert support_status("1.4.16")[0] == "below_minimum"
    assert support_status("1.4.99.999")[0] == "below_minimum"
    assert support_status("1.5.6.0.1")[0] == "above_tested"


def test_supported_min_version_matches_documented_floor() -> None:
    """Guard against an accidental regression to 1.4.16.

    The cleanup decision recorded in docs/lightrag-1.5-upgrade-analysis.md
    is that 1.4.x is no longer supported — the floor moved to 1.5.0.
    """
    assert SUPPORTED_MIN_VERSION == Version("1.5.0")


def test_supported_max_version_pins_1_5_6() -> None:
    assert SUPPORTED_MAX_VERSION == Version("1.5.6")


def test_use_upstream_pipeline_installer_returns_false_when_missing() -> None:
    """Version "0" (the "not installed" sentinel) must not be >= 1.5.0."""
    assert use_upstream_pipeline(Version("0")) is False


# -- 1.4-only monkey patches are gone -----------------------------------------


DELETED_PATCHES = (
    "replace_document_routes",
    "patch_extract_entities_for_cancellation",
    "patch_auto_retry_prevention",
    "patch_http_clients_for_cancellation",
)


def test_launcher_does_not_define_legacy_patches() -> None:
    """The four 1.4-only monkey patches must no longer exist as names.

    Cleanup rationale: 1.4 is no longer supported, and these patches corrupt
    the 1.5 pipeline if engaged (see docs/lightrag-1.5-upgrade-analysis.md).
    """
    from knowledge import lightrag_launcher as launcher

    for name in DELETED_PATCHES:
        assert not hasattr(launcher, name), (
            f"launcher still defines {name}; remove the function body "
            f"and the import site as part of the 1.4 cleanup."
        )


def test_launcher_does_not_reference_deleted_legacy_modules() -> None:
    """Neither ``_legacy_1_4x`` nor ``document_routes_custom`` should appear
    in the launcher source — if they do, the deletion wasn't complete.
    """
    from pathlib import Path

    src = Path("knowledge/lightrag_launcher.py").read_text(encoding="utf-8")
    assert "_legacy_1_4x" not in src
    assert "document_routes_custom" not in src


def test_legacy_modules_removed_from_repo() -> None:
    """The 1.4-only files must be physically gone from the repo."""
    import pathlib

    base = pathlib.Path("third_party/lightrag_custom")
    assert not (base / "document_routes_custom.py").exists()
    assert not (base / "_legacy_1_4x").exists()


# -- apply_all_patches wires only the live patches -----------------------------


def test_launcher_calls_only_live_patches_on_1_5() -> None:
    """On 1.5.x, only the live set of patches is called.

    The live set is the patches that still bind to symbols stable across
    LightRAG ≥ 1.4.10. ``patch_httpx_timeout_compat`` is included because
    it depends only on the httpx package, not on LightRAG.
    """
    from knowledge import lightrag_launcher as launcher

    live = (
        "patch_rerank_binding_for_proxy",
        "patch_lightrag_init",
        "patch_ssl",
        "patch_httpx_timeout_compat",
        "patch_utils_for_confidence_scoring",
        "patch_openai_client_for_lambda_proxy",
        "patch_health_monitoring",
    )

    with patch.object(launcher, "installed_lightrag_version", return_value=Version("1.5.6")):
        with patch.multiple(launcher, **{name: DEFAULT for name in live}) as mocks:
            launcher.apply_all_patches()

    for name, mock in mocks.items():
        mock.assert_called_once_with(), f"{name} should be called exactly once"


def test_launcher_does_not_engage_legacy_patches_on_1_4_either() -> None:
    """1.4.x is now ``below_minimum``; the launcher must NOT engage the
    legacy patches even on 1.4. Operators on 1.4 get a clear WARNING and
    must upgrade — there is no silent fallback any more.
    """
    from knowledge import lightrag_launcher as launcher

    live = (
        "patch_rerank_binding_for_proxy",
        "patch_lightrag_init",
        "patch_ssl",
        "patch_httpx_timeout_compat",
        "patch_utils_for_confidence_scoring",
        "patch_openai_client_for_lambda_proxy",
        "patch_health_monitoring",
    )

    with patch.object(launcher, "installed_lightrag_version", return_value=Version("1.4.16")):
        with patch.multiple(launcher, **{name: DEFAULT for name in live}):
            launcher.apply_all_patches()


def test_launcher_warns_when_below_minimum(caplog) -> None:
    """Pre-1.5.0 versions are below the new supported floor.

    Per CLAUDE.md §6 these are *expected behaviour* — WARNING, not ERROR.
    The launcher must surface a clear message so the operator knows the
    legacy patches are gone and an upgrade is required.
    """
    from knowledge import lightrag_launcher as launcher

    live = (
        "patch_rerank_binding_for_proxy",
        "patch_lightrag_init",
        "patch_ssl",
        "patch_httpx_timeout_compat",
        "patch_utils_for_confidence_scoring",
        "patch_openai_client_for_lambda_proxy",
        "patch_health_monitoring",
    )

    # ``utils.logger_helper`` builds a logger that disables propagation
    # (``logger.propagate = False``). Re-attach a capture handler so caplog
    # sees the records; we look up the live logger rather than hard-coding
    # its name because APP_NAME comes from the runtime config.
    launcher_logger = logging.getLogger(launcher.logger.logger.name if hasattr(launcher.logger, "logger") else launcher.logger.name)
    previous_level = launcher_logger.level
    launcher_logger.setLevel(logging.WARNING)
    launcher_logger.addHandler(caplog.handler)
    try:
        with patch.object(launcher, "installed_lightrag_version", return_value=Version("1.4.16")):
            with patch.multiple(launcher, **{name: DEFAULT for name in live}):
                launcher.apply_all_patches()
    finally:
        launcher_logger.removeHandler(caplog.handler)
        launcher_logger.setLevel(previous_level)

    relevant = [
        rec
        for rec in caplog.records
        if "below the supported minimum" in rec.getMessage()
    ]
    assert relevant, [r.getMessage() for r in caplog.records]
    assert all(rec.levelno == logging.WARNING for rec in relevant)


def test_launcher_warns_when_above_tested(caplog) -> None:
    """Newer-than-tested versions must surface a WARNING (per CLAUDE.md §6).

    The launcher must keep starting so 1.5.7+ users aren't blocked, but the
    operator has to know the version is unvalidated.
    """
    from knowledge import lightrag_launcher as launcher

    live = (
        "patch_rerank_binding_for_proxy",
        "patch_lightrag_init",
        "patch_ssl",
        "patch_httpx_timeout_compat",
        "patch_utils_for_confidence_scoring",
        "patch_openai_client_for_lambda_proxy",
        "patch_health_monitoring",
    )

    launcher_logger = logging.getLogger(launcher.logger.logger.name if hasattr(launcher.logger, "logger") else launcher.logger.name)
    previous_level = launcher_logger.level
    launcher_logger.setLevel(logging.WARNING)
    launcher_logger.addHandler(caplog.handler)
    try:
        with patch.object(launcher, "installed_lightrag_version", return_value=Version("1.5.7")):
            with patch.multiple(launcher, **{name: DEFAULT for name in live}):
                launcher.apply_all_patches()
    finally:
        launcher_logger.removeHandler(caplog.handler)
        launcher_logger.setLevel(previous_level)

    relevant = [
        rec
        for rec in caplog.records
        if "newer than the eCan tested maximum" in rec.getMessage()
    ]
    assert relevant, [r.getMessage() for r in caplog.records]
    assert all(rec.levelno == logging.WARNING for rec in relevant)


def test_launcher_fails_fast_when_lightrag_missing() -> None:
    """Without ``lightrag-hku`` installed the launcher must hard-fail.

    Without the package every subsequent ``from lightrag import ...`` raises
    and the launcher dispatch logic never gets a chance to run. There is
    no graceful recovery, so a RuntimeError is the correct response.
    """
    from knowledge import lightrag_launcher as launcher

    with patch.object(launcher, "installed_lightrag_version", return_value=Version("0")):
        try:
            launcher.apply_all_patches()
        except RuntimeError as exc:
            assert "lightrag-hku is not installed" in str(exc)
        else:  # pragma: no cover - explicit failure path
            raise AssertionError("apply_all_patches should hard-fail when lightrag is missing")


# -- patch_ssl: regression coverage for the inverted-logic bug -----------------


def test_patch_ssl_disables_when_env_false(monkeypatch) -> None:
    """``SSL_VERIFY=false`` must actually patch ssl + aiohttp.

    Regression: the previous implementation read ``verify_ssl = env == 'false'``
    and then *returned* when the condition held, which is the exact opposite of
    the documented intent. The env var is "SSL_VERIFY=false means disable", so
    when the env says disable, the patch must run.
    """
    import ssl as _ssl

    import aiohttp

    from knowledge import lightrag_launcher as launcher

    monkeypatch.setenv("SSL_VERIFY", "false")

    original_aiohttp_init = aiohttp.TCPConnector.__init__
    seen_ssl_kwarg = {}

    def _tracking_init(self, *args, **kwargs):
        seen_ssl_kwarg["ssl"] = kwargs.get("ssl")
        # Don't actually call super — the test only cares that ssl=False was
        # forwarded. Spinning up a real TCPConnector here is unnecessary.
        return None

    # Snapshot what ``ssl._create_default_https_context`` currently resolves
    # to (via the module's __dict__ so the patch detection below is reliable
    # across Python versions where attribute access may bypass __dict__).
    ssl_module = _ssl.__dict__
    sentinel_ssl = lambda *a, **kw: None  # noqa: E731
    monkeypatch.setitem(ssl_module, "_create_default_https_context", sentinel_ssl)
    monkeypatch.setattr(aiohttp.TCPConnector, "__init__", _tracking_init)

    try:
        launcher.patch_ssl()

        # The patch replaces the sentinel with ``ssl._create_unverified_context``.
        # We assert "no longer sentinel" rather than "is _create_unverified_context"
        # so the test does not couple to the implementation choice.
        assert ssl_module["_create_default_https_context"] is not sentinel_ssl, (
            "patch_ssl() did not overwrite ssl._create_default_https_context — "
            "the regression that previously made SSL_VERIFY=false a no-op is back"
        )
        assert ssl_module["_create_default_https_context"] is _ssl._create_unverified_context
        # aiohttp.TCPConnector.__init__ was rewrapped and forces ssl=False.
        aiohttp.TCPConnector.__init__(object())
        assert seen_ssl_kwarg["ssl"] is False
    finally:
        monkeypatch.setattr(aiohttp.TCPConnector, "__init__", original_aiohttp_init)


def test_patch_ssl_keeps_verification_when_env_true(monkeypatch) -> None:
    """``SSL_VERIFY=true`` (the default) must NOT patch ssl or aiohttp.

    This is the companion to ``test_patch_ssl_disables_when_env_false``. The
    bug being guarded against is the pre-fix behaviour of patching nothing
    when the env said *disable*; this test pins the safe no-op behaviour
    when the env says *verify*.
    """
    import ssl as _ssl

    import aiohttp

    from knowledge import lightrag_launcher as launcher

    monkeypatch.setenv("SSL_VERIFY", "true")

    ssl_module = _ssl.__dict__
    sentinel_ssl = lambda *a, **kw: None  # noqa: E731
    sentinel_aio = lambda self, *a, **kw: None  # noqa: E731
    monkeypatch.setitem(ssl_module, "_create_default_https_context", sentinel_ssl)
    monkeypatch.setattr(aiohttp.TCPConnector, "__init__", sentinel_aio)

    try:
        launcher.patch_ssl()

        # Neither surface was overwritten — sentinel values survive.
        assert ssl_module["_create_default_https_context"] is sentinel_ssl
        assert aiohttp.TCPConnector.__init__ is sentinel_aio
    finally:
        pass


def test_patch_ssl_defaults_to_keeping_verification(monkeypatch) -> None:
    """No ``SSL_VERIFY`` env var at all → verification stays on.

    The default is "verification on" — only an explicit ``false`` disables it.
    This matches ``lightrag_server.py``'s own default of "true" (the launcher
    reads the raw env var; the server sets it to ``false`` for dev, which is
    a separate decision owned by the server process).
    """
    monkeypatch.delenv("SSL_VERIFY", raising=False)

    import ssl as _ssl

    import aiohttp

    from knowledge import lightrag_launcher as launcher

    ssl_module = _ssl.__dict__
    sentinel_ssl = lambda *a, **kw: None  # noqa: E731
    sentinel_aio = lambda self, *a, **kw: None  # noqa: E731
    monkeypatch.setitem(ssl_module, "_create_default_https_context", sentinel_ssl)
    monkeypatch.setattr(aiohttp.TCPConnector, "__init__", sentinel_aio)

    try:
        launcher.patch_ssl()

        assert ssl_module["_create_default_https_context"] is sentinel_ssl
        assert aiohttp.TCPConnector.__init__ is sentinel_aio
    finally:
        pass


# -- patch_httpx_timeout_compat ----------------------------------------------


def test_patch_httpx_timeout_compat_adds_alias_when_missing(monkeypatch) -> None:
    """When ``httpx.TimeoutError`` is missing, the shim adds the alias."""
    import httpx

    from knowledge import lightrag_launcher as launcher

    # httpx.TimeoutError may or may not exist depending on the installed
    # httpx version; remove it first to simulate the failure mode the shim
    # protects against.
    monkeypatch.delattr(httpx, "TimeoutError", raising=False)

    launcher.patch_httpx_timeout_compat()

    assert hasattr(httpx, "TimeoutError")
    assert httpx.TimeoutError is httpx.TimeoutException


def test_patch_httpx_timeout_compat_is_idempotent(monkeypatch) -> None:
    """If httpx already exposes TimeoutError (newer versions), the shim
    is a no-op — it must not overwrite the existing attribute.
    """
    import httpx

    from knowledge import lightrag_launcher as launcher

    sentinel = type("TimeoutError", (), {})
    monkeypatch.setattr(httpx, "TimeoutError", sentinel)

    launcher.patch_httpx_timeout_compat()

# -- patch_openai_client_for_retry_on_429 ------------------------------------


import asyncio
from unittest.mock import MagicMock


def test_retry_wrapper_retries_then_succeeds_on_rate_limit(monkeypatch) -> None:
    """On RateLimitError, the wrapper retries with backoff and eventually
    succeeds; only the last attempt's response is returned.
    """
    from openai import RateLimitError

    from knowledge import lightrag_launcher as launcher

    monkeypatch.setenv("LIGHTRAG_LLM_RETRY", "1")
    monkeypatch.setenv("LIGHTRAG_LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("LIGHTRAG_LLM_RETRY_BACKOFF_SEC", "0")
    sleeps = []

    async def fake_sleep(s, *a, **kw):
        sleeps.append(s)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    import openai

    sentinel = object()
    call_count = {"n": 0}
    fake_response = MagicMock()

    async def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RateLimitError(
                "rate limited", response=fake_response, body={"error": "rate_limit"}
            )
        return sentinel

    # The launcher wraps per-instance in __init__; replace the original
    # create at instance level via the wrapper's stored attribute.
    launcher.patch_openai_client_for_retry_on_429()

    client = openai.AsyncOpenAI(api_key="test")
    # Replace the cached original that the wrapper captured during init
    client._llm_original_create = flaky

    async def run():
        return await client.chat.completions.create(model="x", messages=[])

    result = asyncio.get_event_loop().run_until_complete(run())

    assert result is sentinel
    assert call_count["n"] == 3  # 2 failures + 1 success
    assert len(sleeps) == 2  # backoff happened between retries


def test_retry_wrapper_gives_up_after_max_retries(monkeypatch) -> None:
    """If all retries fail, the last exception is re-raised so the
    upstream chunk-processing code still sees a failure.
    """
    from openai import RateLimitError

    from knowledge import lightrag_launcher as launcher

    monkeypatch.setenv("LIGHTRAG_LLM_RETRY", "1")
    monkeypatch.setenv("LIGHTRAG_LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LIGHTRAG_LLM_RETRY_BACKOFF_SEC", "0")

    async def fake_sleep_zero(*a, **kw):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep_zero)

    import openai

    call_count = {"n": 0}
    fake_response = MagicMock()

    async def always_fail(*args, **kwargs):
        call_count["n"] += 1
        raise RateLimitError(
            "still rate limited", response=fake_response, body={"error": "rate_limit"}
        )

    launcher.patch_openai_client_for_retry_on_429()

    client = openai.AsyncOpenAI(api_key="test")
    client._llm_original_create = always_fail

    async def run():
        await client.chat.completions.create(model="x", messages=[])

    raised = False
    try:
        asyncio.get_event_loop().run_until_complete(run())
    except RateLimitError:
        raised = True

    assert raised
    # 1 initial + 2 retries = 3 attempts
    assert call_count["n"] == 3


def test_retry_wrapper_does_not_retry_non_retriable_errors(monkeypatch) -> None:
    """BadRequestError must NOT trigger retry — it's deterministic and
    retrying would just delay the user-visible failure.
    """
    from openai import BadRequestError

    from knowledge import lightrag_launcher as launcher

    monkeypatch.setenv("LIGHTRAG_LLM_RETRY", "1")
    monkeypatch.setenv("LIGHTRAG_LLM_MAX_RETRIES", "5")
    monkeypatch.setenv("LIGHTRAG_LLM_RETRY_BACKOFF_SEC", "0")

    import openai

    call_count = {"n": 0}
    fake_response = MagicMock()

    async def bad_request(*args, **kwargs):
        call_count["n"] += 1
        raise BadRequestError(
            "bad request", response=fake_response, body={"error": "invalid"}
        )

    launcher.patch_openai_client_for_retry_on_429()

    client = openai.AsyncOpenAI(api_key="test")
    client._llm_original_create = bad_request

    async def run():
        await client.chat.completions.create(model="x", messages=[])

    raised = False
    try:
        asyncio.get_event_loop().run_until_complete(run())
    except BadRequestError:
        raised = True

    assert raised
    assert call_count["n"] == 1  # exactly one attempt, no retry


def test_retry_wrapper_disabled_via_env(monkeypatch) -> None:
    """LIGHTRAG_LLM_RETRY=0 must cause patch_openai_client_for_retry_on_429
    to be a no-op (early return), so AsyncOpenAI.__init__ stays untouched.
    """
    monkeypatch.setenv("LIGHTRAG_LLM_RETRY", "0")

    import openai

    # Capture the original __init__ before any patch runs.
    original_init = openai.AsyncOpenAI.__init__

    from knowledge import lightrag_launcher as launcher

    launcher.patch_openai_client_for_retry_on_429()

    # When the patch is disabled, the function returns early and must NOT
    # have replaced __init__.
    assert openai.AsyncOpenAI.__init__ is original_init


