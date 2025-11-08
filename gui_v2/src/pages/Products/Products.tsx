import React, { useEffect, useMemo, useState } from 'react';
import DetailLayout from '../../components/Layout/DetailLayout';
import ProductsList from './ProductsList';
import ProductDetail from './ProductDetail';
import type { Product } from './types';
import { useProductStore } from '../../stores/productStore';
import { useUserStore } from '../../stores/userStore';
import { useTranslation } from 'react-i18next';

const Products: React.FC = () => {
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username || 'user');
  const { products, fetch, save, remove, fetched } = useProductStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!fetched) fetch(username);
  }, [fetched, fetch, username]);

  useEffect(() => {
    if (!selectedId && products.length > 0) setSelectedId(products[0].id);
  }, [products, selectedId]);

  const selected = useMemo(() => products.find(p => p.id === selectedId) ?? null, [products, selectedId]);

  const handleAdd = () => {
    const newId = `p-${Math.floor(Math.random() * 100000)}`;
    const p: Product = {
      id: newId,
      nickName: t('pages.products.newProduct'),
      title: '', features: '', sizeL: '', sizeW: '', sizeH: '', weightOz: '',
      fragile: false, batteryInside: false, chemical: false, flammable: false,
      inventories: [], dropShippers: [], media: [], suppliers: [], platforms: [],
    };
    save(username, p).then(() => setSelectedId(newId));
  };

  const handleRename = (id: string, name: string) => {
    const cur = products.find(p => p.id === id);
    if (cur) save(username, { ...cur, nickName: name });
  };

  const handleDelete = (id: string) => {
    remove(username, id).then(() => {
      if (selectedId === id) setSelectedId(null);
    });
  };

  const handleChange = (np: Product) => {
    save(username, np);
  };

  return (
    <DetailLayout
      listTitle={null}
      detailsTitle={selected ? (selected.nickName || selected.title) : t('pages.products.details')}
      listContent={
        <ProductsList
          products={products}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onRename={handleRename}
          onDelete={handleDelete}
          onAdd={handleAdd}
        />
      }
      detailsContent={<ProductDetail product={selected} onChange={handleChange} />}
    />
  );
};

export default Products;
