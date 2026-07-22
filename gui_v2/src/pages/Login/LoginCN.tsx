/**
 * CN 版本登录页面
 * 使用腾讯云 CloudBase 认证
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Select, Typography, App, Modal, Spin, Space, Divider } from 'antd';
import { UserOutlined, LockOutlined, LoadingOutlined, MobileOutlined, WechatOutlined, MailOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse, IPCAPI } from '../../services/ipc/api';
import { get_ipc_api } from '../../services/ipc_api';
import { userStorageManager, type LoginSession } from '../../services/storage/UserStorageManager';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import { useInitializationProgress, forceCleanupInitializationProgress } from '../../hooks/useInitializationProgress';
import { tokenRefreshService } from '../../services/auth/tokenRefreshService';
import { cloudbaseAuth } from '../../services/auth/cloudbaseAuth';
import LoadingProgress from '../../components/LoadingProgress/LoadingProgress';
import { isWebPlatform } from '../../config/platform';
import logo from '../../assets/logoWhite22.png';
import wechatIcon from '../../assets/wechat_icon.png';
import './Login.css';

const { Title, Text } = Typography;

interface LoginFormValues {
  username: string;
  password: string;
  confirmPassword?: string;
  role: string;
  phone?: string;
  code?: string;
}

type AuthMode = 'login' | 'signup' | 'forgot' | 'phone-login';

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
  const [forgotPasswordLoading, setForgotPasswordLoading] = useState(false);
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
    loginType: string = 'email'
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
        saveLoginSession(token, userInfo, 'Commander', 'phone');
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
        saveLoginSession(token, userInfo, role, 'email');
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
  }, [loading, loginSuccessful, mode, handleEmailLogin, handleSignup, handlePhoneLogin, messageApi, t]);

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

  // 渲染登录模式切换
  const renderModeSwitch = () => (
    <div className="auth-mode-switch">
      <Button
        type="text"
        className={mode === 'login' ? 'active' : ''}
        onClick={() => handleModeChange('login')}
      >
        <MailOutlined /> {t('login.emailLogin')}
      </Button>
      <Button
        type="text"
        className={mode === 'phone-login' ? 'active' : ''}
        onClick={() => handleModeChange('phone-login')}
      >
        <MobileOutlined /> {t('login.phoneLogin')}
      </Button>
    </div>
  );

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
          className="form-input"
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
            className="form-input"
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
              className="form-input"
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
              className="form-input"
            />
          </Form.Item>
        </>
      )}
      {mode === 'login' && (
        <Form.Item name="role" rules={[{ required: true }]}>
          <Select size="large" className="form-input">
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
          className="form-input"
          disabled={codeSent}
        />
      </Form.Item>
      <Form.Item
        name="code"
        rules={[{ required: true, message: t('login.codeRequired') }]}
      >
        <Input
          placeholder={t('login.codePlaceholder')}
          size="large"
          className="form-input"
          suffix={
            <Button
              type="link"
              size="small"
              disabled={countdown > 0}
              onClick={() => handleSendCode(form.getFieldValue('phone'))}
            >
              {countdown > 0 ? `${countdown}s` : t('login.sendCode')}
            </Button>
          }
        />
      </Form.Item>
      <Form.Item name="role" rules={[{ required: true }]}>
        <Select size="large" className="form-input">
          <Select.Option value="Commander">{t('roles.commander')}</Select.Option>
          <Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
          <Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
        </Select>
      </Form.Item>
    </>
  );

  // 渲染微信登录
  const renderWechatLogin = () => (
    <>
      <Divider plain>{t('login.or')}</Divider>
      <Button
        block
        size="large"
        icon={<WechatOutlined />}
        className="wechat-login-button"
        onClick={() => {
          // TODO: 实现微信登录
          messageApi.info(t('login.wechatComingSoon'));
        }}
      >
        {t('login.loginWithWechat')}
      </Button>
    </>
  );

  return (
    <div className="login-container">
      <div className="login-decoration" />
      <div className="background-animation" />

      <div className="language-selector">
        <Select
          value={i18n.language}
          style={{ width: 120 }}
          onChange={handleLanguageChange}
          styles={{
            popup: {
              root: { backgroundColor: '#2d2d2d' }
            }
          }}
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

      <Card className="login-card">
        {loading ? (
          <div className="loading-container">
            <Spin indicator={<LoadingOutlined style={{ fontSize: 48, color: '#1890ff' }} spin />} size="large" />
            <div className="loading-text">{t('login.verifying')}</div>
          </div>
        ) : (
          <>
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
              <div className="logo-container">
                <img src={logo} alt={t('login.logoAlt')} className="logo-image" />
              </div>
              <Title level={2} style={{ color: '#fff', margin: 0 }}>{t('login.title')}</Title>
              <Text style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{t('login.subtitle')}</Text>
            </div>

            {/* 登录模式切换 */}
            {renderModeSwitch()}

            <Form
              form={form}
              name="login"
              onFinish={handleSubmit}
              layout="vertical"
              requiredMark={false}
              initialValues={{ role: 'Commander' }}
            >
              {mode === 'login' || mode === 'signup' ? renderEmailForm() : renderPhoneForm()}

              {(mode === 'login' || mode === 'signup') && renderWechatLogin()}

              <Form.Item>
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
                        : t('login.signUp')
                  }
                </Button>
              </Form.Item>

              {lastError && !loading && (
                <div className="error-message">
                  {lastError}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
                <Button
                  type="link"
                  onClick={() => handleModeChange(mode === 'signup' ? 'login' : 'signup')}
                  className="link-button"
                >
                  {mode === 'signup' ? t('login.backToLogin') : t('login.signUp')}
                </Button>
                {mode === 'login' && (
                  <Button
                    type="link"
                    onClick={() => handleModeChange('forgot')}
                    className="link-button"
                  >
                    {t('login.forgotPassword')}
                  </Button>
                )}
              </div>
            </Form>
          </>
        )}
      </Card>
    </div>
  );
};

export default LoginCN;
