#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified platform handler for build system
Provides consistent platform detection and configuration management
"""

import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List


class PlatformHandler:
    """Unified platform detection and configuration handler"""
    
    # Platform constants
    WINDOWS = "windows"
    MACOS = "macos" 
    LINUX = "linux"
    
    # Architecture constants
    AMD64 = "amd64"
    ARM64 = "arm64"
    X86 = "x86"
    
    def __init__(self):
        self._platform = self._detect_platform()
        self._architecture = self._detect_architecture()
        
    @property
    def platform(self) -> str:
        """Get current platform"""
        return self._platform
        
    @property
    def architecture(self) -> str:
        """Get current architecture"""
        return self._architecture
        
    @property
    def is_windows(self) -> bool:
        """Check if running on Windows"""
        return self._platform == self.WINDOWS
        
    @property
    def is_macos(self) -> bool:
        """Check if running on macOS"""
        return self._platform == self.MACOS
        
    @property
    def is_linux(self) -> bool:
        """Check if running on Linux"""
        return self._platform == self.LINUX
        
    @property
    def is_arm64(self) -> bool:
        """Check if running on ARM64 architecture"""
        return self._architecture == self.ARM64
        
    @property
    def is_amd64(self) -> bool:
        """Check if running on AMD64/x64 architecture"""
        return self._architecture == self.AMD64
        
    def _detect_platform(self) -> str:
        """Detect current platform"""
        system = platform.system().lower()
        if system == "darwin":
            return self.MACOS
        elif system == "windows":
            return self.WINDOWS
        elif system == "linux":
            return self.LINUX
        else:
            return system
            
    def _detect_architecture(self) -> str:
        """Detect current architecture"""
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            return self.AMD64
        elif machine in ("arm64", "aarch64"):
            return self.ARM64
        elif machine in ("i386", "i686", "x86"):
            return self.X86
        else:
            return machine
            
    def get_platform_identifier(self) -> str:
        """Get platform identifier string (e.g., 'macos-arm64')"""
        return f"{self._platform}-{self._architecture}"
        
    def get_executable_extension(self) -> str:
        """Get executable file extension for current platform"""
        if self.is_windows:
            return ".exe"
        else:
            return ""
            
    def get_library_extension(self) -> str:
        """Get dynamic library extension for current platform"""
        if self.is_windows:
            return ".dll"
        elif self.is_macos:
            return ".dylib"
        else:
            return ".so"
            
    def get_python_executable(self, venv_path: Optional[Path] = None) -> str:
        """Get Python executable path for current platform"""
        if venv_path:
            if self.is_windows:
                python_exe = venv_path / "Scripts" / "python.exe"
            else:
                python_exe = venv_path / "bin" / "python3"
            
            if python_exe.exists():
                return str(python_exe)
        
        return sys.executable
        
    def get_platform_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get platform-specific configuration from config dict"""
        platforms_config = config.get("platforms", {})
        return platforms_config.get(self._platform, {})
        
    def get_build_paths(self, project_root: Path) -> Dict[str, Path]:
        """Get platform-specific build paths"""
        paths = {
            "project_root": project_root,
            "dist": project_root / "dist",
            "build": project_root / "build",
            "venv": project_root / "venv"
        }
        
        if self.is_windows:
            paths.update({
                "venv_scripts": paths["venv"] / "Scripts",
                "venv_python": paths["venv"] / "Scripts" / "python.exe"
            })
        else:
            paths.update({
                "venv_scripts": paths["venv"] / "bin", 
                "venv_python": paths["venv"] / "bin" / "python3"
            })
            
        return paths
        
    def get_codesign_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get code signing configuration for current platform"""
        platform_config = self.get_platform_config(config)
        
        if self.is_macos:
            return platform_config.get("codesign", {})
        elif self.is_windows:
            return platform_config.get("sign", {})
        else:
            return {}
            
    def get_installer_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get installer configuration for current platform"""
        installer_config = config.get("installer", {})
        platform_config = installer_config.get(self._platform, {})
        return platform_config
        
    def should_exclude_from_codesign(self, file_path: str, exclude_patterns: List[str]) -> bool:
        """Check if file should be excluded from code signing"""
        if not self.is_macos:
            return False
            
        import fnmatch
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False
        
    def get_framework_paths(self, app_bundle: Path) -> List[Path]:
        """Get framework paths in macOS app bundle"""
        if not self.is_macos:
            return []
            
        frameworks_dir = app_bundle / "Contents" / "Frameworks"
        if not frameworks_dir.exists():
            return []
            
        return [f for f in frameworks_dir.iterdir() if f.suffix == ".framework"]
        
    def validate_environment(self) -> Dict[str, Any]:
        """Validate build environment for current platform"""
        result = {
            "platform": self._platform,
            "architecture": self._architecture,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "issues": []
        }
        
        # Check Python version
        if sys.version_info < (3, 8):
            result["issues"].append(f"Python 3.8+ required, current: {result['python_version']}")
            
        # Platform-specific checks
        if self.is_macos:
            # Check for Xcode command line tools
            import subprocess
            try:
                subprocess.run(["xcode-select", "--print-path"],
                             check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                result["issues"].append("Xcode command line tools not installed")

            # Apple Silicon specific checks
            if self.is_arm64:
                arm64_issues = self._validate_apple_silicon_environment()
                result["issues"].extend(arm64_issues)

        elif self.is_windows:
            # Check for Visual Studio Build Tools
            vs_paths = [
                Path("C:/Program Files (x86)/Microsoft Visual Studio/2019/BuildTools"),
                Path("C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools"),
                Path("C:/Program Files/Microsoft Visual Studio/2019/Community"),
                Path("C:/Program Files/Microsoft Visual Studio/2022/Community")
            ]
            if not any(p.exists() for p in vs_paths):
                result["issues"].append("Visual Studio Build Tools not found")
                
        return result

    def _validate_apple_silicon_environment(self) -> list:
        """Validate Apple Silicon (ARM64) specific environment"""
        issues = []

        # Check if Python is running natively on ARM64
        try:
            import subprocess
            result = subprocess.run(['python3', '-c', 'import platform; print(platform.machine())'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                machine = result.stdout.strip().lower()
                if machine not in ('arm64', 'aarch64'):
                    issues.append("Python may be running under Rosetta 2. Consider using ARM64 native Python for better performance")
        except Exception:
            pass

        # Check for Universal Binary support tools
        if not shutil.which("lipo"):
            issues.append("lipo tool not found (needed for Universal Binary support)")

        return issues

    def __str__(self) -> str:
        """String representation"""
        return f"PlatformHandler({self.get_platform_identifier()})"
        
    def __repr__(self) -> str:
        """Detailed representation"""
        return f"PlatformHandler(platform='{self._platform}', arch='{self._architecture}')"


# Global instance
platform_handler = PlatformHandler()
