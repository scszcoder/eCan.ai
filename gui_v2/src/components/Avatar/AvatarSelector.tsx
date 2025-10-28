import React, { useState, useEffect } from 'react';
import { Tabs, Card, Row, Col, Spin, App, Empty, Badge } from 'antd';
import type { TabsProps } from 'antd';
import { PlayCircleOutlined, PictureOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import './AvatarSelector.css';

export interface AvatarData {
  type: 'system' | 'uploaded' | 'generated';
  id?: string;
  name?: string;
  hash?: string;
  imageUrl: string;
  videoUrl?: string;
  thumbnailUrl?: string;
  tags?: string[];
  imageExists?: boolean;
  videoExists?: boolean;
}

interface AvatarSelectorProps {
  value?: AvatarData;
  onChange?: (avatarData: AvatarData) => void;
  showVideo?: boolean;
  username: string;
  defaultActiveTab?: string;
  onTabChange?: (activeKey: string) => void;
}

export const AvatarSelector: React.FC<AvatarSelectorProps> = ({
  value,
  onChange,
  showVideo = true,
  username,
  defaultActiveTab = 'system',
  onTabChange
}) => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [systemAvatars, setSystemAvatars] = useState<AvatarData[]>([]);
  const [uploadedAvatars, setUploadedAvatars] = useState<AvatarData[]>([]);
  const [selectedAvatar, setSelectedAvatar] = useState<AvatarData | undefined>(value);
  const [hoveredAvatar, setHoveredAvatar] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>(defaultActiveTab);

  useEffect(() => {
    loadSystemAvatars();
    loadUploadedAvatars();
  }, [username]);

  useEffect(() => {
    setSelectedAvatar(value);
  }, [value]);

  const loadSystemAvatars = async () => {
    setLoading(true);
    try {
      const api = get_ipc_api();
      const response = await api.getSystemAvatars<AvatarData[]>(username);
      
      if (response.success && response.data) {
        setSystemAvatars(response.data);
      } else {
        message.error(t('avatar.load_system_failed') || 'Failed to load system avatars');
      }
    } catch (error) {
      console.error('[AvatarSelector] Failed to load system avatars:', error);
      message.error(t('avatar.load_system_failed') || 'Failed to load system avatars');
    } finally {
      setLoading(false);
    }
  };

  const loadUploadedAvatars = async () => {
    try {
      const api = get_ipc_api();
      const response = await api.getUploadedAvatars<AvatarData[]>(username);
      
      if (response.success && response.data) {
        setUploadedAvatars(response.data);
      }
    } catch (error) {
      console.error('[AvatarSelector] Failed to load uploaded avatars:', error);
    }
  };

  const handleSelectAvatar = (avatar: AvatarData) => {
    setSelectedAvatar(avatar);
    if (onChange) {
      onChange(avatar);
    }
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (onTabChange) {
      onTabChange(key);
    }
  };

  const handleDeleteAvatar = async (avatar: AvatarData, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止Event冒泡到卡片的 onClick
    
    if (!avatar.id) {
      message.error(t('avatar.delete_no_id') || 'Cannot delete avatar without ID');
      return;
    }

    modal.confirm({
      title: t('avatar.delete_confirm_title') || 'Delete Avatar',
      content: t('avatar.delete_confirm_message') || 'Are you sure you want to delete this avatar? This action cannot be undone.',
      okText: t('common.delete') || 'Delete',
      okType: 'danger',
      cancelText: t('common.cancel') || 'Cancel',
      onOk: async () => {
        try {
          const api = get_ipc_api();
          const response = await api.deleteUploadedAvatar<any>(username, avatar.id!);
          
          if (response.success) {
            message.success(t('avatar.delete_success') || 'Avatar deleted successfully');
            // Refresh上传的 Avatar List
            await loadUploadedAvatars();
            // IfDelete的是When前选中的 Avatar，清除选中Status
            if (selectedAvatar?.id === avatar.id) {
              setSelectedAvatar(undefined);
              if (onChange) {
                onChange(undefined as any);
              }
            }
          } else {
            const errorMsg = typeof response.error === 'string' 
              ? response.error 
              : (response.error?.message || t('avatar.delete_failed') || 'Failed to delete avatar');
            message.error(errorMsg);
          }
        } catch (error) {
          console.error('[AvatarSelector] Failed to delete avatar:', error);
          message.error(t('avatar.delete_failed') || 'Failed to delete avatar');
        }
      },
    });
  };

  const renderAvatarCard = (avatar: AvatarData, index: number, showDelete: boolean = false) => {
    const isSelected = selectedAvatar?.imageUrl === avatar.imageUrl;
    const isHovered = hoveredAvatar === avatar.imageUrl;
    const showVideoPreview = showVideo && isHovered && avatar.videoUrl && avatar.videoExists;
    
    // Generate unique key: prefer id, hash, or imageUrl, fallback to index
    const uniqueKey = avatar.id || avatar.hash || avatar.imageUrl || `avatar-${index}`;

    return (
      <Col xs={12} sm={8} md={6} key={uniqueKey}>
        <Card
          hoverable
          className={`avatar-card ${isSelected ? 'avatar-card-selected' : ''}`}
          onClick={() => handleSelectAvatar(avatar)}
          onMouseEnter={() => setHoveredAvatar(avatar.imageUrl)}
          onMouseLeave={() => setHoveredAvatar(null)}
          cover={
            <div className="avatar-card-cover">
              {showVideoPreview ? (
                <video
                  src={avatar.videoUrl}
                  autoPlay
                  loop
                  muted
                  className="avatar-preview-video"
                />
              ) : (
                <img
                  src={avatar.thumbnailUrl || avatar.imageUrl}
                  alt={avatar.name || 'Avatar'}
                  className="avatar-preview-image"
                />
              )}
              {avatar.videoExists && (
                <Badge
                  count={<PlayCircleOutlined style={{ color: '#1890ff' }} />}
                  className="avatar-video-badge"
                />
              )}
              {showDelete && (
                <div 
                  className="avatar-delete-button"
                  onClick={(e) => handleDeleteAvatar(avatar, e)}
                >
                  <CloseCircleOutlined />
                </div>
              )}
            </div>
          }
        >
          {avatar.name && (
            <Card.Meta
              title={avatar.name}
              description={
                avatar.tags && avatar.tags.length > 0 ? (
                  <div className="avatar-tags">
                    {avatar.tags.slice(0, 2).map(tag => (
                      <span key={tag} className="avatar-tag">{tag}</span>
                    ))}
                  </div>
                ) : null
              }
            />
          )}
        </Card>
      </Col>
    );
  };

  const tabItems: TabsProps['items'] = [
    {
      key: 'system',
      label: (
        <span>
          <PictureOutlined />
          {t('avatar.system_avatars') || 'System Avatars'}
        </span>
      ),
      children: (
        <Spin spinning={loading}>
          {systemAvatars.length > 0 ? (
            <Row gutter={[16, 16]}>
              {systemAvatars.map((avatar, index) => renderAvatarCard(avatar, index))}
            </Row>
          ) : (
            <Empty description={t('avatar.no_system_avatars') || 'No system avatars available'} />
          )}
        </Spin>
      ),
    },
    {
      key: 'uploaded',
      label: (
        <span>
          <PictureOutlined />
          {t('avatar.my_avatars') || 'My Avatars'}
        </span>
      ),
      children: (
        uploadedAvatars.length > 0 ? (
          <Row gutter={[16, 16]}>
            {uploadedAvatars.map((avatar, index) => renderAvatarCard(avatar, index, true))}
          </Row>
        ) : (
          <Empty description={t('avatar.no_uploaded_avatars') || 'No uploaded avatars yet'} />
        )
      ),
    },
  ];

  return (
    <div className="avatar-selector">
      <Tabs 
        activeKey={activeTab}
        onChange={handleTabChange}
        items={tabItems} 
      />
    </div>
  );
};

export default AvatarSelector;
