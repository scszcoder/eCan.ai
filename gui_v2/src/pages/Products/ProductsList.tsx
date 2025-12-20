import React, { useState } from 'react';
import { List, Dropdown, Button, Modal, Input, Typography, Avatar } from 'antd';
import { MoreOutlined, PlusOutlined, PictureOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import type { Product } from './types';
import { useTranslation } from 'react-i18next';

interface ProductsListProps {
  products: Product[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void; // rename nickName/title
  onDelete: (id: string) => void;
  onAdd: () => void;
}

const ProductsList: React.FC<ProductsListProps> = ({ products, selectedId, onSelect, onRename, onDelete, onAdd }) => {
  const { t } = useTranslation();
  const [renameTarget, setRenameTarget] = useState<Product | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const openRename = (p: Product) => {
    setRenameTarget(p);
    setRenameValue(p.nickName || p.title || '');
  };
  const closeRename = () => { setRenameTarget(null); setRenameValue(''); };
  const confirmRename = () => {
    if (renameTarget) onRename(renameTarget.id, renameValue.trim() || (renameTarget.nickName || renameTarget.title));
    closeRename();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Text strong style={{ color: '#fff' }}>{t('pages.products.title')}</Typography.Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>{t('pages.products.add')}</Button>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <List
          dataSource={products}
          renderItem={(item) => {
            const name = item.nickName || item.title;
            const thumbUrl = item.media && item.media.length > 0 ? item.media[0].url : undefined;
            const totalQty = (item.inventories || []).reduce((sum, inv) => sum + (parseFloat(inv.quantity) || 0), 0);
            const menuItems: MenuProps['items'] = [
              { key: 'rename', label: t('common.rename', { defaultValue: 'Rename' }) },
              { type: 'divider' },
              { key: 'delete', label: t('common.delete'), danger: true },
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
                  avatar={<Avatar shape="square" size={40} src={thumbUrl} icon={!thumbUrl ? <PictureOutlined /> : undefined} />}
                  title={<span style={{ color: '#fff' }}>{name}</span>}
                  description={
                    <div>
                      <div style={{ color: 'rgba(255,255,255,0.65)' }}>
                        {t('pages.products.totalInventory', { count: totalQty })}
                      </div>
                    </div>
                  }
                />
              </List.Item>
            );
          }}
        />
      </div>

      <Modal
        title={t('pages.products.renameTitle')}
        open={!!renameTarget}
        onOk={confirmRename}
        onCancel={closeRename}
        okText={t('common.save')}
      >
        <Input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} placeholder={t('pages.products.namePlaceholder')} />
      </Modal>
    </div>
  );
};

export default ProductsList;
