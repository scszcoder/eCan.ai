from unittest.mock import Mock

import pytest

from knowledge.lightrag_service_probe import ServiceProbeError, probe_model_service


def _response(status=200):
    response = Mock(status_code=status, ok=200 <= status < 300, text="{}", reason="")
    response.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}
    return response


@pytest.mark.parametrize("kind,path", [
    ("llm", "/chat/completions"),
    ("embedding", "/embeddings"),
    ("rerank", "/rerank"),
])
def test_openai_compatible_service_probe(monkeypatch, kind, path):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_service_probe.requests.post", request)
    prefix = {"llm": "LLM", "embedding": "EMBEDDING", "rerank": "RERANK"}[kind]

    result = probe_model_service(kind, {
        f"{prefix}_BINDING": "ryoais",
        f"{prefix}_BINDING_HOST": "https://example.test/v1",
        f"{prefix}_MODEL": "test-model",
        f"{prefix}_BINDING_API_KEY": "secret",
    })

    assert result["success"] is True
    assert result["available"] is True
    assert result["url"].endswith(path)
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert request.call_args.kwargs["timeout"] == (3, 7)
    assert request.call_args.kwargs["verify"] is False


def test_probe_can_enable_strict_ssl_verification(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_service_probe.requests.post", request)
    probe_model_service("llm", {
        "LLM_BINDING": "openai",
        "LLM_BINDING_HOST": "https://example.test/v1",
        "LLM_MODEL": "test-model",
        "SSL_VERIFY": "true",
    })
    assert request.call_args.kwargs["verify"] is True


def test_existing_rerank_endpoint_is_not_duplicated(monkeypatch):
    request = Mock(return_value=_response())
    monkeypatch.setattr("knowledge.lightrag_service_probe.requests.post", request)
    result = probe_model_service("rerank", {
        "RERANK_BINDING": "ryoais",
        "RERANK_BINDING_HOST": "http://localhost:4668/api/rerank",
        "RERANK_MODEL": "reranker",
    })
    assert result["url"] == "http://localhost:4668/api/rerank"


def test_probe_requires_selected_model():
    with pytest.raises(ServiceProbeError) as exc:
        probe_model_service("embedding", {
            "EMBEDDING_BINDING": "openai",
            "EMBEDDING_BINDING_HOST": "https://example.test/v1",
        })
    assert exc.value.category == "missing_config"
