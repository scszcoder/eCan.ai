import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { Chat, Message, Attachment, Content } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
import AgentNotify from './components/AgentNotify';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useAppDataStore } from '@/stores/appDataStore';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';
    const myTwinAgent = useAppDataStore(state => state.myTwinAgent());
    const myTwinAgentId = myTwinAgent?.card?.id;
    const initialized = useAppDataStore(state => state.initialized);

    const [chats, setChats] = useState<Chat[]>([]);
    const [activeChatId, setActiveChatId] = useState<string | null>(null);
    const [hasNewAgentNotifications, setHasNewAgentNotifications] = useState(true);
    const [agentNotifications, setAgentNotifications] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hasFetched, setHasFetched] = useState(false);
    const lastFetchedAgentId = useRef<string | undefined>();
    const prevInitialized = useRef(initialized);
    const fetchOnceRef = useRef(false);

    // tryCreateAndSelectChat 只定义一次
    const tryCreateAndSelectChat = async () => {
        if (agentId && myTwinAgentId) {
            if (!myTwinAgentId) return;
            const my_twin_agent = useAppDataStore.getState().getAgentById(myTwinAgentId);
            const receiver_agent = useAppDataStore.getState().getAgentById(agentId);
            // 1. 先调用 create_chat
            const chatData = {
                members:  [
                    {"user_id": myTwinAgentId, "role": "user", "name": my_twin_agent?.card.name || "you"},
                    {"user_id": agentId, "role": "agent", "name": receiver_agent?.card.name || "receiver agent"}
                  ],
                name: receiver_agent?.card.name || `Chat with ${agentId}`,
                type: 'user-agent',
            };
            const response = await get_ipc_api().chat.createChat(chatData);
            console.log(response.data)
            if (response.success && response.data) {
                const newChat = response.data as Chat;
                setChats(prevChats => {
                    const exists = prevChats.some(c => c.id === newChat.id);
                    if (exists) {
                        // 更新已存在的 chat
                        return prevChats.map(c => c.id === newChat.id ? { ...c, ...newChat } : c);
                    } else {
                        // 添加新 chat
                        return [...prevChats, newChat];
                    }
                });
                setActiveChatId(newChat.id);
                // 2. 获取当前 chat 的 message
                handleChatSelect(newChat.id);
            }
        }
    };

    // 页面每次显示都拉取聊天，拉取完后如有agentId再创建
    useEffect(() => {
        let cancelled = false;
        const fetchChatsAndMaybeCreate = async () => {
            if (!myTwinAgentId) return;
            setIsLoading(true);
            await getChatsAndSetState(myTwinAgentId, true);
            setIsLoading(false);
            if (agentId && !cancelled) {
                await tryCreateAndSelectChat();
            }
        };
        fetchChatsAndMaybeCreate();
        return () => { cancelled = true; };
    }, [myTwinAgentId, agentId]);

    // 通用获取聊天数据的函数，使用新的 API
    const getChatsAndSetState = async (userId?: string, setActive: boolean = false) => {
        try {
            setIsLoading(true);
            
            // 使用新的 API 获取聊天数据
            const response = await get_ipc_api().chat.getChats(
                userId || '',
                false // deep 参数，按需可调整
            );
            console.log("[chats]" + response.data)
            if (response.success && response.data) {
                let chatData: Chat[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Chat[]
                        : [];
                if (!Array.isArray(chatData)) {
                    if (chatData && typeof chatData === 'object') {
                        chatData = Object.values(chatData) as Chat[];
                    } else {
                        chatData = [];
                    }
                }
                
                // 更新所有聊天
                setChats(chatData);
                if (setActive && chatData.length > 0) {
                    setActiveChatId(chatData[0]?.id || null);
                }
                
                logger.debug('Chats loaded successfully:', chatData.length);
            } else {
                logger.error('Failed to load chats:', response.error);
                setError(response.error?.message || 'Failed to load chats');
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error loading chats:', errorMessage);
            setError(`Error loading chats: ${errorMessage}`);
        } finally {
            setIsLoading(false);
        }
    };

    // 页面初始化
    useEffect(() => {
        // 只要 initialized 变 true，重置 hasFetched
        if (initialized) setHasFetched(false);
    }, [initialized]);

    const handleFilterChange = (filters: Record<string, any>) => {
        logger.debug('Filter changed:', filters);
    };

    // 点击chat时
    const handleChatSelect = async (chatId: string) => {
        // 先本地更新未读
        const selectedChat = chats.find(c => c.id === chatId);
        if (!selectedChat) return;
        if (selectedChat.unread > 0) {
            const newChats = chats.map(chat =>
                chat.id === chatId ? { ...chat, unread: 0 } : chat
            );
            setChats(newChats);
        }
        setActiveChatId(chatId);
        // 获取最新消息
        try {
            const response = await get_ipc_api().chat.getChatMessages({ chatId });
            logger.debug("[chat message] result>>>")
            console.log(response.data)
            if (response.success && response.data) {
                let messages: Message[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Message[]
                        : [];
                setChats(prevChats => prevChats.map(c =>
                    c.id === chatId ? { ...c, messages } : c
                ));
            } else {
                // 失败时清空消息并可选提示
                setChats(prevChats => prevChats.map(c =>
                    c.id === chatId ? { ...c, messages: [] } : c
                ));
                if (response.error) {
                    setError(typeof response.error === 'string' ? response.error : response.error.message || 'Failed to load messages');
                }
            }
        } catch (err) {
            logger.error('Error fetching chat messages:', err);
            setChats(prevChats => prevChats.map(c =>
                c.id === chatId ? { ...c, messages: [] } : c
            ));
            setError('Error fetching chat messages');
        }
    };

    const handleChatDelete = async (chatId: string) => {
        try {
            // 调用 API 删除聊天
            const response = await get_ipc_api().chat.deleteChat(chatId);
            
            if (response.success) {
                // 本地更新 UI
                const updatedChats = chats.filter(c => c.id !== chatId);
                setChats(updatedChats);

                // 如果删除的是当前聊天，则切换到第一个聊天
                if (activeChatId === chatId) {
                    setActiveChatId(updatedChats[0]?.id || null);
                }
                
                logger.debug('Chat deleted successfully:', chatId);
            } else {
                logger.error('Failed to delete chat:', response.error);
                setError(`Failed to delete chat: ${response.error?.message || 'Unknown error'}`);
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error deleting chat:', errorMessage);
            setError(`Error deleting chat: ${errorMessage}`);
        }
    };

    const handleChatPin = (chatId: string) => {
        const newChats = chats.map(chat => 
            chat.id === chatId ? { ...chat, pinned: !chat.pinned } : chat
        );
        newChats.sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));
        setChats(newChats);
    };

    const handleChatMute = (chatId: string) => {
        setChats(chats.map(chat => 
            chat.id === chatId ? { ...chat, muted: !chat.muted } : chat
        ));
    };

    const handleMessageSend = async (content: string, attachments: Attachment[]) => {
        if (!activeChatId) {
            logger.error('No activeChatId!!!');
            return;
        }

        const chat = chats.find(c => c.id === activeChatId);
        if (!chat) return;

        if (!myTwinAgentId) return;
        const my_twin_agent = useAppDataStore.getState().getAgentById(myTwinAgentId);
        const senderId = my_twin_agent?.card.id;
        const senderName = my_twin_agent?.card.name;
        if (!senderId || !senderName) return;

        const userMessage: Message = {
            id: uuidv4(),
            chatId: activeChatId,
            role: "user",
            createAt: Date.now(),
            senderId,
            senderName,
            content: content,
            status: 'sending',
            attachment: attachments
        };

        // 先乐观地更新 UI
        const updatedChats = chats.map(c => {
            if (c.id !== activeChatId) return c;
            return {
                ...c,
                messages: [...(c.messages || []), userMessage],
                lastMsg: content,
                lastMsgTime: userMessage.createAt,
            };
        });
        setChats(updatedChats);

        try {
            // 使用新的 API 发送消息
            const messageData = {
                chatId: activeChatId,
                senderId, // 明确为 string
                role: "user",
                content: content,
                createAt: String(Date.now()),
                senderName,
                status: 'sending',
                attachment: attachments as any
            };
            
            const response = await get_ipc_api().chat.sendChat(messageData);
            console.log(response.data)
            if (!response.success) {
                logger.error('Failed to send message:', response.error);
                // 更新消息状态为错误
                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'error' } : m),
                    };
                }));
                return;
            }
            
            // 更新消息状态为已发送，并使用服务器返回的消息 ID
            if (response.data && (response.data as any).id) {
                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map(m => 
                            m.id === userMessage.id 
                                ? { ...m, id: (response.data as any).id, status: 'complete' } 
                                : m
                        ),
                    };
                }));
            } else {
                // 如果服务器没有返回消息 ID，则只更新状态
                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'complete' } : m),
                    };
                }));
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error sending message:', errorMessage);
            
            // 更新消息状态为错误
            setChats(prevChats => prevChats.map(c => {
                if (c.id !== activeChatId) return c;
                return {
                    ...c,
                    messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'error' } : m),
                };
            }));
        }
    };
    
    const currentChat = (!activeChatId || !chats || chats.length === 0)
        ? null
        : chats.find((c) => c.id === activeChatId) || null;

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
        <ChatDetail 
            chatId={activeChatId} 
            chats={chats}
            onSend={handleMessageSend} 
        />
    );

    const renderRightPanel = () => (
        <AgentNotify notifications={agentNotifications} />
    );

    // 显示加载状态或错误信息
    if (isLoading && chats.length === 0) {
        return <div className="loading-container">{t('common.loading')}</div>;
    }

    // 优化：无论 chats 是否为空，都渲染 ChatLayout，只是 detailsContent 为空时显示提示
    return (
        <ChatLayout
            listTitle={t('pages.chat.title')}
            detailsTitle={currentChat ? currentChat.name : t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={currentChat ? renderDetailsContent() : <div className="empty-chat-placeholder">请选择一个聊天</div>}
            agentNotifyTitle={t('pages.chat.agentNotify')}
            agentNotifyContent={renderRightPanel()}
            hasNewAgentNotifications={hasNewAgentNotifications}
            onRightPanelToggle={(collapsed) => {
                if (!collapsed) {
                    setHasNewAgentNotifications(false);
                }
            }}
        />
    );
};

export default ChatPage;
