#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minibuild core: simplified PyInstaller spec generation and build pipeline."""
from __future__ import annotations

import json
import sys
import subprocess
import os
import shutil
import logging

from pathlib import Path
from typing import Dict, List, Set, Any, Optional

# Import platform handler from consolidated build_utils
try:
    from .build_utils import platform_handler
except ImportError:
    # Handle case when imported directly
    from build_utils import platform_handler


class QtFrameworkFixer:
    """Qt WebEngine macOS Framework Symlink Fixer for PyInstaller bundles"""
    
    def __init__(self, bundle_path: Path, verbose: bool = False):
        """Initialize the Qt framework fixer"""
        self.bundle_path = Path(bundle_path)
        self.verbose = verbose
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """Setup logger for the fixer"""
        logger = logging.getLogger("QtFrameworkFixer")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[QT-FRAMEWORK-FIX] %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def fix_qt_webengine(self) -> bool:
        """Fix Qt WebEngine framework structure"""
        if sys.platform != 'darwin':
            self.logger.info("Skipping Qt framework fix (not macOS)")
            return True
            
        try:
            # Find QtWebEngineCore frameworks
            frameworks = list(self.bundle_path.rglob("QtWebEngineCore.framework"))
            
            if not frameworks:
                self.logger.info("No QtWebEngineCore frameworks found")
                return True
                
            success = True
            for framework in frameworks:
                self.logger.info(f"Fixing framework: {framework}")
                if not self._fix_framework_structure(framework):
                    success = False
                    
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to fix Qt WebEngine: {e}")
            return False
    
    def _fix_framework_structure(self, framework_path: Path) -> bool:
        """Fix individual framework structure - minimal and precise"""
        try:
            versions_dir = framework_path / "Versions"
            if not versions_dir.exists():
                self.logger.debug(f"No Versions directory in {framework_path}")
                return True

            # Only look for the common PyInstaller misplaced location
            process_app = versions_dir / "Resources" / "Helpers" / "QtWebEngineProcess.app"
            if not process_app.exists():
                self.logger.debug(f"No QtWebEngineProcess.app found at expected PyInstaller location")
                return True

            self.logger.debug(f"Found QtWebEngineProcess.app at: {process_app}")

            # Ensure version directory A exists
            version_a = versions_dir / "A"
            if not version_a.exists():
                version_a.mkdir(exist_ok=True)
                self.logger.debug(f"Created version directory: {version_a}")

            # Ensure Current symlink exists
            current_link = versions_dir / "Current"
            if not current_link.exists():
                current_link.symlink_to("A")
                self.logger.debug(f"Created Current symlink: {current_link}")

            # Create only the necessary QtWebEngineProcess symlink
            expected_helpers = version_a / "Helpers"
            expected_process = expected_helpers / "QtWebEngineProcess.app"

            if not expected_process.exists():
                expected_helpers.mkdir(parents=True, exist_ok=True)
                relative_path = os.path.relpath(process_app, expected_helpers)
                expected_process.symlink_to(relative_path)
                self.logger.debug(f"Created QtWebEngineProcess symlink: {expected_process} -> {relative_path}")

            # Create only the required framework-level Helpers symlink
            helpers_link = framework_path / "Helpers"
            if not helpers_link.exists():
                try:
                    helpers_link.symlink_to("Versions/Current/Helpers")
                    self.logger.debug(f"Created Helpers symlink: {helpers_link}")
                except Exception as e:
                    self.logger.debug(f"Failed to create Helpers symlink: {e}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to fix framework structure: {e}")
            return False


class MiniSpecBuilder:
    def __init__(self, project_root: Optional[Path] = None, config_path: str = "build_system/build_config.json"):
        self.project_root = project_root or Path.cwd()
        self.config_path = self.project_root / config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg: Dict[str, Any] = json.load(f)
        # Generated hooks directory (for pre_safe_import_module)
        self.gen_hooks_dir = self.project_root / "build" / "pyinstaller_hooks_gen"
        self.pre_safe_dir = self.gen_hooks_dir / "pre_safe_import_module"


    # ---- Public API ----
    def build(self, mode: str = "prod", profile: Dict[str, Any] = None) -> bool:
        # NOTE: Playwright browsers should be prepared BEFORE running this build
        # - In CI: release.yml handles Playwright download
        # - Locally: run `python build_system/prepare_playwright.py` first
        # The build process will only package existing browsers in third_party/ms-playwright/
        
        # Generate essential pre-safe hooks for known problematic modules
        self._ensure_pre_safe_hooks()
        self._ensure_global_sitecustomize()

        # Write spec file with profile settings
        # Always start from a clean state: remove dist/ and old spec files
        try:
            self._clean_previous_outputs()
        except Exception as e:
            print(f"[MINIBUILD] Warning: pre-clean failed: {e}")

        self._last_spec_path = self._write_spec(mode, profile)

        # Run PyInstaller
        # Use virtual environment Python if available, fallback to sys.executable
        python_executable = self._get_python_executable()
        cmd = [python_executable, "-m", "PyInstaller", str(self._last_spec_path)]

        # Note: target architecture is now set in the spec file, not as command line argument
        target_arch = os.getenv('TARGET_ARCH')
        if target_arch and platform_handler.is_macos:
            if target_arch == 'aarch64':
                print(f"[MINIBUILD] Targeting ARM64 architecture (set in spec)")
            elif target_arch == 'amd64':
                print(f"[MINIBUILD] Targeting x86_64 architecture (set in spec)")

        profile = profile or {}
        print(f"[MINIBUILD] Starting {mode} build with profile: {profile}")
        print(f"[MINIBUILD] Profile settings will be applied in spec file generation")

        # Store profile for spec generation
        self._current_profile = profile

        # Only add basic PyInstaller args that don't conflict with spec file
        extra_args = ["--noconfirm", "--clean"]

        # Debug settings (can be applied as command line arg)
        if profile.get("debug", False):
            extra_args.append("--debug=all")

        # UPX compression (can be applied as command line arg)
        if profile.get("upx_compression", False):
            extra_args.append("--upx-dir=upx")


        cmd.extend(extra_args)
        print(f"[MINIBUILD] PyInstaller command: {' '.join(cmd)}")
        env = os.environ.copy()
        py_path = str(self.gen_hooks_dir)
        env["PYTHONPATH"] = (py_path + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else ""))
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(cmd, cwd=str(self.project_root), env=env)
        if result.returncode != 0:
            print(f"[MINIBUILD] {mode.upper()} build failed with code {result.returncode}")
            return False

        # Post-build processing: Fix framework paths for all platforms
        self._fix_framework_paths()

        # Verify Playwright browsers were packaged correctly
        self._verify_packaged_playwright()

        # Verify Python shared library was packaged correctly (macOS)
        self._verify_python_shared_library()

        # Update Info.plist with URL schemes (macOS)
        self._update_info_plist_url_schemes()

        print(f"[MINIBUILD] {mode.upper()} build completed successfully with profile settings")
        return True

    def _ensure_pre_safe_hooks(self) -> None:
        """Generate essential pre-safe hooks for known problematic modules"""
        try:
            # Only generate hooks for modules that are actually used
            used_modules = self._get_used_modules()
            if not used_modules:
                return

            self.pre_safe_dir.mkdir(parents=True, exist_ok=True)
            tmpl = (
                "# Auto-generated by minibuild_core: pre-safe import hook for {mod}\n"
                "def pre_safe_import_module(api):\n"
                "    import sys, argparse\n"
                "    try:\n"
                "        # Patch argparse to avoid argv side-effects during PyInstaller analysis\n"
                "        _orig_parse_args = argparse.ArgumentParser.parse_args\n"
                "        _orig_parse_known_args = argparse.ArgumentParser.parse_known_args\n"
                "        def _safe_parse_args(self, args=None, namespace=None):\n"
                "            return _orig_parse_args(self, args=[], namespace=namespace)\n"
                "        def _safe_parse_known_args(self, args=None, namespace=None):\n"
                "            return _orig_parse_known_args(self, args=[], namespace=namespace)\n"
                "        argparse.ArgumentParser.parse_args = _safe_parse_args\n"
                "        argparse.ArgumentParser.parse_known_args = _safe_parse_known_args\n"
                "    except Exception:\n"
                "        pass\n"
            )

            # Generate hooks only for modules that need them
            essential_modules = {"lightrag", "lightrag.api", "jaraco.text", "jaraco.functools"}
            for mod in essential_modules:
                if mod in used_modules:
                    (self.pre_safe_dir / f"hook-{mod}.py").write_text(tmpl.format(mod=mod), encoding="utf-8")

        except Exception as e:
            print(f"[MINIBUILD] Warning: Failed to generate pre-safe hooks: {e}")

    def _ensure_global_sitecustomize(self) -> None:
        """Ensure a sitecustomize.py that patches argparse globally for isolated child processes."""
        try:
            self.gen_hooks_dir.mkdir(parents=True, exist_ok=True)
            sc = self.gen_hooks_dir / "sitecustomize.py"
            content = (
                "# Auto-generated by minibuild_core: global sitecustomize for PyInstaller isolated child\n"
                "import sys, os, argparse\n"
                "try:\n"
                "    # Only patch when running PyInstaller's isolated child (_child.py)\n"
                "    if hasattr(sys, 'argv') and len(sys.argv) > 0:\n"
                "        prog = os.path.basename(sys.argv[0]).lower()\n"
                "        if prog.endswith('_child.py'):\n"
                "            _orig_parse_args = argparse.ArgumentParser.parse_args\n"
                "            _orig_parse_known_args = argparse.ArgumentParser.parse_known_args\n"
                "            def _safe_parse_args(self, args=None, namespace=None):\n"
                "                return _orig_parse_args(self, args=[], namespace=namespace)\n"
                "            def _safe_parse_known_args(self, args=None, namespace=None):\n"
                "                return _orig_parse_known_args(self, args=[], namespace=namespace)\n"
                "            argparse.ArgumentParser.parse_args = _safe_parse_args\n"
                "            argparse.ArgumentParser.parse_known_args = _safe_parse_known_args\n"
                "except Exception:\n"
                "    pass\n"
            )
            sc.write_text(content, encoding="utf-8")
        except Exception as e:
            print(f"[MINIBUILD] Warning: Failed to generate sitecustomize: {e}")

    def _get_used_modules(self) -> Set[str]:
        """Get modules that are actually used in the project"""
        modules = set()

        # Add modules from config
        build_config = self.cfg.get("build", {})
        pyinstaller_cfg = build_config.get("pyinstaller", {})
        modules.update(pyinstaller_cfg.get("collect_all", []))
        modules.update(pyinstaller_cfg.get("collect_data_only", []))
        modules.update(pyinstaller_cfg.get("hiddenimports", []))

        return modules

    def _get_python_executable(self) -> str:
        """Get Python executable path (prefer virtual environment)"""
        # Check for virtual environment Python
        if os.path.exists("venv"):
            if sys.platform.startswith("win"):
                venv_python = self.project_root / "venv" / "Scripts" / "python.exe"
            else:
                venv_python = self.project_root / "venv" / "bin" / "python"

            if venv_python.exists():
                print(f"[MINIBUILD] Using virtual environment Python: {venv_python}")
                return str(venv_python)
            else:
                print(f"[MINIBUILD] Virtual environment Python not found: {venv_python}")

        # Fallback to current executable
        print(f"[MINIBUILD] Using system Python: {sys.executable}")
        return sys.executable

    def _clean_previous_outputs(self) -> None:
        """Remove dist/ directory and old spec files for a fresh build every time."""
        try:
            app = self.cfg.get("app", {})
            app_name = app.get("name", "eCan")
        except Exception:
            app_name = "eCan"

        # Remove spec files for this app at project root, e.g., eCan_*.spec
        for spec in self.project_root.glob(f"{app_name}_*.spec"):
            try:
                spec.unlink()
                print(f"[MINIBUILD] Removed spec: {spec}")
            except Exception as e:
                print(f"[MINIBUILD] Warning: failed to remove spec {spec}: {e}")

        def _prepare_for_removal(target: Path) -> None:
            """Best-effort: fix permissions so shutil.rmtree can succeed."""
            try:
                if platform_handler.is_macos:
                    subprocess.run(["/bin/chmod", "-R", "u+w", str(target)], check=False)
                    subprocess.run(["/usr/bin/chflags", "-R", "nouchg", str(target)], check=False)

                for root, dirs, files in os.walk(target):
                    root_path = Path(root)
                    for name in dirs:
                        try:
                            (root_path / name).chmod(0o755)
                        except Exception:
                            pass
                    for name in files:
                        file_path = root_path / name
                        try:
                            file_path.chmod(0o644)
                            if name == "CodeResources" or "MacOS" in file_path.parts:
                                file_path.chmod(0o755)
                        except Exception:
                            pass

                if platform_handler.is_macos:
                    for cr_file in target.rglob("CodeResources"):
                        try:
                            cr_file.chmod(0o644)
                            subprocess.run(["/usr/bin/chflags", "nouchg", str(cr_file)], check=False)
                            cr_file.unlink(missing_ok=True)
                            print(f"[MINIBUILD] Removed locked file: {cr_file}")
                        except Exception:
                            pass
            except Exception:
                pass

        def _handle_remove_error(func, path, exc_info):
            try:
                Path(path).chmod(0o755)
            except Exception:
                pass
            try:
                if platform_handler.is_macos:
                    subprocess.run(["/usr/bin/chflags", "nouchg", path], check=False)
            except Exception:
                pass
            try:
                func(path)
            except Exception:
                pass

        # Remove dist directory completely (force even when macOS CodeResources is protected)
        dist_dir = self.project_root / "dist"
        if dist_dir.exists():
            try:
                _prepare_for_removal(dist_dir)
                shutil.rmtree(dist_dir, onerror=_handle_remove_error)
                print(f"[MINIBUILD] Removed dist directory: {dist_dir}")
            except Exception as e:
                print(f"[MINIBUILD] Warning: failed to remove dist {dist_dir}: {e}")

        # Remove PyInstaller build directories (e.g., build/eCan_fast)
        pyinstaller_build_root = self.project_root / "build"
        if pyinstaller_build_root.exists():
            for subdir in pyinstaller_build_root.iterdir():
                if subdir.is_dir() and subdir.name.startswith(f"{app_name}_"):
                    try:
                        _prepare_for_removal(subdir)
                        shutil.rmtree(subdir, onerror=_handle_remove_error)
                        print(f"[MINIBUILD] Removed build directory: {subdir}")
                    except Exception as e:
                        print(f"[MINIBUILD] Warning: failed to remove build dir {subdir}: {e}")

    # ---- Spec generation ----
    def _write_spec(self, mode: str, profile: Dict[str, Any] = None) -> Path:
        """Generate a simplified PyInstaller spec file"""
        profile = profile or {}

        app = self.cfg.get("app", {})
        app_name = app.get("name", "eCan")
        app_version = app.get("version", "1.0.0")
        main_script = app.get("entry_point", "main.py")

        build_config = self.cfg.get("build", {})
        mode_cfg = build_config.get("modes", {}).get(mode, {})
        # Apply profile settings to override mode defaults
        onefile = profile.get("onefile", bool(mode_cfg.get("onefile", False)))
        console_mode = profile.get("console", mode == "dev")
        debug = profile.get("debug", bool(mode_cfg.get("debug", app.get("debug", False))))

        # Get runtime_tmpdir configuration
        runtime_tmpdir = self._get_runtime_tmpdir(mode_cfg)

        # Generate spec content using template
        spec_content = self._generate_spec_template(
            app_name=app_name,
            app_version=app_version,
            main_script=main_script,
            mode=mode,
            onefile=onefile,
            console=console_mode,
            debug=debug,
            runtime_tmpdir=runtime_tmpdir,
            profile=profile
        )

        spec_path = self.project_root / f"{app_name}_{mode}.spec"
        spec_path.write_text(spec_content, encoding="utf-8")
        print(f"[MINIBUILD] Wrote spec: {spec_path}")
        return spec_path

    def _get_runtime_tmpdir(self, mode_cfg: Dict[str, Any]) -> Optional[str]:
        """Get runtime_tmpdir configuration for current platform"""
        runtime_tmpdir_cfg = mode_cfg.get("runtime_tmpdir", {})
        if not runtime_tmpdir_cfg:
            return None

        import sys
        if sys.platform.startswith('win'):
            return runtime_tmpdir_cfg.get("windows")
        elif sys.platform == 'darwin':
            return runtime_tmpdir_cfg.get("macos")
        else:
            return runtime_tmpdir_cfg.get("linux")

    def _generate_version_info_file(self, app_name: str, app_version: str) -> Optional[str]:
        """Generate Windows version info file dynamically"""
        if not sys.platform.startswith('win'):
            return None

        # Parse version string to tuple (e.g., "1.0.0" -> (1, 0, 0, 0))
        version_parts = app_version.split('.')
        while len(version_parts) < 4:
            version_parts.append('0')
        version_tuple = tuple(int(part) for part in version_parts[:4])

        # Get app info from config
        app_info = self.cfg.get("app", {})
        version_info = app_info.get("version_info", {})

        # Get version info with fallbacks to main app config
        company_name = version_info.get("company_name", app_info.get("author", "eCan.AI Team"))
        file_description = version_info.get("file_description", app_info.get("description", f"{app_name} AI Assistant"))
        product_name = version_info.get("product_name", app_info.get("description", f"{app_name} AI Assistant"))
        internal_name = version_info.get("internal_name", app_name)
        original_filename = version_info.get("original_filename", f"{app_name}.exe")
        copyright_year = version_info.get("copyright_year", "2025")
        copyright_holder = version_info.get("copyright_holder", company_name)
        language_code = version_info.get("language_code", "040904B0")
        translation = version_info.get("translation", [1033, 1200])

        # Ensure version string has 4 parts for display
        version_parts_count = len(app_version.split('.'))
        if version_parts_count < 4:
            # Add .0 for missing parts to make it 4-part version
            missing_parts = 4 - version_parts_count
            version_display = app_version + '.0' * missing_parts
        else:
            version_display = app_version

        # Generate version info content
        version_info_content = f'''# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)
    # Set not needed items to zero 0.
    filevers={version_tuple},
    prodvers={version_tuple},
    # Contains a bitmask that specifies the valid bits 'flags'r
    mask=0x3f,
    # Contains a bitmask that specifies the Boolean attributes of the file.
    flags=0x0,
    # The operating system for which this file was designed.
    # 0x4 - NT and there is no need to change it.
    OS=0x4,
    # The general type of file.
    # 0x1 - the file is an application.
    fileType=0x1,
    # The function of the file.
    # 0x0 - the function is not defined for this fileType
    subtype=0x0,
    # Creation date and time stamp.
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'{language_code}',
        [StringStruct(u'CompanyName', u'{company_name}'),
        StringStruct(u'FileDescription', u'{file_description}'),
        StringStruct(u'FileVersion', u'{version_display}'),
        StringStruct(u'InternalName', u'{internal_name}'),
        StringStruct(u'LegalCopyright', u'Copyright © {copyright_year} {copyright_holder}'),
        StringStruct(u'OriginalFilename', u'{original_filename}'),
        StringStruct(u'ProductName', u'{product_name}'),
        StringStruct(u'ProductVersion', u'{version_display}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', {translation})])
  ]
)'''

        # Write to file
        version_info_path = self.project_root / "build_system" / "version_info.txt"
        version_info_path.write_text(version_info_content, encoding='utf-8')
        print(f"[MINIBUILD] Generated version info: {version_info_path} (v{app_version})")

        return str(version_info_path)

    def _generate_spec_template(self, app_name: str, app_version: str, main_script: str,
                               mode: str, onefile: bool, console: bool, debug: bool,
                               runtime_tmpdir: Optional[str], profile: Dict[str, Any] = None) -> str:
        """Generate spec file content using a clean template approach"""

        # Generate Windows version info file dynamically
        self._generate_version_info_file(app_name, app_version)

        # Get configuration data
        hiddenimports = self._hiddenimports_from_config()
        data_files_code = self._generate_data_files_code()
        collect_packages_code = self._generate_collect_packages_code()
        excludes = self._get_excludes()

        # Icon configuration
        icons = self.cfg.get("app", {}).get("icons", {})
        icon_win = icons.get("windows", "eCan.ico")
        icon_mac = icons.get("macos", "eCan.icns")

        # Platform-specific settings
        platform_config = self._get_platform_config()

        # URL scheme configuration
        url_scheme_options = self._get_url_scheme_options()

        # Profile-based settings
        if profile is None:
            profile = {}

        strip_debug = profile.get("strip_debug", False)
        upx_compression = profile.get("upx_compression", False)

        # Target architecture configuration for macOS
        target_arch_config = ""
        target_arch = os.getenv('TARGET_ARCH')
        pyinstaller_target_arch = os.getenv('PYINSTALLER_TARGET_ARCH')

        if platform_handler.is_macos:
            # Use explicit PyInstaller target architecture if provided
            if pyinstaller_target_arch:
                target_arch_config = f"target_arch='{pyinstaller_target_arch}',"
                print(f"[SPEC] Using explicit PyInstaller target architecture: {pyinstaller_target_arch}")
            elif target_arch:
                # Map common architecture names to PyInstaller format
                if target_arch in ['aarch64', 'arm64']:
                    target_arch_config = "target_arch='arm64',"
                    print(f"[SPEC] Mapped {target_arch} to PyInstaller arm64")
                elif target_arch in ['amd64', 'x86_64']:
                    # Check if we're running on ARM64 runner
                    import platform as py_platform
                    current_arch = py_platform.machine().lower()
                    if current_arch in ['arm64', 'aarch64']:
                        # On ARM64 runner, build universal binary for amd64 compatibility
                        target_arch_config = "target_arch='universal2',"
                        print(f"[SPEC] Mapped {target_arch} to PyInstaller universal2 (ARM64 + x86_64)")
                    else:
                        target_arch_config = "target_arch='x86_64',"
                        print(f"[SPEC] Mapped {target_arch} to PyInstaller x86_64")
                else:
                    print(f"[SPEC] Unknown target architecture: {target_arch}, using default")
            else:
                # Default to current architecture if not specified
                import platform as py_platform
                current_arch = py_platform.machine().lower()
                if current_arch in ['arm64', 'aarch64']:
                    target_arch_config = "target_arch='arm64',"
                    print(f"[SPEC] Auto-detected ARM64 architecture")
                else:
                    target_arch_config = "target_arch='x86_64',"
                    print(f"[SPEC] Auto-detected x86_64 architecture")

        template = f'''# -*- mode: python ; coding: utf-8 -*-
"""
Generated PyInstaller spec for {app_name} - {mode} mode
Auto-generated by eCan build system (simplified)
"""

import sys
import os
import shutil
import subprocess
import platform as py_platform
from pathlib import Path

# Project root and basic setup
project_root = Path(r'{str(self.project_root)}')
print(f'[SPEC] Project root: {{project_root}}')

# Load configuration for plist processing
import json
config_path = project_root / 'build_system' / 'build_config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Import plist template processor
from build_system.plist_template_processor import process_info_plist_template


def _force_remove(path: Path) -> None:
    """删除已有的 app bundle，确保后续 PyInstaller 不会因权限问题失败"""
    try:
        if not path.exists():
            return

        if sys.platform == 'darwin':
            subprocess.run(["/bin/chmod", "-R", "u+w", str(path)], check=False)
            subprocess.run(["/usr/bin/chflags", "-R", "nouchg", str(path)], check=False)

            for cr_file in path.rglob('CodeResources'):
                try:
                    cr_file.chmod(0o644)
                    subprocess.run(["/usr/bin/chflags", "nouchg", str(cr_file)], check=False)
                    cr_file.unlink()
                except Exception:
                    pass

        for root, dirs, files in os.walk(path, topdown=False):
            root_path = Path(root)
            for name in files:
                try:
                    (root_path / name).chmod(0o644)
                except Exception:
                    pass
            for name in dirs:
                try:
                    (root_path / name).chmod(0o755)
                except Exception:
                    pass

        shutil.rmtree(path)
        print(f'[SPEC] Removed existing bundle: {{path}}')
    except Exception as exc:
        print(f'[SPEC] Warning: failed to remove {{path}}: {{exc}}')

try:
    from PyInstaller.building import utils as _pyi_build_utils
except Exception:
    _pyi_build_utils = None

try:
    from PyInstaller.building import osx as _pyi_osx
except Exception:
    _pyi_osx = None

# Initialize collections globally for all platforms
# These will be extended later as needed (macOS-specific handling may add items)
data_files = []
binaries = []
hiddenimports = {repr(hiddenimports)}

# Architecture validation for macOS
if sys.platform == 'darwin':
    if _pyi_build_utils is not None:
        def _safe_rmtree(target):
            try:
                _force_remove(Path(target))
            except Exception as exc:
                print(f'[SPEC] Warning: safe_rmtree fallback failed for {{target}}: {{exc}}')
        _pyi_build_utils._rmtree = _safe_rmtree
        if _pyi_osx is not None:
            _pyi_osx._rmtree = _safe_rmtree

    bundle_path = project_root / 'dist' / f'{app_name}.app'
    if bundle_path.exists():
        print(f'[SPEC] Cleaning previous bundle at {{bundle_path}}')
        _force_remove(bundle_path)

    current_arch = py_platform.machine().lower()
    target_arch = '{target_arch or "auto"}'
    print(f'[SPEC] Current architecture: {{current_arch}}')
    print(f'[SPEC] Target architecture: {{target_arch}}')

    if target_arch == 'aarch64' and current_arch in ['x86_64', 'amd64']:
        print('[SPEC] WARNING: Cross-compiling ARM64 on Intel - may cause runtime issues')
    elif target_arch == 'amd64' and current_arch in ['arm64', 'aarch64']:
        print('[SPEC] WARNING: Cross-compiling Intel on ARM64 - may cause runtime issues')

    # PyInstaller automatically includes all required stdlib C-extensions
    # No manual collection needed - let PyInstaller's dependency analysis work

    # On macOS ensure Python shared library is bundled under Frameworks/
    if sys.platform == 'darwin':
        try:
            import sys as _sys
            import sysconfig as _sc
            from pathlib import Path as _P
            
            # Get Python version
            py_ver = str(_sys.version_info.major) + '.' + str(_sys.version_info.minor)
            
            # Primary: use sysconfig to locate the shared library
            fw_prefix = _sc.get_config_var('PYTHONFRAMEWORKPREFIX') or '/Library/Frameworks'
            fw_name = _sc.get_config_var('PYTHONFRAMEWORK') or 'Python'
            python_lib = _P(fw_prefix) / f"{{fw_name}}.framework" / 'Versions' / f"{{py_ver}}" / 'Python'
            
            # Fallback candidates if primary not found
            candidates = [
                python_lib,
                _P(f"/Library/Frameworks/Python.framework/Versions/{{py_ver}}/Python"),
                _P(f"/opt/homebrew/opt/python@{{py_ver}}/Frameworks/Python.framework/Versions/{{py_ver}}/Python"),
                _P(f"/usr/local/opt/python@{{py_ver}}/Frameworks/Python.framework/Versions/{{py_ver}}/Python"),
            ]
            
            # Also check relative to sys.executable
            try:
                exe_path = _P(_sys.executable).resolve()
                for parent in exe_path.parents:
                    if parent.name == 'Versions' and parent.parent.name == 'Python.framework':
                        candidates.insert(0, parent / py_ver / 'Python')
                        break
            except Exception:
                pass
            
            # Find first existing Python shared library
            found_lib = None
            for candidate in candidates:
                if candidate.exists():
                    found_lib = candidate
                    break
            
            if found_lib:
                # Add as binary directly to Frameworks/ (use '.' to place in Contents/Frameworks/)
                # This ensures it lands at Contents/Frameworks/Python, not Contents/Frameworks/Frameworks/Python
                binaries.append((str(found_lib), '.'))
                print(f"[SPEC] Bundled Python shared library: {{found_lib}} -> Frameworks/Python")
            else:
                print(f"[SPEC] Warning: Could not locate Python shared library; tried {{len(candidates)}} paths")
                print(f"[SPEC]   Bootloader may fail if it expects Frameworks/Python")
        except Exception as _e:
            print(f"[SPEC] Warning: Failed to add Python shared library: {{_e}}")

{data_files_code}

{collect_packages_code}

# Add Playwright browsers - carefully handle symlinks to avoid conflicts
playwright_third_party = project_root / "third_party" / "ms-playwright"
if playwright_third_party.exists():
    print(f'[SPEC] Adding Playwright browsers from: {{playwright_third_party}}')
    
    # Manual walk to exclude ALL symlinks (files and directories)
    # This prevents FileExistsError with Chromium Framework structures
    import os
    pw_files = []
    skipped_symlinks = 0
    
    for root, dirs, files in os.walk(str(playwright_third_party), followlinks=False):
        # Remove symlink directories from dirs list (modifies in-place)
        # This prevents os.walk from descending into them
        original_dirs = dirs[:]
        dirs[:] = []
        for d in original_dirs:
            dir_path = os.path.join(root, d)
            if os.path.islink(dir_path):
                skipped_symlinks += 1
                continue
            dirs.append(d)
        
        # Process files, skip symlinks
        for file in files:
            src_path = os.path.join(root, file)
            if os.path.islink(src_path):
                skipped_symlinks += 1
                continue
            
            # Add as data file
            rel_path = os.path.relpath(src_path, str(playwright_third_party))
            dest_path = os.path.join('third_party/ms-playwright', rel_path)
            pw_files.append((src_path, dest_path))
    
    data_files.extend(pw_files)
    print(f'[SPEC] Added {{len(pw_files)}} Playwright files, skipped {{skipped_symlinks}} symlinks')
else:
    print('[SPEC] Playwright browsers not found in third_party')

# Icon detection with enhanced Windows support
icon_path = None
if sys.platform.startswith('win'):
    icon_candidates = [
        project_root / f'{icon_win}',
        project_root / 'resource' / 'images' / 'logos' / 'icon_multi.ico',
        project_root / 'resource' / 'icon.ico',
        project_root / 'resource' / 'eCan.ico'
    ]

    # Check if primary icon exists
    primary_icon = project_root / f'{icon_win}'
    if primary_icon.exists():
        print(f'[SPEC] Found primary icon: {{primary_icon}}')

elif sys.platform == 'darwin':
    icon_candidates = [
        project_root / f'{icon_mac}',
        project_root / 'resource' / 'icon.icns',
        project_root / 'resource' / 'eCan.icns'
    ]
else:
    icon_candidates = []

for candidate in icon_candidates:
    if candidate.exists():
        icon_path = str(candidate)
        print(f'[SPEC] Using icon: {{icon_path}}')
        break

if not icon_path:
    print('[SPEC] Warning: No icon file found')

# Analysis
a = Analysis(
    [r'{main_script}'],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=data_files,
    hiddenimports=hiddenimports,
    hookspath=[str(project_root / 'build_system' / 'pyinstaller_hooks')],
    hooksconfig={{}},
    excludes={repr(excludes)},
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
    copy_metadata=True,
    {target_arch_config}
)

# PyInstaller handles deduplication automatically during TOC processing
# Manual deduplication with dict.fromkeys() can cause issues with TOC tuples
# Only drop unwanted paths explicitly

# Drop heavy tests/examples/__pycache__ and build-related files from datas to reduce size
# Note: Do NOT include '/tests/' here as it would filter out the project's tests directory
# which is needed at runtime (gui/ipc/handlers.py imports from tests.unittests)
drop_tokens = [
    '/testing/',      # Filter third-party testing modules (e.g., pandas.testing)
    '/__pycache__/', 
    '/examples/',
    '/docs/', 
    '/.github/', 
    '/build_system/', 
    'build.py', 
    'requirements-', 
    '.gitignore', 
    '.git/',
    '/.idea/', 
    '/.vscode/', 
    '/.pytest_cache/', 
    '/.mypy_cache/',
    '/node_modules/', 
    '/.DS_Store', 
    'Thumbs.db',
]

def _should_drop_path(p):
    try:
        lp = str(p).lower().replace('\\\\\\\\', '/').replace('\\\\', '/')
        for tok in drop_tokens:
            if tok in lp:
                return True
    except Exception:
        pass
    return False

new_datas = []
dropped = 0
for item in a.datas:
    if _should_drop_path(item[0]):
        dropped += 1
        continue
    new_datas.append(item)

a.datas = new_datas
print("[SPEC] Dropped %d test/example/cache data files" % dropped)

# On macOS, we already excluded symlinks when adding Playwright browsers
# No additional filtering needed for datas since we used custom walk without followlinks
# This preserves all actual files while avoiding symlink conflicts
if sys.platform == 'darwin':
    print("[SPEC] macOS: Playwright browsers added without symlinks")

# Filter out Playwright browser binaries and Chromium Framework to prevent processing errors
# PyInstaller cannot process macOS Chromium.app binaries due to code signing
print("[SPEC] Filtering Playwright binaries and Chromium Framework...")
filtered_binaries = []
playwright_binary_count = 0
chromium_binary_count = 0

for item in a.binaries:
    binary_path = str(item[0])
    binary_path_lower = binary_path.lower()
    
    # Check if this is a Playwright browser binary
    if 'ms-playwright' in binary_path_lower and ('chromium' in binary_path_lower or 'firefox' in binary_path_lower or 'webkit' in binary_path_lower):
        playwright_binary_count += 1
        print(f"[SPEC] Skipping Playwright binary (will be included as data): {{binary_path[:80]}}...")
        continue
    
    # Also skip Chromium Framework binaries - they cause symlink conflicts
    if 'Chromium Framework.framework' in binary_path:
        chromium_binary_count += 1
        print(f"[SPEC] Skipping Chromium Framework binary: {{binary_path[:80]}}...")
        continue
        
    filtered_binaries.append(item)

a.binaries = filtered_binaries
if playwright_binary_count > 0:
    print(f"[SPEC] Filtered {{playwright_binary_count}} Playwright binaries (included as data files)")
if chromium_binary_count > 0:
    print(f"[SPEC] Filtered {{chromium_binary_count}} Chromium Framework binaries")
    
# Let PyInstaller handle binaries deduplication
# macOS-specific deduplication was incorrectly using source paths
# causing all lib-dynload .so files to be filtered except the first one

print(f"[SPEC] Final counts - Data: {{len(a.datas)}}, Binaries: {{len(a.binaries)}}")

{platform_config}

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

{self._generate_exe_config(app_name, app_version, onefile, console, debug, runtime_tmpdir, strip_debug, upx_compression, url_scheme_options, mode)}
'''
        return template
    def _generate_data_files_code(self) -> str:
        """Generate code for data files collection with symlink handling"""
        lines = []
        build_config = self.cfg.get("build", {})
        data_cfg = build_config.get("data_files", {})

        lines.append("# Data files with cross-platform processing")
        lines.append("from build_system.build_utils import process_data_files")
        lines.append("import sys")
        lines.append("")
        lines.append(f"data_files_config = {repr(data_cfg)}")
        lines.append("processed_data_files = process_data_files(data_files_config, verbose=True)")
        lines.append("")
        lines.append("for src_path, dst_path in processed_data_files:")
        lines.append("    if Path(src_path).exists():")
        lines.append("        data_files.append((src_path, dst_path))")
        lines.append("        print(f'[SPEC] Added data: {src_path} -> {dst_path}')")
        lines.append("    else:")
        lines.append("        print(f'[SPEC] Warning: Data file not found: {src_path}')")
        lines.append("")
        lines.append("# Ensure Qt WebEngine resources are included (macOS) without custom hooks")
        lines.append("if sys.platform == 'darwin':")
        lines.append("    try:")
        lines.append("        import PySide6")
        lines.append("        qt_root = Path(PySide6.__file__).parent / 'Qt'")
        lines.append("        res_dirs = [")
        lines.append("            (qt_root / 'resources', 'PySide6/Qt/resources'),")

        lines.append("            # IMPORTANT: place framework resources under Versions/A; PyInstaller will symlink Current -> A")
        lines.append("            (qt_root / 'lib' / 'QtWebEngineCore.framework' / 'Resources', 'PySide6/Qt/lib/QtWebEngineCore.framework/Versions/A/Resources'),")
        lines.append("        ]")
        lines.append("        for src_dir, dst_dir in res_dirs:")
        lines.append("            if src_dir.exists():")
        lines.append("                data_files.append((str(src_dir), dst_dir))")
        lines.append("                print(f'[SPEC] Added QtWebEngine resource dir: {src_dir} -> {dst_dir}')")
        lines.append("    except Exception as e:")
        lines.append("        print(f'[SPEC] Warning: Failed to add QtWebEngine resources: {e}')")

        return "\n".join(lines)

    def _generate_collect_packages_code(self) -> str:
        """Generate code for package collection (simplified)"""
        build_config = self.cfg.get("build", {})
        pyinstaller_cfg = build_config.get("pyinstaller", {})

        lines = []

        # Collect all packages
        collect_pkgs = pyinstaller_cfg.get("collect_all", []) or []
        if collect_pkgs:
            lines.append("from PyInstaller.utils.hooks import collect_all")
            lines.append(f"for pkg in {repr(collect_pkgs)}:")
            lines.append("    try:")
            lines.append("        d, b, h = collect_all(pkg)")
            lines.append("        data_files.extend(d)")
            lines.append("        binaries.extend(b)")
            lines.append("        # Filter out invalid hiddenimports from collect_all")
            lines.append("        valid_h = [m for m in h if isinstance(m, str) and not ('hook-' in m or '_pyinstaller' in m or '/' in m or '\\\\' in m)]")
            lines.append("        hiddenimports.extend(valid_h)")
            lines.append("        if len(h) != len(valid_h):")
            lines.append("            print(f'[SPEC] Filtered {len(h) - len(valid_h)} invalid hiddenimports from {pkg}')")
            lines.append("        print(f'[SPEC] Collected: {pkg}')")
            lines.append("    except Exception as e:")
            lines.append("        print(f'[SPEC] Warning: Failed to collect {pkg}: {e}')")

        # Collect data-only packages
        collect_data_only = pyinstaller_cfg.get("collect_data_only", []) or []
        if collect_data_only:
            lines.append("")
            lines.append("from PyInstaller.utils.hooks import collect_data_files")
            lines.append(f"for pkg in {repr(collect_data_only)}:")
            lines.append("    try:")
            lines.append("        data_files.extend(collect_data_files(pkg))")
            lines.append("        print(f'[SPEC] Collected data: {pkg}')")
            lines.append("    except Exception as e:")
            lines.append("        print(f'[SPEC] Warning: Failed to collect data for {pkg}: {e}')")

        return "\n".join(lines)

    def _get_excludes(self) -> List[str]:
        """Get excludes list from configuration"""
        build_config = self.cfg.get("build", {})
        pyinstaller_cfg = build_config.get("pyinstaller", {})
        return pyinstaller_cfg.get("excludes", [])

    def _get_platform_config(self) -> str:
        """Get platform-specific spec code snippet.
        Return empty string by default to avoid inserting a stray literal into the spec.
        """
        return ""

    def _get_url_scheme_options(self) -> str:
        """Get URL scheme PyInstaller options"""
        try:
            from build_system.url_scheme_config import URLSchemeBuildConfig
            options = URLSchemeBuildConfig.get_pyinstaller_options()

            if not options:
                return ""

            # Convert options to spec file format
            option_lines = []
            for option in options:
                if option.startswith("--osx-bundle-identifier="):
                    bundle_id = option.split("=", 1)[1]
                    option_lines.append(f"bundle_identifier='{bundle_id}',")
                # Skip info_plist option as it's already handled in the template
                # elif option.startswith("--info-plist="):
                #     plist_path = option.split("=", 1)[1]
                #     option_lines.append(f"info_plist='{plist_path}',")

            return "\n        ".join(option_lines)

        except Exception as e:
            print(f"[SPEC] Warning: URL scheme options error: {e}")
            return ""

    def _get_codesign_excludes_code(self, codesign_excludes: List[str]) -> str:
        """Generate codesign excludes code for macOS"""
        if not codesign_excludes:
            return ""

        return f'''# macOS-specific binary filtering
if sys.platform == 'darwin':
    import fnmatch
    codesign_excludes = {repr(codesign_excludes)}

    # Remove binaries that should be excluded from codesign
    filtered_binaries = []
    for binary in a.binaries:
        dest_name = str(binary[0])
        source_path = str(binary[1]) if len(binary) > 1 else ''

        should_exclude = any(
            fnmatch.fnmatch(dest_name, pattern) or fnmatch.fnmatch(source_path, pattern)
            for pattern in codesign_excludes
        )

        if not should_exclude:
            filtered_binaries.append(binary)

    removed_count = len(a.binaries) - len(filtered_binaries)
    a.binaries = filtered_binaries
    print(f"[MACOS] Excluded {{removed_count}} binaries from codesign")
'''

    def _generate_exe_config(self, app_name: str, app_version: str, onefile: bool, console: bool,
                           debug: bool, runtime_tmpdir: Optional[str], strip_debug: bool = False, upx_compression: bool = False, url_scheme_options: str = "", mode: str = "prod") -> str:
        """Generate EXE and packaging configuration"""

        if onefile:
            return f'''exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='{app_name}',
    debug={repr(debug)},
    bootloader_ignore_signals=False,
    strip=False if sys.platform.startswith('win') else {strip_debug},
    upx={upx_compression},
    runtime_tmpdir={repr(runtime_tmpdir)},
    console={repr(console)},
    icon=icon_path,
    version='build_system/version_info.txt' if sys.platform.startswith('win') else None,
    uac_admin=False,  # Disable UAC admin requirement
)'''
        else:
            return f'''exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{app_name}',
    debug={repr(debug)},
    bootloader_ignore_signals=False,
    strip=False if sys.platform.startswith('win') else {strip_debug},
    upx={upx_compression},
    runtime_tmpdir={repr(runtime_tmpdir)},
    console={repr(console)},
    icon=icon_path,
    version='build_system/version_info.txt' if sys.platform.startswith('win') else None,
    uac_admin=False,  # Disable UAC admin requirement
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False if sys.platform.startswith('win') else {strip_debug},
    upx={upx_compression},
    name='{app_name}'
)

        # macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='{app_name}.app',
        icon=icon_path,
        {url_scheme_options}
        info_plist=process_info_plist_template(project_root, config, '{app_name}', '{app_version}', '{mode}'),
    )
'''

    # ---- Helpers ----
    def _hiddenimports_from_config(self) -> List[str]:
        """Get hiddenimports from config with validation"""
        base: Set[str] = set()
        build_config = self.cfg.get("build", {})
        pyinstaller_cfg = build_config.get("pyinstaller", {})

        # Add hidden imports with validation
        for m in pyinstaller_cfg.get("hiddenimports", []) or []:
            if isinstance(m, str) and m:
                # Filter out invalid module names (hook files, paths, etc.)
                if self._is_valid_module_name(m):
                    base.add(m)
                else:
                    print(f"[SPEC] Skipping invalid hiddenimport: {m}")

        return sorted(base)

    def _is_valid_module_name(self, module_name: str) -> bool:
        """Check if a string is a valid Python module name"""
        # Skip hook files
        if "hook-" in module_name:
            return False

        # Skip file paths
        if "/" in module_name or "\\" in module_name:
            return False

        # Skip _pyinstaller internal modules
        if "_pyinstaller" in module_name:
            return False

        # Must not be empty
        if not module_name.strip():
            return False

        # Check each part separated by dots
        parts = module_name.split(".")
        for part in parts:
            if not part:  # Empty part
                return False

            # Must start with letter or underscore (not digit)
            if not (part[0].isalpha() or part[0] == '_'):
                return False

            # Must contain only alphanumeric characters and underscores
            if not part.replace("_", "").isalnum():
                return False

        return True

    def _verify_packaged_playwright(self) -> None:
        """Verify that Playwright browsers were packaged correctly"""
        try:
            print("[MINIBUILD] Verifying packaged Playwright browsers...")
            
            # Find dist directory
            dist_dir = self.project_root / "dist"
            if not dist_dir.exists():
                print("[MINIBUILD] Warning: dist directory not found")
                return
            
            # Find app bundle (macOS) or app directory (Windows/Linux)
            app_bundles = []
            if platform_handler.is_macos:
                app_bundles = list(dist_dir.glob("*.app"))
                if app_bundles:
                    # Check inside Contents/Resources or Contents/MacOS/_internal
                    app_bundle = app_bundles[0]
                    possible_paths = [
                        app_bundle / "Contents" / "Resources" / "third_party" / "ms-playwright",
                        app_bundle / "Contents" / "MacOS" / "_internal" / "third_party" / "ms-playwright"
                    ]
            else:
                # Windows/Linux: check _internal directory
                app_dirs = [d for d in dist_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
                if app_dirs:
                    app_dir = app_dirs[0]
                    possible_paths = [
                        app_dir / "_internal" / "third_party" / "ms-playwright",
                        app_dir / "third_party" / "ms-playwright"
                    ]
                else:
                    print("[MINIBUILD] Warning: No application directory found in dist/")
                    return
            
            # Check if any of the possible paths exist
            found = False
            for path in possible_paths:
                if path.exists():
                    # Check for browser directories
                    browser_dirs = [d for d in path.iterdir() 
                                   if d.is_dir() and any(browser in d.name.lower() 
                                   for browser in ['chromium', 'firefox', 'webkit'])]
                    if browser_dirs:
                        print(f"[MINIBUILD] Playwright browsers found: {path}")
                        print(f"[MINIBUILD]   Browser directories: {[d.name for d in browser_dirs]}")
                        found = True
                        break
                    else:
                        print(f"[MINIBUILD] Path exists but no browsers found: {path}")
            
            if not found:
                print("[MINIBUILD] WARNING: Playwright browsers were NOT packaged!")
                print("[MINIBUILD]   Checked paths:")
                for path in possible_paths:
                    print(f"[MINIBUILD]     - {path}: {'exists' if path.exists() else 'NOT FOUND'}")
            
        except Exception as e:
            print(f"[MINIBUILD] Warning: Playwright verification failed: {e}")
    
    def _verify_python_shared_library(self) -> None:
        """Verify that Python shared library was packaged correctly on macOS"""
        if not platform_handler.is_macos:
            return
        
        try:
            print("[MINIBUILD] Verifying Python shared library...")
            
            # Find dist directory
            dist_dir = self.project_root / "dist"
            app_bundles = list(dist_dir.glob("*.app"))
            
            if not app_bundles:
                print("[MINIBUILD] Warning: No .app bundle found in dist/")
                return
            
            app_bundle = app_bundles[0]
            frameworks_dir = app_bundle / "Contents" / "Frameworks"
            python_lib = frameworks_dir / "Python"
            
            # Check if Python library exists and is valid
            if python_lib.exists() and not python_lib.is_symlink():
                size_mb = python_lib.stat().st_size / (1024 * 1024)
                print(f"[MINIBUILD] ✓ Python shared library found: {python_lib}")
                print(f"[MINIBUILD]   Size: {size_mb:.1f} MB")
                return
            
            # Handle broken symlink or missing file
            if python_lib.is_symlink():
                target = python_lib.resolve(strict=False)
                print(f"[MINIBUILD] Found broken symlink: {python_lib} -> {target}")
                
                # Try to fix broken symlink by copying the actual file
                import sysconfig
                fw_prefix = sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX') or '/Library/Frameworks'
                fw_name = sysconfig.get_config_var('PYTHONFRAMEWORK') or 'Python'
                py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
                
                # Find the actual Python shared library
                source_candidates = [
                    Path(fw_prefix) / f"{fw_name}.framework" / "Versions" / py_ver / "Python",
                    Path(f"/Library/Frameworks/Python.framework/Versions/{py_ver}/Python"),
                    Path(f"/opt/homebrew/opt/python@{py_ver}/Frameworks/Python.framework/Versions/{py_ver}/Python"),
                    Path(f"/opt/homebrew/Cellar/python@{py_ver}") / "*" / "Frameworks" / "Python.framework" / "Versions" / py_ver / "Python"
                ]
                
                # Also try to resolve from the symlink target path
                if target.exists():
                    source_candidates.insert(0, target)
                
                # Try glob pattern for Homebrew Cellar
                import glob
                cellar_pattern = f"/opt/homebrew/Cellar/python@{py_ver}/*/Frameworks/Python.framework/Versions/{py_ver}/Python"
                cellar_matches = glob.glob(cellar_pattern)
                if cellar_matches:
                    source_candidates.insert(0, Path(cellar_matches[0]))
                
                source_lib = None
                for candidate in source_candidates:
                    if candidate.exists():
                        source_lib = candidate
                        break
                
                if source_lib:
                    print(f"[MINIBUILD] Found source Python library: {source_lib}")
                    # Remove broken symlink
                    python_lib.unlink()
                    print(f"[MINIBUILD] Removed broken symlink")
                    
                    # Copy actual file
                    import shutil
                    shutil.copy2(str(source_lib), str(python_lib))
                    size_mb = python_lib.stat().st_size / (1024 * 1024)
                    print(f"[MINIBUILD] ✓ Copied Python shared library: {python_lib} ({size_mb:.1f} MB)")
                    return
                else:
                    print(f"[MINIBUILD] ✗ Could not find source Python library to fix broken symlink")
            
            # Check if file was placed in nested Frameworks directory
            nested_python = frameworks_dir / "Frameworks" / "Python"
            if nested_python.exists():
                size_mb = nested_python.stat().st_size / (1024 * 1024)
                print(f"[MINIBUILD] Found Python library in nested location: {nested_python} ({size_mb:.1f} MB)")
                print(f"[MINIBUILD] Moving to correct location...")
                
                # Remove broken symlink if exists
                if python_lib.is_symlink() or python_lib.exists():
                    python_lib.unlink()
                    print(f"[MINIBUILD] Removed broken symlink/file")
                
                # Move file to correct location
                import shutil
                shutil.move(str(nested_python), str(python_lib))
                
                # Clean up empty nested Frameworks directory
                nested_frameworks = frameworks_dir / "Frameworks"
                if nested_frameworks.exists() and not list(nested_frameworks.iterdir()):
                    nested_frameworks.rmdir()
                    print(f"[MINIBUILD] Removed empty nested Frameworks directory")
                
                print(f"[MINIBUILD] ✓ Python shared library fixed: {python_lib} ({size_mb:.1f} MB)")
                return
            
            # Library not found anywhere
            print(f"[MINIBUILD] ✗ ERROR: Python shared library NOT FOUND")
            print(f"[MINIBUILD]   Expected at: {python_lib}")
            print(f"[MINIBUILD]   Also checked: {nested_python}")
            print(f"[MINIBUILD]   The app will fail to start with 'Failed to load Python shared library' error")
            print(f"[MINIBUILD]   Frameworks directory contents:")
            if frameworks_dir.exists():
                for item in sorted(frameworks_dir.iterdir())[:20]:
                    item_type = "symlink" if item.is_symlink() else "dir" if item.is_dir() else "file"
                    print(f"[MINIBUILD]     - {item.name} ({item_type})")
            else:
                print(f"[MINIBUILD]     (Frameworks directory does not exist)")
                
        except Exception as e:
            print(f"[MINIBUILD] Warning: Python library verification failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _verify_packaged_assets_old(self) -> None:
        """Verify that third-party assets were packaged correctly"""
        try:
            print("[MINIBUILD] Verifying packaged third-party assets...")
            
            # Find dist directory
            dist_dir = self.project_root / "dist"
            if not dist_dir.exists():
                print("[MINIBUILD] Warning: dist directory not found")
                return
            
            # Find app bundle (macOS) or app directory (Windows/Linux)
            app_bundles = []
            if platform_handler.is_macos:
                app_bundles = list(dist_dir.glob("*.app"))
                if app_bundles:
                    # Check inside Contents/Resources or Contents/MacOS/_internal
                    app_bundle = app_bundles[0]
                    possible_paths = [
                        app_bundle / "Contents" / "Resources" / "third_party" / "ms-playwright",
                        app_bundle / "Contents" / "MacOS" / "_internal" / "third_party" / "ms-playwright"
                    ]
            else:
                # Windows/Linux: check _internal directory
                app_dirs = [d for d in dist_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
                if app_dirs:
                    app_dir = app_dirs[0]
                    possible_paths = [
                        app_dir / "_internal" / "third_party" / "ms-playwright",
                        app_dir / "third_party" / "ms-playwright"
                    ]
                else:
                    print("[MINIBUILD] Warning: No application directory found in dist/")
                    return
            
            # Check if any of the possible paths exist
            found = False
            for path in possible_paths:
                if path.exists():
                    # Check for browser directories
                    browser_dirs = [d for d in path.iterdir() 
                                   if d.is_dir() and any(browser in d.name.lower() 
                                   for browser in ['chromium', 'firefox', 'webkit'])]
                    if browser_dirs:
                        print(f"[MINIBUILD] Playwright browsers found: {path}")
                        print(f"[MINIBUILD]   Browser directories: {[d.name for d in browser_dirs]}")
                        found = True
                        break
                    else:
                        print(f"[MINIBUILD] Path exists but no browsers found: {path}")
            
            if not found:
                print("[MINIBUILD] WARNING: Playwright browsers were NOT packaged!")
                print("[MINIBUILD]   This will cause runtime download on first startup (slow)")
                print("[MINIBUILD]   Checked paths:")
                for path in possible_paths:
                    print(f"[MINIBUILD]     - {path}: {'exists' if path.exists() else 'NOT FOUND'}")
            
        except Exception as e:
            print(f"[MINIBUILD] Warning: Asset verification failed: {e}")
    
    def _fix_framework_paths(self) -> None:
        """Fix Qt framework paths after PyInstaller build"""
        try:
            print("[MINIBUILD] Applying Qt framework path fixes...")

            # Use embedded Qt framework fixer

            # Find the built application bundle
            dist_dir = self.project_root / "dist"
            app_bundles = []

            # Look for .app bundles and regular directories
            if dist_dir.exists():
                for item in dist_dir.iterdir():
                    if item.is_dir():
                        app_bundles.append(item)

            if not app_bundles:
                print("[MINIBUILD] Warning: No application bundles found for framework fixes")
                return

            # Apply fixes to each bundle
            success = True
            for bundle in app_bundles:
                print(f"[MINIBUILD] Fixing Qt framework paths in: {bundle}")
                fixer = QtFrameworkFixer(bundle, verbose=False)
                if not fixer.fix_qt_webengine():
                    print(f"[MINIBUILD] Warning: Qt framework fixes failed for {bundle}")
                    success = False

            if success:
                print("[MINIBUILD] Qt framework path fixes completed successfully")
            else:
                print("[MINIBUILD] Qt framework path fixes completed with warnings")

        except Exception as e:
            print(f"[MINIBUILD] Warning: Qt framework path fixes failed: {e}")

    def _update_info_plist_url_schemes(self) -> None:
        """Update Info.plist with URL schemes from build_config.json (macOS only)"""
        if not platform_handler.is_macos:
            return
        
        try:
            print("[MINIBUILD] Updating Info.plist with URL schemes...")
            
            # Find dist directory and app bundle
            dist_dir = self.project_root / "dist"
            app_bundles = list(dist_dir.glob("*.app"))
            
            if not app_bundles:
                print("[MINIBUILD] Warning: No .app bundle found, skipping URL scheme update")
                return
            
            app_bundle = app_bundles[0]
            info_plist_path = app_bundle / "Contents" / "Info.plist"
            
            if not info_plist_path.exists():
                print(f"[MINIBUILD] Warning: Info.plist not found at {info_plist_path}")
                return
            
            # Get URL schemes from build config (use self.cfg, not self.config)
            url_schemes = self.cfg.get('installer', {}).get('macos', {}).get('url_schemes', [])
            
            if not url_schemes:
                print("[MINIBUILD] No URL schemes configured in build_config.json")
                return
            
            # Load existing Info.plist
            import plistlib
            with open(info_plist_path, 'rb') as f:
                plist_data = plistlib.load(f)
            
            # Build CFBundleURLTypes array
            url_types = []
            for scheme_config in url_schemes:
                url_type = {
                    'CFBundleURLName': scheme_config.get('name', f"{scheme_config['scheme']} URL"),
                    'CFBundleURLSchemes': [scheme_config['scheme']],
                }
                if 'role' in scheme_config:
                    url_type['CFBundleTypeRole'] = scheme_config['role']
                url_types.append(url_type)
            
            # Update plist data
            plist_data['CFBundleURLTypes'] = url_types
            
            # Write back to Info.plist
            with open(info_plist_path, 'wb') as f:
                plistlib.dump(plist_data, f)
            
            print(f"[MINIBUILD] ✓ Updated Info.plist with {len(url_types)} URL scheme(s):")
            for scheme_config in url_schemes:
                print(f"[MINIBUILD]   - {scheme_config['scheme']}:// → {scheme_config.get('name', 'URL')}")
            
        except Exception as e:
            print(f"[MINIBUILD] Warning: Info.plist URL scheme update failed: {e}")
            import traceback
            traceback.print_exc()


__all__ = ["MiniSpecBuilder"]
