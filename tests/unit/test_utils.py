"""Unit tests for utility modules."""

import sys
import pytest

pytestmark = pytest.mark.unit


def _clear_utils_cache():
    """Remove any cached utils modules from sys.modules to ensure fresh imports."""
    for _k in list(sys.modules.keys()):
        if _k == "utils" or _k.startswith("utils."):
            del sys.modules[_k]


class TestStrUtils:
    """Tests for string utility functions."""

    def test_all_substrings_all_present(self):
        """all_substrings returns True when all needles are found."""
        _clear_utils_cache()
        from utils.str_utils import all_substrings

        assert all_substrings(["hello", "world"], "hello world") is True
        assert all_substrings(["a", "b", "c"], "abc") is True
        assert all_substrings(["test"], "this is a test string") is True

    def test_all_substrings_some_missing(self):
        """all_substrings returns False when any needle is missing."""
        _clear_utils_cache()
        from utils.str_utils import all_substrings

        assert all_substrings(["hello", "foo"], "hello world") is False
        assert all_substrings(["x", "y", "z"], "abc") is False

    def test_all_substrings_empty_needles(self):
        """all_substrings with empty needles list returns True."""
        _clear_utils_cache()
        from utils.str_utils import all_substrings

        assert all_substrings([], "anything") is True

    def test_all_substrings_empty_haystack(self):
        """all_substrings with empty haystack returns False unless needles empty."""
        _clear_utils_cache()
        from utils.str_utils import all_substrings

        assert all_substrings([], "") is True
        assert all_substrings(["a"], "") is False


class TestEnvUtils:
    """Tests for environment utility functions."""

    def test_is_sensitive_variable_true(self):
        """_is_sensitive_variable flags known sensitive variable names (underscore suffix pattern)."""
        from utils.env.env_utils import EnvironmentLoader

        el = EnvironmentLoader.__new__(EnvironmentLoader)
        # Patterns end with underscore-prefixed keywords: _PASSWORD, _KEY, _TOKEN, etc.
        assert el._is_sensitive_variable("USER_PASSWORD") is True
        assert el._is_sensitive_variable("MY_API_KEY") is True
        assert el._is_sensitive_variable("SOME_SECRET") is True
        assert el._is_sensitive_variable("SERVICE_TOKEN") is True

    def test_is_sensitive_variable_false(self):
        """_is_sensitive_variable returns False for regular variable names."""
        from utils.env.env_utils import EnvironmentLoader

        el = EnvironmentLoader.__new__(EnvironmentLoader)
        assert el._is_sensitive_variable("HOME") is False
        assert el._is_sensitive_variable("PATH") is False
        assert el._is_sensitive_variable("EDITOR") is False

    def test_mask_sensitive_value(self):
        """_mask_sensitive_value masks known sensitive patterns."""
        from utils.env.env_utils import EnvironmentLoader

        el = EnvironmentLoader.__new__(EnvironmentLoader)
        # Passwords with underscore suffix
        masked = el._mask_sensitive_value("USER_PASSWORD", "secret123")
        assert masked != "secret123"
        # Regular vars are not masked
        normal = el._mask_sensitive_value("EDITOR", "vim")
        assert normal == "vim"


class TestTimeUtil:
    """Tests for TimeUtil."""

    def test_formatted_now_with_ms(self):
        """formatted_now_with_ms returns a formatted string."""
        from utils.time_util import TimeUtil

        result = TimeUtil.formatted_now_with_ms()
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain at least year and time components
        assert "-" in result or "/" in result


class TestAllSubstringsEdgeCases:
    """Edge case tests for all_substrings."""

    def test_case_insensitivity(self):
        """all_substrings is case-insensitive (uses lower())."""
        _clear_utils_cache()
        from utils.str_utils import all_substrings

        # Case-insensitive matching
        assert all_substrings(["Hello"], "hello world") is True
        assert all_substrings(["hello"], "Hello World") is True

    def test_partial_matches(self):
        """Partial substring matches are valid."""
        _clear_utils_cache()
        from utils.str_utils import all_substrings

        assert all_substrings(["cat", "dog"], "the cat and dog are friends") is True
        assert all_substrings(["window", "document"], "window.document.write()") is True
