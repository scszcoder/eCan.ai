"""
Regression tests for CN/Intl endpoint routing.

All endpoint resolution is delegated to ``CloudEndpointConfig`` which reads
from ``apps/{app_id}/config/auth_config.yml`` — no hardcoded URLs in code.
The APPSYNC.GRAPHQL_ENDPOINT field is the single source of truth.

Bug history: ``get_tcb_api_url`` used to read
``MainWindow.getWanApiEndpoint()`` (which returns
``settings.json['wan_api_endpoint']``) BEFORE consulting the
``CLOUDBASE.ENV_ID`` configured in ``apps/cn/config/auth_config.yml``.
Since the Intl settings_template.json writes an AWS AppSync URL into
``wan_api_endpoint``, every CN login caused the post-login agent /
skill / prompt sync to silently hit AWS AppSync and get 401.

Fix: ``CloudEndpointConfig`` reads APPSYNC.GRAPHQL_ENDPOINT from the
active app's auth_config.yml — TCB for CN, AppSync for Intl.
"""

import os
import importlib


def _reload(monkeypatch):
    """Reset cached singletons and reload the module."""
    import agent.cloud_api.cloud_api as ca
    import agent.cloud_api.endpoints as ep
    monkeypatch.setattr(ca, "_APPSYNC_ENDPOINT_LOGGED", False)
    monkeypatch.setattr(ep, "_instance", None)
    importlib.reload(ca)
    importlib.reload(ep)
    return ca, ep


class TestCloudEndpointConfigCN:
    """CN build must use TCB endpoints, never AWS."""

    def test_cn_graphql_endpoint_is_tcb(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _, ep = _reload(monkeypatch)
        cfg = ep.get_endpoint_config()
        assert cfg.is_cn, "CN build must report is_cn=True"
        assert "tcloudbase.com" in cfg.graphql_endpoint, (
            f"CN GraphQL must be Tencent TCB, got: {cfg.graphql_endpoint}"
        )
        assert "amazonaws.com" not in cfg.graphql_endpoint, (
            f"CN GraphQL leaked to AWS: {cfg.graphql_endpoint}"
        )

    def test_cn_ws_endpoint_is_tcb(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _, ep = _reload(monkeypatch)
        cfg = ep.get_endpoint_config()
        assert "tcloudbase.com" in cfg.ws_endpoint, (
            f"CN WS must be Tencent TCB, got: {cfg.ws_endpoint}"
        )

    def test_cn_host_is_tcb(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _, ep = _reload(monkeypatch)
        cfg = ep.get_endpoint_config()
        assert "tcloudbase.com" in cfg.host, (
            f"CN host must be Tencent TCB, got: {cfg.host}"
        )


class TestCloudEndpointConfigIntl:
    """Intl build must use AWS AppSync endpoints."""

    def test_intl_graphql_endpoint_is_aws(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _, ep = _reload(monkeypatch)
        cfg = ep.get_endpoint_config()
        assert not cfg.is_cn, "Intl build must report is_cn=False"
        assert ("appsync-api" in cfg.graphql_endpoint
                or "amazonaws.com" in cfg.graphql_endpoint), (
            f"Intl GraphQL must be AWS AppSync, got: {cfg.graphql_endpoint}"
        )

    def test_intl_ws_endpoint_is_appsync_realtime(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _, ep = _reload(monkeypatch)
        cfg = ep.get_endpoint_config()
        assert "appsync-realtime-api" in cfg.ws_endpoint, (
            f"Intl WS must be AppSync realtime, got: {cfg.ws_endpoint}"
        )


class TestGetAppsyncEndpointUnified:
    """``get_appsync_endpoint`` delegates to CloudEndpointConfig."""

    def test_cn_uses_tcb(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        ca, _ = _reload(monkeypatch)
        url = ca.get_appsync_endpoint()
        assert "tcloudbase.com" in url, (
            f"CN get_appsync_endpoint must return TCB URL, got: {url}"
        )

    def test_intl_uses_aws(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        ca, _ = _reload(monkeypatch)
        url = ca.get_appsync_endpoint()
        assert ("appsync-api" in url or "amazonaws.com" in url), (
            f"Intl get_appsync_endpoint must return AppSync URL, got: {url}"
        )


class TestGetTcbApiUrlUnified:
    """``get_tcb_api_url`` delegates to CloudEndpointConfig (CN only)."""

    def test_returns_tcb_for_cn(self, monkeypatch):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        ca, _ = _reload(monkeypatch)
        url = ca.get_tcb_api_url()
        assert "tcloudbase.com" in url, (
            f"get_tcb_api_url (CN) must return TCB URL, got: {url}"
        )

    def test_returns_intl_aws_for_intl(self, monkeypatch):
        """get_tcb_api_url is CN-specific but delegates to CloudEndpointConfig
        which returns the correct endpoint for the current app_id."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        ca, _ = _reload(monkeypatch)
        url = ca.get_tcb_api_url()
        # Returns Intl AppSync when ECAN_APP_ID=intl
        assert ("appsync-api" in url or "amazonaws.com" in url), (
            f"get_tcb_api_url (Intl) must return AppSync URL, got: {url}"
        )


class TestConfigFile:
    """Config files must have the correct APPSYNC fields."""

    def test_cn_auth_config_has_appsync_fields(self):
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parents[3] / "apps" / "cn" / "config" / "auth_config.yml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert "APPSYNC" in cfg, "CN auth_config.yml must have APPSYNC section"
        assert "GRAPHQL_ENDPOINT" in cfg["APPSYNC"], "APPSYNC.GRAPHQL_ENDPOINT required"
        assert "WS_ENDPOINT" in cfg["APPSYNC"], "APPSYNC.WS_ENDPOINT required"
        assert "tcloudbase.com" in cfg["APPSYNC"]["GRAPHQL_ENDPOINT"], (
            "CN GRAPHQL_ENDPOINT must be TCB URL"
        )

    def test_intl_auth_config_has_appsync_fields(self):
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).resolve().parents[3] / "apps" / "intl" / "config" / "auth_config.yml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        assert "APPSYNC" in cfg, "Intl auth_config.yml must have APPSYNC section"
        assert "GRAPHQL_ENDPOINT" in cfg["APPSYNC"], "APPSYNC.GRAPHQL_ENDPOINT required"
        assert "appsync-api" in cfg["APPSYNC"]["GRAPHQL_ENDPOINT"], (
            "Intl GRAPHQL_ENDPOINT must be AWS AppSync URL"
        )
