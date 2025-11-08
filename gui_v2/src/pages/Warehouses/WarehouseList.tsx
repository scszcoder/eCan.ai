import React, { useState } from 'react';
import { List, Dropdown, Button, Modal, Input, Typography } from 'antd';
import { MoreOutlined, PlusOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import type { Warehouse } from './types';

interface WarehouseListProps {
  warehouses: Warehouse[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
}

const WarehouseList: React.FC<WarehouseListProps> = ({ warehouses, selectedId, onSelect, onRename, onDelete, onAdd }) => {
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
        <Typography.Text strong style={{ color: '#fff' }}>Warehouses</Typography.Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>Add New</Button>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <List
          dataSource={warehouses}
          renderItem={(item) => {
            const menuItems: MenuProps['items'] = [
              { key: 'rename', label: 'Rename' },
              { type: 'divider' },
              { key: 'delete', label: 'Delete', danger: true },
            ];
            return (
              <List.Item
                onClick={() => onSelect(item.id)}
                style={{ cursor: 'pointer', paddingLeft: 16, paddingRight: 8, background: selectedId === item.id ? 'rgba(255,255,255,0.06)' : 'transparent' }}
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
                  title={<span style={{ color: '#fff' }}>{item.name}</span>}
                  description={<span style={{ color: 'rgba(255,255,255,0.65)' }}>{item.city}, {item.state}</span>}
                />
              </List.Item>
            );
          }}
        />
      </div>

      <Modal
        title="Rename Warehouse"
        open={!!renameTarget}
        onOk={confirmRename}
        onCancel={closeRename}
        okText="Save"
      >
        <Input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} placeholder="Warehouse name" />
      </Modal>
    </div>
  );
};

export default WarehouseList;
