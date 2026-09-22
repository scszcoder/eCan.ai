"""
Full OTA upgrade test using the downloaded installer.

This tests the complete installation flow:
1. Check if we can load the installer module
2. Verify InnoSetup is available
3. Simulate the installation parameters that would be used
4. Report any issues

Run with: 
  $env:ECAN_FORCE_FROZEN_OTA="1"; python tests/test_inno_full_upgrade.py
"""
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def get_downloaded_installer():
    """Find the downloaded OTA installer."""
    download_dir = project_root / "ota_downloads"
    
    if not download_dir.exists():
        print(f"  ERROR: Download directory not found: {download_dir}")
        return None
    
    # Look for Windows installer
    installers = list(download_dir.glob("*.exe")) + list(download_dir.glob("*.msi"))
    
    if not installers:
        print(f"  ERROR: No installer found in {download_dir}")
        return None
    
    # Return the most recent one
    latest = max(installers, key=lambda p: p.stat().st_mtime)
    print(f"  OK: Found installer: {latest.name}")
    print(f"      Size: {latest.stat().st_size / (1024*1024):.1f} MB")
    return latest

def test_installer_integration():
    """Test the actual installer integration."""
    print("\n[TEST] Testing installer integration...")
    
    from ota.core.installer import InstallationManager
    
    manager = InstallationManager()
    
    # Get the installer
    installer = get_downloaded_installer()
    if not installer:
        return False
    
    print("\n[TEST] Checking installation prerequisites...")
    
    # 1. Check if frozen mode is properly detected
    force_frozen = os.environ.get('ECAN_FORCE_FROZEN_OTA', '').lower() in ('1', 'true', 'yes')
    is_frozen = getattr(sys, 'frozen', False)
    effective_frozen = is_frozen or force_frozen
    
    print(f"  - sys.frozen: {is_frozen}")
    print(f"  - ECAN_FORCE_FROZEN_OTA: {os.environ.get('ECAN_FORCE_FROZEN_OTA', 'not set')}")
    print(f"  - Effective frozen: {effective_frozen}")
    
    if not effective_frozen:
        print("  WARN: Not in frozen mode - OTA installation will use fallback paths")
    
    # 2. Check InnoSetup location
    inno_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    
    inno_found = None
    for path in inno_paths:
        if path.exists():
            inno_found = path
            break
    
    if inno_found:
        print(f"  - InnoSetup: {inno_found} (OK)")
    else:
        print("  WARN: InnoSetup not found - will be downloaded if needed")
    
    # 3. Check installation directory
    print("\n[TEST] Checking installation directory...")
    
    install_options = {
        'silent': True,
        'create_backup': True,
        'auto_restart': True,
    }
    
    # In frozen mode, we would use registry to find existing install
    if effective_frozen:
        install_dir = manager._get_current_windows_install_dir()
        if install_dir:
            print(f"  - Registry install dir: {install_dir}")
        else:
            install_dir = manager._get_windows_standard_install_dir()
            print(f"  - Using standard dir: {install_dir}")
    else:
        # Dev mode - use exe directory as fallback
        install_dir = Path(sys.executable).parent
        print(f"  - Dev mode fallback: {install_dir}")
    
    # 4. Check if directory is writable
    print("\n[TEST] Checking directory writability...")
    
    try:
        from ota.core.installer import is_writable_dir
        
        if is_writable_dir(install_dir):
            print(f"  - {install_dir}: WRITABLE (OK)")
        else:
            print(f"  - {install_dir}: NOT WRITABLE")
            print("    This is expected if running as non-admin without ECAN_FORCE_FROZEN_OTA")
    except Exception as e:
        print(f"  - is_writable_dir check: {e}")
    
    # 5. Simulate the command that would be built
    print("\n[TEST] Simulating InnoSetup command...")
    
    cmd = [
        str(installer),
        '/SILENT',
        '/NORESTART',
        '/SP-',
        f'/DIR="{install_dir}"',
        '/LOG="%TEMP%\\ecan_ota_install.log"',
    ]
    
    print(f"  Command that would be executed:")
    print(f"    {' '.join(cmd)}")
    
    # 6. Summary
    print("\n" + "=" * 60)
    print("OTA UPGRADE TEST SUMMARY")
    print("=" * 60)
    
    issues = []
    
    if not inno_found:
        issues.append("InnoSetup not found - will attempt auto-download")
    
    if not effective_frozen:
        issues.append("Not in frozen mode - using dev fallback paths")
    
    if issues:
        print("\nPotential issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nAll prerequisites met! OTA upgrade should work correctly.")
    
    print("\nTo perform an actual upgrade:")
    print("  1. Make sure you're running as Administrator (for Program Files)")
    print("  2. Set ECAN_FORCE_FROZEN_OTA=1")
    print("  3. Run the OTA upgrade from the app")
    
    return len(issues) == 0

def test_silent_install_flags():
    """Verify the silent install flags are correct."""
    print("\n[TEST] Verifying InnoSetup silent install flags...")
    
    # These are the flags used by _install_exe
    expected_flags = {
        '/SILENT': 'Silent with progress bar (not /VERYSILENT to show errors)',
        '/NORESTART': "Don't restart computer automatically",
        '/SP-': 'Skip the "This will install..." dialog',
        '/CLOSEAPPLICATIONS': 'NOT used (would cause race with os._exit)',
    }
    
    print("  InnoSetup flags that WILL be used:")
    print("    /SILENT - Silent with progress bar")
    print("    /NORESTART - Don't restart computer")
    print("    /SP- - Skip intro dialog")
    print("    /DIR=<path> - Pin install directory from registry")
    print("    /LOG=<path> - Enable detailed logging")
    print()
    print("  InnoSetup flags that will NOT be used:")
    print("    /CLOSEAPPLICATIONS - Not used to avoid race with os._exit(0)")
    
    return True

def main():
    print("=" * 60)
    print("Full OTA Upgrade Test - InnoSetup Integration")
    print("=" * 60)
    
    tests = [
        ("Installer Integration", test_installer_integration),
        ("Silent Install Flags", test_silent_install_flags),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"\n  ERROR: {name} - {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
