import React, { useCallback, useEffect, useState } from 'react';
import { Button, Tooltip, Space, App as AntApp, Modal, ConfigProvider, theme } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import AvatarUploader from '../../components/Avatar/AvatarUploader';
import { useUserStore } from '../../stores/userStore';
import { useAvatarMarketStore } from './avatarMarketStore';
import AvatarList from './components/AvatarList';
import AvatarDetails from './components/AvatarDetails';
import type { AvatarItem, AvatarViewMode } from './types';

const Avatars: React.FC = () => {
  const { t } = useTranslation();
  const { message } = AntApp.useApp();
  const username = useUserStore((s) => s.username);

  const avatars = useAvatarMarketStore((s) => s.avatars);
  const loading = useAvatarMarketStore((s) => s.loading);
  const fetchAvatars = useAvatarMarketStore((s) => s.fetch);
  const forceRefresh = useAvatarMarketStore((s) => s.forceRefresh);
  const upsertAvatar = useAvatarMarketStore((s) => s.upsertAvatar);

  const [selected, setSelected] = useState<AvatarItem | null>(null);
  const [viewMode, setViewMode] = useState<AvatarViewMode>(() => {
    try {
      const raw = localStorage.getItem('avatars:list_view_mode');
      return raw === 'list' ? 'list' : 'grid';
    } catch {
      return 'grid';
    }
  });
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    if (username) fetchAvatars(username);
  }, [username, fetchAvatars]);

  // Keep selection in sync with the underlying list.
  useEffect(() => {
    if (!selected) return;
    const fresh = avatars.find((a) => a.id === selected.id);
    if (fresh && fresh !== selected) {
      setSelected(fresh);
    }
  }, [avatars, selected]);

  const handleRefresh = useCallback(async () => {
    if (!username) return;
    try {
      await forceRefresh(username);
    } catch {
      message.error(t('avatar.load_system_failed', 'Failed to refresh avatars'));
    }
  }, [username, forceRefresh, message, t]);

  const handleUploaded = useCallback((data: any) => {
    if (!data || !data.id) return;
    const imageUrl = data.imageUrl || data.thumbnailUrl || data.cloud_image_url || '';
    const videoUrl = data.videoUrl || data.cloud_video_url || '';
    const item: AvatarItem = {
      id: data.id,
      name: data.name || data.id,
      owner: username || data.owner || '',
      resource_type: videoUrl ? 'video' : 'image',
      description: data.description,
      cloud_image_url: data.cloud_image_url || imageUrl,
      cloud_video_url: data.cloud_video_url || videoUrl,
      presigned_image_url: imageUrl,
      presigned_video_url: videoUrl,
      is_public: data.is_public ?? false,
      image_hash: data.hash,
    };
    upsertAvatar(item);
    setSelected(item);
    setUploadOpen(false);
  }, [upsertAvatar, username]);

  const setGridMode = useCallback(() => {
    setViewMode('grid');
    try { localStorage.setItem('avatars:list_view_mode', 'grid'); } catch {}
  }, []);

  const setListMode = useCallback(() => {
    setViewMode('list');
    try { localStorage.setItem('avatars:list_view_mode', 'list'); } catch {}
  }, []);

  const iconButtonStyle = (active: boolean): React.CSSProperties => ({
    background: active ? 'var(--primary-bg)' : 'transparent',
    border: 'none',
    color: active ? 'var(--primary-text)' : 'var(--text-secondary)',
    boxShadow: 'none',
  });

  const handleClose = useCallback(() => setSelected(null), []);

  return (
    <div className="page-shell page-shell--fill" style={{ display: 'flex', flexDirection: 'column', padding: 0 }}>
      {/* Compact top toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-md) var(--space-lg)',
        borderBottom: '1px solid var(--border-color)',
        background: 'var(--surface-inset)',
      }}>
        <span className="page-title" style={{ margin: 0 }}>
          {t('menu.avatars', 'Avatars')}
          <span style={{ marginLeft: 10, fontSize: 'var(--font-size-sm)', color: 'var(--text-tertiary)', fontWeight: 400 }}>
            {avatars.length} {t('avatar.count_label', 'items')}
          </span>
        </span>
        <Space size={6}>
          <Tooltip title={t('avatar.upload_new')}>
            <Button
              type="primary"
              icon={<span>＋</span>}
              onClick={() => setUploadOpen(true)}
              disabled={!username}
              size="middle"
            >
              {t('avatar.upload_new')}
            </Button>
          </Tooltip>
          <Tooltip title="List view">
            <Button
              type="text"
              shape="circle"
              icon={<span style={{ fontSize: 14 }}>☰</span>}
              onClick={setListMode}
              style={iconButtonStyle(viewMode === 'list')}
            />
          </Tooltip>
          <Tooltip title="Grid view">
            <Button
              type="text"
              shape="circle"
              icon={<span style={{ fontSize: 14 }}>▦</span>}
              onClick={setGridMode}
              style={iconButtonStyle(viewMode === 'grid')}
            />
          </Tooltip>
          <Tooltip title="Refresh">
            <Button
              type="text"
              shape="circle"
              icon={<span style={{ fontSize: 14 }}>↻</span>}
              onClick={handleRefresh}
              loading={loading}
              style={iconButtonStyle(false)}
            />
          </Tooltip>
        </Space>
      </div>

      {/* Full-width grid */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <AvatarList
          avatars={avatars}
          loading={loading}
          selectedId={selected?.id ?? null}
          viewMode={viewMode}
          onSelect={setSelected}
        />
      </div>

      {/* Detail Modal */}
      <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
        <Modal
          open={!!selected}
          onCancel={handleClose}
          footer={null}
          width={760}
          centered
          destroyOnHidden
          closable={false}
          styles={{
            body: { padding: 0, maxHeight: 'calc(90vh - 0px)', overflowY: 'auto' },
            content: { padding: 0, background: 'var(--bg-primary, #0f172a)' },
          }}
          title={
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 'var(--space-sm) var(--space-md)',
              borderBottom: '1px solid var(--border-color)',
            }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>
                {selected?.name || t('avatar.details', 'Avatar Details')}
              </span>
              <Button
                type="text"
                shape="circle"
                icon={<CloseOutlined />}
                onClick={handleClose}
              />
            </div>
          }
        >
          {selected && (
            <div style={{ padding: 18 }}>
              <AvatarDetails
                key={selected.id}
                avatar={selected}
                onSelectRelated={(a) => setSelected(a)}
              />
            </div>
          )}
        </Modal>
      </ConfigProvider>

      {/* Upload Modal */}
      <Modal
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        title={t('avatar.upload_new')}
        destroyOnHidden
        width={520}
      >
        {username && (
          <AvatarUploader
            username={username}
            onUploadSuccess={handleUploaded}
            mode="dragger"
          />
        )}
      </Modal>
    </div>
  );
};

export default Avatars;