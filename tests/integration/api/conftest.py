"""Shared fixtures for integration API tests."""

import pytest
from tests.framework.mock_server import CloudAPIMockServer


@pytest.fixture
def cloud_mock():
    """Per-test CloudAPIMockServer with fresh empty storage."""
    mock = CloudAPIMockServer()
    yield mock
    mock.clear_storage()


@pytest.fixture
def auth_token():
    """A fake auth token for API calls."""
    return "test_token_abc123"
