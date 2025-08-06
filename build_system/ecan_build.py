#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Cross-Platform Build System v8.0
Simplified build script - automatic dependency detection
"""

import os
import sys
import json
import time
import subprocess
import platform
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List

# Encoding initialization for Windows environment
if platform.system() == "Windows":
    try:
        import codecs
        # Reconfigure stdout/stderr only when needed
        if not hasattr(sys.stdout, 'encoding') or sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    except Exception:
        # Continue execution if encoding setup fails (doesn't affect core functionality)
        pass


class BuildEnvironment:
    """Build environment management"""
    
    def __init__(self):
        self.platform = platform.system()
        self.is_windows = self.platform == "Windows"
        self.is_macos = self.platform == "Darwin"
        self.is_linux = self.platform == "Linux"
        self.is_ci = self._detect_ci_environment()
        
    def _detect_ci_environment(self) -> bool:
        """Detect CI environment"""
        ci_vars = ['GITHUB_ACTIONS', 'CI', 'TRAVIS', 'CIRCLECI']
        return any(os.getenv(var) for var in ci_vars)
    
    def get_platform_config(self) -> Dict[str, Any]:
        """Get platform configuration"""
        if self.is_windows:
            return {
                "name": "Windows",
                "icon": "eCan.ico",
                "app_suffix": ".exe",
                "executable_suffix": ".exe"
            }
        elif self.is_macos:
            return {
                "name": "macOS",
                "icon": "eCan.icns",
                "app_suffix": ".app",
                "executable_suffix": ""
            }
        else:
            return {
                "name": "Linux",
                "icon": "eCan.ico",
                "app_suffix": "",
                "executable_suffix": ""
            }


class BuildConfig:
    """Build configuration management"""
    
    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load config file: {e}")
            sys.exit(1)
    
    def get_app_info(self) -> Dict[str, Any]:
        """Get application information"""
        return self.config.get("app_info", {})
    
    def get_data_files(self) -> Dict[str, Any]:
        """Get data files configuration"""
        return self.config.get("data_files", {})
    
    def get_pyinstaller_config(self) -> Dict[str, Any]:
        """Get PyInstaller configuration"""
        return self.config.get("pyinstaller", {})
    
    def get_build_modes(self) -> Dict[str, Any]:
        """Get build modes configuration"""
        return self.config.get("build_modes", {})
    
    def update_version(self, version: str):
        """Update version information"""
        if "app_info" in self.config:
            self.config["app_info"]["version"] = version
        if "installer" in self.config:
            self.config["installer"]["app_version"] = version
        print(f"[INFO] Updated version to: {version}")


class FrontendBuilder:
    """Frontend builder"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.frontend_dir = project_root / "gui_v2"
    
    def build(self, force: bool = False) -> bool:
        """Build frontend"""
        if not self.frontend_dir.exists():
            print("[WARNING] Frontend directory not found, skipping frontend build")
            return True
        
        print("[FRONTEND] Building frontend...")
        
        try:
            # Install dependencies (if needed)
            # if force:
            #     print("[FRONTEND] Force mode: reinstalling dependencies...")
            #     if not self._install_dependencies():
            #         return False

            # Execute build
            if not self._run_build():
                return False
            
            print("[SUCCESS] Frontend build completed")
            return True
            
        except Exception as e:
            print(f"[ERROR] Frontend build failed: {e}")
            return False
    
    def _install_dependencies(self) -> bool:
        """Install dependencies"""
        try:
            print("[FRONTEND] Installing dependencies...")

            # Set command and environment variables based on platform
            if platform.system() == "Windows":
                cmd = "npm ci --legacy-peer-deps"
                shell = True
                # Windows encoding settings
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
                env['CHCP'] = '65001'  # Set code page to UTF-8
            else:
                cmd = ["npm", "ci", "--legacy-peer-deps"]
                shell = False
                # macOS/Linux environment settings
                env = os.environ.copy()
                env['LC_ALL'] = 'en_US.UTF-8'
                env['LANG'] = 'en_US.UTF-8'

            process = subprocess.Popen(
                cmd,
                cwd=self.frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                shell=shell,
                env=env,
                encoding='utf-8',
                errors='replace'  # Replace undecodable characters instead of raising exceptions
            )

            # Display output in real-time
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[FRONTEND] {line.rstrip()}")

            return_code = process.wait()

            if return_code != 0:
                print(f"[ERROR] npm install failed with exit code: {return_code}")
                return False

            print("[SUCCESS] Dependencies installed successfully")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to install dependencies: {e}")
            return False
    
    def _run_build(self) -> bool:
        """Execute build"""
        try:
            print("[FRONTEND] Building frontend...")

            # Set command and environment variables based on platform
            if platform.system() == "Windows":
                cmd = "npm run build"
                shell = True
                # Windows encoding settings
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
                env['CHCP'] = '65001'  # Set code page to UTF-8
            else:
                cmd = ["npm", "run", "build"]
                shell = False
                # macOS/Linux environment settings
                env = os.environ.copy()
                env['LC_ALL'] = 'en_US.UTF-8'
                env['LANG'] = 'en_US.UTF-8'

            process = subprocess.Popen(
                cmd,
                cwd=self.frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                shell=shell,
                env=env,
                encoding='utf-8',
                errors='replace'  # Replace undecodable characters instead of raising exceptions
            )

            # Display output in real-time
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[FRONTEND] {line.rstrip()}")

            return_code = process.wait()

            if return_code != 0:
                print(f"[ERROR] npm build failed with exit code: {return_code}")
                return False

            print("[SUCCESS] Frontend build completed")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to build frontend: {e}")
            return False


class PyInstallerBuilder:
    """PyInstaller builder"""
    
    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path):
        self.config = config
        self.env = env
        self.project_root = project_root
        self.build_dir = project_root / "build"
        self.dist_dir = project_root / "dist"
    
    def build(self, mode: str, force: bool = False) -> bool:
        """Build application"""
        print(f"[PYINSTALLER] Starting PyInstaller build...")

        try:
            # Get mode configuration
            build_modes = self.config.get_build_modes()
            mode_config = build_modes.get(mode, {})

            # force parameter overrides cache settings
            use_cache = mode_config.get("use_cache", False) and not force

            if force:
                print("[PYINSTALLER] Force rebuild requested, ignoring cache")
            elif use_cache:
                print(f"[PYINSTALLER] Cache enabled for {mode} mode")
            else:
                print(f"[PYINSTALLER] Cache disabled for {mode} mode")

            # Check if rebuild is needed (only when cache is enabled and not in force mode)
            if use_cache and self._should_skip_build():
                print("[PYINSTALLER] Build is up to date, skipping...")
                return True

            # Clean previous build
            should_clean = force or mode_config.get("clean", False)
            if should_clean:
                if not self._clean_previous_build():
                    print("[ERROR] Failed to clean previous build")
                    return False
            else:
                # Check for output directory conflicts even if not cleaning
                if self.dist_dir.exists() and not use_cache:
                    print("[PYINSTALLER] Output directory exists, cleaning for fresh build...")
                    if not self._clean_previous_build():
                        print("[ERROR] Failed to clean output directory")
                        return False
            
            # Generate spec file
            spec_file = self._generate_spec_file(mode)
            if not spec_file:
                return False

            # Run PyInstaller
            if not self._run_pyinstaller(spec_file, mode):
                return False
            
            print("[SUCCESS] PyInstaller build completed")
            return True
            
        except Exception as e:
            print(f"[ERROR] PyInstaller build failed: {e}")
            return False

    def _should_skip_build(self) -> bool:
        """Check if build should be skipped (based on file modification time)"""
        try:
            # Note: This method is only called when cache is enabled, so no need to check cache settings again

            # Determine executable filename based on OS
            app_info = self.config.get_app_info()
            app_name = app_info.get("name", "eCan")
            if platform.system() == "Windows":
                exe_name = f"{app_name}.exe"
            else:
                exe_name = app_name  # macOS and Linux don't need .exe extension

            # Check if output file exists
            exe_file = self.dist_dir / app_name / exe_name
            if not exe_file.exists():
                print(f"[CACHE] Executable not found: {exe_file}")
                return False

            exe_mtime = exe_file.stat().st_mtime
            print(f"[CACHE] Checking build cache, executable modified: {exe_mtime}")

            # Check if source code files have been updated
            source_dirs = [
                self.project_root / "src",
                self.project_root / "gui",
                self.project_root / "bot",
                self.project_root / "config",
                self.project_root / "main.py"
            ]

            for source_path in source_dirs:
                if source_path.is_file():
                    if source_path.exists() and source_path.stat().st_mtime > exe_mtime:
                        print(f"[CACHE] Source file newer than executable: {source_path}")
                        return False
                elif source_path.is_dir() and source_path.exists():
                    for py_file in source_path.rglob("*.py"):
                        if py_file.stat().st_mtime > exe_mtime:
                            print(f"[CACHE] Source file newer than executable: {py_file}")
                            return False

            print("[CACHE] Build is up to date")
            return True
        except Exception as e:
            print(f"[CACHE] Error checking build cache: {e}")
            return False

    def _clean_previous_build(self):
        """Clean previous build"""
        print("[PYINSTALLER] Cleaning previous build...")
        try:
            if self.build_dir.exists():
                import shutil
                shutil.rmtree(self.build_dir)
                print(f"[PYINSTALLER] Cleaned build directory: {self.build_dir}")
            
            if self.dist_dir.exists():
                import shutil
                shutil.rmtree(self.dist_dir)
                print(f"[PYINSTALLER] Cleaned dist directory: {self.dist_dir}")
        except Exception as e:
            print(f"[WARNING] Failed to clean previous build: {e}")
            # Try to clean using system commands
            import subprocess
            try:
                if self.build_dir.exists():
                    subprocess.run(["rm", "-rf", str(self.build_dir)], check=True)
                if self.dist_dir.exists():
                    subprocess.run(["rm", "-rf", str(self.dist_dir)], check=True)
                print("[PYINSTALLER] Cleaned using system commands")
            except Exception as e2:
                print(f"[ERROR] Failed to clean using system commands: {e2}")
                return False
        return True
    
    def _generate_spec_file(self, mode: str) -> Optional[Path]:
        """Generate spec file"""
        try:
            spec_content = self._create_spec_content(mode)
            app_info = self.config.get_app_info()
            app_name = app_info.get("name", "eCan")
            spec_file = self.build_dir / f"{app_name.lower()}.spec"
            
            # Ensure build directory exists
            self.build_dir.mkdir(exist_ok=True)
            
            with open(spec_file, 'w', encoding='utf-8') as f:
                f.write(spec_content)
            
            print(f"[PYINSTALLER] Spec file generated: {spec_file}")
            return spec_file
            
        except Exception as e:
            print(f"[ERROR] Failed to generate spec file: {e}")
            return None
    
    def _create_spec_content(self, mode: str) -> str:
        """Create spec file content"""
        app_info = self.config.get_app_info()
        data_files = self.config.get_data_files()
        pyinstaller_config = self.config.get_pyinstaller_config()

        # Get mode configuration
        build_modes = self.config.get_build_modes()
        mode_config = build_modes.get(mode, {})

        # Basic configuration
        main_script = app_info.get("main_script", "main.py")
        main_script_path = str(self.project_root / main_script)

        # Choose correct icon file based on platform
        if self.env.is_windows:
            icon_name = app_info.get("icon_windows", "eCan.ico")
        elif self.env.is_macos:
            icon_name = app_info.get("icon_macos", "eCan.icns")
        else:
            icon_name = app_info.get("icon_windows", "eCan.ico")  # Linux uses ico as default

        icon_path = str(self.project_root / icon_name)

        # Format data files
        data_files_str = self._format_data_files(data_files)

        # Get necessary packages as hidden_imports
        essential_packages = self._get_essential_packages()
        hidden_imports = essential_packages

        # Get mode-specific configuration
        strip_debug = mode_config.get("strip_debug", False)
        console_mode = mode_config.get("console", mode == "dev")
        debug_mode = mode_config.get("debug", mode == "dev")
        use_parallel = mode_config.get("parallel", pyinstaller_config.get("parallel", False))

        # Get collect configuration
        def get_collect_packages(collect_type):
            mode_packages = mode_config.get(collect_type, [])
            global_packages = pyinstaller_config.get(collect_type, [])

            if mode_packages == "all":
                return global_packages
            elif isinstance(mode_packages, list) and mode_packages:
                return mode_packages
            elif isinstance(global_packages, list):
                return global_packages
            else:
                return []

        collect_data_packages = get_collect_packages("collect_data")
        collect_binaries_packages = get_collect_packages("collect_binaries")
        collect_submodules_packages = get_collect_packages("collect_submodules")
        

        
        # Generate collect import statements and data collection code
        collect_imports = []
        collect_code = []

        if collect_data_packages:
            collect_imports.append("from PyInstaller.utils.hooks import collect_data_files")
            data_collections = [f"collect_data_files('{pkg}')" for pkg in collect_data_packages]
            collect_code.append(f"collected_datas = [{', '.join(data_collections)}]")
            collect_code.append("collected_datas = [item for sublist in collected_datas for item in sublist]")

        if collect_binaries_packages:
            collect_imports.append("from PyInstaller.utils.hooks import collect_dynamic_libs")
            binary_collections = [f"collect_dynamic_libs('{pkg}')" for pkg in collect_binaries_packages]
            collect_code.append(f"collected_binaries = [{', '.join(binary_collections)}]")
            collect_code.append("collected_binaries = [item for sublist in collected_binaries for item in sublist]")

        if collect_submodules_packages:
            collect_imports.append("from PyInstaller.utils.hooks import collect_submodules")
            submodule_collections = [f"collect_submodules('{pkg}')" for pkg in collect_submodules_packages]
            collect_code.append(f"collected_submodules = [{', '.join(submodule_collections)}]")
            collect_code.append("collected_submodules = [item for sublist in collected_submodules for item in sublist]")

        collect_imports_str = "\n".join(collect_imports)
        collect_code_str = "\n".join(collect_code)

        # Build Analysis parameters
        binaries_param = "collected_binaries" if collect_binaries_packages else "[]"
        datas_param = f"collected_datas + {data_files_str}" if collect_data_packages else data_files_str
        hiddenimports_param = f"collected_submodules + {hidden_imports}" if collect_submodules_packages else hidden_imports

        # Simplified spec content - includes all dependencies, only excludes specific packages
        parallel_comment = "# Parallel compilation enabled via environment variables" if use_parallel else ""
        collect_comment = f"# Auto-collecting from {len(collect_data_packages + collect_binaries_packages + collect_submodules_packages)} packages" if any([collect_data_packages, collect_binaries_packages, collect_submodules_packages]) else ""

        app_name = app_info.get("name", "eCan")
        bundle_id = f"com.{app_name.lower()}.app"
        
        spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-
{parallel_comment}
{collect_comment}

{collect_imports_str}

block_cipher = None

# Collect additional data, binaries, and submodules
{collect_code_str}

a = Analysis(
    [r'{main_script_path}'],
    pathex=[r'{self.project_root}'],
    binaries={binaries_param},
    datas={datas_param},
    hiddenimports={hiddenimports_param},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={pyinstaller_config.get("excludes", [])},
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{app_name}',
    debug={debug_mode},
    bootloader_ignore_signals=False,
    strip={strip_debug},
    upx=True,
    console={console_mode},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r'{icon_path}',
)
"""
        
        # Add platform-specific configuration
        if self.env.is_windows:
            spec_content += f"""
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip={strip_debug},
    upx=True,
    upx_exclude=[],
    name='{app_name}',
)
"""
        elif self.env.is_macos:
            spec_content += f"""
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip={strip_debug},
    upx=True,
    upx_exclude=[],
    name='{app_name}',
)

app = BUNDLE(
    coll,
    name='{app_name}.app',
    icon=r'{icon_path}',
    bundle_identifier='{bundle_id}',
    info_plist={{
        'CFBundleName': '{app_name}',
        'CFBundleDisplayName': '{app_name}',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14',
        'NSPrincipalClass': 'NSApplication',
        'CFBundleDocumentTypes': [],
        'CFBundleURLTypes': [],
        'LSApplicationCategoryType': 'public.app-category.productivity',
        'NSAppTransportSecurity': {{
            'NSAllowsArbitraryLoads': True
        }}
    }},
)
"""
        
        return spec_content
    
    def _get_essential_packages(self) -> List[str]:
        """Get package list using smart dynamic import detector"""
        print("[PYINSTALLER] Using smart dynamic import detector...")
        
        try:
            # Import smart detector - fix import path
            import sys
            build_system_path = str(self.project_root / "build_system")
            if build_system_path not in sys.path:
                sys.path.insert(0, build_system_path)
            
            from smart_dynamic_detector import SmartDynamicDetector
            
            # Create detector instance
            detector = SmartDynamicDetector(self.project_root)
            
            # Detect smart dynamic imports
            all_packages = detector.detect_smart_imports()
            
            print(f"[PYINSTALLER] Smart detector found {len(all_packages)} packages")
            
            return all_packages
            
        except ImportError as e:
            self._handle_package_manager_error(f"Smart detector file not found: {e}")
            return []
        except Exception as e:
            self._handle_package_manager_error(f"Smart detector error: {e}")
            return []
    
    def _handle_package_manager_error(self, error_msg: str):
        """Handle smart detector errors"""
        print(f"[ERROR] {error_msg}")
        print("[ERROR] Smart dynamic import detector configuration error, build failed")
        print("[ERROR] Please check the following files:")
        print("  - build_system/smart_dynamic_detector.py")
        print("[ERROR] Or run the following command to test the detector:")
        print("  python build_system/smart_dynamic_detector.py")
    

    
    def _format_data_files(self, data_files: Dict[str, Any]) -> str:
        """Format data files"""
        files = []

        # Add directory
        for directory in data_files.get("directories", []):
            dir_path = self.project_root / directory
            if dir_path.exists():
                files.append(f"(r'{dir_path}', '{directory}')")
            else:
                print(f"[WARNING] Directory not found: {dir_path}")

        # Add file
        for file_path in data_files.get("files", []):
            file_path_obj = self.project_root / file_path
            if file_path_obj.exists():
                files.append(f"(r'{file_path_obj}', '.')")
            else:
                print(f"[WARNING] File not found: {file_path_obj}")

        return "[" + ",\n    ".join(files) + "]"

    def _parallel_precompile(self):
        """Parallel precompile Python files to accelerate PyInstaller"""
        try:
            import concurrent.futures
            import py_compile
            import multiprocessing

            print("[OPTIMIZATION] Starting parallel precompilation...")

            # Collect all Python files
            python_files = []
            for pattern in ["**/*.py"]:
                python_files.extend(self.project_root.glob(pattern))

            # Filter out unnecessary files
            exclude_patterns = [
                "venv", "__pycache__", ".git", "build", "dist",
                "tests", "test_", "_test", "setup.py"
            ]

            filtered_files = []
            for file in python_files:
                if not any(pattern in str(file) for pattern in exclude_patterns):
                    filtered_files.append(file)

            if not filtered_files:
                return

            print(f"[OPTIMIZATION] Precompiling {len(filtered_files)} Python files...")

            # Use multithreading instead of multiprocessing (avoid pickle issues)
            max_workers = min(multiprocessing.cpu_count(), 8)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                def compile_file(file_path):
                    try:
                        py_compile.compile(file_path, doraise=True, optimize=1)
                        return True
                    except:
                        return False

                results = list(executor.map(compile_file, filtered_files))

            success_count = sum(results)
            print(f"[OPTIMIZATION] Precompiled {success_count}/{len(filtered_files)} files successfully")

        except Exception as e:
            print(f"[WARNING] Precompilation failed: {e}")
            # Continue building, precompilation failure should not block build

    def _run_pyinstaller(self, spec_file: Path, mode: str = "prod") -> bool:
        """Run PyInstaller"""
        try:
            print(f"[PYINSTALLER] Running command: {sys.executable} -m PyInstaller {spec_file}")
            print(f"[PYINSTALLER] Working directory: {self.project_root}")
            print("=" * 60)

            # Precompilation optimization: parallel precompile Python files
            build_modes = self.config.get_build_modes()
            mode_config = build_modes.get(mode, {})
            use_parallel = mode_config.get("parallel", False)

            if use_parallel and mode in ["fast", "dev", "prod"]:
                self._parallel_precompile()

            # Set environment variables based on platform
            if platform.system() == "Windows":
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
                env['CHCP'] = '65001'  # Set code page to UTF-8
            else:
                # macOS/Linux environment settings
                env = os.environ.copy()
                env['LC_ALL'] = 'en_US.UTF-8'
                env['LANG'] = 'en_US.UTF-8'

            # Add parallel build parameters
            cmd = [sys.executable, "-m", "PyInstaller"]

            # Get configuration
            pyinstaller_config = self.config.get_pyinstaller_config()
            build_modes = self.config.get_build_modes()
            mode_config = build_modes.get(mode, {})

            # When using spec file, only a few options can be added
            cmd.extend([
                "--noconfirm",  # Don't ask for confirmation
            ])

            # Decide whether to clean based on mode
            if mode_config.get("clean", False):
                cmd.append("--clean")
                print("[PYINSTALLER] Clean build enabled")

            # Add cache support (prioritize mode configuration, then global configuration)
            use_cache = mode_config.get("use_cache", pyinstaller_config.get("use_cache", False))
            if use_cache:
                cache_dir = pyinstaller_config.get("cache_dir", "build/pyinstaller_cache")
                cache_path = self.project_root / cache_dir
                cache_path.mkdir(parents=True, exist_ok=True)
                cmd.extend(["--workpath", str(cache_path)])
                print(f"[PYINSTALLER] Using cache directory: {cache_path}")

            # Configure parallel compilation environment variables
            use_parallel = mode_config.get("parallel", pyinstaller_config.get("parallel", False))
            if use_parallel:
                import multiprocessing
                workers = pyinstaller_config.get("workers", 0)
                if workers == 0:
                    workers = min(multiprocessing.cpu_count(), 8)  # Limit to maximum 8 processes

                # Set compilation optimization environment variables
                env['PYTHONHASHSEED'] = '1'  # Ensure compilation consistency
                env['PYTHONOPTIMIZE'] = '1'  # Enable Python optimization
                env['PYTHONDONTWRITEBYTECODE'] = '1'  # Don't write .pyc files, accelerate

                # Set multithreading library optimization (effective for scientific computing libraries)
                env['OMP_NUM_THREADS'] = str(workers)
                env['MKL_NUM_THREADS'] = str(workers)
                env['NUMEXPR_NUM_THREADS'] = str(workers)

                # Set memory and I/O optimization
                env['PYTHONUNBUFFERED'] = '1'  # Unbuffered output

                # Set temporary directory to faster storage (if possible)
                import tempfile
                temp_dir = tempfile.gettempdir()
                env['TMPDIR'] = temp_dir
                env['TEMP'] = temp_dir
                env['TMP'] = temp_dir

                print(f"[PYINSTALLER] Performance optimization enabled with {workers} threads for libraries")
                print(f"[PYINSTALLER] Using temp directory: {temp_dir}")

            strip_debug = mode_config.get("strip_debug", pyinstaller_config.get("strip_debug", False))
            if strip_debug:
                print("[PYINSTALLER] Debug symbols will be stripped (configured in spec file)")

            # Note: When using spec file, collect parameters must be defined in spec file, cannot be added in command line
            # collect configuration will be handled during spec file generation

            cmd.append(str(spec_file))

            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                encoding='utf-8',
                errors='replace'  # Replace undecodable characters instead of raising exceptions
            )

            # Display output in real-time
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[PYINSTALLER] {line.rstrip()}")

            return_code = process.wait()

            print("=" * 60)

            if return_code != 0:
                print(f"[ERROR] PyInstaller failed with exit code: {return_code}")
                return False

            return True

        except Exception as e:
            print(f"[ERROR] Failed to run PyInstaller: {e}")
            return False


class InstallerBuilder:
    """Installer builder"""

    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path, mode: str = "prod"):
        self.config = config
        self.env = env
        self.project_root = project_root
        self.dist_dir = project_root / "dist"
        self.mode = mode
    
    def build(self) -> bool:
        """Build installer"""
        if self.env.is_windows:
            return self._build_windows_installer()
        elif self.env.is_macos:
            return self._build_macos_installer()
        else:
            print("[INFO] Installer creation not implemented for this platform")
            return True
    
    def _build_windows_installer(self) -> bool:
        """Build Windows installer"""
        try:
            # Check Inno Setup
            if not self._check_inno_setup():
                print("[WARNING] Inno Setup not found, skipping installer creation")
                return True
            
            # Create Inno Setup script
            iss_file = self._create_inno_script()
            if not iss_file:
                return False
            
            # Run Inno Setup
            return self._run_inno_setup(iss_file)
            
        except Exception as e:
            print(f"[ERROR] Windows installer creation failed: {e}")
            return False
    
    def _check_inno_setup(self) -> bool:
        """Check Inno Setup"""
        inno_paths = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe"
        ]
        return any(Path(path).exists() for path in inno_paths)
    
    def _create_inno_script(self) -> Optional[Path]:
        """Create Inno Setup script"""
        try:
            installer_config = self.config.config.get("installer", {})
            app_info = self.config.get_app_info()

            # Choose compression settings based on build mode
            compression_modes = installer_config.get("compression_modes", {})
            mode_config = compression_modes.get(self.mode, {})

            # Use mode-specific configuration, or fallback to defaults
            compression = mode_config.get("compression", installer_config.get("compression", "zip"))
            solid_compression = str(mode_config.get("solid_compression", installer_config.get("solid_compression", False))).lower()
            internal_compress_level = mode_config.get("internal_compress_level", "fast")

            # Check if parallel processing is enabled
            build_modes = self.config.get_build_modes()
            build_mode_config = build_modes.get(self.mode, {})
            use_parallel = build_mode_config.get("parallel", False)

            # Add parallel processing comments
            parallel_comment = "; Parallel compression enabled via environment variables" if use_parallel else "; Single-threaded compression"

            iss_content = f"""
; eCan Installer Script
{parallel_comment}
[Setup]
AppName={installer_config.get('app_name', app_info.get('name', 'eCan'))}
AppVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}
AppPublisher={installer_config.get('app_publisher', 'eCan Team')}
DefaultDirName={{autopf}}\\eCan
DefaultGroupName=eCan
OutputDir=..\\dist
OutputBaseFilename=eCan-Setup
Compression={compression}
SolidCompression={solid_compression}
PrivilegesRequired=lowest
InternalCompressLevel={internal_compress_level}
; Improved installation configuration to avoid COM errors
SetupIconFile=..\\eCan.ico
UninstallDisplayIcon={{app}}\\eCan.exe
CreateUninstallRegKey=true
; Handle permission issues
AllowNoIcons=true
DisableProgramGroupPage=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "..\\dist\\eCan\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\eCan"; Filename: "{{app}}\\eCan.exe"
Name: "{{userdesktop}}\\eCan"; Filename: "{{app}}\\eCan.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\eCan.exe"; Description: "{{cm:LaunchProgram,eCan}}"; Flags: nowait postinstall skipifsilent
"""
            
            iss_file = self.project_root / "build" / "setup.iss"
            iss_file.parent.mkdir(exist_ok=True)
            
            with open(iss_file, 'w', encoding='utf-8') as f:
                f.write(iss_content)
            
            return iss_file
            
        except Exception as e:
            print(f"[ERROR] Failed to create Inno Setup script: {e}")
            return None
    
    def _run_inno_setup(self, iss_file: Path) -> bool:
        """Run Inno Setup"""
        try:
            inno_paths = [
                r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                r"C:\Program Files\Inno Setup 6\ISCC.exe"
            ]
            
            iscc_path = None
            for path in inno_paths:
                if Path(path).exists():
                    iscc_path = path
                    break
            
            if not iscc_path:
                print("[ERROR] Inno Setup compiler not found")
                return False
            
            # Dynamically set timeout based on compression mode
            installer_config = self.config.config.get("installer", {})
            compression_modes = installer_config.get("compression_modes", {})
            mode_config = compression_modes.get(self.mode, {})

            compression = mode_config.get("compression", installer_config.get("compression", "lzma"))
            solid_compression = mode_config.get("solid_compression", installer_config.get("solid_compression", False))
            internal_compress_level = mode_config.get("internal_compress_level", "normal")

            # Calculate timeout based on compression settings and parallel processing
            build_modes = self.config.get_build_modes()
            build_mode_config = build_modes.get(self.mode, {})
            use_parallel = build_mode_config.get("parallel", False)

            # Adjust timeout based on build mode and parallel processing
            if self.mode == "prod":
                # Production mode: quality priority, allow sufficient time
                base_timeout_multiplier = 1
                if compression == "lzma" and solid_compression and internal_compress_level == "max":
                    timeout_seconds = int(6000 * base_timeout_multiplier)  # 60 minutes
                elif compression == "lzma" and solid_compression:
                    timeout_seconds = int(4000 * base_timeout_multiplier)  # 40 minutes
                else:
                    timeout_seconds = int(2000 * base_timeout_multiplier)   # 20 minutes
            else:
                # Development mode: speed priority
                timeout_seconds = int(1500)

            print(f"[INSTALLER] Running Inno Setup: {iscc_path}")
            print(f"[INSTALLER] Script file: {iss_file}")
            print(f"[INSTALLER] Build mode: {self.mode}")
            print(f"[INSTALLER] Compression: {compression}, Solid: {solid_compression}, Level: {internal_compress_level}")
            print(f"[INSTALLER] Parallel compression: {'enabled' if use_parallel else 'disabled'}")
            print(f"[INSTALLER] Timeout: {timeout_seconds//60:.1f} minutes ({timeout_seconds} seconds)")
            print(f"[INSTALLER] Starting compression... (this may take several minutes)")
            print("=" * 60)

            # Encoding handling in Windows environment
            if self.env.is_windows:
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'

                # Configure parallel compression
                build_modes = self.config.get_build_modes()
                mode_config = build_modes.get(self.mode, {})
                use_parallel = mode_config.get("parallel", False)

                if use_parallel:
                    import multiprocessing
                    workers = min(multiprocessing.cpu_count(), 8)
                    # Set compression thread count environment variable
                    env['NUMBER_OF_PROCESSORS'] = str(workers)
                    env['INNO_COMPRESS_THREADS'] = str(workers)
                    print(f"[INSTALLER] Parallel compression enabled with {workers} threads")

                # Build Inno Setup command
                cmd = [iscc_path]

                # Add parallel optimization parameters
                if use_parallel:
                    cmd.extend(["/Q", "/O+"])  # Quiet mode + output optimization
                else:
                    cmd.append("/Q")  # Quiet mode only

                cmd.append(str(iss_file))

                try:
                    result = subprocess.run(
                        cmd,
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        env=env,
                        encoding='utf-8',
                        errors='replace',
                        timeout=timeout_seconds
                    )
                except subprocess.TimeoutExpired:
                    print(f"[ERROR] Inno Setup compilation timed out ({timeout_seconds//60:.1f} minutes)")
                    print("[INFO] This usually happens with large files or high compression settings")
                    print("[INFO] Suggestions to reduce build time:")
                    print("  - Use 'fast' mode: python build.py fast")
                    print("  - Use ZIP compression instead of LZMA")
                    print("  - Disable solid compression")
                    print("  - Reduce internal compression level")
                    print(f"[INFO] Current settings: {compression} compression, solid={solid_compression}, level={internal_compress_level}")
                    return False
            else:
                # Non-Windows platform (run Inno Setup through Wine)
                build_modes = self.config.get_build_modes()
                mode_config = build_modes.get(self.mode, {})
                use_parallel = mode_config.get("parallel", False)

                cmd = [iscc_path]
                if use_parallel:
                    cmd.extend(["/Q", "/O+"])  # Quiet mode + output optimization
                else:
                    cmd.append("/Q")  # Quiet mode only
                cmd.append(str(iss_file))

                result = subprocess.run(
                    cmd,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True
                )
            
            if result.returncode != 0:
                print(f"[ERROR] Inno Setup compilation failed:")
                print(f"[ERROR] Return code: {result.returncode}")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] Windows installer created")
            print(f"[INFO] Inno Setup output: {result.stdout}")

            # Check if output file exists
            app_info = self.config.get_app_info()
            app_name = app_info.get("name", "eCan")
            expected_output = self.dist_dir / f"{app_name}-Setup.exe"
            if expected_output.exists():
                size_mb = expected_output.stat().st_size / (1024 * 1024)
                print(f"[INFO] Installer file: {expected_output}")
                print(f"[INFO] File size: {size_mb:.1f} MB")
            else:
                print(f"[WARNING] Expected installer file not found: {expected_output}")

            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to run Inno Setup: {e}")
            return False

    def _build_macos_installer(self) -> bool:
        """Build macOS installer"""
        try:
            print("[INSTALLER] Building macOS pkg installer...")
            
            # Check required tools
            if not self._check_macos_tools():
                print("[WARNING] Required macOS tools not found, skipping pkg creation")
                return True
            
            # Check if .app file exists
            app_info = self.config.get_app_info()
            app_name = app_info.get("name", "eCan")
            version = app_info.get("version", "1.0.0")
            app_path = self.dist_dir / f"{app_name}.app"
            if not app_path.exists():
                print(f"[ERROR] App bundle not found: {app_path}")
                print("[ERROR] Please build the app first using PyInstaller")
                return False

            # Create component package
            component_pkg = self._create_component_package(app_path)
            if not component_pkg:
                return False

            # Use component package directly as final installer (simplified process)
            final_pkg = self.dist_dir / f"{app_name}-{version}.pkg"
            import shutil
            shutil.copy2(component_pkg, final_pkg)
            
            # Ensure file permissions are correct
            import os
            os.chmod(final_pkg, 0o644)
            
            size_mb = final_pkg.stat().st_size / (1024 * 1024)
            print(f"[MACOS] Final package created: {final_pkg} ({size_mb:.1f} MB)")
            
            print("[SUCCESS] macOS pkg installer created")
            return True
            
        except Exception as e:
            print(f"[ERROR] macOS installer creation failed: {e}")
            return False
    
    def _check_macos_tools(self) -> bool:
        """Check required macOS tools"""
        try:
            # Check pkgbuild - use --help instead of --version
            result = subprocess.run(["pkgbuild", "--help"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0 and result.returncode != 1:  # pkgbuild --help may return 1
                print("[ERROR] pkgbuild not found or not working")
                return False
            
            # Check productbuild - use --help instead of --version
            result = subprocess.run(["productbuild", "--help"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0 and result.returncode != 1:  # productbuild --help may return 1
                print("[ERROR] productbuild not found or not working")
                return False
            
            print("[SUCCESS] macOS packaging tools found")
            return True
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Timeout checking macOS tools")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to check macOS tools: {e}")
            return False
    


    def _create_component_package(self, app_path: Path) -> Optional[Path]:
        """Create component package"""
        try:
            print("[MACOS] Creating component package...")
            
            # Create build directory
            build_dir = self.project_root / "build" / "macos_pkg"
            build_dir.mkdir(parents=True, exist_ok=True)
            
            # Create postinstall script
            scripts_dir = build_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            
            postinstall_script = scripts_dir / "postinstall"
            postinstall_content = """#!/bin/bash
# Post-installation script
echo "Installing eCan..."

# Set application permissions
chmod -R 755 "/Applications/eCan.app"

# Create desktop shortcut
if [ -d "/Users/$USER/Desktop" ]; then
    ln -sf "/Applications/eCan.app" "/Users/$USER/Desktop/eCan.app"
    echo "Desktop shortcut created"
fi

# Create Applications folder shortcut
if [ -d "/Applications" ]; then
    # Ensure app is visible in Applications folder
    touch "/Applications/eCan.app"
fi

# Refresh Finder and Dock
killall Finder 2>/dev/null || true
killall Dock 2>/dev/null || true

echo "eCan installation completed"
exit 0
"""
            
            with open(postinstall_script, 'w', encoding='utf-8') as f:
                f.write(postinstall_content)
            
            postinstall_script.chmod(0o755)
            
            # Get app information
            app_info = self.config.get_app_info()
            app_name = app_info.get("name", "eCan")
            version = app_info.get("version", "1.0.0")

            # Get macOS configuration
            macos_config = self.config.config.get("macos", {})
            bundle_identifier = macos_config.get("bundle_identifier", "com.ecan.app")

            # Create component package - use simpler parameters to avoid timeout
            component_pkg = build_dir / f"{app_name}-component.pkg"
            cmd = [
                "pkgbuild",
                "--component", str(app_path),
                "--install-location", "/Applications",
                "--identifier", bundle_identifier,
                "--version", version,
                "--scripts", str(scripts_dir),
                str(component_pkg)
            ]
            
            print(f"[MACOS] Running pkgbuild: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)  # Increase timeout to 15 minutes
            
            if result.returncode != 0:
                print(f"[ERROR] pkgbuild failed:")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return None
            
            print(f"[MACOS] Component package created: {component_pkg}")
            return component_pkg
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Component package creation timed out after 900 seconds")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to create component package: {e}")
            return None

    def _create_final_package(self, component_pkg: Path) -> Optional[Path]:
        """Create final installer package"""
        try:
            print("[MACOS] Creating final package...")
            
            # Create distribution.xml
            build_dir = self.project_root / "build" / "macos_pkg"
            dist_xml = build_dir / "distribution.xml"
            
            # Get version information
            app_info = self.config.get_app_info()
            version = app_info.get("version", "1.0.0")
            
            distribution_content = f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>eCan</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true"/>
    <pkg-ref id="com.ecan.app"/>
    <choices-outline>
        <line choice="com.ecan.app"/>
    </choices-outline>
    <choice id="com.ecan.app" title="eCan">
        <pkg-ref id="com.ecan.app"/>
    </choice>
    <pkg-ref id="com.ecan.app" version="{version}" onConclusion="none">{component_pkg.name}</pkg-ref>
</installer-gui-script>
"""
            
            with open(dist_xml, 'w', encoding='utf-8') as f:
                f.write(distribution_content)
            
            # Create resources directory
            resources_dir = build_dir / "resources"
            resources_dir.mkdir(exist_ok=True)
            
            # Create final installer package
            final_pkg = self.dist_dir / f"eCan-{version}.pkg"
            cmd = [
                "productbuild",
                "--distribution", str(dist_xml),
                "--package-path", str(component_pkg.parent),
                "--resources", str(resources_dir),
                str(final_pkg)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            
            if result.returncode != 0:
                print(f"[ERROR] productbuild failed:")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return None
            
            # Check file size
            if final_pkg.exists():
                size_mb = final_pkg.stat().st_size / (1024 * 1024)
                print(f"[MACOS] Final package created: {final_pkg} ({size_mb:.1f} MB)")
                return final_pkg
            else:
                print("[ERROR] Final package file not found")
                return None
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Final package creation timed out after 600 seconds")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to create final package: {e}")
            return None
    



class ECanBuild:
    """eCan build main class"""
    
    def __init__(self, mode: str = "prod", version: str = None):
        self.mode = mode
        self.version = version
        self.project_root = Path.cwd()

        # Use unified configuration file
        config_file = self.project_root / "build_system" / "build_config.json"
        self.config = BuildConfig(config_file)
        
        # If version is specified, update configuration
        if self.version:
            self.config.update_version(self.version)
            
        self.env = BuildEnvironment()
        self.frontend_builder = FrontendBuilder(self.project_root)
        self.pyinstaller_builder = PyInstallerBuilder(self.config, self.env, self.project_root)
        self.installer_builder = InstallerBuilder(self.config, self.env, self.project_root, self.mode)
    
    def build(self, force: bool = False, skip_frontend: bool = None, skip_installer: bool = False) -> bool:
        """Execute build"""
        start_time = time.time()

        print("=" * 60)
        print("eCan Cross-Platform Build System v8.0")
        print("=" * 60)

        try:
            # Build frontend (if needed)
            if skip_frontend is None:
                skip_frontend = self.mode == "prod"

            if not skip_frontend:
                if not self.frontend_builder.build(force):
                    return False

            # Build main application
            if not self.pyinstaller_builder.build(self.mode, force):
                return False

            # Build installer (if needed)
            if not skip_installer:
                print(f"[INFO] Creating installer for {self.mode} mode...")
                if not self.installer_builder.build():
                    print("[WARNING] Installer creation failed, but build continues")
            else:
                print("[INFO] Skipping installer creation")

            # Display results
            self._show_result(start_time)
            return True

        except KeyboardInterrupt:
            print("\n[INFO] Build interrupted by user")
            return False
        except Exception as e:
            print(f"[ERROR] Build failed: {e}")
            return False
    
    def _show_result(self, start_time: float):
        """Display build results"""
        build_time = time.time() - start_time
        print("=" * 60)
        print(f"[SUCCESS] Build completed in {build_time:.2f} seconds")
        print(f"[INFO] Build mode: {self.mode}")
        print(f"[INFO] Platform: {self.env.platform}")
        print("=" * 60)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="eCan Build System")
    parser.add_argument("mode", choices=["dev", "prod", "fast"], default="prod", nargs="?",
                       help="Build mode (default: prod)")
    parser.add_argument("--force", "-f", action="store_true",
                       help="Force rebuild")
    parser.add_argument("--version", "-V", type=str,
                       help="Specify version number (e.g., 1.0.0, 2.1.3)")
    parser.add_argument("--skip-frontend", action="store_true",
                       help="Skip frontend build")
    parser.add_argument("--skip-installer", action="store_true",
                       help="Skip installer creation")

    args = parser.parse_args()

    # Use specified build mode
    builder = ECanBuild(args.mode, version=args.version)
    success = builder.build(force=args.force, skip_frontend=args.skip_frontend, skip_installer=args.skip_installer)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
