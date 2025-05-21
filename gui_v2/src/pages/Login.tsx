import React from 'react';
import { Form, Input, Button, Card, Select, Typography, App } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import logo from '../assets/logo.png';

const { Title, Text } = Typography;

interface LoginFormValues {
    username: string;
    password: string;
    role: string;
}

const Login: React.FC = () => {
    const navigate = useNavigate();
    const { t, i18n } = useTranslation();
    const [form] = Form.useForm<LoginFormValues>();
    const { message } = App.useApp();

    // 设置默认语言
    React.useEffect(() => {
        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);
    }, [i18n]);

    const handleSubmit = async (values: LoginFormValues) => {
        try {
            // 模拟登录验证
            if (values.username === 'admin' && values.password === 'admin123#') {
                // 保存登录状态和角色
                localStorage.setItem('isAuthenticated', 'true');
                localStorage.setItem('userRole', values.role);
                
                // 显示成功消息
                message.success(t('login.success'));
                
                // 使用 replace 进行导航
                navigate('/', { replace: true });
            } else {
                message.error(t('login.invalidCredentials'));
            }
        } catch (err) {
            console.error('Login error:', err);
            message.error(t('login.error'));
        }
    };

    const handleLanguageChange = (value: { value: string; label: string }) => {
        i18n.changeLanguage(value.value);
        localStorage.setItem('i18nextLng', value.value);
        localStorage.setItem('language', value.value);
    };

    const handleRoleChange = (value: string) => {
        form.setFieldsValue({ role: value });
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
                    value={form.getFieldValue('role') || 'commander'}
                    style={{ width: 140 }}
                    onChange={handleRoleChange}
                    options={roleOptions}
                />
            </div>

            <Card className="login-card" style={{ width: 400 }}>
                <img src={logo} alt="ECBOT" style={{ display: 'block', width: 120, height: 'auto', margin: '0 auto 32px' }} />
                <div className="login-title">
                    <Title level={2}>{t('login.title')}</Title>
                    <Text type="secondary">{t('login.subtitle')}</Text>
                </div>

                <Form
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

                    {/* 隐藏的角色表单项，确保表单能收集到角色 */}
                    <Form.Item name="role" style={{ display: 'none' }}>
                        <Input type="hidden" />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit" block>
                            {t('common.login')}
                        </Button>
                    </Form.Item>
                </Form>
            </Card>
        </div>
    );
};

export default Login; 