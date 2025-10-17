import React, { useState, useEffect } from 'react';
import { Tabs, Card, Row, Col, Spin, App, Empty, Badge } from 'antd';
import type { TabsProps } from 'antd';
import { PlayCircleOutlined, PictureOutlined } from '@ant-design/icons';
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
}

export const AvatarSelector: React.FC<AvatarSelectorProps> = ({
  value,
  onChange,
  showVideo = true,
  username
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [systemAvatars, setSystemAvatars] = useState<AvatarData[]>([]);
  const [uploadedAvatars, setUploadedAvatars] = useState<AvatarData[]>([]);
  const [selectedAvatar, setSelectedAvatar] = useState<AvatarData | undefined>(value);
  const [hoveredAvatar, setHoveredAvatar] = useState<string | null>(null);

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

  const renderAvatarCard = (avatar: AvatarData, index: number) => {
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
            {uploadedAvatars.map((avatar, index) => renderAvatarCard(avatar, index))}
          </Row>
        ) : (
          <Empty description={t('avatar.no_uploaded_avatars') || 'No uploaded avatars yet'} />
        )
      ),
    },
  ];

  return (
    <div className="avatar-selector">
      <Tabs defaultActiveKey="system" items={tabItems} />
    </div>
  );
};

export default AvatarSelector;
