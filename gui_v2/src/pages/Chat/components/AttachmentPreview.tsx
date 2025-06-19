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
    margin: 0;
`;

const AttachmentItem = styled.div`
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    padding: 8px 12px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: var(--transition-fast);
    box-shadow: var(--shadow-sm);
    
    &:hover {
        border-color: var(--primary-color);
        box-shadow: var(--shadow-md);
    }
`;

const AttachmentIcon = styled(PaperClipOutlined)`
    color: var(--text-secondary);
    font-size: 14px;
`;

const AttachmentLink = styled.a`
    color: var(--text-primary);
    text-decoration: none;
    font-size: 13px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 4px;
    
    &:hover {
        color: var(--primary-color);
    }
`;

const RemoveButton = styled(Button)`
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: none;
    background: var(--bg-tertiary);
    color: var(--text-muted);
    transition: var(--transition-fast);
    
    &:hover {
        background: #ff4d4f;
        color: white;
    }
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
                    <AttachmentIcon />
                    <AttachmentLink
                        href={att.url}
                        download={att.name}
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        {att.name}
                        <DownloadOutlined style={{ fontSize: 12 }} />
                    </AttachmentLink>
                    {isPreview && onRemove && (
                        <RemoveButton
                            size="small"
                            type="text"
                            icon={<CloseOutlined style={{ fontSize: 12 }} />}
                            onClick={() => onRemove(att.id)}
                        />
                    )}
                </AttachmentItem>
            ))}
        </AttachmentPreviewWrapper>
    );
};

export default AttachmentPreview; 