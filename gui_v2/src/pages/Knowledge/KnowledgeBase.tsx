import React, { useState, useEffect } from 'react';
import { 
  Table, 
  Button, 
  Space, 
  Tag, 
  Tree, 
  Card, 
  Row, 
  Col, 
  Input, 
  Dropdown, 
  Menu,
  Typography,
  Tooltip,
  Modal,
  Form,
  Select,
  message
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { 
  PlusOutlined, 
  ImportOutlined, 
  ExportOutlined, 
  SearchOutlined,
  FolderOutlined,
  FileTextOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  MoreOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  HistoryOutlined
} from '@ant-design/icons';
import { KnowledgeEntry } from './types';
import DocumentEditor from './components/DocumentEditor';
import VersionControl from './components/VersionControl';
import Collaboration from './components/Collaboration';
import AdvancedSearch from './components/AdvancedSearch';
import DataManager from './components/DataManager';
import { DataManager as StorageDataManager, initializeDefaultData } from './services/storage';


const { Search } = Input;
const { Title } = Typography;
const { Option } = Select;

const KnowledgeBase: React.FC = () => {
  const [viewMode, setViewMode] = useState<'list' | 'card'>('list');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchText, setSearchText] = useState('');
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isEditorVisible, setIsEditorVisible] = useState(false);
  const [editingDocument, setEditingDocument] = useState<KnowledgeEntry | null>(null);
  const [isVersionControlVisible, setIsVersionControlVisible] = useState(false);
  const [isCollaborationVisible, setIsCollaborationVisible] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<KnowledgeEntry | null>(null);
  const [isAdvancedSearchVisible, setIsAdvancedSearchVisible] = useState(false);
  const [isDataManagerVisible, setIsDataManagerVisible] = useState(false);
  const [searchResults, setSearchResults] = useState<KnowledgeEntry[]>([]);
  const [form] = Form.useForm();

  // 初始化数据
  useEffect(() => {
    initializeDefaultData();
  }, []);

    // 从存储服务获取数据
  const [knowledgeData, setKnowledgeData] = useState<KnowledgeEntry[]>(() => {
    const storedData = StorageDataManager.getKnowledgeEntries() || [];
    return storedData.length > 0 ? storedData : [
      {
        id: 1,
        title: '快速开始指南',
        content: '本文档介绍如何快速上手使用系统...',
        category: '技术文档',
        tags: ['入门', '指南', '快速'],
        createdAt: '2024-01-15',
        updatedAt: '2024-01-15',
      },
      {
        id: 2,
        title: 'API 参考文档',
        content: '详细的 API 接口说明和使用示例...',
        category: '技术文档',
        tags: ['API', '开发', '接口'],
        createdAt: '2024-01-14',
        updatedAt: '2024-01-14',
      },
      {
        id: 3,
        title: '用户权限管理',
        content: '系统权限配置和管理说明...',
        category: '管理文档',
        tags: ['权限', '管理', '配置'],
        createdAt: '2024-01-13',
        updatedAt: '2024-01-13',
      },
    ];
  });

  // 分类树数据
  const treeData = [
    {
      title: '技术文档',
      key: 'tech',
      icon: <FolderOutlined />,
      children: [
        {
          title: '用户指南',
          key: 'tech-user',
          icon: <FileTextOutlined />,
        },
        {
          title: '开发文档',
          key: 'tech-dev',
          icon: <FileTextOutlined />,
        },
        {
          title: 'API文档',
          key: 'tech-api',
          icon: <FileTextOutlined />,
        },
      ],
    },
    {
      title: '产品文档',
      key: 'product',
      icon: <FolderOutlined />,
      children: [
        {
          title: '产品介绍',
          key: 'product-intro',
          icon: <FileTextOutlined />,
        },
        {
          title: '使用手册',
          key: 'product-manual',
          icon: <FileTextOutlined />,
        },
      ],
    },
    {
      title: '管理文档',
      key: 'management',
      icon: <FolderOutlined />,
      children: [
        {
          title: '权限管理',
          key: 'management-permission',
          icon: <FileTextOutlined />,
        },
        {
          title: '系统配置',
          key: 'management-config',
          icon: <FileTextOutlined />,
        },
      ],
    },
  ];

  // 表格列配置
  const columns: ColumnsType<KnowledgeEntry> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (text, record) => (
        <div>
          <div style={{ fontWeight: 500, color: '#1890ff', cursor: 'pointer' }}>
            {text}
          </div>
          <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
            {record.content.substring(0, 50)}...
          </div>
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
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 200,
      render: tags => (
        <Space>
          {tags?.map((tag: string, idx: number) => (
            <Tag key={tag + '-' + idx} color="blue">{tag}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 120,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => {
        const menuItems = [
          { key: 'view', label: '查看', icon: <EyeOutlined /> },
          { key: 'edit', label: '编辑', icon: <EditOutlined /> },
          { key: 'version', label: '版本历史', icon: <HistoryOutlined /> },
          { type: 'divider' as const },
          { key: 'delete', label: '删除', icon: <DeleteOutlined />, danger: true },
        ];
        return (
          <Dropdown
            menu={{ items: menuItems, onClick: ({ key }) => {
              if (key === 'view') { setSelectedDocument(record); setIsCollaborationVisible(true); }
              else if (key === 'edit') { handleEdit(record); }
              else if (key === 'version') { setSelectedDocument(record); setIsVersionControlVisible(true); }
              else if (key === 'delete') { /* 删除逻辑 */ }
            }}}
          >
            <Button type="text" icon={<MoreOutlined />} />
          </Dropdown>
        );
      },
    },
  ];

  // 在组件内部定义菜单项
  const getMenuItems = (record: KnowledgeEntry) => ([
    { key: 'view', label: '查看', onClick: () => { setSelectedDocument(record); setIsCollaborationVisible(true); } },
    { key: 'edit', label: '编辑', onClick: () => handleEdit(record) },
    { key: 'version', label: '版本历史', onClick: () => { setSelectedDocument(record); setIsVersionControlVisible(true); } },
    { type: 'divider' },
    { key: 'delete', label: '删除', danger: true },
  ]);

  // 卡片视图渲染
  const renderCardView = () => (
    <Row gutter={[16, 16]}>
      {knowledgeData.map(item => (
        <Col xs={24} sm={12} md={8} lg={6} key={item.id}>
          <Card
            hoverable
            size="small"
            actions={[
              <Tooltip title="查看" key="view"><EyeOutlined /></Tooltip>,
              <Tooltip title="编辑" key="edit"><EditOutlined onClick={() => handleEdit(item)} /></Tooltip>,
              <Tooltip title="删除" key="delete"><DeleteOutlined style={{ color: '#ff4d4f' }} /></Tooltip>,
            ]}
          >
            <Card.Meta
              title={
                <div style={{ color: '#1890ff', cursor: 'pointer' }}>
                  {item.title}
                </div>
              }
              description={
                <div>
                  <div style={{ marginBottom: 8, fontSize: 12 }}>
                    {item.content.substring(0, 60)}...
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    {item.tags?.map((tag, idx) => (
                      <Tag key={tag + '-' + idx}>{tag}</Tag>
                    ))}
                  </div>
                  <div style={{ fontSize: 12, color: '#666' }}>
                    {item.category} • {item.updatedAt}
                  </div>
                </div>
              }
            />
          </Card>
        </Col>
      ))}
    </Row>
  );

  // 处理新建文档
  const handleCreate = () => {
    setEditingDocument(null);
    setIsEditorVisible(true);
  };

  // 处理编辑文档
  const handleEdit = (record: KnowledgeEntry) => {
    setEditingDocument(record);
    setIsEditorVisible(true);
  };

  // 处理文档保存
  const handleDocumentSave = (data: any) => {
    console.log('保存文档:', data);
    if (editingDocument) {
      // 更新现有文档
      const updatedDocument = { ...editingDocument, ...data, updatedAt: new Date().toISOString() };
      StorageDataManager.updateKnowledgeEntry(editingDocument.id, updatedDocument);
      setKnowledgeData(prev => prev.map(item => 
        item.id === editingDocument.id ? updatedDocument : item
      ));
    } else {
      // 创建新文档
      const newDocument: KnowledgeEntry = {
        id: Date.now(),
        ...data,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      StorageDataManager.addKnowledgeEntry(newDocument);
      setKnowledgeData(prev => [newDocument, ...prev]);
    }
    setIsEditorVisible(false);
    setEditingDocument(null);
  };

  // 处理表单提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      console.log('新建文档:', values);
      message.success('文档创建成功');
      setIsModalVisible(false);
      form.resetFields();
    } catch (error) {
      console.error('表单验证失败:', error);
    }
  };

  return (
    <div>
      {/* 页面标题和工具栏 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>知识库管理</Title>
          <Space>
            <Button 
              type={viewMode === 'list' ? 'primary' : 'default'} 
              icon={<UnorderedListOutlined />}
              onClick={() => setViewMode('list')}
            >
              列表
            </Button>
            <Button 
              type={viewMode === 'card' ? 'primary' : 'default'} 
              icon={<AppstoreOutlined />}
              onClick={() => setViewMode('card')}
            >
              卡片
            </Button>
          </Space>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建文档
            </Button>
            <Button icon={<ImportOutlined />}>批量导入</Button>
            <Button icon={<ExportOutlined />} onClick={() => setIsDataManagerVisible(true)}>
              数据管理
            </Button>
          </Space>
          
          <Space>
            <Button 
              icon={<SearchOutlined />} 
              onClick={() => setIsAdvancedSearchVisible(true)}
            >
              高级搜索
            </Button>
            <Search
              placeholder="搜索文档..."
              style={{ width: 300 }}
              allowClear
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </Space>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* 左侧分类树 */}
        <div style={{ width: 250, flexShrink: 0 }}>
          <Card size="small" title="分类导航">
            <Tree
              treeData={treeData}
              selectedKeys={selectedCategory === 'all' ? [] : [selectedCategory]}
              onSelect={(keys) => setSelectedCategory(keys[0] as string || 'all')}
              defaultExpandAll
            />
          </Card>
        </div>

        {/* 右侧内容区 */}
        <div style={{ flex: 1 }}>
          {viewMode === 'list' ? (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={knowledgeData}
              pagination={{
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `共 ${total} 条记录`,
              }}
            />
          ) : (
            renderCardView()
          )}
        </div>
      </div>

      {/* 文档编辑器弹窗 */}
      <Modal
        title={editingDocument ? '编辑文档' : '新建文档'}
        open={isEditorVisible}
        onCancel={() => {
          setIsEditorVisible(false);
          setEditingDocument(null);
        }}
        footer={null}
        width="90%"
        style={{ top: 20 }}
      >
        <DocumentEditor
          initialData={editingDocument ? {
            title: editingDocument.title,
            content: editingDocument.content,
            category: editingDocument.category,
            tags: editingDocument.tags || [],
          } : undefined}
          onSave={handleDocumentSave}
          onCancel={() => {
            setIsEditorVisible(false);
            setEditingDocument(null);
          }}
        />
      </Modal>

      {/* 版本控制弹窗 */}
      <VersionControl
        visible={isVersionControlVisible}
        onClose={() => {
          setIsVersionControlVisible(false);
          setSelectedDocument(null);
        }}
        documentId={selectedDocument?.id || 0}
        onRevert={(version) => {
          console.log('回滚到版本:', version);
          message.success(`已回滚到版本 ${version.version}`);
        }}
      />

      {/* 协作弹窗 */}
      <Modal
        title={`文档协作 - ${selectedDocument?.title}`}
        open={isCollaborationVisible}
        onCancel={() => {
          setIsCollaborationVisible(false);
          setSelectedDocument(null);
        }}
        footer={null}
        width={800}
        style={{ top: 20 }}
      >
        {selectedDocument && (
          <div>
            <Card size="small" style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 8 }}>
                <span style={{ fontWeight: 500 }}>{selectedDocument.title}</span>
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>
                {selectedDocument.content.substring(0, 200)}...
              </div>
            </Card>
            <Collaboration
              documentId={selectedDocument.id}
              onComment={(comment) => {
                console.log('新评论:', comment);
              }}
            />
          </div>
        )}
      </Modal>

      {/* 新建文档弹窗（保留原有简单表单） */}
      <Modal
        title="新建文档"
        open={isModalVisible}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalVisible(false);
          form.resetFields();
        }}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="文档标题"
            rules={[{ required: true, message: '请输入文档标题' }]}
          >
            <Input placeholder="请输入文档标题" />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="请选择分类">
              <Option value="tech">技术文档</Option>
              <Option value="product">产品文档</Option>
              <Option value="management">管理文档</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="tags"
            label="标签"
          >
            <Select mode="tags" placeholder="请输入标签">
              <Option value="入门">入门</Option>
              <Option value="指南">指南</Option>
              <Option value="API">API</Option>
              <Option value="开发">开发</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="content"
            label="文档内容"
            rules={[{ required: true, message: '请输入文档内容' }]}
          >
            <Input.TextArea rows={6} placeholder="请输入文档内容" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 高级搜索弹窗 */}
      <AdvancedSearch
        visible={isAdvancedSearchVisible}
        onClose={() => setIsAdvancedSearchVisible(false)}
        onSearch={(results) => {
          setSearchResults(results as KnowledgeEntry[]);
          setIsAdvancedSearchVisible(false);
        }}
        dataSource={knowledgeData}
      />

      {/* 数据管理弹窗 */}
      <DataManager
        visible={isDataManagerVisible}
        onClose={() => setIsDataManagerVisible(false)}
      />
    </div>
  );
};

export default KnowledgeBase; 