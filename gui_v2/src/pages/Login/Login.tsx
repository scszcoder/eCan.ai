import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Form, Input, Button, Card, Select, Typography, App, Modal, Spin } from 'antd';
import { UserOutlined, LockOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { APIResponse, createIPCAPI } from '../../services/ipc';
import { set_ipc_api, get_ipc_api } from '../../services/ipc_api';
import { logger } from '../../utils/logger';
import { useUserStore } from '../../stores/userStore';
import { pageRefreshManager } from '../../services/events/PageRefreshManager';
import logo from '../../assets/logo.png';
import './Login.css';

const { Title, Text } = Typography;

interface LoginFormValues {
	username: string;
	password: string;
	confirmPassword?: string;
	role: string;
}



type AuthMode = 'login' | 'signup' | 'forgot';

const Login: React.FC = () => {
	// Hooks
	const navigate = useNavigate();
	const { t, i18n } = useTranslation();
	const [form] = Form.useForm<LoginFormValues>();
	const { message: messageApi } = App.useApp();

	// State
	const [mode, setMode] = useState<AuthMode>('login');
	const [loading, setLoading] = useState(false);

	// Initialize IPC API and load login info
	useEffect(() => {
		const initialize = async () => {
			try {
				// 加载登录信息
				const api = get_ipc_api();
				if (!api) return;

				const response: APIResponse<any> = await api.getLastLoginInfo();
				if (response?.data?.last_login) {
					const { username, password, machine_role } = response.data.last_login;
					console.log('last_login', response.data.last_login);
					// 直接更新表单，不需要等待 i18n 初始化
					updateFormWithRole(username, password, machine_role);
				}
			} catch (error) {
				console.error('Failed to initialize:', error);
			}
		};

		initialize();
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

	const handleLogin = async (values: LoginFormValues, api: any) => {
		const response = await api.login(values.username, values.password, values.role);
		if (response.success && response.data) {
			const { token, message: successMessage } = response.data;
			localStorage.setItem('token', token);
			localStorage.setItem('isAuthenticated', 'true');
			localStorage.setItem('userRole', values.role);
			
			// 登录成功后启用页面刷新监听
			pageRefreshManager.enable();
			
			messageApi.success(t('login.success'));
			navigate('/dashboard');
            useUserStore.getState().setUsername(values.username);
			await new Promise(resolve => setTimeout(resolve, 6000));
			const response2 = await api.getAll(values.username);
			logger.info('Get all successful', response2.data);
		} else {
			logger.error('Login failed', response.error);
			messageApi.error(response.error?.message || t('login.failed'));
		}
	};

	const handleSignup = async (values: LoginFormValues, api: any) => {
		if (values.password !== values.confirmPassword) {
			messageApi.error(t('login.passwordMismatch'));
			return;
		}
		await api.handle_sign_up(values.username, values.password, values.role);
		Modal.success({
			title: t('login.signupSuccess'),
			content: t('login.signupSuccessMessage'),
			onOk: () => {
				setMode('login');
			}
		});
	};

	const handleForgotPassword = async (values: LoginFormValues, api: any) => {
		if (values.password !== values.confirmPassword) {
			messageApi.error(t('login.passwordMismatch'));
			return;
		}
		await api.handle_forget_password(values.username, values.password);
		messageApi.success(t('login.forgotSuccess'));
		handleModeChange('login');
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
					await handleForgotPassword(values, api);
					break;
			}
		} catch (error) {
			logger.error(`${mode} error:`, error);
			messageApi.error(t(`login.${mode === 'login' ? 'error' : mode + '.error'}`) + ': ' + (error instanceof Error ? error.message : String(error)));
		} finally {
			setLoading(false);
		}
	};

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
									alt="Logo"
									className="logo-image"
								/>
								<div className="logo-border" />
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

							{mode === 'signup' && (
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
							)}

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

							<Form.Item>
								<Button
									type="primary"
									htmlType="submit"
									size="large"
									block
									loading={loading}
									className="login-button"
								>
									{mode === 'login' ? t('login.loginButton') :
										mode === 'signup' ? t('login.signUp') :
											t('login.resetPassword')}
								</Button>
							</Form.Item>

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