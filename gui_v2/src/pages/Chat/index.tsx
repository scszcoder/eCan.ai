import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useChatStore } from './hooks/useChatStore';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { useUserStore } from '../../stores/userStore';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    
    const {
        chats,
        activeChatId,
        setActiveChat,
        addChat,
        sendMessage,
        initialize
    } = useChatStore();

    // 初始化聊天
    useEffect(() => {
        initialize();
    }, [initialize]);

    // 处理 agentId 参数
    useEffect(() => {
        if (agentId) {
            const existingChat = chats.find(chat => chat.agentId === agentId);
            if (!existingChat) {
                addChat({
                    id: Date.now(),
                    name: `Agent ${agentId}`,
                    type: 'bot',
                    status: 'online',
                    agentId,
                    lastMessage: t('pages.chat.startConversation'),
                    lastMessageTime: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    unreadCount: 0,
                    messages: []
                });
            }
            setActiveChat(existingChat?.id || Date.now());
        }
    }, [agentId, chats, addChat, setActiveChat, t]);

    const handleFilterChange = (filters: Record<string, any>) => {
        // 处理过滤器变化
        console.log('Filter changed:', filters);
    };

    const handleChatSelect = (chatId: number) => {
        setActiveChat(chatId);
    };

    const handleChatDelete = (chatId: number) => {
        // 处理聊天删除
        console.log('Delete chat:', chatId);
    };

    const handleChatPin = (chatId: number) => {
        // 处理聊天置顶
        console.log('Pin chat:', chatId);
    };

    const handleChatMute = (chatId: number) => {
        // 处理聊天静音
        console.log('Mute chat:', chatId);
    };

    const handleMessageSend = (content: string, attachments: any[]) => {
        if (!activeChatId) return;
        sendMessage(activeChatId, content, attachments);
    };

    const renderListContent = () => (
        <ChatList
            chats={chats}
            activeChatId={activeChatId}
            onChatSelect={handleChatSelect}
            onChatDelete={handleChatDelete}
            onChatPin={handleChatPin}
            onChatMute={handleChatMute}
            onFilterChange={handleFilterChange}
        />
    );

    const renderDetailsContent = () => (
        <ChatDetail chatId={activeChatId} />
    );

    return (
        <DetailLayout
            listTitle={t('pages.chat.title')}
            detailsTitle={t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default ChatPage; 