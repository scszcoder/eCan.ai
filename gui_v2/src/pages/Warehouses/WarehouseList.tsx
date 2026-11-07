import React, { useState } from 'react';
import { List, Dropdown, Button, Modal, Input, Typography } from 'antd';
import { MoreOutlined, PlusOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import type { Warehouse } from './types';
import { useTranslation } from 'react-i18next';

interface WarehouseListProps {
  warehouses: Warehouse[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
}

const WarehouseList: React.FC<WarehouseListProps> = ({ warehouses, selectedId, onSelect, onRename, onDelete, onAdd }) => {
  const { t } = useTranslation();
  const [renameTarget, setRenameTarget] = useState<Warehouse | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const openRename = (w: Warehouse) => {
    setRenameTarget(w);
    setRenameValue(w.name);
  };
  const closeRename = () => { setRenameTarget(null); setRenameValue(''); };
  const confirmRename = () => {
    if (renameTarget) onRename(renameTarget.id, renameValue.trim() || renameTarget.name);
    closeRename();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Text strong style={{ color: 'var(--text-primary)' }}>{t('pages.warehouses.title')}</Typography.Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>{t('pages.warehouses.add')}</Button>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <List
          dataSource={warehouses}
          renderItem={(item) => {
            const menuItems: MenuProps['items'] = [
              { key: 'rename', label: t('common.rename', { defaultValue: 'Rename' }) },
              { type: 'divider' },
              { key: 'delete', label: t('common.delete'), danger: true },
            ];
            return (
              <List.Item
                onClick={() => onSelect(item.id)}
                style={{ cursor: 'pointer', paddingLeft: 16, paddingRight: 8, background: selectedId === item.id ? 'var(--surface-subtle-hover)' : 'transparent' }}
                actions={[
                  <Dropdown
                    key="menu"
                    menu={{ items: menuItems, onClick: ({ key }) => {
                      if (key === 'rename') openRename(item);
                      if (key === 'delete') onDelete(item.id);
                    } }}
                    trigger={["click"]}
                    placement="bottomRight"
                  >
                    <Button type="text" size="small" onClick={(e) => e.stopPropagation()} icon={<MoreOutlined />} />
                  </Dropdown>
                ]}
              >
                <List.Item.Meta
                  title={<span style={{ color: 'var(--text-primary)' }}>{item.name}</span>}
                  description={<span style={{ color: 'var(--text-secondary)' }}>{item.city}, {item.state}</span>}
                />
              </List.Item>
            );
          }}
        />
      </div>

      <Modal
        title={t('pages.warehouses.renameTitle')}
        open={!!renameTarget}
        onOk={confirmRename}
        onCancel={closeRename}
        okText={t('common.save')}
      >
        <Input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} placeholder={t('pages.warehouses.namePlaceholder')} />
      </Modal>
    </div>
  );
};

export default WarehouseList;
