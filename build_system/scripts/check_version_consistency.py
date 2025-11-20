#!/usr/bin/env python3
"""
Check version consistency

Ensure version numbers in VERSION file and build_info.py are consistent
"""

import sys
from pathlib import Path

# Project root directory
project_root = Path(__file__).parent.parent.parent


def check_consistency() -> bool:
    """
    Check if VERSION file and build_info.py are consistent
    
    Returns:
        True if consistent, False otherwise
    """
    print("=" * 60)
    print("Checking Version Consistency")
    print("=" * 60)
    
    # 1. Check VERSION file
    version_file = project_root / 'VERSION'
    if not version_file.exists():
        print("❌ VERSION file not found")
        print(f"   Expected location: {version_file}")
        return False
    
    file_version = version_file.read_text().strip()
    print(f"📄 VERSION file: {file_version}")
    
    # 2. Check build_data.py (generated file)
    build_data_file = project_root / 'config' / 'build_data.py'
    if not build_data_file.exists():
        print("⚠️  build_data.py not found (will use fallback in development)")
        print(f"   Expected location: {build_data_file}")
        print("   To generate: python3 build_system/scripts/inject_build_info.py --environment <env>")
        print()
        print("Note: config/build_info.py will use fallback data for local development")
        return True  # Not an error - fallback is acceptable
    
    # 3. Import build_info (which loads from build_data.py)
    try:
        sys.path.insert(0, str(project_root))
        from config.build_info import VERSION as build_version, ENVIRONMENT, IS_FALLBACK
        
        if IS_FALLBACK:
            print(f"⚠️  Using fallback data (build_data.py not found)")
            print(f"   Version: {build_version} ({ENVIRONMENT})")
            return True  # Fallback is acceptable
        
        print(f"🔧 build_data.py: {build_version} ({ENVIRONMENT})")
        
        # 4. Compare versions
        if file_version != build_version:
            print()
            print("❌ Version Mismatch!")
            print(f"   VERSION file:   {file_version}")
            print(f"   build_info.py:  {build_version}")
            print()
            print("Fix:")
            print("   Run: python3 build_system/scripts/inject_build_info.py --environment <env>")
            return False
        
        print()
        print("✅ Versions are consistent!")
        print(f"   Both sources report: {file_version}")
        print("=" * 60)
        return True
        
    except ImportError as e:
        print(f"❌ Error importing build_info: {e}")
        print("   Please run: python3 build_system/scripts/inject_build_info.py")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    """Main entry point"""
    success = check_consistency()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
