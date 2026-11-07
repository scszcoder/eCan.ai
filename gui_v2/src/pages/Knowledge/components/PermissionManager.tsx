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
    { id: 'read', name: t('pages.knowledge.permissionManager.viewDocuments'), description: t('pages.knowledge.permissionManager.viewDocumentsDesc'), category: t('pages.knowledge.permissionManager.documentPermission') },
    { id: 'write', name: t('pages.knowledge.permissionManager.editDocuments'), description: t('pages.knowledge.permissionManager.editDocumentsDesc'), category: t('pages.knowledge.permissionManager.documentPermission') },
    { id: 'delete', name: t('pages.knowledge.permissionManager.deleteDocuments'), description: t('pages.knowledge.permissionManager.deleteDocumentsDesc'), category: t('pages.knowledge.permissionManager.documentPermission') },
    { id: 'comment', name: t('pages.knowledge.permissionManager.comment'), description: t('pages.knowledge.permissionManager.commentDesc'), category: t('pages.knowledge.permissionManager.collaborationPermission') },
    { id: 'approve', name: t('pages.knowledge.permissionManager.approve'), description: t('pages.knowledge.permissionManager.approveDesc'), category: t('pages.knowledge.permissionManager.managementPermission') },
    { id: 'admin', name: t('pages.knowledge.permissionManager.administrator'), description: t('pages.knowledge.permissionManager.administratorDesc'), category: t('pages.knowledge.permissionManager.managementPermission') },
    { id: 'export', name: t('pages.knowledge.permissionManager.exportData'), description: t('pages.knowledge.permissionManager.exportDataDesc'), category: t('pages.knowledge.permissionManager.documentPermission') },
    { id: 'import', name: t('pages.knowledge.permissionManager.importData'), description: t('pages.knowledge.permissionManager.importDataDesc'), category: t('pages.knowledge.permissionManager.documentPermission') },
  ];

  // RoleList
  const roles: Role[] = [
    {
      id: 'admin',
      name: t('pages.knowledge.permissionManager.administrator'),
      description: t('pages.knowledge.permissionManager.administratorRoleDesc'),
      permissions: ['read', 'write', 'delete', 'comment', 'approve', 'admin', 'export', 'import'],
      userCount: 3,
      isSystem: true,
    },
    {
      id: 'editor',
      name: t('pages.knowledge.permissionManager.editor'),
      description: t('pages.knowledge.permissionManager.editorDesc'),
      permissions: ['read', 'write', 'comment', 'export'],
      userCount: 8,
      isSystem: false,
    },
    {
      id: 'viewer',
      name: t('pages.knowledge.permissionManager.viewer'),
      description: t('pages.knowledge.permissionManager.viewerDesc'),
      permissions: ['read', 'comment'],
      userCount: 15,
      isSystem: false,
    },
    {
      id: 'moderator',
      name: t('pages.knowledge.permissionManager.reviewer'),
      description: t('pages.knowledge.permissionManager.reviewerDesc'),
      permissions: ['read', 'comment', 'approve'],
      userCount: 5,
      isSystem: false,
    },
  ];

  // UserPermissionList
  const userPermissions: UserPermission[] = [
    {
      id: '1',
      username: t('pages.knowledge.permissionManager.user.zhangsan'),
      email: 'zhangsan@company.com',
      role: 'admin',
      permissions: ['read', 'write', 'delete', 'comment', 'approve', 'admin', 'export', 'import'],
      status: 'active',
      lastLogin: '2024-01-15 14:30',
    },
    {
      id: '2',
      username: t('pages.knowledge.permissionManager.user.lisi'),
      email: 'lisi@company.com',
      role: 'editor',
      permissions: ['read', 'write', 'comment', 'export'],
      status: 'active',
      lastLogin: '2024-01-15 10:15',
    },
    {
      id: '3',
      username: t('pages.knowledge.permissionManager.user.wangwu'),
      email: 'wangwu@company.com',
      role: 'viewer',
      permissions: ['read', 'comment'],
      status: 'active',
      lastLogin: '2024-01-14 16:45',
    },
    {
      id: '4',
      username: t('pages.knowledge.permissionManager.user.zhaoliu'),
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
      title: t('pages.knowledge.permissionManager.user'),
      key: 'user',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{record.username}</div>
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>{record.email}</div>
        </div>
      ),
    },
    {
      title: t('pages.knowledge.permissionManager.role'),
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
      title: t('pages.knowledge.permissionManager.permission'),
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
      title: t('pages.knowledge.permissionManager.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'active' ? 'green' : 'red'}>
          {status === 'active' ? t('pages.knowledge.permissionManager.active') : t('pages.knowledge.permissionManager.inactive')}
        </Tag>
      ),
    },
    {
      title: t('pages.knowledge.permissionManager.lastLogin'),
      dataIndex: 'lastLogin',
      key: 'lastLogin',
      width: 150,
    },
    {
      title: t('pages.knowledge.permissionManager.actions'),
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title={t('pages.knowledge.permissionManager.editPermission')}>
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
          <Tooltip title={record.status === 'active' ? t('pages.knowledge.permissionManager.disable') : t('pages.knowledge.permissionManager.enable')}>
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
      title: t('pages.knowledge.permissionManager.roleName'),
      dataIndex: 'name',
      key: 'name',
      render: (name, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{name}</div>
          {record.isSystem && <Tag color="orange">{t('pages.knowledge.permissionManager.systemRole')}</Tag>}
        </div>
      ),
    },
    {
      title: t('pages.knowledge.permissionManager.description'),
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: t('pages.knowledge.permissionManager.permissionsCount'),
      key: 'permissionCount',
      render: (_, record) => (
        <Text>{t('pages.knowledge.permissionManager.permissionsCountValue', { count: record.permissions.length })}</Text>
      ),
    },
    {
      title: t('pages.knowledge.permissionManager.userCount'),
      dataIndex: 'userCount',
      key: 'userCount',
      render: (count) => (
        <Text>{t('pages.knowledge.permissionManager.usersCount', { count })}</Text>
      ),
    },
    {
      title: t('pages.knowledge.permissionManager.actions'),
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title={t('pages.knowledge.permissionManager.editRole')}>
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
              title={t('pages.knowledge.permissionManager.confirmDelete')}
              description={t('pages.knowledge.permissionManager.deleteRoleWarning')}
              onConfirm={() => handleDeleteRole(record)}
            >
              <Tooltip title={t('pages.knowledge.permissionManager.deleteRole')}>
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
    message.success(t('pages.knowledge.permissionManager.userStatusChanged', { username: user.username, status: newStatus === 'active' ? t('pages.knowledge.permissionManager.enabled') : t('pages.knowledge.permissionManager.disabled') }));
  };

  // ProcessDeleteRole
  const handleDeleteRole = (role: Role) => {
    message.success(t('pages.knowledge.permissionManager.roleDeleted', { name: role.name }));
  };

  // ProcessPermissionUpdate
  const handlePermissionUpdate = (userId: string, newPermissions: string[]) => {
    message.success(t('pages.knowledge.permissionManager.permissionUpdateSuccess'));
    setIsPermissionModalVisible(false);
    setSelectedUser(null);
  };

  // ProcessRoleUpdate
  const handleRoleUpdate = (roleData: Partial<Role>) => {
    message.success(t('pages.knowledge.permissionManager.roleUpdateSuccess'));
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
            {t('pages.knowledge.permissionManager.addUser')}
          </Button>
        </div>
        <Table
          columns={userColumns}
          dataSource={userPermissions}
          rowKey="id"
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => t('pages.knowledge.permissionManager.totalUsers', { total }),
          }}
        />
      </Card>

      {/* Role Management */}
      <Card title={t('pages.knowledge.roleManagement')} style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />}>
            {t('pages.knowledge.permissionManager.createRole')}
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
      <Card title={t('pages.knowledge.permissionManager.permissionDescription')}>
        <div style={{ display: 'flex', gap: 16 }}>
          {Object.entries(permissionsByCategory).map(([category, perms]) => (
            <div key={category} style={{ flex: 1 }}>
              <Title level={5}>{t(`pages.knowledge.permissionManager.cat.${category}`, category)}</Title>
              {perms.map(perm => (
                <div key={perm.id} style={{ marginBottom: 8 }}>
                  <Text strong>{perm.name}</Text>
                  <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
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
        title={t('pages.knowledge.permissionManager.editUserPermission', { username: selectedUser?.username })}
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
              <Text>{t('pages.knowledge.permissionManager.userLabel')}: {selectedUser.username} ({selectedUser.email})</Text>
            </div>
            
            <div style={{ marginBottom: 16 }}>
              <Text strong>{t('pages.knowledge.permissionManager.roleLabel')}:</Text>
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
              <Text strong>{t('pages.knowledge.permissionManager.detailedPermissions')}:</Text>
              {Object.entries(permissionsByCategory).map(([category, perms]) => (
                <div key={category} style={{ marginTop: 16 }}>
                  <Text type="secondary">{t(`pages.knowledge.permissionManager.cat.${category}`, category)}</Text>
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
                  {t('common.cancel')}
                </Button>
                <Button type="primary" onClick={() => handlePermissionUpdate(selectedUser.id, [])}>
                  {t('common.save')}
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Modal>

      {/* RoleEditModal */}
      <Modal
        title={editingRole ? t('pages.knowledge.permissionManager.editRoleTitle', { name: editingRole.name }) : t('pages.knowledge.permissionManager.createRole')}
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
              <Text strong>{t('pages.knowledge.permissionManager.roleName')}:</Text>
              <Input defaultValue={editingRole.name} style={{ marginTop: 8 }} />
            </div>

            <div style={{ marginBottom: 16 }}>
              <Text strong>{t('pages.knowledge.permissionManager.description')}:</Text>
              <Input.TextArea 
                defaultValue={editingRole.description} 
                style={{ marginTop: 8 }}
                rows={3}
              />
            </div>

            <Divider />

            <div>
              <Text strong>{t('pages.knowledge.permissionManager.permissionSettings')}:</Text>
              {Object.entries(permissionsByCategory).map(([category, perms]) => (
                <div key={category} style={{ marginTop: 16 }}>
                  <Text type="secondary">{t(`pages.knowledge.permissionManager.cat.${category}`, category)}</Text>
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
                  {t('common.cancel')}
                </Button>
                <Button type="primary" onClick={() => handleRoleUpdate({})}>
                  {t('common.save')}
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