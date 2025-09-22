"""
Universal lazy import utility
Simplifies lazy loading of heavy libraries to improve application startup speed
"""

import importlib
from typing import Any, Dict


class LazyImporter:
    """Lazy importer - unified management of all lazy-imported libraries"""

    def __init__(self):
        self._modules: Dict[str, Any] = {}
        self._aliases: Dict[str, str] = {
            # Common library alias mappings
            'pd': 'pandas',
            'np': 'numpy',
            'cv2': 'cv2',
            'plt': 'matplotlib.pyplot',
        }
    
    def __getattr__(self, name: str) -> Any:
        """Dynamically get module, import only on first access"""
        if name.startswith('_'):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

        # Check if already imported
        if name in self._modules:
            return self._modules[name]

        # Get real module name (handle aliases)
        module_name = self._aliases.get(name, name)

        try:
            # Dynamically import module
            module = importlib.import_module(module_name)

            # Special handling: pyautogui needs pyscreeze version fix
            if name == 'pyautogui' or module_name == 'pyautogui':
                self._fix_pyscreeze_version()

            # Cache imported module
            self._modules[name] = module
            return module

        except ImportError as e:
            raise ImportError(f"Failed to import {module_name}: {e}")

    def _fix_pyscreeze_version(self):
        """Fix pyscreeze PIL version compatibility issue"""
        if not hasattr(self._fix_pyscreeze_version, '_fixed'):
            try:
                import pyscreeze
                import PIL
                # Convert string version to tuple to avoid version comparison errors
                __PIL_TUPLE_VERSION = tuple(int(x) for x in PIL.__version__.split("."))
                pyscreeze.PIL__version__ = __PIL_TUPLE_VERSION
                self._fix_pyscreeze_version._fixed = True
            except (ImportError, AttributeError, ValueError):
                # If fix fails, don't affect normal usage
                pass
    
    def register_alias(self, alias: str, module_name: str):
        """Register module alias"""
        self._aliases[alias] = module_name

    def preload(self, *module_names: str):
        """Preload specified modules (optional, for scenarios requiring early loading)"""
        for name in module_names:
            getattr(self, name)

    def is_loaded(self, name: str) -> bool:
        """Check if module is loaded"""
        return name in self._modules

    def get_loaded_modules(self) -> Dict[str, Any]:
        """Get all loaded modules"""
        return self._modules.copy()


# Global lazy importer instance
lazy = LazyImporter()

# Register common heavy library aliases
lazy.register_alias('pd', 'pandas')
lazy.register_alias('np', 'numpy')
lazy.register_alias('pyautogui', 'pyautogui')
lazy.register_alias('requests', 'requests')
lazy.register_alias('PIL', 'PIL')
lazy.register_alias('Image', 'PIL.Image')
lazy.register_alias('cv2', 'cv2')
lazy.register_alias('fuzz', 'fuzzywuzzy.fuzz')
lazy.register_alias('gw', 'pygetwindow')
lazy.register_alias('DeepDiff', 'deepdiff.DeepDiff')
lazy.register_alias('openpyxl', 'openpyxl')

# For backward compatibility, also export common libraries directly
def get_pandas():
    """Get pandas library"""
    return lazy.pd

def get_numpy():
    """Get numpy library"""
    return lazy.np

def get_pyautogui():
    """Get pyautogui library"""
    return lazy.pyautogui

def get_requests():
    """Get requests library"""
    return lazy.requests


# Usage example:
# from utils.lazy_import import lazy
#
# # Direct usage, automatically imports on first access
# df = lazy.pd.DataFrame(data)              # Equivalent to: import pandas as pd; df = pd.DataFrame(data)
# img = lazy.pyautogui.screenshot()         # Equivalent to: import pyautogui; img = pyautogui.screenshot()
# arr = lazy.np.array([1, 2, 3])           # Equivalent to: import numpy as np; arr = np.array([1, 2, 3])
# response = lazy.requests.get(url)         # Equivalent to: import requests; response = requests.get(url)
#
# # Advantages:
# 1. Import only when actually used, dramatically improves startup speed
# 2. Unified management of all lazy imports, cleaner code
# 3. Automatic caching, no performance loss on repeated access
# 4. Alias support, convenient to use
