import React from 'react';
import { Typography } from '@douyinfe/semi-ui';
import { Attachment } from '../types/chat';
import { FileUtils } from '../utils/fileUtils';
import { getFileTypeIcon } from '../utils/attachmentHandler';
import ImagePreview from './ImagePreview';

// Simple的后缀转MIMEType兜底
const getMimeType = (att: Attachment) => {
  if (att.mimeType && att.mimeType !== 'application/octet-stream') return att.mimeType;
  if (att.type && att.type !== 'application/octet-stream') return att.type;
  if (att.name) {
    const ext = att.name.split('.').pop()?.toLowerCase();
    if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg';
    if (ext === 'png') return 'image/png';
    if (ext === 'gif') return 'image/gif';
    if (ext === 'pdf') return 'application/pdf';
    if (ext === 'zip') return 'application/zip';
    if (ext === 'txt') return 'text/plain';
    // ...可Extended更多Type
  }
  return 'application/octet-stream';
};

const AttachmentList: React.FC<{ attachments?: Attachment[] }> = ({ attachments }) => {
  if (!attachments || attachments.length === 0) return null;
  return (
    <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
      {attachments.map(att => {
        const mimeType = getMimeType(att);
        const isImage = FileUtils.isImageFile(mimeType);
        const filePath = att.url?.startsWith('pyqtfile://') ? att.url : (att.url ? `pyqtfile://${att.url}` : '');
        if (isImage) {
          return (
            <div key={att.uid} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <ImagePreview filePath={filePath} fileName={att.name || ''} mimeType={mimeType} />
              <Typography.Text size="small" type="tertiary" style={{ marginTop: 4, maxWidth: 120, textAlign: 'center' }}>
                {att.name}
              </Typography.Text>
            </div>
          );
        }
        // 文件附件
        return (
          <div
            key={att.uid}
            className="file-attachment"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 12px',
              border: '1px solid var(--semi-color-border)',
              borderRadius: 4,
              marginBottom: 8,
              maxWidth: 300,
              cursor: filePath ? 'pointer' : 'not-allowed',
              opacity: filePath ? 1 : 0.5
            }}
            onClick={() => filePath && att.name && FileUtils.downloadFile(filePath, att.name)}
            title={filePath ? 'Click下载' : '无效文件'}
          >
            <span style={{ fontSize: 20 }}>{getFileTypeIcon(att.name || '', mimeType)}</span>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <Typography.Text ellipsis>{att.name}</Typography.Text>
              <Typography.Text size="small" type="tertiary">{mimeType}</Typography.Text>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default AttachmentList; 