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
        'en-US': {
            # Window titles
            'window_title': 'eCan.ai Software Update',
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
            'install_progress': 'Installation Progress',
            
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
            'installing_update': 'Installing update, please wait...',
            'installer_launched_status': 'Installer launched!',
            'installation_failed_status': 'Installation failed',
            'app_update': 'eCan Update',
            'verifying_package': 'Verifying package...',
            'writing_files': 'Writing files...',
            'running_scripts': 'Running package scripts...',
            'writing_receipt': 'Writing package receipt...',
            'installing': 'Installing...',
            'install_complete': 'Software installed successfully',
            'install_complete_restart': 'Installation complete, app will restart in 3 seconds',
            
            # Download manager states
            'check_for_updates': 'Check for Updates...',
            'checking_for_updates': 'Checking for updates...',
            'downloading_progress': 'Downloading... {progress}%',
            'preparing_download_state': 'Preparing download...',
            'verifying_state': 'Verifying...',
            'download_complete_state': 'Download complete',
            'download_failed_state': 'Download failed',
            'cancelled_state': 'Cancelled',
            
            # Installer progress
            'installing_update_progress': 'Installing update... {progress}%',
            'installing_update_with_phase': 'Installing update... {progress}%\n{phase}',
            
            # Download link
            'download_link': 'Download Link',
            'click_to_copy': 'Click to copy',
            'click_to_copy_tooltip': 'Click to copy download link to clipboard',
            'link_copied': 'Link copied!',
            'link_copied_title': 'Link Copied',
            'link_copied_message': 'Download link has been copied to clipboard:',
        },
        'zh-CN': {
            # Window titles
            'window_title': 'eCan.ai 软件更新',
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
            'install_progress': '安装进度',
            
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
            'installing_update': '正在安装更新，请稍候...',
            'installer_launched_status': '安装程序已启动！',
            'installation_failed_status': '安装失败',
            'app_update': 'eCan 更新',
            'verifying_package': '正在验证软件包...',
            'writing_files': '正在写文件...',
            'running_scripts': '正在运行软件包脚本...',
            'writing_receipt': '正在写软件包回执...',
            'installing': '正在安装...',
            'install_complete': '软件已成功安装',
            'install_complete_restart': '安装完成，应用将在 3 秒后重启',
            
            # Download manager states
            'check_for_updates': '检查更新...',
            'checking_for_updates': '正在检查更新...',
            'downloading_progress': '下载中... {progress}%',
            'preparing_download_state': '准备下载...',
            'verifying_state': '验证中...',
            'download_complete_state': '下载完成',
            'download_failed_state': '下载失败',
            'cancelled_state': '已取消',
            
            # Installer progress
            'installing_update_progress': '正在安装更新... {progress}%',
            'installing_update_with_phase': '正在安装更新... {progress}%\n{phase}',
            
            # Download link
            'download_link': '下载链接',
            'click_to_copy': '点击复制',
            'click_to_copy_tooltip': '点击复制下载链接到剪贴板',
            'link_copied': '链接已复制！',
            'link_copied_title': '链接已复制',
            'link_copied_message': '下载链接已复制到剪贴板：',
        }
    }
    
    def __init__(self, language=None):
        """
        Initialize translator
        
        Args:
            language: Language code ('en-US' or 'zh-CN'). If None, auto-detect
        """
        if language is None:
            language = self._detect_language()
        
        # Normalize language code to standard format
        self.language = self._normalize_language(language)
        logger.info(f"[OTA i18n] Language set to: {self.language}")
    
    def _normalize_language(self, language):
        """
        Normalize language code to standard format
        
        Args:
            language: Language code (can be 'zh', 'zh-CN', 'en', 'en-US', etc.)
            
        Returns:
            str: Normalized language code ('zh-CN' or 'en-US')
        """
        if not language:
            return 'en-US'
        
        lang_lower = language.lower()
        
        # Chinese variants
        if 'zh' in lang_lower or 'cn' in lang_lower or 'chinese' in lang_lower:
            return 'zh-CN'
        
        # English variants (default)
        return 'en-US'
    
    def _detect_language(self):
        """
        Auto-detect system language using unified i18n helper
        
        Returns:
            str: Language code ('zh-CN' or 'en-US')
        """
        try:
            # Use unified language detection from utils.i18n_helper
            from utils.i18n_helper import detect_language
            
            # Detect language with supported languages
            detected = detect_language(
                default_lang='en-US',
                supported_languages=['zh-CN', 'en-US']
            )
            
            # Normalize to standard format
            return self._normalize_language(detected)
                
        except Exception as e:
            logger.warning(f"[OTA i18n] Language detection failed: {e}, using default 'en-US'")
            return 'en-US'  # Default to English
    
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
