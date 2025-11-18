#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OTA Update Dialog Internationalization (i18n)
Provides translation support for OTA update dialogs
"""

from utils.logger_helper import logger_helper as logger


class OTATranslations:
    """OTA dialog translations"""
    
    # Translation dictionary
    TRANSLATIONS = {
        'en': {
            # Window titles
            'window_title': 'ECBot Software Update',
            'confirm_install_title': 'Confirm Update Installation',
            
            # Labels
            'current_version': 'Current Version',
            'latest_version': 'Latest Version',
            'new_version': 'New Version',
            'file_size': 'File Size',
            'release_date': 'Release Date',
            'status': 'Status',
            'download_progress': 'Download Progress',
            'update_info': 'Update Information',
            'update_notes': 'Release Notes',
            'install_options': 'Installation Options',
            'speed': 'Speed',
            'remaining_time': 'Remaining Time',
            
            # Status messages
            'preparing_download': 'Preparing download...',
            'downloading': 'Downloading update...',
            'download_complete': 'Download complete, verifying...',
            'verifying': 'Verifying package...',
            'ready_to_check': 'Ready to check for updates...',
            'checking_updates': 'Checking for updates...',
            'update_available': 'New version available!',
            'no_updates': 'You are using the latest version',
            'check_failed': 'Check failed',
            'preparing_install': 'Preparing to install update',
            
            # Success/Error messages
            'download_success': 'Download and verification successful!',
            'download_failed': 'Download failed',
            'download_cancelled': 'Download cancelled',
            'download_error': 'Download error',
            'verification_failed': 'File verification failed!',
            'no_update_notes': 'No release notes available',
            'unknown': 'Unknown',
            'calculating': 'Calculating...',
            
            # Buttons
            'check_update': 'Check Update',
            'download_update': 'Download',
            'install_update': 'Install',
            'install_now': 'Install Now',
            'update_now': 'Update Now',
            'remind_later': 'Later',
            'cancel': 'Cancel',
            'close': 'Close',
            'ok': 'OK',
            
            # Checkboxes
            'create_backup': 'Create backup before installation',
            'auto_restart': 'Automatically restart application after installation',
            
            # Warnings
            'install_warning': '⚠️ Do not close the application during installation',
            
            # Time formats
            'seconds': 'seconds',
            'minutes': 'minutes',
            'hours': 'hours',
            'second': 'second',
            'minute': 'minute',
            'hour': 'hour',
            
            # Dialog titles and messages
            'software_update': 'Software Update',
            'new_version_available': 'New Version {version} Available',
            'current_version_label': 'Current version: {version}',
            'would_you_like_to_update': 'Would you like to update now?',
            'dont_remind_this_version': "Don't remind me about this version",
            'installer_launched': 'Installer Launched',
            'installer_launched_title': '🚀 Installer Launched!',
            'installer_launched_message': 'The macOS installer has been launched.\n\nPlease follow the on-screen instructions to complete the installation.\n\nAfter installation completes, please restart the application to use the new version.',
            'package_not_found': 'Package not found',
            'package_not_found_message': 'Package not found, please download again.',
            'installation_failed': 'Installation Failed',
            'failed_to_launch_installer': 'Failed to launch installer, please try again later.',
            'creating_backup': 'Creating backup...',
            'installing_update': 'Installing update...',
            'installer_launched_status': 'Installer launched!',
            'installation_failed_status': 'Installation failed',
        },
        'zh': {
            # Window titles
            'window_title': 'ECBot 软件更新',
            'confirm_install_title': '确认安装更新',
            
            # Labels
            'current_version': '当前版本',
            'latest_version': '最新版本',
            'new_version': '新版本',
            'file_size': '文件大小',
            'release_date': '发布日期',
            'status': '状态',
            'download_progress': '下载进度',
            'update_info': '更新信息',
            'update_notes': '更新说明',
            'install_options': '安装选项',
            'speed': '速度',
            'remaining_time': '剩余时间',
            
            # Status messages
            'preparing_download': '准备下载...',
            'downloading': '正在下载更新...',
            'download_complete': '下载完成，正在验证...',
            'verifying': '正在验证包...',
            'ready_to_check': '准备检查更新...',
            'checking_updates': '正在检查更新...',
            'update_available': '发现新版本！',
            'no_updates': '已是最新版本',
            'check_failed': '检查失败',
            'preparing_install': '准备安装更新',
            
            # Success/Error messages
            'download_success': '下载并验证成功！',
            'download_failed': '下载失败',
            'download_cancelled': '下载已取消',
            'download_error': '下载错误',
            'verification_failed': '文件验证失败！',
            'no_update_notes': '无更新说明',
            'unknown': '未知',
            'calculating': '计算中...',
            
            # Buttons
            'check_update': '检查更新',
            'download_update': '下载',
            'install_update': '安装',
            'install_now': '立即安装',
            'update_now': '立即更新',
            'remind_later': '稍后',
            'cancel': '取消',
            'close': '关闭',
            'ok': '确定',
            
            # Checkboxes
            'create_backup': '安装前创建备份',
            'auto_restart': '安装完成后自动重启应用',
            
            # Warnings
            'install_warning': '⚠️ 安装过程中请不要关闭应用程序',
            
            # Time formats
            'seconds': '秒',
            'minutes': '分',
            'hours': '时',
            'second': '秒',
            'minute': '分',
            'hour': '时',
            
            # Dialog titles and messages
            'software_update': '软件更新',
            'new_version_available': '发现新版本 {version}',
            'current_version_label': '当前版本: {version}',
            'would_you_like_to_update': '是否现在更新？',
            'dont_remind_this_version': '不再提示此版本',
            'installer_launched': '安装器已启动',
            'installer_launched_title': '🚀 安装器已启动！',
            'installer_launched_message': 'macOS 安装器已启动。\n\n请按照屏幕上的说明完成安装。\n\n安装完成后，请重启应用程序以使用新版本。',
            'package_not_found': '找不到安装包',
            'package_not_found_message': '找不到安装包，请重新下载。',
            'installation_failed': '安装失败',
            'failed_to_launch_installer': '无法启动安装器，请稍后重试。',
            'creating_backup': '正在创建备份...',
            'installing_update': '正在安装更新...',
            'installer_launched_status': '安装器已启动！',
            'installation_failed_status': '安装失败',
        }
    }
    
    def __init__(self, language=None):
        """
        Initialize translator
        
        Args:
            language: Language code ('en' or 'zh'). If None, auto-detect
        """
        if language is None:
            language = self._detect_language()
        
        self.language = language if language in self.TRANSLATIONS else 'en'
        logger.info(f"[OTA i18n] Language set to: {self.language}")
    
    def _detect_language(self):
        """
        Auto-detect system language using unified i18n helper
        
        Returns:
            str: Language code ('en' or 'zh')
        """
        try:
            # Use unified language detection from utils.i18n_helper
            from utils.i18n_helper import detect_language
            
            # Detect language with supported languages
            detected = detect_language(
                default_lang='en-US',
                supported_languages=['zh-CN', 'en-US']
            )
            
            # Convert to OTA format ('zh-CN' -> 'zh', 'en-US' -> 'en')
            if 'zh' in detected.lower() or 'cn' in detected.lower():
                return 'zh'
            else:
                return 'en'
                
        except Exception as e:
            logger.warning(f"[OTA i18n] Language detection failed: {e}, using default 'en'")
            return 'en'  # Default to English
    
    def tr(self, key):
        """
        Translate a key to current language
        
        Args:
            key: Translation key
            
        Returns:
            Translated string, or key if not found
        """
        return self.TRANSLATIONS.get(self.language, {}).get(key, key)
    
    def set_language(self, language):
        """
        Set current language
        
        Args:
            language: Language code ('en' or 'zh')
        """
        if language in self.TRANSLATIONS:
            self.language = language


# Global translator instance
_translator = None


def get_translator(language=None):
    """
    Get global translator instance
    
    Args:
        language: Language code ('en' or 'zh'). If None, use existing or auto-detect
        
    Returns:
        OTATranslations instance
    """
    global _translator
    if _translator is None or language is not None:
        _translator = OTATranslations(language)
    return _translator


def tr(key):
    """
    Shorthand for translation
    
    Args:
        key: Translation key
        
    Returns:
        Translated string
    """
    return get_translator().tr(key)
