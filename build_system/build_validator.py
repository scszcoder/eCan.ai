#!/usr/bin/env python3
"""
Unified Build Validator
Integrates platform detection, environment validation, and build checks
"""

import sys
import os
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import json

# Import existing modules
try:
    from .platform_handler import platform_handler
    from .build_logger import get_build_logger
except ImportError:
    # Fallback for direct execution
    from platform_handler import platform_handler
    from build_logger import get_build_logger

class BuildValidator:
    """Unified build validation system"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = get_build_logger(verbose=verbose)
        self.platform_handler = platform_handler
        self.validation_results = {}
        
    def run_full_validation(self) -> Dict[str, Any]:
        """Run complete build validation"""
        self.logger.info("Starting comprehensive build validation", "VALIDATOR")
        
        results = {
            "platform": self._validate_platform(),
            "environment": self._validate_environment(),
            "project": self._validate_project_structure(),
            "dependencies": self._validate_dependencies(),
            "platform_specific": self._validate_platform_specific(),
            "overall_status": "pending"
        }
        
        # Determine overall status
        all_passed = all(
            result.get("status") == "pass" 
            for result in results.values() 
            if isinstance(result, dict) and "status" in result
        )
        
        results["overall_status"] = "pass" if all_passed else "fail"
        results["summary"] = self._generate_summary(results)
        
        self.validation_results = results
        return results
    
    def _validate_platform(self) -> Dict[str, Any]:
        """Validate platform and architecture"""
        result = {
            "status": "pass",
            "platform": self.platform_handler.platform,
            "architecture": self.platform_handler.architecture,
            "identifier": self.platform_handler.get_platform_identifier(),
            "issues": [],
            "info": {}
        }
        
        # Basic platform info
        result["info"] = {
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "is_arm64": self.platform_handler.is_arm64,
            "is_macos": self.platform_handler.is_macos,
            "is_windows": self.platform_handler.is_windows,
            "is_linux": self.platform_handler.is_linux
        }
        
        # Platform-specific validations
        if self.platform_handler.is_macos:
            macos_issues = self._validate_macos_platform()
            result["issues"].extend(macos_issues)
            
        elif self.platform_handler.is_windows:
            windows_issues = self._validate_windows_platform()
            result["issues"].extend(windows_issues)
            
        elif self.platform_handler.is_linux:
            linux_issues = self._validate_linux_platform()
            result["issues"].extend(linux_issues)
        
        if result["issues"]:
            result["status"] = "fail"
            
        return result
    
    def _validate_macos_platform(self) -> List[str]:
        """macOS specific platform validation"""
        issues = []
        
        # Check Xcode Command Line Tools
        try:
            subprocess.run(["xcode-select", "--print-path"], 
                         check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            issues.append("Xcode Command Line Tools not installed")
        
        # Apple Silicon specific checks
        if self.platform_handler.is_arm64:
            issues.extend(self._validate_apple_silicon())
        
        return issues
    
    def _validate_apple_silicon(self) -> List[str]:
        """Apple Silicon specific validation"""
        issues = []
        
        # Check for Rosetta 2 usage
        try:
            # Check if current process is under Rosetta
            result = subprocess.run(['sysctl', '-n', 'sysctl.proc_translated'], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip() == '1':
                issues.append("Python running under Rosetta 2 - consider ARM64 native Python")
        except Exception:
            pass
        
        # Check Python binary architecture
        try:
            result = subprocess.run(['file', sys.executable], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and 'x86_64' in result.stdout.lower():
                issues.append("Python binary is x86_64 - consider ARM64 native Python")
        except Exception:
            pass
        
        # Check for Universal Binary tools
        if not shutil.which("lipo"):
            issues.append("lipo tool not found (needed for Universal Binary support)")
        
        return issues
    
    def _validate_windows_platform(self) -> List[str]:
        """Windows specific platform validation"""
        issues = []
        
        # Check PowerShell
        if not shutil.which("powershell"):
            issues.append("PowerShell not found")
        
        return issues
    
    def _validate_linux_platform(self) -> List[str]:
        """Linux specific platform validation"""
        issues = []
        
        # Check GCC
        if not shutil.which("gcc"):
            issues.append("GCC compiler not found")
        
        return issues
    
    def _validate_environment(self) -> Dict[str, Any]:
        """Validate build environment"""
        result = {
            "status": "pass",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "issues": [],
            "tools": {}
        }
        
        # Python version check
        if sys.version_info < (3, 8):
            result["issues"].append(f"Python {sys.version_info.major}.{sys.version_info.minor} is too old. Minimum required: 3.8")
        
        # Check essential tools
        essential_tools = {
            "git": "Version control",
            "pip": "Package manager"
        }
        
        for tool, description in essential_tools.items():
            if shutil.which(tool):
                result["tools"][tool] = {"available": True, "description": description}
            else:
                result["tools"][tool] = {"available": False, "description": description}
                result["issues"].append(f"Missing tool: {tool} ({description})")
        
        if result["issues"]:
            result["status"] = "fail"
            
        return result
    
    def _validate_project_structure(self) -> Dict[str, Any]:
        """Validate project structure"""
        result = {
            "status": "pass",
            "issues": [],
            "structure": {}
        }
        
        # Required directories
        required_dirs = ["gui", "agent", "utils", "build_system"]
        for dir_name in required_dirs:
            exists = os.path.exists(dir_name)
            result["structure"][dir_name] = {"type": "directory", "exists": exists}
            if not exists:
                result["issues"].append(f"Missing required directory: {dir_name}")
        
        # Required files
        required_files = ["main.py", "build.py"]
        for file_name in required_files:
            exists = os.path.exists(file_name)
            result["structure"][file_name] = {"type": "file", "exists": exists}
            if not exists:
                result["issues"].append(f"Missing required file: {file_name}")
        
        # Optional files
        optional_files = ["requirements.txt", "README.md"]
        for file_name in optional_files:
            exists = os.path.exists(file_name)
            result["structure"][file_name] = {"type": "file", "exists": exists, "optional": True}
        
        # Check for spec files
        spec_files = list(Path(".").glob("eCan*.spec"))
        result["structure"]["spec_files"] = {
            "type": "files", 
            "count": len(spec_files),
            "files": [str(f) for f in spec_files]
        }
        
        if result["issues"]:
            result["status"] = "fail"
            
        return result
    
    def _validate_dependencies(self) -> Dict[str, Any]:
        """Validate Python dependencies"""
        result = {
            "status": "pass",
            "issues": [],
            "dependencies": {}
        }
        
        # Key dependencies to check (name -> import_name mapping)
        key_deps = {
            "PyInstaller": "PyInstaller",
            "PySide6": "PySide6",
            "requests": "requests",
            "playwright": "playwright"
        }

        for dep_name, import_name in key_deps.items():
            try:
                __import__(import_name)
                result["dependencies"][dep_name] = {"installed": True}
            except ImportError:
                result["dependencies"][dep_name] = {"installed": False}
                result["issues"].append(f"Missing dependency: {dep_name}")
        
        if result["issues"]:
            result["status"] = "fail"
            
        return result
    
    def _validate_platform_specific(self) -> Dict[str, Any]:
        """Platform-specific validations"""
        result = {
            "status": "pass",
            "issues": [],
            "checks": {}
        }
        
        # Playwright browser check (all platforms)
        browser_check = self._check_playwright_browsers()
        result["checks"]["playwright_browsers"] = browser_check
        if browser_check.get("architecture_mismatch"):
            result["issues"].append("Playwright browser architecture mismatch")

        if self.platform_handler.is_macos:
            # Symlink validation (simplified)
            symlink_check = self._check_critical_symlinks()
            result["checks"]["symlinks"] = symlink_check
            if symlink_check.get("broken_count", 0) > 0:
                result["issues"].append(f"Found {symlink_check['broken_count']} broken symlinks")
        
        if result["issues"]:
            result["status"] = "fail"
            
        return result
    
    def _check_playwright_browsers(self) -> Dict[str, Any]:
        """Check Playwright browser architecture"""
        result = {
            "browsers_found": False,
            "arm64_browsers": 0,
            "x64_browsers": 0,
            "architecture_mismatch": False
        }
        
        # Check common Playwright cache locations
        cache_paths = [
            Path.home() / ".cache" / "ms-playwright",  # Linux
            Path.home() / "Library" / "Caches" / "ms-playwright",  # macOS
            Path.cwd() / "third_party" / "ms-playwright"  # Project local
        ]

        # Add Windows specific paths
        if self.platform_handler.is_windows:
            cache_paths.extend([
                Path.home() / "AppData" / "Local" / "ms-playwright",
                Path.home() / "AppData" / "Local" / "eCan" / "ms-playwright"
            ])

        for cache_path in cache_paths:
            if cache_path.exists():
                result["browsers_found"] = True

                # Count browsers by architecture
                for browser_dir in cache_path.glob("chromium-*"):
                    if browser_dir.is_dir():
                        for platform_dir in browser_dir.iterdir():
                            if platform_dir.is_dir():
                                platform_name = platform_dir.name.lower()
                                if "arm64" in platform_name or "mac-arm" in platform_name:
                                    result["arm64_browsers"] += 1
                                elif ("x64" in platform_name or "mac" in platform_name or
                                      "win" in platform_name or "chrome-win" in platform_name):
                                    result["x64_browsers"] += 1
                break
        
        # Check for architecture mismatch
        current_arch = platform.machine().lower()
        if current_arch in ('arm64', 'aarch64'):
            if result["x64_browsers"] > 0 and result["arm64_browsers"] == 0:
                result["architecture_mismatch"] = True
        
        return result
    
    def _check_critical_symlinks(self) -> Dict[str, Any]:
        """Check for critical broken symlinks"""
        result = {
            "checked": 0,
            "broken_count": 0,
            "broken_links": []
        }
        
        # Check common locations for symlinks
        check_paths = [
            Path.cwd() / "dist",
            Path.cwd() / "build"
        ]
        
        for check_path in check_paths:
            if check_path.exists():
                for item in check_path.rglob("*"):
                    if item.is_symlink():
                        result["checked"] += 1
                        if not item.exists():
                            result["broken_count"] += 1
                            result["broken_links"].append(str(item))
        
        return result
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate validation summary"""
        total_issues = 0
        categories_passed = 0
        categories_total = 0
        
        for _, result in results.items():
            if isinstance(result, dict) and "status" in result:
                categories_total += 1
                if result["status"] == "pass":
                    categories_passed += 1
                if "issues" in result:
                    total_issues += len(result["issues"])
        
        return {
            "total_issues": total_issues,
            "categories_passed": categories_passed,
            "categories_total": categories_total,
            "success_rate": f"{categories_passed}/{categories_total}",
            "overall_status": results.get("overall_status", "unknown")
        }

    def validate_build_artifacts(self, version: str, arch: str = "amd64") -> Dict[str, Any]:
        """验证构建产物是否完整"""
        self.logger.info(f"Validating build artifacts for version {version}, arch {arch}", "VALIDATOR")

        checks = []
        platform_name = platform.system()

        if platform_name == "Windows":
            checks.extend(self._validate_windows_artifacts(version, arch))
        elif platform_name == "Darwin":
            checks.extend(self._validate_macos_artifacts(version, arch))
        elif platform_name == "Linux":
            checks.extend(self._validate_linux_artifacts(version, arch))
        else:
            checks.append({
                "name": "platform_support",
                "status": "fail",
                "message": f"Unsupported platform: {platform_name}"
            })

        all_checks_passed = all(check["status"] == "pass" for check in checks)

        return {
            "status": "pass" if all_checks_passed else "fail",
            "checks": checks,
            "summary": f"Build artifacts validation {'passed' if all_checks_passed else 'failed'}"
        }

    def _validate_windows_artifacts(self, version: str, arch: str) -> List[Dict[str, Any]]:
        """验证 Windows 构建产物"""
        checks = []

        # 检查主执行文件
        exe_path = Path("dist/eCan/eCan.exe")
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            checks.append({
                "name": "main_executable",
                "status": "pass",
                "message": f"Main executable found: {exe_path} ({size_mb:.1f} MB)"
            })
        else:
            checks.append({
                "name": "main_executable",
                "status": "fail",
                "message": f"Main executable not found: {exe_path}"
            })

        # 检查标准化的执行文件（支持多种命名格式）
        std_exe_patterns = [
            f"dist/eCan-{version}-windows-{arch}.exe",  # 构建脚本生成的格式
            f"dist/eCan-Setup-windows-{arch}-v{version}.exe",  # 安装包重命名格式
        ]

        std_exe_found = False
        for pattern in std_exe_patterns:
            std_exe = Path(pattern)
            if std_exe.exists():
                size_mb = std_exe.stat().st_size / (1024 * 1024)
                checks.append({
                    "name": "standardized_executable",
                    "status": "pass",
                    "message": f"Standardized executable found: {std_exe} ({size_mb:.1f} MB)"
                })
                std_exe_found = True
                break

        if not std_exe_found:
            checks.append({
                "name": "standardized_executable",
                "status": "fail",
                "message": f"Standardized executable not found. Tried: {', '.join(std_exe_patterns)}"
            })

        # 检查安装包（可选）- 可能与标准化执行文件是同一个文件
        installer_patterns = [
            f"dist/eCan-Setup.exe",  # 原始安装包名
            f"dist/eCan-Setup-windows-{arch}-v{version}.exe",  # 重命名后的安装包
        ]

        installer_found = False
        for pattern in installer_patterns:
            installer_path = Path(pattern)
            if installer_path.exists():
                size_mb = installer_path.stat().st_size / (1024 * 1024)
                checks.append({
                    "name": "installer",
                    "status": "pass",
                    "message": f"Installer found: {installer_path} ({size_mb:.1f} MB)"
                })
                installer_found = True
                break

        if not installer_found:
            # 检查是否安装包被重命名为标准化执行文件
            if std_exe_found:
                checks.append({
                    "name": "installer",
                    "status": "pass",
                    "message": "Installer integrated into standardized executable"
                })
            else:
                checks.append({
                    "name": "installer",
                    "status": "warn",
                    "message": f"Installer not found (optional). Tried: {', '.join(installer_patterns)}"
                })

        return checks

    def _validate_macos_artifacts(self, version: str, arch: str) -> List[Dict[str, Any]]:
        """验证 macOS 构建产物"""
        checks = []

        # 检查 App Bundle
        app_path = Path("dist/eCan.app")
        if app_path.exists():
            checks.append({
                "name": "app_bundle",
                "status": "pass",
                "message": f"App bundle found: {app_path}"
            })

            # 检查 App 内的可执行文件
            exe_path = app_path / "Contents" / "MacOS" / "eCan"
            if exe_path.exists():
                checks.append({
                    "name": "app_executable",
                    "status": "pass",
                    "message": f"App executable found: {exe_path}"
                })
            else:
                checks.append({
                    "name": "app_executable",
                    "status": "fail",
                    "message": f"App executable not found: {exe_path}"
                })
        else:
            checks.append({
                "name": "app_bundle",
                "status": "fail",
                "message": f"App bundle not found: {app_path}"
            })

        # 检查 DMG 文件（可选）
        dmg_patterns = [
            f"dist/eCan-{version}-macos-{arch}.dmg",  # 标准化格式
            f"dist/eCan-macos-{arch}-v{version}.dmg",  # 旧格式
        ]

        dmg_found = False
        for pattern in dmg_patterns:
            dmg_path = Path(pattern)
            if dmg_path.exists():
                size_mb = dmg_path.stat().st_size / (1024 * 1024)
                checks.append({
                    "name": "dmg_package",
                    "status": "pass",
                    "message": f"DMG found: {dmg_path} ({size_mb:.1f} MB)"
                })
                dmg_found = True
                break

        if not dmg_found:
            checks.append({
                "name": "dmg_package",
                "status": "warn",
                "message": f"DMG not found (optional). Tried: {', '.join(dmg_patterns)}"
            })

        return checks

    def _validate_linux_artifacts(self, version: str, arch: str) -> List[Dict[str, Any]]:
        """验证 Linux 构建产物"""
        checks = []

        # 检查主执行文件
        exe_path = Path("dist/eCan/eCan")
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            checks.append({
                "name": "main_executable",
                "status": "pass",
                "message": f"Main executable found: {exe_path} ({size_mb:.1f} MB)"
            })
        else:
            checks.append({
                "name": "main_executable",
                "status": "fail",
                "message": f"Main executable not found: {exe_path}"
            })

        return checks

    def print_validation_report(self, results: Optional[Dict[str, Any]] = None) -> None:
        """Print formatted validation report"""
        if results is None:
            results = self.validation_results

        if not results:
            print("No validation results available")
            return

        print("=" * 60)
        print("Build Validation Report")
        print("=" * 60)

        # Check if this is an artifacts-only validation
        if "artifacts" in results and len(results) <= 2:  # artifacts + overall_status
            artifacts_result = results["artifacts"]
            overall_status = results.get("overall_status", artifacts_result.get("status", "unknown"))

            print(f"Overall Status: {overall_status.upper()}")
            print(f"Validation Type: Build Artifacts Only")

            # Platform info from system
            platform_name = platform.system()
            arch = platform.machine()
            print(f"Platform: {platform_name} ({arch})")

            # Show artifact checks
            checks = artifacts_result.get("checks", [])
            if checks:
                print(f"\nArtifact Checks:")
                for check in checks:
                    status_symbol = "✓" if check["status"] == "pass" else "✗" if check["status"] == "fail" else "⚠"
                    print(f"  {status_symbol} {check['name']}: {check['message']}")

            # Show summary
            print(f"\nSummary: {artifacts_result.get('summary', 'No summary available')}")

        else:
            # Full validation report
            summary = results.get("summary", {})
            print(f"Overall Status: {summary.get('overall_status', 'unknown').upper()}")
            print(f"Categories: {summary.get('success_rate', 'unknown')}")
            print(f"Total Issues: {summary.get('total_issues', 0)}")

            # Platform info
            platform_info = results.get("platform", {})
            print(f"\nPlatform: {platform_info.get('platform', 'unknown')} ({platform_info.get('architecture', 'unknown')})")

            # Show issues by category
            for category, result in results.items():
                if isinstance(result, dict) and "issues" in result and result["issues"]:
                    print(f"\n{category.upper()} Issues:")
                    for issue in result["issues"]:
                        print(f"  [!] {issue}")

            # Show recommendations
            if summary.get("total_issues", 0) > 0:
                print(f"\nRecommendations:")
                print("  1. Fix the issues listed above")
                print("  2. Re-run validation: python build_system/build_validator.py")
                print("  3. Check platform-specific documentation")

def main():
    """Main function for standalone usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build Validation Tool")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--artifacts", action="store_true", help="Validate build artifacts only")
    parser.add_argument("--version", help="Version string for artifact validation")
    parser.add_argument("--arch", default="amd64", help="Architecture for artifact validation (default: amd64)")

    args = parser.parse_args()

    validator = BuildValidator(verbose=args.verbose)

    if args.artifacts:
        if not args.version:
            print("Error: --version is required when using --artifacts")
            sys.exit(1)
        results = {"artifacts": validator.validate_build_artifacts(args.version, args.arch)}
        results["overall_status"] = results["artifacts"]["status"]
    else:
        results = validator.run_full_validation()

    if args.json:
        import json
        print(json.dumps(results, indent=2))
    else:
        validator.print_validation_report(results)

    # Exit with appropriate code
    sys.exit(0 if results.get("overall_status") == "pass" else 1)

if __name__ == "__main__":
    main()
