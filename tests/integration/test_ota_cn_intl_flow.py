"""
Integration tests for OTA CN/INTL workflow.

Tests the complete flow from configuration to URL generation,
simulating the GitHub Actions build workflow.
"""

import os
import sys
import pytest

pytestmark = pytest.mark.integration


def _clear_ota_cache():
    """Remove cached OTA config modules to ensure fresh imports."""
    for _k in list(sys.modules.keys()):
        if _k == "ota" or _k.startswith("ota."):
            del sys.modules[_k]


class TestCNAppCompleteFlow:
    """Test complete CN app OTA flow."""
    
    def test_cn_build_env_vars(self, monkeypatch):
        """CN build should have correct environment variables."""
        # Simulate GitHub Actions CN build
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        monkeypatch.setenv("ECAN_APP_NAME", "eCan.cn")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Verify app detection
        assert config.is_cn_app() is True
        assert config.is_intl_app() is False
        
        # Verify storage backend
        assert config._is_cn is True
    
    def test_cn_appcast_url_format(self, monkeypatch):
        """CN app appcast URL should match expected COS format."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Test all platforms
        macos_url = config.get_appcast_url("macos", "amd64")
        windows_url = config.get_appcast_url("windows", "amd64")
        linux_url = config.get_appcast_url("linux", "amd64")
        
        # All should use COS
        for url in [macos_url, windows_url, linux_url]:
            assert "cos.ap-shanghai.myqcloud.com" in url
            assert "7363-sccb0-d0gc5398xf028be6a-1251680599" in url
            assert url.startswith("https://")
        
        # Platform-specific paths
        assert "macos" in macos_url
        assert "windows" in windows_url
        assert "linux" in linux_url
    
    def test_cn_release_artifact_path(self, monkeypatch):
        """CN release artifacts should use COS path structure."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Simulate release path
        version = "1.0.0"
        release_path = f"releases/v{version}/macos/amd64/eCan.cn-{version}-macos-amd64.pkg"
        
        # Full URL should be constructable
        full_url = config.get_cos_url(release_path)
        
        assert "7363-sccb0-d0gc5398xf028be6a-1251680599" in full_url
        assert f"v{version}" in full_url
        assert "macos" in full_url
        assert "amd64" in full_url


class TestINTLAppCompleteFlow:
    """Test complete INTL app OTA flow."""
    
    def test_intl_build_env_vars(self, monkeypatch):
        """INTL build should have correct environment variables."""
        # Simulate GitHub Actions INTL build
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        monkeypatch.setenv("ECAN_APP_NAME", "eCan")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Verify app detection
        assert config.is_intl_app() is True
        assert config.is_cn_app() is False
        
        # Verify storage backend
        assert config._is_cn is False
    
    def test_intl_appcast_url_format(self, monkeypatch):
        """INTL app appcast URL should match expected S3 format."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Test all platforms
        macos_url = config.get_appcast_url("macos", "aarch64")
        windows_url = config.get_appcast_url("windows", "amd64")
        linux_url = config.get_appcast_url("linux", "amd64")
        
        # All should use S3
        for url in [macos_url, windows_url, linux_url]:
            assert "s3.us-east-1.amazonaws.com" in url
            assert "ecan-releases" in url
            assert url.startswith("https://")
        
        # Platform-specific paths
        assert "macos" in macos_url
        assert "windows" in windows_url
        assert "linux" in linux_url
    
    def test_intl_release_artifact_path(self, monkeypatch):
        """INTL release artifacts should use S3 path structure."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Simulate release path
        version = "1.0.0"
        release_path = f"releases/v{version}/macos/aarch64/eCan-{version}-macos-aarch64.pkg"
        
        # Full URL should be constructable
        full_url = config.get_s3_url(release_path)
        
        assert "ecan-releases" in full_url
        assert f"v{version}" in full_url
        assert "macos" in full_url
        assert "aarch64" in full_url


class TestGitHubActionsWorkflowSimulation:
    """Simulate GitHub Actions workflow conditions."""
    
    def test_cn_workflow_upload_step(self, monkeypatch):
        """Simulate CN workflow upload step (shared-cos-upload.yml)."""
        # Environment as set by GitHub Actions
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        monkeypatch.setenv("ECAN_TENCENT_SECRET_ID", "mock-secret-id")
        monkeypatch.setenv("ECAN_TENCENT_SECRET_KEY", "mock-secret-key")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Should use COS
        assert config.is_cn_app() is True
        
        # Appcast generation should use COS URL
        appcast_url = config.get_appcast_url("macos", "amd64")
        assert "cos.ap-shanghai.myqcloud.com" in appcast_url
        assert "7363-sccb0-d0gc5398xf028be6a-1251680599" in appcast_url
    
    def test_intl_workflow_upload_step(self, monkeypatch):
        """Simulate INTL workflow upload step (shared-s3-upload.yml)."""
        # Environment as set by GitHub Actions
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock-access-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mock-secret-key")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Should use S3
        assert config.is_intl_app() is True
        
        # Appcast generation should use S3 URL
        appcast_url = config.get_appcast_url("macos", "amd64")
        assert "s3.us-east-1.amazonaws.com" in appcast_url
        assert "ecan-releases" in appcast_url
    
    def test_cn_appcast_generation_workflow(self, monkeypatch):
        """Simulate CN appcast generation workflow (shared-cos-appcast-generation.yml)."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Default environment is development
        # Appcast should be generated in COS
        appcast_url = config.get_appcast_url("macos", "amd64")
        
        # Verify URL structure - CN uses COS
        assert "cos.ap-shanghai.myqcloud.com" in appcast_url
        assert "7363-sccb0-d0gc5398xf028be6a-1251680599" in appcast_url
        # Development channel
        assert "dev" in appcast_url
        assert "channels" in appcast_url
    
    def test_intl_appcast_generation_workflow(self, monkeypatch):
        """Simulate INTL appcast generation workflow (shared-appcast-generation.yml)."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Default environment is development
        # Appcast should be generated in S3
        appcast_url = config.get_appcast_url("macos", "amd64")
        
        # Verify URL structure - INTL uses S3
        assert "s3.us-east-1.amazonaws.com" in appcast_url
        assert "ecan-releases" in appcast_url
        # Development channel
        assert "dev" in appcast_url
        assert "channels" in appcast_url


class TestEnvironmentMapping:
    """Test environment and channel mapping."""
    
    def test_development_environment(self, monkeypatch):
        """Development environment should have correct prefix."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # Default is development
        assert config.environment == "development"
        assert config.get_s3_prefix() == "dev"
    
    def test_cos_prefix_matches_environment(self, monkeypatch):
        """COS prefix should match environment configuration."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # In development environment, COS prefix should be "dev"
        url = config.get_cos_url("test/file.xml")
        assert "dev/" in url


class TestArchitectures:
    """Test architecture-specific URLs."""
    
    def test_macos_amd64(self, monkeypatch):
        """macOS amd64 architecture URL."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_appcast_url("macos", "amd64")
        assert "macos" in url
        assert "amd64" in url
    
    def test_macos_aarch64(self, monkeypatch):
        """macOS aarch64 (Apple Silicon) architecture URL."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_appcast_url("macos", "aarch64")
        assert "macos" in url
        assert "aarch64" in url
    
    def test_windows_amd64(self, monkeypatch):
        """Windows amd64 architecture URL."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_appcast_url("windows", "amd64")
        assert "windows" in url
        assert "amd64" in url
    
    def test_linux_amd64(self, monkeypatch):
        """Linux amd64 architecture URL."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_appcast_url("linux", "amd64")
        assert "linux" in url
        assert "amd64" in url


class TestLanguageSupport:
    """Test language-specific appcast URLs."""
    
    def test_zh_cn_language_cn(self, monkeypatch):
        """CN app with Chinese language."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        url = config.get_appcast_url("macos", "amd64", "zh-CN")
        assert "zh-CN" in url
        assert "cos.ap-shanghai.myqcloud.com" in url
    
    def test_en_us_language_intl(self, monkeypatch):
        """INTL app with English language (default, no suffix in URL)."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        # en-US is default, so no language suffix in URL
        url = config.get_appcast_url("macos", "amd64", "en-US")
        # URL should exist and use S3
        assert "s3.us-east-1.amazonaws.com" in url
        # Default language doesn't add suffix
        assert "appcast-macos-amd64.xml" in url
        assert "zh-CN" not in url


class TestFullConfigOutput:
    """Test full configuration output for debugging."""
    
    def test_cn_full_config_structure(self, monkeypatch):
        """CN app full config should have all required fields."""
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        full = config.get_full_config()
        
        # Required fields for CN
        assert 'app_id' in full
        assert full['app_id'] == 'cn'
        assert 'is_cn' in full
        assert full['is_cn'] is True
        assert 'storage_backend' in full
        assert full['storage_backend'] == 'cos'
        assert 'cos_bucket' in full
        assert full['cos_bucket'] == '7363-sccb0-d0gc5398xf028be6a-1251680599'
        assert 'ota_enabled' in full
    
    def test_intl_full_config_structure(self, monkeypatch):
        """INTL app full config should have all required fields."""
        monkeypatch.setenv("ECAN_APP_ID", "intl")
        _clear_ota_cache()
        from ota.config.loader import get_ota_config
        config = get_ota_config(reload=True)
        
        full = config.get_full_config()
        
        # Required fields for INTL
        assert 'app_id' in full
        assert full['app_id'] == 'intl'
        assert 'is_cn' in full
        assert full['is_cn'] is False
        assert 'storage_backend' in full
        assert full['storage_backend'] == 's3'
        assert 's3_bucket' in full
        assert full['s3_bucket'] == 'ecan-releases'
        assert 'ota_enabled' in full


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
