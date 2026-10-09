"""A saved cloud endpoint of the OTHER region's backend is replaced on load.

2026-10-08: songc@yahoo.com last logged in on the CN app, so its settings.json
held the Tencent GraphQL/WS URLs; the US app restored the session (no
interactive login, so the per-app endpoints were never re-applied) and prompt
sync, the subscription client and the LLM proxy talked to the CN backend."""
from types import SimpleNamespace
from unittest.mock import patch

from gui.config import general_settings as gs

US = SimpleNamespace(is_cn=False, host="abc.appsync-realtime-api.us-east-1.amazonaws.com",
                     graphql_endpoint="https://abc.appsync-api.us-east-1.amazonaws.com/graphql",
                     ws_endpoint="wss://abc.appsync-realtime-api.us-east-1.amazonaws.com/graphql")
CN = SimpleNamespace(is_cn=True, host="ws-1.sh.run.tcloudbase.com",
                     graphql_endpoint="https://env.service.tcloudbase.com/api/graphql",
                     ws_endpoint="wss://ws-1.sh.run.tcloudbase.com/ws")


def _repair(cfg, settings):
    with patch("agent.cloud_api.endpoints.get_endpoint_config", return_value=cfg):
        return gs._repair_foreign_endpoints(settings), settings


def test_the_us_app_replaces_saved_cn_endpoints():
    changed, s = _repair(US, {"wan_api_endpoint": CN.graphql_endpoint, "ws_api_endpoint": CN.ws_endpoint,
                              "ws_api_host": CN.host})
    assert changed and s["wan_api_endpoint"] == US.graphql_endpoint
    assert s["ws_api_endpoint"] == US.ws_endpoint and s["ws_api_host"] == US.host


def test_the_cn_app_replaces_saved_us_endpoints():
    changed, s = _repair(CN, {"wan_api_endpoint": US.graphql_endpoint, "ws_api_endpoint": US.ws_endpoint,
                              "ws_api_host": US.host})
    assert changed and s["wan_api_endpoint"] == CN.graphql_endpoint and s["ws_api_host"] == CN.host


def test_a_same_region_custom_endpoint_is_left_alone():
    dev = "https://dev123.appsync-api.us-west-2.amazonaws.com/graphql"
    changed, s = _repair(US, {"wan_api_endpoint": dev, "ws_api_endpoint": "", "ws_api_host": ""})
    assert not changed and s["wan_api_endpoint"] == dev
