/**
 * CN 版本登录页面
 * 使用腾讯云 CloudBase 认证
 * 左右分栏布局：左侧品牌区，右侧表单区
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Select, App, Divider, Modal } from 'antd';
import { UserOutlined, LockOutlined, MobileOutlined, WechatOutlined, MailOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
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

type AuthMode = 'login' | 'signup' | 'forgot' | 'phone-login' | 'phone-signup';

const LoginCN: React.FC = () => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { config: appConfig } = useAppConfig();
  const [form] = Form.useForm<LoginFormValues>();

  // State
  const [mode, setMode] = useState<AuthMode>('login');
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

  // 初始化 CloudBase —— 从 /api/config（后端 auth_config.yml）读取 env_id
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

  // 监听 URL 参数（微信回调时会带 code 参数）
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, '').split('?')[1] || '');
    const code = urlParams.get('code') || hashParams.get('code');
    const state = urlParams.get('state') || hashParams.get('state');
    const savedState = sessionStorage.getItem('wx_state');

    // 如果 URL 中有 code 且 state 校验通过（CloudBase 托管模式回调）
    if (code && state && savedState && state === savedState) {
      // 清除 URL 参数和 sessionStorage
      window.history.replaceState({}, '', window.location.pathname);
      sessionStorage.removeItem('wx_state');

      // 调 CloudBase grantProviderToken + signInWithProvider
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

          // 用 code 换 provider_token
          const { provider_token } = await auth.grantProviderToken({
            provider_id: 'wx_open',
            provider_redirect_uri: window.location.origin,
            provider_code: code,
          });

          // 用 provider_token 完成登录
          let loginResult;
          try {
            loginResult = await auth.signInWithProvider({ provider_token });
          } catch (e: any) {
            // 首次登录可能 not_found，需要先注册并绑定
            if (e?.error === 'not_found') {
              messageApi.warning('请先注册账号，然后再次扫码登录');
              setLoginProgress('idle');
              setShowInitProgress(false);
              return;
            }
            throw e;
          }

          // 拿到 CloudBase token，构造 userInfo 并走和 Intl 一致的登录成功流程
          const accessToken = await auth.getAccessToken();
          const cbUserInfo: any = loginResult?.user || {};

          // 优先用 email 做 user_identifier（如果 CloudBase 给了邮箱），否则用 uuid
          const userIdentifier =
            cbUserInfo.email || cbUserInfo.uuid || `wechat_${cbUserInfo.openId || ''}`;

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

          // Step 1: 把 access_token 交给后端，让后端跑与 Intl password
          // 登录完全一致的登录后续处理（AuthManager 灌入 token → MainWindow
          // 启动 → token_manager → onboarding）。后端会返回 IPC session
          // token / session_id 以便前端后续请求。
          const finalizeResult = await cloudbaseAuth.finalizeSession({
            access_token: accessToken || '',
            refresh_token: accessToken || '',  // CloudBase Web v3 hosted page 不返 refresh，由后端 fallback
            expires_in: 7200,
            user_identifier: userIdentifier,
            user_info: userInfo,
            role: 'Commander',
            lang: i18n.language,
          });

          if (!finalizeResult.success) {
            throw new Error(finalizeResult.error || 'Finalize session failed');
          }

          // Step 2: 用后端返回的 IPC token / user_info / session_id 写
          // 本地会话，与密码登录 saveLoginSession 完全一致。
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
          // 跳转逻辑由 useEffect 监听 initProgress.ui_ready 后自动触发
        } catch (err: any) {
          console.error('[WeChat Callback] Error:', err);
          setLoginProgress('idle');
          setShowInitProgress(false);
          messageApi.error(err?.message || '微信登录失败');
        }
      })();
    }
  }, [navigate, messageApi, t, appConfig?.auth?.cloudbase_env_id]);

  const ensureCloudbase = useCallback((): boolean => {
    if (!appConfig?.auth?.cloudbase_env_id) {
      messageApi.error(t('login.cloudbaseNotConfigured'));
      return false;
    }
    return true;
  }, [appConfig?.auth?.cloudbase_env_id, messageApi, t]);

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
        // 保存 verification_id 用于后续登录
        if (result.verificationId) {
          setVerificationId(result.verificationId);
        }
        messageApi.success(t('login.codeSent'));
        // 开发模式显示验证码
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
        // 清除 verification_id
        setVerificationId(null);
        return true;
      }

      messageApi.error(result.error || t('login.failed'));
      setLastError(result.error || t('login.failed'));
      console.error('[LoginCN] Phone login failed:', result);
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
      console.error('[LoginCN] Email login failed:', result);
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
        setMode('login');
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

  // 邮箱注册（两步：先发验证码返回 verification_id，用户输入验证码后完成注册）
  const handleSignup = useCallback(async (email: string, password: string) => {
    if (!ensureCloudbase()) {
      setLoading(false);
      return;
    }

    try {
      // 如果用户还没输入验证码：第一步发验证码
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
            // 没有 verification_id（已注册）直接切换回登录
            messageApi.info(t('login.emailAlreadyRegistered') || '该邮箱已注册，请直接登录');
            setMode('login');
          }
        } else {
          messageApi.error(result.error || t('login.failed'));
        }
        return;
      }

      // 第二步：输入验证码完成注册
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
    // 立即显示 Login 进度 UI，保持 enabled=true 直到 navigate effect 触发
    // (与 intl Login.tsx handleSubmit 保持一致，避免 subscriber 在 fetch
    // 飞行期间被 unsubscribe 的 race condition)
    setShowInitProgress(true);

    let loginAttempted = false;

    try {
      switch (mode) {
        case 'login':
          loginAttempted = true;
          await handleEmailLogin(values.username, values.password, values.role);
          // 不要在这里 reset loading — 让 navigate effect 处理
          return;
        case 'signup':
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

      // Login 失败时重置进度 UI（与 intl Login.tsx handleSubmit catch 块对齐）
      if (mode === 'login' && loginAttempted) {
        setLoading(false);
        setShowInitProgress(false);
      }
    } finally {
      // 非 login 模式 或 login 未尝试过 才 reset loading
      // (intl 模式：login 成功的 reset 由 navigate effect 统一处理)
      if (mode !== 'login' || !loginAttempted) {
        setLoading(false);
        setShowInitProgress(false);
      }
    }
  }, [loading, loginSuccessful, mode, handleEmailLogin, handleSignup, handlePhoneLogin, handlePhoneSignup, handleResetPassword, messageApi, t]);

  // 切换模式
  const handleModeChange = useCallback((newMode: AuthMode) => {
    setMode(newMode);
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

  // 表单标题（根据 mode）
  const getHeaderText = () => {
    switch (mode) {
      case 'login': return { title: t('login.welcomeBack'), subtitle: t('login.loginSubtitle') };
      case 'signup': return { title: t('login.createAccount'), subtitle: t('login.signupSubtitle') };
      case 'phone-login': return { title: t('login.phoneLogin'), subtitle: t('login.phoneLoginSubtitle') };
      case 'phone-signup': return { title: t('login.phoneSignup'), subtitle: t('login.phoneSignupSubtitle') };
      case 'forgot': return { title: t('login.forgotPassword'), subtitle: t('login.forgotSubtitle') };
      default: return { title: t('login.title'), subtitle: t('login.subtitle') };
    }
  };

  // 渲染左侧品牌区
  const renderBrandPanel = () => (
    <div className="login-brand-panel">
      <div className="brand-logo">
        <img src={logo} alt={t('login.logoAlt')} className="brand-logo-image" />
      </div>
      <div className="brand-title">{t('login.brandName')}</div>
      <div className="brand-tagline">{t('login.brandTagline')}</div>

      <ul className="brand-features">
        <li>
          <span className="brand-feature-dot" />
          <span>{t('login.brandFeature1')}</span>
        </li>
        <li>
          <span className="brand-feature-dot" />
          <span>{t('login.brandFeature2')}</span>
        </li>
        <li>
          <span className="brand-feature-dot" />
          <span>{t('login.brandFeature3')}</span>
        </li>
      </ul>

      <div className="brand-footer">
        © {new Date().getFullYear()} eCan.ai
      </div>
    </div>
  );

  // 渲染顶部：Tab + 标题
  const renderHeader = () => {
    const { title, subtitle } = getHeaderText();
    return (
      <div className="login-header">
        {mode !== 'forgot' && (
          <div className="auth-mode-switch">
            <button
              type="button"
              className={`auth-mode-btn ${mode === 'login' ? 'active' : ''}`}
              onClick={() => handleModeChange('login')}
            >
              <MailOutlined /> {t('login.emailLogin')}
            </button>
            <button
              type="button"
              className={`auth-mode-btn ${(mode === 'phone-login' || mode === 'phone-signup') ? 'active' : ''}`}
              onClick={() => handleModeChange('phone-login')}
            >
              <MobileOutlined /> {t('login.phoneLogin')}
            </button>
          </div>
        )}
        <h1 className="login-title">{title}</h1>
        <p className="login-subtitle">{subtitle}</p>
      </div>
    );
  };

  // 渲染邮箱登录表单
  const renderEmailForm = () => (
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
      {mode === 'login' && (
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
      {mode === 'signup' && (
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
      {mode === 'login' && (
        <Form.Item name="role" rules={[{ required: true }]}>
          <Select size="large">
            <Select.Option value="Commander">{t('roles.commander')}</Select.Option>
            <Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
            <Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
          </Select>
        </Form.Item>
      )}
    </>
  );

  // 渲染手机号登录表单
  const renderPhoneForm = () => (
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
              className="send-code-btn"
              disabled={countdown > 0}
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
  );

  // 渲染微信登录
  const renderWechatLogin = () => {
    // 微信登录未配置时隐藏按钮
    if (!wechatAvailable) {
      return null;
    }

    // 启动 CloudBase 托管登录页微信登录
    const startWechatLogin = async () => {
      try {
        // 获取当前页面 URL，登录完成后跳转回来
        const redirectUri = `${window.location.origin}/login`;
        const resp = await cloudbaseAuth.loginWithCloudBaseWechat(redirectUri);
        console.log('[WeChat H5] Response:', resp);

        if (!resp.success) {
          messageApi.error(resp.error || 'Failed to start WeChat login');
        }
        // 如果成功，前端会跳转到 CloudBase 登录页
      } catch (error) {
        console.error('[WeChat H5] Error:', error);
        messageApi.error(String(error));
      }
    };

    return (
      <>
        <Divider plain>{t('login.or')}</Divider>
        <button
          type="button"
          className="wechat-login-btn"
          onClick={startWechatLogin}
        >
          <WechatOutlined />
          <span>{t('login.loginWithWechat')}</span>
        </button>
      </>
    );
  };

  // 渲染忘记密码表单
  const renderForgotForm = () => (
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
              className="send-code-btn"
              disabled={countdown > 0}
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
  );

  return (
    <div className="login-container">
      {/* 语言选择器 - 右上角 */}
      <div className="language-selector">
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

      <LoadingProgress
        visible={loading || showInitProgress}
        progress={initProgress}
        title={loginProgress === 'redirecting' ? t('login.redirectingToMain') : undefined}
        onComplete={() => {
          setLoading(false);
          setShowInitProgress(false);
        }}
      />

      <div className="login-card">
        {loading ? (
          <div className="loading-container">
            <div className="loading-text">
              {loginProgress === 'redirecting'
                ? t('login.redirectingToMain')
                : loginProgress === 'success'
                  ? t('login.success')
                  : t('login.verifying')}
            </div>
          </div>
        ) : (
          <div className="login-card-inner">
            {/* 左侧品牌区 */}
            {renderBrandPanel()}

            {/* 右侧表单区 */}
            <div className="login-form-panel">
              {renderHeader()}

              <Form
                form={form}
                name="login"
                onFinish={handleSubmit}
                layout="vertical"
                requiredMark={false}
                initialValues={{ role: 'Commander' }}
                className="login-form"
              >
                {mode === 'login' || mode === 'signup'
                  ? renderEmailForm()
                  : mode === 'forgot'
                    ? renderForgotForm()
                    : renderPhoneForm()}

                {(mode === 'login' || mode === 'signup') && renderWechatLogin()}

                <Form.Item className="submit-item">
                  <Button
                    type="primary"
                    htmlType="submit"
                    size="large"
                    block
                    loading={loading}
                    disabled={loading || loginSuccessful}
                    className="login-button"
                  >
                    {loading
                      ? t('login.loggingIn')
                      : mode === 'login'
                        ? t('login.loginButton')
                        : mode === 'phone-login'
                          ? t('login.loginButton')
                          : mode === 'phone-signup'
                            ? t('login.signUp')
                            : mode === 'forgot'
                              ? t('login.resetPassword')
                              : t('login.signUp')}
                  </Button>
                </Form.Item>

                {lastError && !loading && (
                  <div className="error-message">{lastError}</div>
                )}

                <div className="link-row">
                  {mode === 'forgot' ? (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => handleModeChange('login')}
                    >
                      {t('login.backToLogin')}
                    </button>
                  ) : (
                    <>
                      {mode === 'phone-login' || mode === 'phone-signup' ? (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => handleModeChange(mode === 'phone-signup' ? 'phone-login' : 'phone-signup')}
                        >
                          {mode === 'phone-signup' ? t('login.backToLogin') : t('login.signUp')}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => handleModeChange(mode === 'signup' ? 'login' : 'signup')}
                        >
                          {mode === 'signup' ? t('login.backToLogin') : t('login.signUp')}
                        </button>
                      )}
                      {mode === 'login' && (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => handleModeChange('forgot')}
                        >
                          {t('login.forgotPassword')}
                        </button>
                      )}
                    </>
                  )}
                </div>
              </Form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LoginCN;
