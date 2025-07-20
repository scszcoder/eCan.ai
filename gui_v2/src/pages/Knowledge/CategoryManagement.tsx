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
  const [treeData, setTreeData] = useState<CategoryNode[]>([
    {
      key: 'tech',
      title: '技术文档',
      level: 0,
      documentCount: 15,
      children: [
        {
          key: 'tech-user',
          title: '用户指南',
          level: 1,
          parentKey: 'tech',
          documentCount: 8,
          children: [
            {
              key: 'tech-user-basic',
              title: '基础操作',
              level: 2,
              parentKey: 'tech-user',
              documentCount: 3,
            },
            {
              key: 'tech-user-advanced',
              title: '高级功能',
              level: 2,
              parentKey: 'tech-user',
              documentCount: 5,
            },
          ],
        },
        {
          key: 'tech-dev',
          title: '开发文档',
          level: 1,
          parentKey: 'tech',
          documentCount: 7,
          children: [
            {
              key: 'tech-dev-api',
              title: 'API文档',
              level: 2,
              parentKey: 'tech-dev',
              documentCount: 4,
            },
            {
              key: 'tech-dev-sdk',
              title: 'SDK文档',
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
      title: '产品文档',
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
      title: '管理文档',
      level: 0,
      documentCount: 8,
      children: [
        {
          key: 'management-permission',
          title: '权限管理',
          level: 1,
          parentKey: 'management',
          documentCount: 4,
        },
        {
          key: 'management-config',
          title: '系统配置',
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

  // 递归查找节点
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

  // 递归更新节点
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

  // 递归删除节点
  const deleteNode = (nodes: CategoryNode[], key: string): CategoryNode[] => {
    return nodes.filter(node => {
      if (node.key === key) return false;
      if (node.children) {
        node.children = deleteNode(node.children, key);
      }
      return true;
    });
  };

  // 处理添加分类
  const handleAdd = (parentKey?: string) => {
    setEditingNode(null);
    setSelectedNode(parentKey ? findNode(treeData, parentKey) || null : null);
    form.resetFields();
    setIsModalVisible(true);
  };

  // 处理编辑分类
  const handleEdit = (node: CategoryNode) => {
    setEditingNode(node);
    setSelectedNode(null);
    form.setFieldsValue({
      title: node.title,
    });
    setIsModalVisible(true);
  };

  // 处理删除分类
  const handleDelete = (node: CategoryNode) => {
    if (node.children && node.children.length > 0) {
      message.warning('该分类下还有子分类，无法删除');
      return;
    }
    if (node.documentCount && node.documentCount > 0) {
      message.warning('该分类下还有文档，无法删除');
      return;
    }
    
    setTreeData(prev => deleteNode(prev, node.key));
    message.success('分类删除成功');
  };

  // 处理表单提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingNode) {
        // 编辑模式
        setTreeData(prev => updateNode(prev, editingNode.key, { title: values.title }));
        message.success('分类更新成功');
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
          // 添加到父节点
          setTreeData(prev => updateNode(prev, selectedNode.key, {
            children: [...(selectedNode.children || []), newNode]
          }));
        } else {
          // 添加到根节点
          setTreeData(prev => [...prev, newNode]);
        }
        message.success('分类创建成功');
      }
      
      setIsModalVisible(false);
      setEditingNode(null);
      setSelectedNode(null);
      form.resetFields();
    } catch (error) {
      console.error('表单验证失败:', error);
    }
  };

  // 渲染树节点标题
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
          overlay={
            <Menu>
              <Menu.Item key="add" icon={<PlusOutlined />} onClick={() => handleAdd(node.key)}>
                添加子分类
              </Menu.Item>
              <Menu.Item key="edit" icon={<EditOutlined />} onClick={() => handleEdit(node)}>
                编辑
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item 
                key="delete" 
                icon={<DeleteOutlined />} 
                danger
                onClick={() => handleDelete(node)}
              >
                删除
              </Menu.Item>
            </Menu>
          }
          trigger={['click']}
        >
          <Button type="text" size="small" icon={<MoreOutlined />} />
        </Dropdown>
      </div>
    </div>
  );

  // 转换数据为Tree组件格式
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
      {/* 页面标题和工具栏 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>分类管理</Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => handleAdd()}>
            添加根分类
          </Button>
        </div>
      </div>

      {/* 分类树 */}
      <Card>
        <Tree
          treeData={convertToTreeData(treeData)}
          defaultExpandAll
          showIcon
          showLine
          draggable
          onDrop={(info) => {
            // 这里可以实现拖拽排序逻辑
            console.log('拖拽:', info);
          }}
        />
      </Card>

      {/* 添加/编辑分类弹窗 */}
      <Modal
        title={editingNode ? '编辑分类' : '添加分类'}
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
            <Form.Item label="父分类">
              <Input value={selectedNode.title} disabled />
            </Form.Item>
          )}
          
          <Form.Item
            name="title"
            label="分类名称"
            rules={[{ required: true, message: '请输入分类名称' }]}
          >
            <Input placeholder="请输入分类名称" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CategoryManagement; 