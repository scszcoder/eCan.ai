"""
Python 3.14 Asyncio Compatibility Patches

This module contains patches for third-party libraries that are incompatible
with Python 3.14's stricter asyncio.timeout() requirements.

Usage:
    python -m patches.apply_patches

Or programmatically:
    from patches import apply_all_patches
    apply_all_patches()
"""

from .apply_patches import apply_all_patches, check_patches_applied

__all__ = ['apply_all_patches', 'check_patches_applied']
