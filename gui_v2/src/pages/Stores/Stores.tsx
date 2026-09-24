/**
 * Stores — the store as the top-level unit of the business.
 *
 * One call (`store.overview`) gives both halves: where each store runs (cloud
 * registry: assigned vs running machine, login state, billed cost) and what
 * this machine knows about it (agents and tasks serving it, outcomes recorded
 * against it). A store known on only one side still shows.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App } from 'antd';
import DetailLayout from '../../components/Layout/DetailLayout';
import { get_ipc_api } from '@/services/ipc_api';
import StoreList from './StoreList';
import StoreDetail from './StoreDetail';
import StoreFormModal, { type StoreDefinition } from './StoreFormModal';
import type { StoreOverview } from './types';

const Stores: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [data, setData] = useState<StoreOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // null = closed; 'new' = create; otherwise the definition being edited.
  const [form, setForm] = useState<'new' | StoreDefinition | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await get_ipc_api().getStoreOverview<StoreOverview>(showArchived);
      if (res.success && res.data) {
        setData(res.data);
      } else {
        message.error(t('pages.stores.load_failed', 'Failed to load stores'));
      }
    } catch {
      message.error(t('pages.stores.load_failed', 'Failed to load stores'));
    } finally {
      setLoading(false);
    }
  }, [showArchived, message, t]);

  useEffect(() => { load(); }, [load]);

  const stores = useMemo(() => data?.stores || [], [data]);
  useEffect(() => {
    if (stores.length && !stores.some((s) => s.storeId === selectedId)) {
      setSelectedId(stores[0].storeId);
    }
  }, [stores, selectedId]);

  const selected = stores.find((s) => s.storeId === selectedId) || null;

  return (
    <DetailLayout
      listTitle={null}
      detailsTitle={selected ? (selected.label || selected.storeId) : t('pages.stores.details', 'Store')}
      listContent={
        <StoreList
          stores={stores}
          thisVehicleId={data?.this_vehicle_id || ''}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading}
          onRefresh={load}
          showArchived={showArchived}
          onShowArchived={setShowArchived}
          cloudError={data?.cloud_error || ''}
          onAdd={() => setForm('new')}
        />
      }
      detailsContent={
        <>
          <StoreDetail store={selected} thisVehicleId={data?.this_vehicle_id || ''} onChanged={load}
            onEdit={(def) => setForm(def)} />
          <StoreFormModal
            open={form !== null}
            editing={form === 'new' ? null : form}
            onClose={() => setForm(null)}
            onSaved={(sid) => { setForm(null); setSelectedId(sid); load(); }}
          />
        </>
      }
      fillDetailsAvailableWidth
    />
  );
};

export default Stores;
