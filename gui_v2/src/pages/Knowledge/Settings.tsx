import React, { useState } from 'react';
import { 
  Card, 
  Form, 
  Input, 
  Button, 
  Switch, 
  Select, 
  Space, 
  Typography, 
  Divider,
  message,
  Tabs,
  Upload,
  Avatar
} from 'antd';
import { 
  UserOutlined,
  SettingOutlined,
  BellOutlined,
  SecurityScanOutlined,
  SaveOutlined,
  UploadOutlined
} from '@ant-design/icons';

const { Option } = Select;
const { Title, Text } = Typography;
const { TabPane } = Tabs;

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  // 处理保存设置
  const handleSave = async (values: any) => {
    setLoading(true);
    try {
      // 模拟保存
      await new Promise(resolve => setTimeout(resolve, 1000));
      message.success('设置保存成功');
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>系统设置</Title>
      </div>

      <Tabs defaultActiveKey="profile" size="large">
        {/* 个人资料设置 */}
        <TabPane 
          tab={
            <span>
              <UserOutlined />
              个人资料
            </span>
          } 
          key="profile"
        >
          <Card>
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSave}
              initialValues={{
                username: '当前用户',
                email: 'user@company.com',
                department: '技术部',
                position: '开发工程师',
                language: 'zh-CN',
                timezone: 'Asia/Shanghai',
              }}
            >
              <div style={{ display: 'flex', gap: 24, marginBottom: 24 }}>
                <div>
                  <Avatar size={80} icon={<UserOutlined />} />
                  <div style={{ marginTop: 8 }}>
                    <Upload>
                      <Button icon={<UploadOutlined />} size="small">
                        更换头像
                      </Button>
                    </Upload>
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <Form.Item
                    name="username"
                    label="用户名"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input />
                  </Form.Item>
                  
                  <Form.Item
                    name="email"
                    label="邮箱"
                    rules={[
                      { required: true, message: '请输入邮箱' },
                      { type: 'email', message: '请输入有效的邮箱地址' }
                    ]}
                  >
                    <Input />
                  </Form.Item>
                </div>
              </div>

              <Form.Item name="department" label="部门">
                <Input />
              </Form.Item>

              <Form.Item name="position" label="职位">
                <Input />
              </Form.Item>

              <Form.Item name="language" label="语言">
                <Select>
                  <Option value="zh-CN">中文</Option>
                  <Option value="en-US">English</Option>
                </Select>
              </Form.Item>

              <Form.Item name="timezone" label="时区">
                <Select>
                  <Option value="Asia/Shanghai">Asia/Shanghai (UTC+8)</Option>
                  <Option value="America/New_York">America/New_York (UTC-5)</Option>
                  <Option value="Europe/London">Europe/London (UTC+0)</Option>
                </Select>
              </Form.Item>

              <Form.Item>
                <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                  保存设置
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        {/* 系统设置 */}
        <TabPane 
          tab={
            <span>
              <SettingOutlined />
              系统设置
            </span>
          } 
          key="system"
        >
          <Card>
            <Form layout="vertical" onFinish={handleSave}>
              <Title level={5}>知识库设置</Title>
              
              <Form.Item label="默认知识库">
                <Select defaultValue="default">
                  <Option value="default">默认知识库</Option>
                  <Option value="tech">技术文档库</Option>
                  <Option value="product">产品文档库</Option>
                </Select>
              </Form.Item>

              <Form.Item label="文档自动保存">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="自动保存间隔">
                <Select defaultValue="30" disabled>
                  <Option value="30">30秒</Option>
                  <Option value="60">1分钟</Option>
                  <Option value="300">5分钟</Option>
                </Select>
              </Form.Item>

              <Divider />

              <Title level={5}>问答设置</Title>
              
              <Form.Item label="AI回答长度">
                <Select defaultValue="detailed">
                  <Option value="brief">简洁</Option>
                  <Option value="detailed">详细</Option>
                  <Option value="comprehensive">全面</Option>
                </Select>
              </Form.Item>

              <Form.Item label="自动转人工">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="问题自动分类">
                <Switch defaultChecked />
              </Form.Item>

              <Divider />

              <Title level={5}>界面设置</Title>
              
              <Form.Item label="主题">
                <Select defaultValue="light">
                  <Option value="light">浅色主题</Option>
                  <Option value="dark">深色主题</Option>
                  <Option value="auto">跟随系统</Option>
                </Select>
              </Form.Item>

              <Form.Item label="字体大小">
                <Select defaultValue="medium">
                  <Option value="small">小</Option>
                  <Option value="medium">中</Option>
                  <Option value="large">大</Option>
                </Select>
              </Form.Item>

              <Form.Item label="紧凑模式">
                <Switch />
              </Form.Item>

              <Form.Item>
                <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                  保存设置
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        {/* 通知设置 */}
        <TabPane 
          tab={
            <span>
              <BellOutlined />
              通知设置
            </span>
          } 
          key="notifications"
        >
          <Card>
            <Form layout="vertical" onFinish={handleSave}>
              <Title level={5}>邮件通知</Title>
              
              <Form.Item label="新评论通知">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="@提及通知">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="文档更新通知">
                <Switch />
              </Form.Item>

              <Form.Item label="问答回复通知">
                <Switch defaultChecked />
              </Form.Item>

              <Divider />

              <Title level={5}>系统通知</Title>
              
              <Form.Item label="系统维护通知">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="功能更新通知">
                <Switch defaultChecked />
              </Form.Item>

              <Form.Item label="安全提醒">
                <Switch defaultChecked />
              </Form.Item>

              <Divider />

              <Title level={5}>通知频率</Title>
              
              <Form.Item label="邮件摘要">
                <Select defaultValue="daily">
                  <Option value="immediate">立即</Option>
                  <Option value="hourly">每小时</Option>
                  <Option value="daily">每日</Option>
                  <Option value="weekly">每周</Option>
                </Select>
              </Form.Item>

              <Form.Item>
                <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                  保存设置
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        {/* 安全设置 */}
        <TabPane 
          tab={
            <span>
              <SecurityScanOutlined />
              安全设置
            </span>
          } 
          key="security"
        >
          <Card>
            <Form layout="vertical" onFinish={handleSave}>
              <Title level={5}>密码设置</Title>
              
              <Form.Item
                name="currentPassword"
                label="当前密码"
                rules={[{ required: true, message: '请输入当前密码' }]}
              >
                <Input.Password />
              </Form.Item>

              <Form.Item
                name="newPassword"
                label="新密码"
                rules={[
                  { required: true, message: '请输入新密码' },
                  { min: 8, message: '密码长度至少8位' }
                ]}
              >
                <Input.Password />
              </Form.Item>

              <Form.Item
                name="confirmPassword"
                label="确认新密码"
                rules={[
                  { required: true, message: '请确认新密码' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('newPassword') === value) {
                        return Promise.resolve();
                      }
                      return Promise.reject(new Error('两次输入的密码不一致'));
                    },
                  }),
                ]}
              >
                <Input.Password />
              </Form.Item>

              <Divider />

              <Title level={5}>登录安全</Title>
              
              <Form.Item label="两步验证">
                <Switch />
              </Form.Item>

              <Form.Item label="登录设备管理">
                <Button>查看设备</Button>
              </Form.Item>

              <Form.Item label="登录历史">
                <Button>查看历史</Button>
              </Form.Item>

              <Divider />

              <Title level={5}>数据导出</Title>
              
              <Form.Item label="导出个人数据">
                <Button>导出数据</Button>
              </Form.Item>

              <Form.Item>
                <Button type="primary" icon={<SaveOutlined />} loading={loading}>
                  保存设置
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>
      </Tabs>
    </div>
  );
};

export default Settings; 