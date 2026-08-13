"""
Tests for utils.app_config_loader.AppConfigLoader endpoint accessors.

These tests verify that ``AppConfigLoader`` resolves each named property
(``graphql_url``, ``storage_url``, ``get_storage_config()``, ...) to the
correct field value for the active app. They also pin the storage-critical
fields (``storage_region`` / ``storage_bucket`` / ``cdn``) and the new
``backend_*_bucket`` fields end-to-end, so a regression in either the JSON
file or the loader accessors surfaces here.
"""

import importlib
import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers: re-import the loader fresh between tests so we always start with
# an empty _instances cache.
# ---------------------------------------------------------------------------
@pytest.fixture
def loader_module(monkeypatch):
    """Yield utils.app_config_loader with a freshly-reset _instances dict."""
    import utils.app_config_loader as mod
    importlib.reload(mod)
    # _instances is a CLASS attribute (not module-level), so reload doesn't
    # blow it away automatically. Clear it explicitly via the class.
    mod.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
    yield mod
    mod.AppConfigLoader._instances = {}  # type: ignore[attr-defined]


def _loader(monkeypatch, app_id: str, mod):
    """Return a fresh AppConfigLoader pinned to ``app_id``.

    We monkeypatch ECAN_APP_ID before instantiating so the env-var-driven
    branch in ``__new__`` picks the right app.
    """
    monkeypatch.setenv("ECAN_APP_ID", app_id)
    # Clear class-level singleton cache for deterministic per-test isolation.
    mod.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
    return mod.AppConfigLoader(app_id=app_id)


# ===========================================================================
# graphql_url / websocket_url / auth_url / storage_url / update_url /
# privacy_policy_url / terms_url
#
# These map 1:1 to identically-named fields in cloud_endpoints.json.
# ===========================================================================
class TestSharedEndpointAccessors:
    """AppConfigLoader properties that mirror cloud_endpoints.json fields."""

    EXPECTED: dict[str, dict[str, str]] = {
        "graphql_url": {
            "intl": "https://api.ecan.ai/graphql",
            "cn": "https://api.fastprecisiontech.com/graphql",
        },
        "websocket_url": {
            "intl": "wss://ws.ecan.ai/graphql",
            "cn": "wss://ws.fastprecisiontech.com/graphql",
        },
        "auth_url": {
            "intl": "https://auth.ecan.ai",
            "cn": "https://auth.fastprecisiontech.com",
        },
        "storage_url": {
            # See apps/{intl,cn}/config/cloud_endpoints.json for the rationale.
            # Both URLs are virtual-hosted–style with the bucket embedded in
            # the hostname, matching how ota/config/loader.py and the AWS /
            # COS SDKs construct URLs for the rest of the codebase.
            "intl": "https://ecan-skills.s3.us-east-1.amazonaws.com",
            "cn": "https://ecan-skills-1251680599.cos.ap-shanghai.myqcloud.com",
        },
        "update_url": {
            "intl": "https://update.ecan.ai",
            "cn": "https://update.fastprecisiontech.com",
        },
        "privacy_policy_url": {
            "intl": "https://www.ecan.ai/privacy",
            "cn": "https://www.fastprecisiontech.com/privacy",
        },
        "terms_url": {
            "intl": "https://www.ecan.ai/terms",
            "cn": "https://www.fastprecisiontech.com/terms",
        },
    }

    @pytest.mark.parametrize("prop_name", list(EXPECTED.keys()))
    def test_intl_accessor_returns_intl_value(self, prop_name: str, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "intl", loader_module)
        actual = getattr(loader, prop_name)
        assert actual == self.EXPECTED[prop_name]["intl"], (
            f"AppConfigLoader('intl').{prop_name}: "
            f"expected {self.EXPECTED[prop_name]['intl']!r}, got {actual!r}"
        )

    @pytest.mark.parametrize("prop_name", list(EXPECTED.keys()))
    def test_cn_accessor_returns_cn_value(self, prop_name: str, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "cn", loader_module)
        actual = getattr(loader, prop_name)
        assert actual == self.EXPECTED[prop_name]["cn"], (
            f"AppConfigLoader('cn').{prop_name}: "
            f"expected {self.EXPECTED[prop_name]['cn']!r}, got {actual!r}"
        )


# ===========================================================================
# get_storage_config() — used by utils/storage/get_storage_provider() to
# build a Tencent COS or AWS S3 client. Region + bucket must match pinned
# values for the active app.
# ===========================================================================
class TestGetStorageConfig:
    EXPECTED: dict[str, dict[str, str]] = {
        "intl": {
            "provider": "aws",
            "region": "us-east-1",
            "bucket": "ecan-skills",
            "endpoint": "https://ecan-skills.s3.us-east-1.amazonaws.com",
        },
        "cn": {
            "provider": "tencent",
            "region": "ap-shanghai",
            "bucket": "ecan-skills-1251680599",
            "endpoint": "https://ecan-skills-1251680599.cos.ap-shanghai.myqcloud.com",
        },
    }

    def test_intl_storage_config(self, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "intl", loader_module)
        cfg = loader.get_storage_config()
        for key, expected in self.EXPECTED["intl"].items():
            assert cfg[key] == expected, (
                f"intl get_storage_config()[{key!r}]: "
                f"expected {expected!r}, got {cfg[key]!r}"
            )

    def test_cn_storage_config(self, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "cn", loader_module)
        cfg = loader.get_storage_config()
        for key, expected in self.EXPECTED["cn"].items():
            assert cfg[key] == expected, (
                f"cn get_storage_config()[{key!r}]: "
                f"expected {expected!r}, got {cfg[key]!r}"
            )

    def test_cn_storage_provider_is_tencent(self, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "cn", loader_module)
        cfg = loader.get_storage_config()
        assert cfg["provider"] == "tencent", (
            f"cn storage provider={cfg['provider']!r}, expected 'tencent'"
        )

    def test_intl_storage_provider_is_aws(self, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "intl", loader_module)
        cfg = loader.get_storage_config()
        assert cfg["provider"] == "aws", (
            f"intl storage provider={cfg['provider']!r}, expected 'aws'"
        )


# ===========================================================================
# is_cn / is_intl 派发
# ===========================================================================
class TestIdentityDispatch:
    def test_is_cn_true_for_cn_app(self, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "cn", loader_module)
        assert loader.is_cn() is True
        assert loader.is_intl() is False

    def test_is_intl_true_for_intl_app(self, monkeypatch, loader_module):
        loader = _loader(monkeypatch, "intl", loader_module)
        assert loader.is_intl() is True
        assert loader.is_cn() is False

    def test_loader_resolves_app_from_env_var(self, monkeypatch, loader_module):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        loader_module.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
        loader = loader_module.AppConfigLoader()  # no app_id arg
        assert loader.app_id == "cn", (
            f"AppConfigLoader() did not pick ECAN_APP_ID=cn "
            f"(got {loader.app_id!r})"
        )

    def test_default_app_id_is_intl(self, monkeypatch, loader_module):
        monkeypatch.delenv("ECAN_APP_ID", raising=False)
        loader_module.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
        loader = loader_module.AppConfigLoader()
        assert loader.app_id == "intl"


# ===========================================================================
# 直接读 _endpoints["key"]: utils/storage/aws_s3.py 和
# utils/storage/tencent_cos.py 都直接用 [] 取 storage_region /
# storage_bucket / cdn. 把这两个字段经 loader 而非通过 storage provider
# 直接 verify 一遍。
# ===========================================================================
class TestRawEndpointAccess:
    EXPECTED_STORAGE: dict[str, dict[str, str]] = {
        "intl": {"storage_region": "us-east-1", "storage_bucket": "ecan-skills"},
        "cn": {"storage_region": "ap-shanghai", "storage_bucket": "ecan-skills-1251680599"},
    }

    EXPECTED_BACKEND_BUCKETS: dict[str, dict[str, str]] = {
        "intl": {
            "backend_avatar_bucket": "ecan-avatars",
            "backend_skill_bucket": "ecan-skills",
            "backend_log_bucket": "",
            "backend_rag_bucket": "ecan-rags",
        },
        "cn": {
            "backend_avatar_bucket": "ecan-avatars-1251680599",
            "backend_skill_bucket": "ecan-skills-1251680599",
            "backend_log_bucket": "",
            "backend_rag_bucket": "ecan-rags-1251680599",
        },
    }

    @pytest.mark.parametrize("field", ["storage_region", "storage_bucket"])
    def test_storage_field_per_app(self, field: str, monkeypatch, loader_module):
        for app_id in ("intl", "cn"):
            loader = _loader(monkeypatch, app_id, loader_module)
            actual = loader._endpoints[field]
            assert actual == self.EXPECTED_STORAGE[app_id][field], (
                f"AppConfigLoader('{app_id}')._endpoints[{field!r}]: "
                f"expected {self.EXPECTED_STORAGE[app_id][field]!r}, "
                f"got {actual!r}"
            )

    @pytest.mark.parametrize(
        "field", ["backend_avatar_bucket", "backend_skill_bucket",
                  "backend_log_bucket", "backend_rag_bucket"]
    )
    def test_backend_bucket_field_per_app(self, field: str, monkeypatch, loader_module):
        for app_id in ("intl", "cn"):
            loader = _loader(monkeypatch, app_id, loader_module)
            actual = loader._endpoints[field]
            assert actual == self.EXPECTED_BACKEND_BUCKETS[app_id][field], (
                f"AppConfigLoader('{app_id}')._endpoints[{field!r}]: "
                f"expected {self.EXPECTED_BACKEND_BUCKETS[app_id][field]!r}, "
                f"got {actual!r}"
            )

    def test_cdn_field_per_app(self, monkeypatch, loader_module):
        # Intl cdn is set (cdn.ecan.ai) and must be HTTPS.
        # CN has no documented CDN — we expect an empty string so callers
        # know to treat the CDN as unconfigured rather than guessing.
        intl_loader = _loader(monkeypatch, "intl", loader_module)
        cn_loader = _loader(monkeypatch, "cn", loader_module)
        intl_cdn = intl_loader._endpoints.get("cdn", "")
        cn_cdn = cn_loader._endpoints.get("cdn", "")
        assert intl_cdn == "https://cdn.ecan.ai", (
            f"intl cdn={intl_cdn!r} (expected https://cdn.ecan.ai)"
        )
        assert intl_cdn.startswith("https://"), (
            f"intl cdn={intl_cdn!r} is not an https URL"
        )
        assert cn_cdn == "", (
            f"cn cdn={cn_cdn!r} (expected empty string — no CN CDN "
            "documented in the repo)"
        )


# ===========================================================================
# 缓存语义：同一 app_id 返回同一实例（_instances 单例）。
# AppConfigLoader 故意不让 app 切换时拿到旧的实例。这里用 reload 隔离。
# ===========================================================================
class TestCachingSemantics:
    def test_same_app_id_returns_cached_instance(self, monkeypatch, loader_module):
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        loader_module.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
        a = loader_module.AppConfigLoader(app_id="intl")
        b = loader_module.AppConfigLoader(app_id="intl")
        assert a is b, "AppConfigLoader should cache the per-app singleton"

    def test_different_app_ids_return_different_instances(
        self, monkeypatch, loader_module
    ):
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        loader_module.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
        intl = loader_module.AppConfigLoader(app_id="intl")
        cn = loader_module.AppConfigLoader(app_id="cn")
        assert intl is not cn, (
            "cn and intl AppConfigLoaders collapsed to the same instance "
            "— config leak would result"
        )
        assert intl.app_id == "intl"
        assert cn.app_id == "cn"


# ===========================================================================
# Storage provider resolution: utils.storage.get_storage_provider() must
# return the right provider class for the active app. We exercise the
# dispatch through the loader rather than via the env-var-driven
# S3StorageConfig.from_default().
# ===========================================================================
class TestStorageProviderDispatch:
    def test_intl_storage_provider_is_aws(self, monkeypatch, loader_module):
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        loader_module.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
        # Reload utils.storage too so it sees the freshly-built _instances.
        import utils.storage as storage_mod
        importlib.reload(storage_mod)
        provider = storage_mod.get_storage_provider()
        from utils.storage.aws_s3 import AWSS3Provider
        assert isinstance(provider, AWSS3Provider), (
            f"intl dispatch returned {type(provider).__name__}, "
            "expected AWSS3Provider"
        )

    def test_cn_storage_provider_is_tencent(self, monkeypatch, loader_module):
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        loader_module.AppConfigLoader._instances = {}  # type: ignore[attr-defined]
        import utils.storage as storage_mod
        importlib.reload(storage_mod)
        provider = storage_mod.get_storage_provider()
        from utils.storage.tencent_cos import TencentCOSProvider
        assert isinstance(provider, TencentCOSProvider), (
            f"cn dispatch returned {type(provider).__name__}, "
            "expected TencentCOSProvider"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
