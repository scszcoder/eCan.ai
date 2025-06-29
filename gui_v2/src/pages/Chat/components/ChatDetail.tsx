import React, { useMemo, useEffect } from 'react';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat as SemiChat } from '@douyinfe/semi-ui';
import { defaultRoleConfig } from '../types/chat';
import { Message, Content, Chat } from '../types/chat';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';
import { FileUtils } from '../utils/fileUtils';
import { Toast } from '@douyinfe/semi-ui';

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
    // 创建一个新的消息对象，保留原始消息的所有属性
    const processedMessage = { ...message };

    // 确保消息有唯一的 id
    if (!processedMessage.id) {
        processedMessage.id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    // 如果有附件，将消息内容转换为 Semi UI Chat 的 Content 数组格式
    if (message.attachments && message.attachments.length > 0) {
        // 暂时转换为字符串格式，避免 Semi UI Chat 内部处理数组时的 key 冲突
        let contentStr = '';
        
        // 添加文本内容（如果有）
        if (typeof message.content === 'string' && message.content.trim()) {
            contentStr = message.content;
        } else if (Array.isArray(message.content)) {
            // 处理 Content[] 数组
            contentStr = message.content
                .filter(item => item.type === 'text' && item.text)
                .map(item => item.text)
                .join(' ');
        }
        
        // 添加附件信息到字符串中
        const attachmentInfo = message.attachments.map(attachment => {
            const mimeType = attachment.mimeType || attachment.type || '';
            const isImage = attachment.isImage || FileUtils.isImageFile(mimeType);
            const rawFilePath = attachment.filePath || attachment.url || '';
            
            if (isImage) {
                return `[图片: ${attachment.name}]`;
            } else {
                return `[文件: ${attachment.name}]`;
            }
        }).join(' ');
        
        processedMessage.content = contentStr + (contentStr ? ' ' : '') + attachmentInfo;
    } else {
        // 没有附件时，保持原有的字符串格式
        if (typeof message.content !== 'string') {
            if (Array.isArray(message.content)) {
                // 处理 Content[] 数组
                const contentStr = message.content
                    .filter(item => item.type === 'text' && item.text)
                    .map(item => item.text)
                    .join(' ');
                processedMessage.content = contentStr;
            }
        }
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
                    
                    // 直接使用返回的 URL，不添加协议前缀
                    const filePath = data.url || '';
                    
                    // 只传递可序列化的 attachment 字段，避免 circular JSON
                    const safeAttachment = {
                        name: data.name,
                        type: data.type,
                        size: data.size,
                        url: filePath, // 直接使用返回的 URL
                        filePath: filePath, // 保存文件路径
                        mimeType: data.type,
                        isImage: FileUtils.isImageFile(data.type),
                        status: 'complete',
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
            console.log('[ChatDetail] currentChat.messages:', currentChat.messages);
            // 改进的去重处理，确保没有重复的消息
            const uniqueMessages = currentChat.messages.reduce((acc: Message[], message) => {
                // 检查是否已存在相同的消息
                const exists = acc.find(m => {
                    // 1. 检查 ID 是否相同
                    if (m.id === message.id) return true;
                    
                    // 2. 检查是否是同一时间发送的相同内容（时间窗口：5秒内）
                    const timeDiff = Math.abs((m.createAt || 0) - (message.createAt || 0));
                    const isSameTime = timeDiff < 5000; // 5秒内
                    const isSameContent = JSON.stringify(m.content) === JSON.stringify(message.content);
                    const isSameSender = m.senderId === message.senderId;
                    
                    if (isSameTime && isSameContent && isSameSender) return true;
                    
                    // 3. 检查是否是乐观更新的消息（通过 ID 前缀判断）
                    if (m.id.startsWith('user_msg_') && message.id.startsWith('user_msg_')) {
                        const mTime = parseInt(m.id.split('_')[2]) || 0;
                        const msgTime = parseInt(message.id.split('_')[2]) || 0;
                        const timeDiff = Math.abs(mTime - msgTime);
                        if (timeDiff < 1000 && isSameContent && isSameSender) return true;
                    }
                    
                    return false;
                });
                
                if (!exists) {
                    acc.push(message);
                }
                return acc;
            }, []);
            
            return uniqueMessages.map(processMessageContent);
        }
        // 否则返回空数组
        return [];
    }, [currentChat]);

    // 聊天标题
    const chatTitle = currentChat ? currentChat.name : t('pages.chat.defaultTitle');

    // 为 Semi UI Chat 生成稳定的 key
    const chatKey = useMemo(() => {
        return `chat_${chatId}_${messages.length}`;
    }, [chatId, messages.length]);

    return (
        <ChatDetailWrapper>
            <SemiChat
                key={chatKey}
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