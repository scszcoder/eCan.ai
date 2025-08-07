#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Unified Build System v9.0
Supports multiple build modes and performance optimization
"""

import sys
import os
import platform
import argparse
import subprocess
from pathlib import Path


class BuildEnvironment:
    """Build environment detection and management"""
    
    def __init__(self):
        self.platform = platform.system()
        self.is_windows = self.platform == "Windows"
        self.is_macos = self.platform == "Darwin"
        self.is_linux = self.platform == "Linux"
        self.is_ci = self._detect_ci_environment()
        
    def _detect_ci_environment(self) -> bool:
        """Detect if running in CI environment"""
        ci_vars = ['GITHUB_ACTIONS', 'CI', 'TRAVIS', 'CIRCLECI']
        return any(os.getenv(var) for var in ci_vars)
    
    def validate_environment(self) -> bool:
        """Validate build environment"""
        print(f"[ENV] Platform: {self.platform}")
        print(f"[ENV] Python: {platform.python_version()}")
        print(f"[ENV] Architecture: {platform.architecture()[0]}")
        print(f"[ENV] CI Environment: {self.is_ci}")
        
        # Check Python version
        if not self._check_python_version():
            return False
            
        # Check virtual environment
        if not self._check_virtual_environment():
            return False
            
        # Check required files
        if not self._check_required_files():
            return False
            
        return True
    
    def _check_python_version(self) -> bool:
        """Check Python version"""
        version = sys.version_info
        if version.major != 3 or version.minor < 8:
            print(f"[ERROR] Python 3.8+ required, current: {version.major}.{version.minor}")
            return False
        return True
    
    def _check_required_files(self) -> bool:
        """Check required files"""
        required_files = [
            "main.py",
            "build_system/ecan_build.py",
            "build_system/build_config.json"
        ]
        
        for file_path in required_files:
            if not Path(file_path).exists():
                print(f"[ERROR] Required file not found: {file_path}")
                return False
        
        return True
    
    def _check_virtual_environment(self) -> bool:
        """Check virtual environment"""
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            print("[SUCCESS] Virtual environment detected")
            return True
        else:
            print("[WARNING] Virtual environment directory exists but not activated")
            print("[INFO] Activating virtual environment...")
            return self._activate_virtual_environment()
    
    def _activate_virtual_environment(self) -> bool:
        """Activate virtual environment"""
        venv_path = Path("venv")
        if not venv_path.exists():
            print("[ERROR] Virtual environment not found")
            return False
        
        # Activate virtual environment on Windows
        if self.is_windows:
            activate_script = venv_path / "Scripts" / "activate.bat"
            if activate_script.exists():
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = str(venv_path / "Scripts") + os.pathsep + os.environ['PATH']
                print("[SUCCESS] Virtual environment activated")
                return True
        else:
            # Activate virtual environment on Unix systems
            activate_script = venv_path / "bin" / "activate"
            if activate_script.exists():
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = str(venv_path / "bin") + os.pathsep + os.environ['PATH']
                print("[SUCCESS] Virtual environment activated")
                return True
        
        print("[ERROR] Failed to activate virtual environment")
        return False


def print_banner():
    """Print build banner"""
    print("=" * 60)
    print("eCan Unified Build System v9.0")
    print("=" * 60)

def print_mode_info(mode: str, fast: bool = False):
    """Print build mode information"""
    print(f"Build Mode: {mode.upper()}")

    if fast:
        print("🚀 Fast Build Features:")
        print("  ✓ Parallel compilation (multi-core CPU acceleration)")
        print("  ✓ Smart caching (incremental build)")
        print("  ✓ Optimized dependencies (~280 packages)")
        print("  ✓ Debug symbols stripped")
        print("  ✓ Estimated time: 2-5 minutes")
    elif mode == "dev":
        print("🔧 Development Build Features:")
        print("  ✓ Parallel compilation (multi-core CPU acceleration)")
        print("  ✓ Console output enabled")
        print("  ✓ Debug symbols preserved")
        print("  ✓ Estimated time: 5-10 minutes")
    else:
        print("🏭 Production Build Features:")
        print("  ✓ Parallel compilation (multi-core CPU acceleration)")
        print("  ✓ Full optimization and cleanup")
        print("  ✓ Debug symbols stripped")
        print("  ✓ LZMA best compression")
        print("  ✓ Estimated time: 15-25 minutes")

    print("=" * 60)

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="eCan Unified Build System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Build mode description:
  fast     Fast build (parallel+cache, 2-5 minutes)
  dev      Development build (parallel+console, 5-10 minutes)
  prod     Production build (parallel+best compression, 15-25 minutes)

Usage examples:
  python build.py fast              # Fast build
  python build.py dev --force       # Force development build
  python build.py prod              # Production build
  python build.py prod --version 2.1.0  # Build with specified version
  python build.py fast --skip-frontend  # Fast build skipping frontend
  python build.py prod --skip-installer # Skip installer creation
        """
    )

    # Positional arguments
    parser.add_argument(
        "mode",
        choices=["fast", "dev", "prod"],
        default="fast",
        nargs="?",
        help="Build mode (default: fast)"
    )

    # Optional arguments
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force rebuild (clean cache)"
    )

    parser.add_argument(
        "--version", "-V",
        type=str,
        help="Specify version number (e.g.: 1.0.0, 2.1.3)"
    )

    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend build (build Python part only)"
    )

    parser.add_argument(
        "--skip-installer",
        action="store_true",
        help="Skip installer creation (generate executable only)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed build information"
    )

    args = parser.parse_args()

    # Validate environment
    env = BuildEnvironment()
    if not env.validate_environment():
        sys.exit(1)

    # Print information
    print_banner()

    # Use specified build mode
    build_mode = args.mode
    fast_mode = args.mode == "fast"

    print_mode_info(args.mode, fast_mode)

    # Build command
    cmd = [sys.executable, "build_system/ecan_build.py", build_mode]

    # Add optional parameters
    if args.force:
        cmd.append("--force")
    if args.version:
        cmd.extend(["--version", args.version])
    if args.skip_frontend:
        cmd.append("--skip-frontend")
    if args.skip_installer:
        cmd.append("--skip-installer")

    print(f"[EXEC] Executing command: {' '.join(cmd)}")
    print("=" * 60)

    # Execute build
    try:
        subprocess.run(cmd, check=True)

        print("\n" + "=" * 60)
        print("🎉 Build completed!")
        print("=" * 60)

        # Determine executable filename and installer info based on OS
        if platform.system() == "Windows":
            exe_name = "eCan.exe"
            installer_info = f"📦 Installer: {Path.cwd()}/dist/eCan-Setup.exe"
        elif platform.system() == "Darwin":
            exe_name = "eCan"  # macOS
            installer_info = f"📦 Installer: {Path.cwd()}/dist/eCan-1.0.0.pkg"
        else:
            exe_name = "eCan"  # Linux
            installer_info = "📦 Installer: Linux installer not supported yet"

        print(f"📁 Executable: {Path.cwd()}/dist/eCan/{exe_name}")
        if not args.skip_frontend:
            print(f"🌐 Frontend: {Path.cwd()}/gui_v2/dist/")
        if not args.skip_installer:
            print(installer_info)
        print("=" * 60)

        return 0

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed, exit code: {e.returncode}")
        return e.returncode
    except KeyboardInterrupt:
        print("\n⏹️  Build interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Build failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())