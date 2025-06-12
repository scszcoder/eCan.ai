import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Form, Input, Button, Card, Select, Typography, App, Modal, Spin } from 'antd';
import { UserOutlined, LockOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { createIPCAPI } from '../services/ipc';
import { set_ipc_api, get_ipc_api } from '../services/ipc_api';
import { logger } from '../utils/logger';
import logo from '../assets/logo.png';

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
    const [apiInitialized, setApiInitialized] = useState(false);

    // Initialize IPC API
    useEffect(() => {
        try {
            set_ipc_api(createIPCAPI());
            setApiInitialized(true);
        } catch (error) {
            console.error('Failed to initialize IPC API:', error);
        }
    }, []);

    // Load saved language and login info
    useEffect(() => {
        if (!apiInitialized) return;

        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);

        const loadLoginInfo = async () => {
            try {
                const api = get_ipc_api();
                if (!api) return;

                const response = await api.getLastLoginInfo();
                if (response?.data?.last_login) {
                    const { username, password, machine_role } = response.data.last_login;
                    form.setFieldsValue({ username, password, role: machine_role });
                }
            } catch (err) {
                console.warn('Could not load login info from backend', err);
            }
        };

        loadLoginInfo();
    }, [i18n, form, apiInitialized]);

    // Handlers
    const handleLanguageChange = useCallback((value: string) => {
        i18n.changeLanguage(value);
        localStorage.setItem('i18nextLng', value);
        localStorage.setItem('language', value);
    }, [i18n]);

    const handleModeChange = useCallback((newMode: AuthMode) => {
        setMode(newMode);
        form.resetFields();
    }, [form]);

    const handleSubmit = async (values: LoginFormValues) => {
        setLoading(true);
        try {
            const api = get_ipc_api();
            if (!api) throw new Error('IPC API not available');

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
            messageApi.error(t(`${mode}.failed`) + ': ' + (error instanceof Error ? error.message : String(error)));
        } finally {
            setLoading(false);
        }
    };

    const handleLogin = async (values: LoginFormValues, api: any) => {
        const response = await api.login(values.username, values.password, values.role);
        if (response.success && response.data) {
            const { token, message: successMessage } = response.data;
            localStorage.setItem('token', token);
            localStorage.setItem('isAuthenticated', 'true');
            localStorage.setItem('userRole', values.role);
            messageApi.success(successMessage);
            navigate('/dashboard');

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
            messageApi.error(t('signup.passwordMismatch'));
            return;
        }
        await api.handle_sign_up(values.username, values.password, values.role);
        Modal.success({
            title: t('signup.confirmTitle'),
            content: t('signup.confirmMessage'),
            onOk: () => handleModeChange('login')
        });
    };

    const handleForgotPassword = async (values: LoginFormValues, api: any) => {
        if (values.password !== values.confirmPassword) {
            messageApi.error(t('forgot.passwordMismatch'));
            return;
        }
        await api.handle_forget_password(values.username, values.password);
        messageApi.success(t('forgot.success'));
        handleModeChange('login');
    };

    // Render
    return (
        <div className="login-container">
            <div className="login-decoration" />
            <div style={{ position: 'absolute', top: 20, right: 20, display: 'flex', gap: 12, zIndex: 10 }}>
                <Select value={i18n.language} style={{ width: 120 }} onChange={handleLanguageChange}>
                    <Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
                    <Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
                </Select>
            </div>

            <Card className="login-card" style={{ width: 400 }}>
                <img src={logo} alt="ECBOT" style={{ display: 'block', width: 120, height: 'auto', margin: '0 auto 32px' }} />
                <div className="login-title">
                    <Title level={2} style={{ color: 'white' }}>{t(`${mode}.title`)}</Title>
                    <Text type="secondary" style={{ color: 'white' }}>{t(`${mode}.subtitle`)}</Text>
                </div>

                <Spin 
                    spinning={loading} 
                    indicator={<LoadingOutlined style={{ fontSize: 32, color: '#1890ff' }} spin />}
                    tip={t('login.verifying')}
                    wrapperClassName="login-spin-wrapper"
                    style={{
                        position: 'relative',
                        minHeight: '300px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        alignItems: 'center'
                    }}
                >
                    <Form<LoginFormValues>
                        form={form}
                        name="auth"
                        onFinish={handleSubmit}
                        onFinishFailed={(errorInfo) => {
                            console.log('Form validation failed:', errorInfo);
                        }}
                        size="large"
                        className="login-form"
                        style={{
                            opacity: loading ? 0.5 : 1,
                            transition: 'opacity 0.3s ease-in-out',
                            pointerEvents: loading ? 'none' : 'auto'
                        }}
                    >
                        <Form.Item name="username" rules={[{ required: true, message: t('common.username') }]}>
                            <Input prefix={<UserOutlined />} placeholder={t('common.username')} />
                        </Form.Item>

                        <Form.Item name="password" rules={[{ required: true, message: t('common.password') }]}>
                            <Input.Password prefix={<LockOutlined />} placeholder={t('common.password')} />
                        </Form.Item>

                        {(mode === 'signup' || mode === 'forgot') && (
                            <Form.Item name="confirmPassword" rules={[{ required: true, message: t('common.confirmPassword') }]}>
                                <Input.Password prefix={<LockOutlined />} placeholder={t('common.confirmPassword')} />
                            </Form.Item>
                        )}

                        <Form.Item name="role" rules={[{ required: true, message: t('common.selectRole') }]}>
                            <Select placeholder={t('common.selectRole')}>
                                <Select.Option value="commander">{t('roles.commander')}</Select.Option>
                                <Select.Option value="platoon">{t('roles.platoon')}</Select.Option>
                                <Select.Option value="staff_office">{t('roles.staff_office')}</Select.Option>
                            </Select>
                        </Form.Item>

                        <Form.Item>
                            <Button type="primary" htmlType="submit" loading={loading} block>
                                {t(`common.${mode}`)}
                            </Button>
                        </Form.Item>

                        <Row justify="space-between">
                            <Col>
                                {mode !== 'forgot' && (
                                    <Text style={{ color: '#40a9ff', cursor: 'pointer' }} onClick={() => handleModeChange('forgot')}>
                                        {t('login.forgotUsernamePassword')}
                                    </Text>
                                )}
                            </Col>
                            <Col>
                                <Text style={{ color: '#40a9ff', cursor: 'pointer' }} onClick={() => handleModeChange(mode === 'signup' ? 'login' : 'signup')}>
                                    {mode === 'signup' ? t('login.backToLogin') : t('login.signUp')}
                                </Text>
                            </Col>
                        </Row>
                    </Form>
                </Spin>
            </Card>
        </div>
    );
};

export default Login;
