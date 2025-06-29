import React, { useMemo, useEffect, useState } from 'react';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat as SemiChat } from '@douyinfe/semi-ui';
import { defaultRoleConfig } from '../types/chat';
import { Message, Content, Chat } from '../types/chat';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';
import { FileUtils } from '../utils/fileUtils';
import { protocolHandler } from '../utils/protocolHandler';

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

    /* 自定义附件样式 */
    .custom-attachment {
        display: inline-block;
        margin: 4px 8px 4px 0;
        padding: 8px 12px;
        background-color: var(--semi-color-fill-0);
        border-radius: 8px;
        border: 1px solid var(--semi-color-border);
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .custom-attachment:hover {
        background-color: var(--semi-color-fill-1);
        border-color: var(--semi-color-primary);
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .custom-attachment-image {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--semi-color-link);
    }

    .custom-attachment-file {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--semi-color-text-1);
    }

    .custom-attachment-file:hover {
        background-color: var(--semi-color-primary);
        color: white;
    }

    .custom-attachment-file:hover .attachment-icon {
        color: white !important;
    }

    .custom-attachment-file:hover .attachment-name {
        color: white !important;
    }

    .attachment-icon {
        font-size: 16px;
    }

    .attachment-name {
        font-size: 14px;
        word-break: break-all;
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

// 处理消息内容，简化为字符串类型
const processMessageContent = (message: Message): any => {
    // 创建一个新的消息对象，保留原始消息的所有属性
    const processedMessage = { ...message };

    // 确保消息有唯一的 id
    if (!processedMessage.id) {
        processedMessage.id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    // 构建文本内容
    let textContent = '';
    
    // 处理原始文本内容
    if (typeof message.content === 'string' && message.content.trim()) {
        textContent = message.content;
    } else if (Array.isArray(message.content)) {
        // 如果已经是数组，提取文本内容
        const textItems = message.content
            .filter(item => item.type === 'text' && item.text)
            .map(item => item.text);
        textContent = textItems.join('\n');
    }

    // 处理附件，将附件信息添加到文本内容中
    if (message.attachments && message.attachments.length > 0) {
        const attachmentTexts = message.attachments.map((attachment, index) => {
            const mimeType = attachment.mimeType || attachment.type || 'application/octet-stream';
            const isImage = attachment.isImage || FileUtils.isImageFile(mimeType);
            const rawFilePath = attachment.filePath || attachment.url || '';
            const fileName = attachment.name || `file_${index}`;
            
            // 检查文件路径是否有效
            if (!rawFilePath || rawFilePath.trim() === '') {
                return null; // 跳过无效的附件
            }
            
            // 使用 pyqtfile:// 协议生成文件路径
            const filePath = rawFilePath.startsWith('pyqtfile://') 
                ? rawFilePath 
                : `pyqtfile://${rawFilePath}`;
            
            const attachmentText = isImage 
                ? `[image|${filePath}|${fileName}|${mimeType}]`
                : `[file|${filePath}|${fileName}|${mimeType}]`;
            
            return attachmentText;
        }).filter(Boolean); // 过滤掉 null 值
        
        if (attachmentTexts.length > 0) {
            if (textContent) {
                textContent += '\n' + attachmentTexts.join('\n');
            } else {
                textContent = attachmentTexts.join('\n');
            }
        }
    }

    // 将处理后的文本内容赋值给消息
    processedMessage.content = textContent;

    return processedMessage;
};

// 自定义内容渲染组件
const CustomContentRenderer: React.FC<{ content: string }> = ({ content }) => {
    const { t } = useTranslation();
    
    // 使用系统原生文件保存对话框下载文件
    const downloadFileWithNativeDialog = async (filePath: string, fileName: string, mimeType: string) => {
        try {
            // 获取文件内容
            const actualPath = filePath.replace('pyqtfile://', '');
            const fileContent = await FileUtils.getFileContent(actualPath);
            
            if (!fileContent || !fileContent.dataUrl) {
                throw new Error(t('pages.chat.failedToGetFileContent'));
            }

            // 从 data URL 创建 Blob
            const base64Data = fileContent.dataUrl.split(',')[1];
            const binaryData = atob(base64Data);
            const bytes = new Uint8Array(binaryData.length);
            for (let i = 0; i < binaryData.length; i++) {
                bytes[i] = binaryData.charCodeAt(i);
            }
            
            const blob = new Blob([bytes], { type: mimeType });

            // 尝试使用 File System Access API（现代浏览器）
            if ('showSaveFilePicker' in window) {
                try {
                    const handle = await (window as any).showSaveFilePicker({
                        suggestedName: fileName,
                        types: [{
                            description: 'File',
                            accept: { [mimeType]: [`.${fileName.split('.').pop()}`] }
                        }]
                    });
                    
                    const writable = await handle.createWritable();
                    await writable.write(blob);
                    await writable.close();
                    return;
                } catch (e: any) {
                    if (e.name === 'AbortError') {
                        console.log(t('pages.chat.userCancelledSave'));
                        return;
                    }
                    throw e;
                }
            }

            // 回退到传统的下载方法
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            
            // 清理
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);

        } catch (error) {
            console.error(t('pages.chat.nativeDownloadFailed'), error);
            throw error;
        }
    };

    const handleAttachmentClick = async (filePath: string, fileName: string, mimeType: string, isImage: boolean) => {
        if (isImage) {
            // 图片点击时预览
            protocolHandler.handleFile(filePath, fileName, mimeType);
        } else {
            // 文件点击时下载，使用系统原生保存对话框
            try {
                await downloadFileWithNativeDialog(filePath, fileName, mimeType);
            } catch (error) {
                console.error(t('pages.chat.failedToDownloadFile'), error);
                // 回退到原来的方法
                protocolHandler.handleFile(filePath, fileName, mimeType);
            }
        }
    };

    // 解析内容中的附件标记
    const renderContent = () => {
        if (!content) return null;

        const parts = [];
        let currentIndex = 0;
        
        // 使用简单的字符串分割方法来解析附件标记
        // 格式: [类型|文件路径|文件名|MIME类型]
        const attachmentRegex = /\[(image|file)\|([^|]+)\|([^|]+)\|([^\]]+)\]/g;
        let match;
        
        while ((match = attachmentRegex.exec(content)) !== null) {
            const [fullMatch, type, filePath, fileName, mimeType] = match;
            const isImage = type === 'image';
            
            // 添加附件前的文本
            if (match.index > currentIndex) {
                const textBefore = content.slice(currentIndex, match.index);
                if (textBefore.trim()) {
                    parts.push(
                        <span key={`text-${currentIndex}`} style={{ whiteSpace: 'pre-wrap' }}>
                            {textBefore}
                        </span>
                    );
                }
            }
            
            // 添加附件组件
            if (isImage) {
                // 图片显示预览图
                parts.push(
                    <div
                        key={`attachment-${match.index}`}
                        className="custom-attachment custom-attachment-image"
                    >
                        <div style={{ 
                            display: 'flex', 
                            flexDirection: 'column', 
                            alignItems: 'center',
                            gap: '8px'
                        }}>
                            <ImagePreview 
                                filePath={filePath}
                                fileName={fileName}
                                mimeType={mimeType}
                            />
                            <span className="attachment-name" style={{ fontSize: '12px', textAlign: 'center' }}>
                                {fileName}
                            </span>
                        </div>
                    </div>
                );
            } else {
                // 文件显示下载图标
                parts.push(
                    <div
                        key={`attachment-${match.index}`}
                        className="custom-attachment custom-attachment-file"
                        onClick={() => handleAttachmentClick(filePath, fileName, mimeType, false)}
                        title={`${fileName} (${mimeType})`}
                    >
                        <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: '8px',
                            padding: '6px 10px',
                            backgroundColor: 'var(--semi-color-fill-0)',
                            borderRadius: '6px',
                            border: '1px solid var(--semi-color-border)',
                            cursor: 'pointer',
                            transition: 'all 0.2s ease'
                        }}>
                            <span className="attachment-icon" style={{ 
                                fontSize: '16px',
                                color: 'var(--semi-color-primary)'
                            }}>
                                ⬇️
                            </span>
                            <span className="attachment-name" style={{ 
                                fontSize: '13px',
                                color: 'var(--semi-color-text-1)',
                                maxWidth: '120px',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                            }}>
                                {fileName}
                            </span>
                        </div>
                    </div>
                );
            }
            
            currentIndex = match.index + fullMatch.length;
        }
        
        // 添加剩余的文本
        if (currentIndex < content.length) {
            const remainingText = content.slice(currentIndex);
            if (remainingText.trim()) {
                parts.push(
                    <span key={`text-${currentIndex}`} style={{ whiteSpace: 'pre-wrap' }}>
                        {remainingText}
                    </span>
                );
            }
        }
        
        return parts.length > 0 ? parts : <span>{content}</span>;
    };

    return (
        <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '8px',
            wordBreak: 'break-word',
            whiteSpace: 'pre-wrap'
        }}>
            {renderContent()}
        </div>
    );
};

// 图片预览组件
const ImagePreview: React.FC<{ filePath: string; fileName: string; mimeType: string }> = ({ 
    filePath, 
    fileName, 
    mimeType 
}) => {
    const { t } = useTranslation();
    const [imageUrl, setImageUrl] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);
    const [hasError, setHasError] = useState(false);

    useEffect(() => {
        const loadImage = async () => {
            if (!filePath.startsWith('pyqtfile://')) {
                setImageUrl(filePath);
                setIsLoading(false);
                return;
            }

            try {
                setIsLoading(true);
                setHasError(false);
                
                // 使用 FileUtils 获取图片的 data URL
                const actualPath = filePath.replace('pyqtfile://', '');
                const dataUrl = await FileUtils.getFileThumbnail(actualPath);
                
                if (dataUrl) {
                    setImageUrl(dataUrl);
                } else {
                    setHasError(true);
                }
            } catch (error) {
                console.error('[ImagePreview] Failed to load pyqtfile image:', error);
                setHasError(true);
            } finally {
                setIsLoading(false);
            }
        };

        loadImage();
    }, [filePath]);

    const handleClick = () => {
        // 直接使用完整的文件路径（包含协议）
        protocolHandler.handleFile(filePath, fileName, mimeType);
    };

    if (isLoading) {
        return (
            <div style={{
                width: '120px',
                height: '80px',
                backgroundColor: 'var(--semi-color-fill-0)',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--semi-color-border)',
                fontSize: '12px',
                color: 'var(--semi-color-text-2)'
            }}>
                {t('pages.chat.loading')}
            </div>
        );
    }

    if (hasError) {
        return (
            <div 
                style={{
                    width: '120px',
                    height: '80px',
                    backgroundColor: 'var(--semi-color-fill-0)',
                    borderRadius: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: '1px solid var(--semi-color-border)',
                    cursor: 'pointer',
                    fontSize: '12px',
                    color: 'var(--semi-color-text-2)'
                }}
                onClick={handleClick}
            >
                {t('pages.chat.clickToView')}
            </div>
        );
    }

    return (
        <div 
            style={{
                width: '120px',
                height: '80px',
                borderRadius: '8px',
                border: '1px solid var(--semi-color-border)',
                overflow: 'hidden',
                cursor: 'pointer',
                backgroundColor: 'var(--semi-color-fill-0)'
            }}
            onClick={handleClick}
        >
            <img 
                src={imageUrl} 
                alt={fileName}
                style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover'
                }}
            />
        </div>
    );
};

interface ChatDetailProps {
    chatId?: string | null;
    chats?: Chat[];
    onSend?: (content: string, attachments: any[]) => void;
}

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId, chats = [], onSend }) => {
    const { t } = useTranslation();

    // 初始化协议处理器
    useEffect(() => {
        protocolHandler.init();
    }, []);

    // 根据 chatId 获取对应的聊天数据
    const currentChat = useMemo(() => {
        if (!chatId || !chats.length) return null;
        return chats.find(chat => chat.id === chatId);
    }, [chatId, chats]);

    // 处理消息，确保content是字符串
    const messages = useMemo(() => {
        // 如果有当前聊天，使用其消息
        if (currentChat && Array.isArray(currentChat.messages)) {
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
            
            // 按时间排序，确保消息顺序稳定
            uniqueMessages.sort((a, b) => (a.createAt || 0) - (b.createAt || 0));
            
            const processedMessages = uniqueMessages.map((message, index) => {
                const processed = processMessageContent(message);
                // 确保每个消息都有唯一的 key，使用消息 ID 而不是索引
                processed.key = `msg_${processed.id}`;
                return processed;
            });
            
            return processedMessages;
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

    // 自定义渲染配置
    const chatBoxRenderConfig = {
        renderChatBoxContent: (props: any) => {
            // Semi UI Chat 的 renderChatBoxContent 接收 RenderContentProps 类型
            const { message, role, defaultContent, className } = props;
            // 从 message 中获取 content
            const content = message?.content || '';
            
            return <CustomContentRenderer content={content} />;
        }
    };

    // 上传组件的配置 - 移到组件内部以使用 hook
    const uploadProps = {
        action: '', // 禁用 HTTP 上传
        beforeUpload: () => true, // 必须返回 true，允许 customRequest 执行
        customRequest: async (options: any) => {
            const { file, onSuccess, onError } = options;
            try {
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
                    onError(new Error(t('pages.chat.failedToGetFileContent')), file);
                    return;
                }
                
                // 优先从 realFile 获取 type、name、size
                const fileType = realFile.type || file.type || '';
                const fileName = realFile.name || file.name || '';
                const fileSize = realFile.size || file.size || 0;
                
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const fileData = e.target?.result;
                    if (!fileData) {
                        console.error('[uploadProps] FileReader failed');
                        onError(new Error(t('pages.chat.failedToGetFileContent')), file);
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
                            name: data.name || file.name || 'unknown',
                            type: data.type || file.type || 'application/octet-stream',
                            size: data.size || file.size || 0,
                            url: filePath, // 直接使用返回的 URL
                            filePath: filePath, // 保存文件路径
                            mimeType: data.type || file.type || 'application/octet-stream',
                            isImage: FileUtils.isImageFile(data.type || file.type || ''),
                            status: 'complete',
                            uid: data.uid || file.uid || ('' + Date.now())
                        };
                        
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
                
                reader.readAsDataURL(realFile);
            } catch (err) {
                console.error('[uploadProps] customRequest catch', err);
                onError(err, file);
            }
        },
        // 其他配置可按需添加
    };

    return (
        <ChatDetailWrapper>
            {/* <ChatWrapper> */}
                <SemiChat
                    key={chatKey}
                    chats={messages}
                    style={{ ...commonOuterStyle }}
                    align="leftRight"
                    mode="bubble"
                    placeholder={t('pages.chat.typeMessage')}
                    onMessageSend={onSend}
                    roleConfig={defaultRoleConfig}
                    uploadProps={uploadProps}
                    title={chatTitle}
                    showAvatar={true}
                    showTime={true}
                    showStatus={true}
                    maxLength={5000}
                    chatBoxRenderConfig={chatBoxRenderConfig}
                />
            {/* </ChatWrapper> */}
        </ChatDetailWrapper>
    );
};


export default ChatDetail; 