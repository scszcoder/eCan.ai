import React, { useState } from 'react';
import { Layout, Typography, Form, Input, Button, Select } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useNavigate } from 'react-router-dom';
import logo from '../assets/logo.png';

const { Content } = Layout;
const { Title } = Typography;

const LoginContainer = styled.div`
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background-image: url('/background.jpg');
  background-size: cover;
  background-position: center;
  position: relative;
`;

const LoginForm = styled.div`
  background: rgba(255, 255, 255, 0.95);
  padding: 2.5rem;
  border-radius: 12px;
  width: 400px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
`;

const Logo = styled.img`
  width: 180px;
  height: auto;
  display: block;
  margin: 0 auto 2.5rem;
`;

const StyledForm = styled(Form)`
  .ant-form-item {
    margin-bottom: 1.5rem;
  }

  .ant-input-affix-wrapper {
    height: 45px;
    border-radius: 8px;
    border: 1px solid #d9d9d9;
    transition: all 0.3s;

    &:hover, &:focus {
      border-color: #1890ff;
      box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
    }

    .anticon {
      color: #bfbfbf;
    }
  }

  .ant-input {
    font-size: 16px;
    padding: 8px 12px;
  }

  .ant-btn {
    height: 45px;
    font-size: 16px;
    border-radius: 8px;
  }
`;

const RoleSelect = styled(Select)`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  width: 140px;
  
  .ant-select-selector {
    height: 36px !important;
    border-radius: 6px !important;
    display: flex;
    align-items: center;
  }
`;

const Login: React.FC = () => {
  const navigate = useNavigate();
  const [role, setRole] = useState('commander');
  const [form] = Form.useForm();

  const onFinish = (values: any) => {
    // TODO: Implement actual authentication
    console.log('Login values:', values);
    navigate('/main/chat');
  };

  return (
    <LoginContainer>
      <RoleSelect
        value={role}
        onChange={(value) => setRole(value as string)}
        options={[
          { value: 'commander', label: 'Commander' },
          { value: 'platoon', label: 'Platoon' },
          { value: 'staff_office', label: 'Staff Office' },
        ]}
      />
      <LoginForm>
        <Logo src={logo} alt="Logo" />
        <StyledForm
          form={form}
          name="login"
          onFinish={onFinish}
          layout="vertical"
          size="large"
          initialValues={{
            username: 'admin',
            password: 'admin123*'
          }}
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: 'Please input your username!' }]}
          >
            <Input 
              prefix={<UserOutlined />} 
              placeholder="Username"
              autoComplete="username"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: 'Please input your password!' }]}
          >
            <Input.Password 
              prefix={<LockOutlined />} 
              placeholder="Password"
              autoComplete="current-password"
            />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              Sign In
            </Button>
          </Form.Item>
        </StyledForm>
      </LoginForm>
    </LoginContainer>
  );
};

export default Login; 