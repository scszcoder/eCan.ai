import React, { useState } from 'react';
import { Button, Input, Space } from 'antd';
import {
    SendOutlined,
    SmileOutlined,
    PaperClipOutlined,
    AudioOutlined
} from '@ant-design/icons';
import EmojiPicker, { EmojiClickData } from 'emoji-picker-react';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useAttachmentHandler } from '../hooks/useAttachmentHandler';
import AttachmentPreview from './AttachmentPreview';
import { Attachment } from '../types/chat';

const { TextArea } = Input;

const MessageToolbar = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border-top: 1px solid var(--border-color);
    border-radius: 0 0 8px 8px;
`;

interface MessageInputProps {
    onSend: (content: string, attachments: Attachment[]) => void;
    disabled?: boolean;
}

const MessageInput: React.FC<MessageInputProps> = ({ onSend, disabled }) => {
    const { t } = useTranslation();
    const [message, setMessage] = useState('');
    const [showEmojiPicker, setShowEmojiPicker] = useState(false);
    
    const {
        attachments,
        isRecording,
        fileInputRef,
        handleFileChange,
        removeAttachment,
        startRecording,
        stopRecording
    } = useAttachmentHandler();

    const handleSend = () => {
        if (!message.trim() && attachments.length === 0) return;
        onSend(message, attachments);
        setMessage('');
    };

    const handleEmojiClick = (emojiData: EmojiClickData) => {
        setMessage(prev => prev + emojiData.emoji);
        setShowEmojiPicker(false);
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div>
            <MessageToolbar>
                <Button
                    icon={<SmileOutlined />}
                    onClick={() => setShowEmojiPicker(p => !p)}
                />
                <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    multiple
                    onChange={handleFileChange}
                />
                <Button
                    icon={<PaperClipOutlined />}
                    onClick={() => fileInputRef.current?.click()}
                />
                <Button
                    icon={<AudioOutlined />}
                    onMouseDown={startRecording}
                    onMouseUp={stopRecording}
                    onMouseLeave={stopRecording}
                    danger={isRecording}
                />
                <TextArea
                    value={message}
                    onChange={e => setMessage(e.target.value)}
                    placeholder={t('pages.chat.typeMessage')}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    onKeyPress={handleKeyPress}
                />
                <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    disabled={disabled || (!message.trim() && attachments.length === 0)}
                >
                    {t('pages.chat.send')}
                </Button>
            </MessageToolbar>

            {attachments.length > 0 && (
                <AttachmentPreview
                    attachments={attachments}
                    onRemove={removeAttachment}
                    isPreview
                />
            )}

            {showEmojiPicker && (
                <div style={{ position: 'absolute', bottom: 70, right: 20 }}>
                    <EmojiPicker onEmojiClick={handleEmojiClick} />
                </div>
            )}
        </div>
    );
};

export default MessageInput; 