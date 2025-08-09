#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Dynamic Import Detector v2.0
Phased detection and intelligent merging, avoiding module loss while controlling spec file length
Optimized version: improve detection accuracy, ensure all dynamic packages are correctly imported
"""

import os
import sys
import importlib
import ast
import subprocess
from pathlib import Path
from typing import Set, List, Dict, Any, Optional
import json

class SmartDynamicDetector:
    """Smart Dynamic Import Detector v2.0"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.detected_modules = set()
        self.max_hidden_imports = 2000  # Increase limit to ensure more modules are included
        self.windows_cmd_limit = 8191  # Windows command line length limit
        self.spec_line_limit = 7000  # Single line length limit in spec file (with safety margin)

    def detect_smart_imports(self) -> List[str]:
        """Smart dynamic import detection v2.0"""
        print("🧠 Starting smart dynamic import detection v2.0...")

        # Phase 1: Detect project-specific dynamic imports
        print("📝 Phase 1: Detecting project-specific dynamic imports...")
        project_imports = self._detect_project_specific_imports()
        print(f"   Found project-specific imports: {len(project_imports)}")

        # Phase 2: Detect actual dynamic imports in code
        print("💻 Phase 2: Detecting actual dynamic imports in code...")
        code_imports = self._detect_actual_code_imports()
        print(f"   Found code dynamic imports: {len(code_imports)}")

        # Phase 3: Detect critical dependency dynamic imports
        print("🔑 Phase 3: Detecting critical dependency dynamic imports...")
        critical_imports = self._detect_critical_dependencies()
        print(f"   Found critical dependencies: {len(critical_imports)}")

        # Phase 4: Detect runtime dynamic imports
        print("⚡ Phase 4: Detecting runtime dynamic imports...")
        runtime_imports = self._detect_runtime_imports()
        print(f"   Found runtime imports: {len(runtime_imports)}")

        # Phase 5: Detect problematic libraries
        print("🚨 Phase 5: Detecting problematic libraries...")
        problematic_imports = self._detect_problematic_libraries()
        print(f"   Found problematic library imports: {len(problematic_imports)}")

        # Phase 6: Intelligent merging and optimization
        print("🔄 Phase 6: Intelligent merging and optimization...")
        all_modules = project_imports | code_imports | critical_imports | runtime_imports | problematic_imports

        # Phase 7: Validate and filter modules
        print("✅ Phase 7: Validating and filtering modules...")
        validated_modules = self._validate_and_filter_modules(all_modules)
        print(f"   Validated modules: {len(validated_modules)}")

        # Phase 8: Windows compatibility check and compression
        print("🪟 Phase 8: Windows compatibility check and compression...")
        final_modules = self._compress_modules_for_windows(list(validated_modules))

        # If too many modules, use intelligent strategy
        if len(final_modules) > self.max_hidden_imports:
            print(f"⚠️  Too many modules ({len(final_modules)}), using intelligent strategy...")
            final_modules = self._smart_merge_strategy(set(final_modules), project_imports, code_imports, critical_imports, runtime_imports, problematic_imports)
        else:
            final_modules = list(final_modules)

        print(f"✅ Smart detection completed: {len(final_modules)} modules")
        return final_modules

    def _detect_project_specific_imports(self) -> Set[str]:
        """Detect project-specific dynamic imports v2.0"""
        modules = set()

        # Detect package structure in project (more comprehensive detection)
        project_dirs = [
            "agent", "bot", "common", "config", "gui", "utils",
            "telemetry", "knowledge", "settings", "skills", "build_system",
            "resource", "tests", "docs", "scripts"
        ]

        for dir_name in project_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                modules.add(dir_name)

                # Recursively find submodules (unlimited depth)
                submodules = self._get_project_submodules(dir_path, dir_name)
                modules.update(submodules)

        # Add Python files in root directory
        for py_file in self.project_root.glob("*.py"):
            if py_file.name != "__init__.py":
                modules.add(py_file.stem)

        return modules

    def _get_project_submodules(self, dir_path: Path, base_name: str) -> Set[str]:
        """Get project submodules (unlimited depth) v2.0"""
        modules = set()
        try:
            for item in dir_path.iterdir():
                if item.is_file() and item.suffix == '.py':
                    if item.name != "__init__.py":
                        module_name = f"{base_name}.{item.stem}"
                        modules.add(module_name)
                elif item.is_dir() and not item.name.startswith('_'):
                    if (item / '__init__.py').exists():
                        module_name = f"{base_name}.{item.name}"
                        modules.add(module_name)
                        # Recursively find submodules
                        submodules = self._get_project_submodules(item, module_name)
                        modules.update(submodules)
        except Exception as e:
            print(f"   Warning: Failed to get submodules {dir_path}: {e}")
        return modules

    def detect_resource_packages(self) -> List[str]:
        """Detect third-party packages that likely require data file collection.
        Heuristics: packages detected as critical/runtime that contain non-.py resources (md/json/html/svg/png/etc).
        Returns a list of top-level package names suitable for PyInstaller collect_data_files()."""
        # Build candidate module set from critical and runtime detections
        candidates: Set[str] = set()
        try:
            critical = self._detect_critical_dependencies()
            runtime = self._detect_runtime_imports()
            candidates.update(critical)
            candidates.update(runtime)
        except Exception:
            pass
        # Reduce to top-level package names
        roots: Set[str] = set(m.split('.')[0] for m in candidates if m and not m.startswith(('.', '_')))
        resource_exts = {'.md', '.json', '.yaml', '.yml', '.ini', '.toml', '.html', '.htm', '.svg', '.png', '.jpg', '.jpeg', '.ico', '.txt', '.css', '.js'}
        resource_pkgs: Set[str] = set()
        for root in sorted(roots):
            try:
                mod = importlib.import_module(root)
                mod_file = getattr(mod, '__file__', None)
                if not mod_file:
                    continue
                pkg_dir = Path(mod_file).parent
                # Only consider package directories (with __init__.py)
                if not (pkg_dir / '__init__.py').exists():
                    continue
                found = False
                # Scan a limited number of files to avoid heavy IO
                for dirpath, dirnames, filenames in os.walk(pkg_dir):
                    # Shallow scan up to depth 3
                    depth = len(Path(dirpath).relative_to(pkg_dir).parts)
                    if depth > 3:
                        dirnames[:] = []
                        continue
                    for fn in filenames:
                        p = Path(dirpath) / fn
                        if p.suffix.lower() in resource_exts:
                            found = True
                            break
                    if found:
                        break
                if found:
                    resource_pkgs.add(root)
            except Exception:
                continue
        return sorted(resource_pkgs)

    def _detect_actual_code_imports(self) -> Set[str]:
        """Detect actual dynamic imports in code v2.0"""
        dynamic_imports = set()

        # Find all Python files
        python_files = list(self.project_root.rglob("*.py"))
        python_files = [f for f in python_files if not any(skip in str(f) for skip in ['venv', 'build', 'dist', '__pycache__', '.git', 'node_modules'])]

        print(f"   Analyzing {len(python_files)} Python files...")

        try:
            import concurrent.futures
            import multiprocessing

            def analyze_file(py_file):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return self._extract_actual_dynamic_imports(content)
                except:
                    return set()

            # Parallel file analysis
            max_workers = min(multiprocessing.cpu_count(), 8)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = executor.map(analyze_file, python_files)

            # Merge results
            for result in results:
                dynamic_imports.update(result)

        except ImportError:
            # Fallback to serial processing
            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Extract actual dynamic imports
                    imports = self._extract_actual_dynamic_imports(content)
                    dynamic_imports.update(imports)

                except Exception as e:
                    print(f"   Warning: Failed to analyze file {py_file}: {e}")

        return dynamic_imports

    def _extract_actual_dynamic_imports(self, content: str) -> Set[str]:
        """Extract actual dynamic imports v2.0"""
        imports = set()

        lines = content.split('\n')
        for line in lines:
            line = line.strip()

            # Detect importlib.import_module
            if 'importlib.import_module' in line:
                module = self._extract_module_name(line)
                if module:
                    imports.add(module)

            # Detect __import__
            elif '__import__' in line:
                module = self._extract_module_name(line)
                if module:
                    imports.add(module)

            # Detect from ... import *
            elif 'from ' in line and ' import *' in line:
                parts = line.split(' import ')[0].split('from ')[1]
                base_module = parts.strip()
                imports.add(base_module)

            # Detect dynamic string imports
            elif 'import ' in line and ('"' in line or "'" in line):
                module = self._extract_string_module(line)
                if module:
                    imports.add(module)

        return imports

    def _extract_module_name(self, line: str) -> Optional[str]:
        """Extract module name v2.0"""
        if "('" in line or '("' in line:
            start = line.find("('") if "('" in line else line.find('("')
            if start != -1:
                end = line.find("')", start) if "('" in line else line.find('")', start)
                if end != -1:
                    return line[start+2:end]
        return None

    def _extract_string_module(self, line: str) -> Optional[str]:
        """Extract module name from string"""
        import_pos = line.find('import ')
        if import_pos != -1:
            module_part = line[import_pos + 7:].strip()
            if module_part.startswith('"') or module_part.startswith("'"):
                end_quote = module_part.find('"', 1) if module_part.startswith('"') else module_part.find("'", 1)
                if end_quote != -1:
                    return module_part[1:end_quote]
        return None

    def _detect_critical_dependencies(self) -> Set[str]:
        """Detect critical dependency dynamic imports v2.0"""
        modules = set()

        # Extended critical dynamic import patterns v2.0
        critical_patterns = [
            # LightRAG required submodules (ensure runtime script imports are collected)
            "lightrag", "lightrag.api", "lightrag.api.lightrag_server",
            "lightrag.api.webui",

            # browser_use modules (code uses resources and dynamic submodules)
            "browser_use", "browser_use.agent", "browser_use.agent.prompts",
            "browser_use.agent.service", "browser_use.browser",
            "browser_use.dom", "browser_use.utils",

            # scipy related (most common issue)
            "scipy._lib.array_api_compat.numpy.fft",
            "scipy.stats.chatterjeexi",
            "scipy._lib.array_api_compat.numpy",
            "scipy._lib.array_api_compat",
            "scipy._lib._util",
            "scipy._lib._array_api",
            "scipy.sparse._base",
            "scipy.sparse._sputils",
            "scipy.stats._stats_py",
            "scipy.stats._continuous_distns",
            "scipy.stats._discrete_distns",
            "scipy.stats._multivariate",
            "scipy.stats._stats_mstats_common",
            "scipy.stats._stats",
            "scipy.stats._binned_statistic",
            "scipy.stats._qmc",
            "scipy.stats._sobol",
            "scipy.stats._levy_stable",
            "scipy.stats._binomtest",
            "scipy.stats._entropy",
            "scipy.stats._hypotests",
            "scipy.stats._ksstats",
            "scipy.stats._mannwhitneyu",
            "scipy.stats._morestats",
            "scipy.stats._mstats_basic",
            "scipy.stats._mstats_extras",
            "scipy.stats._page_trend_test",
            "scipy.stats._proportion",
            "scipy.stats._relative_risk",
            "scipy.stats._resampling",
            "scipy.stats._rvs_sampling",
            "scipy.stats._survival",
            "scipy.stats._tukeylambda_stats",
            "scipy.stats._variation",
            "scipy.stats.contingency",
            "scipy.stats.distributions",
            "scipy.stats.mstats",
            "scipy.stats.mstats_basic",
            "scipy.stats.mstats_extras",
            "scipy.stats.qmc",
            "scipy.stats.sampling",
            "scipy.stats.survival",

            # numpy related
            "numpy.core._methods",
            "numpy.lib.format",
            "numpy.random._pickle",
            "numpy.random._common",
            "numpy.random._bounded_integers",
            "numpy.random._mt19937",
            "numpy.random._pcg64",
            "numpy.random._philox",
            "numpy.random._sfc64",
            "numpy.random._generator",
            "numpy.random.bit_generator",
            "numpy.random.mtrand",

            # pandas related
            "pandas._libs.tslibs.timedeltas",
            "pandas._libs.tslibs.timestamps",
            "pandas._libs.tslibs.np_datetime",
            "pandas._libs.tslibs.offsets",
            "pandas._libs.tslibs.parsing",
            "pandas._libs.tslibs.period",
            "pandas._libs.tslibs.strptime",
            "pandas._libs.hashtable",
            "pandas._libs.index",
            "pandas._libs.internals",
            "pandas._libs.join",
            "pandas._libs.lib",
            "pandas._libs.missing",
            "pandas._libs.parsers",
            "pandas._libs.properties",
            "pandas._libs.reduction",
            "pandas._libs.sparse",
            "pandas._libs.window",
            "pandas._libs.writers",

            # sklearn related
            "sklearn.utils._cython_blas",
            "sklearn.neighbors._partition_nodes",
            "sklearn.tree._utils",
            "sklearn.tree._splitter",
            "sklearn.tree._criterion",
            "sklearn.tree._tree",

            # transformers related
            "transformers.tokenization_utils",
            "transformers.modeling_utils",
            "transformers.generation.utils",
            "transformers.trainer_utils",
            "transformers.data.data_collator",
            "transformers.data.processors",
            "transformers.pipelines",
            "transformers.feature_extraction_utils",
            "transformers.image_processing_utils",
            "transformers.processing_utils",

            # Web frameworks
            "fastapi.dependencies",
            "starlette.middleware",
            "uvicorn.lifespan",

            # Other critical libraries
            "pydantic.deprecated.decorator",
            "langchain_core._import_utils",
            "langchain_core.tools.base",

            # PySide6 related
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "PySide6.QtNetwork",
            "PySide6.QtWebEngine",
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets",
            "PySide6.QtQml",
            "PySide6.QtQuick",

            # cv2 related (PyInstaller compatibility)
            "cv2.dnn",
            "cv2.gapi",
            "cv2.ximgproc",
            "cv2.xfeatures2d",

            # psutil related (cross-platform)
            "psutil._psutil_windows",
            "psutil._psutil_posix",
            "psutil._psutil_osx",
            "psutil._psutil_linux",

            # pyautogui related (cross-platform)
            "pyautogui._pyautogui_win",
            "pyautogui._pyautogui_osx",
            "pyautogui._pyautogui_x11",

            # cryptography related (OpenSSL)
            "cryptography.hazmat.backends.openssl",
            "cryptography.hazmat.bindings._rust",
            "cryptography.hazmat.primitives._serialization",
            "cryptography.hazmat.primitives._asymmetric",

            # PIL related
            "PIL._tkinter_finder",
            "PIL.ImageQt",
            "PIL._imaging",
            "PIL._imagingmath",

            # requests related
            "requests.packages.urllib3.util.retry",
            "requests.packages.urllib3.contrib.pyopenssl",
            "urllib3.packages.six.moves.urllib.parse",
            "urllib3.util.ssl_",

            # charset_normalizer related
            "charset_normalizer.md__mypyc",
            "charset_normalizer.constant",

            # torch related (if present)
            "torch._C._nn",
            "torch._C._fft",
            "torch._C._linalg",
            "torch._C._sparse",
            "torch.nn.functional",
            "torch.optim.lr_scheduler",

            # Other important libraries
            "requests",
            "urllib3",
            "certifi",
            "charset_normalizer",
            "idna",

            # setuptools and jaraco related modules
            "setuptools",
            "jaraco",
            "jaraco.text",
            "jaraco.classes",
            "jaraco.functools",
            "jaraco.context",
            "jaraco.collections",
            "jaraco.stream",
            "jaraco.itertools",
            "jaraco.logging",
            "jaraco.path",

            # Pydantic related modules
            "pydantic",
            "pydantic.deprecated",
            "pydantic.deprecated.decorator",
            "pydantic_core",
            "pydantic._internal",
            "pydantic._migration",
            "pydantic._internal._validators",

            # LangChain related modules
            "langchain",
            "langchain_core",
            "langchain_openai",
            "langchain_core.tools",
            "langchain_core._import_utils",
            "langchain_core.tools.base",
        ]

        print(f"   Detecting {len(critical_patterns)} critical dynamic import patterns...")

        for module_name in critical_patterns:
            try:
                # Try to import module
                importlib.import_module(module_name)
                modules.add(module_name)
            except ImportError:
                # If import fails, check if it is a project internal module
                if not any(prefix in module_name for prefix in ['scipy.', 'numpy.', 'pandas.', 'sklearn.', 'transformers.', 'PySide6.']):
                    # For non-third-party libraries, try to add to project
                    modules.add(module_name)
            except Exception:
                # For other errors, also try to add
                modules.add(module_name)

        return modules

    def _detect_problematic_libraries(self) -> Set[str]:
        """检测项目中使用的问题库并添加必要的子模块"""
        modules = set()

        # 检查项目中实际使用的问题库
        problematic_libs = {
            'cv2': [
                'cv2.dnn', 'cv2.gapi', 'cv2.ximgproc', 'cv2.xfeatures2d'
            ],
            'psutil': [
                'psutil._psutil_windows', 'psutil._psutil_posix',
                'psutil._psutil_osx', 'psutil._psutil_linux'
            ],
            'pyautogui': [
                'pyautogui._pyautogui_win', 'pyautogui._pyautogui_osx',
                'pyautogui._pyautogui_x11'
            ],
            'cryptography': [
                'cryptography.hazmat.backends.openssl',
                'cryptography.hazmat.bindings._rust'
            ],
            'PIL': [
                'PIL._tkinter_finder', 'PIL.ImageQt', 'PIL._imaging'
            ],
            'requests': [
                'requests.packages.urllib3.util.retry',
                'requests.packages.urllib3.contrib.pyopenssl'
            ]
        }

        # 扫描项目文件检查是否使用了这些库（排除 venv 和其他不必要的目录）
        for py_file in self.project_root.rglob("*.py"):
            if any(skip in str(py_file) for skip in ['.git', '__pycache__', 'build', 'dist', 'venv', '.venv', 'env', '.env', 'site-packages']):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                for lib_name, sub_modules in problematic_libs.items():
                    if f'import {lib_name}' in content or f'from {lib_name}' in content:
                        print(f"   Found problematic library: {lib_name} in {py_file}")
                        modules.update(sub_modules)

            except Exception:
                continue

        return modules

    def _detect_runtime_imports(self) -> Set[str]:
        """Detect runtime dynamic imports"""
        modules = set()

        # Modules that may be needed at runtime
        runtime_modules = [
            # Ensure resource collection for these packages at runtime
            "lightrag", "lightrag.api", "lightrag.api.lightrag_server",
            "lightrag.api.webui",
            "browser_use", "browser_use.agent", "browser_use.agent.prompts",
            "browser_use.agent.service", "browser_use.browser",
            "browser_use.dom", "browser_use.utils",

            # System modules
            "os", "sys", "pathlib", "json", "time", "datetime",
            "subprocess", "platform", "argparse", "typing",

            # Network related
            "requests", "urllib3", "certifi", "charset_normalizer",

            # Data processing
            "pandas", "numpy", "scipy", "sklearn",

            # Machine learning
            "transformers", "torch", "tensorflow",

            # Web frameworks
            "fastapi", "starlette", "uvicorn", "flask",

            # Database
            "sqlite3", "sqlalchemy", "pymongo", "redis",

            # Image processing
            "PIL", "opencv", "matplotlib", "seaborn",

            # Other common libraries
            "yaml", "toml", "configparser", "logging",
            "threading", "multiprocessing", "asyncio",
            "aiohttp", "websockets", "socketserver",
        ]

        print(f"   Detecting {len(runtime_modules)} runtime modules...")

        for module_name in runtime_modules:
            try:
                importlib.import_module(module_name)
                modules.add(module_name)
            except ImportError:
                # For some modules, add to list even if import fails
                # Because these modules may be dynamically loaded at runtime
                if module_name in ["sqlite3", "threading", "multiprocessing", "asyncio"]:
                    modules.add(module_name)
            except Exception:
                # For other errors, also try to add
                modules.add(module_name)

        return modules

    def _smart_merge_strategy(self, all_modules: Set[str], project_imports: Set[str],
                             code_imports: Set[str], critical_imports: Set[str],
                             runtime_imports: Set[str], problematic_imports: Set[str]) -> List[str]:
        """Intelligent merging strategy v2.0, ensuring no important modules are lost"""
        final_modules = set()

        # Strategy 1: Keep all project-specific modules (highest priority)
        final_modules.update(project_imports)
        print(f"   Keeping project-specific modules: {len(project_imports)}")

        # Strategy 2: Keep all actual dynamic imports in code
        final_modules.update(code_imports)
        print(f"   Keeping code dynamic imports: {len(code_imports)}")

        # Strategy 3: Keep all critical dependencies
        final_modules.update(critical_imports)
        print(f"   Keeping critical dependencies: {len(critical_imports)}")

        # Strategy 4: Keep runtime modules
        final_modules.update(runtime_imports)
        print(f"   Keeping runtime modules: {len(runtime_imports)}")

        # Strategy 5: Keep problematic library imports (high priority)
        final_modules.update(problematic_imports)
        print(f"   Keeping problematic library imports: {len(problematic_imports)}")

        # Strategy 6: If there is still space, add other important modules
        remaining_space = self.max_hidden_imports - len(final_modules)
        if remaining_space > 0:
            other_modules = all_modules - final_modules
            if other_modules:
                # Add other modules by priority
                prioritized_others = self._prioritize_other_modules(list(other_modules))
                final_modules.update(prioritized_others[:remaining_space])
                print(f"   Adding other important modules: {min(remaining_space, len(prioritized_others))}")

        return list(final_modules)

    def _prioritize_other_modules(self, modules: List[str]) -> List[str]:
        """Prioritize other modules v2.0"""
        # Define priority rules
        priority_rules = [
            # Highest priority: Scientific computing libraries
            lambda m: any(prefix in m for prefix in ['scipy.', 'numpy.', 'pandas.', 'matplotlib.']),
            # High priority: Machine learning libraries
            lambda m: any(prefix in m for prefix in ['sklearn.', 'transformers.', 'torch.', 'tensorflow.']),
            # Medium priority: Web frameworks
            lambda m: any(prefix in m for prefix in ['fastapi.', 'starlette.', 'uvicorn.', 'django.', 'flask.']),
            # Medium priority: GUI frameworks
            lambda m: any(prefix in m for prefix in ['PySide6.', 'PyQt6.', 'tkinter.', 'wx.']),
            # Low priority: Other libraries
            lambda m: True
        ]

        prioritized = []
        for rule in priority_rules:
            rule_modules = [m for m in modules if rule(m) and m not in prioritized]
            prioritized.extend(rule_modules)

        return prioritized

    def save_detection_result(self, modules: List[str], output_file: str = "smart_detected_modules.json"):
        """Save detection results v2.0"""
        data = {
            "generated_at": str(Path.cwd()),
            "total_modules": len(modules),
            "modules": sorted(modules),
            "detection_method": "smart_automated_v2",
            "max_modules": self.max_hidden_imports,
            "version": "2.0"
        }

        output_path = self.project_root / "build_system" / output_file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"💾 Smart detection results saved to: {output_path}")

    def _is_project_module(self, module_name: str) -> bool:
        """Check if it is a project internal module"""
        project_prefixes = [
            'agent', 'bot', 'common', 'config', 'gui', 'utils',
            'telemetry', 'knowledge', 'settings', 'skills', 'build_system',
            'resource', 'tests', 'docs', 'scripts'
        ]

        # Check if module name starts with project prefix
        for prefix in project_prefixes:
            if module_name.startswith(prefix + '.') or module_name == prefix:
                return True

        # Check if it is a module under project root directory
        root_modules = ['main', 'app_context', 'build']
        if module_name in root_modules:
            return True

        return False

    def _validate_and_filter_modules(self, modules: Set[str]) -> Set[str]:
        """Validate and filter modules, ensure module name validity"""
        validated_modules = set()

        for module in modules:
            if self._is_valid_module_name(module):
                validated_modules.add(module)

        return validated_modules

    def _is_valid_module_name(self, module_name: str) -> bool:
        """Check if module name is valid"""
        # Check basic validity
        if not module_name or module_name.startswith('.') or module_name.endswith('.'):
            return False

        # Check if contains invalid characters
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        if any(char in module_name for char in invalid_chars):
            return False

        # Check if starts with number (Python modules cannot start with numbers)
        if module_name[0].isdigit():
            return False

        # Check if contains consecutive dots
        if '..' in module_name:
            return False

        # Check if ends with dot
        if module_name.endswith('.'):
            return False

        # Exclude hook files
        if 'hook-' in module_name:
            return False

        # Exclude module names with hyphens (Python module names cannot contain hyphens)
        if '-' in module_name:
            return False

        return True

    def _check_windows_compatibility(self, modules: List[str]) -> Dict[str, Any]:
        """Check Windows compatibility"""
        # Simulate generating hidden_imports line in spec file
        hidden_imports_str = "hiddenimports=[" + ", ".join(f"'{m}'" for m in modules) + "]"
        line_length = len(hidden_imports_str)

        result = {
            "line_length": line_length,
            "windows_compatible": line_length <= self.spec_line_limit,
            "exceeds_limit": line_length - self.spec_line_limit if line_length > self.spec_line_limit else 0,
            "modules_count": len(modules)
        }

        return result

    def _compress_modules_for_windows(self, modules: List[str]) -> List[str]:
        """Compress module list for Windows environment"""
        print(f"🪟 Checking Windows compatibility...")

        # Check compatibility of current module list
        compatibility = self._check_windows_compatibility(modules)

        if compatibility["windows_compatible"]:
            print(f"✅ Windows compatibility check passed: {compatibility['line_length']} characters")
            return modules

        print(f"⚠️  Windows compatibility check failed: {compatibility['line_length']} characters (limit: {self.spec_line_limit})")
        print(f"   Exceeds limit: {compatibility['exceeds_limit']} characters")

        # Compression strategy: keep modules by priority
        compressed_modules = self._apply_compression_strategy(modules)

        # Re-check compatibility
        new_compatibility = self._check_windows_compatibility(compressed_modules)

        if new_compatibility["windows_compatible"]:
            print(f"✅ Windows compatibility check passed after compression: {new_compatibility['line_length']} characters")
            print(f"   Kept modules: {len(compressed_modules)} (original: {len(modules)})")
        else:
            print(f"❌ Still exceeds limit after compression: {new_compatibility['line_length']} characters")
            # Further compression
            compressed_modules = self._apply_aggressive_compression(compressed_modules)
            final_compatibility = self._check_windows_compatibility(compressed_modules)
            print(f"✅ Final Windows compatibility check passed after compression: {final_compatibility['line_length']} characters")
            print(f"   Final kept modules: {len(compressed_modules)}")

        return compressed_modules

    def _apply_compression_strategy(self, modules: List[str]) -> List[str]:
        """Apply compression strategy"""
        # Priority 1: Project core modules (must keep)
        core_modules = [m for m in modules if self._is_core_module(m)]

        # Priority 2: Critical third-party libraries
        critical_third_party = [m for m in modules if self._is_critical_third_party(m)]

        # Priority 3: Project internal modules
        project_modules = [m for m in modules if self._is_project_module(m) and m not in core_modules]

        # Priority 4: Other modules (sorted by importance)
        other_modules = [m for m in modules if m not in core_modules + critical_third_party + project_modules]

        # Combine by priority, ensure not exceeding limit
        result = []
        for module_group in [core_modules, critical_third_party, project_modules, other_modules]:
            for module in module_group:
                result.append(module)
                # Check if exceeding limit
                test_compatibility = self._check_windows_compatibility(result)
                if not test_compatibility["windows_compatible"]:
                    result.pop()  # Remove last module
                    break

        return result

    def _apply_aggressive_compression(self, modules: List[str]) -> List[str]:
        """Apply aggressive compression strategy"""
        # Only keep the most core modules
        essential_modules = [
            # Project core
            'main', 'app_context', 'config', 'gui', 'bot', 'agent', 'common', 'utils',

            # Critical third-party libraries
            'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
            'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
            'PySide6.QtWebChannel', 'PySide6.QtWebEngine',
            'requests', 'urllib3', 'certifi', 'charset_normalizer',
            'pandas', 'numpy', 'scipy', 'sklearn',
            'transformers', 'torch', 'tensorflow',
            'fastapi', 'starlette', 'uvicorn', 'flask', 'openai',
            'sqlalchemy', 'sqlite3', 'PIL', 'opencv',
            'cryptography', 'bcrypt', 'jwt', 'playwright',
            'langmem', 'faiss', 'browser-use', 'crawl4ai', 'langmem',
            'faiss.swigfaiss_avx512', 'lightrag',

            # Ensure LightRAG runtime submodules are preserved during compression
            'lightrag.api', 'lightrag.api.lightrag_server',
            'lightrag.api.webui',

            # fake_useragent related modules
            'fake_useragent', 'fake_useragent.data', 'fake_useragent.fake',
            'fake_useragent.utils', 'fake_useragent.errors', 'fake_useragent.settings',

            # browser_use related modules and resources
            'browser_use', 'browser_use.agent', 'browser_use.agent.prompts',
            'browser_use.agent.service', 'browser_use.browser', 'browser_use.dom',
            'browser_use.utils', 'browser_use.controller', 'browser_use.telemetry'

            # Pydantic related modules
            'pydantic', 'pydantic.deprecated', 'pydantic.deprecated.decorator',
            'pydantic_core', 'pydantic._internal', 'pydantic._migration',

            # LangChain related modules
            'langchain', 'langchain_core', 'langchain_openai',
            'langchain_core.tools', 'langchain_core._import_utils',

            # setuptools and jaraco related modules
            'setuptools', 'jaraco', 'jaraco.text', 'jaraco.classes',
            'jaraco.functools', 'jaraco.context', 'jaraco.collections',
            'jaraco.stream', 'jaraco.itertools', 'jaraco.logging', "jaraco.path",
        ]

        # Filter out existing core modules from original list
        result = [m for m in modules if m in essential_modules]

        return result

    def _is_core_module(self, module: str) -> bool:
        """Check if it is a core module"""
        core_modules = [
            'main', 'app_context', 'config', 'gui', 'bot', 'agent', 'common', 'utils'
        ]
        return module in core_modules

    def _is_critical_third_party(self, module: str) -> bool:
        """Check if it is a critical third-party library"""
        critical_libs = [
            'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
            'requests', 'urllib3', 'certifi', 'charset_normalizer',
            'pandas', 'numpy', 'scipy', 'sklearn',
            'transformers', 'torch', 'tensorflow',
            'fastapi', 'starlette', 'uvicorn',
            # Ensure these are always considered critical
            'lightrag', 'browser_use',
            'sqlalchemy', 'sqlite3', 'PIL', 'opencv',
            # Add pydantic related modules
            'pydantic', 'pydantic.deprecated', 'pydantic.deprecated.decorator',
            'pydantic_core', 'pydantic._internal', 'pydantic._migration',
            # Add langchain related modules
            'langchain', 'langchain_core', 'langchain_openai',
            'langchain_core.tools', 'langchain_core._import_utils',
            # Add setuptools and jaraco related modules
            'setuptools', 'jaraco', 'jaraco.text', 'jaraco.classes',
            'jaraco.functools', 'jaraco.context', 'jaraco.collections',
            'jaraco.stream', 'jaraco.itertools', 'jaraco.logging', "jaraco.path",
        ]
        return any(module.startswith(lib) for lib in critical_libs) 