"""
Unit tests for OTA Configuration Loader.

Tests CN/INTL separation, storage URL generation, and appcast URL routing.
"""

import os
import sys
import pytest

pytestmark = pytest.mark.unit


def _clear_ota_cache():
    """Remove cached OTA config modules to ensure fresh imports."""
    for _k in list(sys.modules.keys()):
        if _k == "ota" or _k.startswith("ota."):
            del sys.modules[_k]


def _reload_ota_config():
    """Force reload OTA config with fresh environment."""
    _clear_ota_cache()
    from ota.config import loader
    # Force recreate global instance
    loader._ota_config = None
    return loader.get_ota_config(reload=True)


class TestOTAConfigCNDetection:
    """Tests for CN/INTL app detection."""
    
    def test_cn_app_detected_when_env_set(self, monkeypatch):
        """When ECAN_APP_ID=cn, is_cn_app() returns True."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        assert config.is_cn_app() is True
        assert config.is_intl_app() is False
        assert config._app_id == "cn"
    
    def test_intl_app_detected_when_env_set(self, monkeypatch):
        """When ECAN_APP_ID=intl, is_intl_app() returns True."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        assert config.is_intl_app() is True
        assert config.is_cn_app() is False
        assert config._app_id == "intl"
    
    def test_default_is_intl_when_not_set(self, monkeypatch):
        """When ECAN_APP_ID not set, defaults to INTL."""
        monkeypatch.delenv("ECAN_APP_ID", raising=False)
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        assert config.is_intl_app() is True
        assert config.is_cn_app() is False
    
    def test_app_id_stored_in_config(self, monkeypatch):
        """App ID is stored in full config."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        full_config = config.get_full_config()
        assert full_config['app_id'] == "cn"
        assert full_config['is_cn'] is True
        assert full_config['storage_backend'] == "cos"


class TestOTAConfigStorageURLs:
    """Tests for storage URL generation methods."""
    
    def test_cos_url_generated_for_cn_app(self, monkeypatch):
        """CN app generates COS URLs."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_cos_url("channels/stable/appcast-macos-amd64.xml")
        
        assert "ecan-releases-1251680599" in url
        assert "cos.ap-shanghai.myqcloud.com" in url
        assert "channels/stable/appcast-macos-amd64.xml" in url
    
    def test_s3_url_generated_for_intl_app(self, monkeypatch):
        """INTL app generates S3 URLs."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_s3_url("channels/stable/appcast-macos-amd64.xml")
        
        assert "ecan-releases" in url
        assert "s3.us-east-1.amazonaws.com" in url
        assert "channels/stable/appcast-macos-amd64.xml" in url
    
    def test_storage_url_auto_selects_cos_for_cn(self, monkeypatch):
        """get_storage_url() selects COS for CN app."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_storage_url("test/path/file.xml")
        
        assert "cos.ap-shanghai.myqcloud.com" in url
        assert "ecan-releases-1251680599" in url
    
    def test_storage_url_auto_selects_s3_for_intl(self, monkeypatch):
        """get_storage_url() selects S3 for INTL app."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_storage_url("test/path/file.xml")
        
        assert "s3.us-east-1.amazonaws.com" in url
        assert "ecan-releases" in url


class TestOTAConfigAppcastURL:
    """Tests for appcast URL generation.

    NOTE: These assertions all target the public S3/COS bucket path.
    That path is only reached when ``environment`` is NOT
    ``development`` (in dev the local OTA test server
    ``http://127.0.0.1:8080`` takes over — see
    ``tests/unit/test_local_ota_routing.py`` for the dev-environment
    coverage). Each test below therefore pins ``environment`` to
    ``production`` before asserting.
    """

    def _switch_to_production(self, config):
        # The OTAConfig exposes ``environment`` as a getter over the
        # top-level ``environment`` key in the loaded YAML; mutating
        # that key is the documented test seam (see
        # ``TestOTAConfigEnvironments`` elsewhere in this file).
        config._config["environment"] = "production"

    def test_cn_app_uses_cos_for_appcast(self, monkeypatch):
        """CN app generates appcast URLs pointing to COS."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        self._switch_to_production(config)

        url = config.get_appcast_url("macos", "amd64")

        assert "ecan-releases-1251680599" in url
        assert "cos.ap-shanghai.myqcloud.com" in url
        assert "macos" in url
        assert "amd64" in url

    def test_intl_app_uses_s3_for_appcast(self, monkeypatch):
        """INTL app generates appcast URLs pointing to S3."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        self._switch_to_production(config)

        url = config.get_appcast_url("macos", "amd64")

        assert "ecan-releases" in url
        assert "s3.us-east-1.amazonaws.com" in url
        assert "macos" in url
        assert "amd64" in url

    def test_appcast_url_with_language_cn(self, monkeypatch):
        """CN app generates localized appcast URLs."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        self._switch_to_production(config)

        url = config.get_appcast_url("macos", "aarch64", "zh-CN")

        assert "ecan-releases-1251680599" in url
        assert "cos.ap-shanghai.myqcloud.com" in url
        assert "zh-CN" in url

    def test_appcast_url_with_language_intl(self, monkeypatch):
        """INTL app generates localized appcast URLs."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        self._switch_to_production(config)

        url = config.get_appcast_url("windows", "amd64", "en-US")

        assert "ecan-releases" in url
        assert "s3.us-east-1.amazonaws.com" in url
    
    def test_appcast_url_windows_platform(self, monkeypatch):
        """Appcast URL includes windows platform (test env, INTL)."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)

        url = config.get_appcast_url("windows", "amd64")

        assert "windows" in url
        assert "amd64" in url
        assert "channels/beta/appcast-windows-amd64.xml" in url

    def test_appcast_url_linux_platform(self, monkeypatch):
        """Appcast URL includes linux platform (test env, INTL)."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)

        url = config.get_appcast_url("linux", "amd64")

        assert "linux" in url
        assert "amd64" in url
        assert "channels/beta/appcast-linux-amd64.xml" in url
    
    def test_appcast_url_channel_included(self, monkeypatch):
        """Appcast URL includes channel path (public-bucket path)."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        # Active env is ``test`` (see ota_config.yaml) which already
        # routes through the public-bucket path. Pin to ``production``
        # so the test stays scoped to the channels/.../ stable channel.
        config._config["environment"] = "production"

        url = config.get_appcast_url("macos", "amd64")

        # Should include channels/{channel}/ in path
        assert "channels/" in url
        assert "appcast-macos-amd64.xml" in url


class TestOTAConfigEnvironments:
    """Tests for environment-specific configuration."""
    
    def test_default_environment_is_test(self, monkeypatch):
        """Default environment is ``test`` so dev clients point at the
        remote TEST bucket for end-to-end OTA validation."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)

        assert config.environment == "test"

        full_config = config.get_full_config()
        assert full_config['environment'] == "test"
    
    def test_full_config_includes_storage_info(self, monkeypatch):
        """get_full_config() includes storage backend info."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        full = config.get_full_config()
        
        assert 'storage_backend' in full
        assert 'cos_bucket' in full
        assert 's3_bucket' in full
        assert 'is_cn' in full
        assert 'app_id' in full


class TestOTAConfigEdgeCases:
    """Edge case tests."""
    
    def test_disabled_ota_returns_empty_url(self, monkeypatch):
        """When OTA is disabled, URLs return empty string."""
        # Create a minimal config with OTA disabled
        import tempfile
        import yaml
        from pathlib import Path
        
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({'ota_enabled': False, 'environment': 'production'}, f)
            temp_config = f.name
        
        try:
            _clear_ota_cache()
            from ota.config.loader import get_ota_config
            config = get_ota_config(temp_config, reload=True)
            
            assert config.get_appcast_url("macos", "amd64") == ""
            assert config.get_storage_url("test") == ""
            assert config.get_cos_url("test") == ""
            assert config.get_s3_url("test") == ""
        finally:
            Path(temp_config).unlink(missing_ok=True)
    
    def test_cos_url_without_leading_slash(self, monkeypatch):
        """COS URL handles paths without leading slash."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_cos_url("releases/v1.0.0/file.pkg")
        
        # Should not have double slashes
        assert "myqcloud.com//" not in url
        assert url.startswith("https://")
    
    def test_s3_url_without_double_slashes(self, monkeypatch):
        """S3 URL handles paths without double slashes."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_s3_url("releases/v1.0.0/file.pkg")
        
        # Should not have double slashes in path
        assert "amazonaws.com//" not in url
        assert url.startswith("https://")


class TestOTAConfigRepr:
    """Tests for string representation."""
    
    def test_repr_includes_app_type(self, monkeypatch):
        """String repr includes app type information."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        repr_str = repr(config)
        
        assert "cn" in repr_str.lower() or "cos" in repr_str.lower()
    
    def test_repr_for_intl(self, monkeypatch):
        """INTL repr includes appropriate info."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        repr_str = repr(config)
        
        assert "intl" in repr_str.lower() or "s3" in repr_str.lower() or "ecan" in repr_str.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
