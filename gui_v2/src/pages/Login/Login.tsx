import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Select, Typography, App, Modal, Spin } from 'antd';
import { UserOutlined, LockOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse, IPCAPI, ipcClient } from '../../services/ipc';
import { get_ipc_api } from '../../services/ipc_api';
import { userStorageManager, type LoginSession } from '../../services/storage/UserStorageManager';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import { useInitializationProgress } from '../../hooks/useInitializationProgress';
import LoadingProgress from '../../components/LoadingProgress/LoadingProgress';
import logo from '../../assets/logoWhite22.png';
import googleIcon from '../../assets/Google_Icons.png';
import appleIcon from '../../assets/Apple_Icon3.png';
import './Login.css';

const { Title, Text } = Typography;

interface LoginFormValues {
	username: string;
	password: string;
	confirmPassword?: string;
	role: string;
	confirmCode?: string;
	newPassword?: string;
}

type AuthMode = 'login' | 'signup' | 'forgot';

const Login: React.FC = () => {
	// Hooks
	const navigate = useNavigate();
	const { t, i18n } = useTranslation();
	const { message: messageApi } = App.useApp();
	const [form] = Form.useForm<LoginFormValues>();

	// State
	const [mode, setMode] = useState<AuthMode>('login');
	const [loading, setLoading] = useState(false);
	const [showInitProgress, setShowInitProgress] = useState(false);
	// 新增Local state 控制Validate码Send
	const [codeSent, setCodeSent] = useState(false);
	// LoginSuccessStatus，防止ButtonStatusReset
	const [loginSuccessful, setLoginSuccessful] = useState(false);
	const [hasNavigated, setHasNavigated] = useState(false);
	// 忘记PasswordOperation的loadingStatus
	const [forgotPasswordLoading, setForgotPasswordLoading] = useState(false);
	// Login进度Status
	const [loginProgress, setLoginProgress] = useState<'idle' | 'authenticating' | 'success' | 'redirecting'>('idle');
	// GoogleLogin进度Status
	const [googleLoginProgress, setGoogleLoginProgress] = useState<'idle' | 'opening' | 'authenticating' | 'success' | 'redirecting'>('idle');
	// ErrorStatus
	const [lastError, setLastError] = useState<string | null>(null);

	// Poll backend initialization progress during login
	const { progress: initProgress } = useInitializationProgress(loading || showInitProgress);

	// 标准跳转逻辑：仅当系统初始化就绪且登录成功时才跳转到主页面
	useEffect(() => {
		if (!initProgress?.ui_ready) return;
		if (!loginSuccessful) return;
		if (hasNavigated) return;

		setHasNavigated(true);
		console.log('[Login] ui_ready && loginSuccessful, navigating to main page');
		setLoading(false);
		setShowInitProgress(false);
		navigate('/agents');
	}, [initProgress, loginSuccessful, hasNavigated, navigate]);

	// Initialize IPC API and load login info and language preference
	useEffect(() => {
		const initialize = async () => {
			try {
				// SettingsTimeout，避免长Time等待
				const timeoutPromise = new Promise((_, reject) => {
					setTimeout(() => reject(new Error('IPC initialization timeout')), 5000);
				});

				// LoadLoginInformation
				const api = get_ipc_api();
				if (!api) {
					console.warn('[Login] IPC API not available, skipping login info load');
					return;
				}

				// Load login info (includes language and theme preferences)
				const response = await Promise.race([
					api.getLastLoginInfo(),
					timeoutPromise
				]) as APIResponse<any>;

				console.log('[Login] Last login info', response.data);
				if (response?.data?.last_login) {
					const { username, password, machine_role, language } = response.data.last_login;
					console.log('last_login', response.data.last_login);

					// Apply saved language preference if available
					if (language && i18n.language !== language) {
						console.log('[Login] Applying saved language:', language);
						await i18n.changeLanguage(language);
						localStorage.setItem('i18nextLng', language);
					}

					// TODO: Theme preference will be handled by ThemeContext

					// Update form with login credentials
					// Use default role 'Commander' if machine_role is not available
					updateFormWithRole(username, password, machine_role || 'Commander');
				}
			} catch (error) {
				console.warn('[Login] Failed to load last login info:', error);
				// 不阻塞LoginPageDisplay，继续正常流程
			}
		};

		// DelayInitialize，让Page先Render
		const timer = setTimeout(initialize, 100);
		return () => clearTimeout(timer);
	}, []); // 只在ComponentMount时Execute一次

	// Listen语言变化，UpdateRoleSelect框的Display
	useEffect(() => {
		const currentRole = form.getFieldValue('role');
		if (currentRole) {
			updateFormWithRole(
				form.getFieldValue('username'),
				form.getFieldValue('password'),
				currentRole
			);
		}
	}, [i18n.language]);

	// UpdateFormValue的HelperFunction
	const updateFormWithRole = (username: string, password: string, role: string) => {
		form.setFieldsValue({
			username,
			password,
			role: role
		});
	};

	// Handlers
	const handleLanguageChange = useCallback(async (value: string) => {
		if (i18n.language !== value) {
			await i18n.changeLanguage(value);
			localStorage.setItem('i18nextLng', value);
			
			// Save language preference to uli.json via IPC
			try {
				const api = get_ipc_api();
				if (api) {
					const response = await api.updateUserPreferences(value);
					if (response?.success) {
						console.log('[Login] Language preference saved to uli.json:', value);
					} else {
						console.warn('[Login] Failed to save language preference:', response?.error);
					}
				}
			} catch (error) {
				console.error('[Login] Error saving language preference:', error);
			}
		}
	}, [i18n]);

	const handleModeChange = useCallback((newMode: AuthMode) => {
		setMode(newMode);
		form.resetFields();
		// Reset all loading states when switching modes
		setLoading(false);
		setLoginSuccessful(false);
		setHasNavigated(false);
		setForgotPasswordLoading(false);
		setCodeSent(false);
		setShowInitProgress(false);
		setLoginProgress('idle');
		setGoogleLoginProgress('idle');
		setLastError(null);
	}, [form]);

	const handleLogin = async (values: LoginFormValues, api: IPCAPI) => {
		try {
			setLoginProgress('authenticating');

			// Add timeout for login request
			const loginPromise = api.login(values.username, values.password, values.role, i18n.language);
			const timeoutPromise = new Promise<never>((_, reject) => {
				setTimeout(() => reject(new Error('Login timeout after 30 seconds')), 30000);
			});

			const response: APIResponse<any> = await Promise.race([loginPromise, timeoutPromise]);

			if (response.success && response.data) {
				console.log('[Login] Login successful', response.data);
				setLoginProgress('success');

				const { token, user_info, session_id } = response.data;
				const username = user_info?.username || values.username;

				// 使用统一的UserStorage管理器，保存完整的用户信息
				const loginSession: LoginSession = {
					token,
					userInfo: {
						username,
						email: user_info?.email || username,
						role: user_info?.role || values.role,
						name: user_info?.name || '',
						given_name: user_info?.given_name || '',
						family_name: user_info?.family_name || '',
						picture: user_info?.picture || '',
						email_verified: user_info?.email_verified ?? true,
						login_type: user_info?.login_type || 'password'
					},
					loginTime: Date.now()
				};

				if (session_id) {
					loginSession.sessionId = session_id;
					userStorageManager.setSessionId(session_id);
					ipcClient.setSessionId(session_id);
				}

				userStorageManager.saveLoginSession(loginSession);
				// LoginSuccess后EnabledPageRefreshListen
				pageRefreshManager.enable();

				messageApi.success(t('login.success'));
				setLoginSuccessful(true);

				// LoginSuccess，Settings跳转Status（showInitProgress已在handleSubmit中Settings）
				setLoginProgress('redirecting');
			} else {
				console.error('Login failed', response.error);
				setLoginProgress('idle');
				messageApi.error(response.error?.message || t('login.failed'));
				throw new Error(response.error?.message || 'Login failed');
			}
		} catch (error) {
			console.error('Login error:', error);
			setLoginProgress('idle');
			// 不在这里DisplayErrorMessage，让handleSubmit统一Process
			throw error; // Re-throw to be handled by handleSubmit
		}
	};

	const handleSignup = async (values: LoginFormValues, api: IPCAPI) => {
		if (values.password !== values.confirmPassword) {
			messageApi.error(t('login.passwordMismatch'));
			return;
		}
		const response = await api.signup(values.username, values.password, i18n.language);
		if (response.success) {
			Modal.success({
				title: t('login.signupSuccess'),
				content: response.data && typeof response.data === 'object' && 'message' in response.data ? String((response.data as any).message) : t('login.signupSuccessMessage'),
				onOk: () => {
					setMode('login');
				}
			});
		} else {
			messageApi.error(response.error?.message || t('login.failed'));
		}
	};

	const handleForgotPasswordSendCode = async () => {
		if (forgotPasswordLoading) return; // Prevent double submission

		setForgotPasswordLoading(true);
		try {
			const username = form.getFieldValue('username');
			if (!username) {
				messageApi.error(t('login.usernameRequired'));
				return;
			}
			const api = get_ipc_api();
			if (!api) throw new Error(t('common.error'));

			// Add timeout for forgot password request
			const forgotPromise = api.forgotPassword(username, i18n.language);
			const timeoutPromise = new Promise<never>((_, reject) => {
				setTimeout(() => reject(new Error('Forgot password timeout after 30 seconds')), 30000);
			});

			await Promise.race([forgotPromise, timeoutPromise]);

			setCodeSent(true);
			messageApi.success(t('login.forgotCodeSent'));
		} catch (error) {
			console.error('Forgot password send code error:', error);
			messageApi.error(t('login.forgotCodeSendError') + ': ' + (error instanceof Error ? error.message : String(error)));
		} finally {
			setForgotPasswordLoading(false);
		}
	};

	const handleForgotPasswordReset = async () => {
		if (forgotPasswordLoading) return; // Prevent double submission

		setForgotPasswordLoading(true);
		try {
			const username = form.getFieldValue('username');
			const confirmCode = form.getFieldValue('confirmCode');
			const newPassword = form.getFieldValue('newPassword');
			if (!username || !confirmCode || !newPassword) {
				messageApi.error(t('login.forgotFieldsRequired'));
				return;
			}
			const api = get_ipc_api();
			if (!api) throw new Error(t('common.error'));

			// Add timeout for reset password request
			const resetPromise = api.confirmForgotPassword(username, confirmCode, newPassword, i18n.language);
			const timeoutPromise = new Promise<never>((_, reject) => {
				setTimeout(() => reject(new Error('Reset password timeout after 30 seconds')), 30000);
			});

			const response = await Promise.race([resetPromise, timeoutPromise]);

			if (response.success) {
				messageApi.success(t('login.forgotSuccess'));
				setMode('login');
				setCodeSent(false);
				form.resetFields();
			} else {
				messageApi.error(response.error?.message || t('login.failed'));
			}
		} catch (error) {
			console.error('Forgot password reset error:', error);
			messageApi.error(t('login.forgotResetError') + ': ' + (error instanceof Error ? error.message : String(error)));
		} finally {
			setForgotPasswordLoading(false);
		}
	};

	const handleSubmit = async (values: LoginFormValues) => {
		if (loading || loginSuccessful) return; // Prevent double submission

		setLoading(true);
		setLoginSuccessful(false);
		setLastError(null); // Clear previous errors

		let loginAttempted = false;

		try {
			const api = get_ipc_api();
			if (!api) throw new Error(t('common.error'));

			switch (mode) {
				case 'login':
					loginAttempted = true;
					setHasNavigated(false); // Reset navigation flag for new login attempt
					// 立即DisplayLogin进度UI
					setShowInitProgress(true);
					await handleLogin(values, api);
					// Don't reset loading here for successful login - let the navigation effect handle it
					return;
				case 'signup':
					await handleSignup(values, api);
					break;
				case 'forgot':
					await handleForgotPasswordReset(); // 调用新的ResetPassword逻辑
					break;
			}
		} catch (error) {
			console.error(`${mode} error:`, error);
			const errorMessage = error instanceof Error ? error.message : String(error);
			setLastError(errorMessage);

			// Show error message with retry hint
			messageApi.error({
				content: t(`login.${mode === 'login' ? 'error' : mode + '.error'}`) + ': ' + errorMessage,
				duration: 5, // Show for 5 seconds
			});

			// For login failures, always reset loading state
			if (mode === 'login' && loginAttempted) {
				setLoading(false);
				setLoginSuccessful(false);
				setLoginProgress('idle');
				setShowInitProgress(false); // Hide进度UI
			}
		} finally {
			// Reset loading for non-login modes or if login wasn't attempted
			if (mode !== 'login' || !loginAttempted) {
				setLoading(false);
			}
		}
	};

  // Google login handler
	const handleGoogleLogin = useCallback(async () => {
    if (loading || loginSuccessful) return; // Prevent double submission

    setLoading(true);
    setLoginSuccessful(false);
    setHasNavigated(false); // Reset navigation flag for new login attempt
    setLastError(null); // Clear previous errors
    setGoogleLoginProgress('opening');

    // 立即DisplayLogin进度UI
    setShowInitProgress(true);

    try {
      const api = get_ipc_api();
      if (!api) throw new Error(t('common.error'));

      // Get the selected role from form or use default
      const selectedRole = form.getFieldValue('role') || 'Commander';

      console.log('Starting Google OAuth login with role:', selectedRole);
      setGoogleLoginProgress('authenticating');

      // Add timeout for Google login - Google login requires user interaction in browser
      // and can take up to 5 minutes, so we set a longer timeout
      const loginPromise = api.googleLogin(i18n.language, selectedRole);
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('Google login timeout - please try again')), 300000); // 5 minutes
      });

      const response: APIResponse<any> = await Promise.race([loginPromise, timeoutPromise]);

      if (response.success && response.data) {
        console.log('Google login successful', response.data);
        setGoogleLoginProgress('success');

		const { token, user_info, message, session_id } = response.data;
        // 优先使用 name（显示名称），其次是 username，最后是 email
        const displayName = user_info.name || user_info.username || user_info.email;

        // 使用统一的UserStorage管理器，保存完整的用户信息
		const loginSession: LoginSession = {
          token,
          userInfo: {
            username: displayName,
            email: user_info.email,
            role: user_info.role || selectedRole,
            name: user_info.name || '',
            given_name: user_info.given_name || '',
            family_name: user_info.family_name || '',
            picture: user_info.picture || '',
            email_verified: user_info.email_verified ?? false,
            login_type: user_info.login_type || 'google'
          },
          loginTime: Date.now()
        };

		if (session_id) {
			loginSession.sessionId = session_id;
			userStorageManager.setSessionId(session_id);
			ipcClient.setSessionId(session_id);
		}

		userStorageManager.saveLoginSession(loginSession);

        // Enable page refresh monitoring
        pageRefreshManager.enable();

        messageApi.success(message || t('login.googleSuccess') || 'Google login successful');
        setLoginSuccessful(true);
        setGoogleLoginProgress('redirecting');

      } else {
        console.error('Google login failed', response.error);
        setGoogleLoginProgress('idle');
        const errorMessage = response.error?.message || t('login.googleFailed') || 'Google login failed';
        messageApi.error(errorMessage);
        throw new Error(errorMessage);
      }

    } catch (error) {
      console.error('Google login error:', error);
      setGoogleLoginProgress('idle');
      setShowInitProgress(false); // Hide进度UI
      const errorMessage = error instanceof Error ? error.message : String(error);
      setLastError(errorMessage);

      // Show error message with retry hint
      messageApi.error({
        content: `${t('login.googleError') || 'Google login error'}: ${errorMessage}`,
        duration: 5, // Show for 5 seconds
      });
      setLoading(false);
    }
  }, [i18n.language, navigate, messageApi, loading, loginSuccessful, t, form]);

  // Placeholder for Apple login to prevent runtime errors if referenced in JSX
  const handleAppleLogin = useCallback(() => {
    // TODO: implement Apple login flow
  }, []);

  // Feature flag to toggle Apple login button visibility
  const ENABLE_APPLE_LOGIN = false;

	// Render
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
							root: {
								backgroundColor: '#2d2d2d'
							}
						}
					}}
				>
					<Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
					<Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
				</Select>
			</div>

			{/* Show initialization progress during login process */}
			<LoadingProgress
				visible={loading || showInitProgress}
				progress={initProgress}
				title={loginProgress === 'redirecting' || googleLoginProgress === 'redirecting'
					? t('login.redirectingToMain') || 'Redirecting to main page...'
					: loginProgress === 'success' || googleLoginProgress === 'success'
						? t('login.loginSuccess') || 'Login successful!'
						: undefined
				}
				onComplete={() => {
					// 只负责关闭进度UI，跳转由统一的 effect 处理
					setLoading(false);
					setShowInitProgress(false);
				}}
			/>

			<Card className="login-card">
				{loading ? (
					<div className="loading-container">
						<Spin
							indicator={<LoadingOutlined style={{ fontSize: 48, color: '#1890ff' }} spin />}
							size="large"
						/>
						<div className="loading-text">
							{t('login.verifying')}
						</div>
					</div>
				) : (
					<>
						<div style={{ textAlign: 'center', marginBottom: 24 }}>
							<div className="logo-container">
								<img
									src={logo}
									alt={t('login.logoAlt')}
									className="logo-image"
								/>
							</div>
							<Title level={2} style={{ color: '#fff', margin: 0 }}>{t('login.title')}</Title>
							<Text style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{t('login.subtitle')}</Text>
						</div>

						<Form
							form={form}
							name="login"
							onFinish={handleSubmit}
							layout="vertical"
							requiredMark={false}
							initialValues={{ role: 'Commander' }}
						>
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
										rules={[{ required: true, message: t('login.passwordRequired') }]}
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
								<Form.Item
									name="role"
									rules={[{ required: true, message: t('login.roleRequired') }]}
								>
									<Select
										placeholder={t('login.selectRole')}
										size="large"
										className="form-input"
									>
										<Select.Option value="Commander">{t('roles.commander')}</Select.Option>
										<Select.Option value="Platoon">{t('roles.platoon')}</Select.Option>
										<Select.Option value="Staff Officer">{t('roles.staff_office')}</Select.Option>
									</Select>
								</Form.Item>
							)}
							{mode === 'forgot' && !codeSent && (
								<Form.Item>
									<Button
										type="primary"
										block
										size="large"
										onClick={handleForgotPasswordSendCode}
										loading={forgotPasswordLoading}
										disabled={forgotPasswordLoading}
										className="login-button"
									>
										{forgotPasswordLoading
											? t('login.sending') || 'Sending...'
											: t('login.sendConfirmCode')
										}
									</Button>
								</Form.Item>
							)}
							{mode === 'forgot' && codeSent && (
								<>
									<Form.Item
										name="confirmCode"
										rules={[{ required: true, message: t('login.confirmCodeRequired') }]}
									>
										<Input
											placeholder={t('login.confirmCode')}
											size="large"
											className="form-input"
										/>
									</Form.Item>
									<Form.Item
										name="newPassword"
										rules={[{ required: true, message: t('login.newPasswordRequired') }]}
									>
										<Input.Password
											prefix={<LockOutlined />}
											placeholder={t('login.newPassword')}
											size="large"
											className="form-input"
										/>
									</Form.Item>
									<Form.Item>
										<Button
											type="primary"
											block
											size="large"
											onClick={handleForgotPasswordReset}
											loading={forgotPasswordLoading}
											disabled={forgotPasswordLoading}
											className="login-button"
										>
											{forgotPasswordLoading
												? t('login.resetting') || 'Resetting...'
												: t('login.resetPassword')
											}
										</Button>
									</Form.Item>
								</>
							)}
							{(mode === 'login' || mode === 'signup') && (
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
										{mode === 'login' ? (() => {
											switch (loginProgress) {
												case 'authenticating':
													return t('login.loggingIn') || 'Logging in...';
												case 'success':
													return t('login.loginSuccess') || 'Success!';
												case 'redirecting':
													return t('login.redirecting') || 'Redirecting...';
												default:
													return loading && showInitProgress
														? t('login.redirecting') || 'Redirecting...'
														: loading
															? t('login.loggingIn') || 'Logging in...'
															: loginSuccessful
																? t('login.loginSuccess') || 'Success!'
																: t('login.loginButton');
											}
										})() : loading
											? t('login.loggingIn') || 'Logging in...'
											: t('login.signUp')
										}
									</Button>
								</Form.Item>
							)}
							{mode === 'login' && (
								<Form.Item>
									<Button
										block
										size="large"
										onClick={handleGoogleLogin}
										loading={loading}
										disabled={loading || loginSuccessful}
										className="google-login-button"
										icon={!loading ? <img src={googleIcon} alt="Google" style={{ width: 18, height: 18 }} /> : undefined}
									>
										{(() => {
											switch (googleLoginProgress) {
												case 'opening':
													return t('login.openingGoogle') || 'Opening browser for Google authentication...';
												case 'authenticating':
													return t('login.waitingForBrowserAuth') || 'Please complete authentication in the browser window...';
												case 'success':
													return t('login.loginSuccess') || 'Success!';
												case 'redirecting':
													return t('login.redirecting') || 'Redirecting...';
												default:
													return loading
														? t('login.loggingIn') || 'Logging in...'
														: loginSuccessful
															? t('login.loginSuccess') || 'Success!'
															: t('login.loginWithGoogle') || 'Login with Google';
											}
										})()}
									</Button>
								</Form.Item>
							)}
							{mode === 'login' && ENABLE_APPLE_LOGIN && (
								<Form.Item>
									<Button
										block
										size="large"
										onClick={handleAppleLogin}
										icon={<img src={appleIcon} alt="Apple" style={{ width: 18, height: 18 }} />}
									>
										{t('login.loginWithApple') || 'Login with Apple'}
									</Button>
								</Form.Item>
							)}

							{/* Error display */}
							{lastError && !loading && (
								<div style={{
									marginTop: 16,
									padding: '12px 16px',
									background: 'rgba(255, 77, 79, 0.1)',
									border: '1px solid rgba(255, 77, 79, 0.3)',
									borderRadius: '8px',
									color: '#ff4d4f'
								}}>
									<div style={{ fontSize: '14px', marginBottom: '8px' }}>
										{t('login.lastError') || 'Last error:'} {lastError}
									</div>
									<div style={{ fontSize: '12px', color: 'rgba(255, 255, 255, 0.6)' }}>
										{t('login.retryHint') || 'Please check your credentials and try again.'}
									</div>
								</div>
							)}

							<div style={{
								display: 'flex',
								justifyContent: 'space-between',
								alignItems: 'center',
								marginTop: 16
							}}>
								<Button
									type="link"
									onClick={() => handleModeChange(mode === 'login' ? 'signup' : 'login')}
									className="link-button"
								>
									{mode === 'login' ? t('login.signUp') : t('login.backToLogin')}
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

export default Login;