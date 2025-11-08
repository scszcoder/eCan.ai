#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Internationalization Helper
Provides common language detection functionality for all GUI components
"""

import os
import sys
import json


def detect_language(default_lang='zh-CN', supported_languages=None):
    """
    Detect user's preferred language with priority order.
    
    Priority:
    1. uli.json language setting
    2. macOS system UI language (macOS only)
    3. System locale
    4. Default language
    
    Args:
        default_lang: Default language code if detection fails
        supported_languages: List of supported language codes to validate against
    
    Returns:
        str: Language code (e.g., 'zh-CN', 'en-US')
    """
    try:
        # Priority 1: Check uli.json for language setting
        try:
            # Get project root directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)  # up from utils/
            uli_path = os.path.join(project_root, 'uli.json')
            
            if os.path.exists(uli_path):
                with open(uli_path, 'r', encoding='utf-8') as f:
                    uli_data = json.load(f)
                    language = uli_data.get('language')
                    
                    # Validate if supported_languages is provided
                    if language:
                        if supported_languages is None or language in supported_languages:
                            return language
        except Exception:
            pass  # Continue to next detection method
        
        # Priority 2: macOS system UI language
        if sys.platform == 'darwin':
            try:
                import subprocess
                result = subprocess.run(
                    ['defaults', 'read', '-g', 'AppleLanguages'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    output = result.stdout.lower()
                    # Check for Chinese variants
                    if 'zh-hans' in output or 'zh-cn' in output or 'zh_cn' in output:
                        return 'zh-CN'
                    elif 'zh-hant' in output or 'zh-tw' in output or 'zh-hk' in output:
                        return 'zh-CN'  # Use simplified Chinese for traditional as well
                    elif 'en' in output:
                        return 'en-US'
            except Exception:
                pass  # Continue to next detection method
        
        # Priority 3: System locale
        try:
            import locale
            system_lang = locale.getdefaultlocale()[0]
            if system_lang:
                if 'zh' in system_lang.lower() or 'cn' in system_lang.lower():
                    return 'zh-CN'
                elif 'en' in system_lang.lower():
                    return 'en-US'
        except Exception:
            pass  # Continue to default
        
        # Priority 4: Default language
        return default_lang
        
    except Exception:
        return default_lang


def get_uli_language():
    """
    Get language setting from uli.json file only.
    
    Returns:
        str or None: Language code if found in uli.json, None otherwise
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        uli_path = os.path.join(project_root, 'uli.json')
        
        if os.path.exists(uli_path):
            with open(uli_path, 'r', encoding='utf-8') as f:
                uli_data = json.load(f)
                return uli_data.get('language')
    except Exception:
        pass
    return None


def update_uli_language(language):
    """
    Update language setting in uli.json file.
    
    Args:
        language: Language code to set (e.g., 'zh-CN', 'en-US')
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        uli_path = os.path.join(project_root, 'uli.json')
        
        # Read existing data
        if os.path.exists(uli_path):
            with open(uli_path, 'r', encoding='utf-8') as f:
                uli_data = json.load(f)
        else:
            uli_data = {}
        
        # Update language
        uli_data['language'] = language
        
        # Write back
        with open(uli_path, 'w', encoding='utf-8') as f:
            json.dump(uli_data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception:
        return False

