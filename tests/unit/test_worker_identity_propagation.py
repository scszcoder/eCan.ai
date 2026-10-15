# -*- coding: utf-8 -*-
"""A store-isolation worker must inherit the signed-in identity from the parent.

Without it the worker starts user='?': it opens the empty BASE ecan_base.db
(not '<base>/<user>_local/ecan_base.db') and builds 0 agents, and
secure_store.get(..., username=None) misses the eCanAI API key so its LLM is
None. Either way the store's front desk never runs and no browser launches
(observed running two 抖店 stores on yae).

Covers:
- default_spawner hands the worker ECAN_WORKER_DATA_HOME + ECAN_WORKER_USER.
- worker_entry._data_home prefers the handed-down path.
- secure_store.get_current_username() falls back to the worker env.
"""
import importlib

import pytest

wp = importlib.import_module("agent.ec_tasks.worker_placement")
we = importlib.import_module("agent.ec_tasks.worker_entry")
ss = importlib.import_module("utils.env.secure_store")


def test_default_spawner_passes_data_home_and_user(monkeypatch):
    class _MW:
        my_ecb_data_homepath = r"C:\base\wechat_abc_local"

    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_main_window",
                        staticmethod(lambda: _MW()))
    monkeypatch.setattr(ss, "get_current_username", lambda: "wechat_abc")

    spec = wp.default_spawner("douyin-store3")
    assert spec.env["ECAN_WORKER_DATA_HOME"] == r"C:\base\wechat_abc_local"
    assert spec.env["ECAN_WORKER_USER"] == "wechat_abc"
    assert spec.env["ECAN_WORKER_KEY"] == "douyin-store3"


def test_default_spawner_warns_but_builds_when_identity_missing(monkeypatch):
    class _MW:
        my_ecb_data_homepath = ""

    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_main_window",
                        staticmethod(lambda: _MW()))
    monkeypatch.setattr(ss, "get_current_username", lambda: "")

    spec = wp.default_spawner("douyin-store3")  # must not raise
    assert "ECAN_WORKER_DATA_HOME" not in spec.env
    assert "ECAN_WORKER_USER" not in spec.env


def test_data_home_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("ECAN_WORKER_DATA_HOME", r"C:\base\wechat_abc_local")
    assert we._data_home("anything") == r"C:\base\wechat_abc_local"


def test_data_home_falls_back_without_env(monkeypatch):
    monkeypatch.delenv("ECAN_WORKER_DATA_HOME", raising=False)
    # With no explicit path and no user it returns the base appdata path.
    from config.app_info import app_info
    assert we._data_home("") == app_info.appdata_path


def test_get_current_username_env_fallback_in_worker(monkeypatch):
    # No AuthManager available (worker): get_auth_manager returns None.
    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_auth_manager",
                        classmethod(lambda cls: None))
    monkeypatch.delenv("ECAN_LOG_USER", raising=False)
    monkeypatch.delenv("ECAN_CLI_USER", raising=False)
    monkeypatch.setenv("ECAN_WORKER_USER", "wechat_abc")
    assert ss.get_current_username() == "wechat_abc"


def test_get_current_username_prefers_auth_manager(monkeypatch):
    class _AM:
        def get_current_user(self):
            return "real_user"

    import app_context
    monkeypatch.setattr(app_context.AppContext, "get_auth_manager",
                        classmethod(lambda cls: _AM()))
    monkeypatch.setenv("ECAN_WORKER_USER", "env_user")
    # A live AuthManager wins over the env fallback.
    assert ss.get_current_username() == "real_user"
