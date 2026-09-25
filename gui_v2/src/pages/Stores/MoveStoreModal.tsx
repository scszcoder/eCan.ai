/**
 * Move a store to another machine AND bring its login along (cookies, device
 * data, fingerprint, proxy) so the site keeps seeing the same device.
 *
 * The warning + checkbox are required, not decoration: a live seller login is
 * being copied (docs/OWN_FINGERPRINT_BROWSER.md -- user-commanded, one login,
 * warned first). The backend refuses the move without `confirmed`.
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, App, Checkbox, Modal, Select, Space, Typography } from 'antd';
import { get_ipc_api } from '@/services/ipc_api';
import type { StoreMachine, StoreRow } from './types';

interface Props {
  open: boolean;
  store: StoreRow;
  machines: StoreMachine[];
  thisVehicleId: string;
  onClose: () => void;
  onMoved: () => void;
}

const MoveStoreModal: React.FC<Props> = ({ open, store, machines, thisVehicleId, onClose, onMoved }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const tf = (k: string, d: string) => t(`fleet.${k}`, { defaultValue: d }) as string;
  const [target, setTarget] = useState<string>();
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);

  const from = store.assignedVehicleId || store.reportedVehicleId || '';
  // A login runs in a desktop browser: cloud pods are not a destination.
  const options = machines
    .filter((m) => m.id !== from && m.type !== 'cloud')
    .map((m) => ({
      value: m.id,
      label: `${m.id === thisVehicleId ? tf('this_machine', 'This machine') + ' · ' : ''}${m.name}`
        + (m.status !== 'active' ? ` · ${tf('offline', 'offline')}` : ''),
    }));

  const submit = async () => {
    if (!target || !agreed) return;
    setBusy(true);
    try {
      const res: any = await get_ipc_api().moveStoreWithLogin(
        store.storeId, target, true, store.definition?.browser_profile_id || '');
      if (res?.success) {
        message.success(tf('move_started', 'Moving — both machines pick this up within a minute'));
        onMoved();
        onClose();
      } else {
        message.error(res?.error?.message || tf('failed', 'Request failed'));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} title={tf('move_title', 'Move store with its login')} onCancel={onClose}
      onOk={submit} okText={tf('move_ok', 'Move')} confirmLoading={busy}
      okButtonProps={{ disabled: !target || !agreed, danger: true }} destroyOnClose>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Select style={{ width: '100%' }} placeholder={tf('move_to', 'Move to…')}
          value={target} onChange={setTarget} options={options} />
        <Alert type="warning" showIcon message={tf('move_warn_title', 'A live seller login will be copied')}
          description={
            <Space direction="vertical" size={4}>
              <Typography.Text>{tf('move_warn_1', "This copies the store's logged-in browser session — cookies, site data, fingerprint — and its proxy credentials to the machine you picked.")}</Typography.Text>
              <Typography.Text>{tf('move_warn_2', 'It travels encrypted so only that machine can open it: straight across when the two share a LAN, through the cloud otherwise.')}</Typography.Text>
              <Typography.Text>{tf('move_warn_3', 'The store stops here first and starts there once the login has arrived. The old copy is kept but will refuse to open.')}</Typography.Text>
            </Space>
          } />
        <Checkbox checked={agreed} onChange={(e) => setAgreed(e.target.checked)}>
          {tf('move_agree', 'I understand a logged-in session and its proxy credentials are being copied')}
        </Checkbox>
      </Space>
    </Modal>
  );
};

export default MoveStoreModal;
