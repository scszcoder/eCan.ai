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
                cmd = "npm ci --legacy-peer-deps"
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
                install_cmd = "npm ci --legacy-peer-deps" if platform.system() == "Windows" else ["npm", "ci", "--legacy-peer-deps"]
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
    """PyInstaller builder using standard optimizer"""

    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path):
        self.config = config
        self.env = env
        self.project_root = project_root

    def build(self, mode: str, force: bool = False) -> bool:
        """Build application using standard optimizer"""
        print(f"[PYINSTALLER] Starting PyInstaller build using standard optimizer...")

        try:
            # 使用标准优化器
            from build_system.standard_optimizer import PyInstallerOptimizer
            
            optimizer = PyInstallerOptimizer()
            success = optimizer.build_optimized(mode)
            
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
AppName={installer_config.get('app_name', app_info.get('name', 'eCan'))}
AppVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}
AppPublisher={installer_config.get('app_publisher', 'eCan Team')}
DefaultDirName={{autopf}}\eCan
DefaultGroupName=eCan
OutputDir=..\dist
OutputBaseFilename=eCan-Setup
Compression={compression}
SolidCompression={solid_compression}
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
        """Build macOS installer using pkgbuild"""
        try:
            print("[INSTALLER] Building macOS installer...")

            installer_config = self.config.config.get("installer", {})
            macos_config = installer_config.get("macos", {})
            app_info = self.config.get_app_info()

            app_name = app_info.get("name", "eCan")
            app_version = app_info.get("version", "1.0.0")
            bundle_id = macos_config.get("bundle_identifier", "com.ecan.app")

            # Create app bundle structure
            app_bundle_dir = self.dist_dir / f"{app_name}.app"
            if not app_bundle_dir.exists():
                print(f"[ERROR] App bundle not found: {app_bundle_dir}")
                return False

            # Generate entitlements file if needed
            if macos_config.get("permissions"):
                self._create_entitlements_file(macos_config)

            # Create PKG installer
            pkg_file = self.dist_dir / f"{app_name}-{app_version}.pkg"

            # 使用 .app 作为 root，配合 --install-location /Applications 将 .app 安装到 /Applications
            cmd = [
                "pkgbuild",
                "--root", str(app_bundle_dir),
                "--identifier", bundle_id,
                "--version", app_version,
                "--install-location", "/Applications",
                str(pkg_file)
            ]

            print(f"[INSTALLER] Creating PKG: {pkg_file}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )

            if result.returncode != 0:
                print(f"[ERROR] PKG creation failed:")
                print(f"[ERROR] Return code: {result.returncode}")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] macOS installer created")

            # Optional: Code signing
            if macos_config.get("codesign", {}).get("enabled", False):
                if not self._codesign_pkg(pkg_file, macos_config):
                    return False

            # Optional: Notarization
            if macos_config.get("notarization", {}).get("enabled", False):
                if not self._notarize_pkg(pkg_file, macos_config):
                    print("[WARNING] Notarization failed, but continuing...")

            return True

        except Exception as e:
            print(f"[ERROR] macOS installer creation failed: {e}")
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

    def _notarize_pkg(self, pkg_file: Path, macos_config: Dict[str, Any]) -> bool:
        """Notarize PKG file with Apple"""
        try:
            notarization_config = macos_config.get("notarization", {})
            apple_id = notarization_config.get("apple_id", "")
            team_id = notarization_config.get("team_id", "")
            app_password = notarization_config.get("app_password", "")

            if not all([apple_id, team_id, app_password]):
                print("[WARNING] Incomplete notarization configuration")
                return False

            print(f"[INSTALLER] Starting notarization for: {pkg_file}")

            # Submit for notarization
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
                timeout=1800  # 30 minutes timeout for notarization
            )

            if result.returncode != 0:
                print(f"[WARNING] Notarization failed:")
                print(f"[WARNING] Return code: {result.returncode}")
                print(f"[WARNING] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] PKG notarized successfully")

            # Staple the notarization
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
                print("[WARNING] Failed to staple notarization")

            return True

        except Exception as e:
            print(f"[WARNING] Notarization failed: {e}")
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

    def build(self, force: bool = False, skip_frontend: bool = None, skip_installer: bool = False) -> bool:
        """Execute build"""
        start_time = time.time()

        print("=" * 60)
        print("eCan Cross-Platform Build System v9.0")
        print("=" * 60)

        try:
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
    print("❌ 请使用 build.py 作为构建入口点")
    print("✅ 正确用法: python build.py fast")
    sys.exit(1)


if __name__ == "__main__":
    main()
