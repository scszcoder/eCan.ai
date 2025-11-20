#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Build System for eCan
Consolidates build entry points and improves architecture
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
from build_system.ecan_build import BuildConfig, BuildEnvironment, FrontendBuilder, InstallerBuilder
from build_system.minibuild_core import MiniSpecBuilder
from build_system.build_utils import URLSchemeBuildConfig
from build_system.signing_manager import create_signing_manager, create_ota_signing_manager


class BuildError(Exception):
    """Unified build error class"""
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


## BuildCache removed: always rebuild logic simplified for clarity


class UnifiedBuildSystem:
    """Unified build orchestrator with validation, cleanup, build, packaging, and reporting"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.config = BuildConfig(self.project_root / "build_system" / "build_config.json")
        self.env = BuildEnvironment()
        self.validator = BuildValidator(verbose=False)
        self.cleaner = BuildCleaner(self.project_root, verbose=False)
        
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
                print(f"[THIRD-PARTY] Playwright browsers already present: {playwright_dir}")
                print(f"[THIRD-PARTY]   Found: {[d.name for d in browser_dirs]}")
                print("[THIRD-PARTY] Skipping download (using existing browsers)")
                return
        
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
            frontend = FrontendBuilder(self.project_root)
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
                frontend_dir / "vite.config.js"
            ]
            
            src_dir = frontend_dir / "src"
            if src_dir.exists():
                source_files.extend(src_dir.rglob("*.[jt]s"))
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
        """Setup URL scheme configuration for the build"""
        print("[URL-SCHEME] Setting up URL scheme configuration...")
        try:
            success = URLSchemeBuildConfig.setup_url_scheme_for_build()
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
            minispec = MiniSpecBuilder()
            # Apply profile settings to the build
            return minispec.build(mode, profile)
        except Exception as e:
            raise BuildError(f"Core build failed: {e}", 1)
    
    def build_installer(self, mode: str, skip_installer: bool = False) -> bool:
        """Build installer package"""
        if skip_installer:
            print("[INSTALLER] Skipped")
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
            
            # Perform OTA signing if version is provided
            if version:
                ota_signing_manager = create_ota_signing_manager(self.project_root)
                ota_sign_success = ota_signing_manager.sign_for_ota(version)
                
                if ota_sign_success:
                    print("[SIGN] [OK] OTA signing completed")
                else:
                    # OTA signing is REQUIRED for test/staging/production environments
                    # Only dev/development environment can skip OTA signing
                    # Read environment from env var (set by GitHub Actions) or default to dev
                    environment = os.getenv('ECAN_ENVIRONMENT', 'dev').lower()
                    # Normalize environment names
                    if environment == 'development':
                        environment = 'dev'
                    
                    if environment in ['test', 'staging', 'production']:
                        print("[SIGN] [ERROR] ========================================")
                        print("[SIGN] [ERROR] OTA signing REQUIRED for test/staging/production environments")
                        print(f"[SIGN] [ERROR] Current environment: {environment}")
                        print("[SIGN] [ERROR] Please ensure Ed25519 private key exists at:")
                        print(f"[SIGN] [ERROR]   build_system/certificates/ed25519_private_key.pem")
                        print("[SIGN] [ERROR] ========================================")
                        raise Exception("OTA signing failed in non-dev environment")
                    else:
                        print(f"[SIGN] [WARNING] OTA signing failed in {environment} environment, continuing build")
            
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
                
            standardize_artifact_names(version, arch)
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
            
            # Code signing
            if not kwargs.get('skip_signing', False):
                stage_start = time.perf_counter()
                self.sign_artifacts(mode, version)
                build_times['signing'] = time.perf_counter() - stage_start
            
            # Build installer
            stage_start = time.perf_counter()
            self.build_installer(mode, kwargs.get('skip_installer', False))
            build_times['installer'] = time.perf_counter() - stage_start
            
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
            print(f"\n[ERROR] Unexpected build failure: {e}")
            return 1


def main():
    """Main entry point for unified build system"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified eCan Build System")
    parser.add_argument("mode", choices=["fast", "dev", "prod"], default="prod", nargs="?")
    parser.add_argument("--version", help="Version number")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend build")
    parser.add_argument("--skip-installer", action="store_true", help="Skip installer creation")
    parser.add_argument("--installer-only", action="store_true", help="Create installer only")
    parser.add_argument("--skip-precheck", action="store_true", help="Skip pre-build validation")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip environment cleanup")
    parser.add_argument("--skip-signing", action="store_true", help="Skip code signing")
    parser.add_argument("--test-installer", action="store_true", help="Test installer after creation")
    # '--force' removed: always rebuild behavior is the default now
    
    args = parser.parse_args()
    
    build_system = UnifiedBuildSystem()
    return build_system.build(
        mode=args.mode,
        version=args.version,
        skip_frontend=args.skip_frontend,
        skip_installer=args.skip_installer,
        installer_only=args.installer_only,
        skip_precheck=args.skip_precheck,
        skip_cleanup=args.skip_cleanup,
        skip_signing=args.skip_signing,
        test_installer=args.test_installer
    )


if __name__ == "__main__":
    sys.exit(main())
