import React, { useState } from 'react';
import { Upload, Button, Progress, Modal, App } from 'antd';
import { UploadOutlined, InboxOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { UploadFile, RcFile } from 'antd/es/upload/interface';
import { get_ipc_api } from '@/services/ipc_api';
import './AvatarUploader.css';

const { Dragger } = Upload;

interface AvatarUploaderProps {
  username: string;
  onUploadSuccess?: (avatarData: any) => void;
  mode?: 'button' | 'dragger';
}

export const AvatarUploader: React.FC<AvatarUploaderProps> = ({
  username,
  onUploadSuccess,
  mode = 'button'
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewImage, setPreviewImage] = useState('');

  // Supported formats
  const SUPPORTED_IMAGE_FORMATS = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp'];
  const SUPPORTED_VIDEO_FORMATS = ['video/webm', 'video/mp4', 'video/quicktime', 'video/x-msvideo'];
  const SUPPORTED_FORMATS = [...SUPPORTED_IMAGE_FORMATS, ...SUPPORTED_VIDEO_FORMATS];
  
  const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB for images
  const MAX_VIDEO_SIZE = 50 * 1024 * 1024; // 50MB for videos

  const validateFile = (file: RcFile): boolean => {
    const isImage = SUPPORTED_IMAGE_FORMATS.includes(file.type);
    const isVideo = SUPPORTED_VIDEO_FORMATS.includes(file.type);

    // Check file type
    if (!isImage && !isVideo) {
      message.error(
        t('avatar.unsupported_format') || 
        'Unsupported format. Please upload PNG, JPG, GIF, WebP, WebM, or MP4.'
      );
      return false;
    }

    // Check file size based on type
    const maxSize = isVideo ? MAX_VIDEO_SIZE : MAX_IMAGE_SIZE;
    if (file.size > maxSize) {
      message.error(
        t('avatar.file_too_large') || 
        `File size exceeds ${maxSize / 1024 / 1024}MB limit.`
      );
      return false;
    }

    return true;
  };

  const convertFileToBase64 = (file: RcFile): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          // Remove data URL prefix (e.g., "data:image/png;base64,")
          const base64 = reader.result.split(',')[1];
          resolve(base64);
        } else {
          reject(new Error('Failed to convert file to base64'));
        }
      };
      reader.onerror = error => reject(error);
    });
  };

  const handleUpload = async (file: RcFile): Promise<void> => {
    if (!validateFile(file)) {
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    try {
      // Convert file to base64
      setUploadProgress(20);
      const fileData = await convertFileToBase64(file);
      
      setUploadProgress(40);

      // Upload to backend
      const api = get_ipc_api();
      const response = await api.uploadAvatar(
        username,
        fileData,
        file.name
      );

      setUploadProgress(80);

      if (response.success && response.data) {
        setUploadProgress(100);
        message.success(t('avatar.upload_success') || 'Avatar uploaded successfully!');
        
        if (onUploadSuccess) {
          onUploadSuccess(response.data);
        }
      } else {
        const errorMsg = response.error?.message || 'Upload failed';
        throw new Error(errorMsg);
      }
    } catch (error: any) {
      console.error('[AvatarUploader] Upload error:', error);
      message.error(
        t('avatar.upload_failed') || 
        `Upload failed: ${error.message || 'Unknown error'}`
      );
    } finally {
      setUploading(false);
      setTimeout(() => setUploadProgress(0), 1000);
    }
  };

  const handlePreview = async (file: UploadFile) => {
    if (!file.url && !file.preview) {
      file.preview = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.readAsDataURL(file.originFileObj as RcFile);
        reader.onload = () => resolve(reader.result as string);
      });
    }

    setPreviewImage(file.url || file.preview || '');
    setPreviewVisible(true);
  };

  const uploadProps = {
    accept: [
      ...SUPPORTED_FORMATS,
      '.png', '.jpg', '.jpeg', '.gif', '.webp',  // Image extensions
      '.webm', '.mp4', '.mov', '.avi'            // Video extensions
    ].join(','),
    beforeUpload: (file: RcFile) => {
      handleUpload(file);
      return false; // Prevent default upload behavior
    },
    onPreview: handlePreview,
    showUploadList: false,
    disabled: uploading
  };

  if (mode === 'dragger') {
    return (
      <div className="avatar-uploader-dragger">
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {t('avatar.click_or_drag') || 'Click or drag file to upload'}
          </p>
          <p className="ant-upload-hint">
            {t('avatar.upload_hint') || 'Support: PNG, JPG, GIF, WebP (Max 10MB) or WebM, MP4 video (Max 50MB)'}
          </p>
        </Dragger>
        
        {uploading && (
          <div className="upload-progress-container">
            <Progress percent={uploadProgress} status="active" />
          </div>
        )}

        <Modal
          open={previewVisible}
          title={t('avatar.preview') || 'Preview'}
          footer={null}
          onCancel={() => setPreviewVisible(false)}
        >
          <img alt="preview" style={{ width: '100%' }} src={previewImage} />
        </Modal>
      </div>
    );
  }

  return (
    <div className="avatar-uploader-button">
      <Upload {...uploadProps}>
        <Button
          icon={<UploadOutlined />}
          loading={uploading}
          disabled={uploading}
        >
          {uploading 
            ? t('avatar.uploading') || 'Uploading...' 
            : t('avatar.upload_avatar') || 'Upload Avatar'
          }
        </Button>
      </Upload>
      
      {uploading && (
        <div className="upload-progress-inline">
          <Progress 
            percent={uploadProgress} 
            size="small" 
            status="active"
            style={{ marginTop: 8 }}
          />
        </div>
      )}

      <Modal
        open={previewVisible}
        title={t('avatar.preview') || 'Preview'}
        footer={null}
        onCancel={() => setPreviewVisible(false)}
      >
        <img alt="preview" style={{ width: '100%' }} src={previewImage} />
      </Modal>
    </div>
  );
};

export default AvatarUploader;
