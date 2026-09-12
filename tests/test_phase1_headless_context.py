"""Phase 1 of Path 1.5 — headless runtime context.

1.2 comes before 1.3 on purpose. ``AppContext`` is a desktop GUI singleton whose
``main_window`` is really a service locator, and an unprovided service currently
reads back as ``None``. Call sites guard defensively::

    if mainwin and hasattr(mainwin, 'config_manager'):   # build_node.py

so on a pod a missing service does not fail — it takes a quiet fallback, and the
run *looks* fine while behaving differently. Build ``HeadlessAppContext`` first
and you never find out what you missed.

Two traps this pins down:

  * ``AppContext.__getattr__`` returning None makes ``hasattr(instance, <any>)``
    always True, so ``hasattr`` guards pass vacuously and the code then operates
    on None.
  * ``MissingService`` must NOT be an ``AttributeError`` — ``hasattr`` swallows
    those, which would restore the silent fallback it exists to prevent.
"""

import pytest

import app_context as ac
from app_context import AppContext


@pytest.fixture(autouse=True)
def _restore_mode():
    """Never leak headless mode into another test."""
    ac.set_headless(None)
    ac.reset_missing_service_warnings()
    yield
    ac.set_headless(None)
    ac.reset_missing_service_warnings()


# ---------------------------------------------------------------------------
# Desktop behaviour must not change
# ---------------------------------------------------------------------------

def test_desktop_unknown_service_still_returns_none(monkeypatch):
    monkeypatch.delenv(ac.ENV_HEADLESS, raising=False)
    assert AppContext.definitely_not_a_real_service is None
    assert AppContext.get_instance().another_missing_one is None


def test_desktop_known_attributes_still_work():
    inst = AppContext.get_instance()
    inst.logger = "sentinel"
    try:
        assert AppContext.logger == "sentinel"
    finally:
        inst.logger = None


def test_dunder_access_still_raises_attributeerror():
    """Private/dunder lookups must stay AttributeError in both modes."""
    for headless in (False, True):
        ac.set_headless(headless)
        with pytest.raises(AttributeError):
            AppContext.get_instance().__some_private_thing__


# ---------------------------------------------------------------------------
# Headless: loud
# ---------------------------------------------------------------------------

def test_headless_missing_service_raises():
    ac.set_headless(True)
    with pytest.raises(ac.MissingService) as exc:
        AppContext.config_manager
    assert "config_manager" in str(exc.value)


def test_missing_service_names_the_service_and_the_remedy():
    ac.set_headless(True)
    with pytest.raises(ac.MissingService) as exc:
        AppContext.getWebDriver
    msg = str(exc.value)
    assert "getWebDriver" in msg
    assert "HeadlessAppContext" in msg or "requires=" in msg


def test_missing_service_is_not_an_attributeerror():
    """The load-bearing detail: hasattr must NOT swallow it."""
    assert not issubclass(ac.MissingService, AttributeError)

    ac.set_headless(True)
    with pytest.raises(ac.MissingService):
        hasattr(AppContext, "some_service_a_pod_forgot")


def test_hasattr_guard_no_longer_passes_vacuously():
    """The build_node.py:388 guard shape, headless.

    Desktop: hasattr is True for anything, so the guard passes and the code
    goes on to use None. Headless: it blows up naming the service.
    """
    ac.set_headless(False)
    mainwin = AppContext.get_instance()
    assert hasattr(mainwin, "config_manager") is True  # vacuous, pre-existing

    ac.set_headless(True)
    with pytest.raises(ac.MissingService):
        _ = mainwin and hasattr(mainwin, "config_manager")


# ---------------------------------------------------------------------------
# warn mode — bring-up escape hatch
# ---------------------------------------------------------------------------

def test_warn_mode_logs_once_and_continues(monkeypatch):
    ac.set_headless(True)
    monkeypatch.setenv(ac.ENV_MISSING, "warn")

    seen = []
    import utils.logger_helper as lh
    monkeypatch.setattr(lh.logger_helper, "error", lambda m, *a, **k: seen.append(m))

    assert AppContext.some_absent_service is None      # limps, does not crash
    assert AppContext.some_absent_service is None      # second read
    assert len(seen) == 1, "must be loud once per attribute, not per access"
    assert "some_absent_service" in seen[0]


def test_warn_mode_is_opt_in_raise_is_default(monkeypatch):
    ac.set_headless(True)
    monkeypatch.delenv(ac.ENV_MISSING, raising=False)
    with pytest.raises(ac.MissingService):
        AppContext.yet_another_absent_service


def test_env_var_controls_headless(monkeypatch):
    ac.set_headless(None)
    monkeypatch.setenv(ac.ENV_HEADLESS, "1")
    assert ac.headless_enabled() is True
    monkeypatch.setenv(ac.ENV_HEADLESS, "0")
    assert ac.headless_enabled() is False


def test_explicit_override_beats_env(monkeypatch):
    monkeypatch.setenv(ac.ENV_HEADLESS, "0")
    ac.set_headless(True)
    assert ac.headless_enabled() is True


# ===========================================================================
# 1.3 — HeadlessAppContext
# ===========================================================================

from headless_context import (  # noqa: E402
    HeadlessAppContext, install_headless_context, uninstall_headless_context,
    EXPECTED_SERVICES,
)


def _full_context(**over):
    """A context providing everything EXPECTED_SERVICES asks for."""
    services = {name: f"<{name}>" for name in EXPECTED_SERVICES}
    services.update(over)
    return HeadlessAppContext(services=services)


@pytest.fixture
def installed():
    ctx = _full_context()
    install_headless_context(ctx)
    yield ctx
    uninstall_headless_context()


# --- provided services -----------------------------------------------------

def test_plain_service_is_returned_as_is():
    ctx = HeadlessAppContext(llm="LLM", user="a@b.c")
    assert ctx.llm == "LLM"
    assert ctx.user == "a@b.c"


def test_method_service_given_a_value_is_callable():
    """Call sites do mainwin.get_auth_token() — a plain value must still work."""
    ctx = HeadlessAppContext(get_auth_token="tok",
                             getWanApiEndpoint="https://api.example.com")
    assert ctx.get_auth_token() == "tok"
    assert ctx.getWanApiEndpoint() == "https://api.example.com"


def test_method_service_given_a_callable_is_passed_through():
    ctx = HeadlessAppContext(get_auth_token=lambda: "fresh")
    assert ctx.get_auth_token() == "fresh"


def test_top_ten_services_are_all_expressible():
    """The ~270-of-380-call-site set."""
    top = ["llm", "agent_skills", "agents", "user", "config_manager",
           "agent_tasks", "mcp_client", "getWanApiEndpoint", "get_auth_token",
           "browser_use_llm"]
    ctx = HeadlessAppContext(services={n: f"<{n}>" for n in top})
    for name in top:
        got = getattr(ctx, name)
        assert (got() if callable(got) else got) == f"<{name}>"


# --- missing services are loud --------------------------------------------

def test_unknown_service_raises_not_none():
    ctx = HeadlessAppContext()
    with pytest.raises(ac.MissingService) as exc:
        ctx.some_service_nobody_provided
    assert "some_service_nobody_provided" in str(exc.value)


def test_unprovided_plain_service_raises():
    ctx = HeadlessAppContext(llm="LLM")
    with pytest.raises(ac.MissingService):
        ctx.config_manager


def test_browser_service_names_the_capability_requirement():
    ctx = HeadlessAppContext(llm="LLM")           # browser_capable=False
    with pytest.raises(ac.MissingService) as exc:
        ctx.getWebDriver
    msg = str(exc.value)
    assert "browser_local" in msg and "browser_capable" in msg


def test_browser_service_available_on_browser_capable_vehicle():
    ctx = HeadlessAppContext(browser_capable=True, getWebDriver="driver")
    assert ctx.getWebDriver() == "driver"


def test_browser_capable_but_unprovided_still_raises():
    ctx = HeadlessAppContext(browser_capable=True)
    with pytest.raises(ac.MissingService):
        ctx.browser_manager


def test_desktop_only_service_says_it_has_no_headless_equivalent():
    ctx = HeadlessAppContext(browser_capable=True)
    for name in ("channel_bridge", "rpa_wait_in_line", "todo_wait_in_line"):
        with pytest.raises(ac.MissingService) as exc:
            getattr(ctx, name)
        assert "headless" in str(exc.value).lower()


def test_setwebdriver_write_back_is_honoured():
    """session.py and build_helpers.py write the driver back onto the locator."""
    ctx = HeadlessAppContext(browser_capable=True)
    ctx.setWebDriver("chromedriver")
    assert ctx.getWebDriver() == "chromedriver"


def test_setwebdriver_refused_without_browser_capability():
    ctx = HeadlessAppContext()
    with pytest.raises(ac.MissingService):
        ctx.setWebDriver("chromedriver")


# --- completeness ----------------------------------------------------------

def test_missing_expected_reports_the_gap_up_front():
    ctx = HeadlessAppContext(llm="LLM")
    missing = ctx.missing_expected()
    assert "config_manager" in missing and "user" in missing
    assert "llm" not in missing


def test_install_strict_refuses_an_incomplete_context():
    ctx = HeadlessAppContext(llm="LLM")
    try:
        with pytest.raises(ac.MissingService) as exc:
            install_headless_context(ctx)
        assert "incomplete" in str(exc.value)
    finally:
        uninstall_headless_context()


def test_install_non_strict_starts_but_still_raises_on_use():
    ctx = HeadlessAppContext(llm="LLM")
    try:
        install_headless_context(ctx, strict=False)
        assert AppContext.get_main_window() is ctx
        with pytest.raises(ac.MissingService):
            AppContext.get_main_window().config_manager
    finally:
        uninstall_headless_context()


# --- installation & the sentinel landmine ----------------------------------

def test_installed_context_is_what_skill_code_resolves(installed):
    """The 35 AppContext.get_main_window() call sites get the locator."""
    mainwin = AppContext.get_main_window()
    assert mainwin is installed
    assert mainwin.llm == "<llm>"


def test_hasattr_guard_shape_works_against_installed_context(installed):
    """build_node.py:388's guard must see a provided service."""
    mainwin = AppContext.get_main_window()
    assert mainwin and hasattr(mainwin, "config_manager")


def test_cloud_detection_no_longer_relies_on_main_window_being_none(installed):
    """The landmine: installing a locator makes get_main_window() non-None.

    build_node.py used `AppContext.get_main_window() is None` as the cloud
    sentinel; with a headless context installed that is False, which would have
    silently routed a pod down the local-HTTP MCP path.
    """
    from pathlib import Path
    src = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")
    assert src.count("headless_enabled() or AppContext.get_main_window() is None") == 2
    # and the bare proxy is gone
    assert "\n                    _is_cloud = AppContext.get_main_window() is None" not in src

    # behaviourally: headless is detected even with a non-None main window
    assert AppContext.get_main_window() is not None
    assert ac.headless_enabled() is True


def test_uninstall_restores_desktop(installed):
    uninstall_headless_context()
    assert AppContext.get_main_window() is None
    assert ac.headless_enabled() is False
    assert AppContext.anything_missing is None  # silent None is back
