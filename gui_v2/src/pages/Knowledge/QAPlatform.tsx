import React, { useState } from 'react';
import { 
  Table, 
  Button, 
  Space, 
  Tag, 
  Input, 
  Select, 
  Card, 
  Typography,
  Dropdown,
  Menu,
  Modal,
  Form,
  message,
  Badge,
  Tooltip
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { 
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  MoreOutlined,
  FilterOutlined,
  ExportOutlined,
  CheckOutlined,
  CloseOutlined
} from '@ant-design/icons';
import { QAPair } from './types';

const { Search } = Input;
const { Option } = Select;
const { Title } = Typography;

// 示例数据
const qaData: QAPair[] = [
  {
    id: 1,
    question: '如何重置密码？',
    answer: '根据知识库内容，重置密码的步骤如下：\n1. 点击登录页面的"忘记密码"按钮\n2. 输入你的邮箱地址\n3. 检查邮箱并点击重置链接\n4. 设置新密码',
    asker: '张三',
    createdAt: '2024-01-15 10:30',
    category: '账号管理',
    relatedKnowledgeIds: [1],
  },
  {
    id: 2,
    question: '系统登录失败怎么办？',
    answer: '如果系统登录失败，请尝试以下解决方案：\n1. 检查网络连接\n2. 确认用户名和密码正确\n3. 清除浏览器缓存\n4. 联系技术支持',
    asker: '李四',
    createdAt: '2024-01-15 09:15',
    category: '系统问题',
    relatedKnowledgeIds: [2],
  },
  {
    id: 3,
    question: '如何申请权限？',
    answer: '申请权限的流程如下：\n1. 登录系统\n2. 进入权限申请页面\n3. 选择需要的权限类型\n4. 填写申请理由\n5. 提交申请等待审核',
    asker: '王五',
    createdAt: '2024-01-14 16:45',
    category: '权限管理',
    relatedKnowledgeIds: [3],
  },
];

// 状态配置
const statusConfig = {
  pending: { text: '待审核', color: 'processing', icon: <ClockCircleOutlined /> },
  approved: { text: '已审核', color: 'success', icon: <CheckCircleOutlined /> },
  rejected: { text: '已拒绝', color: 'error', icon: <CloseCircleOutlined /> },
};

const QAPlatform: React.FC = () => {
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [searchText, setSearchText] = useState('');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [editingQA, setEditingQA] = useState<QAPair | null>(null);
  const [form] = Form.useForm();

  // 表格列配置
  const columns: ColumnsType<QAPair> = [
    {
      title: '问题',
      dataIndex: 'question',
      key: 'question',
      width: 300,
      render: (text, record) => (
        <div>
          <div style={{ fontWeight: 500, color: '#1890ff', cursor: 'pointer' }}>
            {text}
          </div>
          <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
            提问人: {record.asker} • {record.createdAt}
          </div>
        </div>
      ),
    },
    {
      title: '答案',
      dataIndex: 'answer',
      key: 'answer',
      width: 400,
      render: (text) => (
        <div style={{ 
          maxHeight: 60, 
          overflow: 'hidden',
          fontSize: 12,
          color: '#666'
        }}>
          {text.length > 100 ? `${text.substring(0, 100)}...` : text}
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: () => {
        const status = 'pending'; // 这里应该从数据中获取
        const config = statusConfig[status as keyof typeof statusConfig];
        return (
          <Badge 
            status={config.color as any} 
            text={config.text}
            icon={config.icon}
          />
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Dropdown
          overlay={
            <Menu>
              <Menu.Item key="view" icon={<EyeOutlined />}>
                查看详情
              </Menu.Item>
              <Menu.Item key="edit" icon={<EditOutlined />}>
                编辑答案
              </Menu.Item>
              <Menu.Item key="approve" icon={<CheckOutlined />}>
                审核通过
              </Menu.Item>
              <Menu.Item key="reject" icon={<CloseOutlined />}>
                拒绝
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item key="delete" icon={<DeleteOutlined />} danger>
                删除
              </Menu.Item>
            </Menu>
          }
        >
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
  ];

  // 处理批量审核
  const handleBatchApprove = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请选择要审核的问答');
      return;
    }
    Modal.confirm({
      title: '批量审核',
      content: `确定要审核通过选中的 ${selectedRowKeys.length} 个问答吗？`,
      onOk: () => {
        message.success('批量审核成功');
        setSelectedRowKeys([]);
      },
    });
  };

  // 处理编辑答案
  const handleEditAnswer = (record: QAPair) => {
    setEditingQA(record);
    form.setFieldsValue({
      question: record.question,
      answer: record.answer,
      category: record.category,
    });
    setIsEditModalVisible(true);
  };

  // 处理表单提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      console.log('更新问答:', values);
      message.success('问答更新成功');
      setIsEditModalVisible(false);
      setEditingQA(null);
      form.resetFields();
    } catch (error) {
      console.error('表单验证失败:', error);
    }
  };

  // 行选择配置
  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  return (
    <div>
      {/* 页面标题和工具栏 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>问答管理</Title>
          <Space>
            <Button 
              type="primary" 
              icon={<CheckOutlined />}
              onClick={handleBatchApprove}
              disabled={selectedRowKeys.length === 0}
            >
              批量审核 ({selectedRowKeys.length})
            </Button>
            <Button icon={<ExportOutlined />}>导出</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Select
              value={selectedStatus}
              onChange={setSelectedStatus}
              style={{ width: 120 }}
              placeholder="状态筛选"
            >
              <Option value="all">全部状态</Option>
              <Option value="pending">待审核</Option>
              <Option value="approved">已审核</Option>
              <Option value="rejected">已拒绝</Option>
            </Select>
            
            <Select
              placeholder="分类筛选"
              style={{ width: 150 }}
              allowClear
            >
              <Option value="account">账号管理</Option>
              <Option value="system">系统问题</Option>
              <Option value="permission">权限管理</Option>
            </Select>
          </Space>
          
          <Search
            placeholder="搜索问题或答案..."
            style={{ width: 300 }}
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>
      </div>

      {/* 统计卡片 */}
      <div style={{ marginBottom: 24 }}>
        <Space size="large">
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1890ff' }}>
                {qaData.length}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>总问答数</div>
            </div>
          </Card>
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#faad14' }}>
                {qaData.filter(qa => qa.id === 1).length}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>待审核</div>
            </div>
          </Card>
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#52c41a' }}>
                {qaData.filter(qa => qa.id === 2).length}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>已审核</div>
            </div>
          </Card>
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ff4d4f' }}>
                {qaData.filter(qa => qa.id === 3).length}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>已拒绝</div>
            </div>
          </Card>
        </Space>
      </div>

      {/* 问答表格 */}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={qaData}
        rowSelection={rowSelection}
        pagination={{
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条记录`,
        }}
        onRow={(record) => ({
          onDoubleClick: () => handleEditAnswer(record),
        })}
      />

      {/* 编辑答案弹窗 */}
      <Modal
        title="编辑答案"
        open={isEditModalVisible}
        onOk={handleSubmit}
        onCancel={() => {
          setIsEditModalVisible(false);
          setEditingQA(null);
          form.resetFields();
        }}
        width={800}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="question"
            label="问题"
          >
            <Input.TextArea rows={2} disabled />
          </Form.Item>
          
          <Form.Item
            name="answer"
            label="答案"
            rules={[{ required: true, message: '请输入答案' }]}
          >
            <Input.TextArea rows={8} placeholder="请输入答案内容" />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
          >
            <Select placeholder="请选择分类">
              <Option value="account">账号管理</Option>
              <Option value="system">系统问题</Option>
              <Option value="permission">权限管理</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default QAPlatform; 