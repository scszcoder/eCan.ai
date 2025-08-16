#!/usr/bin/env python3
"""
Third-Party File Manager
Configurable system for handling various third-party dependencies and files
"""

import os
import sys
import json
import platform
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from abc import ABC, abstractmethod
import fnmatch
import subprocess

class ThirdPartyHandler(ABC):
    """Abstract base class for third-party file handlers"""
    
    def __init__(self, config: Dict[str, Any], global_config: Dict[str, Any]):
        self.config = config
        self.global_config = global_config
        self.verbose = global_config.get('verbose_logging', False)
        
    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[{level}] [{self.__class__.__name__}] {message}")
    
    @abstractmethod
    def find_source_files(self) -> List[Path]:
        """Find source files for this third-party component"""
        pass
    
    @abstractmethod
    def validate_source(self, source_path: Path) -> bool:
        """Validate if source path is valid for this component"""
        pass
    
    def copy_files(self, source_paths: List[Path], destination: Path) -> bool:
        """Copy files using configured strategy"""
        try:
            # Import symlink manager if available
            from symlink_manager import symlink_manager
            use_symlink_manager = True
        except ImportError:
            use_symlink_manager = False
            self.log("Symlink manager not available, using fallback", "WARNING")
        
        strategy = self.config.get('copy_strategy', 'full_copy')
        symlink_handling = self._get_symlink_strategy()
        
        success_count = 0
        for source_path in source_paths:
            if not source_path.exists():
                self.log(f"Source path not found: {source_path}", "WARNING")
                continue
            
            try:
                if use_symlink_manager and symlink_handling.get('handle_conflicts', False):
                    # Use symlink manager for safe copying
                    success = symlink_manager.safe_copytree(
                        source_path, 
                        destination / source_path.name,
                        self.__class__.__name__
                    )
                else:
                    # Use standard copying with strategy
                    success = self._copy_with_strategy(source_path, destination, strategy)
                
                if success:
                    success_count += 1
                    self.log(f"Successfully copied: {source_path}")
                else:
                    self.log(f"Failed to copy: {source_path}", "ERROR")
                    
            except Exception as e:
                self.log(f"Copy error for {source_path}: {e}", "ERROR")
        
        return success_count > 0
    
    def _get_symlink_strategy(self) -> Dict[str, Any]:
        """Get symlink handling strategy for current platform"""
        symlink_config = self.config.get('symlink_handling', {})
        current_platform = platform.system().lower()
        
        if current_platform == 'darwin':
            strategy_name = symlink_config.get('macos', 'safe_copy')
        elif current_platform == 'windows':
            strategy_name = symlink_config.get('windows', 'resolve_symlinks')
        else:
            strategy_name = symlink_config.get('linux', 'preserve_symlinks')
        
        # Get strategy details from global config
        strategies = self.global_config.get('symlink_strategies', {})
        return strategies.get(strategy_name, {'resolve_symlinks': True, 'handle_conflicts': False})
    
    def _copy_with_strategy(self, source: Path, destination: Path, strategy: str) -> bool:
        """Copy files using specified strategy"""
        try:
            if strategy == 'platform_specific':
                return self._copy_platform_specific(source, destination)
            elif strategy == 'selective':
                return self._copy_selective(source, destination)
            elif strategy == 'binary_only':
                return self._copy_binary_only(source, destination)
            else:  # full_copy
                return self._copy_full(source, destination)
        except Exception as e:
            self.log(f"Strategy {strategy} failed: {e}", "ERROR")
            return False
    
    def _copy_platform_specific(self, source: Path, destination: Path) -> bool:
        """Copy only platform-specific files"""
        current_platform = platform.system().lower()
        platform_patterns = {
            'windows': ['*win*', '*.exe', '*.dll'],
            'darwin': ['*mac*', '*darwin*', '*.dylib', '*.app'],
            'linux': ['*linux*', '*.so']
        }
        
        patterns = platform_patterns.get(current_platform, ['*'])
        return self._copy_with_patterns(source, destination, patterns, [])
    
    def _copy_selective(self, source: Path, destination: Path) -> bool:
        """Copy based on include/exclude patterns"""
        filters = self.config.get('filters', {})
        include_patterns = filters.get('include_patterns', ['*'])
        exclude_patterns = filters.get('exclude_patterns', [])
        
        return self._copy_with_patterns(source, destination, include_patterns, exclude_patterns)
    
    def _copy_binary_only(self, source: Path, destination: Path) -> bool:
        """Copy only executable binaries"""
        if source.is_file():
            if self._is_executable(source):
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                return True
        else:
            # For directories, find all executables
            executables = []
            for item in source.rglob('*'):
                if item.is_file() and self._is_executable(item):
                    executables.append(item)
            
            if executables:
                destination.mkdir(parents=True, exist_ok=True)
                for exe in executables:
                    rel_path = exe.relative_to(source)
                    dest_file = destination / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(exe, dest_file)
                return True
        
        return False
    
    def _copy_full(self, source: Path, destination: Path) -> bool:
        """Copy everything with basic filtering"""
        exclude_patterns = self.config.get('filters', {}).get('exclude_patterns', [])
        
        if source.is_file():
            if not self._matches_patterns(str(source), exclude_patterns):
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                return True
        else:
            def ignore_func(dir_path, names):
                ignored = []
                for name in names:
                    full_path = os.path.join(dir_path, name)
                    if self._matches_patterns(full_path, exclude_patterns):
                        ignored.append(name)
                return ignored
            
            shutil.copytree(source, destination, ignore=ignore_func, dirs_exist_ok=True)
            return True
        
        return False
    
    def _copy_with_patterns(self, source: Path, destination: Path, 
                           include_patterns: List[str], exclude_patterns: List[str]) -> bool:
        """Copy files matching include patterns but not exclude patterns"""
        if source.is_file():
            if (self._matches_patterns(str(source), include_patterns) and 
                not self._matches_patterns(str(source), exclude_patterns)):
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                return True
        else:
            def ignore_func(dir_path, names):
                ignored = []
                for name in names:
                    full_path = os.path.join(dir_path, name)
                    if (not self._matches_patterns(full_path, include_patterns) or
                        self._matches_patterns(full_path, exclude_patterns)):
                        ignored.append(name)
                return ignored
            
            shutil.copytree(source, destination, ignore=ignore_func, dirs_exist_ok=True)
            return True
        
        return False
    
    def _matches_patterns(self, path: str, patterns: List[str]) -> bool:
        """Check if path matches any of the patterns"""
        for pattern in patterns:
            if fnmatch.fnmatch(path.lower(), pattern.lower()):
                return True
        return False
    
    def _is_executable(self, path: Path) -> bool:
        """Check if file is executable"""
        if not path.is_file():
            return False
        
        # Check by extension on Windows
        if platform.system() == 'Windows':
            return path.suffix.lower() in ['.exe', '.bat', '.cmd', '.com']
        
        # Check execute permission on Unix-like systems
        return os.access(path, os.X_OK)
    
    def validate_result(self, destination: Path) -> bool:
        """Validate the copied files"""
        validation = self.config.get('validation', {})
        
        # Check required files
        required_files = validation.get('required_files', [])
        for required_file in required_files:
            if not (destination / required_file).exists():
                self.log(f"Required file missing: {required_file}", "ERROR")
                return False
        
        # Check size constraints
        if destination.exists():
            total_size = sum(f.stat().st_size for f in destination.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            
            min_size = validation.get('min_size_mb', 0)
            max_size = validation.get('max_size_mb', float('inf'))
            
            if size_mb < min_size:
                self.log(f"Size too small: {size_mb:.1f}MB < {min_size}MB", "ERROR")
                return False
            
            if size_mb > max_size:
                self.log(f"Size too large: {size_mb:.1f}MB > {max_size}MB", "ERROR")
                return False
        
        # Check executable files
        if validation.get('executable_check', False):
            executables = [f for f in destination.rglob('*') if f.is_file() and self._is_executable(f)]
            if not executables:
                self.log("No executable files found", "ERROR")
                return False
        
        return True


class PlaywrightHandler(ThirdPartyHandler):
    """Handler for Playwright browser files"""
    
    def find_source_files(self) -> List[Path]:
        """Find Playwright browser installation"""
        current_platform = platform.system().lower()
        source_paths = self.config.get('source_paths', {}).get(current_platform, [])
        
        found_paths = []
        for path_str in source_paths:
            # Expand user home directory
            expanded_path = Path(path_str.replace('~', str(Path.home())))
            if expanded_path.exists():
                found_paths.append(expanded_path)
                self.log(f"Found Playwright source: {expanded_path}")
        
        return found_paths
    
    def validate_source(self, source_path: Path) -> bool:
        """Validate Playwright installation"""
        # Check for browsers.json or browser directories
        if (source_path / 'browsers.json').exists():
            return True
        
        # Check for browser directories
        browser_patterns = ['chromium-*', 'firefox-*', 'webkit-*']
        for pattern in browser_patterns:
            if list(source_path.glob(pattern)):
                return True
        
        return False


class ElectronHandler(ThirdPartyHandler):
    """Handler for Electron runtime files"""
    
    def find_source_files(self) -> List[Path]:
        """Find Electron installation"""
        # Implementation similar to PlaywrightHandler
        current_platform = platform.system().lower()
        source_paths = self.config.get('source_paths', {}).get(current_platform, [])
        
        found_paths = []
        for path_str in source_paths:
            expanded_path = Path(path_str.replace('~', str(Path.home())))
            if expanded_path.exists():
                found_paths.append(expanded_path)
        
        return found_paths
    
    def validate_source(self, source_path: Path) -> bool:
        """Validate Electron installation"""
        # Look for electron executable or electron directory
        electron_files = ['electron', 'electron.exe', 'Electron.app']
        for electron_file in electron_files:
            if (source_path / electron_file).exists():
                return True
        return False


# Add more handlers as needed...
class ChromeDriverHandler(ThirdPartyHandler):
    """Handler for ChromeDriver standalone executable"""

    def find_source_files(self) -> List[Path]:
        current_platform = platform.system().lower()
        source_paths = self.config.get('source_paths', {}).get(current_platform, [])

        found_paths = []
        for path_str in source_paths:
            expanded_path = Path(path_str.replace('~', str(Path.home())))

            if expanded_path.exists():
                # Check if it's a directory containing chromedriver
                if expanded_path.is_dir():
                    chromedriver_files = self._find_chromedriver_in_dir(expanded_path)
                    if chromedriver_files:
                        found_paths.extend(chromedriver_files)
                # Check if it's the chromedriver file itself
                elif self._is_chromedriver_file(expanded_path):
                    found_paths.append(expanded_path)

        # Also search in PATH
        path_chromedriver = self._find_chromedriver_in_path()
        if path_chromedriver:
            found_paths.append(path_chromedriver)

        return found_paths

    def validate_source(self, source_path: Path) -> bool:
        """Validate ChromeDriver executable"""
        if source_path.is_file():
            return self._is_chromedriver_file(source_path)
        elif source_path.is_dir():
            return len(self._find_chromedriver_in_dir(source_path)) > 0
        return False

    def _is_chromedriver_file(self, file_path: Path) -> bool:
        """Check if file is a ChromeDriver executable"""
        if not file_path.is_file():
            return False

        name = file_path.name.lower()
        return name in ['chromedriver', 'chromedriver.exe']

    def _find_chromedriver_in_dir(self, directory: Path) -> List[Path]:
        """Find ChromeDriver files in a directory"""
        chromedriver_files = []

        # Look for chromedriver files
        for pattern in ['chromedriver', 'chromedriver.exe']:
            matches = list(directory.glob(pattern))
            chromedriver_files.extend(matches)

        # Also check subdirectories (one level deep)
        for subdir in directory.iterdir():
            if subdir.is_dir():
                for pattern in ['chromedriver', 'chromedriver.exe']:
                    matches = list(subdir.glob(pattern))
                    chromedriver_files.extend(matches)

        return chromedriver_files

    def _find_chromedriver_in_path(self) -> Optional[Path]:
        """Find ChromeDriver in system PATH"""
        try:
            import shutil
            chromedriver_path = shutil.which('chromedriver')
            if chromedriver_path:
                return Path(chromedriver_path)
        except Exception:
            pass

        return None


class FFmpegHandler(ThirdPartyHandler):
    """Handler for FFmpeg multimedia framework"""

    def find_source_files(self) -> List[Path]:
        current_platform = platform.system().lower()
        source_paths = self.config.get('source_paths', {}).get(current_platform, [])

        found_paths = []
        for path_str in source_paths:
            expanded_path = Path(path_str.replace('~', str(Path.home())))
            if expanded_path.exists():
                found_paths.append(expanded_path)

        # Also search in PATH
        try:
            import shutil
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path:
                found_paths.append(Path(ffmpeg_path).parent)
        except Exception:
            pass

        return found_paths

    def validate_source(self, source_path: Path) -> bool:
        ffmpeg_files = ['ffmpeg', 'ffmpeg.exe', 'ffprobe', 'ffprobe.exe']

        if source_path.is_file():
            return source_path.name.lower() in [f.lower() for f in ffmpeg_files]

        for ffmpeg_file in ffmpeg_files:
            if (source_path / ffmpeg_file).exists():
                return True
        return False


class SeleniumDriverHandler(ThirdPartyHandler):
    """Handler for Selenium WebDriver collection"""

    def find_source_files(self) -> List[Path]:
        current_platform = platform.system().lower()
        source_paths = self.config.get('source_paths', {}).get(current_platform, [])

        found_paths = []
        for path_str in source_paths:
            expanded_path = Path(path_str.replace('~', str(Path.home())))
            if expanded_path.exists():
                found_paths.append(expanded_path)

        # Search for drivers in PATH
        driver_names = ['chromedriver', 'geckodriver', 'msedgedriver', 'operadriver']
        for driver_name in driver_names:
            try:
                import shutil
                driver_path = shutil.which(driver_name)
                if driver_path:
                    found_paths.append(Path(driver_path).parent)
            except Exception:
                pass

        return found_paths

    def validate_source(self, source_path: Path) -> bool:
        selenium_drivers = [
            'chromedriver', 'chromedriver.exe',
            'geckodriver', 'geckodriver.exe',
            'msedgedriver', 'msedgedriver.exe',
            'operadriver', 'operadriver.exe'
        ]

        if source_path.is_file():
            return source_path.name.lower() in [d.lower() for d in selenium_drivers]

        # Check if directory contains any selenium drivers
        for driver_file in selenium_drivers:
            if (source_path / driver_file).exists():
                return True

        return False


class GitPortableHandler(ThirdPartyHandler):
    """Handler for portable Git installation"""

    def find_source_files(self) -> List[Path]:
        current_platform = platform.system().lower()
        source_paths = self.config.get('source_paths', {}).get(current_platform, [])

        found_paths = []
        for path_str in source_paths:
            expanded_path = Path(path_str.replace('~', str(Path.home())))
            if expanded_path.exists():
                found_paths.append(expanded_path)

        # Search for git in PATH
        try:
            import shutil
            git_path = shutil.which('git')
            if git_path:
                found_paths.append(Path(git_path).parent)
        except Exception:
            pass

        return found_paths

    def validate_source(self, source_path: Path) -> bool:
        git_files = ['git', 'git.exe']

        if source_path.is_file():
            return source_path.name.lower() in [f.lower() for f in git_files]

        for git_file in git_files:
            if (source_path / git_file).exists():
                return True

        # Check bin subdirectory
        bin_dir = source_path / 'bin'
        if bin_dir.exists():
            for git_file in git_files:
                if (bin_dir / git_file).exists():
                    return True

        return False


class ThirdPartyManager:
    """Main manager for all third-party file handling"""

    def __init__(self, config_path: Optional[Path] = None, verbose: bool = False):
        self.config_path = config_path or Path(__file__).parent / "third_party_config.json"
        self.verbose = verbose
        self.config = self._load_config()
        self.handlers = {}
        self._register_handlers()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load config from {self.config_path}: {e}")
            return {"third_party_handlers": {}, "global_settings": {}}

    def _register_handlers(self) -> None:
        """Register all available handlers"""
        handler_classes = {
            'PlaywrightHandler': PlaywrightHandler,
            'ElectronHandler': ElectronHandler,
            'ChromeDriverHandler': ChromeDriverHandler,
            'FFmpegHandler': FFmpegHandler,
            'SeleniumDriverHandler': SeleniumDriverHandler,
            'GitPortableHandler': GitPortableHandler
        }

        for name, handler_config in self.config.get('third_party_handlers', {}).items():
            if not handler_config.get('enabled', False):
                continue

            handler_class_name = handler_config.get('handler_class')
            if handler_class_name in handler_classes:
                global_config = self.config.get('global_settings', {})
                global_config['verbose_logging'] = self.verbose

                handler = handler_classes[handler_class_name](handler_config, global_config)
                self.handlers[name] = handler

                if self.verbose:
                    print(f"[INFO] Registered handler: {name} ({handler_class_name})")

    def process_all(self, destination_base: Optional[Path] = None) -> Dict[str, bool]:
        """Process all enabled third-party components"""
        results = {}
        destination_base = destination_base or Path.cwd()

        for name, handler in self.handlers.items():
            if self.verbose:
                print(f"[INFO] Processing {name}...")

            try:
                # Find source files
                source_paths = handler.find_source_files()
                if not source_paths:
                    if self.verbose:
                        print(f"[WARNING] No source files found for {name}")
                    results[name] = False
                    continue

                # Validate sources
                valid_sources = []
                for source_path in source_paths:
                    if handler.validate_source(source_path):
                        valid_sources.append(source_path)
                    elif self.verbose:
                        print(f"[WARNING] Invalid source: {source_path}")

                if not valid_sources:
                    if self.verbose:
                        print(f"[WARNING] No valid sources for {name}")
                    results[name] = False
                    continue

                # Determine destination
                handler_config = self.config['third_party_handlers'][name]
                destination = destination_base / handler_config.get('destination', f'third_party/{name}')

                # Copy files
                success = handler.copy_files(valid_sources, destination)

                # Validate result
                if success:
                    success = handler.validate_result(destination)

                results[name] = success

                if self.verbose:
                    status = "SUCCESS" if success else "FAILED"
                    print(f"[INFO] {name}: {status}")

            except Exception as e:
                if self.verbose:
                    print(f"[ERROR] Failed to process {name}: {e}")
                results[name] = False

        return results

    def process_component(self, component_name: str, destination_base: Optional[Path] = None) -> bool:
        """Process a specific third-party component"""
        if component_name not in self.handlers:
            if self.verbose:
                print(f"[ERROR] Unknown component: {component_name}")
            return False

        results = self.process_all(destination_base)
        return results.get(component_name, False)

    def list_available_components(self) -> List[str]:
        """List all available third-party components"""
        return list(self.config.get('third_party_handlers', {}).keys())

    def list_enabled_components(self) -> List[str]:
        """List enabled third-party components"""
        return list(self.handlers.keys())

    def add_component(self, name: str, config: Dict[str, Any]) -> bool:
        """Add a new third-party component configuration"""
        try:
            # Add to config
            self.config.setdefault('third_party_handlers', {})[name] = config

            # Save config
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)

            # Re-register handlers if enabled
            if config.get('enabled', False):
                self._register_handlers()

            if self.verbose:
                print(f"[INFO] Added component: {name}")

            return True

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Failed to add component {name}: {e}")
            return False


# Global instance
third_party_manager = ThirdPartyManager()

def set_verbose(verbose: bool) -> None:
    """Set verbose mode for the global third-party manager"""
    global third_party_manager
    third_party_manager.verbose = verbose
    third_party_manager._register_handlers()  # Re-register with new verbose setting
