#!/usr/bin/env python3
"""
Inno Setup Language Pack Downloader

Download and update language packs from the official Inno Setup repository.
This ensures all language files are properly formatted and compatible.

Usage:
    # Download specific languages
    python download_inno_languages.py ChineseSimplified Japanese Korean

    # Download all available unofficial languages
    python download_inno_languages.py --all-unofficial

    # List available languages
    python download_inno_languages.py --list

    # Update existing languages
    python download_inno_languages.py --update-existing
"""

import argparse
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Optional
import re

# Official Inno Setup language repository
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages"
OFFICIAL_LANGS_URL = f"{GITHUB_RAW_BASE}"
UNOFFICIAL_LANGS_URL = f"{GITHUB_RAW_BASE}/Unofficial"

# Available official languages (always up to date with Inno Setup)
OFFICIAL_LANGUAGES = [
    "Afrikaans",
    "Albanian",
    "Arabic",
    "Armenian",
    "Basque",
    "Belarusian",
    "Bengali",
    "Bosnian",
    "BrazilianPortuguese",
    "Bulgarian",
    "Catalan",
    "Corsican",
    "Croatian",
    "Czech",
    "Danish",
    "Dutch",
    "English",
    "Estonian",
    "Farsi",
    "Finnish",
    "French",
    "Galician",
    "Georgian",
    "German",
    "Greek",
    "Hebrew",
    "Hindi",
    "Hungarian",
    "Icelandic",
    "Indonesian",
    "Irish",
    "Italian",
    "Japanese",
    "Korean",
    "Latvian",
    "Lithuanian",
    "Luxemburgish",
    "Macedonian",
    "Malay",
    "Mongolian",
    "Nepali",
    "Norwegian",
    "Polish",
    "Portuguese",
    "Romanian",
    "Russian",
    "ScottishGaelic",
    "Serbian",
    "SerbianCyrillic",
    "SerbianLatin",
    "Sinhala",
    "Slovak",
    "Slovenian",
    "Spanish",
    "Swedish",
    "Thai",
    "Turkish",
    "Ukrainian",
    "Uzbek",
    "Vietnamese",
    "Welsh",
]

# Available unofficial languages (community-maintained)
UNOFFICIAL_LANGUAGES = [
    "ChineseSimplified",
    "ChineseTraditional",
]

# Get the languages directory
SCRIPT_DIR = Path(__file__).parent
LANGUAGES_DIR = SCRIPT_DIR / "inno_setup_languages"


class Colors:
    """Terminal colors for pretty output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_colored(message: str, color: str = ""):
    """Print colored message if terminal supports it"""
    if sys.stdout.isatty():
        print(f"{color}{message}{Colors.END}")
    else:
        print(message)


def download_language(language: str, is_unofficial: bool = False) -> Optional[Path]:
    """
    Download a language pack from the official repository and convert to .islu format.
    
    Args:
        language: Language name (e.g., 'ChineseSimplified')
        is_unofficial: Whether to download from unofficial languages
        
    Returns:
        Path to downloaded .islu file, or None if failed
    """
    base_url = UNOFFICIAL_LANGS_URL if is_unofficial else OFFICIAL_LANGS_URL
    source_filename = f"{language}.isl"
    url = f"{base_url}/{source_filename}"
    # Always save as .islu (Unicode format)
    output_path = LANGUAGES_DIR / f"{language}.islu"
    
    print_colored(f"Downloading {source_filename} (will convert to .islu)...", Colors.CYAN)
    print(f"  Source: {url}")
    
    try:
        # Create directory if needed
        LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)
        
        # Download with user agent
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'eCan-Language-Downloader/1.0'}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()
            
        # Write to file as UTF-8 and convert to .islu format
        with open(output_path, 'wb') as f:
            f.write(content)
        
        # Convert to .islu format (set LanguageCodePage=0 for Unicode)
        convert_to_islu(output_path)
            
        # Verify it's a valid language file
        if verify_language_file(output_path):
            size_kb = len(content) / 1024
            print_colored(f"✓ Downloaded and converted: {output_path.name} ({size_kb:.1f} KB)", Colors.GREEN)
            
            # Extract and display language info
            lang_info = extract_language_info(output_path)
            if lang_info:
                print(f"  Language Name: {lang_info.get('name', 'Unknown')}")
                print(f"  Language ID: {lang_info.get('id', 'Unknown')}")
                print(f"  Code Page: {lang_info.get('codepage', 'Unknown')}")
            
            return output_path
        else:
            print_colored(f"✗ Invalid language file: {output_path.name}", Colors.RED)
            output_path.unlink()  # Delete invalid file
            return None
            
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print_colored(f"✗ Language not found: {language}", Colors.RED)
        else:
            print_colored(f"✗ HTTP Error {e.code}: {e.reason}", Colors.RED)
        return None
    except urllib.error.URLError as e:
        print_colored(f"✗ Network Error: {e.reason}", Colors.RED)
        return None
    except Exception as e:
        print_colored(f"✗ Error: {e}", Colors.RED)
        return None


def convert_to_islu(filepath: Path) -> None:
    """
    Convert language file to .islu format by setting LanguageCodePage=0.
    This ensures Unicode Inno Setup treats it as a UTF-8 file.
    """
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        
        # Replace LanguageCodePage=<any number> with LanguageCodePage=0
        content = re.sub(
            r'LanguageCodePage=\d+',
            'LanguageCodePage=0',
            content
        )
        
        # Write back as UTF-8 (without BOM for .islu)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print_colored(f"Warning: Failed to convert to .islu format: {e}", Colors.YELLOW)


def verify_language_file(filepath: Path) -> bool:
    """Verify that the file is a valid Inno Setup language file"""
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            
        # Check for required sections
        has_langoptions = '[LangOptions]' in content
        has_messages = '[Messages]' in content
        has_language_id = 'LanguageID=' in content
        
        return has_langoptions and has_messages and has_language_id
    except Exception:
        return False


def extract_language_info(filepath: Path) -> Optional[Dict[str, str]]:
    """Extract language metadata from the file"""
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            
        info = {}
        
        # Extract LanguageName
        if match := re.search(r'LanguageName=(.+)', content):
            info['name'] = match.group(1).strip()
            
        # Extract LanguageID
        if match := re.search(r'LanguageID=(.+)', content):
            info['id'] = match.group(1).strip()
            
        # Extract LanguageCodePage
        if match := re.search(r'LanguageCodePage=(.+)', content):
            info['codepage'] = match.group(1).strip()
            
        return info if info else None
    except Exception:
        return None


def list_available_languages():
    """List all available languages"""
    print_colored("\n=== Official Languages (Inno Setup Built-in) ===", Colors.HEADER)
    for i, lang in enumerate(sorted(OFFICIAL_LANGUAGES), 1):
        print(f"{i:2d}. {lang}")
    
    print_colored("\n=== Unofficial Languages (Community-Maintained) ===", Colors.HEADER)
    for i, lang in enumerate(sorted(UNOFFICIAL_LANGUAGES), 1):
        print(f"{i:2d}. {lang}")
    
    print_colored("\n💡 Usage Examples:", Colors.CYAN)
    print("  python download_inno_languages.py ChineseSimplified Japanese")
    print("  python download_inno_languages.py --all-unofficial")


def list_installed_languages():
    """List currently installed language packs"""
    if not LANGUAGES_DIR.exists():
        print_colored("No languages directory found.", Colors.YELLOW)
        return
    
    lang_files = list(LANGUAGES_DIR.glob("*.isl"))
    
    if not lang_files:
        print_colored("No language packs installed.", Colors.YELLOW)
        return
    
    print_colored("\n=== Installed Language Packs ===", Colors.HEADER)
    for filepath in sorted(lang_files):
        info = extract_language_info(filepath)
        size_kb = filepath.stat().st_size / 1024
        
        if info:
            print(f"  {filepath.name:<30} {info.get('name', 'Unknown'):<20} ({size_kb:.1f} KB)")
        else:
            print(f"  {filepath.name:<30} {'[Invalid file]':<20} ({size_kb:.1f} KB)")


def update_existing_languages():
    """Update all currently installed language packs"""
    if not LANGUAGES_DIR.exists():
        print_colored("No languages directory found.", Colors.YELLOW)
        return
    
    lang_files = list(LANGUAGES_DIR.glob("*.isl"))
    
    if not lang_files:
        print_colored("No language packs to update.", Colors.YELLOW)
        return
    
    print_colored("\n=== Updating Existing Language Packs ===", Colors.HEADER)
    
    updated = 0
    failed = 0
    
    for filepath in sorted(lang_files):
        lang_name = filepath.stem
        print(f"\nUpdating {lang_name}...")
        
        # Try unofficial first, then official
        success = False
        if lang_name in UNOFFICIAL_LANGUAGES:
            success = download_language(lang_name, is_unofficial=True) is not None
        elif lang_name in OFFICIAL_LANGUAGES:
            success = download_language(lang_name, is_unofficial=False) is not None
        else:
            print_colored(f"  ⚠ Unknown language: {lang_name}", Colors.YELLOW)
            failed += 1
            continue
        
        if success:
            updated += 1
        else:
            failed += 1
    
    print_colored(f"\n=== Update Summary ===", Colors.HEADER)
    print_colored(f"Updated: {updated}", Colors.GREEN)
    if failed > 0:
        print_colored(f"Failed: {failed}", Colors.RED)


def main():
    parser = argparse.ArgumentParser(
        description="Download Inno Setup language packs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download specific languages
  %(prog)s ChineseSimplified Japanese Korean
  
  # Download all unofficial languages
  %(prog)s --all-unofficial
  
  # List available languages
  %(prog)s --list
  
  # Show installed languages
  %(prog)s --installed
  
  # Update existing languages
  %(prog)s --update-existing
        """
    )
    
    parser.add_argument(
        'languages',
        nargs='*',
        help='Language names to download (e.g., ChineseSimplified, Japanese)'
    )
    
    parser.add_argument(
        '--all-unofficial',
        action='store_true',
        help='Download all unofficial (community-maintained) languages'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available languages'
    )
    
    parser.add_argument(
        '--installed',
        action='store_true',
        help='List currently installed language packs'
    )
    
    parser.add_argument(
        '--update-existing',
        action='store_true',
        help='Update all currently installed language packs'
    )
    
    args = parser.parse_args()
    
    # Show header
    print_colored("=" * 60, Colors.HEADER)
    print_colored("  Inno Setup Language Pack Downloader", Colors.HEADER + Colors.BOLD)
    print_colored("=" * 60, Colors.HEADER)
    
    # Handle different commands
    if args.list:
        list_available_languages()
        return 0
    
    if args.installed:
        list_installed_languages()
        return 0
    
    if args.update_existing:
        update_existing_languages()
        return 0
    
    # Download languages
    languages_to_download = []
    
    if args.all_unofficial:
        languages_to_download = [(lang, True) for lang in UNOFFICIAL_LANGUAGES]
    elif args.languages:
        for lang in args.languages:
            # Determine if official or unofficial
            is_unofficial = lang in UNOFFICIAL_LANGUAGES
            languages_to_download.append((lang, is_unofficial))
    else:
        parser.print_help()
        return 0
    
    if not languages_to_download:
        print_colored("\nNo languages specified.", Colors.YELLOW)
        print("\nUse --list to see available languages")
        return 1
    
    # Download each language
    print_colored(f"\nDownloading {len(languages_to_download)} language pack(s)...\n", Colors.CYAN)
    
    success_count = 0
    for lang, is_unofficial in languages_to_download:
        if download_language(lang, is_unofficial):
            success_count += 1
        print()  # Empty line between downloads
    
    # Summary
    print_colored("=" * 60, Colors.HEADER)
    if success_count == len(languages_to_download):
        print_colored(f"✓ Successfully downloaded all {success_count} language pack(s)", Colors.GREEN)
    else:
        failed = len(languages_to_download) - success_count
        print_colored(f"✓ Downloaded {success_count}/{len(languages_to_download)} language pack(s)", Colors.YELLOW)
        print_colored(f"✗ Failed: {failed}", Colors.RED)
    
    print_colored(f"\nLanguages directory: {LANGUAGES_DIR}", Colors.CYAN)
    
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
