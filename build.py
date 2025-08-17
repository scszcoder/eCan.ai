#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Unified Build System v9.0
Supports multiple build modes and performance optimization
"""

import sys
import os
import platform
import argparse
import subprocess
import time
from pathlib import Path


# Import unified build validator
try:
    from build_system.build_validator import BuildValidator
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False
    BuildValidator = None

# Import build utilities
from build_system.build_utils import (
    print_banner, print_mode_info, standardize_artifact_names,
    show_build_results, clean_macos_build_artifacts,
    prepare_third_party_assets, dev_sign_artifacts
)

# Import symlink manager for macOS fixes
from build_system.symlink_manager import symlink_manager


class BuildEnvironment:
    """Build environment detection and management"""

    def __init__(self, skip_precheck=False):
        self.platform = platform.system()
        self.is_windows = self.platform == "Windows"
        self.is_macos = self.platform == "Darwin"
        self.is_linux = self.platform == "Linux"
        self.is_ci = self._detect_ci_environment()
        self.skip_precheck = skip_precheck

    def _detect_ci_environment(self) -> bool:
        """Detect if running in CI environment"""
        ci_vars = ['GITHUB_ACTIONS', 'CI', 'TRAVIS', 'CIRCLECI']
        return any(os.getenv(var) for var in ci_vars)

    def validate_environment(self) -> bool:
        """Validate build environment"""
        print(f"[ENV] Platform: {self.platform}")
        print(f"[ENV] Python: {platform.python_version()}")
        print(f"[ENV] Architecture: {platform.architecture()[0]}")
        print(f"[ENV] CI Environment: {self.is_ci}")

        # Check Python version
        if not self._check_python_version():
            return False

        # Check virtual environment
        if not self._check_virtual_environment():
            return False

        # Check required files
        if not self._check_required_files():
            return False

        # Run pre-build check
        if not self._run_pre_build_check():
            return False

        return True

    def _run_pre_build_check(self) -> bool:
        """Run unified build validation"""
        if self.skip_precheck:
            print("[INFO] Skipping build validation (--skip-precheck)")
            return True

        if not VALIDATOR_AVAILABLE:
            print("[WARNING] Build validator not available, skipping")
            return True

        try:
            validator = BuildValidator(verbose=False)
            results = validator.run_full_validation()

            if results.get("overall_status") == "pass":
                print("[SUCCESS] Build validation passed")
                return True
            else:
                print("[ERROR] Build validation failed")
                validator.print_validation_report(results)
                return False

        except Exception as e:
            print(f"[ERROR] Build validation error: {e}")
            return False

    def _check_python_version(self) -> bool:
        """Check Python version"""
        version = sys.version_info
        if version.major != 3 or version.minor < 8:
            print(f"[ERROR] Python 3.8+ required, current: {version.major}.{version.minor}")
            return False
        return True

    def _check_required_files(self) -> bool:
        """Check required files"""
        required_files = [
            "main.py",
            "build_system/build_config.json"
        ]

        for file_path in required_files:
            if not Path(file_path).exists():
                print(f"[ERROR] Required file not found: {file_path}")
                return False

        return True

    def _check_virtual_environment(self) -> bool:
        """Check virtual environment"""
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            print("[SUCCESS] Virtual environment detected")
            return True
        else:
            print("[WARNING] Virtual environment directory exists but not activated")
            print("[INFO] Activating virtual environment...")
            return self._activate_virtual_environment()

    def _activate_virtual_environment(self) -> bool:
        """Activate virtual environment"""
        venv_path = Path("venv")
        if not venv_path.exists():
            print("[ERROR] Virtual environment not found")
            return False

        # Activate virtual environment on Windows
        if self.is_windows:
            activate_script = venv_path / "Scripts" / "activate.bat"
            if activate_script.exists():
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = str(venv_path / "Scripts") + os.pathsep + os.environ['PATH']
                print("[SUCCESS] Virtual environment activated")
                return True
        else:
            # Activate virtual environment on Unix systems
            activate_script = venv_path / "bin" / "activate"
            if activate_script.exists():
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = str(venv_path / "bin") + os.pathsep + os.environ['PATH']
                print("[SUCCESS] Virtual environment activated")
                return True

        print("[ERROR] Failed to activate virtual environment")
        return False





def _standardize_artifact_names(version: str, arch: str = "amd64") -> None:
    """标准化构建产物文件名以匹配 release.yml 期望的格式"""
    import shutil

    platform_name = platform.system()

    if platform_name == "Windows":
        platform_str = "windows"

        # 重命名主执行文件
        src_exe = Path("dist/eCan/eCan.exe")
        dst_exe = Path(f"dist/eCan-{platform_str}-{arch}-v{version}.exe")
        if src_exe.exists():
            try:
                shutil.copy2(src_exe, dst_exe)
                print(f"[RENAME] Created: {dst_exe.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to copy {src_exe} to {dst_exe}: {e}")

        # 重命名安装包
        src_setup = Path("dist/eCan-Setup.exe")
        dst_setup = Path(f"dist/eCan-Setup-{platform_str}-{arch}-v{version}.exe")
        if src_setup.exists():
            try:
                shutil.move(str(src_setup), str(dst_setup))
                print(f"[RENAME] Renamed: {dst_setup.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to rename {src_setup} to {dst_setup}: {e}")

    elif platform_name == "Darwin":
        platform_str = "macos"

        # 创建 DMG 文件
        app_path = Path("dist/eCan.app")
        dmg_path = Path(f"dist/eCan-{platform_str}-{arch}-v{version}.dmg")
        if app_path.exists() and not dmg_path.exists():
            try:
                # 创建临时 DMG 目录
                dmg_temp = Path("build/dmg")
                dmg_temp.mkdir(parents=True, exist_ok=True)

                # 清理并复制 app
                if (dmg_temp / "eCan.app").exists():
                    shutil.rmtree(dmg_temp / "eCan.app")
                shutil.copytree(app_path, dmg_temp / "eCan.app")

                # 创建 DMG
                cmd = [
                    "hdiutil", "create",
                    "-volname", "eCan",
                    "-srcfolder", str(dmg_temp),
                    "-ov", "-format", "UDZO",
                    str(dmg_path)
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                print(f"[RENAME] Created: {dmg_path.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to create DMG: {e}")


def _show_build_results():
    """Show build results"""
    print("\n[RESULT] Build Results:")

    dist_dir = Path("dist")
    if dist_dir.exists():
        for item in dist_dir.iterdir():
            if item.is_dir():
                size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                print(f"  folder {item.name} ({size_mb:.1f} MB)")
            elif item.is_file():
                size_mb = item.stat().st_size / (1024 * 1024)
                print(f"  file {item.name} ({size_mb:.1f} MB)")

    # Show platform-specific information
    if platform.system() == "Windows":
        exe_name = "eCan.exe"
        print(f"\n[INFO] Executable: ./dist/eCan/{exe_name}")
    elif platform.system() == "Darwin":
        exe_name = "eCan"
        print(f"\n[INFO] Executable: ./dist/eCan/{exe_name}")
    else:
        exe_name = "eCan"
        print(f"\n[INFO] Executable: ./dist/eCan/{exe_name}")

    print("\n[OK] Standard optimization features:")
    print("  - PyInstaller native optimization")
    print("  - Smart hidden imports detection")
    print("  - Exclude unnecessary modules")
    print("  - Binary compression")
    print("  - Debug info stripping")



def _clean_macos_build_artifacts(build_path: Path) -> None:
    """Clean macOS build artifacts with special handling for symlinks and frameworks"""
    import shutil
    import os

    if not build_path.exists():
        return

    print(f"[MACOS] Cleaning {build_path} with framework-aware cleanup...")

    # Special handling for frameworks and symlinks
    try:
        # First, try to remove symlinks that might cause conflicts
        for root, _, files in os.walk(build_path, topdown=False):
            root_path = Path(root)

            # Handle framework symlinks specifically
            if root_path.name.endswith('.framework'):
                for item in root_path.iterdir():
                    if item.is_symlink():
                        try:
                            item.unlink()
                            print(f"[MACOS] Removed symlink: {item}")
                        except Exception as e:
                            print(f"[MACOS] Warning: Failed to remove symlink {item}: {e}")

            # Handle other symlinks
            for file in files:
                file_path = root_path / file
                if file_path.is_symlink():
                    try:
                        file_path.unlink()
                        print(f"[MACOS] Removed symlink: {file_path}")
                    except Exception as e:
                        print(f"[MACOS] Warning: Failed to remove symlink {file_path}: {e}")

        # Now remove the directory tree
        shutil.rmtree(build_path, ignore_errors=True)

    except Exception as e:
        print(f"[MACOS] Warning: Framework cleanup failed: {e}")
        # Fallback to regular cleanup
        shutil.rmtree(build_path, ignore_errors=True)





def _prepare_third_party_assets() -> None:
    """Prepare all third-party assets using the unified manager"""
    try:
        from build_system.third_party_manager import third_party_manager, set_verbose

        # Set verbose mode (try to get from args if available)
        verbose_mode = False
        try:
            # Try to access args from the calling context
            frame = sys._getframe(1)
            if 'args' in frame.f_locals and hasattr(frame.f_locals['args'], 'verbose'):
                verbose_mode = frame.f_locals['args'].verbose
        except:
            pass

        set_verbose(verbose_mode)

        print("[THIRD-PARTY] Processing third-party components...")
        results = third_party_manager.process_all()

        success_count = sum(results.values())
        total_count = len(results)

        print(f"[THIRD-PARTY] Processed {success_count}/{total_count} components")

        if success_count < total_count:
            failed = [name for name, success in results.items() if not success]
            print(f"[THIRD-PARTY] Failed components: {failed}")

        # Fallback to original Playwright handling if needed
        if not results.get('playwright', False):
            print("[THIRD-PARTY] Falling back to original Playwright handling...")
            _prepare_playwright_assets_fallback()

    except ImportError as e:
        print(f"[THIRD-PARTY] Third-party manager not available: {e}")
        print("[THIRD-PARTY] Using fallback Playwright handling...")
        _prepare_playwright_assets_fallback()
    except Exception as e:
        print(f"[THIRD-PARTY] Error in third-party processing: {e}")
        print("[THIRD-PARTY] Using fallback Playwright handling...")
        _prepare_playwright_assets_fallback()


def _prepare_playwright_assets_fallback() -> None:
    """Fallback Playwright asset preparation"""
    try:
        from build_system.playwright.utils import build_utils

        third_party = Path.cwd() / "third_party" / "ms-playwright"

        # Prepare Playwright assets using build-time utilities
        build_utils.prepare_playwright_assets(third_party)
    except Exception as e:
        print(f"[THIRD-PARTY] Fallback Playwright preparation failed: {e}")


# Keep the old function name for compatibility
def _prepare_playwright_assets() -> None:
    """Prepare Playwright assets (compatibility wrapper)"""
    _prepare_playwright_assets_fallback()





def _dev_sign_artifacts(enable: bool) -> None:
    """Development-only local signing helper (safe no-op if not configured).
    - Windows: uses signtool with DEV_WIN_CERT_PFX and DEV_WIN_CERT_PASSWORD envs
    - macOS: uses codesign with DEV_MAC_CODESIGN_IDENTITY env
    """
    try:
        if not enable:
            return
        print("[DEV-SIGN] Local development signing enabled")
        sysname = platform.system()
        if sysname == "Windows":
            import shutil
            signtool = r"C:\\Program Files (x86)\\Windows Kits\\10\\bin\\x64\\signtool.exe"
            if not os.path.exists(signtool):
                signtool = shutil.which("signtool.exe") or shutil.which("signtool")
            pfx = os.environ.get("DEV_WIN_CERT_PFX")
            pwd = os.environ.get("DEV_WIN_CERT_PASSWORD", "")
            targets = [
                Path("dist")/"eCan"/"eCan.exe",
                Path("dist")/"eCan-Setup.exe",
            ]
            targets += list(Path("dist").glob("*.exe"))
            targets = [p for p in targets if p.exists()]
            if not signtool or not pfx:
                print("[DEV-SIGN] Windows signtool or DEV_WIN_CERT_PFX not provided; skip")
                return
            for t in targets:
                cmd = [signtool, "sign", "/fd", "SHA256", "/f", pfx]
                if pwd:
                    cmd += ["/p", pwd]
                cmd += ["/tr", "http://timestamp.digicert.com", "/td", "SHA256", str(t)]
                print(f"[DEV-SIGN] Signing {t} ...")
                try:
                    subprocess.run(cmd, check=True)
                except Exception as e:
                    print(f"[DEV-SIGN] WARN: sign failed for {t}: {e}")
        elif sysname == "Darwin":
            identity = os.environ.get("DEV_MAC_CODESIGN_IDENTITY", "").strip()
            app_path = Path("dist")/"eCan.app"
            if not identity:
                print("[DEV-SIGN] DEV_MAC_CODESIGN_IDENTITY not set; skip macOS codesign")
                return
            if not app_path.exists():
                print("[DEV-SIGN] dist/eCan.app not found; skip macOS codesign")
                return
            cmd = ["codesign", "--deep", "--force", "--sign", identity, str(app_path)]
            print(f"[DEV-SIGN] Codesigning {app_path} with identity '{identity}' ...")
            try:
                subprocess.run(cmd, check=True)
                print("[DEV-SIGN] macOS codesign done")
            except Exception as e:
                print(f"[DEV-SIGN] WARN: macOS codesign failed: {e}")
        else:
            print(f"[DEV-SIGN] Unsupported platform for dev-sign: {sysname}")
    except Exception as e:
        print(f"[DEV-SIGN] ERROR: {e}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="eCan Unified Build System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Build mode description:
  fast     Fast build (parallel+cache, 2-5 minutes)
  dev      Development build (parallel+console, 5-10 minutes)
  prod     Production build (parallel+best compression, 15-25 minutes)

Usage examples:
  python build.py fast              # Fast build
  python build.py dev               # Development build
  python build.py prod              # Production build
  python build.py prod --version 2.1.0  # Build with specified version
  python build.py fast --skip-frontend  # Fast build skipping frontend
  python build.py prod --skip-installer # Skip installer creation
  python build.py dev --dev-sign        # Dev build with local signing (if DEV_* env provided)
  python build.py --installer-only  # Create installer only (skip build steps)
""",
    )

    # Positional arguments
    parser.add_argument(
        "mode",
        choices=["fast", "dev", "prod"],
        default="fast",
        help="Build mode (default: fast)"
    )



    parser.add_argument(
        "--version", "-V",
        type=str,
        help="Specify version number (e.g.: 1.0.0, 2.1.3)"
    )

    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend build (build Python part only)"
    )

    parser.add_argument(
        "--skip-installer",
        action="store_true",
        help="Skip installer creation (generate executable only)"
    )

    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Skip build steps, create installer only (requires existing dist files)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed build information"
    )

    parser.add_argument(
        "--enable-sparkle",
        action="store_true",
        help="Enable Sparkle/winSparkle OTA update support (requires dependencies)"
    )

    parser.add_argument(
        "--verify-sparkle",
        action="store_true",
        help="Verify Sparkle/winSparkle installation before build"
    )
    # Always include Playwright browsers in the package
    parser.add_argument(
        "--skip-precheck",
        action="store_true",
        help="Skip pre-build process check"
    )

    parser.add_argument(
        "--dev-sign",
        action="store_true",
        help="Enable development signing (requires DEV_* environment variables)"
    )

    args = parser.parse_args()

    # Validate installer-only mode
    if args.installer_only:
        if args.mode != "fast":
            print("[ERROR] --installer-only mode only supports 'fast' mode")
            print("[INFO] Use: python build.py --installer-only")
            sys.exit(1)
        
        # Check if dist directory exists
        dist_dir = Path("dist")
        if not dist_dir.exists():
            print("[ERROR] --installer-only mode requires existing dist directory")
            print("[INFO] Please run a full build first, or remove --installer-only flag")
            sys.exit(1)
        
        print("[INFO] Installer-only mode: will skip build steps and create installer directly")

    # Sanitize argv to avoid third-party modules (imported later) parsing our original CLI args like 'prod'
    try:
        import sys as _sys
        if isinstance(getattr(_sys, 'argv', None), list) and len(_sys.argv) > 1:
            _sys.argv[:] = _sys.argv[:1]
    except Exception:
        pass

    # Total timer start
    overall_start = time.perf_counter()

    # Normalize console encoding to UTF-8 to avoid UnicodeEncodeError on Windows CI
    try:
        import io as _io, sys as _sys2
        if hasattr(_sys2.stdout, "reconfigure"):
            _sys2.stdout.reconfigure(encoding="utf-8", errors="replace")
            _sys2.stderr.reconfigure(encoding="utf-8", errors="replace")
        else:
            _sys2.stdout = _io.TextIOWrapper(_sys2.stdout.buffer, encoding="utf-8", errors="replace")
            _sys2.stderr = _io.TextIOWrapper(_sys2.stderr.buffer, encoding="utf-8", errors="replace")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUTF8", "1")
    except Exception:
        pass

    # Validate environment
    _t_env_start = time.perf_counter()
    env = BuildEnvironment(skip_precheck=args.skip_precheck)
    if not env.validate_environment():
        sys.exit(1)
    _t_env_end = time.perf_counter()
    print(f"[TIME] Environment validation: {(_t_env_end - _t_env_start):.2f}s")

    # Print information
    print_banner()

    # Use specified build mode
    build_mode = args.mode
    fast_mode = args.mode == "fast"

    print_mode_info(args.mode, fast_mode)

    # Pre-build cleanup (default)
    if not args.installer_only:
        print("[PREP] Cleaning build environment...")
        _t_prep_start = time.perf_counter()
        try:
            import shutil
            # Clean build outputs with enhanced symlink handling
            build_paths = [Path("dist"), Path("build")]
            try:
                from build_system.symlink_manager import symlink_manager, set_verbose
                set_verbose(args.verbose if hasattr(args, 'verbose') else False)
                symlink_manager.cleanup_build_artifacts(build_paths)
                for p in build_paths:
                    if not p.exists():  # Only print if actually cleaned
                        print(f"[PREP] Cleaned: {p}")
            except ImportError:
                # Fallback to original logic
                for p in build_paths:
                    if p.exists():
                        if platform.system() == "Darwin":
                            _clean_macos_build_artifacts(p)
                        else:
                            shutil.rmtree(p, ignore_errors=True)
                        print(f"[PREP] Cleaned: {p}")
            # Clean generated .spec files
            for spec in Path.cwd().glob("*.spec"):
                try:
                    spec.unlink()
                    print(f"[PREP] Cleaned: {spec.name}")
                except Exception as e:
                    print(f"[PREP] Warning: Failed to clean {spec}: {e}")
        except Exception as e:
            print(f"[PREP] Warning: Cleanup failed: {e}")
        _t_prep_end = time.perf_counter()
        print(f"[TIME] Prep clean: {(_t_prep_end - _t_prep_start):.2f}s")
    else:
        print("[PREP] Installer-only mode: skipping cleanup")
        print("[PREP] Using existing dist files for installer creation")

    # Use simplified MiniSpecBuilder for PyInstaller build; frontend and installer as needed
    try:
        from build_system.minibuild_core import MiniSpecBuilder
        from build_system.ecan_build import FrontendBuilder, InstallerBuilder, BuildConfig

        print(f"[BUILD] Starting {build_mode} build using MiniBuild...")
        print("=" * 60)

        env = BuildEnvironment()
        cfg = BuildConfig(Path("build_system")/"build_config.json")
        if args.version:
            cfg.update_version(args.version)
        frontend = FrontendBuilder(Path.cwd())
        installer = InstallerBuilder(cfg, env, Path.cwd(), mode=build_mode)
        minispec = MiniSpecBuilder()

        # Prepare third-party assets (including Playwright)
        if not args.installer_only:
            print("[THIRD-PARTY] Preparing third-party assets for packaging...")
            _t_tp_start = time.perf_counter()
            prepare_third_party_assets()
            _t_tp_end = time.perf_counter()
            print(f"[TIME] Third-party assets: {(_t_tp_end - _t_tp_start):.2f}s")
        else:
            print("[THIRD-PARTY] Installer-only mode: skipping third-party preparation")
        
        # On macOS, we'll use special PyInstaller options to handle codesign
        if sys.platform == "darwin":
            print("[MACOS] Using special PyInstaller options for Playwright browsers")
            print("[MACOS] Custom hooks will handle Playwright browser codesign exclusions")

            # Ensure hooks directory exists
            hooks_dir = Path("hooks")
            if not hooks_dir.exists():
                hooks_dir.mkdir()
                print("[MACOS] Created hooks directory")

            # Fix framework symlinks to prevent PyInstaller conflicts
            if not symlink_manager.fix_pyinstaller_conflicts():
                print("[MACOS] Warning: Framework symlink fix failed, but continuing with build...")
            else:
                print("[MACOS] Framework symlink fix completed successfully")
            
        # 1) Frontend
        if args.installer_only:
            print("[FRONTEND] Installer-only mode: skipping frontend build")
            print("[TIME] Frontend build: skipped")
        elif not args.skip_frontend:
            _t_front_start = time.perf_counter()
            ok_front = frontend.build()
            _t_front_end = time.perf_counter()
            print(f"[TIME] Frontend build: {(_t_front_end - _t_front_start):.2f}s")
            if not ok_front:
                print("[ERROR] Frontend build failed")
                return 1
        else:
            print("[FRONTEND] Skipped")
            print("[TIME] Frontend build: skipped")

        # 2) Core app build
        if args.installer_only:
            print("[CORE] Installer-only mode: skipping core app build")
            print("[CORE] Assuming existing dist files are ready")
            success = True
            print("[TIME] Core app build: skipped")
        else:
            _t_core_start = time.perf_counter()
            success = minispec.build(build_mode)
            _t_core_end = time.perf_counter()
            print(f"[TIME] Core app build: {(_t_core_end - _t_core_start):.2f}s")

        # 3) Installer
        if args.installer_only or (success and not args.skip_installer):
            _t_inst_start = time.perf_counter()
            ok_inst = installer.build()
            _t_inst_end = time.perf_counter()
            print(f"[TIME] Installer: {(_t_inst_end - _t_inst_start):.2f}s")
            if not ok_inst:
                print("[WARNING] Installer creation failed; continuing")
        else:
            print("[INSTALLER] Skipped")
            print("[TIME] Installer: skipped")

        # 4) macOS-specific post-build validation
        if sys.platform == "darwin" and success:
            try:
                from build_system.symlink_validator import symlink_validator
                from build_system.build_logger import build_logger

                # Get app name from config
                app_name = cfg.get_app_info().get("name", "eCan")
                app_bundle = Path("dist") / f"{app_name}.app"
                if app_bundle.exists():
                    print("[MACOS] Validating symlinks in app bundle...")
                    validation_result = symlink_validator.validate_app_bundle(app_bundle)
                    symlink_validator.print_validation_report(validation_result)

                    if validation_result["status"] == "error":
                        print("[WARNING] Symlink validation failed, but continuing...")
                else:
                    print("[WARNING] App bundle not found for symlink validation")
            except Exception as e:
                print(f"[WARNING] Symlink validation error: {e}")

        # 5) Dev-only local signing (disabled by default)
        try:
            dev_sign_artifacts(args.dev_sign)
        except Exception as _e:
            print(f"[DEV-SIGN] error: {_e}")

        if not success:
            print("\n[ERROR] Build failed!")
            return 1

        # 标准化构建产物文件名（如果指定了版本）
        if args.version and not args.installer_only:
            print("\n[RENAME] Standardizing artifact names...")
            _t_rename_start = time.perf_counter()
            try:
                # 获取架构信息（从环境变量或默认值）
                arch = os.getenv('BUILD_ARCH', 'amd64')
                standardize_artifact_names(args.version, arch)
            except Exception as e:
                print(f"[RENAME] Warning: Failed to standardize names: {e}")
            _t_rename_end = time.perf_counter()
            print(f"[TIME] Artifact renaming: {(_t_rename_end - _t_rename_start):.2f}s")

        print("\n" + "=" * 60)
        print("[SUCCESS] Build completed successfully!")
        print("=" * 60)

        # Show build results
        _t_results_start = time.perf_counter()
        show_build_results()
        _t_results_end = time.perf_counter()
        print(f"[TIME] Results reporting: {(_t_results_end - _t_results_start):.2f}s")

        _t_total_end = time.perf_counter()
        print(f"[TIME] Total build time: {(_t_total_end - overall_start):.2f}s")

        return 0

    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build failed, exit code: {e.returncode}")
        return e.returncode
    except KeyboardInterrupt:
        print("\n[WARNING] Build interrupted by user")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Build failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())