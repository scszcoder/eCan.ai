"""
Linux System Permissions and Dependencies Checker
"""

import os
import subprocess
import shutil
from typing import Dict, List, Optional


def check_screenshot_permissions() -> Dict[str, bool]:
    """Check if screenshot tools are available"""
    tools = {
        'scrot': bool(shutil.which('scrot')),
        'gnome-screenshot': bool(shutil.which('gnome-screenshot')),
        'imagemagick': bool(shutil.which('import')),
        'xdotool': bool(shutil.which('xdotool')),
        'xwininfo': bool(shutil.which('xwininfo')),
    }
    return tools


def check_printing_permissions() -> Dict[str, any]:
    """Check CUPS printing system"""
    result = {
        'cups_installed': bool(shutil.which('lp')),
        'lpstat_available': bool(shutil.which('lpstat')),
        'printers': []
    }
    
    if result['lpstat_available']:
        try:
            output = subprocess.check_output(
                ['lpstat', '-p'],
                text=True,
                timeout=2,
                stderr=subprocess.DEVNULL
            )
            # Parse printer list
            for line in output.strip().split('\n'):
                if line.startswith('printer'):
                    parts = line.split()
                    if len(parts) >= 2:
                        result['printers'].append(parts[1])
        except:
            pass
    
    return result


def check_window_manager_tools() -> Dict[str, bool]:
    """Check window management tools"""
    return {
        'wmctrl': bool(shutil.which('wmctrl')),
        'xdotool': bool(shutil.which('xdotool')),
        'xwininfo': bool(shutil.which('xwininfo')),
        'xprop': bool(shutil.which('xprop')),
        'xrandr': bool(shutil.which('xrandr')),
    }


def check_file_manager_tools() -> Dict[str, bool]:
    """Check file manager and file operation tools"""
    return {
        'xdg-open': bool(shutil.which('xdg-open')),
        'nautilus': bool(shutil.which('nautilus')),
        'dolphin': bool(shutil.which('dolphin')),
        'thunar': bool(shutil.which('thunar')),
        'pcmanfm': bool(shutil.which('pcmanfm')),
        'caja': bool(shutil.which('caja')),
        'nemo': bool(shutil.which('nemo')),
    }


def get_missing_dependencies() -> List[str]:
    """Get list of missing system dependencies"""
    missing = []
    
    # Screenshot tools (at least one required)
    screenshot_tools = check_screenshot_permissions()
    if not any([screenshot_tools['scrot'], screenshot_tools['gnome-screenshot'], screenshot_tools['imagemagick']]):
        missing.append('screenshot tool (scrot, gnome-screenshot, or imagemagick)')
    
    # Printing
    printing = check_printing_permissions()
    if not printing['cups_installed']:
        missing.append('cups (printing system)')
    
    # Window management (at least wmctrl or xdotool)
    wm_tools = check_window_manager_tools()
    if not any([wm_tools['wmctrl'], wm_tools['xdotool']]):
        missing.append('window management tool (wmctrl or xdotool)')
    
    # File operations
    file_tools = check_file_manager_tools()
    if not file_tools['xdg-open']:
        missing.append('xdg-utils (file operations)')
    
    return missing


def get_installation_commands() -> Dict[str, str]:
    """Get installation commands for different distributions"""
    missing = get_missing_dependencies()
    
    if not missing:
        return {}
    
    commands = {}
    
    # Ubuntu/Debian packages
    ubuntu_packages = []
    if 'screenshot' in str(missing):
        ubuntu_packages.append('scrot')
    if 'cups' in str(missing):
        ubuntu_packages.append('cups')
    if 'window management' in str(missing):
        ubuntu_packages.append('wmctrl')
        ubuntu_packages.append('xdotool')
    if 'xdg-utils' in str(missing):
        ubuntu_packages.append('xdg-utils')
    
    if ubuntu_packages:
        commands['ubuntu'] = f"sudo apt install -y {' '.join(ubuntu_packages)}"
    
    # Fedora/RHEL packages
    fedora_packages = []
    if 'screenshot' in str(missing):
        fedora_packages.append('scrot')
    if 'cups' in str(missing):
        fedora_packages.append('cups')
    if 'window management' in str(missing):
        fedora_packages.append('wmctrl')
        fedora_packages.append('xdotool')
    if 'xdg-utils' in str(missing):
        fedora_packages.append('xdg-utils')
    
    if fedora_packages:
        commands['fedora'] = f"sudo dnf install -y {' '.join(fedora_packages)}"
    
    # Arch Linux packages
    arch_packages = []
    if 'screenshot' in str(missing):
        arch_packages.append('scrot')
    if 'cups' in str(missing):
        arch_packages.append('cups')
    if 'window management' in str(missing):
        arch_packages.append('wmctrl')
        arch_packages.append('xdotool')
    if 'xdg-utils' in str(missing):
        arch_packages.append('xdg-utils')
    
    if arch_packages:
        commands['arch'] = f"sudo pacman -S {' '.join(arch_packages)}"
    
    return commands


def print_system_requirements():
    """Print installation commands for missing dependencies"""
    missing = get_missing_dependencies()
    
    if not missing:
        print("✅ All system dependencies are installed")
        return
    
    print("=" * 60)
    print("⚠️  Missing System Dependencies")
    print("=" * 60)
    print()
    
    for item in missing:
        print(f"  ❌ {item}")
    
    print()
    print("Installation Commands:")
    print("-" * 60)
    
    commands = get_installation_commands()
    
    if 'ubuntu' in commands:
        print()
        print("Ubuntu/Debian:")
        print(f"  {commands['ubuntu']}")
    
    if 'fedora' in commands:
        print()
        print("Fedora/RHEL:")
        print(f"  {commands['fedora']}")
    
    if 'arch' in commands:
        print()
        print("Arch Linux:")
        print(f"  {commands['arch']}")
    
    print()
    print("=" * 60)


def check_all_permissions() -> Dict[str, any]:
    """Check all system permissions and tools"""
    return {
        'screenshot': check_screenshot_permissions(),
        'printing': check_printing_permissions(),
        'window_manager': check_window_manager_tools(),
        'file_manager': check_file_manager_tools(),
        'missing': get_missing_dependencies(),
    }


def print_full_report():
    """Print full system capabilities report"""
    permissions = check_all_permissions()
    
    print("=" * 60)
    print("Linux System Capabilities Report")
    print("=" * 60)
    
    # Screenshot tools
    print()
    print("📸 Screenshot Tools:")
    for tool, available in permissions['screenshot'].items():
        status = "✅" if available else "❌"
        print(f"  {status} {tool}")
    
    # Printing
    print()
    print("🖨️  Printing System:")
    printing = permissions['printing']
    print(f"  {'✅' if printing['cups_installed'] else '❌'} CUPS installed")
    print(f"  {'✅' if printing['lpstat_available'] else '❌'} lpstat available")
    if printing['printers']:
        print(f"  📋 Printers: {', '.join(printing['printers'])}")
    else:
        print(f"  ⚠️  No printers configured")
    
    # Window management
    print()
    print("🪟 Window Management Tools:")
    for tool, available in permissions['window_manager'].items():
        status = "✅" if available else "❌"
        print(f"  {status} {tool}")
    
    # File managers
    print()
    print("📁 File Manager Tools:")
    for tool, available in permissions['file_manager'].items():
        status = "✅" if available else "❌"
        print(f"  {status} {tool}")
    
    # Missing dependencies
    print()
    if permissions['missing']:
        print("⚠️  Missing Dependencies:")
        for item in permissions['missing']:
            print(f"  ❌ {item}")
        
        print()
        commands = get_installation_commands()
        if commands:
            print("Installation Commands:")
            for distro, cmd in commands.items():
                print(f"  {distro.capitalize()}: {cmd}")
    else:
        print("✅ All dependencies satisfied")
    
    print()
    print("=" * 60)


if __name__ == '__main__':
    print_full_report()
