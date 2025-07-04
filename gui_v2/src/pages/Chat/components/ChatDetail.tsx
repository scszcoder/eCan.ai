import React, { useMemo, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Chat as SemiChat } from '@douyinfe/semi-ui';
import { Message as SemiMessage } from '@douyinfe/semi-foundation/lib/es/chat/foundation';
import { defaultRoleConfig } from '../types/chat';
import { Chat } from '../types/chat';
import { protocolHandler } from '../utils/protocolHandler';
import { ChatDetailWrapper, commonOuterStyle } from '../styles/ChatDetail.styles';
import { processAndDeduplicateMessages } from '../utils/messageProcessor';
import { getUploadProps } from '../utils/attachmentHandler';
import CustomContentRenderer from './CustomContentRenderer';
import { logger } from '@/utils/logger';

interface ChatDetailProps {
    chatId?: string | null;
    chats?: Chat[];
    onSend?: (content: string, attachments: any[]) => void;
}

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId, chats = [], onSend }) => {
    const { t } = useTranslation();
    const wrapperRef = useRef<HTMLDivElement>(null);
    const chatRef = useRef<any>(null);
    const lastMessageLengthRef = useRef<number>(0);
    const justSentMessageRef = useRef<boolean>(false);

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
    const messages = useMemo<SemiMessage[]>(() => {
        // 如果有当前聊天，使用其消息
        if (currentChat && Array.isArray(currentChat.messages)) {
            return processAndDeduplicateMessages(currentChat.messages);
        }
        // 否则返回空数组
        return [];
    }, [currentChat]);

    // 聚焦输入框的函数
    const focusInputArea = () => {
        try {
            // 尝试多种选择器找到输入框
            let inputArea: HTMLTextAreaElement | null = null;
            
            // 尝试不同的选择器找到输入框
            inputArea = document.querySelector('.semi-chat-inputbox textarea') as HTMLTextAreaElement;
            if (!inputArea) {
                inputArea = document.querySelector('.semi-input-textarea') as HTMLTextAreaElement;
            }
            if (!inputArea) {
                inputArea = document.querySelector('textarea[placeholder]') as HTMLTextAreaElement;
            }
            
            if (inputArea) {
                inputArea.focus();
                
                // 尝试将光标移动到文本末尾
                if (typeof inputArea.selectionStart === 'number') {
                    try {
                        const length = inputArea.value.length;
                        inputArea.selectionStart = length;
                        inputArea.selectionEnd = length;
                    } catch (e) {
                        // 忽略错误
                    }
                }
            }
        } catch (error) {
            // 忽略错误
        }
    };

    // 检测消息列表变化，如果有新消息，尝试聚焦输入框
    useEffect(() => {
        if (messages.length > lastMessageLengthRef.current) {
            // 消息列表增加了，可能是发送了新消息
            setTimeout(focusInputArea, 100);
        }
        lastMessageLengthRef.current = messages.length;
    }, [messages.length]);

    // 自定义消息发送处理函数
    const handleMessageSend = (content: string, attachments: any[]) => {
        justSentMessageRef.current = true;
        
        if (onSend) {
            onSend(content, attachments);
        }
        
        // 立即尝试聚焦一次
        focusInputArea();
        
        // 使用多次尝试确保聚焦成功
        const attempts = [100, 200, 300, 500, 1000];
        attempts.forEach(delay => {
            setTimeout(() => {
                if (justSentMessageRef.current) {
                    focusInputArea();
                }
            }, delay);
        });
        
        // 最后一次尝试后重置标志
        setTimeout(() => {
            justSentMessageRef.current = false;
        }, Math.max(...attempts) + 100);
    };

    // 添加事件监听，防止输入框失去焦点
    useEffect(() => {
        // 找到输入框的容器
        const chatContainer = wrapperRef.current?.querySelector('.semi-chat-container');
        
        if (!chatContainer) return;
        
        // 创建事件处理函数
        const preventFocusLoss = (e: Event) => {
            // 如果刚刚发送了消息，确保输入框保持焦点
            if (justSentMessageRef.current) {
                setTimeout(focusInputArea, 0);
            }
        };
        
        // 添加事件监听
        chatContainer.addEventListener('click', preventFocusLoss, true);
        
        return () => {
            // 移除事件监听
            chatContainer.removeEventListener('click', preventFocusLoss, true);
        };
    }, []);

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
            const { message } = props;
            // 从 message 中获取 content
            const content = message?.content || '';
            
            return <CustomContentRenderer content={content} />;
        }
    };

    // 上传组件的配置
    const uploadProps = getUploadProps();

    // 在组件挂载和更新时尝试聚焦输入框
    useEffect(() => {
        // 延迟聚焦，确保组件已经完全渲染
        const timer = setTimeout(focusInputArea, 200);
        return () => clearTimeout(timer);
    }, [chatId]); // 当聊天ID变化时重新聚焦

    return (
        <ChatDetailWrapper ref={wrapperRef}>
            <SemiChat
                ref={chatRef}
                key={chatKey}
                chats={messages}
                style={{ ...commonOuterStyle }}
                align="leftRight"
                mode="bubble"
                placeholder={t('pages.chat.typeMessage')}
                onMessageSend={handleMessageSend}
                roleConfig={defaultRoleConfig}
                uploadProps={uploadProps}
                title={chatTitle}
                showAvatar={true}
                showTime={true}
                showStatus={true}
                maxLength={5000}
                chatBoxRenderConfig={chatBoxRenderConfig}
            />
        </ChatDetailWrapper>
    );
};

export default ChatDetail; 