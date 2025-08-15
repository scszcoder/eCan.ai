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
from typing import Tuple

# Import pre-build check module
try:
    from build_system.pre_build_check import run_pre_build_check
    PRECHECK_AVAILABLE = True
except ImportError:
    PRECHECK_AVAILABLE = False
    run_pre_build_check = None


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
        """Run pre-build check"""
        if self.skip_precheck:
            print("[INFO] Skipping pre-build check (--skip-precheck)")
            return True

        if not PRECHECK_AVAILABLE:
            print("[WARNING] Pre-build check not available, skipping")
            return True

        if not run_pre_build_check():
            print("[ERROR] Pre-build check failed")
            print("[INFO] Please resolve the issues above before building")
            return False

        return True

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


def print_banner():
    """Print build banner"""
    print("=" * 60)
    print("eCan Unified Build System v9.0")
    print("=" * 60)

def print_mode_info(mode: str, fast: bool = False):
    """Print build mode information"""
    print(f"Build Mode: {mode.upper()}")

    if fast:
        print("[FAST] Fast Build Features:")
        print("  * Parallel compilation (multi-core CPU acceleration)")
        print("  * Smart caching (incremental build)")
        print("  * Optimized dependencies (~280 packages)")
        print("  * Debug symbols stripped")
        print("  * Estimated time: 2-5 minutes")
    elif mode == "dev":
        print("[DEV] Development Build Features:")
        print("  * Parallel compilation (multi-core CPU acceleration)")
        print("  * Console output enabled")
        print("  * Debug symbols preserved")
        print("  * Estimated time: 5-10 minutes")
    else:
        print("[PROD] Production Build Features:")
        print("  * Parallel compilation (multi-core CPU acceleration)")
        print("  * Full optimization and cleanup")
        print("  * Debug symbols stripped")
        print("  * LZMA best compression")
        print("  - Estimated time: 15-25 minutes")

    print("=" * 60)


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



def _prepare_playwright_assets() -> None:
    """Prepare Playwright assets (build-time only)"""
    from build_system.playwright.utils import build_utils
    
    third_party = Path.cwd() / "third_party" / "ms-playwright"
    
    # Prepare Playwright assets using build-time utilities
    build_utils.prepare_playwright_assets(third_party)



def _validate_macos_framework_symlinks(dist_dir: Path) -> Tuple[bool, int, int]:
    """Validate that macOS .framework leaf directories are symlinks.
    Returns (ok, checked_frameworks, fixed_issues_count)
    """
    if sys.platform != "darwin":
        return True, 0, 0
    checked = 0
    issues = 0
    try:
        # Search any .framework under the dist directory
        for fw in dist_dir.rglob("*.framework"):
            if not fw.is_dir():
                continue
            checked += 1
            versions_current = fw / "Versions" / "Current"
            for leaf in ("Headers", "Resources", "Modules", "Helpers"):
                leaf_path = fw / leaf
                if leaf_path.exists() and not leaf_path.is_symlink():
                    issues += 1
                    print(f"[VERIFY] ERROR: Framework leaf is not a symlink: {leaf_path}")
                # If leaf exists (symlink or not), verify target exists
                target = versions_current / leaf
                if leaf_path.exists() and not target.exists():
                    issues += 1
                    print(f"[VERIFY] ERROR: Framework leaf target missing: {target}")
        return issues == 0, checked, issues
    except Exception as e:
        print(f"[VERIFY] ERROR during symlink validation: {e}")
        return False, checked, issues or 1

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
""",
    )

    # Positional arguments
    parser.add_argument(
        "mode",
        choices=["fast", "dev", "prod"],
        default="fast",
        nargs="?",
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

    args = parser.parse_args()

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
    print("[PREP] Cleaning build environment...")
    _t_prep_start = time.perf_counter()
    try:
        import shutil
        # Clean build outputs
        for p in [Path("dist"), Path("build")]:
            if p.exists():
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

    # 使用更简洁的 MiniSpecBuilder 直接进行 PyInstaller 构建；前端与安装包按需执行
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

        # Prepare Playwright browsers for packaging (always)
        print("[PLAYWRIGHT] Preparing Playwright browsers for packaging...")
        _t_pw_start = time.perf_counter()
        _prepare_playwright_assets()
        _t_pw_end = time.perf_counter()
        print(f"[TIME] Playwright assets: {(_t_pw_end - _t_pw_start):.2f}s")
        
        # On macOS, we'll use special PyInstaller options to handle codesign
        if sys.platform == "darwin":
            print("[MACOS] Using special PyInstaller options for Playwright browsers")
            print("[MACOS] Custom hooks will handle Playwright browser codesign exclusions")
            
            # Ensure hooks directory exists
            hooks_dir = Path("hooks")
            if not hooks_dir.exists():
                hooks_dir.mkdir()
                print("[MACOS] Created hooks directory")
            
            # Set environment variable so PyInstaller uses our hooks
            os.environ['PYINSTALLER_HOOKS_PATH'] = str(hooks_dir.absolute())
            print(f"[MACOS] Set PYINSTALLER_HOOKS_PATH to: {hooks_dir.absolute()}")

        # 1) Frontend
        if not args.skip_frontend:
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
        _t_core_start = time.perf_counter()
        success = minispec.build(build_mode)
        _t_core_end = time.perf_counter()
        print(f"[TIME] Core app build: {(_t_core_end - _t_core_start):.2f}s")

        # 3) Installer
        if success and not args.skip_installer:
            _t_inst_start = time.perf_counter()
            ok_inst = installer.build()
            _t_inst_end = time.perf_counter()
            print(f"[TIME] Installer: {(_t_inst_end - _t_inst_start):.2f}s")
            if not ok_inst:
                print("[WARNING] Installer creation failed; continuing")
        else:
            print("[INSTALLER] Skipped")
            print("[TIME] Installer: skipped")

        # 4) Dev-only local signing (disabled by default)
        try:
            _dev_sign_artifacts(getattr(args, 'dev_sign', False))
        except Exception as _e:
            print(f"[DEV-SIGN] error: {_e}")

        if not success:
            print("\n[ERROR] Build failed!")
            return 1

        # Post-build macOS symlink validation
        if sys.platform == "darwin":
            dist_root = Path.cwd() / "dist"
            ok_syms, fw_count, issue_count = _validate_macos_framework_symlinks(dist_root)
            print(f"[VERIFY] macOS frameworks checked: {fw_count}, issues: {issue_count}")
            if not ok_syms:
                print("[ERROR] Symlink validation failed. See errors above.")
                return 1

        print("\n" + "=" * 60)
        print("[SUCCESS] Build completed successfully!")
        print("=" * 60)

        # Show build results
        _t_results_start = time.perf_counter()
        _show_build_results()
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