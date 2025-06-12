import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Form, Input, Button, Card, Select, Typography, App, Modal } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { createIPCAPI } from '../services/ipc';
import { set_ipc_api, get_ipc_api } from '../services/ipc_api';
import { logger } from '../utils/logger';
import logo from '../assets/logo.png';
import CryptoJS from 'crypto-js';

const { Title, Text } = Typography;

interface LoginFormValues {
    username: string;
    password: string;
    confirmPassword?: string;
    role: string;
}

const SECRET_KEY = '1Lyt0J0TOYP-isBzB_KJIfzrfLK8Vaujl1c5YqdlW8c=';

function encrypt(text: string): string {
    return CryptoJS.AES.encrypt(text, SECRET_KEY).toString();
}

function decrypt(ciphertext: string): string {
    const bytes = CryptoJS.AES.decrypt(ciphertext, SECRET_KEY);
    return bytes.toString(CryptoJS.enc.Utf8);
}

const Login: React.FC = () => {
    const navigate = useNavigate();
    const { t, i18n } = useTranslation();
    const [form] = Form.useForm<LoginFormValues>();
    const { message: messageApi } = App.useApp();
    const [loading, setLoading] = useState(false);
    const [mode, setMode] = useState<'login' | 'signup' | 'forgot'>('login');
    const [passwordValue, setPasswordValue] = useState<string>('');
    const [userNameValue, setUserNameValue] = useState<string>('');
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

    // Memoize the language change handler
    const handleLanguageChange = useCallback((value: string) => {
        i18n.changeLanguage(value);
        localStorage.setItem('i18nextLng', value);
        localStorage.setItem('language', value);
    }, [i18n]);

    // Load login info only after API is initialized
    useEffect(() => {
        if (!apiInitialized) return;

        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);

        const loadLoginInfo = async () => {
            try {
                const api = get_ipc_api();
                if (!api) {
                    console.warn('IPC API not available');
                    return;
                }

                const response = await api.getLastLoginInfo();
                console.log('Received login info:', response);

                if (response?.uliPath) console.log('uli.json full path:', response.uliPath);
                if (response?.rolePath) console.log('role.json full path:', response.rolePath);

                if (response?.data?.last_login) {
                    const { username, password, machine_role } = response.data.last_login;
                    form.setFieldsValue({
                        username,
                        password: password,
                        role: machine_role
                    });
                }
            } catch (err) {
                console.warn('Could not load login info from backend', err);
            }
        };

        loadLoginInfo();
    }, [i18n, form, apiInitialized]);

    const handleSubmit = async (values: LoginFormValues) => {
        const finalPassword = values.password;
        console.log("Submitted values:", { ...values, password: values.password });
        setLoading(true);
        try {
            const api = get_ipc_api();
            if (!api) {
                throw new Error('IPC API not available');
            }

            if (mode === 'login') {
                const response = await api.login(values.username, values.password, values.role);
                console.log("login finished....", response);
                if (response.success && response.data) {
                    logger.info('Login successful', response.data);
                    const { token, message: successMessage } = response.data;
                    localStorage.setItem('token', token);
                    localStorage.setItem('isAuthenticated', 'true');
                    localStorage.setItem('userRole', values.role);
                    setPasswordValue(values.password);
                    setUserNameValue(values.username);
                    messageApi.success(successMessage);
                    navigate('/dashboard');

                    //wait for 6 seconds
                    await new Promise(resolve => setTimeout(resolve, 6000));

                    const response2 = await api.getAll(values.username);
                    logger.info('Get all successful', response2.data);
                } else {
                    logger.error('Login failed', response.error);
                    messageApi.error(response.error?.message || t('login.failed'));
                }
            } else if (mode === 'signup') {
                if (finalPassword !== values.confirmPassword) {
                    messageApi.error(t('signup.passwordMismatch'));
                } else {
                    await api.handle_sign_up(values.username, finalPassword, values.role);
                    Modal.success({
                        title: t('signup.confirmTitle'),
                        content: t('signup.confirmMessage'),
                        onOk: () => setMode('login')
                    });
                }
            } else if (mode === 'forgot') {
                if (finalPassword !== values.confirmPassword) {
                    messageApi.error(t('forgot.passwordMismatch'));
                } else {
                    await api.handle_forget_password(values.username, finalPassword);
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

                <Form<LoginFormValues>
                    form={form}
                    name="auth"
                    onFinish={handleSubmit}
                    onFinishFailed={(errorInfo) => {
                        console.log('Form validation failed:', errorInfo);
                    }}
                    size="large"
                    className="login-form"
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

                    {/* Debug Login Button */}
                    {/* <Row style={{ marginTop: 16 }}>
                        <Col span={24}>
                            <Button 
                                type="dashed" 
                                danger 
                                block 
                                onClick={() => {
                                    localStorage.setItem('isAuthenticated', 'true');
                                    localStorage.setItem('userRole', 'commander');
                                    navigate('/dashboard');
                                }}
                            >
                                Debug Login (Skip Authentication)
                            </Button>
                        </Col>
                    </Row> */}
                </Form>
            </Card>
        </div>
    );
};

export default Login;
