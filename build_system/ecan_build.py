#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Cross-Platform Build System v9.0
Simplified build script with standard optimizer integration
"""

import os
import sys
import json
import time
import subprocess
import platform
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

# Encoding initialization for Windows environment
if platform.system() == "Windows":
    try:
        import codecs
        if not hasattr(sys.stdout, 'encoding') or sys.stdout.encoding.lower() != 'utf-8':       
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    except Exception:
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
            print("[FRONTEND] skip installing dependencies...")
            # Execute build
            if not self._run_build(force):
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
                cmd = "npm install --legacy-peer-deps"
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
    
    def _run_build(self, force: bool = False) -> bool:
        """Execute build"""
        try:
            print("[FRONTEND] Building frontend...")

            # 若 node_modules 不存在或强制模式，先执行 npm ci
            need_install = force or not (self.frontend_dir / 'node_modules').exists()
            if need_install:
                print("[FRONTEND] Installing dependencies (npm ci)...")
                install_cmd = "npm install --legacy-peer-deps" if platform.system() == "Windows" else ["npm", "ci", "--legacy-peer-deps"]
                install_shell = platform.system() == "Windows"
                install_env = os.environ.copy()
                if platform.system() == "Windows":
                    install_env['PYTHONIOENCODING'] = 'utf-8'
                    install_env['CHCP'] = '65001'
                else:
                    install_env['LC_ALL'] = 'en_US.UTF-8'
                    install_env['LANG'] = 'en_US.UTF-8'
                r = subprocess.run(install_cmd, cwd=self.frontend_dir, shell=install_shell, env=install_env)
                if r.returncode != 0:
                    print(f"[ERROR] npm ci failed with exit code: {r.returncode}")
                    return False

            if platform.system() == "Windows":
                cmd = "npm run build"
                shell = True
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['CHCP'] = '65001'
            else:
                cmd = ["npm", "run", "build"]
                shell = False
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
                errors='replace'
            )

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
    """PyInstaller builder using MiniSpecBuilder (unified path)"""

    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path):
        self.config = config
        self.env = env
        self.project_root = project_root

    def build(self, mode: str, force: bool = False) -> bool:
        """Build application using MiniSpecBuilder (align with build.py)"""
        print(f"[PYINSTALLER] Starting PyInstaller build using MiniSpecBuilder...")

        try:
            from build_system.minibuild_core import MiniSpecBuilder
            minispec = MiniSpecBuilder()
            success = minispec.build(mode)

            if success:
                print("[SUCCESS] PyInstaller build completed")
                return True
            else:
                print("[ERROR] PyInstaller build failed")
                return False
        except Exception as e:
            print(f"[ERROR] PyInstaller build failed: {e}")
            return False


class InstallerBuilder:
    """Installer builder with full Windows/macOS support"""

    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path, mode: str = "prod"):
        self.config = config
        self.env = env
        self.project_root = project_root
        self.dist_dir = project_root / "dist"
        self.mode = mode

    def build(self) -> bool:
        """Build installer"""
        installer_config = self.config.config.get("installer", {})

        if not installer_config.get("enabled", False):
            print("[INSTALLER] Installer disabled in configuration")
            return True

        if self.env.is_windows:
            return self._build_windows_installer()
        elif self.env.is_macos:
            return self._build_macos_installer()
        else:
            print("[INFO] Installer creation not supported for this platform")
            return True

    def _build_windows_installer(self) -> bool:
        """Build Windows installer using Inno Setup"""
        try:
            print("[INSTALLER] Building Windows installer...")

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
            windows_config = installer_config.get("windows", {})
            app_info = self.config.get_app_info()

            # AppId (GUID) from config for Inno Setup
            raw_app_id = windows_config.get("app_id", "6E1CCB74-1C0D-4333-9F20-2E4F2AF3F4A1")
            # Normalize: strip any braces and whitespace; Inno requires GUID in double braces in .iss to avoid constant expansion
            app_id = str(raw_app_id).strip().strip("{}").strip()

            # Get compression settings based on build mode
            compression_modes = installer_config.get("compression_modes", {})
            mode_config = compression_modes.get(self.mode, {})

            compression = mode_config.get("compression", installer_config.get("compression", "zip"))
            solid_compression = str(mode_config.get("solid_compression", installer_config.get("solid_compression", False))).lower()
            internal_compress_level = mode_config.get("internal_compress_level", "normal")

            # 读取构建模式中的 runtime_tmpdir（Windows 平台）
            runtime_tmpdir = None
            try:
                build_modes = self.config.config.get("build_modes", {})
                mode_cfg = build_modes.get(self.mode, {})
                runtime_tmpdir = mode_cfg.get("runtime_tmpdir")
                if isinstance(runtime_tmpdir, dict):
                    runtime_tmpdir = runtime_tmpdir.get("windows")
                if isinstance(runtime_tmpdir, str):
                    runtime_tmpdir = runtime_tmpdir.replace("/", "\\")
            except Exception:
                runtime_tmpdir = None

            # 根据是否提供 runtime_tmpdir 构造 [Dirs] 段
            if runtime_tmpdir:
                dirs_section = f"[Dirs]\nName: \"{runtime_tmpdir}\"; Flags: uninsneveruninstall\n\n"
            else:
                dirs_section = ""

            # 选择文件源：优先使用 onedir 目录，否则使用单文件 EXE
            onedir_dir = self.project_root / 'dist' / 'eCan'
            onefile_exe = self.project_root / 'dist' / 'eCan.exe'
            if onedir_dir.exists():
                files_section = "Source: \"..\\dist\\eCan\\*\"; DestDir: \"{app}\"; Flags: ignoreversion recursesubdirs createallsubdirs"
                run_target = "{app}\\eCan.exe"
            elif onefile_exe.exists():
                files_section = "Source: \"..\\dist\\eCan.exe\"; DestDir: \"{app}\"; Flags: ignoreversion"
                run_target = "{app}\\eCan.exe"
            else:
                files_section = "Source: \"..\\dist\\*.exe\"; DestDir: \"{app}\"; Flags: ignoreversion"
                run_target = "{app}\\eCan.exe"

            iss_content = f"""
; eCan Installer Script
[Setup]
AppId={{{{{app_id}}}}}
AppName={installer_config.get('app_name', app_info.get('name', 'eCan'))}
AppVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}
AppPublisher={installer_config.get('app_publisher', 'eCan Team')}
DefaultDirName={{autopf}}\eCan
DefaultGroupName=eCan
OutputDir=..\dist
OutputBaseFilename=eCan-Setup
Compression={compression}
SolidCompression={solid_compression}
UsePreviousAppDir=no
PrivilegesRequired=lowest
InternalCompressLevel={internal_compress_level}
SetupIconFile=..\eCan.ico
UninstallDisplayIcon={{app}}\eCan.exe
CreateUninstallRegKey=true
AllowNoIcons=true
DisableProgramGroupPage=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

{dirs_section}[Files]
{files_section}

[Icons]
Name: "{{group}}\eCan"; Filename: "{run_target}"
Name: "{{userdesktop}}\eCan"; Filename: "{run_target}"; Tasks: desktopicon

[Run]
Filename: "{run_target}"; Description: "{{cm:LaunchProgram,eCan}}"; Flags: nowait postinstall skipifsilent
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

            print(f"[INSTALLER] Running Inno Setup: {iscc_path}")
            print(f"[INSTALLER] Script file: {iss_file}")

            cmd = [iscc_path, "/Q", str(iss_file)]

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=1800  # 30 minutes timeout
            )

            if result.returncode != 0:
                print(f"[ERROR] Inno Setup compilation failed:")
                print(f"[ERROR] Return code: {result.returncode}")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] Windows installer created")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to run Inno Setup: {e}")
            return False

    def _build_macos_installer(self) -> bool:
        """Build macOS DMG installer with proper UI and shortcuts"""
        try:
            print("[INSTALLER] Building macOS DMG installer...")

            # Auto-install create-dmg tool if needed
            if not self._ensure_create_dmg_installed():
                print("[WARNING] create-dmg tool not available, will use fallback method")

            installer_config = self.config.config.get("installer", {})
            macos_config = installer_config.get("macos", {})
            app_info = self.config.get_app_info()

            app_name = app_info.get("name", "eCan")
            app_version = app_info.get("version", "1.0.0")
            volume_name = macos_config.get("app_name", app_name)

            # Locate app bundle built by PyInstaller
            app_bundle_dir = self.dist_dir / f"{app_name}.app"
            if not app_bundle_dir.exists():
                print(f"[ERROR] App bundle not found: {app_bundle_dir}")
                return False

            # Prepare a staging directory for DMG contents
            dmg_root = self.dist_dir / "dmgroot"
            try:
                if dmg_root.exists():
                    shutil.rmtree(dmg_root)
                dmg_root.mkdir(parents=True, exist_ok=True)
                
                # Copy app bundle
                dest_app = dmg_root / f"{app_name}.app"
                shutil.copytree(app_bundle_dir, dest_app, symlinks=True)
                
                # Create Applications folder symlink
                applications_link = dmg_root / "Applications"
                if applications_link.exists() or applications_link.is_symlink():
                    try:
                        applications_link.unlink()
                    except Exception:
                        pass
                os.symlink("/Applications", str(applications_link))
                
                # Create background image for DMG
                self._create_dmg_background(dmg_root, app_name)
                
                # Create .DS_Store for proper icon positioning
                self._create_dmg_ds_store(dmg_root, app_name)
                
            except Exception as e:
                print(f"[ERROR] Failed to prepare DMG root: {e}")
                return False

            # Try to use create-dmg for better DMG creation
            dmg_file = self.dist_dir / f"{app_name}-{app_version}.dmg"
            if dmg_file.exists():
                try:
                    dmg_file.unlink()
                except Exception:
                    pass

            # Check if create-dmg is available
            if self._check_create_dmg():
                print("[INSTALLER] Using create-dmg for enhanced DMG creation...")
                success = self._create_dmg_with_create_dmg(dmg_root, app_name, app_version, volume_name, dmg_file)
            else:
                print("[INSTALLER] create-dmg not available, using hdiutil...")
                success = self._create_dmg_with_hdiutil(dmg_root, volume_name, dmg_file)

            if not success:
                return False

            if not dmg_file.exists() or dmg_file.stat().st_size == 0:
                print(f"[ERROR] DMG file not created or empty: {dmg_file}")
                return False

            print(f"[SUCCESS] macOS DMG created: {dmg_file} ({dmg_file.stat().st_size / (1024*1024):.1f} MB)")

            # Cleanup staging directory
            try:
                if dmg_root.exists():
                    shutil.rmtree(dmg_root)
                    print(f"[CLEANUP] Removed dmgroot: {dmg_root}")
            except Exception as e:
                print(f"[WARNING] Failed to cleanup dmgroot: {e}")

            # Optional: Notarization for DMG
            if macos_config.get("notarization", {}).get("enabled", False):
                if not self._notarize_dmg(dmg_file, macos_config):
                    print("[WARNING] Notarization failed, but continuing...")

            return True

        except Exception as e:
            print(f"[ERROR] macOS DMG installer creation failed: {e}")
            return False

    def _create_dmg_background(self, dmg_root: Path, app_name: str) -> None:
        """Create a background image for the DMG"""
        try:
            # Create a simple background image using Python
            from PIL import Image, ImageDraw, ImageFont
            
            # Create a background image (800x600)
            width, height = 800, 600
            background = Image.new('RGB', (width, height), color='#f0f0f0')
            draw = ImageDraw.Draw(background)
            
            # Add some text
            try:
                # Try to use a system font
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            except:
                font = ImageFont.load_default()
            
            # Draw title
            title = f"Install {app_name}"
            title_bbox = draw.textbbox((0, 0), title, font=font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (width - title_width) // 2
            draw.text((title_x, 50), title, fill='#333333', font=font)
            
            # Draw instructions
            instructions = [
                "1. Drag the application to Applications folder",
                "2. Double-click to launch",
                "3. Enjoy using the application!"
            ]
            
            for i, instruction in enumerate(instructions):
                y_pos = 150 + i * 40
                draw.text((100, y_pos), instruction, fill='#666666', font=font)
            
            # Save background image
            background_path = dmg_root / ".background" / "background.png"
            background_path.parent.mkdir(exist_ok=True)
            background.save(background_path, "PNG")
            
            print(f"[DMG] Created background image: {background_path}")
            
        except ImportError:
            print("[DMG] PIL not available, skipping background image creation")
        except Exception as e:
            print(f"[DMG] Warning: Could not create background image: {e}")

    def _create_dmg_ds_store(self, dmg_root: Path, app_name: str) -> None:
        """Create .DS_Store file for proper icon positioning in DMG"""
        try:
            # Create .DS_Store file with proper icon positioning
            ds_store_content = self._generate_ds_store_content(app_name)
            ds_store_path = dmg_root / ".DS_Store"
            
            with open(ds_store_path, 'wb') as f:
                f.write(ds_store_content)
            
            print(f"[DMG] Created .DS_Store file: {ds_store_path}")
            
        except Exception as e:
            print(f"[DMG] Warning: Could not create .DS_Store file: {e}")

    def _generate_ds_store_content(self, app_name: str) -> bytes:
        """Generate .DS_Store content for proper icon positioning"""
        # This is a simplified .DS_Store content
        # In a real implementation, you might want to use a library like ds_store
        
        # Basic .DS_Store structure for icon positioning
        ds_store = b'\x00\x00\x00\x01Bud1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        
        # Add icon positions for app and Applications folder
        # App icon at (100, 100)
        # Applications folder at (300, 100)
        
        return ds_store

    def _ensure_create_dmg_installed(self) -> bool:
        """Ensure create-dmg tool is installed, install if needed"""
        try:
            # Check if already installed
            if self._check_create_dmg():
                print("[TOOL] create-dmg tool already installed")
                return True
            
            print("[TOOL] create-dmg tool not found, attempting to install...")
            
            # Check if Homebrew is available
            if not self._check_homebrew():
                print("[TOOL] Homebrew not available, cannot install create-dmg")
                return False
            
            # Install create-dmg
            if self._install_create_dmg():
                print("[TOOL] create-dmg tool installed successfully")
                return True
            else:
                print("[TOOL] Failed to install create-dmg tool")
                return False
                
        except Exception as e:
            print(f"[TOOL] Error during create-dmg installation: {e}")
            return False

    def _check_homebrew(self) -> bool:
        """Check if Homebrew is available"""
        try:
            result = subprocess.run(["which", "brew"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def _install_create_dmg(self) -> bool:
        """Install create-dmg tool using Homebrew"""
        try:
            print("[TOOL] Installing create-dmg via Homebrew...")
            
            cmd = ["brew", "install", "create-dmg"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print("[TOOL] create-dmg installed successfully")
                return True
            else:
                print(f"[TOOL] Homebrew installation failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[TOOL] Error during Homebrew installation: {e}")
            return False

    def _check_create_dmg(self) -> bool:
        """Check if create-dmg tool is available"""
        try:
            result = subprocess.run(["which", "create-dmg"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def _create_dmg_with_create_dmg(self, dmg_root: Path, app_name: str, app_version: str, volume_name: str, dmg_file: Path) -> bool:
        """Create DMG using create-dmg tool for enhanced UI"""
        try:
            # Create a script for create-dmg
            script_content = f"""#!/bin/bash
create-dmg \\
    --volname "{volume_name}" \\
    --volicon "{dmg_root / f'{app_name}.app' / 'Contents' / 'Resources' / 'eCan.icns'}" \\
    --background "{dmg_root / '.background' / 'background.png'}" \\
    --window-pos 200 120 \\
    --window-size 600 400 \\
    --icon-size 100 \\
    --icon "{app_name}.app" 175 120 \\
    --hide-extension "{app_name}.app" \\
    --app-drop-link 425 120 \\
    --no-internet-enable \\
    "{dmg_file}" \\
    "{dmg_root}"
"""
            
            script_path = dmg_root / "create_dmg.sh"
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Make script executable
            os.chmod(script_path, 0o755)
            
            # Run create-dmg
            cmd = ["bash", str(script_path)]
            print(f"[INSTALLER] Running create-dmg script...")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0:
                print("[ERROR] create-dmg failed:")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            return True
            
        except Exception as e:
            print(f"[ERROR] create-dmg creation failed: {e}")
            return False
            
    def _create_dmg_with_hdiutil(self, dmg_root: Path, volume_name: str, dmg_file: Path) -> bool:
        """Create DMG using hdiutil (fallback method)"""
        try:
            cmd = [
                "hdiutil", "create",
                "-volname", str(volume_name),
                "-srcfolder", str(dmg_root),
                "-ov",
                "-format", "UDZO",
                str(dmg_file)
            ]

            print(f"[INSTALLER] Creating DMG with hdiutil: {dmg_file}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0:
                print("[ERROR] hdiutil DMG creation failed:")
                print(f"[ERROR] Return code: {result.returncode}")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            return True

        except Exception as e:
            print(f"[ERROR] hdiutil DMG creation failed: {e}")
            return False

    def _codesign_pkg(self, pkg_file: Path, macos_config: Dict[str, Any]) -> bool:
        """Code sign PKG file"""
        try:
            codesign_config = macos_config.get("codesign", {})
            identity = codesign_config.get("identity", "")

            if not identity:
                print("[WARNING] No code signing identity specified")
                return True

            print(f"[INSTALLER] Code signing PKG with identity: {identity}")

            cmd = ["codesign", "--sign", identity]

            # Add entitlements if specified
            entitlements_file = codesign_config.get("entitlements", "")
            if entitlements_file and Path(entitlements_file).exists():
                cmd.extend(["--entitlements", entitlements_file])

            cmd.append(str(pkg_file))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                print(f"[WARNING] Code signing failed:")
                print(f"[WARNING] Return code: {result.returncode}")
                print(f"[WARNING] STDERR: {result.stderr}")
                return True  # Continue even if signing fails

            print("[SUCCESS] PKG code signed")
            return True

        except Exception as e:
            print(f"[WARNING] Code signing failed: {e}")
            return True  # Continue even if signing fails

    def _notarize_dmg(self, dmg_file: Path, macos_config: Dict[str, Any]) -> bool:
        """Notarize DMG file with Apple"""
        try:
            notarization_config = macos_config.get("notarization", {})
            apple_id = notarization_config.get("apple_id", "")
            team_id = notarization_config.get("team_id", "")
            app_password = notarization_config.get("app_password", "")

            if not all([apple_id, team_id, app_password]):
                print("[WARNING] Incomplete notarization configuration for DMG")
                return False

            print(f"[INSTALLER] Starting DMG notarization for: {dmg_file}")
            cmd = [
                "xcrun", "notarytool", "submit",
                str(dmg_file),
                "--apple-id", apple_id,
                "--team-id", team_id,
                "--password", app_password,
                "--wait"
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800
            )

            if result.returncode != 0:
                print("[WARNING] DMG notarization failed:")
                print(f"[WARNING] Return code: {result.returncode}")
                print(f"[WARNING] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] DMG notarized successfully")

            # Staple notarization to DMG
            staple_cmd = ["xcrun", "stapler", "staple", str(dmg_file)]
            staple_result = subprocess.run(
                staple_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            if staple_result.returncode == 0:
                print("[SUCCESS] Notarization stapled to DMG")
            else:
                print("[WARNING] Failed to staple notarization to DMG")
            return True

        except Exception as e:
            print(f"[WARNING] DMG notarization failed: {e}")
            return False

    def _create_entitlements_file(self, macos_config: Dict[str, Any]) -> Optional[Path]:
        """Create entitlements file for macOS permissions"""
        try:
            permissions = macos_config.get("permissions", [])
            if not permissions:
                return None

            # Map permission names to entitlement keys
            permission_map = {
                "screen_recording": "com.apple.security.device.screen-recording",
                "accessibility": "com.apple.security.device.accessibility",
                "camera": "com.apple.security.device.camera",
                "microphone": "com.apple.security.device.microphone",
                "location": "com.apple.security.personal-information.location",
                "contacts": "com.apple.security.personal-information.addressbook",
                "calendar": "com.apple.security.personal-information.calendars",
                "photos": "com.apple.security.personal-information.photos-library"
            }

            entitlements_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.network.server</key>
    <true/>
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
'''

            # Add requested permissions
            for permission in permissions:
                if permission in permission_map:
                    entitlement_key = permission_map[permission]
                    entitlements_content += f'''    <key>{entitlement_key}</key>
    <true/>
'''

            entitlements_content += '''</dict>
</plist>
'''

            # Write entitlements file
            entitlements_file = self.project_root / "build" / "entitlements.plist"
            entitlements_file.parent.mkdir(exist_ok=True)

            with open(entitlements_file, 'w', encoding='utf-8') as f:
                f.write(entitlements_content)

            print(f"[INSTALLER] Created entitlements file: {entitlements_file}")
            return entitlements_file

        except Exception as e:
            print(f"[WARNING] Failed to create entitlements file: {e}")
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

    def build(self, force: bool = False, skip_frontend: bool = None, skip_installer: bool = False, 
              enable_sparkle: bool = False, verify_sparkle: bool = False) -> bool:
        """Execute build"""
        start_time = time.time()

        print("=" * 60)
        print("eCan Cross-Platform Build System v9.0")
        print("=" * 60)

        try:
            # Check OTA dependencies (CI should have installed them)
            if enable_sparkle or verify_sparkle:
                print("[BUILD] Sparkle support enabled - checking dependencies...")
            self._check_ota_dependencies()
            
            # 如果启用了 Sparkle 验证，进行额外检查
            if verify_sparkle:
                if not self._verify_sparkle_environment():
                    print("[ERROR] Sparkle verification failed!")
                    return False
            
            # Build frontend (if needed)
            if skip_frontend is None:
                skip_frontend = self.mode == "prod"

            if not skip_frontend:
                if not self.frontend_builder.build(force):
                    return False
            else:
                print("[FRONTEND] Skipped by flag --skip-frontend")

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

    def _check_ota_dependencies(self):
        """检查OTA依赖是否已安装（由CI安装）"""
        ota_dir = self.project_root / "ota" / "dependencies"
        install_info_file = ota_dir / "install_info.json"
        
        if not ota_dir.exists():
            print("[OTA] OTA dependencies directory not found")
            print("[OTA] OTA functionality will use fallback HTTP updates")
            return
        
        if not install_info_file.exists():
            print("[OTA] OTA install info not found")
            print("[OTA] Dependencies may not be properly installed")
            return
        
        try:
            with open(install_info_file, 'r') as f:
                install_info = json.load(f)
            
            platform = install_info.get("platform", "unknown")
            install_method = install_info.get("install_method", "unknown")
            installed_deps = install_info.get("installed_dependencies", {})
            
            print(f"[OTA] Dependencies installed via {install_method} for {platform}")
            
            for name, dep_info in installed_deps.items():
                if dep_info.get("installed", False):
                    print(f"[OTA] {name} v{dep_info.get('version', 'unknown')}")
                else:
                    print(f"[OTA] {name} not properly installed")
            
            # Sparkle 特定验证
            self._verify_sparkle_installation(ota_dir, platform)
            
            if not installed_deps:
                print("[OTA] No dependencies found for current platform")
                
        except Exception as e:
            print(f"[OTA] Failed to read install info: {e}")
    
    def _verify_sparkle_installation(self, ota_dir: Path, platform: str):
        """验证 Sparkle/winSparkle 安装"""
        if platform == "darwin":
            # 检查 Sparkle.framework
            sparkle_framework = ota_dir / "Sparkle.framework"
            if sparkle_framework.exists():
                print("[OTA] [OK] Sparkle.framework found")
                
                # 检查关键文件
                sparkle_binary = sparkle_framework / "Versions" / "Current" / "Sparkle"
                sparkle_cli = sparkle_framework / "Versions" / "Current" / "Resources" / "sparkle-cli"
                
                if sparkle_binary.exists():
                    print("[OTA] [OK] Sparkle binary verified")
                else:
                    print("[OTA] [WARN] Sparkle binary not found")
                
                if sparkle_cli.exists():
                    print("[OTA] [OK] Sparkle CLI verified")
                else:
                    print("[OTA] [WARN] Sparkle CLI not found")
            else:
                print("[OTA] [ERROR] Sparkle.framework not found")
                
        elif platform == "windows":
            # 检查 winSparkle
            winsparkle_dir = ota_dir / "winsparkle"
            if winsparkle_dir.exists():
                print("[OTA] [OK] winSparkle directory found")
                
                # 检查关键文件
                winsparkle_dll = winsparkle_dir / "winsparkle.dll"
                winsparkle_lib = winsparkle_dir / "winsparkle.lib"
                
                if winsparkle_dll.exists():
                    print("[OTA] [OK] winSparkle DLL verified")
                else:
                    print("[OTA] [ERROR] winSparkle DLL not found")
                
                if winsparkle_lib.exists():
                    print("[OTA] [OK] winSparkle LIB verified")
                else:
                    print("[OTA] [WARN] winSparkle LIB not found")
            else:
                print("[OTA] [ERROR] winSparkle directory not found")
    
    def _verify_sparkle_environment(self) -> bool:
        """验证 Sparkle 环境是否完整"""
        ota_dir = self.project_root / "ota" / "dependencies"
        
        if not ota_dir.exists():
            print("[SPARKLE] [ERROR] OTA dependencies directory not found")
            return False
        
        platform = "darwin" if self.env.is_macos else "windows" if self.env.is_windows else "unknown"
        
        if platform == "darwin":
            # 验证 Sparkle.framework
            sparkle_framework = ota_dir / "Sparkle.framework"
            if not sparkle_framework.exists():
                print("[SPARKLE] [ERROR] Sparkle.framework not found")
                return False
            
            # 检查关键组件
            required_files = [
                sparkle_framework / "Versions" / "Current" / "Sparkle",
                sparkle_framework / "Versions" / "Current" / "Resources" / "Info.plist",
            ]
            
            for file_path in required_files:
                if not file_path.exists():
                    print(f"[SPARKLE] [ERROR] Required file missing: {file_path.name}")
                    return False
            
            print("[SPARKLE] [OK] Sparkle.framework verification passed")
            return True
            
        elif platform == "windows":
            # 验证 winSparkle
            winsparkle_dir = ota_dir / "winsparkle"
            if not winsparkle_dir.exists():
                print("[SPARKLE] [ERROR] winSparkle directory not found")
                return False
            
            # 检查关键文件
            winsparkle_dll = winsparkle_dir / "winsparkle.dll"
            if not winsparkle_dll.exists():
                print("[SPARKLE] [ERROR] winsparkle.dll not found")
                return False
            
            print("[SPARKLE] [OK] winSparkle verification passed")
            return True
        
        else:
            print(f"[SPARKLE] [WARN] Unsupported platform: {platform}")
            return True  # 不阻止构建
    
    def _show_result(self, start_time: float):
        """Display build results"""
        build_time = time.time() - start_time
        print("=" * 60)
        print(f"[SUCCESS] Build completed in {build_time:.2f} seconds")
        print(f"[INFO] Build mode: {self.mode}")
        print(f"[INFO] Platform: {self.env.platform}")
        print("=" * 60)


# 注意：这个文件现在是纯库文件，不应该直接运行
# 请使用 build.py 作为唯一入口点

def main():
    """Deprecated: Use build.py instead"""
    print("[ERROR] 请使用 build.py 作为构建入口点")
    print("[OK] 正确用法: python build.py fast")
    sys.exit(1)


if __name__ == "__main__":
    main()
