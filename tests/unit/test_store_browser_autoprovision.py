# -*- coding: utf-8 -*-
"""A store-bound task with no browser profile is auto-provisioned its OWN login
profile at run start, instead of silently falling back to the shared default
browser (where a second same-platform store would answer through the first
store's logged-in Chrome -- two "stores" as two tabs in one Chromium).

See prep_skills_run._localize_browser_identity / _provision_store_profile.
"""
import pytest

# Import via agent.ec_tasks first: prep_skills_run <-> ec_tasks have a pre-existing
# circular import that only trips when prep_skills_run is the entry module.
import agent.ec_tasks.runner  # noqa: F401,E402
from agent.ec_skills import prep_skills_run as prep  # noqa: E402
from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as pr  # noqa: E402


class _FakeStoreSvc:
    def __init__(self, existing=None):
        self.rows = dict(existing or {})
        self.upserts = []

    def get_store(self, store_id):
        return self.rows.get(store_id)

    def upsert_store(self, data):
        self.upserts.append(dict(data))
        self.rows.setdefault(data["store_id"], {}).update(data)


@pytest.fixture
def no_main_window(monkeypatch):
    """_local_store_profile and _provision use AppContext.get_main_window();
    route them at a fake store service the test controls."""
    svc = _FakeStoreSvc()

    class _Mgr:
        store_service = svc

    class _MW:
        ec_db_mgr = _Mgr()

    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_main_window", staticmethod(lambda: _MW()))
    return svc


def test_store_without_profile_is_auto_provisioned(monkeypatch, no_main_window):
    created = {}
    monkeypatch.setattr(pr, "get_profile", lambda pid: None)  # nothing on this machine yet
    monkeypatch.setattr(pr, "make_profile", lambda pid, **kw: {"id": pid, **kw})
    monkeypatch.setattr(pr, "save_profile", lambda prof, **kw: created.setdefault("prof", prof))

    task_vars = {"store_id": "shop-a", "store_url": "https://im.jinritemai.com/x"}
    identity = prep._localize_browser_identity(task_vars, None)

    expected = pr.login_profile_id("shop-a")
    assert identity.get("browser_profile_id") == expected
    assert created["prof"]["id"] == expected
    assert created["prof"]["store_id"] == "shop-a"
    # domain carried from the store_url, locale pinned zh-CN
    assert created["prof"]["domain_name"] == "im.jinritemai.com"
    assert created["prof"]["locale"] == "zh-CN"
    # recorded on the store so the next run resolves it locally (no re-provision)
    assert {"store_id": "shop-a", "browser_profile_id": expected} in no_main_window.upserts


def test_two_stores_get_distinct_profiles(monkeypatch, no_main_window):
    monkeypatch.setattr(pr, "get_profile", lambda pid: None)
    monkeypatch.setattr(pr, "make_profile", lambda pid, **kw: {"id": pid, **kw})
    monkeypatch.setattr(pr, "save_profile", lambda prof, **kw: None)

    a = prep._localize_browser_identity({"store_id": "shop-a"}, None)["browser_profile_id"]
    b = prep._localize_browser_identity({"store_id": "shop-b"}, None)["browser_profile_id"]
    assert a and b and a != b  # never the same browser


def test_existing_store_profile_wins_no_provision(monkeypatch):
    """When the store record already has a profile, use it and never provision."""
    svc = _FakeStoreSvc({"shop-a": {"browser_profile_id": "shop-a-deadbeef-login"}})

    class _Mgr:
        store_service = svc

    class _MW:
        ec_db_mgr = _Mgr()

    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_main_window", staticmethod(lambda: _MW()))

    called = {"make": False}
    monkeypatch.setattr(pr, "make_profile", lambda *a, **k: called.__setitem__("make", True) or {})

    identity = prep._localize_browser_identity({"store_id": "shop-a"}, None)
    assert identity["browser_profile_id"] == "shop-a-deadbeef-login"
    assert called["make"] is False
    assert svc.upserts == []


def test_non_store_task_is_untouched(monkeypatch, no_main_window):
    """A task with no store_id and no identity is left exactly as-is."""
    monkeypatch.setattr(pr, "get_profile", lambda pid: None)
    out = prep._localize_browser_identity({"some": "var"}, None)
    assert out in (None, {})  # nothing provisioned
    assert no_main_window.upserts == []


def test_a_skill_with_its_own_profile_for_the_store_runs_there(monkeypatch):
    """owner_settings[store].skill_browser_profiles gives one skill its own browser, so it
    runs beside the store's other work instead of fighting over one Chrome (2026-11-18:
    the Google Ads runner kept taking the Shopify label run's tab to a Google sign-in)."""
    svc = _FakeStoreSvc({"shop-a": {"browser_profile_id": "shop-a-login"}})

    class _Mgr:
        store_service = svc

    class _MW:
        ec_db_mgr = _Mgr()

    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_main_window", staticmethod(lambda: _MW()))
    monkeypatch.setattr(prep, "_skill_profiles", lambda store_id: {"ads_runner": "shop-a-ads"} if store_id == "shop-a" else {})
    monkeypatch.setattr(prep, "_profile_exists", lambda pid: pid in ("shop-a-login", "shop-a-ads"))

    assert prep._localize_browser_identity({"store_id": "shop-a"}, None, "ads_runner")["browser_profile_id"] == "shop-a-ads"
    assert prep._localize_browser_identity({"store_id": "shop-a"}, None, "after_sales")["browser_profile_id"] == "shop-a-login"
    assert prep._localize_browser_identity({"store_id": "shop-a"}, None)["browser_profile_id"] == "shop-a-login"
    # A named profile this machine does not have is not used: the store's own login is.
    monkeypatch.setattr(prep, "_skill_profiles", lambda store_id: {"ads_runner": "gone"})
    assert prep._localize_browser_identity({"store_id": "shop-a"}, None, "ads_runner")["browser_profile_id"] == "shop-a-login"
