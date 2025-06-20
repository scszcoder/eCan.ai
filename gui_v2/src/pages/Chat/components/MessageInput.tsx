import React, { useState, useRef, useEffect } from 'react';
import { Button, Input } from 'antd';
import {
    SendOutlined,
    SmileOutlined,
    PaperClipOutlined,
    AudioOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useAttachmentHandler } from '../hooks/useAttachmentHandler';
import AttachmentPreview from './AttachmentPreview';
import { Attachment } from '../types/chat';
import 'emoji-picker-element';

const { TextArea } = Input;

// 让 TypeScript 识别 <emoji-picker> 自定义元素
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'emoji-picker': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
    }
  }
}

const MessageInputContainer = styled.div`
    position: relative;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
    padding: 24px 0 24px 0;
    display: flex;
    justify-content: center;
`;

const MessagePanel = styled.div`
    background: var(--bg-tertiary);
    border-radius: 20px;
    box-shadow: var(--shadow-md);
    padding: 16px 20px 12px 20px;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0;
`;

const InputAndToolbarWrapper = styled.div`
    display: flex;
    flex-direction: column;
    background: var(--bg-tertiary);
    border-radius: 16px;
    position: relative;
    width: 100%;
    box-sizing: border-box;
`;

const InputAreaWrapper = styled.div`
    background: transparent;
    border: none;
    border-radius: 16px 16px 0 0;
    padding: 0;
    transition: var(--transition-fast);
    display: flex;
    flex-direction: column;
    gap: 0;
    width: 100%;
`;

const StyledTextArea = styled(TextArea)`
    border: none !important;
    background: transparent;
    font-size: 15px;
    line-height: 1.6;
    color: var(--text-primary);
    padding: 10px 56px 10px 0;
    width: 100%;
    box-sizing: border-box;
    border-radius: 16px;
    transition: background var(--transition-fast);
    &::placeholder {
        color: var(--text-muted);
    }
    &:focus {
        box-shadow: none !important;
        border: none !important;
        background: rgba(255,255,255,0.02);
    }
    &:hover {
        box-shadow: none !important;
        border: none !important;
        background: rgba(255,255,255,0.02);
    }
    /* 只设置最大高度，不设置 min-height 和 height，避免干扰 autosize */
    &&.ant-input, &&.ant-input:focus, &&.ant-input:hover {
        max-height: 176px;
        resize: none;
    }
`;

const ToolbarContainer = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: none;
    margin: 0;
    padding: 0 0 4px 0;
    width: 100%;
    min-height: 36px;
`;

const ToolbarLeft = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
`;

const ToolbarRight = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
`;

const ActionButton = styled(Button)`
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: var(--text-secondary) !important;
    transition: background 0.18s, color 0.18s;
    box-shadow: none !important;
    padding: 0;
    svg {
        font-size: 18px;
        color: var(--text-secondary) !important;
        transition: color 0.18s;
    }
    &:hover {
        background: rgba(255,255,255,0.01);
        color: var(--text-primary) !important;
        border: none !important;
        box-shadow: none !important;
    }
    &:hover svg {
        color: var(--text-primary) !important;
    }
    &:focus {
        border: none !important;
        box-shadow: none !important;
    }
    &.recording {
        background: #ff4d4f;
        color: white !important;
        &:hover {
            background: #ff7875;
        }
        svg {
            color: white !important;
        }
    }
`;

const SendButton = styled(Button)`
    position: absolute;
    right: 12px;
    bottom: 12px;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primary-color), var(--accent-color));
    border: none;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(59,130,246,0.10);
    font-size: 20px;
    z-index: 2;
    transition: var(--transition-fast);
    box-shadow: none !important;
    &:hover {
        filter: brightness(1.08);
        transform: scale(1.07);
        border: none !important;
        box-shadow: none !important;
    }
    &:focus {
        border: none !important;
        box-shadow: none !important;
    }
    &:disabled {
        background: var(--bg-tertiary);
        color: var(--text-muted);
        filter: none;
        transform: none;
        border: none !important;
        box-shadow: none !important;
    }
`;

const EmojiPickerContainer = styled.div`
    position: absolute;
    bottom: 60px;
    left: 40px;
    z-index: 1000;
    border-radius: 12px;
    box-shadow: var(--shadow-lg);
    overflow: hidden;
`;

const AttachmentContainer = styled.div`
    margin-bottom: 12px;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: 12px;
    border: 1px solid var(--border-color);
`;

interface MessageInputProps {
    onSend: (content: string, attachments: Attachment[]) => void;
    disabled?: boolean;
}

const EmojiPickerElement: React.FC<{ onEmojiSelect: (emoji: string) => void; style?: React.CSSProperties }> = ({ onEmojiSelect, style }) => {
    const pickerRef = useRef<any>(null);
    useEffect(() => {
        const picker = pickerRef.current;
        if (!picker) return;
        const handler = (event: any) => {
            onEmojiSelect(event.detail.unicode);
        };
        picker.addEventListener('emoji-click', handler);
        return () => picker.removeEventListener('emoji-click', handler);
    }, [onEmojiSelect]);
    return (
        <emoji-picker
            ref={pickerRef}
            images-path="/emoji/png/"
            style={style}
        ></emoji-picker>
    );
};

const MessageInput: React.FC<MessageInputProps> = ({ onSend, disabled }) => {
    const { t } = useTranslation();
    const [message, setMessage] = useState('');
    const [showEmojiPicker, setShowEmojiPicker] = useState(false);
    const textAreaRef = useRef<any>(null);

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

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <MessageInputContainer>
          <MessagePanel>
            {attachments.length > 0 && (
                <AttachmentContainer>
                    <AttachmentPreview
                        attachments={attachments}
                        onRemove={removeAttachment}
                        isPreview
                    />
                </AttachmentContainer>
            )}
            <InputAndToolbarWrapper>
                <InputAreaWrapper>
                    <StyledTextArea
                        ref={textAreaRef}
                        value={message}
                        onChange={e => setMessage(e.target.value)}
                        placeholder={t('pages.chat.typeMessage')}
                        autoSize={{ minRows: 2, maxRows: 8 }}
                        onKeyPress={handleKeyPress}
                    />
                    <SendButton
                        icon={<SendOutlined style={{fontSize: 22, marginLeft: 2, marginTop: 2}} />}
                        onClick={handleSend}
                        disabled={disabled || (!message.trim() && attachments.length === 0)}
                    />
                </InputAreaWrapper>
                <ToolbarContainer>
                    <ToolbarLeft>
                        <ActionButton
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
                        <ActionButton
                            icon={<PaperClipOutlined />}
                            onClick={() => fileInputRef.current?.click()}
                        />
                        <ActionButton
                            icon={<AudioOutlined />}
                            onMouseDown={startRecording}
                            onMouseUp={stopRecording}
                            onMouseLeave={stopRecording}
                            className={isRecording ? 'recording' : ''}
                        />
                        {/* 这里可以加语言切换等按钮 */}
                    </ToolbarLeft>
                    <ToolbarRight />
                </ToolbarContainer>
                {showEmojiPicker && (
                    <EmojiPickerContainer>
                        <EmojiPickerElement
                            onEmojiSelect={(emoji) => {
                                setMessage(prev => prev + emoji);
                                setShowEmojiPicker(false);
                            }}
                        />
                    </EmojiPickerContainer>
                )}
            </InputAndToolbarWrapper>
          </MessagePanel>
        </MessageInputContainer>
    );
};

export default MessageInput; 