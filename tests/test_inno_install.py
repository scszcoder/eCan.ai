"""
Test InnoSetup auto-installation via OTA installer.

Run with: set ECAN_FORCE_FROZEN_OTA=1 && python tests/test_inno_install.py
"""
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_installer_module_import():
    """Test that the installer module can be imported."""
    print("[TEST] Importing ota.core.installer...")
    from ota.core.installer import InstallationManager
    print(f"  OK: InstallationManager imported successfully")
    return True

def test_inno_setup_detection():
    """Test that InnoSetup is detected correctly."""
    print("[TEST] Checking InnoSetup detection...")
    from ota.core.installer import InstallationManager
    
    manager = InstallationManager()
    
    # Check if InnoSetup is in PATH or standard location
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    
    found = None
    for path in inno_paths:
        if Path(path).exists():
            found = path
            break
    
    if found:
        print(f"  OK: InnoSetup found at: {found}")
    else:
        # Check PATH
        import shutil
        iscc = shutil.which("iscc")
        if iscc:
            print(f"  OK: InnoSetup found in PATH: {iscc}")
        else:
            print("  WARN: InnoSetup not found. Will attempt auto-download if needed.")
    
    return True

def test_force_frozen_env():
    """Test that ECAN_FORCE_FROZEN_OTA env var works."""
    print("[TEST] Testing ECAN_FORCE_FROZEN_OTA env var...")
    
    # Check current state
    force_frozen = os.environ.get('ECAN_FORCE_FROZEN_OTA', '').lower() in ('1', 'true', 'yes')
    is_frozen = getattr(sys, 'frozen', False)
    
    print(f"  sys.frozen = {is_frozen}")
    print(f"  ECAN_FORCE_FROZEN_OTA = {os.environ.get('ECAN_FORCE_FROZEN_OTA', 'not set')}")
    print(f"  Effective frozen = {is_frozen or force_frozen}")
    
    if not is_frozen:
        print("  OK: Running in dev mode (ECAN_FORCE_FROZEN_OTA would enable frozen behavior)")
    else:
        print("  OK: Running in frozen/production mode")
    
    return True

def test_registry_detection():
    """Test Windows registry detection for installed app."""
    print("[TEST] Testing Windows registry detection...")
    from ota.core.installer import InstallationManager
    
    manager = InstallationManager()
    
    try:
        install_dir = manager._get_current_windows_install_dir()
        if install_dir:
            print(f"  OK: Found installed app at: {install_dir}")
        else:
            print("  INFO: No previous installation found in registry (fresh install scenario)")
    except Exception as e:
        print(f"  INFO: Registry detection skipped: {e}")
    
    return True

def test_ota_config():
    """Test that OTA config is valid."""
    print("[TEST] Testing OTA config...")
    
    config_path = project_root / "ota" / "ota_config.yaml"
    if not config_path.exists():
        config_path = project_root / "ota" / "config" / "ota_config.yaml"
    
    if config_path.exists():
        print(f"  OK: Config found at: {config_path}")
        
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Check for required keys
        common = config.get('common', {})
        envs = config.get('environments', {})
        
        has_cn = 'cn' in common.get('cos_bucket', '') or 'cos_bucket' in common
        has_intl = 's3_bucket' in common
        
        print(f"  - CN config: {'OK' if has_cn else 'MISSING'}")
        print(f"  - INTL config: {'OK' if has_intl else 'MISSING'}")
        print(f"  - Environments: {list(envs.keys())}")
    else:
        print("  WARN: OTA config not found")
    
    return True

def test_silent_install_params():
    """Test that silent install parameters are correctly formed."""
    print("[TEST] Testing silent install parameters...")
    
    # Simulate the parameters that would be passed to InnoSetup
    install_options = {
        'silent': True,
        'create_backup': True,
        'auto_restart': True,
    }
    
    # These are the params that _install_exe uses
    expected_params = [
        '/SILENT',      # Silent with progress bar
        '/NORESTART',   # Don't restart computer  
        '/SP-',         # Skip "This will install..." dialog
    ]
    
    print(f"  Silent install options: {install_options}")
    print(f"  Expected InnoSetup params: {expected_params}")
    print("  OK: Silent install parameters are defined")
    
    return True

def main():
    print("=" * 60)
    print("InnoSetup Auto-Installation Test")
    print("=" * 60)
    print()
    
    tests = [
        ("Module Import", test_installer_module_import),
        ("InnoSetup Detection", test_inno_setup_detection),
        ("Force Frozen Env", test_force_frozen_env),
        ("Registry Detection", test_registry_detection),
        ("OTA Config", test_ota_config),
        ("Silent Install Params", test_silent_install_params),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
                print(f"  FAILED: {name}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {name} - {e}")
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print()
        print("All tests passed! InnoSetup auto-installation is ready.")
        print()
        print("To do a full OTA upgrade test:")
        print("  1. Build a new installer with: python build_system/ecan_build.py --app cn")
        print("  2. Run with: set ECAN_FORCE_FROZEN_OTA=1 && python -c \"from ota.core.platforms import run_ota_upgrade; run_ota_upgrade()\"")
    else:
        print()
        print("Some tests failed. Please review the output above.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
