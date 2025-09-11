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
        return self.config.get("app", {})

    def update_version(self, version: str):
        """Update version information"""
        if "app" in self.config:
            self.config["app"]["version"] = version
        if "installer" in self.config:
            self.config["installer"]["app_version"] = version
        print(f"[INFO] Updated version to: {version}")

    def get_build_config(self) -> Dict[str, Any]:
        """Get build configuration"""
        return self.config.get("build", {})

    def get_platform_config(self, platform: str) -> Dict[str, Any]:
        """Get platform-specific configuration"""
        platforms = self.config.get("platforms", {})
        return platforms.get(platform, {})


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

            # If node_modules doesn't exist or force mode, run npm ci first
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

    def _ensure_windows_icon_quality(self) -> bool:
        """确保Windows图标质量和配置"""
        try:
            icon_file = self.project_root / "eCan.ico"

            # 验证ICO文件
            if not icon_file.exists():
                print("[WARNING] eCan.ico not found")
                return False

            # 检查ICO文件质量
            file_size = icon_file.stat().st_size
            if file_size < 1000:
                print(f"[WARNING] ICO file seems too small: {file_size} bytes")

            # 验证ICO文件头
            with open(icon_file, 'rb') as f:
                header = f.read(6)
                if header[:2] != b'\x00\x00' or header[2:4] != b'\x01\x00':
                    print("[WARNING] Invalid ICO file header")
                    return False

                icon_count = int.from_bytes(header[4:6], 'little')
                print(f"[INFO] ICO file contains {icon_count} icon(s), size: {file_size} bytes")

            return True

        except Exception as e:
            print(f"[WARNING] Failed to validate ICO file: {e}")
            return False

    def _create_inno_script(self) -> Optional[Path]:
        """Create Inno Setup script"""
        try:
            # 确保Windows图标质量
            if not self._ensure_windows_icon_quality():
                print("[WARNING] Windows icon quality check failed")

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

            # Read runtime_tmpdir from build mode (Windows platform)
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

            # Construct [Dirs] section based on whether runtime_tmpdir is provided
            if runtime_tmpdir:
                dirs_section = f"[Dirs]\nName: \"{runtime_tmpdir}\"; Flags: uninsneveruninstall\n\n"
            else:
                dirs_section = ""

            # Choose file source: prefer onedir directory, otherwise use single file EXE
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

            # Create standardized installer filename with platform and architecture
            arch = os.environ.get('BUILD_ARCH', 'amd64')
            if arch == 'x86_64':
                arch = 'amd64'
            app_version = installer_config.get('app_version', app_info.get('version', '1.0.0'))
            installer_filename = f"eCan-{app_version}-windows-{arch}-Setup"

            # Get Windows-specific installer settings
            default_dir = windows_config.get('default_dir', installer_config.get('default_dir', '{pf}\\eCan'))
            default_group = windows_config.get('default_group', installer_config.get('default_group', 'eCan'))
            privileges_required = windows_config.get('privileges_required', installer_config.get('privileges_required', 'admin'))

            iss_content = f"""
; eCan Installer Script
[Setup]
AppId={{{{{app_id}}}}}
AppName={installer_config.get('app_name', app_info.get('name', 'eCan'))}
AppVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}
AppPublisher={installer_config.get('app_publisher', 'eCan Team')}
DefaultDirName={default_dir}
DefaultGroupName={default_group}
OutputDir=..\dist
OutputBaseFilename={installer_filename}
Compression={compression}
SolidCompression={solid_compression}
UsePreviousAppDir=yes
PrivilegesRequired={privileges_required}
InternalCompressLevel={internal_compress_level}
SetupIconFile=..\eCan.ico
UninstallDisplayIcon={{app}}\eCan.exe
CreateUninstallRegKey=yes
AllowNoIcons=yes
DisableProgramGroupPage=auto
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

{dirs_section}[Files]
{files_section}

[Icons]
Name: "{{group}}\eCan"; Filename: "{run_target}"; IconFilename: "{run_target}"; IconIndex: 0
Name: "{{userdesktop}}\eCan"; Filename: "{run_target}"; IconFilename: "{run_target}"; IconIndex: 0; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{{localappdata}}\eCan"

[Code]
// Notify Windows of new application installation
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Refresh shell to recognize new application
    // This is less intrusive than restarting explorer
  end;
end;

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if MsgBox('Do you want to remove user data and settings?', mbConfirmation, MB_YESNO) = IDYES then
  begin
    // Remove user data directory
    if DirExists(ExpandConstant('{{localappdata}}\eCan')) then
    begin
      if not DelTree(ExpandConstant('{{localappdata}}\eCan'), True, True, True) then
        MsgBox('Could not remove user data directory. You may need to remove it manually.', mbInformation, MB_OK);
    end;
  end;
end;

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

            # Create standardized EXE filename for the main executable
            self._create_standardized_windows_artifacts()

            return True

        except Exception as e:
            print(f"[ERROR] Failed to run Inno Setup: {e}")
            return False

    def _create_standardized_windows_artifacts(self) -> None:
        """Create standardized Windows artifact filenames"""
        try:
            app_info = self.config.get_app_info()
            app_version = app_info.get('version', '1.0.0')
            arch = os.environ.get('BUILD_ARCH', 'amd64')
            if arch == 'x86_64':
                arch = 'amd64'

            # Create standardized EXE filename
            onedir_exe = self.dist_dir / 'eCan' / 'eCan.exe'
            onefile_exe = self.dist_dir / 'eCan.exe'

            source_exe = None
            if onedir_exe.exists():
                source_exe = onedir_exe
            elif onefile_exe.exists():
                source_exe = onefile_exe

            if source_exe:
                std_exe = self.dist_dir / f"eCan-{app_version}-windows-{arch}.exe"
                if not std_exe.exists():
                    try:
                        shutil.copy2(source_exe, std_exe)
                        print(f"[INFO] Created standardized EXE: {std_exe.name}")
                    except Exception as e:
                        print(f"[WARNING] Failed to create standardized EXE: {e}")

            # Only keep standardized installer filename to avoid duplicates
            installer_std = self.dist_dir / f"eCan-{app_version}-windows-{arch}-Setup.exe"
            installer_legacy = self.dist_dir / "eCan-Setup.exe"

            # Remove legacy installer if it exists to avoid duplicates
            if installer_legacy.exists():
                try:
                    installer_legacy.unlink()
                    print(f"[INFO] Removed duplicate legacy installer: {installer_legacy.name}")
                except Exception as e:
                    print(f"[WARNING] Failed to remove legacy installer: {e}")

            # Verify standardized installer exists
            if installer_std.exists():
                print(f"[INFO] Standardized installer ready: {installer_std.name}")
            else:
                print(f"[WARNING] Standardized installer not found: {installer_std.name}")

        except Exception as e:
            print(f"[WARNING] Failed to create standardized Windows artifacts: {e}")

    def _build_macos_installer(self) -> bool:
        """Build macOS PKG installer"""
        try:
            print("[INSTALLER] Building macOS PKG installer...")

            installer_config = self.config.config.get("installer", {})
            macos_config = installer_config.get("macos", {})
            app_info = self.config.get_app_info()

            app_name = app_info.get("name", "eCan")
            app_version = app_info.get("version", "1.0.0")

            # Build PKG installer (default and recommended format)
            return self._build_macos_pkg_installer(app_name, app_version, macos_config)

        except Exception as e:
            print(f"[ERROR] macOS installer creation failed: {e}")
            return False

    def _build_macos_pkg_installer(self, app_name: str, app_version: str, macos_config: Dict[str, Any]) -> bool:
        """Build macOS PKG installer"""
        try:
            print("[INSTALLER] Creating macOS PKG installer...")

            # Locate app bundle built by PyInstaller
            app_bundle_dir = self.dist_dir / f"{app_name}.app"
            if not app_bundle_dir.exists():
                print(f"[ERROR] App bundle not found: {app_bundle_dir}")
                return False

            # Create standardized PKG filename with platform and architecture
            arch = self._get_normalized_arch()
            pkg_file = self.dist_dir / f"{app_name}-{app_version}-macos-{arch}.pkg"
            if pkg_file.exists():
                try:
                    pkg_file.unlink()
                except Exception:
                    pass

            # Create PKG using pkgbuild and productbuild
            success = self._create_pkg_installer(app_bundle_dir, app_name, app_version, pkg_file, macos_config)

            if not success:
                return False

            if not pkg_file.exists() or pkg_file.stat().st_size == 0:
                print(f"[ERROR] PKG file not created or empty: {pkg_file}")
                return False

            print(f"[SUCCESS] macOS PKG created: {pkg_file} ({pkg_file.stat().st_size / (1024*1024):.1f} MB)")

            # Remove any legacy PKG files to avoid duplicates
            legacy_pkg = self.dist_dir / f"{app_name}-{app_version}.pkg"
            if legacy_pkg.exists() and legacy_pkg != pkg_file:
                try:
                    legacy_pkg.unlink()
                    print(f"[INFO] Removed duplicate legacy PKG: {legacy_pkg.name}")
                except Exception as e:
                    print(f"[WARNING] Failed to remove legacy PKG: {e}")

            # Optional: Code signing for PKG
            if macos_config.get("codesign", {}).get("enabled", False):
                try:
                    if not self._codesign_pkg(pkg_file, macos_config):
                        print("[WARNING] PKG code signing failed, but continuing...")
                except Exception as e:
                    print(f"[WARNING] PKG code signing error: {e}")

            # Optional: Notarization for PKG
            if macos_config.get("notarization", {}).get("enabled", False):
                try:
                    if not self._notarize_pkg(pkg_file, macos_config):
                        print("[WARNING] PKG notarization failed, but continuing...")
                except Exception as e:
                    print(f"[WARNING] PKG notarization error: {e}")

            return True

        except subprocess.TimeoutExpired:
            print(f"[ERROR] macOS PKG installer creation timed out")
            return False
        except FileNotFoundError as e:
            print(f"[ERROR] Required file not found during PKG creation: {e}")
            return False
        except PermissionError as e:
            print(f"[ERROR] Permission denied during PKG creation: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] macOS PKG installer creation failed: {e}")
            import traceback
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return False



    def _create_pkg_installer(self, app_bundle_dir: Path, app_name: str, app_version: str, pkg_file: Path, macos_config: Dict[str, Any]) -> bool:
        """Create PKG installer using simplified component-based approach.

        Simplified method focusing on reliability:
        - Use only component-based packaging (most reliable)
        - Better error handling and validation
        - Reduced timeout and complexity
        """
        try:
            print(f"[PKG] Creating PKG installer: {pkg_file.name}")

            # Validate build environment first
            if not self._validate_macos_build_environment():
                return False

            # Validate app bundle exists and has proper structure
            if not self._validate_app_bundle(app_bundle_dir, app_name):
                return False

            # Get configuration values
            install_location = macos_config.get("install_location", "/Applications")
            bundle_identifier = macos_config.get("bundle_identifier", f"com.ecan.{app_name.lower()}")

            # Use component-based packaging (most reliable method)
            print(f"[PKG] Creating component-based package...")
            component_cmd = [
                "pkgbuild",
                "--component", str(app_bundle_dir),
                "--identifier", bundle_identifier,
                "--version", app_version,
                "--install-location", install_location,
                str(pkg_file)
            ]

            result = subprocess.run(
                component_cmd,
                capture_output=True,
                text=True,
                timeout=300  # Reduced timeout to 5 minutes
            )

            if result.returncode != 0:
                print(f"[ERROR] pkgbuild failed:")
                print(f"[ERROR] Command: {' '.join(component_cmd)}")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            # Verify the PKG was created and has reasonable size
            if not pkg_file.exists():
                print(f"[ERROR] PKG file was not created: {pkg_file}")
                return False

            file_size = pkg_file.stat().st_size
            if file_size < 1024:  # Less than 1KB is definitely wrong
                print(f"[ERROR] PKG file too small ({file_size} bytes), likely corrupted")
                pkg_file.unlink()  # Remove invalid file
                return False

            print(f"[SUCCESS] PKG created successfully: {file_size / (1024*1024):.1f} MB")
            return True

        except subprocess.TimeoutExpired:
            print(f"[ERROR] PKG creation timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"[ERROR] PKG creation failed: {e}")
            return False

    def _validate_macos_build_environment(self) -> bool:
        """Validate macOS build environment and required tools"""
        try:
            import platform
            if platform.system() != "Darwin":
                print("[ERROR] PKG creation requires macOS")
                return False

            # Check required tools
            required_tools = ['pkgbuild', 'productbuild']
            for tool in required_tools:
                if not shutil.which(tool):
                    print(f"[ERROR] Required tool not found: {tool}")
                    print(f"[ERROR] Please install Xcode Command Line Tools: xcode-select --install")
                    return False

            # Check macOS version (optional warning)
            try:
                version_output = subprocess.check_output(['sw_vers', '-productVersion'], text=True).strip()
                major_version = float('.'.join(version_output.split('.')[:2]))
                if major_version < 11.0:
                    print(f"[WARNING] macOS {version_output} may have limited PKG support")
            except:
                pass  # Version check is optional

            return True

        except Exception as e:
            print(f"[ERROR] Environment validation failed: {e}")
            return False

    def _validate_app_bundle(self, app_bundle_dir: Path, app_name: str) -> bool:
        """Validate app bundle structure"""
        if not app_bundle_dir.exists():
            print(f"[ERROR] App bundle not found: {app_bundle_dir}")
            return False

        # Check for essential app bundle components
        info_plist = app_bundle_dir / "Contents" / "Info.plist"
        executable_dir = app_bundle_dir / "Contents" / "MacOS"
        executable_file = executable_dir / app_name

        if not info_plist.exists():
            print(f"[ERROR] Invalid app bundle: Info.plist missing")
            return False
        if not executable_dir.exists():
            print(f"[ERROR] Invalid app bundle: MacOS directory missing")
            return False
        if not executable_file.exists():
            print(f"[ERROR] Invalid app bundle: Executable missing ({executable_file})")
            return False

        print(f"[PKG] App bundle validation passed")
        return True

    def _get_normalized_arch(self) -> str:
        """Get normalized architecture name for consistent naming across the build system"""
        import platform

        # Get architecture from environment or system
        arch = os.environ.get('BUILD_ARCH', platform.machine())

        # Normalize architecture names
        arch_map = {
            'x86_64': 'amd64',
            'amd64': 'amd64',
            'i386': 'amd64',  # Fallback for older systems
            'arm64': 'aarch64',
            'aarch64': 'aarch64',
            'arm': 'aarch64'  # Fallback for ARM variants
        }

        normalized = arch_map.get(arch.lower(), 'amd64')  # Default to amd64
        print(f"[ARCH] Normalized architecture: {arch} -> {normalized}")
        return normalized

    def _remove_pkg_relocate_tags(self, component_pkg: Path, temp_dir: Path) -> None:
        """Remove relocate tags from PKG component PackageInfo to prevent installation issues"""
        try:
            print(f"[PKG] Fixing relocate issue in component package...")

            # Extract the component package
            extract_dir = temp_dir / "pkg_extract"
            extract_dir.mkdir(exist_ok=True)

            # Use xar to extract the package
            extract_cmd = ["xar", "-xf", str(component_pkg), "-C", str(extract_dir)]
            result = subprocess.run(extract_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[WARNING] Failed to extract component package: {result.stderr}")
                return

            # Find PackageInfo file - it might be in different locations
            possible_locations = [
                extract_dir / f"{component_pkg.stem}.pkg" / "PackageInfo",
                extract_dir / "PackageInfo",
                extract_dir / f"{component_pkg.name}" / "PackageInfo"
            ]

            package_info_file = None
            for location in possible_locations:
                if location.exists():
                    package_info_file = location
                    break

            if not package_info_file:
                print(f"[WARNING] PackageInfo not found in any of: {[str(loc) for loc in possible_locations]}")
                # List actual contents to debug
                try:
                    contents = list(extract_dir.rglob("*"))
                    print(f"[DEBUG] Extract directory contents: {[str(p) for p in contents[:10]]}")
                except:
                    pass
                return

            # Read and modify PackageInfo
            with open(package_info_file, 'r') as f:
                content = f.read()

            # Remove relocate tags comprehensively
            import re
            original_content = content

            # First, ensure relocatable is set to false
            content = re.sub(r'relocatable="true"', 'relocatable="false"', content)

            # Remove all relocate sections - handle both single line and multi-line
            # Remove complete relocate blocks with content
            content = re.sub(r'<relocate>.*?</relocate>', '', content, flags=re.DOTALL | re.MULTILINE)

            # Remove any remaining relocate opening/closing tags
            content = re.sub(r'<relocate[^>]*>', '', content)
            content = re.sub(r'</relocate>', '', content)

            # Clean up any extra whitespace left behind
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)

            if content != original_content:
                print(f"[PKG] Successfully removed relocate tags from PackageInfo")
                # Show what was removed for debugging
                removed_lines = len(original_content.splitlines()) - len(content.splitlines())
                print(f"[PKG] Removed {removed_lines} lines containing relocate information")
            else:
                print(f"[PKG] No relocate tags found to remove")

            # Write back the modified content
            with open(package_info_file, 'w') as f:
                f.write(content)

            # Repackage the component with optimizations
            print(f"[PKG] Repackaging component (this may take a few minutes)...")

            # Use optimized xar command with compression and parallel processing
            repackage_cmd = [
                "xar", "-cf", str(component_pkg),
                "-C", str(extract_dir),
                "--compression", "gzip",  # Use gzip compression for speed
                "."
            ]

            # Set up environment for faster I/O
            import os
            env = os.environ.copy()
            env['TMPDIR'] = str(temp_dir)  # Use our temp directory

            result = subprocess.run(
                repackage_cmd,
                capture_output=True,
                text=True,
                timeout=900,  # 15 minutes timeout
                env=env
            )

            if result.returncode != 0:
                print(f"[WARNING] Failed to repackage component: {result.stderr}")
            else:
                print(f"[PKG] Successfully fixed relocate issue")

        except Exception as e:
            print(f"[WARNING] Failed to fix relocate issue: {e}")

    def _create_postinstall_script(self, scripts_dir: Path, app_name: str, macos_config: Dict[str, Any]) -> None:
        """Create simplified postinstall script for macOS PKG installer"""
        try:
            install_location = macos_config.get("install_location", "/Applications")
            create_launchpad_shortcut = macos_config.get("create_launchpad_shortcut", True)

            postinstall_script = scripts_dir / "postinstall"

            # Create simplified postinstall script focusing on essential tasks only
            script_content = f"""#!/bin/bash
# eCan Post-Installation Script - Simplified Version
# Handles essential post-installation tasks only

set -e  # Exit on any error

APP_NAME="{app_name}"
APP_PATH="{install_location}/$APP_NAME.app"

echo "eCan Post-Install: Starting essential tasks"

# Verify application installation
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: Application not found at $APP_PATH"
    exit 1
fi

echo "eCan Post-Install: Application found at $APP_PATH"

# Set proper permissions for the application
echo "eCan Post-Install: Setting application permissions"
chmod -R 755 "$APP_PATH" 2>/dev/null || true

# Ensure executable is executable
EXECUTABLE_PATH="$APP_PATH/Contents/MacOS/$APP_NAME"
if [ -f "$EXECUTABLE_PATH" ]; then
    chmod +x "$EXECUTABLE_PATH" 2>/dev/null || true
    echo "eCan Post-Install: Set executable permissions"
else
    echo "WARNING: Executable not found at $EXECUTABLE_PATH"
fi

# Register application with Launch Services (if enabled)"""

            if create_launchpad_shortcut:
                script_content += f"""
echo "eCan Post-Install: Registering with Launch Services and Launchpad"

# Method 1: Register with lsregister (standard way)
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
    echo "eCan Post-Install: Using lsregister to register application"
    "$LSREGISTER" -f "$APP_PATH" 2>/dev/null || true

    # Force rebuild of Launch Services database
    "$LSREGISTER" -kill -r -domain local -domain system -domain user 2>/dev/null || true
    echo "eCan Post-Install: Launch Services database rebuilt"
else
    echo "WARNING: lsregister not found"
fi

# Method 2: Touch the Applications folder to trigger Finder refresh
echo "eCan Post-Install: Refreshing Applications folder"
touch "{install_location}" 2>/dev/null || true

# Method 3: Force Spotlight to reindex the Applications folder
echo "eCan Post-Install: Triggering Spotlight reindex"
mdimport "{install_location}" 2>/dev/null || true

# Method 4: Notify system of new application (macOS 10.14+)
echo "eCan Post-Install: Notifying system of application installation"
if command -v notifyutil >/dev/null 2>&1; then
    notifyutil -p com.apple.LaunchServices.database 2>/dev/null || true
fi

# Method 5: Clear icon cache (helps with icon display issues)
echo "eCan Post-Install: Clearing icon cache"
if [ -d "/Library/Caches/com.apple.iconservices.store" ]; then
    rm -rf "/Library/Caches/com.apple.iconservices.store" 2>/dev/null || true
fi

# Clear user icon cache
USER_ICON_CACHE="$HOME/Library/Caches/com.apple.iconservices.store"
if [ -d "$USER_ICON_CACHE" ]; then
    rm -rf "$USER_ICON_CACHE" 2>/dev/null || true
fi

echo "eCan Post-Install: Application registration completed"
echo "eCan Post-Install: Note - It may take a few moments for the app to appear in Launchpad"
echo "eCan Post-Install: You can also find the app in /Applications/eCan.app"""

            script_content += f"""

# Final verification
if [ -d "$APP_PATH" ] && [ -f "$APP_PATH/Contents/Info.plist" ] && [ -f "$APP_PATH/Contents/MacOS/$APP_NAME" ]; then
    echo "eCan Post-Install: Installation verification passed"
else
    echo "ERROR: Installation verification failed"
    exit 1
fi

echo "eCan Post-Install: Tasks completed successfully"
echo "eCan is now installed and ready to use"

exit 0
"""

            # Write the script
            with open(postinstall_script, 'w', encoding='utf-8') as f:
                f.write(script_content)

            # Make script executable
            postinstall_script.chmod(0o755)

            print(f"[PKG] Created simplified postinstall script with features:")
            print(f"[PKG]   - Essential permissions setup")
            if create_launchpad_shortcut:
                print(f"[PKG]   - Launch Services registration")
            print(f"[PKG]   - Install location: {install_location}")
            print(f"[PKG]   - Simplified error handling for better reliability")

        except Exception as e:
            print(f"[WARNING] Failed to create postinstall script: {e}")

    def _create_simplified_distribution_xml(self, app_name: str, app_version: str, bundle_identifier: str, temp_dir: Path = None) -> str:
        """Create simplified distribution XML for productbuild"""
        
        distribution_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>{app_name} {app_version}</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="false" rootVolumeOnly="true"/>
    
    <!-- System requirements -->
    <installation-check script="pm_install_check();"/>
    <script>
    <![CDATA[
        function pm_install_check() {{
            if(!(system.compareVersions(system.version.ProductVersion, '11.0') >= 0)) {{
                my.result.title = 'Unable to install';
                my.result.message = 'This application requires macOS 11.0 or later.';
                my.result.type = 'Fatal';
                return false;
            }}
            return true;
        }}
    ]]>
    </script>

    <pkg-ref id="{bundle_identifier}"/>
    
    <choices-outline>
        <line choice="default">
            <line choice="{bundle_identifier}"/>
        </line>
    </choices-outline>
    
    <choice id="default" title="{app_name} Installation" description="This will install {app_name} to /Applications."/>
    <choice id="{bundle_identifier}" visible="false">
        <pkg-ref id="{bundle_identifier}"/>
    </choice>
    
    <pkg-ref id="{bundle_identifier}" version="{app_version}" onConclusion="none">
        {app_name}-component.pkg
    </pkg-ref>
</installer-gui-script>"""

        return distribution_xml

    def _create_distribution_xml(self, app_name: str, app_version: str, macos_config: Dict[str, Any], temp_dir: Path = None) -> str:
        """Create distribution XML for productbuild"""
        pkg_config = macos_config.get("pkg", {})

        # Get configuration values
        title = pkg_config.get("title", f"{app_name} {app_version}")
        welcome_file = pkg_config.get("welcome_file", "")
        readme_file = pkg_config.get("readme_file", "")
        license_file = pkg_config.get("license_file", "")
        if welcome_file and Path(welcome_file).exists():
            welcome_section = f'<welcome file="{welcome_file}"/>'

        # Build readme section
        readme_section = ""
        if readme_file and Path(readme_file).exists():
            readme_section = f'<readme file="{readme_file}"/>'

        # Build license section
        license_section = ""
        if license_file and Path(license_file).exists():
            license_section = f'<license file="{license_file}"/>'

        # Build conclusion section
        conclusion_section = ""
        if conclusion_file and Path(conclusion_file).exists():
            conclusion_section = f'<conclusion file="{conclusion_file}"/>'

        # Check for icon file from configuration
        icon_section = ""
        if temp_dir:
            # Get icon from build configuration
            icon_name = None
            mime_type = None

            # Try to get macOS icon from app.icons.macos
            if hasattr(self, 'config') and self.config:
                # Access the config dictionary through the BuildConfig object
                config_dict = self.config.config if hasattr(self.config, 'config') else self.config
                app_config = config_dict.get('app', {})
                icons_config = app_config.get('icons', {})
                macos_icon = icons_config.get('macos')

                if macos_icon:
                    icon_name = macos_icon
                    if icon_name.endswith('.icns'):
                        mime_type = "image/x-icns"
                    elif icon_name.endswith('.ico'):
                        mime_type = "image/x-icon"
                    else:
                        mime_type = "image/x-icns"  # Default for macOS

            # Fallback to default icon names if not configured
            if not icon_name:
                icon_candidates = [
                    ("eCan.icns", "image/x-icns"),
                    ("eCan.ico", "image/x-icon"),
                    ("icon.icns", "image/x-icns")
                ]

                for candidate_name, candidate_mime in icon_candidates:
                    if (self.project_root / candidate_name).exists():
                        icon_name = candidate_name
                        mime_type = candidate_mime
                        break

            # Copy icon if found
            if icon_name:
                icon_file = self.project_root / icon_name
                if icon_file.exists():
                    temp_icon = temp_dir / icon_name
                    try:
                        shutil.copy2(icon_file, temp_icon)
                        icon_section = f'<background file="{icon_name}" mime-type="{mime_type}" scaling="proportional" alignment="center"/>'
                        print(f"[PKG] Added icon to installer: {icon_file}")
                    except Exception as e:
                        print(f"[WARNING] Failed to copy icon {icon_name} for PKG: {e}")
                else:
                    print(f"[WARNING] Configured icon file not found: {icon_file}")
            else:
                print(f"[INFO] No icon configured or found for PKG installer")

        # Get additional configuration
        install_location = macos_config.get("install_location", "/Applications")
        create_desktop_shortcut = macos_config.get("create_desktop_shortcut", False)
        create_launchpad_shortcut = macos_config.get("create_launchpad_shortcut", False)
        min_os_version = macos_config.get("min_os_version", "11.0")

        # Create installation summary
        install_summary = f"This will install {app_name} to {install_location}."
        if create_desktop_shortcut:
            install_summary += " A desktop shortcut will be created."
        if create_launchpad_shortcut:
            install_summary += " The application will be registered with Launchpad."

        distribution_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>{title}</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true"/>

    <!-- System requirements -->
    <installation-check script="pm_install_check();"/>
    <script>
    <![CDATA[
        function pm_install_check() {{
            if(!(system.compareVersions(system.version.ProductVersion, '{min_os_version}') >= 0)) {{
                my.result.title = 'Unable to install';
                my.result.message = 'This application requires macOS {min_os_version} or later.';
                my.result.type = 'Fatal';
                return false;
            }}
            return true;
        }}
    ]]>
    </script>

    {icon_section}
    {welcome_section}
    {readme_section}
    {license_section}
    {conclusion_section}

    <pkg-ref id="com.ecan.{app_name.lower()}"/>

    <choices-outline>
        <line choice="default">
            <line choice="com.ecan.{app_name.lower()}"/>
        </line>
    </choices-outline>

    <choice id="default" title="{app_name} Installation" description="{install_summary}"/>
    <choice id="com.ecan.{app_name.lower()}" visible="false">
        <pkg-ref id="com.ecan.{app_name.lower()}"/>
    </choice>

    <pkg-ref id="com.ecan.{app_name.lower()}" version="{app_version}" onConclusion="none">
        {app_name}-component.pkg
    </pkg-ref>
</installer-gui-script>"""

        return distribution_xml

    def _notarize_pkg(self, pkg_file: Path, macos_config: Dict[str, Any]) -> bool:
        """Notarize PKG file with Apple"""
        try:
            notarization_config = macos_config.get("notarization", {})
            apple_id = notarization_config.get("apple_id", "")
            team_id = notarization_config.get("team_id", "")
            app_password = notarization_config.get("app_password", "")

            if not all([apple_id, team_id, app_password]):
                print("[WARNING] Incomplete notarization configuration for PKG")
                return False

            print(f"[INSTALLER] Starting PKG notarization for: {pkg_file}")
            cmd = [
                "xcrun", "notarytool", "submit",
                str(pkg_file),
                "--apple-id", apple_id,
                "--team-id", team_id,
                "--password", app_password,
                "--wait"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900  # Reduced from 30 minutes to 15 minutes
            )

            if result.returncode != 0:
                print("[WARNING] PKG notarization failed:")
                print(f"[WARNING] Return code: {result.returncode}")
                print(f"[WARNING] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] PKG notarized successfully")

            # Staple notarization to PKG
            staple_cmd = ["xcrun", "stapler", "staple", str(pkg_file)]
            staple_result = subprocess.run(
                staple_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            if staple_result.returncode == 0:
                print("[SUCCESS] Notarization stapled to PKG")
            else:
                print("[WARNING] Failed to staple notarization to PKG")
            return True

        except Exception as e:
            print(f"[WARNING] PKG notarization failed: {e}")
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
                timeout=180  # Reduced to 3 minutes timeout
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
            
            # If Sparkle verification is enabled, perform additional checks
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
        """Check if OTA dependencies are available in third_party directory"""
        third_party_dir = self.project_root / "third_party"
        sparkle_dir = third_party_dir / "sparkle"
        winsparkle_dir = third_party_dir / "winsparkle"

        if not third_party_dir.exists():
            print("[OTA] Third-party dependencies directory not found")
            print("[OTA] OTA functionality will use fallback HTTP updates")
            return

        # Check for platform-specific dependencies
        platform = "darwin" if self.env.is_macos else "windows" if self.env.is_windows else "unknown"

        if platform == "darwin" and sparkle_dir.exists():
            install_info_file = sparkle_dir / "install_info.json"
        elif platform == "windows" and winsparkle_dir.exists():
            install_info_file = winsparkle_dir / "install_info.json"
        else:
            print(f"[OTA] No OTA dependencies found for platform: {platform}")
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
            
            # Sparkle specific verification
            self._verify_sparkle_installation(sparkle_dir if platform == "darwin" else winsparkle_dir, platform)
            
            if not installed_deps:
                print("[OTA] No dependencies found for current platform")
                
        except Exception as e:
            print(f"[OTA] Failed to read install info: {e}")
    
    def _verify_sparkle_installation(self, deps_dir: Path, platform: str):
        """Verify Sparkle/winSparkle installation"""
        if platform == "darwin":
            # Check Sparkle.framework
            sparkle_framework = deps_dir / "Sparkle.framework"
            if sparkle_framework.exists():
                print("[OTA] [OK] Sparkle.framework found")

                # Check key files
                sparkle_binary = sparkle_framework / "Versions" / "Current" / "Sparkle"
                sparkle_cli = deps_dir / "sparkle-cli"  # CLI is now in the sparkle directory root

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
            # Check winSparkle
            winsparkle_dll = deps_dir / "winsparkle.dll"
            if winsparkle_dll.exists():
                print("[OTA] [OK] winSparkle DLL verified")
            else:
                print("[OTA] [ERROR] winSparkle DLL not found")
    
    def _verify_sparkle_environment(self) -> bool:
        """Verify if Sparkle environment is complete"""
        third_party_dir = self.project_root / "third_party"

        if not third_party_dir.exists():
            print("[SPARKLE] [ERROR] Third-party dependencies directory not found")
            return False
        
        platform = "darwin" if self.env.is_macos else "windows" if self.env.is_windows else "unknown"
        
        if platform == "darwin":
            # Verify Sparkle.framework
            sparkle_dir = third_party_dir / "sparkle"
            sparkle_framework = sparkle_dir / "Sparkle.framework"
            if not sparkle_framework.exists():
                print("[SPARKLE] [ERROR] Sparkle.framework not found")
                return False

            # Check key components
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
            # Verify winSparkle
            winsparkle_dir = third_party_dir / "winsparkle"
            if not winsparkle_dir.exists():
                print("[SPARKLE] [ERROR] winSparkle directory not found")
                return False
            
            # Check key files
            winsparkle_dll = winsparkle_dir / "winsparkle.dll"
            if not winsparkle_dll.exists():
                print("[SPARKLE] [ERROR] winsparkle.dll not found")
                return False
            
            print("[SPARKLE] [OK] winSparkle verification passed")
            return True
        
        else:
            print(f"[SPARKLE] [WARN] Unsupported platform: {platform}")
            return True  # Don't block build
    
    def _show_result(self, start_time: float):
        """Display build results"""
        build_time = time.time() - start_time
        print("=" * 60)
        print(f"[SUCCESS] Build completed in {build_time:.2f} seconds")
        print(f"[INFO] Build mode: {self.mode}")
        print(f"[INFO] Platform: {self.env.platform}")
        print("=" * 60)


# Note: This file is now a pure library file and should not be run directly
# Please use build.py as the only entry point

def main():
    """Deprecated: Use build.py instead"""
    print("[ERROR] Please use build.py as the build entry point")
    print("[OK] Correct usage: python build.py fast")
    sys.exit(1)


if __name__ == "__main__":
    main()
