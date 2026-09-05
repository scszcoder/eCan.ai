#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Build System for eCan
Consolidates build entry points and improves architecture.
Supports dual-app: --app=cn | intl | both
"""

import os
import sys
import time
import platform
from pathlib import Path
from typing import Dict, Any, Optional

# Import existing components
from build_system.build_validator import BuildValidator
from build_system.build_cleaner import BuildCleaner
from build_system.build_utils import standardize_artifact_names, show_build_results
from build_system.ecan_build import BuildConfig, BuildEnvironment, FrontendBuilder, InstallerBuilder, WABaileysBridgeBuilder
from build_system.minibuild_core import MiniSpecBuilder
from build_system.url_scheme_config import URLSchemeBuildConfig
from build_system.signing_manager import create_signing_manager, create_ota_signing_manager

# Note: do NOT import utils.app_config_loader at module level. It transitively
# touches config.app_info via utils.constants at import time, prints paths,
# and (depending on the env) creates appdata directories. None of that
# belongs in a CI build process — keep the import local to the helpers that
# actually need it (see `_get_build_config_path` below).

APP_CHOICES = ['intl', 'cn', 'both']


class BuildError(Exception):
    """Unified build error class"""
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


## BuildCache removed: always rebuild logic simplified for clarity


def _get_build_config_path(project_root: Path, app_id: str) -> Path:
    """Determine config path: per-app config if exists, otherwise fallback to shared.

    Thin wrapper around utils.app_config_loader.get_build_config_path that
    exists only to keep the project's existing call sites (`config_path =
    _get_build_config_path(self.project_root, app_id)`) intact; the real
    resolution lives in app_config_loader.

    The import is local (not at module level) so importing `unified_build`
    doesn't pull utils.app_config_loader transitively at startup — keeping
    the module-level build import surface clean of runtime config singletons.
    """
    from utils.app_config_loader import get_build_config_path
    del project_root  # get_build_config_path uses PROJECT_ROOT internally.
    return get_build_config_path(app_id)


class UnifiedBuildSystem:
    """Unified build orchestrator with validation, cleanup, build, packaging, and reporting.

    Supports multi-app via --app parameter (cn / intl / both).
    """

    def __init__(self, project_root: Optional[Path] = None, app_id: str = None):
        self.project_root = project_root or Path.cwd()
        # Resolve app_id via utils.app_config_loader (falls back to ECAN_APP_ID
        # env var internally, so no try/except is needed here).
        from utils.app_config_loader import AppConfigLoader
        app_id = app_id or AppConfigLoader().app_id
        config_path = _get_build_config_path(self.project_root, app_id)
        self.config = BuildConfig(config_path)
        self.env = BuildEnvironment()
        self.validator = BuildValidator(verbose=False)
        self.cleaner = BuildCleaner(self.project_root, verbose=False)
        self.app_id = app_id

    def get_build_profile(self, mode: str) -> Dict[str, Any]:
        """Get build profile settings for the specified mode"""
        profiles = self.config.config.get("build_profiles", {})
        profile = profiles.get(mode, {})
        
        if not profile:
            print(f"[WARNING] No profile found for mode '{mode}', using defaults")
            # Fallback to basic settings
            profile = {
                "optimization": "balanced",
                "debug": mode == "dev",
                "console": mode == "dev",
                "compression": mode == "prod",
                "upx_compression": False,
                "strip_debug": mode == "prod",
                "onefile": False  # Always create app bundles on macOS, not single executables
            }
        
        print(f"[PROFILE] Using '{mode}' profile: {profile}")
        return profile
        
    def validate_environment(self, skip_precheck: bool = False) -> None:
        """Validate build environment with unified error handling"""
        if skip_precheck:
            print("[INFO] Skipping build validation (--skip-precheck)")
            return
            
        try:
            results = self.validator.run_full_validation()
            if results.get("overall_status") != "pass":
                # Check if issues are critical
                platform_issues = results.get("platform", {}).get("issues", [])
                critical_patterns = [
                    "Xcode Command Line Tools not installed",
                    "Python.*too old",
                    "Missing tool:",
                    "Virtual environment not detected"
                ]
                
                is_critical = any(
                    any(pattern.lower() in issue.lower() for pattern in critical_patterns)
                    for issue in platform_issues
                )
                
                if is_critical:
                    raise BuildError("Critical validation issues found", 1)
                else:
                    print("[WARNING] Non-critical validation issues found - continuing")
        except Exception as e:
            if isinstance(e, BuildError):
                raise
            raise BuildError(f"Build validation failed: {e}", 1)
    
    def clean_environment(self, skip_cleanup: bool = False) -> None:
        """Clean build environment"""
        if skip_cleanup:
            print("[CLEAN] Skipped")
            return
            
        try:
            results = self.cleaner.clean_all()
            print(f"[CLEAN] Freed {results['total_size_mb']:.1f}MB, removed {results['broken_symlinks']} broken symlinks")
        except Exception as e:
            print(f"[CLEAN] Warning: Cleanup failed: {e}")
    
    def prepare_third_party_assets(self) -> None:
        """Prepare third-party assets (Playwright browsers)"""
        print("[THIRD-PARTY] Preparing third-party assets...")

        # Check if Playwright browsers already exist (from CI cache or previous install)
        playwright_dir = self.project_root / "third_party" / "ms-playwright"
        if playwright_dir.exists():
            browser_dirs = [d for d in playwright_dir.iterdir()
                           if d.is_dir() and any(b in d.name.lower()
                           for b in ['chromium', 'firefox', 'webkit'])]
            if browser_dirs:
                # Validate browser installation completeness using the build-only
                # helper from build_system.build_utils. We deliberately avoid
                # agent.playwright.core.utils here — that runtime module pulls
                # in utils.logger_helper → colorlog as a side effect, which has
                # no place in a CI build step. If the validation itself fails
                # (corrupt cache, incomplete install), we delete the cache and
                # let the standard download path below take over.
                from build_system.build_utils import validate_browser_installation
                try:
                    if validate_browser_installation(playwright_dir):
                        print(f"[THIRD-PARTY] Playwright browsers already present and valid: {playwright_dir}")
                        print(f"[THIRD-PARTY]   Found: {[d.name for d in browser_dirs]}")
                        print("[THIRD-PARTY] Skipping download (using existing browsers)")
                        return
                except Exception as validation_err:
                    print(f"[THIRD-PARTY] WARNING: Existing browsers at {playwright_dir} are incomplete or invalid: {validation_err}")
                    print("[THIRD-PARTY]   Will re-download browsers...")
                    import shutil
                    shutil.rmtree(playwright_dir, ignore_errors=True)

        try:
            from build_system.build_utils import prepare_third_party_assets
            prepare_third_party_assets()
            print("[THIRD-PARTY] Third-party assets prepared successfully")
        except Exception as e:
            print(f"[THIRD-PARTY] Warning: Failed to prepare third-party assets: {e}")
            print("[THIRD-PARTY]   This may cause issues with browser automation features")
            # Don't fail the build, just warn
    
    def build_frontend(self, skip_frontend: bool = False) -> bool:
        """Build frontend with caching optimization"""
        if skip_frontend:
            print("[FRONTEND] Skipped")
            return True
        
        # Quick cache check
        if self._can_skip_frontend_build():
            print("[FRONTEND] Using cached build (no changes detected)")
            return True
            
        print("[FRONTEND] Building frontend...")
        try:
            frontend = FrontendBuilder(self.project_root, app_id=self.app_id)
            return frontend.build()
        except Exception as e:
            raise BuildError(f"Frontend build failed: {e}", 1)
    
    def _can_skip_frontend_build(self) -> bool:
        """Check if frontend build can be skipped"""
        try:
            frontend_dir = self.project_root / "gui_v2"
            if not frontend_dir.exists():
                return True
            
            dist_dir = frontend_dir / "dist"
            if not dist_dir.exists() or not any(dist_dir.iterdir()):
                return False
            
            # Check if source files are newer than dist
            source_files = [
                frontend_dir / "package.json",
                frontend_dir / "package-lock.json",
            ]
            
            # Check for vite config (both .js and .ts)
            for config_file in [frontend_dir / "vite.config.js", frontend_dir / "vite.config.ts"]:
                if config_file.exists():
                    source_files.append(config_file)
            
            src_dir = frontend_dir / "src"
            if src_dir.exists():
                source_files.extend(src_dir.rglob("*.[jt]s"))
                source_files.extend(src_dir.rglob("*.[jt]sx"))
                source_files.extend(src_dir.rglob("*.vue"))
                source_files.extend(src_dir.rglob("*.css"))
            
            # Get the newest source file time
            newest_source = 0
            for f in source_files:
                if f.exists() and f.is_file():
                    newest_source = max(newest_source, f.stat().st_mtime)
            
            # Get the oldest dist file time
            oldest_dist = float('inf')
            for f in dist_dir.rglob("*"):
                if f.is_file():
                    oldest_dist = min(oldest_dist, f.stat().st_mtime)
            
            # If dist is newer than source, we can skip
            return oldest_dist > newest_source
            
        except Exception:
            return False
    
    def setup_url_scheme(self) -> bool:
        """Validate the Windows URL scheme before building."""
        print("[URL-SCHEME] Setting up URL scheme configuration...")
        try:
            if not platform_handler.is_windows:
                return True

            success = URLSchemeBuildConfig._setup_windows_build()
            if success:
                print("[URL-SCHEME] URL scheme configuration ready")
            else:
                print("[URL-SCHEME] Warning: URL scheme setup failed")
            return success
        except Exception as e:
            print(f"[URL-SCHEME] Warning: URL scheme setup error: {e}")
            return False
    
    def build_core(self, mode: str) -> bool:
        """Build core application (always build)"""
        profile = self.get_build_profile(mode)
        print(f"[CORE] Building core application in {mode} mode...")
        try:
            # Setup URL scheme configuration before building
            self.setup_url_scheme()
            
            # Check if this is Linux platform
            if platform.system() == "Linux":
                return self.build_linux(mode)

            # Pass merged config to MiniSpecBuilder so it uses per-app settings
            minispec = MiniSpecBuilder(app_config=self.config.config)
            # Apply profile settings to the build
            return minispec.build(mode, profile)
        except Exception as e:
            raise BuildError(f"Core build failed: {e}", 1)

    def build_wabaileys_bridge(self) -> None:
        """Copy the pre-built wa_bridge binary into the app bundle.

        The binary is produced by GitHub Actions (setup-wabaileys-bridge action)
        and placed at wabaileys-bridge/dist/.  This method only copies it to the
        correct location inside the app bundle.
        """
        print("[WA-BRIDGE] Copying wa_bridge binary into app bundle...")
        try:
            bridge = WABaileysBridgeBuilder(self.project_root)
            ok = bridge.build(skip=True)
            if not ok:
                print("[WA-BRIDGE] [WARNING] Bridge binary not found – skipping")
        except Exception as e:
            print(f"[WA-BRIDGE] [WARNING] Bridge copy error: {e} – continuing")

    def build_linux(self, mode: str, formats: Optional[list] = None, parallel: bool = True) -> bool:
        """Build Linux packages (PyInstaller + AppImage + DEB)
        
        Args:
            mode: Build mode (dev, prod, fast)
            formats: List of formats to build. If None, read from config.
            parallel: Enable parallel building of packages (default: True)
        """
        print(f"[LINUX] Building Linux packages in {mode} mode...")
        try:
            from build_system.linux_builder import LinuxBuilder
            
            # Create Linux builder
            builder = LinuxBuilder(self.project_root, self.config.config)
            
            # Determine which formats to build
            if formats is None:
                linux_config = self.config.config.get("platforms", {}).get("linux", {})
                formats = []
                if linux_config.get("appimage", {}).get("enabled", False):
                    formats.append("appimage")
                if linux_config.get("deb", {}).get("enabled", False):
                    formats.append("deb")
            
            # Build all formats with parallel support
            results = builder.build_all(mode, formats, parallel=parallel)
            
            # Check if PyInstaller build succeeded (required)
            if not results.get("pyinstaller", False):
                raise BuildError("Linux PyInstaller build failed", 1)
            
            # Package builds are optional - warn if they fail
            for format_name, success in results.items():
                if format_name != "pyinstaller" and not success:
                    print(f"[WARNING] {format_name} package creation failed")
            
            return True
            
        except Exception as e:
            raise BuildError(f"Linux build failed: {e}", 1)
    
    def build_installer(self, mode: str, skip_installer: bool = False) -> bool:
        """Build installer package"""
        if skip_installer:
            print("[INSTALLER] Skipped")
            return True
        
        # Linux packages are built in build_linux(), skip installer step
        if platform.system() == "Linux":
            print("[INSTALLER] Linux packages already created in build step")
            return True
            
        print("[INSTALLER] Creating installer package...")
        try:
            installer = InstallerBuilder(self.config, self.env, self.project_root, mode)
            success = installer.build()
            if not success:
                raise BuildError("Installer creation failed", 1)
            return True
        except BuildError:
            raise
        except Exception as e:
            raise BuildError(f"Installer creation raised an unexpected error: {e}", 1)
    
    def test_installer(self) -> bool:
        """Test the created installer package"""
        print("\n[TEST] Testing installer package...")
        try:
            # Find the most recent PKG file
            pkg_files = list(self.project_root.glob("dist/*.pkg"))
            if not pkg_files:
                print("[TEST] No PKG files found to test")
                return False
            
            # Get the most recent PKG file
            latest_pkg = max(pkg_files, key=lambda p: p.stat().st_mtime)
            print(f"[TEST] Testing PKG: {latest_pkg.name}")
            
            # Import and run the PKG tester
            import sys
            sys.path.insert(0, str(self.project_root / "build_system"))
            
            try:
                from test_pkg_installer import PKGInstallerTester
                tester = PKGInstallerTester(latest_pkg)
                results = tester.run_all_tests()
                
                # Check if all tests passed
                failed_count = sum(1 for r in results.values() if r["status"] in ["FAIL", "ERROR"])
                if failed_count == 0:
                    print("[TEST] All installer tests passed")
                    return True
                else:
                    print(f"[TEST] [ERROR] {failed_count} installer test(s) failed")
                    return False
                    
            finally:
                sys.path.pop(0)
                
        except Exception as e:
            print(f"[TEST] Installer testing failed: {e}")
            return False

    def sign_artifacts(self, mode: str = "prod", version: str = None) -> bool:
        """Sign build artifacts"""
        print("\n[SIGN] Starting artifact code signing...")
        
        try:
            # Create code signing manager
            signing_manager = create_signing_manager(self.project_root, self.config.config)
            
            # Perform code signing
            code_sign_success = signing_manager.sign_artifacts(mode)
            
            # Verify signatures
            if code_sign_success:
                signing_manager.verify_signatures()
            
            # Note: OTA signing moved to after installer creation
            # See: sign_ota_artifacts() method called after build_installer()
            
            print("[SIGN] Signing workflow completed")
            return True
            
        except Exception as e:
            error_msg = str(e)
            # Check if this is an OTA signing failure in non-dev environment
            if "OTA signing failed in non-dev environment" in error_msg:
                print(f"[SIGN] [ERROR] {error_msg}")
                return False  # Block build for OTA signing failures in test/staging/production
            else:
                print(f"[SIGN] [WARNING] Error during signing process: {e}")
                # Other signing failures should not block the overall build
                return True
    
    def sign_ota_artifacts(self, version: str) -> bool:
        """Sign OTA artifacts (must be called AFTER installer creation)"""
        if not version:
            return True
            
        print("\n[OTA-SIGN] Starting OTA artifact signing...")
        
        try:
            ota_signing_manager = create_ota_signing_manager(self.project_root)
            ota_sign_success = ota_signing_manager.sign_for_ota(version)
            
            if ota_sign_success:
                print("[OTA-SIGN] [OK] OTA signing completed")
                return True
            else:
                # OTA signing is REQUIRED for test/staging/production environments
                # Only dev/development environment can skip OTA signing
                environment = os.getenv('ECAN_ENVIRONMENT', 'dev').lower()
                # Normalize environment names
                if environment == 'development':
                    environment = 'dev'
                
                if environment in ['test', 'staging', 'production']:
                    print("[OTA-SIGN] [ERROR] ========================================")
                    print("[OTA-SIGN] [ERROR] OTA signing REQUIRED for test/staging/production environments")
                    print(f"[OTA-SIGN] [ERROR] Current environment: {environment}")
                    print("[OTA-SIGN] [ERROR] Please ensure Ed25519 private key exists at:")
                    print(f"[OTA-SIGN] [ERROR]   build_system/certificates/ed25519_private_key.pem")
                    print("[OTA-SIGN] [ERROR] ========================================")
                    raise Exception("OTA signing failed in non-dev environment")
                else:
                    print(f"[OTA-SIGN] [WARNING] OTA signing failed in {environment} environment, continuing build")
                    return True
                    
        except Exception as e:
            error_msg = str(e)
            if "OTA signing failed in non-dev environment" in error_msg:
                print(f"[OTA-SIGN] [ERROR] {error_msg}")
                return False
            else:
                print(f"[OTA-SIGN] [WARNING] Error during OTA signing: {e}")
                return True
    
    def standardize_artifacts(self, version: str) -> None:
        """Standardize artifact names"""
        if not version:
            return

        print("\n[RENAME] Standardizing artifact names...")
        try:
            # Get architecture from environment or auto-detect
            arch = os.getenv('BUILD_ARCH') or os.getenv('TARGET_ARCH')
            if not arch:
                current_machine = platform.machine().lower()
                if current_machine in ['arm64', 'aarch64']:
                    arch = 'aarch64'
                elif current_machine in ['x86_64', 'amd64']:
                    arch = 'amd64'
                else:
                    arch = 'amd64'
                print(f"[RENAME] Auto-detected architecture: {arch}")
            else:
                print(f"[RENAME] Using environment architecture: {arch}")

            # Use the per-app short name from the build config so the renamed
            # artifacts land in dist/ under the same name that release.yml's
            # upload steps look for (which uses $ECAN_APP_NAME / $DIST_APP).
            app_short_name = self.config.config.get("app", {}).get("name", "eCan")

            standardize_artifact_names(version, arch, app_short_name)
        except Exception as e:
            print(f"[RENAME] Warning: Failed to standardize names: {e}")
    
    def _show_build_timing(self, build_times: Dict[str, float], total_time: float):
        """Show detailed build timing breakdown"""
        print("\n" + "=" * 50)
        print("BUILD TIMING BREAKDOWN")
        print("=" * 50)
        
        # Sort stages by time (longest first)
        sorted_stages = sorted(build_times.items(), key=lambda x: x[1], reverse=True)
        
        for stage, duration in sorted_stages:
            percentage = (duration / total_time) * 100
            stage_name = stage.replace('_', ' ').title()
            
            # Add visual bar
            bar_length = int(percentage / 5)  # Scale to 20 chars max
            bar = "#" * bar_length + "-" * (20 - bar_length)
            
            print(f"{stage_name:12} | {bar} | {duration:6.2f}s ({percentage:5.1f}%)")
        
        print("=" * 50)
        print(f"{'Total':12} | {'#' * 20} | {total_time:6.2f}s (100.0%)")
        print("=" * 50)
    
    def build(self, mode: str = "prod", version: str = None, **kwargs) -> int:
        """Unified build method with comprehensive error handling"""
        overall_start = time.perf_counter()
        build_times = {}  # Track individual stage times
        
        try:
            # Validate build mode (profile will be computed in build_core)
            
            # Update version if specified
            if version:
                self.config.update_version(version)
            
            # Validate environment
            stage_start = time.perf_counter()
            self.validate_environment(kwargs.get('skip_precheck', False))
            build_times['validation'] = time.perf_counter() - stage_start
            
            # Clean environment
            stage_start = time.perf_counter()
            self.clean_environment(kwargs.get('skip_cleanup', False))
            build_times['cleanup'] = time.perf_counter() - stage_start
            
            # Build components
            if not kwargs.get('installer_only', False):
                # Build frontend
                stage_start = time.perf_counter()
                if not self.build_frontend(kwargs.get('skip_frontend', False)):
                    raise BuildError("Frontend build failed", 1)
                build_times['frontend'] = time.perf_counter() - stage_start
                
                # Prepare third-party assets (Playwright browsers) before core build
                stage_start = time.perf_counter()
                self.prepare_third_party_assets()
                build_times['third_party_assets'] = time.perf_counter() - stage_start
                
                # Build core application
                stage_start = time.perf_counter()
                if not self.build_core(mode):
                    raise BuildError("Core application build failed", 1)
                build_times['core'] = time.perf_counter() - stage_start

                # Build WhatsApp Baileys Bridge (must run after core so the app bundle exists)
                if not kwargs.get('skip_wa_bridge', False):
                    stage_start = time.perf_counter()
                    self.build_wabaileys_bridge()
                    build_times['wabaileys_bridge'] = time.perf_counter() - stage_start
                else:
                    print("[WA-BRIDGE] Skipped (--skip-wa-bridge)")
            
            # Code signing
            if not kwargs.get('skip_signing', False):
                stage_start = time.perf_counter()
                self.sign_artifacts(mode, version)
                build_times['signing'] = time.perf_counter() - stage_start
            
            # Build installer
            stage_start = time.perf_counter()
            self.build_installer(mode, kwargs.get('skip_installer', False))
            build_times['installer'] = time.perf_counter() - stage_start
            
            # OTA signing (MUST be after installer creation)
            if not kwargs.get('skip_installer', False):
                stage_start = time.perf_counter()
                if not self.sign_ota_artifacts(version):
                    raise BuildError("OTA signing failed in non-dev environment", 1)
                build_times['ota_signing'] = time.perf_counter() - stage_start
            
            # Test installer if requested
            if kwargs.get('test_installer', False) and not kwargs.get('skip_installer', False):
                stage_start = time.perf_counter()
                self.test_installer()
                build_times['testing'] = time.perf_counter() - stage_start
            
            # Standardize artifacts
            stage_start = time.perf_counter()
            self.standardize_artifacts(version)
            build_times['standardize'] = time.perf_counter() - stage_start

            # Show results
            show_build_results()
            
            total_time = time.perf_counter() - overall_start
            
            # Show detailed timing breakdown
            self._show_build_timing(build_times, total_time)
            
            print(f"\n[SUCCESS] Build completed successfully in {total_time:.2f}s")
            return 0
            
        except BuildError as e:
            print(f"\n[ERROR] {e}")
            return e.exit_code
        except KeyboardInterrupt:
            print("\n[WARNING] Build interrupted by user")
            return 1
        except Exception as e:
            import traceback
            print(f"\n[ERROR] Unexpected build failure: {e}")
            traceback.print_exc()
            return 1


def main():
    """Main entry point for unified build system"""
    import argparse

    parser = argparse.ArgumentParser(description="Unified eCan Build System")
    parser.add_argument("mode", choices=["fast", "dev", "prod"], default="prod", nargs="?")
    parser.add_argument("--app", choices=APP_CHOICES, default=None,
                        help="Which app to build (intl, cn, both)")
    parser.add_argument("--version", help="Version number")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend build")
    parser.add_argument("--skip-installer", action="store_true", help="Skip installer creation")
    parser.add_argument("--installer-only", action="store_true", help="Create installer only")
    parser.add_argument("--skip-precheck", action="store_true", help="Skip pre-build validation")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip environment cleanup")
    parser.add_argument("--skip-signing", action="store_true", help="Skip code signing")
    parser.add_argument("--test-installer", action="store_true", help="Test installer after creation")
    parser.add_argument("--skip-wa-bridge", action="store_true", help="Skip WhatsApp Baileys Bridge build")

    args = parser.parse_args()

    # Default to intl if no app specified
    apps_to_build = ['intl']
    if args.app == 'both':
        apps_to_build = ['cn', 'intl']
    elif args.app in ('cn', 'intl'):
        apps_to_build = [args.app]

    build_kwargs = dict(
        mode=args.mode,
        version=args.version,
        skip_frontend=args.skip_frontend,
        skip_installer=args.skip_installer,
        installer_only=args.installer_only,
        skip_precheck=args.skip_precheck,
        skip_cleanup=args.skip_cleanup,
        skip_signing=args.skip_signing,
        test_installer=args.test_installer,
        skip_wa_bridge=args.skip_wa_bridge,
    )

    exit_code = 0
    for app_id in apps_to_build:
        print(f"\n{'=' * 60}")
        print(f"Building app: {app_id}  ({args.mode} / {platform.system()})")
        print(f"{'=' * 60}")
        os.environ['ECAN_APP_ID'] = app_id
        build_system = UnifiedBuildSystem(app_id=app_id)
        code = build_system.build(**build_kwargs)
        if code != 0:
            print(f"❌ Build failed for app: {app_id}")
            exit_code = code
        else:
            print(f"✅ {app_id} built successfully")
        # Reset for next iteration
        os.environ.pop('ECAN_APP_ID', None)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
