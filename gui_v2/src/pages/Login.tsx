import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Form, Input, Button, Card, Select, Typography, App, Modal, Switch } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
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

const Login: React.FC = () => {
    const navigate = useNavigate();
    const { t, i18n } = useTranslation();
    const [form] = Form.useForm<LoginFormValues>();
    const { message: messageApi } = App.useApp();
    const [loading, setLoading] = useState(false);
    const [mode, setMode] = useState<'login' | 'signup' | 'forgot'>('login');
    const [selectedRole, setSelectedRole] = useState('commander');
    const [isDebugMode, setIsDebugMode] = useState(false);

    set_ipc_api(createIPCAPI());
    const api = get_ipc_api();
    api.selfTest();

    useEffect(() => {
        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);
    }, [i18n]);

    useEffect(() => {
        const role = form.getFieldValue('role');
        if (role) {
            setSelectedRole(role);
        }
    }, [form]);

    const handleSubmit = async (values: LoginFormValues) => {
        setLoading(true);
        try {
            if (mode === 'login') {
                if (isDebugMode) {
                    // Debug mode: Direct login without any verification
                    localStorage.setItem('token', 'debug-token');
                    localStorage.setItem('isAuthenticated', 'true');
                    localStorage.setItem('userRole', selectedRole);
                    messageApi.success('Debug mode: Login successful');
                    navigate('/dashboard');
                    return;
                }

                const response = await api.login(values.username, values.password);
                if (response.success && response.data) {
                    logger.info('Login successful', response.data);
                    const { token, message: successMessage } = response.data;
                    localStorage.setItem('token', token);
                    localStorage.setItem('isAuthenticated', 'true');
                    localStorage.setItem('userRole', values.role);
                    messageApi.success(successMessage);
                    navigate('/dashboard');
                } else {
                    logger.error('Login failed', response.error);
                    messageApi.error(response.error?.message || t('login.failed'));
                }
            } else if (mode === 'signup') {
                if (values.password !== values.confirmPassword) {
                    messageApi.error(t('signup.passwordMismatch'));
                } else {
                    await api.handle_sign_up(values.username, values.password, values.role);
                    Modal.success({
                        title: t('signup.confirmTitle'),
                        content: t('signup.confirmMessage'),
                        onOk: () => setMode('login')
                    });
                }
            } else if (mode === 'forgot') {
                if (values.password !== values.confirmPassword) {
                    messageApi.error(t('forgot.passwordMismatch'));
                } else {
                    await api.handle_forget_password(values.username, values.password);
                    messageApi.success(t('forgot.success'));
                    setMode('login');
                }
            }
        } catch (error) {
            logger.error(`${mode} error:`, error);
            messageApi.error(t(`${mode}.failed`) + ': ' + (error instanceof Error ? error.message : String(error)));
        } finally {
            setLoading(false);
        }
    };

    const handleLanguageChange = (value: string) => {
        i18n.changeLanguage(value);
        localStorage.setItem('i18nextLng', value);
        localStorage.setItem('language', value);
    };

    const handleDebugModeChange = (checked: boolean) => {
        setIsDebugMode(checked);
        
        if (checked) {
            // Auto fill default values in debug mode
            form.setFieldsValue({
                username: 'debug_user',
                password: 'debug_password',
                role: 'commander'
            });
        } else {
            // Clear form when debug mode is turned off
            form.resetFields();
        }
    };

    return (
        <div className="login-container">
            <div className="login-decoration" />
            <div style={{ position: 'absolute', top: 20, right: 20, display: 'flex', gap: 12, zIndex: 10 }}>
                <Select value={i18n.language} style={{ width: 120 }} onChange={handleLanguageChange}>
                    <Select.Option value="en-US">{t('languages.en-US')}</Select.Option>
                    <Select.Option value="zh-CN">{t('languages.zh-CN')}</Select.Option>
                </Select>
                <Select
                    value={selectedRole}
                    style={{ width: 120 }}
                    onChange={(value) => {
                        form.setFieldsValue({ role: value });
                        setSelectedRole(value);
                    }}
                >
                    <Select.Option value="commander">{t('roles.commander')}</Select.Option>
                    <Select.Option value="platoon">{t('roles.platoon')}</Select.Option>
                    <Select.Option value="staff_office">{t('roles.staff_office')}</Select.Option>
                </Select>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: '#fff' }}>Debug</Text>
                    <Switch checked={isDebugMode} onChange={handleDebugModeChange} />
                </div>
            </div>

            <Card className="login-card" style={{ width: 400 }}>
                <img src={logo} alt="ECBOT" style={{ display: 'block', width: 120, height: 'auto', margin: '0 auto 32px' }} />
                <div className="login-title">
                    <Title level={2} style={{ color: 'white' }}>{t(`${mode}.title`)}</Title>
                    <Text type="secondary" style={{ color: 'white' }}>{t(`${mode}.subtitle`)}</Text>
                </div>

                <Form<LoginFormValues>
                    form={form}
                    name="auth"
                    onFinish={handleSubmit}
                    initialValues={{
                        username: '',
                        password: '',
                        role: 'commander',
                    }}
                    size="large"
                    className="login-form"
                    preserve={false}
                >
                    <Form.Item 
                        name="username" 
                        rules={[{ required: true, message: t('common.username') }]}
                    >
                        <Input prefix={<UserOutlined />} placeholder={t('common.username')} />
                    </Form.Item>
                    <Form.Item 
                        name="password" 
                        rules={[{ required: true, message: t('common.password') }]}
                    >
                        <Input.Password prefix={<LockOutlined />} placeholder={t('common.password')} />
                    </Form.Item>

                    {(mode === 'signup' || mode === 'forgot') && (
                        <Form.Item 
                            name="confirmPassword" 
                            rules={[{ required: true, message: t('common.confirmPassword') }]}
                        >
                            <Input.Password prefix={<LockOutlined />} placeholder={t('common.confirmPassword')} />
                        </Form.Item>
                    )}

                    <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} block>
                            {t(`common.${mode}`)}
                        </Button>
                    </Form.Item>

                    <Row justify="space-between">
                        <Col>
                            {mode !== 'forgot' && (
                                <Text style={{ color: '#40a9ff', cursor: 'pointer' }} onClick={() => setMode('forgot')}>
                                    {t('login.forgotUsernamePassword')}
                                </Text>
                            )}
                        </Col>
                        <Col>
                            <Text style={{ color: '#40a9ff', cursor: 'pointer' }} onClick={() => setMode(mode === 'signup' ? 'login' : 'signup')}>
                                {mode === 'signup' ? t('login.backToLogin') : t('login.signUp')}
                            </Text>
                        </Col>
                    </Row>
                </Form>
            </Card>
        </div>
    );
};

export default Login;
