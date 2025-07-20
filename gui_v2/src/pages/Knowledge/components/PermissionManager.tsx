import React, { useState } from 'react';
import { 
  Modal, 
  Table, 
  Button, 
  Space, 
  Tag, 
  Typography, 
  Card, 
  Select,
  Switch,
  message,
  Tooltip,
  Popconfirm,
  Tree,
  Divider,
  Input
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { 
  UserOutlined,
  TeamOutlined,
  LockOutlined,
  UnlockOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  EyeOutlined,
  FileTextOutlined,
  SettingOutlined
} from '@ant-design/icons';

const { Option } = Select;
const { Title, Text } = Typography;

interface Permission {
  id: string;
  name: string;
  description: string;
  category: string;
}

interface Role {
  id: string;
  name: string;
  description: string;
  permissions: string[];
  userCount: number;
  isSystem: boolean;
}

interface UserPermission {
  id: string;
  username: string;
  email: string;
  role: string;
  permissions: string[];
  status: 'active' | 'inactive';
  lastLogin: string;
}

const PermissionManager: React.FC = () => {
  const [selectedUser, setSelectedUser] = useState<UserPermission | null>(null);
  const [isPermissionModalVisible, setIsPermissionModalVisible] = useState(false);
  const [isRoleModalVisible, setIsRoleModalVisible] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);

  // 权限列表
  const permissions: Permission[] = [
    { id: 'read', name: '查看文档', description: '查看知识库中的文档', category: '文档权限' },
    { id: 'write', name: '编辑文档', description: '创建和编辑文档', category: '文档权限' },
    { id: 'delete', name: '删除文档', description: '删除文档', category: '文档权限' },
    { id: 'comment', name: '评论', description: '在文档中添加评论', category: '协作权限' },
    { id: 'approve', name: '审核', description: '审核问答和文档', category: '管理权限' },
    { id: 'admin', name: '管理员', description: '系统管理员权限', category: '管理权限' },
    { id: 'export', name: '导出', description: '导出文档和数据', category: '文档权限' },
    { id: 'import', name: '导入', description: '导入文档和数据', category: '文档权限' },
  ];

  // 角色列表
  const roles: Role[] = [
    {
      id: 'admin',
      name: '管理员',
      description: '拥有所有权限',
      permissions: ['read', 'write', 'delete', 'comment', 'approve', 'admin', 'export', 'import'],
      userCount: 3,
      isSystem: true,
    },
    {
      id: 'editor',
      name: '编辑者',
      description: '可以创建和编辑文档',
      permissions: ['read', 'write', 'comment', 'export'],
      userCount: 8,
      isSystem: false,
    },
    {
      id: 'viewer',
      name: '查看者',
      description: '只能查看文档',
      permissions: ['read', 'comment'],
      userCount: 15,
      isSystem: false,
    },
    {
      id: 'moderator',
      name: '审核员',
      description: '负责审核内容',
      permissions: ['read', 'comment', 'approve'],
      userCount: 5,
      isSystem: false,
    },
  ];

  // 用户权限列表
  const userPermissions: UserPermission[] = [
    {
      id: '1',
      username: '张三',
      email: 'zhangsan@company.com',
      role: 'admin',
      permissions: ['read', 'write', 'delete', 'comment', 'approve', 'admin', 'export', 'import'],
      status: 'active',
      lastLogin: '2024-01-15 14:30',
    },
    {
      id: '2',
      username: '李四',
      email: 'lisi@company.com',
      role: 'editor',
      permissions: ['read', 'write', 'comment', 'export'],
      status: 'active',
      lastLogin: '2024-01-15 10:15',
    },
    {
      id: '3',
      username: '王五',
      email: 'wangwu@company.com',
      role: 'viewer',
      permissions: ['read', 'comment'],
      status: 'active',
      lastLogin: '2024-01-14 16:45',
    },
    {
      id: '4',
      username: '赵六',
      email: 'zhaoliu@company.com',
      role: 'moderator',
      permissions: ['read', 'comment', 'approve'],
      status: 'inactive',
      lastLogin: '2024-01-13 09:20',
    },
  ];

  // 用户权限表格列
  const userColumns: ColumnsType<UserPermission> = [
    {
      title: '用户',
      key: 'user',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{record.username}</div>
          <div style={{ fontSize: 12, color: '#666' }}>{record.email}</div>
        </div>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role) => {
        const roleInfo = roles.find(r => r.id === role);
        return (
          <Tag color={role === 'admin' ? 'red' : role === 'editor' ? 'blue' : 'green'}>
            {roleInfo?.name || role}
          </Tag>
        );
      },
    },
    {
      title: '权限',
      key: 'permissions',
      render: (_, record) => (
        <div>
          {record.permissions.slice(0, 3).map((perm, idx) => {
            const permInfo = permissions.find(p => p.id === perm);
            return (
              <Tag key={perm + '-' + idx} style={{ marginBottom: 4 }}>
                {permInfo?.name || perm}
              </Tag>
            );
          })}
          {record.permissions.length > 3 && (
            <Tag key={record.id + '-more'}>+{record.permissions.length - 3}</Tag>
          )}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'active' ? 'green' : 'red'}>
          {status === 'active' ? '活跃' : '非活跃'}
        </Tag>
      ),
    },
    {
      title: '最后登录',
      dataIndex: 'lastLogin',
      key: 'lastLogin',
      width: 150,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title="编辑权限">
            <Button 
              type="text" 
              size="small" 
              icon={<EditOutlined />}
              onClick={() => {
                setSelectedUser(record);
                setIsPermissionModalVisible(true);
              }}
            />
          </Tooltip>
          <Tooltip title={record.status === 'active' ? '禁用' : '启用'}>
            <Button 
              type="text" 
              size="small" 
              icon={record.status === 'active' ? <LockOutlined /> : <UnlockOutlined />}
              onClick={() => handleToggleUserStatus(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 角色表格列
  const roleColumns: ColumnsType<Role> = [
    {
      title: '角色名称',
      dataIndex: 'name',
      key: 'name',
      render: (name, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{name}</div>
          {record.isSystem && <Tag color="orange">系统角色</Tag>}
        </div>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '权限数量',
      key: 'permissionCount',
      render: (_, record) => (
        <Text>{record.permissions.length} 个权限</Text>
      ),
    },
    {
      title: '用户数量',
      dataIndex: 'userCount',
      key: 'userCount',
      render: (count) => (
        <Text>{count} 个用户</Text>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title="编辑角色">
            <Button 
              type="text" 
              size="small" 
              icon={<EditOutlined />}
              onClick={() => {
                setEditingRole(record);
                setIsRoleModalVisible(true);
              }}
            />
          </Tooltip>
          {!record.isSystem && (
            <Popconfirm
              title="确认删除"
              description="删除角色将影响所有使用该角色的用户"
              onConfirm={() => handleDeleteRole(record)}
            >
              <Tooltip title="删除角色">
                <Button 
                  type="text" 
                  size="small" 
                  icon={<DeleteOutlined />}
                  danger
                />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  // 处理用户状态切换
  const handleToggleUserStatus = (user: UserPermission) => {
    const newStatus = user.status === 'active' ? 'inactive' : 'active';
    message.success(`用户 ${user.username} 已${newStatus === 'active' ? '启用' : '禁用'}`);
  };

  // 处理删除角色
  const handleDeleteRole = (role: Role) => {
    message.success(`角色 ${role.name} 已删除`);
  };

  // 处理权限更新
  const handlePermissionUpdate = (userId: string, newPermissions: string[]) => {
    message.success('权限更新成功');
    setIsPermissionModalVisible(false);
    setSelectedUser(null);
  };

  // 处理角色更新
  const handleRoleUpdate = (roleData: Partial<Role>) => {
    message.success('角色更新成功');
    setIsRoleModalVisible(false);
    setEditingRole(null);
  };

  // 按分类组织权限
  const permissionsByCategory = permissions.reduce((acc, perm) => {
    if (!acc[perm.category]) {
      acc[perm.category] = [];
    }
    acc[perm.category].push(perm);
    return acc;
  }, {} as Record<string, Permission[]>);

  return (
    <div>
      {/* 用户权限管理 */}
      <Card title="用户权限管理" style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />}>
            添加用户
          </Button>
        </div>
        <Table
          columns={userColumns}
          dataSource={userPermissions}
          rowKey="id"
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 个用户`,
          }}
        />
      </Card>

      {/* 角色管理 */}
      <Card title="角色管理" style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />}>
            创建角色
          </Button>
        </div>
        <Table
          columns={roleColumns}
          dataSource={roles}
          rowKey="id"
          pagination={false}
        />
      </Card>

      {/* 权限说明 */}
      <Card title="权限说明">
        <div style={{ display: 'flex', gap: 16 }}>
          {Object.entries(permissionsByCategory).map(([category, perms]) => (
            <div key={category} style={{ flex: 1 }}>
              <Title level={5}>{category}</Title>
              {perms.map(perm => (
                <div key={perm.id} style={{ marginBottom: 8 }}>
                  <Text strong>{perm.name}</Text>
                  <div style={{ fontSize: 12, color: '#666' }}>
                    {perm.description}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Card>

      {/* 用户权限编辑弹窗 */}
      <Modal
        title={`编辑用户权限 - ${selectedUser?.username}`}
        open={isPermissionModalVisible}
        onCancel={() => {
          setIsPermissionModalVisible(false);
          setSelectedUser(null);
        }}
        footer={null}
        width={600}
      >
        {selectedUser && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Text>用户: {selectedUser.username} ({selectedUser.email})</Text>
            </div>
            
            <div style={{ marginBottom: 16 }}>
              <Text strong>角色:</Text>
              <Select
                defaultValue={selectedUser.role}
                style={{ width: 200, marginLeft: 8 }}
              >
                {roles.map(role => (
                  <Option key={role.id} value={role.id}>
                    {role.name}
                  </Option>
                ))}
              </Select>
            </div>

            <Divider />

            <div>
              <Text strong>详细权限:</Text>
              {Object.entries(permissionsByCategory).map(([category, perms]) => (
                <div key={category} style={{ marginTop: 16 }}>
                  <Text type="secondary">{category}</Text>
                  <div style={{ marginTop: 8 }}>
                    {perms.map(perm => (
                      <div key={perm.id} style={{ marginBottom: 8 }}>
                        <Switch
                          defaultChecked={selectedUser.permissions.includes(perm.id)}
                          size="small"
                        />
                        <span style={{ marginLeft: 8 }}>
                          {perm.name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 24, textAlign: 'right' }}>
              <Space>
                <Button onClick={() => setIsPermissionModalVisible(false)}>
                  取消
                </Button>
                <Button type="primary" onClick={() => handlePermissionUpdate(selectedUser.id, [])}>
                  保存
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Modal>

      {/* 角色编辑弹窗 */}
      <Modal
        title={editingRole ? `编辑角色 - ${editingRole.name}` : '创建角色'}
        open={isRoleModalVisible}
        onCancel={() => {
          setIsRoleModalVisible(false);
          setEditingRole(null);
        }}
        footer={null}
        width={600}
      >
        {editingRole && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>角色名称:</Text>
              <Input defaultValue={editingRole.name} style={{ marginTop: 8 }} />
            </div>

            <div style={{ marginBottom: 16 }}>
              <Text strong>描述:</Text>
              <Input.TextArea 
                defaultValue={editingRole.description} 
                style={{ marginTop: 8 }}
                rows={3}
              />
            </div>

            <Divider />

            <div>
              <Text strong>权限设置:</Text>
              {Object.entries(permissionsByCategory).map(([category, perms]) => (
                <div key={category} style={{ marginTop: 16 }}>
                  <Text type="secondary">{category}</Text>
                  <div style={{ marginTop: 8 }}>
                    {perms.map(perm => (
                      <div key={perm.id} style={{ marginBottom: 8 }}>
                        <Switch
                          defaultChecked={editingRole.permissions.includes(perm.id)}
                          size="small"
                        />
                        <span style={{ marginLeft: 8 }}>
                          {perm.name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 24, textAlign: 'right' }}>
              <Space>
                <Button onClick={() => setIsRoleModalVisible(false)}>
                  取消
                </Button>
                <Button type="primary" onClick={() => handleRoleUpdate({})}>
                  保存
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default PermissionManager; 