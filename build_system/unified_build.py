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


class BuildError(Exception):
    """Unified build error class"""
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class BuildCache:
    """Intelligent build caching system with platform-aware symlink handling"""
    
    def __init__(self, project_root: Path, config: Dict[str, Any]):
        self.project_root = project_root
        self.cache_dir = project_root / ".build_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.config = config
        self.platform = platform.system()
        
        # Apply platform-specific cache overrides
        self.cache_settings = self._get_cache_settings()
        
    def _get_cache_settings(self) -> Dict[str, bool]:
        """Get platform-specific cache settings"""
        cache_config = self.config.get("cache", {})
        base_settings = {
            "enabled": cache_config.get("enabled", True),
            "frontend_cache": cache_config.get("frontend_cache", True),
            "core_cache": cache_config.get("core_cache", True),
            "dependency_cache": cache_config.get("dependency_cache", True)
        }
        
        # Apply platform overrides
        platform_overrides = cache_config.get("platform_overrides", {})
        platform_key = "macos" if self.platform == "Darwin" else "windows" if self.platform == "Windows" else "linux"
        
        if platform_key in platform_overrides:
            overrides = platform_overrides[platform_key]
            for key, value in overrides.items():
                if key != "reason" and key in base_settings:
                    base_settings[key] = value
                    if key == "core_cache" and not value:
                        print(f"[CACHE] {platform_key} core cache disabled: {overrides.get('reason', 'Platform-specific override')}")
        
        return base_settings
        
    def should_rebuild_frontend(self) -> bool:
        """Check if frontend needs rebuilding"""
        if not self.cache_settings.get("frontend_cache", True):
            return True
            
        frontend_dir = self.project_root / "gui_v2"
        dist_dir = frontend_dir / "dist"
        
        if not dist_dir.exists():
            return True
            
        # Check if source files are newer than dist
        try:
            src_files = list(frontend_dir.glob("src/**/*"))
            if not src_files:
                return False
                
            newest_src = max(f.stat().st_mtime for f in src_files if f.is_file())
            oldest_dist = min(f.stat().st_mtime for f in dist_dir.rglob("*") if f.is_file())
            
            return newest_src > oldest_dist
        except (OSError, ValueError):
            return True
    
    def should_rebuild_core(self) -> bool:
        """Check if core application needs rebuilding with symlink awareness"""
        # Always rebuild on macOS if core cache is disabled due to symlink issues
        if not self.cache_settings.get("core_cache", True):
            print("[CACHE] Core cache disabled, forcing rebuild")
            return True
            
        dist_dir = self.project_root / "dist"
        if not dist_dir.exists():
            return True
            
        # Check main Python files
        main_files = ["main.py", "app_context.py"]
        try:
            newest_main = max((self.project_root / f).stat().st_mtime 
                            for f in main_files if (self.project_root / f).exists())
            
            if self.platform == "Windows":
                exe_path = dist_dir / "eCan" / "eCan.exe"
            elif self.platform == "Darwin":
                exe_path = dist_dir / "eCan.app"
                # On macOS, also check for symlink integrity
                if exe_path.exists() and not self._validate_macos_symlinks(exe_path):
                    print("[CACHE] macOS symlink validation failed, forcing rebuild")
                    return True
            else:
                exe_path = dist_dir / "eCan"
                
            if not exe_path.exists():
                return True
                
            exe_time = exe_path.stat().st_mtime
            return newest_main > exe_time
        except (OSError, ValueError):
            return True
            
    def _validate_macos_symlinks(self, app_path: Path) -> bool:
        """Validate critical symlinks in macOS app bundle"""
        if self.platform != "Darwin":
            return True
            
        try:
            # Check for common framework symlink issues
            frameworks_dir = app_path / "Contents" / "Frameworks"
            if not frameworks_dir.exists():
                return True
                
            # Look for broken symlinks in frameworks
            for framework in frameworks_dir.glob("*.framework"):
                # Check common symlink targets
                critical_links = ["Resources", "Headers", "Modules", "Current"]
                for link_name in critical_links:
                    link_path = framework / link_name
                    if link_path.is_symlink() and not link_path.exists():
                        print(f"[CACHE] Broken symlink detected: {link_path}")
                        return False
                        
            return True
        except Exception as e:
            print(f"[CACHE] Symlink validation error: {e}")
            return False


class UnifiedBuildSystem:
    """Unified build system with intelligent caching and error handling"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.config = BuildConfig(self.project_root / "build_system" / "build_config.json")
        self.env = BuildEnvironment()
        self.validator = BuildValidator(verbose=False)
        self.cleaner = BuildCleaner(self.project_root, verbose=False)
        self.cache = BuildCache(self.project_root, self.config.config)
        
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
                "onefile": mode == "prod"
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
            print("[CLEAN] Skipping automatic cleanup")
            return
            
        print("[CLEAN] Performing automatic build environment cleanup...")
        try:
            cleanup_results = self.cleaner.clean_all()
            print(f"[CLEAN] Cleanup completed: freed {cleanup_results['total_size_mb']:.1f}MB, "
                  f"removed {cleanup_results['broken_symlinks']} broken symlinks")
        except Exception as e:
            print(f"[CLEAN] Warning: Cleanup failed: {e}")
    
    def build_frontend(self, skip_frontend: bool = False, force: bool = False) -> bool:
        """Build frontend with caching"""
        if skip_frontend:
            print("[FRONTEND] Skipped")
            return True
            
        if not force and not self.cache.should_rebuild_frontend():
            print("[FRONTEND] Up to date, skipping")
            return True
            
        print("[FRONTEND] Building frontend...")
        try:
            frontend = FrontendBuilder(self.project_root)
            return frontend.build()
        except Exception as e:
            raise BuildError(f"Frontend build failed: {e}", 1)
    
    def build_core(self, mode: str, force: bool = False) -> bool:
        """Build core application with caching and profile-based settings"""
        if not force and not self.cache.should_rebuild_core():
            print("[CORE] Up to date, skipping")
            return True
            
        profile = self.get_build_profile(mode)
        print(f"[CORE] Building core application in {mode} mode...")
        
        try:
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
            return installer.build()
        except Exception as e:
            print(f"[WARNING] Installer creation failed: {e}")
            return False
    
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
    
    def build(self, mode: str = "prod", version: str = None, **kwargs) -> int:
        """Unified build method with comprehensive error handling"""
        overall_start = time.perf_counter()
        
        try:
            # Validate build mode and get profile
            profile = self.get_build_profile(mode)
            
            # Update version if specified
            if version:
                self.config.update_version(version)
            
            # Validate environment
            self.validate_environment(kwargs.get('skip_precheck', False))
            
            # Clean environment
            self.clean_environment(kwargs.get('skip_cleanup', False))
            
            # Build components
            force_rebuild = kwargs.get('force', False)
            
            if not kwargs.get('installer_only', False):
                # Build frontend
                if not self.build_frontend(kwargs.get('skip_frontend', False), force_rebuild):
                    raise BuildError("Frontend build failed", 1)
                
                # Build core application
                if not self.build_core(mode, force_rebuild):
                    raise BuildError("Core application build failed", 1)
            
            # Build installer
            self.build_installer(mode, kwargs.get('skip_installer', False))
            
            # Standardize artifacts
            self.standardize_artifacts(version)
            
            # Show results
            show_build_results()
            
            total_time = time.perf_counter() - overall_start
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
    parser.add_argument("--force", action="store_true", help="Force rebuild all components")
    
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
        force=args.force
    )


if __name__ == "__main__":
    sys.exit(main())
