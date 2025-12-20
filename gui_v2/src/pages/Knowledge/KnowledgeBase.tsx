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
  Typography,
  Tooltip,
  Modal,
  Form,
  Select,
  message,
  theme
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
import { useTranslation } from 'react-i18next';


const { Search } = Input;
const { Title } = Typography;
const { Option } = Select;

const KnowledgeBase: React.FC = () => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
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

  // InitializeData
  useEffect(() => {
    initializeDefaultData();
  }, []);

    // 从StorageServiceGetData
  const [knowledgeData, setKnowledgeData] = useState<KnowledgeEntry[]>(() => {
    const storedData = StorageDataManager.getKnowledgeEntries() || [];
    return storedData.length > 0 ? storedData : [
      {
        id: 1,
        title: 'Fast开始指南',
        content: '本Documentation介绍如何Fast上手使用System...',
        category: '技术Documentation',
        tags: ['入门', '指南', 'Fast'],
        createdAt: '2024-01-15',
        updatedAt: '2024-01-15',
      },
      {
        id: 2,
        title: 'API 参考Documentation',
        content: 'Detailed的 API Interface说明和使用Example...',
        category: '技术Documentation',
        tags: ['API', 'Development', 'Interface'],
        createdAt: '2024-01-14',
        updatedAt: '2024-01-14',
      },
      {
        id: 3,
        title: 'UserPermission管理',
        content: 'SystemPermissionConfiguration和管理说明...',
        category: '管理Documentation',
        tags: ['Permission', '管理', 'Configuration'],
        createdAt: '2024-01-13',
        updatedAt: '2024-01-13',
      },
    ];
  });

  // Category树Data
  const treeData = [
    {
      title: '技术Documentation',
      key: 'tech',
      icon: <FolderOutlined />,
      children: [
        {
          title: 'User指南',
          key: 'tech-user',
          icon: <FileTextOutlined />,
        },
        {
          title: 'DevelopmentDocumentation',
          key: 'tech-dev',
          icon: <FileTextOutlined />,
        },
        {
          title: 'APIDocumentation',
          key: 'tech-api',
          icon: <FileTextOutlined />,
        },
      ],
    },
    {
      title: '产品Documentation',
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
      title: '管理Documentation',
      key: 'management',
      icon: <FolderOutlined />,
      children: [
        {
          title: 'Permission管理',
          key: 'management-permission',
          icon: <FileTextOutlined />,
        },
        {
          title: 'SystemConfiguration',
          key: 'management-config',
          icon: <FileTextOutlined />,
        },
      ],
    },
  ];

  // Table列Configuration
  const columns: ColumnsType<KnowledgeEntry> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (text, record) => (
        <div>
          <div style={{ fontWeight: 500, color: token.colorPrimary, cursor: 'pointer' }}>
            {text}
          </div>
          <div style={{ fontSize: 12, color: token.colorTextSecondary, marginTop: 4 }}>
            {record.content.substring(0, 50)}...
          </div>
        </div>
      ),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: 'Tag',
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
      title: 'UpdateTime',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 120,
    },
    {
      title: 'Operation',
      key: 'action',
      width: 120,
      render: (_, record) => {
        const menuItems = [
          { key: 'view', label: '查看', icon: <EyeOutlined /> },
          { key: 'edit', label: 'Edit', icon: <EditOutlined /> },
          { key: 'version', label: 'Version历史', icon: <HistoryOutlined /> },
          { type: 'divider' as const },
          { key: 'delete', label: 'Delete', icon: <DeleteOutlined />, danger: true },
        ];
        return (
          <Dropdown
            menu={{ items: menuItems, onClick: ({ key }) => {
              if (key === 'view') { setSelectedDocument(record); setIsCollaborationVisible(true); }
              else if (key === 'edit') { handleEdit(record); }
              else if (key === 'version') { setSelectedDocument(record); setIsVersionControlVisible(true); }
              else if (key === 'delete') { /* Delete逻辑 */ }
            }}}
          >
            <Button type="text" icon={<MoreOutlined />} />
          </Dropdown>
        );
      },
    },
  ];

  // 在ComponentInternalDefinitionMenu项
  const getMenuItems = (record: KnowledgeEntry) => ([
    { key: 'view', label: '查看', onClick: () => { setSelectedDocument(record); setIsCollaborationVisible(true); } },
    { key: 'edit', label: 'Edit', onClick: () => handleEdit(record) },
    { key: 'version', label: 'Version历史', onClick: () => { setSelectedDocument(record); setIsVersionControlVisible(true); } },
    { type: 'divider' },
    { key: 'delete', label: 'Delete', danger: true },
  ]);

  // 卡片视图Render
  const renderCardView = () => (
    <Row gutter={[16, 16]}>
      {knowledgeData.map(item => (
        <Col xs={24} sm={12} md={8} lg={6} key={item.id}>
          <Card
            hoverable
            size="small"
            actions={[
              <Tooltip title="查看" key="view"><EyeOutlined /></Tooltip>,
              <Tooltip title="Edit" key="edit"><EditOutlined onClick={() => handleEdit(item)} /></Tooltip>,
              <Tooltip title="Delete" key="delete"><DeleteOutlined style={{ color: '#ff4d4f' }} /></Tooltip>,
            ]}
          >
            <Card.Meta
              title={
                <div style={{ color: token.colorPrimary, cursor: 'pointer' }}>
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
                  <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
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

  // Process新建Documentation
  const handleCreate = () => {
    setEditingDocument(null);
    setIsEditorVisible(true);
  };

  // ProcessEditDocumentation
  const handleEdit = (record: KnowledgeEntry) => {
    setEditingDocument(record);
    setIsEditorVisible(true);
  };

  // ProcessDocumentationSave
  const handleDocumentSave = (data: any) => {
    console.log('SaveDocumentation:', data);
    if (editingDocument) {
      // Update现有Documentation
      const updatedDocument = { ...editingDocument, ...data, updatedAt: new Date().toISOString() };
      StorageDataManager.updateKnowledgeEntry(editingDocument.id, updatedDocument);
      setKnowledgeData(prev => prev.map(item => 
        item.id === editingDocument.id ? updatedDocument : item
      ));
    } else {
      // Create新Documentation
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

  // ProcessFormSubmit
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      console.log('新建Documentation:', values);
      message.success('DocumentationCreateSuccess');
      setIsModalVisible(false);
      form.resetFields();
    } catch (error) {
      console.error('FormValidateFailed:', error);
    }
  };

  return (
    <div style={{ 
      backgroundColor: token.colorBgContainer,
      minHeight: '100vh',
      padding: '24px'
    }}>
      {/* Page标题和Tool栏 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0, color: token.colorText }}>{t('pages.knowledge.knowledgeBaseManagement')}</Title>
          <Space>
            <Button 
              type={viewMode === 'list' ? 'primary' : 'default'} 
              icon={<UnorderedListOutlined />}
              onClick={() => setViewMode('list')}
            >
              {t('common.description')}
            </Button>
            <Button 
              type={viewMode === 'card' ? 'primary' : 'default'} 
              icon={<AppstoreOutlined />}
              onClick={() => setViewMode('card')}
            >
              {t('common.card', { defaultValue: 'Card' })}
            </Button>
          </Space>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              {t('common.create')}
            </Button>
            <Button icon={<ImportOutlined />}>{t('pages.knowledge.batchImport')}</Button>
            <Button icon={<ExportOutlined />} onClick={() => setIsDataManagerVisible(true)}>
              {t('pages.knowledge.dataManagement')}
            </Button>
          </Space>
          
          <Space>
            <Button 
              icon={<SearchOutlined />} 
              onClick={() => setIsAdvancedSearchVisible(true)}
            >
              {t('common.search', { defaultValue: 'Search' })}
            </Button>
            <Search
              placeholder={t('common.search', { defaultValue: 'Search...' })}
              style={{ width: 300 }}
              allowClear
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </Space>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* LeftCategory树 */}
        <div style={{ width: 250, flexShrink: 0 }}>
          <Card 
            size="small" 
            title="CategoryNavigation"
            style={{ backgroundColor: token.colorBgElevated }}
          >
            <Tree
              treeData={treeData}
              selectedKeys={selectedCategory === 'all' ? [] : [selectedCategory]}
              onSelect={(keys) => setSelectedCategory(keys[0] as string || 'all')}
              defaultExpandAll
            />
          </Card>
        </div>

        {/* RightContent区 */}
        <div style={{ 
          flex: 1,
          backgroundColor: token.colorBgElevated,
          borderRadius: token.borderRadius,
          padding: '16px'
        }}>
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

      {/* DocumentationEdit器Modal */}
      <Modal
        title={editingDocument ? 'EditDocumentation' : '新建Documentation'}
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

      {/* Version控制Modal */}
      <VersionControl
        visible={isVersionControlVisible}
        onClose={() => {
          setIsVersionControlVisible(false);
          setSelectedDocument(null);
        }}
        documentId={selectedDocument?.id || 0}
        onRevert={(version) => {
          console.log('回滚到Version:', version);
          message.success(`已回滚到Version ${version.version}`);
        }}
      />

      {/* 协作Modal */}
      <Modal
        title={`Documentation协作 - ${selectedDocument?.title}`}
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

      {/* 新建DocumentationModal（保留原有SimpleForm） */}
      <Modal
        title="新建Documentation"
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
            label="Documentation标题"
            rules={[{ required: true, message: '请InputDocumentation标题' }]}
          >
            <Input placeholder="请InputDocumentation标题" />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="Category"
            rules={[{ required: true, message: '请SelectCategory' }]}
          >
            <Select placeholder={t('pages.knowledge.selectCategory')}>
              <Option value="tech">{t('pages.knowledge.technicalDocumentation')}</Option>
              <Option value="product">{t('pages.knowledge.productDocumentation')}</Option>
              <Option value="management">{t('pages.knowledge.managementDocumentation')}</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="tags"
            label="Tag"
          >
            <Select mode="tags" placeholder="请InputTag">
              <Option value="入门">入门</Option>
              <Option value="指南">指南</Option>
              <Option value="API">API</Option>
              <Option value="Development">Development</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="content"
            label="DocumentationContent"
            rules={[{ required: true, message: '请InputDocumentationContent' }]}
          >
            <Input.TextArea rows={6} placeholder="请InputDocumentationContent" />
          </Form.Item>
        </Form>
      </Modal>

      {/* AdvancedSearchModal */}
      <AdvancedSearch
        visible={isAdvancedSearchVisible}
        onClose={() => setIsAdvancedSearchVisible(false)}
        onSearch={(results) => {
          setSearchResults(results as KnowledgeEntry[]);
          setIsAdvancedSearchVisible(false);
        }}
        dataSource={knowledgeData}
      />

      {/* Data管理Modal */}
      <DataManager
        visible={isDataManagerVisible}
        onClose={() => setIsDataManagerVisible(false)}
      />
    </div>
  );
};

export default KnowledgeBase; 