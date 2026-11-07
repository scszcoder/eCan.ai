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
import { useTranslation } from 'react-i18next';

const { Search } = Input;
const { Option } = Select;
const { Title } = Typography;

// Example Data
const qaData: QAPair[] = [
  {
    id: 1,
    question: 'How to reset password?',
    answer: 'Based on the knowledge base, the steps to reset password are:\n1. Click "Forgot Password" button on login page\n2. Enter your email address\n3. Check email and click reset link\n4. Set new password',
    asker: 'User A',
    createdAt: '2024-01-15 10:30',
    category: 'Account Management',
    relatedKnowledgeIds: [1],
  },
  {
    id: 2,
    question: 'What to do if system login fails?',
    answer: 'If system login fails, please try the following solutions:\n1. Check network connection\n2. Verify username and password are correct\n3. Clear browser cache\n4. Contact technical support',
    asker: 'User B',
    createdAt: '2024-01-15 09:15',
    category: 'System Issues',
    relatedKnowledgeIds: [2],
  },
  {
    id: 3,
    question: 'How to apply for permissions?',
    answer: 'The process to apply for permissions:\n1. Login to system\n2. Go to permission application page\n3. Select the required permission type\n4. Fill in application reason\n5. Submit application and wait for approval',
    asker: 'User C',
    createdAt: '2024-01-14 16:45',
    category: 'Permission Management',
    relatedKnowledgeIds: [3],
  },
];

// Status Configuration (labels resolved in component scope)
const statusConfig = {
  pending: { key: 'pendingStatus', color: 'processing', icon: <ClockCircleOutlined /> },
  approved: { key: 'approvedStatus', color: 'success', icon: <CheckCircleOutlined /> },
  rejected: { key: 'rejectedStatus', color: 'error', icon: <CloseCircleOutlined /> },
};

const QAPlatform: React.FC = () => {
  const { t } = useTranslation();
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [searchText, setSearchText] = useState('');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [editingQA, setEditingQA] = useState<QAPair | null>(null);
  const [form] = Form.useForm();

  // Table column configuration
  const columns: ColumnsType<QAPair> = [
    {
      title: t('pages.knowledge.qaPlatform.question'),
      dataIndex: 'question',
      key: 'question',
      width: 300,
      render: (text, record) => (
        <div key={record.id}>
          <div style={{ fontWeight: 500, color: 'var(--primary-text)', cursor: 'pointer' }}>
            {text}
          </div>
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)', marginTop: 4 }}>
            {t('pages.knowledge.qaPlatform.askedBy')}: {record.asker} • {record.createdAt}
          </div>
        </div>
      ),
    },
    {
      title: t('pages.knowledge.qaPlatform.answer'),
      dataIndex: 'answer',
      key: 'answer',
      width: 400,
      render: (text) => (
        <div key={`answer-${text}`} style={{ 
          maxHeight: 60, 
          overflow: 'hidden',
          fontSize: 'var(--font-size-sm)',
          color: 'var(--text-secondary)'
        }}>
          {text.length > 100 ? `${text.substring(0, 100)}...` : text}
        </div>
      ),
    },
    {
      title: t('pages.knowledge.qaPlatform.category'),
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: t('pages.knowledge.qaPlatform.status'),
      key: 'status',
      width: 100,
      render: (_, record) => {
        const status = 'pending'; // 这里Should从Data中Get
        const config = statusConfig[status as keyof typeof statusConfig];
        return (
          <Badge 
            status={config.color as any} 
            text={t(`pages.knowledge.qaPlatform.${config.key}`)}
            // icon={config.icon} // Badge 没有 icon Property，Remove
          />
        );
      },
    },
    {
      title: t('pages.knowledge.qaPlatform.operation'),
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Dropdown
          menu={{ items: getMenuItems(record), onClick: ({ key }) => {
            if (key === 'view') { /* View details logic */ }
            else if (key === 'edit') { handleEditAnswer(record); }
            else if (key === 'approve') { /* Approve logic */ }
            else if (key === 'reject') { /* Reject logic */ }
            else if (key === 'delete') { /* Delete逻辑 */ }
          }}}
        >
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
  ];

  // Process批量审核
  const handleBatchApprove = () => {
    if (selectedRowKeys.length === 0) {
      message.warning(t('pages.knowledge.qaPlatform.selectToApprove'));
      return;
    }
    Modal.confirm({
      title: t('pages.knowledge.qaPlatform.batchApprove'),
      content: t('pages.knowledge.qaPlatform.batchApproveConfirm', { count: selectedRowKeys.length }),
      onOk: () => {
        message.success(t('pages.knowledge.qaPlatform.batchApproveSuccess'));
        setSelectedRowKeys([]);
      },
    });
  };

  // ProcessEdit答案
  const handleEditAnswer = (record: QAPair) => {
    setEditingQA(record);
    form.setFieldsValue({
      question: record.question,
      answer: record.answer,
      category: record.category,
    });
    setIsEditModalVisible(true);
  };

  // ProcessFormSubmit
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      console.log('Update问答:', values);
      message.success(t('pages.knowledge.qaPlatform.answerUpdateSuccess'));
      setIsEditModalVisible(false);
      setEditingQA(null);
      form.resetFields();
    } catch (error) {
      console.error('FormValidateFailed:', error);
    }
  };

  // 行SelectConfiguration
  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  // Menu items for each QA record
  const getMenuItems = (record: QAPair) => ([
    { key: 'view', label: t('pages.knowledge.qaPlatform.viewDetails'), icon: <EyeOutlined /> },
    { key: 'edit', label: t('pages.knowledge.qaPlatform.editAnswer'), icon: <EditOutlined /> },
    { key: 'approve', label: t('pages.knowledge.qaPlatform.approve'), icon: <CheckOutlined /> },
    { key: 'reject', label: t('pages.knowledge.qaPlatform.reject'), icon: <CloseOutlined /> },
    { type: 'divider' as const },
    { key: 'delete', label: t('pages.knowledge.qaPlatform.delete'), icon: <DeleteOutlined />, danger: true },
  ]);

  return (
    <div>
      {/* Page标题和Tool栏 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>{t('pages.knowledge.qaManagement')}</Title>
          <Space>
            <Button 
              type="primary" 
              icon={<CheckOutlined />}
              onClick={handleBatchApprove}
              disabled={selectedRowKeys.length === 0}
            >
              {t('pages.knowledge.qaPlatform.batchApproveWithCount', { count: selectedRowKeys.length })}
            </Button>
            <Button icon={<ExportOutlined />}>{t('pages.knowledge.qaPlatform.export')}</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Select
              value={selectedStatus}
              onChange={setSelectedStatus}
              style={{ width: 120 }}
              placeholder={t('pages.knowledge.qaPlatform.filterByStatus')}
            >
              <Option value="all">{t('pages.knowledge.qaPlatform.allStatus')}</Option>
              <Option value="pending">{t('pages.knowledge.qaPlatform.pendingStatus')}</Option>
              <Option value="approved">{t('pages.knowledge.qaPlatform.approvedStatus')}</Option>
              <Option value="rejected">{t('pages.knowledge.qaPlatform.rejectedStatus')}</Option>
            </Select>
            
            <Select
              placeholder={t('pages.knowledge.qaPlatform.filterByCategory')}
              style={{ width: 150 }}
              allowClear
            >
              <Option value="account">{t('pages.knowledge.accountManagement')}</Option>
              <Option value="system">{t('pages.knowledge.qaPlatform.systemIssues')}</Option>
              <Option value="permission">{t('pages.knowledge.permissionManagement')}</Option>
            </Select>
          </Space>
          
          <Search
            placeholder={t('pages.knowledge.qaPlatform.searchPlaceholder')}
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
              <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 'bold', color: 'var(--primary-text)' }}>
                {qaData.length}
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>{t('pages.knowledge.qaPlatform.totalQa')}</div>
            </div>
          </Card>
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 'bold', color: 'var(--warning-text)' }}>
                {qaData.filter(qa => qa.id === 1).length}
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>{t('pages.knowledge.qaPlatform.pendingStatus')}</div>
            </div>
          </Card>
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 'bold', color: 'var(--success-text)' }}>
                {qaData.filter(qa => qa.id === 2).length}
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>{t('pages.knowledge.qaPlatform.approvedStatus')}</div>
            </div>
          </Card>
          <Card size="small" style={{ width: 200 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 'bold', color: 'var(--error-text)' }}>
                {qaData.filter(qa => qa.id === 3).length}
              </div>
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>{t('pages.knowledge.qaPlatform.rejectedStatus')}</div>
            </div>
          </Card>
        </Space>
      </div>

      {/* 问答Table */}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={qaData}
        rowSelection={rowSelection}
        pagination={{
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => t('pages.knowledge.qaPlatform.totalRecords', { total }),
        }}
        onRow={(record) => ({
          onDoubleClick: () => handleEditAnswer(record),
        })}
      />

      {/* Edit Answer Modal */}
      <Modal
        title={t('pages.knowledge.qaPlatform.editAnswer')}
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
            label={t('pages.knowledge.qaPlatform.question')}
          >
            <Input.TextArea rows={2} disabled />
          </Form.Item>
          
          <Form.Item
            name="answer"
            label={t('pages.knowledge.qaPlatform.answer')}
            rules={[{ required: true, message: t('pages.knowledge.qaPlatform.answerRequired') }]}
          >
            <Input.TextArea rows={8} placeholder={t('pages.knowledge.qaPlatform.answerPlaceholder')} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label={t('pages.knowledge.qaPlatform.category')}
          >
            <Select placeholder={t('pages.knowledge.selectCategory')}>
              <Option value="account">{t('pages.knowledge.accountManagement')}</Option>
              <Option value="system">{t('pages.knowledge.qaPlatform.systemIssues')}</Option>
              <Option value="permission">{t('pages.knowledge.permissionManagement')}</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default QAPlatform; 