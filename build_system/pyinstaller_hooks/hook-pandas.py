"""
PyInstaller hook for pandas - exclude test modules

pandas includes extensive test suites that are not needed in production builds.
This hook explicitly excludes all testing modules to reduce build size and errors.
"""

# Exclude all pandas test modules
excludedimports = [
    # pandas.testing modules
    'pandas.testing',
    
    # pandas.tests modules (top level)
    'pandas.tests',
    'pandas.tests.construction',
    'pandas.tests.construction.test_extract_array',
    
    # pandas.tests.copy_view modules
    'pandas.tests.copy_view',
    'pandas.tests.copy_view.index',
    'pandas.tests.copy_view.index.test_datetimeindex',
    'pandas.tests.copy_view.index.test_index',
    'pandas.tests.copy_view.index.test_periodindex',
    'pandas.tests.copy_view.index.test_timedeltaindex',
    'pandas.tests.copy_view.test_array',
    'pandas.tests.copy_view.test_astype',
    'pandas.tests.copy_view.test_chained_assignment_deprecation',
    'pandas.tests.copy_view.test_clip',
    'pandas.tests.copy_view.test_constructors',
    'pandas.tests.copy_view.test_core_functionalities',
    'pandas.tests.copy_view.test_functions',
    'pandas.tests.copy_view.test_indexing',
    'pandas.tests.copy_view.test_internals',
    'pandas.tests.copy_view.test_interp_fillna',
    'pandas.tests.copy_view.test_methods',
    'pandas.tests.copy_view.test_replace',
    'pandas.tests.copy_view.test_setitem',
    'pandas.tests.copy_view.test_util',
]

print(f"[HOOK] Excluding {len(excludedimports)} pandas test modules")
