/**
 * 登录相关常量
 */

export const LOGIN_SUCCESS_REDIRECT = '/dashboard';

export const LOGIN_MESSAGES = {
    USERNAME_REQUIRED: 'Please input your username!',
    PASSWORD_REQUIRED: 'Please input your password!',
    LOGIN_FAILED: 'Login failed',
    LOGIN_SUCCESS: 'Login successful',
} as const;

export const LOGIN_FORM = {
    USERNAME_PLACEHOLDER: 'Username',
    PASSWORD_PLACEHOLDER: 'Password',
    SUBMIT_TEXT: 'Login',
} as const; 