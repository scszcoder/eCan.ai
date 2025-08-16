#!/usr/bin/env python3
"""
PyInstaller hook for PySide6.QtWebEngineCore on macOS
Handles framework symlink conflicts and ensures proper bundling
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Only apply this hook on macOS
if sys.platform == 'darwin':
    
    def get_qtwebengine_data():
        """Get QtWebEngine data files with symlink conflict resolution"""
        datas = []
        binaries = []
        
        try:
            # Find PySide6 installation
            import PySide6
            pyside6_path = Path(PySide6.__file__).parent
            qt_lib_path = pyside6_path / "Qt" / "lib"
            
            # Handle QtWebEngineCore.framework
            framework_path = qt_lib_path / "QtWebEngineCore.framework"
            if framework_path.exists():
                
                # Handle QtWebEngineProcess.app
                webengine_app_candidates = [
                    framework_path / "Helpers" / "QtWebEngineProcess.app",
                    framework_path / "Versions" / "Current" / "Helpers" / "QtWebEngineProcess.app"
                ]
                
                for app_path in webengine_app_candidates:
                    if app_path.exists() and not app_path.is_symlink():
                        # Add the entire app bundle
                        dest_path = "PySide6/Qt/lib/QtWebEngineCore.framework/Helpers"
                        datas.append((str(app_path), dest_path))
                        print(f"[HOOK] Added QtWebEngineProcess.app: {app_path}")
                        break
                
                # Handle Resources directory
                resources_candidates = [
                    framework_path / "Resources",
                    framework_path / "Versions" / "Current" / "Resources"
                ]
                
                for res_path in resources_candidates:
                    if res_path.exists() and not res_path.is_symlink():
                        dest_path = "PySide6/Qt/lib/QtWebEngineCore.framework"
                        datas.append((str(res_path), dest_path))
                        print(f"[HOOK] Added QtWebEngine Resources: {res_path}")
                        break
                
                # Handle framework binary (avoid symlinks)
                framework_binary_candidates = [
                    framework_path / "QtWebEngineCore",
                    framework_path / "Versions" / "Current" / "QtWebEngineCore"
                ]
                
                for bin_path in framework_binary_candidates:
                    if bin_path.exists() and not bin_path.is_symlink():
                        dest_path = "PySide6/Qt/lib/QtWebEngineCore.framework"
                        binaries.append((str(bin_path), dest_path))
                        print(f"[HOOK] Added QtWebEngineCore binary: {bin_path}")
                        break
                
                # Handle Info.plist and other essential files
                essential_files = [
                    "Info.plist",
                    "Resources/Info.plist"
                ]
                
                for file_name in essential_files:
                    file_candidates = [
                        framework_path / file_name,
                        framework_path / "Versions" / "Current" / file_name
                    ]
                    
                    for file_path in file_candidates:
                        if file_path.exists() and not file_path.is_symlink():
                            dest_path = f"PySide6/Qt/lib/QtWebEngineCore.framework/{file_name}"
                            datas.append((str(file_path), os.path.dirname(dest_path)))
                            print(f"[HOOK] Added essential file: {file_path}")
                            break
        
        except Exception as e:
            print(f"[HOOK] Warning: QtWebEngine hook failed: {e}")
        
        return datas, binaries
    
    # Get the data and binaries
    hook_datas, hook_binaries = get_qtwebengine_data()
    
    # Add to PyInstaller collections
    datas = hook_datas
    binaries = hook_binaries
    
    # Also collect standard data files (excluding problematic symlinks)
    try:
        standard_datas = collect_data_files('PySide6.QtWebEngineCore')
        # Filter out symlinks to avoid conflicts
        filtered_datas = []
        for src, dst in standard_datas:
            if not os.path.islink(src):
                filtered_datas.append((src, dst))
            else:
                print(f"[HOOK] Skipped symlink: {src}")
        
        datas.extend(filtered_datas)
    except Exception as e:
        print(f"[HOOK] Warning: Standard data collection failed: {e}")
    
    # Collect dynamic libraries (excluding problematic ones)
    try:
        standard_binaries = collect_dynamic_libs('PySide6.QtWebEngineCore')
        # Filter out symlinks and problematic binaries
        filtered_binaries = []
        for src, dst in standard_binaries:
            if not os.path.islink(src) and 'Versions/Current' not in src:
                filtered_binaries.append((src, dst))
            else:
                print(f"[HOOK] Skipped problematic binary: {src}")
        
        binaries.extend(filtered_binaries)
    except Exception as e:
        print(f"[HOOK] Warning: Standard binary collection failed: {e}")

else:
    # Non-macOS platforms use standard collection
    datas = collect_data_files('PySide6.QtWebEngineCore')
    binaries = collect_dynamic_libs('PySide6.QtWebEngineCore')

print(f"[HOOK] PySide6.QtWebEngineCore: {len(datas)} data files, {len(binaries)} binaries")
