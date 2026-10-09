"""Access control for the desktop app's local LightRAG server.

The env template used to bind 0.0.0.0 with no API key, so anyone on the same
LAN could read or delete a merchant's knowledge base. These tests pin the
loopback bind, the per-process API key, and that LightRAG's guest-token route
no longer opens the protected endpoints.
"""
import os
import subprocess
import sys
import textwrap

import pytest

from knowledge import lightrag_config_utils as cu


@pytest.fixture(autouse=True)
def _clean_key(monkeypatch):
    monkeypatch.delenv("LIGHTRAG_API_KEY", raising=False)


@pytest.mark.parametrize("host", ["", "0.0.0.0", "::"])
def test_wildcard_host_is_rewritten_to_loopback(host):
    assert cu.resolve_bind_host({"HOST": host}) == "127.0.0.1"


def test_lan_bind_requires_explicit_opt_in():
    assert cu.resolve_bind_host({"HOST": "0.0.0.0", "ECAN_LIGHTRAG_ALLOW_LAN": "1"}) == "0.0.0.0"
    # A specific address is a deliberate choice and is kept.
    assert cu.resolve_bind_host({"HOST": "192.168.1.20"}) == "192.168.1.20"


def test_api_key_is_generated_once_and_published():
    k1 = cu.ensure_local_api_key({})
    assert len(k1) >= 32 and os.environ["LIGHTRAG_API_KEY"] == k1
    # A restart in the same process keeps the key, so live clients keep working.
    assert cu.ensure_local_api_key({}) == k1
    assert cu.local_auth_headers() == {"X-API-Key": k1}


def test_configured_api_key_wins():
    assert cu.ensure_local_api_key({"LIGHTRAG_API_KEY": "user-chosen"}) == "user-chosen"
    # The template placeholder is not a real key.
    assert cu.ensure_local_api_key({"LIGHTRAG_API_KEY": "your-secure-api-key-here"}) != "your-secure-api-key-here"


def test_guest_mode_is_disabled_but_user_accounts_kept():
    env = {}
    cu.ensure_local_auth_accounts(env)
    assert env["AUTH_ACCOUNTS"].startswith("ecan-local:")
    assert env["TOKEN_SECRET"] and env["TOKEN_SECRET"] != "lightrag-jwt-default-secret-key!"
    env2 = {"AUTH_ACCOUNTS": "admin:pw", "TOKEN_SECRET": "s3cret"}
    cu.ensure_local_auth_accounts(env2)
    assert env2 == {"AUTH_ACCOUNTS": "admin:pw", "TOKEN_SECRET": "s3cret"}


def test_client_sends_published_key(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_API_KEY", "abc123")
    from knowledge.lightrag_client import LightragClient
    c = LightragClient(base_url="http://127.0.0.1:1")
    assert c.session.headers["X-API-Key"] == "abc123"


def test_lightrag_auth_rejects_guest_token_and_accepts_key():
    """Run LightRAG's real auth dependency with the env we generate."""
    import importlib.util
    if importlib.util.find_spec("lightrag") is None:
        pytest.skip("lightrag not installed")
    env = {}
    cu.ensure_local_auth_accounts(env)
    script = textwrap.dedent("""
        import sys
        sys.argv = [sys.argv[0]]
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient
        from lightrag.api.utils_api import get_combined_auth_dependency
        from lightrag.api.auth import auth_handler

        app = FastAPI()
        dep = get_combined_auth_dependency("the-key")

        @app.get("/documents", dependencies=[Depends(dep)])
        def docs():
            return {"ok": True}

        c = TestClient(app)
        guest = auth_handler.create_token(username="guest", role="guest")
        print(c.get("/documents").status_code,
              c.get("/documents", headers={"Authorization": "Bearer " + guest}).status_code,
              c.get("/documents", headers={"X-API-Key": "the-key"}).status_code)
    """)
    out = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, **env, "WHITELIST_PATHS": "/health"},
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    no_auth, guest, key = out.stdout.strip().splitlines()[-1].split()
    assert no_auth in ("401", "403")
    assert guest == "401"
    assert key == "200"
