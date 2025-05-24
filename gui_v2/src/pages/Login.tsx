import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Select, Typography, App } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { createIPCAPI } from '../services/ipc';
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
    const [selectedRole, setSelectedRole] = React.useState({
        value: 'commander',
        label: t('roles.commander')
    });

    // 设置默认语言
    React.useEffect(() => {
        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);
    }, [i18n]);

    // 监听表单中role字段的变化
    React.useEffect(() => {
        const role = form.getFieldValue('role');
        if (role) {
            setSelectedRole({
                value: role,
                label: t(`roles.${role}`)
            });
        }
    }, [form, t]);

    const handleSubmit = async (values: LoginFormValues) => {
        setLoading(true);
        try {
            const response = await api.login<LoginResponse>(values.username, values.password);
            if (response.success && response.data) {
                console.log(response.data);
                const { token, message: successMessage } = response.data;
                localStorage.setItem('token', token);
                localStorage.setItem('isAuthenticated', 'true');
                localStorage.setItem('userRole', values.role);
                messageApi.success(successMessage);
                navigate('/dashboard');
            } else {
                console.log(response.error);
                messageApi.error(response.error?.message || t('login.failed'));
            }
        } catch (error) {
            messageApi.error(t('login.failed') + ': ' + (error instanceof Error ? error.message : String(error)));
        } finally {
            setLoading(false);
        }
    };

    const handleLanguageChange = (value: { value: string; label: string }) => {
        i18n.changeLanguage(value.value);
        localStorage.setItem('i18nextLng', value.value);
        localStorage.setItem('language', value.value);
    };

    const languageOptions = [
        { value: 'en-US', label: t('languages.en-US') },
        { value: 'zh-CN', label: t('languages.zh-CN') },
    ];

    const currentLanguage = {
        value: i18n.language,
        label: t(`languages.${i18n.language}`)
    };

    const roleOptions = [
        { value: 'commander', label: t('roles.commander') },
        { value: 'platoon', label: t('roles.platoon') },
        { value: 'staff_office', label: t('roles.staff_office') },
    ];

    return (
        <div className="login-container">
            <div className="login-decoration" />
            <div style={{ position: 'absolute', top: 20, right: 20, display: 'flex', gap: 12, zIndex: 10 }}>
                <Select
                    value={currentLanguage}
                    style={{ width: 120 }}
                    onChange={handleLanguageChange}
                    options={languageOptions}
                    placeholder={t('login.selectLanguage')}
                    labelInValue
                />
                <Select
                    value={selectedRole}
                    style={{ width: 120 }}
                    onChange={(value) => {
                        form.setFieldsValue({ role: value.value });
                        setSelectedRole(value);
                    }}
                    options={roleOptions}
                    placeholder={t('common.selectRole')}
                    labelInValue
                />
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