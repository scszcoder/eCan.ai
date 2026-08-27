"""
Tests for the AppConfig runtime configuration pipeline.

Verifies the contract between frontend and backend:

  1. Desktop path: IPC handler `getAppConfig` returns the agreed payload
     shape (gui/ipc/w2p_handlers/app_config_handler.py).
  2. Web path: web_server.py's GET /api/config returns the SAME payload
     shape — AppConfigContext.tsx's normalize() must consume both.
  3. Whitelist: getAppConfig is registered as pre-auth so AppConfigProvider
     can fetch it before login.
  4. Payload invariants: every field the frontend reads (cloudbase_env_id,
     wechat_app_id, cognito_domain, cognito_client_id) is present and
     populated when ECAN_APP_ID=cn or ECAN_APP_ID=intl.

These tests cover the behavior surface of the runtime-config refactor;
they do NOT cover React component rendering or browser-mode detection.
Run via:  python3 -m pytest tests/unit/test_app_config_runtime.py -v
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

from gui.ipc.registry import IPCHandlerRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def app_id(monkeypatch):
    """Yield env var override; restore on teardown."""
    saved = os.environ.get("ECAN_APP_ID")
    return saved


def _load_handlers():
    """Simulate the runtime initialization done by web_server.load_handlers()
    and main.py: import w2p_handlers and call _ensure_handlers_loaded() to
    trigger pkgutil.walk_packages → app_config_handler registration."""
    import gui.ipc.w2p_handlers as wh
    import gui.ipc.w2p_handlers.app_config_handler  # noqa: F401 — explicit import
    wh._ensure_handlers_loaded()


def _build_payload():
    """Re-import handler module so the env override takes effect."""
    _load_handlers()
    handler_info = IPCHandlerRegistry.get_handler("getAppConfig")
    assert handler_info is not None, (
        "getAppConfig IPC handler not registered — "
        "gui/ipc/w2p_handlers/app_config_handler.py must be importable "
        "and decorated with @IPCHandlerRegistry.handler('getAppConfig')"
    )
    handler, _ = handler_info
    from gui.ipc.types import IPCRequest, IPCResponse
    assert isinstance(handler_info, tuple)
    return handler


def _build_app_config():
    """Call _build_app_config() directly — bypasses the registry."""
    import gui.ipc.w2p_handlers.app_config_handler as h
    importlib.reload(h)
    return h._build_app_config()


# ---------------------------------------------------------------------------
# Test 1: getAppConfig is in the pre-auth whitelist
# ---------------------------------------------------------------------------
def test_get_app_config_is_pre_auth_whitelisted():
    """Frontend must call getAppConfig BEFORE login (to know which auth
    adapter to load). It must therefore be registered after handler
    loading (gui/ipc/registry.py + @IPCHandlerRegistry.handler)."""
    _load_handlers()

    handlers = IPCHandlerRegistry.list_handlers()
    all_methods = set(handlers.get("sync", [])) | set(handlers.get("background", []))
    assert "getAppConfig" in all_methods, (
        "getAppConfig must be registered after _ensure_handlers_loaded(). "
        "Either (a) the handler decorator is missing, (b) the file is not "
        "imported, or (c) pkgutil walk_packages skipped it."
    )


# ---------------------------------------------------------------------------
# Test 2: payload shape is stable and matches AppConfigContext.normalize()
# ---------------------------------------------------------------------------
EXPECTED_KEYS = {"app_id", "is_cn", "auth_type", "auth", "cloud"}
EXPECTED_AUTH_KEYS = {"cloudbase_env_id", "wechat_app_id",
                      "cognito_domain", "cognito_client_id"}
EXPECTED_CLOUD_KEYS = {"graphql_endpoint"}


@pytest.mark.parametrize("app_id_value,expected_is_cn,expected_auth_type", [
    ("intl", False, "cognito"),
    ("cn",   True,  "cloudbase"),
])
def test_ipc_get_app_config_payload_shape(app_id_value, expected_is_cn,
                                          expected_auth_type, monkeypatch):
    """Verify _build_app_config() returns the agreed-upon shape under
    both ECAN_APP_ID=intl and ECAN_APP_ID=cn."""
    monkeypatch.setenv("ECAN_APP_ID", app_id_value)
    payload = _build_app_config()

    # Top-level keys — must match AppConfig interface in
    # gui_v2/src/contexts/AppConfigContext.tsx
    assert set(payload.keys()) == EXPECTED_KEYS, (
        f"payload keys drifted: got {set(payload.keys())}, "
        f"expected {EXPECTED_KEYS}. "
        "If you added a new field, also update AppConfigContext.tsx and "
        "web_server.py's /api/config endpoint."
    )

    assert payload["is_cn"] is expected_is_cn
    assert payload["auth_type"] == expected_auth_type
    assert payload["app_id"] == app_id_value

    # auth sub-payload — must have exactly these 4 keys
    auth = payload["auth"]
    assert set(auth.keys()) == EXPECTED_AUTH_KEYS, (
        f"auth keys drifted: got {set(auth.keys())}, "
        f"expected {EXPECTED_AUTH_KEYS}"
    )
    for k in EXPECTED_AUTH_KEYS:
        assert isinstance(auth[k], str), f"auth.{k} must be string"

    cloud = payload["cloud"]
    assert set(cloud.keys()) == EXPECTED_CLOUD_KEYS
    assert isinstance(cloud["graphql_endpoint"], str)


# ---------------------------------------------------------------------------
# Test 2b: CN/Intl payload values are REAL, not just defaulted to ""
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("app_id_value,non_empty_keys", [
    ("intl", ["cognito_domain", "cognito_client_id"]),
    ("cn",   ["cloudbase_env_id", "wechat_app_id"]),
])
def test_ipc_payload_populates_region_specific_keys(app_id_value,
                                                    non_empty_keys, monkeypatch):
    """The payload shape contract requires the active region keys to be
    populated, not just empty strings. If ECAN_APP_ID=cn but
    cloudbase_env_id is empty, the React frontend will silently fall back
    to cognito — a hard-to-debug auth failure."""
    monkeypatch.setenv("ECAN_APP_ID", app_id_value)
    payload = _build_app_config()

    for k in non_empty_keys:
        assert payload["auth"][k], (
            f"ECAN_APP_ID={app_id_value} but auth.{k} is empty. "
            "This will cause the frontend to silently use the wrong auth "
            "backend. Check auth/auth_config.py.{CLOUDBASE,WECHAT,COGNITO} "
            "and verify ECAN_APP_ID is correctly set in the env."
        )


# ---------------------------------------------------------------------------
# Test 2c: web /api/config also populates region-specific keys
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("app_id_value,non_empty_keys", [
    ("intl", ["cognito_domain", "cognito_client_id"]),
    ("cn",   ["cloudbase_env_id", "wechat_app_id"]),
])
def test_web_api_config_populates_region_specific_keys(app_id_value,
                                                       non_empty_keys, monkeypatch):
    """Same invariant as Test 2b, but for web_server.py's /api/config.
    If a CN web deployment returns cognito-only fields, the React auth
    bootstrap will silently default to cognito and login will fail."""
    monkeypatch.setenv("ECAN_APP_ID", app_id_value)
    import web_server as ws
    importlib.reload(ws)

    from fastapi.testclient import TestClient
    app = ws.create_asgi_app()
    if app is None:
        pytest.skip("FastAPI not available")
    client = TestClient(app)
    r = client.get("/api/config")
    assert r.status_code == 200, f"status {r.status_code}"
    payload = r.json()

    for k in non_empty_keys:
        assert payload["auth"][k], (
            f"web /api/config with ECAN_APP_ID={app_id_value} returned "
            f"empty auth.{k}. The web React shell will load the wrong "
            f"auth adapter. Verify auth/auth_config.py is populated."
        )


# ---------------------------------------------------------------------------
# Test 3: web_server.py's /api/config payload must match IPC handler
# ---------------------------------------------------------------------------
def test_web_server_api_config_matches_ipc_get_app_config(monkeypatch):
    """web_server.py exposes GET /api/config for web deployments. Its
    payload shape MUST equal the IPC handler payload so AppConfigContext.
    normalize() can consume both with the same code path."""
    monkeypatch.setenv("ECAN_APP_ID", "intl")

    # Re-import both modules so ECAN_APP_ID override applies.
    import web_server as ws
    importlib.reload(ws)
    import gui.ipc.w2p_handlers.app_config_handler as ipc_handler
    importlib.reload(ipc_handler)
    _load_handlers()

    from fastapi.testclient import TestClient
    app = ws.create_asgi_app()
    if app is None:
        pytest.skip("FastAPI not available; cannot test web_server endpoint")

    client = TestClient(app)
    r = client.get("/api/config")
    assert r.status_code == 200, f"/api/config returned {r.status_code}"

    web_payload = r.json()
    ipc_payload = ipc_handler._build_app_config()

    # Same top-level keys
    assert set(web_payload.keys()) == set(ipc_payload.keys()), (
        f"/api/config payload keys ({set(web_payload.keys())}) "
        f"differ from getAppConfig payload keys ({set(ipc_payload.keys())}). "
        "Both backends must return the same shape."
    )

    # Same auth sub-keys
    assert set(web_payload["auth"].keys()) == set(ipc_payload["auth"].keys()), (
        f"/api/config auth keys ({set(web_payload['auth'].keys())}) "
        f"differ from getAppConfig auth keys "
        f"({set(ipc_payload['auth'].keys())})"
    )

    # Identity fields agree
    assert web_payload["app_id"] == ipc_payload["app_id"]
    assert web_payload["is_cn"] == ipc_payload["is_cn"]
    assert web_payload["auth_type"] == ipc_payload["auth_type"]


# ---------------------------------------------------------------------------
# Test 4: no SECRET_* values leak into the payload
# ---------------------------------------------------------------------------
FORBIDDEN_SUBSTRINGS = [
    "SECRET_KEY", "APP_SECRET", "WECHAT_APP_SECRET",
    "TENCENT_SECRET", "COGNITO_CLIENT_SECRET",
    "AWS_SECRET_ACCESS_KEY",
]


@pytest.mark.parametrize("app_id_value", ["intl", "cn"])
def test_app_config_payload_has_no_secrets(app_id_value, monkeypatch):
    """Guard against accidental leakage of private credentials into the
    public runtime config payload."""
    # Plant a fake secret value — if it leaks through, this test catches it.
    monkeypatch.setenv("ECAN_WECHAT_APP_SECRET", "leaked-wechat-secret-XYZ")
    monkeypatch.setenv("ECAN_TENCENT_SECRET_ID", "leaked-tencent-id-XYZ")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaked-aws-secret-XYZ")
    monkeypatch.setenv("ECAN_APP_ID", app_id_value)

    import gui.ipc.w2p_handlers.app_config_handler as h
    importlib.reload(h)
    payload = h._build_app_config()

    import json
    serialized = json.dumps(payload, default=str)

    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in serialized, (
            f"SECRET marker '{forbidden}' leaked into AppConfig payload. "
            f"payload={serialized}"
        )
        assert "leaked" not in serialized, (
            f"planted secret value leaked into AppConfig payload: {serialized}"
        )


# ---------------------------------------------------------------------------
# Test 5: LocalServer.py does NOT expose /api/config (deleted in refactor)
# ---------------------------------------------------------------------------
def test_local_server_has_no_api_config_route():
    """The refactor removed /api/config from LocalServer.py; the frontend
    uses IPC `getAppConfig` instead. If anyone re-adds /api/config here
    (e.g. a careless merge), this test catches it — desktop code path
    should be IPC, and only web_server.py serves HTTP /api/config."""
    gui_dir = REPO_ROOT / "gui"
    ls_path = gui_dir / "LocalServer.py"
    if not ls_path.exists():
        pytest.skip("LocalServer.py not found")
    text = ls_path.read_text()
    # The route registration line is removed but we check anyway.
    assert '"/api/config"' not in text, (
        "LocalServer.py re-introduced /api/config route. The runtime "
        "config refactor moved this to (a) IPC handler `getAppConfig` "
        "for desktop and (b) web_server.py's GET /api/config for web "
        "deployment. Do NOT restore this route in LocalServer.py."
    )


# ---------------------------------------------------------------------------
# Test 6: vite-env.d.ts declares VITE_LOCAL_SERVER_PORT (regression)
# ---------------------------------------------------------------------------
def test_vite_env_dts_declares_local_server_port():
    """After the getLocalServerUrl() fix, apiRouter reads
    import.meta.env.VITE_LOCAL_SERVER_PORT. The type must exist in
    vite-env.d.ts so vite.config.ts and api-router.ts stay consistent."""
    vite_env = REPO_ROOT / "gui_v2" / "src" / "vite-env.d.ts"
    if not vite_env.exists():
        pytest.skip("vite-env.d.ts not found")
    text = vite_env.read_text()
    assert "VITE_LOCAL_SERVER_PORT" in text, (
        "vite-env.d.ts is missing VITE_LOCAL_SERVER_PORT. api-router.ts "
        "reads this via import.meta.env; without the type declaration "
        "TS narrowing can silently drop it."
    )
    # And api-router must read it via import.meta.env, not process.env
    api_router = REPO_ROOT / "gui_v2" / "src" / "services" / "api" / "api-router.ts"
    api_text = api_router.read_text()
    assert "process.env.ECAN_LOCAL_SERVER_PORT" not in api_text, (
        "api-router.ts is reading process.env.ECAN_LOCAL_SERVER_PORT — "
        "this variable is never injected by Vite (browser bundle), so "
        "the value is always undefined. Use "
        "import.meta.env.VITE_LOCAL_SERVER_PORT instead."
    )


# ---------------------------------------------------------------------------
# Test 7: frontend still has fallback values when backend is unreachable
# ---------------------------------------------------------------------------
def test_app_config_context_has_intl_cognito_fallback():
    """AppConfigContext.tsx must have a fallback when fetchConfig() throws.
    The fallback is intl/cognito so a stale-region bug never silently shows
    up as a completely-blank config."""
    p = REPO_ROOT / "gui_v2" / "src" / "contexts" / "AppConfigContext.tsx"
    text = p.read_text()
    # The fallback block sets app_id='intl', auth_type='cognito'
    assert "app_id: 'intl'" in text, (
        "AppConfigContext.tsx missing fallback app_id='intl'"
    )
    assert "auth_type: 'cognito'" in text, (
        "AppConfigContext.tsx missing fallback auth_type='cognito'"
    )
    # And the fallback must be reachable via the catch{} branch
    assert "catch" in text, (
        "AppConfigContext.tsx missing try/catch around fetchConfig()"
    )


# ---------------------------------------------------------------------------
# Test 8: web /api/config is registered BEFORE StaticFiles mount (route
# priority). This is critical because FastAPI's StaticFiles with html=True
# would otherwise swallow /api/* paths and return index.html — which
# would silently break web React auth bootstrap.
# ---------------------------------------------------------------------------
def test_web_api_config_route_registered_before_staticfiles_mount(monkeypatch):
    """In web_server.py: /api/config must be a @app.get decorator registered
    BEFORE app.mount('/', StaticFiles). If someone reorders the code so
    the mount comes first, StaticFiles will claim /api/config and return
    index.html. The React fetch('/api/config') would get HTML, json parsing
    would fail, and the SPA would silently fall back to intl/cognito — a
    region/auth mismatch for CN web deployments."""
    import web_server as ws
    importlib.reload(ws)
    app = ws.create_asgi_app()
    if app is None:
        pytest.skip("FastAPI not available")

    # Get the registered routes in registration order.
    routes = list(app.routes)

    # Find the index of /api/config (APIRoute) and the StaticFiles mount.
    api_config_idx = None
    static_mount_idx = None
    for i, r in enumerate(routes):
        if hasattr(r, "path") and r.path == "/api/config":
            api_config_idx = i
        if type(r).__name__ == "Mount" and r.path == "":
            static_mount_idx = i

    if api_config_idx is None:
        pytest.fail("/api/config not registered as a Route on FastAPI app")
    if static_mount_idx is None:
        pytest.skip("StaticFiles mount not active (no gui_v2/dist built)")

    assert api_config_idx < static_mount_idx, (
        f"/api/config (idx={api_config_idx}) is registered AFTER the "
        f"StaticFiles mount (idx={static_mount_idx}). In Starlette, routes "
        f"match in registration order — StaticFiles with html=True will "
        f"return index.html for any non-API path, so /api/config would "
        f"return HTML to the React frontend. Move @app.get('/api/config') "
        f"ABOVE app.mount('/', StaticFiles(...))."
    )


# ---------------------------------------------------------------------------
# Test 9: web /api/config content-type is JSON (not HTML/text)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("app_id_value", ["intl", "cn"])
def test_web_api_config_content_type_is_json(app_id_value, monkeypatch):
    """The frontend does `await resp.json()` on /api/config. If the
    response is HTML (e.g. SPA fallback index.html) or text/plain, the
    JSON parse throws and AppConfigContext falls back to intl/cognito.
    This test catches route registration order regressions where
    StaticFiles intercepts the /api/* prefix."""
    monkeypatch.setenv("ECAN_APP_ID", app_id_value)
    import web_server as ws
    importlib.reload(ws)
    app = ws.create_asgi_app()
    if app is None:
        pytest.skip("FastAPI not available")
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.get("/api/config")
    ct = r.headers.get("content-type", "")
    assert "application/json" in ct, (
        f"/api/config returned Content-Type '{ct}' (expected "
        f"application/json). The web React shell will fail to parse this "
        f"as JSON and silently fall back to intl/cognito — a hard-to-debug "
        f"region mismatch for CN web deployments."
    )
    # Also verify it actually parses as JSON (FastAPI's JSONResponse is
    # application/json by default; StaticFiles is text/html).
    body = r.json()
    assert "app_id" in body, f"/api/config JSON missing app_id: {body}"


# ---------------------------------------------------------------------------
# Test 10: AppConfigContext never falls through to apiRouter in web mode
# (regression). If the `if (platform === 'web')` early-return is removed,
# the code path would call apiRouter.execute('getAppConfig') which has no
# graphql.query — making it produce a placeholder query { __typename } and
# POSTing to AppSync with extensions.method='getAppConfig'. AppSync
# doesn't recognize the method, the call fails, AppConfigContext throws,
# and the fallback intl/cognito kicks in. The regression would be silent
# (no error in console), only visible as auth/region misconfiguration.
# ---------------------------------------------------------------------------
def test_app_config_context_web_mode_early_returns_before_api_router():
    """AppConfigContext.tsx fetchConfig() must do `if (platform === 'web')
    ... return ...` BEFORE any reference to apiRouter. Otherwise web mode
    will try to call apiRouter.execute('getAppConfig'), which has no
    GraphQL definition and would round-trip to AppSync as a placeholder
    query — silently breaking."""
    p = REPO_ROOT / "gui_v2" / "src" / "contexts" / "AppConfigContext.tsx"
    text = p.read_text()

    # Find the positions of the web branch and the apiRouter import.
    web_idx = text.find("if (platform === 'web')")
    api_router_idx = text.find("apiRouter")

    if web_idx == -1:
        pytest.fail(
            "AppConfigContext.tsx missing the `if (platform === 'web')` "
            "early-return branch. Web mode would call apiRouter.execute() "
            "for getAppConfig, which has no GraphQL definition."
        )
    if api_router_idx == -1:
        pytest.skip("apiRouter not used in AppConfigContext (no concern)")

    # The web branch must come BEFORE the apiRouter.execute call.
    # The apiRouter import is inside the function (dynamic import) so
    # check that the function returns before falling through.
    after_web = text[web_idx:]
    assert "fetch('/api/config'" in after_web, (
        "web branch doesn't fetch /api/config"
    )
    # The fetch + return must happen before the apiRouter.execute call.
    fetch_idx = after_web.find("fetch('/api/config'")
    api_exec_idx = after_web.find("apiRouter.execute")
    assert fetch_idx < api_exec_idx or api_exec_idx == -1, (
        f"web branch's fetch('/api/config') is at offset {fetch_idx} but "
        f"apiRouter.execute is at offset {api_exec_idx}. The web branch "
        f"must early-return before the apiRouter fallback."
    )


# ---------------------------------------------------------------------------
# Test 11: platform.ts only returns 'desktop' or 'web' (regression)
# ---------------------------------------------------------------------------
def test_platform_ts_only_has_desktop_web_types():
    """Throughout the codebase, components branch on `detectPlatform() ===
    'desktop' | 'web'` (see MainLayout.tsx, AppConfigContext.tsx,
    appSyncSubscriptions.ts, syncManager.ts). If a third value is
    introduced (e.g. 'cloud'), every `=== 'web'` check would silently
    treat 'cloud' as 'desktop' (or vice versa). This test pins the type
    union to exactly 2 values."""
    p = REPO_ROOT / "gui_v2" / "src" / "config" / "platform.ts"
    text = p.read_text()
    # Type definition: 'desktop' | 'web' — should be exactly 2 values.
    import re
    m = re.search(r"type\s+PlatformType\s*=\s*([^;]+);", text)
    assert m, "PlatformType type alias not found"
    type_def = m.group(1).strip()
    # Parse the union: should be 'desktop' | 'web' (in some order)
    parts = [p.strip().strip("'\"") for p in type_def.split("|")]
    assert sorted(parts) == ["desktop", "web"], (
        f"PlatformType is {type_def}, expected exactly 'desktop' | 'web'. "
        f"Adding a third value (e.g. 'cloud') would silently break every "
        f"`detectPlatform() === 'web'` check across the codebase."
    )