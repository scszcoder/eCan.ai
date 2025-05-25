import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Select, Typography, App } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { createIPCAPI } from '../services/ipc';
import { logger } from '../utils/logger';
import logo from '../assets/logo.png';

const { Title, Text } = Typography;

interface LoginFormValues {
    username: string;
    password: string;
    role: string;
}

interface LoginResponse {
    token: string;
    message: string;
}

const Login: React.FC = () => {
    const navigate = useNavigate();
    const { t, i18n } = useTranslation();
    const [form] = Form.useForm<LoginFormValues>();
    const { message: messageApi } = App.useApp();
    const [loading, setLoading] = useState(false);
    const api = createIPCAPI();
    const [selectedRole, setSelectedRole] = useState('commander');

    // 设置默认语言
    React.useEffect(() => {
        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);
    }, [i18n]);

    // 监听表单中role字段的变化
    React.useEffect(() => {
        const role = form.getFieldValue('role');
        if (role) {
            setSelectedRole(role);
        }
    }, [form]);

    const handleSubmit = async (values: LoginFormValues) => {
        setLoading(true);
        try {
            const response = await api.login<LoginResponse>(values.username, values.password);
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
        } catch (error) {
            logger.error('Login error:', error);
            messageApi.error(t('login.failed') + ': ' + (error instanceof Error ? error.message : String(error)));
        } finally {
            setLoading(false);
        }
    };

    const handleLanguageChange = (value: string) => {
        i18n.changeLanguage(value);
        localStorage.setItem('i18nextLng', value);
        localStorage.setItem('language', value);
    };

    return (
        <div className="login-container">
            <div className="login-decoration" />
            <div style={{ position: 'absolute', top: 20, right: 20, display: 'flex', gap: 12, zIndex: 10 }}>
                <Select
                    value={i18n.language}
                    style={{ width: 120 }}
                    onChange={handleLanguageChange}
                    placeholder={t('login.selectLanguage')}
                >
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
                    placeholder={t('common.selectRole')}
                >
                    <Select.Option value="commander">{t('roles.commander')}</Select.Option>
                    <Select.Option value="platoon">{t('roles.platoon')}</Select.Option>
                    <Select.Option value="staff_office">{t('roles.staff_office')}</Select.Option>
                </Select>
            </div>

            <Card className="login-card" style={{ width: 400 }}>
                <img src={logo} alt="ECBOT" style={{ display: 'block', width: 120, height: 'auto', margin: '0 auto 32px' }} />
                <div className="login-title">
                    <Title level={2}>{t('login.title')}</Title>
                    <Text type="secondary">{t('login.subtitle')}</Text>
                </div>

                <Form<LoginFormValues>
                    form={form}
                    name="login"
                    onFinish={handleSubmit}
                    initialValues={{
                        username: 'admin',
                        password: 'admin123#',
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
                        <Input
                            prefix={<UserOutlined />}
                            placeholder={t('common.username')}
                        />
                    </Form.Item>

                    <Form.Item
                        name="password"
                        rules={[{ required: true, message: t('common.password') }]}
                    >
                        <Input.Password
                            prefix={<LockOutlined />}
                            placeholder={t('common.password')}
                        />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} block>
                            {t('common.login')}
                        </Button>
                    </Form.Item>
                </Form>
            </Card>
        </div>
    );
};

export default Login; 