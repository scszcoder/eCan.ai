"""The eCanAI llm-proxy base comes from this edition's auth_config.yml.

2026-10-26: the bundled provider rows carried only the CN proxy URL, so an intl
install fetched its model list (and sent eCanAI chat/embedding calls) to the CN
proxy with an intl key: every fetch failed and the list never updated."""
import pytest

from agent.cloud_api import endpoints
from auth.auth_config import AuthConfig

CN = "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1"
US = "https://vzepmyiimfwuzbjelxr3ir6uti0ikatm.lambda-url.us-east-1.on.aws/v1"


@pytest.fixture
def edition(monkeypatch):
    def use(app_id):
        monkeypatch.setenv("ECAN_APP_ID", app_id)
        AuthConfig.reload_config()
    yield use
    monkeypatch.undo()
    AuthConfig.reload_config()


@pytest.mark.parametrize("app_id, expected", [("intl", US), ("cn", CN)])
def test_each_edition_has_its_own_proxy(edition, app_id, expected):
    edition(app_id)
    assert endpoints.llm_proxy_base() == expected


def test_only_the_ecanai_row_is_repointed(edition):
    edition("intl")
    data = {"providers": {
        "eCanAI": {"provider": "ecanai", "base_url": CN},
        "OpenAI": {"provider": "openai", "base_url": "https://api.openai.com/v1"},
    }}
    endpoints.apply_llm_proxy_base(data)
    assert data["providers"]["eCanAI"]["base_url"] == US
    assert data["providers"]["OpenAI"]["base_url"] == "https://api.openai.com/v1"
