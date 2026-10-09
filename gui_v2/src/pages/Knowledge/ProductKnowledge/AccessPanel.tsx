import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Empty, Input, List, Popconfirm, Row, Select, Space, Table, Tag, Tooltip, Typography,
} from 'antd';
import { DeleteOutlined, PlusOutlined, ReloadOutlined, SafetyOutlined, TeamOutlined, UserAddOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSAccessView, KSConnection, KSMember } from '@/services/ipc/ksApi';
import { PlaneTag } from './ConnectionsPanel';

const { Text } = Typography;
const ROLES = ['owner', 'admin', 'editor', 'viewer'];
const PERMS = ['read', 'write', 'manage'];

/** Members, groups and knowledge-base access for this computer or a connected server. */
const AccessPanel: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.access.${key}`, o as any));
  const [connections, setConnections] = useState<KSConnection[]>([]);
  const [target, setTarget] = useState<string>('');
  const [view, setView] = useState<KSAccessView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [invite, setInvite] = useState({ email: '', role: 'viewer' });
  const [groupName, setGroupName] = useState('');
  const [grant, setGrant] = useState<{ kb_id?: string; principal_type: string; principal_id?: string; permission: string }>({ principal_type: 'user', permission: 'read' });
  const [audit, setAudit] = useState<any[]>([]);

  useEffect(() => { ksApi.listConnections().then(setConnections).catch(() => setConnections([])); }, []);

  const op = useCallback(async <T,>(name: string, params: Record<string, any> = {}) => ksApi.access<T>(name, params, target || undefined), [target]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setView(await op<KSAccessView>('view'));
      setAudit(await op<any[]>('audit', { limit: 50 }));
      setError(null);
    } catch (e: any) {
      setView(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [op]);
  useEffect(() => { load(); }, [load]);

  const run = async (name: string, params: Record<string, any>, ok?: string) => {
    try {
      await op(name, params);
      if (ok) message.success(ok);
      await load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const memberName = useMemo(() => {
    const m: Record<string, string> = {};
    (view?.members || []).forEach(x => { m[x.id] = x.display_name || x.email; m[x.email] = x.display_name || x.email; m[x.user_id] = x.display_name || x.email; });
    return m;
  }, [view]);
  const groupName_ = (id: string) => view?.groups.find(g => g.id === id)?.name || id;
  const storeName = (id: string) => view?.stores.find(s => s.id === id)?.name || id;
  const principalLabel = (type: string, id: string) =>
    type === 'group' ? `${k('group')}: ${groupName_(id)}` : type === 'store' ? `${k('store')}: ${storeName(id)}`
      : type === 'agent' ? `${k('agent')}: ${id}` : (memberName[id] || id);

  const memberColumns = [
    {
      title: k('member'), key: 'm', render: (_: any, m: KSMember) => (
        <Space direction="vertical" size={0}>
          <Text>{m.display_name || m.email}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{m.email}{view?.me && (m.user_id === view.me.user_id || m.email === view.me.email) ? ` · ${k('you')}` : ''}</Text>
        </Space>
      ),
    },
    {
      title: k('role'), key: 'r', width: 150, render: (_: any, m: KSMember) => (
        <Select size="small" value={m.role} style={{ width: 130 }} options={ROLES.map(r => ({ value: r, label: k(`roles.${r}`) }))}
                onChange={role => run('saveMember', { member_id: m.id, email: m.email, role })} />
      ),
    },
    {
      title: k('status'), key: 's', width: 130, render: (_: any, m: KSMember) => (
        <Tooltip title={k(`statusHint.${m.status}`)}>
          <Tag color={m.status === 'active' ? 'green' : m.status === 'invited' ? 'gold' : 'default'}>{k(`statuses.${m.status}`)}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '', key: 'a', width: 140, render: (_: any, m: KSMember) => (
        <Space>
          <Button size="small" type="link" onClick={() => run('saveMember', { member_id: m.id, email: m.email, role: m.role, status: m.status === 'disabled' ? 'active' : 'disabled' })}>
            {m.status === 'disabled' ? k('enable') : k('disable')}
          </Button>
          <Popconfirm title={k('removeConfirm', { name: m.email })} okButtonProps={{ danger: true }} onConfirm={() => run('removeMember', { member_id: m.id })}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const principalOptions = (type: string) => {
    if (type === 'group') return (view?.groups || []).map(g => ({ value: g.id, label: g.name }));
    if (type === 'store') return (view?.stores || []).map(s => ({ value: s.id, label: s.name }));
    if (type === 'user') return (view?.members || []).map(m => ({ value: m.email, label: m.display_name || m.email }));
    return [];
  };

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Text>{k('manageOn')}</Text>
        <Select style={{ width: 280 }} value={target} onChange={setTarget}
                options={[{ value: '', label: k('thisComputer') }, ...connections.map(c => ({ value: c.id, label: `${c.name} (${String(t(`pages.knowledge.ks.plane.${c.plane}`))})` }))]} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading} />
      </Space>
      {!target && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={k('localNote')} />}
      {error && <Alert type="error" showIcon style={{ marginBottom: 12 }} message={k('loadFailed')} description={error} />}
      {view && (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={14}>
            <Card size="small" title={<Space><TeamOutlined />{k('members')} <Text type="secondary">· {view.tenant.name}</Text></Space>}>
              <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
                <Input placeholder={k('inviteEmail')} value={invite.email} onChange={e => setInvite({ ...invite, email: e.target.value })} />
                <Select value={invite.role} style={{ width: 130 }} options={ROLES.filter(r => r !== 'owner').map(r => ({ value: r, label: k(`roles.${r}`) }))}
                        onChange={role => setInvite({ ...invite, role })} />
                <Button type="primary" icon={<UserAddOutlined />} disabled={!invite.email.includes('@')}
                        onClick={async () => { await run('saveMember', invite, k('invited')); setInvite({ email: '', role: 'viewer' }); }}>{k('invite')}</Button>
              </Space.Compact>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>{k('inviteHint')}</Text>
              <Table rowKey="id" size="small" pagination={false} columns={memberColumns as any} dataSource={view.members} />
            </Card>
            <Card size="small" style={{ marginTop: 16 }} title={k('groups')}>
              <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
                <Input placeholder={k('groupName')} value={groupName} onChange={e => setGroupName(e.target.value)} />
                <Button icon={<PlusOutlined />} disabled={!groupName.trim()} onClick={async () => { await run('saveGroup', { name: groupName, member_ids: [] }); setGroupName(''); }}>{k('addGroup')}</Button>
              </Space.Compact>
              {view.groups.length === 0 ? <Text type="secondary">{k('noGroups')}</Text> : view.groups.map(g => (
                <Row key={g.id} gutter={8} align="middle" style={{ marginBottom: 8 }}>
                  <Col span={6}><Text strong>{g.name}</Text></Col>
                  <Col span={16}>
                    <Select mode="multiple" size="small" style={{ width: '100%' }} value={g.member_ids} placeholder={k('groupMembers')}
                            options={view.members.map(m => ({ value: m.id, label: m.display_name || m.email }))}
                            onChange={ids => run('saveGroup', { group_id: g.id, name: g.name, member_ids: ids })} />
                  </Col>
                  <Col span={2}>
                    <Popconfirm title={k('deleteGroupConfirm')} onConfirm={() => run('deleteGroup', { group_id: g.id })}>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Col>
                </Row>
              ))}
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card size="small" title={<Space><SafetyOutlined />{k('kbAccess')}</Space>}>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>{k('rulesHint')}</Text>
              {view.kbs.map(kb => (
                <div key={kb.id} style={{ marginBottom: 12, padding: 8, borderRadius: 6, background: 'rgba(0,0,0,0.02)' }}>
                  <Space wrap style={{ marginBottom: 6 }}>
                    <Text strong>{kb.name}</Text>
                    <PlaneTag plane={kb.plane} />
                    <Select size="small" value={kb.sensitivity} style={{ width: 150 }}
                            options={['public', 'internal', 'confidential'].map(s => ({ value: s, label: k(`sensitivity.${s}`) }))}
                            onChange={sensitivity => run('updateKb', { kb_id: kb.id, sensitivity })} />
                  </Space>
                  {kb.sensitivity === 'confidential' && <Alert type="warning" showIcon style={{ marginBottom: 6, fontSize: 12 }} message={k('confidentialHint')} />}
                  {view.grants.filter(g => g.kb_id === kb.id).map(g => (
                    <div key={g.id} style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text style={{ fontSize: 12 }}>{principalLabel(g.principal_type, g.principal_id)} · <Tag>{k(`perms.${g.permission}`)}</Tag></Text>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => run('removeGrant', { grant_id: g.id })} />
                    </div>
                  ))}
                </div>
              ))}
              <Space.Compact style={{ width: '100%' }}>
                <Select size="small" placeholder={k('pickKb')} style={{ width: '28%' }} value={grant.kb_id}
                        options={view.kbs.map(kb => ({ value: kb.id, label: kb.name }))} onChange={kb_id => setGrant({ ...grant, kb_id })} />
                <Select size="small" style={{ width: '22%' }} value={grant.principal_type}
                        options={['user', 'group', 'store'].map(x => ({ value: x, label: k(x) }))}
                        onChange={principal_type => setGrant({ ...grant, principal_type, principal_id: undefined })} />
                <Select size="small" showSearch style={{ width: '30%' }} value={grant.principal_id} placeholder={k('pickWho')}
                        options={principalOptions(grant.principal_type)} onChange={principal_id => setGrant({ ...grant, principal_id })} />
                <Select size="small" style={{ width: '20%' }} value={grant.permission}
                        options={PERMS.map(p => ({ value: p, label: k(`perms.${p}`) }))} onChange={permission => setGrant({ ...grant, permission })} />
              </Space.Compact>
              <Button size="small" type="primary" style={{ marginTop: 8 }} disabled={!grant.kb_id || !grant.principal_id}
                      onClick={() => run('setGrant', grant, k('granted'))}>{k('grant')}</Button>
            </Card>
            <Card size="small" style={{ marginTop: 16 }} title={k('audit')}>
              {audit.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
                <List size="small" dataSource={audit.slice(0, 30)} renderItem={(a: any) => (
                  <List.Item>
                    <Text style={{ fontSize: 12 }}>
                      <Text type="secondary">{a.ts ? new Date(a.ts).toLocaleString() : ''}</Text> · {a.actor} · <Tag>{a.action}</Tag>{a.target}
                    </Text>
                  </List.Item>
                )} />
              )}
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
};

export default AccessPanel;
