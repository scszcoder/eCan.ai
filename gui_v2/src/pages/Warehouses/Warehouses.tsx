import React, { useEffect, useMemo, useState } from 'react';
import DetailLayout from '../../components/Layout/DetailLayout';
import WarehouseList from './WarehouseList';
import WarehouseDetail from './WarehouseDetail';
import type { Warehouse } from './types';
import { useWarehouseStore } from '../../stores/warehouseStore';
import { useUserStore } from '../../stores/userStore';
import { useTranslation } from 'react-i18next';

const Warehouses: React.FC = () => {
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username || 'user');
  const { warehouses, fetch, save, remove, fetched } = useWarehouseStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!fetched) {
      fetch(username);
    }
  }, [fetched, fetch, username]);

  useEffect(() => {
    if (!selectedId && warehouses.length > 0) {
      setSelectedId(warehouses[0].id);
    }
  }, [warehouses, selectedId]);

  const selected = useMemo(() => warehouses.find(w => w.id === selectedId) ?? null, [warehouses, selectedId]);

  const handleAdd = () => {
    const newId = `wh-${Math.floor(Math.random() * 100000)}`;
    const w: Warehouse = {
      id: newId,
      name: t('pages.warehouses.newWarehouse'),
      city: '',
      state: '',
      contactFirstName: '',
      contactLastName: '',
      phone: '',
      email: '',
      messagingPlatform: '',
      messagingId: '',
      address1: '',
      address2: '',
      addressCity: '',
      addressState: '',
      addressZip: '',
      costDescription: '',
    };
    save(username, w).then(() => setSelectedId(newId));
  };

  const handleRename = (id: string, name: string) => {
    const cur = warehouses.find(w => w.id === id);
    if (cur) save(username, { ...cur, name });
  };

  const handleDelete = (id: string) => {
    remove(username, id).then(() => {
      if (selectedId === id) setSelectedId(null);
    });
  };

  const handleChange = (nw: Warehouse) => {
    save(username, nw);
  };

  return (
    <DetailLayout
      listTitle={null}
      detailsTitle={selected ? selected.name : t('pages.warehouses.details')}
      listContent={
        <WarehouseList
          warehouses={warehouses}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onRename={handleRename}
          onDelete={handleDelete}
          onAdd={handleAdd}
        />
      }
      detailsContent={<WarehouseDetail warehouse={selected} onChange={handleChange} />}
    />
  );
};

export default Warehouses;
