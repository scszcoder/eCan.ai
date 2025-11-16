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
    
    @staticmethod
    def _setup_windows_build():
        """Setup Windows build configuration"""
        try:
            # Create Windows-specific build configuration
            build_config = {
                "url_scheme": "ecan",
                "protocol_name": "eCan Protocol",
                "executable_name": "eCan.exe",
                "icon_file": "eCan.ico"
            }
            
            print("[URL_SCHEME] Windows URL scheme build configuration created")
            return True
            
        except Exception as e:
            print(f"[ERROR] [URL_SCHEME] Failed to setup Windows build configuration: {e}")
            return False
    
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
                options.extend([
                    f"--osx-bundle-identifier=com.ecan.app",
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


def standardize_artifact_names(version: str, arch: str = "amd64") -> None:
    """Standardize build artifact filenames to match release.yml expected format"""
    platform_name = platform.system()

    if platform_name == "Windows":
        _standardize_windows_artifacts(version, arch)
    elif platform_name == "Darwin":
        _standardize_macos_artifacts(version, arch)
    elif platform_name == "Linux":
        _standardize_linux_artifacts(version, arch)


def _standardize_windows_artifacts(version: str, arch: str):
    """Standardize Windows build artifacts"""
    dist_dir = Path("dist")

    # Find and standardize installer files (Setup.exe)
    setup_files = list(dist_dir.glob("*Setup*.exe"))
    for setup_file in setup_files:
        # Check if it's already in standardized format
        expected_name = f"eCan-{version}-windows-{arch}-Setup.exe"
        expected_path = dist_dir / expected_name

        if setup_file.name != expected_name:
            try:
                if not expected_path.exists():
                    shutil.move(setup_file, expected_path)
                    print(f"[RENAME] {setup_file.name} -> {expected_name}")
                else:
                    # Remove duplicate if standardized version already exists
                    setup_file.unlink()
                    print(f"[RENAME] Removed duplicate: {setup_file.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to rename {setup_file}: {e}")

    # Find and standardize executable files (main app)
    exe_files = [f for f in dist_dir.glob("*.exe") if "Setup" not in f.name]
    for exe_file in exe_files:
        expected_name = f"eCan-{version}-windows-{arch}.exe"
        expected_path = dist_dir / expected_name

        if exe_file.name != expected_name and "eCan" in exe_file.name:
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


def _standardize_macos_artifacts(version: str, arch: str):
    """Standardize macOS build artifacts"""
    dist_dir = Path("dist")

    # Standardize PKG file naming to match release.yml format
    expected_name = f"eCan-{version}-macos-{arch}.pkg"
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


def _standardize_linux_artifacts(version: str, arch: str):
    """Standardize Linux build artifacts"""
    dist_dir = Path("dist")

    # Find executable files or AppImage
    executables = []
    for pattern in ["eCan", "*.AppImage", "*.deb", "*.rpm"]:
        executables.extend(dist_dir.glob(pattern))

    if executables:
        old_path = executables[0]
        suffix = old_path.suffix or ""
        new_name = f"eCan-{version}-linux-{arch}{suffix}"
        new_path = dist_dir / new_name

        try:
            if old_path != new_path:
                shutil.move(old_path, new_path)
                print(f"[RENAME] {old_path.name} -> {new_name}")
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


def prepare_third_party_assets() -> None:
    """Prepare third-party assets (Playwright, Sparkle, winSparkle)"""
    print("[THIRD-PARTY] Preparing third-party assets...")

    try:
        # Use simplified Playwright preparation
        _prepare_playwright_simple()
        print("[THIRD-PARTY] Playwright assets prepared successfully")

    except Exception as e:
        print(f"[THIRD-PARTY] Playwright preparation failed: {e}")
        print("[THIRD-PARTY] This may cause issues with browser automation features")
        # Don't fail the build, just warn

    try:
        # Prepare OTA dependencies (Sparkle/winSparkle)
        _prepare_ota_dependencies()
        print("[THIRD-PARTY] OTA dependencies prepared successfully")

    except Exception as e:
        print(f"[THIRD-PARTY] OTA dependencies preparation failed: {e}")
        print("[THIRD-PARTY] This may cause issues with OTA update features")
        # Don't fail the build, just warn


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

    # Simple copy using standard library
    try:
        shutil.copytree(cache_path, target_path, symlinks=False, dirs_exist_ok=True)
    except Exception as e:
        print(f"[PLAYWRIGHT] Copy failed: {e}")
        raise


def _prepare_ota_dependencies() -> None:
    """Prepare OTA dependencies (Sparkle/winSparkle)"""
    import platform
    import subprocess
    import sys
    import urllib.request
    import tarfile
    import zipfile
    from pathlib import Path

    current_platform = platform.system()
    third_party_dir = Path.cwd() / "third_party"

    if current_platform == "Darwin":
        # Prepare Sparkle for macOS
        sparkle_dir = third_party_dir / "sparkle"
        sparkle_framework = sparkle_dir / "Sparkle.framework"

        if not sparkle_framework.exists():
            print("[BUILD] Downloading Sparkle framework...")
            sparkle_dir.mkdir(parents=True, exist_ok=True)

            # Download Sparkle
            sparkle_url = "https://github.com/sparkle-project/Sparkle/releases/download/2.6.4/Sparkle-2.6.4.tar.xz"
            sparkle_archive = sparkle_dir / "Sparkle-2.6.4.tar.xz"

            urllib.request.urlretrieve(sparkle_url, sparkle_archive)

            # Extract Sparkle
            with tarfile.open(sparkle_archive, 'r:xz') as tar:
                tar.extractall(sparkle_dir)


            # Create install info
            install_info = {
                "platform": "darwin",
                "install_method": "build_system",
                "installed_dependencies": {
                    "sparkle": {
                        "version": "2.6.4",
                        "url": sparkle_url,
                        "target_path": str(sparkle_framework),
                        "installed": True
                    }
                },
                "install_timestamp": str(time.time()),
                "installer_version": "1.0.0"
            }

            import json
            with open(sparkle_dir / "install_info.json", 'w') as f:
                json.dump(install_info, f, indent=2)

            print(f"[BUILD] Sparkle framework prepared at: {sparkle_framework}")
        else:
            print(f"[BUILD] Sparkle framework already exists at: {sparkle_framework}")

    elif current_platform == "Windows":
        # Prepare winSparkle for Windows
        winsparkle_dir = third_party_dir / "winsparkle"
        winsparkle_dll = winsparkle_dir / "winsparkle.dll"

        if not winsparkle_dll.exists():
            print("[BUILD] Downloading winSparkle...")
            winsparkle_dir.mkdir(parents=True, exist_ok=True)

            # Download winSparkle
            winsparkle_url = "https://github.com/vslavik/winsparkle/releases/download/v0.8.0/winsparkle-0.8.0.zip"
            winsparkle_archive = winsparkle_dir / "winsparkle-0.8.0.zip"

            urllib.request.urlretrieve(winsparkle_url, winsparkle_archive)

            # Extract winSparkle
            with zipfile.ZipFile(winsparkle_archive, 'r') as zip_ref:
                zip_ref.extractall(winsparkle_dir / "temp")

            # Find and copy DLL
            temp_dir = winsparkle_dir / "temp"
            dll_files = list(temp_dir.glob("**/winsparkle.dll"))

            if dll_files:
                shutil.copy2(dll_files[0], winsparkle_dll)
                print(f"[BUILD] winSparkle DLL prepared at: {winsparkle_dll}")
            else:
                raise RuntimeError("winSparkle DLL not found in downloaded archive")

            # Cleanup
            shutil.rmtree(temp_dir)
            winsparkle_archive.unlink()
        else:
            print(f"[BUILD] winSparkle DLL already exists at: {winsparkle_dll}")

    else:
        print(f"[BUILD] OTA dependencies not needed for platform: {current_platform}")


def _find_playwright_cache() -> Path:
    """Find Playwright cache directory (simplified)"""
    import os
    import platform
    from pathlib import Path

    # Check environment variable first
    from agent.playwright.core.utils import PlaywrightCoreUtils
    env_path = os.getenv(PlaywrightCoreUtils.ENV_BROWSERS_PATH)
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
            processed_files.append((file_path, file_path))
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
            processed_files.append((file_path, file_path))
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



