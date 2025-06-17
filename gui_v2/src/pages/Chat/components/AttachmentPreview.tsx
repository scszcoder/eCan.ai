import React from 'react';
import { Button, Space, Typography } from 'antd';
import { PaperClipOutlined, DownloadOutlined, CloseOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { Attachment } from '../types/chat';

const { Text } = Typography;

const AttachmentPreviewWrapper = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 0 0;
    border-top: 1px dashed #e0e0e0;
    padding-top: 4px;
`;

const AttachmentItem = styled.div`
    background: #f6f6f6;
    padding: 6px 10px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
`;

interface AttachmentPreviewProps {
    attachments: Attachment[];
    onRemove?: (id: string) => void;
    isPreview?: boolean;
}

const AttachmentPreview: React.FC<AttachmentPreviewProps> = ({
    attachments,
    onRemove,
    isPreview = false
}) => {
    return (
        <AttachmentPreviewWrapper>
            {attachments.map((att) => (
                <AttachmentItem key={att.id}>
                    <PaperClipOutlined />
                    <a
                        href={att.url}
                        download={att.name}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ marginLeft: 4, fontSize: 12 }}
                    >
                        {att.name}
                        <DownloadOutlined style={{ marginLeft: 6 }} />
                    </a>
                    {isPreview && onRemove && (
                        <Button
                            size="small"
                            type="text"
                            icon={<CloseOutlined />}
                            onClick={() => onRemove(att.id)}
                        />
                    )}
                </AttachmentItem>
            ))}
        </AttachmentPreviewWrapper>
    );
};

export default AttachmentPreview; 