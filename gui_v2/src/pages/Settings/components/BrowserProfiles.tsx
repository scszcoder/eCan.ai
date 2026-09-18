/**
 * Browser Profiles — one logged-in identity on one site.
 *
 * Not to be confused with the "profiles" on the Browser Use tab, which are
 * browser-use agent presets. A profile here is an identity: the session that
 * keeps a store logged in, the proxy that store has seen it come from, the
 * fingerprint it presents, and the Chromium build that wrote the session.
 *
 * The page is a thin view over the `browser_profile.*` DTO and never touches
 * the registry's own shape — see `@/types/browserProfile`. Everything that
 * could plausibly change is served rather than hard-coded: which vendors can
 * be imported from, which fingerprint presets exist, and which binary a blank
 * browser path resolves to. Adding a second vendor should be a backend change
 * that this file does not notice.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App,
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CloudDownloadOutlined,
  DeleteOutlined,
  EditOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { get_ipc_api } from '@/services/ipc_api';
import type {
  BrowserProfile,
  BrowserProfileOptions,
  BrowserVendor,
} from '@/types/browserProfile';

const { Text, Paragraph } = Typography;

/** While anything is open, re-read status on this cadence. */
const STATUS_POLL_MS = 5000;

interface EditorState {
  open: boolean;
  /** null = creating. Editing keeps the id fixed: it names the session folder. */
  original: BrowserProfile | null;
}

const BrowserProfiles: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const tp = useCallback(
    (key: string, fallback?: string) =>
      t(`pages.settings.browser_profiles.${key}`, fallback ?? key) as string,
    [t],
  );

  // IPC errors arrive either as a bare string or as {code, message}; the
  // message is the part worth showing.
  const errText = (err: unknown, fallback: string): string =>
    (typeof err === 'string' ? err : (err as { message?: string })?.message) || fallback;

  const [profiles, setProfiles] = useState<BrowserProfile[]>([]);
  const [options, setOptions] = useState<BrowserProfileOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string>('');

  const [editor, setEditor] = useState<EditorState>({ open: false, original: null });
  const [importOpen, setImportOpen] = useState(false);
  const [form] = Form.useForm();
  const [importForm] = Form.useForm();

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // -- data ----------------------------------------------------------------

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const res = await get_ipc_api().listBrowserProfiles<{ profiles: BrowserProfile[] }>();
      if (res.success && res.data) {
        setProfiles(res.data.profiles || []);
      } else if (!quiet) {
        message.error(errText(res.error, tp('load_failed', 'Failed to load browser profiles')));
      }
    } catch (err) {
      if (!quiet) message.error(tp('load_failed', 'Failed to load browser profiles'));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [message, tp]);

  const loadOptions = useCallback(async () => {
    try {
      const res = await get_ipc_api().getBrowserProfileOptions<BrowserProfileOptions>();
      if (res.success && res.data) setOptions(res.data);
    } catch {
      /* the editor degrades to free text without presets */
    }
  }, []);

  useEffect(() => {
    load();
    loadOptions();
  }, [load, loadOptions]);

  // A browser can be opened or closed by a skill run, the CLI, or the user
  // closing the window — none of which come back through this page. Poll only
  // while something is actually open.
  const anyRunning = useMemo(() => profiles.some((p) => p.status?.running), [profiles]);
  useEffect(() => {
    if (!anyRunning) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = setInterval(() => load(true), STATUS_POLL_MS);
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [anyRunning, load]);

  // -- actions -------------------------------------------------------------

  const openEditor = (profile: BrowserProfile | null) => {
    form.resetFields();
    if (profile) {
      form.setFieldsValue({
        id: profile.id,
        label: profile.label,
        domain: profile.domain,
        locale: profile.locale,
        fingerprint_profile: profile.fingerprint_profile || undefined,
        browser_path: profile.browser?.path || '',
        proxy_scheme: profile.proxy?.scheme || 'socks5',
        proxy_host: profile.proxy?.host || '',
        proxy_port: profile.proxy?.port || undefined,
        proxy_username: profile.proxy?.username || '',
        proxy_password: '',
        proxy_bypass: (profile.proxy?.bypass || []).join(', '),
      });
    } else {
      form.setFieldsValue({ locale: 'en-US', proxy_scheme: 'socks5' });
    }
    setEditor({ open: true, original: profile });
  };

  const submitEditor = async () => {
    let values: any;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const original = editor.original;
    const dto: BrowserProfile = {
      ...(original || ({} as BrowserProfile)),
      id: (values.id || '').trim(),
      label: (values.label || '').trim(),
      domain: (values.domain || '').trim(),
      locale: (values.locale || 'en-US').trim(),
      fingerprint_profile: values.fingerprint_profile || '',
      browser: {
        path: (values.browser_path || '').trim(),
        version: original?.browser?.version || '',
      },
      proxy: {
        scheme: values.proxy_scheme || 'socks5',
        host: (values.proxy_host || '').trim(),
        port: Number(values.proxy_port || 0),
        username: (values.proxy_username || '').trim(),
        has_password: !!original?.proxy?.has_password,
        bypass: String(values.proxy_bypass || '')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      },
    } as BrowserProfile;

    setLoading(true);
    try {
      const res = await get_ipc_api().saveBrowserProfile(
        dto, values.proxy_password || '', original ? undefined : true,
      );
      if (res.success) {
        message.success(tp('saved', 'Profile saved'));
        setEditor({ open: false, original: null });
        load();
      } else {
        message.error(errText(res.error, tp('save_failed', 'Failed to save the profile')));
      }
    } finally {
      setLoading(false);
    }
  };

  const launch = async (profile: BrowserProfile) => {
    setBusyId(profile.id);
    try {
      const startUrl = profile.domain ? `https://${profile.domain}` : '';
      const res = await get_ipc_api().launchBrowserProfile<{ port: number }>(
        profile.id, startUrl,
      );
      if (res.success) {
        message.success(tp('launched', 'Browser opened'));
      } else {
        message.error(errText(res.error, tp('launch_failed', 'Could not open the browser')));
      }
    } finally {
      setBusyId('');
      load();
    }
  };

  const stop = async (profile: BrowserProfile) => {
    setBusyId(profile.id);
    try {
      const res = await get_ipc_api().stopBrowserProfile(profile.id);
      if (res.success) message.success(tp('stop_ok', 'Browser closed'));
      else message.error(errText(res.error, tp('stop_failed', 'Could not close the browser')));
    } finally {
      setBusyId('');
      load();
    }
  };

  const remove = async (profile: BrowserProfile, deleteSession: boolean) => {
    setBusyId(profile.id);
    try {
      const res = await get_ipc_api().deleteBrowserProfile(profile.id, deleteSession);
      if (res.success) {
        message.success(tp('removed', 'Profile removed'));
        load();
      } else {
        message.error(errText(res.error, tp('remove_failed', 'Could not remove the profile')));
      }
    } finally {
      setBusyId('');
    }
  };

  const submitImport = async () => {
    let values: any;
    try {
      values = await importForm.validateFields();
    } catch {
      return;
    }
    setLoading(true);
    try {
      const res = await get_ipc_api().importBrowserProfile({
        vendor: values.vendor,
        vendor_profile_id: (values.vendor_profile_id || '').trim(),
        id: (values.id || '').trim(),
        label: (values.label || '').trim(),
        fingerprint_profile: values.fingerprint_profile || '',
        api_key: (values.api_key || '').trim(),
        api_port: Number(values.api_port || 0) || undefined,
        api_url: (values.api_url || '').trim(),
        overwrite: !!values.overwrite,
      });
      if (res.success) {
        message.success(tp('imported', 'Profile imported'));
        setImportOpen(false);
        importForm.resetFields();
        load();
      } else {
        message.error(errText(res.error, tp('import_failed', 'Import failed')));
      }
    } finally {
      setLoading(false);
    }
  };

  // -- render --------------------------------------------------------------

  const fingerprintOptions = useMemo(
    () => (options?.fingerprints || []).map((f) => ({
      value: f.id,
      label: f.name && f.name !== f.id ? `${f.name} (${f.id})` : f.id,
    })),
    [options],
  );

  const vendors: BrowserVendor[] = options?.vendors || [];

  const statusCell = (profile: BrowserProfile) => {
    const st = profile.status;
    if (!st?.running) return <Badge status="default" text={tp('stopped', 'Stopped')} />;
    if (st.relay_port && !st.relay_alive) {
      // The browser is up but its proxy relay died with whoever launched it,
      // so it is now reaching the site from this machine's own address.
      return (
        <Tooltip title={tp('no_proxy_hint',
          'The proxy relay died with the process that launched this browser. '
          + 'It is now reaching the site from this machine\'s own IP — close it.')}>
          <Badge status="error" text={tp('no_proxy', 'Open — NO PROXY')} />
        </Tooltip>
      );
    }
    return (
      <Tooltip title={st.cdp_url}>
        <Badge status="processing" text={`${tp('running', 'Open')} :${st.port}`} />
      </Tooltip>
    );
  };

  const columns = [
    {
      title: tp('col_profile', 'Profile'),
      key: 'profile',
      render: (_: unknown, p: BrowserProfile) => (
        <Space direction="vertical" size={0}>
          <Text strong>{p.label || p.id}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {p.id}{p.domain ? ` · ${p.domain}` : ''}
          </Text>
        </Space>
      ),
    },
    {
      title: tp('col_proxy', 'Proxy'),
      key: 'proxy',
      render: (_: unknown, p: BrowserProfile) =>
        p.proxy?.host ? (
          <Space direction="vertical" size={0}>
            <Text style={{ fontSize: 12 }}>
              {p.proxy.scheme}://{p.proxy.host}:{p.proxy.port}
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {p.proxy.username || tp('no_auth', 'no auth')}
              {p.proxy.has_password ? ` · ${tp('password_stored', 'password in keyring')}` : ''}
            </Text>
          </Space>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {tp('direct', 'Direct')}
          </Text>
        ),
    },
    {
      title: tp('col_fingerprint', 'Fingerprint'),
      key: 'fingerprint',
      render: (_: unknown, p: BrowserProfile) =>
        p.fingerprint_profile
          ? <Tag>{p.fingerprint_profile}</Tag>
          : <Text type="secondary" style={{ fontSize: 12 }}>{tp('none', 'None')}</Text>,
    },
    {
      title: tp('col_source', 'Source'),
      key: 'source',
      render: (_: unknown, p: BrowserProfile) =>
        p.imported_from?.vendor
          ? <Tag color="blue">{p.imported_from.vendor}</Tag>
          : <Text type="secondary" style={{ fontSize: 12 }}>{tp('local', 'Created here')}</Text>,
    },
    {
      title: tp('col_status', 'Status'),
      key: 'status',
      render: (_: unknown, p: BrowserProfile) => statusCell(p),
    },
    {
      title: '',
      key: 'actions',
      align: 'right' as const,
      render: (_: unknown, p: BrowserProfile) => (
        <Space>
          {p.status?.running ? (
            <Tooltip title={tp('stop_hint', 'Close it — this is what writes the session out')}>
              <Button size="small" icon={<PoweroffOutlined />} loading={busyId === p.id}
                      onClick={() => stop(p)} />
            </Tooltip>
          ) : (
            <Tooltip title={tp('launch_hint', 'Open this profile to sign in or check it')}>
              <Button size="small" icon={<PlayCircleOutlined />} loading={busyId === p.id}
                      onClick={() => launch(p)} />
            </Tooltip>
          )}
          <Tooltip title={tp('edit', 'Edit')}>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(p)} />
          </Tooltip>
          <Popconfirm
            title={tp('remove_title', 'Remove this profile?')}
            description={tp('remove_desc',
              'The session folder is kept, so the login survives and the profile '
              + 'can be registered again.')}
            okText={tp('remove_ok', 'Remove')}
            cancelText={tp('cancel', 'Cancel')}
            onConfirm={() => remove(p, false)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} loading={busyId === p.id} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const editing = editor.original;

  return (
    <div>
      <Card
        title={tp('title', 'Browser Profiles')}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>
              {tp('refresh', 'Refresh')}
            </Button>
            <Button icon={<CloudDownloadOutlined />} onClick={() => {
              importForm.resetFields();
              importForm.setFieldsValue({
                vendor: vendors[0]?.id || 'adspower',
                api_port: vendors[0]?.default_api_port || 50325,
              });
              setImportOpen(true);
            }}>
              {tp('import', 'Import from an anti-detect browser')}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor(null)}>
              {tp('new', 'New profile')}
            </Button>
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          {tp('intro',
            'A profile is one logged-in identity on one site. It carries its own '
            + 'session, proxy and fingerprint, so a skill only has to name it — '
            + 'set a browser-automation node to the eCan Fingerprint Browser and '
            + 'pick the profile.')}
        </Paragraph>

        {/* Says out loud what the code already guarantees. A profile is a live
            logged-in session plus proxy credentials; it is the most sensitive
            thing this app holds, so it stays on this machine by default and
            leaving requires the user to say so per profile. */}
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={tp('local_only', 'Profiles stay on this machine')}
          description={tp('local_only_hint',
            'Sessions, proxy credentials and fingerprints are not synced to the '
            + 'cloud and do not travel with a shared skill. Passwords live in the '
            + 'OS keyring. Running a profile headlessly in the cloud has to be '
            + 'authorised by you, per profile.')}
        />

        {profiles.length === 0 && !loading ? (
          <Empty description={tp('empty',
            'No profiles yet. Create one and sign in, or import a profile you '
            + 'already use in AdsPower.')} />
        ) : (
          <Table
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={profiles}
            columns={columns}
            pagination={false}
            expandable={{
              expandedRowRender: (p: BrowserProfile) => (
                <Space direction="vertical" size={2} style={{ fontSize: 12 }}>
                  <Text type="secondary">
                    <FolderOpenOutlined /> {tp('session_dir', 'Session')}: {p.user_data_dir}
                  </Text>
                  <Text type="secondary">
                    {tp('browser_binary', 'Browser')}:{' '}
                    {p.browser?.path
                      || `${options?.default_browser_path || ''} (${tp('resolved', 'resolved')})`}
                  </Text>
                  {p.status?.running && (
                    <Text type="secondary">CDP: {p.status.cdp_url} (pid {p.status.pid})</Text>
                  )}
                </Space>
              ),
            }}
          />
        )}
      </Card>

      {/* ---- create / edit ---- */}
      <Modal
        title={editing
          ? tp('edit_title', 'Edit browser profile')
          : tp('new_title', 'New browser profile')}
        open={editor.open}
        onCancel={() => setEditor({ open: false, original: null })}
        onOk={submitEditor}
        confirmLoading={loading}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" size="small">
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item
                name="id"
                label={tp('f_id', 'Id')}
                tooltip={tp('f_id_hint',
                  'Names the session folder, so it cannot change later. '
                  + 'Letters, digits, - and _.')}
                rules={[
                  { required: true, message: tp('f_id_required', 'An id is required') },
                  {
                    pattern: /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/,
                    message: tp('f_id_invalid', "Letters, digits, '-' and '_' only"),
                  },
                ]}
              >
                <Input placeholder="etsy_main" disabled={!!editing} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="label" label={tp('f_label', 'Name')}>
                <Input placeholder={tp('f_label_ph', 'Etsy store')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item
                name="domain"
                label={tp('f_domain', 'Site')}
                tooltip={tp('f_domain_hint', 'Where Open takes this profile.')}
              >
                <Input placeholder="etsy.com" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="locale" label={tp('f_locale', 'Locale')}>
                <Input placeholder="en-US" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="fingerprint_profile"
                label={tp('f_fingerprint', 'Fingerprint')}
                tooltip={tp('f_fingerprint_hint',
                  'Which stealth preset to present. Leave empty to present the '
                  + 'browser as it is.')}
              >
                <Select allowClear options={fingerprintOptions}
                        placeholder={tp('none', 'None')} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="browser_path"
            label={tp('f_browser', 'Chromium binary')}
            tooltip={tp('f_browser_hint',
              'A profile written by a newer Chromium can stop an older one from '
              + 'starting, so the binary is recorded with the profile. Leave it '
              + 'empty to use the bundled one.')}
          >
            <Input placeholder={options?.default_browser_path
              || tp('f_browser_ph', 'The bundled Chromium')} />
          </Form.Item>

          <Card size="small" title={tp('proxy_title', 'Proxy')} style={{ marginBottom: 8 }}>
            <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 0 }}>
              {tp('proxy_hint',
                'The egress this identity is seen to use. An authenticated SOCKS5 '
                + 'proxy is fronted by a local relay, because Chromium cannot '
                + 'authenticate to one itself. Leave the host empty to go direct.')}
            </Paragraph>
            <Row gutter={12}>
              <Col span={6}>
                <Form.Item name="proxy_scheme" label={tp('f_scheme', 'Type')}>
                  <Select options={[
                    { value: 'socks5', label: 'socks5' },
                    { value: 'http', label: 'http' },
                    { value: 'https', label: 'https' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="proxy_host" label={tp('f_host', 'Host')}>
                  <Input placeholder="us11.example.net" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="proxy_port" label={tp('f_port', 'Port')}>
                  <InputNumber min={0} max={65535} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="proxy_username" label={tp('f_user', 'Username')}>
                  <Input autoComplete="off" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="proxy_password"
                  label={tp('f_password', 'Password')}
                  tooltip={tp('f_password_hint',
                    'Stored in the OS keyring, never in the profile file.')}
                >
                  <Input.Password
                    autoComplete="new-password"
                    placeholder={editing?.proxy?.has_password
                      ? tp('f_password_kept', 'Stored — leave blank to keep it')
                      : ''}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name="proxy_bypass"
              label={tp('f_bypass', 'Bypass')}
              tooltip={tp('f_bypass_hint', 'Comma-separated hosts that skip the proxy.')}
            >
              <Input placeholder="localhost, 127.0.0.1" />
            </Form.Item>
          </Card>

          {editing && (
            <Alert
              type="info"
              showIcon
              message={tp('session_fixed', 'The session folder stays where it is')}
              description={editing.user_data_dir}
            />
          )}
        </Form>
      </Modal>

      {/* ---- import ---- */}
      <Modal
        title={tp('import_title', 'Import a logged-in profile')}
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={submitImport}
        confirmLoading={loading}
        okText={tp('import_ok', 'Import')}
        width={560}
        destroyOnHidden
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={tp('import_warn_title', 'The vendor profile will be closed')}
          description={tp('import_warn',
            'Its folder is only visible while it runs, so it is started briefly '
            + 'and then stopped. Caches are skipped, so a large profile copies in '
            + 'seconds. The vendor\'s own browser and fingerprint are not copied — '
            + 'they only work in their patched browser — so pick one of ours.')}
        />
        <Form form={importForm} layout="vertical" size="small">
          <Row gutter={12}>
            <Col span={10}>
              <Form.Item name="vendor" label={tp('f_vendor', 'From')}
                         rules={[{ required: true }]}>
                <Select options={vendors.map((v) => ({ value: v.id, label: v.name }))} />
              </Form.Item>
            </Col>
            <Col span={14}>
              <Form.Item
                noStyle
                shouldUpdate={(a, b) => a.vendor !== b.vendor}
              >
                {({ getFieldValue }) => {
                  const v = vendors.find((x) => x.id === getFieldValue('vendor'));
                  return (
                    <Form.Item
                      name="vendor_profile_id"
                      label={v?.id_label || tp('f_vendor_id', 'Profile id')}
                      rules={[{ required: true,
                                message: tp('f_vendor_id_required', 'Required') }]}
                    >
                      <Input placeholder="kq15tpi" />
                    </Form.Item>
                  );
                }}
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item
                name="id"
                label={tp('f_new_id', 'Register as')}
                rules={[
                  { required: true, message: tp('f_id_required', 'An id is required') },
                  {
                    pattern: /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/,
                    message: tp('f_id_invalid', "Letters, digits, '-' and '_' only"),
                  },
                ]}
              >
                <Input placeholder="etsy_main" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="fingerprint_profile" label={tp('f_fingerprint', 'Fingerprint')}>
                <Select allowClear options={fingerprintOptions}
                        placeholder={tp('none', 'None')} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item noStyle shouldUpdate={(a, b) => a.vendor !== b.vendor}>
            {({ getFieldValue }) => {
              const v = vendors.find((x) => x.id === getFieldValue('vendor'));
              return (
                <>
                  {v && v.validated === false && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message={tp('import_unvalidated',
                        'This importer has not been tested against a live install')}
                      description={tp('import_unvalidated_hint',
                        'It may fail or bring the profile across without its proxy. '
                        + 'Check the profile before using it as an identity, and '
                        + 'report what happened.')}
                    />
                  )}
                  <Row gutter={12}>
                    <Col span={12}>
                      {v?.needs_account ? (
                        // Account-based vendors (Ziniao) authenticate with
                        // company/user/password, which already live in
                        // Settings -> Browser Automation -> Providers. Asking
                        // again here would be a second place to get it wrong.
                        <Form.Item label={tp('f_credentials', 'Credentials')}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {tp('f_credentials_from_settings',
                              'Taken from Settings → Browser Use → Providers')}
                          </Text>
                        </Form.Item>
                      ) : (
                        <Form.Item name="api_key" label={tp('f_api_key', 'Vendor API key')}
                                   tooltip={tp('f_api_key_hint', 'Only if their local API asks for one.')}>
                          <Input autoComplete="off" />
                        </Form.Item>
                      )}
                    </Col>
                    <Col span={12}>
                      <Form.Item name="api_port" label={tp('f_api_port', 'Vendor API port')}>
                        <InputNumber min={0} max={65535} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                </>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default BrowserProfiles;
