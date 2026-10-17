/**
 * Create or edit a store's definition: name, id, platform, URLs, login profile.
 * Creating also says where it should run: this machine, or unassigned (the
 * first machine to run it claims it).
 */
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Form, Input, Modal, Radio, Select } from 'antd';
import styled from '@emotion/styled';
import { get_ipc_api } from '@/services/ipc_api';
import { PLATFORMS, platformValue } from '@/components/FastDeploy/scenarios';

export interface StoreDefinition {
  store_id: string;
  name: string;
  platform: string;
  store_urls: string[];
  browser_profile_id?: string | null;
}

interface Props {
  open: boolean;
  /** null = create a new store. */
  editing: StoreDefinition | null;
  onClose: () => void;
  onSaved: (storeId: string) => void;
}

/** Vertical form with tightened rhythm: antd's default 24px item gap plus a
 *  full label row leaves a lot of dead space in a short dialog. */
const CompactForm = styled.div`
  .ant-form-item {
    margin-bottom: 10px;
  }
  .ant-form-item:last-child {
    margin-bottom: 0;
  }
  .ant-form-item-label {
    padding-bottom: 2px;
  }
  .ant-form-item-label > label {
    height: auto;
    font-size: 13px;
  }
  .ant-form-item-explain,
  .ant-form-item-extra {
    margin-top: 2px;
    font-size: 12px;
    line-height: 1.5;
  }
  /* Undo global.css's 40px-tall "Select 样式" inside this dialog: it fights
   * size="small" (misaligned text) and, in tags mode, its 38px line-height on
   * .ant-select-selection-item makes each tag taller than the control, so the
   * selected platform text gets clipped away. */
  .ant-select-selector {
    min-height: auto !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
  }
  .ant-select-selection-search-input,
  .ant-select-selection-item,
  .ant-select-selection-placeholder {
    line-height: inherit !important;
    height: auto !important;
  }
`;

const StoreFormModal: React.FC<Props> = ({ open, editing, onClose, onSaved }) => {
  const { t, i18n } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [profiles, setProfiles] = useState<{ id: string; label: string }[]>([]);
  // Platforms typed in before (custom ones) show up in the list next time.
  const [customPlatforms, setCustomPlatforms] = useState<string[]>([]);
  const [idTouched, setIdTouched] = useState(false);
  const ts = (k: string, d: string) => t(`pages.stores.${k}`, d) as string;
  const zh = (i18n.language || '').toLowerCase().startsWith('zh');

  useEffect(() => {
    if (!open) return;
    setIdTouched(!!editing);
    form.setFieldsValue(editing ? {
      name: editing.name, store_id: editing.store_id, platform: editing.platform || undefined,
      urls: (editing.store_urls || []).join('\n'), browser_profile_id: editing.browser_profile_id || undefined,
    } : { name: '', store_id: '', platform: undefined, urls: '', browser_profile_id: undefined, assign: 'here' });
    get_ipc_api().listBrowserProfiles<{ profiles: { id: string; label: string }[] }>().then((res) => {
      if (res.success && res.data) setProfiles(res.data.profiles || []);
    }).catch(() => setProfiles([]));
    get_ipc_api().getStoreCatalog<{ stores: { platform: string }[] }>(true).then((res) => {
      const known = new Set(PLATFORMS.map((p) => p.value));
      const used = (res.success && res.data ? res.data.stores : []).map((x) => x.platform).filter(Boolean);
      setCustomPlatforms(Array.from(new Set(used.filter((v) => !known.has(v)))));
    }).catch(() => setCustomPlatforms([]));
  }, [open, editing, form]);

  const submit = async () => {
    const v = await form.validateFields();
    const store_urls = String(v.urls || '').split('\n').map((u: string) => u.trim()).filter(Boolean);
    setSaving(true);
    try {
      const api = get_ipc_api();
      const res: any = editing
        ? await api.updateStore({ store_id: editing.store_id, name: v.name.trim(), platform: v.platform || '',
            store_urls, browser_profile_id: v.browser_profile_id || '' })
        : await api.createStore({ store_id: v.store_id.trim(), name: v.name.trim(), platform: v.platform || '',
            store_urls, browser_profile_id: v.browser_profile_id || undefined, assign: v.assign });
      if (!res.success) {
        message.error((res.error && (res.error.message || res.error)) || ts('save_failed', 'Could not save the store'));
        return;
      }
      for (const w of res.data?.warnings || []) message.warning(w);
      message.success(ts('saved', 'Store saved'));
      onSaved(editing ? editing.store_id : v.store_id.trim());
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={editing ? ts('edit_store', 'Edit store') : ts('new_store', 'New store')}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={saving}
      okText={ts('save', 'Save')}
      width={440}
      destroyOnHidden
      styles={{ body: { padding: '12px 20px 4px' }, footer: { marginTop: 12 } }}
    >
      <CompactForm>
        <Form form={form} layout="vertical" size="small" colon={false}
          onValuesChange={(changed, all) => {
            // The id is <platform>-<name> until the user edits it, so same-named
            // shops on two platforms get distinct ids. Fixed once created.
            if (('name' in changed || 'platform' in changed) && !idTouched && !editing) {
              const name = String(all.name || '').trim();
              const platform = String(all.platform || '').trim();
              form.setFieldsValue({ store_id: name ? (platform ? `${platform}-${name}` : name) : '' });
            }
            if ('store_id' in changed) setIdTouched(true);
          }}
        >
          <Form.Item name="name" label={ts('name', 'Name')} required rules={[{ required: true, whitespace: true }]}>
            <Input placeholder={ts('name_ph', 'e.g. Shop One')} allowClear />
          </Form.Item>
          <Form.Item name="store_id" label={ts('store_id', 'Store ID')} required
            extra={ts('store_id_hint', 'Permanent. All 飞鸽 sellers share one workstation URL, so this ID (not the URL) is what tells stores apart.')}
            rules={[{ required: true, whitespace: true },
              { validator: (_, v) => (/^https?:\/\//i.test(String(v || '')) ? Promise.reject(ts('id_is_url', 'Use a name, not a URL')) : Promise.resolve()) }]}>
            <Input disabled={!!editing} allowClear />
          </Form.Item>
          {/* Pick one, or type a platform that is not listed and press Enter. The
              field holds a single string; tags mode is only how free text gets in. */}
          <Form.Item name="platform" label={ts('platform', 'Platform')} required
            extra={ts('platform_hint', 'Not listed? Type the platform name and press Enter to add it.')}
            getValueProps={(v) => ({ value: v ? [v] : [] })}
            normalize={(v) => platformValue(Array.isArray(v) ? String(v[v.length - 1] || '') : v)}>
            <Select mode="tags" showSearch optionFilterProp="label"
              options={[
                ...PLATFORMS.map((p) => ({ value: p.value, label: zh ? p.nameZh : p.nameEn })),
                ...customPlatforms.map((v) => ({ value: v, label: v })),
              ]} />
          </Form.Item>
          <Form.Item name="urls" label={ts('urls', 'Store URLs (one per line)')}>
            <Input.TextArea rows={2} placeholder="https://…" style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="browser_profile_id" label={ts('profile', 'Login profile')}
            extra={ts('profile_hint', 'The browser profile signed in to this store. It stays on this machine.')}>
            <Select allowClear placeholder={ts('profile_ph', 'Select or type…')}
              options={profiles.map((p) => ({ value: p.id, label: p.label || p.id }))} />
          </Form.Item>
          {!editing && (
            <Form.Item name="assign" label={ts('runs_on', 'Runs on')}
              extra={ts('unassigned_hint', 'Pick "This machine" to assign now, or "Unassigned" so the first machine to run it claims it automatically.')}>
              <Radio.Group optionType="button" buttonStyle="solid" size="small" options={[
                { value: 'here', label: ts('this_machine', 'This machine') },
                { value: 'none', label: ts('unassigned_short', 'Unassigned') },
              ]} />
            </Form.Item>
          )}
        </Form>
      </CompactForm>
    </Modal>
  );
};

export default StoreFormModal;
