import React from 'react';
import { Card, Form, Switch, Select, Button, message } from 'antd';
import { useAppStore } from '../store/appStore';

const Settings: React.FC = () => {
    const { settings, setSettings } = useAppStore();
    const [form] = Form.useForm();

    const handleSave = async (values: any) => {
        try {
            // 保存到本地存储
            localStorage.setItem('appSettings', JSON.stringify(values));
            setSettings(values);
            message.success('设置已保存');
        } catch (error) {
            message.error('保存设置失败');
        }
    };

    return (
        <div>
            <h1>设置</h1>
            <Card>
                <Form
                    form={form}
                    layout="vertical"
                    initialValues={settings}
                    onFinish={handleSave}
                >
                    <Form.Item
                        label="主题"
                        name="theme"
                    >
                        <Select>
                            <Select.Option value="light">浅色</Select.Option>
                            <Select.Option value="dark">深色</Select.Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        label="语言"
                        name="language"
                    >
                        <Select>
                            <Select.Option value="zh-CN">简体中文</Select.Option>
                            <Select.Option value="en-US">English</Select.Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        label="开机自启"
                        name="autoStart"
                        valuePropName="checked"
                    >
                        <Switch />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit">
                            保存设置
                        </Button>
                    </Form.Item>
                </Form>
            </Card>
        </div>
    );
};

export default Settings; 