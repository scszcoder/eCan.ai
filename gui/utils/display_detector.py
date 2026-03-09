"""
Linux Display Server Detection
Detects X11, Wayland, or headless environment
"""

import os
import subprocess
import shutil
from typing import Literal, Optional, Tuple, Dict

DisplayServer = Literal['x11', 'wayland', 'headless']


def detect_display_server() -> DisplayServer:
    """
    Detect which display server is running
    
    Returns:
        'x11': X11 display server
        'wayland': Wayland display server
        'headless': No display server (server mode)
    """
    
    # Check for Wayland
    if os.environ.get('WAYLAND_DISPLAY'):
        return 'wayland'
    
    # Check for X11
    if os.environ.get('DISPLAY'):
        # Verify X server is actually running
        if shutil.which('xset'):
            try:
                subprocess.run(
                    ['xset', 'q'],
                    capture_output=True,
                    check=True,
                    timeout=1
                )
                return 'x11'
            except:
                pass
    
    return 'headless'


def is_gui_available() -> bool:
    """Check if GUI is available"""
    return detect_display_server() != 'headless'


def get_display_info() -> Dict[str, Optional[str]]:
    """Get detailed display information"""
    server = detect_display_server()
    
    info = {
        'server': server,
        'display': os.environ.get('DISPLAY'),
        'wayland_display': os.environ.get('WAYLAND_DISPLAY'),
        'session_type': os.environ.get('XDG_SESSION_TYPE'),
        'desktop': os.environ.get('XDG_CURRENT_DESKTOP'),
    }
    
    if server == 'x11':
        # Get screen resolution
        try:
            result = subprocess.run(
                ['xrandr'],
                capture_output=True,
                text=True,
                timeout=2
            )
            # Parse primary screen resolution
            import re
            match = re.search(r'(\d+)x(\d+).*\*', result.stdout)
            if match:
                info['resolution'] = f"{match.group(1)}x{match.group(2)}"
        except:
            pass
    
    return info


def check_pyside6_compatibility() -> Tuple[bool, str]:
    """
    Check if PySide6 can run on this system
    
    Returns:
        (can_run, message)
    """
    server = detect_display_server()
    
    if server == 'headless':
        return False, "No display server detected. GUI applications cannot run."
    
    # Check for required libraries (basic check)
    required_libs = [
        'libGL.so.1',
        'libglib-2.0.so.0',
        'libxkbcommon-x11.so.0'
    ]
    
    missing = []
    try:
        result = subprocess.run(
            ['ldconfig', '-p'],
            capture_output=True,
            text=True,
            timeout=2
        )
        ldconfig_output = result.stdout
        
        for lib in required_libs:
            if lib not in ldconfig_output:
                missing.append(lib)
    except:
        # If ldconfig fails, assume libraries are present
        pass
    
    if missing:
        return False, f"Missing required libraries: {', '.join(missing)}"
    
    if server == 'wayland':
        return True, "Wayland detected. PySide6 should work with XWayland."
    
    return True, f"{server.upper()} detected. PySide6 compatible."


def get_desktop_environment() -> Optional[str]:
    """
    Detect the desktop environment
    
    Returns:
        Desktop environment name or None
    """
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    
    if 'gnome' in desktop:
        return 'GNOME'
    elif 'kde' in desktop or 'plasma' in desktop:
        return 'KDE'
    elif 'xfce' in desktop:
        return 'XFCE'
    elif 'lxde' in desktop:
        return 'LXDE'
    elif 'mate' in desktop:
        return 'MATE'
    elif 'cinnamon' in desktop:
        return 'Cinnamon'
    elif desktop:
        return desktop.upper()
    
    return None


def print_display_info():
    """Print display information for debugging"""
    info = get_display_info()
    desktop = get_desktop_environment()
    can_run, message = check_pyside6_compatibility()
    
    print("=" * 60)
    print("Linux Display Information")
    print("=" * 60)
    print(f"Display Server: {info['server']}")
    print(f"Desktop Environment: {desktop or 'Unknown'}")
    print(f"DISPLAY: {info['display'] or 'Not set'}")
    print(f"WAYLAND_DISPLAY: {info['wayland_display'] or 'Not set'}")
    print(f"Session Type: {info['session_type'] or 'Unknown'}")
    if 'resolution' in info:
        print(f"Resolution: {info['resolution']}")
    print()
    print(f"PySide6 Compatible: {'Yes' if can_run else 'No'}")
    print(f"Message: {message}")
    print("=" * 60)


if __name__ == '__main__':
    print_display_info()
