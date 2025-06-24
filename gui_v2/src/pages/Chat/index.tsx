import React, { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '../../stores/appDataStore';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { useUserStore } from '../../stores/userStore';
import { Chat, Message } from './types/chat';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { APIResponse } from '@/services/ipc';
import ChatLayout from './components/ChatLayout';
import AgentNotify from './components/AgentNotify';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    const [activeChatId, setActiveChatId] = useState<number | null>(null);
    const username = useUserStore((state) => state.username)
    // 默认设置为有新消息，方便查看效果
    const [hasNewAgentNotifications, setHasNewAgentNotifications] = useState(true);

    const {
        chats,
        setChats,
        setLoading,
        setError,
    } = useAppDataStore();

    const fetchChats = useCallback(async (chat_ids: number[] = []) => {
        if (!username) {
            logger.warn('[ChatPage] Username not found, skipping fetchChats.');
            return;
        }
        
        logger.info(`[ChatPage] Username exists, fetching chats for "${username}" with chat_ids:`, chat_ids);
        setLoading(true);
        try {
            const response = await get_ipc_api().getChats<{chats: Chat[]}>(username, chat_ids.map(String));
            if (response.success && response.data) {
                console.log('[ChatPage] Fetched chats:', response.data.chats);
                const fetchedChats = response.data.chats as Chat[];
                if (chat_ids.length > 0) {
                    // Merge new chat data with existing chats
                    const updatedChats = chats.map(chat => {
                        const newChat = fetchedChats.find(c => c.id === chat.id);
                        return newChat ? { ...chat, ...newChat } : chat;
                    });
                    setChats(updatedChats);
                } else {
                    // Initial fetch, replace all chats
                    setChats(fetchedChats);
                    if (fetchedChats.length > 0 && !activeChatId) {
                        setActiveChatId(fetchedChats[0].id);
                    }
                }
            } else {
                setError(response.error?.message || 'Failed to fetch chats');
                logger.error('[ChatPage] Error fetching chats:', response.error);
            }
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            setError(errorMessage);
            console.error('[ChatPage] fetchChats error stack:', error instanceof Error ? error.stack : 'No stack trace available');
        } finally {
            setLoading(false);
        }
    }, [username, setLoading, setError, chats, activeChatId, setChats]);

    // 初始化聊天
    useEffect(() => {
        console.log('[ChatPage] username:', username);
        fetchChats();
    }, [username]);

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
        fetchChats([chatId]);
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
            chat_id: activeChatId,
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
            const response: APIResponse<void> = await get_ipc_api().sendChat(newMessage);
            if (response.success && response.data) {
                console.log('[ChatPage] Message sent successfully', response.data);
                const finalStatus: Message['status'] = 'sent';
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
                
                // 模拟收到 Agent 执行结果的通知
                setTimeout(() => {
                    setHasNewAgentNotifications(true);
                    
                    // 添加一条新的 Agent 通知
                    const now = new Date();
                    const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    const dateString = now.toLocaleDateString();
                    const newNotification = {
                        id: Date.now().toString(),
                        title: 'Agent 执行成功',
                        content: `已完成任务: ${content}`,
                        time: `${dateString} ${timeString}`
                    };
                    
                    setAgentNotifications(prev => [newNotification, ...prev]);
                }, 2000);
            } else {
                console.error('[ChatPage] Failed to send message:', response.error);
                const finalStatus: Message['status'] = 'failed';
                const finalChats = updatedChats.map((c: Chat) => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map((m: Message) => m.id === tempId ? { ...m, status: finalStatus } : m) as Message[],
                    };
                });
                setChats(finalChats);
            }
            

        } catch (error) {
            logger.error('Failed to send message:', error);
            console.error('[ChatPage] Error stack:', error instanceof Error ? error.stack : 'No stack trace available');
            const finalStatus: Message['status'] = 'failed';
            const finalChats = updatedChats.map((c: Chat) => {
                if (c.id !== activeChatId) return c;
                return {
                    ...c,
                    messages: c.messages.map((m: Message) => m.id === tempId ? { ...m, status: finalStatus } : m) as Message[],
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

    // agent notify 示例数据
    const [agentNotifications, setAgentNotifications] = useState([
        { 
            id: '1', 
            title: 'Agent 执行成功', 
            content: '已完成搜索任务，找到相关结果 3 条', 
            time: '2024-06-24 19:00' 
        },
        { 
            id: '2', 
            title: 'Agent 执行完成', 
            content: '已完成数据分析任务，生成报告已保存', 
            time: '2024-06-24 18:30' 
        }
    ]);
    
    // 当右侧面板展开时，清除未读状态
    const handleRightPanelToggle = (collapsed: boolean) => {
        if (!collapsed) {
            setHasNewAgentNotifications(false);
        }
    };

    // 获取当前聊天对象
    const currentChat = chats.find((c) => c.id === activeChatId);

    return (
        <ChatLayout
            listTitle={t('pages.chat.title')}
            detailsTitle={currentChat ? currentChat.name : t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
            agentNotifyTitle={t('pages.chat.agentNotify')}
            agentNotifyContent={<AgentNotify notifications={agentNotifications} />}
            hasNewAgentNotifications={hasNewAgentNotifications}
            onRightPanelToggle={handleRightPanelToggle}
        />
    );
};

export default ChatPage; 