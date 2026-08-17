#!/usr/bin/env python3
"""
Build Utilities
Common utility functions for the build system
"""

import os
import platform
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class PlatformHandler:
    """Minimal platform/arch helper consolidated into build_utils."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"

    AMD64 = "amd64"
    ARM64 = "arm64"

    def __init__(self):
        self._platform = self._detect_platform()
        self._architecture = self._detect_architecture()

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def architecture(self) -> str:
        return self._architecture

    @property
    def is_windows(self) -> bool:
        return self._platform == self.WINDOWS

    @property
    def is_macos(self) -> bool:
        return self._platform == self.MACOS

    @property
    def is_linux(self) -> bool:
        return self._platform == self.LINUX

    @property
    def is_arm64(self) -> bool:
        return self._architecture == self.ARM64

    @property
    def is_amd64(self) -> bool:
        return self._architecture == self.AMD64

    def get_platform_identifier(self) -> str:
        return f"{self._platform}-{self._architecture}"

    def _detect_platform(self) -> str:
        system = platform.system().lower()
        if system == "darwin":
            return self.MACOS
        if system == "windows":
            return self.WINDOWS
        if system == "linux":
            return self.LINUX
        return system

    def _detect_architecture(self) -> str:
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            return self.AMD64
        if machine in ("arm64", "aarch64"):
            return self.ARM64
        return machine


# Expose a singleton for existing call sites
platform_handler = PlatformHandler()


class LogLevel(Enum):
    """Log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class BuildLogger:
    """Unified build logger with component tracking"""
    
    def __init__(self, verbose: bool = False, log_file: Optional[Path] = None):
        self.verbose = verbose
        self.log_file = log_file
        self.start_time = time.time()
        self.component_times = {}
        self.error_count = 0
        self.warning_count = 0
        
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            
    def _format_message(self, level: LogLevel, component: str, message: str) -> str:
        """Format log message with timestamp and component"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"[{timestamp}] [{level.value}] [{component}] {message}"
        
    def _write_log(self, formatted_message: str) -> None:
        """Write to console and file if configured"""
        print(formatted_message)
        
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(formatted_message + '\n')
            except Exception:
                pass  # Don't fail build due to logging issues
                
    def debug(self, message: str, component: str = "BUILD") -> None:
        """Log debug message (only in verbose mode)"""
        if self.verbose:
            formatted = self._format_message(LogLevel.DEBUG, component, message)
            self._write_log(formatted)
            
    def info(self, message: str, component: str = "BUILD") -> None:
        """Log info message"""
        formatted = self._format_message(LogLevel.INFO, component, message)
        self._write_log(formatted)
        
    def warning(self, message: str, component: str = "BUILD") -> None:
        """Log warning message"""
        self.warning_count += 1
        formatted = self._format_message(LogLevel.WARNING, component, message)
        self._write_log(formatted)
        
    def error(self, message: str, component: str = "BUILD") -> None:
        """Log error message"""
        self.error_count += 1
        formatted = self._format_message(LogLevel.ERROR, component, message)
        self._write_log(formatted)
        
    def success(self, message: str, component: str = "BUILD") -> None:
        """Log success message"""
        formatted = self._format_message(LogLevel.SUCCESS, component, message)
        self._write_log(formatted)
        
    def start_component(self, component: str, description: str = "") -> None:
        """Start timing a build component"""
        self.component_times[component] = time.time()
        msg = f"Starting {component}"
        if description:
            msg += f": {description}"
        self.info(msg, component)
        
    def end_component(self, component: str, success: bool = True) -> float:
        """End timing a build component and return duration"""
        if component not in self.component_times:
            self.warning(f"Component {component} was not started", component)
            return 0.0
            
        duration = time.time() - self.component_times[component]
        status = "completed" if success else "failed"
        self.info(f"Component {component} {status} in {duration:.2f}s", component)
        
        if not success:
            self.error_count += 1
            
        return duration
        
    def get_stats(self) -> Dict[str, Any]:
        """Get build statistics"""
        return {
            "total_time": time.time() - self.start_time,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "component_count": len(self.component_times),
            "success": self.error_count == 0
        }


# Global logger instance
build_logger = None

def get_build_logger(verbose: bool = False, log_file: Optional[Path] = None) -> BuildLogger:
    """Get or create the global build logger"""
    global build_logger
    if build_logger is None:
        build_logger = BuildLogger(verbose=verbose, log_file=log_file)
    return build_logger


class URLSchemeBuildConfig:
    """Handle URL scheme configuration during build process"""
    
    @staticmethod
    def setup_url_scheme_for_build():
        """Setup URL scheme configuration for current platform"""
        system = platform.system().lower()
        
        if system == "darwin":
            return URLSchemeBuildConfig._setup_macos_build()
        elif system == "windows":
            return URLSchemeBuildConfig._setup_windows_build()
        elif system == "linux":
            return URLSchemeBuildConfig._setup_linux_build()
        else:
            print(f"[WARNING] [URL_SCHEME] URL scheme build setup not supported for platform: {system}")
            return False
    
    @staticmethod
    def _setup_macos_build():
        """Setup macOS build configuration"""
        try:
            # Ensure Info.plist exists in resource directory
            info_plist_path = Path("resource/Info.plist")
            if not info_plist_path.exists():
                print("[ERROR] [URL_SCHEME] Info.plist not found in resource directory")
                return False
            
            print("[URL_SCHEME] macOS URL scheme build configuration ready")
            print("[URL_SCHEME] Info.plist with ecan:// scheme configuration found")
            return True
            
        except Exception as e:
            print(f"[ERROR] [URL_SCHEME] Failed to setup macOS build configuration: {e}")
            return False

    # _setup_windows_build was previously duplicated in both this file and
    # build_system/url_scheme_config.py with subtle differences. The
    # url_scheme_config version now uses utils.app_config_loader helpers and
    # is the single source of truth — use URLSchemeBuildConfig._setup_windows_build.
    
    @staticmethod
    def _setup_linux_build():
        """Setup Linux build configuration"""
        try:
            # Create desktop entry template
            desktop_entry = """[Desktop Entry]
Name=eCan
Exec={executable_path} %u
Icon=ecan
Type=Application
MimeType=x-scheme-handler/ecan
Categories=Utility;Development;
Comment=eCan Automation Platform
"""
            
            # Save desktop entry template
            template_path = Path("build_system/ecan.desktop.template")
            with open(template_path, 'w') as f:
                f.write(desktop_entry)
            
            print("[URL_SCHEME] Linux URL scheme build configuration created")
            return True
            
        except Exception as e:
            print(f"[ERROR] [URL_SCHEME] Failed to setup Linux build configuration: {e}")
            return False
    
    @staticmethod
    def get_pyinstaller_options():
        """Get PyInstaller options for URL scheme support"""
        system = platform.system().lower()
        options = []
        
        if system == "darwin":
            # macOS specific options
            info_plist_path = Path("resource/Info.plist")
            if info_plist_path.exists():
                # Bundle identifier is per-app (e.g. com.ecan.app vs com.ecan.cn.app).
                # Pull it from the loaded build config so CN/Intl both get the
                # correct value instead of an Intl-only hardcode.
                try:
                    from build_system.url_scheme_config import _get_config_path
                    import json
                    _cfg = json.load(open(_get_config_path()))
                    bundle_id = _cfg.get('installer', {}).get('macos', {}).get('bundle_identifier', 'com.ecan.app')
                except Exception:
                    bundle_id = 'com.ecan.app'
                options.extend([
                    f"--osx-bundle-identifier={bundle_id}",
                    f"--info-plist={info_plist_path.absolute()}"
                ])
        
        elif system == "windows":
            # Windows specific options
            options.extend([
                # "--uac-admin",  # Request admin privileges for registry access - commented out to avoid elevation requirement
                "--version-file=build_system/version_info.txt"
            ])
        
        return options



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
        print("  - Parallel processing")
        print("  - Quick development builds")
        print("  - Estimated time: 2-5 minutes")
    elif mode == "dev":
        print("[DEV] Development Build Features:")
        print("  - Debug symbols included")
        print("  - Console output enabled")
        print("  - Parallel processing")
        print("  - Estimated time: 5-10 minutes")
    elif mode == "prod":
        print("[PROD] Production Build Features:")
        print("  - Maximum optimization")
        print("  - Binary compression")
        print("  - Debug info stripping")
        print("  - Estimated time: 15-25 minutes")

    print("=" * 60)


def standardize_artifact_names(version: str, arch: str = "amd64", app_short_name: str = "eCan") -> None:
    """Standardize build artifact filenames to match release.yml expected format.

    `app_short_name` must match the value of `app.name` in the per-app build
    config (and the `ECAN_APP_NAME`/`DIST_APP` env vars used by release.yml),
    so that the renamed artifacts land in dist/ under the same name that the
    upload steps look for. Defaults to "eCan" (Intl) for backward compatibility.
    """
    platform_name = platform.system()

    if platform_name == "Windows":
        _standardize_windows_artifacts(version, arch, app_short_name)
    elif platform_name == "Darwin":
        _standardize_macos_artifacts(version, arch, app_short_name)
    elif platform_name == "Linux":
        _standardize_linux_artifacts(version, arch, app_short_name)


def _standardize_windows_artifacts(version: str, arch: str, app_short_name: str):
    """Standardize Windows build artifacts"""
    dist_dir = Path("dist")

    # Find and standardize installer files (Setup.exe)
    setup_files = list(dist_dir.glob("*Setup*.exe"))
    for setup_file in setup_files:
        # Check if it's already in standardized format
        expected_name = f"{app_short_name}-{version}-windows-{arch}-Setup.exe"
        expected_path = dist_dir / expected_name

        if setup_file.name != expected_name:
            try:
                if not expected_path.exists():
                    shutil.move(setup_file, expected_path)
                    print(f"[RENAME] {setup_file.name} -> {expected_name}")
                    # Keep the corresponding .sig file in sync with the rename,
                    # otherwise OTA signing leaves an orphan signature under
                    # the pre-rename name and the upload step can't find it.
                    old_sig = dist_dir / f"{setup_file.name}.sig"
                    new_sig = expected_path.with_suffix(expected_path.suffix + ".sig")
                    if old_sig.exists() and not new_sig.exists():
                        shutil.move(old_sig, new_sig)
                        print(f"[RENAME] {old_sig.name} -> {new_sig.name}")
                else:
                    # Remove duplicate if standardized version already exists
                    setup_file.unlink()
                    print(f"[RENAME] Removed duplicate: {setup_file.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to rename {setup_file}: {e}")

    # Find and standardize executable files (main app)
    exe_files = [f for f in dist_dir.glob("*.exe") if "Setup" not in f.name]
    for exe_file in exe_files:
        expected_name = f"{app_short_name}-{version}-windows-{arch}.exe"
        expected_path = dist_dir / expected_name

        if exe_file.name != expected_name and app_short_name in exe_file.name:
            try:
                if not expected_path.exists():
                    shutil.move(exe_file, expected_path)
                    print(f"[RENAME] {exe_file.name} -> {expected_name}")
                else:
                    # Remove duplicate if standardized version already exists
                    exe_file.unlink()
                    print(f"[RENAME] Removed duplicate: {exe_file.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to rename {exe_file}: {e}")


def _standardize_macos_artifacts(version: str, arch: str, app_short_name: str = "eCan"):
    """Standardize macOS build artifacts"""
    dist_dir = Path("dist")

    # Standardize PKG file naming to match release.yml format
    expected_name = f"{app_short_name}-{version}-macos-{arch}.pkg"
    expected_path = dist_dir / expected_name

    # Find .pkg files that need renaming
    pkg_files = [f for f in dist_dir.glob("*.pkg") if f.name != expected_name]

    if pkg_files:
        # Rename the first PKG file found to the standardized name
        old_path = pkg_files[0]
        try:
            if not expected_path.exists():
                shutil.move(old_path, expected_path)
                print(f"[RENAME] {old_path.name} -> {expected_name}")
            else:
                # Remove duplicate if standardized version already exists
                old_path.unlink()
                print(f"[RENAME] Removed duplicate: {old_path.name}")
        except Exception as e:
            print(f"[RENAME] Warning: Failed to rename {old_path}: {e}")

        # Remove any additional PKG files to avoid duplicates
        for extra_pkg in pkg_files[1:]:
            try:
                extra_pkg.unlink()
                print(f"[RENAME] Removed duplicate: {extra_pkg.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to remove {extra_pkg}: {e}")

    # Verify the expected PKG exists
    if expected_path.exists():
        print(f"[RENAME] Standardized PKG ready: {expected_name}")
    else:
        print("[RENAME] No PKG installer found for macOS")


def _standardize_linux_artifacts(version: str, arch: str, app_short_name: str):
    """Standardize Linux build artifacts"""
    dist_dir = Path("dist")

    # Find executable files or AppImage
    executables = []
    for pattern in [app_short_name, "*.AppImage", "*.deb", "*.rpm"]:
        executables.extend(dist_dir.glob(pattern))

    if executables:
        old_path = executables[0]
        suffix = old_path.suffix or ""
        new_name = f"{app_short_name}-{version}-linux-{arch}{suffix}"
        new_path = dist_dir / new_name

        try:
            if old_path != new_path:
                shutil.move(old_path, new_path)
                print(f"[RENAME] {old_path.name} -> {new_name}")
                # Keep the corresponding .sig file in sync with the rename,
                # otherwise OTA signing leaves an orphan signature under
                # the pre-rename name and the upload step can't find it.
                old_sig = dist_dir / f"{old_path.name}.sig"
                new_sig = new_path.with_suffix(new_path.suffix + ".sig")
                if old_sig.exists() and not new_sig.exists():
                    shutil.move(old_sig, new_sig)
                    print(f"[RENAME] {old_sig.name} -> {new_sig.name}")
        except Exception as e:
            print(f"[RENAME] Warning: Failed to rename {old_path}: {e}")


def show_build_results():
    """Show build results"""
    print("\n[RESULT] Build Results:")

    dist_dir = Path("dist")
    if dist_dir.exists():
        files = list(dist_dir.iterdir())
        if files:
            print(f"[RESULT] Output directory: {dist_dir.absolute()}")
            for file in sorted(files):
                if file.is_file():
                    size_mb = file.stat().st_size / (1024 * 1024)
                    print(f"[RESULT]   {file.name} ({size_mb:.1f} MB)")
                elif file.is_dir():
                    print(f"[RESULT]   {file.name}/ (directory)")
        else:
            print("[RESULT] No files found in dist directory")
    else:
        print("[RESULT] No dist directory found")

    print("\n[OPTIMIZATION] Applied optimizations:")
    print("  - PyInstaller optimization")
    print("  - Binary compression")
    print("  - Debug info stripping")


def clean_macos_build_artifacts(build_path: Path) -> None:
    """Clean macOS build artifacts"""
    if not build_path.exists():
        return

    print(f"[CLEANUP] Cleaning {build_path}...")

    try:
        shutil.rmtree(build_path, ignore_errors=True)
        print(f"[CLEANUP] Cleaned {build_path}")
    except Exception as e:
        print(f"[CLEANUP] Warning: Failed to clean {build_path}: {e}")


def validate_browser_installation(path: Path) -> bool:
    """Build-only Playwright browser installation validator.

    This intentionally does NOT depend on `agent.playwright.core.utils` (or
    anything that pulls in `utils.logger_helper` / `colorlog`). The build runs
    on a CI runner that has no GUI, no user appdata dir, and no use for
    runtime-only modules — keeping that surface out of the build path makes
    the build deterministic and avoids module-level side effects from
    runtime singletons.

    Mirrors the validation logic the runtime agent uses, but in a self-contained
    stdlib-only form.
    """
    try:
        if not path or not path.exists():
            return False

        # Method 1: prefer browsers.json when present
        browsers_json = path / "browsers.json"
        if browsers_json.exists():
            try:
                import json
                with open(browsers_json, "r", encoding="utf-8") as f:
                    browsers_data = json.load(f)
                if isinstance(browsers_data, dict):
                    return True
            except Exception:
                pass

        # Method 2: fall back to looking for browser directories
        browser_dirs = [
            d for d in path.iterdir()
            if d.is_dir() and not d.name.startswith('.')
            and any(
                name in d.name.lower()
                for name in ('chromium', 'chrome', 'firefox', 'webkit', 'safari', 'edge')
            )
        ]
        if not browser_dirs:
            return False

        for browser_dir in browser_dirs:
            try:
                files = list(browser_dir.rglob("*"))
            except Exception:
                continue
            if len(files) >= 10:
                return True
            # Even with few files, accept if a recognizable executable is present
            for f in files:
                if not f.is_file():
                    continue
                if (f.name.lower().startswith(('chrome', 'chromium', 'firefox'))
                        or f.suffix.lower() in ('.exe', '.app')):
                    return True
        return False
    except Exception:
        return False


def prepare_third_party_assets() -> None:
    """Prepare third-party assets (Playwright browsers and browser-use extensions)"""
    print("[THIRD-PARTY] Preparing third-party assets...")

    try:
        # 1. Prepare Playwright browsers
        _prepare_playwright_simple()
        print("[THIRD-PARTY] Playwright assets prepared successfully")

    except Exception as e:
        print(f"[THIRD-PARTY] Playwright preparation failed: {e}")
        print("[THIRD-PARTY] This may cause issues with browser automation features")
        # Don't fail the build, just warn
    
    try:
        # 2. Prepare browser-use extensions
        _prepare_browser_extensions()
        print("[THIRD-PARTY] Browser extensions prepared successfully")
    
    except Exception as e:
        print(f"[THIRD-PARTY] Browser extensions preparation failed: {e}")
        print("[THIRD-PARTY] Extensions will be disabled at runtime")
        # Don't fail the build, just warn


def _prepare_browser_extensions() -> None:
    """Download browser-use extensions for offline bundling
    
    Note: This is only called if extensions don't already exist.
    GitHub Actions should download extensions during setup-playwright step.
    """
    import zipfile
    import tempfile
    import urllib.request
    import shutil
    from pathlib import Path
    
    # Extension definitions (from browser_use/browser/profile.py)
    EXTENSIONS = [
        {
            'name': 'uBlock Origin',
            'id': 'cjpalhdlnbpafiamejdnhcphjbkeiagm',
            'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dcjpalhdlnbpafiamejdnhcphjbkeiagm%26uc',
        },
        {
            'name': "I still don't care about cookies",
            'id': 'edibdbjcniadpccecjdfdjjppcpchdlm',
            'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dedibdbjcniadpccecjdfdjjppcpchdlm%26uc',
        },
        {
            'name': 'ClearURLs',
            'id': 'lckanjgmijmafbedllaakclkaicjfmnk',
            'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dlckanjgmijmafbedllaakclkaicjfmnk%26uc',
        },
        {
            'name': 'Force Background Tab',
            'id': 'gidlfommnbibbmegmgajdbikelkdcmcl',
            'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dgidlfommnbibbmegmgajdbikelkdcmcl%26uc',
        },
    ]
    
    # Check if extensions already exist (from GitHub Actions)
    extensions_dir = Path.cwd() / "third_party" / "browser_extensions"
    if extensions_dir.exists():
        ext_dirs = [d for d in extensions_dir.iterdir() if d.is_dir() and (d / 'manifest.json').exists()]
        if ext_dirs:
            print(f"[BUILD] Browser extensions already present: {extensions_dir}")
            print(f"[BUILD]   Found: {[d.name for d in ext_dirs]}")
            print("[BUILD] Skipping download (using existing extensions)")
            return
    
    print("[BUILD] Downloading browser-use extensions...")
    extensions_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    for ext in EXTENSIONS:
        print(f"[BUILD] {ext['name']}")
        ext_dir = extensions_dir / ext['id']
        crx_file = extensions_dir / f"{ext['id']}.crx"
        
        # Check if already exists
        if ext_dir.exists() and (ext_dir / 'manifest.json').exists():
            print(f"[BUILD]   Already cached, skipping")
            success_count += 1
            continue
        
        try:
            # Download
            if not crx_file.exists():
                print(f"[BUILD]   Downloading...")
                with urllib.request.urlopen(ext['url'], timeout=30) as response:
                    with open(crx_file, 'wb') as f:
                        f.write(response.read())
                print(f"[BUILD]   Downloaded: {crx_file.stat().st_size / 1024:.1f} KB")
            
            # Extract
            if ext_dir.exists():
                shutil.rmtree(ext_dir)
            ext_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                # Try ZIP extraction first
                with zipfile.ZipFile(crx_file, 'r') as zip_ref:
                    zip_ref.extractall(ext_dir)
            except zipfile.BadZipFile:
                # Handle CRX header
                with open(crx_file, 'rb') as f:
                    magic = f.read(4)
                    if magic != b'Cr24':
                        raise Exception('Invalid CRX file format')
                    version = int.from_bytes(f.read(4), 'little')
                    if version == 2:
                        pubkey_len = int.from_bytes(f.read(4), 'little')
                        sig_len = int.from_bytes(f.read(4), 'little')
                        f.seek(16 + pubkey_len + sig_len)
                    elif version == 3:
                        header_len = int.from_bytes(f.read(4), 'little')
                        f.seek(12 + header_len)
                    zip_data = f.read()
                
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                    temp_zip.write(zip_data)
                    temp_zip.flush()
                    with zipfile.ZipFile(temp_zip.name, 'r') as zip_ref:
                        zip_ref.extractall(ext_dir)
                    os.unlink(temp_zip.name)
            
            if not (ext_dir / 'manifest.json').exists():
                raise Exception('No manifest.json found')
            
            print(f"[BUILD]   Extracted successfully")
            success_count += 1
            
        except Exception as e:
            print(f"[BUILD]   [WARN] Failed: {e}")
    
    print(f"[BUILD] Successfully prepared: {success_count}/{len(EXTENSIONS)} extensions")


def _prepare_playwright_simple() -> None:
    """Simplified Playwright asset preparation"""
    import subprocess
    import sys
    import shutil
    from pathlib import Path

    target_path = Path.cwd() / "third_party" / "ms-playwright"

    # 1. Ensure playwright is installed
    try:
        subprocess.run([sys.executable, "-m", "pip", "show", "playwright"],
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("[BUILD] Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)

    # 2. Find existing cache or install browsers
    cache_path = _find_playwright_cache()
    if not cache_path:
        print("[BUILD] Installing Playwright browsers...")
        # Install to default location
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        cache_path = _find_playwright_cache()

        if not cache_path:
            raise RuntimeError("Failed to install or locate Playwright browsers")

    # 3. Copy to target location
    print(f"[BUILD] Copying Playwright assets: {cache_path} -> {target_path}")
    if target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)

    # Copy with symlinks preserved (important for macOS Chromium.app structure)
    # Note: symlinks=True preserves symbolic links, which is critical for browser functionality
    try:
        shutil.copytree(cache_path, target_path, symlinks=True, dirs_exist_ok=True)

        # Validate the copy using the build-only helper. We intentionally avoid
        # importing agent.playwright.core.utils here: that runtime module pulls
        # in utils.logger_helper / colorlog as a side effect, which has no
        # place in a CI build step.
        if not validate_browser_installation(target_path):
            raise RuntimeError(f"Browser installation validation failed after copy: {target_path}")

        print(f"[BUILD] ✅ Playwright browsers copied and validated successfully")
    except Exception as e:
        print(f"[PLAYWRIGHT] Copy failed: {e}")
        raise


def _find_playwright_cache() -> Path:
    """Find Playwright cache directory (simplified)"""
    import os
    import platform
    from pathlib import Path

    # Check environment variable first.  The constant name comes from the
    # runtime agent module, but we don't need to import that whole module
    # (which would pull utils.logger_helper → colorlog into the build process).
    # The literal matches agent.playwright.core.utils.PlaywrightCoreUtils.ENV_BROWSERS_PATH.
    env_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        env_path_obj = Path(env_path)
        if env_path_obj.exists():
            # Check for browser directories in the environment path
            browser_dirs = [d for d in env_path_obj.iterdir()
                           if d.is_dir() and any(browser in d.name.lower()
                           for browser in ['chromium', 'firefox', 'webkit'])]

            if browser_dirs:
                print(f"[BUILD] Found Playwright browsers in env path: {[d.name for d in browser_dirs]}")
                return env_path_obj

    # Platform-specific default paths
    if platform.system() == "Windows":
        possible_paths = [
            Path.home() / "AppData" / "Local" / "ms-playwright",
            Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright",
        ]
    elif platform.system() == "Darwin":  # macOS
        possible_paths = [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
            Path.home() / "Library" / "Application Support" / "eCan" / "ms-playwright",  # Custom application-specific path
        ]
    else:  # Linux
        possible_paths = [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / ".local" / "share" / "ms-playwright",
        ]

    # Find the first valid path by checking for browser directories
    for path in possible_paths:
        if path.exists():
            # Check for browser directories in each candidate path
            browser_dirs = [d for d in path.iterdir()
                           if d.is_dir() and any(browser in d.name.lower()
                           for browser in ['chromium', 'firefox', 'webkit'])]

            if browser_dirs:
                print(f"[BUILD] Found Playwright browsers: {[d.name for d in browser_dirs]}")
                return path

    return None


def validate_macos_app_bundle(app_bundle_path: Path) -> bool:
    """Simple macOS app bundle validation"""
    import platform

    if platform.system() != "Darwin":
        return True  # Skip on non-macOS

    if not app_bundle_path.exists():
        print(f"[VALIDATION] App bundle not found: {app_bundle_path}")
        return False

    print(f"[VALIDATION] Validating app bundle: {app_bundle_path}")

    # Basic structure check
    contents_dir = app_bundle_path / "Contents"
    if not contents_dir.exists():
        print("[VALIDATION] Contents directory missing")
        return False

    # Check for executable
    macos_dir = contents_dir / "MacOS"
    if not macos_dir.exists():
        print("[VALIDATION] MacOS directory missing")
        return False

    print("[VALIDATION] App bundle structure is valid")
    return True


def validate_build_config(verbose: bool = False) -> bool:
    """
    Validate basic correctness of build_config.json
    Check field definitions and package configurations
    """
    try:
        import json
        config_path = Path("build_system/build_config.json")

        if not config_path.exists():
            if verbose:
                print("[CONFIG] build_config.json not found")
            return False

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        pyinstaller_config = config.get("build", {}).get("pyinstaller", {})

        # Check required fields
        required_fields = ["collect_all", "collect_data_only", "hiddenimports", "excludes"]
        missing_fields = []

        for field in required_fields:
            if field not in pyinstaller_config:
                missing_fields.append(field)

        if missing_fields:
            if verbose:
                print(f"[CONFIG] Missing required fields: {missing_fields}")
            return False

        # Check duplicate packages
        all_packages = set()
        duplicates = []

        for field in ["collect_all", "collect_data_only"]:  # These two fields should not overlap
            packages = pyinstaller_config.get(field, [])
            for pkg in packages:
                if pkg in all_packages:
                    duplicates.append(pkg)
                all_packages.add(pkg)

        if duplicates:
            if verbose:
                print(f"[CONFIG] Duplicate packages found: {duplicates}")
            return False

        if verbose:
            collect_all_count = len(pyinstaller_config.get("collect_all", []))
            collect_data_count = len(pyinstaller_config.get("collect_data_only", []))
            hidden_imports_count = len(pyinstaller_config.get("hiddenimports", []))
            excludes_count = len(pyinstaller_config.get("excludes", []))

            print(f"[CONFIG] Configuration valid:")
            print(f"[CONFIG]   collect_all: {collect_all_count} packages")
            print(f"[CONFIG]   collect_data_only: {collect_data_count} packages")
            print(f"[CONFIG]   hiddenimports: {hidden_imports_count} modules")
            print(f"[CONFIG]   excludes: {excludes_count} modules")

        return True

    except Exception as e:
        if verbose:
            print(f"[CONFIG] Validation failed: {e}")
        return False


def process_data_files(data_files_config: dict, verbose: bool = False) -> list:
    """
    Process data files configuration with cross-platform compatibility
    """
    import platform

    # Use platform-specific processing
    if platform.system() == "Darwin":
        if verbose:
            print("[DATA] macOS: Using symlink-aware processing")
        return _process_macos_data(data_files_config, verbose)
    else:
        if verbose:
            print(f"[DATA] {platform.system()}: Using standard processing")
        return _process_standard_data(data_files_config, verbose)


def _process_standard_data(data_files_config: dict, verbose: bool = False) -> list:
    """Standard data files processing for Windows/Linux"""
    processed_files = []

    # Process directories
    directories = data_files_config.get("directories", [])
    for directory in directories:
        src_path = Path(directory)
        if src_path.exists():
            processed_files.append((directory, directory))
        elif verbose:
            print(f"[DATA] Directory not found: {directory}")

    # Process files
    files = data_files_config.get("files", [])
    for file_path in files:
        src_path = Path(file_path)
        if src_path.exists():
            # For single files, target should be "." (root directory) to avoid nested directory structure
            # PyInstaller datas format: (source, target_dir)
            # If target is the filename itself, it creates a nested structure like VERSION/VERSION
            processed_files.append((file_path, "."))
        elif verbose:
            print(f"[DATA] File not found: {file_path}")

    return processed_files


def _process_macos_data(data_files_config: dict, verbose: bool = False) -> list:
    """macOS data files processing with simple symlink handling"""
    import tempfile
    import shutil

    processed_files = []

    # Process directories
    directories = data_files_config.get("directories", [])
    for directory in directories:
        src_path = Path(directory)
        if not src_path.exists():
            if verbose:
                print(f"[DATA] Directory not found: {directory}")
            continue

        # Check if directory contains symlinks or is a known problematic directory
        needs_processing = _has_symlinks(src_path) or _is_problematic_directory(directory)

        if needs_processing:
            if verbose:
                print(f"[DATA] Processing symlinks in: {directory}")

            # Create symlink-free copy
            temp_dir = Path(tempfile.mkdtemp(prefix=f"{src_path.name}_fixed_"))
            try:
                _copy_and_resolve_symlinks(src_path, temp_dir / src_path.name, verbose)
                processed_files.append((str(temp_dir / src_path.name), directory))
            except Exception as e:
                if verbose:
                    print(f"[DATA] Failed to process {directory}: {e}")
                # Cleanup and use original path
                shutil.rmtree(temp_dir, ignore_errors=True)
                processed_files.append((directory, directory))
        else:
            processed_files.append((directory, directory))

    # Process files
    files = data_files_config.get("files", [])
    for file_path in files:
        src_path = Path(file_path)
        if src_path.exists():
            # For single files, target should be "." (root directory) to avoid nested directory structure
            # PyInstaller datas format: (source, target_dir)
            # If target is the filename itself, it creates a nested structure like VERSION/VERSION
            processed_files.append((file_path, "."))
        elif verbose:
            print(f"[DATA] File not found: {file_path}")

    return processed_files


def _has_symlinks(path: Path) -> bool:
    """Check if directory contains symlinks (but skip system packages)"""
    try:
        path_str = str(path)

        # Don't check symlinks in system packages - let PyInstaller handle them
        if any(pattern in path_str for pattern in ["PySide6", "Qt", "site-packages", "venv/lib", ".framework"]):
            return False

        # Only check our own directories for symlinks
        for item in path.rglob("*"):
            if item.is_symlink():
                return True
    except (OSError, PermissionError):
        pass
    return False


def _is_problematic_directory(directory: str) -> bool:
    """Check if directory is known to contain problematic symlinks"""
    # Only process our own third-party directories, NOT system packages
    problematic_patterns = [
        "third_party",
        "ota",
        "dependencies"
    ]

    # NEVER process PySide6/Qt directories - let PyInstaller handle them
    qt_patterns = [
        "PySide6",
        "Qt",
        "site-packages",
        "venv/lib",
        ".framework"
    ]

    # Check if it's a Qt/PySide6 directory that should be left alone
    for qt_pattern in qt_patterns:
        if qt_pattern in directory:
            return False

    # Only process our own problematic directories
    for pattern in problematic_patterns:
        if pattern in directory:
            return True

    return False


def _copy_and_resolve_symlinks(src: Path, dst: Path, verbose: bool = False):
    """Copy directory, resolving symlinks to actual files"""
    import shutil

    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        src_item = src / item.name
        dst_item = dst / item.name

        try:
            if src_item.is_symlink():
                # Resolve symlink
                try:
                    target = src_item.resolve(strict=True)
                    if target.is_file():
                        shutil.copy2(target, dst_item)
                    elif target.is_dir():
                        _copy_and_resolve_symlinks(target, dst_item, verbose)
                except (OSError, FileNotFoundError):
                    if verbose:
                        print(f"[DATA] Skipping broken symlink: {src_item}")
                    continue
            elif src_item.is_file():
                shutil.copy2(src_item, dst_item)
            elif src_item.is_dir():
                _copy_and_resolve_symlinks(src_item, dst_item, verbose)
        except Exception as e:
            if verbose:
                print(f"[DATA] Warning: Failed to process {src_item}: {e}")
            continue








def dev_sign_artifacts(enable: bool) -> None:
    """Development-only local signing helper (safe no-op if not configured)"""
    if not enable:
        return

    try:
        sysname = platform.system()
        if sysname == "Windows":
            _dev_sign_windows()
        elif sysname == "Darwin":
            _dev_sign_macos()
        else:
            print(f"[DEV-SIGN] Unsupported platform for dev-sign: {sysname}")
    except Exception as e:
        print(f"[DEV-SIGN] ERROR: {e}")


def _dev_sign_windows():
    """Development signing for Windows"""
    cert_pfx = os.getenv("DEV_WIN_CERT_PFX")
    cert_password = os.getenv("DEV_WIN_CERT_PASSWORD")

    if not cert_pfx or not cert_password:
        print(
            "[DEV-SIGN] Windows: DEV_WIN_CERT_PFX or DEV_WIN_CERT_PASSWORD not set, skipping"
        )
        return

    print("[DEV-SIGN] Windows: Development signing enabled")
    # Implementation would go here


def _dev_sign_macos():
    """Development signing for macOS"""
    identity = os.getenv("DEV_MAC_CODESIGN_IDENTITY")

    if not identity:
        print("[DEV-SIGN] macOS: DEV_MAC_CODESIGN_IDENTITY not set, skipping")
        return

    print("[DEV-SIGN] macOS: Development signing enabled")
    # Implementation would go here


# ============================================================================
# Production macOS signing, notarization, and stapling
# ============================================================================
#
# Why this is a no-op-by-default function:
# -----------------------------------------
# The release-{intl,cn}.yml workflows already inject these env vars from
# the runner's secrets into the macOS build job:
#
#   MAC_CERT_P12, MAC_CERT_PASSWORD, MAC_CODESIGN_IDENTITY,
#   APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, TEAM_ID
#
# Until this commit they were dead code — grep for those env names in
# build_system/ found zero call sites. macOS prod signing therefore
# silently did nothing; the resulting `.dmg` / `.pkg` ships
# un-signed and un-notarized, and Gatekeeper will quarantine it on
# first open unless the user right-clicks and chooses "Open Anyway".
#
# This function is the entry point that wires those env vars into a
# real Developer ID signing + notarytool submission + staple. It is
# gated on `MAC_CODESIGN_IDENTITY` being present (a non-empty,
# non-"NOT_SET" string) — that is, it only runs when the workflow
# actually injected a Developer ID identity from the runner's
# secret store. In the absence of that secret the function is a
# no-op so the current behaviour is preserved exactly.
#
# Status: STUB — UNVERIFIED.
# ---------------------------
# As of this commit, the function is wired into the workflow and the
# unit-test surface is in place, but the actual `codesign` /
# `notarytool` / `stapler` invocations have not been exercised on
# a real macOS runner with a real Developer ID. The tests cover the
# gating logic only. When the first Developer ID secret is
# provisioned, run this on a staging tag and watch for:
#
#   1. `codesign --verify --deep --strict --verbose=2` passes
#   2. `xcrun notarytool info <submission-id>` returns "Accepted"
#   3. `xcrun stapler validate -v <app>` prints "The staple is valid"
#   4. `spctl --assess --type execute --verbose <app>` returns
#      "accepted" without "source=Notarized Developer ID" warning
#
# Until that smoke is green, treat this as scaffolding, not as a
# feature: do not lower `MAC_CODESIGN_IDENTITY`'s opt-in gate.
#
# Required tooling (all ship with Xcode + CLT):
#   codesign      (Xcode CLT)
#   xcrun         (Xcode CLT)  → notarytool, stapler, altool
#   ditto         (system)
#
# Required env vars (set by the workflow from `${{ secrets.* }}`):
#   MAC_CODESIGN_IDENTITY       — "Developer ID Application: <Name> (<TEAM>)"
#   MAC_CERT_P12                — base64 of the Developer ID .p12 cert
#   MAC_CERT_PASSWORD           — password for the .p12
#   APPLE_ID                    — Apple ID email for notarytool
#   APPLE_APP_SPECIFIC_PASSWORD — app-specific password (NOT the Apple ID password)
#   TEAM_ID                     — 10-character Apple developer team ID
#
# Workflow contract:
#   * This function is invoked from a release-{intl,cn}.yml step AFTER
#     `Build macOS package` finishes and BEFORE `Prepare artifacts`.
#   * The step sets the same env vars as `Build macOS package` does.
#   * On non-macOS runners the function logs "skipped (non-Darwin)"
#     and returns cleanly.
#   * On macOS without `MAC_CODESIGN_IDENTITY` it logs "skipped
#     (no identity)" and returns cleanly — preserving today's
#     un-signed-and-notarized behaviour until secrets are wired.

_MAC_SIGN_KEYCHAIN_NAME = "ecan-build.keychain-db"
_MAC_SIGN_KEYCHAIN_PASSWORD = "ecan-build-temp-password"  # ephemeral, deleted at end


def _mac_sign_is_configured() -> bool:
    """Return True iff the workflow injected all secrets needed for
    real macOS prod signing. Used both as a gate and as a way for
    tests to assert the configuration state without invoking any
    `codesign` subprocess."""
    required = (
        "MAC_CODESIGN_IDENTITY",
        "MAC_CERT_P12",
        "MAC_CERT_PASSWORD",
        "APPLE_ID",
        "APPLE_APP_SPECIFIC_PASSWORD",
        "TEAM_ID",
    )
    for name in required:
        v = os.getenv(name)
        if not v or v == "NOT_SET":
            return False
    return True


def _mac_sign_resolve_app_bundle(dist_dir: "Path | None" = None) -> "Path | None":
    """Locate the .app bundle produced by `build.py prod` for signing.

    Returns the path to the bundle, or None if no bundle is found.
    The convention `dist/eCan.app` / `dist/eCan.cn.app` comes from
    PyInstaller's BUNDLE directive (see minibuild_core.py:1270).
    """
    import platform as _platform
    if _platform.system() != "Darwin":
        return None
    project_root = Path(__file__).resolve().parents[1]  # build_system/.. = repo root
    if dist_dir is None:
        dist_dir = project_root / "dist"
    if not dist_dir.exists():
        print(f"[MAC-SIGN] dist/ not found at {dist_dir}; cannot locate .app bundle")
        return None
    candidates = sorted(dist_dir.glob("*.app"))
    if not candidates:
        print(f"[MAC-SIGN] no .app bundle in {dist_dir}; nothing to sign")
        return None
    if len(candidates) > 1:
        print(f"[MAC-SIGN] WARNING: multiple .app bundles found, signing the first: "
              f"{[c.name for c in candidates]}")
    return candidates[0]


def sign_macos_prod() -> bool:
    """Production sign + notarize + staple the macOS .app bundle.

    Returns True on success, False on any failure (and logs the
    failure to stdout so CI surfaces it). Designed to be invoked
    from a release workflow step like:

        - name: Sign and notarize macOS artifact
          env:
            MAC_CODESIGN_IDENTITY:     ${{ secrets.MAC_CODESIGN_IDENTITY     || 'NOT_SET' }}
            MAC_CERT_P12:              ${{ secrets.MAC_CERT_P12              || 'NOT_SET' }}
            MAC_CERT_PASSWORD:         ${{ secrets.MAC_CERT_PASSWORD         || 'NOT_SET' }}
            APPLE_ID:                  ${{ secrets.APPLE_ID                  || 'NOT_SET' }}
            APPLE_APP_SPECIFIC_PASSWORD: ${{ secrets.APPLE_APP_SPECIFIC_PASSWORD || 'NOT_SET' }}
            TEAM_ID:                   ${{ secrets.TEAM_ID                   || 'NOT_SET' }}
          run: |
            & $VenvPython -c "import sys; sys.path.insert(0, '.'); from build_system.build_utils import sign_macos_prod; sys.exit(0 if sign_macos_prod() else 1)"

    Gate behaviour:
      * Non-Darwin → log + return True (no-op).
      * Missing any required env var → log + return True (no-op).
      * Anything else → run the full pipeline; return True iff every
        step succeeded.

    Unverified: the actual subprocess pipeline has not been
    exercised on a real Developer-ID-equipped macOS runner. See the
    block comment above for the smoke checklist to run before
    declaring this safe.
    """
    import platform as _platform
    import subprocess as _subprocess
    import tempfile as _tempfile

    # Gate 1: only runs on macOS.
    if _platform.system() != "Darwin":
        print("[MAC-SIGN] Skipped: not running on Darwin.")
        return True

    # Gate 2: only runs when all required secrets are present.
    if not _mac_sign_is_configured():
        print("[MAC-SIGN] Skipped: one or more required env vars are "
              "missing or set to 'NOT_SET' (MAC_CODESIGN_IDENTITY, "
              "MAC_CERT_P12, MAC_CERT_PASSWORD, APPLE_ID, "
              "APPLE_APP_SPECIFIC_PASSWORD, TEAM_ID).")
        return True

    identity = os.environ["MAC_CODESIGN_IDENTITY"]
    cert_p12_b64 = os.environ["MAC_CERT_P12"]
    cert_password = os.environ["MAC_CERT_PASSWORD"]
    apple_id = os.environ["APPLE_ID"]
    app_specific_password = os.environ["APPLE_APP_SPECIFIC_PASSWORD"]
    team_id = os.environ["TEAM_ID"]

    app_bundle = _mac_sign_resolve_app_bundle()
    if app_bundle is None:
        # Important: this is NOT a sign failure. The .app bundle is
        # produced by `build.py prod` in the previous "Build macOS
        # package" step. If that step failed (PyInstaller crash,
        # missing module, disk full, etc.) the .app won't be in
        # dist/ and this step has nothing to do.
        #
        # Returning True here means: don't fail the workflow at
        # the sign step. Earlier steps in the same job will have
        # already failed the build, so the workflow will be red
        # anyway — but the failure status will name the build
        # step, not the sign step, which is the source of truth.
        # If we returned False here, the CI dashboard would show
        # "sign failed" instead of "build failed", which is the
        # regression we want to avoid.
        print(
            "[MAC-SIGN] No .app bundle found in dist/. This usually "
            "means the `Build macOS package` step failed (PyInstaller "
            "crash, missing module, disk full, etc.) — that earlier "
            "step will report the failure with the correct cause. "
            "Sign step is skipping to avoid masking the real error."
        )
        return True

    print(f"[MAC-SIGN] Signing: {app_bundle}")
    print(f"[MAC-SIGN] Identity: {identity}")

    try:
        with _tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Step 1: Decode the .p12 to disk (a temp file we'll feed
            # to `security import`).
            cert_path = tmp_path / "ecan-codesign.p12"
            import base64
            cert_path.write_bytes(base64.b64decode(cert_p12_b64))

            # Step 2: Create an ephemeral keychain so the cert isn't
            # visible to other macOS processes on the runner. The
            # keychain is deleted when `tmp` goes out of scope below.
            keychain_path = tmp_path / _MAC_SIGN_KEYCHAIN_NAME
            subprocess.run(
                ["security", "create-keychain", "-p", _MAC_SIGN_KEYCHAIN_PASSWORD,
                 str(keychain_path)],
                check=True,
            )
            # Unlock so `security import` and `codesign -k` can read it.
            subprocess.run(
                ["security", "unlock-keychain", "-p", _MAC_SIGN_KEYCHAIN_PASSWORD,
                 str(keychain_path)],
                check=True,
            )
            # Allow codesign to use the identity without an interactive
            # prompt. `set-keychain-settings -u` sets the auto-lock
            # timeout; `-lut` disables user-interaction confirmation
            # for the duration of this build.
            subprocess.run(
                ["security", "set-keychain-settings", "-lut",
                 str(keychain_path)],
                check=True,
            )
            # Add the temp keychain to the search list so codesign finds it.
            subprocess.run(
                ["security", "list-keychains", "-d", "user", "-s",
                 str(keychain_path),
                 # Preserve any existing keychain(s) on the runner
                 # by also re-listing them via `list-keychains`. We
                 # don't enumerate them here because the runner is
                 # ephemeral — re-adding the temp keychain is enough
                 # because `list-keychains` returns the union.
                 ],
                check=True,
            )
            # Import the .p12 into the temp keychain.
            subprocess.run(
                ["security", "import", str(cert_path),
                 "-k", str(keychain_path),
                 "-P", cert_password,
                 "-T", "/usr/bin/codesign",
                 "-T", "/usr/bin/security"],
                check=True,
            )

            # Step 3: codesign --force --sign with hardened runtime +
            # timestamp. Hardened runtime is required for notarization
            # (Gatekeeper rejects un-hardened binaries at the notarize
            # stage). --options=runtime + --timestamp are mandatory.
            print("[MAC-SIGN] Running codesign --force --sign ...")
            subprocess.run(
                ["codesign", "--force",
                 "--sign", identity,
                 "--options", "runtime",
                 "--timestamp",
                 "--deep",
                 str(app_bundle)],
                check=True,
            )
            # Verify the signature before submitting to notarize, so
            # we fail fast on a broken signing setup rather than
            # waiting for Apple's notarization queue.
            print("[MAC-SIGN] Verifying codesign result ...")
            subprocess.run(
                ["codesign", "--verify", "--deep", "--strict",
                 "--verbose=2", str(app_bundle)],
                check=True,
            )

            # Step 4: Zip the bundle for notarytool submission.
            # notarytool requires a zip, dmg, or pkg; for an .app the
            # canonical format is `ditto -c -k --sequesterRsrc --keepParent`.
            zip_path = tmp_path / f"{app_bundle.stem}.zip"
            subprocess.run(
                ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                 str(app_bundle), str(zip_path)],
                check=True,
            )

            # Step 5: Submit to notarization. --wait blocks until
            # Apple returns Accepted/Rejected. Without --wait we'd
            # have to poll `notarytool info`, which is what older
            # scripts do but it's slower and more error-prone.
            print("[MAC-SIGN] Submitting to notarytool (this may take "
                  "several minutes) ...")
            submit_result = subprocess.run(
                ["xcrun", "notarytool", "submit", str(zip_path),
                 "--apple-id", apple_id,
                 "--password", app_specific_password,
                 "--team-id", team_id,
                 "--wait"],
                capture_output=True,
                text=True,
            )
            if submit_result.returncode != 0:
                print(f"[MAC-SIGN] notarytool submit FAILED: "
                      f"rc={submit_result.returncode}")
                print(f"[MAC-SIGN] stdout: {submit_result.stdout}")
                print(f"[MAC-SIGN] stderr: {submit_result.stderr}")
                return False
            print(f"[MAC-SIGN] notarytool submit succeeded: {submit_result.stdout.strip()}")

            # Step 6: Staple the notarization ticket onto the bundle.
            # After this, Gatekeeper can verify the ticket offline
            # without contacting Apple.
            print("[MAC-SIGN] Stapling notarization ticket ...")
            subprocess.run(
                ["xcrun", "stapler", "staple", str(app_bundle)],
                check=True,
            )
            # Verify the staple so we know it's valid before shipping.
            subprocess.run(
                ["xcrun", "stapler", "validate", "-v", str(app_bundle)],
                check=True,
            )

            print(f"[MAC-SIGN] OK: signed + notarized + stapled {app_bundle}")
            return True

    except subprocess.CalledProcessError as e:
        print(f"[MAC-SIGN] FAILED: subprocess error: {e}")
        if e.stderr:
            print(f"[MAC-SIGN] stderr: {e.stderr}")
        if e.stdout:
            print(f"[MAC-SIGN] stdout: {e.stdout}")
        return False
    except Exception as e:
        print(f"[MAC-SIGN] FAILED: unexpected error: {e}")
        return False


# Backwards-compat alias. Older code paths may import
# `_sign_macos_prod` (with underscore prefix) — keep the name alive
# so a refactor that adds call sites doesn't break the import.
_sign_macos_prod = sign_macos_prod



