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
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
  const [selectedUser, setSelectedUser] = useState<UserPermission | null>(null);
  const [isPermissionModalVisible, setIsPermissionModalVisible] = useState(false);
  const [isRoleModalVisible, setIsRoleModalVisible] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);

  // PermissionList
  const permissions: Permission[] = [
    { id: 'read', name: '查看Documentation', description: '查看知识库中的Documentation', category: 'DocumentationPermission' },
    { id: 'write', name: 'EditDocumentation', description: 'Create和EditDocumentation', category: 'DocumentationPermission' },
    { id: 'delete', name: 'DeleteDocumentation', description: 'DeleteDocumentation', category: 'DocumentationPermission' },
    { id: 'comment', name: '评论', description: '在Documentation中Add评论', category: '协作Permission' },
    { id: 'approve', name: '审核', description: '审核问答和Documentation', category: '管理Permission' },
    { id: 'admin', name: '管理员', description: 'System管理员Permission', category: '管理Permission' },
    { id: 'export', name: 'Export', description: 'ExportDocumentation和Data', category: 'DocumentationPermission' },
    { id: 'import', name: 'Import', description: 'ImportDocumentation和Data', category: 'DocumentationPermission' },
  ];

  // RoleList
  const roles: Role[] = [
    {
      id: 'admin',
      name: '管理员',
      description: '拥有AllPermission',
      permissions: ['read', 'write', 'delete', 'comment', 'approve', 'admin', 'export', 'import'],
      userCount: 3,
      isSystem: true,
    },
    {
      id: 'editor',
      name: 'Edit者',
      description: 'CanCreate和EditDocumentation',
      permissions: ['read', 'write', 'comment', 'export'],
      userCount: 8,
      isSystem: false,
    },
    {
      id: 'viewer',
      name: '查看者',
      description: '只能查看Documentation',
      permissions: ['read', 'comment'],
      userCount: 15,
      isSystem: false,
    },
    {
      id: 'moderator',
      name: '审核员',
      description: '负责审核Content',
      permissions: ['read', 'comment', 'approve'],
      userCount: 5,
      isSystem: false,
    },
  ];

  // UserPermissionList
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

  // UserPermissionTable列
  const userColumns: ColumnsType<UserPermission> = [
    {
      title: 'User',
      key: 'user',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{record.username}</div>
          <div style={{ fontSize: 12, color: '#666' }}>{record.email}</div>
        </div>
      ),
    },
    {
      title: 'Role',
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
      title: 'Permission',
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
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'active' ? 'green' : 'red'}>
          {status === 'active' ? '活跃' : '非活跃'}
        </Tag>
      ),
    },
    {
      title: '最后Login',
      dataIndex: 'lastLogin',
      key: 'lastLogin',
      width: 150,
    },
    {
      title: 'Operation',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title="EditPermission">
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
          <Tooltip title={record.status === 'active' ? 'Disabled' : 'Enabled'}>
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

  // RoleTable列
  const roleColumns: ColumnsType<Role> = [
    {
      title: 'RoleName',
      dataIndex: 'name',
      key: 'name',
      render: (name, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{name}</div>
          {record.isSystem && <Tag color="orange">SystemRole</Tag>}
        </div>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: 'PermissionCount',
      key: 'permissionCount',
      render: (_, record) => (
        <Text>{record.permissions.length} 个Permission</Text>
      ),
    },
    {
      title: 'UserCount',
      dataIndex: 'userCount',
      key: 'userCount',
      render: (count) => (
        <Text>{count} 个User</Text>
      ),
    },
    {
      title: 'Operation',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title="EditRole">
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
              title="ConfirmDelete"
              description="DeleteRole将影响All使用该Role的User"
              onConfirm={() => handleDeleteRole(record)}
            >
              <Tooltip title="DeleteRole">
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

  // ProcessUserStatusToggle
  const handleToggleUserStatus = (user: UserPermission) => {
    const newStatus = user.status === 'active' ? 'inactive' : 'active';
    message.success(`User ${user.username} 已${newStatus === 'active' ? 'Enabled' : 'Disabled'}`);
  };

  // ProcessDeleteRole
  const handleDeleteRole = (role: Role) => {
    message.success(`Role ${role.name} 已Delete`);
  };

  // ProcessPermissionUpdate
  const handlePermissionUpdate = (userId: string, newPermissions: string[]) => {
    message.success('PermissionUpdateSuccess');
    setIsPermissionModalVisible(false);
    setSelectedUser(null);
  };

  // ProcessRoleUpdate
  const handleRoleUpdate = (roleData: Partial<Role>) => {
    message.success('RoleUpdateSuccess');
    setIsRoleModalVisible(false);
    setEditingRole(null);
  };

  // 按Category组织Permission
  const permissionsByCategory = permissions.reduce((acc, perm) => {
    if (!acc[perm.category]) {
      acc[perm.category] = [];
    }
    acc[perm.category].push(perm);
    return acc;
  }, {} as Record<string, Permission[]>);

  return (
    <div>
      {/* User Permission Management */}
      <Card title={t('pages.knowledge.userPermissionManagement')} style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />}>
            AddUser
          </Button>
        </div>
        <Table
          columns={userColumns}
          dataSource={userPermissions}
          rowKey="id"
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 个User`,
          }}
        />
      </Card>

      {/* Role Management */}
      <Card title={t('pages.knowledge.roleManagement')} style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />}>
            CreateRole
          </Button>
        </div>
        <Table
          columns={roleColumns}
          dataSource={roles}
          rowKey="id"
          pagination={false}
        />
      </Card>

      {/* Permission说明 */}
      <Card title="Permission说明">
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

      {/* UserPermissionEditModal */}
      <Modal
        title={`EditUserPermission - ${selectedUser?.username}`}
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
              <Text>User: {selectedUser.username} ({selectedUser.email})</Text>
            </div>
            
            <div style={{ marginBottom: 16 }}>
              <Text strong>Role:</Text>
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
              <Text strong>DetailedPermission:</Text>
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
                  Cancel
                </Button>
                <Button type="primary" onClick={() => handlePermissionUpdate(selectedUser.id, [])}>
                  Save
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Modal>

      {/* RoleEditModal */}
      <Modal
        title={editingRole ? `EditRole - ${editingRole.name}` : 'CreateRole'}
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
              <Text strong>RoleName:</Text>
              <Input defaultValue={editingRole.name} style={{ marginTop: 8 }} />
            </div>

            <div style={{ marginBottom: 16 }}>
              <Text strong>Description:</Text>
              <Input.TextArea 
                defaultValue={editingRole.description} 
                style={{ marginTop: 8 }}
                rows={3}
              />
            </div>

            <Divider />

            <div>
              <Text strong>PermissionSettings:</Text>
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
                  Cancel
                </Button>
                <Button type="primary" onClick={() => handleRoleUpdate({})}>
                  Save
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