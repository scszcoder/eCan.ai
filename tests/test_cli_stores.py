"""`ecan stores` and `ecan browser create/login-state`: set up a store without the GUI."""

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine

from agent.db.models.store_model import Store
from agent.db.services.db_store_service import DBStoreService


@pytest.fixture
def env(monkeypatch):
    tmp = tempfile.mkdtemp()
    engine = create_engine(f"sqlite:///{os.path.join(tmp, 's.db')}")
    Store.__table__.create(engine)
    svc = DBStoreService(engine=engine)
    ctx = SimpleNamespace(db=SimpleNamespace(store_service=svc))
    monkeypatch.setattr("cli.stores.commands.get_context", lambda: ctx)
    # A throwaway profile registry and session root.
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg
    monkeypatch.setattr(reg, "_registry_path", lambda: Path(tmp) / "browser_profiles.json")
    monkeypatch.setenv("ECAN_BROWSER_DATA_ROOT", os.path.join(tmp, "browser_data"))
    # No cloud from the CLI: store_assign is unreachable, as in real use.
    from agent.cloud_api.store_api import StoreApiUnavailable
    monkeypatch.setattr("agent.cloud_api.store_api.store_assign",
                        mock.Mock(side_effect=StoreApiUnavailable("no session")))
    return svc, reg


def _run(*args):
    from cli.stores.commands import stores
    from cli.browser.commands import browser
    import cli.base.output as cli_output
    group = stores if args[0] == "stores" else browser
    # The output singleton binds to the stdout of the invocation that created
    # it; CliRunner swaps stdout per invocation.
    cli_output._global_output = None
    return CliRunner().invoke(group, list(args[1:]), catch_exceptions=False)


def test_two_store_setup_end_to_end(env):
    svc, reg = env
    for pid, sid in (("douyin-a", "douyin-店A"), ("douyin-b", "douyin-店B")):
        r = _run("browser", "create", "--id", pid, "--store", sid, "--domain", "im.jinritemai.com",
                 "--proxy", "10.0.0.1:1080")          # both stores share one proxy
        assert r.exit_code == 0, r.output
        r = _run("stores", "create", "--id", sid, "--name", sid.split("-", 1)[1], "--platform", "douyin",
                 "--url", "https://im.jinritemai.com/pc_seller_v2/main/workspace", "--profile", pid)
        assert r.exit_code == 0, r.output
        assert "saved on this machine only" in r.output   # no cloud session, said plainly
    stores = {s["store_id"]: s for s in svc.list_stores()}
    assert stores["douyin-店A"]["browser_profile_id"] == "douyin-a"
    assert reg.get_profile("douyin-b")["store_id"] == "douyin-店B"
    assert reg.get_profile("douyin-a")["proxy"]["host"] == reg.get_profile("douyin-b")["proxy"]["host"]
    assert reg.login_state("douyin-a")["state"] == "needs_login"
    assert _run("browser", "login-state", "douyin-a", "ok").exit_code == 0
    assert reg.login_state("douyin-a")["state"] == "ok"


def test_the_same_rules_as_the_stores_page(env):
    assert _run("stores", "create", "--id", "https://im.jinritemai.com/x", "--name", "x",
                "--platform", "douyin").exit_code != 0
    assert _run("stores", "create", "--id", "s", "--name", "s", "--platform", "douyin").exit_code == 0
    assert _run("stores", "create", "--id", "s", "--name", "s", "--platform", "douyin").exit_code != 0
    assert _run("stores", "create", "--id", "t", "--name", "t", "--platform", "douyin",
                "--profile", "no-such-profile").exit_code != 0


def test_update_archive_list(env):
    svc, _ = env
    _run("stores", "create", "--id", "s", "--name", "old", "--platform", "douyin")
    assert _run("stores", "update", "s", "--name", "new", "--url", "https://a").exit_code == 0
    assert svc.get_store("s")["name"] == "new"
    assert _run("stores", "archive", "s").exit_code == 0
    assert _run("stores", "list", "-f", "simple").output.strip() == ""
    assert _run("stores", "list", "--all", "-f", "simple").output.strip() == "s"
    assert json.loads(_run("stores", "show", "s").output)["store_urls"] == ["https://a"]
