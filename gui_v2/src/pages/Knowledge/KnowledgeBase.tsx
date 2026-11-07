import React, { useState, useEffect, useMemo } from 'react';
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
import i18n from 'i18next';


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

  const fixedT = useMemo(() => i18n.getFixedT(i18n.language), []);
  // 初始化数据
  useEffect(() => {
    initializeDefaultData();
  }, []);

    // 从 StorageService 获取数据
  const [knowledgeData, setKnowledgeData] = useState<KnowledgeEntry[]>(() => {
    const storedData = StorageDataManager.getKnowledgeEntries() || [];
    return storedData.length > 0 ? storedData : [
      {
        title: fixedT('pages.knowledge.quickStart'),
        content: fixedT('pages.knowledge.knowledgeBase.fallbackContent1'),
        category: fixedT('pages.knowledge.technicalDocumentation'),
        tags: [fixedT('pages.knowledge.knowledgeBase.tagIntro'), fixedT('pages.knowledge.knowledgeBase.tagGuide'), fixedT('pages.knowledge.knowledgeBase.tagQuick')],
        createdAt: '2024-01-15',
        updatedAt: '2024-01-15',
      },
      {
        id: 2,
        title: fixedT('pages.knowledge.apiReference'),
        content: fixedT('pages.knowledge.knowledgeBase.fallbackContent2'),
        category: fixedT('pages.knowledge.technicalDocumentation'),
        tags: ['API', fixedT('pages.knowledge.knowledgeBase.tagDevelopment'), fixedT('pages.knowledge.knowledgeBase.tagInterface')],
        createdAt: '2024-01-14',
        updatedAt: '2024-01-14',
      },
      {
        id: 3,
        title: fixedT('pages.knowledge.userPermissionManagement'),
        content: fixedT('pages.knowledge.knowledgeBase.fallbackContent3'),
        category: fixedT('pages.knowledge.managementDocumentation'),
        tags: [fixedT('pages.knowledge.permissionManagement'), fixedT('pages.knowledge.knowledgeBase.tagManagement'), fixedT('pages.knowledge.knowledgeBase.tagConfiguration')],
        createdAt: '2024-01-13',
        updatedAt: '2024-01-13',
      },
    ];
  });

  // Category树Data
  // 分类树数据
  const treeData = [
    {
      title: t('pages.knowledge.technicalDocumentation'),
      key: 'tech',
      icon: <FolderOutlined />,
      children: [
        {
          title: t('pages.knowledge.knowledgeBase.userGuide'),
          key: 'tech-user',
          icon: <FileTextOutlined />,
        },
        {
          title: t('pages.knowledge.knowledgeBase.developmentDoc'),
          key: 'tech-dev',
          icon: <FileTextOutlined />,
        },
        {
          title: t('pages.knowledge.apiReference'),
          key: 'tech-api',
          icon: <FileTextOutlined />,
        },
      ],
    },
    {
      title: t('pages.knowledge.productDocumentation'),
      key: 'product',
      icon: <FolderOutlined />,
      children: [
        {
          title: t('pages.knowledge.knowledgeBase.productIntro'),
          key: 'product-intro',
          icon: <FileTextOutlined />,
        },
        {
          title: t('pages.knowledge.knowledgeBase.userManual'),
          key: 'product-manual',
          icon: <FileTextOutlined />,
        },
      ],
    },
    {
      title: t('pages.knowledge.managementDocumentation'),
      key: 'management',
      icon: <FolderOutlined />,
      children: [
        {
          title: t('pages.knowledge.permissionManagement'),
          key: 'management-permission',
          icon: <FileTextOutlined />,
        },
        {
          title: t('pages.knowledge.knowledgeBase.systemConfiguration'),
          key: 'management-config',
          icon: <FileTextOutlined />,
        },
      ],
    },
  ];

  // 表格列配置
  const columns: ColumnsType<KnowledgeEntry> = [
    {
      title: t('common.name'),
      dataIndex: 'title',
      key: 'title',
      render: (text, record) => (
        <div>
          <div style={{ fontWeight: 500, color: token.colorPrimary, cursor: 'pointer' }}>
            {text}
          </div>
          <div style={{ fontSize: 'var(--font-size-sm)', color: token.colorTextSecondary, marginTop: 4 }}>
            {record.content.substring(0, 50)}...
          </div>
        </div>
      ),
    },
    {
      title: t('pages.knowledge.knowledgeBase.category'),
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: t('pages.knowledge.knowledgeBase.tags'),
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
      title: t('pages.knowledge.knowledgeBase.updatedAt'),
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 120,
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 120,
      render: (_, record) => {
        const menuItems = [
          { key: 'view', label: t('pages.knowledge.knowledgeBase.view'), icon: <EyeOutlined /> },
          { key: 'edit', label: t('common.edit'), icon: <EditOutlined /> },
          { key: 'version', label: t('pages.knowledge.knowledgeBase.versionHistory'), icon: <HistoryOutlined /> },
          { type: 'divider' as const },
          { key: 'delete', label: t('common.delete'), icon: <DeleteOutlined />, danger: true },
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

  // 在组件内定义菜单项
  const getMenuItems = (record: KnowledgeEntry) => ([
    { key: 'view', label: t('pages.knowledge.knowledgeBase.view'), onClick: () => { setSelectedDocument(record); setIsCollaborationVisible(true); } },
    { key: 'edit', label: t('common.edit'), onClick: () => handleEdit(record) },
    { key: 'version', label: t('pages.knowledge.knowledgeBase.versionHistory'), onClick: () => { setSelectedDocument(record); setIsVersionControlVisible(true); } },
    { type: 'divider' },
    { key: 'delete', label: t('common.delete'), danger: true },
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
              <Tooltip title={t('pages.knowledge.knowledgeBase.view')} key="view"><EyeOutlined /></Tooltip>,
              <Tooltip title={t('common.edit')} key="edit"><EditOutlined onClick={() => handleEdit(item)} /></Tooltip>,
              <Tooltip title={t('common.delete')} key="delete"><DeleteOutlined style={{ color: 'var(--error-text)' }} /></Tooltip>,
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
                  <div style={{ marginBottom: 8, fontSize: 'var(--font-size-sm)' }}>
                    {item.content.substring(0, 60)}...
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    {item.tags?.map((tag, idx) => (
                      <Tag key={tag + '-' + idx}>{tag}</Tag>
                    ))}
                  </div>
                  <div style={{ fontSize: 'var(--font-size-sm)', color: token.colorTextSecondary }}>
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
    console.log('SaveDocumentation:', data);
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
      message.success(t('pages.knowledge.knowledgeBase.newDocumentSuccess'));
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
      {/* 页面标题和工具栏 */}
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
            title={t('pages.knowledge.categoryNavigation')}
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
                showTotal: (total) => t('pages.knowledge.knowledgeBase.totalRecords', { total }),
              }}
            />
          ) : (
            renderCardView()
          )}
        </div>
      </div>

      {/* DocumentationEdit器Modal */}
      <Modal
        title={editingDocument ? t('pages.knowledge.knowledgeBase.editDocumentTitle') : t('pages.knowledge.knowledgeBase.newDocumentTitle')}
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
          message.success(t('pages.knowledge.knowledgeBase.versionRolledBack', { version: version.version }));
        }}
      />

      {/* 协作Modal */}
      <Modal
        title={`${t('pages.knowledge.knowledgeBase.collaborationTitle', { title: '' })}${selectedDocument?.title ?? ''}`}
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
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
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
        title={t('pages.knowledge.knowledgeBase.newDocumentTitle')}
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
            label={t('pages.knowledge.knowledgeBase.documentTitle')}
            rules={[{ required: true, message: t('pages.knowledge.knowledgeBase.enterDocumentTitle') }]}
          >
            <Input placeholder={t('pages.knowledge.knowledgeBase.enterDocumentTitle')} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label={t('pages.knowledge.knowledgeBase.category')}
            rules={[{ required: true, message: t('pages.knowledge.knowledgeBase.enterCategory') }]}
          >
            <Select defaultValue={t('pages.knowledge.technicalDocumentation')} style={{ width: '100%' }}>
              <Option value="tech">{t('pages.knowledge.technicalDocumentation')}</Option>
              <Option value="product">{t('pages.knowledge.productDocumentation')}</Option>
              <Option value="management">{t('pages.knowledge.managementDocumentation')}</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="tags"
            label={t('pages.knowledge.knowledgeBase.tags')}
          >
            <Select mode="tags" defaultValue={[t('pages.knowledge.knowledgeBase.tagIntro'), t('pages.knowledge.knowledgeBase.tagGuide')]} placeholder={t('pages.knowledge.knowledgeBase.enterTag')}>
              <Option value="入门">{t('pages.knowledge.knowledgeBase.tagIntro')}</Option>
              <Option value="指南">{t('pages.knowledge.knowledgeBase.tagGuide')}</Option>
              <Option value="API">API</Option>
              <Option value="Development">{t('pages.knowledge.knowledgeBase.tagDevelopment')}</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="content"
            label={t('pages.knowledge.knowledgeBase.documentContent')}
            rules={[{ required: true, message: t('pages.knowledge.knowledgeBase.enterDocumentContent') }]}
          >
            <Input.TextArea rows={6} placeholder={t('pages.knowledge.knowledgeBase.enterDocumentContent')} />
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