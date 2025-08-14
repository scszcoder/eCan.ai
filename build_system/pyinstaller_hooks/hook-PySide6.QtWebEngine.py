# -*- coding: utf-8 -*-
"""
PyInstaller hook for PySide6.QtWebEngine
Ensures QtWebEngineProcess and related binaries are properly collected
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from PyInstaller.utils.hooks import get_module_file_attribute
import os
from pathlib import Path

# Collect all QtWebEngine submodules
hiddenimports = collect_submodules('PySide6.QtWebEngine')

# Collect data files
datas = collect_data_files('PySide6.QtWebEngine')

# Collect dynamic libraries
binaries = collect_dynamic_libs('PySide6.QtWebEngine')

# Special handling for QtWebEngineProcess on macOS
def _collect_qtwebengine_process():
    """Collect QtWebEngineProcess binary and related files"""
    try:
        import PySide6
        pyside6_path = Path(PySide6.__file__).parent
        
        # Look for QtWebEngineProcess in the PySide6 installation
        qtwebengine_process = None
        
        # Common paths where QtWebEngineProcess might be located
        search_paths = [
            pyside6_path / "Qt" / "lib" / "QtWebEngineCore.framework" / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess",
            pyside6_path / "Qt" / "lib" / "QtWebEngineCore.framework" / "Versions" / "Current" / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess",
            pyside6_path / "Qt" / "bin" / "QtWebEngineProcess",
            pyside6_path / "QtWebEngineProcess",
        ]
        
        for path in search_paths:
            if path.exists() and path.is_file():
                qtwebengine_process = path
                break
        
        if qtwebengine_process:
            # Add QtWebEngineProcess binary
            binaries.append((str(qtwebengine_process), 'QtWebEngineProcess'))
            
            # If it's a .app bundle on macOS, collect the entire bundle
            if qtwebengine_process.suffix == '.app' or '.app' in str(qtwebengine_process):
                app_bundle = qtwebengine_process.parent.parent.parent.parent  # Go up to .app
                if app_bundle.exists() and app_bundle.is_dir():
                    # Collect the entire QtWebEngineProcess.app bundle
                    for root, dirs, files in os.walk(str(app_bundle)):
                        for file in files:
                            file_path = Path(root) / file
                            rel_path = file_path.relative_to(app_bundle.parent)
                            dest_path = f"QtWebEngineProcess.app/{rel_path}"
                            binaries.append((str(file_path), dest_path))
            
            print(f"[HOOK] Collected QtWebEngineProcess: {qtwebengine_process}")
        else:
            print("[HOOK] Warning: QtWebEngineProcess not found in PySide6 installation")
            
    except Exception as e:
        print(f"[HOOK] Error collecting QtWebEngineProcess: {e}")

# Collect QtWebEngineProcess
_collect_qtwebengine_process()

# Additional hidden imports that might be needed
hiddenimports.extend([
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngine',
    'PySide6.QtWebChannel',
    'PySide6.QtWebSockets',
    'PySide6.QtWebView',
])

print(f"[HOOK] PySide6.QtWebEngine hook: {len(hiddenimports)} hidden imports, {len(datas)} data files, {len(binaries)} binaries")
