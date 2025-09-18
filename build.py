#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Unified Build System v9.0
Supports multiple build modes and performance optimization
"""

import sys

from build_system.build_cleaner import BuildCleaner


def main():
    """Thin wrapper that delegates to build_system.unified_build.main"""
    from build_system.unified_build import main as ub_main
    return ub_main()


if __name__ == "__main__":
    # Thin wrapper:
    # - Handle --cleanup-only locally for convenience/compatibility
    # - Delegate all other CLI handling to the unified build system
    import sys as _sys
    if "--cleanup-only" in _sys.argv:
        try:
            cleaner = BuildCleaner(verbose=False)
            results = cleaner.clean_all()
            print(f"[CLEAN] Done. Freed {results['total_size_mb']:.1f}MB, removed {results['broken_symlinks']} broken symlinks")
            _sys.exit(0)
        except Exception as _e:
            print(f"[CLEAN] Warning: cleanup failed: {_e}")
            _sys.exit(1)
    from build_system.unified_build import main as ub_main
    _sys.exit(ub_main())