import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Empty, Form, Input, List, Modal, Popconfirm, Radio, Row, Space, Steps, Switch, Tag, Tooltip, Typography,
} from 'antd';
import {
  ApiOutlined, CheckCircleOutlined, CloudOutlined, DeleteOutlined, EditOutlined, LaptopOutlined, LockOutlined, LoginOutlined, PlusOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSConnection, KSConnectionTest } from '@/services/ipc/ksApi';
import LanPanel from './LanPanel';

const { Text, Paragraph } = Typography;

const PlaneTag: React.FC<{ plane: string }> = ({ plane }) => {
  const { t } = useTranslation();
  const icon = plane === 'private' ? <LockOutlined /> : plane === 'public' ? <CloudOutlined /> : <LaptopOutlined />;
  const color = plane === 'private' ? 'red' : plane === 'public' ? 'blue' : 'green';
  return <Tag color={color} icon={icon}>{String(t(`pages.knowledge.ks.plane.${plane}`))}</Tag>;
};
export { PlaneTag };

/**
 * Connections to Knowledge Service servers: a private server on the
 * company's own hardware, and/or the eCan cloud. Questions are routed to this
 * computer plus every enabled connection.
 */
const ConnectionsPanel: React.FC<{ onChanged?: () => void }> = ({ onChanged }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.connections.${key}`, o as any));
  const [items, setItems] = useState<KSConnection[]>([]);
  const [editing, setEditing] = useState<Partial<KSConnection> | null>(null);
  const [tests, setTests] = useState<Record<string, KSConnectionTest | 'running'>>({});
  const [login, setLogin] = useState<KSConnection | null>(null);
  const [form] = Form.useForm();
  const [loginForm] = Form.useForm();

  const load = useCallback(async () => {
    try { setItems(await ksApi.listConnections()); } catch (e: any) { message.error(e.message); }
  }, [message]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    const v = await form.validateFields();
    try {
      await ksApi.saveConnection({ ...editing, ...v });
      setEditing(null);
      await load();
      onChanged?.();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const runTest = async (c: KSConnection) => {
    setTests(x => ({ ...x, [c.id]: 'running' }));
    try {
      const res = await ksApi.testConnection(c.id);
      setTests(x => ({ ...x, [c.id]: res }));
    } catch (e: any) {
      setTests(x => ({ ...x, [c.id]: { ok: false, steps: [{ step: 'reach', ok: false, detail: e.message }] } }));
    }
  };

  const doLogin = async () => {
    if (!login) return;
    const v = await loginForm.validateFields();
    try {
      await ksApi.loginConnection(login.id, v.email, v.password);
      message.success(k('signedIn'));
      setLogin(null);
      loginForm.resetFields();
      await load();
      runTest(login);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const toggle = async (c: KSConnection, field: 'enabled' | 'send_queries', value: boolean) => {
    await ksApi.saveConnection({ ...c, [field]: value });
    load();
  };

  return (
    <div>
      <LanPanel onChanged={onChanged} />
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message={k('intro')} description={k('introDetail')} />
      <Row gutter={16}>
        <Col xs={24} xl={16}>
          <Card size="small" title={<Space><ApiOutlined />{k('title')}</Space>}
                extra={<Button size="small" type="primary" icon={<PlusOutlined />}
                               onClick={() => { form.resetFields(); form.setFieldsValue({ plane: 'private', auth: 'local', verify_tls: true }); setEditing({}); }}>
                  {k('add')}
                </Button>}>
            <List
              locale={{ emptyText: <Empty description={k('empty')} /> }}
              dataSource={[{ id: '__local__' } as any, ...items]}
              renderItem={(c: KSConnection & { id: string }) => {
                if (c.id === '__local__') {
                  return (
                    <List.Item>
                      <List.Item.Meta avatar={<LaptopOutlined style={{ fontSize: 20 }} />}
                                      title={<Space>{k('thisComputer')}<PlaneTag plane="local" /></Space>}
                                      description={k('thisComputerHint')} />
                    </List.Item>
                  );
                }
                const test = tests[c.id];
                return (
                  <List.Item
                    actions={[
                      <Tooltip key="en" title={k('enabledHint')}><Switch size="small" checked={c.enabled} onChange={v => toggle(c, 'enabled', v)} /></Tooltip>,
                      ...(c.auth === 'local' ? [<Button key="login" size="small" icon={<LoginOutlined />} onClick={() => setLogin(c)}>{c.signed_in ? k('reSignIn') : k('signIn')}</Button>] : []),
                      <Button key="t" size="small" loading={test === 'running'} onClick={() => runTest(c)}>{k('test')}</Button>,
                      <Button key="e" size="small" type="text" icon={<EditOutlined />} onClick={() => { form.setFieldsValue(c); setEditing(c); }} />,
                      <Popconfirm key="d" title={k('deleteConfirm', { name: c.name })} onConfirm={async () => { await ksApi.deleteConnection(c.id); load(); onChanged?.(); }}>
                        <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={c.plane === 'private' ? <LockOutlined style={{ fontSize: 20, color: '#cf1322' }} /> : <CloudOutlined style={{ fontSize: 20, color: '#1677ff' }} />}
                      title={<Space wrap>{c.name}<PlaneTag plane={c.plane} />
                        {!c.enabled && <Tag>{k('disabled')}</Tag>}
                        {c.auth === 'local' && !c.signed_in && <Tag color="warning">{k('notSignedIn')}</Tag>}
                        {c.plane === 'public' && !c.send_queries && <Tag>{k('queriesNotSent')}</Tag>}
                      </Space>}
                      description={
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }}>{c.base_url} · {k('tenant')}: {c.tenant_id || '—'}</Text>
                          {test && test !== 'running' && (
                            <Steps size="small" direction="vertical" style={{ marginTop: 8 }}
                                   items={test.steps.map(s => ({
                                     title: k(`step.${s.step}`),
                                     status: s.ok ? 'finish' : 'error',
                                     description: <Text style={{ fontSize: 12 }}>{s.detail}{s.ms !== undefined ? ` · ${s.ms} ms` : ''}</Text>,
                                   }))} />
                          )}
                          {test && test !== 'running' && test.ok && <Text type="success" style={{ fontSize: 12 }}><CheckCircleOutlined /> {k('ready')}</Text>}
                        </div>
                      }
                    />
                  </List.Item>
                );
              }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card size="small" title={k('howTitle')}>
            <Paragraph style={{ fontSize: 12 }}><LockOutlined style={{ color: '#cf1322' }} /> {k('howPrivate')}</Paragraph>
            <Paragraph style={{ fontSize: 12 }}><CloudOutlined style={{ color: '#1677ff' }} /> {k('howPublic')}</Paragraph>
            <Paragraph style={{ fontSize: 12 }}>{k('howGuard')}</Paragraph>
          </Card>
        </Col>
      </Row>

      <Modal open={!!editing} title={editing?.id ? k('edit') : k('add')} onCancel={() => setEditing(null)} onOk={save} okText={k('save')} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={k('name')} rules={[{ required: true }]}><Input placeholder={k('namePlaceholder')} /></Form.Item>
          <Form.Item name="plane" label={k('kind')}>
            <Radio.Group optionType="button" options={[{ value: 'private', label: k('kindPrivate') }, { value: 'public', label: k('kindPublic') }]} />
          </Form.Item>
          <Form.Item name="base_url" label={k('address')} rules={[{ required: true }]} extra={k('addressHint')}>
            <Input placeholder="https://ks.mycompany.cn:8790" />
          </Form.Item>
          <Form.Item name="tenant_id" label={k('tenant')} extra={k('tenantHint')}><Input placeholder="tn_..." /></Form.Item>
          <Form.Item name="auth" label={k('auth')}>
            <Radio.Group options={[{ value: 'app', label: k('authApp') }, { value: 'local', label: k('authLocal') }]} />
          </Form.Item>
          <Form.Item name="verify_tls" label={k('verifyTls')} valuePropName="checked" extra={k('verifyTlsHint')}><Switch /></Form.Item>
          <Form.Item noStyle shouldUpdate>
            {() => form.getFieldValue('plane') === 'public' && (
              <Form.Item name="send_queries" label={k('sendQueries')} valuePropName="checked" initialValue extra={k('sendQueriesHint')}><Switch /></Form.Item>
            )}
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={!!login} title={k('signInTo', { name: login?.name })} onCancel={() => setLogin(null)} onOk={doLogin} okText={k('signIn')} destroyOnHidden>
        <Form form={loginForm} layout="vertical">
          <Form.Item name="email" label={k('email')} rules={[{ required: true }]}><Input autoComplete="username" /></Form.Item>
          <Form.Item name="password" label={k('password')} rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>{k('passwordHint')}</Text>
        </Form>
      </Modal>
    </div>
  );
};

export default ConnectionsPanel;
