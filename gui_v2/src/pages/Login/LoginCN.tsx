/**
 * CN 版本登录页面
 * 使用腾讯云 CloudBase 认证
 * 主流居中卡片式布局
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Select, App, Spin } from 'antd';
import { UserOutlined, LockOutlined, MobileOutlined, WechatOutlined, MailOutlined, SafetyCertificateOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse } from '../../services/ipc/api';
import { get_ipc_api } from '../../services/ipc_api';
import { userStorageManager, type LoginSession } from '../../services/storage/UserStorageManager';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import { useInitializationProgress, forceCleanupInitializationProgress } from '../../hooks/useInitializationProgress';
import { tokenRefreshService } from '../../services/auth/tokenRefreshService';
import { cloudbaseAuth } from '../../services/auth/cloudbaseAuth';
import { useAppConfig } from '../../contexts/AppConfigContext';
import LoadingProgress from '../../components/LoadingProgress/LoadingProgress';
import logo from '../../assets/logoWhite22.png';
import './Login.css';

interface LoginFormValues {
  username: string;
  password: string;
  confirmPassword?: string;
  role: string;
  phone?: string;
  code?: string;
  newPassword?: string;
}

type AuthMode = 'email-login' | 'email-signup' | 'phone-login' | 'phone-signup' | 'forgot';

const LoginCN: React.FC = () => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { config: appConfig } = useAppConfig();
  const [form] = Form.useForm<LoginFormValues>();

  // State
  const [activeTab, setActiveTab] = useState<'email' | 'phone' | 'wechat'>('email');
  const [mode, setMode] = useState<AuthMode>('email-login');
  const [loading, setLoading] = useState(false);
  const [showInitProgress, setShowInitProgress] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [loginSuccessful, setLoginSuccessful] = useState(false);
  const [hasNavigated, setHasNavigated] = useState(false);
  const [loginProgress, setLoginProgress] = useState<'idle' | 'authenticating' | 'success' | 'redirecting'>('idle');
  const [lastError, setLastError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [wechatAvailable, setWechatAvailable] = useState(false);
  const [pendingSignupCode, setPendingSignupCode] = useState<{ email: string; password: string; verificationId: string } | null>(null);

  const lastLoginAttemptRef = useRef<number>(0);
  const LOGIN_DEBOUNCE_MS = 3000;

  const { progress: initProgress } = useInitializationProgress(loading || showInitProgress);

  // 初始化
  useEffect(() => {
    forceCleanupInitializationProgress();
  }, []);

  // 初始化 CloudBase
  useEffect(() => {
    const envId = appConfig?.auth?.cloudbase_env_id || '';
    if (envId) {
      cloudbaseAuth.initialize({ envId });
    }
  }, [appConfig?.auth?.cloudbase_env_id]);

  // 检查微信登录是否可用
  useEffect(() => {
    const checkWechat = async () => {
      try {
        const result = await cloudbaseAuth.checkConfig();
        setWechatAvailable(result.wechatAvailable || false);
      } catch {
        setWechatAvailable(false);
      }
    };
    checkWechat();
  }, []);

  // 监听 URL 参数（微信回调）
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, '').split('?')[1] || '');
    const code = urlParams.get('code') || hashParams.get('code');
    const state = urlParams.get('state') || hashParams.get('state');
    const savedState = sessionStorage.getItem('wx_state');

    if (code && state && savedState && state === savedState) {
      window.history.replaceState({}, '', window.location.pathname);
      sessionStorage.removeItem('wx_state');

      (async () => {
        try {
          setLoginProgress('authenticating');
          setShowInitProgress(true);

          const cloudbase = (await import('@cloudbase/js-sdk')).default;
          const app = cloudbase.init({
            env: appConfig?.auth?.cloudbase_env_id || '',
            region: 'ap-shanghai',
            auth: { detectSessionInUrl: true },
          });
          const auth = app.auth();

          const { provider_token } = await auth.grantProviderToken({
            provider_id: 'wx_open',
            provider_redirect_uri: window.location.origin,
            provider_code: code,
          });

          let loginResult;
          try {
            loginResult = await auth.signInWithProvider({ provider_token });
          } catch (e: any) {
            if (e?.error === 'not_found') {
              messageApi.warning('请先注册账号，然后再次扫码登录');
              setLoginProgress('idle');
              setShowInitProgress(false);
              return;
            }
            throw e;
          }

          const accessToken = await auth.getAccessToken();
          const cbUserInfo: any = loginResult?.user || {};
          const userIdentifier = cbUserInfo.email || cbUserInfo.uuid || `wechat_${cbUserInfo.openId || ''}`;

          const userInfo = {
            username: userIdentifier,
            email: cbUserInfo.email || '',
            name: cbUserInfo.nickName || cbUserInfo.nickname || cbUserInfo.displayName || '',
            given_name: '',
            family_name: '',
            picture: cbUserInfo.avatarUrl || '',
            email_verified: !!cbUserInfo.email,
            login_type: 'wechat' as const,
            uuid: cbUserInfo.uuid || '',
          };

          const finalizeResult = await cloudbaseAuth.finalizeSession({
            access_token: accessToken || '',
            refresh_token: accessToken || '',
            expires_in: 7200,
            user_identifier: userIdentifier,
            user_info: userInfo,
            role: 'Commander',
            lang: i18n.language,
          });

          if (!finalizeResult.success) {
            throw new Error(finalizeResult.error || 'Finalize session failed');
          }

          const ipcToken = finalizeResult.ipc_token || accessToken || '';
          const backendUserInfo = finalizeResult.data?.userInfo || userInfo;

          saveLoginSession(
            ipcToken,
            {
              username: userIdentifier,
              email: backendUserInfo.email || '',
              name: backendUserInfo.name || '',
              given_name: backendUserInfo.given_name || '',
              family_name: backendUserInfo.family_name || '',
              picture: backendUserInfo.picture || '',
              email_verified: backendUserInfo.email_verified ?? !!cbUserInfo.email,
              login_type: 'wechat',
            },
            'Commander',
            'wechat',
          );

          setLoginProgress('success');
          messageApi.success(t('login.wechat_login_success') || '微信登录成功');
          setLoginSuccessful(true);
          setLoginProgress('redirecting');
        } catch (err: any) {
          console.error('[WeChat Callback] Error:', err);
          setLoginProgress('idle');
          setShowInitProgress(false);
          messageApi.error(err?.message || '微信登录失败');
        }
      })();
    }
  }, [navigate, messageApi, t, appConfig?.auth?.cloudbase_env_id]);

  // 导航逻辑
  useEffect(() => {
    if (!initProgress?.ui_ready) return;
    if (!loginSuccessful) return;
    if (hasNavigated) return;

    setHasNavigated(true);
    setLoading(false);
    setShowInitProgress(false);
    navigate('/agents');
  }, [initProgress, loginSuccessful, hasNavigated, navigate]);

  // 加载上次登录信息
  useEffect(() => {
    const initialize = async () => {
      try {
        const api = get_ipc_api();
        if (!api) return;

        const timeoutPromise = new Promise((_, reject) => {
          setTimeout(() => reject(new Error('IPC initialization timeout')), 15000);
        });

        const response = await Promise.race([
          api.getLastLoginInfo(),
          timeoutPromise
        ]) as APIResponse<any>;

        const loginData = (response?.data as any)?.last_login;
        if (loginData) {
          const { username, password, machine_role, language } = loginData;

          if (language && i18n.language !== language) {
            await i18n.changeLanguage(language);
            localStorage.setItem('i18nextLng', language);
          }

          form.setFieldsValue({
            username,
            password,
            role: machine_role || 'Commander'
          });
        }
      } catch (error) {
        console.warn('[LoginCN] Failed to load last login info:', error);
      }
    };

    const timer = setTimeout(initialize, 100);
    return () => clearTimeout(timer);
  }, [form, i18n.language]);

  // 验证码倒计时
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  // 处理语言切换
  const handleLanguageChange = useCallback(async (value: string) => {
    if (i18n.language !== value) {
      await i18n.changeLanguage(value);
      localStorage.setItem('i18nextLng', value);

      try {
        const api = get_ipc_api();
        if (api) {
          await api.updateUserPreferences(value);
        }
      } catch (error) {
        console.error('[LoginCN] Error saving language preference:', error);
      }
    }
  }, [i18n]);

  // Tab 切换
  const handleTabChange = useCallback((tab: 'email' | 'phone' | 'wechat') => {
    setActiveTab(tab);
    if (tab === 'email') {
      setMode('email-login');
    } else if (tab === 'phone') {
      setMode('phone-login');
    }
    // 微信 tab 不改变 mode，点击后直接触发登录
    form.resetFields();
    setCodeSent(false);
    setPendingSignupCode(null);
    setLastError(null);
  }, [form]);

  const ensureCloudbase = useCallback((): boolean => {
    if (!appConfig?.auth?.cloudbase_env_id) {
      messageApi.error(t('login.cloudbaseNotConfigured'));
      return false;
    }
    return true;
  }, [appConfig?.auth?.cloudbase_env_id, messageApi, t]);

  // 保存登录会话
  const saveLoginSession = useCallback((
    token: string,
    userInfo: any,
    role: string,
    loginType: 'password' | 'google' = 'password'
  ) => {
    const loginSession: LoginSession = {
      token,
      userInfo: {
        username: userInfo.username || userInfo.email || userInfo.phone || '',
        email: userInfo.email || '',
        role,
        name: userInfo.name || '',
        given_name: userInfo.given_name || '',
        family_name: userInfo.family_name || '',
        picture: userInfo.picture || '',
        email_verified: userInfo.email_verified ?? true,
        login_type: loginType
      },
      loginTime: Date.now()
    };

    userStorageManager.saveLoginSession(loginSession);
    pageRefreshManager.enable();
    sessionStorage.removeItem('token_expired_notification_shown');

    tokenRefreshService.start(token, {
      checkInterval: 30 * 60 * 1000,
      refreshThreshold: 60 * 60,
      onTokenRefreshed: (newToken: string) => {
        userStorageManager.setToken(newToken);
      },
      onTokenExpired: () => {
        messageApi.warning(t('login.sessionExpired'));
        userStorageManager.logout();
        navigate('/login');
      }
    });
  }, [messageApi, navigate, t]);

  // 发送手机验证码
  const handleSendCode = useCallback(async (phone: string) => {
    if (countdown > 0) return;
    if (!ensureCloudbase()) return;

    try {
      const result = await cloudbaseAuth.sendPhoneCode(phone, 'login');
      if (result.success) {
        setCodeSent(true);
        setCountdown(60);
        if (result.verificationId) {
          setVerificationId(result.verificationId);
        }
        messageApi.success(t('login.codeSent'));
        if (result.devCode) {
          messageApi.info(`[Dev] Code: ${result.devCode}`, 5);
        }
      } else {
        messageApi.error(result.error || t('login.codeSendFailed'));
      }
    } catch (error) {
      messageApi.error(String(error));
    }
  }, [countdown, ensureCloudbase, messageApi, t]);

  // 手机号登录
  const handlePhoneLogin = useCallback(async (phone: string, code: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return false;
    }
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithPhone(phone, code, verificationId || undefined);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.success'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        setVerificationId(null);
        return true;
      }

      messageApi.error(result.error || t('login.failed'));
      setLastError(result.error || t('login.failed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLastError(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [saveLoginSession, messageApi, t, verificationId]);

  // 邮箱登录
  const handleEmailLogin = useCallback(async (email: string, password: string, role: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return false;
    }

    // 防止空密码触发 CloudBase 远程调用（keyring 中无密码时会被回填为空字符串）
    if (!password || !password.trim()) {
      const msg = t('login.passwordRequired') || '请输入密码';
      messageApi.warning(msg);
      setLastError(msg);
      setLoginProgress('idle');
      return false;
    }

    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithEmail(email, password);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, role, 'password');
        messageApi.success(t('login.success'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        return true;
      }

      messageApi.error(result.error || t('login.failed'));
      setLastError(result.error || t('login.failed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLastError(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [ensureCloudbase, saveLoginSession, messageApi, t]);

  // 发送密码重置验证码
  const handleSendForgotCode = useCallback(async (phone: string) => {
    if (countdown > 0) return;
    if (!ensureCloudbase()) return;

    try {
      const result = await cloudbaseAuth.sendPasswordResetCode(phone);
      if (result.success) {
        setCodeSent(true);
        setCountdown(60);
        if (result.verificationId) {
          setVerificationId(result.verificationId);
        }
        messageApi.success(t('login.codeSent'));
        if (result.devCode) {
          messageApi.info(`[Dev] Code: ${result.devCode}`, 5);
        }
      } else {
        messageApi.error(result.error || t('login.codeSendFailed'));
      }
    } catch (error) {
      messageApi.error(String(error));
    }
  }, [countdown, ensureCloudbase, messageApi, t]);

  // 重置密码
  const handleResetPassword = useCallback(async (phone: string, code: string, newPassword: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return;
    }
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.resetPasswordWithPhone(phone, code, newPassword, verificationId || undefined);

      if (result.success) {
        messageApi.success(t('login.forgotSuccess'));
        setMode('email-login');
        setActiveTab('email');
        form.resetFields();
        setCodeSent(false);
        setVerificationId(null);
      } else {
        messageApi.error(result.error || t('login.forgotResetError'));
      }
    } catch (error) {
      messageApi.error(String(error));
    } finally {
      setLoginProgress('idle');
    }
  }, [ensureCloudbase, messageApi, t, form, verificationId]);

  // 手机号注册
  const handlePhoneSignup = useCallback(async (phone: string, code: string) => {
    if (!ensureCloudbase()) {
      setLoginProgress('idle');
      return false;
    }
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.signupWithPhone(phone, code, undefined, verificationId || undefined);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.signupSuccess'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        setVerificationId(null);
        return true;
      }

      messageApi.error(result.error || t('login.signupFailed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [ensureCloudbase, saveLoginSession, messageApi, t, verificationId]);

  // 邮箱注册
  const handleSignup = useCallback(async (email: string, password: string) => {
    if (!ensureCloudbase()) {
      setLoading(false);
      return;
    }

    try {
      if (!pendingSignupCode) {
        setLoading(true);
        const result = await cloudbaseAuth.signupWithEmail(email, password);

        if (result.success) {
          if (result.verificationId) {
            setPendingSignupCode({ email, password, verificationId: result.verificationId });
            setCodeSent(true);
            setCountdown(60);
            messageApi.success(t('login.codeSent') || '验证码已发送');
          } else {
            messageApi.info(t('login.emailAlreadyRegistered') || '该邮箱已注册，请直接登录');
            setMode('email-login');
          }
        } else {
          messageApi.error(result.error || t('login.failed'));
        }
        return;
      }

      // 输入验证码完成注册
      setLoading(true);
      const values = form.getFieldsValue(['code']) as { code?: string };
      const code = (values.code || '').trim();
      if (!code) {
        messageApi.error(t('login.codeRequired') || '请输入验证码');
        return;
      }

      const result = await cloudbaseAuth.confirmSignupWithEmail(
        pendingSignupCode.email,
        code,
        pendingSignupCode.password,
        pendingSignupCode.verificationId,
      );

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.signupSuccess'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        setPendingSignupCode(null);
        setVerificationId(null);
        setCodeSent(false);
      } else {
        messageApi.error(result.error || t('login.signupFailed'));
      }
    } catch (error) {
      messageApi.error(String(error));
    } finally {
      setLoading(false);
    }
  }, [ensureCloudbase, messageApi, t, pendingSignupCode, form, saveLoginSession]);

  // 微信登录
  const handleWechatLogin = useCallback(async () => {
    if (!ensureCloudbase()) return;

    try {
      const resp = await cloudbaseAuth.loginWithCloudBaseWechat();
      console.log('[WeChat H5] Response:', resp);

      if (!resp.success) {
        messageApi.error(resp.error || 'Failed to start WeChat login');
      }
    } catch (error) {
      console.error('[WeChat H5] Error:', error);
      messageApi.error(String(error));
    }
  }, [ensureCloudbase, messageApi]);

  // 提交处理
  const handleSubmit = useCallback(async (values: LoginFormValues) => {
    if (loading || loginSuccessful) return;

    const now = Date.now();
    if (now - lastLoginAttemptRef.current < LOGIN_DEBOUNCE_MS) {
      return;
    }
    lastLoginAttemptRef.current = now;

    setLoading(true);
    setLoginSuccessful(false);
    setHasNavigated(false);
    setLastError(null);
    setShowInitProgress(true);

    let loginAttempted = false;

    try {
      switch (mode) {
        case 'email-login':
          loginAttempted = true;
          await handleEmailLogin(values.username, values.password, values.role);
          return;
        case 'email-signup':
          if (values.password !== values.confirmPassword) {
            messageApi.error(t('login.passwordMismatch'));
            setLoading(false);
            setShowInitProgress(false);
            return;
          }
          await handleSignup(values.username, values.password);
          break;
        case 'phone-login':
          await handlePhoneLogin(values.phone!, values.code!);
          break;
        case 'phone-signup':
          await handlePhoneSignup(values.phone!, values.code!);
          break;
        case 'forgot':
          if (values.newPassword !== values.confirmPassword) {
            messageApi.error(t('login.passwordMismatch'));
            setLoading(false);
            setShowInitProgress(false);
            return;
          }
          await handleResetPassword(values.phone!, values.code!, values.newPassword!);
          break;
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setLastError(errorMessage);
      messageApi.error(errorMessage);
      setLoginProgress('idle');

      if (mode === 'email-login' && loginAttempted) {
        setLoading(false);
        setShowInitProgress(false);
      }
    } finally {
      if (mode !== 'email-login' || !loginAttempted) {
        setLoading(false);
      }
    }
  }, [loading, loginSuccessful, mode, handleEmailLogin, handleSignup, handlePhoneLogin, handlePhoneSignup, handleResetPassword, messageApi, t]);

  // 模式切换
  const handleModeChange = useCallback((newMode: AuthMode) => {
    setMode(newMode);
    if (newMode === 'email-login' || newMode === 'email-signup') {
      setActiveTab('email');
    } else if (newMode === 'phone-login' || newMode === 'phone-signup') {
      setActiveTab('phone');
    }
    form.resetFields();
    setLoading(false);
    setLoginSuccessful(false);
    setHasNavigated(false);
    setCodeSent(false);
    setShowInitProgress(false);
    setLoginProgress('idle');
    setLastError(null);
    setCountdown(0);
    setVerificationId(null);
    setPendingSignupCode(null);
  }, [form]);

  // 获取标题
  const getTitle = () => {
    switch (mode) {
      case 'email-login': return t('login.title');
      case 'email-signup': return t('login.createAccount');
      case 'phone-login': return t('login.phoneLogin');
      case 'phone-signup': return t('login.phoneSignup');
      case 'forgot': return t('login.forgotPassword');
      default: return t('login.title');
    }
  };

  return (
    <div className="cn-login-container">
      <div className="cn-login-decoration" />

      {/* 语言选择器 */}
      <div className="cn-language-selector">
        <Select
          value={i18n.language}
          size="small"
          onChange={handleLanguageChange}
          variant="borderless"
        >
          <Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
          <Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
        </Select>
      </div>

      {/* 加载进度 */}
      <LoadingProgress
        visible={loading || showInitProgress}
        progress={initProgress}
        title={loginProgress === 'redirecting' ? t('login.redirectingToMain') : undefined}
        onComplete={() => {
          setLoading(false);
          setShowInitProgress(false);
        }}
      />

      {/* 登录卡片 */}
      <div className="cn-login-card">
        {loading && loginProgress === 'authenticating' ? (
          <div className="cn-loading-container">
            <Spin size="large" />
            <div className="cn-loading-text">
              {loginProgress === 'redirecting'
                ? t('login.redirectingToMain')
                : loginProgress === 'success'
                  ? t('login.success')
                  : t('login.verifying')}
            </div>
          </div>
        ) : (
          <>
            {/* Logo */}
            <div className="cn-login-logo">
              <img src={logo} alt={t('login.logoAlt')} />
            </div>

            {/* 标题 */}
            <h1 className="cn-login-title">{getTitle()}</h1>
            <p className="cn-login-subtitle">{t('login.subtitle')}</p>

            {/* Tab 切换 */}
            {mode !== 'forgot' && (
              <div className="cn-login-tabs">
                <button
                  type="button"
                  className={`cn-tab ${activeTab === 'email' ? 'active' : ''}`}
                  onClick={() => handleTabChange('email')}
                >
                  <MailOutlined />
                  <span>{t('login.emailTab')}</span>
                </button>
                <button
                  type="button"
                  className={`cn-tab ${activeTab === 'phone' ? 'active' : ''}`}
                  onClick={() => handleTabChange('phone')}
                >
                  <MobileOutlined />
                  <span>{t('login.phoneTab')}</span>
                </button>
                {wechatAvailable && (
                  <button
                    type="button"
                    className={`cn-tab ${activeTab === 'wechat' ? 'active' : ''}`}
                    onClick={() => handleTabChange('wechat')}
                  >
                    <WechatOutlined />
                    <span>{t('login.wechatTab')}</span>
                  </button>
                )}
              </div>
            )}

            {/* 表单 */}
            <Form
              form={form}
              name="login"
              onFinish={handleSubmit}
              layout="vertical"
              requiredMark={false}
              initialValues={{ role: 'Commander' }}
              className="cn-login-form"
            >
              {/* 邮箱登录/注册表单 */}
              {(activeTab === 'email' && mode !== 'forgot') && (
                <>
                  <Form.Item
                    name="username"
                    rules={[{ required: true, message: t('login.usernameRequired') }]}
                  >
                    <Input
                      prefix={<UserOutlined />}
                      placeholder={t('common.email')}
                      size="large"
                      autoComplete="username"
                    />
                  </Form.Item>

                  {mode === 'email-login' && (
                    <Form.Item
                      name="password"
                      rules={[{ required: true, message: t('login.passwordRequired') }]}
                    >
                      <Input.Password
                        prefix={<LockOutlined />}
                        placeholder={t('common.password')}
                        size="large"
                        autoComplete="current-password"
                      />
                    </Form.Item>
                  )}

                  {mode === 'email-signup' && (
                    <>
                      <Form.Item
                        name="password"
                        rules={[
                          { required: true, message: t('login.passwordRequired') },
                          { min: 8, message: t('login.passwordMinLength') },
                          { pattern: /[A-Z]/, message: t('login.passwordNeedUppercase') },
                          { pattern: /[a-z]/, message: t('login.passwordNeedLowercase') },
                          { pattern: /[0-9]/, message: t('login.passwordNeedNumber') },
                        ]}
                      >
                        <Input.Password
                          prefix={<LockOutlined />}
                          placeholder={t('common.password')}
                          size="large"
                          autoComplete="new-password"
                        />
                      </Form.Item>
                      <Form.Item
                        name="confirmPassword"
                        rules={[
                          { required: true, message: t('login.confirmPasswordRequired') },
                          ({ getFieldValue }) => ({
                            validator(_, value) {
                              if (!value || getFieldValue('password') === value) {
                                return Promise.resolve();
                              }
                              return Promise.reject(new Error(t('login.passwordMismatch')));
                            },
                          }),
                        ]}
                      >
                        <Input.Password
                          prefix={<LockOutlined />}
                          placeholder={t('login.confirmPassword')}
                          size="large"
                          autoComplete="new-password"
                        />
                      </Form.Item>
                      {pendingSignupCode && (
                        <Form.Item
                          name="code"
                          rules={[{ required: true, message: t('login.codeRequired') }]}
                        >
                          <Input
                            prefix={<SafetyCertificateOutlined />}
                            placeholder={t('login.codePlaceholder')}
                            size="large"
                            maxLength={6}
                            disabled={loginSuccessful}
                          />
                        </Form.Item>
                      )}
                    </>
                  )}

                  {mode === 'email-login' && (
                    <Form.Item name="role" rules={[{ required: true }]}>
                      <Select size="large">
                        <Select.Option value="Commander">{t('roles.commander')}</Select.Option>
                        <Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
                        <Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
                      </Select>
                    </Form.Item>
                  )}
                </>
              )}

              {/* 手机号表单 */}
              {activeTab === 'phone' && mode !== 'forgot' && (
                <>
                  <Form.Item
                    name="phone"
                    rules={[
                      { required: true, message: t('login.phoneRequired') },
                      { pattern: /^1[3-9]\d{9}$/, message: t('login.invalidPhone') }
                    ]}
                  >
                    <Input
                      prefix={<MobileOutlined />}
                      placeholder={t('login.phonePlaceholder')}
                      size="large"
                      disabled={codeSent}
                      maxLength={11}
                    />
                  </Form.Item>
                  <Form.Item
                    name="code"
                    rules={[{ required: true, message: t('login.codeRequired') }]}
                  >
                    <Input
                      prefix={<SafetyCertificateOutlined />}
                      placeholder={t('login.codePlaceholder')}
                      size="large"
                      maxLength={6}
                      suffix={
                        <button
                          type="button"
                          className="cn-send-code-btn"
                          disabled={countdown > 0 || !form.getFieldValue('phone')}
                          onClick={() => handleSendCode(form.getFieldValue('phone'))}
                        >
                          {countdown > 0 ? `${countdown}s` : t('login.sendCode')}
                        </button>
                      }
                    />
                  </Form.Item>
                  <Form.Item name="role" rules={[{ required: true }]}>
                    <Select size="large">
                      <Select.Option value="Commander">{t('roles.commander')}</Select.Option>
                      <Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
                      <Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
                    </Select>
                  </Form.Item>
                </>
              )}

              {/* 微信扫码区域 */}
              {activeTab === 'wechat' && wechatAvailable && (
                <div className="cn-wechat-area">
                  <div className="cn-wechat-icon">
                    <WechatOutlined style={{ fontSize: 36, color: '#07c160' }} />
                  </div>
                  <p className="cn-wechat-hint">{t('login.wechatHint') || '使用微信扫码登录'}</p>
                  <button
                    type="button"
                    className="cn-wechat-btn"
                    onClick={handleWechatLogin}
                    disabled={loading}
                  >
                    <WechatOutlined />
                    <span>{t('login.loginWithWechat')}</span>
                  </button>
                </div>
              )}

              {/* 忘记密码表单 */}
              {mode === 'forgot' && (
                <>
                  <Form.Item
                    name="phone"
                    rules={[
                      { required: true, message: t('login.phoneRequired') },
                      { pattern: /^1[3-9]\d{9}$/, message: t('login.invalidPhone') }
                    ]}
                  >
                    <Input
                      prefix={<MobileOutlined />}
                      placeholder={t('login.phonePlaceholder')}
                      size="large"
                      disabled={codeSent}
                      maxLength={11}
                    />
                  </Form.Item>
                  <Form.Item
                    name="code"
                    rules={[{ required: true, message: t('login.codeRequired') }]}
                  >
                    <Input
                      prefix={<SafetyCertificateOutlined />}
                      placeholder={t('login.codePlaceholder')}
                      size="large"
                      maxLength={6}
                      suffix={
                        <button
                          type="button"
                          className="cn-send-code-btn"
                          disabled={countdown > 0 || !form.getFieldValue('phone')}
                          onClick={() => handleSendForgotCode(form.getFieldValue('phone'))}
                        >
                          {countdown > 0 ? `${countdown}s` : t('login.sendCode')}
                        </button>
                      }
                    />
                  </Form.Item>
                  <Form.Item
                    name="newPassword"
                    rules={[
                      { required: true, message: t('login.passwordRequired') },
                      { min: 8, message: t('login.passwordMinLength') },
                      { pattern: /[A-Z]/, message: t('login.passwordNeedUppercase') },
                      { pattern: /[a-z]/, message: t('login.passwordNeedLowercase') },
                      { pattern: /[0-9]/, message: t('login.passwordNeedNumber') },
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder={t('login.newPassword')}
                      size="large"
                    />
                  </Form.Item>
                  <Form.Item
                    name="confirmPassword"
                    rules={[
                      { required: true, message: t('login.confirmPasswordRequired') },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('newPassword') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error(t('login.passwordMismatch')));
                        },
                      }),
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder={t('login.confirmPassword')}
                      size="large"
                    />
                  </Form.Item>
                </>
              )}

              {/* 提交按钮 */}
              {mode !== 'forgot' && activeTab !== 'wechat' && (
                <Form.Item className="cn-submit-item">
                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    block
                    loading={loading}
                    disabled={loading || loginSuccessful}
                    className="cn-login-button"
                  >
                    {loading
                      ? t('login.loggingIn')
                      : mode === 'email-login' || mode === 'phone-login'
                        ? t('login.loginButton')
                        : t('login.signUp')}
                  </Button>
                </Form.Item>
              )}

              {mode === 'forgot' && (
                <Form.Item className="cn-submit-item">
                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    block
                    loading={loading}
                    className="cn-login-button"
                  >
                    {t('login.resetPassword')}
                  </Button>
                </Form.Item>
              )}

              {/* 错误提示 */}
              {lastError && !loading && (
                <div className="cn-error-message">{lastError}</div>
              )}

              {/* 链接按钮 */}
              <div className="cn-link-row">
                {mode === 'forgot' ? (
                  <button
                    type="button"
                    className="cn-link-button"
                    onClick={() => handleModeChange('email-login')}
                  >
                    <CheckCircleOutlined />
                    <span>{t('login.backToLogin')}</span>
                  </button>
                ) : (
                  <>
                    {/* 忘记密码 */}
                    {mode === 'email-login' && (
                      <button
                        type="button"
                        className="cn-link-button"
                        onClick={() => handleModeChange('forgot')}
                      >
                        {t('login.forgotPassword')}
                      </button>
                    )}

                    {/* 切换登录/注册 */}
                    <button
                      type="button"
                      className="cn-link-button cn-link-primary"
                      onClick={() => handleModeChange(
                        mode === 'email-login' ? 'email-signup' :
                        mode === 'email-signup' ? 'email-login' :
                        mode === 'phone-login' ? 'phone-signup' : 'phone-login'
                      )}
                    >
                      {mode === 'email-signup' || mode === 'phone-signup'
                        ? t('login.backToLogin')
                        : t('login.signUp')}
                    </button>
                  </>
                )}
              </div>
            </Form>
          </>
        )}
      </div>
    </div>
  );
};

export default LoginCN;
