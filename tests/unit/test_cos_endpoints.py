"""
Unit tests for ``utils/storage/cos_endpoints.py``.

Covers the single public helper ``accelerated_endpoint`` and the two
env-var kill switches. The helper is intentionally tiny: the only
job is to hand cos-python-sdk-v5 a base host string that the SDK
can prepend the bucket name to. See the module docstring for the
why.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_accel_env(monkeypatch):
    monkeypatch.delenv("ECAN_COS_ACCELERATE", raising=False)
    monkeypatch.delenv("ECAN_COS_USE_INTERNAL_ACCEL", raising=False)


class TestAcceleratedEndpoint:
    """``accelerated_endpoint`` returns the BASE host the SDK needs."""

    def test_default_returns_public_accel_base(self):
        from utils.storage.cos_endpoints import accelerated_endpoint
        # SDK endpoint is the BASE host — it does
        # f"{bucket}.{endpoint}" itself to build the per-request
        # hostname, so we deliberately do NOT include the bucket
        # prefix here. Putting the bucket in would produce
        # ``<bucket>.<bucket>.cos.accelerate.myqcloud.com`` at
        # request time and break TLS cert verification.
        assert accelerated_endpoint() == "cos.accelerate.myqcloud.com"

    def test_disabled_returns_empty_for_legacy_path(self):
        from utils.storage.cos_endpoints import accelerated_endpoint
        os.environ["ECAN_COS_ACCELERATE"] = "0"
        assert accelerated_endpoint() == ""

    def test_internal_accel_routes_through_tencent_private(self):
        from utils.storage.cos_endpoints import accelerated_endpoint
        os.environ["ECAN_COS_USE_INTERNAL_ACCEL"] = "1"
        assert accelerated_endpoint() == "cos-internal.accelerate.tencentcos.cn"

    def test_internal_takes_precedence_over_public(self):
        from utils.storage.cos_endpoints import accelerated_endpoint
        os.environ["ECAN_COS_USE_INTERNAL_ACCEL"] = "yes"
        assert accelerated_endpoint().endswith("tencentcos.cn")

    def test_truthy_accelerate_flag_variants(self):
        from utils.storage.cos_endpoints import accelerated_endpoint
        for value in ("1", "true", "yes", "on", "TRUE", "On"):
            os.environ["ECAN_COS_ACCELERATE"] = value
            assert accelerated_endpoint() == "cos.accelerate.myqcloud.com", (
                f"flag value {value!r} should enable acceleration"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])