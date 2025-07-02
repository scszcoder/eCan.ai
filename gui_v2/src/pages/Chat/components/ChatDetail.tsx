import React, { useMemo, useEffect } from 'react';
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
    const messages = useMemo<SemiMessage[]>(() => {
        // 如果有当前聊天，使用其消息
        if (currentChat && Array.isArray(currentChat.messages)) {
            return processAndDeduplicateMessages(currentChat.messages);
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
            const { message } = props;
            // 从 message 中获取 content
            const content = message?.content || '';
            
            return <CustomContentRenderer content={content} />;
        }
    };

    // 上传组件的配置
    const uploadProps = getUploadProps();

    return (
        <ChatDetailWrapper>
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
        </ChatDetailWrapper>
    );
};

export default ChatDetail; 