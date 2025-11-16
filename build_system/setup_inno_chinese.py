#!/usr/bin/env python3
"""
Automatically download and install the Inno Setup Simplified Chinese language pack.

This script will:
1. Download the ChineseSimplified.isl language pack
2. Copy it to the Inno Setup Languages directory
3. Verify that the installation was successful

Usage:
    python setup_inno_chinese.py
"""

import os
import sys
import shutil
from pathlib import Path
import urllib.request
import urllib.error


def print_step(message: str):
    """Print step information"""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}")


def print_success(message: str):
    """Print success information"""
    print(f"✓ {message}")


def print_error(message: str):
    """Print error information"""
    print(f"✗ {message}", file=sys.stderr)


def print_warning(message: str):
    """Print warning information"""
    print(f"⚠ {message}")


def find_inno_setup_dir() -> Path:
    """Locate the Inno Setup installation directory"""
    possible_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6"),
        Path(r"C:\Program Files\Inno Setup 6"),
        Path(r"C:\Program Files (x86)\Inno Setup 5"),
        Path(r"C:\Program Files\Inno Setup 5"),
    ]
    
    for path in possible_paths:
        if path.exists() and (path / "ISCC.exe").exists():
            return path
    
    return None


def download_language_pack(script_dir: Path) -> Path:
    """Download the language pack"""
    print_step("Step 1: Download Simplified Chinese language pack")

    # Target directory and file
    target_dir = script_dir / "inno_setup_languages"
    target_dir.mkdir(parents=True, exist_ok=True)

    url = (
        "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/"
        "Languages/Unofficial/ChineseSimplified.isl"
    )
    lang_file = target_dir / "ChineseSimplified.isl"

    print(f"Download URL: {url}")
    print(f"Save path: {lang_file}")

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()

        if not data:
            print_error("Downloaded content is empty")
            sys.exit(1)

        lang_file.write_bytes(data)
        size_kb = len(data) / 1024.0
        print_success(f"Language pack downloaded to: {lang_file} ({size_kb:.1f} KB)")
        return lang_file

    except urllib.error.URLError as e:
        print_error(f"Download failed (network error): {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Error during download: {e}")
        sys.exit(1)


def copy_to_inno_setup(source_file: Path, inno_dir: Path) -> bool:
    """Copy the language pack to the Inno Setup directory"""
    print_step("Step 2: Install language pack into Inno Setup")
    
    languages_dir = inno_dir / "Languages"
    if not languages_dir.exists():
        print_error(f"Inno Setup Languages directory does not exist: {languages_dir}")
        return False
    
    # Target file (note the .isl extension)
    target_file = languages_dir / "ChineseSimplified.isl"
    
    print(f"Source file: {source_file}")
    print(f"Target location: {target_file}")
    
    try:
        # Try copying directly
        shutil.copy2(source_file, target_file)
        print_success(f"Language pack installed to: {target_file}")
        return True
        
    except PermissionError:
        print_warning("Administrator privileges are required to copy files into Program Files")
        print("\nPlease choose one of the following options:")
        print("1. Re-run this script as Administrator")
        print("2. Copy the file manually (requires Administrator privileges):")
        print(f"   Source file: {source_file}")
        print(f"   Target location: {target_file}")
        print("\nManual copy command (run in an elevated PowerShell window):")
        print(f'   Copy-Item "{source_file}" "{target_file}" -Force')
        return False
        
    except Exception as e:
        print_error(f"Error while copying file: {e}")
        return False


def verify_installation(inno_dir: Path) -> bool:
    """Verify that the language pack was installed successfully"""
    print_step("Step 3: Verify installation")
    
    target_file = inno_dir / "Languages" / "ChineseSimplified.isl"
    
    if not target_file.exists():
        print_error(f"Language pack file does not exist: {target_file}")
        return False
    
    # Check file size
    file_size = target_file.stat().st_size
    if file_size < 1000:
        print_warning(f"Language pack file seems too small: {file_size} bytes")
        return False
    
    # Check file content
    try:
        with open(target_file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            
        # Verify required sections
        required_sections = ['[LangOptions]', '[Messages]', 'LanguageID=']
        missing = [s for s in required_sections if s not in content]
        
        if missing:
            print_error(f"Language pack file is missing required sections: {missing}")
            return False
        
        print_success(f"Language pack installed successfully ({file_size} bytes)")
        print(f"  File path: {target_file}")
        
        # Try to extract language information
        import re
        if match := re.search(r'LanguageName=(.+)', content):
            lang_name = match.group(1).strip()
            print(f"  Language name: {lang_name}")
        
        return True
        
    except Exception as e:
        print_error(f"Error while verifying file: {e}")
        return False


def main():
    """Main entry point"""
    print_step("Inno Setup Simplified Chinese language pack auto installer")
    
    # Get script directory
    script_dir = Path(__file__).parent
    print(f"Working directory: {script_dir}")
    
    # Find Inno Setup installation directory
    print("\nSearching for Inno Setup installation directory...")
    inno_dir = find_inno_setup_dir()
    
    if not inno_dir:
        print_error("Could not find Inno Setup installation directory")
        print("\nPlease make sure Inno Setup is installed in one of the following locations:")
        print("  - C:\\Program Files (x86)\\Inno Setup 6")
        print("  - C:\\Program Files\\Inno Setup 6")
        sys.exit(1)
    
    print_success(f"Found Inno Setup: {inno_dir}")
    
    # Download language pack
    lang_file = download_language_pack(script_dir)
    
    # Copy to Inno Setup directory
    if not copy_to_inno_setup(lang_file, inno_dir):
        print_error("\nInstallation failed")
        sys.exit(1)
    
    # Verify installation
    if not verify_installation(inno_dir):
        print_error("\nVerification failed")
        sys.exit(1)
    
    # Success
    print_step("Installation complete")
    print_success("Simplified Chinese language pack has been successfully installed into Inno Setup")
    print("\nYou can now rerun the build command and the installer will support both English and Simplified Chinese.")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
