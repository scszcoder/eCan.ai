import React, { useMemo } from 'react';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat as SemiChat } from '@douyinfe/semi-ui';
import { defaultRoleConfig } from '../types/chat';
import { Message, Content, Chat } from '../types/chat';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';

const ChatDetailWrapper = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    /* 保证撑满父容器 */

    /* Semi UI 深色主题变量覆盖 */
    --semi-color-bg-0: #0f172a;
    --semi-color-bg-1: #1e293b;
    --semi-color-border: #334155;
    --semi-color-text-0: #f8fafc;
    --semi-color-text-1: #cbd5e1;
    --semi-color-text-2: #cbd5e1; /* placeholder增强 */
    --semi-color-primary: #4e40e5;
    --semi-color-primary-hover: #a5b4fc;
    --semi-color-icon-hover: #a5b4fc;
    --semi-color-fill-0: #334155;
    --semi-color-disabled-text: #64748b;
    --semi-color-link: #8b5cf6;

    /* 强制SemiChat宽度100% */
    .semi-chat, .semi-chat-inner {
        max-width: 100% !important;
        width: 100% !important;
        min-width: 0 !important;
        height: 100% !important;
        min-height: 0 !important;
    }
`;

const EmptyState = styled.div`
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    font-size: 14px;
`;

const commonOuterStyle = {
    border: '1px solid var(--semi-color-border)',
    borderRadius: '16px',
    height: '100%',
    width: '100%',
    display: 'flex',
    flexDirection: 'column' as 'column',
    overflow: 'hidden'
};

// 处理消息内容，确保返回符合 Semi UI Chat 组件要求的消息对象
const processMessageContent = (message: Message): any => {
    if (!message.content) {
        return message;
    }

    // 创建一个新的消息对象，保留原始消息的所有属性
    const processedMessage = { ...message };

    // 如果content是对象，转换为字符串
    if (typeof message.content !== 'string') {
        const content = message.content as Content;
        let contentStr = '';

        switch (content.type) {
            case 'text':
                contentStr = content.text || '';
                break;
            case 'code':
                contentStr = content.code ? `\`\`\`${content.code.lang}\n${content.code.value}\n\`\`\`` : '';
                break;
            case 'image':
                contentStr = content.imageUrl ? `![image](${content.imageUrl})` : '';
                break;
            case 'file':
                contentStr = content.fileName || content.fileUrl || 'File';
                break;
            default:
                contentStr = JSON.stringify(content);
        }

        processedMessage.content = contentStr;
    }

    return processedMessage;
};

// 上传组件的配置
const uploadProps = {
    action: '', // 禁用 HTTP 上传
    beforeUpload: () => true, // 必须返回 true，允许 customRequest 执行
    customRequest: async (options: any) => {
        const { file, onSuccess, onError } = options;
        try {
            const reader = new FileReader();
            reader.onload = async (e) => {
                const fileData = e.target?.result;
                if (!fileData) {
                    console.error('[uploadProps] FileReader failed');
                    onError(new Error('读取文件失败'), file);
                    return;
                }
                const api = get_ipc_api();
                const resp = await api.chat.uploadAttachment({
                    name: fileName,
                    type: fileType,
                    size: fileSize,
                    data: fileData as string, // base64 字符串
                });
                logger.debug('[uploadProps] uploadAttachment resp:', resp);
                if (resp.success) {
                    logger.debug('[uploadProps] Attachment upload success, data:', resp.data);
                    const data: any = resp.data;
                    // 只传递可序列化的 attachment 字段，避免 circular JSON
                    const safeAttachment = {
                        name: data.name,
                        type: data.type,
                        size: data.size,
                        url: data.url || data.base64 || data.data || '',
                        status: 'done',
                        uid: data.uid || file.uid || ('' + Date.now())
                    };
                    console.log('[uploadProps] safeAttachment:', safeAttachment)
                    onSuccess(safeAttachment, file);
                } else {
                    logger.error('[uploadProps] Attachment upload error:', resp.error);
                    onError(resp.error, file);
                }
            };
            reader.onerror = (e) => {
                console.error('[uploadProps] FileReader onerror', e);
                onError(new Error('FileReader error'), file);
            };
            // 兼容更多 UI 上传组件的 file 结构，优先用 fileInstance
            let realFile = null;
            if (file.fileInstance instanceof Blob) {
                realFile = file.fileInstance;
            } else if (file.originFileObj instanceof Blob) {
                realFile = file.originFileObj;
            } else if (file instanceof Blob) {
                realFile = file;
            } else if (file.raw instanceof Blob) {
                realFile = file.raw;
            } else {
                for (const key in file) {
                    if (file[key] instanceof Blob) {
                        realFile = file[key];
                        break;
                    }
                }
            }
            if (!realFile) {
                console.error('[uploadProps] Not a Blob/File:', file);
                onError(new Error('文件类型错误，无法上传'), file);
                return;
            }
            // 优先从 realFile 获取 type、name、size
            const fileType = realFile.type || file.type || '';
            const fileName = realFile.name || file.name || '';
            const fileSize = realFile.size || file.size || 0;
            reader.readAsDataURL(realFile);
        } catch (err) {
            console.error('[uploadProps] customRequest catch', err);
            onError(err, file);
        }
    },
    // 其他配置可按需添加
};

interface ChatDetailProps {
    chatId?: string | null;
    chats?: Chat[];
    onSend?: (content: string, attachments: any[]) => void;
}

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId, chats = [], onSend }) => {
    const { t } = useTranslation();

    // 根据 chatId 获取对应的聊天数据
    const currentChat = useMemo(() => {
        if (!chatId || !chats.length) return null;
        return chats.find(chat => chat.id === chatId);
    }, [chatId, chats]);

    // 处理消息，确保content是字符串
    const messages = useMemo(() => {
        // 如果有当前聊天，使用其消息
        if (currentChat && Array.isArray(currentChat.messages)) {
            return currentChat.messages.map(processMessageContent);
        }
        // 否则返回空数组
        return [];
    }, [currentChat]);

    // 聊天标题
    const chatTitle = currentChat ? currentChat.name : t('pages.chat.defaultTitle');

    return (
        <ChatDetailWrapper>
            <SemiChat
                chats={messages}
                style={{ ...commonOuterStyle }}
                align="leftRight"
                mode="userBubble"
                placeholder={t('pages.chat.typeMessage')}
                onMessageSend={onSend}
                roleConfig={defaultRoleConfig}
                uploadProps={uploadProps}
                title={chatTitle}
            />
        </ChatDetailWrapper>
    );
};

export default ChatDetail; 