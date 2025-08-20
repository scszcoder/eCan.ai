#!/usr/bin/env python3
"""
Framework Symlink Manager
Simple framework symlink handling for macOS builds
"""

import os
import platform
import shutil
from pathlib import Path
from typing import List, Optional


class FrameworkManager:
    """Simple framework symlink manager for macOS"""

    # Common framework symlink names
    COMMON_SYMLINKS = ["Resources", "Headers", "Modules", "Helpers", "Current"]

    # Default search paths
    DEFAULT_SEARCH_PATHS = ["third_party", "venv/lib"]

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.is_macos = platform.system() == "Darwin"

    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose"""
        if self.verbose:
            print(f"[{level}] {message}")

    def fix_prebuild_frameworks(self, search_paths: Optional[List[str]] = None) -> bool:
        """Fix framework symlinks before build"""
        if not self.is_macos:
            return True

        paths = search_paths or self.DEFAULT_SEARCH_PATHS
        self.log("Fixing pre-build frameworks...")

        try:
            for path_str in paths:
                self._process_path(Path(path_str))
            return True
        except Exception as e:
            self.log(f"Pre-build fix failed: {e}", "ERROR")
            return False

    def fix_postbuild_frameworks(self, dist_path: str = "dist") -> bool:
        """Fix frameworks after build"""
        if not self.is_macos:
            return True

        dist_dir = Path(dist_path)
        if not dist_dir.exists():
            return True

        self.log("Optimizing post-build frameworks...")

        try:
            self._process_path(dist_dir)
            # Auto-repair any damaged symlinks in the build
            self._auto_repair_symlinks(dist_dir)
            # Fix framework version symlinks
            self._fix_framework_version_symlinks(dist_dir)
            self.log("Post-build optimization completed successfully")
            return True
        except Exception as e:
            self.log(f"Post-build optimization failed: {e}", "ERROR")
            return False

    def _process_path(self, path: Path) -> None:
        """Process all frameworks in a path"""
        if not path.exists():
            return

        frameworks = list(path.rglob("*.framework"))
        for framework in frameworks:
            self._fix_framework(framework)

    def _fix_framework(self, framework_path: Path) -> None:
        """Fix a single framework (skip Qt frameworks)"""
        if not framework_path.exists():
            return

        name = framework_path.name

        # Skip Qt/PySide6 frameworks - let PyInstaller handle them
        qt_frameworks = ["Qt", "PySide6"]
        if any(qt_name in name for qt_name in qt_frameworks):
            self.log(f"Skipping Qt framework: {name}")
            return

        # Skip frameworks in system locations
        path_str = str(framework_path)
        if any(pattern in path_str for pattern in ["site-packages", "venv/lib", "_internal"]):
            self.log(f"Skipping system framework: {name}")
            return

        self.log(f"Processing custom framework: {name}")

        # Special handling for Sparkle (our own framework)
        if "sparkle" in name.lower():
            self._fix_sparkle_framework(framework_path)

        # Fix common symlinks only for our own frameworks
        for symlink_name in self.COMMON_SYMLINKS:
            symlink_path = framework_path / symlink_name
            if symlink_path.is_symlink():
                self._resolve_symlink(symlink_path)

    def _fix_sparkle_framework(self, framework_path: Path) -> None:
        """Fix Sparkle-specific issues"""
        versions_dir = framework_path / "Versions"
        if versions_dir.exists():
            shutil.rmtree(versions_dir, ignore_errors=True)
            self.log("Removed Sparkle Versions directory")

    def _resolve_symlink(self, symlink_path: Path) -> None:
        """Replace symlink with actual content"""
        try:
            target = symlink_path.readlink()
            if not target.is_absolute():
                target = (symlink_path.parent / target).resolve()

            symlink_path.unlink()

            if target.exists():
                if target.is_dir():
                    shutil.copytree(target, symlink_path, symlinks=False, dirs_exist_ok=True)
                else:
                    shutil.copy2(target, symlink_path)
            else:
                # Create empty directory for common symlinks
                if symlink_path.name in self.COMMON_SYMLINKS:
                    symlink_path.mkdir(exist_ok=True)

        except Exception as e:
            self.log(f"Failed to resolve {symlink_path.name}: {e}", "WARNING")

    def _auto_repair_symlinks(self, dist_dir: Path) -> None:
        """Auto-repair damaged symlinks in the build output"""
        self.log("Checking for damaged symlinks...")

        # Find all broken symlinks that need repair
        damaged_links = []
        for item in dist_dir.rglob("*"):
            if item.is_symlink() and not item.exists():
                # Focus on framework-related symlinks that are critical
                if ".framework" in str(item):
                    # Skip framework version symlinks - they're handled separately
                    if "QtWebEngineCore.framework" in str(item) and item.name == "Current":
                        continue
                    damaged_links.append(item)

        if not damaged_links:
            self.log("No damaged symlinks found")
            return

        self.log(f"Found {len(damaged_links)} damaged symlinks, attempting repair")

        for damaged_link in damaged_links:
            self._repair_single_symlink(damaged_link)

    def _repair_single_symlink(self, symlink_path: Path) -> None:
        """Repair a single damaged symlink by finding the correct target"""
        try:
            # Get the symlink target
            target = symlink_path.readlink()
            self.log(f"Repairing symlink: {symlink_path.name} -> {target}")

            # If it's a relative path, resolve it
            if not target.is_absolute():
                target = (symlink_path.parent / target).resolve()

            # Try to find alternative sources for the target
            if not target.exists():
                alternative_target = self._find_alternative_target(symlink_path, target)
                if alternative_target:
                    self.log(f"Found alternative target: {alternative_target}")
                    # Remove damaged symlink and create new one
                    symlink_path.unlink()
                    symlink_path.symlink_to(alternative_target.relative_to(symlink_path.parent))
                    self.log(f"Successfully repaired: {symlink_path.name}")
                    return

            self.log(f"Could not repair symlink: {symlink_path.name}", "WARNING")

        except Exception as e:
            self.log(f"Error repairing symlink {symlink_path.name}: {e}", "WARNING")

    def _find_alternative_target(self, symlink_path: Path, original_target: Path) -> Path:
        """Find alternative target for damaged symlinks"""
        framework_root = None

        # Find the framework root directory
        for parent in symlink_path.parents:
            if parent.name.endswith('.framework'):
                framework_root = parent
                break

        if not framework_root:
            return None

        # Look for alternative versions in the framework
        versions_dir = framework_root / "Versions"
        if not versions_dir.exists():
            return None

        target_name = original_target.name

        # Search in all version directories for the target
        for version_dir in versions_dir.iterdir():
            if version_dir.is_dir() and version_dir.name not in ["Current"]:
                potential_target = version_dir / target_name
                if potential_target.exists():
                    return potential_target

                # For directories, also check if we can find the content elsewhere
                if target_name in ["Helpers", "Resources"]:
                    for subdir in version_dir.iterdir():
                        if subdir.is_dir() and subdir.name == target_name:
                            return subdir

        return None

    def _fix_framework_version_symlinks(self, dist_dir: Path) -> None:
        """Fix framework version symlinks to point to correct versions"""
        self.log("Fixing framework version symlinks...")

        # Find all QtWebEngineCore.framework instances (main problematic framework)
        qtwebengine_frameworks = list(dist_dir.rglob("QtWebEngineCore.framework"))

        for framework in qtwebengine_frameworks:
            self._fix_single_framework_version_symlink(framework)

    def _fix_single_framework_version_symlink(self, framework_path: Path) -> None:
        """Fix a single framework's version symlink"""
        versions_dir = framework_path / "Versions"
        if not versions_dir.exists():
            return

        current_link = versions_dir / "Current"
        version_a = versions_dir / "A"
        version_main = versions_dir / "Main"

        # Check which version has the Helpers directory
        helpers_in_a = (version_a / "Helpers").exists() if version_a.exists() else False
        helpers_in_main = (version_main / "Helpers").exists() if version_main.exists() else False

        if helpers_in_main and not helpers_in_a:
            # Main has Helpers but A doesn't, point Current to Main
            if current_link.exists() or current_link.is_symlink():
                current_link.unlink()
            current_link.symlink_to("Main")
            self.log(f"Fixed framework version symlink to point to Main: {framework_path}")
        elif helpers_in_a:
            # A has Helpers, ensure Current points to A
            if current_link.exists() or current_link.is_symlink():
                current_link.unlink()
            current_link.symlink_to("A")
            self.log(f"Fixed framework version symlink to point to A: {framework_path}")

        # Additional fix: Create direct Helpers symlink if missing
        self._create_direct_helpers_symlink(framework_path)

        # Additional fix: Comprehensive QtWebEngine fix
        self._comprehensive_qtwebengine_fix(framework_path)

    def _create_direct_helpers_symlink(self, framework_path: Path) -> None:
        """Create direct Helpers symlink in framework root if missing"""
        try:
            # Check if this is QtWebEngineCore framework
            if "QtWebEngineCore.framework" not in str(framework_path):
                return

            direct_helpers = framework_path / "Helpers"
            versions_dir = framework_path / "Versions"

            if not versions_dir.exists():
                return

            # Find where the actual Helpers directory is
            actual_helpers = None
            for version in ["Main", "A", "Current"]:
                version_helpers = versions_dir / version / "Helpers"
                if version_helpers.exists():
                    actual_helpers = version_helpers
                    break

            if actual_helpers is None:
                self.log(f"No Helpers directory found in any version: {framework_path}")
                return

            # Create or fix the direct Helpers symlink
            if direct_helpers.exists() or direct_helpers.is_symlink():
                if direct_helpers.is_symlink():
                    # Check if symlink is correct
                    try:
                        if direct_helpers.resolve() == actual_helpers.resolve():
                            return  # Already correct
                    except Exception:
                        pass
                # Remove incorrect symlink or directory
                try:
                    if direct_helpers.is_symlink():
                        direct_helpers.unlink()
                    else:
                        import shutil
                        shutil.rmtree(direct_helpers)
                except Exception as e:
                    self.log(f"Failed to remove existing Helpers: {e}")
                    return

            # Create the symlink
            try:
                # Use relative path for the symlink
                relative_path = os.path.relpath(actual_helpers, framework_path)
                direct_helpers.symlink_to(relative_path)
                self.log(f"Created direct Helpers symlink: {framework_path}/Helpers -> {relative_path}")
            except Exception as e:
                self.log(f"Failed to create Helpers symlink: {e}")

        except Exception as e:
            self.log(f"Error in _create_direct_helpers_symlink: {e}")

    def _comprehensive_qtwebengine_fix(self, framework_path: Path) -> None:
        """Comprehensive QtWebEngine fix - solve all possible issues at once"""
        try:
            # Check if this is QtWebEngineCore framework
            if "QtWebEngineCore.framework" not in str(framework_path):
                return

            self.log(f"Comprehensive QtWebEngine fix: {framework_path}")

            # 1. Ensure directory structure
            self._ensure_qtwebengine_structure(framework_path)

            # 2. Fix all symlinks
            self._fix_qtwebengine_symlinks(framework_path)

            # 3. Copy missing files
            self._copy_qtwebengine_files(framework_path)

            # 4. Fix permissions
            self._fix_qtwebengine_permissions(framework_path)

            self.log(f"QtWebEngine comprehensive fix completed: {framework_path}")

        except Exception as e:
            self.log(f"QtWebEngine comprehensive fix failed: {e}")

    def _ensure_qtwebengine_structure(self, framework_path: Path) -> None:
        """Ensure QtWebEngine directory structure is complete"""
        versions_dir = framework_path / "Versions"

        # Ensure A and Main version directories exist
        for version in ["A", "Main"]:
            version_dir = versions_dir / version
            if not version_dir.exists():
                version_dir.mkdir(parents=True, exist_ok=True)

            # Ensure each version has Resources and Helpers directories
            for subdir in ["Resources", "Helpers"]:
                subdir_path = version_dir / subdir
                if not subdir_path.exists():
                    subdir_path.mkdir(parents=True, exist_ok=True)

    def _fix_qtwebengine_symlinks(self, framework_path: Path) -> None:
        """Fix all QtWebEngine symlinks"""
        versions_dir = framework_path / "Versions"

        # Fix Current symlink - point to version with complete content
        current_link = versions_dir / "Current"
        main_resources = versions_dir / "Main" / "Resources" / "qtwebengine_resources.pak"

        target_version = "Main" if main_resources.exists() else "A"

        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        current_link.symlink_to(target_version)

        # Fix root level symlinks
        root_symlinks = {
            "Resources": "Versions/Current/Resources",
            "Helpers": "Versions/Current/Helpers",
            "QtWebEngineCore": "Versions/Current/QtWebEngineCore"
        }

        for link_name, target in root_symlinks.items():
            link_path = framework_path / link_name

            # Check if target exists, if not find alternative
            if not (framework_path / target).exists():
                for version in ["A", "Main"]:
                    alt_target = f"Versions/{version}/{link_name}"
                    if (framework_path / alt_target).exists():
                        target = alt_target
                        break

            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()

            try:
                link_path.symlink_to(target)
            except Exception as e:
                self.log(f"Failed to create symlink {link_name}: {e}")

    def _copy_qtwebengine_files(self, framework_path: Path) -> None:
        """Copy missing QtWebEngine files"""
        versions_dir = framework_path / "Versions"
        main_dir = versions_dir / "Main"
        a_dir = versions_dir / "A"

        # Copy resources
        self._copy_qtwebengine_resources(main_dir / "Resources", a_dir / "Resources")

        # Copy helpers
        self._copy_qtwebengine_helpers(main_dir / "Helpers", a_dir / "Helpers")

        # Copy binary
        self._copy_qtwebengine_binary(main_dir / "QtWebEngineCore", a_dir / "QtWebEngineCore")

    def _copy_qtwebengine_resources(self, src_dir: Path, dst_dir: Path) -> None:
        """Copy QtWebEngine resource files"""
        if not src_dir.exists():
            return

        resource_files = [
            "qtwebengine_resources.pak",
            "qtwebengine_devtools_resources.pak",
            "qtwebengine_resources_100p.pak",
            "qtwebengine_resources_200p.pak",
            "icudtl.dat",
            "v8_context_snapshot.arm64.bin",
            "v8_context_snapshot.x86_64.bin",
            "Info.plist",
            "PrivacyInfo.xcprivacy"
        ]

        for file_name in resource_files:
            src_file = src_dir / file_name
            dst_file = dst_dir / file_name

            if src_file.exists() and not dst_file.exists():
                try:
                    import shutil
                    shutil.copy2(src_file, dst_file)
                except Exception as e:
                    self.log(f"Failed to copy {file_name}: {e}")

        # Copy locales directory
        src_locales = src_dir / "qtwebengine_locales"
        dst_locales = dst_dir / "qtwebengine_locales"
        if src_locales.exists() and not dst_locales.exists():
            try:
                import shutil
                shutil.copytree(src_locales, dst_locales)
            except Exception as e:
                self.log(f"Failed to copy locales: {e}")

    def _copy_qtwebengine_helpers(self, src_dir: Path, dst_dir: Path) -> None:
        """Copy QtWebEngine Helpers"""
        if not src_dir.exists():
            return

        if not (dst_dir / "QtWebEngineProcess.app").exists():
            try:
                import shutil
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir, symlinks=True)
            except Exception as e:
                self.log(f"Failed to copy Helpers: {e}")

    def _copy_qtwebengine_binary(self, src_file: Path, dst_file: Path) -> None:
        """Copy QtWebEngine binary file"""
        if src_file.exists() and not dst_file.exists():
            try:
                import shutil
                shutil.copy2(src_file, dst_file)
            except Exception as e:
                self.log(f"Failed to copy binary: {e}")

    def _fix_qtwebengine_permissions(self, framework_path: Path) -> None:
        """Fix QtWebEngine file permissions"""
        try:
            # Ensure executable files have execute permissions
            executables = [
                "Helpers/QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess",
                "QtWebEngineCore",
                "Versions/A/QtWebEngineCore",
                "Versions/Main/QtWebEngineCore"
            ]

            for exe_path in executables:
                exe_file = framework_path / exe_path
                if exe_file.exists():
                    import os
                    os.chmod(exe_file, 0o755)
        except Exception as e:
            self.log(f"Failed to fix permissions: {e}")

    def clean_build_artifacts(self, paths: List[str]) -> None:
        """Clean build artifacts"""
        for path_str in paths:
            path = Path(path_str)
            if path.exists():
                self.log(f"Cleaning: {path}")
                shutil.rmtree(path, ignore_errors=True)

    def safe_copy(self, src: Path, dst: Path) -> bool:
        """Safe copy with symlink resolution"""
        try:
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
            return True
        except Exception as e:
            self.log(f"Copy failed: {e}", "ERROR")
            return False


# Legacy compatibility
class SymlinkManager(FrameworkManager):
    """Legacy compatibility wrapper"""

    def fix_pyinstaller_conflicts(self) -> bool:
        """Legacy method name"""
        return self.fix_prebuild_frameworks()

    def fix_frameworks_in_dist(self, dist_path: str = "dist") -> bool:
        """Legacy method name"""
        return self.fix_postbuild_frameworks(dist_path)

    def cleanup_build_artifacts(self, build_paths: List[Path]) -> None:
        """Legacy method signature"""
        paths = [str(p) for p in build_paths]
        self.clean_build_artifacts(paths)

    def safe_copytree(self, src: Path, dst: Path, component: str = "UNKNOWN") -> bool:
        """Legacy method name"""
        return self.safe_copy(src, dst)

    def get_stats(self) -> dict:
        """Legacy method"""
        return {"platform": "macOS" if self.is_macos else "Other"}


# Global instance for backward compatibility
symlink_manager = SymlinkManager(verbose=True)
