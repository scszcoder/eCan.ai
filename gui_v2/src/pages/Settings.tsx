import React, { useEffect } from 'react';
import { Card, Form, Input, Switch, Select, Button, Space, Typography, message } from 'antd';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

const { Title } = Typography;
const { Option } = Select;

const SettingsContainer = styled.div`
    padding: 24px;
`;

const StyledCard = styled(Card)`
    margin-bottom: 24px;
`;

const Settings: React.FC = () => {
    const { t, i18n } = useTranslation();
    const [form] = Form.useForm();

    // 初始化表单值
    useEffect(() => {
        form.setFieldsValue({
            language: i18n.language,
            theme: 'light',
            notifications: true,
            sound: true,
            email: true
        });
    }, [form, i18n.language]);

    const handleLanguageChange = (value: string) => {
        i18n.changeLanguage(value);
        localStorage.setItem('i18nextLng', value);
        localStorage.setItem('language', value);
        message.success(t('settings.languageChanged'));
    };

    const onFinish = (values: any) => {
        console.log('Settings values:', values);
        message.success(t('settings.saved'));
    };

    return (
        <SettingsContainer>
            <Title level={2}>{t('settings.title')}</Title>
            
            <Form
                form={form}
                layout="vertical"
                onFinish={onFinish}
            >
                <StyledCard title={t('settings.general')}>
                    <Form.Item
                        name="language"
                        label={t('settings.language')}
                    >
                        <Select onChange={handleLanguageChange}>
                            <Option value="en">{t('languages.en')}</Option>
                            <Option value="zh">{t('languages.zh')}</Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="theme"
                        label={t('settings.theme')}
                    >
                        <Select>
                            <Option value="light">{t('settings.light')}</Option>
                            <Option value="dark">{t('settings.dark')}</Option>
                            <Option value="system">{t('settings.system')}</Option>
                        </Select>
                    </Form.Item>
                </StyledCard>

                <StyledCard title={t('settings.notifications')}>
                    <Form.Item
                        name="notifications"
                        label={t('settings.enableNotifications')}
                        valuePropName="checked"
                    >
                        <Switch />
                    </Form.Item>

                    <Form.Item
                        name="sound"
                        label={t('settings.sound')}
                        valuePropName="checked"
                    >
                        <Switch />
                    </Form.Item>

                    <Form.Item
                        name="email"
                        label={t('settings.email')}
                        valuePropName="checked"
                    >
                        <Switch />
                    </Form.Item>
                </StyledCard>

                <Form.Item>
                    <Space>
                        <Button type="primary" htmlType="submit">
                            {t('common.save')}
                        </Button>
                        <Button onClick={() => form.resetFields()}>
                            {t('common.reset')}
                        </Button>
                    </Space>
                </Form.Item>
            </Form>
        </SettingsContainer>
    );
};

export default Settings; 