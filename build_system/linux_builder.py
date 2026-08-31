#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linux Builder for eCan.ai
Handles PyInstaller builds, AppImage creation, and DEB package generation
"""

import os
import sys
import shutil
import subprocess
import json
import time
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from build_system.build_utils import process_data_files


class LinuxBuilder:
    """Linux-specific build and packaging functionality"""
    
    def __init__(self, project_root: Path, config: Dict[str, Any]):
        self.project_root = project_root
        self.config = config
        self.app_name = config.get("app", {}).get("name", "eCan")
        self.version = config.get("app", {}).get("version", "1.0.0")
        self.dist_dir = project_root / "dist"
        self.build_dir = project_root / "build"

    @staticmethod
    def _sanitize_deb_version(version: str) -> str:
        """Sanitize version string for DEB package compatibility.
        
        Debian package Version field only allows: alphanumerics, dots (.),
        hyphens (-), plus (+), tildes (~), and colons (:). Underscores are
        not allowed by Debian policy.
        
        Args:
            version: Original version string (may contain underscores)
            
        Returns:
            Sanitized version string with underscores replaced by hyphens
        """
        return version.replace('_', '-')
    
    @staticmethod
    def _find_submodules_without_importing(package: str) -> List[str]:
        """Enumerate package modules without importing its subpackages.

        LightRAG's API modules parse ``sys.argv`` at import time.  PyInstaller's
        ``--collect-all`` imports package directories in an isolated child and
        therefore mistakes the child's RPC arguments for LightRAG CLI options.
        Walking the package files gives PyInstaller the same hidden-import list
        without executing those modules during collection.
        """
        spec = importlib.util.find_spec(package)
        locations = list(spec.submodule_search_locations or []) if spec else []
        modules = {package}
        for location in locations:
            root = Path(location)
            for source in root.rglob("*.py"):
                relative = source.relative_to(root)
                parts = list(relative.with_suffix("").parts)
                if parts[-1] == "__init__":
                    parts.pop()
                if parts:
                    modules.add(".".join([package, *parts]))
        return sorted(modules)
        
    def build_pyinstaller(self, mode: str = "prod") -> bool:
        """
        Build Linux executable using PyInstaller
        
        Args:
            mode: Build mode (dev, prod, fast)
            
        Returns:
            bool: True if successful
        """
        print("\n" + "="*60)
        print("🐧 Building Linux Executable with PyInstaller")
        print("="*60)
        
        try:
            # Get build profile
            profile = self.config.get("build_profiles", {}).get(mode, {})
            
            # Prepare PyInstaller command
            cmd = [
                sys.executable, "-m", "PyInstaller",
                "--name", self.app_name,
                "--distpath", str(self.dist_dir),
                "--workpath", str(self.build_dir),
                "--specpath", str(self.build_dir),
            ]
            
            # Add icon if available
            icon_path = self.project_root / "resource" / "images" / "logos" / "desktop_256x256.png"
            if icon_path.exists():
                cmd.extend(["--icon", str(icon_path)])
            
            # Console mode
            if not profile.get("console", False):
                cmd.append("--noconsole")
            
            # Debug mode
            if profile.get("debug", False):
                cmd.append("--debug=all")
            
            # Hidden imports from config (build_config.json nests pyinstaller under "build")
            pyinstaller_config = self.config.get("build", {}).get("pyinstaller", {})
            for module in pyinstaller_config.get("hiddenimports", []):
                cmd.extend(["--hidden-import", module])
            
            # Collect all packages
            for package in pyinstaller_config.get("collect_all", []):
                if package == "lightrag":
                    cmd.extend(["--collect-data", package])
                    for module in self._find_submodules_without_importing(package):
                        cmd.extend(["--hidden-import", module])
                else:
                    cmd.extend(["--collect-all", package])
            
            # Collect data only packages
            for package in pyinstaller_config.get("collect_data_only", []):
                cmd.extend(["--collect-data", package])

            # Add data files for Linux using shared config ("build.data_files")
            # This mirrors other platforms: resource, config, auth, etc.
            try:
                data_cfg = self.config.get("build", {}).get("data_files", {})
                if data_cfg:
                    processed = process_data_files(data_cfg, verbose=True)
                    for src, dst in processed:
                        src_path = self.project_root / src
                        if src_path.exists():
                            cmd.extend(["--add-data", f"{src_path}:{dst}"])
                        else:
                            print(f"[PyInstaller] Warning: data path not found: {src_path}")
            except Exception as e:
                print(f"[PyInstaller] Warning: failed to process data_files: {e}")
            
            # Exclude modules
            for exclude in pyinstaller_config.get("excludes", []):
                cmd.extend(["--exclude-module", exclude])
            
            # Add hooks path
            hooks_path = self.project_root / "build_system" / "pyinstaller_hooks"
            if hooks_path.exists():
                cmd.extend(["--additional-hooks-dir", str(hooks_path)])
            
            # Main entry point
            cmd.append(str(self.project_root / "main.py"))
            
            print(f"\n[PyInstaller] Command: {' '.join(cmd)}\n")
            
            # Run PyInstaller with timeout
            print("[PyInstaller] Starting build (timeout: 30 minutes)...")
            try:
                result = subprocess.run(
                    cmd, 
                    cwd=str(self.project_root),
                    timeout=1800,  # 30 minutes timeout
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"❌ PyInstaller build failed with code {result.returncode}")
                    # PyInstaller tracebacks often put the useful exception and
                    # source filename near the beginning of stderr.  Keeping only
                    # the tail hid that context and left CI logs with an
                    # unactionable ``SystemExit: 2``.
                    if result.stdout:
                        print("PyInstaller standard output:")
                        print(result.stdout.rstrip())
                    if result.stderr:
                        print("PyInstaller error output:")
                        print(result.stderr.rstrip())
                    return False
            except subprocess.TimeoutExpired:
                print("❌ PyInstaller build timeout (30 minutes exceeded)")
                return False
            except Exception as e:
                print(f"❌ PyInstaller build error: {e}")
                return False
            
            print("✅ PyInstaller build completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ PyInstaller build error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_appimage(self) -> bool:
        """
        Create AppImage package
        
        Returns:
            bool: True if successful
        """
        print("\n" + "="*60)
        print("📦 Creating AppImage Package")
        print("="*60)
        
        try:
            # Check if appimagetool is available
            if not shutil.which("appimagetool"):
                print("⚠️  appimagetool not found. Install from:")
                print("   https://github.com/AppImage/AppImageKit/releases")
                print("\nAlternatively, use linuxdeploy:")
                print("   https://github.com/linuxdeploy/linuxdeploy/releases")
                return False
            
            # Create AppDir structure
            app_dir = self.dist_dir / f"{self.app_name}.AppDir"
            if app_dir.exists():
                shutil.rmtree(app_dir)
            
            app_dir.mkdir(parents=True, exist_ok=True)
            
            # Create directory structure
            (app_dir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
            (app_dir / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
            (app_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True, exist_ok=True)
            
            # Copy executable
            exe_src = self.dist_dir / self.app_name / self.app_name
            exe_dst = app_dir / "usr" / "bin" / self.app_name
            if exe_src.exists():
                shutil.copy2(exe_src, exe_dst)
                os.chmod(exe_dst, 0o755)
            else:
                print(f"❌ Executable not found: {exe_src}")
                return False
            
            # Copy all dependencies (optimized with hard links when possible)
            dist_app_dir = self.dist_dir / self.app_name
            if dist_app_dir.exists():
                print("[AppImage] Copying dependencies...")
                copied_count = 0
                for item in dist_app_dir.iterdir():
                    if item.name != self.app_name:  # Skip the main executable
                        dst = app_dir / "usr" / "bin" / item.name
                        if item.is_dir():
                            shutil.copytree(item, dst, dirs_exist_ok=True)
                            copied_count += 1
                        else:
                            # Try hard link first, fall back to copy
                            try:
                                os.link(item, dst)
                            except (OSError, NotImplementedError):
                                shutil.copy2(item, dst)
                            copied_count += 1
                print(f"[AppImage] Copied {copied_count} items")
            
            # Create desktop file (StartupWMClass from config app_name for taskbar match)
            desktop_content = f"""[Desktop Entry]
Name={self.app_name}
Exec={self.app_name}
Icon={self.app_name}
Type=Application
Categories=Utility;Development;
Comment=AI-powered automation assistant
Terminal=false
StartupWMClass={self.app_name.lower()}
"""
            desktop_file = app_dir / "usr" / "share" / "applications" / f"{self.app_name}.desktop"
            desktop_file.write_text(desktop_content)
            
            # Copy icon
            icon_src = self.project_root / "resource" / "images" / "logos" / "desktop_256x256.png"
            if icon_src.exists():
                icon_dst = app_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / f"{self.app_name}.png"
                shutil.copy2(icon_src, icon_dst)
                
                # Also copy to AppDir root
                shutil.copy2(icon_src, app_dir / f"{self.app_name}.png")
            
            # Create AppRun script
            apprun_content = f"""#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/usr/bin:${{PATH}}"
export LD_LIBRARY_PATH="${{HERE}}/usr/lib:${{LD_LIBRARY_PATH}}"
exec "${{HERE}}/usr/bin/{self.app_name}" "$@"
"""
            apprun_file = app_dir / "AppRun"
            apprun_file.write_text(apprun_content)
            os.chmod(apprun_file, 0o755)
            
            # Copy desktop file to AppDir root
            shutil.copy2(desktop_file, app_dir / f"{self.app_name}.desktop")
            
            # Create AppImage (use consistent naming: {name}-{version}-linux-{arch})
            output_file = self.dist_dir / f"{self.app_name}-{self.version}-linux-amd64.AppImage"
            if output_file.exists():
                output_file.unlink()
            
            cmd = ["appimagetool", str(app_dir), str(output_file)]
            print(f"\n[AppImage] Command: {' '.join(cmd)}\n")
            
            try:
                result = subprocess.run(
                    cmd, 
                    cwd=str(self.dist_dir),
                    timeout=600,  # 10 minutes timeout
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"❌ AppImage creation failed with code {result.returncode}")
                    if result.stderr:
                        print(f"Error output: {result.stderr[-500:]}")
                    return False
            except subprocess.TimeoutExpired:
                print("❌ AppImage creation timeout (10 minutes exceeded)")
                return False
            except Exception as e:
                print(f"❌ AppImage creation error: {e}")
                return False
            
            if output_file.exists():
                os.chmod(output_file, 0o755)
                print(f"✅ AppImage created: {output_file}")
                print(f"   Size: {output_file.stat().st_size / (1024*1024):.2f} MB")
                return True
            else:
                print("❌ AppImage file not created")
                return False
                
        except Exception as e:
            print(f"❌ AppImage creation error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_deb_package(self) -> bool:
        """
        Create DEB package for Debian/Ubuntu
        
        Returns:
            bool: True if successful
        """
        print("\n" + "="*60)
        print("📦 Creating DEB Package")
        print("="*60)
        
        try:
            # Check if dpkg-deb is available
            if not shutil.which("dpkg-deb"):
                print("⚠️  dpkg-deb not found. Install with:")
                print("   sudo apt install dpkg-dev")
                return False
            
            # DEB package has two places that contain the version:
            #   1. The DEBIAN/control file's `Version:` field — must be
            #      dpkg-deb-compatible (no underscores, per Debian policy).
            #   2. The .deb FILENAME — must match the workflow's
            #      `dist/$DIST_APP-$VERSION-linux-amd64.deb` template so
            #      the "Generate Ed25519 signatures" and "Prepare
            #      artifacts" steps can find the artifact.
            #
            # We previously sanitized the FILENAME too, which broke the
            # workflow contract (workflow used the raw `${{ ...version }}`
            # with underscores). Keep the filename verbatim and only
            # sanitize the value written into control's Version field.
            pkg_name = f"{self.app_name}-{self.version}-linux-amd64"
            deb_version = self._sanitize_deb_version(self.version)
            if deb_version != self.version:
                print(f"[DEB] Sanitized version for control file: {self.version} -> {deb_version}")
            pkg_dir = self.dist_dir / pkg_name
            if pkg_dir.exists():
                shutil.rmtree(pkg_dir)
            
            # Create DEBIAN directory
            debian_dir = pkg_dir / "DEBIAN"
            debian_dir.mkdir(parents=True, exist_ok=True)
            
            # Create application directories
            opt_dir = pkg_dir / "opt" / self.app_name
            opt_dir.mkdir(parents=True, exist_ok=True)
            
            apps_dir = pkg_dir / "usr" / "share" / "applications"
            apps_dir.mkdir(parents=True, exist_ok=True)
            
            icons_dir = pkg_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
            icons_dir.mkdir(parents=True, exist_ok=True)
            icons_dir_48 = pkg_dir / "usr" / "share" / "icons" / "hicolor" / "48x48" / "apps"
            icons_dir_48.mkdir(parents=True, exist_ok=True)
            
            bin_dir = pkg_dir / "usr" / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy application files
            dist_app_dir = self.dist_dir / self.app_name
            if dist_app_dir.exists():
                for item in dist_app_dir.iterdir():
                    dst = opt_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)
                        if item.name == self.app_name:
                            os.chmod(dst, 0o755)
            else:
                print(f"❌ Distribution directory not found: {dist_app_dir}")
                return False
            
            # Create symlink in /usr/bin
            symlink = bin_dir / self.app_name.lower()
            symlink.symlink_to(f"/opt/{self.app_name}/{self.app_name}")
            
            # Create desktop file (StartupWMClass from config app_name for taskbar match)
            desktop_content = f"""[Desktop Entry]
Name={self.app_name}
Exec=/opt/{self.app_name}/{self.app_name}
Icon={self.app_name}
Type=Application
Categories=Utility;Development;Office;
Comment=AI-powered automation assistant
Terminal=false
StartupWMClass={self.app_name.lower()}
"""
            desktop_file = apps_dir / f"{self.app_name.lower()}.desktop"
            desktop_file.write_text(desktop_content)
            
            # Copy icon for DEB (launcher + taskbar 48x48)
            icon_src = self.project_root / "resource" / "images" / "logos" / "desktop_256x256.png"
            icon_src_48 = self.project_root / "resource" / "images" / "logos" / "desktop_64x64.png"
            if not icon_src_48.exists():
                icon_src_48 = icon_src
            if icon_src.exists():
                shutil.copy2(icon_src, icons_dir / f"{self.app_name}.png")
                shutil.copy2(icon_src_48, icons_dir_48 / f"{self.app_name}.png")
            else:
                print("[DEB] Warning: resource/images/logos/desktop_256x256.png not found, desktop icon may be missing")
            
            # Calculate installed size (in KB)
            total_size = sum(f.stat().st_size for f in opt_dir.rglob('*') if f.is_file())
            installed_size = total_size // 1024
            
            # Create control file
            # NOTE: Keep this in sync with system dependencies listed in requirements-linux.txt
            control_content = f"""Package: {self.app_name.lower()}
Version: {deb_version}
Section: utils
Priority: optional
Architecture: amd64
Installed-Size: {installed_size}
Depends: libc6, libgcc-s1, libstdc++6, libgl1, libglib2.0-0, libxkbcommon-x11-0, \
 libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, \
 libxcb-shape0, libxcb-xfixes0, libxcb-xinerama0, libxcb-cursor0, python3-tk, \
 scrot | gnome-screenshot | imagemagick, wmctrl | xdotool, xdg-utils
Maintainer: eCan.ai Team <support@ecan.ai>
Description: AI-powered automation assistant
 eCan.ai is an intelligent automation assistant that helps you
 automate repetitive tasks, manage workflows, and boost productivity
 using advanced AI capabilities.
Homepage: https://ecan.ai
"""
            control_file = debian_dir / "control"
            control_file.write_text(control_content)
            
            # Create postinst script
            postinst_content = """#!/bin/bash
set -e

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q
fi

# Update icon cache
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

exit 0
"""
            postinst_file = debian_dir / "postinst"
            postinst_file.write_text(postinst_content)
            os.chmod(postinst_file, 0o755)
            
            # Create postrm script
            postrm_content = """#!/bin/bash
set -e

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q
fi

# Update icon cache
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

exit 0
"""
            postrm_file = debian_dir / "postrm"
            postrm_file.write_text(postrm_content)
            os.chmod(postrm_file, 0o755)
            
            # Build DEB package (pkg_name already includes -linux-amd64)
            output_file = self.dist_dir / f"{pkg_name}.deb"
            if output_file.exists():
                output_file.unlink()
            
            cmd = ["dpkg-deb", "--build", "--root-owner-group", str(pkg_dir), str(output_file)]
            print(f"\n[DEB] Command: {' '.join(cmd)}\n")
            
            try:
                result = subprocess.run(
                    cmd, 
                    cwd=str(self.dist_dir),
                    timeout=900,  # 15 minutes timeout (increased from 10)
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"❌ DEB package creation failed with code {result.returncode}")
                    if result.stderr:
                        print(f"Error output: {result.stderr[-500:]}")
                    return False
            except subprocess.TimeoutExpired:
                print("❌ DEB package creation timeout (15 minutes exceeded)")
                return False
            except Exception as e:
                print(f"❌ DEB package creation error: {e}")
                return False
            
            if output_file.exists():
                print(f"✅ DEB package created: {output_file}")
                print(f"   Size: {output_file.stat().st_size / (1024*1024):.2f} MB")
                
                # Verify package
                print("\n[DEB] Package info:")
                subprocess.run(["dpkg-deb", "--info", str(output_file)])
                
                return True
            else:
                print("❌ DEB package file not created")
                return False
                
        except Exception as e:
            print(f"❌ DEB package creation error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def build_all(self, mode: str = "prod", formats: Optional[List[str]] = None, parallel: bool = True) -> Dict[str, bool]:
        """
        Build all Linux packages with parallel support
        
        Args:
            mode: Build mode (dev, prod, fast)
            formats: List of formats to build (appimage, deb). If None, build all.
            parallel: Enable parallel building of packages (default: True)
            
        Returns:
            Dict mapping format name to success status
        """
        results = {}
        start_time = time.time()
        
        # Always build PyInstaller first
        print("\n" + "="*60)
        print(f"🐧 Linux Build Process - Mode: {mode}")
        print(f"⚡ Parallel Build: {'Enabled' if parallel else 'Disabled'}")
        print("="*60)
        
        # Step 1: PyInstaller build
        print("\n[1/3] Building with PyInstaller...")
        pyinstaller_start = time.time()
        if not self.build_pyinstaller(mode):
            print("\n❌ PyInstaller build failed - cannot continue")
            return {"pyinstaller": False}
        
        results["pyinstaller"] = True
        pyinstaller_time = time.time() - pyinstaller_start
        print(f"✅ PyInstaller completed in {pyinstaller_time:.1f}s")
        
        # Determine which formats to build
        if formats is None:
            formats = ["deb"]  # Only build DEB by default (AppImage is too slow)
        
        # Step 2 & 3: Build packages (parallel or serial)
        if parallel and len(formats) > 1:
            print(f"\n[2/3] Building packages in parallel ({', '.join(formats)})...")
            package_start = time.time()
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {}
                
                if "appimage" in formats:
                    print("  → Submitting AppImage build...")
                    futures[executor.submit(self.create_appimage)] = "appimage"
                
                if "deb" in formats:
                    print("  → Submitting DEB build...")
                    futures[executor.submit(self.create_deb_package)] = "deb"
                
                # Wait for completion
                for future in as_completed(futures):
                    format_name = futures[future]
                    try:
                        results[format_name] = future.result()
                        status = "✅" if results[format_name] else "❌"
                        print(f"  {status} {format_name.upper()} build completed")
                    except Exception as e:
                        print(f"  ❌ {format_name.upper()} build failed with exception: {e}")
                        results[format_name] = False
            
            package_time = time.time() - package_start
            print(f"✅ Parallel packaging completed in {package_time:.1f}s")
        else:
            # Serial build
            step = 2
            total_steps = 2 + len(formats)
            
            if "appimage" in formats:
                print(f"\n[{step}/{total_steps}] Building AppImage...")
                package_start = time.time()
                results["appimage"] = self.create_appimage()
                package_time = time.time() - package_start
                status = "✅" if results["appimage"] else "❌"
                print(f"{status} AppImage completed in {package_time:.1f}s")
                step += 1
            
            if "deb" in formats:
                print(f"\n[{step}/{total_steps}] Building DEB package...")
                package_start = time.time()
                results["deb"] = self.create_deb_package()
                package_time = time.time() - package_start
                status = "✅" if results["deb"] else "❌"
                print(f"{status} DEB package completed in {package_time:.1f}s")
        
        # Print summary
        total_time = time.time() - start_time
        print("\n" + "="*60)
        print("📊 Linux Build Summary")
        print("="*60)
        for format_name, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"  {format_name:15s}: {status}")
        print("="*60)
        print(f"⏱️  Total build time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        print("="*60 + "\n")
        
        return results


def main():
    """Test Linux builder"""
    project_root = Path(__file__).parent.parent
    
    # Load config
    config_file = project_root / "build_system" / "build_config.json"
    with open(config_file) as f:
        config = json.load(f)
    
    # Create builder
    builder = LinuxBuilder(project_root, config)
    
    # Build all formats
    results = builder.build_all(mode="prod")
    
    # Exit with error if any build failed
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
