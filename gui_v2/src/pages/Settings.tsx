import React, { useEffect } from 'react';
import { Card, Form, Input, Switch, Select, Button, Space, Typography, App } from 'antd';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { useTheme } from '../contexts/ThemeContext';

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
    const { theme: currentTheme, changeTheme } = useTheme();
    const [form] = Form.useForm();
    const { message } = App.useApp();

    // 初始化表单值
    useEffect(() => {
        form.setFieldsValue({
            language: i18n.language,
            theme: currentTheme,
            notifications: true,
            sound: true,
            email: true
        });
    }, [form, i18n.language, currentTheme]);

    const handleLanguageChange = (value: string) => {
        i18n.changeLanguage(value);
        localStorage.setItem('i18nextLng', value);
        localStorage.setItem('language', value);
        message.success(t('settings.languageChanged'));
    };

    const handleThemeChange = (value: string) => {
        changeTheme(value as 'light' | 'dark' | 'system');
        message.success(t('settings.themeChanged'));
    };

    const onFinish = (values: any) => {
        console.log('Settings values:', values);
        message.success(t('settings.saved'));
    };

    const handleDropdownClick = (e: React.MouseEvent) => {
        e.stopPropagation();
    };

    return (
        <div className="page-container">
            <Title level={2}>{t('settings.title')}</Title>
            
            <Form
                form={form}
                layout="vertical"
                onFinish={onFinish}
                className="settings-form"
            >
                <Card className="settings-card" title={t('settings.general')}>
                    <Form.Item
                        name="language"
                        label={t('settings.language')}
                    >
                        <Select
                            className="settings-select"
                            onChange={handleLanguageChange}
                            onClick={handleDropdownClick}
                            getPopupContainer={(triggerNode) => triggerNode.parentNode as HTMLElement}
                        >
                            <Option value="en-US">{t('languages.en-US')}</Option>
                            <Option value="zh-CN">{t('languages.zh-CN')}</Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="theme"
                        label={t('settings.theme')}
                    >
                        <Select
                            className="settings-select"
                            onChange={handleThemeChange}
                            onClick={handleDropdownClick}
                            getPopupContainer={(triggerNode) => triggerNode.parentNode as HTMLElement}
                        >
                            <Option value="light">{t('settings.theme.light')}</Option>
                            <Option value="dark">{t('settings.theme.dark')}</Option>
                            <Option value="system">{t('settings.theme.system')}</Option>
                        </Select>
                    </Form.Item>
                </Card>

                <Card className="settings-card" title={t('settings.notifications')}>
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
                </Card>

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
        </div>
    );
};

export default Settings; 