"""
Pins the cache-lag retry wrapper around synchronous startup API calls.

Background: when a fresh JWT lands, CloudBase's SCF gateway takes 30-60s
to propagate the new token through its auth cache. The supervisor
suppresses ``on_session_expired`` during that grace window, and
OfflineSyncManager backs the offline queue off — but synchronous startup
calls (``queryAgents`` for the agent list, ``reqAccountInfo`` for the
account page) don't go through either path. Without help, the user would
briefly see an empty agent list and an "account info unavailable"
warning right after login.

The wrapper ``_appsync_http_request_with_fresh_token_backoff`` is a thin
retry loop over ``appsync_http_request`` that detects
"401 + supervisor.fresh" and retries with a short sleep.
"""

import importlib
import time
import unittest.mock as mock

import pytest


def _import_cloud_api():
    return importlib.import_module("agent.cloud_api.cloud_api")


def _make_supervisor(installed_at: float):
    sup = mock.MagicMock()
    sup.is_fresh_token_rejection.return_value = (
        installed_at > 0 and (time.time() - installed_at) < 60
    )
    return sup


def test_wrapper_does_not_retry_on_success(monkeypatch):
    """Happy path: success on first attempt → no sleep, no retry."""
    cloud = _import_cloud_api()

    ok_response = {"data": {"queryAgents": [{"id": "a"}]}}
    appsync = mock.MagicMock(return_value=ok_response)
    sleep = mock.MagicMock()
    monkeypatch.setattr(cloud, "appsync_http_request", appsync)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: _make_supervisor(time.time()),
    )

    result = cloud._appsync_http_request_with_fresh_token_backoff(
        "query", mock.MagicMock(), "tok", "https://x",
    )

    appsync.assert_called_once()
    sleep.assert_not_called()
    assert result is ok_response


def test_wrapper_retries_on_fresh_token_401(monkeypatch):
    """A 401 inside the supervisor's fresh-token grace window must retry.

    The retry must succeed when the cache catches up (subsequent call
    returns ok). Sleep is called between attempts.
    """
    cloud = _import_cloud_api()

    err_401 = {"errors": [{"message": "Invalid or expired access token",
                            "extensions": {"code": "UNAUTHENTICATED"}}]}
    ok_response = {"data": {"queryAgents": [{"id": "a"}]}}

    # First two attempts: 401. Third attempt: success.
    appsync = mock.MagicMock(side_effect=[err_401, err_401, ok_response])
    sleep = mock.MagicMock()
    monkeypatch.setattr(cloud, "appsync_http_request", appsync)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: _make_supervisor(time.time()),
    )

    result = cloud._appsync_http_request_with_fresh_token_backoff(
        "query", mock.MagicMock(), "tok", "https://x",
        max_attempts=3, sleep_seconds=5.0,
    )

    assert appsync.call_count == 3
    assert sleep.call_count == 2
    assert sleep.call_args.args == (5.0,)
    assert result is ok_response


def test_wrapper_does_not_retry_on_stale_token_401(monkeypatch):
    """A 401 with an OLD token (past grace) must NOT retry — that is a
    real auth failure, retrying just delays surfacing the error to the
    caller."""
    cloud = _import_cloud_api()

    err_401 = {"errors": [{"message": "Invalid or expired access token",
                            "extensions": {"code": "UNAUTHENTICATED"}}]}
    appsync = mock.MagicMock(return_value=err_401)
    sleep = mock.MagicMock()
    monkeypatch.setattr(cloud, "appsync_http_request", appsync)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    # Token installed 5 minutes ago — well past the 60s grace.
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: _make_supervisor(time.time() - 300),
    )

    result = cloud._appsync_http_request_with_fresh_token_backoff(
        "query", mock.MagicMock(), "tok", "https://x",
    )

    appsync.assert_called_once(), (
        "stale-token 401 must not be retried — it's a real auth failure"
    )
    sleep.assert_not_called()
    assert result is err_401


def test_wrapper_returns_last_401_when_retries_exhausted(monkeypatch):
    """If the cache really hasn't caught up after max_attempts, the last
    401 falls through unchanged so the caller can surface an honest
    error."""
    cloud = _import_cloud_api()

    err_401 = {"errors": [{"message": "Invalid or expired access token",
                            "extensions": {"code": "UNAUTHENTICATED"}}]}
    appsync = mock.MagicMock(return_value=err_401)
    sleep = mock.MagicMock()
    monkeypatch.setattr(cloud, "appsync_http_request", appsync)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: _make_supervisor(time.time()),
    )

    result = cloud._appsync_http_request_with_fresh_token_backoff(
        "query", mock.MagicMock(), "tok", "https://x",
        max_attempts=3, sleep_seconds=5.0,
    )

    assert appsync.call_count == 3
    assert sleep.call_count == 2
    assert result is err_401


def test_wrapper_does_not_retry_on_non_401_error(monkeypatch):
    """Only UNAUTHENTICATED errors trigger backoff. A schema error
    (GRAPHQL_VALIDATION_FAILED, resolver null) must fall through on the
    first attempt."""
    cloud = _import_cloud_api()

    schema_err = {"errors": [{"message": "Cannot return null for non-nullable field",
                              "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}]}
    appsync = mock.MagicMock(return_value=schema_err)
    sleep = mock.MagicMock()
    monkeypatch.setattr(cloud, "appsync_http_request", appsync)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: _make_supervisor(time.time()),
    )

    result = cloud._appsync_http_request_with_fresh_token_backoff(
        "query", mock.MagicMock(), "tok", "https://x",
    )

    appsync.assert_called_once()
    sleep.assert_not_called()
    assert result is schema_err


def test_wrapper_without_supervisor_does_not_retry(monkeypatch):
    """Web mode / tests without a supervisor wired must keep the old
    behavior — single attempt, fail fast."""
    cloud = _import_cloud_api()

    err_401 = {"errors": [{"message": "Invalid or expired access token",
                            "extensions": {"code": "UNAUTHENTICATED"}}]}
    appsync = mock.MagicMock(return_value=err_401)
    sleep = mock.MagicMock()
    monkeypatch.setattr(cloud, "appsync_http_request", appsync)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: None,
    )

    result = cloud._appsync_http_request_with_fresh_token_backoff(
        "query", mock.MagicMock(), "tok", "https://x",
    )

    appsync.assert_called_once()
    sleep.assert_not_called()


def test_send_get_agents_uses_wrapper(monkeypatch):
    """send_get_agents_request_to_cloud must use the wrapper, not the
    raw appsync_http_request."""
    cloud = _import_cloud_api()

    ok = {"data": {"queryAgents": []}}
    wrapper = mock.MagicMock(return_value=ok)
    monkeypatch.setattr(cloud, "_appsync_http_request_with_fresh_token_backoff", wrapper)

    session = mock.MagicMock()
    result = cloud.send_get_agents_request_to_cloud(session, "tok", "https://x")

    wrapper.assert_called_once()
    # operation_name must be queryAgents so the retry log is searchable.
    assert wrapper.call_args.kwargs.get("operation_name") == "queryAgents"
    assert result == []


def test_send_account_info_uses_wrapper(monkeypatch):
    """send_account_info_request_to_cloud must use the wrapper."""
    cloud = _import_cloud_api()

    ok = {"data": {"reqAccountInfo": '{"balance": 0}'}}
    wrapper = mock.MagicMock(return_value=ok)
    monkeypatch.setattr(cloud, "_appsync_http_request_with_fresh_token_backoff", wrapper)

    session = mock.MagicMock()
    result = cloud.send_account_info_request_to_cloud(
        session, [{"actid": 0, "op": "{}", "options": "{}"}],
        "tok", "https://x",
    )

    wrapper.assert_called_once()
    assert wrapper.call_args.kwargs.get("operation_name") == "reqAccountInfo"
    assert result == {"balance": 0}