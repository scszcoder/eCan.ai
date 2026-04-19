"""
Unit test configuration for eCan.ai.

CRITICAL: The sys.path manipulation below MUST happen at module level, not in
pytest_configure. This is because pytest resets sys.path[0] to the test directory
(eCan.ai/tests/unit) when it loads this conftest module. If we only fix sys.path
in a pytest_configure hook, it runs too late — after the path has already been
reset. By fixing sys.path at module level (lines 20-22), we ensure it is applied
BEFORE pytest resets it.
"""

import os
import sys

# Fix sys.path at module level, BEFORE pytest can reset sys.path[0].
# __file__ is eCan.ai/tests/unit/conftest.py:
#   dirname(x1) -> eCan.ai/tests/unit
#   dirname(x2) -> eCan.ai/tests
#   dirname(x3) -> eCan.ai (repo root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_UTILS_DIR = os.path.join(_PROJECT_ROOT, "utils")

# Rebuild sys.path: _UTILS_DIR and _PROJECT_ROOT at front.
_new_path = [_UTILS_DIR, _PROJECT_ROOT]
_seen = {_UTILS_DIR, _PROJECT_ROOT}
for p in sys.path:
    if p not in _seen and p != "":
        _new_path.append(p)
        _seen.add(p)
sys.path[:] = _new_path

# Import pytest AFTER fixing sys.path so pytest doesn't reset it.
import pytest


def pytest_configure(config):
    """Set asyncio mode after path is established."""
    config.option.asyncio_mode = "auto"
    config.option.asyncio_default_fixture_loop_scope = "function"


pytestmark = pytest.mark.unit
