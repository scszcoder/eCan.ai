import React, { useEffect } from 'react';
import { Form, Input, Button, Card, Select, Typography, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import logo from '../assets/logo.png';

const { Title, Text } = Typography;

const LoginContainer = styled.div`
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background: #f0f2f5;
    position: relative;
`;

const LoginCard = styled(Card)`
    width: 400px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
`;

const LoginTitle = styled.div`
    text-align: center;
    margin-bottom: 24px;
`;

const SelectContainer = styled.div`
    position: absolute;
    top: 20px;
    right: 20px;
    display: flex;
    gap: 12px;
    z-index: 10;
`;

const Logo = styled.img`
    display: block;
    width: 120px;
    height: auto;
    margin: 0 auto 32px;
`;

const Login: React.FC = () => {
    const navigate = useNavigate();
    const { t, i18n } = useTranslation();
    const [form] = Form.useForm();

    useEffect(() => {
        // 确保初始时角色为 commander
        form.setFieldsValue({ role: 'commander' });
        // 设置默认语言
        const savedLanguage = localStorage.getItem('i18nextLng') || 'zh-CN';
        i18n.changeLanguage(savedLanguage);
    }, [form, i18n]);

    const handleSubmit = async (values: any) => {
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
        } catch (error) {
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
        <LoginContainer>
            <SelectContainer>
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
            </SelectContainer>

            <LoginCard>
                <Logo src={logo} alt="ECBOT" />
                <LoginTitle>
                    <Title level={2}>{t('login.title')}</Title>
                    <Text type="secondary">{t('login.subtitle')}</Text>
                </LoginTitle>

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
            </LoginCard>
        </LoginContainer>
    );
};

export default Login; 