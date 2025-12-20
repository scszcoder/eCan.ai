#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Info.plist Template Processor
Processes Info.plist template with dynamic configuration values
"""

import os
import json
import plistlib
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from utils.logger_helper import logger_helper as logger


class InfoPlistTemplateProcessor:
    """Process Info.plist template with dynamic configuration"""
    
    def __init__(self, project_root: Path, config: Dict[str, Any]):
        self.project_root = project_root
        self.config = config
        self.template_path = project_root / 'resource' / 'Info.plist'
        
    def process_template(self, app_name: str, app_version: str, mode: str = "prod") -> str:
        """
        Process Info.plist template with dynamic values
        
        Args:
            app_name: Application name
            app_version: Application version
            mode: Build mode (prod, dev, etc.)
            
        Returns:
            Path to processed Info.plist file
        """
        try:
            # Load template
            if not self.template_path.exists():
                logger.error(f"Info.plist template not found: {self.template_path}")
                return self._create_fallback_plist(app_name, app_version)
            
            with open(self.template_path, 'rb') as f:
                template_data = plistlib.load(f)
            
            # Apply dynamic configuration
            processed_data = self._apply_dynamic_config(template_data, app_name, app_version, mode)
            
            # Create temporary processed file
            temp_dir = self.project_root / 'build' / 'temp'
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            processed_path = temp_dir / f'Info_{mode}.plist'
            
            with open(processed_path, 'wb') as f:
                plistlib.dump(processed_data, f)
            
            logger.info(f"Processed Info.plist template: {processed_path}")
            return str(processed_path)
            
        except Exception as e:
            logger.error(f"Failed to process Info.plist template: {e}")
            return self._create_fallback_plist(app_name, app_version)
    
    def _apply_dynamic_config(self, template_data: Dict[str, Any], app_name: str, app_version: str, mode: str) -> Dict[str, Any]:
        """Apply dynamic configuration to template data"""
        
        # Get configuration values
        app_config = self.config.get('app', {})
        installer_config = self.config.get('installer', {}).get('macos', {})
        
        # Basic app information
        template_data['CFBundleName'] = app_name
        template_data['CFBundleDisplayName'] = app_name
        template_data['CFBundleVersion'] = app_version
        template_data['CFBundleShortVersionString'] = app_version
        template_data['CFBundleExecutable'] = app_name
        
        # Bundle identifier
        bundle_id = installer_config.get('bundle_identifier', 'com.ecan.app')
        template_data['CFBundleIdentifier'] = bundle_id
        
        # Copyright
        copyright_text = installer_config.get('copyright', f'Copyright © 2025 {app_config.get("author", "eCan.AI Team")}')
        template_data['NSHumanReadableCopyright'] = copyright_text
        
        # Minimum OS version
        min_os_version = installer_config.get('min_os_version', '11.0')
        template_data['LSMinimumSystemVersion'] = min_os_version
        
        # Update usage descriptions with app name
        usage_descriptions = {
            'NSMicrophoneUsageDescription': f'{app_name} needs microphone access for voice features',
            'NSCameraUsageDescription': f'{app_name} needs camera access for visual features',
            'NSNetworkVolumesUsageDescription': f'{app_name} needs network access for automation',
            'NSAppleEventsUsageDescription': f'{app_name} needs AppleEvents access for system automation',
            'NSSystemAdministrationUsageDescription': f'{app_name} needs admin access for system automation',
            'NSApplicationSupportDirectoryUsageDescription': f'{app_name} needs access to Application Support directory to store user data and settings.',
            'NSDocumentsFolderUsageDescription': f'{app_name} needs access to Documents folder for file operations.',
            'NSDesktopFolderUsageDescription': f'{app_name} needs access to Desktop folder for file operations.',
            'NSDownloadsFolderUsageDescription': f'{app_name} needs access to Downloads folder for file operations.',
            'NSScreenCaptureUsageDescription': f'{app_name} needs screen recording permission for automation tasks.',
            'NSAccessibilityUsageDescription': f'{app_name} needs accessibility permission for automation tasks.'
        }
        
        # Apply usage descriptions
        for key, description in usage_descriptions.items():
            template_data[key] = description
        
        # Build CFBundleURLTypes from config
        url_schemes = installer_config.get('url_schemes', [])
        if url_schemes:
            url_types = []
            for scheme_config in url_schemes:
                url_type = {
                    'CFBundleURLName': scheme_config.get('name', f"{scheme_config['scheme']} URL"),
                    'CFBundleURLSchemes': [scheme_config['scheme']],
                }
                if 'role' in scheme_config:
                    url_type['CFBundleTypeRole'] = scheme_config['role']
                if 'icon' in scheme_config:
                    url_type['CFBundleURLIconFile'] = scheme_config['icon']
                url_types.append(url_type)
            template_data['CFBundleURLTypes'] = url_types
        elif 'CFBundleURLTypes' not in template_data:
            # Add default ecan:// scheme if not in template and not in config
            template_data['CFBundleURLTypes'] = [{
                'CFBundleURLName': 'eCan URL',
                'CFBundleURLSchemes': ['ecan'],
                'CFBundleTypeRole': 'Viewer'
            }]
        
        # Mode-specific configurations
        if mode == 'dev':
            template_data['CFBundleDisplayName'] = f'{app_name} (Dev)'
            # Add development-specific settings if needed
        
        return template_data
    
    def _create_fallback_plist(self, app_name: str, app_version: str) -> str:
        """Create fallback Info.plist if template is missing"""
        logger.warning("Creating fallback Info.plist")
        
        app_config = self.config.get('app', {})
        installer_config = self.config.get('installer', {}).get('macos', {})
        bundle_id = installer_config.get('bundle_identifier', 'com.ecan.app')
        
        fallback_data = {
            'CFBundleName': app_name,
            'CFBundleDisplayName': app_name,
            'CFBundleVersion': app_version,
            'CFBundleShortVersionString': app_version,
            'CFBundleExecutable': app_name,
            'CFBundleIdentifier': bundle_id,
            'CFBundlePackageType': 'APPL',
            'CFBundleSignature': '????',
            'CFBundleInfoDictionaryVersion': '6.0',
            'LSApplicationCategoryType': 'public.app-category.productivity',
            'LSMinimumSystemVersion': installer_config.get('min_os_version', '11.0'),
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
            'NSSupportsAutomaticGraphicsSwitching': True,
            'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
            'NSApplicationSupportDirectoryUsageDescription': f'{app_name} needs access to Application Support directory to store user data and settings.',
            'NSDocumentsFolderUsageDescription': f'{app_name} needs access to Documents folder for file operations.',
            'NSDesktopFolderUsageDescription': f'{app_name} needs access to Desktop folder for file operations.',
            'NSDownloadsFolderUsageDescription': f'{app_name} needs access to Downloads folder for file operations.',
            'NSMicrophoneUsageDescription': f'{app_name} needs microphone access for voice features',
            'NSCameraUsageDescription': f'{app_name} needs camera access for visual features',
            'NSNetworkVolumesUsageDescription': f'{app_name} needs network access for automation',
            'NSAppleEventsUsageDescription': f'{app_name} needs AppleEvents access for system automation',
            'NSSystemAdministrationUsageDescription': f'{app_name} needs admin access for system automation',
            'NSScreenCaptureUsageDescription': f'{app_name} needs screen recording permission for automation tasks.',
            'NSAccessibilityUsageDescription': f'{app_name} needs accessibility permission for automation tasks.',
            'LSUIElement': False,
            'LSBackgroundOnly': False,
        }
        
        # Build CFBundleURLTypes from config
        url_schemes = installer_config.get('url_schemes', [])
        if url_schemes:
            url_types = []
            for scheme_config in url_schemes:
                url_type = {
                    'CFBundleURLName': scheme_config.get('name', f"{scheme_config['scheme']} URL"),
                    'CFBundleURLSchemes': [scheme_config['scheme']],
                }
                if 'role' in scheme_config:
                    url_type['CFBundleTypeRole'] = scheme_config['role']
                if 'icon' in scheme_config:
                    url_type['CFBundleURLIconFile'] = scheme_config['icon']
                url_types.append(url_type)
            fallback_data['CFBundleURLTypes'] = url_types
        else:
            # Fallback to default ecan:// scheme if not configured
            fallback_data['CFBundleURLTypes'] = [{
                'CFBundleURLName': 'eCan URL',
                'CFBundleURLSchemes': ['ecan'],
                'CFBundleTypeRole': 'Viewer'
            }]
        
        # Create temporary fallback file
        temp_dir = self.project_root / 'build' / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        fallback_path = temp_dir / 'Info_fallback.plist'
        
        with open(fallback_path, 'wb') as f:
            plistlib.dump(fallback_data, f)
        
        return str(fallback_path)


def process_info_plist_template(project_root: Path, config: Dict[str, Any], 
                               app_name: str, app_version: str, mode: str = "prod") -> str:
    """
    Convenience function to process Info.plist template
    
    Args:
        project_root: Project root path
        config: Build configuration
        app_name: Application name
        app_version: Application version
        mode: Build mode
        
    Returns:
        Path to processed Info.plist file
    """
    processor = InfoPlistTemplateProcessor(project_root, config)
    return processor.process_template(app_name, app_version, mode)
