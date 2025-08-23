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
    show_build_results, prepare_third_party_assets, dev_sign_artifacts
)

# Import symlink manager for macOS fixes
from build_system.symlink_manager import symlink_manager

# Build optimizer removed - always force rebuild for reliability
from build_system.build_cleaner import BuildCleaner


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
                print("[WARNING] Build validation found issues")
                validator.print_validation_report(results)
                
                # Check if the issues are critical (blocking) or just warnings
                if self._are_validation_issues_critical(results):
                    print("[ERROR] Critical validation issues found - build blocked")
                    return False
                else:
                    print("[WARNING] Non-critical validation issues found - continuing with build")
                    return True

        except Exception as e:
            print(f"[ERROR] Build validation failed with exception: {e}")
            return False

    def _are_validation_issues_critical(self, results: dict) -> bool:
        """Determine if validation issues are critical enough to block the build"""
        # Get platform-specific issues
        platform_result = results.get("platform", {})
        platform_issues = platform_result.get("issues", [])
        
        # Check for critical issues that should block the build
        critical_patterns = [
            "Xcode Command Line Tools not installed",
            "Python.*too old",
            "Missing tool:",
            "Virtual environment not detected"
        ]
        
        # Check if any critical issues exist
        for issue in platform_issues:
            for pattern in critical_patterns:
                if pattern.lower() in issue.lower():
                    return True
        
        # Architecture mismatch on Apple Silicon is not critical
        architecture_warnings = [
            "Python binary is x86_64 - consider ARM64 native Python",
            "Python running under Rosetta 2 - consider ARM64 native Python"
        ]
        
        # If only architecture warnings exist, allow build to continue
        if platform_issues and all(any(warning.lower() in issue.lower() for warning in architecture_warnings) for issue in platform_issues):
            return False
            
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
    """Standardize build artifact names to match release.yml expected format"""
    import shutil

    platform_name = platform.system()

    # Normalize architecture names to match release.yml matrix
    if arch in ["aarch64", "arm64"]:
        arch_normalized = "aarch64"  # Use aarch64 for consistency with release.yml
    elif arch in ["amd64", "x86_64"]:
        arch_normalized = "amd64"    # Use amd64 for consistency with release.yml
    else:
        arch_normalized = arch

    print(f"[RENAME] Architecture mapping: {arch} -> {arch_normalized}")

    if platform_name == "Windows":
        platform_str = "windows"
        # Windows only supports amd64, so force it
        arch_normalized = "amd64"

        # Rename main executable
        src_exe = Path("dist/eCan/eCan.exe")
        dst_exe = Path(f"dist/eCan-{version}-{platform_str}-{arch_normalized}.exe")
        if src_exe.exists():
            try:
                shutil.copy2(src_exe, dst_exe)
                print(f"[RENAME] Created: {dst_exe.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to copy {src_exe} to {dst_exe}: {e}")

        # Rename installer package
        src_setup = Path("dist/eCan-Setup.exe")
        dst_setup = Path(f"dist/eCan-{version}-{platform_str}-{arch_normalized}-Setup.exe")
        if src_setup.exists():
            try:
                shutil.move(str(src_setup), str(dst_setup))
                print(f"[RENAME] Renamed: {dst_setup.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to rename {src_setup} to {dst_setup}: {e}")

    elif platform_name == "Darwin":
        # macOS PKG file standardization
        platform_str = "macos"

        # Standardize PKG file naming to match release.yml format
        expected_name = f"eCan-{version}-{platform_str}-{arch_normalized}.pkg"
        expected_path = Path(f"dist/{expected_name}")

        # Find .pkg files that need renaming
        pkg_files = [f for f in Path("dist").glob("*.pkg") if f.name != expected_name]

        if pkg_files:
            # Rename the first PKG file found
            src_pkg = pkg_files[0]
            try:
                shutil.move(str(src_pkg), str(expected_path))
                print(f"[RENAME] Renamed PKG: {src_pkg.name} -> {expected_name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to rename {src_pkg.name} to {expected_name}: {e}")
        else:
            print(f"[RENAME] No PKG files found to rename or already correctly named")

    elif platform_name == "Linux":
        # Linux support (future)
        platform_str = "linux"
        print(f"[RENAME] Linux artifact standardization not yet implemented")

    print(f"[RENAME] Standardization completed for {platform_str}-{arch_normalized}")


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



# macOS build artifacts cleanup is now handled by build_utils.clean_macos_build_artifacts





# Third-party asset preparation is now handled directly in build_utils.py





def _validate_macos_build_tools() -> bool:
    """Validate macOS build tools for PKG creation"""
    try:
        import shutil
        import subprocess

        # Check required tools
        required_tools = ['pkgbuild', 'productbuild']
        missing_tools = []

        for tool in required_tools:
            if not shutil.which(tool):
                missing_tools.append(tool)

        if missing_tools:
            print(f"[ERROR] Missing required macOS build tools: {', '.join(missing_tools)}")
            print("[ERROR] Please install Xcode Command Line Tools:")
            print("[ERROR]   xcode-select --install")
            return False

        # Check Xcode Command Line Tools installation
        try:
            result = subprocess.run(['xcode-select', '-p'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"[BUILD] Xcode Command Line Tools found: {result.stdout.strip()}")
            else:
                print("[WARNING] Xcode Command Line Tools may not be properly installed")
                return False
        except:
            print("[WARNING] Could not verify Xcode Command Line Tools installation")
            return False

        print("[BUILD] macOS build tools validation passed")
        return True

    except Exception as e:
        print(f"[WARNING] macOS build tools validation failed: {e}")
        return False


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
  fast     Fast build (parallel processing, 2-5 minutes) - Quick development builds
  dev      Development build (parallel+console, 5-10 minutes) - Debug-enabled builds
  prod     Production build (parallel+best compression, 15-25 minutes) - Optimized release builds

Cleanup options:
  --skip-cleanup      Skip automatic build environment cleanup
  --cleanup-only      Only perform cleanup, don't build

Usage examples:
  python build.py fast              # Fast build (with auto-cleanup)
  python build.py dev               # Development build
  python build.py prod              # Production build
  python build.py prod --version 2.1.0  # Build with specified version
  python build.py fast --skip-frontend  # Fast build skipping frontend
  python build.py prod --skip-installer # Skip installer creation
  python build.py dev --dev-sign        # Dev build with local signing (if DEV_* env provided)
  python build.py --installer-only  # Create installer only (skip build steps)
  python build.py --cleanup-only    # Only clean build environment
  python build.py fast --skip-cleanup   # Build without auto-cleanup
""",
    )

    # Positional arguments
    parser.add_argument(
        "mode",
        choices=["fast", "dev", "prod"],
        nargs="?",  # Make mode optional for cleanup-only
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

# Cache-related arguments removed - always force rebuild for reliability

    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip automatic build environment cleanup"
    )

    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Only perform cleanup, don't build"
    )

    args = parser.parse_args()

    # Validate cleanup-only mode
    if args.cleanup_only and args.mode is None:
        # For cleanup-only mode, we don't need a build mode
        pass
    elif args.mode is None:
        print("[ERROR] Build mode is required unless using --cleanup-only")
        return 1

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

    # Validate build configuration
    from build_system.build_utils import validate_build_config
    if not validate_build_config(verbose=args.verbose):
        print("[ERROR] Build configuration validation failed")
        return 1

    # Always force rebuild for reliability (cache removed)
    print(f"[BUILD] {args.mode.upper()} mode: force rebuild enabled for reliability")

    # Handle cleanup-only mode
    if args.cleanup_only:
        print("[CLEAN] Cleanup-only mode: performing build environment cleanup...")
        cleaner = BuildCleaner(verbose=args.verbose)
        cleanup_results = cleaner.clean_all()
        print(f"[CLEAN] Cleanup completed: {cleaner.get_cleanup_summary()}")
        print(f"[CLEAN] Time taken: {cleanup_results['cleanup_time']}s")
        return 0

    # Auto-clean build environment before starting (unless skipped)
    if not args.skip_cleanup:
        print("[CLEAN] Performing automatic build environment cleanup...")
        cleaner = BuildCleaner(verbose=args.verbose)
        cleanup_results = cleaner.clean_all()

        if args.verbose:
            print(f"[CLEAN] Cleanup summary: {cleaner.get_cleanup_summary()}")
        else:
            print(f"[CLEAN] Cleanup completed: freed {cleanup_results['total_size_mb']:.1f}MB, "
                  f"removed {cleanup_results['broken_symlinks']} broken symlinks")

        # Re-validate build environment after cleanup
        print("[CLEAN] Re-validating build environment after cleanup...")
        if not validate_build_config(verbose=args.verbose):
            print("[ERROR] Build environment validation failed after cleanup")
            print("[ERROR] Please check the validation output and fix any remaining issues")
            return 1

        print("[CLEAN] Build environment validation passed - ready for clean build")
    else:
        print("[CLEAN] Skipping automatic cleanup (--skip-cleanup specified)")

    # Platform-specific pre-build fixes
    import platform
    current_platform = platform.system()

    if current_platform == "Darwin":
        print("[BUILD] macOS detected - Skipping pre-build symlink fixes (PyInstaller handles this)")
        # Validate macOS build tools for PKG creation
        if not _validate_macos_build_tools():
            print("[WARNING] macOS PKG build tools validation failed")
            print("[WARNING] PKG installer creation may fail")
    elif current_platform == "Windows":
        print("[BUILD] Windows detected - No pre-build fixes needed")
    elif current_platform == "Linux":
        print("[BUILD] Linux detected - No pre-build fixes needed")
    else:
        print(f"[BUILD] Unknown platform: {current_platform} - Proceeding with default behavior")

    # Always rebuild for reliability (cache optimization removed)
    print("[BUILD] Force rebuild mode: ensuring fresh build for reliability")

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
                            from build_system.build_utils import clean_macos_build_artifacts
                            clean_macos_build_artifacts(p)
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
        
        # Platform-specific build preparation (already done in pre-build phase)
        if current_platform == "Darwin":
            print("[BUILD] macOS build preparation completed in pre-build phase")
            
        # 1) Frontend
        if args.installer_only:
            print("[FRONTEND] Installer-only mode: skipping frontend build")
            print("[TIME] Frontend build: skipped")
        elif not args.skip_frontend:
            # Always rebuild frontend for reliability
            print(f"[FRONTEND] Building frontend...")
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
            ok_front = True

        # 2) Core app build
        if args.installer_only:
            print("[CORE] Installer-only mode: skipping core app build")
            print("[CORE] Assuming existing dist files are ready")
            success = True
            print("[TIME] Core app build: skipped")
        else:
            # Always rebuild core application for reliability
            print(f"[CORE] Building core application...")
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

        # 4) Platform-specific post-build validation
        if success:
            if current_platform == "Darwin":
                try:
                    from build_system.build_utils import validate_macos_app_bundle

                    # Get app name from config
                    app_name = cfg.get_app_info().get("name", "eCan")
                    app_bundle = Path("dist") / f"{app_name}.app"
                    if app_bundle.exists():
                        print("[BUILD] macOS: Validating app bundle...")
                        validate_macos_app_bundle(app_bundle)
                    else:
                        print("[WARNING] macOS: App bundle not found for validation")

                    # Apply QtWebEngine final fix
                    print("[BUILD] macOS: Applying QtWebEngine final fix...")
                    try:
                        qtwebengine_frameworks = [
                            "dist/eCan/_internal/PySide6/Qt/lib/QtWebEngineCore.framework",
                            "dist/eCan.app/Contents/Frameworks/PySide6/Qt/lib/QtWebEngineCore.framework"
                        ]

                        for framework_path in qtwebengine_frameworks:
                            if os.path.exists(framework_path):
                                # Fix Helpers symlink
                                helpers_link = os.path.join(framework_path, "Helpers")
                                helpers_target = os.path.join(framework_path, "Versions/Main/Helpers")

                                if os.path.exists(helpers_target):
                                    # Remove existing symlink if it exists
                                    if os.path.exists(helpers_link) or os.path.islink(helpers_link):
                                        os.unlink(helpers_link)

                                    # Create new symlink
                                    os.symlink("Versions/Main/Helpers", helpers_link)
                                    print(f"[BUILD] Created Helpers symlink: {os.path.basename(framework_path)}")

                                # Fix Resources - copy from Main to A
                                main_resources = os.path.join(framework_path, "Versions/Main/Resources")
                                a_resources = os.path.join(framework_path, "Versions/A/Resources")

                                if os.path.exists(main_resources) and os.path.exists(a_resources):
                                    # Check if A/Resources is missing QtWebEngine files
                                    qtwebengine_pak = os.path.join(a_resources, "qtwebengine_resources.pak")
                                    main_pak = os.path.join(main_resources, "qtwebengine_resources.pak")

                                    if os.path.exists(main_pak) and not os.path.exists(qtwebengine_pak):
                                        import subprocess
                                        # Copy all QtWebEngine resources from Main to A
                                        copy_cmd = ["cp", "-r", f"{main_resources}/", a_resources]
                                        subprocess.run(copy_cmd, check=False)
                                        print(f"[BUILD] Copied QtWebEngine resources: {os.path.basename(framework_path)}")

                        print("[BUILD] QtWebEngine final fix completed")
                    except Exception as qtwe_e:
                        print(f"[WARNING] QtWebEngine final fix failed: {qtwe_e}")

                except Exception as e:
                    print(f"[WARNING] macOS: App bundle validation failed: {e}")
            elif current_platform == "Windows":
                # Windows-specific validation
                app_name = cfg.get_app_info().get("name", "eCan")
                exe_path = Path("dist") / f"{app_name}.exe"
                if exe_path.exists():
                    print(f"[BUILD] Windows: Executable created successfully ({exe_path})")
                else:
                    print("[WARNING] Windows: Executable not found")
            elif current_platform == "Linux":
                # Linux-specific validation
                app_name = cfg.get_app_info().get("name", "eCan")
                exe_path = Path("dist") / app_name
                if exe_path.exists():
                    print(f"[BUILD] Linux: Executable created successfully ({exe_path})")
                else:
                    print("[WARNING] Linux: Executable not found")

        # 5) Dev-only local signing (disabled by default)
        try:
            dev_sign_artifacts(args.dev_sign)
        except Exception as _e:
            print(f"[DEV-SIGN] error: {_e}")

        if not success:
            print("\n[ERROR] Build failed!")
            return 1

        # Standardize build artifact names (if version specified)
        if args.version and not args.installer_only:
            print("\n[RENAME] Standardizing artifact names...")
            _t_rename_start = time.perf_counter()
            try:
                # Get architecture info (from environment variable or default)
                # Check both BUILD_ARCH and TARGET_ARCH for compatibility
                arch = os.getenv('BUILD_ARCH') or os.getenv('TARGET_ARCH', 'amd64')
                print(f"[RENAME] Using architecture: {arch}")
                print(f"[RENAME] Environment variables:")
                print(f"  BUILD_ARCH: {os.getenv('BUILD_ARCH', 'not set')}")
                print(f"  TARGET_ARCH: {os.getenv('TARGET_ARCH', 'not set')}")
                print(f"  PYINSTALLER_TARGET_ARCH: {os.getenv('PYINSTALLER_TARGET_ARCH', 'not set')}")
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