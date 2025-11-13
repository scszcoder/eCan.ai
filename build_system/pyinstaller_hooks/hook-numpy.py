"""
PyInstaller hook for numpy - exclude test modules

numpy includes extensive test suites that are not needed in production builds.
This hook explicitly excludes all testing modules to reduce build size and errors.
"""

# Exclude all numpy test modules
excludedimports = [
    # numpy.testing modules
    'numpy.testing',
    'numpy.testing._private',
    'numpy.testing._private.extbuild',
    'numpy.testing._private.utils',
    'numpy.testing.overrides',
    'numpy.testing.print_coercion_tables',
    'numpy.testing.setup',
    'numpy.testing.tests',
    'numpy.testing.tests.test_utils',
    
    # numpy.tests modules
    'numpy.tests',
    'numpy.tests.test__all__',
    'numpy.tests.test_ctypeslib',
    'numpy.tests.test_lazyloading',
    'numpy.tests.test_matlib',
    'numpy.tests.test_numpy_config',
    'numpy.tests.test_numpy_version',
    'numpy.tests.test_public_api',
    'numpy.tests.test_reloading',
    'numpy.tests.test_scripts',
    'numpy.tests.test_warnings',
]

print(f"[HOOK] Excluding {len(excludedimports)} numpy test modules")
