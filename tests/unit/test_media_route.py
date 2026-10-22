"""Media turns (images / video) go by the llm-proxy's direct route on a vision
model and are labelled multimodal. The normal route's gateway refused a 91 KB
screenshot with 413 (2026-10-21); a buyer's photo is 0.5-3 MB."""
from agent.ec_skills.llm_utils.media_route import DEFAULT_MEDIA_MODEL, media_route
from utils import log_scope

HOST = "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1"


def test_media_goes_by_the_direct_route_on_the_vision_model(monkeypatch):
    for k in ("ECAN_MEDIA_MODEL", "ECAN_MEDIA_LLM_URL", "ECAN_MEDIA_ROUTE"):
        monkeypatch.delenv(k, raising=False)
    host, model = media_route(HOST, "qwen3.8-flash")
    assert host == "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy-b/v1"
    assert model == DEFAULT_MEDIA_MODEL


def test_overrides_and_off_switch(monkeypatch):
    monkeypatch.setenv("ECAN_MEDIA_MODEL", "qwen-vl-max")
    monkeypatch.setenv("ECAN_MEDIA_LLM_URL", "https://example/api/x/v1")
    assert media_route(HOST, "qwen3.8-flash") == ("https://example/api/x/v1", "qwen-vl-max")
    monkeypatch.setenv("ECAN_MEDIA_ROUTE", "0")
    assert media_route(HOST, "qwen3.8-flash") == (HOST, "qwen3.8-flash")


def test_a_host_that_is_not_the_proxy_is_left_alone(monkeypatch):
    monkeypatch.delenv("ECAN_MEDIA_LLM_URL", raising=False)
    monkeypatch.delenv("ECAN_MEDIA_ROUTE", raising=False)
    assert media_route("https://other.example/v1", "m")[0] == "https://other.example/v1"


def test_the_modality_header_rides_only_while_set():
    tok = log_scope.set_scope(agent_id="a1")
    try:
        assert "X-Ecan-Modality" not in log_scope.attribution_headers()
        mtok = log_scope.update_scope(modality="multimodal")
        assert log_scope.attribution_headers()["X-Ecan-Modality"] == "multimodal"
        assert log_scope.attribution_headers()["X-Ecan-Agent-Id"] == "a1"
        log_scope.reset_scope(mtok)
        assert "X-Ecan-Modality" not in log_scope.attribution_headers()
    finally:
        log_scope.reset_scope(tok)
