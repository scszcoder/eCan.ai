#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Cross-Platform Build System v9.0
Simplified build script with standard optimizer integration
"""

import os
import sys
import json
import plistlib
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
        """Update version information in config and VERSION file"""
        # Update in-memory config
        if "app" in self.config:
            self.config["app"]["version"] = version
        if "installer" in self.config:
            self.config["installer"]["app_version"] = version
        
        # Update VERSION file so it gets bundled with the correct version
        version_file = Path(__file__).parent.parent / "VERSION"
        try:
            version_file.write_text(version + "\n", encoding="utf-8")
            print(f"[INFO] Updated VERSION file to: {version}")
        except Exception as e:
            print(f"[WARN] Failed to update VERSION file: {e}")
        
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
        """Build frontend (always build when directory exists)"""
        if not self.frontend_dir.exists():
            print("[WARNING] Frontend directory not found, skipping frontend build")
            return True
        # Allow CI or callers to skip frontend build when there are no GUI changes
        skip_env = os.environ.get("ECAN_SKIP_FRONTEND_BUILD", "0")
        if skip_env == "1" and not force:
            print("[FRONTEND] ECAN_SKIP_FRONTEND_BUILD=1 detected, skipping frontend build")
            return True
        print("[FRONTEND] Building frontend...")
        try:
            ok = self._run_build(force)
            if ok:
                print("[SUCCESS] Frontend build completed")
            return ok
        except Exception as e:
            print(f"[ERROR] Frontend build failed: {e}")
            return False
    
    # _install_dependencies removed: dependency install handled inside _run_build as needed
    
    def _run_build(self, force: bool = False) -> bool:
        """Execute build"""
        try:
            # If node_modules doesn't exist or force mode, run npm ci first
            need_install = force or not (self.frontend_dir / 'node_modules').exists()
            if need_install:
                print("[FRONTEND] Installing dependencies (optimized npm ci)...")
                # Optimized npm command for faster installation
                if platform.system() == "Windows":
                    install_cmd = "npm ci --prefer-offline --no-audit --no-fund --legacy-peer-deps"
                else:
                    install_cmd = ["npm", "ci", "--prefer-offline", "--no-audit", "--no-fund", "--legacy-peer-deps"]
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


# PyInstallerBuilder removed: unified build directly uses MiniSpecBuilder


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
        """Ensure Windows icon quality and configuration"""
        try:
            icon_file = self.project_root / "eCan.ico"

            # Validate ICO file existence
            if not icon_file.exists():
                print("[WARNING] eCan.ico not found")
                return False

            # Check ICO file size as a basic quality heuristic
            file_size = icon_file.stat().st_size
            if file_size < 1000:
                print(f"[WARNING] ICO file seems too small: {file_size} bytes")

            # Validate ICO file header structure
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
            # Ensure Windows icon quality before building installer
            if not self._ensure_windows_icon_quality():
                print("[WARNING] Windows icon quality check failed")

            installer_config = self.config.config.get("installer", {})
            windows_config = installer_config.get("windows", {})
            app_info = self.config.get_app_info()

            # AppId (GUID) from config for Inno Setup
            raw_app_id = windows_config.get("app_id", "6E1CCB74-1C0D-4333-9F20-2E4F2AF3F4A1")
            # Normalize: strip any braces and whitespace
            app_id = str(raw_app_id).strip().strip("{}").strip()
            # Pre-wrap with double braces for Inno Setup (to prevent constant expansion)
            app_id_wrapped = "{{" + app_id + "}}"

            # Get compression settings based on build mode
            compression_modes = installer_config.get("compression_modes", {})
            mode_config = compression_modes.get(self.mode, {})

            compression = mode_config.get("compression", installer_config.get("compression", "zip"))
            solid_compression = str(mode_config.get("solid_compression", installer_config.get("solid_compression", False))).lower()
            internal_compress_level = mode_config.get("internal_compress_level", "normal")
            disk_spanning = mode_config.get("disk_spanning", "no")

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
            # Add 'replacesameversion' flag to allow overwriting existing files
            onedir_dir = self.project_root / 'dist' / 'eCan'
            onefile_exe = self.project_root / 'dist' / 'eCan.exe'
            if onedir_dir.exists():
                files_section = "Source: \"..\\dist\\eCan\\*\"; DestDir: \"{app}\"; Flags: ignoreversion replacesameversion recursesubdirs createallsubdirs"
                run_target = "{app}\\eCan.exe"
            elif onefile_exe.exists():
                files_section = "Source: \"..\\dist\\eCan.exe\"; DestDir: \"{app}\"; Flags: ignoreversion replacesameversion"
                run_target = "{app}\\eCan.exe"
            else:
                files_section = "Source: \"..\\dist\\*.exe\"; DestDir: \"{app}\"; Flags: ignoreversion replacesameversion"
                run_target = "{app}\\eCan.exe"

            # Create standardized installer filename with platform and architecture
            arch = os.environ.get('BUILD_ARCH', 'amd64')
            if arch == 'x86_64':
                arch = 'amd64'
            app_version = installer_config.get('app_version', app_info.get('version', '1.0.0'))
            # Inno Setup VersionInfoVersion must be strictly numeric dotted (max 4 parts)
            file_version = self._sanitize_inno_file_version(app_version)
            installer_filename = f"eCan-{app_version}-windows-{arch}-Setup"

            # Get Windows-specific installer settings
            default_dir = windows_config.get('default_dir', installer_config.get('default_dir', '{pf}\\eCan'))
            default_group = windows_config.get('default_group', installer_config.get('default_group', 'eCan'))
            privileges_required = windows_config.get('privileges_required', installer_config.get('privileges_required', 'admin'))

            # Build Registry section for URL scheme
            registry_entries = windows_config.get('registry_entries', [])
            registry_section = ""
            if registry_entries:
                registry_section = "[Registry]\n"
                for entry in registry_entries:
                    root = entry.get('root', 'HKCU')
                    subkey = entry.get('subkey', '')
                    value_name = entry.get('value_name', '')
                    value_data = entry.get('value_data', '')
                    value_type = entry.get('value_type', 'string')
                    
                    # Convert value_type to Inno Setup format
                    if value_type == 'string':
                        type_str = 'string'
                    elif value_type == 'dword':
                        type_str = 'dword'
                    else:
                        type_str = 'string'
                    
                    # Escape double quotes in ValueData to satisfy Inno Setup syntax
                    # Example: "{app}" "%1" -> ""{app}"" ""%1""
                    if isinstance(value_data, str):
                        safe_value_data = value_data.replace('"', '""')
                    else:
                        safe_value_data = str(value_data)

                    # Build registry line
                    if value_name:
                        registry_section += (
                            f'Root: {root}; Subkey: "{subkey}"; '
                            f'ValueType: {type_str}; ValueName: "{value_name}"; '
                            f'ValueData: "{safe_value_data}"\n'
                        )
                    else:
                        registry_section += (
                            f'Root: {root}; Subkey: "{subkey}"; '
                            f'ValueType: {type_str}; ValueData: "{safe_value_data}"\n'
                        )
                registry_section += "\n"

            iss_content = f"""
; eCan Installer Script
; Compression: LZMA2 + Non-Solid + Normal level (with splash screen, 4-6s startup)
[Setup]
AppId={app_id_wrapped}
AppName={installer_config.get('app_name', app_info.get('name', 'eCan'))}
AppVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}
AppPublisher={installer_config.get('app_publisher', 'eCan Team')}
DefaultDirName={default_dir}
DefaultGroupName={default_group}
OutputDir=..\dist
OutputBaseFilename={installer_filename}
Compression={compression}
SolidCompression={solid_compression}
DiskSpanning={disk_spanning}
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
VersionInfoVersion={file_version}
WizardStyle=modern
; Language detection: automatically match system language, fallback to English if no match
LanguageDetectionMethod=uilanguage
UsePreviousLanguage=yes
ShowLanguageDialog=auto
; Prevent multiple installer instances when user double-clicks repeatedly
SetupMutex=eCanInstallerMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\\ChineseSimplified.isl"

[CustomMessages]
english.InitializeCaption=Initializing installer...
chinesesimplified.InitializeCaption=正在启动安装器...
english.RemoveUserDataPrompt=Do you want to remove user data and settings?
chinesesimplified.RemoveUserDataPrompt=是否删除用户数据和设置？

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

{dirs_section}[Files]
{files_section}

[Icons]
Name: "{{group}}\eCan"; Filename: "{run_target}"; IconFilename: "{run_target}"; IconIndex: 0
Name: "{{userdesktop}}\eCan"; Filename: "{run_target}"; IconFilename: "{run_target}"; IconIndex: 0; Tasks: desktopicon

{registry_section}[UninstallDelete]
Type: filesandordirs; Name: "{{localappdata}}\eCan"

[Code]
var
  SplashForm: TSetupForm;
  SplashLabel: TNewStaticText;

// Show splash screen to improve perceived startup speed
function InitializeSetup(): Boolean;
begin
  Result := True;
  try
    SplashForm := CreateCustomForm();
    SplashForm.BorderStyle := bsNone;
    SplashForm.ClientWidth := ScaleX(360);
    SplashForm.ClientHeight := ScaleY(120);
    SplashForm.Position := poScreenCenter;
    SplashForm.Color := clWhite;
    SplashForm.FormStyle := fsStayOnTop;

    SplashLabel := TNewStaticText.Create(SplashForm);
    SplashLabel.Parent := SplashForm;
    SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');
    SplashLabel.AutoSize := True;
    SplashLabel.Left := (SplashForm.ClientWidth - SplashLabel.Width) div 2;
    SplashLabel.Top := (SplashForm.ClientHeight - SplashLabel.Height) div 2;

    SplashForm.Show;
    SplashForm.Update;
  except
  end;
end;

// Initialize wizard form to stay on top
procedure InitializeWizard();
begin
  WizardForm.FormStyle := fsStayOnTop;
end;

// Close splash and bring main window to front
procedure CurPageChanged(CurPageID: Integer);
begin
  if Assigned(SplashForm) and (CurPageID = wpWelcome) then
  begin
    SplashForm.Close;
    SplashForm.Free;
    SplashForm := nil;
    WizardForm.BringToFront;
  end;
end;

// Handle installer step changes
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    WizardForm.FormStyle := fsNormal;
  end;
  
  if CurStep = ssPostInstall then
  begin
    // Reserved for shell refresh if needed
  end;
end;

// Optional: ask to remove user data on uninstall
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if MsgBox(ExpandConstant('{{cm:RemoveUserDataPrompt}}'), mbConfirmation, MB_YESNO) = IDYES then
  begin
    if DirExists(ExpandConstant('{{localappdata}}\\eCan')) then
    begin
      if not DelTree(ExpandConstant('{{localappdata}}\\eCan'), True, True, True) then
        MsgBox('Could not remove user data directory. You may need to remove it manually.', mbInformation, MB_OK);
    end;
  end;
end;

[Run]
Filename: "{run_target}"; Description: "{{cm:LaunchProgram,eCan}}"; Flags: nowait postinstall skipifsilent
"""

            iss_file = self.project_root / "build" / "setup.iss"
            iss_file.parent.mkdir(exist_ok=True)

            # Write script as UTF-8 with BOM so ISCC on CI treats it as Unicode, avoiding ANSI mojibake
            with open(iss_file, 'w', encoding='utf-8-sig') as f:
                f.write(iss_content)

            return iss_file

        except Exception as e:
            print(f"[ERROR] Failed to create Inno Setup script: {e}")
            return None

    def _sanitize_inno_file_version(self, version: str) -> str:
        """Sanitize semantic version to Inno-compatible file version.

        Inno Setup requires a dotted numeric version (up to 4 integers), e.g., 1.2.3.0.
        This converts versions like '0.0.0-gui-v2-cc252e9f' -> '0.0.0.0'.
        """
        try:
            import re
            # Extract numeric components from the start of the version string
            # Split by non-digit characters but keep dots between numeric runs
            # First, keep only digits and dots at the beginning
            match = re.match(r"^(\d+(?:\.\d+)*)", str(version))
            core = match.group(1) if match else "0.0.0"
            parts = [p for p in core.split('.') if p.isdigit()]
            # Ensure at least 3 parts
            while len(parts) < 3:
                parts.append('0')
            # Limit to 4 parts; if more, truncate; if exactly 3, add a trailing 0
            parts = parts[:4]
            if len(parts) == 3:
                parts.append('0')
            # Remove leading zeros normalization (but keep '0' if part is empty)
            norm = [str(int(p)) if p.isdigit() else '0' for p in parts]
            return '.'.join(norm)
        except Exception:
            return '1.0.0.0'

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

            # Remove /Q (Quiet) to show detailed compilation output including language processing
            cmd = [iscc_path, str(iss_file)]

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=1800  # 30 minutes timeout
            )

            # Print Inno Setup output for debugging (especially language compilation)
            if result.stdout:
                print("[INSTALLER] Inno Setup output:")
                for line in result.stdout.splitlines():
                    print(f"  {line}")

            if result.returncode != 0:
                print(f"[ERROR] Inno Setup compilation failed:")
                print(f"[ERROR] Return code: {result.returncode}")
                if result.stdout:
                    print(f"[ERROR] STDOUT: {result.stdout}")
                if result.stderr:
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

            # Note: For Windows distribution, we rely on Inno Setup installer
            # which packages the complete dist/eCan/ directory structure.
            # No need to create separate ZIP or standalone exe files.
            print(f"[INFO] Windows distribution handled by Inno Setup installer")
            print(f"[INFO] Installer: eCan-{app_version}-windows-{arch}-Setup.exe")

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

            # Bundle winSparkle DLL to expected locations for validation and runtime
            try:
                self._bundle_winsparkle_dll()
            except Exception as e:
                print(f"[WARNING] Failed to bundle winSparkle DLL: {e}")

        except Exception as e:
            print(f"[WARNING] Failed to create standardized Windows artifacts: {e}")

    def _bundle_winsparkle_dll(self) -> None:
        """Ensure winSparkle DLL is copied into app bundle for OTA updates.

        Sources:
          - project_root/third_party/winsparkle/winsparkle.dll (installed by setup-ota-deps)

        Target:
          - dist/eCan/third_party/winsparkle/winsparkle.dll (included by Inno Setup when using onedir)
        
        Note: Only copies to the app bundle directory, not dist/third_party/ (removes redundancy)
        """
        third_party_dir = self.project_root / "third_party" / "winsparkle"
        src_dll = third_party_dir / "winsparkle.dll"
        if not src_dll.exists():
            # Also try ota build output as fallback
            alt_src = self.project_root / "ota" / "build" / "winsparkle" / "winsparkle.dll"
            if alt_src.exists():
                src_dll = alt_src
        if not src_dll.exists():
            print("[OTA] [WARN] winSparkle source DLL not found; skipping bundle")
            return

        # Only copy to app bundle directory (dist/eCan/third_party/)
        # This is what gets packaged into the installer
        app_bundle_dir = self.dist_dir / "eCan"
        if not app_bundle_dir.exists():
            print("[OTA] [WARN] App bundle directory not found, skipping winSparkle copy")
            return
            
        dst_winsparkle = app_bundle_dir / "third_party" / "winsparkle"
        dst_winsparkle.mkdir(parents=True, exist_ok=True)
        
        import shutil
        try:
            shutil.copy2(src_dll, dst_winsparkle / "winsparkle.dll")
            print(f"[OTA] [OK] Copied winSparkle to {dst_winsparkle / 'winsparkle.dll'}")
        except Exception as e:
            print(f"[OTA] [ERROR] Failed to copy winSparkle: {e}")

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

            pkg_config = macos_config.get("pkg", {})
            fast_pkg_mode = (self.mode == "fast")
            fix_permissions_flag = pkg_config.get("fix_permissions", True)
            prune_payload_flag = pkg_config.get("prune_payload", True)
            use_productbuild = pkg_config.get("use_productbuild", not fast_pkg_mode)

            if fast_pkg_mode:
                print("[PKG] ⚡ FAST mode enabled - optimizing for speed")
                if fix_permissions_flag or prune_payload_flag:
                    print("[PKG] Skipping payload optimizations for faster build")
                fix_permissions_flag = False  # Skip permission fixes
                prune_payload_flag = False    # Skip file pruning
                use_productbuild = False      # Skip productbuild (use component PKG directly)
                print("[PKG] Fast mode optimizations applied")

            # Optionally fix app bundle permissions to ensure system-wide install works
            if fix_permissions_flag:
                try:
                    self._fix_app_permissions(app_bundle_dir)
                    print("[PKG] Fixed app bundle permissions")
                except Exception as e:
                    print(f"[PKG] Warning: Failed to fix app permissions: {e}")

            # Create PKG using pkgbuild (component-based)
            success = self._create_pkg_installer(
                app_bundle_dir,
                app_name,
                app_version,
                pkg_file,
                macos_config,
                fix_permissions_flag,
                prune_payload_flag,
                use_productbuild
            )

            if not success:
                return False

            if not pkg_file.exists() or pkg_file.stat().st_size == 0:
                print(f"[ERROR] PKG file not created or empty: {pkg_file}")
                return False

            print(f"[SUCCESS] macOS PKG created: {pkg_file} ({pkg_file.stat().st_size / (1024*1024):.1f} MB)")

            # Verify PKG package integrity
            self._verify_pkg_integrity(pkg_file, app_name)

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



    def _create_pkg_installer(
        self,
        app_bundle_dir: Path,
        app_name: str,
        app_version: str,
        pkg_file: Path,
        macos_config: Dict[str, Any],
        fix_permissions: bool,
        prune_payload: bool,
        use_productbuild: bool
    ) -> bool:
        """Create PKG installer using two-step approach to ensure correct installation path.

        Two-step method for reliable installation to /Applications:
        1. Create component package with pkgbuild
        2. Create final installer with productbuild and distribution file
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
            install_location = macos_config.get("install_location", "/Applications") or "/Applications"
            if not install_location.startswith("/"):
                install_location = f"/{install_location}"
            bundle_identifier = macos_config.get("bundle_identifier", f"com.ecan.{app_name.lower()}")

            # Create temporary directory for intermediate files
            temp_dir = self.project_root / "build" / "pkg_temp"
            if temp_dir.exists():
                # Be robust against CodeResources permission quirks
                shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)

            print(f"[PKG] Creating PKG installer using root payload method with forced system domain...")

            # Step 1: Create payload directory structure honoring install_location
            payload_dir = temp_dir / "payload"
            if payload_dir.exists():
                shutil.rmtree(payload_dir, ignore_errors=True)

            relative_install_root = install_location.lstrip("/")
            if relative_install_root:
                target_parent = payload_dir / relative_install_root
            else:
                target_parent = payload_dir
            target_parent.mkdir(parents=True, exist_ok=True)

            target_app = target_parent / f"{app_name}.app"

            if target_app.exists():
                shutil.rmtree(target_app, ignore_errors=True)

            print(f"[PKG] Preparing payload at {target_app}")

            # Use optimized copy method for faster payload creation
            copy_success = False
            start_time = time.perf_counter()
            
            # Try ditto first (fastest on macOS)
            if shutil.which("ditto"):
                try:
                    cmd = ["ditto", "--noqtn", "--norsrc", str(app_bundle_dir), str(target_app)]
                    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
                    copy_success = True
                    duration = time.perf_counter() - start_time
                    print(f"[PKG] [OK] Copied using ditto ({duration:.2f}s)")
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print(f"[PKG] ditto failed, falling back to copytree")

            # Fallback to optimized copytree
            if not copy_success:
                # Use copy2 for better performance with large files
                shutil.copytree(
                    app_bundle_dir, 
                    target_app, 
                    symlinks=True, 
                    dirs_exist_ok=True,
                    copy_function=shutil.copy2  # Faster than default copy function
                )
                duration = time.perf_counter() - start_time
                print(f"[PKG] [OK] Copied using copytree ({duration:.2f}s)")
            
            # Fix permissions for the app in payload
            if fix_permissions:
                self._fix_app_permissions(target_app)
                print(f"[PKG] Fixed permissions for app in payload: {target_app}")

            # Prune unnecessary files to shrink payload size
            if prune_payload:
                self._prune_app_bundle(target_app)
            
            # Create scripts directory and install/uninstall scripts
            scripts_dir = temp_dir / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            
            app_install_path = str((Path(install_location) / f"{app_name}.app"))
            app_install_dir = str(Path(app_install_path).parent)

            component_plist = temp_dir / "component.plist"
            self._create_component_plist(
                component_plist,
                bundle_identifier=bundle_identifier,
                app_name=app_name,
                app_version=app_version,
                install_location=install_location
            )
            
            # Create preinstall script to handle existing installations
            preinstall_script = scripts_dir / "preinstall"
            preinstall_content = f'''#!/bin/bash
# Preinstall script for {app_name}
APP_PATH="{app_install_path}"

if [ -d "$APP_PATH" ]; then
    echo "Removing existing {app_name}.app installation..."
    # Unregister from Launch Services before removal
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u "$APP_PATH" 2>/dev/null || true
    # Remove existing app
    rm -rf "$APP_PATH"
    echo "Existing installation removed"
fi

exit 0
'''
            with open(preinstall_script, 'w') as f:
                f.write(preinstall_content)
            preinstall_script.chmod(0o755)
            print(f"[PKG] Created preinstall script: {preinstall_script}")
            
            # Create postinstall script to register with Launch Services
            postinstall_script = scripts_dir / "postinstall"

            postinstall_content = f'''#!/bin/bash
# Postinstall script for {app_name}
APP_PATH="{app_install_path}"
APP_DIR="{app_install_dir}"

if [ -d "$APP_PATH" ]; then
    echo "Installing {app_name}.app to $APP_DIR"
    
    # Fix app bundle permissions to ensure proper execution
    chmod -R 755 "$APP_PATH/Contents/MacOS"
    chmod 644 "$APP_PATH/Contents/Info.plist"
    
    # Register with Launch Services to make app visible in Launchpad and Spotlight
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_PATH"
    
    # Touch install directory to refresh Finder
    touch "$APP_DIR"
    
    # Gentle Launchpad refresh without visual disruption
    # This method updates the database without forcing a Dock restart
    defaults write com.apple.dock ResetLaunchPad -bool true 2>/dev/null || true
    
    # Notify system of new application without forcing immediate refresh
    # The app will appear in Launchpad within a few seconds naturally
    echo "Note: {app_name} will appear in Launchpad shortly. If not visible immediately, try opening and closing Launchpad."
    
    echo "Successfully installed {app_name}.app to $APP_DIR"
    echo "App should now be visible in Launchpad and Applications folder"
else
    echo "Error: {app_name}.app not found at $APP_PATH"
    exit 1
fi

exit 0
'''
            with open(postinstall_script, 'w') as f:
                f.write(postinstall_content)
            postinstall_script.chmod(0o755)
            print(f"[PKG] Created postinstall script: {postinstall_script}")
            
            # Create component package using --root method
            component_pkg = temp_dir / f"{app_name}-component.pkg"
            pkgbuild_cmd = [
                "pkgbuild",
                "--root", str(payload_dir),
                "--identifier", bundle_identifier,
                "--version", app_version,
                "--install-location", "/",
                "--scripts", str(scripts_dir),
                "--component-plist", str(component_plist),
                "--ownership", "recommended",
                "--preserve-xattr",  # Preserve extended attributes
                str(component_pkg)
            ]
            
            print(f"[PKG] Running pkgbuild: {' '.join(pkgbuild_cmd)}")
            result = subprocess.run(pkgbuild_cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                print(f"[ERROR] pkgbuild failed: {result.stderr}")
                return False

            if not component_pkg.exists():
                print(f"[ERROR] Component PKG file was not created: {component_pkg}")
                return False
                
            component_pkg_size = component_pkg.stat().st_size if component_pkg.exists() else 0
            component_pkg_size_mb = component_pkg_size / (1024 * 1024)
            print(f"[PKG] Component package created: {component_pkg.name} ({component_pkg_size_mb:.1f} MB)")

            # Move component package into dedicated directory for productbuild lookup
            size_threshold_bytes = 1.5 * 1024 * 1024 * 1024  # 1.5 GB
            if use_productbuild and component_pkg_size > size_threshold_bytes:
                print(f"[PKG] Component PKG size {component_pkg_size_mb:.1f} MB exceeds fast-build threshold; skipping productbuild")
                use_productbuild = False

            if use_productbuild:
                packages_dir = temp_dir / "packages"
                packages_dir.mkdir(exist_ok=True)
                final_component_pkg = packages_dir / component_pkg.name
                if final_component_pkg.exists():
                    final_component_pkg.unlink()
                shutil.move(str(component_pkg), str(final_component_pkg))
                component_pkg = final_component_pkg

                relative_pkg_path = f"packages/{component_pkg.name}"

                # Step 2: Create Distribution that forces system domain and correct install location
                distribution_file = temp_dir / "distribution.xml"
                self._create_gui_distribution_file(
                    distribution_file=distribution_file,
                    app_name=app_name,
                    app_version=app_version,
                    bundle_identifier=bundle_identifier,
                    component_pkg_name=relative_pkg_path,
                    install_location=install_location
                )

                # Step 3: Build final product with productbuild
                productbuild_cmd = [
                    "productbuild",
                    "--distribution", str(distribution_file),
                    "--package-path", str(packages_dir),
                    str(pkg_file)
                ]
                print(f"[PKG] Running productbuild: {' '.join(productbuild_cmd)}")
                result = subprocess.run(productbuild_cmd, capture_output=True, text=True, timeout=1800)
                productbuild_output = (result.stdout or "") + (result.stderr or "")
                if result.returncode != 0:
                    print(f"[ERROR] productbuild failed: {result.stderr}")
                    return False
                if "No package found" in productbuild_output:
                    print(f"[ERROR] productbuild could not embed component package. Output: {productbuild_output.strip()}")
                    return False

                pkg_size_mb = pkg_file.stat().st_size / (1024 * 1024)
                print(f"[SUCCESS] PKG created successfully: {pkg_size_mb:.1f} MB")
                print(f"[PKG] Install location: /Applications (forced system domain)")
            else:
                # Directly use the component package as final PKG for faster builds
                if pkg_file.exists():
                    try:
                        pkg_file.unlink()
                    except Exception:
                        pass
                shutil.move(str(component_pkg), str(pkg_file))
                pkg_size_mb = pkg_file.stat().st_size / (1024 * 1024)
                print(f"[SUCCESS] Component PKG ready: {pkg_size_mb:.1f} MB")
                print(f"[PKG] Install location: /Applications (component installer)")
            
            # Clean up temporary directory
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    print(f"[PKG] Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                print(f"[WARNING] Could not clean up temporary directory: {e}")
            
            return True

        except subprocess.TimeoutExpired as timeout_err:
            minutes = getattr(timeout_err, 'timeout', 0) / 60 if getattr(timeout_err, 'timeout', None) else 0
            if minutes:
                print(f"[ERROR] PKG creation timed out after {minutes:.1f} minutes")
            else:
                print("[ERROR] PKG creation timed out")
            return False
        except Exception as e:
            print(f"[ERROR] macOS PKG installer creation failed: {e}")
            import traceback
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return False

    def _create_distribution_file(self, distribution_file: Path, app_name: str, app_version: str, bundle_identifier: str, install_location: str, component_pkg: Path) -> None:
        """Create distribution XML file for productbuild to ensure correct install location"""
        
        # Calculate package size for installKBytes
        pkg_size_kb = int(component_pkg.stat().st_size / 1024) if component_pkg.exists() else 700000
        
        distribution_xml = f'''<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>{app_name}</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="false" rootVolumeOnly="true" />
    <choices-outline>
        <line choice="default">
            <line choice="{bundle_identifier}"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="{bundle_identifier}" visible="false">
        <pkg-ref id="{bundle_identifier}"/>
    </choice>
    <pkg-ref id="{bundle_identifier}" version="{app_version}" installKBytes="{pkg_size_kb}" onConclusion="none">{component_pkg.name}</pkg-ref>
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
</installer-gui-script>'''

        with open(distribution_file, 'w', encoding='utf-8') as f:
            f.write(distribution_xml)
        
        print(f"[PKG] Created distribution file: {distribution_file}")
        print(f"[PKG] Target install location: {install_location}")

    def _create_component_plist(self, plist_path: Path, bundle_identifier: str, app_name: str, app_version: str, install_location: str) -> None:
        """Write component bundle metadata so the installer always targets /Applications."""
        relative_root = Path(install_location.lstrip("/")) / f"{app_name}.app"
        relative_path = str(relative_root).strip("/")
        if not relative_path:
            relative_path = f"{app_name}.app"

        bundle_entry = {
            "BundleIsRelocatable": False,
            "BundleIdentifier": bundle_identifier,
            "BundleName": app_name,
            "BundleVersion": app_version,
            "RootRelativeBundlePath": relative_path
        }

        plist_path.write_bytes(plistlib.dumps([bundle_entry]))

    def _create_gui_distribution_file(self, distribution_file: Path, app_name: str, app_version: str, bundle_identifier: str, component_pkg_name: str, install_location: str) -> None:
        """Create distribution XML file that forces system domain installation."""
        pkg_size_kb = 700000
        try:
            component_pkg_path = (distribution_file.parent / component_pkg_name).resolve()
            if not component_pkg_path.exists():
                fallback_path = distribution_file.parent / "packages" / Path(component_pkg_name).name
                if fallback_path.exists():
                    component_pkg_path = fallback_path
            if component_pkg_path.exists():
                pkg_size_kb = int(component_pkg_path.stat().st_size / 1024)
        except Exception:
            pass

        distribution_xml = f'''<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>{app_name}</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true" enable_currentUserHome="false" enable_anywhere="false"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true"/>
    <pkg-ref id="{bundle_identifier}"/>
    <choices-outline>
        <line choice="default">
            <line choice="{bundle_identifier}"/>
        </line>
    </choices-outline>
    <choice id="default" title="{app_name} Installation" description="Install {app_name} to {install_location}"/>
    <choice id="{bundle_identifier}" visible="false">
        <pkg-ref id="{bundle_identifier}"/>
    </choice>
    <pkg-ref id="{bundle_identifier}" installLocation="{install_location}" version="{app_version}" auth="root">{component_pkg_name}</pkg-ref>
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
</installer-gui-script>'''

        with open(distribution_file, 'w', encoding='utf-8') as f:
            f.write(distribution_xml)
        print(f"[PKG] Created distribution file with forced system domain and installLocation: {install_location}")

    def _fix_app_permissions(self, app_bundle_dir: Path) -> None:
        """Fix app bundle permissions to ensure installer can write to /Applications.
        Directories: 755, Files: 644, Executables in Contents/MacOS: 755
        Also fixes PyInstaller permission issues with CodeResources and other files.
        """
        import stat
        import os

        if not app_bundle_dir.exists():
            return
        
        # First, ensure we can modify all files (fix PyInstaller permission issues)
        try:
            # Recursively make all files and directories writable
            for root, dirs, files in os.walk(app_bundle_dir):
                # Fix directory permissions
                for d in dirs:
                    dir_path = Path(root) / d
                    try:
                        dir_path.chmod(0o755)
                    except (OSError, PermissionError):
                        pass  # Continue if we can't fix permissions
                
                # Fix file permissions
                for f in files:
                    file_path = Path(root) / f
                    try:
                        # Make file writable first, then set proper permissions
                        file_path.chmod(0o644)
                        # Special handling for executables and CodeResources
                        if f == 'CodeResources' or file_path.suffix in ['.so', '.dylib'] or 'MacOS' in str(file_path):
                            file_path.chmod(0o755)
                    except (OSError, PermissionError):
                        pass  # Continue if we can't fix permissions
        except Exception as e:
            print(f"[WARNING] Could not fix all permissions: {e}")
            # Continue anyway

        # Fix directory permissions
        for p in app_bundle_dir.rglob("*"):
            try:
                if p.is_dir():
                    p.chmod(0o755)
                elif p.is_file():
                    # Executables in Contents/MacOS should be 755
                    if "Contents/MacOS" in str(p):
                        p.chmod(0o755)
                    else:
                        # Regular files 644
                        mode = p.stat().st_mode
                        # Preserve execute bit if already set
                        if mode & stat.S_IXUSR:
                            p.chmod(0o755)
                        else:
                            p.chmod(0o644)
            except Exception:
                # Best-effort; skip errors
                continue

    def _prune_app_bundle(self, app_bundle_dir: Path) -> None:
        """Remove cache/test artifacts from the payload to reduce PKG size."""
        if not app_bundle_dir.exists():
            return

        try:
            before_bytes = self._get_directory_size(app_bundle_dir)
            prune_dirs = {"__pycache__", "tests", "test", "testing"}
            prune_suffixes = {".pyc", ".pyo", ".pyd", ".log", ".map", ".pdb", ".tmp"}

            removed_items = 0
            removed_bytes = 0

            for root, dirs, files in os.walk(app_bundle_dir, topdown=True):
                root_path = Path(root)

                # Remove unwanted directories first
                for d in list(dirs):
                    if d.lower() in prune_dirs:
                        dir_path = root_path / d
                        try:
                            size_before = self._get_directory_size(dir_path)
                            shutil.rmtree(dir_path, ignore_errors=True)
                            removed_bytes += size_before
                            removed_items += 1
                            dirs.remove(d)
                            print(f"[PKG] Pruned directory from payload: {dir_path}")
                        except Exception:
                            continue

                # Remove individual files by suffix
                for f in files:
                    file_path = root_path / f
                    if file_path.suffix.lower() in prune_suffixes:
                        try:
                            removed_bytes += file_path.stat().st_size
                            file_path.unlink()
                            removed_items += 1
                        except Exception:
                            continue

            after_bytes = self._get_directory_size(app_bundle_dir)
            delta_mb = (before_bytes - after_bytes) / (1024 * 1024)
            if delta_mb > 0.1:
                print(f"[PKG] Pruned payload by {delta_mb:.2f} MB ({removed_items} items)")
        except Exception as e:
            print(f"[PKG] Warning: Failed to prune payload: {e}")

    def _get_directory_size(self, directory: Path) -> int:
        total = 0
        try:
            for path in directory.rglob("*"):
                if path.is_file():
                    try:
                        total += path.stat().st_size
                    except OSError:
                        continue
        except Exception:
            return total
        return total


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
        conclusion_file = pkg_config.get("conclusion_file", "")
        
        # Build welcome section
        welcome_section = ""
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
    
    def _verify_pkg_integrity(self, pkg_file: Path, app_name: str) -> bool:
        """Verify PKG package integrity and contents"""
        try:
            print(f"[PKG] Verifying package integrity: {pkg_file.name}")
            
            # Check if pkgutil can read the package
            check_cmd = ["pkgutil", "--check-signature", str(pkg_file)]
            result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("[PKG] [OK] Package signature check passed")
            else:
                print(f"[PKG] [WARNING] Package signature check failed (expected for unsigned packages): {result.stderr.strip()}")
            
            # List package contents to verify structure
            list_cmd = ["pkgutil", "--files", str(pkg_file)]
            result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                files = result.stdout.strip().split('\n')
                app_files = [f for f in files if f.startswith(f'Applications/{app_name}.app')]
                
                if app_files:
                    print(f"[PKG] [OK] Package contains {len(app_files)} app bundle files")
                    
                    # Check for essential files
                    essential_files = [
                        f'Applications/{app_name}.app/Contents/Info.plist',
                        f'Applications/{app_name}.app/Contents/MacOS/{app_name}'
                    ]
                    
                    for essential in essential_files:
                        if essential in files:
                            print(f"[PKG] [OK] Essential file found: {essential}")
                        else:
                            print(f"[PKG] [WARNING] Essential file missing: {essential}")
                else:
                    print(f"[PKG] [WARNING] No app bundle files found in package")
                    return False
            else:
                print(f"[PKG] [WARNING] Could not list package contents: {result.stderr.strip()}")
                return False
            
            # Get package info
            info_cmd = ["pkgutil", "--pkg-info-plist", str(pkg_file)]
            result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("[PKG] [OK] Package info accessible")
                # Could parse plist here for more detailed verification
            else:
                print(f"[PKG] [WARNING] Could not get package info: {result.stderr.strip()}")
            
            print("[PKG] Package integrity verification completed")
            return True
            
        except subprocess.TimeoutExpired:
            print("[PKG] [WARNING] Package verification timed out")
            return False
        except Exception as e:
            print(f"[PKG] [WARNING] Package verification failed: {e}")
            return False

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

