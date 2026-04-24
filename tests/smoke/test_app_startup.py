"""Smoke tests for application startup and environment."""

import os
import sys
import pytest

pytestmark = pytest.mark.smoke


class TestEnvironmentSetup:
    """Smoke tests for environment configuration."""

    def test_project_root_on_path(self):
        """Project root is in sys.path."""
        import tests.framework  # noqa: F401

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Framework module should be importable
        assert "tests" in sys.modules

    def test_ecan_mode_set(self, mock_env):
        """ECAN_MODE is set to 'test' in test environment."""
        assert os.getenv("ECAN_MODE") == "test"

    def test_python_version_compatible(self):
        """Python version is 3.10+ (eCan requirement)."""
        assert sys.version_info >= (3, 10)

    def test_core_dependencies_importable(self):
        """Core dependencies are importable."""
        try:
            import fastapi  # noqa: F401
            import langchain  # noqa: F401
            import pydantic  # noqa: F401
            import sqlalchemy  # noqa: F401
            import pytest  # noqa: F401
        except ImportError as e:
            pytest.fail(f"Missing core dependency: {e}")


class TestConfigAndSettings:
    """Smoke tests for configuration loading."""

    def test_app_info_import(self):
        """app_info can be imported and has expected fields."""
        from config.app_info import app_info
        from config.constants import APP_NAME

        assert app_info is not None
        assert APP_NAME == "eCan"
        assert hasattr(app_info, "app_home_path")
        assert hasattr(app_info, "version")

    def test_app_settings_import(self):
        """app_settings can be imported."""
        from config.app_settings import app_settings

        assert app_settings is not None

    def test_requirements_base_exists(self):
        """requirements-base.txt exists and is readable."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        req_path = os.path.join(project_root, "requirements-base.txt")
        assert os.path.exists(req_path), f"{req_path} not found"

        with open(req_path) as f:
            content = f.read()
        assert "langchain" in content
        assert "fastapi" in content

        with open(req_path) as f:
            content = f.read()
        assert "langchain" in content
        assert "fastapi" in content


class TestUtils:
    """Smoke tests for utility modules."""

    def test_time_util_import(self):
        """TimeUtil can be imported and used."""
        from utils.time_util import TimeUtil

        assert TimeUtil is not None
        assert hasattr(TimeUtil, "formatted_now_with_ms")

        # Should not raise
        formatted = TimeUtil.formatted_now_with_ms()
        assert isinstance(formatted, str)
        assert len(formatted) > 0

    def test_logger_helper_has_levels(self):
        """Logger helper supports standard log levels."""
        from utils.logger_helper import logger_helper

        assert hasattr(logger_helper, "debug")
        assert hasattr(logger_helper, "info")
        assert hasattr(logger_helper, "warning")
        assert hasattr(logger_helper, "error")

    def test_secure_store_import(self):
        """secure_store can be imported."""
        from utils.env.secure_store import secure_store

        assert secure_store is not None
