"""Integration test configuration."""

import os
import sys

# Fix sys.path at module level, BEFORE pytest can reset sys.path[0].
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_UTILS_DIR = os.path.join(_PROJECT_ROOT, "utils")

_new_path = [_UTILS_DIR, _PROJECT_ROOT]
_seen = {_UTILS_DIR, _PROJECT_ROOT}
for p in sys.path:
    if p not in _seen and p != "":
        _new_path.append(p)
        _seen.add(p)
sys.path[:] = _new_path
