"""settings.getProviderModels rate-limit deduplication (gui/ipc/.../settings_handler.py).

TCB's llm-proxy rate-limits per source IP. The UI fires several
`settings.getProviderModels` calls for the same (host, model_type)
within a few hundred ms — page switches, useEffect re-runs, workspace
selection, auth-state flips. We collapse these into a single upstream
request via two layers:

1. Per-key Lock  — N concurrent calls for the same key → 1 network call.
2. Negative cache — transient errors (429/401/403) are short-cached so a
   UI re-render mid-storm does not pile more requests onto the rate-limited
   endpoint.

The cache key is ``(host, model_type)`` — intentionally excluding
``api_key``. OpenAI-compatible ``/v1/models`` returns the same catalog
regardless of credential, so keying on ``api_key`` would split the
cache across login states and force the very dedup we're trying to do.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from gui.ipc.w2p_handlers import settings_handler as sh
from gui.ipc.types import IPCRequest


def _req(method_id: str = "test-call"):
    return IPCRequest(id=method_id, type="request", method="settings.getProviderModels")


def _reset():
    sh._PROVIDER_MODELS_CACHE.clear()
    sh._PROVIDER_MODELS_ERROR_CACHE.clear()
    sh._PROVIDER_MODELS_LOCKS.clear()


def _params(model_type="llm", api_key="k", host="https://api.example.com/v1"):
    return {"host": host, "api_key": api_key, "model_type": model_type, "provider": "ecanai"}


def _ok_response(model_ids=("model-a",)):
    """Return a context-manager fake for a successful GET /v1/models."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"data": [{"id": mid} for mid in model_ids]})
    return resp


def _http_error_response(status_code=429, body=""):
    """Return a real requests.exceptions.HTTPError instance."""
    import requests as r
    err = r.HTTPError(f"{status_code} Client Error: Too Many Requests for url: x")
    err.response = MagicMock()
    err.response.status_code = status_code
    if body:
        err.response.content = body.encode()
    return err


# ---------- Layer 1: successful cache hit collapses repeat probes --------


def test_repeat_probes_within_ttl_hit_cache(monkeypatch):
    """Two calls within TTL → second reads cache, no second network call."""
    _reset()
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _ok_response()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    r1 = sh.handle_get_provider_models(_req("a"), _params())
    r2 = sh.handle_get_provider_models(_req("b"), _params())

    assert calls == ["https://api.example.com/v1/models"], (
        f"Expected one network call; got {calls}"
    )
    assert r1.get("status") == "success"
    assert r2.get("status") == "success"
    assert r1.get("result") == r2.get("result")


# ---------- Layer 2: per-key lock coalesces concurrent probes -------------


def test_concurrent_probes_for_same_key_collapse_to_one_network_call(monkeypatch):
    """N threads, same (host,key,type) → only 1 actually hits the network."""
    _reset()
    call_count = 0
    counter_lock = threading.Lock()
    barrier = threading.Barrier(8)

    def fake_get(url, headers=None, timeout=None):
        nonlocal call_count
        with counter_lock:
            call_count += 1
        # Hold long enough that every thread reaches the lock first.
        time.sleep(0.1)
        return _ok_response(("collided-model",))

    monkeypatch.setattr(sh.requests, "get", fake_get)

    results = []
    out_lock = threading.Lock()

    def worker():
        # All workers block here, then race for the lock simultaneously.
        barrier.wait()
        resp = sh.handle_get_provider_models(_req(), _params())
        with out_lock:
            results.append(resp)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count == 1, f"Expected singleflight to collapse to 1 call; got {call_count}"
    assert len(results) == 8
    assert all(r.get("status") == "success" for r in results)


# ---------- Layer 3: negative cache dampens a 429 storm -------------------


def test_transient_429_is_short_cached(monkeypatch):
    """After a 429, repeat calls within the error TTL return the cached error
    WITHOUT hitting the network — preventing the storm from amplifying."""
    _reset()
    import requests as r
    attempts = []

    def fake_get(url, headers=None, timeout=None):
        attempts.append(time.monotonic())
        raise _http_error_response(429, "EXCEED_RATELIMIT")

    monkeypatch.setattr(sh.requests, "get", fake_get)
    monkeypatch.setattr(sh.requests, "HTTPError", r.HTTPError)

    r1 = sh.handle_get_provider_models(_req("a"), _params())
    r2 = sh.handle_get_provider_models(_req("b"), _params())
    r3 = sh.handle_get_provider_models(_req("c"), _params())

    assert len(attempts) == 1, (
        f"429 must collapse via negative cache; got {len(attempts)} network calls"
    )
    for r_ in (r1, r2, r3):
        assert r_.get("status") == "error"
        assert r_.get("error", {}).get("code") == "PROVIDER_MODELS_ERROR"


def test_different_keys_do_not_collide(monkeypatch):
    """Different model_types → different cache keys → both must be probed."""
    _reset()
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _ok_response()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    sh.handle_get_provider_models(_req(), _params(model_type="llm"))
    sh.handle_get_provider_models(_req(), _params(model_type="embedding"))
    sh.handle_get_provider_models(_req(), _params(model_type="rerank"))

    assert len(calls) == 3
    # cache hit on a 4th call to one of them is fine — just no *extra* call
    sh.handle_get_provider_models(_req(), _params(model_type="llm"))
    assert len(calls) == 3


def test_lock_reused_per_key(monkeypatch):
    """Same (host, type) → same lock instance (singleflight guarantee)."""
    _reset()
    l1 = sh._get_provider_models_lock(("h", "llm"))
    l2 = sh._get_provider_models_lock(("h", "llm"))
    l3 = sh._get_provider_models_lock(("h", "embedding"))
    assert l1 is l2
    assert l1 is not l3


# ---------- Regression: auth-state flip must not double-hit the network ---


def test_auth_state_flip_shares_cache(monkeypatch):
    """Logging in mid-flight should NOT cause a second ``/v1/models``
    probe for the same (host, model_type). The catalog returned by an
    OpenAI-compatible endpoint is independent of credential, so the
    cache must coalesce empty-key and filled-key calls.
    """
    _reset()
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return _ok_response()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    # Pre-login probe (empty key).
    sh.handle_get_provider_models(_req("pre"), _params(api_key=""))
    # Post-login probe (real key) for the SAME (host, model_type).
    sh.handle_get_provider_models(_req("post"), _params(api_key="k-real"))

    assert len(calls) == 1, (
        f"Auth-state flip must share the cache; got {len(calls)} network calls: {calls}"
    )
    # The single outbound request should carry whatever key the first
    # call presented — the second call reads the cached body.
    assert calls[0][0] == "https://api.example.com/v1/models"
