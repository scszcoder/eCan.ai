import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useAppDataStore } from '../../stores/appDataStore';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { useUserStore } from '../../stores/userStore';
import { Chat, Message } from './types/chat';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    const [activeChatId, setActiveChatId] = useState<number | null>(null);
    const username = useUserStore((state) => state.username)

    const {
        chats,
        setChats,
        setLoading,
        setError,
    } = useAppDataStore();

    // 初始化聊天
    useEffect(() => {
        const fetchChats = async () => {
            if (!username) {
                logger.warn('[ChatPage] Username not found, skipping fetchChats.');
                return;
            }
            
            logger.info(`[ChatPage] Username exists, fetching chats for "${username}".`);
            setLoading(true);
            try {
                const response = await get_ipc_api().getChats<Chat[]>(username, []);
                if (response.success && response.data) {
                    console.log('[ChatPage] Fetched chats:', response.data);
                    const chatsData = response.data.chats as Chat[];
                    setChats(chatsData);
                    if (chatsData.length > 0 && !activeChatId) {
                        setActiveChatId(chatsData[0].id);
                    }
                } else {
                    setError(response.error?.message || 'Failed to fetch chats');
                    logger.error('[ChatPage] Error fetching chats:', response.error);
                }
            } catch (error) {
                const errorMessage = error instanceof Error ? error.message : String(error);
                setError(errorMessage);
            } finally {
                setLoading(false);
            }
        };

        fetchChats();
    }, [username, setChats, setLoading, setError, activeChatId]);

    // 处理 agentId 参数
    useEffect(() => {
        if (agentId) {
            const existingChat = chats.find(chat => chat.agentId === agentId);
            if (!existingChat) {
                const newChatId = Date.now();
                const newChat: Chat = {
                    id: newChatId,
                    name: `Agent ${agentId}`,
                    type: 'bot',
                    status: 'online',
                    agentId,
                    lastMessage: t('pages.chat.startConversation'),
                    lastMessageTime: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    unreadCount: 0,
                    messages: []
                };
                setChats([...chats, newChat]);
                setActiveChatId(newChatId);
            } else {
                if (activeChatId !== existingChat.id) {
                    setActiveChatId(existingChat.id);
                }
            }
        }
    }, [agentId, chats, setChats, t, activeChatId]);

    const handleFilterChange = (filters: Record<string, any>) => {
        // 处理过滤器变化
        logger.debug('Filter changed:', filters);
    };

    const handleChatSelect = (chatId: number) => {
        const newChats = chats.map(chat =>
            chat.id === chatId ? { ...chat, unreadCount: 0 } : chat
        );
        setChats(newChats);
        setActiveChatId(chatId);
    };

    const handleChatDelete = (chatId: number) => {
        // 处理聊天删除
        logger.debug('Delete chat:', chatId);
    };

    const handleChatPin = (chatId: number) => {
        // 处理聊天置顶
        logger.debug('Pin chat:', chatId);
    };

    const handleChatMute = (chatId: number) => {
        // 处理聊天静音
        logger.debug('Mute chat:', chatId);
    };

    const handleMessageSend = async (content: string, attachments: any[]) => {
        if (!activeChatId) return;

        const chat = chats.find(c => c.id === activeChatId);
        if (!chat) return;
        
        const tempId = Date.now();
        let receiver = '';
        if (chat.type === 'user') {
            receiver = chat.name;
        } else if (chat.type === 'bot') {
            receiver = chat.agentId || '';
        }

        const newMessage: Message = {
            id: tempId,
            chatId: activeChatId,
            content,
            attachments,
            sender_id: 'user', // This should be the current user's ID
            sender_name: 'You', // This should be the current user's name
            recipient_id: receiver,
            recipient_name: chat.name,
            txTimestamp: new Date().toISOString(),
            status: 'sending',
            rxTimestamp: '',
            readTimestamp: '',
        };

        const updatedChats = chats.map(c => {
            if (c.id !== activeChatId) return c;
            return {
                ...c,
                messages: [...(c.messages || []), newMessage],
                lastMessage: content,
                lastMessageTime: new Date().toISOString(),
            };
        });
        setChats(updatedChats);

        try {
            const response = await get_ipc_api().sendChat(newMessage);
            const finalStatus: Message['status'] = response?.success ? 'sent' : 'failed';
            
            // We need to get the latest chats state, because another message could have arrived.
            // However, for this simple case, we'll base the update on `updatedChats`.
            const finalChats = updatedChats.map((c: Chat) => {
                if (c.id !== activeChatId) return c;
                return {
                    ...c,
                    messages: c.messages.map((m: Message) => m.id === tempId ? { ...m, status: finalStatus } : m) as Message[],
                };
            });
            setChats(finalChats);

        } catch (error) {
            logger.error('Failed to send message:', error);
            const finalChats = updatedChats.map((c: Chat) => {
                if (c.id !== activeChatId) return c;
                return {
                    ...c,
                    messages: c.messages.map((m: Message) => m.id === tempId ? { ...m, status: 'failed' } : m) as Message[],
                };
            });
            setChats(finalChats);
        }
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
        <ChatDetail chatId={activeChatId} onSend={handleMessageSend} />
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