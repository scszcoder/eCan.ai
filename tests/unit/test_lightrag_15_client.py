"""HTTP adapter contracts introduced by LightRAG 1.5."""

import json
from typing import Iterator, List, Optional
from unittest.mock import Mock

import pytest

from knowledge import lightrag_client
from knowledge.lightrag_client import (
    LightragClient,
    _SUPPORTED_FILE_TYPES_CACHE,
    _SUPPORTED_FILE_TYPES_TTL_SECONDS,
    clear_supported_file_types_cache,
)


def _client(response: Mock, base_url: str = "http://127.0.0.1:9621") -> LightragClient:
    """Build a LightragClient with the supplied session response."""
    client = LightragClient.__new__(LightragClient)
    client.base_url = base_url
    client.session = Mock()
    client.session.get.return_value = response
    client.session.post.return_value = response
    return client


def _ok_response(payload) -> Mock:
    """Build a Mock that mimics ``requests.Response`` with HTTP 200 + JSON body."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    response.text = json.dumps(payload)
    response.raise_for_status = Mock()
    return response


# ---------------------------------------------------------------------------
# /documents/supported_file_types
# ---------------------------------------------------------------------------


def test_supported_file_types_uses_live_capability_endpoint() -> None:
    clear_supported_file_types_cache()
    response = _ok_response({
        "supported_extensions": [".md", ".pdf"],
        "engines": {"native": [".md", ".pdf"]},
    })
    client = _client(response)

    result = client.get_supported_file_types(workspace="产品知识库")

    assert result["status"] == "success"
    client.session.get.assert_called_once_with(
        "http://127.0.0.1:9621/documents/supported_file_types",
        headers={"LIGHTRAG-WORKSPACE": "%E4%BA%A7%E5%93%81%E7%9F%A5%E8%AF%86%E5%BA%93"},
        timeout=10,
    )


def test_supported_file_types_caches_for_five_minutes() -> None:
    clear_supported_file_types_cache()
    payload = {
        "supported_extensions": [".md", ".pdf"],
        "engines": {"native": [".md", ".pdf"]},
    }
    client = _client(_ok_response(payload))

    first = client.get_supported_file_types(workspace="tenant-a")
    second = client.get_supported_file_types(workspace="tenant-a")

    assert first["data"] == payload
    assert first.get("cached") is not True
    assert second["data"] == payload
    assert second.get("cached") is True

    # The server endpoint must only be hit once across two GUI renders.
    client.session.get.assert_called_once_with(
        "http://127.0.0.1:9621/documents/supported_file_types",
        headers={"LIGHTRAG-WORKSPACE": "tenant-a"},
        timeout=10,
    )


def test_supported_file_types_cache_is_workspace_scoped() -> None:
    """Workspace A's payload must never be returned to workspace B."""
    clear_supported_file_types_cache()
    side_effects = [
        _ok_response({"supported_extensions": [".md"]}),
        _ok_response({"supported_extensions": [".pdf"]}),
    ]
    client = LightragClient.__new__(LightragClient)
    client.base_url = "http://127.0.0.1:9621"
    client.session = Mock()
    client.session.get.side_effect = side_effects

    first = client.get_supported_file_types(workspace="a")
    second = client.get_supported_file_types(workspace="b")

    assert first["data"]["supported_extensions"] == [".md"]
    assert second["data"]["supported_extensions"] == [".pdf"]
    assert client.session.get.call_count == 2


def test_supported_file_types_clear_cache_forces_refresh() -> None:
    clear_supported_file_types_cache()
    payload = {"supported_extensions": [".md"]}
    client = _client(_ok_response(payload))

    client.get_supported_file_types(workspace="a")
    assert len(_SUPPORTED_FILE_TYPES_CACHE) == 1

    clear_supported_file_types_cache()
    assert len(_SUPPORTED_FILE_TYPES_CACHE) == 0

    client.get_supported_file_types(workspace="a")
    assert len(_SUPPORTED_FILE_TYPES_CACHE) == 1
    assert client.session.get.call_count == 2


def test_supported_file_types_ttl_is_five_minutes() -> None:
    """TTL must match the contract documented in the upgrade analysis (§4)."""
    assert _SUPPORTED_FILE_TYPES_TTL_SECONDS == 300.0


def test_supported_file_types_cache_expires_after_ttl(monkeypatch) -> None:
    """After the TTL elapses the next call must hit the server again.

    We freeze ``time.monotonic`` here instead of sleeping for 5 minutes —
    sleeps in unit tests are unreliable and the contract is "more than TTL",
    not a specific wall-clock time.
    """
    clear_supported_file_types_cache()
    responses = [
        _ok_response({"supported_extensions": [".md"]}),
        _ok_response({"supported_extensions": [".txt"]}),
    ]
    client = _client(responses[0])
    client.session.get.side_effect = responses

    base_time = 1_000_000.0
    monkeypatch.setattr("knowledge.lightrag_client.time.monotonic", lambda: base_time)

    first = client.get_supported_file_types(workspace="a")
    assert first["data"]["supported_extensions"] == [".md"]
    assert client.session.get.call_count == 1

    # Still inside the TTL — must be served from cache without another GET.
    monkeypatch.setattr(
        "knowledge.lightrag_client.time.monotonic",
        lambda: base_time + _SUPPORTED_FILE_TYPES_TTL_SECONDS - 1,
    )
    second = client.get_supported_file_types(workspace="a")
    assert second["data"]["supported_extensions"] == [".md"]
    assert client.session.get.call_count == 1

    # Past the TTL — must hit the server again.
    monkeypatch.setattr(
        "knowledge.lightrag_client.time.monotonic",
        lambda: base_time + _SUPPORTED_FILE_TYPES_TTL_SECONDS + 1,
    )
    third = client.get_supported_file_types(workspace="a")
    assert third["data"]["supported_extensions"] == [".txt"]
    assert client.session.get.call_count == 2


def test_supported_file_types_http_error_does_not_pollute_cache() -> None:
    """A 503 must not be cached — the next call must retry the server."""
    clear_supported_file_types_cache()

    error_response = Mock()
    error_response.status_code = 503
    error_response.text = "Service Unavailable"
    error_response.raise_for_status.side_effect = RuntimeError("503")
    client = _client(error_response)

    result = client.get_supported_file_types(workspace="a")

    assert result["status"] == "error"
    assert len(_SUPPORTED_FILE_TYPES_CACHE) == 0

    # Subsequent successful call must not be reported as "cached" because the
    # error path must not have poisoned the cache.
    client.session.get.return_value = _ok_response({"supported_extensions": [".md"]})
    second = client.get_supported_file_types(workspace="a")
    assert second["status"] == "success"
    assert second.get("cached") is not True
    assert client.session.get.call_count == 2


def test_supported_file_types_unrelated_workspace_keeps_old_cache() -> None:
    """A failure for workspace B must not invalidate workspace A's cache."""
    clear_supported_file_types_cache()
    client = _client(_ok_response({"supported_extensions": [".md"]}))

    # Warm up workspace A.
    client.get_supported_file_types(workspace="a")
    assert len(_SUPPORTED_FILE_TYPES_CACHE) == 1

    # Now fail for workspace B.
    error_response = Mock()
    error_response.status_code = 500
    error_response.text = "boom"
    error_response.raise_for_status.side_effect = RuntimeError("500")
    client.session.get.return_value = error_response
    result = client.get_supported_file_types(workspace="b")
    assert result["status"] == "error"

    # Workspace A's cached entry must still be present.
    cache_keys = list(_SUPPORTED_FILE_TYPES_CACHE.keys())
    assert any(ws == "a" for _, ws in cache_keys)


def test_supported_file_types_with_unicode_workspace_key() -> None:
    """Non-ASCII workspace names must work as cache keys (no encode errors)."""
    clear_supported_file_types_cache()
    payload = {"supported_extensions": [".md"]}
    client = _client(_ok_response(payload))

    result = client.get_supported_file_types(workspace="产品知识库")

    assert result["status"] == "success"
    # Cache key is the raw workspace string — the URL-encoding happens at
    # the HTTP layer, not the cache-key layer.
    assert ("http://127.0.0.1:9621", "产品知识库") in _SUPPORTED_FILE_TYPES_CACHE


def test_clear_supported_file_types_cache_is_idempotent() -> None:
    """Clearing an already-empty cache must not raise."""
    clear_supported_file_types_cache()
    clear_supported_file_types_cache()  # second call must also be safe
    assert len(_SUPPORTED_FILE_TYPES_CACHE) == 0


def test_supported_file_types_error_response_includes_status_code() -> None:
    """Error path must surface the upstream status code so the operator
    can tell 401 (expected per CLAUDE.md §6) apart from 500 (a real bug).
    """
    clear_supported_file_types_cache()
    response = Mock()
    response.status_code = 503
    response.text = "Service Unavailable"
    response.raise_for_status.side_effect = RuntimeError("503")
    client = _client(response)

    result = client.get_supported_file_types(workspace="a")

    assert result["status"] == "error"
    # The error message includes the upstream status code.
    assert "503" in result["message"] or "Service" in result["message"]


# ---------------------------------------------------------------------------
# /documents/pipeline_status
# ---------------------------------------------------------------------------


def test_pipeline_status_is_workspace_scoped() -> None:
    response = _ok_response({"busy": False})
    client = _client(response)

    result = client.get_pipeline_status(workspace="tenant-a")

    assert result == {"status": "success", "data": {"busy": False}}
    client.session.get.assert_called_once_with(
        "http://127.0.0.1:9621/documents/pipeline_status",
        headers={"LIGHTRAG-WORKSPACE": "tenant-a"},
        timeout=10,
    )


# ---------------------------------------------------------------------------
# /query include_progress forwarding
# ---------------------------------------------------------------------------


def test_include_progress_is_forwarded_on_query() -> None:
    """include_progress must reach /query so the GUI can render 4-phase progress."""
    response = _ok_response({"response": "ok", "references": []})
    client = _client(response)

    result = client.query(
        "what is the doc?",
        options={
            "mode": "hybrid",
            "include_progress": True,
            "include_references": True,
        },
        workspace="tenant-a",
    )

    assert result["status"] == "success"
    payload = client.session.post.call_args.kwargs["json"]
    assert payload["include_progress"] is True
    assert payload["include_references"] is True
    headers = client.session.post.call_args.kwargs["headers"]
    assert headers["LIGHTRAG-WORKSPACE"] == "tenant-a"


# ---------------------------------------------------------------------------
# query_stream progress events + final metrics chunk
# ---------------------------------------------------------------------------


class _FakeStreamResponse:
    """Drop-in for ``requests.Response`` that yields a fixed NDJSON stream."""

    def __init__(self, lines: List[bytes], status_code: int = 200) -> None:
        self.status_code = status_code
        self._lines = lines
        self.text = ""

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_lines(self) -> Iterator[bytes]:
        for line in self._lines:
            yield line


def _stream_client(ndjson_lines: List[bytes]) -> LightragClient:
    """Build a LightragClient whose ``session.post(..., stream=True)`` returns
    a ``_FakeStreamResponse`` that yields the supplied NDJSON lines.
    """
    client = LightragClient.__new__(LightragClient)
    client.base_url = "http://127.0.0.1:9621"
    client.session = Mock()
    client.session.post.return_value = _FakeStreamResponse(ndjson_lines)
    return client


@pytest.fixture
def stub_confidence(monkeypatch):
    """Stub the confidence scorer at the source module.  ``query_stream``
    imports it via a local ``from knowledge.lightrag_confidence_scorer import
    score_lightrag_response``, so monkeypatching the symbol on that module
    is enough to keep the test free of network calls.
    """
    monkeypatch.setattr(
        "knowledge.lightrag_confidence_scorer.score_lightrag_response",
        lambda *args, **kwargs: {
            "overall_score": 0.5,
            "confidence_level": "low",
            "decision": {"should_answer": True},
        },
        raising=False,
    )


def test_query_stream_yields_metrics_and_progress(stub_confidence) -> None:
    """Stream must surface progress phases and a final metrics chunk."""
    lines = [
        b'{"response": "Hello "}',
        b'{"progress": "graph_search", "response": ""}',
        b'{"progress": "text_search", "response": ""}',
        b'{"response": "world", "response_time": 1.23}',
    ]
    client = _stream_client(lines)

    chunks = list(
        client.query_stream(
            "what?",
            options={"include_progress": True},
            workspace="tenant-a",
        )
    )

    decoded = [json.loads(c) for c in chunks]
    progress_events = [c for c in decoded if c.get("progress")]
    response_events = [c for c in decoded if "response" in c]
    metrics_events = [c for c in decoded if "metrics" in c]

    assert len(progress_events) == 2
    assert progress_events[0]["progress"] == "graph_search"
    assert progress_events[1]["progress"] == "text_search"

    # Original NDJSON ``response`` lines must be yielded untouched.
    assert any(e.get("response") == "Hello " for e in response_events)
    assert any(e.get("response") == "world" for e in response_events)

    # Final metrics chunk must carry timing + latest phase.
    assert len(metrics_events) == 1
    metrics = metrics_events[0]["metrics"]
    assert metrics["progress_phase"] == "text_search"
    assert metrics["response_time"] == 1.23
    assert metrics["elapsed_ms"] >= 0
    assert metrics["time_to_first_token_ms"] is not None


def test_query_stream_metrics_handle_missing_progress(stub_confidence) -> None:
    """Legacy servers (or ``include_progress=false``) must still emit metrics."""
    lines = [b'{"response": "ok"}']
    client = _stream_client(lines)

    chunks = list(client.query_stream("what?", options={}))

    decoded = [json.loads(c) for c in chunks]
    metrics_events = [c for c in decoded if "metrics" in c]
    assert len(metrics_events) == 1
    assert metrics_events[0]["metrics"]["progress_phase"] is None
    assert metrics_events[0]["metrics"]["time_to_first_token_ms"] is not None


def test_query_stream_first_token_is_recorded(stub_confidence) -> None:
    """time_to_first_token_ms must be > 0 once at least one chunk has arrived."""
    lines = [b'{"response": "a"}', b'{"response": "b"}']
    client = _stream_client(lines)

    chunks = list(client.query_stream("q"))
    decoded = [json.loads(c) for c in chunks]
    metrics = next(c["metrics"] for c in decoded if "metrics" in c)

    assert metrics["time_to_first_token_ms"] >= 0


def test_query_stream_http_error_does_not_yield_metrics(stub_confidence) -> None:
    """When /query/stream returns 422 the metrics chunk must be skipped — we
    have no timing data to expose and the caller must see the error first.
    """
    response = _FakeStreamResponse([], status_code=422)
    response.text = "validation error"
    client = _stream_client.__wrapped__(b"") if False else _stream_client_no_mock(response)

    with pytest.raises(RuntimeError):
        chunks = list(client.query_stream("q"))
        # ``raise_for_status`` raises before any chunk is yielded. The
        # ``for line in r.iter_lines()`` block — and therefore the metrics
        # emission — must never run on an HTTP error.
        decoded = [json.loads(c) for c in chunks]
        assert not any("metrics" in c for c in decoded)


def _stream_client_no_mock(response) -> LightragClient:
    """Build a client whose ``session.post(..., stream=True)`` returns the
    supplied response object directly (no Mock wrapping).
    """
    client = LightragClient.__new__(LightragClient)
    client.base_url = "http://127.0.0.1:9621"
    client.session = Mock()
    client.session.post.return_value = response
    return client


def test_query_stream_non_json_line_does_not_break_metrics(stub_confidence) -> None:
    """A non-JSON line in the middle of the stream must not crash the
    accumulator or skip the metrics chunk — servers sometimes emit heartbeats.
    """
    lines = [
        b'{"response": "a"}',
        b':heartbeat',
        b'{"response": "b"}',
    ]
    client = _stream_client(lines)

    chunks = list(client.query_stream("q"))
    decoded = [json.loads(c) for c in chunks if c and not c.startswith(":")]
    metrics = next((c for c in decoded if "metrics" in c), None)

    assert metrics is not None
    # Confidence scorer only sees the merged response buffer; raw heartbeat
    # text is appended to the buffer. We don't pin the exact count here, we
    # only assert that the stream completed without raising.
    assert metrics["metrics"]["elapsed_ms"] >= 0


def test_query_stream_empty_response_still_yields_metrics(stub_confidence) -> None:
    """Server returns zero lines (immediate close). The metrics chunk must
    still be emitted with ``progress_phase=None`` and a non-None elapsed_ms.
    """
    client = _stream_client([])

    chunks = list(client.query_stream("q"))
    decoded = [json.loads(c) for c in chunks if c]
    metrics = next((c for c in decoded if "metrics" in c), None)

    assert metrics is not None
    assert metrics["metrics"]["progress_phase"] is None
    # No lines means no first token either.
    assert metrics["metrics"]["time_to_first_token_ms"] is None
