import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Form, Input, Button, Card, Select, Typography, App, Modal, Spin } from 'antd';
import { UserOutlined, LockOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse, IPCAPI } from '../../services/ipc';
import { get_ipc_api } from '../../services/ipc_api';
import { tokenStorage } from '../../services/ipc/ipcWCClient';
import { useUserStore } from '@/stores/userStore';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
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
	// 新增本地 state 控制验证码发送
	const [codeSent, setCodeSent] = useState(false);

	// Initialize IPC API and load login info
	useEffect(() => {
		const initialize = async () => {
			try {
				// 设置超时，避免长时间等待
				const timeoutPromise = new Promise((_, reject) => {
					setTimeout(() => reject(new Error('IPC initialization timeout')), 5000);
				});

				// 加载登录信息
				const api = get_ipc_api();
				if (!api) {
					console.warn('[Login] IPC API not available, skipping login info load');
					return;
				}

				const response = await Promise.race([
					api.getLastLoginInfo(),
					timeoutPromise
				]) as APIResponse<any>;

				console.log('[Login] Last login info', response.data);
				if (response?.data?.last_login) {
					const { username, password, machine_role } = response.data.last_login;
					console.log('last_login', response.data.last_login);
					// 直接更新表单，不需要等待 i18n 初始化
					updateFormWithRole(username, password, machine_role);
				}
			} catch (error) {
				console.warn('[Login] Failed to load last login info:', error);
				// 不阻塞登录页面显示，继续正常流程
			}
		};

		// 延迟初始化，让页面先渲染
		const timer = setTimeout(initialize, 100);
		return () => clearTimeout(timer);
	}, []); // 只在组件挂载时执行一次

	// 监听语言变化，更新角色选择框的显示
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

	// 更新表单值的辅助函数
	const updateFormWithRole = (username: string, password: string, role: string) => {
		form.setFieldsValue({
			username,
			password,
			role: role
		});
	};

	// Handlers
	const handleLanguageChange = useCallback((value: string) => {
		if (i18n.language !== value) {
			i18n.changeLanguage(value);
			localStorage.setItem('i18nextLng', value);
		}
	}, [i18n]);

	const handleModeChange = useCallback((newMode: AuthMode) => {
		setMode(newMode);
		form.resetFields();
	}, [form]);

	const handleLogin = async (values: LoginFormValues, api: IPCAPI) => {
		const response: APIResponse<any> = await api.login(values.username, values.password, values.role, i18n.language);
		if (response.success && response.data) {
			console.log('[Login] Login successful', response.data);
			const { token, user_info } = response.data;
			
			// 使用新的 token 存储系统
			tokenStorage.setToken(token);
			
			// // 清理IPC请求队列（新登录）
			// api.clearQueue();
			
			// 存储用户信息
			localStorage.setItem('token', token);
			localStorage.setItem('user_info', JSON.stringify({
				username: user_info?.username || values.username,
				role: user_info?.role || values.role,
				email: user_info?.email
			}));
			localStorage.setItem('isAuthenticated', 'true');
			localStorage.setItem('userRole', user_info?.role || values.role);
			localStorage.setItem('username', user_info?.username || values.username);
			
			useUserStore.getState().setUsername(user_info?.username || values.username);
			// 登录成功后启用页面刷新监听
			pageRefreshManager.enable();
			
			messageApi.success(t('login.success'));
			// Navigate immediately for better UX - main window initializes in background
			setTimeout(() => {
				navigate('/agents');
			}, 500)
		} else {
			console.error('Login failed', response.error);
			messageApi.error(response.error?.message || t('login.failed'));
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
		try {
			const username = form.getFieldValue('username');
			if (!username) {
				messageApi.error(t('login.usernameRequired'));
				return;
			}
			const api = get_ipc_api();
			await api.forgotPassword(username, i18n.language);
			setCodeSent(true);
			messageApi.success(t('login.forgotCodeSent'));
		} catch (error) {
			console.error('Forgot password send code error:', error);
			messageApi.error(t('login.forgotCodeSendError'));
		}
	};

	const handleForgotPasswordReset = async () => {
		try {
			const username = form.getFieldValue('username');
			const confirmCode = form.getFieldValue('confirmCode');
			const newPassword = form.getFieldValue('newPassword');
			if (!username || !confirmCode || !newPassword) {
				messageApi.error(t('login.forgotFieldsRequired'));
				return;
			}
			const api = get_ipc_api();
			const response = await api.confirmForgotPassword(username, confirmCode, newPassword, i18n.language);
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
			messageApi.error(t('login.forgotResetError'));
		}
	};

	const handleSubmit = async (values: LoginFormValues) => {
		setLoading(true);
		try {
			const api = get_ipc_api();
			if (!api) throw new Error(t('common.error'));

			switch (mode) {
				case 'login':
					await handleLogin(values, api);
					break;
				case 'signup':
					await handleSignup(values, api);
					break;
				case 'forgot':
					await handleForgotPasswordReset(); // 调用新的重置密码逻辑
					break;
			}
		} catch (error) {
			console.error(`${mode} error:`, error);
			messageApi.error(t(`login.${mode === 'login' ? 'error' : mode + '.error'}`) + ': ' + (error instanceof Error ? error.message : String(error)));
		} finally {
			setLoading(false);
		}
	};

  // Google login handler
  const handleGoogleLogin = useCallback(async () => {
    setLoading(true);
    try {
      const api = get_ipc_api();
      if (!api) throw new Error(t('common.error'));

      console.log('Starting Google OAuth login');
      
      const response: APIResponse<any> = await api.googleLogin(i18n.language);
      
      if (response.success && response.data) {
        console.log('Google login successful', response.data);
        
        const { token, user_info, message } = response.data;
        
        // Store minimal authentication state (UI only)
        localStorage.setItem('token', token);
        localStorage.setItem('isAuthenticated', 'true');
        localStorage.setItem('userRole', 'Commander'); // Default role for Google users
        localStorage.setItem('username', user_info.email);
        
        // Update user store (UI state only)
        useUserStore.getState().setUsername(user_info.email);
        
        // Enable page refresh monitoring
        pageRefreshManager.enable();
        
        // Show success message
        messageApi.success(message || t('login.googleSuccess') || 'Google login successful');
        
        // Navigate to main page immediately for better UX
		setTimeout(() => {
		  navigate('/agents');
		}, 500);
        
      } else {
        console.error('Google login failed', response.error);
        const errorMessage = response.error?.message || t('login.googleFailed') || 'Google login failed';
        messageApi.error(errorMessage);
      }
      
    } catch (error) {
      console.error('Google login error:', error);
      const errorMessage = t('login.googleError') || 'Google login error';
      messageApi.error(`${errorMessage}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [i18n.language, navigate, messageApi]);

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
									placeholder={t('common.username')}
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
										className="login-button"
									>
										{t('login.sendConfirmCode')}
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
											className="login-button"
										>
											{t('login.resetPassword')}
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
										className="login-button"
									>
										{mode === 'login' ? t('login.loginButton') : t('login.signUp')}
									</Button>
								</Form.Item>
							)}
							{mode === 'login' && (
								<Form.Item>
									<Button
										block
										size="large"
										onClick={handleGoogleLogin}
										icon={<img src={googleIcon} alt="Google" style={{ width: 18, height: 18 }} />}
									>
										{t('login.loginWithGoogle') || 'Login with Google'}
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

								{/* Debug Login Button */}
								<Row style={{ marginTop: 16 }} hidden={true}>
									<Col span={24}>
										<Button
											type="dashed"
											danger
											block
											onClick={() => {
												localStorage.setItem('isAuthenticated', 'true');
												localStorage.setItem('userRole', 'Commander');
												navigate('/dashboard');
											}}
										>
											Debug Login (Skip Authentication)
										</Button>
									</Col>
								</Row>
						</Form>
					</>
				)}
			</Card>
		</div>
	);
};

export default Login;