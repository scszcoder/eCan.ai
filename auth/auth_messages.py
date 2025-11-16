"""
Authentication error messages with internationalization support.
This module provides localized error messages that align with gui_v2 login page.
"""

class AuthMessages:
    """Centralized authentication messages with i18n support."""
    
    # Default language
    DEFAULT_LANG = 'en-US'
    
    # Message definitions aligned with gui_v2/src/i18n/locales/
    MESSAGES = {
        'en-US': {
            # Login messages
            'login_success': 'Login successful',
            'login_failed': 'Login failed',
            'login_network_error': 'Network connection failed. Please check your internet connection and try again.',
            'login_timeout_error': 'Authentication request timed out. Please try again or check your network connection.',
            'login_invalid_credentials': 'Invalid username or password',
            'login_user_not_confirmed': 'User email confirmation is needed. Please check your email and confirm first.',
            'login_password_incorrect': 'Password incorrect.',
            'google_login_success': 'Successfully logged in with Google.',
            'get_last_login_success': 'Last login information retrieved successfully.',
            
            # Signup messages
            'signup_success': 'Please confirm that you have received the verification email and verified it.',
            'signup_user_exists': 'An account with this email already exists. Please try logging in instead.',
            'signup_invalid_password': 'Password does not meet requirements. Please use a stronger password.',
            'signup_invalid_email': 'Invalid email format. Please enter a valid email address.',
            'signup_failed': 'Sign up failed',
            
            # Forgot password messages
            'forgot_password_sent': 'Password reset code sent to your email',
            'forgot_password_failed': 'Error in Handle forgot password',
            
            # Confirm forgot password messages
            'confirm_forgot_success': 'Password reset successful. You can now login with your new password.',
            'confirm_forgot_invalid_code': 'Invalid verification code. Please check your email and try again.',
            'confirm_forgot_expired_code': 'Verification code has expired. Please request a new password reset.',
            'confirm_forgot_invalid_password': 'Password does not meet requirements. Please use a stronger password.',
            'confirm_forgot_user_not_found': 'User not found. Please check your email address.',
            'confirm_forgot_failed': 'Failed to confirm password reset',
            
            # Logout messages
            'logout_success': 'User logged out successfully',
            'logout_failed': 'Logout failed',
            
            # OAuth callback messages
            'oauth_success_title': 'Authentication Successful',
            'oauth_success_message': 'You have successfully authenticated with Google.',
            'oauth_success_app_prompt': 'Please open the ecan.ai application',
            'oauth_success_launching': 'Opening ecan.ai application in {countdown} seconds...',
            'oauth_manual_launch': 'Open ecan.ai Application',
            'oauth_success_confirm_prompt': (
                'Authentication successful!\\n\\n'
                'Do you want to open the ecan.ai application to complete login?\\n\\n'
                'If the app does not open automatically, you can click the "Open ecan.ai Application" button on this page.'
            ),
            
            # OAuth error messages
            'oauth_error_title': 'Authentication Error',
            'oauth_error_label': 'Error',
            'oauth_error_description_label': 'Description',
            'oauth_error_close_instruction': 'Please close this window and try again.'
        },
        'zh-CN': {
            # Login messages
            'login_success': '登录成功',
            'login_failed': '登录失败',
            'login_network_error': '网络连接失败。请检查您的网络连接并重试。',
            'login_timeout_error': '认证请求超时。请重试或检查您的网络连接。',
            'login_invalid_credentials': '用户名或密码无效',
            'login_user_not_confirmed': '需要确认用户邮箱。请检查您的邮箱并先确认。',
            'login_password_incorrect': '密码错误。',
            'google_login_success': 'Google 登录成功',
            'get_last_login_success': '成功获取上次登录信息',
            
            # Signup messages
            'signup_success': '请确认您已收到验证邮件并完成验证。',
            'signup_user_exists': '该邮箱已存在账户。请尝试登录。',
            'signup_invalid_password': '密码不符合要求。请使用更强的密码。',
            'signup_invalid_email': '邮箱格式无效。请输入有效的邮箱地址。',
            'signup_failed': '注册失败',
            
            # Forgot password messages
            'forgot_password_sent': '密码重置验证码已发送到您的邮箱',
            'forgot_password_failed': '处理忘记密码时出错',
            
            # Confirm forgot password messages
            'confirm_forgot_success': '密码重置成功。您现在可以使用新密码登录。',
            'confirm_forgot_invalid_code': '验证码无效。请检查您的邮箱并重试。',
            'confirm_forgot_expired_code': '验证码已过期。请重新请求密码重置。',
            'confirm_forgot_invalid_password': '密码不符合要求。请使用更强的密码。',
            'confirm_forgot_user_not_found': '用户不存在。请检查您的邮箱地址。',
            'confirm_forgot_failed': '确认密码重置失败',
            
            # Logout messages
            'logout_success': '用户已成功退出',
            'logout_failed': '退出失败',
            
            # OAuth callback messages
            'oauth_success_title': '认证成功',
            'oauth_success_message': '您已成功通过Google认证。',
            'oauth_success_app_prompt': '请打开 ecan.ai 应用',
            'oauth_success_launching': '正在打开 ecan.ai 应用，{countdown} 秒后自动启动...',
            'oauth_manual_launch': '打开 ecan.ai 应用',
            'oauth_success_confirm_prompt': (
                '认证成功！\\n\\n'
                '是否同意打开 ecan.ai 应用以完成登录？\\n\\n'
                '如果应用没有自动打开，您可以点击页面上的“打开 ecan.ai 应用”按钮。'
            ),
            
            # OAuth error messages
            'oauth_error_title': '认证错误',
            'oauth_error_label': '错误',
            'oauth_error_description_label': '描述',
            'oauth_error_close_instruction': '请关闭此窗口并重试。'
        }
    }
    
    def __init__(self, language: str = None):
        """Initialize with specified language or default."""
        self.language = language or self.DEFAULT_LANG
        if self.language not in self.MESSAGES:
            self.language = self.DEFAULT_LANG
    
    def get_message(self, key: str, language: str = None) -> str:
        """Get localized message by key."""
        lang = language or self.language
        if lang not in self.MESSAGES:
            lang = self.DEFAULT_LANG
        
        return self.MESSAGES[lang].get(key, f"Message key '{key}' not found")
    
    def set_language(self, language: str):
        """Set the current language."""
        if language in self.MESSAGES:
            self.language = language
    
    def get_available_languages(self) -> list:
        """Get list of available languages."""
        return list(self.MESSAGES.keys())


# Global instance for easy access
auth_messages = AuthMessages()
