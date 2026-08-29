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
        "MINERU_API_TOKEN": "local-secret",
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
        "MINERU_API_TOKEN": "secret",
        "SSL_VERIFY": "true",
    })

    assert request.call_args.kwargs["verify"] is True


def test_mineru_official_sends_bearer_token(monkeypatch):
    request = Mock(return_value=_response(404, body={"code": 404, "msg": "task not found"}))
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("mineru", {
        "MINERU_API_MODE": "official",
        "MINERU_OFFICIAL_ENDPOINT": "https://mineru.example",
        "MINERU_API_TOKEN": "secret",
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
            "MINERU_API_TOKEN": "bad",
        })


def test_docling_uses_health_endpoint(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_parser_probe.requests.request", request)

    result = probe_parser("docling", {
        "DOCLING_ENDPOINT": "http://docling:5001",
        "DOCLING_API_KEY": "docling-secret",
    })

    assert result["success"] is True
    assert result["url"] == "http://docling:5001/health"
    assert request.call_args.kwargs["headers"] == {
        "Authorization": "Bearer docling-secret"
    }


@pytest.mark.parametrize("engine,settings,message", [
    ("mineru", {"MINERU_API_MODE": "local"}, "MINERU_LOCAL_ENDPOINT"),
    ("mineru", {"MINERU_API_MODE": "local", "MINERU_LOCAL_ENDPOINT": "http://mineru"}, "MINERU_API_TOKEN"),
    ("mineru", {"MINERU_API_MODE": "official"}, "MINERU_API_TOKEN"),
    ("docling", {}, "DOCLING_ENDPOINT"),
    ("docling", {"DOCLING_ENDPOINT": "http://docling"}, "DOCLING_API_KEY"),
])
def test_probe_reports_missing_configuration(engine, settings, message):
    with pytest.raises(ValueError, match=message):
        probe_parser(engine, settings)
