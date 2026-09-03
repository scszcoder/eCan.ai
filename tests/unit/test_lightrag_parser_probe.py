"""Tests for non-destructive external parser probes."""

from unittest.mock import Mock

import pytest

from knowledge.lightrag_parser_probe import probe_parser


def _response(status: int = 200, *, body=None, content_type: str = "application/json"):
    response = Mock()
    response.status_code = status
    response.ok = 200 <= status < 400
    response.headers = {"content-type": content_type}
    response.reason = "reason"
    response.text = "{}" if body is None else str(body)
    response.json.return_value = body if body is not None else {"status": "ok"}
    return response


def test_mineru_local_uses_health_endpoint(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000/",
        "MINERU_LOCAL_API_KEY": "local-secret",
    })

    assert result["success"] is True
    assert result["mode"] == "local"
    assert result["url"] == "http://127.0.0.1:8000/health"
    assert request.call_args.kwargs["headers"] == {
        "Authorization": "Bearer local-secret"
    }
    assert request.call_args.kwargs["verify"] is False
    request.assert_called_once()


def test_mineru_probe_honors_explicit_ssl_verification(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    probe_parser("mineru", {
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "https://mineru.example",
        "MINERU_LOCAL_API_KEY": "secret",
        "SSL_VERIFY": "true",
    })

    assert request.call_args.kwargs["verify"] is True


def test_mineru_official_sends_bearer_token(monkeypatch):
    request = Mock(return_value=_response(404, body={"code": 404, "msg": "task not found"}))
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "official",
        "MINERU_OFFICIAL_ENDPOINT": "https://mineru.example",
        "MINERU_OFFICIAL_API_KEY": "secret",
    })

    assert result["success"] is True
    assert result["mode"] == "official"
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}


def test_mineru_official_reports_auth_failure(monkeypatch):
    monkeypatch.setattr(
        "knowledge.lightrag_parser_probe.requests.request",
        Mock(return_value=_response(401, body={"message": "unauthorized"})),
    )
    with pytest.raises(RuntimeError, match="鉴权失败"):
        probe_parser("mineru", {
            "MINERU_API_MODE": "official",
            "MINERU_OFFICIAL_ENDPOINT": "https://mineru.example",
            "MINERU_OFFICIAL_API_KEY": "bad",
        })


def test_docling_local_uses_health_endpoint(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("docling", {
        "DOCLING_PROVIDER": "local",
        "DOCLING_LOCAL_ENDPOINT": "http://127.0.0.1:5001",
        "DOCLING_LOCAL_API_KEY": "docling-local-secret",
    })

    assert result["success"] is True
    assert result["url"] == "http://127.0.0.1:5001/health"
    assert request.call_args.kwargs["headers"] == {
        "Authorization": "Bearer docling-local-secret"
    }


@pytest.mark.parametrize("engine,settings,message", [
    ("mineru", {"MINERU_API_MODE": "local"}, "MINERU_LOCAL_ENDPOINT"),
    ("mineru", {"MINERU_API_MODE": "local", "MINERU_LOCAL_ENDPOINT": "http://mineru"}, "MINERU_LOCAL_API_KEY"),
    # official mode uses MINERU_OFFICIAL_ENDPOINT with default, so key is the first check
    ("mineru", {"MINERU_API_MODE": "official"}, "MINERU_OFFICIAL_API_KEY"),
    ("mineru", {"MINERU_API_MODE": "official", "MINERU_OFFICIAL_ENDPOINT": "http://mineru"}, "MINERU_OFFICIAL_API_KEY"),
    ("mineru", {"MINERU_API_MODE": "ecanai"}, "MINERU_ECANAI_ENDPOINT"),
    ("mineru", {"MINERU_API_MODE": "ecanai", "MINERU_ECANAI_ENDPOINT": "http://ecanai"}, "MINERU_API_TOKEN"),
    ("docling", {}, "DOCLING_ECANAI_ENDPOINT"),
    ("docling", {"DOCLING_ECANAI_ENDPOINT": "http://docling"}, "DOCLING_API_KEY"),
    ("docling", {"DOCLING_PROVIDER": "local"}, "DOCLING_LOCAL_ENDPOINT"),
    ("docling", {"DOCLING_PROVIDER": "local", "DOCLING_LOCAL_ENDPOINT": "http://docling"}, "DOCLING_LOCAL_API_KEY"),
    ("docling", {"DOCLING_PROVIDER": "official"}, "DOCLING_OFFICIAL_ENDPOINT"),
    ("docling", {"DOCLING_PROVIDER": "official", "DOCLING_OFFICIAL_ENDPOINT": "http://docling"}, "DOCLING_OFFICIAL_API_KEY"),
])
def test_probe_reports_missing_configuration(engine, settings, message):
    with pytest.raises(ValueError, match=message):
        probe_parser(engine, settings)


# =============================================================================
# Comprehensive tests: all 3 MinerU modes × all key scenarios
# =============================================================================

def test_mineru_local_reads_mineru_local_api_key(monkeypatch):
    """Local mode reads MINERU_LOCAL_API_KEY, not MINERU_API_TOKEN."""
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000",
        "MINERU_LOCAL_API_KEY": "my-local-key",
        # These should NOT be used
        "MINERU_API_TOKEN": "wrong-key",
        "MINERU_OFFICIAL_API_KEY": "wrong-key",
    })

    assert result["success"] is True
    assert result["mode"] == "local"
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer my-local-key"}


def test_mineru_official_reads_mineru_official_api_key(monkeypatch):
    """Official mode reads MINERU_OFFICIAL_API_KEY, not MINERU_API_TOKEN."""
    request = Mock(return_value=_response(404, body={"code": 404, "msg": "not found"}))
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "official",
        "MINERU_OFFICIAL_ENDPOINT": "https://mineru.net",
        "MINERU_OFFICIAL_API_KEY": "my-official-key",
        # These should NOT be used
        "MINERU_API_TOKEN": "wrong-key",
        "MINERU_LOCAL_API_KEY": "wrong-key",
    })

    assert result["success"] is True
    assert result["mode"] == "official"
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer my-official-key"}


def test_mineru_ecanai_reads_mineru_api_token_not_local_key(monkeypatch):
    """eCanAI mode reads MINERU_API_TOKEN (UI field), NOT MINERU_LOCAL_API_KEY."""
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "ecanai",
        "MINERU_ECANAI_ENDPOINT": "https://ecanai.proxy/api/llm-proxy/v1",
        "MINERU_API_TOKEN": "user-ecanai-key",
        # MINERU_LOCAL_API_KEY should be ignored (it was from local mode)
        "MINERU_LOCAL_API_KEY": "stale-local-key",
    })

    assert result["success"] is True
    assert result["mode"] == "ecanai"
    assert result["url"] == "https://ecanai.proxy/api/llm-proxy/v1/health"
    # The user-typed key (MINERU_API_TOKEN) should be used, NOT the stale local key
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer user-ecanai-key"}


def test_mineru_ecanai_rejects_local_key_when_account_token_empty(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    with pytest.raises(ValueError, match="ECANAI_LLM_API_KEY"):
        probe_parser("mineru", {
            "MINERU_API_MODE": "ecanai",
            "MINERU_ECANAI_ENDPOINT": "https://ecanai.proxy/api/llm-proxy/v1",
            "MINERU_API_TOKEN": "",
            "MINERU_LOCAL_API_KEY": "my-local-key",
        })


def test_mineru_ecanai_uses_ecanai_endpoint_not_local_endpoint(monkeypatch):
    """eCanAI mode uses MINERU_ECANAI_ENDPOINT, not MINERU_LOCAL_ENDPOINT."""
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "ecanai",
        "MINERU_ECANAI_ENDPOINT": "https://ecanai.proxy/api/v1",
        "MINERU_LOCAL_ENDPOINT": "http://localhost:8000",  # Should be ignored
        "MINERU_API_TOKEN": "any-key",
    })

    assert result["url"] == "https://ecanai.proxy/api/v1/health"


# =============================================================================
# Comprehensive tests: all 3 Docling modes × all key scenarios
# =============================================================================

def test_docling_local_reads_docling_local_api_key(monkeypatch):
    """Local mode reads DOCLING_LOCAL_API_KEY, not DOCLING_API_KEY."""
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("docling", {
        "DOCLING_PROVIDER": "local",
        "DOCLING_LOCAL_ENDPOINT": "http://127.0.0.1:5001",
        "DOCLING_LOCAL_API_KEY": "my-local-key",
        # These should NOT be used
        "DOCLING_API_KEY": "wrong-key",
    })

    assert result["success"] is True
    assert result["url"] == "http://127.0.0.1:5001/health"
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer my-local-key"}


def test_docling_official_reads_docling_official_api_key(monkeypatch):
    """Official mode reads DOCLING_OFFICIAL_API_KEY."""
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("docling", {
        "DOCLING_PROVIDER": "official",
        "DOCLING_OFFICIAL_ENDPOINT": "https://docling.ai",
        "DOCLING_OFFICIAL_API_KEY": "my-official-key",
        # Should NOT be used
        "DOCLING_API_KEY": "wrong-key",
    })

    assert result["success"] is True
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer my-official-key"}


def test_docling_ecanai_reads_docling_api_key_not_local_key(monkeypatch):
    """eCanAI mode reads DOCLING_API_KEY (UI field), NOT DOCLING_LOCAL_API_KEY."""
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("docling", {
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_ECANAI_ENDPOINT": "https://ecanai.proxy/api/llm-proxy/v1",
        "DOCLING_API_KEY": "user-ecanai-key",
        # DOCLING_LOCAL_API_KEY should be ignored (it was from local mode)
        "DOCLING_LOCAL_API_KEY": "stale-local-key",
    })

    assert result["success"] is True
    assert result["url"] == "https://ecanai.proxy/api/llm-proxy/v1/health"
    # The user-typed key should be used, NOT the stale local key
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer user-ecanai-key"}


def test_docling_ecanai_rejects_local_key_when_account_key_empty(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    with pytest.raises(ValueError, match="ECANAI_LLM_API_KEY"):
        probe_parser("docling", {
            "DOCLING_PROVIDER": "ecanai",
            "DOCLING_ECANAI_ENDPOINT": "https://ecanai.proxy/api/llm-proxy/v1",
            "DOCLING_API_KEY": "",
            "DOCLING_LOCAL_API_KEY": "my-local-key",
        })
