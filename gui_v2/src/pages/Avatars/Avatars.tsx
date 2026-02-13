import React, { useCallback, useEffect, useState } from 'react';
import { Button, Tooltip, Space, message } from 'antd';
import {
  ReloadOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useUserStore } from '../../stores/userStore';
import { useAvatarMarketStore } from './avatarMarketStore';
import AvatarList from './components/AvatarList';
import AvatarDetails from './components/AvatarDetails';
import type { AvatarItem, AvatarViewMode } from './types';

const Avatars: React.FC = () => {
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username);

  const avatars = useAvatarMarketStore((s) => s.avatars);
  const loading = useAvatarMarketStore((s) => s.loading);
  const fetchAvatars = useAvatarMarketStore((s) => s.fetch);
  const forceRefresh = useAvatarMarketStore((s) => s.forceRefresh);

  const [selected, setSelected] = useState<AvatarItem | null>(null);
  const [viewMode, setViewMode] = useState<AvatarViewMode>(() => {
    try {
      const raw = localStorage.getItem('avatars:list_view_mode');
      return raw === 'list' ? 'list' : 'grid';
    } catch {
      return 'grid';
    }
  });

  useEffect(() => {
    if (username) fetchAvatars(username);
  }, [username, fetchAvatars]);

  const handleRefresh = useCallback(async () => {
    if (!username) return;
    try {
      await forceRefresh(username);
    } catch {
      message.error('Failed to refresh avatars');
    }
  }, [username, forceRefresh]);

  const setGridMode = useCallback(() => {
    setViewMode('grid');
    try { localStorage.setItem('avatars:list_view_mode', 'grid'); } catch {}
  }, []);

  const setListMode = useCallback(() => {
    setViewMode('list');
    try { localStorage.setItem('avatars:list_view_mode', 'list'); } catch {}
  }, []);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <span style={{ fontSize: 16, fontWeight: 600, lineHeight: '24px' }}>
        {t('menu.avatars', 'Avatars')}
      </span>
      <Space>
        <Tooltip title="List view">
          <Button
            type="text" shape="circle"
            icon={<UnorderedListOutlined />}
            onClick={setListMode}
            style={{
              background: viewMode === 'list' ? 'rgba(255,255,255,0.06)' : 'transparent',
              border: 'none', color: 'rgba(203,213,225,0.9)', boxShadow: 'none',
            }}
          />
        </Tooltip>
        <Tooltip title="Grid view">
          <Button
            type="text" shape="circle"
            icon={<AppstoreOutlined />}
            onClick={setGridMode}
            style={{
              background: viewMode === 'grid' ? 'rgba(255,255,255,0.06)' : 'transparent',
              border: 'none', color: 'rgba(203,213,225,0.9)', boxShadow: 'none',
            }}
          />
        </Tooltip>
        <Tooltip title="Refresh">
          <Button
            type="text" shape="circle"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
            style={{ background: 'transparent', border: 'none', color: 'rgba(203,213,225,0.9)', boxShadow: 'none' }}
          />
        </Tooltip>
      </Space>
    </div>
  );

  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={selected ? (selected.name || 'Avatar Details') : 'Avatar Details'}
      resizableList
      listWidthStorageKey="avatars:list_panel_width"
      defaultListWidth={380}
      minListWidth={300}
      maxListWidth={640}
      listContent={
        <AvatarList
          avatars={avatars}
          loading={loading}
          selectedId={selected?.id ?? null}
          viewMode={viewMode}
          onSelect={setSelected}
        />
      }
      detailsContent={
        selected ? <AvatarDetails avatar={selected} /> : undefined
      }
    />
  );
};

export default Avatars;
