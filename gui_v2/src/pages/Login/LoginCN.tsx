/**
 * CN 版本登录页面
 * 使用腾讯云 CloudBase 认证
 * 左右分栏布局：左侧品牌区，右侧表单区
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Select, Typography, App, Spin, Divider, Modal } from 'antd';
import { UserOutlined, LockOutlined, LoadingOutlined, MobileOutlined, WechatOutlined, MailOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse } from '../../services/ipc/api';
import { get_ipc_api } from '../../services/ipc_api';
import { userStorageManager, type LoginSession } from '../../services/storage/UserStorageManager';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import { useInitializationProgress, forceCleanupInitializationProgress } from '../../hooks/useInitializationProgress';
import { tokenRefreshService } from '../../services/auth/tokenRefreshService';
import { cloudbaseAuth } from '../../services/auth/cloudbaseAuth';
import LoadingProgress from '../../components/LoadingProgress/LoadingProgress';
import logo from '../../assets/logoWhite22.png';
import './Login.css';

const { Title, Text } = Typography;

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

  const lastLoginAttemptRef = useRef<number>(0);
  const LOGIN_DEBOUNCE_MS = 3000;

  const { progress: initProgress } = useInitializationProgress(loading || showInitProgress);

  // 初始化
  useEffect(() => {
    forceCleanupInitializationProgress();
  }, []);

  // 初始化 CloudBase
  useEffect(() => {
    const envId = import.meta.env.VITE_CLOUDBASE_ENV_ID;
    if (envId) {
      cloudbaseAuth.initialize({ envId });
    }
  }, []);

  // 导航逻辑
  useEffect(() => {
    if (!initProgress?.ui_ready) return;
    if (!loginSuccessful) return;
    if (hasNavigated) return;

    setHasNavigated(true);
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

    try {
      const result = await cloudbaseAuth.sendPhoneCode(phone, 'login');
      if (result.success) {
        setCodeSent(true);
        setCountdown(60);
        messageApi.success(t('login.codeSent'));
      } else {
        messageApi.error(result.error || t('login.codeSendFailed'));
      }
    } catch (error) {
      messageApi.error(String(error));
    }
  }, [countdown, messageApi, t]);

  // 手机号登录
  const handlePhoneLogin = useCallback(async (phone: string, code: string) => {
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithPhone(phone, code);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.success'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
        return true;
      }

      messageApi.error(result.error || t('login.failed'));
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [saveLoginSession, messageApi, t]);

  // 邮箱登录
  const handleEmailLogin = useCallback(async (email: string, password: string, role: string) => {
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
      setLoginProgress('idle');
      return false;
    } catch (error) {
      messageApi.error(String(error));
      setLoginProgress('idle');
      return false;
    }
  }, [saveLoginSession, messageApi, t]);

  // 发送密码重置验证码
  const handleSendForgotCode = useCallback(async (phone: string) => {
    if (countdown > 0) return;

    try {
      const result = await cloudbaseAuth.sendPasswordResetCode(phone);
      if (result.success) {
        setCodeSent(true);
        setCountdown(60);
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
  }, [countdown, messageApi, t]);

  // 重置密码
  const handleResetPassword = useCallback(async (phone: string, code: string, newPassword: string) => {
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.resetPasswordWithPhone(phone, code, newPassword);

      if (result.success) {
        messageApi.success(t('login.forgotSuccess'));
        setMode('login');
        form.resetFields();
        setCodeSent(false);
      } else {
        messageApi.error(result.error || t('login.forgotResetError'));
      }
    } catch (error) {
      messageApi.error(String(error));
    } finally {
      setLoginProgress('idle');
    }
  }, [messageApi, t, form]);

  // 手机号注册
  const handlePhoneSignup = useCallback(async (phone: string, code: string) => {
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.signupWithPhone(phone, code);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setLoginProgress('success');
        saveLoginSession(token, userInfo, 'Commander', 'password');
        messageApi.success(t('login.signupSuccess'));
        setLoginSuccessful(true);
        setLoginProgress('redirecting');
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
  }, [saveLoginSession, messageApi, t]);

  // 邮箱注册
  const handleSignup = useCallback(async (email: string, password: string) => {
    setLoading(true);

    try {
      const result = await cloudbaseAuth.signupWithEmail(email, password);

      if (result.success) {
        Modal.success({
          title: t('login.signupSuccess'),
          content: t('login.signupSuccessMessage'),
          onOk: () => setMode('login')
        });
      } else {
        messageApi.error(result.error || t('login.failed'));
      }
    } catch (error) {
      messageApi.error(String(error));
    } finally {
      setLoading(false);
    }
  }, [messageApi, t]);

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
    setLastError(null);

    try {
      switch (mode) {
        case 'login':
          await handleEmailLogin(values.username, values.password, values.role);
          break;
        case 'signup':
          if (values.password !== values.confirmPassword) {
            messageApi.error(t('login.passwordMismatch'));
            setLoading(false);
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
    } finally {
      if (mode !== 'login' || !loginSuccessful) {
        setLoading(false);
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
  }, [form]);

  // 表单标题（根据 mode）
  const getHeaderText = () => {
    switch (mode) {
      case 'login': return { title: t('login.welcomeBack') || '欢迎回来', subtitle: t('login.loginSubtitle') || '请登录您的账号' };
      case 'signup': return { title: t('login.createAccount') || '创建账号', subtitle: t('login.signupSubtitle') || '填写信息完成注册' };
      case 'phone-login': return { title: t('login.phoneLogin') || '手机登录', subtitle: t('login.phoneLoginSubtitle') || '使用手机号快捷登录' };
      case 'phone-signup': return { title: t('login.phoneSignup') || '手机注册', subtitle: t('login.phoneSignupSubtitle') || '使用手机号注册新账号' };
      case 'forgot': return { title: t('login.forgotPassword') || '找回密码', subtitle: t('login.forgotSubtitle') || '通过手机验证码重置密码' };
      default: return { title: t('login.title'), subtitle: t('login.subtitle') };
    }
  };

  // 渲染左侧品牌区
  const renderBrandPanel = () => (
    <div className="login-brand-panel">
      <div className="brand-logo">
        <img src={logo} alt={t('login.logoAlt')} className="brand-logo-image" />
      </div>
      <div className="brand-title">{t('login.brandName') || 'eCan.ai'}</div>
      <div className="brand-tagline">{t('login.brandTagline') || '智能协同 · 未来已来'}</div>

      <ul className="brand-features">
        <li>
          <span className="brand-feature-dot" />
          <span>{t('login.brandFeature1') || '多端协同，云端同步'}</span>
        </li>
        <li>
          <span className="brand-feature-dot" />
          <span>{t('login.brandFeature2') || 'AI 驱动，智能助理'}</span>
        </li>
        <li>
          <span className="brand-feature-dot" />
          <span>{t('login.brandFeature3') || '安全可靠，企业级加密'}</span>
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
              className={`auth-mode-btn ${mode === 'phone-login' ? 'active' : ''}`}
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
    const handleWechatClick = () => {
      const wechatAppId = (import.meta as any).env?.VITE_WECHAT_APP_ID;
      const redirectUri = encodeURIComponent(window.location.origin + '/#/auth/wechat-callback');
      const state = Math.random().toString(36).slice(2);
      sessionStorage.setItem('wechat_oauth_state', state);

      if (!wechatAppId) {
        messageApi.info(t('login.wechatComingSoon'));
        return;
      }

      const wechatUrl =
        `https://open.weixin.qq.com/connect/oauth2/authorize?appid=${wechatAppId}` +
        `&redirect_uri=${redirectUri}&response_type=code&scope=snsapi_userinfo&state=${state}#wechat_redirect`;
      window.location.href = wechatUrl;
    };

    return (
      <>
        <Divider plain>{t('login.or')}</Divider>
        <button
          type="button"
          className="wechat-login-btn"
          onClick={handleWechatClick}
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
            <Spin indicator={<LoadingOutlined style={{ fontSize: 40, color: '#1890ff' }} spin />} size="large" />
            <div className="loading-text">{t('login.verifying')}</div>
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
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => handleModeChange(mode === 'signup' ? 'login' : 'signup')}
                      >
                        {mode === 'signup' ? t('login.backToLogin') : t('login.signUp')}
                      </button>
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
