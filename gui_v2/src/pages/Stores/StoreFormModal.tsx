/**
 * Create or edit a store's definition: name, id, platform, URLs, login profile.
 * Creating also says where it should run: this machine, or unassigned (the
 * first machine to run it claims it).
 */
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Form, Input, Modal, Radio, Select } from 'antd';
import { get_ipc_api } from '@/services/ipc_api';
import { PLATFORMS } from '@/components/FastDeploy/scenarios';

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

const StoreFormModal: React.FC<Props> = ({ open, editing, onClose, onSaved }) => {
  const { t, i18n } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [profiles, setProfiles] = useState<{ id: string; label: string }[]>([]);
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
      destroyOnClose
    >
      <Form form={form} layout="vertical"
        onValuesChange={(changed) => {
          // The id follows the name until the user edits it.
          if ('name' in changed && !idTouched && !editing) {
            form.setFieldsValue({ store_id: String(changed.name || '').trim() });
          }
          if ('store_id' in changed) setIdTouched(true);
        }}
      >
        <Form.Item name="name" label={ts('name', 'Name')} rules={[{ required: true, whitespace: true }]}>
          <Input placeholder={ts('name_ph', 'e.g. 小店一号')} />
        </Form.Item>
        <Form.Item name="store_id" label={ts('store_id', 'Store ID')}
          extra={ts('store_id_hint', 'Permanent. Every 飞鸽 seller shares one workstation URL, so this, not the URL, is what tells stores apart.')}
          rules={[{ required: true, whitespace: true },
            { validator: (_, v) => (/^https?:\/\//i.test(String(v || '')) ? Promise.reject(ts('id_is_url', 'Use a name, not a URL')) : Promise.resolve()) }]}>
          <Input disabled={!!editing} />
        </Form.Item>
        <Form.Item name="platform" label={ts('platform', 'Platform')} rules={[{ required: true }]}>
          <Select options={PLATFORMS.map((p) => ({ value: p.value, label: zh ? p.nameZh : p.nameEn }))} />
        </Form.Item>
        <Form.Item name="urls" label={ts('urls', 'Store URLs (one per line)')}>
          <Input.TextArea rows={3} placeholder="https://…" />
        </Form.Item>
        <Form.Item name="browser_profile_id" label={ts('profile', 'Login profile')}
          extra={ts('profile_hint', 'The browser profile signed in to this store. It stays on this machine.')}>
          <Select allowClear options={profiles.map((p) => ({ value: p.id, label: p.label || p.id }))} />
        </Form.Item>
        {!editing && (
          <Form.Item name="assign" label={ts('runs_on', 'Runs on')}>
            <Radio.Group options={[
              { value: 'here', label: ts('this_machine', 'This machine') },
              { value: 'none', label: ts('unassigned', 'Unassigned: the first machine to run it claims it') },
            ]} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
};

export default StoreFormModal;
