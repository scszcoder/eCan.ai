import React, { useState } from 'react';
import { Form, Input, Button, Checkbox, Select, Space, Typography } from 'antd';
import { UserOutlined, LockOutlined, GlobalOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '../contexts/LanguageContext';
import { useNavigate } from 'react-router-dom';

const { Title, Text } = Typography;
const { Option } = Select;

const LoginContainer = styled.div`
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background: #f0f2f5;
`;

const LoginForm = styled.div`
    width: 100%;
    max-width: 400px;
    padding: 40px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
`;

const SelectContainer = styled.div`
    position: absolute;
    top: 20px;
    right: 20px;
    display: flex;
    gap: 12px;
`;

const LanguageSelect = styled(Select)`
    width: 120px;
`;

const RoleSelect = styled(Select)`
    width: 140px;
`;

const Login: React.FC = () => {
    const { t } = useTranslation();
    const { currentLanguage, changeLanguage } = useLanguage();
    const navigate = useNavigate();
    const [role, setRole] = useState('commander');

    const onFinish = (values: any) => {
        console.log('Success:', values);
        navigate('/main/chat');
    };

    return (
        <LoginContainer>
            <SelectContainer>
                <LanguageSelect
                    value={currentLanguage}
                    onChange={(value) => changeLanguage(value as string)}
                    prefix={<GlobalOutlined />}
                >
                    <Option value="en">{t('languages.en')}</Option>
                    <Option value="zh">{t('languages.zh')}</Option>
                </LanguageSelect>
                <RoleSelect
                    value={role}
                    onChange={(value) => setRole(value as string)}
                >
                    <Option value="commander">{t('roles.commander')}</Option>
                    <Option value="platoon">{t('roles.platoon')}</Option>
                    <Option value="staff_office">{t('roles.staff_office')}</Option>
                </RoleSelect>
            </SelectContainer>
            <LoginForm>
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    <div>
                        <Title level={2}>{t('login.title')}</Title>
                        <Text type="secondary">{t('login.subtitle')}</Text>
                    </div>
                    <Form
                        name="login"
                        initialValues={{
                            remember: true,
                            username: 'admin',
                            password: 'admin123*'
                        }}
                        onFinish={onFinish}
                        size="large"
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

                        <Form.Item>
                            <Form.Item name="remember" valuePropName="checked" noStyle>
                                <Checkbox>{t('login.rememberMe')}</Checkbox>
                            </Form.Item>
                            <a style={{ float: 'right' }} href="#">
                                {t('login.forgotPassword')}
                            </a>
                        </Form.Item>

                        <Form.Item>
                            <Button type="primary" htmlType="submit" block>
                                {t('login.loginButton')}
                            </Button>
                        </Form.Item>
                    </Form>
                </Space>
            </LoginForm>
        </LoginContainer>
    );
};

export default Login; 