#!/usr/bin/env python3
"""
Universal PyInstaller hook for symlink management
Handles symlink conflicts across all components (QtWebEngine, Playwright, etc.)
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Only apply enhanced symlink handling on macOS
if sys.platform == 'darwin':
    
    def filter_symlink_conflicts(data_list, component_name="UNKNOWN"):
        """Filter out problematic symlinks from data/binary lists"""
        filtered = []
        skipped = []
        
        for item in data_list:
            src_path = item[0] if isinstance(item, tuple) else item
            
            try:
                # Skip if source is a problematic symlink
                if os.path.islink(src_path):
                    target = os.readlink(src_path)
                    
                    # Skip absolute symlinks
                    if os.path.isabs(target):
                        skipped.append(src_path)
                        continue
                    
                    # Skip symlinks pointing outside their directory
                    if target.startswith('../'):
                        skipped.append(src_path)
                        continue
                    
                    # Skip known problematic patterns
                    problematic_patterns = [
                        'Versions/Current',
                        'Helpers',
                        'Resources',
                        'Frameworks'
                    ]
                    
                    if any(pattern in src_path for pattern in problematic_patterns):
                        # Check if target actually exists
                        src_dir = os.path.dirname(src_path)
                        target_path = os.path.join(src_dir, target)
                        if not os.path.exists(target_path):
                            skipped.append(src_path)
                            continue
                
                # Skip cache and temporary files
                skip_patterns = [
                    '/cache/',
                    '/tmp/',
                    '/temp/',
                    '/logs/',
                    'crashpad_database',
                    '.DS_Store'
                ]
                
                if any(pattern in src_path.lower() for pattern in skip_patterns):
                    skipped.append(src_path)
                    continue
                
                # Keep this item
                filtered.append(item)
                
            except Exception as e:
                print(f"[HOOK] Warning: Error processing {src_path}: {e}")
                # When in doubt, skip it
                skipped.append(src_path)
        
        if skipped:
            print(f"[HOOK] {component_name}: Filtered {len(skipped)} problematic items")
            if len(skipped) <= 10:  # Don't spam if too many
                for item in skipped:
                    print(f"[HOOK]   Skipped: {item}")
        
        return filtered
    
    def collect_safe_data_files(module_name):
        """Collect data files with symlink filtering"""
        try:
            raw_data = collect_data_files(module_name)
            return filter_symlink_conflicts(raw_data, module_name)
        except Exception as e:
            print(f"[HOOK] Warning: Failed to collect data for {module_name}: {e}")
            return []
    
    def collect_safe_dynamic_libs(module_name):
        """Collect dynamic libraries with symlink filtering"""
        try:
            raw_libs = collect_dynamic_libs(module_name)
            return filter_symlink_conflicts(raw_libs, module_name)
        except Exception as e:
            print(f"[HOOK] Warning: Failed to collect libraries for {module_name}: {e}")
            return []
    
    # Apply to common problematic modules
    problematic_modules = [
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets', 
        'PySide6.QtWebKit',
        'playwright'
    ]
    
    all_datas = []
    all_binaries = []
    
    for module in problematic_modules:
        try:
            # Try to import the module first
            __import__(module)
            
            print(f"[HOOK] Processing {module} with symlink safety")
            
            # Collect data files safely
            module_datas = collect_safe_data_files(module)
            all_datas.extend(module_datas)
            
            # Collect binaries safely  
            module_binaries = collect_safe_dynamic_libs(module)
            all_binaries.extend(module_binaries)
            
            print(f"[HOOK] {module}: {len(module_datas)} data files, {len(module_binaries)} binaries")
            
        except ImportError:
            print(f"[HOOK] Module {module} not available, skipping")
        except Exception as e:
            print(f"[HOOK] Error processing {module}: {e}")
    
    # Handle third-party Playwright browsers
    third_party_playwright = Path.cwd() / "third_party" / "ms-playwright"
    if third_party_playwright.exists():
        print(f"[HOOK] Found third-party Playwright: {third_party_playwright}")
        
        # Add the entire directory but filter problematic files
        try:
            for item in third_party_playwright.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    # Skip problematic files
                    skip_patterns = [
                        'cache',
                        'tmp',
                        'temp', 
                        'logs',
                        'crashpad_database',
                        '.DS_Store'
                    ]
                    
                    if not any(pattern in str(item).lower() for pattern in skip_patterns):
                        rel_path = item.relative_to(third_party_playwright.parent)
                        dest_path = f"third_party/{rel_path.parent}"
                        all_datas.append((str(item), dest_path))
            
            print(f"[HOOK] Added {len([d for d in all_datas if 'third_party' in d[1]])} third-party Playwright files")
            
        except Exception as e:
            print(f"[HOOK] Error processing third-party Playwright: {e}")
    
    # Set the hook variables
    datas = all_datas
    binaries = all_binaries
    
    print(f"[HOOK] Symlink Manager: Total {len(datas)} data files, {len(binaries)} binaries")

else:
    # Non-macOS platforms: use standard collection
    print("[HOOK] Non-macOS platform: using standard collection")
    
    try:
        datas = collect_data_files('PySide6.QtWebEngineCore')
        binaries = collect_dynamic_libs('PySide6.QtWebEngineCore')
    except Exception:
        datas = []
        binaries = []
    
    # Add third-party Playwright if exists
    third_party_playwright = Path.cwd() / "third_party" / "ms-playwright"
    if third_party_playwright.exists():
        datas.append((str(third_party_playwright), "third_party/ms-playwright"))

print(f"[HOOK] Symlink Manager Hook completed: {len(datas)} data files, {len(binaries)} binaries")
