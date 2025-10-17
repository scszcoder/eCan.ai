import React, { useState, useEffect } from 'react';
import { Modal, Space, Divider } from 'antd';
import { useTranslation } from 'react-i18next';
import AvatarSelector, { AvatarData } from './AvatarSelector';
import AvatarUploader from './AvatarUploader';
import AvatarDisplay from './AvatarDisplay';

interface AvatarManagerProps {
  username: string;
  value?: AvatarData;
  onChange?: (avatarData: AvatarData) => void;
  showVideo?: boolean;
}

export const AvatarManager: React.FC<AvatarManagerProps> = ({
  username,
  value,
  onChange,
  showVideo = true
}) => {
  const { t } = useTranslation();
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedAvatar, setSelectedAvatar] = useState<AvatarData | undefined>(value);

  // 同步外部 value 的变化
  useEffect(() => {
    setSelectedAvatar(value);
  }, [value]);

  const handleAvatarSelect = (avatarData: AvatarData) => {
    setSelectedAvatar(avatarData);
    if (onChange) {
      onChange(avatarData);
    }
    setModalVisible(false);
  };

  const handleUploadSuccess = (uploadData: any) => {
    // Refresh the selector to show newly uploaded avatar
    // The selector will automatically reload uploaded avatars
    const newAvatar: AvatarData = {
      type: 'uploaded',
      hash: uploadData.hash,
      imageUrl: uploadData.imageUrl,
      thumbnailUrl: uploadData.thumbnailUrl,
      videoUrl: uploadData.videoUrl
    };
    
    setSelectedAvatar(newAvatar);
    if (onChange) {
      onChange(newAvatar);
    }
  };

  return (
    <div className="avatar-manager">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {/* Current Avatar Display */}
        <div style={{ textAlign: 'center' }}>
          <AvatarDisplay
            imageUrl={selectedAvatar?.thumbnailUrl || selectedAvatar?.imageUrl}
            videoUrl={selectedAvatar?.videoUrl}
            size="large"
            showVideo={showVideo}
            onClick={() => setModalVisible(true)}
          />
          <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
            {t('avatar.click_to_change') || 'Click to change avatar'}
          </div>
        </div>

        {/* Avatar Selection Modal */}
        <Modal
          title={t('avatar.select_avatar') || 'Select Avatar'}
          open={modalVisible}
          onCancel={() => setModalVisible(false)}
          footer={null}
          width={800}
          destroyOnHidden
        >
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* Upload Section */}
            <div>
              <h4>{t('avatar.upload_new') || 'Upload New Avatar'}</h4>
              <AvatarUploader
                username={username}
                onUploadSuccess={handleUploadSuccess}
                mode="dragger"
              />
            </div>

            <Divider />

            {/* Selection Section */}
            <div>
              <h4>{t('avatar.choose_existing') || 'Choose from Existing'}</h4>
              <AvatarSelector
                username={username}
                value={selectedAvatar}
                onChange={handleAvatarSelect}
                showVideo={showVideo}
              />
            </div>
          </Space>
        </Modal>
      </Space>
    </div>
  );
};

export default AvatarManager;
