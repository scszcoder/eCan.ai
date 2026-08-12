"""
Tests for utils.storage providers — focused on the no-fallback contract.

These tests guard the deliberate behaviour change introduced for the
``apps/{cn,intl}/config/cloud_endpoints.json`` refactor: every storage
provider MUST surface a misconfigured ``storage_region`` / ``storage_bucket``
as a hard ``RuntimeError`` rather than silently defaulting to a hardcoded
value. That makes production bugs loud instead of silent.
"""

import sys
import pytest

pytestmark = pytest.mark.unit


class _EndpointShim:
    """Minimal stand-in for AppConfigLoader used by the storage providers.

    It supports both ``config._endpoints[k]`` (no fallback) and
    ``config._endpoints.get(k, default)`` so we can drive either access
    pattern from the test. Exposes ``app_id`` so error messages can name
    the active app, mirroring AppConfigLoader.
    """

    def __init__(self, d: dict, app_id: str = "test-app"):
        self._d = dict(d)
        self.app_id = app_id

    @property
    def _endpoints(self):
        return self

    def get(self, k, default=None):
        return self._d.get(k, default)

    def __getitem__(self, k):
        return self._d[k]

    def __contains__(self, k):
        return k in self._d


class TestAWSS3ProviderNoFallback:
    """AWSS3Provider must fail loudly when storage_region / storage_bucket is missing."""

    def _make(self, **fields):
        return _EndpointShim(fields)

    def test_missing_storage_region_raises(self):
        from utils.storage.aws_s3 import AWSS3Provider
        cfg = self._make(storage_bucket="ecan-skills")
        with pytest.raises(RuntimeError, match="storage_region"):
            AWSS3Provider(cfg)

    def test_missing_storage_bucket_raises(self):
        from utils.storage.aws_s3 import AWSS3Provider
        cfg = self._make(storage_region="us-east-1")
        with pytest.raises(RuntimeError, match="storage_bucket"):
            AWSS3Provider(cfg)

    def test_empty_dict_raises(self):
        from utils.storage.aws_s3 import AWSS3Provider
        with pytest.raises(RuntimeError):
            AWSS3Provider(self._make())

    def test_both_present_succeeds(self):
        from utils.storage.aws_s3 import AWSS3Provider
        cfg = self._make(storage_region="us-east-1", storage_bucket="ecan-skills", cdn="")
        provider = AWSS3Provider(cfg)
        assert provider.region == "us-east-1"
        assert provider.bucket == "ecan-skills"
        assert provider.cdn_domain == ""


class TestTencentCOSProviderNoFallback:
    """TencentCOSProvider must fail loudly when storage_region / storage_bucket is missing."""

    def _make(self, **fields):
        return _EndpointShim(fields)

    def test_missing_storage_region_raises(self):
        from utils.storage.tencent_cos import TencentCOSProvider
        cfg = self._make(storage_bucket="ecan-skills-1251680599")
        with pytest.raises(RuntimeError, match="storage_region"):
            TencentCOSProvider(cfg)

    def test_missing_storage_bucket_raises(self):
        from utils.storage.tencent_cos import TencentCOSProvider
        cfg = self._make(storage_region="ap-shanghai")
        with pytest.raises(RuntimeError, match="storage_bucket"):
            TencentCOSProvider(cfg)

    def test_empty_dict_raises(self):
        from utils.storage.tencent_cos import TencentCOSProvider
        with pytest.raises(RuntimeError):
            TencentCOSProvider(self._make())

    def test_both_present_succeeds(self):
        from utils.storage.tencent_cos import TencentCOSProvider
        cfg = self._make(
            storage_region="ap-shanghai",
            storage_bucket="ecan-skills-1251680599",
            cdn="",  # CN has no documented CDN; see cloud_endpoints.json
        )
        provider = TencentCOSProvider(cfg)
        assert provider.region == "ap-shanghai"
        assert provider.bucket == "ecan-skills-1251680599"
        assert provider.cdn_domain == ""


class TestCloudEndpointsRequiredFields:
    """Both apps' cloud_endpoints.json must declare the new backend_* bucket fields."""

    REQUIRED_FIELDS = (
        "storage_region",
        "storage_bucket",
        "backend_avatar_bucket",
        "backend_skill_bucket",
        "backend_log_bucket",
        "backend_rag_bucket",
    )

    def test_intl_endpoints_declares_all_required_fields(self):
        from pathlib import Path
        import json
        data = json.loads(
            Path("apps/intl/config/cloud_endpoints.json").read_text(encoding="utf-8")
        )
        missing = [k for k in self.REQUIRED_FIELDS if k not in data]
        assert not missing, f"intl cloud_endpoints.json missing fields: {missing}"

    def test_cn_endpoints_declares_all_required_fields(self):
        from pathlib import Path
        import json
        data = json.loads(
            Path("apps/cn/config/cloud_endpoints.json").read_text(encoding="utf-8")
        )
        missing = [k for k in self.REQUIRED_FIELDS if k not in data]
        assert not missing, f"cn cloud_endpoints.json missing fields: {missing}"

    def test_intl_avatar_bucket_matches_aws_intent(self):
        from pathlib import Path
        import json
        data = json.loads(
            Path("apps/intl/config/cloud_endpoints.json").read_text(encoding="utf-8")
        )
        # The avatar bucket should NOT be the legacy 'ecan-intl-files' mistake
        # and should NOT collide with the runtime 'ecan-skills' bucket.
        assert data["backend_avatar_bucket"] != data["storage_bucket"]
        assert data["backend_avatar_bucket"] == "ecan-avatars"

    def test_cn_buckets_with_appid_suffix(self):
        """COS bucket names that ARE configured must end with the APPID so
        they are globally unique. backend_log_bucket is allowed to be empty
        (the log bucket is unprovisioned in this repo — see apps/cn/config/
        cloud_endpoints.json).
        """
        from pathlib import Path
        import json
        data = json.loads(
            Path("apps/cn/config/cloud_endpoints.json").read_text(encoding="utf-8")
        )
        for field in (
            "backend_avatar_bucket",
            "backend_skill_bucket",
            "backend_rag_bucket",
        ):
            assert data[field].endswith("-1251680599"), (
                f"CN bucket {field}={data[field]!r} must end with -1251680599"
            )
        # log bucket may be empty (unprovisioned). If it is configured, it
        # must follow the same APPID suffix rule.
        log_bucket = data["backend_log_bucket"]
        if log_bucket:
            assert log_bucket.endswith("-1251680599"), (
                f"CN bucket backend_log_bucket={log_bucket!r} must end "
                "with -1251680599 if it is configured"
            )


class TestS3StorageConfigFromDefault:
    """S3StorageConfig.from_default() must read bucket names from _endpoints
    and refuse to fall back to a hardcoded value."""

    def test_from_default_avatar_uses_app_endpoints(self):
        from agent.cloud.s3_storage_service import S3StorageConfig
        cfg = _EndpointShim(
            {
                "storage_region": "us-east-1",
                "backend_avatar_bucket": "ecan-avatars",
            }
        )
        config = S3StorageConfig.from_default(resource_type="avatar", app_config=cfg)
        assert config.bucket == "ecan-avatars"
        assert config.region == "us-east-1"

    def test_from_default_skill_uses_app_endpoints(self):
        from agent.cloud.s3_storage_service import S3StorageConfig
        cfg = _EndpointShim(
            {
                "storage_region": "us-east-1",
                "backend_skill_bucket": "ecan-skills",
            }
        )
        config = S3StorageConfig.from_default(resource_type="skill", app_config=cfg)
        assert config.bucket == "ecan-skills"
        assert config.region == "us-east-1"

    def test_from_default_avatar_missing_bucket_raises(self):
        from agent.cloud.s3_storage_service import S3StorageConfig
        cfg = _EndpointShim({"storage_region": "us-east-1"})  # no bucket field
        with pytest.raises(RuntimeError, match="backend_avatar_bucket"):
            S3StorageConfig.from_default(resource_type="avatar", app_config=cfg)

    def test_from_default_skill_missing_bucket_raises(self):
        from agent.cloud.s3_storage_service import S3StorageConfig
        cfg = _EndpointShim({"storage_region": "us-east-1"})
        with pytest.raises(RuntimeError, match="backend_skill_bucket"):
            S3StorageConfig.from_default(resource_type="skill", app_config=cfg)

    def test_from_default_unknown_resource_type_raises(self):
        from agent.cloud.s3_storage_service import S3StorageConfig
        cfg = _EndpointShim({"storage_region": "us-east-1"})
        with pytest.raises(ValueError, match="Unknown resource_type"):
            S3StorageConfig.from_default(resource_type="document", app_config=cfg)

    def test_from_default_empty_bucket_value_raises(self):
        from agent.cloud.s3_storage_service import S3StorageConfig
        cfg = _EndpointShim(
            {
                "storage_region": "us-east-1",
                "backend_avatar_bucket": "",  # explicitly empty
            }
        )
        with pytest.raises(RuntimeError, match="empty"):
            S3StorageConfig.from_default(resource_type="avatar", app_config=cfg)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
