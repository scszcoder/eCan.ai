import React, { useState } from 'react';
import { Form, Input, Button, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { LoginFormValues } from './types';
import { LOGIN_SUCCESS_REDIRECT, LOGIN_MESSAGES, LOGIN_FORM } from './constants';
import styles from './index.module.css';

const Login: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const onFinish = async (values: LoginFormValues) => {
        setLoading(true);
        try {
            // TODO: 实现登录请求
            // 临时模拟登录成功
            setTimeout(() => {
                localStorage.setItem('token', 'dummy-token');
                message.success(LOGIN_MESSAGES.LOGIN_SUCCESS);
                navigate(LOGIN_SUCCESS_REDIRECT);
                setLoading(false);
            }, 1000);
        } catch {
            message.error(LOGIN_MESSAGES.LOGIN_FAILED);
            setLoading(false);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.loginBox}>
                <h1>{LOGIN_FORM.SUBMIT_TEXT}</h1>
                <Form name="login" onFinish={onFinish} autoComplete="off">
                    <Form.Item
                        name="username"
                        rules={[{ required: true, message: LOGIN_MESSAGES.USERNAME_REQUIRED }]}
                    >
                        <Input placeholder={LOGIN_FORM.USERNAME_PLACEHOLDER} />
                    </Form.Item>

                    <Form.Item
                        name="password"
                        rules={[{ required: true, message: LOGIN_MESSAGES.PASSWORD_REQUIRED }]}
                    >
                        <Input.Password placeholder={LOGIN_FORM.PASSWORD_PLACEHOLDER} />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} block>
                            {LOGIN_FORM.SUBMIT_TEXT}
                        </Button>
                    </Form.Item>
                </Form>
            </div>
        </div>
    );
};

export default Login; 