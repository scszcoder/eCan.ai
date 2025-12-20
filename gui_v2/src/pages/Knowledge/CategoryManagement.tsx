import React, { useState } from 'react';
import { 
  Tree, 
  Button, 
  Modal, 
  Form, 
  Input, 
  Space, 
  Card, 
  Typography,
  message,
  Popconfirm,
  Tooltip,
  Dropdown,
  Menu
} from 'antd';
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  FolderOutlined,
  FileTextOutlined,
  MoreOutlined,
  DragOutlined
} from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

interface CategoryNode extends DataNode {
  key: string;
  title: string;
  children?: CategoryNode[];
  parentKey?: string;
  level: number;
  documentCount?: number;
}

const CategoryManagement: React.FC = () => {
  const { t } = useTranslation();
  const [treeData, setTreeData] = useState<CategoryNode[]>([
    {
      key: 'tech',
      title: '技术Documentation',
      level: 0,
      documentCount: 15,
      children: [
        {
          key: 'tech-user',
          title: 'User指南',
          level: 1,
          parentKey: 'tech',
          documentCount: 8,
          children: [
            {
              key: 'tech-user-basic',
              title: 'BaseOperation',
              level: 2,
              parentKey: 'tech-user',
              documentCount: 3,
            },
            {
              key: 'tech-user-advanced',
              title: 'Advanced功能',
              level: 2,
              parentKey: 'tech-user',
              documentCount: 5,
            },
          ],
        },
        {
          key: 'tech-dev',
          title: 'DevelopmentDocumentation',
          level: 1,
          parentKey: 'tech',
          documentCount: 7,
          children: [
            {
              key: 'tech-dev-api',
              title: 'APIDocumentation',
              level: 2,
              parentKey: 'tech-dev',
              documentCount: 4,
            },
            {
              key: 'tech-dev-sdk',
              title: 'SDKDocumentation',
              level: 2,
              parentKey: 'tech-dev',
              documentCount: 3,
            },
          ],
        },
      ],
    },
    {
      key: 'product',
      title: '产品Documentation',
      level: 0,
      documentCount: 12,
      children: [
        {
          key: 'product-intro',
          title: '产品介绍',
          level: 1,
          parentKey: 'product',
          documentCount: 5,
        },
        {
          key: 'product-manual',
          title: '使用手册',
          level: 1,
          parentKey: 'product',
          documentCount: 7,
        },
      ],
    },
    {
      key: 'management',
      title: '管理Documentation',
      level: 0,
      documentCount: 8,
      children: [
        {
          key: 'management-permission',
          title: 'Permission管理',
          level: 1,
          parentKey: 'management',
          documentCount: 4,
        },
        {
          key: 'management-config',
          title: 'SystemConfiguration',
          level: 1,
          parentKey: 'management',
          documentCount: 4,
        },
      ],
    },
  ]);

  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingNode, setEditingNode] = useState<CategoryNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<CategoryNode | null>(null);
  const [form] = Form.useForm();

  // 生成唯一key
  const generateKey = () => `category_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  // Recursive查找节点
  const findNode = (nodes: CategoryNode[], key: string): CategoryNode | null => {
    for (const node of nodes) {
      if (node.key === key) return node;
      if (node.children) {
        const found = findNode(node.children, key);
        if (found) return found;
      }
    }
    return null;
  };

  // RecursiveUpdate节点
  const updateNode = (nodes: CategoryNode[], key: string, updates: Partial<CategoryNode>): CategoryNode[] => {
    return nodes.map(node => {
      if (node.key === key) {
        return { ...node, ...updates };
      }
      if (node.children) {
        return { ...node, children: updateNode(node.children, key, updates) };
      }
      return node;
    });
  };

  // RecursiveDelete节点
  const deleteNode = (nodes: CategoryNode[], key: string): CategoryNode[] => {
    return nodes.filter(node => {
      if (node.key === key) return false;
      if (node.children) {
        node.children = deleteNode(node.children, key);
      }
      return true;
    });
  };

  // ProcessAddCategory
  const handleAdd = (parentKey?: string) => {
    setEditingNode(null);
    setSelectedNode(parentKey ? findNode(treeData, parentKey) || null : null);
    form.resetFields();
    setIsModalVisible(true);
  };

  // ProcessEditCategory
  const handleEdit = (node: CategoryNode) => {
    setEditingNode(node);
    setSelectedNode(null);
    form.setFieldsValue({
      title: node.title,
    });
    setIsModalVisible(true);
  };

  // ProcessDeleteCategory
  const handleDelete = (node: CategoryNode) => {
    if (node.children && node.children.length > 0) {
      message.warning('该Category下还有子Category，无法Delete');
      return;
    }
    if (node.documentCount && node.documentCount > 0) {
      message.warning('该Category下还有Documentation，无法Delete');
      return;
    }
    
    setTreeData(prev => deleteNode(prev, node.key));
    message.success('CategoryDeleteSuccess');
  };

  // ProcessFormSubmit
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingNode) {
        // Edit模式
        setTreeData(prev => updateNode(prev, editingNode.key, { title: values.title }));
        message.success('CategoryUpdateSuccess');
      } else {
        // 新增模式
        const newNode: CategoryNode = {
          key: generateKey(),
          title: values.title,
          level: selectedNode ? selectedNode.level + 1 : 0,
          parentKey: selectedNode?.key,
          documentCount: 0,
        };

        if (selectedNode) {
          // Add到父节点
          setTreeData(prev => updateNode(prev, selectedNode.key, {
            children: [...(selectedNode.children || []), newNode]
          }));
        } else {
          // Add到根节点
          setTreeData(prev => [...prev, newNode]);
        }
        message.success('CategoryCreateSuccess');
      }
      
      setIsModalVisible(false);
      setEditingNode(null);
      setSelectedNode(null);
      form.resetFields();
    } catch (error) {
      console.error('FormValidateFailed:', error);
    }
  };

  // Render树节点标题
  const renderTitle = (node: CategoryNode) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
      <span>{node.title}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {node.documentCount !== undefined && (
          <span style={{ fontSize: 12, color: '#666' }}>
            ({node.documentCount})
          </span>
        )}
        <Dropdown
          menu={{
            items: [
              { key: 'add', icon: <PlusOutlined />, label: 'Add子Category' },
              { key: 'edit', icon: <EditOutlined />, label: 'Edit' },
              { type: 'divider' },
              { key: 'delete', icon: <DeleteOutlined />, label: 'Delete', danger: true },
            ],
            onClick: ({ key }) => {
              if (key === 'add') handleAdd(node.key);
              else if (key === 'edit') handleEdit(node);
              else if (key === 'delete') handleDelete(node);
            },
          }}
          trigger={['click']}
        >
          <Button type="text" size="small" icon={<MoreOutlined />} />
        </Dropdown>
      </div>
    </div>
  );

  // ConvertData为TreeComponent格式
  const convertToTreeData = (nodes: CategoryNode[]): DataNode[] => {
    return nodes.map(node => ({
      key: node.key,
      title: renderTitle(node),
      icon: node.children && node.children.length > 0 ? <FolderOutlined /> : <FileTextOutlined />,
      children: node.children ? convertToTreeData(node.children) : undefined,
    }));
  };

  return (
    <div>
      {/* Page标题和Tool栏 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>{t('pages.knowledge.categoryManagement')}</Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => handleAdd()}>
            Add根Category
          </Button>
        </div>
      </div>

      {/* Category树 */}
      <Card>
        <Tree
          treeData={convertToTreeData(treeData)}
          defaultExpandAll
          showIcon
          showLine
          draggable
          onDrop={(info) => {
            // 这里CanImplementationDragSort逻辑
            console.log('Drag:', info);
          }}
        />
      </Card>

      {/* Add/EditCategoryModal */}
      <Modal
        title={editingNode ? 'EditCategory' : 'AddCategory'}
        open={isModalVisible}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalVisible(false);
          setEditingNode(null);
          setSelectedNode(null);
          form.resetFields();
        }}
        width={500}
      >
        <Form form={form} layout="vertical">
          {selectedNode && (
            <Form.Item label="父Category">
              <Input value={selectedNode.title} disabled />
            </Form.Item>
          )}
          
          <Form.Item
            name="title"
            label="CategoryName"
            rules={[{ required: true, message: '请InputCategoryName' }]}
          >
            <Input placeholder="请InputCategoryName" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CategoryManagement; 